import assert from "node:assert/strict";
import test from "node:test";
import { boot, clickRow, pressNext, sleep } from "./walkdriver.mjs";

/* BACK NEVER READS (the owner, 2026-10-29): a report opened from the Reports band, then Back on the bottom bar, was gone from the list -
   putting it on the table had read it, and a report read leaves the rail. Next reads it and moves on; Back, opening and looking never do.
   On the demo world: open a report, Back, and its row is still under Reports, unread; open it again and Next, and it is read and gone. */
const reports = (page) => page.$$eval('[data-tq-run="reports"] .tq-pile-row[data-tq-key]', (els) => els.map((e) => e.getAttribute("data-tq-key")));
const pressBack = (page) => page.evaluate(() => { const b = document.querySelector(".tq-dock [data-tq-row] [data-tq-walk-back]"); if (b && !b.disabled) { b.click(); return true; } return false; });
const until = async (f, ms = 15000) => { for (const t0 = Date.now(); Date.now() - t0 < ms; await sleep(200)) if (await f()) return true; return false; };
const unfold = async (page) => { await page.evaluate(() => document.querySelector('[data-tq-section-head="reports"] .fold')?.click()); await sleep(1500); };

test("Back from a report leaves it unread in Reports; Next on it reads it", { timeout: 240000 }, async (t) => {
  const { h, page, errors } = await boot(t, { width: 1440, height: 900 });
  const api = (path) => fetch(`${h.fixtureApi}${path}`, { headers: { "X-Taskuary-Token": h.token } }).then((r) => r.json());
  const row = async (k) => (await api("/api/funnel/pile")).items.find((i) => i.key === k || (i.aliases || []).includes(k));
  await unfold(page);
  const rep = (await reports(page))[0];
  assert.ok(rep, "the demo has a report");
  assert.ok(await clickRow(page, rep));
  await page.waitForSelector('[data-tq-item-sections="report"], [data-tq-item-sections="dashboard"]', { timeout: 20000 }); await sleep(2500);
  assert.ok((await row(rep))?.unread, "opening the report did not read it");
  assert.ok(await pressBack(page), "the report has a Back");
  assert.ok(await until(async () => !(await page.$('.tq-canvas-live [data-tq-item-sections="report"]'))), "Back left the report");
  await sleep(2500);
  assert.ok((await row(rep))?.unread, `Back marked the report read: ${JSON.stringify(await row(rep))}`);
  if (!(await reports(page)).includes(rep)) await unfold(page);
  assert.ok((await reports(page)).includes(rep), "the report is still in the Reports band after Back");

  assert.ok(await clickRow(page, rep)); await sleep(3000);
  assert.ok(await pressNext(page));
  assert.ok(await until(async () => !(await row(rep))), "Next on the report read it off the rail");
  assert.ok(await until(async () => !(await reports(page)).includes(rep)), "and its row left Reports");
  assert.deepEqual(errors, []);
});

// NEXT READS THE REPORT OPEN ON THE REPORTS PAGE (the owner, 2026-10-30: "i hit next on reports ... it did not mark it as read and disappear"):
// opened on the page (its #report= link), not from its row - Next read the table's item under the page and left the report unread
test("Next with a report open on the Reports page reads that report off the rail", { timeout: 240000 }, async (t) => {
  const { h, page, errors } = await boot(t, { width: 1440, height: 900 });
  const api = (path) => fetch(`${h.fixtureApi}${path}`, { headers: { "X-Taskuary-Token": h.token } }).then((r) => r.json());
  const rep = (await api("/api/funnel/pile")).items.find((i) => i.lane === "report" && typeof i.source_id === "number");
  assert.ok(rep, "the demo has a report with a source on the rail");
  // ...over a task, as the owner had it: the table's item is what Next walked on from
  const task = (await api("/api/funnel/pile")).items.find((i) => i.tid);
  assert.ok(await clickRow(page, task.key)); await sleep(3500);
  await page.evaluate((sid) => { location.hash = `report=${sid}`; }, rep.source_id);
  await page.waitForSelector('[data-tq-browse="reports"]', { timeout: 20000 }); await sleep(2500);
  assert.ok((await api("/api/funnel/pile")).items.some((i) => i.key === rep.key), "opening it on the page read it");
  assert.ok(await pressNext(page), "no Next over the Reports page");
  assert.ok(await until(async () => !(await api("/api/funnel/pile")).items.some((i) => i.key === rep.key)), `Next left ${rep.key} on the rail`);
  assert.deepEqual(errors, []);
});
