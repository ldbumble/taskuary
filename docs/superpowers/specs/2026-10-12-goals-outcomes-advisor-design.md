# Goals, the outcome ledger and the Advisor on two clocks

*2026-10-12. Decided in conversation with the owner; this is the record. The design canvas with the
mockups is at https://claude.ai/artifact/MYRd7HArdcJ8nEAkpgjpWD (seven boards: the rail and the New
sheet, a goal on the stage, memory today versus the ledger, the Advisor on two clocks, one object, the
suggestion in the walk, what was not followed up).*

## The three brains, and the hands

Taskuary runs three always-on headless brains. The owner talks to one voice.

| | What it does | What it reads | Clock | Acts? |
|---|---|---|---|---|
| **Triage** | judges each arrival: task, goal, reply, fyi, ignored; attaches it to the task or goal step it serves; names the profile, playbook and repository; assigns the worker | TRIAGE.md, SOUL.md (2,500), JOB.md (2,500), LEARNED.md promoted lines, routing memory, the playbook menu, recent open tasks and goals | on every poll | makes rows; never sends |
| **The assistant** (concierge) | the voice and the hands: walks the rail, runs the set-up walk, connects things, moves things (assign, route, close, later) through deterministic buttons or by asking the model for the verb | COUNSEL.md, SOUL.md, JOB.md whole; the one item on the table; the Advisor's attached line | on a turn | moves things; never does the work, never proposes |
| **The Advisor** | the brain: says what should happen next on each item, what the owner usually does, what was not followed up, which step a mail serves, what worked, which system is worth connecting | everything: LEARNED.md whole (hypotheses too, since it proposes and does not act), the outcome ledger, the dossier, JOB.md, SOUL.md, playbooks, the knowledge base, the calendar, schedules, mutes | two: on the event, on the clock | never; it leaves a line, a chip, a proposal or a row |

The **workers** (coder, general agent) are the fourth kind and not always on: they do the work a task
names, in a session the owner can watch. The Advisor is the manager, so to speak: it proposes work and
says what is late; a worker does it; the assistant moves it; triage sorted it.

From the owner's side the assistant and the Advisor are one thing. COUNSEL.md is the voice for both;
nothing on screen says "Advisor". The split is a prompt-budget split: the heavy reader works off the
request path and leaves one sentence on the item, and the voice that speaks on a turn reads that
sentence and the item, nothing more. It never recomputes what the Advisor computed. "Why?" is
answered from the line's evidence ids, a lookup, not a think.

## Goals are tasks

A goal is not a new object. The difference that matters is not duration: a long task has boxes that
are themselves tasks, owned by different people and agents, and a date that can slip.

**Three additions to the task table:**

- `DueAt` and `DoneWhen` on a task: the date, and the sentence that says when to stop ("the nightly
  census lands in the new ledger for all three sites and the old export is off").
- a checklist box may carry a `TaskId`: the box ticks itself when that task closes. A task whose
  boxes are tasks is what the rail calls a goal. Same number series, same card, same row.
- a **person** is a valid assignee beside the agents. "Ray will send the schema" is a task assigned to
  Ray with the date he said, in the waiting-on-them lane. "I'll get you the numbers Friday" is a task
  on the owner with a date. A promise is a task; the promise ledger as a separate thing goes away,
  and the chase ladder becomes what the clock pass does to any task in that lane past its date.

The gate on volume carries over from the promise producers: a promise is a task when it names a
thing and a time, or when the owner said it. Softer words stay in the thread.

**Where a goal comes from.** The New sheet's fourth tab, **Set a goal**, beside Send something, Give
an agent a job and Note to self. Three questions, not a form: what done looks like, by when, who is
involved (people it may chase, systems it may touch). Then the same two-card "and then" row: *Plan it
and show me* (the twin proposes the steps from mail and the connected systems; the owner cuts or
adds; it starts the first one) or *Track it, I have the plan*. Chat makes one ("make this a goal");
a task promoted this way keeps its number as step 1. The Assistant report proposes one when a task's
checklist spans several people and dates, or a subject keeps returning with "by" in it. **Triage**
makes one for the open-ended ask: no single deliverable, several people or systems, a date or none.
It makes the goal with no steps, and the worker's first job is to explore and propose the steps.
Kind memory and the router correct "that was a task, not a goal" on the same curve as any kind.

**On the rail: one row.** A goal is one row, named for the goal, with a project mark instead of a
mail or PR logo. It sits in a **Goals** band when it has news (slipped, chasing, re-planned, a step
finished), in **Later** when it is quiet or not started, with its date in the age gutter and the sub
line saying who it waits on ("5 of 9 · waiting on Gail's accruals, due Thu"). It is never gone until
done or paused. It climbs into On you only for a decision only the owner can make. Its steps fold
into its row ("3 of 7 · coder on step 5 · Ray owes step 4, chased twice · step 6 is on you") and get
a row of their own only in a lane that is the owner's move: on you, asked you, agent waiting, ready
to close out. The band count counts the goal once. Next walks it as one item.

The row is a fact line, not a progress bar: n of m done, who is working or holding, how long, one
word in the word column (slipped, on track, not started, needs you).

**On the stage: the task card, stretched.** Kicker ("goal · slipped"), title, "by Dec 1 · 3 of 7 ·
re-planned once", three facts (done when; stuck on; the twin's next move), the steps as a list with
owner and state pointing at their task ids, one bar (Nudge Ray, Close step 3, Move the date,
Re-plan, Pause), then "if you do nothing: I chase Ray again Monday and on Wednesday propose Dec 8",
and the history line. Each step opens: the checklist (the same boxes the task card ticks), what was
done (witness facts for an agent step: tool in hand, files, said-versus-did, last test line; for a
human step: the mails sent, when read, who was copied), and a stuck line when the step cannot move
on its own. The two open by default are the one the twin is on and the one that is stuck.

What the twin does with a goal: starts the next step when the one before it clears; chases the
humans on their per-person ladder; re-plans when a step slips and says so; raises the goal to On you
only for a decision.

**Which step does this serve.** An arrival attaches to a task today only by thread. A long task
gets mail on other threads that serve one of its steps (Gail's accruals, Marcus's confirmation).
Triage gets one more field: which open task, and which step, this serves, judged from the task's
done-when and its step titles. The arrival shows under the step ("↳ Gail sent the accruals Tue
09:40"), the step may tick itself, and the Advisor's line says so. The owner's correction is routing
memory on the repository edge's curve.

## The outcome ledger

Every store that remembers today is written from the same signal: a click or a sentence from the
owner, at the moment they give it. SOUL/JOB/STYLE/TRIAGE say what they say; LEARNED.md is what they
do when they correct; the memory notes, routing memory, operation and correction tables, the dossier,
the playbooks, the knowledge base and the audit all stop at the moment of the verdict. Nothing
records what the owner did next, or what the world did after the twin acted. The twin learns to
please; it cannot learn to be right, and it cannot notice the owner's own habits.

**One new table**, `outcome`, beside `operation` and `correction`: one row per action the twin took
or proposed. The action and its target (an operation id where one exists, else the audit row), the
owner's next move and how soon (continue-session "merge it", 2 minutes later), the outcome, when it
was resolved, and a verdict.

| action | target | next move · outcome, resolved by | verdict |
|---|---|---|---|
| coder stopped, PR open, CI green | TQ-0712 | continue "merge it" 2 min later · merged, not reverted in 14d | held · habit 8 of 8 |
| reply sent, approved as-is | Erin · "AP cutover" | nothing · no further mail in 7d, task stayed closed | settled |
| reply sent, approved as-is | Payworth billing | nothing · 4 more rounds, each asking for the PO | unsettled: draft lacked the PO |
| chase (day 5) | Ray · schema sign-off | nothing · delivered day 9, after the second chase | kept, late |
| task closed by the agent | TQ-0704 | nothing · reopened 3d later by a mail from Gail | reopened |
| CC added on a chase | Omar · refund thread | nothing · decision the same day; 3 chases without him got nothing | moved it |
| ignore rule applied | newsletter sender | nothing · no promotion, reply or mention in 60d | no regret |

**Resolving an outcome is bookkeeping, not judgment.** "Did more mail arrive on the thread", "did
the task reopen", "was the PR reverted", "did the person answer and when" are facts already in the
store; a nightly sweep records them. What the facts mean, and what to offer because of them, is
always the model: at reflection as today, and on every event through the Advisor.

**Reflection distils into the stores that exist**, with LEARNED.md's grammar (`[s:N | ev: ids |
seen | k:]`), its decay in reflections, and its promoted-only rule before a line rides into a prompt:

- habits about the owner go to **LEARNED.md** as a new evidence kind ("green PR from the coder: you
  merge it, 8 of 8"; "the agent asks 'open the PR?': you always say yes");
- facts about other people go to a **page per person** (the 2026-08-28 company-brain verdict, never
  built): "Ray answers in 3 days median and needs a second chase"; "refund threads move the day Omar
  is on CC"; "Payworth needs the PO in the first mail". This is the real org chart, derived;
- facts about kinds of work go to the **playbook** they belong to, as a proposal, like playbooks are
  filed today ("closing from a thread with an open question reopens 40%; ask first").

**The one rule.** A derived line never acts on its own. It changes which button is primary, what a
proposal says, what triage weighs, which day the chase goes out. Autonomy stays a proposal the owner
clicks, and it carries the one number it never had: the regret count. "Stop offering" on any line
writes the opposite evidence; the habit decays like every other line.

## The Advisor on two clocks

One Advisor, two entry points into the same module, same brain setting, same voice. Not a second
thinker that could disagree with the first.

**On the event: the shadow.** Runs when one item changes and lands on that item. The triggers are
the events the app already sees: an agent stops or asks (the hooks, the stopped lane, the By the way
strip), a PR opens, a reply arrives on a watched thread, a task closes, a goal step slips, a report
lands, the owner presses something.

**Always the model, never a word match.** This is the rule every door in Taskuary lives by (the
owner, 2026-09-06 and again 2026-10-12): the model reads intent and returns the verb, code validates
the verb against the actions it has, and nothing routes on a hardcoded match. The Advisor is no
exception. On every event it runs one small prompt on the light gear: the event, the item's facts,
the promoted lines, and the ledger facts that bear on it. It answers with a verb from the action
vocabulary and a line, or nothing. Code checks the verb exists and builds the pill from it; the fact
beside the pill ("8 of 8") is read from the ledger, not written by the model. For the item on the
table or next, the dossier and the ledger rows join the prompt: the same model, a bigger read, one
suggestion or nothing. Everything runs in the background after the event.

Event findings are **never rows**. They attach to the item they are about and surface when the walk
reaches it. That line is what keeps the rail from filling with advice.

**On the clock: the watchman.** Unchanged. The seeded Assistant report runs on its schedule and the
morning brief, and reflection runs when corrections or outcomes are queued. It finds what only a
window shows: a promise gone quiet, a slipped thread, a task nobody touched, a goal with no movement,
a system the owner keeps getting mail from and has not connected, what worked this week. Its findings
are **rows**, judged like any arrival (fyi, or asked when they need the owner), because a forgotten
task is work waiting on the owner and belongs on the rail where Next reads it in turn. Nothing fires
for absence; something has to look.

**Cost gates.** The gates are on *when* the model runs, never on *whether*: only on a state change,
one per item per revision, the light gear, a small prompt, the bigger read only for the item on the
table or next, a per-hour cap, and silence when it has nothing to say. An event-driven Advisor that
ran a full read on every stop would be the per-message brief the owner killed in August; the small
prompt and the per-revision rule are what keep it from coming back.

**Speed gates.** Everything runs after the event, off the request path. No button waits on the
model; a Next press stays a pile rebuild. A suggestion that misses its moment is dropped, not queued.

## Surfaces: how it reaches the owner without touching Next

The walk is the spine. Suggestions ride on it, in one place that already exists: **the prompt box**.
The ghost text says what the owner usually does ("You usually merge it here. Tell me what to do
with it, or press…") and a **pill** where the send arrow sits does it: "Merge it · 8 of 8 times".
Typing anything brings the arrow back; Enter on an empty box does nothing; only the pill, or the
owner's words, act. The pill does what the card's primary button does, through the same proposal
and the same receipt. When there is nothing to say the placeholder is today's. The chip row under
the card stays Next, Done, Later, Tomorrow; the suggestion is never a chip there as well (the owner,
2026-10-12: "why is it in two places?").

The pill is usually there when the card is, because the Advisor ran when the item changed. One that
lands later fills the same box without moving anything. No popup, no new strip, no new row.

**About another item:** the By the way strip, which already exists for an agent waiting on the owner
and already has the rules: it waits for a gap, one line at a time, replaced rather than stacked,
Later holds it. "The coder asked on TQ-0712 whether to open the PR. You have said yes 5 of 5 times.
Answer yes for you?" One click and it is an earned-autonomy proposal with its evidence attached.

**The assistant's opening sentence** on every card stays the assistant's: what arrived and what is
asked. The Advisor's line adds what to do about it and why: the habit, the person fact, the thing
someone sent that belongs here. Written by the model; the numbers in it are the ledger's.

**What was not followed up.** The clock pass finds it against the promoted people facts (day 3 is
late for Ray, day 5 for someone unknown) and it lands in the existing slipped lane inside On you,
ranked by how late and how much it matters by JOB.md. The pipe count says "3 slipped". When Next
brings it up the card is the thread: what the owner asked, when, that it was read, the silence
since; the chase is drafted in the owner's voice with the CC the ledger says moved things. The
prompt box: "Ray has been quiet 5 days. Say let it go, he called, a day to ask again, or press…"
with the pill "Chase Ray, copy Omar · Omar got an answer the same day, 2 of 2". Four
answers, each an outcome: **Chase** (same proposal and receipt; the ledger later records how long the
answer took), **Let it go** (the promise closes as dropped; three on one sender and the Advisor stops
raising them), **He answered elsewhere** (the owner says where; the step ticks), **Later** (a date).
A reply arriving is an event: the row goes and the step ticks without the clock pass. Several late
at once sit on the table as one batch, like fyi, with one chip ("Chase all three"); the owner still
answers each. The morning brief carries the same facts one line each and says they are first on the
rail.

## Mechanics: what touches the rail

The owner's worry is that advice changes the rail's order or slows the walk. By construction it
cannot do either.

1. **The event.** The hook fires; the processing pass moves the item's lane, as today.
2. **The Advisor, in the background.** One small prompt on the light gear: the event, the item's
   facts, the promoted lines. It returns a verb from the action vocabulary and a line, or nothing;
   code validates the verb. It writes one **advice** row for the item: the line, the verb (a
   proposal), the evidence ids, the item's `context_revision` (the stamp a proposal already carries
   so a changed item refuses a stale confirmation), the model and cost, and what was dropped: an
   answer no verb matched, or a run a gate skipped.
3. **The rail build is unchanged.** It reads lanes, ages, urgency and the worker signature. It does
   not read advice. The pile cache stays what it is.
4. **The stage render** joins the advice for the key on the table: one lookup. Revision mismatch
   means nothing is shown; a reply arriving moves the revision and the old pill vanishes with no
   cleanup pass.
5. **When it lands**, the live-events push fills the prompt box, whether the card is already up or
   not. Nothing moves. Missing its moment, it is dropped. The bigger read, with the dossier and the
   ledger rows, runs only for the item on the table or next.
6. **The pill** is the card's primary button: the same proposal, confirmation and receipt. The
   outcome row opens, resolved later.

What can move a row is what moves it today: lane, age, urgency, batch, the shown mark, a return
date, a task fact set by the clock pass (late, slipped, a step's state), a clock-pass finding filed
as an idea row through triage. A goal's band comes from task facts only: `DueAt`, its children's
lanes, a step's late fact. An event-path suggestion never moves a row, and no door exists for the
Advisor to promote or demote one. One suggestion per item per revision; an empty Enter does nothing.

The test that pins it: build the rail with and without the advice table populated and assert the
two orders are identical. If that test ever needs an exception, the design has leaked.

## Seeing the Advisor's thinking

The owner can pull up what the Advisor did on any item from the assistant: the history control on
the stage (the clock icon) gains an **Advisor's notes** section for the item on the table, and
"why?" in chat opens the same thing. It is a receipt, not a transcript: what it looked at (the
promoted lines that matched, the dossier facts, the ledger rows, with ids), what it decided (the
line, the chip, the proposal) and what it dropped and why (a line below threshold, a tier 2 call
skipped by a gate, a suggestion that missed its moment). Each clock pass keeps the same record per
finding. Stored beside the attached line, in the store, not in a document; readable from the
Assistant report's row on the Reports tab for the clock pass, and from the item for the event pass.

## Build order

1. The three task additions: `DueAt` and `DoneWhen`; a checklist box pointing at a task; a person as
   assignee. Promises become tasks; the ladder reads the lane. The Goals band and the Later rules.
   The New sheet's fourth tab. The goal card with its opening steps.
2. The `outcome` table and the nightly resolution sweep. Reflection reads it and writes habit lines
   to LEARNED.md with the new evidence kind.
3. The Advisor's event entry point (the small prompt, the verb vocabulary, the advice sidecar, the
   gates) and the prompt box's ghost text and pill; the Advisor's notes receipt.
4. Per-person pages from the ledger; the per-person chase ladder; the slipped interaction with its
   four answers.
5. "Which step does this serve" in triage; triage's goal kind; work facts proposed into playbooks.

## Kept in mind: earned autonomy

Out of scope for this build, but every piece is shaped so it needs nothing new (the owner,
2026-10-12: "if the Advisor sees something always being done the same as always, it should be able
to do earned autonomy as well"). The ledger counts the habit and its regret; the advice sidecar
already carries the verb and the evidence; the proposal path already exists. When a habit line's
evidence passes a bar with no regret, the Advisor's answer on the next event is a different verb:
not "offer Merge it" but "propose doing it myself". That lands as a proposal the owner clicks, is
revocable from the same line ("stop"), and runs through the same operation and receipt. Nothing in
steps 1 to 5 should make that harder; a field that would (a pill with no verb, an action with no
proposal) is the design leaking.

## Left out, on purpose

- Autonomy itself: see above. The proposal is designed in its own spec.
- A separate Advisor model setting. The clock pass uses the Assistant's (one tier over the light
  gear); the event path uses the light gear.
- A Goals page. A goal has the card and Open, like a task; a page of its own waits until the card
  proves too small.
- Showing children on the rail. Decided against: one row per goal, children only when they are the
  owner's move.
