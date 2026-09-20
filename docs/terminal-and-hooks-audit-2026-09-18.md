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

1. ~~**One state, six sentences.**~~ FIXED 2026-09-20. The `blocked` lane in lanes.json now carries `says`: one sentence
   per sub-state (`asking`, `approval`, `stalled`, `parked`), with a `line` form that carries the request's words. Python
   reads it through `workerstate.says` / `sub_state` (request_line, funnel's items, the watcher, the by-the-way alerts, the
   hand-raise ping, the concierge's spoken line and lead, the assistant's context); the desktop through `laneSays.js`
   (WorkPane/WorkLine, the raw-tail pane, Board, the task page's session strip, the agent card's kicker and sub-line, the
   walk's lead, the hand-raise toast, the Timeline sub-line, the general workspace's raised hand). Every session row and
   Board row now carries `state` and `line`; Timeline rows carry `AgentLine` from all three loaders. The point of doing it
   now: the hooks' new `stalled` state (a rate limit) was reaching the pile as "is stuck - rate limit" and every other
   surface as "stopped and is waiting on you" or "asked you something", because those composed from two booleans.
   `tests/test_agent_sentence.py` guards that no site spells the sentence itself. Sub-state names are the chip/kicker words
   (`the coder is stuck`); the `needs you` chip and `agent waving` lane word are unchanged - they are the lane, not the
   sub-state.
2. ~~**A pty that exited mid-question says `input_needed` for ever.**~~ FIXED 2026-09-20: `release_task`, the one
   idempotent place that already knows a run ended, now writes `disconnected` on the worker record; Claude's `SessionEnd`
   hook does the same earlier, except for `clear`/`resume`, which leave the process alive. (Reordering `status()` was and
   is wrong: headless general work has no pty and legitimately asks.)
3. ~~**Hook coverage.**~~ FIXED 2026-09-20, and it turned two "guesses" into events. Claude: `StopFailure` (rate limit,
   token ceiling, overloaded, billing... with the error text) is a new `stalled` request that outranks any question and
   clears when the run speaks again or its quota auto-resumes; `Notification` is read by its typed `notification_type`
   (`agent_needs_input`/`idle_prompt` = a question asked inside the TUI, `permission_prompt` = approval);
   `PermissionRequest` is the approval itself, naming the tool and its arguments; `Elicitation`/`ElicitationResult` cover
   an MCP server asking; `SessionStart` binds the session id before a word is said. Codex: hooks now too (same schema, no
   StopFailure and no question event) - and measured on Windows, a Codex hook cannot reach the network sandbox on or off,
   so its hook appends stdin to `~/.taskuary/hooks/codex.jsonl` (cmd's redirect writes UTF-16) and `hooks.CodexSpool`
   tails it; `--dangerously-bypass-hook-trust` rides on the session argv because a user-scope hook is otherwise skipped
   silently until approved inside the TUI. Both CLIs' hooks install ONCE at user scope, right after set-up installs the
   CLI; a session refreshes them and retires the old per-checkout entries so nothing fires twice. Still not an event:
   a Codex stuck alive on an error (the screen's to notice), and `AskUserQuestion` still arrives asked-and-answered.
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
