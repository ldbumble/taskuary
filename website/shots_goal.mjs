// The owed "look at it once" for goals (spec 2026-10-12): four screenshots of the demo - the rail with the goal row, the
// goal on the table, its task page with the steps, and the New sheet's Set a goal tab.
//   node website/shots_goal.mjs <url> <outdir>
import fs from "node:fs";
import path from "node:path";
import { launch } from "./browser.mjs";

const [url, outdir] = process.argv.slice(2);
fs.mkdirSync(outdir, { recursive: true });
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const clickText = (page, label, tags = "div,span,button,a,p,b") => page.evaluate((l, t) => {
  const norm = (x) => x.replace(/\s+/g, " ").trim();
  const els = [...document.querySelectorAll(t)].filter((d) => d.childElementCount <= 4 && norm(d.textContent).startsWith(l));
  const el = els.find((e) => e.offsetParent !== null) || els[0];
  if (!el) return false;
  el.click(); return true;
}, label, tags);
const shot = (page, name) => page.screenshot({ path: path.join(outdir, name), fullPage: false });

const browser = await launch();
const page = await browser.newPage();
await page.setViewport({ width: 1440, height: 900 });
const errors = [];
page.on("pageerror", (e) => errors.push(`pageerror: ${e.message}`));
page.on("console", (m) => { if (m.type() === "error") errors.push(`console: ${m.text().slice(0, 200)}`); });
await page.goto(url, { waitUntil: "networkidle2", timeout: 60000 });
await wait(2500);
console.log("assistant tab:", await clickText(page, "Assistant"));
await wait(3000);
await shot(page, "1-rail.png");
const rows = await page.evaluate(() => [...document.querySelectorAll(".tq-pile-row .t b")].map((b) => b.textContent.trim()));
console.log("rail rows:", JSON.stringify(rows));
const heads = await page.evaluate(() => [...document.querySelectorAll(".tq-pile-head span")].map((b) => b.textContent.trim()));
console.log("bands:", JSON.stringify(heads));
console.log("goal row clicked:", await clickText(page, "Migrate the census export", ".tq-pile-row .t b"));
await wait(3500);
await shot(page, "2-goal-on-table.png");
const chips = await page.evaluate(() => [...document.querySelectorAll("button")].map((b) => b.textContent.trim()).filter((t) => t && t.length < 32));
console.log("buttons on stage:", JSON.stringify(chips.slice(0, 40)));
const done = await page.evaluate(() => [...document.querySelectorAll("p,span,div")].map((e) => e.textContent.trim()).filter((t) => t.startsWith("Done when") || t.includes("steps done") || t === "Start").slice(0, 6));
console.log("goal steps visible:", JSON.stringify(done));
await shot(page, "3-goal-task-page.png");
// the sidebar's New, by its exact word - "New starter on Monday" is a row and matched first
console.log("new clicked:", await page.evaluate(() => {
  const el = [...document.querySelectorAll("div,span,a,button")].find((d) => d.childElementCount <= 2 && d.textContent.replace(/\s+/g, " ").trim() === "New" && d.offsetParent !== null);
  if (!el) return false; el.click(); return true;
}));
await wait(1800);
console.log("goal tab clicked:", await page.evaluate(() => { const el = [...document.querySelectorAll("[role=tab]")].find((d) => d.textContent.includes("Set a goal")); if (!el) return false; el.click(); return true; }));
await wait(1200);
await shot(page, "4-new-goal.png");
const labels = await page.evaluate(() => [...document.querySelectorAll("[data-tq-new] *")].map((e) => e.childElementCount === 0 ? e.textContent.trim() : "").filter((t) => t && t.length < 60).slice(0, 30));
console.log("sheet labels:", JSON.stringify(labels));
console.log("errors:", JSON.stringify(errors.slice(0, 8)));
await browser.close();
