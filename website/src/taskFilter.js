// Keep the master list and detail pane telling the same story. A task can finish while its
// detail is open; leaving the selected pill on "in progress" makes the accurate Done header
// look like a second, conflicting status. Explicit "all" and search views remain untouched.
export const filterForSelectedState = (filter, stateKey) => {
  if (filter === "live" && ["done", "dropped"].includes(stateKey)) {
    return stateKey === "done" ? "done" : "";
  }
  if (filter === "done" && stateKey !== "done") {
    return ["done", "dropped"].includes(stateKey) ? "" : "live";
  }
  return filter;
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
