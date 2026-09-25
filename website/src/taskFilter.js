// Keep the master list and detail pane telling the same story. A task can finish while its
// detail is open; leaving the selected pill on "in progress" makes the accurate Done header
// look like a second, conflicting status. Search views remain untouched.
// `stateKey` is the task's BUCKET: "upcoming" while a Remind me date holds it, its state otherwise. The pills
// are in progress / upcoming / done (the owner, 2026-09-25) - one each. A dropped task has no pill, so the
// rail stays where it is rather than guess.
export const filterForSelectedState = (filter, stateKey) => {
  if (stateKey === "dropped") return filter;
  const to = stateKey === "done" ? "done" : stateKey === "upcoming" ? "upcoming" : "live";
  return filter === to ? filter : to;
};

// REMIND ME (2026-09-25): an open task put away until a day is Upcoming until that morning. The server writes
// the day as local 'YYYY-MM-DD 07:00:00', so the comparison is against local time in the same shape.
const pad = (n) => String(n).padStart(2, "0");
export const localStamp = (d = new Date()) =>
  `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
export const remindWaiting = (t, now = localStamp()) =>
  !!t?.RemindAt && !["done", "dropped"].includes(t.Status) && String(t.RemindAt) > now;
export const remindDay = (at) => {
  const [y, m, d] = String(at || "").slice(0, 10).split("-").map(Number);
  return y ? new Date(y, m - 1, d).toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short" }) : "";
};

// Closing the detail on the right advances through the work list on the left. Keep this tiny and
// deterministic so a task-changed event cannot make the selection depend on whichever render won
// the race: prefer the following row, then the preceding row, and never return the closed row.
export const nextTaskId = (ids, current) => {
  const order = (ids || []).filter((id) => id != null);
  const at = order.indexOf(current);
  if (at < 0) return order[0] ?? null;
  return order[at + 1] ?? order[at - 1] ?? null;
};

export const completionTransition = (liveIds, current, status = "done") => ({
  next: nextTaskId(liveIds, current),
  filter: "live",
  seen: { id: current, key: status },
});

// THE CUT BELONGS TO THE ROW, not to the pill you are standing on. Live work has no age - it is
// live whether it arrived this morning or last night - so cutting per pill gave `in progress` a
// wider window than `all`, and "all 5" sat over "in progress 4 · done 2" with two live rows from
// last night counted by one and not the other (the owner, 2026-09-22: "that doesn't add up?").
// History does have an age, and that is what "show older" is for.
export const cutAway = (stateKey, touchedToday, older) =>
  !older && ["done", "dropped"].includes(stateKey) && !touchedToday;
