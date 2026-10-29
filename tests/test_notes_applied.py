"""Which standing notes bear on a message is the MODEL's word (the owner, 2026-10-28): triage is handed every note in scope, each with
its id, ranked by meaning within a budget, and its verdict names the ones it applied - `notes_applied`, kept in route.VerdictJson.
An id it was never shown is dropped. The model and the embedder are stand-ins; the people are invented."""
import json

from taskuary import ingest, triage
from taskuary.store import MemoryStore
from tests import fake_embed
from tests.memlines import note as put_note


def _store():
    s = MemoryStore()
    for k in ('calendar_enabled', 'coding_auto_enabled', 'learn_enabled'): s.set_setting(k, '0', 't')
    put_note(s, {'Scope': 'subject', 'ScopeKey': 'payworth refund request', 'Note': 'Payworth refund requests are for the AP team.',
                 'Source': 'verdict', 'Active': 1, 'CreatedBy': 'test'})
    put_note(s, {'Scope': 'sender', 'ScopeKey': 'gail@northwind.example', 'Note': 'Gail asking about the offsite is never a task.',
                 'Source': 'verdict', 'Active': 1, 'CreatedBy': 'test'})
    return s


def test_triage_names_the_notes_it_applied_by_their_ids_and_the_verdict_keeps_them():
    s, seen = _store(), {}
    def llm(system, user, **kw):
        seen['sys'], seen['want'] = system, kw.get('want')
        ids = [triage.note_id(l[2:]) for l in system.splitlines() if l.startswith('- [lrn')]
        seen['ids'] = ids
        return json.dumps({'intent': 'fyi', 'why': 'the AP team takes these', 'title': 'Payworth refund', 'summary': 'A refund ask.',
                           'notes_applied': [ids[0], 'lrn999999999', ids[0]]})
    llm.takes_want = True
    with fake_embed.meaning({'refund': ['refund']}):
        out = ingest.ingest_message(s, {'external_id': 'n1', 'channel': 'email', 'from_email': 'gail@northwind.example', 'from_name': 'Gail Moreno',
                                        'subject': 'Refund for the Payworth overpayment', 'body': 'Can you refund the Payworth overpayment?'},
                                    llm=llm)
    assert len(seen['ids']) == 2 and all(seen['ids']), seen['sys'][-600:]
    assert 'notes_applied' in seen['sys'] and 'notes_applied' in seen['want']['schema']['properties']
    v = s.message_verdict(out['message_id'])
    assert v['notes_applied'] == [seen['ids'][0]], v


def test_with_no_notes_shown_there_is_no_notes_applied():
    s = MemoryStore()
    for k in ('calendar_enabled', 'coding_auto_enabled', 'learn_enabled'): s.set_setting(k, '0', 't')
    seen = {}
    def llm(system, user, **kw):
        seen['want'] = kw.get('want')
        return json.dumps({'intent': 'fyi', 'why': 'x', 'title': 't', 'summary': 's', 'notes_applied': ['lrn1']})
    llm.takes_want = True
    out = ingest.ingest_message(s, {'external_id': 'n2', 'channel': 'email', 'from_email': 'omar@northwind.example',
                                    'subject': 'Lunch', 'body': 'Lunch on Friday?'}, llm=llm)
    assert 'notes_applied' not in seen['want']['schema']['properties']
    assert 'notes_applied' not in s.message_verdict(out['message_id'])


def test_a_correction_on_a_topic_alike_in_meaning_is_evidence_and_one_unlike_is_not():
    from taskuary import operations
    s = MemoryStore()
    s.add_correction({'Sender': 'ray@northwind.example', 'Topic': 'payworth refund request', 'Verdict': 'task', 'Change': 'fyi',
                      'ContextJson': json.dumps({'subject': 'Payworth refund request'})})
    msg = {'from_email': 'erin@northwind.example', 'subject': 'Refund owed on the Payworth overpayment'}
    with fake_embed.meaning({'refund': ['refund']}):
        assert len(operations.evidence_lines(s, msg)) == 1
        assert operations.evidence_lines(s, {'from_email': 'erin@northwind.example', 'subject': 'Offsite agenda for Thursday'}) == []
    with fake_embed.no_embedder():
        assert operations.evidence_lines(s, msg) == [], 'no embedder: only the same sender or the very same topic'


def test_the_advisor_names_an_open_task_alike_in_meaning_as_a_possible_duplicate():
    from taskuary import advisor
    s = MemoryStore()
    a = s.create_task({'Title': 'Refund the Payworth overpayment', 'Status': 'open'}, 'owner')
    b = s.create_task({'Title': 'Payworth wants its money back', 'Summary': 'a refund for the overpayment', 'Status': 'open'}, 'owner')
    c = s.create_task({'Title': 'Book the offsite room', 'Status': 'open'}, 'owner')
    item = {'title': 'Refund the Payworth overpayment', 'key': f'task:{a}'}
    with fake_embed.meaning({'refund': ['refund']}):
        line = advisor.related_line(s, item, 'task', a)
    assert f'TQ-{b:04d}' in line and f'TQ-{c:04d}' not in line and f'TQ-{a:04d}' not in line, line


def test_note_ids_are_read_from_the_line_and_nothing_else():
    assert triage.note_id('[lrn42] Payworth refunds are for AP.') == 'lrn42'
    assert triage.note_id('Payworth refunds are for AP.') == ''
    assert triage.note_id('[draft] not a note id') == ''
