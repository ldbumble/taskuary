# Phase 0 rendered-browser harness

Use Node 22 for all frontend gates (`npm test`, `npm run build`, and browser tests).
The explicit recursive test glob retains every existing frontend test under Node 22.

Run `npm run test:browser` from `website` for the read-only Assistant, Tasks,
Board, and Reports baseline. The harness starts a real FastAPI server in Taskuary's
`--demo` mode and a Vite server whose `TASKUARY_API` is the random fixture port.
It uses an invented SQLite database in a unique temporary `TASKUARY_HOME`; browser,
HOME, USERPROFILE, XDG, Codex, Claude, AppData, and LocalAppData state are
isolated beneath that directory. The fixture uses an explicit non-secret test token.
Chrome or Edge must already be installed. Set `TASKUARY_BROWSER_EXECUTABLE` when it
is not in one of the standard Windows, macOS, or Linux locations.

Puppeteer 25.8.0 requires Node 22.12 or newer. On a machine whose default Node is
older, run the complete gate without changing the global runtime:

```
npm exec --yes --package=node@22 -- node --test --test-concurrency=1 browser/phase0-browser.test.mjs browser/terminal-replay.test.mjs
```

When the active runtime is already Node 22.12+, `npm run test:browser` is the same
gate. CI should select Node 22 before dependency installation and the browser run.

The browser blocks HTTP and WebSocket requests outside its Vite fixture origin;
expected Google font requests are blocked and reported separately. Ports 7787 and
7790 are forbidden. The server's pre-bound listener is installed before guards
block application outbound TCP through Python socket connect/connect_ex and the
active event loop's create_connection; startup self-checks both guards. Demo startup returns before connectors,
schedulers, and waitroom watchers start, while demo middleware denies mutating
connector, send, tool, polling, and worker routes. The test verifies `/api/demo`
before reporting success. These are actual backend fixtures, not browser mocks.

The fixed 37-item demo fixture records first Assistant visibility, text input,
Tasks, Board, and Reports timing. Three Windows/Edge runs measured 1.0-2.3 seconds
to first visibility, 0.12-0.27 seconds per navigation, and 0.47-0.90 seconds for the
24-character input probe. The provisional budgets are 8 seconds, 3 seconds, and
1.5 seconds respectively, leaving startup variance without making a multi-second
navigation regression invisible. Override them with `TASKUARY_BROWSER_VISIBLE_MS`,
`TASKUARY_BROWSER_NAVIGATION_MS`, and `TASKUARY_BROWSER_INPUT_MS` after enough CI
samples establish stable budgets.

`npm run test:browser` includes terminal replay, input emission, and reconnect.
At base commit `2689679`, this test exposed that the demo websocket called
`Replay.quiet_for()` even though the synthetic `Replay` fixture had no such method;
the pane reached `closed`. The separately reviewed Phase 0 runtime fix is commit
`6a50579`. `npm run test:browser:terminal` remains available for a focused run.
The fixture intentionally ignores typed input because it has no PTY or worker; the
test verifies that the rendered xterm emits the complete input over its fixture
websocket and that replay content appears again after reconnect. It records and
gates replay visibility, input emission while the synthetic replay is active, and
reconnect time at 10 seconds, 1.5 seconds, and 10 seconds respectively.

Current/Next rendering is covered without changing its interaction contract.
Assistant browser ownership and controls (walkthrough IDs PW-265 through PW-267) remain
review pending and are outside this harness.
