"""A general agent's next turn carries the newest message triage joined to its task (the owner, 2026-11-03: "I don't see it gets the
most recent question. coding does, but does general agent do that").

Each door is driven down to the brain - a stub that keeps what it was handed - so the test reads what the model actually got: a STOPPED
conversation resumed on its own CLI (carry-on), a LIVE one (pass-in), a QUICK one, and a REPLY task an agent takes up. The stopped one
was the gap: its CLI was handed only "The owner chose Resume", the new ask riding behind it in the system prompt and nowhere on the task.
"""
import json, unittest
from unittest import mock

from taskuary import continuity, general, ingest, llm as llm_mod, quickwork, senders
from taskuary.ingest import ingest_message
from taskuary.store import MemoryStore

ASK = 'Can you also price the Riverside site the same way by Friday?'
AGAIN = dict(external_id='x2', body=ASK, sent_at='2026-11-03 10:00')


def mail(**kw):
    return {'external_id': 'x1', 'channel': 'email', 'subject': 'pilot plan', 'body': 'Can you draft a pilot plan for the new box?',
            'from_email': 'gail@northwind.example', 'from_name': 'Gail Moreno', 'conversation_id': 'AAQk-pilot',
            'sent_at': '2026-11-02 18:00', 'source_name': 'alex@northwind.example', **kw}


class Brain:
    "The model: keeps every (system, user) it is handed, answers in one line."
    def __init__(self): self.calls = []
    def __call__(self, system, user, **k): self.calls.append((system, user)); return 'Priced the Riverside site.'
    @property
    def turn(self): return self.calls[-1][1]


def store():
    s = MemoryStore()
    s.set_setting('owner_email', 'alex@northwind.example', 't')
    s.upsert_agent('claude', 'general', 'cli', json.dumps({'cmd': 'claude'}))
    return s


def ingested(s, m, intent='task'):
    with mock.patch('taskuary.ingest._spawn') as spawn, mock.patch.object(senders, 'wrote_to', return_value=True), \
         mock.patch.object(general, 'provider_options', return_value=[{'pick': 'cli:claude', 'type': 'cli'}]):
        out = ingest_message(s, m, llm=lambda sy, u, **k: json.dumps({'intent': intent, 'kind': 'general', 'why': 'w', 'asks_owner': True}))
    return out, spawn.call_args_list


def worked(s, resumable=True):
    "A general task its assistant worked on Claude Code and finished - its conversation kept under the id its CLI gave it."
    tid = ingested(s, mail())[0]['task_id']
    s.add_comment(tid, general.BRIEF_ACTOR, general.USER_TYPE, 'Can you draft a pilot plan for the new box?')
    s.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, 'Wrote the pilot plan.')
    s._exec("UPDATE comment SET CreatedAt='2026-11-02 18:05' WHERE TaskId=?", (tid,))
    if resumable: s.save_session(tid, 'cli:claude', '', 'cli-conv-1', continuity.context_key(s, 'cli:claude', ''))
    s.update_task(tid, {'Status': 'done'}, 't')
    return tid


def ended(tid):
    """Close the task's conversation and forget it: a closed session left in terminal.SESSIONS is still the task's session to
    terminal.session_for, and the next file's task 1 (test_no_ai_no_start) read it as one started with no AI."""
    if (g := general.session_for(tid)): g.close(learn=False, report=False)
    general.drop_session(tid)


def before_first_turn(s, tid):
    "The first mail came, and joined the task, before the first turn (worked() dates the turns 2026-11-02)."
    for t in ('message', 'route'): s._exec(f"UPDATE {t} SET CreatedAt='2026-11-02 18:01' WHERE TaskId=?", (tid,))


class NextTurn(unittest.TestCase):
    def setUp(self):
        self.brain, own = Brain(), general.start_session      # the router's start is a process boundary in tests: the same start, as the owner's
        for p in [mock.patch.object(llm_mod, 'build_llm', return_value=self.brain),
                  mock.patch.object(general, 'provider_options', return_value=[{'pick': 'cli:claude', 'type': 'cli', 'label': 'Claude Code', 'model': ''}]),
                  mock.patch('taskuary.agents.ready_brains', return_value=['claude']),
                  mock.patch.object(general.GeneralSession, '_file', return_value='filed'),
                  mock.patch.object(general, 'start_session', lambda st, tid, **k: own(st, tid, **{**k, 'actor': 'owner'}))]:
            p.start(); self.addCleanup(p.stop)
        self.addCleanup(general.OPENING.clear)       # a carry-on marks its task opening until its turn runs; a test that only routes leaves it

    def carried_on(self, s, tid):
        _out, spawned = ingested(s, mail(**AGAIN))
        (fn, *args), _kw = spawned[-1]
        self.assertEqual(fn.__name__, '_continue_general')
        fn(*args)
        self.addCleanup(ended, tid)

    def test_a_stopped_conversation_resumed_on_its_cli_is_handed_the_new_ask_as_its_turn(self):
        s = store(); tid = worked(s)
        self.carried_on(s, tid)
        self.assertEqual(general.session_for(tid).cli_sid, 'cli-conv-1')        # its own CLI conversation, so the turn is all it is told
        self.assertIn(ASK, self.brain.turn)
        self.assertLess(self.brain.turn.index(ASK), self.brain.turn.index(continuity.RESUME_PROMPT))   # the news leads, Resume's words follow
        self.assertNotIn('the owner says', self.brain.turn)                    # Taskuary's words, never put in the owner's mouth
        brief = [c for c in s.list_comments(tid) if general.is_brief(c)][-1]
        self.assertIn(ASK, brief['Body'])                                       # ...and the chat shows the line it was handed

    def test_a_stopped_conversation_with_no_cli_to_resume_reads_it_too(self):
        s = store(); tid = worked(s, resumable=False)
        self.carried_on(s, tid)
        self.assertIn(ASK, self.brain.turn)

    def test_a_line_the_news_read_missed_is_still_the_turn(self):
        s = store(); tid = worked(s)
        _out, spawned = ingested(s, mail(**AGAIN))
        (_fn, st, t, msg, mid), _kw = spawned[-1]
        with mock.patch.object(continuity, 'mail_since', return_value=[]):     # its last turn stamped after the line came in
            turn = ingest.carry_on_turn(st, t, msg, mid)
        self.assertIn(ASK, turn)

    def test_a_live_conversation_is_handed_the_new_ask(self):
        s = store(); tid = worked(s)
        general.start_session(s, tid, actor='router')
        self.addCleanup(ended, tid)
        ingest._pass_general(s, tid, {**mail(**AGAIN), 'message_id': 9})
        self.assertIn(ASK, self.brain.turn)
        self.assertTrue(any(general.is_brief(c) and ASK in c['Body'] for c in s.list_comments(tid)))

    def test_the_pane_shows_the_new_mail_in_its_senders_words(self):
        "The overnight run, 2026-11-03: the second mail of a thread was readable only inside the folded 'Taskuary's instructions'."
        s = store(); tid = worked(s)
        before_first_turn(s, tid)
        self.carried_on(s, tid)
        shown = general.shown_history(s, tid)
        first, carried = [m for m in shown if m.get('brief')][0], [m for m in shown if m.get('brief')][-1]
        self.assertNotIn('mail', first)                                         # the opening brief's mail is Came from's
        self.assertEqual([(x['who'], x['words']) for x in carried['mail']], [('Gail Moreno', ASK)])
        self.assertEqual([m['content'] for m in shown], [m['content'] for m in general.history(s, tid)])      # the turns themselves unchanged

    def test_a_mail_read_in_while_the_agent_worked_shows_on_the_turn_it_joined(self):
        "Stored at 18:03, mid-turn, it waited for triage and was put on the task after the 18:05 answer - the turn it carried on is its."
        s = store(); tid = worked(s)
        before_first_turn(s, tid)
        self.carried_on(s, tid)
        s._exec("UPDATE message SET CreatedAt='2026-11-02 18:03' WHERE TaskId=? AND BodyText=?", (tid, ASK))
        self.assertEqual([x['words'] for x in general.shown_history(s, tid)[-1]['mail']], [ASK])

    def test_the_live_pane_shows_the_passed_in_mail_too(self):
        s = store(); tid = worked(s)
        general.start_session(s, tid, actor='router')
        self.addCleanup(ended, tid)
        ingest._pass_general(s, tid, {**mail(**AGAIN), 'message_id': 9})
        self.assertEqual([x['who'] for x in general.shown_history(s, tid)[-1]['mail']], ['Gail Moreno'])

    def test_a_quick_conversation_is_asked_the_new_ask(self):
        s = store(); tid = worked(s)
        asked = []
        with mock.patch.object(quickwork, '_call', side_effect=lambda st, t, q, steps: (asked.append(q), (None, 'stub'))[1]), \
             mock.patch.object(quickwork, 'escalate'):
            quickwork.start(s, tid, ingest._pass_turn(mail(**AGAIN)))
        self.assertIn(ASK, asked[0])

    def test_a_reply_task_agent_reads_the_new_ask_among_its_sources(self):
        s = store()
        tid = ingested(s, mail(), intent='reply_only')[0]['task_id']
        self.assertEqual(s.get_task(tid)['Kind'], 'reply')
        _out, spawned = ingested(s, mail(**AGAIN))
        self.assertIn('_auto_general', [c[0][0].__name__ for c in spawned])     # agent_on_reply starts a fresh conversation...
        with mock.patch.object(ingest, '_reads_quick', return_value=False): ingest._auto_general(s, tid)
        self.addCleanup(ended, tid)
        self.assertIn(ASK, self.brain.turn)                                     # ...whose source material holds the newest message


if __name__ == '__main__': unittest.main()
