"""Triage names the work: a meaningful title, a summary and a checkable list (PW-074 to PW-078).

A task used to be titled with the subject and summarised with the first 1,000 characters of the
body. The same triage verdict now carries `title`, `summary` and `checklist` for `intent=task`,
derived from the cleaned context and never inventing requirements or claiming work done. The
checklist is persisted on the task with stable item ids, rendered as GitHub task-list Markdown
(`- [ ]` / `- [x]`), shared by the task page, the assistant and the worker brief, and kept
separate from task completion: ticking every box closes nothing, and closing a task ticks nothing.
A later message that adds a distinct request merges in without duplicating items or resetting
checked boxes; the owner's own edits are kept.
"""
import json, unittest
from unittest import mock
from fastapi.testclient import TestClient

from taskuary import ingest, server, terminal
from taskuary.store import MemoryStore

MSG = {'external_id': 'e1', 'channel': 'email', 'from_email': 'dana@vendor.example', 'from_name': 'Dana', 'conversation_id': 'AAQk-onboard',
       'subject': 'Re: Re: FW: stuff', 'sent_at': '2026-09-06 09:00:00',
       'body': 'Hi Uri,\n\nTwo things before Friday: please add Priya to the payroll portal, and send me the August export.\n\nThanks,\nDana'}


def verdict(title='Add Priya to payroll and send the August export', summary='Dana needs Priya added to the payroll portal and the August export sent, by Friday.',
            checklist=('Add Priya to the payroll portal', 'Send Dana the August export'), kind='general', **extra):
    def llm(system, user, **k):
        j = {'intent': 'task', 'kind': kind, 'why': 'two asks', **extra}
        if title is not None: j['title'] = title
        if summary is not None: j['summary'] = summary
        if checklist is not None: j['checklist'] = list(checklist) if isinstance(checklist, (list, tuple)) else checklist
        return json.dumps(j)
    return llm


class VerdictNamesTheWorkTests(unittest.TestCase):
    def test_title_summary_and_checklist_come_from_the_verdict(self):
        s = MemoryStore()
        with mock.patch.object(ingest, '_spawn'):
            out = ingest.ingest_message(s, dict(MSG), llm=verdict())
        t = s.get_task(out['task_id'])
        self.assertEqual(t['Title'], 'Add Priya to payroll and send the August export')
        self.assertIn('by Friday', t['Summary'])
        items = s.task_checklist(out['task_id'])
        self.assertEqual([i['text'] for i in items], ['Add Priya to the payroll portal', 'Send Dana the August export'])
        self.assertTrue(all(i['id'] and i['done'] is False for i in items))
        self.assertEqual(s.checklist_markdown(out['task_id']), '- [ ] Add Priya to the payroll portal\n- [ ] Send Dana the August export')

    def test_without_them_the_old_title_and_summary_still_apply(self):
        s = MemoryStore()
        with mock.patch.object(ingest, '_spawn'):
            out = ingest.ingest_message(s, dict(MSG), llm=verdict(title=None, summary=None, checklist=None))
        t = s.get_task(out['task_id'])
        self.assertEqual(t['Title'], 'Stuff'); self.assertIn('Two things before Friday', t['Summary'])   # the router's subject cut, prefixes stripped
        self.assertEqual(s.task_checklist(out['task_id']), [])

    def test_the_checklist_is_validated_not_trusted(self):
        s = MemoryStore()
        junk = ['  Add Priya to the payroll portal ', 'add priya to the payroll portal', '', 42, {'x': 1}] + [f'step {i}' for i in range(20)]
        with mock.patch.object(ingest, '_spawn'):
            out = ingest.ingest_message(s, dict(MSG), llm=verdict(checklist=junk, title='x' * 500))
        items = s.task_checklist(out['task_id'])
        self.assertEqual(items[0]['text'], 'Add Priya to the payroll portal')
        self.assertEqual(len([i for i in items if i['text'].lower() == 'add priya to the payroll portal']), 1)
        self.assertLessEqual(len(items), 12)
        self.assertLessEqual(len(s.get_task(out['task_id'])['Title']), 120)
        s2 = MemoryStore()
        with mock.patch.object(ingest, '_spawn'):
            out2 = ingest.ingest_message(s2, dict(MSG), llm=verdict(checklist='not a list'))
        self.assertEqual(s2.task_checklist(out2['task_id']), [])


class ProgressTests(unittest.TestCase):
    def setUp(self):
        self.s = MemoryStore()
        p = mock.patch.object(server, 'store', self.s); p.start(); self.addCleanup(p.stop)
        self.c = TestClient(server.app)
        with mock.patch.object(ingest, '_spawn'):
            self.tid = ingest.ingest_message(self.s, dict(MSG), llm=verdict())['task_id']
        self.items = self.s.task_checklist(self.tid)

    def test_ticking_a_box_persists_and_shows_on_the_task_detail(self):
        r = self.c.patch(f'/api/tasks/{self.tid}/checklist/{self.items[0]["id"]}', json={'done': True})
        self.assertEqual(r.status_code, 200)
        detail = self.c.get(f'/api/tasks/{self.tid}').json()
        self.assertEqual([i['done'] for i in detail['checklist']], [True, False])
        self.assertIn('- [x] Add Priya to the payroll portal', detail['task']['ChecklistMd'])

    def test_ticking_every_box_completes_nothing_and_closing_ticks_nothing(self):
        for i in self.items: self.c.patch(f'/api/tasks/{self.tid}/checklist/{i["id"]}', json={'done': True})
        self.assertEqual(self.s.get_task(self.tid)['Status'], 'open')
        self.s.update_task(self.tid, {'Status': 'done'}, 'owner')
        self.assertEqual([i['done'] for i in self.s.task_checklist(self.tid)], [True, True])
        self.s.update_task(self.tid, {'Status': 'open'}, 'owner')
        s2 = MemoryStore()
        with mock.patch.object(ingest, '_spawn'):
            tid2 = ingest.ingest_message(s2, dict(MSG), llm=verdict())['task_id']
        s2.update_task(tid2, {'Status': 'done'}, 'owner')
        self.assertEqual([i['done'] for i in s2.task_checklist(tid2)], [False, False])

    def test_the_owner_edits_the_list_and_progress_survives_where_the_words_did(self):
        self.c.patch(f'/api/tasks/{self.tid}/checklist/{self.items[0]["id"]}', json={'done': True})
        r = self.c.put(f'/api/tasks/{self.tid}/checklist', json={'items': ['Add Priya to the payroll portal', 'Send Dana the July AND August exports', 'Confirm with Dana']})
        self.assertEqual(r.status_code, 200)
        items = self.s.task_checklist(self.tid)
        self.assertEqual([(i['text'], i['done']) for i in items],
                         [('Add Priya to the payroll portal', True), ('Send Dana the July AND August exports', False), ('Confirm with Dana', False)])
        self.assertEqual(items[0]['id'], self.items[0]['id'])

    def test_a_later_message_adds_distinct_items_without_duplicates_or_resets(self):
        self.c.patch(f'/api/tasks/{self.tid}/checklist/{self.items[0]["id"]}', json={'done': True})
        follow = {**MSG, 'external_id': 'e2', 'sent_at': '2026-09-06 10:00:00', 'subject': 'Re: Re: FW: stuff',
                  'body': 'Also - please add Priya to the payroll portal AND remove Sam from it.'}
        with mock.patch.object(ingest, '_spawn'):
            out = ingest.ingest_message(self.s, follow, llm=verdict(checklist=('Add Priya to the payroll portal', 'Remove Sam from the payroll portal')))
        self.assertEqual(out['task_id'], self.tid)
        items = self.s.task_checklist(self.tid)
        self.assertEqual([(i['text'], i['done']) for i in items],
                         [('Add Priya to the payroll portal', True), ('Send Dana the August export', False), ('Remove Sam from the payroll portal', False)])
        notes = [c['Body'] for c in self.s.list_comments(self.tid)]
        self.assertTrue(any('Remove Sam from the payroll portal' in n for n in notes), notes)   # the change is surfaced, not silent


class SharedContextTests(unittest.TestCase):
    def test_the_worker_brief_carries_the_checklist_and_the_source_message(self):
        s = MemoryStore()
        with mock.patch.object(ingest, '_spawn'):
            tid = ingest.ingest_message(s, dict(MSG), llm=verdict(kind='coding'))['task_id']
        text = terminal.seed_text(s, tid)
        self.assertIn('CHECKLIST', text); self.assertIn('- [ ] Add Priya to the payroll portal', text)
        self.assertIn('Two things before Friday', text)                    # the source stays accessible beside the list

    def test_the_task_detail_payload_shares_the_same_list(self):
        s = MemoryStore()
        with mock.patch.object(server, 'store', s), mock.patch.object(ingest, '_spawn'):
            tid = ingest.ingest_message(s, dict(MSG), llm=verdict())['task_id']
            d = TestClient(server.app).get(f'/api/tasks/{tid}').json()
        self.assertEqual([i['text'] for i in d['checklist']], [i['text'] for i in s.task_checklist(tid)])


if __name__ == '__main__':
    unittest.main()
