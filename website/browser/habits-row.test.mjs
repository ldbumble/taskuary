import assert from "node:assert/strict";
import test from "node:test";
import { boot, clickRow, findRow, rail, sleep } from "./walkdriver.mjs";

/* ONE ADVISOR ROW FOR ALL HABITS (habits.py; the owner, 2026-11-01: "how many advisor ideas do i have now? it's too many. what does keep
   it/remind me do here? doesn't make much sense"): every habit the Advisor learned sits on one rail row, "Learned 1 habit · 1 to check";
   opened, each is a sentence with the owner's name filled in and its own buttons - Not right on the adopted one, Adopt / No on the one it
   asks about - and the row has no Put it on my list, Remind me, Keep it or Not ours, and no Whose move or Suggestion. Answering the asked
   one leaves the row; moving on from it marks the adopted one seen, and the row goes. On the demo world, with invented habits. */
const seen = (page, sel) => page.$$eval(sel, (bs) => bs.filter((b) => b.offsetParent && b.getBoundingClientRect().width > 0)
  .map((b) => b.textContent.trim() || b.getAttribute("aria-label")));

test("the habits are one Advisor row, each with its own answer, and the row goes once they are answered and seen", { timeout: 240000 }, async (t) => {
  const { page, errors } = await boot(t, { width: 1440, height: 900 });
  await page.evaluate(async () => (await fetch("/api/fixture/task/matrix", { method: "POST", body: JSON.stringify({ state: "habits" }),
    headers: { "X-Taskuary-Token": localStorage.getItem("taskuary_token"), "Content-Type": "application/json" } })).json());
  await page.waitForFunction(() => [...document.querySelectorAll("[data-tq-rail] .tq-pile-row")].some((e) => /Learned \d+ habits? · \d+ to check/.test(e.textContent)),
    { timeout: 30000 });
  assert.equal((await rail(page)).filter((r) => /habit/i.test(r.text)).length, 1, "one row for every habit");
  const key = await findRow(page, /Learned \d+ habits? · \d+ to check/);
  assert.ok(await clickRow(page, key));
  await page.waitForSelector("[data-tq-habits] [data-tq-habit]", { timeout: 20000 }); await sleep(1000);
  const m = await page.evaluate(() => ({ text: document.querySelector("[data-tq-item-sections]").innerText,
    lines: [...document.querySelectorAll("[data-tq-habit]")].map((e) => ({ kind: e.dataset.tqHabit, text: e.innerText.replace(/\s+/g, " ") })) }));
  assert.ok(!m.text.includes("{{"), `no placeholder on the screen: ${m.text}`);
  assert.ok(!/Whose move|Suggestion/.test(m.text), "no Whose move or Suggestion on the habits row");
  const sso = m.lines.find((l) => /closes sign-in help threads/.test(l.text)), fyi = m.lines.find((l) => /Payworth desk/.test(l.text));
  assert.match(sso.text, /^\S+ closes sign-in help threads directly; they need no drafted reply \(seen 8 times\)\. Not right$/);
  assert.equal(sso.kind, "adopted");
  assert.match(fyi.text, /needs no reply \(seen 2 times\)\. Adopt No$/);
  const strip = await seen(page, '[data-tq-item-sections] button');
  for (const w of ["Put it on my list", "Remind me", "Keep it", "Not ours", "Send to agent", "Make a task"]) assert.ok(!strip.includes(w), `no ${w}: ${strip}`);
  // ...No on the asked one: the row stays, holding what is left
  await page.evaluate(() => [...document.querySelectorAll("[data-tq-habit='ask']")].find((e) => /Payworth desk/.test(e.innerText))
    .querySelectorAll("button")[1].click());
  await page.waitForFunction(() => ![...document.querySelectorAll("[data-tq-habit]")].some((e) => /Payworth desk/.test(e.innerText)), { timeout: 15000 });
  const left = await page.evaluate(async () => (await (await fetch("/api/assistant/ideas?status=open", { headers: { "X-Taskuary-Token": localStorage.getItem("taskuary_token") } })).json())
    .data.filter((i) => i.kind === "habit"));
  assert.equal(left.length, 1);
  assert.ok(!left[0].action.habits.some((h) => /Payworth desk/.test(h.say)) && !JSON.stringify(left).includes("{{"));
  // ...and moving on from it marks the adopted ones seen: nothing is open, the row goes
  const other = (await rail(page)).find((r) => r.key !== key && !/habit/i.test(r.text));
  assert.ok(await clickRow(page, other.key));
  const open = () => page.evaluate(async () => (await (await fetch("/api/assistant/ideas?status=open", { headers: { "X-Taskuary-Token": localStorage.getItem("taskuary_token") } })).json())
    .data.filter((i) => i.kind === "habit").length);
  for (let i = 0; i < 30 && await open(); i++) await sleep(500);
  assert.equal(await open(), 0, "answered and seen: the habits row is closed");
  await page.waitForFunction(() => ![...document.querySelectorAll("[data-tq-rail] .tq-pile-row")].some((e) => /habit/i.test(e.textContent)), { timeout: 30000 });
  assert.deepEqual(errors, []);
});
