// A CLOSED TASK OPENED FROM SEARCH OPENS REOPENED (the owner, 2026-11-02: "when you open a task in Search it should automatically open
// instead of having to click Reopen task"). Search marks the task as it hands it over; the task page, when that task's detail lands,
// takes the mark - once - and runs its own Reopen task (task.reopen). Only Search marks: the rail, Recently deleted and a link elsewhere
// open a closed task closed, its Reopen task the press. A mark the page never took (the task did not open) goes stale, so a later open
// from the rail is never reopened by an old search.
export const REOPEN_MARK_MS = 30000;
export const CLOSED = ["done", "dropped"];
const marks = new Map();
// ...and says so, for a page that already has that task open (its detail will not land again to be read)
export const REOPEN_MARKED = "tq-reopen-marked";
export const markReopen = (tid, status, now = Date.now()) => {
  if (!tid || !CLOSED.includes(status)) return;
  marks.set(Number(tid), now);
  if (typeof window !== "undefined") window.dispatchEvent(new Event(REOPEN_MARKED));
};
// ...true once for a marked task, fresh; the mark is gone either way
export const takeReopen = (tid, now = Date.now()) => {
  const at = marks.get(Number(tid));
  marks.delete(Number(tid));
  return at !== undefined && now - at <= REOPEN_MARK_MS;
};
