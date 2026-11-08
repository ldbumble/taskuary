"""WHERE AN ITEM STANDS, AS FACTS - AND THE MODEL'S ONE DECISION (the Advisor design, phase A, 2026-10-23; the owner, 2026-11-02: "never
ever use hard coded rules, let the ai see everything"). rulebook.facts names each state from facts the app keeps and says its fact; the
model reads that, every verb the row offers and the owner's record, and decides every light - read the same by every surface: the desk
canvas (the rail's key), the Tasks tab (task:N), a phone chat (remote_assistant.primary and the card's line). The desk at phone width is the
page's (website/test/rulebookMatrix.test.mjs). Invented Northwind people only."""
import json, re
from datetime import date, datetime, timedelta
from unittest import mock
import pytest
from taskuary import advisor, assistant, calwrite, concierge, faults, funnel, lanes, remote_assistant, rulebook, terminal, words
from taskuary.store import MemoryStore
from taskuary.testing import Factory
from tests import advisor_cases as C


@pytest.fixture(autouse=True)
def _mailbox_connected(monkeypatch):
    """These drafts go by email in a world with no mailbox card: as if one were connected, so the Send is what is judged (a card that says
    Connect email lights nothing - advisor.unconnected, tests/test_agent_lights.py)."""
    from taskuary import advisor as _adv
    monkeypatch.setattr(_adv, 'unconnected', lambda store, item: False)

ERIN, RAY = ('Erin Blake', 'erin@northwind.example'), ('Ray Colton', 'ray@northwind.example')
def at(d=0, h=0): return (datetime.now() - timedelta(days=d, hours=h)).strftime('%Y-%m-%d %H:%M:%S')


# ── the state x surface matrix, over the eval's world (the demo, the advisor matrix's faults, and the states they lack) ─────────────
@pytest.fixture(scope='module')
def world():
    # faults.world holds its calendar fresh for good (assistant._AGENDA): put back the one it found, or every later module's pile
    # carries the world's two meetings ("clear the vendor report" cleared a Vendor review in test_triage_urgent)
    sessions, agenda = dict(terminal.SESSIONS), dict(assistant._AGENDA)
    with mock.patch.object(faults, 'scratch_home', lambda: True): s, by, syn = C.world()
    s.set_setting('advisor_event_cap', '1000', 'test')          # every case is the model's now: the hour's cap is not the subject
    yield s, by, syn
    for sid in [k for k in terminal.SESSIONS if k not in sessions]: terminal.SESSIONS.pop(sid, None)
    assistant._AGENDA.clear(); assistant._AGENDA.update(agenda); funnel.invalidate()


_FACT = re.compile(r"^THE STATE \([^)]*\): (\w+) - .*?(?:; the fact: (.*))?$", re.M)
def model_saying(verb):
    """A model that lights `verb` and says, as its line, the fact THE STATE handed it - so a line on the strip proves the fact reached it."""
    calls = []
    def llm(system, user, **kw):
        calls.append(user); m = _FACT.search(user)
        return json.dumps({'verb': verb, 'line': (m.group(2) or '') if m and verb else '', 'evidence': []})
    llm.calls = calls
    return llm


def _decide(s, syn, item, key=None, verb='unset'):
    """The decision as every surface reads it - after the model read the item (at item.shown, tier 2) and answered `verb`."""
    orig = advisor._item
    with mock.patch.object(advisor, '_item', lambda store, tk, ti, key=None: syn.get(key) or (item if key == item.get('key') else orig(store, tk, ti, key))):
        tgt = advisor.target_of(s, key or item['key'])
        if verb != 'unset': advisor.notice(s, advisor.SHOWN, tgt[0], tgt[1], tier=2, wait=True, llm=model_saying(verb), key=key or item['key'])
        with mock.patch.object(advisor, 'notice'): return advisor.decide(s, key or item['key'], preread=False)


# (case, the state the facts name, the verb the model answers - and so the verb lit, whether a line is said: the model's line is the fact
# THE STATE handed it, so a line proves the fact reached the prompt). Every state is the model's; none lights anything by itself
MATRIX = [
    ('Badge access for the new AP clerk', 'asked', 'reply', True),
    ('did the overnight import finish', 'unsendable', 'copy', False),
    ('AP cutover - Thursday?', 'draft_ready', 'approve', False),
    ('Lease renewal for the Elm Street office', 'failed_cause', 'new_task', True),
    ('Spendly card limits', 'idea', 'mine', False),
    ('Q3 accruals file', 'agent_done', 'close', True),           # "Your reply went at 10:02; nothing since."
    ('Helpdesk tickets by day', 'report_ok', 'next', False),
    ('Vendor portal maintenance', 'fyi', 'next', False),
    ('Reconcile the August GL export', 'working', None, False),      # a chat agent's turn picks the light (advisor.agent_light)
    ('agent asking (coding)', 'agent_asking', None, False),       # a coding agent's ask lights nothing (the owner, 2026-11-02)
    ('agent finished (general)', 'agent_done', None, False),     # its turn said nothing is left nowhere: nothing lit (advisor.agent_light)
    ('agent failed (general)', 'failed_cause', 'continue', False),    # ...its failure's Try again, said by the run's own line
    ('agent stopped-saved (coding)', 'stopped', 'continue', False),
    ('Close the August books', 'done_list', 'close', True),
    ('Move payroll to Payworth', 'goal', 'next', False),
    ('Migrate the census export', 'goal_late', 'chase', True),
    ('Ray: schema sign-off', 'waiting_overdue', 'chase', True),         # due two days ago: late by the header's own clock
    ('Vendor W-9 for the new supplier', 'waiting_late', 'chase', True),
    ('Budget figures for Q4', 'waiting_late', 'chase', True),
]


@pytest.mark.parametrize('case,state,verb,says', MATRIX)
def test_each_state_is_one_decision_on_every_surface(world, case, state, verb, says):
    s, by, syn = world
    item = by[case]
    d = _decide(s, syn, item, verb=verb)
    # ...a Send the model names on a draft in its task's Close out lights Send and close there (the owner, 2026-11-03)
    lit = 'send_close' if verb == 'approve' and item.get('tid') else verb
    assert (d.get('state'), d.get('verb'), bool(d.get('line'))) == (state, lit, says), d
    assert len(d.get('line') or '') <= 64, 'a line is read whole on a phone'
    assert not words.jargon_in(d.get('line') or ''), d['line']
    # THE ADVISOR PICKS ONLY FROM THE BUTTONS THE ROW DRAWS (offered: row_buttons, plus Chase on a wait, plus Next)
    if verb and verb != 'next': assert verb in [v['verb'] for v in advisor.offered(s, syn.get(item['key']) or item)]
    # THE PHONE READS THE SAME DECISION: its lead is the Advisor's verb wherever its chips carry it, and Next leads where Next is lit
    chips = concierge.chips_for(s, syn.get(item['key']) or item)
    lead = remote_assistant.primary({'chips': chips, 'item': item}, d)
    if verb == 'next': assert lead['verb'] == 'next'
    elif lit in {c['verb'] for c in chips}: assert lead['verb'] == lit
    assert remote_assistant.advice_line({'item': item}, d) == (d.get('line') or '')


def test_the_tasks_tab_reads_the_same_decision_as_the_canvas(world):
    """The Tasks tab asks for task:N; the canvas for the rail's key - one task, one decision (U12: they read apart)."""
    s, by, syn = world
    for case in ('Badge access for the new AP clerk', 'Close the August books', 'Ray: schema sign-off', 'Migrate the census export'):
        item = by[case]
        desk, tab = _decide(s, syn, item, verb='reply'), _decide(s, syn, item, key=f"task:{item['tid']}", verb='reply')
        assert (desk['verb'], desk['line']) == (tab['verb'], tab['line']), case


def test_every_state_has_its_meaning_and_fact_and_lights_nothing_of_its_own():
    for st, w in words.ADVICE_RULE.items():
        assert set(w) == {'line', 'is'}, f'{st}: a state is facts - no lit list, no ask flag'
        assert w['is'] and not words.jargon_in(w['line']), (st, w['line'])
        for gone in ('No suggestion', 'Nothing to decide', 'Thinking', 'the choice is yours'): assert gone not in w['line']
    # the states the design's table names, each with a rule
    assert {'asked', 'draft_ready', 'unsendable', 'duplicate', 'working', 'agent_asking', 'unpushed', 'stopped', 'failed', 'agent_done',
            'report_ok', 'report_failed', 'fyi_batch', 'fyi', 'invite_free', 'invite_clash', 'invite_no_cal', 'waiting', 'waiting_late',
            'goal_late', 'goal', 'idea', 'unsorted', 'closed', 'stranger'} <= set(words.ADVICE_RULE)


def test_every_state_reaches_the_model_and_none_is_left_to_a_rule(world):
    """The 2026-11-02 audit: 62% of the rows said "left to the rule" and no model read them. Every case is read now, and its prompt carries
    the state, its meaning and every verb the row offers - Next among them."""
    s, by, syn = world
    for case, state, *_ in MATRIX:
        item = by[case]
        tgt = advisor.target_of(s, item['key'])
        llm = model_saying(None)
        orig = advisor._item
        with mock.patch.object(advisor, '_item', lambda store, tk, ti, key=None: syn.get(key) or (item if key == item.get('key') else orig(store, tk, ti, key))):
            advisor.judge(s, 'reply.arrived', tgt[0], tgt[1], 'rev-' + case, tier=1, llm=llm, key=item['key'])
        assert llm.calls, case
        p = llm.calls[0]
        assert 'THE STATE (' in p and f'): {state} - ' in p, case
        assert re.search(r'^VERBS OFFERED: .*next \(Next\)', p, re.M), case
    assert not s._one("SELECT 1 x FROM advice WHERE Dropped='left to the rule'")


# ── the states the world lacks, each built from its facts ─────────────────────────────────────────────────────────────────────────
@pytest.fixture
def s(monkeypatch):
    s = MemoryStore(); s.set_setting('calendar_enabled', '0', 'test')
    monkeypatch.setattr(terminal, 'live_sessions', lambda tail=0: [])
    monkeypatch.setattr(funnel, '_agenda', lambda _s, **kw: [])
    funnel.invalidate(); yield s; funnel.invalidate()


def _asked(s, title, who=ERIN, d=0, cid=None):
    f = Factory(s)
    t = f.task(title=title, kind='task')
    m = f.message(task_id=t, subject=title, body='can you?', from_name=who[0], from_email=who[1], sent_at=at(d=d), conversation_id=cid or f'email:{title}')
    return t, m, {'key': f'task:{t}', 'kind': 'asked', 'lane': 'asked', 'tid': t, 'mid': m, 'title': title}


def _verbs(*vs): return [{'verb': v, 'label': v} for v in vs]


def test_someone_asked_says_how_long(s):
    t, m, it = _asked(s, 'Badge access', d=3)
    assert rulebook.facts(s, it, _verbs('reply', 'regular_agent', 'remove')) == {'state': 'asked', 'line': 'Erin Blake asked 3 days ago.'}
    assert 'verb' not in rulebook.facts(s, it, _verbs('reply')), 'facts light nothing'


def test_a_duplicate_needs_the_thread_never_the_same_sender_alone(s):
    a, _m, it = _asked(s, 'Payworth export', cid='email:payworth')
    b, _n, _ = _asked(s, 'Payworth export (again)', cid='email:payworth')
    c, _o, it3 = _asked(s, 'Lease renewal')                        # Erin again, another thread: another ask
    d = rulebook.facts(s, {**it, 'tid': b, 'key': f'task:{b}'}, _verbs('reply', 'remove'))
    assert (d['state'], d['line']) == ('duplicate', 'Same ask as TQ-0001 - fold it into that one.')
    # ...ONE SURVIVOR PER PAIR (the Advisor audit's judge, 2026-10-26): the one asked first is never the duplicate of its twin
    assert rulebook.facts(s, it, _verbs('reply', 'remove'))['state'] == 'asked'
    assert rulebook.facts(s, it3, _verbs('reply', 'remove'))['state'] == 'asked'


def test_the_owners_reply_after_their_newest_mail_is_the_answered_fact(s):
    """A3: the owner already answered - by a reply sent from here or one typed in their own mail app - and the facts say so."""
    t, m, it = _asked(s, 'Badge access', d=3)
    s._exec("UPDATE review SET DeliveryState='sent', DecidedAt=? WHERE ReviewId=?", (at(d=2), Factory(s).review(t, m, status='approved', final='Done.')))
    d = rulebook.facts(s, it, _verbs('reply', 'close'))
    assert (d['state'], d['line'], d.get('section')) == ('answered', 'Your reply went 2 days ago; nothing since.', None)
    # ...they wrote again after it: an ask again
    Factory(s).message(task_id=t, subject='RE: Badge access', body='and the second door?', from_name=ERIN[0], from_email=ERIN[1], sent_at=at(d=1), conversation_id='email:Badge access')
    assert rulebook.facts(s, it, _verbs('reply', 'close'))['state'] == 'asked'
    # ...an outgoing message typed elsewhere counts as much as a sent review
    u, _m, it2 = _asked(s, 'Trainly seats', who=RAY, d=2)
    Factory(s).message(task_id=u, subject='RE: Trainly seats', body='Sorted.', direction='out', from_email='alex@northwind.example', sent_at=at(d=1), conversation_id='email:Trainly seats')
    assert rulebook.facts(s, it2, _verbs('reply', 'close'))['state'] == 'answered'


def test_a_first_mail_from_an_unknown_address_is_named_a_stranger(s):
    from taskuary.ingest import HOLD_TAG
    t, m, it = _asked(s, 'Your quote', who=('Sam Ortiz', 'sam@vendor.example'))
    s.add_task_tag(t, HOLD_TAG) if hasattr(s, 'add_task_tag') else s._exec("UPDATE task SET Tags=? WHERE TaskId=?", (HOLD_TAG, t))
    with mock.patch.object(remote_assistant, 'stranger_held', return_value=True):
        assert rulebook.facts(s, it, _verbs('reply', 'regular_agent')) == {'state': 'stranger', 'line': 'First mail from vendor.example.'}


def _invite(s, start, end):
    t = Factory(s).task(title='Budget sync', kind='task')
    cal = {'kind': 'request', 'provider': 'outlook', 'event_id': 'ev-1', 'update': False, 'answered': False, 'asks': True,
           'subject': 'Budget sync', 'start': start, 'end': end, 'all_day': False, 'organizer': 'Erin Blake'}
    m = Factory(s).message(task_id=t, subject='Invitation: Budget sync', from_name=ERIN[0], from_email=ERIN[1], MailMetaJson=json.dumps({'cal': cal}))
    return {'key': f'task:{t}', 'kind': 'asked', 'lane': 'asked', 'tid': t, 'mid': m}


def test_an_invite_says_whether_it_clashes_or_whether_no_calendar_can_say(s):
    day = date.today() + timedelta(days=1)
    while day.weekday() >= 5: day += timedelta(days=1)
    it = _invite(s, f'{day} 14:30', f'{day} 15:00')
    vs = _verbs('accept_invite', 'decline_invite', 'propose_time')
    busy = [{'start': f'{day} 14:00', 'end': f'{day} 15:00', 'subject': '1:1 with Omar', 'all_day': False}]
    with mock.patch.object(rulebook, 'calendar_on', return_value=True), mock.patch.object(calwrite, 'busy', return_value=busy):
        d = rulebook.facts(s, it, vs)
    assert d['state'] == 'invite_clash' and d['line'].startswith('Clashes with 1:1 with Omar')
    with mock.patch.object(rulebook, 'calendar_on', return_value=True), mock.patch.object(calwrite, 'busy', return_value=[]):
        assert rulebook.facts(s, it, vs) == {'state': 'invite_free', 'line': 'Free then.'}
    with mock.patch.object(rulebook, 'calendar_on', return_value=False):
        assert rulebook.facts(s, it, vs)['state'] == 'invite_no_cal'


def test_an_agent_with_work_not_pushed_is_named_so(s):
    t = Factory(s).task(title='Fix the export', kind='coding')
    it = {'key': f'agent:{t}', 'kind': 'agentdone', 'lane': 'done', 'tid': t}
    assert rulebook.facts(s, it, _verbs('close', 'review_changes')) == {'state': 'agent_done', 'line': ''}, 'nothing shows when it ended: no fact said'
    s._exec("INSERT INTO boardnote (TaskId, Agent, Cwd, Kind, Body, CreatedAt) VALUES (?, 'coding', 'C:/x', 'ready', 'ready to push', ?)", (t, at()))
    assert rulebook.facts(s, it, _verbs('close', 'review_changes')) == {'state': 'unpushed', 'line': 'Changes ready - not pushed.'}
    s._exec("INSERT INTO boardnote (TaskId, Agent, Cwd, Kind, Body, CreatedAt) VALUES (?, 'coding', 'C:/x', 'done', 'pushed', ?)", (t, at()))
    assert rulebook.facts(s, it, _verbs('close', 'review_changes'))['state'] == 'agent_done'


def test_waiting_on_someone_is_named_late_after_three_working_days_and_chase_is_always_on_its_row(s):
    f = Factory(s)
    t = f.task(title='Vendor W-9', kind='task', status='waiting'); s._exec("UPDATE task SET WaitingOn='ray.colton@northwind.example' WHERE TaskId=?", (t,))
    it = {'key': f'task:{t}', 'kind': 'todo', 'lane': 'theirs', 'tid': t}
    f.message(task_id=t, subject='W-9?', direction='out', sent_at=at(d=1))
    assert rulebook.facts(s, it, _verbs('defer', 'chase'))['state'] == 'waiting'
    assert rulebook.adds(s, it) == ['chase'], 'Chase is offered on every wait with somebody to write to - when to chase is the model\'s'
    s._exec("UPDATE message SET SentAt=? WHERE TaskId=?", (at(d=7), t))
    d = rulebook.facts(s, it, _verbs('defer', 'chase'))
    assert d['state'] == 'waiting_late' and d['line'].startswith('Ray Colton: ') and d['line'].endswith('days, no answer.')
    assert rulebook.working_days(datetime(2026, 10, 23), datetime(2026, 10, 26)) == 1, 'a Friday ask is one day old on Monday'


def test_a_goal_step_past_its_day_is_named_in_the_fact(s):
    g = s.create_task({'Title': 'Move payroll', 'Status': 'open', 'DoneWhen': 'payroll runs on the new system'}, 'owner')
    s.set_task_checklist(g, ['Export the pay rules', 'schema sign-off'], 'owner')
    k = s.create_task({'Title': 'schema sign-off', 'Status': 'waiting', 'Assignee': 'person:ray.colton@northwind.example', 'ParentId': g,
                       'DueAt': (date.today() - timedelta(days=2)).isoformat()}, 'owner')
    s.link_step(g, s.checklist_id('schema sign-off'), k, 'owner')
    it = {'key': f'task:{g}', 'kind': 'goal_slipped', 'lane': 'yours', 'tid': g}
    assert rulebook.facts(s, it, _verbs('close', 'defer', 'chase')) == {'state': 'goal_late', 'line': "Ray Colton's schema sign-off: 2 days late."}
    s._exec("UPDATE task SET DueAt=? WHERE TaskId=?", ((date.today() + timedelta(days=2)).isoformat(), k))
    assert rulebook.facts(s, it, _verbs('close', 'defer', 'chase')) == {'state': 'goal', 'line': ''}


def test_a_phish_filed_fyi_is_named_so_and_the_model_decides(s):
    """The owner, 2026-10-30: a phishing FYI's row lit Send to agent. The facts name it fyi_danger, said to the model; no code lights for it."""
    fyi = {'key': 'msg:7', 'kind': 'fyi', 'lane': 'fyi', 'mid': 7}
    assert rulebook.facts(s, {**fyi, 'danger': 'Wants Alex to sign in on a look-alike page.'}, _verbs('mine', 'regular_agent', 'not_ours'))['state'] == 'fyi_danger'
    assert not hasattr(rulebook, 'SAFE'), 'no state is decided by code, whatever its name'
    assert rulebook.facts(s, fyi, _verbs('mine', 'regular_agent', 'not_ours'))['state'] == 'fyi'


def test_unsorted_mail_a_batch_a_closed_task_and_a_failed_report(s):
    assert rulebook.facts(s, {'kind': 'fyi', 'lane': 'unjudged', 'mid': 1}, _verbs('retriage'))['state'] == 'unsorted'
    assert rulebook.facts(s, {'kind': 'fyis', 'lane': 'fyi'}, [])['state'] == 'fyi_batch'
    t = Factory(s).task(title='Done already', status='done')
    assert rulebook.facts(s, {'kind': 'todo', 'lane': 'yours', 'tid': t}, _verbs('reopen'))['state'] == 'closed'
    assert rulebook.facts(s, {'kind': 'report', 'lane': 'broken', 'bad': True, 'why': 'mailbox signed out'}, _verbs('rerun')) == \
        {'state': 'report_failed', 'line': 'Report failed: mailbox signed out'}


# ── the model's light, and the checks on it ────────────────────────────────────────────────────────────────────────────────────────
def _habit(s, text, key):
    """A press count where the 2026-10-23 doc kept it - an install the migration has not reached, or a model that wrote one anyway."""
    s.save_doc('learned', f"# Learned\n\n## How you sort mail\n\n## What you do next\n- {text} [s:5 | ev: pr1, pr2, pr3 | seen: 2026-10-20 | k: {key}]\n", 'test')


def _said(s, t, it, verb, line='', kind=None):
    advisor._write(s, target_kind='task', target_id=t, key=it['key'], event=advisor.SHOWN, revision=advisor.revision(s, 'task', t), tier=2,
                   line=line, verb=verb, label=verb, model='m', kind=kind)


def test_nothing_is_lit_before_the_model_reads_the_item(s, monkeypatch):
    t, m, it = _asked(s, 'Weekly report', d=2)
    monkeypatch.setattr(advisor, '_item', lambda store, tk, ti, key=None: it)
    asked = []
    monkeypatch.setattr(advisor, 'notice', lambda *a, **k: asked.append(k.get('tier')))
    d = advisor.decide(s, it['key'], preread=False)
    assert (d['state'], d['verb'], d['line']) == ('asked', None, '') and asked == [2], 'read now, at the bigger tier; nothing lit meanwhile'


def test_a_press_count_lights_nothing(s, monkeypatch):
    """The owner, 2026-10-25: stop learning from presses and remove the habit mark - a press count in the doc never changes the lit button."""
    t, m, it = _asked(s, 'Weekly report', who=('Vendor Desk', 'desk@vendor.example'), d=2)
    monkeypatch.setattr(advisor, '_item', lambda store, tk, ti, key=None: it)
    monkeypatch.setattr(advisor, 'notice', lambda *a, **k: None)
    _said(s, t, it, 'reply')
    assert advisor.decide(s, it['key'], preread=False)['verb'] == 'reply'
    _habit(s, 'On asks from vendor.example, {{owner_first}} presses Mark done (5 of 6)', 'move asked email vendor.example')
    d = advisor.decide(s, it['key'], preread=False)
    assert (d['verb'], d['by']) == ('reply', 'model') and 'says' not in d and d['pill'] == d['label'], 'no habit, no count, no mark'


def test_send_is_never_lit_on_a_draft_the_check_flagged(s, monkeypatch):
    t, m, it = _asked(s, 'Invoice 4410', who=('Vendor Desk', 'desk@vendor.example'))
    rid = Factory(s).review(t, m, draft="It goes out in Friday's payment run.")
    it = {**it, 'kind': 'review', 'lane': 'approve', 'rid': rid, 'draft': True, 'key': f'review:{rid}'}
    monkeypatch.setattr(advisor, '_item', lambda store, tk, ti, key=None: it)
    monkeypatch.setattr(advisor, 'notice', lambda *a, **k: None)
    _habit(s, 'On drafts to vendor.example, {{owner_first}} presses Send (5 of 6)', 'move review email vendor.example')
    _said(s, t, it, 'redraft', 'Draft promises Friday - nothing here shows it.')
    d = advisor.decide(s, it['key'], preread=False)
    assert (d['verb'], d['by'], d['line']) == ('redraft', 'model', 'Draft promises Friday - nothing here shows it.')


def test_the_models_light_is_what_is_lit_with_its_line(s, monkeypatch):
    t, m, it = _asked(s, 'Badge access')
    monkeypatch.setattr(advisor, '_item', lambda store, tk, ti, key=None: it)
    monkeypatch.setattr(advisor, 'notice', lambda *a, **k: None)
    _said(s, t, it, 'reply', 'Erin is waiting on you - answer her.')
    d = advisor.decide(s, it['key'], preread=False)
    assert (d['verb'], d['line'], d['by']) == ('reply', 'Erin is waiting on you - answer her.', 'model')


def test_a_verb_the_row_does_not_carry_is_dropped(s, monkeypatch):
    from tests.test_advisor import brain_saying
    t, m, it = _asked(s, 'Badge access')
    monkeypatch.setattr(advisor, '_item', lambda store, tk, ti, key=None: it)
    monkeypatch.setattr(advisor, 'offered', lambda store, item: _verbs('reply', 'close'))
    rid = advisor.notice(s, advisor.SHOWN, 'task', t, tier=2, wait=True, llm=brain_saying({'verb': 'merge_pr', 'line': 'Merge it.', 'evidence': []}))
    assert s._one('SELECT Dropped FROM advice WHERE Id=?', (rid,))['Dropped'] == 'verb not offered: merge_pr'
    monkeypatch.setattr(advisor, 'notice', lambda *a, **k: None)
    assert advisor.decide(s, it['key'], preread=False)['verb'] is None


def test_the_next_two_are_read_ahead_whatever_their_state(s, monkeypatch):
    items = [{'key': f'k{n}', 'kind': 'asked' if n % 2 else 'report', 'lane': 'asked', 'tid': n} for n in range(5)]
    monkeypatch.setattr(funnel, 'pile', lambda store, quiet=False: {'items': items})
    monkeypatch.setattr(advisor, 'target_of', lambda store, key: ('task', int(key[1:])))
    got = []
    monkeypatch.setattr(advisor, 'notice', lambda store, ev, tk, ti, **kw: got.append((ti, kw.get('tier'), kw.get('key'))))
    class T:
        def __init__(self, target, **kw): self.f = target
        def start(self): self.f()
    monkeypatch.setattr(advisor.threading, 'Thread', T)
    monkeypatch.setattr(advisor, 'BACKGROUND', True)
    advisor._preread(s, 'k0')
    assert got == [(1, 1, 'k1'), (2, 1, 'k2')], 'the next two, a report as much as an ask'


# ── one census for every count ──────────────────────────────────────────────────────────────────────────────────────────────────
def test_one_census_for_on_you_the_walks_end_and_the_rails_tasks():
    items = [{'key': 'a', 'lane': 'asked', 'kind': 'asked'}, {'key': 'b', 'lane': 'theirs', 'kind': 'todo'},
             {'key': 'c', 'lane': 'fyi', 'kind': 'fyi'}, {'key': 'd', 'lane': 'asked', 'kind': 'asked', 'settling': True}]
    c = lanes.census(items)
    assert (c['on_you'], c['tasks']) == (sum(map(lanes.on_you, items)), sum(1 for i in items if not i.get('settling') and lanes.level_of(i) == 'task'))
    assert c['on_you'] < c['tasks'], 'waiting on them is under Tasks and not on you'


def test_a_failure_line_says_what_failed_in_plain_words_never_our_refusal():
    """The dead-end walk's WORDS, 2026-10-23: "Failed: TQ-0012 needs a repository first - working directory do..." was the server's own
    refusal read out on the strip. The line takes the first reason that is the owner's words, else says only that it stopped."""
    assert rulebook._plain_why('TQ-0012 needs a repository first - working directory does not exist', 'Send to agent did not start') == 'Send to agent did not start'
    assert rulebook._plain_why('the mailbox is signed out') == 'the mailbox is signed out'
    assert rulebook._plain_why('needs a repository first', None) == 'it stopped without saying why'


# ── a dashboard, and Share ──────────────────────────────────────────────────────────────────────────────────────────────────────
def test_a_dashboard_is_named_so_and_share_is_on_its_row_for_the_model_to_see(s):
    """A dashboard's refresh lands under Reports like a report run. Share is on a report's and a dashboard's row for the Advisor to see."""
    m = Factory(s).message(subject='Open work - Open tasks 12', body='Open tasks: 12', from_name='Open work', from_email='')
    rep = {'key': f'msg:{m}', 'kind': 'report', 'lane': 'report', 'mid': m}
    dash = {**rep, 'dashboard': True}
    have = [b['verb'] for b in concierge.row_buttons(s, dash)]
    assert 'share_result' in have and 'share_result' in [b['verb'] for b in concierge.row_buttons(s, rep)]
    assert 'share_result' not in [b['verb'] for b in concierge.row_buttons(s, {**rep, 'bad': True})], 'a failed run has nothing to share'
    assert 'share_result' in [v['verb'] for v in advisor.offered(s, dash)], 'the Advisor sees the row has Share'
    assert rulebook.facts(s, dash, _verbs(*have)) == {'state': 'dashboard', 'line': ''}
    assert rulebook.facts(s, rep, _verbs(*have))['state'] == 'report_ok'
    assert 'share_result' not in [c['verb'] for c in concierge.chips_for(s, dash)], "the phone's chips have no Share menu"


def test_a_draft_says_what_leaves_with_it(s):
    """WHAT LEAVES WITH A DRAFT (the design rev 2, data leaving): an address its thread never had and the files it carries are the fact
    said - no dialog, nothing held. A plain reply to the thread's own people says nothing. Addresses and files, never words."""
    t, m, it = _asked(s, 'Q3 accruals')
    f, V = Factory(s), _verbs('approve', 'redraft')
    rv = f.review(t, m, draft='Here are the Q3 accruals.')
    set_env = lambda env: s._exec('UPDATE review SET Deliver=? WHERE ReviewId=?', (json.dumps(env), rv))
    assert rulebook.facts(s, it, V) == {'state': 'draft_ready', 'line': ''}, 'a reply to whom wrote: nothing to say'
    set_env({'kind': 'reply', 'to': ['erin@northwind.example'], 'cc': ['dana@vendor.example']})
    d = rulebook.facts(s, it, V)
    assert (d['line'], d['evidence']) == ('Goes to dana@vendor.example - new to this thread.', [f'rv{rv}']), d
    files = [{'name': 'q3.xlsx', 'path': 'x'}]
    set_env({'kind': 'reply', 'to': ['erin@northwind.example'], 'attachments': files})
    assert rulebook.facts(s, it, V)['line'] == 'Sends the file q3.xlsx.'
    set_env({'kind': 'reply', 'to': ['erin@northwind.example', 'dana@vendor.example'], 'attachments': files + [{'name': 'notes.pdf'}]})
    assert rulebook.facts(s, it, V)['line'] == 'Goes to dana@vendor.example, new to this thread, with 2 files.'
    s.set_setting('owner_email', 'alex@northwind.example', 'test')
    set_env({'channel': 'email', 'to': ['paula@northwind.example'], 'cc': ['alex@northwind.example']})
    assert rulebook.facts(s, it, V)['line'] == 'Goes to paula@northwind.example - new to this thread.'


def test_a_task_left_sitting_lights_only_the_models_move_beside_what_is_owed(s):
    """UNTOUCHED TOO LONG (the design rev 2): an open task of the owner's that nothing moved for UNTOUCHED_DAYS working days is said to the
    model, which reads what is still owed - nothing lit while it reads, then its verb; nothing owed is silent."""
    from tests.test_advisor import brain_saying
    t = Factory(s).task(title='Sign the Elm Street lease', kind='task')
    old = (datetime.now() - timedelta(days=12)).strftime('%Y-%m-%d %H:%M:%S')
    it = {'key': f'task:{t}', 'kind': 'own', 'lane': 'mine', 'tid': t, 'title': 'Sign the Elm Street lease'}
    assert rulebook.state(s, it, [])[0] == 'own'
    rev = advisor.revision(s, 'task', t)
    s._exec('UPDATE task SET CreatedAt=?, UpdatedAt=? WHERE TaskId=?', (old, old, t))
    assert rulebook.untouched(s, s.get_task(t)) >= rulebook.UNTOUCHED_DAYS
    assert advisor.revision(s, 'task', t) != rev, 'crossing the line is read again'
    assert rulebook.facts(s, it, _verbs('close', 'defer', 'reply')) == {'state': 'untouched', 'line': ''}
    orig = advisor._item
    def decide():
        with mock.patch.object(advisor, '_item', lambda store, tk, ti, key=None: it if ti == t else orig(store, tk, ti, key)), \
             mock.patch.object(advisor, 'offered', return_value=[{'verb': v, 'label': v} for v in ('close', 'defer', 'reply')]):
            advisor.notice(s, advisor.SHOWN, 'task', t, tier=2, wait=True, llm=llm)
            with mock.patch.object(advisor, 'notice'): return advisor.decide(s, f'task:{t}', preread=False)
    llm = brain_saying({'verb': None, 'line': '', 'evidence': []})
    assert decide()['verb'] is None, 'nothing owed: nothing lit'
    assert 'UNTOUCHED: nothing has moved on it for' in llm.calls[0][1]
    s._exec('DELETE FROM advice WHERE TargetId=?', (t,))
    llm = brain_saying({'verb': 'reply', 'line': 'Erin still needs the signed lease', 'evidence': [], 'kind': 'late'})
    d = decide()
    assert (d['state'], d['verb'], d['line'], d['by']) == ('untouched', 'reply', 'Erin still needs the signed lease', 'model'), d


def test_what_leaves_stands_beside_the_models_send(s):
    t, m, it = _asked(s, 'Q3 accruals')
    Factory(s).review(t, m, draft='Here are the Q3 accruals.', Deliver=json.dumps({'kind': 'reply', 'to': ['erin@northwind.example'], 'cc': ['dana@vendor.example']}))
    s.reconcile_processing_membership(); s.activate_processing_reads(fixed_now=datetime.now().isoformat(), live_state=[]); funnel.invalidate()
    from tests.test_advisor import brain_saying
    advisor.notice(s, advisor.SHOWN, 'task', t, tier=2, wait=True, llm=brain_saying({'verb': 'approve', 'line': '', 'evidence': []}))
    with mock.patch.object(advisor, 'notice'):
        d = advisor.decide(s, f'task:{t}', preread=False)
    assert (d['state'], d['verb'], d['line']) == ('draft_ready', 'send_close', 'Goes to dana@vendor.example - new to this thread.'), d


# ── AN ACTION WAITING FOR THE OWNER'S YES (the 2026-11-02 audit: an agent's card read as asking lit nothing over a held `git push`) ──────
def _held(s, cmd='git push origin main'):
    from taskuary import proposals
    t = Factory(s).task(title='Ship the ledger fix', kind='code', status='in_progress')
    proposals.queue(s, t, {'action': 'shell_act', 'sid': 'run1', 'command': cmd, 'shell': 'Bash', 'what': 'push your commits to the code host',
                           'why': 'it leaves this computer'}, 'agent')
    return t, {'key': f'agent:{t}', 'kind': 'agent', 'lane': 'blocked', 'asking': True, 'tid': t, 'title': 'Ship the ledger fix'}


def test_a_held_action_is_read_before_an_agent_asking(s):
    t, it = _held(s)
    assert rulebook.facts(s, it, _verbs('approve', 'stop_agent'))['state'] == 'action_held'
    rv = s._one("SELECT ReviewId FROM review WHERE TaskId=? AND Kind='action'", (t,))['ReviewId']
    s._exec("UPDATE review SET Status='dismissed' WHERE ReviewId=?", (rv,))
    assert rulebook.facts(s, it, _verbs('approve', 'stop_agent'))['state'] == 'agent_asking', 'answered: the agent asking is read as before'


def test_the_held_actions_approve_is_on_the_tasks_row_and_pressed_answers_that_proposal(s):
    from tests.test_advisor import brain_saying
    t, _ = _held(s)
    funnel.invalidate()
    rv = s._one("SELECT ReviewId FROM review WHERE TaskId=? AND Kind='action'", (t,))['ReviewId']
    it = advisor._item(s, 'task', t)
    assert not it.get('rid') and concierge.cannot(it, 'approve', s) == ''
    assert {'verb': 'approve', 'label': 'Approve'} in concierge.row_buttons(s, it)
    advisor.notice(s, advisor.SHOWN, 'task', t, tier=2, wait=True, llm=brain_saying({'verb': 'approve', 'line': '', 'evidence': []}))
    with mock.patch.object(advisor, 'notice'): d = advisor.decide(s, f'task:{t}', preread=False)
    assert (d['state'], d['verb'], d['label']) == ('action_held', 'approve', 'Approve'), d
    prop = concierge.propose_direct(s, 'approve', f'task:{t}', press=True)
    assert (prop['kind'], int(prop['target'])) == ('review.approve', rv), prop


def test_a_close_out_or_a_playbook_is_no_held_action(s):
    from taskuary import proposals
    t = Factory(s).task(title='Ledger fix', kind='code', status='in_progress')
    for p in ({'action': 'merge_pr', 'number': 7, 'closeout': True}, {'action': proposals.PLAYBOOK}):
        s.add_review({'TaskId': t, 'Kind': 'action', 'Status': 'pending', 'DraftText': json.dumps(p), 'Reason': 'x'})
    assert proposals.held_pending(s, t) is None


def test_a_held_action_moves_the_revision_and_reaches_the_advisors_prompt(s):
    t = Factory(s).task(title='Ship the ledger fix', kind='code', status='in_progress')
    before = advisor.revision(s, 'task', t)
    from taskuary import proposals
    proposals.queue(s, t, {'action': 'shell_act', 'sid': 'run1', 'command': 'git push', 'shell': 'Bash', 'what': 'push your commits to the code host'}, 'agent')
    assert advisor.revision(s, 'task', t) != before
    p = advisor._prompt(s, advisor.SHOWN, {'key': f'task:{t}', 'kind': 'agent', 'tid': t, 'title': 'Ship the ledger fix'}, _verbs('approve'), 1, 'task', t)
    assert 'AN ACTION WAITS FOR YOUR YES: push your commits to the code host' in p
