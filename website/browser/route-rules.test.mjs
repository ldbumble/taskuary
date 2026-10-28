// WHICH AI DOES EACH JOB (the router, 2026-10-25): the mode line, the rules as sentences, Recent routes and the task's hard-work
// chip, against a fresh install's real server (the demo refuses a change to which AI reads the mail). Auto is turned on and a rule added by the page's own dropdowns; a hard task's draft
// is routed by it and Recent routes says why; a refused save is said on the page and changes nothing; the chip corrects the
// judgement. Fixed is what the page opens on.
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { startHarness } from "./harness.mjs";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const PANEL = "[data-tq-route-rules]";

test("the router's rules: Auto on, a rule added, a hard draft routed by it and the reason shown, a refused save said", { timeout: 240000 }, async (t) => {
  const harness = await startHarness({ fresh: true }); t.after(() => harness.close());
  const api = (p, body, method = body ? "POST" : "GET") => fetch(`${harness.fixtureApi}${p}`, { method,
    headers: { "Content-Type": "application/json", "X-Taskuary-Token": harness.token }, body: body && JSON.stringify(body) }).then((r) => r.json());
  // an AI card with a strong model, and a task triage judged hard - invented people, a fixture home
  const key = (await api("/api/connectors")).data.find((c) => c.Type === "anthropic");
  await api("/api/connectors", { ConnectorId: key.ConnectorId, Secret: "sk-test-not-a-real-key-000000", Active: true,
    ConfigJson: JSON.stringify({ model: "claude-sonnet-5", strong_model: "claude-opus-5" }) });
  await api("/api/settings", { name: "triage_ai", value: `connector:${key.ConnectorId}` }, "PATCH");
  const made = JSON.parse(execFileSync(process.env.TASKUARY_TEST_PYTHON || (process.platform === "win32" ? "python" : "python3"), ["-c", `
import sys, json
sys.path.insert(0, sys.argv[1])
from pathlib import Path
from taskuary.store import SQLiteStore
s = SQLiteStore(str(Path(sys.argv[2]) / 'taskuary.db'))
tid = s.create_task({'Title': 'Pull the board pack together', 'Status': 'open'}, 'owner')
mid = s.add_message({'TaskId': tid, 'Channel': 'email', 'FromEmail': 'erin@northwind.example', 'FromName': 'Erin Blake',
                     'Subject': 'Board pack', 'BodyText': 'Can you pull the board pack together by Thursday?', 'Status': 'routed'})
s.judge_task(tid, {'difficulty': 'hard', 'sure': True}, 'triage')
print(json.dumps({'tid': tid, 'mid': mid}))
`, root, harness.home], { env: { ...process.env, TASKUARY_HOME: harness.home }, encoding: "utf8" }).trim().split("\n").pop());

  const page = await harness.newPage(), errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  const until = (f, arg, timeout = 30000) => page.waitForFunction(f, { timeout, polling: 200 }, arg).catch(async (e) => {
    throw new Error(`${e.message} waiting for ${String(f).slice(0, 160)}\n${(await page.evaluate((s) => `${document.querySelector(s)?.innerText || ""}\n---\n${document.body.innerText.slice(-800)}`, PANEL))}`);
  });
  const settings = () => page.goto(`${harness.ui}#settings=config&group=${encodeURIComponent("How mail is sorted")}`, { waitUntil: "domcontentloaded", timeout: 90000 });
  await settings();
  await until((sel) => document.querySelector(sel), PANEL, 90000);
  assert.match(await page.$eval(PANEL, (e) => e.innerText), /Which AI does each job[\s\S]*Fixed - the cards below/);
  assert.equal(await page.$(`${PANEL} [data-tq-route-add]`), null, "Fixed shows no rules");

  // Auto, by the mode line's own dropdown: the shipped rules arrive as sentences
  await page.click(`${PANEL} [data-tq-route-mode]`);
  await until(() => [...document.querySelectorAll('li[role="option"]')].some((o) => /Auto - by how hard/.test(o.innerText)));
  await page.evaluate(() => [...document.querySelectorAll('li[role="option"]')].find((o) => /Auto - by how hard/.test(o.innerText)).click());
  await until((sel) => document.querySelector(`${sel} [data-tq-route-add]`), PANEL);
  assert.match(await page.$eval(PANEL, (e) => e.innerText), /Hard drafts, general work and coding -> the strong model/);
  assert.equal((await api("/api/ai/route_rules")).mode, "auto");

  // a rule from the dropdowns as they stand - hard drafts -> the strong model - goes first, as the owner's
  await page.evaluate((sel) => [...document.querySelectorAll(`${sel} button`)].find((b) => b.innerText === "Add the rule").click(), PANEL);
  await until((sel) => document.querySelector(`${sel} [data-tq-route-rule="hard-draft-strong"]`), PANEL);
  const rules = (await api("/api/ai/route_rules")).rules;
  assert.equal(rules[0].id, "hard-draft-strong"); assert.equal(rules[0].sentence, "Hard drafts -> the strong model");

  // the failure road: the server refuses a save, and the page says why instead of looking saved
  page.off("request", page.fixtureRequestGuard);
  page.on("request", (r) => {
    if (r.method() === "POST" && new URL(r.url()).pathname === "/api/ai/route_rules")
      return r.respond({ status: 422, contentType: "application/json", body: JSON.stringify({ detail: "a rule names a job the router does not know" }) });
    page.fixtureRequestGuard(r);
  });
  await page.click(`${PANEL} [data-tq-route-rule="hard-draft-strong"] input[type="checkbox"]`);
  await until(() => /a rule names a job the router does not know/.test(document.body.innerText));
  assert.equal((await api("/api/ai/route_rules")).rules[0].on, true, "a refused save changed nothing");

  // the hard task's draft is routed by the owner's rule, and the reason is in Recent routes. The route is written as the brain is
  // built; the call itself cannot leave the fixture, whose network is shut, so the draft fails - and that is all it does
  await api(`/api/messages/${made.mid}/reply`, { draft: true }).catch(() => null);
  const route = (await api(`/api/ai/routes?task=${made.tid}`)).routes.find((r) => r.Job === "draft");
  assert.ok(route, "the draft was routed");
  assert.equal(route.Rule, "hard-draft-strong"); assert.equal(route.Tier, "strong");
  await page.reload({ waitUntil: "domcontentloaded", timeout: 90000 });     // a fresh read of the log, not the list drawn before it
  await until(() => /A draft judged hard -> strong on Anthropic API \(rule hard-draft-strong\)/.test(document.querySelector("[data-tq-recent-routes]")?.innerText || ""), null, 90000);

  // the task wears its hard-work chip, and a press corrects it
  await page.goto(`${harness.ui}#task=${made.tid}`, { waitUntil: "domcontentloaded", timeout: 90000 });
  // ...in Came from, with what triage made of it: where the task opens on another section, Came from is behind its tab (the three sections)
  await until(() => document.querySelector("[data-tq-task-body][data-tq-main]"), null, 90000);
  if (await page.$("[data-tq-section-tab=from]")) await page.click("[data-tq-section-tab=from]");
  await until(() => { const j = document.querySelector("[data-tq-judged]"); return j && j.getBoundingClientRect().width > 0; }, null, 20000);
  assert.match(await page.$eval("[data-tq-judged]", (e) => e.innerText), /hard work/);
  await page.click("[data-tq-judged]");
  await until(() => [...document.querySelectorAll('li[role="menuitem"]')].some((o) => o.innerText === "Ordinary work"));
  await page.evaluate(() => [...document.querySelectorAll('li[role="menuitem"]')].find((o) => o.innerText === "Ordinary work").click());
  await until(() => !document.querySelector("[data-tq-judged]"));
  const judged = (await api(`/api/tasks/${made.tid}`)).judged;
  assert.deepEqual([judged.difficulty, judged.by], ["standard", "owner"]);
  assert.deepEqual(errors, []);
});
