import assert from "node:assert/strict";
import test from "node:test";

import { startHarness } from "./harness.mjs";

/* THE STAGE MOVES RIDE ON THEIR PANE, THE CHAT IS ITS OWN UNIT (the owner, 2026-10-29, after three mockups). On the demo world at 1440 and
   1366: the bar keeps Back and Next and what acts on the whole task (Mark done, Change, Share, Hand it to a person, Close with a note,
   Attach a file); the moves that take the task a stage on - Send to agent / Continue / Run another, Draft reply / Reply / Redraft / Hand it
   to a person, and Came from's Not a task / Remind me - stand on their pane's spine while it is folded, under a rule below its words, and
   inside it while it is open, never on the bar. A spine's press opens its pane and starts the step there - Hand it to a person a compose
   card in Close out. Open, a pane wears a white strip across its top: its name, its moves and the arrows that fold it back. A live agent's bar is Back, Next and Stop and save. The chat is a small pill in the
   corner, apart from the bar, typeable at rest: typing opens it out of its corner into the window, and a line sent lands in it.
   And no pane is a dead end: every open task's open Agent pane and Close out carry their own way on. Invented people only. */
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let CUR = "[data-tq-canvas-item]";
const openTask = async (page, id) => {
  CUR = `[data-tq-canvas-item]:has([data-tq-task-page="${id}"])`;
  await page.evaluate((id) => { location.hash = ""; location.hash = `task=${id}`; }, id);
  await page.waitForSelector(`${CUR} [data-tq-task-body][data-tq-sections]`, { timeout: 20000 });
  await sleep(1500);
};
const openSec = async (page, key) => {
  if (await page.$(`${CUR} [data-tq-slot=${key}][data-tq-open]`)) return;
  await page.click(`${CUR} [data-tq-section-tab=${key}] [data-tq-tab-name]`);
  await page.waitForSelector(`${CUR} [data-tq-slot=${key}][data-tq-open]`, { timeout: 5000 }); await sleep(500);
};
// what the page shows: the bar's buttons, each spine's stage moves, each open pane's heading moves, and where the spine's moves stand in it
const look = (page) => page.evaluate((CUR) => {
  const vis = (b) => !!b.offsetParent && getComputedStyle(b).visibility !== "hidden";
  const words = (sel) => [...document.querySelectorAll(sel)].filter(vis).map((b) => b.textContent.trim()).filter(Boolean);
  const spine = (k) => { const tab = document.querySelector(`${CUR} [data-tq-section-tab=${k}]`); if (!tab) return null;
    const y = (s) => tab.querySelector(s)?.getBoundingClientRect(), moves = y("[data-tq-spine-moves]");
    return { moves: [...tab.querySelectorAll("[data-tq-spine-moves] button")].map((b) => ({ word: b.textContent.trim(), lit: b.classList.contains("p") })),
      between: !moves || (y("[data-tq-tab-name]").bottom <= moves.top && moves.bottom <= y("[data-tq-tab-foot]").top), text: tab.innerText,
      rule: !moves || getComputedStyle(tab.querySelector("[data-tq-spine-moves]")).borderTopWidth === "1px" }; };
  return { bar: words("[data-tq-row] .tq-arow-verbs button").filter((w) => w !== "▾"), open: document.querySelector(`${CUR} [data-tq-slot][data-tq-open]`)?.dataset.tqSlot,
    from: spine("from"), agent: spine("agent"), close: spine("close"),
    pane: { from: words(`${CUR} [data-tq-pane-moves=from] button`), agent: words(`${CUR} [data-tq-pane-moves=agent] button`), close: words(`${CUR} [data-tq-pane-moves=close] button`) } };
}, CUR);
const STAGE = /^(Send to agent|Continue|Try again|Run another agent|Reply|Draft reply|Redraft|Draft with AI|Starting…|Drafting…|Hand it to a person|Remind me|Remove - not a task|Back .+)$/;
const FROM = ["Remind me", "Remove - not a task"];

for (const [w, h] of [[1440, 900], [1366, 768]]) {
  test(`stage moves on their pane, the bar the task's, the chat its own unit - ${w}x${h}`, { timeout: 400000 }, async (t) => {
    const hz = await startHarness();
    t.after(() => hz.close());
    const page = await hz.newPage();
    const errors = [];
    page.on("pageerror", (e) => errors.push(e.message));
    await page.setViewport({ width: w, height: h, deviceScaleFactor: 1 });
    await page.goto(hz.ui, { waitUntil: "domcontentloaded" });
    await page.waitForSelector("[data-tq-rail] .tq-pile-row", { timeout: 30000 });
    const tasks = (await (await fetch(`${hz.fixtureApi}/api/tasks`, { headers: { "X-Taskuary-Token": hz.token } })).json()).data;
    const id = (re) => tasks.find((x) => re.test(x.Title))?.TaskId;

    await t.test("Close out open: Send to agent on Agent's spine, in the middle of it; the bar the task's own moves", async () => {
      await openTask(page, id(/^Invoice 88213/));
      await openSec(page, "close");
      const m = await look(page);
      assert.deepEqual(m.agent.moves.map((x) => x.word), ["Send to agent"], JSON.stringify(m.agent));
      assert.ok(m.agent.between && m.agent.rule, "between the pane's name and its status, under a rule");
      assert.deepEqual(m.from.moves.map((x) => x.word).sort(), FROM, `Came from's spine: Not a task and Remind me ${JSON.stringify(m.from)}`);
      assert.ok(m.from.between && m.from.rule);
      assert.match(m.agent.text, /^\W*Agent\s+not started[\s\S]*Send to agent[\s\S]*2$/, "the spine's words as they were, the move in their middle");
      assert.ok(m.bar.includes("Mark done") && m.bar.includes("Share"), `the bar: ${m.bar}`);
      assert.ok(!m.bar.some((x) => STAGE.test(x)), `no stage move on the bar: ${m.bar}`);
    });

    await t.test("an open pane's white strip: its name, its moves, and arrows that fold it back to its spine", async () => {
      for (const [key, arrows] of [["close", ["left"]], ["agent", ["left", "right"]], ["from", ["right"]]]) {
        await openSec(page, key);
        const st = await page.evaluate((CUR, key) => { const e = document.querySelector(`${CUR} [data-tq-slot=${key}] [data-tq-pane-strip=${key}]`); if (!e) return null;
          const r = e.getBoundingClientRect(), s = e.closest("[data-tq-slot]").getBoundingClientRect();
          return { text: e.innerText, top: Math.round(r.top - s.top), w: Math.round(s.width - r.width), bg: getComputedStyle(e).backgroundColor,
            arrows: [...e.querySelectorAll("[data-tq-strip-fold]")].map((a) => a.dataset.tqStripFold) }; }, CUR, key);
        assert.ok(st && st.top === 0 && st.w <= 1 && st.bg === "rgb(255, 255, 255)", `${key}: a white strip across the pane's top ${JSON.stringify(st)}`);
        assert.match(st.text, { close: /^Close out/, agent: /^Agent/, from: /^Came from/ }[key], JSON.stringify(st));
        assert.deepEqual(st.arrows, arrows, `${key}'s fold arrows`);
      }
      await page.click(`${CUR} [data-tq-pane-strip=from] [data-tq-strip-fold=right]`);
      await page.waitForFunction((CUR) => !document.querySelector(`${CUR} [data-tq-slot=from][data-tq-open]`), { timeout: 5000 }, CUR);
      assert.ok(await page.$(`${CUR} [data-tq-section-tab=from]`), "folded back to its spine");
    });

    await t.test("Agent open: Redraft on Close out's spine; the agent's start is its form's, not the bar's", async () => {
      await openSec(page, "agent");
      // ...once the draft card's own verbs have come round again after the switch
      await page.waitForSelector(`${CUR} [data-tq-section-tab=close] [data-tq-spine-moves] button`, { timeout: 5000 }).catch(() => {});
      const m = await look(page);
      assert.deepEqual(m.close.moves.map((x) => x.word), ["Redraft", "Hand it to a person"], JSON.stringify(m.close));
      assert.ok(m.close.between && m.close.rule);
      assert.ok(!m.bar.some((x) => STAGE.test(x)), `no stage move on the bar: ${m.bar}`);
      assert.ok(m.bar.includes("Mark done"), `${m.bar}`);
      assert.ok(await page.$(`${CUR} [data-tq-run-form]`), "the agent's own form carries its start");
    });

    await t.test("nothing drafted: the spine says Draft reply, and its press opens Close out and starts the draft there", async () => {
      await openTask(page, id(/^Year-end audit/));
      await openSec(page, "agent");
      const m = await look(page);
      assert.deepEqual(m.close.moves.map((x) => x.word), ["Draft reply", "Hand it to a person"], JSON.stringify(m.close));
      await page.click(`${CUR} [data-tq-spine-moves=close] button[data-tq-verb=reply]`);
      await page.waitForSelector(`${CUR} [data-tq-slot=close][data-tq-open]`, { timeout: 5000 });
      await page.waitForFunction((CUR) => /Drafting|AI drafted|Redraft|Send/.test(document.querySelector(`${CUR} [data-tq-slot=close]`)?.innerText || ""),
        { timeout: 20000 }, CUR);
    });

    await t.test("Came from open: both spines carry their stage move; a press on the rest of a spine still opens it", async () => {
      await openTask(page, id(/^Invoice 88213/));
      await openSec(page, "from");
      const m = await look(page);
      assert.deepEqual([m.agent.moves.map((x) => x.word), m.close.moves.map((x) => x.word)], [["Send to agent"], ["Redraft", "Hand it to a person"]], JSON.stringify(m));
      assert.deepEqual([...m.pane.from].sort(), FROM, `Came from open: its heading carries Not a task and Remind me ${JSON.stringify(m.pane)}`);
      assert.ok(!m.bar.some((x) => STAGE.test(x)), `no stage move on the bar: ${m.bar}`);
      await page.click(`${CUR} [data-tq-section-tab=agent] [data-tq-tab-n]`);
      await page.waitForSelector(`${CUR} [data-tq-slot=agent][data-tq-open]`, { timeout: 5000 });
    });

    await t.test("Hand it to a person on Close out's spine opens Close out with the hand-off as a compose card in it - no drawer", async () => {
      await openTask(page, id(/^Invoice 88213/));
      await openSec(page, "agent");
      await page.click(`${CUR} [data-tq-spine-moves=close] button[data-tq-verb=hand]`);
      await page.waitForSelector(`${CUR} [data-tq-slot=close][data-tq-open] [data-tq-handoff-card] input`, { timeout: 8000 });
      const h = await page.evaluate((CUR) => ({ drawer: !!document.querySelector(".MuiDrawer-root .MuiDrawer-paper"),
        send: [...document.querySelectorAll(`${CUR} [data-tq-handoff-card] button`)].map((b) => b.textContent.trim()) }), CUR);
      assert.ok(!h.drawer, "no drawer over the page");
      assert.ok(h.send.includes("Send it") && h.send.some((x) => /Draft with AI|Redraft/.test(x)), `who, the forward and its own Send it: ${h.send}`);
      await page.click(`${CUR} [data-tq-handoff-card] [aria-label="Close handoff"]`);
      await page.waitForFunction((CUR) => !document.querySelector(`${CUR} [data-tq-handoff-card]`), { timeout: 5000 }, CUR);
    });

    await t.test("a live agent's bar is Back, Next and Stop and save - nothing else", async () => {
      const live = tasks.find((x) => x.State === "working" || /census sync fails/.test(x.Title));
      await openTask(page, live.TaskId);
      await page.waitForSelector(`${CUR} .xterm`, { timeout: 20000 }); await sleep(800);
      const m = await look(page);
      assert.deepEqual(m.bar.filter((x) => !/^(← )?Back$|^Next/.test(x)), ["Stop and save"], `${m.bar}`);
      assert.ok(m.bar.some((x) => /^Next/.test(x)), `Next stays: ${m.bar}`);
      const st = await page.evaluate((CUR) => { const e = document.querySelector(`${CUR} [data-tq-pane-strip=agent]`);
        return e && { live: e.hasAttribute("data-tq-live"), h: Math.round(e.getBoundingClientRect().height), stop: !!e.querySelector("[data-tq-strip-stop]"),
          arrows: e.querySelectorAll("[data-tq-strip-fold]").length, words: e.innerText.trim() }; }, CUR);
      assert.ok(st && st.live && st.h <= 34 && st.stop && st.arrows === 2 && !st.words, `a live agent's strip is slim: Stop and save and its arrows, small ${JSON.stringify(st)}`);
    });

    await t.test("the chat is a small pill in the corner, the bar ending before it", async () => {
      await openTask(page, id(/^Invoice 88213/));
      const g = await page.evaluate(() => { const r = (s) => document.querySelector(s)?.getBoundingClientRect();
        const pill = r(".tq-chat-unit .tq-compose-box"), bar = r(".tq-dock"), cv = r(".tq-asst-col");
        return { pill: pill && { l: pill.left, r: pill.right, w: pill.width, h: pill.height, b: pill.bottom }, bar: bar && { r: bar.right, b: bar.bottom }, cv: cv && { r: cv.right, b: cv.bottom },
          inBar: !!document.querySelector(".tq-dock .tq-compose-box") }; });
      assert.ok(g.pill && !g.inBar, `the box is not on the bar: ${JSON.stringify(g)}`);
      assert.ok(g.pill.w >= 300 && g.pill.h <= 48, `the wide ask bar, as wide as the open window (the owner, 2026-10-29): ${JSON.stringify(g.pill)}`);
      assert.ok(g.pill.l - g.bar.r >= 12, `a gap between the bar and the chat: ${JSON.stringify(g)}`);
      assert.ok(g.cv.r - g.pill.r <= 40 && g.cv.b - g.pill.b <= 30, `in the corner: ${JSON.stringify(g)}`);
    });

    await t.test("typed into at rest, the pill opens out of its corner into the window, and the line sent lands in it", async () => {
      const before = await page.$eval(".tq-chat-unit .tq-compose-box", (e) => e.getBoundingClientRect().right);
      await page.click(".tq-chat-unit textarea");
      await page.keyboard.type("What does Tom want?");
      await page.waitForSelector(".tq-chat-unit .tq-compose-box[data-tq-open]", { timeout: 5000 });
      await page.waitForFunction(() => { const p = document.querySelector("[data-tq-chat-pop]"); return p && !p.hidden && p.getBoundingClientRect().height > 100; }, { timeout: 5000 });
      const g = await page.evaluate(() => { const b = document.querySelector(".tq-chat-unit .tq-compose-box").getBoundingClientRect(), p = document.querySelector("[data-tq-chat-pop]").getBoundingClientRect();
        return { w: b.width, r: b.right, pr: p.right, pb: p.bottom, bt: document.querySelector(".tq-chat-unit .tq-compose-field").getBoundingClientRect().top,
          text: document.querySelector(".tq-chat-unit textarea").value }; });
      assert.equal(g.text, "What does Tom want?", "every key typed at rest is in the box");
      assert.ok(g.w >= 300, `the window's width: ${g.w}`);
      assert.ok(Math.abs(g.r - before) <= 2 && Math.abs(g.pr - g.r) <= 2, `out of the pill's own corner: ${JSON.stringify(g)} from ${before}`);
      assert.ok(Math.abs(g.pb - g.bt) <= 2, `the window stands on its field: ${JSON.stringify(g)}`);
      await page.keyboard.press("Enter");
      await page.waitForFunction(() => /What does Tom want\?/.test(document.querySelector("[data-tq-chat-pop] .tq-chat-pop-body")?.innerText || ""), { timeout: 15000 });
      await page.click("[data-tq-box-close]");
      await page.waitForFunction(() => !document.querySelector(".tq-chat-unit .tq-compose-box[data-tq-open]")
        && document.querySelector(".tq-chat-unit .tq-compose-box").getBoundingClientRect().width >= 300, { timeout: 5000 });
    });

    await t.test("no dead end: every open task's open Agent pane and Close out carry their own way on", async () => {
      const open = tasks.filter((x) => !["done", "dropped"].includes(x.Status));
      const miss = [];
      for (const task of open) {
        await openTask(page, task.TaskId);
        if (await page.$(`${CUR} .xterm`)) continue;   // a live agent: its bar's Stop and save (above)
        const from = await (async () => { await openSec(page, "from"); return (await look(page)).pane.from; })();
        if (!from.includes("Remove - not a task") || !from.some((x) => /^(Remind me|Back .+)$/.test(x))) miss.push(`${task.Title} · from: ${from}`);
        for (const key of ["agent", "close"]) {
          await openSec(page, key);
          const way = await page.evaluate((CUR, key) => {
            const slot = document.querySelector(`${CUR} [data-tq-slot=${key}]`);
            return [...slot.querySelectorAll("button")].filter((b) => b.offsetParent && !b.closest("[data-tq-section-tab]"))
              .map((b) => b.textContent.trim()).filter((x) => /^(Send to agent|Start an agent|Continue|Try again|Run another agent|Reply|Draft with AI|Redraft|Send|Accept|Decline|Propose a new time|Find a time|Approve|Connect an AI)$/.test(x)
                || /^(Send|Approve)/.test(x));
          }, CUR, key);
          const owed = key === "agent" || await page.evaluate((CUR) => /Reply to|Answering|AI drafted|Not drafted/.test(document.querySelector(`${CUR} [data-tq-slot=close]`)?.innerText || ""), CUR);
          if (owed && !way.length) miss.push(`${task.Title} · ${key}`);
        }
      }
      assert.deepEqual(miss, [], "a pane with no way on");
    });

    assert.deepEqual(errors, []);
  });
}
