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
const view = (v) => ({ id: v.id, label: v.label, group: v.group, tone: v.tone || "s", title: v.title || "", disabled: !!v.disabled, why: v.why || "", promote: v.promote !== false, lead: !!v.lead, ...(v.closes ? { closes: true } : {}), ...(v.beside ? { beside: true } : {}), ...(v.onCard ? { onCard: true } : {}) });
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
const ROOM = 4;                                            // how many chips the row holds before the rest wait behind More
const isDone = (v) => v.id === "done" || /:done$/.test(String(v.id));
// THE ADVISOR'S PICK (advisor.py, {verb, label}) as the row verb it names: the same id (the task registers `reply`, `continue`), the
// chip's own words, or the act behind them when the card words it differently - the advisor's Reply is the task's "Write reply"
// (it drew a second Reply on the strip, 2026-10-13), Mark done is its `close`, a draft's Send is its `approve`
// ...the same act under the card's own id: Remind me is the row's Snooze, ending the agent its End, a fresh agent its Start
const ALIAS = { defer: ["remind"], stop_agent: ["save-end"], regular_agent: ["start-agent", "send-general"] };
const sameAct = (v, pick) => {
  const l = String(v.label || "").trim().toLowerCase(), want = String(pick?.label || "").trim().toLowerCase(), id = String(v.id || "");
  // ADVISED SEND IS A SEND: the draft's button keeps its `approve` id while it reads Refresh the draft, Mark done or Checking
  // delivery…, and the line said "Send" over the one that was not (the Advisor audit, 2026-10-15)
  if (pick?.verb === "approve" && !l.startsWith("send") && !l.startsWith("run") && !l.startsWith("merge") && !l.startsWith("close")) return false;
  return id === pick?.verb || id.endsWith(`:${pick?.verb}`) || (want && l === want) || (pick?.verb === "close" && isDone(v))
    || (ALIAS[pick?.verb] || []).some((a) => id === a || id.endsWith(`:${a}`));
};
export const advisedIn = (list, pick) => (pick?.verb ? list.find((v) => !v.disabled && v.group !== "next" && sameAct(v, pick)) || null : null);
// the row's button for the advised act, greyed or not - a greyed one hides the line; none at all gives the line its own button
export const advisedAny = (list, pick) => (pick?.verb ? list.find((v) => v.group !== "next" && sameAct(v, pick)) || null : null);

export function rowOf({ list, ref }, pick = null) {
  const by = (g) => list.filter((v) => v.group === g);
  let decide = by("decide"), more = by("more"), agent = by("agent");
  // THE ADVISOR PICKS THE FILLED BUTTON (the owner, 2026-10-13: "the advisor should pick which button is dark based off its advice"):
  // the verb it advises is the one filled - off More and onto the bar if it waited there - and every other one is outlined
  const advised = advisedIn(list, pick);
  if (advised) {
    const fill = (xs) => xs.map((v) => (v.id === advised.id ? { ...v, tone: "p" } : v.tone === "p" ? { ...v, tone: "s" } : v));
    decide = fill(decide); agent = fill(agent);
    if (advised.group === "more") { more = more.filter((v) => v.id !== advised.id); agent = [{ ...advised, tone: "p" }, ...agent]; }
  }
  let primary = advised ? { ...advised, tone: "p" } : decide.find((v) => v.tone === "p") || null;
  // THE CARD ALREADY HOLDS THE MOVE (a waiting draft's Send & close, under the draft): the bar fills nothing, Next included -
  // two filled buttons on one screen leave the owner to work out which one is meant
  const onCard = !advised && list.some((v) => v.onCard);
  // no decision waiting: the session's way back in (Continue session / Start an agent) is the move, else Mark done
  const lead = !primary && !onCard && agent.find((v) => v.lead);
  if (lead) { agent = agent.map((v) => (v === lead ? { ...v, tone: "p" } : v)); primary = lead; }
  // MARK DONE IS ALWAYS ON THE BAR, beside Next - never behind More (the owner, 2026-10-06: "mark done should show next to next on every
  // single task not inside the more button"; before that it went behind More whenever a decision waited, or a live session left no room).
  // The move when nothing else is (filled); otherwise outlined, so the row keeps one filled button.
  const done = more.find((v) => v.id === "done");
  if (done) {
    more = more.filter((v) => v !== done);
    if (done.promote && !primary) { primary = { ...done, tone: "p" }; decide = [primary, ...decide]; }
    else agent = [...agent, { ...done, tone: "s" }];
  }
  // a decision that carries its own close (a reply draft's Mark done, 2026-10-01) is the task's Mark done - never twice in one row
  if (decide.some((v) => v.closes)) { more = more.filter((v) => v.id !== "done"); agent = agent.filter((v) => v.id !== "done"); }
  // Close with a note IS Mark done, with words: it stands right after Mark done wherever Mark done stands - the bar, beside the way
  // back into a session, or behind More (the owner, 2026-10-05: "why is close with note not inside the more.. menu but mark done is")
  const note = more.find((v) => v.id === "close-note");
  if (note) {
    more = more.filter((v) => v !== note);
    // ...ANY Mark done: a reply draft's own registers as `<rid>:done`, and the task's then steps aside (above) - matching only
    // "done" left Close with a note at the top of More while Mark done stood on the bar (the row inventory, 2026-10-05)
    const after = (xs) => { const i = xs.findIndex(isDone); return i < 0 ? null : [...xs.slice(0, i + 1), { ...note, tone: "s" }, ...xs.slice(i + 1)]; };
    const d = after(decide), a = !d && after(agent);
    if (d) decide = d; else if (a) agent = a; else more = after(more) || [note, ...more];
  }
  // NO WORD TWICE: a card's decision and the task's own verbs can name the same act (a close-out's Remind me beside the task's, a
  // message card's Mark done beside the walk's). The first one placed stands; the bar outranks More.
  const seen = new Set();
  const once = (xs) => xs.filter((v) => (seen.has(v.label) ? false : (seen.add(v.label), true)));
  decide = once(decide); agent = once(agent); more = once(more);
  const next = by("next")[0] || null;
  if (decide.length > ROOM) { more = [...decide.slice(ROOM), ...more]; decide = decide.slice(0, ROOM); }   // the row stays a short line of chips; the rest wait behind More
  return { ref, decide, agent, more, primary, next: next && { ...next, tone: primary || onCard ? "s" : "p" },
    why: primary?.disabled && primary.why ? `${primary.label} is off - ${primary.why}` : "" };
}

// THE ROW BY TYPE (the owner, 2026-10-13, canvas H2: "2 most common buttons per type and then down arrow for more on all of them"):
// what a button acts on - the reply, the agent, closing the task, the task itself - read off its id (a draft's own verbs are
// `<rid>:approve`, so the last part counts). A card's own words (a report's "Make a task", a chat chip) are none of these:
// they lead, unlabelled. The order inside each type is rowOf's - the decision first - and its filled button is always in view.
export const TYPES = [["reply", "Reply"], ["agent", "Agent"], ["close", "Close"], ["task", "Task"]];
const TYPE_OF = {
  reply: "reply", approve: "reply", redraft: "reply", palt: "reply", reject: "reply", email: "reply", "ask-sender": "reply", hand: "reply", attach: "reply",
  "start-agent": "agent", "run-another": "agent", continue: "agent", "send-general": "agent", diff: "agent", "save-end": "agent",
  done: "close", "close-note": "close", reopen: "close",
  remind: "task", nat: "task", reshape: "task",
  // what the task's pills used to change (section 1's redesign, 2026-10-16): the pills read now, the row changes
  kind: "task", priority: "task", assign: "task", repo: "task",
};
export const typeOf = (v) => TYPE_OF[String(v?.id || "").split(":").pop()] || "act";
export function clustersOf(row, keep = 2) {
  const all = [...row.decide, ...row.agent, ...row.more];
  return ["act", ...TYPES.map(([t]) => t)].map((type) => {
    const vs = all.filter((v) => typeOf(v) === type);
    if (!vs.length) return null;
    const lead = vs.findIndex((v) => v.tone === "p");
    const shown = lead >= keep ? [...vs.slice(0, keep - 1), vs[lead]] : vs.slice(0, keep);
    return { type, label: (TYPES.find(([t]) => t === type) || [])[1] || "", shown, rest: vs.filter((v) => !shown.includes(v)) };
  }).filter(Boolean);
}

// ONE WORD ON THE BAR (the owner, 2026-10-13: "the buttons look horrible with double words on one button"): the section's label
// names the noun - REPLY, AGENT, CLOSE, TASK - so the button is the verb. The full name rides in the hover text and in the
// section's menu, which can afford it. A label that says a state ("Drafting…", "Back Tue") is kept as it is.
const SHORT = {
  reply: "Draft", approve: "Send", redraft: "Redraft", email: "Share", hand: "Forward", "ask-sender": "Ask",
  continue: "Continue", "run-another": "New", "start-agent": "Start", "send-general": "Start", "save-end": "End", diff: "Changes",
  done: "Done", "close-note": "Note", reopen: "Reopen", remind: "Snooze", nat: "Dismiss", reshape: "Split",
  kind: "Who", priority: "Priority", assign: "Assign", repo: "Repo",
};
export const shortLabel = (v) => {
  const label = String(v?.label || "");
  if (/…$/.test(label) || /^Back /.test(label)) return label;
  return SHORT[String(v?.id || "").split(":").pop()] || label;
};
