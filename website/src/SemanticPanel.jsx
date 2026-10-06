// What the assistant is allowed to state as fact about the company's own numbers.
//
// This company's Intacct is customised, so a query the AI writes itself is plausible and wrong.
// A metric here is a definition PLUS the numbers the owner already knew it had to match - and it
// is only "certified" while every one of them still reconciles. This panel is the visible side of
// that: one row per number, its state, and the known figures it was proved against. Everything is
// also reachable from the chat, which is where a definition normally gets worked out; this is
// where you check what the assistant now believes.
import React, { useCallback, useEffect, useState } from "react";
import { Alert, Box, Button, Chip, CircularProgress, TextField, Typography } from "@mui/material";
import CheckCircleIcon from "@mui/icons-material/CheckCircle";
import ErrorOutlineIcon from "@mui/icons-material/ErrorOutline";
import ScienceIcon from "@mui/icons-material/Science";
import api from "./api";
import { BORDER, DIM, FAINT, INK, PANEL, PANEL2, mono } from "./theme.jsx";

const STATE = {
  verified: { label: "certified", c: { bg: "#dfeade", fg: "#47654a", bd: "#c8d9c7" } },
  draft: { label: "being proved", c: { bg: "#eae4d8", fg: "#55697a", bd: "#d8cfbe" } },
  broken: { label: "stopped matching", c: { bg: "#f5dfe1", fg: "#8a3646", bd: "#e6c6ca" } },
};
const stateOf = (m) => STATE[m.Status] || STATE.draft;
const StatusIcon = ({ status, sx }) => (status === "verified" ? <CheckCircleIcon sx={sx} />
  : status === "broken" ? <ErrorOutlineIcon sx={sx} /> : <ScienceIcon sx={sx} />);
const num = (v) => (v === null || v === undefined || v === "" ? "—"
  : Number(v).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }));

// The known number and what the definition actually returned, side by side - the only thing that
// decides whether the metric may answer. A row that stopped matching says by how much, because
// "off by exactly the rent" is how you find which accounts the definition is missing.
const Fixture = ({ f, onDrop }) => {
  const off = f.LastGot === null || f.LastGot === undefined ? null : Number(f.LastGot) - Number(f.Expected);
  const bad = f.LastPass === 0;
  return (
    <Box component="tr" sx={{ borderTop: `1px solid ${BORDER}` }}>
      <Box component="td" sx={{ py: 0.4, pr: 1 }}><Typography variant="caption" sx={{ ...mono, color: INK }}>{f.Scope || "—"}</Typography></Box>
      <Box component="td" sx={{ py: 0.4, pr: 1 }}><Typography variant="caption" sx={{ ...mono, color: DIM }}>{f.Period || "—"}</Typography></Box>
      <Box component="td" sx={{ py: 0.4, pr: 1, textAlign: "right" }}><Typography variant="caption" sx={{ ...mono, color: INK }}>{num(f.Expected)}</Typography></Box>
      <Box component="td" sx={{ py: 0.4, pr: 1, textAlign: "right" }}>
        <Typography variant="caption" sx={{ ...mono, color: bad ? "#8a3646" : f.LastPass === 1 ? "#47654a" : FAINT }}>
          {f.LastError ? "error" : num(f.LastGot)}
        </Typography>
      </Box>
      <Box component="td" sx={{ py: 0.4, pr: 1, textAlign: "right" }}>
        <Typography variant="caption" sx={{ ...mono, fontSize: 10, color: bad ? "#8a3646" : FAINT }}
          title={f.LastError || ""}>{off === null ? "" : off === 0 ? "exact" : num(off)}</Typography>
      </Box>
      <Box component="td" sx={{ py: 0.4 }}><Typography variant="caption" sx={{ color: FAINT, fontSize: 10 }} noWrap>{f.Source || ""}</Typography></Box>
      <Box component="td" sx={{ py: 0.4, textAlign: "right" }}>
        <Typography variant="caption" onClick={() => onDrop(f.FixtureId)}
          sx={{ color: FAINT, fontSize: 10, cursor: "pointer", "&:hover": { color: "#8a3646" } }}>remove</Typography>
      </Box>
    </Box>
  );
};

const Metric = ({ m, minFixtures, open, onOpen, onChanged }) => {
  const s = stateOf(m);
  const [busy, setBusy] = useState("");
  const [err, setErr] = useState("");
  const [tried, setTried] = useState(null);
  const [t, setT] = useState({ scope: "", period: "" });
  const [nf, setNf] = useState({ Scope: "", Period: "", Expected: "", Source: "" });
  const fixtures = m.fixtures || [];
  const passing = fixtures.filter((f) => f.LastPass === 1).length;

  const run = async (what, fn) => {
    setBusy(what); setErr("");
    try { await fn(); } catch (e) { setErr(e?.response?.data?.detail || `could not ${what}`); }
    setBusy("");
  };
  const check = () => run("check it", async () => { await api.post(`/api/semantic/metrics/${m.MetricId}/check`); onChanged(); });
  const tryIt = () => run("run it", async () => {
    setTried(null);
    const { data } = await api.post(`/api/semantic/metrics/${m.MetricId}/try`, { scope: t.scope || null, period: t.period || null });
    setTried(data);
  });
  const addFixture = () => run("save that number", async () => {
    await api.post(`/api/semantic/metrics/${m.MetricId}/fixtures`, { ...nf, Expected: Number(nf.Expected) });
    setNf({ Scope: "", Period: "", Expected: "", Source: "" }); onChanged();
  });
  const dropFixture = (fid) => run("remove it", async () => { await api.delete(`/api/semantic/fixtures/${fid}`); onChanged(); });

  return (
    <Box sx={{ border: `1px solid ${open ? s.c.bd : BORDER}`, borderRadius: 1.5, bgcolor: open ? s.c.bg : PANEL, mb: 0.6 }}>
      <Box onClick={onOpen} sx={{ display: "flex", alignItems: "center", gap: 0.75, px: 1.1, py: 0.7, cursor: "pointer" }}>
        <StatusIcon status={m.Status} sx={{ fontSize: 15, color: s.c.fg }} />
        <Typography sx={{ ...mono, fontSize: 11.5, fontWeight: 600, color: INK }}>{m.Name}</Typography>
        <Typography variant="caption" sx={{ color: DIM, flex: 1, minWidth: 0 }} noWrap>{m.Label || m.Definition || ""}</Typography>
        <Chip size="small" label={s.label} sx={{ height: 16, fontSize: 9, bgcolor: s.c.bg, color: s.c.fg, border: `1px solid ${s.c.bd}` }} />
        <Typography variant="caption" sx={{ ...mono, fontSize: 10, color: FAINT, whiteSpace: "nowrap" }}>
          {passing}/{fixtures.length} match{fixtures.length < minFixtures ? ` · needs ${minFixtures}` : ""}
        </Typography>
      </Box>
      {open && (
        <Box sx={{ px: 1.1, pb: 1, display: "flex", flexDirection: "column", gap: 0.9 }}>
          {m.Definition && <Typography variant="body2" sx={{ color: INK, fontSize: 12, lineHeight: 1.5 }}>{m.Definition}</Typography>}
          {m.Grain && <Typography variant="caption" sx={{ color: FAINT }}>One row is: {m.Grain}</Typography>}
          {m.LastCheckNote && <Typography variant="caption" sx={{ color: m.Status === "verified" ? "#47654a" : "#8a3646" }}>{m.LastCheckNote}</Typography>}

          {/* the proof, or the absence of it */}
          <Box>
            <Typography sx={{ ...mono, fontSize: 9, letterSpacing: 1, color: "#6b5f45", fontWeight: 600, mb: 0.3 }}>
              KNOWN NUMBERS IT MUST MATCH
            </Typography>
            {fixtures.length ? (
              <Box component="table" sx={{ width: "100%", borderCollapse: "collapse" }}>
                <Box component="thead"><Box component="tr">
                  {["scope", "period", "known", "got", "off", "where from", ""].map((h, i) => (
                    <Box component="th" key={h + i} sx={{ textAlign: i >= 2 && i <= 4 ? "right" : "left", pb: 0.3 }}>
                      <Typography variant="caption" sx={{ ...mono, fontSize: 9, color: FAINT }}>{h}</Typography>
                    </Box>))}
                </Box></Box>
                <Box component="tbody">{fixtures.map((f) => <Fixture key={f.FixtureId} f={f} onDrop={dropFixture} />)}</Box>
              </Box>
            ) : (
              <Typography variant="caption" sx={{ color: FAINT }}>
                None yet — it cannot be trusted until it matches numbers you already know are right.
              </Typography>
            )}
            <Box sx={{ display: "flex", gap: 0.5, mt: 0.6, flexWrap: "wrap", alignItems: "center" }}>
              {[["Scope", "what names one row", 130], ["Period", "2026-07", 90], ["Expected", "the right number", 130], ["Source", "where it came from", 150]].map(([k, ph, w]) => (
                <TextField key={k} size="small" placeholder={ph} value={nf[k]} onChange={(e) => setNf({ ...nf, [k]: e.target.value })}
                  sx={{ width: w, bgcolor: PANEL2, "& input": { fontSize: 11, py: 0.5 } }} />
              ))}
              <Button size="small" disabled={!!busy || !nf.Expected} onClick={addFixture} sx={{ fontSize: 10.5 }}>add known number</Button>
            </Box>
          </Box>

          {/* try it without recording anything - the step where a definition gets fixed */}
          <Box sx={{ display: "flex", gap: 0.5, alignItems: "center", flexWrap: "wrap" }}>
            <TextField size="small" placeholder="scope" value={t.scope} onChange={(e) => setT({ ...t, scope: e.target.value })}
              sx={{ width: 110, bgcolor: PANEL2, "& input": { fontSize: 11, py: 0.5 } }} />
            <TextField size="small" placeholder="2026-07" value={t.period} onChange={(e) => setT({ ...t, period: e.target.value })}
              sx={{ width: 90, bgcolor: PANEL2, "& input": { fontSize: 11, py: 0.5 } }} />
            <Button size="small" disabled={!!busy} onClick={tryIt} sx={{ fontSize: 10.5 }}>
              {busy === "run it" ? "running…" : "run it once"}
            </Button>
            {tried && <Typography variant="caption" sx={{ ...mono, color: INK }}>
              {num(tried.value)} <Typography component="span" variant="caption" sx={{ color: FAINT }}>from {tried.rows} row(s), {tried.ms}ms</Typography>
            </Typography>}
            <Box sx={{ flex: 1 }} />
            <Button size="small" variant="contained" disableElevation disabled={!!busy} onClick={check}
              sx={{ fontSize: 10.5, bgcolor: "#6f8a6e", "&:hover": { bgcolor: "#5b7259" } }}>
              {busy === "check it" ? "checking…" : "check every known number"}
            </Button>
          </Box>

          <Box component="pre" sx={{ ...mono, fontSize: 10, color: DIM, bgcolor: PANEL2, border: `1px solid ${BORDER}`,
            borderRadius: 1, p: 0.75, m: 0, overflowX: "auto", maxHeight: 160 }}>
            {JSON.stringify(m.Spec || {}, null, 2)}
          </Box>
          {m.Notes && <Typography variant="caption" sx={{ color: DIM, whiteSpace: "pre-wrap" }}>{m.Notes}</Typography>}
          {m.Skill && <Typography variant="caption" sx={{ color: FAINT }}>Frozen as skill <b style={mono}>{m.Skill}</b> — every later run uses it.</Typography>}
          {err && <Typography variant="caption" sx={{ color: "#8a3646" }}>{err}</Typography>}
        </Box>
      )}
    </Box>
  );
};

export default function SemanticPanel() {
  const [rows, setRows] = useState(null);
  const [minFixtures, setMin] = useState(3);
  const [open, setOpen] = useState(null);
  const [err, setErr] = useState("");
  const load = useCallback(() => api.get("/api/semantic/metrics")
    .then(({ data }) => { setRows(data.data || []); setMin(data.minFixtures || 3); })
    .catch((e) => { setErr(e?.response?.data?.detail || "could not read the definitions"); setRows([]); }), []);
  useEffect(() => { load(); }, [load]);

  if (rows === null) return <Box sx={{ p: 3, display: "grid", placeItems: "center" }}><CircularProgress size={18} /></Box>;
  const by = (s) => rows.filter((m) => m.Status === s).length;
  return (
    <Box sx={{ p: 1.25, overflowY: "auto", height: "100%" }}>
      <Typography variant="caption" sx={{ color: DIM, display: "block", mb: 1, lineHeight: 1.5 }}>
        What the assistant may state as fact about our own numbers. Every system is configured differently,
        so a query written from the API alone is plausible and wrong — a definition here is only certified
        while it still matches {minFixtures} or more numbers you already knew were right. Work them out in the
        chat; this is where you see what it now believes.
      </Typography>
      {err && <Alert severity="error" sx={{ mb: 1, py: 0 }}>{err}</Alert>}
      {!rows.length ? (
        <Box sx={{ border: `1px dashed ${BORDER}`, borderRadius: 1.5, p: 2, textAlign: "center" }}>
          <Typography variant="body2" sx={{ color: DIM }}>No number has been proved yet.</Typography>
          <Typography variant="caption" sx={{ color: FAINT, display: "block", mt: 0.5 }}>
            Ask the assistant for one in the chat — name a figure you already report on and the period you
            want it for. It will look at the real schema, propose a definition, and ask you for a few cases
            whose numbers you already know. Once they reconcile, the metric appears here and every later
            run uses it.
          </Typography>
        </Box>
      ) : (
        <>
          <Typography sx={{ ...mono, fontSize: 10, color: "#6b5f45", fontWeight: 600, mb: 0.6 }}>
            {by("verified")} CERTIFIED · {by("draft")} BEING PROVED{by("broken") ? ` · ${by("broken")} STOPPED MATCHING` : ""}
          </Typography>
          {rows.map((m) => (
            <Metric key={m.MetricId} m={m} minFixtures={minFixtures} open={open === m.MetricId}
              onOpen={() => setOpen(open === m.MetricId ? null : m.MetricId)} onChanged={load} />
          ))}
        </>
      )}
    </Box>
  );
}
