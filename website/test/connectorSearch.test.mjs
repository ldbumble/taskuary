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


test("an app's client secret is a masked, write-only box that says it is saved (guard.WRITE_ONLY_CONFIG)", () => {
  assert.match(src, /if \(!\(conn\?\.WriteOnlyKeys \|\| \[\]\)\.includes\(key\)\)[\s\S]{0,200}return <TextField type="password" data-tq-write-only=\{key\}/);
  assert.match(src, /`\$\{label\} — saved, type to replace`/);
  assert.match(src, /Object\.fromEntries\(Object\.entries\(cfg\)\.filter\(\(\[k\]\) => !\(conn\?\.WriteOnlyKeys \|\| \[\]\)\.includes\(k\)\)\)/, "typed, then saved, the box empties");
});
