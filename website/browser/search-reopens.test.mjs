import assert from "node:assert/strict";
import test from "node:test";
import { boot, clickRow, findRow, sleep } from "./walkdriver.mjs";

/* A CLOSED TASK OPENED FROM SEARCH OPENS REOPENED (the owner, 2026-11-02: "when you open a task in Search it should automatically open
   instead of having to click Reopen task"): its hit opens it, and the open is Reopen task's own press - the task open on the server,
   the row's verbs an open task's. Only Search: the same closed task opened from the rail or by a link stays closed, Reopen task its press. */
const call = (h) => async (method, url, body) => (await fetch(`${h.fixtureApi}${url}`, { method,
  headers: { "X-Taskuary-Token": h.token, "Content-Type": "application/json" }, body: body ? JSON.stringify(body) : undefined })).json();
const close = async (api, tid) => { const op = await api("POST", "/api/operations", { kind: "task.complete", target: tid, params: {} });
  await api("POST", `/api/operations/${op.id}/execute`, { version: op.version }); };
// ...a Reopen task button on the task's page or the row under it
const reopenOn = (page, tid) => page.evaluate((id) => [...document.querySelectorAll(`[data-tq-task-page="${id}"] button, [data-tq-row] button`)]
  .some((b) => b.offsetParent && /^Reopen task$/.test(b.textContent.trim())), tid);
const status = async (api, tid) => { const d = await api("GET", `/api/tasks/${tid}`); return d?.task?.Status || d?.Status; };

test("a closed task opened from Search is reopened; from the rail or a link it stays closed", { timeout: 240000 }, async (t) => {
  const { h, page, errors } = await boot(t, { width: 1440, height: 900 });
  const api = call(h), tasks = (await api("GET", "/api/tasks")).data, id = (re) => tasks.find((x) => re.test(x.Title))?.TaskId;
  const search = id(/^Month-end close/), rail = id(/^Invoice 88213/);
  assert.ok(search && rail, "the demo world has both tasks");
  await close(api, search); await close(api, rail);
  assert.equal(await status(api, search), "done"); assert.equal(await status(api, rail), "done");

  await t.test("from the rail, or by a link, the closed task opens closed with Reopen task on it", async () => {
    const key = await findRow(page, /Invoice 88213/);
    if (key) await clickRow(page, key);
    else await page.evaluate((id) => { location.hash = ""; location.hash = `task=${id}`; }, rail);
    await page.waitForSelector(`[data-tq-task-page="${rail}"]`, { timeout: 20000 }); await sleep(3500);
    assert.equal(await status(api, rail), "done", "opening it reopened it");
    assert.ok(await reopenOn(page, rail), "Reopen task is the press");
    await page.evaluate((id) => { location.hash = ""; location.hash = `task=${id}`; }, rail); await sleep(3000);
    assert.equal(await status(api, rail), "done", "a link reopened it");
  });

  await t.test("from Search, its hit opens it reopened - the Reopen task press made by the open", async () => {
    await page.keyboard.down("Control"); await page.keyboard.press("k"); await page.keyboard.up("Control");
    await page.waitForSelector("[data-tq-search-input]", { timeout: 10000 });
    await page.keyboard.type("Month-end close");
    await page.waitForSelector(`[data-tq-search-hit="task:${search}"]`, { timeout: 15000 });
    await page.click(`[data-tq-search-hit="task:${search}"]`);
    await page.waitForSelector(`[data-tq-task-page="${search}"]`, { timeout: 20000 });
    for (let i = 0; i < 40 && (await status(api, search)) !== "open"; i++) await sleep(250);
    assert.equal(await status(api, search), "open", "the Search open did not reopen it");
    await sleep(2500);
    assert.ok(!(await reopenOn(page, search)), "Reopen task is still on the page");
  });
  assert.deepEqual(errors, []);
});
