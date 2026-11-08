"""A VENDOR'S OWN REMOTE MCP SERVER (remotemcp.py, the owner 2026-11-08): the catalogue's `mcp` rows, added to the agent CLIs here and signed
in to with one press - every command stood in for, nothing installed and nothing reached."""
import json, tempfile, unittest
from pathlib import Path
from unittest import mock
from urllib.parse import urlparse

from taskuary import connectorcatalog, remotemcp as rm, sendfilter, videotools as vt
from taskuary.store import MemoryStore

EXE = {'claude': r'C:\bin\claude.exe', 'codex': r'C:\bin\codex.exe', 'git': 'git', 'uv': r'C:\bin\uv.exe', 'ffmpeg': r'C:\bin\ffmpeg.exe'}


class Machine:
    "A computer as the card sees it: which programs are here, which servers each CLI has, and a skills folder of its own."
    def __init__(self, have=EXE, claude=(), codex=()):
        self.have, self.servers, self.ran = dict(have), {'claude': set(claude), 'codex': set(codex)}, []
        self.root = Path(tempfile.mkdtemp(prefix='tq-skills-'))
    def run(self, argv, cwd=None, timeout=0):
        self.ran.append((list(argv), cwd))
        if argv[1:3] == ['mcp', 'add']: self.servers['claude' if 'claude' in argv[0] else 'codex'].add(argv[-2] if 'claude' in argv[0] else argv[3])
        if argv[1] == 'clone': (Path(argv[-1])).mkdir(parents=True); (Path(argv[-1]) / 'SKILL.md').write_text('x')
        return 0, 'ok'
    def __enter__(self):
        self.ps = [mock.patch.object(rm, '_which', side_effect=lambda c: self.have.get(c, '')),
                   mock.patch.object(vt, 'skills_root', return_value=self.root),
                   mock.patch.object(sendfilter, 'claude_servers', side_effect=lambda: {n: {} for n in self.servers['claude']}),
                   mock.patch.object(sendfilter, 'codex_servers', side_effect=lambda: {n: {} for n in self.servers['codex']}),
                   mock.patch.object(rm, 'signed_in', side_effect=lambda c, n: (c, n) in self.signed)]
        self.signed = set()
        for p in self.ps: p.start()
        return self
    def __exit__(self, *a):
        for p in self.ps: p.stop()


class TheMcpRoad(unittest.TestCase):
    def test_each_cli_gets_its_own_spelling(self):
        self.assertEqual(rm.add_argv('claude', 'claude', 'invideo', 'https://mcp.invideo.io/mcp'),
                         ['claude', 'mcp', 'add', '--transport', 'http', '--scope', 'user', 'invideo', 'https://mcp.invideo.io/mcp'])
        self.assertEqual(rm.add_argv('codex', 'codex', 'invideo', 'https://mcp.invideo.io/mcp'),
                         ['codex', 'mcp', 'add', 'invideo', '--url', 'https://mcp.invideo.io/mcp'])

    def test_add_registers_where_missing_keeps_it_for_the_send_filter_and_turns_the_card_on(self):
        s = MemoryStore()
        with Machine(claude={'descript'}) as m:                          # already in Claude Code, not in Codex
            self.assertFalse(rm.state(s, 'descript')['ready'])            # ...so Add still has Codex to do
            out = rm.add(s, 'descript', runner=m.run)
        self.assertEqual([a[0] for a, _ in m.ran], [EXE['codex']])        # only the CLI that lacked it was touched
        self.assertEqual(m.ran[0][0][1:], ['mcp', 'add', 'descript', '--url', 'https://api.descript.com/v2/mcp'])
        self.assertTrue(out['ready'] and all(v['added'] for v in out['clis'].values()))
        self.assertIn('codex mcp login descript', ' '.join(out['sign_in']))
        self.assertEqual(json.loads(s.get_setting(sendfilter.OVERRIDES))['descript/*'], 'keep')
        self.assertTrue(s.get_connector_by_type('descript')['Active'])
        with Machine(claude={'descript'}, codex={'descript'}): self.assertIn('ready in Claude Code, Codex', rm.test(s, 'descript'))

    def test_no_agent_cli_here_says_so_and_adds_nothing(self):
        s = MemoryStore()
        with Machine(have={}) as m:
            st = rm.add(s, 'invideo', runner=m.run)
            with self.assertRaises(RuntimeError): rm.test(s, 'invideo')
        self.assertEqual((m.ran, st['ready'], st['missing']), ([], False, ['Claude Code or Codex on this computer']))
        self.assertFalse(s.get_setting(sendfilter.OVERRIDES))
        self.assertFalse(s.get_connector_by_type('invideo')['Active'])

    def test_the_demo_shows_nobodys_machine_and_installs_nothing(self):
        with mock.patch('taskuary.demo.enabled', return_value=True), Machine(claude={'opusclip'}) as m:
            self.assertEqual((rm.state(MemoryStore(), 'opusclip')['clis'], rm.state(MemoryStore(), 'opusclip')['demo']), ({}, True))
            with self.assertRaises(RuntimeError): rm.add(MemoryStore(), 'opusclip', runner=m.run)
        self.assertEqual(m.ran, [])


class SignInOnePress(unittest.TestCase):
    "The card's Sign in: each CLI that has the server runs its own `mcp login` (the browser opens), and the card says Signed in once it is."
    class P:
        def __init__(self): self.rc = None
        def poll(self): return self.rc
        def kill(self): self.rc = -9

    def setUp(self): rm.LOGINS.clear()

    def test_one_press_starts_each_clis_login_once_and_the_card_says_signed_in(self):
        s, started = MemoryStore(), []
        start = lambda argv: started.append(argv) or self.P()
        with Machine(claude={'descript'}, codex={'descript'}) as m:
            m.signed.add(('codex', 'descript'))                                  # Codex is signed in already
            out = rm.sign_in(s, 'descript', start=start)
            self.assertEqual(started, [[EXE['claude'], 'mcp', 'login', 'descript']])
            self.assertEqual((out['said'], out['clis']['claude']['signing_in']), (['Claude Code: sign-in opened in your browser'], True))
            self.assertEqual(rm.sign_in(s, 'descript', start=start)['said'], ['The sign-in is open in your browser'])    # never twice
            rm.LOGINS[('claude', 'descript')][0].rc = 0; m.signed.add(('claude', 'descript'))
            st = rm.state(s, 'descript')
            self.assertTrue(all(v['signed_in'] and not v['signing_in'] for v in st['clis'].values()))
            self.assertEqual((st['sign_in'], rm.sign_in(s, 'descript', start=start)['said']), ([], ['Already signed in']))
        self.assertEqual(len(started), 1)

    def test_nothing_added_nothing_signs_in_and_a_left_page_is_let_go(self):
        with Machine() as m:
            self.assertEqual(rm.sign_in(MemoryStore(), 'invideo', start=lambda a: 1 / 0)['said'], ['Add it first - there is nothing to sign in to yet'])
        p = rm.LOGINS[('claude', 'x')] = (self.P(), 0)
        self.assertFalse(rm.signing_in('claude', 'x')); self.assertEqual(p[0].rc, -9)

    def test_only_the_owner_presses_it_and_the_demo_signs_in_nothing(self):
        from taskuary import guard
        self.assertTrue(guard.denied('POST', '/api/connectors/7/tool/sign-in'))
        with mock.patch('taskuary.demo.enabled', return_value=True), self.assertRaises(RuntimeError): rm.sign_in(MemoryStore(), 'opusclip')

    def test_the_clis_own_record_says_who_is_signed_in(self):
        d = Path(tempfile.mkdtemp(prefix='tq-claude-'))
        (d / '.credentials.json').write_text(json.dumps({'mcpOAuth': {'descript|ab12': {'serverName': 'descript', 'accessToken': 't'},
                                                                      'invideo|cd34': {'serverName': 'invideo', 'accessToken': ''}}}))
        with mock.patch('taskuary.climodels.claude_home', return_value=d):
            self.assertEqual((rm.signed_in('claude', 'descript'), rm.signed_in('claude', 'invideo')), (True, False))
        with mock.patch('taskuary.climodels.claude_home', return_value=d / 'none'): self.assertIsNone(rm.signed_in('claude', 'descript'))
        listed = json.dumps([{'name': 'descript', 'auth_status': 'o_auth'}, {'name': 'invideo', 'auth_status': 'not_logged_in'}])
        with mock.patch('taskuary.spawn.run', return_value=mock.Mock(stdout=listed)) as run, mock.patch.object(rm, '_which', return_value='codex'):
            self.assertEqual((rm.signed_in('codex', 'descript'), rm.signed_in('codex', 'invideo')), (True, False))
        self.assertEqual(run.call_args[0][0], ['codex', 'mcp', 'list', '--json'])


class TheTableIsTheCatalogue(unittest.TestCase):
    "Every server is a working catalogue card with a title, an https URL and the vendor's own page it was read off, and each CLI is told it right."
    def test_every_row_is_a_working_card_with_an_https_url(self):
        self.assertGreaterEqual(len(rm.MCPS), 40)
        for t, (title, url) in rm.MCPS.items():
            c = connectorcatalog.by_type(t)
            self.assertTrue(title.strip() and c and c['planned'] is False and c['title'] == title, t)
            self.assertEqual(urlparse(url).scheme, 'https', t); self.assertTrue(urlparse(url).netloc, t)
            self.assertEqual(urlparse(c['mcp']['docs']).scheme, 'https', t)
            self.assertIn('Sign in', c['desc'], t)
            self.assertRegex(t, r'^[a-z][a-z0-9_]*$')                     # the type is the CLI's server name

    def test_every_row_is_seeded_and_rides_this_road(self):
        have = {c['Type'] for c in MemoryStore().list_connectors()}
        self.assertEqual(sorted(set(rm.MCPS) - have), [])
        self.assertTrue(all(rm.road(t) in (rm, vt) for t in rm.MCPS))
        self.assertIs(rm.road('vidova'), vt); self.assertIs(rm.road('notion_mcp'), rm); self.assertIsNone(rm.road('outlook'))

    def test_add_and_sign_in_argv_for_every_row(self):
        for t, (_, url) in rm.MCPS.items():
            s, started = MemoryStore(), []
            with Machine() as m:
                out = rm.road(t).add(s, t, runner=m.run)
                self.assertEqual([a for a, _ in m.ran[:2]], [[EXE['claude'], 'mcp', 'add', '--transport', 'http', '--scope', 'user', t, url],
                                                             [EXE['codex'], 'mcp', 'add', t, '--url', url]], t)
                self.assertEqual(json.loads(s.get_setting(sendfilter.OVERRIDES))[f'{t}/*'], 'keep')
                rm.LOGINS.clear()
                rm.sign_in(s, t, start=lambda argv: started.append(argv) or SignInOnePress.P())
            self.assertEqual(started, [[EXE['claude'], 'mcp', 'login', t], [EXE['codex'], 'mcp', 'login', t]], t)
            self.assertTrue(all(v['added'] for v in out['clis'].values()), t)
        rm.LOGINS.clear()

    def test_the_card_test_branch_and_the_page_reach_them(self):
        from taskuary import channels
        s = MemoryStore(); cid = s.get_connector_by_type('notion_mcp')['ConnectorId']
        with Machine(claude={'notion_mcp'}, codex={'notion_mcp'}):
            out = channels.test_connector(s, cid)
        self.assertTrue(out['ok'], out); self.assertIn('Notion MCP is ready in Claude Code, Codex', out['detail'])
        native = connectorcatalog.by_type('notion')
        self.assertFalse(native.get('mcp') or native['planned'])          # the Notion feed card stays as it was, beside its server


if __name__ == '__main__':
    unittest.main()
