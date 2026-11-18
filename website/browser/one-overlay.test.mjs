import assert from "node:assert/strict";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import { startHarness } from "./harness.mjs";
import { note, record } from "./recorder.mjs";

/* ONE OVERLAY AT A TIME, A CLOSE IN SIGHT, TYPING WHERE HE CAN SEE IT (the 2026-11-18 walks: Search stayed open over a page that moved and took
   two instructions; "Report this bug" sat under Search taking every word; a picture's viewer swallowed "Post them..."). Recorded, frame by frame:
   Report this bug wears its close; Ctrl+K over it shuts it - one overlay; Search wears its close, and the page moving under it shuts it.
   (A picture's viewer handing a typed key to the box beneath is held by test/overlays.test.mjs.) Invented people. */
const out = path.join(process.env.TEMP || os.tmpdir(), "claude", "one-overlay");
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const shown = (page, sel) => page.evaluate((s) => [...document.querySelectorAll(s)].some((e) => getComputedStyle(e).visibility !== "hidden" && e.getBoundingClientRect().height > 0), sel);

test("one overlay at a time, each with its close, and a typed key goes to the box beneath", { timeout: 300000 }, async (t) => {
  const h = await startHarness({ fresh: true }); t.after(() => h.close());
  const api = (p, body) => fetch(`${h.fixtureApi}${p}`, { method: body ? "POST" : "GET", headers: { "Content-Type": "application/json", "X-Taskuary-Token": h.token },
    body: body && JSON.stringify(body) }).then((r) => r.json());
  await api("/api/setup/first-run/ai", { name: "claude" }); await api("/api/setup/dismiss", { dismissed: true });
  const { taskId } = await api("/api/fixture/task/picture-mail", {});   // a task to move the page to
  const page = await h.newPage(), errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.setViewport({ width: 1500, height: 900 });
  await page.goto(h.ui, { waitUntil: "domcontentloaded" });
  await sleep(4000);
  const rec = await record(page, out), saw = [];
  // 1. Report this bug: a close in sight; Ctrl+K over it shuts it - Search alone on screen
  await page.evaluate(() => window.dispatchEvent(new CustomEvent("tq-report-bug", { detail: null })));
  await sleep(1200);
  const bugUp = await shown(page, "#bug-report-title"), bugClose = await shown(page, "[data-tq-bug-close]");
  await page.keyboard.down("Control"); await page.keyboard.press("k"); await page.keyboard.up("Control");
  await sleep(1200);
  const both = { bug: await shown(page, "#bug-report-title"), search: await shown(page, "[data-tq-search] [role=dialog]") };
  saw.push(`bug report up ${bugUp}, its close ${bugClose}; after Ctrl+K: bug ${both.bug}, search ${both.search}`);
  // 2. Search's close in sight; the page moving under it shuts it
  const searchClose = await shown(page, "[data-tq-search-close]");
  await page.keyboard.type("snag");
  await page.evaluate((n) => { window.location.hash = `task=${n}`; }, taskId);
  await sleep(2500);
  const afterMove = await shown(page, "[data-tq-search] [role=dialog]");
  saw.push(`search close ${searchClose}; after the page moved to the task: search ${afterMove}`);
  await sleep(800);
  await rec.stop({ sheet: 12 });
  await note(out, { done: "Report this bug opened, Ctrl+K over it; Search's words, the page moved to a task",
    expect: "each overlay its close; one at a time; Search shut by the move",
    saw: saw.join("\n"), verdict: "see sheet.png" });
  console.log(saw.join("\n"));
  assert.deepEqual(errors, []);
  assert.ok(bugUp && bugClose, "Report this bug wears its close");
  assert.deepEqual(both, { bug: false, search: true }, "one overlay at a time");
  assert.ok(searchClose, "Search wears its close"); assert.equal(afterMove, false, "the page moving under it shuts it");
});
