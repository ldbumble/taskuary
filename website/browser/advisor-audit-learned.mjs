// THE ADVISOR AUDIT, MEMORY SIDE (2026-10-26): the Learned page after Keep, Wrong and Forget on three learned lines (a fresh install,
// where the page's writes are its own), and - in the demo world - the Why? behind a learned "usual" on its task. Not a test: screenshots
// and records. Invented Northwind people. Run from website/ with Node 22+:  ADVISOR_AUDIT_OUT=<folder> node browser/advisor-audit-learned.mjs
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { startHarness } from "./harness.mjs";

const out = process.env.ADVISOR_AUDIT_OUT || path.resolve("advisoraudit");
await mkdir(out, { recursive: true });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const call = (h) => async (p, method = "GET", body) => (await fetch(`${h.fixtureApi}${p}`, { method,
  headers: { "X-Taskuary-Token": h.token, "Content-Type": "application/json" }, ...(body === undefined ? {} : { body: JSON.stringify(body) }) })).json();
const records = [];
const LINES = {
  keep: ["payroll ray colton", "- Payroll questions from site managers go to Ray Colton (ray@northwind.example) [s:4 | ev: task1 | seen: 2026-10-20 | k: payroll ray colton]"],
  wrong: ["erin same day", "- You answer Erin Blake (erin@northwind.example) the same day [s:3 | ev: msg12 | seen: 2026-10-21 | k: erin same day]"],
  forget: ["paula w9", "- Paula Vance (paula@northwind.example) takes W-9s now [s:3 | ev: task7 | seen: 2026-10-22 | k: paula w9]"],
};

const viewOf = (page) => page.evaluate(() => ({
  sections: [...document.querySelectorAll("[data-tq-learned-section]")].map((e) => e.getAttribute("data-tq-learned-section")),
  lines: [...document.querySelectorAll("[data-tq-learned-line]")].map((e) => ({ key: e.getAttribute("data-tq-learned-line"),
    text: (e.parentElement?.innerText || e.innerText).replace(/\s+/g, " ").trim().slice(0, 220),
    marks: [...(e.parentElement || e).querySelectorAll("[data-tq-mark]")].map((b) => b.getAttribute("data-tq-mark")) })),
  alerts: [...document.querySelectorAll('[role="alert"]')].map((e) => e.innerText.trim()).filter(Boolean),
}));
const changesOf = (page) => page.evaluate(() => [...document.querySelectorAll("[data-tq-learned-changes] > div")].map((e) => ({
  text: e.innerText.replace(/\s+/g, " ").trim().slice(0, 240), marks: [...e.querySelectorAll("[data-tq-mark]")].map((b) => b.getAttribute("data-tq-mark")) })));

{
  const h = await startHarness({ fresh: true }), api = call(h);
  try {
    const doc = (await api("/api/doc/learned")).content || "";
    await api("/api/doc/learned", "PUT", { content: doc.replace("## Your people\n", `## Your people\n${Object.values(LINES).map((l) => l[1]).join("\n")}\n`) });
    const page = await h.newPage();
    await page.setViewport({ width: 1600, height: 810, deviceScaleFactor: 1 });
    const open = async (view) => {
      await page.goto(`${h.ui}#settings=docs&doc=learned&view=${view}`, { waitUntil: "domcontentloaded", timeout: 90000 });
      await page.waitForSelector(view === "viz" ? "[data-tq-learned-line]" : "[data-tq-learned-changes]", { timeout: 60000 }).catch(() => {});
      await sleep(1200);
    };
    const shot = async (cell, extra) => {
      await page.screenshot({ path: path.join(out, `${cell}.png`) });
      const viz = cell.includes("changes") ? null : await viewOf(page), ch = cell.includes("changes") ? await changesOf(page) : null;
      records.push({ cell, file: `${cell}.png`, ...extra, view: viz, changes: ch, doc: (await api("/api/doc/learned")).content.split("\n").filter((l) => /northwind\.example/.test(l)),
        changesApi: ((await api("/api/learned/changes")).data || []).slice(0, 6) });
      console.log(cell);
    };
    await open("viz");
    await shot("learned__before__viz", { step: "three learned lines, nothing marked" });
    for (const [mark, [key]] of Object.entries(LINES)) {
      await open("viz");
      const sel = `[data-tq-learned-line="${key}"] [data-tq-mark="${mark}"]`;
      await sleep(800);
      const there = await page.evaluate((s) => { const b = document.querySelector(s); b?.click(); return !!b; }, sel);
      await sleep(1800);
      await shot(`learned__after_${mark}__viz`, { step: `${mark} on '${key}'`, pressed: there });
      await open("changes");
      await shot(`learned__after_${mark}__changes`, { step: `What changed after ${mark}` });
    }
  } finally { await h.close(); }
}

// THE WHY? BEHIND A LEARNED USUAL, on the task it is about (demo world: Erin's counted usual, advisor/world)
{
  const h = await startHarness(), api = call(h);
  try {
    const page = await h.newPage();
    await page.setViewport({ width: 1600, height: 810, deviceScaleFactor: 1 });
    await page.goto(h.ui, { waitUntil: "domcontentloaded", timeout: 30000 });
    await page.waitForSelector("[data-tq-rail] .tq-pile-row", { timeout: 30000 });
    const world = await api("/api/fixture/advisor/world", "POST", {});
    await page.evaluate((id) => { location.hash = `task=${id}`; }, world.late);
    await page.waitForSelector(`[data-tq-task-page="${world.late}"]`, { timeout: 20000 });
    await sleep(2500);
    const before = await page.evaluate(() => ({ main: document.querySelector("[data-tq-task-body]")?.getAttribute("data-tq-main"),
      tab: document.querySelector("[data-tq-work-tab]")?.innerText.replace(/\s+/g, " "), advisor: document.querySelector("[data-tq-advisor]")?.innerText.replace(/\s+/g, " ") || null }));
    await page.evaluate(() => { const t = document.querySelector("[data-tq-work-tab]"); if (t && t.getAttribute("aria-expanded") !== "true") t.click(); });
    await sleep(800);
    const clicked = await page.evaluate(() => { const b = document.querySelector("[data-tq-advisor] button[aria-haspopup='dialog']"); b?.click(); return !!b; });
    await sleep(1500);
    await page.screenshot({ path: path.join(out, "memory_late_erin__why_popover__1600x810.png") });
    const pop = await page.evaluate(() => {
      const d = document.querySelector('[aria-label="Why the Advisor says this"]');
      return d ? { text: d.innerText.replace(/\s+/g, " ").trim(), marks: [...d.querySelectorAll("button")].map((b) => b.innerText.trim()) } : null;
    });
    records.push({ cell: "memory_late_erin__why_popover__1600x810", file: "memory_late_erin__why_popover__1600x810.png", taskId: world.late,
      advisorInput: await api(`/api/advice?key=task:${world.late}`), notes: await api(`/api/advice/notes?key=task:${world.late}&limit=5`), before, whyClicked: clicked, popover: pop,
      keepWrongForgetInWhy: !!pop && pop.marks.some((m) => /keep|wrong|forget/i.test(m)) });
    console.log("why", JSON.stringify(pop));
    // ...and the Advisor's notes on the item, in the clock menu over past chats (AssistantView AdvisorNotes)
    await page.keyboard.press("Escape");
    await sleep(400);
    const opened = await page.evaluate(() => {
      const b = [...document.querySelectorAll("button")].find((e) => e.querySelector("[data-testid='HistoryIcon']") && e.getBoundingClientRect().width > 0);
      b?.click(); return !!b;
    });
    await sleep(1800);
    await page.screenshot({ path: path.join(out, "memory_late_erin__advisor_notes_menu__1600x810.png") });
    const notesPanel = await page.evaluate(() => document.querySelector(".tq-advisor-notes")?.innerText.replace(/\s+/g, " ").trim() || null);
    records.push({ cell: "memory_late_erin__advisor_notes_menu__1600x810", file: "memory_late_erin__advisor_notes_menu__1600x810.png", taskId: world.late,
      menuOpened: opened, advisorNotesPanel: notesPanel });
    console.log("notes", notesPanel);
  } finally { await h.close(); }
}
await writeFile(path.join(out, "learned-records.json"), JSON.stringify(records, null, 2));
