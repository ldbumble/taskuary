// The landing card's words (LandingCard.jsx), apart from React so a node test reads them.
import { plural as n } from "./timeWords.js";
import { generated } from "./diffView.js";

export const HOW = { rebase: "Rebase and fast-forward", merge: "Merge commit", pr: "Open a PR", discard: "Discard" };

export function landingWords(s) {
  if (!s) return {};
  const stat = `${n(s.changed || 0, "file")} changed, +${s.plus || 0} −${s.minus || 0}`
    + (s.own ? ` · ${n(s.ahead || 0, "commit")} ahead` : s.commits ? ` · ${n(s.commits, "commit")} of its own` : "");
  const p = s.proposal;
  return {
    stat,
    proposal: p?.how ? `The agent proposes ${HOW[p.how] || p.how}${p.why ? ` — ${p.why}` : ""}.` : "",
    hint: s.own ? "A conflict lands nothing: the agent gets it to resolve. Open a PR pushes the branch and opens a draft." : "",
    landed: s.landed ? `Landed · ${HOW[s.landed.how] || s.landed.how}` : "",
    // ...ON A BRANCH EVERYONE COMMITS TO, said: what it counts is this task's own commits and edits, never the branch's whole history since
    shared: s.shared ? `${s.base} is shared with other agents and releases - this counts only this task's own commits and edits.` : "",
  };
}

// THE CARD'S FILE LIST, AS THE DIFF VIEW ORDERS IT: the source first, the generated files (a build's bundles, lock files) apart, folded
export const landingFiles = (files) => ({ src: (files || []).filter((f) => !generated(f.path)), gen: (files || []).filter((f) => generated(f.path)) });

// WHICH TURN THE LANDING CARD IS PART OF: the agent's turn its newest change came in - the last that began at or before it (`at`, landing.state) -
// else the newest. null with no agent turn yet: the card waits at the chat's foot
const stamp = (x) => String(x || "").replace("T", " ").slice(0, 19);
export function landingTurn(messages, at) {
  const turns = (messages || []).filter((m) => m?.role === "assistant" && m.id);
  if (!turns.length) return null;
  const by = at ? turns.filter((m) => m.createdAt && stamp(m.createdAt) <= stamp(at)).at(-1) : null;
  return (by || turns.at(-1)).id;
}
