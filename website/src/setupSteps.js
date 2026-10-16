// What setup mode's rail shows (SetupSteps.jsx) and what its bottom row offers (FirstRun.jsx), from the first run's own state.
//
// THREE STEPS ARE SETUP, the rest is optional (the owner, 2026-10-15: "it should be after email/ai/survey rest is optional"): Finish
// opens once the AI, the email and About your work are done, and the rail says so until then. The rail marks the step ON THE CANVAS
// - it marked About your work while the owner was back on the email step - and a step gone back to always has Continue.
const mailInOf = (st) => st.step === "reading" || st.step === "done";
export const requiredDone = (st) => !!st && mailInOf(st) && !!st.about_done;

export const stepsOf = (st, shown = "") => {
  if (!st) return [];
  const mailIn = mailInOf(st), ready = requiredDone(st);
  const rows = [
    { key: "ai", label: "Your AI", done: st.step !== "ai", sub: st.step !== "ai" ? st.brain?.name || "" : "" },
    { key: "mail", label: "Your email", done: mailIn, sub: mailIn ? (st.step === "reading" ? "connected - sorting your mail" : "connected") : "" },
    { key: "about", label: "About your work", done: !!st.about_done, sub: st.about_done ? "saved" : "" },
    // ticked by what is connected beyond the AI and the mail - optional, but it never ticked however many were set up (2026-10-16)
    { key: "other", label: "More connections", done: (st.more_connected || 0) > 0, optional: true,
      sub: st.more_connected ? `${st.more_connected} connected` : "optional" },
    { key: "finish", label: "Finish", done: !!st.dismissed,
      // on Setup complete the move is its big Go to my day, not a Finish setup in the row (SetupDone)
      sub: ready ? (shown === "finish" ? "ready - Go to my day" : "ready - Finish setup is below") : "after AI, email and About your work" },
  ];
  const next = rows.find((r) => !r.done && !r.optional && (r.key !== "about" || mailIn))?.key || (ready ? "finish" : "");
  const at = shown || next;
  return rows.map((r) => ({ ...r, current: r.key === at }));
};

// ONE STEP ON THE CANVAS, BACK AND NEXT ALWAYS (the owner, 2026-10-15: "always have next/back button if possible and move to next
// step once one is complete"): the setup's steps in order, where to open, whether a step is done, and the row's moves for one.
export const ORDER = ["ai", "mail", "about", "other"];
export const nextOf = (v) => ORDER[Math.min(ORDER.indexOf(v) + 1, ORDER.length - 1)];
export const prevOf = (v) => ORDER[Math.max(ORDER.indexOf(v) - 1, 0)];
export const frontierOf = (st) => !st ? "ai" : st.step === "ai" ? "ai" : st.step === "email" ? "mail" : !st.about_done ? "about" : "other";
// REOPENED, it opens where the work is (the owner, 2026-10-16: the survey sat two Nexts past Your AI, unseen); with every step done,
// on Your AI - reopening is how the AI or the mailbox gets changed
export const openAt = (st, reopened = false) => { const f = frontierOf(st); return reopened && f === "other" ? "ai" : f; };
export const doneOf = (st, v) => !!st && (v === "ai" ? st.step !== "ai" : v === "mail" ? mailInOf(st) : v === "about" ? !!st.about_done : true);
const WAIT = { ai: "pick an AI that works first", mail: "connect your email first", about: "save or skip the answers first" };
// [{id, disabled, why}] for the row: Back from any step but the first; Next while there is a next; on the last, Walk and Finish
export const navMoves = (st, view, reopened = false) => {
  if (!st || !view) return [];
  const out = [];
  if (view !== ORDER[0]) out.push({ id: "back" });
  if (view !== "other") {
    out.push({ id: "next", disabled: !doneOf(st, view), why: WAIT[view] || "" });
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
