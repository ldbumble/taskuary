// A REMOVE ACTS AT ONCE, AND UNDO TAKES IT BACK (the owner, 2026-10-21: no "are you sure"). Remove, Sign out, Disconnect and Not ours
// each asked first; now each runs on the press and leaves "Removed <it> - Undo" in place, and Recently deleted keeps a report, a
// workflow, a rule and a profile for 30 days (recentlydeleted.py). The one exception is a connection card's Remove, which asks once
// (the owner, 2026-11-05: one press, one confirm) - connectorUses.test.mjs pins its question.
import test from "node:test";
import assert from "node:assert/strict";


import { announceRemoved, clearRemoved, fromAnswer, lastRemoved, onRemoved, removedLine, showsRemoved, UNDO_MS } from "../src/removed.js";


test("the Undo line: announced by the press, drawn by the list that holds its kind, and only while it is fresh", () => {
  const seen = [];
  const off = onRemoved((r) => seen.push(r));
  const r = announceRemoved({ did: 7, title: "Outlook mail", kind: "connection" });
  assert.equal(removedLine(r.title, r.verb), "Removed Outlook mail");
  assert.equal(removedLine("ChatGPT", "Signed out of"), "Signed out of ChatGPT");
  assert.equal(lastRemoved().did, 7);
  assert.equal(showsRemoved(r, ["connection"]), true);
  assert.equal(showsRemoved(r, ["report"]), false);
  assert.equal(showsRemoved(r, ["connection"], r.at + UNDO_MS + 1), false);
  clearRemoved(7);
  assert.equal(lastRemoved(), null);
  off();
  assert.equal(seen.length, 2);
  // the server's answer names the kind it filed it under: a report and a workflow are told apart there
  assert.deepEqual(fromAnswer({ deleted: 3, title: "AP ageing", kind: "workflow" }, "report"), { did: 3, title: "AP ageing", kind: "workflow" });
});
