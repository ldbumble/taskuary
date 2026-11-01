// A SEARCH UNDER CONNECTIONS THAT FINDS NO CARD (the owner, 2026-11-01: "if nothing matches their search there should be button file
// request for connection"). One button under the empty result - Request <name> - opens the one report popup as a feature request for
// that name, drafted by the server through the scrub; nothing is filed until Send opens GitHub's page and the owner presses Submit there.
// A search that matches anything shows no such button.
import assert from "node:assert/strict";
import test from "node:test";
import { clickNav, startHarness } from "./harness.mjs";

const DLG = "[aria-labelledby='bug-report-title']";
const type = (page, v) => page.evaluate((v) => {
  const i = document.querySelector("[data-tq-browse-search]"), set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set;
  set.call(i, v); i.dispatchEvent(new Event("input", { bubbles: true }));
}, v);
const button = (page) => page.evaluate(() => document.querySelector("[data-tq-request-connection]")?.innerText.trim() || "");

test("Connections: a name with no card offers Request <name>, which opens the feature-request draft prefilled with it", { timeout: 300000 }, async (t) => {
  const harness = await startHarness(); t.after(() => harness.close());
  const page = await harness.newPage(), errors = [], drafts = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("response", (r) => { if (new URL(r.url()).pathname === "/api/bug-report/draft") drafts.push(JSON.parse(r.request().postData() || "{}")); });
  await page.goto(harness.ui, { waitUntil: "domcontentloaded", timeout: 90000 });
  await page.evaluate(() => { window.__opened = []; window.open = (u) => { window.__opened.push(String(u)); return null; }; });
  await page.waitForSelector("[data-tq-nav='connections']", { timeout: 120000 });
  await clickNav(page, "Connections");
  await page.waitForSelector("[data-tq-browse-search]", { timeout: 30000 });

  await type(page, "gmail");
  await page.waitForSelector("[data-tq-browse-card]", { timeout: 15000 });
  assert.equal(await button(page), "", "a search that matches a card changes nothing");

  await type(page, "Zorblax Ledger");
  await page.waitForSelector("[data-tq-request-connection]", { timeout: 15000 });
  assert.equal(await button(page), "Request Zorblax Ledger");
  await page.click("[data-tq-request-connection]");
  await page.waitForSelector(DLG, { timeout: 15000 });
  await page.waitForFunction((d) => document.querySelector(`${d} input`)?.value, { timeout: 20000 }, DLG);
  assert.equal(drafts.length, 1); assert.deepEqual([drafts[0].kind, drafts[0].screen, drafts[0].error], ["feature", "Connections", ""]);
  assert.match(drafts[0].happened, /Zorblax Ledger/);
  const d = await page.evaluate((d) => ({ head: document.querySelector("#bug-report-title").innerText, title: document.querySelector(`${d} input`).value,
    text: [...document.querySelectorAll(`${d} textarea`)].map((x) => x.value).join("\n") }), DLG);
  assert.equal(d.head, "Request a feature"); assert.match(d.title, /^\[feature\] /); assert.match(`${d.title}\n${d.text}`, /Zorblax Ledger/);
  assert.deepEqual(await page.evaluate(() => window.__opened), [], "nothing is sent before the owner's Send and Submit");

  assert.equal(errors.length, 0, errors.join("\n"));
});
