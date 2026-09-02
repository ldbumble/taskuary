// Headless check: the two views that can hold a live pty session (Timeline, Board) must stay
// MOUNTED behind another tab. Unmounting closes the session's websocket, so coming back
// reconnects and replays the whole scrollback - the pane running top to bottom every time you
// switch tabs (owner, 2026-09-02). Build the demo bundle, serve it, then:
//   node website/tabs_keepalive_check.mjs <url>
// Not part of `npm test` (needs Edge); run it by hand.
import puppeteer from "puppeteer-core";

const EDGE = "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";

const click = (page, label) => page.evaluate((l) => {
  const el = [...document.querySelectorAll("div,span,button")]
    .find((d) => d.childElementCount <= 1 && d.textContent.trim() === l);
  if (!el) throw new Error(`no '${l}' to click`);
  el.click();
}, label);

// Is the element carrying this text present in the DOM, and is it on screen?
const probe = (page, text) => page.evaluate((t) => {
  const el = [...document.querySelectorAll("div,span,button")]
    .find((d) => d.childElementCount <= 1 && d.textContent.trim() === t);
  return { mounted: !!el, visible: !!el && !!el.offsetParent };
}, text);

(async () => {
  const url = process.argv[2];
  const browser = await puppeteer.launch({ executablePath: EDGE, headless: "new" });
  const page = await browser.newPage();
  await page.setViewport({ width: 1440, height: 900 });
  const errors = [];
  page.on("pageerror", (e) => errors.push(`pageerror: ${e.message}`));
  page.on("console", (m) => m.type() === "error" && errors.push(`console: ${m.text()}`));
  await page.goto(url, { waitUntil: "networkidle0", timeout: 30000 });
  await new Promise((r) => setTimeout(r, 1000));

  // "needs me" is the Timeline's own segmented control; "Columns" is the Board's view pill.
  const TIMELINE = "needs me", BOARD = "Columns";

  let t = await probe(page, TIMELINE);
  if (!t.visible) throw new Error("the Timeline did not render on arrival");

  await click(page, "Board");
  await new Promise((r) => setTimeout(r, 900));
  t = await probe(page, TIMELINE);
  if (!t.mounted) throw new Error("the Timeline UNMOUNTED behind the Board - a live session would have dropped its socket");
  if (t.visible) throw new Error("the Timeline is still on screen behind the Board");
  let b = await probe(page, BOARD);
  if (!b.visible) throw new Error("the Board did not render");

  await click(page, "Docs");
  await new Promise((r) => setTimeout(r, 900));
  b = await probe(page, BOARD);
  if (!b.mounted) throw new Error("the Board UNMOUNTED behind Docs - the Wall's sessions would have dropped");
  if (b.visible) throw new Error("the Board is still on screen behind Docs");

  await click(page, "Timeline");
  await new Promise((r) => setTimeout(r, 900));
  t = await probe(page, TIMELINE);
  if (!t.visible) throw new Error("the Timeline did not come back");

  if (errors.length) throw new Error(errors.join("\n"));
  console.log("tabs keep-alive: Timeline and Board stay mounted behind another tab \u2713");
  await browser.close();
})().catch((e) => { console.error(e.message); process.exit(1); });
