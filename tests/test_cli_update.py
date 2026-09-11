"""Updating a CLI that is already here, from the AI CLI agents page.

From the owner, 2026-09-11: codex 0.148.0 refused every run because the model pinned in its own
config needed a newer Codex - "we should have a button to update codex on the cli page". Installing
again is not updating: codex keeps itself under ~/.codex/packages/<version> behind a junction, and
an `npm -g` over that leaves a second copy with the old one still first on PATH. A CLI that ships
its own updater is the one that knows where it put itself.
"""
import unittest
from unittest import mock

from taskuary import cliinstall, clis, guard, server


class PlanTests(unittest.TestCase):
    def test_the_cli_s_own_updater_comes_before_the_package_manager(self):
        self.assertEqual([r['how'] for r in cliinstall.update_plan('codex', has_npm=True)], ['self', 'npm'])
        self.assertEqual([r['how'] for r in cliinstall.update_plan('claude', has_npm=True)], ['self', 'npm'])

    def test_a_road_that_needs_node_is_not_offered_without_node(self):
        self.assertEqual([r['how'] for r in cliinstall.update_plan('codex', has_npm=False)], ['self'])
        self.assertEqual(cliinstall.update_plan('gemini', has_npm=False), [])

    def test_nothing_is_updatable_that_taskuary_has_no_updater_for(self):
        self.assertEqual(cliinstall.update_plan('cursor'), [])
        self.assertEqual(cliinstall.update_plan('rm -rf /'), [])


class RunTests(unittest.TestCase):
    def setUp(self):
        cliinstall.reset(); self.addCleanup(cliinstall.reset)

    def _update(self, name, rc=0, out='updated', found='/usr/local/bin/codex'):
        ran = []
        with mock.patch.object(cliinstall, '_run', side_effect=lambda cmd, **kw: (ran.append(cmd), (rc, out))[1]), \
                mock.patch.object(cliinstall, 'find', return_value=found), \
                mock.patch.object(cliinstall, 'npm', return_value='npm'):
            return cliinstall.update(name), ran

    def test_it_runs_the_updater_through_the_binary_it_actually_found(self):
        """A GUI app keeps the PATH it was launched with, so the name on its own may not resolve."""
        out, ran = self._update('codex')
        self.assertEqual(ran, [['/usr/local/bin/codex', 'update']])
        self.assertEqual(out['phase'], 'done'); self.assertEqual(out['verb'], 'update')
        self.assertEqual(out['detail'], 'updated')          # what the updater said, not our words
        self.assertEqual(self._update('codex', out='')[0]['detail'], 'codex is up to date')

    def test_a_failed_updater_falls_through_to_the_next_road(self):
        ran = []
        def run(cmd, **kw):
            ran.append(cmd)
            return (1, 'unknown command "update"') if len(ran) == 1 else (0, 'ok')
        with mock.patch.object(cliinstall, '_run', side_effect=run), \
                mock.patch.object(cliinstall, 'find', return_value='/usr/local/bin/codex'), \
                mock.patch.object(cliinstall, 'npm', return_value='npm'):
            out = cliinstall.update('codex')
        self.assertEqual([c[0] for c in ran], ['/usr/local/bin/codex', 'npm'])
        self.assertIn('@openai/codex@latest', ran[1])
        self.assertEqual(out['phase'], 'done')

    def test_every_road_failing_says_what_the_updater_said(self):
        out, _ = self._update('codex', rc=1, out='could not reach the release server')
        self.assertEqual(out['phase'], 'failed')
        self.assertIn('could not reach the release server', out['detail'])

    def test_a_cli_that_is_not_here_is_an_install_not_an_update(self):
        out, ran = self._update('codex', found='')
        self.assertEqual(ran, [])
        self.assertEqual(out['phase'], 'failed'); self.assertIn('not on this machine', out['detail'])


class SurfaceTests(unittest.TestCase):
    def test_the_row_says_whether_there_is_an_updater_for_it(self):
        row = next(r for r in clis.detect() if r['name'] == 'codex')
        self.assertIn('updatable', row)
        self.assertEqual(row['updatable'], bool(row['installed'] and cliinstall.update_plan('codex')))
        # a CLI that is not here is offered an Install, never an Update
        gone = next((r for r in clis.detect() if not r['installed']), None)
        if gone: self.assertFalse(gone['updatable'])

    def test_running_an_updater_is_the_owner_s_button_and_never_an_agent_s(self):
        """Same reasoning as /api/cli/install: an agent reads untrusted mail, and one that can
        run a vendor updater can be talked into running one."""
        self.assertTrue(guard.denied('POST', '/api/cli/update'))
        self.assertTrue(guard.denied('POST', '/api/cli/install'))       # and the old door stays shut

    def test_the_endpoint_refuses_a_cli_it_has_no_updater_for(self):
        from fastapi.testclient import TestClient
        c = TestClient(server.app)
        r = c.post('/api/cli/update', json={'name': 'rm -rf /'})
        self.assertEqual(r.status_code, 422)
