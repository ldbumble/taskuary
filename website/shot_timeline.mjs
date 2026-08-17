import puppeteer from "puppeteer-core";
const b = await puppeteer.launch({ executablePath: "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe", headless: "new" });
const p = await b.newPage();
await p.setViewport({ width: 1600, height: 900, deviceScaleFactor: 1.25 });
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
await p.screenshot({ path: "docs/screenshot-timeline.png" });
await b.close();
console.log("timeline shot ok");
