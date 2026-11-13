"""EVERY CLI RUN OF THE GENERAL AGENT OVER ACP, argv as the fallback (the owner, 2026-11-06): claude and codex through their adapters,
Taskuary's own rules answering each permission, the run's model and effort as session options, a kept conversation holding its
connection between turns, and a switch to turn it off. The agent here is tests/fake_acp_server.py; no vendor CLI is installed."""
import json, sys, threading
from types import SimpleNamespace
from pathlib import Path
from unittest import mock

import pytest

from taskuary import acp, acpgate, agents, clipool, clis, permissions, shellgate
from taskuary.store import MemoryStore

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
    assert perm and perm[0]['answer'] == acpgate.ALLOWED


def test_a_push_is_held_for_the_owner_and_the_step_reads_held_not_failed():
    s = MemoryStore()
    tid = s.create_task({'Title': 'Fix the budget total', 'Kind': 'general', 'Status': 'open'}, 'owner')
    # nobody answers the owner's buttons (permissions.ask) in time: the Approve card is filed and the call refused, as before
    with mock.patch.object(shellgate, 'trusted', return_value=''), mock.patch('taskuary.permissions.TIMEOUT', 0.3):
        out, ev = run(profile(), env={'FAKE_ACP_ASK': 'git push origin main'}, store=s, task_id=tid)
    assert 'denied' in out[0]
    perm = next(d for k, _n, d in ev if k == 'permission')
    assert perm['answer'] == acpgate.HELD and 'push' in perm['why']
    res = next(d for k, _n, d in ev if k == 'tool_result')
    assert res['is_error'] and res['result'].startswith(shellgate.HELD)          # agentSteps reads this as "held"
    assert any(json.loads(r.get('DraftText') or '{}').get('command') == 'git push origin main'
               for r in s._rows("SELECT * FROM review WHERE TaskId=? AND Kind='action'", (tid,)))     # the owner's Approve card


def _answering(option):
    "The owner pressing a button on the held call as soon as it is up (the task chat's card, permissions.answer)."
    def go():
        for _ in range(200):
            p = permissions.pending(store=STORE[0])
            if p: return permissions.answer(STORE[0], p[0]['tid'], p[0]['id'], option)
            threading.Event().wait(0.05)
    t = threading.Thread(target=go, daemon=True); t.start(); return t
STORE = [None]


def test_a_chat_agents_held_step_is_its_approve_card_at_once_never_buttons_no_page_draws():
    """Recorded on the real CLI, 2026-11-12: with Developer mode on, a chat agent's delete was put to the owner as Allow once / Reject -
    buttons only a coding task's chat draws. Its turn read "working" for ten minutes with nothing to press; only then the Approve card
    came. A chat agent's held step is that card from the start, whatever Developer mode says."""
    s = MemoryStore()
    tid = s.create_task({'Title': 'Tidy the exports folder', 'Kind': 'general', 'Status': 'open'}, 'owner')
    with mock.patch.object(shellgate, 'trusted', return_value=''), mock.patch.object(permissions, 'ask', side_effect=AssertionError('buttons were asked')):
        out, ev = run(profile(), env={'FAKE_ACP_ASK': 'git push origin main'}, store=s, task_id=tid)
    assert next(d for k, _n, d in ev if k == 'permission')['answer'] == acpgate.HELD and not permissions.pending(tid, s)
    [rv] = s._rows("SELECT * FROM review WHERE TaskId=? AND Kind='action'", (tid,))
    assert rv['Status'] == 'pending' and 'git push origin main' in rv['DraftText']


@pytest.mark.parametrize('option,granted', [('allow_once', True), ('reject_once', False)])
def test_a_held_push_is_the_owners_buttons_and_their_answer_is_the_answer(option, granted):
    s = STORE[0] = MemoryStore()
    tid = s.create_task({'Title': 'Fix the budget total', 'Kind': 'coding', 'Status': 'open'}, 'owner')
    with mock.patch.object(shellgate, 'trusted', return_value=''):
        t = _answering(option)
        out, ev = run(profile(), env={'FAKE_ACP_ASK': 'git push origin main'}, store=s, task_id=tid)
        t.join(5)
    perm = next(d for k, _n, d in ev if k == 'permission')
    assert perm['answer'] == (acpgate.ALLOWED if granted else acpgate.REFUSED)
    assert out[0].startswith('granted') == granted
    # ...and their no is theirs on the step, never "Taskuary refused it: the owner said no" (the owner, 2026-11-10)
    if not granted: assert perm['why'] == acpgate.YOU_REJECTED == 'You rejected this'
    # answered on the spot: no Approve card waits as well
    assert not s._rows("SELECT * FROM review WHERE TaskId=? AND Kind='action'", (tid,))
    assert not permissions.pending(tid, s)


def test_the_step_says_whose_no_it_was():
    opts = [{'optionId': 'y', 'kind': 'allow_once'}, {'optionId': 'n', 'kind': 'reject_once'}]
    for said, reads in ((acpgate.YOU_REJECTED, 'You rejected this'), ('it writes off this machine', 'Taskuary refused it: it writes off this machine')):
        held = {}
        with mock.patch.object(acpgate, 'decide', return_value=(acpgate.REFUSED, said)):
            acpgate.answerer({}, held=held)({'toolCall': {'toolCallId': 'c1', 'kind': 'execute'}, 'options': opts})
        assert held == {'c1': reads}


def test_the_owners_reject_reaches_the_agent_as_the_owners_no_and_their_allow_says_nothing():
    """Agent walk 2, 2026-11-10: Reject reached the agent as the adapter's "User refused permission to run tool" - the same sentence it
    gets when Taskuary blocks a step by itself - and it ended its turn asking for the same push again."""
    from taskuary import browsergate
    for option, heard in (('reject_once', True), ('allow_once', False)):
        s = STORE[0] = MemoryStore()
        tid = s.create_task({'Title': 'Fix the budget total', 'Kind': 'coding', 'Status': 'open'}, 'owner')
        told = []
        sess = SimpleNamespace(sid='run1', send_prompt=lambda text, as_owner=True: told.append((text, as_owner)))
        with mock.patch.object(shellgate, 'trusted', return_value=''), mock.patch('taskuary.workerstate._live', return_value=sess), \
             mock.patch('taskuary.terminal.stranger_now', return_value=False):
            t = _answering(option)
            run(profile(), env={'FAKE_ACP_ASK': 'git push origin main'}, store=s, task_id=tid)
            t.join(5)
            for _ in range(100):
                if told or not heard: break
                threading.Event().wait(0.05)
        if not heard: assert told == []; continue
        [(text, as_owner)] = told
        assert not as_owner and browsergate.OWNER_NO in text and 'git push origin main' in text and "not a block of Taskuary's" in text
        assert 'do not ask for the same step again' in text


def test_the_automatic_rules_still_answer_first_and_never_reach_the_owner():
    s = MemoryStore()
    tid = s.create_task({'Title': 'Fix the budget total', 'Kind': 'coding', 'Status': 'open'}, 'owner')
    with mock.patch.object(permissions, 'ask', side_effect=AssertionError('the owner was asked')):
        out, ev = run(profile(), store=s, task_id=tid)
    assert next(d for k, _n, d in ev if k == 'permission')['answer'] == acpgate.ALLOWED
    # ...an outside HTTP write is no automatic refusal (the north-star audit, 2026-11-10): it is the owner's to answer, as a push is
    cmd = 'curl -X POST https://hooks.vendor.example/notify -d "{}"'
    with mock.patch.object(permissions, 'ask', return_value='reject_once') as asked:
        assert acpgate.answerer({'store': s, 'task_id': tid, 'cwd': HERE})({'toolCall': {'toolCallId': 'c', 'kind': 'execute', 'rawInput': {'command': cmd}},
            'options': [{'optionId': 'y', 'kind': 'allow_once'}, {'optionId': 'n', 'kind': 'reject_once'}]}) == {'outcome': 'selected', 'optionId': 'n'}
    asked.assert_called_once()


@pytest.mark.parametrize('cmd', ['curl -X POST https://hooks.vendor.example/notify -d "{}"',
                                 'curl -F file=@ledger.csv https://upload.vendor.example',
                                 'powershell -Command "Invoke-RestMethod -Method Post -Uri https://api.vendor.example/pay -Body $b"'])
def test_an_http_client_that_writes_off_this_machine_is_held_as_a_card_never_refused(cmd):
    """The north-star audit, 2026-11-10: the ACP road refused an outside HTTP write flat ("only the owner sends") - no card, nothing the
    owner could say yes to, while the hook road let the same command through. Both read it by shellgate.acts and hold it as a push."""
    s = MemoryStore(); tid = s.create_task({'Title': 'Notify the vendor', 'Kind': 'coding', 'Status': 'open'}, 'owner')
    got = acpgate.decide({'toolCallId': 'c', 'kind': 'execute', 'rawInput': {'command': cmd}}, {'store': s, 'task_id': tid, 'cwd': HERE, 'sid': 'run1'})
    assert got[0] == acpgate.HELD and shellgate.HELD in got[1], got
    [rv] = s._rows("SELECT * FROM review WHERE TaskId=? AND Kind='action' AND Status='pending'", (tid,))
    assert json.loads(rv['DraftText'])['action'] == 'shell_act' and 'send data to' in json.loads(rv['DraftText'])['what']


@pytest.mark.parametrize('cmd', ['curl -s https://docs.northwind.example/budget', 'curl -f -s https://docs.northwind.example/a.pdf -o a.pdf',
                                 'curl -s -X POST -H "X-Taskuary-Token: $T" http://127.0.0.1:7787/api/agent/tick -d "{}"',
                                 'git status', 'rg -n approvedTotal src'])
def test_a_read_a_fetch_and_taskuary_s_own_api_are_allowed(cmd):
    assert acpgate.decide({'toolCallId': 'c', 'kind': 'execute', 'rawInput': {'command': cmd}}, {'cwd': HERE})[0] == acpgate.ALLOWED


def test_taskuary_s_own_tools_are_allowed_and_an_outside_send_tool_is_not():
    s = MemoryStore()
    own = {'toolCallId': 'c', '_meta': {'claudeCode': {'toolName': 'mcp__taskuary__propose_reply'}}, 'rawInput': {'text': 'hi'}}
    assert acpgate.decide(own, {'store': s, 'cli': 'claude'})[0] == acpgate.ALLOWED
    verdicts = [{'server': 'mail', 'blocked': False, 'error': '', 'tools': [{'name': 'send_email', 'blocked': True}, {'name': 'search', 'blocked': False}]}]
    with mock.patch('taskuary.sendfilter.verdicts', return_value=verdicts):
        send = {'toolCallId': 'c', '_meta': {'claudeCode': {'toolName': 'mcp__mail__send_email'}}}
        look = {'toolCallId': 'c', 'title': 'mcp.mail.search', 'rawInput': {'server': 'mail', 'tool': 'search', 'arguments': {}}}   # codex's spelling
        unknown = {'toolCallId': 'c', '_meta': {'claudeCode': {'toolName': 'mcp__chat__post_message'}}}
        assert acpgate.decide(send, {'store': s, 'cli': 'claude'})[0] == acpgate.REFUSED
        assert acpgate.decide(look, {'store': s, 'cli': 'codex'})[0] == acpgate.ALLOWED
        assert acpgate.decide(unknown, {'store': s, 'cli': 'claude'})[0] == acpgate.REFUSED          # fail closed, as the send filter is


def test_a_rule_that_raises_refuses():
    c = acp.ACPClient(FAKE[0], FAKE[1:], timeout=30, permit=lambda p: 1 / 0)
    try:
        c.connect(); c.new_session(HERE)
        _stop, said = c.prompt('go')
    finally: c.close()
    assert 'denied' in said


# ── it falls back, and the switch turns it off ─────────────────────────────────────────────────────────────────────────────
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
            assert agents._acp_road(prof, s)                                    # the switch is on and claude has an adapter: it tries
            assert agents.warm_cli(prof, extra_env=env, store=s) and clipool.is_live(key)      # warmed: the argv process, since ACP cannot start
            out1 = agents.run_cli(prof, 'The owner says: compare them on price.', trace, extra_env=env, store=s)
            out2 = agents.run_cli(prof, 'The owner says: look at the south office first', trace, resume=out1[1], extra_env=env, store=s)
        assert 'Payworth is cheapest' in out1[0] and 'south office is on Payworth' in out2[0]
        assert out1[1] and out2[1] == out1[1]                                    # one conversation, resumed
        assert any(n == 'acp' and 'did not start' in str(d) for _k, n, d in ev)  # said on the run's launch line, quietly
    finally: clipool.close(key)


def test_the_switch_off_keeps_every_run_on_the_command_line():
    s = MemoryStore(); s.set_setting(agents.ACP_SETTING, '0', 'owner')
    with mock.patch.object(agents, 'run_acp', side_effect=AssertionError('must not take the ACP road')), \
         mock.patch.object(agents.spawn, 'popen', side_effect=RuntimeError('argv')):
        with pytest.raises(RuntimeError, match='argv'): run(profile(args=['-p']), store=s)
    assert agents.acp_on(MemoryStore()) and not agents.acp_on(s)


def test_the_switch_is_a_setting_on_the_page_and_on_by_default():
    from taskuary import settings_schema
    from taskuary.store import DEFAULT_SETTINGS
    assert DEFAULT_SETTINGS[agents.ACP_SETTING] == '1'
    assert settings_schema.knobs()[agents.ACP_SETTING]['type'] == 'switch'


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


def test_a_stop_ends_its_own_turn_and_never_the_one_that_begins_after_it():
    """The recorded stop, 2026-11-11: he stopped a turn with two lines waiting. Their turn began at once on the same kept conversation, and the
    stop's backstop closed it two seconds after the press - "died mid-turn", nothing drawn, his lines unanswered."""
    import threading, time
    key, said = 'general:test-acp-stop', {}
    def turn(n, stop, resume=None):
        with mock.patch.object(agents, '_resolve_cmd', return_value=[FAKE[0]]):
            try: said[n] = agents.run_cli(profile(keep_alive=key), f'turn {n}', lambda *a: None, extra_env={'FAKE_ACP_HANG': '1'}, cancel=stop, resume=resume)
            except Exception as e: said[n] = e
    try:
        s1, s2 = threading.Event(), threading.Event()
        a = threading.Thread(target=turn, args=(1, s1)); a.start(); time.sleep(1.5)
        t0 = time.time(); s1.set(); a.join(10)                                 # his stop: the turn honours it and ends
        # ...within the backstop's two seconds, or the backstop closed it as designed - a slow runner, where nothing after it means anything
        if time.time() - t0 >= 1.8: pytest.skip('the stopped turn outlived the stop backstop on this machine')
        assert isinstance(said[1], tuple), said                                # ...as an answer, its conversation kept
        # ...and the lines that waited have theirs, on that conversation - bounded: on a slow runner this hung the whole part for 35 minutes
        b = threading.Thread(target=turn, args=(2, s2, said[1][1]), daemon=True); b.start(); b.join(15)
        assert not b.is_alive(), 'the turn after the stop never answered'
        time.sleep(2.5)                                                        # past the backstop's two seconds: it was not closed under them
        c = threading.Thread(target=turn, args=(3, s2, said[1][1]), daemon=True); c.start(); c.join(8)
        assert not c.is_alive(), 'the conversation was closed and a fresh process began its first turn'
        assert 'turn=2' in str(said[2]) and 'turn=3' in str(said[3]), (said[2][0], said[3][0] if isinstance(said[3], tuple) else said[3])
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
    assert o == {'settingSources': ['project', 'local'], 'extraArgs': {'strict-mcp-config': None}, 'settings': '/h/general-7.json', 'additionalDirectories': ['/h/out']}


def test_codex_s_config_flags_become_its_session_config():
    args = clis.preset_args('codex') + ['-c', 'mcp_servers.taskuary.url="http://127.0.0.1:7787/api/mcp?task=7"',
                                        '-c', 'mcp_servers.taskuary.env_http_headers={"X-Taskuary-Token"="TASKUARY_TOKEN"}',
                                        '-c', 'mcp_servers.mail.disabled_tools=["send_email"]', '--sandbox', 'read-only']
    cfg = agents.codex_acp_config(args)
    assert cfg == {'mcp_servers.taskuary.url': 'http://127.0.0.1:7787/api/mcp?task=7',
                   'mcp_servers.taskuary.env_http_headers': {'X-Taskuary-Token': 'TASKUARY_TOKEN'},
                   'mcp_servers.mail.disabled_tools': ['send_email']}


def test_a_closed_connection_takes_its_whole_process_tree_on_windows():
    c = acp.ACPClient(FAKE[0], FAKE[1:], timeout=30)
    with mock.patch.object(acp.os, 'name', 'nt'), mock.patch.object(acp.spawn, 'run') as r:
        c.close()
    assert r.call_args[0][0][:2] == ['taskkill', '/PID'] and '/T' in r.call_args[0][0]
    c.p.kill()
