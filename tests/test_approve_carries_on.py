"""AN APPROVAL IS AN EVENT, AND THE AGENT GOES ON (the owner, 2026-11-09: "i hit approve why was this then an input on the right side?? ... once i
approve it should say sent and what to do next, not a new prompt on right side"). Taskuary's note to the agent after the press is never
recorded as the owner's line, on any transport; the press itself is an event with its result; every yes that went wakes the agent."""
import json, threading, time, unittest
from types import SimpleNamespace
from unittest import mock

from taskuary import cardqueue, general, landing, proposals, sessionrecord, shellgate as sg, terminal as term, verdicts, waitroom, workerstate as ws
from taskuary.store import MemoryStore
from taskuary.testing import Factory

HELD = r'C:\work\ledger'
SAID = 'https://github.com/northwind/ledger/pull/12#issuecomment-1'


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
             mock.patch.object(outbound, 'send_block', return_value=''), mock.patch('taskuary.learn.learn_from'):
            self.assertTrue(verdicts.decide(self.s, self.s.get_review(rid), 'approve')['ok'])
            end = time.time() + 5
            while not tried and time.time() < end: time.sleep(.01)
            time.sleep(.1)
        did = general.owner_did(self.s, self.tid)
        self.assertEqual(len(did), 1, did); self.assertIn(f'rv{rid}', did[0])
    def test_a_second_press_while_the_first_wake_is_starting_rides_in_that_turn(self):
        # two held steps on two cards, pressed a few seconds apart on a resting agent: the second found its answer already woken and no session
        # up yet, so its words went nowhere - and the turn that started answered past it, so the agent never heard it
        self.s.add_comment(self.tid, 'assistant', general.ASSISTANT_TYPE, 'Two steps are held for you.')
        told = []
        def start(*a, **kw): time.sleep(0.3); return SimpleNamespace(send_prompt=lambda text, **k: told.append((text, k)))
        with mock.patch.object(general, 'start_session', side_effect=start), mock.patch.object(general, 'handles', return_value=True):
            self.assertEqual(general.tell(self.s, self.tid, 'The owner approved it and Taskuary ran `git push origin deploy`.'), 'woke')
            self.assertEqual(general.tell(self.s, self.tid, 'The owner approved it and Taskuary ran `git push origin --tags`.'), 'woke')
            end = time.time() + 5
            while not told and time.time() < end: time.sleep(.01)
            time.sleep(0.1)
        [(text, kw)] = told
        self.assertIn('origin deploy', text); self.assertIn('origin --tags', text); self.assertFalse(kw.get('as_owner', True))

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
    with mock.patch.object(general, 'tell', lambda st, t, note, actor='owner': told.append(note) or 'told'):
        hooks._events(SimpleNamespace(store=s, task_id=tid, sid='run1', bg={}), {'hook_event_name': 'UserPromptSubmit', 'prompt': said})
    return '\n'.join(told)


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
    assert proposals.PASSED_TOLD in heard and f'rv{rid}' in heard, heard
    # ...and it keeps its record: never pressable, said so
    out = verdicts.decide(s, s.get_review(rid), 'approve')
    assert (out['ok'], out['send_error']) == (False, proposals.passed_why(s, rv)), out


def test_a_reply_draft_is_the_agents_to_redecide_never_passed_by_the_line_itself():
    s = MemoryStore(); tid = Factory(s).task('Answer the vendor')
    rid = s.add_review({'TaskId': tid, 'Kind': 'draft_reply', 'Status': 'pending', 'DraftText': 'Thursday works.'})
    s._exec("UPDATE review SET CreatedAt='2026-01-01 09:00:01' WHERE ReviewId=?", (rid,))
    assert proposals.move_on(s, tid) == [] and s.get_review(rid)['Status'] == 'pending'




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
    with mock.patch.object(general, 'tell', lambda st, t, n, actor='owner': told.append(n) or 'told'):
        sessionrecord.keep_seed(tid, note)                         # Taskuary typed it (terminal.type_into `brief`)
        hooks._events(sess, {'hook_event_name': 'UserPromptSubmit', 'prompt': note})
        assert s.get_review(rid)['Status'] == 'pending' and not told, (s.get_review(rid)['Status'], told)
        hooks._events(sess, {'hook_event_name': 'UserPromptSubmit', 'prompt': 'Actually make the reply shorter.'})
    # ...his own line in a terminal is heard here; over ACP the hook leaves it to the turn's own beginning
    assert s.get_review(rid)['Status'] == ('pending' if acp else 'superseded')
    assert bool(told) == (not acp)


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
        return self.s.get_review(rid if isinstance(rid, int) else rid['ReviewId'])

    def press(self, rv):
        with mock.patch('taskuary.waitroom.deliver', return_value={'delivered': 1, 'state': 'restarted'}):
            return verdicts.decide(self.s, self.s.get_review(rv['ReviewId']), 'approve')

    def test_an_approved_sql_that_fails_wakes_its_coding_agent_once_with_the_error(self):
        tid = self.coding_ended(); rv = self.card(tid, 'INSERT INTO ledgr (id, amount) SELECT 1, 9.5')
        out = self.press(rv)
        self.assertFalse(out['ok']); self.assertIn('ledgr', out['send_error']); self.assertTrue(out.get('told'))
        [n] = self.s.waiting_notes(tid)
        self.assertEqual(n['CreatedBy'], 'router', "Taskuary's words, never the owner's line")
        self.assertIn('IT FAILED', n['Note']); self.assertIn('ledgr', n['Note']); self.assertIn('what went wrong and the way past it', n['Note'])
        r = self.s.get_review(rv['ReviewId'])
        self.assertEqual(r['Status'], 'superseded', 'the card is over, its error kept - no Try again (the owner, 2026-11-16)')
        self.assertTrue(verdicts.decide(self.s, r, 'approve').get('already'), 'nothing on it presses again')
        self.assertIn('The agent was told', r['ActError'])
        self.assertEqual(general.owner_did(self.s, tid), [], "told once: never said again with the owner's next line")

    def test_the_agents_new_card_is_the_way_past_and_its_yes_is_told_it_went(self):
        tid = self.coding_ended(); self.press(self.card(tid, 'INSERT INTO ledgr (id, amount) SELECT 1, 9.5'))
        out = self.press(self.card(tid, 'INSERT INTO ledger (id, amount) SELECT 1, 9.5'))
        self.assertTrue(out['ok'], out)
        notes = self.s.waiting_notes(tid)
        self.assertEqual(len(notes), 2, 'each press reaches the agent once')
        self.assertIn('it went through', notes[-1]['Note']); self.assertIn('1 row changed', notes[-1]['Note'])

    def test_a_close_out_that_failed_still_waits_and_a_no_after_it_is_still_news(self):
        tid = self.coding_ended()
        rv = self.card(tid, '', 'close_issue', closeout=True)
        with mock.patch.object(proposals, 'linked', return_value=('northwind/ledger', 7)),              mock.patch('taskuary.ci._conn', side_effect=RuntimeError('GitHub is not answering')):
            out = self.press(rv)
        self.assertFalse(out['ok']); [n] = self.s.waiting_notes(tid); self.assertIn('still waits for their press', n['Note'])
        self.assertEqual(self.s.get_review(rv['ReviewId'])['Status'], 'pending', "a close-out is Taskuary's own card: its buttons stay")
        self.s._exec("UPDATE audit SET CreatedAt='2000-01-01 00:00:00' WHERE EntityType='review' AND Action=?", (general.TOLD,))
        self.s.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, 'GitHub was down - press it again later.')
        self.s._exec("UPDATE comment SET CreatedAt='2000-01-01 00:00:01' WHERE ActorType=?", (general.ASSISTANT_TYPE,))
        verdicts.decide(self.s, self.s.get_review(rv['ReviewId']), 'reject')
        self.assertTrue(any('turned down' in x for x in general.owner_did(self.s, tid)), general.owner_did(self.s, tid))

    def test_a_resting_general_agent_is_woken_on_the_failure(self):
        tid = Factory(self.s).task('Copy the September rows'); self.s.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, 'The insert is ready - press Approve.')
        told = []
        ses = SimpleNamespace(send_prompt=lambda text, **kw: told.append((text, kw)))
        with mock.patch.object(general, 'start_session', return_value=ses), mock.patch.object(general, 'handles', return_value=True):
            self.press(self.card(tid, 'INSERT INTO ledgr VALUES (1, 2)'))
            end = time.time() + 5
            while not told and time.time() < end: time.sleep(.01)
        [(text, kw)] = told
        self.assertFalse(kw.get('as_owner', True)); self.assertIn('IT FAILED', text)

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
             mock.patch.object(general, 'tell', side_effect=lambda st, tid, said, actor='owner', **k: heard.append(said) or 'told'):
            out = verdicts.decide(self.s, self.s.get_review(self.rid), 'approve', None, None, 'owner', cc=['ray@northwind.example'])
        self.assertTrue(out['ok'], out)
        [said] = heard
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
        self.assertIn('IT DID NOT GO', n['Note']); self.assertEqual(general.owner_did(self.s, self.tid), [])

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
        self.assertIn('IT DID NOT GO', n['Note']); self.assertIn('the new rate starts in March', n['Note'])
        self.assertNotIn('what went:', n['Note'])


class OneCardAtATime(unittest.TestCase):
    """THE OWNER, 2026-11-16: "where there are 2 action cards, like approve push then email, it should wait on each approval step or action
    card, so the agent should wait on it and then go to next steps". Every kind of card stands in one line (cardqueue): the next is shown only
    once the one before it was pressed and its agent has heard how it went - so a failed push holds back the email announcing it, and a no
    is the agent's to decide on before anything behind it stands. Invented people."""
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
        self.assertIn(f'rv{note} (the email to erin@northwind.example) is shown to the owner once this turn ends', n['Note'], 'it hears what waits, in the same hand-back')
        self.assertEqual(cardqueue.held(self.s, tid), {note}, 'never shown as-is while its agent goes on from the failure')
        verdicts.withdraw(self.s, tid, 'the push was refused - nothing is live', 'agent', which=str(note))
        self.answered(tid, 'GitHub refused the push; I took the note to Erin back.')
        self.assertEqual(cardqueue.state(self.s, tid)['units'], [], 'nothing of it ever stood in front of the owner')

    def test_a_push_that_went_brings_the_email_forward_once_its_agent_has_heard_it(self):
        tid = self.coding_ended(); self.s.set_setting('agent_push_enabled', '1', 'test')
        self.answered(tid, 'The push and the note to Erin are set up.', '2000-01-01 00:00:00')
        push, note = self.card(tid, '', 'open_pr'), self.email(tid, 'erin@northwind.example', 'Erin - the ledger fix is live.')
        self.assertEqual(cardqueue.line(cardqueue.state(self.s, tid)), '1 of 2 · next: the email to erin@northwind.example')
        with mock.patch('taskuary.ci.open_for_task', return_value={'url': 'https://github.com/northwind/ledger/pull/12'}):
            self.assertTrue(self.press(push)['ok'])
        [n] = self.s.waiting_notes(tid); self.assertIn('it went through', n['Note']); self.assertIn(f'rv{note}', n['Note'])
        self.assertEqual(cardqueue.held(self.s, tid), {note})
        self.answered(tid, 'The pull request is open.')
        self.assertEqual((cardqueue.state(self.s, tid)['live'], cardqueue.held(self.s, tid)), ([note], set()))

    def test_a_no_to_the_first_card_tells_its_agent_whose_no_it_was_and_the_next_waits_for_it(self):
        tid = Factory(self.s).task('Answer Gail and tell Ray'); self.answered(tid, 'Both letters are set up.', '2000-01-01 00:00:00')
        first, second = self.email(tid, 'gail@northwind.example', 'Gail - the rate is 4%.'), self.email(tid, 'ray@northwind.example', 'Ray - Gail has the rate.')
        told = []
        with mock.patch.object(general, 'tell', lambda st, t, said, actor='owner', heard=None: told.append(said) or (heard and heard('woke')) or 'woke'):
            self.assertTrue(verdicts.decide(self.s, self.s.get_review(first), 'reject')['ok'])
        [said] = told
        self.assertIn(f'turned down rv{first} (the email to gail@northwind.example) - their own no', said); self.assertIn(f'rv{second}', said)
        self.assertEqual(cardqueue.held(self.s, tid), {second}, 'the line does not go on past a no by itself')
        self.answered(tid, 'Leaving the note to Ray as it is.')
        self.assertEqual(cardqueue.state(self.s, tid)['live'], [second])

    def test_a_no_with_nothing_behind_it_wakes_nobody(self):
        tid = Factory(self.s).task('Answer Gail'); self.answered(tid, 'The letter is set up.', '2000-01-01 00:00:00')
        only = self.email(tid, 'gail@northwind.example', 'Gail - the rate is 4%.')
        with mock.patch.object(general, 'tell', side_effect=AssertionError('a no with nothing behind it is heard with his next line')):
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
        self.assertTrue(any(f"rv{rid}" in x for x in proposals.passed_since(self.s, self.tid, '')), 'and the agent is told, to raise it again')

    def test_a_mail_that_came_in_after_it_greys_it_too(self):
        self.s.set_setting('owner_email', 'alex@northwind.example', 'owner')                  # ...a colleague's mail: no stranger held behind trust
        rid = self.closeout()
        self.s.add_message({'TaskId': self.tid, 'ExternalId': 'g-1', 'ConversationId': 'th-1', 'Channel': 'email', 'Subject': 'Deploy',
                            'FromName': 'Gail Moreno', 'FromEmail': 'gail@northwind.example', 'BodyText': 'Hold the deploy until Friday.', 'Status': 'routed'})
        self.assertEqual(proposals.written_past(self.s, self.tid), {rid})

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
        self.s.set_setting('owner_email', 'alex@northwind.example', 'owner')
        rid = self.closeout()
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
