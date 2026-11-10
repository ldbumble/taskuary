// CONNECTED IS SAID, NEVER ASSUMED, AND ONE CARD PER SYSTEM (the owner, 2026-11-10: "why is there regualr and mcp and why is mcp green?
// it says not added but then green. come on"). A card's state was read off its status line and anything that did not read "off"
// was on: every vendor MCP card's "not added" wore the green ring and the Connected pill, beside the same system's own card.
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { CATALOGUE, NOT_SET_UP, cardState, oneCardPerSystem } from "../src/connectorCatalog.js";

const src = fs.readFileSync(path.join(process.cwd(), "src", "ConnectorsView.jsx"), "utf8");

test("only a card whose line says it is on is on - never green without an active connection", () => {
  for (const desc of ["not added", NOT_SET_UP, "Choose built-in dictation and test the microphone. No API key.", "", undefined,
    "off · trigger · 0/0 table", "off · tool · no key yet"]) assert.notEqual(cardState({ desc }), "on", String(desc));
  for (const desc of ["on · trigger · 1/1 table", "added · your agents can use it", "connection ✓ · 2 reports (built under Reports)"])
    assert.equal(cardState({ desc }), "on", desc);
  assert.equal(cardState({ desc: "on · tool · last test failed" }), "failing");
  assert.equal(cardState({ desc: "anything", guide: true }), "guide");
  assert.match(src, /const connState = cardState;/, "the card reads the one rule");
  assert.match(src, /\{connState\(c\) === "on" && !c\.plain && \(/, "the pill shows only on an on card");
  assert.match(src, /const toolDesc = \(c\) => \(c\.Active \? "added · your agents can use it" : NOT_SET_UP\);/, "an MCP card not added says what the rest say");
  assert.doesNotMatch(src, /: "not added"\)/);
});

test("a system with its own card and an MCP entry is drawn as one card, named for the system", () => {
  const mcp = (on) => ({ key: "s9", channel: "airtable_mcp", title: "Airtable", desc: on ? "added · your agents can use it" : NOT_SET_UP, haystack: "airtable_mcp agent tools" });
  const native = { key: "c1", type: "airtable", title: "Airtable", desc: "off · trigger · 0/0 table", haystack: "Airtable airtable" };
  const draw = (m) => oneCardPerSystem([{ title: "Project management", cards: [native, { key: "c2", type: "linear", desc: "off" }] },
    { title: "Elsewhere", cards: [m] }]);
  const off = draw(mcp(false)).flatMap((g) => g.cards);
  assert.deepEqual(off.map((c) => c.key), ["c1", "c2"], "the MCP entry is not a card of its own");
  assert.notEqual(cardState(off[0]), "on");
  assert.match(off[0].haystack, /mcp/, "searching mcp still finds it");
  const on = draw(mcp(true)).flatMap((g) => g.cards)[0];
  assert.equal(cardState(on), "on", "connected by the MCP road shows as the one card connected");
  // no native card on the page: the MCP card stays, the only card for its system
  assert.deepEqual(oneCardPerSystem([{ title: "x", cards: [mcp(false)] }])[0].cards.map((c) => c.key), ["s9"]);
  assert.match(src, /title: String\(c\.Name \|\| title\)\.replace\(\/\\s\+MCP\$\/i, ""\)/, "no card is named for its road");
});

test("every MCP entry the catalogue ties to a system ties to a working card of another kind", () => {
  const tied = CATALOGUE.filter((c) => c.system);
  assert.ok(tied.length >= 20);
  for (const c of tied) {
    const n = CATALOGUE.find((x) => x.type === c.system);
    assert.ok(c.mcp && n && !n.mcp && !n.planned, c.type);
  }
  assert.match(src, /const groups = oneCardPerSystem\(onceEach\(\[/);
  assert.match(src, /\{page\}\{door\}/, "the MCP server is offered inside the system's card");
});
