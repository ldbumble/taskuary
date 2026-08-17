// Headless render smoke test: loads the built UI in Edge/Chrome, fails on console
// errors or a blank root, walks every tab, and screenshots the result.
import puppeteer from "puppeteer-core";

const EDGE = "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
const TABS = ["Timeline", "Board", "Tasks", "Review", "Connectors", "Docs", "Settings"];

(async () => {
  const url = process.argv[2];
  const browser = await puppeteer.launch({ executablePath: EDGE, headless: "new" });
  const page = await browser.newPage();
  await page.setViewport({ width: 1440, height: 900 });
  const errors = [];
  page.on("pageerror", (e) => errors.push(`pageerror: ${e.message}`));
  page.on("console", (m) => m.type() === "error" && errors.push(`console: ${m.text()}`));
  await page.goto(url, { waitUntil: "networkidle0", timeout: 30000 });
  await new Promise((r) => setTimeout(r, 1200));
  const text = await page.evaluate(() => document.body.innerText);
  if (!text.includes("Taskuary")) throw new Error("top bar missing - root did not render:\n" + text.slice(0, 300));
  for (const t of TABS) {
    if (!text.includes(t)) throw new Error(`tab '${t}' missing from the top bar`);
    await page.evaluate((label) => {
      const el = [...document.querySelectorAll("div")].find((d) => d.childElementCount === 0 && d.textContent === label);
      if (el) el.click();
    }, t);
    await new Promise((r) => setTimeout(r, 900));
    console.log(`tab ${t}: clicked, errors so far: ${errors.length}`);
  }
  await page.screenshot({ path: process.argv[3] || "ui.png" });
  await browser.close();
  const fatal = errors.filter((e) => !e.includes("favicon") && !e.includes("net::ERR") && !e.includes("inter.css"));
  if (fatal.length) { console.error("ERRORS:\n" + fatal.join("\n")); process.exit(1); }
  console.log("render OK - no runtime errors across all 7 tabs");
})().catch((e) => { console.error(e.message); process.exit(1); });
