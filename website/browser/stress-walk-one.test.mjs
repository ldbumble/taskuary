import test from "node:test";
import { back, clickRow, look, matrix, next, settle, sleep, start, verdict, walkChip } from "./stresswalk.mjs";

/* ONE ROW ON THE RAIL, EVERY WALK BUTTON HAMMERED ON IT (the owner, 2026-11-02: "test with ... just 1 task, fast and slow, pressing multiple
   times"). A task, a report or an FYI alone: Next ten times reads it once and ends the walk cleanly - a task stays in Tasks, a report or an FYI
   leaves - with no ghost row, no row twice, no error; Back ten times on it does nothing; Walk me through ten times puts it on the table once;
   and after the end, Walk me through again works. LONG-ish: run by name. */
const ONE = { task: { tasks: 1, reports: 0, fyi: 0, ideas: 0, meetings: 0 }, report: { tasks: 0, reports: 1, fyi: 0, ideas: 0, meetings: 0 },
  fyi: { tasks: 0, reports: 0, fyi: 1, ideas: 0, meetings: 0 } };
const ten = async (page, press, gap) => { for (let i = 0; i < 10; i++) { await press(page); await sleep(gap); } };
const bands = (s) => Object.entries(s.heads).filter(([, n]) => n).map(([b, n]) => `${b}:${n}`).join(" ");

const cases = [];
for (const [kind, world] of Object.entries(ONE)) for (const gap of [40, 400]) {
  cases.push({ id: `${kind}-next-x10-${gap}`, world, run: async ({ page, why, record }) => {
    const k = await start(page);
    await record(); await ten(page, next, gap);
    const s = await settle(page);
    if (!s.end) why.push("the walk did not end");
    const rail = s.rail.map(([, x]) => x);
    if (kind === "task" && (rail.length !== 1 || rail[0] !== k)) why.push(`the task should stay, alone: rail ${bands(s)}`);
    if (kind !== "task" && rail.length) why.push(`the ${kind} should be gone: rail ${bands(s)}`);
    // ...and Walk me through again
    await walkChip(page);
    const s2 = await settle(page);
    if (kind === "task" && s2.ring[0] !== k) why.push(`Walk again after the end did not put the task back on the table (ring ${s2.ring})`);
    if (kind !== "task" && s2.ring.length) why.push(`Walk again on an empty rail ringed ${s2.ring}`);
    return { refolds: 0 };
  } });
  cases.push({ id: `${kind}-back-x10-${gap}`, world, run: async ({ page, why, record }) => {
    const k = await start(page);
    await record(); await ten(page, back, gap);
    const s = await settle(page);
    if (s.ring[0] !== k) why.push(`Back on the only row moved the walk: ring ${s.ring}`);
    return { refolds: 0 };
  } });
  cases.push({ id: `${kind}-walk-x10-${gap}`, world, run: async ({ page, why, record }) => {
    const k = (await look(page)).rail[0]?.[1];
    await record(); await ten(page, walkChip, gap);
    const s = await settle(page);
    if (s.ring[0] !== k) why.push(`ten Walk me through: ring ${s.ring}, the only row is ${k}`);
    return { refolds: 0 };
  } });
}

test("one row, hammered", { timeout: 3 * 60 * 60 * 1000 }, async (t) => {
  verdict(await matrix(t, cases, { delays: (process.env.STRESS_DELAYS || "0,300,1500").split(",").map(Number) }));
});
