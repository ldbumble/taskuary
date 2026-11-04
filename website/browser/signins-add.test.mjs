import assert from "node:assert/strict";
import test from "node:test";
import { boot, sleep } from "./walkdriver.mjs";

/* A SITE'S SIGN-IN SAVED AHEAD OF TIME, UNDER CONNECTIONS (the owner, 2026-11-03: "we probably should have space on connector to fill out what
   the system requires"): Connections > Sign-ins opens the vault's own list; Add a sign-in takes the site, user name and password, posts them
   once, and the list then names the site - never what was typed, and the boxes are emptied. The vault is the page's own request handler
   here (one invented site). */
test("Connections > Sign-ins: a sign-in added ahead of time is posted once and listed by its site alone", { timeout: 180000 }, async (t) => {
  const { page, errors } = await boot(t, { width: 1440, height: 1000 });
  const rows = [], posted = [];
  page.off("request", page.fixtureRequestGuard);
  page.on("request", (r) => {
    const p = new URL(r.url()).pathname;
    if (p === "/api/signins" && r.method() === "GET") return r.respond({ status: 200, contentType: "application/json", body: JSON.stringify({ data: rows }) });
    if (p === "/api/signins" && r.method() === "POST") {
      posted.push(JSON.parse(r.postData() || "{}"));
      rows.push({ site: "payworth.example", saved: Date.now() / 1000, used: 0, code: false });
      return r.respond({ status: 200, contentType: "application/json", body: JSON.stringify({ ok: true, site: "payworth.example" }) });
    }
    page.fixtureRequestGuard(r);
  });
  await page.goto(page.url().split("#")[0] + "#connections=Sign-ins", { waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => [...document.querySelectorAll("button, [role=button], div")].some((b) => b.textContent.trim().startsWith("Saved sign-ins")
    && b.closest("[data-tq-browse-card]")), { timeout: 30000 });
  await page.evaluate(() => [...document.querySelectorAll("[data-tq-browse-card] button, [data-tq-browse-card] [role=button]")]
    .find((b) => /Saved sign-ins/.test(b.textContent))?.click());
  const S = "[data-tq-saved-signins]";
  await page.waitForSelector(`${S} [data-tq-signin-add-open]`, { timeout: 30000 });
  await page.click(`${S} [data-tq-signin-add-open]`);
  await page.waitForSelector("[data-tq-signin-add]");
  const box = async (label, text) => {
    const h = await page.evaluateHandle((label) => [...document.querySelectorAll("[data-tq-signin-add] label")]
      .find((l) => l.textContent.replace("*", "").trim() === label)?.parentElement?.querySelector("input"), label);
    await h.asElement().type(text);
  };
  await box("Site", "https://login.payworth.example/start");
  await box("User name", "alex@northwind.example");
  await box("Password", "correct-horse-9!");
  await page.evaluate(() => [...document.querySelectorAll("[data-tq-signin-add] button")].find((b) => b.textContent.trim() === "Save to vault").click());
  await page.waitForFunction((S) => /payworth\.example/.test(document.querySelector(S)?.innerText || ""), { timeout: 15000 }, S);
  await sleep(500);
  assert.deepEqual(posted, [{ site: "https://login.payworth.example/start", user: "alex@northwind.example", password: "correct-horse-9!", key: "" }]);
  const shown = await page.evaluate(() => document.body.innerText + [...document.querySelectorAll("input")].map((i) => i.value).join(" "));
  assert.match(shown, /Saved your payworth\.example sign-in to the vault\./);
  assert.doesNotMatch(shown, /correct-horse-9!|alex@northwind\.example/, "nothing typed is shown back or left in a box");
  assert.deepEqual(errors, []);
});
