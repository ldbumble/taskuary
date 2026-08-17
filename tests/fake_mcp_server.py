"""A minimal MCP server over stdio for tests: initialize, tools/list, tools/call."""
import json, sys

TOOLS = [{'name': 'echo', 'description': 'echo back the text',
          'inputSchema': {'type': 'object', 'properties': {'text': {'type': 'string'}}}}]

for line in sys.stdin:
    line = line.strip()
    if not line: continue
    msg = json.loads(line)
    if 'id' not in msg: continue  # notification
    m = msg['method']
    if m == 'initialize':
        res = {'protocolVersion': msg['params']['protocolVersion'], 'capabilities': {'tools': {}},
               'serverInfo': {'name': 'fake', 'version': '0'}}
    elif m == 'tools/list':
        res = {'tools': TOOLS}
    elif m == 'tools/call':
        t = msg['params']['arguments'].get('text', '')
        res = {'content': [{'type': 'text', 'text': f'echo: {t}'}], 'isError': False}
    else:
        res = {}
    sys.stdout.write(json.dumps({'jsonrpc': '2.0', 'id': msg['id'], 'result': res}) + '\n')
    sys.stdout.flush()
