"""Point TASKUARY_HOME at a temp dir BEFORE any taskuary import - server.py loads config
and opens the store at import time, so this must run first (pytest imports conftest first).
"""
import os, tempfile

os.environ.setdefault('TASKUARY_HOME', tempfile.mkdtemp(prefix='taskuary_test_'))
