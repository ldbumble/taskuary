// CLI installation lives in Connections; named workers are managed in Docs > Profiles.
import React, { useCallback, useEffect, useState } from "react";
import { Alert, Box, Button, Chip, CircularProgress, Dialog, DialogContent, DialogTitle, FormControlLabel, ListSubheader, MenuItem, Select, Switch, TextField, Typography } from "@mui/material";
import AddIcon from "@mui/icons-material/Add";
import api from "./api";
import { PANEL2, BORDER, DIM, FAINT, INK, card, mono } from "./theme.jsx";
import { Crumb, Empty, LandingCard, ConfirmDelete, TaskuaryMark } from "./ui.jsx";
import { useCliInstall, InstallLine, UpdateLine } from "./cliInstall.jsx";
import { useCliSetup, SetupButton, CliPane } from "./cliSetup.jsx";
import BoltIcon from "@mui/icons-material/Bolt";
import StarIcon from "@mui/icons-material/Star";

// One-click presets: pick your CLI, Save, Test - done. Taskuary pipes the prompt on
// STDIN; --yolo / --full-auto / --dangerously-skip-permissions style flags matter,
// because a headless run has nobody to click "approve".
// Fallback only. The real list is clis.KNOWN on the server, delivered by /api/cli/detect and
// merged in by `presets` below — this static copy is what shows before that request lands (and
// if it fails). Keeping it as the SOURCE is what hid Muse Code: it was registered server-side,
// installable, detected, and still absent from this tab because nobody edited this array too
// (the owner, 2026-09-10). Anything added to clis.KNOWN now appears here on its own.
const FALLBACK_PRESETS = [
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

// What a preset card says under its title, per CLI. The server carries the flags; the sentence
// explaining WHY you would choose this one is a product decision and stays here.
const PRESET_DESC = {
  claude: "Recommended - stream-json shows the run LIVE on the Board and gives resumable sessions.",
  codex: "OpenAI Codex CLI, non-interactive exec mode.",
  gemini: "Google Gemini CLI - --yolo auto-approves tool use.",
  cursor: "Cursor's cursor-agent in headless print mode.",
  copilot: "GitHub Copilot CLI - some versions want the prompt as an argument; run Test to verify.",
  muse: "Meta's Muse Code on Muse Spark - `exec` runs it headless. macOS/Linux/WSL2 only.",
  devin: "Cognition's Devin, running locally - `-p` is its headless turn; run Test to verify it takes the prompt.",
};
// The profile a preset creates is named for its JOB, and every install has shipped Claude
// Code's as `coder`. clis.KNOWN names rows after the CLI, so this keeps that one as it was.
const PRESET_NAME = { claude: "coder" };

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

const BLANK_AGENT = { name: "", cmd: "", args: "", resume: "", timeout: "", cwd: "", cwdMap: "", lightModel: "",
  purpose: "", kind: "general", rulesDoc: "", triageEnabled: true };
const PROFILE_KINDS = ["general", "coding", "research", "analysis", "coordination", "marketing", "markets"];
const lines = (v) => String(v || "").split(NEWLINE).map((x) => x.trim()).filter(Boolean);

export const CliConnectionsPage = ({ onBack }) => {
  const [clis, setClis] = useState(null);
  const [err, setErr] = useState("");
  const { install, update, busy, note } = useCliInstall();
  const { openSetup, opening, pane, note: setupNote } = useCliSetup();
  const load = useCallback(async () => {
    try {
      const { data } = await api.get("/api/cli/detect");
      // Saved workers share these tools. They are not additional CLI connections.
      setClis((data.data || []).filter((row) => !row.profile));
      setErr("");
    } catch (e) { setErr(e?.response?.data?.detail || "Could not load CLI connections"); }
  }, []);
  useEffect(() => { load(); }, [load]);
  return (
    <Box sx={{ maxWidth: 980, mx: "auto" }}>
      <Crumb section="Connections" title="AI CLI agents" onBack={onBack} />
      <Typography variant="body2" sx={{ color: DIM, mb: 1 }}>
        Install and sign in to the CLI tools your agents use. Several worker profiles can share one CLI.
      </Typography>
      <Button size="small" onClick={() => { window.location.hash = "profiles"; }} sx={{ mb: 2 }}>Manage profiles in Docs</Button>
      {err && <Alert severity="error" action={<Button onClick={load}>Retry</Button>} sx={{ mb: 2 }}>{err}</Alert>}
      {!clis && !err && <CircularProgress size={22} />}
      <Box sx={{ display: "grid", gridTemplateColumns: { xs: "minmax(0, 1fr)", md: "repeat(3, minmax(0, 1fr))" }, gap: 2.5 }}>
        {(clis || []).map((cli) => (
          <Box key={cli.name} sx={{ ...card, p: 2 }}>
            <Box sx={{ display: "flex", gap: 1, alignItems: "center", mb: 0.75 }}>
              <TaskuaryMark size={19} />
              <Typography sx={{ color: INK, fontSize: 14, fontWeight: 700 }}>{cli.label}</Typography>
            </Box>
            <Typography variant="body2" sx={{ color: DIM, mb: 1 }}>{PRESET_DESC[cli.name] || `${cli.label} in headless mode.`}</Typography>
            {cli.installed ? (
              <Box sx={{ display: "flex", alignItems: "center", gap: 1, flexWrap: "wrap" }}>
                <Typography variant="caption" sx={{ color: DIM }}>Installed</Typography>
                <SetupButton cli={cli} opening={opening} onOpen={openSetup} />
                {/* installed is not the same as able to run: a CLI too old for the model its own
                    config pins fails every single run (the owner, 2026-09-11) */}
                <UpdateLine cli={cli} busy={busy} onUpdate={async () => { if (await update(cli)) await load(); }} />
              </Box>
            ) : <InstallLine cli={cli} busy={busy} onInstall={async () => { if (await install(cli)) await load(); }} />}
          </Box>
        ))}
      </Box>
      {[note, setupNote].filter(Boolean).map((message, i) => <Alert key={i} severity={message.bad ? "error" : "success"} sx={{ mt: 2 }}>{message.text}</Alert>)}
      {pane && <Box sx={{ mt: 2 }}><CliPane pane={pane} /></Box>}
    </Box>
  );
};

export const AgentsPage = ({ onBack, section = "Docs", title = "Manage profiles", initialCreate = false, onCreated }) => {
  const [agents, setAgents] = useState(null);
  const [catalog, setCatalog] = useState({});     // per agent: the CLI's own model list (codex reads it off disk)
  const [draft, setDraft] = useState(initialCreate ? { ...BLANK_AGENT } : null);
  const [err, setErr] = useState("");
  const [here, setHere] = useState({});           // agent -> its CLI resolves on this machine
  const [effective, setEffective] = useState(""); // ...and the one work is really dispatched to

  const load = useCallback(async () => {
    try {
      const { data } = await api.get("/api/agents");
      const rows = Object.fromEntries((data.data || []).map((r) => [r.Name, r]));
      setAgents(Object.fromEntries(Object.entries(data.config || {}).map(([name, prof]) => [name, {
        ...prof, purpose: prof.purpose || rows[name]?.purpose || "",
        kind: prof.kind || rows[name]?.Kind || "coding",
        rules_doc: rows[name]?.rules_doc || prof.rules_doc || "",
      }]))); setCatalog(data.models || {});
      // which of them this machine can actually start, and which one work really goes to
      setHere(Object.fromEntries((data.data || []).map((r) => [r.Name, r.installed !== false])));
      setEffective(data.default || "");
    }
    catch (e) { setErr(e?.response?.data?.detail || "Failed to load agents"); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const edit = (name) => {
    const a = agents[name] || {};
    setDraft({ name, purpose: a.purpose || "", kind: a.kind || "coding", rulesDoc: a.rules_doc || "", triageEnabled: a.triage_enabled !== false,
      cmd: a.cmd || "", args: (a.args || []).join(NEWLINE), resume: (a.resume_args || []).join(" "),
      timeout: a.timeout || "", cwd: a.cwd || "", lightModel: a.light_model || "",
      cwdMap: Object.entries(a.cwd_map || {}).map(([k, v]) => `${k} = ${v}`).join(NEWLINE) });
  };
  const save = async () => {
    const p = { ...agents[draft.name], cmd: draft.cmd.trim(), args: lines(draft.args),
      purpose: draft.purpose.trim(), kind: draft.kind, rules_doc: draft.rulesDoc || draft.name.trim(), triage_enabled: draft.triageEnabled };
    if (draft.resume.trim()) p.resume_args = draft.resume.trim().split(/\s+/);
    if (draft.timeout) p.timeout = Number(draft.timeout);
    if (draft.cwd.trim()) p.cwd = draft.cwd.trim();
    const map = {};
    for (const l of lines(draft.cwdMap)) { const i = l.indexOf("="); if (i > 0) map[l.slice(0, i).trim()] = l.slice(i + 1).trim(); }
    if (Object.keys(map).length) p.cwd_map = map;
    if (draft.lightModel.trim()) p.light_model = draft.lightModel.trim();
    try {
      const name = draft.name.trim(), isNew = !agents[name];
      const { data } = await api.put(`/api/agents/${encodeURIComponent(name)}`, p);
      setDraft(null); await load();
      if (isNew) onCreated?.(name, data.rules_doc || p.rules_doc);
    }
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
  const runTest = async (name) => {
    setTests((t) => ({ ...t, [name]: { busy: true } }));
    try {
      const { data } = await api.post(`/api/agents/${encodeURIComponent(name)}/test`);
      setTests((t) => ({ ...t, [name]: data }));
    } catch (e) { setTests((t) => ({ ...t, [name]: { ok: false, error: e?.response?.data?.detail || "test failed" } })); }
  };
  // what the server can install, keyed by the COMMAND a row runs - which is how both a preset
  // and a saved profile name their CLI. First row wins: the known-CLI rows come first and carry
  // the vendor's label, where a profile row would carry its own nickname.
  const [canGet, setCanGet] = useState({});
  const [presets, setPresets] = useState(FALLBACK_PRESETS);   // replaced by clis.KNOWN once detect answers
  useEffect(() => {
    api.get("/api/cli/detect").then(({ data }) => {
      const by = {};
      for (const r of data.data || []) if (!(r.cmd in by)) by[r.cmd] = r;
      setCanGet(by);
      // a KNOWN row carries its own flags and label; a row that is only somebody's saved
      // profile (it has `profile`) is not a preset and must not become a card
      const known = (data.data || []).filter((r) => !r.profile && r.args?.length);
      if (known.length) setPresets(known.map((r) => ({
        name: PRESET_NAME[r.name] || r.name, label: r.label, cmd: r.cmd, args: r.args,
        resume: (r.resume_args || [])[0] || "",
        timeout: r.timeout || 1500, desc: PRESET_DESC[r.name] || `${r.label} in headless mode.`,
      })));
    }).catch(() => setCanGet({}));
  }, [agents]);
  const { install, busy: installing, note: installNote } = useCliInstall();
  const { openSetup, opening, pane, note: setupNote } = useCliSetup();
  // installing from an EXISTING profile: point that profile at the absolute path afterwards, so
  // the agent runner can start it without waiting for this process to be restarted
  const getFor = async (name, cmd) => {
    const row = canGet[cmd];
    if (!row) return;
    const done = await install(row);
    if (!done) return;
    if (name && done.path) await api.put(`/api/agents/${encodeURIComponent(name)}`, { cmd: done.path });
    load();
  };
  const usePreset = (pr) => {
    let name = pr.name, n = 2;
    while (agents[name]) name = `${pr.name}-${n++}`;
    setDraft({ ...BLANK_AGENT, name, kind: "coding", purpose: "Write, review and test code in the task's repository.", rulesDoc: "coder", cmd: pr.cmd, args: pr.args.join(NEWLINE),
      resume: pr.resume, timeout: pr.timeout, cwd: "", cwdMap: "" });
  };

  if (!agents) return <CircularProgress size={22} sx={{ m: 4 }} />;
  return (
    <Box sx={{ maxWidth: 980, mx: "auto" }}>
      <Crumb section={section} onBack={onBack} title={title} />
      {err && <Alert severity="error" onClose={() => setErr("")} sx={{ mb: 1.5 }}>{err}</Alert>}
      <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 1 }}>
        <Typography variant="body2" sx={{ color: DIM }}>
          Name your workers here — Atlas, Scout, Coder, or anything useful. The name stays on every task they own,
          whether triage started it or you did. Several named workers can use the same CLI with different profiles.
        </Typography>
        <Box sx={{ flex: 1 }} />
        <Button size="small" variant="contained" startIcon={<AddIcon sx={{ fontSize: 14 }} />}
          onClick={() => setDraft({ ...BLANK_AGENT })}>Add profile</Button>
      </Box>
      <Box sx={{ display: "grid", gridTemplateColumns: { xs: "minmax(0, 1fr)", md: "repeat(3, minmax(0, 1fr))" }, gap: 2.5, mb: 3 }}>
        {presets.map((pr) => (
          <LandingCard key={pr.name} title={pr.label} desc={pr.desc}
            icon={<TaskuaryMark size={19} />} onOpen={() => usePreset(pr)}
            foot={canGet[pr.cmd] && !canGet[pr.cmd].installed
              ? <InstallLine cli={canGet[pr.cmd]} busy={installing} onInstall={() => getFor("", pr.cmd)} sx={{ mt: 0.5 }} />
              : null} />
        ))}
        {installNote && <Alert severity={installNote.bad ? "error" : "success"} sx={{ gridColumn: "1 / -1", fontSize: 12.5 }}>{installNote.text}</Alert>}
        {setupNote && <Alert severity={setupNote.bad ? "error" : "success"} sx={{ gridColumn: "1 / -1", fontSize: 12.5 }}>{setupNote.text}</Alert>}
        {/* the sign-in, in the same session the Board is showing. Nothing here closes it - the
            task's own Done does, and only when the owner says so. */}
        {pane && <Box sx={{ gridColumn: "1 / -1" }}><CliPane pane={pane} /></Box>}
      </Box>
      {!Object.keys(agents).length && <Empty>No agents yet — click a preset above, Save, then Test.</Empty>}
      {Object.entries(agents).map(([name, a]) => {
        const test = tests[name];
        return (
          <React.Fragment key={name}>
            <Box sx={{ py: 1.5, px: 1, borderBottom: `1px solid ${BORDER}`, borderRadius: 1.5,
              bgcolor: defAgent === name ? "#f6f7ff" : "transparent",
              borderLeft: `3px solid ${defAgent === name ? "#55697a" : "transparent"}` }}>
              <Box sx={{ display: "flex", alignItems: "center", gap: 1.25, flexWrap: "wrap" }}>
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
                <Typography sx={{ ...mono, color: INK, fontSize: 12.5, flex: 1, minWidth: 180 }} noWrap>
                  {a.cmd} {(a.args || []).join(" ")}
                </Typography>
                {/* Taskuary ships coder = claude. On a machine without claude that default aimed every
                    dispatch at a CLI nobody had, and the failure read as the agent's, not the setup's. */}
                {here[name] === false && (
                  <Chip size="small" label="not installed on this machine"
                    title={`Nothing here can start ${a.cmd}. Install it, or point this profile at the CLI you do have.`}
                    sx={{ bgcolor: "#f3e0e2", color: "#8a3646", height: 20, fontSize: 10, fontWeight: 700 }} />
                )}
                {here[name] === false && canGet[a.cmd]?.installable && (
                  <Button size="small" variant="outlined" disabled={!!installing}
                    title={`Install ${canGet[a.cmd].label} here and point this profile at it`}
                    onClick={() => getFor(name, a.cmd)} sx={{ fontSize: 10.5, whiteSpace: "nowrap" }}>
                    {installing === canGet[a.cmd].install ? "installing\u2026" : "Install"}
                  </Button>
                )}
                {/* signed-out and signed-in look identical from here - the page has no signal for
                    it, and the CLI itself is the only thing that knows. Sign in is always a
                    legitimate thing to press, so offer it rather than guess. */}
                <SetupButton cli={{ ...canGet[a.cmd], installed: here[name] !== false }}
                  opening={opening} onOpen={openSetup} sx={{ fontSize: 10.5 }} />
                {defAgent === name && here[name] === false && effective && effective !== name && (
                  <Chip size="small" label={`work goes to ${effective}`}
                    title="Your default cannot run here, so tasks are dispatched to an agent that can."
                    sx={{ bgcolor: "#eae4d8", color: "#55697a", height: 20, fontSize: 10 }} />
                )}
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
            </Box>
            {test && !test.busy && (
              <Typography variant="body2" sx={{ ml: 1, mb: 1, fontWeight: 600, color: test.ok ? "#47654a" : "#6b2733" }}>
                {test.ok ? `✓ ${test.result || "responded"}${test.resumable ? " · resumable session detected" : ""}` : `✗ ${test.error}`}
              </Typography>
            )}
          </React.Fragment>
        );
      })}
      {draft && (
        <Dialog open fullWidth maxWidth="md" onClose={() => setDraft(null)} aria-labelledby="profile-editor-title">
          <DialogTitle id="profile-editor-title">{agents[draft.name] ? `Edit profile · ${draft.name}` : "New profile"}</DialogTitle>
          <DialogContent>
          {err && <Alert severity="error" onClose={() => setErr("")} sx={{ mb: 1.5 }}>{err}</Alert>}
        <Box sx={{ pt: 1, display: "flex", flexDirection: "column", gap: 1.25 }}>
          <Box sx={{ display: "flex", gap: 1 }}>
            <TextField autoFocus label="worker name" value={draft.name} disabled={!!agents[draft.name]} sx={{ width: 180 }}
              onChange={(e) => setDraft({ ...draft, name: e.target.value })} />
            <TextField fullWidth label='cmd — "claude", "codex", your own wrapper…' value={draft.cmd}
              onChange={(e) => setDraft({ ...draft, cmd: e.target.value })} />
          </Box>
          <TextField label="When triage should choose this profile" multiline minRows={2} value={draft.purpose}
            required={draft.triageEnabled} helperText="Describe the work it owns, for example: compare vendors using public sources and cite findings."
            onChange={(e) => setDraft({ ...draft, purpose: e.target.value })} />
          <Box sx={{ display: "flex", gap: 1, flexWrap: "wrap" }}>
            <TextField select label="Work type" value={draft.kind} sx={{ minWidth: 180 }}
              onChange={(e) => setDraft({ ...draft, kind: e.target.value, rulesDoc: e.target.value === "coding" ? "coder" : "" })}>
              {[...new Set([...PROFILE_KINDS, draft.kind])].map((kind) => <MenuItem key={kind} value={kind}>{kind}</MenuItem>)}
            </TextField>
            <TextField select label="Instructions document" value={draft.rulesDoc} sx={{ flex: 1, minWidth: 220 }}
              helperText="Coding workers can share CODER.md regardless of which CLI they run."
              onChange={(e) => setDraft({ ...draft, rulesDoc: e.target.value })}>
              <MenuItem value="">Own document with starter instructions</MenuItem>
              {[...new Set(["coder", ...Object.entries(agents).map(([name, a]) => a.rules_doc || name), draft.rulesDoc])].filter(Boolean)
                .map((name) => <MenuItem key={name} value={name}>{name.toUpperCase()}.md</MenuItem>)}
            </TextField>
          </Box>
          <FormControlLabel control={<Switch checked={draft.triageEnabled} onChange={(e) => setDraft({ ...draft, triageEnabled: e.target.checked })} />}
            label="Available to triage for new tasks" />
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
            {(() => {
              // codex: the models its own /model picker lists, each with its reasoning levels, read off
              // ~/.codex/models_cache.json - the hand-typed list said gpt-5 while codex said GPT-5.6-Sol
              const cat = catalog[draft.name] || Object.values(catalog).find((c) => c.cli === cliBase(draft.cmd)) || {};
              const rich = (cat.models || []).filter((m) => m.efforts?.length);
              const flat = rich.length ? [] : (cat.choices?.length ? cat.choices : (MODEL_PICKS[cliBase(draft.cmd)] || []));
              const known = new Set([...rich.flatMap((m) => [m.id, ...m.efforts.map((e) => `${m.id}@${e}`)]), ...flat]);
              return (
                <>
                  <Select size="small" displayEmpty value={draft.lightModel} sx={{ minWidth: 320, bgcolor: "#fff" }}
                    MenuProps={{ PaperProps: { sx: { maxHeight: 420 } } }}
                    onChange={(e) => setDraft({ ...draft, lightModel: e.target.value })}>
                    <MenuItem value="" sx={{ fontSize: 12.5 }}>same model as coding (no downshift)</MenuItem>
                    {rich.map((m) => [
                      <ListSubheader key={`${m.id}-h`} sx={{ fontSize: 11, lineHeight: "28px", color: "#55697a", bgcolor: "#f6f4f1" }}>
                        {m.label}{m.desc ? ` — ${m.desc}` : ""}
                      </ListSubheader>,
                      ...m.efforts.map((eff) => (
                        <MenuItem key={`${m.id}@${eff}`} value={`${m.id}@${eff}`} sx={{ fontSize: 12.5, pl: 3 }}>
                          {m.id} · {eff}{eff === m.default_effort ? " (default)" : ""}
                        </MenuItem>
                      )),
                    ])}
                    {flat.map((mo) => <MenuItem key={mo} value={mo} sx={{ fontSize: 12.5 }}>{pickLabel(mo)}</MenuItem>)}
                    {draft.lightModel && !known.has(draft.lightModel) && (
                      <MenuItem value={draft.lightModel} sx={{ fontSize: 12.5 }}>{pickLabel(draft.lightModel)}</MenuItem>
                    )}
                  </Select>
                  {cat.current?.model && (
                    <Typography variant="caption" sx={{ color: FAINT, display: "block", mt: 0.5 }}>
                      Codex itself is set to {cat.current.model}{cat.current.effort ? ` · ${cat.current.effort}` : ""} (its config.toml) — list read from {cat.source}.
                    </Typography>
                  )}
                </>
              );
            })()}
          </Box>
          <TextField label="repo → dir map (one 'org/repo = C:/src/checkout' per line)" multiline minRows={2}
            value={draft.cwdMap} onChange={(e) => setDraft({ ...draft, cwdMap: e.target.value })} />
          <Box sx={{ display: "flex", gap: 0.75 }}>
            <Button size="small" variant="contained" disabled={!draft.name.trim() || !draft.cmd.trim() || (draft.triageEnabled && !draft.purpose.trim())} onClick={save}>Save</Button>
            <Button size="small" onClick={() => setDraft(null)}>Cancel</Button>
          </Box>
        </Box>
          </DialogContent>
        </Dialog>
      )}
      <ConfirmDelete open={!!confirmDel} what={`the agent "${confirmDel}"`}
        consequence="Any task set to use it falls back to the default agent. Sessions it has already run are kept."
        onClose={() => setConfirmDel(null)} onConfirm={() => del(confirmDel)} />
    </Box>
  );
};
