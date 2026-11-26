"""THE ASSISTANT ON A THINKING MODEL BEHIND A GATEWAY (the owner, 2026-11-09: "what is this garbage???"). On the HIPAA AI card the Assistant
showed "VIEW:", a stub cut mid-sentence, then "say it again" - and never acted on "set up a routine", then "log into <a portal> and
review my denials". The model spent its 380 tokens thinking and handed back a few words with finish_reason 'length'."""
import contextlib
import json
from unittest import mock

import pytest

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
    with mock.patch.object(terminal, 'live_sessions', return_value=[]), mock.patch.object(concierge, '_compose_llm', return_value=sorter),          mock.patch('taskuary.capabilities.has_ai', return_value=True), mock.patch('taskuary.general.start_session'), mock.patch('taskuary.server.store', s):
        return concierge.say(s, line, llm=lambda *a, **k: reply)


ROUTINE = {'kind': 'routine', 'recurs': {'schedule': None, 'objective': 'log into the billing portal and review my denials'},
           'title': 'Review denials', 'signs_in': 'billingportal.example'}

def test_a_routine_asked_for_then_described_starts_its_agent_and_says_where_its_login_comes_from():
    s, seen = store(), []
    turn(s, 'Help me set up a new routine', {'kind': 'task.setup', 'params': {'text': 'set up a new routine'}},
         {'kind': 'routine', 'recurs': {'objective': 'a new routine'}}, [])
    out = turn(s, 'log into the billing portal and review my denials',
               {'kind': 'task.setup', 'params': {'text': 'log into the billing portal and review my denials'}}, ROUTINE, seen)
    assert 'set up a new routine' in seen[-1]['conversation_before'].lower()        # the sort read what came before
    # ...a routine is its agent's to set up (save_routine), on a task with his words - never New's routine form (the walks, 2026-11-18)
    assert 'new' not in out and out['open'].startswith('#task=')
    assert 'review my denials' in s.get_task(int(out['open'].split('=')[1]))['Summary']
    assert 'billingportal.example' in out['say'] and 'Saved sign-ins' in out['say'] and 'CALL' not in out['say']
    # a sign-in is sealed in the computer's keychain; CI's macOS and Linux have none, so an in-memory one stands in (as test_signin)
    import sys
    from taskuary import vault
    from tests.test_signin import FakeKeyring
    with mock.patch.object(vault, '_keyring', return_value=FakeKeyring()) if sys.platform != 'win32' else contextlib.nullcontext():
        signin.save(s, 'billingportal.example', 'alex@northwind.example', 'pw')
    out = turn(s, 'and one more like it', {'kind': 'task.setup', 'params': {'text': 'log into the billing portal and review my denials'}}, ROUTINE, seen)
    assert 'is in Saved sign-ins, so the browser fills it' in out['say']


# ── "pull up my calendar for this upcoming monday" (a tester's install on this card, 2026-11-26: "Working… 30s", and no answer) ───────────
MONDAY = {'events': [{'start': '2026-11-30 10:00', 'end': '2026-11-30 10:30', 'subject': 'Budget review', 'all_day': False, 'where': 'Room 2', 'who': ['Erin Blake']},
                     {'start': '2026-11-30 14:00', 'end': '2026-11-30 15:00', 'subject': 'Dentist', 'all_day': False, 'where': '', 'who': []}],
          'errors': [], 'sources': ['outlook: alex@northwind.example', 'google: alex@example.com'], 'start': '2026-11-30T00:00', 'end': '2026-12-01T00:00', 'tz': 'UTC'}
ASK = 'pull up my calendar for this upcoming monday'
READ = 'CALL: ' + json.dumps({'kind': 'calendar.read', 'params': {'from': '2026-11-30', 'days': 1}})

def reads(agenda): return [c.kwargs for c in agenda.call_args_list if c.kwargs.get('start')]        # the turn's own: the rail's refresh reads from now

def calendars():
    s = store(); s.set_setting('calendar_enabled', '1', 't')
    return s


def test_the_agenda_across_his_calendars_is_read_and_answered_on_this_card():
    "Showing him his day is bringing it up: the read runs at once on an API card too, over every calendar the cards reach, and its answer is the turn's."
    s, asked = calendars(), []
    f = L.make_llm('hipaa_ai', {'base_url': 'https://gateway.example/v1'}, 'code')
    with brain([answer(READ), answer('Monday: Budget review at 10:00 with Erin Blake, then the dentist at 2:00.')], asked), \
         mock.patch('taskuary.calendar.agenda', return_value=MONDAY) as agenda:
        out = concierge.say(s, ASK, llm=f)
    assert out['say'] == 'Monday: Budget review at 10:00 with Erin Blake, then the dentist at 2:00.' and not out.get('error')
    assert [(k['days'], str(k['start'])[:10]) for k in reads(agenda)] == [(1, '2026-11-30')]


def test_with_no_calendar_connected_the_read_says_so_and_so_does_the_answer():
    s, heard = calendars(), []
    def f(system, user, **kw):
        heard.append(user); return READ if len(heard) == 1 else 'No calendar is connected yet, so there is nothing to show for Monday.'
    out = concierge.say(s, ASK, llm=f)
    assert 'No calendar is connected' in heard[1] and out['say'].startswith('No calendar is connected')


def test_a_card_that_never_answers_is_waited_on_for_the_turns_time_and_no_longer():
    """THE HANG: the read is two model calls, each given minutes by its card - and the pass that failed was followed by the read and the
    question once more. With nothing said, the page counted "Working…" for as long as that took. The turn has one clock: past it the owner
    reads why in one line, Try again under it, and nothing is read again for a question nobody is asked."""
    import threading, time
    s, heard, never = calendars(), [], threading.Event()
    def f(system, user, **kw):
        heard.append(user)
        if len(heard) == 1: return READ
        never.wait(30); return 'far too late'
    t0 = time.monotonic()
    try:
        with mock.patch.object(concierge, 'TURN_WAIT', 0.4), mock.patch('taskuary.calendar.agenda', return_value=MONDAY) as agenda:
            out = concierge.say(s, ASK, llm=f)
    finally: never.set()
    assert time.monotonic() - t0 < 5, 'the turn ended inside its time'
    assert out.get('error') and 'stopped waiting' in out['say'] and 'far too late' not in out['say'], out['say']
    assert out['chips'][0] == {'label': concierge.buttons.label('try_again'), 'ask': ASK}
    assert len(reads(agenda)) == 1 and len(heard) == 2, 'no second read, no third ask'
    assert [m['text'] for m in concierge.history(s, concierge.general.dock_task(s)[0]['TaskId'])[-2:]] == [ASK, out['say']], 'his line and the one line of why are the chat'


def test_his_stop_ends_a_turn_whose_card_is_still_out():
    "Stop reached no call under way on an API card: the turn went on waiting behind a page that had stopped. Now it ends at his press."
    import threading, time
    s, never, cancel = calendars(), threading.Event(), threading.Event()
    def f(system, user, **kw): cancel.set(); never.wait(30); return 'late'
    t0 = time.monotonic()
    try:
        with pytest.raises(concierge.Stopped): concierge.say(s, ASK, llm=f, cancel=cancel)
    finally: never.set()
    assert time.monotonic() - t0 < 5


# ── the pass that only chooses a look-up asks the card's quick model; the answer keeps the model chosen for the Assistant ──────────────────
def tiered(light='quick-model'):
    "His HIPAA AI card with a quick model on it, and a model of its own chosen for the Assistant."
    from taskuary import aidefaults
    s = calendars(); c = s.get_connector_by_type('hipaa_ai')
    s.save_connector({'ConnectorId': c['ConnectorId'], 'Active': 1, 'Secret': 'code',
                      'ConfigJson': json.dumps({'base_url': 'https://gateway.example/v1', 'model': 'card-model', **({'light_model': light} if light else {})})}, 't')
    p = f"connector:{c['ConnectorId']}"
    s.set_setting(concierge.AI_KEY, p, 't'); aidefaults.keep_model(s, concierge.MODEL_KEY, 'usual-model', 't', pick=p)
    return s

def models(s, line, replies):
    "The model each pass of the turn asked, in order, and what the turn said."
    asked = []
    def post(url, headers, body, *a, **k):
        asked.append(str(body.get('model')).split('@')[0]); return answer(replies[min(len(asked), len(replies)) - 1])
    with mock.patch.object(L, 'post_retrying', post), mock.patch('taskuary.calendar.agenda', return_value=MONDAY), \
         mock.patch('taskuary.capabilities.has_ai', return_value=True):
        out = concierge.say(s, line)
    return asked, out['say']

def test_the_look_up_pass_asks_the_quick_model_and_the_answer_the_usual_one():
    asked, said = models(tiered(), ASK, [READ, 'Monday: Budget review at 10:00, then the dentist at 2:00.'])
    assert asked == ['quick-model', 'usual-model'] and said.startswith('Monday: Budget review')

def test_what_the_quick_model_says_that_is_no_look_up_is_never_his_answer():
    asked, said = models(tiered(), 'thanks, that is all', ['A quick word.', 'You are welcome.'])
    assert asked == ['quick-model', 'usual-model'] and said == 'You are welcome.'

def test_a_card_with_no_quick_model_asks_its_one_model_once_per_pass():
    asked, said = models(tiered(light=''), ASK, [READ, 'Monday is two meetings.'])
    assert asked == ['usual-model', 'usual-model'] and said == 'Monday is two meetings.'
