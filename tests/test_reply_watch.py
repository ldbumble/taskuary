""""I'll keep an eye out" that keeps it (2026-10-06): a sent reply that asks something watches for the answer, though
the send closed the task. Their answer ends it; two quiet days offer one nudge, held while they are away; the watch
counts its own 30 days and says when it stops. The lines nobody asked for stay in the app."""
import json
from datetime import datetime, timedelta
from unittest import mock

import pytest

from taskuary import asks, general, outbound, remote_assistant, verdicts
from taskuary.store import MemoryStore


@pytest.fixture
def s():
    v = MemoryStore(); yield v; v.close()


def ago(days=0, hours=0): return (datetime.now() - timedelta(days=days, hours=hours)).strftime('%Y-%m-%d %H:%M:%S')


def mail(s, tid, body, who='Blake, Erin', email='erin@vendor.example', status='routed', n=1, at=None, task=True):
    return s.add_message({'TaskId': tid if task else None, 'ExternalId': f'rw-{tid}-{n}', 'ConversationId': f'rw-thread-{tid}',
                          'Channel': 'email', 'SourceName': 'alex@northwind.example', 'Subject': 'Invoice dates',
                          'FromName': who, 'FromEmail': email, 'BodyText': body, 'SentAt': at or ago(hours=10 - n),
                          'Status': status, 'Direction': 'in'})


def asked(s, draft='Which day suits you for the walkthrough?'):
    tid = s.create_task({'Title': 'Book the invoice walkthrough', 'Kind': 'reply', 'Status': 'open', 'Source': 'email'}, 'triage')
    mid = mail(s, tid, 'Can we book a walkthrough of the new invoices?')
    rid = s.add_review({'TaskId': tid, 'MessageId': mid, 'Kind': 'draft_reply', 'Status': 'pending', 'DraftText': draft,
                        'Deliver': json.dumps({'kind': 'reply', 'to': ['erin@vendor.example'], 'cc': [], 'mode': 'reply_to'})})
    return tid, rid


def send(s, rid):
    with mock.patch('taskuary.outbound.reply_to_message', return_value={'channel': 'email', 'to': ['erin@vendor.example'], 'cc': []}), \
         mock.patch.object(outbound, 'send_block', return_value=''), mock.patch('taskuary.learn.learn_from'):
        return verdicts.decide(s, s.get_review(rid), 'approve')


def dock_lines(s):
    return [c['Body'] for c in s.list_comments(general.dock_task(s, 'owner')[0]['TaskId'])]


def rail(): return mock.patch('taskuary.asks._rail', return_value=[])


def test_a_reply_that_asks_closes_the_task_and_starts_the_watch(s):
    tid, rid = asked(s)
    out = send(s, rid)
    t = s.get_task(tid)
    assert out['ok'] and t['Status'] == 'done'
    assert out['watching'] == "Sent. I'll watch for Erin's answer."
    assert t['AskedWatch'] == 'reply' and t['AskedWatchAt'] and t['AskedVia'] == 'desktop'
    assert s.list_comments(tid)[-1]['Body'] == out['watching']


def test_a_reply_that_asks_nothing_starts_no_watch(s):
    tid, rid = asked(s, draft='Thanks, all done on our side.')
    out = send(s, rid)
    assert out['ok'] and 'watching' not in out and not s.get_task(tid)['AskedWatch']


def test_their_answer_is_said_once_and_ends_the_watch_even_when_it_was_filed_on_no_task(s):
    tid, rid = asked(s); send(s, rid)
    with rail(): assert asks.check(s, tid) is None                              # what was there before is not news
    mail(s, tid, 'Thursday at 2 works.', status='filed', n=5, at=ago(), task=False)   # triage filed it: a round trip
    with rail(): line = asks.check(s, tid)
    assert line and 'Erin Blake answered: Thursday at 2 works.' in line
    assert not s.get_task(tid)['AskedWatch'] and line in dock_lines(s)
    with rail(): assert asks.check(s, tid) is None


def test_an_auto_reply_is_not_an_answer(s):
    tid, rid = asked(s); send(s, rid)
    mail(s, tid, 'I am out of the office until Monday.', status='autoreply', n=5, at=ago(), task=False)
    with rail(): assert asks.check(s, tid) is None
    assert s.get_task(tid)['AskedWatch'] == 'reply'


def test_the_sweep_reaches_a_watch_on_a_closed_task(s):
    tid, rid = asked(s); send(s, rid)
    with rail(): asks.check(s, tid)                                             # its close is told (quietly) - still watched
    assert s.get_task(tid)['AskedTold'] == 'finished'
    with mock.patch.object(asks, 'check') as check, mock.patch.object(asks, 'nudge'): asks.sweep(s)
    assert [c[0][1] for c in check.call_args_list] == [tid]


def started(s, tid, days):
    s._exec('UPDATE task SET AskedWatchAt=? WHERE TaskId=?', (ago(days=days), tid))


def test_two_quiet_days_offer_one_nudge_in_the_app_only(s):
    tid, rid = asked(s); send(s, rid); started(s, tid, 1)
    assert asks.nudge(s, s.get_task(tid)) is None                               # one day is not silence yet
    started(s, tid, 3)
    with mock.patch.object(remote_assistant, 'handoff', return_value={'channel': 'whatsapp', 'chat': 'c1@example.com'}), \
         mock.patch.object(remote_assistant, 'send') as phone:
        line = asks.nudge(s, s.get_task(tid))
    assert line and 'still nothing from Erin' in line and 'nudge' in line
    assert not phone.called and line in dock_lines(s)                          # the phone never speaks first
    assert asks.nudge(s, s.get_task(tid)) is None                               # offered once


def test_no_nudge_while_they_are_out_of_office(s):
    tid, rid = asked(s); send(s, rid); started(s, tid, 3)
    with mock.patch('taskuary.assistant.ooo', return_value={'erin@vendor.example': 'out until Monday'}):
        assert asks.nudge(s, s.get_task(tid)) is None
    assert not s.get_task(tid)['AskedNudgedAt']


def test_thirty_days_count_from_the_watch_not_the_task(s):
    tid, rid = asked(s); send(s, rid)
    s._exec('UPDATE task SET CreatedAt=? WHERE TaskId=?', (ago(days=60), tid)); started(s, tid, 5)
    with mock.patch.object(asks, 'check') as check, mock.patch.object(asks, 'nudge'): asks.sweep(s)
    assert [c[0][1] for c in check.call_args_list] == [tid] and s.get_task(tid)['AskedWatch'] == 'reply'


def test_at_thirty_days_the_watch_ends_and_says_so(s):
    tid, rid = asked(s); send(s, rid); started(s, tid, 31)
    with rail(): asks.sweep(s)
    assert not s.get_task(tid)['AskedWatch']
    assert any("I've stopped watching for Erin's answer" in l and 'Keep going?' in l for l in dock_lines(s))
    asks.watch_task(s, tid, 'reply')                                           # keep going: a fresh 30 days
    assert s.get_task(tid)['AskedWatch'] == 'reply' and s.get_task(tid)['AskedWatchAt'] > ago(days=1)


def test_an_old_watch_with_no_start_of_its_own_ends_quietly(s):
    tid, rid = asked(s); send(s, rid)
    s._exec('UPDATE task SET AskedWatchAt=NULL, CreatedAt=? WHERE TaskId=?', (ago(days=40), tid))
    before = len(dock_lines(s))
    asks.sweep(s)
    assert not s.get_task(tid)['AskedWatch'] and len(dock_lines(s)) == before


def test_the_advisor_does_not_chase_what_the_watch_covers(s):
    tid, rid = asked(s); send(s, rid)
    assert tid in asks.touched(s, 1)['tids']
