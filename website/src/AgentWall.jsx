// THE WALL — what the agents are telling each other.
//
// The board already shows what agents ARE doing, read off git and the run trace: who holds
// which file, who is busy. That is true and about as expressive as a security camera. It
// cannot say "the migration is half applied, don't run the tests yet" or "this is green, safe
// to build on" — only the agent doing the work knows that. So they write it down here, one
// line at a time, and the next agent reads the wall before it touches anything (CODER.md, and
// `taskuary --board` in its own terminal).
//
// It reads like a feed on purpose: a coding agent leaving a note for the next one IS a message
// to a colleague, and a timeline of short messages with a face beside each is the form everyone
// already knows how to read. Colour identifies — a dot, a chip — and never floods a surface.
import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Box, Button, CircularProgress, MenuItem, Select, TextField, Tooltip, Typography } from "@mui/material";
import SendIcon from "@mui/icons-material/ArrowUpward";
import PersonOutlineIcon from "@mui/icons-material/PersonOutline";
import api from "./api";
import { BORDER, DIM, FAINT, INK, PANEL, PANEL2, card, mono } from "./theme.jsx";
import { Empty, timeAgo, TaskuaryMark } from "./ui.jsx";

// what a note IS, in the agents' own vocabulary. The colour is a dot beside the word, never a
// wash over the card: one oxblood surface in this app means ALERT, and a note is not an alert.
export const KINDS = {
  working: { label: "working on", dot: "#55697a", hint: "what it is doing right now" },
  note: { label: "note", dot: "#8a7a5c", hint: "anything the next agent needs" },
  blocked: { label: "blocked", dot: "#a2643a", hint: "waiting on something or someone" },
  ready: { label: "ready to push", dot: "#6f8a6e", hint: "finished and safe to build on" },
  done: { label: "done", dot: "#9c968c", hint: "pushed or closed out" },
  // not written by an agent: what a day of notes was folded into, so the wall an agent reads
  // tomorrow is what still matters rather than everything that was ever true (blackboard.roll_up)
  summary: { label: "the day, folded", dot: "#7a5f6b", hint: "a day of notes, summarised - the originals are still here under “show every note”" },
};

// one stable colour per agent, so the same face means the same worker down the whole feed
const AVATAR = ["#55697a", "#6f8a6e", "#8a7a5c", "#7a5f6b", "#4f6f79", "#8a6a4a"];
export const faceOf = (name) => {
  const s = String(name || "agent");
  let n = 0;
  for (const ch of s) n = (n * 31 + ch.charCodeAt(0)) % 9973;
  return { bg: AVATAR[n % AVATAR.length], letter: (s.trim()[0] || "a").toUpperCase() };
};

const short = (p) => String(p || "").split(/[\\/]/).filter(Boolean).slice(-1)[0] || "";
const dayOf = (t) => String(t || "").slice(0, 10);

const Face = ({ who, size = 30 }) => {
  const owner = /^(you|owner|dana whitfield)$/i.test(String(who || "").trim());
  return (
    <Box sx={{ width: size, height: size, borderRadius: "50%", bgcolor: owner ? "#eae4d8" : PANEL2,
      border: `1px solid ${BORDER}`, color: DIM, flexShrink: 0, display: "grid", placeItems: "center" }}>
      {owner ? <PersonOutlineIcon sx={{ fontSize: size * 0.58 }} /> : <TaskuaryMark size={size * 0.64} />}
    </Box>
  );
};

const Kind = ({ kind }) => {
  const k = KINDS[kind] || KINDS.note;
  return (
    <Tooltip title={k.hint}>
      <Box sx={{ display: "inline-flex", alignItems: "center", gap: 0.55, px: 0.85, height: 19, borderRadius: 99,
        border: `1px solid ${BORDER}`, bgcolor: PANEL, flexShrink: 0 }}>
        <Box sx={{ width: 6, height: 6, borderRadius: "50%", bgcolor: k.dot }} />
        <Typography sx={{ fontSize: 10, fontWeight: 700, color: DIM, letterSpacing: 0.2 }}>{k.label}</Typography>
      </Box>
    </Tooltip>
  );
};

const Note = ({ n, onOpenTask }) => {
  const read = String(n.ReadBy || "").split(",").filter(Boolean);
  return (
    <Box sx={{ display: "flex", gap: 1.25, py: 1.5, borderBottom: `1px solid ${BORDER}` }}>
      <Face who={n.Agent} />
      <Box sx={{ minWidth: 0, flex: 1 }}>
        <Box sx={{ display: "flex", alignItems: "center", gap: 0.85, flexWrap: "wrap" }}>
          <Typography sx={{ fontSize: 12.5, fontWeight: 700, color: INK }}>{n.Agent}</Typography>
          <Kind kind={n.Kind} />
          {!!n.TaskId && (
            <Typography onClick={() => onOpenTask?.(n.TaskId)}
              sx={{ ...mono, fontSize: 10.5, color: "#55697a", cursor: onOpenTask ? "pointer" : "default",
                "&:hover": { textDecoration: onOpenTask ? "underline" : "none" } }}>
              TQ-{String(n.TaskId).padStart(4, "0")}
            </Typography>
          )}
          <Box sx={{ flex: 1 }} />
          <Typography sx={{ fontSize: 10.5, color: FAINT }}>{timeAgo(n.CreatedAt)}</Typography>
        </Box>
        <Typography sx={{ fontSize: 13, color: INK, mt: 0.4, whiteSpace: "pre-wrap", wordBreak: "break-word" }}>
          {n.Body}
        </Typography>
        <Box sx={{ display: "flex", alignItems: "center", gap: 0.6, mt: 0.5, flexWrap: "wrap" }}>
          {String(n.Files || "").split(",").filter(Boolean).slice(0, 6).map((f) => (
            <Typography key={f} sx={{ ...mono, fontSize: 10, color: DIM, bgcolor: PANEL2,
              border: `1px solid ${BORDER}`, borderRadius: 1, px: 0.6, py: 0.1 }}>{short(f)}</Typography>
          ))}
          {n.Cwd && n.Cwd !== "." && (
            <Tooltip title={n.Cwd}>
              <Typography sx={{ ...mono, fontSize: 10, color: FAINT }}>{short(n.Cwd)}</Typography>
            </Tooltip>
          )}
          {!!read.length && (
            <Typography sx={{ fontSize: 10, color: FAINT }}>· read by {read.join(", ")}</Typography>
          )}
        </Box>
      </Box>
    </Box>
  );
};

export default function AgentWall({ onOpenTask, refresh }) {
  const [rows, setRows] = useState(null);
  const [body, setBody] = useState("");
  const [kind, setKind] = useState("note");
  const [busy, setBusy] = useState(false);
  const [all, setAll] = useState(false);      // composted days too, or just what still matters
  const load = useCallback(async () => {
    try { setRows((await api.get("/api/board/notes", { params: { all } })).data.data || []); }
    catch { setRows([]); }
  }, [all]);
  useEffect(() => { load(); }, [load, refresh]);
  useEffect(() => { const t = setInterval(load, 10000); return () => clearInterval(t); }, [load]);

  const post = async () => {
    if (!body.trim()) return;
    setBusy(true);
    try { await api.post("/api/board/notes", { body, kind, agent: "you" }); setBody(""); await load(); }
    catch { /* the box keeps the words */ }
    setBusy(false);
  };

  // newest first from the API; the feed reads down the way a conversation does, per day
  const days = useMemo(() => {
    const by = new Map();
    for (const n of rows || []) {
      const d = dayOf(n.CreatedAt);
      if (!by.has(d)) by.set(d, []);
      by.get(d).push(n);
    }
    return [...by.entries()];
  }, [rows]);

  if (rows === null) return <CircularProgress size={22} sx={{ m: 4 }} />;
  return (
    <Box sx={{ maxWidth: 780, mx: "auto" }}>
      <Box sx={{ ...card, p: 1.5, mb: 1.5 }}>
        <Box sx={{ display: "flex", gap: 1.25, alignItems: "flex-start" }}>
          <Face who="you" />
          <TextField fullWidth multiline maxRows={4} size="small" value={body} placeholder="Leave a live handoff for the agents…"
            onChange={(e) => setBody(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); post(); } }}
            sx={{ bgcolor: "#fff", "& textarea": { fontSize: 13 } }} />
        </Box>
        <Box sx={{ display: "flex", alignItems: "center", gap: 1, mt: 1, pl: 5.5 }}>
          <Select size="small" value={kind} onChange={(e) => setKind(e.target.value)}
            sx={{ bgcolor: "#fff", fontSize: 12, height: 30, minWidth: 150 }}>
            {Object.entries(KINDS).filter(([k]) => k !== "summary").map(([k, v]) => (
              <MenuItem key={k} value={k} sx={{ fontSize: 12 }}>
                <Box component="span" sx={{ display: "inline-block", width: 7, height: 7, borderRadius: "50%",
                  bgcolor: v.dot, mr: 1 }} />{v.label}
              </MenuItem>
            ))}
          </Select>
          <Typography variant="caption" sx={{ color: FAINT, flex: 1 }}>
            Task-specific and short-lived; hard-earned durable knowledge belongs in the Hub. Agents post here with <code>taskuary --note</code>.
          </Typography>
          {/* the older days are still here, folded - one summary each, per checkout */}
          <Button size="small" onClick={() => setAll((x) => !x)} sx={{ fontSize: 11, color: DIM, textTransform: "none" }}>
            {all ? "just what still matters" : "show every note"}
          </Button>
          <Button size="small" variant="contained" disableElevation disabled={busy || !body.trim()} onClick={post}
            endIcon={<SendIcon sx={{ fontSize: 15 }} />}>Post</Button>
        </Box>
      </Box>

      {!rows.length ? (
        <Empty>
          Nothing on the wall yet. Agents post here as they work — what they are taking, what they
          found, and “ready to push” when a tree is safe to build on — and read it before they start.
        </Empty>
      ) : days.map(([day, notes]) => (
        <Box key={day} sx={{ mb: 1 }}>
          <Typography sx={{ ...mono, fontSize: 10.5, color: FAINT, letterSpacing: 1, textTransform: "uppercase", mb: 0.25 }}>
            {day}
          </Typography>
          <Box sx={{ ...card, py: 0, px: 1.5 }}>
            {notes.map((n) => <Note key={n.NoteId} n={n} onOpenTask={onOpenTask} />)}
          </Box>
        </Box>
      ))}
    </Box>
  );
}
