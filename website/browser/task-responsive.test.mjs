import assert from "node:assert/strict";
import test from "node:test";
import { mkdir } from "node:fs/promises";
import { startHarness } from "./harness.mjs";

// Exercise real expansion and constrained height, not only viewport width. The dock must
// stay compact and every source/work section must remain reachable inside its own card.
test("task context, expanded messages and agent results fit short laptops and phones", { timeout: 240000 }, async (t) => {
  const harness = await startHarness();
  t.after(() => harness.close());
  const page = await harness.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(harness.ui, { waitUntil: "domcontentloaded", timeout: 20000 });
  await page.waitForSelector("[data-tq-rail] .tq-pile-row", { timeout: 30000 });
  const fixture = (path) => page.evaluate(async (path) => {
    const response = await fetch(path, { method: "POST", headers: {
      "X-Taskuary-Token": localStorage.getItem("taskuary_token"), "Content-Type": "application/json",
    }, body: "{}" });
    return response.json();
  }, path);
  const tasks = (await (await fetch(`${harness.fixtureApi}/api/tasks`, { headers: { "X-Taskuary-Token": harness.token } })).json()).data;
  const mail = tasks.find((task) => task.Source === "email" && task.Status === "open" && task.State === "approve");
  const coding = tasks.find((task) => task.Kind === "coding" && /census sync/.test(task.Title) && !["done", "dropped"].includes(task.Status));
  assert.ok(mail && coding);
  const chat = await fixture("/api/fixture/task/chat-burst");
  const saved = await fixture("/api/fixture/task/coding-saved");
  const rest = await fixture("/api/fixture/general/rest");
  assert.ok(chat.taskId && saved.taskId && rest.taskId);
  const shots = process.env.TQ_LAYOUT_SCREENSHOTS;
  if (shots) await mkdir(shots, { recursive: true });

  for (const [width, height] of [[1858, 900], [1440, 900], [1366, 768], [1366, 640], [1280, 720], [1024, 600], [768, 700], [390, 844]]) {
    await page.setViewport({ width, height, deviceScaleFactor: 1 });
    for (const [name, id] of [["email", mail.TaskId], ["messages", chat.taskId], ["result", saved.taskId], ["rest", rest.taskId], ["agent", coding.TaskId]]) {
      await page.evaluate((id) => { location.hash = `task=${id}`; }, id);
      await page.waitForSelector(`[data-tq-task-page="${id}"] [data-tq-task-head]`, { timeout: 20000 });
      if (name === "messages") {
        // Came from's tab pulls its drawer out (the owner, 2026-10-26); the phone's compact context opens on a tap - before the older messages.
        // ...on the desk Came from is the first of the three sections: its tab, then its Full message history (2026-10-27)
        await page.evaluate(() => (document.querySelector("[data-tq-section-tab=from]") || document.querySelector("[data-tq-from-line]") || document.querySelector("[data-tq-from]"))?.click());
        await new Promise((resolve) => setTimeout(resolve, 400));
        await page.evaluate(() => { const h = document.querySelector("[data-tq-from] [data-tq-history-toggle][aria-expanded=false]"); h?.click(); });
        await page.waitForSelector("[data-tq-show-older]", { timeout: 10000 });
        await page.evaluate(() => document.querySelector("[data-tq-show-older]").click());
        await page.waitForSelector("[data-tq-from] [data-tq-chat-thread]");
      } else if (name === "result") {
        await page.waitForSelector("[data-tq-result-summary]", { timeout: 20000 });
      } else if (name === "rest") {
        // its chat is the rest of its Result, behind the Result heading (the owner, 2026-10-27: "click Result to see more")
        await page.waitForSelector("[data-tq-result-summary]", { timeout: 20000 });
        await page.$eval('[data-tq-work]', (w) => (w.querySelector('[data-tq-full-result]') || w.querySelector('[data-tq-step="2"]').parentElement).click());
        await page.waitForSelector("[data-tq-agent-room='rest'] .tq-aui-viewport", { timeout: 20000 });
      } else if (name === "agent") {
        await page.waitForSelector(".xterm-screen", { timeout: 20000 });
      }
      await new Promise((resolve) => setTimeout(resolve, 400));
      const metrics = await page.evaluate(() => {
        const rect = (e) => { const r = e.getBoundingClientRect(); return { x: r.x, y: r.y, w: r.width, h: r.height, right: r.right, bottom: r.bottom }; };
        const card = document.querySelector("[data-tq-canvas-item]");
        const from = card.querySelector("[data-tq-from]");
        const work = card.querySelector("[data-tq-work]");
        const visible = (e) => e.getBoundingClientRect().width && e.getBoundingClientRect().height;
        const rows = [...document.querySelectorAll("[data-tq-row] .tq-arow-verbs")].filter(visible).map((e) => ({
          h: e.getBoundingClientRect().height, overflow: e.scrollWidth - e.clientWidth,
          centers: [...new Set([...e.children].filter(visible).map((c) => Math.round(c.getBoundingClientRect().top + c.getBoundingClientRect().height / 2)))],
        }));
        const compose = document.querySelector(".tq-compose-box textarea");
        return { pageOverflow: document.documentElement.scrollWidth - innerWidth, card: rect(card),
          from: from && rect(from), work: work && rect(work), rows, compose: compose && rect(compose),
          terminal: card.querySelector(".xterm-screen") && rect(card.querySelector(".xterm-screen")),
          scrollable: from ? getComputedStyle(from).overflowY : null, drawer: !!from?.hasAttribute("data-tq-from-side"),
          // a scroller INSIDE the work column: the Result or a finished agent's chat shrunk into one of its own (TQ-1215)
          inner: work ? [...work.querySelectorAll("*")].filter((e) => visible(e) && /auto|scroll/.test(getComputedStyle(e).overflowY)
            && e.scrollHeight > e.clientHeight + 1 && !e.closest("textarea, .xterm")).length : 0 };
      });
      const say = `${name} at ${width}x${height}: ${JSON.stringify(metrics)}`;
      assert.ok(metrics.pageOverflow <= 1, say);
      assert.ok(metrics.card.right <= width + 1 && metrics.card.x >= 0, say);
      assert.ok(metrics.card.h <= height, say);
      for (const row of metrics.rows) {
        assert.ok(row.centers.length <= 1 && row.h <= 42 && row.overflow <= 1, say);
      }
      if (metrics.compose) assert.ok(metrics.compose.h <= 48, say);
      if (name === "rest" || name === "result") assert.equal(metrics.inner, 0, `one scroller for the work: ${say}`);
      if (name === "agent") assert.ok(metrics.terminal?.h > 100 && metrics.terminal.right <= metrics.card.right, say);
      // Came from is a drawer laid over the work from the left, inside the card, scrolling on its own (the owner, 2026-10-26) - or, on a
      // phone, the stacked page's top block
      // ...or the page itself, the work shut in its right drawer (nothing drafted yet)
      if (metrics.from && metrics.work?.w) {
        if (metrics.drawer) {
          assert.ok(metrics.from.x <= metrics.work.x + 1 && metrics.scrollable === "auto", say);
          assert.ok(metrics.from.bottom <= metrics.card.bottom + 1, say);
        } else assert.ok(metrics.work.y >= metrics.from.bottom - 1, say);
      }
      if (shots) await page.screenshot({ path: `${shots}/${name}-${width}x${height}.png` });
      if (name === "messages" && metrics.scrollable === "auto") {
        const reachable = await page.evaluate(() => {
          const from = document.querySelector("[data-tq-from]");
          const work = document.querySelector("[data-tq-work]");
          const before = work.getBoundingClientRect().top;
          from.scrollTop = from.scrollHeight;
          // ...the last of it: what triage made of it on a phone, the message history's foot in the desk's Came from section
          const all = from.querySelectorAll("[data-tq-sorted], [data-tq-conversation]"), last = all[all.length - 1].getBoundingClientRect();
          const bounds = from.getBoundingClientRect();
          return last.bottom <= bounds.bottom + 1 && last.bottom > bounds.top && work.getBoundingClientRect().top === before;
        });
        assert.ok(reachable, `all source content is reachable without moving the work: ${say}`);
      }
    }
  }
  assert.deepEqual(errors, []);
});
