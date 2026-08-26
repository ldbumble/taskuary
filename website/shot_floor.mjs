// The README's floor shot: the Board's Floor view, where a desk is a task and the posture at
// it says what the agent is doing. Run after seed_demo.py. Pass a second argument to also
// exercise the camera (drag + zoom) and write a -detail shot, which is how you check the orbit
// still works after touching the projection.
import { fileURLToPath } from "node:url";
import { launch } from "./browser.mjs";

const out = (n) => fileURLToPath(new URL(`../docs/${n}.png`, import.meta.url));
// the innermost node whose whole text is `t`, then let the click bubble to whatever owns the
// handler - the Studio toggle carries an icon, so an exact-text-and-no-children match misses it
const click = (p, text) => p.evaluate((t) => {
  const all = [...document.querySelectorAll("div,span,button")].filter((d) => d.textContent.trim() === t);
  all[all.length - 1]?.click();
}, text);
const wait = (ms) => new Promise((r) => setTimeout(r, ms));

const b = await launch();
const p = await b.newPage();
await p.setViewport({ width: 1440, height: 1000, deviceScaleFactor: 2 });
await p.goto(process.argv[2], { waitUntil: "networkidle0" });
await click(p, "Board");
await wait(1200);
await click(p, "Studio");
await wait(2200);                                   // the room's own clock, and the live poll
await p.screenshot({ path: out("screenshot-floor"), clip: { x: 0, y: 44, width: 1440, height: 800 } });
console.log("floor shot ok");

if (process.argv[3]) {
  // turn the room and zoom in, the way a person would, then prove it settled somewhere legible
  const box = await p.evaluate(() => {
    const all = [...document.querySelectorAll("svg[viewBox]")]
      .map((n) => ({ n, r: n.getBoundingClientRect() }))
      .sort((a, b) => b.r.width * b.r.height - a.r.width * a.r.height);
    const r = all[0].r;
    return { x: r.x + r.width * 0.62, y: r.y + r.height * 0.45 };
  });
  await p.mouse.move(box.x, box.y);
  await p.mouse.down();
  for (let i = 1; i <= 12; i++) { await p.mouse.move(box.x + i * 14, box.y - i * 2); await wait(16); }
  await p.mouse.up();
  await wait(700);                                  // the ease has to have finished
  for (let i = 0; i < 5; i++) { await p.mouse.wheel({ deltaY: -240 }); await wait(90); }
  await wait(900);
  await p.screenshot({ path: out("screenshot-floor-detail"), clip: { x: 0, y: 44, width: 1440, height: 800 } });
  console.log("floor detail shot ok");
}
await b.close();
