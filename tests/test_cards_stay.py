"""THE OWNER'S THREE RULES FOR WHAT STANDS IN A CHAT (2026-11-26, in his words), on the real roads - the store, the verdict door, the chat as
the page is served it - for a card alone, a run of cards under tabs and a bulk card:

1. "Things on chat don't go away." Nothing drawn in the chat disappears, hides or is taken off by itself - cards, tabs, words.
2. "No text after an approval card until the approval card is denied or approved, then agent moves on." While a card waits for his press
   nothing of the agent's is drawn after it, and his no on one card never wakes the agent while another still waits.
3. "Cards never just disappear." A card he pressed stays where it was, saying what came of it; one his line greyed stays greyed where it
   stood, and nothing Taskuary does by itself brings an old card back.

Invented people only (Alex Doyle, northwind.example)."""
import json
from unittest import mock

import pytest

from taskuary import bulkcard, cardqueue, chatlog, conversation, events, general, proposals, server, verdicts, workerstate as ws
from taskuary.store import MemoryStore

ASK = 'post about the portal on X, Reddit and LinkedIn'
POSTS = ('x_post', 'reddit_post', 'linkedin_post')


def task(s):
    tid = s.create_task({'Title': 'Announce the ledger portal', 'Kind': 'general', 'Status': 'in_progress', 'OriginBase': 'owner'}, 'owner')
    s.add_message({'TaskId': tid, 'ExternalId': 'own-1', 'Channel': 'own', 'Subject': 'Announce the ledger portal', 'FromName': 'You', 'BodyText': ASK, 'Status': 'routed'})
    return tid


def post(s, tid, t, then=None, batch=None):
    rid = s.add_review({'TaskId': tid, 'Kind': 'action', 'Status': 'pending', 'Origin': 'agent', 'Reason': 'the post you asked for', 'NextStep': then,
                        'DraftText': json.dumps({'action': 'run_tool', 'type': t, 'text': 'The ledger portal is live.'})})
    if batch: s._exec('UPDATE review SET Batch=? WHERE ReviewId=?', (batch, rid))
    return rid


def comment(s, tid, n, then=None):
    "A card whose press needs no network of its own here: a comment on an issue (proposals.execute stood in - woken_by)."
    return s.add_review({'TaskId': tid, 'Kind': 'action', 'Status': 'pending', 'Origin': 'agent', 'Reason': f'comment on issue {n}', 'NextStep': then,
                         'DraftText': json.dumps({'action': 'comment_issue', 'repo': 'northwind/ledger', 'number': n, 'body': 'Fixed in the next release.'})})


def carousel():
    "Three posts raised one after another: one card with a tab each (cardqueue.tabs)."
    s = MemoryStore(); tid = task(s)
    ids = [post(s, tid, t) for t in POSTS]
    says(s, tid, 'Three posts are set up.')
    return s, tid, ids


def bulk():
    "Three posts raised in one call with `items`: one bulk card, its rows sharing a Batch (bulkcard.py)."
    s = MemoryStore(); tid = task(s); key = bulkcard.new_key()
    ids = [post(s, tid, t, batch=key) for t in POSTS]
    says(s, tid, 'Three posts are on one card.')
    return s, tid, ids


def alone():
    s = MemoryStore(); tid = task(s)
    ids = [post(s, tid, 'linkedin_post')]
    says(s, tid, 'The post is set up.')
    return s, tid, ids


SHAPES = {'a card alone': alone, 'a run under tabs': carousel, 'a bulk card': bulk}


def says(s, tid, words): s.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, words)
def typed(s, tid, words, key):
    general.wait_line(s, tid, words, line_id=key); general.take_kept(s, tid)


def served(s, tid):
    cardqueue._SEEN.clear()
    return chatlog.serve(s, tid)


def rows(got):
    "The chat top to bottom, one entry a thing drawn: ('line' | 'turn' | 'note' ..., its id) and ('card', review, status) where the card stands."
    out = []
    for x in got['items']:
        if x['kind'] == 'card': out.append(('card', x['review'], x['status'])); continue
        out.append((x['kind'], x['id']))
        out += [('card', c['review'], c['status']) for c in x.get('cards') or []]
    return out


def under_a_waiting_card(got) -> list:
    "What is drawn after a card that still waits, this side of his next line - rule 2 says: nothing but cards."
    bad, waits = [], False
    for r in rows(got):
        if r[0] == 'line': waits = False
        elif r[0] == 'card': waits = waits or r[2] == 'pending'
        elif waits: bad.append(r)
    return bad


class Watch:
    "Every read of the chat through a timeline: what was ever drawn is still drawn (rule 1), and nothing stands under a waiting card (rule 2)."
    def __init__(self, s, tid): self.s, self.tid, self.seen = s, tid, set()
    def look(self, at=''):
        got = served(self.s, self.tid)
        now = {r[:2] for r in rows(got)}
        assert not self.seen - now, f'{at}: gone from the chat: {sorted(self.seen - now, key=str)}'
        assert not under_a_waiting_card(got), f'{at}: drawn under a card that still waits: {under_a_waiting_card(got)}'
        assert not conversation.flow_breaks(got), f'{at}: {conversation.flow_breaks(got)}'
        self.seen |= now
        return got


def woken_by(s, press):
    "Every wake of the task's agent while `press` runs, whatever road it would have taken (general.to_agent - the one road in)."
    woken = []
    with mock.patch.object(general, 'to_agent', lambda st, t, said='', actor='owner', heard=None, **k: woken.append(said) or (heard and heard('woke')) or 'woke'), \
         mock.patch.object(proposals, 'execute', return_value={'url': 'https://social.example/post/1'}):
        out = press()
    assert out['ok'], out
    return woken


# ── 1. THINGS ON CHAT DON'T GO AWAY ──────────────────────────────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize('shape', SHAPES)
def test_nothing_drawn_in_the_chat_goes_through_presses_later_words_his_line_and_a_keep(shape):
    s, tid, ids = SHAPES[shape](); w = Watch(s, tid)
    w.look('raised')
    woken_by(s, lambda: verdicts.decide(s, s.get_review(ids[0]), 'reject')); w.look('his no')
    says(s, tid, 'Noted.'); w.look('the agent says something after it')
    if len(ids) > 1: s.decide_review(ids[1], 'approved', None, 'owner'); w.look('his yes')
    says(s, tid, 'One went out.'); w.look('more words')
    typed(s, tid, 'Hold the rest - what is on my calendar?', 'l-cal'); w.look('his line')
    ws.record(s, tid, 'run1', 'turn_end', text='Nothing today.', source='api'); says(s, tid, 'Nothing today.'); w.look('the turn it started ended')
    for r in ids[2:]:
        assert proposals.passed(s.get_review(r)) and cardqueue.keep(s, tid, f'rv{r}', 'agent')['ok']
    w.look('its agent kept what still stands')


# ── 2. NO TEXT AFTER AN APPROVAL CARD UNTIL IT IS DENIED OR APPROVED, THEN THE AGENT MOVES ON ────────────────────────────────────────────

@pytest.mark.parametrize('shape', SHAPES)
def test_what_the_agent_says_while_a_card_waits_is_drawn_above_it_and_the_card_is_the_last_thing(shape):
    """His live app: "X draft declined. Reddit and LinkedIn are still available for review." stood UNDER the card still waiting. A later turn's
    words, a turn at work, a note - all above the card; it is the last thing until he presses it or writes."""
    s, tid, ids = SHAPES[shape](); w = Watch(s, tid)
    assert rows(w.look())[-1] == ('card', ids[0], 'pending')
    says(s, tid, 'One more thought on these.')
    got = rows(w.look('a later turn'))
    assert got[-1][0] == 'card' and ('card', ids[0], 'pending') in got and [r[0] for r in got].count('turn') == 2, got
    chatlog.put(s, tid, 'turn', 't:9', {'started': 2e9}, state='working')
    chatlog.step(s, tid, 'sid1', 'm-1', {'k': 'said', 'text': 'Looking at it again.'})
    with mock.patch.object(general, 'working', return_value=True): got = rows(w.look('a turn at work'))
    assert got[-1][0] == 'card' and got.index(('turn', 't:9')) < got.index(('card', ids[0], 'pending')), got
    chatlog.update(s, tid, 't:9', state='done')
    chatlog.put(s, tid, 'note', 'n-1', {'text': 'Taskuary checked back.'})
    assert rows(w.look('a note'))[-1][0] == 'card'
    # ...settled, it stays where he last saw it wait, and what is said now goes under it
    for r in ids: s.decide_review(r, 'rejected', None, 'owner')
    says(s, tid, 'All turned down.')
    got = rows(w.look('settled, and more words'))
    assert got[-1][0] == 'turn' and got.index(('note', 'n-1')) < got.index(('card', ids[0], 'rejected')), got
    assert rows(served(s, tid)) == got, 'the same on the next read: a refresh'


def test_a_card_that_waits_stays_above_his_line_and_the_turn_his_line_starts_is_under_the_line():
    "Only his own line may come after a waiting card, and nothing comes back above or below it by itself (the 11-25 ruling)."
    s, tid, (rid,) = alone(); w = Watch(s, tid)
    w.look()
    chatlog.put(s, tid, 'line', 'l-2', {'text': 'Leave the post for now - what is on my calendar?', 'at': 2e9})
    says(s, tid, 'Nothing today.')
    got = rows(w.look())
    assert got.index(('card', rid, 'pending')) < got.index(('line', 'l-2')) and got[-1][0] == 'turn', got


@pytest.mark.parametrize('shape', ['a run under tabs', 'a bulk card'])
def test_his_no_on_one_card_wakes_nobody_while_another_waits_and_is_told_as_his_with_the_next_turn(shape):
    """His live app: three posts, he wanted LinkedIn only; Dismiss on X, then on Reddit - each woke the agent. A no with a card still waiting
    wakes nobody; the agent is told both as his own (locked rule 2) with its next turn."""
    s, tid, (x, reddit, li) = SHAPES[shape]()
    served(s, tid)
    assert woken_by(s, lambda: verdicts.decide(s, s.get_review(x), 'reject')) == []
    assert woken_by(s, lambda: verdicts.decide(s, s.get_review(reddit), 'reject')) == []
    told = events.take(s, tid)[0]
    assert told.count('he turned it down') == 2 and s.get_review(li)['Status'] == 'pending', told
    assert not under_a_waiting_card(served(s, tid))


@pytest.mark.parametrize('shape', SHAPES)
def test_the_no_that_leaves_nothing_waiting_wakes_the_agent_once_to_move_on(shape):
    s, tid, ids = SHAPES[shape]()
    woken = [n for r in ids for n in woken_by(s, lambda: verdicts.decide(s, s.get_review(r), 'reject'))]
    assert len(woken) == 1, woken


def test_a_held_step_he_dismisses_wakes_nobody_while_a_card_still_waits_and_tells_it_once_when_none_does():
    "A step of the agent's own held for his press (a push) is a card like any other: his Dismiss beside a waiting post starts no turn."
    from taskuary import shellgate as sg, terminal as term
    s = MemoryStore(); tid = task(s)
    li = post(s, tid, 'linkedin_post')
    sg.check(s, tid, 'run1', 'git push origin master', 'Bash', r'C:\work\ledger')
    [held] = [r for r in s._rows("SELECT * FROM review WHERE TaskId=? AND Status='pending' ORDER BY ReviewId", (tid,)) if r['ReviewId'] != li]
    turns = []
    sess = mock.Mock(sid='run1', task_id=tid, alive=True, send_prompt=lambda text, **k: turns.append(text))
    with mock.patch('taskuary.workerstate._live', return_value=sess), mock.patch.object(term, 'stranger_now', return_value=''),          mock.patch.object(general, '_next_turn', lambda st, t, sess_, said, *a, **k: turns.append(said)):
        assert verdicts.decide(s, held, 'reject')['ok']
        assert turns == [] and 'NOT done' in events.take(s, tid)[0], 'his no on the push began a turn while the post still waited'
        assert verdicts.decide(s, s.get_review(li), 'reject')['ok']
    assert len(turns) == 1, turns


def test_a_yes_wakes_the_agent_only_for_its_own_next_step_and_only_once_nothing_waits():
    "Locked rule 3, through a run: a yes with no `then` wakes nobody; one with a `then` wakes it once - when no card of the task still waits."
    s = MemoryStore(); tid = task(s)
    li, x = comment(s, tid, 7, then='reply to Gail that it is fixed'), comment(s, tid, 8)
    says(s, tid, 'Two comments are set up.')
    assert woken_by(s, lambda: verdicts.decide(s, s.get_review(li), 'approve')) == [], 'X still waits'
    assert len(woken_by(s, lambda: verdicts.decide(s, s.get_review(x), 'approve'))) == 1, 'the row is over: its step after the press is owed once'


def test_a_bulk_run_with_a_row_left_out_wakes_nobody():
    s, tid, ids = bulk()
    with mock.patch.object(server, 'store', s): served(s, tid)
    key = s.get_review(ids[0])['Batch']
    with mock.patch.object(verdicts, 'decide', lambda st, rv, verb, **k: {'ok': bool(st.decide_review(rv['ReviewId'], 'approved', None, 'owner'))}):
        assert woken_by(s, lambda: {'ok': bool(bulkcard.run(s, key, skip=[ids[0]], wait=True))}) == []
    assert bulkcard.state(s, key)['left'] == 1 and [s.get_review(r)['Status'] for r in ids] == ['rejected', 'approved', 'approved']


# ── 3. CARDS NEVER JUST DISAPPEAR ────────────────────────────────────────────────────────────────────────────────────────────────────────

def test_a_pressed_tab_keeps_its_tab_and_says_what_came_of_it():
    """His live app: he approved one tab of two and the card slid on to the other - what he had approved "disappeared". The server's half:
    the pressed card is still a tab of the same card, settled, and its row says what the press did (the page keeps it shown - cardLine.lineAt)."""
    s = MemoryStore(); tid = task(s)
    routine, old = comment(s, tid, 7), post(s, tid, 'linkedin_post')
    says(s, tid, 'Two cards are set up.')
    before = served(s, tid)
    woken_by(s, lambda: verdicts.decide(s, s.get_review(routine), 'approve'))
    got = served(s, tid)
    [tabs] = got['queue']['runs']
    assert [(t['key'], t['done']) for t in tabs] == [(str(routine), True), (str(old), False)], tabs
    card = {r[1]: r[2] for r in rows(got) if r[0] == 'card'}
    assert card[routine] in ('approved', 'edited') and {r[:2] for r in rows(before)} <= {r[:2] for r in rows(got)}, card


@pytest.mark.parametrize('shape', SHAPES)
def test_a_card_his_line_greyed_stays_where_it_stood_and_nothing_brings_it_back_by_itself(shape):
    """His live app: his line asked for a routine change, then a new post; the turn raised the routine card - and at its end Taskuary raised the
    OLD post again beside it ("then it showed the old post not even the new one?"). "Nothing comes back automatically": the greyed card stays
    greyed where it stood, the turn's own card stands alone, and the old one stands again only where its agent keeps it."""
    s, tid, ids = SHAPES[shape](); w = Watch(s, tid)
    w.look()
    typed(s, tid, 'Change the Monday routine first, then redo the post.', 'l-redo')
    new = s.add_review({'TaskId': tid, 'Kind': 'action', 'Status': 'pending', 'Origin': 'agent', 'Reason': 'change the Monday routine',
                        'DraftText': json.dumps({'action': 'save_routine', 'name': 'Monday numbers', 'what': 'Change the routine'})})
    ws.record(s, tid, 'run1', 'turn_end', text='The routine change is set up; the post redo follows your approval.', source='api')
    says(s, tid, 'The routine change is set up; the post redo follows your approval.')
    got = rows(w.look('the turn ended'))
    waiting = [r['ReviewId'] for r in s._rows("SELECT ReviewId FROM review WHERE TaskId=? AND Status='pending'", (tid,))]
    assert waiting == [new], 'an old card was raised again by itself'
    assert all(('card', r, 'passed') in got for r in ids[:1]) and got.index(('card', ids[0], 'passed')) < got.index(('line', 'l-redo')), got
    # ...its agent judges the old one still right: kept, it stands again under his line, the greyed one still where it stood
    assert cardqueue.keep(s, tid, ' + '.join(f'rv{r}' for r in ids), 'agent')['ok']
    got = rows(w.look('kept'))
    again = cardqueue.again_of(s, ids[0])
    assert ('card', ids[0], 'passed') in got and s.get_review(again)['Status'] == 'pending'
