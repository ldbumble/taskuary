// The README hero: the Assistant's Game view - the office every task, message and agent lives in - opening on the whole
// floor and zooming into each room in turn (the owner, 2026-10-08: "the main hero shot should be of the game in the assistant
// ... as long as you can zoom in to different sections"). Real UI, the demo's fictional data; nothing is connected.
// npm exec --yes --package=node@22 -- node website/capture-hero.mjs [--probe]      (FFMPEG_PATH, or python with imageio_ffmpeg)
import { createServer } from 'vite';
import { mkdir, writeFile, rm } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { execFileSync } from 'node:child_process';
import { launch } from './browser.mjs';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const scratch = path.join(root, '.codex-tmp/hero');
await rm(scratch, { recursive: true, force: true }); await mkdir(scratch, { recursive: true });
const W = 1280, H = 810;                       // the frame; the GIF is scaled to 960 wide like the old hero
const server = await createServer({ root: path.join(root, 'website'), mode: 'demo', logLevel: 'error', server: { host: '127.0.0.1', port: 0 } });
await server.listen();
const origin = `http://127.0.0.1:${server.httpServer.address().port}`;
const browser = await launch({ args: ['--no-sandbox', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
const page = await browser.newPage();
const errors = [];
page.on('pageerror', (e) => errors.push(e.message));
const delay = (ms) => new Promise((r) => setTimeout(r, ms));
await page.setViewport({ width: W, height: H, deviceScaleFactor: 1 });
let n = 0;
const frame = async () => page.screenshot({ path: path.join(scratch, `f${String(n++).padStart(4, '0')}.png`) });
const hold = async (ms, every = 100) => { for (let t = 0; t < ms; t += every) { await frame(); await delay(every); } };
try {
  await page.goto(origin + '/?demo=explore', { waitUntil: 'networkidle0', timeout: 120000 });
  await page.evaluate(() => [...document.querySelectorAll('button')].find((b) => b.textContent.trim() === 'Game')?.click());
  await delay(6000);                           // the scene loads lazily and settles its camera
  await page.mouse.move(W - 4, H - 4);
  if (process.argv.includes('--probe')) {
    await page.screenshot({ path: path.join(scratch, 'probe.png') });
    await writeFile(path.join(scratch, 'probe.txt'), await page.evaluate(() => document.body.innerText));
    console.log('probe', errors);
  } else {
    const frames = [];
    const shot = async (dur) => { const f = path.join(scratch, `f${String(frames.length).padStart(4, '0')}.png`); await page.screenshot({ path: f }); frames.push([f, dur]); };
    const fly = async (ms = 1400) => { for (let t = 0; t < ms; t += 90) { await shot(0.09); await delay(60); } };     // the camera move, every step
    const stay = async (ms = 1800) => { for (let t = 0; t < ms; t += 300) { await shot(0.3); await delay(250); } };  // the room, alive but light
    // the rooms by their own hotkeys (assistantGame.ZONES: 1 floor, 2 gym, 3 meeting, 4 coffee, 5 archive, 6 core; Esc the whole office)
    const key = async (k) => { await page.keyboard.press(k); };
    await stay(2400);                                               // the whole office first
    for (const k of ['1', '3', '2', '4', '5', '6']) { await key(k); await fly(); await stay(); }
    await key('Escape'); await fly(); await stay(1500);
    if (errors.length) throw new Error(errors.join('\n'));
    const list = path.join(scratch, 'frames.txt');
    await writeFile(list, frames.map(([f, d]) => `file '${f.replaceAll('\\', '/')}'\nduration ${d}`).join('\n') + `\nfile '${frames.at(-1)[0].replaceAll('\\', '/')}'\n`);
    const ffmpeg = process.env.FFMPEG_PATH || execFileSync('python', ['-c', 'import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())'], { encoding: 'utf8' }).trim();
    execFileSync(ffmpeg, ['-y', '-v', 'error', '-f', 'concat', '-safe', '0', '-i', list, '-filter_complex',
      'scale=960:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=192:stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=4:diff_mode=rectangle',
      '-loop', '0', path.join(root, 'docs/hero.gif')]);
    console.log(`hero: ${frames.length} frames`);
  }
} finally { await browser.close(); await server.close(); }
