import test from "node:test";
import { agree, frames, next, open, record, report, server, settle, shot, sleep, start, stopRecord, verdict, walkChip, look } from "./stresswalk.mjs";

/* NEXT, OVER AND OVER, TO THE END (the owner, 2026-11-02: "clicking Next on 50 tasks in a row ... everything still looks smooth"). On the big world
   (~100 tasks, 15 reports, 30 FYI in batches of four, ideas, meetings), Next pressed at a reading pace (600 ms) and fast (120 ms) through Tasks,
   Reports, Ideas and FYI to the end, then Walk me through again - at 1440x900 and 1280x800, with the walk's answers held 0/300/1500 ms. Every
   frame recorded: never blank over 100 ms, no row twice, rows never reorder, the ring only ever goes down. Settled: ring, card and the server's
   walk agree, passed reports and FYI are gone, every task stays. LONG (minutes): run by name. STRESS_CASES=1440/0/600,... picks cases. */
const ONLY = (process.env.STRESS_CASES || "").split(",").filter(Boolean);
const CASES = [];
for (const [w, hh] of [[1440, 900], [1280, 800]]) for (const delay of [0, 300, 1500]) for (const pace of [600, 120]) CASES.push({ w, hh, delay, pace, id: `${w}/${delay}/${pace}` });

test("Next pressed through the whole big world, then Walk me through again", { timeout: 3 * 60 * 60 * 1000 }, async (t) => {
  const h = await server(t), rows = [];
  for (const c of CASES) {
    if (ONLY.length && !ONLY.includes(c.id)) continue;
    const why = [], { page, errors, api, close, name } = await open(h, { width: c.w, height: c.hh, delay: c.delay, world: { tasks: +(process.env.STRESS_TASKS || 100) } });
    try {
      const tasks0 = (await look(page)).heads.task;
      await start(page);
      await record(page);
      let presses = 0, missed = 0;
      const t0 = Date.now();
      for (; presses + missed < 900; ) {
        const s = await look(page);
        if (s.end) break;
        if (await next(page)) presses++; else missed++;
        await sleep(c.pace);
      }
      const ms = Date.now() - t0;
      await settle(page);
      const f = frames(await stopRecord(page));
      if (f.blank > 100) why.push(`blank ${f.blank} ms`);
      if (f.dups.length) why.push(`rows twice: ${f.dups.slice(0, 3)}`);
      if (f.moved.length) why.push(`rows reordered: ${f.moved}`);
      if (f.up) why.push(`the ring went up ${f.up} times on Next alone`);
      const { s } = await agree(page, api, why);
      if (!s.end) why.push(`never reached the end (${presses} presses, ${missed} greyed)`);
      if (s.heads.task !== tasks0) why.push(`Tasks went ${tasks0} -> ${s.heads.task}`);
      for (const b of ["reports", "fyi", "ideas"]) if (s.heads[b]) why.push(`${s.heads[b]} ${b} left after walking past them`);
      // ...and Walk me through again starts at the top
      if (!(await walkChip(page))) why.push("no Walk me through at the end");
      const s2 = await settle(page);
      const top = s2.rail[0]?.[1];
      if (s2.ring[0] !== top) why.push(`Walk again ringed ${s2.ring} not the top row ${top}`);
      await agree(page, api, why);
      if (errors.length) why.push(...errors.slice(0, 5));
      const r = { id: c.id, presses, missed, ms, frames: f.n, blankMs: f.blank, blankAt: f.blankAt, draw: f.draw, worstFrameMs: f.worstFrame, ringDown: f.down, ups: f.ups.map(name), blankCtx: f.blankCtx?.map(name), why: why.map(name) };
      if (why.length) r.shot = await shot(page, `next-${c.id}`);
      rows.push(r);
    } catch (e) { rows.push({ id: c.id, why: [String(e.message || e).slice(0, 300)], shot: await shot(page, `next-${c.id}-threw`) }); }
    report([rows.at(-1)]);
    await close();
  }
  verdict(rows);
});
