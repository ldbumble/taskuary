"""What makes the Assistant on a CLI brain answer quickly (the owner, 2026-10-20) - its process started before it is asked, its words
drawn as they are written - and what must not change for it: the answer, the action, one process per chat."""
import json, os, sys, threading
from unittest import mock

import pytest
from fastapi.testclient import TestClient

from taskuary import agents, clipool, concierge, general
from taskuary.store import MemoryStore

FAKE = os.path.join(os.path.dirname(__file__), 'fake_claude.py')


@pytest.fixture
def fast_fake(monkeypatch, tmp_path):
    """tests/fake_claude.py with no start-up and a quick model, saying `first` to anything."""
    script = tmp_path / 'script.json'
    script.write_text(json.dumps([{'when': '.', 'first': 'It is on the table now.\nCALL: {"kind": "pipe.list", "params": {}}', 'then': 'Ten things.'}]))
    log = tmp_path / 'fake.log'
    monkeypatch.setenv('FAKE_CLAUDE_SCRIPT', str(script)); monkeypatch.setenv('FAKE_CLAUDE_LOG', str(log))
    for k, v in (('FAKE_CLAUDE_SPAWN', '0'), ('FAKE_CLAUDE_THINK', '0'), ('FAKE_CLAUDE_TPS', '2000')): monkeypatch.setenv(k, v)
    monkeypatch.setattr(agents, '_resolve_cmd', lambda name: [sys.executable, FAKE])
    yield log
    clipool.close('')


def _store():
    s = MemoryStore()
    s.upsert_agent('claude', 'general', 'cli', json.dumps({'cmd': 'claude', 'args': ['-p', '--dangerously-skip-permissions', '--output-format', 'stream-json', '--verbose']}))
    s.set_setting(concierge.AI_KEY, 'cli:claude', 't')
    return s


def _pids(log):
    return [json.loads(l)['pid'] for l in log.read_text().splitlines() if '"ev": "ready"' in l] if log.exists() else []


def test_the_chat_is_warmed_with_the_process_its_first_ask_takes(fast_fake):
    s = _store()
    assert concierge.warm(s, wait=True) is True
    tid = general.dock_task(s, 'owner')[0]['TaskId']
    assert [x['key'] for x in clipool.live()] == [f'{concierge.LIVE_KEY}:{tid}']
    assert concierge.warm(s, wait=True) is False                    # one already live: nothing more is started
    concierge.say(s, "what's waiting on me")
    assert len(set(_pids(fast_fake))) == 1                          # the ask - both its rounds - ran on the warmed process
    turns = [json.loads(l) for l in fast_fake.read_text().splitlines() if '"ev": "turn"' in l]
    assert [t['n'] for t in turns] == [1, 2]


def test_warm_does_nothing_for_an_api_brain_or_a_cli_that_keeps_no_conversation(fast_fake):
    s = _store(); s.set_setting(concierge.AI_KEY, 'connector:1', 't')
    assert concierge.warm(s, wait=True) is False
    s = _store(); s.upsert_agent('claude', 'general', 'cli', json.dumps({'cmd': 'claude', 'args': ['-p']}))   # no stream-json: one shot per call
    assert concierge.warm(s, wait=True) is False
    assert clipool.live() == [] and _pids(fast_fake) == []


def test_every_round_of_a_turn_runs_on_one_set_of_instructions(fast_fake):
    """The CLI is launched with the turn's instructions (--system-prompt-file, by content): a round on other ones restarted it."""
    s = _store()
    files = set()
    real_run = clipool.run
    def run(key, cmd, *a, **k):
        files.add(cmd[cmd.index('--system-prompt-file') + 1]); return real_run(key, cmd, *a, **k)
    with mock.patch.object(clipool, 'run', run):
        concierge.say(s, "what's waiting on me")
        concierge.say(s, 'and the next one?')
    assert len(files) == 1


def test_the_assistants_words_stream_and_its_call_line_never_does(fast_fake):
    s = _store()
    words = []
    concierge.say(s, 'bring up the first one', trace=lambda kind, name, detail: kind == 'words' and words.append(detail))
    assert 'It is on the table now.' in words and words[-1] == 'Ten things.'      # each round's words, the look-up's answer last
    assert not any('CALL' in w or '{' in w for w in words)


@pytest.mark.parametrize('half, shown', [
    ('Here it is', 'Here it is'),
    ('Here it is.\nCAL', 'Here it is.'),                             # might yet be a CALL line: held back
    ('Here it is.\nCALL: {"kind": "pipe', 'Here it is.'),
    ('Pick one.\nOPTIONS: a | b', 'Pick one.'),
    ('{"kind": "next"}', ''),
    ('Done.\n```json\n{}', 'Done.'),
    ('Calling Marcus now', 'Calling Marcus now'),                    # a word that starts like the marker is still a word
])
def test_spoken_is_only_what_the_owner_reads(half, shown):
    assert agents.spoken(half) == shown


def test_a_brain_with_no_partial_flag_streams_no_words(fast_fake):
    """Only the Assistant asks for its words (--include-partial-messages); a general agent's kept conversation draws none."""
    s = MemoryStore()
    s.upsert_agent('claude', 'general', 'cli', json.dumps({'cmd': 'claude', 'args': ['-p', '--output-format', 'stream-json', '--verbose']}))
    from taskuary import llm
    seen = []
    b = llm.make_cli_llm(s, 'claude', keep='general:9', trace=lambda kind, *a: seen.append(kind))
    assert b('SYS', 'hello')
    assert 'words' not in seen


def test_continue_lit_with_notes_carries_them_and_says_so():
    """"Rerun the agent with these notes: use the new template" lit Continue and dropped the notes (the real-CLI walk, 2026-10-20):
    the light carries them - Continue's box opens holding them - and the line says they go with it. Without notes, as before."""
    from tests import assistant_walk as W
    s = W.world()
    with mock.patch('taskuary.ingest._spawn'):
        said = lambda call: concierge.say(s, 'rerun the agent', key='msg:17', llm=lambda *a, **k: 'Sending it back.\nCALL: ' + json.dumps(call))
        out = said({'kind': 'agent.continue', 'params': {'ref': 'TQ-0012', 'note': 'use the new template'}})
        assert out['light']['verb'] == 'continue' and out['light']['note'] == 'use the new template'
        assert out['say'] == 'Lit Continue on TQ-0012 with your notes: use the new template'
        assert 'your notes are in its box' in out['light']['line']
        bare = said({'kind': 'agent.continue', 'params': {'ref': 'TQ-0012'}})
        assert bare['say'] == 'Lit Continue on TQ-0012.' and 'note' not in bare['light']


def test_the_tool_text_tells_marking_read_from_putting_down():
    """"mark the FYI read" over one FYI chose Next on the real CLI: the decision and the tool now say which is which."""
    from taskuary import toolcatalog
    assert 'mark the FYI read' in toolcatalog.PURPOSE['pipe.clear'] and 'never next' in toolcatalog.PURPOSE['pipe.clear']
    assert 'marked nothing' in toolcatalog.DECISIONS['next'] and 'pipe.clear' in toolcatalog.DECISIONS['next']


def test_the_page_opening_new_chat_and_a_new_brain_each_warm_it(monkeypatch):
    from taskuary import server
    s = _store()
    calls = []
    monkeypatch.setattr(server, 'store', s)
    monkeypatch.setattr(server, '_warm_assistant', lambda: calls.append('warm'))
    c = TestClient(server.app)
    assert c.get('/api/concierge').status_code == 200
    assert c.post('/api/concierge/ai', json={'pick': ''}).status_code == 200
    assert c.post('/api/assistant/dock/new').status_code == 200
    assert calls == ['warm'] * 3
