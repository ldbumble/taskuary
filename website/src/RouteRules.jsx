// WHICH AI DOES EACH JOB (the router, 2026-10-25 - the mode line, the rules as sentences, the cap line and Recent routes, all
// owner-approved). Fixed is the cards, exactly as before, and a fresh install's answer. Auto lets the rules below pick the quick,
// standard or strong model by the job and how hard triage judged the work; each card stays its job's standard model. A rule is
// built from dropdowns over the values the router knows, never a typed condition, and its sentence is made from what it does.
import React, { useCallback, useEffect, useState } from "react";
import { Alert, Box, Button, MenuItem, Select, Switch, TextField, Typography } from "@mui/material";
import api from "./api";
import { BORDER, DIM, FAINT, INK, card, mono } from "./theme.jsx";

const JOB = { triage: "triage", draft: "drafts", summary: "summaries", advisor: "the Advisor", memory: "memory", rank: "ranking",
  general: "general work", coding: "coding", judge: "judgements" };
const USE = { light: "the quick model", standard: "the card's own model", strong: "the strong model" };
const sel = { fontSize: 12.5, bgcolor: "#fff", minWidth: 150 };
const err = (e, d) => e?.response?.data?.detail || e?.message || d;

export function RouteRules() {
  const [p, setP] = useState(null);
  const [say, setSay] = useState("");
  const [add, setAdd] = useState({ job: "draft", difficulty: "hard", tier: "strong" });
  const [cap, setCap] = useState("");
  const load = useCallback(() => api.get("/api/ai/route_rules").then((r) => { setP(r.data); setCap(String(r.data.cap ?? "")); })
    // a server older than this page (or the public demo) has no router to show: the cards alone are the whole truth there
    .catch((e) => (e?.response?.status === 404 ? setP(false) : setSay(err(e, "could not read how jobs are routed")))), []);
  useEffect(() => { load(); }, [load]);
  const save = async (patch) => {
    try { setSay(""); const r = await api.post("/api/ai/route_rules", patch); setP(r.data); setCap(String(r.data.cap ?? "")); }
    catch (e) { setSay(err(e, "could not save that")); }
  };
  if (p === false) return null;
  if (!p) return say ? <Alert severity="warning" sx={{ mb: 1.5, fontSize: 12.5 }}>{say}</Alert> : null;
  const auto = p.mode === "auto";
  const rules = p.rules || [];
  const put = (next) => save({ rules: next.map(({ sentence, ...r }) => r) });
  const addRule = () => {
    const id = `${add.difficulty === "any" ? "" : `${add.difficulty}-`}${add.job}-${add.tier}`;
    const when = { job: [add.job], ...(add.difficulty === "any" ? {} : { difficulty: [add.difficulty] }) };
    // a new rule goes FIRST: the first rule that sets a tier wins, and the owner's own word is the one meant to win
    put([{ id, when, use: { tier: add.tier }, on: true, by: "owner" }, ...rules.filter((r) => r.id !== id)]);
  };
  return (
    <Box data-tq-knob="ai_route_mode ai_route_strong_cap" data-tq-route-rules="" sx={{ ...card, p: 2, mb: 1.5, bgcolor: "#fff" }}>
      <Box sx={{ display: "flex", alignItems: "center", gap: 1.5, flexWrap: "wrap" }}>
        <Typography sx={{ color: INK, fontWeight: 600, fontSize: 14 }}>Which AI does each job</Typography>
        <Select size="small" value={p.mode} onChange={(e) => save({ mode: e.target.value })} sx={sel} data-tq-route-mode="">
          <MenuItem value="fixed" sx={{ fontSize: 12.5 }}>Fixed - the cards below</MenuItem>
          <MenuItem value="auto" sx={{ fontSize: 12.5 }}>Auto - by how hard the work is</MenuItem>
        </Select>
      </Box>
      <Typography variant="caption" sx={{ color: FAINT, display: "block", mt: 0.5 }}>
        {auto ? "Each card below is its job's standard model; these rules say when the quick or the strong model runs instead. A brain whose strong model box is blank never steps up, and an AI you pick for something always wins."
          : "Every job runs exactly as its card says. Auto picks a quick, standard or strong model by the job and how hard triage judged the work."}
      </Typography>
      {say && <Alert severity="warning" sx={{ mt: 1, fontSize: 12.5 }}>{say}</Alert>}
      {p.warning && <Alert severity="warning" sx={{ mt: 1, fontSize: 12.5 }} data-tq-route-warning="">{p.warning}</Alert>}
      {auto && (
        <Box sx={{ mt: 1.25, pt: 1, borderTop: `1px solid ${BORDER}` }}>
          {rules.map((r) => (
            <Box key={r.id} data-tq-route-rule={r.id} sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
              <Switch size="small" checked={!!r.on} onChange={() => put(rules.map((x) => (x.id === r.id ? { ...x, on: !x.on } : x)))}
                inputProps={{ "aria-label": r.sentence }} />
              <Typography sx={{ fontSize: 12.5, color: r.on ? INK : FAINT, flex: 1 }}>{r.sentence}</Typography>
              {r.by === "owner" && (
                <Typography component="button" type="button" variant="caption" onClick={() => put(rules.filter((x) => x.id !== r.id))}
                  sx={{ border: 0, background: "none", p: 0, font: "inherit", color: "#55697a", cursor: "pointer", "&:hover": { textDecoration: "underline" } }}>
                  remove</Typography>
              )}
            </Box>
          ))}
          <Box sx={{ display: "flex", alignItems: "center", gap: 1, flexWrap: "wrap", mt: 1 }} data-tq-route-add="">
            <Select size="small" value={add.difficulty} onChange={(e) => setAdd({ ...add, difficulty: e.target.value })} sx={{ ...sel, minWidth: 110 }}>
              <MenuItem value="any" sx={{ fontSize: 12.5 }}>Any</MenuItem>
              {(p.difficulties || []).map((d) => <MenuItem key={d} value={d} sx={{ fontSize: 12.5 }}>{d[0].toUpperCase() + d.slice(1)}</MenuItem>)}
            </Select>
            <Select size="small" value={add.job} onChange={(e) => setAdd({ ...add, job: e.target.value })} sx={sel}>
              {Object.entries(JOB).map(([k, v]) => <MenuItem key={k} value={k} sx={{ fontSize: 12.5 }}>{v}</MenuItem>)}
            </Select>
            <Typography sx={{ fontSize: 12.5, color: DIM }}>-&gt;</Typography>
            <Select size="small" value={add.tier} onChange={(e) => setAdd({ ...add, tier: e.target.value })} sx={sel}>
              {Object.entries(USE).map(([k, v]) => <MenuItem key={k} value={k} sx={{ fontSize: 12.5 }}>{v}</MenuItem>)}
            </Select>
            <Button size="small" variant="outlined" onClick={addRule} sx={{ fontSize: 12.5, textTransform: "none" }}>Add the rule</Button>
          </Box>
          <Box sx={{ display: "flex", alignItems: "center", gap: 1, flexWrap: "wrap", mt: 1.25 }}>
            <Typography sx={{ fontSize: 12.5, color: DIM }}>At most</Typography>
            <TextField size="small" value={cap} placeholder="no cap" onChange={(e) => setCap(e.target.value)}
              onBlur={() => cap !== String(p.cap ?? "") && save({ cap })} inputProps={{ "aria-label": "strong calls a day", "data-tq-route-cap": "" }}
              sx={{ width: 90, bgcolor: "#fff" }} />
            <Typography sx={{ fontSize: 12.5, color: DIM }}>strong calls a day; used today: {p.used_today}</Typography>
          </Box>
        </Box>
      )}
    </Box>
  );
}

// RECENT ROUTES: the last twenty AI calls, one line each - which job, which task, which tier on which brain, and why. Read-only.
export function RecentRoutes() {
  const [rows, setRows] = useState(null);
  useEffect(() => { api.get("/api/ai/routes").then((r) => setRows(r.data.routes || [])).catch(() => setRows([])); }, []);
  if (!rows?.length) return null;
  return (
    <Box data-tq-recent-routes="" sx={{ ...card, p: 2, mb: 1.5, bgcolor: "#fff" }}>
      <Typography variant="caption" sx={{ color: FAINT, fontWeight: 600, display: "block", mb: 0.5 }}>RECENT ROUTES</Typography>
      {rows.map((r) => (
        <Typography key={r.Id} sx={{ ...mono, fontSize: 11.5, color: INK, whiteSpace: "pre-wrap" }} title={r.Outcome && r.Outcome !== "ok" ? r.Outcome : undefined}>
          {[r.Job, r.ref, `${r.Tier} -> ${r.brain}${r.Model ? `, ${r.Model}` : ""}`].filter(Boolean).join(" · ")}
          <Typography component="span" sx={{ ...mono, fontSize: 11.5, color: FAINT }}> · {r.Why}</Typography>
        </Typography>
      ))}
    </Box>
  );
}
