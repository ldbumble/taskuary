"""WHAT A TASK'S AGENT IS TOLD BETWEEN TURNS: THE EVENTS SINCE ITS CURSOR (design review change 2, 2026-11-23). Each fact is written ONCE,
where it happens - a message put on the task (store.arrive), his line taken by a turn (general.take_kept), a card's state (store._poke_review),
a press of his (store.audit), Taskuary's own note (general.to_agent), a turn that stopped before it answered - and every road reads them the
same way: the turn takes what is past its cursor (`take`), `render` says each in one fixed shape, and the cursor moves once the agent has
them (`commit`). Nothing is rebuilt from the stores each turn, so nothing is said twice, and nothing stale is said at all: a fact that
changed is a new event, never an old block read again.

One agent per task, so one cursor per task. A conversation said afresh is told the task in full by its brief - the messages and lines are
in it - and the rest of what is past the cursor (cards, presses, notes) with it.

A card is the answer to the call that raised it: the call's own result says it is up, so a conversation that made the call hears only what
became of it - pressed, sent, failed, greyed - by the card's id, once (`render`, `own`)."""
import json, logging, threading, time

logger = logging.getLogger(__name__)

KINDS = ('message', 'said', 'card', 'press', 'note', 'stopped')
IN_BRIEF = ('message', 'said')        # ...what a fresh conversation's brief already carries in full (general.prompt_parts)
HEAD = 'NEW ON THIS TASK, OLDEST FIRST:'


_NS, _NS_LOCK = [0], threading.Lock()
def _ns() -> int:
    "A clock-made key never made twice: Windows' clock ticks in milliseconds, and two notes in one tick were one key - the second dropped."
    with _NS_LOCK: _NS[0] = max(time.time_ns(), _NS[0] + 1); return _NS[0]


def add(store, tid: int, kind: str, key: str = None, **body) -> int | None:
    "Write one event on task `tid` -> its id, or None where `key` was written already (each fact once)."
    if kind not in KINDS: raise ValueError(f'not an event kind: {kind!r}')
    key = key or f'{kind}:{_ns()}'
    with store.lock:
        cur = store.cx.execute('INSERT OR IGNORE INTO event (TaskId, At, Kind, Key, Body) VALUES (?,?,?,?,?)',
                               (int(tid), time.time(), kind, key, json.dumps(body, default=str)))
        store.cx.commit()
    return cur.lastrowid if cur.rowcount else None


def _safe(f):
    "A writer never breaks the act it records: the act is the fact, its event is how the agent hears of it."
    def go(*a, **k):
        try: return f(*a, **k)
        except Exception as e: logger.warning(f'events: {f.__name__} not written - {e}')
    return go


def top(store, tid: int) -> int:
    return (store._one('SELECT MAX(Id) AS m FROM event WHERE TaskId=?', (int(tid),)) or {}).get('m') or 0


def _cursor(store, tid: int) -> tuple[int, set]:
    r = store._one('SELECT Upto, Told FROM event_cursor WHERE TaskId=?', (int(tid),))
    return (r['Upto'], set(json.loads(r['Told'] or '[]'))) if r else (0, set())


def _body(r: dict) -> dict:
    try: b = json.loads(r.get('Body') or '{}')
    except ValueError: b = {}
    return b if isinstance(b, dict) else {}
def _row(r: dict) -> dict: return {**_body(r), 'id': r['Id'], 'at': r['At'], 'kind': r['Kind']}


def pending(store, tid: int, upto: int = None) -> list:
    "The events on task `tid` past its cursor (and up to `upto`) that no turn was handed yet, oldest first."
    at, told = _cursor(store, tid)
    rows = store._rows('SELECT * FROM event WHERE TaskId=? AND Id>? AND Id<=? ORDER BY Id', (int(tid), at, upto if upto is not None else 2 ** 62))
    held = _held(store, tid, rows)
    return [_row(r) for r in rows if r['Id'] not in told and r['Id'] not in held]


def _held(store, tid: int, rows) -> set:
    "The ids of the message events among `rows` whose message no agent is handed until he trusts its sender (origin.withheld)."
    from .origin import withheld
    if not (w := withheld(store, tid) if any(r['Kind'] == 'message' for r in rows) else None): return set()
    return {r['Id'] for r in rows if r['Kind'] == 'message' and _body(r).get('mid') in w}


def commit(store, tid: int, upto: int = None, ids=()) -> None:
    """The agent has them: the cursor moves to `upto`, and `ids` past it - handed to a turn at work (steer) - are kept as told."""
    at, told = _cursor(store, tid)
    # ...A HELD LINE KEEPS ITS PLACE (origin.withheld): the cursor stops before it and what the turn was handed past it is kept as told, so his
    # Trust hands it to the next turn, once
    if upto and upto > at and (held := _held(store, tid, rows := store._rows('SELECT Id, Kind, Body FROM event WHERE TaskId=? AND Id>? AND Id<=?', (int(tid), at, upto)))):
        ids, upto = {*ids, *(r['Id'] for r in rows if r['Id'] not in held)}, min(held) - 1
    at = max(at, upto or 0); told = {i for i in told | set(ids) if i > at}
    with store.lock:
        store.cx.execute('INSERT INTO event_cursor (TaskId, Upto, Told) VALUES (?,?,?) ON CONFLICT(TaskId) DO UPDATE SET Upto=excluded.Upto, Told=excluded.Told',
                         (int(tid), at, json.dumps(sorted(told))))
        store.cx.commit()


def take(store, tid: int, fresh: bool = False, carried=(), upto: int = None, skip=()) -> tuple[str, int]:
    """(what this turn is told, the id to commit once the agent has it). `fresh`: a conversation said afresh, whose brief carries the
    messages and his lines. `carried`: message ids the turn's own words carry already (a passed-in mail's brief). `skip`: kinds the road
    hands over by words of its own (the waiting room's: his lines, the mail it passes in) - passed by, never said twice."""
    upto = top(store, tid) if upto is None else upto
    skip = set(skip) | (set(IN_BRIEF) if fresh else set())
    rows = [e for e in pending(store, tid, upto) if e['kind'] not in skip and not (e['kind'] == 'message' and e.get('mid') in set(carried))]
    return render(rows[-FRESH_N:] if fresh else rows, fresh), upto
FRESH_N = 40                    # ...a brief said afresh carries the newest of them: the task's own record holds the rest


def messages_after(store, tid: int, upto: int) -> set:
    "The message ids put on task `tid` after event `upto`: the next turn's to hear, never in this turn's brief as well."
    return {_row(r).get('mid') for r in store._rows("SELECT * FROM event WHERE TaskId=? AND Kind='message' AND Id>?", (int(tid), upto))}


# ---- the one renderer: each event in its fixed shape, plain fact -------------------------------------------------------------------------

def _clock(at) -> str:
    from datetime import datetime
    return datetime.fromtimestamp(float(at)).strftime('%H:%M')


def _files(fs) -> str:
    from .general import with_files          # ...the one block a prompt names files in, so no door names them again (general.prompt_files)
    return with_files('', [str(f) for f in fs or ()])


def _flat(x, n: int) -> str:
    t = ' '.join(str(x or '').split())
    return t if len(t) <= n else t[:n - 1] + '…'


def _message(e) -> str:
    from .terminal import fence, named
    where = ', '.join(x for x in (f"by {e['channel']}" if e.get('channel') else '', f"subject {fence(_flat(e['subject'], 140))}" if e.get('subject') else '') if x)
    if e.get('own'): head = f"The owner's own message on the thread, sent outside Taskuary (m{e.get('mid')}{', ' + where if where else ''})"
    elif e.get('mine'): head = f"The owner's ask (m{e.get('mid')})"
    else: head = f"Message from {named(e.get('who'), e.get('addr')) or 'someone'} (m{e.get('mid')}{', ' + where if where else ''})"
    if e.get('elsewhere'): head += f", filed on {e['elsewhere']}"
    text = str(e.get('text') or '')
    from .general import reply_line
    return f"{head}:\n" + ''.join(f'{r}\n' for r in [reply_line(e.get('parent'))] if r) + \
        f"{text if e.get('own') or e.get('mine') else fence(text)}" + _files(e.get('files'))


CARD = {'approved': 'he approved it', 'edited': 'he changed your words, then approved it', 'rejected': 'he turned it down',
        'closed_unsent': 'he closed it without sending', 'no_reply': 'he said no reply is needed'}


def _card(e) -> str:
    "One card's new state, as code wrote it: raised, pressed and what came of it, greyed, back."
    s, d, err, note, by = e.get('status'), e.get('delivery') or '', _flat(e.get('error'), 240), _flat(e.get('note'), 200), e.get('by') or ''
    head = f"Card rv{e.get('rid')}" + (f" ({e['what']})" if e.get('what') else '')
    if err and e.get('cut') and s in ('pending', 'superseded'): said = 'Taskuary restarted while his press ran - it may have been done'
    elif err and s in ('pending', 'superseded'): said = f'he pressed it and it failed ({err}) - nothing of it was done' + ('' if s == 'superseded' else '; the card waits for his press')
    elif s == 'pending' and d == 'failed': said = f"he pressed Send and it did not go ({_flat(e.get('reason'), 200) or 'no reason given'}); the card waits for his press"
    elif s == 'pending' and d == 'unknown': said = f"he pressed Send and it may have gone ({_flat(e.get('reason'), 200) or 'no reason given'}) - not known"
    elif s == 'pending': said = ('up for his press again' if e.get('back') else 'up for his press') + (f": {e['words']}" if e.get('words') else '')
    elif s in ('approved', 'edited'):
        said = ('he changed your words and sent it' if s == 'edited' else 'he pressed Send - it was sent') if d == 'sent' else \
               f'{CARD[s]} - it was done' if e.get('act') else CARD[s]
        if d == 'sent' and e.get('to'): said += f" to {', '.join(e['to'])}" + (f", copying {', '.join(e['cc'])}" if e.get('cc') else '')
        if e.get('answers'): said = f"he answered:\n{e['answers']}"
        if e.get('result'): said += f" ({_flat(e['result'], 300)})"
        if e.get('final'): said += f"; what went: \"{_flat(e['final'], 600)}\""
    elif s in CARD: said = CARD[s]
    elif s == 'superseded': said = (e.get('until') or 'greyed, it will not go') + (f' ({note})' if note else '')
    else: said = s or 'changed'
    if s == 'pending' and d in ('failed', 'unknown') and e.get('final'): said += f"; what he pressed Send on: \"{_flat(e['final'], 600)}\""
    return f'{head}: {said}' + (f' - by {by}' if by and by not in ('owner', 'you', 'taskuary', 'system') and s != 'pending' else '')


def _one(e) -> str:
    k = e['kind']
    if k == 'message': return _message(e)
    if k == 'said': return f"The owner wrote in this chat:\n{e.get('text') or ''}" + _files(e.get('files'))
    if k == 'card': return _card(e)
    if k == 'press': return f"The owner {e.get('what') or 'pressed a button'}."
    if k == 'stopped':
        return '\n'.join(x for x in (f"Your last turn stopped before it answered ({_flat(e.get('why'), 300)}); what it was answering is still owed.",
                                     f"What it did before it stopped:\n{e['did']}" if e.get('did') else '', e.get('made') or '') if x)
    return f"Taskuary: {e.get('text') or ''}"


def render(rows: list, fresh: bool = False) -> str:
    """The events, each in its fixed shape under its time - '' with none. A card the agent raised itself in its turn is that tool call's own
    answer, so a conversation that made the call hears only what became of it; one said afresh hears it raised too."""
    rows = [e for e in rows if fresh or not (e['kind'] == 'card' and e.get('own') and e.get('status') in ('pending', 'superseded') and not e.get('back') and not e.get('error'))]
    if not rows: return ''
    return '\n\n'.join([HEAD, *(f"[{_clock(e['at'])}] {_one(e)}" for e in rows)])


# ---- the writers, each called where its fact happens ---------------------------------------------------------------------------------------

def _mail_shown(store, m: dict) -> dict:
    "What the chat shows of it (general.mail_row): its words, and the line it answers or quotes."
    from .general import mail_row
    try: return mail_row(store, m)
    except Exception: return {'words': str(m.get('OwnText') or m.get('BodyText') or m.get('Subject') or '')}


@_safe
def arrived(store, mid: int, tid: int = None) -> None:
    """A message was put on task `tid` (store.arrive, the one writer of message.TaskId, or stored on it): one event on it - and, for the
    owner's own reply, one on every other open task on the same thread, which hears it as theirs too. A reply Taskuary sent on his press,
    come back from his Sent folder, is its card's event already (general.went_from_here): no message event."""
    m = store.get_message(mid)
    if not m or m.get('Status') in ('history', 'skipped') or str(m.get('Channel') or '') == 'report': return
    own = str(m.get('Direction') or 'in') == 'out' or m.get('Status') == 'context'
    from .general import went_from_here
    ours = lambda t: own and went_from_here(store, t)(m)
    files = [a.get('Path') or a.get('Name') for a in store.list_attachments(mid) or [] if a.get('Path') or a.get('Name')]
    from .outbox import asked
    from .wrapup import from_owner
    mine = not own and from_owner(store, m)              # ...his ask, filed as the task's own row (New, the phone): his words, never fenced
    body = dict(mid=mid, who=asked(m) or m.get('FromName') or '', addr='' if asked(m) else m.get('FromEmail') or '', channel=m.get('Channel') or '', own=own, mine=mine,
                subject=str(m.get('Subject') or '').strip() if str(m.get('Channel') or 'email').lower() == 'email' else '',
                text=(r := _mail_shown(store, m))['words'][:3000], files=files[:8], **({'parent': r['reply']} if r.get('reply') else {}))
    if tid and not ours(tid): add(store, tid, 'message', f'message:{mid}', **body)
    if own and m.get('ConversationId'):
        from .store import task_ref
        for r in store._rows("SELECT DISTINCT t.TaskId FROM message t JOIN task k ON k.TaskId=t.TaskId WHERE t.ConversationId=? AND t.TaskId<>IFNULL(?,0) "
                             "AND k.Status NOT IN ('done','dropped')", (m['ConversationId'], tid)):
            if not ours(r['TaskId']) and not (tid and ours(tid)):
                add(store, r['TaskId'], 'message', f'message:{mid}', **body, **({'elsewhere': task_ref(tid)} if tid else {}))


@_safe
def said(store, tid: int, lines) -> None:
    "His lines a turn takes (general.take_kept): each one event, by the line's own comment id."
    for x in lines:
        if str(x.get('text') or '').strip() or x.get('files'):
            add(store, tid, 'said', f"said:{x.get('id') or x.get('CommentId') or _ns()}", text=str(x.get('text') or ''), files=list(x.get('files') or []))


@_safe
def card(store, r: dict) -> None:
    """A card's state as the store just wrote it (store._poke_review - every road that raises, presses, sends, greys or fails a card goes
    through there): one event per state it reaches, a state being what its event says - a draft rewritten in place, or a line added under
    its error, is the same state. A send still going out is no state yet."""
    if not r or not r.get('TaskId') or not r.get('ReviewId'): return
    r = store.get_review(r['ReviewId']) or r
    if r.get('DeliveryState') == 'sending' or r.get('Status') == 'held': return
    if r.get('Status') == 'pending' and r.get('Kind') != 'action' and not str(r.get('DraftText') or '').strip(): return     # ...a reply nobody wrote yet is no card
    tid, rid = int(r['TaskId']), int(r['ReviewId'])
    from . import general, proposals
    from .general import ACT_CUT, AGENT_TOLD
    olds = [json.loads(x['Body']) for x in store._rows("SELECT Body FROM event WHERE TaskId=? AND Kind='card' AND Key LIKE ? ORDER BY Id", (tid, f'card:{rid}:%'))]
    try:
        from .cardqueue import what, _words
        label = what(store, {'rids': [rid], 'rows': [r]}, True)
    except Exception: label = ''
    err = str(r.get('ActError') or '').replace(AGENT_TOLD, '').strip()
    # ...HIS WORDS, where he changed the card's before pressing: what went, or what he pressed Send on that did not go
    went, snap = str(r.get('FinalText') or ''), (store._one('SELECT Text FROM draft_snapshot WHERE ReviewId=? ORDER BY Id DESC LIMIT 1', (rid,)) or {}).get('Text')
    pressed = r.get('Status') in ('approved', 'edited') or r.get('DeliveryState') in general.NOT_GONE
    final = went if r.get('Kind') != 'action' and pressed and went.split() and (snap.split() != went.split() if snap else r.get('Status') == 'edited') else ''
    try: result = (json.loads(r.get('FinalText') or '{}') or {}).get('result') if r.get('Kind') == 'action' else None
    except (TypeError, ValueError, AttributeError): result = None
    answers = proposals.answered(result)             # ...a questions card's: each answer whole, never a cut of its record
    body = dict(rid=rid, act=r.get('Kind') == 'action', what=label, status=r.get('Status'), delivery=r.get('DeliveryState'), error=err.rstrip('. '),
                cut=err.startswith(ACT_CUT), note=r.get('DecideNote'), reason=r.get('Reason') if r.get('DeliveryState') in general.NOT_GONE else '',
                by=r.get('DecidedBy'), final=final, result=str(result)[:300] if result and not answers else '', **({'answers': answers} if answers else {}), words=_words(r) if r.get('Status') == 'pending' else '',
                back=bool(olds) and r.get('Status') == 'pending' and not r.get('DeliveryState') and not err, **_went(r),
                **({'until': proposals.UNTIL} if proposals.comes_back(store, r) else {}))
    if olds and _card(olds[-1]) == _card(body): return
    # ...ITS OWN CALL'S, where a turn at work wrote it - NEVER WHAT AN INPUT GREYED (walk 25, 2026-11-26: his press marks the task at work before
    # his line is heard, so the greying that line did was filed as the turn's own and never said - it answered "waiting for your Send" over a
    # greyed card): that is the input's doing, told to the turn the input begins
    add(store, tid, 'card', f'card:{rid}:{len(olds)}:{_card(body)[:200]}', **body, own=general.at_work(tid) and not (r.get('Status') == 'superseded' and r.get('DecideNote') == proposals.SET_ASIDE))


def _went(r: dict) -> dict:
    "Whom a sent card went to, as its envelope says it after the send - {to, cc} - else nothing."
    if r.get('DeliveryState') != 'sent': return {}
    try: d = json.loads(r.get('Deliver') or '{}') or {}
    except (TypeError, ValueError): return {}
    ls = lambda x: [str(a) for a in (x if isinstance(x, list) else [x] if x else [])]
    return {'to': ls(d.get('to')), 'cc': ls(d.get('cc'))} if isinstance(d, dict) else {}


@_safe
def audited(store, et: str, eid, action: str, actor: str, detail) -> None:
    """A row of the audit that is a fact for the agent (store.audit): a press of his on the task (general.PRESSES), and a proposal of its own
    that was never put on a card."""
    if et != 'task' or not eid: return
    from . import general
    from .processing_unread import OWNER_ACTORS
    try: d = json.loads(detail) if isinstance(detail, str) else (detail or {})
    except ValueError: d = {}
    d = d if isinstance(d, dict) else {}
    if action == 'proposal_refused' and d.get('unheard'):
        from .proposals import refusal_line
        return add(store, eid, 'note', text=f"what you proposed ({d.get('action') or 'the proposal'}) was not put on a card - {refusal_line(d.get('why') or '')}")
    # ...A REOPEN NOT HIS - mail on its thread, a check-back, a failed check - IS A FACT IN ITS PLACE, after the close it undid (walk 15: a resend
    # reopened a task he had just marked done, and its agent, the mail in its brief, was told only the close and said "I've closed this out")
    if action == 'reopen' and actor not in OWNER_ACTORS:
        by = f"{d['by']}'s message" + (f" (m{d['mid']})" if d.get('mid') else '') if d.get('by') else ''
        return add(store, eid, 'note', text=f"The task was reopened{' by ' + by if by else ''}" + (f" - {d['why']}" if d.get('why') else '') + '.')
    # ...A REOPEN HIS TYPED LINE MADE IS SAID BY THAT LINE (general.QUIET's reopened_by_typing): the store's own `reopened` row, written by
    # the same write, right after it, is no press of his
    typed = lambda: [r['Action'] for r in store._rows("SELECT Action FROM audit WHERE EntityType='task' AND EntityId=? AND Action IN ('reopened','reopen','reopened_by_typing') "
                                                      "ORDER BY Id DESC LIMIT 2", (eid,))][1:] == ['reopened_by_typing']
    if actor not in OWNER_ACTORS or action not in general.PRESSES or d.get('review') or action in ('reopened', 'reopen') and typed(): return
    add(store, eid, 'press', what=general.PRESSES[action](d))


def note(store, tid: int, text: str) -> int | None:
    "Taskuary's own word to the agent (general.to_agent): a hand-over closed, a sign-in done, a landing."
    return add(store, tid, 'note', text=str(text or '').strip()) if str(text or '').strip() else None
