"""A report that only speaks up when something is wrong.

Delivery sends every run, which is useless for "tell me when the nightly job did not run":
a message that arrives whether or not anything is wrong is a message you stop reading. These
tests are about the RULE - no network, no channels - because a rule that misfires at 3am, or
stays silent when it should not, is the whole failure mode.
"""
import pytest

from taskuary import reports


def alert_fires(c, head, body):
    """The rule an alert line carries, read against one result - reports.condition_fires."""
    a = c.get('alert') or {}
    if not str(a.get('when') or '').strip() or not str(a.get('to') or '').strip(): return ''
    return reports.condition_fires(a['when'], a.get('count'), a.get('text'), res=reports.read_result(head, body))


def cfg(**alert): return {'title': 'Nightly job check', 'alert': {'to': '4477…', 'channel': 'whatsapp', **alert}}


# ── counting what came back ────────────────────────────────────────────────────────────
def test_the_row_executors_say_the_count_in_their_headline():
    assert reports.result_count('0 rows', '') == 0
    assert reports.result_count('12 rows', 'a\nb') == 12
    assert reports.result_count('1,204 rows (capped at the default 200)', '') == 1204


def test_prose_results_are_counted_by_their_lines():
    assert reports.result_count('what the assistant would read', 'one\n\ntwo\n') == 2
    assert reports.result_count('', '') == 0


# ── the rule the owner actually asked for ──────────────────────────────────────────────
def test_no_run_in_the_window_speaks_up():
    """The ask: query the run log for the last two hours; if nothing is there, tell me."""
    assert alert_fires(cfg(when='nothing_came_back'), '0 rows', '') == 'nothing came back'


def test_a_run_in_the_window_stays_silent():
    assert alert_fires(cfg(when='nothing_came_back'), '3 rows', '{"job": "ok"}') == ''


def test_the_reason_is_carried_so_the_phone_says_which_rule_tripped():
    why = alert_fires(cfg(when='fewer_than', count=5), '2 rows', 'a\nb')
    assert why == 'only 2 came back, expected at least 5'


# ── the other conditions ───────────────────────────────────────────────────────────────
def test_something_came_back_is_the_inverse():
    assert alert_fires(cfg(when='something_came_back'), '4 rows', 'x') == '4 came back'
    assert alert_fires(cfg(when='something_came_back'), '0 rows', '') == ''


def test_more_than_fires_only_above_the_line():
    assert alert_fires(cfg(when='more_than', count=10), '11 rows', '') != ''
    assert alert_fires(cfg(when='more_than', count=10), '10 rows', '') == ''


def test_contains_and_missing_read_the_headline_and_the_body():
    hit = cfg(when='contains', text='ERROR')
    assert alert_fires(hit, '3 rows', 'all fine\nan Error happened') != ''      # case-insensitive
    assert alert_fires(hit, '3 rows', 'all fine') == ''
    gone = cfg(when='missing', text='completed')
    assert alert_fires(gone, '1 rows', 'still running') != ''
    assert alert_fires(gone, '1 rows', 'completed at 04:00') == ''


# ── a failure is not the rule's to judge ───────────────────────────────────────────────
def test_a_failure_never_fires_an_alert():
    """A run that could not run reaches the owner in the app, and only there (the owner, 2026-09-27)."""
    cfg_ = {'route': {'alert': {'how': 'rule', 'rule': 'nothing_came_back'}}, 'alert': {'to': 'x'}}
    assert reports.decide(cfg_, reports.read_result('', 'Report error: login timeout', True))['alert'] is False
    assert 'failed' not in reports.ALERT_WHEN


def test_an_alert_with_nowhere_to_go_never_fires():
    """Switched on and never filled in - a rule that can only fail at 3am."""
    assert alert_fires({'alert': {'when': 'nothing_came_back', 'to': ''}}, '0 rows', '') == ''


def test_no_alert_configured_is_silence_not_an_error():
    assert alert_fires({}, '0 rows', '') == ''


def test_a_nonsense_condition_is_loud_rather_than_quietly_never_firing():
    with pytest.raises(ValueError, match='unknown rule'):
        alert_fires(cfg(when='when_it_feels_wrong'), '0 rows', '')
