// Nothing in the pile refresh - a poll, a reconnect, a tab activation, a watcher event - calls Next, replaces
// the subject, or writes a turn (PW-165..170). The bottom strip those notices rode is gone (2026-09-23): the
// rail and the card on the table already say what it said.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const read = (name) => readFileSync(fileURLToPath(new URL(`../src/${name}`, import.meta.url)), "utf8");

test("the pile refresh notifies and refreshes, and never advances, clears by event, or writes a turn", () => {
  const view = read("AssistantView.jsx");
  const load = view.slice(view.indexOf("const loadPile = useCallback"), view.indexOf("useEffect(() => { loadPileRef.current = loadPile; }"));
  assert.doesNotMatch(load, /surfaceRef|deferInChat|turn\(|role: "assistant"/);            // no Next, no turn of its own (PW-168/169)
  const newer = load.slice(load.indexOf("if (newer) {"), load.indexOf("const refreshed = refreshCurrentPresentation"));
  assert.doesNotMatch(newer, /setMsgs/);                                                    // an update on Current is not a chat line (PW-165)
  assert.doesNotMatch(newer, /setNotices/);                                                 // ...nor a strip: the card refreshes in place
  assert.match(load, /const refreshed = refreshCurrentPresentation\(cur, fresh\)/);          // the context refresh is passive
  const events = load.slice(load.indexOf("if (data.events?.length)"), load.indexOf("// the item on the table is live"));
  assert.doesNotMatch(events, /setMsgs|setCurrent|surfaceRef|deferInChat/);
  // polling, live events and tab activation only refresh the pile
  assert.match(view, /pollWhileActive\(active, \(\) => loadPile\(false\), 30000\)/);
  assert.match(view, /onLive\(\["feed-changed", "task-changed"\], \(ev, meta\) => \{ if \(!coveredByReload\(meta, forcedLoadStartedAt\.current\)\) loadPile\(true\); \}, \{ wait: 1500, max: 5000 \}\)/);
  assert.doesNotMatch(view, /onLive\([^)]*surface/);
});

