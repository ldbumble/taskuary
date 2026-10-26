// THE TASK PAGE'S LAYOUT (the redesign, owner-approved 2026-10-21): two always-open columns - what it came FROM on the left, the
// WORK or the reply on the right - in place of the Task / Agent work / Close out accordion. Pure, so node --test reads it.
import { channelName } from "./taskSources.js";
import { plural } from "./timeWords.js";
import { fmtDate } from "./dates.js";

// WHILE AN AGENT WORKS THE WORK TAKES THE WHOLE WIDTH: a live session - coding or general, working or waiting on you (the rail's
// spinning ring, or its hand) - and From folds to one line over it; the terminal is never covered or squeezed. `sessionView` is the
// page's own "the session fills the page" (a live session the owner has not stepped back from).
// ...AND ONCE IT HAS ACTED (the owner, 2026-10-22): an agent that stopped or finished with its Result (`result`), or whose run failed
// (`failed`, its reason and Try again), keeps the whole width too, From folded over it. Two columns - From | Reply - only where no
// agent ran or none was ever started: a plain mail or chat task with its draft, a held task.
// ...UNTIL 2026-10-25 (the owner: "keep agent working and everything the same with full agent screen ... but keep the 2 columns for when
// agent is not working"): only a LIVE session takes the whole width now. A finished, failed or closed agent is back in two columns - Came
// from on the left, its Result and Close out on the right - and the shade says which section to read (focusOf).
export const layoutOf = ({ sessionView = false }) => (sessionView ? "full" : "columns");

// THE FOCUS (the owner, 2026-10-25: "shading for what to focus on"): with no agent live the card's body is shaded and one section is white -
// the agent's part once it has a Result (or its run failed, Try again being the move); Close out where the reply is the move; and where the
// open half is the agent's box (a to-do, a goal) the task's own LIST instead (the owner's answer, 2026-10-25): a goal's Steps, a to-do's
// checklist (`list`), else the block that carries the ask's source ("source"). A task waiting on a person has nothing white ("none").
export const focusOf = ({ live = false, result = false, failed = false, pane = "", waiting = false, list = false } = {}) =>
  live ? null : waiting ? "none" : result || failed ? "agent" : pane === "agent" ? (list ? "list" : "source") : "reply";

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

// THE ASK IS THE MESSAGE'S OWN WORDS when triage left no summary of its own (the task-view cleanup, owner-approved 2026-10-25): said
// once, under the title, and From does not open the same words again as the message under it. Spacing and line breaks aside.
const squash = (s) => String(s || "").replace(/\s+/g, " ").trim();
export const sameWords = (a, b) => !!squash(a) && squash(a) === squash(b);
// ...and THE ASK THAT IS THE TITLE is not said under it again (the owner, 2026-10-26, a playbook task on a laptop: "you can't see anything.
// there are too many lines on top"): the same words, or a title cut from the ask's own start (a playbook's is its first 100 characters) -
// whoever waits on it still gets the band, and the ask's whole words are the title's hover
export const askIsTitle = (ask, title) => {
  const a = squash(ask).toLowerCase(), t = squash(title).replace(/(…|\.\.\.)$/, "").trim().toLowerCase();
  return !!a && (a === t || (t.length >= 24 && a.startsWith(t)) || (a.length >= 24 && t.endsWith(a)));
};

// WHO A TASK WAITS ON (the owner, 2026-10-25): a task handed to a person opens on them - "Waiting on Ray. Due Oct 23, 2 days late."
// The name is the one their own mail on the task signs with, else the address read as a name, the way the server reads a step's
// holder (processing_unread.holder_name). Null where the task waits on nobody: not waiting, or held by an agent.
export const holderName = (addr) => String(addr || "").split("@")[0].split(/[._-]+/).filter(Boolean)
  .map((p) => p[0].toUpperCase() + p.slice(1)).join(" ");
export const waitingOn = ({ task = {}, messages = [], now = new Date() } = {}) => {
  const who = String(task.Assignee || "");
  if (task.Status !== "waiting" || !who.startsWith("person:")) return null;
  const addr = who.slice(7), mail = messages.find((m) => String(m.FromEmail || "").toLowerCase() === addr.toLowerCase() && m.FromName);
  const name = mail?.FromName || holderName(addr) || addr;
  const due = /^\d{4}-\d{2}-\d{2}/.test(String(task.DueAt || "")) ? new Date(`${String(task.DueAt).slice(0, 10)}T00:00:00`) : null;
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const late = due ? Math.round((today - due) / 86400000) : 0;
  const when = !due ? "" : ` Due ${fmtDate(due, [], { month: "short", day: "numeric" })}${late > 0 ? `, ${plural(late, "day")} late` : late === 0 ? ", today" : ""}.`;
  return { name, line: `Waiting on ${name}.${when}` };
};
