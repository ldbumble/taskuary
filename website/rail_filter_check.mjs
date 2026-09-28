// Does clicking a row's state word filter its band, and does the heading's ✕ bring the rest back?
//
//   node website/rail_filter_check.mjs <url> <outdir>     # against a `taskuary --demo --port N` server
//
// Exits 1 with what it saw when the band did not narrow or did not come back.
import { launch } from "./browser.mjs";

const url = process.argv[2] || "http://127.0.0.1:7913/";
const out = process.argv[3] || ".";
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const bands = (page) => page.evaluate(() => [...document.querySelectorAll(".tq-pile-band")].map((b) => ({
  level: b.dataset.tqRun, n: b.querySelectorAll(".tq-pile-row").length,
  words: [...b.querySelectorAll(".tq-pile-row .tq-pile-word, .tq-pile-row .tq-pile-tag.loud")].map((w) => w.textContent.trim()),
  only: b.querySelector(".tq-pile-only")?.textContent || null })));

const browser = await launch();
const page = await browser.newPage(); await page.setViewport({ width: 1440, height: 980 });
let bad = 0;
try {
  await page.goto(url, { waitUntil: "networkidle2" }); await wait(2500);
  await page.evaluate(() => [...document.querySelectorAll("button, a, [role=tab]")].find((x) => x.textContent.trim() === "Assistant")?.click());
  await wait(3000);
  const before = await bands(page);
  const band = before.find((b) => new Set(b.words).size > 1) || before.find((b) => b.words.length);
  if (!band) { console.log("no row carries a state word", before); process.exit(2); }
  const word = band.words[0];
  await page.screenshot({ path: `${out}/rail-before.png` });
  await page.evaluate((lvl, w) => [...document.querySelectorAll(`.tq-pile-band[data-tq-run="${lvl}"] .tq-pile-word, .tq-pile-band[data-tq-run="${lvl}"] .tq-pile-tag.loud`)]
    .find((x) => x.textContent.trim() === w)?.click(), band.level, word);
  await wait(800);
  const after = (await bands(page)).find((b) => b.level === band.level);
  await page.screenshot({ path: `${out}/rail-filtered.png` });
  const narrowed = after && after.words.every((w) => w === word) && after.only?.includes(word.replace(/^\S+\s/, "").trim().slice(0, 6));
  console.log("band", band.level, "clicked", JSON.stringify(word), "rows", band.n, "->", after?.n, "heading", JSON.stringify(after?.only));
  if (!narrowed || after.n > band.n) { console.log("DID NOT NARROW", after); bad = 1; }
  await page.evaluate(() => document.querySelector(".tq-pile-only")?.click()); await wait(800);
  const back = (await bands(page)).find((b) => b.level === band.level);
  console.log("cleared -> rows", back?.n, "heading", JSON.stringify(back?.only));
  if (!back || back.n !== band.n || back.only) { console.log("DID NOT COME BACK", back); bad = 1; }
} finally { await browser.close(); }
process.exit(bad);
