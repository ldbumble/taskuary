"""A task waiting on somebody else's answer, and what wakes it (the owner picked it, 2026-10-22: "wake a waiting task on
their reply").

An agent that needs a fact only a third party has says so - `taskuary --waiting-on "<who>"` - and the task records WHO
(`WaitingOn`, an address where one is known) and since when. It reads `waiting on them` on the rail until that person
writes on it. Their line wakes it: the wait ends, the task is the owner's news again, and a session the agent left is
offered Continue - which hands it their reply first (continuity.news_block, terminal.resume_seed). Their line goes to the
task's agent as it arrives, whatever triage made of it - the wait is why it matters (ingest.land_on; walk 18: a holding reply
read as fyi woke the task and reached no agent). Anybody else writing on the thread is news as it always was, and the wait stands.
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


def name_of(key: str, store=None, tid=None) -> str:
    """The waited-on person as the rail names a holder: 'Erin Blake' from 'erin blake', or by the task's own message from them (person) -
    else from erin.blake@northwind.example, or the chat a channel's id stands for, never the id itself."""
    from .processing_unread import holder_name
    k = str(key or '')
    if '@' not in k and ':' not in k: return k.title()
    m = next((m for m in reversed(store.list_messages(int(tid))) if _addr(m) == k), None) if store and tid else None
    return person(m, store) or (holder_name('person:' + k) if ':' not in k else readable(k))


# WHO SOMEBODY IS, BY NAME (the owner's live task, 2026-11-25: its header read "waiting for Whatsapp:133702382264527's input"): a chat's
# sender id stood where the person's name belongs - the rail, the header and a watch's line name them here
def person(m: dict, store=None) -> str:
    """The name a message's sender goes by: its FromName, else the name the owner saved for its chat - never an address or a chat's id
    (the poller's stand-in for a name). '' when it has none."""
    from . import wanames
    from .triage import person_name
    m, conv = m or {}, str((m or {}).get('ConversationId') or '')
    i = _addr(m).split(':', 1)[-1]
    saved = wanames.name_of(store, conv.split(':', 1)[1]) if store and conv.startswith('whatsapp:') else ''
    return next((person_name(n) for n in (m.get('FromName') or m.get('from_name'), saved) if person_name(n) and not wanames.bare(n, i)), '')


def readable(key: str) -> str:
    "An address or a chat with no name to it, as he would say it: the address, 'the WhatsApp chat'."
    from .senders import channel_name
    k = str(key or '')
    return f"the {channel_name(k.split(':', 1)[0])} chat" if ':' in k and '@' not in k else k


def word(waits_on: str, who: str = '') -> str:
    """THE ONE WORDING OF "WAITING FOR INPUT" (the owner, 2026-11-24): 'waiting for your input' while a task waits on him, "waiting for Erin's
    input" while it waits on somebody else - the rail, the header, the phone and the brief say it here (taskstate.standing). '' otherwise."""
    from . import lanes
    if waits_on == 'you': return lanes.word('blocked')
    if waits_on != 'them': return ''
    first = (str(who or '').split() or [''])[0]
    named = first and not any(c in first for c in '@:') and not str(who).startswith('the ')      # ...never an address, an id or a chat (readable)
    return lanes.word('theirs').replace('their', f"{first}'s", 1) if named else lanes.word('theirs')


def said(key: str, store=None, tid=None) -> str: return word('them', name_of(key, store, tid)) if key else ''


def on_them(store, t: dict) -> list:
    """Whose answer an open task waits for, as stored: [{who, what, since}] - the person an agent said only they can answer, or a mail he sent
    asked something (WaitingOn: declare, asks.watch_reply), and the answer a reply he sent asked for (asks.py's watch, nothing from them on its
    thread since). [] when nobody's. What taskstate.standing reads for 'them'. `answered`: the line they wrote since, which its agent has
    not yet read through to a turn's end (settle) - a holding "still working on it" is no end of the wait (walk 17, K2)."""
    from . import asks
    if not t or t.get('Status') in ('done', 'dropped'): return []
    out = [{'who': (n := name_of(k, store, t['TaskId'])), 'what': f'an answer from {n}', 'since': t.get('WaitingSince'), 'field': 'WaitingOn', 'key': k,
            'answered': _wrote_since(store, t['TaskId'], t.get('WaitingSince'), lambda m: is_them(k, m))} for k in (waiting(t),) if k]
    if t.get('AskedWatch') == 'reply' and (m := asks._waiting_on(store, t)):
        subj, who, a = ' '.join(str(m.get('Subject') or '').split())[:70], asks._who(m, first=False, store=store), asks._answer(store, t['TaskId'])
        out.append({'who': who, 'key': _addr(m), 'what': f"{who}'s answer to the reply sent {str(t.get('AskedWatchAt') or '')[:16]}" + (f' re "{subj}"' if subj else ''),
                    'since': t.get('AskedWatchAt'), 'field': 'AskedWatch', 'answered': a if a and str(a.get('CreatedAt') or '') > str(t.get('AskedWatchAt') or '') else None})
    return out


def _wrote_since(store, tid: int, at, theirs) -> dict | None:
    "Their newest line on the task since `at`, else None."
    rows = store._rows("SELECT * FROM message WHERE TaskId=? AND IFNULL(Direction,'in')<>'out' AND CreatedAt>? ORDER BY CreatedAt DESC LIMIT 20",
                       (int(tid), str(at or '')))
    return next((m for m in rows if theirs(m)), None)


def settle(store, tid: int) -> None:
    """THE WAIT ENDS WITH THE AGENT'S TURN THAT READ THEIR LINE (walk 17, K2): their reply wakes the agent and the task is its again, but only that
    turn's end closes the wait - a turn that still waits says so again (declare: the wait stands from then). A turn begun before their line
    never heard it, and settles nothing. Called at each turn's end (workerstate.record)."""
    t = store.get_task(int(tid)) or {}
    began = str((store.last_worker_event(int(tid), kinds=('working',)) or {}).get('CreatedAt') or '')
    for w in on_them(store, t):
        if not w['answered'] or str(w['answered'].get('CreatedAt') or '') > began: continue
        store._exec('UPDATE task SET ' + w['field'] + '=NULL WHERE TaskId=?', (int(tid),))


def is_them(key: str, msg: dict) -> bool:
    """Is this message from the person the task waits on?"""
    if not key or not msg: return False
    return _addr(msg) == key if '@' in key else _named(key, _name(msg))


def awaits(store, t: dict, msg: dict) -> bool:
    "Is this line from somebody task `t` waits on for an answer (on_them - the one list where it stands reads)?"
    return any(is_them(w['key'], msg) for w in on_them(store, t))


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
    """A line landed on the task. From the person it waits on: the task is open again and its agent's - the owner's news,
    with Continue leading where an agent left a session (processing_unread.card_for: `woke`) - and the Advisor reads it
    afresh. The wait itself ends with the agent's turn that read it (settle): a holding reply is no answer (walk 17, K2).
    From anyone else: nothing about the wait changes. True when it woke."""
    t = store.get_task(tid) or {}
    key = waiting(t)
    if not is_them(key, msg): return False
    store._exec('UPDATE task SET WokeMid=? WHERE TaskId=?', (mid, tid))
    if t.get('Status') == 'waiting': store.update_task(tid, {'Status': 'open'}, actor)
    who = msg.get('from_name') or msg.get('FromName') or _addr(msg) or 'they'
    store.add_comment(tid, actor, 'agent', f'{who} answered - it was waiting on them.')
    store.audit('task', tid, 'woke', actor, 'agent', {'who': key, 'message_id': mid})
    return True


def woke_by(task: dict, news: dict) -> bool:
    """Is this news the answer the task was waiting on? (the line that woke it, still the newest)"""
    return bool(task and news and task.get('WokeMid') and str(task['WokeMid']) == str(news.get('MessageId')))
