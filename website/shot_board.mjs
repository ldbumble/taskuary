// The README's collaboration shot: two agents working the same checkout (file chips on each
// card) and a third task queued behind one of them, its tooltip open - run after seed_demo.py.
// Shot NARROW (1280) at 2x and cropped to the three busy columns, so the cards read at
// README size instead of shrinking into a wall of four columns and dead space.
import { fileURLToPath } from "node:url";
import { launch } from "./browser.mjs";
const b = await launch();
const p = await b.newPage();
await p.setViewport({ width: 1280, height: 900, deviceScaleFactor: 2 });
await p.goto(process.argv[2], { waitUntil: "networkidle0" });
await p.evaluate(() => [...document.querySelectorAll("div")].find((d) => d.childElementCount === 0 && d.textContent === "Board")?.click());
await new Promise((r) => setTimeout(r, 2500));                     // let the live-runs poll land
// hover the queued chip so the shot shows WHY the task waits and behind WHOM
const chip = await p.evaluateHandle(() =>
  [...document.querySelectorAll(".MuiChip-root")].find((c) => c.textContent.includes("behind TQ-")));
if (chip && chip.asElement()) { await chip.asElement().hover(); await new Promise((r) => setTimeout(r, 900)); }
await p.screenshot({ path: fileURLToPath(new URL("../docs/screenshot-board.png", import.meta.url)),
                     clip: { x: 0, y: 44, width: 948, height: 575 } });
await b.close();
console.log("board shot ok");
