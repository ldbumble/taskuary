"""The local HTTP API + built-in minimal web UI. Localhost-only by default; set
[server].token in config to require an X-Taskuary-Token header (for LAN/self-hosting).
"""
import json
from datetime import datetime
from pathlib import Path
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from . import config
from .store import SQLiteStore, task_ref
from .ingest import ingest_message
from .reports import PLANNED, REGISTRY, render_report, resolve_cfg, run_due_reports, run_report_source
from . import agents as hub_agents
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


class TaskBody(BaseModel):
    Title: str = None; Summary: str = None; Kind: str = None; Priority: str = None
    Status: str = None; Tags: str = None
class MsgBody(BaseModel):
    external_id: str = None; channel: str = 'api'; subject: str = None; body: str = None
    from_name: str = None; from_email: str = None; conversation_id: str = None
    sent_at: str = None; source_link: str = None; source_name: str = None
class TextBody(BaseModel): body: str
class DecideBody(BaseModel): verb: str; final_text: str = None; note: str = None
class CodeBody(BaseModel): repo: str = None
class DocBody(BaseModel): content: str
class SettingBody(BaseModel): name: str; value: str
class SourceBody(BaseModel):
    SourceId: int = None; Channel: str = None; Address: str = None; ConfigJson: str = None; Active: bool = None
class DispatchBody(BaseModel): agent: str = 'coder'; instruction: str = None
class PolicyBody(BaseModel):
    PolicyId: int = None; Name: str = None; Kind: str = None; Pattern: str = None
    Action: str = None; Reason: str = None; SortOrder: int = None; Active: bool = None
class MemoryBody(BaseModel): note: str; scope: str = 'global'; scope_key: str = None
class MemoryToggle(BaseModel): active: bool
class ConnectorBody(BaseModel):
    ConnectorId: int = None; Type: str = None; Name: str = None
    ConfigJson: str = None; Secret: str = None; Active: bool = None


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


@app.get('/api/feed')
def feed(limit: int = 100, offset: int = 0, pending_only: bool = False, channel: str = None):
    days = int(store.get_settings().get('feed_days', 14))
    return {'data': store.feed(min(limit, 500), days, pending_only, channel, max(offset, 0))}


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
    """[github] from config.toml, with the GitHub connector's PAT winning when saved."""
    g = dict(cfg.get('github') or {})
    c = store.get_connector_by_type('github', with_secret=True)
    if c and c.get('Secret'): g['token'] = c['Secret']
    return g

@app.post('/api/tasks/{task_id}/code')
def code(task_id: int, background: BackgroundTasks, body: CodeBody = None):
    if not store.get_task(task_id): raise HTTPException(404, 'task not found')
    background.add_task(run_coding_task, store, task_id, ACTOR, (body.repo if body else None), _github_cfg())
    return {'coder': 'running'}

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
def sources(): return {'data': store.list_sources(active_only=False)}

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

@app.post('/api/connectors')
def save_connector(body: ConnectorBody):
    fields = {k: (int(v) if k == 'Active' else v) for k, v in body.dict().items() if v is not None}
    if not fields.get('ConnectorId') and not (fields.get('Type') and fields.get('Name')):
        raise HTTPException(422, 'new connectors need Type and Name')
    cid = store.save_connector(fields, ACTOR)
    safe = {k: v for k, v in fields.items() if k != 'Secret'} | ({'secret': 'updated'} if 'Secret' in fields else {})
    store.audit('connector', cid, 'edit' if body.ConnectorId else 'create', ACTOR, detail=safe)
    discovery = None
    # a new GitHub PAT is all the config there is: saving the token IS connecting
    if 'Secret' in fields and (store.get_connector(cid) or {}).get('Type') == 'github':
        try:
            from .channels import github_discover
            discovery = github_discover(store, store.get_connector(cid, with_secret=True), ACTOR)
        except Exception as e:
            discovery = {'error': str(e)[:300]}
    from .docsync import sync_connections
    sync_connections(store, ACTOR)
    return {'ok': True, 'connectorId': cid, 'discovery': discovery}

@app.post('/api/connectors/{cid}/test')
def connector_test(cid: int):
    from .channels import test_connector
    if not store.get_connector(cid): raise HTTPException(404, 'connector not found')
    out = test_connector(store, cid)
    store.audit('connector', cid, 'test_ok' if out['ok'] else 'test_failed', ACTOR, detail=out['detail'])
    return out

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
    return {'ok': True, 'policyId': pid}

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

@app.get('/api/settings')
def settings():
    return {'data': [s for s in store.list_settings() if s['Name'] != 'ingest_status']}

@app.patch('/api/settings')
def set_setting(body: SettingBody):
    store.set_setting(body.name, body.value, ACTOR)
    return {'ok': True}

@app.get('/api/audit/verify')
def verify(): return store.verify_audit_chain()
