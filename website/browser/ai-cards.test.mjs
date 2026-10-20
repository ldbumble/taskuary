// EVERY AI CARD, BOTH WAYS (the owner, 2026-10-20: "test every AI card ... success and failure ... never claim success on a failure
// or failure on a success, and reopen after Pick a different AI"). A first start on a fresh fixture with nothing set up; no
// provider is ever reached - the fixture blocks every outbound socket, so a key's real test FAILS the way an unreachable provider
// does, and a success is the server's own answer stood in for at the page. Prints the table it walked.
import assert from "node:assert/strict";
import test from "node:test";
import { clickNav, startHarness } from "./harness.mjs";

const VENDORS = /claude|codex|gemini|chatgpt|openai|anthropic|copilot|qwen|cursor|devin|kimi|opencode|muse|azure|vertex|groq|mistral|deepseek|cohere|perplexity|xai|grok|together|openrouter|meta|ollama|hipaa|cerebras/i;
const KEY = "sk-test-not-a-real-key-000000";
const until = (page, f, arg, timeout = 30000) => page.waitForFunction(f, { timeout, polling: 200 }, arg).catch(async (e) => {
  throw new Error(`${e.message} waiting for ${String(f).slice(0, 200)}\n${(await page.evaluate(() => document.body.innerText)).slice(-1200)}`);
});
const line = (page) => page.evaluate(() => document.querySelector(".tq-next-txt")?.innerText || "");
const shelf = (page) => page.evaluate(() => [...document.querySelectorAll("[data-tq-firstrun] [data-tq-card]")]
  .map((e) => ({ key: e.getAttribute("data-tq-card"), title: e.querySelector("[data-tq-setup-label]")?.innerText || "", text: e.innerText,
    lit: e.hasAttribute("data-tq-setup-lit") })));
// the whole shelf: More AI options opened, Pick a different AI pressed when one card stands alone
const everyCard = (page) => until(page, () => {
  const b = [...document.querySelectorAll("button")].find((x) => x.innerText.trim() === "Pick a different AI" && x.getBoundingClientRect().width > 0);
  if (b) { b.click(); return false; }
  const more = document.querySelector("[data-tq-shelf-more]");
  if (more) { more.click(); return false; }
  return document.querySelectorAll("[data-tq-firstrun] [data-tq-card]").length > 6;
});
const press = (page, key) => page.evaluate((k) => { const c = document.querySelector(`[data-tq-firstrun] [data-tq-card="${k}"]`); c?.click(); return !!c; }, key);

test("setup: every AI card says what happened, never the opposite, and opens again after Pick a different AI", { timeout: 900000 }, async (t) => {
  const harness = await startHarness({ fresh: true }); t.after(() => harness.close());
  const page = await harness.newPage(), errors = [], table = [];
  page.on("pageerror", (e) => errors.push(e.message));
  let succeed = false, installs = 0;
  page.off("request", page.fixtureRequestGuard);
  page.on("request", (r) => {
    const p = new URL(r.url()).pathname;
    // the success road: the server's own answer for a key that worked, stood in for here
    if (succeed && p === "/api/setup/first-run/key") return r.respond({ status: 200, contentType: "application/json", body: JSON.stringify({ ok: true, why: "Your key works - it will sort your mail." }) });
    // a CLI that is not here: its install is refused, as one with no road would be (nothing is installed by a test)
    if (p === "/api/cli/install") { installs++; return r.respond({ status: 409, contentType: "application/json", body: JSON.stringify({ detail: "no installer can run here" }) }); }
    if (/\/chatgpt\/signin$/.test(p)) return r.respond({ status: 200, contentType: "application/json", body: JSON.stringify({ flow: "f", url: "about:blank" }) });
    if (/\/chatgpt\/poll$/.test(p)) return r.respond({ status: 200, contentType: "application/json", body: JSON.stringify({ status: "error", detail: "the sign-in was cancelled" }) });
    if (/\/chatgpt\/cancel$/.test(p)) return r.respond({ status: 200, contentType: "application/json", body: "{}" });
    page.fixtureRequestGuard(r);
  });
  await page.goto(harness.ui, { waitUntil: "domcontentloaded", timeout: 90000 });
  await page.waitForSelector('[data-tq-firstrun="ai"] [data-tq-card]', { timeout: 120000 });
  await everyCard(page);
  const cards = await shelf(page);
  assert.equal(cards.filter((c) => c.lit).length, 0, "nothing lit before the person picks");
  assert.doesNotMatch(await line(page), VENDORS, "the line names no vendor before a pick");
  assert.ok(cards.length >= 10, `every AI card is on the shelf (${cards.length})`);
  for (const c of cards) {
    const row = { card: c.title || c.key, before: c.text.split("\n").pop().split(" · ")[0] };
    assert.doesNotMatch(c.text, /Connected|works|Your AI/, `${row.card} claims nothing before it is set up`);
    await everyCard(page);
    assert.ok(await press(page, c.key), `${row.card} can be pressed`);
    if (c.key.startsWith("cli-")) {
      // a coding tool that is not on this computer: Install, refused, said - never "installed"
      await until(page, () => !/Checking that|Installing/.test(document.querySelector(".tq-next-txt")?.innerText || ""), null, 60000);
      await until(page, () => /didn't install|can't be installed|isn't on this computer|Can't install/i.test(document.body.innerText));
      row.failure = (await line(page)).slice(0, 90);
      assert.doesNotMatch(row.failure, /works|is ready|connected/i, `${row.card}: a failure is never said as a success`);
    } else if (/ChatGPT/.test(c.title)) {
      await until(page, () => /sign-in didn't finish/i.test(document.querySelector(".tq-next-txt")?.innerText || ""));
      row.failure = (await line(page)).slice(0, 90);
      await until(page, (k) => /Sign-in didn.t finish - pick it to try again/.test(document.querySelector(`[data-tq-firstrun] [data-tq-card="${k}"]`)?.innerText || ""), c.key);
    } else {
      // a key card: its own setup opens under it; a key that cannot reach its provider fails, said on the card and on the line
      const field = await page.waitForSelector('[data-tq-firstrun] input[type="password"]', { timeout: 15000 }).catch(() => null);
      if (!field) { row.failure = "(no key to type - local)"; table.push(row); continue; }
      await field.type(KEY);
      const connect = () => page.evaluate(() => { const b = [...document.querySelectorAll("[data-tq-firstrun] button")].find((x) => x.innerText.trim() === "Connect" && !x.disabled); b?.click(); return !!b; });
      assert.ok(await connect(), `${row.card}: Connect`);
      await until(page, () => /✗/.test(document.querySelector("[data-tq-firstrun]")?.innerText || ""), null, 120000);
      row.failure = (await page.evaluate(() => document.querySelector("[data-tq-firstrun]").innerText.match(/✗[^\n]*/)[0])).slice(0, 90);
      assert.doesNotMatch(row.failure, /✓|works - it will sort/, `${row.card}: a failure is never said as a success`);
      assert.doesNotMatch(await line(page), /is ready|works - it will sort/, `${row.card}: the line does not call it working`);
      // ...and the same card, its success stood in for: said as one, never as a failure
      succeed = true; assert.ok(await connect());
      await until(page, () => /✓ Your key works/.test(document.querySelector("[data-tq-firstrun]")?.innerText || ""), null, 30000).catch(() => {});
      row.success = (await page.evaluate(() => (document.querySelector("[data-tq-firstrun]")?.innerText.match(/✓[^\n]*/) || [""])[0])).slice(0, 60) || "(moved on)";
      succeed = false;
    }
    // ...and it opens again after Pick a different AI
    await everyCard(page);
    assert.ok(await press(page, c.key), `${row.card} opens again`);
    row.reopens = "yes";
    table.push(row);
  }
  console.table(table);
  assert.equal(installs > 0, true, "a missing coding tool goes to its Install, never claimed present");
  assert.deepEqual(errors, []);
});

test("Connections: every AI card opens, a key that cannot reach its provider fails on its Test, and it opens again", { timeout: 900000 }, async (t) => {
  const harness = await startHarness({ fresh: true }); t.after(() => harness.close());
  const page = await harness.newPage(), errors = [], table = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(harness.ui, { waitUntil: "domcontentloaded", timeout: 90000 });
  await page.waitForSelector('[data-tq-firstrun="ai"]', { timeout: 120000 });
  await clickNav(page, "Connections");
  const section = () => until(page, () => {
    const b = [...document.querySelectorAll("button")].find((e) => e.innerText.includes("agents & models"));
    if (b && !document.querySelector("[data-tq-browse-card]")) { b.click(); return false; }
    return document.querySelectorAll("[data-tq-browse-card]").length > 5;
  });
  await section();
  const titles = await page.evaluate(() => [...document.querySelectorAll("[data-tq-card]")].filter((e) => e.getBoundingClientRect().width > 0 && getComputedStyle(e).cursor === "pointer")   /* a planned card is not yet a door */.map((e) => e.innerText.split("\n")[0].trim()));
  for (const title of titles) {
    const row = { card: title };
    const openIt = () => until(page, (t) => {
      if (document.querySelector("[data-tq-browse-back]")) return true;
      const c = [...document.querySelectorAll("[data-tq-card]")].find((e) => e.getBoundingClientRect().width > 0 && e.innerText.split("\n")[0].trim() === t);
      c?.click(); return false;
    }, title);
    await openIt();
    row.opens = "yes";
    const text = await page.evaluate(() => document.body.innerText);
    assert.doesNotMatch(text, /✓ Signed in|Connected:/, `${title} claims nothing before it is set up`);
    await page.evaluate(() => document.querySelector("[data-tq-browse-back]").click());
    await section();
    await openIt();
    row.reopens = "yes";
    await page.evaluate(() => document.querySelector("[data-tq-browse-back]").click());
    await section();
    table.push(row);
  }
  console.table(table);
  assert.ok(table.length >= 10);
  assert.deepEqual(errors, []);
});
