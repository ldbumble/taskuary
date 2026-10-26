import assert from "node:assert/strict";
import test from "node:test";

import { startHarness } from "./harness.mjs";

/* THE ONE-TIME SIGN-IN PAGE, SUBMITTED IN A REAL CHROMIUM (the computer-use walk, 2026-10-25): served with no-referrer, its form posted
   `Origin: null`, the token gate refused it, and every fill in Chrome and Edge answered "This sign-in came from another page" - while
   the tests, posting through TestClient with no Origin at all, passed. Here the real browser submits the real form. No agent-browser
   runs in the fixture, so the fill stops at "the task's browser is not open": past the Origin check, which is the point. Invented
   site and credentials only. */
test("the fill page names its task and its own form gets past the Origin check", { timeout: 180000 }, async (t) => {
  const harness = await startHarness();
  t.after(() => harness.close());
  const page = await harness.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  // the fill page is the backend's own, as in the app: let this one origin through the fixture's guard
  page.off("request", page.fixtureRequestGuard);
  page.on("request", (r) => (new URL(r.url()).origin === harness.fixtureApi ? r.continue() : page.fixtureRequestGuard(r)));
  await page.goto(harness.ui, { waitUntil: "domcontentloaded", timeout: 30000 });
  const made = await page.evaluate(async () => (await fetch("/api/fixture/signin/link", { method: "POST", body: "{}",
    headers: { "Content-Type": "application/json", "X-Taskuary-Token": localStorage.getItem("taskuary_token") } })).json());
  assert.match(made.url || "", /^\/signin\//, JSON.stringify(made));

  await page.goto(`${harness.fixtureApi}${made.url}`, { waitUntil: "domcontentloaded", timeout: 30000 });
  let text = await page.$eval("main", (el) => el.innerText);
  assert.match(text, /Sign in to\s+northwind\.example/);
  assert.match(text, /for TQ-\d{4} · Pay the Payworth invoice/, "the page says which task the password goes to");
  assert.match(text, /Authenticator setup key/); assert.doesNotMatch(text, /otpauth:\/\//);
  assert.equal(await page.$eval('meta[name="referrer"]', (m) => m.content), "same-origin");

  await page.type("#u", "alex@northwind.example");
  await page.type("#p", "invented-password-1");
  let origin = "";
  page.on("request", (r) => { if (r.method() === "POST" && r.url().includes("/signin/")) origin = r.headers().origin || ""; });
  await Promise.all([page.waitForNavigation({ waitUntil: "domcontentloaded", timeout: 30000 }), page.click("button[type=submit]")]);
  text = await page.$eval("main", (el) => el.innerText);
  assert.doesNotMatch(text, /came from another page/, `refused as cross-origin (Origin: ${origin || "none"})`);
  assert.match(text, /Nothing was signed in: the task's browser is not open/);
  assert.notEqual(origin, "null", "Chromium sends the page's real origin");
  assert.deepEqual(errors, []);
});
