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
  assert.ok(chat.taskId && saved.taskId);
  const shots = process.env.TQ_LAYOUT_SCREENSHOTS;
  if (shots) await mkdir(shots, { recursive: true });

  for (const [width, height] of [[1858, 900], [1440, 900], [1366, 768], [1280, 720], [1024, 600], [768, 700], [390, 844]]) {
    await page.setViewport({ width, height, deviceScaleFactor: 1 });
    for (const [name, id] of [["email", mail.TaskId], ["messages", chat.taskId], ["result", saved.taskId], ["agent", coding.TaskId]]) {
      await page.evaluate((id) => { location.hash = `task=${id}`; }, id);
      await page.waitForSelector(`[data-tq-task-page="${id}"] [data-tq-task-head]`, { timeout: 20000 });
      if (name === "messages") {
        // The phone's compact context opens before the older messages.
        await page.evaluate(() => document.querySelector("[data-tq-from]")?.click());
        await page.waitForSelector("[data-tq-show-older]", { timeout: 10000 });
        await page.evaluate(() => document.querySelector("[data-tq-show-older]").click());
        await page.waitForSelector("[data-tq-from] [data-tq-chat-thread]");
      } else if (name === "result") {
        await page.waitForSelector("[data-tq-result]", { timeout: 20000 });
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
          scrollable: from ? getComputedStyle(from).overflowY : null };
      });
      const say = `${name} at ${width}x${height}: ${JSON.stringify(metrics)}`;
      assert.ok(metrics.pageOverflow <= 1, say);
      assert.ok(metrics.card.right <= width + 1 && metrics.card.x >= 0, say);
      assert.ok(metrics.card.h <= height, say);
      for (const row of metrics.rows) {
        assert.ok(row.centers.length <= 1 && row.h <= 42 && row.overflow <= 1, say);
      }
      if (metrics.compose) assert.ok(metrics.compose.h <= 48, say);
      if (name === "agent") assert.ok(metrics.terminal?.h > 100 && metrics.terminal.right <= metrics.card.right, say);
      if (metrics.from && metrics.work) {
        const beside = metrics.work.x >= metrics.from.right;
        assert.ok(beside || metrics.work.y >= metrics.from.bottom - 1, say);
        if (beside) {
          assert.ok(metrics.work.w > metrics.from.w && metrics.scrollable === "auto", say);
          assert.ok(metrics.from.bottom <= metrics.card.bottom + 1, say);
        }
      }
      if (shots) await page.screenshot({ path: `${shots}/${name}-${width}.png` });
      if (name === "messages" && metrics.scrollable === "auto") {
        const reachable = await page.evaluate(() => {
          const from = document.querySelector("[data-tq-from]");
          const work = document.querySelector("[data-tq-work]");
          const before = work.getBoundingClientRect().top;
          from.scrollTop = from.scrollHeight;
          const last = from.querySelector("[data-tq-sorted]").getBoundingClientRect();
          const bounds = from.getBoundingClientRect();
          return last.bottom <= bounds.bottom + 1 && last.top >= bounds.top && work.getBoundingClientRect().top === before;
        });
        assert.ok(reachable, `all source content is reachable without moving the work: ${say}`);
      }
    }
  }
  assert.deepEqual(errors, []);
});
