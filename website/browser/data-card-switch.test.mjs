// A DATA CARD, SAVED AND ABOUT TO BE REMOVED (#242, #238). Save sent the card on with every save, so editing a card the owner
// had turned off turned it back on; it now saves the settings only, and the card's own switch - beside Save, held for the Save
// bar - is what turns it on. Remove's row says what leans on the card before the press. The demo refuses connector writes, so
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

  // the switch is the card's own: held for the Save bar like a channel card's, posted only from there
  await page.click("[data-tq-browse-one] [data-tq-card-on] input");
  await until(page, () => /Connection: off → on/.test(document.querySelector(".tq-savebar")?.innerText || ""));
  assert.equal(posts.length, 1, "the switch waits for the Save bar");
  await page.evaluate(() => [...document.querySelectorAll(".tq-savebar button")].find((b) => b.innerText.trim() === "Save").click());
  await until(page, () => !document.querySelector(".tq-savebar"));
  assert.deepEqual(posts[1], { ConnectorId: pm.ConnectorId, Active: true });
  assert.deepEqual(errors, []);
});
