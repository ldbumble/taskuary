// SETTINGS IS FOUND BY ITS PLACES (the owner, 2026-11-10: "do not see agent permissions in settings just searched for it", "don't see
// the vault settings either for saved passwords. where is it?"). The Settings list's search read only the knobs' words: a section
// was found by no word of its name, and a panel - the saved sign-ins, the tools that send - by no word at all.
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import schema from "../../taskuary/settings_schema.json" with { type: "json" };
import { placeHits } from "../src/settingsSearch.js";
import { ABOUT_SECTIONS, AUDIT_SECTIONS } from "../src/settingsMap.js";

const read = (f) => fs.readFileSync(path.join(process.cwd(), "src", f), "utf8");
const pages = { about: { title: "About you" }, config: { title: "Configuration" }, policies: { title: "Mail rules" },
  phone: { title: "Phone & chats" }, audit: { title: "Activity log" }, updates: { title: "Updates" } };
const sections = { about: ABOUT_SECTIONS, config: schema.groups, audit: AUDIT_SECTIONS };
const find = (q) => placeHits(q, { schema, sections, pages });

test("the saved sign-ins and Agent permissions are found by the words a person types", () => {
  for (const q of ["agent permissions", "Agent Permissions", "password", "vault", "saved sign", "sign-in", "login"]) {
    const h = find(q).find((x) => x.page === "config" && x.section === "Agent permissions");
    assert.ok(h, `"${q}" finds a place in Configuration → Agent permissions`);
    assert.equal(h.crumb, "Configuration → Agent permissions");
  }
  const v = find("password vault").find((x) => x.knob === "panel:signins");
  assert.ok(v, "the vault itself, not only its section");
  assert.equal(v.label, "Saved sign-ins", "labelled with the panel's own heading");
});

test("every section of every page is found by its own name, and every page by its title", () => {
  for (const [pg, names] of Object.entries(sections))
    for (const n of names) assert.ok(find(n).some((h) => h.page === pg && h.section === n && !h.knob), `${pg} → ${n}`);
  for (const [pg, p] of Object.entries(pages).filter(([pg]) => !sections[pg]))
    assert.ok(find(p.title).some((h) => h.page === pg), p.title);
  assert.deepEqual(find("  "), [], "nothing typed, nothing found");
});

test("every panel has a heading, words and a section the page draws, and the page lands on it", () => {
  const view = read("SettingsView.jsx");
  for (const [k, p] of Object.entries(schema.panels)) {
    assert.ok(p.title && p.words && schema.groups.includes(p.group), k);
    assert.ok(view.includes(`panel("${k}"`), `SettingsView wraps ${k}, the anchor its hit scrolls to`);
  }
  assert.equal((view.match(/placeHits\(/g) || []).length, 2, "both Settings searches - the list's and the page's - ask the same function");
});

test("Connections' Saved sign-ins card is found by the same words, not a second copy", () => {
  const c = read("ConnectorsView.jsx");
  assert.match(c, /haystack: schema\.panels\["panel:signins"\]\.words/);
  assert.doesNotMatch(c, /haystack: "sign in signin/);
});
