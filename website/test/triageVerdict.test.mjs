import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  extraTriageFields, intentLabel, kindLabel, latestTriageVerdict, legacyTriageVerdict,
  parseTriageVerdict, relationshipLabel, routeIntent, routeWhy,
} from "../src/triageVerdict.js";

test("the latest saved structured triage response is decoded", () => {
  const old = { VerdictJson: JSON.stringify({ intent: "fyi", why: "old" }) };
  const latest = { VerdictJson: JSON.stringify({
    intent: "task", kind: "coding", repository: "acme/widgets", checklist: ["Fix the export"],
  }) };
  assert.deepEqual(parseTriageVerdict(latest), {
    intent: "task", kind: "coding", repository: "acme/widgets", checklist: ["Fix the export"],
  });
  assert.equal(latestTriageVerdict([old, { VerdictJson: "not json" }, latest]).repository, "acme/widgets");
  assert.equal(parseTriageVerdict({ VerdictJson: "[1,2]" }), null);
});

test("triage vocabulary is phrased for the owner", () => {
  assert.equal(intentLabel("reply_only"), "Reply needed");
  assert.equal(kindLabel("task"), "My task list");
  assert.equal(kindLabel("general"), "Assistant");
  assert.equal(relationshipLabel("continues"), "Continues earlier work");
});

test("an old taskless FYI is reconstructed from its saved route", () => {
  const verdict = legacyTriageVerdict({
    routeReason: "",
    routes: [
      { Decision: "queued", Reason: "on the timeline first - triage decides next" },
      { Decision: "file", Reason: "triage: fyi - Automatic reply with no ask." },
    ],
  });
  assert.deepEqual(verdict, {
    intent: "fyi", kind: "", profile: "", title: "", summary: "", checklist: [],
    why: "Automatic reply with no ask.", repository: "",
  });
});

test("an old task keeps its extracted work, checklist, worker, and repository", () => {
  const verdict = legacyTriageVerdict({
    routeReason: "triage: task - asks for a code change",
    task: { Kind: "coding", Title: "Fix exports", Summary: "Dana asked for the export fix.",
      Assignee: "agent:coding", Tags: "urgent,repo:acme/widgets" },
    checklist: [{ text: "Fix CSV quoting" }],
  });
  assert.equal(verdict.repository, "acme/widgets");
  assert.equal(verdict.profile, "coding");
  assert.deepEqual(verdict.checklist, ["Fix CSV quoting"]);
});

test("unknown response fields are not silently discarded", () => {
  assert.deepEqual(extraTriageFields({ intent: "task", why: "x", system: "ADP" }), [["system", "ADP"]]);
});

// the record leads with whose the work is (categories.route_head); a row written before says the classifier's label
test("a route's verdict reads the same in the new head and the old label", () => {
  for (const [reason, want] of [["triage: work for the coding agent in northwind/ledger - fix it · new task", "task"],
    ["triage: work for the assistant - book it", "task"], ["triage: yours to do - sign it", "task"], ["triage: task - old", "task"],
    ["triage: needs a reply - a question", "reply_only"], ["triage: reply_only - old", "reply_only"],
    ["triage: nothing to do - a notice", "fyi"], ["triage: fyi - old", "fyi"], ["not ours - you said so", ""]])
    assert.equal(routeIntent(reason), want, reason);
  assert.equal(routeWhy("triage: work for the coding agent in org/app - the export breaks · new task"), "the export breaks · new task");
  assert.equal(routeWhy("triage: task - old words"), "old words");
});
