// The assistant-canvas screenshot gate (docs/superpowers/plans/2026-09-29-assistant-canvas-redesign.md):
//   node website/canvas_shots.mjs <url-with-?token=> <outdir> <label> [scene,scene,...]
// Shoots every scene at 1440x900 and 390x844 against a `taskuary --demo` server, and records per shot the
// horizontal scroll, the xterm boxes, and any /api/funnel/pile request made during a client-only step.
// Scenes find things by data-* names or aria labels, never by the words inside them.
import fs from "node:fs";
import path from "node:path";
import { launch } from "./browser.mjs";

const [url, outdir, label = "shot", only = ""] = process.argv.slice(2);
if (!url || !outdir) { console.error("usage: canvas_shots.mjs <url?token=> <outdir> <label> [scenes]"); process.exit(2); }
fs.mkdirSync(outdir, { recursive: true });
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const VIEWS = { 1440: { width: 1440, height: 900, deviceScaleFactor: 1 }, 390: { width: 390, height: 844, isMobile: true, hasTouch: true, deviceScaleFactor: 2 } };

const hush = (page) => page.evaluate(() => document.querySelectorAll(".MuiSnackbar-root").forEach((e) => (e.style.display = "none")));
const visible = (page, sel) => page.evaluate((s) => [...document.querySelectorAll(s)].some((e) => e.getBoundingClientRect().width > 0), sel);
const click = (page, sel, nth = 0) => page.evaluate((s, n) => {
  const el = [...document.querySelectorAll(s)].filter((e) => e.getBoundingClientRect().width > 0)[n];
  if (!el) return false; el.scrollIntoView({ block: "center" }); el.click(); return true;
}, sel, nth);
// a button by its visible words - only for today's controls that carry no name yet
const clickText = (page, text, tags = "button,[role=button],a,li") => page.evaluate((l, t) => {
  const norm = (x) => x.replace(/\s+/g, " ").trim();
  const el = [...document.querySelectorAll(t)].filter((d) => norm(d.textContent).toLowerCase() === l.toLowerCase() && d.getBoundingClientRect().width > 0)
    .sort((a, b) => a.textContent.length - b.textContent.length)[0];
  if (!el) return false; el.click(); return true;
}, text, tags);
const tab = async (page, name) => {
  if (await clickText(page, name, "#tqTopNav div, #tqTopNav button")) return true;
  if (await click(page, `[data-tq-nav="${name.toLowerCase()}"]`)) return true;
  const opened = await page.evaluate(() => { const s = document.querySelector("#tqTopNav .MuiSelect-select"); if (!s) return false; s.dispatchEvent(new MouseEvent("mousedown", { bubbles: true })); return true; });
  if (!opened) return false;
  await wait(400);
  return page.evaluate((l) => { const it = [...document.querySelectorAll('li[role="option"]')].find((e) => e.textContent.replace(/^✦ /, "").trim().startsWith(l === "Assistant" ? "✦" : l) || e.textContent.includes(l)); if (!it) return false; it.click(); return true; }, name);
};
// the first step that works - `a() || b()` on promises is always the first promise
const first = async (...fs) => { for (const f of fs) if (await f()) return true; return false; };
const openRail = (page) => click(page, '[aria-label="Open the sidebar"], [data-tq-rail-toggle], [aria-label="The Timeline"]');

// SCENES: [name, async (page, w) => truthy to shoot, and whether the step must be client-only]
const SCENES = [
  ["home", async () => true],
  ["rail-scrolled", async (p) => p.evaluate(() => { const r = document.querySelector("[data-tq-rail]"); if (!r) return false; r.scrollTop = r.scrollHeight / 2; return true; })],
  ["rail-bottom", async (p) => p.evaluate(() => { const r = document.querySelector("[data-tq-rail]"); if (!r) return false; r.scrollTop = r.scrollHeight; return true; })],
  ["filter-open", async (p) => { await p.evaluate(() => { const r = document.querySelector("[data-tq-rail]"); if (r) r.scrollTop = 0; }); return click(p, "[data-tq-filter]"); }],
  ["timeline", async (p) => { await p.keyboard.press("Escape"); await wait(300); return clickText(p, "Timeline", "[aria-label='Feed views'] button"); }],
  ["work", async (p) => clickText(p, "Work", "[aria-label='Feed views'] button")],
  ["section-later", async (p) => click(p, '[data-tq-section-head="later"]'), "walk"],
  ["section-fyi", async (p) => click(p, '[data-tq-section-head="fyi"]'), "walk"],
  ["walk-start", async (p) => first(() => clickText(p, "Walk me through my tasks"), () => click(p, "[data-tq-walk-start]")), "walk"],
  ["walk-next-1", async (p) => first(() => click(p, "[data-tq-next]"), () => clickText(p, "Next")), "walk"],
  ["walk-next-2", async (p) => first(() => click(p, "[data-tq-next]"), () => clickText(p, "Next")), "walk"],
  ["walk-next-3", async (p) => first(() => click(p, "[data-tq-next]"), () => clickText(p, "Next")), "walk"],
  ["expand", async (p) => click(p, "[data-tq-expand]"), "client"],
  ["collapse", async (p) => click(p, "[data-tq-expand]"), "client"],
  ["fold-open", async (p) => click(p, "[data-tq-folded]"), "walk"],
  ["row-click", async (p) => first(() => click(p, "[data-tq-rail] [data-tq-row]", 2), () => click(p, "[data-tq-rail] .tq-pile-row", 2)), "walk"],
  ["agent-row", async (p) => p.evaluate(() => {
    const row = [...document.querySelectorAll("[data-tq-rail] .tq-pile-row .card")].find((c) => /agent waiting|👋/.test(c.title || c.textContent));
    if (!row) return false; row.click(); return true; }), "walk"],
  ["agent-expand", async (p) => click(p, "[data-tq-expand]"), "client"],
  ["agent-collapse", async (p) => click(p, "[data-tq-expand]"), "client"],
  ["nav-new", async (p) => click(p, '[data-tq-nav="new"]')],
  ["nav-reports", async (p) => { await p.keyboard.press("Escape"); return first(() => click(p, '[data-tq-nav="reports"]'), () => tab(p, "Reports")); }],
  ["browse-open-report", async (p) => click(p, "[data-tq-browse-card]"), "client"],
  ["browse-back-reports", async (p) => click(p, "[data-tq-browse-back]"), "client"],
  ["nav-connections", async (p) => first(() => click(p, '[data-tq-nav="connections"]'), () => tab(p, "Connections"))],
  ["browse-section", async (p) => click(p, "[data-tq-browse-chip]", 1), "client"],
  ["browse-one", async (p) => click(p, "[data-tq-browse-card]"), "client"],
  ["browse-back", async (p) => click(p, "[data-tq-browse-back]"), "client"],
  ["nav-settings", async (p) => first(() => click(p, '[data-tq-nav="settings"]'), () => tab(p, "Settings"))],
  ["settings-group", async (p) => click(p, "[data-tq-browse-chip]", 2), "client"],
  ["nav-hub", async (p) => first(() => click(p, '[data-tq-nav="hub"]'), () => tab(p, "Hub"))],
  ["tasks-tab", async (p) => (await tab(p, "Tasks")) && (await wait(1500), first(() => click(p, "[data-tq-task-row]"), () => visible(p, "[data-tq-task-page]")))],
  ["board", async (p) => tab(p, "Board")],
];

(async () => {
  const browser = await launch();
  const facts = [];
  for (const w of [1440, 390]) {
    const page = await browser.newPage();
    await page.setViewport(VIEWS[w]);
    const pileHits = [];
    page.on("request", (r) => { if (r.url().includes("/api/funnel/pile")) pileHits.push(Date.now()); });
    page.on("pageerror", (e) => facts.push({ w, error: String(e.message || e).slice(0, 300) }));
    await page.goto(url, { waitUntil: "load" });
    await wait(4500);
    // the first-run sheet and the demo's own greeter are not the page under test
    await page.evaluate(() => document.querySelectorAll(".MuiDialog-root").forEach((d) => d.remove()));
    for (const [name, step, kind] of SCENES) {
      if (only && !only.split(",").includes(name)) continue;
      if (w === 390 && /^(rail|filter|timeline|work|section|row)/.test(name)) await openRail(page);
      const before = pileHits.length;
      let ok = false;
      try { ok = await step(page, w); } catch (e) { ok = false; }
      if (!ok) { facts.push({ w, name, skipped: true }); continue; }
      await wait(kind === "walk" ? 3500 : 1200);
      await hush(page);
      const file = path.join(outdir, `${label}-${w}-${name}.png`);
      await page.screenshot({ path: file });
      const f = await page.evaluate(() => ({
        hscroll: document.documentElement.scrollWidth > window.innerWidth + 1,
        xterm: [...document.querySelectorAll(".xterm")].filter((x) => x.getBoundingClientRect().width > 0)
          .map((x) => { const r = x.getBoundingClientRect(); return [Math.round(r.width), Math.round(r.height)]; }),
        taskPages: document.querySelectorAll("[data-tq-task-page]").length,
        broken: document.body.innerText.includes("failed to draw") ? (document.querySelector("pre, code")?.textContent || "").slice(0, 160) : "",
      }));
      const pileFetched = pileHits.length > before;
      facts.push({ w, name, file: path.basename(file), ...f, pileFetched, clientOnlyViolated: kind === "client" && pileFetched });
      if (f.broken) console.log(`${w} ${name}: BROKEN PAGE - ${f.broken}`);
      console.log(`${w} ${name}: hscroll=${f.hscroll} xterm=${JSON.stringify(f.xterm)} pages=${f.taskPages} pile=${pileFetched}${kind === "client" && pileFetched ? "  <-- CLIENT STEP FETCHED THE PILE" : ""}`);
    }
    await page.close();
  }
  fs.writeFileSync(path.join(outdir, `${label}-facts.json`), JSON.stringify(facts, null, 1));
  await browser.close();
})();
