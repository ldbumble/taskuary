import assert from "node:assert/strict";
import { mkdir, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import { startHarness } from "./harness.mjs";
import { note, record } from "./recorder.mjs";

/* THE ITEM'S OWN PRESSES ON THE WALK (rules part 4: "every press leaves a line in the chat in the owner's voice and reaches the agent once"; the
   overnight audit, 2026-11-10). The demo world, walked from the day card: Not for me, Remind me (Tomorrow) and a DOUBLE-CLICKED Mark done, each
   on the item on the table. Each one moves the walk on to the row the rail marked next, takes its own row off the rail, leaves the other rows
   where they were, and leaves its line in its task's chat (Not for me, which deletes the task, its "Removed ... Undo" on the rail); the double-click closes one task, never the one drawn under the second click. Then
   the server restarts mid-walk and the page reloads: the walk is where he was. Recorded. */
const out = path.join(process.env.TEMP || os.tmpdir(), "claude", "n17");
const read = (page) => page.evaluate(() => {
  const rows = [...document.querySelectorAll("[data-tq-rail] .tq-pile-row[data-tq-key]")].filter((e) => !e.classList.contains("settling"));
  return { keys: rows.map((e) => e.getAttribute("data-tq-key")), on: rows.filter((e) => /\bcurrent\b/.test(e.className)).map((e) => e.getAttribute("data-tq-key")),
    next: rows.find((e) => /\bnext\b/.test(e.className))?.getAttribute("data-tq-key") || null,
    title: document.querySelector("[data-tq-canvas-item] [data-tq-task-page]")?.querySelector("h1, h2, h3, h4, h5, h6, [class*=Typography]")?.innerText || "" };
});
// ...the item's own button, on the item - never the bar's, never the rail's
const spot = (page, re) => page.evaluate((src) => { const b = [...document.querySelectorAll(".tq-asst-col button, [role=menuitem], .MuiPopover-paper button, .MuiDialog-paper button")].find((x) => new RegExp(src).test(x.innerText.trim())
  && !x.disabled && x.getBoundingClientRect().width > 0 && !x.closest("[data-tq-row], [data-tq-rail]")); if (!b) return null; const q = b.getBoundingClientRect(); return { x: q.x + q.width / 2, y: q.y + q.height / 2 }; }, re);
const hand = async (page, re, count = 1) => { const p = await spot(page, re); if (p) await page.mouse.click(p.x, p.y, { count }); return !!p; };
const settled = async (page, from) => { const t0 = Date.now(); let s;
  do { await new Promise((r) => setTimeout(r, 150)); s = await read(page); } while (Date.now() - t0 < 15000 && (!s.on.length || JSON.stringify(s.on) === JSON.stringify(from)));
  await new Promise((r) => setTimeout(r, 1500)); return { ...(await read(page)), ms: Date.now() - t0 }; };

test("on the walk, Not for me, Remind me and a double-clicked Mark done each move on once, leave the rows alone and leave their line; a restart keeps the walk", { timeout: 600000 }, async (t) => {
  const h = await startHarness();
  t.after(() => h.close());
  const page = await h.newPage();
  await page.setViewport({ width: 1600, height: 900 });
  const errors = [], tids = new Map();
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("response", async (r) => { if (!/\/api\/walk\/(start|next|back|open|leave)$/.test(new URL(r.url()).pathname)) return;
    try { const i = (await r.json())?.item; if (i?.key && i.tid) tids.set(i.key, i.tid); } catch { /* not json */ } });
  const api = (p) => fetch(`${h.fixtureApi}${p}`, { headers: { "X-Taskuary-Token": h.token } }).then((r) => r.json());
  await page.goto(h.ui, { waitUntil: "domcontentloaded" });
  const name = process.env.N17_NAME || "walk-presses", dir = path.join(out, "video", name); await mkdir(dir, { recursive: true });
  await page.waitForFunction(() => [...document.querySelectorAll("button")].some((b) => /^Walk me through my tasks/.test(b.innerText.trim())), { timeout: 60000 });
  const rec = await record(page, dir), steps = [], bad = [];
  try {
    await page.evaluate(() => [...document.querySelectorAll("button")].find((b) => /^Walk me through my tasks/.test(b.innerText.trim()))?.click());
    let s = await settled(page, []);
    await page.evaluate(() => [...document.querySelectorAll("[data-tq-row] button")].find((b) => /^Next$/.test(b.innerText.trim()) && !b.disabled)?.click());
    s = await settled(page, s.on);
    // ...each press on the row on the table, by a hand; `line`: its words in its task's chat (general.PRESSES)
    for (const [what, re, pick, line, count] of [["Not for me", "^Not for me$", null, /said it is not for them/, 1],
      ["Remind me", "^Remind me$", "^Tomorrow$", /set a reminder for/, 1], ["Mark done, double-clicked", "^Mark done$", null, /marked it done/, 2]]) {
      const was = s, key = s.on[0], want = s.next, tid = tids.get(key), below = s.keys.slice(s.keys.indexOf(want) + 1, s.keys.indexOf(want) + 2)[0];
      if (!(await hand(page, re, count))) { bad.push(`${what}: no such button on ${key}`); break; }
      if (pick) { await page.waitForFunction((src) => [...document.querySelectorAll("[role=menuitem], .MuiPopover-paper button")].some((x) => new RegExp(src).test(x.innerText.trim())), { timeout: 10000 }, pick).catch(() => {});
        if (!(await hand(page, pick))) { bad.push(`${what}: no ${pick} to pick`); break; } }
      // ...a Not for me puts the task away whole (server.not_mine): its record is the rail's own "Removed ... Undo", not a chat left behind
      const undo = what === "Not for me" ? await page.waitForFunction(() => /Removed .*Undo/s.test(document.querySelector("[data-tq-rail]")?.innerText || ""), { timeout: 5000 }).then(() => true, () => false) : null;
      s = await settled(page, was.on);
      const kept = was.keys.filter((k) => k !== key && s.keys.includes(k)), now = s.keys.filter((k) => kept.includes(k));
      const chat = undo != null ? "" : tid ? JSON.stringify(await api(`/api/tasks/${tid}/assistant`)) : "";
      const step = { what, from: key, to: s.on, want, ms: s.ms, gone: !s.keys.includes(key), line: undo ?? line.test(chat) };
      steps.push(step);
      if (JSON.stringify(s.on) !== JSON.stringify([want])) bad.push(`${what}: landed on ${s.on.join(",")}, the rail marked ${want} next`);
      if (!step.gone) bad.push(`${what}: its row stayed on the rail`);
      if (JSON.stringify(kept) !== JSON.stringify(now)) bad.push(`${what}: the other rows moved`);
      if (!step.line) bad.push(`${what}: ${undo != null ? "no Removed / Undo on the rail" : `no line in its task's chat (TQ ${tid})`}`);
      // ...the second click never reached the row it drew: the one under it is still on the rail, still open
      if (count > 1 && below && !s.keys.includes(below)) bad.push(`${what}: the second click took ${below} too`);
      if (count > 1 && tids.get(want)) { const t2 = await api(`/api/tasks/${tids.get(want)}`); if ((t2?.task || t2)?.Status === "done") bad.push(`${what}: the second click closed ${want}`); }
    }
    // ...A RESTART MID-WALK: the server goes down and comes back, the page reloads - the walk stands where he was
    const here = s.on;
    await h.restart();
    await page.reload({ waitUntil: "domcontentloaded" });
    const t0 = Date.now(); let r;
    do { await new Promise((x) => setTimeout(x, 300)); r = await read(page); } while (Date.now() - t0 < 30000 && !r.on.length);
    await new Promise((x) => setTimeout(x, 2000)); r = await read(page);
    steps.push({ what: "restart", before: here, after: r.on });
    if (JSON.stringify(r.on) !== JSON.stringify(here)) bad.push(`restart: the walk stood on ${here.join(",")}, after the reload on ${r.on.join(",") || "nothing"}`);
  } finally {
    await page.screenshot({ path: path.join(out, `${name}.png`) });
    await rec.stop();
    await writeFile(path.join(dir, "steps.json"), JSON.stringify(steps, null, 1));
    await note(dir, { done: "The demo world walked from the day card to its second row; there, by a hand on the item: Not for me; Remind me -> Tomorrow; Mark done double-clicked. Then the server restarted and the page reloaded.",
      expect: "Each press moves the walk on to the row the rail marked next, takes its row off the rail, leaves the others where they were and leaves its line in its task's chat; the double-click closes one task; after the restart the walk stands where it was.",
      saw: bad.length ? bad.join("\n") : `as expected: ${steps.map((x) => `${x.what} ${x.ms ?? ""}`.trim()).join("; ")}`, verdict: bad.length ? "FAIL" : "PASS" });
  }
  assert.deepEqual(bad, []);
  assert.deepEqual(errors, []);
});

// AN ARRIVAL MID-WALK NEVER MOVES THE ROWS (the owner, 2026-10-22: rows by arrival never move; Next walks down). A home with three mail tasks;
// the walk stands on the first; a fourth mail arrives. The table stays on his row, the three keep their order, and Next lands on the row that
// was marked next before it came. Recorded
test("a mail arriving mid-walk leaves the table and the rows where they were, and Next goes on where it would have", { timeout: 300000 }, async (t) => {
  const h = await startHarness({ fresh: true });
  t.after(() => h.close());
  const post = (p, body) => fetch(`${h.fixtureApi}${p}`, { method: "POST", headers: { "Content-Type": "application/json", "X-Taskuary-Token": h.token },
    body: JSON.stringify(body) }).then((r) => r.json());
  await post("/api/setup/dismiss", { dismissed: true });
  for (const [i, title] of ["Budget sign-off for Q4", "Badge for the new starter", "Vendor review for Erin"].entries())
    await post("/api/fixture/mail-task", { title, sent: `2026-11-10 0${7 + i}:00:00` });
  const page = await h.newPage();
  await page.setViewport({ width: 1600, height: 900 });
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(h.ui, { waitUntil: "domcontentloaded" });
  const name = process.env.N17_NAME ? `${process.env.N17_NAME}-arrival` : "walk-arrival", dir = path.join(out, "video", name); await mkdir(dir, { recursive: true });
  await page.waitForFunction(() => [...document.querySelectorAll("button")].some((b) => /^Walk me through my tasks/.test(b.innerText.trim()) && !b.disabled), { timeout: 60000 });
  const rec = await record(page, dir), bad = [];
  let before = null, after = null, last = null;
  try {
    await page.evaluate(() => [...document.querySelectorAll("button")].find((b) => /^Walk me through my tasks/.test(b.innerText.trim()))?.click());
    before = await settled(page, []);
    await post("/api/fixture/mail-task", { title: "Parking pass renewal", sent: "2026-11-10 10:00:00" });
    const t0 = Date.now();
    do { await new Promise((r) => setTimeout(r, 250)); after = await read(page); } while (Date.now() - t0 < 20000 && after.keys.length <= before.keys.length);
    await new Promise((r) => setTimeout(r, 1500)); after = await read(page);
    if (after.keys.length <= before.keys.length) bad.push("the new mail never reached the rail");
    if (JSON.stringify(after.on) !== JSON.stringify(before.on)) bad.push(`the table moved: ${before.on.join(",")} -> ${after.on.join(",")}`);
    if (JSON.stringify(after.keys.filter((k) => before.keys.includes(k))) !== JSON.stringify(before.keys)) bad.push("the rows already there moved");
    await page.evaluate(() => [...document.querySelectorAll("[data-tq-row] button")].find((b) => /^Next$/.test(b.innerText.trim()) && !b.disabled)?.click());
    last = await settled(page, after.on);
    if (JSON.stringify(last.on) !== JSON.stringify([before.next])) bad.push(`Next landed on ${last.on.join(",")}, not ${before.next} - the row marked next before the mail came`);
  } finally {
    await page.screenshot({ path: path.join(out, `${name}.png`) });
    await rec.stop();
    await note(dir, { done: "A home with three mail tasks; the walk on the first; a fourth mail arrives; then Next.",
      expect: "The table stays on his row, the rows keep their order with the new one added, and Next lands on the row marked next before it came.",
      saw: bad.length ? bad.join("\n") : `as expected: rows ${before?.keys.length} -> ${after?.keys.length}, Next to ${last?.on.join(",")}`, verdict: bad.length ? "FAIL" : "PASS" });
  }
  assert.deepEqual(bad, []);
  assert.deepEqual(errors, []);
});
