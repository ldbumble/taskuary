// THE TASK PAGE'S LAYOUT: what it came FROM, and the one chat where the agent works and every draft, Send and close is (the owner,
// 2026-11-06: "there should no longer be close out code anywhere"). Pure, so node --test reads it.
import { channelName } from "./taskSources.js";
import { plural } from "./timeWords.js";
import { fmtDate } from "./dates.js";
import { drawerLit, mainView, sectionOf, stageOf } from "./stages.js";
import { waitingEmails } from "./taskLifecycle.js";
import { isGeneralKind } from "./autostart.js";

// WHILE AN AGENT WORKS THE WORK TAKES THE WHOLE WIDTH: a live session - coding or general, working or waiting on you (the rail's
// spinning ring, or its hand) - and From folds to one line over it; the terminal is never covered or squeezed. `sessionView` is the
// page's own "the session fills the page" (a live session the owner has not stepped back from).
// ...AND ONCE IT HAS ACTED (the owner, 2026-10-22): an agent that stopped or finished with its Result (`result`), or whose run failed
// (`failed`, its reason and Try again), keeps the whole width too, From folded over it. Two columns - From | Reply - only where no
// agent ran or none was ever started: a plain mail or chat task with its draft, a held task.
// ...UNTIL 2026-10-25 (the owner: "keep agent working and everything the same with full agent screen ... but keep the 2 columns for when
// agent is not working"): only a LIVE session takes the whole width now.
export const layoutOf = ({ sessionView = false }) => (sessionView ? "full" : "columns");

// THE FOCUS (the owner, 2026-10-25: "shading for what to focus on"), which makes the stage: the agent's part once it has a Result (or its run
// failed); the reply where it is the move ("reply"); a goal's Steps or a to-do's checklist (`list`), else the block that carries the ask
// ("source"). A task waiting on a person has nothing white ("none"). A draft or emails waiting for Send (`owed`) are the move even under a
// finished agent (the owner, 2026-10-27).
export const focusOf = ({ live = false, result = false, failed = false, pane = "", waiting = false, list = false, owed = false } = {}) =>
  live ? null : waiting ? "none" : owed ? "reply" : result || failed ? "agent" : pane === "agent" ? (list ? "list" : "source") : "reply";

// THE MAIN VIEW, read from the one stage model (stages.json, the owner 2026-10-26: "we should define this well"): the focus and what is
// drafted (`drafted`: a draft, emails owed, a close, a write-up) make the stage, and the stage names its main view and whether the other
// part's tab is lit. `stacked`: a phone's narrow body keeps its one stacked page (null). `closed`: a closed task is `done`
export const mainOf = ({ sessionView = false, stacked = false, focus = null, drafted = false, closed = false } = {}) =>
  mainView({ stage: stageOf({ focus, drafted, closed }), sessionView, stacked });
// ...WHICH DRAWER HOLDS WHAT IS NEXT, so its tab is lit: the right one where the task is the page but the move is the reply (nothing
// drafted yet) or an agent (an ask nothing has worked: "source"). A to-do's or a goal's list is itself the move; Came from is context only.
export const nextInDrawer = ({ main = null, focus = null } = {}) => drawerLit({ main, stage: stageOf({ focus }) });

// WHAT THE TASK IS UP TO, the agent or the reply - the focus the stage is read from. The page's focus (taskLifecycle.focusStage) decides
// between them; where it named the task itself, what the task is for: the reply for a reply with somebody to answer, else the agent.
// An agent's RESULT stays the move while nothing waits on a Send (the owner, 2026-10-22). `replyHas`: a draft, emails, a close, a failed
// write-up. `picked`: opened by hand.
export const workPane = ({ stage, kind, hasSender, codeRun = false, result = false, replyHas = false, picked = false }) => {
  if (stage === "reply" && result && !hasSender && !replyHas && !picked) return "agent";
  if (stage === "agent" || stage === "reply") return stage;
  if (codeRun) return "reply";
  return hasSender && !["coding", "general"].includes(kind) ? "reply" : "agent";
};

// A WRITE-UP UNDER WAY IS ONE LINE under the Result it writes up (the owner, 2026-10-29); one that FAILED is a card in the chat, with its
// Try again, where its draft would have stood: "chat", "result" or null
export const writeupAt = (writeup) => (!writeup ? null : writeup.state === "failed" ? "chat" : "result");

// WHAT WAITS ON THE OWNER'S SEND, which makes the stage: `waits` - a reply draft, a proposal or a drafted email waiting for Send (the next
// move); `has` - that, or a reply that went, a close, a write-up that failed, an answer given outside. An email the checklist owes with
// NOTHING DRAFTED for it is not a draft (the owner, 2026-11-02); the server's stage reads the same (stages.facts `drafted`)
export const replyHolds = ({ pending = false, sent = false, proposals = 0, checklist = [], reviews = [], ended = false, outside = 0, closed = false, writeup = false } = {}) => {
  const waits = !!(pending || proposals || waitingEmails(checklist, reviews));
  return { has: waits || !!(sent || ended || outside || closed || writeup), waits };
};

// THE ONE LINE From folds to: who it came from and how many messages ("Gail Moreno · 3 messages"), a workflow's name, or - with
// no message at all - where it was made
export const fromLine = ({ sender = null, count = 0, workflow = null, made = "" } = {}) => {
  if (count && sender) return [sender.FromName || sender.FromEmail || channelName(sender.Channel), plural(count, "message")].join(" · ");
  if (workflow) return `Routine · ${workflow.title}`;
  return made || "";
};

// TWO SECTIONS, IN THE ORDER THE WORK FLOWS: what came in, and the one chat (the owner, 2026-11-06, on a to-do still showing Close out: "i
// thought we removed this from everywhere? ... there should no longer be close out code anywhere"). Every kind - general, reply, coding, a
// plain to-do - is Came from and its chat; a draft's Send, the emails owed, the landing, the hand-off and the close are cards in the chat,
// and the task's buttons ride its strip. One is open and fills the width, the other a closed tab that says where it stands.
export const SECTIONS = [{ key: "from", n: 1, name: "Came from" }, { key: "agent", n: 2, name: "Agent" }];
// ...a live CODING terminal: a general agent's own chat is a session too (mode "assistant"); a coding CLI's is a toggle in its chat (GeneralWorkspace)
export const liveTerminal = (term) => !!term?.alive && term.mode !== "assistant";
// ...A PLAIN TO-DO NO AGENT HAS TOUCHED IS ONE SECTION (the owner, 2026-11-06: the "Agent - not started" column beside a to-do): what came in,
// the box under it - typing there starts the agent, and its chat then joins as the second section. `started`: any agent ever on it
export const soloTodo = ({ kind, started = false } = {}) => kind === "task" && !started;
// ...and it opens where triage put it - on what came in (the owner, 2026-11-05: "if the triage says it is just a todo ... it should open on
// the came from section only") or, once an agent has a Result or a draft on it, where its stage is; every other kind opens on its chat
// ...ONE RULE FOR EVERY KIND (the owner, 2026-11-08): a task with any agent or chat on it - a session, a turn, a draft - opens on its chat, Came
// from folded to the thin arrow tab, so the message shows once, in the chat; one with nothing but what came in opens on Came from. `chat`: the
// page's own reading (TaskPage anyChat); left out, a to-do's stage or any other kind's chat answers it
export const homeSection = (kind, stage, chat = kind !== "task" || sectionOf(stage) === "agent") => (chat ? "agent" : "from");
// ...a closed tab says MORE than its name (the owner, 2026-10-27: "maybe a little smaller and have more summary on each one"): three or four
// short lines, each clamped so a tab never scrolls. Words quoted are somebody's own; each line only where there is something to say.
// ...and read like a book's SPINE (the owner, 2026-10-27): its `lines` at the top under the name, its `foot` - the one status line - at the
// bottom over a thin rule, the section's number under it
const q = (s) => (s ? `“${String(s).replace(/\s+/g, " ").trim()}”` : "");
// ...Came from: who, on what, when; their latest words; how many - and at its foot what triage made of it ("✓ Sorted: a reply to send · normal priority")
// ...AT A GLANCE (the owner, 2026-10-27: "show more"): on what and how many, then every message newest first - who, and a short line each;
// the tab draws as many as fit, newest down with none skipped (TaskPage fitTabLines) - a fixed three under "4 messages" read as one lost
// ...never more than a spine can hold, though (TAB_MOST): a 1,500-line chat drew 1,500 lines into the tab to measure and hide all but a dozen,
// a second of the click that opened it (the owner, 2026-11-01: "this still happens")
export const TAB_MOST = 40;
// ...and under the first line whom it went to, when anyone but the owner was on it (`to`, taskSources.toLine - the owner, 2026-11-03)
// ...WHO it came from, for its first line: an email's sender by name - its SourceName is the owner's own mailbox, and the spine of every mail
// task read "alex@northwind.example · 1 message" (the overnight run, 2026-11-03) - and a chat's room (a WhatsApp group, a Teams channel) by its own
export const cameFrom = (m) => !m ? "" : String(m.Channel || "").toLowerCase() === "email" ? String(m.FromName || m.FromEmail || "") : String(m.SourceName || "");
export const fromStatus = ({ channel = "", count = 0, msgs = [], workflow = null, made = "", sorted = "", to = "" } = {}) => ({
  lines: [count ? [channel, plural(count, "message")].filter(Boolean).join(" · ") : workflow ? `Routine · ${workflow.title}` : made, to,
    ...msgs.slice(0, TAB_MOST).map((m) => `${m.who}: ${q(m.words)}`)].filter(Boolean),
  foot: sorted ? `✓ ${sorted}` : "" });
// ...the Agent: its profile and where it stands, what it did in a line, what it made - and at its foot its state and the Advisor's next move
// ...and a start held back for a free agent slot says so (`queued`, QueuedStart), never "not started" over a start already on its way (2026-11-04)
export const agentWord = ({ live = false, waiting = false, failed = false, stopped = false, result = false, record = false, codeRun = false, queued = false } = {}) =>
  live ? (waiting ? "needs you" : "working") : queued ? "waiting its turn" : failed ? "failed" : stopped ? "stopped" : result ? "finished" : record ? "ran" : codeRun ? "steps ran by code" : "not started";
// ...what an AGENT REPORT says in a line: its Summary, else its first line of words - never the "AGENT REPORT" marker it opens with (the
// state matrix, 2026-10-28: the Agent tab of a task whose sender wrote again read "general · ran / AGENT REPORT")
export const reportLine = (body) => {
  const ls = String(body || "").split("\n").map((l) => l.trim()).filter((l) => l && !/^(AGENT REPORT|LAST MESSAGE)$/i.test(l));
  const i = Math.max(0, ls.findIndex((l) => /^Summary:/i.test(l)));
  const line = (ls[i] || "").replace(/^(Summary|Determination):\s*/i, "");
  // ...and a line that ends on a colon is not a summary, it introduces the next one ("It says:" with nothing after - the email walk,
  // 2026-10-29): the line it opens rides with it
  return line.endsWith(":") && ls[i + 1] ? `${line} ${ls[i + 1]}` : line;
};
export const agentStatus = ({ profile = "", word = "not started", said = "", made = "", advisor = "" } = {}) => ({
  lines: [[profile, word].filter(Boolean).join(" · "), said, made ? `Made: ${made}` : ""].filter(Boolean),
  foot: [word === "finished" ? "✓ Done" : "", advisor ? `Advisor: ${advisor} is next` : ""].filter(Boolean).join(" · ") });

// ANSWERED OUTSIDE TASKUARY: the newest message on the task is the owner's own, typed in Teams, the mail client or a chat
// (channels.ingest_own_message: a `context` row, Direction out) - not a reply sent from here coming back (taskLifecycle.sentElsewhere
// already left those out of `outside`). `messages` the task's conversation with the replies sent from here in it. That message, or null
// while anything came in after it, a reply went from here after it, or a draft waits.
const ts = (m) => Date.parse(String(m?.SentAt || m?.CreatedAt || "").replace(" ", "T")) || 0;
export const answeredOutside = ({ messages = [], outside = [], pending = false } = {}) => {
  if (pending || !outside.length) return null;
  const newest = [...messages].sort((a, b) => ts(b) - ts(a))[0];
  return newest && outside.some((m) => m.MessageId === newest.MessageId) ? newest : null;
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
