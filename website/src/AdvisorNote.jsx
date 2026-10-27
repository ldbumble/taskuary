// THE ADVISOR'S WARNING, IN THE TASK (the owner, 2026-10-26: "maybe keep the box but remove the advisor?"): the strip over the row is gone,
// and the few lines that warned of something on the task stand beside it - under the draft, at the task's head (advice.taskNote). One
// quiet line in the oxblood the invite's clash is said in, whole on hover; a line the model wrote keeps its Why? - what it rests on.
import React, { useState } from "react";
import { Box, Popover } from "@mui/material";
import api from "./api.js";

export default function AdvisorNote({ note, sx }) {
  const [at, setAt] = useState(null), [rest, setRest] = useState(null);
  if (!note?.line) return null;
  const a = note.advice || {};
  const why = (e) => {
    setAt(e.currentTarget); setRest(null);
    api.get("/api/advice/notes", { params: { key: a.key, limit: 5 } })
      .then(({ data }) => setRest((data?.rows || []).find((r) => r.verb === a.verb && r.line) || {}))
      .catch(() => setRest({}));
  };
  return (
    <Box role="note" data-tq-advisor-note={note.at} sx={{ display: "flex", alignItems: "baseline", gap: 0.75, minWidth: 0, fontSize: 12.5, lineHeight: 1.45, ...sx }}>
      <Box component="span" title={note.line} sx={{ color: "#7a2f3c", fontWeight: 600, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
        {note.line}</Box>
      {note.why && <button type="button" className="tq-next-why" aria-haspopup="dialog" aria-expanded={!!at} onClick={why}
        style={{ padding: "1px 4px", fontSize: 12 }}>Why?</button>}
      <Popover open={!!at} anchorEl={at} onClose={() => setAt(null)} anchorOrigin={{ vertical: "bottom", horizontal: "left" }}
        transformOrigin={{ vertical: "top", horizontal: "left" }} slotProps={{ paper: { sx: { borderRadius: 2.5, maxWidth: 420 } } }}>
        <div className="tq-next-pop" role="dialog" aria-label="Why the Advisor says this">
          <div className="said">{a.line || note.line}</div>
          {a.label && <div className="pick">Lit: <b>{a.label}</b> - the dark button</div>}
          {/* what it rests on, in words: an evidence id ("out13") or the model's name tells someone who never wrote code nothing */}
          {rest === null ? <div className="fact">Reading its notes…</div> : (rest.evidence || []).some((e) => e.label) && (
            <div className="rests"><div className="head">What it rests on</div>
              <ul>{rest.evidence.filter((e) => e.label).map((e) => <li key={e.id}>{e.label}</li>)}</ul></div>)}
          {rest?.at && <div className="when">Judged {String(rest.at).slice(0, 16)}</div>}
        </div>
      </Popover>
    </Box>
  );
}
