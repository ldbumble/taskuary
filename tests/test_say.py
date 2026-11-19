"""ONE OWNER-WORDS FUNCTION (the one-log spec, part C, 2026-11-19): what the owner reads is said by say.owner, never borrowed from the words the
agent is told. A corpus scan of every event the owner surfaces carry: no instruction to the agent, no tool's raw frame, no reader's own head.
Invented sites and people only."""
import json
from taskuary import general, say, shellgate

# what only an agent is ever told: its next command, a shouted verdict, the judge's account of itself, a reader's name for itself
AGENT_ONLY = ('`', 'agent-browser', 'REFUSED', 'run it again', 'End your turn', 'propose', 'the AI could not', 'triage:', 'At line:', 'a box only the owner')
GIT = "To https://github.com/northwind/ledger.git\n ! [rejected]        main -> main (fetch first)\nerror: failed to push some refs to 'https://github.com/northwind/ledger.git'\nhint: Updates were rejected"
PS = "At line:1 char:66\n+ \"C:\\WINDOWS\\powershell.exe\" -Command 'git push'\n+     ~~~~~~~~\nUnexpected token '-Command' in expression or statement."
CORPUS = [{'kind': 'land_refused', 'how': 'Push', 'why': GIT}, {'kind': 'land_refused', 'how': 'Deploy', 'why': PS},
          {'kind': 'signin', 'site': 'toll.example', 'ok': True, 'signup': True, 'saved': True, 'where': 'Saved sign-ins'},
          {'kind': 'signin', 'site': 'toll.example', 'ok': False},
          {'kind': 'signup_failed', 'site': 'trainly.example', 'why': 'That email is already registered'}, {'kind': 'signup_failed', 'site': 'trainly.example'},
          {'kind': 'held', 'why': 'the AI could not tell whether it spends money or sends your own details, so it waits for you'},
          {'kind': 'held', 'why': 'the AI could not tell whether it can be undone'}, {'kind': 'held', 'why': 'it leaves this computer'},
          {'kind': 'reason', 'text': 'triage: fyi - Erin Blake shares the rota for next week'}, {'kind': 'reason', 'text': 'triage: the vendor confirms the order'},
          # ...a turn the AI provider ended: its raw error, every shape it comes in
          *({'kind': 'turn_failed', 'raw': r} for r in (
              '{"type":"error","error":{"type":"rate_limit_error","message":"This request would exceed the rate limit for your organization"}}',
              'API Error: 401 {"type":"error","error":{"type":"authentication_error","message":"invalid x-api-key"}}',
              "Error code: 400 - {'error': {'message': 'litellm.BadRequestError: model not allowed', 'type': 'invalid_request_error'}}",
              'HTTP 529 {"type":"error","error":{"type":"overloaded_error","message":"Overloaded"}}', 'Traceback (most recent call last): ...', ''))]
AGENT_ONLY += ('{', 'Error code', 'Traceback', 'litellm', 'x-api-key')


def test_no_agent_facing_words_reach_the_owner():
    for e in CORPUS:
        said = say.owner(e)
        assert said and not [m for m in AGENT_ONLY if m in said], (e, said)


def test_the_presses_he_reads_in_the_chat_are_said_by_it():
    refused = general.PRESSES['land_refused']({'how': 'push', 'why': GIT})
    assert refused.endswith("it did not go: error: failed to push some refs to 'https://github.com/northwind/ledger.git'") and 'REFUSED' not in refused
    assert general.PRESSES['signin_fill']({'site': 'trainly.example', 'ok': True, 'why': 'a code was asked', 'signup': True}).startswith('signed up on trainly.example')
    assert general.PRESSES['signin_fill']({'site': 'toll.example', 'ok': True}).startswith('signed in to toll.example')


def test_a_held_steps_failure_is_its_reason_line():
    assert shellgate.failed(PS, 1, 'push 3 commits to northwind/ledger main') == \
        "Push 3 commits to northwind/ledger main failed: Unexpected token '-Command' in expression or statement."
    assert say.owner({'kind': 'reason', 'text': 'triage: fyi - Erin Blake shares the rota'}) == 'Erin Blake shares the rota'


def test_a_failed_turn_says_what_failed_once_in_his_words():
    from taskuary import chatlog
    from taskuary.general import ASSISTANT_TYPE, FAILED_MARK
    from taskuary.store import MemoryStore
    from taskuary.testing import Factory
    s = MemoryStore(); tid = Factory(s).task('Reconcile the October invoices')
    raw = '{"type":"error","error":{"type":"rate_limit_error","message":"This request would exceed the rate limit"}}'
    body = f'{raw}\n\n{FAILED_MARK}{raw}'           # the shape a failed turn is filed in: its words, then its marked failure
    cid = s.add_comment(tid, 'assistant', ASSISTANT_TYPE, body)
    chatlog.answered(s, tid, cid, 'assistant', body, s.list_comments(tid, internal=True)[-1]['CreatedAt'])
    [t] = [x for x in chatlog.read(s, tid)['items'] if x['kind'] == 'turn']
    assert t['fail'] == say.turn_failed(raw) and 'over its quota' in t['fail']
    assert not t.get('text') and not [x for x in t.get('steps') or [] if x.get('k') == 'error']     # once, never the raw JSON again


# ── THE CORPUS SCAN OVER EVERY SURFACE HE READS (part C, 2026-11-19): the same raw failures pushed through each payload's own builder ───────
RAWS = ('{"type":"error","error":{"type":"rate_limit_error","message":"This request would exceed the rate limit"}}',
        'API Error: 401 {"type":"error","error":{"type":"authentication_error","message":"invalid x-api-key"}}',
        'FileNotFoundError: [Errno 2] No such file or directory: \'claude\'',
        'Traceback (most recent call last):\n  File "x.py", line 3, in <module>\nValueError: bad',
        '503 Server Error: Service Unavailable for url: https://graph.microsoft.example/v1.0/me/messages')


def _clean(said, where):
    assert said and not say.raw(said) and not [m for m in AGENT_ONLY if m in said], (where, said)


def test_no_raw_text_reaches_any_surface_he_reads():
    import asyncio
    from fastapi import HTTPException
    from starlette.requests import Request
    from taskuary import funnel, problems, remote_assistant, server
    from taskuary.store import MemoryStore
    for r in RAWS:
        _clean(say.plain(r, 'any'), 'toast'); _clean(say.plain(r, 'start'), 'start'); _clean(say.plain(r, 'service'), 'bell')
        _clean(say.owner({'kind': 'turn_failed', 'raw': r}), 'chat')
        _clean(remote_assistant.plain(RuntimeError(r)), 'phone')                                  # the phone's "I couldn't answer that - ..."
        _clean(server._queued_info({'State': 'failed', 'Attempts': 3, 'LastError': r})['lastError'], 'start queue')
        req = Request({'type': 'http', 'method': 'POST', 'path': '/api/x', 'headers': [], 'query_string': b'', 'scheme': 'http', 'server': ('127.0.0.1', 80)})
        got = asyncio.run(server._plain_refusal(req, HTTPException(422, r)))
        _clean(json.loads(got.body)['detail'], 'toast')
        s = MemoryStore()
        cid = s.save_connector({'Type': 'imap', 'Name': 'Mail', 'Active': 1}, 't')
        s.touch_connector(cid, r)
        for p in problems.collect(s): _clean(p.get('detail') or p.get('title'), 'bell')
    _clean(funnel._reason_said('triage: fyi - Erin Blake shares the rota'), 'rail')
    # ...and Taskuary's own sentences pass as they are, on every surface
    own = 'No AI is connected - connect one under Connections.'
    assert say.plain(own, 'any') == say.plain(own, 'start') == remote_assistant.plain(ValueError(own)) == own


def test_a_failed_steps_row_says_why_in_his_words():
    for r in RAWS: _clean(say.step_why(r), 'step row')
    assert say.step_why("U a.js\nerror: failed to push some refs\nhint: pull first") == 'Why: error: failed to push some refs'
    assert say.step_why('') == 'It stopped without saying why.'


def test_one_road_for_a_failures_words():
    # the readings each surface had of its own are say's (operations.plain, channels.plain_failure, firstrun.plain_ai_error): one function each
    from taskuary import channels, firstrun, operations
    assert channels.plain_failure is say.plain_failure and firstrun.plain_ai_error is say.plain_ai_error and operations.plain is say.names
    assert say.said(RuntimeError('No AI is connected - connect one under Connections.')) == 'No AI is connected - connect one under Connections.'
    for r in RAWS: _clean(say.said(RuntimeError(r)), 'a line in the chat')
    # ...and no chat line is written from a raw exception any more: every add_comment that names `e` says it through say
    import pathlib, re
    for p in pathlib.Path(say.__file__).parent.glob('*.py'):
        for n, l in enumerate(p.read_text(encoding='utf-8').splitlines(), 1):
            if 'add_comment(' in l and re.search(r"\{(str\(e\)|e)(\)?\[:\d+\])?\}|' '\.join\(str\(e\)", l): raise AssertionError(f'{p.name}:{n} writes a raw exception to the chat')
