// THE ONE ROW ABOVE THE CHAT LINE (layout B): whatever is on the table, its verbs are here - the decision first, the session's verbs
// next, the rare ones behind More; Next is FIRST (the owner, 2026-09-30). The card registers them (actionRow.js); this only draws. Centred over the composer,
// ONE filled button at most (the decision; Next only when there is no decision), and a greyed decision says why it is greyed.
import React, { useState } from "react";
import { Menu, MenuItem, Popover } from "@mui/material";
import api from "./api.js";
import { suggestion } from "./advice.js";
import { advisedIn, press, rowOf, useHosted, useRowVerbs } from "./actionRow.js";

// THE ADVISOR'S SUGGESTION (advisor.py), over the row whose filled button it picked: the reason in a sentence, and Why? for the
// reasoning behind it - the buttons stay on the row, the box below stays the owner's own. Nothing to say draws nothing (2026-10-13).
export function AdvisorNext({ advice }) {
  const verbs = useRowVerbs();
  const [at, setAt] = useState(null), [note, setNote] = useState(null);
  if (!advice?.verb || !advice.line) return null;
  const onRow = advisedIn(verbs.list, advice);
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
      <button type="button" className="tq-next-why" aria-haspopup="dialog" aria-expanded={!!at} onClick={why}>Why?</button>
      <Popover open={!!at} anchorEl={at} onClose={() => setAt(null)} anchorOrigin={{ vertical: "top", horizontal: "right" }}
        transformOrigin={{ vertical: "bottom", horizontal: "right" }} slotProps={{ paper: { sx: { borderRadius: 2.5, maxWidth: 420 } } }}>
        <div className="tq-next-pop" role="dialog" aria-label="Why the Advisor suggests this">
          <div className="pick">Suggested: <b>{onRow?.label || advice.label}</b>{onRow ? " - the dark button below" : ""}</div>
          <div className="said">{advice.line}</div>
          {m >= 2 && <div className="fact">You chose {advice.label} {n} of {m} times in a moment like this.</div>}
          {note === null ? <div className="fact">Reading its notes…</div> : (note.evidence || []).length > 0 && (
            <div className="rests"><div className="head">What it rests on</div>
              <ul>{note.evidence.map((e) => <li key={e.id}>{e.label || e.id}</li>)}</ul></div>)}
          {note?.at && <div className="when">Judged {String(note.at).slice(0, 16)}{note.model ? ` · ${note.model}` : ""}</div>}
        </div>
      </Popover>
    </div>
  );
}

export default function ActionRow({ inline = false, waited = "", advised = null }) {
  const { ref, decide, agent, more, next, why } = rowOf(useRowVerbs(), advised);
  const hosted = useHosted();
  const [at, setAt] = useState(null);
  if (!inline && hosted) return null;                  // a phone's task view carries its own row
  if (!decide.length && !agent.length && !more.length && !next) return null;
  const btn = (v) => (
    <button key={v.id} type="button" className={`tq-ab ${v.tone}`} title={(v.disabled && v.why) || v.title || undefined} disabled={v.disabled} data-tq-verb={v.id}
      onClick={(e) => press(v.id, e, e.currentTarget)}>{v.label}</button>
  );
  return (
    <div className={inline ? "tq-arow inline" : "tq-arow"} role="toolbar" aria-label={ref ? `What to do with ${ref}` : "What to do with this one"} data-tq-row="">
      <div className="tq-arow-verbs">
        {next && <button type="button" className={`tq-ab ${next.tone} next`} data-tq-next="" title={next.title || undefined} disabled={next.disabled}
          onClick={(e) => press(next.id, e, e.currentTarget)}>{next.label}</button>}
        {decide.map(btn)}
        {agent.map(btn)}
        {more.length > 0 && <>
          <button type="button" className="tq-ab q" aria-haspopup="menu" aria-expanded={!!at} data-tq-more="" onClick={(e) => setAt(e.currentTarget)}>More ▾</button>
          <Menu open={!!at} anchorEl={at} onClose={() => setAt(null)} anchorOrigin={{ vertical: "top", horizontal: "center" }} transformOrigin={{ vertical: "bottom", horizontal: "center" }}
            slotProps={{ paper: { sx: { minWidth: 210, borderRadius: 2 } } }}>
            {more.map((v) => (
              <MenuItem key={v.id} dense disabled={v.disabled} title={(v.disabled && v.why) || v.title || undefined} data-tq-verb={v.id}
                onClick={(e) => { const a = at; setAt(null); press(v.id, e, a); }} sx={{ fontSize: 13 }}>{v.label}</MenuItem>
            ))}
          </Menu></>}
        {ref && <span className="tq-arow-ref" data-tq-row-ref="">{ref}{waited && <span className="waited" data-tq-row-waited=""> · {waited}</span>}</span>}
      </div>
      {why && <div className="tq-arow-why" role="status" data-tq-row-why="">{why}</div>}
    </div>
  );
}
