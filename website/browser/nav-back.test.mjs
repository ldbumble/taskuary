import assert from "node:assert/strict";
import test from "node:test";
import { boot, clickRow, doVerb, pressNext, rail, sleep } from "./walkdriver.mjs";

/* BACK GOES UP THE LINE (the owner, 2026-10-27: "We have a Next button - let's have a Back button that goes up the line as well. Basic nav.
   Of course on the first one no Back, like no Next on the last one. Combine Next/Back into one big pill called Nav"). On the demo world:
   Back brings up the rail's row above the one on the table - across sections the other way, past what a close put down - the ring moves
   with it, a double-click is one step, and the first row has no Back, the last no Next. */
const ON = () => {
  const v = [...document.querySelectorAll(".tq-canvas-live [data-tq-canvas-item]")].filter((x) => x.getBoundingClientRect().height > 0).pop();
  return v?.getAttribute("data-tq-canvas-item") || document.querySelector("[data-tq-rail] .tq-pile-row.current")?.getAttribute("data-tq-key") || "";
};
const on = (page) => page.evaluate(`(${ON})()`);
const ring = async (page) => (await rail(page)).find((r) => r.cur)?.key || "";
const nav = (page) => page.evaluate(() => {
  const g = document.querySelector(".tq-dock [data-tq-row] [data-tq-type=nav]");
  // ...on a desk Back is always on the bar, greyed where there is nowhere to go back to (the owner, 2026-10-29): a greyed Back is no Back
  return { label: g?.querySelector(".tq-cl-h")?.textContent || "", back: !!g?.querySelector("[data-tq-walk-back]:not([disabled])"), next: !!g?.querySelector("[data-tq-next]"),
    greyed: !!g?.querySelector("[data-tq-walk-back][disabled]"), words: [...(g?.querySelectorAll("button:not([disabled][data-tq-walk-back])") || [])].map((b) => b.textContent.trim()) };
});
const pressBack = (page) => page.evaluate(() => { const b = document.querySelector(".tq-dock [data-tq-row] [data-tq-walk-back]"); if (b && !b.disabled) { b.click(); return true; } return false; });
const until = async (f, ms = 15000) => { for (const t0 = Date.now(); Date.now() - t0 < ms; await sleep(200)) if (await f()) return true; return false; };
// the rail's walkable rows, top to bottom, with their section (For later is not on the walk's line)
const line = (page) => page.$$eval("[data-tq-rail] .tq-pile-row", (els) => els.map((r) => ({ key: r.getAttribute("data-tq-key"),
  run: r.closest("[data-tq-run]")?.getAttribute("data-tq-run") || "" })).filter((r) => r.key && r.run !== "later"));
const settle = async (page) => { await until(async () => (await nav(page)).words.length > 0); await sleep(2200); };

test("Back walks up the line: the row above, across sections, past what a close put down - and a double-click is one step", { timeout: 300000 }, async (t) => {
  const { page, errors } = await boot(t, { width: 1440, height: 900 });
  const rows = await line(page), tasks = rows.filter((r) => r.run === "task").map((r) => r.key);
  assert.ok(tasks.length >= 4, `the demo rail has tasks: ${JSON.stringify(rows)}`);

  await t.test("the first row: Nav with Next and no Back", async () => {
    await clickRow(page, rows[0].key); await settle(page);
    const n = await nav(page);
    assert.equal(n.label, "Nav"); assert.ok(n.next, "Next is there"); assert.ok(!n.back, `no Back on the first one: ${JSON.stringify(n)}`);
    assert.ok(n.greyed, `...its place kept, greyed (the owner, 2026-10-29) ${JSON.stringify(n)}`);
  });

  await t.test("Next, then Back: the row it came from, ringed on the rail", async () => {
    await clickRow(page, tasks[0]); await settle(page);
    assert.ok(await pressNext(page)); await until(async () => (await on(page)) === tasks[1]); await settle(page);
    assert.equal(await on(page), tasks[1], "Next walks down to the row below");
    const n = await nav(page);
    assert.deepEqual(n.words, ["Back", "Next"], "one pill: Back, then Next");
    assert.ok(await pressBack(page));
    assert.ok(await until(async () => (await on(page)) === tasks[0]), `Back brings up the row above: on ${await on(page)}`);
    assert.ok(await until(async () => (await ring(page)) === tasks[0]), "the rail's ring follows");
    await settle(page);
    assert.ok(await pressNext(page)); assert.ok(await until(async () => (await on(page)) === tasks[1]), "and Next goes back down to where it was");
    await settle(page);
  });

  await t.test("across sections: the first row under Tasks' last goes back to that last task", async () => {
    const now = await line(page), at = now.findIndex((r) => r.run !== "task" && r.run !== "later");
    if (at < 1) return t.skip("no row below Tasks on this rail");
    await clickRow(page, now[at].key); await settle(page);
    assert.ok(await pressBack(page));
    assert.ok(await until(async () => (await on(page)) === now[at - 1].key), `Back crosses into the section above: on ${await on(page)}, want ${now[at - 1].key}`);
    await settle(page);
  });

  await t.test("a double-click on Back is one step up", async () => {
    const now = (await line(page)).map((r) => r.key), i = Math.min(3, now.length - 1);
    await clickRow(page, now[i]); await settle(page);
    const b = await page.$(".tq-dock [data-tq-row] [data-tq-walk-back]");
    await b.click({ count: 2 });
    assert.ok(await until(async () => (await on(page)) === now[i - 1]), `one step: on ${await on(page)}`);
    await sleep(4000);
    assert.equal(await on(page), now[i - 1], `still one step up after the double-click: on ${await on(page)}`);
  });

  await t.test("Back skips a row Mark done put down, and never draws it again", async () => {
    const now = (await line(page)).filter((r) => r.run === "task").map((r) => r.key);
    await clickRow(page, now[1]); await settle(page);
    assert.ok(await doVerb(page, "done"), "Mark done on the second task");
    await sleep(5000);
    await clickRow(page, now[2]); await settle(page);
    await page.evaluate((gone) => { window.__seen = []; const tick = () => { const k = document.querySelector("[data-tq-canvas-item]") && [...document.querySelectorAll(".tq-canvas-live [data-tq-canvas-item]")].map((x) => x.getAttribute("data-tq-canvas-item")); if (k?.includes(gone)) window.__seen.push(gone); if (window.__seen.length < 50) requestAnimationFrame(tick); }; tick(); }, now[1]);
    assert.ok(await pressBack(page));
    assert.ok(await until(async () => (await on(page)) === now[0]), `Back went past the closed task: on ${await on(page)}`);
    await sleep(2500);
    assert.deepEqual(await page.evaluate(() => window.__seen), [], "the closed task was never drawn again");
  });
  assert.deepEqual(errors, []);
});

test("the last row has no Next and keeps its Back; the first has no Back", { timeout: 240000 }, async (t) => {
  const { h, page, errors } = await boot(t, { width: 1440, height: 900 });
  // a rail of tasks alone: every report and fyi read, so the bottom task is the walk's last
  const api = (path, method = "GET", body) => fetch(`${h.fixtureApi}${path}`, { method, headers: { "X-Taskuary-Token": h.token, "Content-Type": "application/json" },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }) }).then((r) => r.json());
  for (const i of (await api("/api/funnel/pile")).items.filter((x) => !x.tid)) await api("/api/funnel/settle", "POST", { key: i.key, verb: "done" });
  await page.reload({ waitUntil: "domcontentloaded" });
  await page.waitForSelector("[data-tq-rail] .tq-pile-row", { timeout: 40000 }); await sleep(2500);
  const rows = (await line(page)).map((r) => r.key);
  assert.ok(rows.length >= 2, `tasks left on the rail: ${rows}`);
  await clickRow(page, rows.at(-1)); await settle(page);
  assert.ok(await until(async () => !(await nav(page)).next, 8000), `the last one has no Next: ${JSON.stringify(await nav(page))}`);
  assert.ok((await nav(page)).back, "...and its Back");
  assert.ok(await pressBack(page));
  assert.ok(await until(async () => (await on(page)) === rows.at(-2)));
  await settle(page);
  assert.ok((await nav(page)).next, "one up from the last, Next is back");
  await clickRow(page, rows[0]); await settle(page);
  assert.deepEqual((await nav(page)).words, ["Next"], "the first one: Next alone");
  assert.deepEqual(errors, []);
});

// BACK FROM THE FIRST FYI IS THE LAST REPORT READ (trust audit F1, 2026-10-28): a report read leaves the rail, so Back from the first FYI
// batch skipped every report the walk had just shown and landed on the last task
test("Back from the first FYI batch brings up the last report read, not the last task", { timeout: 240000 }, async (t) => {
  const { page, errors } = await boot(t, { width: 1440, height: 900 });
  await page.evaluate(() => document.querySelector('[data-tq-section-head="reports"] .fold')?.click()); await sleep(1500);
  const last = await page.evaluate(() => [...document.querySelectorAll('[data-tq-run="reports"] .tq-pile-row[data-tq-key]')].at(-1)?.getAttribute("data-tq-key"));
  assert.ok(last, "the demo has reports");
  await clickRow(page, last); await settle(page);
  assert.ok(await pressNext(page));
  await page.waitForSelector('[data-tq-item-sections="fyis"]', { timeout: 20000 }); await settle(page);
  assert.ok((await nav(page)).back, "the first FYI batch has a Back");
  assert.ok(await pressBack(page));
  assert.ok(await until(async () => !!(await page.$('[data-tq-item-sections="report"], [data-tq-item-sections="dashboard"]'))),
    `Back brought up the report it came from: on ${await on(page)}`);
  assert.deepEqual(errors, []);
});
