import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const read = (f) => readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");

// What the scenario run (2026-11-06: many messages, many tasks, three widths) found off by a pixel or a word, pinned

// A FOLDED TURN'S ONE LINE is cut where it ends - its whole words on hover too, not only a press away
test("the folded What I did line carries its whole words as its title", () => {
  assert.match(read("AgentSummary.jsx"), /<Box component="summary" title=\{did\} sx=\{\{ \.\.\.HEAD, mt: 0, cursor: "pointer", whiteSpace: "nowrap"/);
});
// THE RAIL'S FOOT FADE reaches the card's inner edge: a pixel short, a row's top showed through as a dark sliver (the scenario run, 2026-11-06)
test("the rail's bottom fade sits on the card's inner edge", () => {
  assert.match(read("FeedView.jsx"), /position: "absolute", left: "1px", right: "1px", bottom: 0, zIndex: 6,/);
});

// THE WORKING LINE'S CLOCK is the turn's (the scenario run, 2026-11-06): it read the owner's line before the one just typed, "249m 53s" over a
// turn three seconds old - the server's turn_started when it has said it, and never before the newest input in the thread
test("Working on this… counts from the turn's own start", () => {
  const ws = readFileSync(new URL("../src/GeneralWorkspace.jsx", import.meta.url), "utf8");
  assert.match(ws, /const since = \(session\?\.busy && session\?\.turn_started \? session\.turn_started \* 1000 : null\) \|\| turnStart\(shownMessages\);/);
  assert.match(ws, /const typed = useAuiState\(\(s\) => turnBegan\(s\.thread\.messages\.filter\(\(m\) => m\.role === "user"\)\.map\(\(m\) => m\.createdAt\)\)\);/);
  assert.match(ws, /<AgentBand \{\.\.\.props\} since=\{Math\.max\(since \|\| 0, typed \|\| 0\) \|\| null\} \/>/);
});

// ...and the lines typed while it works come under that line, never between the turn's head and its clock
test("lines typed mid-turn are drawn under Working on this…", () => {
  const ws = readFileSync(new URL("../src/GeneralWorkspace.jsx", import.meta.url), "utf8");
  const i = ws.indexOf("<ThreadPrimitive.Messages components"), a = ws.indexOf("{atWork}", i), b = ws.indexOf("{serverBusy && atWork}", i), h = ws.indexOf("{held.map(", i);
  assert.ok(i > 0 && a > i && b > a && h > b, "messages, the running line, the server's running line, then the held lines");
});

// AN ACTION CARD'S PICK is as wide as what it shows, and the keyboard sees it (the scenario run, 2026-11-06: "Anyone" a word's gap from its chevron)
test("an action card's choice sizes to its pick and rings on keyboard focus", () => {
  assert.match(read("ActionCard.jsx"), /fieldSizing: "content", borderRadius: "4px", "&:focus-visible": \{ outline: `2px solid \$\{ACCENT\}`, outlineOffset: 1 \} \};/);
});

// A TURN THE SERVER WOKE IS READ (the scenario run, 2026-11-06): new mail and a check-back ran three turns on a live, idle session while the
// open chat kept its first answer - nothing polls an idle pane. The task's own `task-changed` reads it once, never over this pane's own stream
test("the open chat reads the task again when it moves, unless a turn is streaming here", () => {
  const ws = read("GeneralWorkspace.jsx");
  assert.match(ws, /import \{ onLive, touches \} from "\.\/live\.js";/);
  assert.match(ws, /quietRef\.current = loaded && !busy && !streaming && !dock;/);
  assert.match(ws, /onLive\("task-changed", \(ev\) => \{ if \(quietRef\.current && touches\(ev, task\.TaskId\)\) refresh\(\); \}\)/);
});
