import assert from "node:assert/strict";
import { mkdir } from "node:fs/promises";
import path from "node:path";
import test from "node:test";

import { startHarness } from "./harness.mjs";

/* THE VIEW SHOWS THE PAGE, NOT THE WHITE OF ITS LOADING (the owner, 2026-11-03: "still looks like white browser hand off page"). The agent
   opens a sign-in page and hands it over; the first frame is the page still loading - white, a spinner - and the painted page follows
   while the owner is in another window or tab. That frame was kept by its number only, and the ack asks for a NEWER one, which a page
   sitting still never makes: the view stayed white for good. Read here by the PIXELS on the view's canvas, never by an element being
   there. A real backend with an agent-browser session that has no Chrome (fixture_changes.browser_view). Invented site and task only. */
const SHOTS = process.env.TASKUARY_SHOTS || "";
const LOADING = `<html><body style="margin:0;background:#fff"><div style="position:absolute;left:50%;top:50%;width:28px;height:28px;
  border:3px solid #ddd;border-top-color:#888;border-radius:50%"></div></body></html>`;
const SIGNIN = `<html><body style="margin:0;font:16px system-ui;background:#eef1f6;color:#1d2433">
  <div style="background:#2b4c9b;color:#fff;padding:18px 32px;font-weight:600;font-size:20px">Payworth · Sign in</div>
  <div style="max-width:420px;margin:48px auto;background:#fff;border-radius:10px;padding:28px 32px">
    <label>User ID</label><div style="border:1px solid #9aa3b5;border-radius:6px;height:36px;margin:6px 0 18px"></div>
    <div style="background:#2b4c9b;color:#fff;border-radius:6px;padding:11px 0;text-align:center;font-weight:600">Next</div>
  </div></body></html>`;

// the share of the view's canvas that is near-white, and of it that is the sign-in page's blue
const pixels = (page) => page.evaluate(() => {
  const c = document.querySelector("[data-tq-browser-layout] canvas");
  if (!c || !c.width) return null;
  const d = c.getContext("2d").getImageData(0, 0, c.width, c.height).data;
  let white = 0, blue = 0, n = 0;
  for (let i = 0; i < d.length; i += 16) {
    n++;
    if (d[i] > 240 && d[i + 1] > 240 && d[i + 2] > 240) white++;
    if (d[i] < 70 && d[i + 1] > 60 && d[i + 1] < 100 && d[i + 2] > 130) blue++;
  }
  return { white: white / n, blue: blue / n };
});

test("a page that finished painting while the owner looked away is drawn when they come back, not left white", { timeout: 180000 }, async (t) => {
  const harness = await startHarness();
  t.after(() => harness.close());
  if (SHOTS) await mkdir(SHOTS, { recursive: true });
  const shot = async (page, name) => { if (SHOTS) await page.screenshot({ path: path.join(SHOTS, `${name}.png`) }); };
  const painter = await harness.newPage();
  await painter.setViewport({ width: 1200, height: 760, deviceScaleFactor: 1 });
  const frameOf = async (html) => { await painter.setContent(html); return painter.screenshot({ type: "jpeg", quality: 80, encoding: "base64" }); };
  const loading = await frameOf(LOADING), signin = await frameOf(SIGNIN);
  await painter.close();

  const page = await harness.newPage();
  await page.setViewport({ width: 1440, height: 1000, deviceScaleFactor: 1 });
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(harness.ui, { waitUntil: "domcontentloaded", timeout: 30000 });
  const call = (url, body, method = "POST") => page.evaluate(async (url, body, method) => (await fetch(url, { method, ...(method === "POST" ? { body: JSON.stringify(body) } : {}),
    headers: { "Content-Type": "application/json", "X-Taskuary-Token": localStorage.getItem("taskuary_token") } })).json(), url, body, method);

  // 1. the agent opened the page and asks to be signed in: its first frame is the page still loading, and the view draws it - white
  // (only the ask puts it on screen: a chat task's browser shows when the owner has a part on it, 2026-11-05)
  const made = await call("/api/fixture/browser/view", { step: "open", frame: loading });
  assert.ok(made.taskId, JSON.stringify(made));
  await call("/api/fixture/browser/view", { step: "signin", taskId: made.taskId });
  await page.evaluate((id) => { window.location.hash = `task=${id}`; }, made.taskId);
  await page.waitForFunction(() => document.querySelector("[data-tq-browser-layout] canvas")
    || (document.querySelector("[data-tq-section-tab=agent]")?.click(), false), { timeout: 30000, polling: 500 });
  await page.waitForFunction(() => [...document.querySelectorAll("[data-tq-browser-layout] p")].some((p) => p.textContent.trim() === "LIVE"), { timeout: 30000 });
  const first = await pixels(page);
  assert.ok(first.white > 0.5, `the loading frame is drawn: ${JSON.stringify(first)}`);

  // 2. the owner looks away (the fill page, the mail) and the page finishes painting meanwhile - one frame, then nothing: it sits still
  const away = await harness.newPage();
  await away.goto("about:blank"); await away.bringToFront();
  await page.waitForFunction(() => document.hidden, { timeout: 10000 });
  const sent = await call("/api/fixture/browser/paint", { taskId: made.taskId, frame: signin });
  assert.equal(sent.sent, 1, JSON.stringify(sent));
  await new Promise((r) => setTimeout(r, 500));

  // 3. back: the view shows the sign-in page, and the frame it drew is acked so the next one can come
  await page.bringToFront(); await away.close();
  await page.waitForFunction(() => !document.hidden, { timeout: 10000 });
  let now = null;
  for (let i = 0; i < 20; i++) { now = await pixels(page); if (now.blue > 0.02) break; await new Promise((r) => setTimeout(r, 250)); }
  await shot(page, "view-after-looking-away");
  assert.ok(now.blue > 0.02 && now.white < first.white, `the painted page is on the view, not the white of its loading: ${JSON.stringify(now)}`);
  // ...and the agent's input under the view is on screen, inside its card - not 40px under the edge behind a second scrollbar
  const input = await page.evaluate(() => {
    const room = document.querySelector("[data-tq-agent-room='live']"), box = room && [...room.querySelectorAll("textarea")].pop();
    let p = room?.parentElement;
    while (p && !(/(auto|scroll)/.test(getComputedStyle(p).overflowY) && p.clientHeight)) p = p.parentElement;
    return box && p && { input: Math.round(box.getBoundingClientRect().bottom), edge: Math.round(p.getBoundingClientRect().bottom), over: p.scrollHeight - p.clientHeight };
  });
  assert.ok(input && input.input <= input.edge && input.over <= 12, `the agent's input is inside the card ${JSON.stringify(input)}`);
  const seen = await call(`/api/fixture/browser/view/${made.taskId}`, null, "GET");
  assert.ok(seen.acks.includes(sent.seq), `the frame drawn on return is acked: ${JSON.stringify(seen.acks)}`);
  assert.deepEqual(errors, []);
});
