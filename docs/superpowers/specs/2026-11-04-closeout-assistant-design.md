# Close out is the Assistant's chat about the task

2026-11-04. Approved direction from the owner, with mockup v3 (stand-in names). This spec turns it into code.

## Why

Close out is the core of the app. It is the one place where a task ends, and today it is a decision card: the message being
answered, a draft and its buttons. To work out what to send, the owner still reads the whole thread, opens the Agent section to see
what was done, and works out for themselves which email actually holds the request. The owner's words: "an Instinct-level assistant
for your job... it's holding your hand... you just talk it into the final result."

The pipeline under Close out does not change: triage, then the agent (when one runs), then the drafts, with the same buttons on top
(Remind me, Watch it, Mark done, Change ▾) and a Send on each draft. What changes is that the Assistant puts it all together in Close
out as a short conversation, and the owner corrects it by talking to it.

## What the owner sees

Close out is a chat column. Its first three messages come from Taskuary and are rebuilt whenever what they rest on changes:

1. **What they're asking.** The ask, read across the whole thread, not the newest mail:
   - who wants what;
   - who else on the thread already handled which part ("Gail owns the accounting side and answered on 11/3");
   - **your part**;
   - mails that don't change the ask, named as such: "The last two emails, Ray apologising and Gail thanking him, don't change the
     ask, so the reply answers Ray's 11/2 email to everyone on it."

   It ends with a link: "The whole thread (N messages) ›" opens Came from.
2. **What I did.** When an agent ran, a summary of its work: what it found and where, and what it made, with "The agent's full
   work ›" opening the Agent section. When no agent ran, the drafter's reasoning: "I read his message and the two earlier invoices
   from Vendor; I think he wants a pay date, so I drafted one that asks AP first."
3. **What's next.** In order:
   - every pending draft, as today's draft card, with its own Send, Send and close, and Edit (`ReviewDecision`, `MoreDrafts`,
     slots);
   - every step only the owner can take, said plainly in a highlighted line: "**On you:** send Ray the password through your
     password tool. Tell me when that's done and I'll close this out." No draft is shown when nothing can be sent, and "nothing to
     send" is said in words.

After those three come event lines, as they happen:
- new mail on the thread ("↓ 2:14 PM · Ray Colton wrote again: …"), followed by Taskuary saying what it changed ("Ray added a third
  address, so I added it to the bank email");
- the agent finishing;
- a draft being redone.

Then come the owner's turns and the Assistant's answers. At the bottom sits one box: "Tell me what's wrong, or ask about anything
here…", with the mic.

**When it opens.** Close out is the section a task opens on, unless an agent is working and needs the owner (it asked a question, is
waiting on a sign-in, or holds a step for Approve). Then the Agent section opens, as today. A task with no agent and no draft still
opens on Close out, and its "What's next" says what is left.

**Reports, FYI and dashboards** get the same column on their own item: "What this says", "What matters to you" and the box. This is
phase 4 below.

## What the box does

The box talks to **the Assistant, scoped to this task**. Every turn answers in one of three ways:

- **It answers from what is on hand:** the thread, the brief, the agent's record and outputs, the drafts. "Where did you find the
  user name?" gets "northwind/ledger/.env, SFTP_USER."
- **It changes a draft:** a redraft with the owner's instruction, a different email to answer ("reply to the second-to-last email"),
  or recipients ("cc Gail", resolved by name from the thread's people and the address book). The draft card updates in place.
- **It hands the work back to the agent** when the question needs new work: check again, find something else, redo a part. The
  agent's own session continues with the owner's exact words (10266b87b already carries exact words under YOU). Close out adds "Sent
  to the agent: …", with a quiet "Agent working…" line until the turn ends. Then the brief and the drafts rebuild. With no agent on
  the task, "hand it to the agent" starts one with the owner's words as its brief.

The Assistant never presses Send, Send and close, Mark done or Approve. It may light them, as today (assistant-sees-the-page).
"Tell me when that's done" from an **On you** line is answered in the box ("done", "sent it"). The Assistant marks that step done,
and when nothing is left it lights Send and close or Mark done.

## Memory

It is invisible. There is no chip and no "Remembered" line. Every correction made in the box is an event for the existing learning
paths, so that triage, the drafter and agents do better next time:

- A redraft instruction goes to `_keep_instruction`, then `byrecipient`. Said twice for the same person, it becomes a STYLE.md "By
  recipient" line. These are today's paths.
- "That's not the ask" and "reply to that email instead" are a new `learn.learn_from` event, `closeout_correction`, carrying the
  brief, the correction and the thread. Triage reads all of LEARNED.md already.
- The drafter's reads widen from `('people',)` to `('people', 'work')`, so "on Payworth access threads, Gail is copied" reaches the
  next draft. This needs a budget check on `voice_line`.

## The code

### 1. The task brief (new: `taskuary/brief.py`)

There is no thread-level reading today: triage is per message, and nothing marks which message carries the ask. Add one model call
per task, the **brief**:

```
{"asking": "...", "your_part": "...", "others": [{"who": "...", "did": "..."}],
 "ask_mid": 1234, "aside": [{"mid": 1240, "why": "thanks only"}],
 "did": "...", "did_by": "agent" | "drafter" | "",
 "next": [{"kind": "draft", "review": 88} | {"kind": "on_you", "text": "...", "done": false}],
 "at": "...", "rests_on": {"mids": [...], "run": 12, "reviews": [...]}}
```

- **Reads:** the whole thread (`ingest.exchange_lines`), the verdicts on its routes, the agent's report and final words
  (`responder.resolution_of`), the pending drafts and their reasons, the checklist, and LEARNED.md (the `whole` cut, as triage).
- **Model:** the triage model and provider, through the same `llm` door, with strict JSON via `cli_json` and a `schemas` entry.
  There is no keyword logic: the model reads intent (no-rules-ai-sees-everything).
- **Stored on the task:** `task.BriefJson` and `BriefAt` (a migration in `store._SHAPE_NOW`).
- **Rebuilt when** what it rests on changes:
  - triage files a route on the task;
  - wrapup finishes a run;
  - a draft is written or redone;
  - an **On you** step is marked done.

  It runs debounced in the background (`_spawn`), and the page reads the last one. While it rebuilds, the old one stays drawn under
  a quiet "updating…".
- **Came from** shows `asking` and `others` as its "What's going on" paragraph, above "What triage made of it" (owner: "update the
  came from triage to have text summary").

### 2. The reply goes to the email that holds the ask

- `responder.draft_reply` takes the target from the brief's `ask_mid` when there is one, else the newest inbound, as today. The
  subject, From line, `asked` and `pin_review_context` all use it.
- `outbound.reply_envelope(..., mode='reply_all')` is built on that message, so the reply goes to everyone on the email that holds
  the ask.
- In `ingest`: a new mail that the brief puts **aside** (thanks, an apology, "got it") no longer re-points a pending draft (today
  `update_review_message` re-points it to whatever arrived). The draft stays pinned to the ask, and the brief rebuild says why.
- An owner's "reply to the second-to-last email" sets the target explicitly: `review.AnswersMid` overrides `ask_mid`.

### 3. The drafter says why

`draft_reply` adds one control line, `WHY: <one or two sentences>`, parsed like `NEEDS:` and `FILES PROMISED:` and stored as
`review.DraftWhy`. It is "What I did" when no agent ran. It is never sent and never appears in the draft body.

### 4. The Close out chat (UI)

- **New `website/src/CloseoutChat.jsx`.** It is mounted in the `slot("close", …)` body (`TaskPage.jsx` ~3357) in place of today's
  Answering line and top of the card.
  - It draws the three brief messages, then the event lines and turns from `GET /api/tasks/{tid}/closeout`. That endpoint returns
    the brief, the events since `BriefAt` and the turns.
  - The draft cards stay the existing components (`ReviewDecision`, `MoreDrafts`, `SlotList`), rendered inside "What's next", so
    there is one copy of each draft and the Send semantics are unchanged (task-close-slots, walk-one-owner).
- **Turns** are task comments with `ActorType` `closeout` (the owner) and `closeout-assistant`, so they persist and survive a reload.
- **The box:** `POST /api/tasks/{tid}/closeout/say {words, view}`. It goes to `concierge.say` with the scope pinned to this task (the
  existing `item` / `set_current` machinery). Its replies are filed on the task, not in the dock's conversation.
- **The dock Assistant** stays the app-wide chat. A Close out turn shows there as one line, "In TQ-1258: …", so there is still one
  Assistant with one memory, seen in two places. This supersedes the "never a second chat" line of the 2026-09-29 canvas spec, at
  the owner's request.
- **Tools the scoped turn may use** sit inside today's catalogue, with no new buckets: `reply`/`redraft` with an instruction,
  `answer_to` (new: sets `AnswersMid`), recipients (`_loop_in` and a remove), `agent.tell` / `agent.start` (existing hand-off with
  exact words), `onyou.done` (new), and lighting buttons. `toolcatalog.block()` stays under its 7,950-character gate.
- **Which section opens:** the "open where the task is up to" rule (three-sections) changes. Close out is the default, and Agent wins
  only while the agent needs the owner.

### 5. Agents do more of the work

The bank credentials case: the login was in a project's `.env`, and the agent left it to the owner. `general.repos_block` and the
assistant template already say to read a repo's `.env` and never paste a secret. The builder must first find out from that run's
record why it did not look (no agent ran? no repo map? the agent didn't search?), then fix that cause. The fix must not be a rule.
It must give the agent better context: the brief's `your_part` goes into the agent's brief, plus "before leaving a step to the owner,
look for it in the projects and folders you can read". It is pinned by an eval case built from the shape (a vendor asks for a login
that sits in a project's .env), with invented names.

A secret the agent found is never pasted into a draft or a chat line. The draft says "password to follow separately", and the
**On you** line says how the owner sends it.

## Phases (each ships on its own)

1. **The brief, and Close out drawn from it.** brief.py, the task columns, rebuild triggers, Came from's paragraph, the three
   messages and **On you**. There is no box yet, and drafts are drawn where they are today, inside "What's next".
2. **The reply target and the drafter's WHY.** `ask_mid`, aside mails no longer re-pointing drafts, `AnswersMid`, `DraftWhy`.
3. **The box.** The scoped Assistant turns, events, tools, the dock line and the open-on-Close-out rule.
4. **Reports, FYI and dashboards** get the column.
5. **Learning and agents.** `closeout_correction`, the drafter's wider reads, the agent context change and its eval.

## Goals, non-goals, anti-goals

- **Goals:**
  - the owner can act on a task from Close out alone in the common case;
  - every correction is made by talking;
  - the reply answers the email that holds the request.
- **Non-goals:** changing triage's per-message verdict; changing Send semantics; replacing the Agent section's full record.
- **Anti-goals (a failure even if it works):**
  - a second copy of a draft;
  - any auto-send or auto-close;
  - a visible memory list or confirm card;
  - keyword rules deciding "aside";
  - Close out stealing focus from an agent that is waiting on the owner;
  - a secret in a draft or a chat line;
  - any real person, company or address in tests or fixtures.

## Tests

Every phase brings Python tests on invented threads (Alex Doyle, Northwind, Ray Colton, Gail Moreno, `*.example`) and browser tests
on the fixture app:

- a thread whose last two mails are thanks: the brief names them aside, and the draft answers the earlier ask, to everyone on it;
- two drafts plus an **On you** step, each draft sent on its own;
- "cc Gail" in the box updates the card;
- "where did you find it" is answered without an agent call;
- a "check again" goes back to the agent with the owner's exact words;
- new mail mid-review adds an event line and the drafts update;
- Close out opens by default, and Agent opens while it asks.

The walk table must still pass, because Send and close drives the walk.

## The owner's answer after the builder check

- **The brief is built for every task, as mail lands** (owner, 2026-11-04). It is ready the moment a task is opened, and it is rebuilt
  on each trigger above. FYI items, reports and dashboards get theirs when first opened (phase 4).

## Calls made after the builder check (the spec author's, not the owner's)

- **Name:** `taskuary/brief.py` is taken (the agent's brief), so the module is `taskuary/threadbrief.py`. The columns go in the
  normal `ALTER TABLE` block; `_SHAPE_NOW` is triage prompt text.
- **"On you" steps are checklist items** owned by the owner (`checklist` with an `owner` mark), not part of `BriefJson`. A rebuild
  may add one but never unticks or rewrites one that is ticked, and "Done ticks every box" applies to them as to any item. The brief
  refers to them by checklist id. `onyou.done` ticks the item.
- **Aside timing: re-point, then restore.** `ingest` keeps today's behaviour, re-pointing and redrafting at once, so a real
  follow-up is never slowed. When the brief rebuild that the same arrival sets off names the mail aside, it restores the draft's
  `AnswersMid` to the ask. It redrafts only if the draft changed because of that mail.
- **Target and freshness are split.** `review.MessageId` stays the newest mail seen (freshness, `context_moved`, `Stale`, and Send's
  checks are unchanged). The new `review.AnswersMid` is the delivery target: subject, In-Reply-To and the reply-all envelope. With
  no `AnswersMid`, it falls back to `MessageId`, which is today's behaviour.
- **Events and turns are one permanent timeline** on the task, ordered by time. The three brief messages are always drawn on top,
  rebuilt in place. A rebuild never removes an event line.
- **Each draft answers its own email.** The brief carries `asks: [{mid, about}]`, and each pending reply review gets its own
  `AnswersMid`. A box turn that changes "the reply" applies to the draft it names. With one reply draft it applies to that one, and
  when it is ambiguous the Assistant asks which.
- **The credentials case is diagnosed read-only** on the live home by the builder (sqlite `mode=ro`). Only its shape goes into the
  repo, the eval and commit messages.
- **Two places, two conversations:**
  - A Close out turn runs on a conversation key of its own for each task, and sees the task's timeline, not the dock's history.
  - The dock's next turn sees the one-line "In TQ-…: …" summaries.
  - Memory (LEARNED.md, STYLE.md) is shared, which is what "one Assistant" means here.

## Left to the builder

- the brief prompt's wording and its JSON schema details;
- the debounce interval;
- the event line copy;
- the exact layout inside the column;
- how a long thread is cut to fit the brief's prompt;
- whether a stale brief is redrawn on open or only on change.
