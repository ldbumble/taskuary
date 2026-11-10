import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { chmod, mkdtemp, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { startHarness } from "./harness.mjs";
import { headUnderLine, turnWatched, watchTurn } from "./turnWatch.mjs";

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
// ...READ IN EVERY STATE THE PAGE COMMITS AND EVERY FRAME IT PAINTS from the press to the answer (turnWatch; CI, 2026-11-10: a 50 ms sample 5 s in
// found nothing under his line - the head was swapped, not filled in): the head in the same state as his line, and in every state after it - only
// the states before his line is drawn at all may lack it; the paint itself within 1.5 s (a runner slowed six-fold took 0.5 s to draw the line)
async function underway(page, line, answer) {
  const w = await turnWatched(page, 30000).catch(async (e) => { throw new Error(`no answer: ${e.message}\n${(await pageText(page)).slice(-800)}`); });
  assert.ok(w.first != null && w.first <= 1500, `the turn's head stood under the line at ${w.first} ms (${w.n} states: ${w.bad.slice(0, 3).map((b) => b.join(": ")).join(" / ")}):\n${(await pageText(page)).slice(-800)}`);
  const bad = w.bad.filter(([at, why]) => !(at < w.first && /drawn 0 times/.test(why)));
  assert.deepEqual(bad, [], `states with no head under his line, or something of the turn above it (ms from the press, of ${w.n}): ${bad.slice(0, 4).map((b) => b.join(": ")).join(" / ")}`);
}
const press = async (page, line, answer) => { await watchTurn(page, line, answer, headUnderLine); await page.keyboard.press("Enter"); return Date.now(); };

test("a stopped general agent: Continue and a line typed after it show at once, working, then the answer", { timeout: 300000 }, async (t) => {
  const w = await agentWorld(t);
  const page = await w.newPage();
  await page.setViewport({ width: 1600, height: 810 });
  // ...as slow as a CI runner when asked (TQ_CPU_THROTTLE=4): the swap this test caught there never showed on a quick desk
  if (process.env.TQ_CPU_THROTTLE) await (await page.createCDPSession()).send("Emulation.setCPUThrottlingRate", { rate: +process.env.TQ_CPU_THROTTLE });
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
  await stopped.type("look at the south office first");
  const pressed = await press(page, "look at the south office first", /Starting with the south office/);
  await inTask(page, /look at the south office first/, 1500);
  assert.ok(Date.now() - pressed < 1500, "the note shows with the press's answer");
  await underway(page, "look at the south office first", /Starting with the south office/);
  assert.ok(Date.now() - pressed > 1000, "the answer cannot land with the press: the fake thinks 2.5 s");

  // ...AND THE NEXT LINE TYPED INTO THE SAME BOX: the same - at once, working, the answer
  const box = await page.waitForSelector("[data-tq-task-page] .tq-aui-input", { visible: true, timeout: 15000 });
  await page.waitForFunction(() => !document.querySelector("[data-tq-task-page] .tq-aui-input")?.disabled, { timeout: 30000 });
  await box.type("and the north office?");
  await press(page, "and the north office?", /The north office runs Trainly today/);
  await underway(page, "and the north office?", /The north office runs Trainly today/);
  const text = await pageText(page);
  assert.ok(text.indexOf("and the north office?") < text.indexOf("The north office runs Trainly"), "the answer stands under the owner's line");
  assert.deepEqual(errors, []);
});
