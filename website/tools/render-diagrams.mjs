// THE DOCS SITE'S DIAGRAMS, DRAWN. The site's markdown build does not run mermaid, so a decision tree
// lives as a committed SVG under docs/site/img/, drawn from the ```mermaid block of its source doc so
// the picture and the doc cannot tell two stories. Re-run after editing the block:
//   node tools/render-diagrams.mjs        (BROWSER_EXE overrides the Edge path, as in ui_audit.mjs)
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import puppeteer from "puppeteer-core";

const HERE = path.dirname(fileURLToPath(import.meta.url)), ROOT = path.resolve(HERE, "..", "..");
const EDGE = process.env.BROWSER_EXE || "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
// source doc -> the svg the site shows
const DIAGRAMS = { "docs/how-a-task-ends.md": "docs/site/img/how-a-task-ends.svg" };

const browser = await puppeteer.launch({ executablePath: EDGE, headless: "new" });
const page = await browser.newPage();
await page.setContent('<script src="https://cdn.jsdelivr.net/npm/mermaid@11.4.1/dist/mermaid.min.js"></script>');
await page.waitForFunction(() => window.mermaid);
for (const [src, out] of Object.entries(DIAGRAMS)) {
  const block = read(src).match(/```mermaid\n([\s\S]*?)```/)?.[1];
  if (!block) throw new Error(`${src}: no mermaid block`);
  // htmlLabels off: the svg is shown through <img>, where foreignObject text is not reliable
  const svg = await page.evaluate(async (code) => {
    mermaid.initialize({ startOnLoad: false, theme: "neutral", flowchart: { htmlLabels: false }, fontFamily: "system-ui, sans-serif" });
    return (await mermaid.render("d", code)).svg;
  }, block);
  fs.mkdirSync(path.dirname(path.join(ROOT, out)), { recursive: true });
  fs.writeFileSync(path.join(ROOT, out), svg.replace('style="max-width', 'style="background:#fff;max-width') + "\n");
  console.log(`${src} -> ${out}`);
}
await browser.close();
function read(p) { return fs.readFileSync(path.join(ROOT, p), "utf8").replace(/\r\n/g, "\n"); }
