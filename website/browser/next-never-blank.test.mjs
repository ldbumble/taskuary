import assert from "node:assert/strict";
import test from "node:test";
import { boot, clickRow, doVerb, sleep } from "./walkdriver.mjs";

/* NEVER A BLANK CANVAS BETWEEN TWO ITEMS (the owner, 2026-10-30: "i clicked not a task on the last task on the tasks section ... nothing shows
   ... until the first 4 of the fyi come onto the canvas? add a ... to ensure user knows things are moving"): the next item drawn ahead but held
   for the press's answer drew nothing at all. On the demo world, reports read so a handful of FYIs comes next: from the press until the batch
   lands, the canvas holds the dots or the next item, every frame. */
test("Not a task on the last task: the dots stand until the FYIs land", { timeout: 200000 }, async (t) => {
  const { h, page, errors } = await boot(t, { width: 1440, height: 900 });
  const api = (p, body) => fetch(`${h.fixtureApi}${p}`, { method: body ? "POST" : "GET", headers: { "X-Taskuary-Token": h.token, "Content-Type": "application/json" },
    ...(body ? { body: JSON.stringify(body) } : {}) }).then((r) => r.json());
  for (const i of (await api("/api/funnel/pile")).items.filter((x) => x.lane === "report" || x.kind === "report" || x.kind === "dashboard"))
    await api("/api/funnel/settle", { key: i.key, verb: "done" });
  await page.reload({ waitUntil: "domcontentloaded" }); await page.waitForSelector("[data-tq-rail] .tq-pile-row", { timeout: 40000 }); await sleep(2500);
  const keys = await page.$$eval('[data-tq-run="task"] .tq-pile-row[data-tq-key]', (els) => els.map((e) => e.getAttribute("data-tq-key")));
  await clickRow(page, keys.at(-1)); await sleep(3500);
  const look = () => page.evaluate(() => {
    const vis = (e) => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0 && r.top < innerHeight && r.bottom > 0; };
    const live = [...document.querySelectorAll(".tq-live-card")].filter(vis).pop();
    const shown = !!live && vis(live) && live.innerText.replace(/\s+/g, " ").trim().length > 20;
    return { item: shown, dots: [...document.querySelectorAll(".tq-typing")].some(vis), fyi: shown && /nothing to decide/.test(live.innerText) };
  });
  doVerb(page, "nat").catch(() => {});
  const blank = [];
  for (let i = 0, t0 = Date.now(); i < 60; i++) {
    const s = await look();
    if (!s.item && !s.dots) blank.push(Date.now() - t0);
    if (s.fyi && s.item) break;
    await sleep(100);
  }
  assert.deepEqual(blank.filter((ms) => ms > 250), [], `the canvas stood blank at ${blank.join(", ")} ms`);
  assert.deepEqual(errors, []);
});
