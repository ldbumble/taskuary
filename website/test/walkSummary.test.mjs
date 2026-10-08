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
  const rows = [it("approve", "review", { order_band: 2 }), it("working", "agent", { order_band: 5 }), it("report", "report", { order_band: 3 }),
    it("fyi", "fyi", { order_band: 4 }), it("asked", "asked", { order_band: 2, surfaced: true, put_down: true })];
  for (const r of rows) assert.equal(groupOf(r), levelOf(r));
  assert.deepEqual(summarize(rows).groups.map((g) => [g.key, g.n]), bandsOf(rows).map((b) => [b.level, b.items.length]));
});

test("a finished agent's task is On you, as on the rail - not an agent waiting (the owner's screenshot, 2026-10-02)", () => {
  const done = it("report", "agentdone", { agent: "coder", title: "Investigate the export" });
  assert.equal(groupOf(done), "task");
  assert.equal(summarize([done]).groups[0].word, "On you");
});

test("the lead counts each band as the rail does", () => {
  const s = summarize([it("approve", "review", { order_band: 2 }), it("asked", "asked", { order_band: 2, surfaced: true, put_down: true }),
    it("report", "report", { order_band: 3 }), it("fyi", "fyi", { order_band: 4 }), it("fyi", "fyi", { order_band: 4, title: "Other" })]);
  assert.equal(s.lead, "5 things: 1 on you, 1 for later, 1 reports, 2 FYI.");
  assert.equal(summarize([]).lead, "Nothing is waiting on you.");
});

test("a drafted reply says it is ready, everything else says its lane's word", () => {
  assert.equal(stateOf(it("approve", "review"), "ready to close out"), "ready to close out");
  assert.equal(stateOf(it("approve", "action"), "ready to close out"), "wants a yes");
  // a close-out is the same one word as a reply
  assert.equal(stateOf({ ...it("approve", "action"), closeout: "merges the pull request on GitHub" }, "ready to close out"), "ready to close out");
  assert.equal(stateOf(it("asked"), "asked you"), "asked you");
});

test("a report's sender is its own title, so the row says Report instead of saying it twice", () => {
  assert.equal(whoOf({ kind: "report", lane: "report", who: "AP ageing over 30 days", title: "AP ageing over 30 days, weekly - 5 rows" }), "Report");
  assert.equal(whoOf({ kind: "asked", who: "Erin Blake", title: "Q3 numbers" }), "Erin Blake");
  assert.equal(whoOf({ kind: "agent", agent: "coder", title: "Reconcile the August GL export" }), "coder");
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
  assert.equal(whoOf({ kind: "agent", lane: "stopped", who: "You", agent: "coder", title: "Why so many emails" }), "coder");
  assert.equal(whoOf({ kind: "fyi", lane: "fyi", who: "noreply-securityapp@vendor.example", title: "Vendor Create" }), "securityapp");
  assert.equal(whoOf({ kind: "asked", who: "erin@northwind.example", title: "Q3 numbers" }), "erin");
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
  const rows = [{ key: "a", lane: "blocked", kind: "agent", agent: "coder", who: "Alex Doyle", title: "Investigate the missing ledger exports for the north region" },
    { key: "b", lane: "reply", kind: "mail", who: "Erin Blake", title: "Budget question" }];
  const g = gistOf({ rows });
  assert.ok(!/\bcoder\b/.test(g), g);
  assert.match(g, /^Investigate the missing ledger exports…, Erin Blake$/);
});
