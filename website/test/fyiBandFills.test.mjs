import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { FLOOR, HEAD_PX, MORE_PX, ROW_PX, awayFromClear, fillCaps, fitRows, fyiHasRoom, railScrolls } from "../src/funnelPile.js";

const view = readFileSync(fileURLToPath(new URL("../src/AssistantView.jsx", import.meta.url)), "utf8");
const rows = (n, at = {}) => Array.from({ length: n }, (_, i) => ({ key: `k${i}`, ...at }));

// the owner, 2026-10-26, a batch of 4 fyi on the table under "FYI 13" beside two other rows: "also the 11 away which is wrong?"
test("away from clear is the headings added up, the batch on the table with them, the FYI not paged in with theirs", () => {
  const bands = [{ level: "task", items: rows(2) }, { level: "fyi", items: rows(13) }];          // 9 in the pile + the 4 put back
  assert.equal(awayFromClear(bands), 15);
  assert.equal(awayFromClear([{ level: "task", items: rows(2) }, { level: "fyi", items: rows(4) }], 9), 15);   // 9 still a tail
  assert.equal(awayFromClear([{ level: "task", items: [...rows(2), { key: "x", settling: true }] }]), 2);       // being read away
  assert.match(view, /const left = awayFromClear\(bands, tail\);/);
  assert.match(view, /data-tq-left=\{left\}/);
});

// "why does the fyi items not scroll out? meaning why does it say 9 more fyi"
test("the fyi band asks for its next page while one more row of it would fit, and not once there is no room", () => {
  const band = (n, total) => [{ level: "task", items: rows(2) }, { level: "fyi", items: rows(n), total }];
  const tall = 2 * HEAD_PX + 2 * ROW_PX + 30 * ROW_PX;
  assert.equal(fyiHasRoom(tall, band(4, 13)), true);                        // 4 drawn, 9 not asked for, room for all
  assert.equal(fillCaps(tall, band(4, 13)).fyi, 4);                         // ...every row it has is drawn already
  assert.equal(fyiHasRoom(tall, band(13, 13)), false);                      // nothing left to ask for
  assert.equal(fyiHasRoom(tall, band(4)), false);                           // no tail at all
  assert.equal(fyiHasRoom(2 * HEAD_PX + 4 * ROW_PX, band(4, 13)), false);   // the rail is full: "N more fyi" is the truth
  // ...asked once per count the band has, so a page that brings nothing new is never asked for again
  assert.match(view, /if \(fyiFills && fyiAsked\.current !== fyiHave\) \{ fyiAsked\.current = fyiHave; onMoreFyi\?\.\(\); \}/);
});

test("a trim taken for one moment's overflow is given back with the room, and the room follows what sits above the pile", () => {
  assert.match(view, /useLayoutEffect\(\(\) => \{ setTrim\(0\); grew\.current = false; \}, \[sig, room\]\);/);
  assert.match(view, /if \(over > 0 \|\| !trim \|\| grew\.current\) return;/);
  assert.match(view, /for \(let s = el\.previousElementSibling; s; s = s\.previousElementSibling\) ro\.observe\(s\)/);
  assert.match(view, /scroller\.getBoundingClientRect\(\)\.top \+ scroller\.scrollTop;/);
});

// the owner, 2026-11-02: "on FYI we should fit as many as can fit on the screen. In mine it's probably 8 at a time or so"
test("fyi fills the room before reports, and a rail that scrolls anyway draws a screenful of each capped band", () => {
  const rail = (t, r, f, total) => [{ level: "task", items: rows(t) }, { level: "reports", items: rows(r) }, { level: "fyi", items: rows(f), total }];
  // room for 3 headings, 3 tasks, 10 more rows and two "more" buttons: fyi takes 8, reports keep their floor
  const avail = 3 * HEAD_PX + 3 * ROW_PX + 10 * ROW_PX + 2 * MORE_PX;
  assert.deepEqual(fillCaps(avail, rail(3, 9, 15)), { fyi: 8, reports: 2 });
  assert.deepEqual(fillCaps(avail, rail(3, 9, 4)), { fyi: 4, reports: 6 });             // ...and what fyi does not need goes to reports
  // 20 tasks overflow a 561px rail at any cap: each band then gets what fits under its heading on one screen, never under FLOOR
  assert.equal(railScrolls(561, rail(20, 5, 15)), true);
  assert.equal(railScrolls(avail, rail(3, 9, 15)), false);
  assert.deepEqual(fillCaps(561, rail(20, 5, 15)), { fyi: Math.floor((561 - HEAD_PX - MORE_PX) / ROW_PX), reports: 5 });
  assert.deepEqual(fillCaps(200, rail(20, 5, 15)), { fyi: 4, reports: 4 });             // a short window: fewer
  assert.equal(fillCaps(60, rail(20, 5, 15)).fyi, FLOOR);
  // fitRows: heights in, rows out - the "more" button costed only while rows stay hidden
  assert.equal(fitRows(HEAD_PX + 5 * ROW_PX, 5), 5);
  assert.equal(fitRows(HEAD_PX + 5 * ROW_PX, 9), 4);
  assert.equal(fitRows(HEAD_PX + 5 * ROW_PX, 3, 9), 3);
  assert.equal(fitRows(0, 9), FLOOR);
  // ...and the overflow trim never eats a screenful the rail meant to draw
  assert.match(view, /const headroom = railScrolls\(room - \(curKey \? CUR_H - ROW_H : 0\), bands\) \? 0 :/);
});
