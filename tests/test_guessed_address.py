"""A GUESSED ADDRESS IS SAID ON THE CARD (the owner, 2026-11-09). With no address on record one agent held its emails back and another put
a firstname@ guess on the draft: the guess is allowed, the card says it is guessed, and the owner's Send is the check. Invented people."""
import json
from unittest import mock

from taskuary import general, server, slots
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
    assert 'guessed' in general._ACTION and 'never hold the email or the meeting invite back' in general._ACTION
