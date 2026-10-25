"""WHAT THE MEMORY LEARNS FROM: EPISODES (slice 2 of the memory redesign, 2026-10-25). Each is one thing the owner did, with its context -
who wrote, what they are to the owner, what it was about, what they did and how soon - built from rows already in the store and cited
by their ids. Navigation is never one, nor anything from personal mail, an agent or an auto-reply. The reflection reads them on a
schedule as well as on corrections, writes general facts about people and ways of working, and the code keeps the books: an id that
does not resolve, or a line resting on nothing the owner did, waits in Watching. Invented Northwind people only (tests/memory_cases.py)."""
import json
from datetime import datetime, timedelta
import pytest
from taskuary import episodes, learn, learned_cut, learnedlines
from tests import memory_cases as C


@pytest.fixture(scope='module')
def w(): return C.world()


def _since(days=61): return (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')


def test_an_episode_carries_who_what_they_are_what_was_done_and_how_soon(w):
    s, facts = w
    eps = {e[0]: e for e in episodes.build(s, _since())}
    erin = eps[f"msg{facts['erin_fast'][0]}"]
    assert erin[2] == 'erin@northwind.example' and '(your manager)' in erin[3] and 'replied 12 min after it arrived' in erin[3]
    renewal = next(e for e in eps.values() if e[0].startswith('fs') and 'payworth' in e[2])
    assert 'put it off to Fri' in renewal[3]
    hand = next(e for e in eps.values() if 'handed it to ray@northwind.example' in e[3])
    assert hand[0].startswith('task') and 'the sender on copy' in hand[3]
    assert any(e[0].startswith('sv') and 'the headcount sheet' in e[3] and 'gail@northwind.example' in e[3] for e in eps.values())
    assert any(e[0].startswith('rv') and 'edited the draft' in e[3] and 'paula@northwind.example' in e[3] for e in eps.values())
    assert sum(e[0].startswith('idea') and 'dismissed it' in e[3] for e in eps.values()) == 3


def test_navigation_personal_mail_agents_and_auto_replies_are_never_episodes(w):
    s, facts = w
    from taskuary import advisor
    t = s.create_task({'Title': 'A press', 'Status': 'open'}, 'owner')
    s._exec("INSERT INTO advice_press (Key,TargetKind,TargetId,Pressed,CreatedAt) VALUES (?,?,?,?,?)", (f'task:{t}', 'task', t, 'next', C._stamp(datetime.now())))
    s.save_source({'Channel': 'email', 'Address': 'alex.home@personal.example', 'Active': 1, 'ConfigJson': json.dumps({'personal': True})}, 'owner')
    m = s.add_message({'ExternalId': 'p1', 'ConversationId': 'email:p1', 'Channel': 'email', 'Subject': 'Dinner', 'FromEmail': 'friend@personal.example',
                       'SourceName': 'alex.home@personal.example', 'SentAt': C._stamp(datetime.now() - timedelta(hours=3)), 'BodyText': 'x', 'Status': 'filed'})
    s.add_message({'ExternalId': 'p2', 'ConversationId': 'email:p1', 'Channel': 'email', 'Subject': 'Re: Dinner', 'FromEmail': C.OWNER[1], 'Direction': 'out',
                   'SentAt': C._stamp(datetime.now() - timedelta(hours=2)), 'BodyText': 'x', 'Status': 'sent'})
    a = s.add_message({'ExternalId': 'a1', 'ConversationId': 'email:a1', 'Channel': 'email', 'Subject': 'Out of office', 'FromEmail': 'ray@northwind.example',
                       'SentAt': C._stamp(datetime.now() - timedelta(hours=3)), 'BodyText': 'x', 'Status': 'autoreply'})
    s.add_message({'ExternalId': 'a2', 'ConversationId': 'email:a1', 'Channel': 'email', 'Subject': 'Re', 'FromEmail': C.OWNER[1], 'Direction': 'out',
                   'SentAt': C._stamp(datetime.now() - timedelta(hours=1)), 'BodyText': 'x', 'Status': 'sent'})
    s.audit('task', t, 'handoff', 'agent:coding', 'agent', {'to': 'ray@northwind.example'})
    ids = {e[0] for e in episodes.build(s, _since())}
    assert not any(i.startswith('pr') for i in ids) and f'msg{m}' not in ids and f'msg{a}' not in ids and f'task{t}' not in ids


def test_the_block_is_capped_and_says_what_it_left_out(w):
    s, _ = w
    text, who, left = episodes.block(s, _since(), cap_n=10)
    assert len([l for l in text.splitlines() if not l.startswith('(')]) == 10 and left > 0 and f'({left} more episodes not shown)' in text
    assert 'erin@northwind.example' in who or 'payworth' in text


def test_reflection_fires_on_episodes_without_a_correction_at_most_daily_and_never_on_silence(w, monkeypatch):
    s, _ = w
    calls = []
    monkeypatch.setattr(learn, 'reflect', lambda store, llm=None: calls.append(1) or True)
    s.set_setting('learn_pending', '0', 'test'); s.set_setting('learn_last_reflect', _since(), 'test')
    assert learn.reflect_if_due(s) and calls == [1], 'enough new episodes is a reason by itself'
    s.set_setting('learn_last_reflect', datetime.now().isoformat(sep=' ', timespec='seconds'), 'test')
    assert not learn.reflect_if_due(s) and calls == [1], 'at most once a day, and nothing new since'
    s.set_setting('learn_last_reflect', _since(), 'test'); s.set_setting('learn_reflect_failed', learn._today(), 'test')
    assert not learn.reflect_if_due(s), 'never on a day a reflection failed'
    from taskuary.store import MemoryStore
    quiet = MemoryStore(); quiet.set_setting('learn_last_reflect', _since(2), 'test')
    assert not learn.reflect_if_due(quiet), 'never on silence'
    s.set_setting('learn_reflect_failed', '', 'test')


def _reflect(s, answer):
    return learn.reflect(s, llm=lambda system, user, **k: (_reflect.seen.append((system, user)), answer(s.get_doc('learned')))[1])
_reflect.seen = []


def test_the_reflection_reads_the_episodes_and_its_lines_are_kept_by_code(w):
    s, facts = w
    s.set_setting('learn_last_reflect', _since(), 'test')
    msgs = [f"msg{i}" for i in facts['erin_fast'][:3]]
    good = f"- Erin Blake (erin@northwind.example) is your manager; you answer her asks within the hour [s:4 | ev: {', '.join(msgs)} | seen: 2026-10-20]"
    bogus = '- Paula Vance (paula@northwind.example) is the CFO and always top priority [s:4 | ev: msg999999, out888888 | seen: 2026-10-20]'
    inbound = '- Sam Price (sam@vendor.example) is a key partner [s:4 | ev: | seen: 2026-10-20]'
    press = '- On asks from northwind.example, {{owner_first}} presses Reply (4 of 4) [s:5 | ev: pr1, pr2 | seen: 2026-10-20]'
    _reflect.seen.clear()
    assert _reflect(s, lambda d: d.replace(learned_cut.PEOPLE + '\n', learned_cut.PEOPLE + '\n' + '\n'.join((good, bogus, inbound, press)) + '\n', 1))
    system, user = _reflect.seen[-1]
    assert 'EPISODES' in user and 'replied 12 min after it arrived' in user and 'never a count of button presses' in system
    doc = s.get_doc('learned')
    people, watching = learned_cut.section(doc, learned_cut.PEOPLE), learn._block(doc, learn.HYP_START, learn.HYP_END)
    assert 'answer her asks within the hour' in people
    assert 'CFO' not in people and 'CFO' in watching, 'an id that does not resolve sends the line to Watching'
    assert 'key partner' not in people, 'a line resting on nothing the owner did is not in use'
    assert 'presses Reply' not in doc, 'a press count never lands'


def test_a_hide_line_goes_to_proposed_and_wrong_is_never_revived(w):
    s, facts = w
    rule = f"- Treat PhishGuard newsletters as fyi, never a task [s:4 | ev: msg{facts['erin_fast'][0]}, task1 | seen: 2026-10-20 | k: phishguard fyi]"
    doc = s.get_doc('learned')
    learnedlines.sync(s, doc, doc, 'reflect')
    s._exec("INSERT OR REPLACE INTO learned_line (Key, Reader, Text, Status) VALUES ('erin answer hour', 'people', 'x', 'wrong')")
    wrong = f"- Erin Blake (erin@northwind.example) gets an answer within the hour [s:5 | ev: msg{facts['erin_fast'][1]} | seen: 2026-10-20 | k: erin answer hour]"
    assert _reflect(s, lambda d: learn._put_block(d.replace(learned_cut.PEOPLE + '\n', learned_cut.PEOPLE + '\n' + wrong + '\n', 1), learn.PROP_START, learn.PROP_END, rule))
    doc = s.get_doc('learned')
    assert 'PhishGuard' in learn._block(doc, learn.PROP_START, learn.PROP_END) and 'gets an answer within the hour' not in doc


def test_a_fact_that_stopped_being_true_is_closed_not_deleted(w):
    s, facts = w
    old = f"- Gail Moreno (gail@northwind.example) is in Finance [s:4 | ev: sv{facts['gail_monday'][0]}, sv{facts['gail_monday'][1]} | seen: 2026-10-01 | k: gail finance]"
    s.save_doc('learned', s.get_doc('learned').replace(learned_cut.PEOPLE + '\n', learned_cut.PEOPLE + '\n' + old + '\n', 1), 'reflect')
    new = f"- Gail Moreno (gail@northwind.example) is in Ops now [s:2 | ev: sv{facts['gail_monday'][2]} | seen: 2026-10-20 | k: gail ops]"
    assert _reflect(s, lambda d: learn._put_block(d.replace(old + '\n', ''), learn.HYP_START, learn.HYP_END,
                                                  (learn._block(d, learn.HYP_START, learn.HYP_END) or '') + '\n' + new) + '\n<!-- closed: gail finance -->')
    r = learnedlines.row(s, 'gail finance')
    assert r['Status'] == 'closed' and r['ValidTo'] == learn._today() and 'closed' in [h['Action'] for h in s.learned_history('gail finance')]
    assert 'Ops now' in learn._block(s.get_doc('learned'), learn.HYP_START, learn.HYP_END) and '<!-- closed' not in s.get_doc('learned')


def test_people_lines_about_nobody_in_the_batch_are_held_back_and_restored_unjudged(w):
    s, _ = w
    far = '- Omar Keller (omar@northwind.example) gets the audit questions [s:4 | ev: task1, task2, task3 | seen: 2026-09-01 | k: omar audit]'
    s.save_doc('learned', s.get_doc('learned').replace(learned_cut.PEOPLE + '\n', learned_cut.PEOPLE + '\n' + far + '\n', 1), 'owner')
    _reflect.seen.clear()
    assert _reflect(s, lambda d: d)
    assert 'omar@northwind.example' not in _reflect.seen[-1][1].split('EPISODES')[0], 'not sent'
    assert 'gets the audit questions' in learned_cut.section(s.get_doc('learned'), learned_cut.PEOPLE), '...and not lost'


def test_no_brain_means_no_lines_and_no_error(w):
    from taskuary.store import MemoryStore
    s = MemoryStore()
    assert learn.reflect(s, llm=None) is False and learned_cut.for_reader(s, 'assistant') == ''


def test_a_promise_kept_every_week_is_an_episode_of_its_own():
    """Slice 5 (2026-10-25): the same person, the same weekday, three weeks or more - said once as the schedule it is."""
    from tests import memory_cases as C
    s, facts = C.world()
    eps = [e for e in episodes.build(s, '2000-01-01') if 'you keep a promise to gail@northwind.example on Mondays' in e[3]]
    assert len(eps) == 1 and '7 weeks' in eps[0][3]
    assert eps[0][0] in {f'sv{m}' for m in facts['gail_monday']}, 'it cites a promise it was counted from'


def test_a_machine_line_with_no_bullet_is_still_the_machines_and_kept_by_its_books(w):
    """The live yardstick (2026-10-25): a real model wrote its lines with no "- ". Untagged reads as the owner's own, in use at once -
    so a line that carries the tag is bulleted and goes through the same books as any machine line."""
    s, facts = w
    s.set_setting('learn_last_reflect', _since(), 'test')
    bare = '- Sam Price (sam@vendor.example) is a key partner [s:5 | ev: msg999999 | seen: 2026-10-20 | k: sam partner]'[2:]
    assert _reflect(s, lambda d: d.replace(learned_cut.PEOPLE + '\n', learned_cut.PEOPLE + '\n' + bare + '\n', 1))
    doc = s.get_doc('learned')
    assert 'key partner' not in learned_cut.section(doc, learned_cut.PEOPLE), 'it rests on nothing that resolves: it waits in Watching'
    assert learn._bullets('Erin [s:4 | ev: msg1 | seen: 2026-10-20]\nyours, untagged\n- tagged [s:2 | ev: msg1 | seen: 2026-10-20]') == \
        '- Erin [s:4 | ev: msg1 | seen: 2026-10-20]\nyours, untagged\n- tagged [s:2 | ev: msg1 | seen: 2026-10-20]'
