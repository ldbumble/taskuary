// JOB 1: the card's button pressed the moment it shows, while the agent's turn is still running. node real-j1.mjs <name> [button regex] [watch ms after press] [subject]
import path from "node:path";
import { api, connect, open, shot, timeline, save, buttons, sleep, out } from "./real-lib.mjs";
import { record } from "./recorder.mjs";
const [name, re = "^Send and close$", ms = "150000", what = "an internal team wiki"] = process.argv.slice(2);
const got = await api("/api/ingest/push", { channel: "email", subject: `Open-source options for ${what}`, from_name: "Gail Moreno", from_email: "gail@northwind.example",
  body: `Hi Alex,\n\nCould you find me three open-source options for ${what} that we could self-host? Please research it properly: for each one read its own site and its repository for the licence, the latest release and how active it is, and compare how hard each is to install - then a short paragraph on each and which you would pick.\n\nThanks,\nGail` });
console.log("push", JSON.stringify(got).slice(0, 300));
const { browser, page } = await connect();
await page.reload({ waitUntil: "domcontentloaded" }); await sleep(3000);          // ...an earlier run's observer goes with its page
await open(page, got.task_id);
const rec = await record(page, path.join(out, "video", name));
await page.evaluate((src) => {
  window.__pressed = null;
  const look = () => { if (window.__pressed) return;
    const b = [...document.querySelectorAll("[data-tq-task-page] button")].find((b) => new RegExp(src).test(b.innerText.trim()) && !b.disabled);
    if (b) { window.__pressed = { at: Date.now(), busy: !!document.querySelector("[data-tq-task-page] [data-tq-stop-run]") }; b.click(); obs.disconnect(); } };
  const obs = new MutationObserver(look); obs.observe(document.body, { subtree: true, childList: true, attributes: true }); look();
}, re);
await page.waitForFunction(() => window.__pressed, { timeout: 400000, polling: 200 });
console.log("PRESSED", JSON.stringify(await page.evaluate(() => window.__pressed)));
const tl = await timeline(page, Number(ms), 150, 1800);
await save(`${name}-timeline.json`, tl);
await shot(page, `${name}-9after`);
await rec.stop({ sheet: 12 });
console.log(tl.map(([t, s]) => `--- ${t} ms\n${s}`).join("\n").slice(-5000));
console.log("TASK", got.task_id, "BUTTONS", await buttons(page));
await browser.disconnect();
