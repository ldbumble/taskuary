// THE STRONG MODEL BOX (the router, 2026-10-25): each AI card gets a third box, blank by default, whose blank means "this brain
// does not step up" - nothing is guessed from a model's name. Against a fresh install's real server: the box is there and says so,
// a name typed into it is saved on the brain that owns it, and a save the server refuses is said on the page, never swallowed.
import assert from "node:assert/strict";
import test from "node:test";
import { startHarness } from "./harness.mjs";

const CARD = '[data-tq-knob~="triage_ai"]';
const STRONG = `${CARD} input[placeholder="none, this brain doesn't step up"]`;

test("the strong model box: blank says no step-up, a name is saved on the brain, a refused save is said", { timeout: 240000 }, async (t) => {
  const harness = await startHarness({ fresh: true }); t.after(() => harness.close());
  const api = (p, body, method = body ? "POST" : "GET") => fetch(`${harness.fixtureApi}${p}`, { method,
    headers: { "Content-Type": "application/json", "X-Taskuary-Token": harness.token }, body: body && JSON.stringify(body) }).then((r) => r.json());
  const conns = (await api("/api/connectors")).data, key = conns.find((c) => c.Type === "anthropic");
  await api("/api/connectors", { ConnectorId: key.ConnectorId, Secret: "sk-test-not-a-real-key-000000", Active: true });
  await api("/api/settings", { name: "triage_ai", value: `connector:${key.ConnectorId}` }, "PATCH");
  const slot = async () => (await api("/api/ai/defaults")).slots.find((s) => s.key === "triage_ai");
  assert.equal((await slot()).strong_model, "", "blank on a fresh card");

  const page = await harness.newPage(), errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  const until = (f, arg, timeout = 30000) => page.waitForFunction(f, { timeout, polling: 200 }, arg).catch(async (e) => {
    throw new Error(`${e.message} waiting for ${String(f).slice(0, 160)}\n${(await page.evaluate(() => document.body.innerText)).slice(-1500)}`);
  });
  await page.goto(`${harness.ui}#settings=config&group=${encodeURIComponent("How mail is sorted")}`, { waitUntil: "domcontentloaded", timeout: 90000 });
  await until((sel) => document.querySelector(sel), STRONG, 90000);
  assert.match(await page.$eval(CARD, (e) => e.innerText), /strong model/);
  // ...and Drafting has its own card beside it, blank meaning the triage brain it always wrote on (the owner, 2026-10-25)
  const drafting = await page.$eval('[data-tq-knob~="draft_ai"]', (e) => e.innerText);
  assert.match(drafting, /Drafting/); assert.match(drafting, /blank = the triage brain, as before/);

  // a name typed in and left: saved on the Anthropic card's own config, and read back on the card
  await page.click(STRONG); await page.keyboard.type("claude-opus-5"); await page.keyboard.press("Tab");
  for (let i = 0; i < 50 && (await slot()).strong_model !== "claude-opus-5"; i++) await new Promise((r) => setTimeout(r, 200));
  assert.equal((await slot()).strong_model, "claude-opus-5", "saved on the brain");
  const config = JSON.parse((await api("/api/connectors")).data.find((c) => c.ConnectorId === key.ConnectorId).ConfigJson || "{}");
  assert.equal(config.strong_model, "claude-opus-5", "...on the card that owns it");

  // the failure road: the server refuses the save, and the page says why instead of looking saved
  page.off("request", page.fixtureRequestGuard);
  page.on("request", (r) => {
    if (r.method() === "POST" && new URL(r.url()).pathname === "/api/ai/defaults")
      return r.respond({ status: 422, contentType: "application/json", body: JSON.stringify({ detail: "no brain on this card to set a strong model on" }) });
    page.fixtureRequestGuard(r);
  });
  await page.click(STRONG, { clickCount: 3 }); await page.keyboard.type("claude-sonnet-5"); await page.keyboard.press("Tab");
  await until(() => /no brain on this card to set a strong model on/.test(document.body.innerText));
  assert.equal((await slot()).strong_model, "claude-opus-5", "a refused save changed nothing");
  assert.deepEqual(errors, []);
});
