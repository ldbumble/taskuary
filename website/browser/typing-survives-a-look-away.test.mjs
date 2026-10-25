import assert from "node:assert/strict";
import test from "node:test";
import { boot, clickRow, findRow, rail, sleep } from "./walkdriver.mjs";

/* WHAT THE OWNER TYPED SURVIVES A LOOK ELSEWHERE (the 2026-10-25 navigation sweep, N18): an edit to a reply draft, and the words in the
   agent's "What should it do?", lived in the card's own state - a look at Reports or another row drew the task again, and the filed draft
   and an empty box came back with nothing said. */
const DRAFT = (x) => !x.placeholder && x.getBoundingClientRect().width > 0 && x.getAttribute("aria-hidden") !== "true";
const draft = (page) => page.evaluate((f) => [...document.querySelectorAll("textarea")].find(new Function(`return (${f})`)())?.value ?? null, DRAFT.toString());
const nav = (page, k) => page.evaluate((k) => document.querySelector(`[data-tq-nav="${k}"]`)?.click(), k);

test("a reply draft's edit and the agent box's words are still there after Reports or another row", { timeout: 240000 }, async (t) => {
  const { page, errors } = await boot(t, { width: 1440 });
  const invoice = await findRow(page, /Invoice 88213/), other = (await rail(page))[0].key;
  for (const [name, away] of [["Reports", () => nav(page, "reports")], ["another row", () => clickRow(page, other)]]) {
    await clickRow(page, invoice);
    await page.waitForFunction(() => [...document.querySelectorAll("textarea")].some((x) => !x.placeholder && x.value.length > 10), { timeout: 20000 });
    await page.evaluate((f) => { const x = [...document.querySelectorAll("textarea")].find(new Function(`return (${f})`)()); x.focus(); x.setSelectionRange(x.value.length, x.value.length); }, DRAFT.toString());
    await page.keyboard.type(" Regards, Alex"); await sleep(1500);
    const before = await draft(page);
    await away(); await sleep(3000);
    await clickRow(page, invoice); await sleep(3500);
    assert.equal(await draft(page), before, `${name}, then the row: the edited draft was lost`);
  }
  await clickRow(page, other); await sleep(3000);
  const box = await page.waitForSelector("textarea[placeholder^='What should it do']", { timeout: 10000 });
  await box.click(); await page.keyboard.type("check the bank feed first"); await sleep(1500);
  await nav(page, "reports"); await sleep(2500); await clickRow(page, other); await sleep(3500);
  assert.equal(await page.$eval("textarea[placeholder^='What should it do']", (x) => x.value).catch(() => null), "check the bank feed first");
  assert.deepEqual(errors, []);
});
