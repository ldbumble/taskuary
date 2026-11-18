# Judged hammer commits

Every commit on a `claude/hammer-*` branch is read by three independent judges (UI/UX, robustness, truth). One that
all three pass is cherry-picked onto this branch. One that any judge fails is listed here with the reason and is
**not** fixed here - its author (or the owner) decides what happens next.

## Landed

| commit | branch | what |
|---|---|---|
| 4355976 | hammer-coding | A line typed after a coding agent died no longer tells it the owner pressed Resume |
| dc48b88 | hammer-connections | A failing Test on the organisation AI card names no Connect button |
| 5acec14 | hammer-buttons-nav | The day card comes back counted, with no Counting… flash on the way home |
| 8b36957 | hammer-assistant | A file attached to the Assistant's line reaches it as its words |
| a1db8aa | hammer-visual | The email card's field names wear one label |
| 5319e10 | hammer-visual | A failed turn and a failed send read as a failure, not a faint hint |
| bd8f436 | hammer-connections | A new connection never takes a removed one's id, so Undo restores the old card as itself |

Known and not from these commits: `tests/test_conversation_list.py::TheList::test_what_one_hand_over_takes_stands_in_the_order_it_came`
fails intermittently on master too (judges saw it on parents and commits alike), and
`website/test/peopleSearch.test.mjs` (a timer) fails now and then under load.

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

### 913693d (hammer-connections) - A database or LinkedIn card that is switched on is one the agent may use
Failed by robustness (truth passed). The start-up heal (`taskuary/store.py:1682-1685`) treats every blank-roles row of
these types as the seed's and runs on every start. A card the owner let agents use and then turned "Off for agents"
is blank too, so the next restart silently gives agents the card back. The heal has no test: deleting it leaves the
new test green.

### 161ac67 (hammer-routines-reports) - A report run by hand read 'never ran' over its own last-run line
Failed by truth (robustness passed), by reading. The rewritten row (`website/src/ReportsView.jsx:510`) falls back to
`LastPolledAt` as a run time, and the commit's comment says only a scheduled run moves that mark. Saving a NEW routine
stamps it too (`taskuary/server.py:7697`, `touch_source`), so a routine that never ran reads "ran 2m ago".

### 3cd3d7b (hammer-agent-status) - A chat agent is not "waiting on you" until its answer is filed
Failed by robustness (truth passed; fix and test are sound). Dead state left by the change: `GeneralSession.spoke` is
now written and never read (`taskuary/general.py:2557`, `:3337`, `:4073`), and the commit's own test still sets it to
no effect (rule 3).

### f196d8c (hammer-inputs) - Pin that a wake after a press hears the press once
Failed by truth and robustness. Test-only, and the test does not pin what it says: with the de-dup removed
(`taskuary/general.py:851-853` filter, `:962` mark, `cardqueue.py:194`) it stays green, because its flow never builds
a prompt that carries the press twice. `tests/many_inputs_rig.py` is a near copy of the rig inline in
`tests/test_waitroom.py`, used by this one test.

### f240734 (hammer-inputs) - A card and a line in one second are ordered by the instant each came
Failed by truth and robustness. `taskuary/proposals.py:682` (`passed_why`) now compares the card's sub-second instant
with his lines' whole-second stamps, so a line typed after the card in the card's own second reads "written before the
agent read your line" where the parent truly said "you wrote ... after it".
`tests/test_answered_yourself.py::TheDraftHisAnswerRetiredStaysWhereItStood::test_a_late_press_on_a_taskless_draft_he_answered_says_so`
is red on the commit, 3 runs of 3. The set-aside ordering itself is right.
