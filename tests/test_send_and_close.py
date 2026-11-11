"""CLOSE OUT HAS TWO SENDS (the owner, 2026-11-03: "when you send message through close out we need button send and close and send without
closing so task stays open on send"). Send and close sends the reply and then closes the task through the one gate (concierge.close_after_send:
its agent stopped; kept open, and said why, only while something else on it waits for the owner's press); Send sends and the task stays open. The desk's Assistant lights the one the words
mean, a phone asks yes or no for it, and the index the model reads stays under its cap. Invented Northwind people only."""
import unittest
from types import SimpleNamespace
from unittest import mock

from taskuary import buttons, concierge, funnel, operations, terminal as term, toolcatalog
from tests import test_assistant_router as desk, test_chat_proposals as phone
import pytest

@pytest.fixture(autouse=True)
def _mailbox_connected(monkeypatch):
    """These drafts go by email in a world with no mailbox card: as if one were connected, so the Send is what is judged (a card that says
    Connect email lights nothing - advisor.unconnected, tests/test_agent_lights.py)."""
    from taskuary import advisor as _adv
    monkeypatch.setattr(_adv, 'unconnected', lambda store, item: False)


SENT = {'channel': 'email', 'to': ['erin@vendor.example'], 'cc': []}


def drafted(s):
    "a reply drafted on a task, on the table - the walk's own item for it"
    tid, item = desk.on_table(s)
    rid = s.add_review({'TaskId': tid, 'MessageId': item.get('mid'), 'Kind': 'reply', 'DraftText': 'The May numbers are attached.', 'Status': 'pending'})
    funnel.invalidate()
    return tid, rid, funnel.item_for_key(s, f'task:{tid}')


class Buttons(unittest.TestCase):
    def test_both_sends_are_on_the_one_list_and_each_says_what_it_does(self):
        self.assertEqual((buttons.label('approve'), buttons.label('send_close')), ('Send', 'Send and close'))
        self.assertEqual(buttons.hint('approve'), 'Sends the reply - the task stays open until you Mark done')
        self.assertTrue(buttons.hint('send_close').startswith('Sends the reply, then closes the task - its agent is stopped, and it stays open only while'))
        self.assertEqual(buttons.VERBS['send_close']['row'], ['send_close'])

    def test_send_and_close_is_offered_only_on_a_reply_drafted_on_a_task(self):
        s = desk.store(); tid, rid, item = drafted(s)
        self.assertEqual(concierge.cannot(item, 'send_close', s), '')
        self.assertIn('send_close', [b['verb'] for b in concierge.row_buttons(s, item)])
        self.assertTrue(concierge.cannot({**item, 'tid': None}, 'send_close', s), 'no task, nothing to close')
        self.assertTrue(concierge.cannot({**item, 'closeout': 'merge the pull request'}, 'send_close', s), "a close-out's yes is Approve")
        slot = s.add_review({'TaskId': tid, 'Kind': 'slot', 'DraftText': 'Hello Gail', 'Status': 'pending'})
        self.assertTrue(concierge.cannot({**item, 'rid': slot}, 'send_close', s), 'one email of several closes nothing')
        self.assertTrue(concierge.cannot({**item, 'draft': ''}, 'send_close', s), 'nothing drafted, nothing to send')

    def test_the_index_names_it_and_stays_under_its_cap(self):
        b = toolcatalog.block()
        self.assertLess(len(b), 7950)
        self.assertIn('send_close "Send and close"', b); self.assertIn('approve "Send"', b)
        self.assertIn('then the task closes', toolcatalog.DECISIONS['send_close'])
        self.assertIn('send_close', toolcatalog.DECISIONS['approve'], "Send's own line says which one closes")


class Server(unittest.TestCase):
    """review.approve takes `close`: the send, then the one gate - and every delivery state the send can end in keeps the task open."""
    def run_op(self, s, rid, **params):
        op = operations.propose(s, 'review.approve', rid, params, 'test')
        with mock.patch.object(term, 'live_sessions', return_value=[]):
            return phone.run(s, op)

    def setUp(self):
        self.s = desk.store(); self.tid, self.rid, self.item = drafted(self.s)
        self._sessions = dict(term.SESSIONS); term.SESSIONS.clear()
    def tearDown(self): term.SESSIONS.clear(); term.SESSIONS.update(self._sessions)

    def test_send_leaves_it_open(self):
        with mock.patch('taskuary.outbound.reply_to_message', return_value=SENT): r = self.run_op(self.s, self.rid)
        self.assertEqual(r.json()['status'], 'done')
        self.assertNotEqual(self.s.get_review(self.rid)['Status'], 'pending'); self.assertEqual(self.s.get_task(self.tid)['Status'], 'open')

    def test_send_and_close_closes_once_it_went(self):
        with mock.patch('taskuary.outbound.reply_to_message', return_value=SENT): r = self.run_op(self.s, self.rid, close=True)
        self.assertEqual(r.json()['status'], 'done'); self.assertEqual(self.s.get_task(self.tid)['Status'], 'done')
        self.assertTrue(r.json()['outcome']['closed'])

    def test_send_and_close_closes_whatever_its_agent_is_doing(self):
        """The owner's live app (2026-11-11): pressed while the agent's turn still ran, the reply went and the task stayed open - "the agent
        session on it is still open" - with the agent woken to hear of the send. It is his close: the agent is saved and stopped, as Mark done does."""
        term.SESSIONS['run1'] = SimpleNamespace(sid='run1', task_id=self.tid, alive=True, mode='assistant', busy=True, started=1)
        with mock.patch('taskuary.outbound.reply_to_message', return_value=SENT), mock.patch('taskuary.writeup.start') as job:
            r = self.run_op(self.s, self.rid, close=True)
        out = r.json()
        self.assertEqual(out['status'], 'done'); self.assertEqual((out['outcome']['closed'], out['outcome']['kept_open']), (True, []))
        # ...behind the press, by the job Mark done's press starts: the session written up, then the task closed
        job.assert_called_once_with(self.s, self.tid, close=True, actor=mock.ANY, no_reply=True, sid='run1')
        self.assertFalse([c['Body'] for c in self.s.list_comments(self.tid) if c['Body'].startswith('Sent. Kept open')])

    def test_it_closes_before_the_agent_parked_on_it_is_woken(self):
        """A send that went wakes the agent that set it up. The close came after, by the page's own call: the parked agent was working
        again, and the task read "Sent. Kept open: The agent session on it is still open" every time an agent had run on it."""
        from taskuary import general, verdicts
        ses = term.SESSIONS['g1'] = SimpleNamespace(sid='g1', task_id=self.tid, alive=True, mode='assistant', busy=False, started=1)
        woke = []
        def wake(store, tid, *a, **k): woke.append(tid); ses.busy = True; return 'told'
        def job(store, tid, **k): ses.alive = False; concierge.close_task(store, tid, k['actor'])       # ...the write-up's own close
        with mock.patch('taskuary.outbound.reply_to_message', return_value=SENT), mock.patch.object(general, 'approved', wake), mock.patch('taskuary.writeup.start', job):
            out = verdicts.decide(self.s, self.s.get_review(self.rid), 'approve', None, None, 'owner', closes=True)
            self.assertTrue(out['shut']['closed']); self.assertEqual(self.s.get_task(self.tid)['Status'], 'done')
            self.assertEqual(woke, [], 'an agent the close stops is not woken to be stopped')
            again = concierge.close_after_send(self.s, self.tid, 'owner')          # the page's walk asks a beat later: closed already
        self.assertEqual((again['status'], again['kept_open']), ('done', []))

    def test_the_second_ask_while_the_close_is_on_its_way_does_not_wait_for_it(self):
        "The page asks the gate again a beat after the send (walk leave `sent`): the close running behind the press is its answer."
        self.s.decide_review(self.rid, 'approved', None, 'owner')                 # ...the reply went
        with mock.patch('taskuary.writeup.closing', return_value=True), mock.patch.object(concierge, 'close_task') as shut:
            again = concierge.close_after_send(self.s, self.tid, 'owner')
        self.assertEqual((again['status'], again['closed'], shut.called), ('done', True, False))

    def test_it_closes_under_an_agent_at_work_and_wakes_nobody(self):
        from taskuary import general, verdicts
        term.SESSIONS['g1'] = SimpleNamespace(sid='g1', task_id=self.tid, alive=True, mode='assistant', busy=True, started=1)
        woke = []
        with mock.patch('taskuary.outbound.reply_to_message', return_value=SENT), mock.patch('taskuary.writeup.start'), \
             mock.patch.object(general, 'approved', lambda store, tid, *a, **k: woke.append(tid) or 'told'):
            out = verdicts.decide(self.s, self.s.get_review(self.rid), 'approve', None, None, 'owner', closes=True)
        self.assertEqual((out['shut']['closed'], out['shut']['kept_open'], woke), (True, [], []), 'a press that closes the task wakes nobody')

    def test_kept_open_is_said_once_in_words_and_its_agent_hears_the_send(self):
        "What still waits for his own press keeps it open - another email the task owes - said once, and the agent hears the send as before."
        from taskuary import general, verdicts
        self.s.add_review({'TaskId': self.tid, 'Kind': 'slot', 'DraftText': 'Hello Gail', 'Status': 'pending'})
        woke = []
        with mock.patch('taskuary.outbound.reply_to_message', return_value=SENT), \
             mock.patch.object(general, 'approved', lambda store, tid, *a, **k: woke.append(tid) or 'told'):
            out = verdicts.decide(self.s, self.s.get_review(self.rid), 'approve', None, None, 'owner', closes=True)
            again = concierge.close_after_send(self.s, self.tid, 'owner')
        why = 'an email this task owes still waits for your Send'
        self.assertEqual((out['shut']['closed'], out['shut']['kept_open'], again['kept_open'], woke), (False, [why], [why], [self.tid]))
        self.assertEqual([c['Body'] for c in self.s.list_comments(self.tid)].count(f'Sent. Kept open: {why[0].upper()}{why[1:]}.'), 1)
        said = [x[2] for x in general.presses(self.s, self.tid)]
        self.assertEqual([x for x in said if 'open' in x], [f'asked to close it with that send - it stays open: {why}'])

    def test_a_plain_send_closes_nothing_and_wakes_as_before(self):
        from taskuary import general, verdicts
        woke = []
        with mock.patch('taskuary.outbound.reply_to_message', return_value=SENT), \
             mock.patch.object(general, 'approved', lambda store, tid, *a, **k: woke.append(tid) or 'told'):
            out = verdicts.decide(self.s, self.s.get_review(self.rid), 'approve', None, None, 'owner')
        self.assertNotIn('shut', out); self.assertEqual((self.s.get_task(self.tid)['Status'], woke), ('open', [self.tid]))

    def test_a_send_that_failed_closes_nothing(self):
        with mock.patch('taskuary.outbound.reply_to_message', side_effect=RuntimeError('the mailbox refused it')):
            out = self.run_op(self.s, self.rid, close=True).json()
        self.assertNotEqual(out['status'], 'done'); self.assertEqual(self.s.get_task(self.tid)['Status'], 'open')
        self.assertEqual(self.s.get_review(self.rid)['Status'], 'pending')

    def test_a_send_nobody_can_confirm_closes_nothing_until_send_anyway_goes(self):
        # no receipt from the provider: delivery unknown, the draft frozen on Check delivery / Send anyway - and the task open
        with mock.patch('taskuary.outbound.reply_to_message', return_value=None): out = self.run_op(self.s, self.rid, close=True).json()
        self.assertNotEqual(out['status'], 'done'); self.assertEqual(self.s.get_task(self.tid)['Status'], 'open')
        self.assertEqual(self.s.get_review(self.rid)['DeliveryState'], 'unknown')
        # ...Send anyway, still the press of Send and close (the page holds which, ReviewDecision `closing`): it went, and the task closes
        with mock.patch('taskuary.outbound.reply_to_message', return_value=SENT): out = self.run_op(self.s, self.rid, close=True, anyway=True).json()
        self.assertEqual(out['status'], 'done'); self.assertEqual(self.s.get_task(self.tid)['Status'], 'done')


class Assistant(unittest.TestCase):
    """The desk lights the send the words mean - never presses it; a phone asks yes or no for it, and its yes runs it."""
    def test_send_it_lights_send_and_send_and_close_lights_send_and_close(self):
        s = desk.store(); tid, rid, item = drafted(s)
        out, _ = desk.say(s, 'send it', item['key'], 'CALL: {"kind": "approve", "params": {}}')
        self.assertEqual(out['light']['verb'], 'approve')
        out, _ = desk.say(s, 'send it and close it', item['key'], 'CALL: {"kind": "send_close", "params": {}}')
        self.assertEqual((out['light']['verb'], out['light']['label']), ('send_close', 'Send and close')); self.assertNotIn('pressed', out)
        self.assertEqual(s.get_review(rid)['Status'], 'pending'); self.assertEqual(s.get_task(tid)['Status'], 'open')
        # ...and the row's button by its own name reaches the same light
        out, _ = desk.say(s, 'send and close', item['key'], 'CALL: {"kind": "button.light", "params": {"button": "Send and close"}}')
        self.assertEqual(out['light']['verb'], 'send_close')

    def test_the_phone_offers_both_and_asks_yes_or_no_for_send_and_close(self):
        s = phone.store(); out = phone.arrive(s, subject='Where is the June invoice?', body='Can you send it?', llm=phone.brain('reply_only', None))
        rv = s.pending_review(out['task_id']); s.save_review_draft(rv['ReviewId'], 'Attached - sorry for the wait.')
        item = phone.pile(s)[0]
        with concierge.delivering(concierge.PHONE):
            verbs = [c['verb'] for c in concierge.chips_for(s, item)]
        self.assertEqual(verbs[:4], ['send_close', 'approve', 'redraft', 'close'], 'Send and close first, then Send, as the desk draws them')
        p = phone.say(s, 'send it and close the task', key=item['key'], model='CALL: {"kind": "send_close", "params": {}}')['proposal']
        self.assertEqual((p['kind'], p['target'], p['label'], p['params'].get('close')), ('review.approve', rv['ReviewId'], 'Send and close', True))
        self.assertEqual(s.get_task(out['task_id'])['Status'], 'open', 'nothing happens until the yes')
        with mock.patch('taskuary.outbound.reply_to_message', return_value=SENT):
            self.assertEqual(phone.run(s, p).json()['status'], 'done')
        self.assertEqual(s.get_task(out['task_id'])['Status'], 'done')

    def test_the_phones_plain_send_still_leaves_it_open(self):
        s = phone.store(); out = phone.arrive(s, subject='Where is the July invoice?', body='Can you send it?', llm=phone.brain('reply_only', None))
        rv = s.pending_review(out['task_id']); s.save_review_draft(rv['ReviewId'], 'Attached.')
        p = phone.say(s, 'send it', key=phone.pile(s)[0]['key'], model='CALL: {"kind": "approve", "params": {}}')['proposal']
        self.assertNotIn('close', p['params'])
        with mock.patch('taskuary.outbound.reply_to_message', return_value=SENT): phone.run(s, p)
        self.assertEqual(s.get_task(out['task_id'])['Status'], 'open')


class Advisor(unittest.TestCase):
    """THE ADVISOR'S SEND IN CLOSE OUT IS SEND AND CLOSE (the owner, 2026-11-03): a model that says send lights Send and close on a draft on a
    task - its Close out - and Send where the row has no Send and close."""
    def decide(self, s, item, verb, offered=None):
        import json
        from contextlib import nullcontext
        from taskuary import advisor
        llm = lambda system, user, **kw: json.dumps({'verb': verb, 'line': '', 'evidence': []})
        with mock.patch.object(term, 'live_sessions', return_value=[]), \
             (mock.patch.object(advisor, 'offered', lambda _s, _it: [buttons.chip(v) for v in offered]) if offered else nullcontext()):
            tgt = advisor.target_of(s, item['key'])
            advisor.notice(s, advisor.SHOWN, tgt[0], tgt[1], tier=2, wait=True, llm=llm, key=item['key'])
            with mock.patch.object(advisor, 'notice'): return advisor.decide(s, item['key'], preread=False)

    def test_a_draft_on_a_task_lights_send_and_close(self):
        s = desk.store(); tid, rid, item = drafted(s)
        d = self.decide(s, item, 'approve')
        self.assertEqual((d['verb'], d['label']), ('send_close', 'Send and close'))
        self.assertEqual(s.get_review(rid)['Status'], 'pending', 'lit, never pressed')

    def test_where_the_row_has_no_send_and_close_it_lights_send(self):
        s = desk.store(); tid, rid, item = drafted(s)
        d = self.decide(s, item, 'approve', offered=('approve', 'redraft', 'close'))
        self.assertEqual((d['verb'], d['label']), ('approve', 'Send'))

class PhonePin(unittest.TestCase):
    def test_a_draft_rewritten_after_the_phone_showed_it_is_not_sent_by_send_and_close_either(self):
        from taskuary import remote_assistant as ra
        s = phone.store(); out = phone.arrive(s, subject='Where is the August invoice?', body='Can you send it?', llm=phone.brain('reply_only', None))
        rv = s.pending_review(out['task_id']); s.save_review_draft(rv['ReviewId'], 'Attached.')
        item = phone.pile(s)[0]
        pin = ra._pinned(s, item, 'send_close')
        self.assertIn('shown', pin)
        s.save_review_draft(rv['ReviewId'], 'Attached - and the September one too.')
        with mock.patch.object(concierge, 'surface', return_value={'say': '', 'item': None}):
            self.assertIn('nothing was sent', ra._draft_moved(s, {'verb': 'send_close', 'key': item['key'], **pin}, item))
        self.assertEqual(s.get_task(out['task_id'])['Status'], 'open')


def tearDownModule(): mock.patch.stopall()


if __name__ == '__main__': unittest.main()
