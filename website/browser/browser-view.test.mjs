import assert from "node:assert/strict";
import { mkdir } from "node:fs/promises";
import path from "node:path";
import test from "node:test";

import { startHarness } from "./harness.mjs";

/* THE BROWSER IS IN THE AGENT'S CANVAS (the owner, 2026-10-28, over a sign-up agent whose "I'm not a robot" and Register reached him as
   a text card: "it should show up as a BROWSER inside the agent canvas instead of this ... so it flows better to go back and continue").
   ...and in a chat task only when the owner has a part on it (2026-11-05: "for browser we don't really want to show it unless they need
   login ... Browser should open side by side not top/bottom"). A real backend with an agent-browser session that has no Chrome
   (fixture_changes.browser_view): nothing is drawn while the agent browses; a held Register opens the view BESIDE the chat with Approve /
   Dismiss on it, and Approve runs it through the decide road and tells the agent; the agent's hand-over of a human check is "Your turn"
   on the view, the page takes the owner's mouse, and Done goes back to the agent; when the session ends no view is kept. On a phone the
   view folds to its chip and the cards stay in the chat.
   Invented site, task and people only. */
const SHOTS = process.env.TASKUARY_SHOTS || "";
const FORM = `<html><body style="margin:0;font:16px system-ui;background:#f4f6fb;color:#1d2433">
  <div style="background:#2b4c9b;color:#fff;padding:18px 32px;font-weight:600;font-size:20px">Trainly · Onboarding webinar</div>
  <div style="max-width:560px;margin:36px auto;background:#fff;border-radius:10px;padding:28px 32px;box-shadow:0 2px 10px #0001">
    <h2 style="margin:0 0 6px">Register for Thursday, 2:00 PM</h2><p style="color:#5b6478;margin:0 0 20px">A 45-minute walk through the Trainly admin console.</p>
    <label>First name</label><div style="border:1px solid #c9d0de;border-radius:6px;padding:9px;margin:4px 0 14px">Alex</div>
    <label>Last name</label><div style="border:1px solid #c9d0de;border-radius:6px;padding:9px;margin:4px 0 14px">Doyle</div>
    <label>Work email</label><div style="border:1px solid #c9d0de;border-radius:6px;padding:9px;margin:4px 0 18px">alex@northwind.example</div>
    <div style="display:flex;align-items:center;gap:12px;border:1px solid #d6dbe6;border-radius:6px;padding:14px;width:300px;background:#f9f9f9">
      <div style="width:24px;height:24px;border:2px solid #9aa3b5;border-radius:3px;background:#fff"></div><span>I'm not a robot</span></div>
    <div style="margin-top:20px;background:#2b4c9b;color:#fff;border-radius:6px;padding:11px 0;width:140px;text-align:center;font-weight:600">Register</div>
  </div></body></html>`;

test("the agent's browser is a view in its canvas: Approve and Your turn on it, both flowing back to the agent", { timeout: 240000 }, async (t) => {
  const harness = await startHarness();
  t.after(() => harness.close());
  if (SHOTS) await mkdir(SHOTS, { recursive: true });
  const shot = async (page, name) => { if (SHOTS) await page.screenshot({ path: path.join(SHOTS, `${name}.png`) }); };

  // the page the agent is on, drawn as the screencast would send it
  const painter = await harness.newPage();
  await painter.setViewport({ width: 1200, height: 760, deviceScaleFactor: 1 });
  await painter.setContent(FORM);
  const frame = await painter.screenshot({ type: "jpeg", quality: 80, encoding: "base64" });
  await painter.close();

  const page = await harness.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(harness.ui, { waitUntil: "domcontentloaded", timeout: 30000 });
  const call = (url, body, method = "POST") => page.evaluate(async (url, body, method) => (await fetch(url, { method, ...(method === "POST" ? { body: JSON.stringify(body) } : {}),
    headers: { "Content-Type": "application/json", "X-Taskuary-Token": localStorage.getItem("taskuary_token") } })).json(), url, body, method);
  const seen = (tid) => call(`/api/fixture/browser/view/${tid}`, null, "GET");
  const until = async (f, what, ms = 20000) => {
    const end = Date.now() + ms;
    for (;;) { const v = await f(); if (v) return v; if (Date.now() > end) assert.fail(`timed out: ${what}`); await new Promise((r) => setTimeout(r, 250)); }
  };
  const openTask = async (tid) => {
    await page.evaluate((id) => { window.location.hash = `task=${id}`; }, tid);
    // the Agent section: open already for a live agent, else one press on its tab
    await page.waitForFunction(() => document.querySelector("[data-tq-browser-layout]")
      || (document.querySelector("[data-tq-section-tab=agent]")?.click(), false), { timeout: 30000, polling: 500 });
  };

  // 1. the session opens and the agent browses: NOTHING of the browser is drawn - the chat says it is working, and that is all (the owner,
  //    2026-11-05: "for browser we don't really want to show it unless they need login")
  const made = await call("/api/fixture/browser/view", { step: "open", frame });
  assert.ok(made.taskId, JSON.stringify(made));
  await openTask(made.taskId);
  await new Promise((r) => setTimeout(r, 4000));                       // the browser state is read every 3 s: past the first reads
  assert.equal(await page.$eval("[data-tq-browser-layout]", (el) => el.dataset.tqBrowserLayout), "none", "no view while the agent just browses");
  assert.equal(await page.$("[data-tq-browser-layout] canvas"), null);
  assert.ok(!/browser ·/.test(await page.evaluate(() => document.body.innerText)), "and no chip for it");
  await shot(page, "1-browsing-no-view");

  // 2. a held Register: the view opens BESIDE the chat with Approve / Dismiss on it, not a card in the chat; Approve runs it, the agent is told
  const held = await call("/api/fixture/browser/view", { step: "hold", taskId: made.taskId });
  assert.ok(held.reviewId, JSON.stringify(held));
  const bar = `[data-tq-browser-layout] [data-tq-browser-held="${held.reviewId}"]`;
  await page.waitForSelector(bar, { visible: true, timeout: 30000 });
  assert.equal(await page.$eval("[data-tq-browser-layout]", (el) => el.dataset.tqBrowserLayout), "split", "side by side, never above the chat");
  assert.match(await page.$eval("[data-tq-browser-layout] input", (el) => el.placeholder || ""), /events\.trainly\.example\/onboarding\/register/);
  assert.match(await page.$eval(bar, (el) => el.innerText), /Approve: press "Register" on events\.trainly\.example/);
  assert.equal(await page.$("[data-tq-browser-acts]"), null, "the held act is on the view only, not a card in the chat as well");
  // ...the chat keeps at least 45% of the width beside it, at a small laptop's width as on a wide screen
  const chatShare = () => page.$eval("[data-tq-browser-layout]", (el) => el.querySelector(".tq-term-slot").getBoundingClientRect().width / el.getBoundingClientRect().width);
  assert.ok(await chatShare() >= 0.44, `the chat keeps its share: ${await chatShare()}`);
  await shot(page, "2-held-register-on-view");
  await page.setViewport({ width: 1024, height: 860, deviceScaleFactor: 1 });
  await page.waitForFunction(() => document.querySelector("[data-tq-browser-layout]")?.dataset.tqBrowserLayout === "split"
    && document.querySelector("[data-tq-browser-layout] canvas")?.getBoundingClientRect().height > 200, { timeout: 15000 });
  assert.ok(await chatShare() >= 0.44, `the chat keeps its share at 1024px: ${await chatShare()}`);
  await shot(page, "2b-view-small-laptop");
  await page.setViewport({ width: 1440, height: 1000, deviceScaleFactor: 1 });
  await page.evaluate((bar) => [...document.querySelectorAll(`${bar} button`)].find((b) => b.textContent.trim() === "Approve").click(), bar);
  const afterApprove = await until(async () => { const s = await seen(made.taskId); return s.told.length ? s : null; }, "the agent told of the approval");
  assert.deepEqual(afterApprove.ran, [["click", "@e7"]], "Approve ran exactly the held command in the agent's browser");
  assert.match(afterApprove.told[0], /The owner approved it and Taskuary ran `agent-browser click @e7`.*continue/s);
  await page.waitForFunction((bar) => !document.querySelector(bar), { timeout: 15000 }, bar);
  // ...and once the owner has done their part the view goes away again
  await page.waitForFunction(() => document.querySelector("[data-tq-browser-layout]")?.dataset.tqBrowserLayout === "none", { timeout: 15000 });

  // 3. the agent hands the page over for a human check: Your turn on the view, the page takes the owner's mouse, Done goes back
  const turn = await call("/api/fixture/browser/view", { step: "turn", taskId: made.taskId });
  const tbar = `[data-tq-browser-layout] [data-tq-browser-turn="${turn.requestId}"]`;
  await page.waitForSelector(tbar, { visible: true, timeout: 30000 });
  assert.match(await page.$eval(tbar, (el) => el.innerText), /Your turn in the browser on events\.trainly\.example: tick the "I'm not a robot" box/);
  assert.equal(await page.$(`[data-tq-asking="${turn.requestId}"]`), null, "the hand-over is on the view, not an asked-you-something card");
  const canvas = await page.$("[data-tq-browser-layout] canvas");
  const r = await canvas.boundingBox();
  await page.mouse.click(r.x + r.width * 0.3, r.y + r.height * 0.6);
  await until(async () => (await seen(made.taskId)).input.includes("input_mouse"), "the owner's click reached the page");
  await shot(page, "3-your-turn-on-view");
  await page.evaluate((tbar) => [...document.querySelectorAll(`${tbar} button`)].find((b) => /hand back/.test(b.textContent)).click(), tbar);
  const back = await until(async () => { const s = await seen(made.taskId); return s.told.length > 1 ? s : null; }, "the agent handed the page back");
  assert.equal(back.told[1], "Done - I finished that in the browser. Look at the page as it is now and continue.");
  await page.waitForFunction((tbar) => !document.querySelector(tbar), { timeout: 15000 }, tbar);

  // 4. the session ends: a chat task keeps no view of the page - the answer is in the chat
  const closed = await call("/api/fixture/browser/view", { step: "close", taskId: made.taskId });
  assert.ok(closed.closed, JSON.stringify(closed));
  await page.reload({ waitUntil: "domcontentloaded" });
  await page.evaluate((id) => { window.location.hash = `task=${id}`; }, made.taskId);
  await page.waitForFunction(() => [...document.querySelectorAll(".tq-aui-agent")].length
    || (document.querySelector("[data-tq-section-tab=agent]")?.click(), false), { timeout: 30000, polling: 500 });
  await new Promise((r) => setTimeout(r, 2000));
  assert.equal(await page.$("[data-tq-browser-last]"), null, "no last view under a chat task's answer");
  await shot(page, "4-no-last-view-after-session");

  // 5. a phone: the view is its chip, and the held act keeps its card in the chat
  const phone = await call("/api/fixture/browser/view", { step: "open", frame });
  await call("/api/fixture/browser/view", { step: "hold", taskId: phone.taskId });
  await page.setViewport({ width: 390, height: 844, deviceScaleFactor: 1 });
  await openTask(phone.taskId);
  await page.waitForFunction(() => document.querySelector("[data-tq-browser-layout]")?.dataset.tqBrowserLayout === "chip"
    && document.querySelector("[data-tq-browser-acts]"), { timeout: 30000 });
  await shot(page, "5-phone-chip");
  assert.deepEqual(errors, []);
});
