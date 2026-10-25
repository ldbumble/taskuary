import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";
import assert from "node:assert/strict";
import { ageHover, arrivedAt, bandsOf, inOrder, isUrgent, latestLine, newMark, nextMarkerKey } from "../src/funnelPile.js";
import { summarize } from "../src/walkSummary.js";

// THE RAIL IS ONE FIXED ORDER (the owner, 2026-10-22: "set by time, oldest to newest and then never move ... on the table should
// never move them"): a row is placed by when it ARRIVED, and the row on the table is drawn in that place, never lifted to the top.
const at = (h) => new Date(Date.now() - h * 3600e3).toISOString().slice(0, 19).replace("T", " ");
const task = (key, h, extra = {}) => ({ key, kind: "todo", lane: "yours", order_band: 2, tid: Number(key.slice(5)), arrived_at: at(h), ...extra });

test("a task pulled onto the table from outside the pile is drawn in its place, not on top", () => {
  const rows = [task("task:1", 19), task("task:2", 17), task("task:3", 11)];
  const pulled = task("task:9", 12);
  assert.deepEqual(inOrder(rows, [pulled]).map((r) => r.key), ["task:1", "task:2", "task:9", "task:3"]);
  assert.deepEqual(inOrder(rows, [task("task:8", 1)]).map((r) => r.key), ["task:1", "task:2", "task:3", "task:8"]);
  const report = { key: "report:5", kind: "report", lane: "report", order_band: 3, arrived_at: at(2) };
  const drawn = bandsOf(inOrder(rows, [report]));
  assert.deepEqual(drawn.map((b) => b.level), ["task", "reports"]);
});

test("the gutter's age is the arrival the rows are ordered by, not the newest activity", () => {
  // the owner's screenshot: 19h, 17h, 11h, <30m and then 1h - the working task's age was its agent's start
  const working = task("task:4", 26, { lane: "working", since: at(1), when: at(0.2) });
  assert.equal(arrivedAt(working), working.arrived_at);
  assert.equal(arrivedAt({ since: "a", when: "b" }), "a");
});

test("the rail draws the pile in the server's order and the table row through inOrder", () => {
  const view = readFileSync(fileURLToPath(new URL("../src/AssistantView.jsx", import.meta.url)), "utf8");
  assert.match(view, /const drawn = inOrder\(/);
  assert.match(view, /band\(i\.kind === "meeting" \? i\.when : arrivedAt\(i\)\)/);
  assert.doesNotMatch(view, /\.\.\.\(curKey && !known \? \[pulledRow\(current\)\] : \[\]\),\s*\.\.\.onTable,\s*\.\.\.drawOrder/);
});

// REPORTS GO OLDEST FIRST LIKE EVERY OTHER SECTION (the owner, 2026-10-22: "reports should go oldest first like everything else"), and
// there is NO URGENT SECTION (2026-10-22: "remove the urgent section and just add quiet shading around it"): an urgent row sits in
// Tasks at its arrival place, shaded.
const report = (key, h) => ({ key, kind: "report", lane: "report", order_band: 3, arrived_at: at(h) });

test("a report from outside the pile takes its oldest-first place among the reports", () => {
  const rows = [report("report:1", 9), report("report:2", 3)];
  assert.deepEqual(inOrder(rows, [report("report:3", 5)]).map((r) => r.key), ["report:1", "report:3", "report:2"]);
  assert.deepEqual(inOrder(rows, [report("report:4", 1)]).map((r) => r.key), ["report:1", "report:2", "report:4"]);
});

test("an urgent task sits in Tasks at its arrival place, and no Urgent band is drawn", () => {
  const rows = [task("task:1", 19), task("task:2", 11, { lane: "time", order_band: 1 }), task("task:3", 2)];
  const bands = bandsOf(rows);
  assert.deepEqual(bands.map((b) => b.level), ["task"]);
  assert.deepEqual(bands[0].items.map((r) => r.key), ["task:1", "task:2", "task:3"]);
  assert.deepEqual(rows.map((r) => isUrgent(r)), [false, true, false]);
  // the marker for Next, with no server selection, walks the urgent row in its place (the owner, 2026-10-22: "you go through it
  // like all other tasks"): from the row above it, it is next; with nothing on the table the walk starts at the top, not at it
  assert.equal(nextMarkerKey(null, rows, rows[0]), "task:2");
  assert.equal(nextMarkerKey(null, rows, null), "task:1");
});

test("the rail shades an urgent row in place and says urgent to a screen reader; the opener still counts it", () => {
  const view = readFileSync(fileURLToPath(new URL("../src/AssistantView.jsx", import.meta.url)), "utf8");
  const css = readFileSync(fileURLToPath(new URL("../src/assistantView.css", import.meta.url)), "utf8");
  assert.match(view, /const hot = !i\.settling && isUrgent\(i\);/);
  assert.match(view, /hot \? "urgent" : imp \? "important" : ""/);
  assert.match(view, /data-tq-urgent=\{hot \? "" : undefined\}/);
  assert.match(view, /aria-label=\{hot \? `\$\{i\.title\} - urgent` : imp \? `\$\{i\.title\} - important` : undefined\}/);
  assert.match(css, /\.tq-pile-row\.urgent \.card \{ background: rgba\(138, 54, 70, \.06\)/);
  // IMPORTANT is the dot's colour, the theme's slate, in its place (the owner, 2026-10-25): urgent outranks it, no edge, no shade, no move
  assert.match(view, /const imp = isImportant\(i, hot\);/);
  assert.match(view, /background: imp \? PRIORITY_COLOR\.important : LEVEL_COLOR\[level\]/);
  assert.doesNotMatch(css, /\.tq-pile-row\.important \.card/);
  assert.doesNotMatch(css, /\.tq-pile-row\.important[^{]*\{[^}]*background/, "important never shades the row");
  assert.doesNotMatch(css, /lvl-urgent/);
  const sum = summarize([task("task:1", 19), task("task:2", 11, { lane: "time", order_band: 1 }), report("report:1", 3)]);
  assert.deepEqual(sum.groups.map((g) => [g.key, g.n, g.urgent]), [["task", 2, 1], ["reports", 1, 0]]);
  assert.equal(sum.lead, "3 things: 2 tasks (1 urgent), 1 reports.");
});

// +N, NEVER A MOVE (the owner, 2026-10-23): a reply since the owner last opened the row is a quiet "+N" beside the ARRIVAL age, the
// age's hover says both clocks, and the line under the title is the newest message; the row on the table (just opened) wears none
const local = (h) => { const d = new Date(Date.now() - h * 3600e3); return new Date(d - d.getTimezoneOffset() * 60e3).toISOString().slice(0, 19).replace("T", " "); };

test("a row with replies since it was opened says +N beside its arrival, and none once it is opened", () => {
  const row = task("task:4", 26, { new_n: 3, last_at: local(2) });
  assert.equal(newMark(row, false), "+3");
  assert.equal(newMark(row, true), "", "the row on the table has just been opened");
  assert.equal(newMark({ ...row, new_n: 0 }, false), "");
  assert.equal(arrivedAt(row), row.arrived_at, "a reply changed the age");
});

test("the age's hover says when it arrived and when its last message came", () => {
  const row = { key: "task:4", arrived_at: local(26), last_at: local(2) };
  assert.match(ageHover(row), /^arrived .+ · last message 2h ago$/);
  assert.match(ageHover({ ...row, last_at: undefined }), /^arrived [^·]+$/);
});

test("the line under the title is the newest message", () => {
  assert.equal(latestLine({ latest: { who: "Erin Blake", text: "Signed copy attached." } }), "Erin Blake: Signed copy attached.");
  assert.equal(latestLine({}), "");
});

test("the rail row draws the mark in the age column and the newest message on the table's line", () => {
  const view = readFileSync(fileURLToPath(new URL("../src/AssistantView.jsx", import.meta.url)), "utf8");
  assert.match(view, /<span className="tq-pile-new">\{newMark\(i, isCur\)\}<\/span>/);
  assert.match(view, /: ageHover\(i\)\}>/);
  assert.match(view, /latestLine\(i\) \? \[latestLine\(i\), ago\(i\.last_at\)\]/);
});
