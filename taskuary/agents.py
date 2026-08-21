"""Agent execution: any CLI is an agent. A profile ({cmd, args, resume_args, timeout, cwd,
cwd_map}) turns Claude Code, Codex, or your own wrapper into a Taskuary teammate: prompt
over STDIN (argv length limits are real on Windows), JSON output parsed when available
(Claude-style {result, session_id} -> resumable sessions), git diff captured around the
run so code changes are first-class, every run traced + audited.
"""
import json, os, re, subprocess, threading, time
from datetime import datetime
from loguru import logger

from .store import task_ref


def _git(cwd, *args):
    try:
        p = subprocess.run(['git', '-C', cwd or os.getcwd(), *args], capture_output=True, text=True,
                           encoding='utf-8', errors='replace', timeout=30)
        return p.stdout.strip() if p.returncode == 0 else ''
    except Exception:
        return ''


def parse_cli_json(stdout: str):
    """Claude-style single JSON object -> (result, session_id); plain text falls through."""
    try:
        j = json.loads((stdout or '').strip())
        return (j.get('result') or '').strip(), j.get('session_id')
    except (ValueError, AttributeError):
        return (stdout or '').strip(), None


def _fresh_path() -> str:
    """PATH as it is NOW, not as it was when Taskuary started. A process keeps the environment
    it was born with, so a CLI installed while the app was running said "command not found"
    until a restart - the one thing the error told you to do that you should not have to.
    Windows keeps the live value in the registry; elsewhere the inherited PATH is all there is."""
    if os.name != 'nt': return os.environ.get('PATH', '')
    import winreg
    parts = [os.environ.get('PATH', '')]
    for hive, key in ((winreg.HKEY_CURRENT_USER, 'Environment'),
                      (winreg.HKEY_LOCAL_MACHINE, r'SYSTEM\CurrentControlSet\Control\Session Manager\Environment')):
        try:
            with winreg.OpenKey(hive, key) as k:
                parts.append(os.path.expandvars(winreg.QueryValueEx(k, 'Path')[0]))
        except OSError:
            pass
    return os.pathsep.join(p for p in parts if p)


def _resolve_cmd(name: str) -> list:
    """Windows can't CreateProcess a bare 'claude': npm installs it as claude.cmd, which
    only PATH-resolves via which() and only executes through cmd /c."""
    import shutil
    path = shutil.which(name) or shutil.which(name, path=_fresh_path())
    if not path:
        raise FileNotFoundError(f"'{name}' not found on PATH - is the CLI installed?")
    if os.name == 'nt' and path.lower().endswith(('.cmd', '.bat')):
        return ['cmd', '/c', path]
    return [path]


def _fmt_input(inp) -> str:
    """The one field a human wants to see per tool call - command, path, pattern…"""
    if not isinstance(inp, dict): return str(inp)[:140]
    for k in ('command', 'file_path', 'path', 'pattern', 'url', 'query', 'description', 'prompt'):
        if inp.get(k): return str(inp[k])[:140]
    return json.dumps(inp)[:140]


def _result_text(c) -> str:
    """A tool_result's content is a string or a list of {type: text} blocks."""
    v = c.get('content')
    if isinstance(v, list): v = ' '.join(str(b.get('text') or '') for b in v if isinstance(b, dict))
    return re.sub(r'\s*\n\s*', ' ⏎ ', str(v or '').strip())


def _live_line(j):
    """One readable console line per claude stream-json event; None = not worth showing.
    Tool RESULTS stream too (trimmed), so the console reads like the terminal you'd see
    if you ran the CLI yourself - not just the commands it fired."""
    t = j.get('type')
    if t == 'system':
        # only the real session init is news; the other system events (hooks, compaction,
        # subagent starts) repeated 'session started' forever and said nothing
        if j.get('subtype') not in (None, 'init'): return None
        m = j.get('model') or (j.get('modelInfo') or {}).get('name') or ''
        return 'session started' + (f' · model {m}' if m else '')
    if t == 'assistant':
        out = []
        for c in (j.get('message') or {}).get('content') or []:
            if c.get('type') == 'tool_use': out.append(f"→ {c.get('name')}: {_fmt_input(c.get('input'))}")
            elif c.get('type') == 'text' and (c.get('text') or '').strip(): out.append(c['text'].strip()[:300])
        return '\n'.join(out) or None
    if t == 'user':
        res = [c for c in (j.get('message') or {}).get('content') or []
               if isinstance(c, dict) and c.get('type') == 'tool_result']
        if not res: return None
        if any(c.get('is_error') for c in res): return f"✗ {_result_text(next(c for c in res if c.get('is_error')))[:300]}"
        txt = _result_text(res[0])
        return f'· {txt[:240]}' if txt else None
    return None


def run_cli(profile: dict, prompt: str, trace, resume: str = None):
    """One headless invocation of the configured CLI, output STREAMED line by line into
    the run trace so the Board shows the agent working live. claude's stream-json events
    render as readable tool/text lines; any other CLI's plain stdout streams as-is.
    Returns (result, session_id, diff)."""
    name = profile.get('cmd', 'claude')
    cmd = _resolve_cmd(name) + list(profile.get('args') or ['-p'])
    # which model works it: profile default, or a per-run override from the UI. The flag
    # name is configurable because every CLI spells it differently (claude/codex: --model).
    if profile.get('model'): cmd += [profile.get('model_arg') or '--model', str(profile['model'])]
    if resume and profile.get('resume_args'): cmd += list(profile['resume_args']) + [resume]
    cwd = profile.get('cwd')
    head0 = _git(cwd, 'rev-parse', 'HEAD')
    trace('prompt', 'prompt_sent_to_agent', prompt)
    trace('tool', 'cli', f'{name} cwd={cwd or os.getcwd()}' + (f' resume={resume}' if resume else ''))
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         text=True, encoding='utf-8', errors='replace', cwd=cwd, shell=False)
    timed = threading.Event()
    killer = threading.Timer(profile.get('timeout', 1200), lambda: (timed.set(), p.kill()))
    killer.start()
    err_buf = []
    threading.Thread(target=lambda: err_buf.append(p.stderr.read()), daemon=True).start()
    # stdin feed on its own thread: writing a big prompt while the child is already
    # emitting output can deadlock both pipes otherwise
    def _feed():
        try: p.stdin.write(prompt); p.stdin.close()
        except Exception: pass
    threading.Thread(target=_feed, daemon=True).start()
    raw, final = [], None
    try:
        for line in p.stdout:
            line = line.rstrip('\n')
            if not line.strip(): continue
            raw.append(line)
            try: j = json.loads(line)
            except ValueError: trace('live', name, line[:400]); continue
            if isinstance(j, dict) and (j.get('type') == 'result' or ('result' in j and 'type' not in j)):
                final = j; continue
            shown = _live_line(j) if isinstance(j, dict) else None
            if shown: trace('live', name, shown)
        p.wait()
    finally:
        killer.cancel()
    if p.returncode != 0:
        why = f'timed out after {profile.get("timeout", 1200)}s' if timed.is_set() else \
            ((err_buf[0] if err_buf else '') or '\n'.join(raw[-5:]) or 'no output')[:500]
        raise RuntimeError(f'{name} exit {p.returncode}: {why}')
    if final is not None: out, sid = str(final.get('result') or '').strip(), final.get('session_id')
    else: out, sid = parse_cli_json('\n'.join(raw))
    trace('output', name, out[-1000:])
    diff = ''
    if head0:
        head1 = _git(cwd, 'rev-parse', 'HEAD')
        if head1 and head1 != head0: diff = _git(cwd, 'diff', f'{head0}..{head1}')
        unc = _git(cwd, 'diff', 'HEAD')
        if unc: diff = f'{diff}\n{unc}'.strip()
        if diff: trace('tool', 'code_changes', f'{len(diff.splitlines())} diff lines captured')
    return out, sid, (diff[:150000] or None)


def task_context(store, task_id: int) -> str:
    d = store.task_detail(task_id)
    t = d['task']
    lines = [f"Task {d['ref']}: {t.get('Title')}", f"Kind: {t.get('Kind')}  Status: {t.get('Status')}",
             f"Summary: {t.get('Summary') or ''}", '', 'Messages:']
    for m in d['messages']:
        lines += [f"- [{m.get('SentAt')}] {m.get('FromName') or m.get('FromEmail')}: {m.get('Subject') or ''}",
                  f"  {str(m.get('BodyText') or '')[:1500]}"]
    lines += ['', 'Thread:'] + [f"- {c.get('Actor')}: {str(c.get('Body'))[:300]}" for c in d['comments']]
    return '\n'.join(lines)


def memory_block(store, messages: list) -> str:
    senders = {(m.get('FromEmail') or '').lower() for m in messages if m.get('FromEmail')}
    domains = {s.rsplit('@', 1)[-1] for s in senders if '@' in s}
    hits = [f"- {n['Note']}" for n in store.list_memories()
            if n['Scope'] == 'global' or (n['Scope'] == 'sender' and (n.get('ScopeKey') or '').lower() in senders)
            or (n['Scope'] == 'sender_domain' and (n.get('ScopeKey') or '').lower() in domains)]
    return ('Standing notes (learned from the owner - FOLLOW these):\n' + '\n'.join(hits)) if hits else ''


def dispatch(store, task_id: int, agent_name: str, instruction: str, actor: str = 'system',
             profile_override: dict = None) -> dict:
    """One open->close agent run on a task; the run row is the live progress channel."""
    agent = store.get_agent(agent_name)
    if not agent: raise ValueError(f'unknown agent: {agent_name}')
    profile = {**json.loads(agent.get('Config') or '{}'), **(profile_override or {})}
    run_id = store.start_run(task_id, agent_name, instruction, actor)
    store.audit('run', run_id, 'dispatch', actor, 'human', {'agent': agent_name, 'task': task_ref(task_id)}, run_id)
    store.update_task(task_id, {'Status': 'in_progress', 'Assignee': f'agent:{agent_name}'}, actor)
    trace = []
    wrote = {'at': 0.0}
    def _t(kind, name, detail):
        cap = 12000 if kind == 'prompt' else 2000
        detail = str(detail)[:cap]
        if kind == 'live' and trace and trace[-1]['kind'] == 'live' and trace[-1]['detail'] == detail: return
        trace.append({'at': datetime.now().isoformat(sep=' ', timespec='seconds'), 'kind': kind,
                      'name': name, 'detail': detail})
        # long streams: drop the oldest live line past 260 events, and flush live lines to
        # the DB at most ~1/s (everything else lands immediately; final flush is guaranteed)
        if len(trace) > 260:
            i = next((k for k, e in enumerate(trace) if e['kind'] == 'live'), None)
            if i is not None: trace.pop(i)
        if kind != 'live' or time.time() - wrote['at'] > 1.0:
            wrote['at'] = time.time()
            store.update_run(run_id, {'TraceJson': json.dumps(trace)})
    try:
        ctx = task_context(store, task_id)
        mem = memory_block(store, store.list_messages(task_id))
        soul = store.doc('soul')
        if agent.get('Kind') == 'coding':
            cdoc = store.doc('coder')
            if cdoc: soul = f'{soul}\n\n{cdoc}' if soul else cdoc
        # LEARNED.md's active sections (never its untested hypotheses) and the rolling DIGEST.md
        # ride along: the profile says how the owner works, the digest what is in flight today
        from .learn import injectable
        lrn, dig = injectable(store.doc('learned') or ''), (store.doc('digest') or '').strip()
        prompt = ((f"Operator's document (authoritative rules):\n{soul}\n\n---\n\n" if soul else '')
                  + (f"Learned profile (distilled from the owner's verdicts):\n{lrn}\n\n---\n\n" if lrn else '')
                  + (f'{dig}\n\n---\n\n' if dig else '')
                  + ctx + (f'\n\n{mem}' if mem else '') + f'\n\nInstruction: {instruction}')
        result, session_id, diff = run_cli(profile, prompt, _t)
        store.update_run(run_id, {'Status': 'done', 'Result': result, 'TraceJson': json.dumps(trace),
                                  **({'SessionId': session_id} if session_id else {}),
                                  **({'DiffText': diff} if diff else {})}, finished=True)
        store.add_comment(task_id, agent_name, 'agent', result)
        store.audit('run', run_id, 'finish', agent_name, 'agent', {'trace_events': len(trace)}, run_id)
        return {'run_id': run_id, 'status': 'done', 'result': result}
    except Exception as e:
        logger.exception(f'taskuary dispatch failed (run {run_id})')
        store.update_run(run_id, {'Status': 'error', 'LastError': str(e)[:2000], 'TraceJson': json.dumps(trace)}, finished=True)
        store.audit('run', run_id, 'error', agent_name, 'agent', str(e)[:2000], run_id)
        return {'run_id': run_id, 'status': 'error', 'result': None}
