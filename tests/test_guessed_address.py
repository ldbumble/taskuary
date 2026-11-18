"""A GUESSED ADDRESS IS SAID ON THE CARD (the owner, 2026-11-09). With no address on record one agent held its emails back and another put
a firstname@ guess on the draft: the guess is allowed, the card says it is guessed, and the owner's Send is the check. Invented people."""
import json
from unittest import mock

from taskuary import general, server, slots
from taskuary.projects import PUBLIC_MAIL
from taskuary.store import MemoryStore
from test_own_ask_no_reply import own_task
from test_withdraw_any_unsent import call

ERIN = 'erin@northwind.example'


def test_the_card_says_which_address_is_guessed_until_the_owner_types_one():
    s = MemoryStore(); tid = own_task(s, 'general')
    with mock.patch.object(server, 'store', s):
        out = json.loads(call(tid, 'propose_email', to=ERIN, subject='Q4 review', text='Hi Erin', guessed=[ERIN])[0])
    rv = s.get_review(out['review_id'])
    assert out['ok'] and 'guessed, check before Send: ' + ERIN in rv['Reason'] and json.loads(rv['Deliver'])['guessed'] == [ERIN]
    slots.readdress(s, rv, ['erin.blake@northwind.example'])
    assert 'guessed' not in s.get_review(out['review_id'])['Reason']


def test_a_rewrite_with_the_address_known_clears_the_mark():
    s = MemoryStore(); tid = own_task(s, 'general')
    rid = slots.draft(s, tid, 'Hi Erin', to=ERIN, subject='Q4', guessed=[ERIN])['review_id']
    assert slots.draft(s, tid, 'Hi Erin, again', to=ERIN, subject='Q4')['review_id'] == rid
    assert 'guessed' not in s.get_review(rid)['Reason'] and 'wrote this email' in s.get_review(rid)['Reason']


def test_the_agent_is_told_to_guess_and_mark_rather_than_hold_the_email():
    told = general.action_line(MemoryStore(), tools=True)      # ...a session with the email tool: `guessed` is the tool's own word
    assert '`guessed`' in told and 'never hold the email or the meeting invite back' in told
    assert 'is a guess' in general.action_line(MemoryStore()) and '`guessed`' not in general.action_line(MemoryStore())


# A GUESS WHERE HIS MAIL KNOWS THE COMPANY IS NO GUESS TO MAKE (the owner, 2026-11-17: an email to a made-up address at a bank went out and
# bounced while the bank's contact had written three months before - "give it tool to search emails"): the email tool refuses it and names
# the people at that company his mail knows, so the agent drafts to one of them or asks him. A company his mail never saw still takes a guess
def test_a_guessed_address_at_a_company_his_mail_knows_is_refused_with_who_is_there():
    s = MemoryStore(); tid = own_task(s, 'general')
    s.add_message({'ExternalId': 'in-bank', 'ConversationId': 'c-bank', 'Channel': 'email', 'SourceName': 'alex@northwind.example',
                   'FromName': 'Garlanian, Anna', 'FromEmail': 'AGarlanian@bank.example', 'Subject': 'Your account', 'BodyText': 'Hi',
                   'SentAt': '2026-08-26 11:58:17', 'Status': 'filed'})
    out = slots.draft(s, tid, 'Hi Anna', to='acarlini@bank.example', subject='Allowlist', guessed=['acarlini@bank.example'])
    assert out['ok'] is False and 'agarlanian@bank.example' in out['why'].lower() and 'Garlanian, Anna' in out['why']
    assert not s._rows("SELECT * FROM review WHERE TaskId=?", (tid,)), 'nothing stands for his Send'
    assert slots.draft(s, tid, 'Hi Anna', to='AGarlanian@bank.example', subject='Allowlist')['ok']


# ...but a free mailbox is nobody's company: a guess at a person's address on a public mail service was refused with whoever else in his mail
# uses that service - strangers to the person it is for - so the agent was steered to draft to one of them
def test_a_guess_at_a_public_mail_service_is_not_refused_by_who_else_uses_it():
    FREE = sorted(PUBLIC_MAIL)[0]       # one of them, unnamed here
    s = MemoryStore(); tid = own_task(s, 'general')
    s.add_message({'ExternalId': 'in-free', 'ConversationId': 'c-free', 'Channel': 'email', 'SourceName': 'alex@northwind.example',
                   'FromName': 'Marcus Reed', 'FromEmail': f'marcus.reed@{FREE}', 'Subject': 'Hello', 'BodyText': 'Hi',
                   'SentAt': '2026-08-26 11:58:17', 'Status': 'filed'})
    out = slots.draft(s, tid, 'Hi Omar', to=f'omar.keller@{FREE}', subject='Saturday', guessed=[f'omar.keller@{FREE}'])
    assert out['ok'], out
    assert f'guessed, check before Send: omar.keller@{FREE}' in s.get_review(out['review_id'])['Reason']
