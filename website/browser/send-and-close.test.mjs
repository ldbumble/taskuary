import assert from "node:assert/strict";
import test from "node:test";

import { startHarness } from "./harness.mjs";

/* CLOSE OUT HAS TWO SENDS (the owner, 2026-11-03: "when you send message through close out we need button send and close and send without
   closing so task stays open on send"). Send and close comes first and filled; Send beside it sends and leaves the task open, on the page.
   On a line too narrow for both, Send folds into the ▾ beside Send and close - never the other way round - and the line never wraps
   (2026-10-23). Invented people only. */
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const sends = (page, sel) => page.evaluate((sel) => {
  const box = document.querySelector(`${sel} [data-tq-closeout] [data-tq-two-sends]`);
  if (!box) return null;
  const bs = [...box.querySelectorAll(":scope > button")].filter((b) => b.offsetParent);
  return { mode: box.getAttribute("data-tq-two-sends"), words: bs.map((b) => b.textContent.trim()), tops: [...new Set(bs.map((b) => Math.round(b.getBoundingClientRect().top)))],
    filled: bs.filter((b) => b.classList.contains("MuiButton-contained")).map((b) => b.textContent.trim()),
    hover: Object.fromEntries(bs.map((b) => [b.textContent.trim(), b.title])), elsewhere: [...document.querySelectorAll(`${sel} button.MuiButton-contained`)].filter((b) => b.offsetParent && !box.contains(b)).map((b) => b.textContent.trim()), over: box.scrollWidth > box.clientWidth + 1 };
}, sel);

test("Close out: Send and close first and filled, Send beside it leaves the task open; narrow, Send folds into the ▾ and the line holds", { timeout: 300000 }, async (t) => {
  const harness = await startHarness();
  t.after(() => harness.close());
  const page = await harness.newPage();
  await page.setViewport({ width: 1600, height: 810, deviceScaleFactor: 1 });
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  const api = (p, body) => fetch(`${harness.fixtureApi}${p}`, { method: body ? "POST" : "GET", body: body && JSON.stringify(body),
    headers: { "X-Taskuary-Token": harness.token, "Content-Type": "application/json" } });
  // the demo sends nothing: the decide is answered as gone and recorded as sent (send-stays-on-closeout's road)
  let recorded = 0;
  page.off("request", page.fixtureRequestGuard);
  page.on("request", async (req) => {
    const rid = (new URL(req.url()).pathname.match(/^\/api\/reviews\/(\d+)\/decide$/) || [])[1];
    if (req.method() === "POST" && rid) {
      recorded = (await api(`/api/fixture/review/${rid}/sent`, {})).status;
      return req.respond({ status: 200, contentType: "application/json", body: JSON.stringify({ ok: true, status: "approved", sent: { channel: "email" }, send_error: null }) });
    }
    page.fixtureRequestGuard(req);
  });
  const tasks = (await (await api("/api/tasks")).json()).data;
  const inv = tasks.find((x) => /^Invoice 88213/.test(x.Title));
  assert.ok(inv, "the demo's invoice reply, a draft waiting in Close out");
  await page.goto(harness.ui, { waitUntil: "domcontentloaded", timeout: 20000 });
  await page.waitForSelector("[data-tq-rail] .tq-pile-row", { timeout: 30000 });
  await page.evaluate((id) => { location.hash = `task=${id}`; }, inv.TaskId);
  const sel = `[data-tq-task-page="${inv.TaskId}"]`;
  await page.waitForSelector(`${sel} [data-tq-closeout] [data-tq-two-sends]`, { timeout: 20000 });
  await sleep(1500);

  const wide = await sends(page, sel);
  assert.equal(wide.mode, "both", JSON.stringify(wide));
  assert.match(wide.words[0], /^Send and close\b/, `Send and close first: ${wide.words}`);
  assert.match(wide.words[1], /^Send\b(?! and close)/, `Send beside it: ${wide.words}`);
  // ...the primary is filled, unless the Advisor lit another of the draft's moves (its Redraft, on the spine): one filled button, never Send
  assert.ok(!wide.filled.some((w) => /^Send\b(?! and close)/.test(w)), `Send is not the filled one: ${JSON.stringify(wide)}`);
  assert.ok(wide.filled.some((w) => /^Send and close/.test(w)) !== wide.elsewhere.length > 0, `Send and close filled unless another move is lit: ${JSON.stringify(wide)}`);
  assert.equal(wide.tops.length, 1, "one line");
  assert.match(wide.hover[wide.words[0]], /then the task closes$/);
  assert.match(wide.hover[wide.words[1]], /the task stays open until you Mark done$/);

  // NARROW: the line holds, Send and close stays in view, and Send waits in the ▾ - its press there is the same Send
  for (const w of [600, 480, 390]) {
    await page.setViewport({ width: w, height: 800, deviceScaleFactor: 1 }); await sleep(900);
    const n = await sends(page, sel);
    t.diagnostic(`${w}px: ${n ? `${n.mode} ${n.words.join(" | ")}` : "Close out folded away"}`);
    if (!n) continue;                                    // a phone's page may fold Close out away behind its tab: nothing to measure there
    assert.equal(n.tops.length, 1, `${w}px: one line ${JSON.stringify(n)}`);
    assert.match(n.words[0], /^Send and close\b/, `${w}px: Send and close never folds ${JSON.stringify(n)}`);
    assert.ok(n.mode === "both" ? n.words.some((x) => /^Send\b(?! and close)/.test(x)) : n.words.includes("▾"), `${w}px: Send in view or in the ▾ ${JSON.stringify(n)}`);
  }
  await page.setViewport({ width: 1600, height: 810, deviceScaleFactor: 1 }); await sleep(1200);
  // ...and squeezed past what the three need (a narrow column beside an agent): Send folds into the ▾, the line holds, the ▾ holds Send
  const squeeze = (px) => page.evaluate((sel, px) => { document.querySelector(`${sel} [data-tq-closeout] [data-tq-two-sends]`).style.maxWidth = px; }, sel, px);
  await squeeze("150px"); await sleep(600);
  const tight = await sends(page, sel);
  t.diagnostic(`squeezed: ${tight.mode} ${tight.words.join(" | ")}`);
  assert.equal(tight.mode, "folded", JSON.stringify(tight));
  assert.match(tight.words[0], /^Send and close\b/, `Send and close never folds ${JSON.stringify(tight)}`);
  assert.ok(tight.words.includes("▾") && !tight.words.some((x) => /^Send\b(?! and close)/.test(x)), `Send is in the ▾ ${JSON.stringify(tight)}`);
  assert.equal(tight.tops.length, 1, "one line");
  await page.evaluate((sel) => document.querySelector(`${sel} [data-tq-send-more]`).click(), sel);
  await page.waitForSelector(".MuiMenu-paper [data-tq-verb$=':approve']", { timeout: 5000 });
  assert.match(await page.$eval(".MuiMenu-paper [data-tq-verb$=':approve']", (e) => e.textContent.trim()), /^Send\b(?! and close)/);
  await page.keyboard.press("Escape"); await sleep(400);
  await squeeze(""); await sleep(600);
  assert.equal((await sends(page, sel)).mode, "both", "with room again Send comes back out");

  // SEND, the plain one: the reply goes and the task stays open, on the page
  await page.evaluate((sel) => document.querySelector(`${sel} [data-tq-closeout] [data-tq-send=open]`).click(), sel);
  for (let i = 0; i < 20 && recorded !== 200; i++) await sleep(250);
  assert.equal(recorded, 200, "the reply went");
  for (let i = 0; i < 8; i++) {
    await sleep(500);
    assert.notEqual(String((await (await api(`/api/tasks/${inv.TaskId}`)).json()).task.Status), "done", "Send leaves the task open");
  }
  assert.ok(await page.$(sel), "still on the task's page");
  assert.deepEqual(errors, []);
});
