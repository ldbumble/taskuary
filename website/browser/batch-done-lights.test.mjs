import assert from "node:assert/strict";
import test from "node:test";
import { boot, clickRow, findRow, pressNext, sleep, type } from "./walkdriver.mjs";

/* "DONE" OVER THE OPEN BATCH LIGHTS ITS OWN BUTTON (the 2026-10-25 navigation sweep, N13): with the 4 fyi on the table and its All read, next on
   screen, a typed "done" was answered "There is nothing to close on 4 fyi ... Open it if you want its own buttons." - the card was open,
   and nothing was lit. The router lights the real button and says nothing (assistant-is-a-router). */
test("done typed over the fyi batch lights All read, next and tells nobody to open it", { timeout: 180000 }, async (t) => {
  const { page, errors } = await boot(t);
  await clickRow(page, await findRow(page, /Regional operations newsletter/)); await sleep(3000);
  assert.ok(await pressNext(page)); await sleep(5000);
  const next = () => page.$eval("[data-tq-row] [data-tq-next]", (b) => ({ text: b.textContent.trim(), lit: b.classList.contains("p") }));
  assert.equal((await next()).text, "All read, next", "the batch is not on the table");
  await type(page, "done"); await sleep(6000);
  const said = await page.$$eval(".tq-msg", (els) => els.map((e) => e.innerText.replace(/\s+/g, " ")));
  assert.ok(!said.some((s) => /Open it if you want its own buttons/.test(s)), "the answer told the owner to open the card that is open");
  assert.deepEqual(await next(), { text: "All read, next", lit: true }, "its own button was not lit");
  assert.deepEqual(errors, []);
});
