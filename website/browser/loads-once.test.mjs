import assert from "node:assert/strict";
import test from "node:test";
import os from "node:os";
import path from "node:path";
import { startHarness } from "./harness.mjs";
import { note, record } from "./recorder.mjs";

/* A PAGE LOADS ITS DATA ONCE (the owner, 2026-10-26: "things don't load twice, if you click a button twice it won't reload [double
   work]"). The overnight setup walk counted the GETs each open fires in the demo world: every start asked for the first-run state, the
   build and today's meetings twice each, and Settings > Docs read all nine documents to draw a list that shows none of their words. */
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const gets = (page) => {
  const seen = [];
  page.on("request", (r) => { const u = new URL(r.url()); if (r.method() === "GET" && u.pathname.startsWith("/api/")) seen.push(u.pathname); });
  return { since: (i) => seen.slice(i), get n() { return seen.length; } };
};
const count = (list, path) => list.filter((p) => p === path).length;
const ONCE = ["/api/setup/first-run", "/api/calendar/today", "/api/build"];

test("a start reads the first-run state, the build and today's meetings once each; Settings > Docs draws its list without the documents",
  { timeout: 180000 }, async (t) => {
  const h = await startHarness(); t.after(() => h.close());
  const page = await h.newPage(), errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.setViewport({ width: 1600, height: 810, deviceScaleFactor: 1 });
  const g = gets(page);
  await page.goto(h.ui, { waitUntil: "domcontentloaded" });
  await page.waitForSelector("[data-tq-rail] .tq-pile-row", { timeout: 60000 });
  await sleep(2500);
  const boot = g.since(0);
  for (const p of ONCE) assert.equal(count(boot, p), 1, `${p} read ${count(boot, p)} times at the start`);

  // Connections opens on its catalogue without asking the machine for SQL Server's ODBC drivers - that card asks when it opens
  const conns = g.n;
  await page.evaluate(() => document.querySelector('[data-tq-nav="connections"]').click());
  await page.waitForSelector('[data-tq-browse="connections"] [data-tq-browse-chip]', { timeout: 20000 });
  await sleep(1500);
  assert.ok(!g.since(conns).includes("/api/mssql/drivers"), `Connections asked for the ODBC drivers: ${g.since(conns)}`);

  // ...the documents live on About you now (the owner, 2026-11-06: You, Docs and Memory on one page; LEARNED.md is its Memory)
  // ...opened from the avatar in the top bar's corner, not a sidebar line (the owner, 2026-11-06)
  await page.evaluate(() => document.querySelector("[data-tq-profile]").click());
  await page.waitForSelector('[data-tq-browse="about"] [data-tq-browse-chip]');
  const at = g.n;
  await page.evaluate(() => [...document.querySelectorAll('[data-tq-browse="about"] [data-tq-browse-chip]')].find((c) => c.innerText.trim() === "Docs").click());
  await page.waitForFunction(() => [...document.querySelectorAll('[data-tq-browse="about"] [data-tq-browse-card]')].some((c) => /JOB\.md/.test(c.innerText)), { timeout: 20000 });
  await sleep(1500);
  const docs = g.since(at).filter((p) => p.startsWith("/api/doc/"));
  assert.deepEqual(docs, [], "the list of documents reads none of them");
  // ...and a document opened from it is still read and drawn - without the rules, settings and notes the other pages show
  const open = g.n;
  await page.evaluate(() => [...document.querySelectorAll('[data-tq-browse="about"] [data-tq-browse-card]')].find((c) => /JOB\.md/.test(c.innerText)).click());
  await page.waitForFunction(() => document.querySelector('[data-tq-browse="about"] [data-tq-browse-one] textarea')?.value.length > 0, { timeout: 20000 });
  await sleep(1000);
  const opened = g.since(open);
  assert.ok(opened.includes("/api/doc/job"), `the document is read: ${opened}`);
  for (const p of ["/api/policies", "/api/memory", "/api/brains", "/api/mailboxes"]) assert.ok(!opened.includes(p), `${p} is not read to open a document`);
  // ...while Configuration, which shows them, still reads them
  await page.evaluate(() => document.querySelector('[data-tq-nav="settings"]').click());
  await page.waitForSelector('[data-tq-browse="settings"] [data-tq-browse-chip]');
  await page.evaluate(() => [...document.querySelectorAll('[data-tq-browse="settings"] [data-tq-browse-chip]')].find((c) => c.innerText.trim() === "Configuration").click());
  await page.waitForFunction(() => document.querySelectorAll('[data-tq-browse="settings"] [data-tq-browse-card]').length > 2, { timeout: 20000 });
  const cfg = g.n;
  await page.evaluate(() => document.querySelector('[data-tq-browse="settings"] [data-tq-browse-card]').click());
  await page.waitForFunction(() => document.querySelector('[data-tq-browse="settings"] [data-tq-browse-one]')?.innerText.length > 40, { timeout: 20000 });
  await sleep(1000);
  assert.ok(g.since(cfg).includes("/api/policies"), "Configuration still reads what it shows");
  assert.deepEqual(errors, []);
});

// SETUP'S CANVAS, ITS RAIL AND THE ASSISTANT SHARE ONE READ OF THE FIRST RUN: the canvas's 5 s read and the rail's own 8 s one were two
// GETs of the same answer, four or five every twelve seconds while a person sets up
test("setup reads its state once for the canvas, the rail and the Assistant - at the start and while it waits", { timeout: 180000 }, async (t) => {
  const h = await startHarness({ fresh: true }); t.after(() => h.close());
  const page = await h.newPage(), errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.setViewport({ width: 1600, height: 810, deviceScaleFactor: 1 });
  // an AI stood in by a key nothing calls (fresh-setup.test.mjs), so setup waits on the main source - the step the canvas re-reads on
  const api = (p, body, method = body ? "POST" : "GET") => fetch(`${h.fixtureApi}${p}`, { method,
    headers: { "Content-Type": "application/json", "X-Taskuary-Token": h.token }, body: body && JSON.stringify(body) }).then((r) => r.json());
  const key = (await api("/api/connectors")).data.find((c) => c.Type === "anthropic");
  await api("/api/connectors", { ConnectorId: key.ConnectorId, Secret: "sk-test-not-a-real-key-000000", Active: true });
  await api("/api/settings", { name: "triage_ai", value: `connector:${key.ConnectorId}` }, "PATCH");
  const g = gets(page);
  await page.goto(h.ui, { waitUntil: "domcontentloaded" });
  await page.waitForSelector('[data-tq-firstrun="email"] [data-tq-card]', { timeout: 60000 });
  await page.waitForSelector("[data-tq-setup-step]");
  assert.equal(count(g.since(0), "/api/setup/first-run"), 1, `the start: ${count(g.since(0), "/api/setup/first-run")} reads`);
  // waiting on the main source: the canvas reads every 5 s (a sign-in may finish in another tab), and the rail draws those answers
  const at = g.n;
  await sleep(16500);
  const n = count(g.since(at), "/api/setup/first-run");
  assert.ok(n <= 4, `${n} reads of the first run in 16.5 s`);
  assert.match(await page.$eval('[data-tq-setup-step="ai"]', (e) => e.innerText), /Your AI[\s\S]*Anthropic/, "the rail still draws each answer");
  assert.deepEqual(errors, []);
});

// A WAKE-UP DOES NOT RE-READ THE REVIEW QUEUE (2026-11-17): the top bar counted /api/reviews?status=pending - every pending card,
// decorated - on mount and after every settled burst of feed-changed / task-changed, for a badge nothing drew. A card that shows a
// review reads it itself; the hub reads it never
test("the hub never reads the pending reviews - not on mount, not on a wake-up", { timeout: 180000 }, async (t) => {
  // ...on a fresh home, not the demo: the demo refuses every write it does not list (the poke below is one), as it must for the public site
  const h = await startHarness({ fresh: true }); t.after(() => h.close());
  const post = (p, body) => fetch(`${h.fixtureApi}${p}`, { method: "POST", headers: { "Content-Type": "application/json", "X-Taskuary-Token": h.token }, body: JSON.stringify(body) });
  await post("/api/setup/first-run/ai", { name: "claude" }); await post("/api/setup/dismiss", { dismissed: true });
  await post("/api/fixture/mail-task", { sent: "2026-11-10 08:00:00" });          // ...a row on the rail, and its draft a review card
  const page = await h.newPage(), errors = [], reads = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("request", (r) => { const u = new URL(r.url()); if (r.method() === "GET" && u.pathname === "/api/reviews" && u.searchParams.get("status") === "pending") reads.push(Date.now()); });
  await page.setViewport({ width: 1600, height: 810, deviceScaleFactor: 1 });
  await page.goto(h.ui, { waitUntil: "domcontentloaded" });
  await page.waitForSelector("[data-tq-rail] .tq-pile-row", { timeout: 60000 });
  await sleep(2500);
  // a review card on the table reads its own row - that read is the card's, not the hub's
  const cards = await page.$$eval("[data-tq-review]", (els) => els.length);
  const boot = reads.length;
  const dir = path.join(process.env.TEMP || os.tmpdir(), "claude", "loads-once", "reviews-on-wake"), rec = await record(page, dir);
  const rail = () => page.$$eval("[data-tq-rail] .tq-pile-row", (els) => els.map((e) => e.innerText.trim().split("\n")[0]).join(" | "));
  const before = await rail();
  const poke = () => fetch(`${h.fixtureApi}/api/fixture/live/poke`, { method: "POST", headers: { "Content-Type": "application/json", "X-Taskuary-Token": h.token }, body: "{}" });
  for (let i = 0; i < 3; i++) { assert.equal((await poke()).status, 200); await sleep(2500); }
  await rec.stop();
  const after = await rail(), woke = reads.length - boot;
  await note(dir, { done: "The hub at rest on the fixture; three feed-changed + task-changed pokes from the server, 2.5 s apart.",
    expect: "The rail stands still: no row flickers, moves or blanks. No GET /api/reviews?status=pending from the hub.",
    saw: `${boot} reads at the start with ${cards} review cards on screen, ${woke} after the pokes; rail before "${before}", after "${after}"`,
    verdict: !woke && boot <= cards && before === after ? "PASS" : "FAIL" });
  assert.ok(boot <= cards, `${boot} reads of the pending reviews at the start with ${cards} review cards on screen`);
  assert.equal(woke, 0, `${woke} reads of the pending reviews after three wake-ups`);
  assert.equal(after, before, "the rail stands as it was");
  assert.deepEqual(errors, []);
});
