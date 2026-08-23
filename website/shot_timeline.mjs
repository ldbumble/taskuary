// The README's two timeline images, both readable at README width (~880px):
//  1. screenshot-timeline.png - the feed alone at ~950px, so it displays near 1:1
//  2. screenshot-digest.png   - the review panel open on the Morning digest, CROPPED to
//     just the panel from a real desktop-width (1846) render: the panel is ~880px wide
//     in that layout, so the crop displays at essentially full size.
import { fileURLToPath } from "node:url";
import { launch } from "./browser.mjs";
const out = (f) => fileURLToPath(new URL(`../docs/${f}`, import.meta.url));
const b = await launch();
const p = await b.newPage();

// 1. the feed, no panel - single readable column
await p.setViewport({ width: 950, height: 900, deviceScaleFactor: 2 });
await p.goto(process.argv[2], { waitUntil: "networkidle0" });
await p.evaluate(() => [...document.querySelectorAll("div")].find((d) => d.childElementCount === 0 && d.textContent === "Timeline")?.click());
await new Promise((r) => setTimeout(r, 1500));
await p.evaluate(() => [...document.querySelectorAll("div")].find((d) => d.childElementCount === 0 && d.textContent === "everything")?.click());
await new Promise((r) => setTimeout(r, 1500));
await p.screenshot({ path: out("screenshot-timeline.png"), clip: { x: 0, y: 0, width: 950, height: 850 } });

// 2. the panel on the Morning digest, at real desktop width, cropped to the panel
await p.setViewport({ width: 1846, height: 1080, deviceScaleFactor: 2 });
await new Promise((r) => setTimeout(r, 800));
await p.evaluate(() => {
  const rows = [...document.querySelectorAll("div")].filter((d) =>
    d.className.includes("Mui") && d.textContent.includes("distilled") && d.textContent.length < 300);
  rows[0]?.click();
});
await new Promise((r) => setTimeout(r, 1500));
await p.screenshot({ path: out("screenshot-digest.png"), clip: { x: 904, y: 74, width: 942, height: 640 } });
await b.close();
console.log("timeline + digest shots ok");
