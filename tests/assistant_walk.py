"""THE DESK ASSISTANT, WALKED THROUGH ON A CLI BRAIN - the owner, 2026-10-20: "even using the Claude CLI backend (headless) it should
respond to things quickly, especially if it's just 'bring up this task', 'respond to this task', 'rerun the agent with these notes'
... I need a full walk-through of that as testing."

One realistic session against the demo world, through the REAL brain road - concierge.brain -> llm.make_cli_llm -> agents.run_cli ->
clipool -> a live process - with tests/fake_claude.py standing in for `claude -p`: its stream-json protocol, its start-up cost, its
time to first token and its token rate. What it answers is the step's script (what a good model says to those words); what is graded
is what Taskuary DOES with that answer, what the line says, and how long each took:
  first word - the first of the answer's words the page could draw (a `words` event, else the answer itself)
  action     - the answer with its act: the button lit, the page opened, the draft started, the rows cleared
`python -m tests.assistant_walk` prints the table (FAKE_CLAUDE_* env vars change the timings); `--real` runs the same steps on the
installed claude instead - see real_cli_safe() for what has to hold first. tests/test_assistant_walk.py holds every step in CI."""
import json, os, re, sys, tempfile, threading, time
from contextlib import ExitStack
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
FAKE = os.path.join(HERE, 'fake_claude.py')


def c(_kind, **params): return 'CALL: ' + json.dumps({'kind': _kind, 'params': params})


class Step:
    """One thing the owner types. `table`: the pile key on screen when it is typed (None: nothing). `first`/`then`: the scripted
    model's answer, and its answer after a look-up. `expect`: the outcome (tests/assistant_queries.py's words: link:<href> |
    draft:<verb> | light:<verb> | read:<tool> | cleared). `says`: a regex the line the owner reads must match - it says what it did; a lit button says nothing (2026-10-23).
    `budget`: (first word, action) in seconds on the fake's realistic timings."""
    def __init__(self, text, table, first, expect, says, then=None, budget=(1.5, 3.0), live=None):
        self.text, self.table, self.first, self.then, self.expect, self.says, self.budget, self.live = text, table, first, then, expect, says, budget, live


STEPS = [
    Step('bring up TQ-12', None, 'Here: [TQ-0012](#task=12).', 'link:#task=12', r'TQ-0*12'),
    Step("respond to this - say we'll have it Friday", 'msg:17', "I'll draft it.\n" + c('reply', text="We'll have it Friday."), 'draft:reply', r'draft|Draft'),
    # TQ-12's coding agent ran before and its session is saved (world()): Continue reopens it, the notes riding along
    Step('rerun the agent with these notes: use the new template', 'msg:17',
         'Sending it back to work with your notes.\n' + c('agent.continue', ref='TQ-0012', note='use the new template'), 'light:continue',
         r'^$'),                                                  # the lit Continue is the whole answer (2026-10-23)
    Step("what's waiting on me", None, c('pipe.list'), 'read:pipe.list', r'month-end',
         # a question that needs a look-up is two model rounds, and its first words are the second round's
         then='Ten things are on you - the month-end close is short by 4,180 and leads the list.', budget=(2.0, 3.0)),
    Step('mark the FYI read', 'msg:5', 'Clearing the FYIs.\n' + c('pipe.clear', select={'kind': 'fyi'}), 'cleared', r'^Marked (all )?\d+ (items?|FYI|reports?) read'),   # "all": past the table's handful (58740414)
    Step('open Settings → Sounds', None, 'The sounds are under [Notifications](#settings=config&group=Notifications).', 'link:#settings', r'Notifications'),
    Step('add LinkedIn as a connector', None, 'Bringing up the LinkedIn card.\n' + c('connection.create', type='linkedin'), 'open:#connector=linkedin', r'LinkedIn'),
    Step('remind me tomorrow', 'msg:1', 'Putting it away until tomorrow.\n' + c('task.defer', until='tomorrow 9am'), 'light:defer', r'^$'),
    Step('stop the agent', 'agent:6', 'Stopping it.\n' + c('stop_agent'), 'light:stop_agent', r'^$', live=6),
]


def outcomes(out: dict, reads: list) -> list:
    o = []
    if (l := out.get('light')) is not None: o.append(f"light:{l.get('verb') or ''}")
    if out.get('open'): o.append(f"open:{out['open']}")
    if out.get('new'): o.append(f"new:{out['new'].get('kind')}")
    d = (out.get('decision') or {}).get('verb')
    if d == 'next': o.append('next')
    elif d in ('reply', 'redraft'): o.append(f'draft:{d}')
    elif d: o.append(f'decision:{d}')
    if out.get('cleared') is not None: o.append('cleared')
    if out.get('proposal'): o.append(f"proposal:{out['proposal'].get('kind')}")
    o += [f'read:{k}' for k in reads]
    o += [f'link:{h}' for h in re.findall(r'\]\((#[^)]+)\)', out.get('say') or '')]
    return o or ['words']


# the real CLI reads no user- or plugin-level settings: the owner's user-wide hooks POST to the live app, and must never fire from here
REAL_ARGS = ['--setting-sources', 'project,local', '--include-hook-events']
LIVE_PORT = ':7787'


BRIEF = 12      # words beside a component brought up (the owner, 2026-10-21: "free text should almost never be used in the assistant")


def words(say: str) -> int:
    """Words as the owner reads them: a markdown link counts as its label."""
    return len(re.sub(r'\[([^\]]*)\]\([^)]*\)', r'\1', say or '').split())


def brief(step, say: str) -> bool:
    """A turn that brings something up - a page, a card, a lit button, a draft, a cleared set - says it in a few words; only a
    question's answer (a look-up) may run longer."""
    return step.expect.startswith('read:') or words(say) <= BRIEF


def world(real: bool = False):
    from taskuary import demo, funnel, terminal
    from taskuary.store import MemoryStore
    funnel.invalidate(); funnel.forget_states(); funnel._SOURCES.update(at=0.0, by={})
    s = MemoryStore()
    with mock.patch.object(terminal, 'live_sessions', return_value=[]): demo.seed(s)
    for k in ('learn_enabled', 'auto_draft_enabled'): s.set_setting(k, '0', 't')
    args = ['-p', '--dangerously-skip-permissions', '--output-format', 'stream-json', '--verbose'] + (REAL_ARGS if real else [])
    s.upsert_agent('claude', 'general', 'cli', json.dumps({'cmd': 'claude', 'args': args}))
    s.set_setting('concierge_ai', 'cli:claude', 't')
    saved = s.resumable_session
    s.resumable_session = lambda tid: {'ExtId': 's12', 'Brain': 'claude'} if int(tid) == 12 else saved(tid)
    funnel.invalidate()
    return s


class Clock:
    """What one turn spent where: spawns, each model round (sent -> first event -> result), the words the page could draw."""
    def __init__(self, log): self.log, self.rounds, self.spawns, self.words, self.t0, self.hooks, self.pids = log, [], 0, None, 0.0, [], set()
    def start(self): self.rounds, self.spawns, self.words, self.t0 = [], 0, None, time.perf_counter()
    def at(self): return time.perf_counter() - self.t0


def _instrument(st, clock: Clock):
    from taskuary import clipool
    init, turn = clipool.Live.__init__, clipool.Live.turn
    def live_init(self, *a, **k):
        clock.spawns += 1; init(self, *a, **k); clock.pids.add(str(self.p.pid))
    def live_turn(self, prompt, on_event, *a, **k):
        r = {'sent': clock.at(), 'chars': len(prompt), 'first': None}
        def on(j):
            if r['first'] is None: r['first'] = clock.at()
            if j.get('subtype') == 'hook_started': clock.hooks.append(j.get('hook_name') or '?')
            on_event(j)
        try: return turn(self, prompt, on, *a, **k)
        finally: r['end'] = clock.at(); clock.rounds.append(r)
    st.enter_context(mock.patch.object(clipool.Live, '__init__', live_init))
    st.enter_context(mock.patch.object(clipool.Live, 'turn', live_turn))


def _guards(st, live_box):
    from taskuary import concierge, ingest, terminal
    st.enter_context(mock.patch.object(terminal, 'live_sessions', return_value=[]))
    st.enter_context(mock.patch.object(terminal, 'for_task', lambda tid, **k: {'sid': f's{tid}'} if live_box and int(tid) in live_box else None))
    st.enter_context(mock.patch.object(ingest, '_spawn'))
    st.enter_context(mock.patch.object(concierge, '_compose_llm', return_value=lambda *a, **k: '{"kind": "report", "why": "scripted"}'))


def _ready(log: str, n: int, wait: float):
    """Until the fake has logged `n` processes ready (its start-up spent), or `wait` seconds."""
    end = time.time() + wait
    while time.time() < end:
        try:
            with open(log, encoding='utf-8') as f:
                if sum('"ev": "ready"' in l for l in f) >= n: return
        except OSError: pass
        time.sleep(0.05)


def real_cli_safe() -> tuple:
    """(True, why) only when the installed claude can be run without the owner's user-level settings: it has --setting-sources, and
    a control run with it fires a hook from a PROJECT settings file and none of the user's (their hooks POST to the live app)."""
    import shutil, subprocess
    exe = shutil.which('claude')
    if not exe: return False, 'no claude on PATH'
    if '--setting-sources' not in subprocess.run([exe, '--help'], capture_output=True, text=True, encoding='utf-8').stdout:
        return False, 'this claude has no --setting-sources'
    d = tempfile.mkdtemp(prefix='tq-real-control-'); os.makedirs(os.path.join(d, '.claude'))
    with open(os.path.join(d, '.claude', 'settings.json'), 'w') as f:
        json.dump({'hooks': {'UserPromptSubmit': [{'hooks': [{'type': 'command', 'command': 'echo control>> control.txt'}]}]}}, f)
    env = {k: v for k, v in os.environ.items() if not k.startswith('TASKUARY_')}
    out = subprocess.run([exe, '-p', '--output-format', 'stream-json', '--verbose', '--tools', '', '--model', 'haiku'] + REAL_ARGS,
                         input='say ok', capture_output=True, text=True, encoding='utf-8', cwd=d, env=env, timeout=180).stdout
    fired = [json.loads(l).get('hook_name') for l in out.splitlines() if '"hook_started"' in l]
    if fired != ['UserPromptSubmit'] or not os.path.exists(os.path.join(d, 'control.txt')):
        return False, f'the control run fired {fired} - expected only the project UserPromptSubmit'
    return True, 'only the project hook fired under --setting-sources project,local; no user hook ran'


def _watch_live_port(clock: Clock, stop):
    """Every socket to the live app's port held by a process this walk started - there must be none."""
    import subprocess
    seen = []
    def go():
        while not stop.is_set():
            out = subprocess.run(['netstat', '-ano'], capture_output=True, text=True).stdout
            seen.extend(l for l in out.splitlines() if LIVE_PORT in l and l.split()[-1] in clock.pids)
            stop.wait(0.2)
    threading.Thread(target=go, daemon=True).start()
    return seen


def run(steps=STEPS, real: bool = False, warm: bool = True, quiet: bool = False, settle: float = 8.0) -> list:
    """Every step in order, in ONE chat (the kept conversation the desk has). Returns a row per step. `warm`: the page opening
    starts the CLI (concierge.warm) and the first ask comes once it is up; `settle` is how long that is given on the real CLI."""
    from taskuary import agents, clipool, concierge, general
    if quiet:
        from loguru import logger
        logger.remove()
    scratch = tempfile.mkdtemp(prefix='tq-walk-')
    script = os.path.join(scratch, 'script.json')
    with open(script, 'w', encoding='utf-8') as f:
        json.dump([{'when': '^' + re.escape(s.text) + '$', 'first': s.first, 'then': s.then or 'Ok.'} for s in steps], f)
    os.environ.update(FAKE_CLAUDE_SCRIPT=script, FAKE_CLAUDE_LOG=os.path.join(scratch, 'fake.log'))
    s, rows, live_box, clock = world(real), [], set(), Clock(os.path.join(scratch, 'fake.log'))
    stop, port = threading.Event(), []
    with ExitStack() as st:
        _guards(st, live_box)
        if not real: st.enter_context(mock.patch.object(agents, '_resolve_cmd', lambda name: [sys.executable, FAKE]))
        else:
            env = agents.spawn_env
            st.enter_context(mock.patch.object(agents, 'spawn_env', lambda *a, **k: {k_: v for k_, v in env(*a, **k).items() if not k_.startswith('TASKUARY_')}))
            port = _watch_live_port(clock, stop)
        _instrument(st, clock)
        reads = []
        real_read = concierge._read
        st.enter_context(mock.patch.object(concierge, '_read', lambda store, item, call: (reads.append(call['kind']), real_read(store, item, call))[1]))
        tid = general.dock_task(s, 'owner')[0]['TaskId']
        if warm and hasattr(concierge, 'warm'):
            # the page opened: the CLI starts, and the owner reads the page before typing - it is ready when they ask
            t = time.perf_counter(); concierge.warm(s, wait=True)
            if real: time.sleep(settle)
            else: _ready(clock.log, 1, 20)
            warmed = time.perf_counter() - t
        else: warmed = 0.0
        for step in steps:
            live_box.clear(); live_box.update({step.live} if step.live else set())
            reads.clear(); clock.start()
            def trace(kind, name, detail):
                if kind == 'words' and clock.words is None and str(detail or '').strip(): clock.words = clock.at()
            err = None
            try: out = concierge.say(s, step.text, key=step.table, trace=trace)
            except Exception as e: out, err = {'say': f'RAISED {type(e).__name__}: {e}'}, e
            action = clock.at()
            got = outcomes(out, list(reads))
            say = str(out.get('say') or '')
            ok = any(g.startswith(step.expect) for g in got) and err is None
            rows.append({'step': step, 'got': got, 'say': say, 'ok': ok, 'said_ok': bool(re.search(step.says, say)), 'brief': brief(step, say),
                         'first_word': clock.words if clock.words is not None else action, 'action': action,
                         'spawns': clock.spawns, 'rounds': list(clock.rounds),
                         'prompt_chars': sum(r['chars'] for r in clock.rounds),
                         'build': clock.rounds[0]['sent'] if clock.rounds else action})
        clipool.close(f'{concierge.LIVE_KEY}:')
        stop.set()
    for r in rows: r.update(warm=warmed, hooks=list(clock.hooks), live_port=list(port))
    return rows


def table(rows) -> str:
    out = [f"{'step':<56} {'outcome':<22} {'ok':<3} {'1st word':>8} {'action':>7} {'rounds':>6} {'spawn':>5} {'build':>6} {'model':>6} {'prompt':>7}"]
    for r in rows:
        s, model = r['step'], sum(x['end'] - x['sent'] for x in r['rounds'])
        within = r['first_word'] <= s.budget[0] and r['action'] <= s.budget[1]
        out.append(f"{s.text[:56]:<56} {','.join(r['got'])[:22]:<22} {'ok' if r['ok'] and r['said_ok'] else 'NO':<3} "
                   f"{r['first_word']:>7.2f}s {r['action']:>6.2f}s {len(r['rounds']):>6} {r['spawns']:>5} {r['build']:>5.2f}s {model:>5.2f}s "
                   f"{r['prompt_chars']:>7}{'' if within else '  OVER BUDGET'}")
        out.append(f"{'':<4}says: {r['say'][:110]!r}")
    return '\n'.join(out)


if __name__ == '__main__':
    real = '--real' in sys.argv
    if real:
        ok, why = real_cli_safe()
        print(f'real CLI safe: {ok} - {why}')
        if not ok: sys.exit(1)
    rows = run(real=real, warm='--cold' not in sys.argv, quiet=True)
    print(table(rows))
    print(f"warm-up at chat start: {rows[0]['warm']:.2f}s (off the owner's clock)")
    if real: print(f"hooks fired: {rows[0]['hooks'] or 'none'}; sockets to {LIVE_PORT} from the walk's CLI: {rows[0]['live_port'] or 'none'}")
