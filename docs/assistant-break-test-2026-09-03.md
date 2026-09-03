# Breaking the Assistant — 2026-09-03

Goal: does the Assistant tab triage everything coming at the owner all day, hand it off, and bring the human
in only for approvals, reports, issues and agent mistakes? Three passes, all on scratch homes, never the live
7787 instance:

1. **Phrase × item matrix, no model** (`docs/break-test/probe.py`): one of every pipe item (draft reply, held
   coding ask, general ask, fyi, report ok/FAILED, agent parked on a question, meeting, proposed action,
   assistant idea) × 71 owner phrases, replaying exactly what `AssistantView.decide()` does with the server's
   decision and diffing the receipt against the real effect (tasks, reviews, message status, funnel state).
2. **Flows, no model** (`docs/break-test/probe2.py`): cold start, the fyi batch, a setting asked mid-walk, later/skip, lookup,
   close/not-ours/done under a live agent, the dead end when everything was shown.
3. **A real day** on a scratch server (`--port 7793`, Claude CLI as triage + concierge brain, a real coder in a
   scratch git repo): 13 arrivals through `/api/ingest/push` (colleague coding ask + follow-up, stranger
   question, two fyi, a newsletter, a general ask, a Teams outage, an OOO, a two-ask mail, a WhatsApp burst),
   then two puppeteer walks through the Assistant tab (`docs/break-test/ui.mjs` + `scn1/scn2.json`; screenshots were in the session scratchpad,
   not kept).

The coder did its job (fixed `export.py`, added tests, committed, honoured the follow-up about two decimals),
triage's verdicts were sensible, and wrap → report → drafted reply → Approve card is the best moment of the
product. Everything below is what broke around it, most severe first.

## A. Wrong target, data lost

1. **"Not ours" about one thing deleted another task.** With Chana's export reply on the table I typed
   *"not ours, facilities handles the portal"* (meaning the Teams outage). The verb applied to the item on the
   table: her message was filed, `/api/messages/{mid}/file` → `_drop_task` **deleted TQ-0002** — the finished
   coding task, its CODER REPORT, the commit reference and the drafted reply. No undo, no confirmation. Later
   the assistant explained the filing as "triage filed it as fyi". Same shape for every verb: the owner's words
   name a subject, the page acts on `current`. `off_subject()` only guards replies that name a TQ ref.
   *Fix:* when the words carry a subject/sender that is not the current item, resolve it (lookup) or ask;
   never file/delete a task-backed item from a sentence that mentions something else. Filing a message whose
   task has a coder report or a live agent should archive, not delete.
2. **Negation/phrasing blindness files real work** (`concierge._SAYS`, order matters): *"don't ignore this
   one"*, *"leave it open"*, *"leave it with the agent"*, *"let them know we will fix it by Friday"*, *"tell
   them to ignore it"*, *"reply: not ours, sorry"* all match `not_ours` (`ignore (it|this)`, `leave it`,
   `let them`) before `reply` is tried → the message is filed and its task deleted. *"remember to reply to
   him"* becomes a memory note. *"approve and remember that X"* drops the memory. *"can you check if the
   report ran?"* → a coding agent is dispatched on the mail (a question became a coder job).
3. **Approving a review that has no draft** (auto-draft off, or the AI draft failed) sends nothing, marks the
   review approved and **closes the task** (`verdicts.decide`: `final` empty → no send;
   `_settle_task_after_sent_reply` still closes a `reply` task). The person never gets an answer and nothing
   remains in the pipe. The chat says "Sending it as drafted."
4. **Approve twice sends twice.** `verdicts.decide` has no already-decided guard: "approve" typed + Approve
   button clicked (or a double click) = two emails.
5. **"close it" from the chat leaves the agent running.** `concierge.close_task` → `store.update_task` only;
   the PATCH route stops the live session, the chat road does not. "done" on an agent item settles the row
   and touches neither task nor agent.

## B. The receipt says one thing, the page does another

The server receipts the verb before knowing whether the card can carry it out
(`say()` → `RECEIPTS[verb]`); the page then refuses or errors, so two contradicting lines land in the chat:

| said on… | chat line 1 | chat line 2 |
|---|---|---|
| "approve" on anything but a review (8 kinds) | Sending it as drafted. Moving on. | I could not do that from here… |
| "rerun it" on anything but a report (verified live on TQ-0007) | Queued the rerun… Moving on. | I could not do that from here… |
| "close it" on fyi / report / meeting / idea | Closing the task. Moving on. | I could not do that… |
| "remember that X" (every kind) | Remembered. **Moving on.** | nothing moves — `decide()` returns before `done()` |
| "send it to the coder" when dispatch fails (422/agent gate) | Sent off to the coding agent… | red error banner, item stays |
| "approve" when the send fails (no connector) | Sending it as drafted. Moving on. | review back to pending but already "read" → gone from the pipe |
| "split it" when nothing to split; any `setting` mid-walk | nothing to split / switch proposed | `decide()` has no branch → `done(null)` marks the current item **done for good** |

## C. The walk gets stuck or lies about where it is

6. **Typed words never start or continue the walk.** With nothing on the table, "next", "done", "walk me
   through my tasks", "start with the mail" do nothing (no item → no decision); with a model they get prose.
   After an fyi batch the key is `fyis:…`, which `next_item` cannot resolve, so "next"/"done"/"not ours" are
   dead until a button is clicked. After "Nothing new. N things I've shown you still wait… say later", saying
   later does nothing.
7. **NEXT pill ≠ Next button.** Read is gone (`funnel_state surfaced`), agents return only after
   `BLOCKED_AGAIN_MIN` = 30. A new chat + "Walk me through my tasks" surfaced two fyi while the parked coder
   row wore the NEXT pill (shots2/02). The blocked agent — the thing that blocks work — was skipped for lunch
   plans.
8. **"skip it"** → `clear` sweep with no match → "Nothing in the pipe matches those words. Moving on." and
   nothing moves. "archive it", "delete it", "snooze it" do nothing; "remind me tomorrow" → 3 hours.
   yes / ok / sure / go ahead / do it are not verbs — without a model the owner cannot say yes.
9. **The model answers the wrong item.** "is it done?" about the coder → "Yes — both FYIs… They're done."
   "what's left?" → "Two more… one needs your yes, one is fyi" with 6 in the pipe and a blocked agent omitted.
   "close it" with nothing on the table → "Done. Yosef Adler - Hey is closed." (TQ-0007 still open).
   "remember that Dovid handles the badge printers" (nothing on the table) → "Got it." and **no memory row**.
   "make the reply shorter" → "Done. Here's the tightened version: …" — the draft was untouched and the
   next "approve" sent the long one. There is no redraft verb; the model claims the edit.
10. **The CLI concierge breaks character.** Claude CLI on haiku answered "next" with *"I understand the role,
    but I don't have the queue data"* and "yes go ahead" with *"I'm in Claude Code… I don't have access to the
    systems Taskuary would need"* — twice, in the owner's face (shots1/03). The voice model must never be able
    to say that; if the CLI is the voice, the answer needs a contract check and a fallback to the facts line.
11. **Answering an agent by words has no road.** "tell the agent yes", "answer the agent: yes remove them",
    "yes remove them" → model prose / `reply` (drafts an EMAIL to the sender carrying "the agent: yes…") /
    `clear`. Only the card's Answer box reaches the pty.

## D. Triage and the pipe

12. **WhatsApp "hey" became a reply task with a drafted "Hey — what's up?"**; the real ask two lines later
    ("did the invoice for Oak Ridge go out?") attached to it, and the pipe offered the greeting draft for
    approval. The burst reader fired the task on the first line.
13. **One conversation, several rows.** A pending review does not claim its thread in `from_feed`, so the
    older mail on the same thread shows again as "asked you" (TQ-0002 twice after the wrap; Yosef three
    times in the All list). The walk showed Yosef twice.
14. **A stopped agent's task shows "agent working" forever.** `working_tids` counts `running_runs()`; the
    stop endpoint leaves the run row, so TQ-0006 sat in the working lane with no session, "nothing for
    you", and TQ-0005 (outage, agent stopped) vanished from the pipe entirely: not read, not offered, not
    findable by "what about the payroll portal outage?".
15. **Fresh install day one = three junk reports** ("(AI prompt set, but no active AI connector - raw data
    below)") surfaced one per turn, though the triage brain was a CLI. Reports should not run without a
    brain, or should not enter the pipe when they say so themselves.
16. **An outage report from Teams was auto-dispatched to a coding agent in a repo** ("payroll portal is down…
    who can look at this??" → coding → coder session in export.py's checkout). Err-toward-coder is the rule,
    but an agent in the wrong checkout cannot investigate a portal; the reply/escalate road was right.
17. **Two asks in one mail were not split** by triage and "split it" on it said "only one ask" (the fast
    brain missed it), then settled the item as done.
18. **Sweep rules key on the wrong words.** "skip all the fyi from Chana and Dovid, I don't need those" wrote
    rules `dovid from dovid@ours.com` and `fyi from chana@ours.com` plus a sender memory on Dovid.

## E. Agents

19. **First dispatch into a new checkout parks on Claude Code's trust dialog**, then on "Allow external
    CLAUDE.md imports?". Three auto-started coders sat "waiting on you" with an empty tail and the chat card
    shows the terminal theme toolbar ("Catppuccin Mocha Dracula…") instead of the question. Pre-trust the cwd
    (`~/.claude.json` projects) or launch with the flags that skip it, and surface the last screen lines as
    the question.
20. **The coder finished and never said so.** `coder.md` "Closing out" (line 27: *you do not write a wrap-up…
    when John clicks Done*) contradicts "Finishing" (line 82: *run `taskuary --done`*). The model obeyed the
    first: job done, committed, parked at the prompt, task in_progress, pipe says "agent waiting on you". The
    owner has to guess it is finished and say "wrap it up".
21. **Rendering the terminal pane resets the watcher.** Mounting the agent card ("restoring the session…
    connecting") produced output, idle reset, and the card flipped to "THE AGENT IS WORKING AGAIN" for an
    agent sitting on a dialog.
22. **"Set something up" starts an agent that immediately interrupts.** The walkthrough task (TQ-0009) opened
    a general agent session, navigated away from the Assistant tab, and 60 s later the By-the-way bar said
    "assistant stopped on TQ-0009 and is waiting on you".

## F. UI

23. At 12 items the top two-thirds of the pipe column is empty wall; rows crowd the mouth with titles cut to
    one letter ("coder T…") behind the ref and NEXT pill (shots1/01).
24. The welcome line counts "9 came in, 3 landed, 2 fyi" but not the three agents waiting — the only lane
    that blocks work.
25. Five alerts queue behind one By-the-way bar; three "coder stopped on TQ-000x" in a row.
26. Chats are titled by the first typed word ("next", "is it done?").
27. A hand-raise toast for a task that had been wrapped and then deleted ("TQ-0002 · coder stopped").
28. Mobile: the pipe is hidden (0×0) with no visible affordance in the first viewport; the chat works.

## What holds

Triage verdicts on the 13 arrivals were right (fyi/promo/OOO filed without a model where possible, reply vs
task vs general sensible, follow-up attached to its thread, colleague auto-worked, stranger held). Wrap → CODER
REPORT → drafted reply with the agent's summary → Approve & send is coherent and reads well. Sweeps by sender
mark read and write a rule. `later`/`skip` return at 3 h / 07:00. A failed send puts the review back to pending
with the reason on the task. Not-ours on a task with a live agent does close the session (`_drop_task`).

## Suggested order of work

1. Guard the destructive road: never `file`/delete from a sentence that names another subject; confirm before
   deleting a task with a report or agent; approve refuses an empty draft and a non-pending review.
2. One truth per turn: the page reports what it did (or could not), the server stops pre-receipting verbs it
   cannot see through; `decide()` gets explicit branches for `setting`/`split`/`remember` and never falls
   into `done(null)`.
3. Fix `_SAYS` ordering and negation (reply/let them know/tell them before not_ours; "don't"/"leave it open");
   add verbs the owner actually uses: yes/ok/go ahead (= the card's primary), answer the agent, redraft,
   forward/assign to a person, delete/archive, remind me tomorrow.
4. The walk from words: "next"/"done" with nothing on the table surface the next item; fyi batch keys resolve.
5. Pipe truth: review rows claim their thread; stop clears the run row; a stopped agent's task comes back as
   "asked you"; blocked agents come out first in a new chat.
6. Agents: pre-trust the cwd, one finishing rule in `coder.md`, surface the last screen as the question.
