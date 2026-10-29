"""THE WRITER'S NEEDS IS WORK, NOT A FAILURE (walk 2026-10-29): a reply writer that said what it needs was kept as a DraftError - the card
drew a red app failure cut mid-word at 240/300 characters, and the Advisor lit "New task to fix this". Now it is kept on its own
(DraftNeeds), whole, the card says it as a plain line, and the rule lights Continue / Send to agent."""
from unittest import mock

from taskuary import advisor, ingest, responder, rulebook
from taskuary.store import MemoryStore, by_sentence
from taskuary.testing import Factory

LONG = ('NEEDS: the October invoice run from the billing export, to see why the total moved by four hundred against September; '
        'and the credit note Gail Moreno raised last week, because the customer counts it twice. Both sit in the finance share, '
        'and neither is in the thread, so nothing here can settle the number they are asking about.')


def reply_with_needs(s, said=LONG):
    f = Factory(s)
    tid = f.task(title='October invoice', kind='reply')
    mid = f.message(tid, from_email='erin@northwind.example', from_name='Erin Blake', subject='October invoice',
                    body='Why did the October total go up?')
    rid = f.review(tid, mid)
    with mock.patch.object(responder, 'write_draft', side_effect=lambda *a, **k: responder._answer(lambda *a, **k: said, 's', 'u', 100)), \
         mock.patch.object(ingest, 'hand_reply_to_agent', return_value=False):
        ingest._auto_draft(s, tid, rid)
    return tid, rid


def test_it_is_kept_whole_as_needs_never_as_a_failure():
    s = MemoryStore(); tid, rid = reply_with_needs(s)
    rv = s.get_review(rid)
    assert not rv.get('DraftError') and rv['DraftNeeds'].startswith('not drafted - it needs the October invoice run')
    assert 'nothing here can settle the number they are asking about' in rv['DraftNeeds']          # never cut at 240
    assert advisor.failure(s, {'tid': tid, 'rid': rid}) is None
    assert not [o for o in s.operations_for(tid, []) if o.get('Status') == 'error']


def test_the_rule_lights_send_to_agent_or_continue_and_says_nothing_the_card_shows():
    s = MemoryStore(); tid, rid = reply_with_needs(s)
    item = {'tid': tid, 'rid': rid, 'kind': 'asked', 'key': f'task:{tid}'}
    verbs = [{'verb': v} for v in ('reply', 'regular_agent', 'mine', 'next')]
    got = rulebook.decide(s, item, verbs)
    assert (got['state'], got['verb'], got['line']) == ('needs_agent', 'regular_agent', '')
    assert rulebook.decide(s, item, verbs + [{'verb': 'continue'}])['verb'] == 'continue'
    assert 'new_task' not in {v['verb'] for v in advisor.offered(s, item)}


def test_a_draft_written_after_clears_it():
    s = MemoryStore(); tid, rid = reply_with_needs(s)
    s.update_review_draft(rid, 'Hi Erin,\n\nThe credit note was counted twice; corrected.', None)
    assert not s.get_review(rid).get('DraftNeeds')


def test_a_redraft_that_needs_answers_plainly_not_with_a_422():
    from taskuary import server
    s = MemoryStore(); tid, rid = reply_with_needs(s)
    with mock.patch.object(server, 'store', s), mock.patch.object(server, '_refresh_chat_context'), \
         mock.patch.object(server.responder, 'write_draft', side_effect=responder.NotDrafted('not drafted - it needs the credit note. An agent can work it out')):
        out = server.draft_review(rid)
    assert out['ok'] is False and out['draft'] == '' and out['needs'].endswith('An agent can work it out')
    assert s.get_review(rid)['DraftNeeds'].startswith('not drafted - it needs the credit note')


def test_a_long_reason_is_cut_at_a_sentence_never_mid_word():
    s = ' '.join(['The export failed on the third sheet.'] * 40)
    out = by_sentence(s, 300)
    assert len(out) <= 300 and out.endswith('sheet.')
    assert by_sentence('short one', 300) == 'short one'
    assert by_sentence('word ' * 100, 50).endswith('…') and not by_sentence('word ' * 100, 50).endswith('wo…')
