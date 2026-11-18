"""ONE CARD FOR A BULK JOB (the owner, 2026-11-16: "For a job that is a bulk process you should be able to review a few of them and then send them
all out. E.g. the goal is to go through all issues on a GitHub repo and close all that don't matter ... On the bulk version, the send should
show a progress bar in the action card since it can take a long time."). The agent raises many of one act in one call (`items`); they stand
as ONE card in the line of cards; one press does them all, each by its own road, in the background; the agent hears the run once.
Invented people and a stand-in GitHub only."""
import json, threading, time
from types import SimpleNamespace
from unittest import mock

from fastapi.testclient import TestClient

from taskuary import bulkcard, cardqueue, conversation, general, github, outbound, proposals, server, taskstate, verdicts
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
    with mock.patch.object(general, 'tell', lambda st, t, said, actor='owner', heard=None: told.append(said) or (heard and heard('woke')) or 'woke'):
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
    with mock.patch.object(github.requests, 'patch', gh.patch), mock.patch.object(general, 'tell', lambda st, t, said, actor='owner', heard=None: told.append(said) or (heard and heard('woke')) or 'woke'):
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
    st = {**bulkcard.state(s, out['batch']), 'key': out['batch'], 'tid': tid, 'state': 'running', 'boot': bulkcard.BOOT}
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
    st = {**bulkcard.state(s, out['batch']), 'key': out['batch'], 'tid': tid, 'state': 'running', 'boot': bulkcard.BOOT}
    bulkcard._save(s, st)
    assert taskstate.state(s, s.get_task(tid)) == 'working', 'his press is at work'
    st['state'] = 'cancelling'; bulkcard._save(s, st)
    assert taskstate.state(s, s.get_task(tid)) == 'working', 'stopping after the row in hand'
    st['state'] = 'stopped'; bulkcard._save(s, st)
    assert taskstate.state(s, s.get_task(tid)) != 'working', 'what was not run waits on him again'


def test_sends_that_did_not_go_still_wait_on_the_card_and_its_agent_never_sets_them_up_again():
    """A run of 20 emails where the mailbox refused every fifth: those rows did not go and still wait for a Send, as a single card's failed
    send does (general.NOT_GONE) - its agent was told to "set up again only what failed", the road to every one of them twice; and a
    stop after the failures counted them as "not run"."""
    s, tid = world()
    with mock.patch.object(server, 'store', s):
        out = call(tid, 'propose_email', items=emails(20))
    n = [0]
    def send(*a, **k):
        n[0] += 1
        if n[0] % 5 == 0: raise RuntimeError('mailbox refused: over quota')
        return {'channel': 'email', 'to': k.get('to') or []}
    with mock.patch.object(outbound, 'send_out', send), mock.patch.object(outbound, 'send_block', lambda *a, **k: ''):
        st, told = press(s, out['batch'])
    assert (st['done'], st['failed']) == (16, 4)
    waiting = [r for r in bulkcard.rows(s, out['batch']) if r['Status'] == 'pending']
    assert len(waiting) == 4, 'a send that did not go still waits on its card'
    [said] = told
    assert 'set up again only what failed' not in said
    assert 'Did not go and still on the card for their press: 4' in said and 'never set them up again' in said, said
    assert 'stands in front of the owner' not in said or '(4 emails)' in said
    rest = cardqueue.state(s, tid)['units'][0]
    assert cardqueue.what(s, rest) == '4 emails', 'what still waits on it, not what it once held'
    assert cardqueue.says(s, tid, pressed=True).count('rv') == 4, cardqueue.says(s, tid, pressed=True)
    stopped = {**st, 'state': 'stopped'}
    assert 'not run' not in bulkcard.summary(s, out['batch'], stopped), 'a row that ran and failed is no row that was not run'


def test_a_press_on_a_bulk_card_the_chat_moved_past_sends_nothing():
    """He typed "hold off" under 5 emails, the card greyed on every surface - and a press on it from a page not yet redrawn sent all 5: the
    run marked itself at work before its first row, and a bulk card at work is never written past, so no row's own refusal stood."""
    s, tid = world()
    with mock.patch.object(server, 'store', s):
        out = call(tid, 'propose_email', items=emails(5))
    s._exec("UPDATE review SET CreatedAt='2026-11-16 09:00:00', DraftAt='2026-11-16 09:00:00' WHERE Batch=?", (out['batch'],))
    general.wait_line(s, tid, 'hold off - I want to change the wording', line_id='l-hold')
    assert len(proposals.written_past(s, tid)) == 5
    sent = []
    with mock.patch.object(server, 'store', s), mock.patch.object(outbound, 'send_out', lambda *a, **k: sent.append(1) or {'channel': 'email'}), \
         mock.patch.object(outbound, 'send_block', lambda *a, **k: ''), mock.patch.object(general, 'tell', lambda *a, **k: 'woke'):
        r = c.post(f"/api/reviews/batch/{out['batch']}/run", json={'skip': []})
        time.sleep(0.5)
    assert r.status_code == 409 and 'hold off' in r.json()['detail'], r.json()
    assert sent == [] and bulkcard.state(s, out['batch'])['state'] == 'idle'
    assert len(proposals.written_past(s, tid)) == 5, 'it stays greyed where it stood'


def test_two_presses_at_once_are_one_run_and_its_agent_hears_it_once():
    """A double click, or the phone and the desk together: both presses found the card not yet at work and each started a run - each found the
    other's row in hand ("already in progress"), counted it failed, and its agent heard the run twice, half of it failed each time."""
    s, tid = world()
    with mock.patch.object(server, 'store', s):
        out = call(tid, 'propose_email', items=emails(6))
    sent, told, slow = [], [], bulkcard.running
    def send(*a, **k): time.sleep(0.02); sent.append(k.get('to')); return {'channel': 'email', 'to': k.get('to') or []}
    with mock.patch.object(outbound, 'send_out', send), mock.patch.object(outbound, 'send_block', lambda *a, **k: ''), \
         mock.patch.object(general, 'tell', lambda st, t, said, actor='owner': told.append(said) or 'woke'), \
         mock.patch.object(bulkcard, 'running', lambda *a: (slow(*a), time.sleep(0.05))[0]):      # ...both presses read it before either marks it
        presses = [threading.Thread(target=bulkcard.run, args=(s, out['batch'])) for _ in range(2)]
        for t in presses: t.start()
        for t in presses: t.join()
        end = time.time() + 10
        while not told and time.time() < end: time.sleep(0.02)
        time.sleep(0.3)
    st = bulkcard.state(s, out['batch'])
    assert (st['done'], st['failed']) == (6, 0) and len(sent) == 6, st
    assert len(told) == 1 and '6 done, 0 failed' in told[0], told


def test_a_run_cut_short_by_a_restart_reads_stopped_with_the_rest_waiting_for_his_press():
    """Taskuary restarted with a run under way: its state still read "running", its thread gone with the old process - Stop the rest lit for
    good, the task "at work" with nothing at work, and a press answered with the dead run. Cut short, it reads stopped (the owner's ruling: a
    turn cut short by a restart is not resumed by itself), and the rest waits for his press."""
    s, tid = world()
    with mock.patch.object(server, 'store', s):
        out = call(tid, 'propose', action='run_tool', type='github_close', repo=REPO, why='duplicates', items=[{'number': n} for n in range(1, 6)])
    bulkcard._save(s, {'key': out['batch'], 'tid': tid, 'total': 5, 'done': 2, 'failed': 0, 'left': 0, 'state': 'running', 'rows': {}, 'boot': 'a-process-gone'})
    assert not bulkcard.running(s, out['batch']) and bulkcard.state(s, out['batch'])['state'] == 'stopped'
    bulkcard._save(s, {'key': out['batch'], 'tid': tid, 'total': 5, 'done': 2, 'state': 'running', 'rows': {}})
    assert bulkcard.state(s, out['batch'])['state'] == 'stopped', 'one written before runs were marked: another process too'
    assert taskstate.state(s, s.get_task(tid)) != 'working', 'nothing is at work on it'
    gh = GitHub()
    with mock.patch.object(github.requests, 'patch', gh.patch):
        st, told = press(s, out['batch'])
    assert (st['state'], st['done']) == ('finished', 5) and len(gh.closed) == 5 and len(told) == 1


def test_a_card_raised_beside_a_bulk_call_is_never_swept_onto_it():
    """The rows of a bulk call were found as every pending card on the task newer than its start: a reply drafted for a mail that came in while
    the call filed its items (or the agent's own tool call beside it) joined the bulk card, and its one press sent that reply with them."""
    from taskuary import agenttools
    s, tid = world()
    real, other = agenttools._call, []
    def beside(store, t, name, a, doors):
        if not other: other.append(s.add_review({'TaskId': tid, 'Kind': 'slot', 'Status': 'pending', 'DraftText': 'Gail - the rate is 4%.',
                                                 'Reason': 'assistant wrote this email - approve to send',
                                                 'Deliver': json.dumps({'channel': 'email', 'to': ['gail@northwind.example'], 'subject': 'Rate'})}))
        return real(store, t, name, a, doors)
    with mock.patch.object(server, 'store', s), mock.patch.object(agenttools, '_call', beside):
        out = call(tid, 'propose_email', items=emails(5))
    assert out['on_the_card'] == 5, out
    assert s.get_review(other[0])['Batch'] is None, 'the email beside it is its own card'
    assert other[0] not in {r['ReviewId'] for r in bulkcard.rows(s, out['batch'])}


def test_a_bulk_card_next_in_line_is_named_as_the_card_names_itself():
    """The line said "next: 40 like northwind/ledger#1" of the card that heads itself "40 issues" (bulkCard.countOf, from the catalogue's
    press words): one fact, two wordings."""
    s, tid = world()
    with mock.patch.object(server, 'store', s):
        call(tid, 'propose_email', to='erin@northwind.example', subject='Issues', text='Erin - closing the stale issues next.')
        call(tid, 'propose', action='run_tool', type='github_close', repo=REPO, why='stale', items=[{'number': n} for n in range(1, 41)])
        call(tid, 'propose', action='run_tool', type='github_close', repo=REPO, why='stale', items=[{'number': n} for n in range(41, 43)])
    us = cardqueue.state(s, tid)['units']
    assert cardqueue.line(cardqueue.state(s, tid)) == '1 of 3 · next: 40 issues'
    assert [cardqueue.what(s, u) for u in us] == ['the email to erin@northwind.example', '40 issues', '2 issues']


def test_after_a_bulk_run_its_agent_hears_what_still_waits_behind_it():
    """A yes, a failure and a no on one card each tell the agent what waits next in the line (cardqueue.says); the bulk card's run did not, so
    the agent went on from 10 emails sent never told the note to Gail behind them stands once its turn ends - free to raise it again."""
    s, tid = world()
    with mock.patch.object(server, 'store', s):
        out = call(tid, 'propose_email', items=emails(10))
        last = call(tid, 'propose_email', to='gail@northwind.example', subject='Done', text='Gail - the ten went out.')
    with mock.patch.object(outbound, 'send_out', lambda *a, **k: {'channel': 'email', 'to': k.get('to') or []}), mock.patch.object(outbound, 'send_block', lambda *a, **k: ''):
        st, told = press(s, out['batch'])
    [said] = told
    assert '10 done' in said and f"rv{last['review_id']} (the email to gail@northwind.example)" in said, said


def chat_cards(s, tid):
    with mock.patch.object(server, 'store', s): got = conversation.items(s, tid)
    return {k['review']: (k['what'], k['status']) for x in got['items'] for k in ([x] if x['kind'] == 'card' else x.get('cards') or [])}


def test_a_line_typed_over_the_line_of_cards_greys_what_stood_and_never_draws_what_waited_behind_it():
    """He typed under a bulk card with a note to Gail held behind it. The bulk card read "pending" in the chat while every other surface read it
    set aside, and the note he had never seen was drawn greyed - "Not sent - you wrote ... after it" - until the agent heard his line and
    it went again: drawn, then gone. What stood greys where it stood; what waited behind it never stands."""
    s, tid = world()
    with mock.patch.object(server, 'store', s):
        bulk = call(tid, 'propose_email', items=emails(10))
        note = call(tid, 'propose_email', to='gail@northwind.example', subject='Done', text='Gail - the ten went out.')['review_id']
    first = bulkcard.rows(s, bulk['batch'])[0]['ReviewId']
    assert chat_cards(s, tid) == {first: ('batch', 'pending')}, 'the note waits its turn, drawn nowhere'
    time.sleep(1.1)                                                                      # (a stamp is a whole second)
    general.wait_line(s, tid, 'wait - leave out the corner lots', line_id='l-corner')
    assert chat_cards(s, tid) == {first: ('batch', 'passed')}, 'greyed where it stood, and the note never drawn'
    proposals.set_aside_drafts(s, tid, time.time())                                      # ...as its agent hears the line
    assert chat_cards(s, tid) == {first: ('batch', 'passed')}, 'the same once heard: nothing appears, nothing goes'


def test_a_bulk_card_that_waited_behind_another_and_was_written_past_never_stands():
    s, tid = world()
    with mock.patch.object(server, 'store', s):
        note = call(tid, 'propose_email', to='gail@northwind.example', subject='First', text='Gail - the letters go out next.')['review_id']
        call(tid, 'propose_email', items=emails(10))
    assert chat_cards(s, tid) == {}, "the note stands in the page's letters, the bulk card waits its turn"
    time.sleep(1.1)
    general.wait_line(s, tid, 'hold everything', line_id='l-hold-all')
    assert chat_cards(s, tid) == {note: ('slot', 'passed')}
    proposals.set_aside_drafts(s, tid, time.time())
    assert chat_cards(s, tid) == {note: ('slot', 'passed')}


def test_a_bulk_card_that_waited_its_turn_then_stood_and_went_stays_where_it_stood():
    s, tid = world()
    with mock.patch.object(server, 'store', s):
        note = call(tid, 'propose_email', to='gail@northwind.example', subject='First', text='Gail - the letters go out next.')['review_id']
        bulk = call(tid, 'propose_email', items=emails(5))
    first = bulkcard.rows(s, bulk['batch'])[0]['ReviewId']
    send = mock.patch.object(outbound, 'send_out', lambda *a, **k: {'channel': 'email', 'to': k.get('to') or []})
    with send, mock.patch.object(outbound, 'send_block', lambda *a, **k: ''), mock.patch.object(general, 'approved', lambda *a, **k: 'woke'):
        assert verdicts.decide(s, s.get_review(note), 'approve')['ok']
    time.sleep(1.1); s.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, 'Sent to Gail; the letters are next.')
    assert chat_cards(s, tid)[first] == ('batch', 'pending'), 'its turn came'
    with send, mock.patch.object(outbound, 'send_block', lambda *a, **k: ''):
        press(s, bulk['batch'])
    assert chat_cards(s, tid)[first] == ('batch', 'done'), 'pressed, it stays where it stood'


def test_its_agent_takes_back_a_bulk_card_by_the_ids_it_was_told():
    """The agent hears a bulk card as "rv1 + rv2 + ... (5 emails)" and is told to take back one an outcome changed - but `which` took one id:
    that string matched nothing, and the answer listed every unsent row. One call takes the card back by the ids it was given."""
    s, tid = world()
    with mock.patch.object(server, 'store', s):
        bulk = call(tid, 'propose_email', items=emails(5))
        note = call(tid, 'propose_email', to='gail@northwind.example', subject='Done', text='Gail - the five went out.')['review_id']
        named = cardqueue.says(s, tid).split(': ', 1)[1].split(' (')[0]
        out = call(tid, 'withdraw_draft', why='the owner wants to wait for the survey', which=named)
    rids = [r['ReviewId'] for r in bulkcard.rows(s, bulk['batch'])]
    assert out['ok'] and sorted(out['review_ids']) == rids, out
    assert {s.get_review(x)['Status'] for x in rids} == {'closed_unsent'}
    assert cardqueue.state(s, tid)['units'][0]['rids'] == [note], 'the note to Gail is the next card'
