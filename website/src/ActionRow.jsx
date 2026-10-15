import { t as tx } from "./i18n.js";
// THE ONE ROW ABOVE THE CHAT LINE (layout B): whatever is on the table, its verbs are here - the decision first, the session's verbs
// next, the rare ones behind More; Next is FIRST (the owner, 2026-09-30). The card registers them (actionRow.js); this only draws. Centred over the composer,
// ONE filled button at most (the decision; Next only when there is no decision), and a greyed decision says why it is greyed.
import React, { useState } from "react";
import { Menu, MenuItem, Popover } from "@mui/material";
import api from "./api.js";
import { suggestion } from "./advice.js";
import { advisedIn, clustersOf, press, rowOf, shortLabel, useHosted, useRowVerbs } from "./actionRow.js";

// THE ADVISOR'S SUGGESTION (advisor.py), over the row whose filled button it picked: the reason in a sentence, and Why? for the
// reasoning behind it - the buttons stay on the row, the box below stays the owner's own. Nothing to say draws nothing (2026-10-13).
export function AdvisorNext({ advice }) {
  const verbs = useRowVerbs();
  const [at, setAt] = useState(null), [note, setNote] = useState(null);
  if (!advice?.verb || !advice.line) return null;
  const onRow = advisedIn(verbs.list, advice);
  // a move the row cannot make is not advice: "Stop the agent" over a greyed Save and end session left Next the filled
  // button under it (the owner, 2026-10-13: "it said stop agent but highlighted button was next?")
  if (!onRow) return null;
  const [n, m] = advice.count || [0, 0];
  const why = (e) => {
    setAt(e.currentTarget); setNote(null);
    api.get("/api/advice/notes", { params: { key: advice.key, limit: 5 } })
      .then(({ data }) => setNote((data?.rows || []).find((r) => r.verb === advice.verb && r.line) || {}))
      .catch(() => setNote({}));
  };
  return (
    <div className="tq-next" role="status" data-tq-advice="">
      <div className="tq-next-txt">{suggestion(advice.line, advice.label, advice.verb)}</div>
      <button type="button" className="tq-next-why" aria-haspopup="dialog" aria-expanded={!!at} onClick={why}>{tx("Why?")}</button>
      <Popover open={!!at} anchorEl={at} onClose={() => setAt(null)} anchorOrigin={{ vertical: "top", horizontal: "right" }}
        transformOrigin={{ vertical: "bottom", horizontal: "right" }} slotProps={{ paper: { sx: { borderRadius: 2.5, maxWidth: 420 } } }}>
        <div className="tq-next-pop" role="dialog" aria-label={tx("Why the Advisor suggests this")}>
          <div className="pick">{tx("Suggested:")} <b>{onRow.label}</b> {tx("- the dark button below")}</div>
          <div className="said">{advice.line}</div>
          {m >= 2 && <div className="fact">{tx("You chose")} {advice.label} {n} {tx("of")} {m} {tx("times in a moment like this.")}</div>}
          {note === null ? <div className="fact">{tx("Reading its notes…")}</div> : (note.evidence || []).length > 0 && (
            <div className="rests"><div className="head">{tx("What it rests on")}</div>
              <ul>{note.evidence.map((e) => <li key={e.id}>{e.label || e.id}</li>)}</ul></div>)}
          {note?.at && <div className="when">{tx("Judged")} {String(note.at).slice(0, 16)}{note.model ? ` · ${note.model}` : ""}</div>}
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
  const row = rowOf(useRowVerbs(), advised);
  const { ref, decide, agent, more, next, why } = row;
  const hosted = useHosted();
  if (!inline && hosted) return null;                  // a phone's task view carries its own row
  if (!decide.length && !agent.length && !more.length && !next) return null;
  // the bar says the verb; the hover says the whole thing - the full name first, then what it does
  const btn = (v) => {
    const word = shortLabel(v), full = word === v.label ? "" : v.label;
    return (
      <button key={v.id} type="button" className={`tq-ab ${v.tone}`} disabled={v.disabled} data-tq-verb={v.id} aria-label={full || undefined}
        title={(v.disabled && v.why) || [full, v.title].filter(Boolean).join(" - ") || undefined}
        onClick={(e) => press(v.id, e, e.currentTarget)}>{word}</button>
    );
  };
  return (
    <div className={inline ? "tq-arow inline" : "tq-arow"} role="toolbar" aria-label={ref ? `What to do with ${ref}` : "What to do with this one"} data-tq-row="">
      <div className="tq-arow-verbs">
        {next && <div className="tq-cl" role="group" aria-label={tx("Move on")}>
          <div className="tq-cl-b"><button type="button" className={`tq-ab ${next.tone} next`} data-tq-next="" title={next.title || undefined} disabled={next.disabled}
            onClick={(e) => press(next.id, e, e.currentTarget)}>{next.label}</button></div></div>}
        {clustersOf(row).map((g) => <Cluster key={g.type} g={g} btn={btn} />)}
      </div>
      {why && <div className="tq-arow-why" role="status" data-tq-row-why="">{why}</div>}
    </div>
  );
}
