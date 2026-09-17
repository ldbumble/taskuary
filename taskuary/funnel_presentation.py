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
import threading
import weakref


_ITEM_SCHEMA = "taskuary.funnel.presentation.v1"
_PILE_SCHEMA = "taskuary.funnel.display.v1"
_SELF_FIELDS = {"presentation_revision"}
_TRANSIENT_PILE_FIELDS = {"rev", "display_revision", "events", "captured_at", "generated_at"}


def _canonical(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _digest(value) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def item_revision(item: dict, backing: dict) -> str:
    """Hash one detached card and its exact display backing.

    The copies this used to take bought nothing - ``json.dumps`` does not mutate what it
    serializes - and they were most of the cost of the walk: 480 000 ``deepcopy`` calls and a third
    of the 3.5 seconds every Next press took on the owner's own store (measured 2026-09-17, 352
    cards). The hash is byte-for-byte the one the copies produced.
    """
    if not isinstance(item, dict):
        raise TypeError("funnel presentation items must be dictionaries")
    if not isinstance(backing, dict):
        raise TypeError("funnel presentation backing must be a dictionary")
    clean = {key: value for key, value in item.items() if key not in _SELF_FIELDS}
    return _digest({"schema": _ITEM_SCHEMA, "item": clean, "backing": backing})


def display_revision(payload: dict) -> str:
    """Hash every repeatable display field while excluding transient event delivery.

    Key presence remains significant, so a request with ``current: null`` differs
    from a response for which no Current lookup was requested.
    """
    if not isinstance(payload, dict):
        raise TypeError("funnel presentation payload must be a dictionary")
    stable = {key: value for key, value in payload.items()
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


def _row_order(row: dict):
    """A deterministic order for rows of ONE table, without encoding each of them as JSON.

    Every row here comes from a single ``SELECT *``, so they share their column order and their
    values alone order them. The JSON key this replaces was called 15 700 times per press.
    """
    return str(tuple(row.values()))


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
    return sorted(out, key=_row_order)


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


def _backing_one(cur, item: dict) -> dict:
    """The per-card road: ~9 queries for one card. Kept as the SPECIFICATION of ``_backings``,
    which must return exactly this for every card; the test holds them equal."""
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
    messages = sorted(all_messages.values(), key=_row_order)
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
        "reviews": sorted(review_rows.values(), key=_row_order),
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




def _backings(cur, items: list[dict]) -> dict[int, dict]:
    """The display backing of every card at once: one query per table for the union of their
    ids, sliced back per card - instead of the ~9 queries ``_backing_one`` makes per card. A stamp
    of 356 cards was ~3,200 queries and 0.34 s on the owner's store, and a press of Next stamps
    the pile several times (measured 2026-09-17). Keyed by ``id(item)``: a card dict has no other
    stable identity here.

    Every backing is byte-for-byte what ``_backing_one`` returns for the same card - the stages
    run in the same order with the same dependencies (reviews name messages and tasks, messages
    name tasks, only a taskless card expands its conversations), and every list is sorted by the
    same ``_row_order`` that ``_rows`` sorts by. ``_backing_one`` stays as the specification and
    the test holds the two equal.
    """
    state = {id(item): {"item": item, "ids": _ids(item)} for item in items}

    def union(name):
        return {value for st in state.values() for value in st["ids"][name]}

    def index(rows, column):
        out: dict = {}
        for row in rows:
            out.setdefault(row.get(column), []).append(row)
        return out

    def pick(idx, keys):
        return sorted((row for key in set(keys) for row in idx.get(key, ())), key=_row_order)

    # Reviews can introduce their message/task after the card was first created.
    review_by_id = index(_rows(cur, "review", "ReviewId", union("review")), "ReviewId")
    for st in state.values():
        st["reviews"] = pick(review_by_id, st["ids"]["review"])
        st["ids"]["message"].update(row.get("MessageId") for row in st["reviews"] if row.get("MessageId") is not None)
        st["ids"]["task"].update(row.get("TaskId") for row in st["reviews"] if row.get("TaskId") is not None)
    # A message can acquire a task without changing the legacy card key.
    message_by_id = index(_rows(cur, "message", "MessageId", union("message")), "MessageId")
    for st in state.values():
        st["messages"] = pick(message_by_id, st["ids"]["message"])
        st["ids"]["task"].update(row.get("TaskId") for row in st["messages"] if row.get("TaskId") is not None)
    task_by_id = index(_rows(cur, "task", "TaskId", union("task")), "TaskId")
    member_by_task = index(_rows(cur, "message", "TaskId", union("task")), "TaskId")
    # Conversation expansion is only the taskless review freshness seam.
    conversation_ids = {row.get("ConversationId") for st in state.values() if not st["ids"]["task"]
                        for row in st["messages"] if row.get("ConversationId")}
    conversation_by_id = index(_rows(cur, "message", "ConversationId", conversation_ids), "ConversationId")
    for st in state.values():
        ids = st["ids"]
        st["tasks"] = pick(task_by_id, ids["task"])
        members = pick(member_by_task, ids["task"])
        conversations = [] if ids["task"] else pick(
            conversation_by_id, [row.get("ConversationId") for row in st["messages"] if row.get("ConversationId")])
        all_messages = {row.get("MessageId"): row for row in [*st["messages"], *members, *conversations]}
        st["messages"] = sorted(all_messages.values(), key=_row_order)
        st["message_ids"] = [row["MessageId"] for row in st["messages"] if row.get("MessageId") is not None]
    # Drafts may be task- or message-linked.
    all_message_ids = {mid for st in state.values() for mid in st["message_ids"]}
    review_by_task = index(_rows(cur, "review", "TaskId", union("task")), "TaskId")
    review_by_message = index(_rows(cur, "review", "MessageId", all_message_ids), "MessageId")
    attachment_by_message = index(_rows(cur, "attachment", "MessageId", all_message_ids), "MessageId")
    comment_by_task = index(_rows(cur, "comment", "TaskId", union("task")), "TaskId")
    run_by_task = index(_rows(cur, "run", "TaskId", union("task")), "TaskId")
    waitroom_by_task = index(_rows(cur, "waitroom", "TaskId", union("task")), "TaskId")
    idea_by_id = index(_rows(cur, "idea", "IdeaId", union("idea")), "IdeaId")
    keys_of = {sid: [value.get("key") for value in [st["item"], *(st["item"].get("items") or [])]
                     if isinstance(value, dict) and value.get("key")] for sid, st in state.items()}
    funnel_by_key = index(_rows(cur, "funnel_state", "Key", {k for keys in keys_of.values() for k in keys}), "Key")
    reply_cards = {sid for sid, st in state.items()
                   if st["item"].get("kind") in ("review", "action") or bool(st["ids"]["review"])}
    github_capabilities = []
    for row in _rows(cur, "connector", "Type", ["github"] if reply_cards else []):
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
    reply_settings = _rows(cur, "setting", "Name", ["reply_channels"] if reply_cards else [])
    out = {}
    for sid, st in state.items():
        ids, reply_card = st["ids"], sid in reply_cards
        review_rows = {row.get("ReviewId"): row for row in [
            *st["reviews"], *pick(review_by_task, ids["task"]), *pick(review_by_message, st["message_ids"])]}
        out[sid] = {
            "messages": st["messages"],
            "tasks": st["tasks"],
            "reviews": sorted(review_rows.values(), key=_row_order),
            "attachments": pick(attachment_by_message, st["message_ids"]),
            "comments": pick(comment_by_task, ids["task"]),
            "runs": pick(run_by_task, ids["task"]),
            "waitroom": pick(waitroom_by_task, ids["task"]),
            "ideas": pick(idea_by_id, ids["idea"]),
            "reply_settings": list(reply_settings) if reply_card else [],
            "github_reply_capabilities": list(github_capabilities) if reply_card else [],
            "funnel_state": pick(funnel_by_key, keys_of[sid]),
        }
    return out


def _backing(cur, item: dict) -> dict:
    """One card's backing, through the batched road."""
    return _backings(cur, [item])[id(item)]


# ---- the stamps made since the last write anywhere (design D, 2026-09-17) -------------------------
# A card's stamp is a pure function of the card and its backing rows, and the backing rows can only
# have changed if SOMETHING was written: every table the backing reads carries a dirty trigger
# (processing_rail.DIRTY_ROWS - message, task, review, attachment, comment, run, waitroom, idea,
# connector, funnel_state; the setting reply_channels is in PROCESSING_DIRTY_SETTINGS). So while the
# store's dirty-row top stands still, a card whose own fields are unchanged has the same stamp, and
# its backing is neither fetched nor hashed again. That fetch-and-hash of every card's full backing,
# message bodies included, was ~300 ms of every rail read - and a press reads the rail several times.
_STAMPS = weakref.WeakKeyDictionary()      # store -> {'top': dirty-row top, 'by': {card fingerprint: presentation_revision}}
_STAMPS_LOCK = threading.Lock()


def _top(cur):
    """The store's dirty-row top - "has anything at all been written?" - or None when it cannot be asked."""
    try:
        return cur.execute("SELECT COALESCE(MAX(Id),0) FROM processing_dirty_row").fetchone()[0]
    except Exception:
        return None


def _stamps(store, top):
    """The book of stamps for this store at this top. A write - any table, any process - opens an empty
    one: every card is fetched and hashed once more, then reused until the next write."""
    if store is None or top is None:
        return None
    with _STAMPS_LOCK:
        book = _STAMPS.get(store)
        if book is None or book["top"] != top:
            book = {"top": top, "by": {}}
            try:
                _STAMPS[store] = book
            except TypeError:
                return None                    # a store that cannot be weakly referenced keeps no book
        return book


def _fingerprint(item: dict) -> str:
    return _digest({key: value for key, value in item.items() if key not in _SELF_FIELDS})


def forget_stamps():
    """Tests: start every store with an empty book."""
    with _STAMPS_LOCK:
        _STAMPS.clear()


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
    # Children are stamped before their parent, whose hash covers their stamps - so the backings
    # are fetched for every card first (they never depend on a stamp) and applied in that order.
    every: list[dict] = []

    def collect(item):
        for child in _children(item):
            collect(child)
        every.append(item)

    def stamp(item, backings, known):
        for child in _children(item):
            stamp(child, backings, known)
        item["presentation_revision"] = known[id(item)] if id(item) in known else item_revision(item, backings[id(item)])

    with _snapshot_cursor(store) as cur:
        for item in targets:
            collect(item)
        book = _stamps(store, _top(cur) if cur is not None else None)
        # a batch card's stamp covers its children's; it is one card per payload at most and is hashed fresh
        leaves = [item for item in every if not _children(item)] if book is not None else []
        prints = {id(item): _fingerprint(item) for item in leaves}
        known = {sid: book["by"][fp] for sid, fp in prints.items() if fp in book["by"]}
        backings = _backings(cur, [item for item in every if id(item) not in known])
        for item in targets:
            stamp(item, backings, known)
        for item in leaves:
            book["by"][prints[id(item)]] = item["presentation_revision"]
    out["display_revision"] = display_revision(out)
    return out
