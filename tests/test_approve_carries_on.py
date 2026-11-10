"""AN APPROVAL IS AN EVENT, AND THE AGENT GOES ON (the owner, 2026-11-09: "i hit approve why was this then an input on the right side?? ... once i
approve it should say sent and what to do next, not a new prompt on right side"). Taskuary's note to the agent after the press is never
recorded as the owner's line, on any transport; the press itself is an event with its result; every yes that went wakes the agent."""
import json, threading, time, unittest
from types import SimpleNamespace
from unittest import mock

from taskuary import general, landing, proposals, sessionrecord, shellgate as sg, terminal as term, verdicts, waitroom, workerstate as ws
from taskuary.store import MemoryStore
from taskuary.testing import Factory

HELD = r'C:\work\ledger'
SAID = 'https://github.com/northwind/ledger/pull/12#issuecomment-1'


class HeldStep(unittest.TestCase):
    def setUp(self):
        self.s = MemoryStore(); self.tid = Factory(self.s).task('Answer the review on the ledger fix')
        proposals._PRESSED.clear(); general._WOKEN.clear()
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
        sess = SimpleNamespace(sid='run1', acp=True, task_id=self.tid, prompt=lambda text, brief=False, shown=None, done=None: got.append((text, brief)),
                               say=lambda *a, **k: self.fail('an approval note went in as an owner prompt'))
        self.approve(sess)
        end = time.time() + 5
        while not got and time.time() < end: time.sleep(.01)
        [(text, brief)] = got
        self.assertTrue(brief, 'drawn as Taskuary\'s brief (_meta.taskuary), never a "You" bubble')
        self.assertIn('The owner approved it', text); self.assertIn('what comes next', text)

    def test_on_a_pty_the_note_is_kept_as_a_seed_and_the_record_reads_it_as_a_brief(self):
        typed = []
        sess = SimpleNamespace(sid='run1', task_id=self.tid, cli='claude', write=lambda s: typed.append(s), n=0)
        with mock.patch.object(term, 'in_box', return_value=None), mock.patch.object(term, 'SEED_CHUNK_GAP', 0), mock.patch.object(term, 'SEED_ENTER', 0):
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

    def action(self, p):
        rid = Factory(self.s).review(self.tid, kind='action', reason='The agent asks', draft=json.dumps(p))
        return self.s.get_review(rid if isinstance(rid, int) else rid['ReviewId'])

    def test_a_card_approved_on_a_live_agent_is_its_next_prompt_by_taskuary(self):
        rv = self.action({'action': 'comment_issue', 'body': 'Fixed in the next release.'})
        with mock.patch.object(proposals, 'execute', return_value={'commented': 'northwind/ledger#7', 'url': SAID}), \
             mock.patch('taskuary.workerstate._live', return_value=object()), mock.patch('taskuary.waitroom.deliver', return_value={}):
            self.assertTrue(verdicts.decide(self.s, rv, 'approve')['ok'])
        [n] = self.s.waiting_notes(self.tid)
        self.assertEqual(n['CreatedBy'], 'router', 'Taskuary\'s note - never drawn as the owner\'s (codingchat.waiting, waitroom.batch)')
        self.assertIn('pressed Approve', n['Note']); self.assertIn(SAID, n['Note']); self.assertIn('what comes next', n['Note'])
        # ...and nothing invites a line about a link that did not come (agent walk 2, 2026-11-10: "No link came back with it", after every Send)
        self.assertNotIn('if it gave one', n['Note']); self.assertIn('where it gave none, say nothing about links', n['Note'])

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
        self.assertFalse(kw.get('as_owner', True)); self.assertIn('pressed Approve', text)
        self.assertFalse(general.follow_up(self.s, self.tid, 'send', said='again'), 'once per answer')

    def test_a_wake_that_never_started_leaves_the_next_press_to_start_it(self):
        self.s.add_comment(self.tid, 'assistant', general.ASSISTANT_TYPE, 'The reply is ready - press Send.')
        tried, told = [], []
        def start(*a, **kw):
            tried.append(1)
            if len(tried) == 1: raise RuntimeError('no AI is connected')
            return SimpleNamespace(send_prompt=lambda text, **k: told.append(text))
        with mock.patch.object(general, 'start_session', side_effect=start), mock.patch.object(general, 'handles', return_value=True):
            self.assertEqual(general.approved(self.s, self.tid, 'Send', 'the reply was sent'), 'woke')
            end = time.time() + 5
            while self.s.list_comments(self.tid, internal=True)[-1]['CommentId'] in general._WOKEN and time.time() < end: time.sleep(.01)
            self.assertEqual(general.approved(self.s, self.tid, 'Approve', 'the note was posted'), 'woke', 'the first woke nobody')
            end = time.time() + 5
            while not told and time.time() < end: time.sleep(.01)
        self.assertEqual(len(told), 1); self.assertIn('pressed Approve', told[0])

    def test_no_agent_ever_on_it_wakes_nothing(self):
        self.assertEqual(general.approved(self.s, self.tid, 'Send', 'the reply was sent'), '')

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
        self.assertTrue(brief, "Taskuary's brief, never the owner's bubble"); self.assertEqual(shown, []); self.assertIn('pressed Approve', text)

    def ended(self):
        "A coding task whose agent worked it and whose session has ended (its transcript filed, nothing live, not idled out)."
        tid = Factory(self.s).task('Fix the export', kind='coding'); self.s.add_transcript(tid, 'run1', 'Fixed the export.', 'claude', HELD)
        return tid

    def test_a_branch_landed_is_handed_back_to_its_agent(self):
        tid = self.ended()
        with mock.patch.object(landing, 'record', return_value={}), mock.patch.object(landing, '_save'), mock.patch('taskuary.waitroom.deliver', return_value={}):
            landing._landed(self.s, tid, 'pr', 'Pushed fix-export and opened pull request #12 into main: ' + SAID, 'owner')
        [n] = self.s.waiting_notes(tid)
        self.assertEqual(n['CreatedBy'], 'router'); self.assertIn('Open a PR', n['Note'])

    def test_an_approval_reaches_a_coding_agent_whose_session_ended(self):
        """The north-star audit, 2026-11-10: an approved merge or comment on a coding task whose session had ended was told nobody, and
        nothing said so - while a landing on the same task reopened its agent through the waiting room. One road (general.tell) now."""
        tid = self.ended()
        rid = Factory(self.s).review(tid, kind='action', reason='The agent asks', draft=json.dumps({'action': 'comment_issue', 'body': 'Fixed.'}))
        rv = self.s.get_review(rid if isinstance(rid, int) else rid['ReviewId'])
        with mock.patch.object(proposals, 'execute', return_value={'commented': 'northwind/ledger#7', 'url': SAID}), \
             mock.patch('taskuary.waitroom.deliver', return_value={'delivered': 1, 'state': 'restarted'}) as reopened:
            self.assertTrue(verdicts.decide(self.s, rv, 'approve')['ok'])
        [n] = self.s.waiting_notes(tid)
        self.assertEqual(n['CreatedBy'], 'router'); self.assertIn('pressed Approve', n['Note']); self.assertIn(SAID, n['Note'])
        reopened.assert_called()

    def test_a_landing_no_agent_worked_says_so_and_starts_nobody(self):
        with mock.patch.object(landing, 'record', return_value={}), mock.patch.object(landing, '_save'), mock.patch('taskuary.waitroom.deliver') as went:
            landing._landed(self.s, self.tid, 'merge', 'Merged fix-export into main.', 'owner')
        went.assert_not_called(); self.assertEqual(self.s.waiting_notes(self.tid), [])
        said = [c for c in self.s.list_comments(self.tid) if 'none was told' in c['Body']]
        self.assertEqual(len(said), 1, said)


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
            self.assertEqual(general.approved(self.s, self.tid, 'Send', 'the reply was sent'), 'told')
            self.assertLess(time.time() - t0, 2, 'the press answered before the turn it began had run')
            end = time.time() + 5
            while not told and time.time() < end: time.sleep(.01)
            turn.set()
            [(text, kw)] = told
            self.assertTrue(kw.get('brief'), "Taskuary's brief in the chat (general.BRIEF_ACTOR) - never the owner's line")
            self.assertIn('pressed Send', text); self.assertIn('what comes next', text)
            self.after()

    def test_on_a_pty_it_is_kept_as_a_seed_the_record_reads_as_a_brief(self):
        typed = []
        sess = self.parked(cli='claude', write=lambda s: typed.append(s), n=0)
        with mock.patch.dict(term.SESSIONS, {'a': sess}, clear=True), mock.patch.object(term, 'in_box', return_value=None), \
             mock.patch.object(term, 'SEED_CHUNK_GAP', 0), mock.patch.object(term, 'SEED_ENTER', 0), mock.patch.object(term, 'chooser_in', return_value=False):
            self.asked(sess)
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
            self.assertEqual(general.approved(self.s, self.tid, 'Send', 'the reply was sent'), 'told')
            self.after()
        [(text, brief)] = got
        self.assertTrue(brief); self.assertIn('pressed Send', text)

    def test_the_owners_own_answer_is_still_theirs(self):
        told = []
        sess = self.parked(send_prompt=lambda text, **kw: told.append((text, kw)))
        with mock.patch.dict(term.SESSIONS, {'a': sess}, clear=True):
            self.asked(sess)
            self.assertEqual(waitroom.add(self.s, self.tid, 'Yes, send it as it is')['state'], 'answered')
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


if __name__ == '__main__': unittest.main()
