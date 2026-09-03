"""Tiny client for the scratch server: python tq.py GET /api/x | POST /api/x '{"json":1}'"""
import sys, json, re, urllib.request
H = r'C:\Users\UNUSSB~1\AppData\Local\Temp\claude\C--Users-unussbaum-Documents-General-Testing-taskhub\4ed300c8-8b52-4c88-8747-64a79ae5215a\scratchpad\home7793\config.toml'
TOK = re.search(r'^token = "(.*)"', open(H, encoding='utf-8').read(), re.M).group(1)
BASE = 'http://127.0.0.1:7793'
def call(method, path, body=None):
    req = urllib.request.Request(BASE + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={'X-Taskuary-Token': TOK, 'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=600) as r: return r.status, json.loads(r.read() or b'null')
    except urllib.error.HTTPError as e: return e.code, e.read().decode(errors='replace')[:400]
if __name__ == '__main__':
    m, p = sys.argv[1], sys.argv[2]; b = json.loads(sys.argv[3]) if len(sys.argv) > 3 else None
    st, out = call(m, p, b); print(st); print(json.dumps(out, indent=1, default=str)[:int(sys.argv[4]) if len(sys.argv) > 4 else 3000])
