import assert from "node:assert/strict";
import test from "node:test";

import { startHarness } from "./harness.mjs";

/* NEXT NEVER ASKS FOR A SECOND PRESS (the owner, 2026-10-26: Next said "The list moved while that was loading - press it again" - "i hate
   the next list changed. No one cares. Think about it from user perspective"). A list moving under a press is the page's to absorb:
   - a rail re-read that clears the table under the press (its task closed somewhere else while Next waited on that read): the press
     captured for a scope that no longer stood, stopped, and asked for another;
   - the server's 409 when the row the ring named left the rail before the press reached it: "The list changed while you pressed Next".
   Either way one press must reach the server, walk on, and say nothing. */

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const ASKED_AGAIN = /list moved while that was loading|list changed while you pressed|press it again|press Next again|still refreshing/i;
const rail = (page) => page.$$eval("[data-tq-rail] .tq-pile-row", (els) => els
  .map((r) => ({ key: r.getAttribute("data-tq-key"), level: r.closest("[data-tq-run]")?.getAttribute("data-tq-run") })).filter((r) => r.key));
const ring = (page) => page.evaluate(() => document.querySelector(".tq-pile-row.current")?.getAttribute("data-tq-key") || null);
const ringOn = (page, k) => page.waitForFunction((x) => document.querySelector(".tq-pile-row.current")?.getAttribute("data-tq-key") === x, { timeout: 20000 }, k);
const nextEnabled = (page) => page.waitForFunction(() => [...document.querySelectorAll("button")].some((n) => n.textContent.trim() === "Next" && !n.disabled), { timeout: 30000 });
const clickNext = (page) => page.evaluate(() => [...document.querySelectorAll("button")].find((n) => n.textContent.trim() === "Next" && !n.disabled).click());
const clickRow = (page, k) => page.evaluate((x) => document.querySelector(`[data-tq-rail] .tq-pile-row[data-tq-key="${x}"] .card`).click(), k);
const closeElsewhere = (page, tid) => page.evaluate(async (t) => {
  const headers = { "X-Taskuary-Token": localStorage.getItem("taskuary_token"), "Content-Type": "application/json" };
  const r = await fetch("/api/fixture/task/closed-elsewhere", { method: "POST", headers, body: JSON.stringify({ task_id: t }) });
  return { status: r.status, body: await r.json() };
}, tid);

// the demo with the rail's reads held on demand and every navigation (and its answer's status) recorded
const open = async (t) => {
  const harness = await startHarness();
  t.after(() => harness.close());
  const page = await harness.newPage();
  const s = { page, errors: [], held: [], streams: [], hold: false };
  page.on("pageerror", (e) => s.errors.push(e.message));
  page.off("request", page.fixtureRequestGuard);
  page.on("request", (req) => {
    const u = new URL(req.url());
    if (s.hold && req.method() === "GET" && u.pathname === "/api/funnel/pile") { s.held.push(req); return; }
    page.fixtureRequestGuard(req);
  });
  page.on("response", (res) => {
    const u = new URL(res.url());
    if (res.request().method() === "POST" && u.pathname === "/api/concierge/stream") s.streams.push(res.status());
  });
  await page.goto(harness.ui, { waitUntil: "domcontentloaded", timeout: 20000 });
  await page.waitForSelector("[data-tq-rail] .tq-pile-row", { timeout: 30000 });
  const rows = await rail(page);
  s.tasks = rows.filter((r) => r.level === "task").map((r) => r.key);
  assert.ok(s.tasks.length >= 3, `the demo rail has three tasks: ${JSON.stringify(rows)}`);
  s.tids = await page.evaluate(async (keys) => {
    const d = await (await fetch("/api/funnel/pile", { headers: { "X-Taskuary-Token": localStorage.getItem("taskuary_token") } })).json();
    return keys.map((k) => d.items.find((i) => i.key === k)?.tid);
  }, s.tasks);
  assert.ok(s.tids.slice(0, 3).every(Number.isInteger), `the task rows name their tasks: ${s.tids}`);
  return s;
};
const saidNothing = async (s) => {
  const body = await s.page.evaluate(() => document.body.innerText);
  assert.ok(!ASKED_AGAIN.test(body), `the owner was asked to press again: ${body.slice(-600)}`);
  assert.deepEqual(s.errors, []);
};

test("Next pressed while the rail read clears the table under it walks on in one press", { timeout: 300000 }, async (t) => {
  const s = await open(t), { page } = s, [first, below] = s.tasks;
  // the rail's reads are held from here: the click's own re-read is the one Next will wait on
  s.hold = true;
  await clickRow(page, first);
  await ringOn(page, first);
  await nextEnabled(page);
  for (let i = 0; i < 50 && !s.held.length; i += 1) await sleep(100);
  assert.ok(s.held.length >= 1, "the click asked the rail again");
  // ...the task closes somewhere else (the phone, the Tasks page): it leaves the rail
  const closed = await closeElsewhere(page, s.tids[0]);
  assert.equal(closed.status, 200, JSON.stringify(closed));
  const pressedAt = s.streams.length;
  await clickNext(page);
  await sleep(800);
  assert.equal(s.streams.length, pressedAt, "the press waits on the rail read before it is sent");
  // the held read lands saying the table's item is gone, as the server does for an item that left (funnel.next_item -> null)
  s.hold = false;
  for (const req of s.held.splice(0)) {
    if (new URL(req.url()).searchParams.get("current") !== first) { page.fixtureRequestGuard(req); continue; }
    const headers = Object.fromEntries(Object.entries(req.headers()).filter(([k]) => /^x-taskuary-token$|^accept$/i.test(k)));
    const data = await (await fetch(req.url(), { headers })).json();
    await req.respond({ status: 200, contentType: "application/json", body: JSON.stringify({ ...data, current: null }) });
  }
  await ringOn(page, below).catch(() => {});
  await sleep(1500);
  assert.deepEqual(s.streams.slice(pressedAt), [200], "one press, one navigation");
  assert.equal(await ring(page), below, "Next walked on to the row below the task that closed");
  await saidNothing(s);
});

test("Next whose named row left the rail before the press reached the server takes the fresh pick, silently", { timeout: 300000 }, async (t) => {
  const s = await open(t), { page } = s, [first, below, after] = s.tasks;
  await clickRow(page, first);
  await ringOn(page, first);
  await nextEnabled(page);
  await sleep(2500);                                   // the capture for the table settles: it names the row below
  // the row below closes somewhere else, and the rail's reads are held so the page still names it: the server refuses the press (409)
  s.hold = true;
  const closed = await closeElsewhere(page, s.tids[1]);
  assert.equal(closed.status, 200, JSON.stringify(closed));
  await sleep(500);
  const pressedAt = s.streams.length;
  await clickNext(page);
  await ringOn(page, after).catch(() => {});
  await sleep(1500);
  s.hold = false;
  for (const req of s.held.splice(0)) page.fixtureRequestGuard(req);
  await sleep(2000);
  assert.deepEqual(s.streams.slice(pressedAt), [409, 200], "refused once, taken again at once with the fresh pick - one move");
  assert.equal(await ring(page), after, `Next walked on past the row that left (${below})`);
  await saidNothing(s);
});
