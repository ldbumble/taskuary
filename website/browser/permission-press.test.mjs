import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { chmod, mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { startHarness } from "./harness.mjs";
import { note, record } from "./recorder.mjs";

/* A PRESSED PERMISSION CARD NEVER LIGHTS AGAIN, AND IS NEVER GONE, BEFORE IT IS THE ANSWERED CARD (permissions.py; the owner, 2026-11-17:
   "when you click buttons on card it flickers then presses", "keep the action cards but gray out if passed"). A coding task on the stand-in
   ACP agent asks to run a command; the owner presses a button. Every DOM change from the press is read: the pressed card may spin or grey,
   then it is the greyed card saying what was pressed - never its buttons lit again, never no card at all in between - and the step it stopped at
   reads as waiting, then as not run once refused. Invented people only. */
const here = path.dirname(fileURLToPath(import.meta.url)), repo = path.resolve(here, "..", "..");
const out = path.join(process.env.TEMP || os.tmpdir(), "claude", "permission-press");

async function codingWorld(t) {
  const bin = await mkdtemp(path.join(os.tmpdir(), "taskuary-fake-claude-"));
  t.after(() => rm(bin, { recursive: true, force: true }).catch(() => {}));
  const win = process.platform === "win32";
  const py = execFileSync(win ? "python" : "python3", ["-c", "import sys; print(sys.executable)"], { encoding: "utf8" }).trim();
  const fake = path.join(repo, "tests", "fake_claude.py");
  await writeFile(path.join(bin, win ? "claude.cmd" : "claude"), win ? `@${py} ${fake} %*\r\n` : `#!/bin/sh\nexec "${py}" "${fake}" "$@"\n`);
  if (!win) await chmod(path.join(bin, "claude"), 0o755);
  Object.assign(process.env, { FAKE_ACP_SPAWN: "0.5", FAKE_ACP_THINK: "0.5", FAKE_ACP_ASK: "rm -rf /srv/ledger-archive" });
  const h = await startHarness({ fresh: true, bin });
  t.after(() => h.close());
  const api = (p, body) => fetch(`${h.fixtureApi}${p}`, { method: body ? "POST" : "GET",
    headers: { "Content-Type": "application/json", "X-Taskuary-Token": h.token }, body: body && JSON.stringify(body) }).then((r) => r.json());
  await api("/api/setup/first-run/ai", { name: "claude" });
  await api("/api/setup/dismiss", { dismissed: true });
  return { ...h, api };
}

for (const kind of ["allow_once", "reject_once"]) test(`a pressed ${kind} holds its card until it is the answered card`, { timeout: 300000 }, async (t) => {
  const w = await codingWorld(t), page = await w.newPage();
  await page.setViewport({ width: 1600, height: 900 });
  const errors = []; page.on("pageerror", (e) => errors.push(e.message));
  const made = await w.api("/api/fixture/coding", {});
  await page.goto(w.ui, { waitUntil: "domcontentloaded" });
  await page.evaluate((id) => { location.hash = `task=${id}`; }, made.taskId);
  const input = "[data-tq-task-page] [data-tq-agent-room] .tq-aui-input";
  await page.waitForSelector(input, { visible: true, timeout: 60000 });
  await page.waitForFunction((s) => !document.querySelector(s)?.disabled, { timeout: 60000 }, input);
  await page.evaluate((s) => document.querySelector(s)?.focus(), input);
  await page.keyboard.type("tidy the ledger archive"); await page.keyboard.press("Enter");
  await page.waitForSelector(`[data-tq-task-page] [data-tq-permission-answer="${kind}"]`, { visible: true, timeout: 90000 });
  await new Promise((r) => setTimeout(r, 1500));
  // ...and the step the card is about says it waits on him - never "Deleted ledger-archive" as done (permissions.calls)
  const stepNow = () => page.evaluate(() => [...document.querySelectorAll("[data-tq-task-page] .tq-aui-step")].map((e) => e.querySelector("summary, .tq-aui-step-line")?.textContent || e.textContent).find((x) => /ledger-archive/.test(x)) || "");
  assert.match(await stepNow(), /waits for your yes/, "the step it stopped at waits on him");
  const dir = path.join(out, kind); await mkdir(dir, { recursive: true });
  const rec = await record(page, dir);
  const states = await page.evaluate((kind) => new Promise((done) => {
    const seen = [], t0 = performance.now(), pane = () => document.querySelector("[data-tq-task-page]");
    const read = () => {
      const live = pane()?.querySelector("[data-tq-permission]"), was = pane()?.querySelector("[data-tq-permission-answered]");
      const lit = live && [...live.querySelectorAll("button")].some((b) => !b.disabled);
      const s = live ? `${lit ? "lit" : "busy"}:${live.getAttribute("data-tq-permission")}` : was ? `answered:${was.getAttribute("data-tq-permission-answered")}` : "none";
      // ...its place in the conversation, not on screen: the chat scrolls on to what the agent says next
      const card = live || was, port = card?.closest(".tq-aui-viewport");
      const y = card ? Math.round(card.getBoundingClientRect().top - (port ? port.getBoundingClientRect().top - port.scrollTop : 0)) : null;
      if (seen.at(-1)?.s !== s || seen.at(-1)?.y !== y) seen.push({ at: Math.round(performance.now() - t0), s, y });
    };
    const obs = new MutationObserver(read); obs.observe(document.body, { subtree: true, childList: true, characterData: true, attributes: true });
    read();
    pane().querySelector(`[data-tq-permission-answer="${kind}"]`).click();
    setTimeout(() => { obs.disconnect(); read(); done(seen); }, 8000);
  }), kind);
  await rec.stop();
  await writeFile(path.join(dir, "states.json"), JSON.stringify(states, null, 1));
  const first = states[0].s.split(":")[1], after = states.slice(1), relit = after.findIndex((x) => x.s === `lit:${first}`), blank = after.findIndex((x) => x.s === "none");
  await note(dir, { done: `A coding agent asks to run a command; the owner presses ${kind}.`, expect: "The pressed button spins, then the card is the greyed answered card - never lit again, never gone.",
    saw: JSON.stringify(states), verdict: relit < 0 && blank < 0 ? "PASS" : "FAIL" });
  assert.equal(relit, -1, `the card lit its buttons again after the press: ${JSON.stringify(states)}`);
  assert.equal(blank, -1, `no card at all for a beat after the press: ${JSON.stringify(states)}`);
  assert.ok(states.some((x) => x.s === `answered:${kind}`), `never the answered card: ${JSON.stringify(states)}`);
  // ...and the answered card stands where the card he pressed stood: no jump as it turns grey
  const landed = states.find((x) => x.s === `answered:${kind}`), moved = states.filter((x) => x.y != null && x.at <= landed.at && Math.abs(x.y - states[0].y) > 2);
  assert.deepEqual(moved, [], `the card moved as it was answered: ${JSON.stringify(states)}`);
  if (kind === "reject_once") assert.match(await stepNow(), /not run/, "a refused step was never run");
  assert.deepEqual(errors, []);
});
