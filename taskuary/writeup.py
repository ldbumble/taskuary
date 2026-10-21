"""THE WRITE-UP RUNS BEHIND THE PRESS (the owner, 2026-10-20). Mark done on a task with a live agent, Close agent on the Wall and
Stop and save all end a session the same way - its transcript becomes the report, the handbook and the playbook are asked, and
for a close the task closes - and that took as long as the AI did, 18 s with the page held under "Writing up this session".

Now the press starts ONE job the server owns and returns at once. The job harvests the session first - the transcript and the
agent's last word, before anything may close the pty - saves that harvest, then runs the same ending (wrapup.wrap) and, for a
close, the same close every surface takes (the task.complete operation). It survives the page going away. A close pressed
anywhere while a job runs for its task waits here for the job (wait_for) - it never ends the session before it is harvested.
A job cut short by a restart is finished from its saved harvest at startup (resume). A write-up that fails still closes when
the press was a close, and says why on the task.

WHAT IT IS DOING NOW IS SAID (the owner, 2026-10-21: "open the Close out right away and show the reply is being created"): the job
names its stage as it reaches it - reading the session, writing the report, drafting the reply - and the task page's Close out
draws that, from here, until the draft replaces it. state() is what the task's detail carries; every stage is a task-changed."""
import json, os, threading, time, uuid
from loguru import logger

PREFIX = 'writeup_job:'                 # setting name per task: the job's record, until it is done
FAILED = 'The write-up of this session did not finish'
_JOBS: dict = {}                        # task id -> threading.Event, set when that task's job is done
_LOCK = threading.Lock()
_HERE = threading.local()               # set on a job's own thread: its own close must not wait for itself
_STATE: dict = {}                       # task id -> {job, stage, running, error, close}: the last job's stage, kept once it ends
# the stages, in the order the job reaches them (wrapup.wrap names each); a job that ends is `done` or `failed`
STAGES = ('reading', 'report', 'reply', 'learning', 'closing')


def in_job() -> bool: return bool(getattr(_HERE, 'on', False))


def state(tid):
    "The task's write-up as the page draws it - {job, stage, running, error, close} - or None when none ran in this process."
    with _LOCK: st = _STATE.get(int(tid))
    return dict(st) if st else None


def _set(tid, job, **kw):
    with _LOCK:
        st = _STATE.get(int(tid))
        if st is None or st.get('job') != job: return
        st.update(kw)
    try:
        from . import live; live.emit(live.TASK, taskId=int(tid))
    except Exception: pass


def stage(tid, name: str) -> None:
    "The job writing this task up has reached `name` (STAGES). Said only from the job's own thread - a wrap outside one says nothing."
    if getattr(_HERE, 'tid', None) != int(tid) or not getattr(_HERE, 'job', None): return
    _set(tid, _HERE.job, stage=name)


def _begin(tid, stage_: str, close: bool) -> str:
    job = uuid.uuid4().hex[:12]
    with _LOCK: _STATE[int(tid)] = {'job': job, 'stage': stage_, 'running': True, 'error': '', 'close': bool(close)}
    return job


def running(tid) -> bool:
    with _LOCK: e = _JOBS.get(int(tid))
    return e is not None and not e.is_set()


def wait_for(tid, timeout: float = 600) -> bool:
    """Block until the write-up running for this task is done (True), or there is none. A close waits here."""
    with _LOCK: e = _JOBS.get(int(tid))
    return e.wait(timeout) if e is not None else True


def _folder(store):
    from . import config
    d = os.path.join(str(config.home()), 'writeups'); os.makedirs(d, exist_ok=True)
    return d


def _save(store, tid, record: dict, harvest: dict | None = None):
    """The job's record, and once harvested the harvest itself - on disk BEFORE any AI is asked."""
    if harvest is not None:
        path = os.path.join(_folder(store), f'{int(tid)}-{int(time.time() * 1000)}.json')
        with open(path, 'w', encoding='utf-8') as f: json.dump(harvest, f, ensure_ascii=False)
        record = {**record, 'harvest': path}
    store.set_setting(PREFIX + str(int(tid)), json.dumps(record), record.get('actor') or 'owner')
    return record


def start(store, tid: int, *, close: bool, actor: str = 'owner', no_reply: bool = False, sid: str = None) -> dict:
    """Start the write-up of this task's session; return at once. A second press while one runs joins it."""
    from . import wrapup
    tid = int(tid)
    if not store.get_task(tid): raise ValueError('this session is not on a task')
    with _LOCK:
        if tid in _JOBS and not _JOBS[tid].is_set():
            return {'wrap': 'started', 'taskId': tid, 'already': True, 'job': (_STATE.get(tid) or {}).get('job')}
        done = _JOBS[tid] = threading.Event()
    job = _begin(tid, 'reading', close)
    record = _save(store, tid, {'close': bool(close), 'actor': actor, 'no_reply': bool(no_reply), 'sid': sid})
    harvested = threading.Event()
    def run():
        try: _run(store, tid, record, harvest_done=harvested, job=job)
        finally:
            harvested.set(); done.set()
    threading.Thread(target=run, name=f'writeup-{tid}', daemon=True).start()
    harvested.wait(30)                  # the press returns once the session is harvested and saved - seconds before any AI answers
    return {'wrap': 'started', 'taskId': tid, 'job': job}


def _run(store, tid, record, harvested: dict = None, harvest_done=None, job: str = None):
    from . import wrapup, live
    close, actor = record.get('close'), record.get('actor') or 'owner'
    failed = ''
    _HERE.on, _HERE.tid, _HERE.job = True, int(tid), job
    def saved(h):
        _save(store, tid, record, h)
        if harvest_done: harvest_done.set()
    try:
        wrapup.wrap(store, tid, close=False, actor=actor, sid=record.get('sid'), no_reply=bool(record.get('no_reply')),
                    harvested=harvested, on_harvest=saved)
    except Exception as e:
        failed = str(e) or type(e).__name__
        logger.warning(f'write-up of task {tid} failed: {failed}')
    finally:
        if harvest_done: harvest_done.set()
    try:
        if close: stage(tid, 'closing'); _close(store, tid, actor, failed)
        elif failed: store.add_comment(tid, actor, 'human', f'{FAILED}: {failed}')
    finally:
        store.set_setting(PREFIX + str(int(tid)), '', actor)
        if job: _set(tid, job, running=False, stage='failed' if failed else 'done', error=failed)
        _HERE.tid = _HERE.job = None
        try: live.emit(live.TASK, taskId=tid)        # the page that left the task, or stayed on it, reads it again
        except Exception: pass


def _close(store, tid, actor, failed):
    """The close every surface takes (the task.complete operation), and the failure said on the closed task."""
    from . import operations, server
    from fastapi import BackgroundTasks
    task = store.get_task(tid) or {}
    if task.get('Status') not in ('done', 'dropped'):
        # the press's own road (taskOps.runOperation): propose, then the execute route - its table check and its receipt included
        op = operations.propose(store, 'task.complete', tid, {}, actor)
        server.execute_operation(op['id'], server.OperationConfirm(version=op['version']), BackgroundTasks())
    if failed: store.add_comment(tid, actor, 'human', f'{FAILED}: {failed}')


def resume(store) -> int:
    """At startup: every job a restart cut short is finished from its saved harvest - or, harvested never, noted and (for a close)
    closed, since the session it would have read is gone."""
    n = 0
    for name, value in (store.settings_like(PREFIX) if hasattr(store, 'settings_like') else _settings_like(store)):
        if not value: continue
        try: record, tid = json.loads(value), int(name[len(PREFIX):])
        except (ValueError, TypeError): continue
        harvest = None
        if record.get('harvest'):
            try:
                with open(record['harvest'], encoding='utf-8') as f: harvest = json.load(f)
            except OSError: harvest = None
        with _LOCK: done = _JOBS[tid] = threading.Event()
        job = _begin(tid, 'report' if harvest else 'closing', record.get('close'))
        def run(tid=tid, record=record, harvest=harvest, done=done, job=job):
            try:
                if harvest: _run(store, tid, record, harvested=harvest, job=job)
                else:
                    _HERE.on = True
                    actor = record.get('actor') or 'owner'
                    why = 'Taskuary restarted before the session was read'
                    if record.get('close'): _close(store, tid, actor, why)
                    else: store.add_comment(tid, actor, 'human', f'{FAILED}: {why}')
                    store.set_setting(PREFIX + str(tid), '', actor)
                    _set(tid, job, running=False, stage='failed', error=why)
            finally: done.set()
        threading.Thread(target=run, name=f'writeup-resume-{tid}', daemon=True).start(); n += 1
    return n


def _settings_like(store):
    try: return [(r[0], r[1]) for r in store.cx.execute('SELECT Name, Value FROM setting WHERE Name LIKE ?', (PREFIX + '%',))]
    except Exception: return []
