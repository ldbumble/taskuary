// The Assistant report card's decisions, tested without a DOM. The panel is JSX; everything it
// DECIDES lives in assistantBlocks.js so it can be checked here.
import { test } from "node:test";
import assert from "node:assert";
import { BLOCKS, blockChoice, blockRowsOf, blocksPatch, costLine, kilo, readsLine, windowPatch } from "../src/assistantBlocks.js";

test("ticking a block writes only that block's override", () => {
  assert.deepEqual(blocksPatch({}, "open_work", { on: true }), { open_work: { on: true } });
});

test("a window change keeps the tick, and the tick keeps the window", () => {
  assert.deepEqual(blocksPatch({ threads: { on: true } }, "threads", { days: 7 }), { threads: { on: true, days: 7 } });
  assert.deepEqual(blocksPatch({ threads: { days: 7 } }, "threads", { on: false }), { threads: { days: 7, on: false } });
});

test("a patch leaves every other block alone", () => {
  const before = { threads: { on: true, days: 7 }, open_work: { on: false } };
  assert.deepEqual(blocksPatch(before, "ooo", { on: true }).threads, { on: true, days: 7 });
});

test("a half-typed window does not snap to zero", () => {
  assert.equal(windowPatch({}, "threads", "days", "").threads.days, "");   // mid-backspace
  assert.equal(windowPatch({}, "threads", "days", "7").threads.days, 7);
  assert.equal(windowPatch({}, "threads", "days", "0").threads.days, 1);   // a 0-day window reads nothing
  assert.equal(windowPatch({}, "threads", "days", "-4").threads.days, 1);
});

test("no blocks key means the declared defaults", () => {
  const rows = blockRowsOf({ type: "assistant" });
  assert.equal(rows.length, BLOCKS.length);
  assert.ok(rows.every((r) => r.on));
  assert.deepEqual(rows.find((r) => r.id === "threads").window, { unit: "days", value: 2 });
  assert.deepEqual(rows.find((r) => r.id === "waiting_on").window, { unit: "hours", value: 24 });
  assert.equal(rows.find((r) => r.id === "ooo").window, null);
});

test("a report with sources of its own and no blocks key reads no Taskuary block", () => {
  // today's behaviour, preserved: a saved monitor must not wake up reading the owner's inbox
  assert.ok(blockRowsOf({ type: "assistant", watch_source_ids: [4] }).every((r) => !r.on));
  assert.ok(blockRowsOf({ type: "assistant", watch_sources: [{ type: "mssql" }] }).every((r) => !r.on));
});

test("a saved choice is the whole truth - a block missing from it is off", () => {
  const rows = blockRowsOf({ type: "assistant", blocks: { open_work: { on: true } } });
  assert.equal(rows.find((r) => r.id === "open_work").on, true);
  assert.equal(rows.find((r) => r.id === "threads").on, false);
});

test("ticking a block on a sourced report reads that block AND its sources", () => {
  const rows = blockRowsOf({ type: "assistant", watch_source_ids: [4], blocks: { gone_quiet: { on: true } } });
  assert.equal(rows.find((r) => r.id === "gone_quiet").on, true);
});

test("a malformed blocks value never turns everything on", () => {
  // failing toward spending the owner's tokens is the wrong way to fail
  for (const bad of ["oops", [], 3, { open_work: true }]) {
    const rows = blockRowsOf({ type: "assistant", blocks: bad });
    assert.ok(rows.every((r) => !r.on), `${JSON.stringify(bad)} turned blocks on`);
  }
});

test("the summary names the blocks and their windows, never a fixed sentence", () => {
  assert.equal(readsLine(blockRowsOf({ type: "assistant", blocks: { threads: { on: true, days: 7 }, open_work: { on: true } } })),
    "Taskuary — What people said (7d), Open work");
  assert.equal(readsLine(blockRowsOf({ type: "assistant", blocks: { waiting_on: { on: true } } })),
    "Taskuary — Waiting on them (24h)");
});

test("nothing ticked reads nothing from Taskuary", () => {
  assert.equal(readsLine(blockRowsOf({ type: "assistant", blocks: {} })), "");
  assert.equal(readsLine([]), "");
});

test("configured systems is not a Taskuary table and is not named as one", () => {
  assert.equal(readsLine([{ id: "system_checks", label: "Configured systems", on: true, window: null }]), "");
});

test("tokens read as a person would say them", () => {
  assert.equal(kilo(12500), "12.5k");
  assert.equal(kilo(340), "340");
  assert.equal(kilo(0), "0");
});

test("the cost line never invents a price, and a weekly report is not quoted per day", () => {
  assert.equal(costLine(12500, 48, null), "~12.5k tokens per run · 48 runs a day");
  assert.equal(costLine(12500, 48, 0.04), "~12.5k tokens per run · 48 runs a day · ~$0.04 a run");
  assert.equal(costLine(900, 1 / 7, null), "~900 tokens per run · 1 runs a week");
  assert.equal(costLine(900, 0, null), "~900 tokens per run · when it is run");
});

test("the first tick does not untick everything else", () => {
  // a saved blocks key is the whole truth, so the first edit must carry the state the owner can SEE
  const rows = [{ id: "threads", on: true, window: { unit: "days", value: 2 } },
                { id: "open_work", on: true, window: null },
                { id: "knowledge", on: false, window: null }];
  const seeded = blockChoice({ type: "assistant" }, rows);
  assert.deepEqual(seeded, { threads: { on: true, days: 2 }, open_work: { on: true }, knowledge: { on: false } });
  const after = blocksPatch(seeded, "open_work", { on: false });
  assert.equal(after.threads.on, true, "ticking one box turned another off");
  assert.equal(after.open_work.on, false);
});

test("once a choice is saved it is edited, not reseeded", () => {
  const cfg = { type: "assistant", blocks: { threads: { on: true, days: 30 } } };
  assert.deepEqual(blockChoice(cfg, [{ id: "threads", on: true, window: { unit: "days", value: 2 } }]),
    { threads: { on: true, days: 30 } });
});

test("a malformed saved choice is reseeded from what the card shows, not trusted", () => {
  for (const bad of ["oops", [], 3]) {
    assert.deepEqual(blockChoice({ blocks: bad }, [{ id: "ooo", on: true, window: null }]), { ooo: { on: true } });
  }
});

// ── the five cards (2026-09-20) ──────────────────────────────────────────────────────────────
import { TASKUARY_CARDS, cardPatch, cardsOf, promptSources, sourceKey } from "../src/assistantBlocks.js";

test("a report saved with cards is read from them, junk and repeats dropped", () => {
  const cards = cardsOf({ type: "assistant", taskuary_sources: [{ card: "work", quiet_days: 5, x: 1 }, { card: "work" }, { card: "nope" }, "junk"] });
  assert.deepEqual(cards, [{ type: "taskuary", card: "work", quiet_days: 5 }]);
  assert.deepEqual(cardsOf({ type: "assistant", taskuary_sources: [] }), []);       // none is a choice
});

test("a report saved before cards existed is shown as the cards its blocks amount to", () => {
  const all = cardsOf({ type: "assistant" });                                          // the seeded Assistant: everything on
  assert.deepEqual(all.map((c) => c.card), TASKUARY_CARDS.map((c) => c.id));
  assert.equal(all[0].days, 2); assert.equal(all[0].hours, 24); assert.equal(all[2].done_days, 7);
  const some = cardsOf({ type: "assistant", blocks: { threads: { on: true, days: 6 }, health: { on: true } } });
  assert.deepEqual(some.map((c) => c.card), ["messages", "systems"]);
  assert.equal(some[0].days, 6);
  assert.deepEqual(cardsOf({ type: "assistant", watch_source_ids: [4] }), []);       // a monitor read no Taskuary block
});

test("a card's number mid-keystroke stays empty rather than snapping to zero", () => {
  const cards = [{ type: "taskuary", card: "messages", days: 2 }];
  assert.equal(cardPatch(cards, "messages", "days", "")[0].days, "");
  assert.equal(cardPatch(cards, "messages", "days", "9")[0].days, 9);
  assert.equal(cardPatch(cards, "messages", "days", "x")[0].days, 2);
});

test("the prompt names a source the way the server spells it", () => {
  assert.equal(sourceKey({ type: "intacct", label: " AP  Bills Due " }, 1), "intacct.ap bills due");
  assert.equal(sourceKey({ type: "mssql" }, 2), "mssql.mssql #2");
  const opts = promptSources({ cards: [{ card: "memory" }], sources: [{ type: "intacct", label: "AP bills due" }] });
  assert.deepEqual(opts.map((o) => o.key), ["taskuary.memory", "intacct.ap bills due"]);
  assert.equal(opts[0].label, "Taskuary · Memory");
});
