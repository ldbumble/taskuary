// Does the timestamp still sit INSIDE the task row? The Tasks rail's header line is one flex row -
// ref, lifecycle, state, "interrupted", the agent - and MUI chips cannot shrink (their label is
// nowrap, so min-width:auto is the whole label). Four chips on a narrow rail pushed "18h ago" past
// the card's right edge, where the rail's own overflow clipped it (the owner, 2026-09-09: "hours
// ago is getting pushed off the task").
//
//   node website/task_row_geometry_check.mjs <url> [width]   # any running server, --demo or live
//
// Read-only: it opens the Tasks tab and measures. Exits 1 naming every row whose time is clipped,
// 2 when there was no row to measure.
import { launch } from "./browser.mjs";

const url = process.argv[2] || "http://127.0.0.1:7787/";
const SLACK = 1;                                          // px: subpixel rounding
const wait = (ms) => new Promise((r) => setTimeout(r, ms));

const openTasks = (page) => page.evaluate(() => {
  const tab = [...document.querySelectorAll("div,button,span")].find((e) => e.childElementCount <= 2 && e.textContent.trim() === "Tasks");
  if (!tab) return "no Tasks tab on the page"; tab.click(); return "";
});

// every task row: the card, and the "3h ago" caption that must stay within it
const rows = (page) => page.evaluate(() => [...document.querySelectorAll("[data-tq-task-row]")].map((card) => {
  const time = card.querySelector("[data-tq-task-age]");
  const c = card.getBoundingClientRect(), t = time?.getBoundingClientRect();
  return { ref: card.querySelector("[data-tq-task-ref]")?.textContent || "?", age: time?.textContent || "",
    cardRight: c.right, timeRight: t?.right ?? null, timeWidth: t?.width ?? null };
}));

const browser = await launch();
const page = await browser.newPage(); await page.setViewport({ width: +(process.argv[3] || 1280), height: 900 });
try {
  // a server with [server].token set answers the dev-proxy page 401 until the page carries it
  if (process.env.TASKUARY_TOKEN) {
    await page.goto(url); await page.evaluate((t) => localStorage.setItem("taskuary_token", t), process.env.TASKUARY_TOKEN);
  }
  await page.goto(url, { waitUntil: "networkidle2" });
  await wait(1500);
  const err = await openTasks(page); if (err) { console.error(err); process.exit(2); }
  await wait(2500);
  const found = await rows(page);
  if (!found.length) { console.error("no task rows to measure"); process.exit(2); }
  const bad = found.filter((r) => r.timeRight === null || r.timeRight > r.cardRight + SLACK);
  for (const r of bad) console.log(`${r.ref} "${r.age}" spills ${(r.timeRight - r.cardRight).toFixed(1)}px past the card`);
  console.log(`${found.length} rows measured, ${bad.length} clipped`);
  process.exit(bad.length ? 1 : 0);
} finally { await browser.close(); }
