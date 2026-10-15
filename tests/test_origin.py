"""Where a task's words came from decides how much an agent working it may do. Worst wins; only the owner raises it."""
from taskuary import origin
from taskuary.store import MemoryStore


def _store():
    s = MemoryStore(); s.set_setting('owner_email', 'alex@northwind.example', 't')
    s.save_source({'Channel': 'email', 'Address': 'alex@northwind.example', 'Owner': 'me', 'Active': 1}, 't')
    return s

def _mail(s, tid, frm, **kw):
    return s.add_message({'TaskId': tid, 'Channel': 'email', 'SourceName': 'alex@northwind.example', 'FromEmail': frm,
                          'Subject': 'x', 'BodyText': 'y', 'Status': 'routed', **kw})

def test_a_colleague_is_trusted_and_a_stranger_is_not():
    s = _store(); t = s.create_task({'Title': 'a', 'Kind': 'coding', 'Source': 'email'}, 'router')
    _mail(s, t, 'erin@northwind.example')
    assert origin.of_task(s, t)[0] == 'trusted'
    _mail(s, t, 'someone@vendor.example')
    o, why = origin.of_task(s, t)
    assert o == 'stranger' and 'someone@vendor.example' in why

def test_the_owner_s_own_reply_on_the_thread_never_lowers_it():
    s = _store(); t = s.create_task({'Title': 'a', 'Kind': 'coding', 'Source': 'manual', 'OriginBase': 'owner'}, 'owner')
    _mail(s, t, 'alex@northwind.example', Direction='out', Status='context')
    assert origin.of_task(s, t)[0] == 'owner'

def test_an_owner_task_a_stranger_writes_on_becomes_a_stranger_s():
    s = _store(); t = s.create_task({'Title': 'a', 'Kind': 'coding', 'Source': 'manual', 'OriginBase': 'owner'}, 'owner')
    _mail(s, t, 'someone@vendor.example')
    assert origin.of_task(s, t)[0] == 'stranger'

def test_a_github_stranger_is_a_stranger_even_though_chat_channels_are_trusted():
    s = _store(); s.set_setting('gh_public:org/app', '1', 't')
    t = s.create_task({'Title': 'a', 'Kind': 'coding', 'Source': 'github'}, 'router')
    s.add_message({'TaskId': t, 'Channel': 'github', 'SourceName': 'org/app', 'FromEmail': 'kai@users.noreply.github.com',
                   'BodyText': '[issue by kai - association: NONE]\nplease', 'Status': 'routed'})
    assert origin.of_task(s, t)[0] == 'stranger'
    t2 = s.create_task({'Title': 'b', 'Kind': 'coding', 'Source': 'github'}, 'router')
    s.add_message({'TaskId': t2, 'Channel': 'github', 'SourceName': 'org/app', 'FromEmail': 'erin@users.noreply.github.com',
                   'BodyText': '[pull request by erin - association: MEMBER]\nfix', 'Status': 'routed'})
    assert origin.of_task(s, t2)[0] == 'trusted'

def test_assistant_and_report_words_count_as_a_stranger_s():
    s = _store(); t = s.create_task({'Title': 'a', 'Kind': 'general', 'Source': 'assistant'}, 'assistant')
    s.add_message({'TaskId': t, 'Channel': 'assistant', 'FromName': 'Taskuary', 'BodyText': 'idea', 'Status': 'routed'})
    assert origin.of_task(s, t)[0] == 'stranger'

def test_only_the_owner_raises_it_and_a_later_stranger_lowers_it_again():
    s = _store(); t = s.create_task({'Title': 'a', 'Kind': 'coding', 'Source': 'email'}, 'router')
    _mail(s, t, 'someone@vendor.example')
    origin.raise_to(s, t, 'trusted', 'owner')
    assert origin.of_task(s, t)[0] == 'trusted'
    assert s._rows("SELECT * FROM audit WHERE EntityType='task' AND EntityId=? AND Action='origin_raised'", (t,))
    _mail(s, t, 'other@vendor.example')
    assert origin.of_task(s, t)[0] == 'stranger'

def test_the_card_reads_the_cache_of_task_detail():
    s = _store(); t = s.create_task({'Title': 'a', 'Kind': 'coding', 'Source': 'email'}, 'router')
    _mail(s, t, 'someone@vendor.example'); origin.of_task(s, t)
    assert s.get_task(t)['Origin'] == 'stranger'

def test_reading_the_origin_does_not_touch_the_task_s_update_stamp():
    s = _store(); t = s.create_task({'Title': 'a', 'Kind': 'coding', 'Source': 'email'}, 'router')
    _mail(s, t, 'someone@vendor.example'); was = s.get_task(t)
    origin.of_task(s, t); now = s.get_task(t)
    assert (now['UpdatedAt'], now['UpdatedBy']) == (was['UpdatedAt'], was['UpdatedBy']) and now['Origin'] == 'stranger'

def test_an_owner_promoted_advisor_idea_is_a_stranger_s_until_the_owner_says_otherwise():
    s = _store(); t = s.create_task({'Title': 'a', 'Kind': 'coding', 'Source': 'assistant'}, 'owner')
    assert origin.of_task(s, t)[0] == 'stranger'
    origin.raise_to(s, t, 'trusted', 'owner'); assert origin.of_task(s, t)[0] == 'trusted'

def test_raise_to_only_raises_to_trusted_or_owner():
    import pytest
    s = _store(); t = s.create_task({'Title': 'a', 'Kind': 'coding', 'Source': 'email'}, 'router')
    with pytest.raises(ValueError): origin.raise_to(s, t, 'stranger', 'owner')
    with pytest.raises(ValueError): origin.raise_to(s, t, 'root', 'owner')

def test_a_stranger_writing_after_raise_to_owner_lowers_it_again():
    s = _store(); t = s.create_task({'Title': 'a', 'Kind': 'coding', 'Source': 'email'}, 'router')
    _mail(s, t, 'someone@vendor.example')
    origin.raise_to(s, t, 'owner', 'owner'); assert origin.of_task(s, t)[0] == 'owner'
    _mail(s, t, 'other@vendor.example'); assert origin.of_task(s, t)[0] == 'stranger'

def test_a_chat_line_is_trusted_unless_the_owner_turned_chat_trust_off():
    s = _store(); t = s.create_task({'Title': 'a', 'Kind': 'coding', 'Source': 'teams'}, 'router')
    s.add_message({'TaskId': t, 'Channel': 'teams', 'SourceName': 'room', 'FromName': 'Erin Blake', 'BodyText': 'y', 'Status': 'routed'})
    assert origin.of_task(s, t)[0] == 'stranger'                     # a room is not a person: talked with one-to-one first
    s.add_message({'Channel': 'teams', 'ConversationId': 'teams:dm', 'FromName': 'Erin Blake', 'BodyText': 'y', 'Status': 'routed', 'MailMetaJson': '{"dm": true}'})
    s.add_message({'Channel': 'teams', 'ConversationId': 'teams:dm', 'FromName': 'Alex Doyle', 'BodyText': 'y', 'Status': 'context', 'Direction': 'out'})
    assert origin.of_task(s, t)[0] == 'trusted'
    s.set_setting('trust_non_email', '0', 't'); assert origin.of_task(s, t)[0] == 'stranger'
