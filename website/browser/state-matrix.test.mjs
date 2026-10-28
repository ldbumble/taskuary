import assert from "node:assert/strict";
import test from "node:test";
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { startHarness } from "./harness.mjs";

/* NO STATE SHOWS THE WRONG THING (the owner, 2026-10-28: a stopped agent showed its whole chat and input box instead of its result, and a
   reply owed opened on Close out instead of Came from). Every state a task or rail item can be in, against what the page draws for it, at a
   desk and a phone: the section it opens on, what that section holds, the tabs and their "Up to here", the dock row and its lit move, the
   Advisor line, no "Loading..." left standing, no page error, and nothing moved between the first paint and four seconds on. One run lists
   every cell that fails. The demo world plus the fixture's states (fixture_changes MATRIX); invented people only.
   TQ_MATRIX_SHOTS=<dir> saves a screenshot of each cell; TQ_MATRIX_DUMP=<file> writes what each cell drew there, as JSON. */
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const SHOTS = process.env.TQ_MATRIX_SHOTS, DUMP = process.env.TQ_MATRIX_DUMP;

// what the open card draws, as one value
const look = (page, id) => page.evaluate((id) => {
  const vis = (e) => !!e && e.getBoundingClientRect().width > 0 && e.getBoundingClientRect().height > 0 && getComputedStyle(e).visibility !== "hidden";
  const txt = (e) => (e?.innerText || "").replace(/\s+/g, " ").trim();
  const items = [...document.querySelectorAll(id ? "[data-tq-canvas-item]" : ".tq-canvas-live [data-tq-canvas-item], .tq-msg.tq-live-card")]
    .filter((x) => vis(x) && !x.closest("[data-tq-folded]"));
  const item = id ? items.find((x) => x.querySelector(`[data-tq-task-page="${id}"]`)) : items.pop();
  const body = item?.querySelector("[data-tq-task-body]");
  const open = item?.querySelector("[data-tq-slot][data-tq-open]");
  const row = document.querySelector("[data-tq-row]");
  const btns = [...(row?.querySelectorAll(".tq-arow-verbs button") || [])].filter(vis)
    .map((b) => ({ id: b.dataset.tqVerb || (b.hasAttribute("data-tq-next") ? "next" : b.hasAttribute("data-tq-back") ? "back" : b.className),
      label: b.textContent.trim(), lit: b.classList.contains("p"), off: b.disabled, more: b.classList.contains("tq-cl-more") }));
  const agent = item?.querySelector("[data-tq-agent-section]");
  return {
    found: !!item, task: !!item?.querySelector("[data-tq-task-page]"), main: body?.getAttribute("data-tq-main") || null, stage: body?.getAttribute("data-tq-stage") || null,
    open: open?.getAttribute("data-tq-slot") || null, openText: txt(open || body || item).slice(0, 700),
    tabs: [...(item?.querySelectorAll("[data-tq-section-tab]") || [])].map((t) => ({ key: t.dataset.tqSectionTab, here: t.hasAttribute("data-tq-here"),
      foot: txt(t.querySelector("[data-tq-tab-status]")), text: txt(t) })),
    row: btns, rowWhy: txt(row?.querySelector("[data-tq-row-why]")),
    advisor: txt(item?.querySelector("[data-tq-advisor-line]")) || [...(item?.querySelectorAll("[data-tq-tab-status]") || [])].map(txt).find((x) => /Advisor:/.test(x)) || "",
    loading: /Loading…|Loading\.\.\./.test(txt(item)),
    result: vis(item?.querySelector("[data-tq-result-summary]")), fullOpen: item?.querySelector("[data-tq-full-result]")?.getAttribute("aria-expanded") === "true",
    chat: [...(item?.querySelectorAll("[data-tq-agent-room]") || [])].some(vis),
    agentBox: [...(agent?.querySelectorAll("textarea, [contenteditable=true]") || [])].some(vis),
    xterm: vis(item?.querySelector(".xterm-screen")),
    tryAgain: [...(item?.querySelectorAll("button") || [])].some((b) => vis(b) && /^(Try again|Connect an AI)/.test(b.textContent.trim())) || btns.some((b) => /^Try again/.test(b.label)),
    draft: [...(item?.querySelectorAll("[data-tq-closeout] textarea") || [])].some(vis),
    buttons: [...(item?.querySelectorAll("button") || [])].filter(vis).map((b) => b.textContent.trim()).filter(Boolean),
    text: txt(item).slice(0, 20000),
    alert: [...document.querySelectorAll("[role=alert]")].filter(vis).map(txt).join(" | "),
    said: [...document.querySelectorAll(".tq-msg")].map(txt).slice(-3).join(" | "),
  };
}, id);

// ...the parts a state may not change between the first paint and a few seconds on
const held = (s) => JSON.stringify({ main: s.main, open: s.open, stage: s.stage, chat: s.chat });

/* THE MATRIX. The cell is reached by a task id (the hash, as a rail press does) or a rail row by its words. `want`:
   section - the one it opens on (the desk); here: null - no tab says "Up to here" (the open one is where it is up to);
   has / not - words the card shows / the open section never shows; result - the agent's Result summary at rest; chat / agentBox - its
   conversation and input box at rest (a finished or stopped agent shows what it did, never its chat); xterm - a live terminal;
   ran - an agent worked it (its tab never says "not started"; false: nothing ran, so it always does); quiet - no Advisor line (a
   closed task, an agent at work); lit - the dock's lit move by label; moves - labels the row or the card must offer.
   ASK OWNER (2026-10-28), drawn as it is today and pinned so: a failed general run shows its conversation under the reason (the
   reason said twice). A task its agent closed opens on the Agent section - who closed it and why (trust audit S2, 2026-10-28). */
const CELLS = (ids) => [
  ["fresh task", ids.fresh, { section: "from", here: null, ran: false, not: /Loading/ }],
  ["reply owed, nothing drafted", ids.owed, { section: "from", here: null, ran: false }],
  ["draft waiting for Send", ids.draft, { section: "close", ran: false, draft: true, moves: [/^Send/] }],
  ["sent reply", ids.sent, { section: "close", ran: false, has: /Attached - signed this morning/, not: /while its agent is still working/ }],
  ["agent working (general)", ids.working, { section: "agent", ran: true, quiet: true, has: /is working/, result: false, moves: [/Stop/] }],
  ["agent working (coding)", ids.coding_working, { section: "agent", ran: true, quiet: true, xterm: true, moves: [/Stop/] }],
  ["agent waiting on you (asked)", ids.asked, { section: "agent", ran: true, has: /close both cards today/ }],
  ["coding agent waiting at its prompt", ids.blocked, { section: "agent", ran: true, xterm: true }],
  ["agent stopped mid-work", ids.stopped, { section: "agent", ran: true, result: true, chat: false, agentBox: false }],
  ["agent stopped and saved (general)", ids.saved, { section: "agent", ran: true, result: true, chat: false, agentBox: false, has: /Ray Colton signs it/ }],
  ["agent stopped and saved (coding)", ids.coding_saved, { section: "agent", ran: true, result: true, chat: false, agentBox: false, has: /Census sync no longer stops/ }],
  ["agent finished", ids.finished, { section: "agent", ran: true, result: true, chat: false, agentBox: false, has: /Three people are missing/ }],
  ["agent failed", ids.failed, { section: "agent", ran: true, tryAgain: true, agentBox: false, has: /could not start/ }],
  ["agent closed the task", ids.agent_closed, { section: "agent", ran: true, quiet: true, has: /missing secret/ }],
  ["closed by owner (done)", ids.done, { section: "close", ran: false, quiet: true, has: /Mark done/ }],
  ["closed by owner (with a note)", ids.note, { section: "close", ran: false, quiet: true, has: /loose cable/ }],
  ["closed by owner (not a task)", ids.removed, { gone: true }],
  ["waiting on a person", ids.waiting, { section: "from", ran: false, has: /Waiting on Ray/ }],
  ["deferred (Remind me)", ids.deferred, { section: "from", ran: false, has: /PhishGuard seats/ }],
  ["goal with steps", ids.goal, { section: "from", ran: false, has: /Inventory the fields/ }],
  ["to-do list", ids.todo, { section: "from", ran: false, has: /Print the August bank reconciliations/ }],
  ["calendar invite", ids.invite, { section: "from", ran: false, has: /AP cutover dry run/, moves: [/^Accept/] }],
  // ...a rail row, by its words: the first of these still on the rail (an item read at the desk has left it by the phone's pass)
  ["report item", /Headcount by site|AP ageing over 30 days|Helpdesk tickets by day/, { card: true, has: /REPORT/i }],
  ["FYI item", /Regional operations newsletter|Riverside export ran clean|badge printer is back|Statement of account/, { card: true, has: /FYI|read/i }],
  ["FYI batch", /Regional operations newsletter|Riverside export ran clean|badge printer is back|Statement of account/, { card: true, batch: true, lit: /All read/ }],
  ["Advisor idea", /weekly report could send it/, { card: true, has: /AP ageing/ }],
  ["news (sender wrote again after a result)", ids.news, { section: "from", ran: true, has: /Ray is away this week/, not: /record is below/, result: false }],
];

function judge(name, w, a, b, errs, want) {
  const bad = [];
  const say = (m) => bad.push(`${name} @${w}: ${m}`);
  if (!a.found && !b.found && !want.gone) { say("nothing drew"); return bad; }
  if (held(a) !== held(b)) say(`moved after first paint: ${held(a)} -> ${held(b)}`);
  if (b.loading) say(`"Loading..." still standing at 4s`);
  if (/Failed to load|went wrong|error/i.test(b.alert)) say(`an error banner: ${b.alert}`);
  for (const e of errs) say(`page error: ${e}`);
  return bad;
}

function expect(name, w, s, want, desk) {
  const bad = [], say = (m) => bad.push(`${name} @${w}: ${m}`);
  // a removed task (Not a task) is gone: its link draws no task page, and the page says it cannot find it
  if (want.gone) { if (s.found) say(`a removed task drew as a task: ${s.text.slice(0, 160)}`); if (!/can't find|removed|deleted/i.test(s.said)) say(`nothing said about it: ${s.said}`); return bad; }
  if (want.card) {
    if (want.has && !want.has.test(s.text)) say(`card does not show ${want.has}: ${s.text.slice(0, 200)}`);
  } else {
    if (!s.task) { say(`no task page: ${s.text.slice(0, 200)}`); return bad; }
    if (desk && want.section && s.main !== want.section) say(`opens on ${s.main} (stage ${s.stage}), want ${want.section}`);
    if (desk) {
      const here = s.tabs.filter((t) => t.here).map((t) => t.key);
      if (here.length > 1) say(`more than one tab says Up to here: ${here}`);
      if (here.includes(s.main)) say("the open section's own tab says Up to here");
      if ("here" in want && want.here === null && here.length) say(`a tab says Up to here (${here}) though the open section is where it is up to`);
      for (const t of s.tabs) if (!t.text) say(`the ${t.key} tab is blank`);
    }
    const shown = desk ? s.openText : s.text;
    if (want.has && !want.has.test(s.text)) say(`does not show ${want.has}: ${shown.slice(0, 220)}`);
    if (want.not && want.not.test(shown)) say(`shows ${want.not}`);
    if ("result" in want && s.result !== want.result) say(`Result summary ${s.result ? "shown" : "missing"}`);
    if ("chat" in want && !s.fullOpen && s.chat !== want.chat) say(`agent chat ${s.chat ? "shown at rest" : "missing"}`);
    if ("agentBox" in want && !s.fullOpen && s.agentBox !== want.agentBox) say(`agent input box ${s.agentBox ? "shown at rest" : "missing"}`);
    if (want.xterm && !s.xterm) say("no terminal for a live agent");
    if (want.tryAgain && !s.tryAgain) say("a failed run with no Try again");
    if (want.draft && !s.draft) say("no draft box in Close out");
    // THE TABS SAY WHAT THEIR SECTIONS HOLD: an agent that ran is never "not started", one that never ran always is; no raw markers
    const agentTab = s.tabs.find((t) => t.key === "agent")?.text || "";
    if (agentTab && want.ran === true && /not started/.test(agentTab)) say(`the Agent tab says not started: ${agentTab}`);
    if (agentTab && want.ran === false && !/not started/.test(agentTab)) say(`the Agent tab says an agent ran: ${agentTab}`);
    for (const t of s.tabs) if (/AGENT REPORT|LAST MESSAGE|\[\[TASKUARY/.test(t.text)) say(`the ${t.key} tab shows a raw marker: ${t.text}`);
    const closeTab = s.tabs.find((t) => t.key === "close")?.text || "";
    if (closeTab && !want.draft && /waiting for Send/.test(closeTab)) say(`the Close out tab claims a draft waits: ${closeTab}`);
    if (want.quiet && s.advisor) say(`an Advisor line where none belongs: ${s.advisor}`);
  }
  // THE DOCK: the moves on offer, the lit one live and on the row, never a greyed button as the only move
  const live = s.row.filter((b) => !b.off && !b.more && b.id !== "back");
  if (s.row.length && !live.length) say(`every move on the row is greyed: ${s.row.map((b) => b.label)}`);
  for (const b of s.row.filter((b) => b.lit && b.off)) say(`the lit move "${b.label}" is greyed`);
  if (s.row.filter((b) => b.lit).length > 1) say(`two lit moves: ${s.row.filter((b) => b.lit).map((b) => b.label)}`);
  if (want.lit && !s.row.some((b) => b.lit && want.lit.test(b.label))) say(`lit is ${s.row.find((b) => b.lit)?.label || "nothing"}, want ${want.lit}`);
  for (const m of desk ? want.moves || [] : []) if (!s.row.some((b) => m.test(b.label)) && !s.buttons.some((b) => m.test(b))) say(`no ${m} on the row: ${s.row.map((b) => b.label)}`);
  return bad;
}

test("every state shows the right thing at a desk and on a phone", { timeout: 900000 }, async (t) => {
  const h = await startHarness();
  t.after(() => h.close());
  const page = await h.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  // ...and every API answer that failed: a "Failed to load task" banner is a request that came back an error
  const failed = [];
  page.on("response", (r) => { if (r.status() >= 400 && /\/api\//.test(r.url())) failed.push(`${r.status()} ${r.request().method()} ${new URL(r.url()).pathname}`); });
  await page.setViewport({ width: 1440, height: 900, deviceScaleFactor: 1 });
  await page.goto(h.ui, { waitUntil: "domcontentloaded" });
  await page.waitForSelector("[data-tq-rail] .tq-pile-row", { timeout: 30000 });
  const api = (p, body) => page.evaluate(async (p, body) => (await fetch(p, { method: body ? "POST" : "GET", ...(body ? { body: JSON.stringify(body) } : {}),
    headers: { "X-Taskuary-Token": localStorage.getItem("taskuary_token"), "Content-Type": "application/json" } })).json(), p, body);
  const tasks = (await api("/api/tasks")).data;
  const id = (re) => tasks.find((x) => re.test(x.Title))?.TaskId;
  const ids = { fresh: id(/^Month-end close is short/), owed: id(/^Year-end audit/), draft: id(/^Invoice 88213/), blocked: id(/importers#214/),
    waiting: id(/^Ray: schema sign-off/), goal: id(/^Migrate the census export/), invite: id(/^Invite: AP cutover dry run/) };
  for (const s of ["sent", "working", "coding_working", "asked", "stopped", "finished", "done", "note", "deferred", "todo", "idea", "news"])
    ids[s] = (await api("/api/fixture/task/matrix", { state: s })).taskId;
  ids.saved = (await api("/api/fixture/task/chat-saved", {})).taskId;
  ids.coding_saved = (await api("/api/fixture/task/coding-saved", {})).taskId;
  ids.failed = (await api("/api/fixture/task/playbook-failed", {})).taskId;
  ids.agent_closed = (await api("/api/fixture/task/agent-closed", { answer: "The nightly run in org/app failed on a missing DEPLOY_KEY secret. I re-added it and the re-run passed.",
    said: "the run failed on a missing secret; re-added it and the re-run passed" })).taskId;
  const gone = (await api("/api/tasks", { Title: "Lunch on Friday?", Summary: "Lunch on Friday?", Kind: "general" })).taskId;
  await api(`/api/tasks/${gone}/not-a-task`, { learn: false });
  ids.removed = gone;
  if (SHOTS) await mkdir(SHOTS, { recursive: true });

  const failures = [], dump = [];
  for (const [w, hgt] of [[1440, 900], [390, 844]]) {
    await page.setViewport({ width: w, height: hgt, deviceScaleFactor: 1 });
    await page.goto(h.ui, { waitUntil: "domcontentloaded" });
    await page.waitForSelector("[data-tq-rail] .tq-pile-row", { timeout: 30000 });
    await sleep(1500);
    for (const [name, target, want] of CELLS(ids)) {
      if (name === "Advisor idea" && w <= 600) await api("/api/fixture/task/matrix", { state: "idea" });   // the desk's was read
      if (target == null) { failures.push(`${name} @${w}: the state could not be built`); continue; }
      const seen = errors.length, failedAt = failed.length;
      let tid = null;
      if (typeof target === "number") {
        tid = target;
        await page.evaluate((id) => { location.hash = `task=${id}`; }, tid);
      } else {
        await page.evaluate(() => { location.hash = ""; });
        // a phone keeps the rail in its drawer
        if (w <= 600) { await page.evaluate(() => document.querySelector('[aria-label="Your work"]')?.click()); await sleep(800); }
        const opened = await page.evaluate((src) => {
          const rx = new RegExp(src);
          const r = [...document.querySelectorAll("[data-tq-rail] .tq-pile-row")].find((e) => rx.test(e.textContent));
          r?.querySelector(".card")?.click(); return !!r;
        }, target.source);
        if (!opened) {
          const rows = await page.evaluate(() => ({ btn: !!document.querySelector('[aria-label="Your work"]'),
            rows: [...document.querySelectorAll("[data-tq-rail] .tq-pile-row")].map((e) => e.textContent.replace(/\s+/g, " ").slice(0, 30)).slice(-8),
            n: document.querySelectorAll("[data-tq-rail] .tq-pile-row").length, rails: document.querySelectorAll("[data-tq-rail]").length,
            bands: [...document.querySelectorAll("[data-tq-rail] *")].filter((e) => /^(REPORTS|FYI|FOR LATER)/.test(e.textContent.trim()) && e.childElementCount === 0).map((e) => e.textContent.trim()) }));
          failures.push(`${name} @${w}: no rail row for ${target} ${JSON.stringify(rows)}`); continue;
        }
        if (want.batch) { await sleep(2500);   // the fyi batch: an FYI on the table, then Next
          await page.evaluate(() => document.querySelector("[data-tq-row] [data-tq-next]")?.click()); }
      }
      if (tid && !want.gone) await page.waitForSelector(`[data-tq-task-page="${tid}"] [data-tq-task-head]`, { timeout: 20000 }).catch(() => {});
      await sleep(500);
      const a = await look(page, want.card ? null : tid);
      await sleep(3500);
      const b = await look(page, want.card ? null : tid);
      const errs = [...errors.slice(seen), ...failed.slice(failedAt)];
      failures.push(...judge(name, w, a, b, errs, want), ...expect(name, w, b, want, w > 600));
      if (DUMP) dump.push({ cell: name, w, first: a, ...b });
      if (SHOTS) await page.screenshot({ path: path.join(SHOTS, `${w}-${name.replace(/[^\w]+/g, "-")}.png`) });
      await page.keyboard.press("Escape").catch(() => {});
    }
  }
  if (DUMP) await writeFile(DUMP, JSON.stringify(dump, null, 1));
  assert.deepEqual(failures, [], `\n${failures.length} cells failed:\n${failures.join("\n")}`);
});
