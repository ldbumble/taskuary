import { fileURLToPath } from "node:url";
import { launch } from "./browser.mjs";
const b = await launch();
const p = await b.newPage();
await p.setViewport({ width: 1600, height: 920, deviceScaleFactor: 1.25 });
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
// a plain path, not a URL object: puppeteer sniffs the type off the extension with
// lastIndexOf, which a URL does not have
await p.screenshot({ path: fileURLToPath(new URL("../docs/screenshot-timeline.png", import.meta.url)),
                    clip: { x: 0, y: 0, width: 1600, height: 860 } });
await b.close();
console.log("timeline shot ok");
