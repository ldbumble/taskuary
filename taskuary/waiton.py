"""A task waiting on somebody else's answer, and what wakes it (the owner picked it, 2026-10-22: "wake a waiting task on
their reply").

An agent that needs a fact only a third party has says so - `taskuary --waiting-on "<who>"` - and the task records WHO
(`WaitingOn`, an address where one is known) and since when. It reads `waiting on them` on the rail until that person
writes on it. Their line wakes it: the wait ends, the task is the owner's news again, and a session the agent left is
offered Continue - which hands it their reply first (continuity.news_block, terminal.resume_seed). Nothing starts by
itself: a live session hears it only under the owner's own answer_to_agent=auto, as any answer does (ingest._hand_to_agent).
Anybody else writing on the thread is news as it always was, and the wait stands.
"""
from datetime import datetime

from loguru import logger


def _now(): return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def _addr(m: dict) -> str: return str(m.get('FromEmail') or m.get('from_email') or '').strip().lower()
def _name(m: dict) -> str: return ' '.join(str(m.get('FromName') or m.get('from_name') or '').casefold().split())


def _named(want: str, name: str) -> bool:
    """'erin blake' names "Blake, Erin" and "Erin Blake at Northwind" - every word of it is a word of theirs."""
    from .triage import person_name
    have = set((person_name(name) or name).casefold().replace(',', ' ').split())
    return bool(want) and set(want.split()) <= have


def resolve(store, tid: int, who: str) -> str:
    """Who the task waits on, as one comparable key: an address, lowercased - else a name the task's own messages put
    an address to - else the name itself, which then matches by name only (a chat line often has no address)."""
    w = ' '.join(str(who or '').casefold().split())
    if not w: return ''
    if '@' in w: return w.strip('<>')
    hit = next((_addr(m) for m in reversed(store.list_messages(tid)) if _addr(m) and _named(w, _name(m))), '')
    return hit or w


def waiting(task: dict) -> str:
    """Who an open task waits on - '' when nobody (a closed task waits on nobody)."""
    t = task or {}
    return '' if t.get('Status') in ('done', 'dropped') else str(t.get('WaitingOn') or '')


def name_of(key: str) -> str:
    """The waited-on person as the rail names a holder: 'Erin Blake' from erin.blake@northwind.example or from 'erin blake'."""
    from .processing_unread import holder_name
    return holder_name('person:' + key) if '@' in key else key.title()


def is_them(key: str, msg: dict) -> bool:
    """Is this message from the person the task waits on?"""
    if not key or not msg: return False
    return _addr(msg) == key if '@' in key else _named(key, _name(msg))


def declare(store, tid: int, who: str, agent: str = 'agent') -> dict:
    """`taskuary --waiting-on`: the agent needs an answer only `who` has. Recorded on the task, which waits on them -
    never on a closed task, and never on the owner (asking the owner is the session's own prompt: AGENT.md)."""
    t = store.get_task(tid) or {}
    if not t: return {'ok': False, 'why': 'no such task'}
    if t.get('Status') in ('done', 'dropped'): return {'ok': False, 'why': 'this task is closed - nothing waits on it'}
    key = resolve(store, tid, who)
    if not key: return {'ok': False, 'why': 'say who it waits on - a name or an address'}
    me = str(store.get_setting('owner_email') or '').lower()
    if me and key == me: return {'ok': False, 'why': 'that is the owner - ask them here, in the session, and stay at the prompt'}
    store._exec('UPDATE task SET WaitingOn=?, WaitingSince=?, WokeMid=NULL WHERE TaskId=?', (key, _now(), tid))
    if t.get('Status') != 'waiting': store.update_task(tid, {'Status': 'waiting'}, agent or 'agent')
    store.add_comment(tid, agent or 'agent', 'agent', f'Waiting on {who.strip()} - it comes back when they answer.')
    store.audit('task', tid, 'waiting_on', agent or 'agent', 'agent', {'who': key})
    return {'ok': True, 'waiting_on': key}


def arrived(store, tid: int, msg: dict, mid: int = None, actor: str = 'router') -> bool:
    """A line landed on the task. From the person it waits on: the wait ends, the task is open again - the owner's news,
    with Continue leading where an agent left a session (processing_unread.card_for: `woke`) - and the Advisor reads it
    afresh. From anyone else: nothing about the wait changes. True when it woke."""
    t = store.get_task(tid) or {}
    key = waiting(t)
    if not is_them(key, msg): return False
    store._exec('UPDATE task SET WaitingOn=NULL, WokeMid=? WHERE TaskId=?', (mid, tid))
    if t.get('Status') == 'waiting': store.update_task(tid, {'Status': 'open'}, actor)
    who = msg.get('from_name') or msg.get('FromName') or _addr(msg) or 'they'
    store.add_comment(tid, actor, 'agent', f'{who} answered - it was waiting on them.')
    store.audit('task', tid, 'woke', actor, 'agent', {'who': key, 'message_id': mid})
    try:
        from . import advisor
        advisor.notice(store, 'reply.arrived', 'task', tid)
    except Exception as e: logger.debug(f'waiton: no advice on {tid} - {e}')
    return True


def woke_by(task: dict, news: dict) -> bool:
    """Is this news the answer the task was waiting on? (the line that woke it, still the newest)"""
    return bool(task and news and task.get('WokeMid') and str(task['WokeMid']) == str(news.get('MessageId')))
