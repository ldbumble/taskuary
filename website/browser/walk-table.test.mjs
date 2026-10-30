import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";
import { boot, clickRow, clickText, doVerb, pressNext, sleep } from "./walkdriver.mjs";

/* THE WALK TABLE, CLICKED (docs/superpowers/specs/2026-10-30-walk-one-owner-design.md, 6.2): every case of tests/fixtures/walk_table.json -
   the same file tests/test_walk_table.py replays in process - driven on the demo app with the rail, the bar's Back and Next and the row's
   verbs, on the world tests/walkworld.py lays out (POST /api/fixture/walk/world). Moves made somewhere other than the desk - an arrival, a
   close elsewhere, an agent closing its task, the phone - go through the fixture.
   THE FRAME RECORDER wraps each case's action: from the press until the expected row is ringed, every animation frame must show the item
   or the dots (never a blank canvas), the ring may stand only on the row it left, the prepared row and the expected one, the press is
   pressed once, and at most one new assistant line lands (rule 7).
   A case the desk has no road for says so in its `browser.skip`; `browser.steps` / `browser.action` say a desk road where it differs.
   WALK_TABLE=W01,W02 runs those alone; WALK_TABLE_OUT=<file> writes each case's result there. */
const TABLE = JSON.parse(fs.readFileSync(new URL("../../tests/fixtures/walk_table.json", import.meta.url), "utf8")).cases;
const ONLY = (process.env.WALK_TABLE || "").split(",").filter(Boolean);
const RECORDED = /^(next|back|open|leave|send|heading|start)\b/;

test("the walk table, clicked, with every action's frames recorded", { timeout: 60 * 60 * 1000 }, async (t) => {
  const { h, page, errors } = await boot(t, { width: 1440, height: 900 });
  const api = (p, body) => fetch(`${h.fixtureApi}${p}`, { method: body ? "POST" : "GET", headers: { "X-Taskuary-Token": h.token, "Content-Type": "application/json" },
    ...(body ? { body: JSON.stringify(body) } : {}) }).then(async (r) => { if (!r.ok) throw new Error(`${p}: ${r.status} ${await r.text()}`); return r.json(); });
  let world = null, sendOk = true;
  // a Send in the demo goes nowhere: the decide is answered here as gone and recorded as sent (send-stays-on-closeout's road)
  page.off("request", page.fixtureRequestGuard);
  page.on("request", async (req) => {
    const rid = (new URL(req.url()).pathname.match(/^\/api\/reviews\/(\d+)\/decide$/) || [])[1];
    if (req.method() === "POST" && rid) {
      if (sendOk) await api(`/api/fixture/review/${rid}/sent`, {}).catch(() => {});
      return req.respond({ status: 200, contentType: "application/json", body: JSON.stringify({ ok: true, status: "approved", sent: { channel: "email" }, send_error: null }) });
    }
    page.fixtureRequestGuard(req);
  });
  const keys = () => world.keys;
  const keyOf = (sym) => {
    const m = /^F(\d)-F(\d)$/.exec(sym);
    return m ? Array.from({ length: m[2] - m[1] + 1 }, (_, i) => keys()[`F${+m[1] + i}`]) : keys()[sym];
  };
  const symOf = (k) => Object.entries(keys()).find(([, v]) => v === k)?.[0] || k;
  const look = () => page.evaluate(() => {
    const vis = (e) => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0 && r.top < innerHeight && r.bottom > 0; };
    const ring = [...document.querySelectorAll("[data-tq-rail] .tq-pile-row.current")].map((e) => e.getAttribute("data-tq-key"));
    const live = [...document.querySelectorAll(".tq-chat-body .tq-live-card, .tq-chat-body .tq-canvas-live")].filter(vis).filter((e) => e.innerText.trim().length > 10);
    const dots = [...document.querySelectorAll(".tq-typing")].some(vis);
    const back = document.querySelector("[data-tq-walk-back]");
    return { ring, item: live.length > 0, dots, back: back ? !back.disabled : null,
      rail: [...document.querySelectorAll("[data-tq-rail] .tq-pile-row[data-tq-key]")].map((e) => [e.closest("[data-tq-run]")?.dataset.tqRun, e.getAttribute("data-tq-key")]),
      walkChip: [...document.querySelectorAll("button")].some((b) => /^Walk me through/.test(b.textContent.trim()) && vis(b)),
      lines: document.querySelectorAll(".tq-msg:not(.you):not(.receipt)").length };
  });
  const settle = async (ms = 20000) => {
    let last = "", same = 0;
    for (const t0 = Date.now(); Date.now() - t0 < ms; ) {
      const s = await look(); const sig = JSON.stringify([s.ring, s.dots, s.rail.length]);
      same = sig === last && !s.dots ? same + 1 : 0; last = sig;
      if (same >= 6) return s;
      await sleep(250);
    }
    return look();
  };
  // New chat: pressed once it can be (never over a move in flight), then the empty chat's Walk, pressable
  const newChat = async () => {
    for (let i = 0; i < 3; i++) {
      await page.waitForFunction(() => { const b = document.querySelector('button[aria-label^="New chat"]'); return b && !b.disabled; }, { timeout: 30000 });
      await page.evaluate(() => document.querySelector('button[aria-label^="New chat"]')?.click());
      const ok = await page.waitForFunction(() => !document.querySelector(".tq-msg:not(.tq-welcome-msg)") && !!document.querySelector(".tq-welcome .tq-chip.primary:not([disabled])"),
        { timeout: 20000 }).then(() => true, () => false);
      if (ok) { await sleep(600); return; }
    }
    throw new Error("New chat did not empty the chat");
  };
  const remind = async () => { await doVerb(page, "remind"); await sleep(700); return clickText(page, /^Tomorrow/, ".MuiPopover-paper"); };
  const note = async () => {
    await doVerb(page, "close-note");
    await page.waitForSelector("[data-tq-close-note-card] textarea, [data-tq-closeout] textarea", { timeout: 10000 }).catch(() => {});
    await page.keyboard.type("Sorted with the floor team.");
    return (await clickText(page, /^Close with a note$/, "[data-tq-close-note-card]")) || clickText(page, /^Close with a note$/, ".tq-canvas-live");
  };
  const send = async () => {
    await page.waitForSelector("[data-tq-closeout]", { timeout: 15000 }).catch(() => {});
    return page.evaluate(() => { const b = [...document.querySelectorAll("[data-tq-closeout] button, .tq-canvas-live button")]
      .find((x) => /^Send\b/.test(x.textContent.trim()) && !x.disabled && x.offsetParent); if (b) { b.click(); return true; } return false; });
  };
  const LEAVE = { done: () => doVerb(page, "done"), note, remind, not_task: () => doVerb(page, "nat"), all_read: () => pressNext(page),
    put_on_list: () => doVerb(page, "w:mine") };
  const fixture = async (verb, sym) => { world = await api("/api/fixture/walk/do", { verb, sym: sym || null }); await sleep(2500); };
  // one step: true when it pressed something on the page (the recorder's to watch)
  const step = async (s) => {
    const [verb, ...args] = s.split(" ");
    if (verb === "start") {
      if (!(await page.$(".tq-welcome .tq-chip.primary:not([disabled])"))) await newChat();
      await page.evaluate(() => document.querySelector(".tq-welcome .tq-chip.primary")?.click()); return true;
    }
    if (verb === "new-chat") { await newChat(); return false; }
    if (verb === "next") { assert.ok(await pressNext(page), "Next is on the bar"); return true; }
    if (verb === "next-twice") { await page.evaluate(() => { const b = document.querySelector("[data-tq-row] [data-tq-next]"); b?.click(); b?.click(); }); return true; }
    if (verb === "next-to-end") {
      for (let i = 0; i < 30; i++) { await settle(); if ((await look()).walkChip || !(await pressNext(page))) return false; }
      throw new Error("the walk never reached its end");
    }
    // ...pressed where it is on; greyed at the top it presses nothing, and the case says what stays on screen (W07)
    if (verb === "back") { await page.evaluate(() => { const b = document.querySelector("[data-tq-walk-back]"); if (b && !b.disabled) b.click(); }); return true; }
    if (verb === "open") {
      const k = keyOf(args[0]);
      if (/^task:\d+$/.test(k)) { await page.evaluate((n) => { location.hash = `task=${n}`; }, k.slice(5)); return true; }
      assert.ok(await clickRow(page, k), `${args[0]} is a rail row`); return true;
    }
    if (verb === "heading") { await page.evaluate((l) => document.querySelector(`[data-tq-section-head="${l}"]`)?.click(), args[0]); return true; }
    if (verb === "leave") { assert.ok(await LEAVE[args[1]](), `${args[1]} pressed`); return true; }
    if (verb === "send") { sendOk = args[1] === "closes"; assert.ok(await send(), "Send pressed"); return true; }
    if (["arrive", "close-elsewhere", "agent-closes", "read"].includes(verb)) { await fixture(verb, args[0]); return false; }
    if (verb === "phone") { await fixture(`phone ${args[0]}`); return false; }
    if (verb === "reload") { await page.reload({ waitUntil: "domcontentloaded" }); await page.waitForSelector("[data-tq-rail] .tq-pile-row", { timeout: 40000 }); await sleep(2500); return false; }
    if (verb === "peek") { world = await api("/api/fixture/walk/keys", {}); assert.equal(symOf(world.below), args[0], "the prepared Next"); return false; }
    throw new Error(`no desk road for "${s}"`);
  };
  const record = () => page.evaluate(() => {
    window.__f = []; window.__rec = true;
    const vis = (e) => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0 && r.top < innerHeight && r.bottom > 0; };
    const tick = () => {
      if (!window.__rec) return;
      const live = [...document.querySelectorAll(".tq-chat-body .tq-live-card, .tq-chat-body .tq-canvas-live")].filter(vis).some((e) => e.innerText.trim().length > 10);
      const dots = [...document.querySelectorAll(".tq-typing")].some(vis);
      window.__f.push({ t: Math.round(performance.now()), item: live, dots, ring: [...document.querySelectorAll("[data-tq-rail] .tq-pile-row.current")].map((e) => e.getAttribute("data-tq-key")).join(",") });
      requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  });
  const stopRecord = () => page.evaluate(() => { window.__rec = false; return window.__f || []; });

  const results = [];
  for (const c of TABLE) {
    if (ONLY.length && !ONLY.includes(c.id)) continue;
    const b = c.browser || {};
    if (b.skip) { results.push({ id: c.id, result: "skip", why: b.skip }); continue; }
    try {
      world = await api("/api/fixture/walk/world", {});
      await page.reload({ waitUntil: "domcontentloaded" }); await page.waitForSelector("[data-tq-rail] .tq-pile-row", { timeout: 40000 });
      await newChat();
      for (const s of b.steps || c.steps) { await step(s); await settle(); }
      world = await api("/api/fixture/walk/keys", {});
      const before = await look(), prepared = world.below;
      const action = b.action || c.action, watched = RECORDED.test(action);
      if (watched) await record();
      await step(action);
      const after = await settle();
      const frames = watched ? await stopRecord() : [];
      world = await api("/api/fixture/walk/keys", {});
      const want = c.expect, why = [];
      const ringSyms = after.ring.map(symOf);
      if (want === "END") { if (after.ring.length) why.push(`wanted the end, ringed ${ringSyms}`); }
      else if (want === "NEW") { if (after.ring.length !== 1 || Object.values(keys()).includes(after.ring[0])) why.push(`wanted a new task, ringed ${ringSyms}`); }
      else {
        const k = keyOf(want), wantKeys = Array.isArray(k) ? k : [k];
        if (/^task:/.test(wantKeys[0] || "")) { if (world.on !== wantKeys[0]) why.push(`wanted ${want} on the table, the walk is on ${symOf(world.on)}`); }
        else if (JSON.stringify([...after.ring].sort()) !== JSON.stringify([...wantKeys].sort())) why.push(`wanted ${want}, ringed ${ringSyms.join(",") || "nothing"}`);
      }
      const onRail = (sym) => after.rail.some(([, k]) => k === keys()[sym]);
      for (const s of c.read || []) if (onRail(s)) why.push(`${s} should have been read off the rail`);
      for (const s of c.rail?.has || []) if (!onRail(s)) why.push(`${s} should be on the rail`);
      for (const s of c.rail?.not || []) if (onRail(s)) why.push(`${s} should be off the rail`);
      for (const s of c.later || []) if (!after.rail.some(([run, k]) => run === "later" && k === keys()[s])) why.push(`${s} should be under For later`);
      if ("back" in c && want !== "END" && after.back !== null && after.back !== c.back) why.push(`Back ${after.back ? "on" : "off"}, wanted ${c.back ? "on" : "off"}`);
      if (watched && frames.length) {
        const press = frames.findIndex((f) => true), blank = frames.slice(press + 1).filter((f) => !f.item && !f.dots);
        if (blank.length) why.push(`${blank.length} of ${frames.length} frames blank (first at ${blank[0].t - frames[0].t} ms)`);
        const okRing = new Set([before.ring.join(","), after.ring.join(","), prepared || "", "", ...(Array.isArray(keyOf(want)) ? [keyOf(want).join(",")] : [keyOf(want) || ""])]);
        const wrong = [...new Set(frames.map((f) => f.ring))].filter((r) => !okRing.has(r) && !r.split(",").every((k) => okRing.has(k)));
        if (wrong.length) why.push(`the ring stood on ${wrong.map((r) => r.split(",").map(symOf).join("+")).join(" / ")}`);
        if (after.lines - before.lines > 1) why.push(`${after.lines - before.lines} new lines for one press`);
      }
      results.push({ id: c.id, result: why.length ? "FAIL" : "pass", why: why.join("; "), frames: frames.length });
    } catch (e) { results.push({ id: c.id, result: "FAIL", why: String(e.message || e).slice(0, 300) }); }
    console.log(JSON.stringify(results.at(-1)));
  }
  if (process.env.WALK_TABLE_OUT) fs.writeFileSync(process.env.WALK_TABLE_OUT, JSON.stringify(results, null, 1));
  const failed = results.filter((r) => r.result === "FAIL");
  assert.deepEqual(failed, [], `${failed.length} of ${results.length} cases failed`);
  assert.deepEqual(errors, []);
});
