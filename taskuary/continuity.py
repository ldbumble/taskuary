"""Reconnect saved conversations and surface unfinished work using records we already keep."""
import hashlib
import json
import os
import re


def context_key(store, pick, model):
    """A native conversation belongs to one provider configuration and working directory."""
    from .config import home
    row = store.get_agent(pick[4:]) if pick.startswith('cli:') else None
    config = json.loads((row or {}).get('Config') or '{}')
    # The general assistant's CLI runs in Taskuary scratch, not the coding profile's checkout.
    config = {k: v for k, v in config.items() if k not in ('cwd', 'cwd_map')}
    scope = [pick, model, config, str((home() / 'scratch').resolve()),
             os.environ.get('CODEX_HOME', ''), os.environ.get('CLAUDE_CONFIG_DIR', '')]
    return hashlib.sha256(json.dumps(scope, sort_keys=True).encode()).hexdigest()


def can_resume(store, pick):
    if not pick.startswith('cli:'): return False
    from .agents import resume_argv
    prof = json.loads((store.get_agent(pick[4:]) or {}).get('Config') or '{}')
    # over ACP the id is the protocol's own (session/new) and session/load is how it is picked back up:
    # devin has no argv resume flag and still reloads its sessions, yet the id it returned was dropped
    # on the floor and the row saved NativeId '' (measured 2026-09-20)
    return bool(resume_argv(prof, 'x')) or bool(prof.get('acp'))


def previous_work(store, limit=5):
    from . import general, terminal
    reviews = {r['TaskId']: r for r in reversed(store.list_reviews('pending')) if r.get('TaskId')}
    live = {s.task_id: s for s in list(terminal.SESSIONS.values()) if s.alive}
    result = []
    for row in store.previous_work():
        tid = row['TaskId']
        if general.is_dock(row): continue
        session = live.get(tid)
        if tid in general.OPENING or (session and (getattr(session, 'mode', '') != 'assistant' or session.busy)): continue
        review = reviews.get(tid)
        if row['Status'] == 'done' and not review: continue
        recap = re.sub(r'^(HANDOVER NOTE|CODER REPORT)\s*', '', row.get('Recap') or '').strip()
        recap = recap or 'A saved session is available. Continue from its existing work and handover.'
        result.append({'taskId': tid, 'title': row['Title'], 'recap': recap[:600],
                       'lastWorkedAt': row['LastWorkedAt'], 'action': 'review' if review else 'resume',
                       'reviewId': review['ReviewId'] if review else None})
        if len(result) >= limit: break
    return result


RESUME_PROMPT = (
    'The owner chose Resume for this task. Use the saved conversation and handover to pick up where '
    'work stopped. Briefly say what is already done, then continue the next unfinished step. '
    'Verify the current state before repeating any action. If you were waiting for an answer or '
    'approval, restate that one question and wait; do not invent the answer or treat Resume as approval '
    'to send, publish, or execute a pending action. If the result is ready, point the owner to it for review.'
)
