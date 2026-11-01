// Before/after frames of each walk move on the walk table's world, for a person to look at (not a test): node browser/walk-shots.mjs <dir>
import fs from "node:fs";
import path from "node:path";
import { boot, clickRow, clickText, doVerb, pressNext, sleep } from "./walkdriver.mjs";

const out = process.argv[2];
fs.mkdirSync(out, { recursive: true });
const t = { after: (f) => { t.done = f; } };
const { h, page } = await boot(t, { width: 1440, height: 900 });
const api = (p, body) => fetch(`${h.fixtureApi}${p}`, { method: "POST", headers: { "X-Taskuary-Token": h.token, "Content-Type": "application/json" },
  body: JSON.stringify(body || {}) }).then((r) => r.json());
page.off("request", page.fixtureRequestGuard);
page.on("request", async (req) => {
  const rid = (new URL(req.url()).pathname.match(/^\/api\/reviews\/(\d+)\/decide$/) || [])[1];
  if (req.method() === "POST" && rid) {
    await api(`/api/fixture/review/${rid}/sent`, {});
    return req.respond({ status: 200, contentType: "application/json", body: JSON.stringify({ ok: true, status: "approved", sent: { channel: "email" }, send_error: null }) });
  }
  page.fixtureRequestGuard(req);
});
const settle = async () => { await sleep(1500); for (let i = 0; i < 40 && await page.$(".tq-typing"); i++) await sleep(250); await sleep(1200); };
const fresh = async () => {
  const w = await api("/api/fixture/walk/world");
  await page.reload({ waitUntil: "domcontentloaded" }); await page.waitForSelector("[data-tq-rail] .tq-pile-row", { timeout: 40000 }); await sleep(2000);
  await page.evaluate(() => document.querySelector('button[aria-label^="New chat"]')?.click());
  await page.waitForSelector(".tq-welcome .tq-chip.primary:not([disabled])", { timeout: 30000 }); await sleep(800);
  return w.keys;
};
const shot = (name) => page.screenshot({ path: path.join(out, `${name}.png`) });
const moves = [
  ["next", (k) => clickRow(page, k.T2), () => pressNext(page)],
  ["back", (k) => clickRow(page, k.T4), () => page.evaluate(() => document.querySelector("[data-tq-walk-back]")?.click())],
  ["mark-done", (k) => clickRow(page, k.T2), () => doVerb(page, "done")],
  ["send-closes", (k) => clickRow(page, k.T4), () => page.evaluate(() => { const b = [...document.querySelectorAll("[data-tq-closeout] button, .tq-canvas-live button")]
    .find((x) => /^Send\b/.test(x.textContent.trim()) && !x.disabled && x.offsetParent); b?.click(); return !!b; })],
  ["remind-me", (k) => clickRow(page, k.T2), async () => { await doVerb(page, "remind"); await sleep(700); return clickText(page, /^Tomorrow/, ".MuiPopover-paper"); }],
  ["not-a-task", (k) => clickRow(page, k.T5), () => doVerb(page, "nat")],
];
for (const [name, open, press] of moves) {
  try {
    const k = await fresh();
    await open(k); await settle();
    await shot(`${name}-1-before`);
    await press(); await settle();
    await shot(`${name}-2-after`);
    console.log("shot", name);
  } catch (e) { console.log("failed", name, e.message); }
}
await t.done?.();
process.exit(0);
