"""Approved five-band activation over existing funnel membership and read state."""
from copy import deepcopy
from datetime import datetime, timedelta
from random import Random
from unittest import mock

import pytest

from taskuary import funnel, terminal
from taskuary.funnel_selection import SelectionStale, capture_selection, recheck_selection
from taskuary.processing_order import attention_band
from taskuary.store import MemoryStore


NOW = datetime(2026, 9, 6, 12, 0, 0)


def stamp(minutes=0):
    return (NOW + timedelta(minutes=minutes)).isoformat(" ")


@pytest.fixture
def store(monkeypatch):
    value = MemoryStore()
    for name in ("calendar_enabled", "coder_auto_enabled", "general_auto_enabled", "learn_enabled"):
        value.set_setting(name, "0", "test")
    value.set_setting("funnel_hours", "240", "test")
    monkeypatch.setattr(terminal, "live_sessions", lambda tail=0: [])
    monkeypatch.setattr(funnel, "_agenda", lambda _store: [])
    funnel.invalidate()
    funnel.forget_states()
    yield value
    funnel.invalidate()
    value.cx.close()


def message(store, name, *, tid=None, at=None, channel="email", status="routed"):
    return store.add_message({
        "ExternalId": f"ordering:{name}", "ConversationId": f"ordering-thread:{name}",
        "TaskId": tid, "Channel": channel, "SourceName": "ordering@example.test",
        "FromName": "Ordering fixture", "FromEmail": "sender@example.test",
        "Subject": name, "BodyText": f"Please handle {name}.",
        "SentAt": at or stamp(-5), "Status": status,
    })


def task_message(store, name, *, priority="normal", kind="general", status="open", at=None):
    tid = store.create_task({"Title": name, "Kind": kind, "Status": status, "Priority": priority}, "test")
    return tid, message(store, name, tid=tid, at=at)


def item(key, lane, *, kind=None, priority="normal", at=None, **extra):
    return {"key": key, "lane": lane, "kind": kind or lane, "title": key,
            "priority": priority, "when": at or stamp(-5), **extra}


@pytest.mark.parametrize(("facts", "expected"), [
    ({}, 4), ({"actionable": True}, 3), ({"working": True, "actionable": True}, 5),
    ({"owner_wait": True, "working": True}, 2),
    ({"urgent": True, "owner_wait": True, "working": True}, 1),
])
def test_attention_facts_have_approved_precedence(facts, expected):
    assert attention_band(**facts) == expected


def test_lanes_rank_asked_then_broken_then_landed_without_mutating_input():
    # the lane is the rank (2026-09-07): an ask outranks a hand-off still waiting for its agent outranks a
    # failed check outranks what merely landed, however old each is; inside one rank the oldest still comes first
    rows = [item("ask", "asked", at=stamp(-1)), item("broken", "broken", at=stamp(-2)),
            item("idea", "forgotten", kind="idea", at=stamp(-3)),
            item("result", "report", at=stamp(-4)), item("todo", "queued", at=stamp(-6))]
    before = deepcopy(rows)
    assert [row["key"] for row in funnel._order(rows)] == ["ask", "todo", "broken", "result", "idea"]
    assert {funnel._band(row) for row in rows} == {3}
    assert rows == before


def test_priority_precedes_age_and_unknown_values_never_invent_urgency():
    rows = [item("low", "asked", priority="low", at=stamp(-90)),
            item("unknown", "asked", priority="ASAP", at=stamp(-100)),
            item("normal", "asked", at=stamp(-80)),
            item("urgent", "asked", priority="urgent", at=stamp(-1)),
            item("high", "asked", priority="high", at=stamp(-2))]
    assert [row["key"] for row in funnel._order(rows)] == ["urgent", "high", "normal", "low", "unknown"]


def test_equal_activity_uses_stable_keys_and_missing_or_invalid_activity_is_last():
    rows = [item("msg:2", "asked"), item("msg:1", "asked"),
            item("missing", "asked", at=""), item("invalid", "asked", at="not a date")]
    rows[2]["when"] = ""
    for seed in range(6):
        shuffled = list(rows)
        Random(seed).shuffle(shuffled)
        assert [row["key"] for row in funnel._order(shuffled)] == ["msg:1", "msg:2", "invalid", "missing"]


def test_producer_sort_activity_keeps_subseconds_and_normalizes_equivalent_offsets():
    # Reverse lexical keys ensure a truncated timestamp would produce the wrong order.
    later = funnel._item("a-later", "asked", "asked", "Later", when="2026-09-06T12:00:00.900+00:00", priority="normal")
    earlier = funnel._item("z-earlier", "report", "asked", "Earlier", when="2026-09-06T12:00:00.100+00:00", priority="normal")
    assert [row["key"] for row in funnel._order([later, earlier])] == ["z-earlier", "a-later"]
    equivalent = funnel._item("b-equivalent", "asked", "asked", "Same instant",
                              when="2026-09-06T08:00:00.900-04:00", priority="normal")
    assert [row["key"] for row in funnel._order([equivalent, later])] == ["a-later", "b-equivalent"]


@pytest.mark.parametrize(("start_seconds", "end_seconds", "ready", "present"), [
    (900, 1800, True, True), (900.001, 1800, False, True), (901, 1800, False, True), (959, 1800, False, True),
    (0, 1800, True, True), (-240, 1800, True, True), (-600, 1, True, False), (-600, 0, False, False),   # started: gone after the grace (2026-09-07)
])
def test_calendar_uses_exact_fifteen_minute_and_current_event_boundaries(
        store, start_seconds, end_seconds, ready, present):
    event = {"subject": "Exact meeting", "start": (NOW + timedelta(seconds=start_seconds)).isoformat(),
             "end": (NOW + timedelta(seconds=end_seconds)).isoformat(), "who": []}
    with mock.patch.object(funnel, "_agenda", return_value=[event]):
        rows = funnel.from_calendar(store, NOW)
    assert bool(rows) is present
    if present:
        assert rows[0]["lane"] == "time"
        assert rows[0]["calendar_ready"] is ready
        assert funnel._band(rows[0]) == (1 if ready else 3)
        assert funnel._not_yet(rows[0]) is not ready


def test_time_critical_items_lead_waits_and_scheduled_items_do_not_raise_urgency():
    current = item("current", "approve", kind="review", priority="low")
    rows = [item("wait", "blocked", kind="agent", priority="urgent"),
            item("scheduled", "time", kind="meeting", calendar_ready=False, mins=60),
            item("urgent", "time", kind="asked"), current,
            item("meeting", "time", kind="meeting", calendar_ready=True, mins=15),
            item("working", "working", kind="todo", priority="urgent")]
    ordered = funnel._order(rows)
    assert [row["key"] for row in ordered] == ["meeting", "urgent", "wait", "current", "scheduled", "working"]
    assert [row["key"] for row in funnel.more_urgent(ordered, "current")] == ["meeting", "urgent"]
    assert [row["key"] for row in funnel.more_urgent(ordered, "scheduled")] == ["meeting", "urgent", "wait", "current"]
    assert "scheduled" not in [row["key"] for row in funnel.more_urgent(ordered, "working")]


@pytest.mark.parametrize("kind", ["coding", "general"])
@pytest.mark.parametrize("request_kind", ["input_needed", "approval_needed"])
def test_both_workers_move_between_working_and_owner_wait_with_feed_band_parity(store, kind, request_kind):
    tid, mid = task_message(store, f"{kind}-{request_kind}", priority="urgent", kind=kind, status="in_progress")
    worker = {"taskId": tid, "agent": kind, "sid": "synthetic", "started": stamp(-30),
              "idle": 0, "waiting": False, "tail": ["Still working"]}
    frozen = list(store.cx.iterdump())
    for waiting, expected in ((False, 5), (True, 2), (False, 5)):
        observed = {**worker, "waiting": waiting}
        if waiting:
            observed["request"] = {"kind": request_kind, "request_id": "fixed-request", "text": "Which file?",
                                   "at": stamp(-2), "choices": []}
        pile = funnel.build(store, now=NOW, reconcile=False, live_state=[observed])
        assert len(pile["items"]) == 1
        row = pile["items"][0]
        feed = next(row for row in store.feed(live_state=[observed]) if row["MessageId"] == mid)
        assert row["key"] == feed["FunnelKey"] == f"agent:{tid}"
        assert row["priority"] == "urgent"
        assert funnel._band(row) == feed["UnreadRank"] == expected
        assert feed["Unread"] == 1
        if waiting:
            assert row["request_kind"] == request_kind
            assert row["since"] == stamp(-2)
    assert list(store.cx.iterdump()) == frozen


def test_feed_review_report_and_task_producers_keep_saved_priority(store):
    _ask_tid, ask_mid = task_message(store, "Ordinary ask", priority="low")
    review_tid, review_mid = task_message(store, "Draft source", priority="urgent")
    rid = store.add_review({"TaskId": review_tid, "MessageId": review_mid, "Kind": "reply",
                            "Status": "pending", "DraftText": "Saved draft"})
    latest = message(store, "Newer draft context", tid=review_tid, at=stamp(-1))
    report_tid = store.create_task({"Title": "Failed report", "Priority": "high", "Status": "open"}, "test")
    report_mid = message(store, "Ordering report FAILED", tid=report_tid, channel="report", status="feed")
    standalone = message(store, "Plain FYI", status="filed")
    feed = store.feed(live_state=[])
    produced = {row["key"]: row for row in funnel.from_feed(store, feed)}
    assert produced[f"msg:{ask_mid}"]["priority"] == "low"
    review = produced[f"review:{rid}"]
    assert (review["priority"], review["mid"], review["when"], funnel._band(review)) == ("urgent", latest, stamp(-1), 2)
    assert produced[f"report:{report_mid}"]["priority"] == "high"
    by_mid = {row["MessageId"]: row for row in feed}
    for mid, band in ((ask_mid, 3), (review_mid, 2), (report_mid, 3), (standalone, 4)):
        assert by_mid[mid]["UnreadRank"] == band


def test_ideas_use_their_own_saved_priority_not_the_related_task_priority(store):
    tid, mid = task_message(store, "Referenced urgent work", priority="urgent")
    own = store.upsert_idea({"key": "ordering-own", "kind": "followup", "text": "Independent follow-up",
                            "action": {"mid": mid, "tid": tid, "triage": {"intent": "task", "priority": "low"}}}, stamp(-3))
    unknown = store.upsert_idea({"key": "ordering-unknown", "kind": "followup", "text": "Another independent follow-up",
                                "action": {"tid": tid}}, stamp(-4))
    rows = {row["key"]: row for row in funnel.from_forgotten(store, set(), set(), reconcile=False)}
    assert rows[f"idea:{own['IdeaId']}"]["priority"] == "low"
    assert rows[f"idea:{unknown['IdeaId']}"]["priority"] in (None, "")


@pytest.mark.parametrize(("intent", "priority", "expected_band"), [
    ("task", "urgent", 1), ("reply_only", "urgent", 1), ("fyi", "urgent", 4),
    ("task", None, 3),
])
def test_only_an_ideas_explicit_urgent_owner_request_is_promoted(store, intent, priority, expected_band):
    idea = store.upsert_idea({"key": "own-ranking", "kind": "followup", "text": "Urgent ASAP is only source text",
                             "action": {"triage": {"intent": intent, "priority": priority}}}, stamp(-3))
    produced = funnel.from_forgotten(store, set(), set(), reconcile=False)
    assert len(produced) == 1 and produced[0]["key"] == f"idea:{idea['IdeaId']}"
    assert produced[0]["priority"] == priority
    assert funnel._band(produced[0]) == expected_band


def test_urgent_idea_ordering_does_not_change_its_existing_age_window(store):
    store.set_setting("funnel_hours", "12", "test")
    idea = store.upsert_idea({"key": "old-urgent", "kind": "followup", "text": "Old independent request",
                             "action": {"triage": {"intent": "task", "priority": "urgent"}}}, stamp(-25 * 60))
    produced = funnel.from_forgotten(store, set(), set(), reconcile=False)
    assert len(produced) == 1 and produced[0]["key"] == f"idea:{idea['IdeaId']}"
    assert funnel._band(produced[0]) == 1
    assert funnel._aged_out(produced[0], NOW, 12) is True
    assert funnel.build(store, now=NOW, reconcile=False, live_state=[])["items"] == []


def test_failed_report_does_not_become_an_urgent_request_only_in_feed(store):
    tid = store.create_task({"Title": "Failed scheduled check", "Priority": "urgent", "Status": "open"}, "test")
    mid = message(store, "Scheduled check FAILED", tid=tid, channel="report", status="feed")
    feed = next(row for row in store.feed(live_state=[]) if row["MessageId"] == mid)
    produced = funnel.from_feed(store, [feed])[0]
    assert produced["lane"] == "broken"
    assert produced["bad"] is True
    assert funnel._band(produced) == feed["UnreadRank"] == 3


@pytest.mark.parametrize(("failed", "subject", "expected_band"), [
    (True, "Report with an ordinary title", 3),
    (False, "Old title ending FAILED", 1),
])
def test_report_rank_uses_saved_run_outcome_even_when_subject_disagrees(store, monkeypatch, failed, subject, expected_band):
    sid = store.save_source({"Channel": "report", "Address": "ordering@example.test", "Active": 1,
                             "ConfigJson": '{"title":"Ordering report"}'}, "test")
    store.add_report_run(sid, {"at": stamp(-1), "title": "Ordering report", "failed": failed})
    monkeypatch.setitem(funnel._SOURCES, "at", 0.0)
    monkeypatch.setitem(funnel._SOURCES, "by", {})
    tid = store.create_task({"Title": "Matched report work", "Priority": "urgent", "Status": "open"}, "test")
    mid = message(store, subject, tid=tid, channel="report", status="feed")
    feed = next(row for row in store.feed(live_state=[]) if row["MessageId"] == mid)
    produced = funnel.from_feed(store, [feed])[0]
    assert funnel._band(produced) == feed["UnreadRank"] == expected_band
    if failed:
        assert produced["lane"] == "broken" and produced["bad"] is True
    else:
        assert produced["lane"] == "time" and produced["kind"] == "asked"


def test_wrapup_keeps_task_priority_and_actual_completion_activity(store):
    tid, mid = task_message(store, "Finished result", priority="high")
    rid = store.add_review({"TaskId": tid, "MessageId": mid, "Kind": "reply", "Status": "pending", "DraftText": "Done."})
    store.decide_review(rid, "approved", "Done.", "owner")
    store._exec("UPDATE review SET DecidedAt=? WHERE ReviewId=?", (stamp(-2), rid))
    result = funnel.from_wrapped(store, NOW, set())
    assert len(result) == 1
    assert (result[0]["priority"], result[0]["when"], funnel._band(result[0])) == ("high", stamp(-2), 3)


def test_priority_reorder_invalidates_captured_next_without_changing_read_or_task_state(store):
    first_tid, first_mid = task_message(store, "High priority", priority="high", at=stamp(-2))
    second_tid, second_mid = task_message(store, "Low priority", priority="low", at=stamp(-20))
    done = message(store, "Previously handled", status="filed")
    deferred = message(store, "Temporarily deferred", status="filed")
    store.set_funnel_state(f"msg:{done}", "done", note="Owner receipt")
    store.set_funnel_state(f"msg:{deferred}", "later", until=stamp(60), note="Temporary interval")
    before = list(store.cx.iterdump())
    initial = capture_selection(store, now=NOW)
    assert initial.selected["mid"] == first_mid
    assert list(store.cx.iterdump()) == before
    store.update_task(second_tid, {"Priority": "urgent"}, "owner")
    updated = list(store.cx.iterdump())
    with pytest.raises(SelectionStale) as stale:
        recheck_selection(store, initial, now=NOW)
    assert stale.value.capture.selected["mid"] == second_mid
    assert stale.value.capture.revision != initial.revision
    assert list(store.cx.iterdump()) == updated
    assert store.get_task(first_tid)["Status"] == store.get_task(second_tid)["Status"] == "open"
    assert set(store.funnel_states()) == {f"msg:{done}", f"msg:{deferred}"}


def test_named_current_review_survives_more_than_400_arrivals_without_expanding_default_queue(store):
    tid, mid = task_message(store, "Older explicit Current", at=stamp(-180))
    rid = store.add_review({"TaskId": tid, "MessageId": mid, "Kind": "reply", "Status": "pending",
                            "DraftText": "Retain this exact draft."})
    current_key = f"review:{rid}"
    initial = funnel.next_item(store, current_key)
    assert (initial["key"], initial["mid"], initial["rid"]) == (current_key, mid, rid)
    for index in range(405):
        message(store, f"New arrival {index:03}", status="filed", at=stamp(-1))
    store.set_setting("funnel_max", "3", "test")
    before = list(store.cx.iterdump())

    # Automatic queue coverage remains the legacy 400 input rows and configured cap.
    assert len(store.feed(limit=400, live_state=[])) == 400
    ordinary = funnel.build(store, now=NOW, reconcile=False, live_state=[])
    assert len(ordinary["items"]) == 3
    assert ordinary["hidden"] == 397
    assert current_key not in {row["key"] for row in ordinary["items"]}

    # Returning to an already named Current must not confuse that input cap with absence.
    restored = funnel.next_item(store, current_key)
    assert (restored["key"], restored["mid"], restored["rid"]) == (current_key, mid, rid)
    assert restored["lane"] == "approve" and restored["order_band"] == 2
    assert store.get_review(rid)["DraftText"] == "Retain this exact draft."
    assert store.get_review(rid)["Status"] == "pending"
    assert store.get_task(tid)["Status"] == "open"
    assert list(store.cx.iterdump()) == before


def test_current_card_retains_authoritative_band_when_its_presentation_lane_is_asked():
    from taskuary import concierge
    row = item('idea:urgent', 'asked', kind='idea', urgent_request=True, order_band=1)
    card = concierge.card_for(row)
    assert (card['key'], card['lane'], card['order_band']) == ('idea:urgent', 'asked', 1)
    assert card['order_band'] == funnel._band(row)
