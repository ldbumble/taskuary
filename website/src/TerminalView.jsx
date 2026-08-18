// Real terminals in the app: xterm.js over a websocket over a pty. There is no Terminal
// "tab" on purpose - a terminal belongs to the work. A board card or a task page opens the
// session for its own repo, and it appears in the dock at the bottom of whatever you were
// looking at (Ctrl+`). The pty lives server-side, so nothing dies when you navigate.
import React, { useCallback, useEffect, useRef, useState } from "react";
import { Box, Button, Checkbox, FormControlLabel, IconButton, Typography } from "@mui/material";
import { Terminal } from "@xterm/xterm";
import { FitAddon } from "@xterm/addon-fit";
import { WebLinksAddon } from "@xterm/addon-web-links";
import { Unicode11Addon } from "@xterm/addon-unicode11";
import "@xterm/xterm/css/xterm.css";
import AddIcon from "@mui/icons-material/Add";
import CloseIcon from "@mui/icons-material/Close";
import TerminalIcon from "@mui/icons-material/Terminal";
import api from "./api";
import { BORDER, CATPPUCCIN, DIM, FAINT, PANEL, XTERM_THEME, mono } from "./theme.jsx";
import { useAgents } from "./ui.jsx";

// Programming fonts first: agent TUIs draw boxes and progress bars out of block glyphs,
// which only line up in a font with real box-drawing coverage.
const TERM_FONT = "'Cascadia Mono', 'JetBrains Mono', 'Fira Code', Consolas, 'Courier New', monospace";

const wsUrl = (sid) => {
  const t = localStorage.getItem("taskuary_token");
  return `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/api/terminals/${sid}/ws${t ? `?token=${encodeURIComponent(t)}` : ""}`;
};

// One live session. Mounts xterm once, streams both ways, resizes the pty to the pane.
export const TerminalPane = ({ sid, height = "70vh", onExit }) => {
  const host = useRef(null);
  const [state, setState] = useState("connecting");
  useEffect(() => {
    const term = new Terminal({ fontSize: 12.5, fontFamily: TERM_FONT, fontWeightBold: 600,
      theme: XTERM_THEME, cursorBlink: true, cursorStyle: "bar", scrollback: 10000,
      allowProposedApi: true, drawBoldTextInBrightColors: false, letterSpacing: 0, lineHeight: 1.15 });
    const fit = new FitAddon();
    term.loadAddon(fit);
    term.loadAddon(new WebLinksAddon((_e, uri) => window.open(uri, "_blank", "noopener")));
    const uni = new Unicode11Addon();
    term.loadAddon(uni);
    term.unicode.activeVersion = "11";              // emoji + box glyphs measure correctly
    term.open(host.current);
    // No WebGL renderer here on purpose: it renders nothing at all on software-GL stacks
    // (WebView2 without a GPU, remote desktop, headless), and a blank terminal is a much
    // worse failure than a few dropped frames. The DOM renderer draws the same colors.
    fit.fit();
    const ws = new WebSocket(wsUrl(sid));
    const send = (m) => ws.readyState === 1 && ws.send(JSON.stringify(m));
    ws.onopen = () => { setState("live"); send({ type: "resize", rows: term.rows, cols: term.cols }); };
    ws.onmessage = (e) => {
      const m = JSON.parse(e.data);
      if (m.type === "out") term.write(m.data);
      else if (m.type === "exit") { setState("exited"); term.write("\r\n\x1b[90m— process exited —\x1b[0m\r\n"); onExit?.(); }
    };
    ws.onclose = () => setState((s) => (s === "exited" ? s : "closed"));
    term.onData((d) => send({ type: "in", data: d }));
    const onResize = () => { fit.fit(); send({ type: "resize", rows: term.rows, cols: term.cols }); };
    window.addEventListener("resize", onResize);
    const ro = new ResizeObserver(onResize);
    ro.observe(host.current);
    term.focus();
    return () => { window.removeEventListener("resize", onResize); ro.disconnect(); ws.close(); term.dispose(); };
  }, [sid, onExit]);
  return (
    <Box sx={{ position: "relative", border: `1px solid ${BORDER}`, borderRadius: 2, overflow: "hidden", bgcolor: CATPPUCCIN.bg }}>
      <Box ref={host} sx={{ height, p: 1, "& .xterm": { height: "100%" } }} />
      {state !== "live" && (
        <Typography variant="caption" sx={{ ...mono, position: "absolute", top: 6, right: 10, fontSize: 10,
          color: state === "exited" ? CATPPUCCIN.green : CATPPUCCIN.yellow }}>
          {state}
        </Typography>
      )}
    </Box>
  );
};

/* ── the dock: a terminal panel at the bottom of the app, on every tab ──────────
   VS Code / Cloud Shell shape - drag its top edge to resize, tabs for parallel
   sessions, and it keeps running while you work elsewhere in the app (the pty lives
   server-side, so switching tabs or closing the dock never kills a session). */
export const TerminalDock = ({ open, onClose, request, onRequestDone, height: h, onHeight: setH }) => {
  const [sessions, setSessions] = useState([]);
  const [sid, setSid] = useState(null);
  const [err, setErr] = useState("");
  const { agents } = useAgents();
  const drag = useRef(null);

  const load = useCallback(async () => {
    try {
      const rows = (await api.get("/api/terminals")).data.data || [];
      setSessions(rows);
      setSid((cur) => (rows.some((s) => s.sid === cur) ? cur : rows[rows.length - 1]?.sid || null));
    } catch { /* the dock is optional UI - never block the app on it */ }
  }, []);
  useEffect(() => { if (open) load(); }, [open, load]);

  const start = useCallback(async (body) => {
    setErr("");
    try { setSid((await api.post("/api/terminals", body)).data.sid); load(); }
    catch (e) { setErr(e?.response?.data?.detail || "Could not start a terminal"); }
  }, [load]);
  useEffect(() => { if (open && request) { start(request); onRequestDone?.(); } }, [open, request, start, onRequestDone]);

  // drag the top edge; the pty is told its new size by the pane's ResizeObserver
  useEffect(() => {
    const move = (e) => { if (drag.current != null) setH(Math.min(Math.max(160, drag.current - e.clientY), window.innerHeight - 120)); };
    const up = () => { drag.current = null; };
    window.addEventListener("mousemove", move); window.addEventListener("mouseup", up);
    return () => { window.removeEventListener("mousemove", move); window.removeEventListener("mouseup", up); };
  }, []);

  if (!open) return null;
  const cur = sessions.find((s) => s.sid === sid);
  const kill = async (s) => { await api.delete(`/api/terminals/${s}`).catch(() => {}); load(); };
  return (
    <Box sx={{ position: "fixed", left: 0, right: 0, bottom: 0, zIndex: 1200, height: h,
      bgcolor: CATPPUCCIN.bg, borderTop: `1px solid ${BORDER}`, boxShadow: "0 -8px 30px rgba(16,24,40,.25)",
      display: "flex", flexDirection: "column" }}>
      <Box onMouseDown={(e) => { drag.current = h + e.clientY; }}
        sx={{ height: 6, cursor: "ns-resize", bgcolor: CATPPUCCIN.bgAlt, "&:hover": { bgcolor: CATPPUCCIN.surface } }} />
      <Box sx={{ display: "flex", alignItems: "center", gap: 0.75, px: 1, py: 0.5, bgcolor: CATPPUCCIN.bgAlt, flexWrap: "wrap" }}>
        {sessions.map((s) => (
          <Box key={s.sid} onClick={() => setSid(s.sid)}
            sx={{ display: "flex", alignItems: "center", gap: 0.5, px: 1, py: 0.3, borderRadius: 1,
              cursor: "pointer", bgcolor: s.sid === sid ? CATPPUCCIN.bg : "transparent",
              border: `1px solid ${s.sid === sid ? CATPPUCCIN.surface : "transparent"}` }}>
            <TerminalIcon sx={{ fontSize: 13, color: s.alive ? CATPPUCCIN.cyan : CATPPUCCIN.faint }} />
            <Typography variant="caption" sx={{ ...mono, color: s.sid === sid ? CATPPUCCIN.fg : CATPPUCCIN.dim, fontSize: 11 }} noWrap>
              {s.label}{s.taskId ? ` · TQ-${String(s.taskId).padStart(4, "0")}` : ""}
            </Typography>
            <CloseIcon onClick={(e) => { e.stopPropagation(); kill(s.sid); }}
              sx={{ fontSize: 12, color: CATPPUCCIN.faint, "&:hover": { color: CATPPUCCIN.red } }} />
          </Box>
        ))}
        <Button size="small" startIcon={<AddIcon sx={{ fontSize: 14 }} />} onClick={() => start({ agent: null })}
          sx={{ fontSize: 11, color: CATPPUCCIN.dim }}>shell</Button>
        {agents.map((a) => (
          <Button key={a} size="small" startIcon={<AddIcon sx={{ fontSize: 14 }} />} onClick={() => start({ agent: a })}
            sx={{ fontSize: 11, color: CATPPUCCIN.mauve }}>{a}</Button>
        ))}
        <Box sx={{ flex: 1 }} />
        {err && <Typography variant="caption" sx={{ color: CATPPUCCIN.red }}>{err}</Typography>}
        <Typography variant="caption" sx={{ ...mono, color: CATPPUCCIN.faint, fontSize: 10.5 }} noWrap>{cur?.cwd || ""}</Typography>
        <IconButton size="small" onClick={onClose} title="Hide the terminal (sessions keep running)">
          <CloseIcon sx={{ fontSize: 15, color: CATPPUCCIN.dim }} />
        </IconButton>
      </Box>
      <Box sx={{ flex: 1, minHeight: 0 }}>
        {!cur
          ? <Typography variant="caption" sx={{ color: CATPPUCCIN.faint, display: "block", p: 2 }}>
              No session — start a shell, or one of your agents, above.
            </Typography>
          : <TerminalPane key={cur.sid} sid={cur.sid} height="100%" onExit={load} />}
      </Box>
    </Box>
  );
};

// Taskuary paints its terminals in Catppuccin Mocha. Claude Code's own theme is set
// inside Claude Code, so this is a command to run there - not something to write into
// somebody's global CLI config behind their back.
export const ThemeHint = () => (
  <Typography variant="caption" sx={{ color: FAINT, display: "block", mt: 1.5 }}>
    Terminals here use the Catppuccin Mocha palette. To match it inside Claude Code itself,
    run{" "}
    <Box component="code" sx={{ ...mono, bgcolor: PANEL, border: `1px solid ${BORDER}`, borderRadius: 1,
      px: 0.75, py: 0.25, fontSize: 11, cursor: "pointer" }}
      title="click to copy"
      onClick={() => navigator.clipboard?.writeText("/plugin install catppuccin@matcra587/claude-themes")}>
      /plugin install catppuccin@matcra587/claude-themes
    </Box>{" "}
    in a Claude Code session, then pick a flavor with /theme.
  </Typography>
);

// Small control other views drop in: "open a real terminal on this task".
export const OpenTerminalButton = ({ taskId, repo, agent, onOpen, label = "Open a terminal here" }) => {
  const [seed, setSeed] = useState(true);
  return (
    <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
      <Button size="small" startIcon={<TerminalIcon sx={{ fontSize: 14 }} />}
        onClick={() => onOpen({ agent: agent || "coder", task_id: taskId, repo: repo || null, seed })}
        sx={{ fontSize: 11.5, color: "#0e7490" }}>{label}</Button>
      <FormControlLabel sx={{ m: 0 }} control={<Checkbox size="small" checked={seed} onChange={(e) => setSeed(e.target.checked)} sx={{ p: 0.5 }} />}
        label={<Typography variant="caption" sx={{ color: FAINT }}>start it on this task</Typography>} />
    </Box>
  );
};
