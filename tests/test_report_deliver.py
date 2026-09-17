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


# ── the shared reading: one judgement of the result, whoever asks ───────────────────────
def test_the_result_is_read_once_and_both_rules_see_the_same_thing():
    res = reports.read_result('4 rows', 'a\nb\nVERDICT: attention: the ledger job has not run', failed=False)
    assert (res['verdict'], res['why']) == ('attention', 'the ledger job has not run')
    assert reports.rule_fires('wrong', {}, res)[1] == 'the ledger job has not run'


def test_a_run_that_could_not_run_is_wrong_for_every_rule():
    res = reports.read_result('FAILED', 'Report error: no connector', failed=True)
    for how in ('always', 'wrong', 'rule'):
        assert reports.rule_fires(how, {'when': 'contains', 'text': 'x'}, res)[0] is True


# ── how delivery decides, and what an older config still means ──────────────────────────
def test_delivery_without_the_setting_still_goes_out_every_run():
    """Deliver has always sent every run; an absent setting cannot quietly change that."""
    assert reports.deliver_how({'deliver': {'to': 'ops@acme.com'}}) == 'always'
    assert reports.deliver_how({}) == 'always'


def test_delivery_can_be_asked_for_silence_of_its_own():
    assert reports.deliver_how({'deliver': {'to': 'x', 'send': 'wrong'}}) == 'wrong'
    assert reports.deliver_how({'deliver': {'to': 'x', 'send': 'rule', 'when': 'more_than', 'count': 5}}) == 'rule'
    assert reports.deliver_how({'deliver': {'to': 'x', 'send': 'nonsense'}}) == 'always'


def test_a_quiet_report_still_mails_the_people_waiting_for_it():
    """reach=wrong + deliver=always: "do not bother me, but send it out every month"."""
    cfg = {'reach': 'wrong', 'deliver': {'to': 'ops@acme.com'}}
    body = 'Nothing outstanding.\nVERDICT: clear'
    assert reports.reaches(cfg, '0 rows', body)[0] is False
    assert reports.delivers(cfg, reports.read_result('0 rows', body, False))[0] is True


def test_delivery_can_be_the_quiet_one_while_the_owner_sees_every_run():
    cfg = {'reach': 'always', 'deliver': {'to': 'ops@acme.com', 'send': 'wrong'}}
    assert reports.delivers(cfg, reports.read_result('0 rows', 'All fine.\nVERDICT: clear', False))[0] is False
    assert reports.delivers(cfg, reports.read_result('x', 'VERDICT: attention: disk at 96%', False))[1] == 'disk at 96%'


def test_delivery_reads_its_own_condition_not_the_alerts():
    """The alert's rule is the alert's. A report can shout at 3am and mail on a different one."""
    cfg = {'deliver': {'to': 'ops@acme.com', 'send': 'rule', 'when': 'more_than', 'count': 5},
           'alert': {'to': '4477…', 'when': 'nothing_came_back'}}
    assert reports.delivers(cfg, reports.read_result('9 rows', 'a', False))[0] is True
    assert reports.delivers(cfg, reports.read_result('2 rows', 'a', False))[0] is False


# ── the whole run: the two rules decide different things about the same result ──────────
def test_a_run_too_quiet_for_the_timeline_still_leaves_the_building():
    """The regression 06447455 introduced: the quiet return sat above the delivery block."""
    s = MemoryStore()
    src = _src(s)
    cfg = {'title': 'Monthly invoices', 'reach': 'wrong', 'deliver': {'to': 'ops@acme.com', 'gate': 'auto'}}
    s.save_source({**src, 'ConfigJson': json.dumps(cfg)}, 't')
    with mock.patch.object(reports, 'render_report', return_value=('0 rows', 'Nothing outstanding.\nVERDICT: clear')), \
         mock.patch.object(reports, 'deliver_report') as sent:
        out = reports.run_report_source(s, s.get_source(src['SourceId']), None)
    assert out['quiet'] is True and out['message_id'] is None      # nothing on the Timeline
    sent.assert_called_once()                                      # ...and it still went out


def test_a_quiet_run_that_could_not_send_is_work_even_though_the_run_was_clean():
    s = MemoryStore()
    src = _src(s)
    cfg = {'title': 'Monthly invoices', 'reach': 'wrong', 'deliver': {'to': 'ops@acme.com', 'gate': 'auto'}}
    s.save_source({**src, 'ConfigJson': json.dumps(cfg)}, 't')
    with mock.patch.object(reports, 'render_report', return_value=('0 rows', 'Nothing outstanding.\nVERDICT: clear')), \
         mock.patch.object(reports, 'deliver_report', side_effect=RuntimeError('SMTP 535 auth failed')):
        out = reports.run_report_source(s, s.get_source(src['SourceId']), None)
    assert 'SMTP 535' in str(out.get('deliver_error') or '')
    row = next(r for r in s.feed(limit=5) if str(r['Subject']).endswith('FAILED'))
    assert funnel.report_failed(s, row['Subject'], row['MessageId']) is True


# ── a send that did not happen ──────────────────────────────────────────────────────────
def test_a_failed_delivery_files_a_row_the_funnel_reads_as_a_failed_check():
    """Not an fyi that scrolls past: `broken` is a lane on the WORK rail, and the owner has to
    know the people waiting for this did not get it."""
    s = MemoryStore()
    mid = reports.file_delivery_failure(s, _src(s), {'title': 'Monthly invoices', 'deliver': {'to': 'ops@acme.com'}},
                                        'Monthly invoices', RuntimeError('SMTP 535 auth failed'))
    row = s.get_message(mid)
    assert row['Subject'].endswith('FAILED') and 'deliver' in row['Subject'].lower()
    assert 'ops@acme.com' in row['BodyText'] and '535' in row['BodyText']
    assert funnel.report_failed(s, row['Subject'], mid) is True
