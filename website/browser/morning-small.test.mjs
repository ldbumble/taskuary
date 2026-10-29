import assert from "node:assert/strict";
import test from "node:test";

import { startHarness } from "./harness.mjs";

/* THREE THINGS THE OWNER READ WRONG (rulings of 2026-10-27), on the demo world:
   - a reply owed with NO DRAFT YET said "ready to send" with its flag, on the rail and the header: it says "reply owed" until the draft lands
   - "remind me Monday" lit Remind me and its picker had no Monday (the phone kept it): the said day is the picker's first button
   - the opener said 12 on you beside the rail's TASKS 13: both count the rail's tasks, one number */
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const boot = async (t) => {
  const harness = await startHarness();
  t.after(() => harness.close());
  const page = await harness.newPage();
  await page.setViewport({ width: 1600, height: 810, deviceScaleFactor: 1 });
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  const api = async (p, method = "GET", body) => (await fetch(`${harness.fixtureApi}${p}`, { method,
    headers: { "X-Taskuary-Token": harness.token, "Content-Type": "application/json" }, body: body && JSON.stringify(body) })).json();
  return { harness, page, errors, api };
};
const open = async (page, id) => {
  await page.evaluate((tid) => { window.location.hash = `task=${tid}`; }, id);
  await page.waitForFunction((tid) => !!document.querySelector(`[data-tq-task-page="${tid}"] [data-tq-task-head]`), { timeout: 20000 }, String(id));
};

test("a reply with no draft yet says reply owed, with no flag, on the rail row and the header - and ready to send once it is drafted", { timeout: 300000 }, async (t) => {
  const { harness, page, errors, api } = await boot(t);
  const tasks = (await api("/api/tasks")).data || [];
  const mail = tasks.find((x) => x.Source === "email" && x.Status === "open" && x.State === "approve");
  assert.ok(mail, "the demo world has an email reply waiting to send");
  const rv = ((await api(`/api/tasks/${mail.TaskId}`)).reviews || []).find((r) => r.Status === "pending" && r.DraftText);
  assert.ok(rv, "...with its draft");
  const read = async () => {
    await page.waitForSelector(".tq-pile-row.current .tq-mark[role=img]", { timeout: 20000 });
    await sleep(1500);
    return page.evaluate(() => {
      const m = document.querySelector(".tq-pile-row.current .tq-mark"), pill = document.querySelector("[data-tq-status-pill]");
      return { label: m?.getAttribute("aria-label") || "", key: m?.getAttribute("data-tq-status") || "", badge: m?.querySelector(".badge")?.textContent || "",
        pill: pill?.querySelector(".word")?.textContent || "", pillKey: pill?.getAttribute("data-tq-status-pill") || "" };
    });
  };
  // the demo refuses edits, so the reads say what the server says of a reply nothing has drafted yet: the rail's row `draft: false`
  // (funnel.from_feed's HasDraft) and the task's pending review with no text
  let owedOn = true;
  const unDraft = (o) => {
    if (Array.isArray(o)) return o.map(unDraft);
    if (!o || typeof o !== "object") return o;
    const out = Object.fromEntries(Object.entries(o).map(([k, v]) => [k, unDraft(v)]));
    if (Number(out.tid) === mail.TaskId && out.kind === "review" && out.lane === "approve") out.draft = false;
    if (Number(out.TaskId) === mail.TaskId && out.ReviewId && out.Status === "pending" && "DraftText" in out) { out.DraftText = ""; out.FinalText = null; }
    return out;
  };
  // (in place of the harness's own guard, which every other request still goes through)
  const guard = page.fixtureRequestGuard;
  page.off("request", guard);
  page.on("request", async (r) => {
    const u = new URL(r.url());
    if (!owedOn || r.method() !== "GET" || !/^\/api\/(funnel\/pile|tasks\/\d+)$/.test(u.pathname)) { guard(r); return; }
    try {
      const res = await fetch(r.url(), { headers: r.headers() });
      r.respond({ status: res.status, contentType: "application/json", body: JSON.stringify(unDraft(await res.json())) });
    } catch { guard(r); }
  });
  await page.goto(harness.ui, { waitUntil: "domcontentloaded", timeout: 20000 });
  await page.waitForSelector("[data-tq-rail] .tq-pile-row", { timeout: 30000 });
  await open(page, mail.TaskId);
  const owed = await read();
  assert.deepEqual([owed.key, owed.label, owed.badge], ["owed", "reply owed", ""], `the rail row: ${JSON.stringify(owed)}`);
  assert.deepEqual([owed.pillKey, owed.pill], ["owed", "reply owed"], `the header says what the rail says: ${JSON.stringify(owed)}`);
  // ...the draft lands: the flag and its words come back
  owedOn = false;
  await page.reload({ waitUntil: "domcontentloaded" });
  await page.waitForSelector("[data-tq-rail] .tq-pile-row", { timeout: 30000 });
  await open(page, mail.TaskId);
  const ready = await read();
  assert.deepEqual([ready.key, ready.label, ready.badge, ready.pill], ["approve", "ready to send", "🏁", "ready to send"], JSON.stringify(ready));
  assert.deepEqual(errors, []);
});

test("a typed 'remind me Monday' lights Remind me, and its picker's first button is that Monday", { timeout: 300000 }, async (t) => {
  const { harness, page, errors, api } = await boot(t);
  await page.goto(harness.ui, { waitUntil: "domcontentloaded", timeout: 20000 });
  await page.waitForSelector("[data-tq-rail] .tq-pile-row", { timeout: 30000 });
  const inv = ((await api("/api/tasks")).data || []).find((x) => /^Invoice 88213/.test(x.Title));
  await open(page, inv.TaskId);
  await page.waitForSelector(".tq-dock [data-tq-row] [data-tq-next]", { timeout: 20000 });
  await sleep(2000);
  await page.click(".tq-compose-box textarea");
  await page.keyboard.type("remind me Monday");
  await page.keyboard.press("Enter");
  // ...on the row, or - Remind me is Came from's move now (the owner, 2026-10-29) - on its spine or in its open heading
  const lit = '.tq-arow-verbs button.tq-ab.p[data-tq-verb$="remind"], [data-tq-spine-moves] button.tq-ab.p[data-tq-verb$="remind"], [data-tq-pane-moves] button.tq-ab.p[data-tq-verb$="remind"]';
  await page.waitForSelector(lit, { visible: true, timeout: 20000 });
  const posted = new Promise((resolve) => page.on("request", (r) => {
    if (r.method() === "POST" && r.url().endsWith(`/api/tasks/${inv.TaskId}/remind`)) resolve(r.postData());
  }));
  // the press itself, on the button (the chat's pop-up may lie over the row - remind-lit-anchor is about where it opens)
  await page.$eval(lit, (b) => b.click());
  await page.waitForFunction(() => [...document.querySelectorAll(".MuiPopover-paper")].some((p) => p.innerText.includes("Bring it back on")), { timeout: 10000 });
  const first = await page.evaluate(() => {
    const p = [...document.querySelectorAll(".MuiPopover-paper")].find((x) => x.innerText.includes("Bring it back on"));
    const b = p.querySelector("button"); return { text: b?.innerText.trim() || "", said: !!b?.hasAttribute("data-tq-remind-said") };
  });
  assert.ok(first.said && /^Mon \d{1,2} \w{3}$/.test(first.text), `the picker leads with the day that was typed: ${JSON.stringify(first)}`);
  await page.click("[data-tq-remind-said]");
  const until = JSON.parse(await Promise.race([posted, sleep(10000).then(() => "{}")])).until || "";
  assert.equal(new Date(`${until.slice(0, 10)}T12:00:00`).getDay(), 1, `its press puts the task away until that Monday: ${until}`);
  assert.deepEqual(errors, []);
});

test("the opener counts the tasks the rail counts: one number", { timeout: 300000 }, async (t) => {
  const { harness, page, errors } = await boot(t);
  await page.goto(harness.ui, { waitUntil: "domcontentloaded", timeout: 20000 });
  await page.waitForSelector("[data-tq-rail] .tq-pile-row", { timeout: 30000 });
  await page.waitForFunction(() => {
    const h = document.querySelector(".tq-day-wait .tq-day-h")?.textContent || "";
    return /^tasks$/i.test(h.trim()) && /^\d+$/.test(document.querySelector(".tq-day-row.lvl-task .n")?.textContent.trim() || "");
  }, { timeout: 30000 });
  await sleep(1500);
  const got = await page.evaluate(() => ({
    head: document.querySelector(".tq-day-wait .tq-day-h")?.textContent.trim() || "",
    row: document.querySelector(".tq-day-row.lvl-task .n")?.textContent.trim() || "",
    rail: document.querySelector("[data-tq-section-head=task] em")?.textContent.trim() || "",
    marks: [...document.querySelectorAll("[data-tq-run=task] .tq-pile-row .tq-mark")].map((m) => m.getAttribute("data-tq-status")),
  }));
  // ...said once (2026-10-28): the heading names the band and the Tasks row under it carries the count - "13 TASKS" over "Tasks 13" was twice
  assert.equal(got.head, "Tasks", `the opener's heading carries no count of its own: ${JSON.stringify(got)}`);
  assert.equal(got.row, got.rail, `the rail's TASKS and the opener's Tasks row: ${JSON.stringify(got)}`);
  // the case it pins: a task that is not the owner's move (an agent at work, a wait on them) is still one of the tasks
  assert.ok(got.marks.some((k) => ["working", "theirs"].includes(k)), `the demo has a task that is not on you: ${JSON.stringify(got.marks)}`);
  assert.deepEqual(errors, []);
});
