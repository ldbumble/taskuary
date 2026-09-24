"""A fake claude in stream-json INPUT mode for tests/test_clipool.py: one JSON message per line in, a `result`
carrying its session id out. It touches no network and no file."""
import json, os, sys, time
args = sys.argv[1:]
sid = args[args.index('--resume') + 1] if '--resume' in args else 'sid-' + str(os.getpid())
n = 0
for line in sys.stdin:
    msg = json.loads(line)['message']['content']
    n += 1
    if msg == 'die': sys.exit(3)
    if msg == 'hang': time.sleep(30)
    print(json.dumps({'type': 'assistant', 'message': {'content': [{'type': 'text', 'text': 'thinking'}]}}), flush=True)
    print(json.dumps({'type': 'result', 'result': f'{os.getpid()}:{n}:{msg}', 'session_id': sid}), flush=True)
