"""An agent's permission request put to the owner (permissions.py): Taskuary's rules first, then the owner's buttons; only the owner's
answer counts; "always" is kept per task and tool pattern and never for a send or a push; no answer is a refusal, said plainly; and the
ACP shape in and out, as step 1's acpgate hands it over."""
import os, tempfile, threading, time
from types import SimpleNamespace
from unittest import mock

import pytest

from taskuary import permissions as perm, terminal as term, workerstate as ws
from taskuary.store import MemoryStore
from taskuary.testing import Factory

REPO = tempfile.mkdtemp(prefix='ledger_')


@pytest.fixture
def s():
    st = MemoryStore()
    was = dict(term.SESSIONS); term.SESSIONS.clear()
    yield st
    term.SESSIONS.clear(); term.SESSIONS.update(was)


def coding(s, cwd=REPO):
    tid = Factory(s).task(title='Ledger rounding', kind='coding')
    term.SESSIONS[f's{tid}'] = SimpleNamespace(alive=True, task_id=tid, cwd=cwd, argv=['claude'], quick=False, sid=f's{tid}', mode='full')
    return tid


def asking(s, tid, req, wait=5.0):
    "ask() on its own thread, as the ACP reader runs it; the result lands in box[0]."
    box = []
    t = threading.Thread(target=lambda: box.append(perm.ask(s, tid, req, wait=wait)), daemon=True); t.start()
    for _ in range(200):
        if perm.pending(tid, s): break
        time.sleep(0.02)
    return t, box


# a fake ACP session/request_permission, as the adapters send it
ACP = {'sessionId': 'sess-1', 'toolCall': {'toolCallId': 'call-7', 'title': 'Run the money tests', 'kind': 'execute',
                                             'rawInput': {'command': 'npm test -- money'}, 'locations': [{'path': os.path.join(REPO, 'money.js')}]},
       'options': [{'optionId': 'a1', 'name': 'Allow', 'kind': 'allow_once'}, {'optionId': 'a2', 'name': 'Always', 'kind': 'allow_always'},
                   {'optionId': 'r1', 'name': 'Reject', 'kind': 'reject_once'}, {'optionId': 'r2', 'name': 'Never', 'kind': 'reject_always'}]}


def test_the_acp_request_reads_in_and_the_answer_goes_back_as_its_once_option():
    r = perm.from_acp(ACP)
    assert (r['kind'], r['command'], r['sid']) == ('execute', 'npm test -- money', 'sess-1')
    assert r['options'] == list(perm.OPTIONS) and r['locations'] == [os.path.join(REPO, 'money.js')]
    assert perm.to_acp(ACP, 'allow_always') == {'outcome': 'selected', 'optionId': 'a1'}     # an "always" is Taskuary's to keep
    assert perm.to_acp(ACP, 'reject_always') == {'outcome': 'selected', 'optionId': 'r1'}
    assert perm.to_acp({'options': [{'optionId': 'a1', 'kind': 'allow_once'}]}, 'reject_once') == {'outcome': 'cancelled'}


def test_a_read_inside_its_checkout_is_answered_by_the_rules_and_a_read_outside_goes_to_the_owner(s):
    tid = coding(s)
    inside = {'tool': 'Read', 'kind': 'read', 'locations': [os.path.join(REPO, 'money.py')]}
    assert perm.ask(s, tid, inside, wait=0.2) == 'allow_once' and not perm.pending(store=s)
    t, box = asking(s, tid, {'tool': 'Read', 'kind': 'read', 'locations': [os.path.join(tempfile.gettempdir(), 'payroll.csv')]})
    assert perm.pending(tid, s), 'a read outside its checkout is the owner\'s'
    perm.answer(s, tid, perm.pending(tid, s)[0]['id'], 'reject_once'); t.join(3)
    assert box == ['reject_once']


def test_the_owners_button_is_the_answer_and_always_is_kept_for_that_task_and_pattern(s):
    tid, other = coding(s), coding(s)
    t, box = asking(s, tid, perm.from_acp(ACP))
    p = perm.pending(tid, s)[0]
    assert [o['label'] for o in p['options']] == ['Allow once', 'Always allow', 'Reject', 'Always reject'] and 'npm test -- money' in p['line']
    # the rail reads it as waiting on the owner
    assert any(r['kind'] == 'approval_needed' for r in ws.status(s, tid)['requests'])
    assert perm.answer(s, tid, p['id'], 'Always allow')['ok']; t.join(3)
    assert box == ['allow_always'] and not perm.pending(tid, s)
    assert perm.ask(s, tid, perm.from_acp(ACP), wait=0.2) == 'allow_once'        # the next one is the rules', and still only once
    t, box = asking(s, other, perm.from_acp(ACP), wait=0.3); t.join(2)
    assert box == ['reject_once'], 'an always on one task is not an always on another'


def test_a_push_or_a_send_is_never_allowed_by_a_rule_and_never_offered_always(s):
    tid = coding(s)
    push = {'tool': 'Bash', 'kind': 'execute', 'command': 'git push origin fix-rounding', 'options': list(perm.OPTIONS)}
    s.set_perm_rule(tid, perm.pattern(perm.normal(push)), 'allow')                  # even an always written before
    t, box = asking(s, tid, push)
    p = perm.pending(tid, s)[0]
    assert p['risky'] and 'allow_always' not in [o['kind'] for o in p['options']]
    with pytest.raises(ValueError): perm.answer(s, tid, p['id'], 'allow_always')
    perm.answer(s, tid, p['id'], 'allow_once'); t.join(3)
    assert box == ['allow_once']
    for words in ('send the invoice to the vendor', 'post the release notes', 'pay the Payworth bill'):
        assert perm.normal({'tool': 'mcp', 'title': words})['risky']


def test_only_the_owner_answers(s):
    tid = coding(s)
    t, box = asking(s, tid, perm.from_acp(ACP), wait=0.5)
    with pytest.raises(PermissionError): perm.answer(s, tid, perm.pending(tid, s)[0]['id'], 'allow_once', actor='teammate')
    t.join(3)
    assert box == ['reject_once']


def test_no_answer_is_a_refusal_said_plainly(s):
    tid, late = coding(s), []
    assert perm.ask(s, tid, perm.from_acp(ACP), wait=0.2, timed_out=lambda: late.append(1)) == 'reject_once'
    assert late == [1] and not perm.pending(store=s)
    said = [c['Body'] for c in s.list_comments(tid)]
    assert any(b.startswith('No answer in') and 'refused' in b and 'npm test -- money' in b for b in said)


def test_the_generic_answer_road_takes_the_label_too(s):
    "The rail's own answer (POST /worker/answer) carries the choice's label - it resolves the held request as the button does."
    tid = coding(s)
    t, box = asking(s, tid, perm.from_acp(ACP))
    rid = perm.pending(tid, s) and next(r['request_id'] for r in ws.status(s, tid)['requests'] if r['kind'] == 'approval_needed')
    ws.answer(s, tid, rid, 'Reject'); t.join(3)
    assert box == ['reject_once']


def test_with_developer_mode_off_nothing_is_put_to_anyone(s):
    tid = coding(s)
    with mock.patch('taskuary.agents.developer_mode', return_value=False):
        assert perm.ask(s, tid, perm.from_acp(ACP), wait=5) == 'reject_once' and not perm.pending(store=s)
