"""THE ONE RULEBOOK (the Advisor design, phase A; the owner's rulings, 2026-10-23): every state the design's table names, decided from
facts the app keeps, read the same by every surface - the desk canvas (the rail's key), the Tasks tab (task:N), a phone chat
(remote_assistant.primary and the card's line) - with a line only where the card does not show the fact, and Next lit where nothing
needs the owner. The desk at phone width is the page's (website/test/rulebookMatrix.test.mjs). Invented Northwind people only."""
import json
from datetime import date, datetime, timedelta
from unittest import mock
import pytest
from taskuary import advisor, assistant, calwrite, concierge, faults, funnel, lanes, remote_assistant, rulebook, terminal, words
from taskuary.store import MemoryStore
from taskuary.testing import Factory
from tests import advisor_cases as C

ERIN, RAY = ('Erin Blake', 'erin@northwind.example'), ('Ray Colton', 'ray@northwind.example')
def at(d=0, h=0): return (datetime.now() - timedelta(days=d, hours=h)).strftime('%Y-%m-%d %H:%M:%S')


# ── the state x surface matrix, over the eval's world (the demo, the advisor matrix's faults, and the states they lack) ─────────────
@pytest.fixture(scope='module')
def world():
    # faults.world holds its calendar fresh for good (assistant._AGENDA): put back the one it found, or every later module's pile
    # carries the world's two meetings ("clear the vendor report" cleared a Vendor review in test_triage_urgent)
    sessions, agenda = dict(terminal.SESSIONS), dict(assistant._AGENDA)
    with mock.patch.object(faults, 'scratch_home', lambda: True): s, by, syn = C.world()
    yield s, by, syn
    for sid in [k for k in terminal.SESSIONS if k not in sessions]: terminal.SESSIONS.pop(sid, None)
    assistant._AGENDA.clear(); assistant._AGENDA.update(agenda); funnel.invalidate()


def _decide(s, syn, item, key=None):
    orig = advisor._item
    with mock.patch.object(advisor, '_item', lambda store, tk, ti, key=None: syn.get(key) or (item if key == item.get('key') else orig(store, tk, ti, key))), \
         mock.patch.object(advisor, 'notice'):
        return advisor.decide(s, key or item['key'], preread=False)


# (case, the state the rule reads, the verb lit with no model read, whether a line is said) - NO DEFAULT VERB (the owner, 2026-10-28):
# an ask, a draft or an idea lights nothing until the model says a fact for it, a plain stop lights nothing, and Mark done says its reason
MATRIX = [
    ('Badge access for the new AP clerk', 'asked', None, False),
    ('did the overnight import finish', 'unsendable', 'copy', False),
    ('AP cutover - Thursday?', 'draft_ready', None, False),
    ('Lease renewal for the Elm Street office', 'failed_cause', 'new_task', True),
    ('Spendly card limits', 'idea', None, False),
    ('Q3 accruals file', 'agent_done', 'close', True),           # "Your reply went at 10:02; nothing since."
    ('Helpdesk tickets by day', 'report_ok', 'next', False),
    ('Vendor portal maintenance', 'fyi', 'next', False),
    ('Reconcile the August GL export', 'working', 'next', False),
    ('agent asking (coding)', 'agent_asking', None, False),
    ('agent finished (general)', 'agent_done', 'close', True),
    ('agent failed (general)', 'failed_cause', 'continue', True),
    ('agent stopped-saved (coding)', 'stopped', None, False),
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
    d = _decide(s, syn, item)
    assert (d.get('state'), d.get('verb'), bool(d.get('line'))) == (state, verb, says), d
    assert len(d.get('line') or '') <= 64, 'a line is read whole on a phone'
    assert not words.jargon_in(d.get('line') or ''), d['line']
    # THE ADVISOR PICKS ONLY FROM THE BUTTONS THE ROW DRAWS (offered: row_buttons, plus Chase where a wait ran past its day)
    if verb and verb != 'next': assert verb in [v['verb'] for v in advisor.offered(s, syn.get(item['key']) or item)]
    # THE PHONE READS THE SAME DECISION: its lead is the Advisor's verb wherever its chips carry it, and Next leads where Next is lit
    chips = concierge.chips_for(s, syn.get(item['key']) or item)
    lead = remote_assistant.primary({'chips': chips, 'item': item}, d)
    if verb == 'next': assert lead['verb'] == 'next'
    elif verb in {c['verb'] for c in chips}: assert lead['verb'] == verb
    assert remote_assistant.advice_line({'item': item}, d) == (d.get('line') or '')


def test_the_tasks_tab_reads_the_same_decision_as_the_canvas(world):
    """The Tasks tab asks for task:N; the canvas for the rail's key - one task, one decision (U12: they read apart)."""
    s, by, syn = world
    for case in ('Badge access for the new AP clerk', 'Close the August books', 'Ray: schema sign-off', 'Migrate the census export'):
        item = by[case]
        desk, tab = _decide(s, syn, item), _decide(s, syn, item, key=f"task:{item['tid']}")
        assert (desk['verb'], desk['line']) == (tab['verb'], tab['line']), case


def test_every_state_has_its_words_and_every_lit_verb_is_a_button():
    from taskuary import buttons
    for st, w in words.ADVICE_RULE.items():
        assert set(w) <= {'line', 'lit', 'ask'}, st
        for v in w['lit']: assert v == 'next' or buttons.label(v), (st, v)
        assert not words.jargon_in(w['line']), (st, w['line'])
        for gone in ('No suggestion', 'Nothing to decide', 'Thinking', 'the choice is yours'): assert gone not in w['line']
    # the states the design's table names, each with a rule
    assert {'asked', 'draft_ready', 'unsendable', 'duplicate', 'working', 'agent_asking', 'unpushed', 'stopped', 'failed', 'agent_done',
            'report_ok', 'report_failed', 'fyi_batch', 'fyi', 'invite_free', 'invite_clash', 'invite_no_cal', 'waiting', 'waiting_late',
            'goal_late', 'goal', 'idea', 'unsorted', 'closed', 'stranger'} <= set(words.ADVICE_RULE)


def test_rule_answers_are_fast_and_spend_nothing_of_the_cap(world):
    """Under 50 ms a state, and no model row - the hourly cap counts model calls only (the design, 1.1)."""
    import time
    s, by, syn = world
    before = (s._one('SELECT COUNT(*) AS n FROM advice WHERE Model IS NOT NULL') or {}).get('n')
    t0 = time.perf_counter()
    for case, *_ in MATRIX: _decide(s, syn, by[case])
    assert (time.perf_counter() - t0) / len(MATRIX) < 0.05
    assert (s._one('SELECT COUNT(*) AS n FROM advice WHERE Model IS NOT NULL') or {}).get('n') == before


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


def test_someone_asked_says_how_long_only_from_a_day_on(s):
    t, m, it = _asked(s, 'Badge access', d=3)
    d = rulebook.decide(s, it, _verbs('reply', 'regular_agent', 'remove'))
    assert (d['state'], d['verb'], d['line'], d['ask']) == ('asked', 'reply', 'Erin Blake asked 3 days ago.', True)
    u, _m, it2 = _asked(s, 'Trainly seats', who=RAY)
    assert rulebook.decide(s, it2, _verbs('reply'))['line'] == '', 'asked this morning: the card says the age already'


def test_a_duplicate_needs_the_thread_never_the_same_sender_alone(s):
    a, _m, it = _asked(s, 'Payworth export', cid='email:payworth')
    b, _n, _ = _asked(s, 'Payworth export (again)', cid='email:payworth')
    c, _o, it3 = _asked(s, 'Lease renewal')                        # Erin again, another thread: another ask
    d = rulebook.decide(s, {**it, 'tid': b, 'key': f'task:{b}'}, _verbs('reply', 'remove'))
    assert (d['state'], d['verb'], d['line']) == ('duplicate', 'remove', 'Same ask as TQ-0001 - fold it into that one.')
    # ...ONE SURVIVOR PER PAIR (the Advisor audit's judge, 2026-10-26): the one asked first keeps its own move, never folded into its twin
    assert rulebook.decide(s, it, _verbs('reply', 'remove'))['state'] == 'asked'
    assert rulebook.decide(s, {**it, 'tid': b, 'key': f'task:{b}'}, _verbs('reply', 'split', 'remove'))['verb'] == 'split', 'folded by merging, where the row can'
    assert rulebook.decide(s, it3, _verbs('reply', 'remove'))['state'] == 'asked'


def test_the_owners_reply_after_their_newest_mail_lights_mark_done_not_reply(s):
    """A3: the owner already answered - by a reply sent from here or one typed in their own mail app - so Mark done, never Reply."""
    t, m, it = _asked(s, 'Badge access', d=3)
    s._exec("UPDATE review SET DeliveryState='sent', DecidedAt=? WHERE ReviewId=?", (at(d=2), Factory(s).review(t, m, status='approved', final='Done.')))
    assert (d := rulebook.decide(s, it, _verbs('reply', 'close')))['state'] == 'answered' and d['verb'] == 'close'
    assert d['line'] == 'Your reply went 2 days ago; nothing since.', 'Mark done says its reason (the owner, 2026-10-28)'
    # ...they wrote again after it: Reply again
    Factory(s).message(task_id=t, subject='RE: Badge access', body='and the second door?', from_name=ERIN[0], from_email=ERIN[1], sent_at=at(d=1), conversation_id='email:Badge access')
    assert rulebook.decide(s, it, _verbs('reply', 'close'))['state'] == 'asked'
    # ...an outgoing message typed elsewhere counts as much as a sent review
    u, _m, it2 = _asked(s, 'Trainly seats', who=RAY, d=2)
    Factory(s).message(task_id=u, subject='RE: Trainly seats', body='Sorted.', direction='out', from_email='alex@northwind.example', sent_at=at(d=1), conversation_id='email:Trainly seats')
    assert rulebook.decide(s, it2, _verbs('reply', 'close'))['verb'] == 'close'


def test_a_first_mail_from_an_unknown_address_is_reply_never_an_agent(s):
    from taskuary.ingest import HOLD_TAG
    t, m, it = _asked(s, 'Your quote', who=('Sam Ortiz', 'sam@vendor.example'))
    s.add_task_tag(t, HOLD_TAG) if hasattr(s, 'add_task_tag') else s._exec("UPDATE task SET Tags=? WHERE TaskId=?", (HOLD_TAG, t))
    with mock.patch.object(remote_assistant, 'stranger_held', return_value=True):
        d = rulebook.decide(s, it, _verbs('reply', 'regular_agent'))
    assert (d['state'], d['verb'], d['line']) == ('stranger', 'reply', 'First mail from vendor.example.')


def _invite(s, start, end):
    t = Factory(s).task(title='Budget sync', kind='task')
    cal = {'kind': 'request', 'provider': 'outlook', 'event_id': 'ev-1', 'update': False, 'answered': False, 'asks': True,
           'subject': 'Budget sync', 'start': start, 'end': end, 'all_day': False, 'organizer': 'Erin Blake'}
    m = Factory(s).message(task_id=t, subject='Invitation: Budget sync', from_name=ERIN[0], from_email=ERIN[1], MailMetaJson=json.dumps({'cal': cal}))
    return {'key': f'task:{t}', 'kind': 'asked', 'lane': 'asked', 'tid': t, 'mid': m}


def test_an_invite_is_accept_when_free_propose_when_it_clashes_and_next_with_no_calendar(s):
    day = date.today() + timedelta(days=1)
    while day.weekday() >= 5: day += timedelta(days=1)
    it = _invite(s, f'{day} 14:30', f'{day} 15:00')
    vs = _verbs('accept_invite', 'decline_invite', 'propose_time')
    busy = [{'start': f'{day} 14:00', 'end': f'{day} 15:00', 'subject': '1:1 with Omar', 'all_day': False}]
    with mock.patch.object(rulebook, 'calendar_on', return_value=True), mock.patch.object(calwrite, 'busy', return_value=busy):
        d = rulebook.decide(s, it, vs)
    assert (d['state'], d['verb']) == ('invite_clash', 'propose_time') and d['line'].startswith('Clashes with 1:1 with Omar')
    with mock.patch.object(rulebook, 'calendar_on', return_value=True), mock.patch.object(calwrite, 'busy', return_value=[]):
        assert rulebook.decide(s, it, vs) | {'ask': 0} == {'state': 'invite_free', 'verb': 'accept_invite', 'line': 'Free then.', 'ask': 0}
    # the owner, 2026-10-23 (ruling 4): no calendar connected - nothing to check, so nothing pushed: Next
    with mock.patch.object(rulebook, 'calendar_on', return_value=False):
        assert (rulebook.decide(s, it, vs)['state'], rulebook.decide(s, it, vs)['verb']) == ('invite_no_cal', 'next')


def test_an_agent_with_work_not_pushed_is_review_changes(s):
    t = Factory(s).task(title='Fix the export', kind='coding')
    it = {'key': f'agent:{t}', 'kind': 'agentdone', 'lane': 'done', 'tid': t}
    assert rulebook.decide(s, it, _verbs('close', 'review_changes'))['verb'] is None, 'nothing shows unpushed work, nor when it ended: nothing lit'
    s._exec("INSERT INTO boardnote (TaskId, Agent, Cwd, Kind, Body, CreatedAt) VALUES (?, 'coding', 'C:/x', 'ready', 'ready to push', ?)", (t, at()))
    d = rulebook.decide(s, it, _verbs('close', 'review_changes'))
    assert (d['state'], d['verb'], d['line']) == ('unpushed', 'review_changes', 'Changes ready - not pushed.')
    s._exec("INSERT INTO boardnote (TaskId, Agent, Cwd, Kind, Body, CreatedAt) VALUES (?, 'coding', 'C:/x', 'done', 'pushed', ?)", (t, at()))
    assert rulebook.decide(s, it, _verbs('close', 'review_changes'))['state'] == 'agent_done'


def test_waiting_on_someone_is_chase_after_three_working_days(s):
    f = Factory(s)
    t = f.task(title='Vendor W-9', kind='task', status='waiting'); s._exec("UPDATE task SET WaitingOn='ray.colton@northwind.example' WHERE TaskId=?", (t,))
    it = {'key': f'task:{t}', 'kind': 'todo', 'lane': 'theirs', 'tid': t}
    f.message(task_id=t, subject='W-9?', direction='out', sent_at=at(d=1))
    assert rulebook.decide(s, it, _verbs('defer', 'chase'))['verb'] is None, 'not late: nothing lit (the owner, 2026-10-28)'
    s._exec("UPDATE message SET SentAt=? WHERE TaskId=?", (at(d=7), t))
    d = rulebook.decide(s, it, _verbs('defer', 'chase'))
    assert (d['state'], d['verb']) == ('waiting_late', 'chase') and d['line'].startswith('Ray Colton: ') and d['line'].endswith('days, no answer.')
    assert rulebook.adds(s, it) == ['chase'], 'Chase joins the row on a wait past its day'
    assert rulebook.working_days(datetime(2026, 10, 23), datetime(2026, 10, 26)) == 1, 'a Friday ask is one day old on Monday'


def test_a_goal_step_past_its_day_is_chase_named_in_the_line(s):
    g = s.create_task({'Title': 'Move payroll', 'Status': 'open', 'DoneWhen': 'payroll runs on the new system'}, 'owner')
    s.set_task_checklist(g, ['Export the pay rules', 'schema sign-off'], 'owner')
    k = s.create_task({'Title': 'schema sign-off', 'Status': 'waiting', 'Assignee': 'person:ray.colton@northwind.example', 'ParentId': g,
                       'DueAt': (date.today() - timedelta(days=2)).isoformat()}, 'owner')
    s.link_step(g, s.checklist_id('schema sign-off'), k, 'owner')
    it = {'key': f'task:{g}', 'kind': 'goal_slipped', 'lane': 'yours', 'tid': g}
    d = rulebook.decide(s, it, _verbs('close', 'defer', 'chase'))
    assert (d['state'], d['verb'], d['line']) == ('goal_late', 'chase', "Ray Colton's schema sign-off: 2 days late.")
    s._exec("UPDATE task SET DueAt=? WHERE TaskId=?", ((date.today() + timedelta(days=2)).isoformat(), k))
    assert rulebook.decide(s, it, _verbs('close', 'defer', 'chase'))['verb'] == 'next', 'on track: Next, silent'


def test_a_phish_filed_fyi_lights_not_ours_never_send_to_agent(s):
    """The owner, 2026-10-30: a phishing FYI's row lit Send to agent. Not ours is its move, at once, with no model read and no habit over it;
    an FYI with no danger is read as before."""
    fyi = {'key': 'msg:7', 'kind': 'fyi', 'lane': 'fyi', 'mid': 7}
    d = rulebook.decide(s, {**fyi, 'danger': 'Wants Alex to sign in on a look-alike page.'}, _verbs('mine', 'regular_agent', 'not_ours'))
    assert (d['state'], d['verb'], d['line'], d['ask']) == ('fyi_danger', 'not_ours', '', False)
    assert 'fyi_danger' in rulebook.SAFE
    assert rulebook.decide(s, fyi, _verbs('mine', 'regular_agent', 'not_ours'))['state'] == 'fyi'


def test_unsorted_mail_a_batch_a_closed_task_and_a_failed_report(s):
    assert rulebook.decide(s, {'kind': 'fyi', 'lane': 'unjudged', 'mid': 1}, _verbs('retriage'))['verb'] == 'retriage'
    assert rulebook.decide(s, {'kind': 'fyis', 'lane': 'fyi'}, [])['verb'] == 'next'
    t = Factory(s).task(title='Done already', status='done')
    assert rulebook.decide(s, {'kind': 'todo', 'lane': 'yours', 'tid': t}, _verbs('reopen'))['verb'] is None, "Reopen stays outlined"
    d = rulebook.decide(s, {'kind': 'report', 'lane': 'broken', 'bad': True, 'why': 'mailbox signed out'}, _verbs('rerun'))
    assert (d['state'], d['verb'], d['line']) == ('report_failed', 'rerun', 'Report failed: mailbox signed out')


# ── the tiers: model over rule, never over a safety rule ─────────────────────────────────────────────────────────────────────────────
def _habit(s, text, key):
    """A press count where the 2026-10-23 doc kept it - an install the migration has not reached, or a model that wrote one anyway."""
    s.save_doc('learned', f"# Learned\n\n## How you sort mail\n\n## What you do next\n- {text} [s:5 | ev: pr1, pr2, pr3 | seen: 2026-10-20 | k: {key}]\n", 'test')


def test_a_press_count_lights_nothing(s, monkeypatch):
    """The owner, 2026-10-25: stop learning from presses and remove the habit mark - a press count in the doc, wherever it sits, never
    changes the lit button by itself; the rule (or the model, where intent must be read) decides."""
    t, m, it = _asked(s, 'Weekly report', who=('Vendor Desk', 'desk@vendor.example'), d=2)       # its age is the lit Reply's reason
    monkeypatch.setattr(advisor, '_item', lambda store, tk, ti, key=None: it)
    monkeypatch.setattr(advisor, 'notice', lambda *a, **k: None)
    before = advisor.decide(s, it['key'], preread=False)
    assert before['verb'] == 'reply'
    _habit(s, 'On asks from vendor.example, {{owner_first}} presses Mark done (5 of 6)', 'move asked email vendor.example')
    d = advisor.decide(s, it['key'], preread=False)
    assert (d['verb'], d['by']) == ('reply', 'rule') and 'says' not in d and d['pill'] == d['label'], 'no habit, no count, no mark'


def test_send_is_never_lit_on_a_draft_the_check_flagged(s, monkeypatch):
    t, m, it = _asked(s, 'Invoice 4410', who=('Vendor Desk', 'desk@vendor.example'))
    rid = Factory(s).review(t, m, draft="It goes out in Friday's payment run.")
    it = {**it, 'kind': 'review', 'lane': 'approve', 'rid': rid, 'draft': True, 'key': f'review:{rid}'}
    monkeypatch.setattr(advisor, '_item', lambda store, tk, ti, key=None: it)
    monkeypatch.setattr(advisor, 'notice', lambda *a, **k: None)
    _habit(s, 'On drafts to vendor.example, {{owner_first}} presses Send (5 of 6)', 'move review email vendor.example')
    rev = advisor.revision(s, 'task', t)
    advisor._write(s, target_kind='task', target_id=t, key=it['key'], event=advisor.SHOWN, revision=rev, tier=2,
                   line='Draft promises Friday - nothing here shows it.', verb='redraft', label='Redraft', model='m')
    d = advisor.decide(s, it['key'], preread=False)
    assert (d['verb'], d['by'], d['line']) == ('redraft', 'model', 'Draft promises Friday - nothing here shows it.')


def test_the_model_agreeing_with_the_rule_says_nothing_more(s, monkeypatch):
    """Ruling 1: the obvious button is not explained. The model's verb stands where it differs from the rule's, with its line; agreeing,
    its sentence goes and the rule's own fact stands - and with none, nothing is lit (NO DEFAULT VERB, the owner, 2026-10-28)."""
    t, m, it = _asked(s, 'Badge access')
    monkeypatch.setattr(advisor, '_item', lambda store, tk, ti, key=None: it)
    monkeypatch.setattr(advisor, 'notice', lambda *a, **k: None)
    rev = advisor.revision(s, 'task', t)
    advisor._write(s, target_kind='task', target_id=t, key=it['key'], event=advisor.SHOWN, revision=rev, tier=2,
                   line='Erin is waiting on you - answer her.', verb='reply', label='Reply', model='m')
    d = advisor.decide(s, it['key'], preread=False)
    assert (d['verb'], d['line'], d['by']) == (None, '', 'rule')


def test_the_next_two_are_read_ahead_where_the_model_must_read_them(s, monkeypatch):
    items = [{'key': f'k{n}', 'kind': 'asked' if n % 2 else 'report', 'lane': 'asked', 'tid': n} for n in range(5)]
    monkeypatch.setattr(funnel, 'pile', lambda store, quiet=False: {'items': items})
    monkeypatch.setattr(advisor, 'target_of', lambda store, key: ('task', int(key[1:])))
    monkeypatch.setattr(advisor, 'offered', lambda store, it: _verbs('reply'))
    monkeypatch.setattr(rulebook, 'decide', lambda store, it, vs: {'ask': it['kind'] == 'asked'})
    got = []
    monkeypatch.setattr(advisor, 'notice', lambda store, ev, tk, ti, **kw: got.append((ti, kw.get('tier'), kw.get('key'))))
    class T:
        def __init__(self, target, **kw): self.f = target
        def start(self): self.f()
    monkeypatch.setattr(advisor.threading, 'Thread', T)
    monkeypatch.setattr(advisor, 'BACKGROUND', True)
    advisor._preread(s, 'k0')
    assert got == [(1, 1, 'k1')], 'the next two: k1 is asked (read ahead), k2 is a report (the rule decides it)'


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


# ── a dashboard, and Share, as the rule reads them ──────────────────────────────────────────────────────────────────────────────────
def test_a_dashboard_row_is_silent_with_next_lit_and_share_is_seen_but_never_lit(s):
    """A dashboard's refresh lands under Reports like a report run, and Next walks past it (the owner, 2026-10-23): no line, Next lit.
    Share is on a report's and a dashboard's row for the Advisor to see - and no rule lights it, whatever else the row carries."""
    m = Factory(s).message(subject='Open work - Open tasks 12', body='Open tasks: 12', from_name='Open work', from_email='')
    rep = {'key': f'msg:{m}', 'kind': 'report', 'lane': 'report', 'mid': m}
    dash = {**rep, 'dashboard': True}
    have = [b['verb'] for b in concierge.row_buttons(s, dash)]
    assert 'share_result' in have and 'share_result' in [b['verb'] for b in concierge.row_buttons(s, rep)]
    assert 'share_result' not in [b['verb'] for b in concierge.row_buttons(s, {**rep, 'bad': True})], 'a failed run has nothing to share'
    assert 'share_result' in [v['verb'] for v in advisor.offered(s, dash)], 'the Advisor sees the row has Share'
    assert rulebook.decide(s, dash, _verbs(*have)) == {'state': 'dashboard', 'verb': 'next', 'line': '', 'ask': False}
    assert rulebook.decide(s, rep, _verbs(*have))['verb'] == 'next'
    assert not any('share_result' in w['lit'] or 'share' in w['lit'] for w in words.ADVICE_RULE.values()), 'no state lights Share'
    assert 'share_result' not in [c['verb'] for c in concierge.chips_for(s, dash)], "the phone's chips have no Share menu"


def test_a_draft_says_what_leaves_with_it_beside_send_never_instead(s):
    """WHAT LEAVES WITH A DRAFT (the design rev 2, data leaving): an address its thread never had and the files it carries are one line beside
    the lit Send - no dialog, nothing held. A plain reply to the thread's own people says nothing. Addresses and files, never words."""
    t, m, it = _asked(s, 'Q3 accruals')
    f, V = Factory(s), _verbs('approve', 'redraft')
    rv = f.review(t, m, draft='Here are the Q3 accruals.')
    set_env = lambda env: s._exec('UPDATE review SET Deliver=? WHERE ReviewId=?', (json.dumps(env), rv))
    d = rulebook.decide(s, it, V)
    assert (d['state'], d['verb'], d['line']) == ('draft_ready', 'approve', ''), 'a reply to whom wrote: nothing to say'
    set_env({'kind': 'reply', 'to': ['erin@northwind.example'], 'cc': ['dana@vendor.example']})
    d = rulebook.decide(s, it, V)
    assert (d['verb'], d['line'], d['evidence']) == ('approve', 'Goes to dana@vendor.example - new to this thread.', [f'rv{rv}']), d
    files = [{'name': 'q3.xlsx', 'path': 'x'}]
    set_env({'kind': 'reply', 'to': ['erin@northwind.example'], 'attachments': files})
    assert rulebook.decide(s, it, V)['line'] == 'Sends the file q3.xlsx.'
    set_env({'kind': 'reply', 'to': ['erin@northwind.example', 'dana@vendor.example'], 'attachments': files + [{'name': 'notes.pdf'}]})
    assert rulebook.decide(s, it, V)['line'] == 'Goes to dana@vendor.example, new to this thread, with 2 files.'
    # ...new mail on the task to someone it never had - and the owner's own address is never "new"
    s.set_setting('owner_email', 'alex@northwind.example', 'test')
    set_env({'channel': 'email', 'to': ['paula@northwind.example'], 'cc': ['alex@northwind.example']})
    assert rulebook.decide(s, it, V)['line'] == 'Goes to paula@northwind.example - new to this thread.'


def test_a_task_left_sitting_lights_only_the_models_move_beside_what_is_owed(s):
    """UNTOUCHED TOO LONG (the design rev 2): an open task of the owner's that nothing moved for UNTOUCHED_DAYS working days asks the model
    what is still owed - nothing lit while it reads, then its verb only beside its line; nothing owed is silent."""
    from tests.test_advisor import brain_saying
    t = Factory(s).task(title='Sign the Elm Street lease', kind='task')
    old = (datetime.now() - timedelta(days=12)).strftime('%Y-%m-%d %H:%M:%S')
    it = {'key': f'task:{t}', 'kind': 'own', 'lane': 'mine', 'tid': t, 'title': 'Sign the Elm Street lease'}
    assert rulebook.state(s, it, [])[0] == 'own', 'fresh: the rule lights nothing of its own'
    rev = advisor.revision(s, 'task', t)
    s._exec('UPDATE task SET CreatedAt=?, UpdatedAt=? WHERE TaskId=?', (old, old, t))
    assert rulebook.untouched(s, s.get_task(t)) >= rulebook.UNTOUCHED_DAYS
    assert advisor.revision(s, 'task', t) != rev, 'crossing the line is read again'
    d = rulebook.decide(s, it, _verbs('close', 'defer', 'reply'))
    assert (d['state'], d['verb'], d['line'], d['ask']) == ('untouched', None, '', True)
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


def test_what_leaves_stands_over_the_models_agreeing_send(s):
    t, m, it = _asked(s, 'Q3 accruals')
    Factory(s).review(t, m, draft='Here are the Q3 accruals.', Deliver=json.dumps({'kind': 'reply', 'to': ['erin@northwind.example'], 'cc': ['dana@vendor.example']}))
    s.reconcile_processing_membership(); s.activate_processing_reads(fixed_now=datetime.now().isoformat(), live_state=[]); funnel.invalidate()
    from tests.test_advisor import brain_saying
    advisor.notice(s, advisor.SHOWN, 'task', t, tier=2, wait=True, llm=brain_saying({'verb': 'approve', 'line': '', 'evidence': []}))
    with mock.patch.object(advisor, 'notice'):
        d = advisor.decide(s, f'task:{t}', preread=False)
    assert (d['state'], d['verb'], d['line']) == ('draft_ready', 'approve', 'Goes to dana@vendor.example - new to this thread.'), d
