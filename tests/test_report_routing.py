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
from taskuary.store import MemoryStore

c = TestClient(server.app)


def res(head='4 rows', body='a\nb', failed=False, n=None):
    return reports.read_result(head, body, failed, n)


def judged(cfg, llm):
    """What the judge answered for the lines set to ask the AI, read off `decide`."""
    d = reports.decide(cfg, res(), llm)
    return {l: d[l] for l in reports.LINES if reports.route_of(cfg, l)[0] == 'ai'}


def llm_saying(text, seen=None):
    def _llm(system, user, **kw):
        if seen is not None: seen.append((system, user))
        return text
    return _llm


# ── the four answers a line can give ────────────────────────────────────────────────────
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


def test_the_judge_answers_booleans_and_writes_no_prose():
    """The sentence was there because the thing answering happened to be able to write. It is not a
    requirement of routing, and for three of the four lines it was computed and thrown away."""
    cfg = {'route': {'work': {'how': 'ai', 'when': 'a job has not run in over two hours'},
                     'timeline': {'how': 'ai', 'when': 'anything worth reading'}}}
    said = judged(cfg, llm_saying('WORK: yes\nTIMELINE: no'))
    assert said == {'work': True, 'timeline': False}
    assert 'why' not in said


def test_a_judge_that_volunteers_a_reason_is_not_punished_for_it():
    """An older model, or one that ignores the instruction, still routes correctly - the reason is
    simply ignored rather than failing the parse."""
    cfg = {'route': {'work': {'how': 'ai', 'when': 'x'}}}
    assert judged(cfg, llm_saying('WORK: yes - the export is late')) == {'work': True}


def test_a_line_the_judge_skipped_leaves_the_run_unjudged_and_it_reaches_you():
    cfg = {'route': {'work': {'how': 'ai', 'when': 'x'}, 'alert': {'how': 'ai', 'when': 'y'}}}
    assert judged(cfg, llm_saying('WORK: no')) == {'work': True, 'alert': True}


def test_a_judge_that_raises_leaves_the_run_unjudged_and_it_reaches_you():
    def boom(*a, **kw): raise RuntimeError('502')
    assert judged({'route': {'work': {'how': 'ai', 'when': 'x'}}}, boom) == {'work': True}


def test_the_prompt_no_longer_asks_for_a_sentence():
    assert 'one short sentence' not in reports.JUDGE_SYSTEM
    assert reports.JUDGE_TOKENS < 300        # it was sized for four yes/nos AND a sentence each


def test_the_alerts_reason_is_the_owners_own_rule_and_no_model_writes_it():
    """An interrupt with no reason is a ping, so it quotes the sentence the owner wrote rather than
    a model's paraphrase of it - and nothing on this road asks anybody for prose."""
    cfg = {'route': {'alert': {'how': 'ai', 'when': 'a job has not run in over two hours'}}}
    d = reports.decide(cfg, res(), llm_saying('ALERT: yes'))
    assert d['alert'] is True
    assert d['why'] == 'your rule: a job has not run in over two hours'


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


def test_a_judge_that_answers_half_the_question_answered_none_of_it():
    cfg = {'route': {'timeline': {'how': 'ai', 'when': 'a'}, 'work': {'how': 'ai', 'when': 'b'}}}
    d = reports.decide(cfg, res(), llm_saying('TIMELINE: no'))
    assert (d['timeline'], d['work']) == (True, True)


def test_a_judge_that_will_not_run_at_all_reaches_you():
    def broken(system, user, **kw): raise RuntimeError('no brain configured')
    cfg = {'route': {'timeline': {'how': 'ai', 'when': 'any error'}}}
    assert reports.decide(cfg, res(), broken)['timeline'] is True


def test_no_brain_at_all_reaches_you():
    cfg = {'route': {'timeline': {'how': 'ai', 'when': 'any error'}}}
    assert reports.decide(cfg, res(), None)['timeline'] is True


def test_a_failed_run_reaches_you_in_the_app_and_nowhere_else():
    """The owner, 2026-09-27: "it's okay if it errors out only in the app". A check that could not
    run is one row on the Timeline - never a task, never a ping, never sent to its recipients - and
    there is nothing to judge, so nobody is asked."""
    seen = []
    cfg = {'route': {'timeline': {'how': 'never'}, 'work': {'how': 'always'}, 'alert': {'how': 'always'},
                     'send': {'how': 'always'}}}
    d = reports.decide(cfg, res(failed=True), llm_saying('TIMELINE: no', seen))
    assert seen == []
    assert d == {'timeline': True, 'work': False, 'alert': False, 'send': False, 'why': 'the report failed to run'}


# ── which judge answers ─────────────────────────────────────────────────────────────────
# The report's brain WRITES the summary; the judge answers four yes/nos ABOUT it. They were one
# setting while both were chat models, because two could quietly differ. They are two now because
# only one of the two jobs can be done by a model that cannot write.
def _with_jev():
    s = MemoryStore()
    cid = s.get_connector_by_type('typesafe')['ConnectorId']
    s.save_connector({'ConnectorId': cid, 'Secret': 'sk-x', 'Active': 1}, 't')
    s.set_setting('judge_ai', f'connector:{cid}', 't')
    return s


def test_unset_is_the_reports_own_brain_which_is_today():
    """The default has to be indistinguishable from the behaviour it replaces."""
    sentinel = object()
    assert reports.judge_for(MemoryStore(), {}, sentinel) is sentinel


def test_a_typesafe_judge_asks_jev_and_returns_booleans():
    cfg = {'route': {'work': {'how': 'ai', 'when': 'a job has not run in over two hours'}}}
    with mock.patch('taskuary.jev.ask', return_value={'work': (True, 0.91)}) as ask:
        out = reports.judge_for(_with_jev(), cfg, None)('0 rows\n\nnothing came back', ['work'], cfg)
    assert out == {'work': True}
    state, questions = ask.call_args[0][1], ask.call_args[0][2]
    assert '0 rows' in state
    # the owner's own sentence is the criterion, word for word, so the card shows what is sent...
    assert questions['work'][1] == 'a job has not run in over two hours'
    # ...and the instruction carries the same evidence rule the chat judge's prompt does, which the
    # decision model was not being told at all
    assert reports.LINE_SAYS['work'] in questions['work'][0]
    assert reports.EVIDENCE_RULE in questions['work'][0]


def test_a_jev_that_fails_says_it_did_not_answer_so_the_run_reaches_you():
    cfg = {'route': {'work': {'how': 'ai', 'when': 'x'}}}
    with mock.patch('taskuary.jev.ask', side_effect=RuntimeError('529')):
        assert reports.judge_for(_with_jev(), cfg, None)('s', ['work'], cfg) is None


def test_decide_routes_through_the_judge_when_given_one():
    cfg = {'route': {'work': {'how': 'ai', 'when': 'x'}, 'timeline': {'how': 'never'}}}
    d = reports.decide(cfg, res(), llm=None, judge=lambda *a: {'work': True})
    assert d['work'] is True and d['timeline'] is False


def test_a_judge_that_did_not_answer_leaves_the_run_unjudged_and_it_reaches_you():
    cfg = {'route': {'work': {'how': 'ai', 'when': 'x'}, 'alert': {'how': 'ai', 'when': 'y'}}}
    d = reports.decide(cfg, res(), llm=None, judge=lambda *a: None)
    assert (d['work'], d['alert']) == (True, True)


def test_the_one_place_that_knows_which_road_picks_the_decision_model_over_the_brain():
    """Passed apart, never sniffed apart: `decide` must not have to guess what it was handed."""
    cfg = {'route': {'work': {'how': 'ai', 'when': 'x'}}}
    with mock.patch('taskuary.jev.ask', return_value={'work': (False, 0.04)}):
        assert reports.decide_for(_with_jev(), cfg, res(), llm_saying('WORK: yes'))['work'] is False
    # ...and with nothing chosen it is the brain that answers, exactly as before
    assert reports.decide_for(MemoryStore(), cfg, res(), llm_saying('WORK: yes'))['work'] is True


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


# ── a rule is arithmetic, and stays arithmetic ──────────────────────────────────────────
def test_a_rule_line_reads_the_number_without_asking_anyone():
    """"Spend over 500" is a comparison a model should not be trusted with (teller, simplefin)."""
    seen = []
    cfg = {'route': {'alert': {'how': 'rule', 'rule': 'more_than', 'count': 500}}}
    assert reports.decide(cfg, res('1,518 spent', ''), llm_saying('ALERT: no', seen))['alert'] is True
    assert reports.decide(cfg, res('499 spent', ''), None)['alert'] is False
    assert seen == [] and not reports.asks_ai(cfg)
    assert reports.route_of(cfg, 'alert') == ('rule', 'more than 500 came back')


def test_a_rule_nobody_can_read_means_the_line_is_simply_on():
    assert reports.route_of({'route': {'alert': {'how': 'rule', 'rule': 'when_it_feels_wrong'}}}, 'alert') == ('always', '')


# ── every report is on the card ─────────────────────────────────────────────────────────
# The old rules (reach, an alert condition, the triage switch) are written down as the card ONCE,
# meaning exactly what they did (the owner, 2026-09-27: one rule set).
def test_an_old_report_on_every_run_becomes_every_run_and_no_work():
    n = reports.from_old_rules({'type': 'mssql', 'title': 'AR'})
    assert n['route'] == {'timeline': {'how': 'always'}, 'work': {'how': 'never'}, 'alert': {'how': 'never'}, 'send': {'how': 'always'}}


def test_an_old_report_that_could_start_work_still_can():
    n = reports.from_old_rules({'type': 'mssql', 'reach': 'always', 'triage': True})
    assert n['route']['work'] == {'how': 'always'} and 'triage' not in n and 'reach' not in n


def test_an_old_rule_moves_onto_the_lines_it_governed():
    n = reports.from_old_rules({'type': 'assistant', 'alert': {'when': 'something_came_back', 'to': '+15550100', 'channel': 'whatsapp'}})
    rule = {'how': 'rule', 'rule': 'something_came_back'}
    assert n['route']['timeline'] == rule and n['route']['alert'] == rule and n['route']['work'] == {'how': 'never'}
    assert n['alert'] == {'to': '+15550100', 'channel': 'whatsapp'}                  # where it goes stays; what fires it moved


def test_only_when_wrong_becomes_the_same_question_asked_of_the_judge():
    n = reports.from_old_rules({'reach': 'wrong', 'deliver': {'to': 'cfo@example.com', 'send': 'always'}})
    assert n['route']['timeline'] == {'how': 'ai', 'when': 'something in it is wrong, or needs me'}
    assert n['route']['send'] == {'how': 'always'} and 'send' not in n['deliver']


def test_an_alert_on_failure_is_gone_because_a_failure_stays_in_the_app():
    n = reports.from_old_rules({'alert': {'when': 'failed', 'to': 'me@example.com'}})
    assert n['route']['alert'] == {'how': 'never'}


def test_the_assistant_on_its_own_default_keeps_its_judge():
    n = reports.from_old_rules({'type': 'assistant'})
    assert n['route']['timeline'] == n['route']['work'] == {'how': 'ai', 'when': reports.ASSISTANT_WHEN}


def test_a_report_already_on_the_card_is_only_filled_in():
    cfg = {'route': {'work': {'how': 'ai', 'when': 'any error'}}, 'reach': 'wrong'}
    n = reports.from_old_rules(cfg)
    assert n['route']['work'] == {'how': 'ai', 'when': 'any error'} and n['route']['timeline'] == {'how': 'always'}
    assert 'reach' not in n
    assert reports.from_old_rules(n) == n                                            # once converted, it stays put


def test_a_report_saved_the_old_way_is_stored_as_the_card():
    s = MemoryStore()
    sid = s.save_source({'Channel': 'report', 'Address': 'x', 'Active': 1, 'ConfigJson': json.dumps({'type': 'mssql', 'reach': 'wrong'})}, 't')
    cfg = json.loads(s.get_source(sid)['ConfigJson'])
    assert 'reach' not in cfg and cfg['route']['timeline']['how'] == 'ai'


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


# ── the interruption is not "the phone" ─────────────────────────────────────────────────
def test_the_alert_line_is_named_for_being_immediate_not_for_a_device():
    """It goes to whichever live channel the owner picked - as often email as WhatsApp (the owner,
    2026-09-17: "why does this say phone if it can go to email?")."""
    assert 'phone' not in reports.LINE_SAYS['alert']
    assert 'right away' in reports.LINE_SAYS['alert']


# ── the Assistant with no rule of its own ───────────────────────────────────────────────
# A report is work you asked for, so a line nobody set means every run. The Assistant is a voice
# that checks in every half hour, and every run from a voice is noise (the owner, 2026-09-20: "only
# show up when the assistant has an idea that matters, not always").
def test_the_assistant_with_no_rule_asks_whether_it_matters_on_both_lines():
    cfg = {'type': 'assistant'}
    assert reports.route_of(cfg, 'timeline') == ('ai', reports.ASSISTANT_WHEN)
    assert reports.route_of(cfg, 'work') == ('ai', reports.ASSISTANT_WHEN)
    assert reports.route_of(cfg, 'alert')[0] == 'never'
    assert reports.asks_ai(cfg)
    assert reports.ASSISTANT_WHEN in reports.judge_prompt(cfg)


def test_an_assistant_that_was_given_a_line_keeps_it():
    assert reports.route_of({'type': 'assistant', 'route': {'timeline': {'how': 'always'}}}, 'timeline') == ('always', '')
    assert reports.route_of({'type': 'assistant', 'watch_source_ids': [3]}, 'timeline') == ('always', '')   # a monitor posts its findings
    assert reports.route_of({'type': 'mssql'}, 'work') == ('always', '')


def test_the_assistants_default_is_judged_and_a_no_holds_both_lines():
    asked = []
    def judge(state, ask, cfg): asked.append(list(ask)); return {l: False for l in ask}
    d = reports.decide({'type': 'assistant'}, res('Assistant', '- a status note'), judge=judge)
    assert asked == [['timeline', 'work']]
    assert (d['timeline'], d['work'], d['alert']) == (False, False, False)


def test_the_assistants_default_reaches_you_when_no_judge_answers():
    d = reports.decide({'type': 'assistant'}, res('Assistant', '- a line'), None)
    assert (d['timeline'], d['work']) == (True, True)


def test_the_card_shows_the_sentence_the_server_asks():
    from pathlib import Path
    src = (Path(__file__).resolve().parents[1] / 'website' / 'src' / 'ReportsView.jsx').read_text(encoding='utf-8')
    assert f'export const ASSISTANT_WHEN = "{reports.ASSISTANT_WHEN}"' in src
