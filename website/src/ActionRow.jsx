// THE ONE ROW ABOVE THE CHAT LINE (layout B): whatever is on the table, its verbs are here - the decision first, the session's verbs
// next, the rare ones behind More; Next is FIRST (the owner, 2026-09-30). The card registers them (actionRow.js); this only draws. Centred over the composer,
// ONE filled button at most - the Advisor's pick, and none before it answers - and a greyed decision says why it is greyed.
import React, { useEffect, useState } from "react";
import { Menu, MenuItem, Popover, useMediaQuery } from "@mui/material";
import api from "./api.js";
import { suggestion } from "./advice.js";
import { advisedAny, advisedIn, clustersOf, phoneRow, press, rowOf, lightOnCard, useHosted, useRowVerbs, useVerbs } from "./actionRow.js";
import { adviceNone } from "./words.js";
import { CONNECT_AI } from "./ConnectAi.jsx";

// what a refused proposal says on the line: the item moved under the Advisor (409) is not the owner's mistake - the page reads
// the advice again, and the line says the suggestion is the new one
export const proposeFailed = (e) => (e?.response?.status === 409 ? "This changed - here's the updated suggestion."
  : e?.response?.data?.detail || "That did not go through - try again.");

// THE ADVISOR'S SUGGESTION (advisor.py), over the row whose filled button it picked: the fact it rests on, and Why? for the
// reasoning behind it - the buttons stay on the row, the box below stays the owner's own. THE OBVIOUS MOVE IS SILENT (the owner,
// 2026-10-23): a decision with no line lights its button and the strip draws no sentence - only an empty mark the walk reads.
export function AdvisorNext({ advice, onPropose }) {
  const verbs = useRowVerbs();
  const [at, setAt] = useState(null), [note, setNote] = useState(null), [going, setGoing] = useState("");
  // A MOVE THE ROW HAS NO BUTTON FOR (Not ours, Take it myself, Chase, Let it go) was hidden, and then got a button of its own beside
  // the line (2026-10-15) - a second row of buttons. The row owns every button (the owner, 2026-10-16: "the advisor should just
  // highlight the button in the button row not add new ones"): the move joins the row in its type, on the proposal road the pill
  // takes, stamped with the revision it was judged at, and the row fills it like any advised button
  const theirs = verbs.list.filter((v) => !String(v.id).startsWith("advice:"));
  const lacks = !!(advice?.verb && advice.verb !== "next" && onPropose) && !advisedAny(theirs, advice);
  // ...a 409 says so once and stays over the suggestion the page reads next for this item; another item starts clean
  useEffect(() => { setGoing(""); }, [advice?.for || advice?.key]);
  const run = async (e, anchor) => {
    setGoing("…");
    try { await onPropose(advice, anchor || e?.currentTarget || null); setGoing(""); } catch (err) { setGoing(proposeFailed(err)); }
  };
  // ...it IS the advice, so it is the dark one (rowOf fills it like any advised verb)
  // ...at the END of its type (group "more"): in front, it pushed the type's own second button into ▾ when the advice landed (2026-10-19)
  useVerbs("advice", lacks ? [{ id: `advice:${advice.verb}`, label: advice.label, group: "more", tone: "p", disabled: going === "…",
    title: "What the Advisor suggests", run }] : [], lacks);
  if (!advice?.verb) return null;
  // the silent decision: its button is lit, and the strip says nothing (data-tq-advice marks it decided for the dead-end walk)
  const mark = <div hidden data-tq-advice="" data-tq-silent="" />;
  if (advice.verb === "next") return advice.line ? <div className="tq-next" role="status" data-tq-advice=""><div className="tq-next-txt">{advice.line}</div></div> : mark;
  // a move the row cannot make NOW is not advice: "Stop the agent" over a greyed Stop and save left Next the filled
  // button under it (the owner, 2026-10-13: "it said stop agent but highlighted button was next?")
  const onRow = advisedIn(verbs.list, advice);
  if (!onRow) {
    // ...but A MOVE THE ROW HAS AND HAS GREYED says why it is off, in the row's own words: the draft's text cleared, Send greyed, and
    // the strip went blank with nothing lit (the advisor matrix, 2026-10-19) - the line it was judged with is not true of this screen
    const off = advisedAny(theirs, advice);
    if (!off?.disabled) return null;
    return (
      <div className="tq-next" role="status" data-tq-advice="off">
        <div className="tq-next-txt">{`${off.label} is off - ${off.why || "it cannot be pressed right now"}.`}</div>
      </div>
    );
  }
  // ...and a move whose text is gone (`blank`: a chat's Mark done copies the draft, and the box was emptied) says what it does now,
  // in place of the line judged over the draft as filed - still the advised move, still lit (the matrix's verify, 2026-10-20)
  if (onRow.blank) return <div className="tq-next" role="status" data-tq-advice=""><div className="tq-next-txt">{`${onRow.blank}.`}</div></div>;
  if (!advice.line) return mark;
  const word = onRow.label;
  const why = (e) => {
    setAt(e.currentTarget); setNote(null);
    api.get("/api/advice/notes", { params: { key: advice.key, limit: 5 } })
      .then(({ data }) => setNote((data?.rows || []).find((r) => r.verb === advice.verb && r.line) || {}))
      .catch(() => setNote({}));
  };
  return (
    <div className="tq-next" role="status" data-tq-advice="">
      <div className="tq-next-txt">{suggestion(advice.line, advice.label, advice.verb)}{going && going !== "…" && <span className="tq-next-err"> {going}</span>}</div>
      <button type="button" className="tq-next-why" aria-haspopup="dialog" aria-expanded={!!at} onClick={why}>Why?</button>
      <Popover open={!!at} anchorEl={at} onClose={() => setAt(null)} anchorOrigin={{ vertical: "top", horizontal: "right" }}
        transformOrigin={{ vertical: "bottom", horizontal: "right" }} slotProps={{ paper: { sx: { borderRadius: 2.5, maxWidth: 420 } } }}>
        <div className="tq-next-pop" role="dialog" aria-label="Why the Advisor suggests this">
          <div className="pick">Suggested: <b>{word}</b> - the dark button</div>
          <div className="said">{advice.line}</div>
          {/* each count in words of what it measures (advisor.says) - a close that held is not an answer to a chase */}
          {!!advice.says && <div className="fact">{advice.says}</div>}
          {/* what it rests on, in words: an evidence id ("out13") or the model's name tells someone who never wrote code nothing */}
          {note === null ? <div className="fact">Reading its notes…</div> : (note.evidence || []).some((e) => e.label) && (
            <div className="rests"><div className="head">What it rests on</div>
              <ul>{note.evidence.filter((e) => e.label).map((e) => <li key={e.id}>{e.label}</li>)}</ul></div>)}
          {note?.at && <div className="when">Judged {String(note.at).slice(0, 16)}</div>}
        </div>
      </Popover>
    </div>
  );
}

// ONE TYPE: its label, its two most likely buttons joined, and its own ▾ for the rest (clustersOf)
function Cluster({ g, btn }) {
  const [at, setAt] = useState(null);
  return (
    <div className="tq-cl" role="group" aria-label={g.label || "This one"} data-tq-type={g.type}>
      {g.label && <span className="tq-cl-h" aria-hidden="true">{g.label}</span>}
      <div className="tq-cl-b">
        {g.shown.map(btn)}
        {g.rest.length > 0 && <>
          <button type="button" className="tq-ab s tq-cl-more" aria-haspopup="menu" aria-expanded={!!at} aria-label={`More ${g.label ? g.label.toLowerCase() + " " : ""}actions`}
            data-tq-more={g.type} onClick={(e) => setAt(e.currentTarget)}>▾</button>
          <Menu open={!!at} anchorEl={at} onClose={() => setAt(null)} anchorOrigin={{ vertical: "top", horizontal: "center" }} transformOrigin={{ vertical: "bottom", horizontal: "center" }}
            slotProps={{ paper: { sx: { minWidth: 200, borderRadius: 2 } } }}>
            {g.rest.map((v) => (
              <MenuItem key={v.id} dense disabled={v.disabled} title={(v.disabled && v.why) || v.title || undefined} data-tq-verb={v.id}
                onClick={(e) => { const a = at; setAt(null); press(v.id, e, a); }} sx={{ fontSize: 13 }}>{v.label}</MenuItem>
            ))}
          </Menu></>}
      </div>
    </div>
  );
}

// the row says what to do, by type - not which task or how long it waited: the card above says both (the owner, 2026-10-13)
export default function ActionRow({ inline = false, advised = null }) {
  // a "none" answer lights its one move: no AI lights the row's own Connect an AI where the row has one (a failure's fix named after
  // its place) - it lit nothing, a move named "ai" no button carries (the design, phase A) - and any other none lights Next
  const verbs = useRowVerbs();
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
  if (!inline && hosted) return null;                  // a phone's task view carries its own row
  if (!decide.length && !agent.length && !more.length && !next) return null;
  // ONE NAME PER BUTTON (buttons.json, the owner, 2026-10-17): the bar says the same words the hover, the Advisor and the menu say -
  // a short bar word ("Snooze", "Stop") beside a long hover one was two names for one button
  // the card's main move keeps its width here, empty and unpressable - its button is under the draft (rowOf's `slot`)
  const btn = (v) => (v.slot ? <span key={v.id} className="tq-ab s slot" aria-hidden="true" data-tq-slot="">{v.label}</span> :
    <button key={v.id} type="button" className={`tq-ab ${v.tone}`} disabled={v.disabled} data-tq-verb={v.id} data-tq-own={v.own ? "" : undefined}
      title={(v.disabled && v.why) || v.title || undefined} onClick={(e) => press(v.id, e, e.currentTarget)}>{v.label}</button>
  );
  return (
    <div className={inline ? "tq-arow inline" : "tq-arow"} role="toolbar" aria-label={ref ? `What to do with ${ref}` : "What to do with this one"} data-tq-row="">
      <div className="tq-arow-verbs">
        {next && <div className="tq-cl" role="group" aria-label="Move on">
          <div className="tq-cl-b"><button type="button" className={`tq-ab ${next.tone} next`} data-tq-next="" {...(String(next.id).endsWith(":back") ? { "data-tq-back": "" } : {})} title={next.title || undefined} disabled={next.disabled}
            onClick={(e) => press(next.id, e, e.currentTarget)}>{next.label}</button></div></div>}
        {(phone ? [phoneRow(row)].filter((g) => g.shown.length || g.rest.length) : clustersOf(row)).map((g) => <Cluster key={g.type} g={g} btn={btn} />)}
      </div>
      {why && <div className="tq-arow-why" role="status" data-tq-row-why="">{why}</div>}
    </div>
  );
}
