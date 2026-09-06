"""Keep the test process inside disposable data, user-config, and I/O boundaries.

This module is imported before test collection, which matters because ``server.py`` loads its
config and opens SQLite at import time.  The guards below are deliberately test-side: production
code does not gain a pytest switch and a unit test can still replace a guarded boundary with its
own fake.  Real local services are reachable only after a test registers its ephemeral port.
"""
import hashlib, os, platform, shutil, socket, subprocess, sys, tempfile, uuid
from contextlib import asynccontextmanager
from contextlib import ExitStack
from pathlib import Path
from unittest import mock
from urllib.parse import urlsplit

# P0-ISOLATION: always allocate the suite's homes ourselves.  An arbitrary inherited
# TASKUARY_TEST_HOME is not evidence that a path is disposable; accepting one here reopened the
# same class of door that the original TASKUARY_HOME guard closed.  HOME/USERPROFILE matter too:
# terminal.pretrust writes ~/.claude.json and provider SDKs use per-user config outside Taskuary.
_TEST_ROOT = Path(tempfile.mkdtemp(prefix='taskuary_pytest_')).resolve()
_TASKUARY_HOME = _TEST_ROOT / 'taskuary'
_USER_HOME = _TEST_ROOT / 'user'
_TEMP_HOME = _TEST_ROOT / 'tmp'
for _path in (_TASKUARY_HOME, _USER_HOME, _TEMP_HOME):
    _path.mkdir(parents=True, exist_ok=True)
os.environ.update({
    'TASKUARY_HOME': str(_TASKUARY_HOME),
    'TASKUARY_TEST_HOME': str(_TASKUARY_HOME),
    'HOME': str(_USER_HOME),
    'USERPROFILE': str(_USER_HOME),
    'XDG_CONFIG_HOME': str(_USER_HOME / '.config'),
    'XDG_DATA_HOME': str(_USER_HOME / '.local' / 'share'),
    'APPDATA': str(_USER_HOME / 'AppData' / 'Roaming'),
    'LOCALAPPDATA': str(_USER_HOME / 'AppData' / 'Local'),
    'CODEX_HOME': str(_USER_HOME / '.codex'),
    'CLAUDE_CONFIG_DIR': str(_USER_HOME / '.claude'),
    'AGENT_BROWSER_HOME': str(_USER_HOME / '.agent-browser'),
    'TASKUARY_HOST': '127.0.0.1', 'TASKUARY_PORT': '0',
    'TASKUARY_TOKEN': 'pytest-owner-token',
    'GIT_CONFIG_GLOBAL': os.devnull, 'GIT_CONFIG_SYSTEM': os.devnull,
    'GIT_CONFIG_NOSYSTEM': '1', 'GIT_TERMINAL_PROMPT': '0',
    'TMP': str(_TEMP_HOME), 'TEMP': str(_TEMP_HOME), 'TMPDIR': str(_TEMP_HOME),
})
tempfile.tempdir = str(_TEMP_HOME)
os.environ.pop('TASKUARY_ALLOW_TEST_HOME', None)
os.environ.pop('TASKUARY_DEMO', None)
os.environ.pop('TASKUARY_API', None)

# The console ``pytest`` entrypoint does not prepend cwd like ``python -m pytest``.
# An editable install may point at the owner's other checkout: always test THIS
# worktree, and fail rather than mix already-imported application modules.
_CHECKOUT_ROOT = Path(__file__).resolve().parents[1]
_loaded_package = sys.modules.get('taskuary')
if _loaded_package is not None:
    if Path(getattr(_loaded_package, '__file__', '')).resolve().parent != _CHECKOUT_ROOT / 'taskuary':
        raise RuntimeError('Taskuary was imported from another checkout before test isolation')
sys.path.insert(0, str(_CHECKOUT_ROOT))

# Cache the read-only platform probe before the subprocess guard is installed.  On Windows,
# ``platform`` otherwise invokes ``ver`` lazily while numpy/botocore are imported by tests.
platform.uname()

# ...and this server answers to the name the test client calls it by. starlette's TestClient sends
# `Host: testserver` (hardcoded for websockets), and token_gate now refuses a Host it does not
# recognise - that is the DNS-rebinding rule, and declaring the name is exactly how a self-hoster
# satisfies it too. Written into the test home's own config, so nothing in taskuary/ knows pytest exists.
_cfg = _TASKUARY_HOME / 'config.toml'
if not _cfg.exists():
    _cfg.parent.mkdir(parents=True, exist_ok=True)
    _cfg.write_text('[server]\nallowed_hosts = "testserver"\n', encoding='utf-8')


import pytest


_ALLOWED_PORTS = set()
_SAFETY_EVENTS = []
_LIFESPAN_DONE = []


def _port_of(url) -> tuple[str, int | None]:
    raw = getattr(url, 'full_url', url)
    try:
        parsed = urlsplit(str(raw))
        return (parsed.hostname or '').lower(), parsed.port or (443 if parsed.scheme == 'https' else 80)
    except (TypeError, ValueError):
        return '', None


def _local_allowed(url) -> bool:
    host, port = _port_of(url)
    return host in {'127.0.0.1', 'localhost', '::1'} and port in _ALLOWED_PORTS


def _blocked(kind, target):
    _SAFETY_EVENTS.append((kind, str(target)))
    raise AssertionError(f'P0-ISOLATION blocked unmocked {kind}: {target}')


@pytest.fixture
def allow_test_port():
    """Register a harness-owned loopback port for real HTTP in one test."""
    made = []
    def allow(port):
        port = int(port)
        _ALLOWED_PORTS.add(port); made.append(port)
        return port
    yield allow
    for port in made: _ALLOWED_PORTS.discard(port)


@pytest.fixture
def isolated_process_env(tmp_path):
    """Build a distinct environment for a browser/CLI fixture subprocess before it imports."""
    made = 0
    ports = []
    def build(*, port=None):
        nonlocal made
        made += 1
        home = tmp_path / f'process-{made}-{uuid.uuid4().hex}'
        user = home / 'user'
        user.mkdir(parents=True)
        env = os.environ.copy()
        env.update({'TASKUARY_HOME': str(home / 'taskuary'), 'TASKUARY_TEST_HOME': str(home / 'taskuary'),
                    'HOME': str(user), 'USERPROFILE': str(user),
                    'XDG_CONFIG_HOME': str(user / '.config'), 'XDG_DATA_HOME': str(user / '.local' / 'share'),
                    'APPDATA': str(user / 'AppData' / 'Roaming'), 'LOCALAPPDATA': str(user / 'AppData' / 'Local'),
                    'CODEX_HOME': str(user / '.codex'), 'CLAUDE_CONFIG_DIR': str(user / '.claude'),
                    'AGENT_BROWSER_HOME': str(user / '.agent-browser')})
        env.pop('TASKUARY_ALLOW_TEST_HOME', None)
        if port is not None:
            _ALLOWED_PORTS.add(int(port))
            ports.append(int(port))
            env['TASKUARY_API'] = f'http://127.0.0.1:{int(port)}'
        return env
    yield build
    for port in ports: _ALLOWED_PORTS.discard(port)


@pytest.fixture(scope='session')
def test_safety_events():
    return _SAFETY_EVENTS


@pytest.fixture(autouse=True)
def no_background_lifespan_overlap():
    """A desktop test must finish server cleanup before the next test uses real boundaries."""
    from taskuary import server
    assert server._open_drain_workers(server.store), \
        'P0-ISOLATION: a prior triage drain still owns the test store'
    yield
    assert server._close_drain_workers(timeout=15), \
        'P0-ISOLATION: a triage drain worker survived its test store'
    pending = [done for done in list(_LIFESPAN_DONE) if not done.is_set()]
    for done in pending:
        assert done.wait(15), 'P0-ISOLATION: a test server lifespan survived its test'


# The owner token is minted on first run now (guard.ensure_tokens), so every request the suite makes
# has to carry it, exactly as the browser's does. Defaulting it HERE, once, means the 73 TestClients
# in these files go THROUGH the new gate instead of around it; a test about the gate itself passes
# its own headers, which win.
def _client_defaults():
    from starlette.testclient import TestClient
    init = TestClient.__init__
    def patched(self, app, *a, **kw):
        from taskuary import server            # the RUNNING app's token, not config.load()'s: a test that
        tok = server.cfg['server'].get('token') or ''   # mocks config.home() would be handed a fresh stranger
        kw['headers'] = {'X-Taskuary-Token': tok, **(kw.get('headers') or {})}
        return init(self, app, *a, **kw)
    TestClient.__init__ = patched
_client_defaults()


@pytest.fixture(scope='session', autouse=True)
def isolated_runtime_boundaries():
    """Deny real integration side effects unless a test supplies a fake or registered port."""
    import httpx, imaplib, requests, smtplib, urllib.request
    from taskuary import browserview, general, hooks, server, spawn, terminal, waitroom, wabridge

    # Auto-dispatch ships on.  In a suite, both coding and general execution stop at the process
    # boundaries below; switching this off also prevents routine ingest tests from trying at all.
    server.store.set_setting('coder_auto_enabled', '0', 'test')

    real_request = requests.sessions.Session.request
    real_async_request = httpx.AsyncClient.request
    real_urlopen = urllib.request.urlopen
    real_term_init = terminal.Term.__init__
    real_start_session = general.start_session
    real_hook_install = hooks.install
    real_browser_listening = browserview._listening
    real_socket = socket.socket
    real_popen = subprocess.Popen
    real_run = subprocess.run
    real_lifespan = server.app.router.lifespan_context

    def guarded_request(self, method, url, *args, **kwargs):
        if _local_allowed(url): return real_request(self, method, url, *args, **kwargs)
        return _blocked('HTTP request', url)

    async def guarded_async_request(self, method, url, *args, **kwargs):
        if _local_allowed(url): return await real_async_request(self, method, url, *args, **kwargs)
        return _blocked('async HTTP request', url)

    def guarded_urlopen(url, *args, **kwargs):
        if _local_allowed(url): return real_urlopen(url, *args, **kwargs)
        return _blocked('URL open', getattr(url, 'full_url', url))

    def guarded_term_init(self, argv, *args, **kwargs):
        command = str((argv or [''])[0])
        if not reviewed_python(argv):
            return _blocked('PTY worker', command)
        return real_term_init(self, argv, *args, **kwargs)

    def guarded_start_session(store, tid, connector_id=None, model=None, actor='owner', pick=None):
        # the router's UNATTENDED assistant start (ingest._start_general, PW-069) is a process boundary
        # like a PTY: a test that wants it supplies a fake general.start_session. An owner-opened
        # session is ordinary test fixture and passes through.
        if actor == 'router': return _blocked('unattended assistant session', f'task {tid}')
        return real_start_session(store, tid, connector_id, model, actor, pick)

    def guarded_hooks(cwd, *args, **kwargs):
        path = Path(cwd).resolve()
        try: path.relative_to(_TEST_ROOT)
        except ValueError:
            _SAFETY_EVENTS.append(('checkout hook write', str(path)))
            return False
        return real_hook_install(cwd, *args, **kwargs)

    def guarded_browser_listening(port, *args, **kwargs):
        """Treat unregistered browser ports as closed without probing a live owner service."""
        if int(port) not in _ALLOWED_PORTS:
            _SAFETY_EVENTS.append(('browser port probe', str(port)))
            return False
        return real_browser_listening(port, *args, **kwargs)

    class GuardedSocket(real_socket):
        """Register sockets this suite binds and refuse every other outbound connection."""
        def bind(self, address):
            result = super().bind(address)
            try:
                host, _requested = address[:2]
                bound_host, bound_port = self.getsockname()[:2]
                if str(host).lower() in ('127.0.0.1', 'localhost', '::1'):
                    _ALLOWED_PORTS.add(int(bound_port))
                    self._taskuary_test_bound_port = int(bound_port)
            except (TypeError, ValueError, OSError):
                pass
            return result

        def close(self):
            port = getattr(self, '_taskuary_test_bound_port', None)
            try: return super().close()
            finally:
                if port is not None: _ALLOWED_PORTS.discard(port)

        def connect(self, address):
            try: host, port = address[:2]
            except (TypeError, ValueError): return _blocked('socket connection', address)
            if str(host).lower() in ('127.0.0.1', 'localhost', '::1') and int(port) in _ALLOWED_PORTS:
                return super().connect(address)
            return _blocked('socket connection', address)

        def connect_ex(self, address):
            try: host, port = address[:2]
            except (TypeError, ValueError): return _blocked('socket connection', address)
            if str(host).lower() in ('127.0.0.1', 'localhost', '::1') and int(port) in _ALLOWED_PORTS:
                return super().connect_ex(address)
            return _blocked('socket connection', address)

    def reviewed_python(argv) -> bool:
        command = argv if isinstance(argv, (list, tuple)) else [argv]
        first = str(command[0] if command else '')
        try:
            if Path(first).resolve() != Path(sys.executable).resolve(): return False
        except OSError:
            return False
        args = [str(x) for x in command[1:]]
        if args[:1] == ['-c']:
            script = args[1] if len(args) > 1 else ''
            # Exact hashes of the synthetic stdin/PTY programs reviewed at checkpoint 2689679,
            # plus this Phase 0 smoke child.  A general ``python -c`` allowance is equivalent to
            # allowing arbitrary filesystem/network code and would make the worker guard fiction.
            allowed = {
                '372e14b70726ee20d3c35632ce4d20dd7de61f4acd8d7c8d60b7cd48e16fcf2a',
                'd9654ab028598c611dfb7f28692ca2aab94ad74522fd6fb220fb4c41ced56546',
                '0ea7d05f79a04d1b5567ed97b41aa681d97e19672717d56eb6f164992529677a',
                '4566b71160625e3f1df4a23fbb56147d8383127d9ca1904a0cab0ff4b076b8a3',
                'dab9c500adeb071e350431a9fbe44ff835263526a0138d2619b1d1f429a20ec1',
                '68dee9b69f752d374dac47936e99ce9c49d015456eed69645fb02ccefc051da9',
                'c320a2d135b24cd16078748fda3766c4f7cfea989cf972b7b8445691c1c3147d',
                '1d49bd863c94851f635e7c883ee83616632e2e25b027f88bd49ed0b287b69998',
                '16b1b0846cf835e4223510add076f34da0dfae9ef63f1bb6a433ce066ef33810',
                '2e19ecdd6381aa3b76d4f9ba687f84337a6709fd0020dfe484c9db9639d56611',
                'b0b14989db94e37ddeb8e5e2fd65c3d5170201e51bb7d348ae524568706ddb96',
                '8730ce9e504bf70f9fd343b40b17d61eb53c54b9e4e0a07a7b071dc85243d4e4',
                '170bd186aeff081511987dc9a6d61928a9248cc696ed3acd1f2bdbbe81392606',
            }
            trailing = args[2:]
            return (hashlib.sha256(script.encode()).hexdigest() in allowed
                    and all(x in {'exec', '--json', '--skip-git-repo-check'} for x in trailing))
        allowed_files = {Path(__file__).resolve().parent / name
                         for name in ('fake_mcp_server.py', 'fake_tui.py')}
        return len(args) == 1 and Path(args[0]).resolve() in allowed_files

    def git_allowed(argv, kwargs) -> bool:
        command = [str(x) for x in (argv if isinstance(argv, (list, tuple)) else [argv])]
        if Path(command[0]).name.lower() not in ('git', 'git.exe'): return False
        lower = [x.lower() for x in command[1:]]
        read_verbs = {'status', 'diff', 'rev-parse', 'rev-list', 'log', 'show', 'ls-files',
                      'merge-base', 'symbolic-ref', 'for-each-ref'}
        verb = next((x for x in lower if not x.startswith('-') and not Path(x).exists()), '')
        if verb in read_verbs: return True
        if verb == 'clone':
            i = lower.index('clone') + 1
            paths = [Path(x).resolve() for x in command[i + 1:] if not x.startswith('-')]
            if len(paths) < 2: return False
            try:
                for path in paths: path.relative_to(_TEST_ROOT)
            except ValueError: return False
            return True
        cwd = Path(kwargs.get('cwd') or os.getcwd()).resolve()
        if '-c' in lower:
            try: cwd = Path(command[lower.index('-c') + 2]).resolve()
            except (IndexError, OSError): return False
        try: cwd.relative_to(_TEST_ROOT)
        except ValueError: return False
        if verb in {'push', 'fetch', 'pull'}:
            # A URL/scp-like command-line remote bypasses an otherwise local checkout config.
            operands = [x for x in command[1:] if not x.startswith('-')]
            if any('://' in x or ('@' in x and ':' in x) for x in operands): return False
            cfg = cwd / '.git' / 'config'
            try: text = cfg.read_text(encoding='utf-8', errors='replace').lower()
            except OSError: return False
            if '://' in text or 'git@' in text: return False
            normalized = text.replace('\\', '/')
            while '//' in normalized: normalized = normalized.replace('//', '/')
            if _TEST_ROOT.as_posix().lower() not in normalized:
                return False
        return True

    def allowed_process(argv, kwargs) -> bool:
        return reviewed_python(argv) or git_allowed(argv, kwargs)

    def guarded_popen(argv, *args, **kwargs):
        if allowed_process(argv, kwargs): return real_popen(argv, *args, **kwargs)
        return _blocked('subprocess', argv)

    def guarded_run(argv, *args, **kwargs):
        if allowed_process(argv, kwargs): return real_run(argv, *args, **kwargs)
        return _blocked('subprocess', argv)

    def stopped(name):
        def no_op(*_args, **_kwargs):
            _SAFETY_EVENTS.append(('lifespan boundary', name))
            return False
        return no_op

    @asynccontextmanager
    async def safe_lifespan(app):
        # Preserve the production lifespan itself, including cleanup, but replace only the five
        # background integration starters while entering it.  Their direct unit tests still call
        # the real functions outside this narrow context.
        import threading
        done = threading.Event()
        _LIFESPAN_DONE.append(done)
        context = real_lifespan(app)
        try:
            # Patch only __aenter__: all five calls happen before the production lifespan yields.
            # Restore the real functions before the server begins handling test requests so an
            # unjoined desktop thread cannot temporarily change a later direct contract test.
            with mock.patch.object(wabridge, 'start_configured', stopped('WhatsApp bridge')), \
                 mock.patch.object(server, 'catch_up_on_startup', stopped('startup catch-up')), \
                 mock.patch.object(server, 'poll_forever', stopped('poll scheduler')), \
                 mock.patch.object(server, 'quick_forever', stopped('chat poll scheduler')), \
                 mock.patch.object(waitroom, 'watch', stopped('waitroom watcher')):
                entered = await context.__aenter__()
            try:
                yield entered
            except BaseException as error:
                suppress = await context.__aexit__(type(error), error, error.__traceback__)
                if not suppress: raise
            else:
                await context.__aexit__(None, None, None)
        finally:
            done.set()

    with ExitStack() as patches:
        patches.enter_context(mock.patch.object(requests.sessions.Session, 'request', guarded_request))
        patches.enter_context(mock.patch.object(httpx.AsyncClient, 'request', guarded_async_request))
        patches.enter_context(mock.patch.object(urllib.request, 'urlopen', guarded_urlopen))
        patches.enter_context(mock.patch.object(socket, 'socket', GuardedSocket))
        patches.enter_context(mock.patch.object(subprocess, 'Popen', guarded_popen))
        patches.enter_context(mock.patch.object(subprocess, 'run', guarded_run))
        patches.enter_context(mock.patch.object(imaplib, 'IMAP4_SSL', side_effect=lambda *a, **k: _blocked('IMAP connection', a[0] if a else '')))
        patches.enter_context(mock.patch.object(smtplib, 'SMTP', side_effect=lambda *a, **k: _blocked('SMTP connection', a[0] if a else '')))
        patches.enter_context(mock.patch.object(smtplib, 'SMTP_SSL', side_effect=lambda *a, **k: _blocked('SMTP connection', a[0] if a else '')))
        patches.enter_context(mock.patch.object(spawn, 'popen', guarded_popen))
        patches.enter_context(mock.patch.object(terminal.Term, '__init__', guarded_term_init))
        patches.enter_context(mock.patch.object(general, 'start_session', guarded_start_session))
        patches.enter_context(mock.patch.object(hooks, 'install', guarded_hooks))
        patches.enter_context(mock.patch.object(browserview, '_listening', guarded_browser_listening))
        patches.enter_context(mock.patch.object(server.app.router, 'lifespan_context', safe_lifespan))
        yield

    # By this point every test server and PTY should have shut down.  Clean only the exact suite
    # directory allocated above; Windows can retain a short-lived SQLite/ConPTY handle, so cleanup
    # is best effort and never widens to a parent supplied by the environment.
    try: shutil.rmtree(_TEST_ROOT)
    except OSError: pass


@pytest.fixture
def fx():
    """A MemoryStore wrapped in the picture factory. Named pictures (pending_draft,
    running, filed_fyi, ...) are the regression fixtures for Timeline/Board chips."""
    from taskuary.testing import Factory
    return Factory()
