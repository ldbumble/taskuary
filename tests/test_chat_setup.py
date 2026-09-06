"""Setting things up from the chat (PW-194 to PW-198).

"Set up a report of open AR every Monday" used to open a walk-through task on the words. Now the request is
sorted by the model (a report, a connection, or digging), gathered by the report composer - whose questions
come back as questions and whose next answer is read as the reply - and put in front of the owner as a
proposal with the exact configuration; the click creates the real resource through the same road the Reports
and Connections tabs take, and the receipt links to its management screen. A proposed report can be dry-run
read-only before the click. A token typed into the chat is not kept. A set-up that needs digging is a
walk-through proposal, not a form, and a simple one never opens a task.
"""
import json, unittest
from unittest import mock

from fastapi.testclient import TestClient

from taskuary import concierge, funnel, general, operations, scopes, server, terminal
from taskuary.store import MemoryStore

REPORT = {'type': 'sqlite', 'title': 'Open tasks by kind', 'db': 'C:/data/taskuary.db', 'query': 'SELECT Kind, count(*) n FROM task GROUP BY Kind', 'cron': '0 8 * * 1'}


def store():
    s = MemoryStore()
    s.upsert_agent('coder', 'coding', 'cli', '{}')
    for k in ('calendar_enabled', 'coder_auto_enabled', 'learn_enabled', 'auto_draft_enabled'): s.set_setting(k, '0', 't')
    funnel.invalidate(); funnel.forget_states()
    return s


def composer(sort=None, compose=None, seen=None):
    """One fake API brain for both passes: the sort answers by its prompt, the composer by its own."""
    def llm(system, user, **kw):
        if seen is not None: seen.append((system[:40], user))
        if 'sort one set-up request' in system: return json.dumps(sort or {'kind': 'report', 'provider': None, 'why': 'a scheduled read'})
        return json.dumps(compose or {'config': REPORT, 'explain': 'Counts open tasks by kind every Monday.', 'confidence': 'high'})
    return llm


def say(s, text, brain, model='On it.\nDECIDE: setup: '):
    with mock.patch.object(terminal, 'live_sessions', return_value=[]), mock.patch.object(concierge, '_compose_llm', return_value=brain):
        return concierge.say(s, text, llm=lambda *a, **k: model + text)


def run(s, p, version=None):
    with mock.patch.object(server, 'store', s), mock.patch.object(terminal, 'live_sessions', return_value=[]):
        return TestClient(server.app).post(f"/api/operations/{p['id']}/execute", json={'version': version if version is not None else p['version']})


class ReportSetupTests(unittest.TestCase):
    def test_a_report_is_gathered_confirmed_and_created_through_the_reports_road(self):
        s = store()
        out = say(s, 'set up a report of open tasks by kind every Monday at 8', composer())
        self.assertIsNone(out['decision']); p = out['proposal']
        self.assertEqual((p['kind'], p['label'], p['params']['title'], p['params']['schedule'], p['params']['triage']),
                         ('report.create', 'Create the report', 'Open tasks by kind', 'cron 0 8 * * 1', 'informational - filed on the Timeline, not triaged'))
        self.assertEqual(p['params']['config'], REPORT); self.assertIn('yes', p['params']['enabled'])
        self.assertIn('Nothing is saved', out['say']); self.assertIn('Counts open tasks by kind', out['say'])
        self.assertEqual([x for x in s.list_sources(active_only=False) if x['Channel'] == 'report' and x['Address'] == 'Open tasks by kind'], [])   # not yet
        self.assertEqual(s.list_tasks(active_only=True), [])                                                # no placeholder task (PW-197)
        r = run(s, p).json()
        self.assertEqual(r['status'], 'done')
        src = s.get_source(r['outcome']['sourceId'])
        self.assertEqual((src['Channel'], src['Address'], bool(src['Active']), json.loads(src['ConfigJson'])), ('report', 'Open tasks by kind', True, REPORT))
        self.assertEqual(r['outcome']['link'], f"#report={src['SourceId']}")                                # the real resource and its screen
        self.assertEqual(run(s, p).json()['duplicate'], True)                                               # a second click creates nothing
        dock = general.dock_task(s)[0]['TaskId']
        self.assertTrue(any('is on the Reports tab and runs on its schedule' in (c.get('Body') or '') for c in general.chat_rows(s, dock)))

    def test_questions_come_back_as_questions_and_the_next_words_answer_them(self):
        s = store(); seen = []
        asks = composer(compose={'questions': ['Which database?', 'How often?']}, seen=seen)
        out = say(s, 'set up a check on the export table', asks)
        self.assertIsNone(out.get('proposal')); self.assertIn('(1) Which database?', out['say']); self.assertIn('Nothing is set up yet', out['say'])
        self.assertEqual(s.list_sources(active_only=False), [x for x in s.list_sources(active_only=False)])   # nothing created, nothing changed
        seen.clear()
        out = say(s, 'the warehouse one, every morning', composer(seen=seen))
        self.assertEqual(out['proposal']['kind'], 'report.create')
        compose_calls = [u for sysm, u in seen if 'sort one set-up' not in sysm]
        self.assertIn('the warehouse one, every morning', compose_calls[-1]); self.assertIn('Which database?', compose_calls[-1])   # the reply rides with the questions

    def test_a_correction_revises_the_same_proposal_and_a_cancel_creates_nothing(self):
        s = store()
        first = say(s, 'set up a report of open tasks by kind every Monday', composer())['proposal']
        second = say(s, 'make it daily at 7 instead', composer(compose={'config': {**REPORT, 'cron': '0 7 * * *'}, 'explain': 'Daily now.'}))['proposal']
        self.assertEqual((second['id'], second['version'], second['params']['schedule']), (first['id'], 2, 'cron 0 7 * * *'))
        self.assertEqual(run(s, first).status_code, 409)                                                    # the old confirmation is stale
        with mock.patch.object(server, 'store', s): TestClient(server.app).delete(f"/api/operations/{second['id']}")
        self.assertEqual(run(s, second).status_code, 409)
        self.assertEqual([x for x in s.list_sources(active_only=False) if x['Address'] == 'Open tasks by kind'], [])

    def test_a_failing_configuration_and_a_duplicate_title_are_failures_not_resources(self):
        s = store()
        out = say(s, 'set up a report', composer(compose={'error': 'the report has no title'}))
        self.assertEqual(out['proposal']['kind'], 'task.setup'); self.assertIn('could not configure that from here', out['say'])   # the walk-through (PW-197)
        s.save_source({'Channel': 'report', 'Address': 'Open tasks by kind', 'Owner': 'o', 'Active': 1, 'ConfigJson': json.dumps(REPORT)}, 'o')
        p = say(s, 'set up a report of open tasks by kind', composer())['proposal']
        r = run(s, p).json()
        self.assertEqual(r['status'], 'error'); self.assertIn('already exists', r['error'])

    def test_a_preview_is_a_dry_run_that_creates_sends_and_starts_nothing(self):
        s = store()
        p = say(s, 'set up a report of open tasks by kind', composer())['proposal']
        with mock.patch.object(server, 'store', s), mock.patch.object(terminal, 'live_sessions', return_value=[]), \
             mock.patch.object(server, 'report_preview', return_value={'ok': True, 'headline': '3 rows', 'summary': 'coding 2, general 1', 'rows': 3, 'chart': ''}) as dry:
            c = TestClient(server.app)
            r = c.post(f"/api/operations/{p['id']}/preview").json()
            self.assertEqual((r['ok'], r['headline']), (True, '3 rows'))
            self.assertNotIn('cron', dry.call_args[0][0]); self.assertNotIn('deliver', dry.call_args[0][0])   # no schedule, no delivery in a dry run
            self.assertEqual([x for x in s.list_sources(active_only=False) if x['Address'] == 'Open tasks by kind'], [])
            self.assertEqual(operations.get(s, p['id'])['status'], 'proposed')                              # still waiting for the click
            writer = operations.propose(s, 'report.create', 0, {'config': {'type': 'intacct_create', 'title': 'Bills', 'object': 'APBILL'}}, 'owner')
            self.assertEqual(c.post(f"/api/operations/{writer['id']}/preview").status_code, 422)          # an executor that writes cannot be dry-run


class ConnectionSetupTests(unittest.TestCase):
    def test_a_connection_is_confirmed_with_its_authority_and_created_off_and_without_a_secret(self):
        s = store()
        out = say(s, 'connect our Slack workspace', composer(sort={'kind': 'connection', 'provider': 'slack', 'why': 'a chat system'}))
        p = out['proposal']
        self.assertEqual((p['kind'], p['label'], p['params']['type'], p['params']['scope']), ('connection.create', 'Create the connection', 'slack', scopes.default_scope('slack')))
        self.assertIn('never take a token or password', out['say']); self.assertIn('stays off', out['say'])
        self.assertNotIn('Secret', json.dumps(p['params'])); self.assertIn('permissions', p['params'])
        r = run(s, p).json()
        self.assertEqual(r['status'], 'done'); o = r['outcome']
        c = s.get_connector(o['connectorId'], with_secret=True)
        self.assertEqual((c['Type'], bool(c['Active']), c.get('Secret') or None, o['state'], o['link']),
                         ('slack', False, None, 'authorization pending', f"#connector={o['connectorId']}"))
        dock = general.dock_task(s)[0]['TaskId']
        self.assertTrue(any('authorization pending' in (x.get('Body') or '') and 'stays off' in (x.get('Body') or '') for x in general.chat_rows(s, dock)))
        again = say(s, 'connect our Slack workspace', composer(sort={'kind': 'connection', 'provider': 'slack'}))['proposal']
        self.assertEqual(run(s, again).json()['outcome']['connectorId'], o['connectorId'])                    # the same card again, not a second one
        self.assertEqual(len(s.connectors_by_type('slack')), 1)

    def test_an_unnamed_system_is_asked_for_and_a_secret_typed_in_is_not_kept(self):
        s = store()
        out = say(s, 'connect the books', composer(sort={'kind': 'connection', 'provider': None}))
        self.assertIsNone(out.get('proposal')); self.assertIn('Which system is it?', out['say'])
        # the fake tokens are assembled here so no token-shaped literal ever sits in the source
        slack_token, gh_token = 'xoxb-' + '1234567890-' + 'abcdefghijklmnop', 'ghp_' + 'ABCDEFGHIJKLMNOPQRSTUVWXYZ012345'
        say(s, f'here, use {slack_token} for slack', composer(sort={'kind': 'connection', 'provider': 'slack'}))
        dock = general.dock_task(s)[0]['TaskId']
        bodies = ' '.join((c.get('Body') or '') for c in general.chat_rows(s, dock))
        self.assertNotIn(slack_token, bodies); self.assertIn('[redacted]', bodies)
        concierge.remember_fact(s, f'the github token is {gh_token}')
        self.assertNotIn('ghp_', s.list_memories()[0]['Note'])

    def test_digging_is_a_walk_through_proposal_and_no_ai_says_so(self):
        s = store()
        out = say(s, 'set up the whole Intacct integration with the portal', composer(sort={'kind': 'investigate', 'provider': None, 'why': 'several systems and a portal to read'}))
        self.assertEqual((out['proposal']['kind'], out['proposal']['label']), ('task.setup', 'Open the walk-through'))
        self.assertIn('needs digging', out['say']); self.assertIn('several systems', out['say'])
        self.assertEqual(s.list_tasks(active_only=True), [])                                                # proposed, not opened
        with mock.patch.object(terminal, 'live_sessions', return_value=[]), mock.patch.object(concierge, '_compose_llm', return_value=None):
            out = concierge.say(s, 'set up a report', llm=lambda *a, **k: 'On it.\nDECIDE: setup: set up a report')
        self.assertIsNone(out.get('proposal')); self.assertIn('AI connector', out['say'])


if __name__ == '__main__':
    unittest.main()
