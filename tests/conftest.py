"""Point TASKUARY_HOME at a temp dir BEFORE any taskuary import - server.py loads config
and opens the store at import time, so this must run first (pytest imports conftest first).
"""
import os, tempfile

# ALWAYS a fresh temp home - never the user's. This was setdefault(), which respected an already-set
# TASKUARY_HOME, and a session that had one (or a taskuary import that had already happened) put the
# whole suite on the LIVE database: 2026-08-27 it overwrote SOUL.md, an Outlook connector's config and
# left 140 fixture tasks on the owner's board. The one override is explicit and named for tests only.
os.environ['TASKUARY_HOME'] = os.environ.get('TASKUARY_TEST_HOME') or tempfile.mkdtemp(prefix='taskuary_test_')


import pytest

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
