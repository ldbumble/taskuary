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


def test_the_writer_names_the_files_and_the_line_never_reaches_the_draft():
    s, seen = MemoryStore(), {}
    tid, _, rid = _task(s)
    out = 'Hi Erin,\n\nHere are the accruals for the 8/31 run.\nFILES PROMISED: PTO_Accruals.xlsx, PTO_Raw.zip'
    responder.write_draft(s, tid, rid, llm=lambda system, user, **k: (seen.update(system=system), out)[1])
    rv = s.get_review(rid)
    assert 'FILES PROMISED' not in rv['DraftText'] and 'Here are the accruals' in rv['DraftText']
    assert _stored(s, rid) == {'named': ['PTO_Accruals.xlsx', 'PTO_Raw.zip']}
    assert responder.FILES in seen['system'], 'the writer is told how to say it'


def test_a_promise_without_names_is_still_a_promise():
    s = MemoryStore()
    tid, _, rid = _task(s)
    responder.write_draft(s, tid, rid, llm=lambda system, user, **k: 'Sending the sheet over now.\nFILES PROMISED: unnamed')
    assert _stored(s, rid) == {'named': []}


def test_words_about_attaching_are_not_a_promise_unless_the_writer_says_so():
    s = MemoryStore()
    tid, _, rid = _task(s)
    responder.write_draft(s, tid, rid, llm=lambda system, user, **k: 'His logins were attached to an old leftover record - fixed now.')
    assert _stored(s, rid) is None


def test_a_redraft_without_a_promise_clears_the_last_one():
    s = MemoryStore()
    tid, _, rid = _task(s)
    responder.write_draft(s, tid, rid, llm=lambda system, user, **k: 'Here it is.\nFILES PROMISED: a.xlsx')
    assert _stored(s, rid)
    responder.write_draft(s, tid, rid, llm=lambda system, user, **k: 'The numbers are in the body below.')
    assert _stored(s, rid) is None


def test_saving_the_same_text_again_keeps_the_writers_word_and_new_text_drops_it():
    s = MemoryStore()
    tid, _, rid = _task(s)
    responder.write_draft(s, tid, rid, llm=lambda system, user, **k: 'Here it is.\nFILES PROMISED: a.xlsx')
    text = s.get_review(rid)['DraftText']
    s.update_review_draft(rid, text, None)                     # a Redraft door re-saving what the writer just wrote
    assert _stored(s, rid) == {'named': ['a.xlsx']}
    s.update_review_draft(rid, 'Different words from an agent.', None, by='agent:general')
    assert _stored(s, rid) is None


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
