"""ONE EMAIL CARD (the owner, 2026-11-08: "share code as much as possible with to/cc/bcc/attach etc"): the reply draft and the agent's email
are one card - To, CC, BCC, Subject, files and body, all editable - and what the owner left on it goes out with Send, through one road
(verdicts.decide -> _deliver_review). Invented people."""
import json
from unittest import mock

from taskuary import outbound, verdicts
from taskuary.store import MemoryStore


def test_the_agents_email_goes_with_the_cc_bcc_and_subject_the_card_has():
    s = MemoryStore(); tid = s.create_task({'Title': 'Q4 review room', 'Kind': 'general', 'Status': 'open'}, 'owner')
    rid = s.add_review({'TaskId': tid, 'Kind': 'slot', 'Status': 'pending', 'DraftText': 'Hi Paula - 3pm.',
                        'Deliver': json.dumps({'channel': 'email', 'to': ['paula@northwind.example'], 'cc': [], 'subject': 'Q4 review'})})
    seen = {}
    def sent(store, ch, to, subject, body, cc=None, bcc=None, **k):
        seen.update(to=to, subject=subject, cc=cc, bcc=bcc); return {'channel': 'email', 'to': to, 'cc': cc or []}
    with mock.patch.object(outbound, 'send_out', side_effect=sent):
        out = verdicts.decide(s, s.get_review(rid), 'approve', 'Hi Paula - 3pm.', cc=['gail@northwind.example'],
                              bcc=['ray@northwind.example'], subject='Q4 review moved to 3pm')
    assert out['ok'], out
    assert seen == {'to': ['paula@northwind.example'], 'subject': 'Q4 review moved to 3pm', 'cc': ['gail@northwind.example'],
                    'bcc': ['ray@northwind.example']}


def test_a_reply_goes_with_its_bcc_and_a_changed_subject():
    s = MemoryStore(); tid = s.create_task({'Title': 'answer Erin', 'Kind': 'general', 'Status': 'open'}, 'owner')
    mid = s.add_message({'TaskId': tid, 'ExternalId': 'graph:E1', 'Channel': 'email', 'SourceName': 'alex@northwind.example',
                         'FromEmail': 'erin@northwind.example', 'Subject': 'Friday', 'BodyText': 'Can you make Friday?', 'Status': 'routed'})
    rid = s.add_review({'TaskId': tid, 'MessageId': mid, 'Kind': 'draft_reply', 'Status': 'pending', 'DraftText': 'Yes, Friday works.'})
    seen = {}
    def sent(store, msg, body, to=None, cc=None, attachments=None, bcc=None, subject=None):
        seen.update(bcc=bcc, subject=subject); return {'channel': 'email', 'to': ['erin@northwind.example'], 'cc': []}
    with mock.patch.object(outbound, 'reply_to_message', side_effect=sent):
        out = verdicts.decide(s, s.get_review(rid), 'approve', 'Yes, Friday works.', bcc=['gail@northwind.example'], subject='Re: Friday - confirmed')
    assert out['ok'], out
    assert seen == {'bcc': ['gail@northwind.example'], 'subject': 'Re: Friday - confirmed'}


# ── ONE LETTER TO ONE PERSON AT A TIME (the owner's live task, 2026-11-13, with invented people: he corrected the agent in the chat; it
# rewrote the reply on the thread - the sender, four people copied, files attached - and a beat later left a second, short email to the
# sender alone. Two cards for one person from one ask, and nothing on either said why) ─────────────────────────────────────────────────────
def _answered(s):
    "A mail from Erin with three people copied, and the agent's reply to it waiting for Send: (task, the mail, the reply)."
    from taskuary import slots
    s.set_setting('owner_email', 'alex@northwind.example', 't')
    tid = s.create_task({'Title': 'Portal access for the auditors', 'Kind': 'general', 'Status': 'open'}, 'owner')
    mid = s.add_message({'TaskId': tid, 'ExternalId': 'graph:P1', 'Channel': 'email', 'SourceName': 'alex@northwind.example', 'FromName': 'Erin Blake',
                         'FromEmail': 'erin@vendor.example', 'Subject': 'Portal access', 'BodyText': 'Can you send the files and a login?', 'Status': 'routed'})
    rid = s.add_review({'TaskId': tid, 'MessageId': mid, 'Kind': 'draft_reply', 'Status': 'pending', 'DraftText': 'Hi Erin - the files are attached.',
                        'Deliver': json.dumps({'kind': 'reply', 'mode': 'reply_all', 'to': ['erin@vendor.example'], 'cc': ['gail@northwind.example', 'ray@northwind.example']})})
    return tid, mid, rid


def test_a_second_letter_to_the_person_the_reply_goes_to_is_folded_in_or_says_why_it_stands_apart():
    from taskuary import slots
    s = MemoryStore(); tid, mid, rid = _answered(s)
    cards = lambda: [(r['Kind'], r['Status']) for r in s._rows("SELECT Kind, Status FROM review WHERE TaskId=? ORDER BY ReviewId", (tid,))]
    # the live call: a new email to the sender alone, while the reply to her waits - by her address, and by her name as an agent writes it
    for to in ('erin@vendor.example', 'Erin Blake <erin@vendor.example>'):
        out = slots.draft(s, tid, 'Hi Erin - your login is in the portal invite.', to=to, subject='Your login', agent='assistant')
        assert not out['ok'] and 'second letter to the same person' in out['why'] and 'apart' in out['why'], out
    assert cards() == [('draft_reply', 'pending')] and not slots.open_(s, tid)                         # nothing was filed, no slot was added
    # ...someone the reply does NOT go to is an email of its own, as ever (a person copied on it too: copied is not written to)
    assert slots.draft(s, tid, 'Paula - please add Erin to the portal.', to='paula@northwind.example', subject='Portal seat', agent='assistant')['ok']
    # ...and where it must be a letter of its own, the agent says why and the card carries it for the owner
    out = slots.draft(s, tid, 'Hi Erin - your login is in the portal invite.', to='erin@vendor.example', subject='Your login', agent='assistant',
                      apart='The login is for Erin alone; Gail and Ray are copied on the reply.')
    assert out['ok'], out
    assert 'apart from the reply - The login is for Erin alone' in s.get_review(out['review_id'])['Reason']
    # ...the owner's own email to her is his to write: never refused
    assert slots.draft(s, tid, 'Erin - call me.', to='erin@vendor.example', subject='Call', agent='owner')['ok']


def test_a_reply_saved_beside_an_email_to_the_same_person_tells_its_agent_there_are_two():
    "The other order: the email first, then the reply to the same person - the reply is saved, and its agent hears there are two letters."
    from taskuary import slots, wrapup
    s = MemoryStore(); tid, mid, rid = _answered(s); s.decide_review(rid, 'closed_unsent', None, 'agent', note='test: no reply yet')
    first = slots.draft(s, tid, 'Hi Erin - your login is in the portal invite.', to='erin@vendor.example', subject='Your login', agent='assistant')
    assert first['ok'], first
    out = wrapup.agent_reply(s, tid, 'Hi Erin - the files are attached, and your login is in the portal invite.', 'assistant')
    assert out['ok'] and f"rv{first['review_id']}" in out['two_letters_to_one_person'], out
    # ...not once that email says why it stands apart
    s.update_review_reason(first['review_id'], f"assistant wrote this email - approve to send ({slots.APART}for Erin alone)")
    assert not slots.also_waiting(s, tid, ['erin@vendor.example'])


def test_a_new_email_to_someone_whose_earlier_one_went_is_a_new_letter_never_could_not_add():
    """Recorded on the real CLI, 2026-11-13: an email to Paula had gone; a second ask joined the task and the owner asked for another to her.
    Every try came back "could not add an email" - what was sent is not owed again - and the agent told him it "would not save, though I
    tried four ways". That rule is for what triage LISTS; an email its agent or the owner writes now is a new letter."""
    from taskuary import slots
    s = MemoryStore(); s.set_setting('owner_email', 'alex@northwind.example', 't')
    tid = s.create_task({'Title': 'Portal seats', 'Kind': 'general', 'Status': 'open'}, 'owner')
    first = slots.draft(s, tid, 'Paula - please add Erin to the portal.', to='paula@northwind.example', subject='Portal seat', agent='assistant')
    s.decide_review(first['review_id'], 'approved', None, 'owner'); slots.settled(s, s.get_review(first['review_id']), True, 'owner')
    assert not slots.open_(s, tid)
    again = slots.draft(s, tid, 'Paula - and Ray too, please.', to='paula@northwind.example', subject='One more seat', agent='assistant')
    assert again['ok'] and again['review_id'] != first['review_id'] and again['slot'] != first['slot'], again
    assert [i['out']['to'] for i in slots.open_(s, tid)] == ['paula@northwind.example']
    # ...while triage listing her again adds nothing: what was sent is not owed twice
    assert slots.add(s, tid, [{'to': 'paula@northwind.example', 'about': 'the seat', 'kind': 'email'}], 'triage') == []
