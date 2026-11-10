// The landing card's words (LandingCard.jsx), apart from React so a node test reads them.
import { plural as n } from "./timeWords.js";
import { generated } from "./diffView.js";

export const HOW = { rebase: "Rebase and fast-forward", merge: "Merge commit", pr: "Open a PR", discard: "Discard", push: "Push", deploy: "Push & deploy" };

// ...AND WHAT A PRESS DID, said on the button it took (the card stays in its turn - the owner, 2026-11-09: "compact the land")
export const DONE = { rebase: "Rebased", merge: "Merged", pr: "PR opened", discard: "Discarded", push: "Pushed", deploy: "Pushed and deployed" };

export function landingWords(s) {
  if (!s) return {};
  const stat = `${n(s.changed || 0, "file")} changed, +${s.plus || 0} −${s.minus || 0}`
    + (s.own ? ` · ${n(s.ahead || 0, "commit")} ahead` : s.commits ? ` · ${n(s.commits, "commit")} of its own` : "");
  const p = s.proposal;
  return {
    stat,
    proposal: p?.how ? `The agent proposes ${HOW[p.how] || p.how}${p.deploy && p.how === "deploy" ? ` to ${p.deploy}` : ""}${p.why ? ` — ${p.why}` : ""}.` : "",
    hint: s.push ? `Never forced: if origin/${s.base} moved, nothing is pushed and the card says why.` : s.own ? "A conflict lands nothing: the agent gets it to resolve. Open a PR pushes the branch and opens a draft." : "",
    // WORK ON THE SHARED BASE IS A PUSH, ASKED WITH BUTTONS (the owner, 2026-11-09: "i thought actions should be cards/buttons??? why is this
    // text??"): the commits origin has not got, up to which, and where Push & deploy sends them too
    question: s.push ? `Push ${n(s.push.ahead || 0, "commit")} to origin/${s.base}, up to ${String(s.push.tip || "").slice(0, 7)}`
      + (s.push.deploy ? `, and deploy it to ${s.push.deploy}?` : "?") : "How should it land?",
    // the button the press most likely is: the agent's pick, else - on the shared base - the furthest the work can go
    primary: p?.how && (s.answers || []).some((a) => a.how === p.how) ? p.how : s.push ? (s.answers || []).at(-1)?.how || "" : "",
    landed: s.landed ? `Landed · ${HOW[s.landed.how] || s.landed.how}${s.landed.deploy ? ` to ${s.landed.deploy}` : ""}` : "",
    // ...ON A BRANCH EVERYONE COMMITS TO, said: what it counts is this task's own commits and edits, never the branch's whole history since
    shared: s.shared ? `${s.base} is shared with other agents and releases - this counts only this task's own commits and edits.` : "",
    // ONE TITLE LINE (the owner, 2026-11-09: "compact the land"): what the press does and how big it is - the files fold behind Show the files
    title: landingTitle(s),
    // ...the second button: the other way a push goes, or on its own branch the next likeliest land
    first: firstHow(s, p), second: secondHow(s, p),
    done: s.landed ? `✓ ${DONE[s.landed.how] || HOW[s.landed.how] || s.landed.how}` : "",
    doneLine: s.landed ? [String(s.landed.sha || "").slice(0, 7), s.landed.deploy && s.landed.how === "deploy" ? `to ${s.base} and ${s.landed.deploy}` : s.landed.how === "push" ? `to ${s.base}` : ""]
      .filter(Boolean).join(" · ") : "",
  };
}

const files = (s) => n(s.changed || 0, "file");
function landingTitle(s) {
  const p = s.push;
  if (p && s.ask) return `Push ${n(p.ahead || 0, "commit")} to ${s.base}${p.deploy ? " and deploy" : ""} - ${files(s)}`;
  if (s.own && (s.ask || s.landed)) return `Land ${s.branch} into ${s.base} - ${n(s.commits || s.ahead || 0, "commit")}, ${files(s)}`;
  if (s.landed) return `${s.landed.how === "deploy" ? "Push and deploy" : "Push"} ${s.base} - ${files(s)}`;
  return `Worked on ${s.branch} - ${files(s)}`;
}
// ...the one filled button: the agent's pick, else the furthest a push goes, else the first way to land
function firstHow(s, p) { const hs = (s.answers || []).map((a) => a.how); return p?.how && hs.includes(p.how) ? p.how : s.push ? hs.at(-1) || "" : hs[0] || ""; }
function secondHow(s, p) { const f = firstHow(s, p); return (s.answers || []).map((a) => a.how).find((h) => h !== f && h !== "discard") || ""; }

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
