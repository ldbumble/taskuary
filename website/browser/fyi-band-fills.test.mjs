import assert from "node:assert/strict";
import test from "node:test";
import { startHarness } from "./harness.mjs";

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
/* THE FYI BAND FILLS THE ROOM IT HAS, AND THE COUNTS ADD UP (the owner, 2026-10-26, a batch of 4 fyi on the table under "FYI 13": "why does
   the fyi items not scroll out? meaning why does it say 9 more fyi. also the 11 away which is wrong?"). The rows past the page's first FYI
   page were fetched only once the band was opened by hand, so a tall rail drew the batch, "N more fyi" and empty space; and "away from clear"
   counted the pile without the batch on the table. The demo has a dozen FYI, so its first page is cut to 4 here (every request's `fyi: 50`)
   - the shape of an account with more FYI than one page. */
test("a tall rail draws every fyi it has room for, and its headings, its 'more' and 'away from clear' agree", { timeout: 180000 }, async (t) => {
  const h = await startHarness(); t.after(() => h.close());
  const page = await h.newPage(), errors = [], asked = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.setViewport({ width: 1440, height: 2400, deviceScaleFactor: 1 });
  page.off("request", page.fixtureRequestGuard);
  page.on("request", (r) => {
    const url = r.url().replace(/([?&]fyi=)50\b/, "$14"), body = r.postData();
    const postData = body && /"fyi":50\b/.test(body) ? body.replace(/"fyi":50\b/, '"fyi":4') : undefined;
    if (url === r.url() && !postData) return page.fixtureRequestGuard(r);
    asked.push(url.includes("fyi=4") || postData ? 4 : 0);
    return r.continue({ url, ...(postData ? { postData } : {}) });
  });
  await page.goto(h.ui, { waitUntil: "domcontentloaded", timeout: 30000 });
  await page.waitForSelector("[data-tq-rail] .tq-pile-row", { timeout: 40000 });
  await sleep(2500);
  const state = () => page.evaluate(() => {
    const sc = document.querySelector("[data-tq-rail]"), pile = document.querySelector(".tq-pile"), box = sc.getBoundingClientRect();
    const heads = Object.fromEntries([...document.querySelectorAll("[data-tq-section-head]")].map((e) => [e.dataset.tqSectionHead, Number(e.querySelector("em")?.textContent)]));
    const more = [...document.querySelectorAll('[data-tq-run="fyi"] .tq-pile-more')].map((e) => ({ text: e.textContent.trim(), room: box.bottom - e.getBoundingClientRect().bottom }));
    return { heads, more, fyiRows: document.querySelectorAll('[data-tq-run="fyi"] .tq-pile-row').length, batch: document.querySelector(".tq-pile-batch")?.textContent || "",
      left: Number(pile.dataset.tqLeft), cheer: document.querySelector(".tq-pile-cheer")?.textContent || "", overflow: sc.scrollHeight - sc.clientHeight };
  });
  const press = () => page.evaluate(() => { const b = document.querySelector("[data-tq-row] [data-tq-next]"); b?.click(); return b?.textContent.trim() || null; });
  const check = async (when, batch) => {
    const s = await state();
    if (batch) assert.match(s.batch, /on the table · \d+ fyi/, `${when}: a batch is on the table - ${JSON.stringify(s)}`);
    assert.equal(s.overflow <= 0, true, `${when}: the rail is tall enough for everything - ${JSON.stringify(s)}`);
    assert.deepEqual(s.more, [], `${when}: no "N more fyi" over an empty rail - ${JSON.stringify(s)}`);
    assert.equal(s.fyiRows, s.heads.fyi, `${when}: the FYI heading counts the rows it draws - ${JSON.stringify(s)}`);
    assert.equal(s.left, Object.values(s.heads).reduce((a, b) => a + b, 0), `${when}: away from clear is the headings added up, the table's rows with them - ${JSON.stringify(s)}`);
    if (s.cheer) assert.match(s.cheer, new RegExp(`\\b${s.left}\\b|One more`), `${when}: the cheer says that count`);
  };
  // the first draw: 4 FYI whole, 8 counted - the band drew 4 rows and "8 more fyi" over 1200px of empty rail
  await check("the first draw", false);
  // the walk up to the first fyi batch, the way fyi-count-between-batches gets there: the last report, then Next
  await page.click('[data-tq-section-head="reports"] .fold'); await sleep(1500);
  await page.evaluate(() => [...document.querySelectorAll('[data-tq-run="reports"] .tq-pile-row[data-tq-key] .card')].at(-1).click()); await sleep(3500);
  await press(); await sleep(4000);
  await check("a batch up", true);
  // ...and a rail made short for a moment and tall again gives the room back: a trim taken in the short moment stayed until a count changed
  await page.setViewport({ width: 1440, height: 900, deviceScaleFactor: 1 }); await sleep(1500);
  await page.setViewport({ width: 1440, height: 2400, deviceScaleFactor: 1 }); await sleep(2000);
  await check("short, then tall again", true);
  assert.ok(asked.length, "the first FYI page was cut to 4 - else this proved nothing");
  assert.deepEqual(errors, []);
});
