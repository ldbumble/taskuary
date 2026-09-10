// Capture the real taskuary.com hero as evenly timed frames. JPEG capture is quick enough to keep
// the browser animation on its real clock; PNG encoding made the resulting GIF run several times fast.
// The GIF encoder lives beside this file so the README animation remains reproducible without a
// video editor.
//   node capture-site-hero.mjs http://127.0.0.1:8767/ .readme-hero-frames
import { mkdir } from "node:fs/promises";
import path from "node:path";
import { performance } from "node:perf_hooks";
import { launch } from "./browser.mjs";

const [url = "http://127.0.0.1:8767/", output = ".readme-hero-frames"] = process.argv.slice(2);
const frameCount = 144;
const interval = 160;
await mkdir(output, { recursive: true });

const browser = await launch({ args: ["--no-sandbox", "--enable-unsafe-swiftshader"] });
try {
  const page = await browser.newPage();
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.setViewport({ width: 1200, height: 760, deviceScaleFactor: 1 });
  await page.goto(url, { waitUntil: "domcontentloaded" });
  const hero = await page.waitForSelector(".workspace-hero");
  const workspace = await hero.contentFrame();
  await workspace.waitForFunction(() => window.workspaceMockup?.state.frames > 1);

  const started = performance.now();
  for (let index = 0; index < frameCount; index += 1) {
    await page.screenshot({
      path: path.join(output, `${String(index).padStart(4, "0")}.jpg`),
      type: "jpeg",
      quality: 92,
      clip: { x: 0, y: 0, width: 1200, height: 760 },
      captureBeyondViewport: false,
    });
    const remaining = started + (index + 1) * interval - performance.now();
    if (remaining > 0) await new Promise((resolve) => setTimeout(resolve, remaining));
  }
  if (errors.length) throw new Error(`page errors: ${errors.join("; ")}`);
  console.log(`Captured ${frameCount} frames over ${Math.round((performance.now() - started) / 100) / 10}s.`);
} finally {
  await browser.close();
}
