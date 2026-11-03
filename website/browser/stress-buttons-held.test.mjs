import assert from "node:assert/strict";
import test from "node:test";

import { startHarness } from "./harness.mjs";

/* A HELD STEP'S APPROVE, PRESSED LIKE A HURRIED HAND (the button stress, 2026-11-02): an agent's browser held a Register for the owner's yes
   (fixture_changes.browser_view, as browser-view.test.mjs) and Approve is pressed three times fast with the mouse where it stands - the held
   command runs once, the agent is told once, the bar goes, and nothing on the page errs. Invented site and task only. */
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const PAGE = `<html><body style="margin:0;font:16px system-ui;background:#f4f6fb"><div style="padding:40px"><h2>Register for Thursday</h2>
  <div style="background:#2b4c9b;color:#fff;border-radius:6px;padding:11px 0;width:140px;text-align:center">Register</div></div></body></html>`;

test("Approve on a held step, pressed three times fast, runs the held command once", { timeout: 240000 }, async (t) => {
  const h = await startHarness();
  t.after(() => h.close());
  const painter = await h.newPage();
  await painter.setViewport({ width: 1200, height: 760, deviceScaleFactor: 1 });
  await painter.setContent(PAGE);
  const frame = await painter.screenshot({ type: "jpeg", quality: 80, encoding: "base64" });
  await painter.close();
  const page = await h.newPage();
  await page.setViewport({ width: 1440, height: 900, deviceScaleFactor: 1 });
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("console", (m) => { if (m.type() === "error" && !/status of 403/.test(m.text())) errors.push(m.text().slice(0, 300)); });
  const writes = [];
  page.on("response", (r) => { const u = new URL(r.url()); if (r.request().method() !== "GET" && u.pathname.startsWith("/api/") && !u.pathname.startsWith("/api/fixture")) writes.push(`${r.status()} ${u.pathname}`); });
  await page.goto(h.ui, { waitUntil: "domcontentloaded", timeout: 30000 });
  const call = (url, body, method = "POST") => page.evaluate(async (url, body, method) => (await fetch(url, { method, ...(method === "POST" ? { body: JSON.stringify(body) } : {}),
    headers: { "Content-Type": "application/json", "X-Taskuary-Token": localStorage.getItem("taskuary_token") } })).json(), url, body, method);
  const made = await call("/api/fixture/browser/view", { step: "open", frame });
  await page.evaluate((id) => { window.location.hash = `task=${id}`; }, made.taskId);
  await page.waitForFunction(() => document.querySelector("[data-tq-browser-layout]") || (document.querySelector("[data-tq-section-tab=agent]")?.click(), false),
    { timeout: 30000, polling: 500 });
  const held = await call("/api/fixture/browser/view", { step: "hold", taskId: made.taskId });
  const bar = `[data-tq-browser-layout] [data-tq-browser-held="${held.reviewId}"]`;
  await page.waitForSelector(bar, { visible: true, timeout: 30000 });
  await sleep(800);
  const at = await page.evaluate((bar) => { const b = [...document.querySelectorAll(`${bar} button`)].find((x) => x.textContent.trim() === "Approve");
    b.scrollIntoView({ block: "nearest" });
    const r = b.getBoundingClientRect(), x = r.x + r.width / 2, y = r.y + r.height / 2, top = document.elementFromPoint(x, y);
    return { x, y, over: top && !b.contains(top) ? `${top.tagName}.${top.className}` : null }; }, bar);
  assert.equal(at.over, null, "Approve is under something else");
  for (let i = 0; i < 3; i++) { await page.mouse.click(at.x, at.y); await sleep(70); }
  let seen = null;
  for (let i = 0; i < 80 && !(seen = await call(`/api/fixture/browser/view/${made.taskId}`, null, "GET")).told.length; i++) await sleep(250);
  await sleep(3000);
  seen = await call(`/api/fixture/browser/view/${made.taskId}`, null, "GET");
  assert.deepEqual(seen.ran, [["click", "@e7"]], `the held command ran once: ${JSON.stringify(seen)} ${JSON.stringify(writes)}`);
  assert.equal(seen.told.length, 1, "the agent was told once");
  await page.waitForFunction((bar) => !document.querySelector(bar), { timeout: 15000 }, bar);
  assert.deepEqual(errors, []);
});
