"""ONE CARD FOR A BULK JOB (the owner, 2026-11-16: "For a job that is a bulk process you should be able to review a few of them and then send them
all out. E.g. the goal is to go through all issues on a GitHub repo and close all that don't matter ... On the bulk version, the send should
show a progress bar in the action card since it can take a long time."). The agent raises many of one act in one call (`items`); they stand
as ONE card in the line of cards; one press does them all, each by its own road, in the background; the agent hears the run once.
Invented people and a stand-in GitHub only."""
import json, threading, time
from types import SimpleNamespace
from unittest import mock

from fastapi.testclient import TestClient

from taskuary import bulkcard, cardqueue, conversation, general, github, outbound, proposals, server, taskstate
from taskuary.store import MemoryStore
from test_agent_toolbox import hdr
from test_own_ask_no_reply import own_task

c = TestClient(server.app)
REPO = 'northwind/ledger'


def call(tid, name, **a):
    r = c.post(f'/api/mcp?task={tid}', headers=hdr(tid), json={'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call',
                                                               'params': {'name': name, 'arguments': a}}).json()['result']
    assert not r['isError'], r
    return json.loads(r['content'][0]['text'])


def world():
    s = MemoryStore(); tid = own_task(s, 'general')
    s.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, 'Set up.'); s._exec("UPDATE comment SET CreatedAt='2000-01-01 00:00:00'")
    gh = s.get_connector_by_type('github')
    s.save_connector({'ConnectorId': gh['ConnectorId'], 'Secret': 'ghp_stand_in', 'Active': 1}, 'test')
    return s, tid


def emails(n): return [{'to': f'owner{i}@cedar.example', 'subject': f'Interest in buying {100 + i} Market St', 'text': f'Hello - about {100 + i} Market St. Alex'}
                       for i in range(n)]


def press(s, key, skip=(), told=None):
    told = [] if told is None else told
    with mock.patch.object(general, 'tell', lambda st, t, said, actor='owner': told.append(said) or 'woke'):
        return bulkcard.run(s, key, skip, wait=True), told


class GitHub:
    "A stand-in GitHub: closes what it is asked to, refuses the numbers in `bad`, and can be slow."
    def __init__(self, bad=(), delay=0.): self.closed, self.bad, self.delay = [], set(bad), delay
    def patch(self, url, **kw):
        time.sleep(self.delay); n = int(url.rsplit('/', 1)[1])
        if n in self.bad: return SimpleNamespace(status_code=410, text='issue was deleted', ok=False, json=lambda: {'message': 'issue was deleted'})
        self.closed.append(n); return SimpleNamespace(status_code=200, text='{}', ok=True, json=lambda: {'number': n, 'state': 'closed'})


def test_twenty_five_emails_are_one_card_and_one_press_sends_them_all():
    s, tid = world()
    with mock.patch.object(server, 'store', s):
        out = call(tid, 'propose_email', items=emails(25))
    assert out['ok'] and out['on_the_card'] == 25 and 'ONE card' in out['shown']
    q = cardqueue.state(s, tid)
    assert len(q['units']) == 1 and len(q['live']) == 25, 'one card in the line, whatever its size'
    with mock.patch.object(server, 'store', s): items = conversation.items(s, tid)['items']
    cards = [k for x in items for k in ([x] if x['kind'] == 'card' else x.get('cards') or [])]
    assert [(k['what'], k['n']) for k in cards] == [('batch', 25)], 'drawn as one card, never 25'
    sent = []
    with mock.patch.object(outbound, 'send_out', lambda *a, **k: sent.append(k.get('to')) or {'channel': 'email', 'to': k.get('to') or []}), \
         mock.patch.object(outbound, 'send_block', lambda *a, **k: ''):
        st, told = press(s, out['batch'], skip=[q['live'][3]])
    assert (st['state'], st['done'], st['failed'], st['left']) == ('finished', 24, 0, 1), st
    assert len(sent) == 24
    [said] = told
    assert '24 done, 0 failed, 1 left out by them' in said, 'its agent hears the whole run once'
    assert s.get_review(q['live'][3])['DecideNote'] == bulkcard.LEFT


def test_forty_issues_closed_with_some_refused_counts_each_and_says_why():
    s, tid = world()
    with mock.patch.object(server, 'store', s):
        out = call(tid, 'propose', action='run_tool', type='github_close', repo=REPO, reason='not_planned', why='stale - no activity in two years',
                   items=[{'number': n} for n in range(1, 41)])
    assert out['on_the_card'] == 40, out
    gh = GitHub(bad={7, 19})
    with mock.patch.object(github.requests, 'patch', gh.patch):
        st, told = press(s, out['batch'])
    assert (st['done'], st['failed'], st['left']) == (38, 2, 0) and len(gh.closed) == 38
    bad = {k: v for k, v in st['rows'].items() if v != 'ok'}
    assert len(bad) == 2 and all('deleted' in v or 'did not' in v or 'close #' in v for v in bad.values()), bad
    [said] = told
    assert '38 done, 2 failed' in said and 'Failed:' in said


def test_cancel_stops_the_rest_and_what_was_not_run_still_waits_on_the_card():
    s, tid = world()
    with mock.patch.object(server, 'store', s):
        out = call(tid, 'propose', action='run_tool', type='github_close', repo=REPO, why='duplicates', items=[{'number': n} for n in range(1, 41)])
    gh, told = GitHub(delay=0.05), []
    with mock.patch.object(github.requests, 'patch', gh.patch), mock.patch.object(general, 'tell', lambda st, t, said, actor='owner': told.append(said) or 'woke'):
        bulkcard.run(s, out['batch'])
        end = time.time() + 20
        while bulkcard.state(s, out['batch'])['done'] < 5 and time.time() < end: time.sleep(0.01)
        bulkcard.cancel(s, out['batch'])
        while bulkcard.state(s, out['batch'])['state'] != 'stopped' and time.time() < end: time.sleep(0.02)
    st = bulkcard.state(s, out['batch'])
    assert st['state'] == 'stopped' and 5 <= st['done'] < 40
    waiting = [r for r in bulkcard.rows(s, out['batch']) if r['Status'] == 'pending']
    assert len(waiting) == 40 - st['done'] - st['failed'], 'the rest still waits, on the same card'
    [said] = told
    assert 'not run - they stopped it' in said


def test_a_line_he_types_while_it_runs_never_stops_the_run():
    s, tid = world()
    with mock.patch.object(server, 'store', s):
        out = call(tid, 'propose', action='run_tool', type='github_close', repo=REPO, why='duplicates', items=[{'number': n} for n in range(1, 11)])
    s._exec("UPDATE review SET CreatedAt='2026-11-16 09:00:00' WHERE Batch=?", (out['batch'],))
    st = {**bulkcard.state(s, out['batch']), 'key': out['batch'], 'tid': tid, 'state': 'running'}
    bulkcard._save(s, st)
    general.wait_line(s, tid, 'how many are left?', line_id='l-left')
    assert proposals.written_past(s, tid) == set(), 'a card at work runs on to its end'
    st['state'] = 'finished'; bulkcard._save(s, st)
    assert len(proposals.written_past(s, tid)) == 10, 'one that is not running greys as any card does'


def test_an_agent_reads_a_repositorys_open_issues_as_rows():
    s, tid = world()
    page = [{'number': n, 'title': f'Stale question {n}', 'labels': [{'name': 'question'}], 'comments': 0, 'updated_at': '2022-03-04T10:00:00Z',
             'user': {'login': 'user1'}, 'body': 'How do I export?'} for n in range(1, 4)] + [{'number': 9, 'pull_request': {}, 'title': 'a PR'}]
    with mock.patch.object(github.requests, 'get', lambda *a, **k: SimpleNamespace(status_code=200, ok=True, text='[]', json=lambda: page)):
        got = github.run_github_issues({'repo': REPO, 'token': 'ghp_stand_in'})
    head, body = got
    assert '3 issues' in head and 'Stale question 1' in body and 'a PR' not in body, 'pull requests are no issues'


def test_a_task_whose_card_is_running_reads_at_work_not_waiting_on_him():
    "2026-11-17: mid-run the chip said \"agent waiting on you\" over rows his press was doing - its rows still read pending until each was done."
    s, tid = world()
    with mock.patch.object(server, 'store', s):
        out = call(tid, 'propose', action='run_tool', type='github_close', repo=REPO, why='duplicates', items=[{'number': n} for n in range(1, 11)])
    assert taskstate.state(s, s.get_task(tid)) != 'working', 'before the press the card waits on him'
    st = {**bulkcard.state(s, out['batch']), 'key': out['batch'], 'tid': tid, 'state': 'running'}
    bulkcard._save(s, st)
    assert taskstate.state(s, s.get_task(tid)) == 'working', 'his press is at work'
    st['state'] = 'cancelling'; bulkcard._save(s, st)
    assert taskstate.state(s, s.get_task(tid)) == 'working', 'stopping after the row in hand'
    st['state'] = 'stopped'; bulkcard._save(s, st)
    assert taskstate.state(s, s.get_task(tid)) != 'working', 'what was not run waits on him again'


def test_two_presses_at_once_are_one_run_and_one_true_telling():
    """Pressed on the phone and the desk in the same moment: both presses started a run, each row went once (its own road refuses a second),
    and the agent was told twice - each telling "5 done, 5 failed" over ten issues that had all closed."""
    s, tid = world()
    with mock.patch.object(server, 'store', s):
        out = call(tid, 'propose', action='run_tool', type='github_close', repo=REPO, why='duplicates', items=[{'number': n} for n in range(1, 11)])
    gh, told, go = GitHub(delay=0.02), [], threading.Barrier(2)
    with mock.patch.object(github.requests, 'patch', gh.patch), mock.patch.object(general, 'tell', lambda st, t, said, actor='owner': told.append(said) or 'woke'):
        def press_it():
            go.wait()
            try: bulkcard.run(s, out['batch'], wait=True)
            except ValueError: pass                                   # the second found nothing waiting: said so, nothing run
        ts = [threading.Thread(target=press_it) for _ in range(2)]
        [t.start() for t in ts]; [t.join() for t in ts]
    st = bulkcard.state(s, out['batch'])
    assert sorted(gh.closed) == list(range(1, 11)) and (st['done'], st['failed']) == (10, 0), st
    [said] = told
    assert '10 done, 0 failed' in said
