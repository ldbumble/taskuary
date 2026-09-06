"""Keep the test process inside disposable data, user-config, and I/O boundaries.

This module is imported before test collection, which matters because ``server.py`` loads its
config and opens SQLite at import time.  The guards below are deliberately test-side: production
code does not gain a pytest switch and a unit test can still replace a guarded boundary with its
own fake.  Real local services are reachable only after a test registers its ephemeral port.
"""
import os, shutil, socket, sys, tempfile, uuid
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
for _path in (_TASKUARY_HOME, _USER_HOME):
    _path.mkdir(parents=True, exist_ok=True)
os.environ.update({
    'TASKUARY_HOME': str(_TASKUARY_HOME),
    'TASKUARY_TEST_HOME': str(_TASKUARY_HOME),
    'HOME': str(_USER_HOME),
    'USERPROFILE': str(_USER_HOME),
    'XDG_CONFIG_HOME': str(_USER_HOME / '.config'),
    'XDG_DATA_HOME': str(_USER_HOME / '.local' / 'share'),
})
os.environ.pop('TASKUARY_ALLOW_TEST_HOME', None)
os.environ.pop('TASKUARY_DEMO', None)

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


def pytest_configure(config):
    config.addinivalue_line('markers', 'allow_test_worker: allow a disposable Python worker child')


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
    def build(*, port=None):
        nonlocal made
        made += 1
        home = tmp_path / f'process-{made}-{uuid.uuid4().hex}'
        user = home / 'user'
        user.mkdir(parents=True)
        env = os.environ.copy()
        env.update({'TASKUARY_HOME': str(home / 'taskuary'), 'TASKUARY_TEST_HOME': str(home / 'taskuary'),
                    'HOME': str(user), 'USERPROFILE': str(user),
                    'XDG_CONFIG_HOME': str(user / '.config'), 'XDG_DATA_HOME': str(user / '.local' / 'share')})
        env.pop('TASKUARY_ALLOW_TEST_HOME', None)
        if port is not None:
            _ALLOWED_PORTS.add(int(port))
            env['TASKUARY_API'] = f'http://127.0.0.1:{int(port)}'
        return env
    return build


@pytest.fixture(scope='session')
def test_safety_events():
    return _SAFETY_EVENTS


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
    import imaplib, requests, smtplib, urllib.request
    from taskuary import browserview, hooks, server, spawn, terminal, waitroom, wabridge

    # Auto-dispatch ships on.  In a suite, both coding and general execution stop at the process
    # boundaries below; switching this off also prevents routine ingest tests from trying at all.
    server.store.set_setting('coder_auto_enabled', '0', 'test')

    real_request = requests.sessions.Session.request
    real_urlopen = urllib.request.urlopen
    real_term_init = terminal.Term.__init__
    real_hook_install = hooks.install
    real_free_port = __import__('taskuary.desktop', fromlist=['free_port']).free_port

    def guarded_request(self, method, url, *args, **kwargs):
        if _local_allowed(url): return real_request(self, method, url, *args, **kwargs)
        return _blocked('HTTP request', url)

    def guarded_urlopen(url, *args, **kwargs):
        if _local_allowed(url): return real_urlopen(url, *args, **kwargs)
        return _blocked('URL open', getattr(url, 'full_url', url))

    def guarded_term_init(self, argv, *args, **kwargs):
        command = str((argv or [''])[0])
        if Path(command).resolve() != Path(sys.executable).resolve():
            return _blocked('PTY worker', command)
        return real_term_init(self, argv, *args, **kwargs)

    def guarded_hooks(cwd, *args, **kwargs):
        path = Path(cwd).resolve()
        temp = Path(tempfile.gettempdir()).resolve()
        try: path.relative_to(temp)
        except ValueError:
            _SAFETY_EVENTS.append(('checkout hook write', str(path)))
            return False
        return real_hook_install(cwd, *args, **kwargs)

    def safe_free_port(*args, **kwargs):
        port = real_free_port(*args, **kwargs)
        _ALLOWED_PORTS.add(port)
        return port

    def stopped(name):
        def no_op(*_args, **_kwargs):
            _SAFETY_EVENTS.append(('lifespan boundary', name))
            return False
        return no_op

    with ExitStack() as patches:
        patches.enter_context(mock.patch.object(requests.sessions.Session, 'request', guarded_request))
        patches.enter_context(mock.patch.object(urllib.request, 'urlopen', guarded_urlopen))
        patches.enter_context(mock.patch.object(imaplib, 'IMAP4_SSL', side_effect=lambda *a, **k: _blocked('IMAP connection', a[0] if a else '')))
        patches.enter_context(mock.patch.object(smtplib, 'SMTP', side_effect=lambda *a, **k: _blocked('SMTP connection', a[0] if a else '')))
        patches.enter_context(mock.patch.object(smtplib, 'SMTP_SSL', side_effect=lambda *a, **k: _blocked('SMTP connection', a[0] if a else '')))
        patches.enter_context(mock.patch.object(spawn, 'popen', side_effect=lambda *a, **k: _blocked('headless worker', a[0] if a else '')))
        patches.enter_context(mock.patch.object(terminal.Term, '__init__', guarded_term_init))
        patches.enter_context(mock.patch.object(hooks, 'install', guarded_hooks))
        patches.enter_context(mock.patch.object(browserview, 'start', stopped('browser launch')))
        patches.enter_context(mock.patch.object(wabridge, 'start_configured', stopped('WhatsApp bridge')))
        patches.enter_context(mock.patch.object(server, 'catch_up_on_startup', stopped('startup catch-up')))
        patches.enter_context(mock.patch.object(server, 'poll_forever', stopped('poll scheduler')))
        patches.enter_context(mock.patch.object(waitroom, 'watch', stopped('waitroom watcher')))
        patches.enter_context(mock.patch('taskuary.desktop.free_port', safe_free_port))
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
