import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { chmod, mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { startHarness } from "./harness.mjs";
import { note, record } from "./recorder.mjs";

/* A LINE TYPED IN A CODING CHAT, AS THE OWNER SEES IT (general.take_line; the owner, 2026-11-10: "coding and general use the same code when it
   comes to interactions so there should be no difference. IT should not say waiting on top of the prompt only under it and it should happen
   right away"; "don't want the working... thing. we should never see that ever. it should show agent and time and how long it's running rightg
   away. under it it can spin like normal"). A coding task whose agent is the stand-in ACP adapter (tests/fake_acp_server.py), slow to start
   (FAKE_ACP_SPAWN), in each state a line meets it: its session ended, idled out, the app restarted, the task closed, a turn still running. The
   chat is sampled every 100 ms from the press to the answer. Invented task and people only. */
const here = path.dirname(fileURLToPath(import.meta.url)), repo = path.resolve(here, "..", "..");
const shots = path.join(process.env.TEMP || os.tmpdir(), "claude", "n17");

async function codingWorld(t, env = {}) {
  const bin = await mkdtemp(path.join(os.tmpdir(), "taskuary-fake-claude-"));
  t.after(() => rm(bin, { recursive: true, force: true }).catch(() => {}));
  const win = process.platform === "win32";
  const py = execFileSync(win ? "python" : "python3", ["-c", "import sys; print(sys.executable)"], { encoding: "utf8" }).trim();
  const fake = path.join(repo, "tests", "fake_claude.py");
  await writeFile(path.join(bin, win ? "claude.cmd" : "claude"), win ? `@${py} ${fake} %*\r\n` : `#!/bin/sh\nexec "${py}" "${fake}" "$@"\n`);
  if (!win) await chmod(path.join(bin, "claude"), 0o755);
  Object.assign(process.env, { FAKE_ACP_SPAWN: "8", FAKE_ACP_THINK: "1.5", ...env });
  const h = await startHarness({ fresh: true, bin });
  t.after(() => h.close());
  const api = (p, body) => fetch(`${h.fixtureApi}${p}`, { method: body ? "POST" : "GET",
    headers: { "Content-Type": "application/json", "X-Taskuary-Token": h.token }, body: body && JSON.stringify(body) }).then((r) => r.json());
  await api("/api/setup/first-run/ai", { name: "claude" });
  await api("/api/setup/dismiss", { dismissed: true });
  await mkdir(shots, { recursive: true });
  return { ...h, api };
}

const heard = (said) => new RegExp(`heard:[^\\n]*${said}`);
const pageText = (page) => page.evaluate(() => document.querySelector("[data-tq-task-page]")?.innerText || "");
const box = async (page) => {
  const b = await page.waitForSelector("[data-tq-task-page] [data-tq-agent-room] .tq-aui-input", { visible: true, timeout: 60000 }).catch(async (e) => {
    await page.screenshot({ path: path.join(shots, "item1-no-box.png") });
    throw new Error(`no chat box: ${e.message}\n${(await page.evaluate(() => document.body.innerText)).slice(0, 1500)}`); });
  await page.waitForFunction(() => !document.querySelector("[data-tq-task-page] .tq-aui-input")?.disabled, { timeout: 60000 });
  return b;
};
// ...typed as a person types, into whichever box is on screen: the box is drawn again as the chat settles, and a handle on the old one is detached
const say = async (page, words) => {
  await box(page);
  await page.evaluate(() => document.querySelector("[data-tq-task-page] [data-tq-agent-room] .tq-aui-input")?.focus());
  await page.keyboard.type(words); await page.keyboard.press("Enter"); return Date.now();
};
const quiet = (page) => page.waitForFunction(() => !document.querySelector("[data-tq-task-page] [data-tq-run-clock]"), { timeout: 90000, polling: 100 });

// ONE SAMPLE of the chat: what is wrong in it ('' when nothing), and the facts the run compares across samples
const look = (page, said) => page.evaluate((said) => {
  const pane = document.querySelector("[data-tq-task-page]");
  if (!pane) return { why: "no task page" };
  const words = /\bWorking\b|\bStarting\b|\bContinuing\b/.exec(pane.querySelector(".tq-aui-viewport")?.innerText || "");
  if (words) return { why: `the words "${words[0]}" in the chat` };
  const mine = [...pane.querySelectorAll(".tq-aui-user-bubble, .tq-aui-user")].filter((e) => e.innerText.includes(said));
  const bubbles = new Set(mine.map((e) => e.closest(".tq-aui-message") || e));
  if (bubbles.size !== 1) return { why: `his line is drawn ${bubbles.size} times: ${[...bubbles].map((e) => e.outerHTML.slice(0, 300)).join(" ||| ")}` };
  const b = mine.pop().getBoundingClientRect(), stream = mine[0]?.closest(".tq-aui-viewport") || pane.querySelector(".tq-aui-viewport") || pane;
  const turn = [...stream.querySelectorAll("[data-tq-run-clock], [data-tq-pending-turn], .tq-aui-thinking, [data-tq-working]")];
  const above = turn.find((e) => e.getBoundingClientRect().top < b.bottom - 1);
  if (above) return { why: `above his line: ${above.outerHTML.slice(0, 160)}` };
  const clock = [...stream.querySelectorAll("[data-tq-run-clock]")].find((e) => e.getBoundingClientRect().top > b.bottom - 1);
  if (!clock) return { why: `no running head under his line: ${turn.map((e) => e.outerHTML.slice(0, 80)).join(" | ") || "nothing"}` };
  const head = clock.closest(".tq-aui-role") || clock, h = head.getBoundingClientRect();
  // ...DIRECTLY under it: nothing drawn between his bubble and the head
  const between = [...stream.querySelectorAll(".tq-aui-message")].find((m) => { const r = m.getBoundingClientRect(); return r.height > 0 && r.top >= b.bottom - 1 && r.bottom <= h.top + 1 && !m.contains(head); });
  if (between) return { why: `between his line and the head: ${between.innerText.slice(0, 120)}` };
  const spin = stream.querySelector(".tq-aui-thinking"), ran = /working (\d+)s|working (\d+)m/.exec(clock.innerText);
  const gap = spin ? spin.getBoundingClientRect().top - h.bottom : null;
  const body = head.closest(".tq-aui-message")?.querySelector(".tq-aui-agent-body, .tq-aui-markdown");
  return { why: "", head: Math.round(h.top - b.bottom), gap: gap == null ? null : Math.round(gap), spinAbove: spin ? spin.getBoundingClientRect().top < h.top : false,
    ran: ran ? +(ran[1] ?? ran[2] * 60) : null, text: (body?.innerText || "").trim().length > 0, hasX: !!clock.querySelector("[data-tq-stop-run]"), row: clock.closest("[data-tq-chat-line], [data-tq-pending-turn]")?.getAttribute("data-tq-chat-line") || "pending" };
}, said);

// FROM THE PRESS TO THE ANSWER, every 100 ms: his line once, the head under it with the spin under the head, no "Working" words, the clock
// counting from the press and never restarting, the head where it stood when the first words came
async function timeline(page, said, answer, pressed, name, { midturn = false } = {}) {
  const bad = [], seen = []; let first = null, shot = false;
  while (Date.now() - pressed < 90000) {
    const txt = await pageText(page);
    if (answer.test(txt)) break;
    const s = await look(page, said), at = Date.now() - pressed;
    // ...a turn that finished between the two reads has answered: its head stops counting with the answer under it
    if (s.why && answer.test(await pageText(page))) break;
    if (s.why === "" && first == null) first = at;
    if (s.why === "" && !shot && at > 1500) { shot = true; await page.screenshot({ path: path.join(shots, `item1-${name}-running.png`) }); }
    // ...mid-turn the turn at work finishes first; what is checked is the turn HE asked for, once it stands
    if (s.why && (at > 600 && !(midturn && first == null))) {
      if (!bad.length) {
        await page.screenshot({ path: path.join(shots, `item1-${name}-wrong.png`) });
        if (process.env.N17_DEBUG) bad.push(`payload: ${JSON.stringify(await page.evaluate(async () => { const id = /task=(\d+)/.exec(location.hash)[1];
          const d = await (await fetch(`/api/tasks/${id}/coding-chat`, { headers: { "X-Taskuary-Token": localStorage.getItem("taskuary_token") } })).json(); return { waiting: d.data?.waiting, turnStarted: d.data?.turnStarted, working: d.data?.working, live: d.data?.live, sessions: (d.data?.sessions || []).map((x) => [x.sid, x.live, x.at, (x.updates || x.steps || []).slice(-3).map((u) => [u.sessionUpdate || u.k, u._meta?.at || u.at || "", u.status || ""])]) }; }))}`);
      }
      if (process.env.N17_DEBUG && !bad.some((b) => b.includes(s.why.slice(0, 30)))) await page.screenshot({ path: path.join(shots, `item1-${name}-wrong-${bad.length}.png`) });
      bad.push(`${at}: ${s.why}`);
    }
    if (s.why === "") {
      if (process.env.N17_DEBUG && seen.length && s.ran != null && s.ran < seen.at(-1).ran) console.log("CLOCK", at, JSON.stringify(seen.at(-1)), JSON.stringify(s), JSON.stringify(await page.evaluate(async () => {
        const id = /task=(\d+)/.exec(location.hash)[1], d = (await (await fetch(`/api/tasks/${id}/coding-chat`, { headers: { "X-Taskuary-Token": localStorage.getItem("taskuary_token") } })).json()).data;
        return { turnStarted: d.turnStarted, working: d.working, live: d.live }; })));
      seen.push({ at, ...s });
      if (s.gap != null && (s.gap < -1 || s.gap > 16)) bad.push(`${at}: the spin stands ${s.gap}px under the head`);
      if (s.spinAbove) bad.push(`${at}: the spin above the head`);
    }
    await new Promise((r) => setTimeout(r, 100));
  }
  const txt = await pageText(page);
  if (!answer.test(txt) && page.tqLog) await writeFile(path.join(shots, `item1-${name}-server.log`), page.tqLog());
  assert.ok(answer.test(txt), `${name}: no answer:\n${txt.slice(-800)}`);
  await page.screenshot({ path: path.join(shots, `item1-${name}-answered.png`) });
  assert.ok(first != null && (midturn || first <= 600), `${name}: the head stood under his line at ${first} ms:\n${txt.slice(-800)}`);
  assert.deepEqual(bad, [], `${name}: ${bad.slice(0, 5).join(" / ")}`);
  const rans = seen.map((s) => s.ran).filter((r) => r != null);
  assert.ok(rans.every((r, i) => !i || r >= rans[i - 1]), `${name}: the clock went back: ${rans.join(",")}`);
  if (!midturn) { const last = seen.at(-1); assert.ok(Math.abs(last.ran - last.at / 1000) <= 2.5, `${name}: the clock counts from the press: ran ${last.ran}s at ${last.at} ms`); }
  const heads = new Set(seen.map((s) => s.head)), worded = seen.find((s) => s.text);
  if (worded) assert.ok([...heads].every((h) => Math.abs(h - seen[0].head) <= 2), `${name}: the head moved when the words came: ${[...heads].join(",")}`);
  return seen;
}

// ONE SCENE OF THE WALK, RECORDED (the owner, 2026-11-10: every audit is judged by watching it): `before` sets the state up on screen, then his
// line is typed and followed to the answer. The frames, a contact sheet and a README go under video/<walk>-<name>
async function scene(page, name, said, { midturn = false, before = null, state = "" } = {}) {
  const dir = path.join(shots, "video", `${process.env.N17_NAME || "coding-walk"}-${name}`), rec = await record(page, dir);
  let err = "";
  try { if (before) await before(); await timeline(page, said, heard(said), await say(page, said), name, { midturn }); }
  catch (e) { err = e.message; throw e; }
  finally {
    await rec.stop();
    await note(dir, { done: `A coding chat (stand-in ACP adapter, slow to start)${state ? `, ${state}` : ""}; the owner types "${said}" and presses Enter.`,
      expect: "His line once; the agent's head (AGENT · time · ran Ns) directly under it from the press, the spin under the head, the clock counting from the press and never restarting; no 'Working' words; nothing drawn above his line; then the answer in that turn.",
      saw: err ? err.slice(0, 1500) : "as expected", verdict: err ? "FAIL" : "PASS" });
  }
}

test("a line typed in an ACP coding chat stands once, its turn's head under it from the press, in every state the line can meet", { timeout: 900000 }, async (t) => {
  const w = await codingWorld(t);
  const page = await w.newPage();
  page.tqLog = w.log;
  await page.setViewport({ width: 1600, height: 810 });
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  const git = execFileSync(process.platform === "win32" ? "where" : "which", ["git"], { encoding: "utf8" }).trim().split(/\s*\n/)[0].trim();
  const made = await w.api("/api/fixture/coding", { git });
  assert.ok(made.taskId, `the coding task was made: ${JSON.stringify(made)}`);
  await page.goto(w.ui, { waitUntil: "domcontentloaded" });
  await page.evaluate((id) => { location.hash = `task=${id}`; }, made.taskId);
  const tid = made.taskId;

  // A FIRST TURN, posted as the page posts a line: the adapter takes 8 s to start
  await w.api(`/api/tasks/${tid}/assistant/messages`, { text: "look at the totals first" });
  await page.waitForFunction(() => /turn=1\]/.test(document.querySelector("[data-tq-task-page]")?.innerText || ""), { timeout: 120000, polling: 200 })
    .catch(async (e) => { await page.screenshot({ path: path.join(shots, "item1-first.png") }); throw new Error(`${e.message}\n${(await pageText(page)).slice(-1500)}`); });
  await quiet(page);
  await page.screenshot({ path: path.join(shots, "item1-first.png") });

  // THE SESSION ENDED
  assert.ok((await w.api("/api/fixture/session", { taskId: tid, state: "ended" })).ok, "the session ended");
  await scene(page, "ended", "now check the tax line", { state: "its session ended" });
  await quiet(page);

  // ...STOPPED BY ITS x MID-TURN, then a line typed carries on
  await scene(page, "after-x", "carry on with the rounding", { state: "a turn stopped by its x", before: async () => {
    await say(page, "and the rounding");
    await page.waitForSelector("[data-tq-task-page] [data-tq-stop-run]", { visible: true, timeout: 10000 });
    await page.screenshot({ path: path.join(shots, "item1-x-before.png") });
    await page.evaluate(() => document.querySelector("[data-tq-task-page] [data-tq-stop-run]").click());     // the head is drawn anew each second
    await quiet(page);
    await page.screenshot({ path: path.join(shots, "item1-x-stopped.png") }); } });
  await quiet(page);

  // IDLED OUT
  const idled = await w.api("/api/fixture/session", { taskId: tid, state: "idled" });
  assert.ok(idled.ok, `the session idled out: ${idled.why}`);
  await scene(page, "idled", "what about the import", { state: "its session idled out" });
  await quiet(page);

  // AFTER A RESTART (TQ_WALK_RESTART=1): a conversation reopened after a restart starts by the CLI's own profile, which the start-up folds into
  // the one coding profile - the stand-in adapter this world names on that profile (acp_cmd) is not reached, and npx is not on a fresh PATH
  if (process.env.TQ_WALK_RESTART) {
    await w.restart();
    await page.reload({ waitUntil: "domcontentloaded" });
    await scene(page, "restart", "is it still there after the restart", { state: "after the app restarted" });
    await quiet(page);
  }

  // A CLOSED TASK: typing reopens it
  await fetch(`${w.fixtureApi}/api/tasks/${tid}`, { method: "PATCH", headers: { "Content-Type": "application/json", "X-Taskuary-Token": w.token }, body: JSON.stringify({ Status: "done" }) });
  await page.reload({ waitUntil: "domcontentloaded" });
  await scene(page, "closed", "one more thing on the closed one", { state: "the task closed" });
  const task = await w.api(`/api/tasks/${tid}`);
  assert.ok(["open", "in_progress"].includes(task.Status ?? task.task?.Status), `typing reopened it: ${JSON.stringify(task).slice(0, 200)}`);
  await quiet(page);

  // A LINE TYPED MID-TURN
  await scene(page, "midturn", "and the changelog too", { midturn: true, state: "a turn still running", before: async () => {
    await say(page, "start on the docs");
    await page.waitForSelector("[data-tq-task-page] [data-tq-run-clock]", { visible: true, timeout: 10000 }); } });
  assert.deepEqual(errors, []);
});
