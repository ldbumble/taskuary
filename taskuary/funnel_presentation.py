"""Deterministic display revisions for the legacy funnel payload.

This is a freshness seam, not another inventory or selection model.  Callers hand
it items the funnel already selected; it only fingerprints the complete local facts
those cards can render.  It never allocates processing identities or changes state.
"""
from __future__ import annotations

import contextlib
import copy
import hashlib
import json


_ITEM_SCHEMA = "taskuary.funnel.presentation.v1"
_PILE_SCHEMA = "taskuary.funnel.display.v1"
_SELF_FIELDS = {"presentation_revision"}
_TRANSIENT_PILE_FIELDS = {"rev", "display_revision", "events", "captured_at", "generated_at"}


def _canonical(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _digest(value) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def item_revision(item: dict, backing: dict) -> str:
    """Hash one detached card and its exact display backing."""
    if not isinstance(item, dict):
        raise TypeError("funnel presentation items must be dictionaries")
    if not isinstance(backing, dict):
        raise TypeError("funnel presentation backing must be a dictionary")
    clean = {key: copy.deepcopy(value) for key, value in item.items() if key not in _SELF_FIELDS}
    return _digest({"schema": _ITEM_SCHEMA, "item": clean, "backing": copy.deepcopy(backing)})


def display_revision(payload: dict) -> str:
    """Hash every repeatable display field while excluding transient event delivery.

    Key presence remains significant, so a request with ``current: null`` differs
    from a response for which no Current lookup was requested.
    """
    if not isinstance(payload, dict):
        raise TypeError("funnel presentation payload must be a dictionary")
    stable = {key: copy.deepcopy(value) for key, value in payload.items()
              if key not in _TRANSIENT_PILE_FIELDS}
    return _digest({"schema": _PILE_SCHEMA, "payload": stable})


def _ids(item: dict) -> dict[str, set]:
    ids = {"message": set(), "task": set(), "review": set(), "idea": set()}
    for value in [item, *(item.get("items") or [])]:
        if not isinstance(value, dict):
            continue
        for name, field in (("message", "mid"), ("task", "tid"),
                            ("review", "rid"), ("idea", "idea")):
            if value.get(field) is not None:
                ids[name].add(value[field])
    return ids


def _children(item: dict) -> list[dict]:
    """Nested FYI cards are presentation envelopes; other business lists are not."""
    values = item.get("items")
    if not isinstance(values, list):
        return []
    return [value for value in values
            if isinstance(value, dict) and all(field in value for field in ("key", "kind", "lane"))]


def _rows(cur, table: str, column: str, values) -> list[dict]:
    values = sorted(set(values), key=lambda value: (str(type(value)), str(value)))
    if not values or cur is None:
        return []
    out = []
    for offset in range(0, len(values), 400):
        part = values[offset:offset + 400]
        rows = cur.execute(
            f'SELECT * FROM {table} WHERE {column} IN ({",".join("?" for _ in part)})', part
        ).fetchall()
        out.extend(dict(row) for row in rows)
    return sorted(out, key=_canonical)


@contextlib.contextmanager
def _snapshot_cursor(store):
    read = getattr(store, "_processing_read", None)
    if callable(read):
        with read() as cur:
            yield cur
        return
    cx, lock = getattr(store, "cx", None), getattr(store, "lock", None)
    if cx is None or lock is None:
        yield None
        return
    with lock:
        cur = cx.cursor()
        try:
            yield cur
        finally:
            cur.close()


def _backing(cur, item: dict) -> dict:
    ids = _ids(item)

    # Reviews can introduce their message/task after the card was first created.
    reviews = _rows(cur, "review", "ReviewId", ids["review"])
    ids["message"].update(row.get("MessageId") for row in reviews if row.get("MessageId") is not None)
    ids["task"].update(row.get("TaskId") for row in reviews if row.get("TaskId") is not None)

    # A message can acquire a task without changing the legacy card key.  Once it
    # does, the whole exact task membership is what CombinedTaskText renders.
    messages = _rows(cur, "message", "MessageId", ids["message"])
    ids["task"].update(row.get("TaskId") for row in messages if row.get("TaskId") is not None)
    tasks = _rows(cur, "task", "TaskId", ids["task"])
    members = _rows(cur, "message", "TaskId", ids["task"])
    # Grouped cards render the task's explicit members, not an entire Teams/WhatsApp
    # room.  Conversation expansion is only the taskless review freshness seam used
    # by /api/reviews to derive Stale/Latest*.
    conversations = _rows(cur, "message", "ConversationId", [
        row.get("ConversationId") for row in messages if row.get("ConversationId")
    ] if not ids["task"] else [])
    all_messages = {row.get("MessageId"): row for row in [*messages, *members, *conversations]}
    messages = sorted(all_messages.values(), key=_canonical)
    message_ids = [row["MessageId"] for row in messages if row.get("MessageId") is not None]

    # Drafts are loaded from /api/reviews and may be task- or message-linked.
    by_task = _rows(cur, "review", "TaskId", ids["task"])
    by_message = _rows(cur, "review", "MessageId", message_ids)
    review_rows = {row.get("ReviewId"): row for row in [*reviews, *by_task, *by_message]}

    reply_card = item.get("kind") in ("review", "action") or bool(ids["review"])
    github_capabilities = []
    for row in _rows(cur, "connector", "Type", ["github"] if reply_card else []):
        try:
            config = json.loads(row.get("ConfigJson") or "{}")
        except (TypeError, ValueError, json.JSONDecodeError):
            config = {}
        if not isinstance(config, dict):
            config = {}
        github_capabilities.append({
            "connector_id": row.get("ConnectorId"),
            "active": bool(row.get("Active")),
            "reply_comments": bool(config.get("reply_comments")),
        })

    return {
        "messages": messages,
        "tasks": tasks,
        "reviews": sorted(review_rows.values(), key=_canonical),
        "attachments": _rows(cur, "attachment", "MessageId", message_ids),
        "comments": _rows(cur, "comment", "TaskId", ids["task"]),
        "runs": _rows(cur, "run", "TaskId", ids["task"]),
        "waitroom": _rows(cur, "waitroom", "TaskId", ids["task"]),
        "ideas": _rows(cur, "idea", "IdeaId", ids["idea"]),
        "reply_settings": _rows(cur, "setting", "Name", ["reply_channels"] if reply_card else []),
        "github_reply_capabilities": github_capabilities,
        "funnel_state": _rows(cur, "funnel_state", "Key", [
            value.get("key") for value in [item, *(item.get("items") or [])]
            if isinstance(value, dict) and value.get("key")
        ]),
    }


def present(store, payload: dict) -> dict:
    """Return a detached funnel payload with strong item and display revisions."""
    if not isinstance(payload, dict):
        raise TypeError("funnel presentation payload must be a dictionary")
    out = copy.deepcopy(payload)
    targets = [*(out.get("items") or [])]
    if "current" in out and out.get("current") is not None:
        targets.append(out["current"])
    if any(not isinstance(item, dict) for item in targets):
        raise TypeError("funnel presentation items must be dictionaries")

    def stamp(cur, item):
        for child in _children(item):
            stamp(cur, child)
        item["presentation_revision"] = item_revision(item, _backing(cur, item))

    with _snapshot_cursor(store) as cur:
        for item in targets:
            stamp(cur, item)
    out["display_revision"] = display_revision(out)
    return out
