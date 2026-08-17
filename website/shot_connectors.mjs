import puppeteer from "puppeteer-core";
const b = await puppeteer.launch({ executablePath: "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe", headless: "new" });
const p = await b.newPage();
await p.setViewport({ width: 1440, height: 1000 });
await p.goto(process.argv[2], { waitUntil: "networkidle0" });
await p.evaluate(() => [...document.querySelectorAll("div")].find((d) => d.childElementCount === 0 && d.textContent === "Connectors")?.click());
await new Promise((r) => setTimeout(r, 1200));
await p.screenshot({ path: "website/connectors.png" });
await b.close();
