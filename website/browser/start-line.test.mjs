import assert from "node:assert/strict";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import { startHarness } from "./harness.mjs";
import { note, record } from "./recorder.mjs";

/* A START NOBODY TYPED OPENS ITS CHAT AS WHAT STARTED IT (the owner, 2026-11-18 on a routine's run, 2026-11-19 on a report's): the box wore
   "Routine · ..." or "Report · ..." and the chat began with the agent's turn. The run stands at the top as an input, named, with what the
   agent was asked - above its turn. Invented people only. */
const out = path.join(process.env.TEMP || os.tmpdir(), "claude", "start-line", process.env.START_LINE_NAME || "after");

test("a routine's run and a report's run open their chat on what started them", { timeout: 300000 }, async (t) => {
  const h = await startHarness({ fresh: true }); t.after(() => h.close());
  const post = (p, body) => fetch(`${h.fixtureApi}${p}`, { method: "POST", headers: { "Content-Type": "application/json", "X-Taskuary-Token": h.token }, body: JSON.stringify(body) }).then((r) => r.json());
  await post("/api/setup/first-run/ai", { name: "claude" }); await post("/api/setup/dismiss", { dismissed: true });
  const errors = [];
  for (const [k, head, asked, said] of [["routine", "From the routine Weekly post drafts", "Draft three posts about this week at Northwind", "Three drafts are ready"],
                                        ["report", "From the report Late invoices check", "Find out why the two Payworth invoices are past due", "Both invoices wait"]]) {
    const made = await post("/api/fixture/started-run", { routine: k === "routine" });
    const page = await h.newPage(); page.on("pageerror", (e) => errors.push(`${k}: ${e.message}`));
    await page.setViewport({ width: 1280, height: 860 });
    const rec = await record(page, path.join(out, k));
    await page.goto(h.ui, { waitUntil: "domcontentloaded" });
    await page.evaluate((id) => { location.hash = `task=${id}`; }, made.taskId);
    await page.waitForFunction((w) => (document.querySelector("[data-tq-task-page] .tq-aui-viewport")?.innerText || "").includes(w), { timeout: 60000, polling: 100 }, said);
    await new Promise((r) => setTimeout(r, 2500));
    const text = await page.evaluate(() => document.querySelector("[data-tq-task-page] .tq-aui-viewport")?.innerText || "");
    await page.screenshot({ path: path.join(out, `${k}.png`) });
    await rec.stop();
    const at = text.indexOf(head), turn = text.indexOf(said);
    await note(path.join(out, k), { done: `opened the task a ${k}'s run started, its agent's first turn done`,
      expect: `"${head}" with "${asked}" at the top of the chat, above the agent's turn`, saw: text.slice(0, 600), verdict: at >= 0 && at < turn ? "pass" : "FAIL" });
    assert.ok(at >= 0 && at < turn && text.includes(asked), `${k}: the chat does not open on what started it:\n${text.slice(0, 600)}`);
    await page.close();
  }
  assert.deepEqual(errors, []);
});
