"""Came from on a task made from the owner's own promise (the owner, 2026-10-26: "need more info where this came from? what sent
email/message/chat etc"). The promise was made in a sent mail that already sits on its thread's task, so task_for_promise could not
link it and the card read only "from email · made 3d ago". The task names it in SourceRef; the page shows it and the thread around it."""
from taskuary.store import MemoryStore


def _thread(s, n_after=1):
    thread = s.create_task({'Title': 'Firewall allow-list for the portal', 'Kind': 'task', 'Status': 'open'}, 'router')
    add = lambda i, **m: s.add_message({'TaskId': thread, 'ExternalId': f'fw-{thread}-{i}', 'ConversationId': f'email:fw-{thread}',
                                        'Channel': 'email', 'Subject': 'Firewall allow-list', **m})
    ask = add(1, FromName='Erin Blake', FromEmail='erin@vendor.example', SentAt='2026-10-22 15:18:05', BodyText='Which IPs will you call from?')
    sent = add(2, FromName='Alex Doyle', FromEmail='alex@northwind.example', Status='context', Direction='out',
               SentAt='2026-10-22 17:30:56', BodyText="I'll send you the source IPs tomorrow.")
    later = [add(3 + i, FromName='Erin Blake', FromEmail='erin@vendor.example', SentAt=f'2026-10-22 17:4{i}:00', BodyText='Thanks!')
             for i in range(n_after)]
    return thread, ask, sent, later


def test_a_promise_task_shows_the_sent_mail_and_its_thread_without_taking_them():
    s = MemoryStore()
    thread, ask, sent, later = _thread(s)
    tid = s.task_for_promise(sent, 'send the source IPs', None)
    assert s.get_message(sent)['TaskId'] == thread                      # the thread's task keeps its mail
    assert [m['MessageId'] for m in s.made_from(s.get_task(tid))] == [ask, sent, *later]   # oldest first, the promise in its place


def test_the_window_is_bounded_around_the_promise():
    s = MemoryStore()
    thread, ask, sent, later = _thread(s, n_after=9)
    tid = s.task_for_promise(sent, 'send the source IPs', None)
    assert [m['MessageId'] for m in s.made_from(s.get_task(tid), before=1, after=2)] == [ask, sent, *later[:2]]


def test_a_task_made_from_nothing_shows_nothing_extra():
    s = MemoryStore()
    assert s.made_from(s.get_task(s.create_task({'Title': 'Typed by hand', 'Kind': 'task'}, 'owner'))) == []
    assert s.made_from({'SourceRef': 'promise:99999'}) == []
    assert s.made_from({'SourceRef': 'https://example.com/x'}) == []


def test_an_advisor_idea_on_a_closed_tasks_mail_shows_that_mail():
    s = MemoryStore()
    thread, ask, sent, later = _thread(s)
    iid = s.cx.execute("INSERT INTO idea (Key, Kind, Text, MessageId) VALUES ('idea:fw', 'chase', 'Erin waits on the IPs', ?)", (ask,)).lastrowid
    tid = s.create_task({'Title': 'Send Erin the IPs', 'Kind': 'task', 'Source': 'assistant', 'SourceRef': f'assistant:idea:{iid}'}, 'assistant')
    assert [m['MessageId'] for m in s.made_from(s.get_task(tid))] == [ask, sent, *later]
    s.cx.execute("UPDATE message SET Channel='assistant' WHERE MessageId=?", (ask,))
    assert s.made_from(s.get_task(tid)) == []                           # the Advisor's own line is not a source


def test_the_task_page_lists_it_under_earlier():
    from fastapi.testclient import TestClient
    from taskuary import server
    s = server.store
    thread, ask, sent, later = _thread(s)
    tid = s.task_for_promise(sent, 'send the source IPs', None)
    d = TestClient(server.app).get(f'/api/tasks/{tid}').json()
    assert d['messages'] == [] and [m['MessageId'] for m in d['earlier']] == [ask, sent, *later]
    assert s.get_message(sent)['TaskId'] == thread
