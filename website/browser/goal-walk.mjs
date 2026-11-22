/* THE GOAL WALK (the owner, 2026-11-22: "make harness better ... keep on iterating towards the goal" - a perfect assistant). Plays a SHAPE - a
   list of steps a person takes - on the running real app (real-run.mjs), and after every step says what the owner would have minded:
   what the screen did while it happened (watch.mjs: flicker, jump, blank, junk, twice), what was sent (the outbox: once per press, never twice),
   what the rail shows (no row twice, the task where it should be), and how long it took. Each step leaves its screenshot; the walk leaves
   goal-<shape>.json and goal-<shape>.md in REAL_OUT. A shape is JSON: [{"do": "new", "say": "..."}, {"do": "press", "button": "Send", "times": 50}, ...]

   node goal-walk.mjs <shape.json>     steps: new | type | press | search | row | go | mail | quiet | wait | expect */
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { api, connect, info, out, save, shot, sleep } from "./real-lib.mjs";
import { clean, said, watch } from "./watch.mjs";
import { record } from "./recorder.mjs";

const file = process.argv[2]; if (!file) { console.log("node goal-walk.mjs <shape.json>"); process.exit(2); }
const shape = JSON.parse(readFileSync(file, "utf8")), name = path.basename(file, ".json");
const { page } = await connect();
const VIS = (e) => { const r = e.getBoundingClientRect(); return r.width > 1 && r.height > 1 && getComputedStyle(e).visibility !== "hidden"; };

const outbox = () => { const f = path.join(info.home, "outbox.jsonl"); return existsSync(f) ? readFileSync(f, "utf8").trim().split("\n").filter(Boolean).map((l) => JSON.parse(l)) : []; };
const rail = () => page.evaluate((vs) => { const vis = eval(vs); return [...document.querySelectorAll("[data-tq-rail] .tq-pile-row[data-tq-key]")].filter(vis)
  .map((e) => ({ key: e.getAttribute("data-tq-key"), text: e.innerText.split("\n").filter(Boolean).join(" | ").slice(0, 160) })); }, `(${VIS})`);
const busy = () => page.evaluate(() => !!document.querySelector("[data-tq-task-page] [data-tq-stop-run]"));
// ...only what spins: a progress ring with a value (the header's setup ring) is a gauge, not work still going
const spinning = () => page.evaluate(() => [...document.querySelectorAll(".MuiCircularProgress-indeterminate, [role=progressbar]:not([aria-valuenow])")].filter((e) => e.getBoundingClientRect().width > 0).length);
const where = () => page.evaluate(() => location.hash || "#rail");

// a button by its words, found as a person sees it (visible, not greyed) - its centre, for the mouse
// ...by its WORDS as a person reads them (a bare arrow's aria-label "Send" is not the card's Send - the first goal walk pressed the empty
// box's), or by a CSS selector given as "[data-tq-…]"
const button = (words) => page.evaluate((w, vs) => {
  const vis = eval(vs), css = w.startsWith("["), re = !css && new RegExp(w, "i"), all = [...document.querySelectorAll(css ? w : "button, [role=button], a")].filter(vis);
  const b = css ? all.pop() : (all.filter((e) => re.test((e.innerText || "").trim())).pop() || all.filter((e) => !(e.innerText || "").trim() && re.test(e.getAttribute("aria-label") || "")).pop());
  if (!b) return null; if (b.matches(":disabled") || b.closest("[inert], [aria-disabled=true]")) return { off: true };
  b.scrollIntoView({ block: "center" }); const q = b.getBoundingClientRect(); return { x: q.x + q.width / 2, y: q.y + q.height / 2, name: b.innerText.trim() };
}, words, `(${VIS})`);
async function typeKeys(words, enter = true) {
  for (const [i, part] of String(words).split("\n").entries()) { if (i) { await page.keyboard.down("Shift"); await page.keyboard.press("Enter"); await page.keyboard.up("Shift"); } await page.keyboard.type(part); }
  if (enter) await page.keyboard.press("Enter");
}
async function typeIn(words) {
  const ok = await page.evaluate((vs) => { const vis = eval(vs); const b = [...document.querySelectorAll("[role=dialog] input:not([type=file]), [role=dialog] textarea"),
    document.querySelector("[data-tq-task-page] .tq-aui-input"), ...document.querySelectorAll("textarea, input[type=text]")].find((e) => e && vis(e) && !e.disabled);
    if (b) b.focus(); return !!b; }, `(${VIS})`);
  if (!ok) return false;
  for (const [i, part] of String(words).split("\n").entries()) { if (i) { await page.keyboard.down("Shift"); await page.keyboard.press("Enter"); await page.keyboard.up("Shift"); } await page.keyboard.type(part); }
  await page.keyboard.press("Enter"); return true;
}
async function untilQuiet(max = 600000) {
  const end = Date.now() + max; let calm = 0;
  while (Date.now() < end) { if (await busy()) calm = 0; else if ((calm += 500) >= 4000) return true; await sleep(500); }
  return false;
}

const STEPS = {
  async new(s) {                                   // New, his words, Enter: how long until his task stands on the rail and its page is drawn
    const b = await button("[data-tq-nav=new]"); if (!b?.x) return { problem: "no New in the nav" }; await page.mouse.click(b.x, b.y);
    // ...his words go in NEW'S OWN box - the first goal walk typed them into the open task's, and read the join as the app's
    const box = "[data-tq-new-agent-box] textarea, [data-tq-new-agent-box] [contenteditable=true]";
    try { await page.waitForSelector(box, { visible: true, timeout: 5000 }); } catch { return { problem: "New opened no box to type in" }; }
    const before = new Set((await rail()).map((r) => r.key)), t0 = Date.now();
    await page.focus(box); await typeKeys(s.say);
    let row = null, page_ = null;
    while (Date.now() - t0 < 60000 && !(row && page_)) {
      row ||= (await rail()).find((r) => !before.has(r.key)) && Date.now() - t0;
      page_ ||= (await where()).includes("task=") && Date.now() - t0;
      await sleep(100);
    }
    return { row_ms: row || null, page_ms: page_ || null, problem: !row ? "no new row on the rail within 60 s" : !page_ ? "his task's page never opened" : "" };
  },
  async type(s) { return { problem: (await typeIn(s.say)) ? "" : "no box to type in" }; },
  async press(s) {                                 // the same button pressed `times` times as fast as a hand can: it must act once
    const sent0 = outbox().length, rows0 = (await rail()).length, b = await button(s.button);
    if (!b) return { problem: `no button says "${s.button}"` }; if (b.off) return { problem: `"${s.button}" is greyed out` };
    for (let i = 0; i < (s.times || 1); i++) { await page.mouse.click(b.x, b.y); if (s.gap) await sleep(s.gap); }
    await sleep(s.settle ?? 6000);
    const sent = outbox().length - sent0, rows = (await rail()).length - rows0;
    const most = s.sends ?? (s.times > 1 ? 1 : null);
    return { sent, rows_added: rows, problem: most != null && sent > most ? `${s.times} presses sent ${sent} times (at most ${most})` : "" };
  },
  async search(s) {                                // Search, the words, the hit: the task must come onto the rail and open, and stay
    const o = await button("[data-tq-search-open]"); if (!o?.x) return { problem: "no Search to open" }; await page.mouse.click(o.x, o.y);
    try { await page.waitForSelector("[data-tq-search-input] input, input[data-tq-search-input]", { visible: true, timeout: 5000 }); } catch { return { problem: "Search opened no box" }; }
    await page.focus("[data-tq-search-input] input, input[data-tq-search-input]"); await page.keyboard.type(s.say);
    const t0 = Date.now(); let hit = null;
    while (Date.now() - t0 < 15000 && !(hit = await page.evaluate(() => { const h = document.querySelector("[data-tq-search-hit]"); if (!h) return null; const q = h.getBoundingClientRect(); return { x: q.x + q.width / 2, y: q.y + q.height / 2, text: h.innerText.slice(0, 120) }; }))) await sleep(200);
    if (!hit || s.none) await page.keyboard.press("Escape").catch(() => {});      // ...Search shut behind it, as a person leaves it
    if (!hit) return { hit_ms: null, problem: s.none ? "" : "no result for words that should find a task" };
    if (s.none) return { problem: `found "${hit.text}" for words that match nothing` };
    await page.mouse.click(hit.x, hit.y); await sleep(2500);
    const at = await where(), r = await rail(), id = (at.match(/task=(\d+)/) || [])[1];
    const onRail = id && r.some((x) => x.key.includes(id));
    await sleep(5000); const stays = (await where()) === at && (!id || (await rail()).some((x) => x.key.includes(id)));
    await page.keyboard.press("Escape").catch(() => {});
    return { hit_ms: Date.now() - t0, opened: at, problem: !id ? "the hit opened no task" : !onRail ? "the task it opened is not on the rail" : !stays ? "it opened, then went off" : "" };
  },
  async row(s) { const at = await page.evaluate((w, vs) => { const vis = eval(vs); const r = [...document.querySelectorAll("[data-tq-rail] .tq-pile-row[data-tq-key]")].filter(vis).find((e) => e.innerText.toLowerCase().includes(w.toLowerCase()));
    if (!r) return null; r.scrollIntoView({ block: "center" }); const q = r.getBoundingClientRect(); return { x: q.x + q.width / 2, y: q.y + q.height / 2 }; }, s.say, `(${VIS})`);
    if (!at) return { problem: `no rail row says "${s.say}"` }; await page.mouse.click(at.x, at.y); await sleep(2000); return {}; },
  async go(s) { if (s.to === "rail") { await page.evaluate(() => { location.hash = ""; }); await sleep(1500); return {}; }
    const b = await button(`^${s.to}$`); if (!b?.x) return { problem: `no "${s.to}" to go to` }; await page.mouse.click(b.x, b.y); await sleep(1500); return {}; },
  async mail(s) {                                  // a message arriving by itself, as the mailbox would bring it (invented people only)
    const r = await api("/api/ingest/push", { channel: "email", external_id: `goal-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`, ...s.msg });
    await sleep(s.settle ?? 3000); return { pushed: !!r, problem: r && r.ok === false ? `the push was refused: ${JSON.stringify(r).slice(0, 200)}` : "" };
  },
  async quiet(s) { const t0 = Date.now(), ok = await untilQuiet((s.max || 600) * 1000); return { took_ms: Date.now() - t0, problem: ok ? "" : `still working after ${s.max || 600} s` }; },
  async wait(s) { await sleep((s.s || 5) * 1000); return {}; },
  async expect(s) {                                // what must (or must not) be on the screen now - the step's own words
    const text = await page.evaluate(() => document.body.innerText);
    const miss = (s.see || []).filter((w) => !new RegExp(w, "i").test(text)), bad = (s.never || []).filter((w) => new RegExp(w, "i").test(text));
    return { problem: [...miss.map((w) => `not on screen: ${w}`), ...bad.map((w) => `on screen and should not be: ${w}`)].join("; ") };
  },
};

const results = [];
for (const [i, s] of shape.entries()) {
  if (!STEPS[s.do]) { results.push({ i, step: s, problem: `no step "${s.do}"` }); continue; }
  const w = await watch(page), t0 = Date.now(), dir = path.join(out, "video", `goal-${name}-${String(i).padStart(2, "0")}-${s.do}`);
  const rec = await record(page, dir).catch(() => null);
  let r; try { r = await STEPS[s.do](s); } catch (e) { r = { problem: `the step threw: ${e.message.slice(0, 200)}` }; }
  const seen = await w.stop().catch(() => ({})), ms = Date.now() - t0;
  await rec?.stop({ sheet: 8 }).catch(() => {});
  const r2 = await rail(), dup = r2.map((x) => x.key).filter((k, j, a) => a.indexOf(k) !== j);
  const spin = (await busy()) ? 0 : await spinning();
  const img = await shot(page, `goal-${name}-${String(i).padStart(2, "0")}-${s.do}`);
  const problems = [r.problem, dup.length && `rail row twice: ${dup.join(", ")}`, spin && s.do !== "press" && `${spin} spinner(s) left with no agent at work`,
    !clean(seen) && said(seen)].filter(Boolean);
  results.push({ i, step: s, ms, ...r, seen, shot: img, problems });
  console.log(`${problems.length ? "✗" : "✓"} ${i} ${s.do} ${JSON.stringify(s).slice(0, 90)} - ${ms} ms${problems.length ? `\n    ${problems.join("\n    ")}` : ""}`);
}
const bad = results.filter((r) => r.problems?.length || r.problem);
await save(`goal-${name}.json`, results);
await save(`goal-${name}.md`, `# Goal walk: ${name}\n\n${bad.length ? `${bad.length} of ${results.length} steps showed something wrong` : `all ${results.length} steps clean`}\n\n` +
  results.map((r) => `- ${r.problems?.length ? "✗" : "✓"} **${r.i} ${r.step.do}** ${r.step.say || r.step.button || r.step.to || ""} (${r.ms} ms) ${r.shot ? `[shot](${r.shot})` : ""}${(r.problems || []).map((p) => `\n  - ${p.replace(/\n/g, "\n    ")}`).join("")}`).join("\n") + "\n");
console.log(`\n${bad.length ? `${bad.length}/${results.length} steps showed something wrong` : `all ${results.length} steps clean`} - ${path.join(out, `goal-${name}.md`)}`);
process.exit(0);
