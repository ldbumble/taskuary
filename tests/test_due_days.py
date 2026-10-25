"""Deadlines kept (2026-10-06): triage reads the day the work is due, the code checks it is a real one, and the task is
brought to the top the day before, said on the day, and asked about once when it has passed - in the app, never on a
phone that did not speak first. Reminders and due days are looked at before the mail is read, and on start."""
import json, unittest
from datetime import datetime, timedelta
from unittest import mock

import pytest

from taskuary import asks, general, ingest, remind, remote_assistant, server, triage
from taskuary.store import MemoryStore


@pytest.fixture
def s():
    v = MemoryStore(); yield v; v.close()


def day(n=0, now=None): return f"{(now or datetime.now()) + timedelta(days=n):%Y-%m-%d}"


# ── triage reads the day; the code keeps only a real one ─────────────────────────────────
def test_a_due_day_is_kept_only_when_it_is_a_real_day_near_the_mail():
    sent = '2026-10-06 09:00:00'
    assert triage.due_of({'due': '2026-10-09'}, sent) == '2026-10-09'
    assert triage.due_of({'due': '2026-10-02'}, sent) == '2026-10-02'            # a few days back: already late, still real
    for bad in ('2031-10-09', '2025-10-09', '2026-02-30', 'Friday', '', None, 'soon'):
        assert triage.due_of({'due': bad}, sent) is None, bad


def brain(due, intent='task', seen=None):
    def llm(system, user, **k):
        if seen is not None: seen.append((system, user))
        out = {'intent': intent, 'why': 'the form is due on Friday', 'title': 'Return the signed form', 'summary': 's',
               'urgent': False, 'due': due}
        if intent == 'task': out['kind'] = 'task'
        return json.dumps(out)
    return llm


def mail(s, llm, sent=None):
    with mock.patch.object(ingest, '_spawn'):
        return ingest.ingest_message(s, {'external_id': 'due-1', 'channel': 'email', 'from_email': 'erin@vendor.example',
                                         'from_name': 'Erin Blake', 'conversation_id': 'due-c1', 'subject': 'Signed form',
                                         'body': 'Could you return the signed form by Friday?', 'sent_at': sent or f'{day()} 09:00:00'},
                                     llm=llm)


def test_the_prompt_asks_for_the_day_from_when_it_was_sent_and_the_schema_carries_it(s):
    seen = []
    mail(s, brain(day(3), seen=seen))
    system, user = seen[0]
    assert '"due"' in system and json.loads(user)['sent_on'] == day()
    assert 'due' in triage.verdict_schema()['schema']['required']


def test_an_owner_document_without_the_field_still_gets_it_asked():
    seen = []
    triage.classify_intent({'from_email': 'erin@vendor.example', 'subject': 's', 'body': 'b'}, llm=brain(None, seen=seen),
                           system='Classify. Answer {"intent": "task|reply_only|fyi", "urgent": false}.')
    assert triage.DUE in seen[0][0]


def test_the_due_day_lands_on_the_task(s):
    out = mail(s, brain(day(3)))
    assert s.get_task(out['task_id'])['DueAt'] == day(3)


def test_an_fyi_carries_no_due_day():
    v = triage.classify_intent({'from_email': 'erin@vendor.example', 'subject': 's', 'body': 'b', 'sent_at': f'{day()} 09:00:00'},
                               llm=brain(day(3), intent='fyi'))
    assert 'due' not in v


# ── said as it nears, once per step, in the app ──────────────────────────────────────────
def due_task(s, n, **k):
    tid = s.create_task({'Title': 'Return the signed form', 'Kind': 'task', 'Status': 'open', 'Source': 'email', **k}, 'triage')
    remind.set_due(s, tid, day(n), 'triage')
    return tid


def dock_lines(s):
    return [c['Body'] for c in s.list_comments(general.dock_task(s, 'owner')[0]['TaskId'])]


def test_far_off_is_quiet(s):
    tid = due_task(s, 5)
    assert remind.deadlines(s) == 0 and s.get_task(tid)['Priority'] != 'urgent'


def test_the_day_before_it_goes_to_the_top_once(s):
    tid = due_task(s, 1)
    assert remind.deadlines(s) == 1
    t = s.get_task(tid)
    assert t['Priority'] == 'urgent' and t['DueSaid'] == 'eve'
    assert s.list_comments(tid)[-1]['Body'] == "This one's due tomorrow, so it's at the top of your list."
    assert remind.deadlines(s) == 0                                             # said once


def test_on_the_day_and_then_late_each_said_once(s):
    tid = due_task(s, 0)
    assert remind.deadlines(s) == 1 and s.list_comments(tid)[-1]['Body'] == "This one's today."
    assert not any("This one's today." in l for l in dock_lines(s))            # the note says it, never the chat
    tomorrow = datetime.now() + timedelta(days=1)
    assert remind.deadlines(s, tomorrow) == 1
    assert s.list_comments(tid)[-1]['Body'] == "This was due yesterday and it's still open."
    assert remind.deadlines(s, tomorrow + timedelta(days=3)) == 0              # late is asked once


def test_long_past_names_the_day():
    now = datetime(2026, 10, 12, 9, 0)
    assert remind.due_line({'DueAt': '2026-10-09'}, now) == "This was due Fri 9 Oct and it's still open."


def test_a_new_day_starts_the_steps_again_and_a_closed_task_is_left_alone(s):
    tid = due_task(s, 0); remind.deadlines(s)
    remind.set_due(s, tid, day(1)); assert not s.get_task(tid)['DueSaid']
    done = due_task(s, 0); s.update_task(done, {'Status': 'done'}, 'owner')
    assert remind.deadlines(s) == 1 and not s.get_task(done)['DueSaid']


def test_the_phone_never_speaks_first(s):
    due_task(s, 0)
    with mock.patch.object(remote_assistant, 'handoff', return_value={'channel': 'whatsapp', 'chat': 'c1@example.com'}), \
         mock.patch.object(remote_assistant, 'connector_for_chat', return_value={'ConnectorId': 3}), \
         mock.patch.object(remote_assistant, 'quiet', return_value=True), mock.patch.object(remote_assistant, 'send') as send:
        assert remind.deadlines(s) == 1
    assert not send.called and not any("This one's today." in l for l in dock_lines(s))




# ── before the catch-up, and on start ────────────────────────────────────────────────────
class OrderTests(unittest.TestCase):
    def setUp(self):
        from tests.test_poll_lanes import arm
        self.s = MemoryStore(); arm(self.s, 'outlook')
        p = mock.patch.object(server, 'store', self.s); p.start(); self.addCleanup(p.stop)
        r = mock.patch.object(server, 'run_due_reports'); r.start(); self.addCleanup(r.stop)
        self.addCleanup(lambda: server._close_drain_workers(10))

    def test_reminders_are_looked_at_before_the_mail_is_read(self):
        order = []
        def poll(store, days, progress=None, only=None): order.append('mail'); return 0
        with mock.patch('taskuary.channels.poll_channels', poll), \
             mock.patch('taskuary.remind.tick', side_effect=lambda st, *a: order.append('reminders')):
            server._poll_reports(0, what='syncing')
        self.assertEqual(order[:2], ['reminders', 'mail'])


# ── B18 (2026-10-11): the urgent flag follows the day, the eve is a working day, and the late line has buttons ──────
def test_moving_the_day_weeks_out_lowers_only_the_urgent_the_assistant_raised(s):
    tid = due_task(s, 0); remind.deadlines(s)
    assert s.get_task(tid)['Priority'] == 'urgent'
    remind.set_due(s, tid, day(21))
    assert s.get_task(tid)['Priority'] == 'regular'                             # back to what it was before the due day raised it
    mine = due_task(s, 0, Priority='urgent'); remind.deadlines(s)               # urgent before the due day ever came near
    remind.set_due(s, mine, day(21)); assert s.get_task(mine)['Priority'] == 'urgent'
    later = due_task(s, 0); remind.deadlines(s)
    s.update_task(later, {'Priority': 'urgent'}, 'owner')                      # the owner said urgent herself, after the raise
    remind.set_due(s, later, day(21)); assert s.get_task(later)['Priority'] == 'urgent'


def test_a_day_moved_but_still_near_keeps_it_at_the_top(s):
    tid = due_task(s, 0); remind.deadlines(s)
    remind.set_due(s, tid, day(1)); assert s.get_task(tid)['Priority'] == 'urgent'


def test_first_seen_already_late_goes_to_the_top(s):
    tid = due_task(s, -3)
    assert remind.deadlines(s) == 1 and s.get_task(tid)['Priority'] == 'urgent'


def test_the_eve_is_the_last_working_day_before_it():
    mon = '2026-10-12'
    assert remind.step(mon, datetime(2026, 10, 8, 9)) is None                  # Thursday: not yet
    assert remind.step(mon, datetime(2026, 10, 9, 9)) == 'eve'                 # Friday is the day before, for work
    assert remind.step(mon, datetime(2026, 10, 11, 9)) == 'eve'                # ...and the weekend is still before it
    assert remind.step('2026-10-15', datetime(2026, 10, 13, 9)) is None
    assert remind.step('2026-10-15', datetime(2026, 10, 14, 9)) == 'eve'       # midweek it is plain tomorrow
    assert remind.due_line({'DueAt': mon}, datetime(2026, 10, 9, 9)) == "This one's due Monday, so it's at the top of your list."
    assert remind.due_line({'DueAt': '2026-10-15'}, datetime(2026, 10, 14, 9)) == "This one's due tomorrow, so it's at the top of your list."


def test_the_assistant_can_move_the_due_day(s):
    tid = due_task(s, 0); remind.deadlines(s)
    with mock.patch.object(server, 'store', s):
        out = server._run_operation({'kind': 'task.update', 'target': tid, 'params': {'due': '3 weeks'}}, None)
    t = s.get_task(tid)
    assert t['DueAt'] == day(21) and t['Priority'] == 'regular' and not t['DueSaid'] and out['changed']['DueAt'] == day(21)
    with mock.patch.object(server, 'store', s), pytest.raises(server.HTTPException):
        server._run_operation({'kind': 'task.update', 'target': tid, 'params': {'due': 'soonish'}}, None)
