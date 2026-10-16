"""Workflows are configured jobs; procedures are how a matching request is handled (PW-203 to PW-208).

A WORKFLOW is a scheduled or hand-run job the owner configured on the Reports tab's Workflows shelf: the
`agent` source with its write grant, or the monthly invoice job. It carries its objective, its configured
inputs, the connections it names, its steps (a saved skill), what it may do, what it must ask first, and
when it is done. A PROCEDURE is a playbook (playbooks.py): how this company handles ONE kind of incoming
request, chosen by triage when a message is an instance of it. The two were one shelf; converting every
playbook into a scheduled job would have been wrong, so the existing definitions stay exactly where they
are and this module only reads them apart (PW-207).

A triggered workflow used to run inside the report loop through a coding CLI, then file its answer as a
report that triage read back as a fresh arrival. Now it is dispatched straight to its worker (PW-204): a
task carrying the definition and this run's context, opened through the same capacity and startup-retry
gates as any unattended start (ingest._auto_general / _auto_code), never through message triage, and never
a coding agent unless the definition says the job is code (a checkout to work in, or `runs_on: coding`).
The brief the worker reads is the workflow's own (PW-206); no procedure selection is needed for it.
"""
import json, threading
from datetime import datetime
from loguru import logger

from .store import task_ref

WORKFLOW_TYPES = ('agent', 'zoho_monthly_invoices')


def cfg_of(src) -> dict:
    if isinstance(src, dict) and 'ConfigJson' in src:
        try: return json.loads(src.get('ConfigJson') or '{}')
        except ValueError: return {}
    return dict(src or {})


def is_workflow(src_or_cfg) -> bool:
    """A job that writes data or keeps state; a report only reads.

    A job DRIVEN IN THE BROWSER is one of these even when it only reads, because the report loop cannot
    run it at all: reports.run_agent builds its CLI read-only and with no shell, so `agent-browser` is
    not there to call and yesterday's sign-in is not there to reuse. A walk that signed into a portal
    and was then promoted to a daily job produced a report that could only fail (the owner, 2026-09-15:
    "why can't it save the workflow and browser state for tomorrow? that's the whole idea of a
    workflow"). The workflow road hands it to a real session, which opens the same named browser with
    the owner's restored profile."""
    cfg = cfg_of(src_or_cfg); t = str(cfg.get('type') or '')
    return t == 'zoho_monthly_invoices' or (t == 'agent' and (cfg.get('access') == 'write' or cfg.get('browser')))


def runs_on(cfg: dict) -> str:
    """Which worker: coding only for actual code work - a checkout to work in, or said outright."""
    want = str(cfg.get('runs_on') or '').lower()
    if want in ('general', 'coding'): return want
    return 'coding' if cfg.get('cwd') else 'general'


def _names(store, ids) -> list:
    out = []
    for i in ids:
        try: c = store.get_connector(int(i))
        except (TypeError, ValueError): c = None
        out.append(f"{c.get('Name') or c.get('Type')} (connection {i})" if c else str(i))
    return out


def definition(store, src) -> dict:
    """The workflow as data (PW-203), read from the source it has always been stored on."""
    cfg = cfg_of(src); sid = src.get('SourceId') if isinstance(src, dict) else None
    skill, steps = str(cfg.get('skill') or '').strip().lstrip('/'), ''
    if skill:
        from . import config
        p = config.home() / 'skills' / skill / 'SKILL.md'
        try: steps = p.read_text(encoding='utf-8') if p.is_file() else ''
        except OSError: steps = ''
    return {'source_id': sid, 'type': cfg.get('type'), 'title': cfg.get('title') or (src.get('Address') if isinstance(src, dict) else '') or '',
            'objective': str(cfg.get('prompt') or cfg.get('objective') or '').strip(), 'skill': skill, 'steps': steps,
            'inputs': cfg.get('inputs') or {},
            'connections': list(cfg.get('uses') or ([cfg['connector_id']] if cfg.get('connector_id') else [])),
            # ...said by name in the brief: "CONNECTIONS: 38" told the agent nothing
            'connection_names': _names(store, cfg.get('uses') or ([cfg['connector_id']] if cfg.get('connector_id') else [])),
            'allowed_actions': ['write'] if cfg.get('access') == 'write' or cfg.get('type') == 'zoho_monthly_invoices' else ['read'],
            'approvals': str(cfg.get('ask_first') or cfg.get('approvals') or '').strip(), 'done_when': str(cfg.get('done_when') or '').strip(),
            'browser': bool(cfg.get('browser')),
            'schedule': {k: cfg[k] for k in ('cron', 'daily_at', 'every_minutes', 'every', 'on_startup', 'tz', 'at') if cfg.get(k) is not None},
            'runs_on': runs_on(cfg), 'agent': cfg.get('agent') or None,
            'enabled': bool(src.get('Active', 1)) if isinstance(src, dict) else True}


def catalog(store) -> dict:
    """Configured workflows on one shelf, request procedures on the other - never the same thing (PW-203/207)."""
    from . import playbooks
    flows = [definition(store, s) for s in store.list_sources(active_only=False) if s.get('Channel') == 'report' and is_workflow(s)]
    procs = [{'slug': b['slug'], 'title': b['title'], 'when': b['when'], 'uses': b['uses'], 'about_code': b['about_code']} for b in playbooks.list_all()]
    return {'workflows': flows, 'procedures': procs}


def brief(defn: dict, trigger: str, when: str, context: dict = None) -> str:
    """What the worker is handed for THIS run: the definition and the run's own context (PW-204/206)."""
    said = {'schedule': 'scheduled', 'assistant': 'started by the assistant for the owner', 'phone': 'run now by the owner from their phone'}
    lines = [f"WORKFLOW RUN: {defn['title']} - {said.get(trigger, 'run now by the owner')} at {when}.",
             'OBJECTIVE: ' + (defn['objective'] or (f"run the saved skill /{defn['skill']}" if defn['skill'] else '(none given)'))]
    if defn.get('inputs'): lines.append('INPUTS: ' + json.dumps(defn['inputs'], default=str))
    if context: lines.append('THIS RUN: ' + json.dumps(context, default=str))
    if defn.get('connections'): lines.append('CONNECTIONS: ' + ', '.join(str(c) for c in defn.get('connection_names') or defn['connections']))
    if defn.get('steps'): lines.append('STEPS (the saved skill):\n' + defn['steps'].strip())
    lines.append('ALLOWED ACTIONS: ' + ("you may write to the connected systems this workflow names, through Taskuary's tools and proposals; "
                                        'anything outside them, and anything under ASK FIRST, waits for the owner'
                                        if 'write' in defn['allowed_actions'] else 'read only - propose changes, make none'))
    # the sign-in the owner typed by hand on an earlier run is in the profile this browser restores
    # (browserview.RESTORE_KEY), so the job starts signed in for as long as the site lets it
    if defn.get('browser'):
        lines.append('BROWSER: this job is driven in the browser the owner is watching, opened with their saved '
                     'profile - the sign-in they typed by hand on an earlier run is restored with it. LOOK FIRST: '
                     'open the page and read it. Most runs are already signed in and nobody needs to be asked; a '
                     'scheduled run happens when the owner is not there. Only when the page actually turns you away '
                     'do you stop - leave it on the sign-in screen and ask them to type it in the pane. Never type '
                     'a password or a code yourself.')
    if defn.get('approvals'): lines.append('ASK FIRST: ' + defn['approvals'])
    if defn.get('done_when'): lines.append('DONE WHEN: ' + defn['done_when'])
    lines.append('This is a configured workflow, not an incoming request: no triage and no procedure selection apply. '
                 'Say --done with your result when it is finished.')
    return '\n'.join(lines)


# WHO STARTED THIS RUN, kept on the task it made (the owner, 2026-10-16: "what does it show triggered it in the task card?"): a
# workflow task has no message behind it and nobody triaged it, so this tag is the only thing that can say where it came from
TRIGGER_TAG = 'workflow-trigger:'
STARTED_BY = {'schedule': 'its schedule', 'manual': 'you (Run now)', 'assistant': 'the assistant', 'phone': 'you, from your phone'}
_STARTING, _LOCK = set(), threading.Lock()      # runs whose worker is on its way: no session yet, and no queue row


def _spawn(fn): threading.Thread(target=fn, daemon=True, name='workflow-start').start()


def trigger_of(task) -> str:
    tags = [x.strip() for x in str((task or {}).get('Tags') or '').split(',')]
    return next((x[len(TRIGGER_TAG):] for x in tags if x.startswith(TRIGGER_TAG)), '')


def source_of(store, task):
    """The workflow a run task came from, while it still exists."""
    ref = str((task or {}).get('SourceRef') or '')
    if (task or {}).get('Source') != 'workflow' or not ref.startswith('workflow:'): return None
    try: return store.get_source(int(ref.split(':', 1)[1]))
    except (TypeError, ValueError): return None


def cwd_of(store, task) -> str | None:
    """The folder a coding workflow works in - its own `cwd`, never a checkout guessed from the run's words."""
    src = source_of(store, task)
    return (str(cfg_of(src).get('cwd') or '').strip() or None) if src else None


_DAYS = {'0': 'Sundays', '1': 'Mondays', '2': 'Tuesdays', '3': 'Wednesdays', '4': 'Thursdays', '5': 'Fridays', '6': 'Saturdays',
         '7': 'Sundays', '1-5': 'weekdays', '*': 'daily'}


def when_words(cfg: dict) -> str:
    """The clock as the owner says it - "Mondays 08:00" - for the common crons; anything else as reports.schedule_words says it."""
    from .reports import schedule_words
    if cfg.get('daily_at') and not cfg.get('cron') and not cfg.get('every_minutes'): return f"daily {cfg['daily_at']}"
    m, h, dom, mon, dow = (str(cfg.get('cron') or '').split() + [''] * 5)[:5]
    if m.isdigit() and h.isdigit() and mon == '*':
        at = f'{int(h):02d}:{int(m):02d}'
        if dom == '*' and dow in _DAYS: return f'{_DAYS[dow]} {at}'
        if dom.isdigit() and dow == '*': return f'day {dom} of each month, {at}'
    return schedule_words(cfg)


def of_task(store, task) -> dict | None:
    """What the task card says about a workflow run: which workflow, and what started it (TaskPage's header and Came from)."""
    if (task or {}).get('Source') != 'workflow': return None
    src, trig = source_of(store, task), trigger_of(task)
    cfg = cfg_of(src) if src else {}
    title = cfg.get('title') or (src or {}).get('Address') or str(task.get('Title') or '').rsplit(' - ', 1)[0]
    return {'source_id': (src or {}).get('SourceId'), 'title': title, 'trigger': trig, 'schedule': when_words(cfg) if src else '',
            'started_by': STARTED_BY.get(trig, '')}


def running(store, sid) -> dict | None:
    """The previous run of this workflow while its worker still has it: a live session, a start on its way, or a queued start that
    has not given up. One that is merely open - waiting on the owner's yes - is not running, so tomorrow's run still goes."""
    from . import terminal
    from .agents import LIVE_STATUSES
    for t in store.dock_tasks(f'workflow:{sid}', limit=3):
        if t.get('Status') not in LIVE_STATUSES: continue
        q = store.get_dispatch(t['TaskId'])
        if t['TaskId'] in _STARTING or terminal.for_task(t['TaskId'], details=False) or (q and q.get('State') != 'failed'): return t
    return None


def run(store, src, actor: str = 'schedule', trigger: str = 'schedule', context: dict = None, background: bool = True) -> dict:
    """EVERY RUN OF A WORKFLOW IS THIS ONE ROAD - its clock, Run now, the assistant, the phone: a task with the definition and this
    run's context, worked by its agent through the same capacity and retry gates as any unattended start, never through message
    triage. A scheduled run with a checkout used to go down the REPORT road instead - a one-shot CLI whose answer was filed under
    Reports - while Run now made a task (the owner, 2026-10-16: "Run now creates task but if it runs on schedule it should also
    show up as task").

    `background`: the task is made now and the worker starts on its own thread - a general session's first turn holds the call
    for as long as the agent works, which kept the owner from their task and held every report behind it on the clock."""
    from . import ingest, browserview
    from .agents import CODING_KINDS
    defn = definition(store, src)
    busy = running(store, defn['source_id'])
    if busy:
        # ...and one run at a time: a tick that comes round while the last run still works would put a second agent on the same job
        store.add_comment(busy['TaskId'], actor, 'agent', f"Workflow run ({trigger}) not started: this run is still working.")
        return {'task_id': busy['TaskId'], 'ref': task_ref(busy['TaskId']), 'kind': busy.get('Kind'), 'title': defn['title'],
                'trigger': trigger, 'busy': True}
    when, kind = datetime.now().strftime('%Y-%m-%d %H:%M'), defn['runs_on']
    text = brief(defn, trigger, when, context)
    # a browser job's run task asks for a browser the way the walk that taught it did: the tag is what
    # general.py reads to launch one, bound to this session and restored from the owner's profile
    tags = ','.join(x for x in (browserview.WANTS if kind == 'general' and defn.get('browser') else '', f'{TRIGGER_TAG}{trigger}') if x)
    # ...and it runs AS the worker it names, wearing that worker's rules (an AP workflow gets AP.md), as reports.run_agent did.
    # A coding name on a GENERAL run is a brain picked long ago, not a role; a coding run takes the profile it names, else the
    # coding profile (ingest._auto_code) - and either way the default brain runs it.
    row = store.get_agent(defn['agent']) if defn.get('agent') else None
    named = bool(row) and (kind == 'coding' or str(row.get('Kind') or '').lower() not in CODING_KINDS)
    tid = store.create_task({'Title': f"{defn['title']} - {when}", 'Summary': text, 'Kind': kind, 'Status': 'open', 'Priority': 'normal',
                             'Source': 'workflow', 'SourceRef': f"workflow:{defn['source_id']}", 'Tags': tags,
                             **({'Assignee': f"agent:{defn['agent']}"} if named else {})}, actor)
    store.add_comment(tid, actor, 'agent', f"Workflow run ({trigger}): handed to the {'coding' if kind == 'coding' else 'regular'} agent "
                                           'with the workflow definition - no triage.')
    logger.info(f"workflow {defn['title']!r} ({trigger}) -> {task_ref(tid)} on the {kind} agent")
    with _LOCK: _STARTING.add(tid)
    def start():
        try:
            if kind == 'coding': ingest._auto_code(store, tid)
            else: ingest._auto_general(store, tid, text)
        finally:
            with _LOCK: _STARTING.discard(tid)
    if background: _spawn(start)
    else: start()
    return {'task_id': tid, 'ref': task_ref(tid), 'kind': kind, 'title': defn['title'], 'trigger': trigger}
