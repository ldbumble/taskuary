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

async function world(t, script = SCRIPT) {
  const bin = await mkdtemp(path.join(os.tmpdir(), "taskuary-fake-claude-"));
  t.after(() => rm(bin, { recursive: true, force: true }).catch(() => {}));
  const win = process.platform === "win32";
  const py = execFileSync(win ? "python" : "python3", ["-c", "import sys; print(sys.executable)"], { encoding: "utf8" }).trim();
  const fake = path.join(repo, "tests", "fake_claude.py");
  await writeFile(path.join(bin, win ? "claude.cmd" : "claude"), win ? `@${py} ${fake} %*\r\n` : `#!/bin/sh\nexec "${py}" "${fake}" "$@"\n`);
  if (!win) await chmod(path.join(bin, "claude"), 0o755);
  await writeFile(path.join(bin, "script.json"), JSON.stringify(script));
  Object.assign(process.env, { FAKE_CLAUDE_SCRIPT: path.join(bin, "script.json"), FAKE_ACP_SCRIPT: path.join(bin, "script.json"), FAKE_CLAUDE_SPAWN: "0.5", FAKE_CLAUDE_THINK: "3", FAKE_CLAUDE_LOG: path.join(bin, "log.jsonl") });
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

// ...AND THE SAME IN A CODING CHAT (one road for both chats): the task's agent is the stand-in ACP adapter (fixture/coding), which files the new
// letter as the real one's shell does (FAKE_ACP_SCRIPT -> `taskuary --reply`)
// ...a coding start held the arrival draft, so for the turn's first second the old card was gone from the chat (2026-11-11): it holds only an
// earlier session's now, as a chat's start does
test("a reply rewritten in a coding chat: the old card greys in place at the press, the new one stands live under his line", { timeout: 600000 }, async (t) => {
  const w = await world(t);
  const page = await w.newPage();
  await page.setViewport({ width: 1600, height: 900 });
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  const git = execFileSync(process.platform === "win32" ? "where" : "which", ["git"], { encoding: "utf8" }).trim().split(/\s*\n/)[0].trim();
  const repo = await w.api("/api/fixture/coding", { git });
  assert.ok(repo.taskId, `the coding home is set up: ${JSON.stringify(repo)}`);
  const made = await w.api("/api/fixture/mail-task", { kind: "coding" });
  assert.ok(made.taskId, JSON.stringify(made));
  await page.goto(w.ui, { waitUntil: "domcontentloaded" });
  await rewrite(t, w, page, { tid: made.taskId, rid: made.reviewId, name: process.env.N17_NAME || "rewrite-coding" });
  assert.deepEqual(errors, []);
});

// A STRANGER'S TASK ON A CLI TOO OLD FOR ITS REVIEWER (the walk, 2026-11-10): its first turn drew a running head with nothing behind it and never
// said why. It reads and answers in the CLI's read-only mode now (origin.launch_mode 'look') - and the reply drafted on arrival, which the
// answer left alone, stays under the mail it answers: it jumped from over his line to under the answer's Next steps (general.draft_turns)
test("a stranger's task on a CLI too old for its reviewer answers under the owner's line, the arrival draft staying where it stood", { timeout: 300000 }, async (t) => {
  process.env.FAKE_CLAUDE_VERSION = "2.1.100";
  t.after(() => { delete process.env.FAKE_CLAUDE_VERSION; });
  const w = await world(t);
  const page = await w.newPage();
  await page.setViewport({ width: 1600, height: 900 });
  const made = await w.api("/api/fixture/mail-task", { stranger: true });
  await page.goto(w.ui, { waitUntil: "domcontentloaded" });
  await page.evaluate((id) => { location.hash = `task=${id}`; }, made.taskId);
  const name = process.env.N17_NAME || "stranger-old-cli", dir = path.join(out, "video", name); await mkdir(dir, { recursive: true });
  await page.waitForSelector("[data-tq-task-page] .tq-aui-input", { visible: true, timeout: 60000 });
  const rec = await record(page, dir);
  const said = "make it shorter and attach the sheet";
  await page.evaluate(() => document.querySelector("[data-tq-task-page] .tq-aui-input")?.focus());
  await page.keyboard.type(said); await page.keyboard.press("Enter");
  const t0 = Date.now(), bad = []; let answered = false;
  while (Date.now() - t0 < 90000) {
    const s = await look(page, made.reviewId, said), card = s.old[0];
    answered = /\bOk\.|could not|did not start|Trust them/.test(s.text.slice(s.text.lastIndexOf(said)));
    if (card && s.bubble && card.top > s.bubble.top) bad.push(`${Date.now() - t0} ms: the arrival draft stands under his line`);
    if (answered && Date.now() - t0 > 2000) { await new Promise((r) => setTimeout(r, 2500)); const e = await look(page, made.reviewId, said);
      if (e.old[0] && e.bubble && e.old[0].top > e.bubble.top) bad.push("at rest: the arrival draft stands under his line"); break; }
    await new Promise((r) => setTimeout(r, 100));
  }
  await page.screenshot({ path: path.join(out, `${name}.png`) });
  await rec.stop();
  const text = await page.evaluate(() => document.querySelector("[data-tq-task-page] .tq-aui-viewport")?.innerText || "");
  await note(dir, { done: "A stranger's mail task with a reply drafted on arrival; the stand-in CLI reports a version too old for a stranger's reviewer; the owner types a line.",
    expect: "Under his line the agent's head and its answer (read-only); the arrival draft stays above his line, under the mail, greyed in place.",
    saw: !answered ? `no answer within 90 s:\n${text.slice(-600)}` : bad.length ? bad.slice(0, 3).join("\n") : "answered under his line; the draft stayed where it stood",
    verdict: answered && !bad.length ? "PASS" : "FAIL" });
  assert.ok(answered, `the turn answered under his line:\n${text.slice(-800)}`);
  assert.deepEqual(bad.slice(0, 3), []);
});

// A HELD CARD IS A ROW IN THE CHAT, AND THE AGENT GOES ON UNDER IT (the owner, 2026-11-10: "it's just a row in the chat"; rules part 1: the agent
// sets the step up as one card and says what it does after the press). The owner asks for a playbook; the stand-in agent files it for his press
// (`taskuary --propose write_playbook`); he presses Approve; the agent is woken and answers. Sampled every 100 ms from the press to the answer:
// nothing of a turn - head, clock, spin - ever stands above the card, and the answer stands under it
const PLAY = [{ when: "pressed .* went through", anywhere: true, first: "Saved - the next vendor review follows it." },
  { when: "keep how we review vendors", anywhere: true, first: "Set it up as a playbook - press Approve and I file it.",
    post: [{ path: "/api/agent/propose", body: { action: "write_playbook", slug: "vendor-review", text: "# Vendor review\nwhen: a vendor tool is to be reviewed\n\nRead the tool's export first, then its sign-on.", why: "so the next vendor review goes the same way" } }] }];
test("a held card is a row in the chat: after Approve the agent's turn stands under it, nothing spins above it", { timeout: 300000 }, async (t) => {
  const w = await world(t, PLAY);
  const page = await w.newPage();
  await page.setViewport({ width: 1600, height: 900 });
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  const made = await w.api("/api/fixture/mail-task", {});
  await page.goto(w.ui, { waitUntil: "domcontentloaded" });
  await page.evaluate((id) => { location.hash = `task=${id}`; }, made.taskId);
  const name = process.env.N17_NAME || "held-approve", dir = path.join(out, "video", name); await mkdir(dir, { recursive: true });
  await page.waitForSelector("[data-tq-task-page] .tq-aui-input", { visible: true, timeout: 60000 });
  const rec = await record(page, dir), bad = [];
  let pressed = null, done = null;
  try {
    await page.evaluate(() => document.querySelector("[data-tq-task-page] .tq-aui-input")?.focus());
    await page.keyboard.type("keep how we review vendors"); await page.keyboard.press("Enter");
    await page.waitForFunction(() => [...document.querySelectorAll("[data-tq-task-page] button")].some((b) => /^Approve/.test(b.innerText.trim()) && !b.disabled),
      { timeout: 60000, polling: 200 });
    await new Promise((r) => setTimeout(r, 1500));
    // ...the card: the box round the Approve that names the playbook's why
    const look = () => page.evaluate(() => {
      const pane = document.querySelector("[data-tq-task-page]"), vp = pane?.querySelector(".tq-aui-viewport");
      const y = (r) => Math.round(r.top - (vp ? vp.getBoundingClientRect().top - vp.scrollTop : 0));
      // ...by where it saves, which it says waiting and pressed alike (PassedCard)
      const title = [...pane.querySelectorAll("*")].filter((e) => e.children.length === 0 && /Playbooks → vendor-review\.md/.test(e.textContent) && e.getBoundingClientRect().height > 0).pop();
      const card = title?.closest("[data-tq-passed]") || title?.closest(".tq-aui-message") || title;
      const turn = [...(vp?.querySelectorAll("[data-tq-run-clock], [data-tq-pending-turn], .tq-aui-thinking, [data-tq-working]") || [])].filter((e) => e.getBoundingClientRect().height > 0);
      const saved = [...(vp?.querySelectorAll(".tq-aui-agent") || [])].find((e) => /Saved - the next vendor review/.test(e.innerText));
      return { card: card ? { top: y(card.getBoundingClientRect()), bottom: y({ top: card.getBoundingClientRect().bottom }) } : null,
        above: turn.map((e) => ({ top: y(e.getBoundingClientRect()), html: e.outerHTML.slice(0, 120) })), saved: saved ? y(saved.getBoundingClientRect()) : null,
        working: /Working|Starting…|Continuing…/.test(vp?.innerText || ""), approved: !!card?.querySelector?.('[data-tq-pressed="approved"]'),
        // ...Taskuary's head over its word to the agent ("Taskuary left 1 note for you. Take them in order:") is the agent's, never his screen's
        machinery: /notes? for you|Take them in order/.test(vp?.innerText || "") };
    });
    const before = await look();
    assert.ok(before.card, "the held card is drawn");
    await page.evaluate(() => [...document.querySelectorAll("[data-tq-task-page] button")].find((b) => /^Approve/.test(b.innerText.trim()) && !b.disabled).click());
    pressed = Date.now();
    while (Date.now() - pressed < 60000) {
      const s = await look(), at = Date.now() - pressed, why = [];
      if (!s.card) why.push("the card is gone from the chat");
      if (s.machinery) why.push("Taskuary's note to the agent drawn as a line");
      if (s.card) for (const h of s.above) if (h.top < s.card.top) why.push(`a turn's ${h.html.slice(0, 60)} above the card`);
      if (s.working) why.push("the old 'Working' words");
      if (s.saved != null && s.card && s.saved < s.card.bottom) why.push("the answer above the card");
      if (why.length) bad.push(`${at}: ${why.join("; ")}`);
      if (s.saved != null) { done = at; break; }
      await new Promise((r) => setTimeout(r, 100));
    }
    await new Promise((r) => setTimeout(r, 1500));
    // ...and at rest: the card where it stood, its press drawn pressed - his press's record in the chat (the owner, 2026-11-09)
    const end = await look();
    if (!end.card || !end.approved) bad.push(`at rest: the card ${end.card ? "stands unpressed" : "is gone"}`);
  } finally {
    await page.screenshot({ path: path.join(out, `${name}.png`) });
    await rec.stop();
    await writeFile(path.join(dir, "server.log"), w.backend.output()); await copyFile(w.log, path.join(dir, "agent.jsonl")).catch(() => {});
    await note(dir, { done: "A general task; the owner asks the agent to keep how vendors are reviewed; the stand-in agent files a playbook for his press; he presses Approve.",
      expect: "The card a row in the chat. After Approve: the card stays where it stood, pressed (✓ Approved), the agent's head under it at once, its answer under it - nothing spinning above the card, no 'Working' words, no 'Taskuary left 1 note' line.",
      saw: done == null ? "no answer under the card within 60 s" : bad.length ? bad.slice(0, 5).join("\n") : `as expected; the answer ${done} ms after the press`,
      verdict: done != null && !bad.length ? "PASS" : "FAIL" });
  }
  assert.ok(done != null, "the agent answered after the press");
  assert.deepEqual(bad.slice(0, 5), []);
  assert.deepEqual(errors, []);
});

// A START REFUSED FOR A STRANGER IS KEPT WHERE IT HAPPENED, WITH THE WAY PAST IT (rules part 4; the walk, 2026-11-10: a running "AGENT · ran 32s"
// head with nothing behind it, never saying why). The AI is a CLI too old for its reviewer and with no read-only mode Taskuary can hold it to (/api/fixture/no-readonly), so a
// stranger's task cannot start on it (origin.launch_mode). The owner types a line: under it, the hold in one sentence and its Trust press - never
// a running head that goes on with nothing in it
test("a stranger's task its AI cannot start says why under the owner's line, with the Trust press", { timeout: 300000 }, async (t) => {
  process.env.FAKE_CLAUDE_VERSION = "2.1.100";
  t.after(() => { delete process.env.FAKE_CLAUDE_VERSION; });
  const w = await world(t);
  assert.ok((await w.api("/api/fixture/no-readonly", {})).ok);
  const page = await w.newPage();
  await page.setViewport({ width: 1600, height: 900 });
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  const made = await w.api("/api/fixture/mail-task", { stranger: true });
  await page.goto(w.ui, { waitUntil: "domcontentloaded" });
  await page.evaluate((id) => { location.hash = `task=${id}`; }, made.taskId);
  const name = process.env.N17_NAME || "stranger-refused", dir = path.join(out, "video", name); await mkdir(dir, { recursive: true });
  await page.waitForSelector("[data-tq-task-page] .tq-aui-input", { visible: true, timeout: 60000 });
  const rec = await record(page, dir), said = "make it shorter and attach the sheet", bad = [];
  let held = null, last = null;
  try {
    await page.evaluate(() => document.querySelector("[data-tq-task-page] .tq-aui-input")?.focus());
    await page.keyboard.type(said); await page.keyboard.press("Enter");
    const t0 = Date.now();
    while (Date.now() - t0 < 45000) {
      last = await page.evaluate((said) => {
        const vp = document.querySelector("[data-tq-task-page] .tq-aui-viewport"), text = vp?.innerText || "", at = text.lastIndexOf(said);
        const after = at < 0 ? "" : text.slice(at + said.length);
        const trust = [...document.querySelectorAll("[data-tq-task-page] button")].some((b) => /^Trust/.test(b.innerText.trim()) && b.getBoundingClientRect().width > 0);
        const ran = /ran (\d+)s/.exec(after);
        return { why: /cannot be kept to only reading|Trust them|Waiting for you|did not start|couldn.t start/i.test(after), trust, ran: ran ? +ran[1] : null,
          clock: !!vp?.querySelector("[data-tq-run-clock]"), after: after.slice(0, 400) };
      }, said);
      if (last.why && last.trust) { held = Date.now() - t0; break; }
      if (last.clock && last.ran != null && last.ran >= 15) bad.push(`${Date.now() - t0} ms: a running head at ${last.ran}s, nothing said`);
      await new Promise((r) => setTimeout(r, 200));
    }
    await new Promise((r) => setTimeout(r, 4000));
    last = await page.evaluate(() => { const c = document.querySelector("[data-tq-task-page] .tq-aui-viewport [data-tq-run-clock]");
      return { clock: !!c, of: c ? (c.closest("[data-tq-pending-turn]") ? "pending" : c.closest("[data-tq-chat-line]")?.getAttribute("data-tq-chat-line") || c.parentElement?.outerHTML.slice(0, 200)) : "",
        text: (document.querySelector("[data-tq-task-page] .tq-aui-viewport")?.innerText || "").slice(-300) }; });
    if (held != null && await page.$("[data-tq-task-page] [data-tq-run-anyway]")) bad.push("Run anyway offered on a start this AI refuses - it cannot work");
    if (held != null && last.clock) bad.push(`a running head still over the hold, 4 s on (${last.of}) ${JSON.stringify(await page.evaluate(async (id) => {
      const get = async (p) => (await fetch(p, { headers: { "X-Taskuary-Token": localStorage.getItem("taskuary_token") } })).json();
      const a = await get(`/api/tasks/${id}/assistant`), d = await get(`/api/tasks/${id}`);
      return { working: a.working, starting: a.starting, session: a.session && { busy: a.session.busy, alive: a.session.alive }, dStarting: d.starting, story: d.agentStory?.kind }; }, made.taskId))}`);
  } finally {
    await page.screenshot({ path: path.join(out, `${name}.png`) });
    await rec.stop();
    await writeFile(path.join(dir, "server.log"), w.backend.output());
    await writeFile(path.join(dir, "payload.json"), JSON.stringify(await w.api(`/api/tasks/${made.taskId}/assistant`), null, 1)).catch(() => {});
    await note(dir, { done: "A stranger's mail task; the AI is a CLI Taskuary cannot hold to reading for a stranger (no reviewer, no read-only mode); the owner types a line.",
      expect: "Under his line: why it cannot start, in one sentence, and the Trust press - the way past it; no Run anyway (it would be refused again). No head running on with nothing behind it.",
      saw: held == null ? `nothing said within 45 s: ${JSON.stringify(last).slice(0, 500)}` : bad.length ? bad.slice(0, 4).join("\n") : `the hold and its Trust ${held} ms after the press`,
      verdict: held != null && !bad.length ? "PASS" : "FAIL" });
  }
  assert.ok(held != null, `the hold is said under his line with its Trust: ${JSON.stringify(last)}`);
  assert.deepEqual(bad.slice(0, 4), []);
  assert.deepEqual(errors, []);
});

// A CODING AGENT'S QUESTION IS ON ITS CHAT, AND HIS ANSWER IS HIS NEXT LINE (one road with the general chat, 2026-11-11): the coding payload carries
// what the agent asks (taskstate.asking) and the page read it on a general task only - the question stood nowhere but in the agent's words. Typed
// into the box, the answer goes the way every line to it goes (general.take_line), never the terminal's answer road (/worker/answer)
const ASKS = [{ when: "yes, with tax", anywhere: true, first: "Done - the totals include tax now." },
  { when: "comment the totals", anywhere: true, first: "Read totals.py.\n\n[[TASKUARY-ASK]] Should the totals include tax? | Yes | No" }];
test("a coding agent's question stands in its chat; the owner's typed answer is his next line and the agent goes on under it", { timeout: 300000 }, async (t) => {
  const w = await world(t, ASKS);
  const page = await w.newPage();
  await page.setViewport({ width: 1600, height: 900 });
  const errors = [], answers = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("request", (r) => { if (/\/worker\/answer/.test(r.url())) answers.push(r.url()); });
  const git = execFileSync(process.platform === "win32" ? "where" : "which", ["git"], { encoding: "utf8" }).trim().split(/\s*\n/)[0].trim();
  const made = await w.api("/api/fixture/coding", { git });
  await page.goto(w.ui, { waitUntil: "domcontentloaded" });
  await page.evaluate((id) => { location.hash = `task=${id}`; }, made.taskId);
  const name = process.env.N17_NAME || "coding-asks", dir = path.join(out, "video", name); await mkdir(dir, { recursive: true });
  // ...its first line posted as the page posts one (browser/coding-line-timeline): a coding task with no session yet draws its box once it has one
  await w.api(`/api/tasks/${made.taskId}/assistant/messages`, { text: "comment the totals" });
  await page.waitForSelector("[data-tq-task-page] .tq-aui-input", { visible: true, timeout: 60000 });
  const rec = await record(page, dir), bad = [], said = "yes, with tax";
  const vp = () => page.evaluate(() => { const v = document.querySelector("[data-tq-task-page] .tq-aui-viewport");
    return { text: v?.innerText || "", asks: v?.querySelectorAll("[data-tq-asking]").length || 0 }; });
  let asked = null, done = null;
  try {
    const t0 = Date.now();
    while (Date.now() - t0 < 60000 && !asked) { const s = await vp(); if (s.asks) asked = s; else await new Promise((r) => setTimeout(r, 200)); }
    if (!asked) bad.push("the question never stood on the chat");
    else if (/TASKUARY-ASK/.test(asked.text)) bad.push("the bare marker is drawn");
    await new Promise((r) => setTimeout(r, 1000));
    await page.evaluate(() => document.querySelector("[data-tq-task-page] .tq-aui-input")?.focus());
    await page.keyboard.type(said); await page.keyboard.press("Enter");
    const t1 = Date.now();
    while (Date.now() - t1 < 60000) {
      const s = await vp(), mine = s.text.lastIndexOf(said), ans = s.text.indexOf("the totals include tax now");
      if (mine < 0 && Date.now() - t1 > 1500) bad.push(`${Date.now() - t1} ms: his answer is not drawn`);
      if (ans >= 0) { if (mine < 0 || ans < mine) bad.push("the agent's answer is not under his line"); done = Date.now() - t1; break; }
      await new Promise((r) => setTimeout(r, 200));
    }
    await new Promise((r) => setTimeout(r, 2000));
    if ((await vp()).asks) bad.push("the question still stands after the agent answered");
    if (answers.length) bad.push(`the answer went the terminal's road: ${answers[0]}`);
  } finally {
    await page.screenshot({ path: path.join(out, `${name}.png`) });
    await rec.stop();
    await writeFile(path.join(dir, "server.log"), w.backend.output());
    await note(dir, { done: "A coding task on the stand-in ACP agent; the owner asks it to comment the totals; it asks whether totals include tax; he types 'yes, with tax'.",
      expect: "The question in the chat as the agent's (no bare marker); his answer drawn as his line at the press; the agent's next turn under it; the question gone.",
      saw: !asked ? "no question on the chat within 60 s" : done == null ? "no answer under his line within 60 s" : bad.length ? bad.slice(0, 4).join("\n") : `as expected; answered ${done} ms after his line`,
      verdict: asked && done != null && !bad.length ? "PASS" : "FAIL" });
  }
  assert.ok(asked, "the question stands on the chat");
  assert.ok(done != null, "the agent answered under his line");
  assert.deepEqual([...new Set(bad)].slice(0, 4), []);
  assert.deepEqual(errors, []);
});
