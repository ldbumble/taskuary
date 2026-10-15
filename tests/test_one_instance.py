"""One live Taskuary per data folder (instance.py), and only the owner's real one writes the hooks every CLI runs (hooks.user_wide)."""
import json, os, tempfile, pytest
from fastapi.testclient import TestClient
from taskuary import config, guard, hooks, instance, origin, server
from taskuary.store import MemoryStore


class Elsewhere:
    "This process's lock on `home`, re-labelled as another process's: still held, but no longer in our own table."
    def __init__(self, home, url='http://127.0.0.1:7999'): self.home, self.url = home, url
    def __enter__(self):
        assert instance.claim(self.url, home=self.home)
        self.f = instance._HELD.pop(instance._key(self.home)); return self
    def __exit__(self, *a): self.f.close()


def test_a_second_claim_on_a_held_folder_is_refused_and_names_the_holder():
    with tempfile.TemporaryDirectory() as d:
        with Elsewhere(d):
            assert not instance.claim('http://127.0.0.1:8001', home=d)
            assert instance.holder(d) == {'pid': os.getpid(), 'url': 'http://127.0.0.1:7999'}
        assert instance.holder(d) == {}                                # the holder gone - however it went - the folder is free
        assert instance.claim('http://127.0.0.1:8001', home=d) and instance.claim(home=d)     # ...and ours, again and again
        assert instance.holder(d) == {}                                # we are not "another" Taskuary
        instance.release(d)

def test_the_server_will_not_start_on_a_folder_another_taskuary_holds():
    with Elsewhere(config.home()):
        with pytest.raises(RuntimeError, match='already running'):
            with TestClient(server.app): pass
    with TestClient(server.app): assert instance._key(config.home()) in instance._HELD
    assert instance._key(config.home()) not in instance._HELD           # let go on shutdown

def test_a_test_or_demo_home_is_not_the_real_instance(monkeypatch):
    assert not hooks.user_wide()
    monkeypatch.setattr(config, 'home', lambda: config.Path.home() / '.taskuary')     # only asked, never opened
    assert hooks.user_wide()
    monkeypatch.setenv('TASKUARY_DEMO', '1'); assert not hooks.user_wide()

def test_a_strangers_session_on_another_instance_reports_its_events_with_its_own_token():
    s, t = MemoryStore(), 7
    d = json.load(open(origin.session_settings(s, t), encoding='utf-8'))['hooks']
    srv = config.load()['server']
    for e in hooks.EVENTS:
        cmd = d[e][-1]['hooks'][0]['command']
        assert hooks.MARK in cmd and hooks.header_file(guard.stranger_token(srv, t)) in cmd and srv['agent_token'] not in cmd
    assert '/api/hooks/claude/floor' in d['PreToolUse'][0]['hooks'][0]['command']           # the floor still first
