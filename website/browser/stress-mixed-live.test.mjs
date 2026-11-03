import assert from "node:assert/strict";
import test from "node:test";
import { bootMixed, clean, look, noBlank, oneTable, pressNext, shot, sleep, startWalk, still } from "./stress-mixed-lib.mjs";

/* MIXED USE 5 - THE WORLD MOVES WHILE THE OWNER READS (the owner, 2026-11-02: "no crazy stuff"). On a row of the walk, new mail arrives
   through the real door (a task, an FYI, a report-like FYI, a burst of three in one poll) and an agent on another task finishes. Each time:
   the rows already on the rail keep their order (arrivals slot in, nothing old moves), the ring and the table stay on the row being read,
   the section headings' counts are the server's, no blank frame, no console error - with the server's answers held 0, 300 and 1500 ms. */
const at = (min) => { const d = new Date(Date.now() - min * 60000); return new Date(d - d.getTimezoneOffset() * 60000).toISOString().slice(0, 19).replace("T", " "); };
let n = 0;
const mail = (from_name, from_email, subject, body) => ({ external_id: `graph:stress-live-${++n}`, channel: "email", from_email, from_name, subject, body,
  conversation_id: `stress-live-${n}`, sent_at: at(0.1), to: ["alex@northwind.example"] });
const task = (title) => ({ intent: "task", kind: "task", why: "scripted", title, summary: title, asks_owner: true });
const fyi = (title) => ({ intent: "fyi", why: "scripted", title, summary: title });
// is `old` still in order inside `now` - every old row there, none swapped
const inOrder = (old, now) => { const ix = old.filter((k) => now.includes(k)).map((k) => now.indexOf(k)); return ix.every((v, i) => !i || v > ix[i - 1]); };
const heads = (page) => page.$$eval("[data-tq-rail] [data-tq-section-head]", (es) => Object.fromEntries(es.filter((e) => e.dataset.tqSectionHead)
  .map((e) => [e.dataset.tqSectionHead, Number((e.innerText.match(/(\d+)\s*$/) || [])[1])])));
const serverHeads = async (api) => { const p = await api("/api/funnel/pile"), by = (f) => p.items.filter(f).length;
  return { task: by((i) => !["report", "fyi"].includes(i.lane)), reports: by((i) => i.lane === "report"), fyi: by((i) => i.lane === "fyi") }; };

for (const delay of [0, 300, 1500]) {
  test(`arrivals and a finished agent mid-walk move nothing old and keep the table, server ${delay} ms`, { timeout: 420000 }, async (t) => {
    const { page, errors, api } = await bootMixed(t, { width: 1440, height: 900, delay });
    const coding = (await api("/api/fixture/task/coding-live", { runs: 0 })).taskId;
    await startWalk(page);
    for (let i = 0; i < 2; i++) { await pressNext(page); await still(page, 30000); }
    let s = await still(page, 30000);
    const reading = s.ring[0];
    assert.ok(reading, "the walk stands on a row");
    const events = [
      ["a task", () => api("/api/fixture/intake/arrive", { messages: [{ msg: mail("Paula Vance", "paula@vendor.example", "Payworth invoice 2210", "Please approve invoice 2210 by Friday."), verdict: task("Approve Payworth invoice 2210") }] })],
      ["an fyi", () => api("/api/fixture/intake/arrive", { messages: [{ msg: mail("Trainly", "news@vendor.example", "Your course is ready", "The spring course is live."), verdict: fyi("Trainly course is live") }] })],
      ["three in one poll", () => api("/api/fixture/intake/arrive", { messages: [
        { msg: mail("Erin Blake", "erin@northwind.example", "Badge for the new starter", "Can you order a badge for Monday?"), verdict: task("Order a badge for the new starter") },
        { msg: mail("Spendly", "noreply@vendor.example", "Weekly spend summary", "Spend is flat this week."), verdict: fyi("Spendly weekly summary") },
        { msg: mail("Gail Moreno", "gail@northwind.example", "Rota for next week", "Please sign off the rota."), verdict: task("Sign off next week's rota") }] })],
      ["an agent finishing", () => api("/api/fixture/task/coding-live/end", { taskId: coding })],
    ];
    for (const [what, fire] of events) {
      const was = await look(page);
      await fire();
      s = await still(page, 30000); await sleep(1500); s = await still(page, 30000);
      const where = `${what} while reading`;
      if (s.ring[0] !== reading || !inOrder(was.keys, s.keys)) await shot(page, `live-${delay}-${what.replace(/\W+/g, "_")}`);
      assert.equal(s.ring[0], reading, `${where}: the ring left the row being read ${JSON.stringify({ reading, ring: s.ring })}`);
      assert.ok(!s.items.length || s.items[0] === reading, `${where}: the table jumped away ${JSON.stringify(s.items)}`);
      assert.ok(inOrder(was.keys, s.keys), `${where}: an old row moved\nwas ${was.keys.join(" ")}\nnow ${s.keys.join(" ")}`);
      oneTable(s, where);
      const want = await serverHeads(api), got = await heads(page);
      for (const k of Object.keys(want)) if (k in got) assert.equal(got[k], want[k], `${where}: the ${k} heading says ${got[k]}, the server ${want[k]}`);
      await noBlank(page, where); clean(errors, where);
    }
    // ...and Next from here walks on from the row being read, not from where an arrival landed
    const below = s.keys[s.keys.indexOf(reading) + 1];
    assert.ok(below, "a row below");
    await pressNext(page); s = await still(page, 30000);
    if (s.ring[0] !== below) await shot(page, `live-${delay}-next-after`);
    assert.equal(s.ring[0], below, `Next after the arrivals is the row below the one read ${JSON.stringify({ below, ring: s.ring })}`);
    oneTable(s, "Next after the arrivals"); clean(errors, "Next after the arrivals");

    // ...and mail landing WHILE a Next is out: the press still lands on the row below, never on the arrival or back where it began
    const from = s.ring[0], next = s.keys[s.keys.indexOf(from) + 1];
    await pressNext(page);
    await api("/api/fixture/intake/arrive", { messages: [{ msg: mail("Omar Keller", "omar@northwind.example", "Export button greyed out", "The export button is greyed out again."),
      verdict: task("Export button greyed out") }] });
    s = await still(page, 30000); await sleep(1500); s = await still(page, 30000);
    if (s.ring[0] !== next) await shot(page, `live-${delay}-arrive-mid-press`);
    assert.equal(s.ring[0], next, `an arrival during a Next moved where it lands ${JSON.stringify({ from, next, ring: s.ring })}`);
    oneTable(s, "arrival mid-press"); await noBlank(page, "arrival mid-press"); clean(errors, "arrival mid-press");
  });
}
