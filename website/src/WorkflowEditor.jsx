import { t as tx } from "./i18n.js";
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
import { BORDER, DIM, FAINT, INK, card } from "./theme.jsx";
import { Crumb, ConfirmDelete, useAgents } from "./ui.jsx";

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

const Field = ({ label, hint, children }) => (
  <Box sx={{ mb: 2 }}>
    <Typography sx={{ color: INK, fontWeight: 600, fontSize: 13, mb: 0.25 }}>{label}</Typography>
    {hint && <Typography variant="caption" sx={{ color: FAINT, display: "block", mb: 0.75 }}>{hint}</Typography>}
    {children}
  </Box>
);

export default function WorkflowEditor({ sourceId, sources, connectors, draft, reload, onBack, onSaved, note, composer, lastRun }) {
  const cur = sources.find((s) => s.SourceId === sourceId) || null;
  const [cfg, setCfg] = useState(() => ({ type: "agent", access: "write", ...(cur ? parse(cur.ConfigJson) : draft || {}) }));
  const [sched, setSched] = useState(() => scheduleOf(cur ? parse(cur.ConfigJson) : draft || {}));
  // a draft the composer fills in while this page is open replaces the form - it is what the owner just asked for
  useEffect(() => { if (!cur && draft) { setCfg({ type: "agent", access: "write", ...draft }); setSched(scheduleOf(draft)); } }, [draft, cur]);
  const [busy, setBusy] = useState("");
  const [msg, setMsg] = useState(null);
  const [confirmDel, setConfirmDel] = useState(false);
  const { agents, kinds } = useAgents();
  // who does it: the general profiles. A coding name only runs code work (a repository folder below), so it is not offered here
  const roles = agents.filter((a) => !["coding", "cli"].includes(String(kinds[a] || "").toLowerCase()));
  const live = useMemo(() => (connectors || []).filter((c) => c.Active), [connectors]);
  const uses = (cfg.uses || []).map(Number);
  const set = (k, v) => setCfg((c) => ({ ...c, [k]: v }));

  const body = () => {
    const c = withSchedule({ ...cfg, type: "agent", access: "write" }, sched);
    for (const k of Object.keys(c)) if (c[k] === "" || c[k] == null || (Array.isArray(c[k]) && !c[k].length)) delete c[k];
    if (!c.browser) delete c.browser;
    return c;
  };
  const missing = !String(cfg.title || "").trim() ? "a name" : !String(cfg.prompt || cfg.skill || "").trim() ? "what it does" : "";
  const save = async () => {
    if (missing) { setMsg({ ok: false, text: `Give it ${missing} first.` }); return null; }
    setBusy("save"); setMsg(null);
    try {
      const c = body();
      const { data } = await api.post("/api/sources", { ...(cur ? { SourceId: cur.SourceId } : {}), Channel: "report",
        Address: c.title, ConfigJson: JSON.stringify(c), Active: cur ? !!cur.Active : true });
      await reload();
      setMsg({ ok: true, text: `Saved — runs ${scheduleWords(sched)}.` });
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
      if (data.task_id) { window.location.hash = `task=${data.task_id}`; return; }
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
      <Crumb section="Workflows" onBack={onBack} title={cur ? (cfg.title || "Workflow") : "New workflow"} />
      {/* the actions, together: what it is doing now, and the three things you can do about it */}
      <Box sx={{ display: "flex", alignItems: "center", gap: 1, flexWrap: "wrap", mb: 2, mt: -1 }}>
        <Typography variant="body2" sx={{ color: DIM, flex: 1, minWidth: 200 }}>
          {cur ? `${cur.Active ? "On" : "Off"} · runs ${scheduleWords(sched)}` : `Not saved yet · will run ${scheduleWords(sched)}`}
        </Typography>
        {cur && <Box sx={{ display: "flex", alignItems: "center" }}>
          <Switch size="small" checked={!!cur.Active} onChange={toggle} />
          <Typography variant="caption" sx={{ color: DIM }}>{cur.Active ? "on" : tx("off")}</Typography>
        </Box>}
        <Button variant="outlined" size="small" disabled={!!busy} onClick={runNow}
          startIcon={busy === "run" ? <CircularProgress size={12} /> : <PlayArrowIcon sx={{ fontSize: 16 }} />}>
          {cur ? "Run now" : "Save & run now"}</Button>
        <Button variant="contained" size="small" disableElevation disabled={!!busy} onClick={save}>
          {busy === "save" ? "Saving…" : tx("Save")}</Button>
      </Box>
      {msg && <Alert severity={msg.ok ? "success" : "warning"} sx={{ mb: 1.5, fontSize: 12.5 }} onClose={() => setMsg(null)}>{msg.text}</Alert>}
      {lastRun}
      {!cur && composer}
      {note && <Alert severity={note.severity} sx={{ mb: 1.5, fontSize: 12.5 }}>{note.text}</Alert>}

      <Box sx={{ ...card, p: 2.5 }}>
        <Field label={tx("Name")} hint={tx("the headline each run's task carries")}>
          <TextField size="small" fullWidth value={cfg.title || ""} placeholder={tx("Weekly duplicate employee check")}
            onChange={(e) => set("title", e.target.value)} sx={{ bgcolor: "#fff" }} />
        </Field>
        <Field label={tx("What it does")} hint={tx("the job, in plain words - the agent reads exactly this on every run")}>
          <TextField size="small" fullWidth multiline minRows={3} value={cfg.prompt || ""}
            placeholder={tx("Check Intacct for active employees that share a name or SSN last four, and open a task for finance per pair.")}
            onChange={(e) => set("prompt", e.target.value)} sx={{ bgcolor: "#fff" }} />
        </Field>
        <Field label={tx("Who does it")} hint={tx("the profile whose rules it works by; which AI runs it is your default brain")}>
          <Select size="small" displayEmpty value={roles.includes(cfg.agent) ? cfg.agent : ""} onChange={(e) => set("agent", e.target.value)}
            sx={{ minWidth: 220, bgcolor: "#fff", fontSize: 13 }}>
            <MenuItem value="" sx={{ fontSize: 13 }}>{roles.includes("assistant") ? "assistant (the default)" : "the default"}</MenuItem>
            {roles.filter((a) => a !== "assistant").map((a) => <MenuItem key={a} value={a} sx={{ fontSize: 13 }}>{a}</MenuItem>)}
          </Select>
        </Field>
        <Field label={tx("Works in")} hint={tx("the connections it may read and change - nothing outside them without asking")}>
          <Box sx={{ display: "flex", flexWrap: "wrap", gap: 0.75 }}>
            {live.map((c) => {
              const on = uses.includes(c.ConnectorId);
              return <Chip key={c.ConnectorId} size="small" label={c.Name || c.Type} variant={on ? "filled" : "outlined"}
                color={on ? "primary" : "default"}
                onClick={() => set("uses", on ? uses.filter((x) => x !== c.ConnectorId) : [...uses, c.ConnectorId])} />;
            })}
            {!live.length && <Typography variant="caption" sx={{ color: FAINT }}>{tx("No connections are switched on - Connections tab.")}</Typography>}
          </Box>
          <Box sx={{ display: "flex", alignItems: "center", mt: 1 }}>
            <Switch size="small" checked={!!cfg.browser} onChange={(e) => set("browser", e.target.checked)} />
            <Typography variant="caption" sx={{ color: DIM }}>{tx("works on web pages, in a browser you can watch")}</Typography>
          </Box>
        </Field>
        <Field label={tx("Ask me before")} hint={tx("what it stops and asks you about, every run")}>
          <TextField size="small" fullWidth value={cfg.ask_first || ""} placeholder={tx("changing or deleting any Intacct record")}
            onChange={(e) => set("ask_first", e.target.value)} sx={{ bgcolor: "#fff" }} />
        </Field>
        <Field label={tx("Done when")} hint={tx("what a finished run looks like - and what it says when there was nothing to do")}>
          <TextField size="small" fullWidth value={cfg.done_when || ""} placeholder={tx("one finance task per duplicate pair; \"all clear\" when there are none")}
            onChange={(e) => set("done_when", e.target.value)} sx={{ bgcolor: "#fff" }} />
        </Field>
        <Field label={tx("When it runs")}>
          <Box sx={{ display: "flex", alignItems: "center", gap: 1, flexWrap: "wrap" }}>
            <Select size="small" value={sched.mode} onChange={(e) => setSched((s) => ({ at: s.at || "08:00", days: s.days || [1], day: s.day || 1,
              minutes: s.minutes || 60, cron: s.cron || cfg.cron || "", mode: e.target.value }))} sx={{ minWidth: 190, bgcolor: "#fff", fontSize: 13 }}>
              <MenuItem value="manual" sx={{ fontSize: 13 }}>{tx("Only when I press Run now")}</MenuItem>
              <MenuItem value="daily" sx={{ fontSize: 13 }}>{tx("Every day")}</MenuItem>
              <MenuItem value="weekly" sx={{ fontSize: 13 }}>{tx("Every week")}</MenuItem>
              <MenuItem value="monthly" sx={{ fontSize: 13 }}>{tx("Every month")}</MenuItem>
              <MenuItem value="every" sx={{ fontSize: 13 }}>{tx("Every few minutes")}</MenuItem>
              <MenuItem value="cron" sx={{ fontSize: 13 }}>{tx("Custom (cron)")}</MenuItem>
            </Select>
            {sched.mode === "weekly" && DAYS.map((d, i) => {
              const on = (sched.days || []).includes(i);
              return <Chip key={d} size="small" label={d} variant={on ? "filled" : "outlined"} color={on ? "primary" : "default"}
                onClick={() => setSched((s) => ({ ...s, days: on ? s.days.filter((x) => x !== i) : [...(s.days || []), i] }))} />;
            })}
            {sched.mode === "monthly" && <TextField size="small" type="number" label={tx("day")} value={sched.day}
              inputProps={{ min: 1, max: 28 }} sx={{ width: 80, bgcolor: "#fff" }}
              onChange={(e) => setSched((s) => ({ ...s, day: Math.min(28, Math.max(1, Number(e.target.value) || 1)) }))} />}
            {["daily", "weekly", "monthly"].includes(sched.mode) && <TextField size="small" type="time" label={tx("at")} value={sched.at}
              sx={{ width: 120, bgcolor: "#fff" }} onChange={(e) => setSched((s) => ({ ...s, at: e.target.value }))} />}
            {sched.mode === "every" && <TextField size="small" type="number" label={tx("minutes")} value={sched.minutes}
              sx={{ width: 110, bgcolor: "#fff" }} onChange={(e) => setSched((s) => ({ ...s, minutes: e.target.value }))} />}
            {sched.mode === "cron" && <TextField size="small" label="cron" value={sched.cron} placeholder="0 8 * * 1"
              sx={{ width: 160, bgcolor: "#fff" }} onChange={(e) => setSched((s) => ({ ...s, cron: e.target.value }))} />}
          </Box>
        </Field>
        <Box component="details" sx={{ mt: 1, borderTop: `1px solid ${BORDER}`, pt: 1.5 }}>
          <Box component="summary" sx={{ cursor: "pointer", color: DIM, fontSize: 12.5, fontWeight: 600 }}>{tx("More")}</Box>
          <Box sx={{ mt: 1.5 }}>
            <Field label={tx("Saved skill")} hint={tx("a slash command with the steps written down, run before the words above (optional)")}>
              <TextField size="small" value={cfg.skill || ""} placeholder="weekly-user-review"
                onChange={(e) => set("skill", e.target.value.replace(/^\//, ""))} sx={{ bgcolor: "#fff", width: 280 }} />
            </Field>
            <Field label={tx("Repository folder")} hint={tx("only for work on code: the run is a coding session in this checkout")}>
              <TextField size="small" fullWidth value={cfg.cwd || ""} placeholder="C:/work/census"
                onChange={(e) => set("cwd", e.target.value)} sx={{ bgcolor: "#fff" }} />
            </Field>
            {cur && <Button size="small" color="error" startIcon={<DeleteOutlineIcon sx={{ fontSize: 15 }} />}
              onClick={() => setConfirmDel(true)}>{tx("Delete workflow")}</Button>}
          </Box>
        </Box>
      </Box>
      {cur && <ConfirmDelete open={confirmDel} what={`the workflow "${cfg.title || cur.Address || "untitled"}"`}
        consequence={tx("It stops running and leaves the Workflows list. The tasks its runs opened stay.")}
        onClose={() => setConfirmDel(false)}
        onConfirm={async () => { await api.delete(`/api/sources/${cur.SourceId}`); await reload(); onBack(); }} />}
    </Box>
  );
}
