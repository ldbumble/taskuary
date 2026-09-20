# The agent pane and the "agent needs you" signal, audited - 2026-09-18

The owner asked for a deep dive: how a CLI agent's session is drawn on the Wall, the task page and in the
Assistant, and whether the "agent needs you" / "agent stopped" hooks hold up - pixel by pixel. Method: two
read-throughs of the code (rendering path, signal path), then a puppeteer walk over a `--demo` instance at
1600px and 390px, screenshots read back, the fixes below applied, and the walk run again.

## What was wrong and is now fixed (this commit)

| Seen | Cause | Fix |
|---|---|---|
| Tasks rail said **agent working** on TQ-0004 while the page header, the Wall cell and the toast all said the coder had stopped and was waiting | `ui.busyNow` read the run row's `running` before the live session's own `waiting` verdict | a live session speaks for itself; the run row decides only when there is none (`ui.jsx`) |
| Every pane read **"Catppuccin Moch"** - the palette name ended under the full-screen button | knob row at `right: 10`, SessionPane's button at `right: 6` on top | knob row at `right: 36`; the connection word (`connecting`, `exited`) rides in that row instead of a hardcoded `right: 130` |
| Wall cells grew a **full-height scrollbar over nothing** and parked the cursor at the very bottom | `replay_text` seeds the pty's whole rendered grid, trailing blank rows included; a 32-row pty in a 26-row cell is six rows of "scrollback" | trailing blank rows are dropped from the seed (`terminal.replay_text`) |
| **"Cannot read properties of undefined (reading 'dimensions')"** page error on a phone leaving the task page | a write's completion callback called `scrollToBottom` after `term.dispose()` | one `disposed` flag; every late callback (write completion, lift, onResize, visibilitychange) obeys it |
| Phone: the agent bar sat **on top of "Agent work"**, its last button off the card; the task strip's buttons covered "TASK" | `WorkflowHeading` and the folded task strip are single flex rows with a `flexShrink: 0` bar | both wrap below `sm`; the bar takes the whole next line (`order: 9`, `flexBasis: 100%`) |
| A permission granted in the pane also **closed screen-minted approvals** | today's `PostToolUse` closer matched every open `approval_needed` | only hook-sourced ones; a chooser the screen reader turned into a request stays open |
| **"Two frames at once"**: Claude Code's UI drawn in the top 32 rows with stale scrollback below, lines landing mid-pane; a real resize did not heal it and hiding/showing the pane was a coincidence (2026-09-19) | a session opens at the server's 32x110 and the page then fits ~60 rows. ConPTY keeps a grown viewport TOP-anchored (cursor on row 32, blank rows below) while xterm pulls 28 lines of scrollback in and moves its cursor to row 60; the CLI's next `ESC[32;..H` overwrites the middle of the pane. Measured: pre-sized 60-row session clean, default-size session broken | the `geom` frame says `conpty`, and the pane sets xterm's `windowsPty` option, whose grow is ConPTY's (blank rows at the bottom, cursor row kept). Behavioural test runs xterm's browser build under node (`terminalConpty.test.mjs`). `Term.resize` now logs the exception it used to swallow |

Earlier today, same area: a pane hidden behind another tab comes back repainted (`wasHidden` + `visibilitychange`),
and a pane being seeded is `working` whatever its screen says (`Term.seeding`).

## Verified after the fixes (demo, 1600px and 390px)

- Task page: rail chip `needs you`, header `coder needs you · agent · needs you`, pane intact after Tasks -> Assistant -> Tasks.
- Wall at 2x: three cells, `--sbar` = 0 on all, cursor at the end of the last line, first line `$ claude` visible, knobs clear of the button.
- Assistant: agent card opens from its rail row, no page errors.
- Phone: no horizontal scroll; strips on two lines.

## Still open - ranked

1. **One state, six sentences.** The same "the agent is parked at its prompt" reads `agent waving` (Assistant rail chip,
   lanes.json), `needs you` (Tasks rail, header), `coder stopped - waiting on you` (Wall, WorkPane), `coder stopped and is
   waiting on you` (toast, pile lead), `coder on TQ-0004 stopped at its prompt - answer it below` (chat), `parked at its
   prompt` (agent card sub-line), `⏸ coder is waiting on you — answer it` (Board). The owner's standing rule is one
   vocabulary in lanes.json. Sites: funnelPile.js:228, ui.jsx:1518/1747, BoardView.jsx:120, TasksView.jsx:1564,
   assistantCards.jsx:354, concierge.py:642, workerstate.request_line. Many tests pin these strings, so it is a deliberate
   pass, not a find-and-replace.
2. **A pty that exited mid-question says `input_needed` for ever.** `workerstate.status` ranks open requests above "not
   live", and `answer` refuses to deliver to a dead run. Not fixable by reordering (headless general work has no pty and
   legitimately asks) - it needs a real "this run ended" event from `Term.close`/`release_task`, which today write a run
   row and a transcript but no worker event. `disconnected` has no producer at all.
3. **Hook coverage.** `PreToolUse` (the actual permission decision), `SubagentStop`, `SessionEnd` are not installed
   (hooks.py EVENTS); permissions are seen only through the `'permission' in message` substring of `Notification`.
   `AskUserQuestion` is recorded asked-and-answered in one breath, so no surface can ever show the question itself.
4. **Four clocks.** `PHASE_DWELL` 3 s (terminal.py), `funnel.DWELL` 12 s, handraiseState's two-poll confirm (~16 s),
   `IDLE_WAITING` 45 s, plus hook latency. The strip can ring several seconds before the pile narrates the same thing.
5. **`NeedsYou` means two things.** processing_all sets it from `waiting` only when no review is pending; rowLane treats
   `AgentWaiting || NeedsYou` as `blocked`; timelineState says they are not synonyms. Rail and Timeline can classify one
   row differently.
6. **Pane geometry.** The FIRST session on a fresh install still opens at the built-in 32x110 and is grown by the pane that
   shows it - nothing has taught the app a pane size yet; every session after that one opens at the remembered size.
   A pane mounted while hidden can send xterm's default 80x24 as the pty size (`ws.onopen -> sendSize`
   is not gated by `usableTerminalBox`); a non-owner still sends one resize before the `geom` frame lands; A−/A+ in a
   non-owner pane changes the glyph but not the rows. Heights are unrelated magic numbers (640, 440, 360/420, 46vh, 38vh).
7. **Chrome nits.** The prompt-pending chip has no width bound (overflows a 4-across cell); theme/size are per-pane state
   with no cross-pane sync until remount; the handraise toast covers the Wall/task input bar's Queue button; the
   "ON THE TABLE" marker on the Assistant rail sits on the border of the row *below* the selected one.
8. **Dead code that misleads.** `TerminalPreview` has no consumer; `readOnly` is never passed by anyone (the whole
   read-only branch is unreachable); the demo `VITE_DEMO` branch returns before the wheel trap, scrollbar gauge and
   repaint are installed, so taskuary.com/demo renders a different terminal from the app.
