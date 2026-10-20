// A FAILED SIGN-IN IS OVER, AND EVERY AI CARD OPENS AGAIN (the owner, 2026-10-20: the ChatGPT sign-in failed, the card and the Advisor
// still said "finish signing in", "Pick a different AI" left it so, and pressing ChatGPT again did nothing - "totally broken").
// A first start on a fresh fixture; OpenAI is never called - the sign-in fails at Taskuary's own listener, or its poll is answered here.
import assert from "node:assert/strict";
import { chmod, mkdtemp, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { clickNav, startHarness } from "./harness.mjs";

const json = (r, status, body) => r.respond({ status, contentType: "application/json", body: JSON.stringify(body) });
const line = (page) => page.evaluate(() => document.querySelector(".tq-next-txt")?.innerText || "");
const cardText = (page, title) => page.evaluate((t) => [...document.querySelectorAll("[data-tq-firstrun] [data-tq-card]")]
  .find((e) => e.innerText.trim().startsWith(t))?.innerText || "", title);
const pressCard = (page, title) => page.evaluate((t) => {
  const c = [...document.querySelectorAll("[data-tq-firstrun] [data-tq-card]")].find((e) => e.innerText.trim().startsWith(t)); c?.click(); return !!c;
}, title);
const press = (page, label) => page.evaluate((l) => {
  const b = [...document.querySelectorAll("button")].find((e) => e.innerText.trim() === l && e.getBoundingClientRect().width > 0); b?.click(); return !!b;
}, label);
const until = (page, f, arg, timeout = 30000) => page.waitForFunction(f, { timeout, polling: 200 }, arg).catch(async (e) => {
  throw new Error(`${e.message} waiting for ${String(f).slice(0, 160)}\n${(await page.evaluate(() => document.body.innerText)).slice(-1500)}`);
});

// the requests the page sends, counted by path; `answer` stands in for the server on the ones it names
async function open(harness, answer = {}) {
  const page = await harness.newPage(), errors = [], sent = {};
  page.on("pageerror", (e) => errors.push(e.message));
  page.off("request", page.fixtureRequestGuard);
  page.on("request", (r) => {
    const p = new URL(r.url()).pathname, k = Object.keys(answer).find((x) => p.endsWith(x));
    if (r.method() === "POST") sent[p.replace(/\/api\/connectors\/\d+\//, "")] = (sent[p.replace(/\/api\/connectors\/\d+\//, "")] || 0) + 1;
    if (k) return answer[k](r);
    page.fixtureRequestGuard(r);
  });
  page.on("response", async (r) => {      // the sign-in's own listener, from the URL it hands the page
    if (r.url().endsWith("/chatgpt/signin") && r.ok()) {
      try { page.redirect = new URL((await r.json()).url).searchParams.get("redirect_uri"); } catch { /* answered here */ }
    }
  });
  await page.goto(harness.ui, { waitUntil: "domcontentloaded", timeout: 90000 });
  await page.waitForSelector('[data-tq-firstrun="ai"] [data-tq-card]', { timeout: 120000 });
  return { page, errors, sent };
}
// the browser comes back to Taskuary's listener from an attempt it does not know: the sign-in fails, as a refusal would
const failAtListener = async (page) => {
  await until(page, () => true);
  for (let i = 0; i < 50 && !page.redirect; i++) await new Promise((r) => setTimeout(r, 100));
  assert.ok(page.redirect, "the sign-in handed the page its listener");
  await fetch(`${page.redirect}?state=not-this-attempt&code=x`).then((r) => r.text());
};

test("first run: a failed ChatGPT sign-in says it failed, keeps it on the card, and ChatGPT starts again", { timeout: 240000 }, async (t) => {
  const harness = await startHarness({ fresh: true }); t.after(() => harness.close());
  const { page, errors, sent } = await open(harness);
  assert.ok(await pressCard(page, "ChatGPT"));
  await until(page, () => /Signing in/.test(document.body.innerText));
  await failAtListener(page);
  await until(page, () => /sign-in didn't finish/i.test(document.querySelector(".tq-next-txt")?.innerText || ""));
  assert.doesNotMatch(await line(page), /Finish signing in/, "an ended sign-in is never 'in progress'");
  assert.match(await cardText(page, "ChatGPT"), /Sign-in didn't finish - pick it to try again/);
  assert.equal(await page.evaluate(() => [...document.querySelectorAll("[data-tq-setup-lit]")].map((e) => e.innerText.split("\n")[0]).join()), "ChatGPT",
    "the card that tries again is the lit move");
  // a reload: the card still says so (its LastError), and the line names it as the way to try again - never "finish signing in"
  await page.reload({ waitUntil: "domcontentloaded" });
  await page.waitForSelector('[data-tq-firstrun="ai"] [data-tq-card]', { timeout: 120000 });
  await until(page, () => /Sign-in didn't finish/.test(document.body.innerText));
  assert.match(await line(page), /The ChatGPT sign-in didn't finish: [^.]+. Pick ChatGPT to try again, or pick another AI./);
  assert.doesNotMatch(await line(page), /Finish signing in/);
  assert.ok(await pressCard(page, "ChatGPT"));
  await until(page, () => /Signing in/.test(document.body.innerText));
  assert.equal(sent["chatgpt/signin"], 2, "pressed again, a fresh sign-in starts");
  assert.deepEqual(errors, []);
});

test("first run: a sign-in whose check errors, or that waits, never blocks - Pick a different AI ends it and ChatGPT opens again", { timeout: 240000 }, async (t) => {
  const harness = await startHarness({ fresh: true }); t.after(() => harness.close());
  let n = 0, poll = "pending";
  const { page, errors, sent } = await open(harness, {
    "/chatgpt/signin": (r) => json(r, 200, { flow: `f${++n}`, url: "about:blank" }),
    "/chatgpt/poll": (r) => (poll === "pending" ? json(r, 200, { status: "pending" }) : json(r, 500, { detail: "Internal Server Error" })),
    "/chatgpt/cancel": (r) => json(r, 200, { ok: true }),
  });
  // waiting in its tab: "Pick a different AI" ends it, the shelf comes back, and ChatGPT starts a fresh one
  assert.ok(await pressCard(page, "ChatGPT"));
  await until(page, () => /Finish signing in/.test(document.querySelector(".tq-next-txt")?.innerText || ""));
  assert.ok(await press(page, "Pick a different AI"));
  await until(page, () => !/Signing in|Finish signing in/.test(document.body.innerText));
  assert.equal(sent["chatgpt/cancel"], 1, "its listener is stopped too");
  assert.ok(await pressCard(page, "ChatGPT"));
  await until(page, () => /Signing in/.test(document.body.innerText));
  assert.equal(n, 2, "ChatGPT opened again");
  // ...and a check the server answers with an error ends it - it polled "finish signing in" for ten minutes, ChatGPT dead
  poll = "error";
  await until(page, () => /sign-in didn't finish/i.test(document.querySelector(".tq-next-txt")?.innerText || ""), null, 20000);
  assert.doesNotMatch(await line(page), /Finish signing in/);
  assert.ok(await pressCard(page, "ChatGPT")); poll = "pending";
  await until(page, () => /Signing in/.test(document.body.innerText));
  assert.equal(n, 3);
  assert.deepEqual(errors, []);
});

test("first run: a coding tool that fails its check opens again after Pick a different AI", { timeout: 300000 }, async (t) => {
  const bin = await mkdtemp(path.join(os.tmpdir(), "taskuary-fake-cli-"));
  t.after(() => rm(bin, { recursive: true, force: true }).catch(() => {}));
  const win = process.platform === "win32", fake = path.join(bin, win ? "claude.cmd" : "claude");
  await writeFile(fake, win ? "@echo not a verdict\r\n" : "#!/bin/sh\necho not a verdict\n"); if (!win) await chmod(fake, 0o755);
  const harness = await startHarness({ fresh: true, bin }); t.after(() => harness.close());
  const { page, errors, sent } = await open(harness);
  assert.ok(await pressCard(page, "Claude"));
  // while it is checked, no shelf of cards that cannot be pressed: the check ends by itself, with its failure and the way out
  await until(page, () => /Checking that Claude works/.test(document.querySelector(".tq-next-txt")?.innerText || ""));
  assert.equal(await press(page, "Pick a different AI"), false, "no Pick a different AI over a check in flight");
  await until(page, () => !/Checking that Claude works/.test(document.querySelector(".tq-next-txt")?.innerText || ""), null, 220000);
  await until(page, () => [...document.querySelectorAll("button")].some((b) => b.innerText.trim() === "Pick a different AI"));
  assert.ok(await press(page, "Pick a different AI"));
  await until(page, () => document.querySelectorAll("[data-tq-firstrun] [data-tq-card]").length > 2);
  assert.ok(await pressCard(page, "Claude"));
  await until(page, (n) => /Checking that Claude works/.test(document.querySelector(".tq-next-txt")?.innerText || ""), null, 20000);
  assert.equal(sent["/api/setup/first-run/ai"], 2, "pressed again, it is checked again");
  assert.deepEqual(errors, []);
});

test("Connections: a failed ChatGPT sign-in is still said when its card is opened again, over the button that tries again", { timeout: 240000 }, async (t) => {
  const harness = await startHarness({ fresh: true }); t.after(() => harness.close());
  const { page, errors, sent } = await open(harness);
  await clickNav(page, "Connections");
  await until(page, () => [...document.querySelectorAll("button")].some((e) => e.innerText.includes("agents & models")));
  await page.evaluate(() => [...document.querySelectorAll("button")].find((e) => e.innerText.includes("agents & models")).click());
  // the card is pressed until its own setup is drawn: the section's list redraws once its cards have loaded
  const openCard = () => until(page, () => {
    if ([...document.querySelectorAll("button")].some((b) => b.innerText.trim() === "Sign in with ChatGPT")) return true;
    const c = [...document.querySelectorAll("[data-tq-card]")].find((e) => /^ChatGPT/.test(e.innerText.trim()) && e.getBoundingClientRect().width > 0);
    c?.click(); return false;
  }).then(() => true);
  assert.ok(await openCard());
  assert.ok(await press(page, "Sign in with ChatGPT"));
  await until(page, () => /Finish in the browser tab/.test(document.body.innerText));
  await failAtListener(page);
  await until(page, () => /✗ the sign-in came back for a different attempt/.test(document.body.innerText));
  await page.evaluate(() => document.querySelector("[data-tq-browse-back]").click());
  await until(page, () => [...document.querySelectorAll("[data-tq-browse-card]")].some((e) => /^ChatGPT[\s\S]*last test failed/.test(e.innerText.trim())));
  assert.ok(await openCard());
  await until(page, () => /✗ The ChatGPT sign-in didn't finish: the sign-in came back for a different attempt[^\n]*Press Sign in with ChatGPT to try again/.test(document.body.innerText));
  assert.ok(await press(page, "Sign in with ChatGPT"));
  await until(page, () => /Finish in the browser tab/.test(document.body.innerText));
  assert.equal(sent["chatgpt/signin"], 2);
  assert.deepEqual(errors, []);
});
