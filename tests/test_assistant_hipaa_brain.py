"""THE ASSISTANT ON A THINKING MODEL BEHIND A GATEWAY (the owner, 2026-11-09: "what is this garbage???"). On the HIPAA AI card the Assistant
showed "VIEW:", a stub cut mid-sentence, then "say it again" - and never acted on "set up a routine", then "log into <a portal> and
review my denials". The model spent its 380 tokens thinking and handed back a few words with finish_reason 'length'."""
import contextlib
import json
from unittest import mock

from taskuary import concierge, funnel, llm as L, signin, terminal
from taskuary.store import MemoryStore


class R:
    def __init__(self, j): self.status_code, self._j, self.text = 200, j, json.dumps(j)
    def json(self): return self._j

def answer(text, finish='stop', reasoning=0, out=20):
    return R({'choices': [{'message': {'role': 'assistant', 'content': text}, 'finish_reason': finish}],
              'usage': {'completion_tokens': out, 'completion_tokens_details': {'reasoning_tokens': reasoning}}})

def brain(replies, asked):
    def post(url, headers, body, *a, **k):
        asked.append(body.get('max_completion_tokens') or body.get('max_tokens')); return replies.pop(0)
    return mock.patch.object(L, 'post_retrying', post)


def test_an_answer_cut_short_by_thinking_is_asked_again_with_room_and_the_route_keeps_it():
    L._THINKS.clear(); asked = []
    f = L.make_llm('hipaa_ai', {'base_url': 'https://gateway.example/v1'}, 'code')
    with brain([answer('Tell me what the routine should', 'length', 360, 376), answer('Tell me what the routine should do.')], asked):
        assert f('sys', 'help me set up a routine', max_tokens=380) == 'Tell me what the routine should do.'
    assert asked == [380, L.ROOM]
    with brain([answer('Sure.')], asked): f('sys', 'and again', max_tokens=380)
    assert asked[-1] == L.ROOM                                   # seen thinking once: asked with room from then on, one request


def test_a_plain_length_cut_is_the_cap_asked_for_and_an_empty_stop_is_asked_once_more():
    L._THINKS.clear(); asked = []
    f = L.make_llm('hipaa_ai', {'base_url': 'https://gateway.example/v1'}, 'code')
    with brain([answer('One two three', 'length', 0, 3)], asked): assert f('sys', 'count', max_tokens=3) == 'One two three'
    with brain([answer('', 'stop', 900, 900), answer('Here it is.')], asked): assert f('sys', 'hi') == 'Here it is.'


def test_a_marker_with_nothing_behind_it_never_reaches_the_owner():
    for raw in ('What would you like this routine to do?\nVIEW:', 'What would you like this routine to do?\nOPTIONS:',
                'What would you like this routine to do?\nDECIDE: ', 'What would you like this routine to do?\nCALL: {"kind": "set'):
        shown, _ = concierge.gate(raw)
        assert shown == 'What would you like this routine to do?', raw
    assert 'say it again' not in concierge.LOST.lower()


def store():
    s = MemoryStore()
    for k in ('calendar_enabled', 'coding_auto_enabled', 'auto_draft_enabled'): s.set_setting(k, '0', 't')
    funnel.invalidate(); funnel.forget_states()
    return s


def turn(s, line, call, sort, seen):
    """The chat model answers with `call`; the set-up sort answers `sort` and records what it was handed."""
    def sorter(system, user, **kw):
        seen.append(json.loads(user)); return json.dumps(sort)
    reply = 'On it.\nCALL: ' + json.dumps(call)
    with mock.patch.object(terminal, 'live_sessions', return_value=[]), mock.patch.object(concierge, '_compose_llm', return_value=sorter):
        return concierge.say(s, line, llm=lambda *a, **k: reply)


ROUTINE = {'kind': 'routine', 'recurs': {'schedule': None, 'objective': 'log into the billing portal and review my denials'},
           'title': 'Review denials', 'signs_in': 'billingportal.example'}

def test_a_routine_asked_for_then_described_opens_new_routine_and_says_where_its_login_comes_from():
    s, seen = store(), []
    turn(s, 'Help me set up a new routine', {'kind': 'task.setup', 'params': {'text': 'set up a new routine'}},
         {'kind': 'routine', 'recurs': {'objective': 'a new routine'}}, [])
    out = turn(s, 'log into the billing portal and review my denials',
               {'kind': 'task.setup', 'params': {'text': 'log into the billing portal and review my denials'}}, ROUTINE, seen)
    assert 'set up a new routine' in seen[-1]['conversation_before'].lower()        # the sort read what came before
    assert out['new']['kind'] == 'workflow' and 'review my denials' in out['new']['text'] and 'routine' in out['new']
    assert 'billingportal.example' in out['say'] and 'Saved sign-ins' in out['say'] and 'CALL' not in out['say']
    # a sign-in is sealed in the computer's keychain; CI's macOS and Linux have none, so an in-memory one stands in (as test_signin)
    import sys
    from taskuary import vault
    from tests.test_signin import FakeKeyring
    with mock.patch.object(vault, '_keyring', return_value=FakeKeyring()) if sys.platform != 'win32' else contextlib.nullcontext():
        signin.save(s, 'billingportal.example', 'alex@northwind.example', 'pw')
    out = turn(s, 'and one more like it', {'kind': 'task.setup', 'params': {'text': 'log into the billing portal and review my denials'}}, ROUTINE, seen)
    assert 'is in Saved sign-ins, so the browser fills it' in out['say']

