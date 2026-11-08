"""AN AGENT'S EMAIL KEEPS ITS CC, AND A WITHDRAWN EMAIL CAN BE WRITTEN AGAIN (the product audit, 2026-11-08). Told "send it to Paula, keep
Gail on cc", the agent ran --cc and said Gail was copied; the saved envelope had `cc: []`. Then "it starts at 3pm, not 2pm": it withdrew
the 2pm email and every new one to Paula was refused ("could not add an email"), so the owner was told to send it by hand. Invented people.
"""
import json
from unittest import mock

from taskuary import server, slots
from taskuary.store import MemoryStore
from test_own_ask_no_reply import own_task
from test_withdraw_any_unsent import call, waiting

PAULA, GAIL = 'paula@northwind.example', 'gail@northwind.example'


def deliver(s, rid): return json.loads(s.get_review(rid)['Deliver'])


def test_the_cc_the_agent_gives_is_on_the_envelope():
    s = MemoryStore(); tid = own_task(s, 'general')
    with mock.patch.object(server, 'store', s):
        out = json.loads(call(tid, 'propose_email', to=PAULA, subject='Q4 review', text='Hi Paula - 2pm.', cc=['Gail Moreno <GAIL@northwind.example>'])[0])
    assert out['ok'] and deliver(s, out['review_id'])['cc'] == [GAIL]


def test_a_cc_that_is_no_address_is_refused_out_loud():
    s = MemoryStore(); tid = own_task(s, 'general')
    out = slots.draft(s, tid, 'Hi Paula', to=PAULA, subject='Q4', cc=['Gail'])
    assert out['ok'] is False and 'Gail' in out['why'] and not waiting(s, tid)
    assert slots.draft(s, tid, 'Hi', to='19:abc@thread.v2', channel='teams', cc=[GAIL])['ok'] is False


def test_after_a_withdraw_the_corrected_email_to_the_same_person_is_written():
    s = MemoryStore(); tid = own_task(s, 'general')
    with mock.patch.object(server, 'store', s):
        old = json.loads(call(tid, 'propose_email', to=PAULA, subject='Q4 review', text='It starts at 2pm.')[0])
        assert json.loads(call(tid, 'withdraw_draft', why='the time changed', which=str(old['review_id']))[0])['ok']
        new = json.loads(call(tid, 'propose_email', to=PAULA, subject='Q4 review', text='It starts at 3pm.', cc=[GAIL])[0])
    assert new['ok'] and new['review_id'] != old['review_id']
    assert waiting(s, tid) == [('slot', new['review_id'])] and deliver(s, new['review_id'])['cc'] == [GAIL]


def test_an_email_to_the_same_person_that_replaces_its_own_draft_stands():
    # the slot to Paula is open, so the new text lands in its review - withdrawing `replaces` then took the new email back with it
    s = MemoryStore(); tid = own_task(s, 'general')
    with mock.patch.object(server, 'store', s):
        old = json.loads(call(tid, 'propose_email', to=PAULA, subject='Q4 review', text='It starts at 2pm.')[0])
        by_id = json.loads(call(tid, 'propose_email', to=PAULA, subject='Q4 review', text='It starts at 3pm.', replaces=str(old['review_id']))[0])
        by_who = json.loads(call(tid, 'propose_email', to=PAULA, subject='Q4 review', text='It starts at 4pm.', replaces=PAULA)[0])
    assert by_id['ok'] and by_who['ok'] and waiting(s, tid) == [('slot', old['review_id'])]
    assert 'not_replaced' not in by_id and 'starts at 4pm' in s.get_review(old['review_id'])['DraftText']
