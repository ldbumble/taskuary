import assert from "node:assert/strict";
import test from "node:test";

import { startHarness } from "./harness.mjs";

/* A BLANK LEFT IN A DRAFT (the owner, 2026-10-30): Send pressed over a "[REASON]" refuses, says "Fill in [REASON] first" under the
   button on Close out, and the draft box marks the blank - nothing is posted. Filled in, the line and the mark go, and Send sends.
   A gateway's "[External]" tag is no blank: it is never marked. */
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

test("Send on Close out refuses over a blank, marks it, and sends once it is filled in", { timeout: 300000 }, async (t) => {
  const harness = await startHarness();
  t.after(() => harness.close());
  const page = await harness.newPage();
  await page.setViewport({ width: 1600, height: 810, deviceScaleFactor: 1 });
  const errors = [], posted = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.off("request", page.fixtureRequestGuard);
  page.on("request", (req) => {
    if (req.method() === "POST" && /^\/api\/reviews\/\d+\/decide$/.test(new URL(req.url()).pathname)) {
      posted.push(JSON.parse(req.postData() || "{}"));
      return req.respond({ status: 200, contentType: "application/json",
        body: JSON.stringify({ ok: false, status: "pending", sent: null, send_error: "the mailbox refused it" }) });
    }
    page.fixtureRequestGuard(req);
  });
  await page.goto(harness.ui, { waitUntil: "domcontentloaded", timeout: 20000 });
  await page.waitForSelector("[data-tq-rail] .tq-pile-row", { timeout: 30000 });
  const tasks = (await (await fetch(`${harness.fixtureApi}/api/tasks`, { headers: { "X-Taskuary-Token": harness.token } })).json()).data;
  const inv = tasks.find((x) => /^Invoice 88213/.test(x.Title));
  assert.ok(inv, "the demo's invoice reply, a draft waiting for Send");
  await page.evaluate((id) => { location.hash = `task=${id}`; }, inv.TaskId);
  await page.waitForSelector(`[data-tq-task-page="${inv.TaskId}"] [data-tq-closeout] textarea[data-tq-draft]`, { timeout: 20000 });
  await sleep(1500);
  const box = "[data-tq-closeout] textarea[data-tq-draft]";
  const write = async (text) => {
    await page.click(box); await page.keyboard.down("Control"); await page.keyboard.press("a"); await page.keyboard.up("Control");
    await page.keyboard.press("Backspace"); await page.type(box, text);
  };
  const press = () => page.evaluate(() => {
    const b = [...document.querySelectorAll("[data-tq-closeout] button")].find((x) => /^Send\b/.test(x.textContent.trim()) && !x.disabled && x.offsetParent);
    if (!b) return false; b.click(); return true;
  });
  const marks = () => page.$$eval("[data-tq-closeout] mark[data-tq-blank]", (ms) => ms.map((m) => m.textContent));

  await write("Re: [External] invoice - we can't pay it on Friday because [REASON].");
  await page.waitForFunction(() => document.querySelectorAll("[data-tq-closeout] mark[data-tq-blank]").length === 1, { timeout: 5000 });
  assert.deepEqual(await marks(), ["[REASON]"], "the blank is marked in the box, the mail tag is not");
  // the mark lies on the words it marks: inside the box, on its first line
  const [m, ta] = await page.evaluate((sel) => [document.querySelector("[data-tq-closeout] mark[data-tq-blank]"), document.querySelector(sel)]
    .map((e) => { const r = e.getBoundingClientRect(); return { l: r.left, t: r.top, r: r.right, b: r.bottom }; }), box);
  assert.ok(m.l >= ta.l && m.r <= ta.r && m.t >= ta.t && m.b <= ta.b, `the mark sits inside the box: ${JSON.stringify({ m, ta })}`);

  assert.ok(await press(), "Close out offers Send");
  await page.waitForSelector("[data-tq-closeout] [data-tq-fill-in]", { timeout: 5000 });
  assert.match(await page.$eval("[data-tq-closeout] [data-tq-fill-in]", (e) => e.textContent), /Fill in \[REASON\] first/);
  assert.equal(posted.length, 0, "nothing was posted over the blank");
  const picked = await page.$eval(box, (e) => e.value.slice(e.selectionStart, e.selectionEnd));
  assert.equal(picked, "[REASON]", "the cursor is on the blank");

  await write("Re: [External] invoice - we can't pay it on Friday because the PO is still open.");
  await page.waitForFunction(() => !document.querySelector("[data-tq-closeout] [data-tq-fill-in]"), { timeout: 5000 });
  assert.deepEqual(await marks(), [], "filled in, nothing is marked");
  assert.ok(await press(), "Send again, filled in");
  for (let i = 0; i < 20 && !posted.length; i++) await sleep(250);
  assert.equal(posted.length, 1, "the filled-in reply was posted");
  assert.match(String(posted[0].final_text || posted[0].reply_text || ""), /the PO is still open/);
  assert.deepEqual(errors, []);
});
