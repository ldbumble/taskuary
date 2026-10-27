// SIGN IN WITH MICROSOFT GOES TO THE BROWSER (an enterprise IT department, 2026-10-27: Conditional Access blocks device-code
// authentication as a known phishing vector). The card's button opens Microsoft's page - the authorization-code flow with PKCE,
// back to this server on localhost - and the device code is only the small "Sign in with a code instead" beside it. The server's
// answers are stood in for at the page and window.open is recorded, so nothing reaches Microsoft.
import assert from "node:assert/strict";
import test from "node:test";
import { clickNav, startHarness } from "./harness.mjs";

const until = (page, f, arg, timeout = 30000) => page.waitForFunction(f, { timeout, polling: 200 }, arg).catch(async (e) => {
  throw new Error(`${e.message} waiting for ${String(f).slice(0, 200)}\n${(await page.evaluate(() => document.body.innerText)).slice(-1500)}`);
});
const press = (page, label) => page.evaluate((l) => {
  const b = [...document.querySelectorAll("[data-tq-browse-one] button")].find((e) => e.innerText.trim() === l && e.getBoundingClientRect().width > 0);
  b?.click(); return !!b;
}, label);
const type = (page, sel, v) => page.evaluate((sel, v) => {
  const i = document.querySelector(sel), set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set;
  set.call(i, v); i.dispatchEvent(new Event("input", { bubbles: true }));
}, sel, v);
const AUTHORIZE = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize?client_id=app&code_challenge_method=S256&state=s";

test("Outlook: Sign in with Microsoft opens the browser sign-in, and the code is the secondary link", { timeout: 600000 }, async (t) => {
  const harness = await startHarness(); t.after(() => harness.close());
  const page = await harness.newPage(), errors = [], starts = [], cancels = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.evaluateOnNewDocument(() => { window.__opened = []; window.open = (u) => { window.__opened.push(String(u)); return null; }; });
  const list = await (await fetch(`${harness.fixtureApi}/api/connectors`, { headers: { "X-Taskuary-Token": harness.token } })).json();
  const ol = list.data.find((c) => c.Type === "outlook");
  page.off("request", page.fixtureRequestGuard);
  page.on("request", (r) => {
    const p = new URL(r.url()).pathname, json = (body) => r.respond({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
    // the card as it is before anyone signed in: no account, no secret
    if (p === "/api/connectors" && r.method() === "GET")
      return json({ ...list, data: list.data.map((c) => c.ConnectorId === ol.ConnectorId ? { ...c, HasSecret: false, SignedOut: false, ConfigJson: "{}" } : c) });
    if (p === `/api/connectors/${ol.ConnectorId}/ms/signin`) {
      const body = JSON.parse(r.postData() || "{}"); starts.push(body);
      return json(body.code ? { flow: `f${starts.length}`, mode: "code", user_code: "ABCD-1234", verification_uri: "https://microsoft.com/devicelogin", expires_in: 900, interval: 5 }
        : { flow: `f${starts.length}`, mode: "browser", url: AUTHORIZE, expires_in: 600 });
    }
    if (p === `/api/connectors/${ol.ConnectorId}/ms/poll`) return json({ status: "pending" });
    if (p === `/api/connectors/${ol.ConnectorId}/ms/cancel`) { cancels.push(JSON.parse(r.postData() || "{}").flow); return json({ ok: true }); }
    page.fixtureRequestGuard(r);
  });
  await page.goto(harness.ui, { waitUntil: "domcontentloaded", timeout: 90000 });
  await page.waitForSelector("[data-tq-nav='connections']", { timeout: 120000 });
  await clickNav(page, "Connections");
  await page.waitForSelector("[data-tq-browse-search]", { timeout: 30000 });
  await type(page, "[data-tq-browse-search]", "outlook");
  await page.waitForSelector(`[data-tq-browse-card="c${ol.ConnectorId}"] [data-tq-card]`, { timeout: 30000 });
  await page.click(`[data-tq-browse-card="c${ol.ConnectorId}"] [data-tq-card]`);
  await page.waitForSelector("[data-tq-browse-one]");
  await until(page, () => /Sign in with Microsoft/.test(document.querySelector("[data-tq-browse-one]")?.innerText || ""));

  // 1. the main button is the browser sign-in: no code asked for, Microsoft's page opened, the card waits for the tab
  assert.ok(await press(page, "Sign in with a code instead"), "the code is offered, as the secondary link");
  await until(page, () => /ABCD-1234/.test(document.body.innerText));
  assert.equal(starts.at(-1).code, true);
  assert.ok(await press(page, "Cancel"));
  await until(page, () => !/ABCD-1234/.test(document.body.innerText));
  assert.ok(await press(page, "Sign in with Microsoft"));
  await until(page, () => /browser tab that opened/.test(document.querySelector("[data-tq-browse-one]")?.innerText || ""));
  assert.equal(starts.at(-1).code, false, "the default is the browser sign-in");
  assert.deepEqual(await page.evaluate(() => window.__opened), [AUTHORIZE], "Microsoft's page was opened");
  assert.doesNotMatch(await page.evaluate(() => document.querySelector("[data-tq-browse-one]").innerText), /ABCD-1234|devicelogin/);

  // 2. from the wait, the code is still one press away - and the browser round is forgotten on the server
  assert.ok(await press(page, "Sign in with a code instead"));
  await until(page, () => /ABCD-1234/.test(document.body.innerText));
  assert.equal(starts.at(-1).code, true);
  assert.ok(cancels.includes(`f${starts.length - 1}`), `the browser round was cancelled: ${cancels}`);
  assert.deepEqual(errors, []);
});
