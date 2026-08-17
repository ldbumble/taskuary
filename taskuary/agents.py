"""Agent execution: any CLI is an agent. A profile ({cmd, args, resume_args, timeout, cwd,
cwd_map}) turns Claude Code, Codex, or your own wrapper into a Taskuary teammate: prompt
over STDIN (argv length limits are real on Windows), JSON output parsed when available
(Claude-style {result, session_id} -> resumable sessions), git diff captured around the
run so code changes are first-class, every run traced + audited.
"""
import json, os, subprocess
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


def _resolve_cmd(name: str) -> list:
    """Windows can't CreateProcess a bare 'claude': npm installs it as claude.cmd, which
    only PATH-resolves via which() and only executes through cmd /c."""
    import shutil
    path = shutil.which(name)
    if not path:
        raise FileNotFoundError(
            f"'{name}' not found on PATH - is the CLI installed? After installing, restart Taskuary so it sees the new PATH.")
    if os.name == 'nt' and path.lower().endswith(('.cmd', '.bat')):
        return ['cmd', '/c', path]
    return [path]


def run_cli(profile: dict, prompt: str, trace, resume: str = None):
    """One headless invocation of the configured CLI. Returns (result, session_id, diff)."""
    name = profile.get('cmd', 'claude')
    cmd = _resolve_cmd(name) + list(profile.get('args') or ['-p'])
    if resume and profile.get('resume_args'): cmd += list(profile['resume_args']) + [resume]
    cwd = profile.get('cwd')
    head0 = _git(cwd, 'rev-parse', 'HEAD')
    trace('prompt', 'prompt_sent_to_agent', prompt)
    trace('tool', 'cli', f'{name} cwd={cwd or os.getcwd()}' + (f' resume={resume}' if resume else ''))
    p = subprocess.run(cmd, input=prompt, capture_output=True, text=True, encoding='utf-8', errors='replace',
                       timeout=profile.get('timeout', 1200), cwd=cwd, shell=False)
    if p.returncode != 0: raise RuntimeError(f'{name} exit {p.returncode}: {(p.stderr or p.stdout or "")[:500]}')
    out, sid = parse_cli_json(p.stdout)
    trace('output', 'cli', out[-1000:])
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
    def _t(kind, name, detail):
        cap = 12000 if kind == 'prompt' else 2000
        trace.append({'at': datetime.now().isoformat(sep=' ', timespec='seconds'), 'kind': kind,
                      'name': name, 'detail': str(detail)[:cap]})
        store.update_run(run_id, {'TraceJson': json.dumps(trace)})
    try:
        ctx = task_context(store, task_id)
        mem = memory_block(store, store.list_messages(task_id))
        soul = store.get_doc('soul')
        if agent.get('Kind') == 'coding':
            cdoc = store.get_doc('coder')
            if cdoc: soul = f'{soul}\n\n{cdoc}' if soul else cdoc
        prompt = ((f"Operator's document (authoritative rules):\n{soul}\n\n---\n\n" if soul else '')
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
