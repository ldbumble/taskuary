import React, { useEffect, useLayoutEffect, useState } from "react";
import { Alert, Box, Button, CircularProgress, IconButton, Tooltip, Typography } from "@mui/material";
import CloseIcon from "@mui/icons-material/Close";
import LaunchIcon from "@mui/icons-material/Launch";
import OpenInFullIcon from "@mui/icons-material/OpenInFull";
import CloseFullscreenIcon from "@mui/icons-material/CloseFullscreen";
import api from "./api.js";
import { lazyGeneral } from "./lazyGeneral.js";
import { TaskuaryMark } from "./ui.jsx";
import { ASSISTANT, BORDER, DIM, GRADIENT, INK, PANEL, PANEL2 } from "./theme.jsx";

const GeneralWorkspace = React.lazy(lazyGeneral("GeneralWorkspace"));
const DockActions = React.lazy(lazyGeneral("DockActions"));

const STARTERS = [
  ["Walk through", "walk"],
  ["Add", "add"],
  ["Set up report", "report"],
];

const WALKTHROUGHS = [
  ["Inbox", "Walk me through the emails that need my attention, exactly one email at a time. Name the sender and subject, explain what they need, recommend the next action, and show the matching reply or task action when one is available. Ask one question, then stop and wait for my answer."],
  ["Tasks", "Walk me through my outstanding tasks, exactly one task at a time. Start with the most consequential or stuck task, explain its state and the next action, show its task action card, ask one question, then stop and wait for my answer."],
  ["Agent work", "Walk me through recent agent work, exactly one result at a time. Explain what the agent changed or found, what remains unresolved, and which action I should take next. Ask one question, then stop and wait for my answer."],
  ["Review", "Walk me through items waiting in Review, exactly one item at a time. Name the rv number and its task when available so the action card shows the exact draft. Explain the decision, recommend Send, Redraft, or Dismiss, ask one question, then stop and wait for my answer."],
];

const errorText = (e) => e?.response?.data?.detail || e?.message || "Taskuary could not open.";

export default function FloatingAssistant({ onNavigate, onChanged, activeTab }) {
  const [open, setOpen] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [mounted, setMounted] = useState(false);
  const [task, setTask] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [prompt, setPrompt] = useState(null);
  const [picker, setPicker] = useState("");
  const [expandedBounds, setExpandedBounds] = useState(null);

  // The bubble is a DOOR now, not a second assistant: the Assistant tab is where the conversation
  // lives, and a dock over another page was one more place for the same chat to be (the owner,
  // 2026-09-03: "it should take you to the assistant tab. No more pop up"). The panel below is kept
  // for the places that still mount it with a task of their own.
  const show = () => onNavigate?.("Assistant");
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
  useLayoutEffect(() => {
    if (!open || !expanded) { setExpandedBounds(null); return undefined; }
    const measure = () => {
      // (the Timeline's stage lives on the Assistant tab now, where this bubble is never mounted -
      // so the expanded panel always takes the window's own right-hand side)
      void activeTab;
      if (window.innerWidth < 900) {
        setExpandedBounds({ left: 0, top: 0, width: window.innerWidth, height: window.innerHeight });
        return;
      }
      const navBottom = document.getElementById("tqTopNav")?.getBoundingClientRect().bottom || 49;
      const left = Math.min(528, Math.round(window.innerWidth * 0.42));
      setExpandedBounds({ left, top: navBottom + 14, width: Math.max(320, window.innerWidth - left - 14),
        height: Math.max(320, window.innerHeight - navBottom - 28) });
    };
    measure();
    const stage = document.querySelector("[data-tq-timeline-stage]");
    const nav = document.getElementById("tqTopNav");
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(measure);
    if (stage) observer?.observe(stage);
    if (nav) observer?.observe(nav);
    window.addEventListener("resize", measure);
    return () => { observer?.disconnect(); window.removeEventListener("resize", measure); };
  }, [activeTab, expanded, open]);

  const ask = (text) => {
    setPicker("");
    setPrompt({ id: `${Date.now()}-${Math.random()}`, text });
  };
  const go = (tab) => { setPicker(""); onNavigate(tab); if (window.innerWidth < 700) setOpen(false); };
  const addTask = () => { window.location.hash = "new-task"; go("Tasks"); };
  const addReport = () => { window.location.hash = "report=new"; go("Reports"); };
  const chooseStarter = (kind) => {
    if (kind === "report") { addReport(); return; }
    setPicker((old) => old === kind ? "" : kind);
  };
  const newChat = async () => {
    const { data } = await api.post("/api/assistant/dock/new");
    setPrompt(null); setPicker(""); setBusy(false); setError(""); setTask(data.task);
  };

  return (
    <>
      {mounted && (
        <Box role="dialog" aria-label="Taskuary" aria-hidden={!open}
          sx={{ position: "fixed", zIndex: 1450,
            right: expanded ? "auto" : { xs: 8, sm: 20 }, bottom: expanded ? "auto" : { xs: 76, sm: 88 },
            left: expanded ? `${expandedBounds?.left || 0}px` : "auto",
            top: expanded ? `${expandedBounds?.top || 0}px` : "auto",
            width: expanded ? `${expandedBounds?.width || window.innerWidth}px` : { xs: "calc(100vw - 16px)", sm: 430 },
            height: expanded ? `${expandedBounds?.height || window.innerHeight}px` : { xs: "calc(100dvh - 92px)", sm: "min(680px, calc(100vh - 112px))" },
            display: open ? "flex" : "none", flexDirection: "column", overflow: "hidden",
            bgcolor: PANEL2, border: `1px solid ${BORDER}`, borderRadius: expanded ? { xs: 0, md: 2 } : { xs: 2, sm: 3 },
            boxShadow: "0 22px 70px rgba(42, 39, 33, .22), 0 4px 18px rgba(42, 39, 33, .10)" }}>
          <Box sx={{ display: "flex", alignItems: "center", gap: 1, px: 1.35, py: 1.05, color: "white", background: GRADIENT }}>
            <TaskuaryMark size={27} sx={{ boxShadow: "0 1px 5px #0002" }} />
            <Box sx={{ minWidth: 0, flex: 1 }}>
              <Typography sx={{ fontSize: 13.5, lineHeight: 1.2, fontWeight: 800 }}>Taskuary</Typography>
              <Typography sx={{ fontSize: 10.5, opacity: 0.78 }}>{busy ? "Working on your last message…" : "Talk it through. Take action."}</Typography>
            </Box>
            <Tooltip title={expanded ? "Return to compact view" : "Fill the workspace beside Timeline"}>
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
            {STARTERS.map(([label, kind]) => (
              <Button key={label} size="small" variant={picker === kind ? "contained" : "outlined"}
                disabled={!task} onClick={() => chooseStarter(kind)}
                sx={{ minHeight: 25, px: 0.8, py: 0.2, fontSize: 10.5, textTransform: "none", borderColor: BORDER, color: INK, bgcolor: PANEL2 }}>
                {label}
              </Button>
            ))}
            <Box sx={{ flex: 1 }} />
            {["Assistant", "Tasks", "Review"].map((tab) => (
              <Button key={tab} size="small" endIcon={<LaunchIcon sx={{ fontSize: "12px !important" }} />} onClick={() => go(tab)}
                sx={{ minWidth: 0, px: 0.55, py: 0.2, fontSize: 10.5, color: DIM, textTransform: "none" }}>{tab}</Button>
            ))}
          </Box>
          {picker && (
            <Box sx={{ px: 1, py: 0.7, display: "flex", alignItems: "center", gap: 0.55, flexWrap: "wrap",
              bgcolor: PANEL2, borderBottom: `1px solid ${BORDER}` }}>
              <Typography sx={{ mr: 0.25, color: DIM, fontSize: 10.5 }}>
                {picker === "walk" ? "Where should we start?" : "What do you want to add?"}
              </Typography>
              {picker === "walk" ? WALKTHROUGHS.map(([label, text]) => (
                <Button key={label} size="small" variant="outlined" onClick={() => ask(text)}
                  sx={{ minHeight: 25, px: 0.8, py: 0.2, fontSize: 10.5, textTransform: "none" }}>{label}</Button>
              )) : <>
                <Button size="small" variant="outlined" onClick={addTask}
                  sx={{ minHeight: 25, px: 0.8, py: 0.2, fontSize: 10.5, textTransform: "none" }}>Task</Button>
                <Button size="small" variant="outlined" onClick={addReport}
                  sx={{ minHeight: 25, px: 0.8, py: 0.2, fontSize: 10.5, textTransform: "none" }}>Report</Button>
                <Button size="small" variant="outlined" onClick={() => go("Connections")}
                  sx={{ minHeight: 25, px: 0.8, py: 0.2, fontSize: 10.5, textTransform: "none" }}>Connection</Button>
              </>}
            </Box>
          )}
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
