// Does the agent terminal actually SCROLL, and is the scrollbar visible? Drives a real
// session in the Tasks tab and measures the xterm viewport.
import puppeteer from "puppeteer-core";
const EDGE = "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const clickText = (page, label, tag = "*") => page.evaluate((label, tag) => {
  const el = [...document.querySelectorAll(tag)].filter((e) => e.offsetParent
    && (e.textContent.trim() === label || (e.childElementCount === 0 && e.textContent.trim().startsWith(label))))[0];
  if (!el) return false;
  (el.closest("button") || el).click();
  return true;
}, label, tag);
(async () => {
  const [url, out] = [process.argv[2], process.argv[3]];
  const b = await puppeteer.launch({ executablePath: EDGE, headless: "new" });
  const page = await b.newPage();
  const errs = [];
  page.on("pageerror", (e) => errs.push(e.message));
  page.on("console", (m) => m.type() === "error" && errs.push(m.text()));
  await page.setViewport({ width: 1600, height: 1000 });
  await page.goto(url, { waitUntil: "networkidle0" });
  await wait(800);
  console.log("Tasks:", await clickText(page, "Tasks", "div"));
  await wait(1000);
  console.log("task row:", await clickText(page, "TQ-0001", "span"));
  await wait(4000);                                    // let the pty stream in
  const view = () => page.evaluate(() => {
    const v = document.querySelector(".xterm-viewport");
    if (!v) return null;
    const cs = getComputedStyle(v);
    return { h: v.clientHeight, scroll: v.scrollHeight, top: v.scrollTop, overflow: cs.overflowY,
             paneH: document.querySelector(".xterm")?.clientHeight || 0 };
  });
  console.log("viewport:", await view());
  // wheel up, like a person looking for what scrolled past
  await page.evaluate(() => {
    const v = document.querySelector(".xterm-viewport");
    v.scrollTop = 0;
    v.dispatchEvent(new Event("scroll"));
  });
  await wait(700);
  const after = await view();
  console.log("after scrolling to top:", after);
  await page.screenshot({ path: `${out}/term-scrolled.png` });
  await page.evaluate(() => { const v = document.querySelector(".xterm-viewport"); v.scrollTop = v.scrollHeight; });
  await wait(600);
  await page.screenshot({ path: `${out}/term-bottom.png` });
  const txt = await page.evaluate(() => document.querySelector(".xterm")?.innerText || "");
  console.log("first visible rows:", txt.split("\n").filter((l) => l.trim()).slice(0, 3));
  await b.close();
  const fatal = errs.filter((e) => !/favicon|inter\.css/.test(e));
  if (fatal.length) { console.error("ERRORS:\n" + fatal.join("\n")); process.exit(1); }
  if (!after || after.scroll <= after.h) { console.error("nothing to scroll - scrollback not reachable"); process.exit(1); }
  console.log("terminal scrolls OK");
})().catch((e) => { console.error(e.message); process.exit(1); });
