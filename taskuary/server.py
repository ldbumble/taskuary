"""The local HTTP API + built-in minimal web UI. Localhost-only by default; set
[server].token in config to require an X-Taskuary-Token header (for LAN/self-hosting).
"""
import asyncio, collections, contextlib, copy, json, re, secrets, sys, threading, time, weakref
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
from .reports import (PLANNED, REGISTRY, note_app_up, render_report, resolve_cfg, run_due_reports,
                      run_report_source)
from . import agents as hub_agents
from . import cli_connections
from . import blackboard
from . import guard
from . import policy as policy_engine
from . import reshape
from . import terminal as hub_term
from .coder import PAUSE_MARKER, pause_note, reply_target as coder_reply_target, wrap as coder_wrap
from . import aisetup, assistant, demo, deps, learn, learnedgraph, operations, outbound, playbooks, rank, responder, waitroom
from . import live as live_bus
from . import processing_all

# whatever the owner's Install button added lives beside their data, not in the build - and it has
# to be importable BEFORE any card reaches for it (deps.py)
deps.use_packages()
cfg = config.load()
store = SQLiteStore(config.db_path())
# The workers Taskuary ships besides the coder, added to the CONFIG before the loop below copies it
# into the database - so they appear on the Agents page like `coder` does, and a restart never
# rewrites one the owner has changed (seed_profiles skips any name already there).
try:
    from loguru import logger as _log                    # loguru is not bound at module scope yet here
    _added = hub_agents.seed_profiles(cfg)
    _split_cli = cli_connections.migrate(cfg)
    if _split_cli:
        import shutil
        _config_file = config.home() / 'config.toml'
        _backup_file = config.home() / 'config.before-cli-connections.toml'
        if _config_file.exists() and not _backup_file.exists(): shutil.copy2(_config_file, _backup_file)
    if _added or _split_cli:
        config.save(cfg)
    if _added:
        _log.info(f"added the shipped agent profiles: {', '.join(_added)}")
except Exception as _e:
    from loguru import logger as _log
    _log.warning(f'could not seed the shipped agent profiles: {_e}')
cli_connections.sync(cfg, store)
try:
    # tasks routed to a CLI back when naming a worker named a brain (the 2026-09-16 spec)
    # name the brain this install is already running, once - the line that moves it onto the
    # brain layer, and onto exactly what it ran yesterday
    if hub_agents.adopt_brain_setting(store):
        from loguru import logger as _log
        _log.info(f"the brain layer is on: default_brain = {store.get_settings().get('default_brain')}")
    _repaired = hub_agents.repair_role_assignees(store)
    if _repaired:
        from loguru import logger as _log
        _log.info(f'corrected {_repaired} task(s) routed to a CLI rather than to a role')
except Exception as _e:
    from loguru import logger as _log
    _log.warning(f'could not correct routed roles: {_e}')
try:
    _adopted = cli_connections.adopt_installed(cfg, store)
    if _adopted:
        config.save(cfg)
        from loguru import logger as _log
        _log.info(f"every installed CLI can be started: added {', '.join(_adopted)}")
except Exception as _e:
    from loguru import logger as _log
    _log.warning(f'could not adopt the installed CLIs: {_e}')
try:
    # one coding role, one CODER.md: the per-CLI coding clones an older setup minted go
    _dropped = hub_agents.drop_cli_clones(cfg, store)
    if _dropped:
        config.save(cfg)
        from loguru import logger as _log
        _log.info(f"one coder for every CLI: dropped the coding clones {', '.join(_dropped)}")
except Exception as _e:
    from loguru import logger as _log
    _log.warning(f'could not drop the per-CLI coding clones: {_e}')
@asynccontextmanager
async def _lifespan(_app):
    live_bus.bind(asyncio.get_running_loop())
    is_demo = demo.enabled()
    if not is_demo:
        # Capture historical read results before startup catch-up, worker repair,
        # or New chat can change the inputs. Schema construction alone never cuts over.
        from .processing_startup import initialize
        initialize(store, live_state=[])
        from . import counsel as _counsel
        try: logger.info(f"COUNSEL migration: {_counsel.migrate(store)}")
        except Exception as e: logger.warning(f'COUNSEL migration skipped: {e}')
        # Preserve the owner's existing opt-out before bridges, catch-up, or drain
        # admission can ingest anything. Failure must not enable unattended work.
        store.upgrade_auto_start()
    if not _open_drain_workers(store):
        raise RuntimeError('previous triage drain still owns this store')
    # the demo builds its world and puts agents on the board BEFORE anything else runs - and
    # never polls, never bridges, never catches up on a mailbox that does not exist
    if is_demo:
        try:
            demo.seed(store)
            demo.start_sessions(store)
        except Exception as e: logger.warning(f'demo seed failed: {e}')
        async with processing_all.membership_lifecycle(store):
            yield
        return
    # No interactive or headless worker survives into this process. Repair any persisted
    # in-progress/running flags before the Board and funnel get their first read.
    hub_term.recover_after_restart(store)
    from . import wabridge
    try:
        wabridge.start_configured(store)      # the launch grace is spent by the first poll (wabridge.ready), never here
    except Exception as e: logger.warning(f'wa bridge startup failed: {e}')
    try:                                      # Codex's hooks write a spool, not a request (hooks.py): read it
        from . import hooks as _hooks
        _hooks.start_codex_spool()
    except Exception as e: logger.warning(f'codex hook spool not started: {e}')
    catch_up_on_startup()          # defined below; resolved when the app actually starts
    try:                           # a relaunch opens a NEW chat rather than resuming the last one
        from . import funnel as _f
        from .general import retire_dock
        if retire_dock(store, ACTOR) is not None: _f.reset_walk(store)
    except Exception as e: logger.warning(f'assistant dock retire failed: {e}')
    try:                           # archived chats past their keep-days go on the app's own clock (PW-158), never on a history read
        from . import retention
        retention.tick(store)
    except Exception as e: logger.warning(f'chat retention skipped: {e}')
    try:                           # ...and the WhatsApp bridge's own log, which loguru never sees
        from . import wabridge
        wabridge.trim_log(store)
    except Exception as e: logger.warning(f'whatsapp log trim skipped: {e}')
    _heal_owner_docs()
    _refresh_soul_connections()
    learn.note_verdicts(store)     # the evidence block in LEARNED.md tracks the verdict table
    try: blackboard.schedule_due(store)   # a retry that was backing off when the app closed is re-armed, not reset (PW-085)
    except Exception as e: logger.warning(f'retry scheduling skipped: {e}')
    try:                           # historical triage failures stored as filed become retriable errors, once (PW-040)
        n = store.upgrade_triage_failures()
        if n: logger.info(f'{n} historical triage failure(s) now show as errors with a retry')
    except Exception as e: logger.warning(f'triage-failure upgrade skipped: {e}')
    note_app_up(store, start=True)   # this launch, so a shut-overnight gap is not read as a dead scheduler
    threading.Thread(target=poll_forever, daemon=True).start()
    threading.Thread(target=quick_forever, daemon=True).start()   # the chat clock, never behind a slow sync
    threading.Thread(target=doorway_forever, daemon=True).start()  # the assistant chat, answered as fast as it is typed
    waitroom.watch(store)          # notes queued for a working agent land when it stops
    from . import msauth
    msauth.on_rotate = lambda cid, rt: store.save_connector({'ConnectorId': cid, 'Secret': rt}, 'msauth')   # a rotated Microsoft refresh token outlives a restart
    try:
        async with processing_all.membership_lifecycle(store):
            yield
    finally:
        if not _close_drain_workers(timeout=DRAIN_WAIT, target_store=store):
            logger.warning('triage drain still stopping during shutdown')
        # Both watched PTYs and one-shot CLI brains are children of this process. An orderly
        # Taskuary close owns them: leaving them alive creates invisible Claude/Codex sessions
        # that can keep consuming resources after there is no UI capable of reaching them.
        hub_term.shutdown_sessions()
        hub_agents.shutdown_cli_children()

app = FastAPI(title='Taskuary', docs_url='/api/docs', lifespan=_lifespan)
ACTOR = 'owner'
# Attaching a terminal repaints it: the rendered replay, then the one-column wiggle's full redraw.
# That output is ours, not the agent's, so idle() must not count it (Term.quiet_for).
ATTACH_QUIET = 10


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
    elif not guard.host_ok(request.headers.get('host'), cfg['server']):
        # EVERY path, not just /api: the page itself carries the owner token, so a name we do not
        # answer to must not be able to load it either (guard.host_ok on DNS rebinding)
        logger.warning(f'refused Host {request.headers.get("host")!r} - not a name this server answers to')
        return JSONResponse({'detail': f'this server does not answer to the name {request.headers.get("host")!r}. '
                                       'If you reach Taskuary by a hostname, add it to allowed_hosts under '
                                       '[server] in config.toml.'}, status_code=403)
    # ...and a request some OTHER page told the browser to make is not the owner asking, whatever
    # token the browser had lying around. The Intuit callback is the one cross-site arrival by
    # design - a redirect from their site, proving itself with the one-time state it was issued.
    elif (request.url.path.startswith('/api') and request.url.path not in ('/api/quickbooks/callback', '/api/zoho/callback')
          and not guard.origin_ok(request.headers)):
        logger.warning(f'refused {request.method} {request.url.path} from origin {request.headers.get("origin")!r}')
        return JSONResponse({'detail': 'this request came from another site. Taskuary answers its own '
                                       'pages only.'}, status_code=403)
    tok = cfg['server'].get('token')
    presented = request.headers.get('X-Taskuary-Token')
    if tok and request.url.path.startswith('/api') and not guard.token_matches(presented, tok, cfg['server'].get('agent_token')):
        # an <img src> cannot carry a header, so attachment READS take the token in the query
        # string - the same concession websockets already needed
        # ...and an OAuth callback is a redirect from the provider's site: no header can ride on it.
        # It proves itself with the one-time state it was issued (quickbooks_authorize), not the token.
        file_read = request.url.path.startswith(('/api/attachments/', '/api/task-artifacts/'))
        if not (file_read and guard.token_matches(request.query_params.get('token'), tok)) \
                and request.url.path not in ('/api/quickbooks/callback', '/api/zoho/callback'):
            # In JSON, like every other refusal: an HTML body left `detail` undefined, so a tab that
            # was open across a token change answered every click with whichever screen's generic
            # "that did not work" fallback happened to be nearest (2026-09-10 audit).
            return JSONResponse({'detail': 'This page is signed in with an out-of-date token - reload it.',
                                 'code': 'unauthorized'}, status_code=401)
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
    Assignee: str | None = None
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
class DecideBody(BaseModel):
    verb: str; final_text: str | None = None; note: str | None = None
    cc: list[str] | None = None      # loop somebody in on this answer (email only)
class CodeBody(BaseModel):
    repo: str | None = None; agent: str | None = None
    model: str | None = None; instruction: str | None = None
class DocBody(BaseModel): content: str
class SettingBody(BaseModel): name: str; value: str
class SourceBody(BaseModel):
    SourceId: int | None = None; ConnectorId: int | None = None; Channel: str | None = None
    Address: str | None = None; ConfigJson: str | None = None; Active: bool | None = None
class DispatchBody(BaseModel):
    # `agent` is the ROLE that works it; `brain` is WHICH CLI runs it. Two questions, and
    # answering both with one name is what sent TQ-0588's coding work to Copilot. `pick` is the
    # same question in the GENERAL namespace ('cli:<profile>' / 'connector:<id>'), which is what a
    # general session resolves and saves; a cli_connections key would mean nothing to it.
    agent: str | None = None; brain: str | None = None; pick: str | None = None
    instruction: str | None = None; model: str | None = None
    # The button says "Send to agent".  The task's Kind remains authoritative once a task
    # exists; this hint is only how an unpromoted message says which kind of task to create.
    kind: str | None = None
class PolicyBody(BaseModel):
    PolicyId: int | None = None; Name: str | None = None; Kind: str | None = None
    Pattern: str | None = None; Action: str | None = None; Reason: str | None = None
    SortOrder: int | None = None; Active: bool | None = None
class MemoryBody(BaseModel):
    note: str; scope: str = 'global'; scope_key: str | None = None
    source: str = 'manual'          # 'writing' = an instruction about how to write, read by the drafter only (PW-060)
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
            'Cache-Control': 'no-store, must-revalidate', 'Retry-After': '1',
            'X-Content-Type-Options': 'nosniff'})
    return HTMLResponse(_seed_token(html), headers={
        'Cache-Control': 'no-store, must-revalidate',
        'X-Content-Type-Options': 'nosniff',
        'Referrer-Policy': 'same-origin',
        'X-Frame-Options': 'DENY'})


def _seed_token(html: str) -> str:
    """The page the SERVER hands out carries the owner token. That is what makes a mandatory token
    cost the owner nothing: no other site can read this HTML (it is same-origin, and a name we do
    not answer to never gets it - token_gate checks Host first), and the app has its credential
    before the bundle's first fetch. A tab opened before the upgrade 401s until it is reloaded,
    which is the whole of the migration (audit 2026-09-02, F03)."""
    tok = cfg['server'].get('token')
    if not tok or '</head>' not in html: return html
    seed = f'<script>try{{localStorage.setItem("taskuary_token",{json.dumps(tok)})}}catch(e){{}}</script>'
    return html.replace('</head>', seed + '</head>', 1)


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
# ...and the walk's shots of each tab. NOT under /assets: those are vite's hashed build output, and
# these are files the repo ships and the page names by a fixed path (walk.STOPS holds `/walk/x.png`),
# so mounting /assets never covered them. It was missing for a whole branch - the files were on disk,
# in the bundle and in the wheel, and every one of the nine 404ed because no route served them.
# check_dir=False for the same reason as /assets: a source checkout that has not been built yet has
# no web/ at all, and the server must still start (it answers the self-healing 503 above).
app.mount('/walk', StaticFiles(directory=str(_web_root / 'walk'), check_dir=False), name='walk')

from fastapi.responses import FileResponse

@app.get('/favicon.ico', include_in_schema=False)
def favicon(): return FileResponse(Path(__file__).parent / 'web' / 'favicon.ico')

@app.get('/favicon.png', include_in_schema=False)
def favicon_png(): return FileResponse(Path(__file__).parent / 'web' / 'favicon.png')


from . import __version__ as _ver
_started = datetime.now().isoformat(sep=' ', timespec='seconds')

@app.get('/api/version')
def version(): return {'version': _ver, 'started': _started, 'cli_installer_revision': 2}

# ── update in place (update.py): Settings → Updates ─────────────────────────────────────
@app.get('/api/update')
def update_check(force: int = 0):
    from . import update
    return update.check(force=bool(force))

@app.post('/api/update')
def update_apply():
    """Fetch the latest release and swap it in. The answer goes out first; the process ends a
    moment later so the new build can start. Owner-only: guard.py refuses an agent token."""
    from . import update
    try: out = update.apply()
    except Exception as e: raise HTTPException(422, str(e))
    # Once apply() returns, the swap helper is ALREADY RUNNING and waiting for this process to go.
    # Anything that throws between here and exit_soon strands it on a PID that never dies - which
    # is how one machine was left with no app and a console spinning on `find "<pid>"`
    # (2026-09-15). The audit row is worth writing and is not worth the app for.
    try: store.audit('app', 0, 'update', ACTOR, detail={k: v for k, v in out.items() if k != 'pip'})
    except Exception as e: logger.warning(f'update: could not write the audit row, restarting anyway - {e}')
    if out.get('restarting'): update.exit_soon()
    return out

def _send_block(channel, has_message=True) -> str:
    """The reason an approved reply could not leave on this channel - outbound.send_block's words,
    '' when it can. Rides on feed rows and reviews as SendBlock, so every surface shows the same
    sentence beside a draft it cannot send (PW-044)."""
    if not has_message: return 'nothing arrived to reply to'
    return outbound.send_block(store, channel)


def _can_send(channel, has_message=True, gh_ok=None) -> bool:
    """Can an approved reply actually LEAVE on this channel? One answer for the whole app -
    outbound.can_reply - so the Approve button, triage and the coder wrap-up cannot
    disagree. The UI turns an unsendable draft's Approve into 'No response required'."""
    if not has_message: return False
    return outbound.can_reply(store, channel)


def _send_state(memo: dict, channel, has_message=True) -> tuple:
    """(CanSend, SendBlock) for one channel, answered once per request. The email probe reads the
    connector cards (PW-143) and a 500-row Timeline must not read them 500 times."""
    k = (str(channel or '').lower(), bool(has_message))
    if k not in memo:
        ok = _can_send(channel, has_message)
        memo[k] = (ok, '' if ok else _send_block(channel, has_message))
    return memo[k]


@app.get('/api/feed')
def feed(limit: int = 100, offset: int = 0, pending_only: bool = False, channel: str = None, source: str = None,
         request: Request = None):
    try: days = int(store.get_settings().get('feed_days') or 14)
    except (TypeError, ValueError): days = 14        # a blanked number field saves '' - the Timeline must not die of it
    tag = '"' + store.feed_tag(days, pending_only, channel, source) + '"'
    if request is not None and request.headers.get('if-none-match') == tag:
        return Response(status_code=304, headers={'ETag': tag, 'Cache-Control': 'no-cache'})
    rows = store.feed(min(limit, 500), days, pending_only, channel, max(offset, 0), source)
    memo = {}
    for r in rows:
        r['CanSend'], r['SendBlock'] = _send_state(memo, r.get('Channel'), True)
    return JSONResponse({'data': rows}, headers={'ETag': tag, 'Cache-Control': 'no-cache'})


def _processing_live():
    try:
        return hub_term.live_sessions(tail=0)
    except Exception:
        return None  # Unavailable observation is distinct from an observed empty roster.


@app.exception_handler(processing_all.AllError)
async def _all_error(_request, error: processing_all.AllError):
    # every route that reads the inventory can meet this; one answer, the same JSON the explicit catches give
    return JSONResponse({'detail': error.detail}, status_code=error.status)

@app.get('/api/processing/all')
def processing_all_page(limit: int = 100, cursor: str = None, channel: str = None, source: str = None):
    try:
        days = int(store.get_settings().get('feed_days') or 14)
    except (TypeError, ValueError):
        days = 14
    try:
        return processing_all.inventory.page(store, limit=limit, cursor=cursor, channel=channel,
                                             source=source, days=days, live_state=_processing_live())
    except processing_all.AllError as exc:
        raise HTTPException(exc.status, exc.detail) from exc


@app.get('/api/processing/items/{item_id}/detail')
def processing_item_detail(item_id: str, kind: str = None, id: int = None, view_revision: str = None):
    try:
        result = processing_all.item_detail(store, item_id, kind=kind, local_id=id,
                                             view_revision=view_revision, live_state=_processing_live())
        row = result.get('row')
        detail = result.get('detail') or {}
        if detail.get('task'):
            detail['artifacts'] = [_artifact_row(a) for a in detail.get('artifacts') or []]
        if row is not None:
            row['CanSend'] = _can_send(row.get('Channel'), True, store.github_replies_ok())
            row['SendBlock'] = '' if row['CanSend'] else _send_block(row.get('Channel'), True)
            result['detail_revision'] = processing_all._digest({key: value for key, value in result.items()
                                                               if key != 'detail_revision'})
        return result
    except processing_all.AllError as exc:
        raise HTTPException(exc.status, exc.detail) from exc


def _queued_info(q):
    """The card's hover text for a held-back dispatch: what it waits for, and why."""
    if not q: return None
    b = q.get('BehindTaskId')
    return {'behind': task_ref(b) if b else None, 'value': q.get('Value'), 'why': q.get('Why'),
            'behindTitle': (store.get_task(b) or {}).get('Title') if b else None,
            'reason': q.get('Reason'), 'since': q.get('CreatedAt'),
            # the retry budget (PW-085..087): waiting | retrying | failed, how many tries, the last error and the next one
            'state': q.get('State') or 'waiting', 'attempts': int(q.get('Attempts') or 0), 'lastError': q.get('LastError'), 'nextAt': q.get('NextAt')}


def _playbook_brief(task, books=None):
    """The existing job description attached to a task, shaped for the work surfaces.

    This deliberately is not an agent capability profile. A named worker can perform different
    kinds of work; the task's playbook says which job it is doing this time.
    """
    slug = playbooks.of_task(task)
    if not slug: return None
    found = (books or {}).get(slug) if books is not None else playbooks.for_task(task)
    uses = (found or {}).get('uses') or []
    if isinstance(uses, str): uses = playbooks.uses_of(found or {})
    return {'slug': slug, 'title': (found or {}).get('title') or slug.replace('-', ' '),
            'uses': uses, 'missing': found is None}

@app.get('/api/tasks')
def tasks(status: str = None, active: bool = False, search: bool = False):
    """An interactive session IS an agent working - the UI has to see it, or a task with a
    live CLI on it reads as 'queued' while the agent sits there asking a question.

    `search` asks for the message-search blobs the Tasks tab filters on locally. They aggregate
    the whole message table (see store.list_tasks) and were 34ms of a 35ms query plus 69KB of a
    319KB payload on a real store, so opening a tab no longer pays for a search nobody ran."""
    qs = {q['TaskId']: q for q in store.queued_dispatches()}
    wc = store.waiting_counts()
    agented = store.agented_task_ids()      # the Board's Done lane shows agent work only
    books = {b['slug']: b for b in playbooks.list_all()}
    # One lightweight pass over the live sessions. for_task() used to scan the roster and build
    # the FULL session payload (including git status and witness reconciliation) for every task;
    # with hundreds of tasks that made Tasks and Board wait behind repository I/O.
    sessions = {s['taskId']: s for s in hub_term.live_sessions(tail=0, details=False) if s.get('taskId')}
    return {'data': [{**t, 'ref': task_ref(t['TaskId']), 'Playbook': _playbook_brief(t, books),
                      'Session': sessions.get(t['TaskId']),
                      'Queued': _queued_info(qs.get(t['TaskId'])), 'Waiting': wc.get(t['TaskId'], 0),
                      'HadAgent': t['TaskId'] in agented}
                     for t in store.list_tasks(status, active_only=active, search=search)]}

@app.post('/api/tasks')
def create_task(body: TaskBody):
    if not body.Title: raise HTTPException(422, 'Title is required')
    tid = store.create_task({k: v for k, v in body.dict().items() if v is not None}, ACTOR)
    # A task created by the owner is their durable TODO. Agent runs may come and go without
    # silently completing it; only routed/triaged work is eligible for automatic completion.
    from . import selfclose
    selfclose.claim(store, tid, ACTOR)
    store.audit('task', tid, 'create', ACTOR)
    return {'taskId': tid, 'ref': task_ref(tid)}


@app.post('/api/assistant/dock')
def assistant_dock():
    """Return the one durable conversation behind the floating Taskuary guide.

    It uses the normal general-work session and comment history, but SourceRef keeps this
    application-level conversation off the owner's task list and Timeline.
    """
    from .general import dock_task
    task, created = dock_task(store, ACTOR)
    return {'task': task, 'ref': task_ref(task['TaskId']), 'created': created}


@app.post('/api/assistant/dock/new')
def assistant_dock_new(background: BackgroundTasks):
    from .processing_navigation import chat_change
    with chat_change(store):
        return _assistant_dock_new(background)


def _assistant_dock_new(background: BackgroundTasks):
    """Archive the current dock conversation and return a genuinely fresh one.

    A client-side clear is dishonest here: the model session and the task comments would still
    carry the old context. The old hidden task remains the durable record, while its replacement
    starts with no messages. Reviews and tasks are separate workspace state and remain available.
    """
    from . import general
    old, _created = general.dock_task(store, ACTOR)
    session = general.session_for(old['TaskId'])
    if session and session.busy:
        raise HTTPException(409, 'Taskuary is still answering. Stop it or wait before starting a new chat.')
    store.update_task(old['TaskId'], {'Status': 'done'}, ACTOR)
    store.audit('task', old['TaskId'], 'archive_assistant_dock', ACTOR)
    from . import funnel, concierge
    funnel.reset_walk(store)       # the new chat walks the pipe afresh; what was decided stands
    store.set_setting(f"{concierge.SID_KEY}:{old['TaskId']}", '', ACTOR)   # a new chat is a new CLI conversation too
    if session:
        # Closing is also the conservative point where the Hub may retain hard-earned knowledge.
        # That can call an AI, so it belongs after the response rather than delaying New chat.
        background.add_task(session.close)
    task, created = general.dock_task(store, ACTOR)
    return {'task': task, 'ref': task_ref(task['TaskId']), 'created': created,
            'archivedTaskId': old['TaskId']}

class ChecklistTick(BaseModel):
    done: bool = True


class ChecklistEdit(BaseModel):
    items: list


@app.patch('/api/tasks/{task_id}/checklist/{item_id}')
def tick_checklist(task_id: int, item_id: str, body: ChecklistTick):
    """One box - and the LAST box is the close. PW-077 kept a tick from ever completing a task so
    that an agent's progress could not end the owner's work; this is the owner's own hand on the
    owner's own list, and with every item ticked there is nothing left of the task but its row -
    which sat on the rail for a day (TQ-0626; the owner, 2026-09-18: "it did not close even though
    i ticked the items"). A task an agent holds is left alone: closing it would stop the agent."""
    t = store.get_task(task_id)
    if not t: raise HTTPException(404, 'task not found')
    if not store.tick_checklist_item(task_id, item_id, body.done, ACTOR): raise HTTPException(404, 'no such checklist item')
    items, closed = store.task_checklist(task_id), False
    if (body.done and items and all(i.get('done') for i in items) and t.get('Status') == 'open'
            and not str(t.get('Assignee') or '').startswith('agent:')):
        from . import concierge
        closed = concierge.close_task(store, task_id, ACTOR)          # the same road as Completed and "close it"
        if closed: store.add_comment(task_id, ACTOR, 'human', 'Closed - the last item on the checklist was ticked.')
    return {'ok': True, 'checklist': items, 'closed': closed}


@app.put('/api/tasks/{task_id}/checklist')
def edit_checklist(task_id: int, body: ChecklistEdit):
    """The owner's words for the list; a box whose words are unchanged keeps its state (PW-076)."""
    if not store.get_task(task_id): raise HTTPException(404, 'task not found')
    return {'ok': True, 'checklist': store.set_task_checklist(task_id, body.items, ACTOR)}


# ── shared operations (operations.py): propose, edit, confirm once, and the durable record ──────
class OperationBody(BaseModel): kind: str; target: int; params: dict = {}
class OperationEdit(BaseModel): params: dict
class OperationConfirm(BaseModel): version: int
class DiscussBody(BaseModel): body: str; actor: str = 'owner'

def _run_operation(op: dict, background: BackgroundTasks):
    """The shared handler for each kind - the same code the task page and the timeline run."""
    kind, tid, mid, p = op['kind'], op['target'], op['target'], op['params'] or {}
    if kind == 'task.create_from_message':
        k = str(p.get('kind') or 'task').lower()
        if k == 'general': return chat_message(mid, background)
        if k == 'coding':
            out = dispatch_message(mid, DispatchBody(kind='coding', agent=p.get('agent'), brain=p.get('brain'),
                                                     instruction=p.get('instructions'), model=p.get('model')), background)
            # a repository still to choose is a decision, not a start: the item stays where it is (PW-135)
            if out.get('dispatch') == 'needs_repo':
                raise operations.Halt(f"{out.get('ref') or 'it'} needs a repository first - {out.get('reason') or 'pick one'}", out)
            return out
        return mine_message(mid, MineBody(kind='task', title=p.get('title')), background)
    if kind == 'message.file': return file_message(mid, NotATaskBody(learn=bool(p.get('learn', True))), background)
    if kind == 'message.reply': return open_reply(mid, None)
    if kind == 'dispatch.prepare':
        # ...through the task's own dispatch DOOR, not the handler underneath it: the door is where a
        # repository the agent cannot open becomes a decision (`needs_repo`) instead of a 422. Calling
        # the handler directly skipped that, so the task page's Start showed "422: I could not tell which
        # checkout this belongs in" as a dead end - and its advice named a task menu the card redesign
        # had already removed (the owner, 2026-09-22: "don't see anywhere on agent or task to choose repo").
        out = dispatch_task(tid, DispatchBody(kind=p.get('kind'), agent=p.get('agent'), brain=p.get('brain'),
                                              instruction=p.get('instructions'), model=p.get('model')), background)
        if out.get('dispatch') == 'needs_repo':
            raise operations.Halt(f"{out.get('ref') or 'it'} needs a repository first - {out.get('reason') or 'pick one'}", out)
        return out
    if kind == 'task.set_kind':
        if str(p.get('kind')) == 'task': return not_coding(tid, NotATaskBody(learn=bool(p.get('learn', True))), background)
        # ...and every other kind down the task page's own road, not a bare field write. Writing
        # the column directly skipped BOTH things the PATCH does: it taught nothing (so "hand it
        # to the assistant" from a card was the one reclassification that never reached either
        # memory) and it left a live session attached to a task that had changed worker mode.
        update_task(tid, TaskBody(Kind=str(p.get('kind'))), background)
        return {'kind': p.get('kind')}
    if kind == 'task.not_a_task': return not_a_task(tid, NotATaskBody(learn=bool(p.get('learn', True))), background)
    if kind == 'routing.remember':
        # the assistant teaching the routing memory in words, which it could not do at all: it could
        # keep a free-text fact (memory.remember) that every verdict then reads, but not a SCOPED,
        # weighted one about this sender and this field. Teaching only - the task is not moved.
        from . import routingmemory as rmem
        field, value = str(p.get('field') or '').strip().lower(), str(p.get('value') or '').strip()
        if field not in rmem.FIELDS: raise HTTPException(422, f"a routing lesson is about {', '.join(rmem.FIELDS)} - not {field or 'nothing'}")
        if not value: raise HTTPException(422, 'say what it should have been')
        if not store.get_task(tid): raise HTTPException(404, 'task not found')
        taught = _teach_routing(tid, field, value, background=background)
        if not taught: return {'field': field, 'value': value, 'learned': 0, 'already': True}
        store.add_comment(tid, ACTOR, 'human', f'You told the assistant: work like this is {field} {value}. Triage learns from it.')
        return {'field': field, 'value': value, **taught}
    # THE APP ITSELF, BY NAME (the assistant-runs-the-app design, 2026-09-18). Each handler runs the road
    # the tab's own button runs, audits as the assistant, and hands back an `undo` the receipt can offer.
    if kind in ('report.run', 'report.pause', 'report.resume', 'report.reach', 'report.edit', 'report.delete'):
        src = store.get_source(tid)
        if not src or src.get('Channel') != 'report': raise HTTPException(404, 'no such report')
        cfg = json.loads(src.get('ConfigJson') or '{}') or {}
        title = cfg.get('title') or src.get('Address')
        if kind == 'report.run':
            from . import remote_assistant
            out = _rerun_report(tid, asked=remote_assistant.asking())
            return {**out, 'title': title, 'undo': None}
        if kind in ('report.pause', 'report.resume'):
            on = kind == 'report.resume'
            store.save_source({'SourceId': tid, 'Active': int(on)}, ACTOR)
            store.audit('source', tid, 'resume' if on else 'pause', 'assistant', detail={'title': title})
            return {'title': title, 'active': on,
                    'undo': {'kind': 'report.pause' if on else 'report.resume', 'target': tid, 'params': {}, 'label': f"{'Pause' if on else 'Resume'} {title}"}}
        if kind == 'report.reach':
            from .reports import REACH, reach_of
            want, prev = str(p.get('reach') or '').strip().lower(), reach_of(cfg)
            if want not in REACH: raise HTTPException(422, f"a report reaches you {', '.join(REACH)} - not {want or 'nothing'}")
            store.save_source({'SourceId': tid, 'ConfigJson': json.dumps({**cfg, 'reach': want})}, ACTOR)
            store.audit('source', tid, 'reach', 'assistant', detail={'title': title, 'from': prev, 'to': want})
            return {'title': title, 'reach': want, 'undo': {'kind': 'report.reach', 'target': tid, 'params': {'reach': prev}, 'label': f'Put {title} back to reaching you: {prev}'}}
        if kind == 'report.edit':
            patch = p.get('config') if isinstance(p.get('config'), dict) else {}
            if not patch: raise HTTPException(422, 'say what to change - config is the keys to change')
            if 'title' in patch and not str(patch['title'] or '').strip(): raise HTTPException(422, 'a report needs a title')
            new = {**cfg, **patch}
            store.save_source({'SourceId': tid, 'ConfigJson': json.dumps(new)}, ACTOR)
            store.audit('source', tid, 'edit', 'assistant', detail={'title': title, 'changed': sorted(patch)})
            return {'title': new.get('title') or title, 'changed': sorted(patch),
                    'undo': {'kind': 'report.edit', 'target': tid, 'params': {'config': {k: cfg.get(k) for k in patch}}, 'label': f'Put {title} back as it was'}}
        delete_source(tid)
        store.audit('source', tid, 'delete', 'assistant', detail={'title': title})
        return {'title': title, 'deleted': True, 'undo': None}
    if kind == 'setting.set':
        from . import settings_schema
        key, meta = str(p.get('setting') or '').strip(), settings_schema.knobs().get(str(p.get('setting') or '').strip())
        if not meta: raise HTTPException(422, f'{key or "that"} is not a setting the schema knows')
        raw, t = p.get('value'), meta.get('type')
        v = str(raw if raw is not None else '').strip()
        if t == 'switch': v = '1' if v.lower() in ('1', 'true', 'on', 'yes') else '0' if v.lower() in ('0', 'false', 'off', 'no') else None
        elif t == 'number': v = str(int(float(v))) if v.replace('.', '', 1).lstrip('-').isdigit() else None
        elif t == 'select': v = v if v in [str(o) for o in (meta.get('options') or [])] else None
        if v is None: raise HTTPException(422, f"{meta['label']} takes {'on or off' if t == 'switch' else 'a number' if t == 'number' else 'one of ' + ', '.join(str(o) for o in meta.get('options') or [])} - not {raw!r}")
        prev = store.get_settings().get(key)
        store.set_setting(key, v, ACTOR)
        store.audit('setting', 0, 'set', 'assistant', detail={'key': key, 'from': prev, 'to': v})
        said = settings_schema.describe(key, v)
        return {'key': key, 'label': meta['label'], 'value': v, 'said': said,
                'undo': {'kind': 'setting.set', 'target': 0, 'params': {'setting': key, 'value': prev if prev is not None else ''},
                         'label': f"Put {meta['label']} back to {settings_schema.describe(key, prev).split(': ', 1)[-1]}"}}
    if kind in ('connection.test', 'connection.pause', 'connection.resume'):
        c = store.get_connector(tid)
        if not c: raise HTTPException(404, 'connector not found')
        name = c.get('Name') or c.get('Type')
        if kind == 'connection.test':
            from .channels import test_connector
            out = test_connector(store, tid)
            store.audit('connector', tid, 'test_ok' if out.get('ok') else 'test_failed', 'assistant', detail=out.get('detail'))
            return {'name': name, 'ok': bool(out.get('ok')), 'detail': out.get('detail'), 'undo': None}
        on = kind == 'connection.resume'
        store.save_connector({'ConnectorId': tid, 'Active': int(on)}, ACTOR)
        store.audit('connector', tid, 'resume' if on else 'pause', 'assistant', detail={'name': name})
        return {'name': name, 'active': on,
                'undo': {'kind': 'connection.pause' if on else 'connection.resume', 'target': tid, 'params': {}, 'label': f"{'Switch off' if on else 'Switch on'} {name}"}}
    if kind == 'script.start':
        return {'script': str(p.get('name') or ''), 'undo': None}
    if kind == 'task.complete':
        # the same close the PATCH road does: the pending draft is dismissed and the agent on it is stopped
        from . import concierge
        if not store.get_task(tid): raise HTTPException(404, 'task not found')
        return {'status': 'done', 'already': not concierge.close_task(store, tid, ACTOR)}
    if kind == 'task.reopen':
        if not store.get_task(tid): raise HTTPException(404, 'task not found')
        store.update_task(tid, {'Status': 'open'}, ACTOR); return {'status': 'open'}
    # the assistant's proposals (concierge.PROPOSALS): each runs the same code the page's own button runs
    if kind == 'task.create_from_text':
        from . import concierge
        return concierge.handoff_task(store, str(p.get('text') or ''), str(p.get('kind') or 'coding'), ACTOR, title=p.get('title'))
    if kind == 'task.setup':
        from . import concierge
        return concierge.setup_task(store, str(p.get('text') or ''), ACTOR)
    if kind == 'message.archive': return file_message(mid, NotATaskBody(learn=False, archive=True), background)
    if kind == 'preference.exclude_sender': return not_mine(mid, NotMineBody(scope=str(p.get('scope') or 'sender')), background)
    # the bigger hammer, down the SAME road the card's own button took (ignore_sender, how='rule')
    if kind == 'preference.sender_rule': return ignore_sender(mid, IgnoreSenderBody(how='rule'), background)
    # the bigger hammer, down the SAME road the card's own button took (ignore_sender, how='rule')
    if kind == 'preference.sender_rule': return ignore_sender(mid, IgnoreSenderBody(how='rule'), background)
    if kind == 'item.settle':
        from . import funnel, verdicts
        verb = str(p.get('verb') or 'done')
        out = funnel.settle(store, str(p.get('key')), verb, ACTOR, p.get('hours'),
                            expected_context=p.get('processing_context'))
        # done on a task-backed item means the TASK is done: its pending draft is dismissed and it closes
        if verb == 'done' and p.get('kind') != 'agent':
            rv = store.get_review(int(p['rid'])) if p.get('rid') else None
            if rv and rv.get('Status') in ('pending', 'held'): verdicts.decide(store, rv, 'no_reply', None, 'handled - the owner said so', ACTOR)
            t = store.get_task(int(p['tid'])) if p.get('tid') else None
            if t and t.get('Status') not in ('done', 'dropped'): store.update_task(int(p['tid']), {'Status': 'done'}, ACTOR); out['closed'] = int(p['tid'])
        return out
    if kind == 'review.approve':
        if not store.get_review(tid): raise HTTPException(404, 'review not found')
        out = decide(tid, DecideBody(verb='approve'), background)
        if not out.get('ok'): raise RuntimeError(out.get('send_error') or 'the reply was not sent')
        return out
    if kind == 'agent.answer':
        # the exact outstanding request of the run that asked (PW-138/139); nothing asked = the waiting room (PW-140)
        from . import workerstate as ws
        out = ws.answer_open(store, tid, str(p.get('text') or 'yes'), ACTOR)
        if out['state'] == 'no_request': return waitroom_add(tid, {'text': str(p.get('text') or 'yes')})
        if not out['delivered']: raise RuntimeError(f"{out['state']}: {out.get('why') or ''}")
        return out
    if kind == 'agent.stop': return _wrap_task(tid, True) if p.get('wrap') else stop_task_agent(tid)
    if kind == 'report.rerun': return report_rerun(tid)
    if kind == 'memory.remember':
        from . import concierge
        return {'memoryId': concierge.remember_fact(store, str(p.get('note') or ''), ACTOR)}
    if kind == 'task.split':
        from . import concierge, funnel
        item = (funnel.next_item(store, p['key']) if p.get('key') else None) or {'tid': tid, 'key': p.get('key')}
        return concierge.split_item(store, item, str(p.get('text') or ''), ACTOR)
    if kind == 'report.create':
        # the same road the Reports tab takes (validate, then save_source) - never an assistant-only path (PW-194)
        from . import compose
        cfg = dict(p.get('config') or {})
        ok, why = compose.validate(store, cfg)
        if not ok: raise RuntimeError(why)
        title = str(cfg.get('title') or '').strip()
        if any(x.get('Channel') == 'report' and str(x.get('Address') or '').casefold() == title.casefold() for x in store.list_sources(active_only=False)):
            raise RuntimeError(f'a report named {title!r} already exists - open it on the Reports tab')
        enabled = bool(p.get('enabled', True))
        out = save_source(SourceBody(Channel='report', Address=title, Active=enabled, ConfigJson=json.dumps(cfg)))
        return {**out, 'title': title, 'type': cfg.get('type'), 'enabled': enabled, 'link': f"#report={out['sourceId']}"}
    if kind == 'connection.create':
        # the same road the Connections tab takes; a secret never rides a proposal, and the card stays off until authorized (PW-196)
        from . import concierge
        typ, name = str(p.get('type') or ''), str(p.get('name') or '')
        cfg = {k: v for k, v in (p.get('config') or {}).items() if not concierge.SECRET_WORDS.search(str(k))}
        body = (ConnectorBody(ConnectorId=tid, ConfigJson=json.dumps(cfg) if cfg else None, Scope=p.get('scope') or None) if tid
                else ConnectorBody(Type=typ, Name=name, ConfigJson=json.dumps(cfg) if cfg else None, Scope=p.get('scope') or None, Active=False))
        out = save_connector(body)
        c = store.get_connector(out['connectorId'], with_secret=True) or {}
        state = ('authorization pending' if not c.get('Secret') else 'connected' if c.get('LastSyncAt') and not c.get('LastError')
                 else 'validation failed' if c.get('LastError') else 'saved, not yet verified')
        return {'connectorId': out['connectorId'], 'type': c.get('Type') or typ, 'name': c.get('Name') or name, 'state': state,
                'active': bool(c.get('Active')), 'link': f"#connector={out['connectorId']}"}
    if kind == 'pipe.clear':
        from . import concierge
        # a SELECTOR names a set exactly (category/kind/lane/sender/contains/age); the word-matching
        # road stays for the sentences that name a subject rather than a class
        if p.get('select'):
            out = concierge.clear_selected(store, p['select'], ACTOR)
            return out
        out = concierge.clear_matching(store, str(p.get('text') or ''), ACTOR, hint=str(p.get('hint') or ''))
        # a standing RULE already keeps these out of the pipe; a sender-wide verdict on top of it would reach
        # everything that person ever sends, which is not what "don't need these" means
        if out.get('remember') and out.get('mid') and not out.get('rules'):
            try: not_mine(int(out['mid']), NotMineBody(scope='sender'), background)
            except Exception as e: logger.warning(f'the sweep happened but the sender was not silenced: {e}')
        return out
    raise HTTPException(501, f'{kind} has no shared handler yet')

@app.post('/api/operations/{oid}/preview')
def preview_operation(oid: str):
    """A dry run of a proposed report (PW-195): read-only, files nothing, sends nothing, activates nothing, starts nothing."""
    from . import scopes
    op = operations.get(store, oid)
    if not op or op['kind'] != 'report.create': raise HTTPException(404, 'nothing to preview')
    cfg = dict((op['params'] or {}).get('config') or {})
    if scopes.needs(cfg.get('type')) != 'read':
        raise HTTPException(422, f"{cfg.get('type')} writes to a system - a dry run could too; run it from the Reports tab once created")
    for k in ('deliver', 'alert', 'triage', 'on_startup', 'cron', 'every_minutes', 'daily_at'): cfg.pop(k, None)
    return report_preview(cfg)

@app.post('/api/operations')
def propose_operation(body: OperationBody):
    try: return operations.propose(store, body.kind, body.target, body.params, ACTOR)
    except ValueError as e: raise HTTPException(422, str(e))

@app.get('/api/operations/{oid}')
def get_operation(oid: str):
    op = operations.get(store, oid)
    if not op: raise HTTPException(404, 'no such proposal')
    return op

@app.patch('/api/operations/{oid}')
def edit_operation(oid: str, body: OperationEdit):
    try: return operations.revise(store, oid, body.params, ACTOR)
    except ValueError as e: raise HTTPException(404 if 'no such' in str(e) else 422, str(e))

@app.delete('/api/operations/{oid}')
def cancel_operation(oid: str):
    try: return operations.cancel(store, oid, ACTOR)
    except ValueError as e: raise HTTPException(404, str(e))

@app.post('/api/operations/{oid}/execute')
def execute_operation(oid: str, body: OperationConfirm, background: BackgroundTasks):
    """The confirmation button: the structured proposal, by id and version - never a phrase sent back
    through an interpreter. Stale or cancelled is 409 with the reason; a failed handler is reported as
    such; a repeated click is the first receipt again (PW-124, PW-125)."""
    op = operations.get(store, oid)
    if not op: raise HTTPException(404, 'no such proposal')
    out = operations.execute(store, oid, body.version, lambda: _run_operation(op, background), ACTOR)
    # the receipt is the fact of what happened, in the chat, after it happened (PW-125)
    from . import concierge
    try: concierge.receipt(store, out, ACTOR)
    except Exception as e: logger.debug(f'no receipt recorded for {oid}: {e}')
    if out['status'] in ('stale', 'cancelled'): raise HTTPException(409, out.get('error') or out['status'])
    return out

@app.get('/api/tasks/{task_id}/history')
def task_history(task_id: int):
    if not store.get_task(task_id): raise HTTPException(404, 'task not found')
    return {'data': operations.history(store, task_id=task_id)}

@app.get('/api/messages/{mid}/history')
def message_history(mid: int):
    if not store.get_message(mid): raise HTTPException(404, 'message not found')
    return {'data': operations.history(store, message_id=mid)}

@app.post('/api/tasks/{task_id}/discussion')
def task_discuss(task_id: int, body: DiscussBody):
    if not store.get_task(task_id): raise HTTPException(404, 'task not found')
    try: return {'id': operations.discuss(store, body.actor, body.body, task_id=task_id)}
    except ValueError as e: raise HTTPException(422, str(e))

@app.post('/api/messages/{mid}/discussion')
def message_discuss(mid: int, body: DiscussBody):
    if not store.get_message(mid): raise HTTPException(404, 'message not found')
    try: return {'id': operations.discuss(store, body.actor, body.body, message_id=mid)}
    except ValueError as e: raise HTTPException(422, str(e))


# ── the worker's own word on its state (workerstate.py) ────────────────────────────────────────
class WorkerAnswerBody(BaseModel): request_id: str; text: str

@app.get('/api/tasks/{task_id}/worker')
def worker_status(task_id: int):
    """Working, input needed (the question), approval needed (the action), finished (the result), failed,
    disconnected, stopped - or unknown; derived from explicit events, never from the screen (PW-222/226)."""
    if not store.get_task(task_id): raise HTTPException(404, 'task not found')
    from . import workerstate as ws
    return ws.status(store, task_id)

@app.post('/api/tasks/{task_id}/worker/answer')
def worker_answer(task_id: int, body: WorkerAnswerBody):
    """Deliver an answer to ONE outstanding request of the run that asked it (PW-139/141): once; 409 when it is
    resolved already or the run changed; 422 when there is no live worker or delivery failed."""
    if not store.get_task(task_id): raise HTTPException(404, 'task not found')
    from . import workerstate as ws
    try: out = ws.answer(store, task_id, body.request_id, body.text, ACTOR)
    except ValueError as e: raise HTTPException(422, str(e))
    if not out['delivered']:
        raise HTTPException(409 if out['state'] in ('resolved', 'stale') else 422, f"{out['state']}: {out.get('why') or ''}")
    return out


@app.get('/api/tasks/{task_id}')
def task_detail(task_id: int):
    d = store.task_detail(task_id)
    if not d: raise HTTPException(404, 'task not found')
    # a session that has ended still leaves work to close out, so the page has to know one
    # happened - the Done and Pause buttons used to vanish with the pty
    tr = store.last_transcript(task_id)
    rs = _resumable(task_id)[0]
    return {**d, 'task': {**d['task'], 'Playbook': _playbook_brief(d['task'])},
            'artifacts': [_artifact_row(a) for a in d.get('artifacts') or []],
            # The detail page only needs lifecycle here; its terminal pane and optional WorkStrip
            # load their own rich data. Do not block selecting a task on git status.
            'session': hub_term.for_task(task_id, tail=3, details=False),
            'transcript': {'sid': tr['Sid'], 'agent': tr['Agent'], 'cwd': tr['Cwd'], 'brain': tr['Brain'],
                           'at': tr['CreatedAt'], 'chars': len(tr['Text'] or '')} if tr else None,
            # ...and WHICH BRAIN ACTUALLY RAN IT, for a session that has ended (_ran_on)
            'ranOn': _ran_on(task_id, tr),
            # ...and whether that ended session can be REOPENED rather than replaced. The id itself
            # stays here: the page needs to know a conversation is waiting, not how to address it.
            'resumable': {'sid': rs['Sid'], 'agent': rs['Agent'], 'cwd': rs['Cwd'], 'at': rs['CreatedAt']} if rs else None}


def _ran_on(task_id: int, tr=None):
    """Which brain actually ran this task's last session, once that session is gone.

    A LIVE session says so itself - general.info reports the connector it reached for, a pty says
    its CLI - and the card reads that first. A CLOSED one said nothing, so the card fell back to the
    CODING ROSTER, which names the brain a role WOULD run on today: a researcher session that ran on
    the owner's Azure OpenAI connector came back an hour later labelled "brain claude", the default
    for a role with no override (the owner, 2026-09-22: "claude did not open but azure openai did").

    Both records exist. A general session saves its pick and model to resume from (store.save_session:
    'connector:7', 'gpt-5.4'), and a pty session's transcript carries the brain it ran. The newer of
    the two is what ran last, and a connector is named as the owner named it, not by its type."""
    saved = store.saved_session(task_id) or {}
    pick, when = str(saved.get('Pick') or ''), str(saved.get('UpdatedAt') or '')
    if pick and (not tr or when >= str(tr['CreatedAt'] or '')):
        if pick.startswith('connector:'):
            c = store.get_connector(int(pick.split(':', 1)[1])) or {}
            name = c.get('Name') or c.get('Type') or 'AI connector'
        else: name = pick.split(':', 1)[-1] or pick
        return {'brain': name, 'model': saved.get('Model') or ''}
    if tr and tr['Brain']: return {'brain': tr['Brain'], 'model': ''}
    return None


def _resumable(task_id: int):
    """(the session this task can be continued from, why it cannot). One judgement for the button
    and the door behind it, so the page never offers what the endpoint will refuse."""
    row = store.resumable_session(task_id)
    if not row: return None, 'no saved session to continue - that agent never named a conversation we can reopen'
    if not store.get_agent(row['Agent'] or ''):
        return None, f'the coder "{row["Agent"]}" is no longer configured; use Run another agent'
    if not (row['Cwd'] and Path(row['Cwd']).is_dir()):
        return None, f'the checkout it worked in no longer exists: {row["Cwd"]}'
    return row, ''

def _workerstate():
    from . import workerstate
    return workerstate


def _assistant_payload(task_id: int, session=None):
    from . import general
    task = store.get_task(task_id)
    if not task: raise HTTPException(404, 'task not found')
    if not general.handles(task):
        raise HTTPException(422, 'assistant view is available for general, research, marketing, and triage tasks')
    session = session or general.session_for(task_id)
    return {'messages': general.history(store, task_id),
            # ONE ENTRY PER CLI, and only the installed ones: this listed a provider per worker
            # profile, so five profiles on Claude read as five brains (the owner, 2026-09-18).
            'providers': general.brain_options(store, keep=general.default_pick(store, task)),
            # what the chat WOULD run on if nobody picks: the picker showed providers[0] instead,
            # which is always a CLI, so a task with no session nominated a coding agent (TQ-0420)
            'defaultPick': general.default_pick(store, task),
            # a walk whose session is still being opened is WORK IN FLIGHT, not an idle conversation
            'starting': task_id in general.OPENING,
            # THE RAISED HAND, where the owner is standing. The agent's question and the answers it
            # offered have been recorded since PW-225 and nothing ever showed them: the workspace got
            # the prose ("tell me when you're signed in") and the two choices it named were never
            # clickable anywhere (2026-09-15). The chip said "needs you"; the question did not.
            'asking': _workerstate().asking_of(store, session) if session else None,
            'session': session.info(tail=3) if session else None}

@app.get('/api/tasks/{task_id}/assistant')
def assistant_state(task_id: int):
    return _assistant_payload(task_id)

@app.post('/api/tasks/{task_id}/assistant/session')
def assistant_session(task_id: int, body: AssistantSessionBody = None):
    from . import general
    body = body or AssistantSessionBody()
    # Opening a FINISHED chat must not resurrect it. GeneralWorkspace posts here on mount, so
    # merely LOOKING at a closed conversation started a live session; it parked with nothing to
    # answer, and BoardView.laneOf - which reads a session that began after ClosedAt as "somebody
    # picked this back up" - filed a done task under Waiting on you, where TQ-0291 sat for
    # forty-five minutes. Reading a closed conversation is reading, not resuming. Sending a
    # message still starts one, because that IS picking it back up.
    t = store.get_task(task_id) or {}
    if t.get('Status') in ('done', 'dropped') and not general.session_for(task_id):
        return _assistant_payload(task_id)
    # The dock and WhatsApp are two views of one assistant. Choosing its provider here is a
    # configuration change, not a tab-local preference that vanishes on restart.
    if general.is_dock(t) and body.pick:
        store.set_setting('assistant_ai', str(body.pick), ACTOR)
        store.set_setting('assistant_model', str(body.model or ''), ACTOR)
    try: session = general.start_session(store, task_id, body.connector_id, body.model, ACTOR, body.pick)
    except (ValueError, RuntimeError) as e: raise HTTPException(422, str(e))
    return _assistant_payload(task_id, session)

@app.post('/api/tasks/{task_id}/assistant/messages')
def assistant_message(task_id: int, body: AssistantMessageBody):
    from . import general
    try:
        _refresh_chat_context(task_id=task_id)
        session = general.start_session(store, task_id, body.connector_id, body.model, ACTOR, body.pick)
        reply = session.send_prompt(body.text, body.attachments, body.connector_id, body.model, pick=body.pick)
    except (ValueError, RuntimeError) as e: raise HTTPException(422, str(e))
    return {'reply': reply, **_assistant_payload(task_id, session)}

@app.post('/api/tasks/{task_id}/assistant/browser')
def assistant_browser(task_id: int):
    """Give THIS conversation a browser, now.

    A browser only ever arrived with the task: the needs:browser mark is set when the task is made
    (the New task dialog's checkbox, or a set-up walk), and nothing in the agent tab could add it
    afterwards. So a chat that turned out to need a page had no way to get one, and the owner asked
    why a browser never showed up there (2026-09-14). Pressing this IS the mark: the task carries it
    from now on, and a session already running gets its Chrome without being restarted.
    """
    from . import browserview, general
    task = store.get_task(task_id)
    if not task: raise HTTPException(404, 'task not found')
    if not general.handles(task): raise HTTPException(422, 'a browser belongs to an assistant conversation')
    if not browserview.installed():
        raise HTTPException(422, 'agent-browser is not installed - Connections -> AI CLI agents lists it')
    store.tag_task(task_id, browserview.WANTS, actor=ACTOR)
    session = general.session_for(task_id)
    if session:
        session.browser_wanted = True                 # the next turn hands the CLI its browser brief
        threading.Thread(target=browserview.start, args=(session.sid,), daemon=True).start()
    return _assistant_payload(task_id, session)

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
    # A WALK DONE IN THE BROWSER REPEATS IN ONE. Without this the promoted job ran through the report
    # loop, whose CLI has no shell and no browser, so tomorrow's run could not reach the page the
    # owner signed into today - and the agent that tried said so and refused to save the report
    # (2026-09-15). Marked here, it is dispatched as a workflow instead: a real session, the same
    # named browser, the owner's restored profile (workflows.run, browserview.start).
    from . import browserview
    if browserview.wanted(task): report_cfg['browser'] = True
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
            fresh = _refresh_chat_context(task_id=task_id)
            if fresh.get('polled'):
                put({'type': 'tool_call', 'name': 'sync_messages',
                     'detail': {'new': fresh.get('added', 0)}})
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
    # One task has one worker mode. Switching the kind from the assistant chat to coding (or
    # back to a human TODO) must close that live assistant session before the coding terminal
    # opens; otherwise both stayed registered on the task and the UI could attach to the wrong
    # one. The same rule lets the kind control move a live coding task into non-coding work.
    next_kind = fields.get('Kind')
    # what triage said, read BEFORE the write that overturns it - verdict_of_task reads the task's
    # current Kind, so capturing it afterwards would record the owner's answer as the verdict
    was_verdict = operations.verdict_of_task(store, task_id) if next_kind and next_kind != t.get('Kind') else None
    if next_kind and next_kind != t.get('Kind'):
        from . import general
        live = hub_term.session_for(task_id)
        if live and live.alive:
            is_chat = getattr(live, 'mode', '') == 'assistant'
            wants_chat = general.handles({'Kind': next_kind})
            if is_chat != wants_chat or next_kind == 'task': hub_term.close(live.sid)
    store.update_task(task_id, fields, ACTOR)
    if t.get('Status') in ('done', 'dropped') and fields.get('Status') in ('open', 'in_progress', 'waiting'):
        # A self-close is remembered in-process to prevent duplicate hooks. Reopening is a new
        # lifecycle, so a later automated run must be allowed to settle again.
        from . import selfclose
        selfclose.forget(task_id)
    # "Mark done - I took care of it" means the agent's job is over too: a live session left
    # running on a finished task is an agent nobody is coming back for. close() files the
    # transcript first, so the record survives the pty as always.
    if fields.get('Status') in ('done', 'dropped'):
        live = hub_term.session_for(task_id)
        if live and live.alive:
            hub_term.close(live.sid)
            store.add_comment(task_id, ACTOR, 'human', 'Task closed - ended the live agent session with it.')
        # the same read receipt concierge.close_task writes: a task the owner closed leaves Unread from
        # whichever button closed it, and a later arrival on it is unread again (the owner, 2026-09-07)
        if t.get('Status') not in ('done', 'dropped'):
            from . import funnel as _funnel
            try: _funnel.settle(store, f'task:{task_id}', 'done', ACTOR, note='the task was closed')
            except Exception as e: logger.debug(f'the closed task did not settle its item: {e}')
    # The kind control is a VERDICT, not a field edit. It used to be the only door to "this is
    # mine, not the agent's" that taught nothing - the tray button beside it reached the identical
    # end state and wrote the lesson - so the owner's correction was given and dropped on the floor
    # (TQ-0501, 2026-09-11). Same judgement, same learning, whichever control they reach for.
    if next_kind and next_kind != t.get('Kind') and next_kind in ('task', 'general', 'coding'):
        # moving it OFF the agent entirely is the button's judgement, so it writes the button's
        # four records. general/coding are still agent work - a weaker signal, the routing fact only.
        if next_kind == 'task': _teach_not_coding(task_id, t, was_verdict, None, True, background)
        else: _teach_routing(task_id, 'kind', next_kind, background=background)
    # ...and WHICH worker: reassigning the profile overturns triage's `profile`, the field that
    # decided an analyst read a timesheet ask in a bank-feeds checkout.
    who = str(fields.get('Assignee') or '')
    if who.startswith('agent:') and who != str(t.get('Assignee') or ''):
        _teach_routing(task_id, 'profile', who.split(':', 1)[1], background=background)
    # "This is not a coding task - it just needs an answer." Changing the kind to reply IS that
    # verdict, so the task enters the review queue the way a question would have at triage:
    # a draft review appears (auto-drafted when that is on), instead of a repo session.
    if fields.get('Kind') == 'reply' and t.get('Kind') != 'reply':
        mid = coder_reply_target(store, task_id)
        if mid and not store.pending_review(task_id):
            rid = store.add_review({'TaskId': task_id, 'MessageId': mid, 'Kind': 'draft', 'Status': 'pending',
                                    'Reason': 'reclassified by you: a question, not work to do - needs a reply'})
            store.add_comment(task_id, ACTOR, 'human', 'Reclassified as a question - it needs an answer, not an agent.')
            if background is not None:
                # always drafted (PW-043) and guarded like ingest's auto-draft: no AI connected means
                # a review waiting in the queue with the failure written on it, never an exception
                from .ingest import _auto_draft
                background.add_task(_auto_draft, store, task_id, rid)
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
    agent = (body.agent if body else None) or hub_agents.default_agent(store)
    if not store.get_agent(agent): raise HTTPException(422, f'unknown agent: {agent}')
    ses = start_session(store, task_id, agent, (body.model if body else None), (body.instruction if body else None),
                        brain=getattr(body, 'brain', None))
    return {'coder': 'session', 'agent': agent, 'model': (body.model if body else None), 'session': ses}

@app.post('/api/tasks/{task_id}/continue')
def continue_task(task_id: int, body: CodeBody):
    """Continue completed coding work without pretending a dead PTY is still alive.

    The transcript is the durable session record. Reopen the same configured agent in the same
    checkout and seed the new terminal with the owner's next instruction plus the saved result.
    If that agent profile was removed, stop and say so instead of silently changing coders.
    """
    task = store.get_task(task_id)
    if not task: raise HTTPException(404, 'task not found')
    instruction = str(body.instruction or '').strip()
    if not instruction: raise HTTPException(422, 'say what code changes you want next')
    _refresh_chat_context(task_id=task_id)
    previous = store.last_transcript(task_id) or {}
    if hub_term.for_task(task_id): raise HTTPException(409, 'this task already has a live coding session')
    from . import agents as hub_agents
    # An explicit picker choice means "restart with this harness". Falling back to the previous
    # transcript preserves the convenient same-agent continue path.
    agent = str(body.agent or previous.get('Agent') or hub_agents.default_agent(store)).strip()
    if not store.get_agent(agent):
        raise HTTPException(422, f'the previous coder "{agent}" is no longer configured; choose a coder from Start session')
    try:
        session = hub_term.start_on_task(store, task_id, agent, body.model, instruction, ACTOR,
                                         brain=getattr(body, 'brain', None),
                                         cwd=previous.get('Cwd') or None)
    except (ValueError, RuntimeError, FileNotFoundError) as e:
        raise HTTPException(422, str(e))
    store.audit('task', task_id, 'continue', ACTOR,
                detail={'agent': agent, 'fromSid': previous.get('Sid'), 'cwd': previous.get('Cwd')})
    return {'continued': True, 'agent': agent, 'fromSession': previous.get('Sid'), 'session': session}


@app.post('/api/tasks/{task_id}/continue-session')
def continue_session(task_id: int, body: CodeBody = None):
    """Reopen the agent's OWN conversation, by the id its CLI gave it.

    Not /continue, which starts a FRESH pane seeded with the handover note - a new agent reading
    about what the last one did. Here the CLI still holds what it read, changed and asked, so the
    prompt is only 'carry on'. The session id is the assistant's trick (session_resume) applied to
    a pty: filed when a hook or a rollout names it, so a restart cannot take it away.
    """
    task = store.get_task(task_id)
    if not task: raise HTTPException(404, 'task not found')
    if task.get('Status') == 'dropped': raise HTTPException(409, 'This task was dismissed.')
    if hub_term.for_task(task_id): raise HTTPException(409, 'this task already has a live session')
    row, why = _resumable(task_id)
    if not row: raise HTTPException(409, why)
    # continuing IS live work again, whatever the card said: a finished task comes back to the work
    # tab rather than having an agent run invisibly behind a done row (the owner, 2026-09-15)
    if task.get('Status') not in ('open', 'waiting', 'in_progress'):
        store.update_task(task_id, {'Status': 'in_progress'}, ACTOR)
    try:
        session = hub_term.start_on_task(store, task_id, row['Agent'], (body.model if body else None),
                                         (body.instruction if body else None), ACTOR,
                                         cwd=row['Cwd'], resume=row['ExtId'])
    except (ValueError, RuntimeError, FileNotFoundError) as e:
        raise HTTPException(422, str(e))
    store.audit('task', task_id, 'continue-session', ACTOR, detail={'agent': row['Agent'], 'fromSid': row['Sid']})
    return {'resumed': row['ExtId'], 'agent': row['Agent'], 'fromSession': row['Sid'], 'session': session}


@app.post('/api/tasks/{task_id}/comments')
def comment(task_id: int, body: TextBody):
    store.add_comment(task_id, ACTOR, 'human', body.body)
    return {'ok': True}


@app.get('/api/assistant/previous-work')
def previous_work():
    from . import continuity
    return {'data': continuity.previous_work(store)}


_RESUME_LOCK = threading.Lock()


def _resume_assistant(task_id):
    from . import continuity, general
    try:
        general.start_session(store, task_id, actor=ACTOR).send_prompt(
            continuity.RESUME_PROMPT, as_owner=False, echo=False)
    except Exception as e:
        _walk_cannot(task_id, f'The session could not resume: {e}. Your saved conversation is still here.')
    finally:
        general.OPENING.discard(task_id)


@app.post('/api/tasks/{task_id}/resume')
def resume_previous_work(task_id: int, background: BackgroundTasks):
    from . import continuity, general
    with _RESUME_LOCK:
        task = store.get_task(task_id)
        if not task: raise HTTPException(404, 'task not found')
        if task.get('Status') == 'dropped': raise HTTPException(409, 'This task was dismissed.')
        review = store.pending_review(task_id)
        if review: return {'action': 'review', 'reviewId': review['ReviewId'], 'taskId': task_id}
        # A finished task is not a closed conversation. The agent's own session is still there to
        # pick up - and picking it up means there is live work again, so the task comes back to the
        # work tab rather than running invisibly behind a done row (the owner, 2026-09-15).
        reopened = task.get('Status') not in ('open', 'waiting', 'in_progress')
        if task_id in general.OPENING or any(s.task_id == task_id and s.alive for s in list(hub_term.SESSIONS.values())):
            return {'action': 'open', 'taskId': task_id}
        if general.handles(task) and not general.provider_options(store):
            raise HTTPException(422, 'Connect an AI provider in Connections to resume this work.')
        if reopened: store.update_task(task_id, {'Status': 'in_progress'}, ACTOR)
        general.OPENING.add(task_id)
    if general.handles(task):
        background.add_task(_resume_assistant, task_id)
    else:
        try: continue_task(task_id, CodeBody(instruction=continuity.RESUME_PROMPT))
        finally: general.OPENING.discard(task_id)
    return {'action': 'open', 'taskId': task_id}

NEEDS_REPO = re.compile(r'could not tell which checkout|no local path|does not exist|choose one', re.I)


@app.post('/api/tasks/{task_id}/dispatch')
def dispatch_task(task_id: int, body: DispatchBody, background: BackgroundTasks):
    if not store.get_task(task_id): raise HTTPException(404, 'task not found')
    try:
        return _dispatch_task_to_its_agent(task_id, body, background)
    except HTTPException as e:
        # a repository the agent cannot open - none chosen, several plausible, a path that is gone - is a
        # DECISION for the owner, shown as a visible choice, never a session in some other checkout (PW-095)
        if e.status_code == 422 and NEEDS_REPO.search(str(e.detail or '')):
            return {'dispatch': 'needs_repo', 'started': False, 'existing': False, 'agent': body.agent or hub_agents.default_agent(store), 'taskId': task_id,
                    'ref': task_ref(task_id), 'reason': str(e.detail or '')}
        raise

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
def set_task_repo(task_id: int, body: RepoBody, background: BackgroundTasks = None):
    """Put this task in the right checkout. The `repo:` tag is the override that always wins over
    the guess, so this is also how you correct one - and because a running session is already in
    the wrong tree, `restart` closes it and opens a fresh one whose prompt names the new repo."""
    t = store.get_task(task_id)
    if not t: raise HTTPException(404, 'task not found')
    # Replacing a choice replaces what that task taught. Otherwise correcting repo A to repo B
    # would leave the same task as positive evidence for both projects forever.
    store.clear_project_evidence(task_id)
    tags = [x for x in re.split(r'[\s,]+', str(t.get('Tags') or '')) if x and not x.startswith('repo:')]
    if body.repo: tags.append(f'repo:{body.repo}')
    store.update_task(task_id, {'Tags': ' '.join(tags)}, ACTOR)
    # a repo Taskuary knows about but has no path for cannot be opened - take the path here
    if body.repo and body.path:
        row = store.get_agent(body.agent)
        if not row: raise HTTPException(422, f'unknown agent: {body.agent}')
        if not Path(body.path).is_dir(): raise HTTPException(422, f'not a directory: {body.path}')
        prof = copy.deepcopy(cfg.get('agents', {}).get(body.agent) or json.loads(row.get('Config') or '{}'))
        prof.setdefault('cwd_map', {})[body.repo] = body.path
        cfg.setdefault('agents', {})[body.agent] = prof
        config.save(cfg)
        cli_connections.sync(cfg, store, body.agent)
    store.add_comment(task_id, ACTOR, 'human',
                      'Marked general - no repository. The session opens in the agent\'s own folder '
                      'and the prompt says there is no codebase to change.' if body.repo == hub_term.NO_REPO
                      else f'Repo set to {body.repo} - the session works there and the prompt says so.'
                      if body.repo else 'Cleared the repo - Taskuary picks it from the ask again.')
    store.audit('task', task_id, 'set_repo', ACTOR, detail={'repo': body.repo, 'path': body.path})
    if body.repo and body.repo != hub_term.NO_REPO:
        from .projects import learn_task_repository
        from . import routingmemory as rmem
        learn_task_repository(store, task_id, body.repo, ACTOR)
        # the project graph already weighted this choice; what it never did was tell the PROFILE.
        # "triage chose ledger and the owner moved the work to portal" is a pattern worth generalising,
        # and it reached LEARNED.md as nothing at all.
        if background is not None and str(t.get('Tags') or '').find(f'repo:{body.repo}') < 0:
            try: background.add_task(learn.learn_from, store, rmem.lesson(store, task_id, 'repository', body.repo))
            except Exception as e: logger.debug(f'repo lesson skipped: {e}')
    from .docsync import sync_projects
    sync_projects(store, ACTOR)
    out = {'ok': True, 'repo': body.repo}
    if body.restart:
        live = hub_term.session_for(task_id)
        if live: hub_term.close(live.sid)
        out['session'] = start_session(store, task_id, body.agent, brain=getattr(body, 'brain', None))
    return out

class NotATaskBody(BaseModel):
    learn: bool = True
    # "archive it": off the pipe and closed, never deleted - the chat's own verb, and what
    # filing does anyway to a task an agent has worked (work_on_task)
    archive: bool = False
    # ...and the half the verdict never carried: WHERE it actually belongs. "Not for the agent"
    # says where the work does not go; only this says where it does, and the routing table had
    # no way to hold a system that is not a git repository at all (TQ-0501: clocking in is ADP).
    belongs_to: str | None = None

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
    was = operations.verdict_of_task(store, task_id)
    store.update_task(task_id, {'Kind': 'task'}, ACTOR)
    store.clear_dispatch(task_id)
    belongs = (body.belongs_to if body else None)
    taught = _teach_not_coding(task_id, t, was, belongs, body is None or body.learn, background)
    store.add_comment(task_id, ACTOR, 'human', 'Not a coding task - kept on your list; the agent is off it.'
                      + (f" It belongs to {belongs.strip()}." if (belongs or '').strip() else ''))
    store.audit('task', task_id, 'not_coding', ACTOR, detail=dict(taught))
    return {'ok': True, 'kind': 'task', **taught}


def _teach_not_coding(task_id: int, t: dict, was: tuple, belongs_to: str = None,
                      learn_it: bool = True, background=None) -> dict:
    """The NOT-FOR-THE-AGENT verdict, written the SAME way whichever control gave it.

    There are two controls for one judgement - the button on the task and the kind selector beside
    it - and they used to teach different things: the button wrote the evidence line, the learned
    profile and the overturned-verdict record, while the selector, which is the one most people
    reach for, wrote the field and nothing else (TQ-0501, the owner: "i updated the type to 'your
    task'... does that trigger memory?" - it did not). Four writes, one of them new:

    - the OVERTURNED VERDICT, so what triage said and what the owner made of it stay joined;
    - an EVIDENCE LINE in the memory table, which ingest.notes_for puts in front of triage on the
      next message about this sender or topic;
    - the general lesson, distilled into LEARNED.md by the hot pass (learn.learn_from);
    - the ROUTING FACT, weighted and task-keyed (routingmemory) - and, when the owner typed one,
      WHERE the work actually lives, which is the half no verdict has ever carried.
    """
    was_kind, was_route = was if was else (None, None)
    operations.record_direct(store, 'task.set_kind', task_id, {'kind': 'task'}, ACTOR, {'kind': 'task'},
                             verdict=was_kind, route_id=was_route)
    msgs = store.list_messages(task_id)
    learned = None
    if msgs and learn_it:
        m = msgs[0]; em = (m.get('FromEmail') or '').lower(); topic = _topic_key(m)
        said = (m.get('Subject') or t.get('Title') or '')[:90]
        learned = store.add_memory({'Scope': 'subject' if topic else 'sender' if em else 'global', 'ScopeKey': topic or em or None,
                                    'Source': 'verdict', 'Active': 1, 'CreatedBy': ACTOR,
                                    'Note': f"{str(m.get('SentAt') or '')[:10]}: \"{said}\""
                                            + (f' from {em}' if em else '') + (f' - the topic "{topic}"' if topic else '')
                                            + ' - NOT A CODING TASK: real work, kept on the owner\'s list, no agent'
                                            + (f' - it belongs to {belongs_to.strip()}' if (belongs_to or '').strip() else '')})
        learn.note_verdicts(store)
    # the general lesson is _teach_routing's to write, once, in words that name what triage had
    # actually answered - this used to write its own vaguer copy alongside it. The memory id rides
    # as the evidence key so LEARNED.md's `ev:` tag points at the line the owner can actually read.
    return {'memoryId': learned,
            **_teach_routing(task_id, 'kind', 'task', belongs_to=belongs_to, background=background,
                             ev=f'mem{learned}' if learned else None)}


def _reclassify(task_id: int, want: str, background=None) -> None:
    """Move an EXISTING task to a kind the owner just chose, down the task page's own road.

    Four controls reclassify a task and each used to do it its own way: the kind selector (the
    PATCH), the button, a timeline card's operation, and the assistant's "put it on my list" /
    "talk this one through". The last three wrote `Kind` straight to the column - so they taught
    neither memory, and left any live session attached to a task that had changed worker mode.
    One road, so a judgement is worth the same wherever it is given.
    """
    t = store.get_task(task_id) or {}
    if not t or t.get('Kind') == want or t.get('Status') in ('done', 'dropped'): return
    update_task(task_id, TaskBody(Kind=want), background)


def _teach_routing(task_id: int, field: str, value: str, belongs_to: str = None,
                   background=None, ev: str = None) -> dict:
    """One correction to a triage verdict, learned wherever it came from.

    Every door that overturns a routing field lands here - the task page's button, the kind
    control, the assistant's "put it on my list" - because the SAME judgement taught different
    things depending on which one you used, and the one most people reach for (the kind control)
    taught nothing at all.

    It writes to BOTH memories, which answer different questions. The routing fact
    (routingmemory) is the precise one: this sender, this field, this value, weighted by how many
    times it has held - what the next verdict is shown. The LEARNED.md line is the general one,
    distilled by the hot pass into a pattern about how the owner works. Only the first existed
    for anything but `kind`, so a reassigned worker or a rerouted repository taught the profile
    nothing whatever.

    A failure to learn never fails the correction: the owner's change to their own task lands
    whatever either memory does.
    """
    from . import routingmemory as rmem
    out = {}
    for f, v in (('system', (belongs_to or '').strip()), (field, value)):
        if not v: continue
        try:
            said = rmem.lesson(store, task_id, f, v, belongs_to if f != 'system' else None, ev)
            n = rmem.learn_correction(store, task_id, f, v, ACTOR, reason=said[:200])
            if n: out[f'learned_{f}'] = n
            # the general lesson, once per correction and only when it taught something new -
            # a re-press of the same button must not spend an AI call restating a known pattern
            if n and background is not None: background.add_task(learn.learn_from, store, said)
        except Exception as e:
            logger.warning(f'routing memory: {f}={v} on task {task_id} not learned - {e}')
    return out

@app.post('/api/tasks/{task_id}/not-a-task')
def not_a_task(task_id: int, body: NotATaskBody = None, background: BackgroundTasks = None):
    """Owner verdict: never needed to be a task. Writes the verdict to memory (_teach_not_a_task
    - a note, never a policy: muting a sender is "Skip this sender", not a side effect of this),
    then deletes the task - its messages stay in the feed as 'filed'.

    learn=false is the lighter verdict: THIS one is just chatter (someone answered "yes"), with
    nothing to conclude - delete the task and teach nothing."""
    if not store.get_task(task_id): raise HTTPException(404, 'task not found')
    msgs, learned = store.list_messages(task_id), None
    was_kind, was_route = operations.verdict_of_task(store, task_id)
    operations.record_direct(store, 'task.not_a_task', task_id, {}, ACTOR, {'deleted': True}, verdict=was_kind, route_id=was_route)
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

def work_on_task(tid: int) -> str:
    """What deleting this task would DESTROY, in words - '' when there is nothing to lose. An agent
    on it, a report it wrote, a commit it made: none of that can be recovered, and one sentence in
    the chat used to be enough to lose all three (the 2026-09-03 break test: "not ours" about the
    Teams outage deleted TQ-0002, its CODER REPORT and its drafted reply)."""
    if not store.get_task(tid): return ''
    had = []
    try:
        # live_sessions is the same truth the pipe reads for "an agent has this one" - for_task alone
        # misses a session the watcher knows about
        live = hub_term.for_task(tid) or next((x for x in hub_term.live_sessions() if x.get('taskId') == tid), None)
        if live: had.append('an agent is working it')
    except Exception: pass
    # A written reply waiting for a yes is work too, and nothing else records it: the drafter leaves no
    # comment, so a reply-only task answered "not ours" was hard-deleted with the draft inside it
    # (2026-09-10 audit). An EMPTY pending review is only a question nobody answered - still deletable.
    rv = store.pending_review(tid)
    if rv and str(rv.get('DraftText') or '').strip(): had.append('it carries a reply waiting to be sent')
    cs = store.list_comments(tid)
    if any(str(c.get('Body') or '').startswith(('CODER REPORT', 'HANDOVER NOTE')) for c in cs): had.append('it carries an agent report')
    # the router's own bookkeeping ('not auto-started', 'start failed', 'queued') is not an agent's work: a task
    # nothing ever ran on stays deletable however loudly the pipeline explained why (PW-073)
    if any(str(c.get('ActorType') or '') == 'agent' and str(c.get('Actor') or '') != 'router' for c in cs) and 'it carries an agent report' not in had:
        had.append('an agent has worked on it')
    return ' and '.join(had)


def _file_task(tid: int, why: str) -> str:
    """The task behind a filed message: DELETED when nothing was ever done on it, ARCHIVED (closed,
    with the reason on it) when an agent touched it. Returns 'deleted' or 'archived'."""
    lost = work_on_task(tid)
    if not lost:
        _drop_task(tid); return 'deleted'
    try:                                       # the work is kept; the agent doing it is not
        live = hub_term.for_task(tid)
        if live: hub_term.close(live['sid'])
    except Exception as e: logger.warning(f'could not stop the agent on archived task {tid}: {e}')
    store.update_task(tid, {'Status': 'done'}, ACTOR)
    store.add_comment(tid, ACTOR, 'human', f'Archived, not deleted - {why}. Kept because {lost}.')
    store.audit('task', tid, 'archived_not_deleted', ACTOR, detail={'why': why, 'kept': lost})
    return 'archived'


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


def _artifact_row(a: dict) -> dict:
    return {'id': a['ArtifactId'], 'name': a.get('Name') or 'session artifact.md',
            'content_type': a.get('ContentType') or 'text/markdown', 'size': a.get('Size') or 0,
            'kind': a.get('Kind') or 'session', 'created_by': a.get('CreatedBy') or '',
            'created_at': a.get('CreatedAt'),
            'url': f"/api/task-artifacts/{a['ArtifactId']}" if a.get('Path') else None}

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

@app.get('/api/messages/{mid}/thread')
def message_thread(mid: int, limit: int = 40):
    """Everything said on this conversation, oldest last - INCLUDING the owner's own replies.

    A chat row that never became a task showed only itself in the panel, so a reply sent from
    Teams or Outlook was invisible here - even though it is ingested (channels.py stores the
    owner's own lines as `context` rows) and the assistant reads it perfectly well when it writes
    the brief. The history on screen disagreed with the history the assistant reasons from, and
    the screen was the one that was wrong.

    `context` rows are deliberately kept OUT of the feed - they are not things that happened TO
    the owner - but they are exactly what makes a thread read as a conversation, so they belong
    here."""
    m = store.get_message(mid)
    if not m: raise HTTPException(404, 'message not found')
    msgs = store.thread_messages(m.get('ConversationId'), m.get('Subject'), limit)
    # ...and what was DECIDED about it. A row with no task has no task detail to read a
    # history out of, and "not ours" is precisely the verdict that leaves it without one.
    return {'messages': msgs or [m], 'conversationId': m.get('ConversationId') or '',
            'routes': store.message_routes(mid), 'reviews': store.reviews_for_message(mid)}

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


@app.get('/api/task-artifacts/{aid}')
def task_artifact(aid: int, download: bool = False):
    """Open or download a session artifact without exposing arbitrary local files."""
    from . import session_artifacts
    artifact = store.get_task_artifact(aid)
    if not artifact: raise HTTPException(404, 'artifact not found')
    path = session_artifacts.confined(artifact.get('Path'))
    if not path: raise HTTPException(404, 'this artifact is no longer on disk')
    # Old artifacts copied the raw PTY stream after the useful result. Keep that durable source
    # file intact, but do not make the in-app reader render terminal repaints and tool chatter.
    text = path.read_text(encoding='utf-8', errors='replace')
    text = text.split('\n## Full session transcript', 1)[0].rstrip() + '\n'
    response = Response(text, media_type='text/markdown; charset=utf-8')
    disposition = 'attachment' if download else 'inline'
    response.headers['Content-Disposition'] = f'{disposition}; filename="{_att_filename(artifact.get("Name"))}"'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    return response

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

class OpenReplyBody(BaseModel):
    draft: bool = True
    instruction: str | None = None
    # "make it shorter": write it AGAIN over the draft that is there. Without this the model
    # claimed the edit and the next approve sent the untouched original (2026-09-03).
    redraft: bool = False

@app.post('/api/messages/{mid}/reply')
def open_reply(mid: int, body: OpenReplyBody = None):
    """Put a reply on the table for ANY message - the coder finished and you want to answer, or
    triage never queued one. Creates the pending review (reusing one if it exists) and, unless
    draft=false, writes the AI draft right now so the box comes back filled. Approving still
    sends; nothing here does."""
    m = store.get_message(mid)
    if not m: raise HTTPException(404, 'message not found')
    try: _refresh_chat_context(task_id=m.get('TaskId'), message_id=mid)
    except RuntimeError as e: raise HTTPException(503, str(e))
    # The requested row may no longer be the end of the conversation after that sync.  Draft and
    # deliver against the newest inbound line, while keeping the same task/review.
    m = (_latest_context_message(m.get('TaskId'), mid) or store.get_message(mid) or m)
    mid = m['MessageId']
    # a FILED message stays filed: answering it is a reply, not a project, and promoting it to a
    # task just to hold the review put a TQ badge on chatter. The review rides task-less.
    tid = m.get('TaskId')
    # ...and a thread its own last reply CLOSED comes back when the owner opens another one. The
    # draft was created on the done task, where the queue's visibility rule hides it, so the card
    # asking for the yes said "already handled" over the message instead of showing the draft, and
    # every click stacked one more invisible review (TQ-0426, 2026-09-07). Answering again is work.
    if tid and (store.get_task(tid) or {}).get('Status') in ('done', 'dropped'):
        store.update_task(tid, {'Status': 'waiting'}, ACTOR)
    rv = store.pending_review(tid) if tid else None
    rid = rv['ReviewId'] if rv else store.add_review({'TaskId': tid, 'MessageId': mid, 'Kind': 'draft',
                                                      'Status': 'pending', 'Reason': 'you opened a reply on this message'})
    draft = (rv or {}).get('DraftText') or ''
    if rv and rv.get('MessageId') != mid:
        draft = ''                    # a correct old draft is still wrong for a newer conversation
    if body is not None and body.redraft: draft = ''          # write it again over what is there
    if not draft and (body is None or body.draft):
        try:
            # the owner's own words on what to say ("tell Ravi it is not owned here") ride into the draft
            note = f"THE OWNER'S INSTRUCTION FOR THIS REPLY - follow it: {body.instruction.strip()}" if body is not None and (body.instruction or '').strip() else None
            draft = (responder.write_draft(store, tid, rid, actor=ACTOR, nudge=note) if tid
                     else responder.draft_for_message(store, m, rid))
        except Exception as e:
            logger.warning(f'reply draft failed for message {mid}: {e}')   # the box opens empty; write it yourself
    if body is not None and body.redraft and draft: store.update_review_draft(rid, draft, (rv or {}).get('RunId'))
    store.audit('review', rid, 'redraft' if (body is not None and body.redraft) else 'open_reply', ACTOR, detail={'message_id': mid})
    return {'reviewId': rid, 'taskId': tid, 'draft': draft}


class NotMineBody(BaseModel):
    note: str | None = None
    scope: str = 'sender'
    topic: str | None = None        # the owner's own wording for a 'subject' verdict's key
class IgnoreSenderBody(BaseModel):
    how: str = 'rule'               # 'rule' = an exclusion rule in Settings | 'memory' = a learned verdict

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
    fate = ''
    if tid and store.get_task(tid):
        store.audit('task', tid, 'not_mine_delete', ACTOR, detail={'message_id': mid, 'memory_id': memid})
        fate = _file_task(tid, f'not ours - {note[:80]}')     # deleted, or archived when an agent worked it
    store.set_message_status(mid, 'ignored')
    store.add_route(mid, None, 'ignore', None, f'not ours - {note[:200]}', [], ACTOR)
    store.audit('memory', memid, 'create', ACTOR, detail={'scope': scope, 'key': key, 'from': em})
    # "not ours" draws a responsibility boundary - the general shape of it belongs in LEARNED.md
    if background is not None:
        background.add_task(learn.learn_from, store,
                            f"mem{memid}: owner said NOT OURS ({scope}): \"{(m.get('Subject') or '')[:80]}\" "
                            f"from {em or '?'} - {note[:200]}")
    return {'ok': True, 'memoryId': memid, 'note': note, 'scope': scope, 'scopeKey': key,
            'taskDeleted': fate == 'deleted', 'taskArchived': fate == 'archived', 'ref': task_ref(tid) if tid else None,
            'alsoCovered': _also_covered(scope, key, tid)}

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
    tid, fate = m.get('TaskId'), ''
    if tid and store.get_task(tid):
        store.audit('task', tid, 'filed_not_work', ACTOR, detail={'message_id': mid})
        # never delete work: a task an agent has been on is CLOSED and kept, report and all
        fate = 'archived' if (body is not None and body.archive) else _file_task(tid, 'filed from the pipe')
        if fate == 'archived' and store.get_task(tid) and store.get_task(tid).get('Status') not in ('done', 'dropped'):
            store.update_task(tid, {'Status': 'done'}, ACTOR)
            store.add_comment(tid, ACTOR, 'human', 'Archived from the pipe - closed, not deleted.')
    learned = _teach_not_a_task(m, background) if (body is None or body.learn) else None
    verdict, route_id = operations.verdict_of_message(store, m)
    store.set_message_status(mid, 'ignored')
    store.add_route(mid, None, 'ignore', None, 'nothing to do - filed by the owner', [], ACTOR)
    operations.record_direct(store, 'message.file', mid, {}, ACTOR, {'taskDeleted': fate == 'deleted', 'taskArchived': fate == 'archived'}, verdict=verdict, route_id=route_id)
    return {'ok': True, 'taskDeleted': fate == 'deleted', 'taskArchived': fate == 'archived',
            'ref': task_ref(tid) if tid else None, 'memoryId': learned}

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

@app.post('/api/messages/{mid}/ignore-sender')
def ignore_sender(mid: int, body: IgnoreSenderBody, background: BackgroundTasks = None):
    """"Ignore this sender" is two different acts, and the owner asked to be asked which
    (2026-09-04: "shoudl I add it to exclusion rule in setting or just a memory").

    rule    an exclusion rule (Settings -> Rules): the sender never reaches triage again, and
            policy.apply_retroactively pulls their existing rows off the timeline too. The bigger
            hammer, and reversible - switching the rule off puts the history back.
    memory  a learned verdict: their mail keeps arriving and stays readable, but the classifier
            reads the verdict on every later message like it. Nothing disappears.

    Neither is the silent default, which is why the card offers both and the chat asks first.
    """
    m = store.get_message(mid)
    if not m: raise HTTPException(404, 'message not found')
    em = (m.get('FromEmail') or '').lower().strip()
    if not em: raise HTTPException(422, 'this message has no sender address to key a rule on')
    if body.how == 'memory':
        return {**not_mine(mid, NotMineBody(scope='sender'), background), 'how': 'memory', 'sender': em}
    if body.how != 'rule': raise HTTPException(422, "how must be 'rule' or 'memory'")
    pid = store.save_policy({'Name': f'Skip {em}', 'Kind': 'sender', 'Pattern': em, 'Action': 'skip',
                             'Reason': f'the owner said to ignore mail from {em}', 'Active': 1}, ACTOR)
    store.audit('policy', pid, 'create', ACTOR, detail={'from': em, 'message_id': mid, 'via': 'ignore-sender'})
    saved = next((p for p in store.list_policies(active_only=False) if p['PolicyId'] == pid), None)
    hidden = policy_engine.apply_retroactively(store, saved or {})
    if hidden: store.audit('policy', pid, 'apply_history', ACTOR, detail={'messages': hidden})
    # ...and the WORK their mail already made. apply_retroactively only hides messages, so the task
    # triage had already cut from one of them stayed open and kept being offered - the owner silenced
    # the sender and the very next thing the pipe showed was that sender again (2026-09-15: "i put
    # this in that ignore sender but then it showed up again?").
    # READ, exactly what pressing Next writes (concierge surfaces an item with read=True) - never
    # closed: silencing who reported a thing is not a verdict on the thing. Nobody's work is thrown
    # away, and a new arrival on the task makes it unread again, as any read receipt does.
    quieted = []
    from . import funnel as _funnel
    for t in store.live_tasks_from_sender(em):
        try:
            _funnel.settle(store, f"task:{t['TaskId']}", 'surfaced', ACTOR, read=True,
                           note=f'the owner silenced {em}')
            quieted.append(t['TaskId'])
        except Exception as e: logger.debug(f"task {t['TaskId']} did not settle under the new rule: {e}")
    if quieted: store.audit('policy', pid, 'quiet_tasks', ACTOR, detail={'tasks': quieted})
    return {'ok': True, 'how': 'rule', 'policyId': pid, 'affected': hidden, 'sender': em,
            'quieted': quieted}

def start_session(store_, tid: int, agent: str = None, model: str = None, instruction: str = None,
                  brain: str = None) -> dict:
    try:
        _refresh_chat_context(task_id=tid)
        # `agent` is the ROLE, `brain` is which CLI runs it - two questions, two arguments
        return hub_term.start_on_task(store_, tid, agent or hub_agents.default_agent(store_), model, instruction,
                                      ACTOR, brain=brain)
    except (ValueError, RuntimeError, FileNotFoundError) as e:
        raise HTTPException(422, str(e))


def _dispatch_task_to_its_agent(tid: int, body: DispatchBody, background: BackgroundTasks) -> dict:
    """Start the explicitly selected kind of agent, or preserve an existing task kind.

    ``general`` is the conversational assistant; ``coding`` is a CLI in a checkout.  The caller
    may deliberately correct triage here: clicking Coding agent or Regular agent is an owner
    verdict, not a hint. A request without a kind remains compatible with task-page continuation
    and uses the task's already-established kind.
    """
    from . import general
    task = store.get_task(tid)
    if not task: raise HTTPException(404, 'task not found')
    # An explicit selection is still a real input even when this task ultimately belongs in the
    # regular workspace. Reject stale/deleted agent names instead of silently accepting a typo.
    if body.agent and not store.get_agent(body.agent):
        raise HTTPException(422, f'unknown agent: {body.agent}')
    task_kind = str(task.get('Kind') or '').lower()
    requested = str(body.kind or '').lower()
    if requested and requested not in ('general', 'coding'):
        raise HTTPException(422, 'kind must be general or coding')

    if requested and requested != task_kind:
        live = hub_term.session_for(tid)
        if live and live.alive:
            who = getattr(live, 'agent', None) or getattr(live, 'label', None) or 'agent'
            raise HTTPException(409, f'{who} is already working on this task; stop that agent before changing agent type')
        was_kind, was_route = operations.verdict_of_task(store, tid)
        store.update_task(tid, {'Kind': requested}, ACTOR)
        operations.record_direct(store, 'dispatch.prepare', tid, {'kind': requested}, ACTOR, {'kind': requested}, verdict=was_kind, route_id=was_route)
        task = store.get_task(tid)
        task_kind = requested

    regular = general.handles(task)

    if regular:
        had_session = general.session_for(tid) is not None
        # THE PROFILE IS THE ASSIGNEE. A general hand-off may now name the worker it goes to, and
        # `agent:<name>` is where general.assigned_role already reads it from to seed PROFILE RULES -
        # so choosing one needs no new column and no migration (the owner, 2026-09-18). A CODING
        # profile named here would seed CODER.md into a chat, so it is refused rather than obeyed.
        if body.agent and body.agent != general.assigned_role(store, task):
            if str((store.get_agent(body.agent) or {}).get('Kind') or '').lower() in ('coding', 'cli'):
                raise HTTPException(422, f'{body.agent} is a coding profile - it cannot run a non-coding task')
            store.update_task(tid, {'Assignee': f'agent:{body.agent}'}, ACTOR)
            task = store.get_task(tid)
        try:
            session = general.start_session(store, tid, model=body.model, pick=body.pick or None, actor=ACTOR)
        except (ValueError, RuntimeError) as e:
            raise HTTPException(422, str(e))
        # The source messages and their files are injected by GeneralSession.send_prompt.  On a
        # new conversation the task summary is the first ask; on an existing conversation only
        # an explicit new instruction is sent, so clicking twice cannot duplicate the task.
        history = general.history(store, tid)
        prompt = str(body.instruction or '').strip()
        if not prompt and not history:
            prompt = str(task.get('Summary') or task.get('Title') or '').strip()
        if prompt:
            background.add_task(session.send_prompt, prompt)
        # the same four words every door speaks (PW-209): a reused conversation is not a new start
        return {'dispatch': 'assistant', 'agent': session.provider, 'model': session.model, 'started': not had_session, 'existing': had_session,
                'taskId': tid, 'ref': task_ref(tid), 'session': session.info(tail=3)}

    agent = body.agent or hub_agents.default_agent(store)
    if not store.get_agent(agent): raise HTTPException(422, f'unknown agent: {agent}')
    # THE BRAIN TRAVELS WITH THE ROLE. This called start_session without it, so a picked CLI got as
    # far as the door and no further: "chose devin from start coding agent screen but it started
    # claude code" (the owner, 2026-09-22). agent = who works it, brain = what runs it.
    ses = start_session(store, tid, agent, body.model, body.instruction, brain=body.brain)
    existing = bool((ses or {}).get('existing'))
    return {'dispatch': 'session', 'agent': agent, 'brain': body.brain, 'model': body.model, 'started': not existing, 'existing': existing,
            'accepted': (ses or {}).get('accepted'),      # the prompt was submitted, not merely typed (PW-209)
            'taskId': tid, 'ref': task_ref(tid), 'session': ses}

@app.post('/api/messages/{mid}/dispatch')
def dispatch_message(mid: int, body: DispatchBody, background: BackgroundTasks):
    """Hand a timeline item to the explicitly selected agent type."""
    m = store.get_message(mid)
    if not m: raise HTTPException(404, 'message not found')
    requested = str(body.kind or '').lower()
    # A named CLI agent is itself an explicit coding choice for old API clients. With neither a
    # kind nor an agent, guessing from triage is exactly the bug this endpoint must prevent.
    if not requested and not body.agent:
        raise HTTPException(422, 'Choose an agent type: general or coding')
    _learn_promotion(m, background)
    verdict, route_id = operations.verdict_of_message(store, m)
    tid = m.get('TaskId') or task_from_message(
        store, mid, ACTOR, requested if requested in ('general', 'coding') else 'coding')
    try:
        out = _dispatch_task_to_its_agent(tid, body, background)
        operations.record_direct(store, 'task.create_from_message', mid, {'kind': requested if requested in ('general', 'coding') else 'coding'}, ACTOR,
                                 {'taskId': tid, 'dispatch': out.get('dispatch')}, verdict=verdict, route_id=route_id)
        return out
    except HTTPException as e:
        reason = str(e.detail or '')
        # This is a decision, not a failed action. The message may only just have become a task,
        # so return its id and let the card ask which repo before resuming the same dispatch.
        if e.status_code == 422 and NEEDS_REPO.search(reason):
            return {'dispatch': 'needs_repo', 'started': False, 'existing': False, 'agent': body.agent or hub_agents.default_agent(store), 'taskId': tid,
                    'ref': task_ref(tid), 'reason': reason}
        raise

def _learn_promotion(m: dict, background):
    """A FILED message the owner promotes by hand is a triage miss in the other direction -
    fyi was the wrong call. The under-reach lessons matter as much as the over-reach ones.

    Promotion used to go only to the AI distillation pass. That made the button claim less than
    it did, while Settings -> Memory showed no evidence that the click had been learned. Save the
    concrete, scoped verdict first; LEARNED.md can then distill its general shape like every other
    owner correction. A positive verdict is evidence, never a hard rule that every similar message
    must become work.
    """
    if m.get('TaskId') or m.get('Status') != 'filed': return None
    em, topic = (m.get('FromEmail') or '').lower(), _topic_key(m)
    if not (em or topic): return None
    memid = store.add_memory({'Scope': 'subject' if topic else 'sender', 'ScopeKey': topic or em,
                              'Source': 'verdict', 'Active': 1, 'CreatedBy': ACTOR,
                              'Note': f"{str(m.get('SentAt') or '')[:10]}: \"{(m.get('Subject') or '')[:90]}\""
                                      + (f' from {em}' if em else '') + (f' - the topic "{topic}"' if topic else '')
                                      + ' - MADE A TASK: triage filed it, but the owner promoted it as real work'})
    learn.note_verdicts(store)
    if background is not None:
        background.add_task(learn.learn_from, store,
                            f"mem{memid}: triage filed \"{(m.get('Subject') or '')[:80]}\" from "
                            f"{m.get('FromEmail') or m.get('SourceName') or '?'} as fyi, but the owner made it a task - "
                            'triage under-reached')
    return memid

# WHICH ROAD IT SHOULD HAVE TAKEN. The Triage tab shows the five roads and says "correcting this
# teaches it" - and there was nothing to click. A correction here is worth more than any other
# signal the funnel gets: it is the owner looking at one real message and saying what should have
# happened to it. So it does BOTH halves - it puts the message on the road it should have taken,
# and it writes the verdict down where the next classification will read it.
ROADS = {'fyi': 'nothing to do', 'reply': 'a sentence settles it', 'coding': 'an agent on a keyboard',
         'general': 'talk it through with the assistant', 'task': 'yours - nothing works it'}
ROAD_VERDICT = {'fyi': 'FILE IT: not work', 'reply': 'REPLY ONLY: answering it IS the work',
                'coding': 'CODING TASK: an agent should work it', 'general': 'A CONVERSATION, not a project',
                'task': "THE OWNER'S OWN TASK: real work, but not an agent's"}


class ReclassifyBody(BaseModel):
    road: str                       # fyi | reply | coding | general | task
    agent: str | None = None        # the ROLE that works it
    brain: str | None = None        # WHICH CLI runs it - blank means the brain settings name


def _teach_reclassify(m: dict, was: str, road: str, background) -> int:
    """The correction as EVIDENCE, not as a rule. Keyed to the topic where there is one and to the
    sender otherwise - never to the sender alone on a channel with no address, which is how one
    verdict about one message becomes a policy about a person (see file_message)."""
    em, topic = (m.get('FromEmail') or '').lower(), _topic_key(m)
    if not (em or topic): return 0
    memid = store.add_memory({'Scope': 'subject' if topic else 'sender', 'ScopeKey': topic or em,
                              'Source': 'verdict', 'Active': 1, 'CreatedBy': ACTOR,
                              'Note': f"{str(m.get('SentAt') or '')[:10]}: \"{(m.get('Subject') or '')[:90]}\""
                                      + (f' from {em}' if em else '') + (f' - the topic \"{topic}\"' if topic else '')
                                      + f' - {ROAD_VERDICT[road]}'
                                      + (f' (triage had called it {was})' if was else '')})
    learn.note_verdicts(store)
    ev = (f'mem{memid}: triage called \"{(m.get("Subject") or "")[:80]}\" from '
          f'{m.get("FromEmail") or m.get("SourceName") or "?"} {was or "unclassified"}, and the owner '
          f'reclassified it as {road} - {ROADS[road]}')
    if background is not None: background.add_task(learn.learn_from, store, ev)
    else: learn.learn_from(store, ev)
    return memid


def _road_now(m: dict) -> str:
    """What the funnel decided, read the way the panel reads it (FeedView roadOf)."""
    routes = store.message_routes(m['MessageId']) or []
    reason = str((routes[-1] if routes else {}).get('Reason') or '')
    if 'triage: fyi' in reason: return 'fyi'
    if 'triage: reply_only' in reason: return 'reply'
    kind = str((store.get_task(m['TaskId']) or {}).get('Kind') or '') if m.get('TaskId') else ''
    if kind in ('coding', 'task'): return kind
    return 'general' if m.get('TaskId') else ''


@app.post('/api/messages/{mid}/reclassify')
def reclassify_message(mid: int, body: ReclassifyBody, background: BackgroundTasks = None):
    """Put this message on the road it should have taken, and remember that triage was wrong.

    Not a relabel: each road is the same action its own button performs, so reclassifying to
    coding really starts the agent and reclassifying to fyi really drops the task. Saying it
    without doing it would leave the funnel and the record disagreeing, which is the failure this
    whole panel exists to prevent."""
    m = store.get_message(mid)
    if not m: raise HTTPException(404, 'message not found')
    road = str(body.road or '').lower()
    if road not in ROADS: raise HTTPException(422, f'unknown road: {body.road!r} - one of {", ".join(ROADS)}')
    was = _road_now(m)
    if was == road: return {'ok': True, 'road': road, 'changed': False, 'was': was}
    memid = _teach_reclassify(m, was, road, background)
    store.audit('message', mid, 'reclassified', ACTOR, detail={'from': was or None, 'to': road, 'memory': memid or None})
    # the panel reads the road off the newest route row, so the correction has to be written where
    # the verdict lives - otherwise the pill still shows what triage said
    store.add_route(mid, m.get('TaskId'),
                    {'fyi': 'file', 'reply': 'reply', 'coding': 'create', 'general': 'create', 'task': 'create'}[road],
                    None, f'triage: {"reply_only" if road == "reply" else road} - you reclassified this'
                          + (f' (triage called it {was})' if was else '') + ' - the verdict is in memory for next time',
                    [], ACTOR)
    out = {'ok': True, 'road': road, 'changed': True, 'was': was, 'memory': memid or None}
    if road == 'fyi': file_message(mid, None, background)
    elif road == 'reply': out['reply'] = open_reply(mid, None)
    elif road == 'coding': out['agent'] = dispatch_message(mid, DispatchBody(agent=body.agent, kind='coding'), background)
    elif road == 'general': out['chat'] = chat_message(mid, background)
    else: out['task'] = mine_message(mid, MineBody(kind='task'), background)
    return out


# ── the assistant on the Timeline (assistant.py): its post and its buttons ───────────────────
@app.get('/api/assistant/ideas')
def assistant_ideas(status: str = None, mid: int = None):
    """What the assistant has said, with what became of each line - by state, or the lines of one post."""
    def row(i):
        out = assistant._public(i) | {'firstSeen': i.get('FirstSeen'), 'lastSaid': i.get('LastSaid'), 'messageId': i.get('MessageId')}
        # Preserve the historical words, but do not keep presenting a disproved "nobody replied"
        # suggestion as open. The successful Review receipt supplies the accurate ending even if
        # the external channel has not ingested our outbound copy as a message.
        if assistant.contradicts_sent_reply(store, out):
            reply = assistant.sent_reply_for(store, out)
            out['answered'] = {'at': reply.get('DecidedAt') or reply.get('CreatedAt'),
                               'text': reply.get('FinalText') or reply.get('DraftText') or ''}
        return out
    return {'data': [row(i) for i in store.list_ideas(status or None, mid)]}

class IdeaBody(BaseModel): days: int = 1

@app.post('/api/assistant/ideas/{iid}/{verb}')
def assistant_act(iid: int, verb: str, body: IdeaBody = None, background: BackgroundTasks = None):
    """One button on one line: followup (the chase, drafted onto the task), task (the agent starts),
    discuss (the full Assistant workspace), dismiss, snooze, or done."""
    try:
        if verb == 'discuss':
            out = assistant.discussion_task(store, iid, ACTOR)
            if out.get('created') and background is not None:
                background.add_task(_assistant_opens, out['taskId'])
            return out
        return assistant.act(store, iid, verb, ACTOR, days=(body.days if body else 1),
                             learn_async=background.add_task if background is not None else None)
        return assistant.act(store, iid, verb, ACTOR, days=(body.days if body else 1),
                             learn_async=background.add_task if background is not None else None)
    except ValueError as e: raise HTTPException(422, str(e))

# What the assistant is told when the owner opens one of its notes for discussion. It is an
# instruction, never recorded as the owner's words (general.send_prompt as_owner=False).
#
# The chat used to open with the assistant's note copied into it and then sit there: the owner had
# just READ that sentence on the Timeline, so the conversation began by repeating them to
# themselves and waiting. "Discuss" is a request for the assistant's next move, so it makes one.
OPENING = ("The owner has just opened this conversation from your note on the Timeline. They have "
           "already read that note - do not repeat it back to them. Open the discussion instead: "
           "say what you would actually DO about it, concretely, in one short paragraph, and then "
           "ask the single thing you need from them to go ahead. If you need nothing, say what you "
           "propose to do and stop. No preamble, no restating the situation.")


def _assistant_opens(task_id: int):
    """The assistant's first turn in a discussion it was asked to have. Runs after the response, so
    the workspace is already on screen when it starts writing. Never raises: an opening line that
    could not be written costs a sentence, and the owner can simply type - which is exactly where
    this conversation stood before."""
    from . import general
    if general.session_for(task_id): return          # already in conversation - not ours to interrupt
    if not general.provider_options(store):
        # no brain configured. Starting a session anyway left one PARKED on the terminal list,
        # waiting forever on an answer nothing was ever going to write - a live-looking agent on
        # the Board doing nothing, from a click that should have done nothing.
        logger.info(f'no AI connector, so the assistant cannot open {task_ref(task_id)}')
        return
    try:
        general.start_session(store, task_id, actor=ACTOR).send_prompt(OPENING, as_owner=False, echo=False)
    except Exception as e:
        general.drop_session(task_id)                # and never leave half a session behind
        logger.info(f'the assistant could not open {task_ref(task_id)}: {str(e)[:200]}')


@app.post('/api/assistant/talk/{iid}')
def assistant_talk(iid: int, body: TextBody):
    """Talk back to one suggestion: corrections and questions get an answer, not a verdict button."""
    try: return assistant.talk(store, iid, body.body, ACTOR, _llm())
    except ValueError as e: raise HTTPException(422, str(e))

# what GeneralWorkspace reads to open a chat with its question already asked (newTask.js)
ASK_TAG = 'ask:assistant'

class MineBody(BaseModel):
    # a plain task: on the owner's list, nothing working it. NOT `general` - that kind opens the
    # assistant's chat (general.GENERAL_KINDS), which is not what "this one is mine" means.
    kind: str = 'task'
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
    verdict, route_id = operations.verdict_of_message(store, m)
    want = (body.kind if body else None) or 'task'
    # A message that ALREADY has a task short-circuits task_from_message, so "this one is mine"
    # on anything triage had already opened changed nothing and taught nothing - it claimed the
    # task and left the kind exactly as the verdict it was overturning (the audit, 2026-09-11).
    tid = m.get('TaskId') or task_from_message(store, mid, ACTOR, want, ACTOR)
    _reclassify(tid, want, background)
    from . import selfclose
    selfclose.claim(store, tid, ACTOR)
    # "mine" takes it off the AGENT's hands, so a worker on the task is precisely what it overrides
    # - the guard used to skip whenever ANY assignee existed, which meant every task triage had
    # routed (they all carry `agent:<role>`) silently ignored the owner claiming it. Only a person
    # already owning it is left alone.
    _who = str((store.get_task(tid) or {}).get('Assignee') or '')
    if not _who or _who.startswith('agent:'): store.update_task(tid, {'Assignee': ACTOR}, ACTOR)
    operations.record_direct(store, 'task.create_from_message', mid, {'kind': (body.kind if body else None) or 'task'}, ACTOR, {'taskId': tid}, verdict=verdict, route_id=route_id)
    if body and (body.title or '').strip(): store.update_task(tid, {'Title': body.title.strip()[:200]}, ACTOR)
    store.audit('task', tid, 'mine', ACTOR, detail={'message_id': mid, 'subject': m.get('Subject')})
    return {'taskId': tid, 'ref': task_ref(tid)}

@app.post('/api/messages/{mid}/chat')
def chat_message(mid: int, background: BackgroundTasks = None):
    """"Talk this one through": the message becomes a `general` task and the assistant's chat
    opens on it with the question already asked.

    The THIRD door, beside /mine (a plain task, yours, nothing works it) and /dispatch (a coding
    session). Triage could already rule a message `general` - and `general` means the assistant's
    chat - but the Timeline had no way to act on that verdict: the only dispatch control on a row
    opened a CLI. A road the classifier can take and the screen cannot is a road that does not
    exist."""
    m = store.get_message(mid)
    if not m: raise HTTPException(404, 'message not found')
    _learn_promotion(m, background)
    verdict, route_id = operations.verdict_of_message(store, m)
    tid = m.get('TaskId') or task_from_message(store, mid, ACTOR, 'general', ACTOR)
    operations.record_direct(store, 'task.create_from_message', mid, {'kind': 'general'}, ACTOR, {'taskId': tid}, verdict=verdict, route_id=route_id)
    from . import selfclose
    selfclose.claim(store, tid, ACTOR)
    _reclassify(tid, 'general', background)
    t = store.get_task(tid) or {}
    # the ask tag is what GeneralWorkspace reads to open with the question instead of an empty
    # thread (website/src/newTask.js). It strips the tag as it asks, so a reload never re-asks.
    tags = [x.strip() for x in str(t.get('Tags') or '').split(',') if x.strip()]
    if ASK_TAG not in tags: store.update_task(tid, {'Tags': ','.join(tags + [ASK_TAG])}, ACTOR)
    store.audit('task', tid, 'chat', ACTOR, detail={'message_id': mid, 'subject': m.get('Subject')})
    return {'taskId': tid, 'ref': task_ref(tid), 'chat': True}

class SplitBody(BaseModel): kind: str | None = None

@app.post('/api/messages/{mid}/split')
def split_msg(mid: int, body: SplitBody = None):
    """Give this message its own task. Two unrelated asks in one chat thread are one
    conversation but two jobs, and an agent sent at the task only ever gets the first."""
    if not store.get_message(mid): raise HTTPException(404, 'message not found')
    tid = split_message(store, mid, ACTOR, (body.kind if body else None))
    from . import selfclose
    selfclose.claim(store, tid, ACTOR)
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
    """Live handoffs by default; durable note history when ``all`` is requested."""
    rows = (blackboard.history(store, cwd or None, limit) if all
            else blackboard.live_wall(store, cwd, limit))
    return {'data': rows,
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
def people(limit: int = 300):
    """The address book behind every place a person is picked - looping somebody in on a reply,
    handing a task over. 60 was enough for a recency list you scroll; a box you SEARCH wants the
    whole book, so the pickers filter a wider set client-side (ui.ContactPicker)."""
    return {'data': store.people(max(1, min(int(limit), 1000)))}

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
        subject = f"{task_ref(task_id)} {t.get('Title') or ''}".strip()
        chat = [m for m in store.list_messages(task_id) if m['Channel'] == 'teams'] if body.channel == 'teams' else []
        if chat:
            # back into the conversation this task CAME from: no address to give, because the
            # thread is the recipient. (The old code demanded one anyway and then ignored it.)
            sent = outbound.send_teams(store, (chat[-1].get('ConversationId') or '')[6:], text)
        elif not body.to:
            raise HTTPException(422, 'who is it going to?')
        elif body.channel == 'email':
            sent = outbound.send_email(store, [body.to], subject, text)
        else:
            # ...and everywhere else this install can send. Handing work to a person was email or
            # the task's own Teams chat and nothing else, while the app has been able to send on
            # WhatsApp, Slack and Telegram for months - so "hand this to a colleague" meant opening
            # WhatsApp yourself, which is the app this one exists to keep you out of. send_out is
            # the same road a report's delivery takes: same senders, same credentials, and a
            # channel switched off for replies is off for this too.
            if not outbound.can_reply(store, body.channel):
                raise HTTPException(422, f'{body.channel} cannot send from here - turn its replies '
                                         'on in Connections, or pick another channel')
            sent = outbound.send_out(store, body.channel, body.to, subject, text)
    except HTTPException: raise
    except Exception as e: raise HTTPException(422, str(e)[:400])
    store.add_comment(task_id, ACTOR, 'human', f'Handed off to {body.to} by {body.channel}:\n{text}')
    # Handing work to a person ENDS it here. The forward went out and somebody else owns the
    # thing now, so leaving the card open on 'needs you' is the funnel asking for a second
    # decision about work the owner just gave away. Closing it also retires the task's pending
    # reviews, so the review queue stops asking about a draft that has already been forwarded.
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
            # The floating guide reuses a general session, but it is app chrome rather than an
            # agent assigned to work. Do not put a duplicate of it on the Board or ring the
            # hand-raise bell while its answer is visible in the dock itself.
            if (store.get_task(t['taskId']) or {}).get('SourceRef') == 'assistant:dock': continue
            # `asking` = the last lines look like a question for the owner (waitroom.looks_like_question):
            # the hand-raise notification says "asked you something" instead of "stopped"
            out.append({'RunId': None, 'TaskId': t['taskId'], 'AgentName': t['agent'] or t['label'],
                        'kind': 'session', 'StartedAt': t['started'], 'idle': t['idle'],
                        'waiting': (w := t['waiting'] if t.get('waiting') is not None else t['idle'] >= hub_term.IDLE_WAITING), 'phase': t.get('phase'),
                        'asking': (ask := bool(w) and waitroom.looks_like_question(t.get('tail') or [])),
                        # ...and the ONE sentence for the state (lanes.json via workerstate.says), so the card, the
                        # Wall and the hand-raise ping read it instead of composing their own from `asking`
                        'request': t.get('request'), 'state': (sub := _workerstate().sub_state(bool(w), ask, t.get('request'))),
                        'line': _workerstate().says(sub, t['agent'] or t['label'], (t.get('request') or {}).get('text')) if sub else None,
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
    from .verdicts import context_moved
    rows = store.list_reviews(status)
    memo = {}
    for r in rows:
        try: special = json.loads(r.get('Deliver') or '{}').get('kind') == 'zoho_invoice'
        except (TypeError, ValueError): special = False
        ok, why = _send_state(memo, r.get('Channel'), bool(r.get('MessageId')))
        r['CanSend'] = special or ok
        r['SendBlock'] = '' if r['CanSend'] else why
        moved, latest = context_moved(store, r)          # material change only (PW-240), never a polling timestamp
        r['Stale'] = bool(moved)
        if r['Stale'] and latest:
            r['LatestMessageId'] = latest.get('MessageId')
            r['LatestPreview'] = str(latest.get('BodyText') or '')[:1500]
            r['LatestSentAt'] = latest.get('SentAt')
    return {'data': rows}

@app.post('/api/reviews/{rid}/attachment')
async def review_attach(rid: int, request: Request, name: str = ''):
    """Put a file on a pending reply. The bytes are the raw body (no multipart dependency, like the
    waiting room's images); `name` is what the recipient will see it called."""
    from . import verdicts
    data = await request.body()
    try: return verdicts.attach(store, rid, name or 'attachment', data, ACTOR)
    except ValueError as e: raise HTTPException(422, str(e))

@app.delete('/api/reviews/{rid}/attachment')
def review_detach(rid: int, name: str):
    from . import verdicts
    try: return verdicts.detach(store, rid, name, ACTOR)
    except ValueError as e: raise HTTPException(422, str(e))

@app.post('/api/reviews/{rid}/decide')
def decide(rid: int, body: DecideBody, background: BackgroundTasks = None):
    """The verdict itself lives in verdicts.decide - ONE door, shared with the phone road
    (a 'approve' typed in the notify chat lands the same way this button does)."""
    rv = store.get_review(rid)
    if not rv: raise HTTPException(404, 'review not found')
    from .verdicts import VERB2STATUS, context_moved, decide as land
    if body.verb not in VERB2STATUS: raise HTTPException(422, 'bad verb')
    if body.verb == 'close_unsent' and rv.get('Kind') == 'action': raise HTTPException(422, 'a proposal is rejected, not closed without sending')
    if body.verb in ('approve', 'edit') and rv.get('Kind') != 'action':
        try: _refresh_chat_context(task_id=rv.get('TaskId'), message_id=rv.get('MessageId'))
        except RuntimeError as e: raise HTTPException(503, str(e))
        rv = store.get_review(rid) or rv
        moved, latest = context_moved(store, rv)
        if moved:
            # The click does not send (PW-239): the context materially changed - a new inbound line, a triage
            # update - so the owner is interrupted with what arrived. Their own edit is kept for comparison, the
            # draft is refreshed from the current context, and the refreshed draft needs its own yes.
            yours = str(body.final_text or '').strip()
            if yours and yours != str(rv.get('DraftText') or '').strip() and rv.get('TaskId'):
                store.add_comment(rv['TaskId'], ACTOR, 'human', f'Your edited reply, kept for comparison - the thread moved before it was sent:\n{yours[:4000]}')
            draft = None
            try:
                draft = (responder.write_draft(store, rv['TaskId'], rid, actor=ACTOR)
                         if rv.get('TaskId') else responder.draft_for_message(store, latest, rid))
            except Exception as e:
                logger.warning(f'could not refresh stale review {rid}: {e}')
            triage = ''
            if rv.get('TaskId'):
                notes = [c for c in store.list_comments(rv['TaskId']) if str(c.get('Actor') or '').lower() == 'triage']
                triage = str(notes[-1].get('Body') or '')[:600] if notes else ''
            return {'ok': False, 'status': 'pending', 'sent': None, 'stale': True,
                    'draft': draft,
                    'interrupt': {'title': 'A new message arrived. Review it before sending.',
                                  'latest': ({'MessageId': latest.get('MessageId'), 'FromName': latest.get('FromName'), 'FromEmail': latest.get('FromEmail'),
                                              'SentAt': latest.get('SentAt'), 'preview': str(latest.get('BodyText') or '')[:1500]} if latest else None),
                                  'triage': triage, 'yours': yours or None, 'refreshed': draft},
                    'send_error': ('New messages arrived after this draft. '
                                   + ('I refreshed it with the latest context; review it and approve again.' if draft
                                      else 'Nothing was sent. Redraft it with the latest context before approving.'))}
    return land(store, rv, body.verb, body.final_text, body.note, ACTOR,
                learn_async=(background.add_task if background is not None else None), cc=body.cc)

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
    wit = getattr(sess, 'witness', None)             # a demo replay has none
    work = wit.snapshot(sess.files(), sess.cwd, (sess.tail(1) or [''])[-1]) if wit else None
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

@app.post('/api/hooks/{cli}')
async def cli_hook(cli: str, request: Request):
    """A CLI's hook fired in a checkout a session of ours works in (hooks.py wires it): the event's
    JSON comes in on the body, the path says which CLI is speaking (claude or codex - same event
    schema, bound to a session of that CLI). Always 200 and quiet - a hook must never trouble the agent."""
    from . import hooks
    if cli not in hooks.HOOKED: return {'bound': False}
    # Anything unreadable is a non-event, including a hook that HUNG UP: hooks.py posts with
    # `curl -s -m 3` so it can never hold the agent, and a server stalled for longer than that
    # outlives the curl - request.body() then raises ClientDisconnect, which is no ValueError and
    # used to escape as a 500 per stall. The agent moved on three seconds ago either way.
    try: payload = json.loads((await request.body()) or b'{}')
    except Exception as e:
        logger.debug(f'claude hook body unreadable: {e}'); return {'bound': False}
    try: return hooks.receive(payload if isinstance(payload, dict) else {}, cli=cli)
    except Exception as e:
        logger.debug(f'{cli} hook ignored: {e}'); return {'bound': False}

# ── the handbook (handbook.py): what the agents worked out, by topic, open to comment ──────
class HubPostBody(BaseModel):
    title: str; body: str = ''; topic: str = ''; kind: str = 'howto'; author: str | None = None
    why_earned: str | None = None
class HubCommentBody(BaseModel): body: str; author: str | None = None

def _hub_actor(request: Request, claimed: str | None = None) -> str:
    """The browser is the owner; an agent token may name its agent without spoofing the owner."""
    from . import guard
    if guard.scope_of(cfg['server'], request.headers) != guard.AGENT: return ACTOR
    raw = request.headers.get('X-Taskuary-Agent') or claimed or 'agent'
    return re.sub(r'[^a-zA-Z0-9_.-]+', '-', str(raw)).strip('-')[:60] or 'agent'

def _require_hub_write(request: Request):
    from . import guard, scopes
    if guard.scope_of(cfg['server'], request.headers) != guard.AGENT: return
    conn = store.get_connector_by_type('handbook')
    if not conn: return
    try: scopes.require(conn, 'hub_write')
    except PermissionError as e:
        store.audit('tool', conn['ConnectorId'], 'run_refused', _hub_actor(request),
                    detail={'type': 'hub_write', 'scope': scopes.scope_of(conn)})
        raise HTTPException(403, str(e))

@app.get('/api/hub')
@app.get('/api/handbook')
def hub_list(topic: str = None, q: str = None, kind: str = None, sort: str = 'new', limit: int = 60, status: str = 'live'):
    """The Hub tab. Topics down the side, high-signal posts in the middle,
    written by whichever agent worked it out, and correctable by whoever knows better.
    status=removed lists what the vote or the owner took off - readable, restorable."""
    posts = store.lore_posts(topic or None, q or None, min(limit, 200), sort,
                             'live' if status == 'live' else 'removed', kind or None)
    # the owner's own vote rides on each row so the arrow can show which way they leaned
    for p in posts: p['MyVote'] = next((v['Delta'] for v in store.lore_votes(p['LoreId']) if v['Actor'] == ACTOR), 0)
    return {'topics': store.lore_topics(), 'data': posts, 'count': store.lore_count()}

@app.get('/api/hub/{lid}')
@app.get('/api/handbook/{lid}')
def hub_one(lid: int):
    p = store.lore_get(lid)
    if not p: raise HTTPException(404, 'no such entry')
    return {**p, 'comments': store.lore_comments(lid), 'votes': store.lore_votes(lid)}

@app.post('/api/hub')
@app.post('/api/handbook')
def hub_post(body: HubPostBody, request: Request):
    """File an entry. Gated the same way the hub_write tool is, because it is the same act
    through a different door - and this door was the way round the ladder.

    An entry is not a note: the Hub gives it to relevant future agents as company knowledge, so it is
    a claim handed to every future session as company fact. scopes.py classifies that as a WRITE
    for exactly that reason. Only AGENTS are measured against it - the owner writing on the Hub
    tab is the person the ladder exists to protect, not a caller to check."""
    from . import guard, handbook as hub
    if not hub.enabled(store):
        raise HTTPException(403, 'the Hub is off - turn its card on under Connections')
    _require_hub_write(request)
    if guard.scope_of(cfg['server'], request.headers) == guard.AGENT and len((body.why_earned or '').strip()) < 20:
        raise HTTPException(422, 'agent Hub posts need why_earned: the concrete investigation or reasoning that earned the post')
    try: return hub.post(store, body.title, body.body, body.topic, body.kind,
                         _hub_actor(request, body.author), why_earned=body.why_earned or '')
    except ValueError as e: raise HTTPException(422, str(e))

@app.post('/api/hub/{lid}/restore')
@app.post('/api/handbook/{lid}/restore')
def hub_restore(lid: int, request: Request):
    """Back on the Hub - a removed entry that turned out to be right after all."""
    if not store.lore_get(lid): raise HTTPException(404, 'no such entry')
    _require_hub_write(request)
    actor = _hub_actor(request)
    store.lore_restore(lid); store.audit('lore', lid, 'restore', actor)
    return dict(store.lore_get(lid))

@app.post('/api/hub/{lid}/comment')
@app.post('/api/handbook/{lid}/comment')
def hub_comment(lid: int, body: HubCommentBody, request: Request):
    """A comment is how a post gets corrected without being erased. An agent that finds an entry
    wrong says so here, and the next reader sees both."""
    if not store.lore_get(lid): raise HTTPException(404, 'no such entry')
    _require_hub_write(request)
    text = ' '.join((body.body or '').split())[:4000]
    if not text: raise HTTPException(422, 'say something')
    cid = store.lore_comment(lid, text, _hub_actor(request, body.author))
    return {'commentId': cid, 'comments': store.lore_comments(lid)}

@app.post('/api/hub/{lid}/vote')
@app.post('/api/handbook/{lid}/vote')
def hub_vote(lid: int, request: Request, up: bool = True, by: str = None):
    """Up or down, one vote per voter - forum rules. The score ranks what the Hub gives
    an agent, and an entry voted below zero is removed from the Hub (restorable). `by` names an
    agent voting through the API; the owner's own votes are ACTOR."""
    from . import handbook as hub
    _require_hub_write(request)
    try: return hub.vote(store, lid, 1 if up else -1, _hub_actor(request, by))
    except ValueError as e: raise HTTPException(404, str(e))

@app.post('/api/hub/{lid}/retire')
@app.post('/api/handbook/{lid}/retire')
def hub_retire(lid: int, request: Request):
    """No longer true. Retired, not deleted: a Hub that silently loses entries is one you
    cannot tell the difference between right and empty in."""
    if not store.lore_get(lid): raise HTTPException(404, 'no such entry')
    _require_hub_write(request)
    actor = _hub_actor(request)
    store.lore_retire(lid, actor)
    store.audit('lore', lid, 'retire', actor)
    return {'retired': True}

class OutboxBody(BaseModel):
    channel: str; to: str | list[str]; about: str; mode: str = 'draft'
    cc: list[str] = []
    subject: str | None = None; repo: str | None = None

@app.post('/api/outbox')
def outbox(body: OutboxBody):
    """＋ New → Send something. Start a message instead of answering one.

    Two modes, one ending. 'draft' has the AI write it now, in the owner's voice, and parks it in
    Review. 'task' sends an agent to find out first; when it finishes, the message is written
    from what it actually found and lands in the same place. Neither one sends: the approved
    review does, through the one door every outgoing message already goes through."""
    from . import outbox as ob
    try: return ob.compose(store, body.channel, body.to, body.about, body.mode, body.subject,
                           body.repo, ACTOR, cc=body.cc)
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
    from . import general, ingest as _ing
    if general.handles(store.get_task(task_id)):
        _ing._spawn(_ing._auto_general, store, task_id)     # the assistant's session, not a CLI (PW-069)
        return {'released': True, 'assistant': True}
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

class ClarifyBody(BaseModel):
    body: str
    message_id: int | None = None

@app.post('/api/tasks/{tid}/clarify')
def clarify_with_sender(tid: int, body: ClarifyBody):
    """Prepare, but never send, the question an agent needs answered.

    This is deliberately its own review kind instead of reusing open_reply(): a task can have
    an action proposal or a final-answer draft already parked on the task, and a clarification
    must not overwrite either. Approval sends the question through the normal human gate while
    stopping the blocked terminal and leaving the coding task waiting for the answer.
    """
    t = store.get_task(tid)
    if not t: raise HTTPException(404, 'task not found')
    text = (body.body or '').strip()
    if not text: raise HTTPException(422, 'write the question to ask')
    messages = store.list_messages(tid)
    if body.message_id:
        m = store.get_message(body.message_id)
        if not m or m.get('TaskId') != tid: raise HTTPException(404, 'that message is not on this task')
    else:
        m = next((x for x in reversed(messages)
                  if x.get('Status') != 'context' and x.get('Direction') != 'out'), None)
    if not m: raise HTTPException(422, 'this task has no incoming message to answer')
    rv = store.pending_review(tid, 'clarification')
    if rv:
        rid = rv['ReviewId']
        store.save_review_draft(rid, text)
    else:
        rid = store.add_review({'TaskId': tid, 'MessageId': m['MessageId'], 'Kind': 'clarification',
                                'Status': 'pending', 'DraftText': text,
                                'Reason': 'the agent needs missing information from the sender'})
    store.add_comment(tid, ACTOR, 'human', 'Clarification drafted for the sender; waiting for your approval on the task.')
    store.audit('review', rid, 'clarification_drafted', ACTOR, detail={'message_id': m['MessageId']})
    return {'reviewId': rid, 'taskId': tid, 'draft': text}

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

def prep_key(start, subject) -> str:
    """What ties a prep row to the invite it is about. The front end builds the same string from
    the event it is drawing (FeedView.evKey), so the two must not drift - hence one function and
    one comment saying so."""
    return f"calendar:{start or ''}:{(subject or 'the meeting').strip()[:120]}"

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
    from . import calendar as cal, ownwork
    subject = (body.subject or 'the meeting').strip()[:120]
    brief = cal.prep_brief(body.dict())
    ask = (body.instruction or '').strip() or 'Get me ready for this meeting.'
    tid = store.create_task({'Title': f'Prep: {subject}'[:200], 'Summary': f'{ask}\n\n{brief}',
                             'Kind': 'general', 'Tags': ASK_TAG, 'Source': 'calendar',
                             'SourceRef': f"calendar:{body.start or ''}:{subject}"[:200]}, ACTOR)
    # The row for this work belongs to the INVITE. Left to ownwork.ensure it became a separate
    # line stamped whenever the session happened to open - so a meeting and the prep for it sat an
    # hour apart on a rail that is meant to read as a day. Same ConversationId as the event keys
    # them together, and ensure() then finds a row already here and adds nothing.
    store.add_message({'TaskId': tid, 'ExternalId': f'prep:{tid}', 'ConversationId': prep_key(body.start, subject),
                       'Channel': ownwork.CHANNEL, 'SourceName': ownwork.SOURCE,
                       'Subject': f'Prep: {subject}'[:200], 'FromName': 'You', 'Status': 'routed',
                       'SentAt': datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 'BodyText': ask})
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

@app.post('/api/tasks/{tid}/dispatch/retry')
def dispatch_retry(tid: int):
    """The owner's Retry after a start failed or ran out of attempts: a new bounded cycle, tried now (PW-087)."""
    if not store.get_task(tid): raise HTTPException(404, 'task not found')
    if not store.dispatch_retry(tid): raise HTTPException(404, 'that task has no queued start')
    store.add_comment(tid, ACTOR, 'human', 'Retrying the start - a fresh set of attempts.')
    store.audit('task', tid, 'dispatch_retry', ACTOR)
    blackboard.drain(store)
    return {'ok': True, 'queued': _queued_info(store.get_dispatch(tid))}

@app.delete('/api/tasks/{tid}/dispatch')
def dispatch_cancel(tid: int):
    """Cancel queued start: the pending dispatch goes; the task is neither deleted nor completed (PW-087)."""
    if not store.get_task(tid): raise HTTPException(404, 'task not found')
    if not store.get_dispatch(tid): raise HTTPException(404, 'that task has no queued start')
    store.clear_dispatch(tid)
    store.add_comment(tid, ACTOR, 'human', 'Cancelled the queued start - the task stays on your list.')
    store.audit('task', tid, 'dispatch_cancel', ACTOR)
    return {'ok': True}

@app.get('/api/funnel/waiting')
def funnel_waiting():
    """What is ranked and still waiting to be judged - what the rail's "250 more" opens. Subjects
    and senders straight off the arrivals, so looking costs no model call."""
    from . import rank
    return rank.waiting(store)


@app.post('/api/funnel/rerank')
def funnel_rerank(): return {'updated': rank.rerank(store, force=True)}

# ── the pipe and the concierge (funnel.py, concierge.py): what comes next, said out loud ──────
class SettleBody(BaseModel): key: str; verb: str = 'done'; hours: float | None = None; only: str | None = None
class SurfaceBody(BaseModel):
    key: str | None = None
    only: str | None = None
    include_surfaced: bool = False
    exclude: str | None = None
    selection_revision: str | None = None
    expected_next_key: str | None = None
    leaving: str | None = None          # the item Next is walking away from: read on the way out (concierge.move_on)
    expected_next_members: list[str] | None = None
class ConciergeSayBody(BaseModel): text: str; key: str | None = None; context_mid: int | None = None
class ConciergeActBody(BaseModel): key: str; verb: str; hours: float | None = None

def _pile_payload(force: bool = False, current: str = None, only: str = None,
                  include_surfaced: bool = False, exclude: str = None) -> dict:
    """The pile as the page draws it, with the selection token Next echoes. One road for the GET,
    for the turn that carries the rail in its answer, and for the settle that does the same."""
    from . import funnel
    from .funnel_selection import capture_selection
    from .processing_navigation import fields
    started = time.time()
    # funnel.pile owns invalidation and single-flight across open tabs. Capture navigation
    # from that exact cached pile; capture_selection accepts it specifically so this endpoint
    # does not rebuild canonical membership a second time.
    cached = funnel.pile(store, force=force) if only is None else None
    events = (cached.get('events') or []) if cached is not None else funnel.announce(store)
    capture = capture_selection(store, only=only, include_surfaced=include_surfaced,
                                exclude=exclude, pile=cached)
    # generated_at: when this read BEGAN (server clock, ms) - the page compares it to its live events
    # to know which writes this read already saw (funnelPile.coveredByReload); transient, outside the revision
    p = {**capture.pile, **fields(store, capture), 'generated_at': int(started * 1000),
         'alerts': funnel.alerts(store, capture.pile['items']), 'events': events}
    # ...and what the page is HOLDING: an item whose review was decided (or whose task closed)
    # leaves the pile, and nothing told the page - so a sent reply sat on the table as
    # "reply pending" for as long as the tab stayed open (the owner, 2026-09-03: "why is it
    # showing back up if the ai agent replied, i edited it and sent??"). Looked up in the build
    # the pile came from, not a second one.
    if current: p = {**p, 'current': funnel.next_item(store, current, items=funnel.full_items(store) if cached is not None else None)}
    # Current is query-specific and may be absent from the ordinary pile. Include
    # its complete presentation in the revision after attaching it to the response.
    return funnel.present(store, p)

def _pile_along(only: str = None, include_surfaced: bool = False, exclude: str = None) -> dict | None:
    """The rail read once after a write and carried in that write's answer, so the page holds it
    instead of asking for the same rows again (design B, 2026-09-17: a press of Next was two of these
    reloads at 1.5-2 s each). Scoped the way the page will hold it. Never the answer's failure: the
    page falls back to its own load when nothing rides along."""
    try: return _pile_payload(force=True, only=only, include_surfaced=include_surfaced, exclude=exclude)
    except Exception as e:
        logger.debug(f'the pile did not ride along: {e}'); return None

@app.get('/api/funnel/pile')
def funnel_pile(force: bool = False, current: str = None, only: str = None,
                include_surfaced: bool = False, exclude: str = None):
    """The ranked pile the Assistant page draws: next-first, every item with the words it rests
    on, plus the alerts that interrupt. Cached a few seconds - it is polled while the page is open."""
    from .funnel_selection import SelectionUnavailable
    try: return _pile_payload(force, current, only, include_surfaced, exclude)
    except SelectionUnavailable as error:
        raise HTTPException(503, error.detail) from error
    except processing_all.AllError as error:
        raise HTTPException(error.status, error.detail) from error

@app.post('/api/funnel/settle')
def funnel_settle(body: SettleBody):
    from . import concierge, funnel, general
    try: out = funnel.settle(store, body.key, body.verb, ACTOR, body.hours)
    except ValueError as e: raise HTTPException(422, str(e))
    if body.verb in ('done', 'later', 'skip'):                              # settled: off the table, and nothing chosen in its place
        dock = general.dock_task(store, ACTOR)[0]['TaskId']
        if concierge.current_key(store, dock) == body.key: concierge.set_current(store, dock, None, ACTOR)
        # the table is empty now, so the page's next scope excludes nothing: the rail comes back captured that way
        out = {**out, 'pile': _pile_along(only=body.only)}
    return out

@app.get('/api/concierge')
def concierge_state():
    """The conversation as it stands: the dock task, its turns with their cards, the AI choices."""
    from . import concierge, general
    task, _ = general.dock_task(store, ACTOR)
    options = general.provider_options(store)
    pick = concierge.pick(store)
    chosen = next((o for o in options if o['pick'] == pick), None)
    model = str(store.get_settings().get(concierge.MODEL_KEY) or '').strip() or (chosen or {}).get('model') or ''
    if pick.startswith('cli:') and not str(store.get_settings().get(concierge.MODEL_KEY) or '').strip():
        model = concierge.LIGHT_DEFAULT.get(re.split(r'[\\/]', str((chosen or {}).get('label') or pick[4:])).pop().split(' ')[0].lower(), model) or model
    from . import remote_assistant
    return {'task': task, 'ref': task_ref(task['TaskId']), 'messages': concierge.history(store, task['TaskId']),
            # the persisted Current, validated against the pile - never the last card of the history (PW-162)
            'current': concierge.restore_current(store, task['TaskId']),
            'providers': general.brain_options(store, keep=pick), 'pick': pick,
            'provider': (chosen or {}).get('label') or pick, 'model': model,
            # the chats this walk can be handed to, and the one it is in right now
            'doorways': remote_assistant.doorways(store), 'handoff': remote_assistant.handoff(store)}

class HandoffBody(BaseModel): channel: str

def _hands_off():
    """Refuse a desktop turn while the walk is in a chat. Two screens answering the same item is how
    the same mail gets replied to twice - the tab locks itself, and this is the same rule in the API."""
    from . import remote_assistant
    h = remote_assistant.handoff(store)
    if h: raise HTTPException(409, f"the walk is in {remote_assistant.LABELS[h['channel']]} - take it back here first")

@app.post('/api/concierge/handoff')
def concierge_handoff(body: HandoffBody):
    """Send the walk to a chat the owner already has connected: it says hello there, and the tab locks."""
    from . import remote_assistant
    try: return remote_assistant.start_handoff(store, body.channel, ACTOR)
    except ValueError as e: raise HTTPException(422, str(e))
    except RuntimeError as e: raise HTTPException(502, str(e))       # the bridge or the bot could not be reached

@app.post('/api/concierge/handoff/end')
def concierge_handoff_end():
    """Take it back: the chat is told the walk is over there, and the desktop is its own again."""
    from . import remote_assistant
    return remote_assistant.end_handoff(store, ACTOR)

class ConciergeAiBody(BaseModel): pick: str | None = None; model: str | None = None

@app.post('/api/concierge/ai')
def concierge_ai(body: ConciergeAiBody):
    """Which AI speaks on the Assistant tab - configuration, not a tab-local preference. Empty pick =
    back to the default (the CLI agent on its quick gear). A change starts a fresh CLI conversation."""
    from . import concierge, general
    store.set_setting(concierge.AI_KEY, str(body.pick or ''), ACTOR)
    store.set_setting(concierge.MODEL_KEY, str(body.model or ''), ACTOR)
    task, _ = general.dock_task(store, ACTOR)
    store.set_setting(f"{concierge.SID_KEY}:{task['TaskId']}", '', ACTOR)
    return {'pick': concierge.pick(store), 'model': body.model or ''}

@app.get('/api/funnel/mutes')
def funnel_mutes():
    """The standing "stop showing me these" rules - written when the owner sweeps the pipe with a
    reason, or tells us in advance. Listed so they are never a black box, and removable."""
    from . import funnel                      # module-scope `funnel` here is the rank route, not the module
    return {'data': funnel.mutes(store)}

@app.delete('/api/funnel/mutes/{idx}')
def funnel_unmute(idx: int):
    from . import funnel
    rules = funnel.mutes(store)
    if not 0 <= idx < len(rules): raise HTTPException(404, 'no such rule')
    gone = rules.pop(idx)
    store.set_setting(funnel.MUTES_KEY, json.dumps(rules), ACTOR)
    funnel.invalidate()
    store.audit('setting', 0, 'funnel_unmute', ACTOR, 'human', {'rule': gone})
    return {'ok': True, 'data': rules}

@app.get('/api/concierge/chats')
def concierge_chats(limit: int = 25, before: int = None):
    """Past chats, newest first, a page at a time; `next` is the cursor for the page before this one. Reading
    the list writes nothing (PW-157)."""
    from . import concierge
    limit = max(1, min(int(limit or 25), 100))
    rows = concierge.chats(store, ACTOR, limit=limit, before=before)
    return {'data': rows, 'next': rows[-1]['taskId'] if len(rows) >= limit else None}

@app.get('/api/concierge/chats/{tid}')
def concierge_chat(tid: int):
    from . import concierge, general
    t = store.get_task(tid)
    if not t or not general.is_dock(t): raise HTTPException(404, 'no such chat')
    return {'task': t, 'messages': concierge.history(store, tid)}

@app.post('/api/concierge/next')
def concierge_next(body: SurfaceBody = None):
    """Pull the next thing out of the pipe - or the one named, or the next piece of mail - and say it."""
    from . import concierge
    body = body or SurfaceBody()
    reservation = _navigation_reservation(body)
    if reservation:
        from .processing_navigation import NavigationStale
        from .funnel_selection import SelectionUnavailable
        try:
            def _surface(selected, guard, dock):
                return concierge.surface(store, actor=ACTOR, only=body.only, include_surfaced=body.include_surfaced,
                                         exclude=body.exclude, selection=selected, commit_guard=guard, bound_dock=dock,
                                         leaving=body.leaving)
            out = _with_pile(reservation.run(_surface, ACTOR), body)
            _refresh_after(out)                      # the change-check follows the four (design C)
            return out
        except NavigationStale as error:
            raise HTTPException(409, error.detail) from error
        except SelectionUnavailable as error:
            raise HTTPException(503, error.detail) from error
    if body.key: _refresh_chat_key(body.key)     # a named pull refreshes ITS item first: the item is the subject (PW-050)
    out = _with_pile(concierge.surface(store, body.key, actor=ACTOR, only=body.only,
                                       include_surfaced=body.include_surfaced, exclude=body.exclude, leaving=body.leaving), body)
    if not body.key: _refresh_after(out)         # ...and the walk's Next answers first, then asks the provider (design C)
    return out

def _with_pile(out: dict, body) -> dict:
    """A Next answer with the rail as the turn left it. The item is on the table, so the page will hold
    the rail with everything but it - that is the scope it is captured under. The walk running out
    (no item) leaves the page to its own load; a named pull (`key`) is not a walk."""
    if body.key or not (out.get('item') or {}).get('key'): return out
    return {**out, 'pile': _pile_along(only=body.only, include_surfaced=body.include_surfaced, exclude=out['item']['key'])}

@app.post('/api/concierge/open')
def concierge_open():
    """The first line of a new chat: the day in a breath, and the buttons that start the walk."""
    from . import concierge
    return concierge.open_day(store, actor=ACTOR)

class ConciergeStreamBody(BaseModel):
    mode: str = 'say'; text: str | None = None; key: str | None = None; only: str | None = None; context_mid: int | None = None
    include_surfaced: bool = False; exclude: str | None = None; leaving: str | None = None
    selection_revision: str | None = None
    expected_next_key: str | None = None
    expected_next_members: list[str] | None = None


def _navigation_reservation(body):
    """Validate modern selection fields before dock, model, refresh or stream work."""
    from .processing_navigation import reserve, NavigationStale
    from .funnel_selection import SelectionUnavailable
    names = {'selection_revision', 'expected_next_key', 'expected_next_members'}
    supplied = names.intersection(body.model_fields_set)
    if not supplied:
        return None  # Compatibility for older callers during the staged cutover.
    if (supplied != names or body.key or getattr(body, 'mode', 'next') != 'next'
            or not re.fullmatch(r'[0-9a-f]{64}', body.selection_revision or '')
            or body.expected_next_members is None):
        raise HTTPException(422, 'automatic navigation requires the complete selection binding')
    try:
        return reserve(store, selection_revision=body.selection_revision,
                       expected_next_key=body.expected_next_key,
                       expected_next_members=body.expected_next_members,
                       only=body.only, include_surfaced=body.include_surfaced, exclude=body.exclude)
    except NavigationStale as error:
        raise HTTPException(409, error.detail) from error
    except SelectionUnavailable as error:
        raise HTTPException(503, error.detail) from error

@app.post('/api/concierge/stream')
async def concierge_stream(body: ConciergeStreamBody):
    """One turn of the assistant, streamed: the CLI's tool calls and progress as they happen, then
    `done` with the same payload the plain endpoints return. Same shape as the task assistant's
    stream; the browser walking away detaches, the stop button (cancel) is not wired here yet."""
    from . import concierge
    from .processing_navigation import NavigationStale
    from .funnel_selection import SelectionUnavailable
    _hands_off()                        # the walk is in a chat: the tab is locked and so is its road
    admission = asyncio.create_task(asyncio.to_thread(_navigation_reservation, body))
    try:
        reservation = await asyncio.shield(admission)
    except asyncio.CancelledError:
        def release_admission(done):
            try:
                held = done.result()
                if held: held.close()
            except Exception:
                pass
        admission.add_done_callback(release_admission)
        raise
    loop, events, cancel = asyncio.get_running_loop(), asyncio.Queue(), threading.Event()
    def put(e):
        try: loop.call_soon_threadsafe(events.put_nowait, e)
        except RuntimeError: pass
    def trace(kind, name, detail):
        if kind == 'prompt' or (kind == 'tool' and name == 'cli'): return    # the prompt and the launch line are ours, not news
        put({'type': kind, 'name': name, 'detail': detail if isinstance(detail, (dict, str)) else str(detail)})
    def work():
        try:
            # the item first, then its source (PW-050): a named item refreshes itself; Next without a key refreshes
            # what it is about to surface, every channel of an FYI batch once, and re-picks if the pile moved
            started = []
            def fetched(n):                      # once per turn, as the new lines land - the result line follows
                if not started: started.append(n); put({'type': 'context_update', 'say': RETRIAGE_STARTED, 'stage': 'started', 'new': n})
            # A typed question polls NOTHING up front: the words are read first, and the item is
            # brought in below only if the answer turns out to be about it. A NAMED pull still refreshes,
            # because there the item IS the subject (PW-050). The walk's Next does not either: it answers
            # from the rail and the change-check follows the four (_refresh_after, design C, 2026-09-17).
            if body.key and body.mode != 'say': freshness = _refresh_chat_key(body.key, body.context_mid, on_fetched=fetched)
            else: freshness = {}
            if freshness.get('polled'):
                put({'type': 'tool_call', 'name': 'sync_messages',
                     'detail': {'new': freshness.get('added', 0)}})
            # said BEFORE the answer, once per new revision (PW-052/057): the owner reads that the thread moved
            # and went through triage, then the assistant's read of it
            # Surfacing an item IS about that item, so the owner reads that it moved before its
            # introduction. A typed question is not: it is triaged first, and the item is brought in
            # only when the answer turns out to be about it (see concierge_say).
            notice = _notice_once(freshness) if body.mode != 'say' else ''
            if notice: put({'type': 'context_update', 'say': notice})
            if body.mode == 'open': out = concierge.open_day(store, actor=ACTOR, trace=trace, cancel=cancel)
            elif body.mode == 'next':
                if reservation:
                    out = reservation.run(lambda selected, guard, dock: concierge.surface(
                        store, actor=ACTOR, only=body.only, trace=trace, cancel=cancel,
                        include_surfaced=body.include_surfaced, exclude=body.exclude,
                        selection=selected, commit_guard=guard, bound_dock=dock, leaving=body.leaving), ACTOR)
                else:
                    out = concierge.surface(store, body.key, actor=ACTOR, only=body.only, trace=trace, cancel=cancel,
                                            include_surfaced=body.include_surfaced, exclude=body.exclude,
                                            leaving=body.leaving)
            else: out = concierge.say(store, body.text or '', body.key, actor=ACTOR, trace=trace, cancel=cancel, item=freshness.get('item'))
            if notice: out['context_update'] = notice
            if body.mode == 'next': out = _with_pile(out, body)       # the rail rides along (design B)
            put({'type': 'done', **out})
            if body.mode == 'next' and not body.key: _refresh_after(out)     # after the answer, never before it (design C)
        except NavigationStale as error:
            put({'type': 'error', 'code': 'selection_stale', 'detail': error.detail, 'error': str(error)})
        except SelectionUnavailable as error:
            put({'type': 'error', 'code': 'selection_unavailable', 'detail': error.detail, 'error': str(error)})
        except processing_all.AllError as error:      # the page retries on this code once membership settles
            put({'type': 'error', 'code': error.detail['code'], 'detail': error.detail, 'error': str(error)})
        except Exception as e:
            logger.warning(f'concierge stream failed: {e}')
            put({'type': 'error', 'error': str(e)})
        finally:
            if reservation: reservation.close()
    try:
        threading.Thread(target=work, daemon=True).start()
    except BaseException:
        if reservation: reservation.close()
        raise
    async def generate():
        while True:
            e = await events.get()
            yield json.dumps(e, default=str) + '\n'
            if e.get('type') in ('done', 'error'): break
    return StreamingResponse(generate(), media_type='application/x-ndjson', headers={'Cache-Control': 'no-cache, no-transform'})

@app.post('/api/reports/{sid}/rerun')
def report_rerun(sid: int):
    """Run one report now and hand back what it produced - the assistant's door (an agent token may
    not touch /api/sources, and should not: this changes no configuration). The report lands on the
    Timeline exactly as a scheduled run would."""
    return _rerun_report(sid)


def _spawn_rerun(fn):
    """The rerun's own thread door, so a test can run the work inline without patching the global
    Thread class - which left a refresh thread unjoinable in a later test's teardown (2026-09-18)."""
    threading.Thread(target=fn, daemon=True).start()


def _rerun_report(sid: int, asked: dict | None = None) -> dict:
    """The rerun itself. `asked` is the chat the ask came from (remote_assistant.asking): a run started
    from WhatsApp used to land on the Timeline and tell the chat nothing (the owner, 2026-09-18: "would
    that come back?"). When it lands, that chat gets the summary."""
    src = store.get_source(sid)
    if not src or src.get('Channel') != 'report': raise HTTPException(404, 'no such report')
    try: title = json.loads(src.get('ConfigJson') or '{}').get('title') or src.get('Address')
    except ValueError: title = src.get('Address')
    def work():
        try:
            out = run_report_source(store, src, _llm(), trigger='manual'); store.touch_source(sid)
        except Exception as e:
            logger.warning(f'rerun of report {sid} failed: {e}'); out = {'error': str(e)[:300]}
        if asked:
            from . import remote_assistant
            said = str(out.get('summary') or out.get('said') or out.get('error') or out.get('subject') or 'done').strip()
            failed = bool(out.get('error')) or str(out.get('subject') or '').endswith('FAILED')
            text = (f"{title} {'could not run' if failed else 'landed'}: {said[:900]}"
                    + ('' if failed else f"\n\nIt is in the pipe. Say \"read {title}\" for the whole thing."))
            try: remote_assistant.send(store, asked['channel'], asked['chat'], text, asked.get('connector_id'))
            except Exception as e: logger.warning(f'the landed report could not reach {asked.get("channel")}: {e}')
    # queued, not awaited: the report lands on the Timeline like a scheduled run, and the pipe picks it up
    _spawn_rerun(work)
    try: title = json.loads(src.get('ConfigJson') or '{}').get('title') or src.get('Address')
    except ValueError: title = src.get('Address')
    return {'queued': True, 'sourceId': sid, 'title': title}

@app.post('/api/concierge/say')
def concierge_say(body: ConciergeSayBody):
    from . import concierge
    try:
        # A TYPED TURN POLLS NOTHING. The freshness check belongs where the item is LOADED into the
        # chat - surfaced or pulled - and that is where it still runs. Doing it again on every prompt
        # re-triaged the same item it had just checked, and announced it: asking "can you remove all
        # the reports in the funnel?" answered "New message from Process Error Check arrived... I sent
        # it through triage before continuing" (the owner, 2026-09-07: "that is the retriage, not a
        # actual triage of the same item again? what's the point of that").
        #
        # Nothing is lost. The act boundary guards itself: operations.propose pins ContextRevision and
        # execute refuses a moved one (409), and verdicts.decide re-checks before a reply can leave.
        _hands_off()
        return concierge.say(store, body.text, body.key, actor=ACTOR)
    except ValueError as e: raise HTTPException(422, str(e))

class ConciergeProposeBody(BaseModel): verb: str; key: str; text: str | None = None; table: bool = False

@app.post('/api/concierge/propose')
def concierge_propose(body: ConciergeProposeBody):
    """A card's own button on one entry: the same proposal the words would make (PW-151), confirmed the same way."""
    from . import concierge
    try: return concierge.propose_direct(store, body.verb, body.key, body.text or '', ACTOR, table=body.table)
    except ValueError as e: raise HTTPException(422, str(e))

class SetupBody2(BaseModel): text: str

@app.post('/api/concierge/setup')
def concierge_setup(body: SetupBody2, background: BackgroundTasks):
    """'Set up X': a walk-through task with the owner's words, and the walk STARTS."""
    from . import concierge, general
    try: made = concierge.setup_task(store, body.text, ACTOR)
    except ValueError as e: raise HTTPException(422, str(e))
    # marked HERE, not in the background task: the pane loads its snapshot within a second of this
    # response and has to be told that a session is coming, or it stops looking for one
    general.OPENING.add(made['taskId'])
    background.add_task(_walk_opens, made['taskId'], body.text)
    return made


# What the walk is told to do first. Like OPENING it is an instruction, never the owner's words -
# their ask is already the one human comment on the task, and repeating it back as a second user
# turn is the conversation talking to itself.
WALK_OPENING = (
    "The owner just asked for this in the Assistant chat and is watching this conversation right "
    "now. Begin the walk. Do not restate their ask and do not ask them to confirm they want it. "
    "First line: whether this can be done from here, and name any part that cannot. Then take them "
    "through the FIRST step only - the actual screen, sign-in or setting - and ask the single thing "
    "you need from them to take it. One step per turn, then stop and wait.")


def _walk_opens(task_id: int, text: str):
    """A set-up walk-through actually starts, right after the response, so the chat is already
    bound to it on screen. It used to open a task and say "open it when you want to start", which
    left the owner holding a cold row and doing the walking themselves (the owner, 2026-09-10:
    "it's supposed to walk me through this?").

    Never raises. A walk that could not start costs a sentence, and the task is still there to be
    opened by hand - which is exactly where this stood before."""
    from . import concierge, general
    try:
        if general.session_for(task_id): return          # already in conversation - not ours to interrupt
        if not general.provider_options(store):
            # same reason as _assistant_opens: a session with no brain parks forever, looking live
            logger.info(f'no AI connector, so the walk-through {task_ref(task_id)} cannot start')
            _walk_cannot(task_id, 'No AI is connected yet, so I cannot start the walk. Connect one under '
                                  'Connections and ask me again.')
            return
        try:
            if concierge.walk_is_external(store, text): store.tag_task(task_id, general.SETUP_EXTERNAL, actor=ACTOR)
            general.start_session(store, task_id, actor=ACTOR).send_prompt(WALK_OPENING, as_owner=False, echo=False)
        except Exception as e:
            general.drop_session(task_id)                # and never leave half a session behind
            logger.info(f'the walk-through {task_ref(task_id)} could not start: {str(e)[:200]}')
            # ...and it says so in the conversation. Logged only, a walk that died on its first
            # breath is indistinguishable from one still thinking: an empty pane either way.
            _walk_cannot(task_id, f'The walk could not start: {str(e)[:200]}')
    finally:
        general.OPENING.discard(task_id)


def _walk_cannot(task_id: int, why: str):
    from . import general
    try: store.add_comment(task_id, 'assistant', general.ASSISTANT_TYPE, why)
    except Exception as e: logger.debug(f'the walk {task_ref(task_id)} could not report its own failure - {e}')

@app.post('/api/concierge/act')
def concierge_act(body: ConciergeActBody):
    from . import concierge
    try: return concierge.act(store, body.key, body.verb, ACTOR, _llm(), body.hours)
    except ValueError as e: raise HTTPException(422, str(e))

# ── the waiting room: notes for a working agent, delivered when it stops (waitroom.py) ──
@app.get('/api/tasks/{tid}/waitroom')
def waitroom_list(tid: int):
    if not store.get_task(tid): raise HTTPException(404, 'task not found')
    return {'data': store.waitroom(tid), 'state': waitroom.state(store, tid)[0]}

@app.post('/api/tasks/{tid}/waitroom')
def waitroom_add(tid: int, body: dict):
    """Queue a note for this task's agent. It is typed in the moment the agent parks at its
    prompt - and at once, as the answer, when it is already parked on a question for you."""
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
        try: deliver = json.loads(rv.get('Deliver') or '{}') or {}
        except (TypeError, ValueError): deliver = {}
        if deliver.get('channel') and deliver.get('kind') != 'zoho_invoice':
            from . import outbox as ob
            draft = ob.redraft_review(store, rv)
        elif rv.get('TaskId'):
            _refresh_chat_context(task_id=rv.get('TaskId'), message_id=rv.get('MessageId'))
            draft = responder.write_draft(store, rv['TaskId'], rid, actor=ACTOR)
        else:
            message = store.get_message(rv.get('MessageId'))
            if not message: raise RuntimeError('the message behind this reply no longer exists')
            _refresh_chat_context(message_id=message['MessageId'])
            message = _latest_context_message(None, message['MessageId']) or message
            draft = responder.draft_for_message(store, message, rid)
    except Exception as e:
        store.set_review_draft_error(rid, str(e)[:300])     # visible beside the draft box, with Retry (PW-046)
        raise HTTPException(422, str(e)[:300])
    store.audit('review', rid, 'redraft', ACTOR)
    return {'ok': True, 'draft': draft}

class EnvelopeBody(BaseModel): mode: str | None = None; to: list[str] | None = None; cc: list[str] | None = None

@app.put('/api/reviews/{rid}/envelope')
def set_review_envelope(rid: int, body: EnvelopeBody):
    """Reply all / Reply to, and editable To/CC, kept with the draft so approval sends exactly this (PW-063/064)."""
    rv = store.get_review(rid)
    if not rv: raise HTTPException(404, 'review not found')
    if rv.get('Status') not in ('pending', 'held'): raise HTTPException(409, 'this reply has already been decided')
    m = store.get_message(rv.get('MessageId')) if rv.get('MessageId') else None
    if not m or str(m.get('Channel') or '').lower() != 'email': raise HTTPException(422, 'only an email reply has a recipient envelope')
    env = store.review_envelope(rid) or outbound.reply_envelope(store, m) or {}
    if body.mode: env = outbound.reply_envelope(store, m, mode=body.mode) or env
    def clean(seq):
        out = []
        for a in seq or []:
            a = str(a or '').strip().lower()
            if a and '@' in a and a not in out: out.append(a)
        return out
    if body.to is not None: env['to'] = clean(body.to)
    if body.cc is not None: env['cc'] = [a for a in clean(body.cc) if a not in env.get('to', [])]
    if not env.get('to'): raise HTTPException(422, 'a reply needs at least one recipient')
    store.set_review_envelope(rid, env)
    store.audit('review', rid, 'envelope', ACTOR, detail={'mode': env.get('mode'), 'to': env.get('to'), 'cc': env.get('cc')})
    return env

@app.patch('/api/reviews/{rid}')
def save_review_text(rid: int, body: TextBody):
    """Save what is in the reply box without deciding or sending it - with the owner's signature applied once
    on an email draft (PW-065); an edit that already carries it is kept as written."""
    rv = store.get_review(rid)
    if not rv: raise HTTPException(404, 'review not found')
    if rv.get('Status') not in ('pending', 'held'):
        raise HTTPException(409, 'this reply has already been decided')
    text = str(body.body or '')[:50_000]
    m = store.get_message(rv.get('MessageId')) if rv.get('MessageId') else None
    if m and str(m.get('Channel') or '').lower() == 'email' and text.strip():
        text = responder.with_signature(text, responder.signature_for(store))
    store.save_review_draft(rid, text)
    store.audit('review', rid, 'edit_draft', ACTOR, detail={'characters': len(text)})
    return {'ok': True, 'draft': text}

def _llm(target_store=None):
    target_store = target_store or store
    try:
        from .llm import build_llm
        return build_llm(target_store)
    except Exception:
        return None

@app.post('/api/ingest/push')
def push(body: MsgBody):
    m = body.dict()
    m['external_id'] = m.get('external_id') or f'api:{datetime.now().isoformat()}'
    m['sent_at'] = m.get('sent_at') or datetime.now().isoformat(sep=' ', timespec='seconds')
    out = ingest_message(store, m, llm=_llm())
    return {**out, 'ref': task_ref(out['task_id']) if out.get('task_id') else None}

@app.post('/api/messages/{mid}/retriage')
def retriage_message(mid: int):
    """Run a safely-filed triage failure through the current brain again.

    It reuses the stored message row, so no connector fetch and no duplicate message are involved.
    claim_retriage is the compare-and-set that prevents a double click creating two tasks.
    """
    m = store.get_message(mid)
    if not m: raise HTTPException(404, 'message not found')
    # the error state is retriable whether or not the failed follow-up is linked to a task; a
    # legacy failure still stored as a taskless filed row is recognised by its diagnostic
    if m.get('Status') != 'error':
        if m.get('TaskId') is not None:
            raise HTTPException(409, 'this message already belongs to a task')
        routes = store.message_routes(mid)
        last = routes[-1] if routes else {}
        if not re.search(r'\btriage\b.*(?:failed|could not read)', str(last.get('Reason') or ''), re.I):
            raise HTTPException(409, 'retry is only available after triage failed')
    brain = _llm()
    if not brain:
        raise HTTPException(422, 'no triage AI is available - check Connections and Settings')
    if not store.claim_retriage(mid):
        raise HTTPException(409, 'triage is already retrying this message')
    from . import ingest as ingest_mod
    try:
        out = ingest_message(store, {**ingest_mod._from_row(m, store), '_mid': mid},
                             actor=ACTOR, llm=brain)
    except Exception as e:
        # Most AI failures are deliberately recorded as errors by ingest_message. This catches only
        # an unexpected pipeline failure so Retry never leaves the row spinning forever.
        now = store.get_message(mid) or {}
        store.place_message(mid, now.get('TaskId'), 'error')
        store.add_route(mid, now.get('TaskId'), 'file', None,
                        f'triage retry failed ({str(e)[:200]}) - unclassified; retry available', [], 'triage',
                        parse_error=str(e)[:1000])
        raise HTTPException(422, str(e)[:300])
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
    # Owner is PROVENANCE - who or what put this row here - and only a CREATE sets it. It was set
    # on every save, and `Owner` is in SOURCE_COLS, so an ordinary Reports-tab save (and the on/off
    # toggle, which posts {SourceId, Active}) silently took the row over: a Telegram chat lost the
    # "discovered: <title>" name ConnectorsView prints, and a seeded row stopped being seeded -
    # which moved the app's own Assistant off its Timeline thread and re-namespaced its ideas
    # (assistant.seeded_source). Editing a row has never been a reason to reassign it.
    if not fields.get('SourceId'): fields.setdefault('Owner', ACTOR)
    # A paired WhatsApp account sees everything its owner does - forty groups and every DM - so
    # there is no catch-all for it; each chat is listed or it does not come in (the owner,
    # 2026-09-17). Telegram keeps its '*': a bot only hears the chats it was added to.
    #
    # Read it off the EXISTING row when the body does not say. The toggle sends {SourceId, Active}
    # and nothing else, so a guard that only read the body let an old '*' be switched back on - a
    # switch that says "on" over a source the poller ignores is worse than the source was.
    was = store.get_source(fields['SourceId']) if fields.get('SourceId') else None
    from .messengers import WA_ALL
    channel = str(fields.get('Channel') or (was or {}).get('Channel') or '')
    address = str(fields.get('Address') or (was or {}).get('Address') or '')
    if channel == 'whatsapp' and address == WA_ALL:
        raise HTTPException(422, 'WhatsApp takes named chats only - add the person or the group you want, '
                                 'not every chat on the account')
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

@app.get('/api/reports/{sid}/invoice-batches')
def invoice_batches(sid: int):
    src = store.get_source(sid)
    if not src: raise HTTPException(404, 'report not found')
    return {'data': store.list_invoice_batches(sid)}

@app.post('/api/reports/{sid}/invoice-batches')
def open_invoice_batch(sid: int, body: dict = None):
    from . import invoice_workflow
    src = store.get_source(sid)
    if not src: raise HTTPException(404, 'report not found')
    try: return invoice_workflow.open_batch(store, src, (body or {}).get('period'))
    except Exception as e: raise HTTPException(422, str(e)[:500])

@app.get('/api/invoice-batches/{bid}')
def invoice_batch(bid: int):
    from . import invoice_workflow
    out = invoice_workflow.detail(store, bid)
    if not out: raise HTTPException(404, 'invoice batch not found')
    return out

@app.patch('/api/invoice-batches/{bid}/items/{iid}')
def update_invoice_item(bid: int, iid: int, body: dict):
    from . import invoice_workflow
    try: return invoice_workflow.update_amount(store, bid, iid, body or {})
    except KeyError as e: raise HTTPException(404, str(e))
    except Exception as e: raise HTTPException(422, str(e)[:500])

@app.post('/api/invoice-batches/{bid}/prepare')
def prepare_invoice_batch(bid: int):
    from . import invoice_workflow
    try: return invoice_workflow.prepare(store, bid)
    except KeyError as e: raise HTTPException(404, str(e))
    except Exception as e: raise HTTPException(422, str(e)[:500])

@app.post('/api/reports/{sid}/replay')
def report_replay(sid: int, body: dict = None, limit: int = 5):
    """What the card's routing WOULD have done to the runs already in the history.

    A rule you have never seen fire is a rule you cannot trust, and waiting for tomorrow's run to
    find out the AI reads your sentence differently is not a way to set one up (2026-09-17). Same
    judge, same prompt, on results that already happened - nothing is posted, sent or filed.
    """
    from .reports import asks_ai, decide, judge_for, judge_prompt, read_result, report_llm, with_judge
    if not store.get_source(sid): raise HTTPException(404, 'report not found')
    cfg = body or {}
    llm = report_llm(store, cfg, _llm()) if asks_ai(cfg) else None
    # resolved once for the whole replay: which judge answers is an install-wide setting, and this
    # is the road the two of them are compared on
    chosen = with_judge(judge_for(store, cfg, llm), llm)
    out = []
    for r in store.report_runs(sid, min(max(1, limit), 20)):
        whole = store.get_report_run(r['runId']) or r
        text = str(whole.get('summary') or '') or '\n'.join(str((l or {}).get('text') or '') for l in (whole.get('lines') or []))
        res = read_result(str(r.get('subject') or '').split('—', 1)[-1].strip(), text, bool(r.get('failed')), r.get('said'))
        out.append({'runId': r['runId'], 'at': r['at'], **decide(cfg, res, **chosen)})
    return {'data': out, 'asksAi': asks_ai(cfg), 'prompt': judge_prompt(cfg)}

@app.get('/api/reports/runs/{rid}')
def report_run(rid: int):
    r = store.get_report_run(rid)
    if not r: raise HTTPException(404, 'run not found')
    return r

@app.get('/api/report-types')
def report_types():
    legacy = {'handbook_search', 'handbook_write', 'handbook_vote'}
    return {'data': [{'type': t, 'status': 'legacy' if t in legacy else ('planned' if t in PLANNED else 'builtin')}
                     for t in REGISTRY]}

@app.get('/api/problems')
def problems_now():
    """What is failing right now, for the bell in the top bar (problems.py): each with where to fix it."""
    from . import problems
    return {'data': problems.collect(store)}

@app.post('/api/problems/{key:path}/dismiss')
def problem_dismiss(key: str):
    """"I have read this one." It comes back if the same thing fails again (problems.signature),
    so this silences a failure you have decided to live with, never a system that keeps breaking."""
    from . import problems
    try: return problems.dismiss(store, key, ACTOR)
    except ValueError as e: raise HTTPException(404, str(e))

@app.get('/api/connectors')
def connectors(request: Request):
    """Channel connector cards (outlook / teams / github). Secrets are write-only.
    ScopeDefault rides along so the card can show what an unset Authority actually means -
    which is per type (winrm starts at admin, a tracker at read), not one global floor.
    Agents still list cards (they have to pick a tool) but ConfigJson drops credential keys."""
    from . import scopes
    rows = [c | {'ScopeDefault': scopes.default_scope(c['Type'])} for c in store.list_connectors()]
    if guard.scope_of(cfg['server'], request.headers) == guard.AGENT:
        rows = [guard.without_config_secrets(c) for c in rows]
    return {'data': rows}

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
    CLI tools (through one representative worker each). Value goes into `triage_ai`."""
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
                   'openrouter': ['openrouter/auto', 'meta-llama/llama-3.3-70b-instruct'],
                   # the private tier leads; -contributor is a data-sharing choice, not a default
                   'meta': ['muse-spark-1.2', 'muse-spark-1.3', 'muse-spark-1.2-contributor']}
    for o in out:
        if o['kind'] == 'api':
            c = store.get_connector(int(o['value'][10:]))
            o['models'] = CONN_MODELS.get((c or {}).get('Type'), [])
    settings = store.get_settings()
    selected = str(settings.get('triage_ai') or '')
    preferred = ([selected[4:]] if selected.startswith('cli:') else [])
    preferred += [x.strip()[4:] for x in str(settings.get('triage_backup_ai') or '').split(',')
                  if x.strip().startswith('cli:')]
    preferred += [str(settings.get('default_agent') or 'coder')]
    # A profile is a job description, not another provider. Researcher, analyst and coder may
    # all use Claude; show one Claude entry rather than several aliases for the same executable.
    # The representative worker remains in the value because its light-model setting is still
    # the runtime source of truth.
    from . import climodels
    out += [{'value': f"cli:{o['value']}", 'label': f"{o['label']} (your CLI)",
             'kind': 'cli', 'ready': o['ready'],
             'models': climodels.catalog(o['cli'])['choices']}
            for o in hub_agents.cli_agent_options(store, preferred=preferred)]
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

@app.get('/api/deps')
def deps_list():
    """What the cards can install, where it would land, and what this build already ships."""
    can, why = deps.can_install()
    return {'can_install': can, 'why': why, 'python': sys.executable, 'frozen': deps.frozen(),
            'where': str(deps.packages_dir()) if deps.frozen() else sys.executable,
            'packages': {k: {'name': deps.pip_name(k), 'installed': deps.installed(k),
                             'bundled': deps.frozen() and k in deps.BUNDLE} for k in deps.OPTIONAL}}


@app.post('/api/deps/install')
def deps_install(body: dict):
    """Install one optional package where THIS Taskuary imports from. The owner's button - it is
    on guard.DENIED, because pip runs arbitrary setup code and an agent asking for that is an
    agent asking to run anything."""
    pkg = str((body or {}).get('package') or '')
    try: out = deps.install(pkg)
    except ValueError as e: raise HTTPException(422, str(e))
    except Exception as e: raise HTTPException(400, str(e))
    store.audit('connector', 0, 'dependency_installed', ACTOR, detail={'package': pkg})
    return out


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
    from . import demo
    if demo.enabled(): return {'connected': False, 'bridge': False, 'node': False, 'manager': {}, 'detail': 'the demo has no bridge - nothing real is reachable from here'}
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
    return wabridge.start(force_install, filter_policy=wabridge.filter_policy(store, cid))

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
    return wabridge.restart(filter_policy=wabridge.filter_policy(store, cid))

@app.get('/api/connectors/{cid}/wa/chats')
def wa_chats(cid: int):
    """Chats reachable through the paired WhatsApp account, for compose and inbound sources."""
    from .messengers import wa_chats as _chats
    c = store.get_connector(cid, with_secret=True)
    if not c or c['Type'] != 'whatsapp': raise HTTPException(404, 'not a WhatsApp connector')
    from . import remote_assistant
    try: rows = _chats(c)
    except RuntimeError as e: raise HTTPException(409, str(e))
    # The owner's own "Message yourself" thread wears a legacy GROUP jid, and so does every group
    # they created - the shape and the number prefix cannot tell those apart, so the count of people
    # in the room does (remote_assistant.own_thread).
    guide = remote_assistant.chat_of(c)
    for r in rows: r['self'] = bool(r.get('group')) and remote_assistant.own_thread(store, c, r, guide)
    return {'data': rows}

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
    cfg = {**f['cfg'], 'auth': 'user', 'account': who['account'], 'name': who['name'],
           **({'granted_scope': t['scope']} if t.get('scope') else {})}      # what was granted, for the send probe (PW-143)
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
def tool_run(body: dict, request: Request):
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
    from .reports import card_of, query_only
    from . import scopes
    connector_id = (body or {}).get('connector_id')
    try: conn = store.get_connector(int(connector_id)) if connector_id else store.get_connector_by_type(card_of(t))
    except (TypeError, ValueError): raise HTTPException(422, 'connector_id must be a number')
    if conn and conn.get('Type') != card_of(t):
        raise HTTPException(422, f'connector {connector_id} is {conn.get("Type")}, not {card_of(t)}')
    if not conn:
        # no card is not 'nothing to check' - it is nothing the owner ever switched on. Types with no
        # card (sqlite, local_file, agent, rest) used to run for anyone holding the API: any file on
        # disk, any database, another agent run (audit 2026-09-02)
        raise HTTPException(403, f'{t} has no connection card an owner turned on - it is not an agent tool')
    if not conn.get('Active'):
        raise HTTPException(403, f'the {t} connection is off - turn it on under Connections')
    if 'tool' not in store_mod.roles_of(conn):
        raise HTTPException(403, f'the {t} connection is not marked as an agent tool (Connections → {t} → Role)')
    hub_tools = {'handbook_search', 'handbook_write', 'handbook_vote',
                 'hub_search', 'hub_write', 'hub_vote', 'hub_comment'}
    actor = _hub_actor(request, (body or {}).get('author')) if t in hub_tools else ACTOR
    try:
        scopes.require(conn, t)
    except PermissionError as e:
        store.audit('tool', conn['ConnectorId'], 'run_refused', actor, detail={'type': t, 'scope': scopes.scope_of(conn)})
        raise HTTPException(403, str(e))
    try:
        # the body says WHAT to run, never WHERE: a base_url/account/server in it used to override the
        # card's, sending the card's token to a host of the caller's choosing (reports.query_only)
        tool_cfg = {**query_only(body), 'type': t}
        if t in hub_tools:
            # The token decides who spoke. A tool payload cannot claim to be the owner or
            # another agent, even though the executor accepts an author for internal calls.
            tool_cfg['author'] = actor
        head, out = REGISTRY[t](resolve_cfg(store, tool_cfg))
    except Exception as e:
        store.audit('tool', (conn or {}).get('ConnectorId', 0), 'run_failed', actor, detail={'type': t, 'error': str(e)[:300]})
        return {'ok': False, 'error': str(e)[:1000]}
    store.audit('tool', (conn or {}).get('ConnectorId', 0), 'run', actor, detail={'type': t, 'headline': str(head)[:200]})
    return {'ok': True, 'headline': head, 'output': (out or '')[:20000]}

@app.post('/api/reports/compose')
def report_compose(body: dict):
    """Say what you want in English; get a report config back, or the questions that stand
    between here and one. Nothing is saved - the answer goes into the same builder the owner
    would have filled in by hand, and Preview runs it for real before anything is scheduled."""
    from .compose import compose
    out = compose(store, (body or {}).get('ask') or '', _llm(), (body or {}).get('answers'),
                  exclude_types=('zoho_monthly_invoices',))
    if out.get('config'):
        store.audit('report', 0, 'compose', ACTOR, detail={'ask': ((body or {}).get('ask') or '')[:300],
                                                           'type': out['config'].get('type'),
                                                           'confidence': out.get('confidence')})
    return out


@app.get('/api/workflows')
def workflows_catalog():
    """Configured workflows and request procedures, read apart (PW-203/207): a job the owner scheduled is not
    a playbook, and a playbook is not a scheduled job."""
    from . import workflows
    return workflows.catalog(store)

@app.post('/api/workflows/compose')
def workflow_compose(body: dict):
    """Describe a stateful invoice or scheduled AI-agent workflow; return an editable draft."""
    from .compose import compose_workflow
    out = compose_workflow(store, (body or {}).get('ask') or '', _llm(), (body or {}).get('answers'))
    if out.get('config'):
        store.audit('workflow', 0, 'compose', ACTOR,
                    detail={'ask': ((body or {}).get('ask') or '')[:300],
                            'type': out['config'].get('type'), 'confidence': out.get('confidence')})
    return out

# ── QuickBooks Online (quickbooks.py): OAuth against Intuit, with a redirect back to this server ──
@app.get('/api/connectors/{cid}/quickbooks/status')
def quickbooks_status(cid: int):
    """What the card needs to draw its Connect box: the redirect URI the Intuit app must carry,
    whether a token is on the card, and which company it is for."""
    from . import quickbooks as qb
    c = store.get_connector(cid, with_secret=True)
    if not c or c['Type'] != 'quickbooks': raise HTTPException(404, 'not a QuickBooks connector')
    conf = json.loads(c.get('ConfigJson') or '{}')
    return {'redirect_uri': qb.redirect_uri(cfg['server']), 'connected': bool(c.get('Secret')),
            'realm_id': conf.get('realm_id') or '', 'env': conf.get('env') or 'production', 'has_app': bool(conf.get('client_id') and conf.get('client_secret'))}

@app.get('/api/connectors/{cid}/quickbooks/authorize')
def quickbooks_authorize(cid: int):
    """Where the browser goes to say yes. The state carries the connector id back."""
    from . import quickbooks as qb
    c = store.get_connector(cid)
    if not c or c['Type'] != 'quickbooks': raise HTTPException(404, 'not a QuickBooks connector')
    nonce = secrets.token_urlsafe(16); _QB_STATES[cid] = (nonce, time.time())
    try: return {'url': qb.authorize_url(json.loads(c.get('ConfigJson') or '{}'), qb.redirect_uri(cfg['server']), f'tq-{cid}-{nonce}')}
    except qb.QuickBooksError as e: raise HTTPException(409, str(e))

_QB_STATES = {}      # connector id -> (nonce, issued at): a callback must answer a Connect we actually started

@app.get('/api/quickbooks/callback', response_class=HTMLResponse)
def quickbooks_callback(code: str = None, state: str = '', realmId: str = None, error: str = None):
    """Intuit sends the browser back here with the code and the company id. The exchange happens
    server-side and the refresh token never reaches the page; the tab just says it worked."""
    from . import quickbooks as qb
    # this page is outside the token gate (Intuit redirects to it), and it echoes what the query
    # string said: escaped, and under a CSP, or a crafted link ran script on the origin that holds
    # the API token (audit 2026-09-02)
    from html import escape as _esc
    csp = {'Content-Security-Policy': "default-src 'none'; style-src 'unsafe-inline'"}
    page = lambda msg, ok=True: HTMLResponse(f'<!doctype html><meta charset=utf-8><title>Taskuary</title><body style="font:15px system-ui;padding:40px;color:#262521;background:#f6f4f1">'
                                             f'<p style="font-weight:700">{"Connected" if ok else "Not connected"}</p><p>{_esc(str(msg))}</p><p style="color:#6e685f">You can close this tab and go back to Taskuary.</p>', headers=csp)
    if error: return page(f'Intuit said: {error}', False)
    if not (code and state.startswith('tq-') and realmId): return page('the callback came back without a code or a company id', False)
    try: cid, nonce = int(state.split('-')[1]), state.split('-', 2)[2]
    except (ValueError, IndexError): return page('bad state', False)
    issued = _QB_STATES.pop(cid, None)
    if not issued or issued[0] != nonce or time.time() - issued[1] > 900: return page('this Connect link is not one Taskuary issued in the last 15 minutes - press Connect on the card again', False)
    c = store.get_connector(cid, with_secret=True)
    if not c or c['Type'] != 'quickbooks': return page('no such QuickBooks card', False)
    try:
        conf = qb.connection(store, cid)
        qb.exchange_code(conf, code, qb.redirect_uri(cfg['server']), realmId)
        store.save_connector({'ConnectorId': cid, 'Active': True}, ACTOR)
        store.audit('connector', cid, 'quickbooks_connected', ACTOR, detail={'realm_id': realmId})
    except Exception as e: return page(str(e)[:300], False)
    return page(f'QuickBooks company {realmId} is connected to the {c["Name"]} card. Press Test there to read the company name.')

# Zoho Invoice uses the same local OAuth shape as QuickBooks, but a token can see multiple
# organizations. Connect selects the first one; the organization id remains editable on the card.
_ZOHO_STATES = {}

@app.get('/api/connectors/{cid}/zoho/status')
def zoho_status(cid: int):
    from . import zoho
    c = store.get_connector(cid, with_secret=True)
    if not c or c['Type'] != 'zoho_invoice': raise HTTPException(404, 'not a Zoho Invoice connector')
    conf = json.loads(c.get('ConfigJson') or '{}')
    return {'redirect_uri': zoho.redirect_uri(cfg['server']), 'connected': bool(c.get('Secret')),
            'organization_id': conf.get('organization_id') or '',
            'organization_name': conf.get('organization_name') or '',
            'has_app': bool(conf.get('client_id') and conf.get('client_secret'))}

@app.get('/api/connectors/{cid}/zoho/authorize')
def zoho_authorize(cid: int):
    from . import zoho
    c = store.get_connector(cid)
    if not c or c['Type'] != 'zoho_invoice': raise HTTPException(404, 'not a Zoho Invoice connector')
    nonce = secrets.token_urlsafe(16); _ZOHO_STATES[cid] = (nonce, time.time())
    try: return {'url': zoho.authorize_url(json.loads(c.get('ConfigJson') or '{}'), zoho.redirect_uri(cfg['server']), f'tq-{cid}-{nonce}')}
    except zoho.ZohoError as e: raise HTTPException(409, str(e))

@app.get('/api/zoho/callback', response_class=HTMLResponse)
def zoho_callback(code: str = None, state: str = '', error: str = None):
    from . import zoho
    from html import escape as _esc
    csp = {'Content-Security-Policy': "default-src 'none'; style-src 'unsafe-inline'"}
    page = lambda msg, ok=True: HTMLResponse(f'<!doctype html><meta charset=utf-8><title>Taskuary</title><body style="font:15px system-ui;padding:40px;color:#262521;background:#f6f4f1">'
        f'<p style="font-weight:700">{"Connected" if ok else "Not connected"}</p><p>{_esc(str(msg))}</p><p style="color:#6e685f">You can close this tab and go back to Taskuary.</p>', headers=csp)
    if error: return page(f'Zoho said: {error}', False)
    if not (code and state.startswith('tq-')): return page('the callback came back without a code', False)
    try: cid, nonce = int(state.split('-')[1]), state.split('-', 2)[2]
    except (ValueError, IndexError): return page('bad state', False)
    issued = _ZOHO_STATES.pop(cid, None)
    if not issued or issued[0] != nonce or time.time() - issued[1] > 900:
        return page('this Connect link expired; press Connect on the Zoho card again', False)
    c = store.get_connector(cid, with_secret=True)
    if not c or c['Type'] != 'zoho_invoice': return page('no such Zoho Invoice card', False)
    try:
        conf = zoho.connection(store, cid)
        zoho.exchange_code(conf, code, zoho.redirect_uri(cfg['server']))
        orgs = zoho.organizations(conf)
        if not orgs: raise RuntimeError('the account returned no Zoho Invoice organizations')
        first = orgs[0]
        zoho._save(conf, organization_id=str(first.get('organization_id')), organization_name=first.get('name'))
        store.save_connector({'ConnectorId': cid, 'Active': True}, ACTOR)
        store.audit('connector', cid, 'zoho_connected', ACTOR, detail={'organization_id': first.get('organization_id')})
    except Exception as e: return page(str(e)[:300], False)
    return page(f'Zoho Invoice organization {first.get("name") or first.get("organization_id")} is connected. Press Test on the card to verify it.')

@app.get('/api/connectors/{cid}/zoho/customers')
def zoho_customers(cid: int):
    from . import scopes, zoho
    c = store.get_connector(cid, with_secret=True)
    if not c or c['Type'] != 'zoho_invoice': raise HTTPException(404, 'not a Zoho Invoice connector')
    try:
        scopes.require(c, 'zoho_customers')
        return {'data': zoho.customers(zoho.connection(store, cid))}
    except Exception as e: raise HTTPException(422, str(e)[:500])

# ── Teller (teller.py): the card runs Teller Connect in the browser; the token it hands back lands here ──
class TellerEnrollBody(BaseModel): access_token: str; enrollment_id: str | None = None; institution: str | None = None

@app.get('/api/connectors/{cid}/teller/status')
def teller_status(cid: int):
    from .teller import CONNECT_JS
    c = store.get_connector(cid, with_secret=True)
    if not c or c['Type'] != 'teller': raise HTTPException(404, 'not a Teller connector')
    conf = json.loads(c.get('ConfigJson') or '{}')
    return {'has_app': bool(conf.get('application_id')), 'connected': bool(c.get('Secret')), 'environment': conf.get('environment') or 'sandbox',
            'institution': conf.get('institution') or '', 'application_id': conf.get('application_id') or '', 'connect_js': CONNECT_JS}

@app.post('/api/connectors/{cid}/teller/enroll')
def teller_enroll(cid: int, body: TellerEnrollBody):
    """Teller Connect finished in the owner's browser: keep the access token (write-only) and name the
    bank on the card. The token never shows again; Test proves it works."""
    c = store.get_connector(cid)
    if not c or c['Type'] != 'teller': raise HTTPException(404, 'not a Teller connector')
    if not body.access_token.strip(): raise HTTPException(422, 'no access token in the enrolment')
    conf = json.loads(c.get('ConfigJson') or '{}')
    conf.update({k: v for k, v in (('enrollment_id', body.enrollment_id), ('institution', body.institution)) if v})
    store.save_connector({'ConnectorId': cid, 'Secret': body.access_token.strip(), 'ConfigJson': json.dumps(conf), 'Active': True}, ACTOR)
    store.audit('connector', cid, 'teller_enrolled', ACTOR, detail={'institution': body.institution or ''})
    return {'ok': True}

# ── SimpleFIN (simplefin.py): the owner pastes a setup token; the server spends it, once ──
class SimpleFinClaimBody(BaseModel): setup_token: str

@app.get('/api/connectors/{cid}/simplefin/status')
def simplefin_status(cid: int):
    """Nothing has to be saved before connecting - there is no application to register and no
    certificate, so `has_app` is true from the start. `connected` is whether the access URL is on
    the card."""
    from .simplefin import BRIDGE, budget
    c = store.get_connector(cid, with_secret=True)
    if not c or c['Type'] != 'simplefin': raise HTTPException(404, 'not a SimpleFIN connector')
    conf = json.loads(c.get('ConfigJson') or '{}')
    return {'has_app': True, 'connected': bool(c.get('Secret')), 'bridge': BRIDGE,
            'institution': conf.get('institution') or '', 'reads_today': budget()}

@app.post('/api/connectors/{cid}/simplefin/claim')
def simplefin_claim(cid: int, body: SimpleFinClaimBody):
    """Trade the setup token for the access URL and keep only the URL (write-only).

    The token is SPENT by this call - SimpleFIN answers a second claim with "Forbidden" - so the
    422s below matter: a mistyped token must fail before it is thrown away, and a token that was
    already claimed must say so in those words rather than looking like a network fault. The
    access URL carries its own basic-auth credentials, which is why it never comes back out."""
    from .simplefin import SimpleFinError, claim, claim_url
    c = store.get_connector(cid)
    if not c or c['Type'] != 'simplefin': raise HTTPException(404, 'not a SimpleFIN connector')
    try: claim_url(body.setup_token)                       # decodes, or 422 with the reason
    except ValueError as e: raise HTTPException(422, str(e)) from e
    try: access = claim(body.setup_token)
    except SimpleFinError as e: raise HTTPException(422, str(e)) from e
    store.save_connector({'ConnectorId': cid, 'Secret': access, 'Active': True}, ACTOR)
    store.audit('connector', cid, 'simplefin_claimed', ACTOR, detail={'host': access.split('@')[-1].split('/')[0]})
    return {'ok': True}

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
    # ...including the write, when the executor IS a write (intacct_create posts the bill): the
    # card's switch and its scope apply to a dry run exactly as to a scheduled one (audit 2026-09-02)
    from .reports import card_of
    from . import scopes
    t = (body or {}).get('type')
    if t == 'zoho_monthly_invoices':
        selected = len((body or {}).get('customers') or [])
        return {'ok': bool(selected), 'headline': f'{selected} customer invoice(s) per monthly batch',
                'summary': ('The schedule opens an editable batch. Prepare creates Zoho drafts; each email waits on the task. Nothing sends automatically.'
                            if selected else 'Choose at least one Zoho customer.'), 'rows': selected, 'chart': ''}
    conn = store.get_connector_by_type(card_of(t)) if t in REGISTRY and card_of(t) else None
    if conn:
        if not conn.get('Active'): return {'ok': False, 'error': f'the {card_of(t)} connection is off - turn it on under Connections'}
        try: scopes.require(conn, t)
        except PermissionError as e: return {'ok': False, 'error': str(e)[:500]}
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

class CliInstallBody(BaseModel):
    name: str
    terminal: bool = False

@app.post('/api/cli/install')
@app.post('/api/cli/install/terminal')
def cli_install(body: CliInstallBody):
    """Install a coding CLI on this machine. The owner's button - it is on guard.DENIED, because
    an agent that can run a vendor installer can be talked into running any installer.

    Returns immediately with the phase: an npm -g of a whole CLI is a minute on a slow line, and
    the browser polls /api/cli/install/state rather than holding a request open for it."""
    from . import cliinstall
    name = str(body.name or '')
    if name not in cliinstall.RECIPES:
        raise HTTPException(422, f'{name} is not one of the CLIs Taskuary installs '
                                 f'({", ".join(sorted(cliinstall.RECIPES))})')
    # one at a time, and say WHOSE - the phase is global, so a second press would otherwise poll
    # the first install's state and report its success as its own
    now = cliinstall.state()
    if now['phase'] == 'installing' and now['name'] != name:
        raise HTTPException(409, f'{now["name"]} is installing right now - one at a time')
    if body.terminal:
        from . import cli_install_terminal
        try: out = cli_install_terminal.start(store, name, actor=ACTOR)
        except (ValueError, RuntimeError, OSError) as e: raise HTTPException(422, str(e))
    else: out = cliinstall.start(name)
    store.audit('connector', 0, 'cli_install_started', ACTOR, detail={'name': name})
    return out

@app.post('/api/cli/update')
@app.post('/api/cli/update/terminal')
def cli_update(body: CliInstallBody):
    """Bring an already-installed CLI up to date, from the AI CLI agents page.

    A CLI too old for the model its own config pins fails every run and says so only in the JSON
    it writes to stdout - codex 0.148.0 answering "requires a newer version of Codex" to everything
    Taskuary asked it (the owner, 2026-09-11). On guard.DENIED beside /api/cli/install, and it
    reports through the same phase the install does: the page polls, it does not hold a request.
    """
    from . import cliinstall
    name = str(body.name or '')
    if name not in cliinstall.UPDATES:
        raise HTTPException(422, f'Taskuary has no updater for {name} '
                                 f'({", ".join(sorted(cliinstall.UPDATES))})')
    now = cliinstall.state()
    if now['phase'] == 'installing' and now['name'] != name:
        raise HTTPException(409, f'{now["name"]} is {now.get("verb") or "install"}ing right now - one at a time')
    if body.terminal:
        from . import cli_install_terminal
        try: out = cli_install_terminal.start(store, name, verb='update', actor=ACTOR)
        except (ValueError, RuntimeError, OSError) as e: raise HTTPException(422, str(e))
    else: out = cliinstall.start_update(name)
    store.audit('connector', 0, 'cli_update_started', ACTOR, detail={'name': name})
    return out

@app.get('/api/cli/install/state')
def cli_install_state():
    """Which phase the install is in, and the absolute path once there is one. The page saves
    THAT as the agent's cmd - a GUI app keeps the PATH it was launched with, so a profile that
    depends on PATH is a profile that works tomorrow instead of now."""
    from . import cliinstall
    return cliinstall.state()

class CliSetupBody(BaseModel): name: str

@app.post('/api/cli/setup')
def cli_setup(body: CliSetupBody):
    """Open the CLI itself in a live pane, as a setup task on the Board, and let it run its own
    onboarding - settings, then the sign-in.

    On guard.DENIED beside /api/cli/install: an agent reads untrusted mail, and an agent that can
    run a CLI's setup on this machine can be talked into running one. A second press reattaches to
    the open pane rather than starting a second one beside it."""
    from . import clis, clisetup
    name = str(body.name or '')
    label = next((k['label'] for k in clis.KNOWN if k['name'] == name), '')
    try: return clisetup.start(store, name, ACTOR, label=label)
    except ValueError as e: raise HTTPException(422, str(e))

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

class SetupSeenBody(BaseModel): step: str

@app.post('/api/setup/seen')
def setup_seen(body: SetupSeenBody):
    """"I have seen that page." The models step asks you to look at where the four brains and their
    models are chosen, and a fresh install already ships working defaults - so there is nothing to
    derive and looking is the whole ask. The only stored step on the list.

    The map is closed: a typo'd step is a 422 rather than a setting nobody can find sitting behind a
    row that can never tick."""
    from . import setup as setup_mod
    key = {'models': setup_mod.SEEN_MODELS}.get(body.step)
    if not key: raise HTTPException(422, f'{body.step!r} is not a step that records being seen')
    # AiDefaults posts this on every mount of the models page, so the write and its audit row must
    # be idempotent - otherwise every visit logs a duplicate event that means nothing new.
    if str(store.get_settings().get(key) or '') != '1':
        store.set_setting(key, '1', ACTOR)
        store.audit('setting', 0, 'setup_seen', ACTOR, detail={'step': body.step})
    return setup_mod.state(store)

class SetupAdoptBrainBody(BaseModel): cli: str

@app.post('/api/setup/adopt-brain')
def setup_adopt_brain(body: SetupAdoptBrainBody):
    """The first CLI that proves it works becomes the triage brain - but only when none is chosen
    yet. CliPicker's `asBrain` branch used to be the only thing that ever wrote `triage_ai`; the
    checklist's "Set up an AI" row now points at the AI CLI agents page instead, and nothing there
    ever wrote it, so installing and testing a CLI there left that row stubbornly grey.

    `body.cli` names a CLI CONNECTION (`claude`, `codex`); `cli:<x>` in `triage_ai` names an agent
    PROFILE, because every reader of it - `setup._ai`, `llm._build_llm`, `llm.make_cli_llm` - looks
    the suffix up with `get_agent`. Writing the connection name stored an id nothing could resolve:
    the row stayed grey AND an install that was happily auto-picking an API key lost its brain
    entirely. So resolve the connection to a worker first, off the same list the Settings brain
    picker is built from, and store nothing at all when no profile runs that CLI - a dangling
    `triage_ai` is worse than an unticked row.

    First writer wins, decided server-side. It is not a compare-and-set: `get_settings` and
    `set_setting` each take and release the store lock and sync routes run in a threadpool, so two
    tests landing together can race - and the loser's only cost is that the other valid CLI won."""
    from . import setup as setup_mod
    worker = next((o['value'] for o in hub_agents.cli_agent_options(store) if o['cli'] == body.cli), '')
    current = str(store.get_settings().get('triage_ai') or '')
    adopted = bool(worker) and not current
    if adopted:
        store.set_setting('triage_ai', f'cli:{worker}', ACTOR)
        store.audit('setting', 0, 'setup_adopt_brain', ACTOR, detail={'cli': body.cli, 'agent': worker})
    return {'ok': True, 'adopted': adopted, **setup_mod.state(store)}

class WalkBody(BaseModel): at: int

@app.get('/api/setup/walk')
def setup_walk():
    """Every stop on the scripted walk, with this install's own facts in it. No AI is involved: the
    chip this sits behind used to open an AI-led walk-through, which could not run before an AI was
    connected - which is when it gets pressed."""
    from . import walk
    return walk.state(store)

@app.post('/api/setup/walk')
def setup_walk_go(body: WalkBody):
    """Next, or a jump. Walking off the end is finishing, and `walk.go` clears the place so the next
    press starts over rather than reopening the last card forever."""
    from . import walk
    return walk.go(store, body.at, ACTOR)

@app.post('/api/setup/walk/reset')
def setup_walk_reset():
    from . import walk
    return walk.reset(store, ACTOR)

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
        return {'ok': False, 'error': 'pyodbc is not installed - the SQL Server card needs it',
                'install': {'package': 'pyodbc', 'name': 'pyodbc'}}

# Models each CLI can be pointed at. The agent profile's own `model` (Connections → AI CLI
# agents) always wins as the default; these are the quick picks the run dialogs offer.
def cli_base(cmd) -> str:
    """'C:\\Users\\me\\...\\codex.exe' and 'codex' are the same CLI. A profile saved with the full
    path (the setup wizard writes what `where` found) offered no model list at all."""
    # both separators: a Windows path in a profile is still codex when the tests run on Linux CI
    return re.sub(r'\.(cmd|exe|bat|ps1)$', '', re.split(r'[\\/]', str(cmd or ''))[-1].lower())


def _agent_work(store_, books=None):
    """Existing work attached to each named worker: live task ownership and scheduled jobs.

    Playbooks and report skills remain the source of truth. This is only a projection for the
    agent card, so naming a worker does not create a second, competing skills system.
    """
    books = {b['slug']: b for b in playbooks.list_all()} if books is None else books
    out = {a['Name']: {'tasks': [], 'reports': []} for a in store_.list_agents(active_only=False)}
    for task in store_.list_tasks(active_only=True):
        assignee = str(task.get('Assignee') or '')
        if not assignee.startswith('agent:'): continue
        name = assignee[6:].strip()
        if not name: continue
        out.setdefault(name, {'tasks': [], 'reports': []})['tasks'].append({
            'taskId': task['TaskId'], 'ref': task_ref(task['TaskId']), 'title': task.get('Title') or '',
            'status': task.get('Status') or 'open', 'playbook': _playbook_brief(task, books),
        })

    # An agent report may be the one flat source or one card in a multi-source report. Either way,
    # the saved report already names the worker and skill; collect those declarations, do not infer
    # expertise from prompts or invent a job title.
    for source in store_.list_sources(active_only=False):
        if source.get('Channel') != 'report': continue
        try: cfg_ = json.loads(source.get('ConfigJson') or '{}')
        except (TypeError, ValueError): continue
        parts = [cfg_] if cfg_.get('type') == 'agent' else [
            s for s in cfg_.get('sources') or [] if isinstance(s, dict) and s.get('type') == 'agent']
        by_agent = {}
        for part in parts:
            name = str(part.get('agent') or cfg_.get('agent') or 'coder').strip()
            skill = str(part.get('skill') or '').strip().lstrip('/')
            if name: by_agent.setdefault(name, set()).update([skill] if skill else [])
        for name, skills in by_agent.items():
            out.setdefault(name, {'tasks': [], 'reports': []})['reports'].append({
                'sourceId': source['SourceId'], 'title': cfg_.get('title') or source.get('Address') or 'Untitled report',
                'kind': 'workflow' if cfg_.get('access') == 'write' else 'report',
                'skills': sorted(skills), 'active': bool(source.get('Active')),
            })
    return out

@app.get('/api/cli/connections')
def list_cli_connections():
    from . import clis, climodels
    known = {r['name']: r for r in clis.detect(store) if not r.get('profile')}
    configured = cfg.get('cli_connections', {})
    rows = []
    for name in dict.fromkeys([*known, *configured]):
        command = configured.get(name) or {k: known[name][k] for k in cli_connections.COMMAND_FIELDS if k in known.get(name, {})}
        command = cli_connections.with_defaults(command)
        base = cli_connections.cli_key(command.get('cmd'))
        row = {**known.get(base, {}), **known.get(name, {}), 'name': name,
               'label': known.get(name, {}).get('label') or name,
               'config': command, 'configured': name in configured,
               'models': climodels.catalog(base)}
        if name in configured: row['installed'] = hub_agents.runs_here(command)
        rows.append(row)
    return {'data': rows}


@app.put('/api/cli/connections/{name}')
def put_cli_connection(name: str, body: dict):
    if not re.fullmatch(r'[a-z0-9][a-z0-9_-]*', name): raise HTTPException(422, 'Invalid connection name')
    if not isinstance(body.get('cmd'), str) or not body['cmd'].strip(): raise HTTPException(422, 'Command is required')
    if not isinstance(body.get('args', []), list) or any(not isinstance(a, str) for a in body.get('args', [])):
        raise HTTPException(422, 'Arguments must be a list of strings')
    if 'resume_args' in body and (not isinstance(body['resume_args'], list) or any(not isinstance(a, str) for a in body['resume_args'])):
        raise HTTPException(422, 'Resume arguments must be a list of strings')
    if 'timeout' in body and (not isinstance(body['timeout'], (int, float)) or body['timeout'] <= 0):
        raise HTTPException(422, 'Timeout must be a positive number')
    base = cli_connections.cli_key(body['cmd'])
    duplicate = next((key for key, c in cfg.get('cli_connections', {}).items()
                      if key != name and cli_connections.cli_key(c.get('cmd')) == base), None)
    if duplicate: raise HTTPException(409, f'This CLI already has a connection: {duplicate}. Edit that connection instead.')
    connection = cli_connections.with_defaults({k: v for k, v in body.items() if k in cli_connections.COMMAND_FIELDS})
    cfg.setdefault('cli_connections', {})[name] = connection
    config.save(cfg)
    cli_connections.sync(cfg, store)
    store.audit('cli_connection', 0, 'save', ACTOR, detail=name)
    return {'ok': True}


@app.delete('/api/cli/connections/{name}')
def delete_cli_connection(name: str):
    users = [n for n, p in cfg.get('agents', {}).items() if p.get('provider') == f'cli:{name}']
    if users: raise HTTPException(409, f'Choose another provider for these profiles first: {", ".join(users)}')
    if name not in cfg.get('cli_connections', {}): raise HTTPException(404, 'Connection not found')
    cfg['cli_connections'].pop(name)
    config.save(cfg)
    store.audit('cli_connection', 0, 'delete', ACTOR, detail=name)
    return {'ok': True}


@app.post('/api/cli/connections/{name}/test')
def test_cli_connection(name: str):
    connection = cfg.get('cli_connections', {}).get(name)
    if not connection: raise HTTPException(404, 'Configure the CLI connection first')
    try:
        result, _, _ = hub_agents.run_cli({**connection, 'timeout': 30}, 'Reply with exactly: ok', lambda *a: None)
        return {'ok': True, 'result': str(result or '')[:300]}
    except Exception as e: return {'ok': False, 'error': str(e)[:400]}


class SkillPathBody(BaseModel):
    path: str
    paths: list | None = None      # the ones ticked in the catalogue; all of them when absent
class SkillImportBody(BaseModel): skills: list

@app.get('/api/skills/found')
def skills_found():
    """Skills already installed on this machine. Read-only, and only files - nothing is learned from
    another tool's configuration."""
    from . import skillimport
    return {'data': skillimport.found()}


@app.post('/api/skills/read')
def skills_read(body: SkillPathBody):
    """A path (a SKILL.md, or a plugin folder) turned into proposals. WRITES NOTHING: the owner reads
    the purpose and the body before any of it becomes a worker's instructions."""
    from . import skillimport
    try: entries = skillimport.read_path(body.path, body.paths)
    except ValueError as e: raise HTTPException(422, str(e))
    except OSError as e: raise HTTPException(422, f'could not read that: {e}')
    if not entries: raise HTTPException(422, 'no SKILL.md there')
    return _skill_proposals(entries)


class SkillUrlBody(BaseModel):
    url: str
    paths: list | None = None

@app.post('/api/skills/list')
def skills_list(body: SkillUrlBody):
    """WHAT IS THERE, before anything is read: one row per skill under a link or a folder - a name, a
    path and which plugin it belongs to. No bodies are fetched and no model is called, so a 252-skill
    repository is a catalogue to choose from rather than a refusal (the owner, 2026-09-18). The
    `paths` of the ones ticked come back to /read or /fetch, which brings in at most PICK_MAX."""
    from . import skillimport
    target = str(body.url or '').strip()
    try:
        rows = skillimport.list_url(target) if target[:8].lower() == 'https://' else skillimport.list_path(target)
    except ValueError as e: raise HTTPException(422, str(e))
    except OSError as e: raise HTTPException(422, f'could not read that: {e}')
    except Exception as e: raise HTTPException(422, f'could not read that: {str(e)[:200]}')
    if not rows: raise HTTPException(422, 'no SKILL.md there')
    return {'data': rows, 'max': skillimport.PICK_MAX}

@app.post('/api/skills/fetch')
def skills_fetch(body: SkillUrlBody):
    """A link - a raw SKILL.md, a GitHub file, or a GitHub repository or folder holding several -
    turned into proposals, the same shape as /read. WRITES NOTHING, and fetches only what the link
    names (skillimport.fetch_url says which shapes)."""
    from . import skillimport
    try: entries = skillimport.fetch_url(body.url, only=body.paths)
    except ValueError as e: raise HTTPException(422, str(e))
    except Exception as e: raise HTTPException(422, f'could not fetch that: {str(e)[:200]}')
    return _skill_proposals(entries)


def _skill_proposals(entries: list) -> dict:
    from . import skillimport, llm as llm_mod
    try: brain = llm_mod.build_llm(store)
    except Exception: brain = None
    # `flat` is the body's length AS A SESSION RECEIVES IT and `doc_chars` is where the seed cuts a
    # rules document: the wizard warns from these, not from a byte count of the file. Of the fifteen
    # skills on the machine this was built on, eleven were over the cut and nine of those were under
    # the old 20KB "large" mark - they arrived truncated with nothing on screen saying so.
    return {'doc_chars': hub_term.DOC_CHARS,
            'data': [dict(skillimport.convert(e, brain), path=e['path'], bytes=e['bytes'],
                          flat=len(hub_term.flatten_rules(e.get('body') or '')), plugin=e.get('plugin') or '')
                     for e in entries]}


@app.post('/api/skills/import')
def skills_import(body: SkillImportBody):
    """Write the ones the owner confirmed. Each becomes an ordinary profile.

    A name that collides with a profile this import did not make is reported in `clashed`, not
    written - one bad name must not discard the rest of a confirmed batch. The wizard offers the
    owner a rename or a resend with that item's `replace: true`."""
    from . import skillimport
    made, clashed = [], []
    for s in (body.skills or []):
        try: made.append(skillimport.save(store, s, bool(s.get('enabled')), replace=bool(s.get('replace'))))
        except skillimport.ProfileCollision as e: clashed.append({'name': e.name, 'kind': e.kind, 'doc': e.doc})
        except (ValueError, OSError) as e: raise HTTPException(422, f'{s.get("name")!r}: {e}')
    # The profile goes into config.toml's table TOO, the way put_agent and seed_profiles write one:
    # the Agents page reads that table, and DELETE /api/agents 404s on a name absent from it - so a
    # profile living only in its store row could be neither edited nor removed anywhere in the UI
    # (seed_profiles' docstring records fixing exactly this once before). It starts from the coding
    # agent's CLI setup, as the shipped roles do, so it is runnable and editable on day one.
    if made:
        keep = hub_agents.cli_inheritance(cfg)
        for name in made:
            try: prof = json.loads((store.get_agent(name) or {}).get('Config') or '{}')
            except ValueError: prof = {}
            cfg.setdefault('agents', {})[name] = {**keep, **cfg['agents'].get(name, {}), **prof}
            try: cli_connections.sync(cfg, store, name)
            except ValueError: pass                # a dangling provider: the store row stands as save() wrote it
        config.save(cfg)
    store.audit('agent', 0, 'skills_imported', ACTOR, detail={'names': made, 'clashed': [c['name'] for c in clashed]})
    return {'imported': made, 'clashed': clashed}


@app.get('/api/agents')
def agents():
    """data = store rows (for dispatch pickers); config = the editable profiles;
    models = the quick-pick model list per agent, keyed by agent name."""
    from . import climodels

    def _models(a):
        prof = json.loads(a.get('Config') or '{}')
        cli = cli_base(prof.get('cmd'))
        cat = climodels.catalog(cli)                       # codex: its own /model list off disk; others: the built-in aliases
        return {'cmd': prof.get('cmd'), 'cli': cli, 'default': prof.get('model'), 'choices': cat['choices'],
                'models': cat['models'], 'current': cat['current'], 'source': cat['source']}
    # the default agent (a setting) comes FIRST: every picker's initial value is the head of
    # this list, so "which CLI opens when I hit Start session" is decided in one place
    # ...and "the default" is the one that can actually run: shipping coder=claude means a
    # machine with only codex installed had every dispatch aimed at a CLI nobody had.
    # A BRAIN THAT IS NOT INSTALLED IS NOT A CHOICE. brain_list was every key in cli_connections,
    # so a CLI the owner had removed - or one seeded and never installed - stayed on every dispatch
    # menu app-wide and failed only when it was started (the owner, 2026-09-18).
    conns = cfg.get('cli_connections') or {}
    brains_here = sorted(k for k in conns if hub_agents.runs_here(cli_connections.with_defaults(conns[k])))
    _cats = {}
    def _brain_cat(key):
        """One catalog read per CLI per request: `catalog` goes to disk, and this is asked twice a brain."""
        if key not in _cats: _cats[key] = climodels.catalog(cli_connections.cli_key(conns[key].get('cmd')) or key)
        return _cats[key]
    from . import general as _general
    head = hub_agents.default_agent(store)
    rows = sorted(store.list_agents(), key=lambda a: a['Name'] != head)
    profs = hub_agents.profiles(store)
    # `roster` is the line triage actually reads for this worker, or why there is none - answered
    # HERE so the Docs page shows the router's real view instead of re-deriving it from Config.
    return {'data': [{**a, 'installed': hub_agents.runs_here(profs.get(a['Name']) or {}),
                      'rules_doc': hub_agents.profile_document(store, a['Name']),
                      'roster': dict(zip(('line', 'reason', 'code'), hub_agents.roster_line(store, a))),
                      'purpose': hub_agents.profile_purpose(a['Name'], profs.get(a['Name']) or {}, a.get('Kind') or 'coding')}
                     for a in rows],
            'config': cfg.get('agents', {}), 'default': head,
            'models': {a['Name']: _models(a) for a in store.list_agents()},
            # WHICH BRAIN each role runs on. The card used to name the role, and after the roles
            # and brains were split every coding row would read `coder` - the owner asked for the
            # coding AGENT (2026-09-16). A brain is not a property of the task, so it is served
            # once per role here rather than stamped on every row.
            'brains': {a['Name']: hub_agents.brain_for(store, a['Name']) for a in rows},
            # every brain that can be picked, and the models each offers. A coding picker chooses
            # the BRAIN: the role is `coder` for every coding task, so offering roles there would
            # be one choice with one entry (the 2026-09-16 spec).
            # the brains a NON-coding hand-off may choose, one per installed CLI (general.py)
            'general_brains': _general.brain_options(store),
            'brain_list': brains_here,
            # every connection keeps its models, installed or not: a task still pinned to a CLI that
            # has since gone has to be able to SAY so, and the picker renders it from this.
            'brain_models': {k: {'choices': _brain_cat(k)['choices'], 'models': _brain_cat(k)['models'],
                                 'installed': k in brains_here,
                                 'default': (cli_connections.gears(cfg, k) or {}).get('model') or ''}
                             for k in (cfg.get('cli_connections') or {})},
            'work': _agent_work(store)}

@app.post('/api/agents/{name}/test')
def agent_test(name: str):
    """One tiny real run through the configured CLI ('Reply with exactly: ok') - proves
    the command exists, flags are right, and headless mode doesn't hang on approvals."""
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
    if not re.fullmatch(r'[a-z0-9][a-z0-9_-]*', name):
        raise HTTPException(422, 'Use a lowercase profile name with letters, numbers, hyphens or underscores')
    row = store.get_agent(name) or {}
    candidate = copy.deepcopy(cfg)
    try:
        profile = cli_connections.set_profile(candidate, store, name, body)
        resolved = cli_connections.resolve(candidate, profile)
    except ValueError as e: raise HTTPException(422, str(e))
    if not str(resolved.get('cmd') or '').strip(): raise HTTPException(422, 'Choose a configured CLI provider')
    profile['kind'] = profile.get('kind') or hub_agents.DEFAULT_PROFILES.get(name, {}).get('kind') or row.get('Kind') or 'coding'
    profile['purpose'] = hub_agents.profile_purpose(name, profile, profile['kind'])
    if profile.get('triage_enabled', True) and not profile['purpose']:
        raise HTTPException(422, 'Describe when triage should choose this profile, or turn off automatic triage routing')
    if profile.get('rules_doc') and not re.fullmatch(r'[a-z0-9][a-z0-9_-]*', str(profile['rules_doc'])):
        raise HTTPException(422, 'Invalid rules document name')
    rules_doc = profile.get('rules_doc')
    if rules_doc and rules_doc != name and not store.get_doc(rules_doc) and not hub_agents.profile_template(store, rules_doc):
        raise HTTPException(422, 'Choose an existing instructions document or this profile\'s own document')
    cfg['agents'] = candidate['agents']
    cfg['cli_connections'] = candidate.get('cli_connections', {})
    config.save(cfg)
    cli_connections.sync(cfg, store, name)
    rules_doc = hub_agents.ensure_profile_document(store, name)
    store.audit('agent', 0, 'save', ACTOR, detail=name)
    return {'ok': True, 'rules_doc': rules_doc, 'triage_available': profile.get('triage_enabled', True) is not False and bool(profile['purpose'])}

@app.delete('/api/agents/{name}')
def delete_agent(name: str):
    if name not in cfg.get('agents', {}): raise HTTPException(404, 'agent not found')
    # An IMPORTED profile's document goes with it: the import wrote it, nothing else shares it, and
    # left behind it would be the body a later profile of the same name silently inherits. A document
    # anyone else wrote (the owner, a template) stays - deleting a worker is not deleting its rules.
    doc = hub_agents.profile_document(store, name)
    orphan = doc == name and store.doc_owner(doc) == 'import'
    cfg['agents'].pop(name)
    config.save(cfg)
    store.delete_agent(name)
    if orphan: store.delete_doc(doc)
    store.audit('agent', 0, 'delete', ACTOR, detail=name)
    return {'ok': True}

def _template_text(name: str) -> str:
    return hub_agents.profile_template(store, name)

def _heal_blank_doc(name: str) -> str:
    """An EMPTY operator document is never what anyone meant: it switches off the rules every prompt
    is stacked on (CODER.md blank = a coder with no rules) and it says nothing an owner wrote. The
    templates have always said "blank the document entirely and the shipped default is used again",
    so that is what happens - here, the moment it is read, not at the next restart."""
    cur = store.get_doc(name)
    if not str(cur or '').strip():
        t = _template_text(name)
        if t.strip():
            store.save_doc(name, t, 'template'); store.audit('doc', 0, 'restored_blank', 'system', detail={'doc': name})
            logger.warning(f'{name}.md was empty - the shipped default is back in place')
            return t
    return cur or ''

@app.get('/api/how-it-works')
def how_it_works():
    """The reference page in Settings → Docs: the Assistant, and the gates a message passes in order.
    Shipped with the app (templates/how-it-works.md) and read-only - it describes what the code does,
    so it is not an operator document to edit and never becomes a `doc` row."""
    from pathlib import Path
    f = Path(__file__).parent / 'templates' / 'how-it-works.md'
    if not f.exists(): raise HTTPException(404, 'the reference page is missing from this build')
    return {'text': f.read_text(encoding='utf-8')}

@app.get('/api/doc/{name}')
def get_doc(name: str):
    """Raw for the editor, rendered so you can see what an agent will actually read."""
    name = hub_agents.profile_document(store, name)
    content = _heal_blank_doc(name)
    return {'name': name, 'content': content, 'rendered': store.doc(name) or '',
            'owner': store.owner()}

@app.put('/api/doc/{name}')
def put_doc(name: str, body: DocBody):
    name = hub_agents.profile_document(store, name)
    # blank = "give me the shipped default back", as the templates' own comments promise
    if not str(body.content or '').strip() and _template_text(name).strip():
        store.save_doc(name, _template_text(name), 'template')
        return {'ok': True, 'restored': True}
    from . import counsel as _counsel
    if name == 'counsel': _counsel.check_budget(store, name, body.content)
    store.save_doc(name, body.content, ACTOR)
    return {'ok': True}

# ── playbooks: the fourth operator document, one file per kind of job (playbooks.py) ──────
# Read by the Docs section's Playbooks shelf and by every connector card (filtered by `uses`). Agents
# may GET these; writing is the owner's (guard.py denies agent tokens) - an agent PROPOSES one.
@app.get('/api/playbooks')
def list_playbooks():
    return {'data': [{k: v for k, v in b.items() if k != 'text'} for b in playbooks.list_all()],
            'template': playbooks.template(), 'folder': str(playbooks.folder())}

@app.get('/api/playbooks/examples')
def playbook_examples(q: str = '', before: int = 0):
    return store.playbook_examples(q[:300], max(0, before))


class PlaybookSetupBody(BaseModel):
    text: str = ''
    message_id: int | None = None
    connector_type: str = ''


def _playbook_opens(task_id: int):
    from . import general
    try:
        general.start_session(store, task_id, actor=ACTOR).send_prompt(
            playbooks.SETUP_OPENING, as_owner=False, echo=False)
    except Exception as e:
        general.drop_session(task_id)
        _walk_cannot(task_id, f'Playbook setup could not start: {e}. You can retry in this conversation.')
    finally:
        general.OPENING.discard(task_id)


@app.post('/api/playbooks/setup')
def setup_playbook(body: PlaybookSetupBody, background: BackgroundTasks):
    from . import general
    if not general.provider_options(store):
        raise HTTPException(422, 'Connect an AI provider in Connections first, then return to create your playbook.')
    try:
        made = playbooks.setup_task(store, body.text, body.message_id, body.connector_type, ACTOR)
    except ValueError as e:
        raise HTTPException(422, str(e))
    general.OPENING.add(made['taskId'])
    background.add_task(_playbook_opens, made['taskId'])
    return made


@app.get('/api/playbooks/{slug}')
def get_playbook(slug: str):
    text = playbooks.read(slug)
    if text is None: raise HTTPException(404, f'no playbook {slug!r}')
    pb = playbooks.parse(text)
    return {'slug': playbooks.slugify(slug), 'content': text, 'title': pb['title'], 'uses': playbooks.uses_of(pb)}

@app.put('/api/playbooks/{slug}')
def put_playbook(slug: str, body: DocBody):
    """'new' as the slug files it under its title."""
    try: out = playbooks.write(slug, body.content)
    except ValueError as e: raise HTTPException(400, str(e))
    store.audit('playbook', 0, 'saved', ACTOR, detail={'slug': out})
    return {'ok': True, 'slug': out}

@app.delete('/api/playbooks/{slug}')
def delete_playbook(slug: str):
    if not playbooks.delete(slug): raise HTTPException(404, f'no playbook {slug!r}')
    store.audit('playbook', 0, 'deleted', ACTOR, detail={'slug': playbooks.slugify(slug)})
    return {'ok': True}

@app.get('/api/learned/graph')
def learned_graph():
    """LEARNED.md as a picture: lines, the verdicts that fed them, each line's score over time,
    the lines that died - the Docs section's Visualize view (discussion #27)."""
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
    answers: list[dict] | dict = {}

@app.get('/api/soul/interview')
def soul_questions():
    """Interview context only; the assistant generates one question at a time."""
    from . import interview
    return {'total': interview.TOTAL_QUESTIONS, 'context': interview.context(store),
            'current': (store.get_doc('soul') or '')[:400], 'owner': store.owner()}

@app.post('/api/soul/interview/next')
def soul_next_question(body: InterviewBody):
    """Use the answers so far to ask one relevant next question, never a fixed form."""
    from . import interview
    try: return {'question': interview.next_question(store, body.answers or [])}
    except ValueError as e: raise HTTPException(422, str(e))

@app.post('/api/soul/interview')
def soul_write(body: InterviewBody):
    """The seven-turn transcript in, SOUL.md out - saved and still theirs to edit."""
    from . import interview
    try: return {'doc': interview.write(store, body.answers or {}, ACTOR)}
    except ValueError as e: raise HTTPException(422, str(e))

@app.post('/api/doc/{name}/generate')
def doc_generate(name: str, days: int = 90):
    """The Docs section's 'Generate from history': read the last N days of the mailbox itself
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
    source = body.source if body.source in ('manual', 'writing') else 'manual'
    mid = store.add_memory({'Scope': body.scope, 'ScopeKey': body.scope_key, 'Note': body.note.strip()[:1000],
                            'Source': source, 'Active': 1, 'CreatedBy': ACTOR})
    store.audit('memory', mid, 'create', ACTOR)
    return {'ok': True, 'memoryId': mid}

@app.patch('/api/memory/{mid}')
def toggle_memory(mid: int, body: MemoryToggle):
    store.set_memory_active(mid, body.active)
    store.audit('memory', mid, 'activate' if body.active else 'deactivate', ACTOR)
    return {'ok': True}

@app.get('/api/audit/recent')
def audit_recent(limit: int = 100): return {'data': store.list_audit(limit=min(limit, 500))}

# Two lanes. The FULL lane reads every connector, judges the queue, watches CI and runs reports,
# one at a time in this process (the DB flag is only for the UI). The CHAT lane reads chat
# connectors on their own fast clock and has their lines judged ahead of the backlog - it used to
# share the full lane's lock, so an AI triage over a 3-day catch-up or a slow report kept Teams
# and WhatsApp from arriving for as long as it ran (PW-001). A connector type is read by ONE lane
# at a time, so dedupe never races two fetches of the same message.
_POLL_BUSY = threading.Lock()
_QUICK_LOCKS, _QUICK_GUARD = {}, threading.Lock()     # one lock per chat type: a hung WhatsApp fetch keeps only its own
def _quick_lock(typ: str) -> threading.Lock:
    with _QUICK_GUARD: return _QUICK_LOCKS.setdefault(typ, threading.Lock())
def _quick_busy() -> bool: return any(l.locked() for l in list(_QUICK_LOCKS.values()))
_LAST_POLL = [time.time()]      # startup's own catch-up counts as the first one
_HEARTBEAT = [0.0]              # ...and when we last wrote down that the app is still up
HEARTBEAT_TICK = 300
POLL_TICK = 30                  # how often the full loop wakes to look at the clock
QUICK_TICK = 5                  # the chat loop looks more often, so "every 30 seconds" means that
SLOW_CHAT_READ = 3.0            # a chat read past this is logged with its length: it is a late phone answer
DRAIN_WAIT = 45                 # the context gate's patience for its lines to be judged (the old lock wait)
CHAT_CONNECTORS = {'teams', 'slack', 'telegram', 'whatsapp', 'imessage', 'discord'}
CHAT_POLL_SECONDS = 30
CONTEXT_FRESH_SECONDS = 60
_FETCHING = {}                  # connector type -> lane reading it right now
_FETCH_CV = threading.Condition()
_STATUS_LOCK = threading.Lock()
_STATUS_OWNERS = {}             # store id -> {token: {lane, what, at, store}}
_STATUS_SEQ = [0]
_DRAIN_WORKERS = {}             # store id -> DrainWorker which captured that exact store
_DRAIN_WORKERS_LOCK = threading.Lock()
_DRAIN_CLOSED = weakref.WeakSet()  # stores shutting down reject a late poll's drain submission


@contextlib.contextmanager
def _claim_fetch(types, lane, wait=False, timeout=None):
    """Atomically reserve the connector types this lane may fetch.

    The old check-then-register pair let two lanes both observe a free connector.  A unique owner
    token also prevents one lane's cleanup from releasing a newer claim after an exception race.
    A waiting correctness gate requires its complete requested set; background lanes take the
    currently available subset and retry skipped connectors on their next clock tick.
    """
    requested = list(dict.fromkeys(types))
    owner = object()
    with _FETCH_CV:
        if wait:
            ready = _FETCH_CV.wait_for(lambda: not any(t in _FETCHING for t in requested),
                                       timeout=timeout if timeout is not None else DRAIN_WAIT)
            claimed = requested if ready else []
        else:
            claimed = [t for t in requested if t not in _FETCHING]
        for t in claimed: _FETCHING[t] = (lane, owner)
    try:
        yield claimed
    finally:
        with _FETCH_CV:
            for t in claimed:
                if _FETCHING.get(t) == (lane, owner): _FETCHING.pop(t, None)
            _FETCH_CV.notify_all()


def _visible_status(owners):
    if not owners: return {'state': 'idle'}
    full = [x for x in owners.values() if x['lane'] == 'full']
    chosen = max(full or list(owners.values()), key=lambda x: x['seq'])
    return {'state': 'running', 'what': chosen['what'], 'at': chosen['at'],
            'phase': chosen['phase'], 'lane': chosen['lane']}


def _status_write(target_store, owners):
    target_store.set_setting('ingest_status', json.dumps(_visible_status(owners)), 'system')


def _status_begin(target_store, lane, what):
    token = object()
    with _STATUS_LOCK:
        _STATUS_SEQ[0] += 1
        owners = _STATUS_OWNERS.setdefault(id(target_store), {})
        owners[token] = {'store': target_store, 'lane': lane, 'what': what, 'phase': 'fetching',
                         'at': datetime.now().isoformat(sep=' ', timespec='seconds'),
                         'seq': _STATUS_SEQ[0]}
        _status_write(target_store, owners)
    return token


def _status_progress(target_store, token, what, *, phase=None):
    with _STATUS_LOCK:
        owners = _STATUS_OWNERS.get(id(target_store), {})
        if token not in owners: return
        owners[token]['what'] = what
        if phase is not None: owners[token]['phase'] = phase
        owners[token]['at'] = datetime.now().isoformat(sep=' ', timespec='seconds')
        _status_write(target_store, owners)


def _status_end(target_store, token):
    with _STATUS_LOCK:
        owners = _STATUS_OWNERS.get(id(target_store), {})
        owners.pop(token, None)
        _status_write(target_store, owners)
        if not owners: _STATUS_OWNERS.pop(id(target_store), None)


def _drain_worker(target_store):
    from . import ingest as ingest_mod
    key = id(target_store)
    with _DRAIN_WORKERS_LOCK:
        if target_store in _DRAIN_CLOSED:
            raise RuntimeError('triage drain is closed for this store')
        worker = _DRAIN_WORKERS.get(key)
        if worker is None:
            worker = ingest_mod.DrainWorker(target_store, lambda: _llm(target_store))
            _DRAIN_WORKERS[key] = worker
        return worker


def join_drains(target_store=None, timeout=None) -> bool:
    """Wait for the exact store's queued triage; used by shutdown and isolated fixtures."""
    target = target_store or store
    with _DRAIN_WORKERS_LOCK: worker = _DRAIN_WORKERS.get(id(target))
    return True if worker is None else worker.join(timeout)


def _open_drain_workers(target_store=None) -> bool:
    """Admit drains for a new lifecycle only after an older worker has fully stopped."""
    target = target_store or store
    key = id(target)
    with _DRAIN_WORKERS_LOCK:
        worker = _DRAIN_WORKERS.get(key)
        if worker and worker.active: return False
        if worker: _DRAIN_WORKERS.pop(key, None)
        _DRAIN_CLOSED.discard(target)
    return True


def _close_drain_workers(timeout=None, target_store=None) -> bool:
    with _DRAIN_WORKERS_LOCK:
        targets = [target_store] if target_store is not None else [w.store for w in _DRAIN_WORKERS.values()]
        keys = [id(target) for target in targets]
        _DRAIN_CLOSED.update(targets)
        workers = [(key, _DRAIN_WORKERS.get(key)) for key in keys if _DRAIN_WORKERS.get(key)]
    end = None if timeout is None else time.monotonic() + timeout
    ok = True
    for key, worker in workers:
        left = None if end is None else max(0, end - time.monotonic())
        stopped = worker.close(left)
        if stopped:
            with _DRAIN_WORKERS_LOCK:
                if _DRAIN_WORKERS.get(key) is worker: _DRAIN_WORKERS.pop(key, None)
        ok = stopped and ok
    return ok


def _ingest_status(what: str = None):
    st = {'state': 'running', 'what': what, 'at': datetime.now().isoformat(sep=' ', timespec='seconds')} if what else {'state': 'idle'}
    store.set_setting('ingest_status', json.dumps(st), 'system')


def _latest_context_message(task_id: int = None, message_id: int = None):
    """Newest inbound line in exactly the context an action is about."""
    if task_id:
        return store.last_inbound_on_task(task_id)
    m = store.get_message(message_id) if message_id else None
    if not m: return None
    cid = m.get('ConversationId')
    return store.last_inbound_in(cid) if cid else m


def _refresh_for_finish(_store, task_id: int, message_id: int) -> dict:
    """coder.finish's refresh (PW-235): the conversation is read from its provider before the result becomes a reply."""
    if _store is not store:
        raise RuntimeError('completion refresh belongs to a different store')
    return _refresh_chat_context(task_id=task_id, message_id=message_id)


def _refresh_chat_context(task_id: int = None, message_id: int = None, grace: bool = False, on_fetched=None) -> dict:
    """Synchronize a live chat before its stored text is used to answer or act.

    The background clock keeps the screen lively; this is the correctness gate.  If an Assistant
    answer, draft, approval, or agent launch is about a chat, its provider is read first and the
    newly ingested lines are attached/triaged before the context is built.
    """
    before = _latest_context_message(task_id, message_id)
    channel = str((before or {}).get('Channel') or '').lower()
    # email is refreshed too (PW-049): through the connector behind the mailbox the message arrived in,
    # incrementally - the poll is a watermark read, and the chain is completed by chains.py, never re-downloaded
    if channel == 'email':
        mailbox = str((before or {}).get('SourceName') or '').lower()
        src = next((x for x in store.list_sources(active_only=False) if x.get('Channel') == 'email' and str(x.get('Address') or '').lower() == mailbox), None)
        conn = store.get_connector(src['ConnectorId']) if src and src.get('ConnectorId') else None
        types = [str(conn.get('Type') or '').lower()] if conn and conn.get('Active') else []
    elif channel in CHAT_CONNECTORS: types = [channel]
    else: return {'polled': False, 'newer': False, 'before': before, 'after': before, 'added': 0}
    connectors = [c for c in store.list_connectors()
                  if c.get('Active') and str(c.get('Type') or '').lower() in types]
    if not types or not connectors:
        return {'polled': False, 'newer': False, 'before': before, 'after': before, 'added': 0, 'channel': channel}
    # `grace`: the chat INTRODUCING an item may lean on a fetch from the last minute - a walk through ten
    # items was ten provider round trips (2026-09-06). An action on it (a reply, an approval, an agent
    # launch) always reads the provider first: that is the correctness gate this function exists for.
    if grace and _recently_fetched(types, store):
        return {'polled': False, 'newer': False, 'before': before, 'after': before,
                'added': 0, 'channel': channel, 'fresh': True}
    added = _poll_reports(0, what=f'refreshing {channel} context', only=types, wait=True, on_fetched=on_fetched)
    if added is False:
        raise RuntimeError('messages are still syncing; I did not use stale chat context - try again in a moment')
    failed = [store.get_connector(c['ConnectorId']) for c in connectors]
    failed = [c for c in failed if c and c.get('LastError')]
    if failed:
        raise RuntimeError(f"I could not refresh {channel}, so I did not use stale chat context: {failed[0]['LastError']}")
    after = _latest_context_message(task_id, message_id)
    newer = bool(after and (not before or after.get('MessageId') != before.get('MessageId')))
    if newer:
        from . import funnel
        funnel.invalidate()
    return {'polled': True, 'newer': newer, 'before': before, 'after': after,
            'added': int(added or 0), 'channel': channel}


from . import coder as _coder_mod
_coder_mod.REFRESH = _refresh_for_finish


_NOTICED = {}      # funnel key -> the message-set revision the owner was last told about (PW-052: once per revision)
# said the moment new lines land on the item under discussion, before their triage result (PW-052/057)
RETRIAGE_STARTED = "New messages came in on this conversation. I'm sending it through triage again before we continue."


def _refresh_items(items: list, on_fetched=None) -> dict:
    """Refresh the sources behind these items - once per channel, not once per item (an FYI batch of
    four Teams lines is one Teams read). Returns the merged freshness."""
    out, done = {'polled': False, 'newer': False, 'added': 0}, set()
    for it in items:
        m = store.get_message(it.get('mid')) if it.get('mid') else None
        ch = str((m or {}).get('Channel') or it.get('channel') or '').lower()
        if not ch or ch in done: continue
        done.add(ch)
        f = _refresh_chat_context(it.get('tid'), it.get('mid'), grace=True, on_fetched=on_fetched)
        out['polled'] = out['polled'] or bool(f.get('polled')); out['newer'] = out['newer'] or bool(f.get('newer'))
        out['added'] += int(f.get('added') or 0)
    return out


_AFTER = collections.deque(maxlen=8)      # the change-checks in flight, so a test (or a shutdown) can wait for them


def _refresh_after(out: dict):
    """The change-check FOLLOWS the four (design C, 2026-09-17). Next used to ask the provider about the
    item it was about to show BEFORE answering - a network wait of 100-1,000 ms inside every press, and a
    re-pick when the thread had moved. Now the answer goes out from the rail, and the provider is asked
    afterwards, here, on a thread: every channel of an FYI batch once (_refresh_items). Mail that arrives
    writes through ingest, the rail's dirty rows and the live event carry it to the page, whose reload
    refreshes the card in place and says so on the strip (funnelPile.currentItemFromPile). The item on
    the table is NOT re-picked. A named pull keeps its up-front refresh - there the item is the subject."""
    item = (out or {}).get('item') or {}
    members = item.get('items') if item.get('kind') == 'fyis' else [item]
    members = [m for m in (members or []) if isinstance(m, dict) and (m.get('mid') or m.get('tid'))]
    if not members: return None
    def work():
        try: _refresh_items(members)
        except Exception as e: logger.debug(f'the change-check after the four could not ask the provider: {e}')
    t = threading.Thread(target=work, daemon=True, name='refresh-after'); _AFTER.append(t); t.start()
    return t


def wait_refresh_after(timeout: float = 5.0):
    """Wait for the change-checks in flight (tests; nothing in the request path waits on them)."""
    for t in list(_AFTER): t.join(timeout)


def _notice_once(freshness: dict) -> str | None:
    """The context-update line, once per new revision of the item (PW-052/057): a poll or a re-render
    that finds nothing new says nothing; the same new line is never announced twice."""
    item = (freshness or {}).get('item') or {}
    if not freshness or not freshness.get('newer') or not item.get('key'): return None
    after = freshness.get('after') or {}
    rev = f"{after.get('MessageId')}:{(store.get_review(item['rid']) or {}).get('Status') if item.get('rid') else ''}"
    if _NOTICED.get(item['key']) == rev: return None
    _NOTICED[item['key']] = rev
    while len(_NOTICED) > 500: _NOTICED.pop(next(iter(_NOTICED)))
    return _context_update_line(freshness)


def _refresh_chat_key(key: str = None, seen_mid: int = None, on_fetched=None) -> dict:
    """Refresh the item held by the Assistant and compare it with what the browser saw."""
    if not key: return {}
    from . import funnel
    item = funnel.next_item(store, key) or funnel.item_for_key(store, key)
    if not item: return {}
    out = _refresh_chat_context(item.get('tid'), item.get('mid'), grace=True, on_fetched=on_fetched)
    # the poll may have landed lines; only then is a second build worth its cost
    fresh = (funnel.next_item(store, key) or funnel.item_for_key(store, key) or item) if out.get('newer') or out.get('added') else item
    after = _latest_context_message(fresh.get('tid'), fresh.get('mid'))
    # `stale` catches a background sync that landed before this request; seen_mid catches the
    # narrower race where it landed after the browser's last five-second pile refresh.
    out['newer'] = bool(out.get('newer') or
                        (seen_mid and after and after.get('MessageId') != seen_mid) or
                        (seen_mid is None and fresh.get('stale')))
    out['item'] = fresh
    out['after'] = after or out.get('after')
    return out


def _context_update_line(freshness: dict) -> str:
    m, item = freshness.get('after') or {}, freshness.get('item') or {}
    who = m.get('FromName') or m.get('FromEmail') or 'Someone'
    ref = item.get('ref') or item.get('title') or 'this thread'
    body = ' '.join(str(m.get('BodyText') or '').split())[:180]
    tail = f': “{body}”' if body else ''
    rv = store.get_review(item['rid']) if item.get('rid') else None
    # the owner answered outside Taskuary (PW-053): the draft was retired by the sync, so say that - not
    # 'redraft it' - and leave any newer ask to triage, which already read it
    if rv and rv.get('Status') == 'superseded':
        return (f'You already answered {ref} outside Taskuary, so the pending draft was retired - nothing to send. '
                'Anything asked since went through triage.')
    draft = ' The earlier draft is now out of date; redraft it before sending.' if rv and rv.get('Status') == 'pending' else ''
    return f'New message from {who} arrived on {ref}{tail}. I sent it through triage before continuing.{draft}'


def poll_forever():
    """The ten-minute sync the Timeline has always PROMISED - made by the server, at last.

    It used to be the BROWSER'S: a setInterval living inside the Timeline tab. So it stopped
    the moment you opened Board or Tasks, because that tab unmounts; it restarted its ten-minute
    countdown every time a filter changed the effect's dependencies; and with no window open
    nothing polled at all - which also meant a report scheduled for 8am Monday only ran if
    somebody happened to have the Timeline on screen at 8am on Monday. The mailbox does not care
    which tab is open, so the clock does not live there any more.

    This is the FULL lane's clock only. The chat clock is quick_forever, on its own thread: while
    this loop sits inside a long sync, a branch here could never fire."""
    while True:
        try:
            # the heartbeat sits OUTSIDE the sync switch on purpose: poll_minutes 0 means
            # "do not go and look", not "the app is closed", and a check that reads arrivals
            # rather than the scheduler has to be able to tell those two apart (TQ-0451)
            if time.time() - _HEARTBEAT[0] >= HEARTBEAT_TICK:
                _HEARTBEAT[0] = time.time(); note_app_up(store)
            try: mins = int(store.get_settings().get('poll_minutes') or 0)
            except (TypeError, ValueError): mins = 10
            if mins > 0 and time.time() - _LAST_POLL[0] >= mins * 60:
                _poll_reports(0, what='syncing')
        except Exception as e:
            logger.warning(f'scheduled poll failed: {e}')      # a bad cycle must not end the loop
        time.sleep(POLL_TICK)


DOORWAY_TICK = 1.0              # the assistant chat is a conversation, not a mailbox - see doorway_forever


def doorway_forever():
    """THE DOORWAY IS NOT ON THE MAIL CLOCK. A message the owner types to the assistant in WhatsApp or
    Telegram waited for that connector's 30-second tick before anything even read it, so a two-step
    walk cost a minute of silence (the owner, 2026-09-15: "30 [seconds] is for incoming. talking to
    whatsapp through assistant should be instant").

    Only connectors that carry an Assistant chat are read here (remote_assistant.polls), and the read
    is the SAME one the chat clock does - the per-type lock in _poll_quick means whichever gets there
    first wins and the other tick is a no-op, and remote_assistant._claim makes a message answered by
    both readers answer once. Nothing else about the poll changes: no reports, no CI."""
    while True:
        try:
            from . import remote_assistant
            types = []
            for c in store.list_connectors():
                if c.get('Active') and c.get('Type') not in types and remote_assistant.polls(store, c):
                    types.append(c['Type'])
            if types: _poll_on_quick_clock(types, timer=False)     # every tick, whatever the chat clock says
        except Exception as e:
            logger.debug(f'doorway poll failed: {e}')
        time.sleep(DOORWAY_TICK)


def quick_forever():
    """The chat clock. poll_minutes 0 is "background sync off", and that includes this clock.

    It also carries the by-the-way push: while the walk is in a phone chat, an interruption has to
    go THERE, and an agent raising its hand is not something a mailbox poll would ever discover.
    That is why it sits outside the sync switch and throttles itself (remote_assistant.push_alerts)."""
    from . import wabridge
    try: wabridge.ready(8)          # whichever lane polls first spends the grace; the other is free
    except Exception as e: logger.debug(f'wa bridge grace skipped: {e}')
    while True:
        try:
            from . import remote_assistant
            try: remote_assistant.push_alerts(store)
            except Exception as e: logger.warning(f'could not send an interruption to the chat: {e}')
            try: mins = int(store.get_settings().get('poll_minutes') or 0)
            except (TypeError, ValueError): mins = 10
            if mins > 0:
                quick = _quick_due()
                if quick: _poll_on_quick_clock(quick)
        except Exception as e:
            logger.exception(f'chat poll failed: {e}')
        time.sleep(QUICK_TICK)


# A chat channel on the ten-minute mailbox clock is a slow conversation. Chat connectors default
# to the 30-second clock; poll_seconds can make one slower (or explicitly zero to leave it only on
# the global clock). The quick pass polls ONLY those connectors and runs no reports or CI.
_QUICK_LAST = {}
_QUICK_LAST_STORE = {}
_QUICK_TIMER = threading.local()


def _recently_fetched(types, target_store=None) -> bool:
    """Whether every requested provider completed a fetch within the context grace period."""
    now = time.time()
    providers = [str(provider).lower() for provider in types]
    return bool(providers) and all(
        now - _QUICK_LAST.get(provider, 0) <= CONTEXT_FRESH_SECONDS
        and (target_store is None or _QUICK_LAST_STORE.get(provider) == id(target_store))
        for provider in providers)


def _poll_on_quick_clock(types, timer: bool = True):
    """Each due chat type on its own thread, marked for the due recheck. One shared chat lane meant a
    bridge that hung for forty seconds skipped every Teams, Slack and Telegram tick in between; now a
    slow type holds only its own lock (_poll_quick) and this tick waits for it no longer than the clock.

    `timer=False` is the doorway's read: it is NOT subject to the chat clock's cadence. Marked as a
    timer read, the doorway's one-second tick was filtered by _quick_due and actually read the
    assistant chat once per poll_seconds - thirty seconds - so "next" typed on the phone sat unheard
    for up to half a minute while the reply itself takes half a second (measured 2026-09-20)."""
    def one(typ):
        _QUICK_TIMER.active = timer
        try: _poll_reports(0, what='syncing', only=[typ])
        except Exception as e: logger.exception(f'chat poll failed ({typ}): {e}')   # with the traceback: 'unhashable type: dict' twice, and no line to go to
        finally: _QUICK_TIMER.active = False
    threads = [threading.Thread(target=one, args=(t,), name=f'quick-{t}', daemon=True) for t in dict.fromkeys(types)]
    for th in threads: th.start()
    deadline = time.monotonic() + QUICK_TICK
    for th in threads: th.join(max(0.0, deadline - time.monotonic()))

def _quick_due() -> list:
    due = []
    for c in store.list_connectors():
        if not c['Active']: continue
        try:
            cfg = json.loads(c.get('ConfigJson') or '{}')
            raw = cfg.get('poll_seconds') if isinstance(cfg, dict) else 0
            # blank is "the default", as the card says - a cleared field saved as '' is not an explicit 0
            if raw is None or str(raw).strip() == '': raw = CHAT_POLL_SECONDS if c.get('Type') in CHAT_CONNECTORS else 0
            secs = int(str(raw).strip())
        except (TypeError, ValueError): secs = 0
        if secs > 0 and time.time() - _QUICK_LAST.get(c['Type'], 0) >= secs:
            due.append(c['Type'])
    return due

def _poll_reports(backfill_hours: float = 0, what: str = 'syncing', startup: bool = False,
                  only=None, wait: bool = False, on_fetched=None, run_reports: bool = True):
    """The full lane; `only` hands the call to the chat lane (_poll_quick) instead."""
    if only is not None:
        return _poll_quick(only, what, wait, timer=bool(getattr(_QUICK_TIMER, 'active', False)), on_fetched=on_fetched)
    target_store = store                 # a test or shutdown cannot retarget work already started
    # one full poll at a time, enforced by a lock instead of the old 10-minute timestamp guard: a
    # slow catch-up (CLI triage over a 3-day backfill) legitimately outlives 10 minutes, so
    # the timeline's auto-sync kept starting SECOND polls over the same watermarks - each one
    # rewriting 'running', and the "catching up" banner never ended.
    acquired = _POLL_BUSY.acquire(timeout=DRAIN_WAIT) if wait else _POLL_BUSY.acquire(blocking=False)
    if not acquired:
        logger.info('poll already running - skipped'); return False
    _LAST_POLL[0] = time.time()  # a manual Sync now resets the clock too, so the timer
                                 # does not fire again moments later over the same watermarks
    status = _status_begin(target_store, 'full', what)
    # WHERE A PASS SPENDS ITS TIME, in one line at the end. The startup catch-up sat behind the
    # "catching up" banner for minutes with nothing in the log between its phases, so "startup took
    # almost 10 minutes" (the owner, 2026-09-18) could not be answered: reading the mailboxes, judging
    # the arrivals, or running the reports? Each phase stamps here; the line at the end says which.
    t0, spent = time.monotonic(), {}
    def _lap(name):
        nonlocal t0
        now = time.monotonic(); spent[name] = spent.get(name, 0.0) + now - t0; t0 = now
    try:
        # channels FIRST: the Morning digest is a report over Taskuary's own data, and run
        # before the catch-up it would summarize yesterday while today sat in the mailbox
        from .channels import poll_channels, _poll_jobs
        # the ORIGINAL what is kept and appended to: "catching up on the last 3 day(s)" is
        # the context, "reading outlook · 12 in so far" is the progress, and replacing the
        # first with the second loses why the poll is running at all
        def _say(kind, so_far): _status_progress(target_store, status, f'{what} · reading {kind}' + (f' · {so_far} in so far' if so_far else ''))
        # show first, judge next: the poll stores every message as it reads it (the timeline
        # shows them at once, wearing 'triaging'), and the AI calls come afterwards, in order
        from . import ingest as ingest_mod
        # a type the chat lane is reading this very second is left to it (one lane per type)
        mine = list(dict.fromkeys(c['Type'] for c, _ in _poll_jobs(target_store)))
        with _claim_fetch(mine, 'full') as types:
            try:
                with ingest_mod.deferred():
                    added = poll_channels(target_store, backfill_hours, progress=_say, only=types) if types else 0
                # "checked" means every source was read: a type the chat lane held this cycle was not,
                # so the stamp waits for a cycle that read them all. Connector errors stay intact.
                if types and set(types) == set(mine):
                    target_store.set_setting('ingest_last_fetch_completed_at', str(time.time()), 'system')
            finally:
                # A full pass IS a chat attempt (PW-002). Stamp before releasing its connector
                # claims, so the quick clock cannot enter the release-to-stamp gap and duplicate it.
                now = time.time()
                for t in types:
                    if t in CHAT_CONNECTORS:
                        _QUICK_LAST[t] = now
                        _QUICK_LAST_STORE[t] = id(target_store)
        _lap('reading')
        def _left(n): _status_progress(target_store, status, f'{what} · processing messages' + (f' · {n} left' if n else ''), phase='triaging')
        # Drain progress runs after a judgement finishes. Publish the phase before
        # submitting so even the first slow judgement cannot still say "reading".
        _left(0)
        try:
            ticket = _drain_worker(target_store).submit(progress=_left)
            ticket.wait()                   # full sync/reports retain their established sequencing
            if ticket.error: logger.warning(f'deferred triage drain failed: {ticket.error}')
        except Exception as e:
            logger.warning(f'deferred triage drain failed: {e}')
        # ...and the rows an EARLIER sync could not judge, now that this one has a brain to ask.
        # After the drain, so today's arrivals are judged first and a still-dead endpoint is
        # discovered on them rather than on the backlog (ingest.retry_failed_triage).
        try:
            retried = ingest_mod.retry_failed_triage(target_store, _llm(target_store))
            if retried: _status_progress(target_store, status, f'{what} · {retried} retried', phase='triaging')
        except Exception as e:
            logger.warning(f'retrying stranded triage failures failed: {e}')
        _lap('judging')
        # the git loop: a task's PR is watched here, and a red build goes back to the agent
        # that wrote the code (ci.py) - off unless the owner turned ci_watch on
        _status_progress(target_store, status, what, phase='checking')
        try:
            from . import ci
            ci.poll(target_store)
        except Exception as e:
            logger.warning(f'CI poll failed: {e}')
        # the agent wall composts once a day: yesterday's notes become one summary per checkout,
        # so what an agent reads tomorrow is what still matters (blackboard.roll_up)
        try:
            blackboard.roll_daily(target_store)
        except Exception as e:
            logger.warning(f'the wall roll-up failed: {e}')
        _status_progress(target_store, status, what, phase='running_reports')
        try:                                            # ...and archived chats past their keep-days go, once a day (retention.py)
            from . import retention
            retention.tick(target_store)
        except Exception as e:
            logger.warning(f'chat retention skipped: {e}')
        try:                                            # the bridge's log is on the same daily clock
            from . import wabridge
            wabridge.trim_log(target_store)
        except Exception as e:
            logger.warning(f'whatsapp log trim skipped: {e}')
        _lap('housekeeping')
        # A startup catch-up says NO here: pulling the inputs in is what 'catching up' means,
        # and the reports that were due get a pass of their own behind it (catch_up_on_startup).
        if run_reports:
            run_due_reports(target_store, startup)      # ...the seeded 'Assistant' report among them (assistant.py)
            _lap('reports')
            try:                                        # ...and the phone's morning line, once a day (remote_assistant)
                from . import remote_assistant
                remote_assistant.morning_line(target_store)
            except Exception as e:
                logger.warning(f'the morning line was skipped: {e}')
        return added
    finally:
        try:
            if spent:
                total = sum(spent.values())
                logger.info(f"full pass ({what}) took {total:.0f}s: " + ' · '.join(f'{k} {v:.0f}s' for k, v in spent.items()))
        finally:
            try: _status_end(target_store, status)
            finally: _POLL_BUSY.release()


def _poll_quick(only, what: str = 'syncing', wait: bool = False, timer: bool = False, on_fetched=None):
    """The chat lane: read ONLY these connector types, put their lines first on the one ordered
    drain worker, and release the fetch clock - no CI, no reports.

    Returns what it added, or False when nothing was read: the lane was busy, every type was in
    the full lane's hands, or the fetch failed - and with wait=True (the context gate before an
    answer about a chat) also waits until its lines' complete routes finish within DRAIN_WAIT. The fast
    clock is stamped when an ATTEMPT ENDS, success or failure: a broken connector retries one
    interval later, while an attempt that never ran is not stamped and is due again next tick.
    A full lane owns the visible banner while both are active; either lane remains truthful when
    the other finishes first."""
    target_store = store                 # every asynchronous drain keeps this exact store
    deadline = time.monotonic() + DRAIN_WAIT if wait else None
    held = [t for t in dict.fromkeys(only)
            if (_quick_lock(t).acquire(timeout=DRAIN_WAIT) if wait else _quick_lock(t).acquire(blocking=False))]
    if not held:
        # named, and only when the wait is long enough to be the reason a chat answer is late: the
        # live log had 161 anonymous "skipped" lines and nothing to say which lane or how long
        logger.info(f"chat poll already running - skipped {', '.join(dict.fromkeys(only))}"); return False
    only = held                          # a type another tick still holds is left to it; it is due again next tick
    ticket, added, fresh_channels = None, False, []
    try:
        remaining = max(0, deadline - time.monotonic()) if wait else None
        with _claim_fetch(list(dict.fromkeys(only)), 'quick', wait=wait, timeout=remaining) as types:
            # The timer computed its due list before admission. A full fetch may have completed
            # and stamped one of these connectors meanwhile; recheck while our claim closes that
            # stale-decision race. Explicit context refreshes intentionally bypass the cadence.
            if timer:
                still_due = set(_quick_due())
                types = [typ for typ in types if typ in still_due]
            if types:
                status = _status_begin(target_store, 'quick', what)
                try:
                    from .channels import CH2SRC, poll_channels
                    from . import ingest as ingest_mod
                    fresh_channels = list(dict.fromkeys(CH2SRC[t] for t in types if t in CH2SRC))
                    def _say(kind, so_far):
                        _status_progress(target_store, status, f'{what} · reading {kind}' + (f' · {so_far} in so far' if so_far else ''))
                    t_read = time.monotonic()
                    with ingest_mod.deferred():
                        added = poll_channels(target_store, 0, progress=_say, only=types)
                    # a slow read is the whole latency of a phone turn: the doorway cannot hand the
                    # owner's line to the assistant until this returns (the owner, 2026-09-20:
                    # "hitting next or 3 in whatsapp takes a while")
                    if (took := time.monotonic() - t_read) > SLOW_CHAT_READ:
                        logger.info(f"chat poll {', '.join(types)} read {int(added or 0)} line(s) in {took:.1f}s")
                    # new lines are announced the moment they LAND (PW-052): the caller says retriage started,
                    # then waits below for the result - the owner is never shown the result as the first word
                    if on_fetched and added:
                        try: on_fetched(int(added))
                        except Exception as e: logger.warning(f'retriage notice failed: {e}')
                    ticket = _drain_worker(target_store).submit(fresh=fresh_channels, only_fresh=True)
                except Exception as e:
                    logger.exception(f"chat poll failed ({', '.join(types)}): {e}")
                finally:
                    now = time.time()
                    for t in types:
                        _QUICK_LAST[t] = now
                        _QUICK_LAST_STORE[t] = id(target_store)
                    _status_end(target_store, status)
    finally:
        for t in held: _quick_lock(t).release()
    # Waiting belongs to the explicit action's correctness gate, not the connector fetch lane.
    # Background ticks can claim and fetch this connector while its earlier rows are triaged.
    if ticket is None: return False
    if wait:
        remaining = max(0, deadline - time.monotonic())
        if not ticket.wait(remaining) or ticket.error: return False
        remaining = max(0, deadline - time.monotonic())
        if not ingest_mod.await_quiet(target_store, fresh_channels, timeout=remaining): return False
    return added


def _catchup_hours(ceiling_days: int) -> float:
    """How far past the watermark startup actually needs to reach: the time the app was CLOSED,
    not the full `startup_sync_days` ceiling. Reopening ten minutes after closing used to re-read
    three days of every mailbox (dedupe threw it all away, slowly - the whole timeline sat behind
    a 'catching up' banner for it). Under an hour of gap is what the watermark already covers.

    Hours, not days. Rounding the gap UP to a whole day and then measuring it from `now` reached
    back behind the watermark by the rounding: closed 8.75h, it asked Graph for 24h and pulled 272
    messages the database already had to keep 93 (the owner's mailbox, 2026-09-17). The gap plus
    channels.STARTUP_OVERLAP is the whole question - the ceiling only ever caps it."""
    last = max((str(s.get('LastPolledAt') or '') for s in store.list_sources()), default='')
    ceiling = ceiling_days * 24
    if not last: return ceiling
    try: gap_h = (datetime.now() - datetime.fromisoformat(last.replace(' ', 'T'))).total_seconds() / 3600
    except ValueError: return ceiling
    from .channels import STARTUP_OVERLAP
    return 0 if gap_h <= 1 else min(ceiling, gap_h + STARTUP_OVERLAP.total_seconds() / 3600)


def catch_up_on_startup():
    """Whatever arrived while the app was closed was polled by nobody, and Taskuary is not a
    service - it is a window you open. So opening it reaches back past the watermark - but only
    as far as the app was actually closed, with `startup_sync_days` (default 3) as the ceiling.
    0 turns the startup poll off entirely."""
    try: days = int(store.get_settings().get('startup_sync_days') or 0)
    except ValueError: days = 0
    if days <= 0: return
    hours = _catchup_hours(days)
    logger.info(f"startup: {'incremental poll (closed under an hour)' if hours == 0 else f'catching up on the {hours:.1f} hour(s) it was closed'}")
    def _catch_up():
        # the bridge's launch grace, spent here instead of in front of the owner's first request
        from . import wabridge
        try: wabridge.ready(8)
        except Exception as e: logger.debug(f'wa bridge grace skipped: {e}')
        # EVERYTHING IN FIRST. A report is not the mail, and running the due ones inside this
        # pass charged their minutes to the catch-up: 27 hours of mail was 91 s of a 264 s
        # startup and six reports were the other 165 s, all of it behind one 'catching up on
        # the 27 hour(s)' banner (measured on the owner's box, 2026-09-19). So the catch-up
        # ENDS when the mail is in and judged...
        _poll_reports(hours, what=f'catching up on the {hours:.0f} hour(s) it was closed' if hours else 'syncing',
                      startup=True, run_reports=False)
        # ...and the reports that were due take their own pass, under their own name. It reads
        # the sources again on the way in, which is cheap (~2 s) and catches whatever landed
        # while the backlog was being judged.
        _poll_reports(0, what='running the reports that were due', startup=True)
        # the Morning digest needs no call of its own anymore: it is a seeded REPORT, run by
        # the pass above like every other one. Consolidate what the verdicts taught next,
        # on the same once-a-day rhythm.
        try: learn.reflect_if_due(store)
        except Exception as e: logger.warning(f'reflection failed: {e}')
    t = threading.Thread(target=_catch_up, daemon=True)
    t.start()
    return t                       # the caller may wait on it; startup itself never does


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
    from .docsync import sync_connections, sync_projects
    from .projects import backfill
    try:
        sync_connections(store, 'startup')
        backfill(store)
        sync_projects(store, 'startup')
    except Exception as e: logger.warning(f'connection sync at startup failed: {e}')

@app.post('/api/ingest/poll')
def ingest_poll(background: BackgroundTasks):
    if _POLL_BUSY.locked(): return {'report': 'busy'}      # a pass is running; a second would be skipped anyway
    background.add_task(_poll_reports)
    return {'report': 'running'}

@app.get('/api/ingest/status')
def ingest_status():
    try: st = json.loads(store.get_settings().get('ingest_status') or '{"state": "idle"}')
    except ValueError: st = {'state': 'idle'}
    # a poll that died with the app leaves 'running' behind with nobody holding the lock - a
    # ghost the timeline banner would show forever (the poll sets the flag only AFTER taking
    # the lock, so running-but-unlocked is always a ghost). Heal it on read.
    if st.get('state') == 'running' and not (_POLL_BUSY.locked() or _quick_busy()):
        st = {'state': 'idle'}
        store.set_setting('ingest_status', json.dumps(st), 'system')
    # the cadence rides along so the timeline's caption can state the truth instead of a
    # hardcoded "every 10 min" that stayed on screen after somebody set the interval to 0
    try: every = int(store.get_settings().get('poll_minutes') or 0)
    except (TypeError, ValueError): every = 10
    try:
        fetched_at = float(store.get_settings().get('ingest_last_fetch_completed_at'))
        if not 0 < fetched_at < float('inf'): fetched_at = None
    except (TypeError, ValueError): fetched_at = None
    # and the clock itself: when the last full poll ran and when the next is due, so the caption
    # can count down instead of asserting a cadence nobody could check
    return {'status': st, 'everyMinutes': every, 'lastPollAt': _LAST_POLL[0],
            'lastFetchCompletedAt': fetched_at,
            # a source whose last read failed, so "checked 7:09" never covers for it (its card has the why)
            'failed': sorted({c['Type'] for c in store.list_connectors() if c.get('Active') and c.get('LastError')}),
            'nextPollAt': (_LAST_POLL[0] + every * 60) if every > 0 else None, 'now': time.time(),
            # the brain's last failure, until it answers again - shown in the caption, not buried in rows
            'triageError': store.get_settings().get('triage_last_error') or '',
            'timelineFade': store.get_settings().get('timeline_fade') or 'normal'}  # how old rows dim (FeedView)

# ── interactive terminals (real pty + websocket; the headless runs live on /api/runs) ──
# And one socket for the rest of the UI: Timeline/Board/Studio subscribe instead of polling.
@app.websocket('/api/events/ws')
async def events_ws(ws: WebSocket):
    """feed-changed, task-changed, run-tail. Same Host/Origin/token questions as the terminal
    socket: a websocket is exempt from the same-origin policy, so a page that learned the token
    used to subscribe from anywhere (audit 2026-09-16)."""
    if not _ws_ok(ws): return await ws.close(code=4401)
    await ws.accept()
    try:
        await live_bus.serve(ws)
    except (WebSocketDisconnect, RuntimeError):
        pass


class TermBody(BaseModel):
    agent: str | None = None; brain: str | None = None; task_id: int | None = None; repo: str | None = None
    cwd: str | None = None; rows: int = 0; cols: int = 0; seed: bool = False   # 0: open it where the owner watches (terminal.opening_geometry)
    model: str | None = None; instruction: str | None = None

@app.get('/api/terminals')
def terminals(details: bool = True):
    return {'data': [t for t in hub_term.listing(details=details)
                     if (store.get_task(t.get('taskId')) or {}).get('SourceRef') != 'assistant:dock']}

@app.get('/api/terminals/{sid}/screen')
def terminal_screen(sid: str, lines: int = 32):
    """Read-only live terminal preview. It never types into or resizes the PTY."""
    out = hub_term.screen(sid, lines)
    if not out: raise HTTPException(404, 'terminal not found')
    return out

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
    # It also used to slice the result to a flat 8000 characters - a second, silent cut on top of
    # seed_text's own (seed_text already bounds itself at SEED_CEILING and says so when it cuts).
    # One prompt builder, both doors: terminal.start_on_task (the dispatch door) never had this
    # slice, so raising DOC_CHARS made this door alone start chopping "Do NOT call the Taskuary
    # API" off the end, unmarked (test_start_session_seeds_the_same_full_prompt_as_dispatch,
    # 2026-09-17).
    seed_fn = ((lambda cwd: hub_term.seed_text(store, body.task_id, body.instruction, repo, cwd))
               if body.seed and body.agent and tk else None)
    # this is the owner's door (agents dispatch through terminal.start_on_task): a session opened
    # here is one they sit in, so the task is theirs to end - whichever dialog or button it came from
    from . import selfclose as _sc
    if tk: _sc.claim(store, body.task_id, ACTOR)
    try:
        t = hub_term.open_session(store, body.agent, body.task_id, repo, body.cwd, body.rows, body.cols,
                                  ACTOR, body.model, seed_fn=seed_fn, brain=body.brain)
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
    # A general session already persists every turn. Pausing it only has to close the live
    # provider session; its complete conversation is the handover when the owner resumes.
    from . import general
    task = store.get_task(tid) or {}
    assistant = general.session_for(tid) if general.handles(task) else None
    # ...and it is the handover whether or not a provider session is still live: an API turn keeps
    # none once it has answered, and this used to fall through and refuse (owner, 2026-09-07).
    if assistant or (general.handles(task) and general.chat_rows(store, tid)):
        history = general.history(store, tid)
        note = next((m['content'][0]['text'] for m in reversed(history)
                     if m.get('role') == 'assistant' and m.get('content')), '')
        if assistant: hub_term.close(assistant.sid)
        store.add_comment(tid, ACTOR, 'human', 'Paused the assistant session - the conversation is saved here for later.')
        store.audit('terminal', tid, 'pause', ACTOR,
                    detail={'sid': sid or getattr(assistant, 'sid', None), 'mode': 'assistant'})
        return {'pause': 'done', 'taskId': tid,
                'note': note or 'Conversation saved. Continue here when you are ready.'}
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
    session = hub_term.get(sid)
    if not session: raise HTTPException(404, 'terminal not found')
    # X ends the worker, not the task. A deliberate Done/Wrap takes the routes above; a plain
    # close must immediately put abandoned in-progress work back in front of the owner.
    tid = getattr(session, 'task_id', None)
    if tid:
        hub_term.release_task(store, tid, ACTOR,
                              'Closed the agent session. The task is open again - nobody is working it.')
        from . import funnel as _funnel
        _funnel.invalidate()
    if not hub_term.close(sid): raise HTTPException(404, 'terminal not found')
    return {'ok': True}

@app.post('/api/tasks/{task_id}/agent/stop')
def stop_task_agent(task_id: int):
    """End only the current worker. The task and reply are separate state machines."""
    task = store.get_task(task_id)
    if not task: raise HTTPException(404, 'task not found')
    _refresh_chat_context(task_id=task_id)
    live = hub_term.session_for(task_id)
    if not live or not getattr(live, 'alive', False):
        return {'stopped': False, 'taskStatus': task.get('Status')}
    sid = live.sid
    label = getattr(live, 'label', None) or getattr(live, 'agent', None) or 'agent'
    stopped = bool(hub_term.close(sid))
    if stopped:
        from . import workerstate as ws
        ws.record(store, task_id, sid, 'stopped', text='stopped by the owner', source='owner')   # never a completion (PW-222)
        # ...and the task is no longer being worked. Nothing moved it out of 'in_progress' and the
        # run row stayed 'running', so the pipe showed "agent working" on a task with no session and
        # nothing for the owner to do, for ever (the 2026-09-03 break test).
        for r in store.list_runs(task_id):
            if r.get('Status') == 'running': store.update_run(r['RunId'], {'Status': 'stopped'}, finished=True)
        if task.get('Status') == 'in_progress':
            store.update_task(task_id, {'Status': 'open'}, ACTOR)
        store.add_comment(task_id, ACTOR, 'human',
                          f'Stopped the {label} session. The task is open again - nobody is working it.'
                          if task.get('Status') == 'in_progress' else f'Stopped the {label} session. The task remains {task.get("Status")}.')
        store.audit('terminal', task_id, 'stop', ACTOR,
                    detail={'sid': sid, 'agent': getattr(live, 'agent', None),
                            'taskStatus': task.get('Status')})
    return {'stopped': stopped, 'taskStatus': (store.get_task(task_id) or {}).get('Status')}

def _ws_ok(ws: WebSocket) -> bool:
    """The HTTP middleware never runs for a websocket, so the same three questions are asked here.
    A browser cannot put a header on a websocket, so the token rides on the query string - but a
    caller that CAN set headers (the test client, a script) may send it that way. Origin matters
    most of all here: a websocket is exempt from the same-origin policy, so any page may open one
    to localhost, and this socket is a keyboard attached to a coding agent (audit 2026-09-02, F03).
    """
    if demo.enabled(): return True
    if not guard.host_ok(ws.headers.get('host'), cfg['server']): return False
    if not guard.origin_ok(ws.headers): return False
    tok = cfg['server'].get('token')
    return not tok or guard.token_matches(ws.query_params.get('token'), tok) \
        or guard.token_matches(ws.headers.get('x-taskuary-token'), tok)


# The pane fits itself to its box, so the pty grows after output exists. ConPTY keeps a grown
# viewport top-anchored (cursor on its old row, blank rows below) while xterm pulls scrollback
# in and moves the cursor down - the CLI's next cursor move then lands mid-pane. The pane fixes
# that with xterm's windowsPty option, but only if it knows which pty it is watching.
def geom_frame(t, owner):
    win = sys.platform == 'win32'
    return {'type': 'geom', 'rows': int(t.rows), 'cols': int(t.cols), 'owner': bool(owner), 'conpty': win,
            'build': sys.getwindowsversion().build if win else None}   # ConPTY reflows only from 21376; xterm follows the build

@app.websocket('/api/terminals/{sid}/ws')
async def terminal_ws(ws: WebSocket, sid: str):
    """Bytes out, keystrokes in. The HTTP token gate can't see websockets, so _ws_ok asks the
    same questions the middleware would have."""
    t = hub_term.get(sid)
    if not _ws_ok(ws): return await ws.close(code=4401)
    if not t: return await ws.close(code=4404)
    await ws.accept()
    q = asyncio.Queue()
    t.subscribe(asyncio.get_running_loop(), q)
    # The first pane on this session drives its geometry; the rest render at what it chose.
    # `q` is already a per-socket identity and is already dropped in `finally`, so it is the token.
    # Three duck-typed classes serve this socket - Term, GeneralSession and demo.Replay - and they
    # share no base, so the token is read tolerantly rather than declared on each of them.
    if getattr(t, 'geom_owner', None) is None: t.geom_owner = q
    owns_geometry = lambda: getattr(t, 'geom_owner', None) is q
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
        nonlocal delivered, inflight, redraw_quiet, redraw_cap
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
            try: await send_frame({'type': 'out', 'data': ''.join(chunks),
                                   # Devin accepts the argv prompt immediately but does not paint
                                   # it until its first model turn returns. Tell the pane the truth
                                   # during that otherwise blank-looking interval.
                                   'promptPending': hub_term.prompt_pending(t),
                                   'cli': hub_term.cli_of(t.argv)})
            finally: inflight -= 1
            delivered += len(chunks)
            # Ignore output that was already queued when the resize began. The first new chunk
            # and every repaint chunk after it move the quiet barrier; ready follows the burst.
            if redraw_boundary is not None and delivered >= redraw_boundary:
                # The cap is only a no-output fallback. Once repaint bytes arrive, quiet after
                # the LAST chunk is the barrier; a fixed cap exposed a long Codex redraw while it
                # was still painting line by line.
                if redraw_cap:
                    redraw_cap.cancel()
                    redraw_cap = None
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
        # RENDERED, not raw (terminal.replay_text): the raw bytes of a full-screen TUI replay as
        # debris in a fresh xterm, and the live repaint then appends to that debris. Flagged as a
        # REPLAY so the browser holds the curtain over it until the live screen is up.
        # A geometry change can repaint the screen. None of that is the agent doing anything, and
        # counting it as output reset idle(): a session parked on a dialog read as working again
        # every time its card was opened (2026-09-03).
        t.quiet_for(ATTACH_QUIET)
        # Say who owns the geometry BEFORE any output: a pane that is not the owner must render at
        # the pty's width rather than fit its own box, or it wraps where the child did not - which
        # is the same corruption by a different road.
        await send_frame(geom_frame(t, owns_geometry()))
        if t.scrollback():
            snap = hub_term.replay_text(t)
            if snap: await send_frame({'type': 'out', 'replay': True, 'data': snap,
                                      'promptPending': hub_term.prompt_pending(t),
                                      'cli': hub_term.cli_of(t.argv)})
        first_resize = True
        while True:
            m = await ws.receive_json()
            if m.get('type') == 'in': input_q.put_nowait(m.get('data') or '')
            elif m.get('type') == 'resize':
                rows, cols = m.get('rows') or 32, m.get('cols') or 110
                # A free token is claimed by whoever asks next: close the task page and the Wall
                # inherits the pty rather than being stuck at the size the task page left behind.
                if getattr(t, 'geom_owner', None) is None: t.geom_owner = q
                if not owns_geometry():
                    # Not ours to change. Tell this pane what the geometry actually is - and lift
                    # its curtain, which the owner's road does through the redraw barrier below.
                    await send_frame(geom_frame(t, False))
                    if first_resize:
                        first_resize = False
                        await send_frame({'type': 'ready'})
                    continue
                if first_resize:
                    first_resize = False
                    # The rendered snapshot already hydrates a same-size reconnect. The old
                    # one-column wiggle forced Codex/Claude to repaint their entire TUI on every
                    # task switch, even when the geometry had not changed; large sessions then
                    # visibly replayed from the top for minutes. Same size means no child resize
                    # at all: reveal the snapshot and resume only live output.
                    if (int(rows), int(cols)) == (int(t.rows), int(t.cols)):
                        await send_frame({'type': 'ready'})
                        continue
                    # For a real geometry change, request exactly one resize. The child repaints
                    # asynchronously, so output beyond this boundary is the new live screen.
                    redraw_boundary = delivered + inflight + q.qsize() + 1
                    redraw_cap = asyncio.create_task(finish_redraw(.35))
                elif (int(rows), int(cols)) == (int(t.rows), int(t.cols)):
                    continue
                t.resize(rows, cols)
                # ...and the next session opens at this size instead of being grown into it
                hub_term.remember_geometry(store, rows, cols)
    except (WebSocketDisconnect, RuntimeError, ValueError):
        pass
    finally:
        if owns_geometry(): t.geom_owner = None        # the next pane to refit inherits the pty
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

class OpenUrlBody(BaseModel):
    url: str

@app.post('/api/terminals/{sid}/browser/open')
def terminal_browser_open(sid: str, body: OpenUrlBody):
    """Navigate the pane the owner is watching. Theirs to drive: the agent is told to hand the
    keyboard over for a password or a 2FA code, and until now there was nowhere to hand it to."""
    from . import browserview
    try: return {'url': browserview.navigate(sid, body.url)}
    except ValueError as e: raise HTTPException(422, str(e))

class ViewportBody(BaseModel):
    w: int
    h: int

@app.post('/api/terminals/{sid}/browser/viewport')
def terminal_browser_viewport(sid: str, body: ViewportBody):
    """The pane says what shape it is; the page is rendered that shape, so there is no letterbox."""
    from . import browserview
    return {'set': browserview.set_viewport(sid, body.w, body.h)}

@app.websocket('/api/terminals/{sid}/browser/ws')
async def terminal_browser_ws(ws: WebSocket, sid: str):
    """agent-browser's screencast, relayed: frames out, the owner's input back when they take over.
    Same rule as the terminal socket."""
    from . import browserview
    if not _ws_ok(ws): return await ws.close(code=4401)
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
    # `version` is the process; `disk_version` is pyproject.toml right now. They part company the
    # moment a pull bumps the number under a running server - and until the owner restarts, the
    # header pill, /api/version and the CLI banner all report the old one. The page says so.
    from . import _version
    try:
        html = (_web_root / 'index.html').read_text(encoding='utf-8')
        return {'asset': (re.search(r'assets/(index-[A-Za-z0-9_-]+\.js)', html) or [None, ''])[1],
                'version': _ver, 'disk_version': _version()}
    except OSError:
        return {'asset': '', 'version': _ver, 'disk_version': _version()}

@app.get('/api/connectors/catalog')
def connectors_catalog():
    """Every card, working or planned, from the one catalogue file both the tab and the report read."""
    from . import connectorcatalog
    return {'data': connectorcatalog.cards()}


@app.get('/api/assistant/blocks')
def assistant_blocks(source_id: int = None, blocks: str = None, taskuary: str = None):
    """What an Assistant report reads, priced. `source_id` names the report whose choice to resolve;
    absent means the declared defaults, which is what a new report starts from. `blocks` is the
    choice the owner is making RIGHT NOW, as JSON, before they have saved it - without it the card
    would price the saved report while showing the edited one, which is the kind of disagreement
    between a page and its data this whole feature exists to end.

    One resolution feeds both this and the run (assistantblocks.resolve), so the card cannot claim a
    read the payload never made. `cost` stays None until the brain's price is known - the money line
    is Task 3's, and a field that exists and says nothing beats a number that is a guess."""
    from . import assistantblocks as blk
    from .reports import runs_per_day
    cfg = {}
    if source_id:
        src = store.get_source(int(source_id))
        # a card that asks about a report that is not there must not be answered with the DEFAULTS:
        # it would show a confident picture of a configuration nobody saved
        if not src: raise HTTPException(404, f'no source {source_id}')
        try: cfg = json.loads(src.get('ConfigJson') or '{}')
        except ValueError: cfg = {}
        if cfg.get('type') != 'assistant': raise HTTPException(404, f"source {source_id} is a {cfg.get('type') or 'rest'} report, not an Assistant")
    if blocks is not None:
        # the unsaved choice wins over the saved one. A malformed string is the owner's editor
        # mid-keystroke, not an attack: price the saved report rather than 400 at them.
        try: cfg = {**cfg, 'blocks': json.loads(blocks)}
        except ValueError: logger.debug('assistant blocks: the page sent a blocks value that is not JSON; pricing what is saved')
    if taskuary is not None:
        # the cards the owner is drawing RIGHT NOW (the page since 2026-09-20) - same rule as `blocks`
        try: cfg = {**cfg, blk.KEY: json.loads(taskuary)}
        except ValueError: logger.debug('assistant blocks: the page sent a taskuary value that is not JSON; pricing what is saved')
    chosen = blk.resolve(store, cfg)
    rows = blk.weighed(store, chosen, report_id=int(source_id) if source_id else None)
    # the live blocks are ON and cost nothing HERE, which is not the same as costing nothing. Named
    # so the card can say "and a live call to your calendar" instead of printing a total that reads
    # as zero for exactly the report that costs the most.
    unpriced = [{'id': r['id'], 'label': r['label']} for r in rows if r['on'] and r['live']]
    return {'data': rows, 'cards': blk.price_cards(rows, chosen), 'total_tokens': sum(r['tokens'] for r in rows if r['on']),
            'runs_per_day': runs_per_day(cfg), 'cost': None, 'unpriced': unpriced,
            'reads_taskuary': blk.reads_taskuary(chosen)}


@app.get('/api/audit/assistant')
def audit_assistant(limit: int = 60):
    """What the assistant changed, newest first - the rows its handlers audit as `assistant` (settings,
    reports, connections). Settings -> Configuration shows them, with the undo beside the newest while
    it still applies (the tiers: an instant write is always visible and always reversible)."""
    rows = [r for r in store.list_audit(limit=max(limit * 5, 200)) if r.get('Actor') == 'assistant'][:limit]
    out = []
    for r in rows:
        try: d = json.loads(r.get('Detail') or '{}') if str(r.get('Detail') or '').startswith('{') else {'detail': r.get('Detail')}
        except ValueError: d = {'detail': r.get('Detail')}
        out.append({'when': r.get('CreatedAt'), 'entity': r.get('EntityType'), 'id': r.get('EntityId'), 'action': r.get('Action'), 'detail': d})
    undo = str(store.get_settings().get('assistant_last_undo') or '')
    op = operations.get(store, undo) if undo else None
    return {'data': out, 'undo': ({'id': op['id'], 'version': op['version'], 'label': 'Undo the last change'} if op and op.get('status') == 'proposed' else None)}


@app.get('/api/settings')
def settings():
    """Every knob, with the value it SHIPS with beside the value it has.

    "Explain them better" starts with the one fact no description contained: what this was before
    you touched it (the owner, 2026-09-16). Writing that into 55 description strings would be 55
    places to drift out of step with store.DEFAULT_SETTINGS; the page reads it from the same dict
    the install was seeded from, so it cannot disagree with what actually shipped."""
    from .store import DEFAULT_SETTINGS
    # `assistant_notes*` is a check's private memory of its own last run, one key per report
    # (assistant.notes_key) - bookkeeping, not a knob, however many reports there are
    rows = [s for s in store.list_settings() if s['Name'] not in ('ingest_status', 'assistant_last_run', 'pane_geometry')
            and not s['Name'].startswith('report_last_run:') and not s['Name'].startswith('assistant_notes')]
    return {'data': [{**r, 'Default': DEFAULT_SETTINGS.get(r['Name'])} for r in rows]}

@app.patch('/api/settings')
def set_setting(body: SettingBody):
    store.set_setting(body.name, body.value, ACTOR)
    return {'ok': True}

@app.get('/api/assistant/doorways')
def assistant_doorways():
    """Where the assistant can be reached, per channel - for Settings -> Assistant on your phone."""
    from . import remote_assistant
    return {'data': remote_assistant.doorway_state(store),
            'standing': store.get_settings().get('phone_assistant') == '1'}

class DoorwayBody(BaseModel):
    channel: str
    chat: str = ''

class ListensBody(BaseModel):
    channel: str
    listens: str

@app.post('/api/assistant/doorways')
def set_assistant_doorway(body: DoorwayBody):
    """Give the assistant a chat on that channel, or '' to take it back."""
    from . import remote_assistant
    try: return remote_assistant.use_chat(store, body.channel, body.chat)
    except ValueError as e: raise HTTPException(422, str(e))

@app.post('/api/assistant/doorways/listens')
def set_assistant_listens(body: ListensBody):
    """When that channel may listen: any time, or only while a walk is handed to it."""
    from . import remote_assistant
    try: return remote_assistant.set_listens(store, body.channel, body.listens)
    except ValueError as e: raise HTTPException(422, str(e))

@app.get('/api/ai/defaults')
def ai_defaults():
    """The three AI defaults with the model each will ACTUALLY run, and which screen owns it."""
    from . import aidefaults
    return aidefaults.state(store, cfg)


class AiDefaultBody(BaseModel):
    slot: str
    value: str = None                   # None = leave the brain/agent alone, only touch the model
    model: str = None                   # None = leave alone; '' = clear back to the provider default
    effort: str = None


@app.post('/api/ai/defaults')
def set_ai_default(body: AiDefaultBody):
    from . import aidefaults
    try: return aidefaults.apply(store, cfg, body.slot, body.value, body.model, body.effort, ACTOR)
    except ValueError as e: raise HTTPException(422, str(e))


@app.get('/api/audit/verify')
def verify(): return store.verify_audit_chain()
