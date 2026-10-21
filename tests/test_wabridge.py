"""The WhatsApp bridge, managed by Taskuary: install if needed, start detached, report the phase -
so neither a person nor an agent runs a server in the foreground and waits on it."""
import json, os, threading, time, unittest
from unittest import mock
from fastapi.testclient import TestClient
from taskuary import server, wabridge
from taskuary.store import MemoryStore

c_api = TestClient(server.app)


class BridgeManagerTests(unittest.TestCase):
    def setUp(self):
        wabridge._STATE.update(phase='idle', detail='', pid=None, at=0.0)
        if wabridge._LOCK.locked(): wabridge._LOCK.release()
        self.addCleanup(setattr, wabridge, '_GRACE_OWED', False)     # start_configured owes it; never leak it into a later poll

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
        s.set_connector_config(wa['ConnectorId'], {'notify_chat': 'alerts@s.whatsapp.net',
                                                    'assistant_chat': 'me@s.whatsapp.net'})
        self.assertEqual(wabridge.filter_policy(s, wa['ConnectorId']), {
            'allDirect': True, 'jids': ['alerts@s.whatsapp.net', 'me@s.whatsapp.net', 'picked@g.us']})

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
        with mock.patch.object(wabridge, '_listening', return_value=True), mock.patch.object(wabridge, 'stale', return_value=False), \
             mock.patch.object(wabridge, 'pid_on_port', return_value=4242), \
             mock.patch.object(wabridge, 'start') as start:
            out = wabridge.start_configured(s)
        self.assertTrue(out['started']); self.assertEqual((out['phase'], out['pid']), ('running', 4242))
        start.assert_not_called()

    def test_a_running_bridge_older_than_the_code_on_disk_is_replaced_not_adopted(self):
        """2026-09-25: the poll code shipped, the app restarted, and the bridge answering was still this morning's -
        detached, adopted, and running code that knew nothing of polls."""
        s = MemoryStore(); wa = s.get_connector_by_type('whatsapp')
        s.save_connector({'ConnectorId': wa['ConnectorId'], 'Active': 1}, 'owner')
        with mock.patch.object(wabridge, '_status', return_value={'connected': True, 'code': 'old'}), \
             mock.patch.object(wabridge, 'restart', return_value={'phase': 'starting'}) as restart:
            out = wabridge.start_configured(s)
        self.assertTrue(out['started']); restart.assert_called_once()
        with mock.patch.object(wabridge, '_status', return_value={'connected': True, 'code': wabridge.code()}):
            self.assertFalse(wabridge.stale())

    def test_the_status_check_carries_the_token_the_bridge_demands(self):
        """Without it /status is a 401, which read as "nothing is running" and launched a second bridge onto a busy port."""
        seen = {}
        def get(url, headers=None, timeout=None):
            seen.update(headers or {}); return mock.Mock(status_code=200, json=lambda: {'code': 'x'})
        with mock.patch('requests.get', side_effect=get):
            self.assertEqual(wabridge._status(), {'code': 'x'})
        self.assertEqual(seen.get('x-bridge-token'), wabridge.token())
        with mock.patch('requests.get', return_value=mock.Mock(status_code=401)):
            self.assertTrue(wabridge._listening(), 'something answers on the port - never launch a second copy onto it')

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
        with mock.patch.object(wabridge, 'node', return_value='node'), mock.patch.object(wabridge, 'stage', return_value=wabridge.run_dir()) as stg, \
             mock.patch.object(wabridge.subprocess, 'run', return_value=mock.Mock(returncode=0, stdout='', stderr='')) as run, \
             mock.patch.object(wabridge.subprocess, 'Popen', return_value=P()) as pop, mock.patch.object(wabridge.time, 'sleep'), \
             mock.patch('builtins.open', mock.mock_open()):
            self.assertEqual(wabridge.start(force_install=True, wait=True,
                             filter_policy={'allDirect': False, 'jids': ['picked@g.us']})['phase'], 'running')
        self.assertEqual(run.call_args[0][0][1:], ['install', '--no-audit', '--no-fund'])              # npm install first
        self.assertEqual(pop.call_args[0][0], ['node', 'bridge.mjs']); self.assertEqual(wabridge.state()['pid'], 4242)
        self.assertEqual(pop.call_args.kwargs['cwd'], str(wabridge.run_dir())); stg.assert_called_once_with(carry=False)   # runs from the home
        self.assertEqual(json.loads(pop.call_args.kwargs['env']['WA_BRIDGE_FILTER']),
                         {'allDirect': False, 'jids': ['picked@g.us']})
        self.assertIn('8977', wabridge.state()['detail'])
        # exits at once -> failed, with the log tail
        wabridge._STATE.update(phase='idle')
        class Dead:
            pid = 1; returncode = 1
            def poll(self): return 1
        with mock.patch.object(wabridge, 'node', return_value='node'), mock.patch.object(wabridge.subprocess, 'Popen', return_value=Dead()), \
             mock.patch.object(wabridge, 'stage', return_value=wabridge.run_dir()), \
             mock.patch.object(wabridge.time, 'sleep'), mock.patch('builtins.open', mock.mock_open()), \
             mock.patch.object(wabridge.Path, 'exists', return_value=True), mock.patch.object(wabridge.Path, 'read_bytes', return_value=b'Error: EADDRINUSE 8977'):
            self.assertEqual(wabridge.start(wait=True)['phase'], 'failed')
        self.assertIn('EADDRINUSE', wabridge.state()['detail'])
        # and the threaded road hands back the phase it is entering, without blocking
        with mock.patch.object(wabridge.threading, 'Thread') as th:
            wabridge._STATE.update(phase='idle')
            self.assertEqual(wabridge.start()['phase'], 'starting'); th.return_value.start.assert_called_once()
            wabridge._LOCK.release()                         # the mocked thread never ran work(), so the lock is ours to give back

    def test_the_bridge_runs_from_the_home_so_its_pairing_outlives_the_launch(self):
        """The one-file exe unpacks the package into a fresh temp folder every launch and deletes it on exit; the bridge
        ran there, with its pairing beside it, so every launch of the exe was unpaired (TQ-1157)."""
        import tempfile
        from pathlib import Path
        src = Path(tempfile.mkdtemp()); self.addCleanup(__import__('shutil').rmtree, src, True)
        (src / 'bridge.mjs').write_text('v1'); (src / 'policy.test.mjs').write_text('t'); (src / 'package.json').write_text('{}')
        (src / 'wa-auth').mkdir(); (src / 'wa-auth' / 'creds.json').write_text('paired')
        with mock.patch.object(wabridge, 'DIR', src):
            run = wabridge.stage()
            self.assertEqual(run, wabridge.run_dir()); self.assertNotEqual(run.parent, src.parent)
            self.assertEqual((run / 'bridge.mjs').read_text(), 'v1'); self.assertFalse((run / 'policy.test.mjs').exists())
            self.assertEqual((run / 'wa-auth' / 'creds.json').read_text(), 'paired', 'a pairing made in the package folder carries over')
            (run / 'wa-auth' / 'creds.json').write_text('paired-later')                  # the bridge kept saving keys in the home
            (src / 'bridge.mjs').write_text('v2'); (run / 'gone.mjs').write_text('old')   # an update; a file it no longer ships
            wabridge.stage()
            self.assertEqual((run / 'bridge.mjs').read_text(), 'v2'); self.assertFalse((run / 'gone.mjs').exists())
            self.assertEqual((run / 'wa-auth' / 'creds.json').read_text(), 'paired-later', 'a later launch never overwrites the live pairing')
            self.assertEqual(wabridge.log(), run / 'wa-bridge.log')
            # the bridge's fingerprint of its own folder matches what Taskuary computes off the shipped code
            import hashlib
            self.assertEqual(hashlib.sha1(b''.join(p.read_bytes() for p in sorted(run.glob('*.mjs')))).hexdigest()[:12], wabridge.code())

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


class BridgePortTests(unittest.TestCase):
    def setUp(self): wabridge._BAD_PORTS_SEEN.clear()

    def test_the_port_comes_from_the_environment(self):
        with mock.patch.dict(os.environ, {'WA_BRIDGE_PORT': '9123'}): self.assertEqual(wabridge.port(), 9123)
        with mock.patch.dict(os.environ, {'WA_BRIDGE_PORT': ''}): self.assertEqual(wabridge.port(), 8977)
        with mock.patch.dict(os.environ, clear=False):
            os.environ.pop('WA_BRIDGE_PORT', None); self.assertEqual(wabridge.port(), 8977)

    def test_a_bad_port_falls_back_and_is_warned_about_once(self):
        for bad in ('abc', '99999', '0', '-1'):
            with self.subTest(port=bad), mock.patch.dict(os.environ, {'WA_BRIDGE_PORT': bad}), \
                    mock.patch.object(wabridge.logger, 'warning') as warn:
                self.assertEqual(wabridge.port(), 8977); self.assertEqual(wabridge.port(), 8977)
                warn.assert_called_once(); self.assertIn(repr(bad), warn.call_args.args[0])

    def test_the_status_check_survives_a_bad_port(self):
        import requests
        with mock.patch.dict(os.environ, {'WA_BRIDGE_PORT': 'abc'}), mock.patch.object(wabridge, 'token', return_value='t'), \
                mock.patch('requests.get', side_effect=requests.ConnectionError('refused')) as get:
            self.assertIsNone(wabridge._status())
        self.assertEqual(get.call_args.args[0], 'http://127.0.0.1:8977/status')


class LaunchGraceIsSpentByThePollTests(unittest.TestCase):
    """uvicorn accepts no connection until the FastAPI lifespan yields, and wait_listening(8)
    sat inside it: both launches on 2026-09-09 spent the full 8s there, so the desktop window
    was up saying "can't connect" for 18 seconds. wait_listening only delays its caller, so the
    grace cannot simply move to a thread - it is spent by the WhatsApp poll, which is who the
    grace was always for. And only when this launch started a bridge (P11): owed always, the
    catch-up waited 8 s ahead of all mail on every launch with WhatsApp off, the default."""

    def setUp(self):
        wabridge._GRACE_OWED = False
        self.addCleanup(setattr, wabridge, "_GRACE_OWED", False)
        wabridge._STATE.update(phase='idle', detail='', pid=None, at=0.0)

    def _on(self):
        s = MemoryStore(); wa = s.get_connector_by_type('whatsapp')
        s.save_connector({'ConnectorId': wa['ConnectorId'], 'Active': 1}, 'owner')
        s.save_source({'Channel': 'whatsapp', 'Address': '155@s.whatsapp.net', 'ConnectorId': wa['ConnectorId'], 'Active': 1}, 'o')
        return s

    def test_the_launch_grace_is_spent_once_and_never_again(self):
        waits = []
        def fake_wait(secs): waits.append(secs); return False
        wabridge._GRACE_OWED = True
        with mock.patch.object(wabridge, "wait_listening", fake_wait):
            wabridge.ready(3); wabridge.ready(3); wabridge.ready(3)
        self.assertEqual(waits, [3], f"the bridge grace was waited {len(waits)} times")

    def test_whatsapp_off_owes_no_grace_and_the_catch_up_reads_mail_at_once(self):
        s = MemoryStore()
        self.assertEqual(wabridge.start_configured(s)['reason'], 'WhatsApp is off')
        order = []
        s.set_setting('startup_sync_days', '1', 't')
        with mock.patch.object(wabridge, "wait_listening", lambda secs: order.append("wait") or False), \
             mock.patch.object(server, "store", s), mock.patch.object(server, "_heal_ended"), \
             mock.patch.object(server, "_poll_reports", lambda *a, **k: order.append("poll")), \
             mock.patch.object(server, "report_pass"), mock.patch("taskuary.learn.reflect_if_due"):
            t0 = time.monotonic(); server.catch_up_on_startup().join(10); took = time.monotonic() - t0
        self.assertEqual(order, ["poll"], "nothing was started, so nothing is waited for")
        self.assertLess(took, 2, f"the catch-up sat {took:.1f}s before the mail")

    def test_a_started_bridge_is_given_its_grace_once_by_the_whatsapp_poll(self):
        from taskuary import messengers
        s = self._on()
        with mock.patch.object(wabridge, '_listening', return_value=False), mock.patch.object(wabridge, 'start', return_value={'phase': 'starting'}):
            self.assertTrue(wabridge.start_configured(s)['started'])
        calls, waits = [], []
        def wa(c_, path, body=None): calls.append(path); return {'seq': 0, 'messages': []}
        def wait(secs): calls.append('grace'); waits.append(secs); return True
        c = s.get_connector_by_type('whatsapp', with_secret=True)
        with mock.patch.object(messengers, '_wa', wa), mock.patch.object(wabridge, 'wait_listening', wait):
            messengers.poll_whatsapp(s, c, s.list_sources(), llm=None)
            messengers.poll_whatsapp(s, c, s.list_sources(), llm=None)
        self.assertEqual(waits, [8], 'the grace is spent once, by the first poll')
        self.assertEqual(calls[0], 'grace', f'the bridge was asked before its grace: {calls}')

    def test_a_second_poller_waits_out_the_first_ones_grace(self):
        """The old flag was spent BEFORE the wait: the chat clock found it spent while the catch-up was still waiting,
        polled a bridge still coming up, and filed the false "bridge not running" the grace was for."""
        wabridge._GRACE_OWED = True
        release, seen = threading.Event(), []
        def slow_wait(secs): release.wait(5); return True
        with mock.patch.object(wabridge, 'wait_listening', slow_wait):
            first = threading.Thread(target=wabridge.ready); first.start()
            time.sleep(.1)
            second = threading.Thread(target=lambda: seen.append(wabridge.ready())); second.start()
            time.sleep(.2)
            self.assertEqual(seen, [], 'the second poller went ahead while the bridge was still starting')
            release.set(); first.join(5); second.join(5)
        self.assertEqual(seen, [True])
