// Does this move land on a stop, or end the walk? `walk.go` clamps anything outside the list to 0
// and returns that, so the answer must come from what was REQUESTED, never from what came back -
// reading `data.at` would make Finish silently reopen the first stop.
export const walkAdvances = (at, total) => at >= 0 && at < total;
