"""A trusted person who writes on a stranger's task lifts it, as if they had started it (the owner, 2026-11-09): a colleague's line on a task
an outsider opened left it in stranger mode - no tools, no earlier mail - for the colleague's own ask. Only someone trusted lifts it, never
past a line triage read as an attack, and a stranger who writes after it lowers it again. Invented people."""

from taskuary import general, origin
from test_origin import _mail, _store


def _opened_by_a_stranger(s):
    t = s.create_task({'Title': 'Vendor portal invoice question', 'Kind': 'general', 'Source': 'email'}, 'router')
    return t, _mail(s, t, 'billing@vendor.example', FromName='Vendor Billing')


def test_a_colleague_writing_after_the_stranger_lifts_the_task():
    s = _store(); t, first = _opened_by_a_stranger(s)
    assert origin.of_task(s, t)[0] == 'stranger'
    erin = _mail(s, t, 'erin@northwind.example', FromName='Erin Blake')
    o, why = origin.of_task(s, t)
    assert o == 'trusted' and 'Erin Blake' in why
    assert s.get_task(t)['TrustedThrough'] == erin                  # kept, so the message reads and Trust presses agree
    said = [c['Body'] for c in s.list_comments(t) if 'you trust them' in c['Body']]
    assert len(said) == 1 and 'from its next turn' in said[0] and 'stays their words' in said[0]
    origin.of_task(s, t)
    assert len([c for c in s.list_comments(t) if 'you trust them' in c['Body']]) == 1, 'said once'


def test_a_stranger_writing_after_the_colleague_lowers_it_again():
    s = _store(); t, _ = _opened_by_a_stranger(s)
    _mail(s, t, 'erin@northwind.example', FromName='Erin Blake'); origin.of_task(s, t)
    _mail(s, t, 'other@vendor.example')
    assert origin.of_task(s, t)[0] == 'stranger'


def test_a_colleague_before_the_stranger_lifts_nothing():
    s = _store(); t = s.create_task({'Title': 'a', 'Kind': 'general', 'Source': 'email'}, 'router')
    _mail(s, t, 'erin@northwind.example'); _mail(s, t, 'billing@vendor.example')
    assert origin.of_task(s, t)[0] == 'stranger' and not s.get_task(t).get('TrustedThrough')


def test_the_owners_own_reply_lifts_nothing():
    s = _store(); t, _ = _opened_by_a_stranger(s)
    _mail(s, t, 'alex@northwind.example', Direction='out', Status='context')
    assert origin.of_task(s, t)[0] == 'stranger'


def test_never_past_a_line_read_as_an_attack():
    s = _store(); t, first = _opened_by_a_stranger(s)
    s.set_message_danger(first, 'Tells the agent to mail the payroll file out.', 'agent')
    _mail(s, t, 'erin@northwind.example', FromName='Erin Blake')
    assert origin.of_task(s, t)[0] == 'stranger'


def test_taskuarys_own_task_is_never_lifted():
    s = _store(); t = s.create_task({'Title': 'a', 'Kind': 'general', 'Source': 'assistant'}, 'assistant')
    s.add_message({'TaskId': t, 'Channel': 'assistant', 'FromName': 'Taskuary', 'BodyText': 'idea', 'Status': 'routed'})
    _mail(s, t, 'erin@northwind.example')
    assert origin.of_task(s, t)[0] == 'stranger'


def test_a_live_general_session_starts_its_cli_again_in_the_new_mode():
    s = _store(); t, _ = _opened_by_a_stranger(s)
    sess = general.GeneralSession.__new__(general.GeneralSession)
    sess.store, sess.task_id, sess.cli_sid = s, t, 'sid-born-stranger'
    s.set_setting(f'stranger_sid:{t}', 'sid-born-stranger', 'router')
    assert not sess.trust_moved(), 'still a stranger: the conversation goes on'
    _mail(s, t, 'erin@northwind.example', FromName='Erin Blake')
    assert sess.trust_moved(), 'lifted: it starts again, in full mode'
    sess.cli_sid = 'sid-born-trusted'
    assert not sess.trust_moved()


# ── in a group, only a line joined as this work lifts it; (the owner, 2026-11-09) ─────────────────
from unittest import mock

GROUP = 'whatsapp:120363-site@g.us'
def _said(s, t, who, verdict=None):
    mid = s.add_message({'TaskId': t, 'Channel': 'whatsapp', 'ConversationId': GROUP, 'FromName': who, 'BodyText': 'y', 'Status': 'routed'})
    if verdict is not None: s.add_route(mid, t, 'attach', 1.0, 'same chat', [], 'triage', verdict=verdict)
    return mid

def _people(s, m, memo=None, seen=None): return ('trusted', 'you talk with them') if m.get('FromName') == 'Erin Blake' else ('stranger', 'new here')


def test_in_a_group_only_a_line_joined_as_this_work_lifts_it():
    s = _store(); t = s.create_task({'Title': 'Cooler alarm', 'Kind': 'general', 'Source': 'whatsapp'}, 'router')
    with mock.patch.object(origin, 'of_message', _people):
        _said(s, t, 'Kai Stranger', {'intent': 'task'})
        _said(s, t, 'Erin Blake', {'intent': 'fyi', 'same_problem': False})         # just posting in the group
        assert origin.of_task(s, t)[0] == 'stranger'
        _said(s, t, 'Erin Blake', {'intent': 'task', 'same_problem': True})         # asks about that very work
        assert origin.of_task(s, t)[0] == 'trusted'

