"""Whether a draft promises a file is its WRITER's word, kept on the review - never a word list over the text (the owner, 2026-10-28).

The card warned "this draft mentions an attachment and nothing is attached" off a regex: it called "his logins were attached to an old
record" a promise. Now the drafter ends a reply that says a file rides with it with responder.FILES and the names; the line is taken
off the draft and stored on the review (FilesPromised), which the card reads. Every model here is a stub; every person invented.
"""
import json, os, tempfile
os.environ.setdefault('TASKUARY_HOME', tempfile.mkdtemp(prefix='tq-files-promised-'))

from taskuary import responder
from taskuary.store import MemoryStore


def _task(s, channel='email'):
    tid = s.create_task({'Title': 'PTO accruals for payroll', 'Summary': 's', 'Kind': 'reply', 'Source': channel}, 'router')
    mid = s.add_message({'TaskId': tid, 'Channel': channel, 'FromName': 'Erin Blake', 'FromEmail': 'erin@northwind.example', 'ConversationId': 'c-7',
                         'Subject': 'PTO accruals', 'SentAt': '2026-10-19 10:00:00', 'BodyText': 'Can you send the accrual files?', 'Status': 'routed'})
    rid = s.add_review({'TaskId': tid, 'MessageId': mid, 'Kind': 'draft', 'Status': 'pending'})
    return tid, mid, rid


def _stored(s, rid):
    fp = (s.get_review(rid) or {}).get('FilesPromised')
    return json.loads(fp) if fp else None







def test_a_reply_with_no_task_carries_the_word_too():
    s = MemoryStore()
    mid = s.add_message({'Channel': 'teams', 'FromName': 'Ray Colton', 'FromEmail': 'ray@northwind.example', 'ConversationId': 'teams:1',
                         'Subject': 'deck', 'SentAt': '2026-10-19 10:00:00', 'BodyText': 'got the deck?', 'Status': 'routed'})
    rid = s.add_review({'MessageId': mid, 'Kind': 'draft', 'Status': 'pending'})
    responder.draft_for_message(s, s.get_message(mid), rid, llm=lambda system, user, **k: 'Yes, here it is.\nFILES PROMISED: Q3_deck.pptx')
    assert _stored(s, rid) == {'named': ['Q3_deck.pptx']}
    assert 'FILES PROMISED' not in s.get_review(rid)['DraftText']


def test_files_said_reads_only_the_writers_last_line():
    assert responder.files_said('One.\nTwo.') == ('One.\nTwo.', None)
    assert responder.files_said('Body\nfiles promised: x.pdf') == ('Body', ['x.pdf'])
    assert responder.files_said('FILES PROMISED: x.pdf\nmore words') == ('FILES PROMISED: x.pdf\nmore words', None)
