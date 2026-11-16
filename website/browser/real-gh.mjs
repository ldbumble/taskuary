// A BULK JOB, WALKED ON THE REAL CLI (not a test: nothing here runs in CI). node real-gh.mjs <name>
// The owner, 2026-11-16: "the goal is to go through all issues on a GitHub repo and close all that don't matter - how will we handle it?".
// Against the instance real-run.mjs keeps up, started with TASKUARY_GITHUB_API at fake_github.py (and TASKUARY_FIXTURE_LOOPBACK=1): the agent
// reads the 40 invented issues, raises the closes as ONE bulk card, he presses it, the bar runs in the card, and the agent hears the run once.
import path from "node:path";
import { api, connect, open, shot, save, sleep, type, buttons, out } from "./real-lib.mjs";
import { record } from "./recorder.mjs";
import { NAMES, sampler, check, rest } from "./real-conv.mjs";

const [name = "gh"] = process.argv.slice(2);
const had = ((await api("/api/connectors"))?.data || []).find((c) => c.Type === "github");
console.log("connector", JSON.stringify(await api("/api/connectors", { ...(had ? { ConnectorId: had.ConnectorId } : {}), Type: "github", Name: "GitHub",
  Secret: "ghp_stand_in", Active: true, Roles: "tool" })).slice(0, 200));
const { browser, page } = await connect();
await page.reload({ waitUntil: "domcontentloaded" }); await sleep(3000);
const t = await api("/api/tasks", { Title: "Tidy the ledger issues", Kind: "general", Summary: "" }).then((x) => x.taskId);
await open(page, t);
await page.waitForSelector("[data-tq-task-page] .tq-aui-input", { visible: true, timeout: 120000 }); await sleep(2000);
const rec = await record(page, path.join(out, "video", `${name}-gh`)), t0 = Date.now(), log = [];
await page.evaluate((tid) => { window.__tid = tid; }, t);
await page.evaluate(sampler, NAMES);
const bulk = () => page.evaluate(() => { const c = document.querySelector("[data-tq-task-page] [data-tq-bulk-card]");
  return c ? { rows: c.querySelectorAll("[data-tq-bulk-row]").length, press: c.querySelector("[data-tq-bulk-press]")?.innerText || "", bar: c.querySelector("[data-tq-bulk-progress]")?.innerText || "",
    open: c.querySelectorAll("[data-tq-bulk-row] textarea, [data-tq-bulk-row] [data-tq-action-card]").length } : null; });
const snap = async (n) => { await shot(page, `${name}-gh-${n}`); const c = await api(`/api/tasks/${t}/conversation`); await save(`${name}-gh-${n}-list.json`, c);
  const s = { s: Math.round((Date.now() - t0) / 1000), working: c.working, queue: c.queue, bulk: await bulk() }; log.push([n, s]); console.log(`[${n}]`, JSON.stringify(s)); };
await type(page, "Go through the open issues on northwind/ledger and close the ones that don't matter any more - stale questions, duplicates, " +
  "things already fixed, old feature ideas nobody asked about again. Keep the live bugs open. Say why for each close.");
await sleep(1500); await snap("0asked");
await rest(page, t, 1200000); await sleep(3000); await snap("1raised");
const b = await bulk();
if (b?.press) {
  await page.evaluate(() => document.querySelector("[data-tq-task-page] [data-tq-bulk-press]").click());
  for (let i = 0; i < 12; i++) { await sleep(700); await snap(`2run-${String(i).padStart(2, "0")}`); }
  await rest(page, t, 600000); await sleep(3000); await snap("3told");
} else console.log("FINDING: no bulk card to press");
const fr = await page.evaluate(() => window.__frames), bad = check(fr);
await save(`${name}-gh-frames.json`, fr); await save(`${name}-gh-findings.txt`, [...new Set(bad)].join("\n") || "no rule broken"); await save(`${name}-gh-steps.json`, log);
await rec.stop({ sheet: 12 });
console.log("TOOK", Math.round((Date.now() - t0) / 1000), "s · RULES BROKEN", new Set(bad).size); console.log([...new Set(bad)].slice(0, 20).join("\n"));
console.log("BUTTONS", (await buttons(page)).slice(0, 300));
await browser.disconnect();
