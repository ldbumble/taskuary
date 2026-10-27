"""The assistant interprets, proposes, and acts only on a confirmed proposal (PW-121 to PW-128).

A phrase table (decide_words) read the owner's sentence and the page carried the verb out on the
spot; "not ours" about the wrong card deleted a finished task. Now the model interprets the words with
the item, the conversation and the pile in front of it, and a consequential decision becomes a
PROPOSAL - one row in operations, with a label, the exact target and parameters - that nothing
executes until the owner clicks its button. The button submits the structured proposal by id and
version, once; a correction before the click revises the same proposal; stale context, a cancel and a
failed handler all leave the item where it was. Two exceptions the owner approved: Next moves the walk
without marking, closing or deferring anything, and a reply request drafts at once and sends nothing.
"""
import json, unittest
from datetime import datetime, timedelta
from unittest import mock

from fastapi.testclient import TestClient

from taskuary import buttons, concierge, funnel, ingest, operations, server, terminal
from taskuary.store import MemoryStore


def ago(hours=0): return (datetime.now() - timedelta(hours=hours)).strftime('%Y-%m-%d %H:%M:%S')


def store():
    s = MemoryStore()
    s.upsert_agent('coding', 'coding', 'cli', '{}')
    for k in ('calendar_enabled', 'learn_enabled', 'auto_draft_enabled'): s.set_setting(k, '0', 't')
    s.set_setting('coding_auto_enabled', '1', 't'); s.set_setting('team_domains', 'ours.com', 't'); s.set_setting('owner_email', 'owner@ours.com', 't')
    funnel.invalidate(); funnel.forget_states(); funnel._SOURCES.update(at=0.0, by={})
    return s


def brain(intent='task', kind='coding'):
    def llm(system, user, **kw):
        out = {'intent': intent, 'why': 'because'}
        if intent == 'task' and kind: out['kind'] = kind
        return json.dumps(out)
    return llm


def arrive(s, subject='Can you fix the export?', body='The nightly export drops inter-company rows.', who='Craig', email='craig@vendor.com',
           conv=None, hours=1, llm=None, channel='email'):
    msg = {'external_id': f'x:{subject}:{hours}', 'channel': channel, 'conversation_id': conv or f'c:{subject}', 'subject': subject, 'from_name': who,
           'from_email': email, 'sent_at': ago(hours), 'body': body, 'to': ['owner@ours.com'], 'source_name': 'owner@ours.com'}
    with mock.patch.object(ingest, '_spawn'):
        return ingest.ingest_message(s, msg, llm=llm or brain())


def pile(s):
    with mock.patch.object(terminal, 'live_sessions', return_value=[]):
        return funnel.build(s, keep_surfaced=True)['items']


def asked(s=None):
    s = s or store(); out = arrive(s)
    return s, out['task_id'], out['message_id'], pile(s)[0]


# THE PHONE'S ROAD (the owner, 2026-10-19): on the desk a typed act lights its button and nothing is proposed (test_assistant_router);
# a phone chat has no buttons, so its words still become the proposal it answers yes or no - the semantics held here
def say(s, text, key=None, model='never asked'):
    with mock.patch.object(terminal, 'live_sessions', return_value=[]), concierge.delivering(concierge.PHONE):
        return concierge.say(s, text, key=key, llm=lambda *a, **k: model)


def run(s, p, version=None):
    with mock.patch.object(server, 'store', s), mock.patch.object(terminal, 'live_sessions', return_value=[]):
        return TestClient(server.app).post(f"/api/operations/{p['id']}/execute", json={'version': version if version is not None else p['version']})


class ProposalTests(unittest.TestCase):
    def test_a_decision_is_a_proposal_the_owner_confirms_not_an_action_the_words_took(self):
        s, tid, mid, item = asked()
        with mock.patch.object(ingest, '_spawn') as spawn:
            out = say(s, 'send it to the coding agent', key=item['key'], model='On it.\nCALL: {"kind": "coding_agent", "params": {}}')
        self.assertIsNone(out['decision']); p = out['proposal']
        self.assertEqual((p['kind'], p['target'], p['params']['kind'], p['status']), ('task.create_from_message', mid, 'coding', 'proposed'))
        self.assertEqual(p['label'], buttons.label('coding_agent')); self.assertIn(f'TQ-{tid:04d}', p['summary'])
        spawn.assert_not_called()                                                   # nothing ran on the words
        self.assertEqual(s.get_task(tid)['Status'], 'open')
        self.assertIn('nothing happens until you say yes', out['say'].lower())
        self.assertFalse(hasattr(concierge, 'decide_words'))                        # the phrase table is gone

    def test_confirming_runs_it_once_and_a_second_click_is_the_same_receipt(self):
        s, tid, mid, item = asked()
        out = say(s, 'send it to the coding agent', key=item['key'], model='On it.\nCALL: {"kind": "coding_agent", "params": {}}')
        with mock.patch.object(server, 'dispatch_message', return_value={'taskId': tid, 'ref': f'TQ-{tid:04d}', 'dispatch': 'started'}) as dispatch:
            r1 = run(s, out['proposal']); r2 = run(s, out['proposal'])
        self.assertEqual((r1.status_code, r1.json()['status']), (200, 'done'))
        self.assertEqual((r2.status_code, r2.json()['status'], r2.json()['duplicate']), (200, 'done', True))
        self.assertEqual(dispatch.call_count, 1)                                     # the shared handler, once
        from taskuary import general
        dock, _ = general.dock_task(s, 'owner')
        self.assertTrue(any(f"Done - {buttons.label('coding_agent')}" in (r.get('Body') or '') for r in general.chat_rows(s, dock['TaskId'])))

    def test_a_proposal_whose_context_moved_is_refused_at_the_click(self):
        s, tid, mid, item = asked()
        out = say(s, 'file it', key=item['key'], model='Filing it.\nCALL: {"kind": "not_ours", "params": {}}')
        arrive(s, subject='Can you fix the export?', body='Never mind - found it.', conv='c:Can you fix the export?', hours=0)
        r = run(s, out['proposal'])
        self.assertEqual(r.status_code, 409); self.assertIn('context', r.json()['detail'])
        self.assertEqual(s.get_task(tid)['Status'], 'open')

    def test_a_correction_before_the_click_revises_the_same_proposal(self):
        s, tid, mid, item = asked()
        first = say(s, 'send it to the coding agent', key=item['key'], model='On it.\nCALL: {"kind": "coding_agent", "params": {}}')['proposal']
        second = say(s, 'no - a regular agent, it is just reading', key=item['key'], model='A regular agent then.\nCALL: {"kind": "regular_agent", "params": {}}')['proposal']
        self.assertEqual((second['id'], second['version'], second['params']['kind']), (first['id'], 2, 'general'))
        self.assertEqual(second['label'], 'Send to agent')
        self.assertEqual(run(s, first).status_code, 409)                             # the old confirmation is stale
        self.assertEqual(operations.get(s, first['id'])['status'], 'proposed')

    def test_cancel_changes_nothing(self):
        s, tid, mid, item = asked()
        p = say(s, 'close it', key=item['key'], model='Closing.\nCALL: {"kind": "close", "params": {}}')['proposal']
        with mock.patch.object(server, 'store', s):
            self.assertEqual(TestClient(server.app).delete(f"/api/operations/{p['id']}").json()['status'], 'cancelled')
        self.assertEqual(run(s, p).status_code, 409); self.assertEqual(s.get_task(tid)['Status'], 'open')

    def test_a_press_on_a_cancelled_proposal_answers_with_its_line_and_way_on(self):
        """The 409 carried only its reason, so the page wrote a second receipt of its own - "Say it again", Next under it - beside the
        line the server had recorded (re-audit, 2026-10-18). It carries that line, its buttons and the proposal as it stands."""
        s, tid, mid, item = asked()
        p = say(s, 'close it', key=item['key'], model='Closing.\nCALL: {"kind": "close", "params": {}}')['proposal']
        operations.cancel(s, p['id'])
        r = run(s, p)
        b = r.json()
        self.assertEqual((r.status_code, b['status'], b['op']['status']), (409, 'cancelled', 'cancelled'))
        self.assertTrue(b['detail'] and isinstance(b['detail'], str))                # every reader of `detail` still reads a sentence
        self.assertTrue(b['receipt'].startswith('Not done'))
        self.assertIsInstance(b['chips'], list)

    def test_a_stale_press_answers_with_the_moved_proposal(self):
        s, tid, mid, item = asked()
        first = say(s, 'send it to the coding agent', key=item['key'], model='On it.\nCALL: {"kind": "coding_agent", "params": {}}')['proposal']
        say(s, 'no - a regular agent', key=item['key'], model='A regular agent then.\nCALL: {"kind": "regular_agent", "params": {}}')
        b = run(s, first).json()
        self.assertEqual((b['status'], b['op']['version']), ('stale', 2))

    def test_a_failed_handler_is_reported_and_settles_nothing(self):
        s, tid, mid, item = asked()
        p = say(s, 'send it to the coding agent', key=item['key'], model='On it.\nCALL: {"kind": "coding_agent", "params": {}}')['proposal']
        with mock.patch.object(server, 'dispatch_message', side_effect=RuntimeError('agent did not start')):
            r = run(s, p)
        self.assertEqual((r.status_code, r.json()['status']), (200, 'error')); self.assertIn('agent did not start', r.json()['error'])
        self.assertEqual([i['key'] for i in pile(s)], [item['key']])                # still on the table


class InterpretationTests(unittest.TestCase):
    def test_words_alone_decide_nothing_the_model_does(self):
        s, tid, mid, item = asked()
        out = say(s, "not ours, let them sort it out", key=item['key'], model='I can file it if you want - say so and I will.')
        self.assertIsNone(out.get('proposal')); self.assertIsNone(out['decision'])
        self.assertEqual(s.get_task(tid)['Status'], 'open')
        with mock.patch.object(concierge, 'brain', return_value=None):
            with mock.patch.object(terminal, 'live_sessions', return_value=[]):
                out = concierge.say(s, 'file it', key=item['key'])
        self.assertIsNone(out.get('proposal')); self.assertIn('AI', out['say'])       # no model, no decision - said plainly

    def test_a_clarifying_question_proposes_nothing(self):
        s, tid, mid, item = asked()
        # every hand-off is Send to agent (COUNSEL, 2026-10-17): the question that is left is yours or an agent's
        out = say(s, 'deal with this', key=item['key'], model='Should I put it on your list, or hand it off?\nOPTIONS: Put it on my list | Send to agent')
        self.assertIsNone(out.get('proposal')); self.assertEqual(out['options'], ['Put it on my list', 'Send to agent'])

    def test_a_decision_that_names_another_item_targets_that_one_and_an_unknown_name_asks(self):
        s, tid, mid, item = asked()
        other = arrive(s, subject='Payroll portal is down', body='Nobody can clock in.', who='Elena', email='elena@ours.com', conv='c:outage', hours=0,
                       llm=brain('task', 'general'))
        mine = next(i for i in pile(s) if i.get('mid') == mid)
        # the model names that row by its HANDLE off the rail (2026-10-08) - words in `on` are handed back, never guessed
        out = say(s, 'not ours, the payroll portal outage is facilities', key=mine['key'],
                  model='Filing that one.\nCALL: {"kind": "not_ours", "params": {"on": "TQ-%04d"}}' % other['task_id'])
        self.assertEqual(out['proposal']['target'], other['message_id']); self.assertIn('not the one on the table', out['say'])
        out = say(s, 'not ours, the badge printer contract is legal', key=mine['key'], model='Filing that one.\nCALL: {"kind": "not_ours", "params": {"on": "badge printer contract"}}')
        self.assertIsNone(out.get('proposal')); self.assertIn('nothing has been touched', out['say'].lower())

    def test_a_decision_that_names_one_fyi_targets_that_entry_not_the_handful(self):
        s = store()
        a = arrive(s, subject='FYI - Rebecca is back Tuesday', body='Just so you know.', who='Erin', email='erin@ours.com', conv='c:a', hours=2, llm=brain('fyi', None))
        b = arrive(s, subject='FYI - lunch moved', body='Thursday now.', who='Erin', email='erin@ours.com', conv='c:b', hours=1, llm=brain('fyi', None))
        with mock.patch.object(terminal, 'live_sessions', return_value=[]):
            batch = concierge.surface(s, llm=None)['item']
        self.assertEqual((batch['kind'], len(batch['items'])), ('fyis', 2))
        out = say(s, 'not ours, the Rebecca one', key=batch['key'],
                  model='Filing that one.\nCALL: {"kind": "not_ours", "params": {"on": "m%d"}}' % a['message_id'])      # its handle
        p = out['proposal']
        self.assertEqual((p['kind'], p['target'], p['settles']), ('message.file', a['message_id'], False))
        self.assertEqual(run(s, p).json()['status'], 'done')
        self.assertEqual(s.get_message(a['message_id'])['Status'], 'ignored')
        self.assertEqual(s.get_message(b['message_id'])['Status'], 'filed')            # the sibling is untouched...
        self.assertTrue(any(i.get('mid') == b['message_id'] for i in pile(s)))         # ...and still unread

    def test_next_moves_on_without_marking_closing_or_deferring(self):
        s, tid, mid, item = asked()
        out = say(s, 'next', key=item['key'], model='Next.\nCALL: {"kind": "next", "params": {}}')
        self.assertEqual(out['decision'], {'verb': 'next'}); self.assertIsNone(out.get('proposal'))
        self.assertNotIn(item['key'], {k for k, st in s.funnel_states().items() if st.get('Status') in ('done', 'later', 'skip')})
        self.assertEqual(s.get_task(tid)['Status'], 'open')
        out = say(s, 'is the agent done?', key=item['key'], model='Not yet - it is still reading the export code.')
        self.assertIsNone(out['decision']); self.assertIsNone(out.get('proposal'))     # a question is a question

    def test_a_reply_request_drafts_at_once_and_sends_nothing(self):
        s, tid, mid, item = asked()
        with mock.patch('taskuary.outbound.reply_to_message') as send:
            out = say(s, 'reply and tell them the export is fixed', key=item['key'], model="I'll draft that.\nCALL: {\"kind\": \"reply\", \"params\": {\"text\": \"tell them the export is fixed\"}}")
        self.assertEqual(out['decision'], {'verb': 'reply', 'text': 'tell them the export is fixed'}); self.assertIsNone(out.get('proposal'))
        send.assert_not_called()


class ExecutionTests(unittest.TestCase):
    def test_done_is_confirmed_then_settles_the_item_and_closes_its_task(self):
        s, tid, mid, item = asked()
        # Handled is gone (buttons.json `removed`): a model still saying "done" lands on Mark done
        p = say(s, 'done, I handled it', key=item['key'], model='Done.\nCALL: {"kind": "done", "params": {}}')['proposal']
        self.assertEqual((p['kind'], p['target'], p['label']), ('task.complete', tid, buttons.label('close')))
        self.assertEqual([i['key'] for i in pile(s)], [item['key']])                # nothing moved yet
        self.assertEqual(run(s, p).json()['status'], 'done')
        self.assertEqual(pile(s), []); self.assertEqual(s.get_task(tid)['Status'], 'done')

    def test_approve_is_confirmed_then_sent(self):
        s = store(); out = arrive(s, subject='Where is the June invoice?', body='Can you send it?', llm=brain('reply_only', None))
        rv = s.pending_review(out['task_id']); s.save_review_draft(rv['ReviewId'], 'Attached - sorry for the wait.')
        item = pile(s)[0]
        p = say(s, 'approve', key=item['key'], model='Sending it.\nCALL: {"kind": "approve", "params": {}}')['proposal']
        self.assertEqual((p['kind'], p['target'], p['label']), ('review.approve', rv['ReviewId'], 'Send'))
        self.assertEqual(s.get_review(rv['ReviewId'])['Status'], 'pending')
        with mock.patch('taskuary.outbound.reply_to_message', return_value={'channel': 'email', 'to': ['craig@vendor.com'], 'cc': []}):
            self.assertEqual(run(s, p).json()['status'], 'done')
        self.assertIn(s.get_review(rv['ReviewId'])['Status'], ('approved', 'edited')); self.assertEqual(s.get_task(out['task_id'])['Status'], 'open')   # sent, not closed

    def test_remember_and_close_are_proposals_that_do_what_they_say(self):
        s, tid, mid, item = asked()
        p = say(s, 'remember that Gail signs off on refunds', key=item['key'], model='Noted.\nCALL: {"kind": "remember", "params": {"text": "Gail signs off on refunds"}}')['proposal']
        self.assertEqual((p['kind'], p['params']['note'], p['settles']), ('memory.remember', 'Gail signs off on refunds', False))
        self.assertNotIn('Gail signs off on refunds', s.get_doc('learned') or '')                 # a proposal: nothing kept yet
        run(s, p); self.assertIn('- Gail signs off on refunds', s.get_doc('learned') or '')     # LEARNED.md, every reader's memory (2026-10-27)
        p = say(s, 'close it', key=item['key'], model='Closing.\nCALL: {"kind": "close", "params": {}}')['proposal']
        self.assertEqual((p['kind'], p['target']), ('task.complete', tid)); self.assertEqual(s.get_task(tid)['Status'], 'open')
        run(s, p); self.assertEqual(s.get_task(tid)['Status'], 'done')

    def test_a_hand_off_with_nothing_on_the_table_proposes_a_new_task(self):
        s = store()
        out = say(s, 'look into why the bulk approve fix did not stick', model='On it.\nCALL: {"kind": "coding_agent", "params": {"text": "look into why the bulk approve fix did not stick"}}')
        p = out['proposal']
        self.assertEqual((p['kind'], p['params']['kind']), ('task.create_from_text', 'coding')); self.assertIn('bulk approve', p['params']['text'])
        self.assertEqual(s.list_tasks(active_only=True), [])
        with mock.patch.object(ingest, '_spawn') as spawn:
            r = run(s, p)
        t = s.get_task(r.json()['outcome']['taskId'])
        self.assertEqual(t['Kind'], 'coding'); self.assertTrue(spawn.called); self.assertIn('did not stick', t['Summary'])

    def test_the_receipt_after_the_click_is_the_fact_and_the_items_card_wears_it(self):
        s, tid, mid, item = asked()
        p = say(s, 'close it', key=item['key'], model='Closing.\nCALL: {"kind": "close", "params": {}}')['proposal']
        from taskuary import general
        dock, _ = general.dock_task(s, 'owner')
        bodies = lambda: [r.get('Body') or '' for r in general.chat_rows(s, dock['TaskId'])]
        bare = run(s, p).json()                           # no card of the item in this chat: its line is said
        self.assertTrue(any('Done -' in b and f'TQ-{tid:04d}' in b for b in bodies()), bodies()[-3:])
        self.assertTrue(bare['receipt'].startswith('Done -') and f'TQ-{tid:04d}' in bare['receipt'])
        # ...and with the item's card drawn, the press is its badge and no line (the owner, 2026-10-22: "we don't need that text ever")
        other = s.create_task({'Title': 'Order the badge printer ribbon', 'Status': 'open'}, 'owner')
        concierge.record(s, dock['TaskId'], 'assistant', 'Next up.', {'kind': 'task', 'key': f'task:{other}', 'tid': other, 'title': 'Order the badge printer ribbon'})
        p = say(s, 'close it', key=f'task:{other}', model='Closing.\nCALL: {"kind": "close", "params": {}}')['proposal']
        n = len(bodies())
        self.assertEqual(run(s, p).json()['status'], 'done')
        self.assertEqual(len(bodies()), n)
        self.assertTrue(any('"pressed": "Mark done"' in b and f'task:{other}' in b for b in bodies()))


    def test_a_press_on_the_tables_own_row_marks_its_card_and_one_elsewhere_does_not(self):
        """Mark done on the card on the table closed it with nothing in the chat to show for it (the walk click-through, 2026-10-17),
        and then with a "Done - Mark done · TQ-0001." line under it (the owner, 2026-10-22: "we don't need that text ever"): the item's
        own card wears the button's label. A close from anywhere else still touches nothing here."""
        from taskuary import general
        s, tid, mid, item = asked()
        dock, _ = general.dock_task(s, 'owner')
        bodies = lambda: [r.get('Body') or '' for r in general.chat_rows(s, dock['TaskId'])]
        concierge.set_current(s, dock['TaskId'], item['key'])
        concierge.record(s, dock['TaskId'], 'assistant', 'Next up.', {'kind': 'asked', 'key': item['key'], 'tid': tid, 'title': 'Can you fix the export?'})
        n = len(bodies())
        run(s, operations.propose(s, 'task.complete', tid, {}, 'owner'))
        self.assertEqual(len(bodies()), n)
        self.assertIn('"pressed": "Mark done"', bodies()[-1])
        other = s.create_task({'Title': 'Order the badge printer ribbon', 'Status': 'open'}, 'owner')
        before = len(bodies())
        run(s, operations.propose(s, 'task.complete', other, {}, 'owner'))
        self.assertEqual(len(bodies()), before)


    def test_a_failure_that_names_its_fix_offers_it_as_a_way_on(self):
        """"no mailbox is connected" came with nothing to press: the fix a failure names (outbound.Fixable) is one of the
        choices recover offers - the model picks among them like any other."""
        s, tid, mid, item = asked()
        fix = {'label': 'Connect a mailbox', 'href': '#connections=Email'}
        op = {'id': 'x1', 'version': 1, 'kind': 'task.complete', 'status': 'error', 'error': 'no mailbox is connected to send from',
              'outcome': {'fix': fix}}
        chips = concierge.recover(s, op, llm=False)['chips']
        self.assertIn({'verb': 'go', **fix}, chips)


class HandoffTests(unittest.TestCase):
    """PW-135/136: a confirmed hand-off that starts is acknowledged and moves on once; the delegated task stays in
    Unread as Working, nothing settled; a repository still to choose, a failed start or a cancel keep the item."""

    def _proposed(self):
        s, tid, mid, item = asked()
        p = say(s, 'send it to the coding agent', key=item['key'], model='On it.\nCALL: {"kind": "coding_agent", "params": {}}')['proposal']
        return s, tid, mid, item, p

    def test_a_hand_off_that_starts_is_receipted_moving_on_and_the_task_stays_in_unread_as_working(self):
        s, tid, mid, item, p = self._proposed()
        started = {'dispatch': 'session', 'agent': 'coding', 'model': None, 'started': True, 'existing': False, 'taskId': tid, 'ref': f'TQ-{tid:04d}'}
        with mock.patch.object(server, 'dispatch_message', return_value=started):
            r = run(s, p).json()
        self.assertEqual((r['status'], r['outcome']['started']), ('done', True))
        from taskuary import general
        dock, _ = general.dock_task(s, 'owner')
        self.assertIn("It's being worked on now - moving on", r['receipt'])     # said to the phone; the desk's card wears its badge
        self.assertNotIn(item['key'], {k for k, st in s.funnel_states().items() if st.get('Status') == 'done'})   # nothing settled
        s.update_task(tid, {'Status': 'in_progress'}, 'router')
        live = [{'taskId': tid, 'sid': 's1', 'agent': 'coding', 'label': 'coding', 'started': ago(0), 'idle': 2, 'waiting': False, 'tail': ['reading']}]
        with mock.patch.object(terminal, 'live_sessions', return_value=live):
            rows = funnel.build(s, keep_surfaced=True)['items']
        self.assertEqual([(i['key'], i['lane']) for i in rows if i.get('tid') == tid], [(f'agent:{tid}', 'working')])   # visible, Working

    def test_a_repository_still_to_choose_keeps_the_item_in_place_and_the_same_confirmation_resumes(self):
        s, tid, mid, item, p = self._proposed()
        needs = {'dispatch': 'needs_repo', 'started': False, 'existing': False, 'agent': 'coding', 'taskId': tid, 'ref': f'TQ-{tid:04d}',
                 'reason': 'could not tell which checkout - pick the repository'}
        with mock.patch.object(server, 'dispatch_message', return_value=needs):
            r = run(s, p).json()
        self.assertEqual((r['status'], r['outcome']['dispatch']), ('error', 'needs_repo')); self.assertIn('repository', r['error'])
        self.assertEqual([i['key'] for i in pile(s)], [item['key']]); self.assertEqual(s.get_task(tid)['Status'], 'open')   # in place
        self.assertEqual(operations.get(s, p['id'])['status'], 'error')
        started = {**needs, 'dispatch': 'session', 'started': True, 'reason': None}
        with mock.patch.object(server, 'dispatch_message', return_value=started) as dispatch:
            r2 = run(s, p).json(); r3 = run(s, p).json()
        self.assertEqual((r2['status'], r2['duplicate'], r3['duplicate']), ('done', False, True)); self.assertEqual(dispatch.call_count, 1)   # advances once

    def test_a_failed_start_and_a_cancel_keep_the_item(self):
        s, tid, mid, item, p = self._proposed()
        with mock.patch.object(server, 'dispatch_message', side_effect=RuntimeError('agent did not start')):
            self.assertEqual(run(s, p).json()['status'], 'error')
        self.assertEqual([i['key'] for i in pile(s)], [item['key']])
        with mock.patch.object(server, 'store', s):
            TestClient(server.app).delete(f"/api/operations/{p['id']}")
        self.assertEqual(run(s, p).status_code, 409); self.assertEqual([i['key'] for i in pile(s)], [item['key']])


class NoCodingToolTests(unittest.TestCase):
    """Coding exists only where a coding tool is connected: COUNSEL offered "Coding agent | Regular agent" to a finance user, who
    picked coding and was refused (2026-10-17 audit)."""
    def test_without_a_coding_tool_the_chat_never_hears_of_coding(self):
        from taskuary import agents, counsel
        s = MemoryStore()
        with mock.patch.object(agents, 'coding_ready', return_value=False): text = counsel.for_chat(s)
        self.assertNotRegex(text.lower(), r'coding|repositor'); self.assertIn('Send to agent', text)
        with mock.patch.object(agents, 'coding_ready', return_value=True): text = counsel.for_chat(s)
        self.assertIn('OPTIONS: ' + ' | '.join(w for _, w in buttons.choices('agent')), text)    # the card's own answers, by name

    def test_an_owners_copy_that_still_talks_coding_gets_the_one_rule(self):
        from taskuary import agents, counsel
        s = MemoryStore(); s.save_doc('counsel', '# Mine\n\n- Code fixes go to the coding agent.\n', 'owner')
        with mock.patch.object(agents, 'coding_ready', return_value=False): text = counsel.for_chat(s)
        self.assertTrue(text.startswith('# Mine') and text.endswith(counsel.NO_CODING))
        s.save_doc('counsel', '# Mine\n\n- Speak plainly.\n', 'owner')
        with mock.patch.object(agents, 'coding_ready', return_value=False): self.assertEqual(counsel.for_chat(s), '# Mine\n\n- Speak plainly.')


if __name__ == '__main__':
    unittest.main()
