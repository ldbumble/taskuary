// THE ACTION ROW'S VERBS (layout B, 2026-09-30): the item on the table no longer wears its buttons - it REGISTERS them here and the
// one row above the chat line (ActionRow.jsx) draws them, in the same place for every item. A verb is the card's own handler,
// unchanged: the row calls the LATEST one, so a press costs what the old button cost and nothing in the card re-renders for it.
// Only a change in what the row SHOWS (a label, a disabled flag, a verb arriving or going) wakes the row; a fresh closure does not.
import React, { useEffect, useSyncExternalStore } from "react";

// verb: { id, label, group: "decide" | "agent" | "more" | "next", tone: "p" | "s" | "q", title, disabled, why, run(event, anchorEl) }
//   `why`: what a DISABLED verb is waiting for, said in the row itself ("write the reply first") - a greyed button that does not say why is a dead end
const live = new Map();          // id -> the latest verb (its run closes over the freshest state)
const owners = new Map();        // owner -> { verbs, ref }
const subs = new Set();
const view = (v) => ({ id: v.id, label: v.label, group: v.group, tone: v.tone || "s", title: v.title || "", disabled: !!v.disabled, why: v.why || "", promote: v.promote !== false, lead: !!v.lead, ...(v.closes ? { closes: true } : {}) });
let snap = { list: [], ref: "" }, sig = "";

export function put(owner, verbs, ref = "") {
  const old = owners.get(owner)?.verbs || [];
  old.forEach((v) => { if (live.get(v.id) === v) live.delete(v.id); });   // not one a newer owner has since taken over
  if (verbs?.length) { owners.set(owner, { verbs, ref }); verbs.forEach((v) => live.set(v.id, v)); } else owners.delete(owner);
  const all = [...owners.values()];
  const next = { list: all.flatMap((o) => o.verbs).map(view), ref: all.map((o) => o.ref).find(Boolean) || "" }, s = JSON.stringify(next);
  if (s === sig) return;
  sig = s; snap = next; subs.forEach((f) => f());
}
export const press = (id, e, anchor) => live.get(id)?.run?.(e, anchor);
const subscribe = (f) => { subs.add(f); return () => subs.delete(f); };
export const useRowVerbs = () => useSyncExternalStore(subscribe, () => snap);

// A PHONE'S TASK VIEW CARRIES THE ROW AT ITS OWN FOOT, in both states: the view is sized once (Expand pins that same box), so the
// row inside it must be there before and after Expand, or the pane would grow. While one is hosted the dock draws none.
let hosts = 0;
export const useHosted = () => useSyncExternalStore(subscribe, () => hosts > 0);
export function useHost(on) {
  useEffect(() => {
    if (!on) return undefined;
    hosts += 1; subs.forEach((f) => f());
    return () => { hosts -= 1; subs.forEach((f) => f()); };
  }, [on]);
}

// a card registers its verbs on every render (cheap: one stringify) and clears them when it goes; `ref` names the item they act on
export function useVerbs(owner, verbs, on = true, ref = "") {
  useEffect(() => { put(owner, on ? verbs : null, ref); });
  useEffect(() => () => put(owner, null), [owner]);
}

// A CARD'S OWN MOVE IS A <Button> IT DRAWS (Send, Answer, Open the connection...): read it once into a row verb - its label, its onClick,
// its disabled flag, its title - so the card draws no button of its own and the row carries it. The same handler runs; only the place changes.
const textOf = (n) => React.Children.toArray(n).map((c) => (typeof c === "string" || typeof c === "number" ? c : React.isValidElement(c) ? textOf(c.props.children) : "")).join("");
export function movesOf(node, group = "decide", prefix = "m") {
  const out = [];
  const walk = (n) => React.Children.forEach(n, (c) => {
    if (!React.isValidElement(c)) return;
    if (c.type === React.Fragment) return walk(c.props.children);
    const p = c.props, label = textOf(p.children).trim();
    if (!label || !(p.onClick || p.href)) return;
    out.push({ id: `${prefix}:${label}`, group, tone: p.variant === "contained" ? "p" : "s", label, title: p.title, disabled: !!p.disabled, why: p.disabled && p.title ? p.title : "",
      run: (e, anchor) => (p.onClick ? p.onClick({ currentTarget: anchor || e?.currentTarget }) : window.open(p.href, "_blank", "noopener")) });
  });
  walk(node);
  const first = out.findIndex((v) => v.tone === "p");
  return out.map((v, i) => (v.tone === "p" && i !== first ? { ...v, tone: "s" } : v));   // one filled button per card's move
}

// the row's layout, from the registered verbs: the decision first, the session's verbs, then the rest behind More.
// A task with no decision waiting has Mark done as its decision (unless a live session holds the page: that has no primary) - or, when
// the session's way back in leads, Mark done stands outlined beside it.
// ONE FILLED BUTTON AT MOST: Next is the filled one only when nothing else on the row is a move of its own.
export function rowOf({ list, ref }) {
  const by = (g) => list.filter((v) => v.group === g);
  let decide = by("decide"), more = by("more"), agent = by("agent");
  let primary = decide.find((v) => v.tone === "p") || null;
  // no decision waiting: the session's way back in (Continue session / Start an agent) is the move, else Mark done
  const lead = !primary && agent.find((v) => v.lead);
  if (lead) { agent = agent.map((v) => (v === lead ? { ...v, tone: "p" } : v)); primary = lead; }
  const done = more.find((v) => v.id === "done");
  if (done && done.promote && !primary) { primary = { ...done, tone: "p" }; decide = [primary, ...decide]; more = more.filter((v) => v !== done); }
  // ...and beside the way back in, not behind More: a closed session is as often finished as continued (the owner, 2026-10-01: "mark done
  // should not be inside the more"). Outlined, so the row still has one filled button. A waiting decision still sends it behind More.
  else if (done && done.promote && lead) { agent = [...agent, done]; more = more.filter((v) => v !== done); }
  // a decision that carries its own close (a reply draft's Mark done, 2026-10-01) is the task's Mark done - never twice in one row
  if (decide.some((v) => v.closes)) more = more.filter((v) => v.id !== "done");
  // Close with a note IS Mark done, with words: it stands right after Mark done wherever Mark done stands - the bar, beside the way
  // back into a session, or behind More (the owner, 2026-10-05: "why is close with note not inside the more.. menu but mark done is")
  const note = more.find((v) => v.id === "close-note");
  if (note) {
    more = more.filter((v) => v !== note);
    const after = (xs) => { const i = xs.findIndex((v) => v.id === "done"); return i < 0 ? null : [...xs.slice(0, i + 1), { ...note, tone: "s" }, ...xs.slice(i + 1)]; };
    const d = after(decide), a = !d && after(agent);
    if (d) decide = d; else if (a) agent = a; else more = after(more) || [note, ...more];
  }
  const next = by("next")[0] || null;
  if (decide.length > 4) { more = [...decide.slice(4), ...more]; decide = decide.slice(0, 4); }   // the row stays a short line of chips; the rest wait behind More
  return { ref, decide, agent, more, primary, next: next && { ...next, tone: primary ? "s" : "p" },
    why: primary?.disabled && primary.why ? `${primary.label} is off - ${primary.why}` : "" };
}
