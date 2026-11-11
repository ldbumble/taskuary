// WHO is working, and what it has got so far - read off the session's own trace.
//
// The thing that does the work is an AGENT. "Assistant" is the thing that helps you run Taskuary,
// and the work window wore that word four times over - the strip, the view button, the composer,
// and "TASKUARY" as the speaker of every turn - while a real agent searched the web (the owner,
// 2026-09-08: "it should be agent not assistant. Assistant is what helps you run taskuary. agents
// are what do work"). Where the window named anything at all it named a binary and a profile:
// "Agent running · Claude Code · <profile> (your CLI)".
//
// Nothing here asks the server for anything new. The trace is already on the assistant payload and
// the name is already on the task, so an agent that reads as working needs no new endpoint.
import { AGENT_SHOWN } from "./kinds.js";
import { toolTarget } from "./assistantStream.js";
import { plural } from "./timeWords.js";

// ONE NAME AT WORK (the owner, 2026-10-28): the agent is Taskuary on every screen. The profile it runs under ("researcher",
// a kind's "Research") read as the actor - "researcher asked you something" over a run signing the owner up for things - and it
// is the instructions, not the worker: it shows on hover only (kinds.instructionsHint), and Settings edits it.
export const agentName = () => AGENT_SHOWN;

const HOST = /^https?:\/\/(?:www\.)?([^/?#]+)/i;
export const sourceOf = (target) => (HOST.exec(String(target || "")) || [])[1] || "";

// Every tool call the turn has made, paired with its result. A call with no result yet is what the
// agent is doing RIGHT NOW - the one fact the old window never stated.
export const workOf = (trace) => {
  const byId = new Map(), steps = [];
  for (const e of trace || []) {
    if (e?.type === "tool_call") {
      const id = e.detail?.tool_call_id || `${e.name}-${steps.length}`;
      const step = { id, tool: e.name || "tool", target: toolTarget(e.detail?.args || {}), done: false, error: false };
      byId.set(id, step); steps.push(step);
    } else if (e?.type === "tool_result") {
      const step = byId.get(e.detail?.tool_call_id || e.name);
      if (step) { step.done = true; step.error = !!e.detail?.is_error; }
    }
  }
  const done = steps.filter((s) => s.done);
  const reads = done.filter((s) => /fetch|read/i.test(s.tool));
  return { steps, done, reads,
           running: steps.filter((s) => !s.done),
           searches: done.filter((s) => /search|grep|glob/i.test(s.tool)),
           sources: [...new Set(reads.map((s) => sourceOf(s.target)).filter(Boolean))] };
};

// ...in the agent's own words. Between two calls there is nothing running, and the honest thing to
// say then is the last thing it did, not silence.
export const doingNow = (work) => {
  const step = work?.running?.[0] || work?.steps?.[work.steps.length - 1];
  if (!step) return "";
  if (/fetch|read/i.test(step.tool)) return `Reading ${sourceOf(step.target) || step.target}`.trim();
  if (/search/i.test(step.tool)) return `Searching for ${step.target}`.trim();
  return `${step.tool} ${step.target}`.trim();
};

// A chat session's "screen" is a pseudo-terminal: "assistant> ..." with a "you>" prompt under it.
// That is the right shape for a CLI holding a shell and the wrong one for a conversation - the Board
// drew a research question as a black rectangle with the sentence cut off mid-word, under a prompt
// nobody types into (the owner, 2026-09-08: "assistant still looks like coding cli?"). The last thing
// it SAID is the last line that is not a prompt.
// ...and a turn's whole answer, from its start (workerstate.status `said`): read off the tail, a drafted reply was its sign-off
export const saidOf = (run) => String(run?.said || "").replace(/\s+/g, " ").trim() || saidFromTail(run?.tail);
export const saidFromTail = (tail) => (tail || [])
  .map((line) => String(line).replace(/^\s*(?:assistant|you)>\s*/i, "").trim())
  .filter(Boolean).pop() || "";

// The trail as a COUNT. A finished tool call is history, and six of them are six rectangles of
// history stacked in front of the one thing that is happening.
export const trailText = (work) => [
  work?.searches?.length && `${work.searches.length} search${work.searches.length === 1 ? "" : "es"}`,
  work?.reads?.length && `${plural(work.reads.length, "page")} read`,
].filter(Boolean).join(" · ");

// The TURN's clock, not the session's: a conversation opened this morning has been alive for hours
// and has been working for twenty seconds. The owner's last line is where the turn began.
export const turnStart = (messages) => {
  const at = [...(messages || [])].reverse().find((m) => m?.role === "user")?.createdAt;
  const ms = at ? new Date(String(at).replace(" ", "T")).getTime() : NaN;
  return Number.isFinite(ms) ? ms : null;
};

export const elapsedText = (ms) => {
  const s = Math.max(0, Math.round((ms || 0) / 1000));
  return s < 60 ? `${s}s` : `${Math.floor(s / 60)}m ${String(s % 60).padStart(2, "0")}s`;
};

// A CHAT TURN'S STAMP (the owner, 2026-11-05: "it should show right when it starts the counter on top, then it stops when response is generated"):
// "working 0:42" from the turn's own start while it runs, "ran 1m 12s" once its answer is filed, and nothing it cannot know - no start, or
// a gap past six hours, which is no turn's run but a chat left and come back to
export const tookText = (ms) => { const s = Math.round(ms / 1000);
  return s < 60 ? `${s}s` : s < 3600 ? `${Math.floor(s / 60)}m ${s % 60}s` : `${Math.floor(s / 3600)}h ${Math.floor((s % 3600) / 60)}m`; };
export const clockText = (ms) => { const s = Math.max(0, Math.floor((ms || 0) / 1000)), h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60);
  return `${h ? `${h}:${String(m).padStart(2, "0")}` : m}:${String(s % 60).padStart(2, "0")}`; };
// ...FROM WHEN IT BEGAN: the newest of everything above it, not the row just above (the owner, 2026-11-05): a mail read in while the turn before
// ran is drawn between that answer and the re-think it woke, stamped when it came in - read as the start, the re-think "ran" from before the
// answer above it had finished
// ...A RUNNING TURN COUNTS FROM THE EARLIER OF ITS OWN START AND THE LINE IT ANSWERS (the owner, 2026-11-10: the clock runs from the press and never
// restarts): a coding agent's first step comes seconds after the press its adapter took to start, and its head read "ran 2s" after "ran 9s"; a mail
// that joined mid-turn is newer than the turn and never sets it back. ms, or null
export const turnFrom = (since, line) => { const ms = [since, line].map((t) => (t == null ? NaN : +new Date(t))).filter(Number.isFinite);
  return ms.length ? Math.min(...ms) : null; };
export const turnBegan = (times) => (times || []).reduce((a, t) => { const ms = +new Date(t ?? NaN); return Number.isFinite(ms) && (a == null || ms > a) ? ms : a; }, null);
export const turnStamp = ({ running, start, end, now }) => {
  const t0 = +new Date(start || NaN), t1 = +new Date((running ? now : end) || NaN), ms = t1 - t0;
  if (!Number.isFinite(ms) || ms < 0 || ms >= 6 * 3600 * 1000) return "";
  return running ? `working ${clockText(ms)}` : ms > 0 ? `ran ${tookText(ms)}` : "";
};

// The Assistant's answer being written: a real brain took 4-51 s behind three silent dots, which read as hung (the owner, 2026-10-20:
// "working... Ns"). Nothing in the first second - most answers are back by then - and whole seconds after it, floored so it never jumps ahead.
export const workingLine = (ms) => (ms >= 1000 ? `Working… ${elapsedText(Math.floor(ms / 1000) * 1000)}` : "");
