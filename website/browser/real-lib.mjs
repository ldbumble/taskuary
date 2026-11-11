// Drive the instance real-run.mjs keeps up: connect to its browser, press, type, read, record.
import { readFile, writeFile, mkdir } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import puppeteer from "puppeteer-core";
export const out = process.env.REAL_OUT || path.join(os.tmpdir(), "claude", "real");
export const info = JSON.parse(await readFile(path.join(out, "info.json"), "utf8"));
export const api = (p, body, method) => fetch(`${info.api}${p}`, { method: method || (body ? "POST" : "GET"), headers: { "Content-Type": "application/json", "X-Taskuary-Token": info.token }, body: body && JSON.stringify(body) }).then(async (r) => { const t = await r.text(); try { return JSON.parse(t); } catch { return t; } });
export const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
export async function connect() {
  const browser = await puppeteer.connect({ browserWSEndpoint: info.ws, defaultViewport: null });
  const page = (await browser.pages()).find((p) => p.url().startsWith(info.ui));
  return { browser, page };
}
export const open = (page, tid) => page.evaluate((id) => { location.hash = `task=${id}`; }, tid);
export const chat = (page) => page.evaluate(() => document.querySelector("[data-tq-task-page] .tq-aui-viewport")?.innerText || "(no chat)");
export const body = (page) => page.evaluate(() => document.body.innerText);
export async function shot(page, name) { const d = path.join(out, "video"); await mkdir(d, { recursive: true }); const f = path.join(d, `${name}.png`); await page.screenshot({ path: f }); return f; }
export async function type(page, words) {
  await page.waitForFunction(() => { const b = document.querySelector("[data-tq-task-page] .tq-aui-input"); return b && !b.disabled; }, { timeout: 60000 });
  await page.evaluate(() => document.querySelector("[data-tq-task-page] .tq-aui-input").focus());
  await page.keyboard.type(words); await page.keyboard.press("Enter");
}
// press the LAST visible enabled button whose words match - the newest card's
export const press = (page, re, scope = "body") => page.evaluate((src, scope) => {
  const b = [...document.querySelectorAll(`${scope} button`)].filter((b) => new RegExp(src).test(b.innerText.trim()) && !b.disabled && b.getBoundingClientRect().width > 0).pop();
  if (!b) return "no such button; have: " + [...new Set([...document.querySelectorAll(`${scope} button`)].filter((b) => b.getBoundingClientRect().width > 0).map((b) => b.innerText.trim() + (b.disabled ? " (off)" : "")).filter(Boolean))].join(" | ").slice(0, 1500);
  b.click(); return "pressed " + b.innerText.trim();
}, re.source, scope);
export const buttons = (page, scope = "[data-tq-task-page]") => page.evaluate((scope) => [...document.querySelectorAll(`${scope} button`)].filter((b) => b.getBoundingClientRect().width > 0).map((b) => (b.innerText.trim() || b.getAttribute("aria-label") || "?") + (b.disabled ? " (off)" : "")).join(" | "), scope);
export const busy = (page) => page.evaluate(() => !!document.querySelector("[data-tq-task-page] [data-tq-stop-run]"));
export async function quiet(page, timeout = 300000, settle = 2500) {
  const end = Date.now() + timeout; let calm = 0;
  while (Date.now() < end) { if (await busy(page)) calm = 0; else if ((calm += 500) >= settle) return true; await sleep(500); }
  return false;
}
// the chat every `every` ms until `ms` passed: [t, text tail] of each CHANGE - a timeline to read
export async function timeline(page, ms, every = 250, tail = 700) {
  const t0 = Date.now(), seen = []; let last = "";
  while (Date.now() - t0 < ms) {
    const now = await page.evaluate((tail) => { const vp = document.querySelector("[data-tq-task-page] .tq-aui-viewport"); const cards = [...document.querySelectorAll("[data-tq-task-page] textarea")].length;
      return (vp?.innerText || "").slice(-tail) + `\n[busy=${!!document.querySelector("[data-tq-task-page] [data-tq-stop-run]")} textareas=${cards} top=${Math.round(vp?.scrollTop || 0)} h=${vp?.scrollHeight || 0}]`; }, tail);
    if (now !== last) { seen.push([Date.now() - t0, now]); last = now; }
    await sleep(every);
  }
  return seen;
}
export const save = (name, data) => writeFile(path.join(out, name), typeof data === "string" ? data : JSON.stringify(data, null, 1));
