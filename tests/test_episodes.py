"""WHAT THE MEMORY LEARNS FROM: EPISODES (slice 2 of the memory redesign, 2026-10-25). Each is one thing the owner did, with its context -
who wrote, what they are to the owner, what it was about, what they did and how soon - built from rows already in the store and cited
by their ids. Navigation is never one, nor anything from personal mail, an agent or an auto-reply. The reflection reads them on a
schedule as well as on corrections, writes general facts about people and ways of working, and the code keeps the books: an id that
does not resolve, or a line resting on nothing the owner did, waits in Watching. Invented Northwind people only (tests/memory_cases.py)."""
import json
from datetime import datetime, timedelta
import pytest
from taskuary import episodes, learning
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
    t = s.create_task({'Title': 'An agent hand-off', 'Status': 'open'}, 'owner')
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
    assert f'msg{m}' not in ids and f'msg{a}' not in ids and f'task{t}' not in ids


def test_the_block_is_capped_and_says_what_it_left_out(w):
    s, _ = w
    text, who, left = episodes.block(s, _since(), cap_n=10)
    assert len([l for l in text.splitlines() if not l.startswith('(')]) == 10 and left > 0 and f'({left} more episodes not shown)' in text
    assert 'erin@northwind.example' in who or 'payworth' in text




def test_a_promise_kept_every_week_is_an_episode_of_its_own():
    """Slice 5 (2026-10-25): the same person, the same weekday, three weeks or more - said once as the schedule it is."""
    from tests import memory_cases as C
    s, facts = C.world()
    eps = [e for e in episodes.build(s, '2000-01-01') if 'you keep a promise to gail@northwind.example on Mondays' in e[3]]
    assert len(eps) == 1 and '7 weeks' in eps[0][3]
    assert eps[0][0] in {f'sv{m}' for m in facts['gail_monday']}, 'it cites a promise it was counted from'


# ── WHAT THE MEMORY LEARNS FROM IS THE OWNER (the owner, 2026-11-13: "memory is broken 2 ways: it saves some random how quickly we respond,
# which is just useless, and it saves information about the user from the agents' takeaway and not what [the user] writes to the hub") ──
def test_the_note_a_task_was_closed_with_is_read_in_the_owners_words_answered_or_not():
    """THE LIVE SHAPE (the audit, 2026-11-13): Close with a note is the one place the owner says WHY a task ends. The note was kept on the
    task and no episode carried it: unanswered, the memory read a bare "closed it without replying"; answered first, nothing at all."""
    from taskuary.store import MemoryStore
    from taskuary.testing import Factory
    s = MemoryStore(); f = Factory(s)
    s.set_setting('owner_email', 'alex@northwind.example', 'test')
    def closed(title, who, note, answered=False):
        tid = f.task(title=title, kind='general')
        f.message(task_id=tid, subject=title, body='Can you look at this?', from_name=who.split('@')[0].title(), from_email=who,
                  conversation_id=f'email:{title}', sent_at=C._stamp(datetime.now() - timedelta(hours=3)))
        if answered: s.add_message({'TaskId': tid, 'ExternalId': f'out-{tid}', 'ConversationId': f'email:{title}', 'Channel': 'email', 'Direction': 'out',
                                    'FromName': 'You', 'FromEmail': 'alex@northwind.example', 'Subject': f'Re: {title}', 'BodyText': 'Done.',
                                    'SentAt': C._stamp(datetime.now() - timedelta(hours=1)), 'Status': 'context'})
        if note: s.add_comment(tid, 'owner', 'human', f'Closed out: {note}')          # as the one close door writes it (server task.complete)
        s.update_task(tid, {'Status': 'done'}, 'owner')
        return f'task{tid}'
    renewal = closed('Payworth renewal', 'renewals@vendor.example', 'Ray owns vendor renewals, not me')
    badge = closed('Badge for the new starter', 'gail@northwind.example', 'Told her in the hallway - facilities does these', answered=True)
    plain = closed('Seat count', 'omar@northwind.example', '')
    done = closed('Parking pass', 'paula@northwind.example', '', answered=True)
    eps = {e[0]: e[3] for e in episodes.build(s, _since())}
    assert 'closed it without replying, and wrote: "Ray owns vendor renewals, not me"' in eps[renewal]
    assert 'you: closed it, and wrote: "Told her in the hallway - facilities does these"' in eps[badge], 'answered first: the note is still his word'
    assert eps[plain].endswith('you: closed it without replying') and done not in eps, 'no note: as before'
    assert all(episodes.is_act(k) for k in (renewal, badge)), 'a line may rest on it'


def test_a_draft_somebody_else_put_down_is_no_verdict_of_the_owners_and_a_close_is_one_episode():
    """THE LIVE SHAPE (the audit, 2026-11-13): an agent says no reply is owed, and the owner marks another task done over its waiting draft.
    The reflection read the first under DRAFT VERDICTS with "owner's note: the agent said no reply is owed", and the second twice - "sent
    no reply" and "closed it without replying" - with Taskuary's own "the owner closed the task" as his note."""
    from taskuary import concierge
    from taskuary.store import MemoryStore
    from taskuary.testing import Factory
    s = MemoryStore(); f = Factory(s)
    s.set_setting('owner_email', 'alex@northwind.example', 'test')
    def owed(title, who):
        tid = f.task(title=title, kind='general')
        mid = f.message(task_id=tid, subject=title, body='Can you look at this?', from_name='Someone', from_email=who, conversation_id=f'email:{title}',
                        sent_at=C._stamp(datetime.now() - timedelta(hours=3)))
        return tid, s.add_review({'TaskId': tid, 'MessageId': mid, 'Kind': 'draft_reply', 'Status': 'pending', 'Channel': 'email', 'DraftText': 'Hi, on it. Alex'})
    _, by_agent = owed('Seat count', 'omar@northwind.example')
    s.decide_review(by_agent, 'no_reply', None, 'agent', 'the agent said no reply is owed')
    closed, with_it = owed('Parking pass', 'paula@northwind.example')
    assert concierge.close_task(s, closed, 'owner')
    _, his = owed('Badge for the new starter', 'gail@northwind.example')
    s.decide_review(his, 'rejected', None, 'owner', 'facilities answers these')
    assert [r['ReviewId'] for r in episodes.own_verdicts(s, _since())] == [his]
    eps = [e[0] for e in episodes.build(s, _since())]
    assert f'rv{by_agent}' not in eps and f'rv{with_it}' not in eps and eps.count(f'task{closed}') == 1 and f'rv{his}' in eps
    said = learning.gather(s, _since())
    assert 'the agent said no reply is owed' not in said and concierge.CLOSED_TASK not in said
    assert "owner's note: facilities answers these" in said and 'gail@northwind.example' in said
