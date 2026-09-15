import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  extraTriageFields, intentLabel, kindLabel, latestTriageVerdict, legacyTriageVerdict,
  parseTriageVerdict, relationshipLabel,
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
      Assignee: "agent:coder", Tags: "urgent,repo:acme/widgets" },
    checklist: [{ text: "Fix CSV quoting" }],
  });
  assert.equal(verdict.repository, "acme/widgets");
  assert.equal(verdict.profile, "coder");
  assert.deepEqual(verdict.checklist, ["Fix CSV quoting"]);
});

test("unknown response fields are not silently discarded", () => {
  assert.deepEqual(extraTriageFields({ intent: "task", why: "x", system: "ADP" }), [["system", "ADP"]]);
});

test("the timeline draws the response as facts, repository, and a numbered task list", () => {
  const view = readFileSync(new URL("../src/FeedView.jsx", import.meta.url), "utf8");
  assert.ok(view.includes("Full triage response"));
  assert.ok(view.includes("Triage's structured response"));
  assert.ok(view.includes('label="Goes to"'));
  assert.ok(view.includes("Repository choice needed"));
  assert.ok(view.includes('component="ol"'));
  assert.ok(view.includes("No separate checklist was returned."));
  assert.ok(view.includes("limited saved response · reconstructed"));
  assert.ok(view.includes("None — triage found no requested action."));
  assert.ok(view.includes("This route was saved without structured triage details."));
});
