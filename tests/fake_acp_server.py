"""A minimal ACP agent over stdio for tests: initialize, session/new, session/prompt.

It exists so the transport can be exercised without installing gemini, cursor or copilot, and it
deliberately does the one thing MCP never does: it sends a REQUEST BACK to the client mid-turn
(session/request_permission) and will not finish the turn until that is answered. A client that
only knows how to match replies to its own requests hangs here - which is the point.

Set in its environment, for the tests that need more:
  FAKE_ACP_FAIL=init     it dies at initialize, as an adapter that cannot start does
  FAKE_ACP_RESUME=1      it offers session/resume (no replay) beside session/load
  FAKE_ACP_ASK=<command> the permission it asks for is to run that shell command (kind execute)
It offers config options (mode, model, effort) the way claude-agent-acp and codex-acp do, and says what they were set to.
"""
import json, os, sys

SID = 'sess_fake_1'
PERM_ID = 9001
_prompt_id = None                 # the turn waiting on the permission answer
_heard = ''                       # what it was asked, said back once the turn ends
SET = {'mode': 'auto', 'model': 'opus', 'effort': 'high'}
STARTS = 0                        # how many turns this one process has served: a kept connection serves more than one


def send(msg): sys.stdout.write(json.dumps(msg) + '\n'); sys.stdout.flush()
def reply(i, result): send({'jsonrpc': '2.0', 'id': i, 'result': result})
def note(method, params): send({'jsonrpc': '2.0', 'method': method, 'params': params})


def update(what, **rest): note('session/update', {'sessionId': SID, 'update': {'sessionUpdate': what, **rest}})


def options():
    sel = lambda i, cat, vals: {'id': i, 'name': i, 'category': cat, 'type': 'select', 'currentValue': SET[i],
                                'options': [{'value': v, 'name': v} for v in vals]}
    return [sel('mode', 'mode', ['default', 'auto']), sel('model', 'model', ['opus', 'sonnet']),
            sel('effort', 'thought_level', ['low', 'high'])]


for line in sys.stdin:
    line = line.strip()
    if not line: continue
    msg = json.loads(line)
    method, mid = msg.get('method'), msg.get('id')

    if method is None:                                  # the client answering our request
        if mid == PERM_ID and _prompt_id is not None:
            granted = ((msg.get('result') or {}).get('outcome') or {}).get('outcome') == 'selected' and \
                'reject' not in str(((msg.get('result') or {}).get('outcome') or {}).get('optionId'))
            update('tool_call_update', toolCallId='call_1', status='completed' if granted else 'failed')
            update('agent_message_chunk', content={'type': 'text', 'text': ('granted' if granted else 'denied') + f' - {_heard}'})
            reply(_prompt_id, {'stopReason': 'end_turn'})
            _prompt_id = None
        continue

    if method == 'initialize':
        if os.environ.get('FAKE_ACP_FAIL') == 'init': sys.exit(3)
        caps = {'loadSession': True, 'promptCapabilities': {'image': False}}
        if os.environ.get('FAKE_ACP_RESUME') == '1': caps['sessionCapabilities'] = {'resume': {}}
        reply(mid, {'protocolVersion': msg['params'].get('protocolVersion', 1), 'agentCapabilities': caps,
                    'agentInfo': {'name': 'fake-acp', 'version': '0'}, 'authMethods': []})
    elif method == 'session/new':
        # the cwd we were given is echoed back so a test can prove the run was placed correctly
        os.environ['FAKE_ACP_CWD'] = str(msg['params'].get('cwd') or '')
        reply(mid, {'sessionId': SID, 'configOptions': options()})
    elif method == 'session/load':
        update('agent_message_chunk', content={'type': 'text', 'text': 'replayed'})
        update('tool_call', toolCallId='old_1', title='an earlier turn', kind='read', status='completed', rawInput={'path': 'old.txt'})
        reply(mid, {'configOptions': options()})
    elif method == 'session/resume':
        reply(mid, {'configOptions': options()})
    elif method == 'session/set_config_option':
        SET[msg['params']['configId']] = msg['params']['value']
        reply(mid, {'configOptions': options()})
    elif method == 'session/prompt':
        STARTS += 1
        said = ' '.join(str(b.get('text') or '') for b in msg['params'].get('prompt') or [])
        _heard = f"heard: {said} [mode={SET['mode']} model={SET['model']} effort={SET['effort']} turn={STARTS}]"
        update('agent_message_chunk', content={'type': 'text', 'text': 'Looking. '})
        ask = os.environ.get('FAKE_ACP_ASK')
        tc = {'toolCallId': 'call_1', 'title': ask, 'kind': 'execute', 'rawInput': {'command': ask}} if ask else \
             {'toolCallId': 'call_1', 'title': 'read the ledger'}
        update('tool_call', **tc, status='pending')
        _prompt_id = mid
        send({'jsonrpc': '2.0', 'id': PERM_ID, 'method': 'session/request_permission',
              'params': {'sessionId': SID, 'toolCall': tc,
                         'options': [{'optionId': 'reject-once', 'name': 'Reject', 'kind': 'reject_once'},
                                     {'optionId': 'allow-always', 'name': 'Always', 'kind': 'allow_always'},
                                     {'optionId': 'allow-once', 'name': 'Allow once', 'kind': 'allow_once'}]}})
    elif method == 'session/cancel':
        if _prompt_id is not None:
            reply(_prompt_id, {'stopReason': 'cancelled'}); _prompt_id = None
    elif mid is not None:
        reply(mid, {})
