// Renders phone_mock.html - the phone's side of the funnel - for the README.
import { fileURLToPath } from "node:url";
import { launch } from "./browser.mjs";
const b = await launch();
const p = await b.newPage();
await p.setViewport({ width: 940, height: 760, deviceScaleFactor: 2 });
await p.goto(new URL("phone_mock.html", import.meta.url).href, { waitUntil: "networkidle0" });
await new Promise((r) => setTimeout(r, 400));
// clip to the phones themselves - a fixed viewport leaves a slab of empty canvas below them
const box = await p.evaluate(() => {
  const r = [...document.querySelectorAll(".phone")].map((e) => e.getBoundingClientRect());
  const bottom = Math.max(...r.map((b) => b.bottom));
  return { width: 940, height: Math.ceil(bottom + 28) };
});
await p.screenshot({ path: fileURLToPath(new URL("../docs/screenshot-phone.png", import.meta.url)),
                     clip: { x: 0, y: 0, ...box } });
await b.close();
console.log("phone shot ok");
