// THE ACTION ROW'S VERBS (layout B, 2026-09-30): the item on the table no longer wears its buttons - it REGISTERS them here and the
// one row above the chat line (ActionRow.jsx) draws them, in the same place for every item. A verb is the card's own handler,
// unchanged: the row calls the LATEST one, so a press costs what the old button cost and nothing in the card re-renders for it.
// Only a change in what the row SHOWS (a label, a disabled flag, a verb arriving or going) wakes the row; a fresh closure does not.
import React, { useEffect, useId, useSyncExternalStore } from "react";
import { label, liveVerb, verbOfRow } from "./buttons.js";

// verb: { id, label, group: "decide" | "agent" | "more" | "next", tone: "p" | "s" | "q", title, disabled, why, run(event, anchorEl) }
//   `why`: what a DISABLED verb is waiting for, said in the row itself ("write the reply first") - a greyed button that does not say why is a dead end
//   `blank`: what an advised move does now that the text it acts on is gone (the draft box emptied) - said in place of the line judged over it
const live = new Map();          // id -> the latest verb (its run closes over the freshest state)
const ofs = new Map();           // id -> the card that registered it: the item a button drawn from it was drawn for (press)
const owners = new Map();        // owner -> { verbs, ref }
const subs = new Set();
const view = (v) => ({ id: v.id, label: v.label, group: v.group, tone: v.tone || "s", title: v.title || "", disabled: !!v.disabled, why: v.why || "", ...(v.blank ? { blank: v.blank } : {}), promote: v.promote !== false, lead: !!v.lead, ...(v.closes ? { closes: true } : {}), ...(v.fill ? { fill: true } : {}), ...(v.beside ? { beside: true } : {}), ...(v.onCard ? { onCard: true } : {}), ...(v.card ? { card: true } : {}) });
let snap = { list: [], ref: "" }, sig = "";

export function put(owner, verbs, ref = "") {
  const old = owners.get(owner)?.verbs || [];
  old.forEach((v) => { if (live.get(v.id) === v) { live.delete(v.id); ofs.delete(v.id); } });   // not one a newer owner has since taken over
  if (verbs?.length) { owners.set(owner, { verbs, ref }); verbs.forEach((v) => { live.set(v.id, v); ofs.set(v.id, owner); }); } else owners.delete(owner);
  const all = [...owners.values()];
  // one button per id: two mounted copies of a card (each its own owner, see useVerbs) carry the same verbs
  // ...and each drawn button says which card it was drawn for (`of`), so its press acts on that card or on nothing (press)
  const seen = new Set(), list = [...owners].flatMap(([o, { verbs: vs }]) => vs.map((v) => [o, v]))
    .filter(([, v]) => !seen.has(v.id) && seen.add(v.id)).map(([o, v]) => ({ ...view(v), of: ofs.get(v.id) || o }));
  const next = { list, ref: all.map((o) => o.ref).find(Boolean) || "" }, s = JSON.stringify(next);
  if (s === sig) return;
  sig = s; snap = next; subs.forEach((f) => f());
}
// EVERY PRESS IS AN ACT THE ADVISOR MUST SEE (2026-10-19): its line was read when the item opened and never again, so after Send it
// still said the sender was waiting. Whoever shows advice hears each press once it settles (onPressed) and reads it again.
// A card's own button that acts without the row (the draft's Send under it) says so the same way: acted(id).
const pressed = new Set();
export const onPressed = (f) => { pressed.add(f); return () => pressed.delete(f); };
export const acted = (id) => pressed.forEach((f) => f(id));
// ...and BEFORE it runs, to whoever records what was lit against what was pressed (the deep dive, 2026-10-20): read after the press
// settled, the line had already moved on to the next item's
const pressing = new Set();
export const onPressing = (f) => { pressing.add(f); return () => pressing.delete(f); };
// ...a card's own button that acts without the row (the draft's Send, Redraft and Copy under it) is heard the same way, before it runs
// (phase B, 2026-10-23: they were never recorded). Told twice when the row ran it - the server keeps one
export const announce = (id) => pressing.forEach((f) => { try { f(id); } catch { /* a lost record never stops the press */ } });
// A PRESS ACTS ON THE ITEM ITS BUTTON WAS DRAWN FOR, OR ON NOTHING (2026-10-25): a double-click on Mark done closed two tasks - the second
// click landed on the same button after the close had drawn the next task up (drawNextEarly), and the row ran whatever verb now answered
// to "done": the next task's. `of`, the card the drawn button came from (the row passes it): another card's verb under the same id is
// not this press's. A press from the code itself (the Advisor's pick of a real button) names none and runs the verb there is.
export const press = (id, e, anchor, of = null) => {
  if (of && ofs.get(id) !== of) return undefined;
  announce(id);
  const out = live.get(id)?.run?.(e, anchor);
  Promise.resolve(out).catch(() => {}).then(() => acted(id));
  return out;
};
// THE CARD'S OWN MOVE, LIT WHERE IT STANDS: the Advisor's pick of a verb the card draws itself (a draft's Send) fills that button on
// the card - rowOf's `lit` - instead of a second Send pushed onto the bar (the row reshuffled when the advice landed, 2026-10-19)
let lit = "";
const litSubs = new Set();
export const lightOnCard = (id) => { if ((id || "") === lit) return; lit = id || ""; litSubs.forEach((f) => f()); };
export const useLit = () => useSyncExternalStore((f) => { litSubs.add(f); return () => litSubs.delete(f); }, () => lit);
export const rowNow = () => snap;          // what the row carries this moment - an Advisor press looks for its real button here
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
// Each mounted card registers as ITSELF: two copies under one name (a closed dialog and an open card, the opener and the chat)
// cleared each other's verbs on every put, every put re-drew both, and React gave up (#185 - issue 263, the UI audit 2026-10-21)
export function useVerbs(owner, verbs, on = true, ref = "") {
  const key = owner + useId();
  useEffect(() => { put(key, on ? verbs : null, ref); });
  useEffect(() => () => put(key, null), [key]);
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
// NOTHING IS DARK UNTIL THE ADVISOR ANSWERS (the owner, 2026-10-17: "nothing dark until advisor ... keep it ai"): the one filled
// button is the verb the Advisor advised for the item on the table. A card's own tone, Next, the first chip, Mark done when
// nothing else waits - every fallback of the row's own - is outlined. No advice, no dark button.
const ROOM = 4;                                            // how many chips the row holds before the rest wait behind More
const isDone = (v) => v.id === "done" || /:done$/.test(String(v.id));
// THE ADVISOR'S PICK (advisor.py, {verb, label}) as the row verb it names: the same id (the task registers `reply`, `continue`), the
// chip's own words, or the task's own id for the same act read off buttons.json's `row` lists - the Advisor's `close` is the row's
// `done`, `defer` its `remind`, `stop_agent` its `save-end` - so it fills the REAL button and never draws a second one beside it
// (it drew a second Reply on the strip, 2026-10-13). An old saved pick of a removed verb (`done`, `later`) lands on the live one.
const sameAct = (v, pick) => {
  const verb = liveVerb(pick?.verb);
  if (!verb) return false;
  const l = String(v.label || "").trim().toLowerCase(), want = String(pick?.label || "").trim().toLowerCase(), id = String(v.id || "");
  // ADVISED SEND IS A SEND: the draft's button keeps its `approve` id while it reads Redraft, Mark done or Checking delivery…,
  // and the line said "Send" over the one that was not (the Advisor audit, 2026-10-15)
  if (verb === "approve" && ![label("approve"), label("approve", "action")].some((w) => l === w.toLowerCase()) && !l.startsWith("send")) return false;
  return id === verb || id.endsWith(`:${verb}`) || verbOfRow(id) === verb || (!!want && l === want);
};
// ...the one on the bar before the card's own of the same act - the card's main move (it holds the bar's first slot, rowOf), then the
// row's own, then one only the card draws: the draft's Mark done (`<rid>:done`) was found first and lit on the card, a screen down,
// while the task's Mark done stood dark on the bar under a line saying "mark it done" (2026-10-19)
export const advisedIn = (list, pick) => {
  if (pick?.id) return list.find((v) => v.id === pick.id && !v.disabled) || null;     // a move named by its id (setup's own)
  const ok = (v) => !v.disabled && v.group !== "next" && sameAct(v, pick), main = (v) => v.card && v.group === "decide" && v.tone === "p";
  return pick?.verb ? list.find((v) => ok(v) && main(v)) || list.find((v) => ok(v) && !v.card) || list.find(ok) || null : null;
};
// the row's button for the advised act, greyed or not - a greyed one hides the line; none at all gives the line its own button
export const advisedAny = (list, pick) => (pick?.verb ? list.find((v) => v.group !== "next" && sameAct(v, pick)) || null : null);
// THE STRIP'S "<X> is off" LINE (AdvisorNext): a move the row has and has greyed says why, in the row's own words - but NOT while a press is in
// flight. The owner's own Send, Reply or Redraft greys the row's draft verbs while it runs (its label "Sending…", "Drafting…"), and the strip
// read that as the advised move being unavailable: "Drafting… is off - it cannot be pressed right now." for half a second after every
// Reply (the 2026-10-25 sweep). The press is not refused; the strip stays quiet until it lands.
// ...AND ONE GESTURE IS ONE PRESS: the second click of a double-click, or a press within ONE_PRESS_MS of the last, on ANOTHER item than
// that press was on is the same hand still moving - the item it lands on was drawn under it a moment ago, never read. Mark done, Next,
// Remind me and Close with a note all draw the next item at the press, so all of them would hand it the second click. `item`: the key of
// the item the press is on (AssistantView's gate reads it off the view under the pointer, else the table). True when it may act.
export const ONE_PRESS_MS = 350;
let lastPress = null;
export const aimed = (item, e = null, now = Date.now()) => {
  const l = lastPress;
  if (l && item !== l.item && (Number(e?.detail) > 1 || now - l.at < ONE_PRESS_MS)) return false;
  lastPress = { item, at: now };
  return true;
};
export const pressInFlight = (list) => (list || []).some((v) => v.busy || /…$/.test(String(v.label || "")));

// A `card` verb is one the card draws itself, under the draft (ReviewDecision): registered so the Advisor can find it, drawn here
// only when it is the advice. holdsMove: the card holds a move of its own under the draft (its filled button, or the task's Mark done
// standing on it) - what the Advisor's Why? names as "under the draft".
export const holdsMove = (list) => list.some((v) => v.onCard || (v.card && v.tone === "p"));
export function rowOf({ list, ref }, pick = null) {
  const by = (g) => list.filter((v) => v.group === g && !v.card);
  // the card's own idea of its move (its filled tone) only says which greyed button the row explains - it never fills one
  const head = by("decide").find((v) => v.tone === "p") || null;
  const plain = (xs) => xs.map((v) => (v.tone === "p" ? { ...v, tone: "s" } : v));
  // THE CARD'S MAIN MOVE LIVES UNDER THE DRAFT ONLY (the owner, 2026-10-22: Send under the draft, never the same press twice on
  // screen) - the bar's copy of it (2026-10-19) is gone, and so is the empty slot that kept its width (the owner, 2026-10-25: "we should
  // not have empty space here"). The row does not reshuffle without it: the bar is the same with and without advice, which only tints.
  // Advised, the Send is lit where it stands, on the card (`lit`).
  let decide = plain(by("decide")), more = plain(by("more")), agent = plain(by("agent"));
  // THE ADVISOR PICKS THE FILLED BUTTON (the owner, 2026-10-13: "the advisor should pick which button is dark based off its advice")
  // - AND ONLY TINTS IT, IN PLACE: the layout is the same with and without advice. A verb in More is filled where it stands
  // (clustersOf keeps the filled one in view); a card's other verb advised (its Redraft) is lit on the card (`lit`, useLit); Next is
  // filled when the Advisor's answer is that nothing here needs a move (words.json advice_none)
  const advised = advisedIn(list, pick), primary = advised ? { ...advised, tone: "p" } : null;
  if (advised && !advised.card) {
    const fill = (xs) => xs.map((v) => (v.id === advised.id ? primary : v));
    decide = fill(decide); agent = fill(agent); more = fill(more);
  }
  // ...WITH ONE EXCEPTION, the owner's (2026-10-20): while an agent is RUNNING its row's Stop and save is dark with no Advisor line -
  // the Advisor stays quiet over a working agent, and the one move there is ending it. A verb asks for that with `fill`; it is
  // marked `own` so the dead-end walk's DARK rule can tell it from the Advisor's
  // ...and only while the strip says NOTHING: under a line ("it says when it needs you", "Connect an AI") the line's own move is the lit
  // one, and a dark Stop and save beside it invited stopping an agent that needed nothing (the UI audit's C2, 2026-10-21; advice.stripWord)
  if (!advised && !pick) agent = agent.map((v) => (v.fill ? { ...v, tone: "p", own: true } : v));
  // MARK DONE IS ALWAYS ON THE BAR, beside Next - never behind More (the owner, 2026-10-06: "mark done should show next to next on every
  // single task not inside the more button"). With no decision waiting it leads the bar; dark only when it is the advice.
  const done = more.find((v) => v.id === "done");
  if (done) {
    more = more.filter((v) => v !== done);
    if (done.promote && !head && !agent.some((v) => v.lead)) decide = [done, ...decide];
    else agent = [...agent, done];
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
    const after = (xs) => { const i = xs.findIndex(isDone); return i < 0 ? null : [...xs.slice(0, i + 1), note, ...xs.slice(i + 1)]; };
    const d = after(decide), a = !d && after(agent);
    if (d) decide = d; else if (a) agent = a; else more = after(more) || [note, ...more];
  }
  // NO WORD TWICE: a card's decision and the task's own verbs can name the same act (a close-out's Remind me beside the task's, a
  // message card's Mark done beside the walk's). The first one placed stands; the bar outranks More.
  const seen = new Set();
  const once = (xs) => xs.filter((v) => v.slot || (seen.has(v.label) ? false : (seen.add(v.label), true)));   // an empty slot names nothing
  decide = once(decide); agent = once(agent); more = once(more);
  const next = by("next")[0] || null;
  if (decide.length > ROOM) { more = [...decide.slice(ROOM), ...more]; decide = decide.slice(0, ROOM); }   // the row stays a short line of chips; the rest wait behind More
  // a greyed decision says why it is greyed - the advised one never is (advisedIn skips greyed verbs), so the card's own move speaks
  return { ref, decide, agent, more, primary, lit: advised?.card ? advised.id : "", next: next && { ...next, tone: pick?.verb === "next" && !next.disabled ? "p" : "s" },
    why: head?.disabled && head.why ? `${head.label} is off - ${head.why}` : "" };
}

// THE ROW BY TYPE (the owner, 2026-10-13, canvas H2: "2 most common buttons per type and then down arrow for more on all of them"):
// what a button acts on - the reply, the agent, closing the task, the task itself - read off its id (a draft's own verbs are
// `<rid>:approve`, so the last part counts). A card's own words (a report's chip, a chat chip) are none of these:
// they lead, unlabelled. The order inside each type is rowOf's - the decision first - and its filled button is always in view.
export const TYPES = [["reply", "Reply"], ["agent", "Agent"], ["close", "Close"], ["task", "Task"]];
const TYPE_OF = {
  reply: "reply", approve: "reply", redraft: "reply", palt: "reply", reject: "reply", email: "reply", "ask-sender": "reply", hand: "reply", attach: "reply", "email-file": "reply", copy: "reply",
  "start-agent": "agent", "run-another": "agent", "strong-again": "agent", continue: "agent", "send-general": "agent", diff: "agent", "save-end": "agent",
  done: "close", "close-note": "close", reopen: "close",
  remind: "task", nat: "task", reshape: "task",
  // what the task's pills used to change (section 1's redesign, 2026-10-16): the pills read now, the row changes
  kind: "task", priority: "task", assign: "task", repo: "task",
  // the Advisor's moves a card has no button for join the row in their type (AdvisorNext), never beside the line (2026-10-16)
  chase: "reply", mine: "agent", answer_agent: "agent", coding_agent: "agent", regular_agent: "agent", rerun: "agent",
  elsewhere: "close", not_ours: "task", not_ours_sender: "task", not_ours_kind: "task", block_sender: "task",
  let_go: "task", defer: "task", split: "task", test_connection: "task",
  // the calendar's answers (calwrite.py) are what goes back: an invite's yes, no or other time, and a thread's meeting
  accept_invite: "reply", decline_invite: "reply", propose_time: "reply", find_time: "reply",
  // ...and a meeting's Prepare starts a researcher: an agent's verb (2026-10-25)
  prepare: "agent",
  // a result's Share (Share.jsx) stands in a band of its own at the row's end: it acts on the whole result, never on a reply or the task
  share: "share",
};
export const typeOf = (v) => TYPE_OF[String(v?.id || "").split(":").pop()] || "act";
// ON A PHONE (narrower than 600px, the owner, 2026-10-22): Next and the ONE move - the lit one, else the row's lead (its first decision,
// else its first session verb) - and every other button of every type behind one ▾. Four typed bands wrapped to four lines over the box.
// An empty slot is neither the move nor a menu item: it only holds the Send's width on a wide row.
export function phoneRow(row) {
  const all = [...row.decide, ...row.agent, ...row.more].filter((v) => !v.slot);
  const lead = all.find((v) => v.tone === "p") || row.decide.find((v) => !v.slot) || row.agent[0] || null;
  return { type: "phone", label: "", shown: lead ? [lead] : [], rest: all.filter((v) => v !== lead) };
}
export function clustersOf(row, keep = 2) {
  const all = [...row.decide, ...row.agent, ...row.more];
  return ["act", ...TYPES.map(([t]) => t), "share"].map((type) => {
    const vs = all.filter((v) => typeOf(v) === type);
    if (!vs.length) return null;
    const lead = vs.findIndex((v) => v.tone === "p");
    const shown = lead >= keep ? [...vs.slice(0, keep - 1), vs[lead]] : vs.slice(0, keep);
    return { type, label: (TYPES.find(([t]) => t === type) || [])[1] || "", shown, rest: vs.filter((v) => !shown.includes(v) && !v.slot) };
  }).filter(Boolean);
}

// THE ROW IS ONE LINE, AT EVERY WIDTH (the owner, 2026-10-23: "the buttons turned into 2 rows ... NEVER do that"): an agent stopped
// while its WhatsApp reply drafted put five typed groups on a desktop row, and the row wrapped. Nothing wraps now - groups FOLD into
// one ▾ at the row's end until the line fits: the lowest group first (Task, then Close, Agent, Reply, the card's own), the group
// holding the lit move last; with every group folded the row is the phone's - Next, the one move, one ▾. Next never folds.
// foldsOf: every layout from the widest (the typed groups) to the narrowest (phoneRow), each a list of groups for Cluster.
export function foldsOf(row) {
  const cs = clustersOf(row), ph = phoneRow(row), lead = ph.shown[0], holds = (g) => !!lead && g.shown.includes(lead);
  const order = [...cs.filter((g) => !holds(g)).reverse(), ...cs.filter(holds)], out = [cs];
  for (let k = 1; k < order.length; k++) {
    const gone = new Set(order.slice(0, k)), folded = cs.filter((g) => gone.has(g)).flatMap((g) => [...g.shown, ...g.rest]).filter((v) => !v.slot);
    // ...ONE ▾ at the row's end: the group standing beside the shared ▾ gives its own ▾'s buttons to it, first - two ▾ side by side
    // read as one button drawn twice
    const left = cs.filter((g) => !gone.has(g)), last = left.at(-1);
    out.push([...left.slice(0, -1), ...(last ? [{ ...last, rest: [] }] : []), { type: "more", label: "", shown: [], rest: [...(last?.rest || []), ...folded] }]);
  }
  out.push([ph].filter((g) => g.shown.length || g.rest.length));
  return out;
}
// a layout's width in px from measured parts (ActionRow reads them off a hidden copy of the row): `btn` by verb id, `label` by type,
// the ▾, Next, a group's side padding, the gap after its label, between its buttons, and between groups
export function rowWidth(groups, next, m) {
  const w = (v) => m.btn[v.id] ?? 0;
  const cl = (g) => {
    const n = g.shown.length + (g.rest.length ? 1 : 0);
    return m.pad + (g.label ? (m.label[g.type] ?? 0) + m.clGap : 0) + g.shown.reduce((a, v) => a + w(v), 0) + (g.rest.length ? m.more : 0) + m.bGap * Math.max(0, n - 1);
  };
  const parts = [...(next ? [m.pad + m.next] : []), ...groups.map(cl)];
  return parts.reduce((a, x) => a + x, 0) + m.rowGap * Math.max(0, parts.length - 1);
}
// the widest layout that fits `avail` (a phone starts at the phone's, 2026-10-22); `extra` steps further when the drawn row still
// overflows what was measured; nothing measured yet (a test render, no layout) is the widest
export function fitRow(row, m, avail, phone = false, extra = 0) {
  const all = foldsOf(row), last = all.length - 1, at = (i) => ({ groups: all[Math.min(last, i)], level: Math.min(last, i), last });
  if (!m || !(avail > 0)) return at((phone ? last : 0) + extra);
  for (let i = phone ? last : 0; i <= last; i++) if (rowWidth(all[i], row.next, m) <= avail) return at(i + extra);
  return { ...at(last), tight: true };
}

