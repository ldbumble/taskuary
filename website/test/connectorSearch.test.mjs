// THE CONNECTIONS BOX AND THE LINKEDIN CARD (the owner, 2026-10-21: "LinkedIn is not working" - "link" typed over the open
// LinkedIn card showed the section chips and that card, no matches; the card's keys saved left Sign in greyed).
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { matchCards } from "../src/connectorCatalog.js";

const src = fs.readFileSync(path.join(process.cwd(), "src", "ConnectorsView.jsx"), "utf8");
const card = (title, channel, haystack, planned = false) => ({ key: channel, title, channel, haystack, planned });
const groups = [
  { title: "Email", cards: [card("Outlook mail", "outlook", "outlook microsoft mail ... the approval link ...")] },
  { title: "Messaging", cards: [card("WhatsApp", "whatsapp", "whatsapp phone linked devices")] },
  { title: "Social", cards: [card("LinkedIn", "linkedin", "linkedin publish"), card("Bluesky", "bluesky", "bluesky app password")] },
  { title: "Project management", cards: [card("Linear", "linear", "linear issues")] },
  { title: "Everything else", cards: [card("Plaid", "plaid", "plaid linked-account aggregator planned", true)] },
];

test("a connector's name typed lists its card first, before cards whose guide only mentions the word", () => {
  const hits = matchCards(groups, "link");
  assert.equal(hits[0].title, "LinkedIn");
  assert.deepEqual(hits.map((h) => h.title), ["LinkedIn", "Outlook mail", "WhatsApp", "Plaid"]);
  assert.equal(hits[0].crumb, "Social", "a match still says which section it is from");
  assert.deepEqual(matchCards(groups, "LinkedIn").map((h) => h.title), ["LinkedIn"], "case does not matter");
});

test("nothing typed is no matches; several names at once, comma-separated, each lead", () => {
  assert.deepEqual(matchCards(groups, ""), []);
  assert.deepEqual(matchCards(groups, "  ,  "), []);
  assert.deepEqual(matchCards(groups, "bluesky, linear").map((h) => h.title), ["Bluesky", "Linear"]);
});

test("words typed put an open card down, so the matches are what shows", () => {
  assert.match(src, /const search = \(v\) => \{ setQ\(v\); if \(v\.trim\(\) && open\) back\(\); \};/);
  assert.ok(src.includes('onChange={(e) => search(e.target.value)} placeholder="Search connectors…"'), "the canvas box searches through it");
  assert.match(src, /<SideRail title="Connections" q=\{q\} setQ=\{search\}/);
  assert.doesNotMatch(src, /onChange=\{\(e\) => setQ\(e\.target\.value\)\} placeholder="Search connectors…"/);
});

test("a sign-in card reads its status again when its keys are saved", () => {
  const box = src.slice(src.indexOf("function OAuthConnect("), src.indexOf("function DataDetail("));
  assert.match(box, /\[conn\.ConnectorId, conn\.ConfigJson, conn\.HasSecret, meta\]/);
  assert.match(box, /st\.member \? ` as \$\{st\.member\}`/, "connected says as whom");
});

test("the LinkedIn card asks in plain words and says where each comes from; AI setup is the optional helper", () => {
  const li = src.slice(src.indexOf('  linkedin: { title: "LinkedIn"'), src.indexOf("  treg: { title:"));
  assert.match(li, /\["Client ID", "client_id", "", "developer\.linkedin\.com\/apps → your app → Auth tab → Client ID"\]/);
  assert.match(li, /\["Client Secret", "client_secret", "", "The same Auth tab/);
  assert.match(li, /label: "Sign in with LinkedIn"/);
  assert.match(li, /secretHelp: "Nothing to paste here/);
  assert.match(src, /\[label, key, ph, help\]\) => \(\s*<TextField key=\{key\} label=\{label\} placeholder=\{ph\} helperText=\{help\}/);
  const ai = src.slice(src.indexOf("const AiSetup ="), src.indexOf("const GATEWAY_HINT"));
  assert.match(ai, /Optional - the card below connects without it/);
  assert.match(ai, /<Button variant="outlined" disabled=\{busy\} onClick=\{start\}/, "not the page's one filled button");
});
