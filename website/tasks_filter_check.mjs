// Does clicking a task's state chip on the Tasks page narrow In progress, and does its pill bring the rest back?
//
//   node website/tasks_filter_check.mjs <url> <outdir>     # against a `taskuary --demo --port N` server
//
// Exits 1 with what it saw when the list did not narrow or did not come back.
import { launch } from "./browser.mjs";

const url = process.argv[2] || "http://127.0.0.1:7913/";
const out = process.argv[3] || ".";
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const chips = (page) => page.evaluate(() => [...document.querySelectorAll('[role="button"][title^="Show"] .MuiChip-label')]
  .map((c) => c.textContent.replace(/^\S+\s(?=[a-z])/, "").trim()));

const browser = await launch();
const page = await browser.newPage(); await page.setViewport({ width: 1440, height: 980 });
let bad = 0;
try {
  await page.goto(url, { waitUntil: "networkidle2" }); await wait(2500);
  // the top bar's tabs are plain elements: click the smallest one whose own text is "Tasks"
  await page.evaluate(() => [...document.querySelectorAll("body *")].filter((x) => /^Tasks\d*$/.test(x.textContent.trim()))
    .sort((a, b) => a.textContent.length - b.textContent.length || b.querySelectorAll("*").length - a.querySelectorAll("*").length)[0]?.click());
  await wait(2500);
  const before = await chips(page);
  const word = before.find((w, i) => before.indexOf(w) === i && before.some((x) => x !== w)) || before[0];
  if (!word) { console.log("no task rows with a state chip"); process.exit(2); }
  await page.screenshot({ path: `${out}/tasks-before.png` });
  // the pill on top, not the chip on the row: the row of states is what the owner looks for
  await page.evaluate((w) => [...document.querySelectorAll(".tq-tasks-states div")].filter((b) => b.textContent.startsWith(w)).sort((a, b) => a.textContent.length - b.textContent.length)[0]?.click(), word);
  await wait(800);
  const after = await chips(page);
  const pill = await page.evaluate(() => document.querySelector(".tq-tasks-states")?.textContent || null);
  await page.screenshot({ path: `${out}/tasks-filtered.png` });
  console.log("clicked", JSON.stringify(word), "rows", before.length, "->", after.length, "pill", JSON.stringify(pill));
  if (!after.length || after.some((w) => w !== word) || !pill?.includes(word)) { console.log("DID NOT NARROW", after); bad = 1; }
  await page.evaluate(() => [...document.querySelectorAll(".tq-tasks-states div")].filter((b) => /^all\d*$/.test(b.textContent)).sort((a, b) => a.textContent.length - b.textContent.length)[0]?.click()); await wait(800);
  const back = await chips(page);
  console.log("cleared -> rows", back.length);
  if (back.length !== before.length) { console.log("DID NOT COME BACK", back); bad = 1; }
} finally { await browser.close(); }
process.exit(bad);
