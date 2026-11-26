// A TEAM FINDS A TIME, RECORDED (docs/product-demo/README.md): the demo world's one scripted scene (taskuary/demo.py SCENE) played in the real
// app - a thread of replies, the agent's availability view filling in as each lands, the invite for the best slot as its card. It starts
// `taskuary --demo` itself on a throwaway home and a free port (never the live app's), types the owner's one line, and keeps the screen as
// Playwright's own video (webm, 1440x900) with a still at each beat. Nothing is sent: the demo refuses every send, and the scene presses none.
//   node website/record-availability.mjs [--out <folder>] [--dark] [--pace <seconds between replies>] [--url http://127.0.0.1:<port> --token <t>]
// Playwright is not a dependency of this repository: TASKUARY_PLAYWRIGHT names its package folder where `import "playwright"` finds none.
// The page's loading is cut from the front with the ffmpeg Playwright itself records with (its browsers folder), where there is one.
import { execFileSync, spawn } from "node:child_process";
import { existsSync, readdirSync } from "node:fs";
import { copyFile, mkdir, mkdtemp, readdir, rm } from "node:fs/promises";
import { createServer } from "node:net";
import os from "node:os";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url)), root = path.resolve(here, "..");
const arg = (k, d = "") => { const i = process.argv.indexOf(`--${k}`); return i < 0 ? d : process.argv[i + 1] ?? "1"; };
const out = path.resolve(arg("out", path.join(root, "docs/product-demo"))), dark = process.argv.includes("--dark"), pace = arg("pace", "2.6");
const LINE = "Keep track of everyone's times as they reply, and set up the invite for the best hour.";
const TITLE = "Product ideas session - a time next week?", NAME = `taskuary-availability${dark ? "-dark" : ""}`;
const delay = (ms) => new Promise((r) => setTimeout(r, ms));
const { chromium } = await import(process.env.TASKUARY_PLAYWRIGHT ? pathToFileURL(path.join(process.env.TASKUARY_PLAYWRIGHT, "index.mjs")).href : "playwright");
const ffmpeg = (() => { const dir = process.env.PLAYWRIGHT_BROWSERS_PATH || path.join(process.env.LOCALAPPDATA || path.join(os.homedir(), ".cache"), "ms-playwright");
  const f = existsSync(dir) ? readdirSync(dir).filter((d) => d.startsWith("ffmpeg-")).sort().at(-1) : "";
  const exe = f ? path.join(dir, f, process.platform === "win32" ? "ffmpeg-win64.exe" : process.platform === "darwin" ? "ffmpeg-mac" : "ffmpeg-linux") : "";
  return exe && existsSync(exe) ? exe : ""; })();

// ── the demo, on its own home and port ──
let url = arg("url"), token = arg("token", "scene-owner-token"), server = null, home = "";
if (!url) {
  const port = await new Promise((res) => { const s = createServer(); s.listen(0, "127.0.0.1", () => { const p = s.address().port; s.close(() => res(p)); }); });
  if (port === 7787) throw new Error("that is the live app's port");
  home = await mkdtemp(path.join(os.tmpdir(), "taskuary-scene-")); url = `http://127.0.0.1:${port}`;
  server = spawn(process.env.TASKUARY_TEST_PYTHON || "python", ["-m", "taskuary.cli", "--demo", "--no-browser", "--port", String(port)], { cwd: root, windowsHide: true, stdio: "ignore",
    env: { ...process.env, PYTHONPATH: root, TASKUARY_HOME: home, TASKUARY_TOKEN: token, TASKUARY_DEMO_SCENE: "availability", TASKUARY_DEMO_SCENE_PACE: pace, TASKUARY_DEMO_OPENS_TOUR: "0" } });
}
const api = async (p) => (await fetch(url + p, { headers: { "X-Taskuary-Token": token } })).json();
for (let i = 0; ; i++) { try { if ((await api("/api/health")).ok) break; } catch { /* not up yet */ } if (i > 240) throw new Error("the demo did not start"); await delay(500); }
const task = ((await api("/api/tasks")).data || []).find((t) => t.Title === TITLE);
if (!task) throw new Error("the scene's task is not in this demo - start it with TASKUARY_DEMO_SCENE=availability");

// ── the screen ──
const work = await mkdtemp(path.join(os.tmpdir(), "taskuary-scene-video-"));
const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1, colorScheme: dark ? "dark" : "light", recordVideo: { dir: work, size: { width: 1440, height: 900 } } });
await ctx.addInitScript(([t, d]) => { localStorage.setItem("taskuary_token", t); localStorage.setItem("taskuary.theme", d ? "dark" : "light"); }, [token, dark]);
const page = await ctx.newPage(), began = Date.now(), errors = [], outside = [];
page.on("pageerror", (e) => errors.push(e.message));
page.on("request", (r) => { if (!r.url().startsWith(url) && !/^(data|blob):/.test(r.url())) outside.push(r.url()); });
await mkdir(out, { recursive: true });
let n = 0, cut = 0; const held = [];
const still = async (what) => { await page.screenshot({ path: path.join(out, `${NAME}-${String(++n).padStart(2, "0")}-${what}.png`) }); };
const best = () => page.locator("[data-tq-availability]").first().getAttribute("data-best").catch(() => "");
const until = async (f, ms = 30000) => { for (const t0 = Date.now(); Date.now() - t0 < ms; await delay(100)) if (await f()) return true; throw new Error("the scene did not get there"); };
try {
  await page.goto(`${url}/#task=${task.TaskId}`, { waitUntil: "domcontentloaded" });
  const box = page.locator(".tq-aui-input").first();
  await box.waitFor({ state: "visible", timeout: 60000 }); await delay(3000);
  cut = (Date.now() - began) / 1000;                   // ...the film begins here: the thread at rest, the page's loading behind it
  await delay(1200); await still("the-thread");
  await box.click(); await page.keyboard.type(LINE, { delay: 26 }); await delay(450); await still("his-line");
  await page.keyboard.press("Enter"); await page.mouse.move(4, 896);
  await until(async () => !!(await best())); await delay(1600); await still("first-times");
  // ...a still each time the best slot or its count moves, once the view has come to rest. THE VIEW STAYS WHERE IT WAS FIRST DRAWN and the
  // replies stand under it, so after the second of them the reader wheels the chat up to hold the view in sight (the chat follows its foot
  // only while he is at it: chatStream.heldAtEnd) - then goes down to the answer and the invite at the end
  const chat = page.locator(".tq-aui-viewport").first(), hold = Math.max(1, +arg("hold", "2"));
  const gap = () => page.evaluate(() => { const c = document.querySelector(".tq-aui-viewport"), v = document.querySelector(".tq-view[data-tq-view]");
    return Math.round(v.getBoundingClientRect().top - c.getBoundingClientRect().top); });
  const toView = async (want = 6) => {
    const b = await chat.boundingBox(); await page.mouse.move(b.x + 6, b.y + b.height - 8);
    for (let pass = 0; pass < 2; pass++) { const dy = (await gap()) - want; if (Math.abs(dy) < 3) break;
      for (let i = 0; i < 12; i++) { await page.mouse.wheel(0, dy / 12); await delay(26); } await delay(160); }
    await page.mouse.move(4, 896);
  };
  for (let was = await best(), seen = 1; seen < 6;) {
    await until(async () => (await best()) !== was, 20000); was = await best(); seen++;
    await delay(1300); if (seen - 1 !== 3) await still(`reply-${seen - 1}`);
    if (seen - 1 === hold) await toView();
    held.push(await gap());
  }
  await page.locator("[data-tq-review-card]").first().waitFor({ state: "attached", timeout: 20000 });
  await delay(1700); await chat.evaluate((v) => v.scrollTo({ top: v.scrollHeight, behavior: "smooth" }));
  await delay(3000); await still("the-invite");
  await delay(1800);
} finally {
  const video = page.video();
  await ctx.close(); await browser.close();
  const raw = video ? await video.path() : "", made = path.join(out, `${NAME}.webm`);
  if (raw && ffmpeg && cut) try { execFileSync(ffmpeg, ["-y", "-loglevel", "error", "-ss", cut.toFixed(2), "-i", raw, "-c:v", "libvpx", "-b:v", "3M", "-crf", "6", "-deadline", "good", "-an", made], { windowsHide: true }); }
    catch (e) { errors.push(`not cut: ${String(e.message).slice(0, 200)}`); await copyFile(raw, made); }
  else if (raw) await copyFile(raw, made);
  await rm(work, { recursive: true, force: true });
  if (server) { server.kill(); await delay(1500); await rm(home, { recursive: true, force: true }).catch(() => {}); }      // ...the demo does not quit from the page: it is this script's to stop
}
console.log(JSON.stringify({ video: path.join(out, `${NAME}.webm`), cut: +cut.toFixed(2), held, stills: (await readdir(out)).filter((f) => f.startsWith(`${NAME}-`)), errors, outside: [...new Set(outside)] }, null, 2));
if (errors.length || outside.length) process.exitCode = 1;
