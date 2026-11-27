// WHO CAN MAKE WHICH TIMES, WORKED OUT (the owner, 2026-11-26: a thread where a team finds a meeting time - "visual would really help"): the
// agent's view gives only who and the ranges each named (viewspec.json `availability`); how many fit each stretch of time, the best slot and
// who it leaves out are arithmetic done here, the same every draw - never a count a model wrote. Pure: test/availability.test.mjs.
const TIME = /^([01]?\d|2[0-3]):([0-5]\d)$/, ISO = /^(\d{4})-(\d{2})-(\d{2})$/;
// "14:30" -> 870 minutes into its day, or null
export const minsOf = (s) => { const m = TIME.exec(String(s ?? "").trim()); return m ? +m[1] * 60 + +m[2] : null; };
// 870 -> "2:30pm"; a range says its half of the day once where both ends share it: "2–4pm", "11am–1pm"
const clock = (m, half = true) => { const h = Math.floor(m / 60) % 24, mm = m % 60; return `${h % 12 || 12}${mm ? `:${String(mm).padStart(2, "0")}` : ""}${half ? (h < 12 ? "am" : "pm") : ""}`; };
export const timeLabel = (m) => clock(m);
export const rangeLabel = (a, b) => `${clock(a, (a < 720) !== (b < 720))}–${clock(b)}`;
// a day as its column is headed: an ISO date by its weekday ("Tue, Dec 1"), any other label as written
export const dayLabel = (d) => { const m = ISO.exec(d); if (!m) return d;
  return new Date(+m[1], +m[2] - 1, +m[3]).toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" }); };

// one person's ranges as minutes, a day at a time, sorted, those that touch or overlap made one: {day: [[from, to]]}
function byDay(ranges) {
  const out = {};
  for (const r of ranges || []) { const a = minsOf(r.from), b = minsOf(r.to); if (a != null && b != null && a < b) (out[r.day] ||= []).push([a, b]); }
  for (const d of Object.keys(out)) out[d] = out[d].sort((x, y) => x[0] - y[0]).reduce((xs, r) => {
    const last = xs.at(-1); if (last && r[0] <= last[1]) last[1] = Math.max(last[1], r[1]); else xs.push([...r]); return xs; }, []);
  return out;
}

// `people`: [{name, ranges?: [{day, from, to}]}] - no `ranges` is no reply yet, an empty list none of the times. `minutes`: how long the meeting is.
// -> {days: [{day, label, segs: [{from, to, n, who}]}], lo, hi (the axis every day shares, whole hours), total, waiting: [names with no reply],
//     rows: [{name, replied, days: {day: [[from, to]]}}], best: {day, label, from, to, n, who, out} | null}
// A day's `segs` are its stretches where the same people are free, each with its count. THE BEST SLOT fits the most people for `minutes`
// together; between equals the longer shared stretch, then the earlier. `out`: who answered and cannot make it.
export function overlap(people, minutes = 30) {
  const rows = (people || []).map((p) => ({ name: p.name, replied: Array.isArray(p.ranges), days: byDay(p.ranges) }));
  let days = [...new Set(rows.flatMap((r) => Object.keys(r.days)))];
  if (days.every((d) => ISO.test(d))) days.sort();
  const all = rows.flatMap((r) => Object.values(r.days).flat());
  const lo = all.length ? Math.floor(Math.min(...all.map((x) => x[0])) / 60) * 60 : 540, hi = all.length ? Math.ceil(Math.max(...all.map((x) => x[1])) / 60) * 60 : 1020;
  const free = (r, d, a, b) => (r.days[d] || []).find((x) => x[0] <= a && x[1] >= b);
  let best = null;
  const better = (c) => !best || c.n > best.n || (c.n === best.n && c.to - c.from > best.to - best.from);      // ...days and starts come in order: the earlier stands
  days = days.map((day) => {
    const cuts = [...new Set(rows.flatMap((r) => (r.days[day] || []).flat()))].sort((a, b) => a - b), segs = [];
    for (let i = 0; i + 1 < cuts.length; i++) {
      const who = rows.filter((r) => free(r, day, cuts[i], cuts[i + 1])).map((r) => r.name), last = segs.at(-1);
      if (!who.length) continue;
      if (last && last.to === cuts[i] && last.who.join("\n") === who.join("\n")) last.to = cuts[i + 1];
      else segs.push({ from: cuts[i], to: cuts[i + 1], n: who.length, who });
    }
    for (const a of cuts) {
      const fit = rows.map((r) => [r, free(r, day, a, a + minutes)]).filter((x) => x[1]);
      const c = { day, label: dayLabel(day), from: a, to: Math.min(...fit.map((x) => x[1][1])), n: fit.length, who: fit.map((x) => x[0].name) };
      if (fit.length && better(c)) best = c;
    }
    return { day, label: dayLabel(day), segs };
  });
  if (best) best.out = rows.filter((r) => r.replied && !best.who.includes(r.name)).map((r) => r.name);
  return { days, lo, hi, total: rows.length, waiting: rows.filter((r) => !r.replied).map((r) => r.name), rows, best };
}

// where the hours are marked on a day's axis: every 1, 2, 3 or 4 hours, few enough to read under a day `n` abreast
export function ticksOf(lo, hi, n = 1) {
  const h = (hi - lo) / 60, step = [1, 2, 3, 4, 6].find((s) => h / s <= (n > 2 ? 3 : n > 1 ? 4 : 8)) || 6, out = [];
  for (let m = Math.ceil(lo / 60 / step) * step * 60; m <= hi; m += step * 60) out.push(m);
  return out;
}

// AN INVITE SET UP FROM WHO CAN MAKE WHICH TIMES DRAWS THAT GRID (taskuary/calwrite.py from_people; the design audit, 2026-11-27): the
// availability view itself over the people and ranges the agent gave - its best slot, banded, is the one the invite holds (calwrite.best_slot)
export const gridView = (grid) => (Array.isArray(grid?.people) && grid.people.length
  ? { root: "a", elements: { a: { type: "availability", props: { people: grid.people, minutes: grid.minutes || 30 } } } } : null);
