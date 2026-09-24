"""A set-up walk-through actually WALKS: it starts, it drives the browser, and it reads the right map.

Asked in the chat to log into a payroll portal and clock in every morning, the setup card opened
TQ-0496 and said "open it when you want to start" - and nothing started. A task nobody started is
not a walk-through (the owner, 2026-09-10: "it's supposed to walk me through this?").

Three things are pinned here: the card's post opens a live session with an unattributed opening
turn; a walk speaks with the Assistant's own brain, like every other assistant action; and the shipped taskuary-setup SKILL rides only when the job
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
        # and the owner is not quoted twice: their ask is said once, and it is their own turn
        said = [c for c in s.list_comments(r.json()['taskId']) if 'refunds report' in (c['Body'] or '')]
        self.assertEqual(len(said), 1)
        self.assertEqual(said[0]['ActorType'], general.USER_TYPE)

    def test_the_walk_opens_with_the_owners_own_words_on_screen(self):
        # The conversation showed the ANSWER with no question above it: the ask was filed as an
        # ordinary human comment, which the chat does not render, so a walk that was working looked
        # like a walk that had never started (the owner, 2026-09-14).
        s = store()
        r, _ = post(s, 'log into adp and clock me in every morning')
        first = general.history(s, r.json()['taskId'])[0]
        self.assertEqual(first['role'], 'user')
        self.assertIn('clock me in', first['content'][0]['text'])

    def test_a_pane_that_opens_before_the_session_exists_is_told_the_walk_is_starting(self):
        # The pane loads its snapshot the moment the card posts - a second or two BEFORE the
        # background walk has a session - and it only polls while something says it is working.
        s, seen = store(), {}
        def start(st, tid, *a, **k):
            seen['during'] = server._assistant_payload(tid)
            return FakeSession(tid)
        r, _ = post(s, 'set up a weekly refunds report', start=start)
        self.assertTrue(seen['during']['starting'], 'a walk with no session yet is still work in flight')
        self.assertIsNone(seen['during']['session'])
        with mock.patch.object(server, 'store', s), mock.patch.object(general, 'provider_options', return_value=ONE_CLI):
            after = server._assistant_payload(r.json()['taskId'])
        self.assertFalse(after['starting'], 'and it is over once the walk has spoken')

    def test_a_walk_that_could_not_start_says_so_where_the_owner_is_looking(self):
        s = store()
        r, _ = post(s, 'set up a report', start=mock.Mock(side_effect=RuntimeError('no brain today')))
        last = general.history(s, r.json()['taskId'])[-1]
        self.assertEqual(last['role'], 'assistant')
        self.assertIn('could not start', last['content'][0]['text'])

    def test_with_no_ai_at_all_the_conversation_still_says_why_nothing_happened(self):
        s = store()
        r, _ = post(s, 'set up a report', providers=[], start=mock.Mock())
        last = general.history(s, r.json()['taskId'])[-1]
        self.assertEqual(last['role'], 'assistant')
        self.assertIn('AI', last['content'][0]['text'])

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


SETUP = {'SourceRef': general.SETUP_REF, 'Kind': 'general'}
BROWSER = {'Kind': 'general', 'Tags': 'needs:browser'}


def api_brain(s):
    row = s.get_connector_by_type('openai')
    s.save_connector({'ConnectorId': row['ConnectorId'], 'Active': 1, 'Secret': 'sk-test',
                      'Name': 'Work model', 'ConfigJson': '{"model":"gpt-test"}'}, 'owner')
    return f"connector:{row['ConnectorId']}"


class WalkBrainTests(unittest.TestCase):
    """A walk speaks with the Assistant's own brain, like every other assistant action (the owner,
    2026-09-24: "of course use default, so if ai api then use that"). It used to prefer codex BY NAME,
    which nobody had chosen and no setting could move."""

    def test_a_walk_takes_the_assistants_brain_even_an_api_one(self):
        s = store(); s.upsert_agent('codex', 'coding', 'cli', json.dumps({'cmd': 'codex'}))
        pick = api_brain(s); s.set_setting(concierge.AI_KEY, pick, 'owner')
        self.assertEqual(general.walk_pick(s, SETUP), pick)
        self.assertEqual(general.walk_pick(s, SETUP), concierge.pick(s))

    def test_with_nothing_chosen_it_is_the_default_cli_not_codex(self):
        s = store(); s.upsert_agent('codex', 'coding', 'cli', json.dumps({'cmd': 'codex'}))
        self.assertEqual(general.walk_pick(s, SETUP), 'cli:coder')

    def test_a_browser_task_still_needs_hands_so_an_api_choice_falls_to_the_default_cli(self):
        # a repeat workflow on the API brain answered "opening the secure area cannot be done from
        # here" (2026-09-15): only a CLI can run agent-browser
        s = store(); s.upsert_agent('codex', 'coding', 'cli', json.dumps({'cmd': 'codex'}))
        s.set_setting(concierge.AI_KEY, api_brain(s), 'owner')
        with mock.patch.object(general, '_browser_task', return_value=True):
            self.assertEqual(general.walk_pick(s, BROWSER), 'cli:coder')
        s.set_setting(concierge.AI_KEY, 'cli:codex', 'owner')        # ...and a CLI choice is kept
        with mock.patch.object(general, '_browser_task', return_value=True):
            self.assertEqual(general.walk_pick(s, BROWSER), 'cli:codex')

    def test_the_picker_names_the_walks_own_brain_before_a_session_exists(self):
        # default_pick is documented as "the SAME reading start_session makes"
        s = store(); s.set_setting(concierge.AI_KEY, api_brain(s), 'owner')
        self.assertEqual(general.default_pick(s, SETUP), general.walk_pick(s, SETUP))

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
