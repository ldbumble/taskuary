"""A number (or a poll tap) on the phone is the desktop's button: it runs in code, never through the model.

The owner, 2026-09-25: "It should match the same exact we just updated to assistant. Only difference is the
formatting should look good on WhatsApp for reports, buttons to click." A pick used to go to the interpreter
as words; the card's own question (how far a Not ours goes, which agent) never reached the phone; a list three
turns old still answered "2"; a bare "yes" in the Assistant chat approved whichever review pinged last.
"""
import json, unittest
from unittest import mock

from taskuary import concierge, funnel, messengers, remote_assistant as ra
from taskuary.store import MemoryStore

JID = '15550001234@s.whatsapp.net'


def armed():
    s = MemoryStore()
    for k in ('calendar_enabled', 'coding_auto_enabled'): s.set_setting(k, '0', 't')
    funnel.invalidate(); funnel.forget_states(); funnel._CACHE.update(cands_at=0.0, cands=[])
    cid = s.get_connector_by_type('whatsapp')['ConnectorId']
    s.save_connector({'ConnectorId': cid, 'Active': 1, 'Roles': 'trigger,tool', 'Secret': 'tok',
                      'ConfigJson': json.dumps({'assistant_chat': JID})}, 'test')
    s.set_setting('phone_assistant', '1', 'test')
    ra.owner_spoke(s, 'whatsapp', JID)                 # the owner is talking in the chat: it may answer (in_session)
    return s, cid


def sent_to(s, text, poll=False):
    """Everything the phone said back to one line from the owner."""
    got = []
    with mock.patch.object(messengers, 'wa_send', side_effect=lambda st, chat, body, connector_id=None, poll=None: got.append((body, poll))), \
         mock.patch('taskuary.general.dock_task', return_value=({'TaskId': 1}, False)), \
         mock.patch.object(concierge, 'restore_current', return_value=None), \
         mock.patch.object(concierge, 'say', side_effect=AssertionError('a pick never reaches the model')):
        ra.respond(s, 'whatsapp', JID, text, None, poll=poll)
    return got


def offer(s, out):
    """Send one turn the way the walk does, so its numbers (and their acts) are what the chat holds."""
    got = []
    with mock.patch.object(messengers, 'wa_send', side_effect=lambda st, chat, body, connector_id=None, poll=None: got.append((body, poll))):
        ra.send(s, 'whatsapp', JID, ra.turn_text(out, store=s), None)
    return got


# a mail asking something - not an FYI, whose card leads with Got it and offers no Send to agent (A8, 2026-10-22)
ITEM = {'key': 'msg:7', 'kind': 'message', 'mid': 7, 'title': 'The export job failed again'}
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
                {'verb': 'not_ours_sender', 'label': 'From now on - their mail is filed for you', 'current': False},
                {'verb': 'block_sender', 'label': 'A rule in Settings - their mail never comes in', 'current': False}]
        prop = {'id': 'op1', 'status': 'proposed', 'verb': 'not_ours', 'label': 'File it', 'summary': 'The export job → file it',
                'key': 'msg:7', 'settles': True, 'alts': alts}
        with mock.patch.object(concierge, 'propose_direct', return_value=prop), \
             mock.patch.object(concierge, 'run_proposal') as run, \
             mock.patch.object(funnel, 'next_item', return_value=ITEM):
            got = sent_to(s, '4')                                    # "Not ours" after the lead word, Next and the rest
        run.assert_not_called()                                      # a question is open: nothing runs yet
        body, poll = got[0]
        self.assertIn('How far?', body)
        self.assertEqual(poll, ['Just this once', 'From now on - their mail is filed for you',
                                'A rule in Settings - their mail never comes in', 'Cancel'])
        # the owner taps "From now on" in the poll: a new proposal from the same road, run at once
        second = {**prop, 'id': 'op2', 'verb': 'not_ours_sender', 'label': 'Ignore this sender from now on'}
        with mock.patch.object(concierge, 'propose_direct', return_value=second) as pd, \
             mock.patch.object(concierge, 'run_proposal', return_value={**second, 'status': 'done'}) as run, \
             mock.patch.object(concierge, 'receipt', return_value='Done - Ignore this sender from now on.'), \
             mock.patch.object(concierge, 'surface', return_value={'say': 'All clear.', 'item': None}), \
             mock.patch.object(funnel, 'next_item', return_value=ITEM):
            got = sent_to(s, 'From now on - their mail is filed for you', poll=True)   # the poll tap
        self.assertEqual(pd.call_args.args[1:3], ('not_ours_sender', 'msg:7'))
        self.assertTrue(pd.call_args.kwargs['exact'])
        run.assert_called_once()
        self.assertIn('Done - Ignore this sender from now on.', got[0][0])

    def test_the_current_answer_is_the_confirm_and_cancel_moves_nothing(self):
        s, _ = armed()
        q, rows = ra.proposal_choices({'id': 'op1', 'verb': 'regular_agent', 'key': 'msg:7', 'settles': True,
                                       'alts': [{'verb': 'coding_agent', 'label': 'A coding agent', 'current': True},
                                                {'verb': 'regular_agent', 'label': 'A non-coding agent', 'current': False}]})
        self.assertEqual(q, 'Which agent?')
        self.assertEqual([(l, a['t']) for l, a in rows], [('A coding agent', 'confirm'), ('A non-coding agent', 'alt'), ('Cancel', 'cancel')])
        with mock.patch('taskuary.operations.get', return_value={'id': 'op1', 'status': 'proposed'}), \
             mock.patch('taskuary.operations.cancel') as cancel:
            self.assertEqual(ra.run_act(s, rows[-1][1], None).splitlines()[0], 'Left it - nothing moved.')    # the way on follows it
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

    def test_the_walk_opens_on_its_pill_and_typed_next_goes_to_the_model(self):
        s, _ = armed()
        with mock.patch.object(funnel, 'pile', return_value={'items': [{'key': 'a'}]}), \
             mock.patch.object(ra, 'who_wants_what', return_value='TODAY: three people want you.'), \
             mock.patch.object(concierge, 'surface', return_value={'say': 'All clear.', 'item': None}):
            self.assertIn('TODAY', ra.run_act(s, {'t': 'walk'}, None))
        said = []
        with mock.patch.object(messengers, 'wa_send', side_effect=lambda *a, **k: said.append(a[2])), \
             mock.patch('taskuary.general.dock_task', return_value=({'TaskId': 1}, False)), \
             mock.patch.object(concierge, 'restore_current', return_value=None), \
             mock.patch.object(concierge, 'say', return_value={'say': 'Next up.', 'item': None}) as model:
            ra.respond(s, 'whatsapp', JID, 'next', None)
        model.assert_called_once()                                    # typed words are the model's, "next" too


class PollTests(unittest.TestCase):
    def test_the_choices_ride_the_last_bubble_as_a_poll_and_a_vote_is_a_pick(self):
        s, _ = armed()
        got = offer(s, {'say': 'The export job failed again.', 'item': ITEM, 'chips': CHIPS})
        self.assertEqual(got[-1][1], ['Make a task', 'Next', 'Send to agent', 'Not ours'])
        self.assertTrue(all(p is None for _, p in got[:-1]))
        self.assertEqual(ra.resolve_index(s, 'whatsapp', JID, 'Send to agent', poll=True), ('Send to agent', True))
        self.assertEqual(ra.resolve_index(s, 'whatsapp', JID, 'Send to agent'), ('Send to agent', False), 'typed, the same words are words')

    def test_a_single_choice_is_still_a_poll(self):
        # the owner, 2026-09-25: "even if only next we should have poll to go next no?"
        s, _ = armed()
        got = offer(s, {'say': 'x', 'item': ITEM, 'chips': [{'verb': 'next', 'label': 'Next'}]})
        # ...and WhatsApp sends no poll of one, so the second option is asking the assistant (2026-10-02)
        self.assertEqual(got[-1][1], ['Next', ra.ASK_SOMETHING])
        self.assertNotIn('Reply with one of', got[-1][0])
        self.assertEqual(ra.acts_for(s, 'whatsapp', JID)[ra.ASK_SOMETHING], {'t': 'prompt'})
        # tapped, it only invites the question - no model, and the lone Next still answers its own tap
        self.assertEqual(sent_to(s, ra.ASK_SOMETHING, poll=True)[-1][0], 'Taskuary:\nGo ahead - type your question.')

    def test_a_finished_agents_card_offers_its_report(self):
        # an agent finished the task behind a report that came again - the card asked "want to see the final report?"
        # and offered only Next
        s, _ = armed()
        t = s.create_task({'Title': 'Why the nightly export times out', 'Kind': 'coding', 'Status': 'done'}, 'coding')
        s.add_comment(t, 'coding', 'agent', 'AGENT REPORT\nThe mass update made the export 6x larger.')
        item = {'key': f'task:{t}', 'kind': 'agentdone', 'tid': t, 'ref': f'TQ-{t:04d}', 'title': 'Why the nightly export times out',
                'lane': 'report', 'channel': 'report'}
        got = offer(s, {'say': 'coding finished it.', 'item': item, 'chips': concierge.chips_for(s, item)})
        self.assertEqual(got[-1][1], ['Mark done', 'Next', 'More'])

    def test_the_bridge_is_sent_the_poll(self):
        s, cid = armed()
        with mock.patch.object(messengers, '_wa') as wa:
            messengers.wa_send(s, JID, 'hello', connector_id=cid, poll=['A', 'B'])
        self.assertEqual(wa.call_args.args[2], {'jid': JID, 'text': 'hello', 'poll': {'name': 'Pick one', 'values': ['A', 'B']}})


class PickJumpsTheQueueTests(unittest.TestCase):
    """2026-09-25: a poll tap got its thumb, then waited a minute behind a typed turn still waiting on the model."""

    def test_a_tap_stops_the_model_turn_in_flight_and_answers_at_once(self):
        import threading, time
        s, cid = armed()
        offer(s, {'say': 'The export job failed again.', 'item': ITEM, 'chips': CHIPS})
        started, sent = threading.Event(), []

        def slow_say(store, text, key=None, actor='owner', cancel=None, **kw):
            started.set()
            for _ in range(200):                                # the model, thinking - until the tap cancels it
                if cancel is not None and cancel.is_set(): raise RuntimeError('cancelled')
                time.sleep(0.01)
            return {'say': 'the late answer', 'item': None}

        with mock.patch.object(messengers, 'react'), \
             mock.patch.object(messengers, 'wa_send', side_effect=lambda st, chat, body, connector_id=None, poll=None: sent.append(body)), \
             mock.patch.object(concierge, 'say', side_effect=slow_say), \
             mock.patch.object(concierge, 'restore_current', return_value=ITEM), \
             mock.patch.object(ra, 'run_act', return_value='Next up: the invoice.') as ran:
            typed = threading.Thread(target=ra._locked_respond, args=(s, 'whatsapp', JID, 'what is this about', cid))
            typed.start(); self.assertTrue(started.wait(2))
            t0 = time.time()
            ra._locked_respond(s, 'whatsapp', JID, 'Next', cid, poll=True)
            took = time.time() - t0
            typed.join(3); self.assertFalse(typed.is_alive())
        self.assertLess(took, 1.5, 'the tap must not wait out the model turn')
        ran.assert_called_once()
        self.assertTrue(any('Next up: the invoice.' in b for b in sent))
        self.assertFalse(any('the late answer' in b or "couldn't answer" in b for b in sent), 'the cancelled turn says nothing')


class NoUndoTests(unittest.TestCase):
    """No Take it back anywhere, the phone's Undo pill with it (the owner, 2026-10-19: "no take it back button. hate that")."""
    def test_a_receipt_offers_no_undo(self):
        s, _ = armed()
        prop = {'id': 'op5', 'status': 'proposed', 'settles': False, 'key': 'msg:7', 'alts': []}
        with mock.patch.object(concierge, 'receipt', return_value='Done - Remind me.'):
            text = ra._ran(s, prop, {**prop, 'status': 'done'}, ITEM, 'owner')
        self.assertNotIn('Undo', text)
        self.assertFalse(hasattr(concierge, 'undo_last'))


if __name__ == '__main__': unittest.main()


class PhoneCardTests(unittest.TestCase):
    """The owner, 2026-09-25, on WhatsApp: "don't need this choices if you have pick ... rather actually show the task and
    then emoji for agent and what it did"."""

    def test_on_whatsapp_the_poll_is_the_choices(self):
        s, _ = armed()
        got = offer(s, {'say': 'The export job failed again.', 'item': ITEM, 'chips': CHIPS})
        self.assertNotIn('Reply with one of', got[-1][0])
        self.assertEqual(got[-1][1], ['Make a task', 'Next', 'Send to agent', 'Not ours'])
        self.assertEqual(ra.resolve_index(s, 'whatsapp', JID, '2'), ('Next', True), 'a typed number still answers')

    def test_an_agents_card_is_the_task_then_what_the_agent_did(self):
        item = {'key': 'agent:9', 'kind': 'agentdone', 'tid': 9, 'ref': 'TQ-0009', 'title': 'Why the nightly export times out',
                'who': 'coding', 'channel': 'report', 'lane': 'report', 'why': 'the agent finished and closed it'}
        text = ra.turn_text({'say': 'coding finished TQ-0009: the export timed out on a mass update.', 'item': item})
        # the task, then the agent and what it found (the card as a story, 2026-09-28)
        # ...and no "🔵 The task · just now" filler where nobody asked (F6)
        self.assertTrue(text.startswith('✅ agent finished · TQ-0009\nWhy the nightly export times out'), text)
        self.assertLess(text.index('Why the nightly export times out'), text.index('the export timed out on a mass update'))
        self.assertNotIn('the agent finished and closed it', text)

    def test_save_and_end_session_is_not_offered_where_there_is_no_session(self):
        paused = {'key': 'agent:7', 'kind': 'agent', 'lane': 'blocked', 'tid': 7, 'paused': True}
        self.assertNotIn('stop_agent', [c['verb'] for c in concierge.chips_for(MemoryStore(), paused)])

    def test_a_finished_agents_more_is_its_report(self):
        s = MemoryStore()
        t = s.create_task({'Title': 'Export timeouts', 'Kind': 'coding', 'Status': 'done'}, 'coding')
        s.add_comment(t, 'coding', 'agent', 'AGENT REPORT\nThe mass update made the export 6x larger.')
        self.assertEqual(ra.more_text(s, {'kind': 'agentdone', 'tid': t}), 'The mass update made the export 6x larger.')


class OwnerRulingsOctoberTwoTests(unittest.TestCase):
    """The owner, 2026-10-02: a hand-back choice when the walk runs out, a poll that answers once, and past twelve choices
    a "More choices" page - never a list cut short."""

    def test_past_twelve_a_page_and_more_choices_and_typed_numbers_still_answer_the_whole_list(self):
        s, _ = armed()
        many = [{'verb': f'v{i}', 'label': f'Choice {i}'} for i in range(1, 16)]
        got = offer(s, {'say': 'x', 'item': ITEM, 'chips': many})
        self.assertEqual(got[-1][1], [f'Choice {i}' for i in range(1, 12)] + [ra.MORE_CHOICES])
        page = sent_to(s, ra.MORE_CHOICES, poll=True)
        self.assertEqual(page[-1][1], [f'Choice {i}' for i in range(12, 16)] + [ra.MORE_CHOICES])
        self.assertEqual(ra.resolve_index(s, 'whatsapp', JID, '14'), ('Choice 14', True))
        # ...and the last page comes round to the first
        self.assertEqual(sent_to(s, ra.MORE_CHOICES, poll=True)[-1][1][0], 'Choice 1')

    def test_a_second_tap_on_a_spent_poll_runs_nothing_and_says_so(self):
        s, _ = armed()
        got = []
        with mock.patch.object(messengers, 'wa_send', side_effect=lambda st, chat, body, connector_id=None, poll=None: got.append(body)):
            ra.stale_tap(s, 'whatsapp', JID, None, spent=True)
        self.assertIn('That list was already used - nothing ran.', got[-1])

    def test_the_walk_running_out_on_the_phone_offers_the_hand_back(self):
        s, _ = armed()
        out = {'item': None, 'say': concierge.ALL_DONE, 'chips': [], 'over': True}
        with mock.patch.object(ra, 'handoff', return_value={'channel': 'whatsapp', 'chat': JID}):
            got = offer(s, out)
        self.assertIn(ra.HAND_BACK, got[-1][1])
        with mock.patch.object(ra, 'end_handoff') as ended:
            sent_to(s, ra.HAND_BACK, poll=True)
        ended.assert_called_once()
        self.assertEqual(ended.call_args[0][2], ra.HANDED_BACK)
        # ...and with no walk on the phone (a chat that always listens) it is not offered
        with mock.patch.object(ra, 'handoff', return_value=None):
            self.assertNotIn(ra.HAND_BACK, offer(s, out)[-1][1] or [])


def wa_patch(got):
    return mock.patch.object(messengers, 'wa_send', side_effect=lambda st, chat, body, connector_id=None, poll=None: got.append((body, poll)))


def tg_patch(got):
    return mock.patch.object(messengers, 'tg_send', side_effect=lambda st, chat, body, connector_id=None, buttons=None: got.append((body, buttons)))


def tg_armed():
    from tests.test_remote_assistant import TG_CHAT, armed_store
    s, _ = armed_store('telegram', TG_CHAT)
    return s, TG_CHAT


NEXT_CARD = {'say': 'Gail Moreno asked about the budget.', 'item': {'key': 'msg:8', 'kind': 'message', 'mid': 8, 'title': 'Budget'},
             'chips': [{'verb': 'mine', 'label': 'Make a task'}, {'verb': 'next', 'label': 'Next'}]}


class NotOursOnTheTableTests(unittest.TestCase):
    """F1: Not ours tapped on the card ON THE TABLE came back as "File it: ..." with nothing numbered and nothing run - the
    proposal acts at once (concierge.AUTO, the owner 2026-10-21: no question before it) and carries its alts, and the phone drew
    the question with no way to answer it. It runs on the tap, as the desktop's button does, and the next card follows."""
    ALTS = [{'verb': 'not_ours', 'label': 'Just this once', 'current': True},
            {'verb': 'not_ours_sender', 'label': 'From now on - their mail is filed for you', 'current': False}]

    def _tap(self, s, patch, channel, chat):
        with patch([]): ra.send(s, channel, chat, ra.turn_text({'say': 'x', 'item': ITEM, 'chips': CHIPS}, store=s), None)
        prop = {'id': 'op1', 'status': 'proposed', 'verb': 'not_ours', 'label': 'Not ours', 'summary': 'The export job → file it',
                'key': 'msg:7', 'settles': True, 'auto': True, 'alts': self.ALTS, 'say': 'Not ours - the export job.'}
        got = []
        with patch(got), \
             mock.patch('taskuary.general.dock_task', return_value=({'TaskId': 1}, False)), \
             mock.patch.object(concierge, 'restore_current', return_value=ITEM), \
             mock.patch.object(concierge, 'say', side_effect=AssertionError('a pick never reaches the model')), \
             mock.patch.object(concierge, 'propose_direct', return_value=prop) as pd, \
             mock.patch.object(concierge, 'run_proposal', return_value={**prop, 'status': 'done'}) as run, \
             mock.patch.object(concierge, 'receipt', return_value='Not ours - filed.'), \
             mock.patch.object(concierge, 'surface', return_value=NEXT_CARD), \
             mock.patch.object(funnel, 'next_item', return_value=ITEM):
            ra.respond(s, channel, chat, 'Not ours', None, poll=True)
        self.assertTrue(pd.call_args.kwargs['table'])
        run.assert_called_once()
        text = '\n'.join(b for b, _ in got)
        self.assertIn('Not ours - filed.', text)
        self.assertIn('Budget', text)                                     # the next card follows
        self.assertIn('Make a task', got[-1][1])

    def test_whatsapp(self): self._tap(armed()[0], wa_patch, 'whatsapp', JID)
    def test_telegram(self):
        s, chat = tg_armed()
        self._tap(s, tg_patch, 'telegram', chat)


class ReceiptBubbleTests(unittest.TestCase):
    """F14: the receipt and the next card were one bubble, and the poll under it held the receipt's picks too - "Open TQ-0005" for
    the task just made, and Next twice."""

    def test_the_receipt_is_its_own_bubble_and_the_poll_is_the_cards(self):
        s, _ = armed()
        table = {'key': 'msg:7', 'kind': 'fyi', 'mid': 7, 'title': 'The export job failed again'}
        prop = {'id': 'op9', 'status': 'proposed', 'label': 'Make a task', 'key': 'msg:7', 'settles': True, 'alts': []}
        done = {**prop, 'status': 'done', 'kind': 'task.create_from_message', 'params': {'kind': 'task'}, 'outcome': {'taskId': 5, 'ref': 'TQ-0005'}}
        got = []
        with mock.patch.object(concierge, 'run_proposal', return_value=done), \
             mock.patch.object(concierge, 'receipt', return_value='TQ-0005 is on your list.'), \
             mock.patch.object(concierge, 'surface', return_value=NEXT_CARD), \
             wa_patch(got):
            ra.send(s, 'whatsapp', JID, ra.carry_out(s, {'say': 'Make a task: the export job.', 'proposal': prop, 'decision': {'verb': 'mine'}},
                                                     table, picked=True), None)
        self.assertGreaterEqual(len(got), 2)
        self.assertIn('TQ-0005 is on your list.', got[0][0]); self.assertIsNone(got[0][1])
        poll = got[-1][1]
        self.assertEqual(len(poll), len(set(poll)), poll)
        self.assertNotIn('Open TQ-0005', poll)
        self.assertEqual(poll, ['Make a task', 'Next'])


class TypedTurnChoicesTests(unittest.TestCase):
    """F2: the choices drawn under a TYPED answer had no item behind them, so tapping Mark done fell through to the model as
    words. They are the table's chips: a tap runs them on the table."""
    TABLE = {'key': 'task:5', 'kind': 'task', 'tid': 5, 'ref': 'TQ-0005', 'title': 'Renew the domain'}
    OWN = [{'verb': 'close', 'label': 'Mark done'}, {'verb': 'next', 'label': 'Next'}]

    def test_mark_done_after_a_typed_turn_closes_the_table_task(self):
        s, _ = armed()
        got = []
        with wa_patch(got), \
             mock.patch('taskuary.general.dock_task', return_value=({'TaskId': 1}, False)), \
             mock.patch.object(concierge, 'restore_current', return_value=self.TABLE), \
             mock.patch.object(concierge, 'chips_for', return_value=self.OWN), \
             mock.patch.object(concierge, 'say', return_value={'say': 'It renews on the 30th.', 'options': [], 'chips': self.OWN, 'decision': None}):
            ra.respond(s, 'whatsapp', JID, 'when does it renew?', None)
        self.assertIn('Mark done', got[-1][1])
        prop = {'id': 'op4', 'status': 'proposed', 'verb': 'close', 'key': 'task:5', 'settles': True, 'auto': True, 'alts': []}
        with wa_patch(got), \
             mock.patch('taskuary.general.dock_task', return_value=({'TaskId': 1}, False)), \
             mock.patch.object(concierge, 'restore_current', return_value=self.TABLE), \
             mock.patch.object(concierge, 'say', side_effect=AssertionError('a pick never reaches the model')), \
             mock.patch.object(concierge, 'propose_direct', return_value=prop) as pd, \
             mock.patch.object(concierge, 'run_proposal', return_value={**prop, 'status': 'done'}) as run, \
             mock.patch.object(concierge, 'receipt', return_value='TQ-0005 closed.'), \
             mock.patch.object(concierge, 'surface', return_value=NEXT_CARD), \
             mock.patch.object(funnel, 'next_item', return_value=self.TABLE):
            ra.respond(s, 'whatsapp', JID, 'Mark done', None, poll=True)
        self.assertEqual(pd.call_args.args[1:3], ('close', 'task:5'))
        run.assert_called_once()

    def test_chips_with_nothing_to_act_on_are_not_drawn(self):
        text = ra.turn_text({'say': 'Done.', 'chips': [{'verb': 'close', 'label': 'Mark done'}, {'verb': 'next', 'label': 'Next'}]}, store=MemoryStore())
        self.assertNotIn('Mark done', text)
        self.assertIn('1 · Next', text)
