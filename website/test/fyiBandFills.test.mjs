import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { HEAD_PX, ROW_PX, awayFromClear, fillCaps, fyiHasRoom } from "../src/funnelPile.js";

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
