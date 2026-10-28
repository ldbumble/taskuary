import assert from "node:assert/strict";
import test from "node:test";

import { startHarness } from "./harness.mjs";

/* A FAILED AGENT IS SAID AS A FAILURE (owner-approved, 2026-10-21, the UI/UX audit's R2). A general agent with no AI to run on
   "started", failed a second later, and its task sat under "waiting on you" - the card said "Agent answered", the rail and the
   Board filed it as an agent waiting on the owner, and the only lit move was "New task to fix this". The New sheet closed over it.
   A fresh home (no AI anywhere: the demo refuses every start), setup put away so the day is open. */

const press = (page, label) => page.evaluate((label) => {
  const b = [...document.querySelectorAll("button")].find((x) => !x.disabled && x.textContent.trim() === label && x.offsetParent);
  if (!b) return false; b.click(); return true;
}, label);
const hasButton = (page, label) => page.waitForFunction((label) =>
  [...document.querySelectorAll("button")].some((b) => b.textContent.trim() === label && b.offsetParent), { timeout: 15000 }, label)
  .catch(async () => {
    const shown = await page.evaluate(() => [...document.querySelectorAll("button")].filter((b) => b.offsetParent).map((b) => b.textContent.trim()).join(" | "));
    if (process.env.TQ_SHOT) await page.screenshot({ path: process.env.TQ_SHOT });
    throw new Error(`no "${label}" button - shown: ${shown.slice(0, 600)}`);
  });

test("a general agent that could not start says Failed, offers Try again and Connect an AI, and is never waiting on you",
  { timeout: 240000 }, async (t) => {
  const harness = await startHarness({ fresh: true });
  t.after(() => harness.close());
  const page = await harness.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(harness.ui, { waitUntil: "domcontentloaded", timeout: 30000 });
  const api = (path, body, method = body ? "POST" : "GET") => page.evaluate(async ({ path, body, method }) => {
    const headers = { "X-Taskuary-Token": localStorage.getItem("taskuary_token"), "Content-Type": "application/json" };
    const r = await fetch(path, { method, headers, ...(body ? { body: JSON.stringify(body) } : {}) });
    return { status: r.status, data: await r.json().catch(() => null) };
  }, { path, body, method });
  assert.equal((await api("/api/setup/dismiss", { dismissed: true })).status, 200);
  await page.reload({ waitUntil: "domcontentloaded" });

  // THE NEW SHEET STAYS OPEN when nothing can run the agent, says so, and carries Connect an AI - and files nothing
  const before = JSON.stringify((await api("/api/tasks")).data);
  await page.evaluate(() => { window.location.hash = "new-task"; });
  await page.waitForFunction(() => [...document.querySelectorAll("[role='tab']")].some((x) => x.textContent.includes("Give an agent a job")), { timeout: 30000 });
  await page.evaluate(() => [...document.querySelectorAll("[role='tab']")].find((x) => x.textContent.includes("Give an agent a job")).click());
  await page.waitForFunction(() => document.body.innerText.includes("A general agent"), { timeout: 10000 });
  await page.evaluate(() => [...document.querySelectorAll("p, span, div")].reverse().find((x) => x.textContent.trim() === "A general agent")?.click());
  const box = await page.waitForSelector("[data-tq-new] textarea, [role='dialog'] textarea", { timeout: 10000 });
  await box.type("compare three payroll vendors on price");
  await hasButton(page, "Send to agent");
  assert.ok(await press(page, "Send to agent"));
  await page.waitForFunction(() => document.body.innerText.includes("No AI is connected"), { timeout: 10000 });
  assert.ok(await page.$("[data-tq-connect-ai]"), "the no-AI line carries Connect an AI");
  assert.ok(await page.evaluate(() => [...document.querySelectorAll("textarea")].some((x) => x.value.includes("compare three payroll vendors"))),
    "the sheet stayed open with the words");
  assert.equal(JSON.stringify((await api("/api/tasks")).data).includes("compare three payroll vendors"), before.includes("compare three payroll vendors"),
    "nothing was filed for a start that could not happen");

  // THE TASK'S AGENT STEP: a start whose first turn failed reads Failed, never "waiting on you"
  const made = (await api("/api/tasks", { Title: "Compare three payroll vendors on price", Summary: "Compare three payroll vendors on price", Kind: "general" })).data;
  assert.ok(made?.taskId, `task not created: ${JSON.stringify(made)}`);
  const sent = await api(`/api/tasks/${made.taskId}/dispatch`, { kind: "general" });
  await page.waitForFunction(async (id) => {
    const r = await fetch(`/api/tasks/${id}`, { headers: { "X-Taskuary-Token": localStorage.getItem("taskuary_token") } });
    const d = await r.json(); return d?.agentStory?.kind === "failed";
  }, { timeout: 20000, polling: 500 }, made.taskId).catch(async () => {
    const d = (await api(`/api/tasks/${made.taskId}`)).data;
    throw new Error(`no failed story: dispatch ${JSON.stringify(sent).slice(0, 300)} story ${JSON.stringify(d?.agentStory)} ended ${d?.runEnded}`);
  });
  const rows = (await api("/api/tasks")).data;
  const row = (Array.isArray(rows) ? rows : rows?.data || []).find((x) => x.TaskId === made.taskId);
  assert.ok(row, "the task is on the list");
  assert.notEqual(row.State, "blocked", "a failed start is never filed under an agent waiting on you");

  await page.evaluate((id) => { window.location.hash = `task=${id}`; }, made.taskId);
  await page.waitForFunction(() => /Failed - No AI is connected/.test(document.body.innerText), { timeout: 20000 });
  const text = await page.evaluate(() => document.body.innerText);
  assert.doesNotMatch(text, /Not started yet|Agent answered|agent waiting on you|CLI agent or an AI provider/);
  await hasButton(page, "Connect an AI");
  if (process.env.TQ_SHOT) await page.screenshot({ path: process.env.TQ_SHOT });
  // Try again with still no AI is greyed, the reason its hover - never pressable into the same failure (the owner, 2026-10-22). On the row,
  // or in its ▾: Close folds last (the owner, 2026-10-27), so on a narrower row the Agent group's greyed Try again folds before Mark done
  const greyed = () => page.evaluate(() => [...document.querySelectorAll('button, [role="menuitem"]')].some((b) => b.textContent.trim().startsWith("Try again")
    && b.offsetParent && (b.disabled || b.getAttribute("aria-disabled") === "true") && /No AI is connected/.test(b.title || b.closest("[title]")?.title || "")));
  // ...read once the task has drawn whole: the failure's own fix (Connect an AI) can land a beat before the row's Try again
  let seen = false;
  for (let i = 0; i < 20 && !(seen = await greyed()); i += 1) await new Promise((r) => setTimeout(r, 500));
  for (const m of seen ? [] : await page.$$eval("[data-tq-row] [data-tq-more]", (e) => e.map((x) => x.dataset.tqMore))) {
    await page.evaluate((m) => document.querySelector(`[data-tq-row] [data-tq-more="${m}"]`)?.click(), m); await new Promise((r) => setTimeout(r, 500));
    if ((seen = await greyed())) break;
    await page.keyboard.press("Escape"); await new Promise((r) => setTimeout(r, 300));
  }
  assert.ok(seen, "Try again is greyed, saying why");
  await page.keyboard.press("Escape"); await new Promise((r) => setTimeout(r, 300));
  // ...and Connect an AI opens Connections at the AI cards
  assert.ok(await press(page, "Connect an AI"));
  await page.waitForFunction(() => decodeURIComponent(location.hash).includes("connections=AI"), { timeout: 10000 });
  assert.deepEqual(errors, []);
});
