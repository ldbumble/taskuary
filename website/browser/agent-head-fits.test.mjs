import assert from "node:assert/strict";
import { mkdirSync } from "node:fs";
import path from "node:path";
import test from "node:test";

import { startHarness } from "./harness.mjs";

/* THE AGENT'S HEADING FITS ITS HALF (the owner, 2026-11-03, Agent beside Close out at ~1600px with the rail open: "this ui looks weird when
   split? make the model choice smaller"). The brain picker and the model field sat ON the heading's title - "Tasku… / answ…" - with Full
   screen and the state chip after them. At every split width the title reads whole or ends in an ellipsis on its one line, and no control
   overlaps it or another control; the heading stays one row. A general agent live on its chat with a draft for the owner (the pair opens on
   its own). Invented people only. TASKUARY_SHOT_DIR: where each width's frame goes. */
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const PAIRED = (sel) => document.querySelector(`${sel} [data-tq-task-body]`)?.dataset.tqPair === "agent+close";

// the heading's boxes: its title, each control in it, the chip
const measure = (sel) => {
  const head = document.querySelector(`${sel} [data-tq-agent-head]`);
  if (!head) return null;
  const box = (e) => { const r = e.getBoundingClientRect(); return { l: r.left, r: r.right, t: r.top, b: r.bottom, w: r.width, h: r.height }; };
  const title = head.querySelector("[data-tq-head-title]");
  const tools = head.querySelector("[data-tq-head-tools]");
  const ctrls = [...(tools?.children || [])].filter((e) => e.offsetParent).map((e) => ({ name: e.getAttribute("aria-label") || e.innerText.trim().slice(0, 30) || e.tagName, ...box(e) }));
  const chip = head.querySelector("[data-tq-head-chip]");
  const cs = title && getComputedStyle(title);
  return { head: box(head), title: title && { ...box(title), text: title.innerText, cut: title.scrollWidth > title.clientWidth + 1, ellipsis: cs.textOverflow === "ellipsis", lines: Math.round(title.getBoundingClientRect().height / parseFloat(cs.lineHeight || "18")) },
    tools: tools && box(tools), ctrls, chip: chip && chip.offsetParent ? { name: chip.innerText.trim(), ...box(chip) } : null };
};
const overlap = (a, b) => Math.min(a.r, b.r) - Math.max(a.l, b.l) > 1 && Math.min(a.b, b.b) - Math.max(a.t, b.t) > 1;

test("the agent heading at split widths: the title reads or ends in …, no control on it or on another, one row", { timeout: 300000 }, async (t) => {
  const harness = await startHarness();
  t.after(() => harness.close());
  const page = await harness.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  const api = (p, body) => fetch(`${harness.fixtureApi}${p}`, { method: body ? "POST" : "GET", body: body && JSON.stringify(body),
    headers: { "X-Taskuary-Token": harness.token, "Content-Type": "application/json" } });
  const { taskId } = await (await api("/api/fixture/general/canvas", {})).json();
  assert.ok(taskId);
  const made = await (await api("/api/fixture/task/agent-draft", { task_id: taskId, text: "Hi Gail - the review waits on the sign-off from finance.", agent: "assistant" })).json();
  assert.ok(made.reviewId, `the agent's draft: ${JSON.stringify(made)}`);
  // ...on the owner's brain and model, whose words are the longest the picker holds: the demo connects no AI, so the chat's read is
  // answered with the session on a CLI and its catalog
  const BRAIN = { id: "cli:claude", pick: "cli:claude", type: "cli", label: "Claude Code (on this computer)", model: "claude-opus-5-5",
    models: [{ id: "claude-opus-5-5", label: "claude-opus-5-5" }, { id: "claude-sonnet-5", label: "claude-sonnet-5" }] };
  page.off("request", page.fixtureRequestGuard);
  page.on("request", async (req) => {
    const at = new URL(req.url()).pathname;
    if (req.method() !== "GET" || at !== `/api/tasks/${taskId}/assistant`) return page.fixtureRequestGuard(req);
    const got = await (await api(at)).json();
    return req.respond({ status: 200, contentType: "application/json",
      body: JSON.stringify({ ...got, providers: [BRAIN], session: got.session && { ...got.session, pick: BRAIN.pick, provider: BRAIN.label, model: BRAIN.model } }) });
  });
  await page.setViewport({ width: 1600, height: 900, deviceScaleFactor: 1 });
  await page.goto(harness.ui, { waitUntil: "domcontentloaded", timeout: 20000 });
  await page.waitForSelector("[data-tq-rail] .tq-pile-row", { timeout: 30000 });
  await page.evaluate((id) => { location.hash = `task=${id}`; }, taskId);
  const sel = `[data-tq-task-page="${taskId}"]`;
  for (const width of [1600, 1440, 1280]) {
    await t.test(`${width}px`, async () => {
      await page.setViewport({ width, height: 900, deviceScaleFactor: 1 });
      // ...1280 with the rail open has no room for two halves (pairRoom): its one Agent pane is checked the same way
      if (width >= 1440) await page.waitForFunction(PAIRED, { timeout: 20000 }, sel).catch(async () =>
        assert.fail(`not side by side: "${await page.evaluate((s) => document.querySelector(`${s} [data-tq-task-body]`)?.dataset.tqPair || "", sel)}"`));
      else await page.waitForFunction((s) => document.querySelector(`${s} [data-tq-slot=agent][data-tq-open]`), { timeout: 20000 }, sel);
      await page.waitForFunction((s) => document.querySelector(`${s} [data-tq-agent-head] [data-tq-head-tools] .MuiSelect-select`), { timeout: 20000 }, sel);
      await sleep(900);
      assert.ok(await page.$("[data-tq-rail] .tq-pile-row"), "the rail is open");
      const dir = process.env.TASKUARY_SHOT_DIR;
      if (dir) { mkdirSync(dir, { recursive: true }); await page.screenshot({ path: path.join(dir, `agent-head-${width}.png`) }); }
      const m = await page.evaluate(measure, sel);
      const said = JSON.stringify(m);
      assert.ok(m?.title && m.ctrls.length >= 3, `the heading, its title and its brain, model and Full screen: ${said}`);
      assert.ok(m.ctrls.some((c) => /Claude Code/.test(c.name)) && m.ctrls.some((c) => /claude-opus/.test(c.name)), `the owner's brain and model: ${said}`);
      assert.equal(m.title.lines, 1, `the title is one line: ${said}`);
      assert.ok(!m.title.cut || m.title.ellipsis, `a title that does not fit ends in an ellipsis: ${said}`);
      assert.ok(m.title.w >= 60, `the title keeps room to be read: ${said}`);
      const boxes = [...m.ctrls, ...(m.chip ? [m.chip] : [])];
      for (const c of boxes) assert.ok(!overlap(m.title, c), `${c.name} overlaps the title: ${said}`);
      boxes.forEach((a, i) => boxes.slice(i + 1).forEach((b) => assert.ok(!overlap(a, b), `${a.name} overlaps ${b.name}: ${said}`)));
      // ...one row: every control sits on the title's line, inside the heading
      const mid = (x) => (x.t + x.b) / 2, row = mid(m.title);
      for (const c of boxes) assert.ok(Math.abs(mid(c) - row) <= 8 && c.r <= m.head.r + 1, `${c.name} is off the heading's one row: ${said}`);
    });
  }
  assert.deepEqual(errors, []);
});
