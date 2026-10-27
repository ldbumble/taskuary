// THE ONE ROW ABOVE THE CHAT LINE (layout B): whatever is on the table, its verbs are here - the decision first, the session's verbs
// next, the rare ones behind More; Next is FIRST (the owner, 2026-09-30). The card registers them (actionRow.js); this only draws. Centred over the composer,
// ONE filled button at most - the Advisor's pick, and none before it answers - and a greyed decision says why it is greyed.
import React, { useEffect, useLayoutEffect, useRef, useState } from "react";
import { Menu, MenuItem, useMediaQuery } from "@mui/material";
import { ROW_HOLD_MS, ROW_STUCK_MS, TYPES, advisedAny, fitRow, press, rowOf, lightOnCard, sameRow, useHosted, useRowVerbs, useVerbs } from "./actionRow.js";
import { adviceNone } from "./words.js";
import { CONNECT_AI } from "./ConnectAi.jsx";

// what a refused proposal says on the line: the item moved under the Advisor (409) is not the owner's mistake - the page reads
// the advice again, and the line says the suggestion is the new one
export const proposeFailed = (e) => (e?.response?.status === 409 ? "This changed - here's the updated suggestion."
  : e?.response?.data?.detail || "That did not go through - try again.");

// THE ADVISOR'S PICK, ON THE ROW AND NOWHERE ELSE (the owner, 2026-10-26: "maybe keep the box but remove the advisor? not sure the advisor
// is really useful"): the strip that said its line over the row is gone - the lit button does the talking, and the few lines that warn
// are drawn in the task beside what they are about (advice.taskNote, AdvisorNote). What stays here is the move the row has no button
// for, joined to the row so it can be lit, and a hidden mark the walks read to tell a decided item from one still being read.
export function AdvisorNext({ advice, onPropose, onErr = null }) {
  const verbs = useRowVerbs();
  const [going, setGoing] = useState(false);
  // A MOVE THE ROW HAS NO BUTTON FOR (Not ours, Take it myself, Chase, Let it go) was hidden, and then got a button of its own beside
  // the line (2026-10-15) - a second row of buttons. The row owns every button (the owner, 2026-10-16: "the advisor should just
  // highlight the button in the button row not add new ones"): the move joins the row in its type, on the proposal road the pill
  // takes, stamped with the revision it was judged at, and the row fills it like any advised button
  const theirs = verbs.list.filter((v) => !String(v.id).startsWith("advice:"));
  const lacks = !!(advice?.verb && advice.verb !== "next" && onPropose) && !advisedAny(theirs, advice);
  useEffect(() => { setGoing(false); }, [advice?.for || advice?.key]);
  // ...a refusal is said where the page says what went wrong (onErr: the chat's error line) - there is no strip to say it on
  const run = async (e, anchor) => {
    setGoing(true);
    try { await onPropose(advice, anchor || e?.currentTarget || null); } catch (err) { onErr?.(proposeFailed(err)); } finally { setGoing(false); }
  };
  // ...it IS the advice, so it is the dark one (rowOf fills it like any advised verb)
  // ...at the END of its type (group "more"): in front, it pushed the type's own second button into ▾ when the advice landed (2026-10-19)
  useVerbs("advice", lacks ? [{ id: `advice:${advice.verb}`, label: advice.label, group: "more", tone: "p", disabled: going,
    title: "What the Advisor suggests", run }] : [], lacks);
  return advice?.verb ? <div hidden data-tq-advice="" data-tq-silent="" data-tq-advice-verb={advice.verb} /> : null;
}

// ONE TYPE: its label, its two most likely buttons joined, and its own ▾ for the rest (clustersOf)
function Cluster({ g, btn, act = press }) {
  const [at, setAt] = useState(null);
  return (
    <div className="tq-cl" role="group" aria-label={g.label || (g.type === "more" ? "More" : "This one")} data-tq-type={g.type}>
      {g.label && <span className="tq-cl-h" aria-hidden="true">{g.label}</span>}
      <div className="tq-cl-b">
        {g.shown.map(btn)}
        {g.rest.length > 0 && <>
          <button type="button" className="tq-ab s tq-cl-more" aria-haspopup="menu" aria-expanded={!!at} aria-label={`More ${g.label ? g.label.toLowerCase() + " " : ""}actions`}
            data-tq-more={g.type} onClick={(e) => setAt(e.currentTarget)}>▾</button>
          <Menu open={!!at} anchorEl={at} onClose={() => setAt(null)} anchorOrigin={{ vertical: "top", horizontal: "center" }} transformOrigin={{ vertical: "bottom", horizontal: "center" }}
            slotProps={{ paper: { sx: { minWidth: 200, borderRadius: 2 } } }}>
            {g.rest.map((v) => (
              <MenuItem key={v.id} dense disabled={v.disabled} title={(v.disabled && v.why) || v.title || undefined} data-tq-verb={v.id} data-tq-for={v.at}
                onClick={(e) => { const a = at; setAt(null); act(v.id, e, a, v.of); }} sx={{ fontSize: 13 }}>{v.label}</MenuItem>
            ))}
          </Menu></>}
      </div>
    </div>
  );
}

// the row says what to do, by type - not which task or how long it waited: the card above says both (the owner, 2026-10-13)
export default function ActionRow({ inline = false, advised: given = null, hold = false, early = true }) {
  // `hold` (actionRow.useRowHold, its number): the new row is not whole yet - the row drawn last stays up as it was, and its presses do
  // nothing, until it is; with none drawn yet (a reload) there is no row until then. Never hidden, never greyed, never drawn twice
  // ...and at most ROW_HOLD_MS from the moment the held row is kept off one that may be drawn (`early`: the new item's own verbs are up)
  // - counted once for a run of holds, a click on another row before this one was whole included - then the live one until the holding
  // is over - and ROW_STUCK_MS from the first difference in one hold, whatever the live row is. The lit pick drawn is the held one: the press that
  // starts a walk move puts the Advisor's light out (busy) a render before the old verbs go
  const now = useRowVerbs(), seen = useRef(null), since = useRef(0), first = useRef({ n: 0, t: 0 }), [, wake] = useState(0);
  if (!hold || first.current.n !== hold) first.current = { n: hold, t: 0 };
  if (!hold) since.current = 0;
  const off = !!hold && (seen.current ? !sameRow(seen.current.verbs, now) : now.list.length > 0), t0 = performance.now();
  if (off && !first.current.t) first.current.t = t0;
  if (off && early && !since.current) since.current = t0;
  const late = (early && !!since.current && t0 - since.current >= ROW_HOLD_MS) || (!!first.current.t && t0 - first.current.t >= ROW_STUCK_MS);
  const free = !hold || late, apart = !free && off;
  useEffect(() => {
    if (!first.current.t || late) return undefined;
    const due = Math.min(since.current ? since.current + ROW_HOLD_MS : Infinity, first.current.t + ROW_STUCK_MS) - performance.now();
    const t = setTimeout(() => wake((n) => n + 1), Math.max(0, due) + 1);
    return () => clearTimeout(t);
  });
  if (free || !apart) seen.current = { verbs: now, advised: free || !seen.current ? given : seen.current.advised };
  const { verbs, advised } = seen.current || { verbs: { list: [], ref: "" }, advised: null };
  // ...a held button acts only where it stands for no item and is still live - Next pressed over a pick in flight is held and runs once
  // the pick lands (AssistantView) - never the item being left's own
  const act = verbs === now ? press : (id, e, a) => { const v = now.list.find((x) => x.id === id && !x.at); return v ? press(id, e, a, v.of) : undefined; };
  // a "none" answer lights its one move: no AI lights the row's own Connect an AI where the row has one (a failure's fix named after
  // its place) - it lit nothing, a move named "ai" no button carries (the design, phase A) - and any other none lights Next
  const move = advised?.none ? adviceNone(advised.none).move : "";
  const conn = move === "ai" ? verbs.list.find((v) => v.label === CONNECT_AI && !v.disabled) : null;
  const pick = advised?.none ? (conn ? { id: conn.id } : move === "ai" ? null : { verb: move || "next" }) : advised;
  const row = rowOf(verbs, pick);
  const { ref, decide, agent, more, next, why } = row;
  const hosted = useHosted();
  // ...a phone's row is Next, the one move and one ▾ (phoneRow) - the width the page calls a phone (AssistantView)
  const phone = useMediaQuery("(max-width:600px)");
  // the card's own move, advised, is lit on the card (rowOf's `lit`); only the row that is drawn says which
  const drawn = inline || !hosted;
  useEffect(() => { if (drawn) lightOnCard(row.lit); }, [drawn, row.lit]);
  useEffect(() => () => { if (drawn) lightOnCard(""); }, [drawn]);
  // ONE LINE, ALWAYS (the owner, 2026-10-23, foldsOf): the row's width and every part it can draw are measured, and the widest
  // layout that fits is drawn - on a resize, a verb arriving or a label changing ("Drafting…" -> "Redraft"), and once the fonts land
  const [box, setBox] = useState(null), ghost = useRef(null);
  const [m, setM] = useState(null), [avail, setAvail] = useState(0), [over, setOver] = useState({ at: "", n: 0 }), [fonts, setFonts] = useState(0);
  const narrow = useMediaQuery("(max-width:1099px)");   // the row's own breakpoint (assistantView.css): pills lose their min-width
  const parts = JSON.stringify([next?.label || "", [...decide, ...agent, ...more].map((v) => [v.id, v.label, v.tone])]);
  useEffect(() => { let on = true; document.fonts?.ready?.then(() => on && setFonts((n) => n + 1)); return () => { on = false; }; }, []);
  useLayoutEffect(() => { if (box && ghost.current) setM(measure(ghost.current, box)); }, [box, parts, narrow, fonts]);
  useLayoutEffect(() => {
    if (!box) return undefined;
    const f = () => setAvail(box.clientWidth);
    f();
    if (typeof ResizeObserver === "undefined") return undefined;
    const ro = new ResizeObserver(f);
    ro.observe(box);
    return () => ro.disconnect();
  }, [box]);
  // ...and if the drawn line still runs past its box (a width the parts did not add up to), one more group folds - until the parts are
  // measured again: an overflow drawn off a measure taken before the fonts landed folded a row that fit, and kept it folded
  const sig = `${parts}|${avail}|${phone}|${JSON.stringify(m)}`, extra = over.at === sig ? over.n : 0;
  const fit = fitRow(row, m, avail, phone, extra);
  useLayoutEffect(() => { if (box && fit.level < fit.last && box.scrollWidth > box.clientWidth + 1) setOver({ at: sig, n: extra + 1 }); });
  if (!inline && hosted) return null;                  // a phone's task view carries its own row
  if (!decide.length && !agent.length && !more.length && !next) return null;
  // ONE NAME PER BUTTON (buttons.json, the owner, 2026-10-17): the bar says the same words the hover, the Advisor and the menu say -
  // a short bar word ("Snooze", "Stop") beside a long hover one was two names for one button
  const btn = (v) => (
    <button key={v.id} type="button" className={`tq-ab ${v.tone}`} disabled={v.disabled} data-tq-verb={v.id} data-tq-for={v.at} data-tq-own={v.own ? "" : undefined}
      title={(v.disabled && v.why) || v.title || (fit.tight ? v.label : undefined)} onClick={(e) => act(v.id, e, e.currentTarget, v.of)}>{v.label}</button>
  );
  return (
    <div className={inline ? "tq-arow inline" : "tq-arow"} role="toolbar" aria-label={ref ? `What to do with ${ref}` : "What to do with this one"} data-tq-row=""
      aria-busy={hold || undefined}>
      <div className={fit.tight ? "tq-arow-verbs tight" : "tq-arow-verbs"} ref={setBox} data-tq-fold={fit.level}>
        {next && <div className="tq-cl tq-cl-next" role="group" aria-label="Move on">
          <div className="tq-cl-b"><button type="button" className={`tq-ab ${next.tone} next`} data-tq-next="" {...(String(next.id).endsWith(":back") ? { "data-tq-back": "" } : {})} data-tq-steady={next.steady ? "" : undefined} title={next.title || undefined} disabled={next.disabled}
            onClick={(e) => act(next.id, e, e.currentTarget, next.of)}>{next.label}</button></div></div>}
        {fit.groups.map((g) => <Cluster key={g.type} g={g} btn={btn} act={act} />)}
      </div>
      {why && <div className="tq-arow-why" role="status" data-tq-row-why="">{why}</div>}
      {/* every part the row can draw, unseen, in the row's own classes - what fitRow adds up */}
      <div className="tq-arow-ghost" ref={ghost} aria-hidden="true">
        <div className="tq-cl">
          {TYPES.map(([t, l]) => <span key={t} className="tq-cl-h" data-tq-wl={t}>{l}</span>)}
          <div className="tq-cl-b">
            {next && <span className={`tq-ab ${next.tone} next`} data-tq-wn="">{next.label}</span>}
            {[...decide, ...agent, ...more].map((v) => <span key={v.id} className={`tq-ab ${v.tone}`} data-tq-w={v.id}>{v.label}</span>)}
            <span className="tq-ab s tq-cl-more" data-tq-wm="">▾</span>
          </div>
        </div>
      </div>
    </div>
  );
}

// the parts' widths off the hidden copy, and the gaps off the row's own styles - rounded up, so a fit is never a fraction short
function measure(ghost, box) {
  const w = (el) => (el ? Math.ceil(el.getBoundingClientRect().width) : 0), px = (el, k) => (el ? parseFloat(getComputedStyle(el)[k]) || 0 : 0);
  const cl = ghost.querySelector(".tq-cl"), b = ghost.querySelector(".tq-cl-b"), btn = {}, label = {};
  ghost.querySelectorAll("[data-tq-w]").forEach((el) => { btn[el.dataset.tqW] = w(el); });
  ghost.querySelectorAll("[data-tq-wl]").forEach((el) => { label[el.dataset.tqWl] = w(el); });
  return { btn, label, more: w(ghost.querySelector("[data-tq-wm]")), next: w(ghost.querySelector("[data-tq-wn]")),
    pad: px(cl, "paddingLeft") + px(cl, "paddingRight"), clGap: px(cl, "columnGap"), bGap: px(b, "columnGap"), rowGap: px(box, "columnGap") };
}
