"""PW-101 projection gates over the actual additive store seam."""

import json

from taskuary.store import SQLiteStore


NOW = "2026-09-06 12:00:00"
BODY_PREFIX = "same-visible-prefix:" + ("x" * 4100)


def seed_projection(path):
    store = SQLiteStore(str(path))
    task_id = store.create_task(
        {
            "Title": "Prepare the synthetic launch",
            "Summary": "Use the complete source record",
            "Kind": "general",
            "Status": "open",
            "Priority": "normal",
            "Source": "email",
            "SourceRef": "fixture:projection",
            "Tags": "launch,fixture",
        },
        "fixture",
    )
    message_id = store.add_message(
        {
            "TaskId": task_id,
            "ExternalId": "fixture:projection:message",
            "ConversationId": "mail:fixture-projection",
            "Channel": "email",
            "SourceName": "fixture-account@example.test",
            "Subject": "Synthetic launch details",
            "FromName": "Avery Example",
            "FromEmail": "avery@example.test",
            "SentAt": NOW,
            "BodyText": BODY_PREFIX + ":original-tail",
            "SourceLink": "https://example.test/messages/projection",
            "Status": "routed",
            "Direction": "in",
            "RecipientsJson": '["owner@example.test"]',
            "MailMetaJson": '{"folder":"fixture"}',
        }
    )
    attachment_id = store.add_attachment(
        {
            "MessageId": message_id,
            "ExternalId": "fixture:projection:attachment",
            "Name": "launch-plan.txt",
            "ContentType": "text/plain",
            "Size": 128,
            "ContentId": "fixture-content-id",
            "Inline": 0,
            "Path": "attachments/fixture-launch-plan.txt",
        }
    )
    review_id = store.add_review(
        {
            "TaskId": task_id,
            "MessageId": message_id,
            "Kind": "draft_reply",
            "DraftText": "Initial synthetic draft",
            "Status": "pending",
            "Reason": "fixture projection",
        }
    )
    store.add_route(
        message_id,
        task_id,
        "task",
        0.9,
        "Initial synthetic route",
        [],
        "fixture",
    )
    idea = store.upsert_idea(
        {
            "key": "fixture-projection-idea",
            "kind": "followup",
            "text": "Retained synthetic idea body",
            "sig": "fixture-idea-v1",
            "action": {"type": "create_task", "title": "Stage the fixture launch"},
        },
        NOW,
    )
    store.set_ideas_message([idea["IdeaId"]], message_id)
    store.set_brief(message_id, json.dumps({"ideas": [{"id": idea["IdeaId"]}]}))
    store.set_setting("owner_email", "owner@example.test", "fixture")
    result = store.backfill_processing("projection-v1", fixed_now=NOW)
    assert result["status"] == "complete"
    target = store.resolve_processing_target(
        "legacy_funnel", f"msg:{message_id}"
    )
    assert target is not None
    return (
        store,
        target["item_id"],
        task_id,
        message_id,
        attachment_id,
        review_id,
        idea["IdeaId"],
    )


def test_projection_tracks_full_content_and_keeps_display_state_view_only(tmp_path):
    (
        store,
        item_id,
        task_id,
        message_id,
        attachment_id,
        review_id,
        _idea_id,
    ) = seed_projection(tmp_path / "projection.db")
    try:
        initial = store.processing_snapshot(item_id)
        assert initial["item_id"] == item_id
        original_body = next(
            member["BodyText"]
            for member in initial["context"]["members"]
            if member.get("MessageId") == message_id
        )
        assert len(original_body) > 4000
        assert original_body.endswith(":original-tail")

        # The visible feed preview is unchanged: only source content beyond its
        # historical 4,000-character boundary changes.
        store.update_message_body(message_id, BODY_PREFIX + ":changed-tail")
        body_changed = store.processing_snapshot(item_id)
        assert body_changed["context_revision"] != initial["context_revision"]
        assert body_changed["view_revision"] != initial["view_revision"]
        changed_body = next(
            member["BodyText"]
            for member in body_changed["context"]["members"]
            if member.get("MessageId") == message_id
        )
        assert changed_body.endswith(":changed-tail")
        assert changed_body[:4000] == original_body[:4000]

        store._exec(
            "UPDATE attachment SET Name=?,Size=? WHERE AttachmentId=?",
            ("launch-plan-v2.txt", 256, attachment_id),
        )
        attachment_changed = store.processing_snapshot(item_id)
        assert attachment_changed["context_revision"] != body_changed["context_revision"]
        assert attachment_changed["view_revision"] != body_changed["view_revision"]

        stable_context = attachment_changed["context_revision"]
        previous_view = attachment_changed["view_revision"]

        # Status writes change several real task columns at once. None represents
        # new substantive model input; all remain visible in the view payload.
        store._exec(
            """UPDATE task SET Status=?,Priority=?,UpdatedAt=?,UpdatedBy=?
               WHERE TaskId=?""",
            ("in_progress", "urgent", "2026-09-06 12:01:00", "fixture", task_id),
        )
        task_view = store.processing_snapshot(item_id)
        assert task_view["context_revision"] == stable_context
        assert task_view["view_revision"] != previous_view
        previous_view = task_view["view_revision"]

        store.save_review_draft(review_id, "Edited synthetic draft")
        draft_view = store.processing_snapshot(item_id)
        assert draft_view["context_revision"] == stable_context
        assert draft_view["view_revision"] != previous_view
        previous_view = draft_view["view_revision"]

        store.set_funnel_state(f"msg:{message_id}", "surfaced", "fixture-owner")
        read_view = store.processing_snapshot(item_id)
        assert read_view["context_revision"] == stable_context
        assert read_view["view_revision"] != previous_view
        previous_view = read_view["view_revision"]

        store._exec(
            """UPDATE route SET Decision=?,Reason=?,RawOutput=?,ParseError=?
               WHERE MessageId=?""",
            (
                "error",
                "Updated synthetic triage failure",
                "not-json",
                "fixture parse error",
                message_id,
            ),
        )
        route_view = store.processing_snapshot(item_id)
        assert route_view["context_revision"] == stable_context
        assert route_view["view_revision"] != previous_view
        assert route_view["view"]["routes"][0]["ParseError"] == "fixture parse error"
        previous_view = route_view["view_revision"]

        store.set_setting("owner_email", "new-owner@example.test", "fixture")
        settings_view = store.processing_snapshot(item_id)
        assert settings_view["context_revision"] == stable_context
        assert settings_view["view_revision"] != previous_view
        assert settings_view["view"]["settings"]["owner_email"] == "new-owner@example.test"
        previous_view = settings_view["view_revision"]

        working = store.processing_snapshot(
            item_id,
            live_state=[
                {
                    "taskId": task_id,
                    "sid": "fixture-session",
                    "agent": "fixture-agent",
                    "waiting": False,
                }
            ],
        )
        assert working["context_revision"] == stable_context
        assert working["view_revision"] != previous_view
        assert working["view"]["worker_attention"][0]["sid"] == "fixture-session"
    finally:
        store.cx.close()


def foundation_rows(store):
    tables = (
        "task",
        "message",
        "attachment",
        "review",
        "route",
        "run",
        "idea",
        "funnel_state",
        "setting",
        "processing_item",
        "processing_member",
        "processing_alias",
        "processing_relation",
        "processing_legacy_evidence",
        "processing_migration",
    )
    return {
        table: [tuple(row) for row in store.cx.execute(f"SELECT * FROM {table}").fetchall()]
        for table in tables
    }


def test_projection_is_deterministic_across_identity_order_and_reopen_and_read_only(tmp_path):
    path = tmp_path / "projection-reopen.db"
    (
        store,
        item_id,
        task_id,
        message_id,
        _attachment_id,
        _review_id,
        _idea_id,
    ) = seed_projection(path)
    live_state = [
        {"taskId": task_id, "sid": "second", "agent": "fixture-b", "waiting": True},
        {"taskId": task_id, "sid": "first", "agent": "fixture-a", "waiting": False},
        {"taskId": task_id + 999, "sid": "unrelated", "agent": "fixture-x"},
    ]
    try:
        first = store.processing_snapshot(item_id, live_state=live_state)

        # Reconciliation accepts unordered entity input. Re-supplying the exact
        # identities in reverse must not perturb either canonical revision.
        members = list(reversed(store.processing_members(item_id)))
        store.reconcile_processing_entities(
            kind=first["item"]["Kind"],
            item_id=item_id,
            members=[
                {
                    "entity_kind": member["EntityKind"],
                    "local_id": member["LocalId"],
                    "role": member["Role"],
                }
                for member in members
            ],
            fixed_now=NOW,
        )
        reordered = store.processing_snapshot(item_id, live_state=list(reversed(live_state)))
        assert reordered["member_ids"] == first["member_ids"]
        assert reordered["related_entity_ids"] == first["related_entity_ids"]
        assert reordered["context_revision"] == first["context_revision"]
        assert reordered["view_revision"] == first["view_revision"]

        before_rows = foundation_rows(store)
        before_changes = store.cx.total_changes
        before_writes = store._writes
        resolved = store.resolve_processing_target(
            "legacy_funnel", f"msg:{message_id}"
        )
        read_one = store.processing_snapshot(item_id, live_state=live_state)
        read_two = store.processing_snapshot(item_id, live_state=live_state)
        assert resolved["item_id"] == item_id
        assert read_one == read_two
        assert store.cx.total_changes == before_changes
        assert store._writes == before_writes
        assert foundation_rows(store) == before_rows
        expected = (read_one["context_revision"], read_one["view_revision"])
    finally:
        store.cx.close()

    reopened = SQLiteStore(str(path))
    try:
        after = reopened.processing_snapshot(item_id, live_state=live_state)
        assert (after["context_revision"], after["view_revision"]) == expected
    finally:
        reopened.cx.close()


def test_message_task_binding_is_context_even_before_membership_reconciliation(tmp_path):
    (
        store,
        item_id,
        _task_id,
        message_id,
        _attachment_id,
        _review_id,
        _idea_id,
    ) = seed_projection(tmp_path / "projection-binding.db")
    try:
        before = store.processing_snapshot(item_id)
        replacement_task = store.create_task(
            {"Title": "Replacement synthetic task", "Kind": "general"}, "fixture"
        )
        store._exec(
            "UPDATE message SET TaskId=? WHERE MessageId=?",
            (replacement_task, message_id),
        )
        rebound = store.processing_snapshot(item_id)
        assert rebound["context_revision"] != before["context_revision"]
        message_context = next(
            member
            for member in rebound["context"]["members"]
            if member.get("MessageId") == message_id
        )
        assert message_context["TaskId"] == replacement_task
    finally:
        store.cx.close()


def test_retired_relation_excludes_related_idea_content(tmp_path):
    (
        store,
        item_id,
        _task_id,
        message_id,
        _attachment_id,
        _review_id,
        idea_id,
    ) = seed_projection(tmp_path / "projection-retired-relation.db")
    try:
        before = store.processing_snapshot(item_id)
        assert any(
            related.get("Text") == "Retained synthetic idea body"
            for related in before["context"]["related_entities"]
        )
        assert f"idea:{idea_id}" in before["related_entity_ids"]

        store._exec(
            """UPDATE processing_relation SET RetiredAt=?
               WHERE FromEntityKind='message' AND FromLocalId=?
                 AND ToEntityKind='idea' AND ToLocalId=?""",
            (NOW, str(message_id), str(idea_id)),
        )
        retired = store.processing_snapshot(item_id)
        assert retired["context_revision"] != before["context_revision"]
        assert not any(
            related.get("Text") == "Retained synthetic idea body"
            for related in retired["context"]["related_entities"]
        )
        assert f"idea:{idea_id}" not in retired["related_entity_ids"]
    finally:
        store.cx.close()
