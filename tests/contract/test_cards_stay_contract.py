"""WHAT STANDS IN A CHAT STAYS, AND A CARD THAT WAITS IS THE LAST THING (the owner, 2026-11-26, in his words):

    "Things on chat don't go away."
    "No text after an approval card until the approval card is denied or approved, then agent moves on."
    "Cards never just disappear."
    "A click on a card only wakes an agent if there is an error or if the agent has to do something next."
    "Nothing comes back automatically."

Pinned through the real code, as tests/contract/ pins the basic interactions: a stand-in agent calls Taskuary's own tools over the route
every CLI uses (/api/mcp), the owner presses through the routes his page uses, and what comes of it is read off the store and the chat's own
read (/api/tasks/<id>/conversation - the one list every page draws, in its one order). No browser, no model, no waiting on a clock. The
people and the company are invented (Alex Doyle, northwind.example).

The shapes a card has, decided by HOW THE AGENT CALLED, never by a count or by what the cards are about:
- separate calls are separate cards, one after another - never tabs of one another;
- one call carrying a set of DIFFERENT acts (the same post for LinkedIn, for X, for Bluesky) is one card with a tab each;
- one call carrying ONE act to many (three posts to one network, a letter to three people) is one list card, one press doing them all.
"""
import json, shutil, threading
from datetime import datetime, timedelta
from unittest import mock

import pytest
from fastapi.testclient import TestClient

from taskuary import (browsergate, cardqueue, checkback, config, events, general, guard, linkedin, outputs, proposals, selfclose, server,
                      terminal as term, workerstate as ws)
from taskuary.store import SQLiteStore

c = TestClient(server.app)
SRV = config.load()['server']
OWNER = {'X-Taskuary-Token': 'pytest-owner-token'}
ASK = 'Announce the ledger portal.'
NETS = ('linkedin', 'x', 'bluesky')


class LinkedIn:
    "LinkedIn's HTTP, stood in: every call kept, none leaves the machine. `fail`: it answers 500."
    def __init__(self): self.calls, self.fail = [], False
    def get(self, url, **kw): self.calls.append(('GET', url)); return mock.Mock(ok=True, json=lambda: {'sub': 'ALEX1', 'name': 'Alex Doyle'})
    def put(self, url, **kw): self.calls.append(('PUT', url)); return mock.Mock(ok=True)
    def post(self, url, **kw):
        self.calls.append(('POST', url, kw.get('json')))
        if self.fail: return mock.Mock(ok=False, status_code=500, text='server error', json=lambda: {'message': 'server error'})
        return mock.Mock(ok=True, headers={'x-restli-id': 'urn:li:share:42'}, json=lambda: {})
    @property
    def posted(self): return [x[2]['commentary'] for x in self.calls if x[0] == 'POST']


class World:
    """One owner's Taskuary on a database file of its own: LinkedIn connected, no other network set up, one task its agent works. `agent` is
    the stand-in agent's tool call; `press`, `run` and `types` are the owner; `read` is the chat as every page is served it."""
    def __init__(self, path):
        self.s = SQLiteStore(str(path)); self._on = mock.patch.object(server, 'store', self.s); self._on.start()
        self.s.set_setting('chatlog_backup', 'a new database: nothing from before the log to copy', 'owner')      # ...so its chat is the log's from its first read
        general._WOKEN.clear(); selfclose._MARKS.clear(); browsergate.HANDS.clear()
        self.tid = self.s.create_task({'Title': 'Posts about the ledger portal', 'Kind': 'general', 'Status': 'in_progress', 'OriginBase': 'owner'}, 'owner')
        self.s.add_message({'TaskId': self.tid, 'ExternalId': 'own-1', 'Channel': 'own', 'Subject': 'Posts about the ledger portal', 'FromName': 'You', 'BodyText': ASK, 'Status': 'routed'})
        li = self.s.get_connector_by_type('linkedin')
        self.s.save_connector({'ConnectorId': li['ConnectorId'], 'Active': 1, 'Secret': 'stand-in',
                               'ConfigJson': json.dumps({'member_name': 'Alex Doyle', 'author': 'urn:li:person:ALEX1'})}, 'owner')
        shutil.rmtree(outputs.folder(self.tid), ignore_errors=True); outputs.folder(self.tid).mkdir(parents=True, exist_ok=True)
        self.woken, self.net, self.seen = [], LinkedIn(), set()

    def close(self):
        self._on.stop(); shutil.rmtree(outputs.folder(self.tid), ignore_errors=True); selfclose._MARKS.clear(); general._WOKEN.clear(); browsergate.HANDS.clear()

    # ── the agent ──
    def agent(self, name, **args):
        "One tool call of the task's agent, over the route a CLI's MCP client posts to: what it was answered (its JSON)."
        hdr = {'X-Taskuary-Token': SRV['agent_token'], guard.TASK_HDR: guard.task_proof(SRV, self.tid)}
        r = c.post(f'/api/mcp?task={self.tid}', headers=hdr, json={'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call', 'params': {'name': name, 'arguments': args}})
        res = r.json()['result']
        assert r.status_code == 200 and not res['isError'], res
        return json.loads(res['content'][0]['text'])

    def post(self, network='linkedin', text='The ledger portal is live.', **more):
        "A call of its own: one post, one card. -> its review id."
        return self.agent('propose', kind='post', network=network, text=text, **more)['review']

    def one_call(self, items, **more):
        "ONE call carrying a set (`items`). -> the review ids it filed, in the order given."
        out = self.agent('propose', kind='post', items=items, **more)
        assert out['ok'] and out.get('batch'), out
        return [r['ReviewId'] for r in self.s._rows('SELECT ReviewId FROM review WHERE Batch=? ORDER BY ReviewId', (out['batch'],))]

    def says(self, words):
        "Its answer, filed as a turn's is - and the turn's end."
        self.s.add_comment(self.tid, 'assistant', general.ASSISTANT_TYPE, words); ws.record(self.s, self.tid, 'run1', 'turn_end', text=words, source='api')

    # ── the owner ──
    def wakes(self):
        "Every wake of the task's agent while this holds lands in `woken`, whatever road it would have taken (general.to_agent - the one road in)."
        return mock.patch.object(general, 'to_agent', lambda st, t, said='', actor='owner', heard=None, **k: self.woken.append(said) or (heard and heard('woke')) or 'woke')

    def press(self, rid, verb='approve'):
        "His press on a card, as his page sends it (the card as drawn rides along): the route's answer."
        p = json.loads(self.s.get_review(rid)['DraftText'])
        body = {'verb': verb, **({'final_text': p.get('text'), 'shown': p} if verb == 'approve' else {})}
        with mock.patch.multiple(linkedin.requests, get=self.net.get, post=self.net.post, put=self.net.put), self.wakes():
            return c.post(f'/api/reviews/{rid}/decide', headers=OWNER, json=body).json()

    def run(self, key, skip=()):
        "His one press on a list card: every ticked row done, each by its own road - to its end."
        with mock.patch.multiple(linkedin.requests, get=self.net.get, post=self.net.post, put=self.net.put), self.wakes():
            r = c.post(f'/api/reviews/batch/{key}/run', headers=OWNER, json={'skip': list(skip)})
            assert r.status_code == 200, r.text
            for t in [t for t in threading.enumerate() if t.name == f'batch-{key}']: t.join(30)
        return c.get(f'/api/reviews/batch/{key}', headers=OWNER).json()

    def types(self, words, key):
        "His own line, heard by the turn it starts - which begins with it, as a turn does (conversation.hear)."
        from taskuary import conversation
        general.wait_line(self.s, self.tid, words, line_id=key); general.take_kept(self.s, self.tid); conversation.hear(self.s, self.tid, turn=True)

    # ── the chat ──
    def read(self):
        "The chat as the page is served it. Every read is checked against the two rules that hold at ALL times: it stays, and a waiting card is last."
        cardqueue._SEEN.clear()
        got = c.get(f'/api/tasks/{self.tid}/conversation', headers=OWNER).json()
        now = {r[:2] for r in rows(got)}
        assert not self.seen - now, f'gone from the chat: {sorted(self.seen - now, key=str)}'
        assert not under_a_waiting_card(got), f'drawn under a card that still waits: {under_a_waiting_card(got)}'
        self.seen |= now
        return got

    def waiting(self): return [r['ReviewId'] for r in self.s._rows("SELECT ReviewId FROM review WHERE TaskId=? AND Status='pending' ORDER BY ReviewId", (self.tid,))]
    def told(self): return events.take(self.s, self.tid)[0]


def rows(got) -> list:
    "The chat top to bottom, one entry a thing drawn: ('line' | 'turn' | 'note' ..., its id), and ('card', review, status) where the card stands."
    out = []
    for x in got['items']:
        if x['kind'] == 'card': out.append(('card', x['review'], x['status'])); continue
        out.append((x['kind'], x['id']))
        out += [('card', k['review'], k['status']) for k in x.get('cards') or []]
    return out


def drawn(got) -> list: return [r for r in rows(got) if r[0] == 'card']


def under_a_waiting_card(got) -> list:
    "What is drawn after a card that still waits, this side of his next line: by the rule, nothing but cards."
    bad, waits = [], False
    for r in rows(got):
        if r[0] == 'line': waits = False
        elif r[0] == 'card': waits = waits or r[2] == 'pending'
        elif waits: bad.append(r)
    return bad


@pytest.fixture
def w(tmp_path):
    world = World(tmp_path / 'taskuary.db')
    with mock.patch.dict(term.SESSIONS, {}, clear=True): yield world          # ...no session of its own is live: its agent rests between turns
    world.close()


def alone(w): return [w.post()]
def a_set(w): return w.one_call([{'network': n, 'text': f'The ledger portal is live ({n}).'} for n in NETS])
def a_list(w): return w.one_call([{'text': f'Ledger portal tip {i}.'} for i in (1, 2, 3)], network='linkedin')
def separate(w): return [w.post(text='The ledger portal is live.'), w.post(text='A second post about the portal.')]
SHAPES = {'a card alone': alone, 'a set under tabs': a_set, 'a list card': a_list, 'separate cards': separate}


@pytest.fixture(params=list(SHAPES))
def cards(request, w):
    "Each shape of card, raised by the agent's own tool and said in its turn."
    ids = SHAPES[request.param](w); w.says('It is set up for your press.')
    return ids


# ── THE SHAPES: decided by how the agent called ──────────────────────────────────────────────────────────────────────────────────────────

def test_separate_calls_are_separate_cards_one_after_another_never_tabs(w):
    "Two unrelated things - a call each - are two cards: one in front, the other behind it until he has pressed the first. Never tabs of one."
    a, b = separate(w); w.says('Two posts are set up.')
    q = w.read()['queue']
    assert (q['live'], q['held'], q['sets']) == ([a], [b], {}), q
    assert drawn(w.read()) == [('card', a, 'pending')], 'one card in front of him'
    assert w.press(a)['ok']
    assert drawn(w.read()) == [('card', a, 'approved'), ('card', b, 'pending')], 'the first stays, pressed; the second stands after it'


def test_one_call_of_different_acts_is_one_card_with_a_tab_each(w):
    "The same post for three networks, raised in ONE call: one card, a tab each named by where it goes, each tab pressed by itself."
    ids = a_set(w); w.says('Three posts are set up.')
    got = w.read(); [tabs] = got['queue']['sets'].values()
    assert [(t['rid'], t['name'], t['done']) for t in tabs] == [(ids[0], 'LinkedIn', False), (ids[1], 'X', False), (ids[2], 'Bluesky', False)], tabs
    assert drawn(got) == [('card', ids[0], 'pending')] and got['queue']['held'] == [], 'ONE card - none of it held behind another'
    named = {r['ReviewId']: r.get('Tab') for r in c.get(f'/api/tasks/{w.tid}', headers=OWNER).json()['reviews']}
    assert [named[i] for i in ids] == ['LinkedIn', 'X', 'Bluesky'], 'each row tells the page its tab'


def test_one_call_of_one_act_to_many_is_one_list_card_never_tabs_and_one_press_does_them_all(w):
    "A bulk act: one list card, no tabs; his one press does every row, the run's progress kept on the card, a row he left out never done."
    ids = a_list(w); w.says('Three tips are on one card.')
    got = w.read()
    assert got['queue']['sets'] == {} and drawn(got) == [('card', ids[0], 'pending')]
    named = {r['ReviewId']: r.get('Tab') for r in c.get(f'/api/tasks/{w.tid}', headers=OWNER).json()['reviews']}
    assert not any(named.get(i) for i in ids), 'a list card has no tabs'
    st = w.run(w.s.get_review(ids[0])['Batch'], skip=[ids[1]])
    assert (st['state'], st['total'], st['done'], st['left'], st['failed']) == ('finished', 3, 2, 1, 0), st
    assert w.net.posted == ['Ledger portal tip 1.', 'Ledger portal tip 3.'] and w.woken == [], 'each as shown; all went, so nobody is woken'
    assert [r[:2] for r in drawn(w.read())] == [('card', ids[0])] and not w.waiting(), 'the card stays where it stood, done'


# ── "THINGS ON CHAT DON'T GO AWAY" / "CARDS NEVER JUST DISAPPEAR" ────────────────────────────────────────────────────────────────────────

def test_nothing_drawn_in_the_chat_goes_whatever_he_presses_and_whatever_is_said_after(w, cards):
    """Every read through a timeline - a no, the agent's later words, a yes, more words, his own line, the turn it starts - holds every row and
    every card the read before it held (World.read checks each one), and nothing of the agent's under a card that still waits."""
    w.read()
    assert w.press(cards[0], 'reject')['ok']; w.read()
    w.says('Noted.'); w.read()
    for rid in w.waiting()[:1]: w.press(rid); w.read()
    w.says('That is done.'); w.read()
    w.types('Hold the rest - what is on my calendar?', 'l-cal'); w.read()
    w.says('Nothing today.'); w.read()
    assert cards[0] in {r[1] for r in drawn(w.read())}, 'the card he said no to is still in the chat'


def test_a_pressed_card_stays_where_it_stood_saying_what_came_of_it(w):
    "Approved or failed: the card is still in the read, in its place, with what his press did."
    a = w.post(); w.says('The post is set up.')
    before = rows(w.read())
    assert w.press(a)['ok']
    after = rows(w.read())
    assert [r[:2] for r in after] == [r[:2] for r in before] and ('card', a, 'approved') in after, 'the same rows, the card now saying it went'
    b = w.post(text='A second post.'); w.says('One more.'); w.read()
    w.net.fail = True
    assert not w.press(b)['ok']
    assert b in {r[1] for r in drawn(w.read())} and w.s.get_review(b)['ActError'], 'a failed press stays on its card, with why'


def test_a_tab_he_pressed_is_still_a_tab_of_the_same_card_with_what_came_of_it(w):
    """He approved one tab of a card and it "disappeared" - the card had slid on. The server's half: the pressed item is still a tab of the same
    card, settled, crossed where he said no; the card's one row stays where it stood and waits while any tab does. (That a press never changes
    the tab SHOWN is the page's own state: website/test/cardLine.test.mjs pins cardLine.lineAt.)"""
    ids = a_set(w); w.says('Three posts are set up.')
    before = rows(w.read())
    assert w.press(ids[1], 'reject')['ok'] and w.press(ids[0])['ok']
    got = w.read(); [tabs] = got['queue']['sets'].values()
    assert [(t['name'], t['done'], bool(t.get('no'))) for t in tabs] == [('LinkedIn', True, False), ('X', True, True), ('Bluesky', False, False)], tabs
    assert rows(got) == before, 'the one card where it stood, still waiting: one tab does'
    assert w.net.posted == ['The ledger portal is live (linkedin).']
    w.press(ids[2], 'reject')
    got = w.read()
    assert [r[:2] for r in drawn(got)] == [('card', ids[0])] and drawn(got)[0][2] != 'pending' and len(next(iter(got['queue']['sets'].values()))) == 3


# ── "NO TEXT AFTER AN APPROVAL CARD UNTIL IT IS DENIED OR APPROVED" ──────────────────────────────────────────────────────────────────────

def test_a_card_is_drawn_once_when_its_turn_has_ended_under_all_the_turn_said_and_never_moves_after(w):
    """The owner, 2026-11-26: "there should be no text writing above card. If you want to say something say it before you render the card."
    A card raised during a turn is not drawn while the turn works - the read says the agent is at work, so the page shows it working - and
    stands once the turn has ended, under everything the turn said before AND after raising it. From then on its place in the read never
    changes: not at his press, not at what is said once it is settled."""
    from taskuary import chatlog
    w.read()
    chatlog.put(w.s, w.tid, 'turn', 't:9', {'started': 2e9}, state='working')
    chatlog.step(w.s, w.tid, 'run1', 'm-1', {'k': 'said', 'text': 'Setting the post up.'})
    a = w.post()
    chatlog.step(w.s, w.tid, 'run1', 'm-2', {'k': 'said', 'text': 'Tell me if you want it shorter.'})
    with mock.patch.object(general, 'working', return_value=True): got = w.read()
    assert drawn(got) == [] and got['working'], 'while its turn works: no card yet, and the chat says the agent is at work'
    chatlog.update(w.s, w.tid, 't:9', state='done')
    got = w.read(); turn = next(x for x in got['items'] if x['id'] == 't:9')
    assert rows(got)[-1] == ('card', a, 'pending') and [k['review'] for k in turn['cards']] == [a], rows(got)
    assert [st['text'] for st in turn['steps']] == ['Setting the post up.', 'Tell me if you want it shorter.'], 'all it said, before and after raising it, is above its card'
    place = [r[:2] for r in rows(got)]
    assert [r[:2] for r in rows(w.read())] == place, 'a refresh: the same place'
    w.press(a)
    assert [r[:2] for r in rows(w.read())] == place, 'his press: the same place'
    w.says('It is posted.')
    assert [r[:2] for r in rows(w.read())][:len(place)] == place, 'and what is said once it is settled goes under it'


def test_what_can_still_arrive_while_a_card_waits_is_never_drawn_under_it(w, cards):
    """THE NET. Nothing wakes the agent while a card waits (the tests under "a click on a card ..."), so nothing of its own comes after the card.
    What can still arrive - a turn a message or a failed press started, a note of Taskuary's - is never drawn UNDER the card (his live app:
    "X draft declined. Reddit and LinkedIn are still available for review." stood under the one still waiting): the card is the last thing.
    Settled, it stays where he last saw it wait and what comes later goes under it."""
    from taskuary import chatlog
    front = cards[0]
    assert rows(w.read())[-1] == ('card', front, 'pending')
    w.says('One more thought on these.')
    got = rows(w.read())
    assert got[-1] == ('card', front, 'pending') and [r[0] for r in got].count('turn') == 2, got
    chatlog.put(w.s, w.tid, 'turn', 't:9', {'started': 2e9}, state='working')
    chatlog.step(w.s, w.tid, 'run1', 'm-1', {'k': 'said', 'text': 'Looking at it again.'})
    with mock.patch.object(general, 'working', return_value=True): got = rows(w.read())
    assert got[-1] == ('card', front, 'pending') and ('turn', 't:9') in got, f'under a turn at work too: {got}'
    chatlog.update(w.s, w.tid, 't:9', state='done')
    chatlog.put(w.s, w.tid, 'note', 'n-1', {'text': 'Taskuary checked the connection.'})
    assert rows(w.read())[-1] == ('card', front, 'pending')
    while w.waiting(): w.press(w.waiting()[0], 'reject'); w.read()
    w.says('All turned down.')
    got = rows(w.read())
    at = next(i for i, r in enumerate(got) if r[:2] == ('card', front))
    assert got[-1][0] == 'turn' and got.index(('note', 'n-1')) < at and got[at][2] != 'pending', f'settled: it stays, and later words go under it: {got}'
    assert rows(w.read()) == got, 'the same on the next read - a refresh, the phone'


def test_only_his_own_line_comes_after_a_waiting_card_and_the_card_never_crosses_it(w):
    "His line ends what is above it: a card raised before it stays above it, the turn his line starts is under the line."
    a = w.post(); w.says('The post is set up.'); w.read()
    w.types('Leave the post for now - what is on my calendar?', 'l-cal')
    w.says('Nothing today.')
    got = rows(w.read())
    line, card = got.index(('line', 'l-cal')), next(i for i, r in enumerate(got) if r[:2] == ('card', a))
    assert card < line and got[-1][0] == 'turn', got


# ── "A CLICK ON A CARD ONLY WAKES AN AGENT IF THERE IS AN ERROR OR IF THE AGENT HAS TO DO SOMETHING NEXT" ────────────────────────────────

def test_a_no_never_wakes_the_agent_and_is_told_as_his_own_with_its_next_turn(w, cards):
    """His live app: Dismiss on X, then on Reddit - each woke the agent, which wrote under the card still waiting. His no wakes nobody - with
    cards still waiting or with none - and each is told as his own (locked rule 2) with the agent's next turn."""
    w.read()
    for n in range(len(cards)):
        assert w.press(w.waiting()[0], 'reject')['ok']
        assert w.woken == [], f'his no number {n + 1} woke the agent'
        w.read()
    assert w.told().count('he turned it down') == len(cards)


def test_a_yes_with_no_next_step_wakes_nobody_and_one_with_a_next_step_wakes_it_once_nothing_waits(w):
    "Locked rule 3, through cards that wait together: no `then`, no wake; a `then` wakes it once - when no card of the task still waits."
    quiet = w.post(); w.says('The post is set up.')
    assert w.press(quiet)['ok'] and w.woken == []
    step, last = w.post(text='A second post.', then='reply to Gail that it is posted'), w.post(text='A third post.')
    w.says('Two more.')
    assert w.press(step)['ok'] and w.woken == [], 'a card still waits behind it: nothing of the agent comes after a waiting card'
    assert w.press(last, 'reject')['ok'] and len(w.woken) == 1, 'nothing waits now: the step its card named is owed, once'
    assert w.net.posted == ['The ledger portal is live.', 'A second post.']


def test_a_press_that_fails_wakes_the_agent_once(w):
    a = w.post(); w.says('The post is set up.')
    w.net.fail = True
    assert not w.press(a)['ok'] and len(w.woken) == 1 and 'failed' in w.told()


def test_nothing_of_taskuarys_own_wakes_the_agent_while_a_card_waits(w):
    "Not a turn's end, not a check-back come due: with a card waiting for his press the agent rests until he has approved or denied it."
    a = w.post(); w.says('The post is set up.')
    checkback.set_check(w.s, w.tid, f'{datetime.now() + timedelta(minutes=1):%Y-%m-%d %H:%M:%S}', 'whether the post got replies')
    fired, later = [], datetime.now() + timedelta(hours=2)
    with w.wakes():
        assert checkback.due(w.s, later, spawn=lambda fn, *args: fired.append(args)) == 0 and fired == [] and w.woken == []
        assert c.post(f'/api/reviews/{a}/decide', headers=OWNER, json={'verb': 'reject'}).json()['ok'] and w.woken == []
        assert checkback.due(w.s, later, spawn=lambda fn, *args: fired.append(args)) == 1 and len(fired) == 1, 'pressed: it is due now, once'


# ── "NOTHING COMES BACK AUTOMATICALLY" ───────────────────────────────────────────────────────────────────────────────────────────────────

def test_a_card_his_line_greyed_stays_greyed_where_it_stood_and_only_its_agent_brings_it_back(w, cards):
    """His live app: his line asked for a routine change, then a new post; the turn raised its own card - and at its end Taskuary raised the OLD
    post again beside it. A greyed card stays greyed where it stood; the turn's own card stands alone; the old one stands again, under his
    line and as it was, only where its agent keeps it."""
    w.read()
    w.types('First something else - then we redo these.', 'l-redo')
    assert all(proposals.passed(w.s.get_review(r)) for r in cards), 'his line greys what waited'
    new = w.post(text='Something else entirely.')
    w.says('That is set up; the others follow your approval.')
    got = rows(w.read())
    assert w.waiting() == [new], f'an old card came back by itself: {w.waiting()}'
    line = got.index(('line', 'l-redo'))
    assert [r for r in got[:line] if r[0] == 'card' and r[2] == 'passed'] and ('card', new, 'pending') in got[line:], got
    assert 'only where you keep it' in cardqueue.screen(w.s, w.tid), 'and its agent is told the truth of it'
    out = w.agent('keep_card', which=' + '.join(f'rv{r}' for r in cards))
    assert out['ok'] and all(proposals.passed(w.s.get_review(r)) for r in cards) and len(w.waiting()) == 1 + len(cards), out
    w.read()
