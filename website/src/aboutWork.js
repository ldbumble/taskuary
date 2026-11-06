// About your work's questions, in order, and what its one Next sends - plain, so a test reads them without drawing the screen.
// THE JOB AND WHAT YOU WORK ON ARE ONE STEP (the owner, 2026-11-06): the job description on top, the workstreams the mail was grouped
// into below it, and one Next for both - nine questions, no longer ten.
export const STEPS = ["name", "org", "role", "signature", "systems", "mailboxes", "job", "style", "soul"];
export const MAIL_AT = STEPS.indexOf("mailboxes");
// Skip before the mailbox step lands on it; on it there is no Skip; past it, Skip leaves the rest (null)
export const skipTo = (at) => (at < MAIL_AT ? MAIL_AT : null);
export const canSkip = (step) => step !== "mailboxes";
// the drafts written from the mail - the server's own list (firstrun.DRAFTS); workstreams has no step of its own, it is drawn under the job
export const DRAFTS = ["job", "workstreams", "style", "soul"];
export const counter = (at) => `${at + 1} of ${STEPS.length}`;
// NEXT NEVER WAITS ON THE GROUPING: still running, an empty answer asks the server to keep the defaults once it lands
// (firstrun.keep_when_ready); ready, the list as the owner left it; nothing to say (failed, none), no call at all
export const wsAnswer = (d, text = "", edited = false) => d?.state === "running" ? { doc: "workstreams", text: "" }
  : (d?.state === "ready" || edited) && String(text || "").trim() ? { doc: "workstreams", text } : null;
export const WS_LATER = "What you work on is still being read from your mail - it fills in on its own; you can change it later on About you.";
// the rows About you sends: only the ones the owner changed - an unanswered proposal left alone stays a proposal
export const changedRows = (was, now) => {
  const old = Object.fromEntries(was.map((r) => [r.slug, JSON.stringify([r.name, !!r.personal, r.keep !== false])]));
  return now.filter((r) => old[r.slug] !== JSON.stringify([r.name, !!r.personal, r.keep !== false]))
    .map((r) => ({ slug: r.slug, name: r.name, personal: !!r.personal, keep: r.keep !== false }));
};
