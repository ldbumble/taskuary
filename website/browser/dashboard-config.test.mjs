import assert from "node:assert/strict";
import test from "node:test";

import { startHarness } from "./harness.mjs";

/* EVERY DASHBOARD IS CONFIGURABLE (the owner, 2026-10-24: "it should be configurable, with a new tab in Reports named Dashboards with
   sources layout like reports"). The built-in Taskuary at a glance is an ordinary row on the Dashboards shelf, drawn with the reports'
   own row; opened, its sources are a report's source cards and its components are cards beside them. A target changed redraws the
   page at once, Save sends it, and New dashboard still offers the ready one. The demo world: invented people only. */
test("the built-in dashboard is a row like a report's, and its components are edited, redrawn and saved", { timeout: 240000 }, async (t) => {
  const harness = await startHarness();
  t.after(() => harness.close());
  const page = await harness.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(`${harness.ui}#report=dashboards`, { waitUntil: "domcontentloaded", timeout: 30000 });

  // THE SHELF: the row wears the reports' own buttons - Run now, Edit and its switch
  const title = "Taskuary at a glance";
  await page.waitForFunction((want) => [...document.querySelectorAll("p,span")].some((el) => el.textContent.trim() === want && el.offsetParent),
    { timeout: 30000 }, title);
  const row = await page.evaluate((want) => {
    const t = [...document.querySelectorAll("p,span")].find((el) => el.textContent.trim() === want && el.offsetParent);
    const r = t.closest("div[class*='MuiBox']").parentElement.parentElement;
    return { buttons: [...r.querySelectorAll("button")].map((b) => b.textContent.trim()), switch: !!r.querySelector("input[type=checkbox]"),
      caption: r.innerText };
  }, title);
  assert.ok(row.buttons.includes("Run now") && row.buttons.includes("Edit") && row.switch, JSON.stringify(row));
  assert.match(row.caption, /6 sources/);
  await page.evaluate((want) => [...document.querySelectorAll("p,span")].find((el) => el.textContent.trim() === want && el.offsetParent).click(), title);

  // THE EDITOR: drawn, then its sources as source cards, then one card per component
  await page.waitForSelector("[data-tq-dashboard-editor] [data-tq-dashboard]", { timeout: 30000 });
  await page.waitForSelector("[data-tq-dash-component]", { timeout: 10000 });
  const text = await page.$eval("[data-tq-dashboard-editor]", (el) => el.innerText);
  assert.match(text, /Sources/); assert.match(text, /What it shows/);
  assert.match(text, /source 1 of 6/, "a report's own source card");
  assert.equal(await page.$$eval("[data-tq-dash-component]", (els) => els.length), 12);
  const meter = () => page.$eval('[role="meter"][aria-label="Closed this week"]', (el) => el.getAttribute("aria-valuemax"));
  assert.equal(await meter(), "15");

  // the weekly target, 15 -> 20: the page redraws over the same rows, nothing is read again
  const target = await page.evaluateHandle(() => {
    const card = [...document.querySelectorAll("[data-tq-dash-component]")].find((c) => [...c.querySelectorAll("input")].some((i) => i.value === "Closed this week"));
    return [...card.querySelectorAll("label")].find((l) => l.textContent.trim() === "target").parentElement.querySelector("input");
  });
  await target.focus();
  await page.keyboard.down("Control"); await page.keyboard.press("a"); await page.keyboard.up("Control");
  await page.keyboard.type("20");
  assert.equal(await target.evaluate((el) => el.value), "20");
  await page.waitForFunction(() => document.querySelector('[role="meter"][aria-label="Closed this week"]')?.getAttribute("aria-valuemax") === "20", { timeout: 5000 });

  // ...and Save sends the edited spec, the same save any dashboard's is (test_dashboards holds it kept). The demo keeps nothing:
  // it says so in its own sentence, never a dead button
  const sent = new Promise((resolve) => page.on("request", (r) => { if (r.method() === "POST" && r.url().endsWith("/api/sources")) resolve(r.postData()); }));
  await page.click("[data-tq-dashboard-save]");
  const body = JSON.parse(await sent), spec = JSON.parse(body.ConfigJson);
  assert.equal(body.Address, title);
  assert.equal(spec.components.find((c) => c.kind === "progress").target, 20);
  assert.equal(spec.components.length, 12);
  await page.waitForFunction(() => /✓|This is the demo/.test(document.querySelector("[data-tq-dashboard-editor]")?.innerText || ""), { timeout: 15000 });

  // NEW DASHBOARD still offers the ready one, in one press
  await page.goto(`${harness.ui}#report=new-dashboard`, { waitUntil: "domcontentloaded" });
  await page.waitForSelector('[data-tq-dashboard-template="glance"]', { timeout: 20000 });
  assert.deepEqual(errors, []);
});
