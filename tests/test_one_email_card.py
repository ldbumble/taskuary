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


# ── TWO LETTERS TO ONE PERSON ARE TWO LETTERS (the owner, 2026-11-13, with invented people: the reply on the thread went to the sender
# with others copied, and a login went to her alone - two different emails he meant to send. 0.4.0.3 refused the second as "one letter
# per person" and folded it into the reply. What was wrong was a COPY written twice, never a second letter) ──────────────────────────────
def _answered(s):
    "A mail from Erin with two people copied, and the agent's reply to it waiting for Send: (task, the mail, the reply)."
    s.set_setting('owner_email', 'alex@northwind.example', 't')
    tid = s.create_task({'Title': 'Portal access for the auditors', 'Kind': 'general', 'Status': 'open'}, 'owner')
    mid = s.add_message({'TaskId': tid, 'ExternalId': 'graph:P1', 'Channel': 'email', 'SourceName': 'alex@northwind.example', 'FromName': 'Erin Blake',
                         'FromEmail': 'erin@vendor.example', 'Subject': 'Portal access', 'BodyText': 'Can you send the files and a login?', 'Status': 'routed'})
    rid = s.add_review({'TaskId': tid, 'MessageId': mid, 'Kind': 'draft_reply', 'Status': 'pending', 'DraftText': 'Hi Erin - the files are attached.',
                        'Deliver': json.dumps({'kind': 'reply', 'mode': 'reply_all', 'to': ['erin@vendor.example'], 'cc': ['gail@northwind.example', 'ray@northwind.example']})})
    return tid, mid, rid


def test_a_separate_email_to_the_person_a_reply_goes_to_stands_as_its_own_card():
    from taskuary import slots
    s = MemoryStore(); tid, mid, rid = _answered(s)
    out = slots.draft(s, tid, 'Hi Erin - your login: user erin, host files.northwind.example.', to='Erin Blake <erin@vendor.example>', subject='Your login', agent='assistant')
    assert out['ok'], out
    cards = [(r['Kind'], r['Status']) for r in s._rows("SELECT Kind, Status FROM review WHERE TaskId=? ORDER BY ReviewId", (tid,))]
    assert cards == [('draft_reply', 'pending'), (slots.KIND, 'pending')], cards                # both wait for their own Send
    assert s.get_review(rid)['DraftText'] == 'Hi Erin - the files are attached.'                # the reply is untouched


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


def test_sending_one_letter_leaves_the_other_waiting_when_its_sent_copy_comes_back():
    """The owner, 2026-11-13: two letters waited on one task - the reply on the thread and a login to the sender alone. He pressed Send on
    one and both boxes closed. The sent copy came back from his Sent folder onto the thread, was heard as a new message, and set aside every
    draft older than it. A letter Taskuary sent on his press is no new input: the other card waits for its own Send."""
    from taskuary import conversation, slots
    s = MemoryStore(); tid, mid, rid = _answered(s)
    s._exec("UPDATE review SET CreatedAt=datetime('now','localtime','-5 minutes') WHERE ReviewId=?", (rid,))   # the reply was written first
    s._exec("UPDATE message SET CreatedAt=datetime('now','localtime','-9 minutes') WHERE MessageId=?", (mid,))  # ...to her mail, before that
    login = 'Hi Erin - your login: user erin, host files.northwind.example.'
    out = slots.draft(s, tid, login, to='erin@vendor.example', subject='Your login', agent='assistant'); assert out['ok'], out
    s.decide_review(out['review_id'], 'approved', login, 'owner'); slots.settled(s, s.get_review(out['review_id']), True, 'owner')
    s._exec("UPDATE review SET DeliveryState='sent' WHERE ReviewId=?", (out['review_id'],))
    s.add_message({'TaskId': tid, 'ExternalId': 'graph:SENT1', 'Channel': 'email', 'SourceName': 'alex@northwind.example', 'FromName': 'Alex Doyle',
                   'FromEmail': 'alex@northwind.example', 'Direction': 'out', 'Subject': 'Your login', 'BodyText': login, 'Status': 'routed'})
    conversation.hear(s, tid, turn=True)
    assert s.get_review(rid)['Status'] == 'pending', s.get_review(rid)
