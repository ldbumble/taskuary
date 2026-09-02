// Fine-tooth-comb UI walk: every tab, every sub-view, the drawer's five tabs, a connector card, the
// Docs shelf, every Settings page - at a desktop and a phone viewport - collecting page errors,
// console errors, horizontal overflow, invisible/clipped controls, and a screenshot of each stop.
//   node website/ui_audit.mjs <url> <outdir> [desktop|mobile]
// Run against the static demo bundle (VITE_DEMO=1 build, served) or a real `--demo` server.
import fs from "node:fs";
import path from "node:path";
import puppeteer from "puppeteer-core";

const EDGE = "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
const [url, outdir, mode = "desktop"] = process.argv.slice(2);
fs.mkdirSync(outdir, { recursive: true });
const VIEW = mode === "mobile" ? { width: 390, height: 844, isMobile: true, hasTouch: true, deviceScaleFactor: 2 }
  : { width: 1440, height: 900 };
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const findings = [];
const note = (where, what, detail = "") => findings.push({ where, what, detail });

const clickText = (page, label, tags = "div,span,button,a,p") => page.evaluate((l, t) => {
  const norm = (x) => x.replace(/\s+/g, " ").trim();
  // a tab may carry a mark after its label: "Review2", "Agentlive", "Agentchat", "Replywaiting"
  const els = [...document.querySelectorAll(t)].filter((d) => d.childElementCount <= 3 && (norm(d.textContent) === l || norm(d.textContent).startsWith(l + " ")
    || /^(\d+|live|chat|done|waiting|open|replied)$/.test(norm(d.textContent).slice(l.length)) && norm(d.textContent).startsWith(l)));
  const el = els.find((e) => e.offsetParent !== null) || els[0];
  if (!el) return false;
  el.click(); return true;
}, label, tags);

// what a human would notice without reading anything
const inspect = (page) => page.evaluate(() => {
  const out = {};
  out.hscroll = document.documentElement.scrollWidth > window.innerWidth + 1;
  out.scrollWidth = document.documentElement.scrollWidth; out.innerWidth = window.innerWidth;
  // controls cut off at the right edge of the viewport
  const vw = window.innerWidth;
  out.clipped = [...document.querySelectorAll("button,[role=button],input,select,textarea")]
    .filter((e) => e.offsetParent !== null && !e.classList.contains("MuiSwitch-input"))   // a switch's hidden input is 3x its track by design
    .map((e) => ({ r: e.getBoundingClientRect(), t: (e.getAttribute("aria-label") || e.textContent || e.placeholder || e.tagName).trim().slice(0, 40) }))
    .filter(({ r }) => r.width > 0 && (r.right > vw + 2 || r.left < -2))
    .map(({ t, r }) => `${t} (${Math.round(r.left)}..${Math.round(r.right)})`).slice(0, 8);
  // text that overflows its box (ellipsis is fine; real overflow is not)
  out.overflowing = [...document.querySelectorAll("p,span,div")].filter((e) => {
    if (e.children.length || !e.textContent.trim() || e.offsetParent === null) return false;
    const cs = getComputedStyle(e);
    return cs.overflow === "visible" && cs.whiteSpace !== "nowrap" && e.scrollWidth > e.clientWidth + 4 && e.clientWidth > 0;
  }).map((e) => e.textContent.trim().slice(0, 50)).slice(0, 6);
  // tiny tap targets on a phone
  out.tinyTargets = window.innerWidth < 500 ? [...document.querySelectorAll("button,[role=button],a")]
    .filter((e) => e.offsetParent !== null)
    .map((e) => ({ r: e.getBoundingClientRect(), t: (e.getAttribute("aria-label") || e.textContent || e.tagName).trim().slice(0, 30) }))
    .filter(({ r }) => r.width > 0 && r.height > 0 && (r.width < 28 || r.height < 28))
    .map(({ t, r }) => `${t} ${Math.round(r.width)}x${Math.round(r.height)}`).slice(0, 10) : [];
  out.bodyText = document.body.innerText.length;
  return out;
});

(async () => {
  const browser = await puppeteer.launch({ executablePath: EDGE, headless: "new" });
  const page = await browser.newPage();
  await page.setViewport(VIEW);
  const errors = [];
  page.on("pageerror", (e) => errors.push(`pageerror: ${e.message}`));
  page.on("console", (m) => m.type() === "error" && !/favicon|net::ERR_/.test(m.text()) && errors.push(`console: ${m.text().slice(0, 200)}`));
  // a live server never goes network-idle (websockets, polls): settle on load and a beat
  try { await page.goto(url, { waitUntil: "networkidle0", timeout: 15000 }); }
  catch { await page.goto(url, { waitUntil: "load", timeout: 45000 }); }
  await wait(1200);

  let n = 0;
  const stop = async (name) => {
    await wait(700);
    const i = await inspect(page);
    const file = path.join(outdir, `${String(++n).padStart(2, "0")}-${mode}-${name.replace(/[^a-z0-9]+/gi, "_")}.png`);
    await page.screenshot({ path: file, fullPage: false });
    if (i.hscroll) note(name, "page scrolls horizontally", `${i.scrollWidth} > ${i.innerWidth}`);
    if (i.clipped.length) note(name, "control clipped at viewport edge", i.clipped.join("; "));
    if (i.overflowing.length) note(name, "text overflows its box", i.overflowing.join(" | "));
    if (i.tinyTargets.length) note(name, "tap target under 28px", i.tinyTargets.join("; "));
    if (i.bodyText < 40) note(name, "page nearly empty", `${i.bodyText} chars of text`);
    while (errors.length) note(name, "script error", errors.shift());
    return file;
  };

  // ── top-level tabs ──────────────────────────────────────────────────────────────────────
  const TABS = ["Timeline", "Board", "Tasks", "Review", "Reports", "Social", "Connections", "Docs", "Settings"];
  const openTab = async (t) => {
    let ok = await clickText(page, t);
    if (!ok && mode === "mobile") {
      // the phone keeps its tabs behind a menu button; try the common affordances
      for (const sel of ['[aria-label="menu"]', '[aria-label="Menu"]', '[aria-label="tabs"]', 'button[aria-haspopup]']) {
        const b = await page.$(sel); if (b) { await b.click(); await wait(400); ok = await clickText(page, t); if (ok) break; }
      }
    }
    if (!ok) note(t, "tab not reachable", "no clickable element with that label");
    await wait(900);
    return ok;
  };

  // Timeline: the list, a row, and each drawer tab
  await openTab("Timeline"); await stop("timeline");
  const rowBox = await page.evaluate(() => {
    // the state word sits at the right end of every row card; the row itself is to its left
    // the word rides with its mark in one span ("👋agent waving"), so allow the emoji child
    const word = [...document.querySelectorAll("span,div,p")].find((d) => d.childElementCount <= 1 && d.offsetParent !== null
      && /(agent waving|reply ready|on your list|agent working)$/.test(d.textContent.trim()) && d.textContent.trim().length < 24
      && d.getBoundingClientRect().top > 120);
    if (!word) return null;
    const r = word.getBoundingClientRect();
    return { x: Math.max(60, r.left - 100), y: r.top + r.height / 2 };
  });
  let rowOpened = false;
  if (rowBox) {
    // desktop rows open on hover then pin on click; a phone taps
    if (mode === "mobile") await page.touchscreen.tap(rowBox.x, rowBox.y);
    else { await page.mouse.move(rowBox.x, rowBox.y); await wait(400); await page.mouse.click(rowBox.x, rowBox.y); }
    rowOpened = true;
  }
  if (rowOpened) {
    await wait(900); await stop("timeline-row-open");
    for (const t of ["Summary", "Message", "Triage", "Agent", "Reply"]) {
      const ok = await clickText(page, t);
      if (!ok) note(`drawer ${t}`, "drawer tab not found");
      await stop(`drawer-${t.toLowerCase()}`);
    }
  } else note("timeline", "no task row to open", "");
  // needs-me segment and the + New dialog
  if (await clickText(page, "needs me")) await stop("timeline-needs-me");
  if (await clickText(page, "New")) { await stop("timeline-new-dialog"); await page.keyboard.press("Escape"); await wait(300); }

  // Board and its four views
  await openTab("Board"); await stop("board-columns");
  for (const v of ["Studio", "Wall", "Live handoffs"]) { if (await clickText(page, v)) await stop(`board-${v.toLowerCase().replace(/ /g, "-")}`); else note("board", `view pill '${v}' missing`); }

  // Tasks: list + first task
  await openTab("Tasks"); await stop("tasks");
  await page.evaluate(() => { const r = [...document.querySelectorAll("div")].find((d) => /^TQ-\d{4}$/.test(d.textContent.trim()) && d.offsetParent !== null); if (r) r.click(); });
  await stop("tasks-selected");

  await openTab("Review"); await stop("review");
  await openTab("Reports"); await stop("reports");
  await openTab("Social"); await stop("social");

  // Connections: the catalog and one Corporate card
  await openTab("Connections"); await stop("connections");
  await clickText(page, "Corporate systems"); await wait(600);
  if (await clickText(page, "Sage Intacct")) { await stop("connections-intacct"); for (const t of ["Guide", "Agent"]) { if (await clickText(page, t)) await stop(`connections-intacct-${t.toLowerCase()}`); } }
  else note("connections", "Sage Intacct card not found");

  // Docs: each document and the Playbooks shelf
  await openTab("Docs"); await stop("docs");
  for (const d of ["TRIAGE.md", "STYLE.md", "CODER.md", "LEARNED.md"]) { if (await clickText(page, d)) await stop(`docs-${d.toLowerCase().replace(".md", "")}`); }
  if (await clickText(page, "New playbook") || await clickText(page, "Write the first playbook")) await stop("docs-new-playbook");
  else note("docs", "Playbooks shelf has no New button");

  // Settings: every page
  await openTab("Settings"); await stop("settings");
  for (const p of ["Configuration", "Routing policies", "Verdicts & notes", "Agents", "Audit integrity", "Updates", "About you"]) {
    if (await clickText(page, p)) await stop(`settings-${p.toLowerCase().replace(/[^a-z]+/g, "-")}`); else note("settings", `page '${p}' not found`);
  }

  fs.writeFileSync(path.join(outdir, `findings-${mode}.json`), JSON.stringify(findings, null, 2));
  console.log(`${mode}: ${n} stops, ${findings.length} findings -> ${outdir}`);
  for (const f of findings) console.log(`  [${f.where}] ${f.what}${f.detail ? ": " + f.detail : ""}`);
  await browser.close();
})().catch((e) => { console.error(e.stack || e.message); process.exit(1); });
