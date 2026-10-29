"""What a reply answers is the newest row SOMEBODY sent (2026-10-13): an End of day checkup joined onto the task was newer than
the colleague who had written again, so the session's reply went to "nobody" and was filed as a result, and the card said
"Nobody sent this one" over a task with a person waiting."""
from taskuary import wrapup
from taskuary.store import MemoryStore
from test_funnel import ago


def _task(s):
    tid = s.create_task({'Title': 'Screening access list', 'Kind': 'coding', 'Status': 'open'}, 'owner')
    add = lambda **m: s.add_message({'TaskId': tid, 'Channel': 'email', 'SourceName': 'alex@northwind.example', 'Status': 'routed', **m})
    return tid, add


def test_a_report_joined_later_is_not_who_the_reply_answers():
    s = MemoryStore(); tid, add = _task(s)
    add(ExternalId='a', FromName='Ray Colton', FromEmail='ray@northwind.example', SentAt=ago(30), BodyText='First ask')
    add(ExternalId='b', FromName='You', FromEmail='alex@northwind.example', SentAt=ago(20), BodyText='Sent.', Status='context', Direction='out')
    again = add(ExternalId='c', FromName='Ray Colton', FromEmail='ray@northwind.example', SentAt=ago(5), BodyText='One more change')
    add(ExternalId='d', Channel='report', FromName='End of day checkup', FromEmail=None, SentAt=ago(3), BodyText='Most urgent: Ray.')
    assert wrapup.reply_target(s, tid) == again


def test_a_task_with_nobody_behind_any_row_still_names_its_newest():
    s = MemoryStore(); tid, add = _task(s)
    only = add(ExternalId='r', Channel='report', FromName='Nightly export', FromEmail=None, SentAt=ago(3), BodyText='Failed.')
    assert wrapup.reply_target(s, tid) == only


def test_a_self_forward_has_no_reply_target():
    """The owner forwarded an invite to their own address with "sign me up?": the reply drafted "Hi Alex" back to them (the email
    walk, 2026-10-29). Only the owner is behind the row, so nobody is answered."""
    s = MemoryStore(); tid, add = _task(s)
    s.set_setting('owner_email', 'alex@northwind.example', 'owner')
    add(ExternalId='f', FromName='Alex Doyle', FromEmail='Alex@Northwind.example', SentAt=ago(5), BodyText='sign me up?')
    assert wrapup.reply_target(s, tid) is None
    erin = add(ExternalId='e', FromName='Erin Blake', FromEmail='erin@vendor.example', SentAt=ago(30), BodyText='Join our webinar')
    assert wrapup.reply_target(s, tid) == erin
