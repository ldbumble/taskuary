// ONE PAGE FOR A WORKFLOW (the owner, 2026-10-15: "there are a lot of buttons in weird places in workflows"). A workflow wore
// the report wizard - Pipeline, Test & preview, Schedule & save - whose steps are about rows and a summary prompt; a workflow
// has none of those. It is what workflows.definition reads: what to do, who does it, the connections it works in, what it
// asks first, when it is done, and when it runs. Every one of those is a field here, the actions sit in one place at the top,
// and Run now is there for a workflow that is not saved yet (it saves, then runs).
import React, { useEffect, useMemo, useState } from "react";
import { Alert, Box, Button, Chip, CircularProgress, MenuItem, Select, Switch, TextField, Typography } from "@mui/material";
import PlayArrowIcon from "@mui/icons-material/PlayArrow";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import api from "./api";
import { label as btnLabel } from "./buttons.js";
import { BORDER, DIM, FAINT, INK, card } from "./theme.jsx";
import { useAgents } from "./ui.jsx";
import { removeNow } from "./Removed.jsx";
import { effortChoices, keepEffort, modelChoices } from "./workflowBrain.js";
import WorkflowSteps from "./WorkflowSteps.jsx";
import { REPAIR, REPORT_WORDS, asReport, asSteps, askFor, diffKeys, firstMissing, onlyReads, outputsOf, toSaved } from "./workflowFlow.js";
import { openAppLink } from "./appLinks.js";
import { openHelp, useViewExtras } from "./pageView.js";

const parse = (s) => { try { return JSON.parse(s || "{}"); } catch { return {}; } };
const DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const hm = (t) => { const [h, m] = String(t || "08:00").split(":"); return [Number(h) || 0, Number(m) || 0]; };
const pad = (n) => String(n).padStart(2, "0");

// the schedule as one of the shapes people say, read off whichever key the config carries
export const scheduleOf = (c) => {
  if (c.every_minutes) return { mode: "every", minutes: c.every_minutes };
  if (c.daily_at) return { mode: "daily", at: c.daily_at };
  const f = String(c.cron || "").trim().split(/\s+/);
  if (f.length === 5 && /^\d+$/.test(f[0]) && /^\d+$/.test(f[1]) && f[3] === "*") {
    const at = `${pad(f[1])}:${pad(f[0])}`;
    if (f[2] === "*" && /^[0-6](,[0-6])*$/.test(f[4])) return { mode: "weekly", at, days: f[4].split(",").map(Number) };
    if (f[2] === "*" && f[4] === "1-5") return { mode: "weekly", at, days: [1, 2, 3, 4, 5] };
    if (/^\d+$/.test(f[2]) && f[4] === "*") return { mode: "monthly", at, day: Number(f[2]) };
  }
  if (c.cron) return { mode: "cron", cron: c.cron };
  return { mode: "manual" };
};

// ...and back: exactly one key, the others cleared, so the scheduler never reads two answers
export const withSchedule = (c, s) => {
  const out = { ...c }; delete out.every_minutes; delete out.daily_at; delete out.cron;
  const [h, m] = hm(s.at);
  if (s.mode === "every" && s.minutes) out.every_minutes = Number(s.minutes);
  if (s.mode === "daily") out.daily_at = `${pad(h)}:${pad(m)}`;
  if (s.mode === "weekly") out.cron = `${m} ${h} * * ${[...(s.days?.length ? s.days : [1])].sort().join(",")}`;
  if (s.mode === "monthly") out.cron = `${m} ${h} ${s.day || 1} * *`;
  if (s.mode === "cron" && String(s.cron || "").trim()) out.cron = String(s.cron).trim();
  return out;
};

export const scheduleWords = (s) => s.mode === "every" ? `every ${s.minutes} minutes`
  : s.mode === "daily" ? `every day at ${s.at}`
  : s.mode === "weekly" ? `${(s.days || []).map((d) => DAYS[d]).join(", ")} at ${s.at}`
  : s.mode === "monthly" ? `on the ${s.day} of each month at ${s.at}`
  : s.mode === "cron" ? `cron ${s.cron}` : "only when you press Run now";

// ...and when a mail starts it too (workflows.from_mail): the clock alone said "only when you press Run now" over a job a mail starts
export const runsWords = (s, c) => String(c?.on_mail || "").trim()
  ? `${s.mode === "manual" ? "" : `${scheduleWords(s)}, and `}when a mail like the one described arrives` : scheduleWords(s);

const Field = ({ label, hint, children }) => (
  <Box sx={{ mb: 2 }}>
    <Typography sx={{ color: INK, fontWeight: 600, fontSize: 13, mb: 0.25 }}>{label}</Typography>
    {hint && <Typography variant="caption" sx={{ color: FAINT, display: "block", mb: 0.75 }}>{hint}</Typography>}
    {children}
  </Box>
);

// WHEN IT RUNS: one picker for a workflow and a report alike (the 2026-10-21 UI audit, B3) - the report's free "daily at HH:MM" box
// saved "7am", which the scheduler cannot read. Every choice here writes a key it can (withSchedule); Custom keeps cron for the rest.
export const SchedulePicker = ({ sched, setSched, cron = "" }) => (
  <Box sx={{ display: "flex", alignItems: "center", gap: 1, flexWrap: "wrap" }}>
    <Select size="small" value={sched.mode} onChange={(e) => setSched((s) => ({ at: s.at || "08:00", days: s.days || [1], day: s.day || 1,
      minutes: s.minutes || 60, cron: s.cron || cron || "", mode: e.target.value }))} sx={{ minWidth: 190, bgcolor: "#fff", fontSize: 13 }}>
      <MenuItem value="manual" sx={{ fontSize: 13 }}>Only when I press Run now</MenuItem>
      <MenuItem value="daily" sx={{ fontSize: 13 }}>Every day</MenuItem>
      <MenuItem value="weekly" sx={{ fontSize: 13 }}>Every week</MenuItem>
      <MenuItem value="monthly" sx={{ fontSize: 13 }}>Every month</MenuItem>
      <MenuItem value="every" sx={{ fontSize: 13 }}>Every few minutes</MenuItem>
      <MenuItem value="cron" sx={{ fontSize: 13 }}>Custom (cron)</MenuItem>
    </Select>
    {sched.mode === "weekly" && DAYS.map((d, i) => {
      const on = (sched.days || []).includes(i);
      return <Chip key={d} size="small" label={d} variant={on ? "filled" : "outlined"} color={on ? "primary" : "default"}
        onClick={() => setSched((s) => ({ ...s, days: on ? s.days.filter((x) => x !== i) : [...(s.days || []), i] }))} />;
    })}
    {sched.mode === "monthly" && <TextField size="small" type="number" label="day" value={sched.day}
      inputProps={{ min: 1, max: 28 }} sx={{ width: 80, bgcolor: "#fff" }}
      onChange={(e) => setSched((s) => ({ ...s, day: Math.min(28, Math.max(1, Number(e.target.value) || 1)) }))} />}
    {["daily", "weekly", "monthly"].includes(sched.mode) && <TextField size="small" type="time" label="at" value={sched.at}
      sx={{ width: 120, bgcolor: "#fff" }} onChange={(e) => setSched((s) => ({ ...s, at: e.target.value }))} />}
    {sched.mode === "every" && <TextField size="small" type="number" label="minutes" value={sched.minutes}
      sx={{ width: 110, bgcolor: "#fff" }} onChange={(e) => setSched((s) => ({ ...s, minutes: e.target.value }))} />}
    {sched.mode === "cron" && <TextField size="small" label="cron" value={sched.cron} placeholder="0 8 * * 1"
      sx={{ width: 160, bgcolor: "#fff" }} onChange={(e) => setSched((s) => ({ ...s, cron: e.target.value }))} />}
  </Box>
);


export default function WorkflowEditor({ sourceId, sources, connectors, types, draft, reload, onBack, onSaved, note, composer, lastRun,
  lastRunRec, fixRun, onFixTaken, onReport }) {
  const cur = sources.find((s) => s.SourceId === sourceId) || null;
  const [cfg, setCfg] = useState(() => ({ type: "agent", access: "write", ...(cur ? parse(cur.ConfigJson) : draft || {}) }));
  const [sched, setSched] = useState(() => scheduleOf(cur ? parse(cur.ConfigJson) : draft || {}));
  // a draft the composer fills in while this page is open replaces the form - it is what the owner just asked for
  useEffect(() => { if (!cur && draft) { setCfg({ type: "agent", access: "write", ...draft }); setSched(scheduleOf(draft)); } }, [draft, cur]);
  const [busy, setBusy] = useState("");
  const [msg, setMsg] = useState(null);
  // REMOVE IS AT ONCE (the owner, 2026-10-21): the Workflows list says "Removed <it> - Undo", and Recently deleted keeps it 30 days
  const remove = async () => {
    try { await removeNow(() => api.delete(`/api/sources/${cur.SourceId}`), "workflow", cfg.title || cur.Address); await reload(); onBack(); }
    catch (e) { setMsg({ ok: false, text: e?.response?.data?.detail || "It could not be removed." }); }
  };
  const { agents, kinds } = useAgents();
  // who does it: the general profiles. A coding name only runs code work (a repository folder below), so it is not offered here
  const roles = agents.filter((a) => !["coding", "cli"].includes(String(kinds[a] || "").toLowerCase()));
  const live = useMemo(() => (connectors || []).filter((c) => c.Active), [connectors]);
  const uses = (cfg.uses || []).map(Number);
  const set = (k, v) => setCfg((c) => ({ ...c, [k]: v }));
  // which model it runs on: the general agents' brain unless this job asks for more (workflows.brain_options)
  const [brain, setBrain] = useState(null);
  useEffect(() => { api.get("/api/workflows/brain").then(({ data }) => setBrain(data?.models ? data : null)).catch(() => setBrain(null)); }, []);
  const models = modelChoices(brain);
  if (cfg.model && models.length && !models.some((m) => m.value === cfg.model)) models.push({ value: cfg.model, label: cfg.model });
  const efforts = effortChoices(brain, cfg.model);
  // STEPS (flow.py): what each step last came back with - the last run's, then every test - and a repair not yet kept
  const steps = asSteps(cfg);
  const [outputs, setOutputs] = useState(() => outputsOf(lastRunRec?.steps));
  const [repair, setRepair] = useState(null);       // {was, explain} while the AI's repair waits on Keep or Discard
  const setFlow = (f) => setCfg((c) => ({ ...c, flow: typeof f === "function" ? f(c.flow || []) : f }));
  const names = Object.fromEntries((connectors || []).map((c) => [c.ConnectorId, c.Name || c.Type]));
  const turnIntoSteps = async () => {
    setBusy("steps"); setMsg(null);
    try {
      const { data } = await api.post("/api/workflows/compose", { ask: askFor(cfg, names) });
      if (data.config?.flow?.length) {
        setCfg((c) => ({ ...c, flow: data.config.flow, ...(data.config.repair ? { repair: data.config.repair } : {}) }));
        setMsg({ ok: true, text: `${data.explain || "Drafted as steps."} Test each step, then Save - nothing is saved yet.` });
      } else if (data.questions?.length) setMsg({ ok: false, text: `It needs to know: ${data.questions.join(" ")}` });
      else if (data.config) setMsg({ ok: true, text: "It reads as work for an agent's hands throughout, so it stays one prompt." });
      else setMsg({ ok: false, text: data.error || "It could not be turned into steps." });
    } catch (e) { setMsg({ ok: false, text: e?.response?.data?.detail || "It could not be turned into steps." }); }
    finally { setBusy(""); }
  };
  // Fix with AI: a failed run's failed step, repaired by the model and shown as an unsaved change - Keep, then Save, or Discard
  const fix = async (runId) => {
    if (!cur || !runId) return;
    setBusy("fix"); setMsg(null);
    try {
      const { data } = await api.post(`/api/workflows/${cur.SourceId}/repair`, { run_id: runId, ...(cfg.flow?.length ? { flow: toSaved(cfg.flow) } : {}) });
      if (data.flow) { setRepair({ was: cfg.flow || [], explain: data.explain || "" }); setCfg((c) => ({ ...c, flow: data.flow })); }
      else setMsg({ ok: false, text: data.questions?.length ? `It needs to know: ${data.questions.join(" ")}` : data.error || "No fix was found.",
        fix: data.fix?.href ? data.fix : null });      // no AI, or the app broke and not the steps: where that is fixed
    } catch (e) { setMsg({ ok: false, text: e?.response?.data?.detail || "No fix was found." }); }
    finally { setBusy(""); }
  };
  // ...and once the workflow has loaded: a fix asked for from the run task arrives before it has
  useEffect(() => { if (fixRun && cur) { fix(fixRun); onFixTaken?.(); } }, [fixRun, cur?.SourceId]);   // eslint-disable-line react-hooks/exhaustive-deps
  const changed = repair ? diffKeys(repair.was, cfg.flow) : null;
  const canFix = !!(cur && steps && lastRunRec?.failed && lastRunRec?.run_id && (lastRunRec.steps || []).some((r) => r.status === "failed"));
  // FIX WITH AI OPENS THE CHAT (2026-10-30): the repair it ran is the Assistant's to press here, as the owner's own "Repair the failed step"
  // would be - it lands as the same unsaved change (Keep, then Save stay the owner's)
  useViewExtras("reports", { buttons: canFix ? [{ id: "repair", label: "Repair the failed step", press: () => fix(lastRunRec.run_id) }] : [] });

  const body = () => {
    const c = withSchedule({ ...cfg, type: "agent", access: "write" }, sched);
    if (Array.isArray(c.flow)) c.flow = toSaved(c.flow);
    for (const k of Object.keys(c)) if (c[k] === "" || c[k] == null || (Array.isArray(c[k]) && !c[k].length)) delete c[k];
    if (!c.browser) delete c.browser;
    if (c.repair === "auto") delete c.repair;
    return c;
  };
  const missing = !String(cfg.title || "").trim() ? "a name"
    : steps ? (!(cfg.flow || []).length ? "a first step" : "") : !String(cfg.prompt || cfg.skill || "").trim() ? "what it does" : "";
  const stepMissing = steps ? firstMissing(cfg.flow) : "";
  const save = async () => {
    if (missing) { setMsg({ ok: false, text: `Give it ${missing} first.` }); return null; }
    if (stepMissing) { setMsg({ ok: false, text: `Not yet: ${stepMissing}.` }); return null; }
    setBusy("save"); setMsg(null);
    try {
      const c = body();
      const { data } = await api.post("/api/sources", { ...(cur ? { SourceId: cur.SourceId } : {}), Channel: "report",
        Address: c.title, ConfigJson: JSON.stringify(c), Active: cur ? !!cur.Active : true });
      await reload();
      setMsg({ ok: true, text: `Saved — runs ${runsWords(sched, cfg)}.` }); setRepair(null);
      if (!cur) onSaved?.(data.sourceId);
      return data.sourceId || cur?.SourceId;
    } catch (e) { setMsg({ ok: false, text: e?.response?.data?.detail || "It could not be saved." }); return null; }
    finally { setBusy(""); }
  };
  // Run now: saved first (the run reads the stored definition), then started - and the run is a task, so it opens there
  const runNow = async () => {
    const sid = await save();
    if (!sid) return;
    setBusy("run");
    try {
      const { data } = await api.post(`/api/reports/${sid}/rerun`);
      if (data.task_id) { openAppLink(`task=${data.task_id}`); return; }
      setMsg({ ok: true, text: `${data.title || "It"} is running.` });
    } catch (e) { setMsg({ ok: false, text: e?.response?.data?.detail || "It could not be started." }); }
    finally { setBusy(""); }
  };
  const toggle = async () => {
    try { await api.post("/api/sources", { SourceId: cur.SourceId, Active: !cur.Active }); await reload(); }
    catch (e) { setMsg({ ok: false, text: e?.response?.data?.detail || "It could not be switched." }); }
  };

  return (
    <Box sx={{ maxWidth: 820, mx: "auto" }}>
      {/* the title alone: the back button above already says Workflows */}
      <Typography sx={{ color: INK, fontWeight: 600, fontSize: 20, lineHeight: 1.2, mb: 1.5 }}>{cur ? (cfg.title || "Routine") : "New routine"}</Typography>
      {/* the actions, together: what it is doing now, and the three things you can do about it */}
      <Box sx={{ display: "flex", alignItems: "center", gap: 1, flexWrap: "wrap", mb: 2, mt: -1 }}>
        <Typography variant="body2" sx={{ color: DIM, flex: 1, minWidth: 200 }}>
          {cur ? `${cur.Active ? "On" : "Off"} · runs ${runsWords(sched, cfg)}` : `Not saved yet · will run ${runsWords(sched, cfg)}`}
        </Typography>
        {cur && <Box sx={{ display: "flex", alignItems: "center" }}>
          <Switch size="small" checked={!!cur.Active} onChange={toggle} />
          <Typography variant="caption" sx={{ color: DIM }}>{cur.Active ? "on" : "off"}</Typography>
        </Box>}
        <Button variant="outlined" size="small" disabled={!!busy} onClick={runNow}
          startIcon={busy === "run" ? <CircularProgress size={12} /> : <PlayArrowIcon sx={{ fontSize: 16 }} />}>
          {cur ? "Run now" : "Save & run now"}</Button>
        <Button variant="contained" size="small" disableElevation disabled={!!busy} onClick={save}>
          {busy === "save" ? "Saving…" : "Save"}</Button>
      </Box>
      {msg && <Alert severity={msg.ok ? "success" : "warning"} sx={{ mb: 1.5, fontSize: 12.5 }} onClose={() => setMsg(null)}
        action={msg.fix ? <Button size="small" component="a" href={msg.fix.href} sx={{ fontSize: 12 }}>{msg.fix.label || btnLabel("fix")}</Button> : null}>{msg.text}</Alert>}
      {lastRun && lastRun({ onFix: canFix ? () => openHelp(`Fix the failed run of ${cfg.title || cur?.Address || "this routine"}`) : null, fixing: busy === "fix",
        // a repair taken back puts the old steps on the saved workflow: the page shows them too
        onChanged: async () => { await reload(); const { data } = await api.get("/api/sources"); const row = (data.data || []).find((x) => x.SourceId === cur?.SourceId);
          if (row) setCfg((c) => ({ ...c, flow: parse(row.ConfigJson).flow })); } })}
      {repair && <Alert severity="info" sx={{ mb: 1.5, fontSize: 12.5 }} action={<Box sx={{ display: "flex", gap: 0.5 }}>
        <Button size="small" color="inherit" onClick={() => { setRepair(null); setMsg({ ok: true, text: "Kept - Save to make it this routine's steps." }); }}>Keep</Button>
        <Button size="small" color="inherit" onClick={() => { setCfg((c) => ({ ...c, flow: repair.was })); setRepair(null); }}>Discard</Button></Box>}>
        The AI's repair{repair.explain ? `: ${repair.explain}` : "."} The changed steps are marked below - nothing is saved yet.</Alert>}
      {/* describing it is how a new one starts; a draft that arrived built (New, or this box) is already past that */}
      {!cur && !draft && composer}
      {note && <Alert severity={note.severity} sx={{ mb: 1.5, fontSize: 12.5 }}>{note.text}</Alert>}

      <Box sx={{ ...card, p: 2.5 }}>
        <Field label="Name" hint="the headline each run's task carries">
          <TextField size="small" fullWidth value={cfg.title || ""} placeholder="Weekly duplicate employee check"
            onChange={(e) => set("title", e.target.value)} sx={{ bgcolor: "#fff" }} />
        </Field>
        {/* A WORKFLOW IS A GOAL (flow.repair): a broken step is fixed by itself only while this still holds */}
        {steps && <Field label="Goal" hint="what it is for, in plain words - a step that breaks is repaired toward this, and anything that would change it asks you first">
          <TextField size="small" fullWidth multiline minRows={1} value={cfg.goal || ""} placeholder="Every Monday, catch AP bills posted twice and get finance to void them."
            onChange={(e) => set("goal", e.target.value)} sx={{ bgcolor: "#fff" }} />
        </Field>}
        {steps ? <Field label="Steps" hint="top to bottom, each the same every run - test one before you save, and only the AI steps use a model">
          {/* READS ONLY IS A REPORT (the owner, 2026-10-18): every workflow run is a task, so steps that only read and judge are
              offered as the report they are - the same reads and prompt, one press away. Saving as a workflow still works. */}
          {onlyReads(cfg.flow, types) && <Alert severity="info" data-tq-report-suggestion="" sx={{ mb: 1.25, fontSize: 12.5 }}
            action={onReport ? <Button size="small" color="inherit" sx={{ whiteSpace: "nowrap" }} onClick={() => onReport(asReport(cfg))}>{btnLabel("make_report")}</Button> : null}>
            {REPORT_WORDS} Add a step that acts - open a task, draft a message, write to a system - or make it a report.</Alert>}
          <WorkflowSteps flow={cfg.flow || []} setFlow={setFlow} outputs={outputs} setOutputs={setOutputs} connectors={connectors} types={types}
            agents={roles} title={cfg.title} sourceId={cur?.SourceId} inputs={cfg.inputs} changed={changed} />
          {!(cfg.flow || []).length && <Typography component="button" type="button" onClick={() => setCfg((c) => { const n = { ...c }; delete n.flow; return n; })}
            sx={{ border: 0, bgcolor: "transparent", p: 0, mt: 0.5, cursor: "pointer", color: "#55697a", fontSize: 12, fontWeight: 600 }}>
            Use one agent prompt instead</Typography>}
        </Field>
        : <Field label="What it does" hint="the job, in plain words - the agent reads exactly this on every run">
          <TextField size="small" fullWidth multiline minRows={3} value={cfg.prompt || ""}
            placeholder="Check Intacct for active employees that share a name or SSN last four, and open a task for finance per pair."
            onChange={(e) => set("prompt", e.target.value)} sx={{ bgcolor: "#fff" }} />
          {/* the same job as steps: code for the reads and writes, a model only where it judges (flow.py) */}
          <Box sx={{ display: "flex", alignItems: "center", gap: 1.5, mt: 0.75, flexWrap: "wrap" }}>
            <Button size="small" variant="outlined" disabled={!!busy || !String(cfg.prompt || "").trim()} onClick={turnIntoSteps}
              startIcon={busy === "steps" ? <CircularProgress size={12} /> : null}>{busy === "steps" ? "Drafting steps…" : "Turn into steps"}</Button>
            <Typography component="button" type="button" onClick={() => set("flow", [])}
              sx={{ border: 0, bgcolor: "transparent", p: 0, cursor: "pointer", color: "#55697a", fontSize: 12, fontWeight: 600 }}>or build the steps yourself</Typography>
            <Typography variant="caption" sx={{ color: FAINT }}>so the same reads and writes run as code, and the AI only judges</Typography>
          </Box>
        </Field>}
        <Field label="Who does it" hint="the profile whose rules it works by">
          <Select size="small" displayEmpty value={roles.includes(cfg.agent) ? cfg.agent : ""} onChange={(e) => set("agent", e.target.value)}
            sx={{ minWidth: 220, bgcolor: "#fff", fontSize: 13 }}>
            <MenuItem value="" sx={{ fontSize: 13 }}>{roles.includes("assistant") ? "assistant (the default)" : "the default"}</MenuItem>
            {roles.filter((a) => a !== "assistant").map((a) => <MenuItem key={a} value={a} sx={{ fontSize: 13 }}>{a}</MenuItem>)}
          </Select>
        </Field>
        {brain && <Field label="Model" hint="the general agents' own unless this job is hard enough to need a stronger model or more thought">
          <Box sx={{ display: "flex", gap: 1, flexWrap: "wrap" }}>
            <Select size="small" displayEmpty value={cfg.model || ""} sx={{ minWidth: 280, bgcolor: "#fff", fontSize: 13 }}
              onChange={(e) => setCfg((c) => ({ ...c, model: e.target.value, effort: keepEffort(brain, e.target.value, c.effort) }))}>
              {models.map((m) => <MenuItem key={m.value || "same"} value={m.value} sx={{ fontSize: 13 }}>{m.label}</MenuItem>)}
            </Select>
            {!!efforts.length && <Select size="small" displayEmpty value={efforts.some((x) => x.value === cfg.effort) ? cfg.effort : ""}
              onChange={(e) => set("effort", e.target.value)} sx={{ minWidth: 150, bgcolor: "#fff", fontSize: 13 }}>
              {efforts.map((x) => <MenuItem key={x.value || "default"} value={x.value} sx={{ fontSize: 13 }}>{x.label}</MenuItem>)}
            </Select>}
          </Box>
        </Field>}
        <Field label="Works in" hint="the connections it may read and change - nothing outside them without asking">
          <Box sx={{ display: "flex", flexWrap: "wrap", gap: 0.75 }}>
            {live.map((c) => {
              const on = uses.includes(c.ConnectorId);
              return <Chip key={c.ConnectorId} size="small" label={c.Name || c.Type} variant={on ? "filled" : "outlined"}
                color={on ? "primary" : "default"}
                onClick={() => set("uses", on ? uses.filter((x) => x !== c.ConnectorId) : [...uses, c.ConnectorId])} />;
            })}
            {!live.length && <Typography variant="caption" sx={{ color: FAINT }}>No connections are switched on - Connections tab.</Typography>}
          </Box>
          <Box sx={{ display: "flex", alignItems: "center", mt: 1 }}>
            <Switch size="small" checked={!!cfg.browser} onChange={(e) => set("browser", e.target.checked)} />
            <Typography variant="caption" sx={{ color: DIM }}>works on web pages, in a browser you can watch</Typography>
          </Box>
        </Field>
        <Field label="Ask me before" hint="what it stops and asks you about, every run">
          <TextField size="small" fullWidth value={cfg.ask_first || ""} placeholder="changing or deleting any Intacct record"
            onChange={(e) => set("ask_first", e.target.value)} sx={{ bgcolor: "#fff" }} />
        </Field>
        <Field label="Done when" hint="what a finished run looks like - and what it says when there was nothing to do">
          <TextField size="small" fullWidth value={cfg.done_when || ""} placeholder='one finance task per duplicate pair; "all clear" when there are none'
            onChange={(e) => set("done_when", e.target.value)} sx={{ bgcolor: "#fff" }} />
        </Field>
        {/* A MAIL STARTS IT (the owner, 2026-10-21): said in words, like a playbook's "when" - triage is shown it beside the playbooks
            and starts this workflow on a mail that is one; the run is that mail's task, and its steps read it as {{mail.subject}} */}
        <Field label="Start when a mail like this arrives" hint="optional - describe the mail in words; triage starts this routine when one like it comes in, and the steps read it as {{mail.from}}, {{mail.subject}}, {{mail.body}}">
          <TextField size="small" fullWidth value={cfg.on_mail || ""} placeholder="a vendor sends an invoice for something we ordered"
            onChange={(e) => set("on_mail", e.target.value)} sx={{ bgcolor: "#fff" }} />
        </Field>
        <Field label="When it runs">
          <SchedulePicker sched={sched} setSched={setSched} cron={cfg.cron} />
        </Field>
        <Box component="details" sx={{ mt: 1, borderTop: `1px solid ${BORDER}`, pt: 1.5 }}>
          <Box component="summary" sx={{ cursor: "pointer", color: DIM, fontSize: 12.5, fontWeight: 600 }}>More</Box>
          <Box sx={{ mt: 1.5 }}>
            <Field label="Saved skill" hint="a slash command with the steps written down, run before the words above (optional)">
              <TextField size="small" value={cfg.skill || ""} placeholder="weekly-user-review"
                onChange={(e) => set("skill", e.target.value.replace(/^\//, ""))} sx={{ bgcolor: "#fff", width: 280 }} />
            </Field>
            {steps && <Field label="When a step fails" hint="the AI repairs the step toward the goal; a fix that would change the goal, or send or write somewhere new, always waits for you">
              <Select size="small" value={cfg.repair || "auto"} onChange={(e) => set("repair", e.target.value)} sx={{ minWidth: 300, bgcolor: "#fff", fontSize: 13 }}>
                {REPAIR.map(([v, w]) => <MenuItem key={v} value={v} sx={{ fontSize: 13 }}>{w}</MenuItem>)}
              </Select>
            </Field>}
            <Field label="Repository folder" hint="only for work on code: the run is a coding session in this checkout">
              <TextField size="small" fullWidth value={cfg.cwd || ""} placeholder="C:/work/census"
                onChange={(e) => set("cwd", e.target.value)} sx={{ bgcolor: "#fff" }} />
            </Field>
            {cur && <Button size="small" color="error" startIcon={<DeleteOutlineIcon sx={{ fontSize: 15 }} />}
              onClick={remove}>Remove routine</Button>}
          </Box>
        </Box>
      </Box>
    </Box>
  );
}
