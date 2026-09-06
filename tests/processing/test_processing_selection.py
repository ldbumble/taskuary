"""PW-106/PW-114/PW-115/PW-118 partial legacy captured-selection gates."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta
from unittest import mock

import pytest

from taskuary import concierge, funnel, general
from taskuary.funnel_selection import (
    SelectionCapture,
    SelectionStale,
    capture_selection,
    recheck_selection,
    selection_fields,
    validate_selection,
)
from taskuary.store import MemoryStore


NOW = datetime(2026, 9, 6, 12, 0, 0)


def stamp(minutes=-5):
    return (NOW + timedelta(minutes=minutes)).strftime("%Y-%m-%d %H:%M:%S")


def store():
    value = MemoryStore()
    for name in ("calendar_enabled", "coder_auto_enabled", "learn_enabled"):
        value.set_setting(name, "0", "test")
    funnel.invalidate()
    funnel.forget_states()
    return value


def message(value, n=1, *, status="routed", channel="email", body=None):
    return value.add_message({
        "ExternalId": f"selection:{n}", "ConversationId": f"selection-thread:{n}",
        "Channel": channel, "SourceName": "fixture", "Subject": f"Selection {n}",
        "FromName": f"Person {n}", "FromEmail": f"person{n}@example.test",
        "SentAt": stamp(-n), "BodyText": body or f"Please handle selection {n}.",
        "Status": status,
    })


def item(key, lane="asked", **values):
    return {
        "key": key, "kind": values.pop("kind", "asked"), "lane": lane,
        "title": values.pop("title", key), "when": stamp(), **values,
    }


class NoStore:
    """Presentation protocol fake: no SQLite cursor means empty display backing."""


def captured(items, **scope):
    with mock.patch.object(funnel, "build", return_value={
        "rev": "legacy", "items": items, "hidden": 0, "muted": 0,
        "rules": [], "lanes": [], "events": [{"transient": True}],
    }) as built:
        result = capture_selection(NoStore(), now=NOW, **scope)
    assert built.call_args.kwargs["reconcile"] is False
    return result


def test_capture_is_deterministic_strict_and_does_not_call_mutating_pile_or_announce():
    value = store()
    mid = message(value, body="x" * 5000 + " first ending")
    writes = (value.cx.total_changes, value._writes)
    with mock.patch.object(funnel, "pile", side_effect=AssertionError("pile announces")), \
         mock.patch.object(funnel, "announce", side_effect=AssertionError("watcher writes")), \
         mock.patch("taskuary.terminal.live_sessions", return_value=[]):
        first = capture_selection(value, now=NOW)
        repeated = capture_selection(value, now=NOW)
        assert (value.cx.total_changes, value._writes) == writes
        value.update_message_body(mid, "x" * 5000 + " changed ending")
        changed = capture_selection(value, now=NOW)

    assert (first.revision, first.member_keys) == (repeated.revision, repeated.member_keys)
    assert len(first.revision) == 64
    assert changed.member_keys == first.member_keys
    assert changed.revision != first.revision
    assert (value.cx.total_changes, value._writes) == (writes[0] + 1, writes[1] + 1)


def test_scope_and_complete_order_are_revision_bound_while_events_are_not():
    items = [
        item("msg:1", mid=1, channel="email"),
        item("msg:2", mid=2, channel="email", surfaced=True, surfaced_at=stamp(-60)),
        item("agent:3", lane="working", kind="agent", tid=3),
    ]
    base = captured(items)
    reordered = captured([items[1], items[0], items[2]])
    mail = captured(items, only="mail")
    surfaced = captured(items, include_surfaced=True)
    excluded = captured(items, include_surfaced=True, exclude="msg:1")
    same_without_event = captured([dict(value) for value in items])

    assert base.revision == same_without_event.revision
    assert len({base.revision, reordered.revision, mail.revision,
                surfaced.revision, excluded.revision}) == 5
    assert base.member_keys == ("msg:1",)
    assert excluded.member_keys == ("msg:2",)


def test_unrelated_worker_display_churn_does_not_starve_selected_context_recheck():
    selected = item("msg:1", mid=1, channel="email", preview="original request")
    worker = item("agent:3", lane="working", kind="agent", tid=3,
                  tail=["first progress line"])
    before = captured([selected, worker])
    unrelated = captured([selected, {**worker, "tail": ["another progress line"]}])
    changed_selected = captured([{**selected, "preview": "materially changed request"}, worker])

    assert unrelated.selected["presentation_revision"] == before.selected["presentation_revision"]
    assert unrelated.pile["items"][1]["presentation_revision"] != before.pile["items"][1]["presentation_revision"]
    assert unrelated.revision == before.revision
    assert changed_selected.member_keys == before.member_keys
    assert changed_selected.revision != before.revision


def test_fyi_capture_uses_one_scoped_order_and_names_the_exact_four_member_card():
    values = [item(f"msg:{n}", lane="fyi", kind="fyi", mid=n, channel="email")
              for n in range(1, 6)]
    # An assistant-local FYI is deliberately in the same lane but not incoming mail.
    values.insert(1, item("idea:9", lane="fyi", kind="idea", idea=9, channel="assistant"))
    cap = captured(values, only="mail")

    assert cap.member_keys == ("msg:1", "msg:2", "msg:3", "msg:4")
    assert cap.selected["key"] == "fyis:msg:1,msg:2,msg:3,msg:4"
    assert [child["key"] for child in cap.selected["items"]] == list(cap.member_keys)
    assert selection_fields(cap)["expected_next_members"] == list(cap.member_keys)

    after_first = captured(values, only="mail", exclude="msg:1")
    assert after_first.member_keys == ("msg:2", "msg:3", "msg:4", "msg:5")


def test_validation_reports_the_fresh_selection_and_recheck_never_replaces_the_capture():
    cap = captured([item("msg:1", mid=1, channel="email")])
    assert validate_selection(
        cap, selection_revision=cap.revision,
        expected_next_key="msg:1", expected_next_members=["msg:1"],
    ) is cap

    with pytest.raises(SelectionStale) as stale:
        validate_selection(
            cap, selection_revision="old", expected_next_key="msg:old",
            expected_next_members=["msg:old"],
        )
    assert stale.value.detail == {
        "code": "selection_stale",
        **selection_fields(cap),
        "requested_next_key": "msg:old",
        "retryable": True,
    }


def test_late_drift_guard_runs_after_model_but_before_sid_settle_or_record():
    value = store()
    mid = message(value)
    with mock.patch("taskuary.terminal.live_sessions", return_value=[]):
        cap = capture_selection(value, now=NOW)

    model_called = []
    def model(*_args, **_kwargs):
        model_called.append(True)
        value.update_message_body(mid, "New facts arrived while the model was speaking.")
        return "Person 1 asked for selection 1. Nothing has been done yet. Please review it."

    @contextmanager
    def guard():
        recheck_selection(value, cap, now=NOW)
        yield

    with mock.patch.object(concierge, "_remember_sid") as remember, \
         mock.patch.object(funnel, "settle") as settle, \
         mock.patch.object(concierge, "record_related") as record:
        with pytest.raises(SelectionStale):
            concierge.surface(value, llm=model, selection=cap, commit_guard=guard)
    assert model_called == [True]
    remember.assert_not_called()
    settle.assert_not_called()
    record.assert_not_called()
    assert value.funnel_states() == {}


def test_captured_surface_commits_exact_item_and_fyi_members_under_one_guard():
    value = store()
    for n in range(1, 6):
        message(value, n, status="filed")
    with mock.patch("taskuary.terminal.live_sessions", return_value=[]):
        cap = capture_selection(value, now=NOW)
    entered = []

    @contextmanager
    def guard():
        entered.append("enter")
        yield
        entered.append("exit")

    with mock.patch.object(funnel, "pile", side_effect=AssertionError("must not reselect")), \
         mock.patch.object(funnel, "next_item", side_effect=AssertionError("must not reselect")), \
         mock.patch.object(funnel, "fyi_batch", side_effect=AssertionError("must not re-batch")), \
         mock.patch.object(concierge, "_brain_for", return_value=None):
        out = concierge.surface(value, selection=cap, commit_guard=guard)

    assert out["item"]["key"] == cap.selected["key"]
    assert [child["key"] for child in out["item"]["items"]] == list(cap.member_keys)
    assert entered == ["enter", "exit"]
    states = value.funnel_states()
    assert set(states) == set(cap.member_keys)
    assert all(state["Status"] == "surfaced" for state in states.values())


def test_working_or_settling_only_capture_is_pending_and_never_claims_all_done():
    cap = captured([
        item("agent:1", lane="working", kind="agent", tid=1),
        item("msg:2", settling=True, mid=2, channel="email"),
        item("meeting:soon", lane="time", kind="meeting", mins=30),
    ])
    assert cap.selected is None
    assert cap.pending == {"working": 1, "settling": 1, "scheduled": 1}

    value = store()
    with mock.patch.object(concierge, "_brain_for", return_value=None):
        out = concierge.surface(value, selection=cap)
    assert out["item"] is None
    assert out["say"] != concierge.ALL_DONE
    assert "in progress" in out["say"]
    assert "triaged" in out["say"]


def test_watcher_cards_keep_readable_history_with_explicit_background_provenance():
    value = store()
    tid = value.create_task({
        "Title": "Import census", "Kind": "coding", "Status": "in_progress",
    }, "owner")
    message(value, tid, body="Import the census.")
    working = [{
        "taskId": tid, "agent": "codex", "label": "codex", "started": stamp(-60),
        "idle": 2, "waiting": False, "tail": ["editing"],
    }]
    asking = [{
        **working[0], "idle": 200, "waiting": True, "tail": ["Which cutoff should I use?"],
    }]
    with mock.patch.object(funnel, "DWELL", 0), \
         mock.patch("taskuary.terminal.live_sessions", return_value=working):
        assert funnel.announce(value) == []
    with mock.patch.object(funnel, "DWELL", 0), \
         mock.patch("taskuary.terminal.live_sessions", return_value=asking):
        events = funnel.announce(value)

    assert events[0]["card"]["background_event"] is True
    dock = general.dock_task(value)[0]
    history = concierge.history(value, dock["TaskId"])
    assert history[-1]["card"]["background_event"] is True
    assert history[-1]["card"]["kind"] == "agent"

    explicit = concierge.card_for(events[0]["card"])
    assert "background_event" not in explicit
