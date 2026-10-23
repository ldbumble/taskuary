// A DASHBOARD'S ROWS, SLICED (src/dashboard/slice.js): the range and the segment re-slice every component from the same rows, a
// colour follows its entity whatever the filter, the tail folds into Other, and every link to the dashboards' shelf lands.
import test from "node:test";
import assert from "node:assert/strict";
import { OTHER, aggregate, componentRows, daysAgo, delta, fmt, groupBy, inRange, inSegment, itemLink, segmentValues, seriesSlots,
  snapshotOf, sortRows, spanOf4, stacked, timeSeries } from "../src/dashboard/slice.js";
import { canvasRequestFromHash, hashFor } from "../src/canvasLinks.js";
import { DRAFT_HASH } from "../src/draftHandoff.js";
import { DASH, placeHref } from "../src/words.js";

const NOW = new Date("2026-10-23T10:00:00");
const d = (n) => daysAgo(n, NOW);
const ROWS = [
  { day: d(0), channel: "email", kind: "reply", n: 2, task_id: 4 }, { day: d(1), channel: "email", kind: "general", n: 3 },
  { day: d(1), channel: "teams", kind: "general", n: 5 }, { day: d(6), channel: "github", kind: "coding", n: 1 },
  { day: d(9), channel: "email", kind: "reply", n: 7 }, { day: d(40), channel: "whatsapp", kind: "reply", n: 4 },
];

test("the last 7 days are today and the six before it, and an undated source is never cut", () => {
  assert.equal(inRange(ROWS, "day", 7, NOW).length, 4);
  assert.equal(inRange(ROWS, "day", 30, NOW).length, 5);
  assert.equal(inRange(ROWS, "day", 0, NOW).length, 6);
  assert.equal(inRange(ROWS, null, 7, NOW).length, 6);
});

test("the segment cuts only rows that carry its column - a source without it is not emptied", () => {
  assert.equal(inSegment(ROWS, "channel", "email").length, 3);
  assert.equal(inSegment([{ x: 1 }], "channel", "email").length, 1);
  assert.equal(inSegment(ROWS, "channel", "").length, 6);
  assert.deepEqual(segmentValues({ sources: { a: { rows: ROWS }, b: { rows: [{ channel: "slack" }] } } }, "channel"),
    ["email", "github", "slack", "teams", "whatsapp"]);
});

test("one cut for every component: range, then segment, then its own where", () => {
  const spec = { sources: [{ key: "m", date: "day" }] }, data = { sources: { m: { rows: ROWS } } };
  const c = { source: "m", where: { kind: "general" } };
  assert.equal(componentRows(spec, data, c, { days: 7, now: NOW }).length, 2);
  assert.equal(componentRows(spec, data, c, { days: 7, segment: "channel", value: "teams", now: NOW }).length, 1);
});

test("the aggregates, and a value nobody can read is no value", () => {
  assert.equal(aggregate(ROWS), 6);
  assert.equal(aggregate(ROWS, "sum", "n"), 22);
  assert.equal(aggregate(ROWS, "max", "n"), 7);
  assert.equal(aggregate([{ n: "x" }], "avg", "n"), null);
});

test("ranked bars fold their tail into Other, never a ninth bar", () => {
  const rows = "abcdefghij".split("").flatMap((k, i) => Array.from({ length: 10 - i }, () => ({ k })));
  const g = groupBy(rows, "k", "count", null, { limit: 4 });
  assert.equal(g.length, 4);
  assert.deepEqual(g.slice(0, 3).map((x) => x.key), ["a", "b", "c"]);
  assert.equal(g[3].key, OTHER);
  assert.equal(g[3].value, rows.length - 10 - 9 - 8);
});

test("a day with nothing is a zero for a count, and a gap for an average", () => {
  const c = timeSeries(ROWS, "day", "count", null, { days: 7, now: NOW });
  assert.equal(c.length, 7);
  assert.equal(c[c.length - 1].value, 1);
  assert.equal(c[3].value, 0);
  const a = timeSeries(ROWS, "day", "avg", "n", { days: 7, now: NOW });
  assert.equal(a[3].value, null);
});

test("COLOUR FOLLOWS THE ENTITY: a filter that drops a series never repaints the ones left", () => {
  const slots = seriesSlots(ROWS, "channel");
  const all = stacked(ROWS, "day", "channel", "count", null, { slots, days: 30, now: NOW });
  const teamsOnly = stacked(inSegment(ROWS, "channel", "teams"), "day", "channel", "count", null, { slots, days: 30, now: NOW });
  assert.equal(slots.email, 0);
  assert.deepEqual(teamsOnly.series, ["teams"]);
  assert.equal(slots.teams, seriesSlots(ROWS, "channel").teams);
  assert.ok(all.series.indexOf("email") < all.series.indexOf("teams"));
  assert.equal(all.cells[d(1)].teams.value, 1);
  assert.equal(all.keys.length, 30);
});

test("past six series the rest is Other", () => {
  const rows = "abcdefgh".split("").map((s) => ({ x: "one", s }));
  const slots = seriesSlots(rows, "s");
  assert.equal(Object.keys(slots).length, 5);
  assert.ok(stacked(rows, "x", "s", "count", null, { slots }).series.includes(OTHER));
});

test("a tile's delta is this range against the same length before it", () => {
  const got = delta(ROWS, "day", 7, "count", null, NOW);
  assert.deepEqual([got.now, got.prev, got.change], [4, 1, 3]);
  assert.equal(delta(ROWS, null, 7, "count", null, NOW), null);
  assert.equal(delta(ROWS, "day", 0, "count", null, NOW), null);
});

test("numbers compact from ten thousand, rows sort either way, an item row opens its item", () => {
  assert.equal(fmt(12900), "12.9K");
  assert.equal(fmt(4200000), "4.2M");
  assert.equal(fmt(1284), "1,284");
  assert.equal(fmt(null), "–");
  assert.deepEqual(sortRows(ROWS, "-n").map((r) => r.n).slice(0, 2), [7, 5]);
  assert.equal(itemLink({ task_id: 4 }), "task=4");
  assert.equal(itemLink({ message_id: 9 }), "msg=9");
  assert.equal(itemLink({ x: 1 }), null);
});

test("the grid: a tile is a quarter, a chart half, a table the row", () => {
  assert.deepEqual([{ kind: "stat" }, { kind: "bar" }, { kind: "table" }, { kind: "bar", w: 9 }].map(spanOf4), [1, 2, 4, 4]);
});

test("every way to the dashboards' shelf lands on it, and reads back to the same address", () => {
  for (const h of ["#report=dashboards", "#report=new-dashboard", "#report=draft-dashboard", placeHref("dashboards"), `#${DRAFT_HASH.dashboard}`]) {
    const r = canvasRequestFromHash(h);
    assert.equal(r.state.section, "dashboards", h);
    assert.equal(canvasRequestFromHash(hashFor("reports", r.state)).state.section, "dashboards", h);
  }
  assert.ok(DASH.new.startsWith("+ New"));
});

test("a shared dashboard carries its tiles as lines and the rows it drew - several sources each marked by its label", () => {
  const spec = { filters: { range: 7 }, sources: [{ key: "t", date: "created" }, { key: "m" }],
    components: [{ kind: "stat", title: "Open tasks", source: "t" }, { kind: "bar", title: "By kind", source: "t", x: "kind" }] };
  const data = { sources: { t: { label: "Tasks", rows: [{ kind: "task", created: d(1) }, { kind: "task", created: d(20) }] },
    m: { label: "Mail", rows: [{ channel: "email" }] }, x: { label: "Empty", rows: [] } } };
  const snap = snapshotOf(spec, data, NOW);
  assert.equal(snap.text, "Open tasks: 1", "the tile over the spec's own range, not a filter the page had set");
  assert.deepEqual(snap.data.map((r) => r.source), ["Tasks", "Tasks", "Mail"]);
  assert.deepEqual(snapshotOf({ components: [] }, { sources: { t: { rows: [{ a: 1 }] } } }, NOW), { text: "", data: [{ a: 1 }] }, "one source: its rows as they are");
});
