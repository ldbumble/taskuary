"""ONE THING, ONE PLACE (railcheck.py): a message, a task, a draft or an idea is drawn on exactly one row, and a row's words are
about the row it is. An invented world with every shape that has put one thing in two places, checked as the rail builds it -
unread, and with read rows kept (what Next and a press resolve keys against)."""
import json
from datetime import datetime, timedelta
from unittest import mock

import pytest

from taskuary import assistant, funnel, ingest, processing_startup, processing_unread, railcheck, sweep
from taskuary.store import MemoryStore, task_ref
from taskuary.testing import Factory


def ago(days=0, hours=0): return (datetime.now() - timedelta(days=days, hours=hours)).strftime('%Y-%m-%d %H:%M:%S')


def build(s, **kw):
    s.reconcile_processing_membership(); funnel.invalidate()
    with mock.patch('taskuary.terminal.live_sessions', return_value=[]): return processing_unread.build(s, live_state=[], **kw)


def rails(s): return [(name, build(s, include_read=read)) for name, read in (('rail', False), ('with read rows', True))]


def clean(s):
    for name, b in rails(s):
        found = railcheck.collisions(b['items'], s, lanes=b['lanes'], ideas=name == 'rail')
        assert not found, f'{name}: {railcheck.summary(found)} {found}'


def mail(f, who, subject, conv, tid=None, days=1, status='routed'):
    return f.message(tid, status=status, subject=subject, body=f'{subject}?', from_name=who, from_email=f"{who.split()[0].lower()}@northwind.example",
                     sent_at=ago(days), conversation_id=conv, source_name='alex@northwind.example')


@pytest.fixture
def s():
    s = MemoryStore()
    for k in ('calendar_enabled', 'coding_auto_enabled'): s.set_setting(k, '0', 't')
    funnel.invalidate(); funnel.forget_states()
    processing_startup.initialize(s, live_state=[])
    return s


def test_the_checker_names_one_thing_in_two_places():
    rows = [{'key': 'processing:a', 'kind': 'fyi', 'lane': 'fyi', 'mid': 7, 'member_ids': ['message:7']},
            {'key': 'processing:b', 'kind': 'idea', 'lane': 'asked', 'idea_kind': 'unanswered', 'idea': 3, 'mid': 7, 'member_ids': ['idea:3'], 'aliases': ['task:9']},
            {'key': 'processing:c', 'kind': 'todo', 'lane': 'yours', 'tid': 9, 'member_ids': ['task:9'], 'aliases': ['task:9'],
             'why': 'same conversation thread as TQ-0009, which was closed - it reopens only on new work'}]
    found = railcheck.collisions(rows, lanes=[{'lane': 'fyi', 'n': 2}])
    assert {c['check'] for c in found} == {'idea_subject', 'alias', 'stale_reason', 'count'}, found
    assert railcheck.summary(found)['idea_subject'] == {'asked/idea/unanswered + fyi/fyi': 1}


def test_a_mixed_world_has_every_thing_in_one_place(s):
    f = Factory(s)
    # a task with two mails on its thread, a draft waiting and the Advisor's line keyed by its task
    tid = f.task(title='Renew the vendor contract')
    first = mail(f, 'Erin Blake', 'Renew the vendor contract', 'c-contract', tid, days=2)
    mail(f, 'Erin Blake', 'Re: Renew the vendor contract', 'c-contract', tid)
    f.review(tid, first, draft='Will do by Friday.')
    s.upsert_idea({'key': 'idea:contract', 'kind': 'idea', 'text': 'Erin asked twice.', 'sig': 'x', 'action': {'tid': tid}}, ago(hours=1))
    # plain FYI, a report run, a sender's ask the daily check raised once it left the rail
    f.filed_fyi(); f.report_row()
    asked = mail(f, 'Paula Vance', 'Can you send the board pack', 'c-pack', days=6, status='filed')
    s.add_route(asked, None, 'file', None, 'they ask for the board pack', [], 'triage',
                verdict={'intent': 'reply_only', 'kind': 'reply', 'why': 'they ask for the board pack', 'sender_class': 'person'})
    s.reconcile_processing_membership()
    item = s._one("SELECT ItemId FROM processing_member WHERE EntityKind='message' AND LocalId=? AND RetiredAt IS NULL", (str(asked),))['ItemId']
    funnel.settle(s, f'processing:{item}', 'surfaced', 'owner', read=True)
    with mock.patch('taskuary.terminal.live_sessions', return_value=[]): assert sweep.run(s)['asks'] == 1
    clean(s)


def test_an_advisor_line_about_a_tasks_mail_is_that_tasks_row(s):
    f = Factory(s)
    tid = f.task(title='Close the September books')
    mid = mail(f, 'Gail Moreno', 'September close', 'c-close', tid)
    [line] = assistant.parse(s, json.dumps({'say': [{'key': 'idea:close', 'text': 'Gail is waiting on the accruals.', 'why': 'she asked',
                                                     'mid': mid}]}), [])
    assert line['action']['tid'] == tid                                  # said over the task's mail: the task's line
    s.upsert_idea(line, ago(hours=1))
    rows = [i for i in build(s, include_read=True)['items'] if i.get('tid') == tid or i.get('mid') == mid]
    assert len(rows) == 1 and rows[0]['kind'] != 'idea', rows
    clean(s)


def test_a_line_said_before_its_mail_became_a_task_joins_the_task(s):
    f = Factory(s)
    mid = mail(f, 'Ray Colton', 'Payworth export failed', 'c-export', status='filed', days=2)
    s.add_route(mid, None, 'file', None, 'triage: nothing to do - a notice', [], 'triage')
    s.upsert_idea({'key': 'idea:export', 'kind': 'idea', 'text': 'The Payworth export failed twice this week.', 'sig': 'x',
                   'action': {'type': 'message', 'mid': mid}}, ago(days=1))
    assert len([i for i in build(s)['items'] if i.get('mid') == mid]) == 2      # the mail's own row and the line about it (ASK OWNER)
    tid = ingest.task_from_message(s, mid, 'owner', 'task', 'owner')            # Put it on my list: the mail is work now
    rows = [i for i in build(s, include_read=True)['items'] if i.get('mid') == mid or i.get('tid') == tid]
    assert len(rows) == 1 and rows[0]['tid'] == tid, [(r['kind'], r['lane'], r.get('tid')) for r in rows]
    clean(s)


def test_not_a_task_leaves_no_reason_naming_the_task_that_went(s):
    # Omar's thread: his first mail was a task, closed; his next joined it as "same conversation thread as TQ-n, which was closed";
    # the owner pressed Not a task, the task went and both mails went back to the feed. The FYI row must not name the gone task.
    f = Factory(s)
    tid = f.task(title='Badge access for the new hire', status='done', ClosedAt=ago(3))
    first = mail(f, 'Omar Keller', 'Badge access', 'c-badge', tid, days=4)
    f.route(first, tid, 'create', 'real work')
    later = mail(f, 'Omar Keller', 'Re: Badge access', 'c-badge', tid, days=1)
    s.add_route(later, None, 'queued', None, 'on the timeline first - triage decides next', [], 'router')
    s.add_route(later, tid, 'attach', 1.0, f'same conversation thread as {task_ref(tid)}, which was closed - it reopens only on new work', [], 'router')
    s.add_route(first, None, 'ignore', None, 'not a task - Badge access', [], 'owner')
    s.delete_task(tid)
    for name, b in rails(s):
        row = next((i for i in b['items'] if i.get('mid') == later), None)
        assert row is None or task_ref(tid) not in str(row.get('why') or ''), (name, row.get('why'))
    clean(s)
