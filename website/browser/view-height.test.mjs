import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { chmod, mkdtemp, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { startHarness } from "./harness.mjs";

/* A TASK OF WORDS HOLDS ONE HEIGHT (the owner, 2026-10-27, a task opened big that shrank to half its height when Reply was pressed, a
   screen of empty canvas under it: "if an agent is not open it should be pinned to the top of the view - the beginning of the task window -
   then take up at least half or a little more, and not change if I click Reply or anything else, unless I start an agent"). The card
   (CanvasItem useHeldHeight) stays at the canvas's top and at one height - at least 55% of the canvas - through Reply, each drawer out and
   back, a section opened by hand, a draft typed into and the chat's pop-up; a started agent takes the room. Invented people only. */
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const FLOOR = 0.55;   // CanvasItem WORDS_FLOOR

const measure = (page) => page.evaluate(() => {
  const r = (s) => { const e = document.querySelector(s); if (!e) return null; const b = e.getBoundingClientRect(); return { top: b.top, h: b.height }; };
  return { card: r("[data-tq-canvas-item]"), canvas: r(".tq-chat-body"), main: document.querySelector("[data-tq-task-body]")?.getAttribute("data-tq-main") };
});
const pinned = (base, m, say) => {
  assert.ok(Math.abs(m.card.top - base.card.top) <= 2, `the card's top moved ${say}: ${base.card.top} -> ${m.card.top}`);
  assert.ok(Math.abs(m.card.h - base.card.h) <= 2, `the card's height moved ${say}: ${base.card.h} -> ${m.card.h}`);
};
const rowPress = (page, label) => page.evaluate((label) => {
  const b = [...document.querySelectorAll("[data-tq-row] button")].find((x) => x.textContent.trim() === label && !x.disabled);
  b?.click(); return !!b;
}, label);

test("a task of words stays at the canvas's top and one height through Reply, the drawers, a section, a draft and the pop-up",
  { timeout: 300000 }, async (t) => {
  const harness = await startHarness();
  t.after(() => harness.close());
  const page = await harness.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  const tasks = (await (await fetch(`${harness.fixtureApi}/api/tasks`, { headers: { "X-Taskuary-Token": harness.token } })).json()).data;
  const ids = tasks.filter((x) => /^(Month-end close is short|New starter on Monday)/.test(x.Title) && x.Status === "open").map((x) => x.TaskId);
  assert.equal(ids.length, 2, JSON.stringify(tasks.map((x) => x.Title)));
  for (const [[width, height], id] of [[[1600, 810], ids[0]], [[1366, 768], ids[1]]]) {
    const say = `at ${width}x${height}`;
    await page.setViewport({ width, height, deviceScaleFactor: 1 });
    if (page.url() === "about:blank") {
      await page.goto(harness.ui, { waitUntil: "domcontentloaded", timeout: 20000 });
      await page.waitForSelector("[data-tq-rail] .tq-pile-row", { timeout: 30000 });
    }
    await page.evaluate((id) => { location.hash = ""; location.hash = `task=${id}`; }, id);
    await page.waitForSelector(`[data-tq-canvas-item] [data-tq-task-page="${id}"] [data-tq-task-body]`, { timeout: 20000 });
    await sleep(2500);
    const base = await measure(page);
    assert.equal(base.main, "task", `the task opens on its task view ${say}`);
    assert.ok(Math.abs(base.card.top - base.canvas.top) <= 2, `the card is pinned to the canvas's top ${say} ${JSON.stringify(base)}`);
    assert.ok(base.card.h >= FLOOR * base.canvas.h - 1, `the card takes at least ${FLOOR} of the canvas ${say} ${JSON.stringify(base)}`);
    const drawers = async (when) => {
      for (const tab of ["[data-tq-from-line]", "[data-tq-work-tab]"]) {
        if (!(await page.$(`[data-tq-canvas-item] ${tab}`))) continue;
        await page.click(`[data-tq-canvas-item] ${tab}`); await sleep(500);
        pinned(base, await measure(page), `with ${tab} out ${when} ${say}`);
        await page.click(`[data-tq-canvas-item] ${tab}`); await sleep(400);
        pinned(base, await measure(page), `with ${tab} back ${when} ${say}`);
      }
    };
    await drawers("before Reply");

    // REPLY: the view goes from the task to its draft - and the card stays as it was
    assert.ok(await rowPress(page, "Reply"), `Reply on the row ${say}`);
    await page.waitForSelector("[data-tq-canvas-item] textarea[data-tq-draft]", { timeout: 20000 });
    await sleep(1500);
    const replied = await measure(page);
    pinned(base, replied, `after Reply (${replied.main}) ${say}`);
    await drawers("after Reply");

    // A SECTION OPENED BY HAND, and back
    for (let i = 0; i < 2; i++) {
      const opened = await page.evaluate(() => { const h = document.querySelector("[data-tq-canvas-item] [data-tq-task-body] [role=button][aria-expanded=false]"); h?.click(); return !!h; });
      if (!opened) break;
      await sleep(600);
      pinned(base, await measure(page), `with a folded section opened ${say}`);
    }

    // A DRAFT TYPED INTO, a long one
    const draft = await page.$("[data-tq-canvas-item] textarea[data-tq-draft]");
    if (draft) {
      await draft.click();
      await page.keyboard.type(" Gail Moreno has the signed copy; Ray Colton picks it up on Thursday.\n\nOne more line.\n\nAnd another.\n\nAnd a last one.");
      await sleep(500);
      pinned(base, await measure(page), `with the draft typed into ${say}`);
    }

    // THE CHAT'S POP-UP over it
    await page.click(".tq-compose-box textarea");
    await page.keyboard.type("what does this one need from me?");
    await page.keyboard.press("Enter");
    await page.waitForSelector("[data-tq-chat-pop]:not([hidden])", { timeout: 20000 });
    await page.waitForFunction(() => !document.querySelector("[data-tq-chat-pop] .tq-pending"), { timeout: 30000 });
    await sleep(400);
    pinned(base, await measure(page), `with the chat's pop-up up ${say}`);
    await page.keyboard.press("Escape"); await page.keyboard.press("Escape"); await sleep(400);
    pinned(base, await measure(page), `with the pop-up gone ${say}`);
  }
  assert.deepEqual(errors, []);
});

// THE DRAWER TABS ARE WHITE, both edges (the owner, 2026-10-27: "the right side thing should be white as well, like the left sidebar -
// otherwise you won't notice it's there"); lit, the right one wears the accent over it
test("both drawer tabs are white at rest", { timeout: 180000 }, async (t) => {
  const harness = await startHarness();
  t.after(() => harness.close());
  const page = await harness.newPage();
  await page.setViewport({ width: 1600, height: 810, deviceScaleFactor: 1 });
  await page.goto(harness.ui, { waitUntil: "domcontentloaded", timeout: 20000 });
  await page.waitForSelector("[data-tq-rail] .tq-pile-row", { timeout: 30000 });
  const tasks = (await (await fetch(`${harness.fixtureApi}/api/tasks`, { headers: { "X-Taskuary-Token": harness.token } })).json()).data;
  const bg = async (id, tab) => {
    await page.evaluate((id) => { location.hash = ""; location.hash = `task=${id}`; }, id);
    await page.waitForSelector(`[data-tq-task-page="${id}"] [data-tq-task-body]`, { timeout: 20000 });
    await sleep(1500);
    return page.evaluate((tab) => { const e = document.querySelector(`[data-tq-canvas-item] ${tab}`); return e && { bg: getComputedStyle(e).backgroundColor, lit: e.hasAttribute("data-tq-lit") }; }, tab);
  };
  // a fresh task opens on its task view, Agent · Close out on the right; a drafted reply's opens on its work, Came from on the left
  const right = await bg(tasks.find((x) => /^New starter on Monday/.test(x.Title)).TaskId, "[data-tq-work-tab]");
  const left = await bg(tasks.find((x) => /^Invoice 88213/.test(x.Title)).TaskId, "[data-tq-from-line]");
  assert.ok(right && left, JSON.stringify({ right, left }));
  assert.equal(left.bg, "rgb(255, 255, 255)", "Came from's tab is white");
  if (!right.lit) assert.equal(right.bg, left.bg, "Agent · Close out's tab is as white as Came from's");
  else assert.equal(right.bg, "rgb(85, 105, 122)", "lit, it wears the accent");
});

// ...AND A STARTED AGENT TAKES THE ROOM: a stand-in claude (tests/fake_claude.py) on a fresh home, as browser/agent-journey.test.mjs
const here = path.dirname(fileURLToPath(import.meta.url)), repo = path.resolve(here, "..", "..");
test("a card of words is held until an agent starts; the live agent takes the canvas", { timeout: 240000 }, async (t) => {
  const bin = await mkdtemp(path.join(os.tmpdir(), "taskuary-fake-claude-"));
  t.after(() => rm(bin, { recursive: true, force: true }).catch(() => {}));
  const win = process.platform === "win32";
  const py = execFileSync(win ? "python" : "python3", ["-c", "import sys; print(sys.executable)"], { encoding: "utf8" }).trim();
  const fake = path.join(repo, "tests", "fake_claude.py");
  await writeFile(path.join(bin, win ? "claude.cmd" : "claude"), win ? `@${py} ${fake} %*\r\n` : `#!/bin/sh\nexec "${py}" "${fake}" "$@"\n`);
  if (!win) await chmod(path.join(bin, "claude"), 0o755);
  await writeFile(path.join(bin, "script.json"), JSON.stringify([{ when: ".", first: "Compared three vendors: Payworth is cheapest at 4 a head." }]));
  Object.assign(process.env, { FAKE_CLAUDE_SCRIPT: path.join(bin, "script.json"), FAKE_CLAUDE_SPAWN: "0.5", FAKE_CLAUDE_THINK: "0.3" });
  const h = await startHarness({ fresh: true, bin });
  t.after(() => h.close());
  const api = (p, body) => fetch(`${h.fixtureApi}${p}`, { method: body ? "POST" : "GET",
    headers: { "Content-Type": "application/json", "X-Taskuary-Token": h.token }, body: body && JSON.stringify(body) }).then((r) => r.json());
  await api("/api/setup/first-run/ai", { name: "claude" });
  await api("/api/setup/dismiss", { dismissed: true });
  const page = await h.newPage();
  await page.setViewport({ width: 1600, height: 810, deviceScaleFactor: 1 });
  await page.goto(h.ui, { waitUntil: "domcontentloaded" });
  const made = await api("/api/tasks", { Title: "Compare payroll vendors", Summary: "Compare three payroll vendors on price for Northwind", Kind: "general" });
  await page.evaluate((id) => { location.hash = `task=${id}`; }, made.taskId);
  await page.waitForSelector(`[data-tq-canvas-item] [data-tq-task-page="${made.taskId}"] [data-tq-task-body]`, { timeout: 30000 });
  await sleep(2500);
  const base = await measure(page);
  assert.ok(Math.abs(base.card.top - base.canvas.top) <= 2 && base.card.h >= FLOOR * base.canvas.h - 1, JSON.stringify(base));
  await page.waitForFunction(() => [...document.querySelectorAll("button")].some((b) => b.textContent.trim() === "Send to agent" && b.offsetParent), { timeout: 30000 });
  await page.evaluate(() => [...document.querySelectorAll("button")].find((b) => b.textContent.trim() === "Send to agent" && b.offsetParent).click());
  await page.waitForSelector("[data-tq-run-form] textarea", { timeout: 15000 });
  await sleep(500);
  pinned(base, await measure(page), "with the agent's box open, nothing started yet");
  await page.evaluate(() => [...document.querySelectorAll("[data-tq-run-form] button")].find((b) => b.textContent.trim() === "Send to agent" && !b.disabled).click());
  await page.waitForSelector("[data-tq-canvas-item] [data-tq-agent-room='live']", { timeout: 30000 });
  await sleep(1500);
  const live = await measure(page);
  assert.ok(Math.abs(live.card.top - base.card.top) <= 2, `the top stays ${JSON.stringify({ base, live })}`);
  assert.ok(live.card.h >= base.card.h && live.card.h >= 0.9 * live.canvas.h, `the live agent takes the canvas ${JSON.stringify({ base, live })}`);
});
