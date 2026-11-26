// keeps a demo-world instance up for press-measure.mjs (scratch home, free ports); stop by touching $PRESS_OUT/stop
import { mkdir, writeFile } from "node:fs/promises";
import { existsSync } from "node:fs";
import path from "node:path";
import { startHarness } from "./harness.mjs";
for (const k of Object.keys(process.env)) if (/^npm_/i.test(k)) delete process.env[k];
const out = process.env.PRESS_OUT; await mkdir(out, { recursive: true });
const h = await startHarness();
const page = await h.newPage();
await page.setViewport({ width: 1440, height: 900 });
page.on("pageerror", (e) => console.log("PAGEERROR", e.message));
await page.goto(h.ui, { waitUntil: "domcontentloaded" });
await writeFile(path.join(out, "info.json"), JSON.stringify({ ui: h.ui, api: h.fixtureApi, token: h.token, home: h.home, ws: page.browser().wsEndpoint(), pid: process.pid }));
console.log("READY", h.ui, h.home);
while (!existsSync(path.join(out, "stop"))) await new Promise((r) => setTimeout(r, 1000));
await h.close(); console.log("CLOSED");
