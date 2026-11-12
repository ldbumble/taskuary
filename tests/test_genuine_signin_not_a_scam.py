"""A genuine sign-in link is not a scam (the owner, 2026-11-01: "this is also wrong. it's not a scam but real").

Alex was signing an AI tool's CLI back in and asked for a sign-in link. It came, from the provider's own no-reply address, and its FYI
row read "Looks like a scam aimed at you - don't click or pay". Triage saw an address, a subject and a body that opened with the mail
client's "You don't often get email from ..." and the company's "This email was sent from outside of ..." notice - and nothing that said
whether the From was genuine or a service Alex uses. Now it is told (senders.sender_check), and the guide says what weighs: the banners
are no evidence, a verified service the owner uses sending a sign-in link is not a scam, and a look-alike, a failed verification or a
display name the domain does not belong to still is. Facts and guidance, no gate and no word list."""
import json
from datetime import datetime, timedelta
from unittest import mock

import pytest

from taskuary import config, ingest, senders, triage
from taskuary.store import MemoryStore

BANNERS = ("You don't often get email from no-reply-x1@mail.aiprovider.example. Learn why this is important\n"
           'This email was sent from outside of Northwind. Do not click links unless you know the content is safe.\n\n')
BODY = BANNERS + 'Sign in to AI Provider\nYou requested a sign-in link. Click below to sign in. This link expires in 10 minutes.'
REAL = {'from_email': 'no-reply-x1@mail.aiprovider.example', 'from_name': 'AI Provider', 'subject': 'Your sign-in link',
        'channel': 'email', 'external_id': 'm-real', 'body': BODY, 'auth': 'pass'}
LOOK = {**REAL, 'from_email': 'no-reply@aiprovider-login.example', 'external_id': 'm-look', 'auth': None}
FORGED = {**REAL, 'external_id': 'm-forged', 'auth': 'fail'}


@pytest.fixture
def s():
    v = MemoryStore()
    # Alex has had the provider's receipts before - from its billing address, not the sign-in one
    v.add_message({'ExternalId': 'old-1', 'Channel': 'email', 'FromEmail': 'billing@aiprovider.example', 'Subject': 'Your receipt',
                   'BodyText': 'Thanks for your payment.', 'Status': 'filed'})
    # ...and a phish that once wore a look-alike name, read as danger: it vouches for nobody
    m = v.add_message({'ExternalId': 'old-2', 'Channel': 'email', 'FromEmail': 'it@aiprovider-login.example', 'BodyText': 'x', 'Status': 'filed'})
    v.set_message_danger(m, 'Wants Alex to sign in on a look-alike page.', 'owner')
    with mock.patch.object(config, 'load', return_value={'cli_connections': {'aiprovider-cli': {}, 'other-cli': {}}}): yield v
    v.close()


def test_the_genuine_mail_is_verified_and_from_an_organisation_alex_hears_from(s):
    c = senders.sender_check(s, REAL)
    assert c['from_domain'] == 'mail.aiprovider.example' and c['from_verified'].startswith('pass')
    assert c['earlier_mail_from_this_organisation'] == 1, 'the billing receipt from the same organisation counts'
    assert c['ai_tools_set_up_here'] == ['aiprovider-cli', 'other-cli']


def test_a_look_alike_has_no_history_and_no_verification(s):
    c = senders.sender_check(s, LOOK)
    assert c['earlier_mail_from_this_organisation'] == 0, 'mail once read as danger vouches for nobody'
    assert c['from_verified'].startswith('not checked')
    assert senders.sender_check(s, FORGED)['from_verified'].startswith('FAILED')


def test_the_organisation_is_the_domain_under_the_mail_host():
    assert senders.org_domain('mail.aiprovider.example') == 'aiprovider.example'
    assert senders.org_domain('aiprovider-login.example') == 'aiprovider-login.example'
    assert senders.org_domain('mail.vendor.co.uk') == 'vendor.co.uk'


def test_a_sign_in_started_here_moments_ago_is_said(s):
    assert 'owner_started_a_sign_in' not in senders.sender_check(s, REAL)
    s.audit('terminal', 1, 'cli_setup', 'owner', detail={'name': 'aiprovider-cli', 'sid': 'x'})
    later = datetime.now() + timedelta(minutes=3)
    assert senders.sender_check(s, REAL, now=later)['owner_started_a_sign_in'].startswith('aiprovider-cli, 3 minutes ago')
    assert 'owner_started_a_sign_in' not in senders.sender_check(s, REAL, now=datetime.now() + timedelta(hours=2))


def test_chat_and_addressless_lines_get_none(s):
    assert senders.sender_check(s, {**REAL, 'channel': 'teams'}) == {} and senders.sender_check(s, {'channel': 'email'}) == {}


def test_ingest_hands_the_check_to_the_judge(s):
    seen = {}
    def judge(msg, **kw): seen.update(kw.get('thread') or {}); return {'intent': 'fyi', 'why': 'x'}
    with mock.patch.object(ingest, 'classify_intent', side_effect=judge):
        ingest.judge(s, {**REAL, 'conversation_id': 'c1'}, llm=lambda *a, **k: '{}')
    assert seen['sender_check']['from_verified'].startswith('pass') and seen['sender_check']['earlier_mail_from_this_organisation'] == 1


def _prompt(msg, thread, system='Judge it. JSON only: {"intent": "...", "danger": null}'):
    seen = {}
    def llm(sy, u, **k): seen.update(sys=sy, usr=json.loads(u)); return json.dumps({'intent': 'fyi', 'why': 'w', 'title': 't', 'summary': 's'})
    triage.classify_intent(msg, llm=llm, system=system, thread=thread)
    return seen


def test_the_model_reads_the_facts_and_what_they_mean(s):
    real, look = (_prompt(m, {'sender_check': senders.sender_check(s, m)}) for m in (REAL, LOOK))
    assert real['usr']['sender_check']['from_verified'].startswith('pass') and real['usr']['sender_check']['earlier_mail_from_this_organisation'] == 1
    assert look['usr']['sender_check']['earlier_mail_from_this_organisation'] == 0 and look['usr']['sender_check']['from_verified'].startswith('not')
    assert triage.FIELDS['sender_check'] in real['sys'], 'a document that never names it still explains it'
    assert '`sender_check`' in triage.SHIPPED, 'the shipped guide lists it with the other fields'


def test_the_guide_says_banners_are_no_evidence_and_a_verified_service_s_link_is_no_scam():
    g = ' '.join(triage.SHIPPED.split())
    scams = g.split('**Strangers and scams.**', 1)[1].split('##', 1)[0]
    assert 'never on the banner a mail system puts on every outside sender' in scams
    assert '`from_verified`' in scams
    assert 'fyi, no `danger`' in scams and '`owner_started_a_sign_in`' in scams
    # ...and real phishing is still named, so the exception never swallows it
    for sign in ('look-alike', 'failed verification', 'display name the domain does not belong to', 'on another domain'):
        assert sign in scams, sign
    # the danger bullet itself - the one a document that takes only the shape is handed - carries the same two sentences
    assert "A mail system's banner is no sign" in triage.DANGER
    assert 'a scam on the owner' in triage.DANGER, 'the 2026-10-30 reading of a phish on the owner stays'


def test_a_scam_on_the_owner_says_what_to_do():
    # a scam filed FYI with its warning told the owner nothing to do (the owner, 2026-11-09): the model writes it, in the danger sentence
    assert 'what the owner should do about it' in triage.DANGER and 'number or address already known' in triage.DANGER
    s = MemoryStore(); mid = s.add_message({'ExternalId': 'x1', 'Channel': 'email', 'BodyText': 'pay today', 'Status': 'filed'})
    said = 'Asks to pay invoice #4471 to new bank details. Warn accounts payable and check with Payworth on a number you already have.'
    s.set_message_danger(mid, said, 'owner')
    assert s.get_message(mid)['Danger'] == said
