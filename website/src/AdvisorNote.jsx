// THE ADVISOR'S SECTION ON THE TASK (the owner, 2026-10-26: "advisor lines that are important show on the task ... it will be hard to
// differentiate between task description and the advisor", then "it can be another section ... one is more a guide and one is more doing
// work but they are in essence the same idea"): the few lines that matter (advice.taskNote) stand in a section of their own over Agent
// work, under the mark and "Advisor", on a slate rule so they never read as the task's own words. Drawn only when there is a line; each keeps its Why? (what it rests on),
// and the draft's warning points at the draft it is about.
import React, { useState } from "react";
import { Box, Popover, Typography } from "@mui/material";
import api from "./api.js";
import { TaskuaryMark } from "./ui.jsx";
import { DIM, INK, label } from "./theme.jsx";

export default function AdvisorNote({ note, onDraft = null, sx }) {
  const [at, setAt] = useState(null), [rest, setRest] = useState(null);
  if (!note?.line) return null;
  const a = note.advice || {};
  const why = (e) => {
    setAt(e.currentTarget); setRest(null);
    api.get("/api/advice/notes", { params: { key: a.key || a.for, limit: 5 } })
      .then(({ data }) => setRest((data?.rows || []).find((r) => r.verb === a.verb && r.line) || {}))
      .catch(() => setRest({}));
  };
  return (
    <Box component="section" aria-label="Advisor" data-tq-advisor="" sx={{ flexShrink: 0, mb: 1, px: 1.25, py: 0.85, borderRadius: 2, bgcolor: "#f3f5f7",
      borderLeft: "3px solid #55697a", minWidth: 0, ...sx }}>
      <Box sx={{ display: "flex", alignItems: "center", gap: 0.6, mb: 0.35 }}>
        <TaskuaryMark size={13} />
        <Typography sx={{ ...label, color: "#55697a" }}>Advisor</Typography>
      </Box>
      <Box data-tq-advisor-note={note.draft ? "draft" : "task"} sx={{ display: "flex", alignItems: "baseline", gap: 0.75, minWidth: 0, fontSize: 13, lineHeight: 1.45 }}>
        <Box component="span" title={note.line} sx={{ color: INK, fontWeight: 500, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {note.line}</Box>
        {note.draft && onDraft && <button type="button" className="tq-next-why" data-tq-advisor-draft="" onClick={onDraft}
          style={{ padding: "1px 4px", fontSize: 12 }}>See the draft</button>}
        <button type="button" className="tq-next-why" aria-haspopup="dialog" aria-expanded={!!at} onClick={why}
          style={{ padding: "1px 4px", fontSize: 12 }}>Why?</button>
      </Box>
      <Popover open={!!at} anchorEl={at} onClose={() => setAt(null)} anchorOrigin={{ vertical: "bottom", horizontal: "left" }}
        transformOrigin={{ vertical: "top", horizontal: "left" }} slotProps={{ paper: { sx: { borderRadius: 2.5, maxWidth: 420 } } }}>
        <div className="tq-next-pop" role="dialog" aria-label="Why the Advisor says this">
          <div className="said">{a.line || note.line}</div>
          {a.label && <div className="pick">Lit: <b>{a.label}</b> - the dark button</div>}
          {/* what it rests on, in words: an evidence id ("out13") or the model's name tells someone who never wrote code nothing */}
          {rest === null ? <div className="fact">Reading its notes…</div> : (rest.evidence || []).some((e) => e.label) ? (
            <div className="rests"><div className="head">What it rests on</div>
              <ul>{rest.evidence.filter((e) => e.label).map((e) => <li key={e.id}>{e.label}</li>)}</ul></div>)
            : <Box className="fact" sx={{ color: DIM }}>{a.by === "model" ? "Read from this item by the AI." : "A fact Taskuary keeps about this item."}</Box>}
          {rest?.at && <div className="when">Judged {String(rest.at).slice(0, 16)}</div>}
        </div>
      </Popover>
    </Box>
  );
}
