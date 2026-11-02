import assert from "node:assert/strict";
import test from "node:test";

import { startHarness } from "./harness.mjs";

/* HOW MUCH REACHES THE AGENT (the owner, 2026-11-02: "tell the user the max amount of characters that go into the instructions, with
   a bar/percentage showing if you are over"). Settings > Docs > CODING.md draws one quiet line and a hairline bar over the words, from
   the server's own number; typing past it turns it red and says what happens to the rest. TRIAGE.md, which nothing cuts, has none. */

test("the Docs editor meters a document against the server's limit, live as you type", { timeout: 240000 }, async (t) => {
  const harness = await startHarness({ fresh: true });
  t.after(() => harness.close());
  const page = await harness.newPage(), errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(`${harness.ui}#settings=docs&doc=coding`, { waitUntil: "domcontentloaded", timeout: 90000 });
  await page.waitForSelector("[data-tq-doc-meter]", { timeout: 60000 });
  const read = () => page.$eval("[data-tq-doc-meter]", (e) => ({ tone: e.getAttribute("data-tq-doc-meter"), text: e.innerText.replace(/\s+/g, " ") }));
  let m = await read();
  assert.equal(m.tone, "ok");
  assert.match(m.text, /^[\d,]+ \/ 8,000 characters reach the agent \d+%$/);

  // past the limit: the words are set the way a paste sets them, and the meter follows without a save
  await page.evaluate(() => {
    const ta = [...document.querySelectorAll("textarea")].find((e) => e.value.includes("CODING.md"));
    Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value").set.call(ta, ta.value + " more".repeat(400));
    ta.dispatchEvent(new Event("input", { bubbles: true }));
  });
  await page.waitForFunction(() => document.querySelector("[data-tq-doc-meter]")?.getAttribute("data-tq-doc-meter") === "over");
  m = await read();
  assert.match(m.text, /over by [\d,]+ - the end is cut off/);
  assert.ok(await page.$('[data-tq-doc-meter] [role="meter"]'));

  await page.goto(`${harness.ui}#settings=docs&doc=triage`, { waitUntil: "domcontentloaded", timeout: 90000 });
  await page.waitForFunction(() => [...document.querySelectorAll("textarea")].some((e) => e.value.length > 1000), { timeout: 60000 });
  assert.equal(await page.$("[data-tq-doc-meter]"), null, "nothing cuts TRIAGE.md, so it has no meter");
  assert.deepEqual(errors, []);
});
