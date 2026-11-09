// AN UNDO IS FOR JUST NOW (the owner, 2026-11-09: "I hit 'walk me through' and an old undo came back"). A task removed as not a task
// left "Removed <title> - Undo" in a module-level slot for ten minutes, with no clock of its own: the rail drew it again whenever it
// mounted inside those minutes - Walk me through, a navigation - long after the owner had moved on. Now the line lives a few seconds
// (as SaveNote's Undo does), its slot empties when they pass, and a press anywhere else ends it.
import test from "node:test";
import assert from "node:assert/strict";
import { announceRemoved, clearRemoved, endRemovedOnPress, lastRemoved, showsRemoved, UNDO_MS } from "../src/removed.js";

test("the line is a short window, not ten minutes", () => {
  assert.ok(UNDO_MS <= 15000, `an Undo offer lasts seconds, not ${UNDO_MS} ms`);
});

test("a rail mounted minutes after the remove (Walk me through) draws no Undo", (t) => {
  let clock = Date.now(); t.mock.method(Date, "now", () => clock);
  const r = announceRemoved({ did: 9, title: "Check the import report", kind: "task" });
  assert.ok(showsRemoved(lastRemoved(), ["task"]), "drawn just after the press");
  clock += 8 * 60 * 1000;                     // the live shape: eight minutes later the owner presses Walk me through
  assert.equal(lastRemoved(), null, "the slot a newly mounted rail reads is empty");
  assert.equal(showsRemoved(lastRemoved(), ["task"]), false);
  clearRemoved();
});

test("a press elsewhere ends it; a press on the line itself does not", () => {
  announceRemoved({ did: 10, title: "Fuel card statement", kind: "task" });
  endRemovedOnPress({ target: { closest: (s) => (s === "[data-tq-undo]" ? {} : null) } });
  assert.equal(lastRemoved()?.did, 10, "Undo or × on the line is its own press");
  endRemovedOnPress({ target: { closest: () => null } });
  assert.equal(lastRemoved(), null, "acting anywhere else ends the offer");
});
