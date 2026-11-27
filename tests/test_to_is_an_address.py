"""TO IS ALWAYS AN ADDRESS, OR EMPTY WITH A REASON (the owner, 2026-11-09: an agent's email card read "To: <a bank's name>" - "it needs
to be email address?"). Triage's slot named an organisation and the draft copied the name onto the envelope. Now a name is resolved when
the draft is saved: the person in the owner's mail, else someone at that organisation (marked guessed), else an empty To the card asks
for. Invented people and organisations."""
import json

import pytest

from taskuary import outbound, slots
from taskuary.store import MemoryStore
from test_own_ask_no_reply import own_task

DESK, ERIN = 'treasury@northwind-bank.example', 'erin@northwind.example'


def store_with_mail():
    s = MemoryStore(); tid = own_task(s, 'general')
    other = s.create_task({'Title': 'An older thread', 'Kind': 'general', 'Status': 'done'}, 'owner')
    for i, (name, a) in enumerate([('Treasury Desk', DESK), ('Erin Blake', ERIN)]):
        s.add_message({'TaskId': other, 'ExternalId': f'm-{i}', 'Channel': 'email', 'FromName': name, 'FromEmail': a,
                       'Subject': 'Hello', 'BodyText': 'hi', 'SentAt': '2026-11-01 09:00:00', 'Status': 'routed'})
    return s, tid


def draft_to(s, tid, who):
    slot = slots.add(s, tid, [{'to': who, 'about': 'ask for the allowlist', 'kind': 'email'}], 'triage')[0]
    out = slots.draft(s, tid, 'Hi - please add the address to the allowlist.', slot=slot['id'], agent='assistant')
    rv = s.get_review(out['review_id'])
    return out, rv, json.loads(rv['Deliver'])


@pytest.mark.parametrize('who', ['Northwind Bank', 'Erin Blake', 'Nowhere Credit Union'], ids=['bank', 'person', 'credit-union'])
def test_to_is_always_an_address_or_empty_with_a_reason(who):
    s, tid = store_with_mail()
    out, rv, d = draft_to(s, tid, who)
    assert out['ok'] and all('@' in a for a in d['to'])
    if not d['to']: assert slots.NEEDS + who in rv['Reason'] and out['to_missing']


def test_an_organisation_gets_someone_at_it_from_the_owners_mail_marked_guessed():
    s, tid = store_with_mail()
    _, rv, d = draft_to(s, tid, 'Northwind Bank')
    assert d['to'] == [DESK] and d['guessed'] == [DESK] and slots.GUESSED + DESK in rv['Reason']
    slot = next(i for i in s.task_checklist(tid) if i.get('out'))
    assert slot['out']['to'] == DESK and slot['out']['name'] == 'Northwind Bank'      # the name rides beside it as its label


def test_a_person_named_in_the_owners_mail_is_known_not_guessed():
    s, tid = store_with_mail()
    _, rv, d = draft_to(s, tid, 'Erin Blake')
    assert d['to'] == [ERIN] and 'guessed' not in d and 'guessed' not in rv['Reason']


def test_nobody_found_leaves_to_empty_until_the_owner_gives_one():
    s, tid = store_with_mail()
    _, rv, d = draft_to(s, tid, 'Nowhere Credit Union')
    assert d['to'] == []
    slots.readdress(s, rv, ['help@nowhere-cu.example'])
    rv = s.get_review(rv['ReviewId'])
    assert json.loads(rv['Deliver'])['to'] == ['help@nowhere-cu.example'] and slots.NEEDS not in rv['Reason']


def test_a_name_never_reaches_the_provider_as_the_recipient():
    with pytest.raises(RuntimeError, match='not an email address'):
        outbound.send_out(MemoryStore(), 'email', ['Northwind Bank'], 'Allowlist', 'Hi')


# ...and EACH address whole: an agent's `to` of "paula@..., gail@..." stood on the card as a single recipient the provider refused at Send, and
# "paula@" stood as if it were one. `to` is a list now (the card-tool design, 2026-11-27): a line of addresses is one email to each of them,
# its To holding every one apart; a cut-short address is refused at the tool before anything stands
@pytest.mark.parametrize('to', ['paula@northwind.example, gail@northwind.example', 'paula@northwind.example; gail@northwind.example',
                                'Paula Vance <paula@northwind.example>, gail@northwind.example',
                                ['paula@northwind.example', 'gail@northwind.example']], ids=['comma', 'semicolon', 'named-and-bare', 'list'])
def test_a_to_of_several_addresses_is_one_email_to_each_of_them(to):
    s = MemoryStore(); tid = own_task(s, 'general')
    out = slots.draft(s, tid, 'Hi Paula', to=to, subject='Q4')
    assert out['ok'] and json.loads(s.get_review(out['review_id'])['Deliver'])['to'] == ['paula@northwind.example', 'gail@northwind.example']

def test_a_to_that_is_not_an_address_is_refused_before_it_stands():
    s = MemoryStore(); tid = own_task(s, 'general')
    out = slots.draft(s, tid, 'Hi Paula', to='paula@', subject='Q4')
    assert out['ok'] is False and 'is not an email address' in out['why'] and '`to` is a list' in out['why']
    assert not s._rows("SELECT * FROM review WHERE TaskId=?", (tid,)), 'nothing stands for his Send'
    assert slots.draft(s, tid, 'Hi Paula', to='paula@northwind.example', subject='Q4', cc=['gail@northwind.example'])['ok']
