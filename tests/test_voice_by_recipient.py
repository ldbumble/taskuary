"""HOW THE OWNER WRITES TO EACH PERSON (phase C, 2026-10-23): STYLE.md's "By recipient" is the drafter's memory. A voice lesson was
learned into LEARNED.md, which no drafter reads, and a Redraft's typed instruction was used once and thrown away - the owner: the
instruction is stored and remembered, and the second time for the same person it becomes a style line; no chips."""
from unittest import mock
from taskuary import byrecipient, responder
from taskuary.store import MemoryStore


def test_the_drafter_reads_the_voice_lessons_for_whom_it_writes_to():
    s = MemoryStore()
    byrecipient.add(s, 'erin@northwind.example', 'No greeting line; answer first.')
    byrecipient.add(s, 'vendor.example', 'Formal, with the invoice number in the first line.')
    byrecipient.add(s, 'everyone', 'Never more than five sentences.')
    tid = s.create_task({'Title': 'Totals', 'Kind': 'reply', 'Source': 'email'}, 'test')
    s.add_message({'TaskId': tid, 'ExternalId': 'v1', 'Channel': 'email', 'Subject': 'Q3 totals', 'FromEmail': 'erin@northwind.example',
                   'BodyText': 'Can you send the Q3 totals?', 'Status': 'routed'})
    seen = {}
    responder.draft_reply(s, tid, llm=lambda sys_, usr, **k: (seen.update(p=sys_), 'ok')[1])
    p = seen['p']
    assert 'No greeting line' in p and 'Never more than five sentences' in p and 'invoice number' not in p
    assert p.index('No greeting line') < p.index('Never more than five sentences'), 'this person first, then everyone'
    assert 'No greeting line' not in responder.style_doc(s), "one person's line never rides the whole document into every reply"


def test_a_redraft_instruction_said_twice_for_one_person_becomes_their_style_line():
    s = MemoryStore()
    def said(n, who, words):
        mid = s.add_message({'ExternalId': f'rd{n}', 'Channel': 'email', 'Subject': 's', 'FromEmail': who, 'BodyText': 'b', 'Status': 'filed'})
        rid = s.add_review({'MessageId': mid, 'Kind': 'draft', 'Status': 'pending'})
        s.add_review_instruction(rid, words)                                     # kept on the review (phase B)
        return byrecipient.note_instruction(s, rid, words)
    assert said(1, 'ray@northwind.example', 'Make it shorter.') == ''
    assert said(2, 'gail@northwind.example', 'make it shorter') == '', 'another person is another count'
    assert said(3, 'ray@northwind.example', 'make it  SHORTER') == 'make it SHORTER'
    assert [w for w, _ in byrecipient.lines(s)] == ['ray@northwind.example']
    assert said(4, 'ray@northwind.example', 'Make it shorter.') == '', 'one line, never written twice'


def test_the_redraft_door_keeps_the_instruction():
    from fastapi.testclient import TestClient
    from taskuary import server
    c = TestClient(server.app)
    mid = server.store.add_message({'ExternalId': 'redraft-door-1', 'Channel': 'email', 'Subject': 'Q3', 'FromEmail': 'omar@northwind.example',
                                    'BodyText': 'Numbers?', 'Status': 'filed'})
    with mock.patch.object(responder, 'draft_for_message', return_value='Here they are.'):
        for _ in range(2): c.post(f'/api/messages/{mid}/reply', json={'draft': True, 'redraft': True, 'instruction': 'Drop the sign-off'})
    assert ('omar@northwind.example', 'Drop the sign-off') in byrecipient.lines(server.store)
