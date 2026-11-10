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

// A category is never empty - but its roadmap may run out: the owner, 2026-11-08, "all the ones that say coming soon just add them
// now". So the guard is that each category holds cards, working or planned, and the roadmap names no category the page lacks.
test("every connector category holds cards, and the roadmap stays inside the categories", () => {
  for (const category of CATEGORIES) assert.ok(CATALOGUE.some((c) => c.group === category), `${category} should not look empty`);
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
  const all = CATALOGUE.filter((c) => c.group === "Everything else");
  assert.ok(all.length >= 10);
  // stripe was the example here until it was built (2026-11-01); shopify until it was (2026-11-08)
  assert.ok(all.some((c) => c.type === "shopify" && !c.planned));
  // ...and docusign until it was (2026-11-08): it signs in by OAuth now (oauth.py)
  assert.ok(all.some((c) => c.type === "docusign" && !c.planned));
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
  assert.match(read("ConnectorsView.jsx"), /const groups = oneCardPerSystem\(onceEach\(\[/, "the page's groups go through onceEach");
});

// Fastmail, Yahoo, Proton Mail Bridge and Exchange are IMAP cards with their servers filled in (the owner, 2026-11-08: "add more
// connections ... make them work well") - one press makes the card, the card remembers its preset, and the preset is not offered twice
test("a mailbox preset makes an IMAP card with its servers, and is offered until it exists", async () => {
  const { PRESETS, presetBody, presetOf, presetsLeft } = await import("../src/connectorCatalog.js");
  assert.deepEqual(Object.keys(PRESETS).sort(), ["exchange", "fastmail", "proton_mail", "yahoo_mail"]);
  const body = presetBody("proton_mail");
  assert.equal(body.Type, "imap"); assert.equal(body.Name, "Proton Mail");
  assert.deepEqual(JSON.parse(body.ConfigJson), { imap_host: "127.0.0.1", imap_port: 1143, imap_starttls: true, smtp_host: "127.0.0.1", smtp_port: 1025, preset: "proton_mail" });
  const made = { Type: "imap", ConfigJson: body.ConfigJson };
  assert.equal(presetOf(made).title, "Proton Mail");
  assert.equal(presetOf({ Type: "imap", ConfigJson: "{}" }), null);
  assert.equal(presetOf({ Type: "gmail", ConfigJson: body.ConfigJson }), null, "a preset belongs to its own card type");
  assert.deepEqual(presetsLeft(["fastmail", "proton_mail", "nope"], [made]), ["fastmail"]);
  const view = read("ConnectorsView.jsx");
  assert.match(view, /\.\.\.presetCards\(\["fastmail", "yahoo_mail", "proton_mail", "exchange"\]\)/);
  assert.match(view, /const m = metaOf\(conn\) \|\| \{ fields: \[\], howto: \[\] \};/);
});
