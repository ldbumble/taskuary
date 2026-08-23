// The README's collaboration shot: two agents working the same checkout (file chips on each
// card) and a third task queued behind one of them, its tooltip open - run after seed_demo.py.
import { fileURLToPath } from "node:url";
import { launch } from "./browser.mjs";
const b = await launch();
const p = await b.newPage();
await p.setViewport({ width: 1600, height: 920, deviceScaleFactor: 1.25 });
await p.goto(process.argv[2], { waitUntil: "networkidle0" });
await p.evaluate(() => [...document.querySelectorAll("div")].find((d) => d.childElementCount === 0 && d.textContent === "Board")?.click());
await new Promise((r) => setTimeout(r, 2500));                     // let the live-runs poll land
// hover the queued chip so the shot shows WHY the task waits and behind WHOM
const chip = await p.evaluateHandle(() =>
  [...document.querySelectorAll(".MuiChip-root")].find((c) => c.textContent.includes("behind TQ-")));
if (chip && chip.asElement()) { await chip.asElement().hover(); await new Promise((r) => setTimeout(r, 900)); }
await p.screenshot({ path: fileURLToPath(new URL("../docs/screenshot-board.png", import.meta.url)),
                     clip: { x: 0, y: 0, width: 1600, height: 860 } });
await b.close();
console.log("board shot ok");
