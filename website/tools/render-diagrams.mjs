// THE DOCS SITE'S DIAGRAMS, DRAWN. The site's markdown build does not run mermaid, so a decision tree
// lives as a committed SVG under docs/site/img/, drawn from the ```mermaid blocks of its source doc so
// the picture and the doc cannot tell two stories. A doc with several blocks draws them in order, one
// svg each. Re-run after editing a block:
//   node tools/render-diagrams.mjs        (BROWSER_EXE overrides the Edge path, as in ui_audit.mjs)
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import puppeteer from "puppeteer-core";

const HERE = path.dirname(fileURLToPath(import.meta.url)), ROOT = path.resolve(HERE, "..", "..");
const EDGE = process.env.BROWSER_EXE || "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
// source doc -> the svgs the site shows, one per mermaid block, in order
const DIAGRAMS = {
  "docs/how-a-task-ends.md": ["docs/site/img/how-a-task-ends.svg"],
  "docs/assistant-words.md": ["docs/site/img/assistant-buttons.svg", "docs/site/img/assistant-questions.svg", "docs/site/img/assistant-task-tools.svg"],
};

const browser = await puppeteer.launch({ executablePath: EDGE, headless: "new" });
const page = await browser.newPage();
await page.setContent('<script src="https://cdn.jsdelivr.net/npm/mermaid@11.4.1/dist/mermaid.min.js"></script>');
await page.waitForFunction(() => window.mermaid);
for (const [src, outs] of Object.entries(DIAGRAMS)) {
  const blocks = [...read(src).matchAll(/```mermaid\n([\s\S]*?)```/g)].map((m) => m[1]);
  if (blocks.length !== outs.length) throw new Error(`${src}: ${blocks.length} mermaid blocks for ${outs.length} pictures`);
  for (const [i, block] of blocks.entries()) {
    // htmlLabels off: the svg is shown through <img>, where foreignObject text is not reliable
    const svg = await page.evaluate(async (code, id) => {
      mermaid.initialize({ startOnLoad: false, theme: "neutral", flowchart: { htmlLabels: false }, fontFamily: "system-ui, sans-serif" });
      return (await mermaid.render(id, code)).svg;
    }, block, `d${i}`);
    const out = path.join(ROOT, outs[i]);
    fs.mkdirSync(path.dirname(out), { recursive: true });
    // an <img> parses the svg as XML, where mermaid's <br> (a line break inside a label) is an unclosed tag
    fs.writeFileSync(out, svg.replace('style="max-width', 'style="background:#fff;max-width').replace(/<br\s*>/g, "<br/>") + "\n");
    console.log(`${src} -> ${outs[i]}`);
  }
}
await browser.close();
function read(p) { return fs.readFileSync(path.join(ROOT, p), "utf8").replace(/\r\n/g, "\n"); }
