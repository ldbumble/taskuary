"""Nothing to send is the writer's call, carried out - never an email of one signature (the owner, 2026-10-08: "it hit close with
not our task and created email with no message?"). The agent was told "not ours, no reply"; the close-out still asked for a reply,
the writer had nothing to say and signed off, and the card offered Send on the signature to six people."""
from unittest import mock

import pytest

from taskuary import learn, responder
from taskuary.store import MemoryStore
from tests.test_review_delivery_safety import make_review

SIG = 'Alex Doyle\nLead Engineer, Dept of IS\nNorthwind'


@pytest.fixture
def s():
    value = MemoryStore()
    value.set_setting('email_signature', SIG, 'test')
    yield value
    value.close()


def write(s, said, nudge=None):
    tid, mid, rid = make_review(s)
    with mock.patch.object(learn, 'learn_from'):
        out = responder.draft_for_review(s, tid, rid, llm=lambda *a, **k: said, resolution='Not ours - the owner chose no reply.', nudge=nudge)
    return tid, rid, out


@pytest.mark.parametrize('said', ['NO REPLY', 'No reply.'])
def test_the_writer_saying_nothing_goes_back_puts_the_draft_down_and_says_so(s, said):
    tid, rid, out = write(s, said)
    assert out == ''
    assert s.get_review(rid)['Status'] == 'no_reply'
    assert any('No reply drafted' in c['Body'] for c in s.list_comments(tid))


@pytest.mark.parametrize('said', ['Thanks,\nAlex', 'Thank you!', 'Cheers'])
def test_a_sign_off_word_is_not_the_writers_no_reply(s, said):
    """A sign-off word list put these down as "no reply"; a thank-you can be the whole real answer. Only the writer's
    NO_REPLY token drops a draft (the owner, 2026-10-11: "everything should be ai")."""
    tid, rid, out = write(s, said)
    assert s.get_review(rid)['Status'] == 'pending' and said.split(',')[0] in s.get_review(rid)['DraftText']


def test_a_draft_of_only_the_signature_fails_and_is_never_offered_to_send(s):
    tid, mid, rid = make_review(s)
    with mock.patch.object(learn, 'learn_from'), pytest.raises(RuntimeError, match='only your signature'):
        responder.draft_for_review(s, tid, rid, llm=lambda *a, **k: f'\n\n{SIG}', resolution='Not ours.')
    assert s.get_review(rid)['Status'] == 'pending' and SIG not in str(s.get_review(rid)['DraftText'] or '')


def test_a_real_answer_is_drafted_with_its_signature(s):
    tid, rid, out = write(s, 'Hi Erin,\n\nThe export runs again - tested this morning.\n\nThanks,')
    rv = s.get_review(rid)
    assert rv['Status'] == 'pending' and 'The export runs again' in rv['DraftText'] and rv['DraftText'].rstrip().endswith('Northwind')


def test_a_reply_the_owner_asked_for_is_never_dropped(s):
    with pytest.raises(RuntimeError):
        write(s, 'NO REPLY', nudge='tell her it is fixed')


def test_the_close_out_writer_is_told_it_may_say_so():
    assert responder.NO_REPLY in responder.DONE


@pytest.mark.parametrize('said', ['on it', 'ok', 'Will do'])
def test_a_short_real_answer_is_still_an_answer(s, said):
    tid, rid, out = write(s, said)
    assert s.get_review(rid)['Status'] == 'pending' and said in s.get_review(rid)['DraftText']
