"""PW-106: complete legacy-funnel display freshness without selection changes."""
from __future__ import annotations

import contextlib
from datetime import datetime, timedelta
from unittest import mock

from taskuary import concierge, funnel
from taskuary.funnel_presentation import display_revision, item_revision
from taskuary.store import MemoryStore


def stamp(seconds=0):
    return (datetime.now() + timedelta(seconds=seconds)).strftime("%Y-%m-%d %H:%M:%S")


def seeded(*, body=None, review=False):
    store = MemoryStore()
    for name in ("calendar_enabled", "coder_auto_enabled", "learn_enabled"):
        store.set_setting(name, "0", "test")
    tid = store.create_task({
        "Title": "Quarterly close", "Summary": "Reconcile the close", "Kind": "reply",
        "Status": "open", "Priority": "normal", "Source": "email",
    }, "test")
    mid = store.add_message({
        "TaskId": tid, "ExternalId": "mail:one", "ConversationId": "thread:close",
        "Channel": "email", "SourceName": "inbox", "Subject": "Quarterly close",
        "FromName": "Dana", "FromEmail": "dana@example.test", "SentAt": stamp(-30),
        "BodyText": body or "Please reconcile the close.", "Status": "routed",
    })
    rid = None
    if review:
        rid = store.add_review({
            "TaskId": tid, "MessageId": mid, "Kind": "draft", "Status": "pending",
            "DraftText": "Initial draft", "Reason": "needs a reply",
        })
    funnel.invalidate()
    return store, tid, mid, rid


def one(store):
    picture = funnel.present(store, funnel.build(store, keep_surfaced=True))
    assert len(picture["items"]) == 1
    return picture, picture["items"][0]


def test_pure_revisions_are_strict_canonical_and_event_delivery_is_transient():
    first = item_revision({"key": "msg:1", "nested": {"b": 2, "a": 1}}, {"messages": [{"BodyText": "whole"}]})
    reordered = item_revision({"nested": {"a": 1, "b": 2}, "key": "msg:1"}, {"messages": [{"BodyText": "whole"}]})
    assert first == reordered
    assert len(first) == 64

    base = {"items": [{"key": "msg:1", "presentation_revision": first}], "alerts": [], "hidden": 0}
    assert display_revision({**base, "events": [{"kind": "asking"}], "rev": "old"}) == display_revision(
        {**base, "events": [{"kind": "done"}], "rev": "new"})
    assert display_revision(base) != display_revision({**base, "alerts": [{"key": "alert:msg:1"}]})
    assert display_revision(base) != display_revision({**base, "current": None})


def test_full_body_beyond_preview_changes_strong_revisions_but_not_legacy_selection_revision():
    prefix = "x" * 5000
    store, _tid, mid, _rid = seeded(body=prefix + " first ending")
    before, old_item = one(store)
    repeated, repeated_item = one(store)
    assert repeated["display_revision"] == before["display_revision"]
    assert repeated_item["presentation_revision"] == old_item["presentation_revision"]
    store.update_message_body(mid, prefix + " second ending")
    after, new_item = one(store)

    assert (new_item["key"], new_item["lane"], new_item["preview"]) == (
        old_item["key"], old_item["lane"], old_item["preview"])
    assert after["rev"] == before["rev"]
    assert new_item["presentation_revision"] != old_item["presentation_revision"]
    assert after["display_revision"] != before["display_revision"]


def test_draft_edit_clear_and_delete_change_same_review_presentation():
    store, _tid, _mid, rid = seeded(review=True)
    before, initial = one(store)
    assert initial["key"] == f"review:{rid}"

    store.save_review_draft(rid, "A materially revised reply")
    edited, edited_item = one(store)
    store.save_review_draft(rid, "")
    cleared = funnel.present(store, {"items": [], "current": edited_item})
    store._exec("DELETE FROM review WHERE ReviewId=?", (rid,))
    deleted = funnel.present(store, {"items": [], "current": edited_item})

    assert edited["rev"] == before["rev"]
    assert edited_item["key"] == initial["key"]
    assert edited_item["presentation_revision"] != initial["presentation_revision"]
    assert cleared["current"]["presentation_revision"] != edited_item["presentation_revision"]
    assert deleted["current"]["key"] == edited_item["key"]
    assert deleted["current"]["presentation_revision"] != cleared["current"]["presentation_revision"]


def test_taskless_review_tracks_new_conversation_context_and_reply_permission():
    store = MemoryStore()
    mid = store.add_message({
        "ExternalId": "chat:first", "ConversationId": "chat:dana", "Channel": "teams",
        "SourceName": "teams", "Subject": "Access", "FromName": "Dana",
        "SentAt": stamp(-90), "BodyText": "Can you reset access?", "Status": "routed",
    })
    rid = store.add_review({
        "MessageId": mid, "Kind": "draft", "Status": "pending", "DraftText": "I will reset it.",
        "Reason": "needs a reply",
    })
    funnel.invalidate()
    _picture, item = one(store)
    assert item["key"] == f"review:{rid}" and item.get("tid") is None
    static = {"items": [], "current": item}

    store.add_message({
        "ExternalId": "chat:later", "ConversationId": "chat:dana", "Channel": "teams",
        "SourceName": "teams", "Subject": "Access", "FromName": "Dana",
        "SentAt": stamp(-30), "BodyText": "It works now; no reset needed.", "Status": "routed",
    })
    newer = funnel.present(store, static)
    assert newer["current"]["key"] == item["key"]
    assert newer["current"]["presentation_revision"] != item["presentation_revision"]

    store.set_setting("reply_channels", "email", "owner")
    disabled = funnel.present(store, static)
    assert disabled["current"]["presentation_revision"] != newer["current"]["presentation_revision"]
    github = store.get_connector_by_type("github")
    store.save_connector({"ConnectorId": github["ConnectorId"], "ConfigJson": "[]"}, "owner")
    assert len(funnel.present(store, static)["current"]["presentation_revision"]) == 64


def test_exact_group_members_and_attachment_metadata_change_without_row_shape_change():
    store, tid, _mid, _rid = seeded()
    old = store.add_message({
        "TaskId": tid, "ExternalId": "mail:old", "ConversationId": "thread:close",
        "Channel": "email", "SourceName": "inbox", "Subject": "Older detail",
        "FromName": "Dana", "SentAt": stamp(-120), "BodyText": "Old member", "Status": "routed",
    })
    before, initial = one(store)
    replacement = store.add_message({
        "ExternalId": "mail:replacement", "ConversationId": "thread:other", "Channel": "email",
        "SourceName": "inbox", "Subject": "Replacement detail", "FromName": "Dana",
        "SentAt": stamp(-180), "BodyText": "Replacement member", "Status": "filed",
    })
    store.place_message(old, None, "skipped")
    store.attach_message(replacement, tid)
    replaced, replaced_item = one(store)
    store.add_attachment({
        "MessageId": replacement, "ExternalId": "attachment:one", "Name": "close.xlsx",
        "ContentType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "Size": 42, "Inline": 0,
    })
    attached, attached_item = one(store)

    assert (initial["key"], initial["lane"], initial.get("more"), initial["preview"]) == (
        replaced_item["key"], replaced_item["lane"], replaced_item.get("more"), replaced_item["preview"])
    assert replaced["rev"] == before["rev"]
    assert replaced_item["presentation_revision"] != initial["presentation_revision"]
    assert attached_item["presentation_revision"] != replaced_item["presentation_revision"]
    assert attached["rev"] == replaced["rev"]


def test_fyi_batch_revision_binds_each_childs_full_backing():
    store = MemoryStore()
    prefix = "f" * 5000
    mids = [store.add_message({
        "ExternalId": f"fyi:{n}", "ConversationId": f"thread:fyi:{n}", "Channel": "email",
        "SourceName": "inbox", "Subject": f"FYI {n}", "FromName": "Dana",
        "SentAt": stamp(-60 - n), "BodyText": prefix + f" ending {n}", "Status": "filed",
    }) for n in range(2)]
    funnel.invalidate()
    members = funnel.build(store)["items"]
    key = "fyis:" + ",".join(item["key"] for item in members)
    first = funnel.batch_item(store, key)
    assert all(len(item["presentation_revision"]) == 64 for item in first["items"])

    store.update_message_body(mids[0], prefix + " changed ending")
    restamped = funnel.present(store, {"items": [first]})["items"][0]
    second = funnel.batch_item(store, key)
    repeated = funnel.present(store, {"items": [second]})["items"][0]
    assert second["key"] == first["key"]
    assert restamped["presentation_revision"] != first["presentation_revision"]
    assert [item["presentation_revision"] for item in restamped["items"]] != [
        item["presentation_revision"] for item in first["items"]]
    assert second["presentation_revision"] != first["presentation_revision"]
    assert [item["presentation_revision"] for item in second["items"]] != [
        item["presentation_revision"] for item in first["items"]]
    assert repeated["presentation_revision"] == second["presentation_revision"]
    assert [item["presentation_revision"] for item in repeated["items"]] == [
        item["presentation_revision"] for item in second["items"]]


def test_task_priority_status_and_native_question_content_are_revision_bound():
    store, tid, _mid, _rid = seeded()
    before, initial = one(store)
    store.update_task(tid, {"Priority": "high", "Status": "waiting"}, "test")
    changed, task_item = one(store)
    assert (task_item["key"], task_item["lane"]) == (initial["key"], initial["lane"])
    assert changed["rev"] == before["rev"]
    assert task_item["presentation_revision"] != initial["presentation_revision"]

    session = {"taskId": tid, "waiting": True, "phase": "parked", "agent": "codex",
               "started": stamp(-60), "tail": ["Which ledger should I use?"]}
    with mock.patch("taskuary.terminal.live_sessions", return_value=[session]):
        waiting_one, agent_one = one(store)
    with mock.patch("taskuary.terminal.live_sessions", return_value=[
        {**session, "tail": ["Which ledger and cutoff should I use?"]}
    ]):
        waiting_two, agent_two = one(store)
    assert (agent_one["key"], agent_one["lane"], agent_one["asking"]) == (
        agent_two["key"], agent_two["lane"], agent_two["asking"])
    assert waiting_one["rev"] == waiting_two["rev"]
    assert agent_one["presentation_revision"] != agent_two["presentation_revision"]
    assert waiting_one["display_revision"] != waiting_two["display_revision"]


def test_present_is_detached_read_only_and_card_keeps_revision():
    store, _tid, _mid, _rid = seeded()
    _picture, item = one(store)
    payload = {"rev": "legacy", "items": [item], "events": [{"kind": "asking"}], "alerts": []}
    writes = (store.cx.total_changes, store._writes)
    reads = 0
    original_read = store._processing_read

    @contextlib.contextmanager
    def counted_read():
        nonlocal reads
        reads += 1
        with original_read() as cur:
            yield cur

    with mock.patch.object(store, "_processing_read", counted_read):
        presented = funnel.present(store, payload)

    assert presented is not payload and presented["items"] is not payload["items"]
    assert reads == 1
    assert (store.cx.total_changes, store._writes) == writes
    assert concierge.card_for(presented["items"][0])["presentation_revision"] == item["presentation_revision"]
    assert presented["rev"] == "legacy"
    changed_events = funnel.present(store, {**payload, "events": [{"kind": "done"}]})
    assert changed_events["display_revision"] == presented["display_revision"]


def test_transport_revision_does_not_duplicate_durable_turn_but_semantic_change_does():
    store = MemoryStore()
    tid = store.create_task({"Title": "Assistant", "Kind": "general", "Status": "open"}, "test")
    child = {"key": "msg:1", "kind": "fyi", "lane": "fyi", "title": "One",
             "presentation_revision": "child-one"}
    card = {"key": "fyis:msg:1", "kind": "fyis", "lane": "fyi", "items": [child],
            "presentation_revision": "parent-one"}
    concierge.record(store, tid, "assistant", "Here is the update.", card)
    concierge.record(store, tid, "assistant", "Here is the update.", {
        **card, "presentation_revision": "parent-two",
        "items": [{**child, "presentation_revision": "child-two"}],
    })
    history = concierge.history(store, tid)
    assert len(history) == 1
    assert "presentation_revision" not in history[0]["card"]
    assert "presentation_revision" not in history[0]["card"]["items"][0]

    concierge.record(store, tid, "assistant", "Here is the update.", {
        **card, "title": "Changed meaning", "presentation_revision": "parent-three",
    })
    assert len(concierge.history(store, tid)) == 2
    concierge.record(store, tid, "user", "Tell me again.")
    concierge.record(store, tid, "assistant", "Here is the update.", {
        **card, "title": "Changed meaning", "presentation_revision": "parent-four",
    })
    assert [turn["role"] for turn in concierge.history(store, tid)] == [
        "assistant", "assistant", "user", "assistant"]
