// THE TASK PAGE'S LAYOUT (the redesign, owner-approved 2026-10-21): two always-open columns - what it came FROM on the left, the
// WORK or the reply on the right - in place of the Task / Agent work / Close out accordion. Pure, so node --test reads it.
import { channelName } from "./taskSources.js";
import { plural } from "./timeWords.js";

// WHILE AN AGENT WORKS THE WORK TAKES THE WHOLE WIDTH: a live session - coding or general, working or waiting on you (the rail's
// spinning ring, or its hand) - and From folds to one line over it; the terminal is never covered or squeezed. `sessionView` is the
// page's own "the session fills the page" (a live session the owner has not stepped back from).
// ...AND ONCE IT HAS ACTED (the owner, 2026-10-22): an agent that stopped or finished with its Result (`result`), or whose run failed
// (`failed`, its reason and Try again), keeps the whole width too, From folded over it. Two columns - From | Reply - only where no
// agent ran or none was ever started: a plain mail or chat task with its draft, a held task.
export const layoutOf = ({ sessionView = false, result = false, failed = false }) => (sessionView || result || failed ? "full" : "columns");

// WHICH HALF OF THE WORK COLUMN IS OPEN. The page's focus (taskLifecycle.focusStage) still decides between the agent and the
// reply; where it named the task itself - now the always-open From column - the work column opens on what the task is for: the
// reply for a reply with somebody to answer, else the agent (its plan, its start, its record).
// ...and an agent's RESULT stays the open half while nothing is in the reply's: Stop and save opens Close out (`stage` reply) so a
// reply being drafted shows where it will land, but on a task nobody sent there is no reply, and Close out was an empty card under
// a Result folded to two lines (the owner, 2026-10-22: "since it gets crunched down you can not really see the agent report").
// `replyHas`: the reply half has something of its own - a draft, emails, a close, a failed write-up. `picked`: opened by hand.
export const workPane = ({ stage, kind, hasSender, codeRun = false, result = false, replyHas = false, picked = false }) => {
  if (stage === "reply" && result && !hasSender && !replyHas && !picked) return "agent";
  if (stage === "agent" || stage === "reply") return stage;
  if (codeRun) return "reply";
  return hasSender && !["coding", "general"].includes(kind) ? "reply" : "agent";
};

// CLOSE OUT UNDER A RESULT, ON A TASK NOBODY SENT: "Nobody sent this one... Work it, or write what you found" and a "reply · not
// available" pill are advice for an open task with nothing done yet - under an agent's Result they read as an empty reply section.
// There Close out says what closes it, and the write-up's progress is a line under the Result it is writing up. A reply being drafted
// (somebody is owed one) and a write-up that failed (its Try again) stay in Close out, where the draft will stand.
//   advice - the "Nobody sent this one" line; chip - the reply pill; writeupAt - "closeout", "result" or null
export const closeOut = ({ hasSender = false, result = false, writeup = null } = {}) => {
  const bare = result && !hasSender;
  return { advice: !bare, chip: !bare, writeupAt: !writeup ? null : bare && writeup.state !== "failed" ? "result" : "closeout" };
};
export const CLOSE_BY_HAND = "Mark done closes it, or close it with a note.";

// THE ONE LINE From folds to: who it came from and how many messages ("Gail Moreno · 3 messages"), a workflow's name, or - with
// no message at all - where it was made
export const fromLine = ({ sender = null, count = 0, workflow = null, made = "" } = {}) => {
  if (count && sender) return [sender.FromName || sender.FromEmail || channelName(sender.Channel), plural(count, "message")].join(" · ");
  if (workflow) return `Workflow · ${workflow.title}`;
  return made || "";
};
