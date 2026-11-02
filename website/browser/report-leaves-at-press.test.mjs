import assert from "node:assert/strict";
import test from "node:test";
import { boot, clickRow, pressNext, sleep } from "./walkdriver.mjs";

/* ONE NEXT ON A REPORT TAKES ITS ROW OFF THE RAIL IN THE FRAME THE TABLE MOVES (the owner, 2026-11-02: "on a report if you press Next, the
   canvas shrinks the report right away and 'on the table' moves to the next item right away, but the prior report stays on the work rail for
   an extra second before it leaves"). The ring moving is not the row leaving: each frame after the press is sampled for the passed report's
   row in the DOM (drawn, with height), and for the ring. With the walk's answer held 2.5 s the row can only leave by the page's own word. */
const SOON = 150;
const run = (page, sec) => page.$$eval(`[data-tq-run="${sec}"] .tq-pile-row[data-tq-key]`, (els) => els.map((e) => e.getAttribute("data-tq-key")));
const ring = (page) => page.evaluate(() => document.querySelector("[data-tq-rail] .tq-pile-row.current")?.getAttribute("data-tq-key") || "");
const until = async (f, ms = 15000) => { for (const t0 = Date.now(); Date.now() - t0 < ms; await sleep(50)) if (await f()) return true; return false; };
// every frame from the press: when the ring left `from`, when `from`'s row stopped being drawn on the rail for good (`goneAt`), first
// (`firstGone`), and when it was drawn again after leaving (`backAt`, -1: never)
const pressAndSample = (page, from) => page.evaluate((k) => new Promise((done) => {
  const b = document.querySelector("[data-tq-row] [data-tq-next]");
  if (!b || b.disabled) { done(null); return; }
  const shown = () => [...document.querySelectorAll(`[data-tq-rail] .tq-pile-row[data-tq-key="${k}"]`)].some((e) => e.getBoundingClientRect().height > 0 && getComputedStyle(e).display !== "none");
  const ringOn = () => document.querySelector("[data-tq-rail] .tq-pile-row.current")?.getAttribute("data-tq-key") || "";
  const t0 = performance.now(); let ringAt = -1, goneAt = -1, firstGone = -1, backAt = -1;
  const tick = () => { const t = Math.round(performance.now() - t0);
    if (ringAt < 0 && ringOn() !== k) ringAt = t;
    if (shown()) { if (goneAt >= 0 && backAt < 0) backAt = t; goneAt = -1; } else { if (goneAt < 0) goneAt = t; if (firstGone < 0) firstGone = t; }
    if (t > 4000) done({ ringAt, goneAt, firstGone, backAt }); else requestAnimationFrame(tick); };
  b.click(); requestAnimationFrame(tick);
}), from);

async function onReport(t, slow, arrive) {
  const { page, errors } = await boot(t, { width: 1440, height: 900, ...(slow ? { slow, slowOn: "/api/walk/" } : {}) });
  const tasks = await run(page, "task"), reports = await run(page, "reports");
  assert.ok(tasks.length && reports.length >= 2, `the demo has tasks and reports: ${tasks} / ${reports}`);
  const r0 = reports[0];
  if (arrive === "click") await clickRow(page, r0);
  else { await clickRow(page, tasks.at(-1)); await until(async () => (await ring(page)) === tasks.at(-1)); await sleep(slow + 2500); assert.ok(await pressNext(page), "Next from the last task"); }
  assert.ok(await until(async () => (await ring(page)) === r0), `the report is on the table: the ring is on ${await ring(page)}`);
  await sleep(slow + 3000);
  const m = await pressAndSample(page, r0);
  assert.ok(m, "Next is pressable on the report");
  assert.ok(m.ringAt >= 0 && m.ringAt <= SOON, `the ring stayed on the report ${m.ringAt} ms`);
  assert.ok(m.goneAt >= 0 && m.goneAt <= SOON, `the report's row stayed on the rail ${m.goneAt} ms after Next (the ring moved at ${m.ringAt} ms)`);
  await sleep(slow + 2000);
  assert.ok(!(await run(page, "reports")).includes(r0), "the report came back on the rail");
  assert.deepEqual(errors, []);
}

/* ...AND A REPORT THAT RE-RAN WHILE IT WAS ON THE TABLE (a nightly report's new run): its row has a new key now and answers to the old one
   as an alias, the ring finds it by that alias - and the press took off only the key it had, so the row stayed until the answer's rail.
   The fixture moves the report onto a new item the way a re-run does; the walk's answer is held 2.5 s. */
async function rerun(t, slow) {
  const { h, page, errors } = await boot(t, { width: 1440, height: 900, ...(slow ? { slow, slowOn: "/api/walk/" } : {}) });
  const [r0] = await run(page, "reports");
  await clickRow(page, r0);
  assert.ok(await until(async () => (await ring(page)) === r0), `the report is on the table: the ring is on ${await ring(page)}`);
  await sleep(slow + 2500);
  const { new: r1 } = await fetch(`${h.fixtureApi}/api/fixture/processing/rerun`, { method: "POST", headers: { "X-Taskuary-Token": h.token, "Content-Type": "application/json" },
    body: JSON.stringify({ key: r0 }) }).then((r) => r.json());
  assert.ok(await until(async () => (await run(page, "reports")).includes(r1)), `the re-run's row never reached the rail: ${await run(page, "reports")}`);
  await sleep(1500);
  const drawn = await page.$$eval("[data-tq-rail] .tq-pile-row[data-tq-key]", (els, ks) => els.filter((e) => ks.includes(e.dataset.tqKey)).length, [r0, r1]);
  console.log("re-run", r0, "->", r1, "rows drawn for it", drawn, "ring", await ring(page));
  const m = await pressAndSample(page, r1);
  console.log("re-run press", JSON.stringify(m));
  assert.ok(m, "Next is pressable on the re-run report");
  assert.ok(m.ringAt >= 0 && m.ringAt <= SOON, `the ring stayed on the re-run report ${m.ringAt} ms`);
  assert.ok(m.goneAt >= 0 && m.goneAt <= SOON, `the re-run report's row stayed on the rail ${m.goneAt} ms after Next (the ring moved at ${m.ringAt} ms)`);
  await sleep(slow + 2000);
  const left = await run(page, "reports");
  assert.ok(!left.includes(r1) && !left.includes(r0), `the re-run report came back on the rail: ${left}`);
  assert.deepEqual(errors, []);
}
test("Next on a report that re-ran while on the table takes its row off at the press", { timeout: 300000 }, (t) => rerun(t, 2500));
test("...with the walk's answer immediate", { timeout: 300000 }, (t) => rerun(t, 0));

/* ...AND THE ANSWER'S RAIL NEVER BRINGS IT BACK unless the answer says the read did not happen: the walk's answer is caught on its way to the
   page and its rail given the passed report again, as a rail built before the read would have it - with `read` saying it was read, the
   row stays off; with `read` empty (the read failed), it is given back as a failed press gives it back. */
async function staleAnswer(t, failed) {
  const { page, errors } = await boot(t, { width: 1440, height: 900 });
  const [r0] = await run(page, "reports");
  const row = await page.evaluate((k) => fetch("/api/funnel/pile", { headers: { "X-Taskuary-Token": localStorage.getItem("taskuary_token") } })
    .then((r) => r.json()).then((p) => p.items.find((i) => i.key === k)), r0);
  page.off("request", page.fixtureRequestGuard);
  page.on("request", async (req) => {
    if (req.method() !== "POST" || !/\/api\/walk\/next$/.test(req.url())) return page.fixtureRequestGuard(req);
    const res = await fetch(req.url(), { method: "POST", headers: req.headers(), body: req.postData() });
    const data = await res.json();
    if (data.pile && !data.pile.items.some((i) => i.key === r0)) data.pile.items = [row, ...data.pile.items];
    if (failed) data.read = [];
    req.respond({ status: res.status, contentType: "application/json", body: JSON.stringify(data) });
  });
  await clickRow(page, r0);
  assert.ok(await until(async () => (await ring(page)) === r0), `the report is on the table: the ring is on ${await ring(page)}`);
  await sleep(3000);
  const m = await pressAndSample(page, r0);
  console.log(failed ? "read failed" : "stale rail", JSON.stringify(m));
  assert.ok(m.firstGone >= 0 && m.firstGone <= SOON, `the report's row stayed on the rail ${m.firstGone} ms after Next`);
  if (failed) assert.ok(m.backAt >= 0, "a read the answer says failed was not given back");
  else assert.ok(m.backAt < 0, `a rail built before the read brought the passed report back at ${m.backAt} ms`);
  assert.deepEqual(errors, []);
}
test("an answer whose rail still lists the passed report does not bring it back", { timeout: 300000 }, (t) => staleAnswer(t, false));
test("...but an answer saying the read failed gives it back", { timeout: 300000 }, (t) => staleAnswer(t, true));

test("Next on a report reached by Next takes its row off the rail at the press", { timeout: 300000 }, (t) => onReport(t, 0, "next"));
test("...with the walk's answer held", { timeout: 300000 }, (t) => onReport(t, 2500, "next"));
test("Next on a report clicked takes its row off the rail at the press", { timeout: 300000 }, (t) => onReport(t, 0, "click"));
test("...clicked, with the walk's answer held", { timeout: 300000 }, (t) => onReport(t, 2500, "click"));
