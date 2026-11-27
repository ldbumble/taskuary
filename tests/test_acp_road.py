"""EVERY CLI RUN OF THE GENERAL AGENT OVER ACP, argv as the fallback (the owner, 2026-11-06): claude and codex through their adapters,
Taskuary's own rules answering each permission, the run's model and effort as session options, a kept conversation holding its
connection between turns, and a switch to turn it off. The agent here is tests/fake_acp_server.py; no vendor CLI is installed."""
import json, os, sys, threading
from types import SimpleNamespace
from pathlib import Path
from unittest import mock

import pytest

from taskuary import acp, gate, agents, clipool, clis, shellgate
from taskuary.store import MemoryStore
from taskuary.testing import turn_told

FAKE = [sys.executable, str(Path(__file__).parent / 'fake_acp_server.py')]
HERE = str(Path(__file__).parent)


def profile(**kw): return {'cmd': FAKE[0], 'args': [], 'acp': FAKE[1:], 'acp_ok': True, 'cwd': HERE, **kw}


def run(prof, prompt='go', env=None, store=None, task_id=None):
    ev = []
    trace = lambda kind, name, detail=None: ev.append((kind, name, detail))
    with mock.patch.object(agents, '_resolve_cmd', return_value=[FAKE[0]]), agents.run_context(store, task_id):
        out = agents.run_cli(prof, prompt, trace, extra_env=env)
    return out, ev


# ── the permission answer is Taskuary's ────────────────────────────────────────────────────────────────────────────────────
def test_a_plain_call_is_allowed_once_never_always():
    """allow_always would stop the next such call reaching us at all - Codex's offers 'don't ask again for commands that start with git'."""
    out, ev = run(profile())
    assert out[0].startswith('granted')                    # the answer is what it said after its last call; "Looking." is a step
    assert any(k == 'progress' and d == 'Looking.' for k, _n, d in ev)
    perm = [d for k, _n, d in ev if k == 'permission']
    assert perm and perm[0]['answer'] == gate.ALLOWED


def test_a_push_is_held_for_the_owner_and_the_step_reads_held_not_failed():
    s = MemoryStore()
    tid = s.create_task({'Title': 'Fix the budget total', 'Kind': 'general', 'Status': 'open'}, 'owner')
    with mock.patch.object(shellgate, 'trusted', return_value=''):
        out, ev = run(profile(), env={'FAKE_ACP_ASK': 'git push origin main'}, store=s, task_id=tid)
    assert 'denied' in out[0]
    perm = next(d for k, _n, d in ev if k == 'permission')
    assert perm['answer'] == gate.HELD and 'push' in perm['why']
    res = next(d for k, _n, d in ev if k == 'tool_result')
    assert res['is_error'] and res['result'].startswith(shellgate.HELD)          # agentSteps reads this as "held"
    assert any(json.loads(r.get('DraftText') or '{}').get('command') == 'git push origin main'
               for r in s._rows("SELECT * FROM review WHERE TaskId=? AND Kind='action'", (tid,)))     # the owner's Approve card


def test_a_no_that_ends_the_agents_turn_is_heard_in_the_same_conversation_and_the_work_goes_on():
    """The HIPAA walk, 2026-11-21: codex-acp's only reject is Codex's "cancel", so every hold aborted Codex's turn - "Cancelled" and Try
    again over the live Approve card, the agent never told it was held. The same conversation goes on, told what the step's answer says."""
    s = MemoryStore()
    tid = s.create_task({'Title': 'Fix the budget total', 'Kind': 'general', 'Status': 'open'}, 'owner')
    with mock.patch.object(shellgate, 'trusted', return_value=''):
        out, ev = run(profile(), env={'FAKE_ACP_ASK': 'git push origin main', 'FAKE_ACP_ABORT': '1'}, store=s, task_id=tid)
    said, sid = out[0], out[1]
    assert sid == 'sess_fake_1' and 'turn=2' in said and 'git push origin main' in said      # the same conversation went on, told of the step
    assert any(json.loads(r.get('DraftText') or '{}').get('command') == 'git push origin main'
               for r in s._rows("SELECT * FROM review WHERE TaskId=? AND Kind='action'", (tid,)))     # ...and its Approve card stands


def test_a_general_runs_own_updates_are_its_chat_rows_and_its_trace_draws_none_again():
    """ONE ACP RECORD ON BOTH ROADS (the owner, 2026-11-23: adopt the open-source model): a task chat's run over ACP hands the agent's own
    updates in as they come (a trace that takes them - general's `visible.acp`) and the chat's rows are those: its call by the agent's own id,
    announced with no input and drawn at once, completed in place. The trace's echo of the same call (agents.ACPSteps) writes no second row."""
    from taskuary import chatlog, conversation
    s = MemoryStore()
    tid = s.create_task({'Title': 'Read the ledger for Erin', 'Kind': 'general', 'Status': 'open'}, 'owner')
    conversation.hear(s, tid, turn=True)
    trace = lambda kind, name, detail=None: chatlog.feed(s, tid, 'sid1', 'trace', {'type': kind, 'name': name, 'detail': detail})
    trace.acp = lambda u: chatlog.feed(s, tid, 'sid1', 'acp', u)
    with mock.patch.object(agents, '_resolve_cmd', return_value=[FAKE[0]]), agents.run_context(s, tid):
        out = agents.run_cli(profile(), 'go', trace)
    assert out[0].startswith('granted')
    rows = [(r['Key'], json.loads(r['Body'])) for r in s._rows("SELECT Key, Body FROM chatlog WHERE TaskId=? AND Kind='step' ORDER BY Id", (tid,))]
    tools = [(k, b.get('title'), b.get('status')) for k, b in rows if b.get('k') == 'tool']
    assert tools == [('s:sid1:call_1', 'read the ledger', 'completed')], rows
    assert [b['text'].strip() for _k, b in rows if b.get('k') == 'said'][0] == 'Looking.'


@pytest.mark.parametrize('kind', ['general', 'coding'])
def test_a_held_step_is_the_tasks_one_action_card_at_once_on_every_agent_kind(kind):
    """The owner, 2026-11-27: "ANY approval is ONE ACTION CARD". A coding agent's held push was a second kind of box - Allow once / Allow
    always / Reject, and "No answer by HH:MM refuses it" - while a chat agent's was the action card. With Developer mode on, a coding task's
    held step is the same card at once: it stands until he presses it, and nothing times out into a no he never saw."""
    s = MemoryStore()
    tid = s.create_task({'Title': 'Tidy the exports folder', 'Kind': kind, 'Status': 'open'}, 'owner')
    with mock.patch.object(shellgate, 'trusted', return_value=''), mock.patch.object(agents, 'developer_mode', return_value=True):
        out, ev = run(profile(), env={'FAKE_ACP_ASK': 'git push origin main'}, store=s, task_id=tid)
    assert next(d for k, _n, d in ev if k == 'permission')['answer'] == gate.HELD
    [rv] = s._rows("SELECT * FROM review WHERE TaskId=? AND Kind='action'", (tid,))
    assert rv['Status'] == 'pending' and json.loads(rv['DraftText'])['action'] == 'shell_act' and 'git push origin main' in rv['DraftText']
    assert not hasattr(gate, 'owner_asks') and not hasattr(gate, 'put_to_owner')


def test_the_step_says_whose_no_it_was():
    opts = [{'optionId': 'y', 'kind': 'allow_once'}, {'optionId': 'n', 'kind': 'reject_once'}]
    for said, reads in (('it writes off this machine', 'Taskuary refused it: it writes off this machine'),):
        held = {}
        with mock.patch.object(gate, 'tool_call', return_value=(gate.REFUSED, said)):
            gate.answerer({}, held=held)({'toolCall': {'toolCallId': 'c1', 'kind': 'execute'}, 'options': opts})
        assert held == {'c1': reads}


def test_a_step_taskuary_refuses_is_told_to_the_agent_with_the_way_on():
    """Recorded on the real CLI, 2026-11-15: a push from the task's own checkout was refused with "call propose_land" - in the log and the
    page's trace only. The adapter told the agent "User refused permission to run tool", and it told the owner "Once you approve, I'll
    push" with nothing on screen to approve."""
    from taskuary import browsergate, landing
    s = MemoryStore()
    tid = s.create_task({'Title': 'Fix the budget total', 'Kind': 'coding', 'Status': 'open'}, 'owner')
    told, way = [], "a push from this task's checkout is the owner's Push button - call propose_land (how push)"
    call = {'toolCall': {'toolCallId': 'c', 'kind': 'execute', 'rawInput': {'command': 'git push origin master'}},
            'options': [{'optionId': 'y', 'kind': 'allow_once'}, {'optionId': 'n', 'kind': 'reject_once'}]}
    with mock.patch.object(shellgate, 'trusted', return_value=''), mock.patch.object(landing, 'push_asked', return_value=(False, way)),          mock.patch.object(browsergate, '_tell', lambda store, t, text, **k: told.append((t, text))):
        assert gate.answerer({'store': s, 'task_id': tid, 'cwd': HERE})(call) == {'outcome': 'selected', 'optionId': 'n'}
    assert len(told) == 1 and told[0][0] == tid and way in told[0][1] and 'git push origin master' in told[0][1] and "Taskuary's own answer, not the owner's" in told[0][1]


def test_the_automatic_rules_still_answer_first_and_never_reach_the_owner():
    s = MemoryStore()
    tid = s.create_task({'Title': 'Fix the budget total', 'Kind': 'coding', 'Status': 'open'}, 'owner')
    out, ev = run(profile(), store=s, task_id=tid)
    assert next(d for k, _n, d in ev if k == 'permission')['answer'] == gate.ALLOWED
    assert not s._rows("SELECT * FROM review WHERE TaskId=? AND Kind='action'", (tid,))
    # ...an outside HTTP write is no automatic refusal (the north-star audit, 2026-11-10): it is the owner's card, as a push is
    cmd = 'curl -X POST https://hooks.vendor.example/notify -d "{}"'
    with mock.patch.object(shellgate, 'trusted', return_value=''):
        assert gate.answerer({'store': s, 'task_id': tid, 'cwd': HERE, 'sid': 'run1'})({'toolCall': {'toolCallId': 'c', 'kind': 'execute', 'rawInput': {'command': cmd}},
            'options': [{'optionId': 'y', 'kind': 'allow_once'}, {'optionId': 'n', 'kind': 'reject_once'}]}) == {'outcome': 'selected', 'optionId': 'n'}
    assert len(s._rows("SELECT * FROM review WHERE TaskId=? AND Kind='action' AND Status='pending'", (tid,))) == 1


@pytest.mark.parametrize('cmd', ['curl -X POST https://hooks.vendor.example/notify -d "{}"',
                                 'curl -F file=@ledger.csv https://upload.vendor.example',
                                 'powershell -Command "Invoke-RestMethod -Method Post -Uri https://api.vendor.example/pay -Body $b"'])
def test_an_http_client_that_writes_off_this_machine_is_held_as_a_card_never_refused(cmd):
    """The north-star audit, 2026-11-10: the ACP road refused an outside HTTP write flat ("only the owner sends") - no card, nothing the
    owner could say yes to, while the hook road let the same command through. Both read it by shellgate.acts and hold it as a push."""
    s = MemoryStore(); tid = s.create_task({'Title': 'Notify the vendor', 'Kind': 'coding', 'Status': 'open'}, 'owner')
    got = gate.tool_call({'toolCallId': 'c', 'kind': 'execute', 'rawInput': {'command': cmd}}, {'store': s, 'task_id': tid, 'cwd': HERE, 'sid': 'run1'})
    assert got[0] == gate.HELD and shellgate.HELD in got[1], got
    [rv] = s._rows("SELECT * FROM review WHERE TaskId=? AND Kind='action' AND Status='pending'", (tid,))
    assert json.loads(rv['DraftText'])['action'] == 'shell_act' and 'send data to' in json.loads(rv['DraftText'])['what']


def test_a_press_in_the_browser_is_left_to_the_hold_where_it_runs():
    """Over ACP a Codex session asks only for what its sandbox blocks, so a press judged here was judged on one road and not the next: the
    hold is at the command itself (gate), on every road. ACP's answer lets the line through, and the session's `agent-browser` holds it."""
    s = MemoryStore(); tid = s.create_task({'Title': 'Pay the vendor', 'Kind': 'coding', 'Status': 'open'}, 'owner')
    ctx = {'store': s, 'task_id': tid, 'cwd': HERE, 'sid': 'run1', 'cli': 'codex'}
    call = lambda c: gate.tool_call({'toolCallId': 'c', 'kind': 'execute', 'rawInput': {'command': c}}, ctx)
    for cmd in ('agent-browser click @e3', 'agent-desktop click @s1:e2', 'agent-browser snapshot -i'):
        assert call(cmd) == (gate.ALLOWED, ''), cmd


@pytest.mark.parametrize('cmd', ['curl -s https://docs.northwind.example/budget', 'curl -f -s https://docs.northwind.example/a.pdf -o a.pdf',
                                 'curl -s -X POST -H "X-Taskuary-Token: $T" http://127.0.0.1:7787/api/agent/tick -d "{}"',
                                 'git status', 'rg -n approvedTotal src'])
def test_a_read_a_fetch_and_taskuary_s_own_api_are_allowed(cmd):
    assert gate.tool_call({'toolCallId': 'c', 'kind': 'execute', 'rawInput': {'command': cmd}}, {'cwd': HERE})[0] == gate.ALLOWED


def test_taskuary_s_own_tools_are_allowed_and_an_outside_send_tool_is_not():
    s = MemoryStore()
    own = {'toolCallId': 'c', '_meta': {'claudeCode': {'toolName': 'mcp__taskuary__propose_reply'}}, 'rawInput': {'text': 'hi'}}
    assert gate.tool_call(own, {'store': s, 'cli': 'claude'})[0] == gate.ALLOWED
    verdicts = [{'server': 'mail', 'blocked': False, 'error': '', 'tools': [{'name': 'send_email', 'blocked': True}, {'name': 'search', 'blocked': False}]}]
    with mock.patch('taskuary.sendfilter.verdicts', return_value=verdicts):
        send = {'toolCallId': 'c', '_meta': {'claudeCode': {'toolName': 'mcp__mail__send_email'}}}
        look = {'toolCallId': 'c', 'title': 'mcp.mail.search', 'rawInput': {'server': 'mail', 'tool': 'search', 'arguments': {}}}   # codex's spelling
        unknown = {'toolCallId': 'c', '_meta': {'claudeCode': {'toolName': 'mcp__chat__post_message'}}}
        assert gate.tool_call(send, {'store': s, 'cli': 'claude'})[0] == gate.REFUSED
        assert gate.tool_call(look, {'store': s, 'cli': 'codex'})[0] == gate.ALLOWED
        assert gate.tool_call(unknown, {'store': s, 'cli': 'claude'})[0] == gate.REFUSED          # fail closed, as the send filter is


def test_a_rule_that_raises_refuses():
    c = acp.ACPClient(FAKE[0], FAKE[1:], timeout=30, permit=lambda p: 1 / 0)
    try:
        c.connect(); c.new_session(HERE)
        _stop, said = c.prompt('go')
    finally: c.close()
    assert 'denied' in said


# ── it falls back, and there is no switch ─────────────────────────────────────────────────────────────────────────────────
def test_an_agent_that_dies_at_initialize_runs_on_the_command_line_and_says_so_once():
    agents._FELL_BACK.discard(FAKE[0])
    seen, real_popen = [], agents.spawn.popen
    def popen(cmd, **kw):
        if '-p' in cmd: raise RuntimeError('the argv road')                     # the argv road reached: the fallback happened
        return real_popen(cmd, **kw)
    for _ in range(2):
        with mock.patch.object(agents.spawn, 'popen', side_effect=popen), mock.patch.object(agents.logger, 'warning') as warn:
            with pytest.raises(RuntimeError, match='the argv road'):
                run(profile(args=['-p']), env={'FAKE_ACP_FAIL': 'init'})
            seen.append(warn.call_count)
    assert seen == [1, 0]                                                       # said once in the log, not on every run


def test_claude_with_no_way_to_launch_its_adapter_answers_on_the_command_line_kept_and_resumed(tmp_path):
    """No npx on PATH (a machine without Node; the browser harness's bare PATH) and no adapter installed: the ACP road cannot start,
    and that is a start failure, not a missing CLI. The general agent's kept conversation is warmed on the argv road and every turn -
    the first, and a resumed one after it - is answered by the owner's own claude. It used to answer "'npx' not found on PATH"."""
    script = tmp_path / 'script.json'
    script.write_text(json.dumps([{'when': 'price', 'first': 'Payworth is cheapest at 4 a head.'}, {'when': 'south', 'first': 'The south office is on Payworth.'}]))
    fake = [sys.executable, str(Path(__file__).parent / 'fake_claude.py')]
    def resolve(c):
        if c == 'npx': raise FileNotFoundError("'npx' not found on PATH - is the CLI installed?")
        return list(fake)
    key, env = 'general:test-acp-no-npx', {'FAKE_CLAUDE_SCRIPT': str(script), 'FAKE_CLAUDE_SPAWN': '0', 'FAKE_CLAUDE_THINK': '0'}
    prof = {'cmd': 'claude', 'args': clis.preset_args('claude'), 'acp_ok': True, 'keep_alive': key, 'cwd': str(tmp_path)}
    s, ev = MemoryStore(), []
    trace = lambda kind, name, detail=None: ev.append((kind, name, detail))
    try:
        with mock.patch.object(agents, '_resolve_cmd', side_effect=resolve), mock.patch.object(agents.pathcache, 'which', return_value=None), \
             agents.run_context(s, None):
            assert agents._acp_road(prof)                                       # claude has an adapter: it tries
            assert agents.warm_cli(prof, extra_env=env, store=s) and clipool.is_live(key)      # warmed: the argv process, since ACP cannot start
            out1 = agents.run_cli(prof, 'The owner says: compare them on price.', trace, extra_env=env, store=s)
            out2 = agents.run_cli(prof, 'The owner says: look at the south office first', trace, resume=out1[1], extra_env=env, store=s)
        assert 'Payworth is cheapest' in out1[0] and 'south office is on Payworth' in out2[0]
        assert out1[1] and out2[1] == out1[1]                                    # one conversation, resumed
        assert any(n == 'acp' and 'did not start' in str(d) for _k, n, d in ev)  # said on the run's launch line, quietly
    finally: clipool.close(key)


def test_there_is_no_switch_and_an_old_homes_saved_off_is_not_read():
    "An agent's steps are asked for before they run, always: a home that saved the old switch off still takes the ACP road."
    from taskuary import settings_schema
    from taskuary.store import DEFAULT_SETTINGS
    assert 'acp_cli' not in DEFAULT_SETTINGS and 'acp_cli' not in settings_schema.knobs()
    s = MemoryStore(); s.set_setting('acp_cli', '0', 'owner')
    with mock.patch.object(agents, 'run_acp', return_value=('ok', 'sid', None)) as acp, \
         mock.patch.object(agents.spawn, 'popen', side_effect=AssertionError('the command line must never be reached')):
        run(profile(args=['-p'], held_only=True), store=s)
    assert acp.called


# ── gears, resume, a kept connection ──────────────────────────────────────────────────────────────────────────────────────
def test_the_run_s_model_and_effort_are_set_as_session_options_and_a_missing_one_is_said():
    """The adapters list their models and efforts as config options (claude: opus, sonnet...; codex: gpt-6.1-sol...) - set there, not
    as a --model flag the adapter has no use for. One the agent has nothing near is said in plain words, never sent to fail the session."""
    for pick, said, note in (('sonnet@low', 'model=sonnet effort=low', None),
                             ('gpt-9@low', 'model=opus effort=low', 'gpt-9 is not available on this claude sign-in, so this ran on opus')):
        ev, c = [], acp.ACPClient(FAKE[0], FAKE[1:], timeout=30)
        try:
            c.connect(); c.new_session(HERE)
            agents._acp_gears(c, {'model': pick}, 'claude', lambda k, n, d=None: ev.append((k, n, d)))
            _stop, out = c.prompt('go')
        finally: c.close()
        assert said in out
        assert any(note in str(d) for _k, _n, d in ev) if note else not ev


def test_resume_takes_session_resume_where_offered_and_a_replay_is_never_traced_as_this_turn():
    for env in ({'FAKE_ACP_RESUME': '1'}, {}):
        ev = []
        with mock.patch.object(agents, '_resolve_cmd', return_value=[FAKE[0]]):
            out = agents.run_cli(profile(), 'carry on', lambda k, n, d=None: ev.append((k, n, d)), resume='sess_fake_1', extra_env=env)
        assert out[1] == 'sess_fake_1'
        assert not any('old.txt' in json.dumps(d, default=str) or 'replayed' in str(d) for _k, _n, d in ev), env


def test_a_kept_conversation_holds_its_connection_between_turns():
    key = 'general:test-acp-keep'
    try:
        out1, _ = run(profile(keep_alive=key))
        with mock.patch.object(agents, '_resolve_cmd', return_value=[FAKE[0]]):
            out2 = agents.run_cli(profile(keep_alive=key), 'and again', lambda *a: None, resume=out1[1])
        assert 'turn=1' in out1[0] and 'turn=2' in out2[0]                     # the same process answered both
        assert clipool.is_live(key)
        assert clipool.close(key) == 1 and not clipool.is_live(key)            # New chat closes it like a claude process
    finally: clipool.close(key)


def test_a_stop_ends_its_own_turn_and_never_the_one_that_begins_after_it(monkeypatch):
    """The recorded stop, 2026-11-11: he stopped a turn with two lines waiting. Their turn began at once on the same kept conversation, and the
    stop's backstop closed it two seconds after the press - "died mid-turn", nothing drawn, his lines unanswered. Read by states, never the
    clock: the backstop's grace is long enough for the slowest runner, and the backstop itself is seen to have let go."""
    import threading
    monkeypatch.setattr(agents, 'STOP_GRACE', 60)
    key, said, heard, real = 'general:test-acp-stop', {}, threading.Event(), agents.ACPSteps.__call__
    def steps(self, u): real(self, u); heard.set()                             # the turn's first update: its prompt is at the agent
    monkeypatch.setattr(agents.ACPSteps, '__call__', steps)
    trace = lambda *a: None
    def turn(n, stop, resume=None):
        with mock.patch.object(agents, '_resolve_cmd', return_value=[FAKE[0]]):
            try: said[n] = agents.run_cli(profile(keep_alive=key), f'turn {n}', trace, extra_env={'FAKE_ACP_HANG': '1'}, cancel=stop, resume=resume)
            except Exception as e: said[n] = e
    others = {t for t in threading.enumerate() if t.name == 'acp-stop-backstop'}       # ...an earlier test's, still waiting on a stop never pressed
    backstops = lambda: [t for t in threading.enumerate() if t.name == 'acp-stop-backstop' and t not in others]
    try:
        s1, s2 = threading.Event(), threading.Event()
        a = threading.Thread(target=turn, args=(1, s1)); a.start()
        assert heard.wait(60), 'the first turn began'
        s1.set(); a.join(60)                                                   # his stop: the turn honours it and ends
        assert isinstance(said[1], clipool.Cancelled) and said[1].session_id, said     # ...as every road says a stop, its conversation named
        for t in backstops(): t.join(10)
        assert not backstops(), 'the stopped turn is over: its backstop let go at once'
        b = threading.Thread(target=turn, args=(2, s2, said[1].session_id), daemon=True); b.start(); b.join(60)
        c = threading.Thread(target=turn, args=(3, s2, said[1].session_id), daemon=True); c.start(); c.join(60)
        assert 'turn=2' in str(said[2]) and 'turn=3' in str(said[3]), (said.get(2), said.get(3))    # ...both on that one conversation
        assert clipool.is_live(key)
    finally: s1.set(); s2.set(); clipool.close(key)


# ── how claude and codex launch ───────────────────────────────────────────────────────────────────────────────────────────
def test_claude_and_codex_launch_through_their_pinned_adapter_driving_the_owner_s_own_binary():
    for name, pkg in (('claude', 'claude-agent-acp@'), ('codex', 'codex-acp@')):
        with mock.patch.object(agents, '_resolve_cmd', side_effect=lambda c: ['npx'] if c == 'npx' else [f'/opt/bin/{c}']), \
             mock.patch.object(agents.pathcache, 'which', return_value=None):
            l = agents.acp_launch({'cmd': name, 'args': clis.preset_args(name)})
        assert l['cmd'][:2] == ['npx', '-y'] and pkg in l['cmd'][2] and l['cmd'][2].split('@')[-1][0].isdigit()   # pinned
        assert f'/opt/bin/{name}' in l['env'].values() and l['mode'] == clis.ADAPTERS[name]['mode']
    with mock.patch.object(agents.pathcache, 'which', return_value='/usr/local/bin/claude-agent-acp'), \
         mock.patch.object(agents, '_resolve_cmd', return_value=['/opt/bin/claude']), \
         mock.patch.object(agents.acpadapter, 'runs_pinned', return_value=True):
        assert agents.acp_launch({'cmd': 'claude', 'args': []})['cmd'] == ['/usr/local/bin/claude-agent-acp']          # installed: no npx


def test_claude_s_argv_reaches_the_adapter_as_sdk_options(tmp_path):
    sysp = tmp_path / 'system.md'; sysp.write_text('You are Alex Doyle\'s agent.', encoding='utf-8')
    args = clis.preset_args('claude') + ['--mcp-config', '/h/agent-tools/TQ-7.mcp.json', '--disallowedTools', 'mcp__mail__send_email,mcp__chat',
                                         '--append-system-prompt-file', str(sysp), '--settings', '/h/hold.json', '--add-dir', '/h/out']
    o = agents.claude_acp_options(args)
    assert o['disallowedTools'] == ['mcp__mail__send_email', 'mcp__chat']
    assert o['systemPrompt'] == {'type': 'preset', 'preset': 'claude_code', 'append': "You are Alex Doyle's agent."}
    assert o['extraArgs'] == {'mcp-config': '/h/agent-tools/TQ-7.mcp.json'} and o['settings'] == '/h/hold.json'
    assert o['additionalDirectories'] == ['/h/out']
    assert not any(k in json.dumps(o) for k in ('dangerously', 'stream-json', '"-p"'))      # the protocol's own, never passed on
    # ...and WHAT STANDS AFTER A FLAG WITH NO VALUE STILL REACHES IT (found on the real CLI, 2026-11-12): a chat agent's argv ends
    # `--setting-sources project,local --strict-mcp-config --settings <its file>` (llm.make_cli_llm), and everything after the bare flag was
    # dropped - its session ran with no hook of Taskuary's (a held step reached the model only as "User refused permission") and read the
    # owner's own CLAUDE.md, which that file excludes
    o = agents.claude_acp_options(['-p', '--setting-sources', 'project,local', '--strict-mcp-config', '--settings', '/h/general-7.json', '--add-dir', '/h/out'])
    assert o == {'settingSources': ['project', 'local'], 'extraArgs': {'strict-mcp-config': None}, 'settings': '/h/general-7.json', 'additionalDirectories': ['/h/out'],
                 'promptSuggestions': False}
    # ...and NO PREDICTED NEXT PROMPT: the adapter's default is one more model call after every turn, for gray text nothing here draws
    assert agents.claude_acp_options([])['promptSuggestions'] is False


def test_codex_s_config_flags_become_its_session_config():
    args = clis.preset_args('codex') + ['-c', 'mcp_servers.taskuary.url="http://127.0.0.1:7787/api/mcp?task=7"',
                                        '-c', 'mcp_servers.taskuary.env_http_headers={"X-Taskuary-Token"="TASKUARY_TOKEN"}',
                                        '-c', 'mcp_servers.mail.disabled_tools=["send_email"]', '--sandbox', 'read-only']
    cfg = agents.codex_acp_config(args)
    assert cfg == {'mcp_servers.taskuary.url': 'http://127.0.0.1:7787/api/mcp?task=7',
                   'mcp_servers.taskuary.env_http_headers': {'X-Taskuary-Token': 'TASKUARY_TOKEN'},
                   'mcp_servers.mail.disabled_tools': ['send_email']}


# ── a CLI whose reads no command line can keep works only on the held road (the owner, 2026-11-16) ────────────────────────────
# Codex quick work - a look with no hands, on `codex exec` - listed the owner's Documents folder and nobody was asked: even its read-only
# sandbox reads the whole disk, and its only way to act alone was --dangerously-bypass-approvals-and-sandbox
@pytest.mark.parametrize('how', [dict(research=True), dict(cli_tools=True)])
def test_codex_quick_and_full_work_on_a_task_go_held_and_claude_s_look_keeps_its_confined_road(how):
    from taskuary import llm
    s = MemoryStore()
    tid = s.create_task({'Title': 'List my Documents folder', 'Kind': 'general', 'Source': 'manual', 'OriginBase': 'owner'}, 'owner')
    seen = {}
    for name in ('codex', 'claude'):
        s.upsert_agent(name, 'general', 'cli', json.dumps({'cmd': name}))
        brain = llm.make_cli_llm(s, name, task_id=tid, keep=f'general:{tid}', **how)
        with mock.patch.object(agents, 'run_cli', side_effect=lambda prof, *a, **k: (seen.update({prof['cmd']: prof}), ('ok', 'sid', None))[1]):
            brain('sys', 'list my Documents folder')
    assert seen['codex'].get('held_only') and agents._acp_road(seen['codex'])
    assert '--dangerously-bypass-approvals-and-sandbox' not in clis.preset_args('codex')
    assert not seen['claude'].get('held_only')                                   # its reads are kept by its own permission rules


def test_a_held_only_run_that_cannot_start_over_acp_runs_nothing_and_says_so():
    s = MemoryStore()
    real_popen = agents.spawn.popen
    def popen(cmd, **kw):
        if '-p' in cmd: raise AssertionError('the command line must never be reached')
        return real_popen(cmd, **kw)
    with mock.patch.object(agents.spawn, 'popen', side_effect=popen):
        with pytest.raises(RuntimeError, match='nothing ran'): run(profile(args=['-p'], held_only=True), env={'FAKE_ACP_FAIL': 'init'}, store=s)


# ── a conversation the CLI no longer has (agents.Gone): the turn is said again to a fresh one, never the CLI's error ─────────────────────────
GONE_ENV = {'FAKE_ACP_RESUME': '1', 'FAKE_ACP_GONE': '1'}

def test_a_resume_the_agent_refuses_is_gone_and_the_fresh_conversation_it_opened_takes_the_whole_turn():
    """The owner's chat after a restart, 2026-11-16: its saved conversation was gone from the CLI. The resume used to fail over to the command
    line, which resumed the same dead id and printed "No conversation found with session ID" into the steps. Now the ACP road says Gone, and
    the turn said again (with no id) runs on the fresh conversation that was opened for it - one start, no fallback, no CLI error anywhere."""
    key, ev = 'general:test-acp-gone', []
    trace = lambda k, n, d=None: ev.append((k, n, d))
    try:
        with mock.patch.object(agents, '_resolve_cmd', return_value=[FAKE[0]]):
            with pytest.raises(agents.Gone): agents.run_cli(profile(keep_alive=key), 'and the totals?', trace, resume='sess_gone_1', extra_env=GONE_ENV)
            conv = clipool._POOL[key]
            said, sid, _ = agents.run_cli(profile(keep_alive=key), 'the whole conversation, then: and the totals?', trace, extra_env=GONE_ENV)
        assert clipool._POOL[key] is conv and sid == conv.sid                 # the conversation opened for it, not a second start
        assert 'heard: the whole conversation' in said and 'turn=1' in said and 'resumed=' not in said
        assert not any(agents.gone(str(d)) or 'did not start' in str(d) for _k, _n, d in ev), ev
    finally: clipool.close(key)


def test_a_gone_resume_on_a_one_shot_acp_run_is_gone_too_never_the_command_line():
    ev = []
    with mock.patch.object(agents, '_resolve_cmd', return_value=[FAKE[0]]), pytest.raises(agents.Gone):
        agents.run_cli(profile(), 'carry on', lambda k, n, d=None: ev.append((k, n, d)), resume='sess_gone_2', extra_env=GONE_ENV)
    assert not any('did not start' in str(d) for _k, _n, d in ev)


@pytest.mark.parametrize('keep', ['', 'general:test-argv-gone'])
def test_the_command_line_says_gone_for_claude_s_own_no_conversation_found(monkeypatch, keep):
    """The same refusal on the argv road, as claude 2.1.326 gives it - with -p on its own (a one-shot) and on a kept stream-json process: the
    line on stderr, a result of error_during_execution with the line in `errors`. Gone, never "claude exit 1: ..." or "error_during_execution"."""
    monkeypatch.setattr(clis, 'ADAPTERS', {}); monkeypatch.setenv('FAKE_CLAUDE_GONE', '1'); monkeypatch.setenv('FAKE_CLAUDE_SPAWN', '0')
    fake = [sys.executable, str(Path(HERE) / 'fake_claude.py')]
    args = ['-p', '--output-format', 'stream-json', '--verbose'] + (['--input-format', 'stream-json'] if keep else [])
    try:
        with mock.patch.object(agents, '_resolve_cmd', return_value=fake), pytest.raises(agents.Gone):
            agents.run_cli({'cmd': 'claude', 'args': args, 'cwd': HERE, **({'keep_alive': keep} if keep else {})}, 'carry on', lambda *a: None,
                           resume='3f1c2b9a-0000-4000-8000-00000000000a')
    finally: clipool.close(keep) if keep else None


def test_a_stop_pressed_before_the_turn_took_its_conversation_still_stops_it(monkeypatch):
    """The stop's backstop looked for the turn's lock, and a stop that landed before the turn took it found none and let go: the turn was
    prompted anyway and ran on, unstopped, until its time ran out. And a stop already pressed when the turn takes its conversation never sends
    the prompt at all: sent, then cancelled, a quick agent did the work he had stopped."""
    stop, got, asked, real = threading.Event(), {}, [], acp.ACPClient.prompt
    monkeypatch.setattr(acp.ACPClient, 'prompt', lambda self, text, sent=None: (asked.append(text), real(self, text, sent=sent))[1])
    stop.set()                                                                   # pressed while the turn was still being started
    def turn():
        try: got['out'] = agents.run_cli(profile(), 'go', lambda *a: None, extra_env={'FAKE_ACP_HANG': '1'}, cancel=stop)
        except Exception as e: got['out'] = e
    with mock.patch.object(agents, '_resolve_cmd', return_value=[FAKE[0]]):
        t = threading.Thread(target=turn, daemon=True); t.start(); t.join(30)
    assert isinstance(got.get('out'), clipool.Cancelled) and got['out'].session_id, got or 'the turn ran on, unstopped'
    assert asked == [], 'the stopped turn was never sent to the agent'


# ── ONE CONTRACT ACROSS ROADS: a stopped turn, an early end, a death (the parity matrix, workstream 6) ─────────────────────────────
@pytest.mark.parametrize('stop', ['refusal', 'max_tokens', 'max_turn_requests', 'other'])
def test_a_turn_that_ends_early_with_nothing_said_fails_as_the_kept_road_reads_its_error_result(stop, tmp_path):
    """An adapter that stopped for a refusal or a limit before saying a word came back as a finished turn with an empty reply. The kept claude
    road raises its CLI's error result; ACP goes the same way (agents.raise_failure)."""
    rules = tmp_path / 'r.json'; rules.write_text(json.dumps([{'when': '.', 'silent': True}]))
    with pytest.raises(clipool.PartWay) as e:
        run(profile(), 'go', env={'FAKE_ACP_SCRIPT': str(rules), 'FAKE_ACP_STOP': stop})
    # ...said once, plainly, with the way on: no agent's name, no stop code (those are the log's) - and an unknown reason claims no limit
    kind = {'refusal': 'refusal', 'max_tokens': 'limit', 'max_turn_requests': 'limit'}.get(stop, 'other')
    assert str(e.value) == clipool.ENDED_EARLY[kind] and stop not in str(e.value) and 'claude' not in str(e.value).lower()
    assert e.value.session_id, 'its conversation goes with it'


@pytest.mark.parametrize('stop', ['max_tokens', 'refusal'])
def test_a_turn_that_says_words_then_hits_a_limit_or_a_refusal_ended_part_way_its_words_kept(stop, tmp_path):
    """An adapter that said half an answer and then stopped at max_tokens came back as the turn's answer, filed done ("agent done"), where the
    kept claude road files the same shape - words, then its error_max_turns - as a turn that ended part-way, its words kept. One way on both."""
    rules = tmp_path / 'r.json'; rules.write_text(json.dumps([{'when': '.', 'first': 'Half of it.'}]))
    ev = []
    with pytest.raises(clipool.PartWay) as e, mock.patch.object(agents, '_resolve_cmd', return_value=[FAKE[0]]):
        agents.run_cli(profile(), 'go', lambda k, n, d=None: ev.append((k, n, d)), extra_env={'FAKE_ACP_SCRIPT': str(rules), 'FAKE_ACP_STOP': stop})
    assert str(e.value) == clipool.ended_early(stop) and e.value.session_id
    assert any(k == 'progress' and 'Half of it.' in str(d) for k, n, d in ev), 'its words stay in its steps'

    # ...and a turn that ended for any other reason after words is still its answer
    out, ev = run(profile(), 'go', env={'FAKE_ACP_SCRIPT': str(rules), 'FAKE_ACP_STOP': 'budget_gone'})
    assert out[0] == 'Half of it.'


def test_an_adapter_that_answers_its_turn_with_its_servers_death_died_mid_turn(tmp_path):
    """Walk 16: a Codex adapter outlived its app-server and answered the prompt with an error carrying that server's stderr; the rail said its
    first line - a deprecation warning - as the cause. The same death as the adapter's own: MID_TURN, its conversation kept for the try."""
    msg = ('The Codex app-server exited with code 4294967295. The agent starts it again on the next request. 2026-11-24T10:37:48Z ERROR '
           'codex_app_server: `[features].multi_agent` is deprecated.')
    rules = tmp_path / 'r.json'; rules.write_text(json.dumps([{'when': '.', 'error': msg}]))
    with pytest.raises(clipool.PartWay) as e:
        run(profile(), 'go', env={'FAKE_ACP_SCRIPT': str(rules)})
    assert str(e.value) == clipool.MID_TURN and e.value.session_id


# ── ONE FAILURE ROAD: a usage limit reads the same whatever the AI and the road (the design round, 2026-11-18) ──────────────────────
def test_a_usage_limit_over_acp_is_the_limit_every_road_raises():
    """Over ACP the adapter says its limit in words, and the chat's road raised them raw - never RateLimited, so the router went on handing
    the spent AI the next call. Read by agents.failure_of, as the one-shot and kept roads read theirs."""
    with pytest.raises(agents.RateLimited) as e:
        run(profile(), 'go', env={'FAKE_ACP_FAIL': 'quota'})
    assert str(e.value) == "You've hit your 5-hour limit · resets 12:10pm (America/New_York)"
    # ...and it keeps the conversation it was on (the HIPAA walk, 2026-11-21): a 429's try again opened a fresh Codex thread and did the work twice
    from taskuary import general
    assert general._unfinished(e.value).session_id == 'sess_fake_1'


@pytest.mark.parametrize('said', ["You've hit your usage limit. Upgrade to Pro or try again at 3:05 PM.", 'Not logged in · Please run /login'])
def test_every_road_reads_a_failure_by_one_function(said):
    "A limit and a sign-out, said in words by any CLI, are the same exception on the one-shot road, the kept road and ACP."
    f = agents.failure_of('codex', said, 'codex')
    assert isinstance(f, agents.RateLimited) if 'limit' in said else 'sign' in str(f).lower() or 'log' in str(f).lower()
    with pytest.raises(type(f)): agents.raise_failure('codex', said, 'codex')


# ── A CONNECTOR STARTED AHEAD (the speed round, 2026-11-20: every new task's agent waited ~1 s for claude's adapter to start) ──────────────
def test_claude_s_adapter_runs_on_no_task_s_environment_and_the_next_task_opens_on_one_started_ahead(tmp_path, monkeypatch):
    import time
    log = tmp_path / 'acp.jsonl'
    monkeypatch.setenv('FAKE_ACP_LOG', str(log))
    launch = {'cmd': FAKE, 'env': {}, 'mode': '', 'meta': {'claudeCode': {'options': {'promptSuggestions': False}}}, 'adapter': 'claude-agent-acp@0'}
    base = {**os.environ}
    open_for = lambda tid: agents._acp_open('claude', launch, str(tmp_path), {**base, 'TQ_TASK': str(tid)}, None, 60, lambda *a: None, base=base)
    try:
        t = time.time(); a = open_for(1)
        for _ in range(100):                                                   # ...the next one starting behind it
            if agents._ACP_SPARE: break
            time.sleep(0.05)
        ahead = next(iter(agents._ACP_SPARE.values())).p.pid
        b = open_for(2)
        rows = [json.loads(l) for l in log.read_text().splitlines()]
        assert [r['env'] for r in rows] == [{'TQ_TASK': '1'}, {'TQ_TASK': '2'}]      # ...each task's own part rides with its session
        assert all(r['proc'] == {} for r in rows)                                       # ...never in the adapter's own process
        assert b.p.pid == ahead != a.p.pid and rows[1]['pid'] == ahead                   # ...task 2 on the one started ahead
        for _ in range(100):
            if agents._ACP_SPARE: break
            time.sleep(0.05)
        assert agents._ACP_SPARE                                                         # ...and a third already up for the next
    finally:
        for c in (locals().get('a'), locals().get('b')):
            if c: c.close()
        agents._close_spares()


def test_the_owner_s_own_codex_starts_with_openai_s_apps_and_plugins_off_as_an_ai_card_s_does():
    """The owner, 2026-11-22: a Codex CLI agent, run on his own ~/.codex, called ChatGPT's Wallet app - "yes turn off". One table closes them
    for every Codex Taskuary starts; his own -c keys still ride after it."""
    import json
    from taskuary import harness
    with mock.patch.object(agents, '_resolve_cmd', side_effect=lambda c: ['npx'] if c == 'npx' else [f'/opt/bin/{c}']), \
         mock.patch.object(agents.pathcache, 'which', return_value=None):
        l = agents.acp_launch({'cmd': 'codex', 'args': ['exec', '-c', 'model_reasoning_effort="high"']})
    cfg = json.loads(l['env']['CODEX_CONFIG'])
    assert cfg['features.apps'] is False and cfg['features.plugins'] is False and cfg['model_reasoning_effort'] == 'high'
    # ...only those: his plan's picture tool and fast tier stay his (the owner, 2026-11-22 - an AI card's harness closes them, his CLI does not)
    assert {k.split('.', 1)[1] for k in cfg if k.startswith('features.')} == set(harness.OWNER_CLI_OFF)
    assert 'features.image_generation' not in cfg and 'features.fast_mode' not in cfg
    assert cfg['skills.bundled.enabled'] is False               # ...and Codex's bundled skills index rides no task of his (the review, 2026-11-23)


def test_a_start_that_fails_once_is_tried_again_before_he_hears_of_it():
    """The owner's live app, 2026-11-22: "Codex did not start ... (session/new: Internal error)" after 40 s, at a busy minute; both his cards
    started in 0.9 s a moment later. Nothing ran on a failed start, so it is tried once more; only a second failure is his to see."""
    from taskuary import acp as acp_mod
    calls = []
    def flaky(*a, **k):
        calls.append(1)
        if len(calls) == 1: raise acp_mod.ACPStartError('session/new: Internal error')
        return ('done', 'sid1', '')
    prof = {'cmd': 'codex', 'held_only': True}
    with mock.patch.object(agents, '_acp_road', return_value=True), mock.patch.object(agents, 'run_acp', side_effect=flaky):
        assert agents.run_cli(prof, 'draw it', lambda *a, **k: None) == ('done', 'sid1', '') and len(calls) == 2
    with mock.patch.object(agents, '_acp_road', return_value=True), \
         mock.patch.object(agents, 'run_acp', side_effect=acp_mod.ACPStartError('session/new: Internal error')):
        with pytest.raises(RuntimeError, match="couldn't start just now"): agents.run_cli(prof, 'draw it', lambda *a, **k: None)


def test_each_installed_adapter_is_primed_once_and_let_go():
    """The owner, 2026-11-22: "still takes 40 seconds" - the first start after launch spent 9.4 s loading the adapter cold; later ones under 4 s.
    Each adapter this computer has is started once in the background and closed; none it lacks."""
    from taskuary import acp as acp_mod
    made = []
    class Fake:
        def __init__(self, *a, **k): made.append(a[0]); self.closed = False
        def connect(self): return {}
        def close(self): self.closed = True
    have = lambda c: [f'/opt/bin/{c}'] if c == 'codex' else []
    with mock.patch.object(agents, '_resolve_cmd', side_effect=have), mock.patch.object(acp_mod, 'ACPClient', Fake), \
         mock.patch.object(agents.pathcache, 'which', return_value=None), mock.patch.object(agents.acpadapter, 'kept', return_value='/opt/kept/codex-acp'):
        assert agents._prime_adapters(0) == ['codex'] and len(made) == 1
