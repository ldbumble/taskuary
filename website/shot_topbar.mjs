// The top bar with the panel closed, and what the tab row actually measures - a nav that
// scrolls sideways is a nav you cannot read at a glance.
import { fileURLToPath } from "node:url";
import { launch } from "./browser.mjs";

const b = await launch();
const p = await b.newPage();
await p.setViewport({ width: Number(process.argv[3] || 1846), height: 700, deviceScaleFactor: 2 });
await p.goto(process.argv[2], { waitUntil: "networkidle0" });
await new Promise((r) => setTimeout(r, 2200));
await p.evaluate(() => [...document.querySelectorAll("button")].find((x) => /Close|Put it away/.test(x.textContent))?.click());
await new Promise((r) => setTimeout(r, 600));
const m = await p.evaluate(() => {
  const scroller = [...document.querySelectorAll("div")].find((d) => d.scrollWidth > d.clientWidth + 4 && d.clientHeight < 60);
  return scroller ? { tag: scroller.textContent.slice(0, 60), scrollWidth: scroller.scrollWidth, clientWidth: scroller.clientWidth } : null;
});
console.log("window:", process.argv[3] || 1846, "| horizontally scrolling strip in the bar:", JSON.stringify(m));
await p.screenshot({ path: fileURLToPath(new URL("../docs/_topbar.png", import.meta.url)),
                     clip: { x: 0, y: 0, width: Number(process.argv[3] || 1846), height: 120 } });
await b.close();
