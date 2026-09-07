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
    def _proposed(self, said, verb):
        s = MemoryStore(); s.upsert_agent('coder', 'coding', 'cli', '{}')
        with mock.patch('taskuary.terminal.live_sessions', return_value=[]):
            return s, concierge.say(s, said, llm=lambda *a, **k: f'On it.\nDECIDE: {verb}: {said}')

    def test_research_routes_to_the_regular_agent_not_the_coding_agent(self):
        """Research is work to hand off, but it has no repository or system to change. The brain names
        the regular agent (the road the contract gives it) and the proposal is a general task - never a
        coding checkout (the owner, 2026-09-04)."""
        for said in ('can you research teh factor elara gravel bike', 'research the best gravel bike for me', 'can you research the Factor Elara'):
            s, out = self._proposed(said, 'regular_agent')
            p = out['proposal']
            self.assertEqual((p['kind'], p['params']['kind']), ('task.create_from_text', 'general'), said)
            self.assertEqual(s.list_tasks(active_only=True), [], said)      # a proposal, not a task

    def test_diagnosing_a_system_is_still_a_hand_off(self):
        for said in ('look into that server and tell me what the file looks like', 'find out why the export drops rows',
                     'send it to the coding agent and figure out why this was not updated'):
            s, out = self._proposed(said, 'coder')
            self.assertEqual((out['proposal']['kind'], out['proposal']['params']['kind']), ('task.create_from_text', 'coding'), said)

    def test_the_brain_is_given_the_walk_through_road_and_the_test_for_it(self):
        """It had `coder` and no way to say "let's talk this through", so reading work had nowhere
        to go but a checkout. The rule moved from the code's SYSTEM string into COUNSEL's own
        document (PW-248/256): the code keeps only the coder/regular_agent/setup verbs themselves."""
        from pathlib import Path
        from taskuary import counsel
        text = (Path(concierge.__file__).parent / 'templates' / 'counsel.md').read_text(encoding='utf-8')
        body = counsel.sections(text)[counsel.DECIDING_HEAD]
        self.assertIn('coder and setup are not the same road', body)
        self.assertIn('the test is whether there is a SYSTEM to type at', body)
        self.assertIn('because the sentence was polite', body)

    def test_a_walk_through_opens_a_general_task_and_starts_no_agent(self):
        s = MemoryStore()
        with mock.patch('taskuary.ingest._spawn') as spawned:
            made = concierge.setup_task(s, 'research the factor elara gravel bike', 'owner')
        spawned.assert_not_called()                                  # nothing is built
        self.assertEqual(s.get_task(made['taskId'])['Kind'], concierge.SETUP_KIND)
        self.assertEqual(concierge.SETUP_KIND, 'general')


if __name__ == '__main__':
    unittest.main()
