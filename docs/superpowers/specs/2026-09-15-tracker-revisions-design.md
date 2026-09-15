# Tracker revisions: an edit or a comment is a new arrival

**Date:** 2026-09-15
**Status:** design approved, unimplemented
**Owner decisions:** recorded inline as `DECIDED`

## The problem

A tracker item is read once and then frozen for good.

`ingest_message` drops a message whose `ExternalId` it has already stored — the
first line of the funnel, before policy, before triage, before any AI call
(`ingest.py:484`). That line is correct. What is wrong is the id the tracker
connectors hand it: `gh:{repo}#{number}`, `jira:{KEY}`, `asana:{gid}` and nine
more name the *item*, and an item's name does not change when the item does.

So the poll sees the edit — GitHub's `list_items` asks for `sort=updated&since=`
and Jira's JQL asks for `updated >= -Nm`, and both duly return the changed item —
and then the funnel throws it away as a duplicate. The row on the Timeline, the
task Title and Summary written at `ingest.py:726`, and the brief the coder reads
from `agents.task_context` are all the text as it was the first time anybody saw
it. An issue rewritten from "login is slow" to "login drops the session, here is
the repro" reaches nobody.

Comments are worse: they are never fetched at all. `github.pr_review_comments`
exists but only the CI watcher calls it, for Taskuary's own pull requests
(`ci.py:244`). A person answering a question on a Jira ticket is invisible.

This is not a GitHub bug. Sweeping every `external_id` in the tree splits the
connectors cleanly in two:

| Version-stamped — revisions already flow | Write-once — frozen at first read |
| --- | --- |
| `notion:{id}:{last_edited[:16]}`, `sentry:{id}:{at[:16]}`, `aws:…:{stamp[:16]}`, `azblob:…:{stamp[:16]}`, `report:{src}:{stamp}` | `gh:{repo}#{n}`, `jira:{KEY}`, `asana`, `monday`, `clickup`, `todoist`, `gitlab`, `azdo`, `linear`, `trello`, `pagerduty` |

Notion and Sentry already do the right thing by suffixing a stamp. Eleven
channels do not.

**DECIDED: Notion and Sentry are left exactly as they are.** They already have
revision behaviour, and converting them to the content hash would cost a one-time
re-triage of every stored page and issue — their existing keys are
`notion:{id}:{stamp}`, so `seen_before`'s fallback (which looks for a bare `base`
row) would find nothing and treat all of them as new. That is precisely the
upgrade-day flood this design is built to avoid. Uniformity is not worth it; the
two shapes coexist, and this paragraph is why.

## What this is not

Not a new connector. The Jira connector already exists and works —
`pm.poll_jira`, JQL `assignee = currentUser()`, alongside Asana, Monday,
ClickUp and Todoist. It simply has the same freeze.

## The shape

Everything downstream already exists. A second message carrying the **same
`conversation_id`** reaches `identity_route` (`ingest.py:994`), which attaches it
to the open task, re-judges it with `judge`, and marks an in-flight draft stale so
the responder rewrites it against the newer text (`ingest.py:587-593`). PW-017 is
already settled: a **closed** task does not reopen — the arrival is judged as new
work.

So the feature is not new machinery. It is letting tracker items reach the
machinery that has been running for mail since the funnel was written. The whole
of §1 is "compute a better `ExternalId`", and `ingest_message` needs no edit at
all.

## §1 — Revision identity

**DECIDED: key the revision on a hash of what triage actually reads** — title plus
rendered body, which already carries the head line each connector writes
(`[Jira KEY - status X · priority Y]`, `[issue by who - association: Y]`). A
status or priority flip therefore *is* a revision. Labels, rank, sprint moves,
assignee churn and worklogs are not, because they never reach the rendered text.

Rejected: keying on the vendor's `updated` stamp (the Notion/Sentry shape). One
line per connector, but Jira bumps `updated` for every field poke, so a label
change would spend an LLM call and put a row on the Timeline.

A shared helper in `channels.py`, used by the eleven write-once tracker connectors:

```python
def rev_id(base, subject, body):
    """A tracker id that changes when the item's WORDS change. `base` names the item
    (gh:owner/repo#42); the suffix is what it said. See docs/.../tracker-revisions."""
    h = hashlib.sha1(f'{subject}\n{body}'.encode()).hexdigest()[:12]
    return f'{base}@{h}'


def seen_before(store, base, subject, body) -> bool:
    """Has this exact version already landed? Content-addressed, so a re-sync cannot
    spam the Timeline and an edit-then-undo says nothing (there is nothing new to say)."""
    h = rev_id(base, subject, body)
    if store.message_exists(h): return True
    row = store.message_by_external(base)          # keyed the old way, before this shipped
    return bool(row) and rev_id(base, row.get('Subject') or '', row.get('BodyText') or '') == h
```

**DECIDED: the first poll after this ships must be silent.** The owner chose
"backfill keys from existing rows"; content-addressing delivers that outcome
without a migration, because the stored row *is* the key — that is the second
branch of `seen_before`. Nothing rewrites an existing `ExternalId`, so
`message_by_external` keeps working for the IMAP and Zoho callers that rely on it
(`imapmail.py:685`, `invoice_workflow.py:156`).

`conversation_id` is unchanged — the bare `gh:{repo}#{n}` / `jira:{KEY}`. That is
what routes the revision onto the existing task, and it must not pick up the hash.

`SentAt` is already the edit time on both connectors (`channels.py:1003` uses
`updated_at`, `pm.py:81` uses `fields.updated`), so revisions sort correctly with
no change.

### Known property

Edit A → B → back to A produces no third row: the text is one we have on file.
Defensible (there is nothing new to say) and it falls out of content-addressing
rather than being coded for. Recorded here because it will look like a bug to
whoever meets it first.

## §2 — Comments

A comment is a separate object with a stable vendor id, so it needs no hash:

- `gh:{repo}#{n}:c{comment_id}`
- `jira:{KEY}:c{comment_id}`

Both keep the item's `conversation_id` unchanged, which is the whole trick — it is
what makes `identity_route` treat a comment exactly as it treats an email reply.

Fetch cost:

- **Jira** — free. `/rest/api/2/search` already runs every poll; add `comment` to
  the `fields` list and they arrive inline. *Open at implementation: Jira caps
  inline comments per issue; confirm the cap and page the overflow, or accept the
  most recent N and say so.*
- **GitHub** — `GET /repos/{repo}/issues/{n}/comments`, called only for issues
  `list_items(since=…)` already returned as touched. A quiet repo costs zero calls.

Edited comments are out of scope. A comment's id is stable across edits, so an
edited comment stays as first read. Revisit if it bites.

**DECIDED: round one is the hash on all eleven write-once trackers, comments on GitHub and
Jira only.** The hash is one helper and a one-line call per connector. Comment
ingestion is per-vendor work — its own endpoint, pagination and body shape — so it
is built for the two the owner named, with the seam shaped so the next vendor is
a small addition.

## §3 — The quiet rules

Without these the feature is a noise generator, so they ship with it, not after.

**Our own comments become `Status='context'`.** Taskuary posts to GitHub issues
itself (`outbound.py:555`, `proposals.py:185`). Ingesting comments naively means
it reads its own reply on the next poll, triages it, and can reply again. Own
comments are kept — they are real thread history — but as `context`, exactly how
mail already treats the owner's own replies (`store.own_replies_to`). Identity is
already on hand: Jira's `test_jira` calls `/myself`, and GitHub's token answers
`/user`.

**Bot comments become `Status='context'` too.** GitHub marks them
(`user.type == 'Bot'`). CI, Dependabot and coverage bots are the highest-volume
commenters on any active repo and none of it is a person wanting something. In the
chain, never work.

**No new dispatch gate.** An earlier draft of this design set `no_auto` on every
revision. That was wrong twice over — see §4 — and is dropped. A revision carries
the same posture as a first sighting: GitHub keeps its per-repo `gh_auto_ok`
picker (off / team / contributors / anyone), Jira runs the normal `auto_start_ok`
trust gate, like mail.

## §4 — Dispatch on attach (all channels)

This section reaches beyond trackers and can land separately.

**The finding.** Auto-dispatch exists only on the *create* branch of
`ingest_message`. `_auto_code` is spawned at `ingest.py:781`, inside the `else`
that handles a new task. An attached message never reaches it. So a comment
landing on an **open, idle** task whose follow-up verdict says *this is a coding
job* starts nothing — the verdict is recorded and the row waits to be pushed by
hand. That has been true of every email reply for months, not just trackers.

It also makes the attach path inconsistent with itself: `ingest.py:599` already
spawns the **responder** when a follow-up is `reply_only`. Replies dispatch on
attach; coding and general do not.

**DECIDED: close it, for all channels, behind the same gates.** This matches the
owner's standing rule (`err-toward-coding-agent`: when unsure send it to the
coder — a cheap "nothing to do here" beats a job sitting on a list), and makes
"a comment is a new arrival" true end to end.

Rules for the attach branch:

- Dispatch on the **task's** `Kind`, not the message's. The task is the unit of
  work. A personal `task` already returns `False` from `auto_start_ok`, so it
  stays the owner's.
- Guarded by the existing `busy` check (`ingest.py:546`) — never interrupts an
  agent mid-run. The owner explicitly declined re-dispatching over a running
  agent. That path is already right: `answer_to_agent='auto'` types the comment
  into the live session, which is the answer the agent was waiting for.
- Same `auto_start_ok` / `gh_auto_ok` gates, same `needs_repo_choice` hold for a
  coding job with no nameable repository.
- Same `Unattended start allowed: …` comment on the task, so PW-080 still answers
  *why did an agent start on this*.
- `_auto_code` already does affinity routing — a task likely to collide with one
  being worked in the same checkout queues behind it rather than racing it — so
  dispatch-on-attach cannot put two agents in one tree.

## Phasing

1. **§1–3, trackers.** Self-contained, no funnel edits, reversible per connector.
2. **§4, attach dispatch.** Shared funnel behaviour for every channel. Lands and
   reverts on its own.

## Testing

- `rev_id` is stable for identical text and differs for changed text
- a pre-upgrade row (bare `ExternalId`) stays silent on the first poll
- an edited issue creates a second message and attaches to the open task
- an edit that only changes labels produces nothing
- a comment attaches to the open task and carries the unchanged `conversation_id`
- our own comment lands as `context` and creates no task
- a `type == 'Bot'` comment lands as `context`
- a comment on a **closed** task opens new work (PW-017 holds)
- a comment on an open idle coding task dispatches the coder (§4)
- a comment on a **busy** task does not dispatch
- `gh_auto_ok` still holds a stranger's comment on a repo set to `team`

## Risks

- **§4 has the widest reach.** Email replies on open coding tasks will start
  agents where they previously waited. Intended, but it is the part worth watching
  on real traffic before trusting.
- **Jira inline comment cap** is unverified; see §2.
- **Comment volume on public repos.** The bot rule handles automation; a genuinely
  busy human thread will still produce a row per comment, as a busy mail thread
  does.
