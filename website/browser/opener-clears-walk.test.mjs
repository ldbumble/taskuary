import assert from "node:assert/strict";
import { mkdirSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { boot, pressNext, sleep } from "./walkdriver.mjs";

/* THE DAY'S OPENER CLEARS THE WALK AND LEADS THE CHAT (the owner, 2026-11-01: "when the morning digest opens let's clear the walk through
   otherwise it's confusing on the table but greeting is. let's move the greeting all the way to the top always"). The opener was recorded
   in the live chat under the last walk's lines, so a folded task card stood over "Good morning", and the rail row kept "on the table".
   On the demo world: walk onto the second row, be away seventeen hours, come back - the greeting is the first line, nothing is on the
   table, and Walk me through my tasks starts from the top again. */
const until = async (f, ms = 15000) => { for (const t0 = Date.now(); Date.now() - t0 < ms; await sleep(250)) if (await f()) return true; return false; };
const ring = (page) => page.evaluate(() => document.querySelector("[data-tq-rail] .tq-pile-row.current")?.getAttribute("data-tq-key") || "");
const walk = (page) => page.evaluate(() => {
  const b = [...document.querySelectorAll(".tq-asst-col button")].find((n) => /^Walk me through my tasks$/.test(n.textContent.trim()) && !n.disabled && n.offsetParent);
  if (b) b.click(); return !!b;
});
const shots = process.env.TASKUARY_SHOTS || "";

test("the day's opener puts the walk down and is the first line of the chat", { timeout: 300000 }, async (t) => {
  const { h, page, errors } = await boot(t, { width: 1366, height: 768 });
  const shot = async (name) => { if (shots) { mkdirSync(shots, { recursive: true }); await page.screenshot({ path: path.join(shots, `${name}.png`) }); } };
  assert.ok(await until(() => walk(page)), "the day opens with its Walk");
  assert.ok(await until(async () => !!(await ring(page))), "the walk put the top row on the table");
  const top = await ring(page);
  await sleep(2500);
  assert.ok(await pressNext(page), "the top row has a Next");
  assert.ok(await until(async () => !["", top].includes(await ring(page))), "Next moved the table down a row");
  await sleep(2500);
  await shot("1-walking");

  // ...seventeen hours away, and back: the page arrives and the opener is drawn
  const r = await fetch(`${h.fixtureApi}/api/fixture/day/away`, { method: "POST", headers: { "X-Taskuary-Token": h.token, "Content-Type": "application/json" }, body: "{}" });
  assert.ok(r.ok, `day/away: ${r.status}`);
  assert.ok(await until(() => page.evaluate(() => !!document.querySelector(".tq-chat-inner .tq-welcome-msg")), 20000), "the opener is drawn");
  await sleep(3000);
  await shot("2-opener");
  const seen = await page.evaluate(() => {
    const kids = [...document.querySelector(".tq-chat-inner").children].filter((e) => e.offsetHeight > 0);
    return { first: kids[0]?.matches(".tq-welcome-msg") || !!kids[0]?.querySelector(".tq-welcome-msg"), head: kids[0]?.innerText.slice(0, 80) || "",
      cards: kids.slice(0, kids.findIndex((e) => e.matches(".tq-welcome-msg") || e.querySelector(".tq-welcome-msg"))).map((e) => e.innerText.slice(0, 60)),
      ringed: document.querySelector("[data-tq-rail] .tq-pile-row.current")?.getAttribute("data-tq-key") || "",
      tagged: /on the table/i.test(document.querySelector("[data-tq-rail]")?.innerText || "") };
  });
  assert.ok(seen.first, `the greeting is the first line, not ${JSON.stringify(seen.head)} (above it: ${JSON.stringify(seen.cards)})`);
  assert.match(seen.head, /Good (morning|afternoon|evening)/);
  assert.equal(seen.ringed, "", "no rail row is on the table under the greeting");
  assert.ok(!seen.tagged, "no rail row says on the table");

  // ...and the walk starts from the top again
  assert.ok(await until(() => walk(page)), "the opener's Walk is pressable");
  assert.ok(await until(async () => (await ring(page)) === top, 20000), `the walk started at ${await ring(page)}, not the top row ${top}`);
  await sleep(1500);
  await shot("3-walk-again");
  assert.deepEqual(errors, []);
});
