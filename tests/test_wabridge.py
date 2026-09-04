"""The WhatsApp bridge, managed by Taskuary: install if needed, start detached, report the phase -
so neither a person nor an agent runs a server in the foreground and waits on it."""
import json, time, unittest
from unittest import mock
from fastapi.testclient import TestClient
from taskuary import server, wabridge
from taskuary.store import MemoryStore

c_api = TestClient(server.app)


class BridgeManagerTests(unittest.TestCase):
    def setUp(self):
        wabridge._STATE.update(phase='idle', detail='', pid=None, at=0.0)
        if wabridge._LOCK.locked(): wabridge._LOCK.release()

    def test_a_bridge_started_by_hand_is_found_by_its_port_and_restarted(self):
        """The owner's bridge predated the code that reports the paired number; only a restart picks the
        new code up, and the manager never started that process - so it finds it by the port."""
        netstat = 'Active Connections\n\n  Proto  Local Address          Foreign Address        State           PID\n  TCP    0.0.0.0:135            0.0.0.0:0              LISTENING       1234\n  TCP    127.0.0.1:8977         0.0.0.0:0              LISTENING       4242\n'
        with mock.patch.object(wabridge.os, 'name', 'nt'), mock.patch.object(wabridge.subprocess, 'run', return_value=mock.Mock(stdout=netstat)) as run:
            self.assertEqual(wabridge.pid_on_port(8977), 4242)
            with mock.patch.object(wabridge, 'start', return_value={'phase': 'starting'}) as st, mock.patch.object(wabridge.time, 'sleep'):
                self.assertEqual(wabridge.restart()['phase'], 'starting')
            self.assertIn(['taskkill', '/PID', '4242', '/T', '/F'], [c.args[0] for c in run.call_args_list]); st.assert_called_once()

    def test_an_enabled_local_bridge_starts_with_the_app(self):
        s = MemoryStore()
        wa = s.get_connector_by_type('whatsapp')
        s.save_connector({'ConnectorId': wa['ConnectorId'], 'Active': 1}, 'owner')
        with mock.patch.object(wabridge, '_listening', return_value=False), \
             mock.patch.object(wabridge, 'start', return_value={'phase': 'starting'}) as start:
            out = wabridge.start_configured(s)
        self.assertTrue(out['started']); self.assertEqual(out['connectorId'], wa['ConnectorId'])
        start.assert_called_once_with(filter_policy={'allDirect': False, 'jids': []})

    def test_launch_filter_contains_only_active_sources_and_the_control_chat(self):
        s = MemoryStore(); wa = s.get_connector_by_type('whatsapp')
        s.save_source({'Channel': 'whatsapp', 'Address': '*', 'ConnectorId': wa['ConnectorId'], 'Active': 1}, 'o')
        s.save_source({'Channel': 'whatsapp', 'Address': 'picked@g.us', 'ConnectorId': wa['ConnectorId'], 'Active': 1}, 'o')
        s.save_source({'Channel': 'whatsapp', 'Address': 'off@g.us', 'ConnectorId': wa['ConnectorId'], 'Active': 0}, 'o')
        s.set_connector_config(wa['ConnectorId'], {'notify_chat': 'me@s.whatsapp.net'})
        self.assertEqual(wabridge.filter_policy(s, wa['ConnectorId']), {
            'allDirect': True, 'jids': ['me@s.whatsapp.net', 'picked@g.us']})

    def test_an_off_or_external_whatsapp_card_does_not_start_a_local_bridge(self):
        s = MemoryStore(); wa = s.get_connector_by_type('whatsapp')
        with mock.patch.object(wabridge, 'start') as start:
            self.assertFalse(wabridge.start_configured(s)['started'])
            s.save_connector({'ConnectorId': wa['ConnectorId'], 'Active': 1,
                              'ConfigJson': '{"bridge_url":"http://wa-box.local:8977"}'}, 'owner')
            out = wabridge.start_configured(s)
        self.assertFalse(out['started']); self.assertEqual(out['reason'], 'external bridge URL')
        start.assert_not_called()

    def test_startup_adopts_a_detached_bridge_that_is_already_running(self):
        s = MemoryStore(); wa = s.get_connector_by_type('whatsapp')
        s.save_connector({'ConnectorId': wa['ConnectorId'], 'Active': 1}, 'owner')
        with mock.patch.object(wabridge, '_listening', return_value=True), \
             mock.patch.object(wabridge, 'pid_on_port', return_value=4242), \
             mock.patch.object(wabridge, 'start') as start:
            out = wabridge.start_configured(s)
        self.assertTrue(out['started']); self.assertEqual((out['phase'], out['pid']), ('running', 4242))
        start.assert_not_called()

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
            self.assertEqual(wabridge.start(force_install=True, wait=True,
                             filter_policy={'allDirect': False, 'jids': ['picked@g.us']})['phase'], 'running')
        self.assertEqual(run.call_args[0][0][1:], ['install', '--no-audit', '--no-fund'])              # npm install first
        self.assertEqual(pop.call_args[0][0], ['node', 'bridge.mjs']); self.assertEqual(wabridge.state()['pid'], 4242)
        self.assertEqual(json.loads(pop.call_args.kwargs['env']['WA_BRIDGE_FILTER']),
                         {'allDirect': False, 'jids': ['picked@g.us']})
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
        self.assertEqual(r['phase'], 'installing'); st.assert_called_once_with(False, filter_policy=mock.ANY)
        slack = next(x for x in server.store.list_connectors() if x['Type'] == 'slack')
        self.assertEqual(c_api.post(f"/api/connectors/{slack['ConnectorId']}/wa/bridge/start").status_code, 404)
        from taskuary import messengers
        with mock.patch.object(messengers.requests, 'get', side_effect=messengers.requests.ConnectionError('refused')):
            r = c_api.get(f"/api/connectors/{wa['ConnectorId']}/wa/status").json()
        self.assertEqual(r['bridge'], False); self.assertIn('phase', r['manager'])                    # the manager's phase rides along
        self.assertIn(r['node'], (True, False))                                                        # step 1 of the pairing box: is Node here
