"""Point TASKUARY_HOME at a temp dir BEFORE any taskuary import - server.py loads config
and opens the store at import time, so this must run first (pytest imports conftest first).
"""
import os, tempfile

os.environ.setdefault('TASKUARY_HOME', tempfile.mkdtemp(prefix='taskuary_test_'))


import pytest

@pytest.fixture(scope='session', autouse=True)
def no_real_agents():
    """Auto-dispatch ships ON, which in a test run means ingest spawning the owner's REAL coding
    CLI under a pty. The shared app store starts with it off; the tests that are about dispatch
    turn it on (or mock start_on_task) themselves."""
    from taskuary import server
    server.store.set_setting('coder_auto_enabled', '0', 'test')
