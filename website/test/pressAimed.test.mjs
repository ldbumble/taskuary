// A PRESS ACTS ON THE ITEM IT WAS AIMED AT (2026-10-25): a double-click on Mark done closed two tasks - the close drew the next task up at
// its press and the second click ran the verb that now answered to "done", the next task's. browser/press-aimed.test.mjs drives it whole.
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { ONE_PRESS_MS, aimed, press, put, rowNow } from "../src/actionRow.js";

test("a drawn button runs its own card's verb, and nothing once another card holds that id", () => {
  const ran = [];
  put("task:a", [{ id: "done", group: "more", label: "Mark done", run: () => ran.push("a") }], "TQ-0001");
  const drawn = rowNow().list.find((x) => x.id === "done");
  assert.equal(drawn.of, "task:a");
  press("done", null, null, drawn.of);
  put("task:a", null); put("task:b", [{ id: "done", group: "more", label: "Mark done", run: () => ran.push("b") }], "TQ-0002");
  press("done", null, null, drawn.of);                     // the button drawn for the first task, pressed again
  assert.deepEqual(ran, ["a"], "a press drawn for one task ran another's");
  press("done", null, null, rowNow().list.find((x) => x.id === "done").of);
  press("done");                                           // the code's own press (the Advisor's real button) names no card
  assert.deepEqual(ran, ["a", "b", "b"]);
  put("task:b", null);
});

test("one gesture is one press: a second click, or a press within one press, on another item does nothing", () => {
  let t = 1e9;
  assert.ok(aimed("A", { detail: 1 }, t));
  assert.ok(!aimed("B", { detail: 2 }, (t += 450)), "the second click of a double-click acted on the next item");
  assert.ok(aimed("A", { detail: 2 }, (t += 10)), "the same item may take its own second click");
  assert.ok(!aimed("B", { detail: 0 }, (t += ONE_PRESS_MS - 50)), "a press within one press acted on the next item");
  assert.ok(aimed("B", { detail: 1 }, (t += ONE_PRESS_MS + 1)), "a press after one press is the owner's next move");
  assert.ok(aimed("", { detail: 0 }, (t += ONE_PRESS_MS + 1)) && aimed("C", { detail: 0 }, (t += 50)), "a press on an empty table holds nothing");
});

test("the canvas holds every press to its item, on the window before any card hears it - and never the rail's", () => {
  const view = fs.readFileSync(new URL("../src/AssistantView.jsx", import.meta.url), "utf8");
  assert.match(view, /if \(!b \|\| b\.closest\("\[data-tq-rail\]"\) \|\| !b\.closest\("\.tq-asst-col, \[role=menu\], \.MuiPopover-paper"\)\) return;/);
  assert.match(view, /if \(!aimed\(item, e\)\) \{ e\.stopPropagation\(\); e\.preventDefault\(\); \}/);
  assert.match(view, /window\.addEventListener\("click", gate, true\);/);
  // ...and a close's late answer leaves a walk that went on without it, and the close's receipt never clears the item it drew
  assert.match(view, /if \(movedOnRef\.current\) \{ movedOnRef\.current = false; onChanged\?\.\(\); setNextComing\(false\); return; \}/);
  assert.match(view, /!earlyRef\.current && moves === tableMoves\.current/);
});
