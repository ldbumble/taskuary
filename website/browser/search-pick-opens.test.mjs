import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";
import { boot, sleep } from "./walkdriver.mjs";

/* A SEARCH PICK OPENS WHAT WAS PICKED (a colleague, 2026-11-03: a hit clicked, "…" on the canvas, then nothing, and "I can't find that
   one - it may be older than what I keep" three times in the chat). Search lists every message whatever became of it; the pick opened
   only the ones a rail would show. A task, an FYI, a read mail, a mail skipped at the first sync, a sent one and a report run: each hit
   clicked puts its own card on the canvas, and no line says it cannot be found. */
const repo = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const SEED = `
import sys
from datetime import datetime, timedelta
from taskuary.store import SQLiteStore
from taskuary import funnel
s = SQLiteStore(sys.argv[1]); ago = lambda **k: (datetime.now() - timedelta(**k)).strftime('%Y-%m-%d %H:%M:%S')
def mail(subj, **f): return s.add_message({'Channel': 'email', 'Subject': f'Lanyard {subj}', 'BodyText': f'About the lanyard order ({subj}).',
  'FromName': 'Gail Moreno', 'FromEmail': 'gail@northwind.example', 'SourceName': 'alex@northwind.example', 'SentAt': ago(days=3),
  'Direction': 'in', 'ConversationId': f'c-{subj}', 'ExternalId': f'lanyard-{subj}', **f})
tid = s.create_task({'Title': 'Lanyard task for the open day', 'Kind': 'general'}, 'owner')
src = s.save_source({'Channel': 'report', 'Address': 'Lanyard stock', 'Active': 1, 'ConfigJson': '{"title": "Lanyard stock"}'}, 't')
m = dict(fyi=mail('fyi', Status='filed'), read=mail('read', Status='filed'), skipped=mail('skipped', Status='skipped', SentAt=ago(days=200)),
  sent=mail('sent', Status='context', Direction='out', FromName='Alex Doyle', FromEmail='alex@northwind.example'),
  report=s.add_message({'Channel': 'report', 'Subject': 'Lanyard stock report', 'BodyText': 'Lanyard stock is low.', 'Status': 'feed',
    'SourceName': f'report:{src}', 'ConversationId': f'report:{src}', 'SentAt': ago(hours=2), 'ExternalId': 'lanyard-report'}))
funnel.settle(s, f"msg:{m['read']}", 'surfaced', 'owner', read=True)
print(tid, *[f'{k}={v}' for k, v in m.items()])
`;
const call = (h) => async (method, url) => (await fetch(`${h.fixtureApi}${url}`, { method, headers: { "X-Taskuary-Token": h.token } })).json();

test("every Search hit clicked opens its own card, and nothing says it cannot be found", { timeout: 300000 }, async (t) => {
  const { h, page, errors } = await boot(t, { width: 1440, height: 900 });
  const out = execFileSync(process.env.TASKUARY_TEST_PYTHON || (process.platform === "win32" ? "python" : "python3"), ["-c", SEED, path.join(h.home, "taskuary.db")],
    { cwd: repo, encoding: "utf8", env: { ...process.env, TASKUARY_HOME: h.home } }).trim().split(/\s+/);
  const tid = Number(out[0]), mids = Object.fromEntries(out.slice(1).map((x) => x.split("=")).map(([k, v]) => [k, Number(v)]));
  const api = call(h);
  const picks = [["task", `task:${tid}`], ...Object.entries(mids).map(([n, mid]) => [n, `msg:${mid}`])];
  for (const [name, hit] of picks) {
    await page.keyboard.down("Control"); await page.keyboard.press("k"); await page.keyboard.up("Control");
    await page.waitForSelector("[data-tq-search-input]", { timeout: 10000 });
    await page.keyboard.type("lanyard");
    await page.waitForSelector(`[data-tq-search-hit="${hit}"]`, { timeout: 15000 });
    await page.click(`[data-tq-search-hit="${hit}"]`);
    // the canvas holds the one picked: its own title on the item's head (a rail row's card is keyed by its rail key, so the words tell)
    const title = { task: "Lanyard task for the open day", report: "Lanyard stock report" }[name] || `Lanyard ${name}`;
    const ok = await page.waitForFunction((t) => [...document.querySelectorAll("[data-tq-item-head], [data-tq-task-page]")].some((e) => e.innerText.includes(t)),
      { timeout: 20000, polling: 200 }, title).then(() => true, () => false);
    const said = ((await api("GET", "/api/concierge")).messages || []).slice(-1).map((l) => l.text).join("");
    assert.ok(ok, `${name}: the pick put nothing of its own on the canvas - the chat said: ${said}`);
    await sleep(800);
  }
  const chat = (await api("GET", "/api/concierge")).messages || [];
  assert.ok(!chat.some((l) => /can't find|older than what I keep|no longer in Taskuary/.test(l.text || "")), "a line said a hit could not be found");
  const shown = await page.evaluate(() => document.body.innerText);
  assert.doesNotMatch(shown, /can't find that one|older than what I keep/);
  assert.deepEqual(errors, []);
});
