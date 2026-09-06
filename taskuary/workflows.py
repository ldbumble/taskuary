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
import json
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
    """A job that writes data or keeps state; a report only reads."""
    cfg = cfg_of(src_or_cfg); t = str(cfg.get('type') or '')
    return t == 'zoho_monthly_invoices' or (t == 'agent' and cfg.get('access') == 'write')


def runs_on(cfg: dict) -> str:
    """Which worker: coding only for actual code work - a checkout to work in, or said outright."""
    want = str(cfg.get('runs_on') or '').lower()
    if want in ('general', 'coding'): return want
    return 'coding' if cfg.get('cwd') else 'general'


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
            'allowed_actions': ['write'] if cfg.get('access') == 'write' or cfg.get('type') == 'zoho_monthly_invoices' else ['read'],
            'approvals': str(cfg.get('ask_first') or cfg.get('approvals') or '').strip(), 'done_when': str(cfg.get('done_when') or '').strip(),
            'schedule': {k: cfg[k] for k in ('cron', 'every_minutes', 'every', 'on_startup', 'tz', 'at') if cfg.get(k) is not None},
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
    lines = [f"WORKFLOW RUN: {defn['title']} - {'scheduled' if trigger == 'schedule' else 'run now by the owner'} at {when}.",
             'OBJECTIVE: ' + (defn['objective'] or (f"run the saved skill /{defn['skill']}" if defn['skill'] else '(none given)'))]
    if defn.get('inputs'): lines.append('INPUTS: ' + json.dumps(defn['inputs'], default=str))
    if context: lines.append('THIS RUN: ' + json.dumps(context, default=str))
    if defn.get('connections'): lines.append('CONNECTIONS: ' + ', '.join(str(c) for c in defn['connections']))
    if defn.get('steps'): lines.append('STEPS (the saved skill):\n' + defn['steps'].strip())
    lines.append('ALLOWED ACTIONS: ' + ("you may write to the connected systems this workflow names, through Taskuary's tools and proposals; "
                                        'anything outside them, and anything under ASK FIRST, waits for the owner'
                                        if 'write' in defn['allowed_actions'] else 'read only - propose changes, make none'))
    if defn.get('approvals'): lines.append('ASK FIRST: ' + defn['approvals'])
    if defn.get('done_when'): lines.append('DONE WHEN: ' + defn['done_when'])
    lines.append('This is a configured workflow, not an incoming request: no triage and no procedure selection apply. '
                 'Say --done with your result when it is finished.')
    return '\n'.join(lines)


def run(store, src, actor: str = 'schedule', trigger: str = 'schedule', context: dict = None) -> dict:
    """A triggered workflow goes straight to its worker: a task with the definition and this run's context,
    through the same capacity and retry gates as any unattended start - never through message triage."""
    from . import ingest
    defn = definition(store, src)
    when = datetime.now().strftime('%Y-%m-%d %H:%M')
    text, kind = brief(defn, trigger, when, context), definition(store, src)['runs_on']
    tid = store.create_task({'Title': f"{defn['title']} - {when}", 'Summary': text, 'Kind': kind, 'Status': 'open', 'Priority': 'normal',
                             'Source': 'workflow', 'SourceRef': f"workflow:{defn['source_id']}"}, actor)
    store.add_comment(tid, actor, 'agent', f"Workflow run ({trigger}): handed to the {'coding' if kind == 'coding' else 'regular'} agent with the workflow definition - no triage.")
    logger.info(f"workflow {defn['title']!r} ({trigger}) -> {task_ref(tid)} on the {kind} agent")
    if kind == 'coding': ingest._auto_code(store, tid)
    else: ingest._auto_general(store, tid, text)
    return {'task_id': tid, 'ref': task_ref(tid), 'kind': kind, 'title': defn['title'], 'trigger': trigger}
