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
