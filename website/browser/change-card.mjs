// A CHANGE CARD, DRAWN, EDITED AND PRESSED (not a test: nothing here runs in CI). node browser/change-card.mjs <out folder>
// The owner, 2026-11-24, over a routine's change card whose box held "prompt: <whole old> -> <whole new>": "to edit text it should show the edited
// text?" - its new words whole, marked where they change, his to edit; what he leaves in the box is what the press saves. A routine of his and the
// agent's ask to change it (fixture change-card), the card shot light and dark, marks on and off, then edited, pressed and recorded, and the
// routine read back.
import path from "node:path";
import { mkdir, writeFile } from "node:fs/promises";
import { startHarness } from "./harness.mjs";
import { record } from "./recorder.mjs";

const OUT = process.argv[2] || path.resolve("change-card-out"), sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const WAS = "Write three LinkedIn posts a week about what Northwind learned. Each post should be long and detailed, around 300 words, with a story, three lessons and a question at the end.";
const NOW = "Write three LinkedIn posts a week about what Northwind learned. Keep each post short, under 80 words: one lesson and a question at the end.";
const EDIT = " No hashtags.";
const h = await startHarness({ fresh: true });
const api = (p, body) => fetch(`${h.fixtureApi}${p}`, { method: body ? "POST" : "GET", headers: { "Content-Type": "application/json", "X-Taskuary-Token": h.token },
  body: body && JSON.stringify(body) }).then((r) => r.json());
const said = [];
try {
  await api("/api/setup/first-run/ai", { name: "claude" }); await api("/api/setup/dismiss", { dismissed: true });
  const fx = await api("/api/fixture/change-card", { was: WAS, now: NOW });
  said.push(`seeded: ${JSON.stringify(fx)}`);
  await mkdir(OUT, { recursive: true });
  const page = await h.newPage(), errors = [];
  page.on("pageerror", (e) => errors.push(e.message)); page.on("console", (m) => { if (m.type() === "error") errors.push(m.text().slice(0, 300)); });
  page.on("request", (r) => { if (/\/decide$/.test(r.url())) said.push(`  -> POST decide ${(r.postData() || "").slice(0, 300)}`); });
  page.on("response", async (r) => { if (/\/decide$/.test(r.url())) said.push(`  <- ${r.status()} ${(await r.text().catch(() => "")).slice(0, 300)}`); });
  await page.setViewport({ width: 1440, height: 1000 });
  const stage = () => page.goto(`${h.ui}/browser/onecard-preview.html?task=${fx.taskId}`, { waitUntil: "domcontentloaded" })
    .then(() => page.waitForSelector("[data-tq-task-page] [data-tq-review-card]", { visible: true, timeout: 60000 })).then(() => sleep(1200));
  const shot = async (name) => { const el = await page.$("[data-tq-task-page] [data-tq-review-card]"); if (el) await el.screenshot({ path: path.join(OUT, `${name}.png`) }); };
  const text = () => page.evaluate(() => document.querySelector("[data-tq-task-page] [data-tq-review-card]")?.innerText || "");
  for (const theme of ["light", "dark"]) {
    await page.emulateMediaFeatures([{ name: "prefers-color-scheme", value: theme }]);
    await stage(); await shot(`card-${theme}`);
    said.push(`card ${theme}:\n${(await text()).split("\n").map((l) => `    ${l}`).join("\n")}`);
  }
  await page.emulateMediaFeatures([{ name: "prefers-color-scheme", value: "light" }]);
  await stage();
  const toggle = async () => page.evaluate(() => [...document.querySelectorAll("[data-tq-show-command]")].find((x) => /what changed/.test(x.innerText))?.click());
  await toggle(); await sleep(300); await shot("card-marks-off"); said.push(`marks off: ${await page.evaluate(() => document.querySelector("[data-tq-change]")?.dataset.tqMarks)}`);
  await toggle(); await sleep(300);
  const rec = await record(page, path.join(OUT, "video", "edit-and-approve"), { secs: 25, mb: 40 });
  await page.evaluate(() => { window.__look = []; const t0 = performance.now(); const tick = () => { const c = document.querySelector("[data-tq-task-page] [data-tq-review-card]"), b = c?.getBoundingClientRect();
    window.__look.push([Math.round(performance.now() - t0), Math.round(b?.top || 0), Math.round(b?.height || 0), c?.getAttribute("data-tq-act-state") || ""]); if (window.__look.length < 900) requestAnimationFrame(tick); };
    requestAnimationFrame(tick); });
  await page.click("[data-tq-change-text]"); await sleep(400);
  said.push(`clicked in: box focused ${await page.evaluate(() => document.activeElement?.matches("textarea[data-tq-change-box]"))}`);
  await page.keyboard.press("End"); await page.evaluate(() => { const t = document.activeElement; t.setSelectionRange(t.value.length, t.value.length); });
  await page.keyboard.type(EDIT, { delay: 25 }); await sleep(500); await shot("card-edited");
  said.push(`added marks while typing: ${await page.evaluate(() => [...document.querySelectorAll("[data-tq-change] mark[data-tq-added]")].map((m) => JSON.stringify(m.textContent)).join(", "))}`);
  const pressed = await page.evaluate(() => { const b = [...document.querySelectorAll("[data-tq-task-page] [data-tq-review-card] button")].find((x) => x.innerText.trim() === "Approve");
    if (!b) return "no Approve"; b.click(); return "Approve"; });
  await sleep(6000); await shot("card-approved");
  await rec.stop({ sheet: 8 });
  const look = await page.evaluate(() => window.__look), hs = look.map((x) => x[2]);
  said.push(`pressed ${pressed}; tops ${[...new Set(look.map((x) => x[1]))].join("/")}; states ${[...new Set(look.map((x) => x[3]))].join(" -> ")}; height jumps >40px: ${hs.filter((x, i) => i && Math.abs(x - hs[i - 1]) > 40).length}`);
  said.push(`after the press:\n${(await text()).split("\n").map((l) => `    ${l}`).join("\n")}`);
  const cfg = await api(`/api/fixture/routine/${fx.sourceId}`);
  said.push(`routine saved: ${JSON.stringify(cfg.prompt)}\n  is the edit: ${cfg.prompt === NOW + EDIT}`);
  said.push(`page errors: ${errors.length ? errors.join(" || ") : "none"}`);
} finally {
  await writeFile(path.join(OUT, "README.txt"), said.join("\n") + "\n");
  console.log(said.join("\n"));
  await h.close();
}
