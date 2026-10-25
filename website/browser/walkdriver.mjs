// THE DEMO DRIVEN THE WAY THE OWNER DRIVES IT (the 2026-10-25 navigation sweep): a rail row clicked, a row verb pressed wherever it
// stands (on the row or inside a ▾), the dock typed into - for the tests that pin what one press leaves on the canvas and the rail.
import { startHarness } from "./harness.mjs";

export const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
export async function boot(t, opts = {}) {
  const h = await startHarness(opts);
  t.after(() => h.close());
  const page = await h.newPage(), errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(h.ui, { waitUntil: "domcontentloaded", timeout: 30000 });
  await page.waitForSelector("[data-tq-rail] .tq-pile-row", { timeout: 40000 });
  await sleep(2000);
  return { h, page, errors };
}
export const rail = (page) => page.$$eval("[data-tq-rail] .tq-pile-row", (els) => els.map((e) => ({
  key: e.getAttribute("data-tq-key"), cur: e.classList.contains("current"), text: e.innerText.replace(/\s+/g, " ").slice(0, 90) })));
export const ringed = async (page) => (await rail(page)).find((r) => r.cur)?.text || "";
export const findRow = async (page, re) => (await rail(page)).find((r) => re.test(r.text))?.key || null;
export const clickRow = (page, key) => page.evaluate((k) => { const c = document.querySelector(`[data-tq-rail] .tq-pile-row[data-tq-key="${k}"] .card`); c?.click(); return !!c; }, key);
export const pressNext = (page) => page.evaluate(() => { const b = document.querySelector("[data-tq-row] [data-tq-next]"); if (b && !b.disabled) { b.click(); return true; } return false; });
export const clickText = (page, re, scope = "body") => page.evaluate((src, scope) => {
  const rx = new RegExp(src);
  const b = [...document.querySelectorAll(`${scope} button, ${scope} [role=button], ${scope} [role=menuitem]`)]
    .find((n) => rx.test(n.textContent.trim()) && !n.disabled && n.getBoundingClientRect().width > 0);
  if (b) { b.click(); return b.textContent.trim(); } return null;
}, re.source, scope);
// a row verb by its id, on the row or in one of its ▾ menus
export async function doVerb(page, id) {
  const onRow = await page.evaluate((id) => { const b = document.querySelector(`[data-tq-row] button[data-tq-verb="${id}"]`); if (b && !b.disabled) { b.click(); return true; } return false; }, id);
  if (onRow) return "row";
  for (const m of await page.$$eval("[data-tq-row] [data-tq-more]", (e) => e.map((x) => x.dataset.tqMore))) {
    await page.evaluate((m) => document.querySelector(`[data-tq-row] [data-tq-more="${m}"]`).click(), m); await sleep(400);
    const hit = await page.evaluate((id) => { const i = document.querySelector(`[role=menu] [role=menuitem][data-tq-verb="${id}"]`); if (i && i.getAttribute("aria-disabled") !== "true") { i.click(); return true; } return false; }, id);
    if (hit) return `menu:${m}`;
    await page.keyboard.press("Escape"); await sleep(300);
  }
  return null;
}
export const rowVerbs = (page) => page.$$eval("[data-tq-row] .tq-arow-verbs button[data-tq-verb]", (bs) => bs.map((b) => b.dataset.tqVerb));
export const folded = (page) => page.$$eval("[data-tq-folded]", (els) => els.map((e) => ({ title: e.querySelector("b")?.textContent || "",
  badge: e.querySelector("[data-tq-pressed]")?.getAttribute("data-tq-pressed") || null, note: e.querySelector("[data-tq-pressed-note]")?.textContent || null })));
// the chat's bubbles as drawn: the owner's (you), the assistant's and the receipts
export const bubbles = (page) => page.$$eval(".tq-msg", (els) => els.map((e) => ({
  who: e.classList.contains("you") ? "you" : e.classList.contains("receipt") ? "receipt" : "assistant", text: e.innerText.replace(/\s+/g, " ").trim().slice(0, 200) })));
export async function type(page, words) {
  const box = await page.waitForSelector(".tq-compose textarea:not([disabled])", { timeout: 20000 });
  await box.click({ clickCount: 3 }); await box.type(words); await page.keyboard.press("Enter");
}
// every line the chat draws from now on, with its time - a line that stood for a frame counts (MutationObserver)
export const watch = (page) => page.evaluate(() => {
  const t0 = performance.now(), log = [];
  const add = (s, el) => { s = (s || "").trim(); if (s && el?.closest?.(".tq-msg")) log.push({ t: Math.round(performance.now() - t0), s: s.replace(/\s+/g, " ").slice(0, 200),
    you: !!el.closest(".tq-msg.you") }); };
  const mo = new MutationObserver((ms) => { for (const m of ms) for (const n of m.addedNodes) add(n.innerText ?? n.textContent, n.nodeType === 1 ? n : n.parentElement); });
  mo.observe(document.body, { subtree: true, childList: true });
  window.__watchStop = () => { mo.disconnect(); return log; };
});
export const unwatch = (page) => page.evaluate(() => window.__watchStop?.() || []);
export const liveCard = (page) => page.evaluate(() => {
  const c = [...document.querySelectorAll(".tq-canvas-live [data-tq-canvas-item], .tq-canvas-live .tq-card")].filter((x) => x.getBoundingClientRect().height > 0 && !x.closest("[data-tq-folded]")).pop();
  return (c?.innerText || "").replace(/\s+/g, " ").slice(0, 120);
});
