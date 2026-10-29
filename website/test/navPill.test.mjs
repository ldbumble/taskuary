// NAV, ONE PILL (the owner, 2026-10-27: "We have a Next button - let's have a Back button that goes up the line as well. Basic nav. Of
// course on the first one no Back, like no Next on the last one. Combine Next/Back into one big pill called Nav"). Back goes up the rail's
// line the way Next walks down it, crossing sections in reverse; it never folds, and neither does Next. Invented rows throughout.
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { BACK, NAV, fitRow, foldsOf, navEnd, navOf, put, rowDrawable, rowNow, rowOf, rowWidth, walkMove } from "../src/actionRow.js";
import { backFrom, rowAbove } from "../src/funnelPile.js";
import { label } from "../src/buttons.js";

const v = (id, group, extra = {}) => ({ id, group, tone: "s", label: id, title: "", disabled: false, why: "", promote: true, lead: false, ...extra });
const back = v(BACK, "back", { label: "Back" }), next = v("next", "next", { label: "Next" });
const task = [v("reply", "decide", { tone: "p" }), v("start-agent", "agent", { lead: true }), v("done", "more"), v("remind", "more"), v("nat", "more"), v("reshape", "more")];

test("Back and Next are the Nav pill: Back is the row's own, never a type, and the words come from buttons.json", () => {
  assert.equal(label("back"), "Back"); assert.equal(label("next"), "Next"); assert.equal(NAV, "Nav");
  const row = rowOf({ ref: "TQ-1", list: [...task, back, next] });
  assert.equal(row.back.id, BACK); assert.equal(row.next.id, "next");
  assert.deepEqual(navOf(row).map((x) => x.id), [BACK, "next"], "up, then down");
  assert.ok(![...row.decide, ...row.agent, ...row.more].some((x) => x.group === "back" || x.group === "next"));
  assert.ok(walkMove(BACK) && walkMove("next") && walkMove("floor:next") && !walkMove("setup:back") && !walkMove("done"));
});

test("on the first item no Back; on the last no Next - the walk's Next only (setup's own Back and Next stay)", () => {
  assert.equal(rowOf({ ref: "", list: [...task, next] }).back, null, "nothing above: no Back registered, none drawn");
  const last = rowOf({ ref: "", list: [...task, back, next], end: true });
  assert.equal(last.next, null, "the last one: no Next"); assert.equal(last.back.id, BACK);
  const setup = rowOf({ ref: "", list: [v("setup:back", "next", { label: "Back" }), v("setup:next", "decide", { tone: "p" })], end: true });
  assert.equal(setup.next.id, "setup:back", "setup's step back is not the walk's Next");
});

test("Nav never folds, at any width, desk or phone - and the widths add it up as one pill", () => {
  const row = rowOf({ ref: "TQ-1", list: [...task, back, next] }, { verb: "reply" });
  for (const groups of foldsOf(row)) assert.ok(!groups.some((g) => [...g.shown, ...g.rest].some((x) => x.group === "back" || x.group === "next")));
  const m = { btn: Object.fromEntries([...row.decide, ...row.agent, ...row.more].map((x) => [x.id, 80])), label: { reply: 50, agent: 50, close: 50, task: 50, nav: 40 },
    more: 30, next: 70, back: 70, pad: 10, clGap: 5, bGap: 5, rowGap: 10 };
  assert.equal(rowWidth([], navOf(row), m), 10 + 40 + 5 + 70 + 70 + 5, "one pill: its label, Back, Next");
  assert.equal(rowWidth([], next, m), 10 + 40 + 5 + 70, "Next alone, as before");
  const phone = fitRow(row, m, 380, true);
  assert.equal(phone.level, phone.last, "a phone draws its own one group beside Nav");
});

test("the row's end flag rides the snapshot, and the walk's Back is no item's verb while a row is held", () => {
  put("nav:t", [{ ...back, run: () => {} }]);
  navEnd(true); assert.equal(rowNow().end, true);
  navEnd(false); assert.equal(rowNow().end, undefined);
  assert.equal(rowDrawable({ key: "msg:9", keyed: false, list: rowNow().list }), false, "Back alone is not the new item's row");
  put("nav:t", null);
});

// the rail's line, invented: two tasks (one urgent in its place), one put For later, a report, an idea, two fyi
const rows = [
  { key: "task:1", tid: 1, lane: "yours", order_band: 2, arrived_at: "2026-10-20 09:00:00" },
  { key: "task:2", tid: 2, lane: "yours", order_band: 2, arrived_at: "2026-10-21 09:00:00" },
  { key: "task:3", tid: 3, lane: "later", order_band: 2, deferred: true, defer_until: "2026-10-29 09:00:00", arrived_at: "2026-10-21 10:00:00" },
  { key: "task:4", tid: 4, lane: "yours", order_band: 2, settling: true, arrived_at: "2026-10-22 09:00:00" },
  { key: "report:5", lane: "report", order_band: 3, arrived_at: "2026-10-20 07:00:00" },
  { key: "report:6", lane: "report", order_band: 3, arrived_at: "2026-10-22 07:00:00" },
  { key: "msg:7", lane: "fyi", order_band: 4, arrived_at: "2026-10-19 07:00:00" },
  { key: "msg:8", lane: "fyi", order_band: 4, arrived_at: "2026-10-23 07:00:00" },
];
const up = (key, gone) => rowAbove(rows, rows.find((i) => i.key === key) || { key }, gone)?.key || null;

test("Back is the row above in the rail's order, across sections in reverse; the first row has none", () => {
  assert.equal(up("task:1"), null, "the first one: no Back");
  assert.equal(up("task:2"), "task:1");
  assert.equal(up("report:5"), "task:2", "the first report goes back to the last task - past For later and a task settling");
  assert.equal(up("report:6"), "report:5");
  assert.equal(up("msg:7"), "report:6", "FYI back to Reports");
  assert.equal(up("msg:8"), "msg:7");
});

test("Back skips what a press put down - Mark done, Remind me, Close with a note - and anything no longer on the rail", () => {
  assert.equal(up("report:5", (i) => i.key === "task:2"), "task:1", "the task closed a moment ago is never brought back");
  assert.equal(up("report:5", () => true), null, "everything above put down: no Back");
  assert.equal(rowAbove(rows.filter((i) => i.key !== "task:2"), rows[4])?.key, "task:1");
});

test("an fyi batch goes back from its first member; a task pulled by name, from the place it joins", () => {
  const batch = { key: "fyis:msg:7,msg:8", kind: "fyis", members: ["msg:7", "msg:8"], items: [rows[6], rows[7]] };
  assert.equal(rowAbove(rows.filter((i) => !i.key.startsWith("msg:")), batch)?.key, "report:6", "its rows left the pile once shown - placed back by the batch");
  assert.equal(rowAbove(rows, { key: "task:9", tid: 9, lane: "asked", arrived_at: "2026-10-20 12:00:00" })?.key, "task:1", "a task opened by name sits in Tasks by arrival");
  assert.equal(rowAbove(rows, null), null);
});

// BACK FROM THE FIRST FYI IS THE LAST REPORT READ (trust audit F1, 2026-10-28): a report read leaves the rail, and Back skipped to the last task
test("Back from the first FYI goes to the last report the walk read; from a later FYI, or with the report still on the rail, the row above", () => {
  const rows = [{ key: "task:1", tid: 1, lane: "asked", order_band: 2 }, { key: "msg:7", lane: "fyi", order_band: 4 }, { key: "msg:8", lane: "fyi", order_band: 4 }];
  const read = { key: "processing:report-6" };
  assert.deepEqual(backFrom(rows, rows[1], undefined, read), { key: "processing:report-6", kind: "report" });
  assert.equal(backFrom(rows, rows[1], undefined, null)?.key, "task:1", "no report read this walk: the row above");
  assert.equal(backFrom(rows, rows[2], undefined, read)?.key, "msg:7", "a later FYI: the FYI above it");
  assert.equal(backFrom([...rows, { key: "processing:report-6", lane: "report", order_band: 3 }], rows[1], undefined, read)?.key, "processing:report-6",
    "a report still on the rail is the row above, by the rail's own order");
  assert.equal(backFrom(rows, rows[0], undefined, read)?.key, undefined, "a task is never sent back to a report");
});

test("the view registers Back beside the floor and runs it as a row pick; Next is hidden on the last one only from the walk's own capture", () => {
  const view = fs.readFileSync(new URL("../src/AssistantView.jsx", import.meta.url), "utf8");
  // ...and on a desk Back is always there, greyed where there is nowhere to go back to (the owner, 2026-10-29)
  assert.match(view, /useVerbs\("nav", \[\{ id: BACK, group: "back", label: btn\("back"\), title: btnHint\("back"\), disabled: !backTo, why: "nothing above this one",\s+run: \(\) => backTo && goBack\(\) \}\], !!backTo \|\| \(deskChat && !firstRun\)\);/);
  assert.match(view, /const up = backFrom\(pileRef\.current\?\.items, currentRef\.current, isDown, lastReportRef\.current\);/);
  assert.match(view, /return surface\(up\.key, null\);/, "the same road as a rail click: one draw, the ring follows");
  assert.match(view, /if \(busy \|\| turnFlight\.current\) \{ backHeld\.current = true;/, "a Back over a move in flight waits for it, and runs once");
  assert.match(view, /sel\.scope\?\.exclude === current\s+&& !sel\.expected_next_key && !\(sel\.expected_next_members \|\| \[\]\)\.length;/);
  const row = fs.readFileSync(new URL("../src/ActionRow.jsx", import.meta.url), "utf8");
  assert.ok(row.indexOf("data-tq-walk-back") < row.indexOf("data-tq-next=\"\""), "Back on the left, Next on the right");
  assert.match(row, /aria-label=\{NAV\} data-tq-type="nav"/);
});
