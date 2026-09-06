"""Pure processing snapshot and legacy-read helpers.

This module deliberately has no store, funnel, or I/O dependency.  Phase 1 can use
the functions while building an additive processing model without changing the
existing feed consumers or read behavior.
"""

from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime, timedelta
from typing import Any


_CONTEXT_SCHEMA = "taskuary.processing.context.v1"
_VIEW_SCHEMA = "taskuary.processing.view.v1"


def _json_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(f"processing revisions require JSON values, got {type(value).__name__}")


def _field_token(name: object) -> str:
    return "".join(ch for ch in str(name).lower() if ch.isalnum())


# Context selection is intentionally allowlisted by entity kind. Store rows carry
# mutation metadata (UpdatedAt/UpdatedBy), latest-review IDs, drafts, status, read,
# priority, and worker projections. A denylist would eventually miss one of those
# aliases and make a view-only write look like new model input.
_MEMBER_CONTEXT_FIELDS = {
    "accountid", "accountscope", "actionjson", "attachments", "attachmentids",
    "body", "bodytext", "channel", "cleanbody", "connectorid", "content",
    "conversationid", "direction", "entityid", "entitykind", "externalid",
    "fromemail", "fromname", "fullbody", "ideaid", "kind", "localid",
    "mailmetajson", "memberid", "messageid", "messageids", "metadata", "namespace",
    "payload",
    "provider", "providerid", "recipientsjson", "role", "sentat", "sig",
    "sourcename", "sourcescope", "sourcelink", "subject", "taskid", "text", "threadid",
}
_TASK_CONTEXT_FIELDS = {
    "checklist", "description", "details", "entityid", "entitykind", "instruction",
    "instructions", "kind",
    "localid", "source", "sourceref", "summary", "tags", "taskid", "title",
    "workerinstructions",
}
_ATTACHMENT_CONTEXT_FIELDS = {
    "attachmentid", "characters", "content", "contenthash", "contentid",
    "contentsha256", "contenttype", "entityid", "entitykind", "externalid",
    "extractedtext", "filename", "inline", "localid", "messageid", "mimetype",
    "metadata", "name", "path", "payload", "sha256", "size", "text",
}
_RELATED_CONTEXT_FIELDS = {
    "accountscope", "actionjson", "entityid", "entitykind", "ideaid", "kind",
    "localid", "memberid", "messageid", "relation", "relatedentityid", "sig",
    "sourcescope", "taskid", "text",
}


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _unordered_entities(values: list[dict], field: str, allowed: set[str]) -> list[dict]:
    if not isinstance(values, list):
        raise TypeError(f"{field} must be a list")
    cleaned = []
    for value in values:
        if not isinstance(value, dict):
            raise TypeError(f"{field} entries must be dictionaries")
        selected = {
            str(key): _json_value(item)
            for key, item in value.items()
            if _field_token(key) in allowed
        }
        if not selected and value:
            raise ValueError(f"{field} entry has no recognized substantive fields")
        cleaned.append(selected)
    return sorted(cleaned, key=_canonical_json)


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def processing_context_revision(
    *,
    members: list[dict],
    tasks: list[dict],
    attachments: list[dict],
    related_entities: list[dict] = (),
) -> str:
    """Hash the substantive processing context using deterministic canonical JSON.

    The four top-level entity collections are sets for revision purposes, so their
    input order does not affect the digest. Full bodies, durable member/account IDs,
    attachment metadata, and material task fields remain significant. Mutable view
    state such as drafts, status, read/defer state, priority, and worker attention is
    excluded here and belongs in :func:`processing_view_revision`.
    """

    payload = {
        "schema": _CONTEXT_SCHEMA,
        "members": _unordered_entities(members, "members", _MEMBER_CONTEXT_FIELDS),
        "tasks": _unordered_entities(tasks, "tasks", _TASK_CONTEXT_FIELDS),
        "attachments": _unordered_entities(
            attachments, "attachments", _ATTACHMENT_CONTEXT_FIELDS
        ),
        "related_entities": _unordered_entities(
            list(related_entities), "related_entities", _RELATED_CONTEXT_FIELDS
        ),
    }
    return _digest(payload)


def processing_view_revision(context_revision: str, view: dict) -> str:
    """Hash one displayed projection and the exact context revision behind it."""

    if not isinstance(context_revision, str) or not context_revision:
        raise ValueError("context_revision must be a non-empty string")
    if not isinstance(view, dict):
        raise TypeError("view must be a dictionary")
    return _digest({"schema": _VIEW_SCHEMA, "context_revision": context_revision, "view": view})


_LEGACY_REQUIRED_ROW_KEYS = {
    "MessageId",
    "Channel",
    "Brief",
    "LinkedIdeas",
    "ReviewId",
    "ReviewStatus",
    "TaskId",
    "TaskStatus",
    "Working",
    "AgentWaiting",
    "NeedsYou",
    "AnsweredAt",
    "MsgStatus",
    "IngestedAt",
}


def _append_once(reasons: list[str], reason: str) -> None:
    if reason not in reasons:
        reasons.append(reason)


def _brief_idea_ids(brief: object) -> tuple[list[Any], str | None]:
    if not brief:
        return [], None
    try:
        parsed = json.loads(brief)
        ideas = parsed.get("ideas") or []
        return [idea.get("id") for idea in ideas if idea.get("id")], None
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        # The current feed ignores malformed Brief JSON. Retain the anomaly so a
        # migration can audit it without changing that observed result.
        return [], type(exc).__name__


def _legacy_defer(key: str, state: dict, now: str) -> dict | None:
    status = state.get("Status")
    if status not in ("later", "skip"):
        return None
    until = state.get("Until")
    # This intentionally preserves feed()'s raw SQLite timestamp predicate. Do
    # not parse or normalize malformed historical values during evidence capture.
    active = not until or until > now
    return {
        "key": key,
        "status": status,
        "until": until,
        "active": bool(active),
        "expired": not active,
        "provenance": "legacy_funnel_state",
    }


def legacy_read_evidence(
    row: dict,
    states: dict,
    *,
    now: str,
    funnel_hours: int = 12,
) -> dict:
    """Evaluate and explain the exact historical ``Store.feed`` handled result.

    ``row`` must be an uncapped feed projection enriched with ``LinkedIdeas`` and
    explicit ``Working``/``AgentWaiting`` values. ``states`` is the verbatim
    ``funnel_state`` mapping keyed by its legacy Key. The result is evidence for a
    later migration; calling this function does not activate new read semantics.
    """

    if not isinstance(row, dict):
        raise TypeError("row must be a dictionary")
    if not isinstance(states, dict):
        raise TypeError("states must be a dictionary")
    missing = sorted(_LEGACY_REQUIRED_ROW_KEYS.difference(row))
    if missing:
        raise ValueError("legacy row is missing explicit enrichment: " + ", ".join(missing))
    if not isinstance(row["LinkedIdeas"], list):
        raise TypeError("LinkedIdeas must be a list")
    if not isinstance(now, str) or not now:
        raise ValueError("now must be a non-empty legacy timestamp string")
    try:
        hours = max(1, int(funnel_hours or 12))
        now_dt = datetime.fromisoformat(now)
    except (TypeError, ValueError) as exc:
        raise ValueError("now and funnel_hours must form a valid fixed legacy clock") from exc
    cutoff = (now_dt - timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S")

    channel = row.get("Channel")
    linked_ideas = row["LinkedIdeas"] if channel == "assistant" else []
    for idea in linked_ideas:
        if not isinstance(idea, dict) or "IdeaId" not in idea or "Status" not in idea:
            raise ValueError("each LinkedIdeas entry requires IdeaId and Status")

    brief_ids, brief_error = _brief_idea_ids(row.get("Brief") if channel == "assistant" else None)
    open_ideas = [idea for idea in linked_ideas if idea.get("Status") == "open"]
    unread_ideas = [
        idea
        for idea in open_ideas
        if (states.get(f"idea:{idea['IdeaId']}") or {}).get("Status")
        not in ("surfaced", "done", "later", "skip")
    ]

    if unread_ideas:
        selected_key = f"idea:{unread_ideas[0]['IdeaId']}"
    elif row.get("ReviewStatus") == "pending" and row.get("ReviewId"):
        selected_key = f"review:{row['ReviewId']}"
    elif row.get("Working") and row.get("TaskId"):
        selected_key = f"agent:{row['TaskId']}"
    elif channel == "report":
        selected_key = f"report:{row['MessageId']}"
    else:
        selected_key = f"msg:{row['MessageId']}"

    selected_state = states.get(selected_key) or {}
    if not isinstance(selected_state, dict):
        raise TypeError(f"legacy state for {selected_key} must be a dictionary")
    verdict = selected_state.get("Status")
    selected_deferral = _legacy_defer(selected_key, selected_state, now)
    deferred = bool(selected_deferral and selected_deferral["active"])

    active_work = bool(
        row.get("AgentWaiting")
        or row.get("Working")
        or row.get("ReviewStatus") == "pending"
        or row.get("NeedsYou")
    )
    ingested_at = row.get("IngestedAt")
    aged = bool(ingested_at and ingested_at < cutoff and not active_work)
    assistant_handled = bool(brief_ids and not unread_ideas)
    closed_task = row.get("TaskStatus") in ("done", "dropped")
    resolved_review = bool(
        row.get("ReviewId") and row.get("ReviewStatus") not in (None, "pending")
    )
    answered = bool(row.get("AnsweredAt"))
    ignored = row.get("MsgStatus") in ("withdrawn", "ignored")

    reasons: list[str] = []
    if assistant_handled:
        _append_once(reasons, "legacy_assistant_handled")
        if not linked_ideas:
            _append_once(reasons, "legacy_assistant_supersession")
    if verdict == "surfaced":
        _append_once(reasons, "legacy_surfaced")
    if verdict == "done":
        _append_once(reasons, "legacy_done")
    if closed_task:
        _append_once(reasons, "legacy_closed_task")
    if resolved_review:
        _append_once(reasons, "legacy_resolved_review")
    if answered:
        _append_once(reasons, "legacy_answered_at")
    if row.get("MsgStatus") == "withdrawn":
        _append_once(reasons, "legacy_withdrawn")
    if row.get("MsgStatus") == "ignored":
        _append_once(reasons, "legacy_ignored")
    if aged:
        _append_once(reasons, "legacy_age_inference")

    candidate_keys = [selected_key, f"msg:{row['MessageId']}"]
    if channel == "report":
        candidate_keys.append(f"report:{row['MessageId']}")
    if row.get("ReviewId"):
        candidate_keys.append(f"review:{row['ReviewId']}")
    if row.get("TaskId"):
        candidate_keys.append(f"agent:{row['TaskId']}")
    candidate_keys.extend(f"idea:{idea['IdeaId']}" for idea in linked_ideas)
    candidate_keys = list(dict.fromkeys(candidate_keys))

    deferrals = []
    relevant_states = {}
    open_idea_keys = {f"idea:{idea['IdeaId']}" for idea in open_ideas}
    for key in candidate_keys:
        if key not in states:
            continue
        state = states[key]
        if not isinstance(state, dict):
            raise TypeError(f"legacy state for {key} must be a dictionary")
        relevant_states[key] = copy.deepcopy(state)
        if key.startswith("idea:") and state.get("Status") in ("surfaced", "done"):
            _append_once(reasons, f"legacy_idea_{state['Status']}")
        evidence = _legacy_defer(key, state, now)
        if evidence:
            deferrals.append(evidence)
            suffix = "active" if evidence["active"] else "expired"
            prefix = "legacy_idea" if key.startswith("idea:") else "legacy"
            _append_once(reasons, f"{prefix}_{evidence['status']}_{suffix}")

    # Prefer the selected alias's deferral; an assistant wrapper may instead be
    # suppressed only because an open idea member is later/skip. That discrepancy
    # is part of the legacy result and must remain visible after expiry too.
    deferral = next((item for item in deferrals if item["key"] == selected_key), None)
    if deferral is None:
        deferral = next(
            (item for item in deferrals if item["key"] in open_idea_keys),
            None,
        )

    handled_before_override = bool(
        assistant_handled
        or verdict in ("surfaced", "done")
        or deferred
        or closed_task
        or resolved_review
        or answered
        or ignored
        or aged
    )
    working_override = bool(
        row.get("Working") and not row.get("AgentWaiting") and not closed_task
    )
    if working_override:
        _append_once(reasons, "legacy_working_override")
    observed_unread = bool(working_override or not handled_before_override)

    open_idea_deferral = any(
        (states.get(f"idea:{idea['IdeaId']}") or {}).get("Status") in ("later", "skip")
        for idea in open_ideas
    )
    permanent_read = bool(
        verdict in ("surfaced", "done")
        or closed_task
        or resolved_review
        or answered
        or ignored
        or aged
        or (assistant_handled and not open_idea_deferral)
    )

    raw_evidence = {
        "provenance": "legacy_feed_handling_inference",
        "selected_state": copy.deepcopy(selected_state),
        "states": relevant_states,
        "brief_idea_ids": copy.deepcopy(brief_ids),
        "brief_parse_error": brief_error,
        "linked_idea_ids": [idea["IdeaId"] for idea in linked_ideas],
        "open_idea_ids": [idea["IdeaId"] for idea in open_ideas],
        "unread_idea_ids": [idea["IdeaId"] for idea in unread_ideas],
        "deferrals": copy.deepcopy(deferrals),
        "active_work": active_work,
        "aged": aged,
        "unread_cutoff": cutoff,
        "working_override": working_override,
        "handled_before_working_override": handled_before_override,
        "assistant_open_idea_deferral_discrepancy": bool(
            assistant_handled and open_idea_deferral
        ),
        "inventory_exclusions": copy.deepcopy(row.get("InventoryExclusions") or []),
    }
    # Fail here rather than leave a migration with evidence it cannot persist.
    _canonical_json(raw_evidence)

    return {
        "selected_key": selected_key,
        "observed_unread": observed_unread,
        "permanent_read": permanent_read,
        "reasons": reasons,
        "deferral": copy.deepcopy(deferral),
        "raw_evidence": raw_evidence,
    }
