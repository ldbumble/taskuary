"""A regular (API) worker says what it needs and when its turn ended, as events - not prose a judge reads (PW-225).

Its turn used to leave one `working` event and nothing after it, so a parked assistant read as working for ever and a
question it asked in prose was a question nobody saw. Now every reply ends the turn with `turn_end`, and a reply that
ends with the ask marker is an Input-needed request with the exact question and choices - the same request the
owner's answer is bound to (workerstate.answer)."""
import unittest
from unittest import mock

from taskuary import general, selfclose, terminal, workerstate as ws
from taskuary.store import MemoryStore
from taskuary.testing import Factory


class AskMarker(unittest.TestCase):
    def test_the_ask_marker_parses_question_and_choices(self):
        self.assertEqual(selfclose.ask_marker('I compared them.\n[[TASKUARY-ASK]] Which vendor? | Acme | Globex'),
                         ('I compared them.', 'Which vendor?', ['Acme', 'Globex']))
        self.assertEqual(selfclose.ask_marker('[[TASKUARY-ASK]]: Go ahead?'), ('', 'Go ahead?', []))
        self.assertEqual(selfclose.ask_marker('plain reply'), ('plain reply', None, []))

    def test_the_prompt_line_teaches_the_marker_and_only_for_a_real_blocker(self):
        self.assertIn(selfclose.ASK_MARKER, selfclose.ASK_LINE); self.assertIn('real blocker', selfclose.ASK_LINE)

    def test_the_ask_is_a_question_never_permission_for_what_a_card_asks(self):
        """The agent walk, 2026-11-10: one line said a draft's Send card IS the confirmation, the ask line offered the marker for anything
        the agent "cannot continue without", and a third called the marker the way to "offer choices" - so an ask for leave to send stood
        over the card that already asked it."""
        ask, summary = selfclose.ASK_LINE, selfclose.SUMMARY_LINE
        self.assertIn('a fact or a decision only they can give', ask); self.assertIn("ask for permission to do what a card already asks", ask)
        self.assertNotIn('offer choices', summary)
        # ...said ONCE, by the ask line (the design round, 2026-11-18): the summary line said it a second time in other words
        self.assertIn('(its Send, Post or Approve is that question)', ask); self.assertNotIn('IS the confirmation', summary); self.assertNotIn('shall I send', summary)


class ApiWorkerSignals(unittest.TestCase):
    def setUp(self):
        self.s = MemoryStore(); self.fx = Factory(self.s); self.tid = self.fx.task(title='Compare vendors', kind='general')

    def turn(self, answer, text='compare them'):
        with mock.patch.object(general, '_selected', return_value=('api:test', 'Test', 'm')):
            sess = general.GeneralSession(self.s, self.tid)
        brain = lambda system, user, **kw: answer
        with mock.patch.object(general.llm_mod, 'build_llm', return_value=brain):
            return sess, sess.send_prompt(text)

    def test_a_session_at_rest_does_not_wait_on_him_while_an_input_is_handed_to_it(self):
        """Recorded on the real CLI, 2026-11-15: the agent's turn ended handing a saved sign-in to Taskuary, and for the ~3 s it was typed the
        task was at work by the server's word (general.hand) while the session it sent the page said `waiting` - the header read "agent
        waiting on you" over a chat that said it was working. The session's own word is the task's: an input on its way is no wait on him."""
        sess, _ = self.turn('Signing in now.')
        self.assertTrue(sess.info(details=False)['waiting'])
        general.hand(self.tid)
        try:
            self.assertFalse(sess.info(details=False)['waiting'], 'an input on its way to the agent: at work, as general.working says')
            self.assertTrue(general.working(self.s, self.tid))
        finally: general.hand(self.tid, -1)
        self.assertTrue(sess.info(details=False)['waiting'])

    def test_a_turn_records_turn_end_and_an_ask_records_input_needed(self):
        sess, reply = self.turn('Two options.\n[[TASKUARY-ASK]] Which vendor? | Acme | Globex')
        self.assertNotIn('TASKUARY-ASK', reply)
        st = ws.status(self.s, self.tid)
        self.assertEqual(st['state'], 'input_needed'); self.assertEqual(st['requests'][0]['text'], 'Which vendor?')
        self.assertEqual([e['Kind'] for e in ws.events(self.s, self.tid, sess.sid)], ['working', 'turn_end', 'input_needed'])

    def test_a_question_asked_in_its_own_words_over_a_bare_marker_waits_on_him(self):
        """The walk, 2026-11-21: told to ask in its own words and end with the marker on its own line, the agent did - and the bare marker
        recorded no question, so the header and the rail read "agent done" over a turn that asked him who should get the mail."""
        from taskuary import taskstate
        sess, reply = self.turn('I found two people it could go to.\n\nWho should get it? I recommend Gail.\n[[TASKUARY-ASK]]')
        st = ws.status(self.s, self.tid)
        self.assertEqual([r['text'] for r in st['requests']], ['Who should get it? I recommend Gail.'])
        self.assertEqual(reply.count('Who should get it?'), 1, 'asked once, in its own words')
        self.assertEqual(taskstate.status(self.s, self.s.get_task(self.tid), sess.info(details=False))['key'], 'blocked')

    def test_a_question_stands_past_a_turn_that_did_not_ask_it_again_until_the_agent_takes_it_back(self):
        """Recorded on the real CLI, 2026-11-15: the agent asked which vendor; a later turn said nothing was left on the owner, and the box still
        asked. The question was then retired by that turn's nothing_left - and walk 16 had questions vanish by the same kind of rule. The owner's
        rule (2026-11-24): it stands until he answers it, the task closes, or the agent withdraws it - with the tool it asked with."""
        import json
        from taskuary import agenttools
        sess, _ = self.turn('Two options.\n[[TASKUARY-ASK]] Which vendor?')
        self.assertEqual(ws.status(self.s, self.tid)['state'], 'input_needed')
        summ = lambda left: selfclose.SUMMARY_OPEN + json.dumps({'about': 'the vendors', 'did': 'Noted your answer to Gail', 'on_you': [], 'nothing_left': left}) + selfclose.SUMMARY_CLOSE
        say = lambda words: (mock.patch.object(general.llm_mod, 'build_llm', return_value=lambda system, user, **kw: words), sess)
        with say('Still comparing.' + summ(False))[0]: sess.send_prompt('Gail wrote again', as_owner=False)
        self.assertEqual([r['text'] for r in ws.status(self.s, self.tid)['requests']], ['Which vendor?'], 'a turn with work left still asks it')
        with say('Gail settled it - nothing more is needed here.' + summ(True))[0]: sess.send_prompt('Gail wrote: Acme', as_owner=False)
        self.assertEqual([r['text'] for r in ws.status(self.s, self.tid)['requests']], ['Which vendor?'], 'not asked again is not answered')
        self.assertIn('Withdrawn: Which vendor?', agenttools.call(self.s, self.tid, 'ask_owner', {'withdraw': True}, {}))
        st = ws.status(self.s, self.tid)
        self.assertEqual(st['requests'], []); self.assertNotIn(st['state'], ('input_needed', 'working'))

    def test_the_choices_it_offers_are_its_asks_buttons_on_the_desktop_and_the_phone(self):
        """Walk 13: the agent passed ask_owner its choices and the app wrote them into the answer as "(a / b / c)" - prose he could not press.
        They ride on the recorded ask (a button each, desktop and phone); the answer keeps the question once and never the bracket list."""
        sess, reply = self.turn('Two options.\n[[TASKUARY-ASK]] Which vendor? | Acme | Globex')
        req = ws.asking_of(self.s, sess)
        self.assertEqual((req['text'], req['choices']), ('Which vendor?', ['Acme', 'Globex']))
        self.assertIn('Which vendor?', reply); self.assertNotIn('(Acme / Globex)', reply)
        from taskuary import remote_assistant as ra
        item = {'kind': 'agent', 'lane': 'blocked', 'asking': True, 'tid': self.tid, 'ref': 'TQ-0001', 'title': 'Compare vendors',
                'who': 'general', 'agent': 'general', 'choices': req['choices'], 'questions': [req]}
        self.assertEqual(ra.agent_answers(item), ['Acme', 'Globex'], 'the phone offers the same presses')
        # ...and his press is his answer, heard once, as his next line
        sent = []; sess.send_prompt = lambda t, **kw: sent.append(t)
        from taskuary import terminal as term
        saved = dict(term.SESSIONS); term.SESSIONS.clear(); term.SESSIONS[sess.sid] = sess
        try: out = ws.answer(self.s, self.tid, req['request_id'], 'Globex', 'owner')
        finally: term.SESSIONS.clear(); term.SESSIONS.update(saved)
        self.assertTrue(out['delivered']); self.assertEqual(sent, ['Globex']); self.assertEqual(ws.status(self.s, self.tid)['requests'], [])

    def test_a_long_question_is_never_cut_mid_word(self):
        """Walk 13: a 700-character question stood as "... Can you send th" - a 600-character cap on the ask."""
        q = 'Alex says the quote is 25 seats, but you told me 250 seats are in use. ' * 9 + 'Can you send the invoice?'
        sess, reply = self.turn('I checked the sheet.\n[[TASKUARY-ASK]] ' + q + ' | Attach it | Ask Alex')
        self.assertEqual(ws.asking_of(self.s, sess)['text'], q)
        self.assertIn('Can you send the invoice?', reply)

    def test_the_question_stays_in_the_answer_the_chat_shows(self):
        """The marker line IS the question; cutting the marker cut the question, and with no question card in the chat any
        more the owner read "it needs your yes first" and never what to say yes to (walk 2026-10-21)."""
        _, reply = self.turn('Prepared the checklist; the laptop needs your yes first.\n'
                             '[[TASKUARY-ASK]] The standard laptop is $1,850 - order it? | Order it | Use a spare')
        self.assertNotIn('TASKUARY-ASK', reply)
        self.assertIn('The standard laptop is $1,850 - order it?', reply); self.assertNotIn('(Order it / Use a spare)', reply)
        filed = [c['Body'] for c in self.s.list_comments(self.tid) if c['ActorType'] == general.ASSISTANT_TYPE][-1]
        self.assertTrue(filed.startswith('Prepared the checklist') and 'order it?' in filed)
        # ...said once: a question already written above its marker is not repeated
        _, again = self.turn('Which vendor? Acme is cheaper.\n[[TASKUARY-ASK]] Which vendor?')
        self.assertEqual(again.count('Which vendor?'), 1)

    def test_a_short_answer_that_says_done_closes_its_task(self):
        """A 188-character W-9 reply with [[TASKUARY-DONE]] was refused as "barely printed anything" - a terminal's gate - and
        the refusal was dropped, so the task sat in progress under an answer saying it was finished (walk 2026-10-21)."""
        self.fx.message(task_id=self.tid, subject='W-9 please')
        with mock.patch.object(general, '_selected', return_value=('api:test', 'Test', 'm')):
            sess = general.GeneralSession(self.s, self.tid)
        self.assertIs(selfclose.blocked(self.s, self.tid, sess), '')
        sess.n = 10
        self.assertEqual(selfclose.blocked(self.s, self.tid, sess), '', 'printed length is a terminal gate, not an answer\'s')

    def test_a_plain_reply_ends_the_turn_and_is_no_hand_raise(self):
        sess, _ = self.turn('Acme is cheaper; Globex ships faster.')
        st = ws.status(self.s, self.tid)
        self.assertEqual(st['requests'], []); self.assertNotEqual(st['state'], 'input_needed')
        self.assertEqual([e['Kind'] for e in ws.events(self.s, self.tid, sess.sid)], ['working', 'turn_end'])
        self.assertIsNone(ws.waiting_of(self.s, sess), 'a turn that ended says nothing about the owner')
        # ...and an API conversation parks at no prompt, so the silence resolves to no hand raise (PW-226)
        self.assertIs(terminal.worker_fields(self.s, sess)['waiting'], False)

    def test_the_owners_answer_resumes_the_same_session(self):
        sess, _ = self.turn('[[TASKUARY-ASK]] Which vendor? | Acme | Globex')
        sent = []; sess.send_prompt = lambda t, **kw: sent.append(t)
        from taskuary import terminal as term
        saved = dict(term.SESSIONS); term.SESSIONS.clear(); term.SESSIONS[sess.sid] = sess
        try: out = ws.answer_open(self.s, self.tid, 'Acme', 'owner')
        finally: term.SESSIONS.clear(); term.SESSIONS.update(saved)
        self.assertTrue(out['delivered']); self.assertEqual(sent, ['Acme']); self.assertEqual(out['path'], 'api')
        self.assertEqual(ws.status(self.s, self.tid)['requests'], [])

    def test_the_system_prompt_teaches_the_marker(self):
        seen = {}
        with mock.patch.object(general, '_selected', return_value=('api:test', 'Test', 'm')):
            sess = general.GeneralSession(self.s, self.tid)
        def brain(system, user, **kw): seen['system'] = system; return 'ok'
        with mock.patch.object(general.llm_mod, 'build_llm', return_value=brain): sess.send_prompt('hi')
        self.assertIn(selfclose.ASK_MARKER, seen['system'])
        self.assertNotIn('choice', selfclose.ASK_LINE.lower(), 'the agent is no longer invited to offer its own options')

    def test_a_turn_that_died_is_not_a_turn_still_working(self):
        """A turn whose brain raised left `working` as the last word anybody had. The task wore
        "Agent is working" for thirteen hours over a CLI that had exited in two seconds, and the
        chat showed the question with no answer and no reason (TQ-0496, 2026-09-11)."""
        with mock.patch.object(general, '_selected', return_value=('cli:codex', 'Codex', '')):
            sess = general.GeneralSession(self.s, self.tid)
        def boom(system, user, **kw): raise RuntimeError('codex exit 1: that model needs a newer Codex')
        with mock.patch.object(general.llm_mod, 'build_llm', return_value=boom), \
                self.assertRaises(RuntimeError):
            sess.send_prompt('clock me in at nine')
        evs = ws.events(self.s, self.tid, sess.sid)
        self.assertEqual([e['Kind'] for e in evs], ['working', 'failed'])
        self.assertEqual(ws.status(self.s, self.tid)['state'], 'failed')
        self.assertIn('newer Codex', evs[-1]['Text'])       # the reason travels with the event
