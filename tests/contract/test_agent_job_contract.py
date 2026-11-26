"""THE BASIC INTERACTIONS - LOCKED (the owner, 2026-11-25: "we need basic interactions to work and not go in circles ... it's the key to the
whole app"; "build a few code tests that it can never change"; "it can never change the basic interactions").

How an agent does a job, pinned through the real code: a stand-in agent calls Taskuary's own tools over the route every CLI uses (/api/mcp),
the owner presses through the routes his page uses, and what comes of it is read off the store and the chat's own payload. No browser, no
model. The people and the company are invented.

THIS FILE IS THE OWNER'S: no agent edits it, or tests/contract/LOCK, without his written OK (tests/test_contract_lock.py holds its hash).
A test here that fails is a broken product, never a test to adjust.
"""
import json, shutil, time
from types import SimpleNamespace
from unittest import mock

import pytest
from fastapi.testclient import TestClient

from taskuary import (browsergate, browserview, card, config, events, general, guard, inboxes, linkedin, outputs, selfclose, server, signin,
                      taskstate, terminal as term, workerstate as ws)
from taskuary.store import SQLiteStore

c = TestClient(server.app)
SRV = config.load()['server']
OWNER = {'X-Taskuary-Token': 'pytest-owner-token'}
PNG = b'\x89PNG\r\n\x1a\n' + b'\0' * 64
LINK = 'https://northwind.example/portal/launch-notes-and-the-full-feature-list-for-finance-teams'


class LinkedIn:
    "LinkedIn's HTTP, stood in: every call kept, none leaves the machine. `fail`: it answers 500."
    def __init__(self, fail=False): self.calls, self.fail = [], fail
    def get(self, url, **kw): self.calls.append(('GET', url)); return mock.Mock(ok=True, json=lambda: {'sub': 'ALEX1', 'name': 'Alex Doyle'})
    def put(self, url, **kw): self.calls.append(('PUT', url)); return mock.Mock(ok=True)
    def post(self, url, **kw):
        self.calls.append(('POST', url, kw.get('json')))
        if self.fail: return mock.Mock(ok=False, status_code=500, text='server error', json=lambda: {'message': 'server error'})
        if 'initializeUpload' in url: return mock.Mock(ok=True, json=lambda: {'value': {'uploadUrl': 'https://upload.linkedin.test/1', 'image': 'urn:li:image:C1'}})
        return mock.Mock(ok=True, headers={'x-restli-id': 'urn:li:share:42'}, json=lambda: {})
    @property
    def posted(self): return [x[2]['commentary'] for x in self.calls if x[0] == 'POST' and 'initializeUpload' not in x[1]]


class World:
    """One owner's Taskuary on a database file of its own: LinkedIn connected, X not set up, one task its agent works. `agent` is the
    stand-in agent's tool call; `press`, `via_browser` and `chat` are the owner's page."""
    def __init__(self, path):
        self.path = str(path); self.open()
        self.tid = self.s.create_task({'Title': 'Posts about the ledger portal', 'Kind': 'general', 'Status': 'open', 'OriginBase': 'owner'}, 'owner')
        li = self.s.get_connector_by_type('linkedin')
        self.s.save_connector({'ConnectorId': li['ConnectorId'], 'Active': 1, 'Secret': 'stand-in',
                               'ConfigJson': json.dumps({'member_name': 'Alex Doyle', 'author': 'urn:li:person:ALEX1'})}, 'owner')
        shutil.rmtree(outputs.folder(self.tid), ignore_errors=True); outputs.folder(self.tid).mkdir(parents=True, exist_ok=True)
        self.woken, self.net = [], LinkedIn()
        self.live = SimpleNamespace(sid='run1', task_id=self.tid, alive=True, waiting=lambda: True, status_tail=lambda n=8: [],
                                    send_prompt=lambda text, **k: self.woken.append(text))

    def open(self):
        "The app starts (again): the store opened off its file, nothing kept in memory."
        self.s = SQLiteStore(self.path)
        for m in getattr(self, '_on', []): m.stop()
        self._on = [mock.patch.object(server, 'store', self.s)]
        for m in self._on: m.start()
        general._WOKEN.clear(); selfclose._MARKS.clear(); browsergate.HANDS.clear()
    restart = open

    def close(self):
        for m in self._on: m.stop()
        shutil.rmtree(outputs.folder(self.tid), ignore_errors=True); selfclose._MARKS.clear(); general._WOKEN.clear(); browsergate.HANDS.clear()

    def picture(self, name='portal.png'): (outputs.folder(self.tid) / name).write_bytes(PNG); return name

    def agent(self, name, **args):
        "One tool call of the task's agent, over the route a CLI's MCP client posts to: (what it was answered, was it an error)."
        hdr = {'X-Taskuary-Token': SRV['agent_token'], guard.TASK_HDR: guard.task_proof(SRV, self.tid)}
        r = c.post(f'/api/mcp?task={self.tid}', headers=hdr, json={'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call', 'params': {'name': name, 'arguments': args}})
        assert r.status_code == 200, r.text
        res = r.json()['result']; return res['content'][0]['text'], res['isError']

    def post(self, network, text, **more):
        "The agent raises a post: the review id of its card, or None with what it was told."
        said, err = self.agent('propose', kind='post', network=network, text=text, **more)
        try: got = json.loads(said)
        except ValueError: got = {}
        return (got.get('review') if got.get('ok') and not err else None), said

    def cards(self, status='pending'):
        return self.s._rows("SELECT * FROM review WHERE TaskId=? AND Kind='action' AND Status=? ORDER BY ReviewId", (self.tid, status))
    def proposal(self, rid): return json.loads(self.s.get_review(rid)['DraftText'])
    def chat(self): return c.get(f'/api/tasks/{self.tid}/assistant', headers=OWNER).json()
    def card(self, rid): return next(x for x in self.chat()['cards'] if x['ReviewId'] == rid)

    def press(self, rid, verb='approve', shown=None, text=None):
        """His press on a card, as his page sends it (the card as drawn rides along as `shown`), LinkedIn stood in and the agent's wake kept:
        the route's answer."""
        p = self.proposal(rid) if shown is None else shown
        body = {'verb': verb, **({'final_text': text if text is not None else p.get('text'), 'shown': p} if verb == 'approve' else {})}
        with mock.patch.multiple(linkedin.requests, get=self.net.get, post=self.net.post, put=self.net.put), self.wakes():
            out = c.post(f'/api/reviews/{rid}/decide', headers=OWNER, json=body).json()
            self.settle()
        return out

    def wakes(self):
        "Every wake of the task's agent while this holds lands in `woken`, whatever road it would have taken."
        return mock.patch.object(general, 'to_agent', lambda st, t, said='', actor='owner', heard=None, **k: self.woken.append(said) or (heard and heard('woke')) or 'woke')
    def settle(self, n=0):
        end = time.time() + 1.5
        while time.time() < end and len(self.woken) <= n: time.sleep(.02)
    def told(self): return events.take(self.s, self.tid)[0]
    def waits_on(self): return taskstate.standing(self.s, self.tid)['waits_on']
    def ends_turn(self):
        "The turn's end as its one reader files it: each question the agent asked by its tool becomes his open question."
        _said, asks = selfclose.ask_markers(selfclose.take_marks(self.tid))
        for q, ch in asks: ws.record(self.s, self.tid, 'run1', 'input_needed', request_id=ws.request_id_for(q), text=q, choices=ch, source='api')
        return [q for q, _ in asks]
    def questions(self): return [r for r in ws.status(self.s, self.tid)['requests'] if r.get('ask') == 'question']


@pytest.fixture
def w(tmp_path):
    world = World(tmp_path / 'taskuary.db')
    with mock.patch.dict(term.SESSIONS, {'run1': world.live}, clear=True): yield world
    world.close()


# ── 1. RAISE: the agent says what, Taskuary decides how ────────────────────────────────────────────────────────────────────────────────

def test_a_post_on_a_connected_network_is_one_card_whose_press_goes_through_the_connection(w):
    """The owner: "the action card is the end result". The agent supplies the content - network, words, picture - and with LinkedIn connected
    its card stands with the connection's own press: no Connect on it, and the agent is told so."""
    rid, said = w.post('linkedin', 'The Northwind ledger portal is live Monday.', picture=w.picture())
    [rv] = w.cards(); assert rv['ReviewId'] == rid
    p = w.proposal(rid)
    assert (p['type'], p['text'], p['image']) == ('linkedin_post', 'The Northwind ledger portal is live Monday.', 'portal.png')
    assert w.card(rid)['connect'] is None, 'a connected card carries no Connect'
    assert 'connected account' in said and 'browser' not in json.loads(said)['cards_stand_as'][0]
    assert w.waits_on() == 'you'


def test_a_post_on_a_network_not_set_up_is_its_card_with_connect_and_the_browser_as_its_road(w):
    """The owner: "if you can't connect then use the browser site for X". X is not set up: the card still stands - with Connect beside it - and
    Post via the browser hands exactly his words to the agent for the site, once. Nothing goes through X's API."""
    rid, said = w.post('x', 'Invoices in one place: the Northwind ledger portal is live Monday.')
    assert rid and [r['ReviewId'] for r in w.cards()] == [rid]
    assert w.card(rid)['connect']['label'].startswith('Connect X')
    assert 'Post via the browser' in said
    with w.wakes(), mock.patch.object(inboxes, '_x_post', side_effect=AssertionError("X's API was called for a network not set up")):
        out = c.post(f'/api/reviews/{rid}/via-browser', headers=OWNER, json={'final_text': 'Invoices in one place - live Monday.'}).json()
        again = c.post(f'/api/reviews/{rid}/via-browser', headers=OWNER, json={'final_text': 'Invoices in one place - live Monday.'}).json()
    assert out['ok'] and out['status'] == 'approved' and again.get('already'), (out, again)
    assert len(w.woken) == 1 and 'Invoices in one place - live Monday.' in w.woken[0], 'the agent is handed his words, once'
    assert card.of_review(w.s, w.s.get_review(rid))['state'] == 'handed', 'pressed is not posted: the agent owes the post'
    assert browsergate.check(w.s, w.tid, 'run1', 'agent-browser open https://x.com/compose/post') == {}, 'a network not connected is reached in the browser'


def test_a_connected_network_never_goes_through_the_browser(w):
    """The owner: "only a connected service never goes through the browser". Post via the browser on a connected card is refused and hands
    nothing to the agent; the card still waits for its own press."""
    rid, _ = w.post('linkedin', 'The Northwind ledger portal is live Monday.')
    with w.wakes(): out = c.post(f'/api/reviews/{rid}/via-browser', headers=OWNER, json={'final_text': 'x'}).json()
    assert not out['ok'] and 'connected' in out['why'], out
    assert w.woken == [] and w.s.get_review(rid)['Status'] == 'pending'


def test_a_post_over_its_networks_limit_is_refused_with_the_limit_and_the_count_and_no_card(w):
    """The owner's screen showed an X card at "314 of 280 characters", every press on it greyed. A bad card is never shown: the agent is
    answered with the limit and the count, and raises it right."""
    rid, said = w.post('x', 'The Northwind ledger portal is live. ' + 'a' * 277)          # 314 characters, no link
    assert rid is None and '280' in said and '314' in said, said
    assert w.cards() == [] and w.chat()['cards'] == []


def test_a_post_is_counted_as_its_network_counts_so_one_that_fits_is_never_refused_or_greyed(w):
    """His live card: 314 characters as typed, 249 as X counts them - X counts any link as 23. The post X takes is a card."""
    text = 'Invoices in one place. The Northwind ledger portal goes live Monday. ' + 'b' * 130 + ' ' + LINK
    assert len(text) > 280
    rid, said = w.post('x', text)
    assert rid, said
    assert w.proposal(rid)['text'] == text


def test_a_field_the_card_does_not_draw_is_ignored_never_a_refusal(w):
    """The design: "harmless extra fields are ignored". The live agent's LinkedIn post carried a field its card has none for, and the whole card was refused. What
    the card does not draw is left off it - neither shown nor run."""
    said, err = w.agent('propose', kind='act', action='run_tool', type='linkedin_post', text='The portal is live.', mood='upbeat', hashtags=['ledger'])
    assert not err and json.loads(said)['ok'], said
    [rv] = w.cards(); p = json.loads(rv['DraftText'])
    assert p['text'] == 'The portal is live.' and 'mood' not in p and 'hashtags' not in p


def test_a_picture_that_is_not_there_is_refused_with_the_fix_and_no_card(w):
    "A card is checked when it is raised: a picture that does not exist is said to the agent, and nothing is shown."
    rid, said = w.post('linkedin', 'The portal is live.', picture='no-such-chart.png')
    assert rid is None and 'no-such-chart.png' in said and w.cards() == []


def test_the_same_card_raised_twice_is_one_card(w):
    "One card per ask: a retried call is the card already waiting."
    a, _ = w.post('linkedin', 'The portal is live.'); b, _ = w.post('linkedin', 'The portal is live.')
    assert a == b and len(w.cards()) == 1


# ── 2. PRESS: exactly what was shown, once ────────────────────────────────────────────────────────────────────────────────────────────

def test_a_press_executes_exactly_what_was_shown_once_and_a_second_press_does_nothing(w):
    "Approve runs what the card showed, the same every time; pressed again, nothing more leaves."
    rid, _ = w.post('linkedin', 'The Northwind ledger portal is live Monday.')
    assert w.net.calls == [], 'nothing leaves before the press'
    out = w.press(rid)
    assert out['ok'] and out['status'] == 'approved', out
    assert w.net.posted == ['The Northwind ledger portal is live Monday.']
    again = w.press(rid)
    assert not again['ok'] and again.get('already'), again
    assert len(w.net.posted) == 1, 'a second press posts nothing'


def test_what_he_left_in_the_box_is_what_goes(w):
    "The card's words are his to change while it waits: his press sends the words as he left them."
    rid, _ = w.post('linkedin', 'The portal is live.')
    w.press(rid, text='The portal is live - and it is fast.')
    assert w.net.posted == ['The portal is live - and it is fast.']


def test_a_card_changed_after_it_was_shown_never_runs_under_the_words_he_read(w):
    "A press carries the card as his page drew it: if the card on file is no longer that one, nothing runs and it is shown again."
    rid, _ = w.post('linkedin', 'The portal is live.')
    out = w.press(rid, shown={**w.proposal(rid), 'text': 'The words he read, since replaced.'})
    assert not out['ok'] and out.get('changed') and w.net.calls == []
    assert w.s.get_review(rid)['Status'] == 'pending'


def test_a_press_after_the_agent_stopped_still_executes(w):
    "The act is plain code on his press: no agent has to be alive for it."
    rid, _ = w.post('linkedin', 'The portal is live.')
    with mock.patch.dict(term.SESSIONS, {}, clear=True): out = w.press(rid)
    assert out['ok'] and w.net.posted == ['The portal is live.']


def test_a_press_whose_execution_fails_is_kept_on_its_card_and_its_agent_is_told_once(w):
    """No dead ends: a failure is kept where it happened, with the way past it - the card says what failed, never "done", and its agent is
    told once so it sets up what goes next."""
    rid, _ = w.post('linkedin', 'The portal is live.')
    w.net = LinkedIn(fail=True)
    out = w.press(rid)
    assert not out['ok'] and out.get('act_failed') and '500' in out['send_error'], out
    on_card = w.card(rid)
    assert '500' in (on_card['ActError'] or '') and on_card['Status'] not in ('approved', 'edited')
    assert card.of_review(w.s, w.s.get_review(rid))['state'] == 'failed'
    assert len(w.woken) == 1 and f'rv{rid}' in w.told() and 'failed' in w.told()


def test_his_no_is_told_to_the_agent_as_his_own(w):
    "Tell the truth: an agent is told whose decision a no was - his Dismiss is his, never read as the agent's or Taskuary's own taking back."
    rid, _ = w.post('linkedin', 'The portal is live.')
    out = w.press(rid, 'reject')
    assert out['ok'] and out['status'] == 'rejected' and w.net.calls == []
    now = card.of_review(w.s, w.s.get_review(rid))
    assert (now['state'], now['verb'], now['by']) == ('done', 'no', 'owner')
    assert f'Card rv{rid}' in w.told() and 'he ' in w.told().split(f'Card rv{rid}')[-1]


# ── 3. WAKE: only where a step of the agent's own follows ─────────────────────────────────────────────────────────────────────────────

def test_a_press_wakes_the_agent_only_if_the_card_has_a_then(w):
    """The owner, said some forty times: a press whose end is the act itself wakes nobody; the agent goes on only where it named its own
    step after the press when it raised the card."""
    quiet, _ = w.post('linkedin', 'The portal is live.')
    w.press(quiet)
    assert w.woken == [], 'a press with no `then` wakes nobody'
    step, _ = w.post('linkedin', 'A second post about the portal.', then='reply to Gail that it is posted')
    assert card.carries_on(w.s.get_review(step))
    w.press(step)
    assert len(w.woken) == 1, 'a card with `then` wakes its agent once'
    assert w.net.posted == ['The portal is live.', 'A second post about the portal.']


def test_a_press_taskuary_confirmed_wakes_nobody_for_a_then_that_only_does_what_the_press_did(w):
    """The owner, 2026-11-25 ("Yes, change the rule"): a press whose act Taskuary confirmed went needs no check of the agent's. A `then` that
    names the to-do the card does - which its press ticks - is satisfied by the press; a `then` that is a real next act still wakes it."""
    todo = w.s.merge_task_checklist(w.tid, ['Post the portal announcement'], 'agent')[0]['id']
    rid, _ = w.post('linkedin', 'The portal is live.', todo=todo, then=f'mark to-do {todo} (Post the portal announcement) done')
    w.press(rid)
    assert w.woken == [] and w.net.posted == ['The portal is live.'], 'the confirmed post is the whole of its `then`'
    assert next(i['done'] for i in w.s.task_checklist(w.tid) if i['id'] == todo), 'the press ticked the to-do itself'
    nxt, _ = w.post('linkedin', 'A second post about the portal.', todo=todo, then='reply to Gail that it is posted')
    w.press(nxt)
    assert len(w.woken) == 1, 'a next act of its own wakes it once'


def test_a_send_with_no_then_wakes_nobody_and_closes_the_agents_question_about_that_card(w):
    """A question the agent asked ABOUT a card is answered by his press on it - left standing, "should it go out as drafted?" stayed on the
    task after it went. A question on something else stays his to answer."""
    rid, _ = w.post('linkedin', 'The portal is live.')
    w.agent('ask_owner', question='Should the LinkedIn post go out as drafted?', card=f'rv{rid}')
    w.agent('ask_owner', question='Which customers may the next post name?')
    w.ends_turn()
    assert len(w.questions()) == 2
    w.press(rid)
    assert w.woken == []
    assert [q['text'] for q in w.questions()] == ['Which customers may the next post name?']


# ── 4. QUESTION: one, standing until he answers ───────────────────────────────────────────────────────────────────────────────────────

def test_the_agents_question_stands_until_answered_and_his_answer_reaches_the_agent_once(w):
    "A missing fact only he has is one question in the task; it waits on him until he answers, and his answer is handed to the agent once."
    other, _ = w.post('linkedin', 'An unrelated post.')
    w.agent('ask_owner', question='What salary band should the post state?')
    assert w.ends_turn() == ['What salary band should the post state?']
    [q] = w.questions()
    assert w.waits_on() == 'you'
    w.press(other)
    assert [x['text'] for x in w.questions()] == [q['text']], 'a press on something else leaves it standing'
    w.woken.clear()
    first = ws.answer(w.s, w.tid, q['request_id'], '90-110k')
    w.settle()
    again = ws.answer(w.s, w.tid, q['request_id'], '90-110k')
    assert first['delivered'] and not again['delivered']
    assert w.woken == ['90-110k'] and w.questions() == []


def test_after_a_question_nothing_more_is_raised_that_turn(w):
    """The owner: "stops if it needs something". His chat showed a question with a greyed post card drawn under it. After the agent asks,
    no card is raised in that turn - the tool answers so, and nothing is put on his screen."""
    _, err = w.agent('ask_owner', question='What salary band should the post state?')
    assert not err
    rid, said = w.post('linkedin', 'We are hiring a financial controller.')
    assert rid is None, f'a card was raised after the question: {said}'
    assert w.cards() == [] and w.chat()['cards'] == []
    w.ends_turn()
    rid, said = w.post('linkedin', 'We are hiring a financial controller.')
    assert rid is None and w.cards() == [], f'a card was raised under his unanswered question: {said}'
    [q] = w.questions(); ws.answer(w.s, w.tid, q['request_id'], '90-110k'); w.settle()
    rid, said = w.post('linkedin', 'We are hiring a financial controller. Salary band: 90-110k.')
    assert rid, f'answered, the card is raised: {said}'


# ── 5. HAND-OFF: his step on a page ───────────────────────────────────────────────────────────────────────────────────────────────────

def test_a_step_handed_to_him_on_a_page_shows_his_step_and_his_done_wakes_the_agent_once(w):
    "A step only he can do on the agent's page is one card saying the step; his I'm done tells the agent once, and a second press nothing."
    page = {'open': True, 'url': 'https://pay.vendor.example/checkout'}
    with mock.patch.object(browserview, 'state', return_value=page), mock.patch.object(browsergate, 'page_error', return_value=''):
        said, err = w.agent('hand_over', what='tick the "I am not a robot" box')
        assert not err and json.loads(said)['ok'], said
        step = browserview.handing(w.s, w.tid)
        assert 'tick the "I am not a robot" box' in step['Text'] and 'vendor.example' in step['Text']
        assert w.waits_on() == 'you'
        first = ws.answer(w.s, w.tid, step['RequestId'], '', press=True)
        w.settle()
        again = ws.answer(w.s, w.tid, step['RequestId'], '', press=True)
    assert first['delivered'] and not again['delivered'] and len(w.woken) == 1
    assert browserview.handing(w.s, w.tid) is None


def test_the_agent_may_open_and_read_a_connected_services_site_and_posting_there_goes_through_its_card(w):
    """The owner, 2026-11-25: "we are creating posts here not reading them. If the create fails or if I ask the agent to see if it's already
    posted it, or if it can read my posts, then it should read it." With LinkedIn connected its site opens and reads like any other; a press
    there the gate would hold - the post itself - is answered with its card, never held as a second card on the page."""
    for cmd in ('agent-browser open https://www.linkedin.com/feed/', 'agent-browser tab new linkedin.com/in/me/recent-activity'):
        assert browsergate.check(w.s, w.tid, 'run1', cmd) == {}, cmd
    feed = {'url': 'https://www.linkedin.com/feed/', 'open': True, 'elements': '- textbox "Text editor" [ref=e2]\n- button "Post" [ref=e5]', 'name': 'LinkedIn'}
    posts = lambda store, todo, *a, **k: [{'hold': True, 'what': 'click the "Post" button on LinkedIn', 'why': 'it speaks for you', 'kind': 'speaks'} for _ in todo]
    with mock.patch.object(browsergate, 'page', return_value=feed), mock.patch.object(browsergate, 'judge', side_effect=posts):
        no = (browsergate.check(w.s, w.tid, 'run1', 'agent-browser click @e5').get('hookSpecificOutput') or {})
    assert no.get('permissionDecision') == 'deny' and 'LinkedIn is connected' in no['permissionDecisionReason'], no
    assert not w.s._rows("SELECT * FROM review WHERE TaskId=? AND Kind='action' AND Status='pending'", (w.tid,)), 'no second card on the page'


def test_a_connected_services_sign_in_is_his_step_where_reading_needs_it(w):
    "To read his own posts the agent may need the site signed in: that page is his step like any other - only the act is its card's."
    page = {'open': True, 'url': 'https://www.linkedin.com/uas/login'}
    with mock.patch.object(browserview, 'state', return_value=page), mock.patch.object(browsergate, 'page_error', return_value=''):
        said, _ = w.agent('hand_over', what='sign in to LinkedIn so I can read your recent posts')
    assert json.loads(said)['ok'], said
    assert browserview.handing(w.s, w.tid)


def test_where_a_network_is_not_connected_its_card_comes_first_and_its_sign_in_at_his_press(w):
    """The owner, 2026-11-22: "card first, sign-in at the press". On real runs both Codex and Claude, asked for posts with X not set up, opened
    x.com and handed him "Sign in to X" with no card raised. The site's page is his step only once his press on the card (Post via the
    browser) handed the post to the agent: before it the hand-over is answered with that fact, and nothing is put to him."""
    page = {'open': True, 'url': 'https://x.com/i/flow/login'}
    with mock.patch.object(browserview, 'state', return_value=page), mock.patch.object(browsergate, 'page_error', return_value=''), \
         mock.patch.object(signin, 'needs', side_effect=lambda st, tid, sid, *a, **k: ws.record(st, tid, sid, 'input_needed', request_id='signin:x.com',
                                                                                             text='Sign in to x.com to continue', source='api') and {'site': 'x.com'}), \
         mock.patch.object(signin, 'shows_signin', return_value=True):
        said, _ = w.agent('hand_over', what='sign in to X', site='x.com')
        assert json.loads(said)['ok'] is False and 'card' in json.loads(said)['why'], said
        assert browserview.handing(w.s, w.tid) is None, 'nothing is put to him before the card'
        rid, _ = w.post('x', 'Invoices in one place - live Monday.')
        with w.wakes(): assert c.post(f'/api/reviews/{rid}/via-browser', headers=OWNER, json={'final_text': 'Invoices in one place - live Monday.'}).json()['ok']
        said, _ = w.agent('hand_over', what='sign in to X', site='x.com')
        assert json.loads(said)['ok'], f'after his press the sign-in is his step: {said}'
        assert browserview.handing(w.s, w.tid)


def test_no_sign_in_is_put_to_him_beside_a_card_that_waits(w):
    """The owner: "we are trying to post to twitter but the browser is asking about linkedin. it's completely broken." His screen showed the X
    card and, beside it, "Sign in to linkedin.com to continue" off a tab the agent had left on a sign-in page. One thing is asked of him at a
    time, and what his browser pane shows belongs to the card on his screen: a turn that ends with cards waiting raises no sign-in."""
    on_signin = [mock.patch.object(signin, 'on_signin_page', return_value=True), mock.patch.object(signin, 'set_aside', return_value=False),
                 mock.patch.object(browsergate, 'held', return_value=[])]
    for m in on_signin: m.start()
    try:
        assert browserview.left_on_signin(w.s, w.tid, 'run1'), 'with nothing else asked, a turn left on a sign-in page is his step'
        w.post('x', 'Invoices in one place - live Monday.')
        assert not browserview.left_on_signin(w.s, w.tid, 'run1'), 'a card waits on him: no second, unrelated ask beside it'
    finally:
        for m in on_signin: m.stop()


# ── 6. THE TURN'S END: needs him / done / working - and the chat shows only that ──────────────────────────────────────────────────────

def test_a_turn_ends_needing_him_done_or_working_and_never_two_at_once(w):
    "Who moves next is one reading: him while a card or a question waits, the agent while it works, nobody once what he asked is done."
    assert w.waits_on() is None
    rid, _ = w.post('linkedin', 'The portal is live.')
    assert w.waits_on() == 'you'
    general.hand(w.tid)                                         # ...an input on its way to the agent: at work
    try: assert w.waits_on() == 'agent'
    finally: general.hand(w.tid, -1)
    w.press(rid)
    assert w.waits_on() is None, 'pressed, with no step after it: nothing is asked of anyone'


def test_working_files_are_not_drawn_in_the_chat_and_a_cards_picture_is_drawn_only_on_its_card(w):
    """The owner: "it should work through what it needs and action cards, not a bunch of artifacts". His chat filled with charts, a drafts .md
    and each picture three times. What an agent makes on the way - scripts, charts, drafts - is kept in the task's files and not drawn in the
    chat; a card's picture is drawn on that card, once; only a file handed over on purpose (show) is drawn."""
    f = outputs.folder(w.tid)
    (f / 'drafts.md').write_text('# Drafts\n\nX: ...\nLinkedIn: ...\n', encoding='utf-8')
    (f / 'make_chart.py').write_text('print(1)\n', encoding='utf-8')
    w.picture('scratch-chart.png'); w.picture('portal.png'); w.picture('for-him.png')
    rid, _ = w.post('linkedin', 'The portal is live.', picture='portal.png')
    said, err = w.agent('show', files=[str(f / 'for-him.png')])
    assert not err, said
    w.s.add_comment(w.tid, 'assistant', general.ASSISTANT_TYPE, 'The LinkedIn post is set up for your press.')     # ...and its turn ends
    chat = w.chat()
    assert [m for m in chat['messages'] if m['role'] == 'assistant'], 'the turn that made them is in the chat'
    drawn ={o['name'] for k in ('outputs', 'turnOutputs') for o in chat.get(k) or [] if o.get('after')}
    assert drawn & {'drafts.md', 'make_chart.py', 'scratch-chart.png'} == set(), f'working files drawn in the chat: {drawn}'
    assert 'portal.png' not in drawn and w.card(rid)['post']['image'] == 'portal.png', "a card's picture is drawn on its card only"
    assert 'for-him.png' in said and 'TASKUARY-FILES' in said, 'what the agent hands over on purpose is drawn'
    assert {'drafts.md', 'make_chart.py', 'scratch-chart.png'} <= {r['name'] for r in outputs.listing(w.tid)}, 'kept in the task files'


# ── 7. A RESTART between the card and the press keeps all of it ───────────────────────────────────────────────────────────────────────

def test_a_restart_between_the_card_and_the_press_keeps_the_card_its_then_and_the_question(w):
    """Nothing that waits on him lives in memory: the app stopped and started again, the card still stands as it was raised, his press still
    runs exactly it, once, its `then` still wakes the agent, and the agent's question still stands."""
    quiet, _ = w.post('linkedin', 'The portal is live.')
    step, _ = w.post('linkedin', 'A second post about the portal.', then='reply to Gail that it is posted')
    w.agent('ask_owner', question='Which customers may the next post name?'); w.ends_turn()
    before = w.proposal(step)
    w.restart()
    assert [r['ReviewId'] for r in w.cards()] == [quiet, step] and w.proposal(step) == before
    assert [q['text'] for q in w.questions()] == ['Which customers may the next post name?'] and w.waits_on() == 'you'
    w.press(quiet)
    assert w.woken == [] and w.net.posted == ['The portal is live.']
    w.press(step)
    assert len(w.woken) == 1 and w.net.posted == ['The portal is live.', 'A second post about the portal.']
    assert not w.press(step)['ok'] and len(w.net.posted) == 2
    assert [q['text'] for q in w.questions()] == ['Which customers may the next post name?']


# ── 8. BULK, AND ONE COMPONENT (the owner, 2026-11-24: "2 ways to hit the same code") ─────────────────────────────────────────────────

def test_a_turn_that_hands_over_three_sheets_draws_them_as_one_artifact_holding_all_three(w):
    """The owner, 2026-11-24: "it put in 9 files as cards? it should combine them ... like the bulk action card, same idea - one card showing
    all the items". Files the agent hands over on purpose are drawn - several of one turn together, as one artifact: every one of them under
    the same turn, none left out because working files are not drawn."""
    openpyxl = pytest.importorskip('openpyxl')
    f, names = outputs.folder(w.tid), ['north.xlsx', 'south.xlsx', 'west.xlsx']
    for n in names:
        wb = openpyxl.Workbook(); wb.active.append(['Region', 'Invoices']); wb.active.append([n.split('.')[0], 12]); wb.save(f / n)
    (f / 'scratch-notes.md').write_text('working notes\n', encoding='utf-8')
    said, err = w.agent('show', files=[str(f / n) for n in names])
    assert not err and all(n in said for n in names), said
    w.s.add_comment(w.tid, 'assistant', general.ASSISTANT_TYPE, 'The three regional sheets are ready.')
    chat = w.chat()
    under = {o['name']: o['after'] for o in chat['outputs'] if o.get('after') and o['name'] in names}
    assert sorted(under) == names, f'every sheet handed over is drawn: {under}'
    assert len(set(under.values())) == 1, 'under one turn, so they stand as one artifact (TurnFiles draws several files of a turn as one)'


def test_a_bulk_approval_does_every_item_with_one_press_exactly_as_shown_and_once(w):
    """The owner, 2026-11-16: "for a job that is a bulk process you should be able to review a few of them and then send them all out". Many of
    one act raised in one call stand as ONE card; one press does every item, each exactly as it was shown, and a second press does nothing."""
    posts = [f'Ledger portal tip {i}: invoices in one place.' for i in range(1, 7)]
    said, err = w.agent('propose', kind='post', network='linkedin', items=[{'text': t} for t in posts])
    assert not err, said
    out = json.loads(said)
    assert out['ok'] and out['on_the_card'] == 6, out
    assert len(w.cards()) == 6 and len({r['Batch'] for r in w.cards()}) == 1, 'six acts, one card'
    assert w.net.calls == []
    with mock.patch.multiple(linkedin.requests, get=w.net.get, post=w.net.post, put=w.net.put), w.wakes():
        r = c.post(f"/api/reviews/batch/{out['batch']}/run", headers=OWNER, json={})
        assert r.status_code == 200, r.text
        end = time.time() + 20
        while time.time() < end and c.get(f"/api/reviews/batch/{out['batch']}", headers=OWNER).json().get('state') != 'finished': time.sleep(.05)
        again = c.post(f"/api/reviews/batch/{out['batch']}/run", headers=OWNER, json={})
        w.settle()
    assert w.net.posted == posts, 'each item went exactly as shown, in order'
    assert again.status_code == 409 and len(w.net.posted) == 6, 'pressed again, nothing more goes'
    assert w.cards() == [] and len(w.woken) <= 1, 'its agent hears the whole run at most once'


LETTERS = [{'to': f'{who}@cedar.example', 'subject': 'The ledger portal is live Monday', 'text': f'Hello {who.title()} - your invoices move to the portal Monday. Alex'}
           for who in ('erin', 'gail', 'paula')]
def _mail(sent):
    "The mailbox stood in at its edge: what would have left, kept."
    from taskuary import outbound
    def send(store, channel, to=None, subject=None, body=None, *a, **k):
        to = [to] if isinstance(to, str) else list(to or [])
        sent.append((to, subject, body)); return {'channel': 'email', 'to': to}
    return mock.patch.multiple(outbound, send_out=send, send_block=lambda *a, **k: '')


def test_one_call_for_three_people_is_one_card_that_sends_all_three_on_one_press_exactly_as_shown(w):
    """The owner, 2026-11-25: "if it's 3 of the same email to different people then it goes in a bulk card because it's one action to multiple
    people ... this is something the agent should decide which tool to use". One call with `items` is ONE card whatever its count; one press
    sends every one, each exactly as it was shown; pressed again, nothing more goes."""
    said, err = w.agent('propose', kind='email', items=LETTERS)
    assert not err, said
    out = json.loads(said)
    assert out['ok'] and out['on_the_card'] == 3 and out.get('batch'), out
    waiting = [x for x in card.waiting(w.s, w.tid, asks=False, trust=False)]
    assert len(waiting) == 1 and len(waiting[0]['rids']) == 3, 'three letters, ONE card on his screen'
    sent = []
    with _mail(sent), w.wakes():
        assert c.post(f"/api/reviews/batch/{out['batch']}/run", headers=OWNER, json={}).status_code == 200
        end = time.time() + 20
        while time.time() < end and c.get(f"/api/reviews/batch/{out['batch']}", headers=OWNER).json().get('state') != 'finished': time.sleep(.05)
        again = c.post(f"/api/reviews/batch/{out['batch']}/run", headers=OWNER, json={})
    assert [(to, sub) for to, sub, _ in sent] == [([x['to']], x['subject']) for x in LETTERS], sent
    assert all(x['text'] in body for x, (_, _, body) in zip(LETTERS, sent)), 'each went with the words it was shown with'
    assert again.status_code == 409 and len(sent) == 3


def test_three_separate_calls_are_three_cards_in_line_one_at_a_time(w):
    """...and "if separate emails need to be sent they should come one after another": a call each is a card each - one in front of him, the
    others behind it, each sent by its own press."""
    rids = [json.loads(w.agent('propose', kind='email', **x)[0])['review_id'] for x in LETTERS]
    assert len(set(rids)) == 3 and not w.s._rows('SELECT 1 FROM review WHERE TaskId=? AND Batch IS NOT NULL', (w.tid,))
    line = card.waiting(w.s, w.tid, asks=False, trust=False)
    assert [x['rids'] for x in line] == [[r] for r in rids] and [x['front'] for x in line] == [True, False, False]
    sent = []
    with _mail(sent), w.wakes():
        out = c.post(f'/api/reviews/{rids[0]}/decide', headers=OWNER, json={'verb': 'approve'}).json()
    assert out.get('ok') and [to for to, _, _ in sent] == [[LETTERS[0]['to']]], (out, sent)
    line = card.waiting(w.s, w.tid, asks=False, trust=False)
    assert [x['rids'] for x in line] == [[rids[1]], [rids[2]]] and line[0]['front'], 'his press brings the next one forward'


def test_an_action_card_and_a_file_artifact_are_drawn_by_the_same_component():
    """The owner, 2026-11-24: "any chart/pdf etc should also be a white artifact; 2 ways to hit the same code: either artifact creation or
    review step". One frame (Artifact.jsx) draws everything a turn sets down: every review card - a reply, a post, an act, a bulk job - is its
    ReviewCard, and a turn's files are drawn through the same Artifact, a group of them with the bulk card's own rows. No second card
    component, no second files renderer."""
    import re
    from pathlib import Path
    src = Path(__file__).resolve().parents[2] / 'website' / 'src'
    jsx = {p.name: p.read_text(encoding='utf-8') for p in src.glob('*.jsx')}
    art = jsx['Artifact.jsx']
    assert re.search(r'export default function Artifact\(', art) and 'tq-turn-frame' in art
    card_body = art.split('export function ReviewCard(', 1)[1]
    assert '<Artifact ' in card_body.split('\nexport ', 1)[0], 'the review card is drawn in the one frame'
    defines = lambda name: [n for n, t in jsx.items() if re.search(rf'(function|const)\s+{name}\b\s*[(=]', t)]
    assert defines('ReviewCard') == ['Artifact.jsx'] and defines('TurnFiles') == ['TurnFiles.jsx'], 'one card component, one files renderer'
    for n in ('ReviewDecision.jsx', 'BulkCard.jsx'):
        assert '<ReviewCard ' in jsx[n] and re.search(r'import \{[^}]*\bReviewCard\b[^}]*\} from "\./Artifact\.jsx"', jsx[n]), f'{n} draws its cards with the one card'
    files = jsx['TurnFiles.jsx']
    assert re.search(r'import Artifact, \{[^}]*\bItems\b[^}]*\} from "\./Artifact\.jsx"', files) and '<Artifact ' in files and '<Items ' in files
    assert 'export const Items' in art and 'items' in card_body.split('{ children', 1)[0], 'a group of files and a bulk card share their rows'
    assert [n for n, t in jsx.items() if 'data-tq-turn-files' in t] == ['TurnFiles.jsx']
