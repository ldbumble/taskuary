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
   Continue card's note and for a line typed into the conversation's own box after it. Invented task and people only. */
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
const visible = (page, label, within = "body") => page.waitForFunction((label, within) => [...document.querySelectorAll(`${within} button`)]
  .some((b) => !b.disabled && b.textContent.trim() === label && b.offsetParent), { timeout: 30000 }, label, within);
const click = (page, label, within = "body") => page.evaluate((label, within) => {
  const b = [...document.querySelectorAll(`${within} button`)].find((x) => !x.disabled && x.textContent.trim() === label && x.offsetParent);
  if (!b) throw new Error(`no ${label} to press`); b.click();
}, label, within);
// the pane says the agent is on it: its working line, a typing mark, or the box's own "Add something for it to pick up…"
const working = (page) => page.evaluate(() => {
  const pane = document.querySelector("[data-tq-task-page]");
  return !!pane && (/working|thinking|Continuing…/i.test(pane.innerText) || !!pane.querySelector(".tq-typing, [data-tq-starting], [aria-busy='true']")
    || !!pane.querySelector('textarea[placeholder^="Add something for it to pick up"]'));
});

test("a stopped general agent: Continue and a line typed after it show at once, working, then the answer", { timeout: 300000 }, async (t) => {
  const w = await agentWorld(t);
  const page = await w.newPage();
  await page.setViewport({ width: 1600, height: 810 });
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(w.ui, { waitUntil: "domcontentloaded" });
  const made = await w.api("/api/tasks", { Title: "Compare payroll vendors", Summary: "Compare three payroll vendors on price for Northwind", Kind: "general" });
  await page.evaluate((id) => { location.hash = `task=${id}`; }, made.taskId);

  // started, answered, stopped and saved: the agent the owner came back to
  await visible(page, "Send to agent"); await click(page, "Send to agent");
  await page.waitForSelector("[data-tq-run-form] textarea", { visible: true, timeout: 15000 });
  await click(page, "Send to agent", "[data-tq-run-form]");
  await inTask(page, /Payworth is cheapest/);
  await visible(page, "Stop and save"); await click(page, "Stop and save");
  await inTask(page, /You stopped it and its report is written/);

  // CONTINUE, filled out: the note is on the pane at once, the pane is working on it, and the answer lands
  await visible(page, "Continue"); await click(page, "Continue");
  await page.waitForSelector("[data-tq-continue-card] textarea", { visible: true, timeout: 15000 });
  await page.type("[data-tq-continue-card] textarea", "look at the south office first");
  await click(page, "Continue", "[data-tq-continue-card]");
  const pressed = Date.now();
  await inTask(page, /look at the south office first/, 1500);
  assert.ok(Date.now() - pressed < 1500, "the note shows with the press's answer");
  assert.ok(await working(page), `the pane says nothing is under way:\n${(await pageText(page)).slice(-800)}`);
  await inTask(page, /Starting with the south office/, 30000);
  assert.ok(Date.now() - pressed > 1000, "the answer cannot land with the press: the fake thinks 2.5 s");

  // ...AND A LINE TYPED INTO THE CONVERSATION'S OWN BOX after it: the same - at once, working, the answer
  const box = await page.waitForSelector("[data-tq-task-page] .tq-aui-input", { visible: true, timeout: 15000 });
  await page.waitForFunction(() => !document.querySelector("[data-tq-task-page] .tq-aui-input")?.disabled, { timeout: 30000 });
  await box.type("and the north office?"); await page.keyboard.press("Enter");
  await inTask(page, /and the north office\?/, 3000);
  assert.ok(await working(page), `the pane says nothing is under way:\n${(await pageText(page)).slice(-800)}`);
  await inTask(page, /The north office runs Trainly today/, 30000);
  const text = await pageText(page);
  assert.ok(text.indexOf("and the north office?") < text.indexOf("The north office runs Trainly"), "the answer stands under the owner's line");
  assert.deepEqual(errors, []);
});
