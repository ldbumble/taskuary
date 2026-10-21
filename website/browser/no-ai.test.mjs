import assert from "node:assert/strict";
import test from "node:test";

import { startHarness } from "./harness.mjs";

/* NO AI CONNECTED IS NEVER A DEAD END (owner-approved, 2026-10-21, the UI/UX audit's W11). A fresh install with setup put away said
   "All done - nothing is waiting on you" over a day in which nothing could be judged, and a typed request was told to connect an AI
   with nothing to press. A fresh home: no AI anywhere. */
test("with no AI the rail says nothing can be sorted, and every no-AI line opens the AI cards", { timeout: 240000 }, async (t) => {
  const harness = await startHarness({ fresh: true });
  t.after(() => harness.close());
  const page = await harness.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(harness.ui, { waitUntil: "domcontentloaded", timeout: 30000 });
  const dismissed = await page.evaluate(async () => (await fetch("/api/setup/dismiss", { method: "POST",
    headers: { "X-Taskuary-Token": localStorage.getItem("taskuary_token"), "Content-Type": "application/json" },
    body: JSON.stringify({ dismissed: true }) })).status);
  assert.equal(dismissed, 200);
  await page.reload({ waitUntil: "domcontentloaded" });

  // THE RAIL: not "All done", and the button is in the message - at EVERY hour. The seeded End of day checkup used to run once its
  // hour had passed and post a normal-looking report over mail that did not exist; a home with nothing to report on now skips it
  // with the reason (a failed run, the bell's - reports.Skipped), so nothing lands on the rail and the empty-rail message holds.
  await page.waitForSelector("[data-tq-pile-no-ai]", { timeout: 30000 });
  assert.doesNotMatch(await page.evaluate(() => document.body.innerText), /All done/);
  const rail = await page.$eval("[data-tq-pile-no-ai]", (el) => el.innerText);
  assert.match(rail, /Nothing can be sorted yet/);
  await page.click("[data-tq-pile-no-ai] [data-tq-connect-ai]");
  await page.waitForFunction(() => decodeURIComponent(location.hash).includes("connections=AI"), { timeout: 10000 });

  // A TYPED REQUEST: the no-AI answer leads its chips with Connect an AI
  await page.evaluate(() => { window.location.hash = ""; });
  const box = await page.waitForSelector("textarea", { timeout: 20000 });
  await box.type("bring up the invoice from Ray");
  await page.keyboard.press("Enter");
  await page.waitForFunction(() => /so I can take instructions/.test(document.body.innerText), { timeout: 20000 });
  await page.waitForFunction(() => [...document.querySelectorAll("button")].some((b) => b.textContent.trim() === "Connect an AI" && b.offsetParent
    && !b.closest("[data-tq-pile-no-ai]")), { timeout: 10000 });
  assert.deepEqual(errors, []);
});
