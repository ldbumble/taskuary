"""One live CLI process per conversation (clipool): the owner, 2026-09-24 - "of course it should keep open
session ... instead of reopening each time". A fake CLI speaks claude's stream-json protocol: it reads one
JSON message per line, answers with a `result` carrying its session id, and remembers how many turns it saw,
so a test can tell one process from two."""
import os, sys, threading, time

import pytest

from taskuary import clipool




FAKE = os.path.join(os.path.dirname(__file__), 'fake_stream_cli.py')


@pytest.fixture
def cli():
    yield [sys.executable, FAKE, '-p', '--output-format', 'stream-json']
    clipool.close('')


def ask(cli, key, text, resume=None, **kw):
    seen = []
    final, _raw = clipool.run(key, cli, text, seen.append, resume=resume, **kw)
    pid, n, said = final['result'].split(':', 2)
    return {'pid': pid, 'turn': int(n), 'said': said, 'sid': final['session_id'], 'events': seen}


def test_turns_share_one_process_and_one_conversation(cli):
    a = ask(cli, 'chat:1', 'hello')
    b = ask(cli, 'chat:1', 'again', resume=a['sid'])
    assert a['pid'] == b['pid'] and b['turn'] == 2 and b['sid'] == a['sid']
    assert a['events'][0]['type'] == 'assistant'                    # the stream still reaches the caller


def test_a_new_chat_or_another_conversation_is_a_fresh_process(cli):
    a = ask(cli, 'chat:1', 'hello')
    fresh = ask(cli, 'chat:1', 'new chat')                          # no resume id: New chat cleared it
    assert fresh['pid'] != a['pid'] and fresh['turn'] == 1
    other = ask(cli, 'chat:1', 'that one', resume='sid-elsewhere')  # another conversation named
    assert other['pid'] != fresh['pid'] and other['sid'] == 'sid-elsewhere'


def test_other_chats_and_other_launch_settings_do_not_share(cli):
    a = ask(cli, 'chat:1', 'x')
    b = ask(cli, 'chat:2', 'y')
    assert a['pid'] != b['pid']
    c = ask(cli + ['--model', 'other'], 'chat:1', 'z', resume=a['sid'])   # a model changed: a new process
    assert c['pid'] != a['pid']


def test_a_process_that_died_between_turns_is_resumed_by_its_id(cli):
    a = ask(cli, 'chat:1', 'hello')
    [lv] = [v for k, v in clipool._POOL.items() if k == 'chat:1']
    lv.p.kill(); lv.p.wait(5)
    b = ask(cli, 'chat:1', 'still there?', resume=a['sid'])
    assert b['pid'] != a['pid'] and b['sid'] == a['sid']


def test_a_process_that_dies_mid_turn_is_reopened_once_and_answers(cli):
    a = ask(cli, 'chat:1', 'hello')
    with pytest.raises(clipool.Ended):
        ask(cli, 'chat:9', 'die')                                   # a first turn that dies is simply an error
    b = ask(cli, 'chat:1', 'fine', resume=a['sid'])
    assert b['said'] == 'fine'


def test_cancel_and_timeout_kill_the_turn_and_the_next_one_starts_clean(cli):
    stop = threading.Event()
    threading.Timer(0.5, stop.set).start()
    with pytest.raises(RuntimeError, match='cancelled'):
        ask(cli, 'chat:1', 'hang', cancel=stop)
    with pytest.raises(RuntimeError, match='timed out'):
        ask(cli, 'chat:2', 'hang', timeout=1)
    assert ask(cli, 'chat:1', 'after')['said'] == 'after'
    assert not [k for k in clipool._POOL if k == 'chat:2']


def test_close_and_the_pool_limit(cli, monkeypatch):
    ask(cli, 'concierge:1', 'x'); ask(cli, 'general:5', 'y')
    assert clipool.close('concierge:') == 1
    assert [x['key'] for x in clipool.live()] == ['general:5']
    monkeypatch.setattr(clipool, 'MAX_LIVE', 2)
    ask(cli, 'a', '1'); time.sleep(0.05); ask(cli, 'b', '2')
    assert {x['key'] for x in clipool.live()} == {'a', 'b'}         # the oldest (general:5) made room


def test_run_cli_takes_the_live_road_only_when_asked(cli, monkeypatch):
    """agents.run_cli: `keep_alive` on a claude stream-json profile goes through the pool - and nothing else does."""
    from taskuary import agents
    calls = []
    monkeypatch.setattr(clipool, 'run', lambda key, cmd, prompt, on, **kw: (calls.append(key) or
                        ({'type': 'result', 'result': 'hi', 'session_id': 's1'}, [])))
    monkeypatch.setattr(agents, '_resolve_cmd', lambda name: ['claude'])
    prof = {'cmd': 'claude', 'args': ['-p', '--output-format', 'stream-json', '--verbose'], 'keep_alive': 'concierge:7'}
    assert agents.run_cli(prof, 'hello', lambda *a: None, resume='s1') == ('hi', 's1', None)
    assert calls == ['concierge:7']


def _kept_brain(monkeypatch, keep, resume=None):
    """The Assistant's brain as make_cli_llm builds it, on the fake stream CLI: a kept conversation, tools off."""
    import json
    from taskuary import agents, llm
    from taskuary.store import MemoryStore
    s = MemoryStore()
    s.upsert_agent('claude', 'coding', 'cli', json.dumps({'cmd': 'claude', 'args': ['-p', '--output-format', 'stream-json', '--verbose']}))
    monkeypatch.setattr(agents, '_resolve_cmd', lambda name: [sys.executable, FAKE])
    return llm.make_cli_llm(s, 'claude', keep=keep, resume=resume)


def test_a_new_chats_second_round_stays_on_its_live_process(cli, monkeypatch):
    """A look-up's second round of a NEW chat went out with the brain's build-time id - none - which clipool reads as
    New chat: it killed the live CLI and spawned another (15 s against 2.6 s warm), and the round lost its own turn."""
    brain = _kept_brain(monkeypatch, 'concierge:41')
    one, two = (brain('SYS', q).split(':', 2) for q in ('what is waiting', 'you looked it up'))
    assert one[0] == two[0] and two[1] == '2'                  # one process, one conversation
    assert brain.session_id == f'sid-{one[0]}'
    # ...and a chat already under way is unchanged: its rounds resume the session it names
    later = _kept_brain(monkeypatch, 'concierge:41', resume=brain.session_id)
    assert later('SYS', 'and now').split(':', 2)[:2] == [one[0], '3']


def test_a_one_shot_brain_never_carries_its_calls_into_one_conversation(cli, monkeypatch):
    """Triage and the drafter call one brain per message; only a KEPT conversation follows its session."""
    from taskuary import agents
    seen = []
    monkeypatch.setattr(agents, 'run_cli', lambda prof, prompt, trace, resume=None, **kw: (seen.append(resume), ('ok', 'sid-x', None))[1])
    brain = _kept_brain(monkeypatch, None)
    brain('SYS', 'one'); brain('SYS', 'two')
    assert seen == [None, None]


def test_a_swap_after_a_turn_replaces_only_a_live_idle_process_launched_otherwise(cli):
    """After a typed turn the Assistant swaps its CLI when the instructions it was launched with changed (concierge.warm, `changed`):
    the next ask then finds it up instead of starting it under the owner (the speed pass, 2026-10-27). A swap never starts a process
    where none is live - a chat closed meanwhile stays closed - and never cuts a turn under way."""
    assert not clipool.warm('chat:1', cli, swap=True) and 'chat:1' not in clipool._POOL
    a = ask(cli, 'chat:1', 'hello')
    assert not clipool.warm('chat:1', cli, resume=a['sid'], swap=True)                   # the same instructions: kept as it is
    lv = clipool._POOL['chat:1']
    with lv.lock: assert not clipool.warm('chat:1', cli + ['--model', 'other'], resume=a['sid'], swap=True)
    assert clipool._POOL['chat:1'] is lv                                                  # a turn under way is never cut
    assert clipool.warm('chat:1', cli + ['--model', 'other'], resume=a['sid'], swap=True)
    swapped = clipool._POOL['chat:1']
    b = ask(cli + ['--model', 'other'], 'chat:1', 'again', resume=a['sid'])
    assert b['pid'] != a['pid'] and b['sid'] == a['sid'] and clipool._POOL['chat:1'] is swapped is not lv   # the next ask takes the swapped one
