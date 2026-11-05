// THE LINE OF A TOOL'S OUTPUT THAT SAYS WHAT WENT WRONG (the owner, 2026-11-05: a failed step "made no sense" when opened - a stack of tool
// text with no reason in front of it): the last line naming an error, a refusal or a missing thing, else its last line
const BAD = /error|exception|denied|refused|not found|no such|cannot|can't|failed|invalid|timed out|permission/i;
export const whyFailed = (detail) => {
  const ls = String(detail || "").split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
  const hit = [...ls].reverse().find((l) => BAD.test(l) && !/^(Traceback|at\s)/.test(l)) || ls.at(-1) || "";
  const line = hit.slice(0, 240);
  return line ? `Why: ${line}` : "It stopped without saying why.";
};
