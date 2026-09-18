"""What the assistant knows about the APP, generated from the tables the tabs read - never typed in.
Asked from WhatsApp to "run me the AR report" it had no list of reports at all (the owner, 2026-09-18)."""
import json, unittest
from taskuary import appfacts
from taskuary.store import MemoryStore


AR = {}


def store():
    s = MemoryStore()                                     # a fresh store already carries the seeded reports (Morning digest, Assistant)
    AR['sid'] = s.save_source({'Channel': 'report', 'Address': 'ar@report', 'Active': 1,
                               'ConfigJson': json.dumps({'title': 'Monthly AR Report', 'type': 'mssql', 'daily_at': '07:00', 'reach': 'always'})}, 't')
    wf = s.save_source({'Channel': 'report', 'Address': 'adp@walk', 'Active': 1,
                        # workflows.is_workflow: an agent job that writes, or one driven in the browser
                        'ConfigJson': json.dumps({'title': 'ADP hours export', 'type': 'agent', 'browser': True, 'cron': '0 6 * * 1-5'})}, 't')
    s.add_report_run(wf, {'at': '2026-09-18 06:01:00', 'title': 'ADP hours export', 'failed': True, 'error': 'sign-in page'})
    s.save_connector({'Type': 'outlook', 'Name': 'Uri mailbox', 'Active': 1, 'ConfigJson': '{}', 'Secret': 'tok'}, 't')
    s.save_connector({'Type': 'teams', 'Name': 'Teams', 'Active': 0, 'ConfigJson': '{}'}, 't')
    s.upsert_agent('coder', 'coding', 'cli', json.dumps({'cmd': 'claude'}))
    s.set_setting('intent_classify_enabled', '1', 't'); s.set_setting('poll_minutes', '10', 't')
    return s


class FactsTests(unittest.TestCase):
    def test_reports_and_workflows_are_told_apart_with_their_clock_and_last_outcome(self):
        rows = {r['title']: r for r in appfacts.reports(store())}
        self.assertFalse(rows['Monthly AR Report']['workflow']); self.assertIn('07:00', rows['Monthly AR Report']['schedule'])
        self.assertTrue(rows['ADP hours export']['workflow']); self.assertIs(rows['ADP hours export']['last_ok'], False)
        self.assertIn('sign-in page', rows['ADP hours export']['last_said'])
        self.assertIsNone(rows['Monthly AR Report']['last_ok'])                      # never ran: unknown, not failed

    def test_settings_come_from_the_schema_with_their_values_in_words(self):
        rows = {r['key']: r for r in appfacts.settings(store())}
        self.assertEqual(rows['intent_classify_enabled']['said'], 'Intent triage (Triage & routing): on')
        self.assertEqual(rows['poll_minutes']['value'], '10')
        self.assertNotIn('ingest_status', rows)                                       # bookkeeping is not a knob

    def test_connections_and_agents(self):
        c = {r['name']: r for r in appfacts.connections(store())}
        self.assertTrue(c['Uri mailbox']['active']); self.assertTrue(c['Uri mailbox']['has_secret'])
        self.assertFalse(c['Teams']['active']); self.assertFalse(c['Teams']['has_secret'])
        self.assertEqual([a['name'] for a in appfacts.agents(store())], ['coder'])

    def test_find_by_name_is_case_insensitive_containment_and_id_wins(self):
        s = store()
        self.assertEqual(appfacts.find_report(s, 'ar report')['title'], 'Monthly AR Report')
        self.assertEqual(appfacts.find_report(s, 'nothing like it', source_id=AR['sid'])['title'], 'Monthly AR Report')
        self.assertIsNone(appfacts.find_report(s, 'payroll'))
        self.assertEqual(appfacts.find_connection(s, 'teams')['type'], 'teams')

    def test_the_state_block_is_counts_and_names_first_and_bounded(self):
        b = appfacts.state_block(store())
        self.assertIn('THE APP RIGHT NOW', b)
        self.assertRegex(b, r'\d+ reports?: '); self.assertIn('1 workflow: ', b)
        self.assertIn('Monthly AR Report', b); self.assertIn('ADP hours export - last run failed', b)
        self.assertRegex(b, r'\d+ connected: .*Uri mailbox'); self.assertNotIn('Teams', b)   # the catalogue's off cards are a count
        self.assertIn('catalogue cards off', b)
        self.assertIn('walk me through my tasks', b)                                   # the scripts, by name
        self.assertLess(len(b), 2500)
        many = store()
        for n in range(80):
            many.save_source({'Channel': 'report', 'Address': f'r{n}@x', 'Active': 1, 'ConfigJson': json.dumps({'title': f'Report number {n}'})}, 't')
        self.assertLessEqual(len(appfacts.state_block(many)), 2500)                    # the cap holds; the look-up has the rest
        self.assertIn('more - reports.list has them all', appfacts.state_block(many))


if __name__ == '__main__':
    unittest.main()
