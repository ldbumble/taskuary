// Headless check of the Wall's drag-to-reorder against the static demo bundle: build it with
// `VITE_DEMO=1 npx vite build --outDir <dir>`, serve <dir>, then `node test/wall_drag_check.mjs <url>`.
// It drags the first pane's handle onto the last pane with real pointer events and asserts the
// order changed - and survived a reload. Not part of `npm test` (needs Edge); run it by hand.
import puppeteer from "puppeteer-core";

const EDGE = "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
// the Wall is the Board tab's second view: Board in the top bar, then the Wall pill
const click = (page, label) => page.evaluate((l) => {
  // a pill is an icon plus its label, so allow one child (the svg) - the top-bar tabs have none
  const el = [...document.querySelectorAll("div,span,button")].find((d) => d.childElementCount <= 1 && d.textContent.trim() === l);
  if (!el) throw new Error(`no '${l}' to click`); el.click();
}, label);
const openWall = async (page) => {
  await click(page, "Board"); await new Promise((r) => setTimeout(r, 700));
  await click(page, "Wall");
  await page.waitForSelector("[data-wall-pane]", { timeout: 15000 });
  await new Promise((r) => setTimeout(r, 800));
};
const refs = (page) => page.$$eval("[data-wall-pane]", (els) => els.map((e) => e.getAttribute("data-wall-pane")));

(async () => {
  const url = process.argv[2];
  const browser = await puppeteer.launch({ executablePath: EDGE, headless: "new" });
  const page = await browser.newPage();
  await page.setViewport({ width: 1440, height: 900 });
  const errors = [];
  page.on("pageerror", (e) => errors.push(`pageerror: ${e.message}`));
  await page.goto(url, { waitUntil: "networkidle0", timeout: 30000 });
  await openWall(page);
  const before = await refs(page);
  if (before.length < 2) throw new Error(`need two panes to drag, got ${before.length}`);
  const handle = await page.$(`[data-wall-pane="${before[0]}"] [aria-label^="Drag"]`);
  const target = await page.$(`[data-wall-pane="${before[before.length - 1]}"]`);
  const h = await handle.boundingBox(), t = await target.boundingBox();
  await page.mouse.move(h.x + h.width / 2, h.y + h.height / 2);
  await page.mouse.down();
  for (let i = 1; i <= 12; i++) {
    await page.mouse.move(h.x + (t.x + t.width / 2 - h.x) * i / 12, h.y + (t.y + t.height / 2 - h.y) * i / 12);
    await new Promise((r) => setTimeout(r, 30));
  }
  await page.mouse.up();
  await new Promise((r) => setTimeout(r, 400));
  const after = await refs(page);
  console.log("before", before, "\nafter ", after);
  if (after.join() === before.join()) throw new Error("drag did not reorder the panes");
  if (after[after.length - 1] !== before[0]) throw new Error("the dragged pane did not land where it was dropped");
  await page.reload({ waitUntil: "networkidle0" });
  await openWall(page);
  const again = await refs(page);
  if (again.join() !== after.join()) throw new Error(`order did not survive a reload: ${again}`);
  if (errors.length) throw new Error(errors.join("\n"));
  console.log("wall drag: reordered and persisted ✓");
  await browser.close();
})().catch((e) => { console.error(e.message); process.exit(1); });
