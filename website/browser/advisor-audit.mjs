// THE ADVISOR AUDIT (the owner, 2026-10-26: "run one for advisor and memories to ensure it's displayed correctly on correct thing (meaning
// left sidebar | right sidebar hidden or open) and it's something that actually makes sense"). Not a test - it asserts nothing: for every
// task stage x Advisor decision x drawer state x screen it saves a screenshot and a record of where the Advisor's words landed, what the
// right tab said, and which button was lit. The demo world plus fixture_changes.py's advisor/world and advisor/say. Invented people.
// Run from website/ with Node 22+:  ADVISOR_AUDIT_OUT=<folder> node browser/advisor-audit.mjs
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { startHarness } from "./harness.mjs";

const out = process.env.ADVISOR_AUDIT_OUT || path.resolve("advisoraudit");
const only = process.env.ADVISOR_AUDIT_ONLY || "";          // a substring of cell names, to re-run a few
await mkdir(out, { recursive: true });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const h = await startHarness();
const api = async (p, method = "GET", body) => (await fetch(`${h.fixtureApi}${p}`, { method,
  headers: { "X-Taskuary-Token": h.token, "Content-Type": "application/json" }, ...(body === undefined ? {} : { body: JSON.stringify(body) }) })).json();

// what the Advisor is made to decide (advisor/say); `real` leaves its own decision
const STATES = {
  silent: { line: "" },
  late_usual: { state: "asked_late", verb: "reply", line: "You usually answer this sender within the hour; this is 5h." },
  same_ask: { state: "duplicate", verb: "remove", line: "Same ask as TQ-0002." },
  draft_warn: { state: "draft_ready", verb: "approve", line: "The draft promises Friday; nothing on the task backs that.", by: "model" },
  caution: { state: "asked", verb: "forward", line: "Paula takes vendor forms now - hand it to her.", by: "model" },
  lit_pick: { verb: "defer", line: "" },
};
const WAIT_USUAL = { state: "waiting_late_usual", verb: "chase", line: "Ray usually answers in a day; this is 4 days." };

// a verb's buttons on the row (buttons.json `row`)
const ROW = { close: ["done"], defer: ["remind"], regular_agent: ["start-agent", "send-general"], stop_agent: ["save-end"], split: ["reshape"],
  close_note: ["close-note"], review_changes: ["diff"], share_result: ["share"], ask_sender: ["ask-sender"], forward: ["hand"], remove: ["nat"],
  run_another: ["run-another"], strong_again: ["strong-again"], change_kind: ["kind"], pick_repo: ["repo"] };
const records = [];
const MEASURE = () => {
  const vis = (el) => {
    if (!el) return false;
    const r = el.getBoundingClientRect();
    if (r.width < 1 || r.height < 1 || r.bottom <= 0 || r.top >= innerHeight || r.right <= 0 || r.left >= innerWidth) return false;
    for (let p = el; p; p = p.parentElement) { const cs = getComputedStyle(p); if (cs.display === "none" || cs.visibility === "hidden" || +cs.opacity === 0) return false; }
    for (let p = el.parentElement; p; p = p.parentElement) {
      const cs = getComputedStyle(p);
      if (cs.overflowX === "visible" && cs.overflowY === "visible") continue;
      const b = p.getBoundingClientRect();
      if (r.bottom <= b.top + 1 || r.top >= b.bottom - 1 || r.right <= b.left + 1 || r.left >= b.right - 1) return false;
    }
    return true;
  };
  const where = (el) => el.closest("[data-tq-from-side]") ? "left drawer" : el.closest("[data-tq-work-side]") ? "right drawer"
    : el.closest("[data-tq-canvas-item]") ? "main view" : el.closest("[data-tq-rail]") ? "rail" : el.closest(".tq-dock") ? "dock" : "elsewhere";
  const card = document.querySelector("[data-tq-canvas-item]");
  const advisor = [...document.querySelectorAll("[data-tq-advisor]")].map((e) => ({ where: where(e), visible: vis(e), text: e.innerText.replace(/\s+/g, " ").trim(),
    kind: e.querySelector("[data-tq-advisor-note]")?.getAttribute("data-tq-advisor-note") || "" }));
  const row = document.querySelector(".tq-dock [data-tq-row]") || document.querySelector("[data-tq-row]");
  const lit = row ? [...row.querySelectorAll(".tq-arow-verbs button.tq-ab.p")].map((b) => ({ verb: b.getAttribute("data-tq-verb"), label: b.innerText.trim(), visible: vis(b), disabled: b.disabled })) : [];
  const buttons = row ? [...row.querySelectorAll(".tq-arow-verbs button")].map((b) => b.getAttribute("data-tq-verb") || (b.hasAttribute("data-tq-next") ? "next" : b.innerText.trim())) : [];
  const rt = card?.querySelector("[data-tq-work-tab]"), lt = card?.querySelector("[data-tq-from-line]");
  // the Advisor's pick of a card's own move is lit on the card (ReviewDecision `data-tq-lit`), and a card's filled MUI buttons are dark too
  const cardLit = card ? [...card.querySelectorAll("[data-tq-lit]")].filter((e) => !e.hasAttribute("data-tq-work-tab"))
    .map((e) => ({ label: e.innerText.trim().slice(0, 40), where: where(e), visible: vis(e) })) : [];
  const cardFilled = card ? [...card.querySelectorAll("button.MuiButton-contained")].map((e) => ({ label: e.innerText.trim().slice(0, 40), where: where(e), visible: vis(e), disabled: e.disabled })) : [];
  return {
    cardLit, cardFilled,
    main: card?.querySelector("[data-tq-task-body]")?.getAttribute("data-tq-main") || (card ? "no task body" : "no task view"),
    advisor, advisedVerb: document.querySelector("[data-tq-advice]")?.getAttribute("data-tq-advice-verb") || null,
    lit, rowButtons: buttons,
    rightTab: rt ? { text: rt.innerText.replace(/\s+/g, " ").trim(), lit: rt.hasAttribute("data-tq-lit"), open: rt.getAttribute("aria-expanded") === "true", note: /· 1 note/.test(rt.innerText) } : null,
    leftTab: lt ? { text: lt.innerText.replace(/\s+/g, " ").trim(), open: lt.getAttribute("aria-expanded") === "true" } : null,
    rightOpen: !!card?.querySelector("[data-tq-work-side]") && vis(card.querySelector("[data-tq-work-side]")),
    leftOpen: !!card?.querySelector("[data-tq-from-side]") && vis(card.querySelector("[data-tq-from-side]")),
    title: card?.querySelector("[data-tq-task-head]")?.innerText.split("\n")[0] || card?.innerText.split("\n")[0] || "",
  };
};
// where else the line's words stand on the page (the rail, Came from, the dock) - a line said twice, or about another task
const ECHO = (needle) => {
  if (!needle) return [];
  const hits = [];
  for (const el of document.querySelectorAll("body *")) {
    if ([...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.includes(needle))) {
      const w = el.closest("[data-tq-advisor]") ? null : el.closest("[data-tq-from-side],[data-tq-from]") ? "came from" : el.closest("[data-tq-rail]") ? "rail"
        : el.closest(".tq-dock") ? "dock" : el.closest("[data-tq-canvas-item]") ? "task" : "elsewhere";
      if (w) hits.push(w);
    }
  }
  return hits;
};

async function openTask(page, id) {
  await page.evaluate((id) => { location.hash = ""; location.hash = `task=${id}`; }, id);
  await page.waitForSelector(`[data-tq-task-page="${id}"]`, { timeout: 20000 });
  await page.waitForSelector(".tq-dock [data-tq-row]", { timeout: 20000 }).catch(() => {});
  await sleep(2200);                                         // past the lit move's hold and the advice read
}

async function capture(page, cell, rec) {
  const file = `${cell}.png`;
  await page.screenshot({ path: path.join(out, file) });
  const m = await page.evaluate(MEASURE);
  // the decision as it stands when the frame is taken: a model read (the demo's scripted one) can land after the page opened
  if (rec.taskId) {
    const a = await api(`/api/advice?key=task:${rec.taskId}`);
    rec = { ...rec, advisorInput: { state: a.state, verb: a.verb, label: a.label, line: a.line, by: a.by, none: a.none, scripted: !!a.scripted } };
    if (!a.scripted && a.by === "model") rec.advisorSource = "real (the demo's scripted model read)";
  }
  const line = rec.advisorInput?.line || "";
  const echoes = await page.evaluate(ECHO, line.slice(0, 28));
  const words = m.advisor.length ? (m.advisor.some((a) => a.visible) ? m.advisor.filter((a) => a.visible).map((a) => a.where).join(", ")
    : `hidden in ${m.advisor.map((a) => a.where).join(", ")}`) : "nowhere";
  const r = { cell, file, ...rec, wordsAppeared: words, ...m, lineEchoes: echoes };
  r.flags = flagsOf(r);
  records.push(r);
  console.log(cell, "|", words, "|", m.lit.map((l) => l.verb).join(","), "|", m.rightTab?.text || "-", r.flags.length ? `FLAGS ${r.flags.join("; ")}` : "");
}

function flagsOf(r) {
  const f = [], a = r.advisor;
  if (a.some((x) => !x.visible && /drawer/.test(x.where)) && !(r.rightTab?.note)) f.push("advisor words in a closed drawer with no tab note");
  if (a.some((x) => !x.visible) && !a.some((x) => x.visible) && !r.rightTab) f.push("advisor section present but not visible");
  if (r.rightTab?.note && !a.some((x) => x.where === "right drawer")) f.push("tab says a note but the drawer holds none");
  const v = r.advisorInput?.verb, ids = [v, ...(ROW[v] || [])];
  r.litMatchesAdvisor = !v ? null : r.lit.some((l) => l.label === r.advisorInput.label || ids.some((i) => l.verb === i || l.verb?.endsWith(`:${i}`) || l.verb === `advice:${v}`));
  r.litOnCard = !v ? null : r.cardLit.some((l) => l.label.startsWith(r.advisorInput.label || "\u0000"));
  if (v && v !== "next" && !r.litMatchesAdvisor && !r.litOnCard)
    f.push(`advisor picked '${v}' (${r.advisorInput.label}) but row lights [${r.lit.map((l) => l.label).join(",")}] and card lights [${r.cardLit.map((l) => l.label).join(",")}]`);
  if (r.litOnCard && r.cardLit.some((l) => !l.visible)) f.push("the card's lit button is not in view");
  const dark = r.cardFilled.filter((b) => b.visible && !b.disabled && b.label !== r.advisorInput?.label).map((b) => b.label);
  if (v && (r.litMatchesAdvisor || r.litOnCard) && dark.length) f.push(`another dark button on the card: ${dark.join(",")}`);
  if (v === "next" && !r.lit.length && !r.rowButtons.includes("next")) f.push("advisor picked Next but no Next on the row");
  if (r.lit.length > 1) f.push(`${r.lit.length} lit buttons`);
  if (r.lit.some((l) => !l.visible)) f.push("lit button not visible");
  if (a.length > 1) f.push(`${a.length} advisor sections`);
  if (r.lineEchoes.length) f.push(`line's words also in ${[...new Set(r.lineEchoes)].join(", ")}`);
  if (r.otherTasksWithUsual?.length) f.push(`usual line also on ${r.otherTasksWithUsual.join(",")}`);
  return f;
}

async function cellsFor(page, stage, tid, state, decision, vps, { drawers = true } = {}) {
  if (decision !== "real") await api("/api/fixture/advisor/say", "POST", { taskId: tid, decision });
  const advisorInput = await api(`/api/advice?key=task:${tid}`);
  for (const [w, hgt] of vps) {
    const name = `${stage}__${state}__${w}x${hgt}`;
    if (only && !name.includes(only)) continue;
    await page.setViewport({ width: w, height: hgt, deviceScaleFactor: 1 });
    await openTask(page, tid);
    const rec = { stage, taskId: tid, advisorState: state, advisorSource: decision === "real" ? "real rulebook decision" : "scripted (advisor/say)",
      advisorInput: { state: advisorInput.state, verb: advisorInput.verb, label: advisorInput.label, line: advisorInput.line, by: advisorInput.by, none: advisorInput.none }, viewport: `${w}x${hgt}` };
    await capture(page, `${name}__closed`, { ...rec, drawer: "both closed" });
    if (!drawers) continue;
    for (const [tab, side, label] of [["[data-tq-work-tab]", "[data-tq-work-side]", "right open"], ["[data-tq-from-line]", "[data-tq-from-side]", "left open"]]) {
      if (!(await page.$(`[data-tq-task-page="${tid}"] ${tab}`))) { records.push({ cell: `${name}__${label.replace(" ", "_")}`, ...rec, drawer: label, file: null, note: "no such drawer on this main view" }); continue; }
      await page.click(tab);
      await page.waitForSelector(side, { visible: true, timeout: 5000 }).catch(() => {});
      await sleep(400);
      await capture(page, `${name}__${label.replace(" ", "_")}`, { ...rec, drawer: label });
      await page.keyboard.press("Escape");
      await sleep(300);
    }
  }
  if (decision !== "real") await api("/api/fixture/advisor/say", "POST", { taskId: tid, decision: null });
}

try {
  const page = await h.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.setViewport({ width: 1600, height: 810, deviceScaleFactor: 1 });
  await page.goto(h.ui, { waitUntil: "domcontentloaded", timeout: 30000 });
  await page.waitForSelector("[data-tq-rail] .tq-pile-row", { timeout: 30000 });
  const world = await api("/api/fixture/advisor/world", "POST", {});
  const failed = (await api("/api/fixture/task/playbook-failed", "POST", {})).taskId;
  const tasks = (await api("/api/tasks")).data;
  const id = (re) => tasks.find((t) => re.test(t.Title) && !["done", "dropped"].includes(t.Status))?.TaskId;
  const S = {
    todo: id(/^Year-end audit/), reply_nodraft: world.plain, reply_drafted: id(/^Can you resend the Q3/),
    agent_working: world.working, agent_finished: world.finished, agent_failed: failed, waiting: id(/^Ray: schema sign-off/),
  };
  await writeFile(path.join(out, "stages.json"), JSON.stringify({ ...S, world }, null, 2));
  const LAP = [[1600, 810], [1920, 1080]];
  // the matrix: every stage x every scripted decision, plus each stage's own real decision
  for (const [stage, tid] of Object.entries(S)) {
    await cellsFor(page, stage, tid, "real", "real", LAP);
    for (const [st, d] of Object.entries(STATES)) await cellsFor(page, stage, tid, st, stage === "waiting" && st === "late_usual" ? WAIT_USUAL : d, LAP);
  }
  // real decisions the app's own facts make: late against Erin's counted usual, one thread on two tasks, a late goal step, an invite clash
  for (const [stage, tid] of [["memory_late_erin", world.late], ["dup_first", world.dup1], ["dup_second", world.dup2],
    ["goal_late", id(/^Migrate the census export/)], ["invite_clash", id(/^Invite: AP cutover/)]]) await cellsFor(page, stage, tid, "real", "real", LAP);
  // THE PHONE: one stacked page, no drawers
  for (const [stage, tid] of [["todo", S.todo], ["reply_drafted", S.reply_drafted], ["agent_working", S.agent_working], ["agent_failed", S.agent_failed], ["memory_late_erin", world.late]])
    for (const st of stage === "memory_late_erin" ? ["real"] : ["draft_warn", "caution", "same_ask"])
      await cellsFor(page, `phone_${stage}`, tid, st, st === "real" ? "real" : STATES[st], [[390, 844]], { drawers: false });
  // THE FYI BATCH: a rail row, not a task - only the Advisor's own decision
  if (!only || "fyi_batch".includes(only)) {
    await page.setViewport({ width: 1600, height: 810, deviceScaleFactor: 1 });
    await page.evaluate(() => { location.hash = ""; });
    await sleep(800);
    const clicked = await page.evaluate(() => { const r = [...document.querySelectorAll("[data-tq-rail] .tq-pile-row")].find((e) => /fyi/i.test(e.innerText)); r?.click(); return r?.innerText || ""; });
    await sleep(2500);
    await capture(page, "fyi_batch__real__1600x810__closed", { stage: "fyi_batch", advisorState: "real", advisorSource: "real rulebook decision", advisorInput: null, viewport: "1600x810", drawer: "n/a", railRow: clicked });
  }
  // A LEARNED USUAL ON THE RIGHT TASK ONLY: the usual's words wherever they stand, across every open task
  const usualOn = [];
  for (const t of (await api("/api/tasks")).data.filter((t) => !["done", "dropped"].includes(t.Status))) {
    const a = await api(`/api/advice?key=task:${t.TaskId}`);
    if (/usually/i.test(a.line || "")) usualOn.push({ taskId: t.TaskId, title: t.Title, line: a.line, state: a.state });
  }
  await writeFile(path.join(out, "usual-lines.json"), JSON.stringify({ expected: world.late, usualOn }, null, 2));
  await writeFile(path.join(out, "records.json"), JSON.stringify(records, null, 2));
  await writeFile(path.join(out, "page-errors.json"), JSON.stringify(errors, null, 2));
  console.log("records", records.length, "errors", errors.length);
} finally { await h.close(); }
