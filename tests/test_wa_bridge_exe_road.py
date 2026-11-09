"""#278: a fresh Windows install pressed Start bridge, Restart, Start - and the bridge never came up. Nothing on an ordinary client
computer runs the bridge's install: no Node, or Node without Git (Baileys fetched libsignal through git). The failure lived only
on the card in npm's own words, the app log had no line of it, every status poll spent Windows' 2 s refused-connect retry, and
the card's chat list answered a raw 409 that the Assistant's bug report filed."""
import json, unittest
from pathlib import Path
from unittest import mock
from fastapi.testclient import TestClient
from loguru import logger
from taskuary import messengers, noderuntime, server, wabridge
from taskuary.store import MemoryStore

c_api = TestClient(server.app)
NPM_NO_GIT = """npm ERR! code ENOENT
npm ERR! syscall spawn git
npm ERR! path git
npm ERR! errno -4058
npm ERR! enoent An unknown git error occurred
npm ERR! enoent This is related to npm not being able to find a file.

npm ERR! A complete log of this run can be found in: C:\\Users\\alex\\AppData\\Local\\npm-cache\\_logs\\debug-0.log"""


class Base(unittest.TestCase):
    def setUp(self):
        wabridge._STATE.update(phase='idle', detail='', pid=None, at=0.0)
        if wabridge._LOCK.locked(): wabridge._LOCK.release()
        self.said = []; sink = logger.add(lambda m: self.said.append(str(m)), level='WARNING', format='{message}')
        self.addCleanup(logger.remove, sink)


class NoNodeTests(Base):
    def test_start_with_no_node_records_and_returns_a_plain_reason_and_logs_it(self):
        with mock.patch.object(wabridge, 'node', return_value=''),              mock.patch.object(noderuntime, 'fetch', side_effect=RuntimeError('could not download Node.js from nodejs.org (refused)')):
            out = wabridge.start(wait=True)
        self.assertEqual(out['phase'], 'failed')
        self.assertEqual(out['detail'], 'Node.js could not be set up: could not download Node.js from nodejs.org (refused)')
        self.assertTrue(any('Node.js could not be set up' in l for l in self.said), 'the app log carries why the start failed')

    def test_a_start_sets_up_node_in_the_background_then_goes_on(self):
        have = {'node': ''}
        def fetch(say):
            say('Setting up WhatsApp - downloading Node.js, 12 of 36 MB'); seen.append(wabridge.state()['detail'])
            have['node'] = '/home/alex/.taskuary/node/bin/node'; return have['node']
        seen = []
        with mock.patch.object(wabridge, 'node', side_effect=lambda: have['node']), mock.patch.object(noderuntime, 'fetch', side_effect=fetch),              mock.patch.object(wabridge, 'stage', side_effect=RuntimeError('reached the install')):
            out = wabridge.start(wait=True)
        self.assertEqual(seen, ['Setting up WhatsApp - downloading Node.js, 12 of 36 MB'], 'the card shows the download as it goes')
        self.assertEqual(out['detail'], 'reached the install', 'Node came, and the start went on past it')

    def test_the_supervisors_automatic_restart_never_downloads(self):
        with mock.patch.object(wabridge, 'node', return_value=''), mock.patch.object(noderuntime, 'fetch') as f:
            out = wabridge.start(wait=True, auto=True)
        f.assert_not_called(); self.assertIn('press Start bridge and Taskuary sets it up', out['detail'])

    def test_the_card_buttons_set_node_up(self):
        s = MemoryStore(); wa = s.get_connector_by_type('whatsapp')
        with mock.patch.object(server, 'store', s), mock.patch.object(wabridge, 'start', return_value={'phase': 'starting'}) as st,              mock.patch.object(wabridge, 'restart', return_value={'phase': 'starting'}) as rs:
            c_api.post(f"/api/connectors/{wa['ConnectorId']}/wa/bridge/start"); c_api.post(f"/api/connectors/{wa['ConnectorId']}/wa/bridge/restart")
        self.assertTrue(st.call_args.kwargs['fetch_node']); self.assertTrue(rs.call_args.kwargs['fetch_node'])


class PortableNodeTests(Base):
    """noderuntime: the official zip, its sha256 checked, unpacked under the data folder - no installer, no administrator."""
    def zipped(self, a):
        import io, zipfile
        b = io.BytesIO()
        with zipfile.ZipFile(b, 'w') as z:
            top = f'node-{noderuntime.VERSION}-{a.rsplit(".", 1)[0]}'
            z.writestr(f'{top}/node.exe', 'MZ'); z.writestr(f'{top}/npm.cmd', '@echo off')
        return b.getvalue()

    def get_for(self, blob):
        class R:
            headers = {'content-length': str(len(blob))}
            def raise_for_status(self): pass
            def iter_content(self, n): yield blob
        return lambda url, stream=True: R()

    def test_it_downloads_checks_and_unpacks_under_the_home(self):
        import hashlib
        blob = self.zipped('win-x64.zip'); said = []
        with mock.patch.object(noderuntime, 'asset', return_value='win-x64.zip'), mock.patch.object(noderuntime.os, 'name', 'nt'),              mock.patch.dict(noderuntime.SHA256, {'win-x64.zip': hashlib.sha256(blob).hexdigest()}):
            got = noderuntime.fetch(say=said.append, get=self.get_for(blob))
            self.assertEqual(noderuntime.find(), got)
        self.assertTrue(Path(got).is_file()); self.assertTrue(Path(got).is_relative_to(noderuntime.home()))
        self.assertTrue((Path(got).parent / 'npm.cmd').is_file(), 'npm comes in the same zip')
        self.assertIn('Setting up WhatsApp - unpacking Node.js', said)

    def test_a_download_that_does_not_match_its_checksum_is_thrown_away(self):
        blob = self.zipped('win-arm64.zip')
        with mock.patch.object(noderuntime, 'asset', return_value='win-arm64.zip'), mock.patch.object(noderuntime.os, 'name', 'nt'),              self.assertRaisesRegex(RuntimeError, 'did not match its published checksum'):
            noderuntime.fetch(get=self.get_for(blob))
        self.assertEqual(noderuntime.find(), '')

    def test_the_pinned_build_names_this_computers_archive(self):
        self.assertEqual(noderuntime.asset('Windows', 'AMD64'), 'win-x64.zip')
        self.assertEqual(noderuntime.asset('Windows', 'ARM64'), 'win-arm64.zip')
        self.assertEqual(noderuntime.asset('Darwin', 'arm64'), 'darwin-arm64.tar.gz')
        self.assertEqual(noderuntime.asset('Windows', 'x86'), '')


class NpmTests(Base):
    def test_no_git_is_said_plainly_not_as_npm_debug_lines(self):
        why = wabridge.npm_why(NPM_NO_GIT)
        self.assertIn('no Git', why); self.assertNotIn('complete log', why); self.assertNotIn('debug-0.log', why)

    def test_other_npm_failures_keep_what_npm_said_without_the_log_path(self):
        self.assertIn('registry.npmjs.org', wabridge.npm_why('npm ERR! code ENOTFOUND\nnpm ERR! getaddrinfo ENOTFOUND registry.npmjs.org'))
        why = wabridge.npm_why('npm error code E404\nnpm error 404 Not Found\nnpm error A complete log of this run can be found in: x.log')
        self.assertEqual(why, 'npm install failed: code E404 / 404 Not Found')

    def test_a_failed_install_records_the_plain_reason_and_logs_npm_raw(self):
        with mock.patch.object(wabridge, 'node', return_value=r'C:\Program Files\nodejs\node.exe'), \
             mock.patch.object(wabridge, 'npm', return_value='npm.cmd'), mock.patch.object(wabridge, 'stage', return_value=Path('.')), \
             mock.patch.object(wabridge.spawn, 'run', return_value=mock.Mock(returncode=1, stdout='', stderr=NPM_NO_GIT)) as run:
            out = wabridge.start(wait=True, force_install=True)
        self.assertEqual(out['phase'], 'failed'); self.assertIn('no Git', out['detail'])
        self.assertTrue(run.call_args.kwargs['env']['PATH'].startswith(r'C:\Program Files\nodejs'), "npm's scripts find the node it found")
        self.assertTrue(any('spawn git' in l for l in self.said), "npm's own words stay in the app log")

    def test_no_npm_beside_node_is_plain(self):
        with mock.patch.object(wabridge, 'node', return_value=r'C:\nodejs\node.exe'), mock.patch.object(wabridge, 'npm', return_value=''), \
             mock.patch.object(wabridge, 'stage', return_value=Path('.')):
            out = wabridge.start(wait=True, force_install=True)
        self.assertIn('npm is missing beside Node', out['detail'])

    def test_the_bridge_installs_without_git(self):
        """Baileys asks for libsignal as git+https, which npm can only fetch with Git - an ordinary computer has none (#278)."""
        pkg = json.loads((wabridge.DIR / 'package.json').read_text(encoding='utf-8'))
        sig = pkg['overrides']['libsignal']
        self.assertTrue(sig.startswith('https://') and 'git' not in sig.split('://', 1)[0], sig)


class DownTests(Base):
    def test_chats_while_down_is_a_plain_line_not_a_409(self):
        s = MemoryStore(); wa = s.get_connector_by_type('whatsapp')
        down = messengers.BridgeDown('the WhatsApp bridge is not running at http://127.0.0.1:8977 - Restart bridge starts it')
        with mock.patch.object(server, 'store', s), mock.patch.object(messengers, '_wa', side_effect=down):
            r = c_api.get(f"/api/connectors/{wa['ConnectorId']}/wa/chats")
            self.assertEqual(r.status_code, 200)
            self.assertEqual((r.json()['data'], r.json()['down']), ([], True))
            self.assertTrue(r.json()['detail'].startswith("WhatsApp isn't running - press Start bridge on the WhatsApp card"))
            self.assertNotIn('127.0.0.1', r.json()['detail'])
            wabridge._set('failed', 'Node.js is not installed on this computer')
            self.assertIn('The last start failed: Node.js is not installed', c_api.get(f"/api/connectors/{wa['ConnectorId']}/wa/chats").json()['detail'])

    def test_a_down_local_bridge_costs_half_a_second_not_windows_two(self):
        seen = {}
        def get(url, timeout=None, headers=None): seen['t'] = timeout; raise messengers.requests.ConnectionError('refused')
        with mock.patch.object(messengers.requests, 'get', side_effect=get), self.assertRaises(messengers.BridgeDown):
            messengers._wa({'ConfigJson': '{}'}, '/status')
        self.assertEqual(seen['t'], (.5, 20))
        with mock.patch.object(messengers.requests, 'get', side_effect=get), self.assertRaises(messengers.BridgeDown):
            messengers._wa({'ConfigJson': json.dumps({'bridge_url': 'http://wa-box.example:8977'})}, '/status')
        self.assertEqual(seen['t'], 20, 'a bridge on another machine keeps the usual connect time')
