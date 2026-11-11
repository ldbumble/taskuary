import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { chmod, mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { startHarness } from "./harness.mjs";
import { note, record } from "./recorder.mjs";

/* THE WALK OVER A ROW WITH AN AGENT AT WORK AND A STRANGER HELD (the overnight walk, 2026-11-11). Three tasks from mail: one plain, one whose
   agent is at work (a long turn), one from a stranger whose start the AI refused (too old for its reviewer, no read-only mode). Walked by the
   bar's Next and once Back: at every row the bar is navigation only, Next is never held by the working row, the working row's desk shows its
   agent at work, and the held row says why in one sentence with Trust. Recorded; an audit that fails on any of those. Invented people only. */
const here = path.dirname(fileURLToPath(import.meta.url)), repo = path.resolve(here, "..", "..");
const out = path.join(process.env.TEMP || os.tmpdir(), "claude", "n17", "video", process.env.N17_NAME || "walk-rows");
const NAV = /^(Back|Next|All read, next|Walk me through my tasks)$/;

test("the walk over an agent at work and a held stranger: navigation-only bar, Next never held, each desk says what it is", { timeout: 600000 }, async (t) => {
  await mkdir(out, { recursive: true });
  const bin = await mkdtemp(path.join(os.tmpdir(), "taskuary-fake-claude-"));
  t.after(() => rm(bin, { recursive: true, force: true }).catch(() => {}));
  const win = process.platform === "win32";
  const py = execFileSync(win ? "python" : "python3", ["-c", "import sys; print(sys.executable)"], { encoding: "utf8" }).trim();
  await writeFile(path.join(bin, win ? "claude.cmd" : "claude"), win ? `@${py} ${path.join(repo, "tests", "fake_claude.py")} %*\r\n` : `#!/bin/sh\nexec "${py}" "${path.join(repo, "tests", "fake_claude.py")}" "$@"\n`);
  if (!win) await chmod(path.join(bin, "claude"), 0o755);
  await writeFile(path.join(bin, "script.json"), JSON.stringify([{ when: "Budget sheet", anywhere: true, first: "Budget checked.", wait: 90 }]));
  Object.assign(process.env, { FAKE_CLAUDE_SCRIPT: path.join(bin, "script.json"), FAKE_CLAUDE_SPAWN: "0.5", FAKE_CLAUDE_THINK: "1", FAKE_CLAUDE_VERSION: "2.1.100" });
  t.after(() => { delete process.env.FAKE_CLAUDE_VERSION; });
  const h = await startHarness({ fresh: true, bin });
  t.after(() => h.close());
  const api = (p, body) => fetch(`${h.fixtureApi}${p}`, { method: body ? "POST" : "GET",
    headers: { "Content-Type": "application/json", "X-Taskuary-Token": h.token }, body: body && JSON.stringify(body) }).then((r) => r.json());
  await api("/api/setup/first-run/ai", { name: "claude" });
  await api("/api/setup/dismiss", { dismissed: true });
  assert.ok((await api("/api/fixture/no-readonly", {})).ok);
  const plain = await api("/api/fixture/mail-task", { sent: "2026-11-10 08:00:00" });
  const busy = await api("/api/fixture/mail-task", { title: "Budget sheet for Ray", sent: "2026-11-10 08:05:00" });
  const held = await api("/api/fixture/mail-task", { stranger: true, title: "Quote from Paula", sent: "2026-11-10 08:10:00" });
  const page = await h.newPage(), errors = [], bad = [], steps = [];
  await page.setViewport({ width: 1600, height: 900 });
  page.on("pageerror", (e) => errors.push(e.message));
  const titles = { [plain.taskId]: "plain", [busy.taskId]: "agent at work", [held.taskId]: "held stranger" };
  await page.goto(h.ui, { waitUntil: "domcontentloaded" });
  // ...the stranger's start refused first: his line on its task, the hold said under it
  await page.evaluate((id) => { location.hash = `task=${id}`; }, held.taskId);
  await page.waitForSelector("[data-tq-task-page] .tq-aui-input", { visible: true, timeout: 60000 });
  const rec = await record(page, out);
  try {
    await page.evaluate(() => document.querySelector("[data-tq-task-page] .tq-aui-input")?.focus());
    await page.keyboard.type("send her our price list"); await page.keyboard.press("Enter");
    await page.waitForFunction(() => [...document.querySelectorAll("[data-tq-task-page] button")].some((b) => /^Trust/.test(b.innerText.trim())), { timeout: 60000 })
      .catch(() => bad.push("the stranger's hold never offered Trust"));
    // ...and the busy task's agent set to work (a long turn)
    await api("/api/fixture/general/start", { taskId: busy.taskId });
    await new Promise((r) => setTimeout(r, 6000));
    // ...then walked from the held row by the bar: up to the top, and down to the end
    const read = () => page.evaluate(() => {
      const tp = document.querySelector("[data-tq-task-page]"), id = /task=(\d+)/.exec(location.hash)?.[1] || "";
      const bar = [...document.querySelectorAll("[data-tq-row] button")].filter((b) => b.getBoundingClientRect().width > 0 && getComputedStyle(b).visibility !== "hidden").map((b) => ({ text: b.innerText.trim(), off: b.disabled }));
      return { id, bar, trust: !!tp && [...tp.querySelectorAll("button")].some((b) => /^Trust/.test(b.innerText.trim()) && b.getBoundingClientRect().width > 0),
        clock: !!tp?.querySelector("[data-tq-run-clock]"), chip: (tp?.querySelector(".MuiChip-label")?.innerText || "").trim(),
        desk: (tp?.querySelector(".tq-aui-viewport")?.innerText || document.querySelector(".tq-asst-col")?.innerText || "").replace(/\s+/g, " ").slice(-260) };
    });
    let s = null;
    const moves = ["Back", "Back", "Next", "Next", "Next"];
    for (let n = 0; n <= moves.length; n++) {
      await new Promise((r) => setTimeout(r, 2500));
      s = await read();
      const kind = titles[s.id] || (s.id ? "other" : "no task");
      steps.push({ n, kind, ...s, bar: s.bar.map((b) => b.text + (b.off ? " (off)" : "")).join(" | ") });
      await page.screenshot({ path: path.join(out, `${n}-${kind.replace(/\W+/g, "-")}.png`) });
      const stray = s.bar.filter((b) => !NAV.test(b.text));
      if (stray.length) bad.push(`${n} ${kind}: the bar holds more than navigation: ${stray.map((b) => b.text).join(", ")}`);
      if (kind === "agent at work" && !s.clock && !/working/i.test(s.chip)) bad.push(`${n}: the working row's desk shows no agent at work (${s.chip})`);
      if (kind === "held stranger" && !s.trust) bad.push(`${n}: the held row shows no Trust: ${s.desk}`);
      const want = moves[n]; if (!want) break;
      const go = s.bar.find((b) => b.text === want || (want === "Next" && /^(Next|All read, next)$/.test(b.text)));
      if (!go) { if (want === "Next") bad.push(`${n} ${kind}: no Next on the bar`); break; }
      if (go.off) { await new Promise((r) => setTimeout(r, 3000)); if ((await read()).bar.some((b) => b.text === go.text && b.off)) bad.push(`${n} ${kind}: ${go.text} held greyed`); }
      await page.evaluate((t) => [...document.querySelectorAll("[data-tq-row] button")].find((x) => x.innerText.trim() === t && !x.disabled)?.click(), go.text);
    }
  } finally {
    await rec.stop();
    await writeFile(path.join(out, "steps.json"), JSON.stringify(steps, null, 1));
    await writeFile(path.join(out, "server.log"), h.backend.output());
    const kinds = new Set(steps.map((x) => x.kind));
    for (const k of ["agent at work", "held stranger"]) if (!kinds.has(k)) bad.push(`the walk never stood on the ${k} row`);
    await note(out, { done: "Three mail tasks - plain, an agent at work, a stranger whose start was refused - walked by Next, Back once from the held row.",
      expect: "The bar navigation only; Next never held; the working row shows its agent at work; the held row its one sentence with Trust.",
      saw: bad.length ? bad.join("\n") : `as expected: ${steps.map((x) => x.kind).join(" > ")}`, verdict: bad.length ? "FAIL" : "PASS" });
  }
  assert.deepEqual(bad, []);
  assert.deepEqual(errors, []);
});
