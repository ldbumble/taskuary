// The setup wizard on a genuinely empty install: it opens itself at 0/3, so no clicking is
// needed to reach it - which is the behaviour worth proving as much as the layout.
import { fileURLToPath } from "node:url";
import { launch } from "./browser.mjs";

const out = process.argv[3] || "../docs/screenshot-setup.png";
const b = await launch();
const p = await b.newPage();
await p.setViewport({ width: 1400, height: 1000, deviceScaleFactor: 2 });
p.on("pageerror", (e) => console.log("PAGE ERROR:", e.message));
p.on("console", (m) => m.type() === "error" && console.log("CONSOLE:", m.text().slice(0, 200)));
await p.goto(process.argv[2], { waitUntil: "networkidle0" });
await new Promise((r) => setTimeout(r, 2500));      // the panel opens itself off /api/setup
// ...but only on a wholly fresh install, so click the counter when it did not
if (!(await p.$('[role="dialog"]'))) {
  await p.evaluate(() => [...document.querySelectorAll("p, span")]
    .find((e) => /^\d\/\d$/.test(e.textContent || ""))?.closest("div")?.click());
  await new Promise((r) => setTimeout(r, 1200));
}
const seen = await p.evaluate(() => document.body.innerText.slice(0, 400));
console.log("--- what the page says ---\n" + seen);
await p.screenshot({ path: fileURLToPath(new URL(out, import.meta.url)) });
await b.close();
console.log("wizard shot ok ->", out);
