# Browser harness

There are no browser tests: the owner removed them (2026-11-21) - they pinned layouts and broke on every redesign while catching
nothing the screen did not show. A screen change is checked by looking at it.

What is here drives the real app for a walk or a recording:

- `real-run.mjs` starts an isolated app (its own `TASKUARY_HOME`, a Vite server, Chrome) and prints `READY <url> <home>`;
  `user.mjs` and `real-lib.mjs` press and read it like the owner does.
- `recorder.mjs` records a scenario's screen to watch before and after a fix.
- `harness.mjs` is the server and browser fixture they share.

Use Node 22 (`npm exec --yes --package=node@22 -- node real-run.mjs`).
