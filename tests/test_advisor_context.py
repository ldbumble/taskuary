"""The Advisor's prompt carries the item's whole context (the deep dive, 2026-10-20): the draft and what is attached, the last messages
on the thread, the task's dates, other open tasks that may be the same ask, the owner's notes on the sender, the head of SOUL.md and
JOB.md, the playbook - and nothing empty (a LEARNED.md heading with nothing learned under it), all under one stated cap."""
import json
from datetime import datetime, timedelta
import pytest
from taskuary import advisor, funnel, terminal
from taskuary.store import MemoryStore
from taskuary.testing import Factory

ERIN = ('Erin Blake', 'erin@northwind.example')


@pytest.fixture
def s(monkeypatch):
    s = MemoryStore(); s.set_setting('calendar_enabled', '0', 'test')
    monkeypatch.setattr(terminal, 'live_sessions', lambda tail=0: [])
    monkeypatch.setattr(funnel, '_agenda', lambda _s, **kw: [])
    funnel.invalidate(); yield s; funnel.invalidate(); s.cx.close()


def ago(h): return (datetime.now() - timedelta(hours=h)).strftime('%Y-%m-%d %H:%M:%S')


def asked(s, title, body, h=2, who=ERIN, cid=None, **task):
    f = Factory(s)
    tid = f.task(title=title, status='open', kind='reply', **task)
    mid = f.message(task_id=tid, subject=title, body=body, from_name=who[0], from_email=who[1], sent_at=ago(h), conversation_id=cid or f'email:{title}')
    return tid, mid


def prompt(s, tid, item=None):
    item = item or {'key': f'task:{tid}', 'kind': 'todo', 'lane': 'yours', 'title': (s.get_task(tid) or {}).get('Title'), 'tid': tid}
    return advisor._prompt(s, advisor.SHOWN, item, [{'verb': 'reply', 'label': 'Reply'}, {'verb': 'approve', 'label': 'Send'}], 2, 'task', tid)


def test_the_draft_and_what_is_attached_are_in_the_prompt(s):
    tid, mid = asked(s, 'Invoice 4410', 'Is it paid?')
    rid = Factory(s).review(tid, mid, draft='It goes out in Friday\'s payment run - the remittance is attached.')
    p = prompt(s, tid, {'key': f'review:{rid}', 'kind': 'review', 'lane': 'approve', 'title': 'Invoice 4410', 'tid': tid, 'rid': rid})
    assert "Friday's payment run - the remittance is attached." in p
    assert 'ATTACHED TO THE DRAFT: nothing' in p
    s._exec('UPDATE review SET Deliver=? WHERE ReviewId=?', (json.dumps({'attachments': [{'name': 'remittance.pdf'}]}), rid))
    assert 'ATTACHED TO THE DRAFT: remittance.pdf' in prompt(s, tid, {'key': f'review:{rid}', 'kind': 'review', 'tid': tid, 'rid': rid, 'title': 'x'})


def test_the_last_three_messages_are_in_it_each_bounded(s):
    tid, _ = asked(s, 'Lease renewal', 'the opening ask', h=9, cid='email:lease')
    f = Factory(s)
    for n, h in ((2, 6), (3, 4), (4, 2)):
        f.message(task_id=tid, subject='RE: Lease renewal', body=f'message {n} ' + 'x' * 900, from_name=ERIN[0], from_email=ERIN[1], sent_at=ago(h), conversation_id='email:lease')
    p = prompt(s, tid)
    assert 'THE LAST 3 MESSAGES ON IT' in p and 'message 2' in p and 'message 4' in p and 'the opening ask' not in p.split('THE LAST 3')[1].split('\n\n')[0]
    assert 'x' * 301 not in p


def test_the_tasks_dates_and_weight_are_facts_of_the_item(s):
    tid, _ = asked(s, 'Badge access', 'by Friday?', Priority='high')
    s.update_task(tid, {'DueAt': '2026-10-23', 'RemindAt': '2026-10-22 09:00:00'}, 'owner')
    item = json.loads(prompt(s, tid).split('THE ITEM: ', 1)[1].split('\n', 1)[0])
    assert (item['due'], item['priority'], item['remind me on']) == ('2026-10-23', 'high', '2026-10-22 09:00:00')


def test_another_open_task_on_the_same_sender_or_thread_is_flagged_a_possible_duplicate(s):
    one, _ = asked(s, 'Month-end close is short', 'the export and the feed disagree')
    two, _ = asked(s, 'Reconcile the export against the feed', 'can it be reconciled?')
    s.update_task(two, {'Status': 'in_progress'}, 'owner')
    other, _ = asked(s, 'Something else entirely', 'hello', who=('Ray Colton', 'ray@northwind.example'))
    p = prompt(s, one)
    dup = p.split('POSSIBLE DUPLICATES', 1)[1].split('\n\n')[0]
    assert 'Reconcile the export against the feed (same sender) - an agent is on it' in dup
    assert 'Something else entirely' not in dup and 'Month-end close' not in dup        # never itself


def test_the_owners_notes_on_the_sender_and_the_head_of_soul_and_job_ride_along(s):
    tid, _ = asked(s, 'Lease renewal', 'is it signed?')
    s.add_memory({'Scope': 'sender', 'ScopeKey': ERIN[1], 'Note': 'Erin handles the leases herself - answer her, never forward', 'Source': 'verdict', 'Active': 1})
    s.add_memory({'Scope': 'sender', 'ScopeKey': 'ray@northwind.example', 'Note': 'Ray is never urgent', 'Source': 'verdict', 'Active': 1})
    s.save_doc('soul', '# SOUL.md\n\nYou work for Alex Doyle.\n<!-- a comment -->\n' + 'y' * 2000, 'owner')
    s.save_doc('job', '# JOB.md\n\nAlex runs facilities for Northwind.', 'owner')
    p = prompt(s, tid)
    assert 'Erin handles the leases herself' in p and 'Ray is never urgent' not in p
    assert 'You work for Alex Doyle.' in p and 'Alex runs facilities for Northwind.' in p and 'a comment' not in p and 'y' * 601 not in p


def test_an_empty_learned_heading_is_left_out_and_a_live_one_kept(s):
    from taskuary.learn import injectable
    tid, _ = asked(s, 'x', 'y')
    s.save_doc('learned', '# LEARNED.md\n\n## Role & responsibilities\n_(nothing learned\nyet)_\n\n## Voice & style\n- Alex signs off with "Thanks, A" [s:5 | ev: rv1 | seen: 2026-10-01]\n', 'owner')
    p = prompt(s, tid)
    assert '## Voice & style' in p and 'Thanks, A' in p and 'Role & responsibilities' not in p
    s.save_doc('learned', '# LEARNED.md\n\n## Role & responsibilities\n_(nothing learned yet)_\n', 'owner')
    assert 'LEARNED' not in prompt(s, tid)


def test_the_prompt_is_bounded_and_keeps_the_item_and_its_verbs(s):
    tid, _ = asked(s, 'x', 'y')
    s.save_doc('soul', '# SOUL\n' + 'z' * 50000, 'owner')
    for n in range(30): s.add_memory({'Scope': 'global', 'Note': f'note {n} ' + 'w' * 280, 'Source': 'verdict', 'Active': 1})
    p = prompt(s, tid)
    assert len(p) <= advisor.PROMPT_CAP and p.startswith('EVENT: item.shown') and 'VERBS OFFERED: reply (Reply)' in p


def test_a_chat_line_gets_the_same_context_as_a_mail(s):
    f = Factory(s)
    tid = f.task(title='can you cover the call', status='open', kind='reply', source='whatsapp')
    for n, h in ((1, 3), (2, 2)):
        f.message(task_id=tid, channel='whatsapp', subject='can you cover the call', body=f'line {n}', from_name='Omar Keller', from_email='@omar',
                  conversation_id='whatsapp:1', sent_at=ago(h))
    rid = f.review(tid, None, draft='Yes - I will take it.')
    p = prompt(s, tid, {'key': f'review:{rid}', 'kind': 'review', 'tid': tid, 'rid': rid, 'title': 'can you cover the call', 'channel': 'whatsapp'})
    assert 'THE LAST 2 MESSAGES' in p and 'whatsapp' in p and 'Yes - I will take it.' in p
