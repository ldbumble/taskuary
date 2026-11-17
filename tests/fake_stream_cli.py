"""A fake claude in stream-json INPUT mode for tests/test_clipool.py: one JSON message per line in, a `result`
carrying its session id out. It touches no network and no file.
Like claude 2.1 it reads stdin while a turn runs: a message whose words hold `absorb:N` works until N more were written to it and takes them
INTO that turn (claude's mid-turn fold) - its result says what it heard; `queue:N` works until N more wait, leaves them queued and ends, each
then its own turn. Every result counts the sends still waiting (`queued_turn_count`), as claude's does."""
import json, os, queue, re, sys, threading, time
args = sys.argv[1:]
sid = args[args.index('--resume') + 1] if '--resume' in args else 'sid-' + str(os.getpid())
q, n = queue.Queue(), 0
def read():
    try:
        for line in sys.stdin: q.put(json.loads(line)['message']['content'])
    finally: q.put(None)
threading.Thread(target=read, daemon=True).start()
def out(j): print(json.dumps(j), flush=True)
def until(k):
    end = time.time() + 10
    while q.qsize() < k and time.time() < end: time.sleep(0.02)
while (msg := q.get()) is not None:
    n += 1
    if msg == 'die': sys.exit(3)
    if msg == 'hang': time.sleep(30)
    out({'type': 'assistant', 'message': {'content': [{'type': 'text', 'text': 'thinking'}]}})
    said = msg
    if (m := re.search(r'absorb:(\d+)', msg)):
        until(int(m[1])); said = 'heard ' + ' | '.join(q.get() for _ in range(min(int(m[1]), q.qsize())))
    elif (m := re.search(r'queue:(\d+)', msg)): until(int(m[1])); said = 'queued'
    out({'type': 'result', 'result': f'{os.getpid()}:{n}:{said}', 'session_id': sid, 'queued_turn_count': q.qsize()})
