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

from .funnel_presentation import item_revision


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

    again = (now - timedelta(minutes=30)).strftime("%Y-%m-%d %H:%M:%S")
    exclude = scope["exclude"]
    excluded_keys = ({key for key in exclude[5:].split(",") if key}
                     if exclude and exclude.startswith("fyis:") else {exclude})
    ready = [
        item for item in items
        if item.get('actionable', True)
        and not item.get("settling")
        and item.get("lane") != "working"
        and not funnel._not_yet(item)
        and item.get("key") not in excluded_keys
        and not excluded_keys.intersection(item.get('aliases', []))
        and (
            scope["include_surfaced"]
            or not item.get("surfaced")
            or (
                item.get("lane") in ("blocked", "approve")
                and funnel._ts(item.get("surfaced_at")) <= again
            )
        )
    ]
    if scope["only"] == "mail" and not any(item.get("processing_id") for item in items):
        ready = [item for item in ready
                 if funnel.came_in(item) or item.get("kind") in funnel.INTERRUPTS]
    return ready


def _selection_facts(item: dict) -> dict:
    from . import funnel

    facts = {name: copy.deepcopy(item.get(name)) for name in (
        "key", "lane", "settling", "surfaced", "surfaced_at", "actionable", "unread", "deferred",
    )}
    facts["not_yet"] = funnel._not_yet(item)
    return facts


def _batch(first: dict, ready: list[dict]) -> tuple[dict, tuple[str, ...]]:
    from . import funnel

    members = ([first] + [item for item in ready
                          if item.get("lane") == "fyi" and item.get("key") != first.get("key")])[:funnel.FYI_BATCH]
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
        "items": copy.deepcopy(members),
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
        # second time. A detached presentation keeps cache callers from mutating one another.
        pile = funnel.present(store, copy.deepcopy(pile))
    items = pile.get("items") or []
    ready = _eligible(items, scope, captured_now)
    first = next((item for item in ready if not item.get("surfaced")),
                 ready[0] if ready else None)
    if first is not None and first.get("lane") == "fyi":
        selected, member_keys = _batch(first, ready)
    else:
        selected = copy.deepcopy(first) if first is not None else None
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
        pile=copy.deepcopy(pile),
        selected=copy.deepcopy(selected),
        member_keys=member_keys,
        pending=copy.deepcopy(pending),
    )


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


def recheck_selection(store, capture: SelectionCapture, *, now: datetime | None = None) -> SelectionCapture:
    """Reject drift after a model call while retaining the originally selected object."""
    fresh = capture_selection(store, now=now, **capture.scope)
    if (fresh.revision != capture.revision
            or fresh.member_keys != capture.member_keys
            or (fresh.selected or {}).get("key") != (capture.selected or {}).get("key")):
        raise SelectionStale(fresh, (capture.selected or {}).get("key"))
    return fresh
