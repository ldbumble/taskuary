// THE TURN'S CLOCK (RunClock.jsx), rendered: what its head claims of the turn's start and how long it has run, as the clock moves and the page
// draws it again.
import test from "node:test";
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";

// ...a stand-in React: every draw a fresh mount (as a return to the task is) - hooks run their first time, effects never; elements are kept as a tree
const R = { useState: (init) => [typeof init === "function" ? init() : init, () => {}], useEffect: () => {}, useContext: (c) => c.v ?? null,
  createContext: (v) => ({ v }), jsx: (type, props) => ({ type, props: props || {} }) };
R.jsxs = R.jsx; R.default = R;
const build = async () => {
  const { build: esb } = await import("esbuild");
  const stub = { "react": "export const { useState, useEffect, useContext, createContext } = globalThis.__R; export default globalThis.__R;",
    "react/jsx-runtime": "export const { jsx, jsxs } = globalThis.__R; export const Fragment = 'Fragment';",
    "@mui/material": "export const IconButton = 'IconButton';", "@mui/icons-material/Close": "export default 'CloseIcon';" };
  const out = await esb({ entryPoints: [fileURLToPath(new URL("../src/RunClock.jsx", import.meta.url))], bundle: true, write: false, format: "esm",
    jsx: "automatic", logLevel: "silent", plugins: [{ name: "stubs", setup(b) {
      b.onResolve({ filter: /.*/ }, (a) => (a.path in stub ? { path: a.path, namespace: "stub" } : undefined));
      b.onLoad({ filter: /.*/, namespace: "stub" }, (a) => ({ contents: stub[a.path], loader: "js" })); } }] });
  globalThis.__R = R;
  return import(`data:text/javascript;base64,${Buffer.from(out.outputFiles[0].text).toString("base64")}`);
};
const words = (n) => (n == null || typeof n === "boolean" ? "" : Array.isArray(n) ? n.map(words).join("") : typeof n === "object"
  ? (typeof n.type === "function" ? words(n.type(n.props)) : words(n.props.children)) : String(n));

test("a turn with no start claims no time, however often it is drawn and however long it runs; a real start is shown and counts", async (t) => {
  t.mock.timers.enable({ apis: ["Date"], now: new Date(2026, 10, 18, 9, 30, 0).getTime() });
  const { RunClock, turnStart } = await build();
  const draw = (started) => words(RunClock({ start: turnStart({ started }) })).trim();
  // ...the server always sends `started` (conversation.items): this is the defensive road. The moment it was drawn read as the turn's start,
  // and its count began at 0s on every draw - "· 9:30 AM · working 0s" a minute into the turn
  const seen = [draw(null)];
  for (const ms of [1000, 5000, 60000]) { t.mock.timers.tick(ms); seen.push(draw(null)); }
  assert.deepEqual(seen, ["· working", "· working", "· working", "· working"], "no start, no time claimed - never a draw's moment, never 0s");
  // ...and the turn's start, once the list gives one: its own time, and the count from it
  const began = Date.now() / 1000 - 7;
  assert.equal(draw(began), "· 9:30 AM · working 7s");
  t.mock.timers.tick(4000);
  assert.equal(draw(began), "· 9:30 AM · working 11s");
});
