import assert from "node:assert/strict";
import test from "node:test";

import { startHarness } from "./harness.mjs";

/* THE ONE-ROW CHAT BAR (the owner, 2026-10-26: "try one row chat bar with ai pop up. let me see what it looks like"). The box is how the
   owner tells Taskuary what to do with the task on the table, and it cost a whole band under the row. At 1600x810: the row's groups and
   the box share ONE line, the box a pill at rest; focused it widens and the groups fold (Next stays); a line sent comes back in a pop-up
   ABOVE the box, over the task view, which does not move; Esc shuts it, the box's own button brings it back. */
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const box = (page, sel) => page.$eval(sel, (e) => { const r = e.getBoundingClientRect(); return { x: Math.round(r.left), y: Math.round(r.top), w: Math.round(r.width), h: Math.round(r.height) }; });

test("one row: the action row and the box share a line, the answer pops up over the task without moving it", { timeout: 300000 }, async (t) => {
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

  // AT REST: one line - the row's buttons and the pill sit side by side, the pill at the end, its tools hidden
  const rest = await page.evaluate(() => {
    const line = document.querySelector(".tq-dock .tq-dock-line"), row = line.querySelector("[data-tq-row] .tq-arow-verbs"), pill = line.querySelector(".tq-compose-box");
    const r = (e) => e.getBoundingClientRect(), mid = (e) => r(e).top + r(e).height / 2;
    return { line: Math.round(r(line).height), mid: Math.abs(mid(row) - mid(pill)), after: r(pill).left >= r(row).right - 1, pill: Math.round(r(pill).width),
      open: line.querySelector(".tq-compose-box").hasAttribute("data-tq-open"), tools: getComputedStyle(line.querySelector(".tq-compose-tools")).display,
      hint: line.querySelector("textarea").placeholder, labels: [...row.querySelectorAll("button")].map((b) => b.textContent.trim()) };
  });
  const say = JSON.stringify(rest);
  assert.ok(rest.line <= 46, `the row and the box are one line ${say}`);
  assert.ok(rest.mid <= 3 && rest.after, `the pill stands at the row's end, on its line ${say}`);
  assert.ok(rest.pill >= 200 && rest.pill <= 240 && !rest.open && rest.tools === "none", `a pill at rest ${say}`);
  assert.equal(rest.hint, "Tell me what to do…");

  // FOCUSED: it widens, shows its tools, and the groups fold for the room - Next stays
  await page.click(".tq-compose-box textarea");
  await page.waitForSelector(".tq-compose-box[data-tq-open]", { timeout: 5000 });
  await sleep(300);
  const wide = await page.evaluate(() => {
    const line = document.querySelector(".tq-dock .tq-dock-line"), pill = line.querySelector(".tq-compose-box"), verbs = line.querySelector(".tq-arow-verbs");
    return { pill: Math.round(pill.getBoundingClientRect().width), tools: getComputedStyle(line.querySelector(".tq-compose-tools")).display, line: Math.round(line.getBoundingClientRect().height),
      next: !!verbs.querySelector("[data-tq-next]"), over: verbs.scrollWidth - verbs.clientWidth, labels: [...verbs.querySelectorAll("button")].map((b) => b.textContent.trim()) };
  });
  assert.ok(wide.pill > rest.pill + 150 && wide.tools !== "none", `it widens with its tools ${JSON.stringify(wide)}`);
  assert.ok(wide.next && wide.over <= 1 && wide.line <= 46, `still one line, Next on it, nothing past its edge ${JSON.stringify(wide)}`);
  assert.ok(wide.labels.length < rest.labels.length, `the groups folded for the room ${JSON.stringify({ rest: rest.labels, wide: wide.labels })}`);

  // SENT: the answer comes up above the box, over the task view - which does not move or change size
  const view = await box(page, "[data-tq-canvas-item]"), dock = await box(page, ".tq-dock");
  await page.keyboard.type("what does Tom want from us?");
  await page.keyboard.press("Enter");
  await page.waitForSelector("[data-tq-chat-pop]:not([hidden])", { timeout: 20000 });
  await page.waitForFunction(() => document.querySelector("[data-tq-chat-pop] .tq-msg.you")?.textContent.includes("what does Tom want"), { timeout: 20000 });
  await page.waitForFunction(() => !document.querySelector("[data-tq-chat-pop] .tq-pending"), { timeout: 30000 });
  const pop = await box(page, "[data-tq-chat-pop]"), input = await box(page, ".tq-compose-box");
  assert.ok(pop.y + pop.h <= input.y + 2, `the pop-up stands above the box ${JSON.stringify({ pop, input })}`);
  const body = await box(page, ".tq-chat-body");
  assert.ok(pop.y < body.y + body.h && pop.y > body.y, `...over the canvas the task view stands on ${JSON.stringify({ pop, body })}`);
  assert.deepEqual(await box(page, "[data-tq-canvas-item]"), view, "the task view did not move");
  assert.ok(pop.h <= Math.max(180, Math.ceil(0.45 * body.h)) + 2, `a few turns tall at most ${JSON.stringify({ pop, body })}`);
  assert.equal(await page.$$eval(".tq-chat-body .tq-msg.you", (els) => els.filter((e) => e.textContent.includes("what does Tom want")).length), 0, "the line is not drawn under the task as well");
  assert.ok((await box(page, ".tq-dock")).h <= dock.h, "the dock did not grow");

  // ESC shuts it; the box's own button brings it back
  await page.keyboard.press("Escape");
  await page.waitForSelector("[data-tq-chat-pop][hidden]", { timeout: 5000 });
  assert.deepEqual(await box(page, "[data-tq-canvas-item]"), view, "the task view did not move");
  await page.click("[data-tq-pop-again]");
  await page.waitForSelector("[data-tq-chat-pop]:not([hidden])", { timeout: 5000 });
  // ...and a press outside it shuts it too
  await page.click("[data-tq-task-head]");
  await page.waitForSelector("[data-tq-chat-pop][hidden]", { timeout: 5000 });
  // ...Esc in an empty box gives the pill back
  await page.click(".tq-compose-box textarea");
  await page.keyboard.press("Escape");
  await page.waitForFunction(() => !document.querySelector(".tq-compose-box[data-tq-open]"), { timeout: 5000 });
  assert.deepEqual(errors, []);
});
