import assert from "node:assert/strict";
import { mkdir } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import { startHarness } from "./harness.mjs";
import { note, record } from "./recorder.mjs";

/* WHAT THE DEMO'S CODING ROW SAYS IS WHAT ITS CHAT SHOWS (the walk audit, 2026-11-10): the issue's row read "agent waiting on you" over a chat
   that showed only the issue - its replayed run typed to a screen nobody saw. The tour sends people there ("read its run"). Opened once the
   replay has stopped: its steps and words in the chat, and the question the row waits on, on the chat's card. */
const out = path.join(process.env.TEMP || os.tmpdir(), "claude", "n17");
test("the demo's coding task shows the run and the question its row says it waits on", { timeout: 300000 }, async (t) => {
  const h = await startHarness();
  t.after(() => h.close());
  const page = await h.newPage();
  await page.setViewport({ width: 1600, height: 900 });
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  const name = process.env.N17_NAME || "demo-coding-row", dir = path.join(out, "video", name); await mkdir(dir, { recursive: true });
  await page.goto(h.ui, { waitUntil: "domcontentloaded" });
  const tid = await page.waitForFunction(async () => {
    const r = await fetch("/api/tasks?limit=200", { headers: { "X-Taskuary-Token": localStorage.getItem("taskuary_token") } }).then((x) => x.json()).catch(() => null);
    return (r?.data || r?.tasks || []).find?.((x) => /importers#214/.test(x.Title))?.TaskId || null;
  }, { timeout: 60000, polling: 500 }).then((x) => x.jsonValue());
  await page.evaluate((id) => { location.hash = `task=${id}`; }, tid);
  const rec = await record(page, dir);
  let seen = null;
  try {
    // ...the replay types for about 12 s, then waits
    seen = await page.waitForFunction(() => {
      const pane = document.querySelector("[data-tq-task-page]"), vp = pane?.querySelector(".tq-aui-viewport");
      const asks = vp?.querySelector("[data-tq-asking]")?.innerText || "";
      return asks && /waiting on you/i.test(pane.innerText) ? { asks, text: vp.innerText, ran: [...vp.querySelectorAll("[data-tq-ran]")].map((e) => e.innerText).join(" | ") } : null;
    }, { timeout: 60000, polling: 300 }).then((x) => x.jsonValue()).catch(() => null);
    await new Promise((r) => setTimeout(r, 1500));
  } finally {
    await page.screenshot({ path: path.join(out, `${name}.png`) });
    await rec.stop();
    const text = await page.evaluate(() => document.querySelector("[data-tq-task-page]")?.innerText || "");
    await note(dir, { done: "The demo world; the coding issue northwind/importers#214 opened while its replayed agent runs, watched until it waits.",
      expect: "The run's steps and words in the chat, then the question it waits on (Push it to a branch...?) on the chat's card - with the row's 'agent waiting on you'.",
      saw: seen ? `the question: ${seen.asks.slice(0, 120)}; head: ${seen.ran}` : `no question on the chat within 60 s:\n${text.slice(-500)}`, verdict: seen ? "PASS" : "FAIL" });
  }
  assert.ok(seen, "the question the row waits on stands on the chat");
  assert.match(seen.text, /census_sync\.py/, "the run's steps are in the chat");
  // ...and its head says how long it ran - the seconds it typed for, never the hours between the issue and the demo opening
  assert.match(seen.ran, /ran \d+s(?!\w)/, `the turn's head: ${seen.ran}`);
  assert.deepEqual(errors, []);
});
