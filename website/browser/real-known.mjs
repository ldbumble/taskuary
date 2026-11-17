// WHAT IS ALREADY KNOWN, WALKED ON THE REAL CLI (not a test: nothing here runs in CI). node real-known.mjs <name>, against real-run.mjs's instance.
// known_world.py seeds a home whose Hub, closed tasks and repository map already say where an internal app's code and live data are; a
// colleague's ask about one record in that app arrives and its general agent starts as arrival starts it. Recorded: the screen, the agent's
// steps in order, the turn's time and every AI call's tokens - so one checkout's first steps can be read against another's. A read the gate
// holds is approved at once (counted): the walk measures how the agent looks, not how fast a person presses.
import path from "node:path";
import { execFileSync } from "node:child_process";
import { api, connect, open, shot, save, sleep, out, info } from "./real-lib.mjs";
import { record } from "./recorder.mjs";

const [name = "known"] = process.argv.slice(2);
const here = path.dirname(new URL(import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1"));
const repo = process.env.REAL_REPO || path.resolve(here, "..", "..");
const py = (file, args = []) => execFileSync(process.env.TASKUARY_TEST_PYTHON || "python", [file, ...args], { encoding: "utf8",
  env: { ...process.env, TASKUARY_HOME: info.home, PYTHONPATH: repo, PYTHONIOENCODING: "utf-8" } });
const { taskId: t } = JSON.parse(py(path.join(here, "known_world.py")).trim().split(/\r?\n/).at(-1));
console.log("task", t, "code under test", repo);

const { browser, page } = await connect();
await page.reload({ waitUntil: "domcontentloaded" }); await sleep(3000);
await open(page, t);
await page.waitForSelector("[data-tq-task-page]", { visible: true, timeout: 120000 });
const rec = await record(page, path.join(out, "video", name)), t0 = Date.now(), log = [];
await api("/api/fixture/general/start", { taskId: t });
let approved = 0, n = 0, busySince = null;
const approve = () => page.evaluate(() => {
  const b = [...document.querySelectorAll("[data-tq-task-page] button")].find((b) => /^(Approve|Allow|Allow once)$/.test(b.innerText.trim()) && !b.disabled && b.getBoundingClientRect().width > 0);
  if (b) { b.click(); return b.innerText.trim(); } return "";
});
while (Date.now() - t0 < 25 * 60000) {
  if (await approve()) { approved++; console.log(`[${Math.round((Date.now() - t0) / 1000)}s] approved a held step`); }
  const c = await api(`/api/tasks/${t}/conversation`);
  if (c.working) busySince ??= Date.now();
  if (++n % 8 === 0) { const turn = (c.items || []).filter((x) => x.kind === "turn").at(-1) || {};
    log.push({ s: Math.round((Date.now() - t0) / 1000), working: c.working, steps: (turn.steps || []).length }); console.log(JSON.stringify(log.at(-1))); }
  if (busySince && !c.working && Date.now() - busySince > 5000) break;
  await sleep(2000);
}
await sleep(3000); await shot(page, `${name}-rest`);
const c = await api(`/api/tasks/${t}/conversation`);
await save(`${name}-conversation.json`, c);
const took = Math.round((Date.now() - t0) / 1000);
await rec.stop({ sheet: 12 });
// ...the AI it used, per call, as the router kept it - and the turn's steps in order
const used = execFileSync(process.env.TASKUARY_TEST_PYTHON || "python", ["-c",
  `import json,sqlite3,sys; cx=sqlite3.connect(sys.argv[1]); cx.row_factory=sqlite3.Row
print(json.dumps([dict(r) for r in cx.execute("SELECT Job,Pick,Ran,Ms,TokensIn,Cached,TokensOut,Calls FROM brainroute WHERE TaskId=? ORDER BY Id",(int(sys.argv[2]),))]))`,
  path.join(info.home, "taskuary.db"), String(t)], { encoding: "utf8" });
const steps = (c.items || []).filter((x) => x.kind === "turn").flatMap((x) => (x.steps || []).map((s) => s.label || s.text || s.name || JSON.stringify(s).slice(0, 160)));
const report = { name, task: t, took_s: took, approved, ai: JSON.parse(used), steps };
await save(`${name}-report.json`, report);
console.log("REPORT", JSON.stringify({ ...report, steps: steps.slice(0, 25) }, null, 1));
await browser.disconnect();
