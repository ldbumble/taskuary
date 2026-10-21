// STOP AND SAVE OPENS CLOSE OUT AT ONCE (the owner, 2026-10-21: "you can't just close the agent but leave off the close out - open
// the Close out right away and show the reply is being created, pending"). What the pending block says is the server job's own stage
// (writeup.py state: reading the session, writing the report, drafting the reply) - never a timer - and the draft replaces it in place.

// the steps the block lists, in the job's order; `reply` only where somebody is owed one
export const WRITEUP_STEPS = [["reading", "Reading the session"], ["report", "Writing the report"], ["reply", "Drafting the reply"]];
const EARLY = new Set(WRITEUP_STEPS.map(([k]) => k));
const FILED = /^(?:(?:AGENT|CODER) REPORT|The write-up of this session did not finish)/;
const FAILED = /^The write-up of this session did not finish:?\s*/;
const agentDrafted = (rv) => String(rv?.DraftBy || "").startsWith("agent:");

// What Close out draws for the write-up: null (the normal Close out - the draft, or what the task says), {state: "pending", stage},
// or {state: "failed", error}.
//   pressed - this page's Stop and save on this task: {n: comments at the press, job: the server's job id once the press answered}
//   server  - the task detail's `writeup` ({job, stage, running, error, close}), or null
//   review  - the pending reply review, if any
export function writeupView({ pressed = null, server = null, comments = [], review = null } = {}) {
  // the agent wrote its own reply (`--reply`): that is the answer, shown at once - nothing is rewritten over it
  if (agentDrafted(review)) return null;
  const mine = server && (!pressed?.job || server.job === pressed.job) ? server : null;
  // ...a job writing this task up, pressed here or anywhere else, while it has not yet filed the reply. A close (Mark done) is not a
  // Close out to wait on: the task leaves the table at once and is closed when the job is done.
  if (mine?.running && !mine.close) return EARLY.has(mine.stage) ? { state: "pending", stage: mine.stage } : null;
  if (!pressed) return null;
  if (!pressed.job) return { state: "pending", stage: server?.running && EARLY.has(server.stage) ? server.stage : "reading" };   // the press is still answering
  if (mine?.stage === "failed") return review ? null : { state: "failed", error: String(mine.error || "") };
  if (mine) return null;                                                   // done: the draft, or what the task says, is the Close out now
  // ...no word from the job (the server restarted under it): the task's own notes say whether the write-up landed or failed
  const after = (comments || []).slice(pressed.n || 0).map((c) => String(c.Body || "").trimStart());
  const fail = after.find((b) => FAILED.test(b));
  if (fail) return review ? null : { state: "failed", error: fail.replace(FAILED, "") };
  return after.some((b) => FILED.test(b)) ? null : { state: "pending", stage: "report" };
}

// the block's heading, by who it is for
export const writeupHead = (view, hasReply) => view?.state === "failed" ? "The write-up of this session did not finish"
  : hasReply ? "Writing the reply from the session…" : "Writing up the session…";
// the steps as the block lists them: each done, now, or to come
export const writeupSteps = (view, hasReply) => {
  const steps = WRITEUP_STEPS.filter(([k]) => hasReply || k !== "reply"), at = steps.findIndex(([k]) => k === view?.stage);
  return steps.map(([k, text], i) => ({ k, text, state: at < 0 ? "next" : i < at ? "done" : i === at ? "now" : "next" }));
};
