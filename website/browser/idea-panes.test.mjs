import assert from "node:assert/strict";
import test from "node:test";
import { boot, clickRow, findRow, sleep } from "./walkdriver.mjs";

/* AN ADVISOR IDEA COMES IN LIKE EVERYTHING ELSE (the owner, 2026-10-31: "it looks pretty dumb this idea ... it should go in the coming from tab
   like fyi's"): the rail's section says Advisor; on the table the idea opens in the three sections, its words, suggestion and the mail it is
   based on in Came from - no "advisor idea" card - its moves on Came from's strip, Send to agent on the Agent spine, and the bar Back and Next.
   On the demo world, an idea built by the fixture on an invented vendor's statement. */
const seen = (page, sel) => page.$$eval(sel, (bs) => bs.filter((b) => b.offsetParent && b.getBoundingClientRect().width > 0)
  .map((b) => b.textContent.trim() || b.getAttribute("aria-label")));

test("an Advisor idea opens in Came from under the rail's Advisor section, its moves on its panes", { timeout: 240000 }, async (t) => {
  const { page, errors } = await boot(t, { width: 1440, height: 900 });
  await page.evaluate(async () => (await fetch("/api/fixture/task/matrix", { method: "POST", body: JSON.stringify({ state: "idea_mail" }),
    headers: { "X-Taskuary-Token": localStorage.getItem("taskuary_token"), "Content-Type": "application/json" } })).json());
  await page.waitForFunction(() => [...document.querySelectorAll("[data-tq-rail] .tq-pile-row")].some((e) => /Payworth statement/.test(e.textContent)), { timeout: 30000 });
  assert.equal(await page.$eval('[data-tq-section-head="ideas"] .lvl-ideas', (e) => e.textContent.trim().toLowerCase()), "advisor", "the rail's section says Advisor");

  assert.ok(await clickRow(page, await findRow(page, /Payworth statement/)));
  await page.waitForSelector('[data-tq-item-sections="idea"] [data-tq-idea-from]', { timeout: 20000 }); await sleep(1500);
  const m = await page.evaluate(() => { const it = document.querySelector('[data-tq-item-sections="idea"]');
    return { main: it.querySelector("[data-tq-sections]").dataset.tqMain, slots: [...it.querySelectorAll("[data-tq-slot]")].map((s) => s.dataset.tqSlot),
      head: it.querySelector("[data-tq-item-head]").innerText.replace(/\s+/g, " "), from: it.querySelector("[data-tq-idea-from]").innerText,
      link: !!it.querySelector('[data-tq-idea-from] a[href^="#msg="]'), kicker: [...document.querySelectorAll(".tq-card-kicker")].map((e) => e.innerText) }; });
  assert.equal(m.main, "from");
  assert.deepEqual(m.slots, ["from", "agent", "close"]);
  assert.match(m.head, /^Advisor The Payworth statement still shows invoice 88213 open/);
  assert.match(m.from, /The Payworth statement still shows invoice 88213 open[\s\S]*Based on/);
  assert.ok(m.link, "the mail it is based on, one press away");
  assert.ok(!m.kicker.some((k) => /advisor idea/i.test(k)), `no advisor-idea card: ${m.kicker}`);
  // ...its moves on Came from's strip, Send to agent on the Agent spine, the bar Back and Next
  const strip = await seen(page, '[data-tq-pane-strip="from"] [data-tq-pane-moves] button');
  assert.ok(strip.includes("Not ours") && !strip.includes("Send to agent"), `Came from's strip: ${strip}`);
  assert.deepEqual(await seen(page, '[data-tq-section-tab="agent"] [data-tq-spine-moves] button'), ["Send to agent"]);
  assert.deepEqual(await seen(page, "[data-tq-row] button"), ["Back", "Next"]);
  assert.deepEqual(errors, []);
});
