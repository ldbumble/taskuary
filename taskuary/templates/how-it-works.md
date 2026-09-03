# How it works

Reference, not settings. Nothing on this page is edited — it describes what the app does with a
message, in the order it does it, so you can tell where to put an instruction and why something
landed where it did.

## The Assistant tab

Two halves, one job: what needs you, one thing at a time.

**The pipe** (left) is everything that could need you, ranked — not the order it arrived in. New
things fall in at the top and slide to their slot; the bottom of the funnel is what comes out next.
The lanes, in the order a sharp assistant would raise them:

| lane | what it means |
|---|---|
| **agent waiting** | an agent stopped and is waiting on you — it is blocking work, so it comes first |
| **coming up** | a meeting inside two hours, or mail from a sender you marked urgent |
| **reply pending** | a reply or an action is drafted and waits for your yes |
| **asked you** | a person asked you for something and nobody is on it |
| **slipped** | the ask that went unanswered, the promise you made, the thread gone quiet |
| **landed** | a report you set up arrived; an agent finished a job |
| **fyi** | a person told you something — read it or don't |
| **agent working** | in hand: nothing for you until it stops or asks. It rides above the funnel |

The pipe is **unread**, the way an inbox is: showing something in the chat is reading it, and read is
gone. What is still on you comes back on its own — a draft you skipped, an agent still parked, a
follow-up nobody chased. Two knobs bound it (Settings → Assistant): how far back it reaches, and how
much it holds at once. A task's number shows small on its row, and a row that stands for several
messages on one thread says so (`+2`).

**The chat** (right) is Taskuary. It surfaces, it does not work: triage has already judged every
item, the coding agents and the responder do the doing. Under each line is the card that acts —
approve and send, answer the agent, hand it to the coding agent, not ours, done, later. Every button
is a door that exists elsewhere in the app; the chat only puts it under the sentence just said.

Say things in plain words and they are carried out, with a receipt saying what happened:

- **next · done · later · tomorrow** — move the walk on
- **reply and tell them X** — the gist rides into the draft
- **approve** — the drafted reply goes as it stands
- **not ours · never again · that sender is noise** — filed, and the verdict written down
- **remember that X** — kept as a note
- **send it to the coding agent** — a task, an agent on it, and a link to it
- **close it** — the task closes (a draft still waiting on it is dismissed first)
- **stop the agent · wrap it up** — the session ends; wrapping also files the report and closes
- **split it** — one arrival that is two jobs becomes two, each with its own number
- **skip all the X from Y** — the ones here are marked read AND a standing rule is written
- **set something up** — a walk-through with the assistant, no code, nothing built

A question is answered, never acted on. A correction is taken, never answered with "next".

## The gates every message passes

Deterministic first, always. A document only decides *what a message is*; every switch, policy,
verdict-on-thread and pipe rule runs outside the model — before it and after it.

1. **Seen before?** A message with an id we already hold is dropped here.
2. **The connector's own switch.** A source set to *feed* lands on the Timeline and nothing else
   happens: no triage, no AI call, no task. GitHub's "use as tracker" and "may reply" are the same
   class of switch, and they win over everything below.
3. **Your policies** (Settings → Policies). Skip, ignore, escalate or draft, matched on a keyword, a
   sender, a domain, a no-reply address, or a first-time sender. Before any model runs.
4. **Your verdict on this conversation.** "Nothing to do here", said on a thread, holds for that
   thread: its next message is filed, not re-judged. A verdict about a *sender* or a *topic* is
   deliberately not a veto — it becomes evidence at step 6 instead, because the same person asks new
   things.
5. **Shortcuts that need no model** — a calendar invite, a tracker notification, obvious noise.
6. **Triage** (`TRIAGE.md`). The only place words decide. It reads: your `TRIAGE.md`, `SOUL.md`,
   `LEARNED.md`, the standing notes that bear on this sender or topic (two agreeing verdicts become
   binding), and the facts around the message — who it was addressed to, who else has replied, the
   prior mail on the thread, what the assistant already said about it, and a report's own brief. It
   answers two things: **is there work** (task / reply / fyi) and **who does it**
   (`coding` an agent, `general` a conversation, `task` your own list).
7. **Gates on the answer.** A stranger's first mail never auto-starts an agent. A reply always enters
   Review. A thread already belonging to a task joins *that* task — never a third one that merely
   looks similar; if its task has closed, the reply is new work.
8. **The pipe.** Marketing, filed items and your own sent mail never enter. Your window and cap bound
   it. Your **standing rules** ("stop showing me the MFA financial reports from Nechama") hold a whole
   family back — quiet lanes only, so anything that actually asks you something still reaches you.

## Where an instruction actually lives

Four homes, and the difference matters:

- **A setting or a connector switch** — deterministic, wins over everything. *"Turn PRs into Timeline
  items, not tasks."* Ask in the chat and Taskuary puts the switch in front of you to approve; it
  never changes one itself, and only routing and visibility switches can be proposed at all.
- **A policy** — deterministic, per sender/keyword/domain: skip, ignore, escalate. Settings → Policies.
- **A standing rule** — deterministic, applied to the pipe: a sender plus the words that name the
  family. Written when you sweep with a reason, or when you say it in advance. Nothing is deleted;
  everything stays on the Timeline.
- **A memory note** — *evidence*, shown to triage, which judges how alike the next message really is.
  This is the one that argues rather than filters: it is how "resident refunds are not ours" teaches
  the classifier without hiding the one refund thread that does ask you something.

If you tell the assistant something and nothing seems to change, this is the list to walk: a note
persuades, a rule filters, a switch decides.
