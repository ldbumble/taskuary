// A LARGE TASK, WALKED ON THE REAL CLI (not a test: nothing here runs in CI). node real-big.mjs <name> [ask]
// The owner, 2026-11-16: "research 100 commercial properties that look distressed and reach out to the owners to buy". Against the instance
// real-run.mjs keeps up: an invented county parcel export (400 commercial parcels, owners at *.example) is connected as a read-only database
// card, he asks, and the walk records what the agent does - its plan, its batches, the view it shows, what it says while it works, the cards
// it raises - with a frame every 20 s and the chat's list beside each. Nothing is pressed: no card is sent.
import path from "node:path";
import { execFileSync } from "node:child_process";
import { api, connect, open, shot, save, sleep, type, buttons, out, info } from "./real-lib.mjs";
import { record } from "./recorder.mjs";
import { NAMES, sampler, check, rest } from "./real-conv.mjs";

const [name = "big", ask = "Research the 100 commercial properties in the county parcel data that look most distressed, show me them in a table with the " +
  "signs of distress, the owner, how to reach them and a score, and set up an email to each owner asking whether they would sell. Work in batches."] = process.argv.slice(2);
const db = path.join(info.home, "parcels.db");
// ...INVENTED, all of it: streets of no city, owners and their addresses at *.example, figures drawn from a fixed seed
execFileSync(process.env.PYTHON || "python", ["-c", `
import random, sqlite3, sys
r = random.Random(7); c = sqlite3.connect(sys.argv[1]); c.execute('DROP TABLE IF EXISTS parcels')
c.execute('CREATE TABLE parcels (parcel_id TEXT, address TEXT, use TEXT, sqft INTEGER, owner TEXT, owner_email TEXT, assessed INTEGER, last_sale_year INTEGER, tax_delinquent_years INTEGER, code_violations INTEGER, vacancy_pct INTEGER, liens INTEGER, notice_of_default INTEGER)')
streets = ['Harbor', 'Mill', 'Quarry', 'Elm', 'Union', 'Canal', 'Foundry', 'Market', 'Depot', 'Ridge']
kinds = ['retail', 'office', 'warehouse', 'mixed use', 'strip center']
for i in range(400):
    d = r.random()
    owner = f"{r.choice(['Northgate', 'Bluestone', 'Cedar', 'Iron', 'Lakeview', 'Summit', 'Pioneer', 'Granite'])} {r.choice(['Holdings', 'Partners', 'Realty', 'Properties'])} {i % 37 + 1} LLC"
    c.execute('INSERT INTO parcels VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)', (f'P-{10000 + i}', f'{100 + i * 7} {r.choice(streets)} St', r.choice(kinds), r.randint(2000, 90000), owner,
        f"owner{i % 37 + 1}@{owner.split()[0].lower()}.example", r.randint(300, 9000) * 1000, r.randint(1985, 2024), int(d > .7) * r.randint(1, 4), int(d > .5) * r.randint(0, 6),
        min(100, int(d * r.randint(0, 120))), int(d > .8) * r.randint(1, 3), int(d > .9)))
c.commit()`, db]);
const had = ((await api("/api/connectors"))?.data || []).find((c) => c.Name === "County parcels");
console.log("connector", JSON.stringify(await api("/api/connectors", { ...(had ? { ConnectorId: had.ConnectorId } : {}), Type: "database", Name: "County parcels",
  ConfigJson: JSON.stringify({ conn_str: `sqlite:///${db.replace(/\\/g, "/")}` }), Active: true, Roles: "tool", Scope: "read" })).slice(0, 200));
await api("/api/fixture/outbox", {});

const { browser, page } = await connect();
await page.reload({ waitUntil: "domcontentloaded" }); await sleep(3000);
const t = await api("/api/tasks", { Title: "Distressed commercial properties", Kind: "general", Summary: "" }).then((x) => x.taskId);
await open(page, t);
await page.waitForSelector("[data-tq-task-page] .tq-aui-input", { visible: true, timeout: 120000 });
await sleep(2000);
const rec = await record(page, path.join(out, "video", `${name}-big`)), t0 = Date.now(), log = [];
await page.evaluate((tid) => { window.__tid = tid; }, t);
await page.evaluate(sampler, NAMES);
const snap = async (n) => {
  await shot(page, `${name}-big-${n}`); const c = await api(`/api/tasks/${t}/conversation`); await save(`${name}-big-${n}-list.json`, c);
  const turn = c.items.filter((x) => x.kind === "turn").at(-1) || {};
  const line = await page.evaluate(() => document.querySelector("[data-tq-task-page] [data-tq-working]")?.innerText || "");
  const s = { s: Math.round((Date.now() - t0) / 1000), working: c.working, steps: (turn.steps || []).length, said: String(turn.text || "").slice(0, 160), line: line.slice(0, 120),
    queue: c.queue, views: (await page.evaluate(() => document.querySelectorAll("[data-tq-task-page] .tq-view-table tbody tr").length)) };
  log.push([n, s]); console.log(`[${n}]`, JSON.stringify(s));
};
await type(page, ask); await sleep(1500); await snap("asked");
let n = 0;
while ((await api(`/api/tasks/${t}/conversation`)).working && Date.now() - t0 < 40 * 60000) { await sleep(20000); await snap(`w${String(++n).padStart(3, "0")}`); }
await rest(page, t, 600000); await sleep(3000); await snap("rest");
const reviews = (await api(`/api/tasks/${t}`))?.reviews || [];
console.log("CARDS", JSON.stringify(reviews.reduce((m, r) => ({ ...m, [`${r.Kind}:${r.Status}`]: (m[`${r.Kind}:${r.Status}`] || 0) + 1 }), {})));
const fr = await page.evaluate(() => window.__frames), bad = check(fr);
await save(`${name}-big-frames.json`, fr); await save(`${name}-big-findings.txt`, [...new Set(bad)].join("\n") || "no rule broken"); await save(`${name}-big-steps.json`, log);
await rec.stop({ sheet: 12 });
console.log("TOOK", Math.round((Date.now() - t0) / 1000), "s · FRAMES", fr.length, "RULES BROKEN", new Set(bad).size); console.log([...new Set(bad)].slice(0, 20).join("\n"));
console.log("BUTTONS", (await buttons(page)).slice(0, 300));
await browser.disconnect();
