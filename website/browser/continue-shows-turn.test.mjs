import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { chmod, mkdtemp, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { startHarness } from "./harness.mjs";

/* CONTINUE SHOWS THE NEW TURN (the owner, 0.3.9.51: "I did Continue, filled it out and nothing happened ... do you check your work?"): a
   stopped general agent, Continue, a note typed and sent - the header said the agent was working while the pane kept only the old answer,
   no sign of what was said, no reply. On a real start (a stand-in claude on PATH, tests/fake_claude.py) and on the canvas, as the owner
   uses it: the owner's words are on the pane at once, the pane says it is working on them, and the answer lands under them - for the
   first line typed after it stopped and for the next one.
   ...ON A CHAT TASK THE BOX IS CONTINUE (the owner, 2026-11-04: "i want this to be a chat? where is the prompt box"): the stopped agent's
   chat keeps its box under it, no press first, and no Continue button or card beside it. Invented task and people only. */
const here = path.dirname(fileURLToPath(import.meta.url)), repo = path.resolve(here, "..", "..");
const SCRIPT = [{ when: "south", first: "Starting with the south office: two sites, both already on Payworth." },
  { when: "north", first: "The north office runs Trainly today; switching saves about 2 a head." },
  { when: ".", first: "Compared three vendors: Payworth is cheapest at 4 a head, Trainly 6, Spendly 7." }];

async function agentWorld(t) {
  const bin = await mkdtemp(path.join(os.tmpdir(), "taskuary-fake-claude-"));
  t.after(() => rm(bin, { recursive: true, force: true }).catch(() => {}));
  const win = process.platform === "win32";
  const py = execFileSync(win ? "python" : "python3", ["-c", "import sys; print(sys.executable)"], { encoding: "utf8" }).trim();
  const fake = path.join(repo, "tests", "fake_claude.py");
  await writeFile(path.join(bin, win ? "claude.cmd" : "claude"), win ? `@${py} ${fake} %*\r\n` : `#!/bin/sh\nexec "${py}" "${fake}" "$@"\n`);
  if (!win) await chmod(path.join(bin, "claude"), 0o755);
  await writeFile(path.join(bin, "script.json"), JSON.stringify(SCRIPT));
  // a slow think, so the moment between the press and the answer is long enough to see what the pane says in it
  Object.assign(process.env, { FAKE_CLAUDE_SCRIPT: path.join(bin, "script.json"), FAKE_CLAUDE_SPAWN: "0.5", FAKE_CLAUDE_THINK: "2.5" });
  const h = await startHarness({ fresh: true, bin });
  t.after(() => h.close());
  const api = (p, body) => fetch(`${h.fixtureApi}${p}`, { method: body ? "POST" : "GET",
    headers: { "Content-Type": "application/json", "X-Taskuary-Token": h.token }, body: body && JSON.stringify(body) }).then((r) => r.json());
  await api("/api/setup/first-run/ai", { name: "claude" });
  await api("/api/setup/dismiss", { dismissed: true });
  return { ...h, api };
}

const pageText = (page) => page.evaluate(() => document.querySelector("[data-tq-task-page]")?.innerText || "");
const inTask = (page, re, timeout = 30000) => page.waitForFunction((src) => new RegExp(src).test(document.querySelector("[data-tq-task-page]")?.innerText || ""),
  { timeout, polling: 50 }, re.source).catch(async () => { throw new Error(`no ${re} on the task:\n${(await pageText(page)).slice(0, 2000)}`); });
// THE TURN HE ASKED FOR STANDS UNDER HIS LINE, AS ITS OWN HEAD (the owner, 2026-11-10: "don't want the working... thing. we should never see that
// ever. it should show agent and time and how long it's running rightg away. under it it can spin like normal"): below his newest bubble, a
// turn head with its running clock ("· 2:05 PM · ran 3s"); nothing of the turn's - head, spin - above the bubble; no line of the old words
// ...sampled every 50 ms from the press to the answer: the head under his line within 500 ms, and in every sample after it until the answer
async function underway(page, line, answer, pressed) {
  let first = null; const bad = [];
  while (Date.now() - pressed < 30000) {
    if (answer.test(await pageText(page))) break;
    const why = await working(page, line), ok = why === "", at = Date.now() - pressed;
    if (ok && first == null) first = at;
    if (!ok && at > 500) bad.push(`${at}: ${why}`);
    await new Promise((r) => setTimeout(r, 50));
  }
  assert.ok(answer.test(await pageText(page)), `no answer:\n${(await pageText(page)).slice(-800)}`);
  assert.ok(first != null && first <= 500, `the turn's head stood under the line at ${first} ms:\n${(await pageText(page)).slice(-800)}`);
  assert.deepEqual(bad, [], `samples with no head under his line, or something of the turn above it (ms from the press): ${bad.slice(0, 4).join(" / ")}`);
}
const working = (page, line) => page.evaluate((said) => {
  const pane = document.querySelector("[data-tq-task-page]");
  if (!pane) return "no task page";
  if (/Working on this|Working on it|Continuing…/.test(pane.innerText)) return "the old working words";
  const mine = [...pane.querySelectorAll(".tq-aui-user-bubble, .tq-aui-user")].filter((e) => e.innerText.includes(said)).pop();
  if (!mine) return "his line is not drawn";
  const bottom = mine.getBoundingClientRect().bottom;
  // ...inside the chat stream: the header chip at the top of the task ("agent working") is not part of the turn and stays
  const stream = mine.closest(".tq-aui-viewport") || pane;
  const turn = [...stream.querySelectorAll("[data-tq-run-clock], [data-tq-pending-turn], .tq-aui-thinking, [data-tq-working]")];
  const above = turn.find((e) => e.getBoundingClientRect().top < bottom - 1);
  if (above) return `above his line: ${above.outerHTML.slice(0, 160)}`;
  return turn.some((e) => e.matches("[data-tq-run-clock]") && /ran \d/.test(e.innerText)) ? "" : `no running head: ${turn.map((e) => e.outerHTML.slice(0, 80)).join(" | ") || "nothing"}`;
}, line);

test("a stopped general agent: Continue and a line typed after it show at once, working, then the answer", { timeout: 300000 }, async (t) => {
  const w = await agentWorld(t);
  const page = await w.newPage();
  await page.setViewport({ width: 1600, height: 810 });
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(w.ui, { waitUntil: "domcontentloaded" });
  const made = await w.api("/api/tasks", { Title: "Compare payroll vendors", Summary: "Compare three payroll vendors on price for Northwind", Kind: "general" });
  await page.evaluate((id) => { location.hash = `task=${id}`; }, made.taskId);

  // started, answered: the agent the owner came back to
  // ...ONE PROMPT BOX (the owner, 2026-11-06): a chat task opens on its chat with the one box under it - no Send to agent form, no button of its
  // own; what is typed there starts the agent
  assert.equal(await page.$("[data-tq-run-form]"), null, "no separate Send to agent form on a chat task");
  const first = await page.waitForSelector("[data-tq-task-page] [data-tq-agent-room] .tq-aui-input", { visible: true, timeout: 30000 });
  await first.type("compare them on price."); await page.keyboard.press("Enter");
  await inTask(page, /Payworth is cheapest/);
  // ...a chat task has no Stop and save any more (the owner, 2026-11-05: "the stop you can get rid of it"): the answered agent rests,
  // its chat stands with the box under it - no Result block, no "The whole conversation", no Continue to press first
  assert.ok(!(await page.$$eval("[data-tq-task-page] button", (bs) => bs.filter((b) => b.offsetParent).map((b) => b.getAttribute("aria-label") || b.textContent.trim()))).includes("Stop and save"),
    "no Stop and save on a chat task");
  const stopped = await page.waitForSelector("[data-tq-task-page] [data-tq-agent-room] .tq-aui-input", { visible: true, timeout: 30000 });   // resting live or saved: the same box
  await page.waitForFunction(() => !document.querySelector("[data-tq-task-page] .tq-aui-input")?.disabled, { timeout: 30000 });
  assert.equal(await page.$("[data-tq-result-summary], [data-tq-full-result], [data-tq-continue-card]"), null, "the chat is the whole Agent section");
  assert.ok(!(await page.$$eval("[data-tq-task-page] button, [data-tq-row] button", (bs) => bs.filter((b) => b.offsetParent).map((b) => b.textContent.trim()))).includes("Continue"),
    "no Continue beside the box");

  // TYPED IN THE BOX: the words are on the pane at once, the pane is working on them, and the answer lands
  await stopped.type("look at the south office first"); await page.keyboard.press("Enter");
  const pressed = Date.now();
  await inTask(page, /look at the south office first/, 1500);
  assert.ok(Date.now() - pressed < 1500, "the note shows with the press's answer");
  await underway(page, "look at the south office first", /Starting with the south office/, pressed);
  assert.ok(Date.now() - pressed > 1000, "the answer cannot land with the press: the fake thinks 2.5 s");

  // ...AND THE NEXT LINE TYPED INTO THE SAME BOX: the same - at once, working, the answer
  const box = await page.waitForSelector("[data-tq-task-page] .tq-aui-input", { visible: true, timeout: 15000 });
  await page.waitForFunction(() => !document.querySelector("[data-tq-task-page] .tq-aui-input")?.disabled, { timeout: 30000 });
  await box.type("and the north office?"); await page.keyboard.press("Enter");
  await underway(page, "and the north office?", /The north office runs Trainly today/, Date.now());
  const text = await pageText(page);
  assert.ok(text.indexOf("and the north office?") < text.indexOf("The north office runs Trainly"), "the answer stands under the owner's line");
  assert.deepEqual(errors, []);
});
