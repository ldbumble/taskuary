import assert from "node:assert/strict";
import test from "node:test";
import { boot, sleep } from "./walkdriver.mjs";

/* AN EMAIL OWED WITH NOTHING DRAFTED IS NOT A CLOSE-OUT (the owner, 2026-11-02): a chat asked the owner to email somebody about a meeting,
   the task's checklist owed that email ("Closes when sent · 0 of 1", "<address> to draft") and no draft was made - and the task opened on
   Close out, empty. "It should show the task, not close out, as there is no close-out draft created." On the demo world: a reply nobody
   has drafted for, an email to Paula Vance added to its checklist, opens on Came from with Close out a tab. Invented people only. */
const call = (h) => async (method, url, body) => (await fetch(`${h.fixtureApi}${url}`, { method,
  headers: { "X-Taskuary-Token": h.token, "Content-Type": "application/json" }, body: body ? JSON.stringify(body) : undefined })).json();
const look = (page, id) => page.evaluate((id) => {
  const body = document.querySelector(`[data-tq-task-page="${id}"] [data-tq-task-body]`);
  return { main: body?.getAttribute("data-tq-main"), stage: body?.getAttribute("data-tq-stage"),
    open: [...(body?.querySelectorAll("[data-tq-slot]") || [])].filter((s) => s.hasAttribute("data-tq-open")).map((s) => s.dataset.tqSlot) };
}, id);

test("a task whose checklist owes an email nobody drafted opens on Came from, not an empty Close out", { timeout: 240000 }, async (t) => {
  const { h, page, errors } = await boot(t, { width: 1440, height: 900 });
  const api = call(h), tasks = (await api("GET", "/api/tasks")).data;
  let id = null;
  for (const x of tasks) if ((await api("GET", `/api/tasks/${x.TaskId}`))?.stage === "to_reply") { id = x.TaskId; break; }
  assert.ok(id, "the demo world has a reply nobody drafted for");
  const op = await api("POST", "/api/operations", { kind: "task.checklist", target: id,
    params: { emails: [{ to: "Paula Vance <paula@vendor.example>", about: "the 2:30 meeting" }] } });
  const ran = await api("POST", `/api/operations/${op.id}/execute`, { version: op.version });
  assert.notEqual(ran?.status, "error", JSON.stringify(ran));
  const d = await api("GET", `/api/tasks/${id}`);
  assert.ok((d.checklist || []).some((i) => i.out && !i.done && !i.rid), `the email is owed, nothing drafted: ${JSON.stringify(d.checklist)}`);
  await page.evaluate((id) => { location.hash = ""; location.hash = `task=${id}`; }, id);
  await page.waitForSelector(`[data-tq-task-page="${id}"] [data-tq-task-body][data-tq-sections]`, { timeout: 20000 }); await sleep(2500);
  const m = await look(page, id);
  assert.equal(m.main, "from", `it opened on ${JSON.stringify(m)}`);
  assert.deepEqual(m.open, ["from"]);
  assert.notEqual(m.stage, "close_out", "nothing of Close out's own is there");
  assert.deepEqual(errors, []);
});
