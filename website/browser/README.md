# Browser harness

There are no browser tests: the owner removed them (2026-11-21) - they pinned layouts and broke on every redesign while catching
nothing the screen did not show. A screen change is checked by looking at it.

What is here drives the real app for a walk or a recording:

- `real-run.mjs` starts an isolated app (its own `TASKUARY_HOME`, a Vite server, Chrome) and prints `READY <url> <home>`;
  `user.mjs` and `real-lib.mjs` press and read it like the owner does.
- `recorder.mjs` records a scenario's screen to watch before and after a fix.
- `harness.mjs` is the server and browser fixture they share.
- `press-keep.mjs` holds the demo world up and `press-measure.mjs <label>` presses the buttons of a day once each as a hand does (`press-lib.mjs`:
  the pointer travels, rests, goes down, comes up - never `element.click()`), records each, and says which took one click, where the click
  went, how far the button moved while the pointer was down, and the milliseconds from the release to the first change on screen.

Use Node 22 (`npm exec --yes --package=node@22 -- node real-run.mjs`).
- `goal-walk.mjs <goals/shape.json>` plays a shape (New, a press 100 times, Search, a mail arriving, waiting on the agent) on the running app
  and says after every step what the owner would mind: `watch.mjs` reads the screen every 100 ms for a flicker, a jump, a blank beat, junk
  words or a thing drawn twice; the outbox says whether a press sent more than once; the rail whether a row stands twice. Each step leaves its
  screenshot and the walk `goal-<shape>.md`. `goals/` holds the shapes every pass replays - a finding becomes a shape there.
