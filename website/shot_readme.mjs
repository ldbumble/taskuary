// README shots against the demo server: the Timeline scrolled (fade band on, panel on the
// assistant's post), the Wall with three live sessions, and COUNSEL.md on the Docs tab.
// Plus the hover test: scrolling under a still cursor must not change the panel.
//   node shot_readme.mjs http://127.0.0.1:PORT <repo-root> [timeline|wall|counsel|hover|all]
import { launch } from "./browser.mjs";
const [url, root, what = "all"] = process.argv.slice(2);
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const b = await launch();
const p = await b.newPage();
p.on("pageerror", (e) => console.log("PAGE ERROR:", e.message));
await p.setViewport({ width: 1846, height: 1080, deviceScaleFactor: 2 });
const clickTab = (t) => p.evaluate((t) => [...document.querySelectorAll("div")].find((d) => d.childElementCount === 0 && d.textContent === t)?.click(), t);
const clickRow = (needle) => p.evaluate((needle) => {
  const rows = [...document.querySelectorAll("[data-tq-keep]")].filter((d) => d.textContent.includes(needle));
  const r = rows[rows.length - 1]; if (!r) return false; r.click(); return true;
}, needle);
const panelText = () => p.evaluate(() => { const ps = [...document.querySelectorAll("[data-tq-keep]")]; return (ps.find((d) => d.textContent.includes("Why it's here")) || {}).textContent?.slice(0, 80) || ""; });
const shot = (name, clip) => p.screenshot({ path: `${root}/docs/${name}`, clip: clip || { x: 0, y: 0, width: 1846, height: 1020 } });

await p.goto(url, { waitUntil: "networkidle0" }); await wait(1200);

if (what === "all" || what === "timeline") {
  await clickTab("Timeline"); await wait(1500);
  await clickTab("everything"); await wait(1000);
  // scroll a little so the dissolve band under the date is on, then pin the assistant's post
  await p.evaluate(() => window.scrollTo(0, 140)); await wait(700);
  await p.mouse.move(600, 60); await wait(400);
  console.log("assistant row:", await clickRow("Summit is missing"));
  await wait(1800);
  await shot("screenshot-timeline.png");
  console.log("timeline shot ok");
}
if (what === "all" || what === "hover") {
  await p.setViewport({ width: 1846, height: 640, deviceScaleFactor: 1 });   // short window: the page has to scroll
  await clickTab("Timeline"); await wait(1200);
  await p.evaluate(() => window.scrollTo(0, 0)); await wait(500);
  const under = () => p.evaluate(() => (document.elementFromPoint(500, 330)?.closest("[data-tq-keep]")?.textContent || "").slice(0, 40));
  // park the cursor over the list, then scroll the page under it: the panel must not change
  await p.mouse.move(500, 330); await wait(600);
  const before = await panelText(), rowBefore = await under();
  for (let i = 0; i < 6; i++) { await p.mouse.wheel({ deltaY: 80 }); await wait(120); }
  await wait(600);
  const during = await panelText(), rowDuring = await under(), y = await p.evaluate(() => window.scrollY);
  // now MOVE the mouse a little and rest: the row under it opens
  await p.mouse.move(520, 340); await wait(60); await p.mouse.move(540, 345); await wait(450);
  const after = await panelText();
  console.log(JSON.stringify({ scrollY: y, rowBefore, rowDuring, before: before.slice(0, 30), during: during.slice(0, 30), after: after.slice(0, 30),
    scrollDidNotSwitch: before === during, rowChanged: rowBefore !== rowDuring, moveOpened: after !== during && !!after }));
}
if (what === "all" || what === "wall") {
  await clickTab("Board"); await wait(1500);
  await p.evaluate(() => [...document.querySelectorAll("*")].find((d) => d.childElementCount <= 1 && d.textContent.trim() === "Wall" && d.closest("button, [role=button], div"))?.closest("button, [role=button]")?.click()
    || [...document.querySelectorAll("div,span,button")].find((d) => d.textContent.trim() === "Wall")?.click());
  await wait(6000);                                  // the panes fill in
  await shot("screenshot-wall.png");
  console.log("wall shot ok");
}
if (what === "all" || what === "counsel") {
  await clickTab("Docs"); await wait(1500);
  await p.evaluate(() => [...document.querySelectorAll("div,span,p")].find((d) => d.childElementCount === 0 && d.textContent.trim() === "COUNSEL.md")?.click());
  await wait(1500);
  await shot("screenshot-counsel.png");
  console.log("counsel shot ok");
}
await b.close();
