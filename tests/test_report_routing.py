"""Where a run goes is a prompt, not a condition.

You cannot write an `if` against prose you have not seen. The conditions tried anyway - `contains`
matched substrings in an LLM's wording, `fewer_than` compared LINES of it - and when the model
skipped the VERDICT line the rule fell through to counting non-blank lines, so "only when something
is wrong" quietly became "every run" (rule_fires, 06447455).

So the model that can read the result answers where it goes, in one line per destination, against
sentences the owner wrote (2026-09-17: "make the UI clear that it's ai deciding it, so it's a prompt
on the report for routing"). Code compares yes to no, which is always one of two things.
"""
import json, unittest
from unittest import mock

import pytest
from fastapi.testclient import TestClient

from taskuary import reports, server

c = TestClient(server.app)


def res(head='4 rows', body='a\nb', failed=False, n=None):
    return reports.read_result(head, body, failed, n)


def llm_saying(text, seen=None):
    def _llm(system, user, **kw):
        if seen is not None: seen.append((system, user))
        return text
    return _llm


# ── the three answers a line can give ───────────────────────────────────────────────────
def test_a_report_with_no_route_block_is_not_routed():
    """Every report that exists predates this. None of them may change behaviour."""
    assert reports.routed({'type': 'sql'}) is False
    assert reports.routed({'type': 'sql', 'reach': 'wrong', 'triage': True}) is False
    assert reports.routed({'type': 'sql', 'route': {}}) is False


def test_a_line_set_to_anything_makes_the_report_routed():
    assert reports.routed({'route': {'work': {'how': 'ai', 'when': 'any error'}}}) is True


def test_an_unset_line_falls_back_to_what_that_destination_has_always_done():
    """A report you set up is work you wanted done: the Timeline AND the work rail every run,
    and delivery every run. Only the interruption stays off until it is asked for."""
    assert reports.route_of({'route': {'timeline': {'how': 'never'}}}, 'work')[0] == 'always'
    cfg = {'route': {'work': {'how': 'ai', 'when': 'any error'}}}
    assert reports.route_of(cfg, 'timeline')[0] == 'always'
    assert reports.route_of(cfg, 'send')[0] == 'always'
    assert reports.route_of(cfg, 'alert')[0] == 'never'
    assert reports.route_of(cfg, 'work') == ('ai', 'any error')


def test_a_line_asking_the_ai_with_nothing_to_judge_by_is_not_asking():
    """An empty sentence is a question the model cannot answer. It means the line is on."""
    assert reports.route_of({'route': {'work': {'how': 'ai', 'when': '   '}}}, 'work')[0] == 'always'


def test_a_word_we_do_not_know_falls_back_to_what_that_line_means_by_default():
    """Never to a guess: an unreadable route is that line's own default, both ways round."""
    assert reports.route_of({'route': {'work': {'how': 'sometimes'}}}, 'work')[0] == 'always'
    assert reports.route_of({'route': {'alert': {'how': 'sometimes'}}}, 'alert')[0] == 'never'


# ── no sentence anywhere means no model is asked ────────────────────────────────────────
def test_a_straight_report_with_no_ai_line_asks_nothing():
    """Rows, everything on `every run`: it routes itself and costs no call (2026-09-17)."""
    cfg = {'route': {'timeline': {'how': 'always'}, 'work': {'how': 'never'}}}
    assert reports.asks_ai(cfg) is False
    seen = []
    d = reports.decide(cfg, res(), llm_saying('TIMELINE: no', seen))
    assert seen == []
    assert (d['timeline'], d['work']) == (True, False)


def test_one_ai_line_is_enough_to_ask():
    assert reports.asks_ai({'route': {'work': {'how': 'ai', 'when': 'any error'}}}) is True


# ── the judge ───────────────────────────────────────────────────────────────────────────
def test_the_ai_decides_each_line_it_was_asked_about():
    cfg = {'route': {'timeline': {'how': 'ai', 'when': 'anything worth knowing'},
                     'work': {'how': 'ai', 'when': 'any error'}}}
    d = reports.decide(cfg, res(), llm_saying('TIMELINE: yes - PROC-8 errored twice\nWORK: yes - same'))
    assert (d['timeline'], d['work']) == (True, True)
    assert d['why'] == 'PROC-8 errored twice'


def test_a_no_on_every_line_is_a_run_that_reaches_nobody():
    cfg = {'route': {'timeline': {'how': 'ai', 'when': 'any error'}, 'send': {'how': 'never'}}}
    d = reports.decide(cfg, res(), llm_saying('TIMELINE: no'))
    assert d['timeline'] is False and d['why'] == ''


def test_the_lines_it_was_not_asked_about_are_not_the_ais_to_answer():
    """`every run` means every run. A model volunteering otherwise does not get a vote."""
    cfg = {'route': {'timeline': {'how': 'always'}, 'work': {'how': 'ai', 'when': 'any error'}}}
    d = reports.decide(cfg, res(), llm_saying('TIMELINE: no\nWORK: no'))
    assert (d['timeline'], d['work']) == (True, False)


def test_never_means_never_whatever_the_ai_says():
    cfg = {'route': {'work': {'how': 'never'}, 'timeline': {'how': 'ai', 'when': 'x'}}}
    assert reports.decide(cfg, res(), llm_saying('TIMELINE: yes\nWORK: yes'))['work'] is False


# ── the failures, which must all land the same way: on you ──────────────────────────────
def test_an_unanswered_line_reaches_you_rather_than_going_quiet():
    """The bug this replaces went the other way: a missing verdict fell through to counting lines,
    so a rule asking for silence delivered every run instead."""
    cfg = {'route': {'timeline': {'how': 'ai', 'when': 'any error'},
                     'work': {'how': 'ai', 'when': 'any error'}}}
    d = reports.decide(cfg, res(), llm_saying('Sure! Here is my assessment: everything looks fine.'))
    assert (d['timeline'], d['work']) == (True, True)
    assert 'did not judge' in d['why']


def test_a_judge_that_answers_half_the_question_answered_none_of_it():
    cfg = {'route': {'timeline': {'how': 'ai', 'when': 'a'}, 'work': {'how': 'ai', 'when': 'b'}}}
    d = reports.decide(cfg, res(), llm_saying('TIMELINE: no'))
    assert (d['timeline'], d['work']) == (True, True)


def test_a_judge_that_will_not_run_at_all_reaches_you():
    def broken(system, user, **kw): raise RuntimeError('no brain configured')
    cfg = {'route': {'timeline': {'how': 'ai', 'when': 'any error'}}}
    d = reports.decide(cfg, res(), broken)
    assert d['timeline'] is True and 'did not judge' in d['why']


def test_no_brain_at_all_reaches_you():
    cfg = {'route': {'timeline': {'how': 'ai', 'when': 'any error'}}}
    assert reports.decide(cfg, res(), None)['timeline'] is True


def test_a_failed_run_reaches_you_without_asking_anyone():
    """A check that could not run is not a clear one, and there is nothing to judge."""
    seen = []
    cfg = {'route': {'timeline': {'how': 'ai', 'when': 'any error'}, 'work': {'how': 'never'}}}
    d = reports.decide(cfg, res(failed=True), llm_saying('TIMELINE: no', seen))
    assert seen == []
    assert (d['timeline'], d['why']) == (True, 'the report failed to run')
    assert d['work'] is False        # ...but never still means never


# ── what the model is actually shown ────────────────────────────────────────────────────
def test_the_prompt_asks_only_about_the_lines_set_to_ask_the_ai():
    cfg = {'route': {'timeline': {'how': 'always'}, 'work': {'how': 'ai', 'when': 'any error at all'},
                     'alert': {'how': 'ai', 'when': 'a job has not run in two hours'}}}
    p = reports.judge_prompt(cfg)
    assert 'WORK: yes|no' in p and 'ALERT: yes|no' in p and 'TIMELINE' not in p
    assert 'any error at all' in p and 'a job has not run in two hours' in p


def test_the_prompt_is_the_one_the_judge_is_given():
    """`see the prompt` on the card is not a paraphrase of what runs."""
    seen = []
    cfg = {'route': {'work': {'how': 'ai', 'when': 'any error at all'}}}
    reports.decide(cfg, res(head='9 rows', body='PROC-8 failed'), llm_saying('WORK: yes', seen))
    system, user = seen[0]
    assert reports.judge_prompt(cfg) in system
    assert '9 rows' in user and 'PROC-8 failed' in user


def test_the_judge_reads_the_result_of_a_report_that_has_no_prompt_of_its_own():
    """Rows go to the judge as rows - that is how a plain SQL report gets an AI rule."""
    seen = []
    cfg = {'route': {'work': {'how': 'ai', 'when': 'any unit under 70'}}}
    reports.decide(cfg, res(head='3 rows', body='unit 4 | 68'), llm_saying('WORK: yes - unit 4 is at 68', seen))
    assert 'unit 4 | 68' in seen[0][1]


# ── the verdict line goes away for a routed report ──────────────────────────────────────
def test_a_routed_report_does_not_staple_the_verdict_contract_to_your_prompt():
    """It was only ever there because code had to read prose. The judge reads it now."""
    assert reports.contract_for({'route': {'work': {'how': 'ai', 'when': 'x'}}}) == ''
    assert reports.contract_for({'reach': 'wrong'}) == reports.VERDICT_CONTRACT


# ── and everything that existed before goes on working ──────────────────────────────────
def test_an_old_report_is_decided_by_the_rules_it_was_set_up_with():
    assert reports.decide({'reach': 'always'}, res('0 rows', ''), None)['timeline'] is True
    assert reports.decide({'reach': 'wrong'}, res('0 rows', ''), None)['timeline'] is False
    quiet = reports.decide({'reach': 'wrong'}, res('0 rows', ''), None)
    assert quiet['work'] is False


def test_an_old_report_that_could_start_work_still_can():
    d = reports.decide({'reach': 'always', 'triage': True}, res(), None)
    assert (d['timeline'], d['work']) == (True, True)


def test_an_old_report_still_mails_what_it_always_mailed_when_it_goes_quiet_for_you():
    """44539620: reach and deliver are different questions, and they stay different ones."""
    cfg = {'reach': 'wrong', 'deliver': {'to': 'cfo@x.com', 'send': 'always'}}
    d = reports.decide(cfg, res('0 rows', ''), None)
    assert (d['timeline'], d['send']) == (False, True)


# ── and you can watch the rule fire before you trust it ─────────────────────────────────
# A rule you have never seen fire is a rule you cannot trust, and waiting for tomorrow's run to
# find out the AI reads your sentence differently is not a way to set one up.
class ReplayingTheRuleOnRunsThatAlreadyHappened(unittest.TestCase):
    def setUp(self):
        self.sid = server.store.save_source({'Channel': 'report', 'Address': 'replay-me', 'Active': 1, 'Owner': 'test',
                                             'ConfigJson': json.dumps({'type': 'mssql', 'title': 'Process errors'})}, 'test')
        for at, subject, summary, failed in [('2026-09-16 15:00:00', 'Process errors — 2 rows', 'PROC-8 errored twice', 0),
                                             ('2026-09-16 16:00:00', 'Process errors — 0 rows', 'all four jobs ran', 0),
                                             ('2026-09-16 17:00:00', 'Process errors — FAILED', 'Report error: no connector', 1)]:
            server.store.add_report_run(self.sid, {'at': at, 'type': 'mssql', 'title': 'Process errors',
                                                   'subject': subject, 'summary': summary, 'failed': failed})

    def test_the_card_can_ask_what_it_would_have_done_without_running_anything(self):
        judge = lambda sys_, usr, **kw: ('WORK: yes - PROC-8 errored twice' if 'errored' in usr else 'WORK: no - all four jobs ran')
        with mock.patch('taskuary.server._llm', return_value=judge):
            r = c.post(f'/api/reports/{self.sid}/replay',
                       json={'type': 'mssql', 'route': {'work': {'how': 'ai', 'when': 'any error at all'}}}).json()
        runs = {x['at'][-8:]: x for x in r['data']}
        self.assertTrue(r['asksAi'])
        self.assertIn('any error at all', r['prompt'])
        self.assertEqual(runs['17:00:00']['why'], 'the report failed to run')   # newest first, and a failure needs no judge
        self.assertTrue(runs['15:00:00']['work'])
        self.assertFalse(runs['16:00:00']['work'])
        self.assertTrue(runs['16:00:00']['timeline'])      # the line nobody set still does what it always did

    def test_a_card_that_asks_nothing_replays_without_a_brain(self):
        with mock.patch('taskuary.server._llm', side_effect=AssertionError('no model may be built')):
            r = c.post(f'/api/reports/{self.sid}/replay',
                       json={'type': 'mssql', 'route': {'work': {'how': 'never'}, 'timeline': {'how': 'always'}}}).json()
        self.assertFalse(r['asksAi'])
        self.assertTrue(all(x['timeline'] and not x['work'] for x in r['data']))

    def test_a_report_that_does_not_exist_is_a_404(self):
        self.assertEqual(c.post('/api/reports/999999/replay', json={}).status_code, 404)


# ── a check that could not run is work, when the card says work ─────────────────────────
def test_a_failed_routed_run_is_work_because_a_broken_monitor_is_something_to_deal_with():
    """The quietest way for a monitor to break is to file its own outage as news."""
    cfg = {'route': {'work': {'how': 'ai', 'when': 'any error'}}}
    assert reports.decide(cfg, res(failed=True), None)['work'] is True


def test_an_old_report_still_refuses_to_make_a_task_out_of_an_outage():
    """Nothing already running starts doing something new on the day this ships."""
    assert reports.decide({'triage': True, 'reach': 'always'}, res(failed=True), None)['work'] is False


# ── the interruption is not "the phone" ─────────────────────────────────────────────────
def test_the_alert_line_is_named_for_being_immediate_not_for_a_device():
    """It goes to whichever live channel the owner picked - as often email as WhatsApp (the owner,
    2026-09-17: "why does this say phone if it can go to email?")."""
    assert 'phone' not in reports.LINE_SAYS['alert']
    assert 'right away' in reports.LINE_SAYS['alert']
