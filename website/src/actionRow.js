// THE ACTION ROW'S VERBS (layout B, 2026-09-30): the item on the table no longer wears its buttons - it REGISTERS them here and the
// one row above the chat line (ActionRow.jsx) draws them, in the same place for every item. A verb is the card's own handler,
// unchanged: the row calls the LATEST one, so a press costs what the old button cost and nothing in the card re-renders for it.
// Only a change in what the row SHOWS (a label, a disabled flag, a verb arriving or going) wakes the row; a fresh closure does not.
import React, { createContext, useContext, useEffect, useId, useRef, useState, useSyncExternalStore } from "react";
import { label, liveVerb, verbOfRow } from "./buttons.js";

// verb: { id, label, group: "decide" | "agent" | "more" | "next" | "back", tone: "p" | "s" | "q", title, disabled, why, run(event, anchorEl) }
//   `why`: what a DISABLED verb is waiting for, said in the row itself ("write the reply first") - a greyed button that does not say why is a dead end
//   `blank`: what an advised move does now that the text it acts on is gone (the draft box emptied) - said in place of the line judged over it
const live = new Map();          // id -> the latest verb (its run closes over the freshest state)
const ofs = new Map();           // id -> the card that registered it: the item a button drawn from it was drawn for (press)
const owners = new Map();        // owner -> { verbs, ref, at }
const subs = new Set();
const view = (v) => ({ id: v.id, label: v.label, group: v.group, tone: v.tone || "s", title: v.title || "", disabled: !!v.disabled, why: v.why || "", ...(v.blank ? { blank: v.blank } : {}), promote: v.promote !== false, lead: !!v.lead, ...(v.closes ? { closes: true } : {}), ...(v.fill ? { fill: true } : {}), ...(v.beside ? { beside: true } : {}), ...(v.onCard ? { onCard: true } : {}), ...(v.card ? { card: true } : {}), ...(v.steady ? { steady: true } : {}), ...(v.tucked ? { tucked: true } : {}), ...(v.spine ? { spine: v.spine } : {}), ...(v.laid ? { laid: v.laid } : {}) });
let snap = { list: [], ref: "" }, sig = "";
// THE WALK'S TWO WAYS, ONE PILL (the owner, 2026-10-27: "We have a Next button - let's have a Back button that goes up the line as well ...
// on the first one no Back, like no Next on the last one. Combine Next/Back into one big pill called Nav"): Back is the walk's step up the
// rail's line (AssistantView registers it, `BACK`, group "back"); Next is the cards' own, as before. `end`: the walk's own selection for
// the item on the table names nothing below it - the last one - and the row draws no Next there (setup's and the floor's are not the walk's)
export const BACK = "nav:back";
export const walkMove = (id) => /(^|:)next$/.test(String(id || "")) || id === BACK;   // a move along the walk: it moves the table, and acts on no item
let end = false;
export const navEnd = (on) => { if (!!on === end) return; end = !!on; draw(); };

export function put(owner, verbs, ref = "", at = null) {
  const old = owners.get(owner)?.verbs || [];
  old.forEach((v) => { if (live.get(v.id) === v) { live.delete(v.id); ofs.delete(v.id); } });   // not one a newer owner has since taken over
  if (verbs?.length) { owners.set(owner, { verbs, ref, at }); verbs.forEach((v) => { live.set(v.id, v); ofs.set(v.id, owner); }); } else owners.delete(owner);
  draw();
}
// THE ROW DRAWS ONLY THE TABLE'S OWN VERBS (the owner, 2026-10-26: "fix switching tasks thing of course"): a card's verbs went only when
// its cleanup ran, so the row wore the old task's Send and Redraft after the switch had begun. A card's verbs carry the table key they
// were registered for (`at`, TableVerbs), and the moment the table names another item they are not drawn - whether or not the old card
// has unmounted yet. Verbs of no item (Next, the chat's chips, setup) are always drawn.
// ...and from the PRESS that moves the table on (`leaving`, AssistantView.surface): the old item stays up the ~100 ms the pull takes,
// and its Send under a ring already on the next row read as the next one's. A press that fails gives them back (leaveRow(null)).
let table = null, leaving = null;
export const rowTable = (key) => { if ((key || null) === table) return; table = key || null; draw(); };
export const leaveRow = (key) => { if ((key || null) === leaving) return; leaving = key || null; draw(); };
const shows = ({ at }) => !at || ((!table || at === table) && at !== leaving);
function draw() {
  const shown = [...owners].filter(([, o]) => shows(o));
  // one button per id: two mounted copies of a card (each its own owner, see useVerbs) carry the same verbs
  // ...and each drawn button says which card it was drawn for (`of`), so its press acts on that card or on nothing (press)
  const seen = new Set(), mine = new Set(shown.map(([o]) => o)), list = shown.flatMap(([o, { verbs: vs, at }]) => vs.map((v) => [o, v, at]))
    .filter(([, v]) => !seen.has(v.id) && seen.add(v.id))
    .map(([o, v, at]) => ({ ...view(v), of: mine.has(ofs.get(v.id)) ? ofs.get(v.id) : o, ...(at ? { at } : {}) }));
  const next = { list, ref: shown.map(([, o]) => o.ref).find(Boolean) || "", ...(end ? { end } : {}) }, s = JSON.stringify(next);
  if (s === sig) return;
  sig = s; snap = next; subs.forEach((f) => f());
}
// THE ROW DRAWS ONCE (the owner, 2026-10-27: "I reopened a task and there were no buttons on the bottom, then it reloaded the buttons ...
// not to load then reload"). A new item's row came up in steps, recorded per frame (browser/row-draws-once): the press dropped the old
// item's verbs and left Next alone and greyed; the new card's verbs arrived; the row went hidden while the Advisor read the item (up to
// 400 ms); then it came back, and changed once more when the lit verb landed and reshuffled it. Reopen drew the open task's verbs off a
// local guess, then the re-read's, then the Advisor's Reply. Now the row the owner was looking at STAYS drawn, as it was, its presses
// inert, until the new row is whole - the item's card has registered its verbs, the walk move is over and the Advisor's read made after
// the change is in - or ROW_HOLD_MS has gone by. Then the new row is drawn in one step. Never an empty row, never a greyed interim.
export const ROW_HOLD_MS = 600, ROW_STUCK_MS = 1500;   // ...and whatever is up, never longer than ROW_STUCK_MS
// ready: nothing on the table and nothing being left - or an item on it that is not the one being left, with verbs of its own on the
// row, no walk move under way (`moving`: its answer still decides what is lit) and the Advisor's read of it (`read`: {key, round}, the
// press round it was made in) made after the last press on it (`round`)
export const rowReady = ({ key = null, leaving = null, moving = false, read = null, round = 0, list = [], keyed = true }) =>
  !moving && rowDrawable({ key, leaving, list, keyed }) && (!key || (read?.key === key && (read.round || 0) >= round));
// ...and what the row may be drawn as when the wait runs out: the item's own verbs up, none of the one being left - never a lone Next
// between two items. A task's view registers its verbs under its table key (`keyed`, TableVerbs); a report's, a batch's or a message's
// card registers none, so there any verb but the floor's is the item's
export const rowDrawable = ({ key = null, leaving = null, list = [], keyed = true }) => (!key ? !leaving : key !== leaving
  && (keyed ? list.some((v) => v.at === key) : list.some((v) => !v.at && !String(v.id).startsWith("floor:") && v.id !== BACK)));
// the hold, numbered (0: none): from each change of `sig` - the table, the item being left, the press round - until ready and the row's
// buttons (`shape`: what the live row would draw) have stood still ROW_QUIET_MS - an item's own reads land a beat apart (a meeting's
// answers after its task) - and once let go it stays let go for that change (a card re-registering its verbs is not a new item). The
// wait is capped where it shows: ActionRow draws the live row ROW_HOLD_MS after the new item's own verbs are up
export const ROW_QUIET_MS = 120;
export function useRowHold(sig, ready, shape = "") {
  const at = useRef({ sig: null, n: 0 }), freed = useRef(0), still = useRef({ shape: null, t: 0 }), [, wake] = useState(0);
  if (at.current.sig !== sig) at.current = { sig, n: at.current.n + 1 };
  const now = performance.now();
  if (still.current.shape !== shape) still.current = { shape, t: now };
  const quiet = now - still.current.t >= ROW_QUIET_MS, n = at.current.n, holding = freed.current !== n;
  useEffect(() => {
    if (!holding || !ready || quiet) return undefined;
    const t = setTimeout(() => wake((k) => k + 1), ROW_QUIET_MS - (performance.now() - still.current.t) + 1);
    return () => clearTimeout(t);
  });
  if (ready && quiet) freed.current = n;
  return freed.current === n ? 0 : n;
}
// ...while it holds, the row drawn follows the live one only where they are the same buttons for the same item - a label turned to its
// busy word ("Reopening…"), a flag - so the press still answers at once
export const sameRow = (a, b) => { const ids = (r) => (r?.list || []).map((v) => `${v.id}@${v.at || ""}`).join("|") + (r?.end ? "|end" : ""); return ids(a) === ids(b); };
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
// ...and ONE AT A TIME (the overnight walk, 2026-10-27; the owner, 2026-10-26: "if you click a button twice it won't [do the work twice]"):
// a double-click on Accept drafted the calendar's answer twice - the verb's own handler had no busy of its own. A verb whose run is still
// answering is not run again for the same card; a run that never answers lets go after FLIGHT_MS. Next keeps the walk's own rules
// for a press over a press
const flying = new Map(), FLIGHT_MS = 30000;
export const press = (id, e, anchor, of = null) => {
  // ...the verb of THAT card: one put down a moment ago may still be mounted, registering the same id after it (rowTable) - and the
  // code's own press runs the one the row draws, not the one put down
  const by = of || snap.list.find((x) => x.id === id)?.of;
  const v = by && ofs.get(id) !== by ? owners.get(by)?.verbs.find((x) => x.id === id) : live.get(id);
  if (of && !v) return undefined;
  const k = `${by || ""}|${id}`;
  if (Date.now() - (flying.get(k) ?? -Infinity) < FLIGHT_MS) return undefined;
  announce(id);
  const out = v?.run?.(e, anchor);
  if (typeof out?.then === "function" && v?.group !== "next") flying.set(k, Date.now());
  Promise.resolve(out).catch(() => {}).then(() => { flying.delete(k); acted(id); });
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
const AtTable = createContext(null);
export const TableVerbs = AtTable.Provider;    // value: the table key of the item the cards inside it draw for (CanvasItem)
export function useVerbs(owner, verbs, on = true, ref = "") {
  const key = owner + useId(), at = useContext(AtTable);
  useEffect(() => { put(key, on ? verbs : null, ref, at); });
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
  const ok = (v) => !v.disabled && v.group !== "next" && v.group !== "back" && sameAct(v, pick), main = (v) => v.card && v.group === "decide" && v.tone === "p";
  return pick?.verb ? list.find((v) => ok(v) && main(v)) || list.find((v) => ok(v) && !v.card) || list.find(ok) || null : null;
};
// the row's button for the advised act, greyed or not - a greyed one hides the line; none at all gives the line its own button
export const advisedAny = (list, pick) => (pick?.verb ? list.find((v) => v.group !== "next" && v.group !== "back" && sameAct(v, pick)) || null : null);
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
  // ...a press with nothing on the table (Walk me through my tasks, the opener's own buttons) was aimed at no item, so what comes up after
  // it was never drawn under another item's press: the walk's first Next is the owner's (walk-again-last-task, 2026-10-25)
  if (l?.item && item !== l.item && (Number(e?.detail) > 1 || now - l.at < ONE_PRESS_MS)) return false;
  lastPress = { item, at: now };
  return true;
};
export const pressInFlight = (list) => (list || []).some((v) => v.busy || /…$/.test(String(v.label || "")));

// A `card` verb is one the card draws itself, under the draft (ReviewDecision): registered so the Advisor can find it, drawn here
// only when it is the advice. holdsMove: the card holds a move of its own under the draft (its filled button, or the task's Mark done
// standing on it) - what the Advisor's Why? names as "under the draft".
export const holdsMove = (list) => list.some((v) => v.onCard || (v.card && v.tone === "p"));
export function rowOf({ list, ref, end: last = false }, pick = null) {
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
  // ...on the last item no Next (the walk's own; setup's Back and Next, and the floor's, are not the walk's), and Back beside it
  const next = by("next").find((v) => !(last && v.id === "next")) || null, back = by("back")[0] || null;
  if (decide.length > ROOM) { more = [...decide.slice(ROOM), ...more]; decide = decide.slice(0, ROOM); }   // the row stays a short line of chips; the rest wait behind More
  // a greyed decision says why it is greyed - the advised one never is (advisedIn skips greyed verbs), so the card's own move speaks
  return { ref, decide, agent, more, primary, lit: advised?.card ? advised.id : "", next: next && { ...next, tone: pick?.verb === "next" && (!next.disabled || next.steady) ? "p" : "s" },
    back: back && { ...back, tone: "s" },
    why: head?.disabled && head.why ? `${head.label} is off - ${head.why}` : "" };
}

// THE ROW IN THREE (the owner, 2026-10-28): Nav, then ONE pill of the moves that finish or advance this item - Mark done, the agent's move
// (Send to agent, Continue, Run another agent), the reply's (Reply, Send, Find a time, Accept) and a card's own words - as many in view as
// the width holds, the rest of their family (Close with a note, Hand it to a person, Copy) behind the pill's ▾; then the moves that CHANGE
// the task (Remind me, Not a task, Split or merge, its kind and owner) in a small pill of their own. The small-caps REPLY / AGENT / CLOSE
// words are gone: the moves say what they are. What a button acts on is still read off its id (a draft's own verbs are `<rid>:approve`,
// so the last part counts) - it says which pill, and where in it.
export const TYPES = [["move", ""], ["change", "Change"]];
export const NAV = "Nav";                 // the pill Back and Next share, labelled like the types
const TYPE_OF = {
  reply: "reply", approve: "reply", redraft: "reply", palt: "reply", reject: "reply", email: "reply", hand: "reply", attach: "reply", "email-file": "reply", copy: "reply",
  "start-agent": "agent", "run-another": "agent", "strong-again": "agent", continue: "agent", "send-general": "agent", diff: "agent", "save-end": "agent",
  done: "close", "close-note": "close", reopen: "close",
  remind: "task", nat: "task", reshape: "task",
  // what the task's pills used to change (section 1's redesign, 2026-10-16): the pills read now, the row changes
  kind: "task", priority: "task", assign: "task", repo: "task",
  // the Advisor's moves a card has no button for join the row in their type (AdvisorNext), never beside the line (2026-10-16)
  chase: "reply", mine: "agent", answer_agent: "agent", coding_agent: "agent", regular_agent: "agent", rerun: "agent",
  elsewhere: "close", not_ours: "task", not_ours_sender: "task", not_ours_kind: "task", block_sender: "task",
  let_go: "task", defer: "task", split: "task", test_connection: "task", report_off: "task",
  // the calendar's answers (calwrite.py) are what goes back: an invite's yes, no or other time, and a thread's meeting
  accept_invite: "reply", decline_invite: "reply", propose_time: "reply", find_time: "reply",
  // ...and a meeting's Prepare starts a researcher: an agent's verb (2026-10-25)
  prepare: "agent",
  // a result's Share (Share.jsx) stands in a band of its own at the row's end: it acts on the whole result, never on a reply or the task
  share: "share",
};
export const typeOf = (v) => TYPE_OF[String(v?.id || "").split(":").pop()] || "act";
// THE ROW'S LEAD: the lit move, else its first decision, else its first session verb - in view at every width.
// `pressable`: on the narrowest row the lead is never a greyed one (the owner, 2026-10-28: a phone's one move was a disabled "Send to agent") -
// the lit move stays (its busy word is its state), any other is the first pressable one, and with none it is the ▾ alone.
// An empty slot is neither a move nor a menu item: it only holds the Send's width on a wide row.
export const leadOf = (row, pressable = true) => {
  const ok = (v) => !v.slot && !(pressable && v.disabled);
  return [...row.decide, ...row.agent, ...row.more].find((v) => v.tone === "p" && !v.slot) || row.decide.find(ok) || (pressable ? row.agent.find(ok) : row.agent[0]) || null;
};
// MARK DONE IS NEVER FOLDED (the owner, 2026-10-28: "You should not have Mark done ever hidden"): a sent reply's row showed Reply and Hand it to
// a person and kept Mark done behind the ▾. Every layout keeps it in view, first in its pill, and the other moves fold round it
export const pinOf = (row) => [...row.decide, ...row.agent, ...row.more].find((v) => isDone(v) && !v.slot) || null;
// the two pills' moves, each in the order they give up their place: the move pill's heads (Mark done, the agent's, the reply's, a card's own
// words) before the rest of their families; a `tucked` move (a sent reply's Hand it to a person: the reply went, Reply is all it needs) is
// never in view unless it is lit
export function pillsOf(row) {
  const all = [...row.decide, ...row.agent, ...row.more].filter((v) => !v.slot), pin = pinOf(row), of = (t) => all.filter((v) => typeOf(v) === t);
  const head = (vs) => { const up = vs.filter((v) => !v.tucked || v.tone === "p"); return up.find((v) => v.tone === "p") || up.find((v) => v.lead) || up[0]; };
  const cl = of("close").filter((v) => v !== pin), ag = of("agent"), rp = of("reply");
  const move = [...new Set([pin || head(cl), head(ag), head(rp), ...of("act"), ...rp, ...ag, ...cl].filter(Boolean))];
  const rank = (v) => { const i = CHANGE_FIRST.indexOf(String(v.id).split(":").pop()); return i < 0 ? CHANGE_FIRST.length : i; };
  // ...a result's Share (Share.jsx) keeps its own small band at the row's end: it acts on the whole result, never on a reply or the task
  return { move, share: of("share"), change: of("task").map((v, i) => [v, i]).sort((a, b) => rank(a[0]) - rank(b[0]) || a[1] - b[1]).map(([v]) => v), pin, lead: leadOf(row), held: leadOf(row, false) };
}
// ...the Change pill's most used first (the owner's list, 2026-10-28: split / merge / not a task / Remind me - Remind me the one pressed most)
const CHANGE_FIRST = ["remind", "defer", "reshape", "split", "nat"];
// a pill with `n` of its moves in view: `must` first claims its places, the rest go by the pill's order; drawn in that order
const pill = (type, vs, n, must) => {
  const can = vs.filter((v) => !v.tucked || v.tone === "p"), keep = new Set(must.filter((v) => vs.includes(v)));
  for (const v of can) { if (keep.size >= n) break; keep.add(v); }
  return { type, label: (TYPES.find(([t]) => t === type) || [])[1] || "", shown: vs.filter((v) => keep.has(v)), rest: vs.filter((v) => !keep.has(v)) };
};
// the narrowest row: Nav, Mark done, the lead, and every other move of both pills behind one ▾
export const phoneRow = (row) => foldsOf(row).at(-1)?.[0] || { type: "move", label: "", shown: [], rest: [] };
// the widest layout, as groups for Cluster: every move in view
export const clustersOf = (row) => foldsOf(row)[0];

// THE ROW IS ONE LINE, AT EVERY WIDTH (the owner, 2026-10-23: "the buttons turned into 2 rows ... NEVER do that"). Nothing wraps - moves FOLD
// into their pill's ▾ until the line fits: the Change pill's first, down to its ▾ alone, then the move pill's from its end - never Mark done,
// never the lit or leading move ("curious to see if we can fit more", 2026-10-28: as many moves in view as the width holds). Narrower still,
// the Change pill joins the move pill's ▾ - one ▾ - and the move pill gives up its moves again down to Mark done and the lead: the phone's
// row (it starts there: one ▾ on a phone, as many moves as fit). Nav (Back, Next) never folds.
// foldsOf: every layout from the widest to the narrowest, each a list of groups for Cluster; `.phone` is where a phone's start.
export function foldsOf(row) {
  // ...the lead kept in view is the row's lead, greyed or not, while the pills stand apart; on one ▾ it is a pressable one (leadOf)
  const { move, share, change, pin, lead, held } = pillsOf(row), set = (...vs) => [...new Set(vs.filter(Boolean))], wide = set(pin, held), narrow = set(pin, lead);
  const min = (must) => must.filter((v) => move.includes(v)).length;
  const two = (n, k) => [...(move.length ? [pill("move", move, n, wide)] : []), ...(change.length ? [pill("change", change, k, wide)] : []),
    ...(share.length ? [{ type: "share", label: "", shown: share, rest: [] }] : [])];
  // ...one ▾: the Change pill's moves after the move pill's own, and its lit move kept in view beside them
  const one = (n) => { const g = pill("move", [...move, ...change, ...share], n + narrow.filter((v) => change.includes(v)).length, narrow); return g.shown.length || g.rest.length ? [{ ...g, type: move.length ? "move" : "change" }] : []; };
  const out = [];
  for (let k = change.length; k >= 0; k--) out.push(two(move.length, k));
  for (let n = move.length - 1; n >= min(wide); n--) out.push(two(n, 0));
  out.phone = out.length;
  for (let n = move.length; n >= min(narrow); n--) out.push(one(n));
  // ...each layout once (a pill with nothing to fold gives the same layout twice)
  const seen = new Set(), sig = (l) => JSON.stringify(l.map((g) => [g.type, g.shown.map((v) => v.id), g.rest.map((v) => v.id)]));
  const kept = out.map((l) => !seen.has(sig(l)) && !!seen.add(sig(l))), uniq = out.filter((_, i) => kept[i]);
  uniq.phone = Math.min(kept.slice(0, out.phone).filter(Boolean).length, uniq.length - 1);
  return uniq;
}
// THE NAV PILL: Back and Next, in the walk's order (up, then down) - never folded, at any width
export const navOf = (row) => [row?.back, row?.next].filter(Boolean);
// a layout's width in px from measured parts (ActionRow reads them off a hidden copy of the row): `btn` by verb id, `label` by type,
// the ▾, Next and Back, a group's side padding, the gap after its label, between its buttons, and between groups. `nav`: the Nav pill's
// buttons (navOf), or Next alone
export function rowWidth(groups, nav, m) {
  const w = (v) => m.btn[v.id] ?? 0;
  const cl = (g) => {
    const n = g.shown.length + (g.rest.length ? 1 : 0);
    return m.pad + (g.label ? (m.label[g.type] ?? 0) + m.clGap : 0) + g.shown.reduce((a, v) => a + w(v), 0) + (g.rest.length ? m.more : 0) + m.bGap * Math.max(0, n - 1);
  };
  const ns = (Array.isArray(nav) ? nav : [nav]).filter(Boolean), nw = (v) => (v.group === "back" ? m.back ?? m.next : m.next);
  const parts = [...(ns.length ? [m.pad + (m.label?.nav ? m.label.nav + m.clGap : 0) + ns.reduce((a, v) => a + nw(v), 0) + m.bGap * (ns.length - 1)] : []), ...groups.map(cl)];
  return parts.reduce((a, x) => a + x, 0) + m.rowGap * Math.max(0, parts.length - 1);
}
// the widest layout that fits `avail` (a phone starts at its one-▾ layouts, foldsOf.phone); `extra` steps further when the drawn row still
// overflows what was measured; nothing measured yet (a test render, no layout) is the widest
export function fitRow(row, m, avail, phone = false, extra = 0) {
  const all = foldsOf(row), last = all.length - 1, from = phone ? all.phone : 0, at = (i) => ({ groups: all[Math.min(last, i)], level: Math.min(last, i), last });
  if (!m || !(avail > 0)) return at(from + extra);
  for (let i = from; i <= last; i++) if (rowWidth(all[i], navOf(row), m) <= avail) return at(i + extra);
  // ...and a move left too little room to say anything goes into the ▾ too, unless it is the lit one: a phone's report put Back, Next and
  // the chat pill beside "Put it on my list", and it read "Pu" (the 2026-10-27 sweep). A long move with room for its words is shortened.
  // Mark done stays (pinOf): only the move beside it goes
  const g = all[last][0], lead = g?.shown.find((v) => !isDone(v)), pin = g?.shown.find(isDone);
  if (lead && lead.tone !== "p" && avail - (rowWidth(all[last], navOf(row), m) - (m.btn[lead.id] ?? 0)) < MOVE_MIN) {
    const one = { type: pin ? g.type : "more", label: "", shown: pin ? [pin] : [], rest: [...g.shown.filter((v) => v !== pin), ...g.rest] };
    return { ...at(last), groups: [one], ...(pin && rowWidth([one], navOf(row), m) > avail ? { tight: true } : {}) };
  }
  return { ...at(last), tight: true };
}
const MOVE_MIN = 72;   // a few words and the ellipsis: less reads as a stray letter

// THE STAGE MOVES RIDE ON THEIR PANE (the owner, 2026-10-29, after three mockups). The bar keeps what acts on the whole task - Back and
// Next, Mark done, Change, Share, Hand it to a person, Close with a note, Attach a file. The moves that take the task a STAGE on belong to
// their pane: Send to agent, Continue, Run another to Agent; Reply, Draft reply, Redraft to Close out. Folded, a pane carries them on its
// spine, between its name and its status; open, inside it - and never on the bar. A press opens that pane and starts the step there
// (TaskPage's "a press opens its section"). While an agent is LIVE the bar's one move is Stop and save, Back and Next beside it.
// The task page's verbs say which pane is open and whether an agent is live (`laid`; none where it lays no panes - a phone, the Tasks
// tab): carried WITH the verbs, so the row never draws a set where the item's moves and the panes they ride on disagree (row-draws-once).
// The row draws the rest and hands the stage moves here, by pane (putSpineVerbs, useSpineVerbs)
const CLOSE_STAGE = new Set(["reply", "redraft", "chase", "accept_invite", "decline_invite", "propose_time", "find_time"]);
export const stageOf = (v) => { const k = String(v?.id || "").split(":").pop(), t = typeOf(v);
  return CLOSE_STAGE.has(k) ? "close" : t === "agent" && k !== "save-end" && k !== "diff" ? "agent" : ""; };
const NONE = [];
let spineVerbs = {}, spineSig = "";
const spineSubs = new Set(), spineSub = (f) => { spineSubs.add(f); return () => spineSubs.delete(f); }, spineDraw = () => spineSubs.forEach((f) => f());
export const laidOf = (list) => (list || []).find((v) => v.laid)?.laid || null;
export const putSpineVerbs = (by) => { const s = JSON.stringify(by); if (s === spineSig) return; spineSig = s; spineVerbs = by; spineDraw(); };
export const useSpineVerbs = (sec) => useSyncExternalStore(spineSub, () => spineVerbs[sec] || NONE);
// ...the row less its stage moves, and each pane's in the move pill's order (`spine`: the word a folded pane shows - Draft reply where
// nothing is drafted yet); a live agent's row only its Stop and save
export function splitRow(row, on, list = []) {
  if (!on) return { row, by: {} };
  const only = (keep) => ({ ...row, decide: row.decide.filter(keep), agent: row.agent.filter(keep), more: row.more.filter(keep) });
  if (on.live) return { row: only((v) => String(v.id).split(":").pop() === "save-end"), by: {} };
  const by = {};
  for (const v of pillsOf(row).move) { const k = stageOf(v); if (k) (by[k] ||= []).push(v); }
  // ...and a draft's own Redraft, which the row never draws (it is the card's, under the draft, while Close out is open): on the folded
  // spine it stands for the draft - filled when it is the Advisor's pick (rowOf's lit) - and Reply, which only opens that draft, steps aside
  const redraft = list.filter((x) => x.card && stageOf(x) === "close").map((v) => ({ ...v, tone: row.lit === v.id ? "p" : "s" }));
  if (redraft.length) by.close = [...redraft, ...(by.close || []).filter((v) => !redraft.some((r) => r.label === v.label) && v.id !== "reply")];
  return { row: only((v) => !stageOf(v)), by };
}
