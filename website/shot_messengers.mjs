// The README's picture of Telegram/WhatsApp in the funnel: both rows on the timeline, the
// Telegram question open with its drafted reply ready to approve.
import { fileURLToPath } from "node:url";
import { launch } from "./browser.mjs";
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const b = await launch();
const p = await b.newPage();
await p.setViewport({ width: 1600, height: 920, deviceScaleFactor: 1.25 });
await p.goto(process.argv[2], { waitUntil: "networkidle0" });
await wait(1000);
await p.evaluate(() => [...document.querySelectorAll("div")].find((d) => d.childElementCount === 0 && d.textContent === "Timeline")?.click());
await wait(1200);
// open the Telegram row's review canvas
await p.evaluate(() => {
  const rows = [...document.querySelectorAll("div")].filter((d) => d.textContent.includes("resend the Q3 numbers") && d.className.includes("Mui"));
  rows[rows.length - 1]?.click();
});
await wait(1600);
await p.screenshot({ path: fileURLToPath(new URL("../docs/screenshot-messengers.png", import.meta.url)),
                     clip: { x: 0, y: 0, width: 1600, height: 860 } });
await b.close();
console.log("messengers shot ok");
