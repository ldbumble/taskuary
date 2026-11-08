import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
const read = (n) => fs.readFileSync(path.join(process.cwd(), "src", n), "utf8");
import { CATALOGUE, PLANNED_CONNECTORS, onceEach, plannedFor } from "../src/connectorCatalog.js";
import { AI_SHELF } from "../src/aiShelf.js";

const CATEGORIES = [
  "AI — agents & models", "AI — voice", "Email", "Messaging", "Developer",
  "Project management", "Databases", "Cloud & infrastructure", "Corporate systems",
  "Markets & finance", "Observability", "Agentic web", "Files & sheets", "Everything else",
  // Social arrived last because it had NO roadmap at all until Bluesky and Mastodon were built
  // (2026-09-22) - a category holding two working cards and nothing else reads as a finished
  // subject. The order is the catalogue's own, by where each group's first planned card sits.
  "Social",
];

// THE ROADMAP EMPTIES AS IT IS BUILT (the owner, 2026-11-08: "all the ones that say coming soon just add them now"): a category is
// judged by every card it holds, working or planned, and the planned ones are only those no road reaches yet
test("every connector category holds several cards, working or planned", () => {
  const groups = new Set(CATALOGUE.map((c) => c.group));
  for (const category of CATEGORIES) {
    assert.ok(groups.has(category), category);
    assert.ok(CATALOGUE.filter((c) => c.group === category).length >= 5, `${category} should not look empty`);
  }
  for (const category of Object.keys(PLANNED_CONNECTORS)) assert.ok(CATEGORIES.includes(category), category);
  assert.equal(plannedFor("AI — agents & models").length, 0);      // every model provider on the roadmap now has a card
});

test("the requested Grok API connector is BUILT, not merely planned", () => {
  // it was a roadmap entry; it speaks the OpenAI surface, so it became a real card. A type that
  // is live must not also sit on the roadmap, or Connections draws it twice.
  assert.equal(plannedFor("AI — agents & models").find((c) => c.type === "xai"), undefined);
  const view = read("ConnectorsView.jsx");
  assert.match(view, /^ {2}xai: \{ group: "AI — agents & models"/m);
  assert.ok(AI_SHELF.includes("xai"));
});

test("Everything else is a useful catalog rather than an empty bucket", () => {
  // ten planned until the vendors' own MCP servers made Intercom, PayPal and Calendly working cards here (remotemcp.py, 2026-11-08)
  const entries = plannedFor("Everything else");
  assert.ok(entries.length >= 5);
  assert.ok(CATALOGUE.filter((c) => c.group === "Everything else" && c.mcp && !c.planned).length >= 10);
  assert.ok(entries.some((c) => c.type === "shopify"));      // stripe was the example here until it was built (2026-11-01)
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

test("every card in the catalogue, working or planned, has a one-line description", () => {
  const blank = CATALOGUE.filter((c) => !String(c.desc || "").trim()).map((c) => c.type);
  assert.deepEqual(blank, []);
  const multiline = CATALOGUE.filter((c) => /\n/.test(c.desc)).map((c) => c.type);
  assert.deepEqual(multiline, []);
});

test("unknown categories safely return no entries", () => {
  assert.deepEqual(plannedFor("not a category"), []);
});

// the server's planned list and this catalogue name the same systems apart: PointClickCare drew twice, once under Corporate systems by
// its catalogue name and once as a bare "pointclickcare" under Everything else (2026-10-19 UI walk)
test("each connector type is drawn once: a planned card never repeats a live one or an earlier planned one", () => {
  const groups = onceEach([
    { title: "Corporate systems", cards: [{ key: "catalog-pcc", type: "pointclickcare", planned: true }, { key: "d1", channel: "intacct" }] },
    { title: "Agentic web", cards: [{ key: "catalog-x", type: "exa", planned: true }, { key: "d2", channel: "exa" }, { key: "d3", channel: "exa" }] },
    { title: "Everything else", cards: [{ key: "ppointclickcare", channel: "pointclickcare", planned: true }, { key: "pgraphql", channel: "graphql", planned: true }] },
  ]);
  assert.deepEqual(groups.map((g) => g.cards.map((c) => c.key)), [["catalog-pcc", "d1"], ["d2", "d3"], ["pgraphql"]]);
  assert.match(read("ConnectorsView.jsx"), /const groups = onceEach\(\[/, "the page's groups go through onceEach");
});
