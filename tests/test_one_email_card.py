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
