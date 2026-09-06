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
  assert.match(view, /onLive\(\["feed-changed", "task-changed"\], \(\) => loadPile\(true\)\)/);
});
