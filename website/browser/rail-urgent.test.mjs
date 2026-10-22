import assert from "node:assert/strict";
import test from "node:test";

import { startHarness } from "./harness.mjs";

/* NO URGENT SECTION, AND REPORTS OLDEST FIRST (the owner, 2026-10-22): "reports should go oldest first like everything else", and
   "remove the urgent section and just add quiet shading around it for urgent notice". On the demo world: a task in the middle of
   Tasks is marked urgent - no Urgent heading appears, the row stays where it was, shaded, and says "urgent" to a screen reader -
   and the reports are drawn oldest first. */

async function request(h, path, method = "GET", body) {
  const response = await fetch(`${h.fixtureApi}${path}`, {
    method, headers: { "X-Taskuary-Token": h.token, "Content-Type": "application/json" },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
  assert.ok(response.ok, `${method} ${path}: ${response.status}`);
  return response.json();
}

const rail = (page) => page.$$eval("[data-tq-rail] .tq-pile-row", (els) => els
  .map((r) => ({ key: r.getAttribute("data-tq-key"), level: r.closest("[data-tq-run]")?.getAttribute("data-tq-run"),
    urgent: r.hasAttribute("data-tq-urgent"), label: r.querySelector(".card")?.getAttribute("aria-label") || "",
    shade: getComputedStyle(r.querySelector(".card")).backgroundColor }))
  .filter((r) => r.key));
const stamp = (s) => Date.parse(String(s || "").replace(" ", "T")) || 0;

test("an urgent task is shaded in its place under Tasks, with no Urgent heading, and reports read oldest first", { timeout: 240000 }, async (t) => {
  const harness = await startHarness();
  t.after(() => harness.close());
  const page = await harness.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(harness.ui, { waitUntil: "domcontentloaded", timeout: 20000 });
  await page.waitForSelector("[data-tq-rail] .tq-pile-row", { timeout: 30000 });

  const pile = await request(harness, "/api/funnel/pile");
  const byKey = Object.fromEntries((pile.items || []).map((i) => [i.key, i]));
  const before = await rail(page);
  const tasks = before.filter((r) => r.level === "task" && byKey[r.key]?.tid && !String(byKey[r.key]?.kind || "").startsWith("goal"));
  assert.ok(tasks.length >= 3, `the demo rail has tasks to mark: ${JSON.stringify(before)}`);
  assert.ok(!before.some((r) => r.urgent), "the demo world starts with nothing urgent");
  const mid = tasks[1];

  await request(harness, `/api/tasks/${byKey[mid.key].tid}`, "PATCH", { Priority: "urgent" });
  await page.waitForFunction((k) => document.querySelector(`[data-tq-rail] .tq-pile-row[data-tq-key="${k}"]`)?.hasAttribute("data-tq-urgent"),
    { timeout: 30000 }, mid.key).catch(async () => assert.fail(`the urgent task was never shaded: ${JSON.stringify(await rail(page))}`));
  // ...and the shade itself: the card's background fades in (transition: background .15s), so a read in the same frame saw transparent
  await page.waitForFunction((k) => { const c = document.querySelector(`[data-tq-rail] .tq-pile-row[data-tq-key="${k}"] .card`);
    return c && getComputedStyle(c).backgroundColor !== "rgba(0, 0, 0, 0)"; }, { timeout: 5000 }, mid.key).catch(() => {});

  const after = await rail(page);
  assert.equal(await page.$("[data-tq-section-head=urgent]"), null, "an Urgent heading was drawn");
  const heads = await page.$$eval("[data-tq-section-head]", (els) => els.map((e) => e.textContent.trim().toLowerCase()));
  assert.ok(!heads.some((h) => h.startsWith("urgent")), `an Urgent heading was drawn: ${heads}`);
  const row = after.find((r) => r.key === mid.key);
  assert.equal(row.level, "task", "the urgent task left Tasks");
  assert.match(row.label, /urgent$/, "the urgent row does not say urgent to a screen reader");
  assert.notEqual(row.shade, "rgba(0, 0, 0, 0)", "the urgent row is not shaded");
  assert.deepEqual(after.filter((r) => r.urgent).map((r) => r.key), [mid.key], "only the marked task is shaded");
  // ...and IN ITS PLACE: the rows of Tasks keep their order
  const kept = (rows) => rows.filter((r) => r.level === "task").map((r) => r.key).filter((k) => before.some((r) => r.key === k) && after.some((r) => r.key === k));
  assert.deepEqual(kept(after), kept(before), "marking a task urgent moved a row");

  // ...and WALKED IN ITS PLACE (the owner, 2026-10-22: "once you hit next on the item before it, it opens up, then you hit next it goes
  // to next, no jumping around"): open the row above it, and Next opens the urgent row, then the row below it
  const marked = (cls) => page.$eval(`[data-tq-rail] .tq-pile-row.${cls}`, (r) => r.getAttribute("data-tq-key")).catch(() => null);
  const onTable = (k) => page.waitForFunction((key) => document.querySelector("[data-tq-rail] .tq-pile-row.current")?.getAttribute("data-tq-key") === key
    && !document.querySelector(".tq-typing"), { timeout: 60000 }, k).catch(async () => assert.fail(`${k} never went on the table: current ${await marked("current")}`));
  const pressNext = () => page.evaluate(() => {
    const b = [...document.querySelectorAll("button")].find((n) => n.textContent.trim() === "Next" && !n.disabled);
    if (!b) throw new Error("no enabled Next"); b.click();
  });
  const walk = after.filter((r) => r.level === "task").map((r) => r.key), at = walk.indexOf(mid.key);
  await page.click(`[data-tq-rail] .tq-pile-row[data-tq-key="${walk[at - 1]}"] .card`);
  await onTable(walk[at - 1]);
  await page.waitForFunction((k) => document.querySelector("[data-tq-rail] .tq-pile-row.next")?.getAttribute("data-tq-key") === k, { timeout: 30000 }, mid.key)
    .catch(async () => assert.fail(`the row above the urgent one did not mark it Next: next ${await marked("next")}`));
  await pressNext(); await onTable(mid.key);
  await page.waitForFunction((k) => document.querySelector("[data-tq-rail] .tq-pile-row.next")?.getAttribute("data-tq-key") === k, { timeout: 30000 }, walk[at + 1])
    .catch(async () => assert.fail(`after the urgent row Next is not the row below it: next ${await marked("next")}`));
  await pressNext(); await onTable(walk[at + 1]);

  // REPORTS OLDEST FIRST, today's brief aside (it leads Reports)
  const reports = after.filter((r) => r.level === "reports" && byKey[r.key] && !byKey[r.key].brief_today).map((r) => byKey[r.key]);
  assert.ok(reports.length >= 2, `the demo rail has reports to order: ${JSON.stringify(after)}`);
  const times = reports.map((i) => stamp(i.arrived_at || i.sort_at || i.since || i.when));
  assert.deepEqual(times, [...times].sort((a, b) => a - b), `reports are not oldest first: ${JSON.stringify(reports.map((i) => [i.title, i.arrived_at]))}`);
  assert.deepEqual(errors, []);
});
