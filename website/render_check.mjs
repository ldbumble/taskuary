// Headless render smoke test: loads the built UI in Edge/Chrome, fails on console
// errors or a blank root, walks the current canvas navigation, and screenshots it.
import { launch } from "./browser.mjs";
import { clickNav } from "./browser/harness.mjs";

const VIEWS = ["Board", "Assistant", "Reports", "Hub", "Connections", "Settings"];

(async () => {
  const url = process.argv[2];
  if (!url) throw new Error("Pass the URL of an isolated demo or test instance.");
  const browser = await launch();
  try {
  const page = await browser.newPage();
  await page.setViewport({ width: 1440, height: 900 });
  const errors = [];
  page.on("pageerror", (e) => errors.push(`pageerror: ${e.message}`));
  page.on("console", (m) => m.type() === "error" && errors.push(`console: ${m.text()}`));
  await page.goto(url, { waitUntil: "networkidle0", timeout: 30000 });
  await new Promise((r) => setTimeout(r, 1200));
  const text = await page.evaluate(() => document.body.innerText);
  if (!text.includes("Taskuary")) throw new Error("top bar missing - root did not render:\n" + text.slice(0, 300));
  for (const t of VIEWS) {
    await clickNav(page, t);
    await new Promise((r) => setTimeout(r, 900));
    console.log(`view ${t}: opened, errors so far: ${errors.length}`);
  }
  await page.screenshot({ path: process.argv[3] || "ui.png" });
  const fatal = errors.filter((e) => !e.includes("favicon") && !e.includes("net::ERR") && !e.includes("inter.css"));
  if (fatal.length) throw new Error("ERRORS:\n" + fatal.join("\n"));
  console.log("render OK - no runtime errors across all canvas views");
  } finally { await browser.close(); }
})().catch((e) => { console.error(e.message); process.exit(1); });
