import assert from "node:assert/strict";
import test from "node:test";
import { boot, clickRow, clickText, doVerb, findRow, folded, sleep } from "./walkdriver.mjs";

/* CLOSE WITH A NOTE FOLDS WEARING ITS OWN BADGE AND THE NOTE (typed-put-down-acts, 2026-10-23; the 2026-10-25 sweep, N6): at the press the
   card read "✓ Mark done" with no note, and only a reload drew the server's stamp - "✓ Close with a note" and the note under it. */
test("Close with a note wears its badge and its note at the press, the same as after a reload", { timeout: 180000 }, async (t) => {
  const { page, errors } = await boot(t);
  const worn = async () => (await folded(page)).filter((f) => /New starter/.test(f.title)).map(({ badge, note }) => ({ badge, note }));
  await clickRow(page, await findRow(page, /New starter/)); await sleep(3000);
  assert.ok(await doVerb(page, "close-note")); await sleep(800);
  await page.keyboard.type("Handled by Erin Blake on the phone");
  assert.ok(await clickText(page, /^Close with a note$/, "[data-tq-close-note-card]")); await sleep(4000);
  const atPress = await worn();
  assert.deepEqual(atPress, [{ badge: "Close with a note", note: "Handled by Erin Blake on the phone" }]);
  await page.reload({ waitUntil: "domcontentloaded" }); await page.waitForSelector("[data-tq-folded]", { timeout: 30000 }); await sleep(4000);
  assert.deepEqual(await worn(), atPress, "the badge changed across a reload");
  assert.deepEqual(errors, []);
});
