import assert from "node:assert/strict";
import test from "node:test";
import { startHarness } from "./harness.mjs";
import { quietWatch } from "./settle.mjs";

/* OPENING A TASK DOES NOT REBUILD THE RAIL BEHIND ITS OWN READS (speed round, 2026-11-18). The chat's "working changed" effect also ran on
   its first draw, when the list was already held: it said "answered" over nothing, and the task page answered with the rail's forced rebuild
   (every row, decorated), the task and the terminal again - two forced rail reads and three reads of the task to open one task. COUNTS, never time: a
   task opened from the rail reads the rail's rebuild once and its own detail once. */

test("opening a task forces the rail's rebuild once and reads the task once", { timeout: 180000 }, async (t) => {
  const h = await startHarness({ fresh: true }); t.after(() => h.close());
  const post = (p, body) => fetch(`${h.fixtureApi}${p}`, { method: "POST", headers: { "Content-Type": "application/json", "X-Taskuary-Token": h.token }, body: JSON.stringify(body) }).then((r) => r.json());
  await post("/api/setup/first-run/ai", { name: "claude" }); await post("/api/setup/dismiss", { dismissed: true });
  const made = await post("/api/fixture/mail-task", {});
  const page = await h.newPage(), errors = [], reads = [], quiet = quietWatch(page);
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("request", (r) => { const u = new URL(r.url()); if (r.method() === "GET") reads.push(u.pathname + u.search); });
  await page.setViewport({ width: 1600, height: 900 });
  await page.goto(h.ui, { waitUntil: "domcontentloaded" });
  await page.waitForSelector("[data-tq-rail] .tq-pile-row", { timeout: 60000 });
  await quiet();
  const at = reads.length;
  await page.evaluate((id) => { location.hash = `task=${id}`; }, made.taskId);
  await page.waitForSelector("[data-tq-task-page] .tq-aui-input", { visible: true, timeout: 60000 });
  await quiet();
  const since = reads.slice(at);
  const forced = since.filter((u) => u.startsWith("/api/funnel/pile") && u.includes("force=1")).length;
  // ...a read of the task with whatever it asks (its first says `opened`, a poll names its rev)
  const detail = since.filter((u) => u.split("?")[0] === `/api/tasks/${made.taskId}`);
  console.log(`# from the open until 2.5 s with no request: forced rail reads ${forced}; reads of the task ${detail.length}: ${detail.join(" | ")}`);
  assert.equal(forced, 1, `${forced} forced rail rebuilds to open one task: ${since.filter((u) => u.startsWith("/api/funnel/pile")).join(" | ")}`);
  assert.equal(detail.length, 1, `${detail.length} reads of the task to open it`);
  assert.deepEqual(errors, []);
});
