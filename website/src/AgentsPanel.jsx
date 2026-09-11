// Connections own commands; profiles reference a connection and choose a model.
import React, { useCallback, useEffect, useRef, useState } from "react";
import { Alert, Autocomplete, Box, Button, Chip, CircularProgress, Dialog, DialogContent, DialogTitle, FormControlLabel, MenuItem, Switch, TextField, Typography } from "@mui/material";
import AddIcon from "@mui/icons-material/Add";
import api from "./api";
import { BORDER, DIM, card, mono } from "./theme.jsx";
import { Crumb, Empty, ConfirmDelete, TaskuaryMark } from "./ui.jsx";
import { useCliInstall, InstallLine, UpdateLine } from "./cliInstall.jsx";
import { useCliSetup, SetupButton, CliPane } from "./cliSetup.jsx";

const lines = (v) => String(v || "").split("\n").map((x) => x.trim()).filter(Boolean);
const failure = (e) => e?.response?.data?.detail || e?.message || "Could not save changes";
const BLANK_CONNECTION = { name: "", cmd: "", args: "", resumeArgs: "", timeout: 1500, modelArg: "" };
const BLANK_PROFILE = { name: "", purpose: "", kind: "general", rulesDoc: "", triageEnabled: true, provider: "", model: "" };
const PROFILE_KINDS = ["general", "coding", "research", "analysis", "coordination", "marketing", "markets"];

export const CliConnectionsPage = ({ onBack }) => {
  const [clis, setClis] = useState(null), [draft, setDraft] = useState(null);
  const [err, setErr] = useState(""), [saving, setSaving] = useState(false);
  const [tests, setTests] = useState({}), [confirmDel, setConfirmDel] = useState(null);
  const { install, update, busy, note, pane: installPane, setPane: setInstallPane } = useCliInstall({ terminal: true });
  const installerRef = useRef(null);
  useEffect(() => { if (installPane) installerRef.current?.scrollIntoView({ behavior: "smooth", block: "center" }); }, [installPane]);
  const { openSetup, opening, pane, note: setupNote } = useCliSetup();
  const load = useCallback(async () => {
    try { const { data } = await api.get("/api/cli/connections"); setClis(data.data || []); setErr(""); }
    catch (e) { setErr(e?.response?.status === 404 ? "Restart Taskuary to load the updated CLI connections configuration." : failure(e)); }
  }, []);
  useEffect(() => { load(); }, [load]);
  const edit = (cli) => {
    const c = cli.config;
    setDraft({ name: cli.name, existing: true, cmd: c.cmd || "", args: (c.args || []).join("\n"),
      resumeArgs: (c.resume_args || (c.resume ? [c.resume] : [])).join("\n"), timeout: c.timeout || 1500, modelArg: c.model_arg || "" });
  };
  const save = async () => {
    setSaving(true); setErr("");
    try {
      await api.put(`/api/cli/connections/${encodeURIComponent(draft.name.trim())}`, {
        cmd: draft.cmd.trim(), args: lines(draft.args), resume_args: lines(draft.resumeArgs),
        timeout: Number(draft.timeout), ...(draft.modelArg.trim() ? { model_arg: draft.modelArg.trim() } : {}),
      });
      setDraft(null); await load();
    } catch (e) { setErr(failure(e)); } finally { setSaving(false); }
  };
  const runTest = async (name) => {
    setTests((t) => ({ ...t, [name]: { busy: true } }));
    try { const { data } = await api.post(`/api/cli/connections/${encodeURIComponent(name)}/test`); setTests((t) => ({ ...t, [name]: data })); }
    catch (e) { setTests((t) => ({ ...t, [name]: { ok: false, error: failure(e) } })); }
  };
  return <Box sx={{ maxWidth: 980, mx: "auto" }}>
    <Crumb section="Connections" title="AI CLI agents" onBack={onBack} />
    <Box sx={{ display: "flex", gap: 2, alignItems: "center", mb: 1 }}>
      <Typography variant="body2" sx={{ color: DIM, flex: 1 }}>Configure each CLI once. Its command and arguments are shared by every profile that chooses it.</Typography>
      <Button variant="contained" startIcon={<AddIcon />} onClick={() => setDraft({ ...BLANK_CONNECTION })}>Add CLI connection</Button>
    </Box>
    <Button size="small" onClick={() => { window.location.hash = "profiles"; }} sx={{ mb: 2 }}>Manage profiles in Docs</Button>
    {err && !draft && <Alert severity="error" sx={{ mb: 2 }}>{err}</Alert>}
    {!clis && !err && <CircularProgress size={22} />}
    <Box sx={{ display: "grid", gridTemplateColumns: { xs: "minmax(0, 1fr)", md: "repeat(2, minmax(0, 1fr))" }, gap: 2 }}>
      {(clis || []).map((cli) => <Box key={cli.name} data-connection={cli.name} sx={{ ...card, p: 2 }}>
        <Box sx={{ display: "flex", gap: 1, alignItems: "center", mb: 1 }}>
          <TaskuaryMark size={19} /><Typography sx={{ fontWeight: 700, flex: 1 }}>{cli.label}</Typography>
          <Chip size="small" label={cli.installed ? "Installed" : cli.installable ? "Not installed" : "Cannot install here"} />
          {cli.configured && <Chip size="small" label="Configured" />}
        </Box>
        <Typography sx={{ ...mono, fontSize: 12, overflowWrap: "anywhere", mb: 1 }}>{cli.config.cmd} {(cli.config.args || []).join(" ")}</Typography>
        <Box sx={{ display: "flex", gap: 1, flexWrap: "wrap", alignItems: "center" }}>
          <Button size="small" onClick={() => edit(cli)}>{cli.configured ? "Edit command" : "Configure"}</Button>
          {cli.configured && <Button size="small" disabled={tests[cli.name]?.busy} onClick={() => runTest(cli.name)}>{tests[cli.name]?.busy ? "Testing..." : "Test"}</Button>}
          {cli.installed ? <>
            <SetupButton cli={cli} opening={opening} onOpen={openSetup} />
            <UpdateLine cli={cli} busy={busy} onUpdate={async () => { if (await update(cli)) await load(); }} />
          </> : <InstallLine cli={cli} busy={busy} onInstall={async () => { if (await install(cli)) await load(); }} />}
          {cli.configured && <Button size="small" color="error" onClick={() => setConfirmDel(cli.name)}>Remove</Button>}
        </Box>
        {tests[cli.name] && !tests[cli.name].busy && <Alert severity={tests[cli.name].ok ? "success" : "error"} sx={{ mt: 1 }}>{tests[cli.name].ok ? tests[cli.name].result || "Connection works" : tests[cli.name].error}</Alert>}
      </Box>)}
    </Box>
    {[note, setupNote].filter(Boolean).map((message, i) => <Alert key={i} severity={message.bad ? "error" : "success"} sx={{ mt: 2 }}>{message.text}</Alert>)}
    {installPane && <Box ref={installerRef} sx={{ mt: 2, ...card, p: 2 }}>
      <Box sx={{ display: "flex", alignItems: "center", mb: 1 }}>
        <Typography sx={{ flex: 1, fontWeight: 700 }}>{installPane.verb === "update" ? "Update" : "Install"} {installPane.name} — terminal</Typography>
        <Button size="small" onClick={async () => {
          try { await api.post(`/api/terminals/${encodeURIComponent(installPane.sid)}/wrap`, { task_id: installPane.taskId, close: true }); setInstallPane(null); await load(); }
          catch (e) { setErr(failure(e)); }
        }}>Close terminal</Button>
      </Box>
      <Typography variant="body2" sx={{ color: DIM, mb: 1 }}>Watch the commands and answer installer prompts here. Closing the terminal stops any command still running.</Typography>
      <CliPane pane={installPane} />
    </Box>}
    {pane && <Box sx={{ mt: 2 }}><CliPane pane={pane} /></Box>}
    {draft && <Dialog open fullWidth maxWidth="sm" onClose={() => !saving && setDraft(null)}>
      <DialogTitle>{draft.existing ? `CLI connection: ${draft.name}` : "Add CLI connection"}</DialogTitle>
      <DialogContent><Box sx={{ display: "flex", flexDirection: "column", gap: 2, pt: 1 }}>
        {err && <Alert severity="error">{err}</Alert>}
        <TextField autoFocus label="Connection name" disabled={draft.existing} value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} />
        <TextField label="Command" value={draft.cmd} onChange={(e) => setDraft({ ...draft, cmd: e.target.value })} />
        <TextField label="Arguments (one per line)" multiline minRows={3} value={draft.args} onChange={(e) => setDraft({ ...draft, args: e.target.value })} />
        <TextField label="Resume arguments (one per line)" multiline value={draft.resumeArgs} onChange={(e) => setDraft({ ...draft, resumeArgs: e.target.value })} />
        <TextField label="Timeout (seconds)" type="number" value={draft.timeout} onChange={(e) => setDraft({ ...draft, timeout: e.target.value })} />
        <TextField label="Model flag (optional)" helperText="Leave blank to use this CLI's standard model flag." value={draft.modelArg} onChange={(e) => setDraft({ ...draft, modelArg: e.target.value })} />
        <Typography variant="caption" sx={{ color: DIM }}>Changes apply to every profile using this connection on its next run.</Typography>
        <Box><Button variant="contained" disabled={saving || !draft.name.trim() || !draft.cmd.trim() || !(Number(draft.timeout) > 0)} onClick={save}>Save</Button><Button onClick={() => setDraft(null)}>Cancel</Button></Box>
      </Box></DialogContent>
    </Dialog>}
    <ConfirmDelete open={!!confirmDel} what={`the CLI connection "${confirmDel}"`} consequence="Choose another provider for any profiles using it first. The CLI stays installed."
      onClose={() => setConfirmDel(null)} onConfirm={async () => { try { await api.delete(`/api/cli/connections/${encodeURIComponent(confirmDel)}`); await load(); } catch (e) { setErr(failure(e)); } }} />
  </Box>;
};

export const AgentsPage = ({ onBack, section = "Docs", title = "Manage profiles", initialCreate = false, onCreated, onRules }) => {
  const [agents, setAgents] = useState(null), [connections, setConnections] = useState([]);
  const [draft, setDraft] = useState(initialCreate ? { ...BLANK_PROFILE } : null);
  const [err, setErr] = useState(""), [saving, setSaving] = useState(false), [confirmDel, setConfirmDel] = useState(null);
  const load = useCallback(async () => {
    try {
      const [a, c] = await Promise.all([api.get("/api/agents"), api.get("/api/cli/connections")]);
      const rows = Object.fromEntries((a.data.data || []).map((r) => [r.Name, r]));
      setAgents(Object.fromEntries(Object.entries(a.data.config || {}).map(([name, p]) => [name, {
        ...p, purpose: p.purpose || rows[name]?.purpose || "", kind: p.kind || rows[name]?.Kind || "coding", rules_doc: rows[name]?.rules_doc || p.rules_doc || "",
      }])));
      setConnections((c.data.data || []).filter((r) => r.configured)); setErr("");
    } catch (e) { setErr(failure(e)); }
  }, []);
  useEffect(() => { load(); }, [load]);
  const edit = (name) => {
    const a = agents[name];
    setDraft({ name, existing: true, purpose: a.purpose, kind: a.kind, rulesDoc: a.rules_doc,
      triageEnabled: a.triage_enabled !== false, provider: a.provider || "", model: a.model || "" });
  };
  const save = async () => {
    setSaving(true); setErr("");
    const name = draft.name.trim();
    const p = { purpose: draft.purpose.trim(), kind: draft.kind, rules_doc: draft.rulesDoc || (draft.kind === "coding" ? "coder" : name),
      triage_enabled: draft.triageEnabled, provider: draft.provider, model: draft.model.trim() };
    try {
      const { data } = await api.put(`/api/agents/${encodeURIComponent(name)}`, p);
      const isNew = !draft.existing;
      setDraft(null); await load();
      if (isNew) onCreated?.(name, data.rules_doc || p.rules_doc);
    } catch (e) { setErr(failure(e)); } finally { setSaving(false); }
  };
  const providerLabel = (value) => connections.find((c) => `cli:${c.name}` === value)?.label || value || "Choose a provider";
  const catalog = connections.find((c) => `cli:${c.name}` === draft?.provider)?.models || {};
  const modelOptions = [...new Set([...(catalog.choices || []), ...(catalog.models || []).flatMap((m) => (m.efforts || []).map((e) => `${m.id}@${e}`))])];
  return <Box sx={{ maxWidth: 980, mx: "auto" }}>
    <Crumb section={section} title={title} onBack={onBack} />
    {err && !draft && <Alert severity="error" sx={{ mb: 2 }}>{err}</Alert>}
    <Box sx={{ display: "flex", alignItems: "center", gap: 2, mb: 2 }}>
      <Typography variant="body2" sx={{ color: DIM, flex: 1 }}>Give each worker a purpose and instructions, then choose its provider and model. Triage uses the purpose to assign new tasks.</Typography>
      <Button variant="contained" startIcon={<AddIcon />} onClick={() => setDraft({ ...BLANK_PROFILE })}>Add profile</Button>
    </Box>
    {!agents && !err && <CircularProgress size={22} />}
    {agents && !Object.keys(agents).length && <Empty>Add a profile to create your first worker.</Empty>}
    {Object.entries(agents || {}).map(([name, a]) => <Box key={name} data-profile={name} sx={{ py: 2, borderBottom: `1px solid ${BORDER}` }}>
      <Box sx={{ display: "flex", alignItems: "center", gap: 1, flexWrap: "wrap" }}>
        <Chip size="small" label={name} /><Typography variant="body2" sx={{ flex: 1 }}>{providerLabel(a.provider)} · {a.model || "Provider default model"}</Typography>
        {a.triage_enabled === false && <Chip size="small" label="Manual only" />}
        {onRules && <Button size="small" onClick={() => onRules(a.rules_doc || name)}>Instructions</Button>}
        <Button size="small" onClick={() => edit(name)}>Edit</Button><Button size="small" color="error" onClick={() => setConfirmDel(name)}>Delete</Button>
      </Box>
      <Typography variant="body2" sx={{ color: DIM, mt: 1 }}>{a.purpose || "Add a purpose so triage knows when to choose this profile."}</Typography>
    </Box>)}
    {draft && <Dialog open fullWidth maxWidth="sm" onClose={() => !saving && setDraft(null)}>
      <DialogTitle>{draft.existing ? `Edit profile · ${draft.name}` : "Add profile"}</DialogTitle>
      <DialogContent><Box sx={{ display: "flex", flexDirection: "column", gap: 2, pt: 1 }}>
        {err && <Alert severity="error">{err}</Alert>}
        <TextField autoFocus label="Profile name" disabled={draft.existing} value={draft.name}
          error={!draft.existing && !!agents?.[draft.name.trim()]} helperText={!draft.existing && agents?.[draft.name.trim()] ? "A profile already uses this name." : ""}
          onChange={(e) => setDraft({ ...draft, name: e.target.value })} />
        <TextField label="Purpose — when should triage choose this profile?" multiline minRows={2} value={draft.purpose} onChange={(e) => setDraft({ ...draft, purpose: e.target.value })} />
        <TextField select label="Model provider" SelectProps={{ displayEmpty: true }} InputLabelProps={{ shrink: true }} value={draft.provider} onChange={(e) => setDraft({ ...draft, provider: e.target.value, model: "" })}>
          <MenuItem value="">Choose a CLI connection</MenuItem>
          {connections.map((c) => <MenuItem key={c.name} value={`cli:${c.name}`}>{c.label}</MenuItem>)}
          {draft.provider && !connections.some((c) => `cli:${c.name}` === draft.provider) && <MenuItem value={draft.provider}>{draft.provider} (unavailable)</MenuItem>}
        </TextField>
        {!connections.length && <Alert severity="info">Configure a CLI under Connections → AI CLI agents first.</Alert>}
        <Autocomplete freeSolo options={modelOptions} inputValue={draft.model} onInputChange={(_, model) => setDraft((d) => ({ ...d, model }))}
          renderInput={(params) => <TextField {...params} label="Model name" helperText="Choose a model or type its name. Leave blank for the provider default." />} />
        <TextField select label="Type of work" value={draft.kind} onChange={(e) => setDraft({ ...draft, kind: e.target.value })}>
          {[...new Set([...PROFILE_KINDS, draft.kind])].map((k) => <MenuItem key={k} value={k}>{k}</MenuItem>)}
        </TextField>
        <TextField select label="Instructions document" SelectProps={{ displayEmpty: true }} InputLabelProps={{ shrink: true }} value={draft.rulesDoc} onChange={(e) => setDraft({ ...draft, rulesDoc: e.target.value })}>
          <MenuItem value="">{draft.kind === "coding" ? "Shared CODER.md" : "Own document with starter instructions"}</MenuItem>
          {[...new Set(["coder", ...Object.entries(agents || {}).map(([n, a]) => a.rules_doc || n), draft.rulesDoc])].filter(Boolean).map((n) => <MenuItem key={n} value={n}>{n.toUpperCase()}.md</MenuItem>)}
        </TextField>
        <FormControlLabel control={<Switch checked={draft.triageEnabled} onChange={(e) => setDraft({ ...draft, triageEnabled: e.target.checked })} />} label="Available to triage for new tasks" />
        <Box><Button variant="contained" disabled={saving || !agents || !draft.name.trim() || (!draft.existing && !!agents?.[draft.name.trim()]) || !connections.some((c) => `cli:${c.name}` === draft.provider) || (draft.triageEnabled && !draft.purpose.trim())} onClick={save}>Save</Button><Button onClick={() => setDraft(null)}>Cancel</Button></Box>
      </Box></DialogContent>
    </Dialog>}
    <ConfirmDelete open={!!confirmDel} what={`the profile "${confirmDel}"`} consequence="Existing sessions are kept. Tasks fall back to the default profile."
      onClose={() => setConfirmDel(null)} onConfirm={async () => { try { await api.delete(`/api/agents/${encodeURIComponent(confirmDel)}`); await load(); } catch (e) { setErr(failure(e)); } }} />
  </Box>;
};
