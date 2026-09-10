// One bottom strip for every unsolicited update (PW-165..170): notices are always pending until Open or Later,
// a newer message on Current raises a notice instead of a chat line, and nothing in the pile refresh - a
// poll, a reconnect, a tab activation, a watcher event - calls Next, replaces the subject, or writes a turn.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { pendingAlerts, topAlert } from "../src/funnelPile.js";

const read = (name) => readFileSync(fileURLToPath(new URL(`../src/${name}`, import.meta.url)), "utf8");

test("a notice is pending whatever is on the table; a pile alert only when it outranks it", () => {
  const done = { key: "notice:7", item: "task:7", kind: "done", lane: "report", text: "codex finished TQ-0007", notice: true, order_band: 3 };
  const update = { key: "notice:msg:9", item: "msg:9", kind: "update", lane: "asked", text: "New message on this thread", notice: true, local: true };
  const draft = { key: "alert:review:3", item: "review:3", kind: "review", lane: "approve", text: "a reply waits", order_band: 2 };
  const onUrgent = { key: "msg:9", lane: "time", order_band: 1 };
  assert.deepEqual(pendingAlerts([draft, done, update], new Set(), onUrgent).map((a) => a.key), ["notice:7", "notice:msg:9"]);   // the draft does not outrank; both notices show
  assert.equal(topAlert([draft, done, update], new Set(), onUrgent).key, "notice:7");
  assert.deepEqual(pendingAlerts([draft, done, update], new Set(["notice:7"]), onUrgent).map((a) => a.key), ["notice:msg:9"]);   // Later puts one down, the next comes up
  assert.equal(topAlert([draft, done, update], new Set(["notice:7", "notice:msg:9"]), onUrgent), null);
  assert.equal(topAlert([draft], new Set(), { key: "x", lane: "fyi" }).key, "alert:review:3");                                      // ...and the pile's own rule still holds
  assert.equal(topAlert([draft], new Set(), { key: "review:3", lane: "approve" }), null);
});

test("the pile refresh notifies and refreshes, and never advances, clears by event, or writes a turn", () => {
  const view = read("AssistantView.jsx");
  const load = view.slice(view.indexOf("const loadPile = useCallback"), view.indexOf("useEffect(() => { loadPileRef.current = loadPile; }"));
  assert.doesNotMatch(load, /surfaceRef|deferInChat|turn\(|role: "assistant"/);            // no Next, no turn of its own (PW-168/169)
  const newer = load.slice(load.indexOf("if (newer) {"), load.indexOf("const refreshed = refreshCurrentPresentation"));
  assert.doesNotMatch(newer, /setMsgs/);                                                    // an update on Current is not a chat line (PW-165)
  assert.match(newer, /setNotices\(\(n\) => \[\.\.\.n\.filter\(\(x\) => x\.key !== key\), \{ key, item: cur\.key/);   // ...it is a strip notice, once per message
  assert.match(load, /const refreshed = refreshCurrentPresentation\(cur, fresh\)/);          // the context refresh is passive
  const events = load.slice(load.indexOf("if (data.events?.length)"), load.indexOf("// the item on the table is live"));
  assert.doesNotMatch(events, /setMsgs|setCurrent|surfaceRef|deferInChat/);
  // polling, live events and tab activation only refresh the pile
  assert.match(view, /pollWhileActive\(active, \(\) => loadPile\(false\), 30000\)/);
  assert.match(view, /onLive\(\["feed-changed", "task-changed"\], \(\) => \{ clearTimeout\(t\); t = setTimeout\(\(\) => loadPile\(true\), 1500\); \}\)/);
  assert.doesNotMatch(view, /onLive\([^)]*surface/);
});

test("the strip is one, stays until Open or Later, and Later puts down the notice and nothing else", () => {
  const view = read("AssistantView.jsx");
  const strip = view.slice(view.indexOf('<div className="tq-btw"'), view.indexOf('<div className="tq-compose">'));
  assert.match(strip, /\(\+\$\{pending\.length - 1\} more\)/);                              // the rest of the queue is not lost
  assert.match(strip, /ack\(alert, true\)/); assert.match(strip, /ack\(alert, false\)/);
  assert.match(strip, />Later<\/button>/);
  assert.match(strip, /alert\.item === current \? "Open the update" : current \? "Switch to it" : "Open"/);
  assert.equal((view.match(/className="tq-btw"/g) || []).length, 1);                        // one surface
  const ack = view.slice(view.indexOf("const ack = async (a, go)"), view.indexOf("const openChats"));
  assert.match(ack, /verb: "ack"/); assert.doesNotMatch(ack, /verb: "done"|Status|settle", \{ key: a\.item/);   // never the item
  assert.match(ack, /if \(go\) surface\(a\.item/);                                          // Open is the owner's own navigation
  assert.match(ack, /if \(!a\.local\)/);                                                    // a page-side notice needs no server row
  assert.match(view, /const pending = useMemo\(\(\) => pendingAlerts\(\[\.\.\.\(pile\?\.alerts \|\| \[\]\), \.\.\.notices\]/);
  assert.match(view, /setAcked\(new Set\(\)\); setNotices\(\[\]\)/);                       // a new chat starts clean
});
