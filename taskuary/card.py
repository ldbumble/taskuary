"""ONE CARD (the design review, change 6: "six kinds of 'waiting on him', each with its own told-back road"). Whatever waits on the owner - a
reply or an email to Send, an act to Approve (a proposal, a post, a held step, a close-out, a skill, a bulk batch), the agent's question, a
step handed to him on a page (a sign-in, his turn), the landing question, a stranger's Trust - is read here as ONE object:

    {id, task, kind, sort, state, verb, what, rids, at, decided, by, error, front}

kind   send | approve | answer | on_page | land | trust          (what his press is: words that go, an act that runs, a fact, his hands, ...)
sort   reply | email | calendar | post | act | held | closeout | skill | question | signin | turn | land | trust
state  pending -> pressed (a send under way) -> handed (his press gave its act to the agent) -> done | failed | withdrawn | set_aside

The rows stay where they live (review, worker_event, landing's record): this module only reads them, one function per question -
`waiting` (what waits on him), `front` (what is in front), `may_close` (may a press close the task), `did` (what a press did) - and presses
them by ONE road (`press`): a review through the desk's own door (server.press_review, the stale-thread check and verdicts.decide behind it), a
question or a page step through workerstate.answer. The desk, the phone and the Assistant read and press here; `settled` is what the agent's
events read of the presses since its cursor."""
import json, re
from contextlib import contextmanager

from . import cardqueue as cq

SEND, APPROVE, ANSWER, ON_PAGE, LAND, TRUST = 'send', 'approve', 'answer', 'on_page', 'land', 'trust'
STATES = ('pending', 'pressed', 'handed', 'done', 'failed', 'withdrawn', 'set_aside')
OPEN = ('pending', 'pressed', 'handed')
HOLDS_CLOSE = (SEND, APPROVE, LAND)             # ...what keeps a task open past a Send and close: a question or a page step never did
TAKERS = ('agent', 'assistant', 'taskuary')     # who takes a card back: never his no


def _p(r) -> dict: return cq._p(r)


def sort_of(r: dict) -> str:
    "A review row's card, finer than its kind: what the page draws it as."
    from .proposals import CLOSEOUT, HELD_ACTS, SKILL, is_post
    if r.get('Kind') != 'action':
        try: own = json.loads(r.get('Deliver') or '{}') or {}
        except (TypeError, ValueError): own = {}
        return 'calendar' if isinstance(own, dict) and own.get('kind') == 'calendar' else 'email' if r.get('Kind') == 'slot' else 'reply'
    p = _p(r); a = p.get('action')
    return ('closeout' if p.get('closeout') or a in CLOSEOUT else 'skill' if a == SKILL else 'held' if a in HELD_ACTS
            else 'post' if is_post(p) else 'act')


def state_of(r: dict) -> str:
    """THE ONE STATE MACHINE of a review's card. pending: his to press (a press that failed and left it standing too - `error` says why);
    pressed: his Send is under way; handed: his press gave its act to the agent, not done yet (cardqueue.handed); done: his press settled it,
    yes or no (`verb`); failed: his press ran and nothing of it was done; withdrawn: its agent or Taskuary took it back; set_aside: the chat
    moved past it (proposals.passed)."""
    from .conversation import _card
    from .proposals import passed
    s = r.get('Status')
    if s in ('pending', 'held'): return 'pressed' if r.get('DeliveryClaim') or r.get('DeliveryState') == 'sending' else 'pending'
    if cq.handed(r): return 'handed'
    if passed(r): return 'set_aside'
    if _card(r)['status'] == 'failed': return 'failed'
    if s in ('approved', 'edited', 'sent'): return 'done'
    return 'done' if s in ('rejected', 'no_reply', 'closed_unsent') and r.get('DecidedBy') not in TAKERS else 'withdrawn'


VERBS = {'approved': 'yes', 'sent': 'yes', 'edited': 'edited', 'rejected': 'no', 'no_reply': 'no', 'closed_unsent': 'no'}


def _error(r) -> str:
    if r.get('ActError'): return cq._flat(r['ActError'])
    return cq._flat(r.get('Reason')) if r.get('DeliveryState') in ('failed', 'unknown') else ''


def presses(store, r: dict) -> tuple:
    """THE BUTTONS A REVIEW'S CARD DRAWS, by verb - the one answer every surface that names a press reads (the phone's picks, the Assistant's
    lines, the agent's screen fact, where it stands). A letter its channel cannot deliver (capabilities.can_send_draft) has no Send: its
    Connect where a connection would lift it ('connect:<its label>', outbound.review_connect), else Copy - as the desk draws it (walk 21:
    "ready to send" and a phone poll's Send over a Teams card that had only Copy)."""
    if r.get('Kind') == 'action': return ('approve',)
    from . import capabilities, outbound
    if capabilities.can_send_draft(store, r.get('ReviewId')): return ('approve',)
    fix = capabilities._safe(lambda: outbound.review_connect(store, r), None)
    if not (fix and fix.get('label')): return ('copy',)
    return (f"connect:{fix['label']}", *(('copy',) if fix.get('waits') else ()))     # ...its draft kept to copy, where it says so


def press_words(c: dict) -> str:
    "A card's buttons by their names, for a reader that reads words: 'Copy - it cannot be sent from here'."
    from . import buttons
    ps = c.get('presses') or ()
    return ', '.join(v.partition(':')[2] or buttons.label(v, 'action' if c.get('kind') == APPROVE else None) for v in ps) + \
        (' - it cannot be sent from here' if c.get('kind') == SEND and 'approve' not in ps else '')


def _of(store, rows: list, front: bool = False) -> dict:
    "A card of review rows (one, or a bulk card's / a turn's held steps): its state is the first open row's, else the first row's."
    rows = [r for r in rows if r]
    open_ = [r for r in rows if state_of(r) in OPEN]
    r = (open_ or rows)[0]; st = state_of(r)
    return {'id': f"rv{r['ReviewId']}", 'task': r.get('TaskId'), 'kind': APPROVE if r.get('Kind') == 'action' else SEND, 'sort': sort_of(r),
            'state': st, 'verb': VERBS.get(r.get('Status')) if st in ('done', 'handed') else None,
            'what': cq.what(store, {'rids': [x['ReviewId'] for x in rows], 'rows': rows}), 'rids': [x['ReviewId'] for x in rows],
            'at': r.get('CreatedAt'), 'decided': r.get('DecidedAt'), 'by': r.get('DecidedBy'), 'error': _error(r), 'front': front, 'row': r,
            'presses': presses(store, r) if st == 'pending' else ()}


def of_review(store, r: dict) -> dict: return _of(store, [r])


def _ask(tid, q: dict, kind: str) -> dict:
    sort = q.get('ask') if kind == ON_PAGE else 'question'
    return {'id': f"{'page' if kind == ON_PAGE else 'ask'}:{int(tid)}:{q['request_id']}", 'task': int(tid), 'kind': kind, 'sort': sort,
            'state': 'pending', 'verb': None, 'what': cq._flat(q.get('text'), 200), 'rids': [], 'at': q.get('at'), 'decided': None, 'by': None,
            'error': '', 'front': False, 'request': q.get('request_id')}


def _asks(store, tid: int) -> list:
    """The agent's question and the steps handed to him on a page, as cards: the question the live run is asking (workerstate.asking_of - its
    group as one), else the ones a run that is over was still asking (left_asking, which the page draws) or an agent at rest still asks
    (taskstate.open_question: idled out, or after a restart - it stands until he answers, the task closes or the agent takes it back); each
    page step that waits."""
    from . import general, taskstate, workerstate as ws
    out = []
    try:
        live = general.session_for(tid) or ws._live(tid)
        qs = [q] if live and (q := ws.asking_of(store, live)) else [] if live else \
            ws.left_asking(store, tid)[:1] or [q for q in (taskstate.open_question(store, tid),) if q]
        out += [_ask(tid, q, ANSWER) for q in qs if q.get('text') and q.get('ask', 'question') == 'question' and q.get('kind') != 'approval_needed']
    except Exception as e:
        from loguru import logger
        logger.debug(f'card: the questions on task {tid} were not read - {e}')
    return out + [_ask(tid, q, ON_PAGE) for q in cq.on_page(store, tid)]


def _land(store, tid: int, u: dict) -> dict:
    return {'id': f'land:{int(tid)}', 'task': int(tid), 'kind': LAND, 'sort': 'land', 'state': 'pending', 'verb': None, 'what': cq.what(store, u),
            'rids': [cq.LAND], 'at': None, 'decided': None, 'by': None, 'error': '', 'front': False}


def waiting(store, tid, asks: bool = True, trust: bool = True) -> list:
    """WHAT WAITS ON THE OWNER ON TASK `tid`, card by card, in the order the page brings them: the line (cardqueue.state - its front first,
    then what is held behind it, the landing question among them), then the cards outside the line still his to press (a workflow's own step,
    an email he wrote himself, a reply held while the agent worked), then - with `asks` - the agent's question and the steps handed to him on
    a page. A card his press handed to the agent stands as `handed`: owed by the agent now, not by him. On a task a stranger's mail started
    its Trust stands in front of them all (origin.keeps_him: the page draws no other card to press until he trusts them)."""
    if store is None or not str(tid or '').isdigit(): return []
    # ...one read of a page asks it once (cardqueue.fresh): its detail, its Send and close and its pill each ask
    return cq.fresh(store, ('cards', int(tid), bool(asks), bool(trust)), lambda: _waiting(store, int(tid), asks, trust))


def _waiting(store, tid: int, asks: bool, trust: bool = True) -> list:
    from . import origin
    from .conversation import unwritten
    # ...the line itself read once whatever is asked beside it (the Trust, the agent's question): Send and close and where it stands each ask -
    # and before the hold, whose first judging of the task's origin writes it down (origin.of_task), which a line kept would not outlive
    # ...AND ON A WATCHED TASK THE TRUST IS OWED TO NOBODY (the owner, 2026-11-25: "Trust <name>" lit, "on you", on a thread somebody else
    # handles): no work of his waits on it - it stands in the chat for him to press if he wants an agent on it, and waits on nothing
    if asks or trust:
        from . import watch
        line, h = waiting(store, tid, asks=False, trust=False), origin.keeps_him(store, tid) if trust and not watch.watching(store.get_task(tid)) else None
        out = [{'id': f'trust:{tid}', 'task': tid, 'kind': TRUST, 'sort': 'trust', 'state': 'pending', 'verb': None, 'what': cq._flat(h.get('line')),
                'rids': [], 'at': None, 'decided': None, 'by': None, 'error': '', 'front': True}] if h else []
        return out + line + (_asks(store, tid) if asks else [])
    out, st = [], cq.state(store, tid)
    for i, u in enumerate(st['units']):
        out.append(_land(store, tid, u) if u['rids'] == [cq.LAND] else _of(store, cq._waits(u) or u['rows']))
        out[-1]['front'] = i == 0
    seen, by = {x for u in st['units'] for x in u['rids']} | set(st['past']), {}
    for r in store._rows("SELECT * FROM review WHERE TaskId=? AND Status IN ('pending','held') ORDER BY ReviewId", (tid,)):
        if r['ReviewId'] in seen or unwritten(r) or cq.obsolete_read(store, tid, r): continue
        by.setdefault(cq._turn(r), []).append(r)
    return out + [_of(store, rs) for rs in by.values()]


def front(store, tid, trust: bool = True, asks: bool = True) -> dict | None:
    """THE CARD IN FRONT on task `tid` - the one his next press is for - or None: a stranger's Trust, else the line's front, else the first
    card outside it, else (with `asks`) the agent's question. A handed one is in front, but it is the agent's to do. `trust`: False reads
    past the Trust."""
    pick = lambda cs: next((c for c in cs if c['front']), None) or next(iter(cs), None)
    cs = [c for c in waiting(store, tid, asks=False) if trust or c['kind'] != TRUST]
    return pick(cs) or (pick(waiting(store, tid)) if asks else None)


def front_review(store, tid) -> dict:
    """The review row of the card in front that waits for HIS press now - {} where none does: nothing waits, the front is no review (the
    landing question, a stranger's Trust), or his press already handed it to the agent."""
    c = front(store, tid, asks=False)
    return dict(c['row']) if c and c.get('row') and c['state'] == 'pending' else {}


def pending(store, tid, sort: str) -> dict | None:
    """The review row of the oldest card of `sort` ('closeout', 'skill', 'held', 'act', 'post', ...; 'acts': any act to Approve) still
    waiting for his press on task `tid`, in the line or out of it - None when none does."""
    if not tid: return None
    for r in store._rows("SELECT * FROM review WHERE TaskId=? AND Status='pending' ORDER BY ReviewId", (int(tid),)):
        if (sort == 'acts' and r.get('Kind') == 'action') or sort_of(r) == sort: return r
    return None


def holds_close(store, tid, pressing=None) -> list:
    """The cards that keep task `tid` open past a press that would close it: every send, act and landing question still open on it but the
    one being pressed (`pressing`: its card id or review id). THE ONE ANSWER the close-offering buttons (may_close) and the close after a
    send (concierge.close_after_send) read."""
    p = str(pressing or '')
    skip = lambda c: p and (c['id'] == p or p.lstrip('rv') in {str(x) for x in c['rids']})
    return [c for c in waiting(store, tid, asks=False, trust=False) if c['kind'] in HOLDS_CLOSE and not skip(c)]


def may_close(store, tid, pressing=None) -> str:
    """MAY A PRESS ON THE CARD IN FRONT CLOSE TASK `tid` WITH IT (Send and close, Approve and close)? '' when nothing else holds the close,
    else what does, in words ('the email to Erin Blake'). `pressing`: the card pressed - the front where none is named. An answer awaited from
    somebody else, the agent's own question and a check-back its agent set hold it too, as the task stands (taskstate.standing - walk 16: Send and close stood first
    under a reply while the agent's own check-back said the work goes on) - Send and Mark done stay, and a check-back outlives Mark done."""
    if not tid: return ''
    if pressing is None: pressing = next((c['id'] for c in waiting(store, tid, asks=False, trust=False) if c['front'] and c['kind'] != TRUST), None)
    if (c := next((c['what'] or 'another card' for c in holds_close(store, tid, pressing)), '')): return c
    from .taskstate import standing
    st = standing(store, tid)
    # ...and the agent's own question to him (the owner, 2026-11-24, J1: it stands until he answers, the task closes or the agent withdraws it -
    # walk 18: Send and close stood first under it)
    if st.get('ask'): return f"the agent's question ({' '.join(st['ask'].split()[:12])})"
    if st['them']: return st['them'][0]['what']
    return f"the check-back the agent set ({' '.join(st['check']['what'].split()[:12]) or 'its next look'})" if st['check'] else ''


def lines(store, tid, asks: bool = True) -> list:
    """What waits on him on task `tid`, a line each, for the Assistant, the dock and the phone's reads: {rid, verb, line, says} - `line` the
    short line, `verb` the button that answers it, `says` the words a Send and close kept open says. The page's own waiting cards
    (`waiting`), never a reading of its own. A stranger's Trust in front is the one line, in its hold's words: nothing behind it is his to
    press until then (walk 16: the phone's "list them all" left both held senders out - their tasks had no line)."""
    from . import buttons, proposals
    A, S, out = buttons.label('approve', 'action'), buttons.label('approve'), []
    cs = waiting(store, tid, asks)
    if cs and cs[0]['kind'] == TRUST: return [{'rid': None, 'verb': 'trust', 'says': '', 'line': cs[0]['what']}]      # ...no press it holds open (HOLDS_CLOSE)
    for c in cs:
        r = c.get('row') or {}
        if c['kind'] == SEND:
            d = json.loads(r.get('Deliver') or '{}') if str(r.get('Deliver') or '').startswith('{') else {}
            to = ', '.join(d['to']) if isinstance(d.get('to'), list) else str(d.get('to') or '')
            to = to or str((store.get_message(r['MessageId']) or {}).get('FromEmail') or '') if r.get('MessageId') else to
            what, held = f"{'an email' if r.get('Kind') == 'slot' else 'a reply'}{' to ' + to if to else ''}", r.get('Status') == 'held'
            says = (f"an email this task owes still waits for your {S}" if r.get('Kind') == 'slot' else
                    'a reply held while the agent worked comes back for your Send' if held else f'another reply still waits for your {S}')
            # ...as its card draws it (presses): one its channel cannot deliver has no Send to name
            if c['state'] == 'pending' and 'approve' not in c['presses']:
                out.append({'rid': r['ReviewId'], 'verb': None, 'says': f'{what} still waits to be copied - {press_words(c)}',
                            'line': f'{what} is drafted - {press_words(c)}'}); continue
            out.append({'rid': r['ReviewId'], 'verb': 'approve', 'says': says, 'line': f"{what} is drafted - {S} sends it" + (' (held while the agent works)' if held else '')})
        elif c['kind'] == APPROVE and c['state'] == 'handed':
            d = json.loads(r.get('FinalText') or '{}') if str(r.get('FinalText') or '').startswith('{') else {}
            what = f"the {proposals.POSTS[d['type']]} post" if proposals.is_post(d) else ' '.join(str(r.get('Reason') or 'the act').split())[:120]
            out.append({'rid': r['ReviewId'], 'verb': None, 'says': f'{what} is with the agent, not done yet',
                        'line': f"{what} is handed to the agent - not done yet; its final press waits for your yes"})
        elif c['kind'] == APPROVE:
            d = _p(r)
            if c['sort'] == 'held':
                step = d.get('what') or str(d.get('command') or 'a step')[:120]
                says, line = f"the agent's held step still waits for your {A} - {step}", f"the agent's held step - {step} - waits for your {A}"
            else:
                why = ' '.join(str(r.get('Reason') or 'a proposal').split())[:200]
                says, line = f"{why} - still waiting for your {A}", f"a {proposals.POSTS[d['type']]} post waits for your {A}" if c['sort'] == 'post' else f"{why} - {A} does it"
            out.append({'rid': r['ReviewId'], 'verb': 'approve', 'says': says, 'line': line})
        elif c['kind'] == LAND:
            out.append({'rid': None, 'verb': None, 'says': f"{c['what']} question still waits for your answer", 'line': f"{c['what']} question waits for your answer"})
        elif c['kind'] == ANSWER: out.append({'rid': None, 'verb': 'answer_agent', 'says': '', 'line': f"the agent asks: {c['what']}"})
        elif c['kind'] == ON_PAGE: out.append({'rid': None, 'verb': None, 'says': '', 'line': f"handed to you on the page: {c['what']}"})
    return out


def did(store, c: dict, verb: str = None) -> str:
    """WHAT A PRESS DID, in the owner's words, read off the card as it stands now - the one sentence the phone's receipt and the agent's
    events say of it. `verb`: the press just made, for a card whose row has not moved yet."""
    st, what = c['state'], c['what']
    letter = c['kind'] == SEND
    if st == 'handed': return f"Handed {what} to its agent - not done yet; its own final press comes back to you."
    if st == 'failed': return f"Failed - {c['error'] or 'it did not go'}. Nothing of {what} was done."
    if st == 'set_aside': return f'Greyed - the chat moved past {what}; nothing went.'
    if st == 'withdrawn': return f'Taken back - {what} will not go.'
    if st == 'pressed': return f'Sending {what}…'
    v = c.get('verb') or {'approve': 'yes', 'edit': 'edited', 'reject': 'no', 'no_reply': 'no', 'close_unsent': 'no', 'merge_anyway': 'yes'}.get(verb or '')
    if st == 'pending' and c.get('error') and not verb: return f"{'Not sent' if letter else 'Not done'} - {c['error']}. It waits for your press again."
    if v == 'no': return f"{'Not sent' if letter else 'Dismissed'}: {what} - nothing {'went' if letter else 'ran'}."
    if v == 'edited': return f'Sent {what}, with your words.'
    if v == 'yes':
        got = cq._result(c['row']) if c.get('row') and st == 'done' else ''
        return f"{'Approved' if not letter else 'Sent'} {what}." + (f' {got}' if got else '')
    return ''


def press(store, cid, verb: str, text: str = None, **kw) -> dict:
    """THE ONE PRESS ROAD for every card, wherever it was pressed - {'ok', 'did', 'out'}. A review goes through the desk's own door
    (server.decide: the thread that moved stops it, verdicts.decide does it); a question or a step on a page through workerstate.answer. A
    card no longer his to press is said as what became of it, and nothing is pressed."""
    cid = str(cid)
    if cid.isdigit() or cid.startswith('rv'): return _press_review(store, int(cid.lstrip('rv')), verb, text, **kw)
    kind, _, rest = cid.partition(':')
    if kind in ('ask', 'page'):
        from . import workerstate as ws
        tid, _, rid = rest.partition(':')
        try: out = ws.answer(store, int(tid), rid, text or '', kw.get('actor') or 'owner', press=kind == 'page' and not text)
        except ValueError as e: return {'ok': False, 'did': f'Not answered - {e}.', 'out': {}}
        ok = bool(out.get('delivered'))
        return {'ok': ok, 'did': 'Told the agent.' if ok else f"Not answered - {out.get('why') or out.get('state') or 'it did not reach the agent'}.", 'out': out}
    return {'ok': False, 'out': {}, 'did': {'land': 'The landing question is answered on the task page - its own buttons say where the work goes.',
                                            'trust': 'Nothing waits but Trust: press Trust on the task, and its agent starts.'}.get(kind, 'No card of that name.')}


def _press_review(store, rid: int, verb: str, text: str = None, **kw) -> dict:
    from fastapi import HTTPException
    from . import server
    rv = store.get_review(rid) or {}
    c = of_review(store, rv) if rv else None
    if not c: return {'ok': False, 'did': 'No card of that name - nothing was pressed.', 'out': {}}
    if c['state'] != 'pending': return {'ok': False, 'did': f"That card is not waiting any more ({did(store, c) or c['state']}) - nothing was pressed.", 'out': {}}
    try: out = server.press_review(store, rid, server.DecideBody(verb=verb, final_text=text, **{k: v for k, v in kw.items() if k != 'actor'}))
    except HTTPException as e: return {'ok': False, 'did': f'Not done - {e.detail}. Nothing went.', 'out': {}}
    if out.get('stale') or out.get('send_error') or not out.get('ok', True):
        return {'ok': False, 'did': f"Not sent - {out.get('send_error') or 'it did not go'}", 'out': out}
    now = of_review(store, store.get_review(rid) or rv)
    # ...a door that answered for a row that has not moved (a press still settling) is said by the press that was made
    return {'ok': True, 'did': did(store, now if now['state'] != 'pending' else {**now, 'error': ''}, verb), 'out': out}


def settled(store, tid, since: str = '') -> list:
    """The cards on task `tid` settled since `since` (a stored time), oldest first - each with its state and what the press did (`did`): what
    an agent's events say of the presses since its cursor."""
    rows = store._rows("SELECT * FROM review WHERE TaskId=? AND Status NOT IN ('pending','held') AND DecidedAt>? ORDER BY DecidedAt, ReviewId",
                       (int(tid), str(since or '')))
    return [{**c, 'did': did(store, c)} for c in (of_review(store, r) for r in rows if cq.in_line({**r, 'Status': 'pending', 'DecideNote': None}))]


# WHETHER HIS PRESS WAKES THE AGENT IS ITS CARD'S, NOT ITS TURN'S (the owner, said ~40 times): a press whose end is the act itself - a Send -
# wakes nobody; the agent goes on only where a step of its OWN follows, which it gave as the card's `then` when it raised it. It was a word in
# the turn's end_turn whose meaning lived only in that tool's text, and a trim of the text made every Send wake it to say it went (d6e6a670a)
def then_of(c) -> str:
    "The agent's own step after his press on card `c` - a review row (NextStep) or the landing question's proposal (then) - '' for none."
    return ' '.join(str((c or {}).get('NextStep') or (c or {}).get('then') or '').split())


# ...AND AN ACT TASKUARY CONFIRMED NEEDS NO CHECK OF THE AGENT'S (the owner's written OK, 2026-11-25: "Yes, change the rule"): every caller is a
# press that went - posted, sent, pushed - so a `then` that only does what that press already did is satisfied by it. Told by the card's own
# record, never by reading the words for meaning: a `then` naming the to-do this card does (`todo`, which its press ticks - went) wakes nobody
def carries_on(c, store=None) -> bool:
    "Whether his confirmed press on card `c` (a review row, or the landing question's proposal) wakes its agent for a next act of its own."
    # ...HIS ANSWERS TO ITS QUESTIONS ARE ITS TO GO ON WITH (locked rule 4: his answer reaches the agent once) - a questions card names no `then`
    from .proposals import ASKS
    if (c or {}).get('Kind') == 'action' and _p(c).get('action') == ASKS: return True
    if not (then := then_of(c).casefold()): return False
    if store is None or not (c or {}).get('ReviewId'): return True
    own = [i for i in store.task_checklist(int(c['TaskId'])) if i['id'] in _todos(store, c['ReviewId'])]
    return not any(re.search(rf'(?<!\w){re.escape(i["id"].casefold())}(?!\w)', then) or ' '.join(i['text'].split()).casefold() in then for i in own)


# ...and a question its agent asked ABOUT a card (ask_owner's `card`) is answered by his press on it: left standing, "Should it go out as
# drafted?" stayed on the task after the letter went. A question beside a card on something else stays his (walk 20: a vendor's reply and
# what headcount to share with them, in one turn)
ASKED = 'asked_about'
def asked_about(store, rid) -> list:
    "The questions task's agent asked about review `rid`, in its words."
    rows = [r for r in store.list_audit('review', int(rid)) if r.get('Action') == ASKED]
    out = []
    for r in rows:
        try: d = r['Detail'] if isinstance(r.get('Detail'), dict) else json.loads(r.get('Detail') or '{}')
        except ValueError: d = {}
        if d.get('question'): out.append(d['question'])
    return out


def _standing(store, tid) -> tuple:
    from . import landing
    rows = store._rows("SELECT ReviewId, DraftText, DraftAt FROM review WHERE TaskId=? AND Status IN ('pending','held')", (int(tid),))
    return {r['ReviewId']: (r['DraftText'], r['DraftAt']) for r in rows}, landing.record(store, int(tid)).get('proposal')


@contextmanager
def raising(store, tid, then, todo=None):
    """Run a call that raises cards on task `tid`: each card it raised or rewrote keeps `then` - none clears it, the newest raise speaks - the
    landing question's too. Read back by `carries_on`, after a restart as before it. `todo`: the task's to-do those cards do (went)."""
    from . import landing
    was = _standing(store, tid)
    yield
    now, then = _standing(store, tid), ' '.join(str(then or '').split())[:300]
    todo = next((i['id'] for i in store.task_checklist(int(tid)) if str(todo or '').strip().strip('[]') == i['id']), None)
    for rid in [k for k, v in now[0].items() if was[0].get(k) != v]:
        # ...a card Taskuary raised in the call's place comes with its own next act - the call itself, once his press opens the way
        # (workstreams.move_card) - and keeps it: cleared here, his Approve moved the task and woke nobody, the email owed (walk 25)
        if rid not in was[0] and then_of(store.get_review(rid)): continue
        store.set_review_next_step(rid, then)
        if todo: store.audit('review', rid, FULFILS, 'agent', 'agent', {'todo': todo})
    if now[1] and now[1] != was[1]: landing.keep_then(store, int(tid), then)


# THE PRESS'S RECORD IS TASKUARY'S, NEVER A TURN OF THE AGENT'S (the owner: "wake only for a real next step"; walk 22, 2026-11-25: every card
# carried `then: "mark the to-do complete"`, so every Send woke its agent to tick a box and say under the card what the card already said).
# A card names the to-do it does as it is raised (`todo`, raising); the to-do is ticked by plain code once every card raised for it has gone -
# every kind of card, by the one door a press that went passes (verdicts.decide; cardqueue.done for an act handed to the browser)
FULFILS = 'fulfils'
def _todos(store, rid) -> set:
    out = set()
    for r in store.list_audit('review', int(rid)):
        if r.get('Action') != FULFILS: continue
        try: d = r['Detail'] if isinstance(r.get('Detail'), dict) else json.loads(r.get('Detail') or '{}')
        except ValueError: d = {}
        if d.get('todo'): out.add(str(d['todo']))
    return out


def went(store, rv: dict) -> list:
    "His press on review `rv` went: -> the to-dos ticked, each one this card does with no other card for it still waiting or under way."
    tid, mine = rv.get('TaskId'), _todos(store, rv['ReviewId']) if rv.get('ReviewId') else set()
    if not (tid and mine): return []
    open_ = [r for r in store._rows("SELECT * FROM review WHERE TaskId=? AND ReviewId<>? AND Status IN ('pending','held','approved','edited')", (int(tid), rv['ReviewId']))
             if r['Status'] in ('pending', 'held') or cq.handed(r)]
    left = set().union(*(_todos(store, r['ReviewId']) for r in open_)) if open_ else set()
    return [t for t in sorted(mine - left) if store.tick_checklist_item(int(tid), t, True, 'taskuary')]
