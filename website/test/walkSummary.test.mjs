// The start of the walk IS the rail (the owner, 2026-10-02: "it should just read from the rail no?"): the rail's bands,
// in its order, under its names - so the opener can never put a row in a group the rail does not.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { gistOf, groupOf, refOf, stateOf, summarize, whoOf, GROUPS } from "../src/walkSummary.js";
import { LEVEL_ORDER, SECTION_WORDS, bandsOf, levelOf } from "../src/funnelPile.js";

const it = (lane, kind = "asked", extra = {}) => ({ key: `${lane}:${kind}:${Math.random()}`, lane, kind, who: "Erin Blake", title: "Q3 numbers", ...extra });

test("the groups are the rail's bands, in the rail's order, under the rail's names", () => {
  assert.deepEqual(GROUPS.map((g) => g.key), LEVEL_ORDER);
  for (const g of GROUPS) assert.equal(g.word, SECTION_WORDS[g.key]);
  const rows = [it("approve", "review", { order_band: 2 }), it("working", "agent", { order_band: 2 }), it("report", "report", { order_band: 3 }),
    it("fyi", "fyi", { order_band: 4 }), it("asked", "asked", { order_band: 2, surfaced: true, put_down: true })];
  for (const r of rows) assert.equal(groupOf(r), levelOf(r));
  assert.deepEqual(summarize(rows).groups.map((g) => [g.key, g.n]), bandsOf(rows).map((b) => [b.level, b.items.length]));
});

test("a finished agent's task is under Tasks, as on the rail - not an agent waiting (the owner's screenshot, 2026-10-02)", () => {
  const done = it("report", "agentdone", { agent: "coding", title: "Investigate the export" });
  assert.equal(groupOf(done), "task");
  assert.equal(summarize([done]).groups[0].word, "Tasks");
});

test("the lead counts each band as the rail does", () => {
  const s = summarize([it("approve", "review", { order_band: 2 }), it("asked", "asked", { order_band: 2, deferred: true }),
    it("report", "report", { order_band: 3 }), it("fyi", "fyi", { order_band: 4 }), it("fyi", "fyi", { order_band: 4, title: "Other" })]);
  assert.equal(s.lead, "5 things: 1 tasks, 1 for later, 1 reports, 2 FYI.");
  // a task an agent is working counts under Tasks, and one Next walked past stays there (the owner, 2026-10-21)
  const t = summarize([it("approve", "review", { order_band: 2 }), it("working", "agent", { order_band: 2 }), it("asked", "asked", { order_band: 2, surfaced: true, put_down: true })]);
  assert.equal(t.lead, "3 things: 3 tasks.");
  assert.equal(summarize([]).lead, "Nothing is waiting on you.");
});

// HOW A ROW READS IS THE SERVER'S (funnel_presentation.shows, tests/test_row_presentation.py): the page draws its words
test("a row draws the server's who and state word, never a copy of its own", () => {
  const row = { ...it("approve", "action"), who: "Alex", email: "notifications@github.com", shows: { who: "github", state: "wants a yes", move: "" } };
  assert.equal(whoOf(row), "github");
  assert.equal(stateOf(row, "ready to send"), "wants a yes");
  // ...and the fold and the band's gist read the same words
  const s = summarize([{ ...row, key: "a" }, { ...row, key: "b" }]);
  assert.equal(s.groups[0].rows.length, 1);
  assert.equal(gistOf(s.groups[0]), "github");
  assert.equal(whoOf({ kind: "report", lane: "report", who: "AP ageing", title: "AP ageing - 5 rows", shows: { who: "Report", state: "landed" } }), "Report");
});

test("a card without the server's words falls back to its plain fields", () => {
  assert.equal(whoOf({ kind: "asked", who: "Erin Blake", title: "Q3 numbers" }), "Erin Blake");
  assert.equal(whoOf({ kind: "agent", agent: "coding", title: "Reconcile the August GL export" }), "coding");
  assert.equal(whoOf({}), "someone");
  assert.equal(stateOf(it("asked"), "asked you"), "asked you");
});

test("every group the opener draws has a colour role - a missing one crashed the page (2026-09-24)", () => {
  // ...a tint of its own in the stylesheet now (2026-09-28), one rule per group
  const css = readFileSync(new URL("../src/assistantView.css", import.meta.url), "utf8");
  for (const g of GROUPS) assert.ok(css.includes(`.tq-sum-head span.lvl-${g.key}`), `no pill colour for ${g.key}`);
});

test("a row reads cleanly: its task number, the agent on an agent row, an address's name, one line for a repeat", () => {
  // the owner, 2026-09-30: "let's clean this table up per row - it looks messy and maybe include task numbers?"
  assert.equal(refOf({ tid: 887 }), "TQ-0887");
  assert.equal(refOf({ ref: "TQ-0018", tid: 18 }), "TQ-0018");
  assert.equal(refOf({ title: "no task yet" }), "");
  const twice = { lane: "fyi", kind: "fyi", who: "alerts@vendor.example", title: "Vendor Create - 0 created" };
  const s = summarize([{ ...twice, key: "a" }, { ...twice, key: "b" }, it("fyi", "fyi", { title: "Other" })]);
  const read = s.groups.find((g) => g.key === "fyi").rows;
  assert.deepEqual(read.map((r) => [r.title, r.count || 1]), [["Vendor Create - 0 created", 2], ["Other", 1]]);
  assert.equal(s.n, 3);   // the lead still counts both - folding is how the row reads, not what is waiting
  // two TASKS with one title are two jobs, never folded
  const t = summarize([it("asked", "asked", { tid: 1 }), it("asked", "asked", { tid: 2 })]);
  assert.equal(t.groups[0].rows.length, 2);
});

test("a band's box names an agent's task, never the profile running it", () => {
  const rows = [{ key: "a", lane: "blocked", kind: "agent", agent: "coding", who: "Alex Doyle", title: "Investigate the missing ledger exports for the north region" },
    { key: "b", lane: "reply", kind: "mail", who: "Erin Blake", title: "Budget question" }];
  const g = gistOf({ rows });
  assert.ok(!/\bcoding\b/.test(g), g);
  // ...alone, with the count of the rest: a cut title and a name beside it were both clipped on the opener's row
  assert.match(g, /^Investigate the missing ledger exports… \+1$/);
});

test("a row with no sender but the agent names its task too, never the profile", () => {
  const g = gistOf({ rows: [{ key: "t", lane: "yours", kind: "task", agent: "coding", who: "", title: "Recurring export timeout" }] });
  assert.equal(g, "Recurring export timeout");
});

test("an agent's finished work names the task, whatever field holds the agent", () => {
  // the live shape: kind agentdone, who is the profile, no agent field
  const g = gistOf({ rows: [{ key: "p", kind: "agentdone", lane: "report", who: "coding", agent: null, title: "Recurring export timeout failures" }] });
  assert.equal(g, "Recurring export timeout failures");
});
