"""HIS EDIT IS WHAT GOES (the owner, 2026-11-26: "never even overwrite an edit of a text for any card from user. Make sure that never happens
... They would send email with generated email instead of their edits").

Whatever card takes his words - a post on any network, a tracker comment, an issue, a letter, a list of letters, a change to something
stored, his answers to the agent's questions - the words he left in it are the words:

    typed -> kept on its review as he types -> no draft is written over them -> his press sends exactly them, from any screen ->
    the card reads them after the press, where it went AND where it failed -> its agent is told them.

THE KINDS ARE READ OFF THE CODE, NEVER LISTED: every write a catalogue card draws a box for (connectorcatalog.text_key) is a case here by
itself, so a network added later is covered the day it is added. Each far side is stood in at the one seam its press runs through
(reports.REGISTRY for an executor, outbound.send_out for a letter, proposals._run for a change); the routes, the store, the verdict road
and what the agent is told are the real code. No browser, no model. Invented people."""
import json, time
from unittest import mock

import pytest, requests
from fastapi.testclient import TestClient

from taskuary import bulkcard, cardqueue, connectorcatalog as cat, conversation, general, linkedin, outbound, pagestep, proposals, reports, scopes, server, trackers, workflows
from taskuary.store import MemoryStore, his_edit, his_words

c = TestClient(server.app)
OWNER = {'X-Taskuary-Token': 'pytest-owner-token'}
WRITES = sorted(t for t in reports.REGISTRY if scopes.needs(t) != 'read' and t not in reports.PLANNED and t not in scopes.NEVER_AGENT)
BOXED = [t for t in WRITES if cat.text_key(cat.action_for(t))]             # every write whose card draws a box for its words
FILED = 'We built a scheduler. It is good at finding a time.'              # ...as its agent wrote them
HIS = 'Have you ever tried to get nine people into one room?\n\nWe built a scheduler that finds the best time and shows what it costs.\n\nAlex Doyle'
REFUSED = 'the far side refused it: field override not supported'


class World:
    "One owner's Taskuary in memory: one task its agent works, every wake of that agent kept."
    def __init__(self):
        self.s = MemoryStore(); self.woken = []
        self.tid = self.s.create_task({'Title': 'Tell people about the scheduler', 'Kind': 'general', 'Status': 'open', 'OriginBase': 'owner'}, 'owner')
        conversation.hear(self.s, self.tid, turn=True)
        self.s.add_comment(self.tid, 'assistant', general.ASSISTANT_TYPE, 'It is set up for your press.')
        self._on = [mock.patch.object(server, 'store', self.s),
                    mock.patch.object(general, 'to_agent', lambda st, t, said='', actor='owner', heard=None, **k: self.woken.append(said) or (heard and heard('woke')) or 'woke')]
        for m in self._on: m.start()
        general._WOKEN.clear()
    def close(self):
        for m in self._on: m.stop()

    def act(self, p: dict) -> int:
        return self.s.add_review({'TaskId': self.tid, 'Kind': 'action', 'Status': 'pending', 'Origin': 'agent', 'DraftText': json.dumps(p),
                                  'Reason': f"the agent proposes to {proposals.ACTIONS[p['action']][0]}"})
    def letter(self, to='erin@northwind.example') -> int:
        return self.s.add_review({'TaskId': self.tid, 'Kind': 'slot', 'Status': 'pending', 'DraftText': FILED, 'Reason': 'assistant wrote this email',
                                  'Deliver': json.dumps({'channel': 'email', 'to': [to], 'subject': 'The scheduler'})})
    def write(self, t: str) -> dict:
        "A write of type `t` as its own catalogue card shapes it, its box holding the agent's words."
        kind = reports.card_of(t)
        conn = self.s.get_connector_by_type(kind) or {'ConnectorId': self.s.save_connector({'Type': kind, 'Name': kind, 'Active': 1}, 'owner')}
        self.s.save_connector({'ConnectorId': conn['ConnectorId'], 'Active': 1, 'Roles': 'tool', 'Scope': 'admin', 'Secret': 'stand-in'}, 'owner')
        act, named = cat.action_for(t), {'repo': 'northwind/ledger', 'number': '12', 'subreddit': 'accounting'}
        fill = {'choice': lambda f: f['choices'][0]['value'], 'image': lambda f: None}
        p = {'action': 'run_tool', 'type': t, 'connector_id': conn['ConnectorId'],
             **{f['key']: v for f in act['fields'] if (v := named.get(f['key']) or fill.get(f['type'], lambda f: FILED)(f)) is not None}}
        if t in trackers.TYPES:
            tracker, verb = trackers.TYPES[t][:2]
            p.update({'item': '1234567' if tracker == 'monday' else 'NW-12', **({need: 'Done'} if (need := trackers.NEED.get(verb)) else {})})
        return p

    def typed(self, rid: int, **edit):
        "He types into the card: the page keeps it on the review (heldEdits.js -> POST /held)."
        out = c.post(f'/api/reviews/{rid}/held', headers=OWNER, json={'edit': edit or None})
        assert out.status_code == 200 and out.json()['ok'], out.text
    def press(self, rid: int, **body) -> dict:
        out = c.post(f'/api/reviews/{rid}/decide', headers=OWNER, json={'verb': 'approve', **body})
        end = time.time() + .3
        while time.time() < end and not self.woken: time.sleep(.02)
        return out.json()
    def drawn(self, rid: int) -> dict:
        "The act's card as the task's page is handed it (GET /api/tasks/{id}/assistant)."
        return next(k for k in c.get(f'/api/tasks/{self.tid}/assistant', headers=OWNER).json()['cards'] if k['ReviewId'] == rid)
    def told(self, rid: int) -> str:
        "The card's words as its agent is told them."
        return cardqueue._words(self.s.get_review(rid))


@pytest.fixture
def w():
    world = World()
    yield world
    world.close()


def _stood_in(t, ran, fails=False):
    def run(cfg):
        ran.append(cfg)
        if fails: raise RuntimeError(REFUSED)
        return ('done', 'it went')
    return mock.patch.dict(reports.REGISTRY, {t: run}), mock.patch.object(reports, 'resolve_cfg', side_effect=lambda store, cfg: dict(cfg)), \
        mock.patch.object(reports, 'checked', side_effect=lambda store, p: p)


def _his(t):
    "His words for write `t`, short enough for its network's own limit."
    f = cat.field(cat.action_for(t), cat.text_key(cat.action_for(t)))
    return HIS if not f.get('max') or len(HIS) <= f['max'] else HIS[:f['max'] - 1].strip()


# ── an act with a box: every network's post, a comment, an issue ─────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize('t', BOXED)
def test_his_words_in_an_acts_box_are_what_its_press_runs_and_what_its_card_keeps(w, t):
    ran, k, his = [], cat.text_key(cat.action_for(t)), _his(t)
    a, b, d = _stood_in(t, ran)
    with a, b, d:
        rid = w.act(w.write(t))
        out = w.press(rid, final_text=his)
    assert out.get('ok') and len(ran) == 1, out
    assert ran[0][k] == his, f'{t} ran with {ran[0][k]!r}'
    assert json.loads(w.s.get_review(rid)['FinalText'])[k] == his and w.drawn(rid)['post'][k] == his, 'the card that went reads his words'
    assert ' '.join(his.split())[:60] in w.told(rid), 'and its agent is told his words went'


@pytest.mark.parametrize('t', BOXED)
def test_a_press_that_fails_keeps_his_words_on_its_card_and_tells_its_agent_them(w, t):
    ran, k, his = [], cat.text_key(cat.action_for(t)), _his(t)
    a, b, d = _stood_in(t, ran, fails=True)
    with a, b, d:
        rid = w.act(p := w.write(t))
        out = w.press(rid, final_text=his)
    assert not out.get('ok') and ran and ran[0][k] == his, out
    rv = w.s.get_review(rid)
    assert REFUSED[:24] in str(rv.get('ActError')), rv
    assert w.drawn(rid)['post'][k] == his, 'the failed card went back to the words its agent wrote'
    assert ' '.join(his.split())[:60] in w.told(rid) and p[k] not in w.told(rid), 'its agent is told what he pressed, to set the next card up with'
    assert json.loads(rv['DraftText'])[k] == p[k], 'what the agent filed is still on record as filed'


@pytest.mark.parametrize('t', BOXED)
def test_a_press_with_no_words_of_its_own_runs_what_he_typed_into_the_card(w, t):
    "Typed on the task, pressed on the rail, the phone or by a list's one press: the words are the ones he left in the box."
    ran, k, his = [], cat.text_key(cat.action_for(t)), _his(t)
    a, b, d = _stood_in(t, ran)
    with a, b, d:
        rid = w.act(w.write(t))
        w.typed(rid, text=his)
        assert w.drawn(rid)['OwnerEdit'] and his_words(w.s.get_review(rid)) == his, 'the card is handed back what he typed, after a reload too'
        assert ' '.join(his.split())[:60] in w.told(rid), 'and the agent is told the card as it stands'
        out = w.press(rid)
    assert out.get('ok') and ran[0][k] == his and json.loads(w.s.get_review(rid)['FinalText'])[k] == his, (out, ran)


def test_a_video_post_carries_no_alt_text_and_a_picture_keeps_its_own(tmp_path):
    "LinkedIn refuses a whole post for an override its category does not take: a video's media is its urn alone."
    posts = []
    def post(url, **kw):
        if url.endswith('/rest/posts'): posts.append(kw['json'])
        return mock.Mock(ok=True, headers={'x-restli-id': 'urn:li:share:42'}, json=lambda: {})
    (tmp_path / 'tour.mp4').write_bytes(b'\0' * 64); (tmp_path / 'chart.png').write_bytes(b'\0' * 64)
    with mock.patch.object(linkedin.requests, 'post', post), mock.patch.object(linkedin, 'upload_video', lambda *a: 'urn:li:video:V1'), \
         mock.patch.object(linkedin, 'upload_image', lambda *a: 'urn:li:image:C1'):
        for name in ('tour.mp4', 'chart.png'):
            linkedin.run_linkedin_post({'token': 't', 'author': 'urn:li:person:ALEX1', 'text': HIS, 'image_path': str(tmp_path / name), 'alt': 'A week of meetings on one screen'})
    assert posts[0]['content'] == {'media': {'id': 'urn:li:video:V1'}}, posts[0]['content']
    assert posts[1]['content'] == {'media': {'id': 'urn:li:image:C1', 'altText': 'A week of meetings on one screen'}}
    assert posts[0]['commentary'] == posts[1]['commentary'] == HIS


# ── a letter, and a list of them ─────────────────────────────────────────────────────────────────────────────────────────────────────────
def _mail(sent, fails=False):
    def send(store, channel, to, subject, body, **k):
        sent.append({'to': to, 'subject': subject, 'body': body})
        if fails: raise RuntimeError(REFUSED)
        return {'channel': 'email', 'to': to or []}
    return mock.patch.object(outbound, 'send_out', send), mock.patch.object(outbound, 'send_block', lambda *a, **k: '')


@pytest.mark.parametrize('how', ['with the press', 'typed, pressed elsewhere'])
def test_his_words_in_a_letter_are_the_letter_that_goes(w, how):
    sent = []; a, b = _mail(sent)
    with a, b:
        rid = w.letter()
        if how == 'with the press': out = w.press(rid, final_text=HIS)
        else: w.typed(rid, text=HIS, subject='A room for nine'); out = w.press(rid)
    assert out.get('ok') and len(sent) == 1, out
    assert sent[0]['body'].strip() == HIS and FILED not in sent[0]['body'], sent
    if how != 'with the press': assert sent[0]['subject'] == 'A room for nine', 'the subject he changed went with it'
    rv = w.s.get_review(rid)
    assert rv['FinalText'].strip() == HIS and rv['Status'] == 'edited' and HIS.split('\n')[0] in w.told(rid)


def test_no_draft_is_written_over_words_he_typed_and_his_own_ask_takes_them_back(w):
    sent = []; a, b = _mail(sent)
    with a, b:
        rid = w.letter()
        w.typed(rid, text=HIS)
        # ...a later draft from anyone - its agent, the thread moving, versions to pick from - never lands over them
        assert w.s.update_review_draft(rid, 'Hi Erin - a new draft, written again.', None, by='agent:assistant') is False
        w.s.set_review_versions(rid, ['Version one.', 'Version two.'])
        rv = w.s.get_review(rid)
        assert rv['DraftText'] == FILED and not rv.get('Versions') and his_words(rv) == HIS, rv
        # ...a box he emptied holds no words, and his own ask for other words (Redraft) takes his back: then a draft lands
        w.typed(rid, text='   ')
        assert w.s.update_review_draft(rid, 'Hi Erin - written again at his ask.', None) is not False
        w.typed(rid, text=HIS); w.s.his_words_back(rid)
        assert not his_words(w.s.get_review(rid)) and w.s.update_review_draft(rid, 'Hi Erin - and again.', None) is not False
        # ...typed over that one, his are what go
        w.typed(rid, text=HIS)
        assert w.press(rid).get('ok') and sent[0]['body'].strip() == HIS, sent


def test_a_letter_its_agent_writes_again_never_lands_in_the_box_he_typed_into(w):
    "The agent's own road for a task's email (slots.draft): his version is kept with his words on it, and the new letter is a card of its own."
    from taskuary import slots
    first = slots.draft(w.s, w.tid, FILED, to='erin@northwind.example', subject='The scheduler', agent='assistant')
    assert first.get('ok'), first
    rid = first['review_id']
    w.typed(rid, text=HIS)
    # ...a letter is new unless it says what it replaces (the owner's OK, 2026-11-27): his card stands as he left it, the new one beside it
    beside = slots.draft(w.s, w.tid, 'Hi Erin - and one more thing.', to='erin@northwind.example', subject='The scheduler', agent='assistant')
    assert beside.get('ok') and beside['review_id'] != rid and 'replaced_the_owners_version' not in beside, beside
    assert w.s.get_review(rid)['Status'] == 'pending' and his_words(w.s.get_review(rid)) == HIS, 'his card, as he left it'
    again = slots.draft(w.s, w.tid, 'Hi Erin - a second go at it.', to='erin@northwind.example', subject='The scheduler', agent='assistant',
                        slot=first['slot'], replaces=True)
    assert again.get('ok') and again['review_id'] not in (rid, beside['review_id']) and again.get('replaced_the_owners_version') == HIS, again
    mine, new = w.s.get_review(rid), w.s.get_review(again['review_id'])
    assert mine['Status'] == 'closed_unsent' and mine['FinalText'] == HIS and FILED in mine['DraftText'], 'his version, kept as he left it'
    assert 'a second go' in new['DraftText'] and not his_words(new), 'the new letter is its own card, as its agent wrote it'


def test_a_letter_that_does_not_go_still_stands_with_his_words_for_the_next_send(w):
    sent = []; a, b = _mail(sent, fails=True)
    with a, b:
        rid = w.letter()
        w.typed(rid, text=HIS)
        out = w.press(rid, final_text=HIS)
    assert (not out.get('ok') or out.get('send_error')) and w.s.get_review(rid)['Status'] == 'pending', out
    assert his_words(w.s.get_review(rid)) == HIS and HIS.split('\n')[0] in w.told(rid), 'the card that waits again holds the generated words'
    again = []; a, b = _mail(again)
    with a, b: assert w.press(rid).get('ok'), 'his next Send'
    assert again[0]['body'].strip() == HIS, again


def test_a_list_of_letters_goes_each_as_he_left_it_with_one_press(w):
    sent = []; a, b = _mail(sent)
    rids = [w.letter(to=f'owner{i}@cedar.example') for i in range(3)]
    key = bulkcard.new_key()
    w.s._exec(f"UPDATE review SET Batch=? WHERE ReviewId IN ({','.join('?' * len(rids))})", (key, *rids))
    w.typed(rids[1], text=HIS)
    with a, b: st = bulkcard.run(w.s, key, wait=True)
    assert (st['done'], st['failed']) == (3, 0), st
    went = {m['to'][0]: m['body'].strip() for m in sent}
    assert went == {'owner0@cedar.example': FILED, 'owner1@cedar.example': HIS, 'owner2@cedar.example': FILED}, went


# ── a change to something stored, and his answers ───────────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize('how', ['with the press', 'typed, pressed elsewhere'])
def test_his_words_in_a_changes_box_are_what_is_saved(w, how):
    ran, his = [], 'List every invoice over 30 days late, oldest first, with who owns it.'
    p = workflows.change_card({'action': 'change_setup', 'source_id': 7, 'kind': 'report', 'title': 'Late invoices',
                               'was': {'prompt': 'List late invoices.'}, 'patch': {'prompt': 'List invoices over 30 days late.'}})
    with mock.patch.object(proposals, 'validate', return_value=(True, '')), mock.patch.object(pagestep, 'sync'), \
         mock.patch.object(proposals, '_run', side_effect=lambda store, rv, p, *x, **k: ran.append(p) or {'done': True}):
        rid = w.act(p)
        if how == 'with the press': out = w.press(rid, fields={'prompt': his})
        else: w.typed(rid, words={'prompt': his}); out = w.press(rid)
    assert out.get('ok') and ran[0]['patch']['prompt'] == his, (out, ran)
    assert json.loads(w.s.get_review(rid)['FinalText'])['patch']['prompt'] == his


def test_his_answers_typed_into_a_questions_card_are_the_answers_its_agent_gets(w):
    answers = ['Office managers', 'One page', '']
    p = {'action': proposals.ASKS, 'title': 'Before I write the page',
         proposals.ASKS: [{'question': 'Who is it for?', 'choices': []}, {'question': 'How long?', 'choices': ['One page', 'Three']}, {'question': 'What tone?', 'choices': []}]}
    rid = w.act(p)
    w.typed(rid, answers=answers)
    assert his_edit(w.s.get_review(rid))['answers'] == answers
    assert w.press(rid).get('ok')
    assert [x['answer'] for x in json.loads(w.s.get_review(rid)['FinalText'])['result']['answers']] == answers


def test_what_he_typed_is_kept_only_while_the_card_waits_and_only_what_a_card_lets_him_change(w):
    rid = w.letter()
    w.typed(rid, text=HIS, cc=['gail@northwind.example'], to=['stranger@vendor.example'], Status='approved')
    assert his_edit(w.s.get_review(rid)) == {'text': HIS, 'cc': ['gail@northwind.example']}, 'only its words and who is copied - never where it goes'
    assert json.loads(w.s.get_review(rid)['Deliver'])['to'] == ['erin@northwind.example'] and w.s.get_review(rid)['DraftText'] == FILED
    w.typed(rid)
    assert not w.s.get_review(rid).get('OwnerEdit'), 'taken back, nothing is held'
    w.s.decide_review(rid, 'rejected', None, 'owner')
    assert not c.post(f'/api/reviews/{rid}/held', headers=OWNER, json={'edit': {'text': HIS}}).json()['ok'], 'a card already answered takes no edit'


# ── a press that failed: Try again only where a second try could get past it ────────────────────────────────────────────────────────────
def _far_side(t, ran, fail):
    "Executor `t` stood in: what `fail()` hands back is raised - what the far side answered, as a failure carries it."
    def run(cfg):
        ran.append(cfg)
        if (e := fail()): raise e
        return ('done', 'it went')
    return mock.patch.dict(reports.REGISTRY, {t: run}), mock.patch.object(reports, 'resolve_cfg', side_effect=lambda store, cfg: dict(cfg)), \
        mock.patch.object(reports, 'checked', side_effect=lambda store, p: p)


def _answered(status):
    e = RuntimeError(f'the network answered {status}'); e.status = status
    return e


PASSING = {'no answer in time': lambda: requests.Timeout('no answer in 30 seconds'), 'unreachable': lambda: requests.ConnectionError('no route'),
           'down': lambda: _answered(503), 'over its limit': lambda: _answered(429)}
REFUSALS = {'the content': lambda: _answered(400), 'the token': lambda: _answered(403), 'unsaid': lambda: RuntimeError(REFUSED)}


@pytest.mark.parametrize('why', sorted(PASSING))
def test_a_failure_a_second_try_could_get_past_is_his_to_try_again_with_his_words(w, why):
    ran, left = [], [PASSING[why]]
    a, b, d = _far_side('linkedin_post', ran, lambda: left.pop()() if left else None)
    with a, b, d:
        rid = w.act(w.write('linkedin_post'))
        out = w.press(rid, final_text=HIS)
        assert not out.get('ok') and out.get('retry') and out['status'] == 'superseded', out
        drawn, rv = w.drawn(rid), w.s.get_review(rid)
        assert drawn['ActError'] and drawn['ActRetry'] == 1 and drawn['post']['text'] == HIS, 'the failed card reads his words, and lights Try again'
        assert json.loads(rv['DraftText'])['text'] == FILED and len(w.woken) == 1, 'a failure is told to its agent once, as any is'
        out = w.press(rid)                                             # Try again: the press alone, from any screen
    assert out.get('ok') and len(ran) == 2 and ran[1]['text'] == HIS, (out, ran)
    rv = w.s.get_review(rid)
    assert rv['Status'] == 'approved' and json.loads(rv['FinalText'])['text'] == HIS and not w.drawn(rid)['ActRetry']
    assert not w.press(rid).get('ok') and len(ran) == 2, 'pressed again, nothing more went'


def test_the_try_that_fails_too_is_over(w):
    ran = []
    a, b, d = _far_side('linkedin_post', ran, PASSING['down'])
    with a, b, d:
        rid = w.act(w.write('linkedin_post'))
        assert w.press(rid, final_text=HIS).get('retry')
        out = w.press(rid)
        rv = w.s.get_review(rid)
        assert not out.get('ok') and not out.get('retry') and rv['Status'] == 'superseded' and len(ran) == 2, (out, rv)
        assert json.loads(rv['FinalText'])['text'] == HIS and not w.drawn(rid)['ActRetry'], 'one Try again: then the failed card keeps his words and offers none'
        w.press(rid)
    assert len(ran) == 2, 'a third press ran nothing'


def test_try_again_is_gone_once_its_agent_has_set_up_what_goes_next(w):
    "One way on at a time: the card its agent raised after the failure is the one to press - the failed one never posts beside it."
    ran = []
    a, b, d = _far_side('linkedin_post', ran, PASSING['down'])
    with a, b, d:
        rid = w.act(w.write('linkedin_post'))
        assert w.press(rid, final_text=HIS).get('retry') and w.drawn(rid)['ActRetry'] == 1
        w.act(w.write('linkedin_post'))
        assert not w.drawn(rid)['ActRetry'] and not w.press(rid).get('ok') and len(ran) == 1


@pytest.mark.parametrize('why', sorted(REFUSALS))
def test_what_the_far_side_refused_offers_no_try_again_and_wakes_its_agent_once(w, why):
    ran = []
    a, b, d = _far_side('linkedin_post', ran, REFUSALS[why])
    with a, b, d:
        rid = w.act(w.write('linkedin_post'))
        out = w.press(rid, final_text=HIS)
    rv = w.s.get_review(rid)
    assert not out.get('ok') and not out.get('retry') and rv['Status'] == 'superseded' and not rv.get('ActRetry'), (out, rv)
    assert len(w.woken) == 1 and w.drawn(rid)['post']['text'] == HIS


# ── the same thing brought up again shows his version ───────────────────────────────────────────────────────────────────────────────────
def test_the_same_letter_saved_again_by_its_agent_leaves_his_version_standing(w):
    from taskuary import slots
    rid = slots.draft(w.s, w.tid, FILED, to='erin@northwind.example', subject='The scheduler', agent='assistant')['review_id']
    filed = w.s.get_review(rid)['DraftText']
    w.typed(rid, text=HIS)
    again = slots.draft(w.s, w.tid, FILED, to='erin@northwind.example', subject='The scheduler', agent='assistant')
    rv = w.s.get_review(rid)
    assert again.get('ok') and again['review_id'] == rid and 'replaced_the_owners_version' not in again, again
    assert rv['Status'] == 'pending' and rv['DraftText'] == filed and his_words(rv) == HIS, 'nothing changed: the card stands as he left it'
    sent = []; a, b = _mail(sent)
    with a, b: assert w.press(rid).get('ok')
    assert sent[0]['body'].strip() == HIS


def test_a_card_raised_again_as_it_was_carries_what_he_typed(w):
    "cardqueue.keep raises the same card again under his line - every column but what came of the old one: the same thing, so his words ride with it."
    rid = w.letter()
    w.typed(rid, text=HIS)
    assert his_words({k: v for k, v in w.s.get_review(rid).items() if k not in cardqueue.CAME_OF}) == HIS


# ── the thread moved under his Send ─────────────────────────────────────────────────────────────────────────────────────────────────────
def _thread(s):
    from taskuary import operations
    tid = s.create_task({'Title': 'The October numbers', 'Kind': 'reply', 'Status': 'open', 'Source': 'email'}, 'router')
    msg = lambda ext, at, body: s.add_message({'TaskId': tid, 'ExternalId': ext, 'ConversationId': 'conv-1', 'Channel': 'email', 'SourceName': 'alex@northwind.example',
                                               'Subject': 'October numbers', 'FromName': 'Erin Blake', 'FromEmail': 'erin@northwind.example', 'SentAt': at,
                                               'BodyText': body, 'Status': 'routed'})
    first = msg('m1', '2026-11-06 09:00:00', 'Could you send the October numbers?')
    rid = s.add_review({'TaskId': tid, 'MessageId': first, 'Kind': 'draft', 'Status': 'pending', 'DraftText': 'Here they are.', 'Reason': 'needs a reply'})
    s.pin_review_context(rid, first, operations.message_revision(s, tid))
    msg('m2', '2026-11-06 10:30:00', 'Actually - September too, please.')
    return rid


@pytest.mark.parametrize('edited', [True, False])
def test_a_draft_refreshed_under_his_send_is_said_only_where_one_was_written_and_never_over_his_words(edited):
    s = MemoryStore(); rid, sent = _thread(s), []
    def reply(*a, **k): sent.append(str((a, k))); return {'channel': 'email', 'to': ['erin@northwind.example'], 'cc': []}
    press = lambda **body: c.post(f'/api/reviews/{rid}/decide', headers=OWNER, json={'verb': 'approve', **body}).json()
    with mock.patch.object(server, 'store', s), mock.patch('taskuary.responder.draft_reply', return_value='Both months are attached.'),          mock.patch('taskuary.outbound.reply_to_message', side_effect=reply):
        out = press(final_text=HIS if edited else 'Here they are.')
        rv = s.get_review(rid)
        assert out.get('stale') and not sent, out
        if edited:
            assert rv['DraftText'] == 'Here they are.' and his_words(rv) == HIS, 'no draft was written over his words'
            assert 'Your words are kept' in out['send_error'] and 'refreshed it' not in out['send_error'], out['send_error']
            assert out['interrupt']['yours'] == HIS and 'Both months' in out['interrupt']['refreshed'], 'the new draft is offered beside his, his to take'
            assert press().get('ok') and HIS.split('\n')[0] in sent[0], sent
        else:
            assert 'Both months' in rv['DraftText'] and 'I refreshed it' in out['send_error'], (rv['DraftText'], out['send_error'])
