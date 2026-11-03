import assert from "node:assert/strict";
import test from "node:test";
import { boot, clickRow, pressNext, sleep } from "./walkdriver.mjs";

/* NEXT ON THE LAST ROW (the owner, 2026-11-02: "You can't mark read on the final FYI?"). The rail down to one row, on the table: Next stood
   greyed there ("nothing below this one"), so a press did nothing - the FYI stayed unread, stayed on the rail, and the walk never ended.
   Next on the last row does what it does on any row (rule 4) and then the walk is over: an FYI or a report is read and leaves the rail at
   the press, a task stays on it - and the walk stands at its end, Walk again offered where anything is left. */
const until = async (f, ms = 15000) => { for (const t0 = Date.now(); Date.now() - t0 < ms; await sleep(25)) if (await f()) return Date.now() - t0; return -1; };
const shown = (page, k) => page.evaluate((k) => [...document.querySelectorAll(`[data-tq-rail] .tq-pile-row[data-tq-key="${k}"]`)].some((e) => e.getBoundingClientRect().height > 0), k);
// the walk's end over an empty rail: the day is done (concierge.end_turn's all_done)
const clear = (page) => () => page.$$eval(".tq-msg .body", (els) => els.some((e) => e.textContent.trim().startsWith("Nothing's waiting.")));
const row = (page) => page.evaluate(() => [...document.querySelectorAll(".tq-asst-col button")].filter((b) => b.offsetParent && !b.disabled).map((b) => b.textContent.trim()));

async function lastOne(t, keep) {
  const { h, page, errors } = await boot(t, { width: 1440, height: 900 });
  const api = (p, body, method) => fetch(`${h.fixtureApi}${p}`, { method: method || (body ? "POST" : "GET"), headers: { "X-Taskuary-Token": h.token, "Content-Type": "application/json" },
    ...(body ? { body: JSON.stringify(body) } : {}) }).then((r) => r.json());
  const items = (await api("/api/funnel/pile")).items, it = items.find(keep);
  assert.ok(it, "the demo has the row to keep");
  for (const i of items) if (i.key !== it.key) {
    if (i.tid && i.lane !== "report" && i.lane !== "fyi") await api(`/api/tasks/${i.tid}`, { Status: "done" }, "PATCH");
    else await api("/api/funnel/settle", { key: i.key, verb: "done" });
  }
  await page.reload({ waitUntil: "domcontentloaded" }); await page.waitForSelector("[data-tq-rail] .tq-pile-row", { timeout: 40000 }); await sleep(2500);
  const left = await page.$$eval("[data-tq-rail] .tq-pile-row[data-tq-key]", (els) => els.map((e) => e.getAttribute("data-tq-key")));
  assert.deepEqual(left, [it.key], "one row left on the rail");
  await clickRow(page, it.key); await sleep(3500);
  const pile = async () => api("/api/funnel/pile");
  return { h, page, errors, it, pile };
}

test("Next on the last FYI reads it, takes it off the rail at the press, and ends the walk", { timeout: 300000 }, async (t) => {
  const { page, errors, it, pile } = await lastOne(t, (i) => i.lane === "fyi");
  assert.ok(await pressNext(page), `Next is pressable on the last FYI: ${JSON.stringify(await row(page))}`);
  const gone = await until(async () => !(await shown(page, it.key)), 3000);
  console.log("last fyi off the rail after", gone, "ms");
  assert.ok(gone >= 0 && gone <= 300, `the last FYI stayed on the rail ${gone < 0 ? "3000+" : gone} ms after Next`);
  assert.ok(await until(async () => !(await pile()).items.some((i) => i.key === it.key), 10000) >= 0, "the server still has the FYI unread on the rail");
  assert.ok(await until(async () => (await pile()).walk?.ended === true || !(await pile()).walk?.on, 10000) >= 0, "the walk did not end");
  await sleep(2000);
  assert.ok(!(await shown(page, it.key)), "the FYI came back on the rail");
  assert.ok(await until(clear(page), 5000) >= 0, "the page never said the walk is over: nothing waiting");
  assert.deepEqual(errors, []);
});

test("Next on the last report reads it and ends the walk", { timeout: 300000 }, async (t) => {
  const { page, errors, it, pile } = await lastOne(t, (i) => i.lane === "report");
  assert.ok(await pressNext(page), `Next is pressable on the last report: ${JSON.stringify(await row(page))}`);
  const gone = await until(async () => !(await shown(page, it.key)), 3000);
  assert.ok(gone >= 0 && gone <= 300, `the last report stayed on the rail ${gone < 0 ? "3000+" : gone} ms after Next`);
  assert.ok(await until(async () => !(await pile()).items.some((i) => i.key === it.key), 10000) >= 0, "the server still has the report on the rail");
  assert.ok(await until(async () => (await pile()).walk?.ended === true || !(await pile()).walk?.on, 10000) >= 0, "the walk did not end");
  assert.ok(await until(clear(page), 5000) >= 0, "the page never said the walk is over: nothing waiting");
  assert.deepEqual(errors, []);
});

test("Next on the last task keeps it on the rail and ends the walk with Walk again", { timeout: 300000 }, async (t) => {
  const { page, errors, it, pile } = await lastOne(t, (i) => i.tid && i.lane !== "report" && i.lane !== "fyi");
  assert.ok(await pressNext(page), `Next is pressable on the last task: ${JSON.stringify(await row(page))}`);
  assert.ok(await until(async () => (await row(page)).includes("Walk me through my tasks"), 10000) >= 0, `the end offers the walk again: ${JSON.stringify(await row(page))}`);
  assert.ok((await pile()).items.some((i) => i.key === it.key), "a task Next passed stays on the rail (rule 4)");
  assert.ok(await shown(page, it.key), "the task left the rail");
  assert.ok((await pile()).walk?.ended === true || !(await pile()).walk?.on, "the walk did not end");
  assert.deepEqual(errors, []);
});
