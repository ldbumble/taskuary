// Whichever browser this machine actually has. Hard-coding Edge meant the shot scripts died with
// "Failed to launch the browser process: Code: 0" on a box where Edge will not run headless.
import { existsSync } from "node:fs";
import puppeteer from "puppeteer-core";

const CANDIDATES = [
  process.env.PUPPETEER_EXECUTABLE_PATH,
  "C:/Program Files/Google/Chrome/Application/chrome.exe",
  "C:/Program Files (x86)/Google/Chrome/Application/chrome.exe",
  "C:/Program Files/Microsoft/Edge/Application/msedge.exe",
  "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
  "/usr/bin/google-chrome",
  "/usr/bin/chromium",
].filter(Boolean);

export async function launch(opts = {}) {
  const tried = [];
  for (const executablePath of CANDIDATES) {
    if (!existsSync(executablePath)) continue;
    try {
      return await puppeteer.launch({ executablePath, headless: "new", args: ["--no-sandbox"], ...opts });
    } catch (e) { tried.push(`${executablePath}: ${e.message.split("\n")[0]}`); }
  }
  throw new Error(`no usable browser.\n${tried.join("\n") || "none of the known paths exist"}`);
}
