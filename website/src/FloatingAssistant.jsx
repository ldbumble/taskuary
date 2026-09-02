import React, { useEffect, useState } from "react";
import { Alert, Box, Button, CircularProgress, IconButton, Tooltip, Typography } from "@mui/material";
import CloseIcon from "@mui/icons-material/Close";
import LaunchIcon from "@mui/icons-material/Launch";
import OpenInFullIcon from "@mui/icons-material/OpenInFull";
import CloseFullscreenIcon from "@mui/icons-material/CloseFullscreen";
import api from "./api.js";
import { TaskuaryMark } from "./ui.jsx";
import { ASSISTANT, BORDER, DIM, GRADIENT, INK, PANEL, PANEL2 } from "./theme.jsx";

const GeneralWorkspace = React.lazy(() => import("./GeneralWorkspace.jsx").then((m) => ({ default: m.GeneralWorkspace })));
const DockActions = React.lazy(() => import("./GeneralWorkspace.jsx").then((m) => ({ default: m.DockActions })));

const STARTERS = [
  ["Walk through it all", "Walk me through everything that is open and needs attention. Cover exactly one item at a time: explain the context and recommendation, ask me the one question needed for that item, then stop and wait for my answer before continuing."],
  ["Important now", "Walk me through what needs my attention right now. Start with the most consequential item, explain why it matters, and tell me the next action."],
  ["Outstanding tasks", "Review my outstanding tasks. Call out what is waiting, stuck, or has gone quiet, then recommend the order I should handle them."],
  ["End of day", "Give me an executive and concise evening Inbox Brief for emails in my Inbox (Focused and Other) and Sent from the last 8 hours only. Group 1: What I accomplished today (emails sent/responded, meeting invites triaged, emails deleted/archived). Group 2: Top 3 things to focus on tomorrow (based on urgency and importance). Exclude all other folders, bulk/marketing, system notifications, receipts, and blocked senders/keywords. Include invites and flagged messages. Start with two one-sentence roll-ups: Summary of accomplishments (themes + number of invites handled). Summary of top 3 priorities for tomorrow. For each group, list 3–5 bullets in this format: [Sender] — Subject — one-line gist with icons (✅ for completed, 🔍 for priority, 📅 for invite). If a group has no items, omit it entirely. End with a short motivational phrase acknowledging progress."],
];

const errorText = (e) => e?.response?.data?.detail || e?.message || "Taskuary could not open.";

export default function FloatingAssistant({ onNavigate, onChanged, onExpandedChange }) {
  const [open, setOpen] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [mounted, setMounted] = useState(false);
  const [task, setTask] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [prompt, setPrompt] = useState(null);

  const show = () => { setMounted(true); setOpen(true); };
  useEffect(() => { onExpandedChange?.(open && expanded); }, [expanded, onExpandedChange, open]);
  useEffect(() => {
    if (!mounted || task || error) return;
    let live = true;
    api.post("/api/assistant/dock").then(({ data }) => live && setTask(data.task)).catch((e) => live && setError(errorText(e)));
    return () => { live = false; };
  }, [mounted, task, error]);
  useEffect(() => {
    if (!open) return undefined;
    const close = (e) => { if (e.key === "Escape") setOpen(false); };
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  }, [open]);

  const ask = (text) => setPrompt({ id: `${Date.now()}-${Math.random()}`, text });
  const go = (tab) => { onNavigate(tab); if (window.innerWidth < 700) setOpen(false); };
  const newChat = async () => {
    const { data } = await api.post("/api/assistant/dock/new");
    setPrompt(null); setBusy(false); setError(""); setTask(data.task);
  };

  return (
    <>
      {mounted && (
        <Box role="dialog" aria-label="Taskuary" aria-hidden={!open}
          sx={{ position: "fixed", zIndex: 1450,
            right: expanded ? 0 : { xs: 8, sm: 20 }, bottom: expanded ? 0 : { xs: 76, sm: 88 },
            width: expanded ? { xs: "100vw", md: "min(760px, 58vw)" } : { xs: "calc(100vw - 16px)", sm: 430 },
            height: expanded ? "100dvh" : { xs: "calc(100dvh - 92px)", sm: "min(680px, calc(100vh - 112px))" },
            display: open ? "flex" : "none", flexDirection: "column", overflow: "hidden",
            bgcolor: PANEL2, border: `1px solid ${BORDER}`, borderRadius: expanded ? 0 : { xs: 2, sm: 3 },
            boxShadow: "0 22px 70px rgba(42, 39, 33, .22), 0 4px 18px rgba(42, 39, 33, .10)" }}>
          <Box sx={{ display: "flex", alignItems: "center", gap: 1, px: 1.35, py: 1.05, color: "white", background: GRADIENT }}>
            <TaskuaryMark size={27} sx={{ boxShadow: "0 1px 5px #0002" }} />
            <Box sx={{ minWidth: 0, flex: 1 }}>
              <Typography sx={{ fontSize: 13.5, lineHeight: 1.2, fontWeight: 800 }}>Taskuary</Typography>
              <Typography sx={{ fontSize: 10.5, opacity: 0.78 }}>{busy ? "Working on your last message…" : "Talk it through. Take action."}</Typography>
            </Box>
            <Tooltip title={expanded ? "Return to compact view" : "Expand beside your workspace"}>
              <IconButton size="small" aria-label={expanded ? "Return Taskuary to compact view" : "Expand Taskuary"}
                onClick={() => setExpanded((v) => !v)} sx={{ color: "white" }}>
                {expanded ? <CloseFullscreenIcon sx={{ fontSize: 17 }} /> : <OpenInFullIcon sx={{ fontSize: 17 }} />}
              </IconButton>
            </Tooltip>
            <IconButton size="small" aria-label="Close Taskuary" onClick={() => setOpen(false)} sx={{ color: "white" }}>
              <CloseIcon sx={{ fontSize: 19 }} />
            </IconButton>
          </Box>
          <Box sx={{ px: 1, py: 0.8, display: "flex", gap: 0.55, flexWrap: "wrap", bgcolor: PANEL, borderBottom: `1px solid ${BORDER}` }}>
            {STARTERS.map(([label, text]) => (
              <Button key={label} size="small" variant="outlined" disabled={!task} onClick={() => ask(text)}
                sx={{ minHeight: 25, px: 0.8, py: 0.2, fontSize: 10.5, textTransform: "none", borderColor: BORDER, color: INK, bgcolor: PANEL2 }}>
                {label}
              </Button>
            ))}
            <Box sx={{ flex: 1 }} />
            {["Timeline", "Tasks", "Review"].map((tab) => (
              <Button key={tab} size="small" endIcon={<LaunchIcon sx={{ fontSize: "12px !important" }} />} onClick={() => go(tab)}
                sx={{ minWidth: 0, px: 0.55, py: 0.2, fontSize: 10.5, color: DIM, textTransform: "none" }}>{tab}</Button>
            ))}
          </Box>
          <Box sx={{ flex: 1, minHeight: 0, display: "flex", flexDirection: "column" }}>
            {!task && !error && <Box sx={{ flex: 1, display: "grid", placeItems: "center" }}><CircularProgress size={22} /></Box>}
            {error && <>
              <Alert severity="error" sx={{ borderRadius: 0 }}>{error}</Alert>
              <React.Suspense fallback={<Box sx={{ flex: 1, display: "grid", placeItems: "center" }}><CircularProgress size={22} /></Box>}>
                <DockActions messages={[]} expanded={expanded} onNavigate={go} onChanged={onChanged} />
              </React.Suspense>
            </>}
            {task && (
              <React.Suspense fallback={<Box sx={{ flex: 1, display: "grid", placeItems: "center" }}><CircularProgress size={22} /></Box>}>
                <GeneralWorkspace task={task} compact dock dockExpanded={expanded} prompt={prompt}
                  onPromptUsed={(id) => setPrompt((p) => p?.id === id ? null : p)}
                  onBusyChange={setBusy} onDockNavigate={go} onDockChanged={onChanged}
                  onDockNewChat={newChat} />
              </React.Suspense>
            )}
          </Box>
        </Box>
      )}
      <Tooltip title={open ? "Taskuary is open" : "Ask Taskuary about your day"} placement="left">
        <Box component="button" aria-label={open ? "Taskuary is open" : "Open Taskuary"} onClick={() => open ? setOpen(false) : show()}
          sx={{ position: "fixed", zIndex: 1451, right: { xs: 14, sm: 24 }, bottom: { xs: 14, sm: 22 },
            width: 52, height: 52, p: 0, borderRadius: "50%", border: "1px solid rgba(255,255,255,.72)",
            display: open && expanded ? "none" : "grid", placeItems: "center", cursor: "pointer", background: GRADIENT,
            boxShadow: "0 10px 28px rgba(69, 79, 70, .30), 0 2px 7px rgba(42, 39, 33, .18)",
            transition: "transform .16s ease, box-shadow .16s ease", "&:hover": { transform: "translateY(-2px) scale(1.03)", boxShadow: "0 13px 32px rgba(69, 79, 70, .36)" },
            "&:focus-visible": { outline: `3px solid ${ASSISTANT.tint}`, outlineOffset: 3 } }}>
          <TaskuaryMark size={37} />
          {busy && <Box sx={{ position: "absolute", right: 0, top: 0, width: 12, height: 12, borderRadius: "50%", bgcolor: "#c89b43", border: "2px solid white" }} />}
        </Box>
      </Tooltip>
    </>
  );
}
