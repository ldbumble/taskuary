import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { chmod, mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { startHarness } from "./harness.mjs";
import { note, record } from "./recorder.mjs";

/* THE GENERAL CHAT AND THE CODING CHAT, SIDE BY SIDE AT EVERY STATE (the owner, 2026-11-10: "coding and general use the same code when it comes
   to interactions so there should be no difference"). One world, two tasks from the same mail - one on the stand-in claude (general), one on the
   stand-in ACP adapter (coding) - both answering the same script. Each state is driven on both at once and shot at the same moments after the
   press; the sheet lays each state's two frames next to each other, and states.json keeps what each chat's foot held, row by row, for the table.
   An audit, not a gate: it fails only when a state cannot be reached. Invented people only. */
const here = path.dirname(fileURLToPath(import.meta.url)), repo = path.resolve(here, "..", "..");
const out = path.join(process.env.TEMP || os.tmpdir(), "claude", "n17", "video", process.env.N17_NAME || "side-by-side");
const propose = (slug, why) => ({ path: "/api/agent/propose", body: { action: "write_playbook", slug, text: `# ${slug}\nwhen: a vendor tool is to be reviewed\n\nRead the export first.`, why } });
const SCRIPT = [{ when: "pressed .* went through", anywhere: true, first: "Saved - the next vendor review follows it." },
  { when: "and the prices too", anywhere: true, first: "Prices: Payworth 4 a head, Trainly 6." },
  { when: "start on the vendors", anywhere: true, first: "Read the vendor list: three vendors.", wait: 5 },
  { when: "ask me first", anywhere: true, first: "Read the list.\n\n[[TASKUARY-ASK]] Should the setup fee count in the price?" },
  { when: "yes count it", anywhere: true, first: "Counted the setup fee in." },
  // ...a playbook of its own for each chat: two pending for one name, the second is refused (proposals.queue)
  ...["general", "coding"].flatMap((k) => [{ when: `keep how we review ${k}`, anywhere: true, first: "Set it up as a playbook - press Approve and I file it.", post: [propose(`vendor-review-${k}`, "so the next review goes the same way")] },
    { when: `one more playbook ${k}`, anywhere: true, first: "Set up one more - press Approve and I file it.", post: [propose(`vendor-intake-${k}`, "so intake goes the same way")] }]),
  { when: "draft erin an answer", anywhere: true, first: "Drafted her an answer.", post: [{ path: "/api/agent/reply", body: { text: "Hi Erin, here is the long review of the tool. Alex", agent: "assistant" } }] },
  { when: "make it shorter", anywhere: true, first: "Shorter now.", post: [{ path: "/api/agent/reply", body: { text: "Hi Erin, two flaws. Alex", agent: "assistant" } }] },
  { when: "take your time", anywhere: true, first: "Took my time.", wait: 40 },
  { when: "break now", anywhere: true, exit: 3 },
  { when: "back again", anywhere: true, first: "Back - nothing changed." }];

async function world(t) {
  const bin = await mkdtemp(path.join(os.tmpdir(), "taskuary-fake-claude-"));
  t.after(() => rm(bin, { recursive: true, force: true }).catch(() => {}));
  const win = process.platform === "win32";
  const py = execFileSync(win ? "python" : "python3", ["-c", "import sys; print(sys.executable)"], { encoding: "utf8" }).trim();
  await writeFile(path.join(bin, win ? "claude.cmd" : "claude"), win ? `@${py} ${path.join(repo, "tests", "fake_claude.py")} %*\r\n` : `#!/bin/sh\nexec "${py}" "${path.join(repo, "tests", "fake_claude.py")}" "$@"\n`);
  if (!win) await chmod(path.join(bin, "claude"), 0o755);
  await writeFile(path.join(bin, "script.json"), JSON.stringify(SCRIPT));
  // ...the same pace on both: a start of a second, a think of two
  Object.assign(process.env, { FAKE_CLAUDE_SCRIPT: path.join(bin, "script.json"), FAKE_ACP_SCRIPT: path.join(bin, "script.json"), FAKE_CLAUDE_SPAWN: "1", FAKE_ACP_SPAWN: "1",
    FAKE_CLAUDE_THINK: "2", FAKE_ACP_THINK: "2" });
  const h = await startHarness({ fresh: true, bin });
  t.after(() => h.close());
  const api = (p, body) => fetch(`${h.fixtureApi}${p}`, { method: body ? "POST" : "GET",
    headers: { "Content-Type": "application/json", "X-Taskuary-Token": h.token }, body: body && JSON.stringify(body) }).then((r) => r.json());
  await api("/api/setup/first-run/ai", { name: "claude" });
  await api("/api/setup/dismiss", { dismissed: true });
  return { ...h, api };
}

// WHAT THE CHAT HOLDS, row by row from the foot up: each row's marks, its words, and what is greyed, spinning or pressable in it
const foot = (page) => page.evaluate(() => {
  const vp = document.querySelector("[data-tq-task-page] .tq-aui-viewport");
  if (!vp) return { rows: [], box: "no chat" };
  const grey = (e) => { for (let x = e, i = 0; x && x !== vp && i < 8; x = x.parentElement, i++) if (+getComputedStyle(x).opacity < 0.9) return true; return false; };
  const rows = [...vp.children].filter((e) => e.getBoundingClientRect().height > 0).slice(-7).map((e) => {
    const cls = `${e.className}`.split(" ").filter((c) => c.startsWith("tq-")).join(".");
    const flags = [e.querySelector("[data-tq-run-clock]") && `head[${e.querySelector("[data-tq-run-clock]").innerText.replace(/\s+/g, " ").trim()}]`,
      e.querySelector("[data-tq-stop-run]") && "x", e.querySelector(".tq-aui-thinking") && "spin", e.matches("[data-tq-pending-turn]") || e.querySelector("[data-tq-pending-turn]") ? "pending" : "",
      e.querySelector("[data-tq-asking]") && "asking", grey(e) && "GREY", ...[...e.querySelectorAll("button")].filter((b) => b.innerText.trim()).map((b) => `[${b.innerText.trim().slice(0, 18)}${b.disabled ? " off" : ""}]`)].filter(Boolean);
    return `${cls || e.tagName.toLowerCase()} ${flags.join(" ")} :: ${(e.innerText || "").replace(/\s+/g, " ").trim().slice(0, 140)}`;
  });
  const input = document.querySelector("[data-tq-task-page] .tq-aui-input");
  const bar = [...document.querySelectorAll("[data-tq-task-page] button")].filter((b) => b.getBoundingClientRect().width > 0 && !vp.contains(b)).map((b) => (b.innerText || b.getAttribute("aria-label") || "").trim().slice(0, 18)).filter(Boolean);
  return { rows, box: input ? (input.disabled ? "box off" : `box "${input.placeholder || ""}"`) : "no box", buttons: [...new Set(bar)].join(" | ") };
});

test("the general chat and the coding chat, side by side at every state", { timeout: 1500000 }, async (t) => {
  await mkdir(out, { recursive: true });
  const w = await world(t), git = execFileSync(process.platform === "win32" ? "where" : "which", ["git"], { encoding: "utf8" }).trim().split(/\s*\n/)[0].trim();
  assert.ok((await w.api("/api/fixture/coding", { git })).taskId, "the coding home is set up");
  const tasks = { general: await w.api("/api/fixture/mail-task", { kind: "general" }), coding: await w.api("/api/fixture/mail-task", { kind: "coding" }) };
  const kinds = Object.keys(tasks), pages = {}, recs = {}, errors = [], states = [];
  for (const k of kinds) {
    const p = pages[k] = await w.newPage();
    await p.setViewport({ width: 1280, height: 900 });
    p.on("pageerror", (e) => errors.push(`${k}: ${e.message}`));
    // ...the tab at the back reads hidden, and a hidden page reads no live news (live.onLive): its RAIL and the cards a reload brings stand
    // stale there - compare those by states.json's `rail` (the server's own pile), never by that frame. Made visible both, the two tabs
    // followed the one walk onto one task (sbs-run4)
    await p.goto(w.ui, { waitUntil: "domcontentloaded" });
    await p.evaluate((id) => { location.hash = `task=${id}`; }, tasks[k].taskId);
    await p.waitForSelector("[data-tq-task-page] .tq-aui-input", { visible: true, timeout: 60000 });
    recs[k] = await record(p, path.join(out, `rec-${k}`));
  }
  const both = (f) => Promise.all(kinds.map((k) => f(pages[k], k)));
  // ...a frame of each at the same moment, and what each foot held
  const shoot = async (state, label) => {
    const s = { state, label, at: {} };
    await both(async (p, k) => { const f = `${state}-${label}-${k}.png`.replace(/[^\w.-]+/g, "_"); await p.screenshot({ path: path.join(out, f) }); s.at[k] = { file: f, ...(await foot(p)) }; });
    // ...and what the rail says of each task then: one reading of the state, whatever agent works it
    const pile = await w.api("/api/funnel/pile").catch(() => ({}));
    for (const k of kinds) { const i = (pile.items || []).find((x) => x.tid === tasks[k].taskId); s.at[k].rail = i ? `${i.lane}/${i.kind}${i.chat ? " chat" : ""} · ${i.why || ""}` : "no row"; }
    states.push(s);
  };
  const shots = async (state, marks) => { const t0 = Date.now(); for (const [label, ms] of marks) { const d = ms - (Date.now() - t0); if (d > 0) await new Promise((r) => setTimeout(r, d)); await shoot(state, label); } };
  const typeIn = (words) => both(async (p, k) => {
    await p.waitForFunction(() => { const b = document.querySelector("[data-tq-task-page] .tq-aui-input"); return b && !b.disabled; }, { timeout: 60000 });
    await p.evaluate(() => document.querySelector("[data-tq-task-page] .tq-aui-input").focus());
    await p.keyboard.type(typeof words === "function" ? words(k) : words); await p.keyboard.press("Enter"); });
  const until = (re, timeout = 60000) => both((p, k) => p.waitForFunction((src) => new RegExp(src).test(document.querySelector("[data-tq-task-page] .tq-aui-viewport")?.innerText || ""),
    { timeout, polling: 100 }, re.source).catch(() => { throw new Error(`${k}: no ${re} within ${timeout} ms`); }));
  const press = (re) => both(async (p, k) => {
    const ok = await p.waitForFunction((src) => { const b = [...document.querySelectorAll("[data-tq-task-page] button, .MuiPopover-root button")].filter((b) => new RegExp(src).test(b.innerText.trim()) && !b.disabled && b.getBoundingClientRect().width > 0).pop();
      if (b) b.click(); return !!b; }, { timeout: 30000, polling: 100 }, re.source).catch(() => null);
    if (!ok) throw new Error(`${k}: no ${re} to press: ${(await foot(p)).buttons} ${JSON.stringify(await p.evaluate(async (id) => {
      const d = await (await fetch(`/api/tasks/${id}/assistant`, { headers: { "X-Taskuary-Token": localStorage.getItem("taskuary_token") } })).json();
      return { turns: d.turns, drafts: (d.playbookDrafts || []).map((r) => [r.ReviewId, r.Status]), cards: (d.cards || []).length, ids: (d.messages || []).map((m) => m.id).slice(-6) };
    }, tasks[k].taskId)).slice(0, 900)}`); });
  const quiet = () => both((p) => p.waitForFunction(() => !document.querySelector("[data-tq-task-page] [data-tq-stop-run]"), { timeout: 90000, polling: 100 }));
  const step = async (name, f) => { try { await f(); } catch (e) { states.push({ state: name, failed: e.message.slice(0, 400) }); await shoot(name, "failed").catch(() => {}); } };

  try {
    await shoot("0-arrived", "rest");
    await step("1-start", async () => { await typeIn("start on the vendors"); await shots("1-start", [["0.3s", 300], ["1.5s", 1500], ["4s", 4000]]); });
    await step("2-midturn", async () => { await typeIn("and the prices too"); await shots("2-midturn", [["0.3s", 300], ["2s", 2000]]);
      await until(/Prices: Payworth/, 90000); await new Promise((r) => setTimeout(r, 1500)); await shoot("2-midturn", "rest"); });
    await quiet();
    await step("3-asked", async () => { await typeIn("ask me first"); await until(/setup fee count/); await new Promise((r) => setTimeout(r, 1500)); await shoot("3-asked", "rest");
      await typeIn("yes count it"); await shots("3-answered", [["0.3s", 300]]); await until(/Counted the setup fee/); await new Promise((r) => setTimeout(r, 1500)); await shoot("3-answered", "rest"); });
    await step("4-card", async () => { await typeIn((k) => `keep how we review ${k}`); await until(/press Approve and I file it/); await new Promise((r) => setTimeout(r, 2000)); await shoot("4-card", "waiting");
      await press(/^Approve/); await shots("5-approved", [["0.3s", 300], ["2s", 2000]]); await until(/Saved - the next vendor review/); await new Promise((r) => setTimeout(r, 1500)); await shoot("5-approved", "rest"); });
    await step("6-dismissed", async () => { await typeIn((k) => `one more playbook ${k}`); await until(/Set up one more/); await new Promise((r) => setTimeout(r, 2000));
      await press(/^Dismiss/); await shots("6-dismissed", [["0.3s", 300], ["3s", 3000]]); });
    await quiet();
    await step("7-replaced", async () => { await typeIn("draft erin an answer"); await until(/Drafted her an answer/); await new Promise((r) => setTimeout(r, 1500)); await shoot("7-replaced", "first card");
      await typeIn("make it shorter"); await shots("7-replaced", [["0.3s", 300]]); await until(/Shorter now/); await new Promise((r) => setTimeout(r, 2000)); await shoot("7-replaced", "rest"); });
    await quiet();
    await step("8-stopped", async () => { await typeIn("take your time"); await new Promise((r) => setTimeout(r, 5000)); await shoot("8-stopped", "working");
      await both((p) => p.evaluate(() => document.querySelector("[data-tq-task-page] [data-tq-stop-run]")?.click())); await shots("8-stopped", [["0.3s", 300], ["3s", 3000]]); });
    await quiet();
    await step("9-idled", async () => { await quiet().catch(() => {});
      for (const k of kinds) states.push({ state: "9-idled", label: `fixture ${k}`, note: JSON.stringify(await w.api("/api/fixture/session", { taskId: tasks[k].taskId, state: "idled" })) });
      await new Promise((r) => setTimeout(r, 3000)); await shoot("9-idled", "idle");
      await typeIn("back again"); await shots("9-idled", [["0.3s", 300], ["1.5s", 1500]]); await until(/Back - nothing changed/); await new Promise((r) => setTimeout(r, 1500)); await shoot("9-idled", "rest"); });
    await quiet().catch(() => {});
    await step("10-failed", async () => { await typeIn("break now"); await shots("10-failed", [["1s", 1000], ["6s", 6000], ["15s", 15000]]); });
    await quiet().catch(() => {});
    await step("11-remind", async () => { await press(/^Remind me/); await new Promise((r) => setTimeout(r, 800)); await shoot("11-remind", "menu");
      await press(/^Tomorrow/); await shots("11-remind", [["0.3s", 300], ["2s", 2000]]); });
    await step("12-done", async () => { await both((p, k) => p.evaluate((id) => { location.hash = `task=${id}`; }, tasks[k].taskId)); await new Promise((r) => setTimeout(r, 3000)); await shoot("12-done", "back on it");
      await press(/^Mark done/); await shots("12-done", [["0.3s", 300], ["2s", 2000]]); });
  } finally {
    await Promise.all(kinds.map((k) => recs[k].stop({ sheet: 0 })));
    await writeFile(path.join(out, "states.json"), JSON.stringify(states, null, 1));
    await writeFile(path.join(out, "server.log"), w.backend.output());
    // ...the sheet: each state's two frames next to each other, what each foot held under them
    const esc = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;");
    const rows = await Promise.all(states.filter((s) => s.at).map(async (s) => `<tr><th colspan=2>${esc(s.state)} · ${esc(s.label)}</th></tr><tr>${await Promise.all(kinds.map(async (k) =>
      `<td><img src="data:image/png;base64,${(await readFile(path.join(out, s.at[k].file))).toString("base64")}"><pre>${esc(k)} · ${esc(s.at[k].box)} · ${esc(s.at[k].buttons)}\nrail: ${esc(s.at[k].rail)}\n${s.at[k].rows.map(esc).join("\n")}</pre></td>`)).then((x) => x.join(""))}</tr>`));
    const sheet = await pages.general.browser().newPage();
    try {
      await sheet.setViewport({ width: 1800, height: 1000 });
      // ...three states a sheet: one tall page outgrows what a screenshot can hold
      for (let i = 0; i < rows.length; i += 3) {
        await sheet.setContent(`<style>body{font:12px sans-serif;margin:6px}td{vertical-align:top;width:50%}img{width:100%;border:1px solid #bbb}pre{white-space:pre-wrap;font-size:10px;margin:2px}th{text-align:left;background:#eee;padding:4px}</style><table><tr><th>general</th><th>coding</th></tr>${rows.slice(i, i + 3).join("")}</table>`);
        await sheet.screenshot({ path: path.join(out, `sheet-${String(i / 3 + 1).padStart(2, "0")}.png`), fullPage: true });
      }
    } finally { await sheet.close(); }
    const failed = states.filter((s) => s.failed);
    await note(out, { done: "Two tasks from the same mail, one general (stand-in claude), one coding (stand-in ACP), the same script; each state driven on both at once.",
      expect: "The same chat on both, state by state: the same words, the same order, the same greyed card, the same head and spin.",
      saw: failed.length ? failed.map((s) => `${s.state}: ${s.failed}`).join("\n") : "see sheet-*.png and states.json", verdict: failed.length ? "STATES NOT REACHED" : "RECORDED" });
  }
  assert.deepEqual(states.filter((s) => s.failed).map((s) => s.state), []);
  assert.deepEqual(errors, []);
});
