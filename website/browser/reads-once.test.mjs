import assert from "node:assert/strict";
import test from "node:test";
import { boot, clickRow, findRow, sleep } from "./walkdriver.mjs";

/* A PRESS READS WHAT IT CHANGED ONCE, AND AN ARRIVAL REACHES THE RAIL AT ONCE (the load-once pass, 2026-10-27; the owner, the same day:
   "yes of course but careful nothing else changes - I thought we fixed this"). Every wake-up carries the stamp of its write and the tab
   whose press made it (liveSeq.js): the rail is not built again for writes the press's own answer already held, the Review badge and the
   Advisor are not read again for them, and a burst that is not the page's own - a new mail - is read at once instead of 1.5 s later.
   Measured before this pass on the demo world: a row opened 15 GETs, Next 12-15 (a second full rail and conversation read 1.5 s after
   each), "All read, next" 9 (three Review counts), and a new mail 1.9-2.2 s from its arrival to its row. */
const at = (min) => { const d = new Date(Date.now() - min * 60000); return new Date(d - d.getTimezoneOffset() * 60000).toISOString().slice(0, 19).replace("T", " "); };
const mail = (i) => ({ external_id: `graph:reads-once-${i}`, channel: "email", from_email: `p${i}@vendor.example`, from_name: `Vendor ${i}`,
  subject: `Invoice ${i}`, body: "Please approve.", conversation_id: `reads-once-${i}`, sent_at: at(0.1), to: ["alex@northwind.example"] });
const task = (title) => ({ intent: "task", kind: "task", why: "scripted", title, summary: title, asks_owner: true });

async function watched(t) {
  const { h, page, errors } = await boot(t, { width: 1600, height: 810 });
  const gets = [], posts = [], advice = [];
  page.on("request", (r) => {
    const u = new URL(r.url());
    if (!u.pathname.startsWith("/api/") || u.pathname.startsWith("/api/fixture")) return;
    (r.method() === "GET" ? gets : posts).push(u.pathname);
  });
  // an Advisor line that lands is a real change, read once more for the item it names
  const cdp = await page.createCDPSession(); await cdp.send("Network.enable");
  cdp.on("Network.webSocketFrameReceived", (e) => { if (/"type":"advice"/.test(e.response?.payloadData || "")) advice.push(Date.now()); });
  const window = async (act, ms = 3500) => {
    const g = gets.length, p = posts.length, a = advice.length;
    await act(); await sleep(ms);
    const got = gets.slice(g), n = (path) => got.filter((x) => x === path).length;
    return { got, n, posts: posts.slice(p), lines: advice.length - a };
  };
  return { h, page, errors, window };
}
const pressNext = (page) => page.evaluate(() => document.querySelector("[data-tq-row] [data-tq-next]")?.click());

test("a row opened and each Next read the rail, the conversation and the Advisor once - never again for the press's own writes",
  { timeout: 240000 }, async (t) => {
  const { page, errors, window } = await watched(t);
  const open = await window(async () => {
    await clickRow(page, await findRow(page, /Invoice 88213/));
    await page.waitForSelector("[data-tq-canvas-item] [data-tq-task-body]", { timeout: 20000 });
  }, 4000);
  assert.ok(open.n("/api/funnel/pile") <= 1, `a row opened read the rail ${open.n("/api/funnel/pile")} times: ${open.got}`);
  assert.ok(open.n("/api/concierge") <= 1, `...and the conversation ${open.n("/api/concierge")} times`);
  assert.ok(open.n("/api/advice") <= 2 + open.lines, `...and the Advisor ${open.n("/api/advice")} times (${open.lines} lines landed)`);
  for (let i = 0; i < 2; i++) {
    const next = await window(() => pressNext(page));
    assert.ok(next.posts.includes("/api/concierge/stream"), `Next ${i} was pressed: ${next.posts}`);
    // the press's answer carries the rail: the 1.5 s reload behind it read the same rows again
    assert.equal(next.n("/api/funnel/pile"), 0, `Next ${i} read the rail again: ${next.got}`);
    assert.equal(next.n("/api/concierge"), 0, `Next ${i} read the conversation again: ${next.got}`);
    assert.ok(next.n("/api/advice") <= 1 + next.lines, `Next ${i} read the Advisor ${next.n("/api/advice")} times (${next.lines} lines landed)`);
    assert.ok(next.n("/api/reviews") <= 1, `Next ${i} counted the Review badge ${next.n("/api/reviews")} times`);
  }
  assert.deepEqual(errors, []);
});

test("All read, next on an FYI batch counts the badge at most twice and reads the rail it brought back never",
  { timeout: 240000 }, async (t) => {
  const { page, errors, window } = await watched(t);
  await page.click('[data-tq-section-head="reports"] .fold').catch(() => {}); await sleep(1500);
  await page.evaluate(() => [...document.querySelectorAll('[data-tq-run="reports"] .tq-pile-row[data-tq-key] .card')].at(-1)?.click()); await sleep(3500);
  await pressNext(page); await sleep(3500);
  const fyi = await window(() => pressNext(page));
  assert.ok(fyi.posts.includes("/api/funnel/settle"), `the press settled an FYI batch: ${fyi.posts}`);
  assert.equal(fyi.n("/api/funnel/pile"), 0, `the settle's own rail was read again: ${fyi.got}`);
  assert.ok(fyi.n("/api/reviews") <= 2, `the Review badge was counted ${fyi.n("/api/reviews")} times: ${fyi.got}`);
  assert.ok(fyi.n("/api/advice") <= 1 + fyi.lines, `the Advisor was read ${fyi.n("/api/advice")} times - the batch put down is not read again`);
  assert.deepEqual(errors, []);
});

test("a new mail reaches the rail at once - one rail read, well inside the old 1.5 s wait", { timeout: 240000 }, async (t) => {
  const { h, page, errors, window } = await watched(t);
  for (let i = 0; i < 2; i++) {
    const title = `Approve reads-once invoice ${i}`;
    let ms = null;
    const got = await window(async () => {
      const t0 = Date.now();
      await fetch(`${h.fixtureApi}/api/fixture/intake/arrive`, { method: "POST", headers: { "Content-Type": "application/json", "X-Taskuary-Token": h.token },
        body: JSON.stringify({ messages: [{ msg: mail(i), verdict: task(title) }] }) });
      await page.waitForFunction((x) => [...document.querySelectorAll("[data-tq-rail] .tq-pile-row .t b")].some((b) => b.textContent === x), { timeout: 8000, polling: 20 }, title);
      ms = Date.now() - t0;
    }, 3000);
    assert.ok(ms < 1400, `mail ${i} took ${ms} ms to reach the rail`);
    assert.equal(got.n("/api/funnel/pile"), 1, `mail ${i}: one arrival, one rail read: ${got.got}`);
  }
  assert.deepEqual(errors, []);
});
