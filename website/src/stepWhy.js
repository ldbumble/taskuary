// THE LINE OF A TOOL'S OUTPUT THAT SAYS WHAT WENT WRONG (the owner, 2026-11-05: a failed step "made no sense" when opened - a stack of tool
// text with no reason in front of it): the last line naming an error, a refusal or a missing thing, else its last line
// ...and of a Taskuary tool's step (`own`, agentSteps.ownTool) never the line its refusal gives the agent as the next step (NEXT_STEP,
// agenttools.NEXT_STEP: the same words): that line names tools and their fields for the agent, and the owner reads what happened - the line
// above it. Any other step's output is a program's own, and a line of it starting with those words is its own line, kept
import marks from "../../taskuary/nextstep.json" with { type: "json" };
export const NEXT_STEP = marks.next_step;
// ...ONE RULE FOR EVERY SURFACE THE OWNER READS A TOOL'S WORDS ON (the UI judge, 2026-11-18: the general road drew a refusal as a "⚠" note,
// whole, "⚠ there is no report 9 ⏎ Next: `report` is ..."): the step's Why line, the "⚠" note of a failed call, the record's. A kept result's
// line breaks may be the app's own mark (agents._result_text: " ⏎ ")
const LINES = new RegExp(`\\r?\\n|${marks.line_mark.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}`);
// ...and only its LAST line is the step: the tool writes no other (agenttools.steps_of quotes any line of other text that reads like one)
export const forOwner = (text, own = false) => {
  const s = String(text || ""), ls = s.split(LINES);
  return own ? (ls.at(-1).trim().startsWith(NEXT_STEP) ? ls.slice(0, -1) : ls).join("\n").trim() : s;
};
const BAD = /error|exception|denied|refused|not found|no such|cannot|can't|failed|invalid|timed out|permission/i;
export const whyFailed = (detail, own = false) => {
  const ls = forOwner(detail, own).split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
  const hit = [...ls].reverse().find((l) => BAD.test(l) && !/^(Traceback|at\s)/.test(l)) || ls.at(-1) || "";
  const line = hit.slice(0, 240);
  return line ? `Why: ${line}` : "It stopped without saying why.";
};
