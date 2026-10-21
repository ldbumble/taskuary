"""A stand-in for headless `claude -p` that speaks its real I/O and keeps its timing profile, for repeatable latency numbers
(tests/assistant_walk.py). Never a network call, never a file outside FAKE_CLAUDE_LOG.

What it reproduces of Claude Code 2.x in `-p --output-format stream-json --verbose` mode:
  - `--input-format stream-json`: one process, one JSON `user` line per turn on stdin, a `result` event closing each turn
  - without it: the prompt is all of stdin, one turn, then exit (the per-call road)
  - `system`/`init` before the first turn's answer, `assistant` with the whole message, `result` with session_id
  - `--include-partial-messages`: `stream_event` content_block_delta text chunks as the words are written
  - `--resume <id>` keeps that session id; `--system-prompt-file` is read (its size counts toward the first turn)
Timing (seconds, env, defaults measured against claude 2.1 on the owner's machine - 4.2 s a cold turn, ~1.1 s warm):
  FAKE_CLAUDE_SPAWN  start-up before the process reads stdin (node, settings, auth)       2.5
  FAKE_CLAUDE_THINK  time to first token on a warm process, before any input is counted   0.7
  FAKE_CLAUDE_PREFILL per 10K characters of input the provider has not seen in this session 0.25
  FAKE_CLAUDE_TPS    output tokens a second (a token ~4 characters)                        70
What it SAYS comes from FAKE_CLAUDE_SCRIPT, a JSON list of {"when": regex, "first": text, "then": text}: the owner's words are
found where the Assistant puts them ("The owner says: " on a first round, "The owner asked: " on a look-up's second round), the
first rule whose regex matches answers - `first` on a first round, `then` once it has looked something up. No rule: "Ok."
FAKE_CLAUDE_LOG, when set, gets one JSON line per event ({pid, ev, t, ...}) for the latency breakdown."""
import json, os, re, sys, time

T0 = time.time()
args = sys.argv[1:]
def arg(k): return args[args.index(k) + 1] if k in args and args.index(k) + 1 < len(args) else None
def env(k, d): return float(os.environ.get(k) or d)
if '--help' in args:                     # an older claude has no --setting-sources: FAKE_CLAUDE_OLD=1
    print('Usage: claude [options]\n  -p, --print\n' + ('' if os.environ.get('FAKE_CLAUDE_OLD') else '  --setting-sources <sources>\n')); sys.exit(0)
SPAWN, THINK, PREFILL, TPS = env('FAKE_CLAUDE_SPAWN', 2.5), env('FAKE_CLAUDE_THINK', 0.7), env('FAKE_CLAUDE_PREFILL', 0.25), env('FAKE_CLAUDE_TPS', 70)
LIVE, PARTIAL = 'stream-json' in (arg('--input-format') or ''), '--include-partial-messages' in args
sid = arg('--resume') or f'fake-{os.getpid()}-{int(T0 * 1000) % 100000}'
system = open(arg('--system-prompt-file'), encoding='utf-8').read() if arg('--system-prompt-file') else ''
script = json.load(open(os.environ['FAKE_CLAUDE_SCRIPT'], encoding='utf-8')) if os.environ.get('FAKE_CLAUDE_SCRIPT') else []


def log(ev, **kw):
    if not os.environ.get('FAKE_CLAUDE_LOG'): return
    with open(os.environ['FAKE_CLAUDE_LOG'], 'a', encoding='utf-8') as f: f.write(json.dumps({'pid': os.getpid(), 'ev': ev, 't': time.time(), **kw}) + '\n')


def out(j): sys.stdout.write(json.dumps(j) + '\n'); sys.stdout.flush()


def answer(prompt: str) -> str:
    then = 'You looked up ' in prompt or 'You asked Taskuary for ' in prompt
    m = re.search(r'^The owner (?:says|asked): (.*)$', prompt, re.M)
    said = m.group(1).strip() if m else prompt.strip().splitlines()[-1] if prompt.strip() else ''
    for r in script:
        if re.search(r['when'], said, re.I): return r.get('then' if then else 'first') or r.get('first') or 'Ok.'
    return 'Ok.'


def turn(prompt: str, n: int):
    t = time.time()
    log('turn', chars=len(prompt), n=n)
    if n == 1: out({'type': 'system', 'subtype': 'init', 'session_id': sid, 'model': arg('--model') or 'default', 'tools': []})
    unseen = len(prompt) + (len(system) if n == 1 else 0)
    time.sleep(THINK + PREFILL * unseen / 10_000)
    text = answer(prompt)
    log('first_token', n=n)
    chunks = re.findall(r'.{1,4}', text, re.S) or ['']
    start = time.time()
    for i, c in enumerate(chunks):
        if PARTIAL: out({'type': 'stream_event', 'session_id': sid, 'event': {'type': 'content_block_delta', 'index': 0, 'delta': {'type': 'text_delta', 'text': c}}})
        lag = start + (i + 1) / TPS - time.time()
        if lag > 0: time.sleep(lag)
    out({'type': 'assistant', 'session_id': sid, 'message': {'role': 'assistant', 'content': [{'type': 'text', 'text': text}]}})
    log('result', n=n, out_chars=len(text))
    out({'type': 'result', 'subtype': 'success', 'is_error': False, 'result': text, 'session_id': sid, 'num_turns': n,
         'duration_ms': int((time.time() - t) * 1000)})


if os.environ.get('FAKE_CLAUDE_BROKEN'): sys.exit(1)          # a CLI half-way through updating itself: it starts and dies
time.sleep(SPAWN)
log('ready', spawn=round(time.time() - T0, 3), live=LIVE, args=args)
if LIVE:
    n = 0
    for line in sys.stdin:
        if not line.strip(): continue
        n += 1
        c = json.loads(line)['message']['content']
        turn(c if isinstance(c, str) else ''.join(b.get('text', '') for b in c if isinstance(b, dict)), n)
else:
    turn(sys.stdin.read(), 1)
