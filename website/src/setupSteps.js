// What setup mode's rail shows (SetupSteps.jsx) and what its bottom row offers (FirstRun.jsx), from the first run's own state.
//
// THE SERVER SAYS THE STEPS (firstrun.rail): which are done, which can be opened yet, what a waiting one waits for, where setup opens
// and whether Finish is open. This page re-derived all of that from `step` - a second copy of the rule (2026-10-18). What stays here is
// the canvas's own: the rail marks the step ON THE CANVAS - it marked About your work while the owner was back on the email step - and
// a step gone back to always has Continue.
const rowOf = (st, k) => st?.rail?.find((r) => r.key === k);
export const requiredDone = (st) => !!st?.ready;

export const stepsOf = (st, shown = "") => {
  if (!st?.rail) return [];
  const next = st.rail.find((r) => !r.done && !r.optional && r.open)?.key || (st.ready ? "finish" : "");
  const at = shown || next;
  // on Setup complete the move is its big Go to my day, not a Finish setup in the row (SetupDone)
  return st.rail.map((r) => ({ ...r, current: r.key === at, disabled: !r.open,
    ...(r.key === "finish" && st.ready && shown === "finish" ? { sub: "ready - Go to my day" } : {}) }));
};

// ONE STEP ON THE CANVAS, BACK AND NEXT ALWAYS (the owner, 2026-10-15: "always have next/back button if possible and move to next
// step once one is complete"): the setup's steps in order, where to open, whether a step is done, and the row's moves for one.
export const ORDER = ["ai", "mail", "about", "other"];
export const nextOf = (v) => ORDER[Math.min(ORDER.indexOf(v) + 1, ORDER.length - 1)];
export const prevOf = (v) => ORDER[Math.max(ORDER.indexOf(v) - 1, 0)];
export const frontierOf = (st) => st?.frontier || "ai";
// REOPENED, it opens where the work is (the owner, 2026-10-16: the survey sat two Nexts past Your AI, unseen); with every step done,
// on Your AI - reopening is how the AI or the mailbox gets changed
export const openAt = (st, reopened = false) => { const f = frontierOf(st); return reopened && f === "other" ? "ai" : f; };
// done enough to move on from: More connections is optional, so it always is
export const doneOf = (st, v) => !!st && (v === "other" || (rowOf(st, v)?.done ?? true));
// whether a step can be opened yet: the email after a working AI, About your work after the email; the AI and the optional
// connections always
export const reachable = (st, v) => rowOf(st, v)?.open ?? true;
// [{id, disabled, why}] for the row: Back from any step but the first; Next while there is a next; on the last, Walk and Finish
export const navMoves = (st, view, reopened = false) => {
  if (!st || !view) return [];
  const out = [];
  if (view !== ORDER[0]) out.push({ id: "back" });
  if (view !== "other") {
    out.push({ id: "next", disabled: !doneOf(st, view), why: rowOf(st, view)?.need || "" });
    // reopened from the top bar to change one thing: the way back to the day is on every step, not only the last
    if (reopened) out.push({ id: "finish" });
  }
  else {
    // Finish setup alone: Walk me through my tasks is the day's own move once setup is finished (the owner, 2026-10-15)
    const ready = requiredDone(st) || reopened;
    out.push({ id: "finish", disabled: !ready, why: ready ? "" : "AI, email and About your work come first" });
  }
  return out;
};
