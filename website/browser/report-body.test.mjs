import assert from "node:assert/strict";
import test from "node:test";
import { boot, clickRow, findRow, sleep } from "./walkdriver.mjs";

/* A DATA REPORT READS AS ONE, AND THE BUILT-IN DASHBOARD OPENS LIKE IT (the owner, 2026-10-28: "the report on the demo site looks horrible.
   make it look better. also add a dashboard like all taskuary versions come with by default"). On the demo world: a report's body is its
   name, one line of what it found, its chart and its table side by side at a desk's width - the table using its width, numbers
   right-aligned in tabular figures - and one above the other on a phone; its files a row of chips. Taskuary at a glance, which every
   install has, opens in the same three sections, the dashboard in the middle. */
const body = (page) => page.evaluate(() => {
  const r = document.querySelector("[data-tq-report-body] [data-tq-report-rows]");
  if (!r) return null;
  const box = (e) => e && (({ left, top, width, height }) => ({ x: Math.round(left), y: Math.round(top), w: Math.round(width), h: Math.round(height) }))(e.getBoundingClientRect());
  const t = r.querySelector("[data-tq-report-table] table"), chart = r.querySelector("[data-tq-report-chart]");
  const nums = [...t.querySelectorAll("tbody td.n")];
  return { h2: r.querySelector("h2")?.textContent, said: r.querySelector("[data-tq-report-summary]")?.textContent, rep: box(r), table: box(t),
    chart: chart && { kind: chart.dataset.tqReportChart, ...box(chart) }, rows: t.querySelectorAll("tbody tr").length,
    right: nums.every((td) => getComputedStyle(td).textAlign === "right"), tab: nums.every((td) => getComputedStyle(td).fontVariantNumeric.includes("tabular-nums")),
    cells: nums.map((td) => td.textContent), img: !!r.querySelector("img"), chips: [...r.querySelectorAll("a[href]")].map((a) => a.textContent) };
});

// a report's row, unfolding the Reports section when it is folded away
const reportRow = async (page, re) => {
  let key = await findRow(page, re);
  if (!key) { await page.evaluate(() => document.querySelector('[data-tq-section-head="reports"] .fold')?.click()); await sleep(1200); key = await findRow(page, re); }
  return key;
};

test("a data report reads as its name, what it found, its chart and its table side by side - one above the other on a phone", { timeout: 240000 }, async (t) => {
  const { page, errors } = await boot(t, { width: 1440, height: 900 });
  assert.ok(await clickRow(page, await reportRow(page, /AP ageing over 30 days/)));
  await page.waitForSelector("[data-tq-report-rows]", { timeout: 20000 }); await sleep(1200);
  const b = await body(page);
  assert.equal(b.h2, "AP ageing over 30 days, weekly");
  assert.match(b.said, /^5 rows · [\d,.]+ past due in all · largest \S.* at [\d,.]+ \(\d+%\)$/, b.said);
  assert.equal(b.rows, 5);
  assert.ok(b.right && b.tab, "every number right-aligned in tabular figures");
  assert.ok(b.cells.every((c) => /\.\d\d$/.test(c)), `one count of decimals in a column: ${b.cells}`);
  assert.equal(b.chart.kind, "bars");
  assert.ok(Math.abs(b.chart.y - b.table.y) < 40 && b.chart.x < b.table.x, `side by side: ${JSON.stringify(b)}`);
  assert.ok(b.chart.w + b.table.w > b.rep.w * 0.85, `together they use the card's width, not a narrow table in an empty panel: ${JSON.stringify(b)}`);
  assert.ok(!b.img, "the chart is drawn, not its picture");
  assert.ok(b.chips.some((c) => /\.xlsx/.test(c)) && b.chips.some((c) => /\.svg/.test(c)), `its files are chips: ${b.chips}`);

  // a run of days is a line
  assert.ok(await clickRow(page, await reportRow(page, /Helpdesk tickets by day/)));
  await page.waitForFunction(() => document.querySelector("[data-tq-report-rows] h2")?.textContent.startsWith("Helpdesk"), { timeout: 20000 }); await sleep(800);
  const d = await body(page);
  assert.equal(d.chart.kind, "line");
  assert.match(d.said, /^14 days · [\d,]+ tickets in all · peak \d+ on [A-Z][a-z]{2} \d+/, d.said);

  // ...and on a phone the chart sits above the table, each the card's width
  await page.setViewport({ width: 390, height: 844, deviceScaleFactor: 1 }); await sleep(1500);
  const p = await body(page);
  assert.ok(p.chart.y + p.chart.h <= p.table.y + 2 && Math.abs(p.chart.w - p.table.w) < 30, `stacked: ${JSON.stringify(p)}`);
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), "no sideways scroll");
  assert.deepEqual(errors, []);
});

test("the built-in dashboard opens in a task's three sections, the dashboard in the middle", { timeout: 240000 }, async (t) => {
  const { page, errors } = await boot(t, { width: 1440, height: 900 });
  assert.ok(await clickRow(page, await reportRow(page, /Taskuary at a glance/)), "the built-in dashboard is on the rail");
  await page.waitForSelector('[data-tq-item-sections="dashboard"] [data-tq-dash-body] [data-tq-dash-kind]', { timeout: 20000 }); await sleep(1200);
  const m = await page.evaluate(() => {
    const it = document.querySelector('[data-tq-item-sections="dashboard"]');
    return { main: it.querySelector("[data-tq-sections]").dataset.tqMain, slots: [...it.querySelectorAll("[data-tq-slot]")].map((s) => s.dataset.tqSlot),
      head: it.querySelector("[data-tq-item-head]").innerText.replace(/\s+/g, " "), tiles: it.querySelectorAll('[data-tq-dash-body] [data-tq-dash-kind="stat"]').length };
  });
  assert.equal(m.main, "report");
  assert.deepEqual(m.slots, ["from", "report", "close"]);
  assert.match(m.head, /^Dashboard Taskuary at a glance/);
  assert.equal(m.tiles, 5);
  // Came from names what produced it, with the way to edit it
  await page.evaluate(() => document.querySelector('[data-tq-item-sections] [data-tq-section-tab="from"]')?.click()); await sleep(600);
  assert.match(await page.$eval("[data-tq-dash-from]", (e) => e.innerText), /Dashboard\s+Taskuary at a glance[\s\S]*Runs\s+\S[\s\S]*Edit this dashboard/);
  assert.deepEqual(errors, []);
});
