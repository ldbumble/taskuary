""""Later" with a real time (2026-10-06): a reminder can be set for later today, and Later on the rail comes back after
the meetings the owner is in, not in the middle of one. The calendar is read as already cached - never a live call in
front of a press - and with no calendar it is plain hours."""
from datetime import datetime, timedelta
from unittest import mock

import pytest

from taskuary import funnel, remind
from taskuary.store import MemoryStore

NOW = datetime(2026, 9, 25, 9, 30)          # passed in as `now` everywhere: nothing here reads the real clock


@pytest.fixture
def s():
    v = MemoryStore(); yield v; v.close()


def meeting(start, mins):
    a = NOW.replace(hour=int(start[:2]), minute=int(start[3:]))
    return {'start': f'{a:%Y-%m-%d %H:%M}', 'end': f'{a + timedelta(minutes=mins):%Y-%m-%d %H:%M}', 'subject': 'Weekly sync'}


def cal(*events): return mock.patch('taskuary.remind.agenda', return_value=list(events))


# ── a reminder later today ───────────────────────────────────────────────────────────────
def test_later_today_is_read_with_a_time():
    for said, at in (('today 3pm', '2026-09-25 15:00:00'), ('3pm', '2026-09-25 15:00:00'), ('at 4:15 pm', '2026-09-25 16:15:00'),
                     ('today at 17:30', '2026-09-25 17:30:00'), ('in 2 hours', '2026-09-25 11:30:00'),
                     ('in 45 minutes', '2026-09-25 10:15:00'), ('an hour', '2026-09-25 10:30:00')):
        assert remind.parse(said, NOW) == at, said


def test_a_time_already_gone_or_today_with_no_time_is_refused():
    with pytest.raises(ValueError, match='already gone'): remind.parse('today 8am', NOW)
    with pytest.raises(ValueError, match='already gone'): remind.parse('9am', NOW)
    with pytest.raises(ValueError, match='say a time later today'): remind.parse('today', NOW)
    with pytest.raises(ValueError, match='say a time later today'): remind.parse('2026-09-25', NOW)
    with pytest.raises(ValueError, match='day has gone'): remind.parse('2026-09-20', NOW)


def test_today_is_said_with_its_time():
    assert remind.when('2026-09-25 14:35:00', NOW) == 'today at 2:35'
    assert remind.when('2026-09-26 07:00:00', NOW) == 'Sat 26 Sep'


def test_a_reminder_for_later_today_puts_the_task_away_and_its_undo_keeps_the_hour(s):
    tid = s.create_task({'Title': 'Call the vendor back', 'Kind': 'task', 'Status': 'open'}, 'owner')
    later = (datetime.now() + timedelta(hours=1)).replace(second=0, microsecond=0)
    if later.date() != datetime.now().date(): pytest.skip('too close to midnight for a later-today reminder')
    out = remind.set_reminder(s, tid, f'today {later:%H:%M}')
    assert out['remindAt'] == f'{later:%Y-%m-%d %H:%M:00}' and remind.waiting(s.get_task(tid))
    again = remind.set_reminder(s, tid, '2 weeks')
    assert again['undo']['params'] == {'until': f'{later:%Y-%m-%d %H:%M}'}


def test_the_five_minute_sweep_brings_it_back_without_waiting_for_a_sync(s):
    from taskuary import asks
    tid = s.create_task({'Title': 'Call the vendor back', 'Kind': 'task', 'Status': 'open'}, 'owner')
    s.update_task(tid, {'RemindAt': f'{datetime.now() - timedelta(minutes=2):%Y-%m-%d %H:%M:00}'}, 'owner')
    with mock.patch('taskuary.asks._rail', return_value=[]): asks.sweep(s)
    assert s.list_comments(tid)[-1]['Body'] == remind.DUE_NOTE and not s.get_task(tid)['RemindAt']


# ── after your meetings ──────────────────────────────────────────────────────────────────
def test_a_run_of_meetings_close_together_is_one_run():
    run = remind.busy_run([meeting('09:00', 60), meeting('10:05', 55), meeting('13:00', 30)], NOW)
    assert run == (NOW.replace(hour=11, minute=0), NOW.replace(hour=10, minute=5))
    assert remind.busy_run([meeting('13:00', 30)], NOW) is None
    assert remind.busy_run([meeting('13:00', 30)], NOW, ahead=True)[0] == NOW.replace(hour=13, minute=30)


def test_after_my_meetings_offers_the_next_free_moment(s):
    with cal(meeting('14:00', 30)):
        free = remind.after_meetings(s, NOW)
    assert free == {'until': '2026-09-25 14:35', 'label': 'After your 2:00',
                    'says': "You're in meetings until 2:30. I'll bring it back at 2:35."}
    with cal(): assert remind.after_meetings(s, NOW) is None


def test_after_my_meetings_with_none_left_today_asks_for_a_time(s):
    tid = s.create_task({'Title': 'Call the vendor back', 'Kind': 'task', 'Status': 'open'}, 'owner')
    with cal(), pytest.raises(ValueError, match='no more meetings today'):
        remind.set_reminder(s, tid, 'after my meetings')


# ── Later on the rail ────────────────────────────────────────────────────────────────────
def test_later_with_no_calendar_is_three_hours_said_plainly(s):
    with cal():
        back, says = funnel.later_until(s, NOW)
    assert back == NOW + timedelta(hours=funnel.LATER_HOURS) and says == "I'll bring it back at 12:30."


def test_later_in_meetings_comes_back_after_them(s):
    with cal(meeting('09:00', 90)):
        back, says = funnel.later_until(s, NOW)
    assert back == NOW.replace(hour=10, minute=35)
    assert says == "You're in meetings until 10:30. I'll bring it back at 10:35."


def test_later_that_would_land_mid_meeting_waits_for_its_end(s):
    with cal(meeting('12:00', 150)):
        back, says = funnel.later_until(s, NOW)
    assert back == NOW.replace(hour=14, minute=35) and 'until 2:30' in says


def test_settle_carries_the_sentence(s):
    with cal(), mock.patch.object(s, 'set_funnel_state') as put:
        out = funnel.settle(s, 'mail:1', 'later')
    assert put.call_args[0][1] == 'later' and out['says'].startswith("I'll bring it back")


def test_the_receipt_says_when_it_comes_back_and_who_is_watched():
    from taskuary import concierge
    assert concierge._outcome_line('item.settle', {'verb': 'later'}, {'says': "I'll bring it back at 2:35."}) == " I'll bring it back at 2:35."
    assert concierge._outcome_line('review.approve', {}, {'watching': "Sent. I'll watch for Erin's answer."}).endswith("Erin's answer.")
    assert concierge._outcome_line('item.settle', {'verb': 'done'}, {'closed': 7, 'says': 'x'}) != ' x'
