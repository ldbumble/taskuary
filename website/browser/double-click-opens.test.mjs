import assert from "node:assert/strict";
import test from "node:test";
import { boot, clickRow, findRow, sleep } from "./walkdriver.mjs";

/* A DOUBLE-CLICK OPENS, IT DOES NOT OPEN AND SHUT (the overnight walk, 2026-10-27; the owner, 2026-10-26: "if you click a button twice it
   won't reload"): a double-click on Ask sender, Find a time or a ▾ opened its dialog or menu with the first click, and the second landed on
   that dialog's backdrop and shut it - the press looked dead (secondClick.js). One OS double-click each, the way a mouse sends it. */
async function dbl(page, find) {
  const at = await page.evaluate(find);
  assert.ok(at, `nothing to press: ${find}`);
  await page.mouse.click(at.x, at.y, { clickCount: 1 }); await page.mouse.click(at.x, at.y, { clickCount: 2 });
  await sleep(900);
}
const rowButton = (re) => new Function(`const b = [...document.querySelectorAll("[data-tq-row] button")].find((n) => ${re}.test(n.textContent.trim()) && !n.disabled
  && n.getBoundingClientRect().width > 0); if (!b) return null; const r = b.getBoundingClientRect(); return { x: r.x + r.width / 2, y: r.y + r.height / 2 };`);
const up = (page) => page.evaluate(() => [...document.querySelectorAll("[role=dialog], [role=menu], .MuiPopover-paper")]
  .filter((d) => d.getBoundingClientRect().width > 0).map((d) => d.innerText.replace(/\s+/g, " ").slice(0, 300)));
const shut = async (page) => { for (let i = 0; i < 3; i++) { await page.keyboard.press("Escape"); await sleep(250); } };

test("a double-click on Ask sender, Find a time or a ▾ leaves what it opened open", { timeout: 240000 }, async (t) => {
  const { page, errors } = await boot(t, { width: 1600, height: 810 });
  await clickRow(page, await findRow(page, /Month-end close is short/)); await sleep(2500);
  await dbl(page, rowButton("/^Ask sender$/"));
  assert.ok((await up(page)).some((d) => /Ask the sender/.test(d)), `Ask sender: ${JSON.stringify(await up(page))}`);
  await shut(page);
  await dbl(page, () => { const b = document.querySelector("[data-tq-row] [data-tq-more]"); const r = b?.getBoundingClientRect(); return r ? { x: r.x + r.width / 2, y: r.y + r.height / 2 } : null; });
  assert.ok((await page.$$("[role=menu] [role=menuitem]")).length > 0, "the ▾ menu shut itself");
  await shut(page);
  await clickRow(page, await findRow(page, /Half an hour on the audit/)); await sleep(2500);
  await dbl(page, rowButton("/^Find a time$/"));
  assert.ok((await up(page)).some((d) => /Or pick a day/.test(d)), `Find a time: ${JSON.stringify(await up(page))}`);
  // ...and a click on the backdrop a moment later still shuts it
  await sleep(600); await page.mouse.click(5, 400); await sleep(700);
  assert.deepEqual(await up(page), [], "a later click outside did not shut it");
  assert.deepEqual(errors, []);
});
