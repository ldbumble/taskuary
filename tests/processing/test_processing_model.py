import copy
import json

import pytest

from taskuary.processing import (
    legacy_read_evidence,
    processing_context_revision,
    processing_view_revision,
)


NOW = "2026-09-06 12:00:00"


def context(**changes):
    value = {
        "members": [
            {
                "MemberId": "message:41",
                "MessageId": 41,
                "AccountScope": "gmail:account-a",
                "FromName": "Alex",
                "BodyText": "The complete source body",
                "Status": "feed",
                "Unread": 1,
            },
            {
                "MemberId": "message:42",
                "MessageId": 42,
                "AccountScope": "gmail:account-a",
                "FromName": "Alex",
                "BodyText": "A later reply",
            },
        ],
        "tasks": [
            {
                "TaskId": 9,
                "Title": "Prepare launch notes",
                "Description": "Cover rollback and support",
                "Checklist": [
                    {"text": "verify", "required_status": "approved"},
                    {"text": "publish"},
                ],
                "WorkerInstructions": "Use the signed release checklist",
                "Status": "open",
                "Priority": "urgent",
                "Working": "codex",
            }
        ],
        "attachments": [
            {
                "AttachmentId": 7,
                "MessageId": 41,
                "Filename": "plan.pdf",
                "MimeType": "application/pdf",
                "Size": 812,
                "ContentSha256": "abc",
                "Status": "ready",
            }
        ],
        "related_entities": [
            {"EntityId": "thread:account-a:thread-2", "Kind": "conversation"},
            {
                "EntityId": "idea:3",
                "IdeaId": 3,
                "Kind": "idea",
                "Text": "Stage the rollout",
                "ActionJson": {
                    "type": "create_task",
                    "parameters": {"worker_instructions": "Use a canary"},
                },
            },
        ],
    }
    value.update(changes)
    return value


def revision(value=None):
    return processing_context_revision(**(value or context()))


def row(**changes):
    value = {
        "MessageId": 41,
        "Channel": "email",
        "Brief": None,
        "LinkedIdeas": [],
        "ReviewId": None,
        "ReviewStatus": None,
        "TaskId": None,
        "TaskStatus": None,
        "Working": None,
        "AgentWaiting": False,
        "NeedsYou": 0,
        "AnsweredAt": None,
        "MsgStatus": "feed",
        "IngestedAt": "2026-09-06 11:30:00",
    }
    value.update(changes)
    return value


def evidence(value=None, states=None, **kwargs):
    return legacy_read_evidence(value or row(), states or {}, now=NOW, **kwargs)


def test_context_revision_is_deterministic_for_entity_order_and_dict_order():
    original = context()
    reordered = {
        "related_entities": list(reversed(original["related_entities"])),
        "attachments": [dict(reversed(list(item.items()))) for item in reversed(original["attachments"])],
        "tasks": [dict(reversed(list(item.items()))) for item in reversed(original["tasks"])],
        "members": [dict(reversed(list(item.items()))) for item in reversed(original["members"])],
    }
    assert revision(original) == revision(reordered)
    assert len(revision(original)) == 64


@pytest.mark.parametrize(
    ("section", "field", "replacement"),
    [
        ("members", "BodyText", "The body changed in place"),
        ("members", "MemberId", "message:41-replaced"),
        ("members", "TaskId", 18),
        ("attachments", "Filename", "corrected-plan.pdf"),
        ("attachments", "ContentSha256", "def"),
        ("tasks", "Description", "Cover a new material requirement"),
        ("tasks", "WorkerInstructions", "Use the emergency checklist"),
        ("related_entities", "EntityId", "thread:account-a:thread-3"),
    ],
)
def test_substantive_changes_update_context_without_requiring_new_ids(section, field, replacement):
    original = context()
    changed = copy.deepcopy(original)
    changed[section][0][field] = replacement
    assert revision(changed) != revision(original)


def test_account_scope_prevents_same_display_name_from_colliding():
    original = context()
    other_account = copy.deepcopy(original)
    other_account["members"][0]["AccountScope"] = "gmail:account-b"
    assert other_account["members"][0]["FromName"] == original["members"][0]["FromName"]
    assert revision(other_account) != revision(original)


def test_nested_substantive_payload_is_preserved_verbatim():
    original = context()
    changed = copy.deepcopy(original)
    changed["tasks"][0]["Checklist"][0]["required_status"] = "signed"
    assert revision(changed) != revision(original)

    changed = copy.deepcopy(original)
    changed["related_entities"][1]["ActionJson"]["parameters"]["worker_instructions"] = "Use two canaries"
    assert revision(changed) != revision(original)


def test_draft_status_read_priority_and_worker_state_are_view_only():
    original = context()
    changed = copy.deepcopy(original)
    changed["members"][0].update(Status="filed", Unread=0, DraftText="reply", DraftHtml="<p>reply</p>")
    changed["tasks"][0].update(
        Status="done",
        Priority="low",
        Working=None,
        AgentWaiting=True,
        WorkerStatus="waiting",
        ClosedAt="2026-09-06 12:01:00",
    )
    changed["members"][0].update(ReviewId=91, CreatedAt="2026-09-06 12:01:00", UpdatedBy="draft")
    changed["tasks"][0].update(UpdatedAt="2026-09-06 12:01:00", UpdatedBy="worker")
    changed["attachments"][0].update(UpdatedAt="2026-09-06 12:01:00")
    assert revision(changed) == revision(original)

    first_view = {
        "DraftText": "reply",
        "Status": "open",
        "Unread": 1,
        "Priority": "urgent",
        "Working": "codex",
    }
    base = revision(original)
    for key, replacement in {
        "DraftText": "edited reply",
        "Status": "done",
        "Unread": 0,
        "Priority": "low",
        "Working": "claude",
    }.items():
        changed_view = dict(first_view, **{key: replacement})
        assert processing_view_revision(base, changed_view) != processing_view_revision(base, first_view)


def test_view_revision_is_canonical_and_bound_to_context():
    view = {"Status": "open", "Unread": 1, "members": [41, 42]}
    reordered_keys = {"members": [41, 42], "Unread": 1, "Status": "open"}
    assert processing_view_revision("ctx-a", view) == processing_view_revision("ctx-a", reordered_keys)
    assert processing_view_revision("ctx-a", view) != processing_view_revision("ctx-b", view)


def test_legacy_evaluator_requires_explicit_idea_and_live_state_enrichment():
    missing_ideas = row()
    del missing_ideas["LinkedIdeas"]
    with pytest.raises(ValueError, match="LinkedIdeas"):
        evidence(missing_ideas)

    malformed_idea = row(Channel="assistant", LinkedIdeas=[{"IdeaId": 2}])
    with pytest.raises(ValueError, match="IdeaId and Status"):
        evidence(malformed_idea)


def test_selected_key_preserves_legacy_precedence():
    idea_row = row(
        Channel="assistant",
        Brief=json.dumps({"ideas": [{"id": 8}]}),
        LinkedIdeas=[{"IdeaId": 8, "Status": "open", "MessageId": 41}],
        ReviewId=3,
        ReviewStatus="pending",
        TaskId=9,
        Working="codex",
    )
    assert evidence(idea_row)["selected_key"] == "idea:8"
    assert evidence(row(ReviewId=3, ReviewStatus="pending", TaskId=9, Working="codex"))["selected_key"] == "review:3"
    assert evidence(row(TaskId=9, Working="codex"))["selected_key"] == "agent:9"
    assert evidence(row(Channel="report"))["selected_key"] == "report:41"
    assert evidence()["selected_key"] == "msg:41"


@pytest.mark.parametrize("status", ["surfaced", "done"])
def test_permanent_funnel_verdicts_preserve_historical_read(status):
    result = evidence(states={"msg:41": {"Key": "msg:41", "Status": status, "At": NOW}})
    assert result["observed_unread"] is False
    assert result["permanent_read"] is True
    assert f"legacy_{status}" in result["reasons"]
    assert result["raw_evidence"]["states"]["msg:41"]["At"] == NOW


@pytest.mark.parametrize("status", ["later", "skip"])
def test_active_deferral_suppresses_unread_without_becoming_permanent(status):
    state = {"Key": "msg:41", "Status": status, "Until": "2026-09-06 14:00:00", "By": "owner"}
    result = evidence(states={"msg:41": state})
    assert result["observed_unread"] is False
    assert result["permanent_read"] is False
    assert result["deferral"] == {
        "key": "msg:41",
        "status": status,
        "until": "2026-09-06 14:00:00",
        "active": True,
        "expired": False,
        "provenance": "legacy_funnel_state",
    }
    assert f"legacy_{status}_active" in result["reasons"]


@pytest.mark.parametrize("status", ["later", "skip"])
def test_expired_deferral_returns_unread_and_stays_nonpermanent(status):
    state = {"Key": "msg:41", "Status": status, "Until": "2026-09-06 10:00:00"}
    result = evidence(states={"msg:41": state})
    assert result["observed_unread"] is True
    assert result["permanent_read"] is False
    assert result["deferral"]["expired"] is True
    assert f"legacy_{status}_expired" in result["reasons"]


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"TaskStatus": "done"}, "legacy_closed_task"),
        ({"TaskStatus": "dropped"}, "legacy_closed_task"),
        ({"ReviewId": 5, "ReviewStatus": "approved"}, "legacy_resolved_review"),
        ({"ReviewId": 5, "ReviewStatus": ""}, "legacy_resolved_review"),
        ({"AnsweredAt": "2026-09-06 11:00:00"}, "legacy_answered_at"),
        ({"MsgStatus": "ignored"}, "legacy_ignored"),
        ({"MsgStatus": "withdrawn"}, "legacy_withdrawn"),
        ({"IngestedAt": "2026-09-05 11:59:59"}, "legacy_age_inference"),
    ],
)
def test_independent_legacy_handling_causes_are_retained(changes, reason):
    result = evidence(row(**changes))
    assert result["observed_unread"] is False
    assert result["permanent_read"] is True
    assert reason in result["reasons"]


def test_pending_review_with_answered_at_retains_both_facts():
    result = evidence(row(ReviewId=5, ReviewStatus="pending", AnsweredAt="2026-09-06 11:00:00"))
    assert result["selected_key"] == "review:5"
    assert result["observed_unread"] is False
    assert result["permanent_read"] is True
    assert "legacy_answered_at" in result["reasons"]
    assert result["raw_evidence"]["active_work"] is True


def test_active_work_prevents_age_inference():
    result = evidence(row(IngestedAt="2026-09-05 11:00:00", NeedsYou=1))
    assert result["observed_unread"] is True
    assert result["permanent_read"] is False
    assert "legacy_age_inference" not in result["reasons"]


def test_working_override_preserves_permanent_reasons_but_observed_row_is_unread():
    active = row(TaskId=9, Working="codex", MsgStatus="ignored")
    state = {"agent:9": {"Key": "agent:9", "Status": "done", "At": NOW}}
    result = evidence(active, states=state)
    assert result["selected_key"] == "agent:9"
    assert result["observed_unread"] is True
    assert result["permanent_read"] is True
    assert {"legacy_done", "legacy_ignored", "legacy_working_override"} <= set(result["reasons"])


def test_waiting_agent_does_not_apply_working_override():
    waiting = row(TaskId=9, Working="codex", AgentWaiting=True)
    result = evidence(waiting, states={"agent:9": {"Status": "surfaced"}})
    assert result["observed_unread"] is False
    assert "legacy_working_override" not in result["reasons"]


def test_superseded_assistant_wrapper_is_permanent_legacy_inference():
    wrapper = row(
        Channel="assistant",
        Brief=json.dumps({"ideas": [{"id": 8}]}),
        LinkedIdeas=[],
    )
    result = evidence(wrapper)
    assert result["selected_key"] == "msg:41"
    assert result["observed_unread"] is False
    assert result["permanent_read"] is True
    assert result["raw_evidence"]["provenance"] == "legacy_feed_handling_inference"
    assert "legacy_assistant_handled" in result["reasons"]
    assert "legacy_assistant_supersession" in result["reasons"]


@pytest.mark.parametrize("status", ["later", "skip"])
@pytest.mark.parametrize(
    ("until", "expired"),
    [("2026-09-06 14:00:00", False), ("2026-09-06 10:00:00", True)],
)
def test_assistant_idea_deferral_preserves_the_old_handled_discrepancy(status, until, expired):
    wrapper = row(
        Channel="assistant",
        Brief=json.dumps({"ideas": [{"id": 8}]}),
        LinkedIdeas=[{"IdeaId": 8, "Status": "open", "MessageId": 41}],
    )
    idea_state = {"Key": "idea:8", "Status": status, "Until": until, "By": "owner"}
    result = evidence(wrapper, states={"idea:8": idea_state})
    # feed() excludes later/skip ideas from unread_ideas even after Until, then
    # calls the wrapper handled. Capture that result without turning it permanent.
    assert result["selected_key"] == "msg:41"
    assert result["observed_unread"] is False
    assert result["permanent_read"] is False
    assert result["deferral"]["expired"] is expired
    assert result["raw_evidence"]["states"]["idea:8"] == idea_state
    assert result["raw_evidence"]["assistant_open_idea_deferral_discrepancy"] is True
    assert "legacy_assistant_supersession" not in result["reasons"]
    suffix = "expired" if expired else "active"
    assert f"legacy_idea_{status}_{suffix}" in result["reasons"]


def test_mixed_surfaced_and_deferred_assistant_ideas_are_not_collapsed_to_permanent_read():
    wrapper = row(
        Channel="assistant",
        Brief=json.dumps({"ideas": [{"id": 8}, {"id": 9}]}),
        LinkedIdeas=[
            {"IdeaId": 9, "Status": "open", "MessageId": 41},
            {"IdeaId": 8, "Status": "open", "MessageId": 41},
        ],
    )
    states = {
        "idea:8": {"Key": "idea:8", "Status": "surfaced", "At": NOW},
        "idea:9": {"Key": "idea:9", "Status": "later", "Until": "2026-09-06 14:00:00"},
    }
    result = evidence(wrapper, states=states)
    assert result["observed_unread"] is False
    assert result["permanent_read"] is False
    assert result["raw_evidence"]["states"] == states
    assert {"legacy_idea_surfaced", "legacy_idea_later_active"} <= set(result["reasons"])


def test_inventory_exclusion_is_recorded_but_never_treated_as_read():
    result = evidence(row(InventoryExclusions=["page_cap", "source_filter"]))
    assert result["observed_unread"] is True
    assert result["permanent_read"] is False
    assert result["reasons"] == []
    assert result["raw_evidence"]["inventory_exclusions"] == ["page_cap", "source_filter"]


def test_invalid_brief_matches_legacy_no_ids_and_records_the_anomaly():
    result = evidence(row(Channel="assistant", Brief="{not-json", LinkedIdeas=[]))
    assert result["observed_unread"] is True
    assert result["raw_evidence"]["brief_parse_error"] == "JSONDecodeError"
