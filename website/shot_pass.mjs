// A visual pass over the live pane and the Assistant walk, at a desktop and a phone viewport:
//   BROWSER_EXE=<chrome> node website/shot_pass.mjs <url-with-?token=> <outdir> <label> [desktop|mobile] [steps]
// Shoots the Board, the Tasks workspace of the first task (its pane open), and the Assistant tab,
// pressing Next `steps` times on the walk with a shot after each. Hides the hand-raise toasts.
import fs from "node:fs";
import path from "node:path";
import puppeteer from "puppeteer-core";

const EXE = process.env.BROWSER_EXE || "C:/Program Files/Google/Chrome/Application/chrome.exe";
const [url, outdir, label = "shot", mode = "desktop", stepsArg = "3"] = process.argv.slice(2);
fs.mkdirSync(outdir, { recursive: true });
const VIEW = mode === "mobile" ? { width: 390, height: 844, isMobile: true, hasTouch: true, deviceScaleFactor: 2 } : { width: 1440, height: 900, deviceScaleFactor: 1 };
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const shots = [];

const pills = (page) => page.evaluate(() => [...document.querySelectorAll("#tqTopNav *")]
  .filter((e) => e.childElementCount === 0 && e.getBoundingClientRect().width > 0).map((e) => e.textContent.trim()).filter(Boolean));
const clickTab = async (page, label) => {
  const desktop = await page.evaluate((l) => {
    const norm = (x) => x.replace(/\s+/g, " ").trim();
    const els = [...document.querySelectorAll("#tqTopNav *")].filter((e) => e.getBoundingClientRect().width > 0 && norm(e.textContent).startsWith(l) && e.childElementCount <= 3 && !e.closest(".MuiSelect-select"));
    const el = els.sort((a, b) => a.textContent.length - b.textContent.length)[0];
    if (!el) return false; el.click(); return true;
  }, label);
  if (desktop) return true;
  // the phone keeps its pages behind one labelled selector (TaskHubPage: "Taskuary page")
  const opened = await page.evaluate(() => { const s = document.querySelector("#tqTopNav .MuiSelect-select"); if (!s) return false; s.dispatchEvent(new MouseEvent("mousedown", { bubbles: true })); return true; });
  if (!opened) return false;
  await wait(600);
  const picked = await page.evaluate((l) => {
    const want = l === "Assistant" ? "Taskuary" : l;
    const it = [...document.querySelectorAll('li[role="option"]')].find((e) => e.textContent.replace(/\s+/g, " ").trim().replace(/^✦ /, "").startsWith(want));
    if (!it) return false; it.click(); return true;
  }, label);
  await wait(300);
  return picked;
};
const clickText = (page, label, tags = "button,[role=button],div,span,a,p") => page.evaluate((l, t) => {
  const norm = (x) => x.replace(/\s+/g, " ").trim();
  const els = [...document.querySelectorAll(t)].filter((d) => d.childElementCount <= 3 && norm(d.textContent) === l && d.getBoundingClientRect().width > 0);
  const el = els.sort((a, b) => a.textContent.length - b.textContent.length)[0];
  if (!el) return false; el.click(); return true;
}, label, tags);
const hush = (page) => page.evaluate(() => { document.querySelectorAll(".MuiSnackbar-root").forEach((e) => (e.style.display = "none")); });
async function shot(page, name) {
  await hush(page);
  const file = path.join(outdir, `${label}-${mode}-${name}.png`);
  await page.screenshot({ path: file, fullPage: false });
  const facts = await page.evaluate(() => ({
    hscroll: document.documentElement.scrollWidth > window.innerWidth + 1,
    xterm: [...document.querySelectorAll(".xterm")].map((x) => { const r = x.getBoundingClientRect(); const rows = x.querySelector(".xterm-rows"); return { w: Math.round(r.width), h: Math.round(r.height), rows: rows ? rows.children.length : 0, rowH: rows && rows.children[0] ? Math.round(rows.children[0].getBoundingClientRect().height * 10) / 10 : 0 }; }),
    errors: window.__tqErrors || [],
  }));
  shots.push({ name, file, ...facts });
  console.log(`  shot ${name}: hscroll=${facts.hscroll} xterm=${JSON.stringify(facts.xterm)}`);
}

(async () => {
  const browser = await puppeteer.launch({ executablePath: EXE, headless: "new", args: ["--no-sandbox"] });
  const page = await browser.newPage();
  await page.setViewport(VIEW);
  page.on("pageerror", (e) => console.log("  PAGE ERROR:", String(e).slice(0, 200)));
  page.on("console", (m) => { if (m.type() === "error") console.log("  CONSOLE ERROR:", m.text().slice(0, 200)); });
  await page.goto(url, { waitUntil: "load" });
  await wait(2500);
  // the first-run "Five things left" sheet stands over every tab of a fresh home
  if (await clickText(page, "Put it away", "button")) { await wait(800); console.log("  setup sheet put away"); }
  console.log("tabs:", JSON.stringify(await pills(page)));
  // ── Board
  if (await clickTab(page, "Board")) {
    await wait(2500); await shot(page, "board");
    // the Wall: every live session as a cell, the narrowest pty surface on the desktop
    if (await clickText(page, "Wall", "button,span,div")) { await wait(3500); await shot(page, "wall"); }
  }
  // ── Tasks: first task, its workspace with the pane
  if (await clickTab(page, "Tasks")) {
    await wait(2000);
    const opened = await page.evaluate(() => {
      const row = [...document.querySelectorAll("[data-task-id], .tq-task-row, tr, li, div")].find((e) => /TQ-0001/.test(e.textContent) && e.getBoundingClientRect().width > 0 && e.childElementCount > 0 && e.textContent.length < 400);
      if (!row) return false; row.click(); return true;
    });
    await wait(3500); await shot(page, "task-workspace");
    console.log("  task row opened:", opened);
  }
  // ── Assistant walk, stepping
  if (await clickTab(page, "Assistant")) {
    await wait(3000); await shot(page, "walk-0-opening");
    // the opening offers the walk; the walk offers Next
    const started = await clickText(page, "Walk me through my tasks", "button");
    await wait(4000); await shot(page, "walk-1");
    console.log("  walk started:", started);
    const steps = parseInt(stepsArg, 10) || 0;
    for (let i = 2; i <= steps + 1; i++) {
      const ok = (await clickText(page, "Next", "button")) || (await clickText(page, "Next"));
      await wait(2500); await shot(page, `walk-${i}`);
      console.log(`  next pressed: ${ok}`);
      // an agent card offers its screen: the pane inside the walk is the other pty surface
      if (await clickText(page, "Show the screen", "button,span,div")) { await wait(3000); await shot(page, `walk-${i}-screen`); console.log("  screen shown"); }
    }
  }
  fs.writeFileSync(path.join(outdir, `${label}-${mode}-facts.json`), JSON.stringify(shots, null, 2));
  await browser.close();
})().catch((e) => { console.error(e); process.exit(1); });
