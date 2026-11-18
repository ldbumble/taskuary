# Judged hammer commits

Every commit on a `claude/hammer-*` branch is read by three independent judges (UI/UX, robustness, truth). One that
all three pass is cherry-picked onto this branch. One that any judge fails is listed here with the reason and is
**not** fixed here - its author (or the owner) decides what happens next.

## Landed

| commit | branch | what |
|---|---|---|
| 4355976 | hammer-coding | A line typed after a coding agent died no longer tells it the owner pressed Resume |
| dc48b88 | hammer-connections | A failing Test on the organisation AI card names no Connect button |

## Failed

### 038e422 (hammer-assistant) - The Assistant called a network refusal a sign-in to fix
Failed by all three judges. `taskuary/concierge.py:995` now runs `general.refused_line(error)` before the
context-length branch, and `failures._REFUSED` matches any `<name> error 400 at <url>` text. An API brain's
"maximum context length" / "prompt is too long" 400 therefore reads "... refused the request ... Type to try again"
where it used to say "Start a new chat". Typing again cannot succeed: a dead end (rule 4), and no test pins that case.
The proxy-refusal fix itself is right. Way past: call only `unreached_line` first, or check context length before
`refused_line`, with a test for an llm.py-shaped 400.

### 0f46950 (hammer-visual) - One search box for every browse page
Failed by UI and robustness. (1) `website/test/connectorSearch.test.mjs:35` still asserts the old JSX and is red on
the commit (full node suite 2867/2868). (2) The Connections box was a native `type="search"`: Escape emptied it and it
drew a clear button; the shared box (`website/src/CanvasBrowse.jsx:35-41`) does neither.

### abdfa90 (hammer-routines-reports) - Settings said auto ran on a gateway card that auto never runs
Failed by robustness (UI and truth passed). Dead code left by the change: `taskuary/aidefaults.py:333`
("auto — currently ...") can no longer run, and `auto_target` is now a one-line alias of `agents.ready_connector`
with one caller (rule 3: dead code goes in the same change).

### a63a15a (hammer-connections) - A key typed on a connection card saves even when another box on it was refused
Failed by robustness (truth passed). `onSaved` is now called once per save; `website/src/ConnectorsView.jsx:2796-2801`
(and `:3173`) advances the stepper to Test as soon as the key's save lands, so in the commit's own scenario the refused
address's "Not saved" reason is folded shut inside the Credentials step. No test runs the hook.

### b9683ed (hammer-routines-reports) - Run now pressed twice said the second press started a run it never started
Failed by robustness (truth passed). (1) `website/src/demoApi.js:623` answers the rerun without `said`, so the static
demo now shows a bare tick, an empty alert and nothing on Try again. (2) The busy check is check-then-start
(`taskuary/server.py:7160` reads it, `taskuary/reports.py:2911` claims the slot later on the thread): two fast presses
can both read "running", and a press can read "no second run started" while its work does start one.
