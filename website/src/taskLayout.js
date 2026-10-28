// THE TASK PAGE'S LAYOUT (the redesign, owner-approved 2026-10-21): two always-open columns - what it came FROM on the left, the
// WORK or the reply on the right - in place of the Task / Agent work / Close out accordion. Pure, so node --test reads it.
import { channelName } from "./taskSources.js";
import { plural } from "./timeWords.js";
import { fmtDate } from "./dates.js";
import { drawerLit, mainView, stageOf } from "./stages.js";

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
// ...BUT THE FOCUS FOLLOWS THE NEXT MOVE (the owner, 2026-10-27: "why is the white part the agent result if the focus is on ready to send"):
// a draft or emails waiting for Send (`owed`) make Close out the white section even under a finished agent - its Result is shaded above.
// A finished agent with nothing drafted keeps the focus on its Result.
export const focusOf = ({ live = false, result = false, failed = false, pane = "", waiting = false, list = false, owed = false } = {}) =>
  live ? null : waiting ? "none" : owed ? "reply" : result || failed ? "agent" : pane === "agent" ? (list ? "list" : "source") : "reply";

// THE MAIN VIEW (the owner, 2026-10-26: "if task view is where the task opens to it should only open on that, and then right side arrow
// should pull out the agent/close out screens. If up to agent or close out open those with coming from in left side draw"): the focus
// says where the task is up to. A live agent, its Result or its failure, or Close out -> "work", Came from the left drawer; a to-do, a
// goal's steps, an ask nothing has worked yet, a wait on a person -> "task", Agent and Close out the right drawer. `stacked`: a phone's
// narrow body keeps its one stacked page (null).
// ...and a reply with NOTHING DRAFTED yet opens on the task, its right tab lit (the owner, 2026-10-26: "you can open on task but highlight
// the side bar so people know to go there"); `drafted` is anything of Close out's own - a draft, emails owed, a close, a write-up
// ...ALL OF IT NOW READ FROM THE ONE STAGE MODEL (stages.json, the owner 2026-10-26: "we should define this well"): the focus and what
// is drafted make the stage, and the stage names its main view and whether the drawer's tab is lit. `closed`: a closed task is `done`,
// which opens on how it closed
export const mainOf = ({ sessionView = false, stacked = false, focus = null, drafted = false, closed = false } = {}) =>
  mainView({ stage: stageOf({ focus, drafted, closed }), sessionView, stacked });
// ...WHICH DRAWER HOLDS WHAT IS NEXT, so its tab is lit: the right one where the task is the page but the move is the reply (nothing
// drafted yet) or an agent (an ask nothing has worked: "source"). A to-do's or a goal's list is itself the move; Came from is context only.
export const nextInDrawer = ({ main = null, focus = null } = {}) => drawerLit({ main, stage: stageOf({ focus }) });

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

// THREE SECTIONS IN A ROW, IN THE ORDER THE WORK FLOWS (the owner, 2026-10-27, from a mockup: "input -> agent/advisor -> close ... 3 sections
// from left to right showing the flow; on the outside it shows the status of each category and opens up to the one it's up to"): one is
// open and fills the width, the other two are closed tabs that say where each stands in a line or two. `here`: the section the task is up
// to (stages.sectionOf). Pure, so node --test reads it.
export const SECTIONS = [{ key: "from", n: 1, name: "Came from" }, { key: "agent", n: 2, name: "Agent" }, { key: "close", n: 3, name: "Close out" }];
// ...a closed tab says MORE than its name (the owner, 2026-10-27: "maybe a little smaller and have more summary on each one"): three or four
// short lines, each clamped so a tab never scrolls. Words quoted are somebody's own; each line only where there is something to say.
// ...and read like a book's SPINE (the owner, 2026-10-27): its `lines` at the top under the name, its `foot` - the one status line - at the
// bottom over a thin rule, the section's number under it
const q = (s) => (s ? `“${String(s).replace(/\s+/g, " ").trim()}”` : "");
// ...Came from: who, on what, when; their latest words; how many - and at its foot what triage made of it ("✓ Sorted: a reply to send · normal priority")
// ...AT A GLANCE (the owner, 2026-10-27: "show more"): on what and how many, then the last two or three messages - who, and a short line each
export const fromStatus = ({ channel = "", count = 0, msgs = [], workflow = null, made = "", sorted = "" } = {}) => ({
  lines: [count ? [channel, plural(count, "message")].filter(Boolean).join(" · ") : workflow ? `Workflow · ${workflow.title}` : made,
    ...msgs.slice(0, 3).map((m) => `${m.who}: ${q(m.words)}`)].filter(Boolean),
  foot: sorted ? `✓ ${sorted}` : "" });
// ...the Agent: its profile and where it stands, what it did in a line, what it made - and at its foot its state and the Advisor's next move
export const agentWord = ({ live = false, waiting = false, failed = false, stopped = false, result = false, record = false, codeRun = false } = {}) =>
  live ? (waiting ? "needs you" : "working") : failed ? "failed" : stopped ? "stopped" : result ? "finished" : record ? "ran" : codeRun ? "steps ran by code" : "not started";
// ...what an AGENT REPORT says in a line: its Summary, else its first line of words - never the "AGENT REPORT" marker it opens with (the
// state matrix, 2026-10-28: the Agent tab of a task whose sender wrote again read "general · ran / AGENT REPORT")
export const reportLine = (body) => {
  const ls = String(body || "").split("\n").map((l) => l.trim()).filter((l) => l && !/^(AGENT REPORT|LAST MESSAGE)$/i.test(l));
  return (ls.find((l) => /^Summary:/i.test(l)) || ls[0] || "").replace(/^(Summary|Determination):\s*/i, "");
};
export const agentStatus = ({ profile = "", word = "not started", said = "", made = "", advisor = "" } = {}) => ({
  lines: [[profile, word].filter(Boolean).join(" · "), said, made ? `Made: ${made}` : ""].filter(Boolean),
  foot: [word === "finished" ? "✓ Done" : "", advisor ? `Advisor: ${advisor} is next` : ""].filter(Boolean).join(" · ") });
// ...Close out: who it answers and where, the draft's first words, and whether it went - "Drafted · waiting for Send", "Sent", "Nothing owed"
// ...and what is in it: the draft's first words, or what was sent and when, the emails owed, the close and its note
export const closeStatus = ({ closed = false, note = "", to = "", where = "", draft = "", waiting = false, emails = 0, sent = false, sentWhen = "", owed = false } = {}) => ({
  lines: [to ? `Reply to ${to}${where ? ` in ${where}` : ""}` : "", q(draft),
    closed ? ["Closed", note].filter(Boolean).join(" · ") : waiting ? "Drafted · waiting for Send" : sent ? (sentWhen ? `Sent ${sentWhen}` : "Sent") : owed ? "Not drafted yet" : emails ? "" : "Nothing owed",
    emails ? `${plural(emails, "email")} waiting for Send` : ""].filter(Boolean),
  foot: "" });

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
