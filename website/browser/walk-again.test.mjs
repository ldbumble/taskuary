import assert from "node:assert/strict";
import { mkdir, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import { startHarness } from "./harness.mjs";
import { note, record } from "./recorder.mjs";

/* THE WAY TO WALK AGAIN IS ON THE BAR (the owner, 2026-11-10, on the desk after a walk went through everything with one task still open: "where
   is the button to start over?" - the bar held only Back). The demo world: walk it from the day card to its end by the bar's Next, then read
   the bar - the walk's again beside Back while the rail holds anything, never Back alone (rules part 4: no dead ends). Recorded. */
const out = path.join(process.env.TEMP || os.tmpdir(), "claude", "n17");
const barButtons = (page) => page.evaluate(() => [...document.querySelectorAll("[data-tq-row] button")]
  .filter((b) => b.getBoundingClientRect().width > 0 && getComputedStyle(b).visibility !== "hidden").map((b) => ({ text: b.innerText.trim(), off: b.disabled })));
const press = (page, re) => page.evaluate((src) => { const b = [...document.querySelectorAll("button")].find((x) => new RegExp(src).test(x.innerText.trim()) && !x.disabled
  && x.getBoundingClientRect().width > 0); b?.click(); return !!b; }, re);

test("at the end of a walk with tasks still open, the bar offers the walk again beside Back", { timeout: 600000 }, async (t) => {
  const h = await startHarness();
  t.after(() => h.close());
  const page = await h.newPage();
  await page.setViewport({ width: 1600, height: 900 });
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  const reqs = [];
  page.on("request", (r) => { const u = new URL(r.url()); if (u.pathname.startsWith("/api/") && r.method() !== "GET") reqs.push(`${Date.now()} ${r.method()} ${u.pathname} ${(r.postData() || "").slice(0, 120)}`); });
  await page.goto(h.ui, { waitUntil: "domcontentloaded" });
  const name = process.env.N17_NAME || "walk-again", dir = path.join(out, "video", name); await mkdir(dir, { recursive: true });
  await page.waitForFunction(() => [...document.querySelectorAll("button")].some((b) => /^Walk me through my tasks/.test(b.innerText.trim())), { timeout: 60000 });
  assert.ok(await press(page, "^Walk me through my tasks"), "the day card's walk");
  let rec = null, bar = [], end = false;
  for (let i = 0; i < 80 && !end; i++) {
    await page.waitForFunction(() => [...document.querySelectorAll("[data-tq-row] button")].some((b) => /^(Next|All read, next)/.test(b.innerText.trim()) && !b.disabled)
      || /you're clear|1 to go|to go, then/.test(document.body.innerText), { timeout: 20000, polling: 200 }).catch(() => {});
    await new Promise((r) => setTimeout(r, 400));
    bar = await barButtons(page);
    if (!bar.some((b) => /^(Next|All read, next)/.test(b.text) && !b.off)) { end = true; break; }
    if (!rec && i > 0) rec = await record(page, dir);
    await press(page, "^(Next|All read, next)");
  }
  if (!rec) rec = await record(page, dir);
  // ...each step after the end, kept with what the bar held: a step that does not come is the finding
  const steps = [], barNow = async () => (await barButtons(page)).map((b) => b.text + (b.off ? " (off)" : "")).join(" | ");
  const step = async (said, re) => { const ok = await page.waitForFunction((re) => [...document.querySelectorAll("[data-tq-row] button")]
      .some((b) => new RegExp(re).test(b.innerText.trim()) && !b.disabled), { timeout: 30000, polling: 200 }, re).then(() => true, () => false);
    steps.push(`${ok ? "ok" : "MISSING"} - ${said}: ${await barNow()}`); return ok; };
  let ok = false;
  try {
    await new Promise((r) => setTimeout(r, 2500));
    bar = await barButtons(page);
    // the end: the walk again beside Back, and BACK LIT, to the last row the walk was on (the owner, 2026-11-09: Back is any task you were on) -
    // it was greyed there, the bar's one button pressing nothing
    ok = end && await step("the end: the walk again on the bar", "^Walk me through my tasks") && await step("the end: Back lit", "^Back$");
    await page.screenshot({ path: path.join(out, `${name}.png`) });
    ok = ok && await press(page, "^Back$") && await step("Back: the last row on the table again, its way on", "^(Next|All read, next)");
    // ...and the end's walk again gone from the bar once that row is back: it stood there greyed beside Back and Next (the recorded walk, 2026-11-10)
    if (ok) { await new Promise((r) => setTimeout(r, 2000)); const left = (await barButtons(page)).filter((b) => /^Walk me through my tasks/.test(b.text));
      steps.push(`${left.length ? "STALE" : "ok"} - the walk again gone from the bar under the row: ${await barNow()}`); ok = !left.length; }
    ok = ok && await press(page, "^(Next|All read, next)") && await step("on from it: the end again", "^Walk me through my tasks");
    if (ok) await new Promise((r) => setTimeout(r, 1500));          // ...pressed as a person does, once the end has drawn
    ok = ok && await press(page, "^Walk me through my tasks") && await step("the walk again: the first row, its Next", "^(Next|All read, next)");
  } finally {
    await page.screenshot({ path: path.join(out, `${name}-end.png`) });
    await rec.stop();
    await writeFile(path.join(dir, "server.log"), h.backend.output());
    await writeFile(path.join(dir, "requests.txt"), reqs.join("\n"));
    await note(dir, { done: "The demo world: the day card's walk, then the bar's Next until it is gone - the walk at its end, tasks still on the rail; then Back, Next, and the walk again.",
      expect: "At the end, on the bar: Back (lit, to the last row walked) and Walk me through my tasks - never Back alone. Back brings the last row back; Next ends again; the walk again starts at the top.",
      saw: steps.join("\n") || "the walk never reached its end", verdict: ok ? "PASS" : "FAIL" });
  }
  assert.ok(ok, steps.join("\n"));
  assert.deepEqual(errors, []);
});
