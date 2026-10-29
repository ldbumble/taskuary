import assert from "node:assert/strict";
import test from "node:test";

import { startHarness } from "./harness.mjs";

/* THE CHAT IS ITS OWN UNIT BESIDE THE BAR (the owner, 2026-10-29: "it looks weird coming out of the bottom bar", after the one-row chat
   bar of 2026-10-26). At 1600x810: the bar is one line and ENDS before the chat, a gap between them; the chat is a wide ask bar in the corner;
   focused it opens up out of its own corner into the window, and the bar beside it does not move or fold (Next stays); a line sent comes
   back in the window, over the task view, which does not move; Esc shuts it to the pill, the pill brings it back. */
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const box = (page, sel) => page.$eval(sel, (e) => { const r = e.getBoundingClientRect(); return { x: Math.round(r.left), y: Math.round(r.top), w: Math.round(r.width), h: Math.round(r.height) }; });

test("the chat is its own unit: the bar ends before it, it opens out of its corner, the answer over the task without moving it", { timeout: 300000 }, async (t) => {
  const harness = await startHarness();
  t.after(() => harness.close());
  const page = await harness.newPage();
  await page.setViewport({ width: 1600, height: 810, deviceScaleFactor: 1 });
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(harness.ui, { waitUntil: "domcontentloaded", timeout: 20000 });
  await page.waitForSelector("[data-tq-rail] .tq-pile-row", { timeout: 30000 });
  const tasks = (await (await fetch(`${harness.fixtureApi}/api/tasks`, { headers: { "X-Taskuary-Token": harness.token } })).json()).data;
  const reply = tasks.find((x) => /^Invoice 88213/.test(x.Title));
  assert.ok(reply, "the demo's invoice reply");
  await page.evaluate((id) => { location.hash = `task=${id}`; }, reply.TaskId);
  await page.waitForSelector(`[data-tq-task-page="${reply.TaskId}"]`, { timeout: 20000 });
  await page.waitForSelector(".tq-dock [data-tq-row] [data-tq-next]", { timeout: 20000 });
  await sleep(2500);

  // AT REST: the bar one line, the pill apart from it in the corner, small, its tools hidden
  const rest = await page.evaluate(() => {
    const dock = document.querySelector(".tq-dock"), row = dock.querySelector("[data-tq-row] .tq-arow-verbs"), pill = document.querySelector(".tq-chat-unit .tq-compose-box");
    const r = (e) => e.getBoundingClientRect(), mid = (e) => r(e).top + r(e).height / 2;
    return { line: Math.round(r(dock).height), mid: Math.abs(mid(dock) - mid(pill)), gap: Math.round(r(pill).left - r(dock).right), pill: Math.round(r(pill).width),
      right: Math.round(r(pill).right), inBar: !!dock.querySelector(".tq-compose-box"), open: pill.hasAttribute("data-tq-open"),
      tools: getComputedStyle(pill.querySelector(".tq-compose-tools")).display, hint: pill.querySelector("textarea").placeholder,
      labels: [...row.querySelectorAll("button")].map((b) => b.textContent.trim()) };
  });
  const say = JSON.stringify(rest);
  assert.ok(rest.line <= 46, `the bar is one line ${say}`);
  assert.ok(!rest.inBar && rest.gap >= 12 && rest.mid <= 6, `the bar ends before the chat, a gap between them, on one line ${say}`);
  assert.ok(rest.pill >= 300 && !rest.open && rest.tools === "none", `the wide ask bar, as wide as the open window (the owner, 2026-10-29) at rest ${say}`);
  assert.equal(rest.hint, "Ask…");

  // FOCUSED: it opens out of its own corner - its right edge where the pill's was - into the window, with its tools; the bar beside it
  // does not move or fold
  await page.click(".tq-chat-unit textarea");
  await page.waitForSelector(".tq-compose-box[data-tq-open]", { timeout: 5000 });
  await sleep(300);
  const wide = await page.evaluate(() => {
    const dock = document.querySelector(".tq-dock"), pill = document.querySelector(".tq-chat-unit .tq-compose-box"), verbs = dock.querySelector(".tq-arow-verbs"), field = pill.querySelector(".tq-compose-field");
    return { field: Math.round(field.getBoundingClientRect().width), right: Math.round(field.getBoundingClientRect().right), tools: getComputedStyle(pill.querySelector(".tq-compose-tools")).display,
      line: Math.round(dock.getBoundingClientRect().height), above: Math.round(dock.getBoundingClientRect().top - field.getBoundingClientRect().top),
      next: !!verbs.querySelector("[data-tq-next]"), over: verbs.scrollWidth - verbs.clientWidth, labels: [...verbs.querySelectorAll("button")].map((b) => b.textContent.trim()) };
  });
  assert.ok(Math.abs(wide.field - rest.pill) <= 1 && Math.abs(wide.right - rest.right) <= 1 && wide.tools !== "none", `opened it only grows up - never wider - with its tools ${JSON.stringify(wide)}`);
  assert.ok(wide.next && wide.over <= 1 && wide.line <= 46, `the bar still one line, Next on it, nothing past its edge ${JSON.stringify(wide)}`);
  assert.ok(wide.above > 10, `it rises over the canvas ${JSON.stringify(wide)}`);
  assert.deepEqual(wide.labels, rest.labels, "nothing on the bar folded or moved while the chat is open");

  // SENT: the answer comes up above the box, over the task view - which does not move or change size
  const view = await box(page, "[data-tq-canvas-item]"), dock = await box(page, ".tq-dock");
  await page.keyboard.type("what does Tom want from us?");
  await page.keyboard.press("Enter");
  await page.waitForSelector("[data-tq-chat-pop]:not([hidden])", { timeout: 20000 });
  await page.waitForFunction(() => document.querySelector("[data-tq-chat-pop] .tq-msg.you")?.textContent.includes("what does Tom want"), { timeout: 20000 });
  await page.waitForFunction(() => !document.querySelector("[data-tq-chat-pop] .tq-pending"), { timeout: 30000 });
  const pop = await box(page, "[data-tq-chat-pop]"), input = await box(page, ".tq-compose-box .tq-compose-field");
  assert.ok(pop.y + pop.h <= input.y + 2, `the pop-up stands above the box ${JSON.stringify({ pop, input })}`);
  const body = await box(page, ".tq-chat-body");
  assert.ok(pop.y < body.y + body.h && pop.y > body.y, `...over the canvas the task view stands on ${JSON.stringify({ pop, body })}`);
  assert.deepEqual(await box(page, "[data-tq-canvas-item]"), view, "the task view did not move");
  assert.ok(pop.h + input.h <= 0.5 * 810 + 2 && pop.h + input.h >= 300, `the chat window is at most half the screen, at least 300px ${JSON.stringify({ pop, input })}`);
  assert.equal(await page.$$eval(".tq-chat-body .tq-msg.you", (els) => els.filter((e) => e.textContent.includes("what does Tom want")).length), 0, "the line is not drawn under the task as well");
  assert.ok((await box(page, ".tq-dock")).h <= dock.h, "the dock did not grow");

  // ESC shuts the chat window, the box back to its pill; the pill opens it again on the same conversation (the chat window, 2026-10-28)
  await page.keyboard.press("Escape");
  await page.waitForSelector("[data-tq-chat-pop][hidden]", { timeout: 5000 });
  await page.waitForFunction(() => !document.querySelector(".tq-compose-box[data-tq-open]"), { timeout: 5000 });
  assert.deepEqual(await box(page, "[data-tq-canvas-item]"), view, "the task view did not move");
  await page.click(".tq-compose-box textarea");
  await page.waitForSelector("[data-tq-chat-pop]:not([hidden])", { timeout: 5000 });
  assert.match(await page.$eval("[data-tq-chat-pop]", (e) => e.textContent), /what does Tom want/, "the same conversation");
  // ...and a press outside it leaves it open: only its × or Esc shuts it
  await page.click("[data-tq-task-head]");
  await sleep(300);
  assert.equal(await page.$eval("[data-tq-chat-pop]", (e) => e.hidden), false, "a press outside leaves it open");
  // ...and an Esc aimed at the task view is the task view's (the owner, 2026-10-28: "make sure that never happens"); Esc IN it shuts it
  await page.keyboard.press("Escape"); await sleep(300);
  assert.equal(await page.$eval("[data-tq-chat-pop]", (e) => e.hidden), false, "an Esc outside leaves it open");
  await page.click(".tq-compose-box textarea");
  await page.keyboard.press("Escape");
  await page.waitForFunction(() => !document.querySelector(".tq-compose-box[data-tq-open]"), { timeout: 5000 });
  assert.deepEqual(errors, []);
});
