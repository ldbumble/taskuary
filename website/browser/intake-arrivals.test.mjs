import assert from "node:assert/strict";
import test from "node:test";

import { startHarness } from "./harness.mjs";

/* MAIL ARRIVING, AS THE PAGE HEARS IT (the intake walk, 2026-10-26): every arrival goes through the real door (ingest.ingest_message,
   triage scripted) while the page is open at the owner's laptop size. One arrival is one rail read; the same mail on the next sync pass
   is nothing at all; and a task open on the table is not re-read when the mail is for OTHER work - each one re-read it and its waiting
   room. A reply on the open task still is. */

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const at = (min) => { const d = new Date(Date.now() - min * 60000); return new Date(d - d.getTimezoneOffset() * 60000).toISOString().slice(0, 19).replace("T", " "); };
const mail = (ext, from_email, from_name, subject, body, conversation_id) =>
  ({ external_id: ext, channel: "email", from_email, from_name, subject, body, conversation_id, sent_at: at(0.1), to: ["alex@northwind.example"] });
const task = (title) => ({ intent: "task", kind: "task", why: "scripted", title, summary: title, asks_owner: true });
const rows = (page) => page.$$eval("[data-tq-rail] .tq-pile-row .t b", (els) => els.map((b) => b.textContent));

test("an arrival is one rail read, a repeat is none, and other work leaves the open task alone", { timeout: 300000 }, async (t) => {
  const h = await startHarness();
  t.after(() => h.close());
  const page = await h.newPage();
  await page.setViewport({ width: 1600, height: 810 });
  const reqs = [], errors = [];
  page.on("request", (r) => { const u = new URL(r.url()); if (u.pathname.startsWith("/api/") && !u.pathname.startsWith("/api/fixture")) reqs.push(r.method() + " " + u.pathname); });
  page.on("pageerror", (e) => errors.push(e.message));
  // the wake-ups the page hears: other work moving in a window (a demo agent's pane changing state on its own task, handraise.moved) is
  // read on its own account, and counted apart from the arrival's
  const wakes = [], cdp = await page.createCDPSession(); await cdp.send("Network.enable");
  cdp.on("Network.webSocketFrameReceived", (e) => {
    const d = e.response?.payloadData || "";
    if (/"type":"(task|feed)-changed"/.test(d)) { try { wakes.push(JSON.parse(d)); } catch { /* not one of ours */ } }
  });
  const arrive = async (items, settle = 4000) => {
    const from = reqs.length, w = wakes.length;
    const res = await fetch(`${h.fixtureApi}/api/fixture/intake/arrive`, { method: "POST", headers: { "Content-Type": "application/json", "X-Taskuary-Token": h.token },
      body: JSON.stringify({ messages: items }) }).then((r) => r.json());
    assert.ok(res.out, JSON.stringify(res));
    await sleep(settle);
    return { out: res.out, reqs: reqs.slice(from), wakes: wakes.slice(w) };
  };
  await page.goto(h.ui, { waitUntil: "domcontentloaded", timeout: 30000 });
  await page.waitForSelector("[data-tq-rail] .tq-pile-row", { timeout: 60000 });
  await sleep(4000);

  const first = { msg: mail("graph:arrive-1", "paula@vendor.example", "Paula Vance", "Payworth invoice 2210", "Please approve invoice 2210 by Friday.", "arrive-1"),
    verdict: task("Approve Payworth invoice 2210") };
  const one = await arrive([first]);
  assert.equal(one.out[0].status, "created");
  assert.ok((await rows(page)).includes("Approve Payworth invoice 2210"), "the arrival's row is on the rail");
  const theirs = (e) => [e.task_id, ...(e.task_ids || [])].includes(one.out[0].task_id) || e.message_id === one.out[0].message_id;
  const elsewhere = one.wakes.filter((e) => !theirs(e)).length, reads = one.reqs.filter((r) => r === "GET /api/funnel/pile").length;
  assert.ok(reads >= 1 && reads <= 1 + elsewhere, `one arrival, one rail read (${elsewhere} wake-ups for other work): ${one.reqs}\n${JSON.stringify(one.wakes)}`);

  const again = await arrive([{ ...first, verdict: null }], 2500);
  assert.equal(again.out[0].status, "duplicate");
  // (the page's own timers - capabilities' 4 s tail of the last arrival, the live-runs tick - may fall in the window; no read an arrival makes)
  assert.deepEqual(again.reqs.filter((r) => /funnel|ingest|reviews|concierge|tasks/.test(r)), [], `the next sync pass's copy of the same mail is nothing: ${again.reqs}`);

  await page.evaluate(() => [...document.querySelectorAll("[data-tq-rail] .tq-pile-row .card")].find((c) => c.textContent.includes("Approve Payworth invoice 2210")).click());
  await page.waitForFunction(() => document.querySelector(".tq-pile-row.current")?.textContent.includes("Approve Payworth invoice 2210"), { timeout: 20000 });
  await sleep(4000);
  const tid = one.out[0].task_id;
  const other = await arrive([{ msg: mail("graph:arrive-2", "omar@northwind.example", "Omar Keller", "Badge for the new starter", "Can you order a badge?", "arrive-2"),
    verdict: task("Order a badge for the new starter") }]);
  assert.ok((await rows(page)).includes("Order a badge for the new starter"));
  assert.deepEqual(other.reqs.filter((r) => r.startsWith(`GET /api/tasks/${tid}`)), [], `mail for other work re-read the open task: ${other.reqs}`);
  const mine = await arrive([{ msg: mail("graph:arrive-3", "paula@vendor.example", "Paula Vance", "RE: Payworth invoice 2210", "Attached the corrected invoice.", "arrive-1"),
    verdict: task("Approve Payworth invoice 2210") }]);
  assert.equal(mine.out[0].task_id, tid);
  assert.ok(mine.reqs.includes(`GET /api/tasks/${tid}`), `a reply on the open task re-reads it: ${mine.reqs}`);
  assert.deepEqual(errors, []);
});
