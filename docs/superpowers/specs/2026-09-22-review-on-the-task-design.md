# Review happens on the task

**Date:** 2026-09-22
**Status:** design, approved in conversation — not yet implemented

## Why

A decision about a task lives on a different page from the task. Stage 3 of the task page
shows the envelope and three lines of the draft, then hands you a button — *Edit draft in
Review* — that throws you onto another tab to do the one thing the card was about
(`TasksView.jsx:1656`). The task page already loads the review; it simply refuses to let
you act on it.

The split is not load-bearing. It is a leftover from when Review was the only place a draft
could be seen, and it has since been out-voted twice: the Assistant pile decides reviews
inline (`assistantCards.jsx` `ReplyCard`), and the Work rail already lists them as live work.
Review is the last surface that makes you go somewhere to say yes.

So: **every decision lives on a task.** The Review tab goes.

## 1 · The task page decides

Stage 3 stops being a preview and becomes the decision. It gains, from `ReviewView.jsx`:

- the inbound message above the draft (four lines, the rest one click away)
- the editable draft box, the TO line, the CC row, attachments
- Approve & send · No reply needed · Reject · Redraft
- the stale-draft warning **and its road out** — while the thread is ahead of the draft,
  *Refresh the draft* is the primary button, not a disabled Approve
- the held "waiting on the agent working this task" state, with *Answer now anyway*
- the approval-interrupt compare (PW-239): the owner's edit stays theirs, the refreshed
  draft is shown beside it
- the send-failed alert, which has to say so at the click rather than leave a NOT SENT line
  in the history to be found later

### Proposals share the section

`Kind:"action"` reviews — a proposed playbook, a proposed setting, a proposed tool run —
land in the **same** section, not a fourth stage. The reason is vocabulary, not tidiness:
`lanes.json` has exactly one lane for both, `approve`, whose hint reads *"a reply or an
action is drafted and waits for your yes"*. One lane on the rail must be one section on the
page, or the two surfaces disagree about how many things are happening.

This reverses the comment at `TasksView.jsx:613` (*"the Reply stage must show only
communication intended for the sender"*) deliberately. That rule existed to stop a
proposal's JSON envelope from being rendered as the current draft — a real bug, solved
properly by `proposalPresentation()` in `reviewProposal.js`, which already gives a playbook
its own title, SAVE TO destination, *Save playbook* and *Discard proposal* labels. The
presentation layer makes the exclusion unnecessary.

Three consequences:

- **The no-sender empty state goes.** Stage 3 currently renders *"No inbound sender is
  attached to this task, so there is nothing to reply to."* A settings proposal from chat
  and a playbook drafted after a coding job both have no sender and still need a yes. The
  stage renders on a pending review, not on `sourceMessage`.
- **`focusStage` opens on a proposal.** Today it opens stage 3 only for
  `reply === "draft ready"`, or a `kind === "reply"` task with a sender. A task whose only
  waiting thing is a playbook would open folded. A pending `Kind:"action"` review has to
  claim the open stage too.
- **Order, when both are pending:** the reply first, the proposal beneath it. Sending is
  what settles the task, and `proposals.py` queues a proposal after the reply anyway, so
  newest-first would put the lesser thing on top.

`pendingReplyReview()` keeps filtering `Kind:"action"` out of the *reply* slot — the reply
and the proposal are still two records with two verdicts — but the stage renders both.

## 2 · The rail speaks the Work rail's vocabulary

No new bucket and no new word. A task with a drafted reply stays in **in progress**; the row
says what is waiting.

The word comes from `lanes.json` — the file whose own header says *"a word cannot mean one
thing on the rail, another in chat and a third on the Timeline"*. `funnelPile.rowMeta()`
already turns a lane into its word and mark for the Work rail, chat and the Timeline; the
Tasks rail becomes the fourth reader of the same table.

This replaces a ladder that is already wrong, at `ui.jsx:1019`:

```js
export const stateOf = (t) => {
  if (!t) return ST.queued;
  if (t.Status === "dropped") return ST.dropped;
  if (t.Status === "done")    return ST.done;
  if (busyNow(t))             return ST.working;
  return ST.needs_you;                // incl. a session sitting at a question
};
```

Everything that is not dropped, done or busy falls through to the red `needs you`. So a task
with a drafted reply waiting already wears the identical chip to a coder parked on a
question — today, before any of this. After the change those are `reply ready ✉️` and
`agent waving 👋`, which is what the Work rail has been calling them all along.

**Only the fall-through is replaced.** `lanes.json` names live work and nothing else — its
own header says so — so it has no word for done or dropped, and `stateOf` keeps those
rungs. The `busyNow` rung and the `needs_you` fall-through are what give way to the lane.
This matters beyond tidiness: `cutAway` in §6 tests `stateOf(t).key` for done/dropped, and
those rungs surviving is why the two changes do not collide in either order.

**Server side:** `/api/tasks` returns the row's lane so the rail reads the assigned lane
rather than re-deriving one. `funnel.py` is the only thing that assigns lanes and stays so;
the Tasks rail must not grow a second derivation, or the two will drift and this whole
section will have been for nothing.

## 3 · No review without a task

`review.TaskId` is nullable and three paths create a review with none:

| path | what it is |
|---|---|
| `concierge.propose_switch` (`concierge.py:1560`) | a setting you asked for in chat — no task, no message |
| `invoice_workflow` (`invoice_workflow.py:175`) | an outbound Zoho invoice awaiting approval |
| `reports` (`reports.py:2140`) | an outbound report awaiting approval |

With no Review tab these have nowhere to be decided. **`store.add_review` creates a task
when `TaskId` is missing** — one chokepoint, so no call site added later can strand a
decision by forgetting. The three existing callers pass their own title and kind so the
words are theirs, not a generic fallback:

- `Invoice · <customer> · <period>`
- `Report · <title> → <recipients>`
- `Setting · <what you asked for>`

A one-off migration gives the same treatment to rows already sitting in live databases.

## 4 · The word "Review"

Roughly 100 strings name Review as a **place** — *"it proposes, you approve in Review"*,
*"a question waits in Review for your approval"* — across `taskuary/*.py` connector and
agent prompts, `website/src/*.jsx` tooltips, and `docs/`. Agents read some of them aloud
during connector setup. Once the tab is gone every one of them names a room that does not
exist.

They become **"on the task"**: the capital-R place disappears, lowercase review survives as
the act.

```
"it proposes, you approve in Review"      → "it proposes, you approve on the task"
"a question waits in Review for your yes" → "a question waits on the task for your yes"
"Edit draft in Review"                    → (gone — the draft is already in front of you)
```

The `/api/reviews` endpoint and the `review` table keep their names. They are internal,
nobody reads them, and renaming them would churn the ~80 test references that are correct
as they stand.

## 5 · Docs folds into Settings

Removing a tab unbalances a nav strip that is absolutely centred on the Assistant pill, so
Docs moves in beside the other configuration.

`NAV` in `SettingsView.jsx:816` becomes `["about", "docs", "config", "policies", "memory",
"audit", "updates"]` — a rail entry immediately after About you, scrolled to like every
other section, with `PAGES.docs` carrying its title, icon and description. `DocsView`
renders as that page unchanged; it keeps reading its own hash for `#playbook=` and
`#profiles`.

**The deep links have to follow it.** `TaskHubPage.jsx` currently routes
`#playbook=` and `#profiles` to `go("Docs")`; those become `go("Settings")` with the docs
rail entry selected, or the connector cards' playbook links land on a tab that is gone.

Tabs go 9 → 7 and the strip is symmetric again:
`Board Tasks Reports · ✦ · Hub Connections Settings`.

## 6 · The pill counts, which do not add up

Independent of everything above, and lands first.

Observed: `all 5`, `in progress 4`, `done 2`. Root cause at `TasksView.jsx:511`:

```js
const countIn = (key) => {
  const rows = (tasks || []).filter((x) => !key || inBucket(x, key));
  return !search && key !== "live" && !older ? rows.filter(touchedToday).length : rows.length;
};                        //   ^^^^^^^^^^^^^ "in progress" alone is exempt from the today-cut
```

`in progress` counts live tasks of any age. `all` and `done` count only tasks touched today.
Two time windows, so `all` is not a superset of its own parts and the arithmetic cannot
close. Confirmed against live rows: TQ-0667 and TQ-0664 (`waiting`, both 2026-09-21 23:2x)
are live and not touched today — counted under `in progress`, excluded from `all`.

The cut is being applied **per pill** when it belongs **per row**. Live work has no age; it
is live whether it arrived this morning or last night. History does have an age.

```js
// the cut is about HISTORY, not about which pill you are on: live work shows at any age,
// finished work stops at today until "show older"
export const cutAway = (t, older) =>
  !older && ["done", "dropped"].includes(stateOf(t).key) && !touchedToday(t);
```

Used by both `countIn` and `shown`. Then `all` = live (any age) + finished (today): a true
superset, and the archive still cannot flood the list — which is what the cut was for
(*"A count that outruns the rows beneath it reads as a bug"*).

The predicate moves to `taskFilter.js`, already the home for this kind of pure list logic,
where it can be tested without a browser.

## 7 · Which stage opens, when two things want you

The ladder stays exactly as it is, and it is already pinned by
`taskLifecycle.test.mjs:56-68`: a draft ready outranks everything, then an agent with work
in it, then the task. The only new rung is that a pending `Kind:"action"` review also opens
stage 3 — every existing assertion still holds.

The Assistant already mirrors this. `funnelPile.assistantFocus()` returns the same three
cards with the sentence that says which, and its comment states the contract outright:
*"the assistant's answer to the task page's `focusStage`, and kept in the same precedence
so the two cannot drift."* It also already routes a proposed action to the **reply** card
with its own words — which is the strongest argument that §1 is right: the Assistant has
worked this way since 2026-09-14 and the task page is the surface out of step.

### The case where they do drift

They disagree today, despite the comment:

| both true at once | task page | Assistant |
|---|---|---|
| agent waving **and** something waiting on your yes | opens **reply** | shows the **agent** card |

`focusStage` tests reply first; `assistantFocus` tests `lane === "blocked"` first, and since
an item carries one lane and `blocked` sorts above `approve` in `lanes.json`, the funnel
hands it over as the agent's.

**How often can that happen?** For a reply, almost never — `terminal.py:970` calls
`store.hold_reviews()` when a session starts, parking pending drafts as `held` (*"a draft
written from the mail alone promises what the session has not found yet"*). It is reachable
only by pressing *Answer now anyway* on a held draft while the session is still alive, which
is the owner explicitly overriding the hold.

But `hold_reviews` matches `Kind IN ('draft','draft_reply')` only. **A `Kind:"action"`
review is never held.** So an agent that proposes a playbook and then stops with a question
leaves a waving agent and a pending proposal — routinely. This design makes that case more
visible, not less, since it is the one moving proposals into stage 3.

### The rule

Not a flat precedence, because it is usually **one event seen twice**. `lanes.json` already
has the sub-state: `blocked.says.approval` is *"{agent} needs your approval"*. When an agent
is parked because it proposed something, the proposal **is** the answer to the wave —
approving it is what releases the agent. Opening the agent stage there would show a terminal
sitting at a prompt with the thing that unblocks it folded away one card below.

> The agent wins, **except** when the agent is blocked on `approval` and a proposal is
> pending — then stage 3 opens, because that proposal is what it is waiting for.

`assistantFocus` gains the same exception, in the same shape, so the contract its own
comment claims becomes true rather than aspirational. Both get a test for the exception and
for the plain case either side of it.

## 8 · The red count moves to Tasks

The badge is the one thing the Review tab gave you without going anywhere, so it survives
the tab. `TaskHubPage` already has `refreshPending` and already recounts on
`feed-changed` / `task-changed`; only the pill it decorates changes.

It counts **tasks, not reviews** — deduplicated by `TaskId`. A task holding both a drafted
reply and a proposed playbook is one thing waiting on you, and `Tasks · 5` over four rows
would be the same "count that outruns the rows beneath it" the pill counts were fixed for
in §6.

Deliberately *not* widened to everything on you: a waving agent is not counted. That would
be a better number, but it is a different number from the one being moved, and changing its
meaning in the same breath as its home is how a count quietly starts lying. Easy follow-up
once this lands.

## Code shape

`ReviewView.jsx` does not move into `TasksView.jsx`. TasksView is 2043 lines and would take
another ~250. Instead the decision block is extracted to **`ReviewDecision.jsx`** — one
review in, a verdict out — and stage 3 mounts it. `ReviewView.jsx` is then deleted, not
kept as a second caller.

Files touched:

| file | change |
|---|---|
| `website/src/ReviewDecision.jsx` | **new** — the decision, extracted |
| `website/src/ReviewView.jsx` | **deleted** |
| `website/src/TasksView.jsx` | stage 3 mounts the decision + proposals; `onGoReview` prop and its three call sites go |
| `website/src/TaskHubPage.jsx` | `TABS`, the pending badge, the Review mount, `#playbook`/`#profiles` routing |
| `website/src/taskLifecycle.js` | `focusStage` opens on a pending proposal, and the `approval` exception |
| `website/src/funnelPile.js` | `assistantFocus` gains the same exception, so the two stay in lockstep |
| `website/src/ui.jsx` | `stateOf`'s busy rung and `needs_you` fall-through give way to lane tags; done/dropped stay |
| `website/src/taskFilter.js` | `cutAway` |
| `website/src/settingsMap.js`, `SettingsView.jsx` | the docs rail entry |
| `website/src/FloatingAssistant.jsx` | the "Review" quick prompt and its tab list |
| `website/src/GeneralWorkspace.jsx` | the *All review* button |
| `taskuary/store.py` | `add_review` creates the task; migration |
| `taskuary/concierge.py`, `invoice_workflow.py`, `reports.py` | pass title and kind |
| `taskuary/server.py` | `/api/tasks` returns the lane |
| ~100 strings across `taskuary/`, `website/src/`, `docs/` | "in Review" → "on the task" |

`lanes.json` is **not** edited. That is the point of it.

## Testing

- `cutAway` and the pill counts: unit tests in `website/test/` (`node --test` is wired up),
  written failing first.
- `focusStage` with a pending proposal and no sender: `taskLifecycle` tests.
- The `approval` exception, and the plain case either side of it, asserted **twice** — once
  against `focusStage` and once against `assistantFocus` — so the lockstep the comment
  claims is enforced rather than hoped for. `assistantFocus.test.mjs` already exists.
- The badge counts tasks, not reviews: a task holding a reply *and* a proposal counts once.
- `add_review` with no `TaskId` creates a task; the migration backfills existing rows:
  pytest, against a temp home — `conftest` forces one, and it must stay that way.
- The full pytest suite from the repo root before any push. "No tests ran" is a failure.
- `npm run lint:undef` and a bundle rebuild, since `.jsx` is syntax-checked by esbuild and
  never by pytest.

## Deliberately not done

- **`lanes.json` gains no `says` split for `approve`.** A playbook proposal will tag
  `reply ready`, which is the lane's existing word and is slightly a lie over a playbook.
  Combining proposals into the same section makes it much less of one — the section
  genuinely holds both — and the alternative was a new sub-state vocabulary for a wart this
  small. Revisit if it reads wrong in use.
- **No cross-task queue replaces the Review tab.** The Assistant pile is the walk through
  what needs you; the Tasks rail shows the tag on the row. The tab's history filters
  (approved / edited / rejected / no_reply) retire rather than move — each task keeps its
  own verdict in Context & history.
- **The `review` table and `/api/reviews` keep their names.**
