// A PRESS IS HEARD BEFORE IT RUNS: every press on the row - Next included - is told to its listeners (the table re-reads its decision
// after it), and a listener that throws never stops the press. A row id names its button's verb (buttons.json).
import test from "node:test";
import assert from "node:assert/strict";
import { onPressing, press, put } from "../src/actionRow.js";
import { verbOfRow } from "../src/buttons.js";

test("a press is heard before its handler runs, with the row id, and a listener that throws is not the press's problem", async () => {
  const order = [];
  put("t", [{ id: "done", group: "more", label: "Mark done", run: () => order.push("ran") }]);
  const off = onPressing((id) => order.push(`heard ${id}`));
  const bad = onPressing(() => { throw new Error("lost"); });
  press("done");
  off(); bad(); put("t", null);
  assert.deepEqual(order, ["heard done", "ran"]);
});

test("a row id names its verb: Mark done is close, Remind me is defer", () => {
  assert.equal(verbOfRow("done"), "close");
  assert.equal(verbOfRow("remind"), "defer");
  assert.equal(verbOfRow("12:approve"), "approve");
});

