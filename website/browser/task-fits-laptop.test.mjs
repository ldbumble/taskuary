import assert from "node:assert/strict";
import test from "node:test";
import { startHarness } from "./harness.mjs";

// A FAILED RUN FITS A LAPTOP (the owner, 2026-10-26, 1600x810: "you can't see anything. there are too many lines on top of the tasks. button
// height is too high? you can't see what you have to do.. this has to be fixed"): a playbook whose agent could not start, cut off by a
// restart after. Its title was said twice, three scrollbars stood in one column, the reason it failed was at the foot of a scroller inside
// a scroller, and the dock took 138px. Now: the title once, the reason first, one scroller, the dock about 115px.
// ...AND ONE MAIN VIEW AT EVERY WIDTH (the owner, 2026-10-26: "if task view is where the task opens to it should only open on that, and then
// right side arrow should pull out the agent/close out screens. If up to agent or close out open those with coming from in left side
// draw"): the failed run is the page with Came from behind a tab on the left; a task nothing has worked yet is the page with Agent and
// Close out behind a tab on the right. A drawer slides OVER the main view - it does not move - and Escape or a press outside shuts it.
const rect = (page, sel) => page.$eval(sel, (e) => { const r = e.getBoundingClientRect(); return { x: Math.round(r.left), y: Math.round(r.top), w: Math.round(r.width), h: Math.round(r.height) }; });

test("one main view at every width: a failed run with Came from on the left, a fresh task with Agent and Close out on the right", { timeout: 300000 }, async (t) => {
  const harness = await startHarness();
  t.after(() => harness.close());
  const page = await harness.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(harness.ui, { waitUntil: "domcontentloaded", timeout: 20000 });
  await page.waitForSelector("[data-tq-rail] .tq-pile-row", { timeout: 30000 });
  const made = await page.evaluate(async () => (await fetch("/api/fixture/task/playbook-failed", { method: "POST", body: "{}",
    headers: { "X-Taskuary-Token": localStorage.getItem("taskuary_token"), "Content-Type": "application/json" } })).json());
  assert.ok(made.taskId, JSON.stringify(made));
  const burst = await page.evaluate(async () => (await fetch("/api/fixture/task/chat-burst", { method: "POST", body: "{}",
    headers: { "X-Taskuary-Token": localStorage.getItem("taskuary_token"), "Content-Type": "application/json" } })).json());
  assert.ok(burst.taskId, JSON.stringify(burst));
  const tasks = (await (await fetch(`${harness.fixtureApi}/api/tasks`, { headers: { "X-Taskuary-Token": harness.token } })).json()).data;
  const fresh = tasks.find((x) => /^Year-end audit/.test(x.Title) && !["done", "dropped"].includes(x.Status));
  assert.ok(fresh, "the demo's audit task, nothing run on it");
  const open = async (id, ready) => {
    await page.evaluate((id) => { location.hash = ""; location.hash = `task=${id}`; }, id);
    await page.waitForSelector(`[data-tq-task-page="${id}"] ${ready}`, { timeout: 20000 });
    await page.waitForSelector(".tq-dock [data-tq-row]", { timeout: 20000 });
    await new Promise((resolve) => setTimeout(resolve, 2000));   // past the lit move's hold and the chat's first draw
  };
  for (const [width, height] of [[1920, 1080], [1600, 810], [1366, 768]]) {
    await page.setViewport({ width, height, deviceScaleFactor: 1 });
    await open(made.taskId, "[data-tq-run-why]");
    const m = await page.evaluate(() => {
      const card = document.querySelector("[data-tq-canvas-item]");
      const scrolls = (e) => /auto|scroll/.test(getComputedStyle(e).overflowY) && e.scrollHeight > e.clientHeight + 1;
      const work = card.querySelector("[data-tq-work]");
      const inner = [...work.querySelectorAll("*")].filter(scrolls).map((e) => `${[...e.attributes].filter((a) => a.name.startsWith("data-")).map((a) => a.name).join(",") || e.className} ${e.clientHeight}/${e.scrollHeight}`);
      const why = card.querySelector("[data-tq-run-why]"), w = why.getBoundingClientRect();
      // seen: inside the window and inside every box above it that clips
      let seen = w.top >= 0 && w.bottom <= innerHeight;
      for (let p = why.parentElement; p && seen; p = p.parentElement) {
        if (getComputedStyle(p).overflowY === "visible") continue;
        const b = p.getBoundingClientRect(); seen = w.top >= b.top - 1 && w.bottom <= b.bottom + 1;
      }
      const title = card.querySelector("[data-tq-task-head]").textContent.match(/Create playbook: [^.]{20}/)?.[0] || "";
      const tab = card.querySelector("[data-tq-from-line]");
      return { main: card.querySelector("[data-tq-task-body]").getAttribute("data-tq-main"), inner, seen, why: why.textContent, ask: !!card.querySelector("[data-tq-ask]"), title,
        twice: title ? card.innerText.split(title).length - 1 : -1, dock: document.querySelector(".tq-dock").getBoundingClientRect().height,
        from: !!card.querySelector("[data-tq-from]"), right: !!card.querySelector("[data-tq-work-tab]"),
        tab: tab && { arrow: tab.querySelector("[data-tq-from-chevron]").textContent, words: tab.textContent, expanded: tab.getAttribute("aria-expanded"), w: tab.getBoundingClientRect().width } };
    });
    const say = `${width}x${height}: ${JSON.stringify(m)}`;
    assert.equal(m.main, "work", `the failed run is the page ${say}`);
    assert.ok(!m.from && !m.right, `Came from is shut in its drawer, no right tab ${say}`);
    assert.ok(m.tab && m.tab.arrow === "›" && /Came from/.test(m.tab.words) && m.tab.expanded === "false" && m.tab.w >= 24, `the left tab, its arrow and its words ${say}`);
    assert.deepEqual(m.inner, [], `nothing scrolls inside the main view ${say}`);
    assert.ok(m.title && !m.ask && m.twice === 1, `the title is said once ${say}`);
    assert.match(m.why, /could not start: this tool has no built-in reviewer/, say);
    assert.ok(m.seen, `the reason is in view ${say}`);
    assert.ok(m.dock <= 120, `the dock is short ${say}`);
    // ...the tab pulls Came from out OVER the main view, which stays where it was; Escape shuts it and hands focus back to the tab
    const before = await rect(page, "[data-tq-work]");
    await page.click("[data-tq-from-line]");
    await page.waitForSelector("[data-tq-from-side]", { visible: true, timeout: 5000 });
    assert.match(await page.$eval("[data-tq-from-side]", (e) => e.innerText), /Came from[\s\S]*Site ops digest/);
    assert.equal(await page.$eval("[data-tq-from-line]", (e) => e.getAttribute("aria-expanded")), "true");
    assert.deepEqual(await rect(page, "[data-tq-work]"), before, `the main view does not move ${say}`);
    await page.keyboard.press("Escape");
    await page.waitForFunction(() => !document.querySelector("[data-tq-from-side]"), { timeout: 5000 });
    assert.ok(await page.evaluate(() => document.activeElement?.hasAttribute("data-tq-from-line")), "Escape hands focus back to the tab");

    // A TASK NOTHING HAS WORKED YET: the task is the page, Agent and Close out behind the right tab
    await open(fresh.TaskId, "[data-tq-work-tab]");
    const f = await page.evaluate(() => {
      const card = document.querySelector("[data-tq-canvas-item]"), tab = card.querySelector("[data-tq-work-tab]"), work = card.querySelector("[data-tq-work]");
      return { main: card.querySelector("[data-tq-task-body]").getAttribute("data-tq-main"), left: !!card.querySelector("[data-tq-from-line]"),
        work: work && getComputedStyle(work).display, arrow: tab.querySelector("[data-tq-from-chevron]").textContent, words: tab.textContent };
    });
    assert.deepEqual(f, { main: "task", left: false, work: "none", arrow: "‹", words: "‹Agent · Close out" }, `${width}: the fresh task's page`);
    const from = await rect(page, "[data-tq-from]"), card = await rect(page, "[data-tq-canvas-item]");
    // ...the main view fills the width (the owner, 2026-10-26: "no main view should fill the screen. why waste space?") - less the tab
    assert.ok(from.w >= card.w - 80, `${width}: the task fills the width ${JSON.stringify({ from, card })}`);
    // ...and the tab is lit: the drawer holds the next move (an agent for an ask nothing has worked)
    assert.ok(await page.$("[data-tq-work-tab][data-tq-lit]"), `${width}: the right tab is lit`);
    await page.click("[data-tq-work-tab]");
    await page.waitForSelector("[data-tq-work-side] [data-tq-closeout]", { visible: true, timeout: 5000 });
    assert.equal(await page.$eval("[data-tq-work-tab]", (e) => e.getAttribute("aria-expanded")), "true");
    const side = await rect(page, "[data-tq-work-side]");
    assert.deepEqual(await rect(page, "[data-tq-from]"), from, `${width}: the task under the drawer does not move`);
    assert.ok(side.x + side.w > from.x + from.w - 1 || side.x > from.x, `${width}: the drawer comes in from the right ${JSON.stringify({ side, from })}`);
    // ...a press outside it shuts it
    await page.click("[data-tq-task-head]");
    await page.waitForFunction(() => getComputedStyle(document.querySelector("[data-tq-work]")).display === "none", { timeout: 5000 });

    // A REPLY WITH NOTHING DRAFTED opens on the task, the right tab lit and naming the move (the owner, 2026-10-26: "you can open on task
    // but highlight the side bar so people know to go there")
    await open(burst.taskId, "[data-tq-work-tab]");
    const b = await page.evaluate(() => {
      const card = document.querySelector("[data-tq-canvas-item]"), tab = card.querySelector("[data-tq-work-tab]");
      return { main: card.querySelector("[data-tq-task-body]").getAttribute("data-tq-main"), lit: tab.hasAttribute("data-tq-lit"),
        words: tab.querySelector("[data-tq-from-words]").textContent, bg: getComputedStyle(tab).backgroundColor };
    });
    assert.equal(b.main, "task", `${width}: ${JSON.stringify(b)}`);
    assert.ok(b.lit && b.words === "Close out · reply to Gail Moreno" && b.bg === "rgb(85, 105, 122)", `${width}: the tab is lit and names the reply ${JSON.stringify(b)}`);
  }
  assert.deepEqual(errors, []);
});
