// The README's "work arrives and gets sorted" shot: the Assistant tab's rail on "all" (the whole
// Timeline) in Task mode, with the review canvas open on the pending draft.
// Reflow and crop the live UI so labels stay legible in GitHub's narrower README column.
import { fileURLToPath } from "node:url";
import { launch } from "./browser.mjs";
const b = await launch();
const p = await b.newPage();
await p.setViewport({ width: 1846, height: 1080, deviceScaleFactor: 2 });
await p.goto(process.argv[2], { waitUntil: "networkidle0" });
await p.evaluate(() => [...document.querySelectorAll("div")].find((d) => d.childElementCount === 0 && d.textContent === "all")?.click());
await new Promise((r) => setTimeout(r, 1200));
await p.evaluate(() => [...document.querySelectorAll(".tq-stage-mode button")].find((x) => x.textContent === "Task")?.click());
await new Promise((r) => setTimeout(r, 600));
// open the review canvas on the pending-draft row
await p.evaluate(() => {
  const rows = [...document.querySelectorAll("div")].filter((d) => d.textContent.includes("AP cutover") && d.className.includes("Mui"));
  rows[rows.length - 1]?.click();
});
await new Promise((r) => setTimeout(r, 1500));
await p.evaluate(() => {
  const app = document.getElementById("root");
  app.style.filter = "contrast(1.16) saturate(1.08) brightness(.985)";
  app.style.transformOrigin = "top left";
});
await p.setViewport({ width: 1280, height: 820, deviceScaleFactor: 2 });
await new Promise((r) => setTimeout(r, 900));
await p.evaluate(() => {
  document.getElementById("tqTopNav").style.display = "none";
  window.scrollTo(0, 0);
});
await new Promise((r) => setTimeout(r, 500));
// a plain path, not a URL object: puppeteer sniffs the type off the extension with
// lastIndexOf, which a URL does not have
await p.screenshot({ path: fileURLToPath(new URL("../docs/screenshot-timeline-crop.png", import.meta.url)),
                    clip: { x: 0, y: 0, width: 1280, height: 620 } });
await b.close();
console.log("timeline shot ok");
