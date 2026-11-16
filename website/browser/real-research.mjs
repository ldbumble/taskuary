// A RESEARCH REPORT WITH A CHART, WALKED ON THE REAL CLI (not a test: nothing here runs in CI). node real-research.mjs <name> [ask]
// He asks for a short report from published sources with a chart. The CLI researches the web read-only by its own tools; the walk records
// what it does and shows - its steps, the words it says while it works, the view (a chart, a table) - with a frame every 20 s. Nothing is pressed.
import path from "node:path";
import { api, connect, open, shot, save, sleep, type, buttons, out, info } from "./real-lib.mjs";
import { record } from "./recorder.mjs";
import { NAMES, sampler, check, rest } from "./real-conv.mjs";

const [name = "res", ask = "Research how the US office vacancy rate has moved over the last five years, from published sources on the web. " +
  "Give me a short report: the trend, the main reasons, and a chart of the yearly rate, with your sources."] = process.argv.slice(2);
await api("/api/fixture/outbox", {});

const { browser, page } = await connect();
await page.reload({ waitUntil: "domcontentloaded" }); await sleep(3000);
const t = await api("/api/tasks", { Title: "Office vacancy report", Kind: "general", Summary: "" }).then((x) => x.taskId);
await open(page, t);
await page.waitForSelector("[data-tq-task-page] .tq-aui-input", { visible: true, timeout: 120000 });
await sleep(2000);
const rec = await record(page, path.join(out, "video", `${name}-res`)), t0 = Date.now(), log = [];
await page.evaluate((tid) => { window.__tid = tid; }, t);
await page.evaluate(sampler, NAMES);
const snap = async (n) => {
  await shot(page, `${name}-res-${n}`); const c = await api(`/api/tasks/${t}/conversation`); await save(`${name}-res-${n}-list.json`, c);
  const turn = c.items.filter((x) => x.kind === "turn").at(-1) || {};
  const line = await page.evaluate(() => document.querySelector("[data-tq-task-page] [data-tq-working]")?.innerText || "");
  const s = { s: Math.round((Date.now() - t0) / 1000), working: c.working, steps: (turn.steps || []).length, said: String(turn.text || "").slice(0, 160), line: line.slice(0, 120),
    queue: c.queue, views: (await page.evaluate(() => document.querySelectorAll("[data-tq-task-page] .tq-view-el svg, [data-tq-task-page] .tq-view-table").length)) };
  log.push([n, s]); console.log(`[${n}]`, JSON.stringify(s));
};
await type(page, ask); await sleep(1500); await snap("asked");
let n = 0;
while ((await api(`/api/tasks/${t}/conversation`)).working && Date.now() - t0 < 40 * 60000) { await sleep(20000); await snap(`w${String(++n).padStart(3, "0")}`); }
await rest(page, t, 600000); await sleep(3000); await snap("rest");
const reviews = (await api(`/api/tasks/${t}`))?.reviews || [];
console.log("CARDS", JSON.stringify(reviews.reduce((m, r) => ({ ...m, [`${r.Kind}:${r.Status}`]: (m[`${r.Kind}:${r.Status}`] || 0) + 1 }), {})));
const fr = await page.evaluate(() => window.__frames), bad = check(fr);
await save(`${name}-res-frames.json`, fr); await save(`${name}-res-findings.txt`, [...new Set(bad)].join("\n") || "no rule broken"); await save(`${name}-res-steps.json`, log);
await rec.stop({ sheet: 12 });
console.log("TOOK", Math.round((Date.now() - t0) / 1000), "s · FRAMES", fr.length, "RULES BROKEN", new Set(bad).size); console.log([...new Set(bad)].slice(0, 20).join("\n"));
console.log("BUTTONS", (await buttons(page)).slice(0, 300));
await browser.disconnect();
