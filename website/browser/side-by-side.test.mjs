import assert from "node:assert/strict";
import test from "node:test";
import { mkdirSync } from "node:fs";
import path from "node:path";

import { startHarness } from "./harness.mjs";

/* TWO PANES SIDE BY SIDE (the owner, 2026-11-01, "try it": "a button to open 2 side by side so you can see agent response and close out
   generated email or came from and agent work ... if agent working we don't need that button"). On the canvas, the open pane's strip
   carries a two-column toggle: pressed, the pane and its partner each take half the work area - Agent beside Close out, Came from beside
   Agent - each under its own strip with its own moves, the third a spine; pressed again, one pane. Not where two halves would be cramped,
   nor over a live agent. Invented people (fixture chat-saved: a stopped agent's answer and the reply it drafted).
   TASKUARY_SHOT_DIR: where the 1440x900 and 1920x1080 frames go. */
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const DRAFT = "Ray Colton signs the snag list on Thursday - keys are at reception from 7.";
let CUR = "[data-tq-canvas-item]";
const openTask = async (page, id) => {
  CUR = `[data-tq-canvas-item]:has([data-tq-task-page="${id}"])`;
  await page.evaluate((id) => { location.hash = ""; location.hash = `task=${id}`; }, id);
  await page.waitForSelector(`${CUR} [data-tq-task-body][data-tq-sections]`, { timeout: 20000 });
  await sleep(1500);
};
const openSec = async (page, key) => {
  if (await page.$(`${CUR} [data-tq-slot=${key}][data-tq-open]`)) return;
  await page.click(`${CUR} [data-tq-section-tab=${key}] [data-tq-tab-name]`);
  await page.waitForSelector(`${CUR} [data-tq-slot=${key}][data-tq-open]`, { timeout: 5000 }); await sleep(500);
};
// what the body shows: the open slots, their widths, each open strip's moves, where the toggle stands
const look = (page) => page.evaluate((CUR) => {
  const body = document.querySelector(`${CUR} [data-tq-task-body]`), vis = (b) => !!b.offsetParent && getComputedStyle(b).visibility !== "hidden";
  const open = [...body.querySelectorAll(":scope [data-tq-slot][data-tq-open]")];
  return { pair: body.dataset.tqPair || "", bodyW: Math.round(body.getBoundingClientRect().width), open: open.map((s) => s.dataset.tqSlot),
    widths: open.map((s) => Math.round(s.getBoundingClientRect().width)),
    toggles: [...body.querySelectorAll("[data-tq-strip-pair]")].filter(vis).map((b) => [b.closest("[data-tq-pane-strip]").dataset.tqPaneStrip, b.dataset.tqStripPair, b.getAttribute("aria-label")]),
    strips: Object.fromEntries(open.map((s) => [s.dataset.tqSlot, [...s.querySelectorAll("[data-tq-pane-strip] [data-tq-pane-moves] button")].filter(vis).map((b) => b.textContent.trim())])),
    spines: [...body.querySelectorAll("[data-tq-section-tab]")].map((t) => t.dataset.tqSectionTab),
    // ...each open section's region laid inside its own slot, so nothing in one half is cut by the other
    fits: open.every((s) => { const r = s.querySelector(":scope > [role=region]")?.getBoundingClientRect(), o = s.getBoundingClientRect(); return r && r.right <= o.right + 2; }),
    // ...and each open strip's moves on one line inside it: what does not fit is behind its ▾, never cut off at the edge
    cut: open.filter((s) => { const b = s.querySelector("[data-tq-pane-moves]"); return b && b.scrollWidth > b.clientWidth + 1; }).map((s) => s.dataset.tqSlot) };
}, CUR);
const shot = async (page, name) => { const dir = process.env.TASKUARY_SHOT_DIR; if (!dir) return; mkdirSync(dir, { recursive: true }); await sleep(600); await page.screenshot({ path: path.join(dir, name) }); };
// ...pressed, the page has settled once each open slot has slid to the width its body is laid at and its strip's moves have folded to fit
const settled = (page) => page.waitForFunction((CUR) => [...document.querySelectorAll(`${CUR} [data-tq-task-body] [data-tq-slot][data-tq-open]`)].every((s) => {
  const r = s.querySelector(":scope > [role=region]"), b = s.querySelector("[data-tq-pane-moves]");
  return r && Math.abs(s.getBoundingClientRect().width - r.getBoundingClientRect().width) <= 3 && (!b || b.scrollWidth <= b.clientWidth + 1); }), { timeout: 8000 }, CUR).catch(() => {});
const flip = async (page, strip) => { await page.click(`${CUR} [data-tq-pane-strip=${strip}] [data-tq-strip-pair]`); await sleep(300); await settled(page); };
// ...the verbs behind a strip's ▾
const tucked = async (page, sec) => { if (!(await page.$(`${CUR} [data-tq-more=${sec}]`))) return [];
  await page.click(`${CUR} [data-tq-more=${sec}]`); await page.waitForSelector("[role=menu] [role=menuitem]", { timeout: 5000 });
  const vs = await page.$$eval("[role=menu] [role=menuitem]", (xs) => xs.map((x) => x.dataset.tqVerb));
  await page.keyboard.press("Escape"); await page.waitForFunction(() => !document.querySelector("[role=menu]"), { timeout: 5000 }); return vs; };
const CHANGE = ["reshape", "kind", "priority"];

test("side by side: Agent beside Close out and Came from beside Agent, each with its moves; back to one; none narrow or over a live agent", { timeout: 300000 }, async (t) => {
  const hz = await startHarness();
  t.after(() => hz.close());
  const page = await hz.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.setViewport({ width: 1440, height: 900, deviceScaleFactor: 1 });
  await page.goto(hz.ui, { waitUntil: "domcontentloaded" });
  await page.waitForSelector("[data-tq-rail] .tq-pile-row", { timeout: 30000 });
  const made = await page.evaluate(async (draft) => (await fetch("/api/fixture/task/chat-saved", { method: "POST", body: JSON.stringify({ draft }),
    headers: { "X-Taskuary-Token": localStorage.getItem("taskuary_token"), "Content-Type": "application/json" } })).json(), DRAFT);
  const tid = made.taskId;
  // the demo sends nothing: Send's answer is played here
  let decided = 0;
  page.off("request", page.fixtureRequestGuard);
  page.on("request", (req) => {
    if (req.method() === "POST" && /^\/api\/reviews\/\d+\/decide$/.test(new URL(req.url()).pathname)) { decided++;
      return req.respond({ status: 200, contentType: "application/json", body: JSON.stringify({ ok: true, status: "approved", sent: { channel: "whatsapp" }, send_error: null }) }); }
    page.fixtureRequestGuard(req);
  });

  await t.test("1440: the toggle on the open strip; pressed, Agent and Close out take a half each, each under its own strip", async () => {
    await openTask(page, tid);
    await openSec(page, "agent");
    let m = await look(page);
    assert.deepEqual(m.toggles, [["agent", "off", "Side by side"]], `one toggle, on the open pane's strip ${JSON.stringify(m)}`);
    await shot(page, "one-pane-1440x900.png");
    await flip(page, "agent");
    m = await look(page);
    assert.equal(m.pair, "agent+close", JSON.stringify(m));
    assert.deepEqual(m.open, ["agent", "close"]);
    assert.deepEqual(m.spines, ["from"], "Came from stays a spine");
    assert.ok(Math.abs(m.widths[0] - m.widths[1]) <= 4 && m.widths[0] > 400, `two halves of about one width ${JSON.stringify(m)}`);
    assert.ok(m.fits, `each body inside its half ${JSON.stringify(m)}`);
    assert.deepEqual(m.cut, [], `no move cut off at a half's edge ${JSON.stringify(m)}`);
    assert.deepEqual(m.toggles.map((x) => x.slice(0, 2)), [["agent", "on"], ["close", "on"]], "each half can go back to one");
    assert.ok(m.strips.close.includes("Mark done"), `Close out's moves on its strip ${JSON.stringify(m.strips)}`);
    assert.ok(m.strips.agent.length > 0, `Agent's moves on its strip ${JSON.stringify(m.strips)}`);
    const words = await page.evaluate((CUR) => ({ agent: document.querySelector(`${CUR} [data-tq-slot=agent]`).innerText,
      draft: [...document.querySelectorAll(`${CUR} [data-tq-slot=close] textarea`)].map((x) => x.value).join(" ") }), CUR);
    assert.match(words.agent, /Ray Colton/, "the agent's answer shows");
    assert.ok(words.draft.includes("snag list"), `the drafted reply shows beside it: ${words.draft}`);
    await shot(page, "agent-closeout-1440x900.png");
  });

  // ...the demo world has no AI, so the agent's own starts are greyed: its press here is the Result's "The whole conversation", in place
  await t.test("a press in the Agent half opens the agent's whole answer there, Close out still beside it", async () => {
    const before = await page.$eval(`${CUR} [data-tq-slot=agent] [role=region]`, (e) => e.innerText.length);
    const pressed = await page.evaluate((CUR) => { const b = [...document.querySelectorAll(`${CUR} [data-tq-slot=agent] button`)].find((x) => /^The whole conversation/.test(x.textContent.trim()) && x.offsetParent);
      if (!b) return false; b.click(); return true; }, CUR);
    assert.ok(pressed, "the Result's way to the whole answer, in the Agent half");
    await page.waitForFunction((CUR, n) => document.querySelector(`${CUR} [data-tq-slot=agent] [role=region]`).innerText.length > n, { timeout: 8000 }, CUR, before);
    const m = await look(page);
    assert.equal(m.pair, "agent+close", `still side by side ${JSON.stringify(m)}`);
    assert.ok(m.strips.close.includes("Mark done"), "Close out still open beside it");
  });

  await t.test("Came from's toggle pairs it with Agent; the outer arrow slides the pair; the toggle again is one pane", async () => {
    await flip(page, "agent");
    let m = await look(page);
    assert.deepEqual([m.pair, m.open], ["", ["agent"]], `one pane again ${JSON.stringify(m)}`);
    await openSec(page, "from");
    await flip(page, "from");
    m = await look(page);
    assert.equal(m.pair, "from+agent", JSON.stringify(m));
    assert.deepEqual(m.open, ["from", "agent"]);
    assert.ok(Math.abs(m.widths[0] - m.widths[1]) <= 4, JSON.stringify(m));
    assert.deepEqual(m.cut, [], `no move cut off at a half's edge ${JSON.stringify(m)}`);
    assert.ok(m.strips.from.some((x) => /Not a task|Remind me/.test(x)), `Came from's moves ${JSON.stringify(m.strips)}`);
    // ...its Change with them: on the strip, or - a 1440 half has no room for it - its Split or merge, who and priority behind the ▾
    const behind = m.strips.from.includes("Change ▾") ? CHANGE : await tucked(page, "from");
    assert.ok(CHANGE.every((v) => behind.includes(v)), `Came from's Change ${JSON.stringify(m.strips)} ${behind}`);
    // ...no arrow points at the other open half; Agent's outer one shows Close out beside it
    const arrows = await page.evaluate((CUR) => [...document.querySelectorAll(`${CUR} [data-tq-strip-fold]`)].map((a) => `${a.closest("[data-tq-pane-strip]").dataset.tqPaneStrip}:${a.dataset.tqStripFold}`), CUR);
    assert.deepEqual(arrows, ["agent:right"], `${arrows}`);
    // ...and Close out's spine still carries its draft's Redraft, as it does beside Came from alone
    const spine = await page.$$eval(`${CUR} [data-tq-spine-moves=close] button`, (bs) => bs.map((b) => b.textContent.trim()));
    assert.ok(spine.includes("Redraft"), `Close out's spine: ${spine}`);
    await shot(page, "from-agent-1440x900.png");
    await page.click(`${CUR} [data-tq-pane-strip=agent] [data-tq-strip-fold=right]`); await sleep(700);
    m = await look(page);
    assert.deepEqual(m.open, ["agent", "close"], `slid along ${JSON.stringify(m)}`);
  });

  await t.test("a press in the Close out half: Send goes, from beside the Agent", async () => {
    const send = await page.evaluate((CUR) => {
      const b = [...document.querySelectorAll(`${CUR} [data-tq-slot=close] button`)].find((x) => /^Send\b/.test(x.textContent.trim()) && !x.disabled && x.offsetParent);
      if (!b) return false; b.click(); return true;
    }, CUR);
    assert.ok(send, "Close out offers Send while Agent is open beside it");
    for (let i = 0; i < 20 && !decided; i++) await sleep(250);
    assert.equal(decided, 1, "the Send reached the server");
  });

  await t.test("narrow: no toggle, and side by side falls back to one pane", async () => {
    const t2 = (await page.evaluate(async () => (await fetch("/api/fixture/task/chat-saved", { method: "POST", body: JSON.stringify({ draft: "Thursday works." }),
      headers: { "X-Taskuary-Token": localStorage.getItem("taskuary_token"), "Content-Type": "application/json" } })).json())).taskId;
    await openTask(page, t2);
    await openSec(page, "agent");
    await flip(page, "agent");
    assert.equal((await look(page)).pair, "agent+close");
    for (const [w, h] of [[1280, 800], [1024, 768]]) {
      await page.setViewport({ width: w, height: h, deviceScaleFactor: 1 }); await sleep(1200);
      // ...1024's work area is a phone's stacked page (under 760): no slots at all
      const m = await look(page);
      assert.ok(!m.toggles.length && !m.pair && m.open.length <= 1, `${w}: one pane, no toggle ${JSON.stringify(m)}`);
    }
    await page.setViewport({ width: 1440, height: 900, deviceScaleFactor: 1 }); await sleep(1200);
  });

  await t.test("a live agent: no toggle - it keeps the room", async () => {
    const tasks = (await (await fetch(`${hz.fixtureApi}/api/tasks`, { headers: { "X-Taskuary-Token": hz.token } })).json()).data;
    const live = tasks.find((x) => x.State === "working" || /census sync fails/.test(x.Title));
    await openTask(page, live.TaskId);
    await page.waitForSelector(`${CUR} .xterm`, { timeout: 20000 }); await sleep(800);
    assert.deepEqual((await look(page)).toggles, [], "no side by side over a live agent");
  });

  await t.test("1920x1080: both pairs", async () => {
    await page.setViewport({ width: 1920, height: 1080, deviceScaleFactor: 1 });
    const t3 = (await page.evaluate(async (draft) => (await fetch("/api/fixture/task/chat-saved", { method: "POST", body: JSON.stringify({ draft }),
      headers: { "X-Taskuary-Token": localStorage.getItem("taskuary_token"), "Content-Type": "application/json" } })).json(), DRAFT)).taskId;
    await openTask(page, t3);
    await openSec(page, "agent");
    await flip(page, "agent");
    let m = await look(page);
    assert.equal(m.pair, "agent+close", JSON.stringify(m));
    assert.ok(Math.abs(m.widths[0] - m.widths[1]) <= 4 && m.fits, JSON.stringify(m));
    await shot(page, "agent-closeout-1920x1080.png");
    await flip(page, "agent");
    await openSec(page, "from");
    await flip(page, "from");
    m = await look(page);
    assert.equal(m.pair, "from+agent", JSON.stringify(m));
    assert.ok(m.strips.from.includes("Change ▾") && !m.cut.length, `a 1920 half has room for Came from's Change ${JSON.stringify(m)}`);
    await shot(page, "from-agent-1920x1080.png");
  });

  assert.deepEqual(errors, []);
});
