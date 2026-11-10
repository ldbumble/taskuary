// CONNECTED IS SAID, NEVER ASSUMED, AND ONE CARD PER SYSTEM (the owner, 2026-11-10: "why is there regualr and mcp and why is mcp green?
// it says not added but then green. come on"). A card's state was read off its status line and anything that did not read "off"
// was on: every vendor MCP card's "not added" wore the green ring and the Connected pill, beside the same system's own card.
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { CATALOGUE, NOT_SET_UP, WAYS, WAY_NAMES, cardState, oneCardPerSystem, waysOf, wayState } from "../src/connectorCatalog.js";

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
  // ...Basecamp and Jira too: the MCP-only card of each is the same system under another name (the owner, 2026-11-10)
  for (const [m, n] of [["basecamp", "basecamp_todos"], ["atlassian", "jira"]]) assert.equal(CATALOGUE.find((c) => c.type === m).system, n);
  assert.ok(!CATALOGUE.some((c) => / MCP$/.test(c.title)), "no entry is named for its road");
});

// TWO WAYS IN, TWO EQUAL CHOICES (the owner, 2026-11-10: "it's mcp vs api for cards. there should be 2 options.. yes"): on a system's one card
// its own connector and its vendor's MCP server, each with its own setup and state - not a section under Remove
test("a system with both ways offers API and MCP at the top of its page, each its own setup and state; one way offers no choice", () => {
  const api = { ConnectorId: 1, Type: "airtable", Name: "Airtable", Active: 0 }, mcp = { ConnectorId: 2, Type: "airtable_mcp", Name: "Airtable MCP", Active: 1 };
  const byType = { airtable: api, airtable_mcp: mcp, linear: { ConnectorId: 3, Type: "linear" } };
  assert.deepEqual(waysOf(api, byType), { API: api, MCP: mcp }, "opened by its own card");
  assert.deepEqual(waysOf(mcp, byType), { API: api, MCP: mcp }, "opened by its MCP row");
  assert.equal(waysOf({ Type: "slack" }, byType), null, "a system with one way has no choice");
  assert.equal(waysOf(api, { airtable: api }), null, "no MCP row here: no choice");
  assert.deepEqual([wayState("API", api), wayState("MCP", mcp)], [NOT_SET_UP, "set up"]);
  assert.equal(wayState("API", { LastSyncAt: "2026-11-10 09:00:00" }), "set up", "a data card set up by its reads");
  assert.deepEqual(WAY_NAMES, ["API", "MCP"]);
  assert.ok(WAY_NAMES.every((w) => WAYS[w] && WAYS[w].split(/[.!?] /).length === 1), "one plain sentence under each");
  for (const w of WAY_NAMES) assert.doesNotMatch(WAYS[w], /CLI|MCP|sign-in or key/, `${w} says it without jargon`);
  // ...drawn with the page's own tabs, the chosen way's own page under them; choosing opens that way's row
  assert.match(src, /const ways = waysOf\(conn, byType\);/);
  assert.match(src, /onWay=\{\(w\) => setOpen\(\{ kind: "connector", id: ways\[w\]\.ConnectorId \}\)\}/);
  assert.match(src, /\{choice\}\{page\}/, "the choice at the top, the chosen way's setup under it");
  assert.match(src, /<UnderTabs tabs=\{WAY_NAMES\} value=\{at\}/);
  assert.doesNotMatch(src, /McpDoor|For your agents/, "no section tucked under Remove");
  // ...and the grid's one card reads connected when either way is
  const draw = (a, m) => oneCardPerSystem([{ title: "x", cards: [{ key: "c1", type: "airtable", desc: a }, { key: "s2", channel: "airtable_mcp", desc: m }] }])[0].cards;
  assert.equal(cardState(draw(NOT_SET_UP, "added · your agents can use it")[0]), "on");
  assert.equal(cardState(draw("connection ✓ · 1 report (built under Reports)", NOT_SET_UP)[0]), "on");
  assert.equal(cardState(draw(NOT_SET_UP, NOT_SET_UP)[0]), "off");
});
