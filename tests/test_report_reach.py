"""When a report reaches the owner at all.

A scheduled check that posts "All clear" every hour is a check nobody reads. The owner had no way
to ask for silence: the conditions were row-shaped ("fewer rows than 5" compared five LINES of an
AI summary), they were never evaluated for an Assistant-sourced check at all, and the only way to
get an all-clear line was to ask the model for one in the prompt - which is what made it post one
(2026-09-17: "if no errors then don't show up at all ... make this better for all use cases").

So a prose answer ends with a line code can read, and ONE rule decides whether the run reaches the
owner - on the Timeline and on the phone alike.
"""
import pytest

from taskuary import reports


# ── the verdict: the one thing a prose answer must say in a form code can read ──────────
def test_a_clear_verdict_is_read_and_taken_off_the_report():
    kind, why, rest = reports.verdict_of('Nothing unusual in the last hour.\n\nVERDICT: clear')
    assert (kind, why) == ('clear', '')
    assert 'VERDICT' not in rest and rest == 'Nothing unusual in the last hour.'


def test_an_attention_verdict_carries_its_sentence():
    kind, why, rest = reports.verdict_of('Three runs failed.\nVERDICT: attention: 3 runs failed on the same TCP error')
    assert (kind, why) == ('attention', '3 runs failed on the same TCP error')
    assert rest == 'Three runs failed.'


def test_the_last_verdict_wins_because_the_contract_says_final_line():
    """A model that quotes the contract back before answering must not settle it with the quote."""
    kind, _, _ = reports.verdict_of('I will end with VERDICT: clear if all is well.\n\nVERDICT: attention: disk at 96%')
    assert kind == 'attention'


def test_no_verdict_at_all_is_not_a_verdict():
    assert reports.verdict_of('12 rows came back')[0] == ''
    assert reports.verdict_of('')[0] == ''


# ── how a report reaches you, and what the old configs still mean ───────────────────────
def test_a_report_without_the_setting_keeps_doing_what_it_did():
    assert reports.reach_of({'type': 'sql'}) == 'always'                       # posted every run
    assert reports.reach_of({'type': 'assistant'}) == 'wrong'                  # was quiet already
    assert reports.reach_of({'type': 'sql', 'alert': {'when': 'nothing_came_back'}}) == 'rule'


def test_the_setting_wins_over_the_guess():
    assert reports.reach_of({'type': 'assistant', 'reach': 'always'}) == 'always'
    assert reports.reach_of({'alert': {'when': 'failed'}, 'reach': 'wrong'}) == 'wrong'


# ── the rule itself ─────────────────────────────────────────────────────────────────────
def test_a_clear_check_reaches_nobody():
    speak, why = reports.reaches({'reach': 'wrong'}, 'what the check found', 'All quiet.\nVERDICT: clear')
    assert (speak, why) == (False, '')


def test_a_check_that_found_something_reaches_you_in_its_own_words():
    speak, why = reports.reaches({'reach': 'wrong'}, 'x', 'VERDICT: attention: 3 runs failed on the same TCP error')
    assert speak and why == '3 runs failed on the same TCP error'


def test_without_a_verdict_the_rows_are_the_answer():
    assert reports.reaches({'reach': 'wrong'}, '0 rows', '')[0] is False
    assert reports.reaches({'reach': 'wrong'}, '4 rows', 'a\nb')[0] is True


def test_the_assistants_own_count_is_the_answer_when_it_has_one():
    """Its findings are rows in no sense - it hands over how many it made."""
    assert reports.reaches({'reach': 'wrong'}, 'Backend monitor', '', found=0)[0] is False
    assert reports.reaches({'reach': 'wrong'}, 'Backend monitor', 'the ledger job has not run', found=1)[0] is True


def test_a_failed_run_always_reaches_you():
    """A check that could not run is not a clear one - whatever the rule was."""
    for reach in ('always', 'wrong', 'rule'):
        speak, why = reports.reaches({'reach': reach, 'alert': {'when': 'contains', 'text': 'x'}},
                                     'FAILED', 'Report error: no connector', failed=True)
        assert (speak, why) == (True, 'the report failed to run')


def test_every_run_reaches_you_whatever_it_found():
    assert reports.reaches({'reach': 'always'}, '0 rows', '')[0] is True


def test_only_when_reads_the_condition_the_alert_would_have_read():
    cfg = {'reach': 'rule', 'alert': {'when': 'nothing_came_back'}}
    assert reports.reaches(cfg, '0 rows', '')[1] == 'nothing came back'
    assert reports.reaches(cfg, '3 rows', 'a')[0] is False
    # ...and it is the SAME reading the push uses, so the two can never disagree
    with_push = {'reach': 'rule', 'alert': {'when': 'nothing_came_back', 'to': '4477…'}}
    assert reports.alert_fires(with_push, '0 rows', '') == reports.reaches(with_push, '0 rows', '')[1]


# ── the contract the model is given ─────────────────────────────────────────────────────
def test_the_prompt_asks_for_the_verdict_and_says_it_is_not_for_the_reader():
    assert 'VERDICT: clear' in reports.VERDICT_CONTRACT
    assert 'removed before the report is filed' in reports.VERDICT_CONTRACT
    assert 'all clear' in reports.VERDICT_CONTRACT.lower()
