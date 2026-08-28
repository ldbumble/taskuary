"""The WhatsApp bridge, managed by Taskuary: install if needed, start detached, report the phase -
so neither a person nor an agent runs a server in the foreground and waits on it."""
import time, unittest
from unittest import mock
from fastapi.testclient import TestClient
from taskuary import server, wabridge

c_api = TestClient(server.app)


class BridgeManagerTests(unittest.TestCase):
    def setUp(self):
        wabridge._STATE.update(phase='idle', detail='', pid=None, at=0.0)
        if wabridge._LOCK.locked(): wabridge._LOCK.release()

    def test_no_node_is_a_failed_phase_the_owner_can_act_on(self):
        # wait=True runs the worker inline: a threaded worker outlived its mocks on a slow CI box and
        # kept the lock, so the next test's start() was a no-op and both went red
        with mock.patch.object(wabridge, 'node', return_value=''):
            self.assertEqual(wabridge.start(wait=True)['phase'], 'failed')
        self.assertIn('nodejs.org', wabridge.state()['detail'])

    def test_install_then_start_detached_and_a_dying_bridge_is_reported(self):
        class P:
            pid = 4242
            def poll(self): return None
        with mock.patch.object(wabridge, 'node', return_value='node'), mock.patch.object(wabridge, 'DIR', wabridge.DIR), \
             mock.patch.object(wabridge.subprocess, 'run', return_value=mock.Mock(returncode=0, stdout='', stderr='')) as run, \
             mock.patch.object(wabridge.subprocess, 'Popen', return_value=P()) as pop, mock.patch.object(wabridge.time, 'sleep'), \
             mock.patch('builtins.open', mock.mock_open()):
            self.assertEqual(wabridge.start(force_install=True, wait=True)['phase'], 'running')
        self.assertEqual(run.call_args[0][0][1:], ['install', '--no-audit', '--no-fund'])              # npm install first
        self.assertEqual(pop.call_args[0][0], ['node', 'bridge.mjs']); self.assertEqual(wabridge.state()['pid'], 4242)
        self.assertIn('8977', wabridge.state()['detail'])
        # exits at once -> failed, with the log tail
        wabridge._STATE.update(phase='idle')
        class Dead:
            pid = 1; returncode = 1
            def poll(self): return 1
        with mock.patch.object(wabridge, 'node', return_value='node'), mock.patch.object(wabridge.subprocess, 'Popen', return_value=Dead()), \
             mock.patch.object(wabridge.time, 'sleep'), mock.patch('builtins.open', mock.mock_open()), \
             mock.patch.object(wabridge.Path, 'exists', return_value=True), mock.patch.object(wabridge.Path, 'read_bytes', return_value=b'Error: EADDRINUSE 8977'):
            self.assertEqual(wabridge.start(wait=True)['phase'], 'failed')
        self.assertIn('EADDRINUSE', wabridge.state()['detail'])
        # and the threaded road hands back the phase it is entering, without blocking
        with mock.patch.object(wabridge.threading, 'Thread') as th:
            wabridge._STATE.update(phase='idle')
            self.assertEqual(wabridge.start()['phase'], 'starting'); th.return_value.start.assert_called_once()
            wabridge._LOCK.release()                         # the mocked thread never ran work(), so the lock is ours to give back

    def test_the_card_and_the_agent_have_a_verb_for_it(self):
        wa = next(x for x in server.store.list_connectors() if x['Type'] == 'whatsapp')
        with mock.patch.object(wabridge, 'start', return_value={'phase': 'installing', 'detail': 'npm install'}) as st:
            r = c_api.post(f"/api/connectors/{wa['ConnectorId']}/wa/bridge/start").json()
        self.assertEqual(r['phase'], 'installing'); st.assert_called_once_with(False)
        slack = next(x for x in server.store.list_connectors() if x['Type'] == 'slack')
        self.assertEqual(c_api.post(f"/api/connectors/{slack['ConnectorId']}/wa/bridge/start").status_code, 404)
        from taskuary import messengers
        with mock.patch.object(messengers.requests, 'get', side_effect=messengers.requests.ConnectionError('refused')):
            r = c_api.get(f"/api/connectors/{wa['ConnectorId']}/wa/status").json()
        self.assertEqual(r['bridge'], False); self.assertIn('phase', r['manager'])                    # the manager's phase rides along
