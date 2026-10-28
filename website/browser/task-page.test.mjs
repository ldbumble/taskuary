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
// ...read once the page has stopped moving: the Advisor's line, the rail's read and the canvas pin land after the task header does, and on
// a slower runner (CI's Linux, 0.3.9.48) a first read caught the reply 3px from where it came to rest - which is not the drawer moving it
const settled = async (page) => {
  let was = "", same = 0, l = null;
  for (let i = 0; i < 40 && same < 3; i++) { l = await layout(page); const k = JSON.stringify(l); same = k === was ? same + 1 : 0; was = k; await new Promise((r) => setTimeout(r, 150)); }
  return l;
};

test("the task page: From | Work at rest, the work alone while an agent works, its Result when it stopped", { timeout: 360000 }, async (t) => {
  const harness = await startHarness();
  t.after(() => harness.close());
  const page = await harness.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(harness.ui, { waitUntil: "domcontentloaded", timeout: 20000 });
  const tasks = (await (await fetch(`${harness.fixtureApi}/api/tasks`, { headers: { "X-Taskuary-Token": harness.token } })).json()).data || [];

  // ONE MAIN VIEW (the owner, 2026-10-26: "If up to agent or close out open those with coming from in left side draw"): a reply drafted is
  // the page, Came from a drawer behind the tab on the left, laid over it
  await t.test("an email task: the reply is the page, Came from behind its left tab, the triage line last, no chips by the title", async () => {
    const mail = tasks.find((x) => x.Source === "email" && x.Status === "open" && x.State === "approve");
    assert.ok(mail, "the demo world has an email reply waiting to send");
    await open(page, mail.TaskId);
    await page.waitForSelector("[data-tq-from-line]", { timeout: 20000 });
    const shut = await settled(page);
    assert.equal(shut.layout, "work");
    assert.ok(!shut.from && shut.work, `the reply alone, Came from shut: ${JSON.stringify(shut)}`);
    await page.click("[data-tq-from-line]");
    await page.waitForSelector("[data-tq-from-side] [data-tq-sorted]", { timeout: 20000 });
    const l = await settled(page);
    assert.deepEqual(l.work, shut.work, "the drawer is laid over the reply, which does not move");
    assert.ok(l.from.x <= l.work.x + 1, `Came from comes in from the left: ${JSON.stringify(l)}`);
    assert.match(l.sorted, /^Sorted as: a reply to send · \w+ priority/, "what triage made of it, at the foot of From");
    assert.equal(l.statusKey, "approve");
    assert.match(l.status, /ready to send$/, "the status is the rail's word");
    assert.equal(await page.$$eval("[data-tq-task-head] [data-tq-fact], [data-tq-task-head] .MuiChip-root", (els) => els.length), 0, "no chips by the title");
    // the header is the bold title alone and the ask is the task's first part (the owner, 2026-10-27: "top border on task is too big. It
    // should just have the bolded task name the rest should be in the task"); where it is the one message's own words From does not open
    // them again (a lone message opened whole before); the reply is the open half of the work
    assert.equal(await page.$("[data-tq-task-head] + [data-tq-ask]"), null, "nothing under the title in the header");
    assert.ok(await page.$("[data-tq-from] [data-tq-ask]"), "the ask is in the task");
    assert.equal(await page.$("[data-tq-from] [data-tq-conversation-row][aria-expanded=true]"), null, "the ask's words are read once");
    assert.ok(await page.$("[data-tq-work] [data-tq-closeout] textarea"), "the draft is in the work column");
    await page.keyboard.press("Escape");
    await page.waitForFunction(() => !document.querySelector("[data-tq-from-side]"), { timeout: 5000 });
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

  await t.test("a chat burst reads newest on top, the older lines behind Show N older", async () => {
    const made = await post(page, "/api/fixture/task/chat-burst");
    assert.ok(made.taskId, JSON.stringify(made));
    await open(page, made.taskId);
    // ...nothing drafted, so the task is the page and the burst is in it - Close out behind the lit right tab (the owner, 2026-10-26)
    await page.waitForSelector("[data-tq-work-tab][data-tq-lit]", { timeout: 20000 });
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
    assert.match(l.line, /Came from · \S/, `From folded to its tab: "${l.line}"`);
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
    // ...and the tab reads as a press: an arrow in a disc, a pointer, a title saying what it opens, a tint on hover (the owner, 2026-10-22;
    // the tab 2026-10-26: "make it with arrow and more visible to pull out where it came from")
    const look = () => page.$eval("[data-tq-from-line]", (e) => ({ chevron: e.querySelector("[data-tq-from-chevron]")?.textContent, cursor: getComputedStyle(e).cursor,
      title: e.getAttribute("title"), bg: getComputedStyle(e).backgroundColor }));
    const shut = await look();
    assert.deepEqual([shut.chevron, shut.cursor, shut.title], ["›", "pointer", "Show where this came from"]);
    await page.hover("[data-tq-from-line]");
    assert.notEqual((await look()).bg, shut.bg, "hovered, the tab tints");
    await page.click("[data-tq-from-line]");
    await page.waitForSelector("[data-tq-from-side]", { visible: true, timeout: 5000 });
    const opened = await look();
    assert.deepEqual([opened.chevron, opened.title], ["‹", "Hide where this came from"], "open, the arrow turns");
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
    await page.waitForFunction(() => !document.querySelector("[data-tq-from-side]") && document.querySelector("[data-tq-from-chevron]")?.textContent === "›", { timeout: 5000 });
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

  // ...and AN AGENT THAT HAS ACTED: its Result the one white section on the shaded body, Close out under it on the shade (the owner,
  // 2026-10-25) - the page, with Came from behind the left tab (2026-10-26: "If up to agent or close out open those with coming from in
  // left side draw")
  await t.test("an agent that stopped and saved: its Result the white focus and the page, Came from behind the left tab", async () => {
    const made = await post(page, "/api/fixture/task/coding-saved");
    assert.ok(made.taskId, JSON.stringify(made));
    await open(page, made.taskId);
    await page.waitForSelector("[data-tq-work] [data-tq-result-summary]", { timeout: 20000 });
    const l = await layout(page);
    assert.equal(l.layout, "work");
    assert.ok(!l.from && l.work, `the Result alone, Came from shut: ${JSON.stringify(l)}`);
    assert.ok(await page.$("[data-tq-from-line]"), "Came from is behind its tab");
    const shade = await page.evaluate(() => ({ focus: [...document.querySelectorAll("[data-tq-focus]")].map((e) => (e.querySelector("[data-tq-result-summary]") ? "result" : e.matches("[data-tq-closeout]") ? "closeout" : "other")),
      body: getComputedStyle(document.querySelector("[data-tq-work]").closest("[data-tq-columns]").parentElement).backgroundColor }));
    assert.deepEqual(shade.focus, ["result"], "the Result is the one white section");
    assert.equal(shade.body, "rgb(245, 242, 237)", "the body is shaded");
    assert.ok(await page.$("[data-tq-work] [data-tq-closeout]"), "Close out stays under the Result");
    assert.equal(l.statusKey, "saved");
    assert.match(l.status, /stopped and saved$/);
    // ...resting on what it did and what it made; its heading unfolds the write-up whole (the owner, 2026-10-27: "click Result to see more")
    assert.match(await page.$eval("[data-tq-result-summary]", (e) => e.innerText), /^Census sync no longer stops on a site with no manager\./);
    await page.$eval('[data-tq-work] [data-tq-step="2"]', (dot) => dot.parentElement.click());
    await page.waitForSelector("[data-tq-work] [data-tq-result]", { timeout: 10000 });
    const r = await page.$eval("[data-tq-result]", (e) => ({ text: e.innerText, parts: [...e.querySelectorAll("[data-tq-result-part]")].map((p) => p.getAttribute("data-tq-result-part")),
      diff: e.querySelector("[data-tq-diff-stat]")?.innerText || "" }));
    assert.deepEqual(r.parts, ["What it found", "How it resolved it", "Summary", "write-up"]);
    assert.match(r.text, /A site with no manager stopped the whole census run/);
    assert.match(r.text, /Not pushed - yours to approve/);
    // ...the diff folded behind its count (the task-view cleanup, owner-approved 2026-10-25)
    assert.match(r.diff, /1 file changed \+2 −1/);
    assert.equal(await page.$("[data-tq-work] .xterm"), null, "no terminal: the session is one line");
    const heading = await page.$eval('[data-tq-work] [data-tq-step="2"]', (dot) => dot.parentElement.querySelector("p")?.textContent);
    assert.equal(heading, "Result", "the agent half is called Result");
    await page.click("[data-tq-replay]");
    await page.waitForFunction(() => document.querySelector("[data-tq-replay]")?.getAttribute("aria-expanded") === "true", { timeout: 5000 });
  });

  // ...AND ON THE TABLE IT HAS THE ROOM (the owner, 2026-10-22: "this looks weird... since it gets crunched down you can not really see
  // the agent report/close out"): a task the owner made, its agent stopped and saved and its write-up still running - the card had
  // shrunk to its words (~300px), the Result folded to two lines, the From sidebar cut off, and Close out offered the advice for an
  // open task nobody sent ("Work it, or write what you found") with a "reply · not available" pill
  await t.test("a saved agent on a task nobody sent: its Result open beside Came from, the card its own height, no empty reply section", async () => {
    const made = await post(page, "/api/fixture/task/coding-saved", { mine: true, writing: true });
    assert.ok(made.taskId, JSON.stringify(made));
    await open(page, made.taskId);
    await page.waitForSelector("[data-tq-work] [data-tq-result-summary]", { timeout: 20000 });
    await page.waitForSelector("[data-tq-work] [data-tq-writeup-at=result]", { timeout: 20000 });
    const box = (sel) => page.$eval(sel, (e) => { const r = e.getBoundingClientRect(); return { x: r.left, y: r.top, w: r.width, h: r.height, bottom: r.bottom }; });
    const area = await box(".tq-chat-body");
    const item = await page.evaluate((tid) => { const r = document.querySelector(`[data-tq-task-page="${tid}"]`).closest("[data-tq-canvas-item]").getBoundingClientRect();
      return { h: r.height }; }, String(made.taskId));
    // ...but only as tall as what it says (the owner, 2026-10-22: blank under Close out) - unless its words need the whole height
    const fit = await page.evaluate((tid) => { const v = document.querySelector(`[data-tq-task-page="${tid}"]`);
      const sc = [...v.querySelectorAll("*")].find((e) => e.scrollHeight > e.clientHeight + 2 && getComputedStyle(e).overflowY === "auto");
      return { scrolls: !!sc }; }, String(made.taskId));
    assert.ok(fit.scrolls || item.h < area.h * 0.98, `no blank under the task (${Math.round(item.h)}px of ${Math.round(area.h)}px)`);
    const result = await box("[data-tq-result-summary]");
    assert.equal((await layout(page)).layout, "work", "the Result is the page (2026-10-26)");
    // the write-up's progress is a line of the Result, under it - not a box of its own in Close out
    const line = await box("[data-tq-writeup-at=result]");
    assert.ok(line.y >= result.bottom, "the write-up line sits under the Result");
    assert.match(await page.$eval("[data-tq-writeup-at=result]", (e) => e.innerText), /Writing up the session…[\s\S]*Writing the report…/);
    assert.equal(await page.$("[data-tq-closeout] [data-tq-writeup]"), null, "no progress box in Close out");
    assert.equal(await page.$("[data-tq-writing-up]"), null, "no third hint line");
    const text = await page.$eval("[data-tq-task-page]", (e) => e.innerText);
    assert.doesNotMatch(text, /Nobody sent this one/, "no advice for an open task under a Result");
    assert.doesNotMatch(text, /not available/i, "no reply pill where no reply exists");
    assert.equal(await page.$eval("[data-tq-closeout]", (e) => e.innerText.trim()), "Close out", "folded under the Result, Close out is its heading");
    // Came from is the drawer behind the left tab, scrolling on its own over the Result (2026-10-26)
    await page.click("[data-tq-from-line]");
    await page.waitForSelector("[data-tq-from-side]", { visible: true, timeout: 5000 });
    assert.equal(await page.$eval("[data-tq-from-side]", (e) => getComputedStyle(e).overflowY), "auto", "From scrolls inside itself");
    await page.keyboard.press("Escape");
    await page.waitForFunction(() => !document.querySelector("[data-tq-from-side]"), { timeout: 5000 });
    // ...and opened by hand, Close out says what closes it - still no advice and no pill - and the write-up stays the Result's line
    await page.$eval('[data-tq-closeout] [data-tq-step="3"]', (dot) => dot.parentElement.click());
    await page.waitForFunction(() => /Mark done closes it, or close it with a note\./.test(document.querySelector("[data-tq-closeout]")?.innerText || ""), { timeout: 5000 });
    const opened = await page.$eval("[data-tq-task-page]", (e) => e.innerText);
    assert.doesNotMatch(opened, /Nobody sent this one|not available/i);
    assert.ok(await page.$("[data-tq-work] [data-tq-writeup-at=result]"), "the write-up line stays with the Result");
    assert.equal(await page.$("[data-tq-closeout] [data-tq-writeup]"), null);
  });

  assert.deepEqual(errors, []);
});
