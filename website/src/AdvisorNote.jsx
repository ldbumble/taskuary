// THE ADVISOR'S SECTION ON THE TASK (the owner, 2026-10-26: "advisor lines that are important show on the task ... it will be hard to
// differentiate between task description and the advisor", then "it can be another section ... one is more a guide and one is more doing
// work but they are in essence the same idea"): the few lines that matter (advice.taskNote) stand in a section of their own, under the mark
// and "Advisor", on a slate rule so they never read as the task's own words. Drawn only when there is a line; each keeps its Why? (what it
// rests on), and the draft's warning points at the draft it is about.
// ...ONE COMPACT LINE IN THE MAIN VIEW, AND IT WRAPS (the Advisor audit's judge, 2026-10-26): behind the right drawer's sideways tab a late
// line or the reason for a fold was off screen, and on a phone "this is 5h" was cut off by an ellipsis - the mark, the word and the line
// share one row that wraps, never truncates. Why? reads the SAME decision the row lit (its `rests`), and a reason that came from memory
// carries Keep / Wrong / Forget right there (the judge's F5): Wrong or Forget takes the line off this task and every other that used it.
import React, { useState } from "react";
import { Box, Popover, Typography } from "@mui/material";
import api from "./api.js";
import { TaskuaryMark } from "./ui.jsx";
import { ALERT_INK, DIM, INK, label } from "./theme.jsx";
import { MARKS, MARK_HINT } from "./learnedGroups.js";

// the moves a memory line takes from the task: the owner's own line Forget only, a learned one all three (learnedGroups.marksFor)
export const memoryMarks = (r) => (r?.kind !== "memory" || !r.key ? [] : r.own ? ["forget"] : ["keep", "wrong", "forget"]);
export const MARKED = { keep: "Kept - it is yours now.", wrong: "Marked wrong - it leaves, and the task reads again.", forget: "Forgotten - the task reads again." };

export default function AdvisorNote({ note, onDraft = null, sx }) {
  const [at, setAt] = useState(null), [done, setDone] = useState({}), [err, setErr] = useState("");
  if (!note?.line) return null;
  const a = note.advice || {}, rests = a.rests || [];
  const mark = async (r, how) => {
    setErr("");
    try { await api.post("/api/learned/mark", { key: r.key, how }); setDone((d) => ({ ...d, [r.key]: how })); }
    catch (e) { setErr(e?.response?.data?.detail || "That did not go through - nothing was changed."); }
  };
  return (
    <Box component="section" aria-label="Advisor" data-tq-advisor="" sx={{ flexShrink: 0, mb: 1, px: 1.25, py: 0.6, borderRadius: 2, bgcolor: "#f3f5f7",
      borderLeft: "3px solid #55697a", minWidth: 0, ...sx }}>
      <Box data-tq-advisor-note={note.draft ? "draft" : "task"} sx={{ display: "flex", flexWrap: "wrap", alignItems: "baseline", columnGap: 0.75, rowGap: 0.25,
        minWidth: 0, fontSize: 13, lineHeight: 1.45 }}>
        <Box component="span" sx={{ display: "inline-flex", alignItems: "center", gap: 0.5, alignSelf: "center" }}>
          <TaskuaryMark size={12} /><Typography component="span" sx={{ ...label, color: "#55697a" }}>Advisor</Typography></Box>
        <Box component="span" data-tq-advisor-line="" sx={{ color: INK, fontWeight: 500, minWidth: 0, overflowWrap: "anywhere" }}>{note.line}</Box>
        {note.draft && onDraft && <button type="button" className="tq-next-why" data-tq-advisor-draft="" onClick={onDraft}
          style={{ padding: "1px 4px", fontSize: 12 }}>See the draft</button>}
        <button type="button" className="tq-next-why" aria-haspopup="dialog" aria-expanded={!!at} onClick={(e) => setAt(e.currentTarget)}
          style={{ padding: "1px 4px", fontSize: 12 }}>Why?</button>
      </Box>
      <Popover open={!!at} anchorEl={at} onClose={() => setAt(null)} anchorOrigin={{ vertical: "bottom", horizontal: "left" }}
        transformOrigin={{ vertical: "top", horizontal: "left" }} slotProps={{ paper: { sx: { borderRadius: 2.5, maxWidth: 420 } } }}>
        <div className="tq-next-pop" role="dialog" aria-label="Why the Advisor says this">
          <div className="said">{a.line || note.line}</div>
          {a.label && <div className="pick">Lit: <b>{a.label}</b> - the dark button</div>}
          {/* what it rests on, in words: an evidence id ("out13") or the model's name tells someone who never wrote code nothing */}
          {rests.length ? (
            <div className="rests"><div className="head">What it rests on</div>
              <ul>{rests.map((r) => (
                <li key={r.id} data-tq-advisor-rests={r.kind || ""}>
                  {r.kind === "memory" ? <>What Taskuary knows: “{r.label}”</> : r.label}
                  {memoryMarks(r).length > 0 && (done[r.key] ? <Box component="span" data-tq-advisor-marked={done[r.key]} sx={{ display: "block", color: DIM, fontSize: 12 }}>{MARKED[done[r.key]]}</Box>
                    : <Box component="span" data-tq-advisor-marks="" sx={{ display: "flex", gap: 0.25, mt: 0.25 }}>
                      {memoryMarks(r).map((m) => <button key={m} type="button" className="tq-next-why" data-tq-mark={m} title={MARK_HINT[m]}
                        onClick={() => mark(r, m)} style={{ padding: "1px 6px", fontSize: 12, color: m === "wrong" ? ALERT_INK : undefined }}>{MARKS[m]}</button>)}
                    </Box>)}
                </li>))}</ul></div>)
            : <Box className="fact" sx={{ color: DIM }}>{a.by === "model" ? "Read from this item by the AI." : "A fact Taskuary keeps about this item."}</Box>}
          {err && <Box role="alert" sx={{ color: ALERT_INK, fontSize: 12 }}>{err}</Box>}
        </div>
      </Popover>
    </Box>
  );
}
