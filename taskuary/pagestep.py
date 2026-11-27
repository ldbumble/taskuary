"""A STEP HANDED TO HIM ON A PAGE IS A CARD LIKE ANY OTHER (the owner, 2026-11-25: "the browser should be treated like a card, so only one at a
time. You can't create an artifact, then an html thing, then do nothing" - an agent wrote "I also opened a sign-in card for whois.com" under
its answer, the pane read "opening browser", and no card stood anywhere). A sign-in or a your-turn on the agent's page was a worker request
drawn only on the browser pane: outside the line of cards, so it opened beside whatever else waited, and where the pane could not draw it
nothing said it was owed.

Its card is a review row (`page_step`) made here from the request, and settled here when the request ends - so it stands in the ONE line
(cardqueue): one at a time with every other card, a tab of its run, the step of the card whose browser road it is on (cardqueue.step), on
the phone and in what the agent is told. The request stays the record of the step itself (browserview.hand_over, signin.needs) and its
hand-back the one road (workerstate.answer): the card's I'm done presses that. The pane opens for it only while its card is in front
(shown); behind another card it waits its turn, pane and all."""
import json

ACT = 'page_step'
DONE_ON_PAGE, GONE = 'done on the page', 'the step was taken back'


def _open(store, tid: int) -> list:
    from . import workerstate as ws
    return [r for r in ws.open_requests(ws.events(store, int(tid))) if ws.ask_of(r['RequestId'])['ask'] in ('signin', 'turn')]


def _cards(store, tid: int) -> list:
    from .proposals import _action
    return [r for r in store._rows("SELECT * FROM review WHERE TaskId=? AND Kind='action' AND Status='pending' ORDER BY ReviewId", (int(tid),)) if _action(r) == ACT]


def card_of(store, tid: int, request_id) -> dict | None:
    "The waiting card of the page step `request_id` on task `tid`, or None."
    return next((r for r in _cards(store, tid) if json.loads(r['DraftText']).get('request') == str(request_id)), None)


def card_id(store, tid: int, request_id) -> int | None:
    "The card of the page step `request_id` on task `tid`, whatever became of it - its press is said by it, never by a line under it."
    rows = store._rows("SELECT ReviewId, DraftText FROM review WHERE TaskId=? AND Kind='action' AND DraftText LIKE ?", (int(tid), f'%"{ACT}"%'))
    return next((r['ReviewId'] for r in rows if json.loads(r['DraftText'] or '{}').get('request') == str(request_id)), None)


def sync(store, tid: int) -> None:
    """Each step handed to him on a page has its card, and a card whose step has ended is settled by how it ended: answered (his I'm done, the
    page moving on, the sign-in going in) it is done; taken back or overtaken, withdrawn. Derived from the requests as they stand, on every
    road that raises or closes one - called where the line is written (chatlog.advance) and where a step is handed over."""
    from . import proposals, workerstate as ws
    open_, cards = {r['RequestId']: r for r in _open(store, tid)}, _cards(store, tid)
    have = {json.loads(c['DraftText']).get('request') for c in cards}
    # ...ONE CARD PER STEP, WHATEVER CAME OF IT (walk 25, 2026-11-26: his Dismiss settles the card, then closes the step - a read between the
    # two found the step open with no card waiting and raised a second, drawn greyed under the one he had dismissed): a step is the event
    # that asked it (`ev`), and one whose card was ever made has it
    made = {p.get('ev') for r in store._rows("SELECT DraftText FROM review WHERE TaskId=? AND Kind='action' AND DraftText LIKE ?", (int(tid), f'%"{ACT}"%'))
            if isinstance(p := json.loads(r['DraftText'] or '{}'), dict)}
    for rid, r in open_.items():
        if rid in have or r['Id'] in made: continue
        site, signin = ws.ask_of(rid)['site'], ws.ask_of(rid)['ask'] == 'signin'
        # ...and a sign-in the fill page can type carries its way there (`fill`): the card is the one place the step is said, link and all
        from .signin import fills
        proposals.queue(store, int(tid), {'action': ACT, 'request': rid, 'ev': r['Id'], 'sid': str(r.get('Sid') or ''), 'what': ' '.join(str(r.get('Text') or '').split())[:300],
                                          **({'site': site} if site else {}), **({'fill': True} if signin and fills(r.get('Text')) else {})}, 'taskuary')
    if not (gone := [c for c in cards if json.loads(c['DraftText']).get('request') not in open_]): return
    from . import browsergate, browserview, signin
    how = {e['RequestId']: str(e.get('Text') or '') for e in ws.events(store, int(tid)) if e['Kind'] == 'answered'}
    for c in gone:
        ok = how.get(json.loads(c['DraftText']).get('request')) in (browserview.TURN_DONE, browsergate.MOVED_ON, signin.DONE)
        store.decide_review(c['ReviewId'], 'approved' if ok else 'superseded', None, 'taskuary', note=DONE_ON_PAGE if ok else GONE)


def shown(store, tid: int, ask: dict | None) -> dict | None:
    "`ask` as the page may draw it: a step on a page only while its card is in front of the line - behind another card it waits its turn."
    from . import cardqueue, workerstate as ws
    if not ask or ws.ask_of(ask.get('request_id'))['ask'] == 'question': return ask
    if not (c := card_of(store, tid, ask.get('request_id'))): sync(store, tid); c = card_of(store, tid, ask.get('request_id'))
    return None if c and c['ReviewId'] in cardqueue.held(store, tid) else ask


def place(store, tid: int, request_id) -> str:
    "Where the step's card stands, as its agent is told it: on his screen with its page, or in line behind what waits."
    from . import cardqueue
    if not (c := card_of(store, tid, request_id)): return ''
    st = cardqueue.state(store, tid)
    if c['ReviewId'] in st['live']: return 'Its card is on his screen now, with the page open beside it.'
    n = next((i for i, u in enumerate(st['units'], 1) if c['ReviewId'] in u['rids']), 0)
    return (f"Its card is in line, {n} of {len(st['units'])}: it and its page come to his screen once what is in front of it "
            f"({cardqueue.what(store, st['units'][0], True)}) is pressed.")


# ── his press on the card: the gate a held act has (proposals._gate) ─────────────────────────────────────────────────────────────────────────
def perform(store, tid: int, p: dict, run=None) -> dict:
    "His I'm done on the card: the step's own hand-back (workerstate.answer), which closes it and tells its agent once."
    from . import browserview, workerstate as ws
    from .signin import DONE
    rid = str(p.get('request') or '')
    signin = ws.ask_of(rid)['ask'] == 'signin'
    out = ws.answer(store, int(tid), rid, DONE if signin else '', 'owner', press=not signin)
    if not out.get('delivered') and out.get('state') != 'resolved': raise RuntimeError(out.get('why') or 'the agent could not be told')
    return {'performed': f"told the agent: {browserview.TURN_DONE}"}


def declined(store, tid: int, p: dict) -> None:
    "His Dismiss: the step is closed undone and its agent told it was not done, as his own no."
    from . import browsergate
    browsergate.not_pressed(store, int(tid), str(p.get('request') or ''), 'they dismissed its card', his=True)
