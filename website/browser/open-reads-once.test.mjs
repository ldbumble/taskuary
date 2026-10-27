import assert from "node:assert/strict";
import test from "node:test";
import { boot, clickRow, findRow, sleep } from "./walkdriver.mjs";

/* OPENING A TASK READS EACH THING ONCE (the overnight walk, 2026-10-27; the owner, 2026-10-26: "things don't load twice"). Every GET the
   page sends while two drafted replies are opened in turn, counted by path. */
async function opened(t, rows) {
  const { page, errors } = await boot(t, { width: 1600, height: 810 });
  const gets = [];
  page.on("request", (r) => { if (r.method() === "GET" && /\/api\//.test(r.url())) gets.push(new URL(r.url()).pathname + new URL(r.url()).search); });
  const per = [];
  for (const re of rows) {
    const from = gets.length;
    await clickRow(page, await findRow(page, re));
    await page.waitForSelector("[data-tq-canvas-item] [data-tq-task-body]", { timeout: 20000 }); await sleep(4000);
    per.push(gets.slice(from));
  }
  return { page, errors, per };
}

test("To and Cc share one read of everyone, and a second draft opened reads nobody again", { timeout: 180000 }, async (t) => {
  const { errors, per } = await opened(t, [/Invoice 88213/, /Can you confirm the AP cutover/]);
  const people = per.flat().filter((u) => u === "/api/people");
  assert.ok(people.length <= 1, `/api/people read ${people.length} times over two drafts`);
  assert.deepEqual(errors, []);
});
