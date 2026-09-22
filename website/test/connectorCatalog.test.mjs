import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
const read = (n) => fs.readFileSync(path.join(process.cwd(), "src", n), "utf8");
import { PLANNED_CONNECTORS, plannedFor } from "../src/connectorCatalog.js";

const CATEGORIES = [
  "AI — agents & models", "AI — voice", "Email", "Messaging", "Developer",
  "Project management", "Databases", "Cloud & infrastructure", "Corporate systems",
  "Markets & finance", "Observability", "Agentic web", "Files & sheets", "Everything else",
];

test("every connector category has several roadmap entries", () => {
  assert.deepEqual(Object.keys(PLANNED_CONNECTORS), CATEGORIES);
  for (const category of CATEGORIES) {
    assert.ok(plannedFor(category).length >= 5, `${category} should not look empty`);
  }
});

test("the requested Grok API connector is BUILT, not merely planned", () => {
  // it was a roadmap entry; it speaks the OpenAI surface, so it became a real card. A type that
  // is live must not also sit on the roadmap, or Connections draws it twice.
  assert.equal(plannedFor("AI — agents & models").find((c) => c.type === "xai"), undefined);
  const view = read("ConnectorsView.jsx");
  assert.match(view, /^ {2}xai: \{ group: "AI — agents & models"/m);
  assert.match(view, /"xai"/);
});

test("Everything else is a useful catalog rather than an empty bucket", () => {
  const entries = plannedFor("Everything else");
  assert.ok(entries.length >= 10);
  assert.ok(entries.some((c) => c.type === "stripe"));
  assert.ok(entries.some((c) => c.type === "docusign"));
});

test("catalog identifiers are unique and every card has searchable copy", () => {
  const entries = Object.values(PLANNED_CONNECTORS).flat();
  assert.equal(new Set(entries.map((c) => c.type)).size, entries.length);
  for (const entry of entries) {
    assert.match(entry.type, /^[a-z][a-z0-9_]*$/);
    assert.ok(entry.title.trim());
    assert.ok(entry.desc.trim());
  }
});

test("unknown categories safely return no entries", () => {
  assert.deepEqual(plannedFor("not a category"), []);
});
