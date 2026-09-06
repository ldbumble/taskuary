"""Pure ordering and pagination for frozen processing inventory snapshots.

This module deliberately does not decide whether an item is readable, eligible,
deferred, excluded, or actionable.  It orders the raw canonical inventory using
persisted activity/priority fields and optional, revision-bound ranking facts.
"""

from __future__ import annotations

import base64
import copy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from typing import Any


SNAPSHOT_SCHEMA = "taskuary.processing.inventory.v1"
PAGE_SCHEMA = "taskuary.processing.inventory.page.v1"
CURSOR_VERSION = 1
MAX_PAGE_LIMIT = 500

from .processing_order import PRIORITY_RANK as _PRIORITY_RANK, attention_band
_SIGNAL_BAND = {
    "urgent_request": 1,
    "owner_input": 2,
    "owner_approval": 2,
    "actionable_task": 3,
    "finished_result": 3,
    "fyi": 4,
    "working": 5,
}
_FACT_KEYS = frozenset({"view_revision", "activity", "triage_priority", "attention"})
_QUERY_REVISION = "canonical-items-v1"


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False)


def _digest(value: Any) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _require_text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _timestamp(value: Any) -> tuple[tuple[int, ...], str, bool] | None:
    """Return a deterministic sortable coordinate and normalized display value.

    Offset-aware timestamps are normalized to UTC. Legacy naive timestamps retain
    a wall-clock coordinate only so a frozen ``as_of`` can be carried without
    consulting the machine timezone. They are never accepted as sortable activity.
    """
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip()
    try:
        parsed = datetime.fromisoformat(raw[:-1] + "+00:00" if raw.endswith("Z") else raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        normalized = parsed.isoformat(timespec="microseconds" if parsed.microsecond else "seconds")
        key = (parsed.year, parsed.month, parsed.day, parsed.hour, parsed.minute,
               parsed.second, parsed.microsecond)
        return key, normalized, False
    utc = parsed.astimezone(timezone.utc)
    normalized = utc.isoformat(timespec="microseconds" if utc.microsecond else "seconds")
    normalized = normalized[:-6] + "Z"
    key = (utc.year, utc.month, utc.day, utc.hour, utc.minute, utc.second, utc.microsecond)
    return key, normalized, True


def _unknown_activity(diagnostics: list[str]) -> dict[str, Any]:
    return {
        "state": "unknown", "at": None, "normalized_at": None,
        "timestamp_basis": None, "provenance": None,
        "diagnostics": [*diagnostics, "activity_unknown"],
    }


def _derived_activity(item: dict[str, Any]) -> tuple[dict[str, Any], tuple[int, ...] | None]:
    view = item.get("view") if isinstance(item.get("view"), dict) else {}
    diagnostics: list[str] = []
    candidates: list[tuple[tuple[int, ...], str, str, str]] = []
    owned_idea_ids = {
        str(member.get("LocalId")) for member in item.get("members", [])
        if isinstance(member, dict) and member.get("EntityKind") == "idea"
        and member.get("LocalId") not in (None, "")
    }
    owned_idea_ids.update(
        member_id.split(":", 1)[1] for member_id in item.get("member_ids", [])
        if isinstance(member_id, str) and member_id.startswith("idea:")
    )

    def add(rows: Any, kind: str, id_field: str, primary: str,
            fallback: str | None = None, predicate=lambda row: True) -> int:
        if not isinstance(rows, list):
            return 0
        entity_count = 0
        for index, row in enumerate(rows):
            if not isinstance(row, dict) or not predicate(row):
                continue
            entity_count += 1
            fields = (primary, fallback) if fallback else (primary,)
            for field in fields:
                raw = row.get(field)
                if raw in (None, ""):
                    continue
                parsed = _timestamp(raw)
                identity = row.get(id_field)
                identity = str(identity) if identity not in (None, "") else f"row-{index}"
                provenance = f"{kind}:{identity}.{field}"
                if parsed is None:
                    diagnostics.append(f"invalid_timestamp:{provenance}")
                    continue
                key, normalized, aware = parsed
                if not aware:
                    diagnostics.append(f"naive_timestamp_timezone_unknown:{provenance}")
                    continue
                candidates.append((key, provenance, str(raw), normalized))
                break
        return entity_count

    source_entities = 0
    source_entities += add(view.get("messages"), "message", "MessageId", "SentAt", "CreatedAt")
    source_entities += add(
        view.get("ideas"), "idea", "IdeaId", "LastSaid", "FirstSeen",
        predicate=lambda row: str(row.get("IdeaId")) in owned_idea_ids,
    )
    source_entities += add(
        view.get("reviews"), "review", "ReviewId", "CreatedAt",
        predicate=lambda row: str(row.get("Status") or "").lower() == "pending",
    )
    source_entities += add(
        view.get("runs"), "run", "RunId", "StartedAt",
        predicate=lambda row: str(row.get("Status") or "").lower() in {"running", "working"},
    )
    source_entities += add(
        view.get("runs"), "run", "RunId", "FinishedAt",
        predicate=lambda row: str(row.get("Status") or "").lower() not in {"running", "working"},
    )
    if not source_entities:
        add(view.get("tasks"), "task", "TaskId", "CreatedAt")

    if not candidates:
        return _unknown_activity(diagnostics), None
    candidates.sort(key=lambda candidate: candidate[1])
    key, provenance, raw, normalized = max(candidates, key=lambda candidate: candidate[0])
    return ({
        "state": "known", "at": raw,
        "normalized_at": normalized,
        "timestamp_basis": "absolute_utc",
        "provenance": provenance, "diagnostics": diagnostics,
    }, key)


def _derived_priority(item: dict[str, Any]) -> dict[str, Any]:
    view = item.get("view") if isinstance(item.get("view"), dict) else {}
    tasks = view.get("tasks") if isinstance(view.get("tasks"), list) else []
    task_by_id = {
        str(row.get("TaskId")): row for row in tasks
        if isinstance(row, dict) and row.get("TaskId") not in (None, "")
    }
    diagnostics: list[str] = []
    selected: dict[str, Any] | None = None
    provenance: str | None = None
    if len(task_by_id) == 1:
        task_id, selected = next(iter(task_by_id.items()))
        provenance = f"task:{task_id}.Priority"
    elif len(task_by_id) > 1:
        primary_ids = {
            str(member.get("LocalId")) for member in item.get("members", [])
            if isinstance(member, dict)
            and member.get("EntityKind") == "task"
            and member.get("Role") == "primary"
        }
        matches = primary_ids & task_by_id.keys()
        if len(matches) == 1:
            task_id = next(iter(matches))
            selected = task_by_id[task_id]
            provenance = f"primary_task:{task_id}.Priority"
        else:
            diagnostics.append("priority_ambiguous_multiple_tasks")
    if selected is None:
        diagnostics.append("priority_unknown")
        return {"state": "unknown", "value": None, "rank": None,
                "provenance": provenance, "raw": None, "diagnostics": diagnostics}
    raw = selected.get("Priority")
    value = str(raw).strip().lower() if raw is not None else ""
    if value not in _PRIORITY_RANK:
        diagnostics.extend(([f"unrecognized_priority:{raw}"] if raw not in (None, "") else []) +
                           ["priority_unknown"])
        return {"state": "unknown", "value": None, "rank": None,
                "provenance": provenance, "raw": raw, "diagnostics": diagnostics}
    return {"state": "known", "value": value, "rank": _PRIORITY_RANK[value],
            "provenance": provenance, "raw": raw, "diagnostics": diagnostics}


def _normalize_activity(value: Any) -> tuple[dict[str, Any], tuple[int, ...] | None]:
    if not isinstance(value, dict) or set(value) - {"at", "provenance"}:
        raise ValueError("activity fact must contain only at and provenance")
    provenance = _require_text(value.get("provenance"), "activity.provenance")
    raw = value.get("at")
    if raw is None:
        return ({"state": "unknown", "at": None, "normalized_at": None,
                 "timestamp_basis": None, "provenance": provenance,
                 "diagnostics": ["explicit_activity_unknown"]}, None)
    parsed = _timestamp(raw)
    if parsed is None:
        raise ValueError("activity.at must be an ISO timestamp or null")
    key, normalized, aware = parsed
    if not aware:
        raise ValueError("activity.at must include an explicit UTC offset")
    return ({"state": "known", "at": raw, "normalized_at": normalized,
             "timestamp_basis": "absolute_utc",
             "provenance": provenance, "diagnostics": []}, key)


def _normalize_priority(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) - {"value", "provenance"}:
        raise ValueError("triage_priority fact must contain only value and provenance")
    provenance = _require_text(value.get("provenance"), "triage_priority.provenance")
    raw = value.get("value")
    if raw is None:
        return {"state": "unknown", "value": None, "rank": None,
                "provenance": provenance, "raw": None,
                "diagnostics": ["explicit_priority_unknown"]}
    if not isinstance(raw, str) or raw.lower() not in _PRIORITY_RANK:
        raise ValueError("triage_priority.value must be urgent, high, normal, low, or null")
    normalized = raw.lower()
    return {"state": "known", "value": normalized, "rank": _PRIORITY_RANK[normalized],
            "provenance": provenance, "raw": raw, "diagnostics": []}


def _normalize_attention(value: Any, as_of: tuple[int, ...], as_of_aware: bool) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {"signals"} or not isinstance(value["signals"], list):
        raise ValueError("attention fact must contain exactly a signals list")
    signals: list[dict[str, Any]] = []
    diagnostics: list[str] = []
    qualifying: list[int] = []
    for index, raw in enumerate(value["signals"]):
        if not isinstance(raw, dict):
            raise ValueError(f"attention signal {index} must be an object")
        kind = raw.get("kind")
        if not isinstance(kind, str):
            raise ValueError(f"attention signal {index} kind must be a string")
        provenance = _require_text(raw.get("provenance"), f"attention.signals[{index}].provenance")
        allowed = {"kind", "provenance", "starts_at", "ends_at"} if kind == "calendar" else {"kind", "provenance"}
        if set(raw) - allowed:
            raise ValueError(f"attention signal {index} has unknown fields")
        normalized = {"kind": kind, "provenance": provenance, "band": None}
        if kind == "calendar":
            if "starts_at" not in raw:
                raise ValueError("calendar signal requires starts_at")
            start = _timestamp(raw.get("starts_at"))
            end = _timestamp(raw.get("ends_at")) if raw.get("ends_at") is not None else None
            if start is None or (raw.get("ends_at") is not None and end is None):
                raise ValueError("calendar timestamps must be ISO timestamps")
            start_key, start_normalized, start_aware = start
            end_key, end_normalized, end_aware = end if end else (None, None, True)
            if not as_of_aware or not start_aware or not end_aware:
                raise ValueError("calendar ranking requires offset-aware as_of and timestamps")
            if end_key is not None and end_key <= start_key:
                raise ValueError("calendar ends_at must be later than starts_at")
            normalized.update({"starts_at": raw["starts_at"], "normalized_starts_at": start_normalized,
                               "ends_at": raw.get("ends_at"), "normalized_ends_at": end_normalized})
            current = start_key <= as_of and end_key is not None and as_of < end_key
            soon_limit = _coordinate_add_minutes(as_of, 15)
            soon = as_of <= start_key <= soon_limit
            if current or soon:
                normalized["band"] = 1
                qualifying.append(1)
            else:
                diagnostics.append(f"calendar_outside_attention_window:{provenance}")
        elif kind in _SIGNAL_BAND:
            normalized["band"] = _SIGNAL_BAND[kind]
            qualifying.append(_SIGNAL_BAND[kind])
        else:
            raise ValueError(f"unknown attention signal kind: {kind}")
        signals.append(normalized)
    signals.sort(key=_json)
    diagnostics.sort()
    if not qualifying:
        return {"state": "unknown", "band": None, "signals": signals,
                "diagnostics": [*diagnostics, "attention_unknown"]}
    selected_band = attention_band(urgent=1 in qualifying, owner_wait=2 in qualifying,
                                   working=5 in qualifying, actionable=3 in qualifying)
    if selected_band == 5 and any(band in qualifying for band in (3, 4)):
        diagnostics.append("working_suppresses_non_owner_attention")
    return {"state": "known", "band": selected_band, "signals": signals,
            "diagnostics": diagnostics}


def _coordinate_add_minutes(value: tuple[int, ...], minutes: int) -> tuple[int, ...]:
    dt = datetime(*value[:6], microsecond=value[6]) + timedelta(minutes=minutes)
    return (dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second, dt.microsecond)


def _encode_cursor(payload: dict[str, Any]) -> str:
    return base64.urlsafe_b64encode(_json(payload).encode("utf-8")).decode("ascii").rstrip("=")


def _decode_cursor(cursor: Any) -> dict[str, Any]:
    if not isinstance(cursor, str) or not cursor:
        raise ValueError("cursor must be a non-empty string")
    try:
        raw = base64.b64decode(cursor + "=" * (-len(cursor) % 4), altchars=b"-_", validate=True)
        payload = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("malformed cursor") from exc
    if not isinstance(payload, dict):
        raise ValueError("malformed cursor")
    return payload


def _validate_snapshot(snapshot: Any) -> tuple[dict[str, Any], tuple[int, ...], bool, list[dict[str, Any]]]:
    if not isinstance(snapshot, dict):
        raise ValueError("snapshot must be an object")
    frozen = copy.deepcopy(snapshot)
    if frozen.get("schema_version") != SNAPSHOT_SCHEMA:
        raise ValueError(f"snapshot schema_version must be {SNAPSHOT_SCHEMA}")
    _require_text(frozen.get("snapshot_revision"), "snapshot_revision")
    parsed_as_of = _timestamp(frozen.get("as_of"))
    if parsed_as_of is None:
        raise ValueError("as_of must be an ISO timestamp")
    as_of, _, as_of_aware = parsed_as_of
    items = frozen.get("items")
    if not isinstance(items, list):
        raise ValueError("snapshot.items must be a list")
    seen: set[str] = set()
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise ValueError(f"snapshot item {index} must be an object")
        item_id = _require_text(item.get("item_id"), f"snapshot.items[{index}].item_id")
        if item_id in seen:
            raise ValueError(f"duplicate item_id: {item_id}")
        seen.add(item_id)
    coverage = frozen.get("coverage")
    if not isinstance(coverage, dict):
        raise ValueError("snapshot.coverage must be an object")
    canonical_count = coverage.get("canonical_item_count")
    if isinstance(canonical_count, bool) or not isinstance(canonical_count, int):
        raise ValueError("coverage canonical_item_count must be an integer")
    if canonical_count != len(items):
        raise ValueError("coverage canonical_item_count does not match snapshot items")
    member_count = coverage.get("member_count")
    if isinstance(member_count, bool) or not isinstance(member_count, int) or member_count < 0:
        raise ValueError("coverage member_count must be a non-negative integer")
    actual_member_count = 0
    for index, item in enumerate(items):
        members = item.get("members", [])
        if not isinstance(members, list):
            raise ValueError(f"snapshot.items[{index}].members must be a list")
        actual_member_count += len(members)
    if member_count != actual_member_count:
        raise ValueError("coverage member_count does not match snapshot item members")
    return frozen, as_of, as_of_aware, items


def processing_inventory_page(
    snapshot: dict[str, Any], *, order: str = "all", limit: int = 100,
    cursor: str | None = None, facts: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Return one deterministically ordered page from a frozen raw inventory."""
    if order not in {"all", "priority"}:
        raise ValueError("order must be all or priority")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_PAGE_LIMIT:
        raise ValueError(f"limit must be an integer from 1 through {MAX_PAGE_LIMIT}")
    frozen, as_of, as_of_aware, items = _validate_snapshot(snapshot)
    supplied = {} if facts is None else copy.deepcopy(facts)
    if not isinstance(supplied, dict):
        raise ValueError("facts must be an object keyed by item_id")
    if any(not isinstance(item_id, str) or not item_id for item_id in supplied):
        raise ValueError("facts keys must be non-empty item_id strings")
    by_id = {item["item_id"]: item for item in items}
    unknown_ids = set(supplied) - set(by_id)
    if unknown_ids:
        raise ValueError(f"facts contain unknown item_id: {sorted(unknown_ids)[0]}")

    ranked: list[tuple[dict[str, Any], tuple[int, ...] | None]] = []
    normalized_supplied: dict[str, Any] = {}
    for item in items:
        item_id = item["item_id"]
        activity, activity_key = _derived_activity(item)
        priority = _derived_priority(item)
        attention = {"state": "unknown", "band": None, "signals": [],
                     "diagnostics": ["attention_requires_revision_bound_fact"]}
        if item_id in supplied:
            fact = supplied[item_id]
            if not isinstance(fact, dict) or set(fact) - _FACT_KEYS:
                raise ValueError(f"facts[{item_id}] has unknown fields or is not an object")
            revision = _require_text(fact.get("view_revision"), f"facts[{item_id}].view_revision")
            if revision != item.get("view_revision"):
                raise ValueError(f"facts[{item_id}] view_revision is stale")
            if "activity" in fact:
                activity, activity_key = _normalize_activity(fact["activity"])
            if "triage_priority" in fact:
                priority = _normalize_priority(fact["triage_priority"])
            if "attention" in fact:
                attention = _normalize_attention(fact["attention"], as_of, as_of_aware)
            normalized_supplied[item_id] = {
                "view_revision": revision,
                **({"activity": activity} if "activity" in fact else {}),
                **({"triage_priority": priority} if "triage_priority" in fact else {}),
                **({"attention": attention} if "attention" in fact else {}),
            }
        output_item = copy.deepcopy(item)
        output_item["inventory_facts"] = {
            "activity": activity,
            "triage_priority": priority,
            "attention": attention,
            "read_state": {"state": "unknown"},
            "defer_state": {"state": "unknown"},
            "exclusion_state": {"state": "unknown"},
            "actionability": {"state": "unknown"},
        }
        ranked.append((output_item, activity_key))

    facts_revision = _digest(normalized_supplied)

    def all_key(entry: tuple[dict[str, Any], tuple[int, ...] | None]) -> tuple[Any, ...]:
        item, activity = entry
        if activity is None:
            return (1, (), item["item_id"])
        return (0, tuple(-part for part in activity), item["item_id"])

    def priority_key(entry: tuple[dict[str, Any], tuple[int, ...] | None]) -> tuple[Any, ...]:
        item, activity = entry
        info = item["inventory_facts"]
        band = info["attention"]["band"]
        priority_rank = info["triage_priority"]["rank"]
        return (
            1 if band is None else 0, band if band is not None else 99,
            priority_rank if priority_rank is not None else 99,
            1 if activity is None else 0, activity or (), item["item_id"],
        )

    ranked.sort(key=all_key if order == "all" else priority_key)
    position = 0
    if cursor is not None:
        payload = _decode_cursor(cursor)
        expected_keys = {"version", "snapshot_revision", "order", "facts_revision",
                         "query_revision", "position", "anchor"}
        if (set(payload) != expected_keys or isinstance(payload.get("version"), bool)
                or not isinstance(payload.get("version"), int)
                or payload.get("version") != CURSOR_VERSION):
            raise ValueError("malformed cursor payload")
        if payload.get("snapshot_revision") != frozen["snapshot_revision"]:
            raise ValueError("cursor snapshot_revision mismatch")
        if payload.get("order") != order:
            raise ValueError("cursor order mismatch")
        if payload.get("facts_revision") != facts_revision:
            raise ValueError("cursor facts mismatch")
        if payload.get("query_revision") != _QUERY_REVISION:
            raise ValueError("cursor query mismatch")
        position = payload.get("position")
        if isinstance(position, bool) or not isinstance(position, int) or not 0 < position < len(ranked):
            raise ValueError("cursor position out of range")
        if payload.get("anchor") != ranked[position - 1][0]["item_id"]:
            raise ValueError("cursor anchor mismatch")

    end = min(position + limit, len(ranked))
    page_items = [copy.deepcopy(entry[0]) for entry in ranked[position:end]]
    next_cursor = None
    if end < len(ranked):
        next_cursor = _encode_cursor({
            "version": CURSOR_VERSION,
            "snapshot_revision": frozen["snapshot_revision"],
            "order": order,
            "facts_revision": facts_revision,
            "query_revision": _QUERY_REVISION,
            "position": end,
            "anchor": ranked[end - 1][0]["item_id"],
        })
    coverage = copy.deepcopy(frozen["coverage"])
    result = {
        "schema_version": PAGE_SCHEMA,
        "as_of": frozen["as_of"],
        "snapshot_revision": frozen["snapshot_revision"],
        "order": order,
        "facts_revision": facts_revision,
        "items": page_items,
        "next_cursor": next_cursor,
        "counts": {
            "canonical_item_count": coverage["canonical_item_count"],
            "member_count": coverage["member_count"],
            "returned_count": len(page_items),
            "remaining_count": len(ranked) - end,
        },
        "coverage": coverage,
        "worker_attention_available": bool(frozen.get("worker_attention_available", False)),
        "worker_input_revision": copy.deepcopy(frozen.get("worker_input_revision")),
    }
    return result
