// A PRESS AS A HAND MAKES IT, AND WHAT THE PAGE DID WITH IT (the owner, 2026-11-26: "most buttons on our app you have to click twice for it
// to go? is it that or it just takes a second"). The pointer travels to the button, rests, goes down, comes up ~90 ms later - never
// element.click(), which reaches a button a hand cannot and skips the hover, the focus and the blur a real press sets off. The page logs
// every pointer event with what was under it, whether the click reached the app or was swallowed, where the button stood at down and at up,
// and the first thing that changed on screen after the release.
import { readFile } from "node:fs/promises";
import path from "node:path";
import puppeteer from "puppeteer-core";

export const out = process.env.PRESS_OUT;
export const info = JSON.parse(await readFile(path.join(out, "info.json"), "utf8"));
export const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
export const api = (p, body, method) => fetch(`${info.api}${p}`, { method: method || (body ? "POST" : "GET"), headers: { "Content-Type": "application/json", "X-Taskuary-Token": info.token },
  body: body && JSON.stringify(body) }).then(async (r) => { const t = await r.text(); try { return JSON.parse(t); } catch { return t; } });
export async function connect() {
  const browser = await puppeteer.connect({ browserWSEndpoint: info.ws, defaultViewport: null });
  const page = (await browser.pages()).find((p) => p.url().startsWith(info.ui));
  return { browser, page };
}

const PROBE = () => {
  if (window.__tqPress) return;
  const w = window.__tqPress = { ev: [], mut: [], on: false };
  const desc = (el) => { if (!el || !el.tagName) return String(el?.nodeName || el);
    const b = el.closest?.("button, a[href], [role=button], [role=menuitem], textarea, input") || el;
    const a = [...(b.attributes || [])].filter((x) => x.name.startsWith("data-tq-")).map((x) => x.name).slice(0, 2).join(",");
    return `${b.tagName.toLowerCase()}${b.className && typeof b.className === "string" ? "." + b.className.split(/\s+/).filter((c) => !/^css-|^Mui/.test(c)).slice(0, 2).join(".") : ""}${a ? `[${a}]` : ""} "${(b.innerText || b.getAttribute?.("aria-label") || "").trim().replace(/\s+/g, " ").slice(0, 40)}"${b.disabled ? " (off)" : ""}`; };
  w.desc = desc;
  for (const type of ["pointerdown", "mousedown", "pointerup", "mouseup", "click", "focusin", "focusout"]) {
    window.addEventListener(type, (e) => { if (!w.on) return;
      const r = { type, t: performance.now(), target: desc(e.target), x: e.clientX, y: e.clientY };
      // ...a click the page swallowed never reaches the document's own bubble: read a tick later
      if (type === "click") { r.heard = false; const hear = () => { r.heard = true; }; document.addEventListener("click", hear, { once: true });
        setTimeout(() => { r.prevented = e.defaultPrevented; document.removeEventListener("click", hear); }, 0); }
      w.ev.push(r); }, true);
  }
  // ...what was pressed, kept from its pointerdown: a change on it (greyed, a spinner, its words) is the press answered where it was made
  window.addEventListener("pointerdown", (e) => { w.pressed = e.target.closest?.("button, a[href], [role=button], [role=menuitem], label") || e.target; }, true);
  const own = (m, el) => !!w.pressed && (w.pressed.contains(el) || [...(m.removedNodes || [])].some((n) => n === w.pressed || n.contains?.(w.pressed)));
  new MutationObserver((ms) => { if (!w.on) return; const t = performance.now();
    for (const m of ms) { if (w.mut.length > 3000) break; const el = m.target.nodeType === 1 ? m.target : m.target.parentElement;
      // ...the caret, a clock and the pointer's own ripple are not the press's answer
      if (!el || el.closest(".MuiTouchRipple-root, [data-tq-clock]")) continue;
      w.mut.push({ t, own: own(m, el), kind: m.type === "attributes" ? `@${m.attributeName}` : m.type, on: desc(el).slice(0, 90) }); } })
    .observe(document.body, { childList: true, subtree: true, attributes: true, characterData: true });
};

// where a thing stands now: its centre, whether it is the thing under its own centre, and whether it takes a press
const at = (page, find) => page.evaluate((src) => {
  const el = eval(src)(); if (!el) return null;
  el.scrollIntoView?.({ block: "nearest" });
  if (!el.getBoundingClientRect().width) return null;     // there, and not drawn: nothing a hand can press
  const r = el.getBoundingClientRect(), x = r.x + r.width / 2, y = r.y + r.height / 2, top = document.elementFromPoint(x, y);
  return { x, y, w: r.width, h: r.height, name: window.__tqPress.desc(el), off: el.matches(":disabled") || !!el.closest("[inert], [aria-disabled=true]"),
    covered: !(top && (el.contains(top) || top.contains(el))) ? window.__tqPress.desc(top) : "" };
}, find.toString());

// `find`: a function run in the page that returns the element (as a hand finds it: by what it says). `from`: where the pointer comes from.
// `rest`: how long it rests on the button before the press; `hold`: down to up. Returns the press's own log.
export async function press(page, find, { from = null, rest = 140, hold = 90, watch = 3000, changed = null, still = false } = {}) {
  await page.evaluate(PROBE);
  const a = await at(page, find);
  if (!a) return { ok: false, why: "not on screen" };
  const start = from || { x: Math.max(40, a.x - 320), y: Math.max(40, a.y - 180) };
  // ...`still`: the pointer is where the last press left it - a hand that presses the same button again does not move
  if (!still) { await page.mouse.move(start.x, start.y); await sleep(60); }
  // ...the pointer's own travel, ~250 ms: what grows, opens or lights under a hover does so before the press, as it does for a hand
  for (let i = 1; i <= 12 && !still; i++) { await page.mouse.move(start.x + (a.x - start.x) * i / 12, start.y + (a.y - start.y) * i / 12); await sleep(20); }
  await sleep(rest);
  const before = await at(page, find);
  await page.evaluate(() => { const w = window.__tqPress; w.ev = []; w.mut = []; w.on = true; });
  const tx = before?.x ?? a.x, ty = before?.y ?? a.y;
  if (!still) await page.mouse.move(tx, ty);
  await page.mouse.down(); await sleep(hold);
  const mid = await at(page, find);
  await page.mouse.up();
  const t0 = Date.now(); let did = null;
  while (Date.now() - t0 < watch) { if (changed && (did = await page.evaluate((s) => eval(s)(), changed.toString()))) break; await sleep(25); }
  if (!changed) await sleep(0);
  const log = await page.evaluate(() => { const w = window.__tqPress; w.on = false; return { ev: w.ev, mut: w.mut }; });
  const up = log.ev.find((e) => e.type === "mouseup"), down = log.ev.find((e) => e.type === "mousedown"), click = log.ev.find((e) => e.type === "click");
  const firstAfter = (t) => log.mut.find((m) => m.t >= t);
  const moved = before && mid ? Math.round(Math.hypot(mid.x - before.x, mid.y - before.y)) : null;
  return { ok: true, name: a.name, aimed: { x: Math.round(tx), y: Math.round(ty) }, off: !!before?.off, covered: before?.covered || "",
    down: down?.target, up: up?.target, click: click ? { target: click.target, heard: click.heard, prevented: !!click.prevented } : null,
    movedWhileHeld: moved, standsAtUp: mid ? { x: Math.round(mid.x), y: Math.round(mid.y), covered: mid.covered } : "gone",
    msDownToFirstChange: down && firstAfter(down.t) ? Math.round(firstAfter(down.t).t - down.t) : null,
    msUpToFirstChange: up && firstAfter(up.t) ? Math.round(firstAfter(up.t).t - up.t) : null, firstChange: up && firstAfter(up.t) ? `${firstAfter(up.t).kind} ${firstAfter(up.t).on}` : "",
    msUpToOwnChange: up && log.mut.find((m) => m.own && m.t >= down.t) ? Math.round(log.mut.find((m) => m.own && m.t >= down.t).t - up.t) : null,
    msUpToDone: did ? Date.now() - t0 : null, did: changed ? !!did : undefined,
    focus: log.ev.filter((e) => e.type.startsWith("focus")).map((e) => `${e.type}:${e.target.slice(0, 40)}`).slice(0, 6) };
}
export const say = (label, r) => console.log(`${label}: ${JSON.stringify(r, null, 1)}`);

// EVERY ANSWER FROM THE SERVER `ms` LATE, as on a busy day or a big mailbox: what a press shows before its answer is what he sees while he
// wonders whether it took (0 = as it is)
export const slow = (page, ms) => page.evaluate((ms) => {
  if (!window.__tqSlow) { window.__tqSlow = { ms: 0 }; const send = XMLHttpRequest.prototype.send, f = window.fetch;
    XMLHttpRequest.prototype.send = function (...a) { const d = window.__tqSlow.ms; if (d) setTimeout(() => send.apply(this, a), d); else send.apply(this, a); };
    window.fetch = (...a) => { const d = window.__tqSlow.ms; return d ? new Promise((r) => setTimeout(r, d)).then(() => f(...a)) : f(...a); }; }
  window.__tqSlow.ms = ms; }, ms);
