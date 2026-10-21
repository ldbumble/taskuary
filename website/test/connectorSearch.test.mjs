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
  assert.match(src, /return <TextField label=\{label\} placeholder=\{ph \|\| ""\} helperText=\{help\}/);   // ConfigField: the help under the box
});

test("Get AI to set it up is a button in the card's own row, and its walk is drawn on the card - no terminal", () => {
  const ai = src.slice(src.indexOf("function useAiWalk("), src.indexOf("const GATEWAY_HINT"));
  assert.match(ai, /<Button variant="outlined" disabled=\{ai\.busy \|\| !ai\.ready\.ok\} onClick=\{ai\.start\} data-tq-ai-setup="start"/, "outlined, never the card's filled button");
  assert.doesNotMatch(ai, /TerminalPane/, "the walk is the general agent's, not a terminal");
  for (const path of ['post("", ctx', 'post("/say", { ...ctx, saved: labels }', 'post("/say", { ...ctx, text }', 'post("/done"']) assert.ok(ai.includes(path), path);
  assert.match(ai, /stop = lightField\(root, label\)/, "the field it asks for is lit");
  const data = src.slice(src.indexOf("function DataDetail("), src.indexOf("const ROLE_META"));
  assert.match(data, /<AiWalkButton ai=\{ai\} \/>\s*\{msg && /, "beside Save and Test");
  assert.match(data, /await api\.post\("\/api\/connectors", body\);\s*ai\.saved\(put\);/, "what Save put on the card is told to the walk");
  assert.doesNotMatch(data.slice(0, data.indexOf("<UnderTabs")), /<AiSetup|<AiWalk/, "nothing above the form");
});

test("an app's client secret is a masked, write-only box that says it is saved (guard.WRITE_ONLY_CONFIG)", () => {
  assert.match(src, /if \(!\(conn\?\.WriteOnlyKeys \|\| \[\]\)\.includes\(key\)\)[\s\S]{0,200}return <TextField type="password" data-tq-write-only=\{key\}/);
  assert.match(src, /`\$\{label\} — saved, type to replace`/);
  assert.match(src, /Object\.fromEntries\(Object\.entries\(cfg\)\.filter\(\(\[k\]\) => !\(conn\?\.WriteOnlyKeys \|\| \[\]\)\.includes\(k\)\)\)/, "typed, then saved, the box empties");
});
