import assert from "node:assert/strict";
import test from "node:test";
import os from "node:os";
import path from "node:path";

import { startHarness } from "./harness.mjs";

/* THE CHAT IS A WINDOW (the owner, 2026-10-28, on 0.3.9.58: "why is it showing up in the actual canvas???? i thought we moved this to the side
   chat box like in support on most websites"): with a report on the table - drawn in a task's three sections - "what are my outstanding
   tasks?" and its whole answer were drawn in the canvas under the card, because the answer pop-up only held what was said while a TASK
   VIEW held the table. Now every turn goes into one support-style window at the canvas's bottom right: on a task and on a report, nothing
   new in the canvas, the window stays open, × shuts it, the pill opens it again on the same conversation; on a phone it is a bottom sheet. */
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const rect = (page, sel) => page.$eval(sel, (e) => { const r = e.getBoundingClientRect(); return { l: r.left, r: r.right, t: r.top, b: r.bottom, w: r.width, h: r.height }; });
const Q = "what are my outstanding tasks?";
const inCanvas = (page) => page.$$eval(".tq-chat-body .tq-msg.you, .tq-chat-body .tq-msg.receipt, .tq-chat-body .tq-msg:not(.tq-live-card):not(.tq-welcome-msg) .body > p",
  (els) => els.map((e) => e.textContent.trim()).filter(Boolean));
const ask = async (page, q) => {
  await page.click(".tq-compose-box textarea");
  await page.waitForSelector("[data-tq-chat-win]:not([hidden])", { timeout: 5000 });
  await page.keyboard.type(q);
  await page.keyboard.press("Enter");
  await page.waitForFunction((q) => [...document.querySelectorAll("[data-tq-chat-win] .tq-msg.you")].some((e) => e.textContent.includes(q)), { timeout: 20000 }, q);
  await page.waitForFunction(() => !document.querySelector("[data-tq-chat-win] .tq-pending"), { timeout: 30000 });
  await sleep(400);
};
const openTask = async (page, harness, re) => {
  const tasks = (await (await fetch(`${harness.fixtureApi}/api/tasks`, { headers: { "X-Taskuary-Token": harness.token } })).json()).data;
  const t = tasks.find((x) => re.test(x.Title));
  assert.ok(t, `the demo's ${re}`);
  await page.evaluate((id) => { location.hash = `task=${id}`; }, t.TaskId);
  await page.waitForSelector(`[data-tq-task-page="${t.TaskId}"]`, { timeout: 20000 });
  await sleep(2000);
};

test("an answer goes into the chat window on a task and on a report, never into the canvas; × shuts it and the pill brings the same conversation back", { timeout: 300000 }, async (t) => {
  const harness = await startHarness();
  t.after(() => harness.close());
  const page = await harness.newPage();
  await page.setViewport({ width: 1366, height: 768, deviceScaleFactor: 1 });
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(harness.ui, { waitUntil: "domcontentloaded", timeout: 20000 });
  await page.waitForSelector("[data-tq-rail] .tq-pile-row", { timeout: 30000 });

  // ON A TASK
  await openTask(page, harness, /^Invoice 88213/);
  const before = await inCanvas(page), view = await rect(page, "[data-tq-canvas-item]");
  await ask(page, Q);
  const win = await rect(page, "[data-tq-chat-win]"), box = await rect(page, ".tq-compose-box"), dock = await rect(page, ".tq-dock"), body = await rect(page, ".tq-chat-body");
  const field = await rect(page, ".tq-compose-box .tq-compose-field"), line = await rect(page, ".tq-dock-line");
  const say = JSON.stringify({ win, box, field, dock, body, line });
  assert.deepEqual(await inCanvas(page), before, "nothing new is drawn in the canvas");
  assert.match(await page.$eval("[data-tq-chat-win] .tq-chat-pop-body", (e) => e.textContent), /outstanding tasks[\s\S]*scripted/, "the question and its answer are in the window");
  assert.equal(await page.$eval("[data-tq-chat-win] .tq-chat-pop-head b", (e) => e.textContent), "Taskuary");
  // ...THE PILL'S WIDTH, OUT OF THE BAR, AT MOST HALF THE SCREEN (the owner, 2026-10-28: "the chat should come out of the bottom bar and not go all
  // the way up, max 50%" - "make it narrower to fit the size on the bar and it expands only height not width")
  assert.ok(box.w >= 276 && box.w <= 284 && Math.abs(win.w - box.w) <= 1 && Math.abs(win.r - box.r) <= 1 && Math.abs(field.w - box.w) <= 1, `one ~280px panel, the pill's width ${say}`);
  assert.ok(box.t >= line.t - 1 && box.b <= line.b + 1 && dock.r - box.r < 40, `...the box stays in the bar, at its right end ${say}`);
  assert.ok(Math.abs(field.b - box.b) <= 1 && Math.abs(win.b - field.t) <= 1, `...the field rises out of it, the conversation flush on the field ${say}`);
  assert.ok(win.t >= body.t && win.h + field.h <= 0.5 * 768 + 2 && win.h + field.h >= 300, `...within the canvas, 300px to half the screen ${say}`);
  assert.deepEqual(await rect(page, "[data-tq-canvas-item]"), view, "the task view did not move");
  assert.ok(await page.$eval("[data-tq-chat-win] .tq-chat-pop-body", (b) => b.scrollHeight - b.scrollTop - b.clientHeight <= 2), "the newest words in view");
  // ...its own lines right, the answer left with the mark
  const sides = await page.$eval("[data-tq-chat-win] .tq-chat-pop-body", (b) => {
    const you = b.querySelector(".tq-msg.you .body").getBoundingClientRect(), it = [...b.querySelectorAll(".tq-msg:not(.you)")].pop(), r = b.getBoundingClientRect();
    return { youRight: r.right - you.right, itLeft: it.querySelector(".body").getBoundingClientRect().left - r.left, mark: !!it.querySelector(".avatar")?.children.length };
  });
  assert.ok(sides.youRight < 24 && sides.itLeft < 60 && sides.mark, `the owner's bubble right, Taskuary's answer left with its mark ${JSON.stringify(sides)}`);

  // ...it stays open (no auto-close, a click on the canvas leaves it), × shuts it, the pill opens it on the same conversation
  await sleep(3000);
  await page.click("[data-tq-task-head]");
  await sleep(300);
  assert.equal(await page.$eval("[data-tq-chat-win]", (e) => e.hidden), false, "it stays open until × or Esc");
  await page.click("[data-tq-chat-win] [aria-label='Close the chat']");
  await page.waitForSelector("[data-tq-chat-win][hidden]", { timeout: 5000 });
  await page.waitForFunction(() => !document.querySelector(".tq-compose-box[data-tq-open]"), { timeout: 5000 });
  await page.click(".tq-compose-box textarea");
  await page.waitForSelector("[data-tq-chat-win]:not([hidden])", { timeout: 5000 });
  assert.match(await page.$eval("[data-tq-chat-win] .tq-chat-pop-body", (e) => e.textContent), /outstanding tasks[\s\S]*scripted/, "reopened, the same conversation");
  await page.keyboard.press("Escape");
  await page.waitForSelector("[data-tq-chat-win][hidden]", { timeout: 5000 });

  // ON A REPORT (the owner's screenshot: the answer drawn under it, in the canvas)
  const rows = await page.$$("[data-tq-rail] .tq-pile-row");
  const at = await page.$$eval("[data-tq-rail] .tq-pile-row", (r) => r.findIndex((x) => /Headcount by site/.test(x.textContent)));
  assert.ok(at >= 0, "the demo's report on the rail");
  await rows[at].click();
  await page.waitForSelector("[data-tq-item-sections]", { timeout: 20000 });
  await sleep(1500);
  const onReport = await inCanvas(page);
  await ask(page, `${Q} (report)`);
  assert.deepEqual(await inCanvas(page), onReport, "nothing new in the canvas under the report");
  assert.equal(await page.$$eval("[data-tq-chat-win] .tq-msg.you", (els) => els.length), 2, "the window holds both turns");

  // A TASK NAMED IN AN ANSWER OPENS AS ITS RAIL ROW DOES (the owner, 2026-10-28: "it should hit the task and it should open ... like hitting a
  // task on the work rail"): "open TQ-0004" - the Assistant presses that row (a receipt in the window) - and later its name, pressed in the
  // answer, brings it back the same way: the task on the canvas, its rail row the selected one
  const onTable = () => page.evaluate(() => ({ hash: location.hash, sel: document.querySelector("[data-tq-rail] .tq-pile-row .card[aria-selected=true]")?.textContent || "",
    view: document.querySelector("[data-tq-task-page]")?.getAttribute("data-tq-task-page") || "" }));
  await ask(page, "open TQ-0004");
  await page.waitForFunction(() => document.querySelector("[data-tq-task-page]")?.getAttribute("data-tq-task-page") === "4", { timeout: 20000 });
  let at4 = await onTable();
  assert.match(at4.sel, /TQ-0004/, `the Assistant pressed TQ-0004's rail row ${JSON.stringify(at4)}`);
  assert.match(await page.$eval("[data-tq-chat-win] .tq-chat-pop-body", (e) => [...e.querySelectorAll(".tq-msg.receipt")].pop()?.textContent || ""), /Opened TQ-0004/,
    "...and said so in the window");
  const first = await page.$$("[data-tq-rail] .tq-pile-row .card");
  await first[0].click();
  await page.waitForFunction(() => document.querySelector("[data-tq-task-page]")?.getAttribute("data-tq-task-page") !== "4", { timeout: 20000 });
  await sleep(800);
  await page.click("[data-tq-chat-win] .tq-chat-pop-body [data-tq-task-link='4']");
  await page.waitForFunction(() => document.querySelector("[data-tq-task-page]")?.getAttribute("data-tq-task-page") === "4", { timeout: 20000 });
  await sleep(500);
  at4 = await onTable();
  assert.match(at4.sel, /TQ-0004/, `the name pressed in the answer selected its rail row ${JSON.stringify(at4)}`);
  assert.equal(at4.hash, "#task=4");
  assert.deepEqual(errors, []);
});

test("on a phone the chat window is a bottom sheet", { timeout: 300000 }, async (t) => {
  const harness = await startHarness();
  t.after(() => harness.close());
  const page = await harness.newPage();
  await page.setViewport({ width: 390, height: 844, deviceScaleFactor: 1, isMobile: true, hasTouch: true });
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(harness.ui, { waitUntil: "domcontentloaded", timeout: 20000 });
  await page.waitForSelector(".tq-compose-box textarea", { timeout: 30000 });
  await openTask(page, harness, /^Invoice 88213/);
  const before = await inCanvas(page);
  await ask(page, Q);
  const win = await rect(page, "[data-tq-chat-win]"), box = await rect(page, ".tq-compose-box"), say = JSON.stringify({ win, box });
  assert.ok(win.l <= 0.5 && win.r >= 389.5 && box.l <= 0.5 && box.r >= 389.5, `the screen's width ${say}`);
  assert.ok(Math.abs(box.b - 844) <= 1 && Math.abs(win.b - box.t) <= 1, `...the box at the screen's foot, the conversation on it ${say}`);
  assert.deepEqual(await inCanvas(page), before, "nothing new in the canvas");
  await page.click("[data-tq-chat-win] [aria-label='Close the chat']");
  await page.waitForSelector("[data-tq-chat-win][hidden]", { timeout: 5000 });
  assert.deepEqual(errors, []);
});

/* ONCE OPEN, ONLY ITS × AND ESC SHUT IT (the owner, 2026-10-28: "when we were chatting with the Taskuary chat that pops up it randomly closes
   ... it closed when it responded. Make sure that never happens" - and "it's too small, it should get a little taller"): an answer, an
   answer that opens a task or acts on the row, a feed rebuild pushed by the server, Next, a click on the canvas, a rail row and an Esc
   aimed at the canvas all leave it open; × and Esc in it shut it. Its minimize puts it away to a pill that says it can be continued -
   over a reload too - and opens on the same conversation. */
test("the chat window stays open through answers, acts, feed rebuilds and Next; only × and Esc in it shut it; minimize continues it", { timeout: 400000 }, async (t) => {
  const harness = await startHarness();
  t.after(() => harness.close());
  const page = await harness.newPage();
  await page.setViewport({ width: 1440, height: 900, deviceScaleFactor: 1 });
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(harness.ui, { waitUntil: "domcontentloaded", timeout: 20000 });
  await page.waitForSelector("[data-tq-rail] .tq-pile-row", { timeout: 30000 });
  // every moment it was shut, watched from the page itself - a close and a reopen between two checks is still a close
  await page.evaluate(() => { window.__shut = []; window.__on = "boot";
    new MutationObserver(() => { const w = document.querySelector("[data-tq-chat-win]"); if ((!w || w.hidden) && window.__watch) window.__shut.push(window.__on); })
      .observe(document.body, { subtree: true, attributes: true, attributeFilter: ["hidden"], childList: true }); });
  const during = (s) => page.evaluate((s) => { window.__on = s; window.__watch = true; }, s);
  const shut = () => page.evaluate(() => [...new Set(window.__shut)]);
  const isOpen = () => page.$eval("[data-tq-chat-win]", (e) => !e.hidden).catch(() => false);
  const stays = async (s) => { assert.ok(await isOpen(), `open after ${s}`); assert.deepEqual(await shut(), [], `never shut during ${s}`); };
  const say = async (q) => {
    await page.focus(".tq-compose-box textarea"); await page.keyboard.type(q); await page.keyboard.press("Enter");
    await page.waitForFunction((q) => [...document.querySelectorAll("[data-tq-chat-win] .tq-msg.you")].some((e) => e.textContent.includes(q)), { timeout: 20000 }, q);
    await page.waitForFunction(() => !document.querySelector("[data-tq-chat-win] .tq-pending"), { timeout: 30000 });
    await sleep(1200);
  };
  await openTask(page, harness, /^Invoice 88213/);

  await ask(page, Q);
  await during("an answer");
  await sleep(1500); await stays("an answer");
  // ...TALL ENOUGH, NEVER PAST HALF THE SCREEN (the owner, 2026-10-28: "max 50%"), between the canvas's top and the box in the bar
  const win = await rect(page, "[data-tq-chat-win]"), box = await rect(page, ".tq-compose-box"), body = await rect(page, ".tq-chat-body"), line = await rect(page, ".tq-dock-line");
  const field = await rect(page, ".tq-compose-box .tq-compose-field"), tall = JSON.stringify({ win, box, field, body, line });
  assert.ok(win.h + field.h >= 300 && win.h + field.h <= 0.5 * 900 + 2, `the window is 300px..half the screen tall ${tall}`);
  assert.ok(win.t >= body.t && box.t >= line.t - 1 && box.b <= line.b + 1, `...under the canvas's top, its box in the bar ${tall}`);
  const fill = await page.$eval("[data-tq-chat-win] .tq-chat-pop-body", (b) => ({ h: b.getBoundingClientRect().height, win: b.parentElement.getBoundingClientRect().height }));
  assert.ok(fill.win - fill.h < 60, `the conversation fills the window ${JSON.stringify(fill)}`);

  await during("an answer that opens a task"); await say("open TQ-0004");
  await page.waitForFunction(() => document.querySelector("[data-tq-task-page]")?.getAttribute("data-tq-task-page") === "4", { timeout: 20000 });
  await stays("an answer that opens a task");
  await during("an answer that acts on the row"); await say("remind me Monday");
  await stays("an answer that acts on the row");
  await during("a typed close"); await say("mark this done");
  await stays("a typed close");

  await during("a feed rebuild");
  const rows = await page.$$eval("[data-tq-rail] .tq-pile-row", (r) => r.length);
  const pushed = await fetch(`${harness.fixtureApi}/api/fixture/processing/ordering`, { method: "POST", headers: { "X-Taskuary-Token": harness.token, "Content-Type": "application/json" }, body: "{}" });
  assert.equal(pushed.status, 200);
  await page.waitForFunction((n) => document.querySelectorAll("[data-tq-rail] .tq-pile-row").length > n, { timeout: 20000 }, rows);
  await sleep(1500); await stays("a feed rebuild");

  await during("Next"); const was = await page.evaluate(() => location.hash);
  await page.click("[data-tq-next]");
  await page.waitForFunction((h) => location.hash !== h, { timeout: 20000 }, was);
  await sleep(1500); await stays("Next");

  await during("a click on the canvas and an Esc aimed at it");
  await page.click(".tq-chat-body"); await page.keyboard.press("Escape"); await sleep(500);
  await stays("a click on the canvas and an Esc aimed at it");
  await during("a rail row");
  const cards = await page.$$("[data-tq-rail] .tq-pile-row .card"); await cards[1].click(); await sleep(2000);
  await stays("a rail row");
  await page.evaluate(() => { window.__watch = false; });

  // × shuts it; the pill opens it; Esc in it shuts it
  await page.click("[data-tq-chat-win] [aria-label='Close the chat']");
  await page.waitForSelector("[data-tq-chat-win][hidden]", { timeout: 5000 });
  await page.click(".tq-compose-box textarea");
  await page.waitForSelector("[data-tq-chat-win]:not([hidden])", { timeout: 5000 });
  await page.keyboard.press("Escape");
  await page.waitForSelector("[data-tq-chat-win][hidden]", { timeout: 5000 });

  // MINIMIZE IS NOT × (the owner, 2026-10-28: the two did the same): it folds the window to its head - a strip standing on the open box, the
  // conversation kept - and a press on the strip brings the whole window back at its newest line; × (and Esc) from the strip is the pill
  const hint = () => page.$eval(".tq-compose-box textarea", (e) => e.placeholder);
  assert.notEqual(await hint(), "Continue chat…", "a shut window's pill is the plain one");
  await page.click(".tq-compose-box textarea");
  await page.waitForSelector("[data-tq-chat-win]:not([hidden])", { timeout: 5000 });
  const said = await page.$eval("[data-tq-chat-win] .tq-chat-pop-body", (e) => e.textContent), full = await rect(page, "[data-tq-chat-win]");
  const minimize = async () => {
    await page.click("[data-tq-chat-win] [aria-label='Minimize the chat']");
    await page.waitForSelector("[data-tq-chat-win][data-tq-mini]:not([hidden])", { timeout: 5000 });
    await sleep(300);
    const strip = await rect(page, "[data-tq-chat-win]"), fld = await rect(page, ".tq-compose-box .tq-compose-field"), at = JSON.stringify({ strip, fld, full });
    assert.ok(strip.h > 20 && strip.h < 60 && Math.abs(strip.w - full.w) <= 1, `minimized, the window is its head strip ${at}`);
    assert.ok(Math.abs(strip.b - fld.t) <= 1, `...standing on the open box, not down at the bar ${at}`);
    assert.ok(await page.$(".tq-compose-box[data-tq-open]"), "...the box still open under it");
    assert.equal(await page.$eval("[data-tq-chat-win] .tq-chat-pop-head b", (e) => e.textContent), "Taskuary");
    assert.ok(await page.$("[data-tq-chat-win] [aria-label='Expand the chat']"), "...its control now expands");
  };
  await minimize();
  await page.click("[data-tq-chat-win] .tq-chat-pop-head b");
  await page.waitForFunction(() => { const w = document.querySelector("[data-tq-chat-win]"); return w && !w.hidden && !w.hasAttribute("data-tq-mini"); }, { timeout: 5000 });
  await sleep(300);
  assert.equal(await page.$eval("[data-tq-chat-win] .tq-chat-pop-body", (e) => e.textContent), said, "pressing the strip: the same conversation");
  assert.ok(Math.abs((await rect(page, "[data-tq-chat-win]")).h - full.h) <= 2, "...the whole window again");
  assert.ok(await page.$eval("[data-tq-chat-win] .tq-chat-pop-body", (b) => b.scrollHeight - b.scrollTop - b.clientHeight <= 2), "at its newest line");
  await minimize();
  await page.click("[data-tq-chat-win] [aria-label='Expand the chat']");
  await page.waitForFunction(() => { const w = document.querySelector("[data-tq-chat-win]"); return w && !w.hidden && !w.hasAttribute("data-tq-mini"); }, { timeout: 5000 });
  await minimize();
  await page.focus("[data-tq-chat-win] [aria-label='Expand the chat']");
  await page.keyboard.press("Escape");
  await page.waitForSelector("[data-tq-chat-win][hidden]", { timeout: 5000 });
  await page.waitForFunction(() => !document.querySelector(".tq-compose-box[data-tq-open]"), { timeout: 5000 });

  // ...and over a reload: put away, the pill continues it, the conversation read back from the server
  await page.click(".tq-compose-box textarea");
  await page.waitForSelector("[data-tq-chat-win]:not([hidden])", { timeout: 5000 });
  await minimize();
  await page.reload({ waitUntil: "domcontentloaded" });
  await page.waitForSelector(".tq-compose-box[data-tq-continue]", { timeout: 30000 });
  assert.equal(await hint(), "Continue chat…", "the pill still continues it after a reload");
  await page.click(".tq-compose-box textarea");
  await page.waitForSelector("[data-tq-chat-win]:not([hidden])", { timeout: 5000 });
  assert.match(await page.$eval("[data-tq-chat-win] .tq-chat-pop-body", (e) => e.textContent), /outstanding tasks[\s\S]*open TQ-0004[\s\S]*mark this done/, "the same conversation after the reload");
  await sleep(500);
  assert.ok(await page.$eval("[data-tq-chat-win] .tq-chat-pop-body", (b) => b.scrollHeight - b.scrollTop - b.clientHeight <= 2), "...at its newest line");
  await page.screenshot({ path: process.env.TASKUARY_CHATWIN_SHOT || path.join(os.tmpdir(), "chat-window-open.png") });
  assert.deepEqual(errors, []);
});

/* IT OPENS ONLY BY THE OWNER'S HAND (the owner, 2026-10-28: "when the walk-through ended, the chat reopened by itself"): the walk's lines - its
   end above all - landed in the window's conversation and opened it. Shut, it stays shut through a whole walk to its end; what came is counted
   on the pill. */
test("a walk to its end with the chat window shut never opens it", { timeout: 300000 }, async (t) => {
  const harness = await startHarness();
  t.after(() => harness.close());
  const req = async (p, method = "GET", body) => (await fetch(`${harness.fixtureApi}${p}`, { method, headers: { "X-Taskuary-Token": harness.token, "Content-Type": "application/json" },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }) })).json();
  // ...a short walk: two tasks left open
  const pile = await req("/api/funnel/pile");
  for (const i of pile.items.filter((x) => x.tid).slice(2)) await req(`/api/tasks/${i.tid}`, "PATCH", { Status: "done" });
  const page = await harness.newPage();
  await page.setViewport({ width: 1440, height: 900, deviceScaleFactor: 1 });
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(harness.ui, { waitUntil: "domcontentloaded", timeout: 20000 });
  await page.waitForSelector("[data-tq-rail] .tq-pile-row", { timeout: 30000 });
  await sleep(1500);
  // ...a conversation had, then ×: the window has lines a walk's would join
  await ask(page, Q);
  await page.click("[data-tq-chat-win] [aria-label='Close the chat']");
  await page.waitForSelector("[data-tq-chat-win][hidden]", { timeout: 5000 });
  await page.evaluate(() => { window.__opened = 0;
    new MutationObserver(() => { const w = document.querySelector("[data-tq-chat-win]"); if (w && !w.hidden) window.__opened += 1; })
      .observe(document.body, { subtree: true, attributes: true, attributeFilter: ["hidden"], childList: true }); });
  const press = (re) => page.evaluate((src) => {
    const b = [...document.querySelectorAll(".tq-asst-col button")].find((n) => new RegExp(src).test(n.textContent.trim()) && !n.disabled && n.offsetParent);
    if (b) b.click(); return !!b;
  }, re.source);
  const until = async (f, ms = 15000) => { for (const t0 = Date.now(); Date.now() - t0 < ms; await sleep(250)) if (await f()) return true; return false; };
  let nexts = 0;
  if (await until(() => press(/^Walk me through my tasks$/), 6000)) nexts += 1;
  for (let i = 0; i < 30 && await until(() => press(/^(Next|All read, next)( →)?$/), 6000); i += 1) { nexts += 1; await sleep(1500); }
  await sleep(2500);
  assert.ok(nexts >= 2, `walked: ${nexts} presses`);
  assert.ok(await until(async () => (await page.evaluate(() => [...document.querySelectorAll(".tq-asst-col button")].filter((b) => b.offsetParent).map((b) => b.textContent.trim())))
    .includes("Walk me through my tasks"), 8000), "the walk's end is on the dock, as today");
  assert.equal(await page.evaluate(() => window.__opened), 0, "the window never opened by itself");
  assert.ok(await page.$eval("[data-tq-chat-win]", (e) => e.hidden), "...and is shut at the walk's end");
  assert.deepEqual(errors, []);
});
