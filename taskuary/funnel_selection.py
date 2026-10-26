"""A captured, side-effect-free selection from the legacy funnel.

This is an optimistic concurrency seam for the current funnel policy.  It does
not introduce canonical processing identities or redefine read/actionability.
The server can show a capture to a client, reject a stale echo before effects,
and hand the exact captured item to the concierge without selecting again.
"""
from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta

from .funnel_presentation import detach, item_revision


_SCHEMA = "taskuary.funnel.selection.v1"


def _canonical(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)


def _digest(value) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class SelectionCapture:
    """The exact pile, item and batch membership approved by one selection read."""

    revision: str
    scope: dict
    pile: dict
    selected: dict | None
    member_keys: tuple[str, ...]
    pending: dict


class SelectionStale(RuntimeError):
    """The client or an in-flight model turn refers to an older selection."""

    def __init__(self, fresh: SelectionCapture, requested_key=None):
        self.capture = fresh
        self.detail = {
            "code": "selection_stale",
            **selection_fields(fresh),
            "requested_next_key": requested_key,
            "retryable": True,
        }
        super().__init__("the funnel selection changed; refresh before moving on")


class SelectionUnavailable(RuntimeError):
    """A required native worker observation failed; do not select from guessed state."""

    def __init__(self, reason="worker attention is unavailable"):
        self.detail = {
            "code": "selection_unavailable",
            "error": str(reason),
            "retryable": True,
        }
        super().__init__(str(reason))


def _scope(*, only=None, include_surfaced=False, exclude=None) -> dict:
    return {
        "only": str(only) if only is not None else None,
        "include_surfaced": bool(include_surfaced),
        "exclude": str(exclude) if exclude is not None else None,
    }


def _eligible(items: list[dict], scope: dict, now: datetime) -> list[dict]:
    # Import lazily: funnel owns the unchanged legacy policy and imports this
    # module only from its public capture wrapper.
    from . import funnel

    exclude = scope["exclude"]
    excluded_keys = ({key for key in exclude[5:].split(",") if key}
                     if exclude and exclude.startswith("fyis:") else {exclude})
    ready = [
        item for item in items
        if item.get('actionable', True)
        and not item.get("settling")
        # ...a task an agent is WORKING is walked like every other task, in the rail's order (the owner, 2026-10-21)
        and not funnel._not_yet(item)
        and item.get("key") not in excluded_keys
        and not excluded_keys.intersection(item.get('aliases', []))
        # the mark IS the return clock (processing_unread: this_walk / RETURN_MINUTES) - no second cooldown
        # here, or the walk would take a waving agent back while the rail still showed it as passed.
        # ...and only a PUT-DOWN mark holds it: Next or Remind me. Shown is not acted on - four open tasks sat
        # under Tasks, each merely shown once, and the walk said there was nothing to walk through (the
        # owner, 2026-10-13: "before you hit next it should not be counted as read no? until it's acted on?")
        and (scope["include_surfaced"] or not item.get("put_down"))
    ]
    return ready


def below(items: list[dict], ready: list[dict], exclude, place=None, at_key=None) -> list[dict] | None:
    """NEXT WALKS DOWN THE LINE (the owner, 2026-10-22: "if I click on the bottom one then hit Next it should go to Reports, not jump
    back to Tasks. It should always be in order"): the walkable rows BELOW the one on the table (`exclude`, a row or an fyi batch),
    in the rail's order - or below the walk's place (funnel.walk_place) when that row has left the rail (closed) or the table is
    empty after a close. None at a walk's start: nothing is above, the walk takes the top (first_at_start). Rows above that were
    never reached come up again with the next walk (funnel.new_walk), never in the middle of this one.

    URGENT IS WALKED IN ORDER (the owner, 2026-10-22, overruling the line-skip the same day: "urgent is combined into tasks and it never
    moves ... you go through it like all other tasks", "a meeting in 4 hours - once you hit Next on the item before it, it opens up,
    then you hit Next it goes to next, no jumping around"): an urgent row is shaded where it sits and reached like any other."""
    from . import funnel
    keys = ({k for k in exclude[5:].split(",") if k} if exclude and exclude.startswith("fyis:") else {exclude}) if exclude else set()
    # ...a row put away with Remind me has left the walk's line for For later: its place there is not where the walk stood, so the walk
    # goes on from its place's clock instead (Next after "later" found nothing below the For later row and ended on a new task above it)
    gone = lambda i: i.get("deferred")
    hit = [n for n, i in enumerate(items) if (i.get("key") in keys or keys.intersection(i.get("aliases") or [])) and not gone(i)]
    # ...and the walk's place is the rail's own ROW while it is still there (`at_key`, funnel.walk_place): the place's clock was read off
    # the card put on the table, built by key, whose arrival need not be the rail row's - Next then picked a different row than the
    # one the page had marked a moment before (PW-118)
    stood = [] if hit or place is None or not at_key else [
        n for n, i in enumerate(items) if (i.get("key") == at_key or at_key in (i.get("aliases") or [])) and not gone(i)]
    if hit or stood:
        # ...the place's own row, still walkable with nothing on the table, is where the walk stood: offered again (below)
        cut, at = max(hit) if hit else max(stood) - 1, {id(i): n for n, i in enumerate(items)}
        down = [i for i in ready if at.get(id(i), -1) > cut]
    elif place is None: return None
    # ...from the place itself: a row still there and walkable with nothing on the table is where the walk stood (the table was
    # cleared under it, or it changed since), so it is offered again - a row Next or a close took the walk past is not walkable
    # ...and by its PLACE, never its key: the row on the table can come back under another key with the same arrival - a message
    # handed to an agent is `agent:<task>` now, where it was `msg:<id>` - and the key's tiebreak put it above the place, so Next
    # found nothing below and the walk ended on a task waiting right there (tests/test_lifecycle.py)
    # ...nor its task number (the tie-break after the arrival): `msg:<id>` has none, `agent:<task>` has one. So the place is the
    # section and the arrival - the first four parts, which is also all a place saved before the task number joined the key holds
    # ...BUT A ROW IN THE SAME SECOND WITH A LOWER TASK NUMBER IS ABOVE IT: a goal and the steps made with it arrive together, and with the
    # step put down (Remind me, Mark done) its goal - drawn just above it - matched the place's clock and Next walked back UP to it (the
    # 2026-10-25 sweep: "Remind me on the last task lands on the goal above it"). Where both carry a number it decides; a key with none
    # (`msg:<id>`) is still the place's own row under another name
    else:
        p = tuple(place)
        # ...and two rows with no task number in the same second by their first message, the order's next tie-break (funnel.place_id):
        # two dashboards filed by one run, the lower put down, and Next walked back up to it (2026-10-25). A place saved before it is shorter
        def from_place(i):
            k = funnel.order_key(i)
            if k[:4] != p[:4]: return k[:4] > p[:4]
            if len(p) < 6: return True
            if not (k[4] or p[4]): return k[5] >= p[5]
            if len(p) < 9 or not (k[4] and p[4]): return True
            if not (k[6] or p[6]): return k[7] >= p[7]
            return len(p) < 10 or not (k[6] and p[6]) or k[8] >= p[8]       # ...and neither has a message: their first member
        down = [i for i in ready if from_place(i)]
    return down


def first_at_start(ready: list[dict]):
    """A walk's first row: what waits on the owner (funnel.leads), then anything ready - the reason a pending reply is not buried under
    an inbox of unread fyi. An urgent row is not lifted: it is walked in its place."""
    from . import funnel
    return next((i for i in ready if funnel.leads(i)), ready[0] if ready else None)


def _selection_facts(item: dict) -> dict:
    from . import funnel

    facts = {name: detach(item.get(name)) for name in (
        "key", "lane", "settling", "surfaced", "surfaced_at", "actionable", "unread", "deferred",
    )}
    facts["not_yet"] = funnel._not_yet(item)
    return facts


def _members(first: dict, ready: list[dict], size: int) -> list[dict]:
    from . import funnel
    return ([first] + [item for item in ready
                       if funnel.batchable(item) and item.get("key") != first.get("key")])[:size]


def _batch(first: dict, ready: list[dict], size: int) -> tuple[dict, tuple[str, ...]]:
    members = _members(first, ready, size)
    keys = tuple(item["key"] for item in members)
    card = {
        "key": "fyis:" + ",".join(keys),
        "kind": "fyis",
        "lane": "fyi",
        "title": f"{len(members)} fyi",
        "who": "",
        "when": members[0].get("when"),
        "since": members[0].get("since"),
        "channel": members[0].get("channel"),
        "why": "people told you things; nothing to do",
        "items": detach(members),
        "members": list(keys),
    }
    # The children were stamped together with the displayed pile.  Re-reading
    # their backing here could create a batch assembled from two database moments.
    # Their complete captured envelopes and revisions are sufficient backing for
    # the synthetic parent card.
    card["presentation_revision"] = item_revision(card, {
        "captured_child_presentations": [
            {"key": child.get("key"),
             "presentation_revision": child.get("presentation_revision")}
            for child in members
        ],
    })
    return card, keys


def capture_selection(store, *, only=None, include_surfaced=False,
                      exclude=None, now: datetime | None = None, pile=None) -> SelectionCapture:
    """Capture the current automatic selection without watcher or reconciliation writes."""
    from . import funnel
    from . import terminal

    captured_now = now or datetime.now()
    scope = _scope(only=only, include_surfaced=include_surfaced, exclude=exclude)
    lazy = pile is not None
    if pile is None:
        try:
            live_state = copy.deepcopy(terminal.live_sessions(tail=6))
        except Exception as error:
            raise SelectionUnavailable() from error
        for worker in live_state:
            waiting = (worker.get("waiting") if worker.get("waiting") is not None
                       else (worker.get("idle") or 0) >= terminal.IDLE_WAITING)
            if not waiting or not worker.get("sid"):
                continue
            try:
                rendered = [str(line).strip() for line in terminal.asking_lines(worker["sid"], 4)
                            if str(line).strip()]
            except Exception:
                rendered = []
            if rendered:
                worker["tail"] = rendered
        if getattr(store, 'processing_reads_active', lambda: False)():
            from .processing_unread import build
            from .processing_all import AllError
            try:
                pile = funnel.present(store, build(store, now=captured_now, live_state=live_state, only=only))
            except AllError as error:
                raise SelectionUnavailable(str(error)) from error
        else:
            pile = funnel.present(store, funnel.build(
                store, now=captured_now, reconcile=False, live_state=live_state
            ))
    else:
        # The HTTP read path already owns funnel.pile's invalidation-aware single-flight cache.
        # Capture selection from that exact pile instead of rebuilding canonical membership a
        # second time. A detached presentation keeps cache callers from mutating one another:
        # present() detaches its own copy and never writes to what it is handed.
        # ...and only what the selection RESTS ON is stamped here: the selected row and its batch. Stamping the whole
        # rail was the first of three whole-pile fingerprints every press paid (3,770 rows, 2026-10-20), and no reader
        # of this capture uses another row's stamp - the revision covers the selected stamps alone, and the pile
        # payload stamps every row it sends in its own final present().
        pile = detach(pile)
    items = pile.get("items") or []
    ready = _eligible(items, scope, captured_now)
    # ...and only what is BELOW the row on the table, or the walk's place: Next walks down the line, never back up (2026-10-22)
    wp = (funnel.walk_place(store) or (None, None)) if only is None and not include_surfaced else (None, None)
    down = below(items, ready, scope["exclude"], wp[1], at_key=wp[0])
    if down is not None: ready = down
    # At a walk's start: what waits on the owner (first_at_start). Walking on, simply the next row down - an urgent one in its place.
    first = (ready[0] if ready else None) if down is not None else first_at_start(ready)
    if lazy and first is not None:
        want = _members(first, ready, funnel.fyi_batch_size(store)) if funnel.batchable(first) else [first]
        for row, stamped in zip(want, funnel.present(store, {"items": want})["items"]):
            stamped = dict(stamped)                   # present() may hand back the very row it was given: clearing it first emptied both
            row.clear(); row.update(stamped)          # in place: `items` and `ready` hold the same row; nested cards come stamped too
    if first is not None and funnel.batchable(first):
        selected, member_keys = _batch(first, ready, funnel.fyi_batch_size(store))
    else:
        selected = detach(first) if first is not None else None
        member_keys = (selected["key"],) if selected is not None else ()

    pending = {
        "working": sum(1 for item in items if item.get("lane") == "working"),
        "settling": sum(1 for item in items if item.get("settling")),
        "scheduled": sum(1 for item in items if funnel._not_yet(item)),
    }
    stable = {
        "schema": _SCHEMA,
        "scope": scope,
        "items": [_selection_facts(item) for item in items],
        "expected_next_key": selected.get("key") if selected else None,
        "expected_next_members": list(member_keys),
        # Display churn elsewhere in the pile must not starve a model turn.  The
        # exact item(s) about to be surfaced are different: their full backing is
        # the context the response rests on and must still be current at commit.
        "selected_presentations": ([{
            "key": selected.get("key"),
            "presentation_revision": selected.get("presentation_revision"),
            "members": [{
                "key": child.get("key"),
                "presentation_revision": child.get("presentation_revision"),
            } for child in (selected.get("items") or []) if isinstance(child, dict)],
        }] if selected else []),
        "selection_pending": pending,
    }
    return SelectionCapture(
        revision=_digest(stable),
        scope=copy.deepcopy(scope),
        pile=pile,                   # present()'s own fresh copy: nothing else holds it
        selected=detach(selected),
        member_keys=member_keys,
        pending=copy.deepcopy(pending),
    )


def capture_from_rail(store, *, only=None, include_surfaced=False, exclude=None,
                      now: datetime | None = None) -> SelectionCapture:
    """The selection the page is looking at, taken from the rail's own cached build rather than a
    second one. /api/funnel/pile captures from funnel.pile for the unscoped walk, so this is the same
    pile the client's token came from; the cache serves it only while nothing has been written since
    (funnel.pile checks the store's dirty-row top), and a scoped walk (`only`) still builds its own.
    Quiet: the watcher does not speak inside a turn's admission (design B, 2026-09-17).

    The live workers are observed HERE, first, and the cache is compared against that observation:
    an observation that fails is still a refusal (SelectionUnavailable) - a cached pile is not a
    guess to fall back on - and a worker that moved since the build is a rebuilt pile."""
    from . import funnel, terminal
    if only is None:
        try: observed = copy.deepcopy(terminal.live_sessions(tail=6))
        except Exception as error: raise SelectionUnavailable() from error
        pile = funnel.pile(store, quiet=True, observed=observed)
        # ...and only a build that holds every write so far (the rule funnel.pile keeps for a shared rebuild): a write that landed
        # while this build ran - the Advisor filing its line, say - left the capture a step behind the store, and the commit
        # check, building again with it, refused the press as stale though the pick had not moved (PW-118, 2026-10-20).
        for _ in range(3):
            if funnel.built_as_of_now(store): break
            pile = funnel.pile(store, quiet=True, observed=observed)
    else: pile = None
    return capture_selection(store, only=only, include_surfaced=include_surfaced, exclude=exclude,
                             now=now, pile=pile)


def selection_fields(capture: SelectionCapture) -> dict:
    """The stable fields exposed by pile responses and echoed by Next requests."""
    return {
        "selection_revision": capture.revision,
        "expected_next_key": capture.selected.get("key") if capture.selected else None,
        "expected_next_members": list(capture.member_keys),
        "selection_pending": copy.deepcopy(capture.pending),
    }


def validate_selection(capture: SelectionCapture, *, selection_revision,
                       expected_next_key, expected_next_members) -> SelectionCapture:
    """Validate a client echo against an already fresh server capture."""
    members = list(expected_next_members or [])
    if (selection_revision != capture.revision
            or expected_next_key != (capture.selected.get("key") if capture.selected else None)
            or members != list(capture.member_keys)):
        raise SelectionStale(capture, expected_next_key)
    return capture


def same_pick(a: SelectionCapture, b: SelectionCapture) -> bool:
    """The same item(s) handed over - the one thing a press made on what the page showed is bound to (PW-050)."""
    return (a.selected or {}).get("key") == (b.selected or {}).get("key") and tuple(a.member_keys) == tuple(b.member_keys)


def _backing(capture: SelectionCapture):
    s = capture.selected or {}
    return s.get("presentation_revision"), [(c.get("key"), c.get("presentation_revision")) for c in s.get("items") or [] if isinstance(c, dict)]


def same_backing(a: SelectionCapture, b: SelectionCapture) -> bool:
    """The same pick, read from the same content: an answer made from one is true of the other."""
    return same_pick(a, b) and _backing(a) == _backing(b)


def recheck_selection(store, capture: SelectionCapture, *, now: datetime | None = None) -> SelectionCapture:
    """Reject drift after a model call while retaining the originally selected object."""
    fresh = capture_from_rail(store, now=now, **capture.scope)
    if (fresh.revision != capture.revision
            or fresh.member_keys != capture.member_keys
            or (fresh.selected or {}).get("key") != (capture.selected or {}).get("key")):
        raise SelectionStale(fresh, (capture.selected or {}).get("key"))
    return fresh
