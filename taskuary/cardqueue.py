"""ONE CARD AT A TIME (the owner, 2026-11-16: "where there are 2 action cards, like approve push then email, it should wait on each approval
step or action card, so the agent should wait on it and then go to next steps ... action cards should hold up the agent until it's completed.
In chat flow it makes more sense"). Every card on a task - a reply or an email to Send, an act to Approve (a push, a PR, a post, a SQL write,
a held step), a calendar answer, the landing question - stands in ONE line, in the order it was raised. Only its front is live; the rest are
held: drawn nowhere, named on the front as what comes next. One comes forward the moment the owner has pressed the one before it; the agent
hears the row once it is over (row_over) where a step of its own follows, and at once where a press failed. HIS NO NEVER WAKES IT (the owner,
2026-11-26: a click on a card wakes its agent only where it failed or the agent has something to do next - Dismiss on two posts of three
woke it twice, and it wrote under the one still waiting): it is recorded on its card and is that card's event (events.card), told as his
own with the agent's next turn. A press never sends or closes another card; nothing goes without its own press.

Plain code, read wherever a card is drawn, listed or told: the chat's list (conversation.items), the page's detail (server.task_detail), what
waits on the owner (store.waiting_reviews), and what its agent hears (agenttools, events.py, general.approved/failed)."""
import json, time, weakref

LAND = 'land'                   # the landing question (landing.record): a card with no review row
FRESH = 1.0                     # seconds one read of a task's line serves the reads beside it, while nothing was written


# ...ONE READ OF A PAGE ASKS IT ONCE (tests/test_big_task_opens_fast: the task's open, its state, what waits on him and its pill each asked
# the line again): kept for a second, and only while this store has written nothing since
_SEEN: dict = {}
def fresh(store, key, fn):
    w = getattr(store, '_writes', None)
    if w is None: return fn()
    k, now = (id(store), key), time.monotonic()
    # ...and only for this very store: a store gone and a new one at its address (a test's) is another store
    if (got := _SEEN.get(k)) and got[3]() is store and got[0] == w and now - got[1] < FRESH: return got[2]
    if len(_SEEN) > 512: _SEEN.clear()
    # ...kept from when it was READ, not asked: a read longer than FRESH (a 1,500-line chat) was stale as it landed and read again by every caller
    v = fn(); _SEEN[k] = (w, time.monotonic(), v, weakref.ref(store)); return v


def _p(r) -> dict:
    try: d = json.loads(r.get('DraftText') or '{}') or {}
    except (TypeError, ValueError): d = {}
    return d if isinstance(d, dict) else {}


def handed(r: dict) -> bool:
    """PRESSED IS NOT DONE (walk 6, 2026-11-23: Post via the browser on a LinkedIn card approved it, and its agent was told "Done 7:31 AM: post to
    LinkedIn" in the very message asking it to go and post it; the X card came forward as if it had gone, and the Assistant's list of what
    waits left it out). THE ONE STATE of a press that handed its act to the agent to do - pressed, not yet done - read by the line (the next
    card waits behind it), the agent's screen fact and what the Assistant says a task holds (card.lines). Cleared by its real
    result (done)."""
    if r.get('Kind') != 'action' or r.get('Status') not in ('approved', 'edited'): return False
    try: got = (json.loads(r.get('FinalText') or '{}') or {}).get('result') or {}
    except (TypeError, ValueError, AttributeError): got = {}
    return isinstance(got, dict) and bool(got.get('browser')) and not got.get('done')


def done(store, tid: int, said: str) -> list:
    """The act a press handed to the agent, done: its own final press ran (browsergate.perform) - the oldest handed card on task `tid` settles
    with `said` as its result, and the line moves on. -> its review id, or []."""
    if not (r := in_flight(store, tid)): return []
    p = json.loads(r['FinalText'])
    store.review_result(r['ReviewId'], json.dumps({**p, 'result': {**p['result'], 'done': str(said or 'done')[:300]}}))
    from . import card, ledger
    ledger.went(store, r['ReviewId'])                    # ...it went live: on the record (ledger.py), as an act its card ran is
    card.went(store, r)                                  # ...and the to-do it does is ticked, as any card's that went
    from .proposals import finished_without
    finished_without(store, tid, r['ReviewId'])          # ...and a step held on its road that it went without is over with it: nothing pending, no button
    return [r['ReviewId']]


def step(u: dict) -> dict | None:
    """THE STEP OF A HANDED CARD'S BROWSER ROAD THAT WAITS FOR HIS PRESS (walk 22, 2026-11-25: the final Post on X was held, joined to the X card
    he had pressed, and drawn nowhere - both agents said a card waited): that card's own next press, drawn on it - the newest held, or None."""
    return next(reversed(_waits(u)), None) if u.get('rows') and handed(u['rows'][0]) else None


def step_says(sp: dict) -> str:
    "A held step in words, with what its page holds for it to send (browsergate.held_says) - one sentence for his card and for its agent."
    from .browsergate import held_says
    return held_says(_p(sp))


def in_flight(store, tid: int) -> dict | None:
    "The act on task `tid` a press handed to its agent and that is not done yet - the oldest one, as `done` settles them - or None."
    return next((r for r in store._rows("SELECT * FROM review WHERE TaskId=? AND Kind='action' AND Status IN ('approved','edited') ORDER BY ReviewId",
                                        (int(tid),)) if handed(r)), None)


def obsolete_read(store, tid, review) -> bool:
    """Hide obsolete requests to read an already allowed folder. Keep successful approvals in the history."""
    from . import readgate
    return (bool(tid) and review['Kind'] == 'action' and review['Status'] not in ('approved', 'edited')
            and readgate.opened(store, tid, _p(review)))


def in_line(r: dict) -> bool:
    """A card of the line: one the owner presses - the agent's, triage's, or Taskuary's own close-out and skill alike (his live app,
    2026-11-23: the skill stood outside the line, so the email in front of it thought nothing waited behind and offered Send and close;
    the task closed, then came back for the skill). Never a workflow's own step, an email he wrote himself, nor one nobody has written
    (a reply owed, a to-do's email)."""
    from .conversation import unwritten
    from .proposals import passed
    if passed(r) or unwritten(r): return False
    if r['Kind'] == 'slot': return bool(str(r.get('DraftText') or '').strip()) and not str(r.get('Reason') or '').startswith('your email')
    if r['Kind'] == 'action': return not (_p(r).get('block') or str(r.get('Reason') or '').startswith('the workflow'))
    return True


def _closeout(r) -> bool:
    from .proposals import CLOSEOUT
    return r.get('Kind') == 'action' and (bool((p := _p(r)).get('closeout')) or p.get('action') in CLOSEOUT)


def _turn(r) -> str:
    """A turn's held steps are one card (heldGroups on the page), and so are the rows of a bulk card (bulkcard.py, its Batch): the key they
    share - a review's own id for any other card."""
    if r.get('Batch'): return f"b:{r['Batch']}"
    p = _p(r) if r['Kind'] == 'action' else {}
    return f"{p.get('sid') or ''}|{p['turn']}|{p.get('where') or p.get('cwd') or ''}" if p.get('action') == 'shell_act' and p.get('turn') is not None else f"rv{r['ReviewId']}"


def _units(store, tid: int, past: set) -> list:
    "Every card of the line on task `tid`, waiting or settled, oldest first: [{'rids', 'at', 'done', 'rows'}] - the landing question among them."
    from . import landing
    from .conversation import ep
    from .proposals import HELD_ACTS, moved_on
    out, by = [], {}
    # ...A STEP HELD WHILE A PRESSED ACT IS UNDER WAY IS THAT ACT'S OWN NEXT PRESS (his live app, 2026-11-23: Post via the browser on the X card, the
    # agent signed in and wrote the post, and the gate held its final Post - queued as a card of its own behind the Reddit and LinkedIn cards, so
    # Reddit stood in front, the browser said nothing waited on him, and the agent ended on "I'll bring you the link"): it is a row of the card
    # he pressed (its `card`, written as it was held - proposals.queue), drawn on that card (step) - one a card taken back or failed left
    # waiting stands as a card of its own
    for r in store._rows("SELECT * FROM review WHERE TaskId=? ORDER BY ReviewId", (int(tid),)):
        if r['ReviewId'] in past or obsolete_read(store, tid, r): continue
        if r['Kind'] == 'action' and (p := _p(r)).get('action') in HELD_ACTS and (u := by.get(f"rv{p.get('card')}")) and (r['Status'] != 'pending' or u['rows'][0]['Status'] in ('approved', 'edited')):
            u['rids'].append(r['ReviewId']); u['rows'].append(r); continue
        # ...a settled one by what it was while it waited: its run tells how many came together ("2 of 3")
        if r['Status'] != 'pending' and not r.get('DecidedAt'): continue
        if not in_line(r if r['Status'] == 'pending' else {**r, 'Status': 'pending', 'DecideNote': None}): continue
        if (k := _turn(r)) in by: u = by[k]
        else: u = by[k] = {'rids': [], 'rows': [], 'at': ep(r['CreatedAt'])}; out.append(u)
        u['rids'].append(r['ReviewId']); u['rows'].append(r)
    # ...A CLOSE-OUT IS PRESSED WITH THE REPLY IT CLOSES (ReviewDecision's `closeout`): one card with it, after it - alone only with no reply
    reply = lambda u: any(r['Kind'] not in ('action', 'slot') and r['Status'] == 'pending' for r in u['rows'])
    for co in [u for u in out if all(_closeout(r) and r['Status'] == 'pending' for r in u['rows'])]:
        if (to := next((u for u in out if u is not co and reply(u)), None)):
            to['rids'] += co['rids']; to['rows'] += co['rows']; out.remove(co)
    for u in out: u['done'] = None if any(r['Status'] == 'pending' or handed(r) for r in u['rows']) else max(ep(r.get('DecidedAt')) for r in u['rows'])
    rec = landing.record(store, int(tid)); q = rec.get('proposal') or {}
    if q.get('at') and not q.get('passed') and max(float(rec.get('moved') or 0), moved_on(store, int(tid))) <= ep(q['at']):
        went = str((rec.get('landed') or {}).get('at') or '')
        out.append({'rids': [LAND], 'rows': [], 'at': ep(q.get('first') or q['at']), 'done': ep(went) if went >= q['at'] else None, 'how': q.get('how')})
        out.sort(key=lambda u: u['at'])
    return out


# PRESSES IN A ROW WAKE THE AGENT ONCE (the owner, 2026-11-23; walk 6: told "you hear how they went once the last is pressed", it was woken by
# every Send and wrote one line each, saying what the card's own Sent already said). Each press is recorded on its card and the next stands at
# once; the agent is woken when the row is over, or at once by a press that fails (general.failed). THE ONE ANSWER to "is the row finished"
def row_over(store, tid: int) -> bool:
    "Does nothing on task `tid` wait for his press? A card its press handed to the agent to do (handed) is the agent's now, not his."
    return not any(u['rids'] == [LAND] or _waits(u) for u in state(store, tid)['units'])


def unheard(store, tid: int) -> list:
    "His yeses on cards of the line gone since task `tid`'s agent last answered that it was never woken on (general.TOLD), oldest first."
    from .general import TOLD, _last_answer
    told = lambda r: store._one("SELECT 1 AS x FROM audit WHERE EntityType='review' AND EntityId=? AND Action=? AND CreatedAt>=?", (r['ReviewId'], TOLD, r['DecidedAt']))
    return [r for r in store._rows("SELECT * FROM review WHERE TaskId=? AND Status IN ('approved','edited') AND DecidedAt>=? ORDER BY ReviewId",
                                   (int(tid), _last_answer(store, int(tid)) or '')) if in_line({**r, 'Status': 'pending', 'DecideNote': None}) and not told(r)]


# A CARD HIS INPUT GREYED THAT STILL STANDS COMES BACK ONLY BY ITS AGENT'S KEEP (the owner, 2026-11-26: "Nothing comes back automatically" -
# Taskuary's own re-raise at the turn's end stood the OLD post beside the card the turn had raised; 11-23, walk 6: the same three posts proposed
# four times, each a model call and one more grey copy). An input greys what it bears on (proposals.set_aside_drafts); whether one is still
# right is its agent's to judge, and `keep` raises it again as it was - no rewrite
# ...AS A NEW CARD UNDER THE LINE, NEVER LIVE AGAIN ABOVE IT (the owner, 2026-11-25: "Never bring back things on top. It's a chat."): the
# greyed one stays greyed where it stood, and is raised again once (again_of)
# ...AND AN ACT HIS PRESS HANDED TO ITS AGENT THAT CANNOT BE DONE COMES BACK (walk 7, 2026-11-23: Post via the browser on the X card,
# no X account to sign in with; it could not be withdrawn - "nothing unsent" - and every card behind it waited for good, the Reddit one greyed
# with no reason). Kept with `why`: the press it had ends failed where he pressed it, saying why, and the card stands again for his press -
# Post via the browser to try again, Dismiss to skip it - so the line moves on. His word to drop it is withdraw_draft's (verdicts.withdraw)
KEEP = ('Kept: {ids} stand{s} again under the newest line, as {it} was - nothing was rewritten.')
UNDONE = 'handed to its agent, which could not do it'
# ...A KEPT CARD IS EVERY COLUMN OF THE CARD (walk 24, 2026-11-25: copied by a list of names, a reply kept with two versions stood with one and
# no picker, and an act would have lost its `then`): all its row holds but what came of it - a column added later is a kept card's too
CAME_OF = frozenset(('ReviewId', 'TaskId', 'Status', 'FinalText', 'DecidedBy', 'DecidedAt', 'DecideNote', 'CreatedAt', 'DraftAt', 'DraftError', 'DraftNeeds', 'Stale',
                     'ActError', 'NotNeeded', 'Batch', 'DeliveryState', 'DeliveryClaim', 'DeliveryAttemptedAt', 'DeliveryEnvelope', 'DeliveryReceipt'))
IDS = r'\s*(?:rv)?\d+(?:\s*[,+]\s*(?:rv)?\d+)*\s*'      # 'rv12 + rv13': the ids of a card of many, its one handle


def named(store, tid: int, which: str) -> list:
    """[review id] of the one card on task `tid` that `which` names by what it is (the reply to a sender's address, or their first name) - a card of
    one is named, never numbered (walk 11: the agent told him it drafted the reply "(rv2)"); [] when none or several match."""
    from .proposals import SET_ASIDE
    k = ' '.join(str(which or '').split()).casefold()
    if not k: return []
    hit = [r['ReviewId'] for r in store._rows('SELECT * FROM review WHERE TaskId=? ORDER BY ReviewId DESC', (int(tid),))
           if ((r['Status'] == 'superseded' and r.get('DecideNote') == SET_ASIDE) or handed(r))
           and k in what(store, {'rids': [r['ReviewId']], 'rows': [r]}, True).casefold()]
    return hit[:1] if len(hit) == 1 else []


def asking(store, tid: int) -> bool:
    """Whether the task's agent's own question to the owner stands: asked in this turn (ask_owner's mark), or asked before and not yet answered.
    WHILE IT STANDS NOTHING IS RAISED UNDER IT, ON ANY ROAD (locked rule 4; walk 24, 2026-11-25: the agent's propose was refused under its
    question and Taskuary's own re-raise then stood a live card there) - the agent's call (agenttools) and `keep` both ask this."""
    from . import proposals, selfclose, taskstate
    return selfclose.asks_now(tid) or bool(taskstate.open_question(store, tid)) or bool(proposals.asks_waiting(store, tid))


ASKED = 'Greyed while your question stands - he cannot press it; it stands again only where you keep it (keep_card) once he has answered'
WAITS = 'your question to the owner stands - nothing is raised under it; a greyed card can be kept once he has answered'
def keep(store, tid: int, which, by: str = 'agent', why: str = '') -> dict:
    """Raise again each greyed card `which` names ('rv12 + rv13') on task `tid` as a new card, the same words and envelope, drawn under the
    newest line - and an act his press handed to its agent that it could not do (handed), with `why`, which its failed press then says.
    Never one that went, was turned down, is live or was raised again already; a held step is run again instead (its gate holds it anew).
    And none while the agent's question stands (asking)."""
    import re
    from . import bulkcard
    from .proposals import HELD_ACTS, SET_ASIDE, _action
    if asking(store, tid): return {'ok': False, 'why': WAITS}
    w = str(which or '')
    ids = list(dict.fromkeys(int(x) for x in re.findall(r'\d+', w))) if re.fullmatch(IDS, w, re.I) else named(store, tid, w)
    if not ids: return {'ok': False, 'why': 'name the greyed card as the screen fact names it (the reply to gail@northwind.example; a card of many: rv12 + rv13)'}
    kept, bad, batch = {}, [], {}
    for i in ids:
        r = store.get_review(i)
        if not r or r.get('TaskId') != int(tid): bad.append(f'rv{i}: no card of this task has that id'); continue
        if handed(r):
            if not (w := ' '.join(str(why or '').split())[:300]):
                bad.append(f'rv{i}: say in `why` what stopped it (no account to sign in with, the site refused) - his card says it'); continue
            p = {k: v for k, v in json.loads(r['FinalText']).items() if k != 'result'}
            if not store.review_unhanded(i, 'superseded', w, UNDONE): bad.append(f'rv{i}: it was done or settled meanwhile'); continue
            r = {**r, 'DraftText': json.dumps(p)}
        elif not (r['Status'] == 'superseded' and r.get('DecideNote') == SET_ASIDE):
            bad.append(f"rv{i}: not greyed by an input ({_card_status(r)}) - only a greyed card is kept; raise a new one where it is still needed"); continue
        elif (n := again_of(store, i)): bad.append(f'rv{i}: it stands again already, as rv{n}'); continue
        if r['Kind'] == 'action' and _action(r) in HELD_ACTS: bad.append(f'rv{i}: a step held for his press - run it again and Taskuary holds it anew'); continue
        rest = {k: v for k, v in r.items() if k not in CAME_OF}
        new = store.add_review({**rest, 'TaskId': int(tid), 'Status': 'pending'})
        if r.get('Batch'): rest['Batch'] = batch.setdefault(r['Batch'], bulkcard.new_key())
        # ...written now: a card is older than an input by when its words were written (proposals._older), so the kept one stands after it
        store._exec(f"UPDATE review SET DraftAt=CreatedAt, {', '.join(f'{k}=?' for k in rest)} WHERE ReviewId=?", (*rest.values(), new))
        store._review_changed(new); kept[i] = new
    if kept: store.audit('task', int(tid), 'cards_kept', by, 'agent', {'kept': {str(k): v for k, v in kept.items()}})
    one = len(kept) == 1
    says = KEEP.format(ids=what(store, {'rids': [v], 'rows': [store.get_review(v)]}, True) if one and (v := next(iter(kept.values())))
                       else ' + '.join(f'rv{v}' for v in kept.values()),
                       s='s' if one else '', it='it' if one else 'they')
    return {'ok': bool(kept), **({'kept': {f'rv{k}': f'rv{v}' for k, v in kept.items()}, 'says': says} if kept else {}), **({'why': '; '.join(bad)} if bad else {})}


def again_of(store, rid) -> int | None:
    "The card greyed card `rid` was raised again as (keep's record), or None."
    for a in store._rows("SELECT Detail FROM audit WHERE EntityType='task' AND Action='cards_kept' AND Detail LIKE ?", (f'%"{int(rid)}"%',)):
        if (n := (json.loads(a['Detail'] or '{}').get('kept') or {}).get(str(int(rid)))): return int(n)
    return None


def is_again(store, rid) -> bool:
    "Card `rid` is a greyed card Taskuary raised again (keep) - its words are the earlier turn's, never a draft a later turn wrote."
    return any(str(int(rid)) in [str(v) for v in (json.loads(a['Detail'] or '{}').get('kept') or {}).values()]
               for a in store._rows("SELECT Detail FROM audit WHERE EntityType='task' AND Action='cards_kept' AND Detail LIKE ?", (f'%{int(rid)}%',)))


def _card_status(r) -> str:
    from .conversation import _card
    return {'pending': 'it still waits for his press', 'superseded': 'taken back or replaced'}.get(s := _card(r)['status'], s.replace('_', ' '))


def state(store, tid: int) -> dict: return fresh(store, ('state', int(tid)), lambda: _state(store, tid))


def _stood(u: dict) -> bool:
    """Did this card stand for his press - waiting for it, or settled by it? Never one its agent or Taskuary took back, rewrote or moved past
    (design round 6, D6: three emails rewritten for a corrected figure, the first new one read "4 of 7" - the three dead ones counted)."""
    from .conversation import _card
    return u['done'] is None or not u['rows'] or any(not ((s := _card(r)['status']) in ('passed', 'withdrawn', 'superseded') or s == 'closed_unsent'
                                                         and r.get('DecidedBy') in ('agent', 'assistant', 'taskuary')) for r in u['rows'])


def _state(store, tid: int) -> dict:
    """The line on task `tid`: {'live': the front's ids or [], 'held': ids that wait behind it, 'n': the front's place in the run it is one
    of, 'of': that run's length, 'next': what comes next in words, 'units', 'runs': every run of the cards that stood (_runs), 'past': the
    cards the chat moved past (proposals.written_past), 'fronts': the ids of the first card that waits in each LATER run - each stands where
    it was raised, under the line of his that began its run}."""
    from .proposals import written_past
    us = _units(store, tid, past := written_past(store, int(tid)))
    waiting = [u for u in us if u['done'] is None]
    # ...the run it is one of: each card that stood for his press, raised while the one before it still waited or with nothing of his between
    runs = _runs(store, tid, [u for u in us if _stood(u)])
    if not waiting: return {'live': [], 'held': [], 'n': 0, 'of': 0, 'next': '', 'units': [], 'runs': runs, 'past': past, 'fronts': []}
    front = waiting[0]
    run = next(r for r in runs if any(x is front for x in r))
    n = next(i for i, x in enumerate(run) if x is front) + 1
    held = [x for u in waiting[1:] for x in u['rids']]
    # ...AND EACH PRESS BRINGS THE NEXT AT ONCE (the owner, 2026-11-20: asked to post to three platforms, one card stood and the rest never
    # appeared - the next was held while the agent went on from the press, and a turn that went on longer hid it): every card raised stands
    # queued, the front is drawn, and its agent hears the row once it is over (row_over)
    live = front['rids']
    return {'live': live, 'held': held, 'n': n, 'of': len(run), 'next': what(store, waiting[1]) if len(waiting) > 1 else '', 'units': waiting,
            'runs': runs, 'past': past, 'fronts': [u['rids'] for r in runs if (u := _front(r)) and u is not front]}


def _front(run: list) -> dict | None:
    "The card of a run that is in front: the first of it that waits, or None."
    return next((u for u in run if u['done'] is None), None)


def _runs(store, tid: int, us: list) -> list:
    """The cards that stood, oldest first, cut into runs: a card is one of the run before it when it was raised before that one was settled,
    AND ON THROUGH THE CARDS ITS AGENT RAISES AFTER A PRESS while nothing of his came between (decided 2026-11-20: "2 of 7" went on as "1 of 6"
    when the agent wrote the next letters after his Send) - only his line or a message that came in begins a new run.
    AND A RUN NEVER CROSSES HIS LINE (walk 24, 2026-11-25: an email raised after his answer became tab 2 of the card that stood above the
    answer, with nothing to press under it, and the one card moved down the chat when its front was pressed): a card raised after a line of
    his begins its own run under that line, whether or not the one above still waits (a stamp is a whole second: only a line surely between)."""
    heard = store._rows("SELECT At, Kind FROM heard WHERE TaskId=? AND Kind IN ('line','mail')", (int(tid),))
    ins, his = sorted(r['At'] for r in heard), [r['At'] for r in heard if r['Kind'] == 'line']
    def linked(a, b):
        if any(a['at'] + 1 <= x < b['at'] for x in his): return False
        return b['at'] <= (a['done'] or float('inf')) + 1 or not any((a['done'] or 0.) < x < b['at'] for x in ins)
    out = []
    for u in us:
        if out and linked(out[-1][-1], u): out[-1].append(u)
        else: out.append([u])
    return out


# WHAT IS ONE CARD, AND WHAT IS A TAB (the owner, 2026-11-26, taking back 11-25's "a run of cards is one card with tabs" - a routine change and
# a post stood as two tabs of one card): THE AGENT'S CALL DECIDES, never a count and never what the cards are about.
# - separate calls are separate cards, one after another (the line: its front drawn, the rest behind it) - never tabs of one another;
# - ONE call carrying a set (`items`, bulkcard.py - its rows share a Batch) is ONE card: where its items are the same act (one letter to many,
#   forty issues closed) the list card, one press doing them all with its progress on it; where they are DIFFERENT acts - the same post for
#   X, for Reddit and for LinkedIn - one card with a tab each (`sets`), each tab the card of its own act with its own press.
def is_set(rows: list) -> bool:
    "Are the rows of one call's card different acts (a tab each), not one act to many (the list)? By each row's own act, as it was filed."
    return all(r.get('Kind') == 'action' for r in rows) and len({_p(r).get('type') or _p(r).get('action') for r in rows}) > 1


def sets(store, tid: int) -> dict:
    """{its Batch: [{'key', 'rid', 'name', 'done', 'no'}]} for each card on task `tid` that is a set under tabs (is_set), its tabs in the order
    they were raised: `name` where it goes ('LinkedIn'), `done` once settled, `no` settled without going - his no, or a press that failed."""
    by = {}
    for r in store._rows('SELECT * FROM review WHERE TaskId=? AND Batch IS NOT NULL ORDER BY ReviewId', (int(tid),)): by.setdefault(r['Batch'], []).append(r)
    went = ('approved', 'edited', 'sent')
    return {k: [{'key': str(r['ReviewId']), 'rid': r['ReviewId'], 'name': tab(store, r), 'done': r['Status'] != 'pending' and not handed(r),
                 **({'no': True} if r['Status'] not in ('pending', *went) else {})} for r in rs] for k, rs in by.items() if is_set(rs)}


def tab(store, r: dict) -> str:
    "A tab's name: the network its post goes to ('LinkedIn'), else what its act is by its own name or words ('Push')."
    from .proposals import POSTS
    if (net := POSTS.get(_p(r).get('type'))): return net
    if (n := own_name(r)): return n
    w = what(store, {'rids': [r['ReviewId']], 'rows': [{**r, 'Batch': None}]})
    w = w[4:] if w.startswith('the ') else w
    return w[:1].upper() + w[1:]


def alone(s: dict) -> list:
    """The keys of the cards on the line `s` (state) that stand lit beside its front: the first that waits of each LATER run (state's
    `fronts`), which stands where it was raised, under the line of his that began its run."""
    return [str(f[0]) for f in s['fronts'] if f != [LAND]]


def own_name(r: dict) -> str:
    "An act's thing by its own name, as written ('northwind/ledger#31' - an issue or a pull request), else ''."
    p = _p(r) if r.get('Kind') == 'action' else {}
    return f"{p['repo']}#{p['number']}" if p.get('repo') and p.get('number') is not None else ''



def mark(store, tid: int, s: dict) -> None:
    """Each card that waits marked as it is first seen waiting, in the chat's ledger: one taken back before its turn came never stands
    (conversation.items). Written where the chat is read and where the agent is told its line - never by a read of what waits on him."""
    if (ids := [x for x in s['held'] if x != LAND]):
        with store.lock: store.cx.executemany("INSERT OR IGNORE INTO shown (TaskId, Key, Seq, Host) VALUES (?,?,0,'held')", [(int(tid), f'q:r:{x}') for x in ids]); store.cx.commit()



def held(store, tid: int) -> set:
    "The ids of task `tid`'s cards that wait their turn - drawn nowhere until it comes."
    return set(state(store, tid)['held']) if tid else set()


def what(store, u: dict, addr: bool = False) -> str:
    """A card in the owner's words: 'the email to Erin Blake', 'the reply to Gail Moreno', 'the push', 'delete the old export'. `addr`: as an
    agent is told it, each person with the address it went to ('the reply to gail@northwind.example (Gail Moreno)') - the screen names
    people, but an agent sends to addresses, and a name alone left it guessing which of two Gails the reply went to."""
    from . import landing
    if u['rids'] == [LAND]: return f"the {landing.HOW.get(u.get('how'), 'push').lower()}"
    rows = _waits(u) or u['rows']; r = rows[0]
    if r.get('Batch') and len(u['rows']) > 1:
        from .timewords import plural
        # ...as the card heads itself (bulkCard.countOf): "24 emails", "40 issues" - the noun of the act's own press words, else "steps"
        if r.get('Kind') == 'slot': return plural(len(rows), 'email')
        if r.get('Kind') != 'action': return f"{len(rows)} like {what(store, {'rids': [r['ReviewId']], 'rows': [{**r, 'Batch': None}]}, addr)}"
        from .connectorcatalog import action_for
        press = str((action_for(_p(r).get('type')) or {}).get('press') or '').split()
        return plural(len(rows), press[1] if len(press) == 2 else 'step')
    if r.get('Kind') == 'action':
        if (n := own_name(r)): return n                                     # ...an issue by its own name
        p = _p(r)
        from .proposals import SKILL
        if p.get('action') == SKILL: return 'the skill'
        from .proposals import act_words
        why = act_words(r.get('Reason'))
        # ...cut at a word, never mid-word ("so its effect is u" stood on the line, design round 6)
        return (why if len(why) <= 90 else why[:90].rsplit(' ', 1)[0].rstrip(',;:') + '…') or 'the next step'
    try: own = json.loads(r.get('Deliver') or '{}') or {}
    except (TypeError, ValueError): own = {}
    if isinstance(own, dict) and own.get('kind') == 'calendar': return 'the calendar answer'
    to = to_whom(store, r, addr)
    return f"the {'email' if r.get('Kind') == 'slot' else 'reply'}" + (f' to {to}' if to else '')


def to_whom(store, r: dict, addr: bool = False) -> str:
    """Whom card row `r` goes to - or went to - by name, as its card says it: every surface that names a card's recipient reads it here (the
    card, the agent, the phone's receipt - walk 10, 2026-11-23: the phone said "Sent to gail@..." for a reply that went to Paula)."""
    try: own = json.loads(r.get('Deliver') or '{}') or {}
    except (TypeError, ValueError): own = {}
    # ...WHERE IT WENT IS THE ONE ANSWER THE CARD READS (outbound.review_envelope): what went out once sent, else where it would go - walk 2,
    # 2026-11-19: the card said "Sent to Erin Blake" and the agent was told the reply went to Gail, and drafted an apology to her
    from .outbound import review_envelope
    try: env = review_envelope(store, r)
    except Exception: env = own if isinstance(own, dict) else {}
    to = env.get('to') if isinstance(env, dict) else None
    # ...BY NAME, NOT ADDRESS (the design walk, 2026-11-20: "next: the reply to gail@northwind.example"): each address as the mail, the org
    # chart or the directory knows its person (calwrite.name_of, the one that names people in titles), the address only where none does
    from .calwrite import name_of
    def who(x, n): return f'{x} ({n})' if addr and x and n and n != x else n or x
    to = ', '.join(who(x, name_of(store, x)) if '@' in str(x) else str(x) for x in (to if isinstance(to, list) else [to] if to else []))
    if not to and r.get('MessageId'):
        m = store.get_message(r.get('AnswersMid') or r['MessageId']) or {}; e = str(m.get('FromEmail') or '')
        to = who(e, name_of(store, e)) if '@' in e else m.get('FromName') or e
    return to


def _waits(u: dict) -> list:
    "The rows of a card that still wait - a bulk card part-run (a send that did not go, a stop) is what is left on it, not what it once held."
    return [r for r in u.get('rows') or [] if r.get('Status') == 'pending']


def line(s: dict) -> str:
    """What the live card says of the line, plain: '1 of 2 · next: the email to Erin', and the last of them '2 of 2' (the real-Claude walk,
    2026-11-19: the second letter stood with no count once the first went) - '' for a card alone in its line."""
    if not s['live'] or s['of'] < 2: return ''
    return f"{s['n']} of {s['of']}" + (f" · next: {s['next']}" if s['of'] > s['n'] and s['next'] else '')      # ...none where what follows it is settled already


SCREEN_HEAD = ("WHAT THE OWNER'S SCREEN SHOWS ON THIS TASK NOW, AND WHAT CAME OF EACH CARD (Taskuary's record - a card it does not name is not "
               'on his screen; his own line greys what waited - never his answer to your question - a message only the cards to its sender or on '
               'its thread, and a greyed card stays greyed where it stood unless you keep it):')
NOTHING = 'Nothing waits for his press.'
SETTLED = 6                     # the settled cards told, newest last: enough that a sent letter is never drafted again


def _words(r) -> str:
    "A card's own words, as its card shows them: what went, else what waits - '' for an act with none."
    if r.get('Kind') == 'action': w = (p := _p(r)).get('text') or p.get('body') or ''
    else: w = r.get('FinalText') or r.get('DraftText') or ''          # ...his own words where he changed them, sent or not
    w = ' '.join(str(w).split())
    return f'"{w[:300]}{"…" if len(w) > 300 else ""}"' if w else ''


def outcome(r) -> str:
    """What came of his last press on a card that still waits - '' when it went or he has not pressed. A send that MAY have gone is never
    sent or set up again unasked; one that did not go stays for his Send; an act a restart cut may have been done."""
    from .general import ACT_CUT
    err, why = str(r.get('ActError') or ''), _flat(r.get('ActError') or r.get('Reason') or 'no reason was given')
    if err.startswith(ACT_CUT): return ' - Taskuary restarted while his press ran: it MAY have been done, so check before anything else'
    if err: return f' - his press failed ({why}) and nothing of it was done'
    if r.get('DeliveryState') == 'unknown': return f' - his Send MAY have gone ({why})'
    if r.get('DeliveryState') == 'failed': return f' - his Send did not go ({why})'
    return ''


def _result(r) -> str:
    "What a done act gave back, as its card says it - its link."
    from .verdicts import in_words
    try: got = (json.loads(r.get('FinalText') or '{}') or {}).get('result')
    except (TypeError, ValueError, AttributeError): got = None
    return in_words(got, 200) if got else ''


def screen(store, tid: int, skip=()) -> str:
    """THE ONE FACT OF WHAT STANDS ON THE OWNER'S SCREEN FOR TASK `tid`, AND WHAT CAME OF EACH CARD (the design round, 2026-11-18: an agent told
    him "each has its own Post button" when one stood and his next line had greyed it): the line the page draws (state), each card greyed
    where the chat moved past it (written_past, proposals.passed_why) and each settled one by the state the chat draws it in
    (conversation._card) - sent, done with its link, failed and why, turned down. Told at the head of every turn and after every press and
    every card raised. `skip`: review ids said elsewhere in the same words (the reply draft's own block). '' on a task that never had a card."""
    from .continuity import clock
    from .conversation import _card
    from .proposals import SET_ASIDE, UNTIL, comes_back, passed_why
    from . import general, landing
    st = state(store, tid); mark(store, tid, st)
    live, held, past, front = set(st['live']), set(st['held']), st['past'], st['units'][0]['rids'] if st['units'] else []
    since = str(general._last_answer(store, int(tid)) or '')
    waiting, settled, seen = [], [], set()
    def name(u, r):
        # ...a card of one by what it is, never its number (named); a card of many by the ids its tools take, its name beside them
        ids = [w['ReviewId'] for w in _waits(u)] or u['rids']
        return (f"{' + '.join(f'rv{x}' for x in ids)}, {what(store, u, True)}" if len(u['rows']) > 1 else what(store, u, True)) + (f': {w}' if r and (w := _words(r)) else '')
    def greyed(r, n):
        # ...one his line greyed is its agent's to keep (keep); a held step, one a message passed or its turn finished without, never
        # ...and while its question stands, the truth of that wait: he cannot press it, and nothing brings it back before his answer's turn ends
        # (the owner, 2026-11-26: "it should not say it's waiting if you can't press it")
        head = ((ASKED if asking(store, tid) else UNTIL.capitalize()) if comes_back(store, r) else 'Greyed by an input your turn has not heard yet' if r.get('Status') == 'pending' else 'Greyed, will not go')
        settled.append((r.get('DecidedAt') or r.get('CreatedAt') or '', head + (f' ({w})' if (w := passed_why(store, r)) else '') + f': {n}'))
    for u in _units(store, tid, set()):
        seen.update(u['rids'])
        if set(u['rids']) & set(skip): continue
        r = (_waits(u) or u['rows'] or [{}])[0]; n, ids = name(u, r), set(u['rids'])
        if u['done'] is None:
            if (sp := step(u)):
                # ...its held step is HIS now, on the card he pressed - never "do it", never a card of its own (walk 22: both agents said one waited)
                waiting.append(f"Waiting for his press now, drawn on the card he pressed as its last step ({what(store, {'rids': u['rids'][:1], 'rows': u['rows'][:1]}, True)}): "
                               f"{step_says(sp)}")
            elif (h := next((x for x in u['rows'] if handed(x)), None)):
                waiting.append(f"Handed to you by his press {clock(h.get('DecidedAt'))}, NOT done yet - do it; it is done once its own final press "
                               f"has gone, and the next card waits until then. One you cannot do now: keep_card it with `why` (it stands again "
                               f"for his press); one he drops: withdraw_draft it: {name(u, h)}")
            elif r and ids <= past: greyed(r, n)
            elif ids & live or u['rids'] in st['fronts']:
                # ...on the buttons its card draws where it has no Send (card.presses; walk 21: "ready to send" over Copy + Redraft)
                from . import card
                ps = card.presses(store, r) if r and r.get('Kind') != 'action' else ('approve',)
                shown = '' if 'approve' in ps else f" (its card: {card.press_words({'kind': card.SEND, 'presses': ps})})"
                waiting.append(f'Waiting for his press now{outcome(r)}: {n}{shown}')
            elif u['rids'] == front: waiting.append(f'Comes forward once your turn ends (you are going on from his last press): {n}')
            # ...A CARD BEHIND THE FRONT COMES ONCE THE ONE IN FRONT IS PRESSED (separate calls are separate cards, one after another)
            elif ids & held: waiting.append(f'Raised, and behind the card in front - it comes forward at his press on that one: {n}')
            continue
        s, at = (_card(r)['status'] if r else 'approved'), clock(r.get('DecidedAt')) if r else ''
        if s == 'passed': str(r.get('DecidedAt') or '') >= since and greyed(r, n)
        elif s == 'failed': settled.append((r['DecidedAt'], f"Failed {at}, nothing went ({_flat(r.get('ActError') or r.get('DecideNote'))}): {n}"))
        elif s in ('approved', 'edited', 'sent'):
            got = _result(r) if r else ''
            settled.append((r.get('DecidedAt') or '', f"{'Done' if r.get('Kind') == 'action' or not u['rows'] else 'Sent'} {at}"
                                                      f"{' (he changed your words first)' if s == 'edited' else ''}: {n}" + (f' - {got}' if got else '')))
        elif s == 'rejected': settled.append((r['DecidedAt'], f'Turned down by him {at}: {n}'))
        elif s == 'closed_unsent' and r.get('DecidedBy') not in ('agent', 'assistant'): settled.append((r['DecidedAt'], f'Closed by him without sending {at}: {n}'))
    # ...and Taskuary's own cards the chat moved past (a close-out, the landing question): greyed on his screen as the agent's are
    for r in store._rows("SELECT * FROM review WHERE TaskId=? AND Status='superseded' AND DecideNote=? AND DecidedAt>=?", (int(tid), SET_ASIDE, since)):
        if r['ReviewId'] not in seen | set(skip): greyed(r, name({'rids': [r['ReviewId']], 'rows': [r]}, r))
    q = landing.record(store, int(tid)).get('proposal') or {}
    if (gone := str(q.get('passed') or '')) and gone >= since:
        settled.append((gone, f"Greyed, will not go (the chat moved on past it): the {landing.HOW.get(q.get('how'), 'push').lower()} question you raised"))
    # ...AND A STEP HANDED TO HIM ON A PAGE IS WAITING ON HIM TOO (walk 9, 2026-11-23: "Nothing waits for his press" while the robot check it had
    # handed him was still owed - the agent lost it): read off the one record of what he was asked (workerstate's open requests), as the page is
    waiting += [f"Handed to him on the page, NOT done yet: {_flat(q.get('text'))}" for q in on_page(store, tid)]
    if not (waiting or settled): return ''
    lines = [f'- {x}' for _, x in sorted(settled, key=lambda p: str(p[0]))][-SETTLED:] + ([f'- {x}' for x in waiting] or [NOTHING])
    return '\n'.join([SCREEN_HEAD, *lines])


def on_page(store, tid: int) -> list:
    "The steps handed to him on a page that still wait - a sign-in, his turn (workerstate.ask_of) - as their open requests."
    from . import workerstate as ws
    try: return [q for q in ws.status(store, int(tid))['requests'] if q.get('ask') in ('signin', 'turn')]
    except Exception as e:
        from loguru import logger
        logger.debug(f'cardqueue: the steps handed over on task {tid} were not read - {e}'); return []


def _flat(x, n: int = 200) -> str: return ' '.join(str(x or '').split())[:n]

