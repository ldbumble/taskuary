"""Which standing notes bear on a message is the MODEL's word (the owner, 2026-10-28): triage is handed every note in scope, each with
its id, ranked by meaning within a budget. Its verdict was also asked to NAME the ones it applied (`notes_applied`) - an answer no
code and no screen ever read, so it is not asked for any more (2026-11-11); only the old shape, kept for one evaluation, still does.
The model and the embedder are stand-ins; the people are invented."""
import json

from taskuary import ingest, triage
from taskuary.store import MemoryStore
from tests import fake_embed
from tests.memlines import note as put_note


def _store():
    s = MemoryStore()
    for k in ('calendar_enabled', 'coding_auto_enabled'): s.set_setting(k, '0', 't')
    put_note(s, {'Scope': 'subject', 'ScopeKey': 'payworth refund request', 'Note': 'Payworth refund requests are for the AP team.',
                 'Source': 'verdict', 'Active': 1, 'CreatedBy': 'test'})
    put_note(s, {'Scope': 'sender', 'ScopeKey': 'gail@northwind.example', 'Note': 'Gail asking about the offsite is never a task.',
                 'Source': 'verdict', 'Active': 1, 'CreatedBy': 'test'})
    return s


def test_triage_is_shown_every_note_by_its_id_and_is_not_asked_which_it_applied():
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
    assert 'notes_applied' not in seen['sys'] and 'notes_applied' not in json.dumps(seen['want'])
    assert 'notes_applied' not in s.message_verdict(out['message_id'])


def test_the_old_shape_still_names_them_for_the_evaluation():
    seen = {}
    def llm(system, user, **kw):
        seen['sys'], seen['want'] = str(system), kw.get('want')
        return json.dumps({'intent': 'fyi', 'why': 'x', 'title': 't', 'summary': 's', 'notes_applied': ['lrn7', 'lrn999', 'lrn7']})
    llm.takes_want = True
    v = triage.classify_intent({'subject': 'Refund', 'body': 'Can you refund it?'}, llm=llm, lean=False,
                               notes=['[lrn7] Payworth refund requests are for the AP team.'])
    assert 'notes_applied' in seen['sys'] and 'notes_applied' in seen['want']['schema']['properties']
    assert v['notes_applied'] == ['lrn7'], v


def test_a_note_on_one_sender_leaves_the_cached_part_of_the_prompt_the_same_for_every_mail():
    """The memory is a cached block of triage's prompt (llm.stable). The lines a mail's evidence also carries were taken out of it, so a
    sender with a note had a memory of their own - billed whole again, the guide with it on a CLI (5 memories over 40 mails, 2026-11-11)."""
    s, seen = _store(), []
    def llm(system, user, **kw):
        seen.append(system); return json.dumps({'intent': 'fyi', 'why': 'scripted', 'title': 'A line', 'summary': 'A line.'})
    llm.takes_want = True
    for i, who in enumerate(('gail', 'ray')):
        ingest.ingest_message(s, {'external_id': f'c{i}', 'channel': 'email', 'from_email': f'{who}@northwind.example', 'from_name': who.title(),
                                  'subject': f'A question {i}', 'body': 'Are you joining the offsite?'}, llm=llm)
    gail, ray = seen
    assert 'Gail asking about the offsite is never a task.' in gail.rest and 'Gail asking' not in ray.rest     # the evidence is this mail's own
    assert gail.blocks == ray.blocks and any('Gail asking about the offsite' in b for b in ray.blocks)          # ...the memory is everyone's


def test_with_no_notes_shown_there_is_no_notes_applied():
    s = MemoryStore()
    for k in ('calendar_enabled', 'coding_auto_enabled'): s.set_setting(k, '0', 't')
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
