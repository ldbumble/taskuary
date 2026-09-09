"""Taskuary is a WINDOW, and the Assistant has to know it.

is_due always knew ("a local app sleeps... a cron slot missed while closed fires on the next poll
after reopening"), but nothing wrote down WHEN the app was up. So the Assistant - which reads
arrivals, not the scheduler - saw a 17-hour hole in a 140-minute report and filed "no scheduled
report has fired since Tue 15:39... the 08:00 digest is 23 minutes late" (TQ-0451). The app had
been shut from 17:00 to 08:19; the digest ran at 08:25, two minutes after the alarm.
"""
import json
from datetime import datetime, timedelta

from taskuary import reports
from taskuary.store import MemoryStore


def at(**kw): return (datetime.now() - timedelta(**kw)).strftime('%Y-%m-%d %H:%M:%S')

def store(sessions=None):
    s = MemoryStore()
    if sessions is not None: s.set_setting(reports.APP_SESSIONS, json.dumps(sessions), 't')
    return s

def sessions(s): return json.loads(s.get_settings()[reports.APP_SESSIONS])


# ── writing it down ────────────────────────────────────────────────────────────────────
def test_a_launch_opens_a_session_and_a_heartbeat_extends_it():
    s = store()
    reports.note_app_up(s, start=True)
    reports.note_app_up(s)
    assert len(sessions(s)) == 1
    reports.note_app_up(s, start=True)
    assert len(sessions(s)) == 2

def test_only_the_last_few_launches_are_kept():
    s = store()
    for _ in range(reports.KEEP_SESSIONS + 5): reports.note_app_up(s, start=True)
    assert len(sessions(s)) == reports.KEEP_SESSIONS

def test_a_hand_edited_setting_never_breaks_the_launch():
    for junk in ('not json', '{"start": "x"}', '[42]'):
        s = store(); s.set_setting(reports.APP_SESSIONS, junk, 't')
        reports.note_app_up(s)
        assert isinstance(sessions(s), list)


# ── reading it back ────────────────────────────────────────────────────────────────────
def test_the_overnight_close_is_named_with_its_length():
    """TQ-0451's own shape: up until 17:00, shut, back at 08:19 the next morning."""
    words = reports.uptime_words(store([{'start': at(hours=25), 'seen': at(hours=16)},
                                        {'start': at(minutes=10), 'seen': at(minutes=1)}]))
    assert 'closed' in words and '15h50m' in words       # shut at -16h, back at -10m
    assert 'no report could fire' in words

def test_how_long_this_launch_has_been_up_is_always_said():
    """The other half of the false alarm: 'the 08:00 digest is late' when the app opened at 08:19."""
    assert 'running since' in reports.uptime_words(store([{'start': at(minutes=4), 'seen': at(minutes=1)}]))
    assert '4m ago' in reports.uptime_words(store([{'start': at(minutes=4), 'seen': at(minutes=1)}]))

def test_a_restart_is_not_a_closure():
    """A heartbeat is not instant, so a quick relaunch must not read as downtime."""
    words = reports.uptime_words(store([{'start': at(hours=3), 'seen': at(hours=2)},
                                        {'start': at(hours=2), 'seen': at(minutes=1)}]))
    assert 'closed' not in words

def test_closures_older_than_the_window_are_left_out():
    words = reports.uptime_words(store([{'start': at(days=9), 'seen': at(days=9)},
                                        {'start': at(days=5), 'seen': at(minutes=1)}]), days=2)
    assert 'closed' not in words and 'running since' in words

def test_nothing_recorded_yet_says_nothing():
    assert reports.uptime_words(store()) == ''
    assert reports.uptime_words(store([])) == ''


# ── what the check actually reads ──────────────────────────────────────────────────────
def test_the_assistant_is_told_when_the_app_was_shut():
    from taskuary import assistant
    s = store([{'start': at(hours=25), 'seen': at(hours=16)}, {'start': at(minutes=4), 'seen': at(minutes=1)}])
    text = assistant.inputs(s, [])
    assert 'WHEN TASKUARY WAS RUNNING' in text
    assert 'closed' in text and 'running since' in text

def test_with_nothing_recorded_the_section_is_left_out_entirely():
    """An empty labelled section reads as "nothing was running" - the very error being fixed."""
    from taskuary import assistant
    assert 'WHEN TASKUARY WAS RUNNING' not in assistant.inputs(store(), [])


def test_the_instruction_warns_against_calling_a_shut_app_a_dead_scheduler():
    from taskuary import assistant
    assert 'WHEN TASKUARY WAS RUNNING' in assistant.PROMPT
    assert 'cannot fire while the app is shut' in assistant.PROMPT
