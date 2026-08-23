// The README hero: the triaged timeline with the review panel open on the pending draft.
// Shot NARROW (1280) at 2x so the rows and the panel read at README size - the old 1600px
// frame shrank every line into squint territory.
import { fileURLToPath } from "node:url";
import { launch } from "./browser.mjs";
const b = await launch();
const p = await b.newPage();
await p.setViewport({ width: 1120, height: 900, deviceScaleFactor: 2 });
await p.goto(process.argv[2], { waitUntil: "networkidle0" });
await p.evaluate(() => [...document.querySelectorAll("div")].find((d) => d.childElementCount === 0 && d.textContent === "Timeline")?.click());
await new Promise((r) => setTimeout(r, 1500));
await p.evaluate(() => [...document.querySelectorAll("div")].find((d) => d.childElementCount === 0 && d.textContent === "everything")?.click());
await new Promise((r) => setTimeout(r, 1200));
// open the review canvas on the pending-draft row
await p.evaluate(() => {
  const rows = [...document.querySelectorAll("div")].filter((d) => d.textContent.includes("vendor spend") && d.className.includes("Mui"));
  rows[rows.length - 1]?.click();
});
await new Promise((r) => setTimeout(r, 1500));
// nudge the review panel's own scroll so the DRAFT REPLY box makes the frame - at this
// zoom the panel is taller than the viewport and the draft slipped below the fold
await p.evaluate(() => {
  [...document.querySelectorAll("div")]
    .filter((d) => d.scrollHeight > d.clientHeight + 20 && d.clientHeight > 250 && d.getBoundingClientRect().left > 600)
    .forEach((d) => { d.scrollTop = 262; });
});
await new Promise((r) => setTimeout(r, 400));
// a plain path, not a URL object: puppeteer sniffs the type off the extension with
// lastIndexOf, which a URL does not have
await p.screenshot({ path: fileURLToPath(new URL("../docs/screenshot-timeline.png", import.meta.url)),
                    clip: { x: 0, y: 0, width: 1120, height: 762 } });
await b.close();
console.log("timeline shot ok");
