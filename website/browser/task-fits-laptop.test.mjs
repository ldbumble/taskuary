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
// ...AND IN THREE SECTIONS (the owner, 2026-10-27: "input -> agent/advisor -> close ... opens up to the one it's up to"): the failed run opens
// on the Agent, Came from and Close out its tabs; a task nothing has worked yet on Came from; a reply nothing has drafted on Close out. A
// tab opens its section, the others close.
const rect = (page, sel) => page.$eval(sel, (e) => { const r = e.getBoundingClientRect(); return { x: Math.round(r.left), y: Math.round(r.top), w: Math.round(r.width), h: Math.round(r.height) }; });

test("three sections at every width: a failed run on the Agent, a fresh task on Came from, a reply owed on Came from too", { timeout: 300000 }, async (t) => {
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
  const main = () => page.$eval("[data-tq-canvas-item] [data-tq-task-body]", (e) => e.getAttribute("data-tq-main"));
  const tabs = () => page.$$eval("[data-tq-canvas-item] [data-tq-section-tab]", (els) => els.map((e) => ({ key: e.dataset.tqSectionTab, words: e.innerText,
    arrow: e.querySelector("[data-tq-tab-arrow]")?.textContent, across: getComputedStyle(e.querySelector("[data-tq-tab-name]")).writingMode === "horizontal-tb" })));
  for (const [width, height] of [[1920, 1080], [1600, 810], [1366, 768]]) {
    await page.setViewport({ width, height, deviceScaleFactor: 1 });
    await open(made.taskId, "[data-tq-agent-section] [data-tq-run-why], [data-tq-agent-section] [data-tq-result-summary]");
    const m = await page.evaluate(() => {
      const card = document.querySelector("[data-tq-canvas-item]");
      const scrolls = (e) => /auto|scroll/.test(getComputedStyle(e).overflowY) && e.scrollHeight > e.clientHeight + 1;
      const work = card.querySelector("[data-tq-work]");
      const inner = [...work.querySelectorAll("*")].filter(scrolls).map((e) => `${[...e.attributes].filter((a) => a.name.startsWith("data-")).map((a) => a.name).join(",") || e.className} ${e.clientHeight}/${e.scrollHeight}`);
      // ...the reason, said as the Result's summary while it rests on it (master, 2026-10-27), else the run's own why line
      const why = card.querySelector("[data-tq-run-why]") || card.querySelector("[data-tq-result-summary]"), w = why.getBoundingClientRect();
      // seen: inside the window and inside every box above it that clips
      let seen = w.top >= 0 && w.bottom <= innerHeight;
      for (let p = why.parentElement; p && seen; p = p.parentElement) {
        if (getComputedStyle(p).overflowY === "visible") continue;
        const b = p.getBoundingClientRect(); seen = w.top >= b.top - 1 && w.bottom <= b.bottom + 1;
      }
      const title = card.querySelector("[data-tq-task-head]").textContent.match(/Create playbook: [^.]{20}/)?.[0] || "";
      return { main: card.querySelector("[data-tq-task-body]").getAttribute("data-tq-main"), inner, seen, why: why.textContent, title,
        twice: title ? card.innerText.split(title).length - 1 : -1, dock: document.querySelector(".tq-dock").getBoundingClientRect().height,
        from: !!card.querySelector("[data-tq-from]")?.getBoundingClientRect().width };
    });
    const say = `${width}x${height}: ${JSON.stringify(m)}`;
    assert.equal(m.main, "agent", `the failed run opens on the Agent ${say}`);
    assert.ok(!m.from, `Came from is shut ${say}`);
    const tm = await tabs();
    assert.deepEqual(tm.map((x) => [x.key, x.arrow, x.across]), [["from", "›", true], ["close", "‹", true]], `the tabs either side, words across ${say}`);
    assert.match(tm[0].words, /^›\s+Came from\s+\S/, `Came from's tab says where it came from ${say}`);
    assert.deepEqual(m.inner, [], `nothing scrolls inside the open section ${say}`);
    assert.ok(m.title && m.twice === 1, `the title is said once ${say}`);
    assert.match(m.why, /could not start: this tool has no built-in reviewer/, say);
    assert.ok(m.seen, `the reason is in view ${say}`);
    assert.ok(m.dock <= 120, `the dock is short ${say}`);
    // ...Came from's tab opens it and the Agent folds to its tab; the Agent's brings the run back
    await page.click("[data-tq-canvas-item] [data-tq-section-tab=from]");
    await page.waitForSelector("[data-tq-from]", { visible: true, timeout: 5000 });
    assert.match(await page.$eval("[data-tq-from]", (e) => e.innerText), /Came from[\s\S]*What came in[\s\S]*What triage made of it/i);
    assert.equal(await main(), "from");
    await page.click("[data-tq-canvas-item] [data-tq-section-tab=agent]");
    await page.waitForSelector("[data-tq-agent-section] [data-tq-result-summary], [data-tq-agent-section] [data-tq-run-why]", { visible: true, timeout: 5000 });

    // A TASK NOTHING HAS WORKED YET: Came from is open, the Agent and Close out its tabs on the right
    await open(fresh.TaskId, "[data-tq-section-tab=agent]");
    assert.equal(await main(), "from", `${width}: the fresh task opens on Came from`);
    assert.deepEqual((await tabs()).map((x) => [x.key, x.arrow]), [["agent", "‹"], ["close", "‹"]], `${width}: its tabs`);
    const from = await rect(page, "[data-tq-from]"), card = await rect(page, "[data-tq-canvas-item]");
    // ...the open section fills the width (the owner, 2026-10-26: "no main view should fill the screen. why waste space?") - less the tabs
    assert.ok(from.w >= card.w - 2 * 156 - 10, `${width}: Came from fills the width ${JSON.stringify({ from, card })}`);
    await page.click("[data-tq-canvas-item] [data-tq-section-tab=agent]");
    await page.waitForSelector("[data-tq-work] [data-tq-run-form]", { visible: true, timeout: 5000 });
    assert.equal(await main(), "agent");
    assert.equal(await page.$eval("[data-tq-from]", (e) => e.getBoundingClientRect().width), 0, `${width}: Came from closed as the Agent opened`);

    // A REPLY WITH NOTHING DRAFTED opens on Came from - what they wrote is read first (the owner, 2026-10-28: "why is it opening on Close out,
    // not Came from?") - with Close out its tab, where the reply is written
    await open(burst.taskId, "[data-tq-section-tab=close]");
    assert.equal(await main(), "from", `${width}: the reply owed opens on Came from`);
    assert.match(await page.$eval("[data-tq-from]", (e) => e.innerText), /Gail Moreno/, `${width}: who wrote`);
  }
  assert.deepEqual(errors, []);
});