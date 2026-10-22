import assert from "node:assert/strict";
import test from "node:test";

import { startHarness } from "./harness.mjs";

/* THE LATEST CLICK WINS (the owner, 0.3.9.21: "I clicked on task 1171 and it jumped back to the deep dive one, then right back to 1171").
   With task A open, a rail click on task B must go straight to B and never show A again - not when A's own reads are slow, and not when
   a read of the conversation sent while B's pull was in flight answers after it with A still the server's Current.
   That last one was the owner's: a turn on a real brain takes seconds, a live event mid-turn reads the conversation (B's first read
   files its origin, and task-changed names the task on the table), the server still says A, and that answer landed after B's - A
   went back up, and the rail read that follows B's landing put B back. */

const SAMPLE_MS = 3000;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
// every task the canvas shows, in order, as it changes - the view's own id and the ref in its header
const watch = (page) => page.evaluate(() => {
  const seen = window.__tqSeen = [];
  const now = () => [...document.querySelectorAll("[data-tq-task-page]")].filter((e) => e.getBoundingClientRect().height > 0 && e.querySelector("[data-tq-task-head]"))
    .map((e) => e.getAttribute("data-tq-task-page")).join(",");
  const note = () => { const v = now(); if (seen[seen.length - 1] !== v) seen.push(v); };
  note();
  const mo = new MutationObserver(note);
  mo.observe(document.body, { subtree: true, childList: true, attributes: true, characterData: true, attributeFilter: ["data-tq-task-page", "style", "class"] });
  window.__tqStop = () => { mo.disconnect(); note(); return seen; };
});
const rows = (page) => page.$$eval("[data-tq-rail] .tq-pile-row", (els) => els.filter((r) => r.closest("[data-tq-run]")?.getAttribute("data-tq-run") === "task")
  .map((r) => r.getAttribute("data-tq-key")).filter(Boolean));
const clickRow = (page, key) => page.evaluate((k) => document.querySelector(`[data-tq-rail] .tq-pile-row[data-tq-key="${k}"] .card`).click(), key);
const shown = (page) => page.evaluate(() => [...document.querySelectorAll("[data-tq-task-page]")].filter((e) => e.getBoundingClientRect().height > 0 && e.querySelector("[data-tq-task-head]"))
  .map((e) => e.getAttribute("data-tq-task-page")));
// the row clicked is the one on the table, and one task view is up
const settled = (page, key) => page.waitForFunction((k) => document.querySelector(".tq-pile-row.current")?.getAttribute("data-tq-key") === k
  && [...document.querySelectorAll("[data-tq-task-page]")].filter((e) => e.getBoundingClientRect().height > 0 && e.querySelector("[data-tq-task-head]")).length === 1,
  { timeout: 20000 }, key);

// a run of distinct shown ids: B straight after A, never A again
const assertStraight = (seen, a, b) => {
  const ids = seen.map((s) => s.split(",").filter(Boolean)).filter((x) => x.length).map((x) => x.join(","));
  const firstB = ids.findIndex((x) => x === b);
  assert.ok(firstB >= 0, `B (${b}) was shown: ${JSON.stringify(seen)}`);
  assert.ok(!ids.slice(firstB).some((x) => x.split(",").includes(a)), `A (${a}) came back after B was shown: ${JSON.stringify(seen)}`);
  assert.equal(ids[ids.length - 1], b, `B is what stays: ${JSON.stringify(seen)}`);
};

test("a rail click on task B while task A is open goes straight to B and stays", { timeout: 360000 }, async (t) => {
  const harness = await startHarness();
  t.after(() => harness.close());
  const page = await harness.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  // the harness's own guard, wrapped: a request the test slows is held, then handed to it as before - or, with `answer`, it goes to the
  // server NOW and its answer is handed back `ms` later: a read taken before a write, landing after it
  const slow = [];          // [{ test(url, method), ms, answer }]
  page.off("request", page.fixtureRequestGuard);
  page.on("request", (req) => {
    const rule = slow.find((s) => s.test(req.url(), req.method()));
    if (!rule) return page.fixtureRequestGuard(req);
    if (!rule.answer) return void setTimeout(() => page.fixtureRequestGuard(req), rule.ms);
    const u = new URL(req.url()), at = Date.now();
    fetch(`${harness.fixtureApi}${u.pathname}${u.search}`, { headers: { "X-Taskuary-Token": harness.token } })
      .then(async (r) => ({ status: r.status, body: await r.text() }))
      .then(({ status, body }) => setTimeout(() => req.respond({ status, contentType: "application/json", body }).catch(() => {}), Math.max(0, rule.ms - (Date.now() - at))))
      .catch(() => req.abort("failed").catch(() => {}));
  });
  // the live socket, held so the test can hand the page an event the server would have sent
  await page.evaluateOnNewDocument(() => {
    const W = window.WebSocket;
    window.WebSocket = class extends W { constructor(...a) { super(...a); if (String(a[0]).includes("/api/events/ws")) window.__tqLive = this; } };
  });
  const liveEvent = (ev) => page.evaluate((e) => window.__tqLive?.dispatchEvent(new MessageEvent("message", { data: JSON.stringify(e) })), ev);
  await page.goto(harness.ui, { waitUntil: "domcontentloaded", timeout: 20000 });
  await page.waitForSelector("[data-tq-rail] .tq-pile-row", { timeout: 30000 });
  const keys = await rows(page);
  assert.ok(keys.length >= 4, `the demo rail has tasks to pick: ${keys}`);

  const round = async (ka, kb, delays = () => [], during = null) => {
    await clickRow(page, ka);
    await settled(page, ka);
    const [a] = await shown(page);
    await sleep(800);                                   // A's view, its reads and the rail behind it settle
    slow.splice(0, slow.length, ...delays(a));
    await watch(page);
    // kb: a rail row's key, or a task id opened as a link - the road the Assistant's own Open takes (openAppLink)
    const to = typeof kb === "function" ? kb(a) : kb;
    if (typeof to === "number") await page.evaluate((id) => { window.location.hash = `task=${id}`; }, to); else await clickRow(page, to);
    await during?.();
    await sleep(SAMPLE_MS);
    const seen = await page.evaluate(() => window.__tqStop());
    slow.length = 0;
    const [b] = await shown(page);
    assert.ok(b && b !== a, `a task other than A is shown after the click: ${JSON.stringify(seen)}`);
    assertStraight(seen, a, b);
    return { a, b, seen };
  };

  await t.test("plain: A, then a click on B", async () => {
    await round(keys[0], keys[1]);
  });

  await t.test("A's reads answer late: the click on B still wins", async () => {
    await round(keys[2], keys[3], (a) => [{ test: (u) => new RegExp(`/api/tasks/${a}(?:[/?]|$)`).test(new URL(u).pathname + "/"), ms: 1500 }]);
  });

  await t.test("a read of the conversation sent during B's pull answers after it: the table stays on B", async () => {
    // B's pull takes a while to reach the server (a turn on a real brain takes seconds); a chat event mid-turn reads the conversation
    // while the server still says A, and that answer is handed back only after B's pull has landed
    await round(keys[1], keys[2], () => [
      { test: (u, m) => m === "POST" && /\/api\/concierge\/(?:stream|next)$/.test(new URL(u).pathname), ms: 1200 },
      { test: (u, m) => m === "GET" && new URL(u).pathname === "/api/concierge", ms: 2200, answer: true },
    ], async () => { await sleep(150); await liveEvent({ type: "chat-changed" }); });
  });

  await t.test("the Assistant's own Open (a task link) is a click too: the same late read does not take it back", async () => {
    const tasks = (await (await fetch(`${harness.fixtureApi}/api/tasks`, { headers: { "X-Taskuary-Token": harness.token } })).json()).data || [];
    const open = tasks.filter((x) => !["done", "dropped"].includes(x.Status)).map((x) => x.TaskId);
    const { b } = await round(keys[3], (a) => open.find((id) => String(id) !== a), () => [
      { test: (u, m) => m === "POST" && /\/api\/concierge\/(?:stream|next)$/.test(new URL(u).pathname), ms: 1200 },
      { test: (u, m) => m === "GET" && new URL(u).pathname === "/api/concierge", ms: 2200, answer: true },
    ], async () => { await sleep(150); await liveEvent({ type: "chat-changed" }); });
    assert.equal(await page.evaluate(() => window.location.hash), `#task=${b}`, "the address says the task on the table");
  });

  assert.deepEqual(errors, []);
});
