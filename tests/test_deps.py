"""The Install button's half: what may be installed, into which Python, and who may ask."""
import sys, unittest
from unittest import mock

from fastapi.testclient import TestClient

from taskuary import deps, guard, server

c = TestClient(server.app)


class DepsTests(unittest.TestCase):
    def test_the_list_is_closed(self):
        """pip runs arbitrary setup code, so the field is not a field - it is a menu."""
        with self.assertRaisesRegex(ValueError, 'not one of the packages'):
            deps.install('requests; rm -rf /')
        with self.assertRaisesRegex(ValueError, 'not one of the packages'):
            deps.install('some-package-nobody-vetted')
        self.assertEqual(c.post('/api/deps/install', json={'package': 'evil'}).status_code, 422)

    def test_it_installs_into_the_python_that_is_running(self):
        """The whole point: not 'a' Python, THE one whose site-packages this process imports from."""
        seen = {}
        ok = mock.Mock(returncode=0, stdout='Successfully installed boto3', stderr='')
        with mock.patch.object(deps.spawn, 'run', side_effect=lambda cmd, **kw: (seen.update(cmd=cmd), ok)[1]):
            out = deps.install('boto3')
        self.assertEqual(seen['cmd'][:4], [sys.executable, '-m', 'pip', 'install'])
        self.assertIn('boto3>=1.28', seen['cmd'])
        self.assertEqual((out['ok'], out['name'], out['python']), (True, 'boto3', sys.executable))

    def test_a_pip_failure_is_reported_not_swallowed(self):
        bad = mock.Mock(returncode=1, stdout='', stderr='ERROR: no matching distribution')
        with mock.patch.object(deps.spawn, 'run', return_value=bad):
            with self.assertRaisesRegex(RuntimeError, 'no matching distribution'):
                deps.install('boto3')

    def test_the_packaged_exe_installs_beside_the_owners_data(self):
        """It used to answer "this is the packaged Taskuary.exe" and stop, which left the AWS card
        permanently dead on the one install most people download (owner, 2026-09-02). sys.executable
        IS Taskuary.exe there, so `-m pip` would start a second copy of the app: pip runs in this
        process instead, into ~/.taskuary/packages, which is on sys.path from startup."""
        seen = {}
        with mock.patch.object(deps.sys, 'frozen', True, create=True):
            self.assertEqual(deps.can_install(), (True, ''))
            with mock.patch.object(deps, '_pip_here',
                                   side_effect=lambda req: (seen.update(req=req), (0, 'Successfully installed boto3'))[1]):
                out = deps.install('boto3')
        self.assertEqual(seen['req'], 'boto3>=1.28')
        self.assertEqual(out['where'], str(deps.packages_dir()))
        self.assertIn(str(deps.packages_dir()), sys.path)

    def test_a_build_with_no_pip_inside_says_which_install_can(self):
        no_pip = mock.patch.object(deps, 'installed', lambda pkg: False)
        with mock.patch.object(deps.sys, 'frozen', True, create=True), no_pip:
            can, why = deps.can_install()
            self.assertFalse(can); self.assertIn('Taskuary.exe', why)
            with self.assertRaisesRegex(RuntimeError, 'Taskuary.exe'): deps.install('boto3')

    def test_what_the_exe_ships_is_one_list_the_build_reads(self):
        """deps.BUNDLE and taskuary.spec drifting apart is a build that silently ships dead cards."""
        from pathlib import Path
        self.assertTrue(set(deps.BUNDLE) <= set(deps.OPTIONAL))
        spec = (Path(__file__).resolve().parent.parent / 'taskuary.spec').read_text(encoding='utf-8')
        self.assertIn('from taskuary.deps import BUNDLE', spec)
        self.assertIn('*BUNDLE', spec)

    def test_the_owner_may_install_and_an_agent_may_not(self):
        self.assertTrue(guard.denied('POST', '/api/deps/install'))
        self.assertFalse(guard.denied('GET', '/api/deps'))       # reading the list is harmless

    def test_the_name_the_owner_sees_is_the_pip_name(self):
        self.assertEqual(deps.pip_name('winpty'), 'pywinpty')
        self.assertEqual(deps.pip_name('faster_whisper'), 'faster-whisper')
        self.assertEqual(deps.pip_name('boto3'), 'boto3')

    def test_a_missing_package_reaches_the_card_as_a_button_not_a_command(self):
        """channels.test_connector turns deps.Missing into the structured half the card renders."""
        from taskuary import aws, channels
        cid = server.store.get_connector_by_type('aws')['ConnectorId']
        # aws.test used to flatten every exception to a string, which is what lost the package
        with mock.patch.object(aws, 'client', side_effect=deps.Missing('boto3', 'boto3 is not installed')):
            out = channels.test_connector(server.store, cid)
        self.assertFalse(out['ok'])
        self.assertEqual(out['install']['package'], 'boto3')
        self.assertEqual(out['install']['name'], 'boto3')
        self.assertTrue(out['install']['can'])

    def test_aws_raises_the_kind_the_card_can_act_on(self):
        from taskuary import aws
        real = __builtins__['__import__'] if isinstance(__builtins__, dict) else __builtins__.__import__
        def no_boto(name, *a, **k):
            if name == 'boto3': raise ImportError('no boto3')
            return real(name, *a, **k)
        with mock.patch('builtins.__import__', side_effect=no_boto):
            with self.assertRaises(deps.Missing) as cm: aws._boto3()
        self.assertEqual(cm.exception.package, 'boto3')
        self.assertIn('AWS card', str(cm.exception))


if __name__ == '__main__':
    unittest.main()
