import assert from "node:assert/strict";
import test from "node:test";
import { boot, clickRow, clickText, doVerb, findRow, pressNext, ringed, sleep, bubbles } from "./walkdriver.mjs";

/* A PUT-DOWN WALKS ON THE WAY NEXT DOES (the 2026-10-25 navigation sweep, N1): from the bottom task - a goal's step - Next went down to the
   first report, but Remind me and Mark done walked back UP to the goal just above it. Both arrive in the same second, and with the step gone
   from the rail the walk read on from its place's clock alone. And Remind me's warning that the day is past the due date wore a success
   tick (N9). */
const BOTTOM = /schema sign-off/, GOAL = /Migrate the census/, REPORT = /Headcount by site/;
for (const how of ["next", "remind", "done"]) {
  test(`${how} on the last task goes down to the first report`, { timeout: 180000 }, async (t) => {
    const { page, errors } = await boot(t);
    await clickRow(page, await findRow(page, BOTTOM)); await sleep(3000);
    if (how === "next") assert.ok(await pressNext(page));
    if (how === "remind") { assert.ok(await doVerb(page, "remind")); await sleep(600); assert.ok(await clickText(page, /^Tomorrow/)); }
    if (how === "done") assert.ok(await doVerb(page, "done"));
    await sleep(4500);
    const at = await ringed(page);
    assert.ok(REPORT.test(at) && !GOAL.test(at), `${how} on the last task landed on ${at}`);
    if (how === "remind") assert.deepEqual((await bubbles(page)).filter((b) => b.who === "receipt" && /^✓ That is after it is due/.test(b.text)), [],
      "a warning about the day wore a success tick");
    assert.deepEqual(errors, []);
  });
}
