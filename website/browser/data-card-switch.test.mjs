// A DATA CARD, SAVED AND ABOUT TO BE REMOVED (#242, #238). Save sent the card on with every save, so editing a card the owner
// had turned off turned it back on; it now saves the settings only, and the card's own switch - beside Save, saved on the press
// (2026-10-23) - is what turns it on. Remove's row says what leans on the card before the press. The demo refuses connector writes, so
// the save and the dependents are the server's answers, stood in for at the page; nothing leaves the fixture.
import assert from "node:assert/strict";
import test from "node:test";
import { clickNav, startHarness } from "./harness.mjs";

const until = (page, f, arg, timeout = 30000) => page.waitForFunction(f, { timeout, polling: 200 }, arg).catch(async (e) => {
  throw new Error(`${e.message} waiting for ${String(f).slice(0, 200)}\n${(await page.evaluate(() => document.body.innerText)).slice(-1500)}`);
});
const type = (page, sel, v) => page.evaluate((sel, v) => {
  const i = document.querySelector(sel);
  Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set.call(i, v); i.dispatchEvent(new Event("input", { bubbles: true }));
}, sel, v);
const card = (page) => page.evaluate(() => document.querySelector("[data-tq-browse-one]").innerText);

test("a data card: Save keeps it off, its own switch turns it on, and Remove's row says what uses it", { timeout: 600000 }, async (t) => {
  const harness = await startHarness(); t.after(() => harness.close());
  const page = await harness.newPage(), errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  const list = await (await fetch(`${harness.fixtureApi}/api/connectors`, { headers: { "X-Taskuary-Token": harness.token } })).json();
  const pm = list.data.find((c) => c.Type === "prometheus");
  const posts = [];
  page.off("request", page.fixtureRequestGuard);
  page.on("request", (r) => {
    const p = new URL(r.url()).pathname, json = (body) => r.respond({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
    if (p === "/api/connectors" && r.method() === "POST") { posts.push(JSON.parse(r.postData() || "{}")); return json({ ok: true, connectorId: pm.ConnectorId }); }
    if (p === `/api/connectors/${pm.ConnectorId}/uses`)
      return json({ data: [{ kind: "workflow", names: ["Month close", "Invoice run"] }, { kind: "report", names: ["Morning sales"] }] });
    page.fixtureRequestGuard(r);
  });
  await page.goto(harness.ui, { waitUntil: "domcontentloaded", timeout: 90000 });
  await page.waitForSelector("[data-tq-nav='connections']", { timeout: 120000 });
  await clickNav(page, "Connections");
  await page.waitForSelector("[data-tq-browse-search]", { timeout: 30000 });
  await type(page, "[data-tq-browse-search]", "prometheus");
  await page.waitForSelector(`[data-tq-browse-card="d${pm.ConnectorId}"] [data-tq-card]`);
  await page.click(`[data-tq-browse-card="d${pm.ConnectorId}"] [data-tq-card]`);
  await page.waitForSelector("[data-tq-browse-one] [data-tq-card-on]");

  // #238: what leans on it, on Remove's own row - and the line is there before anything is pressed
  await until(page, () => /Used by: 2 workflows, the Morning sales report/.test(document.querySelector("[data-tq-used-by]")?.innerText || ""));
  const row = await page.evaluate(() => {
    const l = document.querySelector("[data-tq-used-by]"), b = [...document.querySelectorAll("[data-tq-browse-one] button")].find((x) => x.innerText.trim() === "Remove connection");
    return !!b && l.parentElement === b.parentElement;
  });
  assert.ok(row, "the line sits beside Remove connection");

  // #242: Save posts the settings, not the switch; the card is still off and says how to turn it on
  assert.match(await card(page), /Off — flip on once Test passes\./);
  await page.evaluate(() => {
    const i = [...document.querySelectorAll("[data-tq-browse-one] input")].find((x) => x.closest(".MuiFormControl-root")?.querySelector("label")?.innerText.trim() === "base URL");
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set.call(i, "https://metrics.northwind.example"); i.dispatchEvent(new Event("input", { bubbles: true }));
  });
  await page.evaluate(() => [...document.querySelectorAll("[data-tq-browse-one] button")].find((b) => b.innerText.trim() === "Save").click());
  await until(page, () => /saved ✓/.test(document.querySelector("[data-tq-browse-one]").innerText));
  assert.equal(posts.length, 1);
  assert.ok(!("Active" in posts[0]), `Save switched the card: ${JSON.stringify(posts[0])}`);
  assert.equal(JSON.parse(posts[0].ConfigJson).base_url, "https://metrics.northwind.example");

  // the switch is the card's own, saved on the press like a channel card's: no Save bar calls it unsaved
  await page.click("[data-tq-browse-one] [data-tq-card-on] input");
  for (let i = 0; i < 100 && posts.length < 2; i++) await new Promise((r) => setTimeout(r, 100));
  assert.deepEqual(posts[1], { ConnectorId: pm.ConnectorId, Active: true }, "the press posts the switch");
  assert.equal(await page.$(".tq-savebar"), null, "nothing left unsaved");
  assert.deepEqual(errors, []);
});

// THE OWNER, 2026-10-23: "you enable a connection and then sync now button shows up but then under it it says not saved". A channel
// card's Enable saves on the press; Sync now is there once the server has it on, and greyed - the reason on it - while an edit waits
test("a channel card: Enable saves at once, Sync now never stands beside an unsaved change", { timeout: 300000 }, async (t) => {
  const harness = await startHarness({ fresh: true }); t.after(() => harness.close());
  const api = (p, init = {}) => fetch(`${harness.fixtureApi}${p}`, { ...init, headers: { "Content-Type": "application/json", "X-Taskuary-Token": harness.token } }).then((r) => r.json());
  const imap = (await api("/api/connectors")).data.find((c) => c.Type === "imap");
  await api("/api/connectors", { method: "POST", body: JSON.stringify({ ConnectorId: imap.ConnectorId, Active: false, Secret: "app-password",
    ConfigJson: JSON.stringify({ host: "mail.northwind.example", username: "alex@northwind.example" }) }) });
  await api("/api/sources", { method: "POST", body: JSON.stringify({ Channel: "email", Address: "alex@northwind.example", ConnectorId: imap.ConnectorId, Active: true }) });
  const page = await harness.newPage(), errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  const text = () => page.evaluate(() => document.body.innerText);
  const step = (name) => page.evaluate((n) => [...document.querySelectorAll(".MuiStepLabel-label")].find((e) => e.innerText.trim() === n).click(), name);
  await page.goto(`${harness.ui}#connector=imap`, { waitUntil: "domcontentloaded", timeout: 90000 });
  await until(page, () => [...document.querySelectorAll(".MuiStepLabel-label")].some((e) => e.innerText.trim() === "Enable"), undefined, 120000);
  await step("Enable");
  await until(page, () => /Off — flip on once Test passes/.test(document.body.innerText));
  await page.click("[data-tq-card-on] input");
  // ...on a CI runner the first poll after the switch can take past the default 30s (it failed there three times and passed on each
  // rerun, 2026-10-25) - the wait is for the server's own word, so a longer wait cannot pass a wrong card
  await until(page, () => /polling on schedule/.test(document.body.innerText) && [...document.querySelectorAll("button")].some((b) => /^Sync/.test(b.innerText.trim()) && !b.disabled), undefined, 120000);
  assert.equal((await api("/api/connectors")).data.find((c) => c.ConnectorId === imap.ConnectorId).Active, 1, "saved on the press");
  assert.doesNotMatch(await text(), /unsaved change/, "Sync now beside an unsaved change");

  // a real unsaved change (a mailbox switched off, not saved): Sync now stays, greyed, and says why
  await step("Mailbox");
  await page.waitForSelector('[aria-label="Remove alex@northwind.example"]', { timeout: 15000 });
  await page.evaluate(() => document.querySelector('[aria-label="Remove alex@northwind.example"]').parentElement.querySelector('input[type="checkbox"]').click());
  await until(page, () => /1 unsaved change/.test(document.body.innerText));
  await step("Enable");
  await until(page, () => /Save your changes first/.test(document.querySelector("[data-tq-sync-why]")?.title || ""));
  assert.equal(await page.evaluate(() => document.querySelector("[data-tq-sync-why] button").disabled), true);
  await page.evaluate(() => [...document.querySelectorAll(".tq-savebar button")].find((b) => b.innerText.trim() === "Save").click());
  await until(page, () => !/unsaved change/.test(document.body.innerText) && !document.querySelector("[data-tq-sync-why]")
    && [...document.querySelectorAll("button")].some((b) => /^Sync/.test(b.innerText.trim()) && !b.disabled));
  assert.deepEqual(errors, []);
});
