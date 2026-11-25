// ONE CARD FOR A BULK JOB (taskuary/bulkcard.py; the owner, 2026-11-16: "For a job that is a bulk process you should be able to review a few of
// them and then send them all out ... On the bulk version, the send should show a progress bar in the action card"). The reading of it, kept
// apart from BulkCard.jsx so it is tested alone: a row in a line, the press's words, where the run stands.
import { actionFor } from "./actionCard.js";
import { proposalFrom } from "./reviewProposal.js";
import { plural } from "./timeWords.js";

const env = (r) => { try { return JSON.parse(r?.Deliver || "{}") || {}; } catch { return {}; } };
const one = (w) => String(w || "").split(/\r?\n/).map((x) => x.trim()).find(Boolean) || "";
// a row as the list shows it: whom or what it goes to, its one line, and what to check before the press
export const rowOf = (r) => {
  if (r.Kind !== "action") {
    const e = env(r), to = (Array.isArray(e.to) ? e.to : [e.to]).filter(Boolean).join(", ") || r.FromEmail || "";
    return { id: r.ReviewId, target: to, line: e.subject || one(r.DraftText), flags: (e.guessed || []).some((g) => to.includes(g)) ? ["address guessed"] : [] };
  }
  const p = proposalFrom(r) || {};
  const target = [p.repo && (p.number != null ? `${p.repo}#${p.number}` : p.repo), p.to, p.target].filter(Boolean).join(" · ");
  // ...an act that names nobody goes to its system, by the name its card has (a post: "LinkedIn") - never the tool's own id
  return { id: r.ReviewId, target: target || actionFor(p.type)?.title || p.type || p.action || "", line: one(p.title || p.comment || p.body || p.text || p.what || r.Reason), flags: [] };
};
// the press, by the act's own words: "Send 24 emails", "Close 37 issues" (a catalogue press of verb and noun), else "Approve all 5"
export const pressOf = (rows, n) => {
  const r = rows[0] || {};
  if (r.Kind !== "action") return `Send ${plural(n, "email")}`;
  const press = actionFor(proposalFrom(r)?.type)?.press || "", [verb, ...rest] = press.split(" ");
  return rest.length === 1 ? `${verb} ${plural(n, rest[0])}` : press ? `${press} - all ${n}` : `Approve all ${n}`;
};
// ...and what the card holds, by the same words: "24 emails", "30 issues", "6 posts" (a post's press names its network, its kind what it is),
// else "5 steps"
export const countOf = (rows) => {
  const r = rows[0] || {}, n = rows.length;
  if (r.Kind !== "action") return plural(n, "email");
  const act = actionFor(proposalFrom(r)?.type), rest = (act?.press || "").split(" ").slice(1);
  return plural(n, rest.length === 1 ? rest[0] : act?.kind === "post" ? "post" : "step");
};
const SET_ASIDE = "set aside when you moved on";
// where each row stands: done, failed (its error), left out, set aside as the chat moved on, or waiting
export const rowState = (r, run) => {
  const said = run?.rows?.[String(r.ReviewId)];
  if (said === "ok" || ["approved", "edited", "sent"].includes(r.Status)) return { done: true };
  if (said === "left") return { left: true };
  // ...a send that did not go still waits on the card (bulkcard.summary): once the run is over, ticked for the next press, its error beside it
  if (said) return r.Status === "pending" && !running(run) ? { waiting: true, failed: said } : { failed: said };
  if (r.Status === "superseded" && r.DecideNote === SET_ASIDE) return { aside: true };
  if (r.Status === "superseded" && r.ActError) return { failed: r.ActError };
  return r.Status === "pending" ? { waiting: true } : { left: true };
};
export const running = (run) => ["running", "cancelling"].includes(run?.state);
// the bar: what of this run is over, of its total
export const progress = (run) => (run?.total ? Math.round((100 * ((run.done || 0) + (run.failed || 0) + (run.left || 0))) / run.total) : 0);
// HOW TALL ITS ROWS STAND before they scroll in their own box: a long list of lines stays a short one; with a row OPEN to review, most of the
// window - a letter opened was cut half way down by the short cap, its second neighbour unseen (the card gallery, 2026-11-25)
export const listCap = (items) => ((items || []).some((x) => x.open) ? "min(80vh, 900px)" : 420);
