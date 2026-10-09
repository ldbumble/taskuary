// The README hero: the Assistant's Game view - the office every task, message and agent lives in - opening on the whole
// floor and zooming into each room in turn (the owner, 2026-10-08: "the main hero shot should be of the game in the assistant
// ... as long as you can zoom in to different sections"). Real UI, the demo's fictional data; nothing is connected.
// npm exec --yes --package=node@22 -- node website/capture-hero.mjs [--probe | --encode]   (FFMPEG_PATH, or python with imageio_ffmpeg)
//   --encode re-encodes the frames already in .codex-tmp/hero without opening a browser
import { createServer } from 'vite';
import { mkdir, writeFile, rm, copyFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { execFileSync } from 'node:child_process';
import { launch } from './browser.mjs';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const scratch = path.join(root, '.codex-tmp/hero');
const W = 1280, H = 810, FPS = 20;
// An animated WebP, not a GIF (2026-10-09): smooth camera flights change every pixel of every frame, and 256 colours a
// frame put 20 fps of them at 20 MB; WebP carries the same motion at a third of that. GitHub and PyPI show it like an image.
const encode = () => {
  const ffmpeg = process.env.FFMPEG_PATH || execFileSync('python', ['-c', 'import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())'], { encoding: 'utf8' }).trim();
  execFileSync(ffmpeg, ['-y', '-v', 'error', '-framerate', String(FPS), '-i', path.join(scratch, '%05d.png'), '-vf', 'scale=1120:-1:flags=lanczos',
    '-c:v', 'libwebp_anim', '-quality', '72', '-compression_level', '6', '-loop', '0', path.join(root, 'docs/hero.webp')]);
};
if (process.argv.includes('--encode')) { encode(); process.exit(0); }

await rm(scratch, { recursive: true, force: true }); await mkdir(scratch, { recursive: true });
const server = await createServer({ root: path.join(root, 'website'), mode: 'demo', logLevel: 'error', server: { host: '127.0.0.1', port: 0 } });
await server.listen();
const origin = `http://127.0.0.1:${server.httpServer.address().port}`;
const browser = await launch({ args: ['--no-sandbox', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
const page = await browser.newPage();
const errors = [];
page.on('pageerror', (e) => errors.push(e.message));
const delay = (ms) => new Promise((r) => setTimeout(r, ms));
await page.setViewport({ width: W, height: H, deviceScaleFactor: 1 });
// THE CLOCK IS OURS (2026-10-09, the owner: "the movement looks stilted"): frames were taken whenever a screenshot finished
// and played back at a fixed rate - and ffmpeg's concat snapped those rates to a 25 fps grid besides - so the camera lurched.
// Now the scene's time (performance.now and requestAnimationFrame, which drive its camera flights and walkers) moves only
// when tick() says, by exactly one frame per screenshot, and every frame lands on one 20 fps sequence.
await page.evaluateOnNewDocument(() => {
  const real = performance.now.bind(performance), raf = window.requestAnimationFrame.bind(window);
  let t = 0, held = false, q = [];
  performance.now = () => held ? t : real();
  window.requestAnimationFrame = (cb) => held ? (q.push(cb), q.length) : raf(cb);
  window.__hold = () => { t = real(); held = true; };
  window.__tick = (ms) => { t += ms; const run = q; q = []; run.forEach((cb) => cb(t)); };
});
try {
  await page.goto(origin + '/?demo=explore', { waitUntil: 'networkidle0', timeout: 120000 });
  await page.evaluate(() => [...document.querySelectorAll('button')].find((b) => b.textContent.trim() === 'Game')?.click());
  await page.waitForSelector('canvas', { timeout: 60000 });     // a blank page is no hero (two captures at once share Vite's cache)
  await delay(6000);                           // the scene loads lazily and settles its camera
  await page.mouse.move(W - 4, H - 4);
  if (process.argv.includes('--probe')) {
    await page.screenshot({ path: path.join(scratch, 'probe.png') });
    await writeFile(path.join(scratch, 'probe.txt'), await page.evaluate(() => document.body.innerText));
    console.log('probe', errors);
  } else {
    const cdp = await page.createCDPSession(), step = 1000 / FPS;
    let n = 0;
    await page.evaluate(() => window.__hold());
    // one screenshot per `ms` of scene time; a slower beat repeats its frame so the sequence keeps one rate
    const shot = async (ms) => { await page.evaluate((ms) => window.__tick(ms), ms);
      const f = path.join(scratch, `${String(n++).padStart(5, '0')}.png`); await page.screenshot({ path: f });
      for (let i = 1; i < ms / step; i++) await copyFile(f, path.join(scratch, `${String(n++).padStart(5, '0')}.png`)); };
    // CSS (the room panels sliding in) keeps real time; slowed to the pace frames are taken, it moves with the camera
    const t0 = Date.now(); for (let i = 0; i < 5; i++) await shot(step);
    await cdp.send('Animation.enable'); await cdp.send('Animation.setPlaybackRate', { playbackRate: Math.min(1, step / ((Date.now() - t0) / 5)) });
    // a flight is as long as GameScene's (0.85 s) plus a beat, every frame; a room holds at half that, which its walkers carry
    const fly = async (ms = 1000) => { for (let t = 0; t < ms; t += step) await shot(step); };
    const stay = async (ms = 1900) => { for (let t = 0; t < ms; t += 2 * step) await shot(2 * step); };
    // the rooms by their own hotkeys (assistantGame.ZONES: 1 floor, 2 gym, 3 meeting, 4 coffee, 5 archive, 6 core; Esc the whole office)
    await stay(2400);                                               // the whole office first
    for (const k of ['1', '3', '2', '4', '5', '6']) { await page.keyboard.press(k); await fly(); await stay(); }
    await page.keyboard.press('Escape'); await fly(); await stay(1800);
    if (errors.length) throw new Error(errors.join('\n'));
    encode();
    console.log(`hero: ${n} frames at ${FPS} fps`);
  }
} finally { await browser.close(); await server.close(); }
