// NAV, ONE PILL (the owner, 2026-10-27: "We have a Next button - let's have a Back button that goes up the line as well. Basic nav. Of
// course on the first one no Back, like no Next on the last one. Combine Next/Back into one big pill called Nav"). Back goes up the rail's
// line the way Next walks down it, crossing sections in reverse; it never folds, and neither does Next. Invented rows throughout.
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { BACK, NAV, fitRow, foldsOf, navEnd, navOf, put, rowDrawable, rowNow, rowOf, rowWidth, walkMove } from "../src/actionRow.js";
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

test("on the first item no Back; on the last Next greyed - the walk's Next only (setup's own Back and Next stay)", () => {
  assert.equal(rowOf({ ref: "", list: [...task, next] }).back, null, "nothing above: no Back registered, none drawn");
  const last = rowOf({ ref: "", list: [...task, back, next], end: true });
  // ...greyed, never gone (the owner, 2026-10-30: "always keep the back and next button but grey them out if not applicable")
  assert.equal(last.next.id, "next", "the last one: Next stands"); assert.equal(last.next.disabled, true, "...greyed"); assert.equal(last.back.id, BACK);
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
// WHICH ROW IS ABOVE is the server's (railwalk.back, 2026-10-30): the rail's order read upward from the row on screen, For later and
// rows still settling off the line, a read row gone - pinned by the walk table (tests/fixtures/walk_table.json W05-W07, W12, W19, W20,
// W39, W45, W47) and its browser runner. The page only asks, and greys Back where the walk says nothing is above.
test("the view registers Back beside the floor and asks the walk for the row above; Next is hidden on the last one from the walk's own word", () => {
  const view = fs.readFileSync(new URL("../src/AssistantView.jsx", import.meta.url), "utf8");
  // ...and on a desk Back is always there, greyed where there is nowhere to go back to (the owner, 2026-10-29)
  assert.match(view, /useVerbs\("nav", \[\{ id: BACK, group: "back", label: btn\("back"\), title: btnHint\("back"\), disabled: !backTo, why: "nothing above this one",\s+run: \(\) => backTo && goBack\(\) \}\], !!backTo \|\| \(deskChat && !firstRun\)\);/);
  assert.match(view, /if \(!walkOf\(pileRef\.current\)\?\.above\) return undefined;/, "nothing above: nothing happens");
  assert.match(view, /return surface\(null, null, null, false, "back"\);/, "the walk's own Back: the row above, from the server");
  assert.match(view, /const backTo = table\.speaks && !firstRun && !old && !walk && onWalk \? walkNow\.above : null;/);
  assert.match(view, /if \(busy \|\| turnFlight\.current\) \{ backHeld\.current = true;/, "a Back over a move in flight waits for it, and runs once");
  assert.match(view, /const atEnd = !!current && table\.speaks && onWalk && !walkNow\.below;/, "no Next on the last one: the walk says nothing is below");
  const row = fs.readFileSync(new URL("../src/ActionRow.jsx", import.meta.url), "utf8");
  assert.ok(row.indexOf("data-tq-walk-back") < row.indexOf("data-tq-next=\"\""), "Back on the left, Next on the right");
  assert.match(row, /aria-label=\{NAV\} data-tq-type="nav"/);
});
