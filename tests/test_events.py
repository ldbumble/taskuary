"""WHAT AN AGENT IS TOLD BETWEEN TURNS IS THE EVENTS SINCE ITS CURSOR (events.py; design review change 2, 2026-11-23).

Each turn of a conversation that goes on gets what happened since its cursor - a message, his line, a card's new state - each once, in one
fixed shape, and the cursor moves. Driven down to the brain (a stub that keeps what it was handed), so each test reads what the model got.
Invented people only."""
import json, unittest
from unittest import mock

from taskuary import continuity, events, general, llm as llm_mod
from taskuary.store import MemoryStore


class Brain:
    "The model: keeps every turn it is handed, answers in one line."
    def __init__(self): self.calls = []
    down = False
    def __call__(self, system, user, **k):
        if self.down: raise RuntimeError('no answer')
        self.calls.append(user); return 'Done.'
    @property
    def turn(self): return self.calls[-1]


def store():
    s = MemoryStore()
    s.set_setting('owner_email', 'alex@northwind.example', 't')
    s.upsert_agent('claude', 'general', 'cli', json.dumps({'cmd': 'claude'}))
    return s


def mail(s, tid, n, body, conv='conv-pilot', who=('Gail Moreno', 'gail@vendor.example')):
    return s.add_message({'TaskId': tid, 'ExternalId': f'x{n}', 'ConversationId': conv, 'Channel': 'email', 'Subject': 'pilot plan',
                          'FromName': who[0], 'FromEmail': who[1], 'SentAt': f'2026-11-23 09:0{n}', 'BodyText': body, 'Status': 'routed'})


def task(s):
    "A task its agent has worked once on Claude Code, its conversation kept under the id its CLI gave it - and its cursor past all of it."
    tid = s.create_task({'Title': 'Pilot plan', 'Kind': 'general', 'Status': 'in_progress'}, 't')
    s._exec('UPDATE task SET TrustedThrough=? WHERE TaskId=?', (10 ** 9, tid))
    mail(s, tid, 1, 'Can you draft a pilot plan for the new box?')
    s.add_comment(tid, 'owner', general.USER_TYPE, 'Draft it, please.')
    s.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, 'Drafted the reply - it waits for your Send.')
    s.save_session(tid, 'cli:claude', '', 'cli-conv-1', continuity.context_key(s, 'cli:claude', ''))
    events.commit(s, tid, events.top(s, tid))
    return tid


class Events(unittest.TestCase):
    def setUp(self):
        self.brain = Brain()
        for p in [mock.patch.object(llm_mod, 'build_llm', return_value=self.brain),
                  mock.patch.object(general, 'provider_options', return_value=[{'pick': 'cli:claude', 'type': 'cli', 'label': 'Claude Code', 'model': ''}]),
                  mock.patch('taskuary.agents.ready_brains', return_value=['claude']),
                  mock.patch.object(general.GeneralSession, '_file', return_value='filed')]:
            p.start(); self.addCleanup(p.stop)

    def say(self, s, tid, line, kept=True):
        ses = general.session_for(tid) or general.start_session(s, tid)
        self.addCleanup(lambda: (general.session_for(tid) and general.session_for(tid).close(learn=False, report=False), general.drop_session(tid)))
        if kept: self.assertEqual(ses.cli_sid, 'cli-conv-1')          # ...a conversation that goes on: the turn is all it is told
        ses.send_prompt(line)
        return self.brain.turn

    def test_a_turn_after_a_press_gets_exactly_that_event_once(self):
        s = store(); tid = task(s)
        rid = s.add_review({'TaskId': tid, 'Kind': 'draft_reply', 'Status': 'pending', 'DraftText': 'Hi Gail - the plan is attached.'})
        events.commit(s, tid, events.top(s, tid))            # ...the turn that raised it ended: the card is that call's own answer
        s.decide_review(rid, 'approved', 'Hi Gail - the plan is attached.', 'owner')
        turn = self.say(s, tid, 'what is left?')
        self.assertEqual(turn.count(f'Card rv{rid}'), 1)
        self.assertIn('he approved it', turn)
        self.assertIn('what is left?', turn)
        self.assertNotIn(f'rv{rid}', self.say(s, tid, 'thanks'))     # ...and the turn after hears it no more

    def test_after_he_answers_a_question_nothing_says_it_still_waits(self):
        s = store(); tid = task(s)
        s.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, 'Which site should the pilot start at?')
        first = self.say(s, tid, 'Start at the Riverside site.')
        self.assertIn('Start at the Riverside site.', first)
        again = self.say(s, tid, 'And keep it to two weeks.')
        for t in (first, again): self.assertNotIn('STILL WAITING', t.upper().replace('STILL WAITS', 'STILL WAITING'))
        self.assertNotIn('Riverside', again)                   # ...his answer was told once, in its own turn

    def test_a_resumed_session_gets_only_the_events_since_its_cursor(self):
        s = store(); tid = task(s)
        self.say(s, tid, 'Go ahead.')
        general.session_for(tid).close(learn=False, report=False); general.drop_session(tid)
        mail(s, tid, 2, 'Also price the Riverside site by Friday.')
        turn = self.say(s, tid, 'Look at her new note.')           # ...a new session on the same kept conversation
        self.assertIn('Riverside site by Friday', turn)
        for old in ('Can you draft a pilot plan', 'Go ahead.'): self.assertNotIn(old, turn)

    def test_two_mails_in_one_poll_are_two_events(self):
        s = store(); tid = task(s)
        a, b = mail(s, tid, 2, 'First: the budget is fixed.'), mail(s, tid, 3, 'Second: Erin Blake joins the pilot.', who=('Erin Blake', 'erin@vendor.example'))
        got = [e for e in events.pending(s, tid) if e['kind'] == 'message']
        self.assertEqual([e['mid'] for e in got], [a, b])
        turn = self.say(s, tid, 'Fold both in.')
        self.assertIn(f'(m{a}', turn); self.assertIn(f'(m{b}', turn)
        self.assertLess(turn.index('budget is fixed'), turn.index('Erin Blake joins'))

    def test_nothing_is_told_twice(self):
        s = store(); tid = task(s)
        mail(s, tid, 2, 'Budget is fixed at ten thousand.')
        self.say(s, tid, 'Noted, carry on.')
        rid = s.add_review({'TaskId': tid, 'Kind': 'draft_reply', 'Status': 'pending', 'DraftText': 'Hi Gail - noted.'})
        s.decide_review(rid, 'rejected', None, 'owner')
        self.say(s, tid, 'Why that draft?')
        mail(s, tid, 3, 'Erin Blake joins on Monday.', who=('Erin Blake', 'erin@vendor.example'))
        self.say(s, tid, 'Anything new?')
        for fact in ('Budget is fixed', 'Noted, carry on.', 'he turned it down', 'Why that draft?', 'Erin Blake joins', 'Anything new?'):
            self.assertEqual(sum(fact in t for t in self.brain.calls), 1, fact)

    def test_a_cut_turn_leaves_its_events_for_the_next(self):
        "A turn whose AI never answered moved no cursor: the try after it is told the same events, once."
        s = store(); tid = task(s)
        mail(s, tid, 2, 'Can we start Monday?')
        self.brain.down = True
        with self.assertRaises(Exception): self.say(s, tid, 'Answer her.')
        self.brain.down = False
        if (g := general.session_for(tid)): g.close(learn=False, report=False)
        general.drop_session(tid)
        turn = self.say(s, tid, 'Try again.', kept=False)            # ...said afresh: its brief carries the mail, once
        self.assertEqual(turn.count('Can we start Monday?'), 1)

    def test_his_own_reply_on_the_thread_reaches_the_other_task_on_it(self):
        s = store(); tid = task(s)
        other = s.create_task({'Title': 'Pilot budget', 'Kind': 'general', 'Status': 'in_progress'}, 't')
        mail(s, other, 4, 'What is the budget?')
        mid = s.add_message({'ExternalId': 'own-1', 'ConversationId': 'conv-pilot', 'Channel': 'email', 'Direction': 'out', 'Status': 'context',
                             'FromEmail': 'alex@northwind.example', 'BodyText': 'Ten thousand, fixed.', 'SentAt': '2026-11-23 09:09'})
        got = [e for e in events.pending(s, tid) if e['kind'] == 'message']
        self.assertEqual([(e['mid'], e['own']) for e in got], [(mid, True)])
        self.assertIn("The owner's own message on the thread", events.render(got))
