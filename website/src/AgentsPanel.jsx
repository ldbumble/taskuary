// Bring-your-own-AI-CLI editor - shared by Settings (Agents page) and Connectors
// (AI CLI agents card). Any CLI that reads a prompt on stdin is a teammate.
import React, { useCallback, useEffect, useState } from "react";
import { Alert, Box, Button, Chip, CircularProgress, MenuItem, Select, TextField, Typography } from "@mui/material";
import AddIcon from "@mui/icons-material/Add";
import api from "./api";
import { PANEL2, BORDER, DIM, FAINT, INK, card, mono } from "./theme.jsx";
import { Crumb, Empty, LandingCard, ConfirmDelete } from "./ui.jsx";
import SmartToyIcon from "@mui/icons-material/SmartToy";
import BoltIcon from "@mui/icons-material/Bolt";
import StarIcon from "@mui/icons-material/Star";

// One-click presets: pick your CLI, Save, Test - done. Taskuary pipes the prompt on
// STDIN; --yolo / --full-auto / --dangerously-skip-permissions style flags matter,
// because a headless run has nobody to click "approve".
const PRESETS = [
  { name: "coder", label: "Claude Code", cmd: "claude",
    args: ["-p", "--dangerously-skip-permissions", "--output-format", "stream-json", "--verbose"], resume: "--resume", timeout: 1500,
    desc: "Recommended - stream-json shows the run LIVE on the Board and gives resumable sessions." },
  { name: "codex", label: "Codex CLI", cmd: "codex", args: ["exec", "--full-auto"], resume: "", timeout: 1500,
    desc: "OpenAI Codex CLI, non-interactive full-auto mode." },
  { name: "gemini", label: "Gemini CLI", cmd: "gemini", args: ["--yolo"], resume: "", timeout: 1500,
    desc: "Google Gemini CLI - --yolo auto-approves tool use." },
  { name: "cursor", label: "Cursor CLI", cmd: "cursor-agent", args: ["-p", "--force", "--output-format", "text"], resume: "", timeout: 1500,
    desc: "Cursor's cursor-agent in headless print mode." },
  { name: "copilot", label: "Copilot CLI", cmd: "copilot", args: ["-p", "--allow-all-tools"], resume: "", timeout: 1500,
    desc: "GitHub Copilot CLI - some versions want the prompt as an argument; run Test to verify." },
];

const NEWLINE = String.fromCharCode(10);
const ARGS_PH = ['-p', '--dangerously-skip-permissions', '--output-format', 'stream-json', '--verbose'].join(NEWLINE);
// the model quick-picks per CLI (mirrors the server's CLI_MODELS) - the light-model field is
// a DROPDOWN of what the CLI actually takes, not a text box to guess spellings into
// codex on a ChatGPT plan has no smaller model - its cheap gear is REASONING EFFORT on the
// same model, spelled effort:<level> and translated to -c model_reasoning_effort=<level>
const MODEL_PICKS = {
  claude: ["haiku", "sonnet", "opus", "claude-haiku-4-5", "claude-sonnet-5", "claude-opus-5"],
  codex: ["effort:low", "effort:minimal", "effort:medium", "gpt-5", "gpt-5-codex"],
  gemini: ["gemini-2.5-flash", "gemini-2.5-pro"],
};
const pickLabel = (v) => v.startsWith("effort:")
  ? `same model, ${v.slice(7)} reasoning effort` : v;
// "C:\...\OpenAI\Codex\bin\codex.exe" is codex: the picks key on the CLI, not on how the path was typed
const cliBase = (cmd) => String(cmd || "").trim().replace(/^.*[\\/]/, "").replace(/\.(cmd|exe|bat|ps1)$/i, "").toLowerCase();

const BLANK_AGENT = { name: "", cmd: "", args: "", resume: "", timeout: "", cwd: "", cwdMap: "", lightModel: "" };
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
      timeout: a.timeout || "", cwd: a.cwd || "", lightModel: a.light_model || "",
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
    if (draft.lightModel.trim()) p.light_model = draft.lightModel.trim();
    try { await api.put(`/api/agents/${encodeURIComponent(draft.name.trim())}`, p); setDraft(null); load(); }
    catch (e) { setErr(e?.response?.data?.detail || "save failed"); }
  };
  const [confirmDel, setConfirmDel] = useState(null);
  const del = async (name) => { await api.delete(`/api/agents/${encodeURIComponent(name)}`); await load(); };
  const [tests, setTests] = useState({});
  // which agent works tasks when nothing names one - the row wears it, and one click moves it
  const [defAgent, setDefAgent] = useState("");
  useEffect(() => {
    api.get("/api/settings").then(({ data }) => {
      setDefAgent((data.data || []).find((x) => x.Name === "default_agent")?.Value || "coder");
    }).catch(() => {});
  }, []);
  const makeDefault = async (name) => {
    await api.patch("/api/settings", { name: "default_agent", value: name });
    setDefAgent(name);
  };
  // WHICH brain triages is one exclusive choice across everything that could do it - the AI
  // connectors holding keys and these CLI agents. Selecting one deselects the other, because
  // it is one setting; /api/brains already lists every candidate with whether it is ready.
  const [brains, setBrains] = useState([]);
  const [triage, setTriage] = useState("");
  useEffect(() => {
    api.get("/api/brains").then(({ data }) => setBrains(data.data || [])).catch(() => {});
    api.get("/api/settings").then(({ data }) => {
      setTriage((data.data || []).find((x) => x.Name === "triage_ai")?.Value || "");
    }).catch(() => {});
  }, []);
  const pickTriage = async (value) => {
    await api.patch("/api/settings", { name: "triage_ai", value });
    setTriage(value);
  };

  const runTest = async (name) => {
    setTests((t) => ({ ...t, [name]: { busy: true } }));
    try {
      const { data } = await api.post(`/api/agents/${encodeURIComponent(name)}/test`);
      setTests((t) => ({ ...t, [name]: data }));
    } catch (e) { setTests((t) => ({ ...t, [name]: { ok: false, error: e?.response?.data?.detail || "test failed" } })); }
  };
  const usePreset = (pr) => setDraft({ name: pr.name, cmd: pr.cmd, args: pr.args.join(NEWLINE),
    resume: pr.resume, timeout: pr.timeout, cwd: "", cwdMap: "" });

  if (!agents) return <CircularProgress size={22} sx={{ m: 4 }} />;
  return (
    <Box sx={{ maxWidth: 980, mx: "auto" }}>
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
      <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", md: "repeat(3, 1fr)" }, gap: 2.5, mb: 3 }}>
        {PRESETS.map((pr) => (
          <LandingCard key={pr.name} title={pr.label} desc={pr.desc}
            icon={<SmartToyIcon sx={{ fontSize: 19, color: "#55697a" }} />} onOpen={() => usePreset(pr)} />
        ))}
      </Box>
      {brains.length > 0 && (
        <Box sx={{ mb: 2, p: 1.5, bgcolor: PANEL2, border: `1px solid ${BORDER}`, borderRadius: 2 }}>
          <Typography sx={{ color: INK, fontWeight: 700, fontSize: 13 }}>Who does the triage?</Typography>
          <Typography variant="caption" sx={{ color: FAINT, display: "block", mb: 1 }}>
            One brain reads and classifies every inbound message — an AI connector (cheap, instant)
            or one of the CLI agents below (no API key; give it a light model so triage does not run
            the coding tier). Picking one unpicks the other: it is a single choice.
          </Typography>
          <Box sx={{ display: "flex", gap: 0.75, flexWrap: "wrap" }}>
            {brains.map((b) => {
              const on = triage === b.value;
              return (
                <Chip key={b.value || "auto"} size="small" label={b.label} clickable={b.ready}
                  onClick={() => b.ready && pickTriage(b.value)}
                  title={b.ready ? "" : "not ready — save a key / finish setup on its connector first"}
                  sx={{ height: 24, fontSize: 11, fontWeight: on ? 700 : 400, opacity: b.ready ? 1 : 0.45,
                    bgcolor: on ? "#55697a" : "#fff", color: on ? "#fff" : DIM,
                    border: `1px solid ${on ? "#55697a" : BORDER}` }} />
              );
            })}
          </Box>
        </Box>
      )}
      {!Object.keys(agents).length && <Empty>No agents yet — click a preset above, Save, then Test.</Empty>}
      {Object.entries(agents).map(([name, a]) => (
        <Box key={name} sx={{ display: "flex", alignItems: "center", gap: 1.5, py: 1.75, px: 1,
          borderBottom: `1px solid ${BORDER}`, borderRadius: 1.5,
          bgcolor: defAgent === name ? "#f6f7ff" : "transparent",
          borderLeft: `3px solid ${defAgent === name ? "#55697a" : "transparent"}` }}>
          <Chip size="small" label={name} sx={{ bgcolor: "#eae4d8", color: "#55697a", height: 21, fontSize: 10.5, fontWeight: 700 }} />
          {defAgent === name ? (
            <Chip size="small" icon={<StarIcon sx={{ fontSize: 12 }} />} label="default"
              title="Works every task nothing names an agent for — Start session, Send to coding agent, auto-dispatch"
              sx={{ bgcolor: "#55697a", color: "#fff", height: 20, fontSize: 10, fontWeight: 700,
                "& .MuiChip-icon": { color: "#fff" } }} />
          ) : (
            <Button size="small" sx={{ fontSize: 10, minWidth: 0, px: 0.75, color: FAINT }}
              title="Make this the agent every task uses unless another is picked"
              onClick={() => makeDefault(name)}>make default</Button>
          )}
          <Typography sx={{ ...mono, color: INK, fontSize: 12.5, flex: 1, minWidth: 0 }} noWrap>
            {a.cmd} {(a.args || []).join(" ")}
          </Typography>
          {a.cmd === "claude" && !(a.args || []).includes("--dangerously-skip-permissions") && (
            <Chip size="small" label="will hang headless — add --dangerously-skip-permissions"
              sx={{ bgcolor: "#eae4d8", color: "#55697a", height: 20, fontSize: 10 }} />
          )}
          <Typography variant="caption" sx={{ ...mono, color: FAINT }}>
            timeout {a.timeout || 1200}s{a.resume_args ? " · resumable" : ""}{a.light_model ? ` · light: ${a.light_model}` : ""}
          </Typography>
          <Button size="small" startIcon={<BoltIcon sx={{ fontSize: 13 }} />} disabled={tests[name]?.busy}
            onClick={() => runTest(name)}>{tests[name]?.busy ? "Testing…" : "Test"}</Button>
          <Button size="small" onClick={() => edit(name)}>Edit</Button>
          <Button size="small" color="error" onClick={() => setConfirmDel(name)}>Delete</Button>
        </Box>
      )).flatMap((row, i) => {
        const name = Object.keys(agents)[i];
        const t = tests[name];
        return t && !t.busy ? [row,
          <Typography key={name + "t"} variant="body2" sx={{ ml: 1, mb: 1, fontWeight: 600, color: t.ok ? "#47654a" : "#6b2733" }}>
            {t.ok ? `✓ ${t.result || "responded"}${t.resumable ? " · resumable session detected" : ""}` : `✗ ${t.error}`}
          </Typography>] : [row];
      })}
      {draft && (
        <Box sx={{ ...card, bgcolor: PANEL2, p: 2, mt: 2, display: "flex", flexDirection: "column", gap: 1.25 }}>
          <Typography variant="body2" sx={{ color: "#55697a", fontWeight: 700 }}>{agents[draft.name] ? `Edit agent · ${draft.name}` : "New agent"}</Typography>
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
          <Box>
            <Typography variant="caption" sx={{ color: DIM, display: "block", mb: 0.5 }}>
              light model — what triage, drafts and summaries run on when this CLI is the triage
              brain; coding sessions keep the main model
            </Typography>
            <Select size="small" displayEmpty value={draft.lightModel} sx={{ minWidth: 260, bgcolor: "#fff" }}
              onChange={(e) => setDraft({ ...draft, lightModel: e.target.value })}>
              <MenuItem value="" sx={{ fontSize: 12.5 }}>same model as coding (no downshift)</MenuItem>
              {(MODEL_PICKS[cliBase(draft.cmd)] || []).map((mo) => (
                <MenuItem key={mo} value={mo} sx={{ fontSize: 12.5 }}>{pickLabel(mo)}</MenuItem>
              ))}
              {draft.lightModel && !(MODEL_PICKS[cliBase(draft.cmd)] || []).includes(draft.lightModel) && (
                <MenuItem value={draft.lightModel} sx={{ fontSize: 12.5 }}>{draft.lightModel}</MenuItem>
              )}
            </Select>
          </Box>
          <TextField label="repo → dir map (one 'org/repo = C:/src/checkout' per line)" multiline minRows={2}
            value={draft.cwdMap} onChange={(e) => setDraft({ ...draft, cwdMap: e.target.value })} />
          <Box sx={{ display: "flex", gap: 0.75 }}>
            <Button size="small" variant="contained" disabled={!draft.name.trim() || !draft.cmd.trim()} onClick={save}>Save</Button>
            <Button size="small" onClick={() => setDraft(null)}>Cancel</Button>
          </Box>
        </Box>
      )}
      <ConfirmDelete open={!!confirmDel} what={`the agent "${confirmDel}"`}
        consequence="Any task set to use it falls back to the default agent. Sessions it has already run are kept."
        onClose={() => setConfirmDel(null)} onConfirm={() => del(confirmDel)} />
    </Box>
  );
};

