"""ONE CARD AT A TIME (the owner, 2026-11-16: "where there are 2 action cards, like approve push then email, it should wait on each approval
step or action card, so the agent should wait on it and then go to next steps ... action cards should hold up the agent until it's completed.
In chat flow it makes more sense"). Every card on a task - a reply or an email to Send, an act to Approve (a push, a PR, a post, a SQL write,
a held step), a calendar answer, the landing question - stands in ONE line, in the order it was raised. Only its front is live; the rest are
held: drawn nowhere, named on the front as what comes next. One comes forward the moment the owner has pressed the one before it; the agent
hears the row once it is over (row_over), at once where a press failed, and from a no where cards still stand behind it (said_no) - it then
lets the rest stand, changes them, or takes them back. A press never sends or closes another card; nothing goes without its own press.

Plain code, read wherever a card is drawn, listed or told: the chat's list (conversation.items), the page's detail (server.task_detail), what
waits on the owner (store.waiting_reviews), and what its agent hears (agenttools, general.latest_block, general.approved/failed)."""
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
    v = fn(); _SEEN[k] = (w, now, v, weakref.ref(store)); return v


def _p(r) -> dict:
    try: d = json.loads(r.get('DraftText') or '{}') or {}
    except (TypeError, ValueError): d = {}
    return d if isinstance(d, dict) else {}


def handed(r: dict) -> bool:
    """PRESSED IS NOT DONE (walk 6, 2026-11-23: Post via the browser on a LinkedIn card approved it, and its agent was told "Done 7:31 AM: post to
    LinkedIn" in the very message asking it to go and post it; the X card came forward as if it had gone, and the Assistant's list of what
    waits left it out). THE ONE STATE of a press that handed its act to the agent to do - pressed, not yet done - read by the line (the next
    card waits behind it), the agent's screen fact and what the Assistant says a task holds (concierge.owed_items). Cleared by its real
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
    return [r['ReviewId']]


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
    """A card of the line: one the owner presses, and the agent's or triage's to raise - never a close-out, a playbook or a workflow's own step
    (Taskuary's, beside the reply - proposals._older's rule), an email he wrote himself, nor one nobody has written (a reply owed, a to-do's email)."""
    from .conversation import unwritten
    from .proposals import CLOSEOUT, PLAYBOOKS, passed
    if passed(r) or unwritten(r): return False
    if r['Kind'] == 'slot': return bool(str(r.get('DraftText') or '').strip()) and not str(r.get('Reason') or '').startswith('your email')
    if r['Kind'] == 'action':
        p = _p(r)
        return not (p.get('closeout') or p.get('action') in CLOSEOUT or p.get('action') in PLAYBOOKS or p.get('block')
                    or str(r.get('Reason') or '').startswith('the workflow'))
    return True


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
    from .proposals import moved_on
    out, by = [], {}
    # ...A STEP HELD WHILE A PRESSED ACT IS UNDER WAY IS THAT ACT'S OWN NEXT PRESS (his live app, 2026-11-23: Post via the browser on the X card, the
    # agent signed in and wrote the post, and the gate held its final Post - queued as a card of its own behind the Reddit and LinkedIn cards, so
    # Reddit stood in front, the browser said nothing waited on him, and the agent ended on "I'll bring you the link"): it joins the card he
    # pressed, which stays in front until its act is done
    fl = in_flight(store, tid); fl_at = ep(fl.get('DecidedAt')) if fl else None
    for r in store._rows("SELECT * FROM review WHERE TaskId=? ORDER BY ReviewId", (int(tid),)):
        if r['ReviewId'] in past or obsolete_read(store, tid, r): continue
        if fl and r['ReviewId'] > fl['ReviewId'] and r['Kind'] == 'action' and _p(r).get('action') == 'browser_act' and ep(r['CreatedAt']) >= fl_at:
            u = by.get(f"rv{fl['ReviewId']}")
            if u: u['rids'].append(r['ReviewId']); u['rows'].append(r); continue
        # ...a settled one by what it was while it waited: its run tells how many came together ("2 of 3")
        if r['Status'] != 'pending' and not r.get('DecidedAt'): continue
        if not in_line(r if r['Status'] == 'pending' else {**r, 'Status': 'pending', 'DecideNote': None}): continue
        if (k := _turn(r)) in by: u = by[k]
        else: u = by[k] = {'rids': [], 'rows': [], 'at': ep(r['CreatedAt'])}; out.append(u)
        u['rids'].append(r['ReviewId']); u['rows'].append(r)
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


def unheard(store, tid: int) -> bool:
    "Has a yes of his on a card of the line gone since task `tid`'s agent last answered, told to nobody yet (general.TOLD)?"
    from .general import TOLD, _last_answer
    told = lambda r: store._one("SELECT 1 AS x FROM audit WHERE EntityType='review' AND EntityId=? AND Action=? AND CreatedAt>=?", (r['ReviewId'], TOLD, r['DecidedAt']))
    return any(in_line({**r, 'Status': 'pending', 'DecideNote': None}) and not told(r) for r in store._rows(
        "SELECT * FROM review WHERE TaskId=? AND Status IN ('approved','edited') AND DecidedAt>?", (int(tid), _last_answer(store, int(tid)) or '')))


def state(store, tid: int) -> dict: return fresh(store, ('state', int(tid)), lambda: _state(store, tid))


def _stood(u: dict) -> bool:
    """Did this card stand for his press - waiting for it, or settled by it? Never one its agent or Taskuary took back, rewrote or moved past
    (design round 6, D6: three emails rewritten for a corrected figure, the first new one read "4 of 7" - the three dead ones counted)."""
    from .conversation import _card
    return u['done'] is None or not u['rows'] or any(not ((s := _card(r)['status']) in ('passed', 'withdrawn', 'superseded') or s == 'closed_unsent'
                                                         and r.get('DecidedBy') in ('agent', 'assistant', 'taskuary')) for r in u['rows'])


def _state(store, tid: int) -> dict:
    """The line on task `tid`: {'live': the front's ids or [], 'held': ids that wait behind it, 'n': the front's place in the run it is one
    of, 'of': that run's length, 'next': what comes next in words, 'units', 'past': the cards the chat moved past (proposals.written_past)}."""
    from .proposals import written_past
    us = _units(store, tid, past := written_past(store, int(tid)))
    waiting = [u for u in us if u['done'] is None]
    if not waiting: return {'live': [], 'held': [], 'n': 0, 'of': 0, 'next': '', 'units': [], 'past': past}
    front = waiting[0]
    # ...the run it is one of: the cards before it that were raised while the one before them still waited - each one that stood for his press
    us = [u for u in us if _stood(u)]
    i = us.index(front); n = 1
    # ...AND ON THROUGH THE CARDS ITS AGENT RAISES AFTER A PRESS, while nothing of his came between (decided 2026-11-20: "2 of 7" went on as
    # "1 of 6" when the agent wrote the next letters after his Send): only his line or a message that came in begins a new run
    ins = sorted(r['At'] for r in store._rows("SELECT At FROM heard WHERE TaskId=? AND Kind IN ('line','mail')", (int(tid),)))
    between = lambda a, b: any(a < x < b for x in ins)
    while i - n >= 0 and (us[i - n + 1]['at'] <= (us[i - n]['done'] or float('inf')) + 1
                          or not between(us[i - n]['done'] or 0., us[i - n + 1]['at'])): n += 1
    held = [x for u in waiting[1:] for x in u['rids']]
    # ...AND EACH PRESS BRINGS THE NEXT AT ONCE (the owner, 2026-11-20: asked to post to three platforms, one card stood and the rest never
    # appeared - the next was held while the agent went on from the press, and a turn that went on longer hid it): every card raised stands
    # queued, the front is drawn, and its agent hears the row once it is over (row_over)
    live = front['rids']
    return {'live': live, 'held': held, 'n': n, 'of': n + len(waiting) - 1, 'next': what(store, waiting[1]) if len(waiting) > 1 else '', 'units': waiting, 'past': past}


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
        if (p := _p(r)).get('repo') and p.get('number') is not None: return f"{p['repo']}#{p['number']}"       # ...an issue by its own name
        why = ' '.join(str(r.get('Reason') or '').split())
        for lead in ('the agent proposes to ', 'the workflow asks to '): why = why[len(lead):] if why.lower().startswith(lead) else why
        why = why.split(': ', 1)[1] if why.startswith('held before it ran') and ': ' in why else why
        why = why.split(' - ')[0]
        # ...cut at a word, never mid-word ("so its effect is u" stood on the line, design round 6)
        return (why if len(why) <= 90 else why[:90].rsplit(' ', 1)[0].rstrip(',;:') + '…') or 'the next step'
    try: own = json.loads(r.get('Deliver') or '{}') or {}
    except (TypeError, ValueError): own = {}
    if isinstance(own, dict) and own.get('kind') == 'calendar': return 'the calendar answer'
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
    if not to and r.get('MessageId'): m = store.get_message(r.get('AnswersMid') or r['MessageId']) or {}; to = who(m.get('FromEmail') or '', m.get('FromName') or '')
    return f"the {'email' if r.get('Kind') == 'slot' else 'reply'}" + (f' to {to}' if to else '')


def _waits(u: dict) -> list:
    "The rows of a card that still wait - a bulk card part-run (a send that did not go, a stop) is what is left on it, not what it once held."
    return [r for r in u.get('rows') or [] if r.get('Status') == 'pending']


def line(s: dict) -> str:
    """What the live card says of the line, plain: '1 of 2 · next: the email to Erin', and the last of them '2 of 2' (the real-Claude walk,
    2026-11-19: the second letter stood with no count once the first went) - '' for a card alone in its line."""
    if not s['live'] or s['of'] < 2: return ''
    return f"{s['n']} of {s['of']}" + (f" · next: {s['next']}" if s['of'] > s['n'] else '')


SCREEN_HEAD = ("WHAT THE OWNER'S SCREEN SHOWS ON THIS TASK NOW, AND WHAT CAME OF EACH CARD (Taskuary's record - a card it does not name is not "
               'on his screen; never say otherwise, and name a card by what it is, never by where it stands). Take back or replace one the newest '
               'message changes; one greyed or turned down is raised again only as a new card:')
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
    if r.get('DeliveryState') == 'unknown': return f' - his Send MAY have gone ({why}): never send it or set it up again unless he asks'
    if r.get('DeliveryState') == 'failed': return f' - his Send did not go ({why}); never set it up again'
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
    from .proposals import SET_ASIDE, passed_why
    from . import general, landing
    st = state(store, tid); mark(store, tid, st)
    live, held, past, front = set(st['live']), set(st['held']), st['past'], st['units'][0]['rids'] if st['units'] else []
    since = str(general._last_answer(store, int(tid)) or '')
    waiting, settled, seen = [], [], set()
    def name(u, r):
        ids = [w['ReviewId'] for w in _waits(u)] or u['rids']
        return (f"{' + '.join(f'rv{x}' for x in ids)}, {what(store, u, True)}" if u['rows'] else what(store, u, True)) + (f': {w}' if r and (w := _words(r)) else '')
    def greyed(r, n): settled.append((r.get('DecidedAt') or r.get('CreatedAt') or '', f"Greyed, will not go{f' ({w})' if (w := passed_why(store, r)) else ''}: {n}"))
    for u in _units(store, tid, set()):
        seen.update(u['rids'])
        if set(u['rids']) & set(skip): continue
        r = (_waits(u) or u['rows'] or [{}])[0]; n, ids = name(u, r), set(u['rids'])
        if u['done'] is None:
            if (h := next((x for x in u['rows'] if handed(x)), None)):
                waiting.append(f"Handed to you by his press {clock(h.get('DecidedAt'))}, NOT done yet - do it; it is done once its own final press "
                               f"has gone, and the next card waits until then: {name(u, h)}")
            elif r and ids <= past: greyed(r, n)
            elif ids & live:
                waiting.append(f'Waiting for his press now{outcome(r)}: {n}')
            elif u['rids'] == front: waiting.append(f'Comes forward once your turn ends (you are going on from his last press): {n}')
            elif ids & held: waiting.append(f'Not on his screen yet - it comes forward once the one before it is pressed (after an act, once you have heard how it went): {n}')
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
    if not (waiting or settled): return ''
    lines = [f'- {x}' for _, x in sorted(settled, key=lambda p: str(p[0]))][-SETTLED:] + ([f'- {x}' for x in waiting] or [NOTHING])
    return '\n'.join([SCREEN_HEAD, *lines])


def once(facts: str, said: str) -> str:
    """`facts` (a turn's, latest_block) less the screen fact when `said` - the note the same turn carries, a press told back - says it
    already: a press woke the agent with the screen in its note, and the turn's facts said it again above it."""
    if SCREEN_HEAD not in (said or '') or SCREEN_HEAD not in (facts or ''): return facts
    return '\n\n'.join(p for p in facts.split('\n\n') if not p.startswith(SCREEN_HEAD))


def _flat(x, n: int = 200) -> str: return ' '.join(str(x or '').split())[:n]


def said_no(store, rv: dict, verb: str, actor: str = 'owner') -> str:
    """A NO DOES NOT CARRY THE LINE ON BY ITSELF (the owner, 2026-11-16): his no to a card with others behind it wakes its agent, told whose no
    it was, to decide what of the rest still stands - what it leaves is shown once its turn ends. 'told', 'woke' or '' (nothing waits)."""
    from . import general
    from .proposals import HELD_ACTS
    tid = rv.get('TaskId')
    # ...(a held step turned down tells its agent by its own road, the gate's; and Close without sending a reply closes the task)
    if _p(rv).get('action') in HELD_ACTS or verb == 'close_unsent' and rv.get('Kind') != 'slot': return ''
    # ...and a no that ends a row whose yeses woke nobody (row_over) is the row's one wake
    if not tid or not (state(store, tid)['units'] or unheard(store, tid)): return ''
    no = {'reject': 'turned down', 'no_reply': 'said no reply is needed for', 'close_unsent': 'closed without sending', 'close_pr': 'turned down'}.get(verb, 'turned down')
    return general.to_agent(store, tid, f"The owner {no} rv{rv['ReviewId']} ({what(store, {'rids': [rv['ReviewId']], 'rows': [rv]}, True)}) - their own no.\n\n{screen(store, tid)}", actor,
                        heard=lambda how: store.audit('review', int(rv['ReviewId']), general.TOLD, actor, 'system', {'task': int(tid), 'how': how, 'no': verb}))
