"""What the walk puts up next, from the rail's own rows (railwalk, 2026-10-30). Kept from the captured-selection gates (PW-106/114/115/118)
whose machinery is gone: what they pinned about WHICH row comes up - a task an agent is working is walked in its place, an Advisor idea is
walked alone before the FYI, a batch key is answered without a full-history build, and the watcher writes no chat card."""
from __future__ import annotations

from datetime import datetime, timedelta
from unittest import mock

import pytest

from taskuary import concierge, funnel, general
from taskuary.store import MemoryStore
from tests.railwalk_rows import RowWalk


NOW = datetime(2026, 9, 6, 12, 0, 0)


def stamp(minutes=-5):
    return (NOW + timedelta(minutes=minutes)).strftime("%Y-%m-%d %H:%M:%S")


def store():
    value = MemoryStore()
    for name in ("calendar_enabled", "coding_auto_enabled"):
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
    return {"key": key, "kind": values.pop("kind", "asked"), "lane": lane, "title": values.pop("title", key), "when": stamp(), **values}


@pytest.fixture
def walk():
    w = RowWalk(store(), [])
    yield w
    w.close()


def test_a_working_agents_task_is_walked_like_any_task(walk):
    # a task an agent is working is under Tasks and the walk takes it in its place (the owner, 2026-10-21)
    walk.rows[:] = [item("agent:1", lane="working", kind="agent", tid=1, order_band=2),
                    item("msg:2", settling=True, mid=2, channel="email")]
    assert walk.start() == "agent:1"


def test_a_row_still_being_read_is_not_on_the_walk(walk):
    """Settling rows are not on the line (spec 3.1): with nothing else, the walk has reached its end."""
    walk.rows[:] = [item("msg:2", settling=True, mid=2, channel="email")]
    assert walk.start() is None


def test_an_advisor_idea_is_walked_before_the_fyi_and_never_inside_their_batch(walk):
    # the rail draws Advisor ideas above FYI; oldest-first had the fresh idea behind every older mail, so Next opened the FYI
    # batch and walked past it - and an idea that did lead would have been read as one more fyi in the card
    old = [item(f"mail:{n}", "fyi", kind="fyi", order_band=4, when=stamp(-600 - n)) for n in range(5)]
    idea = item("idea:1", "fyi", kind="idea", order_band=4, when=stamp(-2))
    walk.rows[:] = funnel._order(old + [idea])
    assert walk.rows[0]["key"] == "idea:1"
    assert walk.start() == "idea:1"                                    # alone
    nxt = walk.next("idea:1")                                          # Next from the idea walks down to the FYI below it (2026-10-22)
    assert nxt.startswith("fyis:") and "idea:1" not in nxt


def test_watcher_events_write_no_chat_card_and_explicit_cards_carry_no_background_flag():
    value = store()
    tid = value.create_task({"Title": "Import census", "Kind": "coding", "Status": "in_progress"}, "owner")
    message(value, tid, body="Import the census.")
    working = [{"taskId": tid, "agent": "codex", "label": "codex", "started": stamp(-60), "idle": 2, "waiting": False, "tail": ["editing"]}]
    asking = [{**working[0], "idle": 200, "waiting": True, "state": "asking", "tail": ["Which cutoff should I use?"]}]
    with mock.patch.object(funnel, "DWELL", 0), mock.patch("taskuary.terminal.live_sessions", return_value=working):
        assert funnel.announce(value) == []
    with mock.patch.object(funnel, "DWELL", 0), mock.patch("taskuary.terminal.live_sessions", return_value=asking):
        events = funnel.announce(value)
    assert events[0]["kind"] == "asking" and events[0]["card"] is None          # a strip notice, never a chat card (PW-165)
    dock = general.dock_task(value)[0]
    assert concierge.history(value, dock["TaskId"]) == []                     # the watcher wrote nothing into the chat
    with mock.patch("taskuary.terminal.live_sessions", return_value=asking):
        explicit = concierge.card_for(funnel.next_item(value, f"agent:{tid}", include_surfaced=True) or {})
    assert explicit.get("kind") == "agent"
    assert "background_event" not in explicit


def test_a_batch_key_is_answered_by_batch_item_and_never_by_the_full_history_build():
    """After "All read, Next" the page sends the batch key it holds as `current`. A `fyis:` key goes to batch_item first; no build may be
    asked for full history (~9 s of an 11.6 s press, measured live on 2026-09-17)."""
    values = [item(f"msg:{n}", lane="fyi", kind="fyi", mid=n, channel="email") for n in range(1, 5)]
    key = "fyis:" + ",".join(v["key"] for v in values)

    class ReadsActive:
        def processing_reads_active(self): return True
    with mock.patch.object(funnel, "build", return_value={"rev": "legacy", "items": values, "hidden": 0,
                                                          "muted": 0, "rules": [], "lanes": [], "events": []}) as built, \
            mock.patch.object(funnel, "_present_one", side_effect=lambda s, i: i):
        got = funnel.next_item(ReadsActive(), key, items=values)
    assert got["key"] == key and [c["key"] for c in got["items"]] == [v["key"] for v in values]
    assert not any(c.kwargs.get("full_history") for c in built.call_args_list), built.call_args_list
