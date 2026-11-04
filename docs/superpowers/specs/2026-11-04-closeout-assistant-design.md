# The agent's chat is where a task ends: Close out folds into it

2026-11-04. Worked out with the owner through three mockups (stand-in names) and a builder check. **This replaces the first version
of this spec**, in which Close out became a separate Assistant chat beside the agent.

## Why

Close out is where a task ends, and today it is a decision card: the message being answered, a draft and its buttons. To work out
what to send, the owner reads the whole thread, opens the Agent section to see what was done, and works out for themselves which
email actually holds the request. The general agent's chat is a second place to talk about the same task.

The owner, in their words:
- "an Instinct-level assistant for your job… it's holding your hand… you just talk it into the final result";
- "combine the general agent and close out when it's non coding… it's really the same thing";
- "let the agent just do the work and mail etc and only have 2 sections".

So for a non-coding task, **the agent's chat is the task's whole conversation**: what it's about, what was done, what's next and its
buttons, plus one box to correct it. Coding tasks do not change.

## What does not change

- **Triage and starting:** triage reads every arrival and decides as today (a sub-agent or the core agent by size, plus auto-routing
  when it is on). The agent starts by itself, as today. Nothing waits for the owner to open the task.
- **Coding tasks:** the coding CLI in its terminal, with Came from, Agent and Close out exactly as today. Nothing is typed into a
  coding terminal by Taskuary, and no card is drawn over it.
- **The task's top buttons:** Remind me, Watch it, Mark done and Change ▾.
- **Send semantics:** each draft's Send and Send and close, held steps' Approve, never an auto-send, and never an auto-close.
- **Exact words:** what the owner types shows under YOU word for word (10266b87b), and anything Taskuary adds stays folded.

## What the owner sees on a non-coding task

Two sections: **Came from**, then **the agent's chat**. The chat is the default section the task opens on.

**Came from** is the thread as today, with a short **"What's going on"** paragraph on top, written by triage (below).

**The agent's chat**, top to bottom:

1. **The ask, as triage read it.** It is drawn before the agent says anything, so a task with no agent (a reply that only needed a
   draft) still has it:
   - who wants what;
   - who on the thread already handled which part;
   - **your part**;
   - the mails that don't change the ask, named as such: "the last two emails are thanks, so the reply answers Ray's 11/2 email".
2. **While the agent works:** one quiet line, "Working on this…". Its steps are folded under it and open on a press. There are no
   live lines scrolling by.
3. **When the agent needs the owner:** it says so in plain words: "I got an email about the bank login and I'm not sure what to do
   next: should I send it to Ray, or wait for Gail?" Choice buttons appear only when the agent gave real choices (ba4ab43c3). The
   owner answers in the box.
4. **When the agent's turn ends**, its last message has three parts:
   - **What this is about:** from triage's reading, whatever the source (email, a chat, monday.com…).
   - **What I did:** what it found and where, and what it made. Its full steps stay folded above.
   - **Next steps:**
     - every draft as its card, with its own Send, Send and close, and Edit, drawn **inside this message**;
     - every step only the owner can take, as an **On you** line: "On you: send Ray the password through your password tool. Tell
       me when that's done and I'll close this out.";
     - or "Nothing left to do here", with Mark done lit.
5. **New mail on the thread** arrives as a line ("↓ 2:14 PM · Ray Colton wrote again: …"). The agent takes it as its next turn (it
   does this today, `_carry_on`) and ends that turn with an updated three-part message. Drafts the new mail changes are redone in
   place, and the earlier summary folds.
6. **The box** at the bottom: "Tell me what's wrong, or ask about anything here…", with the mic. It continues the agent's session
   with the owner's exact words. "Cc Gail", "reply to the second-to-last email", "where did you find the user name?" and "check
   again" all go the same way.

**When no agent ran** (triage made it a reply and the drafter wrote it): the chat shows part 1, then the drafter's reasoning as "What
I did" ("I read his message and the two earlier invoices; I think he wants a pay date, so I drafted one that asks AP first"), then
the draft card. The box starts the agent with the owner's words (`agent_on_reply`, as today), and from then on it is the agent's
chat as above.

**Close out as a section is gone for non-coding tasks.** Everything it held (the draft cards, slots and owed emails, the To/Cc line,
the sent history and the calendar invite line) moves into the agent's chat, inside the message it belongs to. The sent history stays
as the agent's earlier summaries plus "Sent ✓" on each card that went.

## How it is built

### 1. Triage writes the thread reading

Triage already reads every arrival and the task it lands on. Its verdict gains a `thread` object, written on every arrival on a task:

```
"thread": {"asking": "...", "your_part": "...", "others": [{"who": "...", "did": "..."}],
           "asks": [{"mid": 1234, "about": "..."}], "aside": [{"mid": 1240, "why": "thanks only"}],
           "on_you": ["..."]}
```

- The fields join the strict schema, the contract line in `templates/triage.md` and `tests/test_verdict_shape.py`.
- Triage is given the task's thread so far (`ingest.exchange_lines`), the task's last `thread` reading and the agent's latest report.
- It is stored in `route.VerdictJson` as today. The newest reading is copied to a new `task.ThreadJson` column (the normal
  `ALTER TABLE` block) for the page.
- It is drawn as part 1 of the chat and as Came from's "What's going on".
- There is no keyword logic: the model reads intent (no-rules-ai-sees-everything).
- There is no new model call: it rides on the triage call that already happens.

### 2. The agent's goal changes (profile and brief)

The general agent's instructions (`templates/assistant.md`, the default general profile, and the brief `brief.py` builds) change from
"do the job" to **"get the owner to done"**:

- Read triage's `thread` reading first: what is asked, the owner's part, and who handled what.
- Do as much of the owner's part as you can before leaving anything to them. Look in the projects and folders you can read
  (`general.repos_block`) before saying a thing can't be found. The bank-credentials case was a login that sat in a project's
  `.env`, and the agent left it to the owner.
- Never paste a secret into a draft or a message. Say it follows separately, and make sending it an **On you** step.
- Draft every email the job needs through the existing tools (`taskuary --reply`, `slots.draft`). The reply answers the email that
  holds the ask (section 4).
- End every turn with the three parts. If you need the owner, say what you got and what you are unsure about, in one or two plain
  sentences, with choices only when there are real ones.

The end-of-turn message is structured, not free text: the agent ends with a short block the server parses. A shape like
`SUMMARY: {"about": …, "did": …, "on_you": […]}` follows the pattern of `taskuary --reply` and selfclose's lines. The page draws it
as the three parts, with the turn's drafts from the store. A turn that ends without the block falls back to today's display.

The builder must first read the bank-credentials run read-only (live home, sqlite `mode=ro`) to see why the agent did not look. The
fix must address that cause by giving the agent better context, not by adding a rule. It is pinned by an eval case built from its
shape, with invented names.

### 3. The buttons move into the chat

- **New `website/src/AgentSummary.jsx`** draws the three-part message. Its "Next steps" renders the existing draft and slot
  components inside it (`ReviewDecision`, `MoreDrafts`, `SlotList`). There is still one copy of each draft, Send is still Send, and
  the walk's Send and close is the same press (walk-one-owner).
- **`GeneralWorkspace.jsx`** draws part 1 from `task.ThreadJson`, folds the working steps under "Working on this…", and draws each
  end-of-turn summary with `AgentSummary`. Earlier summaries fold and the newest stays open.
- **`TaskPage.jsx`:** for a non-coding task the section list is `[from, agent]`, and `slot("close", …)` is not drawn. Coding tasks
  keep `[from, agent, close]`. The "open where the task is up to" rule becomes: a non-coding task always opens on the agent's chat.
- **The "drafted a message → opens Close out" behaviour is retired.** The draft is in the chat where it was made. This supersedes the
  2026-11-02 approve-agent-draft-in-place ruling and the stage-3 decision card of the 2026-09-22 review-on-the-task spec, for
  non-coding tasks.
- **On you steps** are checklist items with an owner mark. The box's "done" / "sent it" goes to the agent, which ticks the item
  through `taskuary` and ends its turn. When nothing is left, Mark done is lit, never pressed.

### 4. The reply goes to the email that holds the ask

- **Target and freshness are split.** `review.MessageId` stays the newest mail seen: freshness, `context_moved`, `Stale` and Send's
  checks are unchanged. A new `review.AnswersMid` is the delivery target (subject, In-Reply-To, the reply-all envelope); without it,
  delivery falls back to `MessageId`, as today.
- **The drafter** (`responder.draft_reply`) and **the agent's reply tool** (`wrapup.reply_target`) set `AnswersMid` from triage's
  newest ask in `thread.asks`. `outbound.reply_envelope(..., mode='reply_all')` is built on that message.
- **Aside mails:** triage writes `aside` in the verdict on the mail itself, so `ingest` knows before it re-points anything. An aside
  mail leaves `AnswersMid` on the ask and does not redraft. Every other mail re-points and redrafts as today.
- **Several drafts** each answer their own email. Each pending review has its own `AnswersMid`. "Reply to the second-to-last email"
  sets it on the draft the owner means, and the agent asks which one when it is unclear.

### 5. The drafter says why

`draft_reply` adds one control line, `WHY: <one or two sentences>`, parsed like `NEEDS:` and `FILES PROMISED:` and stored as
`review.DraftWhy`. It is "What I did" when no agent ran. It is never sent and never shown in the draft.

### 6. Fast answers: the session stays warm

A simple ask ("cc Gail") should come back in seconds. The general agent's CLI session stays alive while its task is open on screen,
plus a grace period after leaving, so a turn does not pay for a cold resume. The builder measures the cold-resume and warm-turn
times and picks the grace period. The idle sessions' memory and the provider's concurrency limits bound how many stay warm.

### 7. Memory is invisible

There is no chip and no "Remembered" line. A correction made in the box reaches the existing learning paths:

- A redraft instruction goes to `_keep_instruction` and then `byrecipient`. Said twice for the same person, it becomes a STYLE.md
  "By recipient" line.
- "That's not the ask" or "reply to that one instead" becomes a `learn.learn_from` event, `owner_correction`, carrying the thread
  reading, the correction and the thread. Triage reads all of LEARNED.md.
- The drafter's reads widen from `('people',)` to `('people', 'work')`, with a budget check on `voice_line`.

### 8. Reports, FYI and dashboards (later phase)

The same column on their own item: triage's reading as "What this says", "What matters to you", and the box. A turn there starts a
light general agent on the item (read-only).

## Phases (each ships on its own)

1. **Triage's thread reading:** the verdict's `thread` fields, `task.ThreadJson`, Came from's "What's going on", and part 1 drawn at
   the top of the agent's chat.
2. **The reply target and the drafter's WHY:** `AnswersMid`, aside mails not re-pointing, `DraftWhy`.
3. **The agent's new goal and the summary block:** the profile and brief text, the `SUMMARY:` block, `AgentSummary.jsx`, "Working
   on this…" folding, and the bank-credentials diagnosis and eval.
4. **Close out folds in:** the cards move into the chat, `[from, agent]` for non-coding tasks, opening on the chat, On you checklist
   items, and the walk table re-proved.
5. **A warm session and learning:** the keep-warm period, `owner_correction`, and the drafter's wider reads.
6. **Reports, FYI and dashboards.**

## Goals, non-goals, anti-goals

- **Goals:**
  - in the common case the owner acts on a task from the agent's chat alone;
  - every correction is made by talking;
  - the reply answers the email that holds the request;
  - agents do more of the owner's part.
- **Non-goals:** changing triage's routing, how agents start, coding tasks, or Send semantics.
- **Anti-goals (a failure even if it works):**
  - a second copy of a draft;
  - any auto-send or auto-close;
  - a visible memory list or confirm card;
  - keyword rules deciding "aside";
  - anything typed into a coding terminal;
  - a secret in a draft or a chat line;
  - live working lines scrolling past;
  - any real person, company or address in tests, fixtures or this repository.

## Tests

Each phase brings Python tests on invented threads (Alex Doyle, Northwind, Ray Colton, Gail Moreno, `*.example`) and browser tests
on the fixture app:

- a thread whose last two mails are thanks: triage names them aside, and the draft answers the earlier ask to everyone on it;
- an agent turn ending with two drafts and an On you step: each draft is sent from inside the chat, and Mark done lights when the
  On you step is ticked;
- "cc Gail" in the box changes the card, and "where did you find it" is answered;
- new mail mid-task adds a line, the next summary replaces the last, and the drafts update;
- a non-coding task opens on the chat and shows no Close out section, while a coding task is unchanged;
- "Working on this…" folds the steps, and an agent's question shows in plain words.

The walk table must still pass, because Send and close drives the walk.

## After the builder check

**The owner's answer.** Mark done and close-with-a-note move to **the agent section's side strip**, the place Close out's strip held
(`useSpineVerbs`: `close = sec === "agent"` for a non-coding task). The walk's behaviour is unchanged, and the summary's "Nothing
left to do" lights the strip's Mark done.

**Calls by the spec's author (not the owner's):**
- **Aside mails and freshness:** `verdicts.context_moved` skips mails whose verdict put them in `aside`. A thanks mail does not mark
  the draft stale and does not redraft it on Send. Every other mail does, as today.
- **The bank-credentials case** is TQ-1258 in the owner's live home. The builder reads it read-only (sqlite `mode=ro`, with
  `TASKUARY_HOME` set before any import; importing-server-migrates-live-home). Only its shape goes into the repo, the eval and the
  commit messages.
- **On you has one owner.**
  - Before any agent turn, triage's `thread.on_you` is drawn as text in part 1, and no checklist item is made.
  - The agent's `SUMMARY` `on_you` creates the checklist items. Each later summary replaces the unticked ones and never touches
    the ticked ones.
  - On a task no agent will run (a draft-only reply), triage's `on_you` creates the items instead.
- **Non-coding** means the task's workspace is general (`workspaceMode === "general"`), the switch that already picks the chat over
  a terminal. A task that becomes coding mid-way (a hand-off, or Developer mode turned on) draws `[from, agent, close]` from then on.
  The chat's summary then stops drawing draft cards, so a draft always has exactly one home.
- **The phone is out of scope for now** (the owner, 2026-11-04: "let's not worry about the phone now"). It keeps today's close-out
  flow.
- **Keep-warm applies only where the CLI supports a long-lived process** (Claude Code's streaming input, for example). Other brains
  and the backup-provider fallback keep today's resume-per-turn. It is its own phase (5), measured before and after.

## Left to the builder

- the wording of the triage prompt for the thread fields and of the agent's new goal;
- the exact `SUMMARY:` format;
- the keep-warm grace period;
- the event lines' copy;
- the layout inside the chat;
- how a long thread is cut to fit triage's prompt.
