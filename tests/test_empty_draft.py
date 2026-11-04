"""A reply draft never ends up empty without saying so, and a rewrite that brought nothing back is never reported as done.
The shape: a chat reply whose writer put its WHY line first came back as nothing - the WHY took the reply under it - and the empty
text replaced the good draft; the Assistant then said "Rewritten" over a blank box."""
from unittest import mock
import pytest
from taskuary import responder, server
from taskuary.store import MemoryStore

nl = chr(10)


def test_a_why_put_first_comes_off_alone_and_the_reply_under_it_stays():
    assert responder.why_said('WHY: Gail asked about Friday.' + nl + nl + 'Friday works for me.') == ('Friday works for me.', 'Gail asked about Friday.')
    # ...and a WHY in the middle never takes the reply's last line with it
    out = 'Hi Gail.' + nl + nl + 'WHY: she asked.' + nl + nl + 'See you Friday.'
    assert responder.why_said(out) == (out, None)
    # the WHY at the end, wrapped onto a second line, is still the WHY
    assert responder.why_said('Hi.' + nl + nl + 'WHY: one' + nl + 'two') == ('Hi.', 'one two')


def test_a_writer_that_wrote_only_its_why_is_a_failed_draft_not_an_empty_one():
    with pytest.raises(RuntimeError, match='no reply'):
        responder._answer(lambda *a, **k: 'WHY: she asked about Friday.', 's', 'u', 10)
    with pytest.raises(RuntimeError, match='no reply'):
        responder._answer(lambda *a, **k: 'WHY: one' + nl + 'FILES PROMISED: unnamed', 's', 'u', 10)


def _chat():
    s = MemoryStore(); tid = s.create_task({'Title': 'Friday plan', 'Kind': 'general', 'Status': 'open', 'Source': 'whatsapp'}, 'router')
    mid = s.add_message({'TaskId': tid, 'ExternalId': 'w1', 'ConversationId': 'whatsapp:team@g.us', 'Channel': 'whatsapp', 'SourceName': 'The Team',
                         'FromName': 'Gail Moreno', 'FromEmail': 'whatsapp:100', 'SentAt': '2026-11-04 09:00:00', 'BodyText': 'Can we meet Friday?',
                         'Status': 'routed'})
    rid = s.add_review({'TaskId': tid, 'MessageId': mid, 'Kind': 'draft_reply', 'Status': 'pending', 'Reason': "assistant's own reply from the session - approve to send"})
    s.update_review_draft(rid, 'Friday at ten works.', None, by='agent:assistant')
    return s, tid, mid, rid


def test_the_drafter_keeps_the_reply_when_the_why_came_first():
    s, tid, mid, rid = _chat()
    responder.draft_for_review(s, tid, rid, llm=lambda *a, **k: 'WHY: Gail asked for a day.' + nl + nl + 'Friday at ten, Gail.')
    r = s.get_review(rid)
    assert r['DraftText'] == 'Friday at ten, Gail.' and r['DraftWhy'] == 'Gail asked for a day.'


def test_an_empty_draft_never_replaces_good_text():
    s, tid, mid, rid = _chat()
    for empty in ('', '   ', nl + nl, None):
        assert s.update_review_draft(rid, empty, None) is False
        r = s.get_review(rid)
        assert r['DraftText'] == 'Friday at ten works.' and r['DraftBy'] == 'agent:assistant' and 'empty' in r['DraftError']
    # ...a review with no text yet says so too, and the next real draft clears the line
    r2 = s.add_review({'TaskId': tid, 'MessageId': mid, 'Kind': 'draft_reply', 'Status': 'pending'})
    s.update_review_draft(r2, ' ', None)
    assert not s.get_review(r2)['DraftText'] and 'empty' in s.get_review(r2)['DraftError']
    assert s.update_review_draft(r2, 'Friday.', None) is not False and s.get_review(r2)['DraftError'] is None


def _redraft(s, mid, wrote):
    with mock.patch.object(server, 'store', s), mock.patch.object(server, '_refresh_chat_context', lambda **k: None), \
         mock.patch('taskuary.responder.write_draft', wrote):
        return server.open_reply(mid, server.OpenReplyBody(redraft=True, instruction='say Friday at ten'))


def test_a_rewrite_that_came_back_empty_says_so_and_keeps_the_draft():
    s, tid, mid, rid = _chat()
    out = _redraft(s, mid, lambda *a, **k: '')
    assert out['changed'] is False and out['draft'] == 'Friday at ten works.' and 'empty' in out['why']
    assert s.get_review(rid)['DraftText'] == 'Friday at ten works.'


def test_a_rewrite_that_failed_says_why():
    s, tid, mid, rid = _chat()
    def boom(*a, **k): raise RuntimeError('the AI connector timed out')
    out = _redraft(s, mid, boom)
    assert out['changed'] is False and 'timed out' in out['why'] and s.get_review(rid)['DraftText'] == 'Friday at ten works.'


def test_a_rewrite_that_wrote_the_same_words_is_not_called_rewritten():
    s, tid, mid, rid = _chat()
    out = _redraft(s, mid, lambda *a, **k: 'Friday at ten works.')
    assert out['changed'] is False and out['why']


def test_a_real_rewrite_is_changed():
    s, tid, mid, rid = _chat()
    out = _redraft(s, mid, lambda *a, **k: 'Friday at ten it is, Gail.')
    assert out['changed'] is True and out['draft'] == 'Friday at ten it is, Gail.' == s.get_review(rid)['DraftText']


def test_the_card_redraft_says_whether_it_changed():
    s, tid, mid, rid = _chat()
    with mock.patch.object(server, 'store', s), mock.patch.object(server, '_refresh_chat_context', lambda **k: None), \
         mock.patch('taskuary.responder.write_draft', lambda *a, **k: ''):
        out = server.draft_review(rid, server.DraftBody(instruction='say Friday'))
    assert out['changed'] is False and out['draft'] == 'Friday at ten works.' and 'empty' in out['why']
