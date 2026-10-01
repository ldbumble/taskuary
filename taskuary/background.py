"""What a Claude run left RUNNING when its turn ended - background shells, monitors, subagents. Claude's own word
first: its Stop payload lists them (`from_hook`); a Claude that does not send that list is read off its own
transcript instead (`pending` - the Stop hook names it: `transcript_path`).

Stop is the end of a RESPONSE. A coder that starts a long pull in the background, arms a monitor on it and says
"re-pulling Jan 2024 now" ends its turn there, and the pane sits at a bare prompt with "1 shell, 1 monitor still
running" under it - so every surface read "coder is waiting on you" while the work went on (the owner, 2026-10-01:
"since there is a sub agent doing work the main chat might wait but the process is still going"). When a job
ends Claude is woken by its notification, takes a turn, and Stops again, so each Stop re-reads this.

The transcript says when a job STARTS (the tool result carries `backgroundTaskId`, a monitor's `taskId` +
`timeoutMs`, a subagent's `isAsync` + `agentId`) and when it ENDS (a `<task-notification>` with a `<status>`,
a monitor's "[Monitor expired" event, a TaskStop). Claude itself says some stops leave no marker - a shell killed
from its UI - so every job also carries its own deadline, and one past it is not counted.
"""
import json, re, time
from datetime import datetime

SHELL_MS = 1_800_000      # Bash run_in_background's default timeout
_TID = re.compile(r'<task-id>([^<]+)</task-id>')
_ENDED = re.compile(r'<status>|\[Monitor expired')
# cheap substring gate: a transcript runs to tens of MB and only these lines can start or end a job
_MARKS = ('backgroundTaskId', '"timeoutMs"', 'async_launched', '<task-notification>', '"run_in_background":true',
          '"name":"Monitor"', '"name":"TaskStop"', '"name":"Agent"', '"name":"Task"')


def _epoch(ts) -> float:
    try: return datetime.fromisoformat(str(ts).replace('Z', '+00:00')).timestamp()
    except ValueError: return time.time()


def _started(r: dict, inp: dict, at: float):
    "(id, job) for a tool result that put work in the background, else None"
    if r.get('backgroundTaskId'):
        return r['backgroundTaskId'], {'kind': 'shell', 'what': inp.get('description') or str(inp.get('command') or '')[:120],
                                       'until': at + (inp.get('timeout') or SHELL_MS) / 1000}
    if r.get('taskId') and 'timeoutMs' in r:
        return r['taskId'], {'kind': 'monitor', 'what': inp.get('description') or '',
                             'until': None if r.get('persistent') else at + (r.get('timeoutMs') or 0) / 1000}
    if r.get('isAsync') and r.get('agentId'):
        return r['agentId'], {'kind': 'agent', 'what': r.get('description') or inp.get('description') or '', 'until': None}


def pending(path, now: float = None) -> list:
    """The jobs still running as of `now`: [{id, kind: shell|monitor|agent, what, until (epoch s, None = no deadline)}]."""
    now, uses, jobs = now or time.time(), {}, {}
    try: f = open(path, encoding='utf-8', errors='replace')
    except (OSError, TypeError): return []
    with f:
        for l in f:
            if not any(m in l for m in _MARKS): continue
            try: o = json.loads(l)
            except ValueError: continue
            c = o.get('content') if o.get('type') == 'queue-operation' else (o.get('message') or {}).get('content')
            if isinstance(c, str):
                # the queued copy counts as well as the delivered one: the job has ended even before Claude reads it
                if '<task-notification>' in c and _ENDED.search(c):
                    for i in _TID.findall(c): jobs.pop(i, None)
                continue
            for b in c if isinstance(c, list) else []:
                if not isinstance(b, dict): continue
                if b.get('type') == 'tool_use':
                    uses[b.get('id')] = b
                    if b.get('name') == 'TaskStop':
                        inp = b.get('input') or {}
                        jobs.pop(str(inp.get('task_id') or inp.get('shell_id') or ''), None)
                elif b.get('type') == 'tool_result' and isinstance(o.get('toolUseResult'), dict):
                    got = _started(o['toolUseResult'], (uses.get(b.get('tool_use_id')) or {}).get('input') or {}, _epoch(o.get('timestamp')))
                    if got: jobs[got[0]] = got[1]
    return [dict(id=k, **v) for k, v in jobs.items() if v['until'] is None or v['until'] > now]


def from_hook(p: dict):
    """The jobs Claude itself says are running, off its Stop payload - None when this Claude does not send the list.

    Claude 2.1.286 carries `background_tasks` on Stop and SubagentStop (measured 2026-10-01; the hooks reference does
    not list it): [{id, type: shell|subagent, status, description, command|agent_type}], shrinking as each job ends.
    A monitor is a `shell` there. The CLI's own word, so it needs no deadline; the transcript read is for a Claude
    without it. `ambient` is the SDK's mark for housekeeping a host should not count as activity."""
    got = p.get('background_tasks')
    if not isinstance(got, list): return None
    return [{'id': str(t.get('id') or ''), 'kind': 'agent' if t.get('type') == 'subagent' else str(t.get('type') or 'task'),
             'what': str(t.get('description') or t.get('command') or '')[:120], 'until': None}
            for t in got if isinstance(t, dict) and t.get('status', 'running') == 'running' and not t.get('ambient')]


def is_wake(prompt) -> bool:
    "a turn the CLI took because background work reported - a UserPromptSubmit nobody typed (Claude's, Copilot's)"
    return str(prompt or '').lstrip().startswith(('<task-notification>', '<system_notification>'))


# COPILOT (1.0.86, measured 2026-10-01) sends no list on Stop, but says both ends in its hooks: a shell started with
# `mode: async` answers "<command started in background with shellId: 0>", and its end is a Notification
# `shell_completed` naming "(shellId: 0)" - then Copilot wakes and takes a turn on it. `detach` is the other way: a
# server left to outlive the session, which nobody wakes for, so it is not counted. No timeout is said, so a cap.
_STARTED = re.compile(r'started in background with shellId:\s*([\w-]+)')
_SHELL_ID = re.compile(r'shellId:\s*([\w-]+)')
CAP_S = 7200


def track(jobs: dict, p: dict) -> None:
    "keep a session's own running jobs from its hook events (`jobs` lives on the pane: a pane and its jobs die together)"
    ev = p.get('hook_event_name')
    if ev == 'PostToolUse':
        inp, res = p.get('tool_input') or {}, p.get('tool_result') or p.get('tool_response') or {}
        m = _STARTED.search(str(res.get('text_result_for_llm') if isinstance(res, dict) else res))
        if m and isinstance(inp, dict) and not inp.get('detach'):
            jobs[m.group(1)] = {'id': m.group(1), 'kind': 'shell', 'what': str(inp.get('description') or inp.get('command') or '')[:120],
                                'until': time.time() + CAP_S}
    elif ev == 'Notification' and str(p.get('notification_type') or '').startswith('shell_'):
        m = _SHELL_ID.search(str(p.get('message') or ''))
        if m: jobs.pop(m.group(1), None)


def live(jobs, now: float = None) -> list:
    "the ones of a recorded list still inside their deadline"
    now = now or time.time()
    return [j for j in jobs or [] if isinstance(j, dict) and (j.get('until') is None or j['until'] > now)]


def summary(jobs) -> str:
    "'1 shell, 1 monitor still running' - the words Claude's own footer uses"
    n = {}
    for j in jobs: n[j['kind']] = n.get(j['kind'], 0) + 1
    return ', '.join(f"{v} {k}{'' if v == 1 else 's'}" for k, v in n.items()) + ' still running' if n else ''
