import assert from "node:assert/strict";
import test from "node:test";

import { startHarness } from "./harness.mjs";

/* THE TASK PAGE, REDESIGNED (owner-approved 2026-10-21), on the demo world - and IN THREE SECTIONS since 2026-10-27 (the owner: "input ->
   agent/advisor -> close ... opens up to the one it's up to"): Came from | Agent | Close out, the one the task is up to open; a live agent
   nearly the whole width, Came from and Close out slim tabs, a terminal nothing covers; the agent's Result when it has stopped and saved;
   From newest on top with the older lines folded; and the header's status the rail's own. */

const post = (page, path, body = {}) => page.evaluate(async ({ path, body }) => {
  const headers = { "X-Taskuary-Token": localStorage.getItem("taskuary_token"), "Content-Type": "application/json" };
  const r = await fetch(path, { method: "POST", headers, body: JSON.stringify(body) });
  return r.json();
}, { path, body });
const open = async (page, id) => {
  await page.evaluate((tid) => { window.location.hash = `task=${tid}`; }, id);
  await page.waitForFunction((tid) => !!document.querySelector(`[data-tq-task-page="${tid}"] [data-tq-task-head]`), { timeout: 20000 }, String(id));
};
// the view on the table, its sections and where they sit (a closed section is not drawn: null)
const layout = (page) => page.evaluate(() => {
  const box = (sel) => { const e = document.querySelector(sel); if (!e) return null; const r = e.getBoundingClientRect(); return r.width ? { x: r.left, y: r.top, w: r.width, h: r.height, right: r.right } : null; };
  return { layout: document.querySelector("[data-tq-columns]")?.getAttribute("data-tq-layout"), main: document.querySelector("[data-tq-task-body]")?.getAttribute("data-tq-main"),
    from: box("[data-tq-from]"), work: box("[data-tq-work]"), closeout: box("[data-tq-closeout]"),
    fromTab: document.querySelector("[data-tq-section-tab=from]")?.getAttribute("title") || "", status: document.querySelector("[data-tq-status-pill]")?.innerText.trim() || "",
    statusKey: document.querySelector("[data-tq-status-pill]")?.getAttribute("data-tq-status-pill") || "",
    head: document.querySelector("[data-tq-task-head]")?.innerText || "", sorted: document.querySelector("[data-tq-sorted]")?.innerText || "" };
});
// ...read once the page has stopped moving: the Advisor's line, the rail's read and the canvas pin land after the task header does, and on
// a slower runner (CI's Linux, 0.3.9.48) a first read caught the reply 3px from where it came to rest - which is not the drawer moving it
const settled = async (page) => {
  let was = "", same = 0, l = null;
  for (let i = 0; i < 40 && same < 3; i++) { l = await layout(page); const k = JSON.stringify(l); same = k === was ? same + 1 : 0; was = k; await new Promise((r) => setTimeout(r, 150)); }
  return l;
};

test("the task page: three sections at rest, the agent nearly the whole width while it works, its Result when it stopped", { timeout: 360000 }, async (t) => {
  const harness = await startHarness();
  t.after(() => harness.close());
  const page = await harness.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(harness.ui, { waitUntil: "domcontentloaded", timeout: 20000 });
  const tasks = (await (await fetch(`${harness.fixtureApi}/api/tasks`, { headers: { "X-Taskuary-Token": harness.token } })).json()).data || [];

  // ONE MAIN VIEW (the owner, 2026-10-26), THREE SECTIONS (2026-10-27): a reply drafted opens on Close out, Came from its tab on the left
  await t.test("an email task: Close out is open, Came from behind its tab, what triage made of it in Came from, no chips by the title", async () => {
    const mail = tasks.find((x) => x.Source === "email" && x.Status === "open" && x.State === "approve");
    assert.ok(mail, "the demo world has an email reply waiting to send");
    await open(page, mail.TaskId);
    await page.waitForSelector("[data-tq-section-tab=from]", { timeout: 20000 });
    const shut = await settled(page);
    assert.equal(shut.layout, "sections");
    assert.equal(shut.main, "close");
    assert.ok(!shut.from && shut.closeout, `the reply alone, Came from shut: ${JSON.stringify(shut)}`);
    await page.click("[data-tq-section-tab=from]");
    await page.waitForSelector("[data-tq-from] [data-tq-sorted]", { visible: true, timeout: 20000 });
    const l = await settled(page);
    assert.ok(l.from && !l.closeout, `Came from open, Close out its tab: ${JSON.stringify(l)}`);
    assert.ok(l.from.x < shut.closeout.x, `Came from is on the left: ${JSON.stringify(l)}`);
    assert.match(l.sorted, /What triage made of it\s+a reply to send · \w+ priority/, "what triage made of it, in Came from");
    assert.equal(l.statusKey, "approve");
    assert.match(l.status, /ready to send$/, "the status is the rail's word");
    assert.equal(await page.$$eval("[data-tq-task-head] [data-tq-fact], [data-tq-task-head] .MuiChip-root", (els) => els.length), 0, "no chips by the title");
    // the header is the bold title alone and the ask is the task's first part (the owner, 2026-10-27: "top border on task is too big. It
    // should just have the bolded task name the rest should be in the task"); where it is the one message's own words From does not open
    // them again (a lone message opened whole before); the draft stays in Close out, kept while it is shut
    assert.equal(await page.$("[data-tq-task-head] + [data-tq-ask]"), null, "nothing under the title in the header");
    assert.ok(await page.$("[data-tq-from] [data-tq-ask]"), "the ask is in the task");
    assert.equal(await page.$("[data-tq-from] [data-tq-conversation-row][aria-expanded=true]"), null, "the ask's words are read once");
    assert.ok(await page.$("[data-tq-closeout] textarea"), "the draft is in Close out");
    await page.click("[data-tq-section-tab=close]");
    await page.waitForSelector("[data-tq-closeout] textarea", { visible: true, timeout: 5000 });
    // ...and the header's status is the rail row's own: the same words on the row's icon
    await page.waitForSelector(".tq-pile-row.current .tq-mark[role=img]", { timeout: 20000 });
    assert.equal(await page.$eval(".tq-pile-row.current .tq-mark", (e) => e.getAttribute("aria-label")),
      await page.$eval("[data-tq-status-pill] .word", (e) => e.textContent));
  });

  await t.test("a rail row carries its state in its icon - the ring while an agent works, a 👋 or 🏁 badge, or nothing - and no status words on its right", async () => {
    const rows = await page.$$eval("[data-tq-rail] .tq-pile-row", (els) => els.map((r) => { const m = r.querySelector(".tq-mark"); return {
      key: r.getAttribute("data-tq-key"), mark: m?.getAttribute("data-tq-status") || "", label: m?.getAttribute("aria-label") || "",
      badge: r.querySelector(".tq-mark .badge")?.textContent || "", ring: !!r.querySelector(".tq-mark.spins"), kids: m ? m.children.length : 0,
      after: m ? getComputedStyle(m, "::after").content : "none",
      word: r.querySelector(".tq-pile-word")?.innerText || "", band: r.closest("[data-tq-run]")?.getAttribute("data-tq-run") }; }));
    const tasks = rows.filter((r) => r.band === "task" && r.mark);
    assert.ok(tasks.length >= 5, `rows under Tasks wear their state: ${JSON.stringify(rows)}`);
    for (const r of tasks) {
      assert.ok(r.label, `${r.key} says its state in words`);
      assert.ok(!(r.ring && r.badge), `${r.key} wears the ring or a badge, never both: ${JSON.stringify(r)}`);
      // a badge only where the move is the owner's (the owner, 2026-10-22: too many emojis on the rail)
      assert.ok(["", "👋", "🏁"].includes(r.badge), `${r.key}: the only badges are the hand and the flag, not ${r.badge}`);
      if (r.badge) assert.ok(["blocked", "asked", "approve"].includes(r.mark), `${r.key}: a ${r.badge} only on waiting-on-you or ready to send`);
      else if (!r.ring) assert.ok(!["blocked", "asked", "approve"].includes(r.mark), `${r.key}: ${r.mark} wears its badge`);
      // no ring round the logo but the working one - the shaped rings are gone (the owner, 2026-10-22)
      assert.equal(r.after !== "none", r.ring, `${r.key}: only a working row draws a ring`);
      assert.equal(r.word, "", `${r.key} has no status word on its right`);
    }
    assert.ok(tasks.some((r) => r.mark === "approve" && r.badge === "🏁" && r.label === "ready to send"), "ready to send is a 🏁 badge, said in words");
    const ring = rows.find((r) => r.ring);
    if (ring) assert.match(ring.label, /is working on this$/);
  });

  await t.test("a chat burst reads as one flow under the boxes: its latest five, newest last, Show all the sixth", async () => {
    const made = await post(page, "/api/fixture/task/chat-burst");
    assert.ok(made.taskId, JSON.stringify(made));
    await open(page, made.taskId);
    // ...the burst is Came from's: its tab, then the Conversation under the two boxes (the one flow, 2026-10-28)
    await page.waitForSelector("[data-tq-task-body][data-tq-sections]", { timeout: 20000 });
    if (await page.$("[data-tq-section-tab=from]")) await page.click("[data-tq-section-tab=from]");
    await page.waitForSelector("[data-tq-from] [data-tq-conversation-block] [data-tq-conversation-row]", { visible: true, timeout: 20000 });
    const rows = () => page.$$eval("[data-tq-from] [data-tq-conversation-row]", (els) => els.map((e) => e.innerText.replace(/\s+/g, " ").trim()));
    const first = await rows();
    assert.equal(first.length, 5, `the latest five: ${first}`);
    assert.match(first[4], /Gail Moreno and bring the floor plan please/, "the newest last");
    assert.match(first[2], /Gail Moreno Alex, can you be there at 9:30\?/);
    await page.click("[data-tq-from] [data-tq-conversation-more]");
    const all = await rows();
    assert.equal(all.length, 6, "Show all opens the sixth in place");
    assert.match(all[0], /Morning all/, "the opening line first");
  });

  await t.test("a coding agent working keeps nearly the whole width; Came from and Close out are slim tabs and nothing covers the terminal", async () => {
    const coding = tasks.find((x) => x.Kind === "coding" && /census sync/.test(x.Title) && !["done", "dropped"].includes(x.Status));
    assert.ok(coding, "the demo world's census sync session");
    await open(page, coding.TaskId);
    await page.waitForSelector(".xterm-screen", { timeout: 20000 });
    await page.waitForFunction(() => document.querySelector("[data-tq-task-body]")?.getAttribute("data-tq-main") === "agent", { timeout: 20000 });
    const l = await layout(page);
    assert.equal(l.from, null, "no Came from section while the agent works");
    assert.match(l.fromTab, /Came from[\s\S]*1 message/, `Came from folded to its slim tab, its words on hover: "${l.fromTab}"`);
    assert.ok(["working", "blocked"].includes(l.statusKey), `the rail's working or waiting status: ${l.statusKey}`);
    const term = await page.evaluate(() => {
      const view = document.querySelector("[data-tq-task-page] [data-tq-task-head]").parentElement.getBoundingClientRect();
      const x = document.querySelector(".xterm-screen").getBoundingClientRect();
      const hits = [[0.5, 0.5], [0.1, 0.1], [0.9, 0.2], [0.5, 0.9]].map(([fx, fy]) => document.elementFromPoint(x.left + x.width * fx, x.top + Math.min(x.height, 300) * fy));
      return { share: x.width / view.width, covered: hits.filter((h) => !h?.closest(".xterm")).length, h: x.height };
    });
    assert.ok(term.share > 0.85, `the terminal has nearly the whole width (${Math.round(term.share * 100)}%)`);
    assert.equal(term.covered, 0, "nothing is drawn over the terminal");
    assert.ok(term.h > 200, `the terminal is not squeezed (${term.h}px)`);
  });

  // ITEM 6 (the owner, 2026-10-21): a look at where it came from never refits the terminal or sends the pty a resize - now Came from's slim
  // tab opens its section and the agent folds to its tab, its terminal kept (hidden, never measured at nothing); its tab brings it back
  await t.test("Came from's tab over the running coding pane: the terminal keeps its size and gets no resize", async () => {
    const cdp = await page.createCDPSession();
    await cdp.send("Network.enable");
    const resizes = [];
    cdp.on("Network.webSocketFrameSent", ({ response }) => { try { if (JSON.parse(response.payloadData).type === "resize") resizes.push(response.payloadData); } catch { /* not json */ } });
    const pane = () => page.evaluate(() => {
      const x = document.querySelector(".xterm-screen"), r = x?.getBoundingClientRect();
      return x ? { w: Math.round(r.width), h: Math.round(r.height), rows: document.querySelectorAll(".xterm-rows > div").length } : null;
    });
    await new Promise((r) => setTimeout(r, 1500));               // the pane's own first fit settles before the clock starts
    resizes.length = 0;
    const before = await pane();
    assert.ok(before, "the coding pane is there");
    // ...and the tab reads as a press: an arrow in a disc, a pointer, a title saying what it opens, a tint on hover
    const look = () => page.$eval("[data-tq-section-tab=from]", (e) => ({ arrow: e.querySelector("[data-tq-tab-arrow]")?.textContent, cursor: getComputedStyle(e).cursor,
      label: e.getAttribute("aria-label"), bg: getComputedStyle(e).backgroundColor }));
    const shut = await look();
    assert.deepEqual([shut.arrow, shut.cursor, shut.label], ["›", "pointer", "Open Came from"]);
    await page.hover("[data-tq-section-tab=from]");
    assert.notEqual((await look()).bg, shut.bg, "hovered, the tab tints");
    await page.click("[data-tq-section-tab=from]");
    await page.waitForSelector("[data-tq-from]", { visible: true, timeout: 5000 });
    assert.match(await page.$eval("[data-tq-from]", (e) => e.innerText), /What came in/, "the same Came from every other task shows");
    await new Promise((r) => setTimeout(r, 600));
    await page.click("[data-tq-section-tab=agent]");
    await page.waitForFunction(() => document.querySelector("[data-tq-task-body]")?.getAttribute("data-tq-main") === "agent", { timeout: 5000 });
    await new Promise((r) => setTimeout(r, 600));
    assert.deepEqual(await pane(), before, "the pane is still there, the same size, after the look away");
    assert.deepEqual(resizes, [], "no resize was sent to the pty");
    await cdp.detach();
  });

  // ...and AN AGENT THAT HAS ACTED: its Result the one white section, the Agent open (the owner, 2026-10-25; three sections 2026-10-27)
  await t.test("an agent that stopped and saved: the Agent open on its Result, Came from and Close out its tabs", async () => {
    const made = await post(page, "/api/fixture/task/coding-saved");
    assert.ok(made.taskId, JSON.stringify(made));
    await open(page, made.taskId);
    await page.waitForSelector("[data-tq-work] [data-tq-result-summary]", { visible: true, timeout: 20000 });
    const l = await layout(page);
    assert.equal(l.main, "agent");
    assert.ok(!l.from && l.work && !l.closeout, `the Result alone, Came from and Close out shut: ${JSON.stringify(l)}`);
    assert.ok(await page.$("[data-tq-section-tab=from]") && await page.$("[data-tq-section-tab=close]"), "Came from and Close out are behind their tabs");
    const shade = await page.evaluate(() => [...document.querySelectorAll("[data-tq-focus]")].filter((e) => e.getBoundingClientRect().width)
      .map((e) => (e.querySelector("[data-tq-result-summary]") ? "result" : e.matches("[data-tq-closeout]") ? "closeout" : "other")));
    assert.deepEqual(shade, ["result"], "the Result is the one white section");
    assert.equal(l.statusKey, "saved");
    assert.match(l.status, /stopped and saved$/);
    // ...resting on what it did and what it made; its heading - or the one Full results and record press - unfolds the write-up whole
    assert.match(await page.$eval("[data-tq-result-summary]", (e) => e.innerText), /^Census sync no longer stops on a site with no manager\./);
    assert.ok(await page.$("[data-tq-work] [data-tq-full-result]"), "one press for the full results and record");
    await page.$eval('[data-tq-work]', (w) => (w.querySelector('[data-tq-full-result]') || w.querySelector('[data-tq-step="2"]').parentElement).click());
    await page.waitForSelector("[data-tq-work] [data-tq-result]", { timeout: 10000 });
    const r = await page.$eval("[data-tq-result]", (e) => ({ text: e.innerText, parts: [...e.querySelectorAll("[data-tq-result-part]")].map((p) => p.getAttribute("data-tq-result-part")),
      diff: e.querySelector("[data-tq-diff-stat]")?.innerText || "" }));
    assert.deepEqual(r.parts, ["What it found", "How it resolved it", "Summary", "write-up"]);
    assert.match(r.text, /A site with no manager stopped the whole census run/);
    assert.match(r.text, /Not pushed - yours to approve/);
    // ...the diff folded behind its count (the task-view cleanup, owner-approved 2026-10-25)
    assert.match(r.diff, /1 file changed \+2 −1/);
    assert.equal(await page.$("[data-tq-work] .xterm"), null, "no terminal: the session is one line");
    const heading = await page.$eval('[data-tq-work] [data-tq-step="2"]', (dot) => dot.parentElement.innerText);
    // ...the section's own heading, no second way to the record (the owner, 2026-10-27: "why are there 2 buttons for full results?")
    assert.match(heading, /^Agent/, "the agent's section, by its name alone (2026-10-28)");
    assert.equal(await page.$eval('[data-tq-work] [data-tq-step="2"]', (dot) => dot.parentElement.getAttribute("aria-expanded")), null, "the heading folds nothing");
    await page.click("[data-tq-replay]");
    await page.waitForFunction(() => document.querySelector("[data-tq-replay]")?.getAttribute("aria-expanded") === "true", { timeout: 5000 });
  });

  // ...AND IT HAS THE ROOM (the owner, 2026-10-22: "since it gets crunched down you can not really see the agent report/close out"): a task the
  // owner made, its agent stopped and saved and its write-up still running - Close out offered the advice for an open task nobody sent
  // ("Work it, or write what you found") with a "reply · not available" pill
  await t.test("a saved agent on a task nobody sent: its Result open, the card the canvas, no empty reply section", async () => {
    const made = await post(page, "/api/fixture/task/coding-saved", { mine: true, writing: true });
    assert.ok(made.taskId, JSON.stringify(made));
    await open(page, made.taskId);
    await page.waitForSelector("[data-tq-work] [data-tq-result-summary]", { visible: true, timeout: 20000 });
    await page.waitForSelector("[data-tq-work] [data-tq-writeup-at=result]", { timeout: 20000 });
    const box = (sel) => page.$eval(sel, (e) => { const r = e.getBoundingClientRect(); return { x: r.left, y: r.top, w: r.width, h: r.height, bottom: r.bottom }; });
    const area = await box(".tq-chat-body");
    const item = await page.evaluate((tid) => document.querySelector(`[data-tq-task-page="${tid}"]`).closest("[data-tq-canvas-item]").getBoundingClientRect().height, String(made.taskId));
    // ...the card takes the canvas, a small gap over the dock (2026-10-27); a short section is white under its words
    assert.ok(item >= area.h - 30, `the card takes the canvas (${Math.round(item)}px of ${Math.round(area.h)}px)`);
    const result = await box("[data-tq-result-summary]");
    assert.equal((await layout(page)).main, "agent", "the Result is the open section");
    // the write-up's progress is a line of the Result, under it - not a box of its own in Close out
    const line = await box("[data-tq-writeup-at=result]");
    assert.ok(line.y >= result.bottom, "the write-up line sits under the Result");
    assert.match(await page.$eval("[data-tq-writeup-at=result]", (e) => e.innerText), /Writing up the session…[\s\S]*Writing the report…/);
    assert.equal(await page.$("[data-tq-closeout] [data-tq-writeup]"), null, "no progress box in Close out");
    assert.equal(await page.$("[data-tq-writing-up]"), null, "no third hint line");
    const text = await page.$eval("[data-tq-task-page]", (e) => e.innerText);
    assert.doesNotMatch(text, /Nobody sent this one/, "no advice for an open task under a Result");
    assert.doesNotMatch(text, /not available/i, "no reply pill where no reply exists");
    // ...Close out's tab says there is nothing owed; opened, it says what closes it - still no advice and no pill
    assert.match(await page.$eval("[data-tq-section-tab=close]", (e) => e.innerText), /Nothing owed/);
    await page.click("[data-tq-section-tab=from]");
    await page.waitForSelector("[data-tq-from]", { visible: true, timeout: 5000 });
    assert.equal(await page.$eval("[data-tq-from]", (e) => getComputedStyle(e).overflowY), "auto", "Came from scrolls inside itself");
    await page.click("[data-tq-section-tab=close]");
    // ...its heading the name alone - its explanation was small text that did not help (the owner, 2026-10-28)
    await page.waitForFunction(() => document.querySelector("[data-tq-task-body]")?.getAttribute("data-tq-main") === "close" && !!document.querySelector("[data-tq-closeout]"), { timeout: 5000 });
    const opened = await page.$eval("[data-tq-task-page]", (e) => e.innerText);
    assert.doesNotMatch(opened, /Nobody sent this one|not available/i);
    assert.ok(await page.$("[data-tq-work] [data-tq-writeup-at=result]"), "the write-up line stays with the Result");
    assert.equal(await page.$("[data-tq-closeout] [data-tq-writeup]"), null);
  });

  assert.deepEqual(errors, []);
});
