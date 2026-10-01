# Press audit — every press, on every item, on every surface (one-time)

**Status:** design approved by the owner 2026-10-01. One-time audit, not a maintained test suite.

## Why

Three bugs in one day had the same shape: a press did the right thing *eventually*, but what the owner saw
next was wrong or slow.

- Mark done on a task with a live session waited 18 s on an AI write-up, and meanwhile the row sat under
  For later (fixed ac051beb).
- A daily report run was filed onto yesterday's closed task and never showed (fixed 37f2c8c5).
- Clicking a rail row waited ~9 s on a mailbox poll before the item opened (fixed 9b3ea74d).

None of the existing harnesses would have caught all three: `tests/test_assistant_reactions.py` is server-side
only, `docs/break-test/` replays phrases but not buttons, and `website/browser/` covers ~10 flows. The owner
asked for one walk through everything — fake data, every press by item type, checking that the right thing
happens next, how fast, and whether an AI call runs after each click — plus questions to the Assistant checked
for the right context.

## What the owner decided

| Question | Decision |
|---|---|
| Purpose | Both layers: scripted passes for outcomes and speed, a real-AI pass for answer context. |
| Where "the right thing" comes from | Drafted from the owner's existing rules (the 2026-09-24 decision map, recorded feedback, today's fixes); every press with no rule, or two conflicting rules, is a question for the owner. |
| Shape | One shared press map read by a server pass, a browser pass and a real-AI pass. |
| Lifetime | **One-time.** The harness is throwaway (scratchpad); the fixes it leads to keep their own regression tests in the repo. |
| Must record per press | Speed, whether an AI call ran (and whether it blocked the screen), and what happened. |

## The fake world

Built fresh for the run from the demo data, invented people only (the stand-ins in CLAUDE.md). One of every item
type in every state that matters:

- mail: an ask, a reply-only, an fyi, a follow-up on an open task, a reply on a closed task, a burst of two in
  one poll
- chat: a line, a burst, an ask with no clock
- reports: a clean run, a failed run, a run the AI judge turns down, a run of a report whose earlier run became
  a task
- tasks: coding and general, each with no agent / working / waiting on the owner / stopped / session saved
- a meeting, an Advisor idea, a proposal, a broken connection, a For later item that is due back

## The press map (`presses.yaml`, scratchpad)

One row per **item type × surface × press**.

- surfaces: rail click, the card on the table, the action row, the Task page, Board, Wall, phone doorway,
  a typed message
- presses: Next, Mark done, Remind me / Later, Reply / Send, Approve, Draft with AI, Send to agent,
  Continue session, Stop / Save and end, Reopen, Split, Not a task, Open the original, plus each card's own verbs

Each row states what should happen:

- **effect** — task status, rail band (or gone), reviews drafted/sent/dismissed, agent started/stopped,
  read receipt
- **next on screen** — which item comes up, what the card and the strip say
- **speed budget** — e.g. row off the rail ≤ 300 ms, next item drawn ≤ 1.5 s
- **AI expected** — none, or which (triage / Assistant / write-up / drafter / judge), and whether it may block
  the screen or must run after
- `rule: ?` when no rule exists or two conflict — these become the owner's question list

## The trace (every press)

- time from the press to each visible change (row left, card folded, next item drawn, strip updated)
- every AI call the press caused, recorded at the one seam every model call passes (`llm.build_llm`), tagged
  with the press: which brain, purpose, blocking or after, duration
- a before/after diff of tasks, rail (funnel/processing state), reviews and agent sessions

A row **fails** when the effect is wrong, a budget is blown, or an AI call blocks where the map says it must not.

## The three passes (in order)

1. **Server pass** — every row fired through the same endpoints the page calls, on the fresh world, scripted
   brain. Hundreds of presses in minutes. Catches wrong outcomes and blocking AI calls.
2. **Browser pass** — about 40 key journeys clicked in the real page (puppeteer, `website/browser.mjs`),
   timed to each visible change, screenshots on failure. Catches page-only bugs (a row lingering, jumping bands,
   a card not folding).
3. **Real-AI pass** — the same world with the owner's configured AI on fake data. About 10 questions per item
   type typed to the Assistant ("what's this about", "who asked", "reply saying yes", "what did the agent do",
   "what's next", off-topic asks). Each answer graded: the right item, the right task, the newest message, no
   other task's thread. Each AI call's prompt is logged, so a wrong answer can be traced to missing context
   versus a bad model answer.

## Safety

- A scratch `TASKUARY_HOME`; never the live home or its database.
- `claude.cmd` / `codex.cmd` shims on PATH that exit at once, so no real agent CLI can start (the scratch home
  adopts the installed Claude otherwise — recorded incident).
- Sessions in the fake world are plain shells or the repo's fake CLIs (`tests/fake_tui.py`, a Claude-Code-shaped
  painter), never a real agent.
- The real-AI pass reads the AI connection from a copied config and sees only the fake world.

## What the owner gets

One findings page (an artifact):

1. **The decision tree** — every press per item type drawn as a map, each press green / red / `?`.
2. **Findings, worst first** — press, what happened vs what should have, time, AI calls (blocking or after),
   screenshot for browser findings.
3. **The question list** — the `rule: ?` presses, answered once by the owner.

Then fixes in batches, each with its own regression test in the repo and the full suite before every push.

## Out of scope

- Keeping the harness running in CI or maintaining the press map after the audit.
- Real mailboxes, real chat providers, real agent CLIs.
- Visual design review (covered by the earlier UI audits).
