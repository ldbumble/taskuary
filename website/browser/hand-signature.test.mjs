import assert from "node:assert/strict";
import test from "node:test";

import { startHarness } from "./harness.mjs";

/* YOUR SIGNATURE (the owner, 2026-11-04: an agent signs a permission slip with "a signature I save once"): Settings > Replies holds the
   card. Drawn with the mouse on its pad and saved, the picture goes up once as a PNG cut to the ink, the card shows it back from the
   owner-only route, and Clear forgets it. The demo refuses writes, so /api/hand-signature is answered here the way handsign.py would:
   it keeps the bytes it was sent and hands the same bytes back (tests/test_sign_form.py holds the server to that). */
test("Settings > Your signature: draw it, save, see it, clear it", { timeout: 180000 }, async (t) => {
  const harness = await startHarness();
  t.after(() => harness.close());
  const page = await harness.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  let kept = null;
  const puts = [];
  page.off("request", page.fixtureRequestGuard);
  page.on("request", (r) => {
    const p = new URL(r.url()).pathname, json = (body) => r.respond({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
    const info = () => kept ? { saved: true, type: "image/png", width: kept.readUInt32BE(16), height: kept.readUInt32BE(20) } : { saved: false };
    if (p === "/api/hand-signature" && r.method() === "GET") return json(info());
    if (p === "/api/hand-signature" && r.method() === "PUT") {
      const { data } = JSON.parse(r.postData()); puts.push(data); kept = Buffer.from(data.replace(/^data:[^,]*,/, ""), "base64"); return json(info());
    }
    if (p === "/api/hand-signature" && r.method() === "DELETE") { kept = null; return json(info()); }
    if (p === "/api/hand-signature/image") return kept ? r.respond({ status: 200, contentType: "image/png", body: kept }) : r.respond({ status: 404, body: "" });
    page.fixtureRequestGuard(r);
  });
  await page.goto(`${harness.ui}#settings=config&group=Replies`, { waitUntil: "domcontentloaded", timeout: 90000 });
  const C = "[data-tq-hand-signature]";
  await page.waitForFunction((C) => /No signature saved/.test(document.querySelector(C)?.innerText || ""), { timeout: 60000 }, C);
  const press = (label) => page.evaluate((C, label) => [...document.querySelectorAll(`${C} button`)].find((b) => b.textContent.trim() === label).click(), C, label);
  const saved = () => page.evaluate(() => fetch("/api/hand-signature", { headers: { "X-Taskuary-Token": localStorage.getItem("taskuary_token") } }).then((r) => r.json()));

  // DRAW: Save waits for ink, then a stroke across the pad
  await press("Draw it");
  await page.waitForSelector(`${C} [data-tq-hand-signature-pad] canvas`);
  assert.equal(await page.$eval(C, (el) => [...el.querySelectorAll("button")].find((b) => b.textContent.trim() === "Save").disabled), true, "nothing drawn, nothing to save");
  await page.$eval(`${C} canvas`, (el) => el.scrollIntoView({ block: "center", behavior: "instant" }));
  // ...and still: Settings scrolls itself to the section it opened on, and a stroke drawn while it moves lands half off the pad
  let pad = null;
  for (let i = 0; i < 40; i++) {
    await new Promise((r) => setTimeout(r, 250));
    const now = await (await page.$(`${C} canvas`)).boundingBox();
    if (pad && now && Math.abs(now.y - pad.y) < 0.5 && Math.abs(now.x - pad.x) < 0.5) break;
    pad = now;
  }
  await page.mouse.move(pad.x + 40, pad.y + pad.height * 0.6);
  await page.mouse.down();
  for (let i = 1; i <= 24; i++) await page.mouse.move(pad.x + 40 + i * 14, pad.y + pad.height * (0.6 - 0.25 * Math.sin(i / 3)), { steps: 2 });
  await page.mouse.up();
  await press("Save");

  // ...SEE IT: the card shows the saved picture back, read through the owner-only route
  await page.waitForSelector(`${C} [data-tq-hand-signature-preview]`, { timeout: 15000 })
    .catch(async (e) => { throw new Error(`${e.message}: ${await page.$eval(C, (el) => el.innerText)} ${errors.join(" | ")}`); });
  await page.waitForFunction((C) => document.querySelector(`${C} [data-tq-hand-signature-preview]`)?.naturalWidth > 0, { timeout: 10000 }, C);
  assert.equal(puts.length, 1); assert.match(puts[0], /^data:image\/png;base64,/);
  assert.equal(kept.subarray(1, 4).toString(), "PNG");
  const got = await saved();
  assert.equal(got.saved, true);
  assert.ok(got.width > 200 && got.width <= 600 && got.height <= 240, `cut to the ink: ${got.width}x${got.height}`);
  assert.match(await page.$eval(C, (el) => el.innerText), /Draw a new one[\s\S]*Upload a picture[\s\S]*Clear/);

  // CLEAR: forgotten, and the card says so
  await press("Clear");
  await page.waitForFunction((C) => /No signature saved/.test(document.querySelector(C)?.innerText || ""), { timeout: 10000 }, C);
  assert.equal(await page.$(`${C} [data-tq-hand-signature-preview]`), null);
  assert.equal((await saved()).saved, false);
  assert.deepEqual(errors, []);
});
