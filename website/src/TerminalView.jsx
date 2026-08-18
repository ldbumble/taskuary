// Real terminals in the app: xterm.js over a websocket over a pty. Open your coding CLI
// (or a plain shell) in a repo, watch it work, type back at it - the same session the
// agent is in, not a transcript of one.
import React, { useCallback, useEffect, useRef, useState } from "react";
import { Alert, Box, Button, Checkbox, FormControlLabel, MenuItem, Select, TextField, Typography } from "@mui/material";
import { Terminal } from "@xterm/xterm";
import { FitAddon } from "@xterm/addon-fit";
import "@xterm/xterm/css/xterm.css";
import AddIcon from "@mui/icons-material/Add";
import CloseIcon from "@mui/icons-material/Close";
import TerminalIcon from "@mui/icons-material/Terminal";
import api from "./api";
import { BORDER, DIM, FAINT, INK, PANEL, card, mono } from "./theme.jsx";
import { Empty } from "./ui.jsx";

// xterm on the app's dark console palette (same ink as the Board's live tails).
const XTERM_THEME = { background: "#0f172a", foreground: "#cbd5e1", cursor: "#22d3ee",
  black: "#0f172a", red: "#fca5a5", green: "#86efac", yellow: "#fcd34d", blue: "#a5b4fc",
  magenta: "#d8b4fe", cyan: "#67e8f9", white: "#e2e8f0", brightBlack: "#475569" };

const wsUrl = (sid) => {
  const t = localStorage.getItem("taskuary_token");
  return `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/api/terminals/${sid}/ws${t ? `?token=${encodeURIComponent(t)}` : ""}`;
};

// One live session. Mounts xterm once, streams both ways, resizes the pty to the pane.
export const TerminalPane = ({ sid, height = "70vh", onExit }) => {
  const host = useRef(null);
  const [state, setState] = useState("connecting");
  useEffect(() => {
    const term = new Terminal({ fontSize: 12.5, fontFamily: "Consolas, 'Cascadia Mono', monospace",
      theme: XTERM_THEME, cursorBlink: true, scrollback: 5000, convertEol: false });
    const fit = new FitAddon();
    term.loadAddon(fit);
    term.open(host.current);
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
