import assert from "node:assert/strict";
import test from "node:test";
import { startHarness } from "./harness.mjs";

/* THE PHONE'S CHROME LEAVES THE TITLE ITS ROOM (the overnight walk, owner-approved 2026-10-27, item 8). At 390px "Invoice 88213 - past due"
   read "Invoice …" beside a "ready to send" pill, "Setup: pick your AI" put the top bar on two rows, and the chat box stood 58px tall at
   rest. Under 600px: the status pill and the setup chip are their icon alone (the words their name and hover), Refresh and Quit sit inside
   Help, and the box is one line. The desk keeps all of it as it was. */
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const json = (r, body) => r.respond({ status: 200, contentType: "application/json", body: JSON.stringify(body) });

async function open(t, width) {
  const h = await startHarness(); t.after(() => h.close());
  const page = await h.newPage(), errors = [], quits = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.setViewport({ width, height: 844, deviceScaleFactor: 1 });
  // a home that is not the demo and is still being set up: the chip the walk saw ("Setup: pick your AI")
  page.off("request", page.fixtureRequestGuard);
  page.on("request", (r) => {
    const p = new URL(r.url()).pathname;
    if (p === "/api/demo") return json(r, { demo: false });
    if (p === "/api/setup" && r.method() === "GET") return json(r, { left: 2, todo: "pick your AI", dismissed: false });
    if (p === "/api/quit") { quits.push(r.method()); return json(r, r.method() === "GET" ? { running: "1 running agent" } : { quitting: true, stopped: [] }); }
    return page.fixtureRequestGuard(r);
  });
  await page.goto(h.ui, { waitUntil: "domcontentloaded", timeout: 30000 });
  await page.waitForSelector("[data-tq-rail] .tq-pile-row", { timeout: 40000 });
  await page.waitForSelector("[data-tq-setup-chip]", { timeout: 20000 });
  await sleep(1500);
  const tasks = (await (await fetch(`${h.fixtureApi}/api/tasks`, { headers: { "X-Taskuary-Token": h.token } })).json()).data;
  return { page, errors, quits, tasks };
}
const bar = (page) => page.evaluate(() => {
  const nav = document.getElementById("tqTopNav"), vis = [...nav.children].filter((e) => e.getBoundingClientRect().width);
  const chip = nav.querySelector("[data-tq-setup-chip]");
  return { h: nav.getBoundingClientRect().height, mids: [...new Set(vis.map((e) => { const b = e.getBoundingClientRect(); return Math.round((b.top + b.bottom) / 2 / 6); }))],
    over: nav.scrollWidth - nav.clientWidth, chip: chip && { w: chip.getBoundingClientRect().width, name: chip.getAttribute("aria-label"), seen: chip.innerText.trim() },
    names: [...nav.querySelectorAll("button")].filter((b) => b.getBoundingClientRect().width).map((b) => b.getAttribute("aria-label") || "") };
});
async function task(page, id) {
  await page.evaluate((id) => { location.hash = `task=${id}`; }, id);
  await page.waitForSelector(`[data-tq-task-page="${id}"] [data-tq-task-head]`, { timeout: 20000 });
  await sleep(600);
  return page.evaluate(() => {
    const head = document.querySelector("[data-tq-task-head]"), pill = head.querySelector("[data-tq-status-pill]");
    const title = [...head.querySelectorAll(".MuiTypography-root")].find((e) => e.hasAttribute("title"));
    const box = document.querySelector(".tq-dock .tq-compose-box");
    return { headH: head.getBoundingClientRect().height, title: { text: title.textContent, w: title.clientWidth, whole: title.scrollWidth <= title.clientWidth + 1 },
      pill: { w: pill.getBoundingClientRect().width, word: pill.querySelector(".word")?.textContent, title: pill.getAttribute("title"),
        wordSeen: pill.querySelector(".word").getBoundingClientRect().width > 2 }, box: box.getBoundingClientRect().height };
  });
}

test("on a phone the title keeps its room: icon-only pills, a one-row bar, Refresh and Quit inside Help, a one-line box", { timeout: 240000 }, async (t) => {
  const { page, errors, quits, tasks } = await open(t, 390);
  const b = await bar(page);
  assert.equal(b.mids.length, 1, `the top bar is one row: ${JSON.stringify(b)}`);
  assert.ok(b.h <= 60 && b.over <= 0, `the bar fits one row: ${JSON.stringify(b)}`);
  assert.equal(b.chip.name, "Setup: pick your AI", "the setup chip keeps its words as its name");
  assert.equal(b.chip.seen, "", "...and draws only its ring");
  assert.ok(b.chip.w <= 32, `the chip is its ring: ${b.chip.w}`);
  assert.ok(!b.names.includes("Quit Taskuary") && !b.names.some((n) => /refresh/i.test(n)), `Refresh and Quit left the bar: ${b.names}`);

  for (const re of [/^Invoice 88213/, /^Ray: schema sign-off/]) {
    const k = tasks.find((x) => re.test(x.Title));
    const m = await task(page, k.TaskId);
    assert.equal(m.title.text, k.Title);
    assert.ok(m.title.whole && m.title.w >= 140, `the title reads whole, not "Invoice …": ${JSON.stringify(m)}`);
    assert.ok(m.headH <= 40, `the header is one row: ${m.headH}`);
    assert.ok(m.pill.w <= 24 && !m.pill.wordSeen, `the status pill is its mark: ${JSON.stringify(m.pill)}`);
    assert.ok(m.pill.word && m.pill.title, "...its word still in it for a reader, and a hover");
    assert.ok(m.box <= 44, `the chat box is one line at rest: ${m.box}`);
  }

  // Help holds the three: Report a problem, the same refresh, the same Quit with its hover's words and no box asking
  await page.click("#tqTopNav [data-tq-help]");
  await page.waitForSelector('[role="menu"] [data-tq-quit]', { timeout: 10000 });
  await page.waitForFunction(() => document.querySelector('[role="menu"] [data-tq-quit]').innerText.includes("and the 1 running agent with it"), { timeout: 10000 });
  const items = await page.$$eval('[role="menu"] [role="menuitem"]', (els) => els.map((e) => e.innerText.split("\n")[0]));
  assert.deepEqual(items, ["Report a problem", "Refresh", "Quit Taskuary"]);
  await page.click('[role="menu"] [data-tq-reload]');
  await page.waitForFunction(() => !document.querySelector('[role="menu"]'), { timeout: 10000 });
  await page.click("#tqTopNav [data-tq-help]");
  await page.waitForSelector('[role="menu"] [data-tq-quit]', { timeout: 10000 });
  await page.click('[role="menu"] [data-tq-quit]');
  await page.waitForSelector("[data-tq-stopped]", { timeout: 10000 });
  assert.equal(await page.$('[role="dialog"]'), null, "no box asks");
  assert.deepEqual(quits.filter((m) => m === "POST"), ["POST"]);
  assert.deepEqual(errors, []);
});

test("on the desk nothing moved: words on the pills, Refresh and Quit on the bar, Help reports a problem", { timeout: 240000 }, async (t) => {
  const { page, errors, tasks } = await open(t, 1440);
  const b = await bar(page);
  assert.equal(b.chip.seen, "Setup: pick your AI");
  assert.ok(b.names.includes("Quit Taskuary") && b.names.includes("Report a problem"), `${b.names}`);
  assert.equal(await page.$("#tqTopNav [data-tq-help]"), null, "Help is the one Report a problem button, no menu");
  const m = await task(page, tasks.find((x) => /^Invoice 88213/.test(x.Title)).TaskId);
  assert.ok(m.pill.wordSeen && m.pill.w > 100, `the pill says "ready to send": ${JSON.stringify(m.pill)}`);
  assert.ok(m.box >= 34 && m.box <= 40, `the desk's pill at rest: ${m.box}`);
  assert.deepEqual(errors, []);
});
