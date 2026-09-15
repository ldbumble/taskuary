"""A minimal ACP agent over stdio for tests: initialize, session/new, session/prompt.

It exists so the transport can be exercised without installing gemini, cursor or copilot, and it
deliberately does the one thing MCP never does: it sends a REQUEST BACK to the client mid-turn
(session/request_permission) and will not finish the turn until that is answered. A client that
only knows how to match replies to its own requests hangs here - which is the point.
"""
import json, os, sys

SID = 'sess_fake_1'
PERM_ID = 9001
_prompt_id = None                 # the turn waiting on the permission answer


def send(msg): sys.stdout.write(json.dumps(msg) + '\n'); sys.stdout.flush()
def reply(i, result): send({'jsonrpc': '2.0', 'id': i, 'result': result})
def note(method, params): send({'jsonrpc': '2.0', 'method': method, 'params': params})


def update(kind, **rest): note('session/update', {'sessionId': SID, 'update': {'sessionUpdate': kind, **rest}})


for line in sys.stdin:
    line = line.strip()
    if not line: continue
    msg = json.loads(line)
    method, mid = msg.get('method'), msg.get('id')

    if method is None:                                  # the client answering our request
        if mid == PERM_ID and _prompt_id is not None:
            granted = ((msg.get('result') or {}).get('outcome') or {}).get('outcome') == 'selected'
            update('agent_message_chunk', content={'type': 'text', 'text': 'granted' if granted else 'denied'})
            reply(_prompt_id, {'stopReason': 'end_turn'})
            _prompt_id = None
        continue

    if method == 'initialize':
        reply(mid, {'protocolVersion': msg['params'].get('protocolVersion', 1),
                    'agentCapabilities': {'loadSession': True, 'promptCapabilities': {'image': False}},
                    'agentInfo': {'name': 'fake-acp', 'version': '0'}, 'authMethods': []})
    elif method == 'session/new':
        # the cwd we were given is echoed back so a test can prove the run was placed correctly
        os.environ['FAKE_ACP_CWD'] = str(msg['params'].get('cwd') or '')
        reply(mid, {'sessionId': SID})
    elif method == 'session/load':
        update('agent_message_chunk', content={'type': 'text', 'text': 'replayed'})
        reply(mid, None)
    elif method == 'session/prompt':
        said = ' '.join(str(b.get('text') or '') for b in msg['params'].get('prompt') or [])
        update('agent_message_chunk', content={'type': 'text', 'text': f'heard: {said} '})
        update('tool_call', toolCallId='call_1', title='read the ledger', status='pending')
        update('tool_call_update', toolCallId='call_1', status='completed')
        _prompt_id = mid
        send({'jsonrpc': '2.0', 'id': PERM_ID, 'method': 'session/request_permission',
              'params': {'sessionId': SID, 'toolCall': {'toolCallId': 'call_1'},
                         'options': [{'optionId': 'reject-once', 'name': 'Reject', 'kind': 'reject_once'},
                                     {'optionId': 'allow-once', 'name': 'Allow once', 'kind': 'allow_once'}]}})
    elif method == 'session/cancel':
        if _prompt_id is not None:
            reply(_prompt_id, {'stopReason': 'cancelled'}); _prompt_id = None
    elif mid is not None:
        reply(mid, {})
