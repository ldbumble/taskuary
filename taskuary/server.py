"""The local HTTP API + built-in minimal web UI. Localhost-only by default; set
[server].token in config to require an X-Taskuary-Token header (for LAN/self-hosting).
"""
import asyncio, json, threading
from datetime import datetime
from pathlib import Path
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from . import config
from . import store as store_mod
from .store import SQLiteStore, task_ref
from .ingest import ingest_message, task_from_message
from .reports import PLANNED, REGISTRY, render_report, resolve_cfg, run_due_reports, run_report_source
from . import agents as hub_agents
from . import policy as policy_engine
from . import terminal as hub_term
from .coder import run_coding_task
from .converse import message_agent

cfg = config.load()
store = SQLiteStore(config.db_path())
for name, prof in cfg.get('agents', {}).items():
    store.upsert_agent(name, prof.get('kind', 'coding'), 'cli', json.dumps(prof))
app = FastAPI(title='Taskuary', docs_url='/api/docs')
ACTOR = 'owner'


from loguru import logger
import time as _time

@app.middleware('http')
async def request_log(request: Request, call_next):
    t0 = _time.time()
    try:
        resp = await call_next(request)
    except Exception:
        logger.exception(f'{request.method} {request.url.path} crashed')
        raise
    if request.url.path.startswith('/api'):
        logger.debug(f'{request.method} {request.url.path} -> {resp.status_code} ({int((_time.time() - t0) * 1000)}ms)')
    return resp

@app.middleware('http')
async def token_gate(request: Request, call_next):
    tok = cfg['server'].get('token')
    if tok and request.url.path.startswith('/api') and request.headers.get('X-Taskuary-Token') != tok:
        return HTMLResponse('unauthorized', status_code=401)
    return await call_next(request)


# pydantic v2: `str = None` is NOT optional - an explicit JSON null then 422s the request
# (the UI sends e.g. final_text: null on reject). Every nullable field must say `| None`.
class TaskBody(BaseModel):
    Title: str | None = None; Summary: str | None = None; Kind: str | None = None
    Priority: str | None = None; Status: str | None = None; Tags: str | None = None
class MsgBody(BaseModel):
    external_id: str | None = None; channel: str = 'api'; subject: str | None = None
    body: str | None = None; from_name: str | None = None; from_email: str | None = None
    conversation_id: str | None = None; sent_at: str | None = None
    source_link: str | None = None; source_name: str | None = None
class TextBody(BaseModel): body: str
class DecideBody(BaseModel): verb: str; final_text: str | None = None; note: str | None = None
class CodeBody(BaseModel): repo: str | None = None; agent: str | None = None
class DocBody(BaseModel): content: str
class SettingBody(BaseModel): name: str; value: str
class SourceBody(BaseModel):
    SourceId: int | None = None; ConnectorId: int | None = None; Channel: str | None = None
    Address: str | None = None; ConfigJson: str | None = None; Active: bool | None = None
class DispatchBody(BaseModel): agent: str = 'coder'; instruction: str | None = None
class PolicyBody(BaseModel):
    PolicyId: int | None = None; Name: str | None = None; Kind: str | None = None
    Pattern: str | None = None; Action: str | None = None; Reason: str | None = None
    SortOrder: int | None = None; Active: bool | None = None
class MemoryBody(BaseModel): note: str; scope: str = 'global'; scope_key: str | None = None
class MemoryToggle(BaseModel): active: bool
class ConnectorBody(BaseModel):
    ConnectorId: int | None = None; Type: str | None = None; Name: str | None = None
    ConfigJson: str | None = None; Secret: str | None = None; Active: bool | None = None
    Roles: str | None = None                       # csv of trigger,report,tool - see store.ROLES


@app.get('/', response_class=HTMLResponse)
def index():
    return (Path(__file__).parent / 'web' / 'index.html').read_text(encoding='utf-8')

_assets = Path(__file__).parent / 'web' / 'assets'
if _assets.is_dir():
    from fastapi.staticfiles import StaticFiles
    app.mount('/assets', StaticFiles(directory=str(_assets)), name='assets')

from fastapi.responses import FileResponse

@app.get('/favicon.ico', include_in_schema=False)
def favicon(): return FileResponse(Path(__file__).parent / 'web' / 'favicon.ico')

@app.get('/favicon.png', include_in_schema=False)
def favicon_png(): return FileResponse(Path(__file__).parent / 'web' / 'favicon.png')


from . import __version__ as _ver
_started = datetime.now().isoformat(sep=' ', timespec='seconds')

@app.get('/api/version')
def version(): return {'version': _ver, 'started': _started}

@app.get('/api/feed')
def feed(limit: int = 100, offset: int = 0, pending_only: bool = False, channel: str = None, source: str = None):
    days = int(store.get_settings().get('feed_days', 14))
    return {'data': store.feed(min(limit, 500), days, pending_only, channel, max(offset, 0), source)}


@app.get('/api/tasks')
def tasks(status: str = None): return {'data': [{**t, 'ref': task_ref(t['TaskId'])} for t in store.list_tasks(status)]}

@app.post('/api/tasks')
def create_task(body: TaskBody):
    if not body.Title: raise HTTPException(422, 'Title is required')
    tid = store.create_task({k: v for k, v in body.dict().items() if v is not None}, ACTOR)
    store.audit('task', tid, 'create', ACTOR)
    return {'taskId': tid, 'ref': task_ref(tid)}

@app.get('/api/tasks/{task_id}')
def task_detail(task_id: int):
    d = store.task_detail(task_id)
    if not d: raise HTTPException(404, 'task not found')
    return d

@app.patch('/api/tasks/{task_id}')
def update_task(task_id: int, body: TaskBody):
    store.update_task(task_id, {k: v for k, v in body.dict().items() if v is not None}, ACTOR)
    return {'ok': True}

@app.post('/api/tasks/{task_id}/message')
def msg_agent(task_id: int, body: TextBody, background: BackgroundTasks):
    if not store.get_task(task_id): raise HTTPException(404, 'task not found')
    store.add_comment(task_id, ACTOR, 'human', body.body)
    background.add_task(message_agent, store, task_id, body.body, ACTOR)
    return {'chat': 'running'}

def _github_cfg():
    from .coder import github_cfg
    return github_cfg(store)

@app.post('/api/tasks/{task_id}/code')
def code(task_id: int, background: BackgroundTasks, body: CodeBody = None):
    if not store.get_task(task_id): raise HTTPException(404, 'task not found')
    agent = (body.agent if body else None) or 'coder'
    if not store.get_agent(agent): raise HTTPException(422, f'unknown agent: {agent}')
    background.add_task(run_coding_task, store, task_id, ACTOR, (body.repo if body else None), _github_cfg(), agent)
    return {'coder': 'running', 'agent': agent}

@app.post('/api/tasks/{task_id}/comments')
def comment(task_id: int, body: TextBody):
    store.add_comment(task_id, ACTOR, 'human', body.body)
    return {'ok': True}

@app.post('/api/tasks/{task_id}/dispatch')
def dispatch_task(task_id: int, body: DispatchBody, background: BackgroundTasks):
    if not store.get_task(task_id): raise HTTPException(404, 'task not found')
    if not store.get_agent(body.agent): raise HTTPException(422, f'unknown agent: {body.agent}')
    background.add_task(hub_agents.dispatch, store, task_id, body.agent, body.instruction or 'Work this task.', ACTOR)
    return {'dispatch': 'running', 'agent': body.agent}

@app.post('/api/tasks/{task_id}/not-a-task')
def not_a_task(task_id: int):
    """Owner verdict: never needed to be a task. Teaches (sender ignore policy + memory
    note), then deletes the task - its messages stay in the feed as 'filed'."""
    if not store.get_task(task_id): raise HTTPException(404, 'task not found')
    msgs, learned = store.list_messages(task_id), None
    em = (msgs[0].get('FromEmail') or '').lower() if msgs else ''
    if em:
        store.save_policy({'Name': f'not-a-task: {em}', 'Kind': 'sender', 'Pattern': em, 'Action': 'ignore',
                           'Reason': 'owner said not a task', 'SortOrder': 50, 'Active': 1}, ACTOR)
        mid = store.add_memory({'Scope': 'sender', 'ScopeKey': em, 'Source': 'verdict', 'Active': 1, 'CreatedBy': ACTOR,
                                'Note': f"Messages from {em} like '{(msgs[0].get('Subject') or '')[:80]}' are not tasks - do not open tasks or draft replies."})
        learned = {'policy': em, 'memory_id': mid}
    store.audit('task', task_id, 'not_a_task_delete', ACTOR)
    store.delete_task(task_id)
    return {'ok': True, 'learned': learned}

@app.post('/api/tasks/purge-dropped')
def purge_dropped():
    victims = [t['TaskId'] for t in store.list_tasks('dropped')]
    for tid in victims:
        store.audit('task', tid, 'purge_dropped', ACTOR)
        store.delete_task(tid)
    return {'ok': True, 'deleted': len(victims)}

@app.get('/api/messages/{mid}')
def get_message(mid: int):
    """One message, whole body - the timeline row only carries a 4000-char preview."""
    m = store.get_message(mid)
    if not m: raise HTTPException(404, 'message not found')
    return m

@app.post('/api/messages/{mid}/dispatch')
def dispatch_message(mid: int, body: DispatchBody, background: BackgroundTasks):
    """Hand ANY timeline item (failed report, email, chat) to an agent with your own
    prompt. Messages that are not on a task yet become one first, so the run carries the
    full context (subject, sender, body, thread) the agent needs."""
    m = store.get_message(mid)
    if not m: raise HTTPException(404, 'message not found')
    if not store.get_agent(body.agent): raise HTTPException(422, f'unknown agent: {body.agent}')
    tid = m.get('TaskId') or task_from_message(store, mid, ACTOR)
    background.add_task(hub_agents.dispatch, store, tid, body.agent,
                        body.instruction or 'Investigate this and fix it end to end.', ACTOR)
    return {'dispatch': 'running', 'agent': body.agent, 'taskId': tid, 'ref': task_ref(tid)}

@app.get('/api/runs/live')
def live_runs(lines: int = 3):
    """The tail of every run that is working right now - the Board renders it as a tiny
    console on each card (the full trace is on the task)."""
    out = []
    for r in store.running_runs():
        try: evs = [e for e in json.loads(r.get('TraceJson') or '[]') if e.get('kind') == 'live']
        except ValueError: evs = []                    # mid-write JSON: next poll fixes it
        out.append({'RunId': r['RunId'], 'TaskId': r['TaskId'], 'AgentName': r['AgentName'],
                    'StartedAt': r['StartedAt'], 'tail': [e['detail'] for e in evs[-max(1, min(lines, 10)):]]})
    return {'data': out}

@app.get('/api/runs/{run_id}')
def get_run(run_id: int):
    r = store.get_run(run_id)
    if not r: raise HTTPException(404, 'run not found')
    return r

@app.get('/api/reviews')
def reviews(status: str = None): return {'data': store.list_reviews(status)}

@app.post('/api/reviews/{rid}/decide')
def decide(rid: int, body: DecideBody):
    rv = store.get_review(rid)
    if not rv: raise HTTPException(404, 'review not found')
    verb2status = {'approve': 'approved', 'edit': 'edited', 'reject': 'rejected', 'no_reply': 'no_reply'}
    if body.verb not in verb2status: raise HTTPException(422, 'bad verb')
    final = body.final_text if body.verb == 'edit' else (rv.get('DraftText') if body.verb == 'approve' else None)
    store.decide_review(rid, verb2status[body.verb], final, ACTOR, body.note)
    if final and rv.get('TaskId'): store.add_comment(rv['TaskId'], ACTOR, 'human', f'Reviewed draft ({body.verb}):\n{final}')
    if body.verb == 'no_reply' and rv.get('TaskId'): store.update_task(rv['TaskId'], {'Status': 'done'}, ACTOR)
    # reply-only items are not real tasks: answering them IS the work, so close on decision
    if body.verb in ('approve', 'edit') and rv.get('TaskId'):
        t = store.get_task(rv['TaskId'])
        if (t or {}).get('Kind') == 'reply' and t.get('Status') not in ('done', 'dropped'):
            store.update_task(rv['TaskId'], {'Status': 'done'}, ACTOR)
    store.audit('review', rid, body.verb, ACTOR, detail={'kind': rv.get('Kind')})
    return {'ok': True, 'status': verb2status[body.verb]}

@app.post('/api/reviews/{rid}/draft')
def draft_review(rid: int):
    """(Re)generate the AI draft for a pending review inline."""
    rv = store.get_review(rid)
    if not rv: raise HTTPException(404, 'review not found')
    names = [a['Name'] for a in store.list_agents()]
    name = 'responder' if 'responder' in names else (names[0] if names else None)
    if not name: raise HTTPException(422, 'no agents configured')
    out = hub_agents.dispatch(store, rv['TaskId'], name, 'Draft the reply this message needs.', ACTOR)
    if out['status'] != 'done': raise HTTPException(502, 'draft agent failed - see the run log')
    store.update_review_draft(rid, out['result'], out['run_id'])
    store.audit('review', rid, 'redraft', ACTOR, run_id=out['run_id'])
    return {'ok': True, 'draft': out['result'], 'runId': out['run_id']}

def _llm():
    try:
        from .llm import build_llm
        return build_llm(store)
    except Exception:
        return None

@app.post('/api/ingest/push')
def push(body: MsgBody):
    m = body.dict()
    m['external_id'] = m.get('external_id') or f'api:{datetime.now().isoformat()}'
    m['sent_at'] = m.get('sent_at') or datetime.now().isoformat(sep=' ', timespec='seconds')
    out = ingest_message(store, m, llm=_llm())
    return {**out, 'ref': task_ref(out['task_id']) if out.get('task_id') else None}

@app.post('/api/reports/run')
def reports_run(): return {'ran': run_due_reports(store)}

@app.get('/api/sources')
def sources():
    # default_repo rides along so the Board's repo picker preselects it
    return {'data': store.list_sources(active_only=False),
            'default_repo': (cfg.get('github') or {}).get('default_repo')}

@app.post('/api/sources')
def save_source(body: SourceBody):
    fields = {k: (int(v) if k == 'Active' else v) for k, v in body.dict().items() if v is not None}
    fields.setdefault('Owner', ACTOR)
    sid = store.save_source(fields, ACTOR)
    from .docsync import sync_connections
    sync_connections(store, ACTOR)
    return {'sourceId': sid}

@app.delete('/api/sources/{sid}')
def delete_source(sid: int):
    if not store.get_source(sid): raise HTTPException(404, 'source not found')
    store.delete_source(sid)
    store.audit('source', sid, 'delete', ACTOR)
    from .docsync import sync_connections
    sync_connections(store, ACTOR)
    return {'ok': True}

@app.post('/api/sources/{sid}/run')
def run_source_now(sid: int):
    src = store.get_source(sid)
    if not src: raise HTTPException(404, 'source not found')
    out = run_report_source(store, src, _llm())
    store.touch_source(sid)
    return out

@app.get('/api/report-types')
def report_types():
    return {'data': [{'type': t, 'status': 'planned' if t in PLANNED else 'builtin'} for t in REGISTRY]}

@app.get('/api/connectors')
def connectors():
    """Channel connector cards (outlook / teams / github). Secrets are write-only."""
    return {'data': store.list_connectors()}

@app.get('/api/brains')
def brains():
    """Everything that could do intent triage: cloud AI connectors with a key, plus your
    CLI agents (same brain that codes). Value goes into the `triage_ai` setting."""
    from .llm import AI_TYPES
    out = [{'value': '', 'label': 'auto — first active AI connector', 'kind': 'auto', 'ready': True}]
    out += [{'value': f"connector:{c['Type']}", 'label': c['Name'], 'kind': 'api',
             'ready': bool(c['Active'] and c['HasSecret'])}
            for c in store.list_connectors() if c['Type'] in AI_TYPES]
    out += [{'value': f"cli:{a['Name']}", 'label': f"{a['Name']} (CLI agent)", 'kind': 'cli', 'ready': True}
            for a in store.list_agents()]
    return {'data': out, 'current': store.get_settings().get('triage_ai') or ''}

@app.post('/api/connectors')
def save_connector(body: ConnectorBody):
    fields = {k: (int(v) if k == 'Active' else v) for k, v in body.dict().items() if v is not None}
    if fields.get('Roles') is not None:
        bad = {r for r in fields['Roles'].split(',') if r} - set(store_mod.ROLES)
        if bad: raise HTTPException(422, f"unknown role(s): {', '.join(sorted(bad))}")
    if not fields.get('ConnectorId') and not (fields.get('Type') and fields.get('Name')):
        raise HTTPException(422, 'new connectors need Type and Name')
    cid = store.save_connector(fields, ACTOR)
    safe = {k: v for k, v in fields.items() if k != 'Secret'} | ({'secret': 'updated'} if 'Secret' in fields else {})
    store.audit('connector', cid, 'edit' if body.ConnectorId else 'create', ACTOR, detail=safe)
    discovery = None
    # a new GitHub PAT is all the config there is: saving the token IS connecting - and
    # re-ENABLING the connector re-runs discovery too (refreshes the SOUL.md repo map,
    # incl. README summaries for repos with no description)
    c = store.get_connector(cid, with_secret=True) or {}
    if c.get('Type') == 'github' and c.get('Secret') and ('Secret' in fields or fields.get('Active')):
        try:
            from .channels import github_discover
            discovery = github_discover(store, c, ACTOR)
        except Exception as e:
            discovery = {'error': str(e)[:300]}
    from .docsync import sync_connections
    sync_connections(store, ACTOR)
    return {'ok': True, 'connectorId': cid, 'discovery': discovery}

@app.post('/api/connectors/{cid}/reset')
def connector_reset(cid: int):
    c = store.get_connector(cid)
    if not c: raise HTTPException(404, 'connector not found')
    store.reset_connector(cid)
    store.audit('connector', cid, 'reset', ACTOR, detail={'type': c['Type']})
    from .docsync import sync_connections
    sync_connections(store, ACTOR)
    return {'ok': True}

@app.post('/api/connectors/{cid}/test')
def connector_test(cid: int):
    from .channels import test_connector
    if not store.get_connector(cid): raise HTTPException(404, 'connector not found')
    out = test_connector(store, cid)
    store.audit('connector', cid, 'test_ok' if out['ok'] else 'test_failed', ACTOR, detail=out['detail'])
    return out

@app.post('/api/tools/run')
def tool_run(body: dict):
    """The agents' hands on your other systems: run ONE query/script through a connection
    the owner marked as a tool, and get the raw output back (no AI pass, no timeline row).
    Same executors the Reports tab uses, same saved credentials - so an agent working a
    task can look something up in SQL Server, run a script on a box, or call an MCP tool.
    A connection without the 'tool' role refuses."""
    t = (body or {}).get('type')
    if t not in REGISTRY: raise HTTPException(422, f'unknown tool type: {t}')
    conn = store.get_connector_by_type(t)
    if conn and 'tool' not in store_mod.roles_of(conn):
        raise HTTPException(403, f'the {t} connection is not marked as an agent tool (Connectors → {t} → Role)')
    try:
        head, out = REGISTRY[t](resolve_cfg(store, {**body, 'type': t}))
    except Exception as e:
        store.audit('tool', (conn or {}).get('ConnectorId', 0), 'run_failed', ACTOR, detail={'type': t, 'error': str(e)[:300]})
        return {'ok': False, 'error': str(e)[:1000]}
    store.audit('tool', (conn or {}).get('ConnectorId', 0), 'run', ACTOR, detail={'type': t, 'headline': str(head)[:200]})
    return {'ok': True, 'headline': head, 'output': (out or '')[:20000]}

@app.post('/api/reports/preview')
def report_preview(body: dict):
    """Dry-run a report config - executor plus the AI pass when ai_prompt is set -
    without filing a row. Exactly what a scheduled run would produce."""
    try:
        head, summary = render_report(store, body, _llm() if body.get('ai_prompt') else None)
        return {'ok': True, 'headline': head, 'summary': summary[:4000]}
    except Exception as e:
        return {'ok': False, 'error': str(e)[:500]}

@app.get('/api/mssql/drivers')
def mssql_drivers():
    try:
        from .mssql import drivers
        return {'data': drivers()}
    except Exception:
        return {'data': []}

@app.post('/api/mcp/tools')
def mcp_tools(body: dict):
    """List the tools an MCP server exposes (spawns it briefly over stdio)."""
    try:
        from .mcp import list_tools
        return {'ok': True, 'data': list_tools(body)}
    except Exception as e:
        return {'ok': False, 'error': str(e)[:500]}

@app.post('/api/mssql/test')
def mssql_test(body: dict):
    """Body fields override the saved SQL Server connection (blank body = test the
    connector's saved connection)."""
    try:
        from .mssql import test
        return test(resolve_cfg(store, {**body, 'type': 'mssql'}))
    except ImportError:
        return {'ok': False, 'error': 'pyodbc not installed - pip install taskuary[mssql]'}

@app.get('/api/agents')
def agents():
    """data = store rows (for dispatch pickers); config = the editable profiles."""
    return {'data': store.list_agents(), 'config': cfg.get('agents', {})}

@app.post('/api/agents/{name}/test')
def agent_test(name: str):
    """One tiny real run through the configured CLI ('Reply with exactly: ok') - proves
    the command exists, flags are right, and headless mode doesn't hang on approvals."""
    prof = cfg.get('agents', {}).get(name)
    if not prof:
        a = store.get_agent(name)
        prof = json.loads(a['Config']) if a and a.get('Config') else None
    if not prof: raise HTTPException(404, 'agent not found')
    profile = {**prof, 'timeout': min(int(prof.get('timeout', 120) or 120), 180)}
    try:
        out, sid, _ = hub_agents.run_cli(profile, 'Reply with exactly: ok', lambda *a: None)
        return {'ok': True, 'result': (out or '')[:300], 'resumable': bool(sid)}
    except FileNotFoundError:
        return {'ok': False, 'error': f"command not found: {profile.get('cmd')} - is the CLI installed and on PATH?"}
    except Exception as e:
        return {'ok': False, 'error': str(e)[:400]}

@app.put('/api/agents/{name}')
def put_agent(name: str, body: dict):
    if not body.get('cmd'): raise HTTPException(422, 'cmd is required')
    cfg.setdefault('agents', {})[name] = body
    config.save(cfg)
    store.upsert_agent(name, body.get('kind', 'coding'), 'cli', json.dumps(body))
    store.audit('agent', 0, 'save', ACTOR, detail=name)
    return {'ok': True}

@app.delete('/api/agents/{name}')
def delete_agent(name: str):
    if name not in cfg.get('agents', {}): raise HTTPException(404, 'agent not found')
    cfg['agents'].pop(name)
    config.save(cfg)
    store.delete_agent(name)
    store.audit('agent', 0, 'delete', ACTOR, detail=name)
    return {'ok': True}

@app.get('/api/doc/{name}')
def get_doc(name: str): return {'name': name, 'content': store.get_doc(name) or ''}

@app.put('/api/doc/{name}')
def put_doc(name: str, body: DocBody):
    store.save_doc(name, body.content, ACTOR)
    return {'ok': True}

@app.get('/api/policies')
def policies(): return {'data': store.list_policies(active_only=False)}

@app.post('/api/policies')
def save_policy(body: PolicyBody):
    fields = {k: (int(v) if k == 'Active' else v) for k, v in body.dict().items() if v is not None}
    if not fields.get('PolicyId') and not all(fields.get(k) for k in ('Name', 'Kind', 'Action', 'Reason')):
        raise HTTPException(422, 'new policies need Name, Kind, Action, Reason')
    pid = store.save_policy(fields, ACTOR)
    store.audit('policy', pid, 'edit' if body.PolicyId else 'create', ACTOR, detail=fields)
    # a skip rule also reaches BACKWARDS: the sender's existing rows leave the timeline
    # (and come back if you switch the rule off) - see policy.apply_retroactively
    saved = next((p for p in store.list_policies(active_only=False) if p['PolicyId'] == pid), None)
    hidden = policy_engine.apply_retroactively(store, saved or {})
    if hidden: store.audit('policy', pid, 'apply_history', ACTOR, detail={'messages': hidden, 'active': bool(saved.get('Active'))})
    return {'ok': True, 'policyId': pid, 'affected': hidden}

@app.get('/api/memory')
def memory(): return {'data': store.list_memories(active_only=False)}

@app.post('/api/memory')
def add_memory(body: MemoryBody):
    if body.scope not in ('global', 'sender', 'sender_domain', 'source'): raise HTTPException(422, 'bad scope')
    if not body.note.strip(): raise HTTPException(422, 'note is required')
    mid = store.add_memory({'Scope': body.scope, 'ScopeKey': body.scope_key, 'Note': body.note.strip()[:1000],
                            'Source': 'manual', 'Active': 1, 'CreatedBy': ACTOR})
    store.audit('memory', mid, 'create', ACTOR)
    return {'ok': True, 'memoryId': mid}

@app.patch('/api/memory/{mid}')
def toggle_memory(mid: int, body: MemoryToggle):
    store.set_memory_active(mid, body.active)
    store.audit('memory', mid, 'activate' if body.active else 'deactivate', ACTOR)
    return {'ok': True}

@app.get('/api/audit/recent')
def audit_recent(limit: int = 100): return {'data': store.list_audit(limit=min(limit, 500))}

def _poll_reports():
    store.set_setting('ingest_status', json.dumps({'state': 'running'}), 'system')
    try:
        run_due_reports(store)
        from .channels import poll_channels
        poll_channels(store)
    finally:
        store.set_setting('ingest_status', json.dumps({'state': 'idle'}), 'system')

@app.post('/api/ingest/poll')
def ingest_poll(background: BackgroundTasks):
    background.add_task(_poll_reports)
    return {'report': 'running'}

@app.get('/api/ingest/status')
def ingest_status():
    try: return {'status': json.loads(store.get_settings().get('ingest_status') or '{"state": "idle"}')}
    except ValueError: return {'status': {'state': 'idle'}}

# ── interactive terminals (real pty + websocket; the headless runs live on /api/runs) ──
class TermBody(BaseModel):
    agent: str | None = None; task_id: int | None = None; repo: str | None = None
    cwd: str | None = None; rows: int = 32; cols: int = 110; seed: bool = False

@app.get('/api/terminals')
def terminals(): return {'data': hub_term.listing()}

@app.post('/api/terminals')
def open_terminal(body: TermBody):
    """Spawn an agent CLI (or a plain shell) under a real pty. seed=true types the task's
    context in as the first line, so the agent starts on it and you keep talking."""
    try:
        t = hub_term.open_session(store, body.agent, body.task_id, body.repo, body.cwd, body.rows, body.cols, ACTOR)
    except (ValueError, RuntimeError) as e:
        raise HTTPException(422, str(e))
    # seeding only makes sense for an agent CLI - a bare shell would just try to RUN the text
    if body.seed and body.agent and body.task_id and store.get_task(body.task_id):
        tk = store.get_task(body.task_id)
        seed = (f"Work Taskuary task {task_ref(body.task_id)}: {tk.get('Title')}. "
                f"{(tk.get('Summary') or '')[:600]}").replace('\n', ' ')
        threading.Timer(1.5, lambda: t.write(seed + '\r')).start()      # let the TUI paint first
        store.add_comment(body.task_id, ACTOR, 'human', f'Opened an interactive {t.label} terminal in {t.cwd}')
    return t.info()

@app.delete('/api/terminals/{sid}')
def close_terminal(sid: str):
    if not hub_term.close(sid): raise HTTPException(404, 'terminal not found')
    return {'ok': True}

@app.websocket('/api/terminals/{sid}/ws')
async def terminal_ws(ws: WebSocket, sid: str):
    """Bytes out, keystrokes in. The HTTP token gate can't see websockets, so a configured
    token rides on the query string."""
    tok = cfg['server'].get('token')
    t = hub_term.get(sid)
    if tok and ws.query_params.get('token') != tok: return await ws.close(code=4401)
    if not t: return await ws.close(code=4404)
    await ws.accept()
    q = asyncio.Queue()
    t.subscribe(asyncio.get_running_loop(), q)
    async def to_browser():
        while True:
            data = await q.get()
            if data is None: return await ws.send_json({'type': 'exit'})
            await ws.send_json({'type': 'out', 'data': data})
    pump = asyncio.create_task(to_browser())
    try:
        if t.scrollback(): await ws.send_json({'type': 'out', 'data': t.scrollback()})
        while True:
            m = await ws.receive_json()
            if m.get('type') == 'in': t.write(m.get('data') or '')
            elif m.get('type') == 'resize': t.resize(m.get('rows') or 32, m.get('cols') or 110)
    except (WebSocketDisconnect, RuntimeError, ValueError):
        pass
    finally:
        t.unsubscribe(q); pump.cancel()

@app.get('/api/settings')
def settings():
    return {'data': [s for s in store.list_settings() if s['Name'] != 'ingest_status']}

@app.patch('/api/settings')
def set_setting(body: SettingBody):
    store.set_setting(body.name, body.value, ACTOR)
    return {'ok': True}

@app.get('/api/audit/verify')
def verify(): return store.verify_audit_chain()
