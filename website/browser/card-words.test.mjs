import assert from "node:assert/strict";
import { mkdir, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import { startHarness } from "./harness.mjs";
import { note, record } from "./recorder.mjs";

/* EVERY CARD SAYS IN WORDS WHAT ITS APPROVE DOES, AND NOTHING NAMES THE APP'S OWN MACHINERY (design round 5, 2026-11-19): round 4 gave a routine
   its lead; a step in a connected system and a part moved to its own task still stood as a reason line over a box, and Came from's card was
   headed "What triage made of it". Each is opened in the app and shot. Invented people only. */
const out = path.join(process.env.TEMP || os.tmpdir(), "claude", "card-words", process.env.CARD_WORDS_SHOT || "now");

test("a card leads with what its Approve does; Came from reads in his words", { timeout: 240000 }, async (t) => {
  const h = await startHarness({ fresh: true });
  t.after(() => h.close());
  const api = async (p, body) => (await fetch(`${h.fixtureApi}${p}`, { method: "POST", headers: { "Content-Type": "application/json", "X-Taskuary-Token": h.token },
    body: JSON.stringify(body) })).json();
  await api("/api/setup/dismiss", { dismissed: true });
  const page = await h.newPage();
  await page.setViewport({ width: 1400, height: 1000 });
  const errors = []; page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(h.ui, { waitUntil: "domcontentloaded" });
  await mkdir(out, { recursive: true });
  const rec = await record(page, out);
  const seen = {};
  for (const [name, post, reason] of [["tool", { action: "run_tool", type: "sql_query", database: "ledger", query: "select vendor, sum(total) from invoices group by vendor" },
    "the agent proposes to run a query on the ledger database - the vendor totals for October"],
  ["break-out", { action: "break_out", title: "Book the caterer", summary: "The caterer quotes and the booking", moves: "2 messages, 1 to-do" },
    'the agent proposes to move the caterer quotes to a task of its own, "Book the caterer"']]) {
    const { taskId } = await api("/api/fixture/act-card", { title: `Card words (${name})`, post, reason });
    await page.evaluate((id) => { location.hash = `task=${id}`; }, taskId);
    await page.waitForFunction(() => [...document.querySelectorAll("[data-tq-task-page] button")].some((b) => b.innerText.trim() === "Approve"), { timeout: 60000 });
    await new Promise((r) => setTimeout(r, 1200));
    const card = await page.evaluateHandle(() => [...document.querySelectorAll("[data-tq-task-page] button")].find((b) => b.innerText.trim() === "Approve").closest("[data-tq-draft-box]")?.parentElement
      || [...document.querySelectorAll("[data-tq-task-page] button")].find((b) => b.innerText.trim() === "Approve").parentElement.parentElement.parentElement);
    await card.evaluate((e) => e.scrollIntoView({ block: "center" }));
    await card.screenshot({ path: path.join(out, `${name}.png`) });
    seen[name] = await card.evaluate((e) => ({ lead: e.querySelector("[data-tq-held-lead]")?.innerText || "", text: e.innerText.slice(0, 400) }));
  }
  const { taskId } = await api("/api/fixture/mail-task", { title: "Erin asks about the ledger sync" });
  await page.evaluate((id) => { location.hash = `task=${id}`; }, taskId);
  await page.waitForSelector("[data-tq-task-page]", { visible: true, timeout: 60000 });
  await page.evaluate(() => [...document.querySelectorAll("[data-tq-task-page] button, [data-tq-task-page] [role=button]")].find((b) => /^Email · Erin Blake$/.test(b.innerText.trim()))?.click());
  await new Promise((r) => setTimeout(r, 1500));
  await page.screenshot({ path: path.join(out, "came-from.png") });
  seen.from = await page.evaluate(() => document.querySelector("[data-tq-task-page]")?.innerText.includes("triage made of it") ? "triage" : document.querySelector("[data-tq-sorted]")?.innerText.split(/\r?\n/)[0] || "none");
  await rec.stop();
  await writeFile(path.join(out, "seen.json"), JSON.stringify(seen, null, 1));
  const bad = [!seen.tool.lead && "the tool card has no lead", !seen["break-out"].lead && "the break-out card has no lead", !String(seen.from).startsWith("How Taskuary read it") && `Came from's card reads ${seen.from}`].filter(Boolean);
  await note(out, { done: "A step in a connected system, a part moved out, and a mail task's Came from, each opened.", expect: "Each card leads with what Approve does; no 'triage'.",
    saw: JSON.stringify(seen), verdict: bad.length ? "FAIL" : "PASS" });
  assert.deepEqual(bad, []);
  assert.deepEqual(errors, []);
});
