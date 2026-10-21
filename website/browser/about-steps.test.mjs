// ABOUT YOUR WORK, ON THE RENDERED PAGE (the owner, 2026-10-20): every source - a mailbox, a chat, a task system (2026-10-21) - is
// connected before the job is read, and the step that asks for them is never skipped. A first start on a fresh fixture with the AI and the mail stood in for (the setup state is the
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
        return json(r, 200, { ...st, step: "reading", todo: "about your work", ai_error: "", mail_error: "", sources: world.boxes,
          brain: { ...st.brain, ready: true, name: "Your AI" }, frontier: "about", ready: false,
          rail: st.rail.map((x) => ({ ...x, done: ["ai", "mail"].includes(x.key) || x.done, open: true })) });
      }
      if (p === "/api/setup/first-run/about/suggest") return json(r, 200, { name: "Alex Doyle", org: "Northwind", role: "Finance lead", signature: "", systems: [] });
      if (p === "/api/setup/first-run/about/learn") {
        world.learned = JSON.parse(r.postData() || "{}"); (world.asked ||= []).push(world.learned.docs);
        return json(r, 200, { ...world.drafts.job, drafts: world.drafts });
      }
      if (p === "/api/setup/first-run/about/drafts") return json(r, 200, world.drafts);
      if (p === "/api/setup/first-run/about/accept") { (world.accepted ||= []).push(JSON.parse(r.postData()).doc); return json(r, 200, { state: "ready" }); }
    } catch (e) { errors.push(`fixture: ${e.message}`); return r.abort(); }
    page.fixtureRequestGuard(r);
  });
  await page.goto(harness.ui, { waitUntil: "domcontentloaded", timeout: 90000 });
  await onStep(page, "name");
  return { page, errors, sent };
}

const DRAFT = (text) => ({ state: "ready", why: "", text });
const NONE = { state: "none", why: "", text: "" };

test("About your work: Skip lands on the sources step, which cannot be skipped and moves on once a source is in", { timeout: 240000 }, async (t) => {
  const harness = await startHarness({ fresh: true }); t.after(() => harness.close());
  const world = { boxes: [], drafts: { job: DRAFT("### What my job is\n- I run the month-end close."), style: NONE, soul: NONE } };
  const { page, errors, sent } = await open(harness, world);
  assert.match(await page.evaluate(() => document.body.innerText), /About your work · 1 of \d+/);
  assert.ok(await press(page, "Skip these questions"));
  await onStep(page, "mailboxes");
  assert.equal(await button(page, "Skip these questions"), null, "the mailbox step has no Skip");
  assert.deepEqual(await button(page, "That's all my sources"), { off: true }, "with no source it cannot move on");
  assert.match(await line(page), /Connect your email, chat or task system with its card/);
  assert.ok(await page.$("[data-tq-firstrun] [data-tq-card]"), "the main source step's own cards are on it");
  // a mailbox connected (the card's own setup, read back on the next poll): listed, and the step moves on
  world.boxes = [{ address: "alex@northwind.example", type: "imap", title: "Email" }];
  await until(page, () => /alex@northwind\.example/.test(document.querySelector("[data-tq-mailboxes]")?.innerText || ""), null, 20000);
  await until(page, () => [...document.querySelectorAll("button")].some((b) => b.innerText.trim() === "That's all my sources" && !b.disabled));
  assert.match(await line(page), /One source is connected\. .*Then press That's all my sources\./);
  await shot(page, "about-mailboxes");
  assert.ok(await press(page, "That's all my sources"));
  await onStep(page, "job");
  // passing it writes the job from every mailbox in - Skip went past the title, so this is the first time it is written
  assert.equal(sent["/api/setup/first-run/about/learn"], 1);
  assert.equal(world.learned.name, "Alex Doyle");
  // Back to it and Skip from a question before it: lands on it again, never past it
  for (const s of ["mailboxes", "systems", "signature"]) { assert.ok(await press(page, "Back")); await onStep(page, s); }
  assert.ok(await press(page, "Skip these questions"));
  await onStep(page, "mailboxes");
  assert.deepEqual(errors, []);
});

test("About your work: the job, how you write and who you are are drafts to accept, and a failed one says why with Write it again", { timeout: 240000 }, async (t) => {
  const harness = await startHarness({ fresh: true }); t.after(() => harness.close());
  const world = { boxes: [{ address: "alex@northwind.example", type: "outlook", title: "Email" }, { address: "alex@riverside.example", type: "imap", title: "Email" }],
    drafts: { job: DRAFT("## At Northwind (alex@northwind.example)\n\n### What my job is\n- I run the month-end close.\n\n"
      + "## At riverside.example (alex@riverside.example)\n\n### What my job is\n- I keep the volunteer rota."),
    style: { state: "failed", why: "no sent mail to learn from - connect a mailbox", text: "" },
    soul: { state: "running", why: "", text: "" } } };
  const { page, errors, sent } = await open(harness, world);
  assert.ok(await press(page, "Skip these questions"));
  await onStep(page, "mailboxes");
  assert.match(await line(page), /2 sources are connected\./);
  assert.ok(await press(page, "That's all my sources"));
  await onStep(page, "job");
  assert.deepEqual(world.asked, [["job", "style", "soul"]], "all three drafts are written once every mailbox is in");
  // the job: read as a document, a section per organisation, and accepted as it is
  await until(page, () => document.querySelectorAll("[data-tq-job-read] h2").length === 2);
  assert.match(await page.evaluate(() => document.body.innerText), /About your work · 7 of 9/);
  assert.match(await line(page), /This is your job as your email describes it/);
  await shot(page, "about-job");
  assert.ok(await press(page, "Looks right"));
  await onStep(page, "style");
  assert.deepEqual(world.accepted, ["job"]);
  // how you write failed: said plainly on the canvas and on the line, with Write it again lit - Next never pretends it worked
  assert.match(await page.evaluate(() => document.querySelector("[data-tq-draft-failed]")?.innerText || ""), /I couldn't write it: no sent mail to learn from/);
  assert.match(await line(page), /I couldn't write it from your sent mail \(no sent mail to learn from - connect a mailbox\)\. Press Write it again/);
  assert.equal(await page.evaluate(() => document.querySelector('[data-tq-setup-lit="about"]')?.innerText), "Write it again");
  assert.ok(await button(page, "Next"), "past it without a draft is still Next");
  await shot(page, "about-style-failed");
  world.drafts.style = DRAFT("### Tone & length\n- Two or three sentences, the answer first.");
  assert.ok(await press(page, "Write it again"));
  await until(page, () => /answer first/.test(document.querySelector("[data-tq-job-read]")?.innerText || ""));
  assert.deepEqual(world.asked.at(-1), ["style"], "only that draft is written again");
  assert.ok(await press(page, "Looks right"));
  await onStep(page, "soul");
  // who you are, still being written: said, and the step waits for it; then it arrives on the next read
  assert.match(await page.evaluate(() => document.body.innerText), /Describing how you like to work…/);
  assert.deepEqual(await button(page, "Save"), { off: true }, "the last step waits on its draft");
  world.drafts.soul = DRAFT("### How I like to work\n- I settle a question the same day.");
  await until(page, () => /same day/.test(document.querySelector("[data-tq-job-read]")?.innerText || ""), null, 20000);
  assert.match(await line(page), /This is how you like to work, from your mail and your answers/);
  await shot(page, "about-soul");
  assert.ok(await press(page, "Looks right"));
  for (let i = 0; i < 100 && !sent["/api/setup/first-run/about"]; i++) await new Promise((r) => setTimeout(r, 100));
  assert.equal(sent["/api/setup/first-run/about"], 1, "the last Looks right saves the answers");
  assert.deepEqual(world.accepted, ["job", "style", "soul"]);
  assert.deepEqual(errors, []);
});
