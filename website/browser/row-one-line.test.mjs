import assert from "node:assert/strict";
import test from "node:test";

import { startHarness } from "./harness.mjs";

/* THE ROW IS ONE LINE (the owner, 2026-10-23: "even on my desktop i saw a time where the buttons turned into 2 rows ... it was when
   after closing agent and it was drafting a whatsapp response it showed 2 rows of buttons. NEVER do that"). Every row state the demo
   and the fixtures reach - the walk's first items, a stopped and saved agent, one still writing up, a closed task, a WhatsApp burst,
   and the owner's own case (a WhatsApp task whose agent was stopped, its reply drafting) - at 1440, 1024 and 390 wide: each drawn row
   is one line of buttons as tall as one button, nothing runs past its edge or the page's, no label breaks inside its pill, and Next and
   the lit move are still there. A task view's own bar ([data-tq-task-bar]), wherever one is drawn, is held to the same. */
const WIDTHS = [1440, 1024, 390];
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// what the drawn rows look like now: every visible [data-tq-row]'s line of buttons, and the Tasks tab's bar
const look = (page) => page.evaluate(() => {
  const seen = (e) => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0 && getComputedStyle(e).visibility !== "hidden"; };
  const rows = [...document.querySelectorAll("[data-tq-row] .tq-arow-verbs"), ...document.querySelectorAll("[data-tq-task-bar]")].filter(seen);
  return { page: { scroll: document.documentElement.scrollWidth, width: window.innerWidth }, rows: rows.map((box) => {
    const kids = [...box.querySelectorAll("button, .tq-ab.slot")].filter(seen);
    const r = box.getBoundingClientRect(), tall = Math.max(0, ...[...box.children].filter(seen).map((k) => k.getBoundingClientRect().height));
    return { bar: box.hasAttribute("data-tq-task-bar"), height: Math.round(r.height), tall: Math.round(tall), over: box.scrollWidth - box.clientWidth,
      tops: [...new Set([...box.children].filter(seen).map((k) => Math.round(k.getBoundingClientRect().top + k.getBoundingClientRect().height / 2)))],
      left: Math.round(Math.min(...kids.map((k) => k.getBoundingClientRect().left)) - r.left), right: Math.round(r.right - Math.max(...kids.map((k) => k.getBoundingClientRect().right))),
      // a label broken onto two lines is a pill taller than its line
      broken: kids.filter((k) => k.getBoundingClientRect().height > 50).map((k) => k.textContent),
      next: !!box.querySelector("[data-tq-next]"), lit: [...box.querySelectorAll("button.tq-ab.p")].map((k) => k.textContent),
      labels: kids.map((k) => k.textContent.trim()).filter(Boolean), fold: box.getAttribute("data-tq-fold") };
  }) };
});

const check = async (page, what) => {
  const at = {};
  for (const w of WIDTHS) {
    await page.setViewport({ width: w, height: w > 600 ? 1000 : 844, deviceScaleFactor: 1 });
    await page.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r))));
    await sleep(350);
    const now = await look(page);
    at[w] = now;
    const say = (why) => `${what} @${w}: ${why}\n${JSON.stringify(now.rows)}`;
    assert.ok(now.page.scroll <= now.page.width + 1, say(`the page scrolls sideways (${now.page.scroll} > ${now.page.width})`));
    for (const r of now.rows) {
      assert.ok(r.tops.length <= 1, say("the buttons sit on more than one line"));
      assert.ok(r.height <= r.tall + 2, say(`the row is ${r.height}px for a ${r.tall}px line`));
      assert.ok(r.over <= 1, say(`the row runs ${r.over}px past its edge`));
      assert.ok(r.left >= -1 && r.right >= -1, say("a button sticks out of the row"));
      assert.deepEqual(r.broken, [], say("a label broke onto two lines"));
    }
  }
  // ...and what the widest row had in view - Next, its lit move - is in view at every width
  const wide = at[WIDTHS[0]].rows.filter((r) => !r.bar);
  for (const w of WIDTHS.slice(1)) {
    const rows = at[w].rows.filter((r) => !r.bar);
    if (wide.some((r) => r.next)) assert.ok(rows.some((r) => r.next), `${what} @${w}: Next is gone`);
    for (const lit of wide.flatMap((r) => r.lit)) assert.ok(rows.some((r) => r.lit.includes(lit)), `${what} @${w}: the lit "${lit}" folded away`);
  }
  await page.setViewport({ width: 1440, height: 1000, deviceScaleFactor: 1 });
  if (process.env.TQ_ROW_DEBUG) console.log(what, JSON.stringify(Object.fromEntries(WIDTHS.map((w) => [w, at[w].rows.map((r) => `${r.bar ? "bar" : `fold ${r.fold}`}: ${r.labels.join(" | ")}`)]))));
  return at;
};

test("the action row is one line in every state the demo reaches, at 1440, 1024 and 390", { timeout: 600000 }, async (t) => {
  const harness = await startHarness();
  t.after(() => harness.close());
  const page = await harness.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  // a draft asked for is held - "Drafting…" stays on the row as long as the test looks (the owner's case)
  page.off("request", page.fixtureRequestGuard);
  page.on("request", (req) => {
    if (req.method() === "POST" && /\/api\/reviews\/\d+\/draft$/.test(new URL(req.url()).pathname)) return;   // never answered
    return page.fixtureRequestGuard(req);
  });
  await page.goto(harness.ui, { waitUntil: "domcontentloaded", timeout: 20000 });
  await page.waitForSelector("[data-tq-rail] .tq-pile-row", { timeout: 30000 });
  const fixture = (path, body = {}) => page.evaluate(async (p, b) => {
    const headers = { "X-Taskuary-Token": localStorage.getItem("taskuary_token"), "Content-Type": "application/json" };
    const r = await fetch(p, { method: "POST", headers, body: JSON.stringify(b) });
    return r.json();
  }, path, body);
  const rowUp = () => page.waitForFunction(() => [...document.querySelectorAll("[data-tq-row] [data-tq-next], [data-tq-row] button")]
    .some((b) => b.getBoundingClientRect().width > 0), { timeout: 30000 });
  const onTable = async (id) => {
    await page.evaluate((i) => { window.location.hash = `task=${i}`; }, id);
    await page.waitForFunction((i) => document.querySelector(`[data-tq-canvas-item*="${i}"]`) || document.body.innerText.includes(`TQ-${String(i).padStart(4, "0")}`), { timeout: 30000 }, id);
    await rowUp(); await sleep(800);
  };
  const states = [];

  // THE WALK: the rail's first row, then Next, as the owner walks it - whatever rows the demo's items draw
  const first = await page.$eval("[data-tq-rail] .tq-pile-row[data-tq-key]", (e) => e.getAttribute("data-tq-key"));
  await page.evaluate((k) => document.querySelector(`[data-tq-rail] .tq-pile-row[data-tq-key="${k}"] .card`).click(), first);
  await rowUp(); await sleep(800);
  for (let i = 0; i < 5; i++) {
    const key = await page.evaluate(() => document.querySelector(".tq-pile-row.current")?.getAttribute("data-tq-key") || `walk-${Date.now()}`);
    states.push(key); await check(page, `walk item ${i + 1} (${key})`);
    const moved = await page.evaluate(() => {
      const b = [...document.querySelectorAll("[data-tq-next]")].find((n) => !n.disabled && n.getBoundingClientRect().width > 0);
      if (!b) return false; b.click(); return true;
    });
    if (!moved) break;
    await page.waitForFunction((k) => (document.querySelector(".tq-pile-row.current")?.getAttribute("data-tq-key") || "") !== k, { timeout: 20000 }, key).catch(() => {});
    await rowUp(); await sleep(800);
  }

  // THE FIXTURES: an agent stopped and saved, one still writing its result, a closed task, a WhatsApp burst
  for (const [what, path, body] of [["agent stopped and saved", "/api/fixture/task/coding-saved", {}], ["agent writing up", "/api/fixture/task/coding-saved", { writing: true }],
    ["WhatsApp burst", "/api/fixture/task/chat-burst", {}]]) {
    const made = await fixture(path, body);
    assert.ok(made.taskId, `${what}: ${JSON.stringify(made)}`);
    await onTable(made.taskId); states.push(what); await check(page, what);
  }

  // THE OWNER'S CASE: the agent stopped and saved on a WhatsApp ask, and its reply drafting - Reply pressed, the draft held
  const saved = await fixture("/api/fixture/task/chat-saved");
  assert.ok(saved.taskId, JSON.stringify(saved));
  await onTable(saved.taskId);
  await check(page, "WhatsApp agent stopped and saved");
  const pressed = await page.evaluate(() => {
    const b = document.querySelector('[data-tq-row] [data-tq-verb="reply"]');
    if (b) { b.click(); return "row"; }
    const m = document.querySelector('[data-tq-row] [data-tq-more]');
    return m ? "menu" : "";
  });
  if (pressed === "menu") {
    await page.evaluate(() => document.querySelector("[data-tq-row] [data-tq-more]").click());
    await page.waitForSelector('[role="menu"] [data-tq-verb="reply"]', { timeout: 10000 });
    await page.evaluate(() => document.querySelector('[role="menu"] [data-tq-verb="reply"]').click());
  } else assert.equal(pressed, "row", "the WhatsApp task offers Reply");
  await page.waitForFunction(() => document.body.innerText.includes("Drafting…"), { timeout: 20000 });
  await sleep(600);
  const owner = await check(page, "WhatsApp agent stopped, its reply drafting (the owner's case)");
  states.push("owner's case");
  assert.ok(owner[1440].rows.some((r) => !r.bar && r.labels.length >= 3), `the owner's row carries its verbs: ${JSON.stringify(owner[1440].rows)}`);

  // A CLOSED TASK: Reopen and Next
  const closed = await fixture("/api/fixture/task/agent-closed", { answer: "Re-added the missing secret; the re-run passed.", said: "the re-run passed" });
  assert.ok(closed.taskId, JSON.stringify(closed));
  await onTable(closed.taskId); states.push("closed"); await check(page, "closed by its agent");

  assert.ok(states.length >= 7, `states walked: ${states.join(", ")}`);
  assert.deepEqual(errors, []);
});
