import assert from "node:assert/strict";
import test from "node:test";

import { startHarness } from "./harness.mjs";

/* THE TASK IN THREE SECTIONS (the owner, 2026-10-27, from a mockup: "input -> agent/advisor -> close ... 3 sections from left to right showing
   the flow; on the outside it shows the status of each category and opens up to the one it's up to"). On the demo world at 1440x900:
   Came from | Agent | Close out in that order, the one the task is up to open, the other two closed tabs ~156px wide whose words read
   across; a tab's press opens its section in one smooth move - never two open, the card never changing height - and the card takes the
   canvas down to a small gap over the dock. A row's press opens the section it belongs to. A live agent keeps nearly all the width, Came
   from and Close out slim 44px tabs, and its terminal is never remounted or resized by a look away. Invented people only. */
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// the card of the task opened last (a canvas can hold a card put down a moment ago)
let CUR = "[data-tq-canvas-item]";
const look = (page) => page.evaluate((CUR) => {
  const item = document.querySelector(CUR), body = item?.querySelector("[data-tq-task-body]"), cv = document.querySelector(".tq-chat-body");
  const box = (e) => e && (({ left, top, width, height }) => ({ left: Math.round(left), top: Math.round(top), w: Math.round(width), h: Math.round(height) }))(e.getBoundingClientRect());
  return { main: body?.getAttribute("data-tq-main"), stage: body?.getAttribute("data-tq-stage"), card: box(item), canvas: box(cv), body: box(body),
    slots: [...(item?.querySelectorAll("[data-tq-slot]") || [])].map((s) => ({ key: s.dataset.tqSlot, open: s.hasAttribute("data-tq-open"), ...box(s) })),
    tabs: [...(item?.querySelectorAll("[data-tq-section-tab]") || [])].map((t) => ({ key: t.dataset.tqSectionTab, text: t.innerText, mini: t.hasAttribute("data-tq-mini"),
      here: t.hasAttribute("data-tq-here"), w: Math.round(t.getBoundingClientRect().width), writing: getComputedStyle(t.querySelector("[data-tq-tab-name], [data-tq-tab-n]")).writingMode })) };
}, CUR);
// ...a tab pressed at the first frame, and every frame for a while after: how many sections are open on screen, and the card's height
const watch = (page, ms, tab) => page.evaluate((ms, CUR, tab) => new Promise((done) => {
  const seen = [], t0 = performance.now();
  const frame = () => {
    const item = document.querySelector(CUR);
    if (!seen.length) item.querySelector(tab).click();
    const open = [...item.querySelectorAll("[data-tq-slot] > [role=region]")].filter((e) => getComputedStyle(e).display !== "none" && getComputedStyle(e).visibility === "visible").length;
    seen.push({ open, h: Math.round(item.getBoundingClientRect().height) });
    if (performance.now() - t0 < ms) requestAnimationFrame(frame); else done(seen);
  };
  requestAnimationFrame(frame);
}), ms, CUR, tab);
const openTask = async (page, id) => {
  CUR = `[data-tq-canvas-item]:has([data-tq-task-page="${id}"])`;
  await page.evaluate((id) => { location.hash = ""; location.hash = `task=${id}`; }, id);
  await page.waitForSelector(`[data-tq-canvas-item] [data-tq-task-page="${id}"] [data-tq-task-body][data-tq-sections]`, { timeout: 20000 });
  await sleep(1800);
};
const rowPress = (page, label) => page.evaluate((label) => {
  const b = [...document.querySelectorAll("[data-tq-row] button")].find((x) => x.textContent.trim() === label && !x.disabled);
  b?.click(); return !!b;
}, label);

test("three sections in the flow's order, open where the task is up to, tabs that say where each stands", { timeout: 300000 }, async (t) => {
  const h = await startHarness();
  t.after(() => h.close());
  const page = await h.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.setViewport({ width: 1440, height: 900, deviceScaleFactor: 1 });
  await page.goto(h.ui, { waitUntil: "domcontentloaded" });
  await page.waitForSelector("[data-tq-rail] .tq-pile-row", { timeout: 30000 });
  const tasks = (await (await fetch(`${h.fixtureApi}/api/tasks`, { headers: { "X-Taskuary-Token": h.token } })).json()).data;
  const id = (re) => tasks.find((x) => re.test(x.Title))?.TaskId;

  await t.test("a drafted reply opens on Close out; Came from and Agent are its tabs, words across, ~156px, with their status", async () => {
    await openTask(page, id(/^Invoice 88213/));
    const m = await look(page);
    assert.equal(m.main, "close", JSON.stringify(m));
    assert.deepEqual(m.slots.map((s) => s.key), ["from", "agent", "close"], "the flow's order");
    assert.deepEqual(m.slots.map((s) => s.open), [false, false, true], "one open");
    for (const tab of m.tabs) {
      assert.ok(Math.abs(tab.w - 156) <= 2, `${tab.key} tab is ~156px: ${tab.w}`);
      assert.equal(tab.writing, "horizontal-tb", `${tab.key}'s words read across`);
    }
    const from = m.tabs.find((x) => x.key === "from").text, agent = m.tabs.find((x) => x.key === "agent").text;
    assert.match(from, /Came from[\s\S]*Email · 1 message[\s\S]*Tom Alvarez: “This invoice[\s\S]*Sorted: a reply to send[\s\S]*1$/, from);
    assert.match(agent, /Agent[\s\S]*not started[\s\S]*2$/, agent);
    assert.ok(m.slots[2].w > 600, `the open one fills the rest: ${m.slots[2].w}`);
    // ...the card takes the canvas, pinned at its top, a small gap over the dock
    assert.ok(Math.abs(m.card.top - m.canvas.top) <= 2, `pinned to the canvas's top ${JSON.stringify(m)}`);
    assert.ok(m.card.h >= m.canvas.h - 30, `takes the canvas: ${m.card.h} of ${m.canvas.h}`);
  });

  await t.test("a tab opens its section in one smooth move: never two open, the card one height", async () => {
    const before = await look(page);
    const seen = await watch(page, 700, "[data-tq-section-tab=from]");
    assert.ok(seen.every((f) => f.open <= 1), `two sections open in one frame: ${JSON.stringify(seen.filter((f) => f.open > 1).slice(0, 3))}`);
    assert.ok(seen.every((f) => Math.abs(f.h - before.card.h) <= 1), `the card moved: ${[...new Set(seen.map((f) => f.h))]}`);
    const m = await look(page);
    assert.equal(m.main, "from");
    assert.deepEqual(m.slots.map((s) => s.open), [true, false, false]);
    assert.match(await page.$eval("[data-tq-canvas-item] [data-tq-from]", (e) => e.innerText), /What came in[\s\S]*What triage made of it/);
    assert.doesNotMatch(await page.$eval("[data-tq-canvas-item] [data-tq-from]", (e) => e.innerText), /Full message history/, "no second copy at the foot");
    const close = m.tabs.find((x) => x.key === "close");
    assert.ok(close.here, "Close out is where the task is up to");
    assert.match(close.text, /Close out[\s\S]*Reply to Tom Alvarez[\s\S]*Drafted · waiting for Send[\s\S]*Up to here[\s\S]*3$/, close.text);
    // ...and the stage is the task's, not the pick's
    assert.equal(m.stage, before.stage);
    await page.click(`${CUR} [data-tq-section-tab=agent]`); await sleep(500);
    assert.equal((await look(page)).main, "agent");
    await page.click(`${CUR} [data-tq-section-tab=close]`); await sleep(500);
    const back = await look(page);
    assert.equal(back.main, "close");
    assert.equal(back.card.h, before.card.h, "one height through every switch");
  });

  // ...each kind of task opens where it is up to
  await t.test("each task opens on the section it is up to", async () => {
    for (const [re, want] of [[/^Invoice 88213/, "close"], [/^Reconcile the August GL export/, "agent"], [/^Year-end audit/, "from"],
      [/^Ray: schema sign-off/, "from"], [/^Migrate the census export/, "from"], [/^Invite: AP cutover dry run/, "from"]]) {   // owed, nothing drafted: what came in first (2026-10-28)
      const tid = id(re);
      if (!tid) continue;
      await openTask(page, tid);
      const m = await look(page);
      assert.equal(m.main, want, `${re}: ${m.stage} opened on ${m.main}`);
      assert.ok(!m.tabs.some((x) => x.here), `${re}: the open section is where it is up to, so no tab says so`);
    }
  });

  // A PRESS OPENS THE SECTION IT BELONGS TO (the owner, 2026-10-27)
  await t.test("a row's press opens the section it belongs to", async () => {
    for (const [re, start, label, want] of [
      [/^Reconcile the August GL export/, "agent", "Reply", "close"],
      [/^Year-end audit/, "from", "Reply", "close"],
      [/^Invoice 88213/, "close", "Send to agent", "agent"],
      [/^Migrate the census export/, "from", "Hand it to a person", "close"]]) {   // (Year-end has a draft by now: it opens on Close out)
      await openTask(page, id(re));
      const at = await look(page);
      assert.equal(at.main, start, `${re} opens on ${start}: ${JSON.stringify(at)}`);
      const pressed = await rowPress(page, label);
      if (!pressed) { t.diagnostic(`${label} is not on the row for ${re}`); continue; }
      await sleep(700);
      assert.equal((await look(page)).main, want, `${label} on ${re} opens ${want}`);
      await page.keyboard.press("Escape"); await sleep(300);
    }
  });
  assert.deepEqual(errors, []);
});

test("a live agent keeps the width: slim Came from and Close out, its terminal kept through a look away", { timeout: 300000 }, async (t) => {
  const h = await startHarness();
  t.after(() => h.close());
  const page = await h.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.setViewport({ width: 1440, height: 900, deviceScaleFactor: 1 });
  await page.goto(h.ui, { waitUntil: "domcontentloaded" });
  await page.waitForSelector("[data-tq-rail] .tq-pile-row", { timeout: 30000 });
  const tasks = (await (await fetch(`${h.fixtureApi}/api/tasks`, { headers: { "X-Taskuary-Token": h.token } })).json()).data;
  const live = tasks.find((x) => x.State === "working" || /census sync fails/.test(x.Title));
  await openTask(page, live.TaskId);
  await page.waitForSelector("[data-tq-canvas-item] .xterm", { timeout: 20000 });
  await sleep(800);
  const m = await look(page);
  assert.equal(m.main, "agent");
  assert.deepEqual(m.tabs.map((x) => [x.key, x.mini, x.w]), [["from", true, 44], ["close", true, 44]], JSON.stringify(m.tabs));
  const agent = m.slots.find((s) => s.key === "agent");
  assert.ok(agent.w >= m.body.w - 90, `the live agent keeps nearly all of it: ${agent.w} of ${m.body.w}`);
  // the terminal, marked, and its size
  const term = () => page.evaluate(() => { const x = document.querySelector("[data-tq-canvas-item] .xterm"); if (x && !x.__mark) x.__mark = Math.random();
    const r = x?.querySelector(".xterm-screen")?.getBoundingClientRect(); return { mark: x?.__mark, w: Math.round(r?.width || 0), h: Math.round(r?.height || 0) }; });
  const t0 = await term();
  await page.click(`${CUR} [data-tq-section-tab=from]`); await sleep(600);
  const away = await look(page);
  assert.equal(away.main, "from", "Came from opens over the live agent");
  assert.ok(away.tabs.some((x) => x.key === "agent" && !x.mini), "the agent folds to its tab");
  const t1 = await term();
  assert.equal(t1.mark, t0.mark, "the terminal is the same one, never remounted");
  assert.deepEqual([t1.w, t1.h], [t0.w, t0.h], "and never resized while it is out of sight");
  await page.click(`${CUR} [data-tq-section-tab=agent]`); await sleep(600);
  assert.equal((await look(page)).main, "agent");
  const t2 = await term();
  assert.deepEqual([t2.mark, t2.w, t2.h], [t0.mark, t0.w, t0.h], "back on the agent, its screen is as it was");
  assert.deepEqual(errors, []);
});
