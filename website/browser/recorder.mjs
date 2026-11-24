import { execFileSync } from "node:child_process";
import { mkdir, readFile, rm, writeFile } from "node:fs/promises";
import path from "node:path";

/* A SCENARIO'S SCREEN, RECORDED AS THE OWNER WOULD SEE IT (the owner, 2026-11-10: "all ageent audits should be videoing screens if the agent does
   well because that's how users see it"). Chrome's own screencast (CDP Page.startScreencast) writes a numbered JPEG each time the page paints, at
   real speed, with its time; `stop()` keeps them, a frames.json of their times and - with ffmpeg on PATH - a video.mp4 at their real spacing. With
   no ffmpeg a contact sheet (sheet.png, `n` frames evenly spaced, each with its time) is drawn by the same browser. `note()` writes the
   scenario's README.txt: what was done, what should be seen, what was seen, the verdict and the commit. Judge a run by watching it: a flicker,
   a jump, a thing that appears and then moves, or a blank beat is a finding even where every assertion passed. */
const ffmpeg = (() => { try { execFileSync("ffmpeg", ["-version"], { stdio: "ignore" }); return true; } catch { return false; } })();

// A RECORDING HAS A CEILING (2026-11-24: a JPEG per paint, and a spinner paints sixty times a second - a recording left running filled the
// disk). At most `fps` frames a second are kept (a paint sooner than that after the last kept one is acked, not written), and the recording
// stops keeping at `secs` seconds or `mb` megabytes, saying so once. TQ_RECORD_FPS / TQ_RECORD_SECS / TQ_RECORD_MB change the defaults.
const LIMIT = { fps: +process.env.TQ_RECORD_FPS || 20, secs: +process.env.TQ_RECORD_SECS || 600, mb: +process.env.TQ_RECORD_MB || 300 };

export async function record(page, dir, { fps = LIMIT.fps, secs = LIMIT.secs, mb = LIMIT.mb } = {}) {
  await rm(dir, { recursive: true, force: true }); await mkdir(dir, { recursive: true });
  const cdp = await page.createCDPSession(), frames = [], t0 = Date.now(), writes = [];
  let bytes = 0, full = false;
  cdp.on("Page.screencastFrame", ({ data, sessionId, metadata }) => {
    cdp.send("Page.screencastFrameAck", { sessionId }).catch(() => {});
    const ms = Math.round((metadata?.timestamp ? metadata.timestamp * 1000 : Date.now()) - t0);
    if (full || (frames.length && ms - frames.at(-1).ms < 1000 / fps)) return;
    if (ms > secs * 1000 || bytes > mb * 1e6) {
      full = true; console.warn(`recorder: ${dir} stopped keeping frames at ${(ms / 1000).toFixed(0)} s, ${(bytes / 1e6).toFixed(0)} MB`); return;
    }
    const file = `${String(frames.length).padStart(5, "0")}.jpg`, jpg = Buffer.from(data, "base64");
    bytes += jpg.length; frames.push({ file, ms });
    writes.push(writeFile(path.join(dir, file), jpg));
  });
  await cdp.send("Page.startScreencast", { format: "jpeg", quality: 70, everyNthFrame: 1 });
  const stop = async ({ sheet = 12 } = {}) => {
    await cdp.send("Page.stopScreencast").catch(() => {}); await Promise.all(writes); await cdp.detach().catch(() => {});
    const t = frames[0]?.ms || 0; frames.forEach((f) => { f.ms -= t; });
    await writeFile(path.join(dir, "frames.json"), JSON.stringify(frames));
    if (ffmpeg && frames.length > 1) {
      // ...each frame held until the next one painted: the concat list gives every frame its own real duration
      const list = frames.map((f, i) => `file '${f.file}'\nduration ${(((frames[i + 1]?.ms ?? f.ms + 1000) - f.ms) / 1000).toFixed(3)}`).join("\n");
      await writeFile(path.join(dir, "frames.txt"), `${list}\nfile '${frames.at(-1).file}'\n`);
      try { execFileSync("ffmpeg", ["-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", "frames.txt", "-vsync", "vfr", "-pix_fmt", "yuv420p", "video.mp4"], { cwd: dir }); } catch {}
    }
    if (sheet && frames.length) await contactSheet(page.browser(), dir, frames, sheet);
    return frames;
  };
  return { dir, stop, mark: () => Date.now() - t0 };
}

async function contactSheet(browser, dir, frames, n) {
  const pick = [...new Set(Array.from({ length: Math.min(n, frames.length) }, (_, i) => frames[Math.round(i * (frames.length - 1) / Math.max(1, Math.min(n, frames.length) - 1))]))];
  const imgs = await Promise.all(pick.map(async (f) => `<figure><img src="data:image/jpeg;base64,${(await readFile(path.join(dir, f.file))).toString("base64")}"><figcaption>${(f.ms / 1000).toFixed(1)} s · ${f.file}</figcaption></figure>`));
  const p = await browser.newPage();
  try {
    await p.setViewport({ width: 1800, height: 1000 });
    await p.setContent(`<style>body{margin:8px;font:12px sans-serif;display:grid;grid-template-columns:repeat(3,1fr);gap:8px;background:#fff}figure{margin:0}img{width:100%;border:1px solid #ccc}</style>${imgs.join("")}`);
    await p.screenshot({ path: path.join(dir, "sheet.png"), fullPage: true });
  } finally { await p.close(); }
}

export const commit = () => { try { return execFileSync("git", ["rev-parse", "--short", "HEAD"], { encoding: "utf8" }).trim() + (execFileSync("git", ["status", "--porcelain", "--", "../taskuary", "src"], { encoding: "utf8" }).trim() ? " + uncommitted changes" : ""); } catch { return "unknown"; } };

export const note = (dir, { done, expect, saw, verdict }) => writeFile(path.join(dir, "README.txt"),
  `WHAT WAS DONE\n${done}\n\nWHAT SHOULD BE SEEN\n${expect}\n\nWHAT WAS SEEN\n${saw}\n\nVERDICT: ${verdict}\nCOMMIT: ${commit()}\n${ffmpeg ? "video.mp4 at real speed; " : ""}frames *.jpg with their times in frames.json; sheet.png: evenly spaced frames\n`);
