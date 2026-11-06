"""THE WORKSTREAMS READ FROM THE MAIL (the design's S6; the owner, 2026-11-01: six months, a one-screen confirm at first setup, then an
Advisor card; a new connector or project's other hat noticed - added when sure). Alex Doyle's world, invented (CLAUDE.md): the day job
at Northwind with Erin and Paula, the Ledger app with Omar and Marcus in a chat group and its repository, and Mom."""
import json
from datetime import datetime, timedelta
import pytest
from taskuary import assistant, firstrun, workstreams as W, wsboot
from taskuary.store import MemoryStore
from taskuary.testing import Factory

ERIN, PAULA, OMAR, MARCUS, MOM = ('erin@northwind.example', 'paula@northwind.example', 'omar@ledger.example', 'marcus@ledger.example',
                                  'mom@family.example')
def ago(**k): return (datetime.now() - timedelta(**k)).strftime('%Y-%m-%d %H:%M:%S')


def world():
    s = MemoryStore()
    s.set_setting('owner_email', 'alex@northwind.example', 'test')
    f = Factory(s)
    def thread(cid, who, mine, channel='email', source=None, n=3, words='About the work'):
        for i in range(n):
            conv = f'{cid}{i}' if channel == 'email' else f'{channel}:{cid}'        # a chat is one conversation; mail is a thread each
            f.message(channel=channel, source_name=source, from_email=who[i % len(who)], conversation_id=conv, subject=f'{cid} {i}', sent_at=ago(days=10 + i))
            if mine: f.message(channel=channel, source_name=source, direction='out', status='context', conversation_id=conv,
                               RecipientsJson=json.dumps([{'email': w} for w in who]), body=f'{words} {i}', sent_at=ago(days=10 + i, hours=-1))
    thread('budget', [ERIN, PAULA], True, words='The Q4 budget file goes to Paula Friday')
    # ...both chats come by the same WhatsApp connection: its name is no signal of which hat
    thread('ledger', [OMAR, MARCUS], True, channel='whatsapp', source='My phone', words='Fixed the export, pushing tonight')
    thread('home', [MOM], True, channel='whatsapp', source='My phone', words='I will pick up the car at 5')
    for i in range(4): f.message(channel='email', from_email='news@bulk.example', conversation_id=f'news{i}', SenderClass='bulk', sent_at=ago(days=i + 1))
    return s


def namer(sure=True, personal_name='Personal'):
    """A scripted model: names each group by who is in it, the way the real one is asked to."""
    def llm(system, user, **kw):
        groups = [b.split(' - ')[0].split()[0] for b in user.split('GROUP ')[1:]]
        bodies = {g: b for g, b in zip(groups, user.split('GROUP ')[1:])}
        ws = []
        for g, b in bodies.items():
            if 'northwind' in b: ws.append({'groups': [g], 'name': 'Northwind finance systems', 'about': 'IT for finance at Northwind', 'personal': False,
                                            'sure': sure, 'section': '- I run finance systems; Erin Blake is my manager\n- Q4 budget due 2026-11-15'})
            elif 'ledger' in b: ws.append({'groups': [g], 'name': 'Ledger app', 'about': 'a product I build with Omar and Marcus', 'personal': False,
                                           'sure': sure, 'section': "- Omar Keller tests it; his bug reports become coding tasks"})
            elif 'family' in b: ws.append({'groups': [g], 'name': personal_name, 'about': 'home', 'personal': True, 'sure': sure, 'section': 'never'})
        return json.dumps({'workstreams': ws})
    return llm


def test_six_months_of_threads_cluster_into_the_owners_hats_and_machines_are_never_people():
    s = world()
    ts = wsboot.gather(s)
    assert all('news@bulk.example' not in t['people'] for t in ts)
    gs = wsboot.groups(ts)
    sets = sorted(sorted(g['people'] + g['sources']) for g in gs)
    assert sets == [[ERIN, PAULA], [MARCUS, OMAR, 'whatsapp:ledger'], [MOM, 'whatsapp:home']]
    assert next(g for g in gs if ERIN in g['people'])['domains'] == ['northwind.example']
    assert any('Q4 budget file' in l for g in gs for l in g['lines'])


def test_the_model_names_them_as_proposals_and_nothing_places_an_item_until_confirmed():
    s = world()
    got = wsboot.propose(s, namer())
    assert sorted(w['slug'] for w in got) == ['ledger-app', 'northwind-finance-systems', 'personal']
    assert W.streams(s) == [] and len(wsboot.proposals(s)) == 3
    active = wsboot.confirm(s, [{'slug': 'northwind-finance-systems', 'name': 'Northwind', 'keep': True}, {'slug': 'ledger-app', 'keep': True},
                                {'slug': 'personal', 'keep': True}])
    assert sorted(w['name'] for w in active) == ['Ledger app', 'Northwind', 'Personal'] and W.personal(s) == {'personal'}
    assert 'Q4 budget due 2026-11-15' in W.section(s, 'northwind-finance-systems') and W.section(s, 'personal') == ''
    assert W.by_signals(W.streams(s), {'Channel': 'whatsapp', 'SourceName': 'My phone', 'ConversationId': 'whatsapp:ledger'}) == ('ledger-app', 'chat')
    # ...left out on the screen, one is gone
    s2 = world(); wsboot.propose(s2, namer())
    wsboot.confirm(s2, [{'slug': 'ledger-app', 'keep': False}])
    assert W.get(s2, 'ledger-app') is None


def test_the_setup_screen_is_a_draft_the_owner_answers(monkeypatch):
    s = world()
    monkeypatch.setattr('taskuary.llm.build_llm', lambda *a, **k: namer())
    firstrun.learn(s, {}, wait=True, docs=('workstreams',))
    d = firstrun.drafts(s)['workstreams']
    rows = json.loads(d['text'])
    assert d['state'] == 'ready' and {r['slug'] for r in rows} == {'northwind-finance-systems', 'ledger-app', 'personal'}
    firstrun.accept(s, 'workstreams', json.dumps([{**r, 'keep': r['slug'] != 'personal'} for r in rows]))
    assert sorted(w['slug'] for w in W.streams(s)) == ['ledger-app', 'northwind-finance-systems']


def _settled(s, timeout=10):
    import time
    for _ in range(int(timeout / 0.02)):
        if firstrun.drafts(s)['workstreams']['state'] != 'running': return
        time.sleep(0.02)
    raise AssertionError('the grouping never settled')


def test_one_next_with_the_grouping_done_keeps_the_list_as_left_and_the_job(monkeypatch):
    """ABOUT YOUR WORK IS ONE STEP (the owner, 2026-11-06): the job and the workstreams under it, one Next for both."""
    s = world()
    monkeypatch.setattr('taskuary.llm.build_llm', lambda *a, **k: namer())
    firstrun.learn(s, {}, wait=True, docs=('workstreams',))
    rows = json.loads(firstrun.drafts(s)['workstreams']['text'])
    firstrun.accept(s, 'workstreams', json.dumps([{**r, 'name': 'Ledger migration'} if r['slug'] == 'ledger-app' else r for r in rows]))
    got = {w['slug']: w for w in W.streams(s)}
    assert set(got) == {'northwind-finance-systems', 'ledger-app', 'personal'} and got['ledger-app']['name'] == 'Ledger migration'
    assert got['personal']['personal'] and not firstrun._drafts(s)['workstreams'].get('keep')
    # ...the answers came back on the step when setup is opened again: not grouped from the mail a second time
    assert json.loads(firstrun.about(s)['workstreams'])[0]['kept'] is True


def test_one_next_while_the_grouping_runs_keeps_the_defaults_once_it_lands(monkeypatch):
    """Next never waits on the grouping: pressed while it runs, every workstream is kept once it lands - all ticked, none personal."""
    import threading
    s, go = world(), threading.Event()
    def slow(system, user, **k): go.wait(10); return namer()(system, user, **k)
    monkeypatch.setattr('taskuary.llm.build_llm', lambda *a, **k: slow)
    firstrun.learn(s, {}, docs=('workstreams',))
    assert firstrun.drafts(s)['workstreams']['state'] == 'running'
    assert firstrun.accept(s, 'workstreams', '')['state'] == 'running'        # the screen's Next, with nothing to answer yet
    assert W.streams(s) == []
    go.set(); _settled(s)
    got = {w['slug']: w for w in W.streams(s)}
    assert set(got) == {'northwind-finance-systems', 'ledger-app', 'personal'} and not any(w['personal'] for w in got.values())
    assert 'Q4 budget due 2026-11-15' in W.section(s, 'northwind-finance-systems')
    assert wsboot.proposals(s) == [] and firstrun.drafts(s)['workstreams']['state'] == 'ready'
    # ...and nothing running, an empty answer keeps nothing
    s2 = world(); monkeypatch.setattr('taskuary.llm.build_llm', lambda *a, **k: namer())
    firstrun.learn(s2, {}, wait=True, docs=('workstreams',)); firstrun.accept(s2, 'workstreams', '')
    assert W.streams(s2) == [] and len(wsboot.proposals(s2)) == 3


def test_a_grouping_that_fails_after_next_keeps_nothing_and_says_why(monkeypatch):
    import threading
    s, go = world(), threading.Event()
    def broken(system, user, **k): go.wait(10); raise RuntimeError('the AI is down')
    monkeypatch.setattr('taskuary.llm.build_llm', lambda *a, **k: broken)
    firstrun.learn(s, {}, docs=('workstreams',)); firstrun.accept(s, 'workstreams', '')
    go.set(); _settled(s)
    d = firstrun._drafts(s)['workstreams']
    assert d['state'] == 'failed' and not d['keep'] and W.streams(s) == []


def test_about_you_changes_what_you_work_on_later_and_a_left_out_one_comes_back(monkeypatch):
    """The same list on About you: renamed, Personal, left out - unticked there it is put back among the unanswered, never deleted."""
    s = world()
    monkeypatch.setattr('taskuary.llm.build_llm', lambda *a, **k: namer())
    firstrun.learn(s, {}, wait=True, docs=('workstreams',))
    firstrun.accept(s, 'workstreams', json.dumps([{'slug': 'northwind-finance-systems'}, {'slug': 'ledger-app'}]))
    page = json.loads(firstrun.workstreams_page(s)['text'])
    assert {(r['slug'], r['kept']) for r in page} == {('northwind-finance-systems', True), ('ledger-app', True), ('personal', False)}
    assert page[-1]['slug'] == 'personal'                                            # the kept ones first
    nw = next(r for r in page if r['slug'] == 'northwind-finance-systems')
    assert nw['section'].startswith('- I run finance systems') and '###' not in nw['section']   # the name is the row's box, not a heading again
    assert next(r for r in page if r['slug'] == 'personal')['keep'] is False         # unanswered: unticked here, never kept by a save
    # the owner's own words in the section survive a rename from About you
    s.save_doc('job', s.get_doc('job').replace('Q4 budget due 2026-11-15', 'Q4 budget moved to 2026-12-01'), 'owner')
    firstrun.answer_workstreams(s, [{'slug': 'northwind-finance-systems', 'name': 'Northwind finance', 'keep': True}])
    assert W.get(s, 'northwind-finance-systems')['name'] == 'Northwind finance' and 'moved to 2026-12-01' in W.section(s, 'northwind-finance-systems')
    firstrun.answer_workstreams(s, [{'slug': 'ledger-app', 'keep': False}])
    assert [w['slug'] for w in W.streams(s)] == ['northwind-finance-systems'] and W.get(s, 'ledger-app')['status'] == 'proposed'
    firstrun.answer_workstreams(s, [{'slug': 'ledger-app', 'keep': True}, {'slug': 'personal', 'keep': True, 'personal': True}])
    assert {w['slug'] for w in W.streams(s)} == {'northwind-finance-systems', 'ledger-app', 'personal'} and W.personal(s) == {'personal'}


def test_a_new_sources_hat_is_added_when_sure_and_asked_on_a_card_when_not():
    s = world()
    wsboot.propose(s, namer()); wsboot.confirm(s, [{'slug': 'northwind-finance-systems'}, {'slug': 'personal', 'keep': False}])
    # the Ledger crew's chat came in after setup: no workstream places it
    s.set_setting(W.KEY, json.dumps([w for w in W.streams(s, True) if w['slug'] != 'ledger-app']), 'test')
    assert ('whatsapp', 'My phone') in wsboot.new_sources(s)
    done = dict(wsboot.judge_sources(s, namer(sure=False)))
    assert done.get('ledger-app') == 'proposed'
    i = s._one("SELECT * FROM idea WHERE Key='idea:workstream-ledger-app'")
    assert i and i['Kind'] == 'workstream' and i['Text'].startswith('Is Ledger app a separate workstream')
    assert ('whatsapp', 'My phone') not in wsboot.new_sources(s)   # judged once
    assistant.act(s, i['IdeaId'], 'accept')
    assert W.get(s, 'ledger-app')['status'] == 'active' and 'bug reports become coding tasks' in W.section(s, 'ledger-app')


def test_no_on_a_card_takes_it_out_and_it_never_asks_again():
    s = world()
    wsboot.propose(s, namer(sure=False))
    i = wsboot.card(s, 'ledger-app')
    assistant.act(s, i['IdeaId'], 'dismiss')
    assert W.get(s, 'ledger-app') is None
    W.upsert(s, {'name': 'Ledger app', 'status': 'proposed'})
    assert wsboot.card(s, 'ledger-app') is None


def test_the_weekly_refresh_rewrites_a_section_and_a_quiet_workstream_is_put_by():
    s = world()
    wsboot.propose(s, namer()); wsboot.confirm(s, [{'slug': 'northwind-finance-systems'}, {'slug': 'ledger-app'}])
    for m in s._rows('SELECT MessageId FROM message'): W.stamp_message(s, m['MessageId'])
    s._exec("UPDATE message SET SentAt=? WHERE Workstream='ledger-app'", (ago(days=90),))
    out = wsboot.refresh(s, lambda system, user, **k: '- I run finance systems; Paula Vance is the CFO\n- Q1 plan due 2027-01-31')
    assert out == {'northwind-finance-systems': 'refreshed', 'ledger-app': 'quiet'}
    assert 'Q1 plan due 2027-01-31' in W.section(s, 'northwind-finance-systems') and W.get(s, 'ledger-app')['status'] == 'quiet'
    assert sorted(w['slug'] for w in W.streams(s)) == ['ledger-app', 'northwind-finance-systems']     # quiet stays listed, its index says so
    assert '(quiet)' in s.get_doc('job')
