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
    with pytest.raises(clipool.PartWay):
        ask(cli, 'chat:9', 'die')                                   # a first turn that dies is simply an error - said as one that ended part-way
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
    monkeypatch.setattr(clipool, 'MAX_LIVE', 2); monkeypatch.setattr(clipool, 'REST', 0)
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


def test_is_live(cli):
    assert not clipool.is_live('general:5')
    ask(cli, 'general:5', 'hi')
    assert clipool.is_live('general:5') and not clipool.is_live('general:6')
    clipool.close('general:5')
    assert not clipool.is_live('general:5')


def test_touch_keeps_a_process_from_the_reaper(cli):
    ask(cli, 'general:5', 'hi'); ask(cli, 'general:6', 'hi')
    for k in ('general:5', 'general:6'): clipool._POOL[k].used -= 31 * 60
    assert clipool.touch('general:5') == 1
    clipool._sweep()
    assert clipool.is_live('general:5') and not clipool.is_live('general:6'), 'on screen stays; the one nobody looks at is reaped'
    assert clipool.touch('general:9') == 0


def _steer_in(key, *said):
    "Words written into the turn at work on `key` once it is on - as the owner types them while it works (general.GeneralSession.steer)."
    end = time.time() + 20
    while not clipool.steerable(key) and time.time() < end: time.sleep(0.02)
    return [clipool.steer(key, w) for w in said]


def test_words_written_while_a_turn_works_go_into_that_turn(cli):
    """A GENERAL AGENT HEARS WHAT IS TYPED WHILE IT WORKS (2026-11-17): claude's stream-json input takes a further message mid-turn and folds it in.
    The turn's one result answers them - and the next turn reads its own result, not one left behind."""
    got = {}
    t = threading.Thread(target=lambda: got.update(ask(cli, 'chat:1', 'absorb:2 check the totals')), daemon=True); t.start()
    assert _steer_in('chat:1', 'use the March file', 'and skip the refunds') == [True, True]
    t.join(20)
    assert got['said'] == 'heard use the March file | and skip the refunds'
    assert not clipool.steerable('chat:1') and not clipool.steer('chat:1', 'too late'), 'at rest a line is a turn of its own, never steered'
    assert ask(cli, 'chat:1', 'next', resume=got['sid'])['said'] == 'next'


def test_words_the_cli_queued_as_their_own_turn_are_read_to_the_end(cli):
    """...where the CLI kept them for a turn of their own (queued_turn_count > 0), the turn reads on to the last result, with every answer in it:
    returned at the first, the second sat in the pipe and the next turn read it as its own answer."""
    got = {}
    t = threading.Thread(target=lambda: got.update(ask(cli, 'chat:1', 'queue:1 check the totals')), daemon=True); t.start()
    assert _steer_in('chat:1', 'and the refunds') == [True]
    t.join(20)
    assert got['said'].split('\n\n')[0] == 'queued' and got['said'].endswith(':and the refunds')
    assert ask(cli, 'chat:1', 'next', resume=got['sid'])['said'] == 'next'


def test_a_general_agent_over_acp_hears_his_line_at_its_next_step():
    """Design round 3, 2026-11-18 (Codex as the general agent): "sign up yourself" sat unheard 13 minutes behind a 15-minute turn - a kept ACP
    conversation is not a claude process, so nothing could steer it. An ACP agent that steers (`_session/steering`) takes his words into the
    turn at work; one that does not keeps them for the next turn, and its road says so (takes_words)."""
    class Client:
        def __init__(self, steers): self.steers, self.got = steers, []
        def can_steer(self): return self.steers
        def steer(self, text): self.got.append(text); return 'injected'
    class Conv:
        def __init__(self, steers): self.client, self.lock = Client(steers), threading.Lock()
        def alive(self): return True
        def close(self): pass
    for key, steers in (('general:71', True), ('general:72', False)):
        conv = Conv(steers); clipool._POOL[key] = conv
        try:
            assert not clipool.steerable(key), 'at rest a line is a turn of its own'
            with conv.lock:
                assert clipool.steerable(key) is steers and clipool.takes_words(key) is steers
                assert clipool.steer(key, lambda: 'sign up yourself') is steers
            assert conv.client.got == (['sign up yourself'] if steers else [])
        finally: clipool._POOL.pop(key, None)


def test_words_the_agent_did_not_take_stay_his_waiting_lines():
    """The agent audit, 2026-11-22: a line sent in the second the turn ended was taken and heard first, the adapter answered "promptRequired",
    steer said True anyway - and nothing ever answered it. What did not go in is not taken: False, and the next turn takes it."""
    class Client:
        def __init__(self, answer): self.answer = answer
        def can_steer(self): return True
        def steer(self, text): return self.answer
    class Conv:
        def __init__(self, answer): self.client, self.lock = Client(answer), threading.Lock()
        def alive(self): return True
        def close(self): pass
    for answer, went in (('promptRequired', False), ('injected', True)):
        took = []
        def lines(take=True): took.append(take); return 'use the March file'
        clipool._POOL['general:81'] = conv = Conv(answer)
        try:
            with conv.lock: assert clipool.steer('general:81', lines) is went
            assert took == ([False, True] if went else [False]), 'taken only once it went in'
        finally: clipool._POOL.pop('general:81', None)


class _Conv:
    "An ACP conversation as the pool holds one (acp.Conversation's shape)."
    def __init__(self): self.lock, self.used, self.closed, self.sid, self.turns = threading.Lock(), time.time(), False, None, 0
    def alive(self): return not self.closed
    def close(self): self.closed = True


def test_a_full_pool_never_closes_a_conversation_at_work_or_just_opened(monkeypatch):
    """Walk 9, 2026-11-23: three agents "died mid-turn" at once with 13 tasks open - the pool, full at 6, closed the oldest conversation
    with no turn LOCKED on it: one just opened, whose turn had not yet taken its lock. A start past the cap waits for room instead."""
    monkeypatch.setattr(clipool, 'MAX_LIVE', 2)
    try:
        busy, fresh = _Conv(), _Conv()
        busy.lock.acquire()
        clipool._put('general:1', busy); clipool._put('general:2', fresh)
        third = _Conv(); t = threading.Thread(target=clipool._put, args=('general:3', third), daemon=True); t.start()
        t.join(1.5)
        assert not busy.closed and not fresh.closed, 'nothing at work is closed for room'
        assert t.is_alive() and 'general:3' not in clipool._POOL, 'the third waits for room'
        fresh.used -= clipool.REST + 1                   # ...the second one has sat at rest a while now: it makes room
        t.join(3)
        assert fresh.closed and not busy.closed and clipool._POOL.get('general:3') is third
    finally:
        busy.lock.release(); clipool.close('general:')
