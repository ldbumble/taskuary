// Does a connection card hold its settings until Save? Opens the GitHub card, switches Processing, and checks the bar
// appears with the change, Discard puts it back, and Save keeps it across a reload.
//
//   node website/savebar_check.mjs <url> <outdir>     # against a `taskuary --demo --port N` server
import { launch } from "./browser.mjs";

const url = process.argv[2] || "http://127.0.0.1:7913/";
const out = process.argv[3] || ".";
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const clickText = (page, re) => page.evaluate((src) => {
  const rx = new RegExp(src);
  const el = [...document.querySelectorAll("body *")].filter((x) => rx.test(x.textContent.trim()))
    .sort((a, b) => a.textContent.length - b.textContent.length)[0];
  el?.click(); return !!el;
}, re.source);
const bar = (page) => page.evaluate(() => document.querySelector(".tq-savebar")?.innerText || null);
const ranked = (page) => page.evaluate(() => {
  const r = [...document.querySelectorAll("input[type=radio]")].find((i) => i.closest("label, div")?.textContent.includes("Ranked together") && i.value === "rank");
  return r ? r.checked : [...document.querySelectorAll("*")].some((x) => /Ranked together/.test(x.textContent) && x.querySelector?.("input:checked"));
});
const openGithub = async (page) => {
  await page.goto(url, { waitUntil: "networkidle2" }); await wait(2000);
  await clickText(page, /^Connections$/); await wait(1500);
  await clickText(page, /^Developer$/); await wait(1000);                 // the catalogue opens on its categories
  await clickText(page, /^GitHub$/); await wait(1800);
  await clickText(page, /^Inbound/); await wait(800);                     // the step that holds Processing
};

const browser = await launch();
const page = await browser.newPage(); await page.setViewport({ width: 1440, height: 1100 });
page.on("dialog", (d) => d.accept());
let bad = 0;
const fail = (why, x) => { console.log("FAIL:", why, x ?? ""); bad = 1; };
try {
  await openGithub(page);
  if (await bar(page)) fail("a bar before anything changed", await bar(page));
  if (!(await clickText(page, /^Ranked together$/))) { console.log("no Processing step on this card"); process.exit(2); }
  await wait(600);
  let b = await bar(page);
  console.log("after the click:", JSON.stringify(b));
  if (!b || !/Processing: One by one → Ranked together/.test(b)) fail("the bar did not list the change", b);
  await page.screenshot({ path: `${out}/savebar-pending.png` });
  await clickText(page, /^Discard$/); await wait(600);
  if (await bar(page)) fail("Discard left the bar up", await bar(page));
  await clickText(page, /^Ranked together$/); await wait(500);
  await clickText(page, /^Save$/); await wait(1500);
  if (await bar(page)) fail("Save left the bar up", await bar(page));
  await openGithub(page);
  b = await bar(page);
  const text = await page.evaluate(() => document.body.innerText);
  console.log("after a reload: bar", JSON.stringify(b), "| ranked checked:", await ranked(page));
  if (!(await ranked(page))) fail("the saved choice did not survive a reload");
  await page.screenshot({ path: `${out}/savebar-saved.png` });
  if (!/Ranked together/.test(text)) fail("no Processing on the reopened card");
} finally { await browser.close(); }
process.exit(bad);
