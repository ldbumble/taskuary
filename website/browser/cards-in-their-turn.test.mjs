import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { chmod, copyFile, mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { startHarness } from "./harness.mjs";
import { note, record } from "./recorder.mjs";

/* A DRAFT REWRITTEN AFTER THE OWNER PROMPTS IS A NEW CARD IN THE NEW TURN (the owner, 2026-11-10: "i asked it to rewrite a email, it reqrote in
   place then put it under the prompt. Check that this does not happen? ... The second you write ptompt on email action it should go gray and then
   it should generate new email action box under it with new email.."). A reply drafted on arrival waits on the task; the owner types a rewrite
   into the task's box; the stand-in agent (tests/fake_claude.py) files the new letter as the real one does (`taskuary --reply`). Sampled every
   100 ms from the key press until the new card is live, and recorded. Invented people only. */
const here = path.dirname(fileURLToPath(import.meta.url)), repo = path.resolve(here, "..", "..");
const out = path.join(process.env.TEMP || os.tmpdir(), "claude", "n17");
const NEW = "Hi Erin, short version: two real flaws, the sheet is attached. Alex";
const SCRIPT = [{ when: "make it shorter", anywhere: true, first: "Rewrote it short, with the sheet attached.",
  post: [{ path: "/api/agent/reply", body: { text: NEW, agent: "assistant", files: [{ name: "flaws.csv", data: Buffer.from("flaw,impact\nexport,high\nsso,medium\n").toString("base64") }] } }] }];

async function world(t) {
  const bin = await mkdtemp(path.join(os.tmpdir(), "taskuary-fake-claude-"));
  t.after(() => rm(bin, { recursive: true, force: true }).catch(() => {}));
  const win = process.platform === "win32";
  const py = execFileSync(win ? "python" : "python3", ["-c", "import sys; print(sys.executable)"], { encoding: "utf8" }).trim();
  const fake = path.join(repo, "tests", "fake_claude.py");
  await writeFile(path.join(bin, win ? "claude.cmd" : "claude"), win ? `@${py} ${fake} %*\r\n` : `#!/bin/sh\nexec "${py}" "${fake}" "$@"\n`);
  if (!win) await chmod(path.join(bin, "claude"), 0o755);
  await writeFile(path.join(bin, "script.json"), JSON.stringify(SCRIPT));
  Object.assign(process.env, { FAKE_CLAUDE_SCRIPT: path.join(bin, "script.json"), FAKE_CLAUDE_SPAWN: "0.5", FAKE_CLAUDE_THINK: "3", FAKE_CLAUDE_LOG: path.join(bin, "log.jsonl") });
  const h = await startHarness({ fresh: true, bin });
  t.after(() => h.close());
  const api = (p, body) => fetch(`${h.fixtureApi}${p}`, { method: body ? "POST" : "GET",
    headers: { "Content-Type": "application/json", "X-Taskuary-Token": h.token }, body: body && JSON.stringify(body) }).then((r) => r.json());
  await api("/api/setup/first-run/ai", { name: "claude" });
  await api("/api/setup/dismiss", { dismissed: true });
  return { ...h, api, log: path.join(bin, "log.jsonl") };
}

// ONE SAMPLE: the old card and every other draft card, each where it stands in the chat's content (not the window: the chat scrolls), its words,
// whether it is greyed and its Send pressable; his line's place
const look = (page, oldId, said) => page.evaluate((oldId, said) => {
  const pane = document.querySelector("[data-tq-task-page]"), vp = pane?.querySelector(".tq-aui-viewport");
  const y = (r) => Math.round(r.top - (vp ? vp.getBoundingClientRect().top - vp.scrollTop : 0));
  const grey = (el) => { for (let e = el, i = 0; e && i < 8; e = e.parentElement, i++) if (+getComputedStyle(e).opacity < 0.9) return true; return [...el.querySelectorAll("*")].slice(0, 3).some((e) => +getComputedStyle(e).opacity < 0.9); };
  // ...the letter itself - who it goes to, its subject and words, its files - not the controls round it (a greyed card hides its Change)
  const words = (el) => [(/To\s+([^<\n]*<[^>]+>)/.exec(el.innerText) || [])[1], (/[\w.-]+\.(csv|pdf|xlsx|docx|png)\b/.exec(el.innerText) || [])[0], ...[...el.querySelectorAll("textarea, input")].map((x) => x.value)].join("|").replace(/\s+/g, " ").trim();
  // ...where the letter stands: its text box, what the eye follows (the card's own box starts at a heading in one place, under it in another)
  const card = (el) => { const r = (el.querySelector("textarea") || el).getBoundingClientRect(), send = [...el.querySelectorAll("button")].filter((b) => b.matches("[data-tq-send]") || /^(Send|Connect email)/.test(b.innerText.trim()));
    return { id: el.getAttribute("data-tq-review") || el.getAttribute("data-tq-replaced"), record: el.matches("[data-tq-replaced]"), top: y(r), bottom: y({ top: r.bottom }), words: words(el), grey: grey(el),
      live: send.some((b) => !b.disabled) && !grey(el), sends: send.length }; };
  // ...a replaced draft's record is the old card too, where it stood (PassedCard.ReplacedDraft)
  const cards = [...(pane?.querySelectorAll("[data-tq-review], [data-tq-replaced]") || [])].filter((e) => e.getBoundingClientRect().height > 0).map(card);
  const mine = [...(pane?.querySelectorAll(".tq-aui-user-bubble") || [])].filter((e) => e.innerText.includes(said)).pop();
  const ext = [...(pane?.querySelectorAll("[data-tq-file-card], [data-tq-show-file]") || [])].filter((e) => e.getBoundingClientRect().height > 0).length;
  return { cards, old: cards.filter((c) => c.id === String(oldId)), bubble: mine ? { top: y(mine.getBoundingClientRect()), bottom: y({ top: mine.getBoundingClientRect().bottom }) } : null,
    text: pane?.innerText || "", files: ext,
    // ...the head of the turn his line began: the first turn head under his line
    head: mine ? [...pane.querySelectorAll("[data-tq-ran]")].map((e) => y(e.getBoundingClientRect())).find((t) => t > y(mine.getBoundingClientRect())) ?? null : null };
}, oldId, said);

async function rewrite(t, w, page, { tid, rid, name }) {
  const dir = path.join(out, "video", name), said = "make it shorter and attach the sheet";
  await mkdir(dir, { recursive: true });
  await page.evaluate((id) => { location.hash = `task=${id}`; }, tid);
  await page.waitForSelector(`[data-tq-task-page] [data-tq-review="${rid}"]`, { visible: true, timeout: 60000 }).catch(async (e) => {
    await page.screenshot({ path: path.join(out, `item3c-${name}-no-card.png`) });
    throw new Error(`${e.message}\n${(await page.evaluate(() => document.body.innerText)).slice(0, 2500)}`); });
  const box = await page.waitForSelector("[data-tq-task-page] [data-tq-agent-room] .tq-aui-input, [data-tq-task-page] .tq-aui-input", { visible: true, timeout: 60000 });
  const rec = await record(page, dir);
  const t0 = await look(page, rid, said);
  assert.equal(t0.old.length, 1, "the waiting draft stands once");
  assert.ok(t0.old[0].live, `T0: the draft is live: ${JSON.stringify(t0.old[0])}`);
  await page.screenshot({ path: path.join(out, `item3c-${name}-t0.png`) });
  await box.type(said);
  const before = await look(page, rid, said), pressed = Date.now();
  await page.keyboard.press("Enter");
  const samples = [], bad = [];
  let shot = 0, done = null;
  while (Date.now() - pressed < 90000) {
    const s = await look(page, rid, said), at = Date.now() - pressed;
    samples.push({ at, ...s, text: undefined });
    const o = s.old[0], why = [];
    if (s.old.length !== 1) why.push(`the old card is drawn ${s.old.length} times`);
    if (!s.old.length && process.env.N17_DEBUG && !bad.length) why.push(JSON.stringify(await page.evaluate(async (tid) => {
      const get = async (p) => (await fetch(p, { headers: { "X-Taskuary-Token": localStorage.getItem("taskuary_token") } })).json();
      const a = await get(`/api/tasks/${tid}/assistant`), d = await get(`/api/tasks/${tid}`);
      return { dom: [...document.querySelectorAll("[data-tq-replaced], [data-tq-row-cards]")].map((e) => [e.outerHTML.slice(0, 80), e.getBoundingClientRect().height]), turns: a.turns, ids: a.messages.map((m) => [m.id, m.role, m.createdAt]), reviews: (d.reviews || []).map((r) => [r.ReviewId, r.Status, r.DecideNote, r.CreatedAt]) };
    }, tid)));
    if (o && !o.record && o.words !== before.old[0].words) why.push(`the old card's words changed: ${o.words.slice(0, 120)}`);
    if (o && Math.abs(o.top - before.old[0].top) > 2) why.push(`the old card moved ${before.old[0].top} -> ${o.top}`);
    if (s.bubble && o && !o.record && !(o.grey && !o.live)) why.push("his line is drawn and the old card is not grey");
    if (s.bubble && o && o.top > s.bubble.top) why.push("the old card is under his line");
    const others = s.cards.filter((c) => c.id !== String(rid));
    if (s.cards.filter((c) => c.live).length > 1) why.push("two live cards");
    for (const c of others) if (s.bubble && c.top < s.bubble.bottom) why.push(`a new card (${c.id}) above his line`);
    for (const c of others) if (s.head != null && c.top < s.head) why.push(`a new card (${c.id}) over the turn's head`);
    if (s.files) why.push(`${s.files} file preview card(s)`);
    if (/Files are in [A-Z]:\\/.test(s.text)) why.push("a 'Files are in C:\\...' line");
    if (why.length) { bad.push(`${at}: ${why.join("; ")}`); if (shot < 4) await page.screenshot({ path: path.join(out, `item3c-${name}-wrong-${shot++}.png`) }); }
    if (others.some((c) => c.live && c.words.includes("short version"))) { done = at; break; }
    await new Promise((r) => setTimeout(r, 100));
  }
  // ...AND ONCE THE TURN HAS ANSWERED, NO SECOND HEAD: every state the page commits for 4 s after the new card is live (the recorded walk,
  // 2026-11-10, frame 00353: a second running "AGENT · ran 5s ×" stood a beat under the new card as the turn filed its answer)
  const second = await page.evaluate(() => new Promise((done) => {
    const seen = [], t0 = performance.now(), look = () => {
      const vp = document.querySelector("[data-tq-task-page] .tq-aui-viewport"), answered = /Rewrote it short/.test(vp?.innerText || "");
      const extra = vp ? vp.querySelectorAll("[data-tq-pending-turn]").length + Math.max(0, vp.querySelectorAll("[data-tq-run-clock]").length - 1) : 0;   // ...the turn's own spin under its words is not one
      if (answered && extra && !seen.length) seen.push(Math.round(performance.now() - t0), [...vp.children].slice(-4).map((e) => `${e.className}`.split(" ").filter((c) => c.startsWith("tq-")).join(".") + (e.matches("[data-tq-pending-turn]") ? "[PENDING]" : "") + `[${(e.innerText || "").slice(0, 50).replace(/\s+/g, " ")}]`).join(" | "));
    };
    const obs = new MutationObserver(look); obs.observe(document.body, { subtree: true, childList: true, characterData: true, attributes: true });
    const frame = () => { look(); if (performance.now() - t0 < 4000) requestAnimationFrame(frame); else { obs.disconnect(); done(seen); } };
    requestAnimationFrame(frame);
  }));
  if (second.length) bad.push(`${second[0]} ms after the card: a second running head under the answered turn: ${second[1]}`);
  const end = await look(page, rid, said);
  await page.screenshot({ path: path.join(out, `item3c-${name}-end.png`) });
  // ...the recording ends before the test scrolls the record into view for its own picture: that scroll is not the page's
  await rec.stop();
  await page.evaluate(() => document.querySelector("[data-tq-replaced]")?.scrollIntoView({ block: "center" }));
  await page.screenshot({ path: path.join(out, `item3c-${name}-end-record.png`) });
  await writeFile(path.join(dir, "samples.json"), JSON.stringify({ before: { ...before, text: undefined }, samples }, null, 1));
  await copyFile(w.log, path.join(dir, "agent.jsonl")).catch(() => {});
  await writeFile(path.join(dir, "server.log"), w.backend.output());
  const ok = done != null && !bad.length;
  await note(dir, { done: `A reply drafted on arrival waits on the task (${name}); the owner types "${said}" into the task's box and presses Enter; the stand-in agent files a new letter with a file, as taskuary --reply does.`,
    expect: "At the press: his line, and the old card greyed in place - its words frozen, Send disabled. Under his line: the agent's head and spin, then the NEW card with the new letter, To, the file, Send - live. Never: the old card rewritten, moved, or under his line; two live cards; a file preview; a 'Files are in' line.",
    saw: done == null ? `no live new card within 90 s. Last: ${JSON.stringify(end.cards).slice(0, 600)}` : bad.length ? bad.slice(0, 6).join("\n") : `as expected; the new card live ${done} ms after the press`,
    verdict: ok ? "PASS" : "FAIL" });
  assert.ok(done != null, `${name}: no new live card under his line within 90 s: ${JSON.stringify(end.cards).slice(0, 800)}\n${end.text.slice(-1200)}`);
  assert.deepEqual(bad, [], `${name}: ${bad.slice(0, 5).join(" / ")}`);
  const after = end.cards.filter((c) => c.id !== String(rid) && c.live);
  assert.equal(after.length, 1, "one live card: the new one");
  assert.ok(after[0].words.includes("flaws.csv"), `the new card names its file: ${after[0].words.slice(0, 300)}`);
}

test("a reply rewritten after the owner prompts: the old card greys in place at the press, the new one stands live under his line", { timeout: 600000 }, async (t) => {
  const w = await world(t);
  const page = await w.newPage();
  await page.setViewport({ width: 1600, height: 900 });
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  const made = await w.api("/api/fixture/mail-task", {});
  assert.ok(made.taskId, JSON.stringify(made));
  await page.goto(w.ui, { waitUntil: "domcontentloaded" });
  await rewrite(t, w, page, { tid: made.taskId, rid: made.reviewId, name: process.env.N17_NAME || "rewrite-general" });
  assert.deepEqual(errors, []);
});
