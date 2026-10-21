// LINKEDIN, FROM ITS CARD (the owner, 2026-10-21: "LinkedIn is not working"). Two things stood between a person and a connected
// card: "link" typed over the open card showed the section chips and that card, never the matches; and the app's keys, saved,
// left Sign in with LinkedIn greyed under "Save first" until the card was closed and opened again. The demo refuses every
// connector write, so a save and the status after it are the server's own answers, stood in for at the page; nothing reaches
// LinkedIn - the fixture blocks every outbound request.
import assert from "node:assert/strict";
import test from "node:test";
import { clickNav, startHarness } from "./harness.mjs";

const until = (page, f, arg, timeout = 30000) => page.waitForFunction(f, { timeout, polling: 200 }, arg).catch(async (e) => {
  throw new Error(`${e.message} waiting for ${String(f).slice(0, 200)}\n${(await page.evaluate(() => document.body.innerText)).slice(-1500)}`);
});
const type = (page, sel, v) => page.evaluate((sel, v) => {
  const i = document.querySelector(sel), set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set;
  set.call(i, v); i.dispatchEvent(new Event("input", { bubbles: true }));
}, sel, v);
const titles = (page) => page.evaluate(() => [...document.querySelectorAll("[data-tq-browse-card]")].map((c) => c.innerText.split("\n")[0]));
const signIn = (page) => page.evaluate(() => {
  const b = [...document.querySelectorAll("[data-tq-browse-one] button")].find((x) => /Sign in with LinkedIn|Reconnect/.test(x.innerText));
  return b ? (b.disabled ? "disabled" : "enabled") : "missing";
});
const field = (page, label, v) => page.evaluate((label, v) => {
  const i = [...document.querySelectorAll("[data-tq-browse-one] input")].find((x) => x.closest(".MuiFormControl-root")?.querySelector("label")?.innerText.trim() === label);
  if (!i) return false;
  Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set.call(i, v); i.dispatchEvent(new Event("input", { bubbles: true }));
  return true;
}, label, v);

test("LinkedIn: typed finds its card at once, and the card connects in plain steps", { timeout: 600000 }, async (t) => {
  const harness = await startHarness(); t.after(() => harness.close());
  const page = await harness.newPage(), errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  const list = await (await fetch(`${harness.fixtureApi}/api/connectors`, { headers: { "X-Taskuary-Token": harness.token } })).json();
  const li = list.data.find((c) => c.Type === "linkedin");
  let saved = null, tested = 0;
  page.off("request", page.fixtureRequestGuard);
  page.on("request", (r) => {
    const u = new URL(r.url()), p = u.pathname, json = (body) => r.respond({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
    if (p === "/api/connectors" && r.method() === "POST") { saved = JSON.parse(r.postData() || "{}"); return json({ ok: true, connectorId: li.ConnectorId }); }
    if (p === "/api/connectors" && r.method() === "GET" && saved?.ConfigJson)
      return json({ ...list, data: list.data.map((c) => c.ConnectorId === li.ConnectorId ? { ...c, ConfigJson: saved.ConfigJson } : c) });
    if (p === `/api/connectors/${li.ConnectorId}/linkedin/status`)
      return json({ redirect_uri: "http://localhost:7999/api/linkedin/callback", connected: false, has_app: !!saved?.ConfigJson, member: "", days_left: null });
    if (p === `/api/connectors/${li.ConnectorId}/test`) { tested++; return json({ ok: false, ms: 3, detail: "LinkedIn is not signed in yet - save the app's Client ID and Client Secret on the LinkedIn card, then press Sign in with LinkedIn" }); }
    page.fixtureRequestGuard(r);
  });
  await page.goto(harness.ui, { waitUntil: "domcontentloaded", timeout: 90000 });
  await page.waitForSelector("[data-tq-nav='connections']", { timeout: 120000 });
  await clickNav(page, "Connections");
  await page.waitForSelector("[data-tq-browse-search]", { timeout: 30000 });

  // 1. the name typed lists its card first
  await type(page, "[data-tq-browse-search]", "link");
  await until(page, () => document.querySelectorAll("[data-tq-browse-card]").length > 0);
  assert.equal((await titles(page))[0], "LinkedIn", `LinkedIn leads the matches for "link": ${(await titles(page)).join(" | ")}`);
  await page.click(`[data-tq-browse-card="d${li.ConnectorId}"] [data-tq-card]`);
  await page.waitForSelector("[data-tq-browse-one]");

  // 2. words typed over the open card put it down and show the matches
  await type(page, "[data-tq-browse-search]", "bluesky");
  await until(page, () => !document.querySelector("[data-tq-browse-one]") && document.querySelectorAll("[data-tq-browse-card]").length > 0);
  assert.equal((await titles(page))[0], "Bluesky");
  await type(page, "[data-tq-browse-search]", "linkedin");
  await until(page, () => document.querySelectorAll("[data-tq-browse-card]").length > 0);
  await page.click(`[data-tq-browse-card="d${li.ConnectorId}"] [data-tq-card]`);
  await page.waitForSelector("[data-tq-browse-one]");

  // 3. the card: plain fields that say where each comes from, Sign in held until the keys are saved, AI setup only a helper
  const text = await page.evaluate(() => document.querySelector("[data-tq-browse-one]").innerText);
  for (const want of ["Client ID", "developer.linkedin.com/apps → your app → Auth tab → Client ID", "Client Secret", "Sign in with LinkedIn",
    "Nothing to paste here", "Optional - the card below connects without it", "Add another LinkedIn account"]) assert.ok(text.includes(want), `the card says "${want}"`);
  assert.equal(await signIn(page), "disabled", "Sign in waits for the app's keys");
  const aiFilled = await page.evaluate(() => [...document.querySelectorAll("[data-tq-browse-one] button")].find((b) => b.innerText.trim() === "Get AI to set it up")?.className.includes("contained"));
  assert.equal(aiFilled, false, "Get AI to set it up is not the card's filled button");
  assert.ok(await field(page, "Client ID", "test-client-id-0001"));
  assert.ok(await field(page, "Client Secret", "test-client-secret-0001"));
  await page.evaluate(() => [...document.querySelectorAll("[data-tq-browse-one] button")].find((b) => b.innerText.trim() === "Save").click());
  await until(page, () => /saved ✓/.test(document.querySelector("[data-tq-browse-one]").innerText));
  assert.deepEqual(JSON.parse(saved.ConfigJson), { client_id: "test-client-id-0001", client_secret: "test-client-secret-0001" });
  await until(page, () => [...document.querySelectorAll("[data-tq-browse-one] button")].some((x) => /Sign in with LinkedIn/.test(x.innerText) && !x.disabled));
  assert.equal(await signIn(page), "enabled", "saved keys unlock Sign in without reopening the card");

  // 4. Test says plainly what is missing
  await page.evaluate(() => [...document.querySelectorAll("[data-tq-browse-one] button")].find((b) => b.innerText.trim() === "Test").click());
  await until(page, () => /press Sign in with LinkedIn/.test(document.querySelector("[data-tq-browse-one]").innerText));
  assert.equal(tested, 1);
  if (process.env.TASKUARY_SHOTS) await page.screenshot({ path: `${process.env.TASKUARY_SHOTS}/linkedin-card-after.png` });
  assert.deepEqual(errors, []);
});
