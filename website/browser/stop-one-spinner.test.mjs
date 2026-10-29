import assert from "node:assert/strict";
import test from "node:test";

import { startHarness } from "./harness.mjs";

/* ONE PRESS OF STOP, ONE WRITE-UP, ONE INDICATOR (the owner, 2026-10-29: Stop on the Agent pane's strip showed two spinners, as if the
   wrap-up ran twice). It ran once - the page drew Close out's pending box, a spinner by its heading and a bar at its foot, in the section
   the press had left. Now the Agent pane, where Stop was pressed, holds one line with one spinner, and Close out none. On the demo world's
   live agent; the /wrap the press posts is answered here (the demo refuses writes) and counted. */
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

test("Stop on a live agent's strip: one /wrap, one spinner, in the Agent pane", { timeout: 300000 }, async (t) => {
  const hz = await startHarness();
  t.after(() => hz.close());
  const page = await hz.newPage();
  const errors = [], wraps = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.setViewport({ width: 1440, height: 900, deviceScaleFactor: 1 });
  const guard = page.fixtureRequestGuard;
  page.off("request", guard);
  page.on("request", (r) => {
    if (r.method() === "POST" && /\/wrap$/.test(new URL(r.url()).pathname)) {
      wraps.push(new URL(r.url()).pathname);
      return r.respond({ status: 200, contentType: "application/json", body: JSON.stringify({ wrap: "started", job: "fixture-stop" }) });
    }
    guard(r);
  });
  await page.goto(hz.ui, { waitUntil: "domcontentloaded" });
  await page.waitForSelector("[data-tq-rail] .tq-pile-row", { timeout: 30000 });
  const tasks = (await (await fetch(`${hz.fixtureApi}/api/tasks`, { headers: { "X-Taskuary-Token": hz.token } })).json()).data;
  const live = tasks.find((x) => /census sync fails/.test(x.Title));
  assert.ok(live, "the demo world has a live agent");
  await page.evaluate((id) => { location.hash = `task=${id}`; }, live.TaskId);
  await page.waitForSelector("[data-tq-strip-stop]", { timeout: 20000 });
  await sleep(1000);
  await page.$eval("[data-tq-strip-stop]", (b) => { b.click(); b.click(); });
  await page.waitForSelector("[data-tq-writeup=pending]", { timeout: 10000 });
  // ...read over a few seconds: the page settles under the press (the detail reloads, the sections are read again)
  for (let i = 0; i < 6; i++) {
    const s = await page.evaluate(() => {
      const vis = (e) => e.getClientRects().length > 0 && getComputedStyle(e).visibility !== "hidden";
      const where = (e) => e.closest("[data-tq-slot]")?.getAttribute("data-tq-slot") || "?";
      return { spin: [...document.querySelectorAll(".MuiCircularProgress-root,.MuiLinearProgress-root")].filter(vis).map(where),
        lines: [...document.querySelectorAll("[data-tq-writeup]")].filter(vis).map((e) => `${where(e)}:${e.getAttribute("data-tq-writeup-at") || "box"}`),
        open: document.querySelector("[data-tq-slot][data-tq-open]")?.getAttribute("data-tq-slot") };
    });
    assert.deepEqual(s, { spin: ["agent"], lines: ["agent:result"], open: "agent" }, `one indicator, in the Agent pane (read ${i})`);
    await sleep(500);
  }
  assert.deepEqual(wraps, [`/api/tasks/${live.TaskId}/wrap`], "one press, one write-up");
  assert.deepEqual(errors, []);
});
