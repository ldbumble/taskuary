"""When a report LEAVES, and what happens when it cannot.

`reach` says whether a run reaches the OWNER - the Timeline row and the push. Delivery is a
different question: it sends the result somewhere else entirely, to an address the owner chose.
The two got tangled when `reach` shipped (06447455), because the quiet return sat above the
delivery block: picking "only when something is wrong" silently stopped a monthly report going
out to its recipients (the owner, 2026-09-17: "deliver is to push to somewhere not timeline,
that is something else").

So delivery gets its OWN rule, in the same three words, reading the SAME verdict - one judgement
of the result, two consumers, which is how they can never disagree. And a send that did not
happen is work, not an fyi: it files its own row that the funnel reads as a failed check.
"""
import json
from unittest import mock

import pytest

from taskuary import funnel, reports
from taskuary.store import MemoryStore


def _src(s, title='Monthly invoices'):
    sid = s.save_source({'Channel': 'report', 'Address': title, 'Active': 1, 'ConfigJson': '{}'}, 't')
    return next(x for x in s.list_sources() if x['SourceId'] == sid)


# ── delivery answers on its own line of the card ────────────────────────────────────────
def test_a_quiet_report_still_mails_the_people_waiting_for_it():
    """Timeline never + send every run: "do not bother me, but send it out every month"."""
    cfg = {'route': {'timeline': {'how': 'never'}}, 'deliver': {'to': 'ops@example.com'}}
    d = reports.decide(cfg, reports.read_result('0 rows', 'Nothing outstanding.'))
    assert (d['timeline'], d['send']) == (False, True)


def test_delivery_reads_its_own_rule_not_the_alerts():
    """The alert's rule is the alert's. A report can shout at 3am and mail on a different one."""
    cfg = {'route': {'send': {'how': 'rule', 'rule': 'more_than', 'count': 5}, 'alert': {'how': 'rule', 'rule': 'nothing_came_back'}},
           'deliver': {'to': 'ops@example.com'}, 'alert': {'to': '+15550100'}}
    assert reports.decide(cfg, reports.read_result('9 rows', 'a'))['send'] is True
    assert reports.decide(cfg, reports.read_result('2 rows', 'a'))['send'] is False


def test_a_failure_is_never_sent_to_the_people_a_report_is_addressed_to():
    """"Report error: ..." is the owner's to read, in the app (the owner, 2026-09-27)."""
    cfg = {'route': {'send': {'how': 'always'}}, 'deliver': {'to': 'ops@example.com', 'gate': 'auto'}}
    assert reports.decide(cfg, reports.read_result('FAILED', 'Report error: no connector', True))['send'] is False


# ── the whole run: the two rules decide different things about the same result ──────────
def test_a_run_the_timeline_puts_down_still_leaves_the_building():
    """The regression 06447455 introduced: the quiet return sat above the delivery block."""
    s = MemoryStore()
    src = _src(s)
    cfg = {'title': 'Monthly invoices', 'route': {'timeline': {'how': 'never'}}, 'deliver': {'to': 'ops@example.com', 'gate': 'auto'}}
    s.save_source({**src, 'ConfigJson': json.dumps(cfg)}, 't')
    with mock.patch.object(reports, 'render_report', return_value=('0 rows', 'Nothing outstanding.')), \
         mock.patch.object(reports, 'deliver_report') as sent:
        out = reports.run_report_source(s, s.get_source(src['SourceId']), None)
    # filed and put down at once - a task or nothing (2026-09-28)...
    assert s.funnel_states()[f"report:{out['message_id']}"]['Status'] == 'done'
    sent.assert_called_once()                                      # ...and it still went out


def test_a_quiet_run_that_could_not_send_rings_the_bell_even_though_the_run_was_clean():
    s = MemoryStore()
    src = _src(s)
    cfg = {'title': 'Monthly invoices', 'route': {'timeline': {'how': 'never'}}, 'deliver': {'to': 'ops@example.com', 'gate': 'auto'}}
    s.save_source({**src, 'ConfigJson': json.dumps(cfg)}, 't')
    with mock.patch.object(reports, 'render_report', return_value=('0 rows', 'Nothing outstanding.')), \
         mock.patch.object(reports, 'deliver_report', side_effect=RuntimeError('SMTP 535 auth failed')):
        out = reports.run_report_source(s, s.get_source(src['SourceId']), None)
    assert 'SMTP 535' in str(out.get('deliver_error') or '')
    from taskuary import problems
    assert any(p['key'] == f"report_send:{src['SourceId']}" and '535' in p['detail'] for p in problems.collect(s))


# ── a send that did not happen ──────────────────────────────────────────────────────────
def test_a_failed_send_is_in_the_bell_not_on_the_rail_and_the_next_send_clears_it():
    """The owner, 2026-09-28: a send that did not go is a notification - it used to file a `broken` row on
    the work rail. The bell holds the latest one per report until a send goes."""
    from taskuary import problems
    s = MemoryStore(); src = _src(s)
    cfg = {'title': 'Monthly invoices', 'deliver': {'to': 'ops@example.com'}}
    with mock.patch.object(reports, 'deliver_report', side_effect=RuntimeError('SMTP 535 auth failed')):
        assert '535' in reports._deliver(s, src, cfg, 'Monthly invoices', 's', 'b')
    assert not s.feed(limit=5)
    bell = [p for p in problems.collect(s) if p['key'] == f"report_send:{src['SourceId']}"]
    assert len(bell) == 1 and 'ops@example.com' in bell[0]['detail'] and bell[0]['report'] == src['SourceId']
    with mock.patch.object(reports, 'deliver_report'):
        assert reports._deliver(s, src, cfg, 'Monthly invoices', 's', 'b') is None
    assert not [p for p in problems.collect(s) if p['key'] == f"report_send:{src['SourceId']}"]
