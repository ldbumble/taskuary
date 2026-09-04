"""Two things the owner hit on 2026-09-04.

One report may not cost the others their run, and the ones that read only Taskuary's own database
go first - a SQL Server that was not there spent 41 s in a login timeout while the Morning digest
waited behind it. And "can you research the Factor Elara gravel bike" is a walk-through, not a
hand-off: it opened a coding agent on a checkout.
"""
import json, unittest
from unittest import mock

from taskuary import concierge, reports
from taskuary.store import MemoryStore


def _report(s, title, kind, address=None):
    return s.save_source({'Channel': 'report', 'Address': address or title, 'Active': 1,
                          'ConfigJson': json.dumps({'type': kind, 'title': title, 'every': 'startup'})}, 'test')


class ReportOrderTests(unittest.TestCase):
    def _run(self, s, ran, boom=()):
        def fake(store, src, llm=None):
            cfg = json.loads(src.get('ConfigJson') or '{}')
            ran.append(cfg.get('type'))
            if cfg.get('type') in boom: raise RuntimeError('the server is not there')
            return {'subject': cfg.get('title')}
        with mock.patch.object(reports, 'run_report_source', fake), \
             mock.patch.object(reports, 'is_due', lambda *a, **k: True):
            return reports.run_due_reports(s, startup=True)

    def test_every_dial_out_report_waits_behind_every_local_one(self):
        """A fresh store already seeds several store-backed reports, so the assertion is the
        PARTITION rather than two fixed names: nothing that dials out may run before something
        that only reads the database."""
        s = MemoryStore()
        _report(s, 'Process Error Check', 'mssql')      # unreachable in real life...
        _report(s, 'Headcount', 'sql')
        _report(s, 'A metric', 'metric')                # ...and this local one was added AFTER it
        ran = []
        self._run(s, ran)
        local = [t in reports.STORE_BACKED for t in ran]
        self.assertEqual(local, sorted(local, reverse=True), ran)     # all local, then all dial-out
        # the ordering is what is under test, so a local report added LAST must still overtake:
        # every store-backed type comes first in list_sources() order, which would pass unsorted
        self.assertLess(ran.index('metric'), ran.index('mssql'), ran)
        self.assertEqual(sorted(t for t in ran if t in ('mssql', 'sql')), ['mssql', 'sql'])

    def test_a_report_that_raises_does_not_cost_the_others_their_run(self):
        s = MemoryStore()
        _report(s, 'Process Error Check', 'mssql')
        _report(s, 'Headcount', 'sql')
        ran = []
        n = self._run(s, ran, boom=('mssql',))
        self.assertEqual(sorted(t for t in ran if t in ('mssql', 'sql')), ['mssql', 'sql'])
        self.assertIn('digest', ran)                                 # the local ones ran too
        self.assertEqual(n, len(ran) - 1)                            # only the raiser is uncounted

    def test_even_a_raising_report_is_touched_so_it_waits_for_its_next_slot(self):
        s = MemoryStore()
        _report(s, 'Process Error Check', 'mssql', address='Process Error Check')
        self._run(s, [], boom=('mssql',))
        row = next(x for x in s.list_sources() if x['Address'] == 'Process Error Check')
        self.assertTrue(row['LastPolledAt'])

    def test_the_split_reuses_resolve_cfg_s_own_list_and_never_crashes_the_poll(self):
        for t in ('assistant', 'digest', 'automate', 'evening_inbox'):
            self.assertTrue(reports._own_data({'ConfigJson': json.dumps({'type': t})}), t)
        for t in ('mssql', 'sql', 'rest', 'zoho_monthly_invoices'):
            self.assertFalse(reports._own_data({'ConfigJson': json.dumps({'type': t})}), t)
        self.assertFalse(reports._own_data({'ConfigJson': '{}'}))            # 'rest' by default
        self.assertFalse(reports._own_data({'ConfigJson': 'not json'}))      # never crashes the poll


class ResearchIsAWalkThroughTests(unittest.TestCase):
    def test_research_no_longer_hard_routes_to_the_coding_agent(self):
        """The other verbs on that rule DIAGNOSE something that exists; research reads about the
        world (the owner, 2026-09-04: this opened a coding agent on a checkout)."""
        for said in ('can you research teh factor elara gravel bike',
                     'research the best gravel bike for me',
                     'can you research the Factor Elara'):
            self.assertIsNone(concierge.decide_words(said), said)

    def test_diagnosing_a_system_is_still_a_hand_off(self):
        for said in ('can you look into that server and what the file looks like?',
                     'look into that server and tell me what the file looks like',
                     'find out why the export drops rows',
                     'send it to the coding agent and figure out why this was not updated'):
            self.assertEqual((concierge.decide_words(said) or {}).get('verb'), 'coder', said)

    def test_the_brain_is_given_the_walk_through_road_and_the_test_for_it(self):
        """It had `coder` and no way to say "let's talk this through", so reading work had nowhere
        to go but a checkout."""
        blob = ' '.join(str(getattr(concierge, n)) for n in dir(concierge)
                        if n.isupper() and isinstance(getattr(concierge, n), str))
        self.assertIn('setup (reading, thinking or research with NO system to type at', blob)
        self.assertIn('the test is whether there is a SYSTEM to type at', blob)
        self.assertIn('because the sentence was polite', blob)

    def test_a_walk_through_opens_a_general_task_and_starts_no_agent(self):
        s = MemoryStore()
        with mock.patch('taskuary.ingest._spawn') as spawned:
            made = concierge.setup_task(s, 'research the factor elara gravel bike', 'owner')
        spawned.assert_not_called()                                  # nothing is built
        self.assertEqual(s.get_task(made['taskId'])['Kind'], concierge.SETUP_KIND)
        self.assertEqual(concierge.SETUP_KIND, 'general')


if __name__ == '__main__':
    unittest.main()
