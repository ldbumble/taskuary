// Frames for the README hero GIF: the funnel doing its actual job - a mail arriving,
// triage's verdict, the drafted reply waiting on you, then a scheduled report landing with
// its chart. Writes numbered PNGs plus a manifest of per-frame delays; hero_gif.py turns
// them into the GIF (no ffmpeg on this box, and Pillow writes GIFs fine).
//
//   node hero_frames.mjs http://127.0.0.1:PORT
import { mkdirSync, rmSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { launch } from "./browser.mjs";

const OUT = fileURLToPath(new URL("./_hero", import.meta.url));
rmSync(OUT, { recursive: true, force: true });
mkdirSync(OUT, { recursive: true });

const W = 1440, H = 860;
const b = await launch();
const p = await b.newPage();
await p.setViewport({ width: W, height: H, deviceScaleFactor: 1 });
await p.goto(process.argv[2], { waitUntil: "networkidle0" });

const frames = [];
let n = 0;
const shot = async (delay) => {
  const f = `f${String(n++).padStart(3, "0")}.png`;
  await p.screenshot({ path: `${OUT}/${f}` });
  frames.push({ file: f, delay });
};
// a burst during a transition is what makes it read as motion rather than slides
const burst = async (ms, count, each = 90) => {
  for (let i = 0; i < count; i++) { await shot(each); await new Promise((r) => setTimeout(r, ms)); }
};
const hold = async (ms) => { await shot(ms); };
const click = async (text) => p.evaluate((t) => [...document.querySelectorAll("*")]
  .find((d) => d.childElementCount === 0 && d.textContent.trim() === t)?.click(), text);
const clickRow = async (needle) => p.evaluate((nd) => {
  const rows = [...document.querySelectorAll("div")].filter((d) => d.textContent.includes(nd) && d.className.includes("Mui"));
  rows[rows.length - 1]?.click();
}, needle);
const wait = (ms) => new Promise((r) => setTimeout(r, ms));

// ── 1. the timeline: everything in one funnel ─────────────────────────────
await click("Timeline"); await wait(2200);
await hold(2000);

// ── 2. a mail: the verdict, the thread, the drafted reply ─────────────────
await clickRow("Q3 vendor spend");
await burst(110, 7);                    // the review canvas growing out of the row
await wait(900); await hold(2600);
// down to the draft itself - the thing you approve
await p.evaluate(() => {
  const box = [...document.querySelectorAll("div")].find((d) => d.scrollHeight > d.clientHeight + 80
    && d.getBoundingClientRect().left > 700);
  if (box) box.scrollTop = box.scrollHeight;
});
await burst(120, 4); await hold(2800);

// ── 3. a scheduled report: rows, chart, spreadsheet ───────────────────────
await clickRow("Nightly census — 6 rows");
await burst(110, 6);
await wait(1000); await hold(3000);

// ── 4. the reports tab: where the pipeline is built ───────────────────────
await click("Reports"); await burst(130, 4); await wait(700); await hold(2400);

// ── 5. the board: agents working, and the note one left the next ──────────
await click("Board"); await burst(130, 4); await wait(700); await hold(2600);

// ── 6. back where you started ─────────────────────────────────────────────
await click("Timeline"); await wait(1600); await hold(1800);

writeFileSync(`${OUT}/frames.json`, JSON.stringify({ width: W, height: H, frames }, null, 1));
await b.close();
console.log(`captured ${frames.length} frames -> ${OUT}`);
