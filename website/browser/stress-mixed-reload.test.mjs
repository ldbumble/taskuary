import assert from "node:assert/strict";
import test from "node:test";
import { bootMixed, clean, look, noBlank, oneTable, pressNext, shot, sleep, startWalk, still, type } from "./stress-mixed-lib.mjs";

/* MIXED USE 4 - F5 MID-WALK, MID-PRESS, AND OVER A SERVER RESTART (the owner, 2026-11-02: "no crazy stuff"). The page is reloaded on a row
   of the walk, while a Next is out (held 1500 ms), and after the server was stopped and started again on the same home. Each time the walk
   comes back where the server holds it (railwalk.on), the press that was out is applied at most once (the ring at most one row on), and no
   error banner is left standing once the server answers. */
const tasks = async (api) => (await api("/api/tasks")).data;
const reload = async (page) => {
  await page.reload({ waitUntil: "domcontentloaded" });
  await page.waitForSelector("[data-tq-rail] .tq-pile-row", { timeout: 40000 });
  await sleep(1500); await page.evaluate(() => window.__blanks.arm());
  return still(page, 30000);
};
const ringIndex = (s) => s.keys.indexOf(s.ring[0]);

test("a reload on a row, mid-press and over a server restart resumes the walk and applies nothing twice", { timeout: 480000 }, async (t) => {
  const { h, page, errors, api } = await bootMixed(t, { width: 1440, height: 900, delay: 1500 });
  await startWalk(page);
  for (let i = 0; i < 3; i++) { await pressNext(page); await still(page, 30000); }
  let s = await still(page), on = s.ring[0];
  assert.ok(on, "the walk stands on a row");

  // ON A ROW: the same row after F5
  s = await reload(page);
  if (s.ring[0] !== on) await shot(page, "reload-on-row");
  assert.equal(s.ring[0], on, `F5 on a row comes back to it ${JSON.stringify({ on, s })}`);
  oneTable(s, "after F5 on a row"); clean(errors, "after F5 on a row");

  // MID-PRESS: a Next out, F5 before it is back - the ring lands on the row or the one below, never two on, and on what the server holds
  const before = ringIndex(s), done0 = (await tasks(api)).filter((x) => x.Status === "done").length;
  await pressNext(page); await sleep(300);
  s = await reload(page);
  const held = (await api("/api/fixture/walk/keys", {})).on;
  assert.ok(ringIndex(s) - before <= 1 && ringIndex(s) >= before, `mid-press F5 moved the ring ${ringIndex(s) - before} rows ${JSON.stringify(s)}`);
  if (held && s.ring[0]) assert.equal(s.ring[0], held, "the page rings the row the server holds");
  assert.equal((await tasks(api)).filter((x) => x.Status === "done").length, done0, "a Next closed nothing");
  oneTable(s, "after F5 mid-press"); clean(errors, "after F5 mid-press");

  // MID-ASK: a typed close out, F5 before its answer is back - the task closes once, and the chat holds the exchange once, not twice
  const done1 = (await tasks(api)).filter((x) => x.Status === "done").length;
  await type(page, "mark it done"); await sleep(400);
  s = await reload(page); await sleep(2500);
  const done2 = (await tasks(api)).filter((x) => x.Status === "done").length;
  assert.ok(done2 - done1 <= 1, `a typed close and an F5 closed ${done2 - done1}`);
  const said = await page.$$eval(".tq-msg.you", (es) => es.map((e) => e.innerText.trim()).filter((x) => x === "mark it done").length);
  assert.ok(said <= 1, `the typed words are drawn ${said} times after F5`);
  oneTable(await still(page, 30000), "after F5 mid-ask"); clean(errors, "after F5 mid-ask");
  s = await still(page, 30000);

  // OVER A RESTART: the server goes away and comes back, the page reloads - the walk is where it was, and no banner sticks
  on = s.ring[0];
  await h.restart({ down: 1500 });
  await sleep(2000);
  s = await reload(page);
  if (s.ring[0] !== on || s.banners.length) await shot(page, "reload-after-restart");
  assert.equal(s.ring[0], on, `the walk resumes after a restart ${JSON.stringify({ on, s })}`);
  oneTable(s, "after a restart"); await noBlank(page, "after a restart");
  await sleep(4000);
  assert.deepEqual((await look(page)).banners, [], "an error banner stands after the server is back");
  clean(errors, "after a restart");

  // ...and the open page, never reloaded, rides out a restart: the banner it shows while the server is down clears once it is back
  await h.restart({ down: 4000 });
  await sleep(8000);
  s = await still(page, 30000);
  if (s.banners.length) await shot(page, "restart-no-reload");
  assert.deepEqual(s.banners, [], "a banner from the outage is still up");
  assert.equal(await pressNext(page), true, "Next presses after the outage");
  oneTable(await still(page, 30000), "Next after the outage");
  // a request the outage refused may log once; anything else is a failure
  clean(errors.filter((e) => !/Network Error|ERR_CONNECTION_REFUSED|ECONNREFUSED|503|502/.test(e)), "after an outage");
});
