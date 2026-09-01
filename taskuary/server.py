"""The local HTTP API + built-in minimal web UI. Localhost-only by default; set
[server].token in config to require an X-Taskuary-Token header (for LAN/self-hosting).
"""
import asyncio, json, re, secrets, threading, time
import requests
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse, Response, StreamingResponse
from pydantic import BaseModel

from . import config
from . import store as store_mod
from .store import SQLiteStore, task_ref
from .ingest import ingest_message, split_message, task_from_message
from .reports import PLANNED, REGISTRY, render_report, resolve_cfg, run_due_reports, run_report_source
from . import agents as hub_agents
from . import blackboard
from . import guard
from . import policy as policy_engine
from . import reshape
from . import terminal as hub_term
from .coder import PAUSE_MARKER, pause_note, reply_target as coder_reply_target, wrap as coder_wrap
from . import aisetup, assistant, demo, learn, learnedgraph, outbound, rank, responder, waitroom

cfg = config.load()
store = SQLiteStore(config.db_path())
for name, prof in cfg.get('agents', {}).items():
    # merge, don't clobber: paths DISCOVERED at runtime (find_checkout) live on the agent row,
    # and a boot that rewrites Config from config.toml wholesale would forget them
    _old = json.loads((store.get_agent(name) or {}).get('Config') or '{}')
    prof = {**prof, 'cwd_map': {**(_old.get('cwd_map') or {}), **(prof.get('cwd_map') or {})}}
    store.upsert_agent(name, prof.get('kind', 'coding'), 'cli', json.dumps(prof))
@asynccontextmanager
async def _lifespan(_app):
    # the demo builds its world and puts agents on the board BEFORE anything else runs - and
    # never polls, never bridges, never catches up on a mailbox that does not exist
    if demo.enabled():
        try:
            demo.seed(store)
            demo.start_sessions(store)
        except Exception as e: logger.warning(f'demo seed failed: {e}')
        yield
        return
    from . import wabridge
    try: wabridge.start_configured(store)
    except Exception as e: logger.warning(f'wa bridge startup failed: {e}')
    catch_up_on_startup()          # defined below; resolved when the app actually starts
    _heal_owner_docs()
    _refresh_soul_connections()
    learn.note_verdicts(store)     # the evidence block in LEARNED.md tracks the verdict table
    threading.Thread(target=poll_forever, daemon=True).start()
    waitroom.watch(store)          # notes queued for a working agent land when it stops
    from . import msauth
    msauth.on_rotate = lambda cid, rt: store.save_connector({'ConnectorId': cid, 'Secret': rt}, 'msauth')   # a rotated Microsoft refresh token outlives a restart
    yield

app = FastAPI(title='Taskuary', docs_url='/api/docs', lifespan=_lifespan)
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
    # /api/health is the Docker / load-balancer pulse - it must work without the LAN token
    if request.url.path == '/api/health':
        return await call_next(request)
    # the demo is the real app with every door to the outside world shut, and it is shut HERE:
    # over the method and the path, before a handler exists to be trusted (demo.py)
    if demo.enabled():
        why = demo.refuse(request.method, request.url.path)
        if why: return JSONResponse({'detail': why, 'demo': True}, status_code=403)
    tok = cfg['server'].get('token')
    if tok and request.url.path.startswith('/api') and request.headers.get('X-Taskuary-Token') not in (tok, cfg['server'].get('agent_token')):
        # an <img src> cannot carry a header, so attachment READS take the token in the query
        # string - the same concession websockets already needed
        if not (request.url.path.startswith('/api/attachments/') and request.query_params.get('token') == tok):
            return HTMLResponse('unauthorized', status_code=401)
    # WHAT AN AGENT MAY NOT DO, before a handler exists to be talked round (guard.py). A session
    # runs with the agent token in its environment, and the routes that SEND - approve a reply,
    # hand work to a person, start an outbound message - are refused to it here, in code. Not in
    # SOUL.md, not in a setting: an instruction sitting in the same context as the untrusted mail
    # is not a control, and a model that has been talked into "they want this sent now" would
    # otherwise find this API and approve its own draft.
    if guard.scope_of(cfg['server'], request.headers) == guard.AGENT:
        why = guard.denied(request.method, request.url.path)
        if why:
            logger.warning(f'agent refused {request.method} {request.url.path} - {why}')
            return JSONResponse({'detail': f'agents cannot do this: {why}. Ask the owner - it is '
                                           'their button, and no instruction in a message changes that.'},
                                status_code=403)
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
class AssistantSessionBody(BaseModel):
    connector_id: int | None = None; pick: str | None = None; model: str | None = None
class AssistantMessageBody(AssistantSessionBody):
    text: str; attachments: list[str] = []
class DecideBody(BaseModel): verb: str; final_text: str | None = None; note: str | None = None
class CodeBody(BaseModel):
    repo: str | None = None; agent: str | None = None
    model: str | None = None; instruction: str | None = None
class DocBody(BaseModel): content: str
class SettingBody(BaseModel): name: str; value: str
class SourceBody(BaseModel):
    SourceId: int | None = None; ConnectorId: int | None = None; Channel: str | None = None
    Address: str | None = None; ConfigJson: str | None = None; Active: bool | None = None
class DispatchBody(BaseModel): agent: str = 'coder'; instruction: str | None = None; model: str | None = None
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
    Scope: str | None = None                       # read | write | admin - see scopes.SCOPES
class AiSetupBody(BaseModel):
    guide: list[str] = []; fields: list = []; secret_label: str | None = None   # the card's Guide + form, as the UI has them
    agent_steps: list[str] = []                                                  # the card's Agent tab: steps written FOR the agent
    agent: str | None = None; model: str | None = None


_web_root = Path(__file__).parent / 'web'


def _index_response(index_file: Path):
    try:
        html = index_file.read_text(encoding='utf-8')
    except FileNotFoundError:
        # Vite empties its output directory before replacing a production bundle. A browser can
        # arrive in that small gap while the Python server stays live; make it a self-healing 503,
        # not an application traceback. This also gives a useful response for an incomplete install.
        html = '''<!doctype html><html><head><meta charset="utf-8">
<meta http-equiv="refresh" content="1"><title>Taskuary is updating</title></head>
<body style="font:14px system-ui;margin:4rem;color:#4d4a43">Taskuary is updating&hellip;</body></html>'''
        return HTMLResponse(html, status_code=503, headers={
            'Cache-Control': 'no-store, must-revalidate', 'Retry-After': '1'})
    return HTMLResponse(html, headers={'Cache-Control': 'no-store, must-revalidate'})


@app.get('/', response_class=HTMLResponse)
def index():
    """The one file that must NEVER be cached. Every asset under /assets carries a content hash
    in its name, so those can be held forever - but index.html is what NAMES them, and a cached
    copy points a fresh install at a bundle that is no longer there (or worse, one that is). An
    old index.html is how a fixed crash keeps crashing: the fix shipped, the browser kept asking
    for yesterday's JS, and the stack trace named a file the repo had already replaced."""
    return _index_response(_web_root / 'index.html')

_assets = _web_root / 'assets'
from fastapi.staticfiles import StaticFiles
app.mount('/assets', StaticFiles(directory=str(_assets), check_dir=False), name='assets')

from fastapi.responses import FileResponse

@app.get('/favicon.ico', include_in_schema=False)
def favicon(): return FileResponse(Path(__file__).parent / 'web' / 'favicon.ico')

@app.get('/favicon.png', include_in_schema=False)
def favicon_png(): return FileResponse(Path(__file__).parent / 'web' / 'favicon.png')


from . import __version__ as _ver
_started = datetime.now().isoformat(sep=' ', timespec='seconds')

@app.get('/api/version')
def version(): return {'version': _ver, 'started': _started}

def _can_send(channel, has_message=True, gh_ok=None) -> bool:
    """Can an approved reply actually LEAVE on this channel? One answer for the whole app -
    outbound.can_reply - so the Approve button, triage and the coder wrap-up cannot
    disagree. The UI turns an unsendable draft's Approve into 'No response required'."""
    if not has_message: return False
    return outbound.can_reply(store, channel)


@app.get('/api/feed')
def feed(limit: int = 100, offset: int = 0, pending_only: bool = False, channel: str = None, source: str = None,
         request: Request = None):
    days = int(store.get_settings().get('feed_days', 14))
    tag = '"' + store.feed_tag(days, pending_only, channel, source) + '"'
    if request is not None and request.headers.get('if-none-match') == tag:
        return Response(status_code=304, headers={'ETag': tag, 'Cache-Control': 'no-cache'})
    rows = store.feed(min(limit, 500), days, pending_only, channel, max(offset, 0), source)
    gh_ok = store.github_replies_ok()
    for r in rows: r['CanSend'] = _can_send(r.get('Channel'), True, gh_ok)
    return JSONResponse({'data': rows}, headers={'ETag': tag, 'Cache-Control': 'no-cache'})


def _queued_info(q):
    """The card's hover text for a held-back dispatch: what it waits for, and why."""
    if not q: return None
    b = q.get('BehindTaskId')
    return {'behind': task_ref(b) if b else None, 'value': q.get('Value'), 'why': q.get('Why'),
            'behindTitle': (store.get_task(b) or {}).get('Title') if b else None,
            'reason': q.get('Reason'), 'since': q.get('CreatedAt')}

@app.get('/api/tasks')
def tasks(status: str = None, active: bool = False):
    """An interactive session IS an agent working - the UI has to see it, or a task with a
    live CLI on it reads as 'queued' while the agent sits there asking a question."""
    qs = {q['TaskId']: q for q in store.queued_dispatches()}
    wc = store.waiting_counts()
    agented = store.agented_task_ids()      # the Board's Done lane shows agent work only
    return {'data': [{**t, 'ref': task_ref(t['TaskId']), 'Session': hub_term.for_task(t['TaskId']),
                      'Queued': _queued_info(qs.get(t['TaskId'])), 'Waiting': wc.get(t['TaskId'], 0),
                      'HadAgent': t['TaskId'] in agented}
                     for t in store.list_tasks(status, active_only=active)]}

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
    # a session that has ended still leaves work to close out, so the page has to know one
    # happened - the Done and Pause buttons used to vanish with the pty
    tr = store.last_transcript(task_id)
    return {**d, 'session': hub_term.for_task(task_id, tail=3),
            'transcript': {'agent': tr['Agent'], 'at': tr['CreatedAt'], 'chars': len(tr['Text'] or '')} if tr else None}

def _assistant_payload(task_id: int, session=None):
    from . import general
    task = store.get_task(task_id)
    if not task: raise HTTPException(404, 'task not found')
    if not general.handles(task):
        raise HTTPException(422, 'assistant view is available for general, research, marketing, and triage tasks')
    session = session or general.session_for(task_id)
    return {'messages': general.history(store, task_id), 'providers': general.provider_options(store),
            'session': session.info(tail=3) if session else None}

@app.get('/api/tasks/{task_id}/assistant')
def assistant_state(task_id: int):
    return _assistant_payload(task_id)

@app.post('/api/tasks/{task_id}/assistant/session')
def assistant_session(task_id: int, body: AssistantSessionBody = None):
    from . import general
    body = body or AssistantSessionBody()
    try: session = general.start_session(store, task_id, body.connector_id, body.model, ACTOR, body.pick)
    except (ValueError, RuntimeError) as e: raise HTTPException(422, str(e))
    return _assistant_payload(task_id, session)

@app.post('/api/tasks/{task_id}/assistant/messages')
def assistant_message(task_id: int, body: AssistantMessageBody):
    from . import general
    try:
        session = general.start_session(store, task_id, body.connector_id, body.model, ACTOR, body.pick)
        reply = session.send_prompt(body.text, body.attachments, body.connector_id, body.model, pick=body.pick)
    except (ValueError, RuntimeError) as e: raise HTTPException(422, str(e))
    return {'reply': reply, **_assistant_payload(task_id, session)}

@app.post('/api/tasks/{task_id}/assistant/cancel')
def assistant_cancel(task_id: int):
    """The stop button. The ONLY thing that stops an answer being written - walking away does
    not (see the stream's docstring)."""
    from . import general
    session = general.session_for(task_id)
    return {'stopped': bool(session and session.stop())}

@app.post('/api/tasks/{task_id}/assistant/report')
def assistant_create_report(task_id: int, body: AssistantSessionBody = None):
    """One click: summarize the discussion and create a native daily agent report.

    The existing Reports editor owns every adjustment after that (prompt, model, cadence,
    enable/disable). Long instructions become provider-neutral Taskuary skills automatically.
    """
    from . import general
    body = body or AssistantSessionBody()
    task = store.get_task(task_id)
    if not task: raise HTTPException(404, 'task not found')
    if not general.handles(task): raise HTTPException(422, 'only assistant discussions can become reports here')
    # Repeated clicks reopen the same report instead of quietly creating duplicates.
    for source in store.list_sources(active_only=False):
        if source.get('Channel') != 'report': continue
        try: old = json.loads(source.get('ConfigJson') or '{}')
        except ValueError: continue
        if old.get('origin_task_id') == task_id:
            return {'sourceId': source['SourceId'], 'title': old.get('title') or source.get('Address'),
                    'config': old, 'created': False, 'mode': 'skill' if old.get('skill') else 'prompt'}
    try: draft = general.report_draft(store, task_id, body.pick, body.model)
    except (ValueError, RuntimeError) as e: raise HTTPException(422, str(e))
    options = [p for p in general.provider_options(store) if p.get('type') == 'cli']
    chosen = next((p for p in options if p.get('pick') == body.pick), None) or (options[0] if options else None)
    if not chosen: raise HTTPException(422, 'a recurring report needs a configured CLI agent')
    agent = str(chosen['pick']).split(':', 1)[1]
    title, prompt = draft['title'].strip()[:160], draft['prompt'].strip()[:12000]
    report_cfg = {'type': 'agent', 'title': title, 'agent': agent, 'daily_at': '08:00',
                  'origin_task_id': task_id, 'origin_task_ref': task_ref(task_id)}
    chosen_model = body.model if chosen.get('pick') == body.pick else chosen.get('model')
    if chosen_model: report_cfg['model'] = str(chosen_model).strip()
    if len(prompt) > general.REPORT_SKILL_CHARS:
        report_cfg['skill'] = general.save_report_skill(task_id, title, prompt)
        report_cfg['prompt'] = 'Run this workflow with current information and produce today\'s report.'
        mode = 'skill'
    else:
        report_cfg['prompt'] = prompt
        mode = 'prompt'
    sid = store.save_source({'Channel': 'report', 'Address': report_cfg['title'], 'Owner': ACTOR,
                             'Active': 1, 'ConfigJson': json.dumps(report_cfg)}, ACTOR)
    store.audit('source', sid, 'created_from_assistant', ACTOR,
                detail={'task_id': task_id, 'agent': agent, 'schedule': {k: report_cfg[k] for k in ('daily_at', 'every_minutes', 'cron') if k in report_cfg}})
    store.add_comment(task_id, ACTOR, 'human',
                      f'Created daily recurring report "{report_cfg["title"]}" from this discussion ({mode}; report source {sid}).')
    return {'sourceId': sid, 'title': report_cfg['title'], 'config': report_cfg, 'created': True, 'mode': mode}

@app.post('/api/tasks/{task_id}/assistant/stream')
async def assistant_stream(task_id: int, body: AssistantMessageBody):
    """NDJSON work stream for assistant-ui: the configured CLI's real tool/text events.

    The CLI stays on a worker thread (its subprocess pipes are blocking); events cross onto the
    request loop through a queue.

    Closing the browser stream DETACHES; it does not kill. It used to: leaving the Board tab,
    pressing refresh, or any remount of the pane ended the response - and since the reply is
    only filed once the run finishes, an answer that was seconds away was lost and the chat
    looked as though it had ignored the question. Stopping is now an explicit act
    (/assistant/cancel, the stop button), and a run nobody is watching still finishes and still
    files its reply on the task.
    """
    from . import general
    loop, events, cancel = asyncio.get_running_loop(), asyncio.Queue(), threading.Event()

    def put(event):
        # the reader is gone: drop the event and keep working. The answer is filed on the task
        # either way, which is what the chat reads when it comes back.
        try: loop.call_soon_threadsafe(events.put_nowait, event)
        except RuntimeError: pass

    def trace(kind, name, detail):
        put({'type': kind, 'name': name, 'detail': detail})

    def work():
        try:
            session = general.start_session(store, task_id, body.connector_id, body.model, ACTOR, body.pick)
            put({'type': 'start', 'session': session.info()})
            try:
                reply = session.send_prompt(body.text, body.attachments, body.connector_id, body.model,
                                            pick=body.pick, trace=trace, cancel=cancel)
            except RuntimeError as e:
                # it ended between being handed over and being spoken to (the owner closed the
                # pane, a wrap-up ran). A question is not lost over a race: start a fresh one
                # and ask it there, once.
                if 'has ended' not in str(e) or cancel.is_set(): raise
                general.drop_session(task_id)
                session = general.start_session(store, task_id, body.connector_id, body.model, ACTOR, body.pick)
                reply = session.send_prompt(body.text, body.attachments, body.connector_id, body.model,
                                            pick=body.pick, trace=trace, cancel=cancel)
            put({'type': 'done', 'reply': reply, 'payload': _assistant_payload(task_id, session)})
        # Once headers are streaming, FastAPI cannot replace this with its normal JSON error
        # response. Always terminate the NDJSON stream explicitly instead of leaving the UI's
        # spinner alive forever (missing CLI, provider/network errors, and bugs all land here).
        except Exception as e:
            # the browser shows this under the question now; the log is for the run nobody was
            # watching, and for the owner who can only report that nothing happened
            logger.warning(f'assistant stream for task {task_id} failed: {e}')
            put({'type': 'error', 'error': str(e)})

    threading.Thread(target=work, daemon=True).start()

    async def generate():
        try:
            while True:
                event = await events.get()
                yield json.dumps(event, default=str) + '\n'
                if event.get('type') in ('done', 'error'): break
        finally:
            # NOT cancel.set(): see the docstring. A browser that walked away is not a stop.
            if not cancel.is_set(): logger.debug(f'assistant stream for task {task_id} detached; the run continues')

    return StreamingResponse(generate(), media_type='application/x-ndjson',
                             headers={'Cache-Control': 'no-cache, no-transform'})

@app.patch('/api/tasks/{task_id}')
def update_task(task_id: int, body: TaskBody, background: BackgroundTasks = None):
    t = store.get_task(task_id)
    if not t: raise HTTPException(404, 'task not found')
    fields = {k: v for k, v in body.dict().items() if v is not None}
    store.update_task(task_id, fields, ACTOR)
    # "Mark done - I took care of it" means the agent's job is over too: a live session left
    # running on a finished task is an agent nobody is coming back for. close() files the
    # transcript first, so the record survives the pty as always.
    if fields.get('Status') in ('done', 'dropped'):
        live = hub_term.session_for(task_id)
        if live and live.alive:
            hub_term.close(live.sid)
            store.add_comment(task_id, ACTOR, 'human', 'Task closed - ended the live agent session with it.')
    # "This is not a coding task - it just needs an answer." Changing the kind to reply IS that
    # verdict, so the task enters the Review queue the way a question would have at triage:
    # a draft review appears (auto-drafted when that is on), instead of a repo session.
    if fields.get('Kind') == 'reply' and t.get('Kind') != 'reply':
        mid = coder_reply_target(store, task_id)
        if mid and not store.pending_review(task_id):
            rid = store.add_review({'TaskId': task_id, 'MessageId': mid, 'Kind': 'draft', 'Status': 'pending',
                                    'Reason': 'reclassified by you: a question, not work to do - needs a reply'})
            store.add_comment(task_id, ACTOR, 'human', 'Reclassified as a question - it needs an answer, not an agent.')
            if store.get_settings().get('auto_draft_enabled') == '1' and background is not None:
                # guarded like ingest's auto-draft: no AI connected means an undrafted review
                # waiting in the queue, never an exception out of a background task
                def _draft(tid=task_id, r=rid):
                    try: responder.write_draft(store, tid, r, actor='auto-draft')
                    except Exception as e: logger.warning(f'auto-draft failed for task {tid}: {e}')
                background.add_task(_draft)
        # a reclassification is a triage verdict the owner had to overturn - worth generalizing
        if background is not None:
            background.add_task(learn.learn_from, store,
                                f"{task_ref(task_id)}: owner reclassified \"{(t.get('Title') or '')[:80]}\" from a "
                                'coding task to a question needing only a reply - triage over-reached')
    return {'ok': True}

@app.post('/api/tasks/{task_id}/code')
def code(task_id: int, background: BackgroundTasks, body: CodeBody = None):
    """Put the CLI on this task - in a REAL session, like every other way of starting one. This
    used to be the headless path (pipes, no window, a report you read afterwards); nothing starts
    where you cannot watch it, interrupt it or answer it, so it is now the same as /dispatch."""
    if not store.get_task(task_id): raise HTTPException(404, 'task not found')
    agent = (body.agent if body else None) or 'coder'
    if not store.get_agent(agent): raise HTTPException(422, f'unknown agent: {agent}')
    ses = start_session(store, task_id, agent, (body.model if body else None), (body.instruction if body else None))
    return {'coder': 'session', 'agent': agent, 'model': (body.model if body else None), 'session': ses}

@app.post('/api/tasks/{task_id}/comments')
def comment(task_id: int, body: TextBody):
    store.add_comment(task_id, ACTOR, 'human', body.body)
    return {'ok': True}

@app.post('/api/tasks/{task_id}/dispatch')
def dispatch_task(task_id: int, body: DispatchBody, background: BackgroundTasks):
    if not store.get_task(task_id): raise HTTPException(404, 'task not found')
    ses = start_session(store, task_id, body.agent, body.model, body.instruction)
    return {'dispatch': 'session', 'agent': body.agent, 'model': body.model, 'session': ses}

class RepoBody(BaseModel):
    repo: str | None = None          # None clears the tag and lets Taskuary guess again
    path: str | None = None          # set the agent's local path for it, if it has none
    agent: str = 'coder'
    restart: bool = False            # close the session that is in the wrong tree and reopen here

def _repo_rows(task_id: int, agent: str = 'coder'):
    """Every repo Taskuary knows, ranked for this task, with whether the agent can open it. A repo
    in SOUL.md with no local path is listed and flagged, not hidden - "we know what it is but not
    where it is" is the thing the owner has to fix, and it cannot be fixed invisibly."""
    row = store.get_agent(agent) or {}
    prof = json.loads(row.get('Config') or '{}')
    paths, desc = (prof.get('cwd_map') or {}), hub_term.repo_map(store)
    tagged = (re.search(r'repo:([^\s,]+)', str((store.get_task(task_id) or {}).get('Tags') or '')) or [None, None])[1]
    return [{'repo': r, 'score': sc, 'what': desc.get(r, ''), 'path': paths.get(r),
             'has_path': has, 'tagged': r == tagged,
             # a pathless repo is searched for on the spot, so the picker can offer the answer
             'found': None if has else hub_term.find_checkout(r, prof, seconds=1.5)}
            for r, sc, has in hub_term.rank_repos(store, task_id, prof)]

@app.get('/api/tasks/{task_id}/repos')
def task_repos(task_id: int, agent: str = 'coder'):
    if not store.get_task(task_id): raise HTTPException(404, 'task not found')
    picked, why = hub_term.guess_repo(store, task_id, json.loads((store.get_agent(agent) or {}).get('Config') or '{}'))
    return {'data': _repo_rows(task_id, agent), 'picked': picked, 'why': why}

@app.put('/api/tasks/{task_id}/repo')
def set_task_repo(task_id: int, body: RepoBody):
    """Put this task in the right checkout. The `repo:` tag is the override that always wins over
    the guess, so this is also how you correct one - and because a running session is already in
    the wrong tree, `restart` closes it and opens a fresh one whose prompt names the new repo."""
    t = store.get_task(task_id)
    if not t: raise HTTPException(404, 'task not found')
    tags = [x for x in re.split(r'[\s,]+', str(t.get('Tags') or '')) if x and not x.startswith('repo:')]
    if body.repo: tags.append(f'repo:{body.repo}')
    store.update_task(task_id, {'Tags': ' '.join(tags)}, ACTOR)
    # a repo Taskuary knows about but has no path for cannot be opened - take the path here
    if body.repo and body.path:
        row = store.get_agent(body.agent)
        if not row: raise HTTPException(422, f'unknown agent: {body.agent}')
        if not Path(body.path).is_dir(): raise HTTPException(422, f'not a directory: {body.path}')
        prof = json.loads(row.get('Config') or '{}')
        prof.setdefault('cwd_map', {})[body.repo] = body.path
        cfg.setdefault('agents', {})[body.agent] = prof
        config.save(cfg)
        store.upsert_agent(body.agent, row.get('Kind') or 'coding', 'cli', json.dumps(prof))
    store.add_comment(task_id, ACTOR, 'human',
                      'Marked general - no repository. The session opens in the agent\'s own folder '
                      'and the prompt says there is no codebase to change.' if body.repo == hub_term.NO_REPO
                      else f'Repo set to {body.repo} - the session works there and the prompt says so.'
                      if body.repo else 'Cleared the repo - Taskuary picks it from the ask again.')
    store.audit('task', task_id, 'set_repo', ACTOR, detail={'repo': body.repo, 'path': body.path})
    out = {'ok': True, 'repo': body.repo}
    if body.restart:
        live = hub_term.session_for(task_id)
        if live: hub_term.close(live.sid)
        out['session'] = start_session(store, task_id, body.agent)
    return out

class NotATaskBody(BaseModel): learn: bool = True

def _teach_not_a_task(m: dict, background=None):
    """The NOT A TASK verdict, written the SAME way whichever door it came through - the task
    list's "Not a task" and the timeline's "Not a task - just conversation" are one judgement
    and used to teach two different things (owner, 2026-08-30).

    It writes a memory note and NOTHING else. It used to also save a sender `ignore` POLICY,
    which quietly muted that address for good - a second, wider verdict the owner never asked
    for, hidden inside a button whose label says "not a task". Silencing a sender has its own
    button and always did ("Skip this sender"), where it is undoable and says what it does.

    Keyed on the topic where there is one and on the sender otherwise. With neither - a Teams
    chat has no address, and a two-word subject has no topic - there is nothing to key a note
    to, and a note keyed to nothing is a verdict against everyone, so none is written. The
    thread is still ruled either way: that is the ignore route the callers add."""
    em, topic = (m.get('FromEmail') or '').lower(), _topic_key(m)
    if not (em or topic): return None
    mid = store.add_memory({'Scope': 'subject' if topic else 'sender', 'ScopeKey': topic or em,
                            'Source': 'verdict', 'Active': 1, 'CreatedBy': ACTOR,
                            'Note': f"{str(m.get('SentAt') or '')[:10]}: \"{(m.get('Subject') or '')[:90]}\""
                                    + (f' from {em}' if em else '') + (f' - the topic "{topic}"' if topic else '')
                                    + ' - NOT A TASK: the owner filed it, no task, no reply'})
    learn.note_verdicts(store)
    # the sender note is durable already; the GENERAL lesson (what kinds of mail are not tasks
    # for this owner) is LEARNED.md's to distill
    if background is not None:
        background.add_task(learn.learn_from, store,
                            f"mem{mid}: owner said NOT A TASK: \"{(m.get('Subject') or '')[:80]}\""
                            + (f' from {em}' if em else '') + ' should never have opened a task')
    return mid

@app.post('/api/tasks/{task_id}/not-coding')
def not_coding(task_id: int, body: NotATaskBody = None, background: BackgroundTasks = None):
    """Owner verdict: real work, but not for the coding agent. The default is the other way
    round on purpose - everything that is work goes to the agent, which says "nothing to do
    here" when there is nothing - so this button is how the exceptions get taught: the task
    stays, on the owner's list, its live session (if any) is closed, and an evidence line says
    so for the next message like it."""
    t = store.get_task(task_id)
    if not t: raise HTTPException(404, 'task not found')
    live = hub_term.session_for(task_id)
    if live and live.alive: hub_term.close(live.sid)
    store.update_task(task_id, {'Kind': 'general'}, ACTOR)
    store.clear_dispatch(task_id)
    msgs = store.list_messages(task_id)
    learned = None
    if msgs and (body is None or body.learn):
        m = msgs[0]; em = (m.get('FromEmail') or '').lower(); topic = _topic_key(m)
        mid = store.add_memory({'Scope': 'subject' if topic else 'sender' if em else 'global', 'ScopeKey': topic or em or None,
                                'Source': 'verdict', 'Active': 1, 'CreatedBy': ACTOR,
                                'Note': f"{str(m.get('SentAt') or '')[:10]}: \"{(m.get('Subject') or t.get('Title') or '')[:90]}\""
                                        + (f' from {em}' if em else '') + (f' - the topic "{topic}"' if topic else '')
                                        + ' - NOT A CODING TASK: real work, kept on the owner\'s list, no agent'})
        learned = mid
        learn.note_verdicts(store)
        if background is not None:
            background.add_task(learn.learn_from, store,
                                f"mem{mid}: owner said NOT A CODING TASK: \"{(m.get('Subject') or t.get('Title') or '')[:80]}\" - "
                                'real work, but not for the coding agent')
    store.add_comment(task_id, ACTOR, 'human', 'Not a coding task - kept on your list; the agent is off it.')
    store.audit('task', task_id, 'not_coding', ACTOR, detail={'memory_id': learned})
    return {'ok': True, 'kind': 'general', 'memoryId': learned}

@app.post('/api/tasks/{task_id}/not-a-task')
def not_a_task(task_id: int, body: NotATaskBody = None, background: BackgroundTasks = None):
    """Owner verdict: never needed to be a task. Writes the verdict to memory (_teach_not_a_task
    - a note, never a policy: muting a sender is "Skip this sender", not a side effect of this),
    then deletes the task - its messages stay in the feed as 'filed'.

    learn=false is the lighter verdict: THIS one is just chatter (someone answered "yes"), with
    nothing to conclude - delete the task and teach nothing."""
    if not store.get_task(task_id): raise HTTPException(404, 'task not found')
    msgs, learned = store.list_messages(task_id), None
    if msgs and (body is None or body.learn):
        mid = _teach_not_a_task(msgs[0], background)
        if mid: learned = {'memory_id': mid}
    # whatever was (or was not) learned about the sender, THIS conversation has been ruled on:
    # the owner's ignore route is what ingest.veto reads before the next message on it can open
    # a task (store.owner_verdict_on_thread) - the six-tasks-from-one-chat failure
    if msgs:
        store.add_route(msgs[0]['MessageId'], None, 'ignore', None,
                        f"not a task - {(msgs[0].get('Subject') or 'this conversation')[:80]}", [], ACTOR)
    store.audit('task', task_id, 'not_a_task_delete', ACTOR)
    _drop_task(task_id)
    return {'ok': True, 'learned': learned}

class SplitHalf(BaseModel): title: str | None = None; summary: str | None = None
class TaskSplitBody(BaseModel):
    second: SplitHalf
    first: SplitHalf | None = None
    move_message_ids: list[int] = []
class MergeBody(BaseModel): into: int

@app.get('/api/tasks/{task_id}/split/suggest')
def split_suggest(task_id: int):
    """What are the two jobs in here? A proposal only - nothing is created until the owner
    confirms, and with no AI brain connected it hands back the ask-shaped lines instead."""
    if not store.get_task(task_id): raise HTTPException(404, 'task not found')
    return reshape.propose_split(store, task_id, _llm())

@app.post('/api/tasks/{task_id}/split')
def split_task_api(task_id: int, body: TaskSplitBody):
    """Triage filed two jobs as one. This task keeps its ref, session and report; the second
    job becomes a new task, with the messages you ticked."""
    try:
        new = reshape.split_task(store, task_id, body.second.dict(),
                                 body.first.dict() if body.first else None, body.move_message_ids, ACTOR)
    except ValueError as e:
        raise HTTPException(404 if 'no task' in str(e) else 422, str(e))
    return {'taskId': new, 'ref': task_ref(new)}

@app.get('/api/tasks/{task_id}/merge-candidates')
def merge_candidates_api(task_id: int):
    if not store.get_task(task_id): raise HTTPException(404, 'task not found')
    return {'data': reshape.merge_candidates(store, task_id)}

@app.post('/api/tasks/{task_id}/merge')
def merge_task_api(task_id: int, body: MergeBody):
    """Fold this task into `into` - the same job, filed twice. This one is dropped with a
    pointer at the survivor; a task with a live session cannot be folded away underneath it."""
    if hub_term.for_task(task_id):     # for_task only ever returns a LIVE session
        raise HTTPException(422, f'{task_ref(task_id)} has a session running - close or pause it first')
    try:
        return reshape.merge_tasks(store, task_id, body.into, ACTOR)
    except ValueError as e:
        raise HTTPException(404 if 'no task' in str(e) else 422, str(e))

@app.post('/api/tasks/purge-dropped')
def purge_dropped():
    victims = [t['TaskId'] for t in store.list_tasks('dropped')]
    for tid in victims:
        store.audit('task', tid, 'purge_dropped', ACTOR)
        _drop_task(tid)
    return {'ok': True, 'deleted': len(victims)}

def _drop_task(tid: int):
    """Deleting a task must also stop the agent working it. "Not a task" read as a kill - it
    was not: the pty kept running, kept editing files, and kept holding the task id, so when
    SQLite handed that id to the NEXT task the orphan showed up as the agent working it. A
    task that no longer exists has nobody working it, by definition."""
    try:
        live = hub_term.for_task(tid)
        if live:
            hub_term.close(live['sid'])
            logger.info(f'closed the session on task {tid} - the task was deleted')
    except Exception as e:
        logger.warning(f'could not close the session on deleted task {tid}: {e}')
    store.delete_task(tid)

@app.get('/api/messages/{mid}')
def get_message(mid: int):
    """One message, whole body - the timeline row only carries a 4000-char preview."""
    m = store.get_message(mid)
    if not m: raise HTTPException(404, 'message not found')
    return m

def _att_row(a: dict) -> dict:
    """One attachment as the panel needs it: enough to decide whether to draw it or list it."""
    return {'id': a['AttachmentId'], 'name': a['Name'], 'content_type': a['ContentType'] or '',
            'size': a['Size'], 'inline': bool(a['Inline']), 'saved': bool(a['Path']),
            'is_image': str(a['ContentType'] or '').startswith('image/'),
            # a voice note is meant to be PLAYED where you are reading it, not downloaded and
            # opened in something else - the panel draws a player for these (Attachments.jsx)
            'is_audio': str(a['ContentType'] or '').startswith('audio/'),
            'url': f"/api/attachments/{a['AttachmentId']}" if a['Path'] else None}

# SVG/HTML as a navigable document on this origin runs script as Taskuary. PNG/JPEG
# stay `inline` so the panel <img> can draw them; SVG still displays in <img> with
# Content-Disposition: attachment (the tab-open case is what this blocks).
_NOSCRIPT = ('image/svg+xml', 'image/svg', 'text/html', 'application/xhtml+xml',
             'text/xml', 'application/xml', 'text/javascript', 'application/javascript')

def _attachment_path(raw: str):
    """The file on disk, if it is really one of ours. A Path column pointing outside
    ~/.taskuary/attachments would turn GET /api/attachments/:id into a local file read."""
    if not raw: return None
    # resolve() is INSIDE the try: a malformed stored path (embedded NUL, illegal chars)
    # raises right there, and that used to be a 500 where the honest answer is 404
    try:
        p, root = Path(raw).resolve(), (config.home() / 'attachments').resolve()
        if not p.is_relative_to(root) or not p.is_file(): return None
    except (OSError, ValueError):
        return None
    return p

def _att_filename(name: str) -> str:
    """Content-Disposition cannot carry CR/LF or a path - take the first line, then
    the basename. Mail names are mostly cleaned on save; this is the last gate."""
    n = Path((str(name or 'attachment').splitlines() or ['attachment'])[0]).name[:120]
    return n or 'attachment'

@app.get('/api/messages/{mid}/attachments')
def message_attachments(mid: int):
    if not store.get_message(mid): raise HTTPException(404, 'message not found')
    return {'data': [_att_row(a) for a in store.list_attachments(mid)]}

@app.get('/api/attachments/{aid}')
def attachment(aid: int, download: bool = False):
    """The bytes. Images are served inline so the panel can just draw them; everything else
    downloads under its own name. Path is confined to the attachments dir; SVG/HTML never
    render as a document on this origin."""
    a = store.get_attachment(aid)
    if not a: raise HTTPException(404, 'attachment not found')
    path = _attachment_path(a.get('Path'))
    if not path:
        raise HTTPException(404, 'this one was never saved - open the original message for it')
    ct = (a.get('ContentType') or 'application/octet-stream').split(';')[0].strip() or 'application/octet-stream'
    # audio joins images as "shown in place": <audio> is a subresource like <img>, and an
    # attachment disposition on it is a download prompt waiting to happen
    inline = (not download) and ct.lower().startswith(('image/', 'audio/')) and ct.lower() not in _NOSCRIPT
    resp = FileResponse(path, media_type=ct, filename=_att_filename(a.get('Name')),
                        content_disposition_type='inline' if inline else 'attachment')
    resp.headers['X-Content-Type-Options'] = 'nosniff'
    return resp

@app.post('/api/messages/{mid}/attachments/fetch')
def fetch_attachments(mid: int):
    """Pull a message's attachments now - for mail that arrived before Taskuary kept them, and
    for a retry after a Graph hiccup."""
    m = store.get_message(mid)
    if not m: raise HTTPException(404, 'message not found')
    ext = str(m.get('ExternalId') or '')
    if m.get('Channel') != 'email' or not ext.startswith('graph:'):
        raise HTTPException(422, 'only Outlook mail can be re-fetched')
    c = store.get_connector_by_type('outlook', with_secret=True)
    if not c: raise HTTPException(422, 'no Outlook connection')
    from .channels import fetch_mail_attachments, graph_creds, graph_token
    try:
        gcfg, gsec, _ = graph_creds(store, c)
        n = fetch_mail_attachments(store, mid, graph_token(gcfg, gsec), m.get('SourceName'), ext.split(':', 1)[1])
    except Exception as e:
        raise HTTPException(422, str(e)[:300])
    return {'fetched': n, 'data': [_att_row(a) for a in store.list_attachments(mid)]}

class OpenReplyBody(BaseModel): draft: bool = True

@app.post('/api/messages/{mid}/reply')
def open_reply(mid: int, body: OpenReplyBody = None):
    """Put a reply on the table for ANY message - the coder finished and you want to answer, or
    triage never queued one. Creates the pending review (reusing one if it exists) and, unless
    draft=false, writes the AI draft right now so the box comes back filled. Approving still
    sends; nothing here does."""
    m = store.get_message(mid)
    if not m: raise HTTPException(404, 'message not found')
    # a FILED message stays filed: answering it is a reply, not a project, and promoting it to a
    # task just to hold the review put a TQ badge on chatter. The review rides task-less.
    tid = m.get('TaskId')
    rv = store.pending_review(tid) if tid else None
    rid = rv['ReviewId'] if rv else store.add_review({'TaskId': tid, 'MessageId': mid, 'Kind': 'draft',
                                                      'Status': 'pending', 'Reason': 'you opened a reply on this message'})
    draft = (rv or {}).get('DraftText') or ''
    if not draft and (body is None or body.draft):
        try:
            draft = (responder.write_draft(store, tid, rid, actor=ACTOR) if tid
                     else responder.draft_for_message(store, m, rid))
        except Exception as e:
            logger.warning(f'reply draft failed for message {mid}: {e}')   # the box opens empty; write it yourself
    store.audit('review', rid, 'open_reply', ACTOR, detail={'message_id': mid})
    return {'reviewId': rid, 'taskId': tid, 'draft': draft}


class NotMineBody(BaseModel):
    note: str | None = None
    scope: str = 'sender'
    topic: str | None = None        # the owner's own wording for a 'subject' verdict's key

NOT_MINE_SCOPES = ('subject', 'sender', 'sender_domain', 'global')

def _topic_key(m: dict) -> str:
    """The topic a subject-scoped verdict keys on. Empty when the subject has too little in it
    to match on, which is when the verdict has to be about the sender instead."""
    from .routing import subject_topic
    return subject_topic(m.get('Subject') or '')

def _suggest_scope(m: dict) -> str:
    """Which scope this verdict most likely means. It defaulted to 'sender', and that is the
    wrong guess for what people actually write: "resident refunds are not our task" is about a
    KIND OF WORK, and filed under one colleague on a seventeen-person thread it never fired
    again. A subject to key on means the topic is the better bet; the owner still chooses."""
    return 'subject' if _topic_key(m) else 'sender'

def _not_mine_note(m: dict, scope: str = None, topic: str = None) -> str:
    """The note we would write: an EVIDENCE line - when, what subject, from whom, what the owner
    said - never a rule. The scope only decides which later messages this line is pulled up
    for (by topic, by sender, by their domain, or always); the model reads the line itself and
    judges how alike the new message is. So the wording carries the specifics whatever the
    scope, and the owner can still say it in their own words."""
    who = m.get('FromEmail') or m.get('FromName') or 'an unknown sender'
    subj = (m.get('Subject') or '')[:90]
    when = str(m.get('SentAt') or '')[:10]
    scope = scope or _suggest_scope(m)
    about = (f' - the topic "{topic or _topic_key(m)}"' if scope == 'subject' and (topic or _topic_key(m)) else
             f' - anyone at {who.rsplit("@", 1)[-1]}' if scope == 'sender_domain' else
             ' - whoever sends it' if scope == 'global' else '')
    return f'{when}: "{subj}" from {who}{about} - NOT OURS: other people\'s work, no task, no reply'

@app.post('/api/messages/{mid}/not-mine')
def not_mine(mid: int, body: NotMineBody, background: BackgroundTasks = None):
    """"Not our task." Two things happen: this item stops being work, and the reason is written
    to MEMORY - which the funnel reads on every later message it applies to (ingest.notes_for
    for the classifier, ingest.veto before a message joins an existing task), so the same
    verdict doesn't have to be given twice. Unlike "Skip this sender", their mail keeps
    arriving; only the judgement is learned.

    SCOPE is the whole game, and 'sender' was the wrong default: most verdicts are about a kind
    of work, not a person, and a topic rule keyed to one colleague on a long thread never fires
    again. 'subject' keys on the topic and matches by overlap, so the next resident, invoice or
    ticket number in the subject line does not slip past it."""
    m = store.get_message(mid)
    if not m: raise HTTPException(404, 'message not found')
    em = (m.get('FromEmail') or '').lower()
    if body.scope not in NOT_MINE_SCOPES: raise HTTPException(422, 'bad scope')
    scope = body.scope
    # a scope with nothing to key on would save a verdict that can never match: fall back to the
    # widest thing this message CAN be keyed on rather than writing a note that does nothing
    # the owner can say what the topic IS - they know that "resident refund request" is the
    # standing part and the resident's name is not, and no amount of trimming beats being told
    from .routing import norm_subject, tokens
    topic = norm_subject((body.topic or '').strip())[:200] or _topic_key(m)
    if scope == 'subject' and len(tokens(topic)) < 2: scope = 'sender' if em else 'global'
    if scope in ('sender', 'sender_domain') and not em: scope = 'global'
    key = (topic if scope == 'subject' else None if scope == 'global'
           else em.rsplit('@', 1)[-1] if scope == 'sender_domain' else em)
    note = (body.note or '').strip() or _not_mine_note(m, scope, key if scope == 'subject' else None)
    memid = store.add_memory({'Scope': scope, 'ScopeKey': key, 'Note': note[:1000],
                              'Source': 'verdict', 'Active': 1, 'CreatedBy': ACTOR})
    learn.note_verdicts(store)
    tid = m.get('TaskId')
    if tid and store.get_task(tid):
        store.audit('task', tid, 'not_mine_delete', ACTOR, detail={'message_id': mid, 'memory_id': memid})
        _drop_task(tid)                              # its messages revert to 'filed'
    store.set_message_status(mid, 'ignored')
    store.add_route(mid, None, 'ignore', None, f'not ours - {note[:200]}', [], ACTOR)
    store.audit('memory', memid, 'create', ACTOR, detail={'scope': scope, 'key': key, 'from': em})
    # "not ours" draws a responsibility boundary - the general shape of it belongs in LEARNED.md
    if background is not None:
        background.add_task(learn.learn_from, store,
                            f"mem{memid}: owner said NOT OURS ({scope}): \"{(m.get('Subject') or '')[:80]}\" "
                            f"from {em or '?'} - {note[:200]}")
    return {'ok': True, 'memoryId': memid, 'note': note, 'scope': scope, 'scopeKey': key,
            'taskDeleted': bool(tid), 'alsoCovered': _also_covered(scope, key, tid)}

def _also_covered(scope: str, key: str, dropped_tid) -> list:
    """Other OPEN tasks this new verdict now covers - REPORTED, never deleted. One click that
    silently removes five tasks is not a verdict, it is a surprise. But saying nothing is how
    "the system is not learning it" happens: the verdict works from now on while yesterday's
    tasks sit there looking like proof that it did not."""
    from .ingest import topic_hit
    if scope == 'global' or not key: return []
    out = []
    for t in store.snapshots():
        if t['task_id'] == dropped_tid: continue
        hit = (any(topic_hit(key, s) for s in t['subjects']) if scope == 'subject'
               else any((e or '').lower().endswith('@' + key) for e in t['senders']) if scope == 'sender_domain'
               else key in {(e or '').lower() for e in t['senders']})
        if hit: out.append({'taskId': t['task_id'], 'title': t['title']})
    return out[:20]

@app.post('/api/messages/{mid}/file')
def file_message(mid: int, body: NotATaskBody = None, background: BackgroundTasks = None):
    """"Not a task - just conversation" / "Nothing to do here" - the timeline's door onto the
    SAME verdict the task list's "Not a task" gives, and now teaching the same thing through it
    (owner, 2026-08-30). It used to teach nothing at all, which was the right answer to the wrong
    problem: what made the old exit dangerous was "Not our task" writing a verdict against the
    SENDER - and against every sender at once on a channel with no address, like Teams. A
    NOT A TASK note keyed to the topic is not that, and _teach_not_a_task writes nothing when
    there is nothing to key it to. No sender is ever muted here; that is "Skip this sender".

    Either way the rest of THIS conversation is filed with it - the owner ignore route below is
    what ingest.veto reads (store.owner_verdict_on_thread), because "not a task" said on a thread
    and then a task from its next reply is the funnel arguing with itself."""
    m = store.get_message(mid)
    if not m: raise HTTPException(404, 'message not found')
    tid = m.get('TaskId')
    if tid and store.get_task(tid):
        store.audit('task', tid, 'filed_not_work', ACTOR, detail={'message_id': mid})
        _drop_task(tid)                              # its messages revert to 'filed'
    learned = _teach_not_a_task(m, background) if (body is None or body.learn) else None
    store.set_message_status(mid, 'ignored')
    store.add_route(mid, None, 'ignore', None, 'nothing to do - filed by the owner', [], ACTOR)
    return {'ok': True, 'taskDeleted': bool(tid), 'memoryId': learned}

@app.get('/api/messages/{mid}/not-mine/suggest')
def not_mine_suggest(mid: int, scope: str = None, topic: str = None):
    """The note we'd save, so the panel can show it for editing before it's committed - phrased
    for `scope`, or for the scope this message most likely calls for when none is given."""
    m = store.get_message(mid)
    if not m: raise HTTPException(404, 'message not found')
    if scope and scope not in NOT_MINE_SCOPES: raise HTTPException(422, 'bad scope')
    scope = scope or _suggest_scope(m)
    from .routing import norm_subject
    topic = norm_subject((topic or '').strip())[:200] or _topic_key(m)
    return {'note': _not_mine_note(m, scope, topic), 'from': m.get('FromEmail'), 'scope': scope,
            'topic': topic}

def start_session(store_, tid: int, agent: str = None, model: str = None, instruction: str = None) -> dict:
    try:
        return hub_term.start_on_task(store_, tid, agent or 'coder', model, instruction, ACTOR)
    except (ValueError, RuntimeError, FileNotFoundError) as e:
        raise HTTPException(422, str(e))

@app.post('/api/messages/{mid}/dispatch')
def dispatch_message(mid: int, body: DispatchBody, background: BackgroundTasks):
    """Hand ANY timeline item (failed report, email, chat) to an agent with your own
    prompt. Messages that are not on a task yet become one first, so the run carries the
    full context (subject, sender, body, thread) the agent needs."""
    m = store.get_message(mid)
    if not m: raise HTTPException(404, 'message not found')
    if not store.get_agent(body.agent): raise HTTPException(422, f'unknown agent: {body.agent}')
    _learn_promotion(m, background)
    tid = m.get('TaskId') or task_from_message(store, mid, ACTOR)
    ses = start_session(store, tid, body.agent, body.model, body.instruction)
    return {'dispatch': 'session', 'agent': body.agent, 'taskId': tid, 'ref': task_ref(tid), 'session': ses}

def _learn_promotion(m: dict, background):
    """A FILED message the owner promotes by hand is a triage miss in the other direction -
    fyi was the wrong call. The under-reach lessons matter as much as the over-reach ones."""
    if background is not None and not m.get('TaskId') and m.get('Status') == 'filed':
        background.add_task(learn.learn_from, store,
                            f"msg{m['MessageId']}: triage filed \"{(m.get('Subject') or '')[:80]}\" from "
                            f"{m.get('FromEmail') or m.get('SourceName') or '?'} as fyi, but the owner made it a task - "
                            'triage under-reached')

# ── the assistant on the Timeline (assistant.py): its post and its buttons ───────────────────
@app.get('/api/assistant/ideas')
def assistant_ideas(status: str = None, mid: int = None):
    """What the assistant has said, with what became of each line - by state, or the lines of one post."""
    return {'data': [assistant._public(i) | {'firstSeen': i.get('FirstSeen'), 'lastSaid': i.get('LastSaid'), 'messageId': i.get('MessageId')}
                     for i in store.list_ideas(status or None, mid)]}

class IdeaBody(BaseModel): days: int = 1

@app.post('/api/assistant/ideas/{iid}/{verb}')
def assistant_act(iid: int, verb: str, body: IdeaBody = None, background: BackgroundTasks = None):
    """One button on one line: followup (the chase, drafted into Review), task (the agent starts),
    discuss (the full Assistant workspace), dismiss, snooze, or done."""
    try:
        if verb == 'discuss': return assistant.discussion_task(store, iid, ACTOR)
        return assistant.act(store, iid, verb, ACTOR, days=(body.days if body else 1),
                             learn_async=background.add_task if background is not None else None)
    except ValueError as e: raise HTTPException(422, str(e))

@app.post('/api/assistant/talk/{iid}')
def assistant_talk(iid: int, body: TextBody):
    """Talk back to one suggestion: corrections and questions get an answer, not a verdict button."""
    try: return assistant.talk(store, iid, body.body, ACTOR, _llm())
    except ValueError as e: raise HTTPException(422, str(e))

class MineBody(BaseModel):
    kind: str = 'general'
    title: str | None = None        # the assistant's suggested title, accepted as-is from the panel

@app.post('/api/messages/{mid}/mine')
def mine_message(mid: int, body: MineBody = None, background: BackgroundTasks = None):
    """"This one is mine": a real task, on my list, with no agent sent at it. A lot of mail is
    genuinely work and genuinely not an agent's - go into some web app, approve the thing - and
    filing it as "nothing to do" is a lie. It lands as a task assigned to you, which the feed
    already reads as needs-you (no run on it, not done). The day a computer-use connector exists,
    THIS is the queue it takes from."""
    m = store.get_message(mid)
    if not m: raise HTTPException(404, 'message not found')
    _learn_promotion(m, background)
    tid = m.get('TaskId') or task_from_message(store, mid, ACTOR, (body.kind if body else None) or 'general', ACTOR)
    if not (store.get_task(tid) or {}).get('Assignee'): store.update_task(tid, {'Assignee': ACTOR}, ACTOR)
    if body and (body.title or '').strip(): store.update_task(tid, {'Title': body.title.strip()[:200]}, ACTOR)
    store.audit('task', tid, 'mine', ACTOR, detail={'message_id': mid, 'subject': m.get('Subject')})
    return {'taskId': tid, 'ref': task_ref(tid)}

class SplitBody(BaseModel): kind: str | None = None

@app.post('/api/messages/{mid}/split')
def split_msg(mid: int, body: SplitBody = None):
    """Give this message its own task. Two unrelated asks in one chat thread are one
    conversation but two jobs, and an agent sent at the task only ever gets the first."""
    if not store.get_message(mid): raise HTTPException(404, 'message not found')
    tid = split_message(store, mid, ACTOR, (body.kind if body else None))
    return {'taskId': tid, 'ref': task_ref(tid)}

class HandoffBody(BaseModel):
    to: str | None = None; channel: str = 'email'; note: str | None = None
    text: str | None = None; draft_only: bool = False

# ── the agent wall (blackboard.py): what the agents leave for each other ─────────────────
class NoteBody(BaseModel):
    body: str; kind: str = 'note'; agent: str | None = None
    cwd: str | None = None; task_id: int | None = None; files: str | None = None

@app.get('/api/board/notes')
def board_notes(cwd: str = '', limit: int = 60, all: bool = False):
    """Everything by default - the Board is one wall - or one checkout's own when cwd is given.
    `all` includes the notes a daily roll-up has already composted into a summary."""
    return {'data': store.notes(blackboard.norm(cwd) or None, limit, rolled=all),
            'kinds': list(blackboard.KINDS), 'summary_kind': blackboard.SUMMARY}

@app.post('/api/board/notes')
def board_post(body: NoteBody):
    try:
        return blackboard.post(store, body.body, body.kind, body.agent or ACTOR, body.cwd or '',
                               body.task_id, body.files or '')
    except ValueError as e: raise HTTPException(422, str(e))

@app.post('/api/board/notes/{note_id}/read')
def board_read(note_id: int, who: str = ''):
    store.mark_note_read(note_id, who or ACTOR)
    return {'ok': True}

@app.get('/api/people')
def people(): return {'data': store.people()}

@app.get('/api/send-targets')
def send_targets():
    """Where a report is allowed to be sent: the live channels, and the destinations known on
    each. The builder offers these and nothing else - a WhatsApp JID typed from memory is a
    report that quietly goes nowhere."""
    return {'data': outbound.send_targets(store)}

@app.post('/api/tasks/{task_id}/handoff')
def handoff(task_id: int, body: HandoffBody):
    """Hand the task to a PERSON: the AI writes the forward message from the task's own
    context, you edit it, and it goes out on the channel you picked."""
    t = store.get_task(task_id)
    if not t: raise HTTPException(404, 'task not found')
    try:
        text = (body.text or '').strip() or outbound.draft_handoff(store, task_id, body.to or 'a colleague', body.note)
        if body.draft_only: return {'draft': text}
        if not body.to: raise HTTPException(422, 'who is it going to?')
        if body.channel == 'email':
            sent = outbound.send_email(store, [body.to], f"{task_ref(task_id)} {t.get('Title') or ''}".strip(), text)
        elif body.channel == 'teams':
            msgs = [m for m in store.list_messages(task_id) if m['Channel'] == 'teams']
            if not msgs: raise HTTPException(422, 'this task did not come from a chat, so there is no chat to post in - use email')
            sent = outbound.send_teams(store, (msgs[-1].get('ConversationId') or '')[6:], text)
        else:
            raise HTTPException(422, f'cannot send on {body.channel}')
    except HTTPException: raise
    except Exception as e: raise HTTPException(422, str(e)[:400])
    store.add_comment(task_id, ACTOR, 'human', f'Handed off to {body.to} by {body.channel}:\n{text}')
    # Handing work to a person ENDS it here. The forward went out and somebody else owns the
    # thing now, so leaving the card open on 'needs you' is the funnel asking for a second
    # decision about work the owner just gave away. Closing it also retires the task's pending
    # reviews, so the Review queue stops asking about a draft that has already been forwarded.
    store.update_task(task_id, {'Status': 'done'}, ACTOR)
    store.audit('task', task_id, 'handoff', ACTOR,
                detail={'to': body.to, 'channel': body.channel, 'closed': True})
    return {'sent': sent, 'text': text, 'status': 'done'}

@app.get('/api/runs/live')
def live_runs(lines: int = 3):
    """The tail of every run that is working right now - the Board renders it as a tiny
    console on each card (the full trace is on the task)."""
    out = []
    for r in store.running_runs():
        try: evs = [e for e in json.loads(r.get('TraceJson') or '[]') if e.get('kind') == 'live']
        except ValueError: evs = []                    # mid-write JSON: next poll fixes it
        out.append({'RunId': r['RunId'], 'TaskId': r['TaskId'], 'AgentName': r['AgentName'], 'kind': 'run',
                    'StartedAt': r['StartedAt'], 'idle': 0, 'files': blackboard.trace_files(r.get('TraceJson')),
                    'tail': [e['detail'] for e in evs[-max(1, min(lines, 10)):]]})
    # live pty sessions count as work in progress too - and their idle time is what says
    # whether the agent is thinking or parked at a question waiting for the owner
    for t in hub_term.live_sessions(tail=max(1, min(lines, 10))):
        if t.get('taskId'):
            # `asking` = the last lines look like a question for the owner (waitroom.looks_like_question):
            # the hand-raise notification says "asked you something" instead of "stopped"
            out.append({'RunId': None, 'TaskId': t['taskId'], 'AgentName': t['agent'] or t['label'],
                        'kind': 'session', 'StartedAt': t['started'], 'idle': t['idle'],
                        'waiting': (w := t['waiting'] if t.get('waiting') is not None else t['idle'] >= hub_term.IDLE_WAITING), 'phase': t.get('phase'),
                        'asking': bool(w) and waitroom.looks_like_question(t.get('tail') or []),
                        'Title': (store.get_task(t['taskId']) or {}).get('Title') or '',
                        'files': t.get('files') or [], 'tail': t.get('tail') or [],
                        'cli': t.get('cli'), 'work': t.get('work')})     # the CLI it runs; said and did (witness.py) - the card's pane
    return {'data': out}

@app.get('/api/runs/{run_id}')
def get_run(run_id: int):
    r = store.get_run(run_id)
    if not r: raise HTTPException(404, 'run not found')
    return r

@app.get('/api/reviews')
def reviews(status: str = None):
    rows = store.list_reviews(status)
    gh_ok = store.github_replies_ok()
    for r in rows: r['CanSend'] = _can_send(r.get('Channel'), bool(r.get('MessageId')), gh_ok)
    return {'data': rows}

@app.post('/api/reviews/{rid}/decide')
def decide(rid: int, body: DecideBody, background: BackgroundTasks = None):
    """The verdict itself lives in verdicts.decide - ONE door, shared with the phone road
    (a 'approve' typed in the notify chat lands the same way this button does)."""
    rv = store.get_review(rid)
    if not rv: raise HTTPException(404, 'review not found')
    from .verdicts import VERB2STATUS, decide as land
    if body.verb not in VERB2STATUS: raise HTTPException(422, 'bad verb')
    return land(store, rv, body.verb, body.final_text, body.note, ACTOR,
                learn_async=(background.add_task if background is not None else None))

@app.get('/api/tasks/{tid}/proof')
def task_proof(tid: int):
    """The evidence behind a task: files git says moved, the test run the session actually
    performed, CI on its pull request, attempts and timings - plus what is MISSING, said
    plainly, so a thin card is never mistaken for a clean one."""
    if not store.get_task(tid): raise HTTPException(404, 'task not found')
    from . import proof
    return proof.gather(store, tid)

@app.get('/api/tasks/{tid}/work')
def task_work(tid: int, diff: bool = True):
    """Said and did, for the task page: the agent's own list and tool in hand (witness), the files
    it wrote with git's +/- per file (proof.review), and where the task came from - the two
    halves side by side so a disagreement is seen BEFORE the review, not after."""
    t = store.get_task(tid)
    if not t: raise HTTPException(404, 'task not found')
    from . import proof
    sess = hub_term.session_for(tid)
    work = sess.witness.snapshot(sess.files(), sess.cwd, (sess.tail(1) or [''])[-1]) if sess else None
    rev = {}
    if diff:
        try: rev = proof.review(store, tid) or {}
        except Exception as e: logger.debug(f'work review for {tid}: {e}')
    by_path = {f.get('path'): f for f in (rev.get('files') or [])}
    files = [{**f, 'added': by_path.get(f['path'], {}).get('added'), 'removed': by_path.get(f['path'], {}).get('removed')} for f in (work or {}).get('files', [])]
    for p, f in by_path.items():                        # git saw it, the witness did not: still DID
        if p not in {x['path'] for x in files}: files.append({'path': p, 'n': 0, 'last': None, 'stray': False, 'late': False, 'added': f.get('added'), 'removed': f.get('removed')})
    d = store.task_detail(tid); m0 = (d.get('messages') or [None])[0] or {}
    approved = next((r for r in d.get('reviews') or [] if r.get('Status') in ('approved', 'sent')), None)
    prov = {'from': ' · '.join(x for x in (m0.get('Channel'), m0.get('FromName') or m0.get('FromEmail')) if x) or t.get('Source') or '',
            'kind': t.get('Kind') or '', 'by': (sess.agent if sess else '') or t.get('RunAgent') or '',
            'approved': (approved or {}).get('UpdatedAt') or (approved or {}).get('CreatedAt'), 'status': t.get('Status')}
    return {'work': work, 'files': files, 'prov': prov, 'diffstat': {'added': rev.get('added'), 'removed': rev.get('removed')},
            'session': {'sid': sess.sid, 'alive': sess.alive, 'agent': sess.agent, 'cli': hub_term.cli_of(sess.argv), 'started': sess.started, 'cwd': sess.cwd} if sess else None}

@app.post('/api/hooks/claude')
async def claude_hook(request: Request):
    """Claude Code's hook fired in a checkout a session of ours works in (hooks.py wires it): the
    event's JSON comes in on the body. Always 200 and quiet - a hook must never trouble the agent."""
    from . import hooks
    try: payload = json.loads((await request.body()) or b'{}')
    except ValueError: return {'bound': False}
    try: return hooks.receive(payload if isinstance(payload, dict) else {})
    except Exception as e:
        logger.debug(f'claude hook ignored: {e}'); return {'bound': False}

# ── the handbook (handbook.py): what the agents worked out, by topic, open to comment ──────
class LoreBody(BaseModel):
    title: str; body: str = ''; topic: str = ''; kind: str = 'howto'; author: str | None = None
class LoreCommentBody(BaseModel): body: str

@app.get('/api/handbook')
def handbook_list(topic: str = None, q: str = None, sort: str = 'new', limit: int = 60):
    """The Social tab. Topics down the side, posts in the middle - the company's own know-how,
    written by whichever agent worked it out, and correctable by whoever knows better."""
    posts = store.lore_posts(topic or None, q or None, min(limit, 200), sort)
    return {'topics': store.lore_topics(), 'data': posts, 'count': store.lore_count()}

@app.get('/api/handbook/{lid}')
def handbook_one(lid: int):
    p = store.lore_get(lid)
    if not p: raise HTTPException(404, 'no such entry')
    return {**p, 'comments': store.lore_comments(lid)}

@app.post('/api/handbook')
def handbook_post(body: LoreBody):
    from . import handbook
    try: return handbook.post(store, body.title, body.body, body.topic, body.kind, body.author or ACTOR)
    except ValueError as e: raise HTTPException(422, str(e))

@app.post('/api/handbook/{lid}/comment')
def handbook_comment(lid: int, body: LoreCommentBody):
    """A comment is how a post gets corrected without being erased. An agent that finds an entry
    wrong says so here, and the next reader sees both."""
    if not store.lore_get(lid): raise HTTPException(404, 'no such entry')
    text = ' '.join((body.body or '').split())[:4000]
    if not text: raise HTTPException(422, 'say something')
    cid = store.lore_comment(lid, text, ACTOR)
    return {'commentId': cid, 'comments': store.lore_comments(lid)}

@app.post('/api/handbook/{lid}/vote')
def handbook_vote(lid: int, up: bool = True):
    """Useful, or not. The score is what `handbook.block` ranks by, so voting is how the entries
    an agent is handed before it starts become the ones that actually helped."""
    if not store.lore_get(lid): raise HTTPException(404, 'no such entry')
    store.lore_vote(lid, 1 if up else -1)
    return dict(store.lore_get(lid))

@app.post('/api/handbook/{lid}/retire')
def handbook_retire(lid: int):
    """No longer true. Retired, not deleted: a handbook that silently loses entries is one you
    cannot tell the difference between right and empty in."""
    if not store.lore_get(lid): raise HTTPException(404, 'no such entry')
    store.lore_retire(lid, ACTOR)
    store.audit('lore', lid, 'retire', ACTOR)
    return {'retired': True}

class OutboxBody(BaseModel):
    channel: str; to: str; about: str; mode: str = 'draft'
    subject: str | None = None; repo: str | None = None

@app.post('/api/outbox')
def outbox(body: OutboxBody):
    """＋ New → Send something. Start a message instead of answering one.

    Two modes, one ending. 'draft' has the AI write it now, in the owner's voice, and parks it in
    Review. 'task' sends an agent to find out first; when it finishes, the message is written
    from what it actually found and lands in the same place. Neither one sends: the approved
    review does, through the one door every outgoing message already goes through."""
    from . import outbox as ob
    try: return ob.compose(store, body.channel, body.to, body.about, body.mode, body.subject, body.repo, ACTOR)
    except ValueError as e: raise HTTPException(422, str(e))
    except Exception as e: raise HTTPException(422, str(e)[:400])

class NoteBody(BaseModel): title: str; body: str = ''; when: str | None = None

@app.post('/api/notes')
def own_note(body: NoteBody):
    """A note to yourself: a reminder, an idea, a thing to come back to.

    Everything on the Timeline until now was something that HAPPENED to the owner - mail, a
    chat, a report, a repository. There was nowhere to put "chase the Ashgrove AP on Tuesday"
    except an agent that would go and do something about it, so it went in a notebook instead
    and the one screen the owner watches all day knew nothing about it. `when` is what the note
    is FOR, not when it was typed: the row sits in that day (ownwork.note)."""
    from . import ownwork
    try: return ownwork.note(store, body.title, body.body, body.when, ACTOR)
    except ValueError as e: raise HTTPException(422, str(e))

class ReleaseBody(BaseModel): agent: str | None = None; model: str | None = None

@app.post('/api/tasks/{task_id}/release')
def release_task(task_id: int, body: ReleaseBody, background: BackgroundTasks):
    """"Yes, this one is fine" - the owner letting a held task through to the agent.

    A first message from an address nobody here has ever written to does not get to start a
    session by itself (senders.known): an inbound message is a prompt, and an unvetted prompt
    that opens a terminal on this machine is the whole prompt-injection surface in one step. It
    is still triaged, still shown, still a task - it just waits for this click. Releasing drops
    the hold so the sender is never asked about again, and starts the session."""
    from .ingest import HOLD_TAG
    if not store.get_task(task_id): raise HTTPException(404, 'task not found')
    if not store.task_has_tag(task_id, HOLD_TAG): raise HTTPException(422, 'this task is not being held')
    store.tag_task(task_id, HOLD_TAG, on=False, actor=ACTOR)
    store.add_comment(task_id, ACTOR, 'human', 'Released to the agent - you vouched for this sender.')
    store.audit('task', task_id, 'release', ACTOR)
    ses = start_session(store, task_id, body.agent, body.model)
    return {'released': True, 'session': ses}

class AgentDoneBody(BaseModel): task_id: int; summary: str = ''; agent: str = 'agent'

@app.post('/api/agent/done')
def agent_done(body: AgentDoneBody):
    """`taskuary --done "..."` from inside an agent's own shell: the session says it has finished.

    This is the ending the Done button used to be the only door to - and the button is a person
    looking at a screen, which is exactly what an agent working at 2am does not have. Same wrap,
    same report, same drafted reply waiting on the owner's approval; only the thing that noticed
    the work was over has changed (selfclose.declare)."""
    from . import selfclose
    if not store.get_task(body.task_id): raise HTTPException(404, 'no such task')
    return selfclose.declare(store, body.task_id, body.summary, body.agent)

@app.get('/api/tasks/{tid}/diff')
def task_diff(tid: int, scope: str = 'task'):
    """What THIS task's agent changed in its checkout, per file (scope=checkout: everything a
    push would carry, whoever wrote it). Read-only by construction: `git diff`, `git status`,
    `git log` - never `add`, never `stash`."""
    if not store.get_task(tid): raise HTTPException(404, 'task not found')
    from . import proof
    return proof.review(store, tid, scope if scope in ('checkout', 'pr') else 'task')

@app.post('/api/tasks/{tid}/land')
def task_land(tid: int, flow: str = None):
    """Publish this task's work the way Settings says: a DRAFT pull request, or the commits
    pushed straight onto the default branch. `flow` overrides for this one task. Never
    merges, never force-pushes, and refuses unless 'Agents may push / deploy' is on."""
    if not store.get_task(tid): raise HTTPException(404, 'task not found')
    from . import ci
    try:
        if flow == 'direct': return ci.push_direct(store, tid, ACTOR)
        if flow == 'pr': return ci.open_for_task(store, tid, ACTOR)
        return ci.land(store, tid, ACTOR)
    except Exception as e:
        raise HTTPException(422, str(e)[:300])

@app.post('/api/tasks/{tid}/ci')
def task_ci(tid: int):
    """Check this task's PR now: refresh the checks and, when red, hand the failure to the
    agent that wrote the code."""
    if not store.get_task(tid): raise HTTPException(404, 'task not found')
    from . import ci
    return ci.check_task(store, tid)

@app.post('/api/tasks/{tid}/answer')
def answer_to_agent(tid: int, body: dict):
    """Type an attached message's text into the task's live agent session - the person
    answered the very question the agent is waiting on. The 'ask' mode's one click."""
    m = store.get_message(int((body or {}).get('message_id') or 0))
    if not m or m.get('TaskId') != tid: raise HTTPException(404, 'that message is not on this task')
    from . import terminal
    if not terminal.say_to_task(store, tid, m, ACTOR):
        raise HTTPException(422, 'no live agent session on this task - start one and it gets the thread anyway')
    return {'ok': True}

@app.get('/api/calendar/today')
def calendar_today():
    """Today's meetings with who is in them and what they are about - the digest panel's strip."""
    from . import calendar as cal
    try: return cal.today(store)
    except Exception as e: return {'date': None, 'now': None, 'events': [], 'tz': None, 'errors': [str(e)[:200]]}

class MeetingPrepBody(BaseModel):
    """The event as the Timeline panel already has it, plus what the owner wants done about it."""
    subject: str | None = None; start: str | None = None; end: str | None = None
    where: str | None = None; organizer: str | None = None; who: list[str] = []
    about: str | None = None; link: str | None = None; status: str | None = None
    all_day: bool = False
    instruction: str | None = None
    # kept so a page loaded before the switch to the chat assistant still posts cleanly; the
    # prep conversation picks its own provider inside the workspace
    agent: str = 'coder'; model: str | None = None

@app.post('/api/calendar/prep')
def calendar_prep(body: MeetingPrepBody):
    """"Get me ready for this one": the meeting on the Timeline, handed to an agent with your
    own prompt. The invite (when, where, who, what it says) becomes the task's context and your
    prompt is the ask, so the session opens already knowing which meeting it is about.

    It opens the ASSISTANT'S CHAT, not a coding session (owner, 2026-09-01). Getting ready for
    a meeting is reading, checking and thinking - there is no checkout to work in, and a CLI in
    the agent's own folder was the wrong tool wearing the right name. Kind `general` plus the ask
    tag is exactly what the Board and + New create, so the chat opens with the brief already
    asked (website/src/newTask.js, GeneralWorkspace).
    """
    from . import calendar as cal
    subject = (body.subject or 'the meeting').strip()[:120]
    brief = cal.prep_brief(body.dict())
    ask = (body.instruction or '').strip() or 'Get me ready for this meeting.'
    tid = store.create_task({'Title': f'Prep: {subject}'[:200], 'Summary': f'{ask}\n\n{brief}',
                             'Kind': 'general', 'Tags': 'ask:assistant', 'Source': 'calendar',
                             'SourceRef': f"calendar:{body.start or ''}:{subject}"[:200]}, ACTOR)
    store.audit('task', tid, 'create_from_meeting', ACTOR, detail={'subject': subject, 'start': body.start})
    return {'taskId': tid, 'ref': task_ref(tid), 'agent': 'assistant', 'chat': True}

@app.get('/api/calendar/upcoming')
def calendar_upcoming(hours: int = 72, force: bool = False):
    """The Timeline's 'coming up' band: the owner's next events, cached five minutes."""
    from . import calendar as cal
    try: return cal.upcoming(store, max(1, min(hours, 96)), force)
    except Exception as e: return {'events': [], 'tz': None, 'errors': [str(e)[:200]], 'fetched': None}

# ── the funnel: what is being worked, what waits and in what order (rank.py) ────────────
@app.get('/api/funnel')
def funnel(): return rank.funnel(store)

@app.post('/api/funnel/{tid}/pin')
def funnel_pin(tid: int):
    """The owner's override: this one is next. Pinned = top value; it starts at the next free slot."""
    if not any(q['TaskId'] == tid for q in store.queued_dispatches()): raise HTTPException(404, 'that task is not waiting')
    store.set_dispatch_value(tid, rank.PIN, 'pinned by you')
    store.audit('task', tid, 'funnel_pin', ACTOR)
    blackboard.drain_later(store, 0.1)
    return {'ok': True}

@app.post('/api/funnel/{tid}/later')
def funnel_later(tid: int):
    if not any(q['TaskId'] == tid for q in store.queued_dispatches()): raise HTTPException(404, 'that task is not waiting')
    store.set_dispatch_value(tid, rank.LATER, 'pushed back by you')
    store.audit('task', tid, 'funnel_later', ACTOR)
    return {'ok': True}

@app.post('/api/funnel/rerank')
def funnel_rerank(): return {'updated': rank.rerank(store, force=True)}

# ── the waiting room: notes for a working agent, delivered when it stops (waitroom.py) ──
@app.get('/api/tasks/{tid}/waitroom')
def waitroom_list(tid: int):
    if not store.get_task(tid): raise HTTPException(404, 'task not found')
    return {'data': store.waitroom(tid), 'state': waitroom.state(store, tid)[0]}

@app.post('/api/tasks/{tid}/waitroom')
def waitroom_add(tid: int, body: dict):
    """Queue a note for this task's agent. It is typed in the moment the agent parks at its
    prompt - unless it parked on a question for you, which comes first."""
    try: return waitroom.add(store, tid, str((body or {}).get('text') or ''), ACTOR)
    except ValueError as e: raise HTTPException(422, str(e))

@app.post('/api/tasks/{tid}/waitroom/bulk')
def waitroom_bulk(tid: int, body: dict):
    """A pasted list - one prompt per line - becomes that many notes, in order. With the drip on
    (Settings -> Coder agent) each lands as its own turn when the agent stops."""
    try: return waitroom.add_many(store, tid, str((body or {}).get('text') or ''), ACTOR)
    except ValueError as e: raise HTTPException(422, str(e))

_IMG_EXT = {'image/png': 'png', 'image/jpeg': 'jpg', 'image/gif': 'gif', 'image/webp': 'webp'}
IMG_MAX = 12 * 1024 * 1024

@app.post('/api/tasks/{tid}/waitroom/image')
async def waitroom_image(tid: int, request: Request):
    """A screenshot pasted into the Tell-the-agent box, posted as the raw body (no multipart
    dependency, like /api/voice/transcribe). The pty carries text only, so the image goes to
    disk under ~/.taskuary/attachments/waitroom/<task>/ and the NOTE names the file - a coding
    CLI reads images from a path (Claude Code's Read does), which is how it gets to see it."""
    return await _save_prompt_image(tid, request)


async def _save_prompt_image(tid: int, request: Request):
    """Store an image that will be named in a CLI prompt, from either prompt surface."""
    if not store.get_task(tid): raise HTTPException(404, 'task not found')
    mime = (request.headers.get('content-type') or '').split(';')[0].strip().lower()
    ext = _IMG_EXT.get(mime)
    if not ext: raise HTTPException(415, 'paste a PNG, JPEG, GIF or WebP image')
    data = await request.body()
    if not data: raise HTTPException(422, 'no image in the request')
    if len(data) > IMG_MAX: raise HTTPException(413, 'image over 12 MB - crop it')
    d = config.home() / 'attachments' / 'waitroom' / str(tid)
    d.mkdir(parents=True, exist_ok=True)
    p = d / f'{time.strftime("%Y%m%d-%H%M%S")}-{secrets.token_hex(3)}.{ext}'
    p.write_bytes(data)
    store.audit('task', tid, 'waitroom_image', ACTOR, detail={'path': str(p), 'size': len(data)})
    return {'path': str(p), 'size': len(data)}


@app.post('/api/terminals/{sid}/image')
async def terminal_image(sid: str, request: Request):
    """Paste a screenshot into xterm's prompt: save it and return the local path to type."""
    t = hub_term.get(sid)
    if not t: raise HTTPException(404, 'terminal not found')
    if not t.task_id: raise HTTPException(422, 'this terminal is not attached to a task')
    return await _save_prompt_image(t.task_id, request)

@app.delete('/api/tasks/{tid}/waitroom/{wid}')
def waitroom_drop(tid: int, wid: int):
    store.drop_waiting(wid, tid)
    return {'ok': True}

@app.post('/api/reviews/{rid}/release')
def release_review(rid: int):
    """Answer now without waiting for the session. A held draft is one the agent's findings are
    supposed to rewrite - but sometimes the sender just needs telling something today, and a
    reply held behind an agent that never finished is worse than an early one."""
    rv = store.get_review(rid)
    if not rv: raise HTTPException(404, 'review not found')
    if rv['Status'] != 'held': raise HTTPException(422, 'this one is not being held')
    store.unhold_review(rid, 'released by you - answered without waiting for the session')
    store.audit('review', rid, 'release', ACTOR)
    return {'ok': True}

@app.post('/api/reviews/{rid}/draft')
def draft_review(rid: int):
    """(Re)generate the AI draft for a pending review inline. The main AI writes replies -
    a coding CLI is the wrong (and expensive) tool for two sentences of email - unless the
    owner deliberately configured an agent named `responder`. On a review a coder closed,
    the redraft reads its report, so it reports the work instead of promising it."""
    rv = store.get_review(rid)
    if not rv: raise HTTPException(404, 'review not found')
    try:
        draft = responder.write_draft(store, rv['TaskId'], rid, actor=ACTOR)
    except Exception as e:
        raise HTTPException(422, str(e)[:300])
    store.audit('review', rid, 'redraft', ACTOR)
    return {'ok': True, 'draft': draft}

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
    was = store.get_source(fields['SourceId']) if fields.get('SourceId') else None
    sid = store.save_source(fields, ACTOR)
    # SWITCHING SOMETHING ON MUST LOOK BACK. The watermark advances on every poll, including
    # polls that deliberately read nothing from this source (a repo whose issues were 'off',
    # a chat not yet approved) - so flipping it on would otherwise only ever catch what
    # happens NEXT, and everything already sitting there would be invisible forever.
    if was and _woke_up(was, store.get_source(sid)):
        store.rewind_source(sid)
        store.audit('source', sid, 'rewind', ACTOR, detail={'why': 'switched on - the next poll reaches back'})
    from .docsync import sync_connections
    sync_connections(store, ACTOR)
    return {'sourceId': sid}


def _live(src) -> set:
    """What this source is actually set to READ right now: the Active flag plus whichever
    per-kind pickers it carries (github issues/prs, a cloud object's mode)."""
    try: cfg = json.loads(src.get('ConfigJson') or '{}')
    except ValueError: cfg = {}
    if not src.get('Active'): return set()
    return {f'{k}:{cfg[k]}' for k in ('issues', 'prs', 'mode')
            if cfg.get(k) in ('tasks', 'feed')} or ({'active'} if not cfg else set())


def _woke_up(before, after) -> bool:
    """Did this save turn something ON that was off? (Never the reverse - switching a repo
    off must not rewind anything.)"""
    return bool(_live(after) - _live(before))

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

@app.get('/api/reports/last-runs')
def report_last_runs():
    """What each report's last run did - when, how long, what it read, what came out (reports.last_runs)."""
    from .reports import last_runs
    return {'data': last_runs(store)}

@app.get('/api/reports/{sid}/runs')
def report_runs(sid: int, limit: int = 60):
    """A report's run history, newest first, without the inputs (store.report_runs) - the Reports tab's
    History; one run whole, inputs and all, is /api/reports/runs/{rid}."""
    if not store.get_source(sid): raise HTTPException(404, 'source not found')
    return {'data': store.report_runs(sid, min(max(1, limit), 200))}

@app.get('/api/reports/runs/{rid}')
def report_run(rid: int):
    r = store.get_report_run(rid)
    if not r: raise HTTPException(404, 'run not found')
    return r

@app.get('/api/report-types')
def report_types():
    return {'data': [{'type': t, 'status': 'planned' if t in PLANNED else 'builtin'} for t in REGISTRY]}

@app.get('/api/problems')
def problems_now():
    """What is failing right now, for the bell in the top bar (problems.py): each with where to fix it."""
    from . import problems
    return {'data': problems.collect(store)}

@app.get('/api/connectors')
def connectors():
    """Channel connector cards (outlook / teams / github). Secrets are write-only.
    ScopeDefault rides along so the card can show what an unset Authority actually means -
    which is per type (winrm starts at admin, a tracker at read), not one global floor."""
    from . import scopes
    return {'data': [c | {'ScopeDefault': scopes.default_scope(c['Type'])} for c in store.list_connectors()]}

@app.get('/api/scopes')
def scope_catalog():
    """The Authority dropdown: the three levels, and for each the actions it unlocks - so the
    card can say what changes when you move it instead of leaving the owner to guess."""
    from . import scopes
    return {'data': [{'value': s, 'actions': scopes.actions_at(s),
                      'gains': sorted(a for a, need in scopes.ACTIONS.items() if need == s)}
                     for s in scopes.SCOPES],
            'defaults': scopes.DEFAULT_SCOPE}

@app.get('/api/brains')
def brains():
    """Everything that could do intent triage: cloud AI connectors with a key, plus your
    CLI agents (same brain that codes). Value goes into the `triage_ai` setting."""
    from .llm import AI_TYPES
    # no steering: auto is one option among equals, and which brain triages is the owner's call
    out = [{'value': '', 'label': 'auto — first active AI connector', 'kind': 'auto', 'ready': True}]
    out += [{'value': f"connector:{c['ConnectorId']}", 'label': c['Name'], 'kind': 'api',
             'ready': bool(c['Active'] and (c['HasSecret'] or c['Type'] == 'ollama'))}   # local models carry no key
            for c in store.list_connectors() if c['Type'] in AI_TYPES]
    # named by WHAT RUNS, leading with the CLI ('claude · coder'): the profile name is the
    # detail, not the identity - 'coder' says nothing about which model family answers.
    # Each entry also carries its known model choices, so pickers offer a dropdown instead
    # of a spelling test (free typing still allowed for models we don't know about).
    CONN_MODELS = {'anthropic': ['claude-opus-5', 'claude-sonnet-5', 'claude-haiku-4-5'],
                   'openai': ['gpt-4o-mini'],
                   'openrouter': ['openrouter/auto', 'meta-llama/llama-3.3-70b-instruct']}
    for o in out:
        if o['kind'] == 'api':
            c = store.get_connector(int(o['value'][10:]))
            o['models'] = CONN_MODELS.get((c or {}).get('Type'), [])
    def _cli_of(a):
        prof = cfg.get('agents', {}).get(a['Name']) or json.loads(a.get('Config') or '{}')
        return cli_base(prof.get('cmd') or a['Name'])
    out += [{'value': f"cli:{a['Name']}",
             'label': (_cli_of(a) + (f" · {a['Name']}" if _cli_of(a) != a['Name'] else '')) + ' (your CLI)',
             'kind': 'cli', 'ready': True, 'models': CLI_MODELS.get(_cli_of(a), [])}
            for a in store.list_agents()]
    current = store.get_settings().get('triage_ai') or ''
    # Old settings named a type (connector:anthropic). Keep accepting that in llm.py, but
    # point the picker at the concrete instance it currently resolves to.
    if current.startswith('connector:') and not current[10:].isdigit():
        old = store.get_connector_by_type(current[10:])
        if old: current = f"connector:{old['ConnectorId']}"
    return {'data': out, 'current': current}

@app.post('/api/connectors')
def save_connector(body: ConnectorBody):
    fields = {k: (int(v) if k == 'Active' else v) for k, v in body.dict().items() if v is not None}
    if fields.get('Name') is not None:
        fields['Name'] = fields['Name'].strip()
        if not fields['Name']: raise HTTPException(422, 'connector name cannot be blank')
    if fields.get('Roles') is not None:
        bad = {r for r in fields['Roles'].split(',') if r} - set(store_mod.ROLES)
        if bad: raise HTTPException(422, f"unknown role(s): {', '.join(sorted(bad))}")
    if fields.get('Scope') is not None:
        from . import scopes
        if fields['Scope'] not in scopes.SCOPES:
            raise HTTPException(422, f"unknown authority: {fields['Scope']} - one of {', '.join(scopes.SCOPES)}")
    if not fields.get('ConnectorId') and not (fields.get('Type') and fields.get('Name')):
        raise HTTPException(422, 'new connectors need Type and Name')
    if not fields.get('ConnectorId'):
        # New instances start with the normal role for their type, but never inherit credentials,
        # cursors, sources or test state from the card they were added beside.
        fields.setdefault('Roles', store_mod.DEFAULT_ROLES.get(fields['Type'], ''))
    current = store.get_connector(fields['ConnectorId']) if fields.get('ConnectorId') else None
    typ = fields.get('Type') or (current or {}).get('Type')
    name = fields.get('Name') or (current or {}).get('Name')
    if typ and name and any(c['Name'].casefold() == name.casefold()
                            and c['ConnectorId'] != fields.get('ConnectorId')
                            for c in store.connectors_by_type(typ)):
        raise HTTPException(409, f'a {typ} connector named {name!r} already exists')
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

# ── Voice (taskuary/voice.py): speech to text for the funnel and for the prompt box ──
@app.get('/api/voice/status')
def voice_status():
    from . import voice
    return voice.ready(store)

@app.get('/api/voice/vocabulary')
def voice_vocabulary():
    from . import voice
    return {'terms': voice.vocabulary(store), 'limit': voice.VOCAB_MAX}

@app.put('/api/voice/vocabulary')
def voice_vocabulary_save(body: dict):
    from . import voice
    try: terms = voice.save_vocabulary(store, body.get('terms'), ACTOR)
    except ValueError as e: raise HTTPException(422, str(e))
    store.audit('setting', 0, 'voice_vocabulary', ACTOR, detail={'count': len(terms)})
    return {'terms': terms, 'limit': voice.VOCAB_MAX}

@app.post('/api/voice/transcribe')
async def voice_transcribe(request: Request):
    """A clip from the browser's microphone, posted as the raw body (no multipart dependency):
    the text comes back and goes wherever the prompt box goes."""
    from . import voice
    data = await request.body()
    if not data: raise HTTPException(422, 'no audio in the request')
    mime = (request.headers.get('content-type') or 'audio/webm').split(';')[0].strip()
    try: return voice.transcribe(store, data, mime, f'clip.{voice.ext_for(mime)}')
    except RuntimeError as e: raise HTTPException(409, str(e))
    except requests.RequestException as e: raise HTTPException(502, f'could not reach the transcription service: {str(e)[:160]}')

@app.post('/api/messages/{mid}/transcribe')
def message_transcribe(mid: int):
    """A voice note that landed untranscribed (no connector at the time): the audio is attached,
    so it is transcribed now and the body replaced."""
    from . import voice
    try: out = voice.transcribe_message(store, mid)
    except RuntimeError as e: raise HTTPException(409, str(e))
    store.audit('message', mid, 'transcribed', ACTOR, detail={'provider': out['provider']})
    return out

@app.get('/api/connectors/{cid}/mail/folders')
def mail_folder_list(cid: int, mailbox: str):
    """A mailbox's folders, for the Mailboxes step: which ones this source reads (Inbox by default)."""
    from .channels import graph_token, mail_folders
    c = store.get_connector(cid, with_secret=True)
    if not c or c['Type'] != 'outlook': raise HTTPException(404, 'folders are an Outlook card thing')
    try:
        tok = graph_token({**json.loads(c.get('ConfigJson') or '{}'), '_cid': cid}, c.get('Secret'))
        return {'data': mail_folders(tok, mailbox)}
    except requests.HTTPError as e: raise HTTPException(502, f'Graph refused the folder list: {str(e)[:160]}')
    except RuntimeError as e: raise HTTPException(409, str(e))

@app.get('/api/connectors/{cid}/wa/status')
def wa_status(cid: int):
    """Paired or not - the pairing QR as an SVG for the card to draw (messengers.wa_status), and
    what Taskuary's own bridge manager is doing (installing, starting, running, failed)."""
    from .messengers import wa_status as _status
    from . import wabridge
    c = store.get_connector(cid, with_secret=True)
    if not c or c['Type'] != 'whatsapp': raise HTTPException(404, 'not a WhatsApp connector')
    # node: the one thing the card cannot install for the owner - step 1 of the pairing box turns on it
    try: return {**_status(c), 'bridge': True, 'node': True, 'manager': wabridge.state()}
    except RuntimeError as e: return {'connected': False, 'bridge': False, 'node': bool(wabridge.node()), 'detail': str(e), 'manager': wabridge.state()}   # bridge down is a state, not a 500

@app.post('/api/connectors/{cid}/wa/bridge/start')
def wa_bridge_start(cid: int, force_install: bool = False):
    """Install the bridge's dependency if needed and start it detached - the card's button and the
    setup agent's verb, instead of a shell command that never returns (wabridge.py)."""
    from . import wabridge
    c = store.get_connector(cid)
    if not c or c['Type'] != 'whatsapp': raise HTTPException(404, 'not a WhatsApp connector')
    store.audit('connector', cid, 'wa_bridge_start', ACTOR)
    return wabridge.start(force_install)

@app.post('/api/connectors/{cid}/wa/bridge/stop')
def wa_bridge_stop(cid: int):
    from . import wabridge
    return wabridge.stop()

@app.post('/api/connectors/{cid}/wa/bridge/restart')
def wa_bridge_restart(cid: int):
    """Stop the running bridge (ours or one started by hand - found by its port) and start the one on
    disk: how a paired bridge picks up newer bridge code without the owner touching a shell."""
    from . import wabridge
    c = store.get_connector(cid)
    if not c or c['Type'] != 'whatsapp': raise HTTPException(404, 'not a WhatsApp connector')
    store.audit('connector', cid, 'wa_bridge_restart', ACTOR)
    return wabridge.restart()

@app.get('/api/connectors/{cid}/wa/chats')
def wa_chats(cid: int):
    """The chats the WhatsApp bridge has seen - to pick 'only these' as sources (messengers.wa_chats)."""
    from .messengers import wa_chats as _chats
    c = store.get_connector(cid, with_secret=True)
    if not c or c['Type'] != 'whatsapp': raise HTTPException(404, 'not a WhatsApp connector')
    try: return {'data': _chats(c)}
    except RuntimeError as e: raise HTTPException(409, str(e))

# ── Get AI to set it up (taskuary/aisetup.py): the card's guide as the agent's prompt, live on the card ──
@app.post('/api/connectors/{cid}/ai-setup')
def connector_ai_setup(cid: int, body: AiSetupBody):
    c = store.get_connector(cid)
    # WhatsApp pairs itself (Node check, bridge auto-start, QR on the card); an agent here only sat on the bridge process
    if c and c['Type'] == 'whatsapp': raise HTTPException(422, 'WhatsApp needs no agent: the Pair with your phone box does the setup itself')
    try: return aisetup.start(store, cfg['server'], cid, body.guide, body.fields, body.secret_label, body.agent, body.model, ACTOR, body.agent_steps)
    except (ValueError, RuntimeError, FileNotFoundError) as e: raise HTTPException(422, str(e))

@app.get('/api/connectors/{cid}/ai-setup')
def connector_ai_setup_live(cid: int):
    """Reattach: the card reloads, the agent is still there."""
    return {'session': aisetup.live_for(store, cid)}

# ── Sign in with Microsoft (taskuary/msauth.py): Graph for a regular user, no Azure portal ──
_MSFLOWS = {}   # flow id -> the device code being polled; one browser tab, minutes, then gone

@app.post('/api/connectors/{cid}/ms/signin')
def ms_signin(cid: int):
    """Start the device-code sign-in: the code and URL to show, and a flow id to poll with."""
    import secrets as _secrets
    from . import msauth
    c = store.get_connector(cid)
    if not c or c['Type'] != 'outlook': raise HTTPException(404, 'Sign in with Microsoft lives on the Outlook card')
    cfg = json.loads(c.get('ConfigJson') or '{}')
    try: d = msauth.device_start(cfg)
    except RuntimeError as e: raise HTTPException(409, str(e))
    except requests.RequestException as e: raise HTTPException(502, f'could not reach login.microsoftonline.com: {str(e)[:160]}')
    flow = _secrets.token_urlsafe(12)
    for k, v in list(_MSFLOWS.items()):
        if time.time() - v['at'] > 1800: _MSFLOWS.pop(k, None)
    _MSFLOWS[flow] = {'cid': cid, 'device_code': d.pop('device_code'), 'cfg': cfg, 'at': time.time()}
    return {'flow': flow, **d}

@app.post('/api/connectors/{cid}/ms/poll')
def ms_poll(cid: int, body: dict):
    """One poll of a sign-in. pending until the user finishes in the browser; then the card is
    connected as them: refresh token saved as the secret, their mailbox added as the source."""
    from . import msauth
    flow = (body or {}).get('flow')
    f = _MSFLOWS.get(flow)
    if not f or f['cid'] != cid: raise HTTPException(404, 'no such sign-in in progress - start it again')
    try: t = msauth.device_poll(f['cfg'], f['device_code'])
    except msauth.AdminConsent as e:
        _MSFLOWS.pop(flow, None)
        return {'status': 'error', 'detail': str(e), 'admin_consent_url': msauth.admin_consent_url(f['cfg'])}
    except RuntimeError as e:
        _MSFLOWS.pop(flow, None)
        return {'status': 'error', 'detail': str(e)}
    if t.get('pending'): return {'status': 'pending'}
    _MSFLOWS.pop(flow, None)
    if not t.get('refresh_token'):
        return {'status': 'error', 'detail': 'Microsoft returned no refresh token - the offline_access scope was not granted'}
    who = msauth.me(t['access_token'])
    cfg = {**f['cfg'], 'auth': 'user', 'account': who['account'], 'name': who['name']}
    store.save_connector({'ConnectorId': cid, 'ConfigJson': json.dumps(cfg), 'Secret': t['refresh_token'], 'Active': 1}, ACTOR)
    if who['account'] and not any(s['Channel'] == 'email' and (s['Address'] or '').lower() == who['account'].lower()
                                  for s in store.list_sources(active_only=False)):
        store.save_source({'Channel': 'email', 'Address': who['account'], 'ConnectorId': cid, 'Active': 1}, ACTOR)
    store.audit('connector', cid, 'ms_signin', ACTOR, detail={'account': who['account']})
    from .docsync import sync_connections
    sync_connections(store, ACTOR)
    # signed in = connected: the first sync starts now, so mail is on the Timeline by the time
    # the card has finished saying "signed in" - not ten minutes later, or never until Sync now
    threading.Thread(target=_poll_reports, kwargs={'what': 'syncing'}, daemon=True).start()
    return {'status': 'ok', **who, 'syncing': True}

@app.get('/api/connectors/{cid}/ms/adminlink')
def ms_adminlink(cid: int):
    """The admin-approval link on demand - for the person who knows in advance that IT has to say yes."""
    from . import msauth
    c = store.get_connector(cid)
    if not c or c['Type'] != 'outlook': raise HTTPException(404, 'Sign in with Microsoft lives on the Outlook card')
    try: return {'url': msauth.admin_consent_url(json.loads(c.get('ConfigJson') or '{}'))}
    except RuntimeError as e: raise HTTPException(409, str(e))

@app.post('/api/connectors/{cid}/ms/signout')
def ms_signout(cid: int):
    """Forget the sign-in: the refresh token goes, the card turns off, admin fields stay."""
    c = store.get_connector(cid)
    if not c: raise HTTPException(404, 'connector not found')
    cfg = json.loads(c.get('ConfigJson') or '{}')
    for k in ('auth', 'account', 'name'): cfg.pop(k, None)
    store.save_connector({'ConnectorId': cid, 'ConfigJson': json.dumps(cfg), 'Secret': '', 'Active': 0}, ACTOR)
    store.audit('connector', cid, 'ms_signout', ACTOR, detail={'type': c['Type']})
    from .docsync import sync_connections
    sync_connections(store, ACTOR)
    return {'ok': True}

@app.post('/api/platform/macos/open-settings')
def macos_open_settings(body: dict):
    """Open one of two System Settings panes the Apple Messages card walks the owner through.
    The pane is an enum mapped to a fixed URL on this side - the browser never sends a URL."""
    from . import imessage
    pane = (body or {}).get('pane')
    if pane not in imessage.PANES: raise HTTPException(422, f'unknown pane: {pane}')
    try: return imessage.open_settings(pane)
    except imessage.SetupError as e: return {'ok': False, 'detail': str(e), 'setup': e.setup}

@app.post('/api/platform/macos/probe')
def macos_probe(body: dict):
    """The Automation consent check: a non-sending Apple Event to Messages.app. Run only after
    the card has explained that macOS is about to ask - nothing is sent either way."""
    from . import imessage
    what = (body or {}).get('what')
    if what != 'messages_automation': raise HTTPException(422, f'unknown probe: {what}')
    try: return imessage.automation_probe()
    except imessage.SetupError as e: return {'ok': False, 'detail': str(e), 'setup': e.setup}
    except Exception as e: return {'ok': False, 'detail': str(e)[:500]}

@app.post('/api/tools/run')
def tool_run(body: dict):
    """The agents' hands on your other systems: run ONE query/script through a connection
    the owner marked as a tool, and get the raw output back (no AI pass, no timeline row).
    Same executors the Reports tab uses, same saved credentials - so an agent working a
    task can look something up in SQL Server, run a script on a box, or call an MCP tool.
    Catalog cards exist from first launch (winrm/mssql already have the tool role in
    DEFAULT_ROLES) even when the owner never connected them - off means off. A connection
    without the 'tool' role also refuses, and so does one whose Authority sits below what
    the executor needs - running PowerShell on a box is 'admin', reading a table is 'read'."""
    t = (body or {}).get('type')
    if t not in REGISTRY: raise HTTPException(422, f'unknown tool type: {t}')
    from .reports import card_of
    from . import scopes
    connector_id = (body or {}).get('connector_id')
    try: conn = store.get_connector(int(connector_id)) if connector_id else store.get_connector_by_type(card_of(t))
    except (TypeError, ValueError): raise HTTPException(422, 'connector_id must be a number')
    if conn and conn.get('Type') != card_of(t):
        raise HTTPException(422, f'connector {connector_id} is {conn.get("Type")}, not {card_of(t)}')
    if conn:
        if not conn.get('Active'):
            raise HTTPException(403, f'the {t} connection is off - turn it on under Connections')
        if 'tool' not in store_mod.roles_of(conn):
            raise HTTPException(403, f'the {t} connection is not marked as an agent tool (Connections → {t} → Role)')
        try:
            scopes.require(conn, t)
        except PermissionError as e:
            store.audit('tool', conn['ConnectorId'], 'run_refused', ACTOR, detail={'type': t, 'scope': scopes.scope_of(conn)})
            raise HTTPException(403, str(e))
    try:
        head, out = REGISTRY[t](resolve_cfg(store, {**body, 'type': t}))
    except Exception as e:
        store.audit('tool', (conn or {}).get('ConnectorId', 0), 'run_failed', ACTOR, detail={'type': t, 'error': str(e)[:300]})
        return {'ok': False, 'error': str(e)[:1000]}
    store.audit('tool', (conn or {}).get('ConnectorId', 0), 'run', ACTOR, detail={'type': t, 'headline': str(head)[:200]})
    return {'ok': True, 'headline': head, 'output': (out or '')[:20000]}

@app.post('/api/reports/compose')
def report_compose(body: dict):
    """Say what you want in English; get a report config back, or the questions that stand
    between here and one. Nothing is saved - the answer goes into the same builder the owner
    would have filled in by hand, and Preview runs it for real before anything is scheduled."""
    from .compose import compose
    out = compose(store, (body or {}).get('ask') or '', _llm(), (body or {}).get('answers'))
    if out.get('config'):
        store.audit('report', 0, 'compose', ACTOR, detail={'ask': ((body or {}).get('ask') or '')[:300],
                                                           'type': out['config'].get('type'),
                                                           'confidence': out.get('confidence')})
    return out

@app.get('/api/intacct/fields')
def intacct_object_fields(obj: str, connector_id: int = None):
    """What this company's copy of an Intacct object actually carries, custom fields and all.

    "I don't know what fields off hand Intacct has set up" is not a question anybody should answer
    from memory - Sage knows, the lookup call is cheap, and a hardcoded field list is wrong the day
    somebody adds a field. The source card asks this and the owner clicks the ones they want."""
    from .intacct import fields_of
    from .reports import intacct_connection
    try: return {'ok': True, 'data': fields_of(intacct_connection(store, connector_id), (obj or '').strip())}
    except Exception as e: return {'ok': False, 'error': str(e)[:500]}

@app.post('/api/reports/compose-sources')
def report_compose_sources(body: dict):
    """Say what a check should READ; get the source cards back. The step below /compose: no title,
    no schedule, just the part of the form that needs knowing an object name or a field id.

    This is what the Assistant's Pipeline step calls - and what a single source card calls with its
    own type in `type`, so "AP bills due in the next 30 days" comes back as the object, the fields
    this company's Intacct actually has, and the filter."""
    from .compose import compose_sources
    b = body or {}
    out = compose_sources(store, b.get('ask') or '', _llm(), (b.get('type') or '').strip() or None, b.get('answers'))
    if out.get('sources'):
        store.audit('report', 0, 'compose_sources', ACTOR,
                    detail={'ask': (b.get('ask') or '')[:300], 'confidence': out.get('confidence'),
                            'types': [s.get('type') for s in out['sources']]})
    return out

@app.post('/api/reports/preview')
def report_preview(body: dict):
    """Dry-run a report config - executor plus the AI pass when ai_prompt is set -
    without filing a row. Exactly what a scheduled run would produce."""
    try:
        head, summary = render_report(store, body, _llm() if body.get('ai_prompt') else None)
        # the chart is half of what a scheduled run hands back, so the dry run has to show it -
        # rendered in memory here, since a preview files no message to hang an attachment on
        from .artifacts import chart_directive, rows_from_body, strip_directive, to_svg_chart
        svg, rows = '', rows_from_body(summary)
        if rows and str(store.get_settings().get('report_images_enabled') or '1') == '1':
            val, lab, ctitle = chart_directive(summary)
            svg = to_svg_chart(rows, None, ctitle or body.get('title') or head, val, lab) or ''
        return {'ok': True, 'headline': head, 'summary': strip_directive(summary)[:4000],
                'rows': len(rows), 'chart': svg}
    except Exception as e:
        return {'ok': False, 'error': str(e)[:500]}

class SetupBody(BaseModel): dismissed: bool

@app.get('/api/cli/detect')
def cli_detect():
    """The AI CLIs on this machine. Most people already pay for one and have no separate API key,
    so the wizard offers what they have before it asks for a key."""
    from . import clis
    return {'data': clis.detect(store), 'tools': clis.tools()}    # tools: optional helpers (agent-browser), never offered as agents

@app.get('/api/setup')
def setup_state():
    """What still stands between this install and a working funnel, read off real state - so a
    step un-does itself if the connection behind it is removed."""
    from . import setup as setup_mod
    return setup_mod.state(store)

@app.post('/api/setup/dismiss')
def setup_dismiss(body: SetupBody):
    """"I know, leave me alone." A setting, so it stays dismissed across restarts - and it is
    reversible, because a checklist you cannot get back is a worse trap than one you cannot hide."""
    from . import setup as setup_mod
    store.set_setting(setup_mod.DISMISSED, '1' if body.dismissed else '0', ACTOR)
    store.audit('setting', 0, 'setup_dismiss' if body.dismissed else 'setup_reopen', ACTOR)
    return {'ok': True, **setup_mod.state(store)}

@app.get('/api/aws/catalog')
def aws_catalog(service: str = None):
    """The services and operations a report source can name, read off botocore's own models -
    so the two fields that used to be free text with an example in the placeholder can be
    picked from instead of remembered."""
    try:
        from .aws import catalog
        return catalog(store, service)
    except Exception as e:
        return {'seen': [], 'services': [], 'operations': [], 'error': str(e)[:300]}

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
        return {'ok': False, 'error': 'pyodbc is not installed - run: pip install pyodbc'}

# Models each CLI can be pointed at. The agent profile's own `model` (Connections → AI CLI
# agents) always wins as the default; these are the quick picks the run dialogs offer.
CLI_MODELS = {
    'claude': ['opus', 'sonnet', 'haiku', 'claude-opus-5', 'claude-sonnet-5', 'claude-haiku-4-5'],
    'codex': ['gpt-5-codex', 'gpt-5'],
    'gemini': ['gemini-2.5-pro', 'gemini-2.5-flash'],
}

def cli_base(cmd) -> str:
    """'C:\\Users\\me\\...\\codex.exe' and 'codex' are the same CLI. A profile saved with the full
    path (the setup wizard writes what `where` found) offered no model list at all."""
    # both separators: a Windows path in a profile is still codex when the tests run on Linux CI
    return re.sub(r'\.(cmd|exe|bat|ps1)$', '', re.split(r'[\\/]', str(cmd or ''))[-1].lower())

@app.get('/api/agents')
def agents():
    """data = store rows (for dispatch pickers); config = the editable profiles;
    models = the quick-pick model list per agent, keyed by agent name."""
    def _models(a):
        from . import climodels
        prof = json.loads(a.get('Config') or '{}')
        cli = cli_base(prof.get('cmd'))
        cat = climodels.catalog(cli)                       # codex: its own /model list off disk; others: the built-in aliases
        return {'cmd': prof.get('cmd'), 'cli': cli, 'default': prof.get('model'), 'choices': cat['choices'] or CLI_MODELS.get(cli, []),
                'models': cat['models'], 'current': cat['current'], 'source': cat['source']}
    # the default agent (a setting) comes FIRST: every picker's initial value is the head of
    # this list, so "which CLI opens when I hit Start session" is decided in one place
    # ...and "the default" is the one that can actually run: shipping coder=claude means a
    # machine with only codex installed had every dispatch aimed at a CLI nobody had.
    head = hub_agents.default_agent(store)
    rows = sorted(store.list_agents(), key=lambda a: a['Name'] != head)
    profs = hub_agents.profiles(store)
    return {'data': [{**a, 'installed': hub_agents.runs_here(profs.get(a['Name']) or {})} for a in rows],
            'config': cfg.get('agents', {}), 'default': head,
            'models': {a['Name']: _models(a) for a in store.list_agents()}}

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
def get_doc(name: str):
    """Raw for the editor, rendered so you can see what an agent will actually read."""
    return {'name': name, 'content': store.get_doc(name) or '', 'rendered': store.doc(name) or '',
            'owner': store.owner()}

@app.put('/api/doc/{name}')
def put_doc(name: str, body: DocBody):
    store.save_doc(name, body.content, ACTOR)
    return {'ok': True}

@app.get('/api/learned/graph')
def learned_graph():
    """LEARNED.md as a picture: lines, the verdicts that fed them, each line's score over time,
    the lines that died - the Docs tab's Visualize view (discussion #27)."""
    return learnedgraph.graph(store)

class AdoptBody(BaseModel): key: str

@app.post('/api/learn/adopt')
def learn_adopt(body: AdoptBody):
    try: return learn.adopt(store, body.key, ACTOR)
    except ValueError as e: raise HTTPException(404, str(e))

@app.get('/api/doc/generate/status')
def doc_generate_status():
    """Live progress + receipts for a running (or the last) generate-from-history: what is
    being read right now, and afterwards the exact evidence handed to the model."""
    from .histgen import STATUS
    return STATUS

# ── SOUL.md from a short interview (interview.py) ────────────────────────────────────────
class InterviewBody(BaseModel):
    answers: dict = {}

@app.get('/api/soul/interview')
def soul_questions():
    """The questions, and what the app can already see - so it never asks what it can read."""
    from . import interview
    return {'questions': interview.QUESTIONS, 'context': interview.context(store),
            'current': (store.get_doc('soul') or '')[:400], 'owner': store.owner()}

@app.post('/api/soul/interview')
def soul_write(body: InterviewBody):
    """Their answers in, SOUL.md out - saved, and theirs to edit like any other document."""
    from . import interview
    try: return {'doc': interview.write(store, body.answers or {}, ACTOR)}
    except ValueError as e: raise HTTPException(422, str(e))

@app.post('/api/doc/{name}/generate')
def doc_generate(name: str, days: int = 90):
    """The Docs tab's 'Generate from history': read the last N days of the mailbox itself
    (sent + inbox over Graph; Taskuary's own record when no Graph mailbox is connected),
    distill it, and fill the doc's marked block. Slow by nature - one or two Graph sweeps
    plus an AI pass - the button shows it working."""
    from . import histgen
    try:
        detail = histgen.generate(store, name, days)
    except Exception as e:
        raise HTTPException(400, str(e)[:400])
    store.audit('doc', 0, 'generate_from_history', ACTOR, detail={'doc': name, 'source': detail})
    return {'ok': True, 'detail': detail}

@app.post('/api/learn/reflect')
def learn_reflect():
    """Consolidate LEARNED.md now instead of waiting for the threshold - the Docs page's
    'Reflect now'. False means there was no AI brain or nothing usable came back; the doc
    is never replaced with a worse one."""
    ok = learn.reflect(store)
    if ok: store.audit('doc', 0, 'reflect', ACTOR)
    return {'ok': True, 'reflected': ok}

class OwnerBody(BaseModel): name: str; email: str | None = None

@app.get('/api/owner')
def get_owner(): return {**store.owner(), 'tokens': list(store_mod.DOC_TOKENS)}

# ── About you (taskuary/whoami.py): what the system knows about its owner, in one place ──
@app.get('/api/whoami')
def whoami():
    from . import whoami as _w
    return _w.profile(store)

@app.patch('/api/whoami')
def whoami_save(body: dict):
    """The manual facts (phone, handles, title, bio, avatar choice) - plain whitelisted settings.
    Name and email keep going through PUT /api/owner, which retokens the docs."""
    from . import whoami as _w
    try: out = _w.save(store, body or {}, ACTOR)
    except ValueError as e: raise HTTPException(422, str(e))
    store.audit('setting', 0, 'profile', ACTOR, detail={'fields': sorted((body or {}).keys())})
    return out

@app.get('/api/whoami/avatar')
def whoami_avatar(style: str = 'monogram', seed: str = '', name: str = ''):
    """A preview: the same deterministic SVG the profile shows, for a style and seed not saved yet."""
    from . import whoami as _w
    if style not in _w.STYLES: raise HTTPException(422, f'style must be one of {", ".join(_w.STYLES)}')
    nm = name or (store.owner().get('owner') if store.owner().get('owner') != 'the owner' else '')
    return {'svg': _w.avatar_svg(nm, seed or nm or 'taskuary', style), 'style': style, 'seed': seed or nm or 'taskuary'}

@app.put('/api/owner')
def put_owner(body: OwnerBody):
    """Your name, in ONE place. SOUL.md and CODER.md refer to the owner nine times between them,
    so typing it in changed one of them and left a document that half called you by name and half
    called you John Smith. Saving here rewrites every literal occurrence of the OLD name into a
    {{owner}} token, so the documents convert themselves once and never drift again."""
    new = (body.name or '').strip()
    if not new: raise HTTPException(422, 'a name is required')
    was = store.owner()
    changed = []
    # 'the owner' is the fallback when no name is known, and real prose says those words -
    # retokenizing them would punch {{owner}} holes all over a doc that never had a name in it
    if was['owner'] in ('the owner', '') or '{{' in was['owner']: was = {**was, 'owner': '', 'owner_email': ''}
    for doc in ('soul', 'coder', 'digest', 'learned', 'triage', 'style', 'counsel'):
        raw = store.get_doc(doc)
        if not raw: continue
        tokened = store_mod.retoken_doc(raw, was['owner'], was['owner_email'])
        # a drifted doc holds BOTH names - the one you typed in and the template's John Smith
        # the edit missed - so the shipped placeholder is always swept too
        tokened = store_mod.retoken_doc(tokened, 'John Smith', 'john.smith@example.com')
        if tokened != raw:
            store.save_doc(doc, tokened, ACTOR)
            changed.append(doc)
    store.set_setting('owner_name', new, ACTOR)
    if body.email is not None: store.set_setting('owner_email', body.email.strip(), ACTOR)
    store.audit('doc', 0, 'set_owner', ACTOR, detail={'from': was['owner'], 'to': new, 'retokened': changed})
    return {**store.owner(), 'retokened': changed}

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

@app.delete('/api/policies/{pid}')
def delete_policy(pid: int):
    """Gone, not just off. The rules "Not a task" writes by itself pile up, and a wrong one
    could only ever be switched off - the list kept every mistake. A skip rule's hidden history
    comes back first, exactly as switching it off would have done."""
    p = next((x for x in store.list_policies(active_only=False) if x['PolicyId'] == pid), None)
    if not p: raise HTTPException(404, 'policy not found')
    shown = policy_engine.apply_retroactively(store, {**p, 'Active': 0})
    store.delete_policy(pid)
    store.audit('policy', pid, 'delete', ACTOR, detail={'name': p.get('Name'), 'restored': shown})
    return {'ok': True, 'restored': shown}

@app.get('/api/memory')
def memory(): return {'data': store.list_memories(active_only=False)}

@app.post('/api/memory')
def add_memory(body: MemoryBody):
    # 'subject' was missing here, so a topic rule - which is what most verdicts actually are -
    # could only be written by pressing "Not our task" on a message, never typed in by hand
    if body.scope not in ('global', 'sender', 'sender_domain', 'source', 'subject'):
        raise HTTPException(422, 'bad scope')
    # a keyed scope with no key matches nothing, ever: saved, listed, and silent
    if body.scope != 'global' and not (body.scope_key or '').strip():
        raise HTTPException(422, f'a {body.scope} note needs a scope_key to match on')
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

_POLL_BUSY = threading.Lock()   # whether a poll runs IN THIS PROCESS; the DB flag is only for the UI
_LAST_POLL = [time.time()]      # startup's own catch-up counts as the first one
POLL_TICK = 30                  # how often the loop wakes to look at the clock


def poll_forever():
    """The ten-minute sync the Timeline has always PROMISED - made by the server, at last.

    It used to be the BROWSER'S: a setInterval living inside the Timeline tab. So it stopped
    the moment you opened Board or Tasks, because that tab unmounts; it restarted its ten-minute
    countdown every time a filter changed the effect's dependencies; and with no window open
    nothing polled at all - which also meant a report scheduled for 8am Monday only ran if
    somebody happened to have the Timeline on screen at 8am on Monday. The mailbox does not care
    which tab is open, so the clock does not live there any more."""
    while True:
        try:
            try: mins = int(store.get_settings().get('poll_minutes') or 0)
            except (TypeError, ValueError): mins = 10
            if mins > 0 and time.time() - _LAST_POLL[0] >= mins * 60:
                _poll_reports(0, what='syncing')
            elif mins > 0:
                # poll_minutes 0 is "background sync off", and that includes the fast clock
                quick = _quick_due()
                if quick: _poll_reports(0, what='syncing', only=quick)
        except Exception as e:
            logger.warning(f'scheduled poll failed: {e}')      # a bad cycle must not end the loop
        time.sleep(POLL_TICK)


# A chat channel on the ten-minute mailbox clock is a slow conversation. A connector whose
# config carries poll_seconds asks to be read more often than poll_minutes, on its own - the
# quick pass polls ONLY those connectors and runs no reports or CI, so the expensive ones stay
# on the global clock. Granularity is POLL_TICK.
_QUICK_LAST = {}

def _quick_due() -> list:
    due = []
    for c in store.list_connectors():
        if not c['Active']: continue
        try:
            cfg = json.loads(c.get('ConfigJson') or '{}')
            secs = int(cfg.get('poll_seconds') or 0) if isinstance(cfg, dict) else 0
        except (TypeError, ValueError): secs = 0
        if secs > 0 and time.time() - _QUICK_LAST.get(c['Type'], 0) >= secs:
            due.append(c['Type'])
    return due

def _poll_reports(backfill_days: int = 0, what: str = 'syncing', startup: bool = False, only=None):
    # one poll at a time, enforced by a lock instead of the old 10-minute timestamp guard: a
    # slow catch-up (CLI triage over a 3-day backfill) legitimately outlives 10 minutes, so
    # the timeline's auto-sync kept starting SECOND polls over the same watermarks - each one
    # rewriting 'running', and the "catching up" banner never ended.
    if not _POLL_BUSY.acquire(blocking=False):
        logger.info('poll already running - skipped'); return
    if only is None:
        _LAST_POLL[0] = time.time()  # a manual Sync now resets the clock too, so the timer
                                     # does not fire again moments later over the same watermarks
    else:
        for t in only: _QUICK_LAST[t] = time.time()
    store.set_setting('ingest_status', json.dumps(
        {'state': 'running', 'what': what, 'at': datetime.now().isoformat(sep=' ', timespec='seconds')}), 'system')
    try:
        # channels FIRST: the Morning digest is a report over Taskuary's own data, and run
        # before the catch-up it would summarize yesterday while today sat in the mailbox
        from .channels import poll_channels
        def _say(kind, so_far):
            # the ORIGINAL what is kept and appended to: "catching up on the last 3 day(s)" is
            # the context, "reading outlook · 12 in so far" is the progress, and replacing the
            # first with the second loses why the poll is running at all
            store.set_setting('ingest_status', json.dumps(
                {'state': 'running', 'at': datetime.now().isoformat(sep=' ', timespec='seconds'),
                 'what': f'{what} · reading {kind}' + (f' · {so_far} in so far' if so_far else '')}), 'system')
        # show first, judge next: the poll stores every message as it reads it (the timeline
        # shows them at once, wearing 'triaging'), and the AI calls come afterwards, in order
        from . import ingest as ingest_mod
        with ingest_mod.deferred():
            poll_channels(store, backfill_days, progress=_say, **({'only': only} if only is not None else {}))
        def _left(n):
            store.set_setting('ingest_status', json.dumps(
                {'state': 'running', 'at': datetime.now().isoformat(sep=' ', timespec='seconds'),
                 'what': f'{what} · triaging' + (f' · {n} left' if n else '')}), 'system')
        try: ingest_mod.drain(store, _llm(), progress=_left)
        except Exception as e: logger.warning(f'deferred triage drain failed: {e}')
        if only is not None: return            # a quick pass reads its channels and stops
        # the git loop: a task's PR is watched here, and a red build goes back to the agent
        # that wrote the code (ci.py) - off unless the owner turned ci_watch on
        try:
            from . import ci
            ci.poll(store)
        except Exception as e:
            logger.warning(f'CI poll failed: {e}')
        # the agent wall composts once a day: yesterday's notes become one summary per checkout,
        # so what an agent reads tomorrow is what still matters (blackboard.roll_up)
        try:
            blackboard.roll_daily(store)
        except Exception as e:
            logger.warning(f'the wall roll-up failed: {e}')
        run_due_reports(store, startup)          # ...the seeded 'Assistant' report among them (assistant.py)
    finally:
        try: store.set_setting('ingest_status', json.dumps({'state': 'idle'}), 'system')
        finally: _POLL_BUSY.release()


def _catchup_days(ceiling: int) -> int:
    """How far past the watermark startup actually needs to reach: the time the app was CLOSED,
    not the full `startup_sync_days` ceiling. Reopening ten minutes after closing used to re-read
    three days of every mailbox (dedupe threw it all away, slowly - the whole timeline sat behind
    a 'catching up' banner for it). Under an hour of gap is what the watermark already covers."""
    last = max((str(s.get('LastPolledAt') or '') for s in store.list_sources()), default='')
    if not last: return ceiling
    try: gap_h = (datetime.now() - datetime.fromisoformat(last.replace(' ', 'T'))).total_seconds() / 3600
    except ValueError: return ceiling
    return 0 if gap_h <= 1 else min(ceiling, int(gap_h // 24) + 1)


def catch_up_on_startup():
    """Whatever arrived while the app was closed was polled by nobody, and Taskuary is not a
    service - it is a window you open. So opening it reaches back past the watermark - but only
    as far as the app was actually closed, with `startup_sync_days` (default 3) as the ceiling.
    0 turns the startup poll off entirely."""
    try: days = int(store.get_settings().get('startup_sync_days') or 0)
    except ValueError: days = 0
    if days <= 0: return
    days = _catchup_days(days)
    logger.info(f"startup: {'incremental poll (closed under an hour)' if days == 0 else f'catching up on the last {days} day(s)'}")
    def _catch_up():
        _poll_reports(days, what=f'catching up on the last {days} day(s)' if days else 'syncing', startup=True)
        # the Morning digest needs no call of its own anymore: it is a seeded REPORT, run by
        # the poll above like every other one. Consolidate what the verdicts taught next,
        # on the same once-a-day rhythm.
        try: learn.reflect_if_due(store)
        except Exception as e: logger.warning(f'reflection failed: {e}')
    threading.Thread(target=_catch_up, daemon=True).start()


def _heal_owner_docs():
    """The shipped docs read as a person on purpose - John Smith is the open-source example, not
    a token soup - and they stay that way until a REAL owner is known. The moment one is (the
    owner card, or a name typed into SOUL.md), the docs convert themselves once per launch: the
    placeholder and the known name both sweep into {{owner}} tokens, so every mention follows
    the one setting from then on. "Johnson Controls" is not a name match; owner prose survives."""
    try:
        soul = store.get_doc('soul') or ''
        if not (store.get_settings().get('owner_name') or '').strip():
            name = store_mod.owner_from_soul(soul)
            if name and name not in ('the owner', 'John Smith'):   # John Smith IS the placeholder
                store.set_setting('owner_name', name, 'startup')
                em = store_mod.email_from_soul(soul)
                if em and em != 'john.smith@example.com': store.set_setting('owner_email', em, 'startup')
        who = store.owner()
        if who['owner'] in ('the owner', '', 'John Smith') or '{{' in who['owner']:
            return                                    # nobody real named yet: the example stands
        for doc in ('soul', 'coder', 'digest', 'learned', 'triage', 'style', 'counsel'):
            raw = store.get_doc(doc)
            if not raw: continue
            t = store_mod.retoken_doc(raw, 'John Smith', 'john.smith@example.com')
            t = store_mod.retoken_doc(t, who['owner'], who['owner_email'])
            if t != raw:
                # tokenizing a name is not editing the document: a doc nobody has touched stays
                # 'template' so shipped improvements keep reaching it (store seeds it afresh each
                # launch and this pass tokenizes it again - idempotent, and current)
                store.save_doc(doc, t, 'template' if store.doc_owner(doc) == 'template' else 'startup')
                logger.info(f'{doc}.md: owner names converted to tokens (owner: {who["owner"]})')
    except Exception as e:
        logger.warning(f'owner-doc heal failed: {e}')


def _refresh_soul_connections():
    """The connections block in SOUL.md is GENERATED text, so a fix to its wording has to reach
    installs that never touch a connector again - refresh it once per launch. The owner's own
    prose outside the markers is untouched, as always."""
    from .docsync import sync_connections
    try: sync_connections(store, 'startup')
    except Exception as e: logger.warning(f'connection sync at startup failed: {e}')

@app.post('/api/ingest/poll')
def ingest_poll(background: BackgroundTasks):
    background.add_task(_poll_reports)
    return {'report': 'running'}

@app.get('/api/ingest/status')
def ingest_status():
    try: st = json.loads(store.get_settings().get('ingest_status') or '{"state": "idle"}')
    except ValueError: st = {'state': 'idle'}
    # a poll that died with the app leaves 'running' behind with nobody holding the lock - a
    # ghost the timeline banner would show forever (the poll sets the flag only AFTER taking
    # the lock, so running-but-unlocked is always a ghost). Heal it on read.
    if st.get('state') == 'running' and not _POLL_BUSY.locked():
        st = {'state': 'idle'}
        store.set_setting('ingest_status', json.dumps(st), 'system')
    # the cadence rides along so the timeline's caption can state the truth instead of a
    # hardcoded "every 10 min" that stayed on screen after somebody set the interval to 0
    try: every = int(store.get_settings().get('poll_minutes') or 0)
    except (TypeError, ValueError): every = 10
    # and the clock itself: when the last full poll ran and when the next is due, so the caption
    # can count down instead of asserting a cadence nobody could check
    return {'status': st, 'everyMinutes': every, 'lastPollAt': _LAST_POLL[0],
            'nextPollAt': (_LAST_POLL[0] + every * 60) if every > 0 else None, 'now': time.time(),
            # the brain's last failure, until it answers again - shown in the caption, not buried in rows
            'triageError': store.get_settings().get('triage_last_error') or '',
            'timelineFade': store.get_settings().get('timeline_fade') or 'normal'}  # how old rows dim (FeedView)

# ── interactive terminals (real pty + websocket; the headless runs live on /api/runs) ──
class TermBody(BaseModel):
    agent: str | None = None; task_id: int | None = None; repo: str | None = None
    cwd: str | None = None; rows: int = 32; cols: int = 110; seed: bool = False
    model: str | None = None

@app.get('/api/terminals')
def terminals(): return {'data': hub_term.listing()}

@app.post('/api/terminals')
def open_terminal(body: TermBody):
    """Spawn an agent CLI (or a plain shell) under a real pty. seed=true types the task's
    context in as the first line, so the agent starts on it and you keep talking."""
    tk = store.get_task(body.task_id) if body.task_id else None
    # Taskuary picks the checkout, not the agent: with no repo named, match the ask against the
    # SOUL.md repo map (which lives in this database, nowhere the agent can read).
    repo, why = body.repo, None
    if body.agent and tk and not repo and not body.cwd:
        row = store.get_agent(body.agent)
        repo, why = hub_term.guess_repo(store, body.task_id, json.loads((row or {}).get('Config') or '{}'))
    # seeding only makes sense for an agent CLI - a bare shell would just try to RUN the text.
    # This used to build its own thin prompt (title + summary, no message), which is exactly why
    # an agent started here went back to the API for the mail: it had not been given it.
    seed_fn = ((lambda cwd: hub_term.seed_text(store, body.task_id, None, repo, cwd)[:8000])
               if body.seed and body.agent and tk else None)
    try:
        t = hub_term.open_session(store, body.agent, body.task_id, repo, body.cwd, body.rows, body.cols,
                                  ACTOR, body.model, seed_fn=seed_fn)
    except (ValueError, RuntimeError, FileNotFoundError) as e:
        # a CLI you configured but never installed is the common one - say which, don't 500
        raise HTTPException(422, str(e))
    # This is the task page's Start session door (dispatch uses terminal.start_on_task). Opening
    # a real session is an explicit restart: the live agent belongs in progress even when this
    # task had already been marked done, waiting or dropped.
    if tk and tk.get('Status') != 'in_progress':
        store.update_task(body.task_id, {'Status': 'in_progress'}, ACTOR)
    if seed_fn:
        store.add_comment(body.task_id, ACTOR, 'human',
                          f'Opened an interactive {t.label} session in {t.cwd}' + (f' - {why}.' if why else '.'))
    return t.info()

class WrapBody(BaseModel): task_id: int | None = None; close: bool = True

def _wrap_task(tid: int, close: bool, sid: str = None):
    """The route's thin end of coder.wrap - which is also what a self-closing agent calls
    (selfclose.py), so "the agent decided it was done" and "you clicked Done" travel the
    same road and leave the same record."""
    try: return coder_wrap(store, tid, close, ACTOR, sid)
    except ValueError as e: raise HTTPException(422, str(e))


def _pause_task(tid: int, sid: str = None):
    if not tid or not store.get_task(tid): raise HTTPException(422, 'this session is not on a task')
    text, agent, found = hub_term.transcript_for(store, tid)
    if not text.strip(): raise HTTPException(422, 'nothing to save - this task has no session transcript')
    note = pause_note(store, tid, text)
    if found: hub_term.close(found)
    store.add_comment(tid, agent, 'agent', f'{PAUSE_MARKER}\n{note}')
    store.add_comment(tid, ACTOR, 'human', 'Paused the session - picking this up later.')
    store.audit('terminal', tid, 'pause', ACTOR, detail={'sid': sid or found})
    return {'pause': 'done', 'taskId': tid, 'note': note}


@app.post('/api/tasks/{task_id}/wrap')
def wrap_task(task_id: int, body: WrapBody):
    """"We're done" - and it asks the agent NOTHING. The transcript is already on screen, so we
    take it, end the session, and let the main AI turn it into the report; the responder drafts
    the reply from that report and the task waits on you to send it. Typing a wrap-up prompt into
    the pty meant one more prompt to read, minutes of waiting, and a fresh chance for an agent you
    just stopped to go do more work."""
    return _wrap_task(task_id, body.close)

@app.post('/api/tasks/{task_id}/pause')
def pause_task(task_id: int, body: WrapBody):
    """Stop for now WITHOUT throwing the work away. Killing a session used to lose everything it
    had worked out - the pty dies, the scrollback goes, and the next session starts from nothing.
    This writes the handover note first (from the transcript, by the main AI), files it on the
    task, and hands it to whoever resumes: the next session is seeded with it. The task stays
    open - pausing is not finishing, so no report and no reply draft."""
    return _pause_task(task_id)

@app.post('/api/terminals/{sid}/wrap')
def wrap_terminal(sid: str, body: WrapBody):
    """Same thing, addressed by session - what the terminal pane itself has a handle on."""
    t = hub_term.get(sid)
    return _wrap_task(body.task_id or (t.task_id if t else None), body.close, sid)

@app.post('/api/terminals/{sid}/pause')
def pause_terminal(sid: str, body: WrapBody):
    t = hub_term.get(sid)
    return _pause_task(body.task_id or (t.task_id if t else None), sid)

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
    input_q = asyncio.Queue()
    send_lock = asyncio.Lock()
    delivered, inflight = 0, 0
    redraw_boundary = None
    redraw_quiet = None
    redraw_cap = None

    async def send_frame(frame):
        # Output and the ready barrier come from separate tasks. One lock makes their order on
        # the wire exactly the order expressed below.
        async with send_lock: await ws.send_json(frame)

    async def finish_redraw(delay: float):
        """Send ready after the resize-driven repaint goes quiet, not after resize() returns."""
        nonlocal redraw_boundary, redraw_quiet, redraw_cap
        try: await asyncio.sleep(delay)
        except asyncio.CancelledError: return
        if redraw_boundary is None: return
        redraw_boundary = None
        if redraw_quiet and redraw_quiet is not asyncio.current_task(): redraw_quiet.cancel()
        if redraw_cap and redraw_cap is not asyncio.current_task(): redraw_cap.cancel()
        redraw_quiet = redraw_cap = None
        await send_frame({'type': 'ready'})

    async def to_browser():
        nonlocal delivered, inflight, redraw_quiet
        while True:
            data = await q.get()
            if data is None: return await send_frame({'type': 'exit'})
            # Codex repaints its WHOLE screen for every keystroke, and ConPTY hands that back in
            # several reads. One websocket frame - and one xterm parse - per read meant a fast
            # sentence typed its own repaints into a backlog the echo had to queue behind, which
            # is what "typing is really slow" was. Drain whatever is already waiting and send it
            # as one ordered chunk, exactly as to_pty() does for keystrokes. Nothing is dropped:
            # this only changes how many frames the same bytes arrive in.
            chunks, ended = [data], False
            while True:
                try: more = q.get_nowait()
                except asyncio.QueueEmpty: break
                if more is None: ended = True; break     # the exit marker keeps its place in the order
                chunks.append(more)
            inflight += 1
            try: await send_frame({'type': 'out', 'data': ''.join(chunks)})
            finally: inflight -= 1
            delivered += len(chunks)
            # Ignore output that was already queued when the resize began. The first new chunk
            # and every repaint chunk after it move the quiet barrier; ready follows the burst.
            if redraw_boundary is not None and delivered >= redraw_boundary:
                if redraw_quiet: redraw_quiet.cancel()
                redraw_quiet = asyncio.create_task(finish_redraw(.09))
            if ended: return await send_frame({'type': 'exit'})
    pump = asyncio.create_task(to_browser())

    async def to_pty():
        """Drain the socket independently of ConPTY and fold its queued keystrokes into one write.

        pywinpty writes are synchronous and can take a visible beat while Codex is repainting.
        Calling one directly from the receive loop made a fast sentence arrive one character per
        beat. The first character may still be in flight, but the rest collect here and cross the
        PTY in one ordered byte stream instead of paying that cost for every key.
        """
        while True:
            data = await input_q.get()
            chunks = [data]
            while True:
                try: chunks.append(input_q.get_nowait())
                except asyncio.QueueEmpty: break
            await asyncio.to_thread(t.write, ''.join(chunks))
    input_pump = asyncio.create_task(to_pty())
    try:
        # scrubbed: a replayed scrollback that still contains the TUI's terminal queries makes
        # xterm answer them AGAIN, and the answers land in the CLI as typed junk - see terminal.py
        # flagged as a REPLAY so the browser can hold the curtain over it: writing a long
        # scrollback runs the viewport from the top of the session down to the bottom, and
        # watching a week of coding scroll past every time you reopen a task is not a feature
        if t.scrollback():
            await send_frame({'type': 'out', 'replay': True, 'data': hub_term.scrub_queries(t.scrollback())})
        first_resize = True
        while True:
            m = await ws.receive_json()
            if m.get('type') == 'in': input_q.put_nowait(m.get('data') or '')
            elif m.get('type') == 'resize':
                rows, cols = m.get('rows') or 32, m.get('cols') or 110
                # a full-screen TUI (codex) paints with absolute cursor moves, so the raw
                # scrollback replay above renders as smeared bars on a reopened page - and
                # nothing repaints until the CHILD is told to. A one-column wiggle on the
                # first resize makes ConPTY signal a window change: a full redraw, the live
                # screen instead of the replay's debris.
                if first_resize:
                    first_resize = False
                    # The child repaints asynchronously. Mark the queue boundary before the
                    # wiggle; output beyond it is evidence of the live Codex screen arriving.
                    redraw_boundary = delivered + inflight + q.qsize() + 1
                    redraw_cap = asyncio.create_task(finish_redraw(1.5))
                    t.resize(rows, max(2, cols - 1))
                    await asyncio.sleep(0.05)
                t.resize(rows, cols)
    except (WebSocketDisconnect, RuntimeError, ValueError):
        pass
    finally:
        t.unsubscribe(q); pump.cancel(); input_pump.cancel()
        if redraw_quiet: redraw_quiet.cancel()
        if redraw_cap: redraw_cap.cancel()

# ── the knowledge base (knowledge.py): the card's Reindex button; searching goes through /api/tools/run (kb_search) ──
class ReindexBody(BaseModel): connector_id: int | None = None

@app.post('/api/knowledge/reindex')
def knowledge_reindex(body: ReindexBody):
    """Walk the Knowledge base card's sources now and refresh the index. Long for a big library -
    the response carries what was indexed, skipped, removed and any file that would not read."""
    from . import knowledge
    r = knowledge.reindex(store, body.connector_id)
    store.audit('connector', body.connector_id or 0, 'reindex', ACTOR, detail={k: v for k, v in r.items() if k != 'errors'})
    return {'ok': not r['errors'] or r['indexed'] > 0, **r}

@app.get('/api/knowledge/search')
def knowledge_search(q: str, limit: int = 8, connector_id: int | None = None):
    """Ranked passages for a question - what the card's search box shows."""
    from . import knowledge
    return {'data': knowledge.search(store, q, max(1, min(50, limit)), connector_id)}

# ── the semantic layer (semantic.py): business numbers proved against known ones ──
class MetricBody(BaseModel):
    Name: str | None = None; Label: str | None = None; Grain: str | None = None
    Definition: str | None = None; Spec: dict | None = None; Notes: str | None = None
    ConnectorId: int | None = None

class FixtureBody(BaseModel):
    """One number the owner already knows is right - the only thing that can prove a definition."""
    Scope: str | None = None; Period: str | None = None
    Expected: float; Tolerance: float | None = None; Source: str | None = None

class TryBody(BaseModel): scope: str | None = None; period: str | None = None

def _metric_row(m: dict) -> dict:
    return {**m, 'Spec': json.loads(m.get('SpecJson') or '{}'), 'fixtures': store.list_fixtures(m['MetricId'])}

@app.get('/api/semantic/metrics')
def metrics_list(status: str = None):
    """Every definition with its known numbers and whether they still reconcile."""
    from . import semantic
    return {'data': [_metric_row(m) for m in store.list_metrics(status)], 'minFixtures': semantic.MIN_FIXTURES}

@app.post('/api/semantic/metrics')
def metric_save(body: MetricBody):
    """Write (or rewrite) a definition. Saving NEVER makes it trusted - only check() does, and
    editing the spec of a verified metric puts it back to draft, because the proof was of the
    old query and nothing has proved the new one."""
    if not (body.Name or '').strip(): raise HTTPException(422, 'a metric needs a name')
    old = store.metric_by_name(body.Name)
    fields = {'Name': body.Name, 'Label': body.Label, 'Grain': body.Grain, 'Definition': body.Definition,
              'Notes': body.Notes, 'ConnectorId': body.ConnectorId}
    if body.Spec is not None: fields['SpecJson'] = json.dumps(body.Spec)
    if old and body.Spec is not None and json.dumps(body.Spec) != (old.get('SpecJson') or ''):
        fields['Status'] = 'draft'
    mid = store.save_metric({k: v for k, v in fields.items() if v is not None}, ACTOR)
    store.audit('metric', mid, 'save', ACTOR, detail={'name': body.Name, 'respec': bool(old and fields.get('Status'))})
    return _metric_row(store.get_metric(mid))

@app.delete('/api/semantic/metrics/{mid}')
def metric_delete(mid: int):
    if not store.get_metric(mid): raise HTTPException(404, 'no such metric')
    store.delete_metric(mid); store.audit('metric', mid, 'delete', ACTOR)
    return {'ok': True}

@app.post('/api/semantic/metrics/{mid}/fixtures')
def metric_add_fixture(mid: int, body: FixtureBody):
    if not store.get_metric(mid): raise HTTPException(404, 'no such metric')
    fid = store.add_fixture(mid, body.dict(), ACTOR)
    store.audit('metric', mid, 'fixture_add', ACTOR, detail={'scope': body.Scope, 'period': body.Period, 'expected': body.Expected})
    return _metric_row(store.get_metric(mid)) | {'fixtureId': fid}

@app.delete('/api/semantic/fixtures/{fid}')
def metric_drop_fixture(fid: int):
    store.delete_fixture(fid)
    return {'ok': True}

@app.post('/api/semantic/metrics/{mid}/try')
def metric_try(mid: int, body: TryBody = None):
    """Run the definition once WITHOUT recording anything - the exploration step. This is how a
    definition gets to the point of being worth proving: try it on a facility, look at the
    number, adjust the spec, try again."""
    from . import semantic
    m = store.get_metric(mid)
    if not m: raise HTTPException(404, 'no such metric')
    body = body or TryBody()
    try: return semantic.evaluate(store, m, body.scope, body.period)
    except Exception as e: raise HTTPException(422, str(e)[:400])

@app.post('/api/semantic/metrics/{mid}/check')
def metric_check(mid: int):
    """Re-prove it against every known number. The only road to 'verified' - and the road back."""
    from . import semantic
    if not store.get_metric(mid): raise HTTPException(404, 'no such metric')
    try: return semantic.check(store, mid, ACTOR)
    except ValueError as e: raise HTTPException(422, str(e))

# ── the agent's browser, beside its terminal (browserview.py) ──
@app.get('/api/terminals/{sid}/browser')
def terminal_browser(sid: str):
    """Is a browser open for this session, and on what page - read from agent-browser's state
    files, so the pane can appear when the agent opens a page and fold when it closes."""
    from . import browserview
    return browserview.state(sid)

class SnapBody(BaseModel): task_id: int | None = None

@app.post('/api/terminals/{sid}/browser/snapshot')
def terminal_browser_snapshot(sid: str, body: SnapBody):
    """Keep the frame on the task record: a JPEG attachment plus a comment naming the page."""
    from . import browserview
    try: return browserview.snapshot(store, sid, ACTOR, body.task_id)
    except ValueError as e: raise HTTPException(422, str(e))

@app.websocket('/api/terminals/{sid}/browser/ws')
async def terminal_browser_ws(ws: WebSocket, sid: str):
    """agent-browser's screencast, relayed: frames out, the owner's input back when they take over.
    Same token rule as the terminal socket - it rides on the query string."""
    from . import browserview
    tok = cfg['server'].get('token')
    if tok and ws.query_params.get('token') != tok: return await ws.close(code=4401)
    await browserview.relay(ws, sid)

@app.get('/api/health')
def health():
    """Unauthenticated on purpose: a container HEALTHCHECK needs a pulse without the LAN token."""
    return {'ok': True}

@app.get('/api/demo')
def demo_state():
    """Is this a demo instance? The banner asks; nothing else depends on it."""
    return {'demo': demo.enabled(), 'owner': demo.OWNER if demo.enabled() else ''}

@app.get('/api/build')
def build():
    """Which UI bundle is on disk right now.

    Taskuary updates underneath an open tab - a git pull, a rebuild, `pip install -U` - and the
    tab goes on running the JavaScript it loaded at breakfast. Every symptom of that looks like
    a bug that was already fixed, and the owner has no way to tell the difference from inside
    the page. So the page asks, and says "reload" when the answer stops matching what it loaded.
    """
    try:
        html = (_web_root / 'index.html').read_text(encoding='utf-8')
        return {'asset': (re.search(r'assets/(index-[A-Za-z0-9_-]+\.js)', html) or [None, ''])[1],
                'version': _ver}
    except OSError:
        return {'asset': '', 'version': _ver}

@app.get('/api/settings')
def settings():
    return {'data': [s for s in store.list_settings() if s['Name'] not in ('ingest_status', 'assistant_last_run', 'assistant_notes', 'assistant_notes_at')
                     and not s['Name'].startswith('report_last_run:')]}

@app.patch('/api/settings')
def set_setting(body: SettingBody):
    store.set_setting(body.name, body.value, ACTOR)
    return {'ok': True}

@app.get('/api/audit/verify')
def verify(): return store.verify_audit_chain()
