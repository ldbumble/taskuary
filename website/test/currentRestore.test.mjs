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
  assert.match(view, /pollWhileActive\(active, \(\) => loadPile\(false\), 30000\)/);
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
