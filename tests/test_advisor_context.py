"""The Advisor's prompt carries the item's whole context (the deep dive, 2026-10-20): the draft and what is attached, the last messages
on the thread, the task's dates, other open tasks that may be the same ask, the owner's notes on the sender, the head of SOUL.md and
JOB.md, the playbook - and nothing empty (a LEARNED.md heading with nothing learned under it), all under one stated cap."""
import json
from datetime import datetime, timedelta
import pytest
from taskuary import advisor, funnel, terminal
from taskuary.store import MemoryStore
from taskuary.testing import Factory
from tests.memlines import note

ERIN = ('Erin Blake', 'erin@northwind.example')


@pytest.fixture
def s(monkeypatch):
    s = MemoryStore(); s.set_setting('calendar_enabled', '0', 'test')
    monkeypatch.setattr(terminal, 'live_sessions', lambda tail=0: [])
    monkeypatch.setattr(funnel, '_agenda', lambda _s, **kw: [])
    funnel.invalidate(); yield s; funnel.invalidate(); s.close()


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
    assert (item['due'], item['priority'], item['remind me on']) == ('2026-10-23', 'important', '2026-10-22 09:00:00')   # high reads important (2026-10-25)


def test_another_open_task_on_the_same_thread_is_flagged_a_possible_duplicate_and_the_same_sender_alone_is_not(s):
    one, _ = asked(s, 'Month-end close is short', 'the export and the feed disagree', cid='email:month-end')
    two, _ = asked(s, 'Reconcile the export against the feed', 'can it be reconciled?', cid='email:month-end')
    s.update_task(two, {'Status': 'in_progress'}, 'owner')
    other, _ = asked(s, 'Something else entirely', 'hello', who=('Ray Colton', 'ray@northwind.example'))
    # the same sender asking another thing is no duplicate (the design, 2026-10-23): one person asks for many things
    lone, _ = asked(s, 'Badge access for the new AP clerk', 'can you set it up?')
    # in_progress with nothing running is a stopped or failed agent: never "an agent is on it - look again later" (2026-10-22 walk)
    dup = prompt(s, one).split('POSSIBLE DUPLICATES', 1)[1].split('\n\n')[0]
    assert 'Reconcile the export against the feed (same thread)' in dup and 'an agent is on it' not in dup
    assert 'Badge access' not in dup, 'Erin asking something else is not the same ask'
    s.start_run(two, 'assistant', 'reconcile', 'owner')
    p = prompt(s, one)
    dup = p.split('POSSIBLE DUPLICATES', 1)[1].split('\n\n')[0]
    assert 'Reconcile the export against the feed (same thread) - an agent is on it' in dup
    assert 'Something else entirely' not in dup and 'Month-end close' not in dup        # never itself
    assert 'POSSIBLE DUPLICATES' not in prompt(s, lone)


def test_the_owners_notes_on_the_sender_and_the_head_of_soul_and_job_ride_along(s):
    tid, _ = asked(s, 'Lease renewal', 'is it signed?')
    note(s, {'Scope': 'sender', 'ScopeKey': ERIN[1], 'Note': 'Erin handles the leases herself - answer her, never forward', 'Source': 'verdict', 'Active': 1})
    note(s, {'Scope': 'sender', 'ScopeKey': 'ray@northwind.example', 'Note': 'Ray is never urgent', 'Source': 'verdict', 'Active': 1})
    s.save_doc('soul', '# SOUL.md\n\nYou work for Alex Doyle.\n<!-- a comment -->\n' + 'y' * 2000, 'owner')
    s.save_doc('job', '# JOB.md\n\nAlex runs facilities for Northwind.', 'owner')
    p = prompt(s, tid)
    assert 'Erin handles the leases herself' in p and 'Ray is never urgent' not in p
    assert 'You work for Alex Doyle.' in p and 'Alex runs facilities for Northwind.' in p and 'a comment' not in p and 'y' * 601 not in p


def test_the_advisor_reads_how_the_owner_works_and_never_a_press_count(s):
    """One section per subject (the owner, 2026-10-25): the Advisor reads your people, what you care about, how you work and your
    promises - "What to bring up" is the rail's - and a press count left in an old section reaches nobody."""
    tid, _ = asked(s, 'x', 'y')
    s.save_doc('learned', '# LEARNED.md\n\n## Your people\n_(nothing\nyet)_\n- Gail Moreno (gail@northwind.example) gets the headcount questions [s:5 | ev: out1 | seen: 2026-10-01]\n\n'
                          '## What you care about\n- Vendor statements are fyi [s:5 | ev: mem1 | seen: 2026-10-01]\n\n'
                          '## What to bring up\n- Newsletter ideas are dismissed [s:5 | ev: out2 | seen: 2026-10-01]\n\n'
                          '## What you do next\n- On asks from northwind.example, Alex presses Reply (4 of 4) [s:5 | ev: pr1 | seen: 2026-10-01]\n', 'owner')
    p = prompt(s, tid)
    assert 'WHAT YOU KNOW ABOUT HOW THE OWNER WORKS' in p and 'gets the headcount questions' in p and 'Vendor statements' in p
    assert 'presses Reply' not in p and 'Newsletter ideas' not in p and 'nothing' not in p and 'from their own presses' not in p
    s.save_doc('learned', '# LEARNED.md\n\n## Your people\n_(nothing learned yet)_\n', 'owner')
    assert 'HOW THE OWNER WORKS' not in prompt(s, tid)


def test_the_prompt_is_bounded_and_keeps_the_item_and_its_verbs(s):
    tid, _ = asked(s, 'x', 'y')
    s.save_doc('soul', '# SOUL\n' + 'z' * 50000, 'owner')
    for n in range(30): note(s, {'Scope': 'global', 'Note': f'note {n} ' + 'w' * 280, 'Source': 'verdict', 'Active': 1})
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


# ── WHAT THE POP-UP ASSISTANT READS, THE ADVISOR READS (the 2026-11-02 audit) ─────────────────────────────────────────────────────────
def test_the_task_page_reaches_the_prompt_for_the_item_on_the_table(s):
    tid, _ = asked(s, 'Lease renewal', 'is it signed?', Summary='Get the Elm Street lease signed before the 30th')
    s.add_comment(tid, 'coding', 'agent', 'AGENT REPORT: the lease is with the landlord for signature')
    p = prompt(s, tid)
    assert "THE TASK'S PAGE" in p and 'Get the Elm Street lease signed before the 30th' in p and 'with the landlord for signature' in p
    tier1 = advisor._prompt(s, advisor.SHOWN, {'key': f'task:{tid}', 'kind': 'todo', 'tid': tid, 'title': 'x'}, [{'verb': 'reply', 'label': 'Reply'}], 1, 'task', tid)
    assert "THE TASK'S PAGE" not in tier1, 'the bigger read is for the item on the table'


def test_the_owners_own_words_reach_the_prompt_pane_answers_continues_and_outgoing_lines(s):
    tid, _ = asked(s, 'Vendor W-9', 'can you get their W-9?')
    s.add_worker_event({'TaskId': tid, 'Sid': 'run1', 'Kind': 'answered', 'RequestId': 'q1', 'Text': 'Use the 2025 form, not the old one', 'Source': 'owner'})
    s._exec("INSERT INTO outcome (Kind,TargetKind,TargetId,Actor,At,NextMove,FactsJson) VALUES (?,?,?,?,?,?,?)",
            ('agent.continued', 'task', tid, 'owner', ago(1), 'Ask Gail for the signed copy', '{}'))
    Factory(s).message(task_id=tid, subject='W-9', body='On it - I will send it by Friday.', direction='out', status='context', channel='whatsapp',
                       from_name='Alex Doyle', sent_at=ago(0.5), conversation_id='whatsapp:w9')
    p = prompt(s, tid)
    words = p.split("THE OWNER'S OWN WORDS ON IT", 1)[1].split('\n\n')[0]
    assert 'Use the 2025 form' in words and 'Ask Gail for the signed copy' in words and 'I will send it by Friday' in words and 'whatsapp' in words
    assert words.index('Ask Gail') < words.index('send it by Friday'), 'oldest first: the newest is the latest instruction'


def test_an_agent_task_keeps_a_bounded_tail_of_its_thread(s):
    tid, _ = asked(s, 'Lease renewal', 'the opening ask ' + 'q' * 600, h=5, cid='email:lease')
    s.add_comment(tid, 'coding', 'assistant_agent', 'I drafted the renewal summary.')
    p = prompt(s, tid)
    assert "THE THREAD BEFORE THE AGENT'S LAST TURN" in p and 'the opening ask' in p and 'q' * 201 not in p
    assert 'MESSAGES ON IT, oldest first' not in p, 'the tail, never the whole thread twice'


def test_a_promise_task_shows_the_owners_message_it_was_made_from(s):
    f = Factory(s)
    f.message(subject='', body='are you bringing the budget sheet thursday?', from_name='Gail Moreno', from_email='@gail', channel='whatsapp',
              conversation_id='whatsapp:gail', sent_at=ago(3))
    mid = f.message(subject='', body='Yes - I will bring the Q4 budget sheet Thursday', direction='out', status='context', channel='whatsapp',
                    from_name='Alex Doyle', conversation_id='whatsapp:gail', sent_at=ago(2))
    tid = s.task_for_promise(mid, 'bring the Q4 budget sheet Thursday', None)
    s._exec('UPDATE message SET TaskId=NULL WHERE MessageId=?', (mid,))       # its mail is on the thread's own task: none on the promise
    assert not s.list_messages(tid)
    p = prompt(s, tid)
    src = p.split('WHAT THIS TASK WAS MADE FROM', 1)[1].split('\n\n')[0]
    assert "the owner's own message" in src and 'I will bring the Q4 budget sheet Thursday' in src and 'are you bringing the budget sheet' in src


def test_who_the_owner_is_comes_before_the_memory_and_the_ledger_so_the_bound_drops_it_last(s):
    tid, _ = asked(s, 'x', 'y')
    s.save_doc('job', '# JOB.md\n\nAlex runs facilities for Northwind.', 'owner')
    s.save_doc('learned', '# LEARNED.md\n\n## Your people\n- Gail Moreno (gail@northwind.example) gets the headcount questions [s:5 | ev: out1 | seen: 2026-10-01]\n', 'owner')
    p = prompt(s, tid)
    assert p.index('WHO THE OWNER IS') < p.index('WHAT YOU KNOW ABOUT HOW THE OWNER WORKS')
    from taskuary import learned_cut
    assert learned_cut.BUDGET['advisor'] >= 6000 and advisor.PROMPT_CAP >= 16000
