"""A COMPUTER WITH NO BROWSER FOR AGENTS IS GIVEN ONE (2026-11-09). An agent on an API card, asked to check something on a website on a
computer where nobody had installed agent-browser, answered "the agent browser is not set up - set it up under Connections?" and, told
yes, sent the owner to a card that prints an npm command. Nothing was wrong with the AI: the browser is a program, and only a person at
a terminal ever put it there. Now Taskuary fetches its own (browserruntime) - the agent is handed the browser tools all the same, the
first call waits for the download with its steps said in the turn, and a download that cannot be made is said with its real reason.
"""
import hashlib, io, os, tarfile, tempfile, threading, time, unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from taskuary import apiagent, browserruntime as rt, browserview as bv, general, llm
from taskuary.store import MemoryStore

BLOB = b'MZ the program itself'
ASSET = rt.asset                # the real one: Base pins this computer's
ASK = 'log into the scheduling portal and read the denials'


class Resp:
    def __init__(self, blob, status=200): self.blob, self.status, self.headers = blob, status, {'content-length': str(len(blob))}
    def raise_for_status(self):
        if self.status != 200:
            import requests
            raise requests.HTTPError(f'{self.status} for url')
    def iter_content(self, n): yield self.blob


def npm_pack(a, blob=BLOB):
    b = io.BytesIO()
    with tarfile.open(fileobj=b, mode='w:gz') as t:
        i = tarfile.TarInfo(f'package/bin/agent-browser-{a}'); i.size = len(blob); t.addfile(i, io.BytesIO(blob))
    return b.getvalue()


class Base(unittest.TestCase):
    def setUp(self):
        d = tempfile.TemporaryDirectory(ignore_cleanup_errors=True); self.addCleanup(d.cleanup)
        self.home, self.a = Path(d.name), rt.asset() or 'linux-x64'
        for p in (mock.patch.object(rt, 'home', return_value=self.home), mock.patch.object(rt, 'on_path'),
                  mock.patch.object(rt, 'asset', return_value=self.a), mock.patch.object(bv, 'home', return_value=self.home / 'ab'),
                  mock.patch.dict(rt.SHA256, {self.a: hashlib.sha256(BLOB).hexdigest()}),
                  mock.patch.dict(rt._STATE, {'line': '', 'failed': '', 'at': 0.0}), mock.patch.dict(os.environ, {'AGENT_BROWSER_EXECUTABLE_PATH': ''})):
            p.start(); self.addCleanup(p.stop)

    def chrome_ok(self, cmd): (self.home / 'ab' / 'browsers' / 'chrome-150.0.1').mkdir(parents=True); return SimpleNamespace(returncode=0, stdout='', stderr='')


class TheProgramTests(Base):
    "browserruntime.fetch: one native file, from GitHub or from inside the npm package, kept only when its sha256 is the pinned one."

    def test_every_platform_agent_browser_ships_is_pinned_and_the_rest_are_said(self):
        for s, m, libc, want in (('Windows', 'AMD64', '', 'win32-x64.exe'), ('Windows', 'ARM64', '', 'win32-x64.exe'), ('Darwin', 'arm64', '', 'darwin-arm64'),
                                 ('Darwin', 'x86_64', '', 'darwin-x64'), ('Linux', 'x86_64', 'glibc', 'linux-x64'), ('Linux', 'aarch64', 'glibc', 'linux-arm64'),
                                 ('Linux', 'x86_64', '', 'linux-musl-x64'), ('Linux', 'riscv64', 'glibc', ''), ('FreeBSD', 'amd64', '', '')):
            self.assertEqual(ASSET(s, m, libc), want, (s, m)); self.assertTrue(not want or len(rt.SHA256[want]) == 64)

    def test_the_github_file_is_checked_and_kept(self):
        asked, said = [], []
        def get(url): asked.append(url); return Resp(BLOB)
        exe = rt.fetch(said.append, get)
        self.assertEqual(Path(exe).read_bytes(), BLOB); self.assertEqual(rt.find(), exe); self.assertTrue(rt.mine(exe))
        self.assertEqual(asked, [f'{rt.GITHUB}/v{rt.VERSION}/agent-browser-{self.a}']); self.assertIn('one time', said[0])
        self.assertEqual(rt.fetch(get=lambda url: self.fail('fetched twice')), exe)

    def test_a_firewall_that_blocks_github_still_gets_it_from_npm(self):
        def get(url):
            if 'github.com' in url:
                import requests
                raise requests.ConnectionError('refused')
            return Resp(npm_pack(self.a))
        self.assertEqual(Path(rt.fetch(get=get)).read_bytes(), BLOB)

    def test_a_file_that_is_not_the_published_one_is_thrown_away_and_the_reason_is_plain(self):
        with self.assertRaises(RuntimeError) as e: rt.fetch(get=lambda url: Resp(b'something else') if 'github' in url else Resp(b'', 503))
        self.assertIn('did not match its published checksum', str(e.exception)); self.assertIn('company firewall', str(e.exception))
        self.assertEqual(rt.find(), '')

    def test_a_test_never_downloads_it(self):
        with self.assertRaises(RuntimeError): rt.fetch()
        self.assertFalse(rt.can())


class TheSetUpTests(Base):
    "browserruntime.ensure: the program and its Chrome, one set-up at a time, every waiter hearing where it is."

    def test_the_program_then_chrome_and_it_is_whole(self):
        said, ran = [], []
        def run(cmd): ran.append(cmd); return self.chrome_ok(cmd)
        exe = rt.ensure(said.append, lambda url: Resp(BLOB), run)
        self.assertEqual(ran, [[exe, 'install']]); self.assertTrue(rt.whole())
        self.assertIn('downloading Chrome', ' '.join(said)); self.assertEqual(said[-1], 'The browser is set up')
        with mock.patch.object(bv.shutil, 'which', return_value=None): self.assertTrue(bv.installed()); self.assertEqual(bv.program(), exe)
        rt.ensure(get=lambda url: self.fail('fetched twice'), run=lambda cmd: self.fail('installed twice'))

    def test_chrome_that_would_not_download_is_said_and_the_browser_is_not_called_installed(self):
        no = SimpleNamespace(returncode=1, stdout='', stderr='error: failed to download Chrome: connection reset')
        with self.assertRaises(RuntimeError) as e: rt.ensure(get=lambda url: Resp(BLOB), run=lambda cmd: no)
        self.assertIn('connection reset', str(e.exception)); self.assertIn('company firewall', str(e.exception))
        self.assertFalse(rt.whole()); self.assertIn('connection reset', rt._STATE['failed'])
        with mock.patch.object(bv.shutil, 'which', return_value=rt.find()): self.assertFalse(bv.installed())        # ours on PATH, no Chrome: not yet
        with mock.patch.object(bv.shutil, 'which', return_value=str(self.home.parent / 'npm' / 'agent-browser.cmd')): self.assertTrue(bv.installed())

    def test_a_turn_that_needs_it_joins_the_download_already_under_way(self):
        go, heard, fetched = threading.Event(), [], []
        def get(url): fetched.append(url); rt._tell('Setting up the browser - downloading agent-browser (one time)'); go.wait(5); return Resp(BLOB)
        t = threading.Thread(target=lambda: rt.ensure(get=get, run=self.chrome_ok)); t.start()
        while not fetched: time.sleep(.01)
        u = threading.Thread(target=lambda: rt.ensure(heard.append, get=lambda url: self.fail('a second download'), run=lambda c: self.fail('a second install')))
        u.start()
        while not heard: time.sleep(.01)
        go.set(); t.join(5); u.join(5)
        self.assertIn('downloading agent-browser', heard[0]); self.assertEqual(len(fetched), 1); self.assertTrue(rt.whole())

    def test_the_way_in_says_why_in_words_and_the_background_try_is_not_made_every_keystroke(self):
        with mock.patch.object(rt, 'ensure', side_effect=RuntimeError('agent-browser could not be downloaded (GitHub: refused)')), \
             mock.patch.object(bv.shutil, 'which', return_value=None):        # the owner's own install is not this computer's story
            self.assertIn('GitHub: refused', bv.set_up())
        with mock.patch.object(rt, 'whole', return_value=True): self.assertEqual(bv.set_up(), '')
        made = []
        with mock.patch.object(rt.threading, 'Thread', side_effect=lambda **kw: made.append(kw) or mock.Mock()):
            self.assertTrue(rt.start()); self.assertFalse(rt.start())
        self.assertEqual(len(made), 1)


class Brain:
    "A card that takes tools: it opens the portal, then answers."
    def __init__(self): self.seen, self.steps = [], iter([{'tool_calls': [{'id': 'c1', 'function': {'name': 'browser_open', 'arguments': '{"url": "portal.example"}'}}]}])
    def chat(self, msgs, tools, max_tokens, **kw):
        self.seen.append((msgs[0]['content'], [t['function']['name'] for t in tools], msgs[-1]))
        return next(self.steps, {'content': 'Read it.'})


class TheCardAgentTests(unittest.TestCase):
    "THE LIVE SHAPE: an API card on a task that needs a website, on a computer with no agent-browser."

    def turn(self, why=''):
        s = MemoryStore()
        tid = s.create_task({'Title': 'Read the denials on the scheduling portal', 'Summary': 'go', 'Kind': 'general', 'Status': 'open'}, 'owner')
        sess = general.GeneralSession(s, tid)
        sess.pick, sess.provider, sess.model = 'connector:1', 'HIPAA AI', ''
        brain, here = Brain(), {'yes': False}
        def set_up(say=None):
            if say: say('Setting up the browser - downloading Chrome (one time, about 170 MB)')
            here['yes'] = not why
            return why
        with mock.patch.object(llm, 'build_llm', return_value=brain), mock.patch.object(bv, 'installed', side_effect=lambda: here['yes']), \
             mock.patch.object(bv, 'can_set_up', side_effect=lambda: not here['yes']), mock.patch.object(bv, 'set_up', side_effect=set_up) as wait, \
             mock.patch.object(bv, 'set_up_soon', return_value='') as soon, mock.patch.object(bv, 'state', return_value={'open': False}), \
             mock.patch.object(bv, 'start', return_value=True) as start, mock.patch('taskuary.browsergate.check', return_value=None), \
             mock.patch('taskuary.browsergate._run', return_value=(0, '- heading "Denials"')), mock.patch('taskuary.browsergate.address', return_value='https://portal.example/'), \
             mock.patch.object(apiagent, 'taskuary_tools', return_value=[]):
            sess.send_prompt(ASK, echo=False)
        return sess, brain, SimpleNamespace(wait=wait, soon=soon, start=start)

    def test_it_is_handed_the_browser_and_never_told_to_send_the_owner_to_install_one(self):
        sess, brain, m = self.turn()
        system, names, _ = brain.seen[0]
        self.assertIn(apiagent.BRIEF, system); self.assertIn('browser_open', names)
        self.assertNotIn('NO BROWSER FOR AGENTS', system); self.assertNotIn('Set up the agent browser', system)
        m.soon.assert_called()                                                         # the download began with the turn, behind it

    def test_its_first_browser_call_waits_for_the_download_and_the_turn_says_so(self):
        sess, brain, m = self.turn()
        m.wait.assert_called_once(); m.start.assert_called_once()                      # set up, THEN opened
        self.assertIn('PAGE https://portal.example/', brain.seen[1][2]['content'])
        said = [e['detail'] for e in sess.trace if e['type'] == 'progress' and e['name'] == 'browser']
        self.assertTrue(any('downloading Chrome' in str(d) for d in said), sess.trace)
        self.assertFalse(any(general.NO_BROWSER_LINE in str(e.get('detail')) for e in sess.trace), 'the AI was never the problem')

    def test_a_download_that_cannot_be_made_reaches_the_agent_with_its_real_reason(self):
        why = 'agent-browser could not be downloaded (GitHub: refused; npm: refused) - check the internet connection, a VPN, or a company firewall'
        sess, brain, m = self.turn(why)
        back = brain.seen[1][2]['content']
        self.assertIn(why, back); self.assertIn('never send them to a settings page', back); m.start.assert_not_called()


class TheCliAgentTests(unittest.TestCase):
    "The same computer, a CLI agent: its `agent-browser` is a command in its own shell, so the program has to BE there."

    def turn(self, wanted, why='', failed=''):
        from test_general import connect_cli
        from test_signup_from_a_message import world
        connect_cli(self, claude={'cmd': 'claude', 'args': ['-p']})
        s, tid, _, _ = world()
        sess = general.GeneralSession(s, tid, pick='cli:claude')
        sess.browser_wanted, seen, here = wanted, {}, {'yes': False}
        def answer(system, user, **kw): seen.update(system=system); return 'Done.'
        def set_up(say=None):
            if say: say('Setting up the browser - downloading agent-browser (one time)')
            here['yes'] = not why
            return why
        with mock.patch.object(bv, 'start') as start, mock.patch.object(bv, 'installed', side_effect=lambda: here['yes']), \
             mock.patch.object(bv, 'can_set_up', side_effect=lambda: not here['yes']), mock.patch.object(bv, 'set_up', side_effect=set_up) as wait, \
             mock.patch.object(bv, 'set_up_soon', return_value=failed) as soon, mock.patch.object(bv, 'last_page', return_value=''), \
             mock.patch.object(bv, 'state', return_value={'open': False, 'url': '', 'port': 1}), mock.patch.object(bv, 'keep_page'), \
             mock.patch.object(llm, 'build_llm', return_value=answer):
            sess.send_prompt('Sign me up for the webinar in its mail and prepare the registration for my approval', pick='cli:claude')
        return sess, seen['system'], SimpleNamespace(wait=wait, soon=soon, start=start)

    def test_a_task_that_asked_for_a_browser_waits_for_it_and_is_then_offered_it(self):
        sess, system, m = self.turn(wanted=True)
        m.wait.assert_called_once(); self.assertIn('NO BROWSER IS OPEN', system); self.assertNotIn('DID NOT OPEN', system)
        self.assertTrue(any(e.get('name') == 'browser' and 'downloading agent-browser' in str(e.get('detail')) for e in sess.trace))

    def test_one_that_could_not_be_set_up_says_the_real_reason(self):
        sess, system, m = self.turn(wanted=True, why='Chrome could not be downloaded (connection reset)')
        self.assertIn('THE BROWSER DID NOT OPEN for this task (Chrome could not be downloaded (connection reset))', system)
        self.assertNotIn('install agent-browser under', system)

    def test_a_task_only_offered_it_is_not_held_up_and_is_told_it_is_on_its_way(self):
        sess, system, m = self.turn(wanted=False)
        m.wait.assert_not_called(); m.soon.assert_called_once()
        self.assertIn('NO BROWSER IS OPEN', system); self.assertIn('IT IS STILL BEING SET UP', system); self.assertNotIn('install agent-browser under', system)
        # ...and the turn says it at once, under its header (the owner, 2026-11-10: "check why it did not start right away")
        self.assertIn(bv.GETTING, [e.get('detail') for e in sess.trace if e.get('name') == 'browser'])

    def test_and_when_the_last_try_failed_it_is_told_why_not_that_it_is_coming(self):
        sess, system, m = self.turn(wanted=False, failed='agent-browser could not be downloaded (GitHub: refused)')
        self.assertIn('Taskuary tried to set its own up and could not (agent-browser could not be downloaded (GitHub: refused))', system)
        self.assertNotIn('IT IS STILL BEING SET UP', system); self.assertNotIn('install agent-browser under', system)


if __name__ == '__main__': unittest.main()
