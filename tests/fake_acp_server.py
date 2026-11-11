"""A minimal ACP agent over stdio for tests: initialize, session/new, session/prompt.

It exists so the transport can be exercised without installing gemini, cursor or copilot, and it
deliberately does the one thing MCP never does: it sends a REQUEST BACK to the client mid-turn
(session/request_permission) and will not finish the turn until that is answered. A client that
only knows how to match replies to its own requests hangs here - which is the point.

Set in its environment, for the tests that need more:
  FAKE_ACP_FAIL=init     it dies at initialize, as an adapter that cannot start does
  FAKE_ACP_SPAWN=<secs>  it takes that long to start before it reads anything, as npx fetching an adapter does
  FAKE_ACP_THINK=<secs>  each turn takes that long before its first word, as a model thinking does
  FAKE_ACP_FAIL=turn     its first turn answers with an error after a word, as an overloaded model's does
  FAKE_ACP_RESUME=1      it offers session/resume (no replay) beside session/load
  FAKE_ACP_ASK=<command> the permission it asks for is to run that shell command (kind execute)
  FAKE_ACP_CODE=<file>   a coding turn: a plan, an edit of that file asked for (kind edit, its location) and, once allowed, made -
                         a comment line on top, sent back as a diff - then `git status` run, its output streamed as terminal deltas
  FAKE_ACP_HANG=1        a turn that only ends when it is cancelled (session/cancel) - or steered
  FAKE_ACP_STEER=1       it advertises mid-turn input (_meta.steering.supported, as claude-agent-acp and codex-acp do): `_session/steering`
                         joins the running turn, which then ends saying what it was steered with; with no turn running it is promptRequired
  FAKE_ACP_STEER_ECHO=1  ...and echoes the steered words back as a user_message_chunk before it answers the steer
  FAKE_ACP_USAGE=1       each turn's answer carries its usage and _meta.quota, as both adapters' PromptResponses do
  FAKE_ACP_MODELS=<a,b>  the model values it offers (default opus,sonnet)
  FAKE_DIRECTOR=<folder> each turn's words come from a scenario (fake_director.py), no permission asked; a session/cancel ends it meanwhile
  FAKE_ACP_SCRIPT=<file>  fake_claude's script: the first rule whose `when` the owner's words match answers `first`, after its `post`s ran
                         as the agent's own `taskuary --reply` would (fake_director.post) - a coding agent filing a reply, no permission asked
It offers config options (mode, model, effort) the way claude-agent-acp and codex-acp do, and says what they were set to.
"""
import json, os, re, sys
from fake_director import directed, folder_of, post

SID = 'sess_fake_1'
PERM_ID = 9001
_prompt_id = None                 # the turn waiting on the permission answer
_heard = ''                       # what it was asked, said back once the turn ends
SET = {'mode': 'auto', 'model': 'opus', 'effort': 'high'}
STARTS = 0                        # how many turns this one process has served: a kept connection serves more than one
RESUMED = ''                      # the session it was resumed into, said back in its answer


def send(msg): sys.stdout.write(json.dumps(msg) + '\n'); sys.stdout.flush()
def reply(i, result): send({'jsonrpc': '2.0', 'id': i, 'result': result})
def note(method, params): send({'jsonrpc': '2.0', 'method': method, 'params': params})


def update(what, **rest): note('session/update', {'sessionId': SID, 'update': {'sessionUpdate': what, **rest}})


def code_done(granted):
    "The edit allowed: made, its diff sent, a command run with its output streamed, and the turn ends."
    path = os.environ['FAKE_ACP_CODE']
    if granted:
        old = open(path, encoding='utf-8').read()
        new = '# keeps the ledger totals\n' + old
        open(path, 'w', encoding='utf-8', newline='\n').write(new)
        update('tool_call_update', toolCallId='call_1', status='completed',
               content=[{'type': 'diff', 'path': path, 'oldText': old, 'newText': new}])
        update('tool_call', toolCallId='call_2', title='git status', kind='execute', status='in_progress', rawInput={'command': 'git status --short'})
        update('tool_call_update', toolCallId='call_2', _meta={'terminal_output_delta': {'data': ' M ' + os.path.basename(path) + '\n'}})
        update('tool_call_update', toolCallId='call_2', status='completed', _meta={'terminal_exit': {'exit_code': 0}})
        update('plan', entries=[{'content': 'Read the file', 'status': 'completed'}, {'content': 'Add the comment', 'status': 'completed'}])
    else: update('tool_call_update', toolCallId='call_1', status='failed')
    update('agent_message_chunk', content={'type': 'text', 'text': ('Added the comment.' if granted else 'denied') + f' - {_heard}'})


def ended(stop='end_turn'):
    "A turn's answer - with what it used, the shape claude-agent-acp and codex-acp give, when FAKE_ACP_USAGE asks."
    if os.environ.get('FAKE_ACP_USAGE') != '1': return {'stopReason': stop}
    n = {'inputTokens': 12 * STARTS, 'cachedReadTokens': 3000, 'cachedWriteTokens': 400, 'outputTokens': 250}
    return {'stopReason': stop, 'usage': {**n, 'totalTokens': sum(n.values())},
            '_meta': {'quota': {'token_count': n, 'model_usage': [{'model': 'claude-opus-5-5', 'token_count': n}]}}}


def options():
    sel = lambda i, cat, vals: {'id': i, 'name': i, 'category': cat, 'type': 'select', 'currentValue': SET[i],
                                'options': [{'value': v, 'name': v} for v in vals]}
    return [sel('mode', 'mode', ['default', 'auto']), sel('model', 'model', (os.environ.get('FAKE_ACP_MODELS') or 'opus,sonnet').split(',')),
            sel('effort', 'thought_level', ['low', 'high'])]


if os.environ.get('FAKE_ACP_SPAWN'): __import__('time').sleep(float(os.environ['FAKE_ACP_SPAWN']))
for line in sys.stdin:
    line = line.strip()
    if not line: continue
    msg = json.loads(line)
    method, mid = msg.get('method'), msg.get('id')

    if method is None:                                  # the client answering our request
        if mid == PERM_ID and _prompt_id is not None:
            granted = ((msg.get('result') or {}).get('outcome') or {}).get('outcome') == 'selected' and \
                'reject' not in str(((msg.get('result') or {}).get('outcome') or {}).get('optionId'))
            if os.environ.get('FAKE_ACP_CODE'): code_done(granted)
            else:
                update('tool_call_update', toolCallId='call_1', status='completed' if granted else 'failed')
                update('agent_message_chunk', content={'type': 'text', 'text': ('granted' if granted else 'denied') + f' - {_heard}'})
            reply(_prompt_id, ended())
            _prompt_id = None
        continue

    if method == 'initialize':
        if os.environ.get('FAKE_ACP_FAIL') == 'init': sys.exit(3)
        caps = {'loadSession': True, 'promptCapabilities': {'image': False}}
        if os.environ.get('FAKE_ACP_RESUME') == '1': caps['sessionCapabilities'] = {'resume': {}}
        reply(mid, {'protocolVersion': msg['params'].get('protocolVersion', 1), 'agentCapabilities': caps,
                    'agentInfo': {'name': 'fake-acp', 'version': '0'}, 'authMethods': [],
                    **({'_meta': {'steering': {'supported': True}}} if os.environ.get('FAKE_ACP_STEER') == '1' else {})})
    elif method == 'session/new':
        # the cwd we were given is echoed back so a test can prove the run was placed correctly
        os.environ['FAKE_ACP_CWD'] = str(msg['params'].get('cwd') or '')
        reply(mid, {'sessionId': SID, 'configOptions': options()})
    elif method == 'session/load':
        update('agent_message_chunk', content={'type': 'text', 'text': 'replayed'})
        update('tool_call', toolCallId='old_1', title='an earlier turn', kind='read', status='completed', rawInput={'path': 'old.txt'})
        reply(mid, {'configOptions': options()})
    elif method == 'session/resume':
        RESUMED = str(msg['params'].get('sessionId') or '')
        reply(mid, {'configOptions': options()})
    elif method == 'session/set_config_option':
        SET[msg['params']['configId']] = msg['params']['value']
        reply(mid, {'configOptions': options()})
    elif method == 'session/prompt':
        STARTS += 1
        if os.environ.get('FAKE_ACP_THINK'): __import__('time').sleep(float(os.environ['FAKE_ACP_THINK']))
        # ...said back without Taskuary's markers its brief explains: a real agent never quotes them back, and one echoed from the brief raised a
        # sign-in nobody asked for
        said = re.sub(r'\[\[[^\]]*\]\]', '', ' '.join(str(b.get('text') or '') for b in msg['params'].get('prompt') or []))
        _heard = f"heard: {said} [mode={SET['mode']} model={SET['model']} effort={SET['effort']} turn={STARTS}" + (f' resumed={RESUMED}' if RESUMED else '') + ']'
        rule = next((r for r in (json.load(open(os.environ['FAKE_ACP_SCRIPT'], encoding='utf-8')) if os.environ.get('FAKE_ACP_SCRIPT') else [])
                     if re.search(r['when'], said, re.I)), None)
        if rule:
            # ...each post the shell call a real agent makes for it, reported running before it files and done after - never a card ahead of its turn
            for i, p in enumerate(rule.get('post') or []):
                update('tool_call', toolCallId=f'post_{i}', title='taskuary', kind='execute', status='in_progress', rawInput={'command': f"taskuary {p['path'].rsplit('/', 1)[-1]}"})
                post(p); update('tool_call_update', toolCallId=f'post_{i}', status='completed')
            update('agent_message_chunk', content={'type': 'text', 'text': rule.get('first') or 'Ok.'}); reply(mid, ended()); continue
        if folder_of():                                # a scenario's own turn (fake_director.py): its words, no permission asked
            _prompt_id = mid                           # ...on a thread, so a session/cancel meanwhile ends the turn as a real adapter's does
            def answer_later(mid=mid, said=said):
                global _prompt_id
                text = directed(said)
                if _prompt_id == mid: update('agent_message_chunk', content={'type': 'text', 'text': text}); reply(mid, ended()); _prompt_id = None
            __import__('threading').Thread(target=answer_later, daemon=True).start(); continue
        update('agent_message_chunk', content={'type': 'text', 'text': 'Looking. '})
        if os.environ.get('FAKE_ACP_FAIL') == 'turn' and STARTS == 1:
            send({'jsonrpc': '2.0', 'id': mid, 'error': {'code': -32603, 'message': 'Internal error: API Error: 529 Overloaded'}}); continue
        if os.environ.get('FAKE_ACP_HANG') == '1' and STARTS == 1:
            _prompt_id = mid; continue                  # only session/cancel ends this one
        if os.environ.get('FAKE_ACP_CODE'):
            path = os.environ['FAKE_ACP_CODE']
            update('plan', entries=[{'content': 'Read the file', 'status': 'completed'}, {'content': 'Add the comment', 'status': 'in_progress'}])
            tc = {'toolCallId': 'call_1', 'title': f'Edit {os.path.basename(path)}', 'kind': 'edit', 'rawInput': {'file_path': path},
                  'locations': [{'path': path, 'line': 1}]}
            update('tool_call', **tc, status='pending')
            _prompt_id = mid
            send({'jsonrpc': '2.0', 'id': PERM_ID, 'method': 'session/request_permission', 'params': {'sessionId': SID, 'toolCall': tc,
                  'options': [{'optionId': 'reject-once', 'name': 'Reject', 'kind': 'reject_once'}, {'optionId': 'allow-once', 'name': 'Allow once', 'kind': 'allow_once'}]}})
            continue
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
    elif method == '_session/steering' and os.environ.get('FAKE_ACP_STEER') == '1':
        if _prompt_id is None:
            reply(mid, {'outcome': 'promptRequired', 'reason': 'noRunningTurn'}); continue
        steered = ' '.join(str(b.get('text') or '') for b in msg['params'].get('prompt') or [])
        # ...echoed back first, as claude-agent-acp does when the CLI takes a steer in under a uuid of its own
        if os.environ.get('FAKE_ACP_STEER_ECHO') == '1': update('user_message_chunk', content={'type': 'text', 'text': steered})
        reply(mid, {'outcome': 'injected'})
        update('agent_message_chunk', content={'type': 'text', 'text': f'steered: {steered} - {_heard}'})
        reply(_prompt_id, ended()); _prompt_id = None
    elif method == 'session/cancel':
        if _prompt_id is not None:
            reply(_prompt_id, {'stopReason': 'cancelled'}); _prompt_id = None
    elif mid is not None:
        reply(mid, {})
