// THE COMBINE SLIDER (the owner, 2026-10-29): a message connection's card shows how readily triage joins its messages into one task,
// 1 "Keep separate" .. 5 "Combine", read from the server and saved when it is let go. The save is the server's answer, stood in for at
// the page as the other card tests do; nothing leaves the fixture.
import assert from "node:assert/strict";
import test from "node:test";
import { clickNav, startHarness } from "./harness.mjs";

// a card that shows its setup steps without a sign-in first; the Microsoft cards open on their sign-in
const COMBINED = ["whatsapp", "telegram", "slack", "discord", "imessage", "imap", "gmail", "teams", "outlook"];
const until = (page, f, arg, timeout = 30000) => page.waitForFunction(f, { timeout, polling: 200 }, arg).catch(async (e) => {
  throw new Error(`${e.message} waiting for ${String(f).slice(0, 200)}\n${(await page.evaluate(() => document.body.innerText)).slice(-1500)}`);
});
const type = (page, sel, v) => page.evaluate((sel, v) => {
  const i = document.querySelector(sel);
  Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set.call(i, v); i.dispatchEvent(new Event("input", { bubbles: true }));
}, sel, v);

test("a message connection's card shows the combine slider at its level and saves a move", { timeout: 300000 }, async (t) => {
  const harness = await startHarness(); t.after(() => harness.close());
  const page = await harness.newPage(), errors = [], puts = [];
  page.on("pageerror", (e) => errors.push(e.message));
  const list = await (await fetch(`${harness.fixtureApi}/api/connectors`, { headers: { "X-Taskuary-Token": harness.token } })).json();
  const conn = COMBINED.map((t) => list.data.find((c) => c.Type === t)).find(Boolean);
  assert.ok(conn, "the demo world has a message connection");
  page.off("request", page.fixtureRequestGuard);
  page.on("request", (r) => {
    const p = new URL(r.url()).pathname;
    if (p.startsWith("/api/combine/") && r.method() === "PUT") {
      puts.push([p, JSON.parse(r.postData() || "{}")]);
      return r.respond({ status: 200, contentType: "application/json", body: JSON.stringify({ ok: true, level: puts.at(-1)[1].level }) });
    }
    page.fixtureRequestGuard(r);
  });
  await page.goto(harness.ui, { waitUntil: "domcontentloaded", timeout: 90000 });
  await page.waitForSelector("[data-tq-nav='connections']", { timeout: 120000 });
  await clickNav(page, "Connections");
  await page.waitForSelector("[data-tq-browse-search]", { timeout: 30000 });
  await type(page, "[data-tq-browse-search]", conn.Name || conn.Type);
  await page.waitForSelector(`[data-tq-browse-card="c${conn.ConnectorId}"] [data-tq-card]`);
  // pressed until the card opens: a list still settling under the search can move it from under a single press
  for (let i = 0; i < 5 && !(await page.$("[data-tq-browse-one]")); i++) {
    await page.evaluate((sel) => document.querySelector(sel)?.click(), `[data-tq-browse-card="c${conn.ConnectorId}"] [data-tq-card]`);
    await page.waitForSelector("[data-tq-browse-one]", { timeout: 3000 }).catch(() => {});
  }
  await until(page, () => [...document.querySelectorAll("[data-tq-browse-one] .MuiStepButton-root")].some((b) => /Inbound — what becomes work/.test(b.innerText)));
  await page.evaluate(() => [...document.querySelectorAll("[data-tq-browse-one] .MuiStepButton-root")].find((b) => /Inbound — what becomes work/.test(b.innerText)).click());
  await page.waitForSelector('[data-testid="combine-level"] input[type="range"]');
  const kind = ["outlook", "gmail", "imap"].includes(conn.Type) ? "email" : conn.Type;
  const want = ["whatsapp", "email"].includes(kind) ? 4 : 3;
  await until(page, (w) => Number(document.querySelector('[data-testid="combine-level"] input[type="range"]').value) === w, want);
  const shown = await page.evaluate(() => document.querySelector('[data-testid="combine-level"]').innerText);
  assert.match(shown, /Separate/); assert.match(shown, /Combine/);

  await page.focus('[data-testid="combine-level"] input[type="range"]');
  await page.keyboard.press("ArrowRight");
  await until(page, (w) => Number(document.querySelector('[data-testid="combine-level"] input[type="range"]').value) === w + 1, want);
  for (const t0 = Date.now(); !puts.length && Date.now() - t0 < 5000;) await new Promise((r) => setTimeout(r, 50));
  assert.deepEqual(puts.at(-1), [`/api/combine/${kind}`, { level: want + 1 }]);
  assert.deepEqual(errors, []);
});
