import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { chmod, mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { startHarness } from "./harness.mjs";
import { note, record } from "./recorder.mjs";

/* AN ACT'S CARD NEVER LIGHTS AGAIN BEFORE IT SAYS WHAT WAS PRESSED (the owner, 2026-11-17: "when you click buttons on card it flickers then
   presses"). A comment on a tracker item waits on the task (ActionCard); he presses Dismiss, or its press. Every DOM change from the press is
   read: once pressed, its buttons may grey, and then the card is the pressed card - never its buttons lit again in between. Invented people only. */
const here = path.dirname(fileURLToPath(import.meta.url)), repo = path.resolve(here, "..", "..");
const out = path.join(process.env.TEMP || os.tmpdir(), "claude", "act-card");

async function world(t) {
  const bin = await mkdtemp(path.join(os.tmpdir(), "taskuary-fake-claude-"));
  t.after(() => rm(bin, { recursive: true, force: true }).catch(() => {}));
  const win = process.platform === "win32";
  const py = execFileSync(win ? "python" : "python3", ["-c", "import sys; print(sys.executable)"], { encoding: "utf8" }).trim();
  const fake = path.join(repo, "tests", "fake_claude.py");
  await writeFile(path.join(bin, win ? "claude.cmd" : "claude"), win ? `@${py} ${fake} %*\r\n` : `#!/bin/sh\nexec "${py}" "${fake}" "$@"\n`);
  if (!win) await chmod(path.join(bin, "claude"), 0o755);
  await writeFile(path.join(bin, "script.json"), "[]");
  Object.assign(process.env, { FAKE_CLAUDE_SCRIPT: path.join(bin, "script.json"), FAKE_CLAUDE_SPAWN: "0.5", FAKE_CLAUDE_THINK: "1" });
  const h = await startHarness({ fresh: true, bin });
  t.after(() => h.close());
  const api = (p, body) => fetch(`${h.fixtureApi}${p}`, { method: body ? "POST" : "GET",
    headers: { "Content-Type": "application/json", "X-Taskuary-Token": h.token }, body: body && JSON.stringify(body) }).then((r) => r.json());
  await api("/api/setup/first-run/ai", { name: "claude" });
  await api("/api/setup/dismiss", { dismissed: true });
  return { ...h, api };
}

// every committed state of the card from the press: its buttons lit, greyed, or none; and what it says
const watch = (page, sel, which, ms = 6000) => page.evaluate((sel, which, ms) => new Promise((done) => {
  const seen = [], t0 = performance.now();
  const read = () => {
    const c = document.querySelector(sel), bs = c ? [...c.querySelectorAll("button")] : [];
    const s = !c ? "gone" : !bs.length ? "pressed" : bs.some((b) => !b.disabled) ? "lit" : "busy";
    const text = (c?.innerText || "").replace(/\s+/g, " ").slice(-90), last = seen.at(-1);
    if (last?.s !== s || last?.text !== text) seen.push({ at: Math.round(performance.now() - t0), s, text, state: c?.getAttribute("data-tq-act-state") });
  };
  const obs = new MutationObserver(read); obs.observe(document.body, { subtree: true, childList: true, characterData: true, attributes: true });
  read();
  const b = document.querySelector(`${sel} ${which}`);
  if (!b) return done([{ s: "no-button", text: document.querySelector(sel)?.innerText }]);
  b.click();
  setTimeout(() => { obs.disconnect(); read(); done(seen); }, ms);
}), sel, which, ms);

const relitAfter = (states) => { const after = states.slice(1); return after.findIndex((x, i) => x.s === "lit" && after.slice(0, i).some((y) => y.s !== "lit")); };

// ...`elsewhere`: decided in another window before this one pressed - the press answers `already`, and the card reads what was decided
for (const [name, which, body, elsewhere, says] of [["dismiss", "[data-tq-act-dismiss]", { connected: true }, null, /dismissed/],
  ["post-fails", "[data-tq-act-press]", { connected: true }, null, /blocked outbound/],
  ["dismissed-elsewhere", "[data-tq-act-press]", { connected: true }, "reject", /dismissed/]]) {
  test(`an act's card pressed (${name}) never lights again before it says what was pressed`, { timeout: 300000 }, async (t) => {
    const w = await world(t), page = await w.newPage();
    await page.setViewport({ width: 1600, height: 900 });
    const errors = []; page.on("pageerror", (e) => errors.push(e.message));
    const made = await w.api("/api/fixture/act-card", body);
    assert.ok(made.taskId, JSON.stringify(made));
    await page.goto(w.ui, { waitUntil: "domcontentloaded" });
    await page.evaluate((id) => { location.hash = `task=${id}`; }, made.taskId);
    const sel = `[data-tq-task-page] [data-tq-act="${made.reviewId}"]`;
    await page.waitForSelector(sel, { visible: true, timeout: 60000 });
    await new Promise((r) => setTimeout(r, 2500));
    const dir = path.join(out, "video", name); await mkdir(dir, { recursive: true });
    if (elsewhere) await w.api(`/api/reviews/${made.reviewId}/decide`, { verb: elsewhere, final_text: null, note: null });
    const rec = await record(page, dir);
    const states = await watch(page, sel, which);
    // ...and once the chat is read again it is still that card, pressed, with its words - never swapped for another (2026-11-18)
    const kept = await page.evaluate((sel) => document.querySelector(sel)?.innerText.replace(/\s+/g, " ") || "", sel);
    await rec.stop();
    await writeFile(path.join(dir, "states.json"), JSON.stringify(states, null, 1));
    const relit = relitAfter(states);
    await note(dir, { done: `An act's card waits; the owner presses ${name}.`, expect: "Its buttons grey, then the card says what was pressed - never lit again between.",
      saw: JSON.stringify(states), verdict: relit < 0 ? "PASS" : "FAIL" });
    assert.notEqual(states[0]?.s, "no-button", `no button on the card: ${states[0]?.text}`);
    assert.equal(relit, -1, `the card lit its buttons again after the press: ${JSON.stringify(states)}`);
    assert.match(kept, says, `the pressed card does not say what came of it: ${kept}`);
    assert.doesNotMatch(kept, /Try again|didn't go through/, `a press decided elsewhere read as a failure: ${kept}`);
    assert.match(kept, /deployed this morning/, `the pressed card went from where it stood: ${JSON.stringify(states)}`);
    assert.ok(!states.some((x) => x.s === "gone"), `the card went, or was swapped for another, after the press: ${JSON.stringify(states)}`);
    assert.deepEqual(errors, []);
  });
}

test("an act's card whose tracker is not connected offers Connect, never a Post that can only fail", { timeout: 300000 }, async (t) => {
  const w = await world(t), page = await w.newPage();
  await page.setViewport({ width: 1600, height: 900 });
  const made = await w.api("/api/fixture/act-card", {});
  await page.goto(w.ui, { waitUntil: "domcontentloaded" });
  await page.evaluate((id) => { location.hash = `task=${id}`; }, made.taskId);
  const sel = `[data-tq-task-page] [data-tq-act="${made.reviewId}"]`;
  await page.waitForSelector(`${sel} [data-tq-act-connect]`, { visible: true, timeout: 60000 });
  assert.equal(await page.$(`${sel} [data-tq-act-press]`), null, "Post comment lit beside Connect");
});

// ...ITS WORDS AND CHOICES EDITED, THEN PRESSED, AND IT LANDS: the press says the pick ("Save as draft"), and the card says it went in the
// pick's words with its link - his words, never the agent's, from the press to the read after it
test("a post with its words and a choice edited lands as edited, and its card says so with no relight", { timeout: 300000 }, async (t) => {
  const w = await world(t), page = await w.newPage();
  await page.setViewport({ width: 1600, height: 900 });
  const errors = []; page.on("pageerror", (e) => errors.push(e.message));
  const made = await w.api("/api/fixture/act-card", { connected: true, lands: "linkedin_post", title: "Gas prices post",
    post: { action: "run_tool", type: "linkedin_post", text: "Gas rose 4 cents this week.", visibility: "CONNECTIONS", publish: "now" } });
  await page.goto(w.ui, { waitUntil: "domcontentloaded" });
  await page.evaluate((id) => { location.hash = `task=${id}`; }, made.taskId);
  const sel = `[data-tq-task-page] [data-tq-act="${made.reviewId}"]`;
  await page.waitForSelector(`${sel} [data-tq-act-press]`, { visible: true, timeout: 60000 });
  await new Promise((r) => setTimeout(r, 1500));
  await page.select(`${sel} select[data-tq-act-choice=publish]`, "draft");
  await page.$eval(`${sel} textarea[data-tq-act-text]`, (x) => { x.focus(); x.select(); }); await page.keyboard.type("Gas rose 5 cents this week.");
  assert.match(await page.$eval(`${sel} [data-tq-act-press]`, (b) => b.innerText), /Save as draft/);
  const dir = path.join(out, "video", "edited-lands"); await mkdir(dir, { recursive: true });
  const rec = await record(page, dir);
  const states = await watch(page, sel, "[data-tq-act-press]");
  await rec.stop();
  await writeFile(path.join(dir, "states.json"), JSON.stringify(states, null, 1));
  const kept = await page.evaluate((sel) => document.querySelector(sel)?.innerText.replace(/\s+/g, " ") || "", sel);
  await note(dir, { done: "A post waits; the owner edits its words, picks Save as draft and presses.", expect: "Saving, then the card says Saved as a draft with his words and its link.",
    saw: JSON.stringify(states), verdict: relitAfter(states) < 0 ? "PASS" : "FAIL" });
  assert.equal(relitAfter(states), -1, `relit: ${JSON.stringify(states)}`);
  // ...every state after the press says his words, never the agent's coming back for a beat
  assert.ok(!states.filter((x) => x.s === "pressed").some((x) => /4 cents|Post now/.test(x.text)), `the agent's words came back after the press: ${JSON.stringify(states)}`);
  assert.match(kept, /^.*Save as draft Gas rose 5 cents this week\. ✓ Saved as a draft/); assert.match(kept, /See it on LinkedIn/);
  const sent = (await w.api(`/api/tasks/${made.taskId}/assistant`)).cards.find((c) => c.ReviewId === made.reviewId);
  assert.equal(sent.post.result?.url, "https://social.example/alex/posts/1"); assert.equal(sent.post.text, "Gas rose 5 cents this week."); assert.equal(sent.post.publish, "draft");
  assert.deepEqual(errors, []);
});

// ...POSTED FROM ANOTHER WINDOW WHILE THIS ONE HELD AN EDIT: the press here answers `already`, and the card says what went - the other window's
// words - never this window's edit as if it had been posted
test("a post sent from another window is said in the words that went, not this window's edit", { timeout: 300000 }, async (t) => {
  const w = await world(t), page = await w.newPage();
  await page.setViewport({ width: 1600, height: 900 });
  const made = await w.api("/api/fixture/act-card", { connected: true, lands: "linkedin_post", title: "Gas prices post",
    post: { action: "run_tool", type: "linkedin_post", text: "Gas rose 4 cents this week.", visibility: "CONNECTIONS", publish: "now" } });
  await page.goto(w.ui, { waitUntil: "domcontentloaded" });
  await page.evaluate((id) => { location.hash = `task=${id}`; }, made.taskId);
  const sel = `[data-tq-task-page] [data-tq-act="${made.reviewId}"]`;
  await page.waitForSelector(`${sel} [data-tq-act-press]`, { visible: true, timeout: 60000 });
  await page.$eval(`${sel} textarea[data-tq-act-text]`, (x) => { x.focus(); x.select(); }); await page.keyboard.type("An edit never sent.");
  await w.api(`/api/reviews/${made.reviewId}/decide`, { verb: "approve", final_text: "Gas rose 6 cents this week.", note: null });
  const states = await watch(page, sel, "[data-tq-act-press]", 4000);
  assert.notEqual(states[0]?.s, "no-button", "the card had already turned before the press");
  assert.ok(!states.filter((x) => x.s === "pressed").some((x) => /never sent/.test(x.text)), `this window's edit was said as posted: ${JSON.stringify(states)}`);
  assert.equal(relitAfter(states), -1, `relit: ${JSON.stringify(states)}`);
  assert.match(await page.$eval(sel, (c) => c.innerText), /6 cents/);
});
