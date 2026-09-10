from __future__ import annotations

import base64
import copy
import json

import pytest

from taskuary.processing_inventory import (
    PAGE_SCHEMA,
    processing_inventory_page,
)


AS_OF = "2026-09-06T16:00:00Z"


def _item(
    item_id: str,
    *,
    at: str | None = None,
    priority: str | None = "normal",
    view_revision: str | None = None,
    members: list[dict] | None = None,
    view: dict | None = None,
) -> dict:
    item_view = copy.deepcopy(view) if view is not None else {}
    if at is not None:
        item_view.setdefault("messages", []).append({"MessageId": item_id, "SentAt": at})
    if priority is not None:
        item_view.setdefault("tasks", []).append(
            {"TaskId": f"task-{item_id}", "Priority": priority, "CreatedAt": at}
        )
    return {
        "item_id": item_id,
        "context_revision": f"context-{item_id}",
        "view_revision": view_revision or f"view-{item_id}",
        "members": copy.deepcopy(members or []),
        "view": item_view,
        "legacy_evidence": [{"raw": {"kept": item_id}}],
    }


def _snapshot(items: list[dict], *, revision: str = "snapshot-1", as_of: str = AS_OF) -> dict:
    return {
        "schema_version": "taskuary.processing.inventory.v1",
        "as_of": as_of,
        "snapshot_revision": revision,
        "items": copy.deepcopy(items),
        "coverage": {
            "canonical_item_count": len(items),
            "member_count": sum(len(item.get("members", [])) for item in items),
            "uncatalogued": {"message": 0, "task": 0, "review": 0, "idea": 0},
            "completed_baselines": ["legacy-v1"],
            "unsupported": ["calendar", "comments"],
        },
        "worker_attention_available": False,
        "worker_input_revision": "workers-0",
    }


def _fact(item: dict, *signals: dict, activity: str | None = None,
          priority: str | None = None) -> dict:
    fact: dict = {"view_revision": item["view_revision"]}
    if signals:
        fact["attention"] = {"signals": list(signals)}
    if activity is not None:
        fact["activity"] = {"at": activity, "provenance": "test:activity"}
    if priority is not None:
        fact["triage_priority"] = {"value": priority, "provenance": "test:priority"}
    return fact


def _signal(kind: str, **extra) -> dict:
    return {"kind": kind, "provenance": f"test:{kind}", **extra}


def _ids(page: dict) -> list[str]:
    return [item["item_id"] for item in page["items"]]


def _rewrite_cursor(cursor: str, **changes) -> str:
    raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
    payload = json.loads(raw)
    payload.update(changes)
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(encoded).decode().rstrip("=")


def test_all_orders_newest_first_then_stable_id_and_missing_last():
    items = [
        _item("missing", at=None),
        _item("same-b", at="2026-09-06T12:00:00-04:00"),
        _item("old", at="2026-09-06T14:00:00Z"),
        _item("same-a", at="2026-09-06T16:00:00Z"),
    ]

    page = processing_inventory_page(_snapshot(items))

    assert _ids(page) == ["same-a", "same-b", "old", "missing"]
    assert page["items"][0]["inventory_facts"]["activity"] == {
        "state": "known",
        "at": "2026-09-06T16:00:00Z",
        "normalized_at": "2026-09-06T16:00:00Z",
        "timestamp_basis": "absolute_utc",
        "provenance": "message:same-a.SentAt",
        "diagnostics": [],
    }


def test_naive_persisted_activity_is_unknown_instead_of_assuming_machine_timezone():
    item = _item("legacy", at="2026-09-06 12:00:00")

    activity = processing_inventory_page(_snapshot([item]))["items"][0]["inventory_facts"]["activity"]

    assert activity["state"] == "unknown"
    assert activity["timestamp_basis"] is None
    assert "naive_timestamp_timezone_unknown:message:legacy.SentAt" in activity["diagnostics"]
    assert all("task:" not in diagnostic for diagnostic in activity["diagnostics"])


def test_default_activity_uses_only_defensible_source_events_and_not_updated_at():
    view = {
        "messages": [{"SentAt": "2026-01-01T10:00:00Z"}],
        "ideas": [{"FirstSeen": "2026-01-01T09:00:00Z", "LastSaid": "2026-01-02T10:00:00Z"}],
        "reviews": [
            {"Status": "done", "CreatedAt": "2026-01-05T10:00:00Z"},
            {"Status": "pending", "CreatedAt": "2026-01-03T10:00:00Z"},
        ],
        "runs": [
            {"Status": "running", "StartedAt": "2026-01-04T10:00:00Z", "UpdatedAt": "2026-02-01T00:00:00Z"},
            {"Status": "done", "FinishedAt": "2026-01-02T12:00:00Z", "UpdatedAt": "2026-03-01T00:00:00Z"},
        ],
        "tasks": [{"TaskId": "t", "Priority": "high", "CreatedAt": "2025-01-01T00:00:00Z",
                   "UpdatedAt": "2026-04-01T00:00:00Z", "ClosedAt": "2026-05-01T00:00:00Z"}],
    }

    activity = processing_inventory_page(_snapshot([_item("item", view=view)]))["items"][0]["inventory_facts"]["activity"]

    assert activity["at"] == "2026-01-04T10:00:00Z"
    assert activity["provenance"] == "run:row-0.StartedAt"


def test_newer_catchup_task_creation_does_not_replace_source_message_activity():
    item = _item("message", view={
        "messages": [{"MessageId": 41, "SentAt": "2026-01-01T00:00:00Z"}],
        "tasks": [{"TaskId": 99, "Priority": "urgent", "CreatedAt": "2026-08-01T00:00:00Z"}],
    })

    activity = processing_inventory_page(_snapshot([item]))["items"][0]["inventory_facts"]["activity"]

    assert activity["at"] == "2026-01-01T00:00:00Z"
    assert activity["provenance"] == "message:41.SentAt"


def test_related_idea_activity_does_not_replace_owned_member_activity():
    item = _item(
        "wrapper",
        members=[{"EntityKind": "idea", "LocalId": "11", "Role": "primary"}],
        view={"ideas": [
            {"IdeaId": 11, "LastSaid": "2026-01-01T00:00:00Z"},
            {"IdeaId": 99, "LastSaid": "2026-08-01T00:00:00Z"},
        ]},
    )

    activity = processing_inventory_page(_snapshot([item]))["items"][0]["inventory_facts"]["activity"]

    assert activity["at"] == "2026-01-01T00:00:00Z"
    assert activity["provenance"] == "idea:11.LastSaid"


def test_priority_order_uses_five_attention_levels_then_oldest_and_id():
    items = [
        _item("working", at="2026-01-01T00:00:00Z", priority="urgent"),
        _item("fyi", at="2026-01-01T00:00:00Z", priority="urgent"),
        _item("action-new", at="2026-04-01T00:00:00Z", priority="high"),
        _item("action-old-z", at="2026-02-01T00:00:00Z", priority="high"),
        _item("action-old-a", at="2026-02-01T00:00:00Z", priority="high"),
        _item("action-urgent", at="2026-05-01T00:00:00Z", priority="urgent"),
        _item("owner", at="2026-01-01T00:00:00Z", priority="low"),
        _item("request", at="2026-01-01T00:00:00Z", priority="low"),
        _item("unknown", at="2025-01-01T00:00:00Z", priority="urgent"),
    ]
    kinds = {
        "working": "working", "fyi": "fyi", "action-new": "actionable_task",
        "action-old-z": "finished_result", "action-old-a": "actionable_task",
        "action-urgent": "actionable_task", "owner": "owner_approval", "request": "urgent_request",
    }
    facts = {item["item_id"]: _fact(item, _signal(kinds[item["item_id"]]))
             for item in items if item["item_id"] in kinds}

    page = processing_inventory_page(_snapshot(items), order="priority", facts=facts)

    # one level for everything the owner has to do, a landed result below it, and inside a level the
    # oldest leads - saved priority is a fact on the row, not a tiebreak (2026-09-07)
    assert _ids(page) == [
        "request", "owner", "action-old-a", "action-new", "action-urgent",
        "action-old-z", "fyi", "working", "unknown",
    ]
    assert [page["items"][i]["inventory_facts"]["attention"]["band"] for i in range(8)] == [1, 2, 2, 2, 2, 3, 4, 5]
    unknown = page["items"][-1]["inventory_facts"]["attention"]
    assert unknown == {"state": "unknown", "band": None, "signals": [],
                       "diagnostics": ["attention_requires_revision_bound_fact"]}


def test_priority_order_puts_missing_activity_last_within_the_same_band_and_priority():
    missing = _item("missing", at=None, priority="high")
    invalid = _item("invalid", at="not-a-time", priority="high")
    known = _item("known", at="2026-01-01T00:00:00Z", priority="high")
    items = [missing, invalid, known]
    facts = {item["item_id"]: _fact(item, _signal("actionable_task")) for item in items}

    page = processing_inventory_page(_snapshot(items), order="priority", facts=facts)

    assert _ids(page) == ["known", "invalid", "missing"]
    invalid_activity = page["items"][1]["inventory_facts"]["activity"]
    assert invalid_activity["state"] == "unknown"
    assert "invalid_timestamp:message:invalid.SentAt" in invalid_activity["diagnostics"]


def test_waiting_signal_beats_working_signal_for_the_same_item():
    item = _item("both", at="2026-01-01T00:00:00Z")
    facts = {"both": _fact(item, _signal("working"), _signal("owner_input"))}

    attention = processing_inventory_page(_snapshot([item]), order="priority", facts=facts)["items"][0]["inventory_facts"]["attention"]

    assert attention["band"] == 2
    assert {signal["kind"] for signal in attention["signals"]} == {"working", "owner_input"}


@pytest.mark.parametrize("ordinary", ["actionable_task", "finished_result", "fyi"])
def test_working_stays_band_five_when_only_ordinary_attention_is_also_present(ordinary):
    item = _item("working")
    facts = {"working": _fact(item, _signal("working"), _signal(ordinary))}

    attention = processing_inventory_page(
        _snapshot([item]), order="priority", facts=facts
    )["items"][0]["inventory_facts"]["attention"]

    assert attention["band"] == 5
    assert "working_suppresses_non_owner_attention" in attention["diagnostics"]


def test_urgent_request_still_overrides_working():
    item = _item("working")
    facts = {"working": _fact(item, _signal("working"), _signal("urgent_request"))}

    attention = processing_inventory_page(_snapshot([item]), facts=facts)["items"][0]["inventory_facts"]["attention"]

    assert attention["band"] == 1


def test_semantically_identical_signal_order_has_the_same_facts_revision():
    item = _item("both")
    first = {"both": _fact(item, _signal("working"), _signal("owner_input"))}
    second = {"both": _fact(item, _signal("owner_input"), _signal("working"))}

    first_page = processing_inventory_page(_snapshot([item]), facts=first)
    second_page = processing_inventory_page(_snapshot([item]), facts=second)

    assert first_page["facts_revision"] == second_page["facts_revision"]
    assert first_page["items"] == second_page["items"]


@pytest.mark.parametrize(
    ("starts_at", "ends_at", "expected_band"),
    [
        ("2026-09-06T16:15:00Z", None, 1),
        ("2026-09-06T16:15:00.000001Z", None, None),
        ("2026-09-06T15:45:00Z", "2026-09-06T16:00:00Z", None),
        ("2026-09-06T15:00:00Z", "2026-09-06T15:59:59Z", None),
    ],
)
def test_calendar_attention_window_boundaries(starts_at, ends_at, expected_band):
    item = _item("calendar", at="2026-01-01T00:00:00Z")
    signal = _signal("calendar", starts_at=starts_at, **({"ends_at": ends_at} if ends_at else {}))

    attention = processing_inventory_page(
        _snapshot([item]), order="priority", facts={"calendar": _fact(item, signal)}
    )["items"][0]["inventory_facts"]["attention"]

    assert attention["band"] == expected_band
    assert attention["state"] == ("known" if expected_band else "unknown")


def test_calendar_facts_require_offset_aware_as_of_and_timestamps():
    item = _item("calendar")
    aware = _signal("calendar", starts_at="2026-09-06T16:10:00Z")
    naive = _signal("calendar", starts_at="2026-09-06 16:10:00")

    with pytest.raises(ValueError, match="offset-aware"):
        processing_inventory_page(
            _snapshot([item], as_of="2026-09-06 16:00:00"),
            facts={"calendar": _fact(item, aware)},
        )
    with pytest.raises(ValueError, match="offset-aware"):
        processing_inventory_page(_snapshot([item]), facts={"calendar": _fact(item, naive)})
    backwards = _signal("calendar", starts_at="2026-09-06T16:10:00Z",
                        ends_at="2026-09-06T16:09:00Z")
    with pytest.raises(ValueError, match="later than"):
        processing_inventory_page(_snapshot([item]), facts={"calendar": _fact(item, backwards)})


def test_default_priority_requires_one_unambiguous_task_and_preserves_unknown_raw_value():
    single = _item("single", at=None, priority="HIGH")
    ambiguous = _item("ambiguous", view={
        "tasks": [{"TaskId": "a", "Priority": "urgent"}, {"TaskId": "b", "Priority": "low"}]
    })
    bad = _item("bad", at=None, priority="critical")

    page = processing_inventory_page(_snapshot([single, ambiguous, bad]))
    facts = {item["item_id"]: item["inventory_facts"]["triage_priority"] for item in page["items"]}

    assert facts["single"]["value"] == "high"
    assert facts["ambiguous"]["state"] == "unknown"
    assert "priority_ambiguous_multiple_tasks" in facts["ambiguous"]["diagnostics"]
    assert facts["bad"]["raw"] == "critical"
    assert "unrecognized_priority:critical" in facts["bad"]["diagnostics"]


def test_primary_task_member_disambiguates_default_priority():
    item = _item(
        "multi",
        members=[{"EntityKind": "task", "LocalId": "b", "Role": "primary"}],
        view={"tasks": [{"TaskId": "a", "Priority": "low"}, {"TaskId": "b", "Priority": "urgent"}]},
    )

    priority = processing_inventory_page(_snapshot([item]))["items"][0]["inventory_facts"]["triage_priority"]

    assert priority["value"] == "urgent"
    assert priority["provenance"] == "primary_task:b.Priority"


def test_507_items_paginate_without_cap_duplicates_or_gaps_and_counts_stay_raw():
    items = [_item(f"item-{index:04d}", at=f"2026-01-{index % 28 + 1:02d}T00:00:00Z") for index in range(507)]
    snapshot = _snapshot(items)
    cursor = None
    found: list[str] = []
    pages = 0
    while True:
        page = processing_inventory_page(snapshot, limit=37, cursor=cursor)
        pages += 1
        found.extend(_ids(page))
        assert page["counts"]["canonical_item_count"] == 507
        assert page["counts"]["returned_count"] <= 37
        assert not ({"eligible_count", "unread_count", "next_count"} & page["counts"].keys())
        cursor = page["next_cursor"]
        if cursor is None:
            assert page["counts"]["remaining_count"] == 0
            break

    expected = _ids(processing_inventory_page(snapshot, limit=500))
    expected += _ids(processing_inventory_page(snapshot, limit=500,
                                                cursor=processing_inventory_page(snapshot, limit=500)["next_cursor"]))
    assert found == expected
    assert len(found) == len(set(found)) == 507
    assert pages == 14


def test_page_metadata_and_raw_evidence_are_preserved_without_policy_claims():
    item = _item("kept", at="2026-01-01T00:00:00Z")
    snapshot = _snapshot([item])

    page = processing_inventory_page(snapshot)

    assert page["schema_version"] == PAGE_SCHEMA
    assert page["coverage"] == snapshot["coverage"]
    assert page["coverage"]["unsupported"] == ["calendar", "comments"]
    assert page["worker_attention_available"] is False
    assert page["worker_input_revision"] == "workers-0"
    assert page["items"][0]["legacy_evidence"] == item["legacy_evidence"]
    policy = page["items"][0]["inventory_facts"]
    assert {key: policy[key] for key in ("read_state", "defer_state", "exclusion_state", "actionability")} == {
        "read_state": {"state": "unknown"},
        "defer_state": {"state": "unknown"},
        "exclusion_state": {"state": "unknown"},
        "actionability": {"state": "unknown"},
    }


def test_snapshot_and_facts_are_not_mutated_and_return_is_detached():
    item = _item("one", at="2026-01-01T00:00:00Z")
    snapshot = _snapshot([item])
    facts = {"one": _fact(item, _signal("fyi"))}
    original_snapshot, original_facts = copy.deepcopy(snapshot), copy.deepcopy(facts)

    page = processing_inventory_page(snapshot, facts=facts)
    page["items"][0]["view"]["messages"][0]["SentAt"] = "changed"
    page["coverage"]["unsupported"].append("changed")

    assert snapshot == original_snapshot
    assert facts == original_facts


def test_duplicate_item_ids_and_invalid_limits_are_rejected():
    duplicate = _snapshot([_item("same"), _item("same")])
    with pytest.raises(ValueError, match="duplicate item_id"):
        processing_inventory_page(duplicate)
    for limit in (0, 501, True, 1.5):
        with pytest.raises(ValueError, match="limit"):
            processing_inventory_page(_snapshot([]), limit=limit)
    wrong_counts = _snapshot([_item("one")])
    wrong_counts["coverage"]["canonical_item_count"] = True
    with pytest.raises(ValueError, match="canonical_item_count"):
        processing_inventory_page(wrong_counts)
    wrong_members = _snapshot([_item("one", members=[{"LocalId": "1"}])])
    wrong_members["coverage"]["member_count"] = 0
    with pytest.raises(ValueError, match="member_count"):
        processing_inventory_page(wrong_members)


def test_facts_reject_unknown_items_unknown_fields_and_stale_view_revision_on_first_page():
    item = _item("one")
    snapshot = _snapshot([item])
    with pytest.raises(ValueError, match="unknown item_id"):
        processing_inventory_page(snapshot, facts={"other": _fact(item, _signal("fyi"))})
    with pytest.raises(ValueError, match="keys"):
        processing_inventory_page(snapshot, facts={1: _fact(item, _signal("fyi"))})
    with pytest.raises(ValueError, match="unknown fields"):
        processing_inventory_page(snapshot, facts={"one": {"view_revision": item["view_revision"], "read": True}})
    with pytest.raises(ValueError, match="stale"):
        processing_inventory_page(snapshot, facts={"one": {"view_revision": "old", "attention": {"signals": []}}})


def test_cursor_rejects_malformed_snapshot_order_facts_anchor_and_position_changes():
    items = [_item("a", at="2026-01-01T00:00:00Z"), _item("b", at="2026-02-01T00:00:00Z")]
    snapshot = _snapshot(items)
    facts = {"a": _fact(items[0], _signal("working"))}
    cursor = processing_inventory_page(snapshot, limit=1, facts=facts)["next_cursor"]
    assert cursor

    with pytest.raises(ValueError, match="malformed"):
        processing_inventory_page(snapshot, limit=1, cursor="not base64!", facts=facts)
    with pytest.raises(ValueError, match="snapshot_revision"):
        processing_inventory_page(_snapshot(items, revision="snapshot-2"), limit=1, cursor=cursor, facts=facts)
    with pytest.raises(ValueError, match="order"):
        processing_inventory_page(snapshot, order="priority", limit=1, cursor=cursor, facts=facts)
    changed_facts = {"a": _fact(items[0], _signal("fyi"))}
    with pytest.raises(ValueError, match="facts"):
        processing_inventory_page(snapshot, limit=1, cursor=cursor, facts=changed_facts)
    with pytest.raises(ValueError, match="anchor"):
        processing_inventory_page(snapshot, limit=1, cursor=_rewrite_cursor(cursor, anchor="wrong"), facts=facts)
    with pytest.raises(ValueError, match="position"):
        processing_inventory_page(snapshot, limit=1, cursor=_rewrite_cursor(cursor, position=2), facts=facts)
    with pytest.raises(ValueError, match="query"):
        processing_inventory_page(snapshot, limit=1,
                                  cursor=_rewrite_cursor(cursor, query_revision="other"), facts=facts)
    with pytest.raises(ValueError, match="malformed"):
        processing_inventory_page(snapshot, limit=1,
                                  cursor=_rewrite_cursor(cursor, version=True), facts=facts)
    with pytest.raises(ValueError, match="malformed"):
        processing_inventory_page(snapshot, limit=1,
                                  cursor=_rewrite_cursor(cursor, version=1.0), facts=facts)


def test_worker_revision_change_invalidates_cursor_through_snapshot_revision():
    items = [_item("a"), _item("b")]
    snapshot = _snapshot(items, revision="worker-input-a")
    cursor = processing_inventory_page(snapshot, limit=1)["next_cursor"]
    changed = _snapshot(items, revision="worker-input-b")
    changed["worker_input_revision"] = "workers-1"

    with pytest.raises(ValueError, match="snapshot_revision"):
        processing_inventory_page(changed, limit=1, cursor=cursor)


def test_explicit_activity_requires_aware_timestamp_and_normalizes_offsets():
    a, b = _item("a"), _item("b")
    facts = {
        "a": _fact(a, activity="2026-09-06T12:30:00-04:00"),
        "b": _fact(b, activity="2026-09-06T16:00:00Z"),
    }
    page = processing_inventory_page(_snapshot([a, b]), facts=facts)

    assert _ids(page) == ["a", "b"]
    assert page["items"][0]["inventory_facts"]["activity"]["normalized_at"] == "2026-09-06T16:30:00Z"
    with pytest.raises(ValueError, match="explicit UTC offset"):
        processing_inventory_page(_snapshot([a]), facts={"a": _fact(a, activity="2026-09-06 12:00:00")})
