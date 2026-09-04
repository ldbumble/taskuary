// README shots against the demo server: the unified pipe/chat, the Wall with three live
// sessions, and COUNSEL.md.
// Plus the hover test: scrolling under a still cursor must not change the panel.
//   node shot_readme.mjs http://127.0.0.1:PORT <repo-root> [chat|wall|counsel|hover|all]
import { launch } from "./browser.mjs";
const [url, root, what = "all"] = process.argv.slice(2);
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const b = await launch();
const p = await b.newPage();
p.on("pageerror", (e) => console.log("PAGE ERROR:", e.message));
await p.setViewport({ width: 1846, height: 1080, deviceScaleFactor: 2 });
const clickTab = (t) => p.evaluate((t) => [...document.querySelectorAll("div")].find((d) => d.childElementCount === 0 && d.textContent === t)?.click(), t);
const panelText = () => p.evaluate(() => { const ps = [...document.querySelectorAll("[data-tq-keep]")]; return (ps.find((d) => d.textContent.includes("Why it's here")) || {}).textContent?.slice(0, 80) || ""; });
const shot = (name, clip) => p.screenshot({ path: `${root}/docs/${name}`, clip: clip || { x: 0, y: 0, width: 1846, height: 1020 } });
// The app palette is intentionally quiet; at README scale its screenshot used to wash into
// the GitHub page. Tone the captured pixels, not the product theme. Keeping this here makes
// every regenerated README image match, and unlike an image-model edit every glyph stays real.
const applyReadmeTone = () => p.evaluate(() => {
  const app = document.getElementById("root");
  app.style.filter = "contrast(1.16) saturate(1.08) brightness(.985)";
  app.style.transformOrigin = "top left";
});

await p.goto(url, { waitUntil: "networkidle0" }); await wait(1200);
// A fresh demo home opens the first-run checklist. It is useful in the product, but README
// shots are of the workspace behind it; put it away just as a returning user would.
await p.evaluate(() => [...document.querySelectorAll("button")]
  .find((b) => b.textContent.trim() === "Put it away")?.click());
await wait(500);

if (what === "all" || what === "chat") {
  // The product now opens here: the Timeline is the pipe beside the chat, not a separate
  // README story followed by a second Assistant story. Capture only the sealed demo so the
  // README can never expose somebody's real inbox, contacts, repositories, or reports.
  await p.setViewport({ width: 1440, height: 900, deviceScaleFactor: 2 });
  await wait(1800);
  await applyReadmeTone();
  await shot("screenshot-chat.png", { x: 0, y: 0, width: 1440, height: 900 });
  await p.setViewport({ width: 1846, height: 1080, deviceScaleFactor: 2 });
  console.log("chat shot ok (demo data only)");
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
