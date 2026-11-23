"""LOOKING OUT FOR THE OWNER'S JOB (lookout.py; the owner, 2026-11-02): once a day the Advisor reads the job, the window and what it said
before, may read further with read-only tools, and proposes - credit, a pain of others to fix, money left on the table, a problem
developing, a person to loop in. Plain code checks every quote and number against what the run read (2026-11-23); what passes is the
ordinary idea row. Alex Doyle's world, invented (CLAUDE.md)."""
import json, re
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


def quoted(user, ref):
    "Words the run was shown of `ref`, copied from its line as a careful model would: the subject in quotes, else the line's own words."
    for l in user.splitlines():
        if re.search(rf'\b{ref}\b', l):
            m = re.search(r'"([^"]{8,})"', l)
            return m.group(1) if m else l.strip()[:30]
    return 'nothing like this was shown'


def brain(*answers):
    """A scripted model: each call takes the next answer, and what it was asked is kept. An idea given `refs` and no quotes quotes each ref
    from what this call was shown."""
    seen, it = [], iter(answers)
    def llm(system, user, **kw):
        seen.append((system, user)); a = next(it)
        if isinstance(a, dict):
            a = {'reads': a.get('reads') or [], 'ideas': [{k: v for k, v in d.items() if k != 'refs'}
                                                          | {'quotes': d.get('quotes') or [{'ref': r, 'quote': quoted(user, r)} for r in d.get('refs') or []],
                                                             'counts': d.get('counts') or []} for d in a.get('ideas') or []]}
        return json.dumps(a) if not isinstance(a, str) else a
    llm.seen = seen
    return llm


def idea(family, title, refs, **k):
    return {'family': family, 'title': title, 'evidence': k.get('evidence', 'seen four Mondays running'), 'refs': refs,
            'why': k.get('why', 'it costs real money'), 'next_step': k.get('next_step', 'Draft the per-approver list'),
            'pitch': k.get('pitch', 'I noticed X and propose Y'), **({'quotes': k['quotes']} if 'quotes' in k else {}),
            **({'counts': k['counts']} if 'counts' in k else {})}


def rd(tool, **k): return {'tool': tool, 'q': None, 'sent': None, 'days': None, 'id': None, 'name': None} | k


def test_the_pass_reads_the_job_the_window_the_people_and_what_the_owner_said_before():
    s, ids = world()
    old = s.upsert_idea({'key': 'idea:lookout-old', 'kind': 'pitch', 'text': 'Put the vendor list in a shared sheet', 'action': {'type': 'lookout'}}, ago(days=9))
    assistant.act(s, old['IdeaId'], 'dismiss', 'owner')
    llm = brain({'ideas': []})
    out = lookout.tick(s, llm, force=True)
    assert out == {'ran': True, 'raised': [], 'updated': [], 'held': [], 'calls': 1, 'deep': ['source:email']}, 'no idea is an answer, in one call'
    system, user = llm.seen[0]
    assert 'credit' in system and 'communicate more' in system and 'diagnosis' in system, 'the bar is the prompt'
    assert all(t in system for t in lookout.READS) and 'word for word' in system.lower(), 'it is told the tools it may read with, and that quotes are checked'
    assert JOB.splitlines()[1] in user
    assert '"Invoices waiting approval - week 0": 4 message(s)' in user and f"msg{ids['backlog'][0]}" in user, 'grouped, counted, citable'
    assert 'Gail Moreno: the owner wrote to them 1 time(s); from them each week, oldest first:' in user, 'the weekly pattern of who they deal with'
    assert '[pitch] Put the vendor list in a shared sheet - the owner: turned it down' in user, 'what the owner answered is evidence'
    assert f"task{ids['task']} closed" in user


def test_a_quote_not_in_what_it_read_or_a_number_it_cannot_back_drops_the_idea_and_the_good_one_lands_with_its_evidence():
    """EVIDENCE CHECKED IN CODE (the design review, 2026-11-23): no second model. A quote must stand word for word in what the run was shown
    of the id it cites, and each number must be in what it cites - else the idea is dropped, and why is kept for the next run."""
    s, ids = world()
    a, b = ids['dup']
    w = f"msg{ids['backlog'][0]}"
    llm = brain({'ideas': [idea('pitch', 'Approvers sit on invoices', [w], quotes=[{'ref': w, 'quote': 'approvers ignore the queue'}]),
                           idea('early_warning', 'The backlog will pass 3000 invoices next month', [w]),
                           idea('money', 'Vendor billing sent invoice 4471 twice - $1,200 may be paid twice', [f'msg{a}', f'msg{b}'],
                                pitch='I caught a $1,200 double invoice before it was paid twice')]})
    out = lookout.tick(s, llm, force=True)
    assert out['calls'] == 1 and out['held'] == ['Approvers sit on invoices', 'The backlog will pass 3000 invoices next month'] and len(out['raised']) == 1
    held = {h['title']: h['why'] for h in json.loads(s.get_setting(lookout.HELD_KEY))}
    assert held['Approvers sit on invoices'] == f'the words "approvers ignore the queue" are not in {w} as read'
    assert held['The backlog will pass 3000 invoices next month'] == 'the number 3000 is not in what it cites'
    i = s.get_idea(out['raised'][0])
    act = json.loads(i['ActionJson'])
    assert i['Key'].startswith('idea:lookout-vendor-billing') and i['Kind'] == 'money' and i['Status'] == 'open'
    assert [e['ref'] for e in act['evidence']] == [f'msg{a}', f'msg{b}'] and 'Vendor billing: Invoice 4471' in act['evidence'][0]['label']
    assert act['evidence'][0]['quote'] == 'Invoice 4471', 'the words it rests on travel with it'
    assert 'Pitch: "I caught a $1,200 double invoice' in act['suggest'] and act['why'].startswith('seen four Mondays')
    # ...and it is on the rail as the Advisor's idea, with the verbs every idea has
    from taskuary import funnel
    row = next(x for x in funnel.build(s)['items'] if x.get('idea') == i['IdeaId'])
    assert row['idea_kind'] == 'money' and row['title'] == i['Text']


def test_the_run_reads_before_it_proposes_and_a_count_it_claims_is_counted_again():
    """ONE RUN WITH READ-ONLY TOOLS: it searches the mail - his sent mail too - reads a message whole, and only then proposes; a count it
    states is run again by the code and must match. Nothing it may call moves anything."""
    s, ids = world()
    a, b = ids['dup']
    llm = brain({'reads': [rd('search_mail', q='invoice 4471'), rd('search_mail', q='ledger sync', sent=True), rd('read_message', id=f'msg{b}'),
                           rd('memory', q='invoice approvals'), rd('read_task', id=f"task{ids['task']}")]},
                {'ideas': [idea('money', 'Invoice 4471 came 2 times in a week from Vendor billing', [f'msg{a}'],
                                counts=[{'search': 'invoice 4471', 'sent': None, 'days': None, 'n': 2}]),
                           idea('pitch', 'Invoice 4471 came 3 times', [f'msg{b}'], counts=[{'search': 'invoice 4471', 'sent': None, 'days': None, 'n': 3}])]})
    out = lookout.tick(s, llm, force=True)
    told = llm.seen[1][1]
    assert 'search_mail "invoice 4471" (in and out, 30 days): 2 match' in told and 'search_mail "ledger sync" (his sent mail, 30 days): 1 match' in told
    assert f'msg{b} ' in told and 'Invoice 4471 for $1,200' in told and 'I run finance systems at Northwind' in told and 'Fix the Payworth export' in told
    assert out['calls'] == 2 and [s.get_idea(i)['Text'] for i in out['raised']] == ['Invoice 4471 came 2 times in a week from Vendor billing']
    assert json.loads(s.get_setting(lookout.HELD_KEY))[0]['why'] == 'it says 3 for "invoice 4471"; the mail holds 2'
    assert lookout.runs(s)[0]['reads'][:2] == ['search_mail invoice 4471', 'search_mail ledger sync'], 'what it read is on its run line'


def test_an_invented_id_a_personal_thread_or_a_turned_down_family_is_never_raised():
    s, ids = world()
    llm = brain({'ideas': [idea('money', 'A charge nobody can find', ['msg987654'], quotes=[{'ref': 'msg987654', 'quote': 'a charge of some kind'}])]})
    assert lookout.tick(s, llm, force=True)['raised'] == [] and len(llm.seen) == 1, 'an id the run never read rests on nothing'
    # No more ideas like this on a credit idea: credit is not asked for again, and one the model offers anyway is dropped
    c = s.upsert_idea({'key': 'idea:lookout-credit-1', 'kind': 'credit', 'text': 'Show the export fix', 'action': {'type': 'lookout'}}, ago(days=8))
    assistant.act(s, c['IdeaId'], 'dismiss_kind', 'owner')
    assert 'credit' not in lookout.families(s)
    user, seen, _ = lookout.window(s)
    assert 'the owner turned down or does not use: credit' in user
    t = f"task{ids['task']}"
    q = [{'ref': t, 'quote': 'Fix the Payworth export'}]
    assert lookout.verify(s, idea('credit', 'You fixed the export', [t], quotes=q), seen, {}, lookout.families(s)) == (None, 'not a family it may raise now')
    assert lookout.verify(s, idea('pitch', 'Fix the export', [t], quotes=q), seen, {}, lookout.families(s))[0]['refs'] == [t]
    # ...and a thread under a personal workstream is never read, so never cited
    from taskuary import workstreams
    workstreams.save(s, [{'name': 'Personal', 'personal': True}], 'test')
    s._exec('UPDATE message SET Workstream=? WHERE MessageId=?', ('personal', ids['dup'][0]))
    assert f"msg{ids['dup'][0]}" not in lookout.window(s)[1]
    assert lookout.read(s, rd('read_message', id=f"msg{ids['dup'][0]}"), {}, {}).endswith('personal - not read')
    assert lookout.count(s, 'invoice 4471') and all(m['MessageId'] != ids['dup'][0] for m in lookout.count(s, 'invoice 4471'))


def test_what_the_owner_turned_down_and_what_the_code_held_comes_back_as_evidence_never_as_citable():
    s, ids = world()
    llm = brain({'ideas': [idea('early_warning', 'Gail went quiet', [f"msg{ids['mine']}"], quotes=[{'ref': 'msg424242', 'quote': 'nothing of the sort'}])]})
    lookout.tick(s, llm, force=True)
    i = s.upsert_idea({'key': 'idea:lookout-x', 'kind': 'money', 'text': 'Cancel the unused Trainly seats', 'action': {'type': 'lookout'}}, ago(days=1))
    assistant.act(s, i['IdeaId'], 'dismiss_kind', 'owner')
    user, seen, _ = lookout.window(s)
    assert '[money] Cancel the unused Trainly seats - the owner: turned it down - no more ideas like this' in user
    assert '[early_warning] Gail went quiet - held back: it cites msg424242, which the run never read' in user
    assert 'msg424242' not in seen, 'an id named only in what was held is no evidence'


def test_a_run_is_a_few_turns_at_most_three_raised_and_never_more_than_six_ideas_waiting():
    s, ids = world()
    a, b = ids['dup']
    w, g, t = f"msg{ids['backlog'][0]}", f"msg{ids['mine']}", f"task{ids['task']}"
    llm = brain({'ideas': [idea('money', 'Invoice 4471 billed twice', [f'msg{a}']), idea('pitch', 'The approval backlog never drains', [w]),
                           idea('reminder', 'Gail is owed an answer on the ledger sync', [g]), idea('credit', 'The export fix saved the close', [t]),
                           idea('new_idea', 'A weekly check on the approval queue', [w]), idea('leverage', 'Loop Paula into the ledger sync', [g])]})
    out = lookout.tick(s, llm)
    assert out['calls'] == 1 and len(out['raised']) == lookout.MAX_RAISE == 3, 'three land'
    assert len(out['held']) == lookout.MAX_IDEAS - 3, 'five read at most; past three they are held as enough for now'
    assert lookout.due(s) is False, 'a pass just ran'
    s.set_setting(lookout.LAST_KEY, ago(days=2), 't'); s.set_setting(lookout.TRIED_KEY, ago(days=2), 't')
    for n in range(3): s.upsert_idea({'key': f'{lookout.KEY}more-{n}', 'kind': 'money', 'text': f'More {n}', 'action': {'type': 'lookout'}}, ago(hours=1))
    assert lookout.why_not(s) == '6 ideas already wait on the rail (at most 6)' and lookout.tick(s, brain())['ran'] is False, 'six waiting: no pass, no call'
    for r in lookout.open_ideas(s): s.set_idea_status(r['IdeaId'], 'done', 'owner')
    assert lookout.due(s) is True
    # a model that keeps reading is told its last turn is its last: STEPS turns, then its ideas or nothing
    reader = brain(*[{'reads': [rd('search_mail', q='invoice')]}] * lookout.STEPS)
    out = lookout.tick(s, reader, force=True)
    assert out['calls'] == lookout.STEPS and 'This is your last turn' in reader.seen[-1][1] and out['raised'] == []
    # ...and a brain that never answers in JSON is asked twice, then the pass waits
    calls = []
    def prose(system, user, **k): calls.append(1); return 'I would rather chat'
    out = lookout.tick(s, prose, force=True)
    assert len(calls) == out['calls'] == 2 and out['raised'] == [], 'the re-ask, then the pass waits'
    assert lookout.CALLS >= lookout.STEPS


def test_a_model_that_did_not_answer_is_tried_again_within_hours_not_a_day():
    s, _ = world()
    out = lookout.tick(s, lambda system, user, **k: 'I cannot help with that')
    assert out == {'ran': True, 'raised': [], 'held': [], 'calls': 2, 'deep': ['source:email']}, 'asked, and re-asked once for the JSON'
    assert not s.get_setting(lookout.LAST_KEY) and s.get_setting(lookout.TRIED_KEY) and lookout.due(s) is False
    s.set_setting(lookout.TRIED_KEY, ago(hours=7), 't')
    assert lookout.due(s) is True


def test_each_family_is_held_to_the_advisors_eighty_percent_bar_and_send_to_agent_carries_the_pitch(monkeypatch):
    assert set(lookout.FAMILIES) == set(ideagrade.LOOKOUT) <= set(ideagrade.MODEL_KINDS)
    s, ids = world()
    a, _b = ids['dup']
    llm = brain({'ideas': [idea('money', 'Invoice 4471 billed twice', [f'msg{a}'], pitch='I caught a double invoice')]})
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
    llm = brain({'ideas': [idea('money', 'Vendor billing sent invoice 4471 twice', [f'msg{a}', f'msg{b}'], pitch='I caught a double invoice')]})
    iid = lookout.tick(s, llm, force=True)['raised'][0]
    if canonical: s.reconcile_processing_membership(fixed_now=ago())
    funnel.invalidate()
    row = next(x for x in funnel.pile(s, force=True, quiet=True)['items'] if x.get('idea') == iid)
    assert (row['kind'], lanes.level_of(row)) == ('idea', 'ideas'), row
    assert {f: lanes.idea_word(f) for f in lookout.FAMILIES} == {'credit': 'credit', 'pitch': 'pain → fix', 'money': 'money left on the table',
                                                              'early_warning': 'early warning', 'leverage': 'leverage', 'reminder': 'slipped through',
                                                              'connection': 'joined up', 'new_idea': 'new idea'}
    assert all(lanes.idea_section(f) == 'ideas' for f in lookout.FAMILIES)
    assert json.loads(s.get_idea(iid)['ActionJson'])['suggest'].endswith('\nPitch: "I caught a double invoice"')


def test_a_daily_pass_never_says_yesterdays_idea_again_whatever_its_words():
    """IDENTITY IS ITS SUBJECTS AND ITS FAMILY (the design review, 2026-11-23): the same subjects in the same family, reworded, is the same
    idea - held as said, the run reading it under BEFORE - with nothing new to update it with."""
    s, ids = world()
    a, _b = ids['dup']
    first = lookout.tick(s, brain({'ideas': [idea('money', 'Invoice 4471 billed twice', [f'msg{a}'])]}), force=True)['raised'][0]
    llm = brain({'ideas': [idea('money', 'Payworth charged invoice 4471 two times', [f'msg{a}'])]})
    out = lookout.tick(s, llm, force=True)
    assert out['raised'] == [] and out['updated'] == [] and '[money] Invoice 4471 billed twice - the owner: not answered yet' in llm.seen[0][1]
    assert json.loads(s.get_setting(lookout.HELD_KEY))[0]['why'] == 'said before as "Invoice 4471 billed twice" - nothing new since'
    assert s.get_idea(first)['Text'] == 'Invoice 4471 billed twice'
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
    from taskuary import brainroute, learning
    done, calls, reflected, held = threading.Event(), [], [], [False]
    monkeypatch.setattr(assistant, 'clock', lambda store: (calls.append(1), done.set()))
    # ...and what the verdicts taught is consolidated on the same clock: an app left open all week reflected only at its next start
    monkeypatch.setattr(learning, 'reflect_if_due', lambda store: reflected.append(1))
    monkeypatch.setattr(brainroute, 'auto_held', lambda store: held[0])
    monkeypatch.setattr(demo, 'enabled', lambda: False)
    monkeypatch.setattr(server, '_ADVISOR_AT', [0.0])
    t0 = 10_000.0
    assert server.advisor_pass(t0) is True and done.wait(5)
    assert server.advisor_pass(t0 + 60) is False, 'a tick a minute later does not look again'
    assert server._ADVISOR_BUSY.acquire(timeout=5); server._ADVISOR_BUSY.release()
    held[0] = True                                   # past the day's AI ceiling nothing unasked runs, reflection included
    done.clear(); assert server.advisor_pass(t0 + server.ADVISOR_TICK) is True and done.wait(5) and calls == [1, 1]
    assert reflected == [1], 'once on the first tick, and not while the ceiling holds'
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
                           idea('pitch', 'Approvers clear 90 invoices a day', [f"msg{ids['backlog'][0]}"])]})
    now, later = asked(s, monkeypatch, llm)
    assert now.startswith('Started a pass for ideas for your job'), now
    assert later == 'The pass for ideas for your job raised 1 idea, 1 held back - its evidence did not hold or it was said before - under Advisor.', later
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
    for f, t in (('money', 'Invoice 4471 billed twice'), ('pitch', 'Vendor billing sends every invoice twice'),
                 ('early_warning', 'Invoice 4471 will be paid twice on the next run'), ('connection', 'The double invoice and the export fix are one bug')):
        lookout.tick(s, brain({'ideas': [idea(f, t, [f'msg{a}', f'msg{b}'])]}), force=True)
    assert len(rail()) == 4 and len(lookout.waiting(s)) == 4 and lookout.tick(s, brain(), force=True)['ran'] is False, 'four on the rail: no pass'
    first = rail()[0]
    s.set_idea_status(first['idea'], 'snoozed', 'owner'); s._exec('UPDATE idea SET SnoozeUntil=? WHERE IdeaId=?', (ago(days=-2), first['idea']))
    for x in rail(): funnel.settle(s, x['key'], 'surfaced', read=True)                    # the owner opens each and reads it
    assert rail() == [] and len(lookout.open_ideas(s)) == 4, 'read: off the rail, still open'
    assert [i['IdeaId'] for i in lookout.waiting(s)] == [first['idea']], 'the one put away till Saturday still waits'
    s.set_setting(lookout.LAST_KEY, ago(days=2), 't'); s.set_setting(lookout.TRIED_KEY, ago(days=2), 't')
    assert lookout.due(s) is True
    out = lookout.tick(s, brain({'ideas': [idea('leverage', 'Vendor billing would fix the double invoices for one ask', [f'msg{a}', f'msg{b}'])]}))
    assert len(out['raised']) == 1 and [x['title'] for x in rail()] == ['Vendor billing would fix the double invoices for one ask']


def test_a_family_under_the_bar_still_raises_one_idea_a_day():
    s, ids = world()
    a, b = ids['dup']
    for n in range(10): s.upsert_idea({'key': f'{lookout.KEY}old-{n}', 'kind': 'money', 'text': f'Old {n}', 'action': {'type': 'lookout'}}, ago(days=3))
    s._exec("UPDATE idea SET Status='dismissed', DecidedBy='owner'")                    # ten he turned down: walking past would teach nothing
    s.set_setting(ideagrade.SINCE_KEY, ago(days=20), 't')
    assert 'money' in ideagrade.quiet_kinds(s) and 'money' in lookout.families(s), 'quiet, and still asked for'
    out = lookout.tick(s, brain({'ideas': [idea('money', 'Invoice 4471 billed twice', [f'msg{a}']),
                                           idea('money', 'The approval backlog costs late fees', [f"msg{ids['backlog'][0]}"])]}), force=True)
    assert [s.get_idea(i)['Text'] for i in out['raised']] == ['Invoice 4471 billed twice'], 'one a day'
    assert 'money' not in lookout.families(s), 'its one raised: not asked for again today'


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


def test_what_the_code_held_is_never_said_to_be_raised_and_a_held_theme_lands_once_its_evidence_holds():
    """The owner's live Advisor, 2026-11-14..18: a theme held once was held as "already raised" every morning after. What the code held
    reaches the next run as held, with why - never as raised - and the same theme lands when its evidence holds."""
    s, ids = world()
    a, b = ids['dup']
    first = brain({'ideas': [idea('money', 'Vendor billing sent invoice 4471 3 times', [f'msg{a}', f'msg{b}'])]})
    assert lookout.tick(s, first, force=True)['raised'] == []
    user = lookout.window(s)[0]
    assert '[money] Vendor billing sent invoice 4471 3 times - held back: the number 3 is not in what it cites' in user
    assert '- the owner:' not in user.split('Vendor billing sent invoice 4471 3 times')[1].split(chr(10))[0], 'held, never raised'
    again = brain({'ideas': [idea('money', 'Vendor billing sent invoice 4471 2 times in a week', [f'msg{a}', f'msg{b}'])]})
    assert len(lookout.tick(s, again, force=True)['raised']) == 1, 'two cited: the number is its own'
    assert '[money] Vendor billing sent invoice 4471 2 times in a week - the owner: not answered yet' in lookout.window(s)[0]


def test_new_evidence_updates_the_idea_in_place_and_a_new_angle_is_a_new_idea():
    """The owner, 2026-11-18: "when you run the next advisor it replaces it or does not say the same thing twice". The same subjects in the
    same family with new evidence update the one idea in place - one row, never said twice; the same subjects in another family are a new
    angle and a new idea; and one he put down is never raised again, new evidence or not."""
    s, ids = world()
    a, b = ids['dup']
    old = lookout.tick(s, brain({'ideas': [idea('money', 'Vendor billing sent invoice 4471 twice', [f'msg{a}'])]}), force=True)['raised'][0]
    out = lookout.tick(s, brain({'ideas': [idea('money', 'Vendor billing billed invoice 4471 again five days ago', [f'msg{a}', f'msg{b}'])]}), force=True)
    assert out['raised'] == [] and out['updated'] == [old] and s.get_idea(old)['Text'] == 'Vendor billing billed invoice 4471 again five days ago'
    act = json.loads(s.get_idea(old)['ActionJson'])
    assert [e['ref'] for e in act['evidence']] == [f'msg{a}', f'msg{b}'] and len(lookout.open_ideas(s)) == 1
    angle = lookout.tick(s, brain({'ideas': [idea('pitch', 'Vendor billing double-bills: ask them to fix their export', [f'msg{a}', f'msg{b}'])]}), force=True)
    assert len(angle['raised']) == 1 and len(lookout.open_ideas(s)) == 2, 'another family on the same subjects is a new angle'
    s.set_idea_status(old, 'done', 'owner')
    Factory(s).message(from_email=AP, from_name='Vendor billing', subject='Invoice 4471', body='Invoice 4471 for $1,200', sent_at=ago(days=1))
    again = lookout.tick(s, brain({'ideas': [idea('money', 'Vendor billing sent invoice 4471 a third time', [f'msg{a}', f'msg{b}'])]}), force=True)
    assert again['raised'] == again['updated'] == [] and s.get_idea(old)['Status'] == 'done', 'handled: not said again'


# ── THE OWNER, 2026-11-23: 2-3 GOOD IDEAS A DAY, ROTATING THROUGH THE SYSTEMS, NEVER THE SAME THING TWICE ─────────────────────────────────
def busy_week():
    """Alex's week, invented: two expense tools billing for the same job, an ask of his Gail never answered, and the nightly ledger
    export failing the same way four nights running."""
    s = MemoryStore()
    s.set_setting('owner_email', ALEX, 'test'); s.save_doc('job', JOB, 'test')
    f, ids = Factory(s), {}
    ids['subs'] = [f.message(from_email='billing@spendly.example', from_name='Spendly', source_name='Outlook', subject='Your Spendly receipt',
                             body='Spendly Team plan, 40 seats, $1,600 / month', sent_at=ago(days=9)),
                   f.message(from_email='billing@vendor.example', from_name='Payworth', source_name='Outlook', subject='Payworth Expenses renewal',
                             body='Payworth Expenses, 40 seats, $1,450 / month, renews on the 1st', sent_at=ago(days=6))]
    ids['ask_in'] = f.message(from_email=GAIL, from_name='Gail Moreno', source_name='Outlook', subject='Q4 accruals', conversation_id='q4',
                              body='Can we close Q4 accruals this week?', sent_at=ago(days=8))
    ids['ask'] = f.message(direction='out', status='context', source_name='Outlook', subject='Re: Q4 accruals', conversation_id='q4',
                           body='Gail, can you send me the accrual list by Friday?', RecipientsJson=json.dumps({'to': [GAIL]}), sent_at=ago(days=6))
    s.put_sent_verdict(ids['ask'], 'q4', True, False, 'the accrual list', None, 'test')
    ids['fail'] = [f.message(from_email='jobs@northwind.example', from_name='Ledger jobs', source_name='Ledger monitor', channel='report',
                             subject='Nightly ledger export failed', body='HTTP 403: the service account password expired', sent_at=ago(days=d, hours=3))
                   for d in (4, 3, 2, 1)]
    return s, ids


def test_a_quiet_look_asks_nothing_and_says_why_and_a_new_day_or_new_mail_always_runs(monkeypatch):
    s, ids = busy_week()
    noon = datetime.now().replace(hour=12, minute=0, second=0, microsecond=0)
    monkeypatch.setattr(lookout, '_now', lambda: noon)
    at = lambda **k: (noon - timedelta(**k)).strftime('%Y-%m-%d %H:%M:%S')
    s.set_setting(lookout.LAST_KEY, at(hours=4), 't'); s.set_setting(lookout.TRIED_KEY, at(hours=4), 't')
    s.set_setting(lookout.STAMP_KEY, str(lookout.stamp(s)), 't')
    assert lookout.why_not(s, look=True).startswith('the last pass started at 08:00'), 'a pass four hours ago'
    s.set_setting(lookout.TRIED_KEY, at(hours=7), 't'); s.set_setting(lookout.LAST_KEY, at(hours=7), 't')
    never = brain()                                                          # any call would fail: nothing may be asked
    out = lookout.tick(s, never, wait=True)
    assert out['ran'] is False and out['skipped'] == 'ran at ' + at(hours=7)[:16] + ' and nothing new has arrived since' and not never.seen
    assert json.loads(s.get_setting(lookout.SKIP_KEY))['why'] == out['skipped'], 'the skip is kept with its reason'
    Factory(s).message(from_email=GAIL, from_name='Gail Moreno', subject='Re: Q4 accruals', body='Attached', sent_at=at(hours=1))
    assert lookout.due(s, look=True) is True and lookout.due(s) is False, 'new mail: the next look runs it; the clock waits for tomorrow'
    # ...and a day later with nothing moved at all it runs anyway: unchanged facts never block a new day
    s.set_setting(lookout.STAMP_KEY, str(lookout.stamp(s)), 't')
    s.set_setting(lookout.LAST_KEY, at(days=1, hours=1), 't'); s.set_setting(lookout.TRIED_KEY, at(days=1, hours=1), 't')
    assert lookout.due(s) is True and lookout.due(s, look=True) is True
    # a quiet day: the model finds nothing that clears the bar - nothing is raised and the check is not paid for
    out = lookout.tick(s, brain({'ideas': []}))
    assert out['ran'] and out['raised'] == [] and out['calls'] == 1


def test_a_week_with_a_duplicate_subscription_an_unanswered_ask_and_a_recurring_failure_raises_three_kinds_with_their_evidence():
    s, ids = busy_week()
    user, shown, deep = lookout.window(s)
    # the context: what is owed (his ask Gail never answered), the failure counted, the two tools in their own words
    owed = user[user.index('WHAT IS OWED'):user.index('TASKS:')]
    assert '[followup]' in owed and 'Q4 accruals' in owed and f"msg{ids['ask_in']}" in shown
    assert set(deep) == {'source:Outlook', 'source:Ledger monitor'}, deep
    assert '"Nightly ledger export failed": 4 message(s)' in user and 'HTTP 403: the service account password expired' in user
    assert 'Spendly Team plan, 40 seats, $1,600 / month' in user and 'Payworth Expenses, 40 seats' in user
    a, b = ids['subs']
    llm = brain({'ideas': [
        idea('money', 'Spendly and Payworth Expenses both bill 40 seats for expenses - about $1,450 a month paid twice', [f'msg{a}', f'msg{b}'],
             evidence='Spendly receipt: 40 seats $1,600/month; Payworth renewal: 40 seats $1,450/month, renews on the 1st',
             next_step='Draft the cancellation to Payworth before the 1st'),
        idea('reminder', 'Gail never sent the accrual list you asked for six days ago', [f"msg{ids['ask_in']}"],
             evidence='you asked for it by Friday; nothing came back', next_step='Draft a nudge to Gail'),
        idea('pitch', 'The nightly ledger export failed four nights on an expired service-account password', [f"msg{ids['fail'][-1]}"],
             evidence='4 failures in 4 nights, each HTTP 403 password expired', next_step='Move the service account to a managed secret that rotates')]})
    out = lookout.tick(s, llm, force=True)
    rows = [s.get_idea(i) for i in out['raised']]
    assert [r['Kind'] for r in rows] == ['money', 'reminder', 'pitch'], 'three items, three kinds'
    acts = [json.loads(r['ActionJson']) for r in rows]
    assert all(a_['evidence'] and a_['next_step'] for a_ in acts), 'each carries what it rests on and the one step to press'
    assert 'Payworth: Payworth Expenses renewal' in acts[0]['evidence'][1]['label']


def test_five_passes_over_four_systems_give_each_a_deep_look_a_new_angle_each_return_and_no_item_twice():
    s = MemoryStore(); s.set_setting('owner_email', ALEX, 'test')
    f, mids = Factory(s), {}
    for src in ('Payworth', 'Spendly', 'Trainly', 'PhishGuard'):
        mids[src] = [f.message(from_email=f'{src.lower()}@vendor.example', from_name=src, source_name=src, channel='report',
                               subject=f'{src} weekly', body=f'{src} numbers', sent_at=ago(days=d)) for d in (9, 5, 2)]
    deeps, said = [], []
    for run in range(5):
        title = 'Payworth weekly numbers fell three weeks running' if run < 2 else 'Payworth bills for seats nobody used this month'
        # ...it reads the message first: on a pass where Payworth is not the deep look, the window does not show it, and an id it never
        # read is no evidence
        ref = f"msg{mids['Payworth'][0]}"
        llm = brain({'reads': [rd('read_message', id=ref)]}, {'ideas': [idea('early_warning' if run < 2 else 'money', title, [ref])]})
        out = lookout.tick(s, llm, force=True)
        deeps.append(out['deep']); said += out['raised']
        if run == 1: assert '- [early_warning] Payworth weekly numbers fell three weeks running - the owner:' in llm.seen[0][1], 'what it said is in its context'
    assert {a for d in deeps for a in d} == {f'source:{x}' for x in mids}, f'every system had a deep look: {deeps}'
    assert deeps[:2] == [['source:Payworth', 'source:PhishGuard'], ['source:Spendly', 'source:Trainly']], 'the longest unlooked first, two a pass'
    n = sum('source:Payworth' in d for d in deeps)
    assert n >= 2 and list(lookout.coverage(s)['source:Payworth']['lens']) == list(lookout.LENSES)[:n], \
        'each return to an area takes the angle not taken there longest'
    assert [s.get_idea(i)['Text'] for i in said] == ['Payworth weekly numbers fell three weeks running', 'Payworth bills for seats nobody used this month'], \
        'the same item is never raised twice; a new angle on the same system is'


# ── LEADS FROM TASK AGENTS, THE RUN LINE, AND SAYING ONCE THAT THERE WAS NOTHING (the design review, 2026-11-23) ─────────────────────
def test_a_lead_a_task_agent_noted_reaches_the_next_run_as_a_pointer_it_must_read_before_it_cites():
    s, ids = world()
    a, b = ids['dup']
    t = Factory(s).task(title='Pay the Vendor billing invoice')
    assert lookout.note_lead(s, t, 'Vendor billing seems to send each invoice twice', [f'msg{b}']) == {'kept': True}
    assert lookout.note_lead(s, t, 'vendor billing seems to send each invoice  twice')['already'] is True, 'once'
    with pytest.raises(ValueError): lookout.note_lead(s, t, 'odd')
    user, seen, _ = lookout.window(s)
    assert f'- from task {t} (' in user and 'Vendor billing seems to send each invoice twice (points at message ' in user
    llm = brain({'reads': [rd('read_message', id=f'msg{b}')]}, {'ideas': [idea('money', 'Invoice 4471 came twice from Vendor billing', [f'msg{b}'])]})
    out = lookout.tick(s, llm, force=True)
    assert len(out['raised']) == 1 and lookout.leads(s) == [], 'read on this run: not shown again'
    assert 'LEADS FROM' not in lookout.window(s)[0]


def test_every_run_leaves_a_line_and_three_with_nothing_say_so_once_on_the_rail():
    from taskuary import funnel
    s, ids = world()
    a, _b = ids['dup']
    for n in range(4): lookout.tick(s, brain({'ideas': [idea('money', 'You paid 99 dollars for nothing', [f'msg{a}'])]}), force=True)
    rs = lookout.runs(s)
    assert len(rs) == 4 and "raised nothing; held 'You paid 99 dollars for nothing': the number 99 is not in what it cites" in lookout.run_line(rs[0])
    assert 'looked closely at source:email (' in lookout.run_line(rs[0])
    quiet = s._rows("SELECT * FROM idea WHERE Kind='lookout_quiet'")
    assert len(quiet) == 1 and quiet[0]['Text'].startswith('My last 3 looks for ideas about your job found nothing worth your time'), 'said once, not on the fourth'
    assert 'the number 99 is not in what it cites' in json.loads(quiet[0]['ActionJson'])['why'], 'it opens on the looks behind it'
    funnel.invalidate()
    assert any(x.get('idea') == quiet[0]['IdeaId'] for x in funnel.pile(s, force=True, quiet=True)['items']), 'on the rail'
    assert lookout.tick(s, brain({'ideas': [idea('money', 'Invoice 4471 billed twice', [f'msg{a}'])]}), force=True)['raised']
    assert not s.get_setting(lookout.QUIET_KEY), 'something raised: the next quiet spell may be said again'
    # ...and the run lines open from the app, newest first
    from fastapi.testclient import TestClient
    from taskuary import server
    with pytest.MonkeyPatch.context() as m:
        m.setattr(server, 'store', s)
        got = TestClient(server.app).get('/api/advisor/lookout').json()
    assert len(got['runs']) == 5 and 'raised 1' in got['runs'][0] and 'the number 99 is not in what it cites' in got['runs'][1]


def test_a_task_agent_has_a_note_lead_tool_whose_door_is_its_own_and_it_reaches_the_advisor():
    from taskuary import agenttools, guard
    assert 'note_lead' in {t['name'] for t in agenttools.listing()} and agenttools.TOOLS['note_lead'][0] == 'own'
    assert guard.classify(*agenttools.TOOLS['note_lead'][3])[0] == 'agent', 'an agent may call it'
    s, ids = world()
    t = Factory(s).task(title='Pay the Vendor billing invoice')
    doors = {'note_lead': lambda tid, text, refs: lookout.note_lead(s, tid, text, refs)}
    agenttools.call(s, t, 'note_lead', {'text': 'Vendor billing sent invoice 4471 twice this month', 'refs': [f"msg{ids['dup'][0]}"]}, doors)
    assert [l['text'] for l in lookout.leads(s)] == ['Vendor billing sent invoice 4471 twice this month']
