// SETUP'S STEPS AT EVERY SCREEN SIZE (the owner, 2026-11-03: "the setup walk through the nav is broken. it should just be back, all ready, next
// in corner like in actual app ... the cards are laid out really weird. fix it depending on the screen size"). A fresh first start; the mail
// step is the server's own setup state with the AI marked done, as about-steps does it. At each width: Back and Next are the walk's Nav pill,
// on one row in the bar's corner, Back greyed on the first step; the cards neither overlap nor run out of the canvas; nothing scrolls sideways.
import assert from "node:assert/strict";
import { mkdir } from "node:fs/promises";
import path from "node:path";
import test from "node:test";
import { startHarness } from "./harness.mjs";

const SIZES = [[1920, 1080], [1440, 900], [1280, 800], [1024, 768], [390, 844]];
const until = (page, f, arg, timeout = 45000) => page.waitForFunction(f, { timeout, polling: 200 }, arg);

const measure = (page) => page.evaluate(() => {
  const r = (e) => { const b = e.getBoundingClientRect(); return { l: b.left, r: b.right, t: b.top, b: b.bottom, w: b.width, h: b.height }; };
  const fr = document.querySelector("[data-tq-firstrun]"), dock = document.querySelector(".tq-dock"), pill = dock?.querySelector('[data-tq-type="nav"]');
  const tiles = [...fr.querySelectorAll("[data-tq-setup-grid] > *")].map((e) => ({ k: e.getAttribute("data-tq-card") || "more", grid: [...fr.querySelectorAll("[data-tq-setup-grid]")].indexOf(e.parentElement), ...r(e) }));
  const wide = []; for (let e = fr; e; e = e.parentElement) if (e.scrollWidth > e.clientWidth + 1 && getComputedStyle(e).overflowX !== "visible") wide.push(e.className || e.tagName);
  const btn = (sel) => { const e = pill?.querySelector(sel); return e && { ...r(e), off: e.disabled, text: e.innerText.trim(), label: e.getAttribute("aria-label") || "" }; };
  return { fr: r(fr), dock: dock && r(dock), pill: pill && r(pill), back: btn("[data-tq-back]"), next: btn("[data-tq-next]"), tiles, wide,
    page: document.documentElement.scrollWidth - innerWidth, others: [...dock.querySelectorAll("[data-tq-row] button")].filter((e) => !pill.contains(e) && !e.closest(".tq-arow-ghost") && e.getBoundingClientRect().width > 0).map((e) => e.innerText.trim()) };
});

test("setup's AI and mail steps: the Nav pill in the bar's corner, even cards, no sideways scroll, at five screen sizes", { timeout: 600000 }, async (t) => {
  const harness = await startHarness({ fresh: true }); t.after(() => harness.close());
  const page = await harness.newPage(), errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  let mail = false;
  page.off("request", page.fixtureRequestGuard);
  page.on("request", async (rq) => {
    const p = new URL(rq.url()).pathname;
    if (mail && p === "/api/setup/first-run" && rq.method() === "GET") {
      try {
        const st = await (await fetch(`${harness.fixtureApi}${p}`, { headers: { "X-Taskuary-Token": harness.token } })).json();
        return rq.respond({ status: 200, contentType: "application/json", body: JSON.stringify({ ...st, step: "mail", frontier: "mail", ai_error: "",
          brain: { ...st.brain, ready: true, name: "Your AI" }, rail: st.rail.map((x) => ({ ...x, done: x.key === "ai" || x.done, open: ["ai", "mail"].includes(x.key) || x.open })) }) });
      } catch (e) { errors.push(`fixture: ${e.message}`); return rq.abort(); }
    }
    page.fixtureRequestGuard(rq);
  });
  for (const step of ["ai", "mail"]) {
    mail = step === "mail";
    await page.goto(harness.ui, { waitUntil: "domcontentloaded" });
    await until(page, (s) => document.querySelector(`[data-tq-firstrun] [data-tq-card]`) && document.querySelector('.tq-dock [data-tq-type="nav"] [data-tq-next]')
      && (s !== "mail" || !document.querySelector('.tq-dock [data-tq-back]')?.disabled), step);
    for (const [w, h] of SIZES) {
      await page.setViewport({ width: w, height: h, deviceScaleFactor: 1 });
      await new Promise((r) => setTimeout(r, 600));
      const m = await measure(page), at = `${step} ${w}x${h}`;
      if (process.env.TASKUARY_SHOTS) { await mkdir(process.env.TASKUARY_SHOTS, { recursive: true }); await page.screenshot({ path: path.join(process.env.TASKUARY_SHOTS, `${step}-${w}x${h}.png`) }); }
      // NAV: Back then Next in one pill, one row, in the bar's bottom-left corner - and nothing else of setup's in the bar
      assert.ok(m.pill && m.back && m.next, `${at}: Back and Next are the Nav pill`);
      assert.ok(m.back.r <= m.next.l + 1, `${at}: Back before Next`);
      assert.ok(Math.abs(m.back.t - m.next.t) < 2 && m.pill.h < 52, `${at}: one row (pill ${m.pill.h}px)`);
      assert.ok(m.pill.l - m.dock.l < 40 && m.dock.b - m.pill.b < 20, `${at}: in the corner - pill ${JSON.stringify(m.pill)} dock ${JSON.stringify(m.dock)}`);
      assert.equal(m.back.off, step === "ai", `${at}: Back is greyed on the first step only`);
      assert.match(m.next.text, /^Next$/, at);
      assert.deepEqual(m.others, [], `${at}: no other buttons in the bar`);
      // CARDS: inside the shelf, none over another, the same size within a grid's row
      for (const c of m.tiles) assert.ok(c.l >= m.fr.l - 1 && c.r <= m.fr.r + 1 && c.r <= w, `${at}: ${c.k} runs out of the shelf (${c.l}-${c.r} of ${m.fr.l}-${m.fr.r})`);
      for (const a of m.tiles) for (const b of m.tiles) {
        if (a === b) continue;
        const x = Math.min(a.r, b.r) - Math.max(a.l, b.l), y = Math.min(a.b, b.b) - Math.max(a.t, b.t);
        assert.ok(x <= 1 || y <= 1, `${at}: ${a.k} overlaps ${b.k}`);
      }
      const cards = m.tiles.filter((c) => c.k !== "more");
      for (const c of cards) assert.ok(Math.abs(c.w - cards[0].w) <= 1 && Math.abs(c.h - cards[0].h) <= 1, `${at}: ${c.k} is ${c.w}x${c.h}, ${cards[0].k} ${cards[0].w}x${cards[0].h}`);
      for (const c of cards) assert.ok(c.w >= Math.min(230, m.fr.w - 2), `${at}: ${c.k} is ${c.w}px wide - too narrow to read`);
      // a row is never ragged: More ends where the row ends
      const more = m.tiles.find((c) => c.k === "more");
      if (more) assert.ok(Math.abs(more.r - Math.max(...cards.filter((c) => c.grid === more.grid).map((c) => c.r))) <= 1, `${at}: More stops short of its row's end`);
      assert.ok(m.page <= 1, `${at}: the page scrolls sideways by ${m.page}px`);
      assert.deepEqual(m.wide, [], `${at}: these scroll sideways`);
    }
  }
  assert.deepEqual(errors, []);
});
