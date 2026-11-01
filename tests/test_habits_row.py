"""ONE ADVISOR ROW FOR ALL HABITS (habits.py; the owner, 2026-11-01: "how many advisor ideas do i have now? it's too many. what does keep
it/remind me do here? doesn't make much sense"). A habit the Advisor is sure of is adopted, an unsure useful one asked - at most two a week -
and all of them sit on one row, "Learned 3 habits · 2 to check", each a sentence to the owner with its own Not right, or Adopt / No. The row
carries no task, agent, reminder or Not ours; it goes once nothing in it is open, and the habit cards of before fold into it. No {{...}}
ever reaches the screen. Invented Northwind people only."""
import json
from datetime import datetime
from unittest import mock
import pytest
from taskuary import assistant, concierge, funnel, habits, learn, learnedgraph as lg
from taskuary.store import MemoryStore

TODAY = datetime.now().strftime('%Y-%m-%d')


def _line(key, text, score, ev): return lg.fmt({'key': key, 'text': text, 'ev': ev, 'score': score, 'seen': TODAY, 'status': 'proposed'})
def _doc(*lines):
    return f"# LEARNED\n\n## What you care about\n\n## Proposed rules — your call\n{learn.PROP_START}\n" + '\n'.join(lines) + f"\n{learn.PROP_END}\n"
def _row(s): return s._one('SELECT * FROM idea WHERE Key=?', (habits.KEY,))
def _items(s): return json.loads(_row(s)['ActionJson'])['habits']
def _status(s): return {l['key']: l['status'] for l in lg.lines(s.get_doc('learned'))}

SURE = ('sso threads', '{{owner_first}} closes sign-in help threads directly; they need no drafted reply', 12, [f'rv{i}' for i in range(1, 9)])
SURE2 = ('board pack', '{{owner_first}} builds the board pack alone each month', 11, [f'rv{i}' for i in range(40, 47)])
ASKS = [(f'ask {n}', f'Forwarded FYI mail from team {n} needs no reply', 5, [f'rv{20 + 2 * n}', f'rv{21 + 2 * n}']) for n in range(4)]


@pytest.fixture
def s():
    s = MemoryStore(); s.set_setting('owner_name', 'Alex Doyle', 't'); s.set_setting('calendar_enabled', '0', 't')
    s.save_doc('learned', _doc(*(_line(*x) for x in (SURE, SURE2, *ASKS)), _line('weak one', 'Something seen twice', 2, ['rv90'])), 'reflect')
    return s


def test_every_habit_lands_on_one_row_said_with_the_owners_name_and_two_asked_a_week(s):
    out = habits.tick(s)
    assert out == {'adopted': ['sso threads', 'board pack'], 'asked': ['ask 0', 'ask 1']}, 'two asked a week; the rest wait'
    assert s._one("SELECT COUNT(*) n FROM idea WHERE Kind='habit'")['n'] == 1, 'one row, not one card a habit'
    r = _row(s)
    assert r['Text'] == 'Learned 2 habits · 2 to check'
    it = {i['line']: i for i in _items(s)}
    assert it['sso threads'] == {'line': 'sso threads', 'adopted': True,
                                 'say': 'Alex closes sign-in help threads directly; they need no drafted reply (seen 8 times).'}
    assert all('{{' not in i['say'] for i in it.values())
    st = _status(s)
    assert st['sso threads'] == st['board pack'] == 'live' and st['ask 2'] == st['ask 3'] == st['weak one'] == 'proposed'
    # ...a second reflection this week asks nothing more, and the waiting ones are still in LEARNED.md
    assert habits.tick(s) == {'adopted': [], 'asked': []} and _status(s)['ask 3'] == 'proposed'


def test_the_row_offers_no_task_agent_reminder_or_not_ours_and_no_whose_move(s):
    habits.tick(s)
    a = json.loads(_row(s)['ActionJson'])
    assert 'whose' not in a and 'suggest' not in a
    item = {'kind': 'idea', 'idea': _row(s)['IdeaId'], 'idea_kind': 'habit', 'key': f"idea:{_row(s)['IdeaId']}", 'action': a, 'title': _row(s)['Text']}
    assert [c['verb'] for c in concierge.chips_for(s, item)] == ['next']
    for v in ('task', 'agent', 'snooze', 'accept', 'rule'):
        with pytest.raises(ValueError): assistant.act(s, item['idea'], v)


def test_each_habit_is_answered_on_its_own_line_and_the_row_goes_when_nothing_is_open(s):
    habits.tick(s)
    iid = _row(s)['IdeaId']
    assistant.act(s, iid, 'habit', line='sso threads', yes=False)                 # Not right: taken back for good
    assert 'sso threads' not in {k for k, v in _status(s).items() if v == 'live'}
    assistant.act(s, iid, 'habit', line='ask 0', yes=True)                         # Adopt
    assert _status(s)['ask 0'] == 'live'
    assistant.act(s, iid, 'habit', line='ask 1', yes=False)                        # No: left proposed, never asked again
    assert _status(s)['ask 1'] == 'proposed' and _row(s)['Status'] == 'open' and _row(s)['Text'] == 'Learned 1 habit'
    with pytest.raises(ValueError): assistant.act(s, iid, 'habit', line='ask 1', yes=True)
    assert assistant.act(s, iid, 'seen')['open'] == 0 and _row(s)['Status'] == 'done', 'everything answered or seen: the row goes'
    assert habits.tick(s)['asked'] == [], 'a No and this week\'s two: nothing asked again'
    # ...a new adoption later brings the row back, with only the new one, in its own place on the rail
    s.save_doc('learned', s.get_doc('learned').replace(learn.PROP_END, _line('vendor', 'The month-end checklist is run alone', 10,
                                                                           [f'rv{i}' for i in range(60, 66)]) + '\n' + learn.PROP_END), 'reflect')
    assert habits.tick(s)['adopted'] == ['vendor']
    assert _row(s)['Status'] == 'open' and [i['line'] for i in _items(s)] == ['vendor'] and _row(s)['Text'] == 'Learned 1 habit'


def test_a_no_on_the_row_puts_the_asked_ones_down_for_good_and_a_line_gone_elsewhere_leaves_it(s):
    habits.tick(s)
    learn.adopt(s, 'ask 0', 'owner')                                             # adopted on the Learned page instead
    habits.draw(s)
    assert 'ask 0' not in [i['line'] for i in _items(s)]
    assistant.act(s, _row(s)['IdeaId'], 'dismiss')
    assert _row(s)['Status'] == 'dismissed' and habits._said(s)['ask 1']['state'] == 'no' and habits._said(s)['sso threads']['state'] == 'seen'


def test_the_model_says_each_habit_plainly_with_the_count_and_a_bad_answer_keeps_the_named_line(s):
    seen = {}
    def llm(system, user, **k):
        seen['user'] = user
        return json.dumps({'lines': ["You close sign-in help requests yourself, so I won't draft replies to them.", '{{owner_first}} oops',
                                     'You treat forwarded team 0 FYIs as read, so I would file them.', '']})
    habits.tick(s, llm)
    assert '1. ADOPTED: {{owner_first}} closes sign-in help threads' in seen['user'] and '3. ASKING: Forwarded FYI mail from team 0' in seen['user']
    it = {i['line']: i['say'] for i in _items(s)}
    assert it['sso threads'] == "You close sign-in help requests yourself, so I won't draft replies to them (seen 8 times)."
    assert it['board pack'] == 'Alex builds the board pack alone each month (seen 7 times).', 'a {{...}} answer is not used'
    assert it['ask 1'] == 'Forwarded FYI mail from team 1 needs no reply (seen 2 times).'
    assert habits.unphrased(s) == ['board pack', 'ask 1']
    # ...and a model that cannot answer leaves every line readable
    s2 = MemoryStore(); s2.save_doc('learned', _doc(_line(*SURE)), 'reflect')
    habits.tick(s2, lambda *a, **k: (_ for _ in ()).throw(RuntimeError('down')))
    assert _items(s2)[0]['say'] == 'The owner closes sign-in help threads directly; they need no drafted reply (seen 8 times).'


def test_the_habit_cards_of_before_fold_into_the_one_row(s):
    stamp = f'{TODAY} 08:00:00'
    for n, (k, adopted, st) in enumerate([('sso threads', True, 'open'), ('board pack', True, 'open'), ('ask 0', False, 'open'),
                                          ('ask 1', False, 'dismissed'), ('ask 2', False, 'snoozed')]):
        say = f'Adopted a habit of yours: "{{{{owner_first}}}} habit {n}"' if adopted else f'Is this a habit of yours: "habit {n}"?'
        s._exec('INSERT INTO idea (Key, Kind, Text, ActionJson, Status, FirstSeen, LastSaid, SaidCount) VALUES (?,?,?,?,?,?,?,1)',
                (f'idea:habit-{k.replace(" ", "-")}', 'habit', say, json.dumps({'type': 'habit', 'line': k, 'adopted': adopted, 'whose': 'the owner',
                                                                                 'suggest': 'Keep it'}), st, stamp, stamp))
    learn.adopt(s, 'sso threads', 'advisor-sure'); learn.adopt(s, 'board pack', 'advisor-sure')
    assert habits.fold(s) == 5
    assert s._one("SELECT COUNT(*) n FROM idea WHERE Key LIKE 'idea:habit-%' AND Status='open'")['n'] == 0
    assert [i['line'] for i in _items(s)] == ['sso threads', 'board pack', 'ask 0', 'ask 2'] and _row(s)['Text'] == 'Learned 2 habits · 2 to check'
    assert habits._said(s)['ask 1']['state'] == 'no', "the old No still stands"
    assert _items(s)[0]['say'] == 'Alex closes sign-in help threads directly; they need no drafted reply (seen 8 times).'
    assert habits.fold(s) == 0 and len(_items(s)) == 4, 'folding again changes nothing'


def test_no_idea_text_sent_to_the_client_carries_a_placeholder(s):
    s.upsert_idea({'key': 'idea:habit-legacy', 'kind': 'habit', 'text': 'Adopted a habit of yours: "{{owner_first}} files Payworth statements"',
                   'action': {'type': 'habit', 'line': 'sso threads', 'adopted': False}}, f'{TODAY} 08:00:00')
    habits.tick(s, lambda *a, **k: json.dumps({'lines': ['{{owner}} does it'] * 9}))
    with mock.patch('taskuary.terminal.live_sessions', return_value=[]):
        funnel.invalidate(); items = funnel.build(s, live_state=[])['items']; funnel.invalidate()
    rows = [i for i in items if i.get('kind') == 'idea']
    assert any(i.get('idea_kind') == 'habit' for i in rows)
    sent = json.dumps([concierge.card_for(i) for i in rows]) + json.dumps([assistant._public(i) for i in s.list_ideas('open')])
    assert '{{' not in sent, sent
