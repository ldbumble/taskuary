// A MULTI-STEP JOB BEHIND A SIGN-IN, WALKED ON THE REAL CLI (not a test: nothing here runs in CI). node real-portal.mjs <name> <site url>
// Against the instance real-run.mjs keeps up with REAL_BROWSER=1 (and TASKUARY_FIXTURE_LOOPBACK=1), and fake_portal.py on loopback: he asks
// for a summary of every payroll run on a portal with no connector. The agent opens the site in its browser; each time a page is handed to
// him beside the chat he types into it (the sign-in, then the code) as he would; the agent pages through the runs and summarises them. Then a
// second task asks the same site again: the saved sign-in should carry it, with no page shown. Frames sampled, the layout read every 200 ms.
import path from "node:path";
import { api, connect, open, shot, save, sleep, type, buttons, out } from "./real-lib.mjs";
import { record } from "./recorder.mjs";
import { NAMES, sampler, check, rest } from "./real-conv.mjs";

const [name = "portal", site = "http://127.0.0.1:18766"] = process.argv.slice(2);
const until = async (f, ms, every = 500) => { const end = Date.now() + ms; while (Date.now() < end) { const v = await f(); if (v) return v; await sleep(every); } return null; };
const pane = (page) => page.evaluate(() => { const c = document.querySelector("[data-tq-task-page] canvas") || document.querySelector("canvas"); if (!c) return null;
  const b = c.getBoundingClientRect(); return b.width ? [b.left, b.top, b.width, b.height] : null; });

async function walk(tag, page, ask, rounds) {
  const t = await api("/api/tasks", { Title: tag === "a" ? "Payroll runs summary" : "Payworth account reference", Kind: "general", Summary: "" }).then((x) => x.taskId);
  await open(page, t);
  await page.waitForSelector("[data-tq-task-page] .tq-aui-input", { visible: true, timeout: 120000 }); await sleep(2000);
  const rec = await record(page, path.join(out, "video", `${name}-${tag}`)), t0 = Date.now(), log = [];
  await page.evaluate((tid) => { window.__tid = tid; }, t); await page.evaluate(sampler, NAMES);
  const snap = async (n) => { await shot(page, `${name}-${tag}-${n}`); const c = await api(`/api/tasks/${t}/conversation`); await save(`${name}-${tag}-${n}-list.json`, c);
    const s = { s: Math.round((Date.now() - t0) / 1000), working: c.working, pane: !!(await pane(page)), asking: c.asking?.request_id || "",
      said: String(c.items.filter((x) => x.kind === "turn").at(-1)?.text || "").slice(0, 200) }; log.push([n, s]); console.log(`[${tag} ${n}]`, JSON.stringify(s)); };
  await type(page, ask); await sleep(1500); await snap("0asked");
  for (const [i, keys] of rounds.entries()) {
    // ...a page handed to him beside the chat, or the agent at rest without one (a finding where one was expected)
    let calm = 0;
    const got = await until(async () => (await pane(page)) || ((await api(`/api/tasks/${t}/conversation`)).working ? (calm = 0, null) : (++calm >= 15 && "rest")), 600000, 2000);
    await snap(`1shown-${i}`);
    if (got === "rest") { console.log(`[${tag}] FINDING: at rest with no page shown for round ${i}`); break; }
    await sleep(2500);
    const [x, y, w, h] = await pane(page);
    await page.mouse.click(x + w / 2, y + h * 0.3); await sleep(500);
    for (const k of keys) { await page.keyboard.press("Tab"); await sleep(250); await page.keyboard.type(k, { delay: 40 }); await sleep(250); }
    await snap(`2typed-${i}`); await page.keyboard.press("Enter"); await sleep(4000); await snap(`3sent-${i}`);
  }
  await rest(page, t, 900000); await sleep(3000); await snap("4end");
  const fr = await page.evaluate(() => window.__frames), bad = check(fr);
  await save(`${name}-${tag}-frames.json`, fr); await save(`${name}-${tag}-findings.txt`, [...new Set(bad)].join("\n") || "no rule broken"); await save(`${name}-${tag}-steps.json`, log);
  await rec.stop({ sheet: 12 });
  console.log(`[${tag}] TOOK`, Math.round((Date.now() - t0) / 1000), "s · RULES BROKEN", new Set(bad).size); console.log([...new Set(bad)].slice(0, 15).join("\n"));
  console.log(`[${tag}] SAID\n` + (await api(`/api/tasks/${t}/conversation`)).items.filter((x) => x.kind === "turn").map((x) => "  > " + String(x.text || "").replace(/\n/g, "\n    ")).join("\n"));
  console.log(`[${tag}] BUTTONS`, (await buttons(page)).slice(0, 300));
}

const { browser, page } = await connect();
await page.reload({ waitUntil: "domcontentloaded" }); await sleep(3000);
await walk("a", page, `Sign in to our Payworth payroll portal at ${site} and go through every page of the payroll runs. Summarise the total gross paid per month, ` +
  "how many runs are still scheduled, and show it as a table.", [["alex", "northwind-pass"], ["424242"]]);
await walk("b", page, `What is our account reference on Payworth (${site})?`, []);
await browser.disconnect();
