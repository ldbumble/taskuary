import assert from "node:assert/strict";
import test from "node:test";

import { startHarness } from "./harness.mjs";

/* A CLOSE-OUT HAS THE SAME PAIR AS CLOSE OUT'S SENDS (the owner, 2026-11-03): the pull request's card in Close out - merge it, then send the
   reply - offers Approve and close first and filled, which closes the task once the reply went, and Approve beside it, which leaves the task
   open. The line never wraps: tight, Approve folds into the ▾ beside Approve and close (2026-10-23). GitHub is never reached - the card's read
   and its press are answered here. Invented people (fixture pr-closeout). */
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const pair = (page, sel) => page.evaluate((sel) => {
  const box = document.querySelector(`${sel} [data-tq-closeout] [data-tq-two-sends]`);
  if (!box) return null;
  const bs = [...box.querySelectorAll(":scope > button")].filter((b) => b.offsetParent);
  return { mode: box.getAttribute("data-tq-two-sends"), words: bs.map((b) => b.textContent.trim()), tops: [...new Set(bs.map((b) => Math.round(b.getBoundingClientRect().top)))],
    filled: bs.filter((b) => b.classList.contains("MuiButton-contained")).map((b) => b.textContent.trim()), off: bs.filter((b) => b.disabled).map((b) => b.textContent.trim()),
    hover: Object.fromEntries(bs.map((b) => [b.textContent.trim(), b.title])), over: box.scrollWidth > box.clientWidth + 1 };
}, sel);

test("a pull request's close-out: Approve and close first and filled, Approve beside it leaves the task open; tight, Approve folds", { timeout: 300000 }, async (t) => {
  const harness = await startHarness();
  t.after(() => harness.close());
  const page = await harness.newPage();
  await page.setViewport({ width: 1600, height: 810, deviceScaleFactor: 1 });
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  const api = (p, body) => fetch(`${harness.fixtureApi}${p}`, { method: body ? "POST" : "GET", body: body && JSON.stringify(body),
    headers: { "X-Taskuary-Token": harness.token, "Content-Type": "application/json" } });
  const made = [await (await api("/api/fixture/task/pr-closeout", {})).json(), await (await api("/api/fixture/task/pr-closeout", {})).json()];
  assert.ok(made.every((m) => m.taskId && m.closeout), JSON.stringify(made));
  const byCo = Object.fromEntries(made.map((m) => [String(m.closeout), m]));
  // GitHub says the pull request can merge; the press merges nothing and is answered as gone - both reviews recorded on the server, as a merge
  // and its reply leave them
  const pressed = [];
  page.off("request", page.fixtureRequestGuard);
  page.on("request", async (req) => {
    const path = new URL(req.url()).pathname, [, rid, what] = path.match(/^\/api\/reviews\/(\d+)\/(closeout|decide)$/) || [];
    if (rid && byCo[rid] && what === "closeout" && req.method() === "GET")
      return req.respond({ status: 200, contentType: "application/json", body: JSON.stringify({ state: "clean", ok: true, offers: [], note: "", reason: "" }) });
    if (rid && byCo[rid] && what === "decide" && req.method() === "POST") {
      for (const r of [byCo[rid].closeout, byCo[rid].reply]) await api(`/api/fixture/review/${r}/sent`, {});
      pressed.push(rid);
      return req.respond({ status: 200, contentType: "application/json", body: JSON.stringify({ ok: true, status: "approved", reply: { ok: true }, send_error: null }) });
    }
    page.fixtureRequestGuard(req);
  });
  const statusOf = async (id) => String((await (await api(`/api/tasks/${id}`)).json()).task.Status);
  await page.goto(harness.ui, { waitUntil: "domcontentloaded", timeout: 20000 });
  await page.waitForSelector("[data-tq-rail] .tq-pile-row", { timeout: 30000 });
  const open = async (id) => {
    await page.evaluate((id) => { location.hash = `task=${id}`; }, id);
    const sel = `[data-tq-task-page="${id}"]`;
    await page.waitForSelector(`${sel} [data-tq-closeout] [data-tq-two-sends]`, { timeout: 20000 });
    await page.waitForFunction((sel) => [...document.querySelectorAll(`${sel} [data-tq-closeout] [data-tq-two-sends] > button`)].some((b) => !b.disabled), { timeout: 20000 }, sel);
    await sleep(1200);
    return sel;
  };

  const [one, two] = made, sel = await open(one.taskId);
  const wide = await pair(page, sel);
  t.diagnostic(`wide: ${wide.mode} ${wide.words.join(" | ")}`);
  assert.equal(wide.mode, "both", JSON.stringify(wide));
  assert.deepEqual(wide.words.slice(0, 2), ["Approve and close", "Approve"], JSON.stringify(wide));
  assert.ok(wide.words.some((w) => /^Decline/.test(w)), `Decline stays: ${wide.words}`);
  assert.deepEqual(wide.filled, ["Approve and close"], `one filled, and it is Approve and close: ${JSON.stringify(wide)}`);
  assert.deepEqual(wide.off, [], JSON.stringify(wide));
  assert.equal(wide.tops.length, 1, "one line");
  assert.match(wide.hover["Approve and close"], /^Approve and close merges the pull request on GitHub, then sends your reply to .+ - then the task closes$/);
  assert.match(wide.hover.Approve, /^Approve merges the pull request on GitHub, then sends your reply to .+ - the task stays open until you Mark done$/);

  // TIGHT: the line holds, Approve and close stays in view, and Approve waits in the ▾ - its press there is the same Approve
  const squeeze = (px) => page.evaluate((sel, px) => { document.querySelector(`${sel} [data-tq-closeout] [data-tq-two-sends]`).style.maxWidth = px; }, sel, px);
  await squeeze("300px"); await sleep(600);
  const tight = await pair(page, sel);
  t.diagnostic(`squeezed: ${tight.mode} ${tight.words.join(" | ")}`);
  assert.equal(tight.mode, "folded", JSON.stringify(tight));
  assert.equal(tight.words[0], "Approve and close", `Approve and close never folds ${JSON.stringify(tight)}`);
  assert.ok(tight.words.includes("▾") && !tight.words.includes("Approve"), `Approve is in the ▾ ${JSON.stringify(tight)}`);
  await page.evaluate((sel) => document.querySelector(`${sel} [data-tq-send-more]`).click(), sel);
  await page.waitForSelector(".MuiMenu-paper [data-tq-verb$=':approve']", { timeout: 5000 });
  assert.equal(await page.$eval(".MuiMenu-paper [data-tq-verb$=':approve']", (e) => e.textContent.trim()), "Approve");
  await page.keyboard.press("Escape"); await sleep(400);
  await squeeze(""); await sleep(600);
  assert.equal((await pair(page, sel)).mode, "both", "with room again Approve comes back out");

  // APPROVE, the plain one: the merge and the reply go, and the task stays open, on the page
  await page.evaluate((sel) => document.querySelector(`${sel} [data-tq-closeout] [data-tq-send=open]`).click(), sel);
  for (let i = 0; i < 20 && !pressed.length; i++) await sleep(250);
  assert.deepEqual(pressed, [String(one.closeout)], "the close-out was pressed");
  for (let i = 0; i < 6; i++) { await sleep(500); assert.notEqual(await statusOf(one.taskId), "done", "Approve leaves the task open"); }
  assert.ok(await page.$(sel), "still on the task's page");

  // APPROVE AND CLOSE: the merge and the reply go, then the task closes
  const sel2 = await open(two.taskId);
  await page.evaluate((sel) => document.querySelector(`${sel} [data-tq-closeout] [data-tq-send=close]`).click(), sel2);
  let status = "";
  for (let i = 0; i < 40 && status !== "done"; i++) { await sleep(500); status = await statusOf(two.taskId); }
  assert.deepEqual(pressed, [String(one.closeout), String(two.closeout)]);
  assert.equal(status, "done", "Approve and close closed the task once the reply went");
  assert.equal(await statusOf(one.taskId), "open", "the first task is still open");
  assert.deepEqual(errors, []);
});
