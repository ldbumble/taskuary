import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { chmod, mkdtemp, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { startHarness } from "./harness.mjs";

/* THE PANE SPLITTING IS NOT A REPLAY (the owner, 2026-11-03: "when you are using codex when it splits pane it scrolls from the top. stop
   that."). Codex - and Claude Code - clear the screen and print their whole history again on every change of the pty's size, a few lines a
   frame, so a pane that narrows (Close out opened beside the agent, the window made smaller) watched the session scroll from its first line
   down to the bottom. ...AND READING HIGHER UP STAYS PUT ("did you fix the codex cli that is always scrolling down???"): the same reprint,
   on any resize, left the pane on its bottom under an owner reading its history. A stand-in claude in a pty (tests/fake_claude.py,
   FAKE_CLAUDE_HISTORY, FAKE_CLAUDE_TICK) does exactly that while it keeps working; on every frame drawn the pane never shows the top of
   its history, it follows the bottom while the owner is there, stays where they scrolled to through new output, a split and the page's
   polls, and follows again once they are back at the bottom - the same xterm throughout. Invented task and people only. */
const here = path.dirname(fileURLToPath(import.meta.url)), repo = path.resolve(here, "..", "..");
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const LINES = 400, FIRST = "history line 000";

async function agentWorld(t) {
  const bin = await mkdtemp(path.join(os.tmpdir(), "taskuary-fake-claude-"));
  t.after(() => rm(bin, { recursive: true, force: true }).catch(() => {}));
  const win = process.platform === "win32";
  const py = execFileSync(win ? "python" : "python3", ["-c", "import sys; print(sys.executable)"], { encoding: "utf8" }).trim();
  const fake = path.join(repo, "tests", "fake_claude.py");
  await writeFile(path.join(bin, win ? "claude.cmd" : "claude"), win ? `@${py} ${fake} %*\r\n` : `#!/bin/sh\nexec "${py}" "${fake}" "$@"\n`);
  if (!win) await chmod(path.join(bin, "claude"), 0o755);
  Object.assign(process.env, { FAKE_CLAUDE_SPAWN: "0.3", FAKE_CLAUDE_THINK: "0.2", FAKE_CLAUDE_HISTORY: String(LINES), FAKE_CLAUDE_TICK: "0.4" });
  const h = await startHarness({ fresh: true, bin });
  t.after(() => h.close());
  const api = (p, body, method) => fetch(`${h.fixtureApi}${p}`, { method: method || (body ? "POST" : "GET"),
    headers: { "Content-Type": "application/json", "X-Taskuary-Token": h.token }, body: body && JSON.stringify(body) }).then((r) => r.json());
  await api("/api/setup/first-run/ai", { name: "claude" });
  await api("/api/setup/dismiss", { dismissed: true });
  await api("/api/settings", { name: "developer_mode", value: "1" }, "PATCH");
  return { ...h, api };
}

const rows = (page) => page.evaluate(() => document.querySelector("[data-tq-task-page] .xterm-rows")?.textContent || "");
// where the viewport stands: its first line's words, its offset and the buffer's bottom (TerminalView's el.tqTerm)
const view = (page) => page.evaluate(() => {
  const b = document.querySelector("[data-tq-task-page] .xterm")?.parentElement?.tqTerm?.buffer.active;
  return b && { vy: b.viewportY, by: b.baseY, first: b.getLine(b.viewportY)?.translateToString(true) || "" };
});
// every frame the browser paints: what the owner SEES (a still frame laid over the rows hides them), where the viewport is, and whether it
// is still the same xterm
const watch = (page) => page.evaluate(() => {
  const host = document.querySelector("[data-tq-task-page] .xterm").parentElement, term = host.tqTerm;
  window.tqFrames = [];
  const tick = () => {
    const now = document.querySelector("[data-tq-task-page] .xterm")?.parentElement, held = now?.querySelector("[data-tq-held-frame]");
    const text = (held || now?.querySelector(".xterm-rows"))?.textContent || "", b = now?.tqTerm?.buffer.active;
    window.tqFrames.push({ top: text.includes("history line 000"), n: Math.max(-1, ...[...text.matchAll(/history line (\d+)/g)].map((m) => +m[1])), held: !!held, same: now === host && now.tqTerm === term,
      vy: b?.viewportY ?? -1, by: b?.baseY ?? -1, first: b?.getLine(b.viewportY)?.translateToString(true) || "" });
    if (window.tqFrames.length < 100000) requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
});
const frames = (page) => page.evaluate(() => window.tqFrames);

test("a Codex-style reprint never shows the pane scrolling from the top, and reading higher up stays put", { timeout: 300000 }, async (t) => {
  const w = await agentWorld(t);
  const page = await w.newPage();
  await page.setViewport({ width: 1600, height: 900 });
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(w.ui, { waitUntil: "domcontentloaded" });
  const made = await w.api("/api/tasks", { Title: "Fix the vendor export", Summary: "The vendor export drops the date column for Northwind", Kind: "coding" });
  const dir = await mkdtemp(path.join(os.tmpdir(), "taskuary-ledger-"));
  t.after(() => rm(dir, { recursive: true, force: true }).catch(() => {}));
  await w.api(`/api/tasks/${made.taskId}/repo`, { repo: "northwind/ledger", path: dir }, "PUT");
  await page.evaluate((id) => { location.hash = `task=${id}`; }, made.taskId);

  await page.waitForFunction(() => [...document.querySelectorAll("button")].some((b) => !b.disabled && b.textContent.trim() === "Send to agent" && b.offsetParent), { timeout: 30000 });
  await page.evaluate(() => [...document.querySelectorAll("button")].find((b) => !b.disabled && b.textContent.trim() === "Send to agent" && b.offsetParent).click());
  await page.waitForSelector("[data-tq-run-form] textarea", { visible: true, timeout: 15000 });
  await page.type("[data-tq-run-form] textarea", "find the export bug");
  await page.waitForSelector("[data-tq-run-form] [data-tq-agent-start=coding]:not([disabled])", { timeout: 20000 });
  await page.$eval("[data-tq-run-form] [data-tq-agent-start=coding]:not([disabled])", (b) => b.click());
  await page.waitForSelector("[data-tq-task-page] .xterm-rows", { timeout: 30000 })
    .catch(async () => assert.fail(`no agent pane\n--- server:\n${w.backend.output().slice(-3000)}`));
  await page.waitForFunction(() => /history line 399/.test(document.querySelector("[data-tq-task-page] .xterm-rows")?.textContent || "")
    && !document.body.innerText.includes("restoring the session"), { timeout: 30000 })
    .catch(async () => assert.fail(`the history never settled on the pane:\n${(await rows(page)).slice(-1500)}`));
  await sleep(2500);                                    // the first fit's reprint, under the curtain, is done
  assert.ok(!(await rows(page)).includes(FIRST), "the pane does not start on the bottom");

  // what every frame must hold: never the top of the history, never a new xterm, never a viewport near the top outside a still frame
  const looked = async (say) => {
    await sleep(3500);
    const f = await frames(page);
    assert.ok(f.length > 20, `too few frames painted ${say}: ${f.length}`);
    const top = f.findIndex((x) => x.top || (!x.held && x.vy < 50));
    assert.equal(top, -1, `the pane showed the top of its history ${say} (frame ${top} of ${f.length}: ${JSON.stringify(f[top])})`);
    assert.ok(f.every((x) => x.same), `the xterm was made again ${say}`);
    return f;
  };
  const atBottom = async (say) => {
    const f = await looked(say), v = await view(page);
    assert.ok(!f.at(-1).held && v.vy === v.by, `the pane is not on its bottom ${say}: ${JSON.stringify(v)}`);
    // ...and it FOLLOWED: the live lines kept arriving and the viewport went down with them
    const shown = f.filter((x) => !x.held);
    assert.ok(shown.at(-1).n > shown[0].n, `the pane did not follow the live output ${say}: ${JSON.stringify([shown[0], shown.at(-1)])}\n${(await rows(page)).slice(-300)}`);
  };

  // THE PAGE SPLITTING: the agent's column narrowed by the layout - as Close out opening beside a live agent over its draft does (TaskPage
  // autoPair) - with the window untouched
  const split = async (on) => {
    const before = await page.$eval("[data-tq-task-page] .xterm", (e) => e.getBoundingClientRect().width);
    await page.$eval("[data-tq-term-box]", (e, on) => { e.style.maxWidth = on ? "55%" : ""; }, on);
    await page.waitForFunction((w0) => Math.abs((document.querySelector("[data-tq-task-page] .xterm")?.getBoundingClientRect().width || w0) - w0) > 100,
      { timeout: 10000 }, before).catch(() => assert.fail("the agent's column did not change width"));
  };
  await watch(page); await split(true); await atBottom("with the page split beside it");
  await watch(page); await split(false); await atBottom("with the split closed again");
  // ...AND THE WINDOW MADE NARROWER, a real resize
  await watch(page); await page.setViewport({ width: 1280, height: 900 }); await atBottom("after the window narrowed");

  // READING HIGHER UP: the wheel takes the owner up the history, and the agent goes on working
  const box = await page.$eval("[data-tq-task-page] .xterm", (e) => { const r = e.getBoundingClientRect(); return { x: r.x + r.width / 2, y: r.y + r.height / 2 }; });
  await page.mouse.move(box.x, box.y);
  for (let i = 0; i < 20; i++) { await page.mouse.wheel({ deltaY: -400 }); await sleep(60); }
  await sleep(400);
  const up = await view(page);
  assert.ok(up.by - up.vy > 60, `the wheel did not take the pane up its history: ${JSON.stringify(up)}`);
  const stays = async (say, still) => {
    const f = await looked(say), v = await view(page);
    assert.ok(v.by - v.vy > 40, `the pane went back to its bottom under the owner ${say}: ${JSON.stringify(v)}`);
    if (still) {
      const moved = f.find((x) => !x.held && x.first !== up.first);
      assert.equal(moved, undefined, `the pane moved under the owner ${say}: from "${up.first}" to ${JSON.stringify(moved)}`);
    }
    return v;
  };
  // ...new output and the page's polls, seconds of them: the same line stays at the top of the pane
  await watch(page); await stays("while the agent kept printing", true);
  // ...and the page splitting under them: the reprint clears the history, the pane comes back the same way up from the bottom
  const pre = await view(page);
  await watch(page); await split(true);
  const after = await stays("with the page split under the owner reading", false);
  // ...give or take the lines the agent printed meanwhile (one each 0.4 s)
  assert.ok(Math.abs((after.by - after.vy) - (pre.by - pre.vy)) < 20, `the pane did not come back where the owner was: ${JSON.stringify({ pre, after })}`);

  // BACK AT THE BOTTOM, it follows again
  const narrowed = await page.$eval("[data-tq-task-page] .xterm", (e) => { const r = e.getBoundingClientRect(); return { x: r.x + r.width / 2, y: r.y + r.height / 2 }; });
  await page.mouse.move(narrowed.x, narrowed.y);
  for (let i = 0; i < 40 && await view(page).then((v) => v.vy < v.by); i++) { await page.mouse.wheel({ deltaY: 400 }); await sleep(60); }
  const down = await view(page);
  assert.equal(down.vy, down.by, `the wheel did not bring the pane back to its bottom: ${JSON.stringify(down)}`);
  await watch(page); await atBottom("once the owner scrolled back down");
  assert.deepEqual(errors, []);
});
