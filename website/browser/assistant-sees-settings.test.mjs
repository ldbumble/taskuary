import assert from "node:assert/strict";
import test from "node:test";

import { clickNav, startHarness } from "./harness.mjs";
import { api, ask, scriptChat, shot, sleep, stepRows, until } from "./sees-page.mjs";

/* "TURN OFF X" OVER SETTINGS FINDS THE SETTING AND TURNS IT OFF (the owner, 2026-10-30: "It can find the right setting on the Settings page
   and turn it off"). Asked over the Settings page, the scripted answer opens the setting's group - the way its card opens it - and flips
   its own switch, which saves the way the owner's click saves (PATCH /api/settings). Each is a step in the chat. */

const WANT = ["advisor_events", "sign_replies", "playbooks_enabled", "intent_classify_enabled", "calendar_enabled"];

test("Settings: asked to turn a setting off, it opens its group and flips its own switch", { timeout: 300000 }, async (t) => {
  const harness = await startHarness();
  t.after(() => harness.close());
  const page = await harness.newPage();
  await page.setViewport({ width: 1600, height: 900, deviceScaleFactor: 1 });
  const errors = [], patched = [];
  page.on("pageerror", (e) => errors.push(e.message));
  const settings = (await api(harness, "/api/settings")).data || [];
  const schema = await api(harness, "/api/settings/schema").catch(() => ({}));
  const on = WANT.map((k) => settings.find((s) => s.Name === k && String(s.Value) === "1")).find(Boolean);
  assert.ok(on, "a switch that is on in the demo");
  const group = schema?.knobs?.[on.Name]?.group || { advisor_events: "Advisor", sign_replies: "Replies", playbooks_enabled: "How mail is sorted",
    intent_classify_enabled: "How mail is sorted", calendar_enabled: "Replies" }[on.Name];
  const turns = scriptChat(page, harness, () => ({ say: "Turned it off.", view_ops: [
    { op: "open", area: "settings", section: "config", open: group, knob: on.Name }, { op: "set", field: on.Name, value: "off" }] }),
  (req, url) => { if (req.method() === "PATCH" && url.pathname === "/api/settings") patched.push(JSON.parse(req.postData() || "{}")); return false; });
  await page.goto(harness.ui, { waitUntil: "domcontentloaded", timeout: 30000 });
  await page.waitForSelector("[data-tq-nav='settings']", { timeout: 60000 });
  await clickNav(page, "Settings");
  await page.waitForSelector("[data-tq-browse='settings'] [data-tq-browse-chip]", { timeout: 30000 });
  await sleep(800);
  await shot(page, "settings", "1-settings-page");

  await ask(page, "turn off that setting for me");
  await until(page, (k) => !!document.querySelector(`[data-tq-knob~="${k}"]`), on.Name);
  await until(page, () => /Turned off/.test([...document.querySelectorAll(".tq-chat-pop .tq-aui-step")].map((x) => x.innerText).join(" ")));
  assert.equal(turns[0].view?.area, "settings", "the page it was asked over went with the line");
  const rows = await stepRows(page);
  assert.match(rows[0], /^Opened /);
  assert.match(rows[1], /^Turned off /);
  for (let i = 0; i < 40 && !patched.length; i++) await sleep(150);
  assert.deepEqual(patched, [{ name: on.Name, value: "0" }], "saved the way the switch's own click saves");
  let now = null;
  for (let i = 0; i < 40; i++) { now = ((await api(harness, "/api/settings")).data || []).find((s) => s.Name === on.Name); if (String(now?.Value) === "0") break; await sleep(250); }
  assert.equal(String(now?.Value), "0", "the setting is off");
  assert.equal(await page.$eval(`[data-tq-knob~="${on.Name}"] input[type=checkbox]`, (e) => e.checked), false, "its switch shows it");
  await shot(page, "settings", "2-switch-turned-off");
  assert.deepEqual(errors, []);
});
