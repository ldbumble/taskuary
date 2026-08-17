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
from .reports import PLANNED, REGISTRY, run_due_reports, run_report_source
from . import agents as hub_agents
from .coder import run_coding_task
from .converse import message_agent

cfg = config.load()
store = SQLiteStore(config.db_path())
for name, prof in cfg.get('agents', {}).items():
    store.upsert_agent(name, prof.get('kind', 'coding'), 'cli', json.dumps(prof))
app = FastAPI(title='Taskuary', docs_url='/api/docs')
ACTOR = 'owner'


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


@app.get('/', response_class=HTMLResponse)
def index():
    return (Path(__file__).parent / 'web' / 'index.html').read_text(encoding='utf-8')


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

@app.post('/api/tasks/{task_id}/code')
def code(task_id: int, background: BackgroundTasks, body: CodeBody = None):
    if not store.get_task(task_id): raise HTTPException(404, 'task not found')
    background.add_task(run_coding_task, store, task_id, ACTOR, (body.repo if body else None), cfg.get('github'))
    return {'coder': 'running'}

@app.post('/api/tasks/{task_id}/comments')
def comment(task_id: int, body: TextBody):
    store.add_comment(task_id, ACTOR, 'human', body.body)
    return {'ok': True}

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
    if body.verb == 'no_reply' and rv.get('TaskId'): store.update_task(rv['TaskId'], {'Status': 'done'}, ACTOR)
    return {'ok': True, 'status': verb2status[body.verb]}

@app.post('/api/ingest/push')
def push(body: MsgBody):
    m = body.dict()
    m['external_id'] = m.get('external_id') or f'api:{datetime.now().isoformat()}'
    m['sent_at'] = m.get('sent_at') or datetime.now().isoformat(sep=' ', timespec='seconds')
    out = ingest_message(store, m)
    return {**out, 'ref': task_ref(out['task_id']) if out.get('task_id') else None}

@app.post('/api/reports/run')
def reports_run(): return {'ran': run_due_reports(store)}

@app.get('/api/sources')
def sources(): return {'data': store.list_sources(active_only=False)}

@app.post('/api/sources')
def save_source(body: SourceBody):
    fields = {k: (int(v) if k == 'Active' else v) for k, v in body.dict().items() if v is not None}
    fields.setdefault('Owner', ACTOR)
    return {'sourceId': store.save_source(fields, ACTOR)}

@app.delete('/api/sources/{sid}')
def delete_source(sid: int):
    if not store.get_source(sid): raise HTTPException(404, 'source not found')
    store.delete_source(sid)
    store.audit('source', sid, 'delete', ACTOR)
    return {'ok': True}

@app.post('/api/sources/{sid}/run')
def run_source_now(sid: int):
    src = store.get_source(sid)
    if not src: raise HTTPException(404, 'source not found')
    out = run_report_source(store, src)
    store.touch_source(sid)
    return out

@app.get('/api/connectors')
def connectors():
    return {'data': [{'type': t, 'status': 'planned' if t in PLANNED else 'builtin'} for t in REGISTRY]}

@app.post('/api/reports/preview')
def report_preview(body: dict):
    """Dry-run a connector config: returns the headline/summary without filing a row."""
    try:
        head, summary = REGISTRY[body.get('type', 'rest')](body)
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
    try:
        from .mssql import test
        return test(body)
    except ImportError:
        return {'ok': False, 'error': 'pyodbc not installed - pip install taskuary[mssql]'}

@app.get('/api/agents')
def agents(): return {'data': cfg.get('agents', {})}

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

@app.get('/api/settings')
def settings(): return {'data': store.list_settings()}

@app.patch('/api/settings')
def set_setting(body: SettingBody):
    store.set_setting(body.name, body.value, ACTOR)
    return {'ok': True}

@app.get('/api/audit/verify')
def verify(): return store.verify_audit_chain()
