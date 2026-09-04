// Frames for the README hero GIF: the Assistant doing its actual job - the pipe ranked by
// triage beside the chat, a mail pulled in with its drafted reply waiting on you, the whole
// Timeline in task mode with a scheduled report open, then the Reports and the Board. Writes numbered PNGs plus a manifest of per-frame delays; hero_gif.py turns
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

// ── 1. the Assistant: the pipe, ranked, beside the chat ───────────────────
await wait(2200);
await hold(2200);

// ── 2. a mail pulled into the chat: what it is, and the drafted reply waiting on you ──
await p.evaluate(() => [...document.querySelectorAll(".tq-pile-row .card")].find((c) => /AP cutover/i.test(c.textContent))?.click());
await burst(140, 6);                    // the row slides up to CURRENT, the card lands in the chat
await wait(2200); await burst(120, 3); await hold(3000);

// ── 3. the whole Timeline, in task mode: a scheduled report, whole ────────
await click("all"); await wait(900);
await p.evaluate(() => [...document.querySelectorAll(".tq-stage-mode button")].find((x) => x.textContent === "Task")?.click());
await wait(500); await hold(1600);
await clickRow("Headcount by site");
await burst(110, 6);
await wait(1000); await hold(3000);

// ── 4. the reports tab: where the pipeline is built ───────────────────────
await click("Reports"); await burst(130, 4); await wait(700); await hold(2400);

// ── 5. the board: agents working, and the note one left the next ──────────
await click("Board"); await burst(130, 4); await wait(700); await hold(2600);

// ── 6. back where you started ─────────────────────────────────────────────
await click("Assistant"); await wait(1600); await hold(1800);

writeFileSync(`${OUT}/frames.json`, JSON.stringify({ width: W, height: H, frames }, null, 1));
await b.close();
console.log(`captured ${frames.length} frames -> ${OUT}`);
