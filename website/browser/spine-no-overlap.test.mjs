import assert from "node:assert/strict";
import test from "node:test";

import { startHarness } from "./harness.mjs";

/* A SPINE'S WORDS NEVER RUN UNDER ITS MOVES (the owner, 2026-11-02): a WhatsApp group task of ~87 messages, Came from the slim column
   beside an open section - its "<sender>: "<words>..." lines ran down the whole spine and Remind me / Watch it / Not a task / Change were
   drawn on top of them. Each drawn line's box stays clear of every move's box, at a desk and at a laptop size, whichever section is open -
   and after an agent's session ends, when the slim 44px tabs a live agent leaves turn back into spines (TaskPage SectionTab: the fit was
   measured only on mount, and a tab first drawn slim never measured its lines at all). Invented people only. */
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const clash = (page, CUR, key) => page.evaluate((CUR, key) => {
  const tab = document.querySelector(`${CUR} [data-tq-section-tab=${key}]:not([data-tq-mini])`);
  if (!tab) return null;
  const box = (e) => e.getBoundingClientRect(), hit = (a, b) => a.left < b.right && b.left < a.right && a.top < b.bottom && b.top < a.bottom;
  const shown = (e) => getComputedStyle(e).display !== "none" && box(e).height > 0;
  const lines = [...tab.querySelectorAll("[data-tq-tab-line]")].filter(shown), btns = [...tab.querySelectorAll("button")].filter(shown);
  const tb = box(tab), out = btns.filter((b) => box(b).bottom > tb.bottom + 0.5).map((b) => b.textContent.trim());
  return { lines: lines.length, btns: btns.map((b) => b.textContent.trim()), out,
    hits: lines.flatMap((l) => btns.filter((b) => hit(box(l), box(b))).map((b) => `${l.textContent.slice(0, 40)} x ${b.textContent.trim()}`)) };
}, CUR, key);
const clear = (m, where) => {
  assert.ok(m, `Came from is a spine ${where}`);
  assert.ok(m.lines >= 1, `some of the chat is shown ${where}: ${JSON.stringify(m)}`);
  assert.ok(m.btns.includes("Remind me"), `its moves are there ${where}: ${m.btns}`);
  assert.deepEqual(m.hits, [], `${where}, a line under a move: ${JSON.stringify(m)}`);
  assert.deepEqual(m.out, [], `${where}, a move past the spine's foot: ${JSON.stringify(m)}`);
};

for (const [w, h] of [[1440, 900], [1280, 800]]) {
  test(`a many-message Came from spine keeps its lines off its moves at ${w}x${h}`, { timeout: 240000 }, async (t) => {
    const hz = await startHarness();
    t.after(() => hz.close());
    const page = await hz.newPage(), errors = [];
    page.on("pageerror", (e) => errors.push(e.message));
    const post = async (p, b) => (await fetch(`${hz.fixtureApi}${p}`, { method: "POST", headers: { "Content-Type": "application/json", "X-Taskuary-Token": hz.token },
      body: JSON.stringify(b) })).json();
    const open = async (id) => {
      const CUR = `[data-tq-canvas-item]:has([data-tq-task-page="${id}"])`;
      await page.evaluate((id) => { location.hash = ""; location.hash = `task=${id}`; }, id);
      await page.waitForSelector(`${CUR} [data-tq-task-body][data-tq-sections]`, { timeout: 20000 });
      await sleep(1500);
      return CUR;
    };
    await page.setViewport({ width: w, height: h, deviceScaleFactor: 1 });
    await page.goto(hz.ui, { waitUntil: "domcontentloaded" });
    await page.waitForSelector("[data-tq-rail] .tq-pile-row", { timeout: 30000 });

    await t.test("beside an open Close out or Agent", async () => {
      const CUR = await open((await post("/api/fixture/task/group-chat", {})).taskId);
      for (const sec of ["close", "agent"]) {
        await page.click(`${CUR} [data-tq-section-tab=${sec}] [data-tq-tab-arrow]`);
        await page.waitForSelector(`${CUR} [data-tq-section-tab=from] [data-tq-spine-moves] button`, { timeout: 10000 });
        await sleep(900);
        clear(await clash(page, CUR, "from"), `beside ${sec}`);
        // ...and Mark done the first of Close out's moves, open on its strip or folded on its spine (the owner, 2026-11-02)
        const sel = sec === "close" ? `${CUR} [data-tq-pane-moves=close] button` : `${CUR} [data-tq-section-tab=close] [data-tq-spine-moves] button`;
        const words = await page.$$eval(sel, (bs) => bs.map((b) => b.textContent.trim()));
        assert.equal(words[0], "Mark done", `Close out's moves beside ${sec}: ${words}`);
      }
    });

    await t.test("after a live agent's session ends and its slim tabs are spines again", async () => {
      const made = await post("/api/fixture/task/group-chat", { live: true }), CUR = await open(made.taskId);
      await page.waitForSelector(`${CUR} [data-tq-section-tab=from][data-tq-mini]`, { timeout: 15000 });
      assert.ok((await post("/api/fixture/task/coding-live/end", { taskId: made.taskId })).ended);
      await page.waitForSelector(`${CUR} [data-tq-section-tab=from]:not([data-tq-mini]) [data-tq-spine-moves] button`, { timeout: 20000 });
      await sleep(900);
      clear(await clash(page, CUR, "from"), "after the session ended");
    });
    assert.deepEqual(errors, []);
  });
}
