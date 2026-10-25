"""Everything the task page can do, the Assistant can do as a tool (the owner, 2026-09-25: "anything you can do on
the actual task should be in assistant tools available"). Each case is the model's CALL line, scripted, then the
card's confirm button through the shared handler - and the task afterwards is what the page's own button leaves."""
import json, unittest
from unittest import mock

from taskuary import concierge, ingest, toolcatalog
import tests.test_assistant_reactions as T


# THE PHONE'S ROAD (the owner, 2026-10-19): on the desk a typed act lights its button or opens its page and proposes nothing
# (test_assistant_router); a phone chat has no buttons, so a tool the model names still becomes a proposal answered yes or no -
# the proposals, their targets and their handlers are held here, on that road
def setUpModule():
    global _ROAD
    from taskuary import concierge
    _ROAD = concierge.DELIVERY.set(concierge.PHONE)
def tearDownModule():
    from taskuary import concierge
    concierge.DELIVERY.reset(_ROAD)


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
        # a note is the Assistant's to write at once, on the phone too (the owner, 2026-10-20) - on the task the ref names
        p, out = call(s, 'task.comment', key=item['key'], text='noted', ref=f'TQ-{other:04d}')
        self.assertIsNone(p); self.assertIn('noted', [c['Body'] for c in s.list_comments(other)])
        self.assertNotIn('noted', [c['Body'] for c in s.list_comments(tid)])
        p, out = call(s, 'task.comment', text='noted', ref='TQ-9999')
        self.assertIsNone(p); self.assertIn('Name the task', out['say'])


    def test_an_agent_is_never_put_on_the_task_on_the_table_unless_the_call_names_it(self):
        """The owner, 2026-09-29: "if i ask for task it should not merge with old one or agent run unless i ask". A new
        job typed while a task sat on the table became dispatch.prepare with no ref - a run on THAT task."""
        s, tid, mid, item = table()
        for tool in ('dispatch.prepare', 'agent.continue'):
            p, out = call(s, tool, key=item['key'], kind='coding', instructions='review the widgets repo')
            self.assertIsNone(p, tool)
        p, _ = call(s, 'dispatch.prepare', key=item['key'], kind='coding', ref=f'TQ-{tid:04d}')
        self.assertEqual(p['target'], tid, 'named, the task on the table is still one call away')

    def test_continue_session_on_the_table_reopens_its_own_saved_session_without_a_ref(self):
        """2026-09-30: "continue the session and tell the coding agent to merge it in" on a close-out card was refused for want
        of a ref, and the retry settled on the close-out - a merge the owner had asked the AGENT to make. Continuing reopens the
        task's own saved session, so the table's task is what is meant; a task with no session to reopen still must be named."""
        s, tid, mid, item = table()
        p, out = call(s, 'agent.continue', key=item['key'], note='merge it in')
        self.assertIsNone(p, 'nothing saved on the task: still a miss, never an agent on it')
        s.add_transcript(tid, 'pane-1', 'reviewed it', agent='coding', cwd='.', ext_id='thread-1')
        item = T.pile(s)[0]
        p, out = call(s, 'agent.continue', key=item['key'], note='merge it in')
        self.assertEqual((p['kind'], p['target'], p['params']['note']), ('agent.continue', tid, 'merge it in'))

    def test_the_hand_offs_name_is_read_as_its_kind_and_never_falls_to_a_regular_agent(self):
        """2026-09-29 replay: kind "coding" became a card labelled "Start a regular agent" that waited for a yes.
        LEGACY kind on purpose: the old name a model may still say is read as coding."""
        s = T.store()
        p, _ = call(s, 'task.create_from_text', kind='coder', text='review the widgets repo for the portal')
        self.assertIn('coding agent', p['label'])
        p, out = call(s, 'task.create_from_text', kind='robot', text='review the widgets repo')
        self.assertIsNone(p, 'an unknown kind is the model\'s to fix, never a silent regular agent')


class ToolTests(unittest.TestCase):
    def run_card(self, s, p):
        r = T.run(s, p)
        self.assertEqual(r.status_code, 200, r.text[:300])
        return r.json()

    def test_a_finished_agents_card_tells_the_model_its_session_is_there_and_offers_no_continue_pill(self):
        # "can you do that? just null those two" on a finished agent's card was read as a new job and opened a second task:
        # the model had only the summary. It is told the session exists - it decides (2026-10-08: never code in front of it).
        # Its ROW draws no Continue (the owner, 2026-10-18: "no keep going if finished") - what is typed still reaches the session
        s, tid, mid, item = table()
        s.add_transcript(tid, 'sid-1', 'found the two accounts', agent='coding', ext_id='abc-123', brain='claude')
        done = {**item, 'kind': 'agentdone', 'lane': 'agent', 'summary': 'found the two accounts', 'tid': tid, 'ref': f'TQ-{tid:04d}'}
        said = concierge.facts(s, done)
        self.assertIn('AGENT SESSION', said)
        self.assertIn('agent.continue', said)
        self.assertNotIn('continue', [c['verb'] for c in concierge.chips_for(s, done)])

    def test_a_card_with_no_saved_session_says_nothing_about_one(self):
        s, tid, mid, item = table()
        self.assertNotIn('AGENT SESSION', concierge.facts(s, {**item, 'tid': tid}))

    def test_the_model_choosing_a_new_task_is_left_to_be_a_new_task(self):
        s, tid, mid, item = table()
        s.add_transcript(tid, 'sid-1', 'x', agent='coding', ext_id='abc-123', brain='claude')
        p, _ = call(s, 'task.create_from_text', kind='coding', text=f'Like TQ-{tid:04d} but for the portal: fix the export')
        self.assertEqual(p['kind'], 'task.create_from_text', p)

    def test_update_changes_priority_and_takes_it_for_me(self):
        s, tid, mid, item = table()
        p, _ = call(s, 'task.update', key=item['key'], priority='urgent', assignee='owner')
        self.run_card(s, p)
        t = s.get_task(tid)
        self.assertEqual((t['Priority'], t['Assignee']), ('urgent', 'owner'))

    def test_a_note_lands_on_the_task(self):
        s, tid, mid, item = table()
        p, out = call(s, 'task.comment', key=item['key'], text='Erin wants it by Friday')
        self.assertIsNone(p); self.assertTrue(out['say'].startswith('Added a note to'), out['say'])      # written at once, and said
        self.assertIn('Erin wants it by Friday', [c['Body'] for c in s.list_comments(tid)])

    def test_a_checklist_item_is_ticked_by_its_number(self):
        s, tid, mid, item = table()
        s.set_checklist(tid, ['Pull the export log', 'Fix the filter'], 'o') if hasattr(s, 'set_checklist') else \
            s._write_checklist(tid, [{'id': 'a', 'text': 'Pull the export log', 'done': False}, {'id': 'b', 'text': 'Fix the filter', 'done': False}], 'o')
        p, out = call(s, 'task.check', key=item['key'], item='1')
        self.assertIsNone(p); self.assertTrue(out['say'].startswith('Ticked'), out['say'])
        self.assertEqual([i['done'] for i in s.task_checklist(tid)], [True, False])
        call(s, 'task.check', key=item['key'], item='2')
        self.assertEqual([i['done'] for i in s.task_checklist(tid)], [True, True])
        self.assertNotEqual(s.get_task(tid)['Status'], 'done', 'Mark done is the close, never the last box (T16)')

    def test_words_off_the_contract_are_the_models_to_fix_never_guessed(self):
        """The owner, 2026-10-11: no word lists. 'me' was read as the owner, any word became agent:<word>, and a checklist
        item was the first one containing the words. Now each is refused before a card, naming what IS allowed."""
        s, tid, mid, item = table()
        s._write_checklist(tid, [{'id': 'a', 'text': 'Pull the export log', 'done': False}, {'id': 'b', 'text': 'Fix the filter', 'done': False}], 'o')
        for tool, kw, says in (('task.update', {'assignee': 'me'}, 'owner'), ('task.update', {'assignee': 'robot'}, 'owner'),
                               ('task.update', {'due': 'soonish'}, 'YYYY-MM-DD'), ('task.check', {'item': 'filter'}, '2. Fix the filter')):
            with self.subTest(tool=tool, kw=kw):
                dock = concierge.general.dock_task(s, 'owner')[0]['TaskId']
                with self.assertRaises(concierge.CallMiss) as e:
                    concierge.call_turn(s, dock, {'kind': tool, 'params': {**kw, 'ref': f'TQ-{tid:04d}'}}, item, 'do it')
                self.assertIn(says, str(e.exception))
        self.assertEqual([i['done'] for i in s.task_checklist(tid)], [False, False])
        self.assertNotEqual(s.get_task(tid)['Assignee'], 'agent:robot')

    def test_the_card_run_holds_the_same_contract(self):
        from taskuary import server
        s, tid, mid, item = table()
        with mock.patch.object(server, 'store', s):
            for kw in ({'assignee': 'myself'}, {'due': 'whenever'}):
                with self.assertRaises(server.HTTPException) as e: server._run_operation({'kind': 'task.update', 'target': tid, 'params': kw}, None)
                self.assertEqual(e.exception.status_code, 422)
            out = server._run_operation({'kind': 'task.update', 'target': tid, 'params': {'assignee': 'owner', 'due': 'friday'}}, None)
            self.assertEqual(s.get_task(tid)['Assignee'], 'owner'); self.assertTrue(out['changed']['DueAt'])
            server._run_operation({'kind': 'task.update', 'target': tid, 'params': {'due': 'none'}}, None)
            self.assertFalse(s.get_task(tid)['DueAt'])

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

    def test_send_out_results_is_a_card_that_drafts_and_sort_it_again_runs_the_rows_retriage(self):
        """Both were the page's alone (2026-10-18): each is a tool now, down the page's own handler - and a send still waits for a yes."""
        from taskuary import server
        s, tid, mid, item = table()
        p, _ = call(s, 'task.share', key=item['key'], who='Erin', about='the export is fixed')
        self.assertEqual((p['kind'], p.get('auto')), ('task.share', None))
        with mock.patch('taskuary.outbox.task_email', return_value={'ok': True}) as te:
            self.run_card(s, p)
        self.assertEqual(te.call_args.args[1:4], (tid, 'erin@northwind.example', 'the export is fixed'))
        with mock.patch.object(server, 'store', s), mock.patch.object(server, 'retriage_message', return_value={'task_id': None}) as rt:
            server._run_operation({'kind': 'message.retriage', 'target': mid, 'params': {}}, None)
        rt.assert_called_once_with(mid)
        dock = concierge.general.dock_task(s, 'owner')[0]['TaskId']
        with self.assertRaises(concierge.CallMiss):
            concierge.call_turn(s, dock, {'kind': 'task.share', 'params': {'who': 'Omar Keller', 'ref': f'TQ-{tid}'}}, item, 'send it to Omar')

    def test_reject_the_draft_leaves_the_task_open(self):
        s, tid, rid, item = T.ResponseTests()._drafted()
        p, _ = call(s, 'review.reject', key=item['key'])
        self.assertEqual(p['target'], rid)
        self.run_card(s, p)
        self.assertEqual(s.get_review(rid)['Status'], 'rejected')
        self.assertNotEqual(s.get_task(tid)['Status'], 'done')

    def test_stop_names_its_agent_or_stops_nothing(self):
        s, tid, mid, item = table()
        with mock.patch.object(concierge, '_agent_running', return_value=True):
            p, out = call(s, 'agent.stop', ref=f'TQ-{tid:04d}')
            self.assertEqual((p['kind'], p['target'], p['params'].get('wrap')), ('agent.stop', tid, True))
            p, out = call(s, 'agent.stop')
            self.assertIsNone(p)
        # ...and with nothing running there is nothing to stop: no card that fails at the press (real-AI check, 2026-10-18)
        p, out = call(s, 'agent.stop', ref=f'TQ-{tid:04d}')
        self.assertIsNone(p)


class OneLineTests(unittest.TestCase):
    """One line (the owner, 2026-09-25: "don't keep decided as fallback - the assistant should only be AI"): the model
    ends with a CALL, a decision is a tool like any other, and a DECIDE line is read as nothing at all."""
    def test_a_decide_line_is_never_read_whatever_it_names(self):
        for line in ('DECIDE: next', 'DECIDE: task.update: priority urgent', 'DECIDE: not_ours ON: payroll portal outage'):
            self.assertIsNone(concierge.parse_decision('Ok.' + chr(10) + line)[1], line)
            self.assertIsNone(concierge.parse_call('Ok.' + chr(10) + line)[1], line)

    def test_a_decision_and_an_operation_are_the_same_line(self):
        d = concierge.parse_decision('Ok.' + chr(10) + 'CALL: ' + json.dumps({'kind': 'coding_agent', 'params': {'text': 'fix it', 'as': 'northwind/ledger'}}))[1]
        self.assertEqual(d, {'verb': 'coding_agent', 'text': 'fix it', 'as': 'northwind/ledger'})
        c = concierge.parse_call('Ok.' + chr(10) + 'CALL: ' + json.dumps({'kind': 'task.update', 'params': {'priority': 'urgent'}}))[1]
        self.assertEqual(c, {'kind': 'task.update', 'params': {'priority': 'urgent'}})

    def test_every_tool_is_in_a_bucket_and_described_on_demand(self):
        every = set(toolcatalog.PURPOSE) | set(toolcatalog.DECISIONS)
        bucketed = {k for _, _, ks in toolcatalog.BUCKETS for k in ks}
        self.assertEqual(every - bucketed, set())
        for k in every | set(toolcatalog.READS):
            self.assertNotIn('There is no tool', toolcatalog.describe(k), k)
        # 7400 until "anything you can do, via the Assistant" (app.find, the set and to-do tools - the owner, 2026-10-20)
        # ...7650 since the org chart's people.relate (2026-10-22): its parameters are in its description, not the index
        # ...7800 since the app's own trouble is looked into in the chat (app.health on WHERE, app.repair in the app bucket, 2026-10-24)
        # ...7850 since a meeting can be Prepared from the chat (prepare in the time bucket, 2026-10-25)
        # ...7950 since the chat corrects the memory as well (memory.remember's about / replaces, memory.wrong, memory.about - 2026-10-25)
        self.assertLess(len(toolcatalog.block()), 7950, 'the index rides every turn - keep it an index')
        # ...and it names every look-up, so a question finds its tool without guessing a bucket (the 2026-10-20 query walk)
        for k in toolcatalog.READS: self.assertIn(k, toolcatalog.block(), k)   # 7000 until the four calendar tools (2026-10-20)


class DocsPageTests(unittest.TestCase):
    def test_the_docs_page_is_the_catalogue_as_it_stands(self):
        """docs/site/assistant-tools.md is written from toolcatalog (`python -m taskuary.toolcatalog`) - a tool added,
        renamed or reworded without rewriting it fails here, so the docs never describe tools that are not there."""
        from pathlib import Path
        page = (Path(toolcatalog.__file__).resolve().parent.parent / toolcatalog.DOCS_PAGE).read_text(encoding='utf-8')
        self.assertEqual(page.replace('\r\n', '\n'), toolcatalog.docs_markdown(), 'run: python -m taskuary.toolcatalog')
