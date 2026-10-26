import assert from "node:assert/strict";
import test from "node:test";
import { boot, sleep } from "./walkdriver.mjs";

/* A REFUSED PRESS ON SAVED SIGN-INS IS SAID ON ITS ROW, AND THE LIST STAYS (the 2026-10-26 sweep; click-the-failure-path): a refused Remove
   replaced the whole Saved sign-ins block with its error until a reload, and a refused Remove authenticator key said nothing at all. The
   list is served by the page's own request handler (one invented site), and the vault refuses every change. */
const ROWS = { data: [{ site: "portal.vendor.example", saved: Date.now() / 1000 - 86400, used: 0, code: true }] };
test("a refused Remove or Remove authenticator key is said on its row, and the list stays to try again", { timeout: 180000 }, async (t) => {
  const { page, errors } = await boot(t, { width: 1440, height: 1000 });
  page.off("request", page.fixtureRequestGuard);
  page.on("request", (r) => {
    const p = new URL(r.url()).pathname;
    if (p === "/api/signins" && r.method() === "GET") return r.respond({ status: 200, contentType: "application/json", body: JSON.stringify(ROWS) });
    if (p.startsWith("/api/signins/") && r.method() !== "GET")
      return r.respond({ status: 500, contentType: "application/json", body: JSON.stringify({ detail: "The vault is locked just now." }) });
    page.fixtureRequestGuard(r);
  });
  await page.goto(page.url().split("#")[0] + "#settings=config&group=Agent%20permissions", { waitUntil: "domcontentloaded" });
  const S = "[data-tq-saved-signins]";
  await page.waitForSelector(S, { timeout: 30000 }); await sleep(1500);
  const state = () => page.evaluate((S) => ({ list: /portal\.vendor\.example/.test(document.querySelector(S)?.innerText || ""),
    said: [...document.querySelectorAll(`${S} [data-tq-signin-err]`)].map((e) => e.textContent) }), S);
  const press = (re) => page.evaluate((S, src) => [...document.querySelectorAll(`${S} button`)].find((b) => new RegExp(src).test(b.textContent.trim())).click(), S, re.source);

  await press(/^Remove authenticator key$/); await sleep(1500);
  assert.deepEqual(await state(), { list: true, said: ["The vault is locked just now."] }, "a refused Remove authenticator key said nothing on its row");
  await press(/^Remove$/); await sleep(1500);
  assert.deepEqual(await state(), { list: true, said: ["The vault is locked just now."] }, "a refused Remove took the list away");
  assert.ok(await page.evaluate((S) => [...document.querySelectorAll(`${S} button`)].some((b) => b.textContent.trim() === "Remove" && !b.disabled), S),
    "Remove cannot be pressed again");
  assert.deepEqual(errors, []);
});
