"""THE WRITER'S NEEDS IS WORK, NOT A FAILURE (walk 2026-10-29): a reply writer that said what it needs was kept as a DraftError - the card
drew a red app failure cut mid-word at 240/300 characters, and the Advisor lit "New task to fix this". Now it is kept on its own
(DraftNeeds), whole, the card says it as a plain line, and the rule lights Continue / Send to agent.
The writer is the owner's own press now (Draft with AI / Redraft): nothing drafts at arrival - the reply is the task's agent's."""
from unittest import mock

from taskuary import responder, rulebook
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
    from taskuary import server
    with mock.patch.object(server, 'store', s), mock.patch.object(server, '_refresh_chat_context'), \
         mock.patch.object(responder, 'draft_for_review', side_effect=lambda *a, **k: responder._answer(lambda *a, **k: said, 's', 'u', 100)):
        assert server.draft_review(rid)['ok'] is False            # the owner pressed Draft with AI: the writer said what it needs
    return tid, rid






def test_a_long_reason_is_cut_at_a_sentence_never_mid_word():
    s = ' '.join(['The export failed on the third sheet.'] * 40)
    out = by_sentence(s, 300)
    assert len(out) <= 300 and out.endswith('sheet.')
    assert by_sentence('short one', 300) == 'short one'
    assert by_sentence('word ' * 100, 50).endswith('…') and not by_sentence('word ' * 100, 50).endswith('wo…')
