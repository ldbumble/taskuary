import assert from "node:assert/strict";
import test from "node:test";
import { startHarness } from "./harness.mjs";

// THE LATEST RUN'S REPORT FIRST, EVERY EARLIER ONE UNDER IT (the owner, 2026-10-29): a task whose agent ran twice showed only the newest
// run's Result at rest - the first run's report was on the page nowhere, three presses deep behind Replay and More. Now the earlier run
// is a line under the latest report (when, which agent, what came of it) that opens in place. Invented repository and people.
const LATEST = /Census sync no longer stops on a site with no manager\./, EARLIER = "Found where the census run stops; no fix yet.";

test("a task with two runs: the latest report on top, the earlier one listed below it, and it opens in place", { timeout: 180000 }, async (t) => {
  const harness = await startHarness();
  t.after(() => harness.close());
  const page = await harness.newPage();
  await page.setViewport({ width: 1366, height: 900 });
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(harness.ui, { waitUntil: "domcontentloaded", timeout: 20000 });
  await page.waitForSelector("[data-tq-rail] .tq-pile-row", { timeout: 30000 });
  const made = await page.evaluate(async () => (await fetch("/api/fixture/task/coding-saved", { method: "POST", body: JSON.stringify({ mine: true, twice: true }),
    headers: { "X-Taskuary-Token": localStorage.getItem("taskuary_token"), "Content-Type": "application/json" } })).json());
  assert.ok(made.taskId, JSON.stringify(made));
  await page.evaluate((id) => { location.hash = `task=${id}`; }, made.taskId);
  await page.waitForSelector("[data-tq-work] [data-tq-result-summary]", { visible: true, timeout: 20000 });
  await page.waitForSelector("[data-tq-result-summary] [data-tq-runs-before] [data-tq-run-before]", { visible: true, timeout: 20000 })
    .catch(async () => assert.fail(`no earlier run under the latest report: ${await page.$eval("[data-tq-work]", (w) => w.innerText)}`));

  const at = await page.evaluate(() => {
    const sum = document.querySelector("[data-tq-result-summary]"), did = sum.querySelector("[data-tq-result-did]"), list = sum.querySelector("[data-tq-runs-before]");
    return { did: did?.innerText || "", rows: [...list.querySelectorAll("[data-tq-run-before]")].map((r) => [r.getAttribute("data-tq-run-before"), r.innerText]),
      below: !!(did && did.compareDocumentPosition(list) & Node.DOCUMENT_POSITION_FOLLOWING), head: list.innerText.split("\n")[0] };
  });
  assert.match(at.did, LATEST, "the latest run's report leads");
  assert.ok(at.below, "the earlier run is under the latest report");
  assert.match(at.head, /Earlier runs · 1/i);
  assert.equal(at.rows.length, 1, `one earlier run: ${JSON.stringify(at.rows)}`);
  assert.equal(at.rows[0][0], "1");
  assert.match(at.rows[0][1], /Run 1 · \d{4}-\d\d-\d\d \d\d:\d\d · codex/, "when and which agent");
  assert.ok(at.rows[0][1].includes(EARLIER), `its one-line outcome: ${at.rows[0][1]}`);
  assert.doesNotMatch(at.rows[0][1], /no fix yet[\s\S]*The run stops/, "folded to its line");

  // ...it opens in place, to its own report - what happened, and its last message behind its own More
  await page.click("[data-tq-run-before='1'] [role=button]");
  await page.waitForFunction((e) => /what happened\s+/i.test(document.querySelector("[data-tq-run-before='1']")?.innerText || "")
    && document.querySelector("[data-tq-run-before='1']").innerText.includes(e), { timeout: 10000 }, EARLIER)
    .catch(async () => assert.fail(`the earlier run did not open: ${await page.$eval("[data-tq-run-before='1']", (e) => e.innerText)}`));
  assert.equal(await page.$eval("[data-tq-run-before='1'] [role=button]", (b) => b.getAttribute("aria-expanded")), "true");
  const more = await page.$("[data-tq-run-before='1'] button");
  await more.click();
  await page.waitForFunction(() => /The run stops at the first site with no manager/.test(document.querySelector("[data-tq-run-before='1']")?.innerText || ""), { timeout: 10000 });
  assert.match(await page.$eval("[data-tq-result-did]", (e) => e.innerText), LATEST, "the latest report still leads");
  assert.deepEqual(errors, []);
});
