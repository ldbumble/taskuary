"""Point TASKUARY_HOME at a temp dir BEFORE any taskuary import - server.py loads config
and opens the store at import time, so this must run first (pytest imports conftest first).
"""
import os, tempfile
from pathlib import Path

# ALWAYS a fresh temp home - never the user's. This was setdefault(), which respected an already-set
# TASKUARY_HOME, and a session that had one (or a taskuary import that had already happened) put the
# whole suite on the LIVE database: 2026-08-27 it overwrote SOUL.md, an Outlook connector's config and
# left 140 fixture tasks on the owner's board. The one override is explicit and named for tests only.
os.environ['TASKUARY_HOME'] = os.environ.get('TASKUARY_TEST_HOME') or tempfile.mkdtemp(prefix='taskuary_test_')

# ...and this server answers to the name the test client calls it by. starlette's TestClient sends
# `Host: testserver` (hardcoded for websockets), and token_gate now refuses a Host it does not
# recognise - that is the DNS-rebinding rule, and declaring the name is exactly how a self-hoster
# satisfies it too. Written into the test home's own config, so nothing in taskuary/ knows pytest exists.
_cfg = Path(os.environ['TASKUARY_HOME']) / 'config.toml'
if not _cfg.exists():
    _cfg.parent.mkdir(parents=True, exist_ok=True)
    _cfg.write_text('[server]\nallowed_hosts = "testserver"\n', encoding='utf-8')


import pytest


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
def no_real_agents():
    """Auto-dispatch ships ON, which in a test run means ingest spawning the owner's REAL coding
    CLI under a pty. The shared app store starts with it off; the tests that are about dispatch
    turn it on (or mock start_on_task) themselves."""
    from taskuary import server
    server.store.set_setting('coder_auto_enabled', '0', 'test')


@pytest.fixture
def fx():
    """A MemoryStore wrapped in the picture factory. Named pictures (pending_draft,
    running, filed_fyi, ...) are the regression fixtures for Timeline/Board chips."""
    from taskuary.testing import Factory
    return Factory()
