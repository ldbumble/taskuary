"""THE LOAD HARNESS'S SERVER HALF (load-burst.mjs; the owner, 2026-11-24: "does the thing groan under the weight?"). Installed by
fixture_server.py on a fresh fixture when TASKUARY_FIXTURE_LOAD=1. It changes nothing the app decides - it watches and hands mail in:

- every hold of the store's writer lock and every wait on it, with the holder's call site (store._TimedLock, wrapped)
- the event loop's lag (a 50 ms tick, how late it wakes) and the request thread pool's borrowed tokens
- every request's server time by route, and a one-second sampler: CPU, memory, threads, the triage backlog, agents working and queued
- mail handed in the way a poll hands it: stored under ingest.deferred(), then the one drain worker judges it (server._drain_worker)
- the stand-in CLI (tests/fake_claude.py) as `claude`, so triage and agents run on its timing and the scenario's words

Invented people only."""
import asyncio, ctypes, os, sys, threading, time
from collections import defaultdict
from pathlib import Path

FAKE = str(Path(__file__).resolve().parents[2] / 'tests' / 'fake_claude.py')
T0 = time.time()


def _rss() -> int:
    if os.name != 'nt':
        try: return int(open('/proc/self/statm').read().split()[1]) * os.sysconf('SC_PAGE_SIZE')
        except Exception: return 0
    class PMC(ctypes.Structure):
        _fields_ = [('cb', ctypes.c_ulong), ('PageFaultCount', ctypes.c_ulong)] + [(n, ctypes.c_size_t) for n in (
            'PeakWorkingSetSize', 'WorkingSetSize', 'QuotaPeakPagedPoolUsage', 'QuotaPagedPoolUsage', 'QuotaPeakNonPagedPoolUsage',
            'QuotaNonPagedPoolUsage', 'PagefileUsage', 'PeakPagefileUsage')]
    c = PMC(); c.cb = ctypes.sizeof(PMC)
    k, ps = ctypes.windll.kernel32, ctypes.windll.psapi
    k.GetCurrentProcess.restype = ctypes.c_void_p; ps.GetProcessMemoryInfo.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong]
    ps.GetProcessMemoryInfo(k.GetCurrentProcess(), ctypes.byref(c), c.cb)
    return c.WorkingSetSize


def install(app, store):
    from fastapi import Body, Request
    from taskuary import agents, ingest, store as store_mod

    # ── the stand-in CLI as `claude` (audit_scenarios does the same): every spawn runs python on fake_claude.py ──
    real_resolve = agents._resolve_cmd
    agents._resolve_cmd = lambda name: [sys.executable, FAKE] if os.path.basename(str(name)).lower().split('.')[0] == 'claude' else real_resolve(name)

    # ── the writer lock, watched ──
    holds, waits, LK = [], [], threading.Lock()
    # ...named past this file too, and two frames deep (the store's caller, and who called it), so a hold says whose work it was
    skip = (store_mod._HERE, store_mod._CTX, __file__)
    def site():
        f = sys._getframe(1)
        while f is not None and f.f_code.co_filename in skip: f = f.f_back
        if f is None: return '?'
        g = f.f_back
        here = f'{os.path.basename(f.f_code.co_filename)}:{f.f_lineno} {f.f_code.co_name}'
        return here + (f' < {os.path.basename(g.f_code.co_filename)}:{g.f_lineno} {g.f_code.co_name}' if g else '')
    store_mod._call_site = site
    TL = store_mod._TimedLock
    o_acq, o_rel = TL.acquire, TL.release
    def acquire(self, blocking=True, timeout=-1):
        t = time.perf_counter(); got = o_acq(self, blocking, timeout); w = time.perf_counter() - t
        if w > 0.05:
            with LK: waits.append((time.time() - T0, round(w, 3), site(), threading.current_thread().name))
        return got
    def release(self):
        held = time.perf_counter() - self._since if self._depth == 1 else 0.0
        site, who = self._site, self._who
        o_rel(self)
        if held > 0.05:
            with LK: holds.append((time.time() - T0, round(held, 3), site, who))
    TL.acquire, TL.release = acquire, release

    # ── every request's server time ──
    reqs = []
    import re
    norm = lambda p: re.sub(r'/\d+(?=/|$)', '/N', p)
    @app.middleware('http')
    async def timing(request: Request, call_next):
        t = time.perf_counter()
        resp = await call_next(request)
        if request.url.path.startswith('/api/') and not request.url.path.startswith('/api/fixture/load'):
            reqs.append((time.time() - T0, f'{request.method} {norm(request.url.path)}', round((time.perf_counter() - t) * 1000, 1)))
        return resp

    # ── every judged mail's own time, start to landed (ingest._judge_one: one row, one lane) - its overhead is this less the model's delay ──
    judged, o_judge = [], ingest._judge_one
    def judge_one(st, r, llm):
        t = time.perf_counter()
        try: return o_judge(st, r, llm)
        finally: judged.append((time.time() - T0, round((time.perf_counter() - t) * 1000, 1), r['MessageId'], threading.current_thread().name))
    ingest._judge_one = judge_one

    # ── the loop and the pool, and the one-second sampler ──
    lag, samples = [], []
    loop_state = {'on': False}
    async def ticker():
        import anyio.to_thread
        while True:
            t = time.perf_counter(); await asyncio.sleep(0.05); late = (time.perf_counter() - t - 0.05) * 1000
            try: lim = anyio.to_thread.current_default_thread_limiter(); pool = (lim.borrowed_tokens, lim.total_tokens)
            except Exception: pool = (None, None)
            lag.append((time.time() - T0, round(late, 1), *pool))
            if len(lag) > 200_000: del lag[:100_000]

    def sampler():
        from taskuary import blackboard as bb, terminal
        last_cpu, last_t = sum(os.times()[:2]), time.time()
        while True:
            time.sleep(1.0)
            try:
                now, cpu = time.time(), sum(os.times()[:2])
                t0 = time.perf_counter()
                pend = len(store.pending_triage(ingest._ALL))
                q = (store._one('SELECT COUNT(*) n FROM dispatchq') or {}).get('n')
                read_ms = round((time.perf_counter() - t0) * 1000, 1)
                live = bb.live_count(); sess = len([t for t in list(terminal.SESSIONS.values()) if getattr(t, 'alive', False)])
                samples.append({'t': round(now - T0, 1), 'cpu': round(100 * (cpu - last_cpu) / max(1e-6, now - last_t), 1), 'rss_mb': round(_rss() / 2**20, 1),
                                'threads': threading.active_count(), 'triage_backlog': pend, 'queued_agents': q, 'working_agents': live, 'sessions': sess,
                                'sampler_read_ms': read_ms})
                last_cpu, last_t = cpu, now
            except Exception as e:
                samples.append({'t': round(time.time() - T0, 1), 'error': str(e)[:200]})
    threading.Thread(target=sampler, name='load-sampler', daemon=True).start()

    @app.post('/api/fixture/load/start')
    async def load_start():
        if not loop_state['on']: loop_state['on'] = True; asyncio.get_running_loop().create_task(ticker())
        return {'ok': True, 't': time.time() - T0}

    @app.get('/api/fixture/load/stats')
    async def load_stats(since: float = 0.0):
        f = lambda xs: [x for x in list(xs) if x[0] >= since]
        return {'now': time.time() - T0, 'holds': f(holds), 'waits': f(waits), 'lag': f(lag), 'reqs': f(reqs), 'judged': f(judged),
                'samples': [s for s in list(samples) if s['t'] >= since]}

    # ── mail handed in as a poll hands it ──
    @app.post('/api/fixture/load/arrive')
    def load_arrive(body: dict = Body(...)):
        """{messages: [msg]}: each stored under deferred() as poll_channels stores it (the page shows it 'triaging' at once), then the one
        drain worker judges the backlog - the same two steps server's full lane takes. Returns at once with when they were stored."""
        from taskuary import server
        msgs = body.get('messages') or []
        t = time.perf_counter(); out = []
        with ingest.deferred():
            for m in msgs: out.append((ingest.ingest_message(store, dict(m)) or {}).get('message_id'))
        stored = round((time.perf_counter() - t) * 1000, 1)
        server._drain_worker(store).submit()
        return {'mids': out, 'stored_ms': stored}

    @app.post('/api/fixture/load/outcomes')
    def load_outcomes(body: dict = Body(...)):
        """{externals: [id]} -> where each mail ended: its row's status and task, the task's status, kind and assignee, and the route's action."""
        res = {}
        for ext in body.get('externals') or []:
            m = store._one('SELECT MessageId, TaskId, Status FROM message WHERE ExternalId=?', (ext,))
            if not m: res[ext] = None; continue
            t = store.get_task(m['TaskId']) if m.get('TaskId') else None
            r = store._one('SELECT Decision, Reason, RawOutput, ParseError FROM route WHERE MessageId=? ORDER BY RouteId DESC LIMIT 1', (m['MessageId'],))
            res[ext] = {'mid': m['MessageId'], 'status': m['Status'], 'task': m.get('TaskId'), 'taskStatus': (t or {}).get('Status'),
                        'kind': (t or {}).get('Kind'), 'assignee': (t or {}).get('Assignee'), 'route': r}
        q = store._rows('SELECT TaskId, Reason, CreatedAt FROM dispatchq')
        # every task the burst made: what its chat says about its agent (queued, started), and its runs - a queued start that never ran is a dead end
        tasks = {}
        for tid in {v['task'] for v in res.values() if v and v.get('task')}:
            cs = [c.get('Body') or '' for c in store.list_comments(tid) if c.get('Actor') in ('router', 'system', 'agent')]
            tasks[tid] = {'queuedSaid': sum('Waiting its turn' in c for c in cs), 'startedSaid': sum('started' in c.lower() for c in cs),
                          'runs': (store._one('SELECT COUNT(*) n FROM run WHERE TaskId=?', (tid,)) or {}).get('n'),
                          'transcripts': (store._one('SELECT COUNT(*) n FROM transcript WHERE TaskId=?', (tid,)) or {}).get('n'),
                          'status': (store.get_task(tid) or {}).get('Status'), 'last': cs[-1][:160] if cs else ''}
        return {'out': res, 'dispatchq': q, 'tasks': tasks}

    @app.post('/api/fixture/load/big')
    def load_big(body: dict = Body(...)):
        """A task with `lines` chat lines from three people and the owner (big_chat's shape, any size), its route rows too."""
        from datetime import datetime, timedelta
        n = int(body.get('lines') or 2000)
        tid = store.create_task({'Title': f'Site ops: the cold room ({n} lines)', 'Kind': 'reply', 'Status': 'open', 'Source': 'whatsapp',
                                 'Summary': 'The site team wants the cold room fixed.'}, 'router')
        start, who = datetime.now() - timedelta(days=3), ('Ray Colton', 'Gail Moreno', 'Paula Vance', 'Alex Doyle')
        for j in range(n):
            w = who[j % 4]; mine = w == 'Alex Doyle'
            mid = store.add_message({'TaskId': tid, 'Channel': 'whatsapp', 'SourceName': 'Site ops', 'ExternalId': f'load-big-{tid}-{j}', 'ConversationId': f'load-big-{tid}',
                                     'FromName': w, 'BodyText': f'Cold room note {j + 1}: ' + ('the compressor is loud again' if j % 2 else 'engineer booked for Thursday'),
                                     'SentAt': (start + timedelta(minutes=j)).isoformat(' ', 'seconds'), 'Status': 'context' if mine else 'routed'})
            store.add_route(mid, tid, 'create' if j == 0 else 'attach', None, 'same chat', [], 'triage', verdict={'intent': 'reply_only', 'summary': 'the cold room'})
        store.reconcile_processing_membership()
        return {'taskId': tid}
