import assert from "node:assert/strict";
import test from "node:test";

import { startHarness } from "./harness.mjs";

/* THE APP'S OWN TROUBLE, LOOKED INTO IN THE CHAT (the owner, 2026-10-23: "we need to see what it's thinking like general agent"). The
   turn is scripted at the stream - the demo has no model and no bridge - so what is held here is the page: the steps drawn while it
   works and kept on the answer in the general agent's own rows, and the one button the server chose under it, which opens what it
   says - the scrubbed Report this bug popup, drafted from what was found. */

const STEPS = [
  { id: "trouble-1", kind: "read", summary: "Checked WhatsApp: on, never synced - last error: the WhatsApp bridge is not running", detail: "the WhatsApp bridge is not running", status: "error" },
  { id: "trouble-2", kind: "read", summary: "Asked the WhatsApp bridge: not answering", detail: "manager: failed", status: "error" },
  { id: "trouble-3", kind: "run", summary: "Restarted the WhatsApp bridge", detail: "manager: failed", status: "error" },
];
const REPORT = { message: "WhatsApp is not working: the bridge is not answering", screen: "Assistant", route: "connector whatsapp" };

test("whatsapp isn't working: the steps show as the general agent's do, and what it cannot fix offers Report this bug",
  { timeout: 240000 }, async (t) => {
  const harness = await startHarness();
  t.after(() => harness.close());
  const page = await harness.newPage();
  const errors = [], drafts = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.off("request", page.fixtureRequestGuard);
  page.on("request", (request) => {
    const url = new URL(request.url());
    if (url.origin === harness.ui && url.pathname === "/api/concierge/stream") {
      const done = { say: "I restarted the bridge and it still doesn't answer - Report this bug drafts it for the app's tracker.",
                     options: [], decision: null, steps: STEPS, chips: [{ verb: "bug", label: "Report this bug", report: REPORT }] };
      return request.respond({ status: 200, contentType: "application/x-ndjson",
        body: [{ type: "steps", name: "troubleshoot", detail: { steps: STEPS.slice(0, 2) } }, { type: "done", ...done }].map((e) => JSON.stringify(e)).join("\n") + "\n" });
    }
    if (url.origin === harness.ui && url.pathname === "/api/bug-report/draft") drafts.push(request.postData() || "");
    page.fixtureRequestGuard(request);
  });
  await page.goto(harness.ui, { waitUntil: "domcontentloaded", timeout: 30000 });
  const input = await page.waitForSelector(".tq-compose textarea:not([disabled])", { timeout: 30000 });
  await input.type("whatsapp isn't working");
  await page.keyboard.press("Enter");
  await page.waitForFunction(() => document.body.innerText.includes("still doesn't answer"), { timeout: 20000 });

  const rows = await page.$$eval(".tq-msg .tq-aui-steps .tq-aui-step", (xs) => xs.map((x) => x.innerText.replace(/\s+/g, " ").trim()));
  assert.equal(rows.length, 3, `the answer keeps its three steps: ${rows.join(" | ")}`);
  assert.match(rows[0], /^Checked WhatsApp/);
  assert.match(rows[2], /Restarted the WhatsApp bridge failed/, "a press that did not work says failed on its row");
  // ...a row opens on what it read
  await page.evaluate(() => document.querySelector(".tq-msg .tq-aui-step summary").click());
  await page.waitForFunction(() => document.querySelector(".tq-msg .tq-aui-step[open] pre")?.innerText.includes("bridge is not running"), { timeout: 5000 });

  // THE ONE BUTTON: Report this bug, drafted from what it found - not the page's last error
  const pressed = await page.evaluate(() => {
    const b = [...document.querySelectorAll("button")].find((x) => x.textContent.trim() === "Report this bug" && x.offsetParent);
    if (!b) return false; b.click(); return true;
  });
  assert.ok(pressed, "Report this bug is under the answer");
  await page.waitForSelector("[aria-labelledby='bug-report-title']", { timeout: 15000 });
  for (let n = 0; n < 50 && !drafts.length; n++) await new Promise((r) => setTimeout(r, 100));
  assert.ok(drafts.length, "the popup asked the server for its scrubbed draft");
  const sent = JSON.parse(drafts[0]);
  assert.match(JSON.stringify(sent), /WhatsApp is not working/);
  assert.match(JSON.stringify(sent), /connector whatsapp/);
  assert.deepEqual(errors, []);
});
