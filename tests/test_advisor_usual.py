"""SLICE 4: THE ADVISOR'S DEFAULTS AND MEMORY-FACT LINES (the memory redesign, 2026-10-25). The Advisor's recommendation and its reason stay
ONE line on the strip (the owner: "Reply: you usually answer Erin within the hour; this is 3h"); Remind me opens on the learned day
(ruling 7); a hand-off rests on whom the owner hands that kind of ask to; Chase is late on the person's own day (ruling 8); and with nothing
checkable there is no line (ruling 1). All counted from what the owner DID in the yardstick's Northwind world - invented people only."""
import json
from datetime import datetime, timedelta
from unittest import mock
import pytest
from taskuary import advisor, funnel, rulebook, terminal, usual
from taskuary.testing import Factory
from tests import memory_cases as C
from tests.memory_cases import put_off, reflected


@pytest.fixture
def w():
    with mock.patch.object(terminal, 'live_sessions', lambda tail=0: []), mock.patch.object(funnel, '_agenda', lambda _s, **kw: []), \
         mock.patch.object(advisor, 'notice', lambda *a, **k: None):
        s, facts = C.world(); funnel.invalidate()
        yield s, facts
        funnel.invalidate()


def ask(s, who, title, body, hours=3):
    f, at = Factory(s), (datetime.now() - timedelta(hours=hours)).strftime('%Y-%m-%d %H:%M:%S')
    t = f.task(title=title, kind='task')
    f.message(task_id=t, subject=title, body=body, from_name=C.P[who][0], from_email=C.P[who][1], conversation_id=f'email:{title}', sent_at=at)
    funnel.invalidate()
    return t


def test_erin_at_three_hours_gets_her_lateness_beside_the_lit_reply(w):
    s, facts = w
    t = ask(s, 'erin', 'Q4 headcount forecast', 'Can you send me the Q4 headcount forecast before the leadership sync?')
    d = advisor.decide(s, f'task:{t}', preread=False)
    assert (d['state'], d['verb']) == ('asked_late', 'reply')
    assert d['line'] == 'You usually answer Erin within the hour; this is 3h.'
    assert len(d['line']) <= 60, 'one line on the strip, read whole on a phone'
    assert d['evidence'] and set(d['evidence']) <= {f'msg{m}' for m in facts['erin_fast']}, 'it cites the answers it was counted from'


def test_no_line_when_nothing_is_checkable(w):
    s, _ = w
    fresh = ask(s, 'erin', 'Quick check on the offsite', 'Is the offsite still on Thursday?', hours=0.3)      # inside her usual
    stranger = ask(s, 'omar', 'Expense policy wording', 'Per diem or daily allowance?')                         # nobody's usual yet
    for t in (fresh, stranger):
        d = advisor.decide(s, f'task:{t}', preread=False)
        assert (d['state'], d['verb'], d['line']) == ('asked', 'reply', ''), d


def test_a_payworth_renewal_opens_remind_me_on_the_day_its_how_you_work_line_says(w):
    """Remind me's day comes from a How you work line the owner can see and correct (the owner, 2026-10-25) - the count alone sets none."""
    s, facts = w
    t = ask(s, 'payworth', 'Payworth renewal notice', 'Your annual subscription renews next month.')
    assert usual.remind_day(s, t) is None, 'counted, but no line says it yet'
    reflected(s, put_off(s, 'payworth', 13))
    d = usual.remind_day(s, t)
    assert d['day'] == 'Friday' and d['by'] == 'renewals@payworth.example' and d['line'] == 'You put mail from renewals@payworth.example off to Friday'
    on = datetime.strptime(d['on'], '%Y-%m-%d').date()
    assert on.weekday() == 4 and on > datetime.now().date()
    from fastapi.testclient import TestClient
    from taskuary import server
    with mock.patch.object(server, 'store', s): got = TestClient(server.app).get(f'/api/tasks/{t}/remind/usual').json()
    assert got['on'] == d['on'] and got['line'] == d['line'], 'the picker reads the same day, and the line it came from'
    # ...and a sender whose mail was never put off has no usual day
    assert usual.remind_day(s, ask(s, 'gail', 'Rota', 'Can you check the rota?')) is None


def test_the_owner_rewords_the_day_and_the_default_follows_then_deletes_it_and_there_is_none(w):
    s, _ = w
    t = ask(s, 'payworth', 'Payworth renewal notice', 'Your annual subscription renews next month.')
    reflected(s, put_off(s, 'payworth', 13))
    doc = s.get_doc('learned')
    s.save_doc('learned', doc.replace('off to Friday [', 'off to Thursday ['), 'owner')
    assert usual.remind_day(s, t)['day'] == 'Thursday', 'the owner said Thursday'
    reflected(s)
    assert usual.remind_day(s, t)['day'] == 'Thursday', '...and the next reflection keeps their word'
    line = next(l for l in s.get_doc('learned').splitlines() if 'k: put off renewals@payworth.example' in l)
    s.save_doc('learned', s.get_doc('learned').replace(line + '\n', ''), 'owner')
    assert usual.remind_day(s, t) is None
    reflected(s)
    assert usual.remind_day(s, t) is None and 'renewals@payworth.example off to' not in s.get_doc('learned'), 'deleted stays deleted'


def test_an_owner_line_of_their_own_sets_the_day(w):
    s, _ = w
    t = ask(s, 'spendly', 'Spendly invoice', 'Your invoice is ready.')
    doc = s.get_doc('learned')
    s.save_doc('learned', doc.replace('## How you work\n', '## How you work\n- Mail from spendly.example waits for Monday\n', 1), 'owner')
    d = usual.remind_day(s, t)
    assert (d['day'], d['by'], d['evidence']) == ('Monday', 'spendly.example', [])


def test_a_payroll_ask_lights_hand_off_with_the_ray_line(w):
    s, facts = w
    t = ask(s, 'site1', 'Payroll correction for a site 5', 'One of our staff was paid the wrong rate last cycle - can this be fixed?', hours=1)
    seen = []
    def brain(system, user, **kw):
        seen.append(user)
        ok = 'WHOM YOU HANDED THEIR ASKS TO: ray@northwind.example' in user
        return json.dumps({'verb': 'forward' if ok else 'reply', 'line': 'Ray handles payroll for you.' if ok else '', 'evidence': ['task1'] if ok else []})
    rev = advisor.revision(s, 'task', t)
    advisor.judge(s, advisor.SHOWN, 'task', t, rev, tier=2, llm=brain, key=f'task:{t}')
    assert seen and 'WHOM YOU HANDED THEIR ASKS TO: ray@northwind.example, 2 of 2 times' in seen[-1]
    d = advisor.decide(s, f'task:{t}', preread=False)
    assert (d['verb'], d['by'], d['line']) == ('forward', 'model', 'Ray handles payroll for you.')


def test_hand_it_to_a_person_opens_on_ray_for_a_payroll_ask_chosen_not_sent(w):
    """The usual recipient, pre-filled (the owner, 2026-10-25): whom this sender's asks were handed to before. Nothing is sent."""
    s, _ = w
    t = ask(s, 'site1', 'Payroll correction for a site 6', 'Another rate was wrong last cycle - can this be fixed?', hours=1)
    sent = s._one("SELECT COUNT(*) n FROM message WHERE Direction='out'")['n']
    u = usual.handoff_usual(s, t)
    assert (u['to'], u['channel'], u['from'], u['n']) == ('ray@northwind.example', 'email', 'east.manager@northwind.example', 2)
    from fastapi.testclient import TestClient
    from taskuary import server
    with mock.patch.object(server, 'store', s):
        c = TestClient(server.app)
        assert c.get(f'/api/tasks/{t}/handoff/usual').json()['to'] == 'ray@northwind.example'
        assert c.get(f"/api/tasks/{ask(s, 'erin', 'Offsite agenda', 'Can you check the agenda?')}/handoff/usual").json() == {}, 'nobody learned'
        assert c.get('/api/tasks/999999/handoff/usual').status_code == 404
    assert s._one("SELECT COUNT(*) n FROM message WHERE Direction='out'")['n'] == sent
    assert not s._rows("SELECT 1 FROM audit WHERE EntityId=? AND Action='handoff'", (t,)), 'chosen, not sent'


def test_one_hand_off_is_no_usual(w):
    s, _ = w
    t = ask(s, 'omar', 'Travel booking', 'Can you book the travel?')
    old = ask(s, 'omar', 'Earlier travel', 'Can you book it?')
    s.audit('task', old, 'handoff', 'owner', 'human', {'to': 'gail@northwind.example', 'channel': 'email'})
    assert usual.handoff_usual(s, t) is None


def test_erins_usual_is_in_what_the_model_reads(w):
    s, _ = w
    t = ask(s, 'erin', 'Board deck numbers', 'Can you check the board deck numbers?')
    p = advisor._prompt(s, advisor.SHOWN, advisor._item(s, 'task', t, f'task:{t}'), [], 2, 'task', t)
    assert 'HOW SOON YOU ANSWER erin@northwind.example: within the hour - the median of your last 6 answers' in p
    assert 'this one has waited 3h' in p


def test_chase_is_late_on_the_persons_own_day_once_three_answers_say_it(w):
    s, _ = w
    gail = C.P['gail'][1]
    t = s.create_task({'Title': 'Headcount sign-off', 'Status': 'waiting', 'Assignee': f'person:{gail}'}, 'owner')
    s._exec('UPDATE task SET WaitingSince=? WHERE TaskId=?', ((datetime.now() - timedelta(days=4)).strftime('%Y-%m-%d %H:%M:%S'), t))
    it = {'key': f'task:{t}', 'tid': t, 'lane': 'theirs', 'kind': 'task'}
    assert rulebook.state(s, it, [{'verb': 'chase'}])[0] in ('waiting_late', 'waiting')            # three working days: the rule's day
    for i in range(3):                                                                                # ...then Gail's own: she answers in a day
        s._exec("INSERT INTO outcome (Kind, TargetKind, TargetId, At, FactsJson, ResolvedAt, Verdict) VALUES ('reply.sent','task',?,?,?,?,'answered')",
                (t, '2026-09-01 09:00:00', json.dumps({'who': gail, 'answer_days': 1}), '2026-09-02 09:00:00'))
    st, f = rulebook.state(s, it, [{'verb': 'chase'}])
    assert st == 'waiting_late_usual'
    assert rulebook._say(st, **f) == f"Gail usually answers in a day; this is {f['days']} days."


def test_a_learned_day_never_reaches_a_stranger_on_a_shared_mail_provider(w):
    """A shared mail provider is nobody's organisation: a day learned from one freelancer there is not a stranger's day (people lines
    reach a task's own people, never strangers - the owner, 2026-10-25). freemail.example stands in for the real providers."""
    s, _ = w
    f = Factory(s)
    pub = getattr(usual, 'PUBLIC_MAIL', set()) | {'freemail.example'}
    def mail(frm):
        t = f.task(title=f'Note from {frm}', kind='task')
        f.message(task_id=t, subject='A note', body='Can you look at this?', from_name=frm, from_email=frm, conversation_id=f'email:{frm}')
        return t
    jo, kim = mail('jo.freelance@freemail.example'), mail('kim.parent@freemail.example')
    tag = f' [s:4 | ev: fs{jo} | seen: 2026-10-20 | k: put off jo.freelance@freemail.example]'
    with mock.patch.object(usual, 'PUBLIC_MAIL', pub, create=True):
        for line in ('- You put mail from jo.freelance@freemail.example off to Friday' + tag, '- Mail from jo.freelance@freemail.example waits for Friday'):
            s.save_doc('learned', '## How you work\n' + line + '\n', 'owner')
            assert usual.remind_day(s, jo)['day'] == 'Friday', line
            assert usual.remind_day(s, kim) is None, line
