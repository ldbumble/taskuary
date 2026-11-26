// THE CHIP ON A PROMPT BOX, DRAWN AND MEASURED (not a test: nothing here runs in CI). node browser/chips.mjs <out folder>
// The owner, 2026-11-25 and again 11-26: "the blue pill does not match the words". Every place that draws the chip, on the stage
// (browser/onecard-preview.html?chips=1), shot at a desk, a small laptop, a phone and a side panel - and each pill measured against its own words:
// `slack` is pill past an uncut name, `spill` is words past the pill, `clipped` is a pill the row cut off without its round end. All three are 0.
import path from "node:path";
import { mkdir, writeFile } from "node:fs/promises";
import { startHarness } from "./harness.mjs";

const OUT = process.argv[2] || path.resolve("chips-out");
const SHOTS = [["desk-1440", 1440, 0], ["laptop-1024", 1024, 0], ["phone-390", 390, 0], ["panel-360", 1440, 360], ["panel-280", 1440, 280]];
const h = await startHarness({ fresh: true }), said = [];
try {
  await mkdir(OUT, { recursive: true });
  const page = await h.newPage();
  for (const [name, vw, w] of SHOTS) {
    await page.setViewport({ width: vw, height: 700, deviceScaleFactor: 2 });
    await page.goto(`${h.ui}/browser/onecard-preview.html?chips=1${w ? `&w=${w}` : ""}`, { waitUntil: "domcontentloaded" });
    await page.waitForSelector("[data-tq-chip-stage] .tq-attach-chip", { visible: true, timeout: 60000 });
    await page.evaluate(() => document.fonts.ready);
    await (await page.$("[data-tq-chip-stage]")).screenshot({ path: path.join(OUT, `${name}.png`) });
    const rows = await page.evaluate(() => [...document.querySelectorAll("[data-tq-chip-case]")].flatMap((box) => [...box.querySelectorAll(".tq-attach-chip")].map((c) => {
      const kids = [...c.children], span = kids.find((k) => k.tagName === "SPAN"), r = c.getBoundingClientRect(), s = span.getBoundingClientRect();
      const range = document.createRange(); range.selectNodeContents(span);
      const words = range.getBoundingClientRect().width, cut = span.scrollWidth > span.clientWidth, row = c.closest("[data-tq-attach-row]")?.getBoundingClientRect();
      const pad = (k) => parseFloat(getComputedStyle(c)[k]), inner = kids.reduce((n, k) => n + k.getBoundingClientRect().width, 0) + (kids.length - 1) * parseFloat(getComputedStyle(c).columnGap || 0);
      return { at: box.dataset.tqChipCase, name: span.textContent.slice(0, 28), w: Math.round(r.width), cut, slack: Math.round(Math.max(0, cut ? 0 : s.width - words) + Math.max(0, r.width - inner - pad("paddingLeft") - pad("paddingRight") - 2)),
        spill: Math.round(Math.max(0, s.right - r.right, cut ? 0 : words - s.width)), clipped: Math.round(Math.max(0, r.right - (row || c.parentElement.getBoundingClientRect()).right)) };
    })));
    const bad = rows.filter((x) => x.slack > 1 || x.spill > 1 || x.clipped > 1);
    said.push(`${name}: ${rows.length} chips, ${bad.length} wrong`, ...rows.map((x) => `  ${bad.includes(x) ? "WRONG" : "ok   "} ${x.at.padEnd(8)} ${String(x.w).padStart(4)}px ${x.cut ? "cut…" : "whole"} slack ${x.slack} spill ${x.spill} clipped ${x.clipped}  ${x.name}`));
  }
} finally {
  await writeFile(path.join(OUT, "README.txt"), said.join("\n") + "\n");
  console.log(said.join("\n"));
  await h.close();
}
