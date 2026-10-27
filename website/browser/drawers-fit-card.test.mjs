import assert from "node:assert/strict";
import path from "node:path";
import test from "node:test";

import { startHarness } from "./harness.mjs";

// EVERY DRAWER AND POP-UP FITS WHAT IT OPENS IN (the owner, 2026-10-26, a short finished agent's Result with Came from pulled out: "the ui
// of the sidebars looks messed up? it's bigger then the task box ... check all of the popups or sidebars match sizing"). The drawer ran
// 200px past the card's foot over the canvas, its tab strip with it. Now, at every size and for every kind of task: each drawer and tab
// lies inside the card's body, the body inside the card, the chat's pop-up inside the canvas and off the rail - and what is longer than
// its box scrolls inside it. TASKUARY_SHOTS=<dir> saves a frame of each.
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const DRAWER_FLOOR = 400;   // CanvasItem.jsx
const SIZES =[[1920, 1080], [1600, 810], [1366, 768], [1280, 720], [390, 844]];
const TODO = "Ask the site office for the signed snag list from the last walk-through, check it against the floor plan Gail sent, "
  + "and tell the group who signs it this Thursday and where the keys are picked up from reception";

// every open drawer, tab and pop-up against its container: [what, its rect, the container's], and whatever overflows without a scroller
const measure = (page) => page.evaluate(() => {
  const r = (e) => { const b = e.getBoundingClientRect(); return { t: b.top, b: b.bottom, l: b.left, r: b.right }; };
  const shown = (e) => e && getComputedStyle(e).display !== "none" && e.getBoundingClientRect().height > 0;
  const card = document.querySelector("[data-tq-canvas-item]"), body = card?.querySelector("[data-tq-task-body]");
  const out = [], stuck = [], fill = [];
  const inside = (what, e, box) => { if (shown(e) && box) out.push([what, r(e), box.nodeType ? r(box) : box]); };
  inside("body", body, card);
  for (const sel of ["[data-tq-from-side]", "[data-tq-work-side]", "[data-tq-from-line]", "[data-tq-work-tab]"]) {
    inside(sel, card?.querySelector(sel), body);
    // ...and a drawer or tab is the body's whole height, not a box of its own size
    const e = card?.querySelector(sel);
    if (shown(e) && (Math.abs(r(e).t - r(body).t) > 1 || Math.abs(r(e).b - r(body).b) > 1)) fill.push(`${sel} ${Math.round(r(e).t)}-${Math.round(r(e).b)} in ${Math.round(r(body).t)}-${Math.round(r(body).b)}`);
  }
  // the pop-up's room: the canvas and the dock it stands on (it overlaps the dock's top edge by design, chat-bar.test.mjs)
  const pop = document.querySelector("[data-tq-chat-pop]:not([hidden])"), canvas = document.querySelector(".tq-chat-body"), dock = document.querySelector(".tq-dock");
  if (canvas && dock) inside("pop", pop, { ...r(canvas), b: r(dock).b });
  for (const e of [card?.querySelector("[data-tq-from-side]"), card?.querySelector("[data-tq-work-side]"), pop?.querySelector(".tq-chat-pop-body")])
    if (shown(e) && e.scrollHeight > e.clientHeight + 1 && !/auto|scroll/.test(getComputedStyle(e).overflowY)) stuck.push(e.outerHTML.slice(0, 80));
  const rail = document.querySelector("[data-tq-rail]");
  const overRail = pop && shown(rail) && r(pop).l < r(rail).r - 1 && r(pop).r > r(rail).l + 1;
  return { out, stuck, fill, overRail, main: body?.getAttribute("data-tq-main"), cardH: card && Math.round(card.getBoundingClientRect().height) };
});
// ...every miss at every size gathered, so one run says all of them
const fails = [];
const check = (m, say) => {
  const r = (a) => Object.values(a).map(Math.round).join(",");
  for (const [what, a, b] of m.out)
    if (!(a.t >= b.t - 1 && a.b <= b.b + 1 && a.l >= b.l - 1 && a.r <= b.r + 1)) fails.push(`${what} past its container ${say}: tblr ${r(a)} in ${r(b)}`);
  if (m.stuck.length) fails.push(`overflows without scrolling ${say}: ${m.stuck}`);
  if (m.fill.length) fails.push(`not the body's height ${say}: ${m.fill}`);
  if (m.overRail) fails.push(`the pop-up is over the rail ${say}`);
};

test("every drawer, tab and pop-up lies inside its card or canvas, at five sizes and six kinds of task", { timeout: 900000 }, async (t) => {
  const harness = await startHarness();
  t.after(() => harness.close());
  const page = await harness.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.setViewport({ width: 1600, height: 810, deviceScaleFactor: 1 });
  await page.goto(harness.ui, { waitUntil: "domcontentloaded", timeout: 20000 });
  await page.waitForSelector("[data-tq-rail] .tq-pile-row", { timeout: 30000 });
  const make = (kind, body = {}) => page.evaluate(async (kind, body) => (await fetch(`/api/fixture/${kind}`, { method: "POST", body: JSON.stringify(body),
    headers: { "X-Taskuary-Token": localStorage.getItem("taskuary_token"), "Content-Type": "application/json" } })).json(), kind, body);
  const tasks = (await (await fetch(`${harness.fixtureApi}/api/tasks`, { headers: { "X-Taskuary-Token": harness.token } })).json()).data;
  const fresh = tasks.find((x) => /^Year-end audit/.test(x.Title) && !["done", "dropped"].includes(x.Status));
  const reply = tasks.find((x) => /^Invoice 88213/.test(x.Title));
  const kinds = { short: (await make("task/chat-saved", { todo: TODO })).taskId, long: (await make("task/playbook-failed")).taskId,
    draft: (await make("task/chat-saved", { draft: "Ray Colton signs it on Thursday - keys are at reception from 7." })).taskId,
    todo: (await make("general/rest")).taskId, fresh: fresh?.TaskId, reply: reply?.TaskId, live: (await make("general/canvas")).taskId };
  assert.ok(Object.values(kinds).every(Boolean), JSON.stringify(kinds));
  const shot = (name) => process.env.TASKUARY_SHOTS && page.screenshot({ path: path.join(process.env.TASKUARY_SHOTS, `${name}.png`) });
  const open = async (id) => {
    await page.evaluate((id) => { location.hash = ""; location.hash = `task=${id}`; }, id);
    await page.waitForSelector(`[data-tq-canvas-item] [data-tq-task-page="${id}"] [data-tq-task-body]`, { timeout: 20000 });
    await sleep(1500);
  };
  for (const [width, height] of SIZES) {
    await page.setViewport({ width, height, deviceScaleFactor: 1 });
    for (const [kind, id] of Object.entries(kinds)) {
      await open(id);
      const say = `${kind} at ${width}x${height}`;
      const shut = await measure(page);
      check(shut, `${say}, shut`);
      await shot(`${kind}-${width}x${height}-shut`);
      for (const tab of ["[data-tq-from-line]", "[data-tq-work-tab]"]) {
        if (!(await page.$(`[data-tq-canvas-item] ${tab}`))) continue;
        await page.click(`[data-tq-canvas-item] ${tab}`);
        await sleep(500);
        const m = await measure(page);
        await shot(`${kind}-${width}x${height}-${tab.includes("from") ? "left" : "right"}`);
        check(m, `${say}, ${tab} open (${m.main})`);
        if (!m.out.some(([w]) => /side/.test(w))) fails.push(`the drawer did not open ${say} ${tab}`);
        // ...and it does not stretch the card past what it says, but to the floor a drawer is read in (CanvasItem DRAWER_FLOOR)
        if (m.cardH > Math.max(shut.cardH, DRAWER_FLOOR) + 1) fails.push(`the card grew ${shut.cardH} -> ${m.cardH} for ${tab} ${say}`);
        await page.click(`[data-tq-canvas-item] ${tab}`);
        await sleep(300);
      }
    }
    // THE CHAT'S POP-UP over a task with its row (chat-bar.test.mjs): inside the canvas, off the rail, scrolling inside - the desk's
    // one-row dock's; a phone's row rides in the view with no pill
    if (width < 600) continue;
    await open(kinds.reply);
    await page.waitForSelector("[data-tq-row] [data-tq-next]", { timeout: 20000 });   // a phone's row rides at the view's foot
    await page.click(".tq-compose-box textarea");
    await page.keyboard.type(`what does Tom want from us at ${width}?`);
    await page.keyboard.press("Enter");
    await page.waitForSelector("[data-tq-chat-pop]:not([hidden])", { timeout: 20000 });
    await page.waitForFunction(() => !document.querySelector("[data-tq-chat-pop] .tq-pending"), { timeout: 30000 });
    await sleep(300);
    const m = await measure(page);
    await shot(`pop-${width}x${height}`);
    check(m, `the pop-up at ${width}x${height}`);
    if (!m.out.some(([w]) => w === "pop")) fails.push(`the pop-up is not up at ${width}x${height}`);
    await page.keyboard.press("Escape");
    await page.keyboard.press("Escape");
  }
  assert.deepEqual(fails, []);
  assert.deepEqual(errors, []);
});
