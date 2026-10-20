// ABOUT YOUR WORK, ON THE RENDERED PAGE (the owner, 2026-10-20): every mailbox is connected before the job is read, and the step that
// asks for them is never skipped. A first start on a fresh fixture with the AI and the mail stood in for (the setup state is the
// server's own, with its first two steps marked done); no model is called - the drafts are scripted here.
import assert from "node:assert/strict";
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";
import { startHarness } from "./harness.mjs";

const json = (r, status, body) => r.respond({ status, contentType: "application/json", body: JSON.stringify(body) });
const line = (page) => page.evaluate(() => document.querySelector(".tq-next-txt")?.innerText || "");
const step = (page) => page.evaluate(() => document.querySelector("[data-tq-firstrun-about]")?.getAttribute("data-tq-firstrun-about") || "");
const button = (page, label) => page.evaluate((l) => {
  const b = [...document.querySelectorAll("button")].find((e) => e.innerText.trim() === l && e.getBoundingClientRect().width > 0);
  return b ? { off: b.disabled } : null;
}, label);
const press = (page, label) => page.evaluate((l) => {
  const b = [...document.querySelectorAll("button")].find((e) => e.innerText.trim() === l && e.getBoundingClientRect().width > 0 && !e.disabled);
  b?.click(); return !!b;
}, label);
const until = (page, f, arg, timeout = 30000) => page.waitForFunction(f, { timeout, polling: 200 }, arg).catch(async (e) => {
  throw new Error(`${e.message} waiting for ${String(f).slice(0, 160)}\n${(await page.evaluate(() => document.body.innerText)).slice(-1500)}`);
});
const onStep = (page, s) => until(page, (x) => document.querySelector(`[data-tq-firstrun-about="${x}"]`), s);
// screenshots for the review, only when asked (TASKUARY_SHOTS=<folder>)
const shot = async (page, name) => {
  if (!process.env.TASKUARY_SHOTS) return;
  await mkdir(process.env.TASKUARY_SHOTS, { recursive: true });
  await page.screenshot({ path: path.join(process.env.TASKUARY_SHOTS, `${name}.png`) });
};

// the world: `boxes` the mailboxes connected so far, `drafts` what each draft's state says; every request the page sends is counted
async function open(harness, world) {
  const page = await harness.newPage(), errors = [], sent = {};
  page.on("pageerror", (e) => errors.push(e.message));
  page.off("request", page.fixtureRequestGuard);
  const real = async (p) => (await fetch(`${harness.fixtureApi}${p}`, { headers: { "X-Taskuary-Token": harness.token } })).json();
  page.on("request", async (r) => {
    const p = new URL(r.url()).pathname;
    if (r.method() === "POST") sent[p] = (sent[p] || 0) + 1;
    try {
      // the AI and the mail stood in for: the server's own setup state, its first two steps done and About your work open
      if (p === "/api/setup/first-run" && r.method() === "GET") {
        const st = await real(p);
        return json(r, 200, { ...st, step: "reading", todo: "about your work", ai_error: "", mail_error: "", mailboxes: world.boxes,
          brain: { ...st.brain, ready: true, name: "Your AI" }, frontier: "about", ready: false,
          rail: st.rail.map((x) => ({ ...x, done: ["ai", "mail"].includes(x.key) || x.done, open: true })) });
      }
      if (p === "/api/setup/first-run/about/suggest") return json(r, 200, { name: "Alex Doyle", org: "Northwind", role: "Finance lead", signature: "", systems: [] });
      if (p === "/api/setup/first-run/about/learn") { world.learned = JSON.parse(r.postData() || "{}"); return json(r, 200, world.drafts.job); }
      if (p === "/api/setup/first-run/about/job") return json(r, 200, world.drafts.job);
    } catch (e) { errors.push(`fixture: ${e.message}`); return r.abort(); }
    page.fixtureRequestGuard(r);
  });
  await page.goto(harness.ui, { waitUntil: "domcontentloaded", timeout: 90000 });
  await onStep(page, "name");
  return { page, errors, sent };
}

const DRAFT = (text) => ({ state: "ready", why: "", text });

test("About your work: Skip lands on the mailbox step, which cannot be skipped and moves on once a mailbox is in", { timeout: 240000 }, async (t) => {
  const harness = await startHarness({ fresh: true }); t.after(() => harness.close());
  const world = { boxes: [], drafts: { job: DRAFT("### What my job is\n- I run the month-end close.") } };
  const { page, errors } = await open(harness, world);
  assert.match(await page.evaluate(() => document.body.innerText), /About your work · 1 of \d+/);
  assert.ok(await press(page, "Skip these questions"));
  await onStep(page, "mailboxes");
  assert.equal(await button(page, "Skip these questions"), null, "the mailbox step has no Skip");
  assert.deepEqual(await button(page, "That's all my mail"), { off: true }, "with no mailbox it cannot move on");
  assert.match(await line(page), /Connect your email with its card/);
  assert.ok(await page.$("[data-tq-firstrun] [data-tq-card]"), "the email step's own cards are on it");
  // a mailbox connected (the card's own setup, read back on the next poll): listed, and the step moves on
  world.boxes = [{ address: "alex@northwind.example", type: "imap" }];
  await until(page, () => /alex@northwind\.example/.test(document.querySelector("[data-tq-mailboxes]")?.innerText || ""), null, 20000);
  await until(page, () => [...document.querySelectorAll("button")].some((b) => b.innerText.trim() === "That's all my mail" && !b.disabled));
  assert.match(await line(page), /One mailbox is connected\. .*Then press That's all my mail\./);
  await shot(page, "about-mailboxes");
  assert.ok(await press(page, "That's all my mail"));
  await onStep(page, "job");
  // Back to it and Skip from a question before it: lands on it again, never past it
  for (const s of ["mailboxes", "systems", "signature"]) { assert.ok(await press(page, "Back")); await onStep(page, s); }
  assert.ok(await press(page, "Skip these questions"));
  await onStep(page, "mailboxes");
  assert.deepEqual(errors, []);
});
