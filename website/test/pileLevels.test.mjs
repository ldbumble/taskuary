import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";
import assert from "node:assert/strict";
import { LEVEL_META, LEVEL_ORDER, levelLabel, levelOf, levelsOf } from "../src/funnelPile.js";

// Unread is ranked, not chronological, so the heading names the LEVEL the rail is crossing.
// One level per thing triage decided: open work and landed results are not merged into a single name (the owner,
// 2026-09-07: "why work and reports combined ... just make each one it's own thing").
test("every level has its own word and its own hint", () => {
  // the canvas redesign (2026-09-29): On you, Agents working, For later, Reports, Advisor ideas, FYI
  assert.deepEqual(LEVEL_ORDER, ["urgent", "task", "agents", "later", "reports", "ideas", "fyi"]);
  for (const level of LEVEL_ORDER) {
    assert.ok(levelLabel(level).length, `${level} needs a word`);
    assert.ok(LEVEL_META[level].hint.length, `${level} needs a hint`);
  }
  assert.equal(new Set(LEVEL_ORDER.map(levelLabel)).size, LEVEL_ORDER.length, "no two levels share a word");
  assert.equal(levelLabel(""), "");
  assert.equal(levelLabel("nonsense"), "");
});

test("no level name merges two things", () => {
  for (const level of LEVEL_ORDER) assert.ok(!/[&+]|and/.test(levelLabel(level)), `${levelLabel(level)} names two things`);
  assert.equal(levelLabel("task"), "on you");
  assert.equal(levelLabel("later"), "for later");
  assert.equal(levelLabel("ideas"), "advisor ideas");
  assert.equal(levelLabel("reports"), "reports");
});

// One level for the owner's work, whoever is waiting on it - triage never split those - and a
// landed result is not work at all (the owner, 2026-09-07).
test("everything triage called work is one level, and a result is not in it", () => {
  for (const lane of ["asked", "queued", "broken", "approve", "blocked"]) {
    assert.equal(levelOf({ lane, order_band: 2 }), "task", lane);
  }
  assert.equal(levelOf({ lane: "report", order_band: 3 }), "reports");
  assert.equal(levelOf({ lane: "forgotten", order_band: 4 }), "fyi", "an idea nobody judged is an fyi");
  assert.ok(LEVEL_ORDER.indexOf("reports") > LEVEL_ORDER.indexOf("task"));
  assert.ok(LEVEL_ORDER.indexOf("fyi") > LEVEL_ORDER.indexOf("reports"));
});

test("the ends of the list are one level each", () => {
  assert.equal(levelOf({ lane: "time", order_band: 1 }), "urgent");
  assert.equal(levelOf({ lane: "fyi", order_band: 4 }), "fyi");
  assert.equal(levelOf({ lane: "working", order_band: 5 }), "agents");
  assert.equal(levelOf({}), "task", "a row with no band still lands in one, so the dock never reads empty");
  // work you pressed Next on waits at the bottom, beside the agents - still yours, not at the top
  assert.equal(levelOf({ lane: "stopped", order_band: 2, surfaced: true, put_down: true }), "later");
  // shown and clicked away from is not put aside (2026-10-08: "it moved 1003 automatically to later?")
  assert.equal(levelOf({ lane: "stopped", order_band: 2, surfaced: true }), "task");
  assert.equal(levelOf({ lane: "stopped", order_band: 2 }), "task");
  assert.equal(levelOf({ lane: "time", order_band: 1, surfaced: true }), "urgent", "a meeting about to start never moves down");
});

test("the menu offers only the runs the pile holds, in the order the rail draws them", () => {
  const pile = [
    { lane: "fyi", order_band: 4 },
    { lane: "report", order_band: 3 },
    { lane: "approve", order_band: 2 },
    { lane: "asked", order_band: 2 },
  ];
  assert.deepEqual(levelsOf(pile), ["task", "reports", "fyi"]);
  assert.deepEqual(levelsOf([]), []);
  assert.deepEqual(levelsOf(null), []);
});

test("the card on the table keeps its band - it is passed only once Next moves you on", () => {
  const view = readFileSync(fileURLToPath(new URL("../src/AssistantView.jsx", import.meta.url)), "utf8");
  assert.match(view, /bandsOf\(drawn\.map\(\(i\) => \(i\.surfaced && atTable\(i\) \? \{ \.\.\.i, surfaced: false \} : i\)\)\)/);
});

// the owner, 2026-09-28: "the work rail still read agents working for a split second into your task, then goes back"
test("the card on the table never moves its row: the rail's lane and shown mark win", async () => {
  const { placed, levelOf } = await import("../src/funnelPile.js");
  const row = { key: "a", lane: "working", order_band: 5, kind: "agent", title: "Fix the export" };
  const stale = { key: "a", lane: "blocked", order_band: 2, surfaced: true, kind: "agent", why: "asked you" };
  const drawn = placed(row, stale);
  assert.equal(drawn.lane, "working");
  assert.equal(drawn.surfaced, undefined);
  assert.equal(drawn.why, "asked you", "the card still lends its words");
  assert.notEqual(levelOf(drawn), levelOf(stale));
});

test("an older rail answer never replaces a newer one", async () => {
  const { refreshPilePresentation } = await import("../src/funnelPile.js");
  const newer = { generated_at: 2000, items: [{ key: "a", lane: "working" }] };
  const older = { generated_at: 1000, items: [{ key: "a", lane: "blocked" }] };
  assert.equal(refreshPilePresentation(newer, older), newer);
  const newest = { generated_at: 3000, items: [] };
  assert.equal(refreshPilePresentation(newer, newest), newest);
});

// FOR LATER holds what Next walked past AND what Remind me put away; ADVISOR IDEAS leaves FYI while it is still an idea
test("for later and advisor ideas are their own levels", () => {
  assert.equal(levelOf({ lane: "yours", order_band: 2, deferred: true, defer_until: "2099-01-01 08:00" }), "later");
  assert.equal(levelOf({ lane: "forgotten", kind: "idea", order_band: 4 }), "ideas");
  assert.equal(levelOf({ lane: "yours", kind: "idea", order_band: 2, tid: 7 }), "task", "an idea made a task is a task");
  assert.equal(levelOf({ lane: "working", kind: "idea", order_band: 5, tid: 7 }), "agents");
});

test("For later's gutter says how long until it comes back, soonest first", async () => {
  const { railBack, backAt, bandsOf } = await import("../src/funnelPile.js");
  const now = Date.parse("2026-09-29T12:00:00");
  const at = (m) => new Date(now + m * 60000).toISOString();
  assert.equal(railBack(at(10), now), "in 30m");
  assert.equal(railBack(at(45), now), "in 1h");
  assert.equal(railBack(at(185), now), "in 3h");
  assert.equal(railBack(at(60 * 50), now), "in 2d");
  assert.equal(railBack(at(-5), now), "", "a return time already past is no age at all");
  assert.equal(railBack(null, now), "");
  assert.equal(backAt({ back_at: "2026-09-29 15:00:00" }), "2026-09-29 15:00:00");
  assert.equal(backAt({ defer_until: "2026-10-02 08:00" }), "2026-10-02 08:00");
  assert.equal(backAt({}), null);
  const rows = [
    { key: "b", lane: "yours", order_band: 2, surfaced: true, put_down: true, back_at: at(300) },
    { key: "a", lane: "yours", order_band: 2, deferred: true, defer_until: at(60) },
    { key: "c", lane: "yours", order_band: 2, surfaced: true, put_down: true },
  ];
  assert.deepEqual(bandsOf(rows).find((b) => b.level === "later").items.map((i) => i.key), ["a", "b", "c"]);
});

test("reports, ideas and fyi divide what is left; the rest are never capped", async () => {
  const { CAPPED } = await import("../src/funnelPile.js");
  assert.deepEqual(CAPPED, ["reports", "ideas", "fyi"]);
});

// ONE RULE, TWO COPIES: the server's funnel.level_of reads the same fixture (tests/test_canvas_sections.py)
test("the page puts every fixture row where the server does", () => {
  const rows = JSON.parse(readFileSync(fileURLToPath(new URL("../../tests/fixtures/rail_levels.json", import.meta.url)), "utf8"));
  for (const [item, level] of rows) assert.equal(levelOf(item), level, JSON.stringify(item));
});
