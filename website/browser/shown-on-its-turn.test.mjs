import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { chmod, mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { startHarness } from "./harness.mjs";
import { note, record } from "./recorder.mjs";

/* A PAGE BELONGS TO THE TURN THAT MADE IT, WHATEVER THAT TURN'S END, IN BOTH KINDS OF CHAT. The stand-in shows a page (the `show` tool, through
   the MCP door as a real agent calls it) in a turn that answers, and another in a turn the owner stops; then he writes again. Each page must
   stand under the line that asked for it - never carried onto the next turn's answer, never missing from a coding chat. Invented people only. */
const here = path.dirname(fileURLToPath(import.meta.url)), repo = path.resolve(here, "..", "..");
const out = path.join(process.env.TEMP || os.tmpdir(), "claude", "n17", "video", process.env.N17_NAME || "shown-on-its-turn");
const show = (name) => ({ path: "/api/mcp?task={task}", body: { jsonrpc: "2.0", id: 1, method: "tools/call", params: { name: "show", arguments: { files: [name] } } } });

test("a page the agent showed stays on the turn that made it, in a general and a coding chat", { timeout: 600000 }, async (t) => {
  await mkdir(out, { recursive: true });
  const bin = await mkdtemp(path.join(os.tmpdir(), "taskuary-fake-claude-"));
  t.after(() => rm(bin, { recursive: true, force: true }).catch(() => {}));
  const win = process.platform === "win32";
  const py = execFileSync(win ? "python" : "python3", ["-c", "import sys; print(sys.executable)"], { encoding: "utf8" }).trim();
  await writeFile(path.join(bin, win ? "claude.cmd" : "claude"), win ? `@${py} ${path.join(repo, "tests", "fake_claude.py")} %*\r\n` : `#!/bin/sh\nexec "${py}" "${path.join(repo, "tests", "fake_claude.py")}" "$@"\n`);
  if (!win) await chmod(path.join(bin, "claude"), 0o755);
  const h0 = { home: "" }, file = (n) => path.join(h0.home, "scratch", n);
  Object.assign(process.env, { FAKE_CLAUDE_SCRIPT: path.join(bin, "script.json"), FAKE_ACP_SCRIPT: path.join(bin, "script.json"), FAKE_CLAUDE_SPAWN: "1", FAKE_ACP_SPAWN: "1",
    FAKE_CLAUDE_THINK: "1", FAKE_ACP_THINK: "1" });
  const h = await startHarness({ fresh: true, bin });
  t.after(() => h.close());
  h0.home = h.home;
  await mkdir(path.join(h.home, "scratch"), { recursive: true });
  for (const k of ["general", "coding"]) for (const n of ["chart", "draft"])
    await writeFile(file(`${n}-${k}.html`), `<!doctype html><title>${n}</title><h1>The ${n} for Northwind (${k})</h1>`);
  await writeFile(path.join(bin, "script.json"), JSON.stringify(["general", "coding"].flatMap((k) => [
    { when: `show me the chart ${k}`, anywhere: true, first: "Here is the chart.", post: [show(file(`chart-${k}.html`))] },
    { when: `start the draft ${k}`, anywhere: true, first: "Draft done.", post: [show(file(`draft-${k}.html`))], wait: 40 }]).concat(
    [{ when: "back again", anywhere: true, first: "Back - nothing changed." }])));
  const api = (p, body) => fetch(`${h.fixtureApi}${p}`, { method: body ? "POST" : "GET",
    headers: { "Content-Type": "application/json", "X-Taskuary-Token": h.token }, body: body && JSON.stringify(body) }).then((r) => r.json());
  await api("/api/setup/first-run/ai", { name: "claude" });
  await api("/api/setup/dismiss", { dismissed: true });
  const git = execFileSync(win ? "where" : "which", ["git"], { encoding: "utf8" }).trim().split(/\s*\n/)[0].trim();
  assert.ok((await api("/api/fixture/coding", { git })).taskId, "the coding home is set up");
  const kinds = (process.env.N17_KINDS || "general,coding").split(","), seen = {}, errors = [];
  for (const k of kinds) {
    const task = await api("/api/fixture/mail-task", { kind: k }), p = await h.newPage();
    await p.setViewport({ width: 1280, height: 900 });
    p.on("pageerror", (e) => errors.push(`${k}: ${e.message}`));
    await p.goto(h.ui, { waitUntil: "domcontentloaded" });
    await p.evaluate((id) => { location.hash = `task=${id}`; }, task.taskId);
    await p.waitForSelector("[data-tq-task-page] .tq-aui-input", { visible: true, timeout: 60000 });
    const rec = await record(p, path.join(out, k));
    const typeIn = async (words) => {
      await p.waitForFunction(() => { const b = document.querySelector("[data-tq-task-page] .tq-aui-input"); return b && !b.disabled; }, { timeout: 60000 });
      await p.evaluate(() => document.querySelector("[data-tq-task-page] .tq-aui-input").focus());
      await p.keyboard.type(words); await p.keyboard.press("Enter"); };
    const until = (re, timeout = 60000) => p.waitForFunction((src) => new RegExp(src).test(document.querySelector("[data-tq-task-page] .tq-aui-viewport")?.innerText || ""),
      { timeout, polling: 100 }, re.source);
    const quiet = () => p.waitForFunction(() => !document.querySelector("[data-tq-task-page] [data-tq-stop-run]"), { timeout: 90000, polling: 100 });
    // ...where each page stands: the owner's line it stands under, read down the chat
    const where = () => p.evaluate((k) => {
      const vp = document.querySelector("[data-tq-task-page] .tq-aui-viewport"), at = {};
      let line = "(none)";
      const walk = (e) => { if (e.matches?.(".tq-aui-user")) line = (e.querySelector(".tq-aui-user-bubble")?.innerText || "").trim();
        for (const n of ["chart", "draft"]) if (e.childElementCount === 0 && (e.innerText || "").includes(`${n}-${k}.html`) && !at[n]) at[n] = line;
        for (const c of e.children) walk(c); };
      if (vp) walk(vp);
      at.rows = vp ? [...vp.querySelectorAll(".tq-aui-message")].map((e) => `${e.className.replace(/tq-aui-/g, "")}${e.getBoundingClientRect().height ? "" : " HIDDEN"} :: ${(e.innerText || "").replace(/\s+/g, " ").slice(0, 70)}`) : [];
      return at;
    }, k);
    try {
      await typeIn(`show me the chart ${k}`); await until(/Here is the chart/); await quiet(); await new Promise((r) => setTimeout(r, 2500));
      await p.screenshot({ path: path.join(out, `${k}-1-chart.png`) });
      await typeIn(`start the draft ${k}`); await new Promise((r) => setTimeout(r, 6000));
      await p.screenshot({ path: path.join(out, `${k}-2-working.png`) });
      await p.evaluate(() => document.querySelector("[data-tq-task-page] [data-tq-stop-run]")?.click()); await quiet(); await new Promise((r) => setTimeout(r, 2500));
      await p.screenshot({ path: path.join(out, `${k}-3-stopped.png`) });
      await typeIn("back again"); await until(/Back - nothing changed/); await quiet(); await new Promise((r) => setTimeout(r, 3000));
      await p.screenshot({ path: path.join(out, `${k}-4-after.png`) });
      seen[k] = await where();
      // ...and what the server said of it, to tell a placement from a drawing
      await writeFile(path.join(out, `${k}-payload.json`), JSON.stringify(await api(k === "coding" ? `/api/tasks/${task.taskId}/coding-chat` : `/api/tasks/${task.taskId}/assistant`), null, 1));
      await p.reload({ waitUntil: "domcontentloaded" }); await until(/Back - nothing changed/); await new Promise((r) => setTimeout(r, 3000));
      await p.screenshot({ path: path.join(out, `${k}-5-reloaded.png`) });
      seen[`${k} reloaded`] = await where();
    } finally { await rec.stop({ sheet: 0 }); }
  }
  await writeFile(path.join(out, "server.log"), h.backend.output());
  await writeFile(path.join(out, "seen.json"), JSON.stringify(seen, null, 1));
  const want = (k) => ({ chart: `show me the chart ${k}`, draft: `start the draft ${k}` });
  const bad = Object.entries(seen).filter(([k, { rows, ...at }]) => JSON.stringify(at) !== JSON.stringify(want(k.split(" ")[0])));
  await note(out, { done: "Each kind: a page shown in a turn that answered, another in a turn the owner stopped, then a new line answered; read again after a reload.",
    expect: "Each page under the line that asked for it, in both kinds.", saw: JSON.stringify(seen), verdict: bad.length ? "FAIL" : "PASS" });
  assert.deepEqual(errors, []);
  assert.deepEqual(bad, []);
});
