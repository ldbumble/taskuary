// Opening Assistant restores, it does not start (PW-162..164): Current is the server's validated word, and no
// mount, tab activation, remount or reconnect calls Next or starts a walk.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const read = (name) => readFileSync(fileURLToPath(new URL(`../src/${name}`, import.meta.url)), "utf8");

test("Current comes from the server's validated state, never from the last historical card", () => {
  const view = read("AssistantView.jsx");
  const load = view.slice(view.indexOf("const loadState = useCallback"), view.indexOf("const deferredChat = useRef"));
  assert.match(load, /const last = data\.current \|\| null/);
  assert.doesNotMatch(load, /restorableCurrent|data\.messages\[|surface\(|turn\(/);
  assert.doesNotMatch(view, /restorableCurrent\(/);
});

test("mounting, activating, remounting and reconnecting only load - nothing calls Next", () => {
  const view = read("AssistantView.jsx");
  const effects = view.match(/useEffect\(\(\) => [^]*?\}, \[[^\]]*\]\);|useEffect\(\(\) => [^\n]*\n/g) || [];
  assert.ok(effects.length > 5);
  for (const e of effects) assert.doesNotMatch(e, /surface\(\)|surface\(null|turn\(\{ mode: "next"|start\(/, e.slice(0, 120));
  assert.match(view, /useEffect\(\(\) => \{ loadState\(\)\.catch\(\(e\) => setErr\(errText\(e\)\)\); \}, \[loadState\]\);/);
  assert.match(view, /pollWhileActive\(active, \(\) => \{\s*if \(first \|\| !liveUp\(\) \|\| \+\+n % 10 === 0\) loadPile\(false\);\s*else readChat\(\)/);
  assert.match(view, /onLive\(\["feed-changed", "task-changed"\], \(ev, meta\) => \{ if \(!coveredByReload\(meta, forcedLoadStartedAt\.current\)\) loadPile\(true\); \}, \{ wait: 1500, max: 5000 \}\)/);
});

// ...and it STAYS the server's word while the tab is open. The walk can be driven from a phone chat
// holding the handoff, and this tab followed the words while its rail went on ringing whatever the
// desk last put up (the owner, 2026-09-22: "it's out of sync again while talking to assistant on
// whatsapp" - the chat showed four fyis, the rail ringed the report before them).
test("the freshness poll adopts the server's Current, except while a turn of ours is in flight", () => {
  const view = read("AssistantView.jsx");
  const poll = view.slice(view.indexOf('const { data: st } = await api.get("/api/concierge")'),
                          view.indexOf("if (data.events?.length)"));
  assert.match(poll, /const said = st\.current \|\| null;/);
  assert.match(poll, /if \(!turnFlight\.current\)/, "a local answer is the newer truth");
  assert.match(poll, /setCurrent\(said\?\.key \|\| null\);/);
  assert.match(poll, /setCurrentItem\(said\);/);
  assert.match(poll, /currentRef\.current = said;/);
});

// The bracket round a batch is drawn behind its rows, between a sticky opaque band heading above it
// and the next row below. Both edges were landing on something: its top four pixels under the
// heading (which paints over it, so the group read as a row with its top cut off) and its label on
// the next fyi's subject (the owner, 2026-09-22: "you don't see the on the table when choosing 4
// fyi's? and top of the items looks cut off why?"). Geometry is measured in a browser -
// website/batch_bracket_check.mjs against a demo server - so this pins the arithmetic behind it.
test("a batch's bracket clears the sticky heading and leaves room for its own label", () => {
  const view = read("AssistantView.jsx");
  assert.match(view, /const BATCH_TAIL = \d+;/, "the gap under a bracket has a name");
  assert.match(view, /if \(wasInBatch && !inBatch\) stackHeight \+= BATCH_TAIL;/);
  assert.match(view, /if \(inBatch && !wasInBatch && stackHeight === 0\) stackHeight \+= 4;/);
  assert.match(view, /top: Math\.max\(0, mem\[0\]\.top - 4\)/, "never above the stack, where the heading paints");
  assert.match(view, /height: mem\[mem\.length - 1\]\.top \+ ROW_H \+ 1 - Math\.max\(0, mem\[0\]\.top - 4\)/,
    "the bottom edge stays where it was when the top is clamped");
});
