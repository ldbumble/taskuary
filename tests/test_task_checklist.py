"""A task's checkable list (PW-074 to PW-078).

Triage names the row (a title) and nothing else (2026-11-23): the ask is the sender's own words and the to-dos are the task's agent's
or the owner's to write. The checklist is persisted on the task with stable item ids, rendered as GitHub task-list Markdown
(`- [ ]` / `- [x]`), shared by the task page, the assistant and the worker brief, and kept
separate from task completion: ticking every box closes nothing, and closing a task ticks nothing.
The owner's own edits are kept.
"""
import json, tempfile, unittest
from pathlib import Path
from unittest import mock
from fastapi.testclient import TestClient

from taskuary import ingest, server, terminal
from taskuary.store import MemoryStore, SQLiteStore

MSG = {'external_id': 'e1', 'channel': 'email', 'from_email': 'dana@vendor.example', 'from_name': 'Dana', 'conversation_id': 'AAQk-onboard',
       'subject': 'Re: Re: FW: stuff', 'sent_at': '2026-09-06 09:00:00',
       'body': 'Hi Alex,\n\nTwo things before Friday: please add Priya to the payroll portal, and send me the August export.\n\nThanks,\nDana'}


TODOS = ['Add Priya to the payroll portal', 'Send Dana the August export']


def made(s, **kw):
    "The task the mail makes, with the to-dos its agent wrote (triage writes none)."
    with mock.patch.object(ingest, '_spawn'):
        tid = ingest.ingest_message(s, dict(MSG), llm=verdict(**kw))['task_id']
    s.set_task_checklist(tid, TODOS, 'agent')
    return tid


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
    def test_the_title_comes_from_the_verdict_and_the_ask_is_the_senders_own_words(self):
        s = MemoryStore()
        with mock.patch.object(ingest, '_spawn'):
            out = ingest.ingest_message(s, dict(MSG), llm=verdict())
        t = s.get_task(out['task_id'])
        self.assertEqual(t['Title'], 'Add Priya to payroll and send the August export')
        self.assertIn('Two things before Friday', t['Summary'])
        self.assertEqual(s.task_checklist(out['task_id']), [])               # the verdict's checklist writes nothing
        s.set_task_checklist(out['task_id'], TODOS, 'agent')
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

class ProgressTests(unittest.TestCase):
    def setUp(self):
        self.s = MemoryStore()
        p = mock.patch.object(server, 'store', self.s); p.start(); self.addCleanup(p.stop)
        self.c = TestClient(server.app)
        self.tid = made(self.s)
        self.items = self.s.task_checklist(self.tid)

    def test_ticking_a_box_persists_and_shows_on_the_task_detail(self):
        r = self.c.patch(f'/api/tasks/{self.tid}/checklist/{self.items[0]["id"]}', json={'done': True})
        self.assertEqual(r.status_code, 200)
        detail = self.c.get(f'/api/tasks/{self.tid}').json()
        self.assertEqual([i['done'] for i in detail['checklist']], [True, False])
        self.assertIn('- [x] Add Priya to the payroll portal', detail['task']['ChecklistMd'])

    def test_a_tick_never_closes_and_closing_ticks_every_box(self):
        """A tick is a tick: Mark done is the close (T16, the owner, 2026-09-25 - the last tick closed it from
        2026-09-18 to then). And closing ticks every box. "The list records what was done" left a coding agent's
        `--done` on TQ-0646 showing three open boxes on a closed card (the owner, 2026-09-18: "part of
        --done should be that, no? same if it's saved manually"). Dropped still ticks nothing."""
        first, last = self.items
        self.c.patch(f'/api/tasks/{self.tid}/checklist/{first["id"]}', json={'done': True})
        self.assertEqual(self.s.get_task(self.tid)['Status'], 'open')            # one box left: still open
        self.c.patch(f'/api/tasks/{self.tid}/checklist/{last["id"]}', json={'done': True})
        self.assertEqual(self.s.get_task(self.tid)['Status'], 'open')            # Mark done is the close (T16)
        self.assertEqual([i['done'] for i in self.s.task_checklist(self.tid)], [True, True])
        s2 = MemoryStore(); tid2 = made(s2)
        s2.update_task(tid2, {'Status': 'done'}, 'owner')
        self.assertEqual([i['done'] for i in s2.task_checklist(tid2)], [True, True])
        s2.update_task(tid2, {'Status': 'open'}, 'owner')                        # reopening un-ticks nothing
        s3 = MemoryStore(); tid3 = made(s3)
        s3.update_task(tid3, {'Status': 'dropped'}, 'owner')
        self.assertEqual([i['done'] for i in s3.task_checklist(tid3)], [False, False])

    def test_the_owner_edits_the_list_and_progress_survives_where_the_words_did(self):
        self.c.patch(f'/api/tasks/{self.tid}/checklist/{self.items[0]["id"]}', json={'done': True})
        r = self.c.put(f'/api/tasks/{self.tid}/checklist', json={'items': ['Add Priya to the payroll portal', 'Send Dana the July AND August exports', 'Confirm with Dana']})
        self.assertEqual(r.status_code, 200)
        items = self.s.task_checklist(self.tid)
        self.assertEqual([(i['text'], i['done']) for i in items],
                         [('Add Priya to the payroll portal', True), ('Send Dana the July AND August exports', False), ('Confirm with Dana', False)])
        self.assertEqual(items[0]['id'], self.items[0]['id'])

class PreservationTests(unittest.TestCase):
    def test_substantive_case_operators_and_internal_spacing_stay_distinct_while_old_id_and_tick_survive(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'checklist.db'
            s = SQLiteStore(str(path))
            tid = s.create_task({'Title': 'Exact checklist identity'}, 'owner')
            legacy_id = 'legacy42'
            s._exec('UPDATE task SET Checklist=? WHERE TaskId=?', (json.dumps([
                {'id': legacy_id, 'text': 'x >= 3', 'done': True},
            ]), tid))

            added = s.merge_task_checklist(tid, [
                'x <= 3', 'X >= 3', 'A  B', 'A B',
                'Inspect /Data/Export.csv.', 'Inspect /data/export.csv.',
            ], 'triage')
            items = s.task_checklist(tid)

            self.assertEqual(items[0], {'id': legacy_id, 'text': 'x >= 3', 'done': True})
            self.assertEqual(added, items[1:])
            self.assertEqual([i['text'] for i in items],
                             ['x >= 3', 'x <= 3', 'X >= 3', 'A  B', 'A B',
                              'Inspect /Data/Export.csv.', 'Inspect /data/export.csv.'])
            self.assertEqual(len({i['id'] for i in items}), 7)
            self.assertEqual(s.set_task_checklist(tid, [i['text'] for i in items], 'owner'), items)
            s.close()
            reopened = SQLiteStore(str(path))
            self.assertEqual(reopened.task_checklist(tid), items)
            reopened.close()

    def test_owner_reorder_cannot_let_a_new_box_steal_a_retained_legacy_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'reserved-id.db'
            s = SQLiteStore(str(path))
            tid = s.create_task({'Title': 'Stable action targets'}, 'owner')
            retained_id = s.checklist_id('step 1')
            s._exec('UPDATE task SET Checklist=? WHERE TaskId=?', (json.dumps([
                {'id': retained_id, 'text': 'Step 1.', 'done': True},
            ]), tid))

            items = s.set_task_checklist(tid, ['step 1', 'Step 1.'], 'owner')

            self.assertEqual(items[1], {'id': retained_id, 'text': 'Step 1.', 'done': True})
            self.assertNotEqual(items[0]['id'], retained_id)
            self.assertEqual(len({item['id'] for item in items}), 2)
            s.close()

            reopened = SQLiteStore(str(path))
            self.assertEqual(reopened.task_checklist(tid), items)
            self.assertTrue(reopened.tick_checklist_item(tid, retained_id, False, 'owner'))
            self.assertFalse(reopened.task_checklist(tid)[1]['done'])
            reopened.close()

    def test_thirteenth_item_is_durable_repeated_once_and_owner_can_edit_and_tick_past_twelve(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'thirteen.db'
            s = SQLiteStore(str(path))
            tid = s.create_task({'Title': 'Accumulated checklist'}, 'owner')
            first = s.set_task_checklist(tid, [f'step {i}' for i in range(12)], 'triage')
            self.assertTrue(s.tick_checklist_item(tid, first[0]['id'], True, 'owner'))

            added = s.merge_task_checklist(tid, ['step 12'], 'triage')
            persisted = s.task_checklist(tid)
            self.assertEqual(len(persisted), 13)
            self.assertEqual(added, persisted[12:])
            self.assertEqual(s.merge_task_checklist(tid, ['step 12'], 'triage'), [])
            self.assertEqual(s.task_checklist(tid)[0], {**first[0], 'done': True})

            edited = s.set_task_checklist(tid, [*[f'step {i}' for i in range(13)], 'step 13'], 'owner')
            self.assertEqual(len(edited), 14)
            self.assertEqual(edited[0], {**first[0], 'done': True})
            self.assertTrue(s.tick_checklist_item(tid, edited[13]['id'], True, 'owner'))
            s.close()

            reopened = SQLiteStore(str(path))
            after = reopened.task_checklist(tid)
            self.assertEqual(len(after), 14)
            self.assertTrue(after[0]['done'])
            self.assertTrue(after[13]['done'])
            reopened.close()

class SharedContextTests(unittest.TestCase):
    def test_the_worker_brief_carries_the_checklist_and_the_source_message(self):
        s = MemoryStore(); s.set_setting('owner_email', 'alex@vendor.example', 't')
        # a colleague's mail is the owner's own domain; an unvouched sender would be a stranger's, whose words ride in a file (tests/test_origin_seed.py)
        tid = made(s, kind='coding')
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
