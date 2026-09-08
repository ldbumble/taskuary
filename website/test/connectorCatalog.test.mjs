import test from "node:test";
import assert from "node:assert/strict";
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

test("the requested Grok API connector is in the AI category", () => {
  const grok = plannedFor("AI — agents & models").find((c) => c.type === "xai");
  assert.deepEqual(grok, {
    type: "xai", title: "xAI (Grok API)", desc: "Grok models through xAI's API",
  });
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
