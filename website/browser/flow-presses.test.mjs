import assert from "node:assert/strict";
import test from "node:test";
import { boot, rail, clickRow, findRow, doVerb, pressNext, folded, bubbles, type, sleep } from "./walkdriver.mjs";

/* EVERY PRESS LEAVES WORDS, LANDS ON THE NEXT THING, AND STAYS DONE (the 2026-10-28 flow walk). On the demo world: Mark done, Close with
   a note, Remind me + a day and a typed "mark this done" each fold their item with the badge of what was pressed and put the next row on
   the table; a refused press (the demo pausing no report) is said and leaves the row as it was; a reload keeps every one of them. And the
   failures: a Next whose request never gets an answer says so where it can be read - at a laptop and a phone - and the next Next goes on;
   Hand it to a person opens on the name to type; a person found with nothing on record says so. Invented Northwind people. */
const ringed = async (page) => (await rail(page)).find((r) => r.cur)?.text || "";
const badge = async (page, re) => (await folded(page)).find((f) => re.test(f.title)) || null;
const tasksNow = async (h) => (await (await fetch(`${h.fixtureApi}/api/tasks`, { headers: { "X-Taskuary-Token": h.token } })).json()).data;
const open = async (page, re) => { const k = await findRow(page, re); assert.ok(k, `${re} is on the rail`); await clickRow(page, k); await sleep(2500); };
const clickWords = (page, words, scope = "body") => page.evaluate((w, s) => {
  const b = [...document.querySelectorAll(`${s} button, ${s} [role=menuitem]`)].find((n) => n.innerText.trim() === w && !n.disabled && n.getBoundingClientRect().width > 0);
  b?.click(); return !!b; }, words, scope);

test("a press folds its item with its badge, lands on the row below, and a reload keeps it", { timeout: 300000 }, async (t) => {
  const { h, page, errors } = await boot(t, { width: 1440, height: 900 });
  const next = async (re) => { const rows = (await rail(page)).map((r) => r.text); return rows[rows.findIndex((x) => re.test(x)) + 1] || ""; };

  // Mark done
  await open(page, /overnight import/);
  let below = await next(/overnight import/);
  assert.ok(await doVerb(page, "done"), "Mark done is on the row");
  await page.waitForFunction(() => [...document.querySelectorAll("[data-tq-folded] [data-tq-pressed]")].some((e) => /Mark done/.test(e.getAttribute("data-tq-pressed"))), { timeout: 20000 });
  await sleep(1500);
  assert.equal((await ringed(page)).slice(0, 30), below.slice(0, 30), "Mark done puts the row below on the table");

  // Close with a note: the note under its badge
  await open(page, /AP cutover date/);
  assert.ok(await doVerb(page, "close-note"));
  await page.waitForSelector("[data-tq-close-note-card] textarea, [data-tq-closeout] textarea[placeholder^='What came of it']", { timeout: 10000 }).catch(() => {});
  await page.keyboard.type("Called Ruth - Thursday holds");
  assert.ok(await clickWords(page, "Close with a note", "[data-tq-close-note-card]") || await clickWords(page, "Close with a note", ".tq-canvas-live"), "the note's own Close with a note");
  await page.waitForFunction(() => [...document.querySelectorAll("[data-tq-folded]")].some((e) => /Thursday holds/.test(e.innerText)), { timeout: 20000 });
  assert.equal((await badge(page, /AP cutover date/))?.note, "Called Ruth - Thursday holds");

  // Remind me, Tomorrow
  await open(page, /Reconcile the August/);
  below = await next(/Reconcile the August/);
  assert.ok(await doVerb(page, "remind"));
  await page.waitForFunction(() => [...document.querySelectorAll(".MuiPopover-paper")].some((p) => /Bring it back on/.test(p.innerText)), { timeout: 10000 });
  assert.ok(await clickWords(page, "Tomorrow", ".MuiPopover-paper"));
  await page.waitForFunction(() => [...document.querySelectorAll("[data-tq-folded] [data-tq-pressed]")].some((e) => /Remind me/.test(e.getAttribute("data-tq-pressed"))), { timeout: 20000 });

  // typed: "mark this done" acts on the task on the table, with a receipt
  await open(page, /Year-end audit/);
  await type(page, "mark this done");
  await page.waitForFunction(() => [...document.querySelectorAll("[data-tq-folded]")].some((e) => /Year-end audit/.test(e.innerText) && e.querySelector("[data-tq-pressed]")), { timeout: 20000 });
  assert.ok((await bubbles(page)).some((b) => b.who === "receipt" && /Mark done/.test(b.text)), "the typed close says what it did");
  await page.keyboard.press("Escape"); await page.keyboard.press("Escape"); await sleep(500);

  // a refused press says so and leaves the row whole: the demo pauses no report, and the report's Share stays on its row
  await open(page, /AP ageing over 30 days/);
  const shareOn = () => page.$("[data-tq-row] button[data-tq-verb=share]").then(Boolean);
  assert.ok(await shareOn(), "a report on the table offers Share");
  assert.ok(await doVerb(page, "w:report_off"));
  await page.waitForFunction(() => /switched off/.test(document.body.innerText), { timeout: 20000 });
  await sleep(1500);
  assert.ok(await shareOn(), "the refusal said under the report leaves its Share on the row");

  // ...and a reload keeps every one of them
  await page.reload({ waitUntil: "domcontentloaded" });
  await page.waitForSelector("[data-tq-rail] .tq-pile-row", { timeout: 40000 }); await sleep(3000);
  const titles = (await rail(page)).map((r) => r.text);
  for (const re of [/overnight import/, /AP cutover date/, /Year-end audit/]) assert.ok(!titles.some((x) => re.test(x)), `${re} stays closed after a reload`);
  assert.ok(titles.some((x) => /^in \d+[hd].*Reconcile the August/.test(x)), `the reminded task waits on the rail under its day: ${JSON.stringify(titles)}`);
  const all = await tasksNow(h), of = (re) => all.find((x) => re.test(x.Title));
  assert.equal(of(/overnight import/).Status, "done");
  assert.equal(of(/AP cutover date/).Status, "done");
  assert.equal(of(/Year-end audit/).Status, "done");
  assert.ok(of(/Reconcile the August/).RemindAt, "Remind me set a day on the task");
  assert.deepEqual(errors, []);
});

for (const [width, height] of [[1440, 900], [390, 844]]) {
  test(`at ${width}px a Next that gets no answer says so where it can be read, and the next Next goes on`, { timeout: 240000 }, async (t) => {
    const { page, errors } = await boot(t, { width, height });
    let failing = false;
    page.off("request", page.fixtureRequestGuard);
    page.on("request", (r) => (failing && new URL(r.url()).pathname.startsWith("/api/") && r.method() !== "GET" ? r.abort("failed") : page.fixtureRequestGuard(r)));
    await open(page, /New starter on Monday/);
    const was = await ringed(page);
    failing = true;
    assert.ok(await pressNext(page));
    // the words, on the screen and not under the canvas or the dock: the element at their own corner is them
    const said = await page.waitForFunction(() => [...document.querySelectorAll("div")].find((d) => d.children.length <= 2 && /^Taskuary did not answer/.test(d.textContent)
      && (() => { const r = d.getBoundingClientRect(); if (!r.height) return false; const e = document.elementFromPoint(r.left + 4, r.top + 4); return e === d || d.contains(e); })())?.textContent || null,
    { timeout: 15000 }).then((x) => x.jsonValue()).catch(() => null);
    assert.ok(said, "the failed Next says so, in view");
    assert.doesNotMatch(await page.evaluate(() => document.body.innerText), /Failed to fetch|Network Error/, "in words, not the browser's");
    assert.equal(await ringed(page), was, "the item it could not leave is still the one on the table");
    failing = false;
    assert.ok(await pressNext(page)); await sleep(3000);
    assert.notEqual(await ringed(page), was, "the next Next goes on");
    assert.deepEqual(errors, []);
  });
}

test("Hand it to a person opens on the name to type; a person found with nothing on record says so", { timeout: 240000 }, async (t) => {
  const { page, errors } = await boot(t, { width: 1440, height: 900 });
  await open(page, /Month-end close/);
  assert.ok(await doVerb(page, "hand"));
  await page.waitForSelector('input[placeholder="who should own this — name or email"]', { visible: true, timeout: 15000 });
  await sleep(600);
  assert.equal(await page.evaluate(() => document.activeElement?.placeholder || ""), "who should own this — name or email", "the name is where typing goes");
  await page.keyboard.type("gail"); await sleep(1500);
  assert.equal(await page.$eval('input[placeholder="who should own this — name or email"]', (e) => e.value), "gail");
  await page.click('[aria-label="Close handoff"]'); await sleep(800);

  await page.keyboard.down("Control"); await page.keyboard.press("k"); await page.keyboard.up("Control"); await sleep(800);
  await page.keyboard.type("dynamo");
  await page.waitForFunction(() => /Lena Ortiz/.test(document.querySelector("[data-tq-search]")?.innerText || ""), { timeout: 15000 });
  await page.evaluate(() => [...document.querySelectorAll("[data-tq-search] *")].find((e) => e.children.length === 0 && e.textContent === "Lena Ortiz")?.click());
  await page.waitForSelector("[data-tq-search-alone]", { timeout: 15000 });
  assert.match(await page.$eval("[data-tq-search-alone]", (e) => e.textContent), /^Nothing from or about Lena Ortiz yet/);
  assert.deepEqual(errors, []);
});
