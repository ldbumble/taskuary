"""EVERY KIND OF CARD, ONE LIFECYCLE (the owner, 2026-11-25: "are you only testing posting and PRs? what about other action cards? ... future ones
should work as well, so think for all types of action cards. Make these design fixes so we don't have these issues in general").

Whatever a card carries - an act Taskuary knows (every proposals.ACTIONS entry), a write on a connector (every executor in reports.REGISTRY
that scopes.ACTIONS does not call a read), a letter, a bulk card, the landing question, a post put up through the browser, a step handed to
him on a page - it goes the same way:

    raised -> drawn as ONE card with its press -> his press executes it once -> its outcome stands on the card -> the agent is woken only
    where the card carries its own next step (`then`); a press whose execution FAILS stays on its card with why, and wakes its agent once.

THE KINDS ARE READ OFF THE CODE, NEVER LISTED: a new action or executor added later is a new case here by itself. Each kind's far side is
stood in at the one seam its press runs through (proposals._run for an act, reports.REGISTRY for an executor, outbound.send_out for a
letter), so nothing leaves the machine; the raise, the line, the chat's list, the press route and the wake are the real code. Invented people."""
import json, time
from unittest import mock

import pytest
from fastapi.testclient import TestClient

from taskuary import (bulkcard, card, cardqueue, chatlog, conversation, general, landing, outbound, pagestep, proposals, reports, scopes, server,
                      signin, workerstate as ws)
from taskuary.store import MemoryStore

c = TestClient(server.app)
OWNER = {'X-Taskuary-Token': 'pytest-owner-token'}
ACTS = sorted(proposals.ACTIONS)                                        # every act a card can carry
WRITES = sorted(t for t in reports.REGISTRY if scopes.needs(t) != 'read' and t not in reports.PLANNED and t not in scopes.NEVER_AGENT)
REFUSED = 'the far side refused it: the account is closed'


class World:
    "One owner's Taskuary in memory: one task its agent works, every wake of that agent kept."
    def __init__(self):
        self.s = MemoryStore(); self.woken = []
        self.tid = self.s.create_task({'Title': 'Close the month', 'Kind': 'general', 'Status': 'open', 'OriginBase': 'owner'}, 'owner')
        conversation.hear(self.s, self.tid, turn=True)
        self.s.add_comment(self.tid, 'assistant', general.ASSISTANT_TYPE, 'It is set up for your press.')
        self._on = [mock.patch.object(server, 'store', self.s),
                    mock.patch.object(general, 'to_agent', lambda st, t, said='', actor='owner', heard=None, **k: self.woken.append(said) or (heard and heard('woke')) or 'woke')]
        for m in self._on: m.start()
        general._WOKEN.clear()

    def close(self):
        for m in self._on: m.stop()

    def act(self, p: dict, then: str = '') -> int:
        "An act's card as the store keeps it (proposals.queue's own row)."
        return self.s.add_review({'TaskId': self.tid, 'Kind': 'action', 'Status': 'pending', 'Origin': 'agent', 'DraftText': json.dumps(p),
                                  'Reason': f"the agent proposes to {proposals.ACTIONS[p['action']][0]}", 'NextStep': then or None})

    def cards(self) -> dict:
        cardqueue._SEEN.clear()
        return {k['review']: k for x in chatlog.read(self.s, self.tid)['items'] for k in ([x] if x['kind'] == 'card' else x.get('cards') or [])}

    def press(self, rid: int, verb='approve', text=None) -> dict:
        out = c.post(f'/api/reviews/{rid}/decide', headers=OWNER, json={'verb': verb, **({'final_text': text} if text is not None else {})})
        end = time.time() + .4
        while time.time() < end and not self.woken: time.sleep(.02)
        return out.json()

    def lifecycle(self, rid: int, ran: list, wakes: int):
        "Drawn with its press -> pressed once -> its outcome on the card -> `wakes` wakes; a second press runs nothing."
        drawn = self.cards().get(rid)
        assert drawn and drawn['status'] == 'pending', f'not drawn as a card to press: {drawn}'
        mine = next(k for k in card.waiting(self.s, self.tid) if rid in k['rids'])
        assert mine['state'] == 'pending' and 'approve' in mine['presses'], mine
        out = self.press(rid)
        assert out.get('ok'), out
        assert len(ran) == 1, f'executed {len(ran)} times'
        after = self.cards().get(rid)
        assert after and after['status'] in ('approved', 'edited', 'sent'), f'its outcome is not on its card: {after}'
        assert card.did(self.s, card.of_review(self.s, self.s.get_review(rid))), 'the press says nothing of what it did'
        self.press(rid)
        assert len(ran) == 1, 'a second press ran it again'
        assert len(self.woken) == wakes, f'woke its agent {len(self.woken)} times, not {wakes}: {self.woken}'

    def failure(self, rid: int):
        "A press whose execution fails: kept on its card with why, its agent woken once."
        out = self.press(rid)
        assert not out.get('ok') and REFUSED[:24] in str(out.get('send_error')), out
        rv = self.s.get_review(rid)
        assert REFUSED[:24] in str(rv.get('ActError') or rv.get('Reason') or ''), f'the failure is not kept on its card: {rv}'
        assert self.cards().get(rid), 'the failed card is gone from the chat'
        assert len(self.woken) == 1, f'a failed press woke its agent {len(self.woken)} times'


@pytest.fixture
def w():
    world = World()
    yield world
    world.close()


def _filled(a: str) -> dict:
    "A proposal of act `a` with every field its declaration requires."
    return {'action': a, **{k: 'x' for k in proposals.ACTIONS[a][1]}, **({'sid': 'run1', 'request': 'yourturn:x'} if a in proposals.HELD_ACTS else {})}


@pytest.mark.parametrize('a', ACTS)
@pytest.mark.parametrize('then', ['', 'tell Erin it is done'])
def test_every_act_is_drawn_pressed_once_says_what_it_did_and_wakes_only_for_its_then(w, a, then):
    ran = []
    with mock.patch.object(proposals, 'validate', return_value=(True, '')), mock.patch.object(pagestep, 'sync'), \
         mock.patch.object(proposals, '_run', side_effect=lambda *x, **k: ran.append(1) or {'done': True}):
        rid = w.act(_filled(a), then)
        # ...a held step's own gate tells its agent what it ran (perform), so its press goes through no wake of its own here
        # ...and his answers to its questions are always its agent's to go on with (card.carries_on)
        w.lifecycle(rid, ran, wakes=1 if (then or a == proposals.ASKS) and a not in proposals.HELD_ACTS else 0)


@pytest.mark.parametrize('a', ACTS)
def test_every_act_that_fails_at_its_press_keeps_the_failure_on_its_card_and_wakes_its_agent_once(w, a):
    def fails(*x, **k): raise RuntimeError(REFUSED)
    with mock.patch.object(proposals, 'validate', return_value=(True, '')), mock.patch.object(pagestep, 'sync'), \
         mock.patch.object(proposals, '_run', side_effect=fails):
        w.failure(w.act(_filled(a)))


def _connected(w, t: str) -> int:
    "The connection executor `t` runs on, switched on as an agent tool."
    kind = reports.card_of(t)
    conn = w.s.get_connector_by_type(kind) or {'ConnectorId': w.s.save_connector({'Type': kind, 'Name': kind, 'Active': 1}, 'owner')}
    w.s.save_connector({'ConnectorId': conn['ConnectorId'], 'Active': 1, 'Roles': 'tool', 'Scope': 'admin', 'Secret': 'stand-in'}, 'owner')
    return conn['ConnectorId']


def _write(w, t: str) -> dict:
    """A write of type `t` as its own declaration shapes it: the fields its card draws where the catalogue declares one (connectorcatalog),
    the item a tracker's act is on, an MCP call's tool - else its words."""
    from taskuary import connectorcatalog as cat, trackers
    p = {'action': 'run_tool', 'type': t, 'connector_id': _connected(w, t)}
    if (act := cat.action_for(t)):
        fill = {'choice': lambda f: f['choices'][0]['value'], 'image': lambda f: None}
        named = {'repo': 'northwind/ledger', 'number': '12', 'subreddit': 'accounting'}
        p.update({f['key']: v for f in act['fields'] if (v := named.get(f['key']) or fill.get(f['type'], lambda f: 'Posted from the month-end close.')(f)) is not None})
    else: p['text'] = 'Posted from the month-end close.'
    if t in trackers.TYPES:                                       # ...the item it is on, and what its verb needs (trackers.NEED)
        tracker, verb = trackers.TYPES[t][:2]
        p.update({'item': '1234567' if tracker == 'monday' else 'NW-12', **({need: 'Done'} if (need := trackers.NEED.get(verb)) else {})})
    if t == 'mcp': p['tool'] = 'add_note'
    return p


@pytest.mark.parametrize('t', WRITES)
def test_every_write_on_a_connector_waits_as_one_card_and_its_press_runs_it_once(w, t):
    ran = []
    with mock.patch.dict(reports.REGISTRY, {t: lambda cfg: ran.append(cfg) or ('done', 'it went')}), \
         mock.patch.object(reports, 'resolve_cfg', side_effect=lambda store, cfg: dict(cfg)), mock.patch.object(reports, 'checked', side_effect=lambda store, p: p):
        rid = w.act(_write(w, t))
        assert not ran, 'it ran before his press'
        w.lifecycle(rid, ran, wakes=0)


@pytest.mark.parametrize('t', WRITES)
def test_every_write_that_its_system_refuses_stays_on_its_card_and_wakes_its_agent_once(w, t):
    def fails(cfg): raise RuntimeError(REFUSED)
    with mock.patch.dict(reports.REGISTRY, {t: fails}), mock.patch.object(reports, 'resolve_cfg', side_effect=lambda store, cfg: dict(cfg)):
        w.failure(w.act(_write(w, t)))


# ── the kinds that are no act of a catalogue: a letter, many of one, the work's own question, the browser's road, his step on a page ──────
def _letter(w, to='erin@northwind.example', then='') -> int:
    return w.s.add_review({'TaskId': w.tid, 'Kind': 'slot', 'Status': 'pending', 'DraftText': 'Hi Erin - the October close is done. Alex', 'NextStep': then or None,
                           'Reason': 'assistant wrote this email', 'Deliver': json.dumps({'channel': 'email', 'to': [to], 'subject': 'October close'})})


@pytest.mark.parametrize('then', ['', 'file her answer'])
def test_a_letter_is_drawn_sent_once_and_wakes_only_for_its_then(w, then):
    sent = []
    with mock.patch.object(outbound, 'send_out', lambda *a, **k: sent.append(k.get('to')) or {'channel': 'email', 'to': k.get('to') or []}), \
         mock.patch.object(outbound, 'send_block', lambda *a, **k: ''):
        rid = _letter(w, then=then)
        drawn = w.cards().get(rid)
        assert drawn and drawn['status'] == 'pending', drawn
        out = w.press(rid, text='Hi Erin - the October close is done. Alex')
        assert out.get('ok') and len(sent) == 1, out
        assert w.cards()[rid]['status'] in ('approved', 'edited', 'sent')
        w.press(rid, text='Hi Erin - the October close is done. Alex')
        assert len(sent) == 1 and len(w.woken) == (1 if then else 0), w.woken


def test_a_letter_that_does_not_go_stays_on_its_card_and_wakes_its_agent_once(w):
    def fails(*a, **k): raise RuntimeError(REFUSED)
    with mock.patch.object(outbound, 'send_out', fails), mock.patch.object(outbound, 'send_block', lambda *a, **k: ''):
        rid = _letter(w)
        out = w.press(rid, text='Hi Erin - the October close is done. Alex')
        assert not out.get('ok') or out.get('send_error'), out
        assert w.s.get_review(rid)['Status'] == 'pending' and w.cards().get(rid), 'the letter that did not go still stands for his Send'
        assert len(w.woken) == 1, w.woken


def test_a_bulk_card_is_one_card_whose_one_press_does_every_row_once(w):
    sent = []
    rids = [_letter(w, to=f'owner{i}@cedar.example') for i in range(3)]
    key = bulkcard.new_key()
    w.s._exec(f"UPDATE review SET Batch=? WHERE ReviewId IN ({','.join('?' * len(rids))})", (key, *rids))
    with mock.patch.object(outbound, 'send_out', lambda *a, **k: sent.append(k.get('to')) or {'channel': 'email', 'to': k.get('to') or []}), \
         mock.patch.object(outbound, 'send_block', lambda *a, **k: ''):
        assert len(cardqueue.state(w.s, w.tid)['units']) == 1, 'many of one act are one card'
        st = bulkcard.run(w.s, key, wait=True)
        assert (st['done'], st['failed']) == (3, 0) and len(sent) == 3, st
        try: bulkcard.run(w.s, key, wait=True)
        except ValueError: pass
        assert len(sent) == 3 and not w.woken, 'pressed again, nothing more went; all went, nobody woken'


def test_a_post_put_up_through_the_browser_keeps_every_further_press_on_its_one_card(w):
    """Not connected: his press hands the post to the agent's browser; the sign-in it needs and the site's final Post are HIS, each drawn on
    that same card as its next press - never a second card, never nothing to press."""
    x = w.act({'action': 'run_tool', 'type': 'x_post', 'text': 'We close the month in four days.'})
    assert w.cards()[x]['status'] == 'pending'
    assert proposals.via_browser(w.s, x, '')['ok'] and len(w.woken) == 1, 'his press hands it to its agent, once'
    assert not w.cards()[x].get('step'), 'handed: nothing of his to press yet'
    ws.record(w.s, w.tid, 'run1', 'input_needed', request_id='yourturn:signin-x', text='Your turn in the browser on x.example: sign in to X', source='api')
    got = w.cards()
    signin = pagestep.card_of(w.s, w.tid, 'yourturn:signin-x')
    assert got[x]['status'] == 'pending' and got[x]['step'] == {'review': signin['ReviewId'], 'what': 'Your turn in the browser on x.example: sign in to X', 'card': x, 'press': 'done'}, got[x]
    assert signin['ReviewId'] not in got, 'his sign-in is on the post\'s card, never a card beside it'
    ws.record(w.s, w.tid, 'run1', 'answered', request_id='yourturn:signin-x', text="I'm done", source='owner')
    assert not w.cards()[x].get('step') and w.s.get_review(signin['ReviewId'])['Status'] == 'approved'
    # ...and a shell step held on the way (the re-walk, 2026-11-25: the picture's upload, held, stood as a third tab behind LinkedIn)
    li = w.act({'action': 'run_tool', 'type': 'linkedin_post', 'text': 'We close the month in four days.'})
    up = proposals.queue(w.s, w.tid, {'action': 'shell_act', 'sid': 'run1', 'turn': 0, 'command': 'agent-browser upload @e10 close.png', 'what': 'attach the picture'})['reviewId']
    got = w.cards()
    assert got[x]['step']['review'] == up and up not in got and cardqueue.state(w.s, w.tid)['held'] == [li], 'the held upload is the X card\'s, in front of LinkedIn'
    with mock.patch.object(proposals, '_run', return_value={'performed': 'attach the picture'}): assert w.press(up).get('ok')
    w.s.decide_review(li, 'rejected', None, 'owner')
    held = proposals.queue(w.s, w.tid, {'action': 'browser_act', 'sid': 'run1', 'args': ['click', '@e20'], 'what': 'Publish your post on X'})['reviewId']
    got = w.cards()
    assert got[x]['step']['review'] == held and held not in got
    with mock.patch.object(proposals, '_run', side_effect=lambda *a, **k: cardqueue.done(w.s, w.tid, 'Posted on x.example') and {'performed': 'Publish'}):
        assert w.press(held).get('ok')
    got = w.cards()
    assert got[x]['status'] == 'approved' and not got[x].get('step') and held not in got and not cardqueue.state(w.s, w.tid)['units']


def test_a_sign_in_is_one_card_that_carries_its_way_to_the_fill_page(w):
    """The card gallery, 2026-11-25: a sign-in step said its words twice - a chat line with "fill it in securely" over its card. One step, one
    card: the card says it and carries the fill page's way (`fill`), on its own or as the next press of the post it is on; a code the site asks
    is typed on the page, so its card carries none."""
    ws.record(w.s, w.tid, 'run1', 'input_needed', request_id='signin:x.example', text='Sign in to X to continue', source='api')
    got = w.cards(); c = pagestep.card_of(w.s, w.tid, 'signin:x.example')
    assert json.loads(c['DraftText'])['fill'] is True and got[c['ReviewId']]['status'] == 'pending'
    ws.record(w.s, w.tid, 'run1', 'answered', request_id='signin:x.example', text='Signed in', source='owner'); w.cards()
    x = w.act({'action': 'run_tool', 'type': 'x_post', 'text': 'We close the month in four days.'})
    assert proposals.via_browser(w.s, x, '')['ok']
    ws.record(w.s, w.tid, 'run1', 'input_needed', request_id='signin:x.example~2', text='Sign in to X to continue', source='api')
    assert w.cards()[x]['step']['fill'] is True, 'on the post it is the next press of: the same way there'
    ws.record(w.s, w.tid, 'run1', 'answered', request_id='signin:x.example~2', text='Signed in', source='owner'); w.cards()
    ws.record(w.s, w.tid, 'run1', 'input_needed', request_id='signin:x.example~3', text=signin.CODE_ASK.format(site='x.example'), source='api')
    assert 'fill' not in w.cards()[x]['step'], 'a code is typed on the page'


def test_a_step_handed_to_him_on_a_page_is_a_card_in_the_line_one_at_a_time_and_his_done_settles_it(w):
    """The owner's live task, 2026-11-25: the agent wrote "I also opened a sign-in card for whois.com", the pane read "opening browser", and no
    card stood. The step is a card of the one line: behind another card it waits its turn - its page with it - and the agent is told where
    it stands; in front it is drawn with its I'm done, which closes it and tells its agent once."""
    from taskuary import browsergate, taskstate
    letter = _letter(w)
    ws.record(w.s, w.tid, 'run1', 'input_needed', request_id='yourturn:whois', text='Your turn in the browser on whois.example: sign in to see your domain', source='api')
    got = w.cards(); step = pagestep.card_of(w.s, w.tid, 'yourturn:whois')
    assert step and step['ReviewId'] not in got and got[letter]['status'] == 'pending', 'one card at a time: the letter is in front'
    said = pagestep.place(w.s, w.tid, 'yourturn:whois')
    assert 'in line, 2 of 2' in said and 'erin@northwind.example' in said, said
    ask = {'request_id': 'yourturn:whois', 'ask': 'turn', 'text': 'sign in'}
    assert pagestep.shown(w.s, w.tid, ask) is None, 'no page is put to him beside the card that waits'
    w.s.decide_review(letter, 'rejected', None, 'owner')
    got = w.cards()
    assert got[step['ReviewId']]['status'] == 'pending' and pagestep.shown(w.s, w.tid, ask) == ask, 'in front: its card and its page'
    assert 'on his screen now' in pagestep.place(w.s, w.tid, 'yourturn:whois')
    with mock.patch.object(browsergate, 'done', side_effect=lambda st, t, rid: bool(ws.record(st, t, 'run1', 'answered', request_id=rid, text="I'm done", source='owner')) or True) as done:
        assert w.press(step['ReviewId']).get('ok')
        w.press(step['ReviewId'])
    assert done.call_count == 1 and w.cards()[step['ReviewId']]['status'] == 'approved'
    assert not [k for k in card.waiting(w.s, w.tid) if k['state'] == 'pending'], 'nothing is owed once he is done'


# ── THE AGENT'S QUESTIONS, ONE CARD (the owner, 2026-11-26: an interview is one card answered with one press) ────────────────────────────
ASKED = [{'question': 'Who is the site for?'}, {'question': 'Which pages?', 'choices': ['Home, Menu, Contact', 'One page']},
         {'question': 'What tone?', 'choices': ['Warm', 'Plain']}]
def _tool(w, name, **args):
    "One call of the agent's own tool on its task, through the real door (/api/mcp): (what it was told, whether that was a refusal)."
    from taskuary import config, guard
    srv = config.load()['server']
    r = c.post(f'/api/mcp?task={w.tid}', headers={'X-Taskuary-Token': srv['agent_token'], guard.TASK_HDR: guard.task_proof(srv, w.tid)},
               json={'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call', 'params': {'name': name, 'arguments': args}}).json()['result']
    return r['content'][0]['text'], r['isError']


def test_several_questions_are_one_card_nothing_is_raised_under_it_and_one_press_tells_its_agent_every_answer_once(w):
    from taskuary import events
    said, err = _tool(w, 'ask_owner', question='Before I build the site', questions=ASKED)
    assert not err and 'one card' in said, said
    [rv] = proposals.asks_waiting(w.s, w.tid); rid = rv['ReviewId']
    assert [q['question'] for q in proposals.asks_of(json.loads(rv['DraftText']))] == [q['question'] for q in ASKED]
    drawn = w.cards()
    assert list(drawn) == [rid] and drawn[rid]['status'] == 'pending', 'one card, drawn to press'
    # ...it is the agent's question (locked rule 4): no card under it, and no second set of questions
    said, err = _tool(w, 'propose', kind='post', network='x', text='Harbor Bakery opens Saturday.')
    assert err and 'your question to the owner stands' in said, said
    assert _tool(w, 'ask_owner', questions=ASKED[:2])[1] and len(w.s._rows('SELECT 1 FROM review WHERE TaskId=?', (w.tid,))) == 1
    # ...his one press answers them all - the card as the page drew it, his answers beside it
    answers = ['Locals and visitors to the harbour', 'Home, Menu, Contact', '']
    out = c.post(f'/api/reviews/{rid}/decide', headers=OWNER, json={'verb': 'approve', 'shown': json.loads(rv['DraftText']), 'fields': {'answers': answers}}).json()
    end = time.time() + .4
    while time.time() < end and not w.woken: time.sleep(.02)
    assert out.get('ok') and len(w.woken) == 1, (out, w.woken)
    # ...the card stays where it stood, showing his answers (rule 10), and its agent is told each one in the card's event
    after = w.cards()[rid]; kept = json.loads(w.s.get_review(rid)['FinalText'])['result']['answers']
    assert after['status'] == 'approved' and [a['answer'] for a in kept] == answers
    told = events.render(events.pending(w.s, w.tid), fresh=True)
    assert '1. Who is the site for? - Locals and visitors to the harbour' in told and '3. What tone? - (left empty)' in told, told
    c.post(f'/api/reviews/{rid}/decide', headers=OWNER, json={'verb': 'approve', 'fields': {'answers': ['other', 'other', 'other']}})
    assert len(w.woken) == 1 and [a['answer'] for a in json.loads(w.s.get_review(rid)['FinalText'])['result']['answers']] == answers, 'a second press changed nothing'
    # ...answered, the question no longer stands: the next card is raised
    assert not cardqueue.asking(w.s, w.tid) and not _tool(w, 'propose', kind='post', network='x', text='Harbor Bakery opens Saturday.')[1]


def test_questions_the_agent_takes_back_or_gives_wrongly_leave_nothing_standing(w):
    for bad in ([{'question': 'Only one?'}, {'choices': ['a']}], [{'question': f'Question {i}?'} for i in range(7)]):
        said, err = _tool(w, 'ask_owner', questions=bad)
        assert err and '2-6' in said and not proposals.asks_waiting(w.s, w.tid), said
    # ...one question in the list is the plain question it always was, never a card
    assert not _tool(w, 'ask_owner', questions=[{'question': 'Which domain?', 'choices': ['harborbakery.example']}])[1] and not proposals.asks_waiting(w.s, w.tid)
    _tool(w, 'ask_owner', withdraw=True)
    assert not _tool(w, 'ask_owner', questions=ASKED)[1]
    [rv] = proposals.asks_waiting(w.s, w.tid)
    said, err = _tool(w, 'ask_owner', withdraw=True)
    assert not err and 'Withdrawn' in said and not cardqueue.asking(w.s, w.tid), said
    assert w.s.get_review(rv['ReviewId'])['Status'] == 'superseded' and w.cards()[rv['ReviewId']]['status'] != 'pending', 'greyed where it stood, never gone'


def test_the_landing_question_wakes_its_agent_only_where_its_proposal_named_a_step_after_it(w):
    for then, woken in (('', 0), ('check the deploy is live', 1)):
        w.woken.clear()
        landing._save(w.s, w.tid, {'proposal': {'how': 'merge', **({'then': then} if then else {})}})
        with mock.patch('taskuary.waitroom.deliver', return_value={}), mock.patch.object(general, 'at_work', return_value=False), \
             mock.patch.object(landing, '_hand_back', side_effect=lambda st, t, text: w.woken.append(text)):
            landing._landed(w.s, w.tid, 'merge', 'Merged fix-export into main.', 'owner')
        assert len(w.woken) == woken, (then, w.woken)


# ── HIS NEXT LINE AND THE CARDS THAT WAIT (walk 23) ───────────────────────────────────────────────────────────────────────────────────

def _line(w, words: str):
    "His line on the task, heard and taken by its agent as it is sent (general.take_line's own steps)."
    general.wait_line(w.s, w.tid, words); general.take_kept(w.s, w.tid)
    ws.line_answers(w.s, w.tid, words)


WAITING = [a for a in ACTS if a not in proposals.HELD_ACTS] + ['letter', 'bulk']
def _waiting(w, kind: str) -> list:
    if kind == 'letter': return [_letter(w)]
    if kind == 'bulk':
        rids = [_letter(w, to=f'owner{i}@cedar.example') for i in range(3)]
        w.s._exec(f"UPDATE review SET Batch=? WHERE ReviewId IN ({','.join('?' * len(rids))})", (bulkcard.new_key(), *rids)); return rids
    return [w.act(_filled(kind))]


@pytest.mark.parametrize('kind', WAITING)
def test_his_answer_to_the_agents_own_question_greys_no_card_of_any_kind(w, kind):
    """Walk 23: a LinkedIn post waited, the agent asked him about something else, he pressed its chip - and the post went grey for good while
    the agent said it "is still waiting for your press". His answer to the question the agent asked is no moving on: every card stands."""
    rids = _waiting(w, kind)
    ws.record(w.s, w.tid, 'run1', 'input_needed', text='Two posts are up on X - keep both?', choices=['Keep both', 'Remove the first'], source='api')
    _line(w, 'Keep both')
    assert all(w.s.get_review(r)['Status'] == 'pending' for r in rids), 'his answer to the question greyed a card that waits'
    assert proposals.written_past(w.s, w.tid) == set() and w.cards()[rids[0]]['status'] == 'pending'
    assert 'Waiting for his press now' in cardqueue.screen(w.s, w.tid) and 'Greyed' not in cardqueue.screen(w.s, w.tid)
    for t in ('worker_event', 'comment'): w.s._exec(f"UPDATE {t} SET CreatedAt='2026-01-01 09:00:00' WHERE TaskId=?", (w.tid,))     # ...a while later
    _line(w, 'Now write it shorter')                                    # ...his next line, under no question, moves the chat on as ever
    assert all(proposals.passed(w.s.get_review(r)) for r in rids)


def test_a_card_its_agent_can_still_keep_is_told_whenever_its_turn_ended(w):
    """A contract run failed one time in a few (2026-11-26): the turn's answer fell in the second after his line, and the screen fact dropped
    the greyed card its agent could still keep - told only while both stamps shared a second, which a live turn never does."""
    rids = _waiting(w, WAITING[0])
    _line(w, 'First something else.')
    ws.record(w.s, w.tid, 'run1', 'turn_end', text='That is done.', source='api')
    w.s.add_comment(w.tid, 'assistant', general.ASSISTANT_TYPE, 'That is done.')
    def said(): return 'only where you keep it' in cardqueue.screen(w.s, w.tid)
    assert said(), "the answer in his line's own second"
    w.s._exec("UPDATE worker_event SET CreatedAt='2099-01-01 09:00:00' WHERE TaskId=? AND Kind='turn_end'", (w.tid,))
    w.s._exec("UPDATE comment SET CreatedAt='2099-01-01 09:00:00' WHERE TaskId=? AND ActorType=?", (w.tid, general.ASSISTANT_TYPE))
    cardqueue._SEEN.clear()
    assert said(), "the answer a second later: still the agent's to keep, and still told"
    assert cardqueue.keep(w.s, w.tid, ' + '.join(f'rv{r}' for r in rids), 'agent')['ok'] and not said(), 'kept: told as the card that waits now'


@pytest.mark.parametrize('kind', WAITING)
def test_a_card_his_line_greyed_stays_greyed_and_stands_again_only_by_its_agents_keep(w, kind):
    """The owner, 2026-11-26 ("Nothing comes back automatically ... if the reply is still the right choice after a clarifying question then of
    course bring it back"): his line asked for a routine change and then a new post; at the turn's end Taskuary raised the OLD post again
    beside the routine card - "then it showed the old post not even the new one?". Greyed the second he types, a card stays greyed where it
    stood whatever the turn ends on; its agent is told that as a fact, and it stands again - under his line, as it was, once - only by the
    agent's own keep (walk 23's plain-code re-raise is gone)."""
    rids = _waiting(w, kind)
    assert w.cards()[rids[0]]['status'] == 'pending'
    _line(w, 'The post box on the page is empty.')
    assert all(proposals.passed(w.s.get_review(r)) for r in rids), 'his line greys what waited, the second he types'
    assert 'stands again under his newest line only where you keep it' in cardqueue.screen(w.s, w.tid), cardqueue.screen(w.s, w.tid)
    ws.record(w.s, w.tid, 'run1', 'turn_end', text='That is fixed.', source='api')
    w.s.add_comment(w.tid, 'assistant', general.ASSISTANT_TYPE, 'That is fixed.')
    n = len(w.s._rows('SELECT 1 FROM review WHERE TaskId=?', (w.tid,)))
    assert n == len(rids) and all(proposals.passed(w.s.get_review(r)) for r in rids) and not any(cardqueue.again_of(w.s, r) for r in rids), 'Taskuary raised it again by itself'
    assert w.cards()[rids[0]]['status'] == 'passed', 'and it is still in the chat, greyed where it stood'
    # ...the agent judges it still right: its keep stands it again as a new card under his line, never live again above it
    out = cardqueue.keep(w.s, w.tid, ' + '.join(f'rv{r}' for r in rids), 'agent')
    assert out['ok'], out
    again = [cardqueue.again_of(w.s, r) for r in rids]
    assert all(again) and all(w.s.get_review(n)['Status'] == 'pending' for n in again) and all(proposals.passed(w.s.get_review(r)) for r in rids)
    assert [(w.s.get_review(n)['DraftText'], w.s.get_review(n)['Deliver']) for n in again] == [(w.s.get_review(r)['DraftText'], w.s.get_review(r)['Deliver']) for r in rids], 'as it was'
    chatlog.advance(w.s, w.tid); cardqueue._SEEN.clear(); items = chatlog.read(w.s, w.tid)['items']
    at = lambda rid: next(i for i, x in enumerate(items) for k in ([x] if x['kind'] == 'card' else x.get('cards') or []) if k['review'] == rid)
    line = next(i for i, x in enumerate(items) if 'The post box on the page is empty.' in json.dumps(x))
    assert at(rids[0]) < line < at(again[0]), [x['kind'] for x in items]
    assert w.cards()[again[0]]['status'] == 'pending' and 'Waiting for his press now' in cardqueue.screen(w.s, w.tid)
    assert not cardqueue.keep(w.s, w.tid, ' + '.join(f'rv{r}' for r in rids), 'agent')['ok'], 'kept once'
    _line(w, 'Make it shorter.')
    new = _waiting(w, kind)                                             # ...the turn writes it again: the rewrite is what greys the old one for good
    ws.record(w.s, w.tid, 'run1', 'turn_end', text='Shorter now.', source='api')
    assert all(proposals.passed(w.s.get_review(r)) for r in again) and all(w.s.get_review(r)['Status'] == 'pending' for r in new)
