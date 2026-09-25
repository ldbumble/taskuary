"""A number (or a poll tap) on the phone is the desktop's button: it runs in code, never through the model.

The owner, 2026-09-25: "It should match the same exact we just updated to assistant. Only difference is the
formatting should look good on WhatsApp for reports, buttons to click." A pick used to go to the interpreter
as words; the card's own question (how far a Not ours goes, which agent) never reached the phone; a list three
turns old still answered "2"; a bare "yes" in the Assistant chat approved whichever review pinged last.
"""
import json, unittest
from unittest import mock

from taskuary import concierge, funnel, messengers, phone, remote_assistant as ra
from taskuary.store import MemoryStore

JID = '15550001234@s.whatsapp.net'


def armed():
    s = MemoryStore()
    for k in ('calendar_enabled', 'coder_auto_enabled', 'learn_enabled'): s.set_setting(k, '0', 't')
    funnel.invalidate(); funnel.forget_states(); funnel._CACHE.update(cands_at=0.0, cands=[])
    cid = s.get_connector_by_type('whatsapp')['ConnectorId']
    s.save_connector({'ConnectorId': cid, 'Active': 1, 'Roles': 'trigger,tool', 'Secret': 'tok',
                      'ConfigJson': json.dumps({'assistant_chat': JID})}, 'test')
    s.set_setting('phone_assistant', '1', 'test')
    return s, cid


def sent_to(s, text, fn='send'):
    """Everything the phone said back to one line from the owner."""
    got = []
    with mock.patch.object(messengers, 'wa_send', side_effect=lambda st, chat, body, connector_id=None, poll=None: got.append((body, poll))), \
         mock.patch('taskuary.general.dock_task', return_value=({'TaskId': 1}, False)), \
         mock.patch.object(concierge, 'restore_current', return_value=None), \
         mock.patch.object(concierge, 'say', side_effect=AssertionError('a pick never reaches the model')):
        ra.respond(s, 'whatsapp', JID, text, None)
    return got


def offer(s, out):
    """Send one turn the way the walk does, so its numbers (and their acts) are what the chat holds."""
    got = []
    with mock.patch.object(messengers, 'wa_send', side_effect=lambda st, chat, body, connector_id=None, poll=None: got.append((body, poll))):
        ra.send(s, 'whatsapp', JID, ra.turn_text(out, store=s), None)
    return got


ITEM = {'key': 'msg:7', 'kind': 'fyi', 'mid': 7, 'title': 'The export job failed again'}
CHIPS = [{'verb': 'mine', 'label': 'Make a task'}, {'verb': 'regular_agent', 'label': 'Send to agent'},
         {'verb': 'not_ours', 'label': 'Not ours'}, {'verb': 'next', 'label': 'Next'}]


class PickIsTheButtonTests(unittest.TestCase):
    def test_a_numbered_chip_runs_the_desktop_road_without_the_model(self):
        s, _ = armed()
        offer(s, {'say': 'The export job failed again.', 'item': ITEM, 'chips': CHIPS})
        prop = {'id': 'op9', 'status': 'proposed', 'label': 'Put it on my list', 'summary': 'msg → put it on my list',
                'key': 'msg:7', 'settles': True, 'alts': []}
        with mock.patch.object(concierge, 'propose_direct', return_value=prop) as pd, \
             mock.patch.object(concierge, 'run_proposal', return_value={**prop, 'status': 'done'}) as run, \
             mock.patch.object(concierge, 'receipt', return_value='Done - Put it on my list.'), \
             mock.patch.object(concierge, 'surface', return_value={'say': 'All clear.', 'item': None}), \
             mock.patch.object(funnel, 'next_item', return_value=ITEM):
            got = sent_to(s, '1')
        pd.assert_called_once_with(s, 'mine', 'msg:7', actor='owner', table=False)
        run.assert_called_once()
        self.assertIn('Done - Put it on my list.', got[0][0])

    def test_not_ours_asks_how_far_and_each_answer_runs(self):
        s, _ = armed()
        offer(s, {'say': 'x', 'item': ITEM, 'chips': CHIPS})
        alts = [{'verb': 'not_ours', 'label': 'Just this once', 'current': True},
                {'verb': 'not_ours_sender', 'label': 'From now on - triage learns this sender', 'current': False},
                {'verb': 'block_sender', 'label': 'A rule in Settings - it never reaches triage', 'current': False}]
        prop = {'id': 'op1', 'status': 'proposed', 'verb': 'not_ours', 'label': 'File it', 'summary': 'The export job → file it',
                'key': 'msg:7', 'settles': True, 'alts': alts}
        with mock.patch.object(concierge, 'propose_direct', return_value=prop), \
             mock.patch.object(concierge, 'run_proposal') as run, \
             mock.patch.object(funnel, 'next_item', return_value=ITEM):
            got = sent_to(s, '4')                                    # "Not ours" after the lead word, Next and the rest
        run.assert_not_called()                                      # a question is open: nothing runs yet
        body, poll = got[0]
        self.assertIn('How far?', body)
        self.assertEqual(poll, ['Just this once', 'From now on - triage learns this sender',
                                'A rule in Settings - it never reaches triage', 'Cancel'])
        # the owner taps "From now on" in the poll: a new proposal from the same road, run at once
        second = {**prop, 'id': 'op2', 'verb': 'not_ours_sender', 'label': 'Ignore this sender from now on'}
        with mock.patch.object(concierge, 'propose_direct', return_value=second) as pd, \
             mock.patch.object(concierge, 'run_proposal', return_value={**second, 'status': 'done'}) as run, \
             mock.patch.object(concierge, 'receipt', return_value='Done - Ignore this sender from now on.'), \
             mock.patch.object(concierge, 'surface', return_value={'say': 'All clear.', 'item': None}), \
             mock.patch.object(funnel, 'next_item', return_value=ITEM):
            got = sent_to(s, 'From now on - triage learns this sender')
        self.assertEqual(pd.call_args.args[1:3], ('not_ours_sender', 'msg:7'))
        self.assertTrue(pd.call_args.kwargs['exact'])
        run.assert_called_once()
        self.assertIn('Done - Ignore this sender from now on.', got[0][0])

    def test_the_current_answer_is_the_confirm_and_cancel_moves_nothing(self):
        s, _ = armed()
        q, rows = ra.proposal_choices({'id': 'op1', 'verb': 'regular_agent', 'key': 'msg:7', 'settles': True,
                                       'alts': [{'verb': 'coder', 'label': 'A coding agent', 'current': True},
                                                {'verb': 'regular_agent', 'label': 'A non-coding agent', 'current': False}]})
        self.assertEqual(q, 'Which agent?')
        self.assertEqual([(l, a['t']) for l, a in rows], [('A coding agent', 'confirm'), ('A non-coding agent', 'alt'), ('Cancel', 'cancel')])
        with mock.patch('taskuary.operations.get', return_value={'id': 'op1', 'status': 'proposed'}), \
             mock.patch('taskuary.operations.cancel') as cancel:
            self.assertEqual(ra.run_act(s, rows[-1][1], None), 'Left it - nothing moved.')
        cancel.assert_called_once()

    def test_a_checkout_nobody_named_is_asked_for_before_it_starts(self):
        prop = {'id': 'op3', 'kind': 'task.create_from_text', 'params': {'kind': 'coding', 'repo': 'northwind/ledger'},
                'clear': False, 'repo_choices': ['northwind/portal', 'northwind/ledger'], 'key': None}
        self.assertTrue(ra.asks(prop))
        q, rows = ra.proposal_choices(prop)
        self.assertEqual(q, 'Which repository should the coding agent use?')
        self.assertEqual([l for l, _ in rows], ['northwind/ledger (best guess)', 'northwind/portal', 'Cancel'])
        self.assertEqual(rows[1][1], {'t': 'repo', 'id': 'op3', 'key': None, 'settles': False, 'repo': 'northwind/portal'})


class StaleListTests(unittest.TestCase):
    def test_a_list_answers_one_reply(self):
        s, _ = armed()
        offer(s, {'say': 'x', 'item': ITEM, 'chips': CHIPS})
        with mock.patch.object(concierge, 'surface', return_value={'say': 'All clear.', 'item': None}):
            sent_to(s, '2')                                          # Next: runs, and the list is spent
        self.assertEqual(ra.resolve_index(s, 'whatsapp', JID, '3'), ('3', False))

    def test_typed_next_does_not_reprint_the_days_summary(self):
        s, _ = armed()
        with mock.patch.object(funnel, 'pile', return_value={'items': [{'key': 'a'}]}), \
             mock.patch.object(ra, 'who_wants_what', return_value='TODAY: three people want you.'), \
             mock.patch.object(concierge, 'surface', return_value={'say': 'All clear.', 'item': None}):
            self.assertNotIn('TODAY', ra.script_direct(s, 'next'))
            self.assertIn('TODAY', ra.script_direct(s, 'walk me through my tasks'))


class PollTests(unittest.TestCase):
    def test_the_choices_ride_the_last_bubble_as_a_poll_and_a_vote_is_a_pick(self):
        s, _ = armed()
        got = offer(s, {'say': 'The export job failed again.', 'item': ITEM, 'chips': CHIPS})
        self.assertEqual(got[-1][1], ['Make a task', 'Next', 'Send to agent', 'Not ours'])
        self.assertTrue(all(p is None for _, p in got[:-1]))
        self.assertEqual(ra.resolve_index(s, 'whatsapp', JID, 'Send to agent'), ('Send to agent', True))
        self.assertEqual(ra.resolve_index(s, 'whatsapp', JID, 'send to agent'), ('send to agent', False), 'typed words stay words')

    def test_a_single_choice_is_no_poll(self):
        s, _ = armed()
        got = offer(s, {'say': 'x', 'item': ITEM, 'chips': [{'verb': 'mine', 'label': 'Make a task'}]})
        self.assertIsNone(got[-1][1])

    def test_the_bridge_is_sent_the_poll(self):
        s, cid = armed()
        with mock.patch.object(messengers, '_wa') as wa:
            messengers.wa_send(s, JID, 'hello', connector_id=cid, poll=['A', 'B'])
        self.assertEqual(wa.call_args.args[2], {'jid': JID, 'text': 'hello', 'poll': {'name': 'Pick one', 'values': ['A', 'B']}})


class UndoTests(unittest.TestCase):
    def test_a_receipt_with_an_undo_offers_it_as_a_choice(self):
        s, _ = armed()
        prop = {'id': 'op5', 'status': 'proposed', 'settles': False, 'key': 'msg:7', 'alts': []}
        with mock.patch.object(concierge, 'receipt', return_value='Done - Remind me. Undo: clear the reminder.'):
            text = ra._ran(s, prop, {**prop, 'status': 'done'}, ITEM, 'owner')
        self.assertIn('1 · Undo', text)
        with mock.patch.object(concierge, 'undo_last', return_value='Done - put back.') as undo:
            self.assertEqual(ra.run_act(s, {'t': 'undo'}, None), 'Done - put back.')
        undo.assert_called_once()


class ApprovalsYieldTests(unittest.TestCase):
    def test_a_bare_yes_in_the_assistant_chat_is_the_assistants(self):
        s, _ = armed()
        s.set_setting('phone_approvals', '1', 'test')
        with mock.patch.object(phone, 'notify_chats_of', return_value=[JID]), \
             mock.patch.object(phone, '_find_review', side_effect=AssertionError('no review is looked up')):
            self.assertFalse(phone.intercept(s, 'whatsapp', JID, 'yes'))


if __name__ == '__main__': unittest.main()
