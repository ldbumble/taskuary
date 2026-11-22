// A set-up proposed in the chat (PW-194/195): the card shows the configuration facts, can dry-run a report before the
// click, and links to the created resource's own screen afterwards.
import test from "node:test";
import assert from "node:assert/strict";


import { describe } from "../src/proposalCard.js";


test("the card shows the report's facts, not the raw config, and offers a dry run", () => {
  const p = { id: "r1", kind: "report.create", target: 0, version: 1, params: { config: { type: "sqlite" }, title: "Open tasks", schedule: "cron 0 8 * * 1", enabled: "yes", triage: "informational" }, label: "Create the report", summary: "Open tasks (sqlite)" };
  const d = describe(p);
  assert.deepEqual(d.params, [["title", "Open tasks"], ["schedule", "cron 0 8 * * 1"], ["enabled", "yes"], ["triage", "informational"]]);
  assert.equal(d.preview, true);
  assert.equal(describe({ ...p, kind: "connection.create" }).preview, false);
});
