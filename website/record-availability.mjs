// A TEAM FINDS A TIME, RECORDED (docs/product-demo/README.md): the demo world's one scripted scene (taskuary/demo.py SCENE) played in the real
// app - a thread of replies, the agent's availability view drawn again under each as it lands, the invite for the best slot as its card. It
// starts `taskuary --demo` itself on a throwaway home and a free port (never the live app's) and opens the thread's task - the scene starts by
// itself, nobody types. The film is THE TASK'S OWN PANEL (no rail, no top bar): the page is drawn at the density that makes that panel 1440
// real pixels wide and the panel alone is photographed as it changes - never scaled up. A still of the same panel is saved at each beat. Nothing is sent: the demo refuses every send, and the scene presses none.
//   node website/record-availability.mjs [--out <folder>] [--name <file name>] [--dark] [--pace <seconds between replies>]
// Playwright is not a dependency of this repository: TASKUARY_PLAYWRIGHT names its package folder where `import "playwright"` finds none.
// The film is put together by the ffmpeg in Playwright's own browsers folder (the one its videos are made with); nothing else is needed.
import { spawn } from "node:child_process";
import { existsSync, readdirSync } from "node:fs";
import { mkdir, mkdtemp, readdir, rm } from "node:fs/promises";
import { createServer } from "node:net";
import os from "node:os";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url)), root = path.resolve(here, "..");
const arg = (k, d = "") => { const i = process.argv.indexOf(`--${k}`); return i < 0 ? d : process.argv[i + 1] ?? "1"; };
const out = path.resolve(arg("out", path.join(root, "docs/product-demo"))), dark = process.argv.includes("--dark"), pace = arg("pace", "2.6");
const TITLE = "Product ideas session - a time next week?", NAME = arg("name", `taskuary-availability${dark ? "-dark" : ""}`);
const W = 1440, H = 900, PANEL = 1018, DPR = 1440 / PANEL, FPS = 30;      // ...the task panel is 1018 of the page's 1440: at this density it is 1440 real pixels
const delay = (ms) => new Promise((r) => setTimeout(r, ms));
const { chromium } = await import(process.env.TASKUARY_PLAYWRIGHT ? pathToFileURL(path.join(process.env.TASKUARY_PLAYWRIGHT, "index.mjs")).href : "playwright");
const ffmpeg = (() => { const dir = process.env.PLAYWRIGHT_BROWSERS_PATH || path.join(process.env.LOCALAPPDATA || path.join(os.homedir(), ".cache"), "ms-playwright");
  const f = existsSync(dir) ? readdirSync(dir).filter((d) => d.startsWith("ffmpeg-")).sort().at(-1) : "";
  const exe = f ? path.join(dir, f, process.platform === "win32" ? "ffmpeg-win64.exe" : process.platform === "darwin" ? "ffmpeg-mac" : "ffmpeg-linux") : "";
  return exe && existsSync(exe) ? exe : ""; })();
if (!ffmpeg) throw new Error("no ffmpeg in Playwright's browsers folder - `playwright install ffmpeg` puts one there");

// ── the demo, on its own home and port ──
const token = "scene-owner-token";
const port = await new Promise((res) => { const s = createServer(); s.listen(0, "127.0.0.1", () => { const p = s.address().port; s.close(() => res(p)); }); });
if (port === 7787) throw new Error("that is the live app's port");
const home = await mkdtemp(path.join(os.tmpdir(), "taskuary-scene-")), url = `http://127.0.0.1:${port}`;
const server = spawn(process.env.TASKUARY_TEST_PYTHON || "python", ["-m", "taskuary.cli", "--demo", "--no-browser", "--port", String(port)], { cwd: root, windowsHide: true, stdio: "ignore",
  env: { ...process.env, PYTHONPATH: root, TASKUARY_HOME: home, TASKUARY_TOKEN: token, TASKUARY_DEMO_SCENE: "availability", TASKUARY_DEMO_SCENE_PACE: pace, TASKUARY_DEMO_OPENS_TOUR: "0" } });
const api = async (p) => (await fetch(url + p, { headers: { "X-Taskuary-Token": token } })).json();
let browser = null; const errors = [], outside = [], held = []; let panel = null, kept = 0, secs = 0;
try {
  for (let i = 0; ; i++) { try { if ((await api("/api/health")).ok) break; } catch { /* not up yet */ } if (i > 240) throw new Error("the demo did not start"); await delay(500); }
  const task = ((await api("/api/tasks")).data || []).find((t) => t.Title === TITLE);
  if (!task) throw new Error("the scene's task is not in this demo");

  // ── the screen ──
  browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: W, height: H }, deviceScaleFactor: DPR, colorScheme: dark ? "dark" : "light" });
  await ctx.addInitScript(([t, d]) => { localStorage.setItem("taskuary_token", t); localStorage.setItem("taskuary.theme", d ? "dark" : "light"); }, [token, dark]);
  const page = await ctx.newPage();
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("request", (r) => { if (!r.url().startsWith(url) && !/^(data|blob):/.test(r.url())) outside.push(r.url()); });
  await mkdir(out, { recursive: true });
  let n = 0;
  const still = async (what) => { await page.screenshot({ path: path.join(out, `${NAME}-${String(++n).padStart(2, "0")}-${what}.png`), clip: panel }); };
  const best = () => page.locator("[data-tq-availability]").first().getAttribute("data-best").catch(() => "");
  const until = async (f, ms = 30000) => { for (const t0 = Date.now(); Date.now() - t0 < ms; await delay(100)) if (await f()) return true; throw new Error("the scene did not get there"); };

  await page.goto(`${url}/#task=${task.TaskId}`, { waitUntil: "domcontentloaded" });
  await page.locator(".tq-aui-input").first().waitFor({ state: "visible", timeout: 60000 }); await page.mouse.move(4, H - 4); await delay(1500);
  // ...the task's own panel: the card that holds its title, its buttons, its chat and its box
  panel = await page.evaluate(() => { let e = document.querySelector(".tq-aui-viewport");
    while (e && !(/TQ-\d+/.test(e.textContent) && e.textContent.includes("Mark done"))) e = e.parentElement;
    const r = e.getBoundingClientRect(); return { x: Math.round(r.x), y: Math.round(r.y), width: Math.round(r.width), height: Math.round(r.height) }; });

  // ── the film: the panel photographed as fast as the browser gives it, each with its time, from here (the page's loading is behind it).
  // The browser's screencast - what Playwright's own video is made of - keeps the page at one pixel a point whatever its density, so the
  // words came out small or stretched; a screenshot is taken at the page's density, and of the panel alone
  const frames = []; let filming = true;
  const film = (async () => { while (filming) { const t = Date.now(); const jpg = await page.screenshot({ type: "jpeg", quality: 93, clip: panel, caret: "initial" }).catch(() => null);
    if (jpg) frames.push({ t, jpg }); } })();
  await still("the-thread");
  await until(async () => !!(await best())); await delay(1600); await still("first-times");
  // ...a still each time the best slot or its count moves, once the view has come to rest. Each time it is shown again the view stands under
  // the newest reply (chatStream.viewHomes), so the chat following its own foot keeps it in sight: `held` is how far its top and its foot
  // stood inside the chat's window at each beat - then down to the invite at the end
  const chat = page.locator(".tq-aui-viewport").first();
  const gap = () => page.evaluate(() => { const c = document.querySelector(".tq-aui-viewport").getBoundingClientRect(), v = document.querySelector(".tq-view[data-tq-view]").getBoundingClientRect();
    return [Math.round(v.top - c.top), Math.round(c.bottom - v.bottom)]; });
  for (let was = await best(), seen = 1; seen < 6;) {
    await until(async () => (await best()) !== was, 20000); was = await best(); seen++;
    await delay(1300); if (seen - 1 !== 3) await still(`reply-${seen - 1}`);
    held.push(await gap());
  }
  await page.locator("[data-tq-review-card]").first().waitFor({ state: "attached", timeout: 20000 });
  await delay(1700); await chat.evaluate((v) => v.scrollTo({ top: v.scrollHeight, behavior: "smooth" }));
  await delay(3000); await still("the-invite");
  await delay(1800);
  filming = false; await film;

  // ── put together: each painted frame held until the next one, at FPS, cut to the panel ──
  const size = (b) => { for (let i = 2; i < b.length;) { if (b[i] !== 0xff) break; const m = b[i + 1], len = b.readUInt16BE(i + 2);
    if (m >= 0xc0 && m <= 0xc3) return [b.readUInt16BE(i + 7), b.readUInt16BE(i + 5)]; i += 2 + len; } return [0, 0]; };
  const [fw, fh] = size(frames[0].jpg), crop = `crop=${Math.floor(fw / 2) * 2}:${Math.floor(fh / 2) * 2}:0:0`;       // ...the encoder takes even sides
  const enc = spawn(ffmpeg, ["-y", "-loglevel", "error", "-f", "image2pipe", "-c:v", "mjpeg", "-framerate", String(FPS), "-i", "pipe:0", "-vf", crop,
    "-c:v", "libvpx", "-b:v", "5M", "-crf", "5", "-deadline", "good", "-an", path.join(out, `${NAME}.webm`)], { windowsHide: true, stdio: ["pipe", "ignore", "pipe"] });
  let said = "", shut = false; enc.stderr.on("data", (d) => { said = (said + d).slice(-600); }); enc.stdin.on("error", () => { shut = true; });
  const t0 = frames[0].t, end = frames.at(-1).t + 400;
  for (let i = 0, f = 0; t0 + (i * 1000) / FPS <= end; i++) { while (f + 1 < frames.length && frames[f + 1].t <= t0 + (i * 1000) / FPS) f++;
    if (shut) break; if (!enc.stdin.write(frames[f].jpg)) await Promise.race([new Promise((r) => enc.stdin.once("drain", r)), delay(5000)]); kept = i + 1; }
  enc.stdin.end(); const code = enc.exitCode ?? await new Promise((r) => enc.on("exit", r));
  if (code) errors.push(`the film was not made (${crop}, frames ${size(frames[0].jpg)}): ${said}`);
  secs = +(kept / FPS).toFixed(1); panel = { ...panel, film: [fw, fh], taken: frames.length, perSecond: +(frames.length / ((frames.at(-1).t - t0) / 1000)).toFixed(1) };
} finally {
  if (browser) await browser.close();
  server.kill(); await delay(1500); await rm(home, { recursive: true, force: true }).catch(() => {});      // ...the demo does not quit from the page: it is this script's to stop
}
console.log(JSON.stringify({ video: path.join(out, `${NAME}.webm`), secs, panel, held, stills: (await readdir(out)).filter((f) => f.startsWith(`${NAME}-`)), errors, outside: [...new Set(outside)] }, null, 2));
if (errors.length || outside.length) process.exitCode = 1;
