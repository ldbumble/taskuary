// WHO CAN MAKE WHICH TIMES (availability.js, viewSpec's `availability`): the counts and the best slot are worked out from the ranges alone,
// the page draws only a spec the catalog allows, and a view shown again under its `id` is one view under the newest line. Invented people.
import assert from "node:assert/strict";
import test from "node:test";
import { dayLabel, minsOf, overlap, rangeLabel, ticksOf, timeLabel } from "../src/availability.js";
import { MARK, normalise } from "../src/viewSpec.js";
import { viewAt, viewHomes } from "../src/chatStream.js";

const TUE = "2026-12-01", WED = "2026-12-02";
const r = (day, from, to) => ({ day, from, to });
const TEAM = [
  { name: "Erin Blake", ranges: [r(TUE, "14:00", "16:00")] },
  { name: "Gail Moreno", ranges: [r(TUE, "15:00", "17:00")] },
  { name: "Ray Colton", ranges: [r(WED, "10:00", "12:00"), r(TUE, "15:00", "16:00")] },
  { name: "Marcus Reed", ranges: [r(TUE, "13:00", "16:00"), r(WED, "09:00", "11:00")] },
  { name: "Paula Vance", ranges: [r(WED, "10:00", "11:00")] },
  { name: "Omar Keller" },
];

test("times read as minutes and say themselves the way a person would", () => {
  assert.equal(minsOf("14:30"), 870); assert.equal(minsOf("9:05"), 545);
  for (const bad of ["2pm", "24:00", "14:60", "", null, 14]) assert.equal(minsOf(bad), null);
  assert.equal(timeLabel(870), "2:30pm"); assert.equal(timeLabel(720), "12pm"); assert.equal(timeLabel(0), "12am");
  assert.equal(rangeLabel(840, 960), "2–4pm"); assert.equal(rangeLabel(660, 780), "11am–1pm"); assert.equal(rangeLabel(540, 630), "9–10:30am");
  assert.equal(dayLabel(TUE), "Tue, Dec 1"); assert.equal(dayLabel("Next Tuesday"), "Next Tuesday");
});

test("the best slot fits the most people, with its count, who fits and who does not", () => {
  const o = overlap(TEAM, 60);
  assert.deepEqual([o.best.day, o.best.from, o.best.to, o.best.n], [TUE, 900, 960, 4]);
  assert.deepEqual(o.best.who, ["Erin Blake", "Gail Moreno", "Ray Colton", "Marcus Reed"]);
  assert.deepEqual(o.best.out, ["Paula Vance"]);          // ...answered, and cannot make it
  assert.deepEqual(o.waiting, ["Omar Keller"]);           // ...no reply is not a no
  assert.equal(o.total, 6);
  assert.deepEqual(o.days.map((d) => d.day), [TUE, WED]);            // dates in order, whatever order they were named in
  assert.deepEqual([o.lo, o.hi], [540, 1020]);                       // one axis for every day, whole hours
});

test("each stretch of a day carries how many are free in it", () => {
  const tue = overlap(TEAM, 60).days[0].segs.map((s) => [s.from, s.to, s.n]);
  assert.deepEqual(tue, [[780, 840, 1], [840, 900, 2], [900, 960, 4], [960, 1020, 1]]);
  assert.deepEqual(overlap(TEAM, 60).days[1].segs.map((s) => s.n), [1, 3, 1]);
});

test("the count climbs as replies come, and the best slot moves with them", () => {
  const upTo = (n) => overlap(TEAM.map((p, i) => (i < n ? p : { name: p.name })), 60);
  assert.equal(upTo(0).best, null);
  assert.deepEqual(upTo(0).waiting.length, 6);
  assert.deepEqual([upTo(1).best.n, upTo(1).best.from, upTo(1).best.to], [1, 840, 960]);
  assert.deepEqual([upTo(2).best.n, upTo(2).best.from, upTo(2).best.to], [2, 900, 960]);
  assert.equal(upTo(3).best.n, 3); assert.equal(upTo(4).best.n, 4);
  assert.deepEqual(upTo(5).best.out, ["Paula Vance"]);
});

test("the meeting's length decides what fits: a slot too short for it is no slot", () => {
  const two = [{ name: "Erin Blake", ranges: [r(TUE, "14:00", "15:00")] }, { name: "Gail Moreno", ranges: [r(TUE, "14:30", "16:00")] }];
  assert.deepEqual([overlap(two, 30).best.n, overlap(two, 30).best.from, overlap(two, 30).best.to], [2, 870, 900]);
  const long = overlap(two, 60).best;                          // ...half an hour together is not an hour: the best is one person's own time
  assert.deepEqual([long.n, long.who, long.from, long.to], [1, ["Gail Moreno"], 870, 960]);
  assert.equal(overlap(two, 120).best, null);
});

test("between equal counts the longer shared stretch wins, then the earlier", () => {
  const p = (name, ...ranges) => ({ name, ranges });
  const longer = overlap([p("Erin Blake", r(TUE, "09:00", "10:00"), r(WED, "13:00", "16:00")), p("Ray Colton", r(TUE, "09:00", "10:00"), r(WED, "13:00", "16:00"))], 60).best;
  assert.deepEqual([longer.day, longer.from, longer.to], [WED, 780, 960]);
  const earlier = overlap([p("Erin Blake", r(WED, "09:00", "10:00"), r(TUE, "13:00", "14:00"))], 60).best;
  assert.equal(earlier.day, TUE);
});

test("a person's ranges that touch or overlap are one stretch; an empty list is someone who can make none", () => {
  const o = overlap([{ name: "Erin Blake", ranges: [r(TUE, "09:00", "10:00"), r(TUE, "10:00", "11:30"), r(TUE, "11:00", "12:00")] }, { name: "Paula Vance", ranges: [] }], 180);
  assert.deepEqual(o.rows[0].days[TUE], [[540, 720]]);
  assert.deepEqual([o.best.n, o.best.from, o.best.to], [1, 540, 720]);
  assert.deepEqual(o.best.out, ["Paula Vance"]); assert.deepEqual(o.waiting, []);
});

test("labels that are no dates stand in the order they were named", () => {
  assert.deepEqual(overlap([{ name: "Erin Blake", ranges: [r("Thu", "09:00", "10:00"), r("Mon", "09:00", "10:00")] }]).days.map((d) => d.day), ["Thu", "Mon"]);
});

test("the hours marked under a day are few enough to read", () => {
  assert.deepEqual(ticksOf(540, 1020, 1), [540, 600, 660, 720, 780, 840, 900, 960, 1020]);
  assert.deepEqual(ticksOf(540, 1020, 2), [600, 720, 840, 960]);
  assert.deepEqual(ticksOf(540, 1020, 3), [540, 720, 900]);
});

// ── the page's guard ──
const view = (props, more = {}) => ({ root: "a", elements: { a: { type: "availability", props } }, ...more });

test("a good availability comes back whole; one with no reply keeps no ranges", () => {
  const v = normalise(view({ title: "Product ideas session", minutes: 60, people: TEAM }, { id: "times" }));
  assert.equal(v.id, "times");
  assert.deepEqual(v.elements.a.props.people[0], TEAM[0]);
  assert.deepEqual(v.elements.a.props.people[5], { name: "Omar Keller" });
  assert.equal(v.elements.a.props.minutes, 60);
});

test("an availability outside the catalog is null, never half drawn", () => {
  const bad = (people, more = {}) => assert.equal(normalise(view({ people, ...more })), null);
  bad([]);                                                                             // nobody
  bad([{ name: "Erin Blake", ranges: [r(TUE, "16:00", "14:00")] }]);                   // ends before it starts
  bad([{ name: "Erin Blake", ranges: [r(TUE, "2pm", "4pm")] }]);                       // not a 24-hour time
  bad([{ name: "Erin Blake", ranges: [{ day: TUE, from: "14:00", to: "16:00", count: 4 }] }]);   // a count is never the agent's to give
  bad([{ name: "Erin Blake", fits: true }]);
  bad([{ name: "Erin Blake" }, { name: "Erin Blake" }]);                               // one entry a person
  bad([{ name: "Erin Blake", ranges: Array.from({ length: 8 }, (_, i) => r(`2026-12-0${i + 1}`, "09:00", "10:00")) }]);   // past a week of days
  bad(Array.from({ length: 13 }, (_, i) => ({ name: `Person ${i}` })));                // past the cap
  bad(TEAM, { minutes: 5 });
  assert.equal(normalise(view({ people: TEAM, best: "Tue 3pm" })), null);              // the best slot is worked out, never taken
});

// ── shown again under its id: one view, at its newest place ──
const show = (id, spec) => ({ k: "tool", id, name: "mcp__taskuary__show", output: `Shown in the owner's chat. ${MARK}${JSON.stringify(spec)}` });
const upTo = (n) => view({ people: TEAM.map((p, i) => (i < n ? p : { name: p.name })) }, { id: "times" });

test("a view shown again under its id is drawn once, at its newest place; no older copy is drawn", () => {
  const turns = [{ id: "t1", steps: [show("c1", upTo(1))] }, { id: "t2", steps: [{ k: "said", text: "Gail replied." }, show("c2", upTo(2))] }, { id: "t3", steps: [show("c3", upTo(4))] }];
  const homes = viewHomes(turns), part = (id, n) => ({ type: "view", id, spec: normalise(upTo(n)) });
  assert.equal(homes.get("times").at, "t3:c3");
  assert.deepEqual(viewAt(homes, "t3", part("c3", 4)), normalise(upTo(4)));           // ...the newest is the view
  assert.equal(viewAt(homes, "t1", part("c1", 1)), null);                             // ...the earlier ones draw nothing
  assert.equal(viewAt(homes, "t2", part("c2", 2)), null);
  // ...and while only the first has been shown it is the newest: nothing is a line before there is something below
  assert.deepEqual(viewAt(viewHomes(turns.slice(0, 1)), "t1", part("c1", 1)), normalise(upTo(1)));
});

test("the rule is every view's: a chart shown again under its id is drawn once, as it now is", () => {
  const chart = (v) => ({ id: "spend", root: "c", elements: { c: { type: "chart", props: { kind: "bar", points: [{ label: "Payworth", value: v }] } } } });
  const turns = [{ id: "t1", steps: [show("c1", chart(200))] }, { id: "t2", steps: [show("c2", chart(540))] }], homes = viewHomes(turns);
  assert.equal(viewAt(homes, "t1", { id: "c1", spec: normalise(chart(200)) }), null);
  assert.equal(viewAt(homes, "t2", { id: "c2", spec: normalise(chart(540)) }).elements.c.props.points[0].value, 540);
});

test("a view with no id, and one he can answer, stand each time they are shown", () => {
  const plain = view({ people: TEAM }), ask = { id: "q1", root: "c", elements: { c: { type: "choice", props: { label: "Which day?", options: ["Tue", "Wed"] } } } };
  const turns = [{ id: "t1", steps: [show("c1", plain), show("c2", ask)] }, { id: "t2", steps: [show("c3", plain), show("c4", ask)] }];
  const homes = viewHomes(turns);
  assert.equal(homes.size, 0);
  assert.deepEqual(viewAt(homes, "t2", { id: "c3", spec: normalise(plain) }), normalise(plain));
  assert.deepEqual(viewAt(homes, "t2", { id: "c4", spec: normalise(ask) }), normalise(ask));
});

test("a refused re-show changes nothing: the view stays where it last passed", () => {
  const turns = [{ id: "t1", steps: [show("c1", upTo(2))] }, { id: "t2", steps: [{ k: "tool", id: "c2", name: "mcp__taskuary__show", output: "elements.a.props.people[0].ranges[0].from must be before its to" }] }];
  assert.deepEqual(viewHomes(turns).get("times"), { at: "t1:c1", spec: normalise(upTo(2)) });
});
