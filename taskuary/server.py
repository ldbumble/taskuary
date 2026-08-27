"""The local HTTP API + built-in minimal web UI. Localhost-only by default; set
[server].token in config to require an X-Taskuary-Token header (for LAN/self-hosting).
"""
import asyncio, json, re, threading, time
import requests
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse, Response
from pydantic import BaseModel

from . import config
from . import store as store_mod
from .store import SQLiteStore, task_ref
from .ingest import ingest_message, split_message, task_from_message
from .reports import PLANNED, REGISTRY, render_report, resolve_cfg, run_due_reports, run_report_source
from . import agents as hub_agents
from . import blackboard
from . import policy as policy_engine
from . import reshape
from . import terminal as hub_term
from .coder import (PAUSE_MARKER, finish as coder_finish, pause_note, reply_target as coder_reply_target,
                    report_from_transcript, resolution_text)
from . import learn, learnedgraph, outbound, rank, responder, waitroom

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
    tok = cfg['server'].get('token')
    if tok and request.url.path.startswith('/api') and request.headers.get('X-Taskuary-Token') != tok:
        # an <img src> cannot carry a header, so attachment READS take the token in the query
        # string - the same concession websockets already needed
        if not (request.url.path.startswith('/api/attachments/') and request.query_params.get('token') == tok):
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


@app.get('/', response_class=HTMLResponse)
def index():
    """The one file that must NEVER be cached. Every asset under /assets carries a content hash
    in its name, so those can be held forever - but index.html is what NAMES them, and a cached
    copy points a fresh install at a bundle that is no longer there (or worse, one that is). An
    old index.html is how a fixed crash keeps crashing: the fix shipped, the browser kept asking
    for yesterday's JS, and the stack trace named a file the repo had already replaced."""
    html = (Path(__file__).parent / 'web' / 'index.html').read_text(encoding='utf-8')
    return HTMLResponse(html, headers={'Cache-Control': 'no-store, must-revalidate'})

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
    return {'data': [{**t, 'ref': task_ref(t['TaskId']), 'Session': hub_term.for_task(t['TaskId']),
                      'Queued': _queued_info(qs.get(t['TaskId'])), 'Waiting': wc.get(t['TaskId'], 0)}
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
                      f'Repo set to {body.repo} - the session works there and the prompt says so.'
                      if body.repo else 'Cleared the repo - Taskuary picks it from the ask again.')
    store.audit('task', task_id, 'set_repo', ACTOR, detail={'repo': body.repo, 'path': body.path})
    out = {'ok': True, 'repo': body.repo}
    if body.restart:
        live = hub_term.session_for(task_id)
        if live: hub_term.close(live.sid)
        out['session'] = start_session(store, task_id, body.agent)
    return out

class NotATaskBody(BaseModel): learn: bool = True

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
    """Owner verdict: never needed to be a task. Teaches (sender ignore policy + memory
    note), then deletes the task - its messages stay in the feed as 'filed'.

    learn=false is the lighter verdict: THIS one is just chatter (someone answered "yes"),
    with nothing to conclude about the sender - delete the task, teach nothing, keep their
    future messages flowing exactly as before."""
    if not store.get_task(task_id): raise HTTPException(404, 'task not found')
    msgs, learned = store.list_messages(task_id), None
    em = (msgs[0].get('FromEmail') or '').lower() if msgs else ''
    if em and (body is None or body.learn):
        store.save_policy({'Name': f'not-a-task: {em}', 'Kind': 'sender', 'Pattern': em, 'Action': 'ignore',
                           'Reason': 'owner said not a task', 'SortOrder': 50, 'Active': 1}, ACTOR)
        # the same generalisation as "Not our task": this verdict is about a kind of work, and
        # keyed to one sender it stops applying the moment a colleague forwards the same thing.
        # (The sender ignore POLICY above stays per-sender - that one really is about them.)
        topic = _topic_key(msgs[0])
        mid = store.add_memory({'Scope': 'subject' if topic else 'sender', 'ScopeKey': topic or em,
                                'Source': 'verdict', 'Active': 1, 'CreatedBy': ACTOR,
                                'Note': f"{str(msgs[0].get('SentAt') or '')[:10]}: \"{(msgs[0].get('Subject') or '')[:90]}\" from {em}"
                                        + (f' - the topic "{topic}"' if topic else '')
                                        + ' - NOT A TASK: the owner filed it, no task, no reply'})
        learned = {'policy': em, 'memory_id': mid}
        learn.note_verdicts(store)
        # the sender note is durable already; the GENERAL lesson (what kinds of mail are not
        # tasks for this owner) is LEARNED.md's to distill. learn=false teaches nothing, as asked.
        if background is not None:
            background.add_task(learn.learn_from, store,
                                f"mem{mid}: owner said NOT A TASK: \"{(msgs[0].get('Subject') or '')[:80]}\" from {em} "
                                'should never have opened a task')
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
    inline = (not download) and ct.lower().startswith('image/') and ct.lower() not in _NOSCRIPT
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
def file_message(mid: int):
    """"Nothing to do here" - the harmless exit, and the one that was MISSING. A message
    triage filed with no task offered only "Not our task", which writes a durable verdict
    against the sender (and against EVERY sender when the channel has no address to key on,
    like Teams) - so getting one chat off the timeline could quietly teach the funnel to stop
    listening to a colleague. This teaches nothing about the SENDER or the topic: the item
    stops being work, its task goes if it had one, and their next message on another thread
    arrives exactly as before. The rest of THIS conversation is filed with it, though - the
    owner ignore route below is what ingest.veto reads (store.owner_verdict_on_thread), because
    "not a task" said on a thread and then a task from its next reply is the funnel arguing."""
    m = store.get_message(mid)
    if not m: raise HTTPException(404, 'message not found')
    tid = m.get('TaskId')
    if tid and store.get_task(tid):
        store.audit('task', tid, 'filed_not_work', ACTOR, detail={'message_id': mid})
        _drop_task(tid)                              # its messages revert to 'filed'
    store.set_message_status(mid, 'ignored')
    store.add_route(mid, None, 'ignore', None, 'nothing to do - filed by the owner, nothing learned', [], ACTOR)
    return {'ok': True, 'taskDeleted': bool(tid)}

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

class MineBody(BaseModel): kind: str = 'general'

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

@app.get('/api/people')
def people(): return {'data': store.people()}

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
                        'files': t.get('files') or [], 'tail': t.get('tail') or []})
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

@app.get('/api/report-types')
def report_types():
    return {'data': [{'type': t, 'status': 'planned' if t in PLANNED else 'builtin'} for t in REGISTRY]}

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
    out += [{'value': f"connector:{c['Type']}", 'label': c['Name'], 'kind': 'api',
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
        if o['kind'] == 'api': o['models'] = CONN_MODELS.get(o['value'][10:], [])
    def _cli_of(a):
        prof = cfg.get('agents', {}).get(a['Name']) or json.loads(a.get('Config') or '{}')
        return re.sub(r'\.(cmd|exe|bat|ps1)$', '', Path(str(prof.get('cmd') or a['Name'])).name.lower())
    out += [{'value': f"cli:{a['Name']}",
             'label': (_cli_of(a) + (f" · {a['Name']}" if _cli_of(a) != a['Name'] else '')) + ' (your CLI)',
             'kind': 'cli', 'ready': True, 'models': CLI_MODELS.get(_cli_of(a), [])}
            for a in store.list_agents()]
    return {'data': out, 'current': store.get_settings().get('triage_ai') or ''}

@app.post('/api/connectors')
def save_connector(body: ConnectorBody):
    fields = {k: (int(v) if k == 'Active' else v) for k, v in body.dict().items() if v is not None}
    if fields.get('Roles') is not None:
        bad = {r for r in fields['Roles'].split(',') if r} - set(store_mod.ROLES)
        if bad: raise HTTPException(422, f"unknown role(s): {', '.join(sorted(bad))}")
    if fields.get('Scope') is not None:
        from . import scopes
        if fields['Scope'] not in scopes.SCOPES:
            raise HTTPException(422, f"unknown authority: {fields['Scope']} - one of {', '.join(scopes.SCOPES)}")
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
    return {'status': 'ok', **who}

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
    conn = store.get_connector_by_type(card_of(t))    # s3_object runs on the aws card's roles
    if conn:
        if not conn.get('Active'):
            raise HTTPException(403, f'the {t} connection is off - turn it on under Connectors')
        if 'tool' not in store_mod.roles_of(conn):
            raise HTTPException(403, f'the {t} connection is not marked as an agent tool (Connectors → {t} → Role)')
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
    return {'data': clis.detect(store)}

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

# Models each CLI can be pointed at. The agent profile's own `model` (Connectors → AI CLI
# agents) always wins as the default; these are the quick picks the run dialogs offer.
CLI_MODELS = {
    'claude': ['opus', 'sonnet', 'haiku', 'claude-opus-5', 'claude-sonnet-5', 'claude-haiku-4-5'],
    'codex': ['gpt-5-codex', 'gpt-5'],
    'gemini': ['gemini-2.5-pro', 'gemini-2.5-flash'],
}

@app.get('/api/agents')
def agents():
    """data = store rows (for dispatch pickers); config = the editable profiles;
    models = the quick-pick model list per agent, keyed by agent name."""
    def _models(a):
        prof = json.loads(a.get('Config') or '{}')
        picks = CLI_MODELS.get((prof.get('cmd') or '').lower(), [])
        return {'cmd': prof.get('cmd'), 'default': prof.get('model'), 'choices': picks}
    # the default agent (a setting) comes FIRST: every picker's initial value is the head of
    # this list, so "which CLI opens when I hit Start session" is decided in one place
    rows = sorted(store.list_agents(), key=lambda a: a['Name'] != (store.get_settings().get('default_agent') or 'coder'))
    return {'data': rows, 'config': cfg.get('agents', {}),
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
    for doc in ('soul', 'coder', 'digest', 'learned', 'triage', 'style'):
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
        run_due_reports(store, startup)
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
        for doc in ('soul', 'coder', 'digest', 'learned', 'triage', 'style'):
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
    return {'status': st, 'everyMinutes': every}

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
    if seed_fn:
        store.add_comment(body.task_id, ACTOR, 'human',
                          f'Opened an interactive {t.label} session in {t.cwd}' + (f' - {why}.' if why else '.'))
    return t.info()

class WrapBody(BaseModel): task_id: int | None = None; close: bool = True

# Wrapping up belongs to the TASK, not to a pty. Keying it on a live session meant that once the
# CLI had exited and been reaped - ten minutes - the buttons had nothing to read and quietly
# vanished, leaving a task that could never be closed out. The transcript is filed when a session
# ends, so these work whether the terminal is live, exited, or long gone.
def _wrap_task(tid: int, close: bool, sid: str = None):
    if not tid or not store.get_task(tid): raise HTTPException(422, 'this session is not on a task')
    text, agent, found = hub_term.transcript_for(store, tid)
    if not text.strip(): raise HTTPException(422, 'nothing to wrap up - this task has no session transcript')
    if found: hub_term.close(found)          # done means done - the pty and its shells go too
    rep = report_from_transcript(store, tid, text, agent)
    report = resolution_text(rep)
    store.add_comment(tid, ACTOR, 'human', 'Closed the session - wrapped up from what was on screen.')
    store.add_comment(tid, agent, 'agent', f'CODER REPORT\n{report}')
    # anything the agent PROPOSED becomes a pending review here, at the one moment its whole
    # transcript is in hand - and refusals are recorded rather than dropped (proposals.py)
    proposed = []
    if store.get_settings().get('proposals_enabled', '1') == '1':
        try:
            from . import proposals
            proposed = proposals.collect(store, tid, text, agent)
        except Exception as e:
            logger.warning(f'proposal collection failed for task {tid}: {e}')
    # 'drafting' must be what finish() ACTUALLY did, not a second guess at it: recomputing it
    # from reply_target alone skipped the can-this-channel-even-reply rule, so a GitHub task
    # with replies off closed with no draft while the card still promised one in Review.
    fin = {}
    if close and (store.get_task(tid) or {}).get('Status') not in ('done', 'dropped'):
        fin = coder_finish(store, tid, rep, None, agent) or {}
    store.audit('terminal', tid, 'wrap', ACTOR, detail={'sid': sid or found, 'close': close})
    return {'wrap': 'done', 'taskId': tid, 'report': report, 'proposed': proposed,
            'drafting': bool(fin.get('drafting'))}


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
    async def to_browser():
        while True:
            data = await q.get()
            if data is None: return await ws.send_json({'type': 'exit'})
            await ws.send_json({'type': 'out', 'data': data})
    pump = asyncio.create_task(to_browser())
    try:
        # scrubbed: a replayed scrollback that still contains the TUI's terminal queries makes
        # xterm answer them AGAIN, and the answers land in the CLI as typed junk - see terminal.py
        # flagged as a REPLAY so the browser can hold the curtain over it: writing a long
        # scrollback runs the viewport from the top of the session down to the bottom, and
        # watching a week of coding scroll past every time you reopen a task is not a feature
        if t.scrollback():
            await ws.send_json({'type': 'out', 'replay': True, 'data': hub_term.scrub_queries(t.scrollback())})
        first_resize = True
        while True:
            m = await ws.receive_json()
            if m.get('type') == 'in': t.write(m.get('data') or '')
            elif m.get('type') == 'resize':
                rows, cols = m.get('rows') or 32, m.get('cols') or 110
                # a full-screen TUI (codex) paints with absolute cursor moves, so the raw
                # scrollback replay above renders as smeared bars on a reopened page - and
                # nothing repaints until the CHILD is told to. A one-column wiggle on the
                # first resize makes ConPTY signal a window change: a full redraw, the live
                # screen instead of the replay's debris.
                wiggled = first_resize
                if first_resize:
                    first_resize = False
                    t.resize(rows, max(2, cols - 1))
                    await asyncio.sleep(0.05)
                t.resize(rows, cols)
                # the replay is debris until that redraw lands - THIS is the moment the pane
                # is showing the live screen, and the only honest time to lift the curtain
                if wiggled: await ws.send_json({'type': 'ready'})
    except (WebSocketDisconnect, RuntimeError, ValueError):
        pass
    finally:
        t.unsubscribe(q); pump.cancel()

@app.get('/api/health')
def health():
    """Unauthenticated on purpose: a container HEALTHCHECK needs a pulse without the LAN token."""
    return {'ok': True}

@app.get('/api/settings')
def settings():
    return {'data': [s for s in store.list_settings() if s['Name'] != 'ingest_status']}

@app.patch('/api/settings')
def set_setting(body: SettingBody):
    store.set_setting(body.name, body.value, ACTOR)
    return {'ok': True}

@app.get('/api/audit/verify')
def verify(): return store.verify_audit_chain()
