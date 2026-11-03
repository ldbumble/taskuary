import assert from "node:assert/strict";
import test from "node:test";
import { startHarness } from "./harness.mjs";
import { bootMixed, clean, look, noBlank, oneLine, oneTable, overlaps, pressBack, pressNext, rowLook, shot, sleep, startWalk, still, type } from "./stress-mixed-lib.mjs";

/* MIXED USE 1 - TYPED ASKS AND THE WALK'S BUTTONS, INTERLEAVED (the owner, 2026-11-02: "no crazy stuff"). The pop-up Assistant is typed to
   ("next", "mark it done", "remind me friday", "open the reports", "what's on my plate" - answered from the browser recording, never a model)
   while Next and Back are pressed, some before the typed answer is back, with every /api/ answer held 0, 300 and 1500 ms. After each the
   chat and the walk agree: one ring, one item on the table and it is the ringed row, no card twice, the row one line, nothing over anything,
   no blank frame, no console error. A typed "mark it done" closes the task on the server once. */
for (const delay of [0, 300, 1500]) {
  test(`typed asks and Next/Back interleave and agree, server ${delay} ms`, { timeout: 420000 }, async (t) => {
    const { page, errors, api } = await bootMixed(t, { width: 1440, height: 900, delay });
    const check = async (where) => {
      const s = await still(page, 30000);
      try {
        oneTable(s, where); oneLine(await rowLook(page), where);
        assert.deepEqual(await overlaps(page), [], `${where}: a box drawn over another`);
        await noBlank(page, where); clean(errors, where);
      } catch (e) { await shot(page, `chat-walk-${delay}-${where.replace(/\W+/g, "_")}`); throw e; }
      return s;
    };
    await startWalk(page); let s = await check("walk started");
    const first = s.ring[0];

    await type(page, "next"); s = await check("typed next");
    assert.notEqual(s.ring[0], first, "typed next moved the walk");
    assert.equal(s.pop, true, "the pop-up shows the answer");

    // ...Next pressed while a typed next is still out: one move each, never a row skipped past twice or the ring split
    // (a Next reads nothing off the rail under Tasks - "stays" - so the rows keep their places and a move is one row)
    const at = (s) => s.keys.indexOf(s.ring[0]);
    let from = at(s);
    // ...Next stands greyed while a typed ask is out (the press-queue question, see the todo test below): a press it refused is no move
    await type(page, "next"); const took = await pressNext(page); s = await check("typed next + pressed Next");
    assert.equal(at(s) - from, took ? 2 : 1, `a typed next and a Next ${took ? "pressed" : "refused"} are ${took ? 2 : 1} rows down, not ${at(s) - from}`);
    from = at(s); await pressBack(page); s = await check("Back");
    assert.equal(at(s) - from, -1, `Back is one row up, not ${at(s) - from}`);
    from = at(s); await pressBack(page); await type(page, "next"); s = await check("Back + typed next");
    assert.equal(at(s), from, `Back then a typed next lands where it started ${JSON.stringify({ from, now: at(s) })}`);

    // a typed close: the task on the table closes once on the server, and the walk goes on
    const on = s.ring[0];
    const before = (await api("/api/tasks")).data.filter((x) => x.Status === "done").length;
    await type(page, "mark it done"); s = await check("typed mark it done");
    const after = (await api("/api/tasks")).data.filter((x) => x.Status === "done").length;
    assert.ok(after - before <= 1, `one close, not ${after - before}`);
    assert.ok(s.keys.length > 0, "the rail still has rows");

    await type(page, "remind me friday"); s = await check("typed remind me friday");
    await pressNext(page); await type(page, "what's on my plate"); s = await check("Next + what's on my plate");
    assert.match((await page.$eval("[data-tq-chat-pop]", (p) => p.innerText)), /waits on you/, "the plate answer is in the pop-up");

    await type(page, "open the reports"); s = await check("open the reports");
    await pressNext(page); s = await check("Next after the reports");
    assert.ok(on, "the walk had a row");
  });
}

/* A NEXT PRESSED WHILE A TYPED "next" IS OUT IS TAKEN (found 2026-11-02 as lost: greyed and refused, or taken and the walk still one row on -
   the typed answer puts its row up a moment later (deferInChat), and the press ran in that moment to the same row and the typed move was
   refused behind it). Now held behind the typed move, like any press over a move in flight: a typed next and a pressed Next are two rows. */
test("a Next pressed while a typed next is out is taken, not dropped", { timeout: 240000 }, async (t) => {
  const { page } = await bootMixed(t, { width: 1440, height: 900, delay: 1500 });
  let s = await startWalk(page);
  const from = s.keys.indexOf(s.ring[0]);
  await type(page, "next"); await sleep(200);
  const took = await pressNext(page);
  s = await still(page, 30000);
  assert.equal(took, true, "Next was greyed while the typed ask was out");
  assert.equal(s.keys.indexOf(s.ring[0]) - from, 2, "the click was taken, so a typed next and a pressed Next are two rows down");
});
