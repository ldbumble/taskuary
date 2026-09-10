// WHO is working, and what it has got so far - read off the session's own trace.
//
// The thing that does the work is an AGENT. "Assistant" is the thing that helps you run Taskuary,
// and the work window wore that word four times over - the strip, the view button, the composer,
// and "TASKUARY" as the speaker of every turn - while a real agent searched the web (the owner,
// 2026-09-08: "it should be agent not assistant. Assistant is what helps you run taskuary. agents
// are what do work"). Where the window named anything at all it named a binary and a profile:
// "Agent running · Claude Code · coder (your CLI)".
//
// Nothing here asks the server for anything new. The trace is already on the assistant payload and
// the name is already on the task, so an agent that reads as working needs no new endpoint.
import { assignedAgent } from "./agentIdentity.js";
import { toolTarget } from "./assistantStream.js";

// Until a roster of named specialists exists, the kind of work IS the name - which is the same
// thing triage already decided. A worker explicitly assigned to the task outranks it.
export const KIND_NAME = { research: "Research", marketing: "Marketing", triage: "Triage",
                           setup: "Set-up", coding: "Coder", general: "Agent", assistant: "Agent" };
export const agentName = (task) => assignedAgent(task?.Assignee)
  || KIND_NAME[String(task?.Kind || "").toLowerCase()] || "Agent";

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
export const saidFromTail = (tail) => (tail || [])
  .map((line) => String(line).replace(/^\s*(?:assistant|you)>\s*/i, "").trim())
  .filter(Boolean).pop() || "";

// The trail as a COUNT. A finished tool call is history, and six of them are six rectangles of
// history stacked in front of the one thing that is happening.
export const trailText = (work) => [
  work?.searches?.length && `${work.searches.length} search${work.searches.length === 1 ? "" : "es"}`,
  work?.reads?.length && `${work.reads.length} page${work.reads.length === 1 ? "" : "s"} read`,
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
