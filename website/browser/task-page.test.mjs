import assert from "node:assert/strict";
import test from "node:test";

import { startHarness } from "./harness.mjs";

/* THE TASK PAGE, REDESIGNED (owner-approved 2026-10-21), on the demo world: two columns - From | the work - at rest; the work alone,
   full width, while an agent works, From folded to one line over a terminal nothing covers; the agent's Result when it has stopped and
   saved; From newest on top with the older lines folded; and the header's status the rail's own. */

const post = (page, path, body = {}) => page.evaluate(async ({ path, body }) => {
  const headers = { "X-Taskuary-Token": localStorage.getItem("taskuary_token"), "Content-Type": "application/json" };
  const r = await fetch(path, { method: "POST", headers, body: JSON.stringify(body) });
  return r.json();
}, { path, body });
const open = async (page, id) => {
  await page.evaluate((tid) => { window.location.hash = `task=${tid}`; }, id);
  await page.waitForFunction((tid) => !!document.querySelector(`[data-tq-task-page="${tid}"] [data-tq-task-head]`), { timeout: 20000 }, String(id));
};
// the view on the table, its two columns and where they sit
const layout = (page) => page.evaluate(() => {
  const box = (sel) => { const e = document.querySelector(sel); if (!e) return null; const r = e.getBoundingClientRect(); return { x: r.left, y: r.top, w: r.width, h: r.height, right: r.right }; };
  return { layout: document.querySelector("[data-tq-columns]")?.getAttribute("data-tq-layout"), from: box("[data-tq-from]"), work: box("[data-tq-work]"),
    line: document.querySelector("[data-tq-from-line]")?.innerText || "", status: document.querySelector("[data-tq-status-pill]")?.innerText.trim() || "",
    statusKey: document.querySelector("[data-tq-status-pill]")?.getAttribute("data-tq-status-pill") || "",
    head: document.querySelector("[data-tq-task-head]")?.innerText || "", sorted: document.querySelector("[data-tq-sorted]")?.innerText || "" };
});

test("the task page: From | Work at rest, the work alone while an agent works, its Result when it stopped", { timeout: 360000 }, async (t) => {
  const harness = await startHarness();
  t.after(() => harness.close());
  const page = await harness.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(harness.ui, { waitUntil: "domcontentloaded", timeout: 20000 });
  const tasks = (await (await fetch(`${harness.fixtureApi}/api/tasks`, { headers: { "X-Taskuary-Token": harness.token } })).json()).data || [];

  await t.test("an email task: From on the left, the reply on the right, the triage line last, no chips by the title", async () => {
    const mail = tasks.find((x) => x.Source === "email" && x.Status === "open" && x.State === "approve");
    assert.ok(mail, "the demo world has an email reply waiting to send");
    await open(page, mail.TaskId);
    await page.waitForSelector("[data-tq-from] [data-tq-sorted]", { timeout: 20000 });
    const l = await layout(page);
    assert.equal(l.layout, "columns");
    assert.ok(l.from && l.work, "both columns drawn");
    assert.ok(l.from.right <= l.work.x + 1 && Math.abs(l.from.y - l.work.y) < 4, `From is beside the work, on its left: ${JSON.stringify(l)}`);
    assert.match(l.sorted, /^Sorted as: a reply to send · \w+ priority/, "what triage made of it, at the foot of From");
    assert.equal(l.statusKey, "approve");
    assert.match(l.status, /ready to send$/, "the status is the rail's word");
    assert.equal(await page.$$eval("[data-tq-task-head] [data-tq-fact], [data-tq-task-head] .MuiChip-root", (els) => els.length), 0, "no chips by the title");
    // the one message it came from reads whole, and the reply is the open half of the work
    assert.ok(await page.$("[data-tq-from] [data-tq-conversation-row][aria-expanded=true]"), "a lone message opens whole");
    assert.ok(await page.$("[data-tq-work] [data-tq-closeout] textarea"), "the draft is in the work column");
    // ...and the header's status is the rail row's own: the same words on the row's icon
    await page.waitForSelector(".tq-pile-row.current .tq-mark[role=img]", { timeout: 20000 });
    assert.equal(await page.$eval(".tq-pile-row.current .tq-mark", (e) => e.getAttribute("aria-label")),
      await page.$eval("[data-tq-status-pill] .word", (e) => e.textContent));
  });

  await t.test("a rail row carries its state in its icon - a badge, or the ring while an agent works - and no status words on its right", async () => {
    const rows = await page.$$eval("[data-tq-rail] .tq-pile-row", (els) => els.map((r) => { const m = r.querySelector(".tq-mark"); return {
      key: r.getAttribute("data-tq-key"), mark: m?.getAttribute("data-tq-status") || "", label: m?.getAttribute("aria-label") || "",
      badge: r.querySelector(".tq-mark .badge")?.textContent || "", ring: !!r.querySelector(".tq-mark.spins"), kids: m ? m.children.length : 0,
      after: m ? getComputedStyle(m, "::after").content : "none",
      word: r.querySelector(".tq-pile-word")?.innerText || "", band: r.closest("[data-tq-run]")?.getAttribute("data-tq-run") }; }));
    const tasks = rows.filter((r) => r.band === "task" && r.mark);
    assert.ok(tasks.length >= 5, `rows under Tasks wear their state: ${JSON.stringify(rows)}`);
    for (const r of tasks) {
      assert.ok(r.label, `${r.key} says its state in words`);
      assert.ok(r.ring !== !!r.badge, `${r.key} wears the ring or a badge, never both and never neither: ${JSON.stringify(r)}`);
      // no ring round the logo but the working one - the shaped rings are gone (the owner, 2026-10-22)
      assert.equal(r.after !== "none", r.ring, `${r.key}: only a working row draws a ring`);
      assert.equal(r.word, "", `${r.key} has no status word on its right`);
    }
    assert.ok(tasks.some((r) => r.mark === "approve" && r.badge === "🏁" && r.label === "ready to send"), "ready to send is a 🏁 badge, said in words");
    const ring = rows.find((r) => r.ring);
    if (ring) assert.match(ring.label, /is working on this$/);
  });

  await t.test("a chat burst reads newest on top, the older lines behind Show N older", async () => {
    const made = await post(page, "/api/fixture/task/chat-burst");
    assert.ok(made.taskId, JSON.stringify(made));
    await open(page, made.taskId);
    await page.waitForSelector("[data-tq-from] [data-tq-conversation-row]", { timeout: 20000 });
    const rows = () => page.$$eval("[data-tq-from] [data-tq-conversation-row]", (els) => els.map((e) => e.innerText.replace(/\s+/g, " ").trim()));
    const first = await rows();
    assert.equal(first.length, 3, `the newest three: ${first}`);
    assert.match(first[0], /Gail Moreno and bring the floor plan please/, "the newest on top");
    assert.match(first[2], /Gail Moreno Alex, can you be there at 9:30\?/);
    assert.equal(await page.$eval("[data-tq-show-older]", (e) => e.getAttribute("data-tq-show-older")), "3");
    await page.click("[data-tq-show-older]");
    await page.waitForSelector("[data-tq-from] [data-tq-chat-thread]", { timeout: 10000 });   // a chat's Show all is its back-and-forth
    const thread = await page.$eval("[data-tq-from] [data-tq-chat-thread]", (e) => e.innerText);
    assert.ok(thread.indexOf("floor plan") < thread.indexOf("Morning all"), "still newest on top, the opening line last");
  });

  await t.test("a coding agent working takes the whole width; From is one line and nothing covers the terminal", async () => {
    const coding = tasks.find((x) => x.Kind === "coding" && /census sync/.test(x.Title) && !["done", "dropped"].includes(x.Status));
    assert.ok(coding, "the demo world's census sync session");
    await open(page, coding.TaskId);
    await page.waitForSelector(".xterm-screen", { timeout: 20000 });
    await page.waitForFunction(() => document.querySelector("[data-tq-columns]")?.getAttribute("data-tq-layout") === "full", { timeout: 20000 });
    const l = await layout(page);
    assert.equal(l.from, null, "no From column while the agent works");
    assert.match(l.line, /^From\s*\S/, `From folded to one line: "${l.line}"`);
    assert.match(l.line, /1 message/);
    assert.ok(["working", "blocked"].includes(l.statusKey), `the rail's working or waiting status: ${l.statusKey}`);
    const term = await page.evaluate(() => {
      const view = document.querySelector("[data-tq-task-page] [data-tq-task-head]").parentElement.getBoundingClientRect();
      const x = document.querySelector(".xterm-screen").getBoundingClientRect();
      const hits = [[0.5, 0.5], [0.1, 0.1], [0.9, 0.2], [0.5, 0.9]].map(([fx, fy]) => document.elementFromPoint(x.left + x.width * fx, x.top + Math.min(x.height, 300) * fy));
      return { share: x.width / view.width, covered: hits.filter((h) => !h?.closest(".xterm")).length, h: x.height };
    });
    assert.ok(term.share > 0.9, `the terminal has the whole width (${Math.round(term.share * 100)}%)`);
    assert.equal(term.covered, 0, "nothing is drawn over the terminal");
    assert.ok(term.h > 200, `the terminal is not squeezed (${term.h}px)`);
  });

  // ITEM 6 (the owner, 2026-10-21): the folded line opens From as a sidebar OVER the agent's left edge - the pane underneath keeps its
  // size, the terminal is not refitted, and no resize reaches the pty; the line, the X and Escape close it
  await t.test("the From line opens a sidebar over the running coding pane; the terminal keeps its size and gets no resize", async () => {
    const cdp = await page.createCDPSession();
    await cdp.send("Network.enable");
    const resizes = [];
    cdp.on("Network.webSocketFrameSent", ({ response }) => { try { if (JSON.parse(response.payloadData).type === "resize") resizes.push(response.payloadData); } catch { /* not json */ } });
    const pane = () => page.evaluate(() => {
      const x = document.querySelector(".xterm-screen"), r = x?.getBoundingClientRect();
      return x ? { w: Math.round(r.width), h: Math.round(r.height), left: Math.round(r.left), rows: document.querySelectorAll(".xterm-rows > div").length } : null;
    });
    await new Promise((r) => setTimeout(r, 1500));               // the pane's own first fit settles before the clock starts
    resizes.length = 0;
    const before = await pane();
    assert.ok(before, "the coding pane is there");
    assert.equal(await page.$eval("[data-tq-from-line]", (e) => e.getAttribute("aria-expanded")), "false", "closed by default");
    // ...and the line reads as a press: a chevron after its words, a pointer, a title saying what it opens (the owner, 2026-10-22)
    const look = () => page.$eval("[data-tq-from-line]", (e) => ({ chevron: e.querySelector("[data-tq-from-chevron]")?.textContent, cursor: getComputedStyle(e).cursor,
      title: e.getAttribute("title"), gap: e.querySelector("[data-tq-from-chevron]").getBoundingClientRect().left - e.querySelector("[data-tq-from-words]").getBoundingClientRect().right }));
    const shut = await look();
    assert.deepEqual([shut.chevron, shut.cursor, shut.title], ["▸", "pointer", "Show where this came from"]);
    assert.ok(shut.gap >= 0 && shut.gap < 16, `the chevron sits right after the words (${shut.gap}px)`);
    await page.hover("[data-tq-from-line]");
    assert.equal(await page.$eval("[data-tq-from-words]", (e) => getComputedStyle(e).textDecorationLine), "underline", "hovered, the words underline");
    await page.click("[data-tq-from-line]");
    await page.waitForSelector("[data-tq-from-side]", { visible: true, timeout: 5000 });
    const opened = await look();
    assert.deepEqual([opened.chevron, opened.title], ["◂", "Hide where this came from"], "open, the chevron turns");
    const side = await page.$eval("[data-tq-from-side]", (e) => { const r = e.getBoundingClientRect(); return { left: r.left, w: r.width, text: e.innerText }; });
    assert.match(side.text, /Came from/, "the same From every other task shows");
    assert.ok(side.left <= before.left + 2 && side.w < before.w, "laid over the agent's left edge");
    await new Promise((r) => setTimeout(r, 600));
    assert.deepEqual(await pane(), before, "the terminal underneath keeps its size and place while the sidebar is open");
    await page.keyboard.press("Escape");
    await page.waitForFunction(() => !document.querySelector("[data-tq-from-side]"), { timeout: 5000 });
    assert.equal(await page.evaluate(() => document.activeElement?.hasAttribute("data-tq-from-line")), true, "Escape hands focus back to the line");
    await page.keyboard.press("Enter");                          // ...where Enter opens it and Space closes it
    await page.waitForSelector("[data-tq-from-side]", { timeout: 5000 });
    await page.keyboard.press("Space");
    await page.waitForFunction(() => !document.querySelector("[data-tq-from-side]") && document.querySelector("[data-tq-from-chevron]")?.textContent === "▸", { timeout: 5000 });
    await page.click("[data-tq-from-line]");                     // ...and the line and the X close it too
    await page.waitForSelector("[data-tq-from-close]", { visible: true, timeout: 5000 });
    await page.click("[data-tq-from-close]");
    await page.waitForFunction(() => !document.querySelector("[data-tq-from-side]"), { timeout: 5000 });
    await page.click("[data-tq-from-line]"); await page.waitForSelector("[data-tq-from-side]", { timeout: 5000 });
    await page.click("[data-tq-from-line]"); await page.waitForFunction(() => !document.querySelector("[data-tq-from-side]"), { timeout: 5000 });
    await new Promise((r) => setTimeout(r, 600));
    assert.deepEqual(await pane(), before, "the pane is still there, the same size, after it closes");
    assert.deepEqual(resizes, [], "no resize was sent to the pty");
    await cdp.detach();
  });

  await t.test("an agent that stopped and saved: the columns return, and the work column is its Result", async () => {
    const made = await post(page, "/api/fixture/task/coding-saved");
    assert.ok(made.taskId, JSON.stringify(made));
    await open(page, made.taskId);
    await page.waitForSelector("[data-tq-work] [data-tq-result]", { timeout: 20000 });
    const l = await layout(page);
    assert.equal(l.layout, "columns");
    assert.equal(l.statusKey, "saved");
    assert.match(l.status, /stopped and saved$/);
    const r = await page.$eval("[data-tq-result]", (e) => ({ text: e.innerText, parts: [...e.querySelectorAll("[data-tq-result-part]")].map((p) => p.getAttribute("data-tq-result-part")),
      diff: e.querySelector("[data-tq-diff-stat]")?.innerText || "" }));
    assert.deepEqual(r.parts, ["What it found", "How it resolved it", "Summary", "write-up"]);
    assert.match(r.text, /A site with no manager stopped the whole census run/);
    assert.match(r.text, /Not pushed - yours to approve/);
    assert.match(r.diff, /1 file changed · \+2 −1/);
    assert.equal(await page.$("[data-tq-work] .xterm"), null, "no terminal: the session is one line");
    const heading = await page.$eval('[data-tq-work] [data-tq-step="2"]', (dot) => dot.parentElement.querySelector("p")?.textContent);
    assert.equal(heading, "Result", "the agent half is called Result");
    await page.click("[data-tq-replay]");
    await page.waitForFunction(() => document.querySelector("[data-tq-replay]")?.getAttribute("aria-expanded") === "true", { timeout: 5000 });
  });

  assert.deepEqual(errors, []);
});
