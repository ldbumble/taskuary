// Press "Use & test" on the first detected CLI and see whether the AI step actually ticks. This
// runs the real CLI once ("Reply with exactly: ok"), which is the only thing that tells
// "installed" from "works".
import { launch } from "./browser.mjs";

const b = await launch();
const p = await b.newPage();
await p.setViewport({ width: 1400, height: 1100, deviceScaleFactor: 1 });
p.on("pageerror", (e) => console.log("PAGE ERROR:", e.message));
await p.goto(process.argv[2], { waitUntil: "networkidle0" });
await new Promise((r) => setTimeout(r, 2500));
if (!(await p.$('[role="dialog"]'))) {
  await p.evaluate(() => [...document.querySelectorAll("p, span")]
    .find((e) => /^\d\/\d$/.test(e.textContent || ""))?.closest("div")?.click());
  await new Promise((r) => setTimeout(r, 1200));
}
const which = process.argv[3] || "Claude Code";
const hit = await p.evaluate((label) => {
  const row = [...document.querySelectorAll("div")]
    .find((d) => d.textContent.startsWith(label) && d.querySelector("button"));
  const btn = row?.querySelector("button");
  if (!btn) return false;
  btn.click();
  return true;
}, which);
console.log(`clicked "Use & test" on ${which}:`, hit);
for (let i = 0; i < 40; i++) {
  await new Promise((r) => setTimeout(r, 3000));
  const msg = await p.evaluate(() => {
    const a = document.querySelector('[role="dialog"] .MuiAlert-message');
    const chip = [...document.querySelectorAll("p, span")].map((e) => e.textContent).find((t) => /^\d\/\d$/.test(t || ""));
    return { alert: a?.textContent || "", chip };
  });
  if (msg.alert) { console.log("result:", msg.alert, "| counter:", msg.chip || "gone (all done)"); break; }
  if (i % 4 === 3) console.log("  still running the CLI…");
}
await b.close();
