import assert from "node:assert/strict";
import test from "node:test";
import { execFileSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { boot, sleep } from "./walkdriver.mjs";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");

/* AN EMAIL OWED WITH NOTHING DRAFTED IS NOT A CLOSE-OUT (the owner, 2026-11-02): a chat asked the owner to email somebody about a meeting,
   the task's checklist owed that email ("Closes when sent · 0 of 1", "<address> to draft") and no draft was made - and the task opened on
   Close out, empty. "It should show the task, not close out, as there is no close-out draft created." On the demo world: a reply nobody
   has drafted for, an email to Paula Vance added to its checklist, opens on Came from with Close out a tab. Invented people only. */
// ...once more on a dropped socket: a kept-alive connection the server closed while the draft was written lands as "fetch failed"
const call = (h) => async (method, url, body) => {
  const go = () => fetch(`${h.fixtureApi}${url}`, { method, headers: { "X-Taskuary-Token": h.token, "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined });
  return (await go().catch(go)).json();
};
const look = (page, id) => page.evaluate((id) => {
  const body = document.querySelector(`[data-tq-task-page="${id}"] [data-tq-task-body]`);
  return { main: body?.getAttribute("data-tq-main"), stage: body?.getAttribute("data-tq-stage"),
    open: [...(body?.querySelectorAll("[data-tq-slot]") || [])].filter((s) => s.hasAttribute("data-tq-open")).map((s) => s.dataset.tqSlot) };
}, id);

// ...Close out, opened: each line's To, read as the owner reads it - the owed email's own row, the reply's line, the drafted card's
const closeTos = (page, id) => page.evaluate((id) => {
  const co = document.querySelector(`[data-tq-task-page="${id}"] [data-tq-closeout]`), next = (e) => e?.nextElementSibling?.textContent || "";
  return { slot: [...(co?.querySelectorAll("[data-tq-slot-to]") || [])].map((e) => e.parentElement.innerText.replace(/\s+/g, " ").trim()),
    reply: [...(co?.querySelectorAll("[data-tq-reply-to]") || [])].map((e) => `${e.textContent} ${next(e)}`), text: co?.innerText || "" };
}, id);
const tabText = (page, id) => page.evaluate((id) => document.querySelector(`[data-tq-task-page="${id}"] [data-tq-section-tab=close]`)?.innerText || "", id);
const openTask = async (page, id) => {
  await page.evaluate((id) => { location.hash = ""; location.hash = `task=${id}`; }, id);
  await page.waitForSelector(`[data-tq-task-page="${id}"] [data-tq-task-body][data-tq-sections]`, { timeout: 20000 }); await sleep(2500);
};

// ...an email to Paula Vance added to what a task owes, through the task's own checklist road; the slot's id
const owe = async (api, id) => {
  const op = await api("POST", "/api/operations", { kind: "task.checklist", target: id,
    params: { emails: [{ to: "Paula Vance <paula@vendor.example>", about: "the 2:30 meeting" }] } });
  const ran = await api("POST", `/api/operations/${op.id}/execute`, { version: op.version });
  assert.notEqual(ran?.status, "error", JSON.stringify(ran));
  const d = await api("GET", `/api/tasks/${id}`);
  assert.ok((d.checklist || []).some((i) => i.out && !i.done && !i.rid), `the email is owed, nothing drafted: ${JSON.stringify(d.checklist)}`);
  return d.checklist.find((i) => i.out).id;
};
const openClose = (page, id) => page.evaluate((id) => document.querySelector(`[data-tq-task-page="${id}"] [data-tq-section-tab=close] [data-tq-tab-arrow]`)?.click(), id);

test("a task owing an email nobody drafted opens on Came from, and Close out's To is that email's own", { timeout: 300000 }, async (t) => {
  const { h, page, errors } = await boot(t, { width: 1440, height: 900 });
  const api = call(h), tasks = (await api("GET", "/api/tasks")).data;
  let id = null;
  for (const x of tasks) if ((await api("GET", `/api/tasks/${x.TaskId}`))?.stage === "to_reply") { id = x.TaskId; break; }
  assert.ok(id, "the demo world has a reply nobody drafted for");
  // ...and somebody's message with nothing drafted for it - a chat's first, as the owner's was - the email owed beside the reply owed
  const asks = [];
  for (const x of tasks) { const d = await api("GET", `/api/tasks/${x.TaskId}`), m = (d?.messages || []).find((m) => m.FromName && m.FromName !== "Taskuary" && m.Direction !== "out");
    if (m && !["close_out", "done", "agent_working", "waiting"].includes(d?.stage) && x.TaskId !== id) asks.push({ id: x.TaskId, chat: m.Channel !== "email" }); }
  const both = (asks.find((o) => o.chat) || asks[0])?.id;
  assert.ok(both, "the demo world has a message nobody answered");
  await owe(api, id);
  const slot = await owe(api, both);

  await t.test("it opens on Came from, not an empty Close out, and the Close out tab leads with the email and its To", async () => {
    await openTask(page, id);
    const m = await look(page, id);
    assert.equal(m.main, "from", `it opened on ${JSON.stringify(m)}`);
    assert.deepEqual(m.open, ["from"]);
    assert.notEqual(m.stage, "close_out", "nothing of Close out's own is there");
    assert.match(await tabText(page, id), /Close out\s+Email to paula@vendor\.example · to draft/);
    await openClose(page, id); await sleep(1200);
    const c = await closeTos(page, id);
    assert.equal(c.slot.length, 1, JSON.stringify(c));
    assert.match(c.slot[0], /^To .*paula@vendor\.example to draft/, "the owed email's To is its address");
  });

  await t.test("beside a reply: the owed email's To is its address, the sender's line is the reply's", async () => {
    await openTask(page, both); await openClose(page, both); await sleep(1200);
    const c = await closeTos(page, both);
    assert.match(c.slot[0] || "", /^To .*paula@vendor\.example to draft/, JSON.stringify(c));
    assert.equal(c.reply.length, 1, `the reply to the sender keeps its line: ${JSON.stringify(c)}`);
    assert.match(c.reply[0], /^Reply to /, `the sender's line is the reply's: ${c.reply[0]}`);
    assert.doesNotMatch(c.reply[0], /paula@vendor\.example/);
  });

  await t.test("drafted: its card's To is the email's address, never the sender", async () => {
    // the demo refuses an agent's draft road (it would reach something real), so the email is written where that road writes it (slots.draft)
    const out = execFileSync(process.env.TASKUARY_TEST_PYTHON || (process.platform === "win32" ? "python" : "python3"), ["-c", `
import sys, json
sys.path.insert(0, sys.argv[1])
from pathlib import Path
from taskuary import slots
from taskuary.store import SQLiteStore
s = SQLiteStore(str(Path(sys.argv[2]) / 'taskuary.db'))
print(json.dumps(slots.draft(s, int(sys.argv[3]), 'Hi Paula, the meeting is at 2:30.', slot=sys.argv[4], agent='owner')))
`, ROOT, h.home, String(both), slot], { env: { ...process.env, TASKUARY_HOME: h.home }, encoding: "utf8" });
    assert.ok(JSON.parse(out.trim().split(/\r?\n/).at(-1)).ok, out);
    assert.ok((await api("GET", `/api/tasks/${both}`)).checklist.find((i) => i.id === slot)?.rid, "the email has its draft");
    await page.reload({ waitUntil: "domcontentloaded" }); await page.waitForSelector("[data-tq-rail] .tq-pile-row", { timeout: 40000 });
    await openTask(page, both); await openClose(page, both); await sleep(1500);
    const c = await closeTos(page, both);
    assert.match(c.slot[0] || "", /^To .*paula@vendor\.example waits for your yes/, JSON.stringify(c.slot));
    // ...the drafted card under its row is addressed to the email's address
    assert.match(c.text, /waits for your yes[\s\S]*To\s*paula@vendor\.example/, c.text.slice(0, 600));
    for (const r of c.reply) assert.doesNotMatch(r, /paula@vendor\.example/);
  });
  assert.deepEqual(errors, []);
});
