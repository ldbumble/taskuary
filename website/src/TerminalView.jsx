// Real terminals in the app: xterm.js over a websocket over a pty. Open your coding CLI
// (or a plain shell) in a repo, watch it work, type back at it - the same session the
// agent is in, not a transcript of one.
import React, { useCallback, useEffect, useRef, useState } from "react";
import { Alert, Box, Button, Checkbox, FormControlLabel, IconButton, MenuItem, Select, TextField, Typography } from "@mui/material";
import { Terminal } from "@xterm/xterm";
import { FitAddon } from "@xterm/addon-fit";
import { WebLinksAddon } from "@xterm/addon-web-links";
import { Unicode11Addon } from "@xterm/addon-unicode11";
import "@xterm/xterm/css/xterm.css";
import AddIcon from "@mui/icons-material/Add";
import CloseIcon from "@mui/icons-material/Close";
import TerminalIcon from "@mui/icons-material/Terminal";
import api from "./api";
import { BORDER, DIM, FAINT, INK, PANEL, card, mono } from "./theme.jsx";
import { Empty, useAgents } from "./ui.jsx";

// A full 16-colour ANSI palette, not a partial one: agent CLIs paint their whole TUI with
// these (spinners, diffs, boxes, syntax), so leaving the brights undefined makes their
// output look flat and washed out.
const XTERM_THEME = {
  background: "#0b1020", foreground: "#d7dcea", cursor: "#22d3ee", cursorAccent: "#0b1020",
  selectionBackground: "#3b4a7a", selectionForeground: "#ffffff",
  black: "#0b1020", red: "#f87171", green: "#4ade80", yellow: "#fbbf24", blue: "#60a5fa",
  magenta: "#c084fc", cyan: "#22d3ee", white: "#cbd5e1",
  brightBlack: "#64748b", brightRed: "#fca5a5", brightGreen: "#86efac", brightYellow: "#fde68a",
  brightBlue: "#93c5fd", brightMagenta: "#e9d5ff", brightCyan: "#a5f3fc", brightWhite: "#f8fafc",
};
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
    <Box sx={{ position: "relative", border: `1px solid ${BORDER}`, borderRadius: 2, overflow: "hidden", bgcolor: "#0f172a" }}>
      <Box ref={host} sx={{ height, p: 1, "& .xterm": { height: "100%" } }} />
      {state !== "live" && (
        <Typography variant="caption" sx={{ ...mono, position: "absolute", top: 6, right: 10, fontSize: 10,
          color: state === "exited" ? "#86efac" : "#fcd34d" }}>
          {state}
        </Typography>
      )}
    </Box>
  );
};

export default function TerminalView({ startWith, onStarted }) {
  const [sessions, setSessions] = useState([]);
  const [sid, setSid] = useState(null);
  const [agents, setAgents] = useState([]);
  const [repos, setRepos] = useState([]);
  const [err, setErr] = useState("");
  const [draft, setDraft] = useState({ agent: "coder", repo: "", cwd: "", seed: false, task_id: null });

  const load = useCallback(async () => {
    try { setSessions((await api.get("/api/terminals")).data.data || []); }
    catch (e) { setErr(e?.response?.data?.detail || "Failed to list terminals"); }
  }, []);
  useEffect(() => { load(); const t = setInterval(load, 5000); return () => clearInterval(t); }, [load]);
  useEffect(() => {
    api.get("/api/agents").then(({ data }) => {
      const ns = (data.data || []).map((a) => a.Name);
      setAgents(ns);
      if (ns.length && !ns.includes("coder")) setDraft((d) => ({ ...d, agent: ns[0] }));
    }).catch(() => {});
    api.get("/api/sources").then(({ data }) => {
      const gh = (data.data || []).filter((s) => s.Channel === "github" && s.Active).map((s) => s.Address);
      setRepos(gh);
      const def = data.default_repo && gh.includes(data.default_repo) ? data.default_repo : gh[0];
      if (def) setDraft((d) => ({ ...d, repo: def }));
    }).catch(() => {});
  }, []);

  const open = useCallback(async (body) => {
    setErr("");
    try {
      const { data } = await api.post("/api/terminals", body);
      setSid(data.sid); load();
      return data;
    } catch (e) { setErr(e?.response?.data?.detail || "Could not start a terminal"); }
  }, [load]);
  // opened from a task ("open a terminal here") - fire once, then clear the request
  useEffect(() => { if (startWith) { open(startWith); onStarted?.(); } }, [startWith, open, onStarted]);

  const kill = async (s) => { await api.delete(`/api/terminals/${s}`).catch(() => {}); if (sid === s) setSid(null); load(); };
  const cur = sessions.find((s) => s.sid === sid);

  return (
    <Box>
      <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 2, flexWrap: "wrap" }}>
        <Typography sx={{ color: INK, fontWeight: 800, fontSize: 17, mr: 1 }}>Terminal</Typography>
        {agents.length > 0 && (
          <Select size="small" value={draft.agent} onChange={(e) => setDraft({ ...draft, agent: e.target.value })}
            sx={{ fontSize: 12, height: 30, bgcolor: PANEL }}>
            {agents.map((a) => <MenuItem key={a} value={a} sx={{ fontSize: 12.5 }}>{a}</MenuItem>)}
            <MenuItem value="" sx={{ fontSize: 12.5 }}>plain shell</MenuItem>
          </Select>
        )}
        {repos.length > 0 && (
          <Select size="small" value={draft.repo} displayEmpty onChange={(e) => setDraft({ ...draft, repo: e.target.value })}
            sx={{ fontSize: 12, height: 30, bgcolor: PANEL, maxWidth: 240 }}>
            <MenuItem value="" sx={{ fontSize: 12.5 }}>agent's default folder</MenuItem>
            {repos.map((r) => <MenuItem key={r} value={r} sx={{ fontSize: 12.5 }}>{r}</MenuItem>)}
          </Select>
        )}
        <TextField size="small" placeholder="…or a folder path" value={draft.cwd}
          onChange={(e) => setDraft({ ...draft, cwd: e.target.value })} sx={{ width: 240, bgcolor: PANEL }} />
        <Button size="small" variant="contained" disableElevation startIcon={<AddIcon sx={{ fontSize: 15 }} />}
          onClick={() => open({ agent: draft.agent || null, repo: draft.repo || null, cwd: draft.cwd || null })}>
          Open terminal
        </Button>
      </Box>
      {err && <Alert severity="error" onClose={() => setErr("")} sx={{ mb: 1.5 }}>{err}</Alert>}

      {/* session tabs */}
      {sessions.length > 0 && (
        <Box sx={{ display: "flex", gap: 0.75, mb: 1.25, flexWrap: "wrap" }}>
          {sessions.map((s) => (
            <Box key={s.sid} onClick={() => setSid(s.sid)}
              sx={{ ...card, display: "flex", alignItems: "center", gap: 0.75, px: 1.25, py: 0.5, cursor: "pointer",
                borderColor: s.sid === sid ? "#c9cff0" : BORDER, bgcolor: s.sid === sid ? "#eef0ff" : PANEL }}>
              <TerminalIcon sx={{ fontSize: 14, color: s.alive ? "#0e7490" : FAINT }} />
              <Typography variant="caption" sx={{ fontWeight: 700, color: s.sid === sid ? "#4f46e5" : INK }}>{s.label}</Typography>
              <Typography variant="caption" sx={{ ...mono, color: FAINT, fontSize: 10 }} noWrap>
                {s.taskId ? `TQ-${String(s.taskId).padStart(4, "0")} · ` : ""}{(s.cwd || "").split(/[\\/]/).slice(-1)[0]}
              </Typography>
              <CloseIcon onClick={(e) => { e.stopPropagation(); kill(s.sid); }}
                sx={{ fontSize: 13, color: FAINT, "&:hover": { color: "#b91c1c" } }} />
            </Box>
          ))}
        </Box>
      )}

      {!cur ? (
        <Empty>No terminal open — pick an agent and a folder above, then Open terminal. It runs the CLI for real: its prompts, its questions, your keystrokes.</Empty>
      ) : (
        <>
          <Typography variant="caption" sx={{ ...mono, color: DIM, display: "block", mb: 0.5 }}>
            {cur.cmd} · {cur.cwd}
          </Typography>
          <TerminalPane key={cur.sid} sid={cur.sid} onExit={load} />
        </>
      )}
    </Box>
  );
}

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
      bgcolor: "#0b1020", borderTop: `1px solid ${BORDER}`, boxShadow: "0 -8px 30px rgba(16,24,40,.25)",
      display: "flex", flexDirection: "column" }}>
      <Box onMouseDown={(e) => { drag.current = h + e.clientY; }}
        sx={{ height: 6, cursor: "ns-resize", bgcolor: "#111a33", "&:hover": { bgcolor: "#1e293b" } }} />
      <Box sx={{ display: "flex", alignItems: "center", gap: 0.75, px: 1, py: 0.5, bgcolor: "#111a33", flexWrap: "wrap" }}>
        {sessions.map((s) => (
          <Box key={s.sid} onClick={() => setSid(s.sid)}
            sx={{ display: "flex", alignItems: "center", gap: 0.5, px: 1, py: 0.3, borderRadius: 1,
              cursor: "pointer", bgcolor: s.sid === sid ? "#0b1020" : "transparent",
              border: `1px solid ${s.sid === sid ? "#334155" : "transparent"}` }}>
            <TerminalIcon sx={{ fontSize: 13, color: s.alive ? "#22d3ee" : "#64748b" }} />
            <Typography variant="caption" sx={{ ...mono, color: s.sid === sid ? "#e2e8f0" : "#94a3b8", fontSize: 11 }} noWrap>
              {s.label}{s.taskId ? ` · TQ-${String(s.taskId).padStart(4, "0")}` : ""}
            </Typography>
            <CloseIcon onClick={(e) => { e.stopPropagation(); kill(s.sid); }}
              sx={{ fontSize: 12, color: "#64748b", "&:hover": { color: "#fca5a5" } }} />
          </Box>
        ))}
        <Button size="small" startIcon={<AddIcon sx={{ fontSize: 14 }} />} onClick={() => start({ agent: null })}
          sx={{ fontSize: 11, color: "#94a3b8" }}>shell</Button>
        {agents.map((a) => (
          <Button key={a} size="small" startIcon={<AddIcon sx={{ fontSize: 14 }} />} onClick={() => start({ agent: a })}
            sx={{ fontSize: 11, color: "#a5b4fc" }}>{a}</Button>
        ))}
        <Box sx={{ flex: 1 }} />
        {err && <Typography variant="caption" sx={{ color: "#fca5a5" }}>{err}</Typography>}
        <Typography variant="caption" sx={{ ...mono, color: "#475569", fontSize: 10.5 }} noWrap>{cur?.cwd || ""}</Typography>
        <IconButton size="small" onClick={onClose} title="Hide the terminal (sessions keep running)">
          <CloseIcon sx={{ fontSize: 15, color: "#94a3b8" }} />
        </IconButton>
      </Box>
      <Box sx={{ flex: 1, minHeight: 0 }}>
        {!cur
          ? <Typography variant="caption" sx={{ color: "#64748b", display: "block", p: 2 }}>
              No session — start a shell, or one of your agents, above.
            </Typography>
          : <TerminalPane key={cur.sid} sid={cur.sid} height="100%" onExit={load} />}
      </Box>
    </Box>
  );
};

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
