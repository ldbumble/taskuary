"""Everything the task page can do, the Assistant can do as a tool (the owner, 2026-09-25: "anything you can do on
the actual task should be in assistant tools available"). Each case is the model's CALL line, scripted, then the
card's confirm button through the shared handler - and the task afterwards is what the page's own button leaves."""
import json, unittest
from unittest import mock

from taskuary import concierge, ingest, toolcatalog
import tests.test_assistant_reactions as T


def call(s, tool, key=None, **params):
    """The model names a tool - the CALL line, scripted - and the card it becomes."""
    out = T.say(s, 'do it', key=key, model='On it.' + chr(10) + 'CALL: ' + json.dumps({'kind': tool, 'params': params}))
    return out.get('proposal'), out


def table(s=None, **kw):
    s = s or T.store()
    with mock.patch.object(ingest, '_spawn'):
        out = T.arrive(s, llm=T.brain('task', 'coding'), who='Erin Blake', email='erin@northwind.example',
                       to=('alex@northwind.example',), **kw)
    return s, out['task_id'], out['message_id'], T.pile(s)[0]


class CatalogueTests(unittest.TestCase):
    def test_every_task_page_action_is_a_tool_the_model_is_shown(self):
        block = toolcatalog.block()
        for kind in ('task.update', 'task.set_kind', 'task.set_repo', 'task.check', 'task.comment', 'task.handoff', 'task.merge',
                     'task.clarify', 'task.reopen', 'task.not_a_task', 'task.complete', 'task.defer', 'task.split',
                     'dispatch.prepare', 'agent.continue', 'agent.stop', 'agent.answer', 'review.approve', 'review.reject'):
            self.assertIn(kind, block, kind)

    def test_forward_and_split_are_tools_not_words_the_code_matches(self):
        for verb in ('forward', 'split', 'setting'): self.assertNotIn(verb, concierge.VERBS)


class TargetTests(unittest.TestCase):
    def test_a_task_tool_on_a_mail_card_acts_on_its_task_not_the_mails_number(self):
        s, tid, mid, item = table()
        s.update_task(tid, {'Title': 'padding'}, 'o')
        for _ in range(3): table(s, subject=f'filler {_}')          # task and message numbers drift apart
        p, _ = call(s, 'task.update', key=item['key'], priority='high')
        self.assertEqual(p['target'], tid)

    def test_a_named_task_wins_and_an_unknown_one_changes_nothing(self):
        s, tid, mid, item = table()
        s2, other, _, _ = table(s, subject='Another job')
        p, _ = call(s, 'task.comment', key=item['key'], text='noted', ref=f'TQ-{other:04d}')
        self.assertEqual(p['target'], other)
        p, out = call(s, 'task.comment', text='noted', ref='TQ-9999')
        self.assertIsNone(p); self.assertIn('Name the task', out['say'])


class ToolTests(unittest.TestCase):
    def run_card(self, s, p):
        r = T.run(s, p)
        self.assertEqual(r.status_code, 200, r.text[:300])
        return r.json()

    def test_update_changes_priority_and_takes_it_for_me(self):
        s, tid, mid, item = table()
        p, _ = call(s, 'task.update', key=item['key'], priority='urgent', assignee='me')
        self.run_card(s, p)
        t = s.get_task(tid)
        self.assertEqual((t['Priority'], t['Assignee']), ('urgent', 'owner'))

    def test_a_note_lands_on_the_task(self):
        s, tid, mid, item = table()
        self.run_card(s, call(s, 'task.comment', key=item['key'], text='Erin wants it by Friday')[0])
        self.assertIn('Erin wants it by Friday', [c['Body'] for c in s.list_comments(tid)])

    def test_a_checklist_item_is_ticked_by_number_or_words(self):
        s, tid, mid, item = table()
        s.set_checklist(tid, ['Pull the export log', 'Fix the filter'], 'o') if hasattr(s, 'set_checklist') else \
            s._write_checklist(tid, [{'id': 'a', 'text': 'Pull the export log', 'done': False}, {'id': 'b', 'text': 'Fix the filter', 'done': False}], 'o')
        self.run_card(s, call(s, 'task.check', key=item['key'], item='1')[0])
        self.assertEqual([i['done'] for i in s.task_checklist(tid)], [True, False])
        self.run_card(s, call(s, 'task.check', key=item['key'], item='filter')[0])
        self.assertEqual(s.get_task(tid)['Status'], 'done', 'the last box is Mark done')

    def test_reopen_and_not_a_task(self):
        s, tid, mid, item = table()
        s.update_task(tid, {'Status': 'done'}, 'o')
        self.run_card(s, call(s, 'task.reopen', ref=f'TQ-{tid:04d}')[0])
        self.assertEqual(s.get_task(tid)['Status'], 'open')
        s2, t2, _, i2 = table()
        self.run_card(s2, call(s2, 'task.not_a_task', key=i2['key'])[0])
        self.assertIn((s2.get_task(t2) or {}).get('Status'), (None, 'dropped', 'done'))

    def test_kind_changes_down_the_task_pages_road(self):
        s, tid, mid, item = table()
        self.run_card(s, call(s, 'task.set_kind', key=item['key'], kind='general')[0])
        self.assertEqual(s.get_task(tid)['Kind'], 'general')

    def test_merge_folds_it_into_the_named_task(self):
        s, keep, _, _ = table()
        s, gone, _, item = table(s, subject='Can you fix the export? (again)')
        self.run_card(s, call(s, 'task.merge', ref=f'TQ-{gone:04d}', into=f'TQ-{keep:04d}')[0])
        self.assertEqual(s.get_task(gone)['Status'], 'dropped')

    def test_hand_off_and_ask_the_sender_each_write_a_draft_and_send_nothing(self):
        s, tid, mid, item = table()
        with mock.patch('taskuary.outbound.draft_handoff', return_value='Can you take this one?'), \
             mock.patch('taskuary.outbound.send_email') as sent:
            self.run_card(s, call(s, 'task.handoff', key=item['key'], who='Erin')[0])
            sent.assert_not_called()
        rv = s.pending_review(tid, live_only=False)
        self.assertIn('erin@northwind.example', rv['Deliver'])
        s2, t2, _, i2 = table()
        self.run_card(s2, call(s2, 'task.clarify', key=i2['key'], text='Which date range do you need?')[0])
        self.assertTrue(any('Which date range' in (r.get('DraftText') or '') for r in s2.list_reviews('pending')))

    def test_reject_the_draft_leaves_the_task_open(self):
        s, tid, rid, item = T.ResponseTests()._drafted()
        p, _ = call(s, 'review.reject', key=item['key'])
        self.assertEqual(p['target'], rid)
        self.run_card(s, p)
        self.assertEqual(s.get_review(rid)['Status'], 'rejected')
        self.assertNotEqual(s.get_task(tid)['Status'], 'done')

    def test_stop_names_its_agent_or_stops_nothing(self):
        s, tid, mid, item = table()
        p, out = call(s, 'agent.stop', ref=f'TQ-{tid:04d}')
        self.assertEqual((p['kind'], p['target'], p['params'].get('wrap')), ('agent.stop', tid, True))
        p, out = call(s, 'agent.stop')
        self.assertIsNone(p)


class ModelShapeTests(unittest.TestCase):
    """The shapes the real brain wrote when it chose a task tool (the replay, 2026-09-25): a DECIDE line naming the
    tool. Each is read as the CALL it means; anything that would not validate is still no action at all."""
    def test_a_tool_named_on_a_decide_line_is_the_call_it_means(self):
        for line, want in (('DECIDE: task.update: priority urgent', ('task.update', {'priority': 'urgent'})),
                           ('DECIDE: task.reopen ON: TQ-0737', ('task.reopen', {'ref': 'TQ-0737'})),
                           ('DECIDE: task.comment ON: TQ-0736: Erin wants it by Friday', ('task.comment', {'ref': 'TQ-0736', 'text': 'Erin wants it by Friday'})),
                           ('DECIDE: task.merge ON: TQ-0735: into TQ-0738', ('task.merge', {'ref': 'TQ-0735', 'into': 'TQ-0738'})),
                           ('DECIDE: task.clarify: which date range they need', ('task.clarify', {'text': 'which date range they need'}))):
            got = concierge.parse_call('On it.' + chr(10) + line)[1]
            self.assertEqual((got['kind'], got['params']), want, line)

    def test_a_plain_verb_or_an_unknown_tool_is_not_a_call(self):
        for line in ('DECIDE: next', 'DECIDE: made.up: 1', 'DECIDE: task.merge'):
            self.assertIsNone(concierge.parse_call('Ok.' + chr(10) + line)[1], line)

    def test_the_card_runs_from_it(self):
        s, tid, mid, item = table()
        out = T.say(s, 'make this one urgent', key=item['key'], model='Setting it.' + chr(10) + 'DECIDE: task.update: priority urgent')
        self.assertEqual((out['proposal']['kind'], out['proposal']['target']), ('task.update', tid))
