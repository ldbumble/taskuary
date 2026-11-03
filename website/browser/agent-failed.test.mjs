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

test("a general agent with no AI to run it is refused, offers Connect an AI, and is never waiting on you",
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
  // ...and its Connect an AI opens Connections at the AI cards
  await page.click("[data-tq-connect-ai]");
  await page.waitForFunction(() => decodeURIComponent(location.hash).includes("connections=AI"), { timeout: 10000 });

  // THE TASK'S AGENT STEP: a start with no AI is refused before anything changes (no AI, no start: server._brainless, the owner,
  // 2026-11-03) - it used to "start" and fail a second later. Nothing is filed under an agent waiting on you
  const made = (await api("/api/tasks", { Title: "Compare three payroll vendors on price", Summary: "Compare three payroll vendors on price", Kind: "general" })).data;
  assert.ok(made?.taskId, `task not created: ${JSON.stringify(made)}`);
  const sent = await api(`/api/tasks/${made.taskId}/dispatch`, { kind: "general" });
  assert.equal(sent.status, 422, JSON.stringify(sent));
  assert.match(String(sent.data?.detail || ""), /No AI is connected to run this agent/);
  assert.ok(!["working", "failed"].includes((await api(`/api/tasks/${made.taskId}`)).data?.agentStory?.kind), "a refused start left an agent story");
  const rows = (await api("/api/tasks")).data;
  const row = (Array.isArray(rows) ? rows : rows?.data || []).find((x) => x.TaskId === made.taskId);
  assert.ok(row, "the task is on the list");
  assert.notEqual(row.State, "blocked", "a refused start is never filed under an agent waiting on you");

  await page.evaluate((id) => { window.location.hash = `task=${id}`; }, made.taskId);
  await page.waitForFunction(() => /Compare three payroll/.test(document.body.innerText), { timeout: 20000 });
  const text = await page.evaluate(() => document.body.innerText);
  assert.doesNotMatch(text, /Agent answered|agent waiting on you|CLI agent or an AI provider/);
  // ...its Send to agent is greyed, the reason its hover - never pressable into the refusal (the owner, 2026-10-22)
  await hasButton(page, "Send to agent");
  assert.ok(await page.evaluate(() => [...document.querySelectorAll("button")].some((b) => b.offsetParent && b.textContent.trim() === "Send to agent"
    && b.disabled && /No AI is connected/.test(b.title || b.closest("[title]")?.title || ""))), "Send to agent is greyed, saying why");
  // ...and the task is still on the rail, with the dock row's moves under it: a refused start is never a page with nothing to press
  await page.waitForFunction(() => [...document.querySelectorAll("[data-tq-rail] .tq-pile-row")].some((r) => r.offsetParent && /Compare three payroll/.test(r.textContent)),
    { timeout: 15000 }).catch(() => { throw new Error("the task has no row on the rail"); });
  await page.waitForFunction(() => [...document.querySelectorAll("[data-tq-row] button, :is([data-tq-spine-moves], [data-tq-pane-moves]) button")].some((b) => b.offsetParent && b.textContent.trim() === "Mark done"),
    { timeout: 15000 }).catch(() => { throw new Error("the dock row has no Mark done"); });
  if (process.env.TQ_SHOT) await page.screenshot({ path: process.env.TQ_SHOT });
  assert.deepEqual(errors, []);
});
