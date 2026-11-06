// SETTINGS > PHONE & CHATS (the owner, 2026-11-06: "it's not clear where that is"): one page for the Assistant chat on the phone and, in
// Developer mode only, the chats bound to coding agents.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { PHONE_GROUP, SETUP_STEPS, bindingRow, canHandOver, doorwayStatus, phoneSections } from "../src/phoneChats.js";
import { SETTINGS_PAGES, canvasRequestFromHash, hashFor } from "../src/canvasLinks.js";

const read = (name) => readFileSync(fileURLToPath(new URL(`../src/${name}`, import.meta.url)), "utf8");

test("Agent channels are drawn only in Developer mode; the Assistant section always is", () => {
  assert.deepEqual(phoneSections({ devMode: false }), ["assistant"]);
  assert.deepEqual(phoneSections(), ["assistant"]);
  assert.deepEqual(phoneSections({ devMode: true }), ["assistant", "agents"]);
  // ...and the page asks phoneSections, with the Settings view's own devMode - never a section drawn by itself
  const page = read("PhoneChats.jsx");
  assert.match(page, /phoneSections\(\{ devMode \}\)/);
  assert.match(page, /secs\.includes\("agents"\) && \(/);
  assert.match(read("SettingsView.jsx"), /<PhoneChats devMode=\{devMode\}/);
});

test("each Assistant chat says where it stands, in words", () => {
  const wa = { channel: "whatsapp", live: true, chat: "15550001111@s.whatsapp.net", listens: "walk" };
  assert.equal(doorwayStatus({ channel: "telegram", live: false }).state, "off");
  assert.match(doorwayStatus({ channel: "telegram", live: false }).line, /^Telegram is not switched on/);
  assert.equal(doorwayStatus({ ...wa, chat: "" }).state, "unset");
  assert.equal(doorwayStatus(wa).state, "walk");
  assert.equal(doorwayStatus({ ...wa, listens: "always" }).state, "on");
  assert.equal(doorwayStatus(wa, { channel: "whatsapp", chat: wa.chat }).state, "walking");
  // a walk out on the other channel is not this one's
  assert.equal(doorwayStatus(wa, { channel: "telegram", chat: "4242" }).state, "walk");
  assert.ok(SETUP_STEPS.whatsapp.length && SETUP_STEPS.telegram.length);
});

test("the walk is offered only where it can go, and not twice", () => {
  const tg = { channel: "telegram", live: true, chat: "4242", listens: "always" };
  assert.equal(canHandOver(tg), true);
  assert.equal(canHandOver({ ...tg, chat: "" }), false);
  assert.equal(canHandOver({ ...tg, live: false }), false);
  assert.equal(canHandOver(tg, { channel: "telegram", chat: "4242" }), false, "already walking there: Walk it here instead");
});

test("a binding reads as what it talks to, where, and with whom", () => {
  const one = bindingRow({ id: 3, kind: "slack", label: "Slack", chat: "C0LEDGER", task: 12, ref: "TQ-0012", repoName: "northwind/ledger",
    members: [{ name: "Alex Doyle", role: "owner" }, { name: "Gail Moreno", role: "teammate" }, { name: "Ray Colton", role: "teammate" }] });
  assert.deepEqual(one, { id: 3, channel: "Slack", chat: "C0LEDGER", what: "TQ-0012's agent", href: "#task=12", repo: "northwind/ledger",
    people: "you, Gail Moreno, Ray Colton" });
  const all = bindingRow({ id: 4, kind: "telegram", label: "Telegram", chat: "4242", task: null, members: [{ name: "Alex Doyle", role: "owner" }] });
  assert.equal(all.what, "the coding agents");
  assert.equal(all.href, "");
  assert.equal(all.repo, "any repository");
  assert.equal(all.people, "you");
});

test("#settings=phone opens the page, and an old link to the phone group lands there with its knob", () => {
  assert.ok(SETTINGS_PAGES.includes("phone"));
  assert.deepEqual(canvasRequestFromHash("#settings=phone", 1), { kind: "browse", area: "settings", state: { section: "phone", open: "phone" }, n: 1 });
  const old = canvasRequestFromHash(`#settings=config&group=${encodeURIComponent(PHONE_GROUP)}&key=phone_morning_line`, 2);
  assert.deepEqual(old.state, { section: "phone", open: "phone", knob: "phone_morning_line" });
  assert.equal(hashFor("settings", old.state), "#settings=phone&key=phone_morning_line");
  assert.equal(hashFor("settings", { section: "phone", open: "phone" }), "#settings=phone");
});

test("the phone group is Phone & chats', not a Configuration group too; the cards link there", () => {
  const s = read("SettingsView.jsx");
  assert.match(s, /g !== PHONE_GROUP && \(panels\[g\]/);
  assert.doesNotMatch(s, /"Assistant on your phone": <PhoneDoorways/);
  assert.match(read("ConnectorsView.jsx"), /openAppLink\("settings=phone"\)/);
});
