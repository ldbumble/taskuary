// Bring-your-own-AI-CLI editor - shared by Settings (Agents page) and Connectors
// (AI CLI agents card). Any CLI that reads a prompt on stdin is a teammate.
import React, { useCallback, useEffect, useState } from "react";
import { Alert, Box, Button, Chip, CircularProgress, TextField, Typography } from "@mui/material";
import AddIcon from "@mui/icons-material/Add";
import api from "./api";
import { PANEL2, BORDER, DIM, FAINT, INK, card, mono } from "./theme.jsx";
import { Crumb, Empty } from "./ui.jsx";

const NEWLINE = String.fromCharCode(10);
const ARGS_PH = ['-p', '--dangerously-skip-permissions', '--output-format', 'json'].join(NEWLINE);
const BLANK_AGENT = { name: "", cmd: "", args: "", resume: "", timeout: "", cwd: "", cwdMap: "" };
const lines = (v) => String(v || "").split(NEWLINE).map((x) => x.trim()).filter(Boolean);

export const AgentsPage = ({ onBack, section = "Settings", title = "Agents" }) => {
  const [agents, setAgents] = useState(null);
  const [draft, setDraft] = useState(null);
  const [err, setErr] = useState("");

  const load = useCallback(async () => {
    try { setAgents((await api.get("/api/agents")).data.config || {}); }
    catch (e) { setErr(e?.response?.data?.detail || "Failed to load agents"); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const edit = (name) => {
    const a = agents[name] || {};
    setDraft({ name, cmd: a.cmd || "", args: (a.args || []).join(NEWLINE), resume: (a.resume_args || []).join(" "),
      timeout: a.timeout || "", cwd: a.cwd || "",
      cwdMap: Object.entries(a.cwd_map || {}).map(([k, v]) => `${k} = ${v}`).join(NEWLINE) });
  };
  const save = async () => {
    const p = { cmd: draft.cmd.trim(), args: lines(draft.args) };
    if (draft.resume.trim()) p.resume_args = draft.resume.trim().split(/\s+/);
    if (draft.timeout) p.timeout = Number(draft.timeout);
    if (draft.cwd.trim()) p.cwd = draft.cwd.trim();
    const map = {};
    for (const l of lines(draft.cwdMap)) { const i = l.indexOf("="); if (i > 0) map[l.slice(0, i).trim()] = l.slice(i + 1).trim(); }
    if (Object.keys(map).length) p.cwd_map = map;
    try { await api.put(`/api/agents/${encodeURIComponent(draft.name.trim())}`, p); setDraft(null); load(); }
    catch (e) { setErr(e?.response?.data?.detail || "save failed"); }
  };
  const del = async (name) => { await api.delete(`/api/agents/${encodeURIComponent(name)}`); load(); };

  if (!agents) return <CircularProgress size={22} sx={{ m: 4 }} />;
  return (
    <Box sx={{ maxWidth: 980 }}>
      <Crumb section={section} onBack={onBack} title={title} />
      {err && <Alert severity="error" onClose={() => setErr("")} sx={{ mb: 1.5 }}>{err}</Alert>}
      <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 1 }}>
        <Typography variant="body2" sx={{ color: DIM }}>
          Any CLI that reads a prompt on stdin is a teammate — Claude Code's JSON output enables resumable sessions.
        </Typography>
        <Box sx={{ flex: 1 }} />
        <Button size="small" variant="contained" startIcon={<AddIcon sx={{ fontSize: 14 }} />}
          onClick={() => setDraft({ ...BLANK_AGENT })}>Add agent</Button>
      </Box>
      {!Object.keys(agents).length && <Empty>No agents yet — add your CLI below.</Empty>}
      {Object.entries(agents).map(([name, a]) => (
        <Box key={name} sx={{ display: "flex", alignItems: "center", gap: 1.5, py: 1.75, borderBottom: `1px solid ${BORDER}` }}>
          <Chip size="small" label={name} sx={{ bgcolor: "#eef0ff", color: "#4f46e5", height: 21, fontSize: 10.5, fontWeight: 700 }} />
          <Typography sx={{ ...mono, color: INK, fontSize: 12.5, flex: 1, minWidth: 0 }} noWrap>
            {a.cmd} {(a.args || []).join(" ")}
          </Typography>
          <Typography variant="caption" sx={{ ...mono, color: FAINT }}>
            timeout {a.timeout || 1200}s{a.resume_args ? " · resumable" : ""}
          </Typography>
          <Button size="small" onClick={() => edit(name)}>Edit</Button>
          <Button size="small" color="error" onClick={() => del(name)}>Delete</Button>
        </Box>
      ))}
      {draft && (
        <Box sx={{ ...card, bgcolor: PANEL2, p: 2, mt: 2, display: "flex", flexDirection: "column", gap: 1.25 }}>
          <Typography variant="body2" sx={{ color: "#4f46e5", fontWeight: 700 }}>{agents[draft.name] ? `Edit agent · ${draft.name}` : "New agent"}</Typography>
          <Box sx={{ display: "flex", gap: 1 }}>
            <TextField label="name" value={draft.name} disabled={!!agents[draft.name]} sx={{ width: 180 }}
              onChange={(e) => setDraft({ ...draft, name: e.target.value })} />
            <TextField fullWidth label='cmd — "claude", "codex", your own wrapper…' value={draft.cmd}
              onChange={(e) => setDraft({ ...draft, cmd: e.target.value })} />
          </Box>
          <TextField label="args (one per line)" multiline minRows={2} value={draft.args}
            placeholder={ARGS_PH}
            onChange={(e) => setDraft({ ...draft, args: e.target.value })} />
          <Box sx={{ display: "flex", gap: 1 }}>
            <TextField fullWidth label="resume args — enables message-the-agent continuity" value={draft.resume}
              placeholder="--resume" onChange={(e) => setDraft({ ...draft, resume: e.target.value })} />
            <TextField label="timeout (s)" type="number" sx={{ width: 130 }} value={draft.timeout}
              onChange={(e) => setDraft({ ...draft, timeout: e.target.value })} />
          </Box>
          <TextField label="working dir (optional)" value={draft.cwd} onChange={(e) => setDraft({ ...draft, cwd: e.target.value })} />
          <TextField label="repo → dir map (one 'org/repo = C:/src/checkout' per line)" multiline minRows={2}
            value={draft.cwdMap} onChange={(e) => setDraft({ ...draft, cwdMap: e.target.value })} />
          <Box sx={{ display: "flex", gap: 0.75 }}>
            <Button size="small" variant="contained" disabled={!draft.name.trim() || !draft.cmd.trim()} onClick={save}>Save</Button>
            <Button size="small" onClick={() => setDraft(null)}>Cancel</Button>
          </Box>
        </Box>
      )}
    </Box>
  );
};

