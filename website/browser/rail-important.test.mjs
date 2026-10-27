import assert from "node:assert/strict";
import test from "node:test";

import { startHarness } from "./harness.mjs";

/* AN IMPORTANT TASK'S DOT IS RINGED, AS URGENT'S IS (the owner, 2026-10-27: "This is an important task but I don't see a bigger circle on
   the green dot like the red dot's larger thing on the task's time dot"). Important was the bare 8px dot in slate - read as the band's
   sage - and on the table the band's colour painted over it. It wears urgent's ring in its own slate, on the table too; regular stays
   the plain dot. */
async function request(h, path, method = "GET", body) {
  const response = await fetch(`${h.fixtureApi}${path}`, {
    method, headers: { "X-Taskuary-Token": h.token, "Content-Type": "application/json" },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
  assert.ok(response.ok, `${method} ${path}: ${response.status}`);
  return response.json();
}
const SLATE = "rgb(85, 105, 122)", RING = "rgba(85, 105, 122, 0.5)";

test("an important task's rail dot is ringed in slate, on the table too, and a regular one stays plain", { timeout: 240000 }, async (t) => {
  const harness = await startHarness();
  t.after(() => harness.close());
  const page = await harness.newPage();
  await page.setViewport({ width: 1366, height: 900 });
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(harness.ui, { waitUntil: "domcontentloaded", timeout: 20000 });
  await page.waitForSelector("[data-tq-rail] .tq-pile-row", { timeout: 30000 });

  const pile = await request(harness, "/api/funnel/pile");
  const tasks = (pile.items || []).filter((i) => i.tid && i.kind === "todo" &&String(i.priority || "regular").toLowerCase() !== "urgent");
  assert.ok(tasks.length >= 2, `the demo rail has tasks to mark: ${JSON.stringify((pile.items || []).map((i) => [i.kind, i.priority]))}`);
  const [imp, plain] = tasks;
  await request(harness, `/api/tasks/${imp.tid}`, "PATCH", { Priority: "important" });
  await request(harness, `/api/tasks/${plain.tid}`, "PATCH", { Priority: "regular" });
  const dot = (k) => page.evaluate((key) => {
    const i = document.querySelector(`[data-tq-rail] .tq-pile-row[data-tq-key="${key}"] .rail i`);
    return i ? { bg: getComputedStyle(i).backgroundColor, ring: getComputedStyle(i).boxShadow,
      current: i.closest(".tq-pile-row").classList.contains("current") } : null;
  }, k);
  const ringed = (k) => page.waitForFunction((key, slate, ring) => {
    const i = document.querySelector(`[data-tq-rail] .tq-pile-row[data-tq-key="${key}"] .rail i`);
    return i && getComputedStyle(i).backgroundColor === slate && getComputedStyle(i).boxShadow.includes(ring);
  }, { timeout: 30000 }, k, SLATE, RING).catch(async () => assert.fail(`the important row's dot is not ringed in slate: ${JSON.stringify(await dot(k))}`));

  await ringed(imp.key);
  const regular = await dot(plain.key);
  assert.ok(regular, "the regular row is on the rail");
  assert.ok(!regular.ring.includes(RING), `a regular row wears important's ring: ${JSON.stringify(regular)}`);
  assert.notEqual(regular.bg, SLATE, "a regular row's dot is slate");

  // ...and ON THE TABLE: the band's colour painted over it (the owner's screen was the task he had open)
  await page.click(`[data-tq-rail] .tq-pile-row[data-tq-key="${imp.key}"] .card`);
  await page.waitForFunction((k) => document.querySelector("[data-tq-rail] .tq-pile-row.current")?.getAttribute("data-tq-key") === k, { timeout: 30000 }, imp.key);
  await ringed(imp.key);
  assert.deepEqual(errors, []);
});
