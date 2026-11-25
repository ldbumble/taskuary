"""AN APPROVAL IS AN EVENT, AND THE AGENT GOES ON (the owner, 2026-11-09: "i hit approve why was this then an input on the right side?? ... once i
approve it should say sent and what to do next, not a new prompt on right side"). Taskuary's note to the agent after the press is never
recorded as the owner's line, on any transport; the press itself is an event with its result; every yes that went wakes the agent."""
import json, re, threading, time, unittest
from types import SimpleNamespace
from unittest import mock

from taskuary import (agenttools, card, cardqueue, events, general, landing, proposals, selfclose, sessionrecord, shellgate as sg, terminal as term,
                      verdicts, waitroom, workerstate as ws)
from taskuary.store import MemoryStore
from taskuary.testing import Factory

HELD = r'C:\work\ledger'
SAID = 'https://github.com/northwind/ledger/pull/12#issuecomment-1'


def told_with(s, tid, *said) -> str:
    "What its agent got: the words that rode the wake, and the events past its cursor that its turn is told (events.take)."
    return '\n'.join([*map(str, said), events.take(s, tid)[0]])


THEN = 'post the run log on the issue'          # ...the agent's own step after his press, as it raised the card (card.raising)


def acted_card(s, tid, then=THEN) -> int:
    "An act he pressed Approve on (a held run, a tool's step), raised with the agent's own step after it."
    rid = s.add_review({'TaskId': tid, 'Kind': 'action', 'Status': 'pending', 'DraftText': json.dumps({'action': 'run_tool'}), 'NextStep': then})
    s.decide_review(rid, 'approved', None, 'owner'); return rid


def sent_card(s, tid, then=None) -> int:
    "A card he pressed Send on, as the store writes it: its event is what the agent hears of the press (events.card)."
    rid = s.add_review({'TaskId': tid, 'Kind': 'draft_reply', 'Status': 'pending', 'DraftText': 'Confirmed.', 'NextStep': then})
    s.decide_review(rid, 'approved', 'Confirmed.', 'owner'); return rid


class HeldStep(unittest.TestCase):
    def setUp(self):
        self.s = MemoryStore(); self.tid = Factory(self.s).task('Answer the review on the ledger fix')
        general._WOKEN.clear()
        sg.check(self.s, self.tid, 'run1', "gh pr comment 12 --body 'Thanks - merged after the fix'", 'Bash', HELD)
        [self.rv] = self.s._rows("SELECT * FROM review WHERE TaskId=? AND Kind='action' AND Status='pending'", (self.tid,))

    def approve(self, sess):
        run = mock.patch.object(sg.subprocess, 'run', lambda *a, **k: SimpleNamespace(returncode=0, stdout=SAID, stderr=''))
        with mock.patch('taskuary.workerstate._live', return_value=sess), mock.patch.object(sg.os.path, 'isdir', lambda p: p == HELD), run, \
             mock.patch.object(term, 'stranger_now', return_value=''):
            out = verdicts.decide(self.s, self.rv, 'approve')
        self.assertTrue(out['ok'], out)
        return out

    def test_over_acp_the_note_is_taskuarys_never_the_owners(self):
        got = []
        sess = SimpleNamespace(sid='run1', acp=True, alive=True, task_id=self.tid, waiting=lambda: True, status_tail=lambda n=8: [],
                               prompt=lambda text, brief=False, shown=None, done=None: got.append((text, brief)),
                               say=lambda *a, **k: self.fail('an approval note went in as an owner prompt'))
        with mock.patch.dict(term.SESSIONS, {'run1': sess}, clear=True): self.approve(sess)      # ...by the one road in (general.to_agent)
        end = time.time() + 5
        while not got and time.time() < end: time.sleep(.01)
        [(text, brief)] = got
        self.assertTrue(brief, 'drawn as Taskuary\'s brief (_meta.taskuary), never a "You" bubble')
        self.assertIn('The owner approved it', text)

    def test_on_a_pty_the_note_is_kept_as_a_seed_and_the_record_reads_it_as_a_brief(self):
        typed = []
        sess = SimpleNamespace(sid='run1', task_id=self.tid, cli='claude', write=lambda s: typed.append(s), n=0, alive=True, waiting=lambda: True,
                               tail=lambda n=8: [], status_tail=lambda n=8: [])
        with mock.patch.object(term, 'in_box', return_value=None), mock.patch.object(term, 'SEED_CHUNK_GAP', 0), mock.patch.object(term, 'SEED_ENTER', 0),              mock.patch.dict(term.SESSIONS, {'run1': sess}, clear=True):      # ...a pane at rest: the waiting room types it in (general.to_agent)
            self.approve(sess)
            end = time.time() + 5
            while not typed and time.time() < end: time.sleep(.01)
        line = ''.join(typed)
        steps = sessionrecord.mark_briefs(self.tid, [{'k': 'you', 'text': line.strip()}])
        self.assertEqual([x['k'] for x in steps], ['brief'], steps)

    def test_the_press_is_an_event_with_its_result_and_no_owner_line(self):
        self.approve(SimpleNamespace(sid='run1', send_prompt=lambda text, as_owner=True: None))
        self.assertEqual(general.press_lines(self.s, self.tid), [], 'until the owner writes again it is the pressed card in the turn, not a line')
        owner = [c for c in self.s.list_comments(self.tid, internal=True) if c.get('ActorType') == general.USER_TYPE and c.get('Actor') != general.BRIEF_ACTOR]
        self.assertEqual(owner, [], 'nothing drawn as typed by the owner')
        self.s._exec("INSERT INTO comment (TaskId, Actor, ActorType, Body, CreatedAt) VALUES (?, 'owner', ?, 'Thanks - now the changelog', '2000-01-01')",
                     (self.tid, general.USER_TYPE))      # ...an owner line whose time is before the press: still the card
        self.assertEqual(general.press_lines(self.s, self.tid), [])
        self.s._exec("UPDATE comment SET CreatedAt='2999-01-01' WHERE Body='Thanks - now the changelog'")
        # ...the owner wrote again: still the card, in its turn (the owner, 2026-11-09: "compact the land") - never a line in its place
        self.assertEqual(general.press_lines(self.s, self.tid), [])
        kept = json.loads(self.s.get_review(self.rv['ReviewId'])['FinalText'])
        self.assertEqual(kept['result']['said'], SAID, 'the card keeps what it did, to read as its result')


class EveryYesCarriesOn(unittest.TestCase):
    def setUp(self):
        self.s = MemoryStore(); self.tid = Factory(self.s).task('Post the release note'); general._WOKEN.clear()

    def action(self, p, tid=None, then=THEN):
        rid = Factory(self.s).review(tid or self.tid, kind='action', reason='The agent asks', draft=json.dumps(p))
        rid = rid if isinstance(rid, int) else rid['ReviewId']; self.s.set_review_next_step(rid, then)
        return self.s.get_review(rid)

    def test_a_card_approved_on_a_live_agent_is_its_next_prompt_by_taskuary(self):
        rv = self.action({'action': 'comment_issue', 'body': 'Fixed in the next release.'})
        with mock.patch.object(proposals, 'execute', return_value={'commented': 'northwind/ledger#7', 'url': SAID}), \
             mock.patch('taskuary.workerstate._live', return_value=object()), mock.patch('taskuary.waitroom.deliver', return_value={}):
            self.assertTrue(verdicts.decide(self.s, rv, 'approve')['ok'])
        [n] = self.s.waiting_notes(self.tid)
        self.assertEqual(n['CreatedBy'], 'router', 'Taskuary\'s note - never drawn as the owner\'s (codingchat.waiting, waitroom.batch)')
        self.assertIn('he approved it', n['Note']); self.assertIn(SAID, n['Note'])
        # ...and nothing invites a line about a link that did not come (agent walk 2, 2026-11-10: "No link came back with it", after every Send)
        self.assertNotIn('if it gave one', n['Note'])

    def test_a_resting_general_agent_that_answered_is_woken_once_never_as_the_owner(self):
        self.s.add_comment(self.tid, 'assistant', general.ASSISTANT_TYPE, 'The reply is ready - press Send.')
        rv = self.action({'action': 'comment_issue', 'body': 'Fixed.'})
        told = []
        ses = SimpleNamespace(send_prompt=lambda text, **kw: told.append((text, kw)))
        with mock.patch.object(proposals, 'execute', return_value={'commented': 'northwind/ledger#7'}), \
             mock.patch.object(general, 'start_session', return_value=ses), mock.patch.object(general, 'handles', return_value=True):
            self.assertTrue(verdicts.decide(self.s, rv, 'approve')['ok'])
            end = time.time() + 5
            while not told and time.time() < end: time.sleep(.01)
        [(text, kw)] = told
        self.assertFalse(kw.get('as_owner', True)); self.assertIn('he approved it', told_with(self.s, self.tid, text))
        self.assertFalse(general.follow_up(self.s, self.tid, said='again'), 'once per answer')

    def test_a_wake_that_never_started_leaves_the_next_press_to_start_it(self):
        self.s.add_comment(self.tid, 'assistant', general.ASSISTANT_TYPE, 'The reply is ready - press Send.')
        tried, told = [], []
        def start(*a, **kw):
            tried.append(1)
            if len(tried) == 1: raise RuntimeError('no AI is connected')
            return SimpleNamespace(send_prompt=lambda text, **k: told.append(text))
        with mock.patch.object(general, 'start_session', side_effect=start), mock.patch.object(general, 'handles', return_value=True):
            self.assertEqual(general.approved(self.s, self.tid, 'Send', 'the reply was sent', review=sent_card(self.s, self.tid, THEN)), 'woke')
            end = time.time() + 5
            while self.s.list_comments(self.tid, internal=True)[-1]['CommentId'] in general._WOKEN and time.time() < end: time.sleep(.01)
            self.assertEqual(general.approved(self.s, self.tid, 'Approve', 'the note was posted', review=sent_card(self.s, self.tid, THEN)), 'woke', 'the first woke nobody')
            end = time.time() + 5
            while not told and time.time() < end: time.sleep(.01)
        self.assertEqual(len(told), 1); self.assertIn('he approved it', told_with(self.s, self.tid, told[0]))

    def test_a_send_whose_wake_never_started_is_still_news_to_the_next_turn(self):
        """No AI connected when he pressed Send on the agent's email: the send went, the wake did not start - and the press was marked told
        before the start was tried, so no later turn heard the email went (the stress round, 2026-11-18). Marked told only once it began."""
        from taskuary import outbound, slots
        cid = self.s.add_comment(self.tid, 'assistant', general.ASSISTANT_TYPE, 'The email to Paula is ready - press Send.')
        self.s._exec('UPDATE comment SET CreatedAt=? WHERE CommentId=?', ('2000-01-01 00:00:00', cid))      # its answer, before the press
        rid = slots.draft(self.s, self.tid, 'Hi Paula', to='paula@northwind.example', subject='Q4')['review_id']
        tried = []
        def start(*a, **kw): tried.append(1); raise RuntimeError('no AI is connected')
        with mock.patch.object(general, 'start_session', side_effect=start), mock.patch.object(general, 'handles', return_value=True), \
             mock.patch.object(outbound, 'send_out', return_value={'channel': 'email', 'to': ['paula@northwind.example'], 'cc': []}), \
             mock.patch.object(outbound, 'send_block', return_value=''), mock.patch('taskuary.learning.learn_from'):
            self.assertTrue(verdicts.decide(self.s, self.s.get_review(rid), 'approve')['ok'])
            end = time.time() + 5
            while not tried and time.time() < end: time.sleep(.01)
            time.sleep(.1)
        self.assertIn('he pressed Send - it was sent to paula@northwind.example', events.take(self.s, self.tid)[0])   # ...still past its cursor: its next turn hears it
    def test_a_second_press_while_the_first_wake_is_starting_rides_in_that_turn(self):
        # two held steps on two cards, pressed a few seconds apart on a resting agent: the second found its answer already woken and no session
        # up yet, so its words went nowhere - and the turn that started answered past it, so the agent never heard it
        self.s.add_comment(self.tid, 'assistant', general.ASSISTANT_TYPE, 'Two steps are held for you.')
        told = []
        def start(*a, **kw): time.sleep(0.3); return SimpleNamespace(send_prompt=lambda text, **k: told.append((text, k)))
        with mock.patch.object(general, 'start_session', side_effect=start), mock.patch.object(general, 'handles', return_value=True):
            self.assertEqual(general.to_agent(self.s, self.tid, 'The owner approved it and Taskuary ran `git push origin deploy`.'), 'woke')
            self.assertEqual(general.to_agent(self.s, self.tid, 'The owner approved it and Taskuary ran `git push origin --tags`.'), 'woke')
            end = time.time() + 5
            while not told and time.time() < end: time.sleep(.01)
            time.sleep(0.1)
        [(text, kw)] = told
        self.assertIn('origin deploy', told_with(self.s, self.tid, text)); self.assertIn('origin --tags', told_with(self.s, self.tid, text)); self.assertFalse(kw.get('as_owner', True))

    def test_no_agent_ever_on_it_wakes_nothing(self):
        self.assertEqual(general.approved(self.s, self.tid, 'Send', 'the reply was sent', review=sent_card(self.s, self.tid)), '')

    def test_a_live_coding_chat_hears_an_approval_as_taskuarys_brief(self):
        """The north-star audit, 2026-11-10: the waiting room handed an ACP coding session Taskuary's own note (an approval, a landing) with
        no owner line in it and `brief` unset - drawn in the coding chat as a "You" bubble, the 2026-11-09 complaint ("i hit approve why was
        this then an input on the right side??") on the one road every approval now takes."""
        got = []
        sess = SimpleNamespace(sid='run1', acp=True, alive=True, task_id=self.tid, waiting=lambda: True, status_tail=lambda n=8: [],
                               prompt=lambda text, brief=False, shown=None, done=None: got.append((text, brief, shown)))
        rv = self.action({'action': 'comment_issue', 'body': 'Fixed.'})
        with mock.patch.dict(term.SESSIONS, {'run1': sess}, clear=True), \
             mock.patch.object(proposals, 'execute', return_value={'commented': 'northwind/ledger#7', 'url': SAID}):
            self.assertTrue(verdicts.decide(self.s, rv, 'approve')['ok'])
        [(text, brief, shown)] = got
        self.assertTrue(brief, "Taskuary's brief, never the owner's bubble"); self.assertEqual(shown, []); self.assertIn('he approved it', told_with(self.s, self.tid, text))

    def ended(self):
        "A coding task whose agent worked it and whose session has ended (its transcript filed, nothing live, not idled out)."
        tid = Factory(self.s).task('Fix the export', kind='coding'); self.s.add_transcript(tid, 'run1', 'Fixed the export.', 'claude', HELD)
        return tid

    def test_a_branch_landed_is_handed_back_to_its_agent(self):
        tid = self.ended()
        with mock.patch.object(landing, 'record', return_value={'proposal': {'how': 'pr', 'then': 'say the PR is up'}}), mock.patch.object(landing, '_save'),              mock.patch('taskuary.waitroom.deliver', return_value={}):
            landing._landed(self.s, tid, 'pr', 'Pushed fix-export and opened pull request #12 into main: ' + SAID, 'owner')
        [n] = self.s.waiting_notes(tid)
        self.assertEqual(n['CreatedBy'], 'router'); self.assertIn('Open a PR', n['Note'])

    def test_an_approval_reaches_a_coding_agent_whose_session_ended(self):
        """The north-star audit, 2026-11-10: an approved merge or comment on a coding task whose session had ended was told nobody, and
        nothing said so - while a landing on the same task reopened its agent through the waiting room. One road (general.to_agent) now."""
        tid = self.ended()
        rv = self.action({'action': 'comment_issue', 'body': 'Fixed.'}, tid)
        with mock.patch.object(proposals, 'execute', return_value={'commented': 'northwind/ledger#7', 'url': SAID}), \
             mock.patch('taskuary.waitroom.deliver', return_value={'delivered': 1, 'state': 'restarted'}) as reopened:
            self.assertTrue(verdicts.decide(self.s, rv, 'approve')['ok'])
        [n] = self.s.waiting_notes(tid)
        self.assertEqual(n['CreatedBy'], 'router'); self.assertIn('he approved it', n['Note']); self.assertIn(SAID, n['Note'])
        reopened.assert_called()

    def test_a_landing_no_agent_worked_says_so_and_starts_nobody(self):
        with mock.patch.object(landing, 'record', return_value={'proposal': {'how': 'merge', 'then': 'deploy it'}}), mock.patch.object(landing, '_save'),              mock.patch('taskuary.waitroom.deliver') as went:
            landing._landed(self.s, self.tid, 'merge', 'Merged fix-export into main.', 'owner')
        went.assert_not_called(); self.assertEqual(self.s.waiting_notes(self.tid), [])
        said = [c for c in self.s.list_comments(self.tid) if 'none was told' in c['Body']]
        self.assertEqual(len(said), 1, said)


class OneRoadIntoTheAgent(unittest.TestCase):
    """ONE ROAD INTO THE AGENT (one road per decision, #10): a press, a browser hand-over closed and a sign-in done each woke the agent their own
    way - a chat heard a press only on the waiting room's next look (up to 10 s, the chat at rest meanwhile) and a page's Done at once."""
    def setUp(self):
        self.s = MemoryStore(); self.tid = Factory(self.s).task('Pay the toll invoice'); general._WOKEN.clear()

    def test_a_press_and_a_page_done_reach_a_live_chat_the_same_way_at_once(self):
        from taskuary import browsergate
        told = []
        sess = SimpleNamespace(sid='run1', task_id=self.tid, alive=True, send_prompt=lambda text, **kw: told.append((text, kw)))
        with mock.patch.dict(term.SESSIONS, {'run1': sess}, clear=True), mock.patch.object(waitroom, 'tick', side_effect=AssertionError('no clock')):
            t0 = time.time()
            self.assertEqual(general.approved(self.s, self.tid, 'Send', 'the reply was sent', review=sent_card(self.s, self.tid, THEN)), 'told')
            browsergate._tell(self.s, self.tid, "The owner pressed I'm done: they say they finished the step.", wake=True)
            end = time.time() + 5
            while len(told) < 2 and time.time() < end: time.sleep(.01)
        self.assertLess(time.time() - t0, 2, "heard at once - never on the waiting room's clock")
        self.assertEqual([kw for _t, kw in told], [{'as_owner': False}] * 2, "one road: the same call for both, never the owner's line")
        self.assertIn('he approved it', told_with(self.s, self.tid, *[t for t, _ in told])); self.assertIn("I'm done", told_with(self.s, self.tid, *[t for t, _ in told]))
        self.assertEqual(self.s.waiting_notes(self.tid), [], 'nothing left for a clock to deliver')

    def test_who_it_is_from_says_the_road(self):
        with self.assertRaises(ValueError): general.to_agent(self.s, self.tid, 'hi', frm='the assistant')
        with mock.patch.object(ws, 'answer', return_value={'delivered': True}) as ans, mock.patch.object(general, 'take_line', return_value={'kept': 1}) as line:
            general.to_agent(self.s, self.tid, 'Yes', frm='owner', request='q1')
            general.to_agent(self.s, self.tid, 'Also check March', frm='owner', wait=False)
        self.assertEqual(ans.call_args.args[2:4], ('q1', 'Yes')); self.assertEqual(line.call_args.args[1:3], (self.tid, 'Also check March'))
        with mock.patch.object(waitroom, 'deliver', return_value={}):
            general.to_agent(self.s, self.tid, 'Kept for its next stop', frm='owner', wake=False)
            general.to_agent(self.s, self.tid, 'Erin Blake on Teams: the file is up', frm='sender')
        self.assertEqual([n['CreatedBy'] for n in self.s.waiting_notes(self.tid)], ['owner', waitroom.TEAMMATE])


class ParkedOnItsOwnQuestion(unittest.TestCase):
    """The agent walk, 2026-11-09: the agent had asked "Should the reply go out as drafted?" and the owner pressed Send. Taskuary's note
    about the press reached it as the owner's ANSWER to that question: their bubble in the chat ("You: The owner pressed Send on what you
    set up..."), their words in the record the Advisor learns the owner from - and the press itself waited twelve seconds on the turn."""
    Q = 'Should the reply to Erin go out as drafted?'
    def setUp(self):
        self.s = MemoryStore(); self.tid = Factory(self.s).task('Answer Erin on the renewal'); general._WOKEN.clear()

    def parked(self, **kw):
        return SimpleNamespace(sid='run1', task_id=self.tid, alive=True, waiting=lambda: True, **kw)

    def asked(self, sess):
        self.assertTrue(ws.record(self.s, self.tid, sess.sid, 'input_needed', text=self.Q, source='api'))
        self.assertEqual(waitroom.state(self.s, self.tid)[0], 'asking')

    def after(self):
        [ev] = [e for e in ws.events(self.s, self.tid) if e['Kind'] == 'answered']
        self.assertNotEqual(ev.get('Source'), 'owner', 'the owner said nothing: the Advisor reads an owner answer as their own words')
        self.assertEqual(self.s.waiting_notes(self.tid), [])
        said = [c for c in self.s.list_comments(self.tid, internal=True) if c.get('ActorType') == general.USER_TYPE and c.get('Actor') != general.BRIEF_ACTOR]
        self.assertEqual(said, [], 'nothing filed as typed by the owner')

    def test_a_chat_agent_hears_it_as_taskuarys_brief_and_the_press_does_not_wait_on_its_turn(self):
        told, turn = [], threading.Event()
        def send_prompt(text, **kw): told.append((text, kw)); turn.wait(5)
        sess = self.parked(send_prompt=send_prompt)
        with mock.patch.dict(term.SESSIONS, {'a': sess}, clear=True):
            self.asked(sess)
            t0 = time.time()
            self.assertEqual(general.approved(self.s, self.tid, 'Approve', 'it ran', review=acted_card(self.s, self.tid)), 'told')
            self.assertLess(time.time() - t0, 2, 'the press answered before the turn it began had run')
            end = time.time() + 5
            while not told and time.time() < end: time.sleep(.01)
            turn.set()
            [(text, kw)] = told
            self.assertTrue(kw.get('brief'), "Taskuary's brief in the chat (general.BRIEF_ACTOR) - never the owner's line")
            self.assertIn('he approved it', told_with(self.s, self.tid, text))
            self.after()

    def test_on_a_pty_it_is_kept_as_a_seed_the_record_reads_as_a_brief(self):
        typed = []
        sess = self.parked(cli='claude', write=lambda s: typed.append(s), n=0)
        with mock.patch.dict(term.SESSIONS, {'a': sess}, clear=True), mock.patch.object(term, 'in_box', return_value=None), \
             mock.patch.object(term, 'SEED_CHUNK_GAP', 0), mock.patch.object(term, 'SEED_ENTER', 0), mock.patch.object(term, 'chooser_in', return_value=False):
            self.asked(sess)
            landing._save(self.s, self.tid, {'proposal': {'how': 'merge', 'then': 'deploy it'}})
            landing._landed(self.s, self.tid, 'merge', 'Merged the branch into main (f0ce6ca).', 'owner')
            end = time.time() + 5
            while not ''.join(typed).strip() and time.time() < end: time.sleep(.01)
            time.sleep(.3)
            self.after()
        steps = sessionrecord.mark_briefs(self.tid, [{'k': 'you', 'text': ''.join(typed).strip()}])
        self.assertEqual([x['k'] for x in steps], ['brief'], steps)

    def test_over_acp_it_is_a_prompt_marked_taskuarys(self):
        got = []
        sess = self.parked(acp=True, prompt=lambda text, brief=False, shown=None, done=None: got.append((text, brief)),
                           say=lambda *a, **k: self.fail("Taskuary's note went in as the owner's prompt"))
        with mock.patch.dict(term.SESSIONS, {'a': sess}, clear=True), mock.patch.object(term, 'chooser_in', return_value=False):
            self.asked(sess)
            self.assertEqual(general.approved(self.s, self.tid, 'Approve', 'it ran', review=acted_card(self.s, self.tid)), 'told')
            self.after()
        [(text, brief)] = got
        self.assertTrue(brief); self.assertIn('he approved it', told_with(self.s, self.tid, text))

    def test_the_owners_own_answer_is_still_theirs(self):
        told = []
        sess = self.parked(send_prompt=lambda text, **kw: told.append((text, kw)))
        with mock.patch.dict(term.SESSIONS, {'a': sess}, clear=True):
            self.asked(sess)
            self.assertEqual(waitroom.add(self.s, self.tid, 'Yes, send it as it is', 'owner')['state'], 'answered')
        [(text, kw)] = told
        self.assertEqual(text, 'Yes, send it as it is'); self.assertFalse(kw.get('brief'))
        [ev] = [e for e in ws.events(self.s, self.tid) if e['Kind'] == 'answered']
        self.assertEqual(ev.get('Source'), 'owner')


class InputsAreTypedOrCameIn(unittest.TestCase):
    """The owner's rule (2026-11-09): an input is what they typed, or what came in on the thread. A typed waiting-room batch on a pty is
    Taskuary's head round the owner's notes: their notes are theirs, the head a brief."""
    def test_a_typed_batch_splits_into_the_owners_lines(self):
        from taskuary import waitroom
        typed = waitroom.batch([{'Note': 'try now', 'CreatedBy': 'owner'}, {'Note': 'and the docs', 'CreatedBy': 'owner'}], remaining=1)
        got = sessionrecord.mark_briefs(424242, [{'k': 'you', 'text': typed}])
        self.assertEqual([(x['k'], x['text']) for x in got if x['k'] == 'you'], [('you', 'try now'), ('you', 'and the docs')])
        self.assertEqual([x['k'] for x in got], ['brief', 'you', 'you'])
        mine = waitroom.batch([{'Note': 'Pushed 2 commits.', 'CreatedBy': 'router'}])
        self.assertEqual([x['k'] for x in sessionrecord.mark_briefs(424242, [{'k': 'you', 'text': mine}])], ['brief'])



# A CARD YOU HAVE MOVED PAST IS OLD NEWS (the owner, 2026-11-10: "no once youa re passed it, it should stay where it is with buttons grayed out.
# You can ask the agent to bring it back?"). Every kind of action card, every kind of agent: raised in a turn, then the owner writes on the task
# - through each agent's own road - and the card is passed: still there at its place, not pressable from any press road, its agent told once it
# is old news; asked again, the agent raises it again and that is a new live card after the old one.
import pytest
from taskuary import acpcoding, hooks

CARDS = {'shell_act': {'action': 'shell_act', 'sid': 'run1', 'command': 'git push origin main', 'what': 'Push the fix', 'cwd': HELD},
         'browser_act': {'action': 'browser_act', 'sid': 'run1', 'what': 'Press Save on the vendor form', 'site': 'vendor.example'},
         'desktop_act': {'action': 'desktop_act', 'sid': 'run1', 'what': 'Click Submit in the payroll app'},
         'break_out': {'action': 'break_out', 'title': 'Chase the August invoice', 'what': 'Move the invoice chase to its own task'},
         'save_routine': {'action': 'save_routine', 'title': 'Weekly export check', 'what': 'Keep the export check as a routine'},
         'run_tool': {'action': 'run_tool', 'tool': 'export', 'what': 'Run the August export'},
         'comment_issue': {'action': 'comment_issue', 'repo': 'northwind/ledger', 'number': 12, 'text': 'Fixed in main', 'what': 'Comment on the issue'}}


def _raised(s, tid, p):
    rid = s.add_review({'TaskId': tid, 'Kind': 'action', 'Status': 'pending', 'DraftText': json.dumps(p), 'Reason': p['what']})
    s._exec("UPDATE review SET CreatedAt='2026-01-01 09:00:01' WHERE ReviewId=?", (rid,))
    return rid


def _line(s, tid, agent, said):
    "The owner's next line on the task, through `agent`'s own road; what that agent is told next."
    if agent == 'general':                        # the chat's agent (an API card's too: the same session, its brain an API)
        heard = []
        with mock.patch.object(general, '_selected', return_value=('api:test', 'Test', 'm')):
            sess = general.GeneralSession(s, tid)
        with mock.patch.object(general.llm_mod, 'build_llm', return_value=lambda system, user, **kw: heard.append(user) or 'On it.'):
            sess.send_prompt(said)
        return '\n'.join(heard)
    if agent == 'acp':                            # a coding agent over ACP: what its next turn is sent, as that turn begins (_begins)
        a = acpcoding.ACPCoding.__new__(acpcoding.ACPCoding)
        a.store, a.task_id = s, tid
        return a._begins([(said, False, [], None)], said)[0]
    told = []                                     # a coding agent in a terminal: its prompt hook, then Taskuary's next line
    with mock.patch.object(general, 'to_agent', lambda st, t, note, actor='owner': told.append(note) or 'told'):
        hooks._events(SimpleNamespace(store=s, task_id=tid, sid='run1', bg={}), {'hook_event_name': 'UserPromptSubmit', 'prompt': said})
    return told_with(s, tid, *told)


@pytest.mark.parametrize('agent', ['general', 'acp', 'pty'])
@pytest.mark.parametrize('kind', list(CARDS))
def test_a_card_he_writes_past_greys_in_its_place_on_every_agents_road_and_its_agent_is_told(kind, agent):
    """REVISED 2026-11-12 (from the owner's root rule - a chat only grows at its foot and the live action is the last thing, "the agent should
    bring it up"): his next line sets a waiting card aside on every agent's road - greyed in its own place, never pressable - and the turn
    that hears him is told it was set aside because he wrote again (never that he declined), to raise it again if it is still needed.
    (2026-11-11's "a waiting card stays lit" is replaced: the card he asked about now greys, and the agent raises it again below, last.)"""
    from taskuary import conversation
    s = MemoryStore(); tid = Factory(s).task('Fix the August export')
    s.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, 'I set it up - it waits for your press.')
    s._exec("UPDATE comment SET CreatedAt='2026-01-01 09:00:00' WHERE TaskId=?", (tid,))
    rid = _raised(s, tid, CARDS[kind])
    if agent == 'acp': conversation.hear(s, tid, ['l-acp'])            # ...the coding session's road hears his line as its turn begins
    heard = _line(s, tid, agent, 'What does that step change?')
    rv = s.get_review(rid)
    assert proposals.passed(rv), rv
    assert f'Card rv{rid} ' in heard and 'greyed, it will not go' in heard.split(f'Card rv{rid} ')[-1], heard
    # ...and it keeps its record: never pressable, said so
    out = verdicts.decide(s, s.get_review(rid), 'approve')
    assert (out['ok'], out['send_error']) == (False, proposals.passed_why(s, rv)), out


def test_a_card_his_line_greyed_that_still_stands_comes_back_under_it_as_it_was():
    """Walk 6 (the owner, 2026-11-23): every input greyed every waiting card, and the only way to keep one was a new proposal - the same three
    posts proposed four times, and a reply to Paula greyed by Gail's unrelated line. His line greys them; the agent's next turn brings back
    each that still stands, the same card under his newest line (cardqueue.keep), and nothing live sits above that line. Invented people."""
    from taskuary import agenttools, conversation
    s = MemoryStore(); tid = Factory(s).task('Post the Q3 headline and answer Paula')
    s.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, 'The post and the reply wait for your press.')
    s._exec("UPDATE comment SET CreatedAt='2026-01-01 09:00:00' WHERE TaskId=?", (tid,))
    post = _raised(s, tid, {'action': 'run_tool', 'type': 'linkedin_post', 'text': 'Q3 closed at 214 people.', 'what': 'Post the Q3 headline'})
    reply = s.add_review({'TaskId': tid, 'Kind': 'draft_reply', 'Status': 'pending', 'DraftText': 'Paula - Marcus handles printing now.',
                          'Deliver': json.dumps({'kind': 'reply', 'to': ['paula@northwind.example'], 'cc': []})})
    s._exec("UPDATE review SET CreatedAt='2026-01-01 09:00:01' WHERE ReviewId=?", (reply,))
    general.wait_line(s, tid, 'Also put the board pack on the shared drive.', line_id='l-drive'); conversation.hear(s, tid, ['l-drive'])
    assert proposals.passed(s.get_review(post)) and proposals.passed(s.get_review(reply)), 'his line greys every card that waited'
    out = json.loads(agenttools.call(s, tid, 'keep_card', {'which': f'rv{post} + rv{reply}'}, {}))
    assert out['ok'] and set(out['kept']) == {f'rv{post}', f'rv{reply}'}, out
    new = [int(out['kept'][f'rv{x}'][2:]) for x in (post, reply)]
    for old, rid in zip((post, reply), new):
        o, n = s.get_review(old), s.get_review(rid)
        assert (n['Status'], n['Kind'], n['DraftText'], n['Deliver']) == ('pending', o['Kind'], o['DraftText'], o['Deliver']), 'the same card'
        assert proposals.passed(o), 'the greyed one keeps its record where it stood'
    assert proposals.written_past(s, tid) == set(), 'nothing it brought back sits above his newest line'
    assert set(cardqueue.state(s, tid)['live']) | cardqueue.held(s, tid) == set(new)
    again = json.loads(agenttools.call(s, tid, 'keep_card', {'which': f'rv{new[0]}'}, {}))
    assert not again['ok'] and 'still waits for his press' in again['why'], 'only a greyed card is kept, and the refusal says the way on'


def test_a_held_step_is_run_again_never_kept():
    from taskuary import agenttools, conversation
    s = MemoryStore(); tid = Factory(s).task('Fix the August export')
    rid = _raised(s, tid, CARDS['shell_act'])
    general.wait_line(s, tid, 'What does that push change?', line_id='l-q'); conversation.hear(s, tid, ['l-q'])
    out = json.loads(agenttools.call(s, tid, 'keep_card', {'which': f'rv{rid}'}, {}))
    assert not out['ok'] and 'run it again' in out['why'], out




@pytest.mark.parametrize('acp', [False, True])
def test_a_prompt_that_is_not_his_never_sets_his_waiting_reply_aside(acp, tmp_path, monkeypatch):
    """Recorded on the real CLI, 2026-11-15: a coding session's prompt hook set every waiting card aside on ANY prompt - a note another agent
    left, a brief Taskuary typed - and told its agent "THE OWNER MOVED ON PAST THESE CARDS": the reply to the colleague greyed a second after
    the note arrived, the owner having touched nothing, and the agent would not raise it again. Only his own words move the conversation on
    (the record's one rule for whose a told step is - sessionrecord.mark_briefs); over ACP his line is heard as the turn begins (_begins)."""
    from taskuary import session_artifacts, sessionrecord
    monkeypatch.setattr(session_artifacts, 'root', lambda: tmp_path)
    s = MemoryStore(); tid = Factory(s).task('Comment the ledger totals')
    rid = s.add_review({'TaskId': tid, 'Kind': 'draft_reply', 'Status': 'pending', 'DraftText': 'Hi Gail - total() returns the sum plus tax.'})
    s._exec("UPDATE review SET CreatedAt='2026-01-01 09:00:01' WHERE ReviewId=?", (rid,))
    told, note = [], 'A note for you from the agent on TQ-0009: it changed totals.py in this checkout - read its diff before you edit the same lines.'
    sess = SimpleNamespace(store=s, task_id=tid, sid='run1', bg={}, acp=acp)
    with mock.patch.object(general, 'to_agent', lambda st, t, n, actor='owner': told.append(n) or 'told'):
        sessionrecord.keep_seed(tid, note)                         # Taskuary typed it (terminal.type_into `brief`)
        hooks._events(sess, {'hook_event_name': 'UserPromptSubmit', 'prompt': note})
        assert s.get_review(rid)['Status'] == 'pending' and not told, (s.get_review(rid)['Status'], told)
        hooks._events(sess, {'hook_event_name': 'UserPromptSubmit', 'prompt': 'Actually make the reply shorter.'})
    # ...his own line in a terminal is heard here; over ACP the hook leaves it to the turn's own beginning
    assert s.get_review(rid)['Status'] == ('pending' if acp else 'superseded')
    assert bool(told) == (not acp)



def test_taskuarys_words_typed_into_a_chat_go_in_as_its_brief_never_his_line():
    """The HIPAA walk, 2026-11-21: the waiting room handed a chat agent Taskuary's word of an approved sign-up by typing it into its composer,
    which sent it as the owner's own line - a "You" bubble speaking of him in the third person, [[TASKUARY-SIGNIN]] marker and all."""
    got, typed, done = [], [], threading.Event()
    sess = SimpleNamespace(task_id=1, write=typed.append, send_prompt=lambda text, **k: got.append((text, k)))
    term.type_into(sess, 'The owner approved the sign-up on 127.0.0.3.', done=lambda ok: done.set(), brief=True)
    assert done.wait(5) and got == [('The owner approved the sign-up on 127.0.0.3.', {'brief': True})] and typed == []


if __name__ == '__main__': unittest.main()


class AFailedPressIsHandedBack(unittest.TestCase):
    """THE OWNER, 2026-11-16: "we can't have an agent asking to do something then it does nothing or errors out, at least hand back to agent so
    we are not left hanging". A coding agent set up an INSERT on a database card; the owner pressed Approve; the card said the error in red and
    nothing else moved - its agent never heard, the task sat on "waiting on you". Every press that ran and failed now reaches its agent once."""
    def setUp(self):
        import os, sqlite3, tempfile
        self.s = MemoryStore(); general._WOKEN.clear()
        fd, self.db = tempfile.mkstemp(suffix='.db'); os.close(fd); self.addCleanup(lambda: os.path.exists(self.db) and os.remove(self.db))
        cx = sqlite3.connect(self.db); cx.execute('CREATE TABLE ledger (id INTEGER, amount REAL)'); cx.commit(); cx.close()
        c = self.s.get_connector_by_type('database')
        self.s.save_connector({'ConnectorId': c['ConnectorId'], 'ConfigJson': json.dumps({'conn_str': f'sqlite:///{self.db}'}), 'Active': 1}, 'test')
        # ...the engine itself stood in by sqlite3 (CI installs no sqlalchemy): the card, the road and the result's words are the real ones
        def engine(cs, query, n, write=False):
            cx = sqlite3.connect(cs.split(':///', 1)[1])
            try:
                cur = cx.execute(query)
                rows = [dict(zip([d[0] for d in cur.description], r)) for r in cur.fetchmany(n)] if cur.description else [{'rows_affected': max(cur.rowcount, 0)}]
                cx.commit() if write else cx.rollback(); return rows
            except sqlite3.Error as e: raise RuntimeError(f'(sqlite3.{type(e).__name__}) {e}')
            finally: cx.close()
        p = mock.patch('taskuary.db._rows_sqlalchemy', engine); p.start(); self.addCleanup(p.stop)

    def coding_ended(self):
        tid = Factory(self.s).task('Copy the September rows', kind='coding'); self.s.add_transcript(tid, 'run1', 'Set up the insert.', 'claude', HELD)
        return tid

    def card(self, tid, query, action='run_tool', **p):
        d = {'action': action, 'type': 'database', 'query': query} if action == 'run_tool' else {'action': action, **p}
        rid = Factory(self.s).review(tid, kind='action', reason='The agent asks', draft=json.dumps(d))
        rid = rid if isinstance(rid, int) else rid['ReviewId']; self.s.set_review_next_step(rid, THEN)
        return self.s.get_review(rid)

    def press(self, rv):
        with mock.patch('taskuary.waitroom.deliver', return_value={'delivered': 1, 'state': 'restarted'}):
            return verdicts.decide(self.s, self.s.get_review(rv['ReviewId']), 'approve')

    def test_an_approved_sql_that_fails_wakes_its_coding_agent_once_with_the_error(self):
        tid = self.coding_ended(); rv = self.card(tid, 'INSERT INTO ledgr (id, amount) SELECT 1, 9.5')
        out = self.press(rv)
        self.assertFalse(out['ok']); self.assertIn('ledgr', out['send_error']); self.assertTrue(out.get('told'))
        [n] = self.s.waiting_notes(tid)
        self.assertEqual(n['CreatedBy'], 'router', "Taskuary's words, never the owner's line")
        r = self.s.get_review(rv['ReviewId'])
        self.assertEqual(r['Status'], 'superseded', 'the card is over, its error kept - no Try again (the owner, 2026-11-16)')
        self.assertTrue(verdicts.decide(self.s, r, 'approve').get('already'), 'nothing on it presses again')
        self.assertIn('The agent was told', r['ActError'])
        self.assertEqual(events.take(self.s, tid)[0], '', "told once: nothing of it is past its cursor")

    def test_the_agents_new_card_is_the_way_past_and_its_yes_is_told_it_went(self):
        tid = self.coding_ended(); self.press(self.card(tid, 'INSERT INTO ledgr (id, amount) SELECT 1, 9.5'))
        out = self.press(self.card(tid, 'INSERT INTO ledger (id, amount) SELECT 1, 9.5'))
        self.assertTrue(out['ok'], out)
        notes = self.s.waiting_notes(tid)
        self.assertEqual(len(notes), 2, 'each press reaches the agent once')
        self.assertIn('he approved it - it was done', notes[-1]['Note']); self.assertIn('1 row changed', notes[-1]['Note'])

    def test_a_close_out_that_failed_still_waits_and_a_no_after_it_is_still_news(self):
        tid = self.coding_ended()
        rv = self.card(tid, '', 'close_issue', closeout=True)
        with mock.patch.object(proposals, 'linked', return_value=('northwind/ledger', 7)),              mock.patch('taskuary.ci._conn', side_effect=RuntimeError('GitHub is not answering')):
            out = self.press(rv)
        self.assertFalse(out['ok']); [n] = self.s.waiting_notes(tid); self.assertIn('the card waits for his press', n['Note'])
        self.assertEqual(self.s.get_review(rv['ReviewId'])['Status'], 'pending', "a close-out is Taskuary's own card: its buttons stay")
        self.s._exec("UPDATE audit SET CreatedAt='2000-01-01 00:00:00' WHERE EntityType='review' AND Action=?", (general.TOLD,))
        self.s.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, 'GitHub was down - press it again later.')
        self.s._exec("UPDATE comment SET CreatedAt='2000-01-01 00:00:01' WHERE ActorType=?", (general.ASSISTANT_TYPE,))
        verdicts.decide(self.s, self.s.get_review(rv['ReviewId']), 'reject')
        self.assertIn('he turned it down', told_with(self.s, tid, *[n['Note'] for n in self.s.waiting_notes(tid)]))

    def test_a_resting_general_agent_is_woken_on_the_failure(self):
        tid = Factory(self.s).task('Copy the September rows'); self.s.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, 'The insert is ready - press Approve.')
        told = []
        ses = SimpleNamespace(send_prompt=lambda text, **kw: told.append((text, kw)))
        with mock.patch.object(general, 'start_session', return_value=ses), mock.patch.object(general, 'handles', return_value=True):
            self.press(self.card(tid, 'INSERT INTO ledgr VALUES (1, 2)'))
            end = time.time() + 5
            while not told and time.time() < end: time.sleep(.01)
        [(text, kw)] = told
        self.assertFalse(kw.get('as_owner', True)); self.assertIn('it failed (', told_with(self.s, tid, text))

    def test_no_agent_ever_on_it_wakes_nothing_and_the_card_says_only_its_error(self):
        tid = Factory(self.s).task('Copy the September rows', kind='coding'); rv = self.card(tid, 'INSERT INTO ledgr VALUES (1, 2)')
        out = self.press(rv)
        self.assertFalse(out.get('told')); self.assertEqual(self.s.waiting_notes(tid), [])
        self.assertNotIn('The agent was told', self.s.get_review(rv['ReviewId'])['ActError'])

    def test_a_held_browser_step_that_cannot_run_is_handed_back(self):
        tid = self.coding_ended()
        rv = self.card(tid, '', 'browser_act', sid='s1', args=['click', '@e3'], url='https://portal.example/pay', what='press Pay', command='click @e3')
        with mock.patch('taskuary.browserview.state', return_value={'open': False}), mock.patch('taskuary.browserview.ended_on'):
            out = self.press(rv)
        self.assertFalse(out['ok']); [n] = self.s.waiting_notes(tid); self.assertIn('browser is closed', n['Note'])

    def test_a_pushed_work_github_refused_is_handed_back(self):
        tid = self.coding_ended(); self.s.set_setting('agent_push_enabled', '1', 'test')
        rv = self.card(tid, '', 'open_pr')
        with mock.patch('taskuary.ci.open_for_task', side_effect=RuntimeError('GitHub refused the push: the branch is protected')):
            out = self.press(rv)
        self.assertFalse(out['ok']); [n] = self.s.waiting_notes(tid); self.assertIn('branch is protected', n['Note'])

    def test_a_setting_change_that_cannot_land_is_handed_back(self):
        tid = self.coding_ended()
        rv = self.card(tid, '', 'settings', changes=[{'name': 'poll_minutes', 'value': 5}])
        with mock.patch.object(self.s, 'set_setting', side_effect=RuntimeError('the settings file is locked')):
            out = self.press(rv)
        self.assertFalse(out['ok']); [n] = self.s.waiting_notes(tid); self.assertIn('settings file is locked', n['Note'])

    def test_held_steps_approved_together_tell_once_for_the_card(self):
        tid = self.coding_ended()
        for cmd in ('git push origin fix', 'gh pr create --fill'): sg.check(self.s, tid, 'run1', cmd, 'Bash', HELD)
        rids = [r['ReviewId'] for r in self.s._rows("SELECT * FROM review WHERE TaskId=? AND Kind='action' AND Status='pending'", (tid,))]
        said = []
        no = SimpleNamespace(returncode=1, stdout=b'rejected', stderr=b'')
        with mock.patch.object(sg, '_tell', lambda st, t, text, **k: said.append(text)), mock.patch.object(sg, 'mid_turn', return_value=''), \
             mock.patch.object(sg.os.path, 'isdir', lambda p: True), mock.patch('taskuary.spawn.run', lambda *a, **k: no):
            sg.approve_steps(self.s, rids, verdicts.decide)
        self.assertEqual(len(said), 1, said); self.assertEqual(self.s.waiting_notes(tid), [], 'the card told it - never a second note')


class AFailedSendIsHandedBack(unittest.TestCase):
    "A Send that ran and did not go: its agent hears it at once, in the words owner_did keeps for it."
    def setUp(self):
        self.s = MemoryStore(); general._WOKEN.clear()
        self.tid = Factory(self.s).task('Answer Erin on the renewal', kind='coding')
        self.s.add_transcript(self.tid, 'run1', 'Drafted the reply.', 'claude', HELD)
        mid = self.s.add_message({'TaskId': self.tid, 'ExternalId': 'graph:x1', 'ConversationId': 'th-1', 'Channel': 'email', 'Subject': 'Renewal',
                                  'FromEmail': 'erin@northwind.example', 'BodyText': 'Can you confirm?', 'SentAt': '2026-10-01 09:00:00', 'Status': 'routed'})
        self.rid = self.s.add_review({'TaskId': self.tid, 'MessageId': mid, 'Kind': 'draft_reply', 'Status': 'pending', 'DraftText': 'Confirmed.',
                                      'Deliver': json.dumps({'kind': 'reply', 'to': ['erin@northwind.example'], 'cc': [], 'mode': 'reply_to'})})

    def test_a_send_tells_its_agent_whom_it_went_to_as_the_owner_left_it(self):
        """The owner moved the reply off Erin and onto Gail, copying Ray, and pressed Send. Its agent heard only "the reply was sent", and
        its next turn told the owner it had answered Erin. It hears whom the reply went to and who was copied - the card's envelope as sent."""
        from taskuary import outbound
        self.s.set_review_envelope(self.rid, {'kind': 'reply', 'mode': 'reply_to', 'to': ['gail@northwind.example'], 'cc': []})
        heard = []
        sent = lambda st, m, body, to=None, cc=None, **k: {'channel': 'email', 'to': to, 'cc': cc or []}
        with mock.patch('taskuary.outbound.reply_to_message', side_effect=sent), mock.patch.object(outbound, 'send_block', return_value=''), \
             mock.patch.object(verdicts, 'context_moved', return_value=(False, None)), \
             mock.patch.object(general, 'to_agent', side_effect=lambda st, tid, said, actor='owner', **k: heard.append(said) or 'told'):
            out = verdicts.decide(self.s, self.s.get_review(self.rid), 'approve', None, None, 'owner', cc=['ray@northwind.example'])
        self.assertTrue(out['ok'], out)
        said = told_with(self.s, self.tid, *heard).split(f'Card rv{self.rid} ')[-1]      # ...what became of the card, as the send left it
        self.assertIn('gail@northwind.example', said); self.assertIn('ray@northwind.example', said)
        self.assertNotIn('erin', said.lower())

    def test_a_send_the_provider_refused_wakes_its_agent_once(self):
        from taskuary import outbound
        with mock.patch('taskuary.outbound.reply_to_message', side_effect=RuntimeError('mailbox is over its sending limit')), \
             mock.patch.object(outbound, 'send_block', return_value=''), mock.patch('taskuary.waitroom.deliver', return_value={}), \
             mock.patch.object(verdicts, 'context_moved', return_value=(False, None)):
            out = verdicts.decide(self.s, self.s.get_review(self.rid), 'approve')
        self.assertEqual(out.get('delivery'), 'failed', out)
        [n] = self.s.waiting_notes(self.tid)
        self.assertIn('it did not go', n['Note']); self.assertEqual(events.take(self.s, self.tid)[0], '', 'told once')

    def test_the_owners_own_words_on_a_send_that_failed_reach_its_agent(self):
        """He rewrote the reply in the box and pressed Send, and the provider refused it: its agent heard "IT DID NOT GO" and nothing of his
        words - so the one it set up again went back to its own (the stress round, 2026-11-18). His words ride with the failure, as with a yes."""
        from taskuary import outbound
        self.s.snap_draft(self.rid, self.s.add_comment(self.tid, 'claude', 'agent', 'Drafted the reply.'))     # the turn that left it
        with mock.patch('taskuary.outbound.reply_to_message', side_effect=RuntimeError('mailbox is over its sending limit')), \
             mock.patch.object(outbound, 'send_block', return_value=''), mock.patch('taskuary.waitroom.deliver', return_value={}), \
             mock.patch.object(verdicts, 'context_moved', return_value=(False, None)):
            verdicts.decide(self.s, self.s.get_review(self.rid), 'approve', 'Confirmed - and the new rate starts in March.')
        [n] = self.s.waiting_notes(self.tid)
        self.assertIn('it did not go', n['Note']); self.assertIn('the new rate starts in March', n['Note'])
        self.assertNotIn('what went:', n['Note'])


class OneCardAtATime(unittest.TestCase):
    """THE OWNER, 2026-11-16: "where there are 2 action cards, like approve push then email, it should wait on each approval step or action
    card, so the agent should wait on it and then go to next steps". Every kind of card stands in one line (cardqueue), one drawn at a time -
    and EACH PRESS BRINGS THE NEXT AT ONCE (the owner, 2026-11-20: the hold while the agent went on from a press hid the rest of three posts):
    the agent hears each press as it is made, with what now waits, and takes back what the press changed. Invented people."""
    setUp, coding_ended, card, press = (AFailedPressIsHandedBack.setUp, AFailedPressIsHandedBack.coding_ended, AFailedPressIsHandedBack.card,
                                        AFailedPressIsHandedBack.press)

    def email(self, tid, to, words):
        return self.s.add_review({'TaskId': tid, 'Kind': 'slot', 'Status': 'pending', 'DraftText': words, 'Reason': 'assistant wrote this email - approve to send',
                                  'Deliver': json.dumps({'channel': 'email', 'to': [to], 'cc': [], 'subject': 'Ledger fix', 'slot': to})})

    def answered(self, tid, words, when=None):
        cid = self.s.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, words)
        if when: self.s._exec('UPDATE comment SET CreatedAt=? WHERE CommentId=?', (when, cid))

    def test_a_push_that_failed_holds_back_the_email_announcing_it_and_its_agent_decides(self):
        tid = self.coding_ended(); self.s.set_setting('agent_push_enabled', '1', 'test')
        self.answered(tid, 'The push and the note to Erin are set up.', '2000-01-01 00:00:00')
        push, note = self.card(tid, '', 'open_pr'), self.email(tid, 'erin@northwind.example', 'Erin - the ledger fix is live.')
        self.assertEqual((cardqueue.state(self.s, tid)['live'], cardqueue.held(self.s, tid)), ([push['ReviewId']], {note}))
        self.assertEqual([r['ReviewId'] for r in self.s.waiting_reviews() if r['TaskId'] == tid], [push['ReviewId']])
        with mock.patch('taskuary.ci.open_for_task', side_effect=RuntimeError('GitHub refused the push: the branch is protected')):
            out = self.press(push)
        self.assertFalse(out['ok']); [n] = self.s.waiting_notes(tid)
        self.assertIn('branch is protected', n['Note'])
        self.assertIn(f'Card rv{note} (the email to erin@northwind.example): up for his press', n['Note'], 'it hears what waits, in the same hand-back')
        self.assertEqual((cardqueue.state(self.s, tid)['live'], cardqueue.held(self.s, tid)), ([note], set()), 'the press brings the next at once')
        verdicts.withdraw(self.s, tid, 'the push was refused - nothing is live', 'agent', which=str(note))
        self.answered(tid, 'GitHub refused the push; I took the note to Erin back.')
        self.assertEqual(cardqueue.state(self.s, tid)['live'], [], 'its agent took it back: nothing waits')

    def test_a_push_that_went_brings_the_email_forward_at_the_press(self):
        tid = self.coding_ended(); self.s.set_setting('agent_push_enabled', '1', 'test')
        self.answered(tid, 'The push and the note to Erin are set up.', '2000-01-01 00:00:00')
        push, note = self.card(tid, '', 'open_pr'), self.email(tid, 'erin@northwind.example', 'Erin - the ledger fix is live.')
        self.assertEqual(cardqueue.line(cardqueue.state(self.s, tid)), '1 of 2 · next: the email to erin@northwind.example')
        with mock.patch('taskuary.ci.open_for_task', return_value={'url': 'https://github.com/northwind/ledger/pull/12'}):
            self.assertTrue(self.press(push)['ok'])
        self.assertEqual(self.s.waiting_notes(tid), [], 'a card still stands behind it: the press is recorded, nobody is woken')
        self.assertEqual((cardqueue.state(self.s, tid)['live'], cardqueue.held(self.s, tid)), ([note], set()))

    def test_presses_in_a_row_wake_the_agent_once_after_the_last(self):
        """Walk 6 (the owner, 2026-11-23): three letters stood in a row and the agent was told it would hear once the last was pressed - then
        it was woken by every Send and wrote "Gail's copy has gone." under a card that already said Sent. One wake, after the last, naming all."""
        from taskuary import outbound
        tid = Factory(self.s).task('Send the board pack'); self.answered(tid, 'Three letters are set up.', '2000-01-01 00:00:00')
        ids = [self.email(tid, f'{n}@northwind.example', f'{n.title()} - the pack is attached.') for n in ('erin', 'gail', 'paula')]
        told = []
        with mock.patch.object(general, 'to_agent', lambda st, t, said, actor='owner', heard=None, **k: told.append(said) or (heard and heard('woke')) or 'woke'), \
             mock.patch('taskuary.card.carries_on', return_value=True), mock.patch('taskuary.learning.learn_from'), \
             mock.patch.object(outbound, 'send_out', side_effect=lambda st, ch, to, *a, **k: {'channel': ch, 'to': to, 'cc': []}), \
             mock.patch.object(outbound, 'send_block', return_value=''):
            for i, rid in enumerate(ids):
                self.assertTrue(verdicts.decide(self.s, self.s.get_review(rid), 'approve')['ok'])
                self.assertEqual(len(told), 0 if i < 2 else 1, f'after press {i + 1}')
        said = told_with(self.s, tid, *told)
        for rid in ids: self.assertIn(f'Card rv{rid} (the email to', said)

    def test_a_no_that_ends_a_row_of_yeses_is_its_one_wake(self):
        from taskuary import outbound
        tid = Factory(self.s).task('Answer Gail and tell Ray'); self.answered(tid, 'Both letters are set up.', '2000-01-01 00:00:00')
        first, second = self.email(tid, 'gail@northwind.example', 'Gail - the rate is 4%.'), self.email(tid, 'ray@northwind.example', 'Ray - Gail has the rate.')
        told = []
        with mock.patch.object(general, 'to_agent', lambda st, t, said, actor='owner', heard=None, **k: told.append(said) or (heard and heard('woke')) or 'woke'), \
             mock.patch('taskuary.learning.learn_from'), mock.patch.object(outbound, 'send_block', return_value=''), \
             mock.patch.object(outbound, 'send_out', side_effect=lambda st, ch, to, *a, **k: {'channel': ch, 'to': to, 'cc': []}):
            self.assertTrue(verdicts.decide(self.s, self.s.get_review(first), 'approve')['ok'])
            self.assertEqual(told, [])
            self.assertTrue(verdicts.decide(self.s, self.s.get_review(second), 'reject')['ok'])
        [said] = told
        said = told_with(self.s, tid, said)
        self.assertIn(f'Card rv{second} (the email to ray@northwind.example): he turned it down', said); self.assertIn(f'Card rv{first} ', said)

    def test_a_no_to_the_first_card_tells_its_agent_whose_no_it_was_and_the_next_comes_forward(self):
        tid = Factory(self.s).task('Answer Gail and tell Ray'); self.answered(tid, 'Both letters are set up.', '2000-01-01 00:00:00')
        first, second = self.email(tid, 'gail@northwind.example', 'Gail - the rate is 4%.'), self.email(tid, 'ray@northwind.example', 'Ray - Gail has the rate.')
        told = []
        with mock.patch.object(general, 'to_agent', lambda st, t, said, actor='owner', heard=None: told.append(said) or (heard and heard('woke')) or 'woke'):
            self.assertTrue(verdicts.decide(self.s, self.s.get_review(first), 'reject')['ok'])
        [said] = told
        said = told_with(self.s, tid, said)
        self.assertIn(f'Card rv{first} (the email to gail@northwind.example): he turned it down', said); self.assertIn(f'Card rv{second} ', said)
        self.assertEqual((cardqueue.state(self.s, tid)['live'], cardqueue.held(self.s, tid)), ([second], set()), 'the press brings the next at once')

    def test_a_no_with_nothing_behind_it_wakes_nobody(self):
        tid = Factory(self.s).task('Answer Gail'); self.answered(tid, 'The letter is set up.', '2000-01-01 00:00:00')
        only = self.email(tid, 'gail@northwind.example', 'Gail - the rate is 4%.')
        with mock.patch.object(general, 'to_agent', side_effect=AssertionError('a no with nothing behind it is heard with his next line')):
            self.assertTrue(verdicts.decide(self.s, self.s.get_review(only), 'reject')['ok'])


class TheChatMovedOn(unittest.TestCase):
    """THE OWNER, 2026-11-16 (said ~20 times): "The second a new prompt comes in, from manual or email, it should gray out the action card but
    never move. Why do I have to click things on top while I kept on chatting." Recorded live on a coding task: a "Push 2 commits to master and
    deploy" card stood lit above his newer line "what needs to deploy?"; he scrolled up, pressed it, and it failed. One rule for every card -
    Taskuary's own close-out and landing question included: an input after it greys it in place at once, nothing presses it, and its agent
    hears the input and raises what is still wanted under it. Invented people."""
    def setUp(self):
        self.s = MemoryStore(); self.tid = Factory(self.s).task('Deploy the ledger fix'); general._WOKEN.clear()

    def closeout(self):
        rid = self.s.add_review({'TaskId': self.tid, 'Kind': 'action', 'Status': 'pending', 'Reason': 'finishing it: close the issue it came from',
                                 'DraftText': json.dumps({'action': 'close_issue', 'closeout': True})})
        self.s._exec("UPDATE review SET CreatedAt='2026-11-16 09:00:00' WHERE ReviewId=?", (rid,))
        return rid

    def test_a_close_out_greys_the_moment_his_line_comes_and_presses_nothing(self):
        from taskuary import conversation
        rid = self.closeout()
        self.assertEqual(proposals.written_past(self.s, self.tid), set())
        self.assertIn(rid, [r['ReviewId'] for r in self.s.waiting_reviews()])
        general.wait_line(self.s, self.tid, 'what needs to deploy?', line_id='l-deploy')          # ...typed while its agent works: not heard yet
        self.assertEqual(proposals.written_past(self.s, self.tid), {rid}, 'greyed at once, before any agent hears the line')
        self.assertNotIn(rid, [r['ReviewId'] for r in self.s.waiting_reviews()]); self.assertIsNone(self.s.waiting_on_owner(self.tid))
        out = verdicts.decide(self.s, self.s.get_review(rid), 'approve')
        self.assertTrue(out.get('passed') and not out['ok'], out)
        self.assertEqual(self.s.get_review(rid)['Status'], 'pending', 'never pressed - and never gone: it is still its card, greyed')
        conversation.hear(self.s, self.tid, ['l-deploy'])                                          # ...its agent takes the line
        r = self.s.get_review(rid)
        self.assertTrue(proposals.passed(r), 'set aside for good as the agent hears it')
        # ...and the agent is told, by what it is (a card of one is named, never numbered - walk 11), and can raise it again by that name
        said = cardqueue.screen(self.s, self.tid).split('Greyed, will not go')[1]
        self.assertIn('finishing it', said); self.assertNotIn(f'rv{rid}', said)
        self.assertEqual(cardqueue.named(self.s, self.tid, 'finishing it'), [rid])

    def reply_to_gail(self):
        """Gail asked on her thread, and her reply is ready."""
        self.s.set_setting('owner_email', 'alex@northwind.example', 'owner')                  # ...colleagues' mail: no stranger held behind trust
        mid = self.s.add_message({'TaskId': self.tid, 'ExternalId': 'g-0', 'ConversationId': 'th-gail', 'Channel': 'email', 'Subject': 'Deploy',
                                  'FromName': 'Gail Moreno', 'FromEmail': 'gail@northwind.example', 'BodyText': 'When does it go out?', 'Status': 'routed'})
        self.s._exec("UPDATE message SET CreatedAt='2026-11-16 08:00:00' WHERE MessageId=?", (mid,))
        rid = self.s.add_review({'TaskId': self.tid, 'MessageId': mid, 'Kind': 'draft_reply', 'Status': 'pending', 'DraftText': 'Hi Gail - Thursday.'})
        self.s._exec("UPDATE review SET CreatedAt='2026-11-16 09:00:00' WHERE ReviewId=?", (rid,))
        return rid

    def test_a_mail_greys_only_the_cards_it_bears_on(self):
        """THE OWNER, 2026-11-23, narrowing the rule above: a chat line from one colleague greyed another's ready reply card, and its agent
        redrafted it for nothing. A message greys the cards to whom it is from, or on its own thread; everyone else's stand live."""
        from taskuary import conversation
        rid, act = self.reply_to_gail(), self.closeout()
        paula = self.s.add_message({'TaskId': self.tid, 'ExternalId': 'p-1', 'ConversationId': 'chat-paula', 'Channel': 'teams', 'Subject': '',
                                    'FromName': 'Paula Vance', 'FromEmail': 'paula@northwind.example', 'BodyText': 'Can you add me to the rollout?', 'Status': 'routed'})
        self.assertEqual(proposals.written_past(self.s, self.tid), set(), "Paula's line bears on neither Gail's reply nor the close-out")
        conversation.hear(self.s, self.tid, turn=True)                                             # ...its agent hears Paula's line
        self.assertEqual([self.s.get_review(x)['Status'] for x in (rid, act)], ['pending', 'pending'], 'nothing set aside: nothing to redraft')
        self.assertTrue(conversation.heard(self.s, self.tid, 'mail', [paula]))
        self.s.add_message({'TaskId': self.tid, 'ExternalId': 'g-1', 'ConversationId': 'th-gail', 'Channel': 'email', 'Subject': 'RE: Deploy',
                            'FromName': 'Gail Moreno', 'FromEmail': 'gail@northwind.example', 'BodyText': 'Hold it until Friday.', 'Status': 'routed'})
        self.assertEqual(proposals.written_past(self.s, self.tid), {rid}, "Gail wrote again: her reply greys, the close-out stands")
        conversation.hear(self.s, self.tid, turn=True)
        self.assertTrue(proposals.passed(self.s.get_review(rid))); self.assertEqual(self.s.get_review(act)['Status'], 'pending')
        general.wait_line(self.s, self.tid, 'hold everything', line_id='l-hold')                    # ...his own line redirects the whole task
        self.assertEqual(proposals.written_past(self.s, self.tid), {act})

    # ONE SENTENCE FOR A GREYED CARD ON EVERY SURFACE (2026-11-17): his own answer to the sender read "you wrote again", and a press on a card
    # the sender's new mail moved past was refused with "set aside when you moved on" - the chat, the press and the page said three things
    def test_his_own_answer_to_the_sender_says_he_answered_them(self):
        self.s.set_setting('owner_email', 'alex@northwind.example', 'owner')
        mid = self.s.add_message({'TaskId': self.tid, 'ExternalId': 'g-1', 'ConversationId': 'th-1', 'Channel': 'email', 'Subject': 'Pilot',
                                  'FromName': 'Gail Moreno', 'FromEmail': 'gail@northwind.example', 'BodyText': 'Can you price site two?', 'Status': 'routed'})
        self.s._exec("UPDATE message SET CreatedAt='2026-11-16 08:00:00' WHERE MessageId=?", (mid,))
        rid = self.s.add_review({'TaskId': self.tid, 'MessageId': mid, 'Kind': 'draft_reply', 'Status': 'pending', 'DraftText': 'Hi Gail - yes, by Friday.'})
        self.s._exec("UPDATE review SET CreatedAt='2026-11-16 09:00:00' WHERE ReviewId=?", (rid,))
        self.s.add_message({'TaskId': self.tid, 'ExternalId': 'a-1', 'ConversationId': 'th-1', 'Channel': 'email', 'Subject': 'RE: Pilot', 'Direction': 'out',
                            'FromName': 'Alex Doyle', 'FromEmail': 'alex@northwind.example', 'BodyText': 'Done - see attached.', 'Status': 'routed'})
        self.assertEqual(proposals.passed_why(self.s, self.s.get_review(rid)), 'Not sent - you answered Gail Moreno yourself')

    def test_a_press_on_a_card_the_sender_wrote_past_is_refused_with_the_same_sentence(self):
        rid = self.reply_to_gail()
        self.s.add_message({'TaskId': self.tid, 'ExternalId': 'g-1', 'ConversationId': 'th-1', 'Channel': 'email', 'Subject': 'Deploy',
                            'FromName': 'Gail Moreno', 'FromEmail': 'gail@northwind.example', 'BodyText': 'Hold the deploy until Friday.', 'Status': 'routed'})
        out = verdicts.decide(self.s, self.s.get_review(rid), 'approve')
        self.assertEqual(out['send_error'], 'Not sent - Gail Moreno wrote again after it')
        self.assertEqual(out['send_error'], proposals.passed_why(self.s, self.s.get_review(rid)))

    def test_the_landing_question_greys_by_the_same_rule(self):
        landing._save(self.s, self.tid, {'start': 'abc', 'cwd': HELD, 'base': 'master', 'proposal': {'how': 'push', 'why': 'ship it', 'at': '2026-11-16 09:00:00'}})
        self.assertEqual(cardqueue.state(self.s, self.tid)['live'], [cardqueue.LAND])
        general.wait_line(self.s, self.tid, 'what needs to deploy?', line_id='l-deploy')
        self.assertEqual(cardqueue.state(self.s, self.tid)['units'], [], 'greyed: no longer the card that stands')
        from taskuary import conversation
        self.assertTrue(landing.pass_over(self.s, self.tid, conversation.ep('2026-11-16 09:00:00') - 1) is False, 'an input before it moves nothing')
        conversation.hear(self.s, self.tid, ['l-deploy'])
        self.assertTrue(landing.record(self.s, self.tid)['proposal'].get('passed'))
        self.assertFalse(landing.asked(self.s, self.tid))

    def test_a_push_raised_again_after_its_press_was_refused_keeps_its_place_before_the_email(self):
        """Recorded on the real CLI, 2026-11-16: Push was refused, the agent set the push up again, and it went behind the email announcing it
        - which then stood first; the agent took the email back and wrote it again. A card asked again while it still stands keeps its place."""
        from taskuary import conversation
        ask = {'ask': True, 'own': False, 'branch': 'master', 'answers': [{'how': 'push'}], 'line': '1 commit on master not on origin yet'}
        landing._save(self.s, self.tid, {'start': 'abc', 'cwd': HELD, 'base': 'master', 'proposal': {'how': 'push', 'why': 'ship it', 'at': '2026-11-16 09:00:00'}})
        note = self.s.add_review({'TaskId': self.tid, 'Kind': 'slot', 'Status': 'pending', 'DraftText': 'Erin - the fix is live.', 'Reason': 'assistant wrote this email - approve to send',
                                  'Deliver': json.dumps({'channel': 'email', 'to': ['erin@northwind.example'], 'cc': [], 'subject': 'Fix', 'slot': 'erin'})})
        self.s._exec("UPDATE review SET CreatedAt='2026-11-16 09:00:05' WHERE ReviewId=?", (note,))
        with mock.patch.object(landing, 'state', return_value=ask), mock.patch('taskuary.agentchannels.landing_proposed', lambda *a: None):
            landing.propose(self.s, self.tid, 'push', 'the push was refused - asking again')
        q = cardqueue.state(self.s, self.tid)
        self.assertEqual((q['live'], q['held']), ([cardqueue.LAND], [note]))

    def test_a_draft_the_working_turn_wrote_after_his_line_says_it_was_written_before_the_agent_read_it(self):
        """The owner's live task, 2026-11-16 ("there was no earlier draft. This is broken?"): an ask came in on WhatsApp, the agent started, he
        typed "Do it for the Hillside school" at 15:29:22 while it worked, and the turn - which never read his line - finished its draft at
        15:30:31. The next turn heard his line and set that draft aside, and it read "set aside when you moved on" as if he had done something
        to a draft he never saw. Greyed it stays; its line says what happened."""
        from taskuary import conversation
        general.wait_line(self.s, self.tid, 'Do it for the Hillside school', line_id='l-school')
        self.s._exec("UPDATE comment SET CreatedAt='2026-11-16 15:29:22' WHERE LineId='l-school'")
        rid = self.s.add_review({'TaskId': self.tid, 'Kind': 'slot', 'Status': 'pending', 'DraftText': 'Hi - the form for Lakeside is attached.',
                                 'Reason': 'assistant wrote this email - approve to send', 'Deliver': json.dumps({'channel': 'email', 'to': ['gail@northwind.example']})})
        self.s._exec("UPDATE review SET CreatedAt='2026-11-16 15:30:31' WHERE ReviewId=?", (rid,))
        self.assertEqual(proposals.written_past(self.s, self.tid), set(), 'written after his line: nothing moved past it before it is heard')
        conversation.hear(self.s, self.tid, ['l-school'])                                     # ...the next turn takes his line
        r = self.s.get_review(rid)
        self.assertTrue(proposals.passed(r))
        self.assertEqual(proposals.passed_why(self.s, r), 'Not sent - written before the agent read your line "Do it for the Hillside school"')

    def test_a_card_a_line_came_after_says_he_wrote_after_it(self):
        rid = self.closeout()
        general.wait_line(self.s, self.tid, 'what needs to deploy?', line_id='l-deploy')
        self.assertEqual(proposals.passed_why(self.s, self.s.get_review(rid)), 'Not sent - you wrote "what needs to deploy?" after it')


def test_a_post_its_agent_is_told_of_reads_as_the_card_it_was_never_the_tools_rows():
    """The owner's live task, 2026-11-18: he pressed Post to LinkedIn and his agent was woken with "pressed Approve on what you set up, and it
    went through: run tool - headline: 1 row, output: [{"id": "urn:...", "author": ...}]" - the tool's raw rows. Its provider's safety check
    refused that turn, and every turn after it. The note names the press and the card as he saw them, and the result by its link."""
    s = MemoryStore(); tid = Factory(s).task('Announce the ledger portal')
    p = {'action': 'run_tool', 'type': 'linkedin_post', 'text': 'The Northwind ledger portal is live.'}
    rid = Factory(s).review(tid, kind='action', reason='the agent proposes to write linkedin post on LinkedIn - the portal launch', draft=json.dumps(p))
    rv = s.get_review(rid if isinstance(rid, int) else rid['ReviewId'])
    rows = json.dumps([{'id': 'urn:li:share:700000001', 'author': 'urn:li:person:alexdoyle', 'visibility': 'PUBLIC',
                        'url': 'https://www.linkedin.example/feed/update/urn:li:share:700000001'}])
    press, said = verdicts.pressed(s, rv, {'result': {'headline': '1 row', 'output': rows, 'url': ''}})
    assert press == 'Post to LinkedIn'
    assert 'write linkedin post on LinkedIn' in said and 'https://www.linkedin.example/feed/update/urn:li:share:700000001' in said
    assert 'urn:li:person' not in said and '"author"' not in said and 'run tool' not in said



# AS FAR AS THE RESULT GOES (a walk, 2026-11-18): told "what it did" after a payment note was sent, the agent said Accounts Payable "received"
# it - nobody had answered. Every approval's note says a thing sent is sent, never received or acted on until someone answers


# WHAT STANDS ON HIS SCREEN, IN ONE FACT (the design round, 2026-11-18): a walk's agent set up three posts that stood one at a time, then told
# him "each has its own Post button" when only the first was drawn and his next line had greyed it - nothing told it what the page showed.
# cardqueue.screen reads the same line the page draws (state, written_past, each card's settled state) and says it in plain words, every turn
def test_the_screen_fact_says_what_waits_what_is_held_what_is_greyed_and_what_happened():
    s = MemoryStore(); f = Factory(s); tid = f.task('Announce the ledger portal')
    general_answer = s.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, 'Three posts are set up.')
    s._exec("UPDATE comment SET CreatedAt='2000-01-01 00:00:00' WHERE CommentId=?", (general_answer,))
    post = lambda kind, words: s.add_review({'TaskId': tid, 'Kind': 'action', 'Status': 'pending', 'Reason': f'post on {kind}',
                                              'DraftText': json.dumps({'action': 'run_tool', 'type': f'{kind.lower()}_post', 'text': words})})
    sent = s.add_review({'TaskId': tid, 'Kind': 'slot', 'Status': 'pending', 'DraftText': 'Gail - the portal launches Monday.', 'Reason': 'assistant wrote this email',
                         'Deliver': json.dumps({'channel': 'email', 'to': ['gail@northwind.example'], 'subject': 'Portal'})})
    s.decide_review(sent, 'approved', 'Gail - the portal launches Monday.', 'owner')
    s._exec("UPDATE review SET DeliveryState='sent', DecidedAt='1999-12-31 09:00:00' WHERE ReviewId=?", (sent,))     # ...heard by the answer after it
    x, reddit = post('X', 'The portal launches Monday.'), post('Reddit', 'Northwind ledger portal: invoices in one place.')
    said = cardqueue.screen(s, tid)
    # ...each card of one by what it is, never its number (walk 11: the agent told him it drafted the reply "(rv2)")
    assert 'post on X' in said.split('Waiting for his press now:')[1].split('\n')[0] and 'The portal launches Monday.' in said, said
    assert 'post on Reddit' in said.split('Not on his screen yet')[1].split('\n')[0], said
    assert 'the email to gail@northwind.example' in said.split('Sent')[1].split('\n')[0] and not re.search(r'\brv\d', said), said
    s._exec("UPDATE review SET CreatedAt='2000-01-01 00:00:01' WHERE ReviewId IN (?,?)", (x, reddit))
    general.wait_line(s, tid, 'Give me a button for each', line_id='l-each')                 # ...his line greys both, the moment it is sent
    said = cardqueue.screen(s, tid)
    assert 'Waiting for his press now' not in said and 'Nothing waits for his press' in said, said
    assert said.count('Greyed') == 2 and 'Not sent - you wrote "Give me a button for each" after it' in said, said
    assert 'run_tool' not in said and 'superseded' not in said and 'pending' not in said, 'his words, never the rows'


def test_a_card_set_aside_while_it_waited_its_turn_is_greyed_in_the_chat_never_gone():
    # the Hydrogen walk, 2026-11-19: "the Reddit post is up next" - card 6 of 6, set aside by his line before its turn came, had no row and vanished
    from taskuary import chatlog
    s = MemoryStore(); f = Factory(s); tid = f.task('Announce the ledger portal')
    post = lambda kind, words: s.add_review({'TaskId': tid, 'Kind': 'action', 'Status': 'pending', 'Reason': f'post on {kind}',
                                              'DraftText': json.dumps({'action': 'run_tool', 'type': f'{kind.lower()}_post', 'text': words})})
    x, reddit = post('X', 'The portal launches Monday.'), post('Reddit', 'Northwind ledger portal: invoices in one place.')
    for r in (x, reddit): s.decide_review(r, 'superseded', None, 'taskuary', proposals.SET_ASIDE)     # his line moved past both
    cards = [c['review'] for i in chatlog.read(s, tid)['items'] for c in ([i] if i['kind'] == 'card' else i.get('cards') or [])]
    assert reddit in cards, 'greyed where it stood, never gone'


class ASendIsSaidByItsCard(unittest.TestCase):
    """The owner, 2026-11-25, twice in one night on a WhatsApp reply: Send woke the agent and it wrote "You sent Gabi..." under the card that
    read Sent - once while it was still at work (the waiting room handed it the press as it stopped), once at rest with no summary filed. Words
    he sent are said by their card; the agent hears them in its next turn, and is woken only where it said a step of its own follows."""
    def setUp(self):
        self.s = MemoryStore(); self.tid = self.s.create_task({'Title': 'Reply to Gail', 'Kind': 'general', 'Status': 'open'}, 'owner')

    def test_a_send_with_no_then_starts_no_turn_whatever_its_turn_said_and_one_with_then_wakes_it(self):
        """d6e6a670a trimmed end_turn's after_press text and every Send woke the agent to say it went: whether a press wakes is now the card's
        own `then`, never a word in the turn's summary - a summary that still says after_press wakes nobody."""
        rid, step = sent_card(self.s, self.tid), sent_card(self.s, self.tid, 'tell Ray the date is fixed')
        self.s.add_comment(self.tid, 'assistant', general.SUMMARY_TYPE, json.dumps({'did': 'drafted it', 'after_press': 'send'}))
        with mock.patch.object(general, 'to_agent', return_value='told') as told:
            for busy in (True, False):
                with mock.patch.object(general, 'at_work', return_value=busy):
                    self.assertEqual(general.approved(self.s, self.tid, 'Send', 'the reply was sent', review=rid), '', f'at work: {busy}')
            told.assert_not_called()
            self.assertEqual(general.approved(self.s, self.tid, 'Send', 'the reply was sent', review=step), 'told')    # ...a step of its own follows
        self.assertNotIn('after_press', agenttools.TOOLS['end_turn'][1] + json.dumps(agenttools.TOOLS['end_turn'][2]) + selfclose.SUMMARY_LINE)

    def test_a_send_never_answers_a_question_on_something_else_and_answers_the_one_asked_about_its_card(self):
        """Walk 20: a reply card to a vendor and ONE question on what headcount to share, in the same turn - his words sent to someone else are
        not his answer to it. A question asked ABOUT the card (ask_owner's `card`) is: left standing, it stayed on the task after the letter went."""
        rid, sess = sent_card(self.s, self.tid), SimpleNamespace(sid='run1', task_id=self.tid, alive=True, waiting=lambda: True)
        head, drafted = 'What headcount should I share with them?', 'Should the reply to Gail go out as drafted?'
        act = acted_card(self.s, self.tid)
        with mock.patch.object(general, 'to_agent', return_value='told') as told, mock.patch.dict(term.SESSIONS, {'run1': sess}, clear=True), \
             mock.patch.object(general, 'at_work', return_value=False):
            agenttools.call(self.s, self.tid, 'ask_owner', {'question': drafted, 'card': f'rv{rid}'}, {})
            for q in (head, drafted): self.assertTrue(ws.record(self.s, self.tid, 'run1', 'input_needed', text=q, source='api'))
            self.assertEqual(general.approved(self.s, self.tid, 'Send', 'the reply was sent', review=rid), '')       # ...the Send is its card's
            told.assert_not_called()
            self.assertEqual([r['text'] for r in ws.status(self.s, self.tid)['requests']], [head], 'his Send answered the one about its card')
            self.assertEqual(general.approved(self.s, self.tid, 'Approve', 'it ran', review=act), 'told')            # ...an act with a step after it

    def test_an_approved_merge_with_then_deploy_wakes_it_once_and_one_without_wakes_nobody(self):
        quiet, merge = acted_card(self.s, self.tid, None), acted_card(self.s, self.tid, 'deploy, then reply that it is live')
        self.s.add_comment(self.tid, 'assistant', general.ASSISTANT_TYPE, 'The merge is set up.'); general._WOKEN.clear()
        told = []
        with mock.patch.object(general, 'start_session', return_value=SimpleNamespace(send_prompt=lambda text, **k: told.append(text))), \
             mock.patch.object(general, 'handles', return_value=True):
            self.assertEqual(general.approved(self.s, self.tid, 'Approve', 'it ran', review=quiet), '')
            self.assertEqual(general.approved(self.s, self.tid, 'Approve', 'merged', review=merge), 'woke')
            end = time.time() + 5
            while not told and time.time() < end: time.sleep(.01)
        self.assertEqual(len(told), 1)


@pytest.mark.parametrize('road', ['tool', 'cli', 'marker'])
def test_then_is_kept_on_the_card_whatever_road_raised_it_and_a_rewrite_without_it_clears_it(road):
    """One rule on every road a card is raised by - an agent's tool (general CLI, Codex, API agents over MCP), `taskuary --reply/--draft --then`
    (the CLI's endpoint, server._raising) and a TASKUARY-PROPOSE mark - kept on the card itself, so a restart between the card and his press
    keeps it. A later raise of the same card speaks for it: rewritten with no `then`, its press wakes nobody."""
    s = MemoryStore(); tid = Factory(s).task('Write the onboarding playbook')
    text = '# Onboarding\nwhen: a new hire starts\nDay one: the laptop.'
    doors = {'propose': lambda t, p: {'ok': bool(q := proposals.queue(s, t, p)), 'review': q and q['reviewId']}}
    def raise_(then, words):
        p = {'action': 'write_playbook', 'slug': 'onboarding', 'text': words}
        if road == 'tool': agenttools.call(s, tid, 'propose', {'kind': 'act', **p, **({'then': then} if then else {})}, doors)
        elif road == 'marker': proposals.queue(s, tid, {**p, **({'then': then} if then else {})})
        else:
            with card.raising(s, tid, then): proposals.queue(s, tid, p)
        return s._rows("SELECT * FROM review WHERE TaskId=? ORDER BY ReviewId DESC", (tid,))[0]
    first = raise_('tell Erin it is up', text)
    assert card.then_of(s.get_review(first['ReviewId'])) == 'tell Erin it is up' and card.carries_on(s.get_review(first['ReviewId']))
    general._WOKEN.clear()                                    # ...a restart: nothing held in memory, the card still says it
    s.decide_review(first['ReviewId'], 'approved', None, 'owner')
    with mock.patch.object(general, 'to_agent', return_value='woke') as told:
        assert general.approved(s, tid, 'Approve', 'saved', review=first['ReviewId']) == 'woke'
        assert not card.carries_on(again := s.get_review(raise_('', text + ' The badge.')['ReviewId']))
        s.decide_review(again['ReviewId'], 'approved', None, 'owner')
        assert general.approved(s, tid, 'Approve', 'saved', review=again['ReviewId']) == ''
    assert told.call_count == 1


def test_a_landing_wakes_its_agent_only_where_its_proposal_named_a_step_after_it():
    s = MemoryStore(); tid = Factory(s).task('Fix the export', kind='coding'); s.add_transcript(tid, 'run1', 'Fixed the export.', 'claude', HELD)
    for then, woken in (('', False), ('check the deploy is live', True)):
        landing._save(s, tid, {'proposal': {'how': 'merge', **({'then': then} if then else {})}})
        with mock.patch('taskuary.waitroom.deliver', return_value={}), mock.patch.object(general, 'at_work', return_value=False):
            landing._landed(s, tid, 'merge', f'Merged fix-export into main ({then or "quiet"}).', 'owner')
        assert bool(s.waiting_notes(tid)) is woken, then
        if not woken: assert 'quiet' in events.take(s, tid)[0], 'what landed unwoken is still said in its next turn'
