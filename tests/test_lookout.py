"""LOOKING OUT FOR THE OWNER'S JOB (lookout.py; the owner, 2026-11-02): once a week the Advisor reads the job, the window and what it said
before, proposes at most two ideas - credit, a pain of others to fix, money left on the table, a problem developing, a person to loop in -
and a second look holds what is generic or unsupported. What passes is the ordinary idea row. Alex Doyle's world, invented (CLAUDE.md)."""
import json
from datetime import datetime, timedelta
import pytest
from taskuary import assistant, ideagrade, lookout
from taskuary.store import MemoryStore
from taskuary.testing import Factory

ALEX, GAIL, PAULA, AP = 'alex@northwind.example', 'gail@northwind.example', 'paula@northwind.example', 'billing@vendor.example'
JOB = "## The job\n- I run finance systems at Northwind: the invoice approvals, the vendor master and the month-end reports."
def ago(**k): return (datetime.now() - timedelta(**k)).strftime('%Y-%m-%d %H:%M:%S')


def world():
    s = MemoryStore()
    s.set_setting('owner_email', ALEX, 'test'); s.save_doc('job', JOB, 'test')
    f, ids = Factory(s), {}
    # a weekly backlog report that never drains, the same vendor billed twice, and Gail writing a lot - then hardly at all
    ids['backlog'] = [f.message(from_email='reports@northwind.example', from_name='Payworth', subject=f'Invoices waiting approval - week {w}',
                                body=f'Total waiting: {2500 + w * 40} invoices', sent_at=ago(days=7 * w + 1)) for w in range(4)]
    ids['dup'] = [f.message(from_email=AP, from_name='Vendor billing', subject='Invoice 4471', body='Invoice 4471 for $1,200', sent_at=ago(days=d))
                  for d in (12, 5)]
    for d in (40, 38, 36, 34, 33, 31, 30, 3):
        f.message(from_email=GAIL, from_name='Gail Moreno', subject=f'Ledger sync {d}', conversation_id=f'g{d}', sent_at=ago(days=d))
    ids['mine'] = f.message(direction='out', status='context', subject='Re: Ledger sync', body='On it',
                            RecipientsJson=json.dumps({'to': [GAIL, PAULA]}), sent_at=ago(days=2))
    ids['task'] = f.task(title='Fix the Payworth export', status='done', ClosedAt=ago(days=4))
    return s, ids


def brain(*answers):
    """A scripted model: each call takes the next answer, and what it was asked is kept."""
    seen, it = [], iter(answers)
    def llm(system, user, **kw):
        seen.append((system, user)); return json.dumps(next(it))
    llm.seen = seen
    return llm


def idea(family, title, refs, **k):
    return {'family': family, 'title': title, 'evidence': k.get('evidence', 'seen four Mondays running'), 'refs': refs,
            'why': k.get('why', 'it costs real money'), 'next_step': k.get('next_step', 'Draft the per-approver list'),
            'pitch': k.get('pitch', 'I noticed X and propose Y')}


def test_the_pass_reads_the_job_the_window_the_people_and_what_the_owner_said_before():
    s, ids = world()
    old = s.upsert_idea({'key': 'idea:lookout-old', 'kind': 'pitch', 'text': 'Put the vendor list in a shared sheet', 'action': {'type': 'lookout'}}, ago(days=9))
    assistant.act(s, old['IdeaId'], 'dismiss', 'owner')
    llm = brain({'ideas': []})
    out = lookout.tick(s, llm, force=True)
    assert out == {'ran': True, 'raised': [], 'held': [], 'calls': 1}, 'no idea is an answer: the check is not paid for'
    system, user = llm.seen[0]
    assert 'credit' in system and 'communicate more' in system and 'diagnosis' in system, 'the bar is the prompt'
    assert JOB.splitlines()[1] in user
    assert '"Invoices waiting approval - week 0": 4 message(s)' in user and f"msg{ids['backlog'][0]}" in user, 'grouped, counted, citable'
    assert 'Gail Moreno: the owner wrote to them 1 time(s); from them each week, oldest first:' in user, 'the weekly pattern of who they deal with'
    assert '[pitch] Put the vendor list in a shared sheet - the owner: turned it down' in user, 'what the owner answered is evidence'
    assert f"task{ids['task']} closed" in user


def test_the_check_holds_a_generic_idea_and_the_specific_one_lands_as_an_idea_row_with_its_evidence():
    s, ids = world()
    a, b = ids['dup']
    llm = brain({'ideas': [idea('pitch', 'Communicate more with the approvers', [f"msg{ids['backlog'][0]}"]),
                           idea('money', 'Vendor billing sent invoice 4471 twice - $1,200 may be paid twice', [f'msg{a}', f'msg{b}'],
                                pitch='I caught a $1,200 double invoice before it was paid twice')]},
                {'keep': [2], 'why': {'1': 'generic - no count, no fix'}})
    out = lookout.tick(s, llm, force=True)
    assert out['calls'] == 2 and out['held'] == ['Communicate more with the approvers'] and len(out['raised']) == 1
    i = s.get_idea(out['raised'][0])
    act = json.loads(i['ActionJson'])
    assert i['Key'].startswith('idea:lookout-vendor-billing') and i['Kind'] == 'money' and i['Status'] == 'open'
    assert [e['ref'] for e in act['evidence']] == [f'msg{a}', f'msg{b}'] and 'Vendor billing: Invoice 4471' in act['evidence'][0]['label']
    assert 'Pitch: "I caught a $1,200 double invoice' in act['suggest'] and act['why'].startswith('seen four Mondays')
    check_user = llm.seen[1][1]
    assert f'msg{a}: ' in check_user and 'Invoice 4471' in check_user, 'the check reads what each idea cites'
    held = json.loads(s.get_setting(lookout.HELD_KEY))
    assert held[0]['title'] == 'Communicate more with the approvers' and 'generic' in held[0]['why']
    # ...and it is on the rail as the Advisor's idea, with the verbs every idea has
    from taskuary import funnel
    row = next(x for x in funnel.build(s)['items'] if x.get('idea') == i['IdeaId'])
    assert row['idea_kind'] == 'money' and row['title'] == i['Text']


def test_an_invented_id_a_personal_thread_or_a_turned_down_family_is_never_raised():
    s, ids = world()
    llm = brain({'ideas': [idea('money', 'A charge nobody can find', ['msg987654'])]})
    assert lookout.tick(s, llm, force=True)['raised'] == [] and len(llm.seen) == 1, 'an id the window never showed rests on nothing'
    # No more ideas like this on a credit idea: credit is not asked for again, and one the model offers anyway is dropped
    c = s.upsert_idea({'key': 'idea:lookout-credit-1', 'kind': 'credit', 'text': 'Show the export fix', 'action': {'type': 'lookout'}}, ago(days=8))
    assistant.act(s, c['IdeaId'], 'dismiss_kind', 'owner')
    assert 'credit' not in lookout.families(s)
    user, shown = lookout.window(s)
    assert 'the owner turned down or does not use: credit' in user
    assert lookout._clean(s, idea('credit', 'You fixed the export', [f"task{ids['task']}"]), shown, lookout.families(s)) is None
    assert lookout._clean(s, idea('pitch', 'Fix the export', [f"task{ids['task']}"]), shown, lookout.families(s))['refs'] == [f"task{ids['task']}"]


def test_what_the_owner_and_the_check_turned_down_comes_back_as_evidence():
    s, ids = world()
    llm = brain({'ideas': [idea('early_warning', 'Gail went quiet', [f"msg{ids['mine']}"])]}, {'keep': [], 'why': {'1': 'one message, no pattern'}})
    lookout.tick(s, llm, force=True)
    i = s.upsert_idea({'key': 'idea:lookout-x', 'kind': 'money', 'text': 'Cancel the unused Trainly seats', 'action': {'type': 'lookout'}}, ago(days=1))
    assistant.act(s, i['IdeaId'], 'dismiss_kind', 'owner')
    user, _ = lookout.window(s)
    assert '[money] Cancel the unused Trainly seats - the owner: turned it down - no more ideas like this' in user
    assert '[early_warning] Gail went quiet - held by the check: one message, no pattern' in user


def test_the_cost_is_two_calls_a_day_capped_at_three_and_never_more_than_four_ideas_waiting():
    s, ids = world()
    a, b = ids['dup']
    llm = brain({'ideas': [idea('money', f'Idea {n}', [f'msg{a}']) for n in range(9)]}, {'keep': [1, 2, 3, 4, 5]})
    out = lookout.tick(s, llm)
    assert out['calls'] == 2 and len(out['raised']) == lookout.MAX_IDEAS == 4, 'at most four proposed, checked in one call'
    assert lookout.due(s) is False and lookout.tick(s, brain())['ran'] is False, 'four waiting: no pass, no call'
    for r in lookout.open_ideas(s): s.set_idea_status(r['IdeaId'], 'done', 'owner')
    assert lookout.due(s) is False, 'and a day between passes'
    s.set_setting(lookout.LAST_KEY, ago(days=2), 't'); s.set_setting(lookout.TRIED_KEY, ago(days=2), 't')
    assert lookout.due(s) is True
    # a check whose answer is not an object raises nothing - ask_json re-asks it once (llm.json_of), the third and last call
    odd = brain({'ideas': [idea('pitch', 'Fix the export again', [f'msg{b}'])]}, 'not an object')
    out = lookout.tick(s, odd, force=True)
    assert out['raised'] == [] and out['calls'] == lookout.CALLS == 3 and out['held'] == ['Fix the export again']
    # ...and a brain that never answers in JSON is asked three times at most, whatever ask_json would try next
    calls = []
    def prose(system, user, **k): calls.append(1); return 'I would rather chat'
    out = lookout.tick(s, prose, force=True)
    assert len(calls) == out['calls'] == 2 and out['raised'] == [], 'the re-ask, then the pass waits a day'
    s2, ids2 = world()
    def babble(system, user, **k):
        calls.append(1)
        return json.dumps({'ideas': [idea('money', 'Invoice 4471 twice', [f"msg{ids2['dup'][0]}"])]}) if len(calls) == 2 else 'prose'
    calls.clear(); out = lookout.tick(s2, babble, force=True)
    assert len(calls) == out['calls'] == 3 and out['raised'] == [] and out['held'] == ['Invoice 4471 twice'], 'the check would be a fourth call: held'


def test_a_model_that_did_not_answer_is_tried_again_within_hours_not_a_day():
    s, _ = world()
    out = lookout.tick(s, lambda system, user, **k: 'I cannot help with that')
    assert out == {'ran': True, 'raised': [], 'held': [], 'calls': 2}, 'asked, and re-asked once for the JSON'
    assert not s.get_setting(lookout.LAST_KEY) and s.get_setting(lookout.TRIED_KEY) and lookout.due(s) is False
    s.set_setting(lookout.TRIED_KEY, ago(hours=7), 't')
    assert lookout.due(s) is True


def test_each_family_is_held_to_the_advisors_eighty_percent_bar_and_send_to_agent_carries_the_pitch(monkeypatch):
    assert set(lookout.FAMILIES) == set(ideagrade.LOOKOUT) <= set(ideagrade.MODEL_KINDS)
    s, ids = world()
    a, _b = ids['dup']
    llm = brain({'ideas': [idea('money', 'Invoice 4471 billed twice', [f'msg{a}'], pitch='I caught a double invoice')]}, {'keep': [1]})
    iid = lookout.tick(s, llm, force=True)['raised'][0]
    briefs = []
    from taskuary import ingest
    monkeypatch.setattr(ingest, '_spawn', lambda fn, store, tid, *rest: briefs.append(rest[0] if rest else ''))
    out = assistant.act(s, iid, 'agent', 'owner')
    assert out['taskId'] and 'The one line for the owner\'s boss: I caught a double invoice' in briefs[0]
    assert f'msg{a} - ' in briefs[0] and 'The next step it suggested: Draft the per-approver list' in briefs[0]


@pytest.mark.parametrize('canonical', [False, True])
def test_an_idea_lands_under_the_advisor_never_in_fyi_and_says_its_family(canonical):
    """The owner, 2026-11-02 evening: a lookout idea sits in the rail's Advisor section with the other Advisor ideas, named for its family,
    its pitch on a line of its own - on the old pile and the shared one alike."""
    from taskuary import funnel, lanes
    s, ids = world()
    a, b = ids['dup']
    if canonical:
        n = ago(); s.reconcile_processing_membership(fixed_now=n); s.activate_processing_reads(fixed_now=n, live_state=[])
    llm = brain({'ideas': [idea('money', 'Vendor billing sent invoice 4471 twice', [f'msg{a}', f'msg{b}'], pitch='I caught a double invoice')]}, {'keep': [1]})
    iid = lookout.tick(s, llm, force=True)['raised'][0]
    if canonical: s.reconcile_processing_membership(fixed_now=ago())
    funnel.invalidate()
    row = next(x for x in funnel.pile(s, force=True, quiet=True)['items'] if x.get('idea') == iid)
    assert (row['kind'], lanes.level_of(row)) == ('idea', 'ideas'), row
    assert {f: lanes.idea_word(f) for f in lookout.FAMILIES} == {'credit': 'credit', 'pitch': 'pain → fix', 'money': 'money left on the table',
                                                              'early_warning': 'early warning', 'leverage': 'leverage'}
    assert all(lanes.idea_section(f) == 'ideas' for f in lookout.FAMILIES)
    assert json.loads(s.get_idea(iid)['ActionJson'])['suggest'].endswith('\nPitch: "I caught a double invoice"')


def test_a_daily_pass_never_says_yesterdays_idea_again_the_check_reads_what_was_raised():
    s, ids = world()
    a, _b = ids['dup']
    lookout.tick(s, brain({'ideas': [idea('money', 'Invoice 4471 billed twice', [f'msg{a}'])]}, {'keep': [1]}), force=True)
    llm = brain({'ideas': [idea('money', 'Payworth charged invoice 4471 two times', [f'msg{a}'])]}, {'keep': [], 'why': {'1': 'already raised'}})
    out = lookout.tick(s, llm, force=True)
    assert out['raised'] == [] and 'ALREADY RAISED' in llm.seen[1][1] and 'Invoice 4471 billed twice' in llm.seen[1][1], 'the check sees it'
    assert lookout.EVERY_DAYS == 1, 'once a day (the owner, 2026-11-03)'


# ── ITS OWN CLOCK, AND NOW WHEN ASKED (2026-11-03) ────────────────────────────────────────────────────────────────────────────────────
def test_the_pass_runs_on_the_advisors_own_clock_never_inside_a_report_run(monkeypatch):
    """The root cause: the pass sat in assistant.run under `if report_id is None:`, and the scheduler always runs the Advisor with its
    report_id - so it had never run on a live home. It is the clock's now (assistant.clock), and the Advisor report's off switch stops it."""
    import inspect
    from taskuary import wsboot
    assert 'lookout' not in inspect.getsource(assistant.run) and 'wsboot' not in inspect.getsource(assistant.run)
    s, _ = world()
    ran = []
    monkeypatch.setattr(lookout, 'tick', lambda store, *a, **k: ran.append('lookout'))
    monkeypatch.setattr(wsboot, 'tick', lambda store, *a, **k: ran.append('wsboot'))
    monkeypatch.setattr(lookout, 'CLOCK', True)
    src = assistant.source(s)
    assert src and src.get('Active'), 'the seeded Advisor report is on'
    assistant.clock(s)
    assert ran == ['wsboot', 'lookout']
    s.save_source({**{k: v for k, v in src.items() if k != 'cfg'}, 'Active': 0}, 'owner')
    ran.clear(); assistant.clock(s)
    assert ran == [], 'the Advisor switched off: neither pass'


def test_the_server_clock_runs_it_off_the_reports_lock_at_most_every_fifteen_minutes(monkeypatch):
    import threading
    from taskuary import demo, server
    done, calls = threading.Event(), []
    monkeypatch.setattr(assistant, 'clock', lambda store: (calls.append(1), done.set()))
    monkeypatch.setattr(demo, 'enabled', lambda: False)
    monkeypatch.setattr(server, '_ADVISOR_AT', [0.0])
    t0 = 10_000.0
    assert server.advisor_pass(t0) is True and done.wait(5)
    assert server.advisor_pass(t0 + 60) is False, 'a tick a minute later does not look again'
    assert server._ADVISOR_BUSY.acquire(timeout=5); server._ADVISOR_BUSY.release()
    done.clear(); assert server.advisor_pass(t0 + server.ADVISOR_TICK) is True and done.wait(5) and calls == [1, 1]
    monkeypatch.setattr(demo, 'enabled', lambda: True)
    assert server.advisor_pass(t0 + 3 * server.ADVISOR_TICK) is False, 'the demo world runs nothing on a clock'


def asked(s, monkeypatch, llm):
    """The Assistant's advisor.ideas through the chat's own road: (the line said at once, the line said when the pass ends or None)."""
    import threading
    from taskuary import concierge
    monkeypatch.setattr(lookout, 'brain', lambda store: llm)
    got, done = [], threading.Event()
    real = concierge.record
    def record(store, tid, role, text, *a, **k):
        if text.startswith('The pass for ideas'): got.append(text); done.set()
        return real(store, tid, role, text, *a, **k)
    monkeypatch.setattr(concierge, 'record', record)
    out = concierge.call_turn(s, 0, {'kind': 'advisor.ideas', 'params': {}}, None, 'look for ideas for my job now')
    assert out['did'] == 'advisor.ideas'
    if out['started']: assert done.wait(10)
    return out['say'], (got or [None])[0]


def test_asking_the_assistant_starts_a_pass_now_and_says_how_many_ideas_it_raised(monkeypatch):
    from taskuary import toolcatalog
    assert 'advisor.ideas' in {k for _, _, ks in toolcatalog.BUCKETS for k in ks} and 'runs at once, said' in toolcatalog.describe('advisor.ideas')
    assert toolcatalog.valid('advisor.ideas', {}) == '' and len(toolcatalog.block()) < 7950
    s, ids = world()
    a, b = ids['dup']
    s.set_setting(lookout.LAST_KEY, ago(hours=1), 't')                  # it ran an hour ago: the day is not up, the owner's ask still runs it
    llm = brain({'ideas': [idea('money', 'Vendor billing sent invoice 4471 twice', [f'msg{a}', f'msg{b}']),
                           idea('pitch', 'Communicate more with the approvers', [f"msg{ids['backlog'][0]}"])]},
                {'keep': [1], 'why': {'2': 'generic'}})
    now, later = asked(s, monkeypatch, llm)
    assert now.startswith('Started a pass for ideas for your job'), now
    assert later == 'The pass for ideas for your job raised 1 idea, 1 held back by the second look - under Advisor.', later
    assert [r['Key'] for r in lookout.open_ideas(s)] == ['idea:lookout-vendor-billing-sent-invoice-4471-twice'], 'an ordinary Advisor idea row'


def test_an_asked_pass_still_keeps_max_open_waiting_at_most_and_needs_an_ai(monkeypatch):
    s, ids = world()
    for n in range(lookout.MAX_OPEN): s.upsert_idea({'key': f'{lookout.KEY}old-{n}', 'kind': 'money', 'text': f'Old {n}', 'action': {'type': 'lookout'}}, ago(days=1))
    never = brain()                                                         # any call would fail: nothing may be asked
    now, later = asked(s, monkeypatch, never)
    assert now.startswith(f'Nothing started: {lookout.MAX_OPEN} ideas for your job already wait under Advisor') and later is None and not never.seen
    s2, _ = world()
    now, later = asked(s2, monkeypatch, None)
    assert now.startswith('Nothing started: no AI is connected') and later is None and not s2.get_setting(lookout.TRIED_KEY)
    now, later = asked(s2, monkeypatch, lambda system, user, **k: 'I would rather chat')
    assert later == 'The pass for ideas for your job got no answer from the AI - nothing raised. Ask again in a while.'


def test_four_ideas_the_owner_read_leave_room_for_the_next_days_pass():
    """The live shape (2026-11-12): four ideas raised on one morning, each opened and read - off the rail, still open - and the daily pass
    never ran again: six days with no idea for the owner's job. Waiting means on the rail; one put away till a later day still waits."""
    from taskuary import funnel
    s, ids = world()
    a, b = ids['dup']
    n = ago(); s.reconcile_processing_membership(fixed_now=n); s.activate_processing_reads(fixed_now=n, live_state=[])
    def rail():
        s.reconcile_processing_membership(fixed_now=ago()); funnel.invalidate()
        return [x for x in funnel.pile(s, force=True, quiet=True)['items'] if x.get('kind') == 'idea']
    for t in ('Invoice 4471 billed twice', 'Trainly seats unused for 60 days', 'Payworth late fee on the 14th', 'Spendly renewal at a higher tier'):
        lookout.tick(s, brain({'ideas': [idea('money', t, [f'msg{a}', f'msg{b}'])]}, {'keep': [1]}), force=True)
    assert len(rail()) == 4 and len(lookout.waiting(s)) == 4 and lookout.tick(s, brain(), force=True)['ran'] is False, 'four on the rail: no pass'
    first = rail()[0]
    s.set_idea_status(first['idea'], 'snoozed', 'owner'); s._exec('UPDATE idea SET SnoozeUntil=? WHERE IdeaId=?', (ago(days=-2), first['idea']))
    for x in rail(): funnel.settle(s, x['key'], 'surfaced', read=True)                    # the owner opens each and reads it
    assert rail() == [] and len(lookout.open_ideas(s)) == 4, 'read: off the rail, still open'
    assert [i['IdeaId'] for i in lookout.waiting(s)] == [first['idea']], 'the one put away till Saturday still waits'
    s.set_setting(lookout.LAST_KEY, ago(days=2), 't'); s.set_setting(lookout.TRIED_KEY, ago(days=2), 't')
    assert lookout.due(s) is True
    out = lookout.tick(s, brain({'ideas': [idea('money', 'Vendor billing charged $900 twice in October', [f'msg{a}', f'msg{b}'])]}, {'keep': [1]}))
    assert len(out['raised']) == 1 and [x['title'] for x in rail()] == ['Vendor billing charged $900 twice in October']


def test_the_days_pass_runs_from_the_morning_not_a_day_after_the_last(monkeypatch):
    """It drifted to 5:53 PM: the pass ran 24 hours after the one before (2026-11-05). Once a calendar day, from MORNING_H."""
    from datetime import datetime
    s, _ = world()
    monkeypatch.setattr(lookout, '_now', lambda: datetime(2026, 11, 5, 8, 0))
    s.set_setting(lookout.LAST_KEY, '2026-11-04 17:53:56', 't'); s.set_setting(lookout.TRIED_KEY, '2026-11-04 17:53:41', 't')
    assert lookout.due(s) is True, 'yesterday evening, this morning: due'
    monkeypatch.setattr(lookout, '_now', lambda: datetime(2026, 11, 5, 6, 0))
    assert lookout.due(s) is False, 'before the morning, and under a day: wait'
    s.set_setting(lookout.LAST_KEY, '2026-11-05 07:30:00', 't'); s.set_setting(lookout.TRIED_KEY, '2026-11-05 07:30:00', 't')
    monkeypatch.setattr(lookout, '_now', lambda: datetime(2026, 11, 5, 18, 0))
    assert lookout.due(s) is False, 'ran today: not again'
