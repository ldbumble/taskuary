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
  // ...a coding turn from the live session's own `turnStarted` first (codingchat.live_of): its first turn on a resume is a brief, drawn as no line,
  // and the owner's last line drawn was two days back - "Working on this… 2947m 55s" (the owner's live coding task, 2026-11-08)
  assert.match(ws, /const since = turnStart\(shownMessages\), began = session\?\.busy && session\?\.turn_started \? session\.turn_started \* 1000\n\s+: coding && cc\.live\?\.working && cc\.live\?\.turnStarted \? cc\.live\.turnStarted \* 1000 : codingAt \? \+asUtc\(codingAt\) \|\| null : null;/);
  assert.match(ws, /const typed = useAuiState\(\(s\) => turnBegan\(s\.thread\.messages\.filter\(\(m\) => m\.role === "user"\)\.map\(\(m\) => m\.createdAt\)\)\);/);
  // ...the server's start first: a mail joining mid-turn is newer than the turn, and set its clock back to 0s
  assert.match(ws, /<AgentBand \{\.\.\.props\} since=\{began \|\| Math\.max\(since \|\| 0, typed \|\| 0\) \|\| null\} \/>/);
  assert.match(ws, /work=\{work\} since=\{since\} began=\{began\}/);
});

// ...and the lines typed while it works come under that line, never between the turn's head and its clock
test("lines typed mid-turn are drawn under Working on this…", () => {
  const ws = readFileSync(new URL("../src/GeneralWorkspace.jsx", import.meta.url), "utf8");
  const i = ws.indexOf("<ThreadPrimitive.Messages components"), a = ws.indexOf("{atWork}", i), b = ws.indexOf("{serverBusy && atWork}", i), h = ws.indexOf("notShown(held, mineDrawn)].map(", i);
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

// A REPORT MADE A TASK says where it went on its row - and squeezed, its words drop out whole, never "Mo…" (the scenario run, 2026-11-06)
test("a moved row's words wrap away whole before they are cut", () => {
  const css = read("assistantView.css"), av = read("AssistantView.jsx");
  assert.match(css, /\.tq-pile-moved \{[^}]*flex-direction: row-reverse; flex-wrap: wrap;[^}]*height: 1\.5em; overflow: hidden;/);
  assert.match(css, /\.tq-pile-moved \.w \{ flex: 0 0 auto; \}/);
  assert.match(css, /\.tq-pile-moved \{ flex: 0 1000 auto; min-width: 5em;/, "it gives way before the title, down to its ref");
  assert.ok(av.indexOf('<span className="ref" role="link"') < av.indexOf('<span className="w">Moved to Tasks ·</span>'), "the ref comes first in the page");
});

// A CHECK-BACK COME DUE is the input of the turn it wakes, on the right under a clock (the scenario run, 2026-11-06): long, it was drawn as
// nothing, and the turn stood under the one before with no input over it
test("a check-back's turn opens on what it was set to verify", () => {
  const ws = read("GeneralWorkspace.jsx"), py = readFileSync(new URL("../../taskuary/checkback.py", import.meta.url), "utf8");
  const src = ws.slice(ws.indexOf("export const checkBackDue"), ws.indexOf("const UserMessage = "));
  const checkBackDue = new Function(`${src.replace("export ", "")}; return checkBackDue;`)();
  const turn = /TURN = \("([^"]+)"\s*\n\s*"([^"]+)"\)/.exec(py);
  assert.ok(turn, "the server's check-back line is where the test reads it");
  const said = (turn[1] + turn[2]).replace("{what}", "whether Ray sent the paper");
  assert.equal(checkBackDue(said), "whether Ray sent the paper");
  assert.equal(checkBackDue("THE THREAD CHANGED: Ray Colton wrote on this task"), "");
  assert.match(ws, /data-tq-chat-trigger="check-back"/);
});
