// JOB 1 on a coding task: the agent files its reply mid-turn and goes on working; Send and close is pressed the moment the card shows.
import path from "node:path";
import { api, connect, open, shot, timeline, save, buttons, sleep, type, out, info } from "./real-lib.mjs";
import { record } from "./recorder.mjs";
const [name, re = "^Send and close$", ms = "60000"] = process.argv.slice(2);
if (!process.env.REAL_CODING_UP) console.log("coding", JSON.stringify(await api("/api/fixture/coding", { git: info.git, real: true })).slice(0, 200));
const got = await api("/api/fixture/mail-task", { kind: "coding", title: "Is tax included in the ledger total?" });
console.log("task", JSON.stringify(got));
const { browser, page } = await connect();
await page.reload({ waitUntil: "domcontentloaded" }); await sleep(3000);          // ...an earlier run's observer goes with its page
await open(page, got.taskId);
await page.waitForSelector("[data-tq-task-page] .tq-aui-input", { visible: true, timeout: 60000 });
const rec = await record(page, path.join(out, "video", name));
await shot(page, `${name}-0open`);
await type(page, "Read totals.py. First draft the reply to Erin saying whether tax is included in the total (one or two lines, as a reply for my Send). After that, add a docstring to total() and commit it.");
await page.evaluate((src) => {
  window.__pressed = null;
  const look = () => { if (window.__pressed) return;
    const b = [...document.querySelectorAll("[data-tq-task-page] button")].find((b) => new RegExp(src).test(b.innerText.trim()) && !b.disabled);
    if (b) { window.__pressed = { at: Date.now(), busy: !!document.querySelector("[data-tq-task-page] [data-tq-stop-run]") }; b.click(); obs.disconnect(); } };
  const obs = new MutationObserver(look); obs.observe(document.body, { subtree: true, childList: true, attributes: true }); look();
}, re);
const before = await timeline(page, 8000, 250, 900);
for (let i = 0; i < 400 && !(await page.evaluate(() => window.__pressed)); i++) await sleep(500);
console.log("PRESSED", JSON.stringify(await page.evaluate(() => window.__pressed)));
const tl = await timeline(page, Number(ms), 150, 1500);
await save(`${name}-timeline.json`, [...before, ...tl]);
await shot(page, `${name}-9after`);
await rec.stop({ sheet: 12 });
console.log("TASK", got.taskId, "BUTTONS", await buttons(page));
await browser.disconnect();
