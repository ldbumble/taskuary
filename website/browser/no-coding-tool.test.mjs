import assert from "node:assert/strict";
import test from "node:test";

import { startHarness } from "./harness.mjs";

/* NO CODING TOOL CHOSEN, NO START (owner-approved, 2026-10-21, the UI/UX audit's R3). On a fresh install the live-session picker
   was a blank box, and Send to coding agent found a tool on the computer by itself and started it. A fresh home: no tool anywhere. */
test("with no coding tool the live session says pick one, Send to coding agent stays off, and the server refuses", { timeout: 240000 }, async (t) => {
  const harness = await startHarness({ fresh: true });
  t.after(() => harness.close());
  const page = await harness.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(harness.ui, { waitUntil: "domcontentloaded", timeout: 30000 });
  const api = (path, body) => page.evaluate(async ({ path, body }) => {
    const r = await fetch(path, { method: body ? "POST" : "GET", headers: { "X-Taskuary-Token": localStorage.getItem("taskuary_token"),
      "Content-Type": "application/json" }, ...(body ? { body: JSON.stringify(body) } : {}) });
    return { status: r.status, data: await r.json().catch(() => null) };
  }, { path, body });
  assert.equal((await api("/api/setup/dismiss", { dismissed: true })).status, 200);
  await page.reload({ waitUntil: "domcontentloaded" });

  await page.evaluate(() => { window.location.hash = "new-task"; });
  await page.waitForFunction(() => [...document.querySelectorAll("[role='tab']")].some((x) => x.textContent.includes("Give an agent a job")), { timeout: 30000 });
  await page.evaluate(() => [...document.querySelectorAll("[role='tab']")].find((x) => x.textContent.includes("Give an agent a job")).click());
  await page.waitForFunction(() => document.body.innerText.includes("A live session"), { timeout: 10000 });
  await page.evaluate(() => [...document.querySelectorAll("p, span, div")].reverse().find((x) => x.textContent.trim() === "A live session")?.click());
  await page.waitForSelector("[data-tq-no-coding-tool]", { timeout: 10000 });
  assert.match(await page.$eval("[data-tq-no-coding-tool]", (el) => el.innerText), /Pick a coding tool first/);
  const box = await page.waitForSelector("[data-tq-new] textarea, [role='dialog'] textarea", { timeout: 10000 });
  await box.type("work out why the nightly export drops the last row");
  const send = await page.evaluate(() => [...document.querySelectorAll("button")].find((b) => b.textContent.trim() === "Send to coding agent")?.disabled);
  assert.equal(send, true, "Send to coding agent stays disabled with no coding tool");

  // ...and the server refuses a start by any other road
  const made = (await api("/api/tasks", { Title: "Fix the export", Summary: "Fix the export", Kind: "coding" })).data;
  const out = await api(`/api/tasks/${made.taskId}/dispatch`, { agent: null });
  assert.equal(out.status, 422, JSON.stringify(out.data));
  assert.match(String(out.data?.detail || ""), /Pick a coding tool first/);
  assert.equal(((await api("/api/terminals")).data?.data || []).length, 0, "nothing was started");

  // Connect one opens the coding tools
  await page.click("[data-tq-no-coding-tool] button");
  await page.waitForFunction(() => location.hash.includes("cli-agents"), { timeout: 10000 });
  assert.deepEqual(errors, []);
});
