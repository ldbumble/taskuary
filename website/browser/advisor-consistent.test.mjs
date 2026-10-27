// THE ADVISOR AUDIT'S MATRIX, AS A TEST (the audit and its independent judge, 2026-10-26: placement 72%, consistency 52%). Every stage the
// audit drew - a to-do, a reply with and without a draft, an agent at work, one finished, one failed, a wait - under the Advisor's real
// decision and each decision a model could write (fixture_changes.py advisor/say, checked as a real answer is), at a laptop, with each
// drawer shut and pulled out, and on a phone. It asserts the judge's criteria: the Advisor's words stand in the MAIN view (never a drawer,
// no tab note), wrap whole on a phone, the lit button is enabled and is the decision's own, the clock menu says the section's line or
// nothing, a duplicate pair has one survivor, and nothing is said over an agent at work. Invented Northwind people only (CLAUDE.md).
import assert from "node:assert/strict";
import test from "node:test";
import { startHarness } from "./harness.mjs";

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
// what a model may write (the judge's valid combinations: a draft warning only where a draft is, a same ask only on a real pair)
const SAY = {
  late_usual: { state: "asked_late", verb: "reply", line: "You usually answer this sender within the hour; this is 5h.", kind: "late" },
  caution: { state: "asked", verb: "forward", line: "Paula takes vendor forms now - hand it to her.", by: "model", kind: "handoff" },
  lit_pick: { verb: "defer", line: "" },
  draft_warn: { state: "draft_ready", verb: "approve", line: "The draft promises Friday; nothing on the task backs that.", by: "model", kind: "draft_caution" },
};
const ROW = { close: ["done"], defer: ["remind"], regular_agent: ["start-agent", "send-general"], stop_agent: ["save-end"], split: ["reshape"],
  close_note: ["close-note"], review_changes: ["diff"], share_result: ["share"], forward: ["hand"], remove: ["nat"],
  run_another: ["run-another"], strong_again: ["strong-again"] };

const MEASURE = () => {
  const vis = (el) => { if (!el) return false; const r = el.getBoundingClientRect(); if (r.width < 1 || r.height < 1) return false;
    for (let p = el; p; p = p.parentElement) { const cs = getComputedStyle(p); if (cs.display === "none" || cs.visibility === "hidden") return false; } return true; };
  const where = (el) => el.closest("[data-tq-from-side]") ? "left drawer" : el.closest("[data-tq-work-side]") ? "right drawer" : el.closest("[data-tq-canvas-item]") ? "main view" : "elsewhere";
  const card = document.querySelector("[data-tq-canvas-item]");
  const adv = [...document.querySelectorAll("[data-tq-advisor]")].map((e) => { const l = e.querySelector("[data-tq-advisor-line]");
    return { where: where(e), visible: vis(e), line: l?.textContent.trim() || "", whole: !l || l.scrollWidth <= l.clientWidth + 1 }; });
  const row = document.querySelector(".tq-dock [data-tq-row]") || document.querySelector("[data-tq-row]");
  const lit = row ? [...row.querySelectorAll(".tq-arow-verbs button.tq-ab.p")].map((b) => ({ verb: b.getAttribute("data-tq-verb") || (b.hasAttribute("data-tq-next") ? "next" : ""), label: b.innerText.trim(), disabled: b.disabled })) : [];
  const cardLit = card ? [...card.querySelectorAll("[data-tq-lit]")].filter((e) => !e.hasAttribute("data-tq-work-tab")).map((e) => ({ label: e.innerText.trim(), disabled: !!e.disabled })) : [];
  const tab = card?.querySelector("[data-tq-work-tab]");
  return { adv, lit, cardLit, tab: tab ? tab.innerText.replace(/\s+/g, " ").trim() : "", main: card?.querySelector("[data-tq-task-body]")?.getAttribute("data-tq-main") || "" };
};

test("the Advisor's decision: in the main view, pressable, the same on every surface, one survivor per pair", { timeout: 900000 }, async () => {
  const h = await startHarness();
  const api = async (p, method = "GET", body) => (await fetch(`${h.fixtureApi}${p}`, { method,
    headers: { "X-Taskuary-Token": h.token, "Content-Type": "application/json" }, ...(body === undefined ? {} : { body: JSON.stringify(body) }) })).json();
  const fails = [], tally = { placement: [0, 0], lit: [0, 0], consistency: [0, 0] };
  const check = (crit, ok, what) => { tally[crit][1]++; if (ok) tally[crit][0]++; else { fails.push(`${crit}: ${what}`); console.log("FAIL", crit, what); } };
  try {
    const page = await h.newPage();
    const errors = [];
    page.on("pageerror", (e) => errors.push(e.message));
    await page.setViewport({ width: 1600, height: 810, deviceScaleFactor: 1 });
    await page.goto(h.ui, { waitUntil: "domcontentloaded", timeout: 60000 });
    await page.waitForSelector("[data-tq-rail] .tq-pile-row", { timeout: 60000 });
    const world = await api("/api/fixture/advisor/world", "POST", {});
    const failed = (await api("/api/fixture/task/playbook-failed", "POST", {})).taskId;
    const tasks = (await api("/api/tasks")).data;
    const id = (re) => tasks.find((t) => re.test(t.Title) && !["done", "dropped"].includes(t.Status))?.TaskId;
    const open = async (tid) => {
      await page.evaluate((i) => { location.hash = ""; location.hash = `task=${i}`; }, tid);
      await page.waitForSelector(`[data-tq-task-page="${tid}"]`, { timeout: 30000 });
      await sleep(2200);
    };
    const cell = async (name, tid, { drawers = true } = {}) => {
      await open(tid);
      const d = await api(`/api/advice?key=task:${tid}`);
      const shots = [["closed", await page.evaluate(MEASURE)]];
      for (const [tab, side] of drawers ? [["[data-tq-work-tab]", "[data-tq-work-side]"], ["[data-tq-from-line]", "[data-tq-from-side]"]] : []) {
        if (!(await page.$(`[data-tq-task-page="${tid}"] ${tab}`))) continue;
        await page.click(tab); await page.waitForSelector(side, { visible: true, timeout: 5000 }).catch(() => {}); await sleep(400);
        shots.push([tab, await page.evaluate(MEASURE)]);
        await page.keyboard.press("Escape"); await sleep(300);
      }
      for (const [how, m] of shots) {
        // 1 PLACEMENT: wherever the Advisor speaks, it is the main view - never a drawer - and no tab carries a note of it
        check("placement", m.adv.every((a) => a.where === "main view") && !/note/.test(m.tab), `${name} ${how}: ${JSON.stringify(m.adv)} tab "${m.tab}"`);
      }
      const m = shots[0][1];
      // 3 THE LIT BUTTON: enabled, and the decision's own (on the row, or the card's own move)
      if (d.verb && d.verb !== "next") {
        const ids = [d.verb, ...(ROW[d.verb] || [])];
        const own = m.lit.some((l) => !l.disabled && (l.label === d.label || ids.some((i) => l.verb === i || l.verb?.endsWith(`:${i}`) || l.verb === `advice:${d.verb}`)))
          || m.cardLit.some((l) => !l.disabled && l.label.startsWith(d.label));
        check("lit", own, `${name}: decided ${d.verb} (${d.label}) - row lights ${JSON.stringify(m.lit)}, card ${JSON.stringify(m.cardLit)}`);
      }
      check("lit", m.lit.every((l) => !l.disabled), `${name}: a lit button is greyed ${JSON.stringify(m.lit)}`);
      // 5 CONSISTENCY: the section says the decision's line or nothing, whole
      const shown = m.adv.filter((a) => a.visible);
      check("consistency", shown.every((a) => a.line === d.line && a.whole), `${name}: section ${JSON.stringify(shown)} vs decision "${d.line}"`);
      return { d, m };
    };
    const stages = { todo: id(/^Year-end audit/), reply_nodraft: world.plain, reply_drafted: id(/^Can you resend the Q3/), agent_finished: world.finished,
      agent_failed: failed, waiting: id(/^Ray: schema sign-off/) };
    for (const [stage, tid] of Object.entries(stages)) {
      await cell(`${stage}/real`, tid);
      for (const [st, say] of Object.entries(SAY)) {
        if (st === "draft_warn" && stage !== "reply_drafted") continue;
        await api("/api/fixture/advisor/say", "POST", { taskId: tid, decision: say });
        const { d } = await cell(`${stage}/${st}`, tid);
        // the check after the decision (advisor.checked): a draft caution never lights Send; late on a draft lights the draft's own Send
        if (st === "draft_warn") check("lit", d.verb !== "approve", `${stage}/draft_warn lit Send under its own caution`);
        if (st === "late_usual" && stage === "reply_drafted") check("lit", d.verb === "approve", `${stage}/late_usual lit ${d.verb}, not the draft's Send`);
        await api("/api/fixture/advisor/say", "POST", { taskId: tid, decision: null });
      }
    }
    // THE TWO STAGES THE AUDIT NEVER REACHED: a finished agent's page leads with its work (its Result), not the plain ask
    const fin = await cell("agent_finished/reached", world.finished, { drawers: false });
    check("placement", fin.m.main === "work", `the finished agent's page is main=${fin.m.main}`);
    // A WAIT PAST ITS DUE DAY: Chase, on the header's own count
    const wait = await api(`/api/advice?key=task:${stages.waiting}`);
    check("consistency", wait.verb === "chase" && wait.state === "waiting_overdue", `the overdue wait decided ${wait.state}/${wait.verb}`);
    // AN AGENT AT WORK: nothing said over it, Next its decision - even with a model line scripted for it
    await api("/api/fixture/advisor/say", "POST", { taskId: world.working, decision: SAY.caution });
    const work = await cell("agent_working/caution", world.working, { drawers: false });
    check("consistency", work.d.state === "working" && !work.d.line && !work.m.adv.length, `a line over a working agent: ${JSON.stringify(work.d)}`);
    await api("/api/fixture/advisor/say", "POST", { taskId: world.working, decision: null });
    // A DUPLICATE PAIR: one survivor; the other folded into it, naming it
    const [a, b] = [await cell("dup_first", world.dup1), await cell("dup_second", world.dup2)];
    check("consistency", [a.d.state, b.d.state].filter((s) => s === "duplicate").length === 1, `dup states ${a.d.state} / ${b.d.state}`);
    check("consistency", /^Same ask as TQ-\d+ - fold it into that one\.$/.test(b.d.line) && !["remove", "split"].includes(a.d.verb), `dup lines "${a.d.line}" / "${b.d.line}"`);
    // ERIN'S USUAL: the task, LEARNED.md and the clock menu say one thing
    const erin = await cell("memory_late_erin", world.late);
    const learned = (await api("/api/doc/learned")).content || "";
    check("consistency", erin.d.state === "asked_late" && /You answer Erin Blake \(erin@northwind\.example\) within the hour/.test(learned)
      && (erin.d.rests || []).some((r) => r.kind === "memory" && /within the hour/.test(r.label)), `the usual: ${JSON.stringify(erin.d)}`);
    await page.evaluate(() => { [...document.querySelectorAll("button")].find((e) => e.querySelector("[data-testid='HistoryIcon']") && e.getBoundingClientRect().width > 0)?.click(); });
    await sleep(1500);
    const menu = await page.evaluate(() => document.querySelector("[data-tq-advisor-notes-line]")?.innerText.replace(/\s+/g, " ").trim() || null);
    check("consistency", !menu || menu.includes(erin.d.line), `the clock menu says "${menu}" beside "${erin.d.line}"`);
    await page.keyboard.press("Escape"); await sleep(300);
    // ...Why? on it carries Keep / Wrong / Forget, and Wrong takes the line off the task
    await page.evaluate(() => document.querySelector("[data-tq-advisor] button[aria-haspopup='dialog']")?.click()); await sleep(600);
    const marks = await page.evaluate(() => [...document.querySelectorAll("[data-tq-advisor-marks] [data-tq-mark]")].map((b) => b.getAttribute("data-tq-mark")));
    check("consistency", marks.join() === "keep,wrong,forget", `Why? offers ${marks}`);
    await page.evaluate(() => document.querySelector("[data-tq-advisor-marks] [data-tq-mark='wrong']")?.click()); await sleep(2500);
    const after = await api(`/api/advice?key=task:${world.late}`);
    const said = await page.evaluate(() => document.querySelector(".tq-next-pop")?.innerText.replace(/\s+/g, " ") || "");
    const left = ((await api("/api/doc/learned")).content || "").split(/\r?\n/).filter((l) => /erin@/.test(l));
    check("consistency", after.state === "asked" && !after.line, `after Wrong the task still says "${after.line}" - popover "${said}", LEARNED ${JSON.stringify(left)}`);
    // THE PHONE: one stacked page, the line whole - "this is 5h" was cut off by an ellipsis
    await api("/api/fixture/advisor/say", "POST", { taskId: world.plain, decision: SAY.late_usual });
    await page.setViewport({ width: 390, height: 844, deviceScaleFactor: 1 });
    await page.goto(h.ui, { waitUntil: "domcontentloaded", timeout: 60000 });
    await sleep(2500);
    const ph = await cell("phone/late_usual", world.plain, { drawers: false });
    check("placement", ph.m.adv.length === 1 && ph.m.adv[0].whole && ph.m.adv[0].line.endsWith("this is 5h."), `phone: ${JSON.stringify(ph.m.adv)}`);
    await api("/api/fixture/advisor/say", "POST", { taskId: world.plain, decision: null });
    console.log("judge's criteria re-measured:", Object.fromEntries(Object.entries(tally).map(([k, [p, n]]) => [k, `${p}/${n}`])));
    assert.deepEqual(fails, []);
    assert.deepEqual(errors, []);
  } finally { await h.close(); }
});
