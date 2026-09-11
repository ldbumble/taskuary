"""A set-up walk-through actually WALKS: it starts, it drives the browser, and it reads the right map.

Asked in the chat to log into a payroll portal and clock in every morning, the setup card opened
TQ-0496 and said "open it when you want to start" - and nothing started. A task nobody started is
not a walk-through (the owner, 2026-09-10: "it's supposed to walk me through this?").

Three things are pinned here: the card's post opens a live session with an unattributed opening
turn; a walk prefers the codex CLI, because a walk needs a keyboard on a real browser and codex's
own config names the model for that; and the shipped taskuary-setup SKILL rides only when the job
IS configuring Taskuary - it is the wrong map for somebody else's portal.
"""
import json, unittest
from unittest import mock

from fastapi.testclient import TestClient

from taskuary import concierge, general, server, terminal
from taskuary.store import MemoryStore

ONE_CLI = [{'pick': 'cli:coder', 'type': 'cli', 'cmd': 'claude', 'label': 'Claude Code (your CLI)', 'model': ''}]


def store():
    s = MemoryStore()
    s.upsert_agent('coder', 'coding', 'cli', '{}')
    return s


class FakeSession:
    def __init__(self, tid): self.sid, self.task_id, self.said = 's-walk', tid, []
    def send_prompt(self, text, *a, **k): self.said.append((text, k)); return 'ok'


def post(s, text, sessions=None, external=False, providers=ONE_CLI, start=None):
    """The setup card's own request, with the walk's moving parts held still."""
    seen = sessions if sessions is not None else {}
    start = start or (lambda st, tid, *a, **k: seen.setdefault('s', FakeSession(tid)))
    with mock.patch.object(server, 'store', s), \
         mock.patch.object(general, 'start_session', side_effect=start) as started, \
         mock.patch.object(general, 'provider_options', return_value=providers), \
         mock.patch.object(concierge, 'walk_is_external', return_value=external):
        r = TestClient(server.app).post('/api/concierge/setup', json={'text': text})
    return r, started


class WalkStartsTests(unittest.TestCase):
    def setUp(self): terminal.SESSIONS.clear()
    def tearDown(self): terminal.SESSIONS.clear()

    def test_the_setup_card_opens_a_live_walk_and_leaves_no_cold_task(self):
        s = store()
        r, started = post(s, 'use browser control to log into adp and clock me in around 9am every day')
        out = r.json()
        self.assertEqual(out['ref'][:3], 'TQ-')
        self.assertTrue(started.called, 'the walk starts with the card, not with a later click')
        self.assertEqual(started.call_args.args[1], out['taskId'])
        self.assertEqual(s.get_task(out['taskId'])['Kind'], 'general')
        self.assertIn('needs:browser', s.get_task(out['taskId'])['Tags'])

    def test_the_walk_opens_with_an_instruction_that_is_never_the_owners_words(self):
        s, sessions = store(), {}
        r, _ = post(s, 'set up a weekly refunds report', sessions)
        text, kw = sessions['s'].said[0]
        self.assertFalse(kw.get('as_owner', True), 'the opening turn is an instruction, not the owner speaking')
        self.assertIn('walk', text.lower())
        # and the owner is not quoted twice: their ask is the one human comment on the task
        human = [c for c in s.list_comments(r.json()['taskId']) if c['ActorType'] == 'human']
        self.assertEqual(len(human), 1)
        self.assertIn('refunds report', human[0]['Body'])

    def test_a_walk_over_the_owners_own_systems_is_tagged_so_the_prompt_can_read_it(self):
        s = store()
        r, _ = post(s, 'log into adp and clock me in every morning', external=True)
        self.assertTrue(s.task_has_tag(r.json()['taskId'], general.SETUP_EXTERNAL))

    def test_no_ai_configured_starts_nothing_rather_than_parking_a_dead_session(self):
        s = store()
        boom = mock.Mock(side_effect=AssertionError('must not start a session with no brain'))
        r, _ = post(s, 'set up a report', providers=[], start=boom)
        self.assertEqual(r.status_code, 200)
        self.assertFalse(boom.called)

    def test_a_walk_that_cannot_start_costs_the_owner_a_sentence_not_the_task(self):
        s = store()
        r, _ = post(s, 'set up a report', start=mock.Mock(side_effect=RuntimeError('no brain today')))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(s.get_task(r.json()['taskId'])['Status'], 'open')

    def test_an_empty_ask_is_still_refused(self):
        with mock.patch.object(server, 'store', store()):
            self.assertEqual(TestClient(server.app).post('/api/concierge/setup', json={'text': ' '}).status_code, 422)


class WalkBrainTests(unittest.TestCase):
    def test_a_walk_prefers_codex_because_it_is_the_one_that_drives_the_browser(self):
        s = store()
        s.upsert_agent('codex', 'coding', 'cli', json.dumps({'cmd': 'codex'}))
        self.assertEqual(general.walk_pick(s), 'cli:codex')

    def test_with_no_codex_the_first_cli_still_drives_it(self):
        self.assertEqual(general.walk_pick(store()), 'cli:coder')

    def test_with_no_cli_at_all_it_names_nobody_rather_than_an_api_brain_that_cannot_click(self):
        self.assertEqual(general.walk_pick(MemoryStore()), '')

    def test_no_model_is_named_here_so_codex_own_config_keeps_deciding(self):
        # the owner wants gpt-6-astra for browser work; that lives in ~/.codex/config.toml. Naming
        # it in the code would freeze it, so walk_pick returns a PICK and never a model.
        self.assertNotIn('gpt-', ' '.join(str(c) for c in general.walk_pick.__code__.co_consts))

    def test_provider_options_says_which_cli_each_choice_actually_runs(self):
        s = MemoryStore()
        s.upsert_agent('coder', 'coding', 'cli', json.dumps({'cmd': 'claude'}))
        s.upsert_agent('codex', 'coding', 'cli', json.dumps({'cmd': 'codex'}))
        cmds = {o['pick']: o.get('cmd') for o in general.provider_options(s) if o['type'] == 'cli'}
        self.assertEqual(cmds, {'cli:coder': 'claude', 'cli:codex': 'codex'})


class WalkProcedureTests(unittest.TestCase):
    def _walk(self, text='walk me through it', external=False):
        s = MemoryStore()
        tid = s.create_task({'Title': 'A walk', 'Summary': text, 'Kind': 'general', 'Status': 'open',
                             'Source': 'assistant', 'SourceRef': general.SETUP_REF}, 'owner')
        if external: s.tag_task(tid, general.SETUP_EXTERNAL, actor='owner')
        return general._prompt(s, tid)[0]

    def test_a_taskuary_configuration_walk_keeps_the_shipped_procedure(self):
        self.assertIn('# Taskuary setup walkthrough', self._walk())

    def test_a_walk_over_the_owners_own_systems_drops_it_and_says_what_the_job_is(self):
        p = self._walk('log into adp and clock me in', external=True)
        self.assertNotIn('# Taskuary setup walkthrough', p)
        self.assertIn('PROCEDURE FOR THIS JOB', p)          # still given a shape, just not that one
        self.assertIn('not about configuring Taskuary', p)

    def test_the_sort_is_the_models_reading_and_an_unsure_answer_keeps_the_skill(self):
        s = MemoryStore()
        outside = lambda system, user, **k: json.dumps({'taskuary': False})
        inside = lambda system, user, **k: json.dumps({'taskuary': True})
        junk = lambda system, user, **k: 'I could not say'
        blew_up = mock.Mock(side_effect=RuntimeError('the CLI died'))
        self.assertTrue(concierge.walk_is_external(s, 'clock me into adp every morning', llm=outside))
        self.assertFalse(concierge.walk_is_external(s, 'connect my outlook', llm=inside))
        self.assertFalse(concierge.walk_is_external(s, 'anything', llm=junk))
        self.assertFalse(concierge.walk_is_external(s, 'anything', llm=blew_up))
        self.assertFalse(concierge.walk_is_external(s, 'anything'))          # no brain: the skill stays

    def test_the_sort_reads_intent_and_carries_no_word_list(self):
        # standing rule: never route on regex or keywords - the model returns the verdict, code validates
        self.assertNotIn('adp', concierge.WALK_SORT.lower())
        self.assertNotIn('re.search', concierge.WALK_SORT)


if __name__ == '__main__':
    unittest.main()
