// A WORKFLOW AS STEPS, top to bottom (taskuary/flow.py; the owner, 2026-10-18: "make the setup like a step by step thing like n8n
// style ... that you can see the deterministic steps so that part is repeatable"). Each step is a card on one rail: what kind it
// is, its own config, and Test this step - which runs it for real (reads, AI) or says what it would do (anything that writes),
// against the outputs of the steps above. RunSteps.jsx is the same list read back from a run.
import React, { useRef, useState } from "react";
import { Alert, Box, Button, Chip, CircularProgress, IconButton, Menu, MenuItem, Select, TextField, Typography } from "@mui/material";
import AddIcon from "@mui/icons-material/Add";
import ArrowUpwardIcon from "@mui/icons-material/ArrowUpward";
import ArrowDownwardIcon from "@mui/icons-material/ArrowDownward";
import CloseIcon from "@mui/icons-material/Close";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import PlayArrowIcon from "@mui/icons-material/PlayArrow";
import api from "./api";
import { ALERT, ALERT_INK, BORDER, DIM, FAINT, INK, PANEL, PANEL2, mono } from "./theme.jsx";
import { SourceCard } from "./ReportsView.jsx";
import { Dot, StepResult } from "./RunSteps.jsx";
import { KIND_WORDS, ONLY_IF, badRefs, canAddAgent, insertStep, missingIn, moveStep, recHead, removeStep, runWords, testWords, toSaved,
  tokenInQuery, tokensFor } from "./workflowFlow.js";

const NOT_A_STEP = new Set(["agent", "assistant", "zoho_monthly_invoices"]);
const KIND_TINT = { source: "#e6ebef", ai: "#efe9f3", task: "#e5ece2", draft: "#f3ede2", agent: "#efece6" };
const field = { bgcolor: "#fff" };

const KindChip = ({ kind }) => <Box component="span" sx={{ px: 0.75, py: 0.1, borderRadius: 1, fontSize: 10.5, fontWeight: 600, color: DIM,
  bgcolor: KIND_TINT[kind] || PANEL2, whiteSpace: "nowrap", flexShrink: 0 }}>{KIND_WORDS[kind] || kind}</Box>;

// a text box with "Insert output of" - the earlier steps and what each one can hand on, put in where the cursor was
function TokenField({ flow, index, value, onChange, label, placeholder, multiline, minRows, monospace }) {
  const [at, setAt] = useState(null);
  const ref = useRef(null);
  const sel = useRef(null);
  const groups = tokensFor(flow, index).filter((g) => g.tokens.length);
  const put = (tok) => {
    const v = String(value || ""), [a, b] = sel.current || [v.length, v.length];
    onChange(v.slice(0, a) + tok + v.slice(b)); setAt(null);
  };
  return (
    <Box sx={{ position: "relative" }}>
      <TextField size="small" fullWidth label={label} placeholder={placeholder} value={value || ""} multiline={multiline} minRows={minRows}
        inputRef={ref} sx={field} inputProps={monospace ? { style: { fontFamily: "Consolas, monospace", fontSize: 11.5 } } : undefined}
        onSelect={(e) => { sel.current = [e.target.selectionStart, e.target.selectionEnd]; }}
        onChange={(e) => onChange(e.target.value)} />
      {!!groups.length && <>
        <Typography component="button" type="button" onClick={(e) => setAt(e.currentTarget)}
          sx={{ border: 0, bgcolor: "transparent", p: 0, mt: 0.35, cursor: "pointer", color: "#55697a", fontSize: 11.5, fontWeight: 600,
            "&:hover": { textDecoration: "underline" } }}>Insert output of…</Typography>
        <Menu anchorEl={at} open={!!at} onClose={() => setAt(null)}>
          {groups.flatMap((g) => [
            <MenuItem key={`h-${g.id}`} disabled sx={{ fontSize: 11, opacity: "1 !important", color: FAINT, fontWeight: 600, minHeight: 0, py: 0.5 }}>
              {g.n}. {g.label}</MenuItem>,
            ...g.tokens.map(([tok, says]) => <MenuItem key={tok} onClick={() => put(tok)} sx={{ fontSize: 12.5, pl: 3, gap: 1 }}>
              {says}<Box component="span" sx={{ ...mono, fontSize: 11, color: FAINT, ml: "auto" }}>{tok}</Box></MenuItem>),
          ])}
        </Menu>
      </>}
    </Box>
  );
}

function OnlyIf({ flow, index, step, onChange }) {
  const above = flow.slice(0, index);
  if (!above.length) return null;
  const oi = step.only_if || null;
  return (
    <Box sx={{ display: "flex", alignItems: "center", gap: 1, flexWrap: "wrap" }}>
      <Typography variant="caption" sx={{ color: DIM, fontWeight: 600 }}>Only if</Typography>
      <Select size="small" displayEmpty value={oi?.step || ""} sx={{ ...field, fontSize: 12.5, minWidth: 180 }}
        onChange={(e) => onChange({ only_if: e.target.value ? { step: e.target.value, is: oi?.is || "yes" } : undefined })}>
        <MenuItem value="" sx={{ fontSize: 12.5 }}>always runs</MenuItem>
        {above.map((s, n) => <MenuItem key={s.id} value={s.id} sx={{ fontSize: 12.5 }}>{n + 1}. {s.label || KIND_WORDS[s.kind]}</MenuItem>)}
      </Select>
      {oi && <Select size="small" value={oi.is} sx={{ ...field, fontSize: 12.5 }} onChange={(e) => onChange({ only_if: { ...oi, is: e.target.value } })}>
        {ONLY_IF.map(([v, w]) => <MenuItem key={v} value={v} sx={{ fontSize: 12.5 }}>{w}</MenuItem>)}
      </Select>}
    </Box>
  );
}

function KindConfig({ step, flow, index, set, typeOptions, connectors, agents, test }) {
  const tf = (k, label, ph, more = {}) => <TokenField flow={flow} index={index} value={step[k]} label={label} placeholder={ph}
    onChange={(v) => set({ [k]: v })} {...more} />;
  if (step.kind === "source") return (
    <>
      <SourceCard bare src={step} index={index} count={1} removable={false} connectors={connectors}
        typeOptions={typeOptions} onChange={set} test={test}
        onRetype={(t) => set({ type: t }, true)} onFill={(one) => set(one)} onCopy={() => {}} onRemove={() => {}} />
      {tokenInQuery(step) && <Alert severity="warning" sx={{ fontSize: 12, py: 0 }}>
        An earlier step's output is pasted into this query as text. Check what it can contain before this runs on a schedule.</Alert>}
    </>
  );
  if (step.kind === "ai") return (
    <>
      {tf("prompt", "What should it judge, summarize or draft?", "Are any of these real duplicates, rather than a reissued invoice?", { multiline: true, minRows: 3 })}
      <Box sx={{ display: "flex", gap: 1, alignItems: "center", flexWrap: "wrap" }}>
        <Typography variant="caption" sx={{ color: DIM, fontWeight: 600 }}>It answers</Typography>
        <Select size="small" value={step.output || "text"} sx={{ ...field, fontSize: 12.5 }} onChange={(e) => set({ output: e.target.value })}>
          <MenuItem value="yes_no" sx={{ fontSize: 12.5 }}>yes or no, and why</MenuItem>
          <MenuItem value="fields" sx={{ fontSize: 12.5 }}>named fields</MenuItem>
          <MenuItem value="text" sx={{ fontSize: 12.5 }}>text</MenuItem>
        </Select>
        {step.output === "fields" && <TextField size="small" label="fields, comma separated" value={(step.fields || []).join(", ")} sx={{ ...field, minWidth: 220 }}
          onChange={(e) => set({ fields: e.target.value.split(",").map((x) => x.trim()).filter(Boolean) })} />}
      </Box>
      {test}
    </>
  );
  if (step.kind === "task") return (
    <>
      {tf("title", "Task title", "Duplicate bill: {{s1.head}}")}
      {tf("summary", "What the task says", "The pairs, and what to do about them", { multiline: true, minRows: 2 })}
      <Select size="small" displayEmpty value={step.assignee || ""} sx={{ ...field, fontSize: 12.5, maxWidth: 260 }} onChange={(e) => set({ assignee: e.target.value })}>
        <MenuItem value="" sx={{ fontSize: 12.5 }}>for you</MenuItem>
        {agents.map((a) => <MenuItem key={a} value={a} sx={{ fontSize: 12.5 }}>for the {a} agent</MenuItem>)}
      </Select>
      {test}
    </>
  );
  if (step.kind === "draft") return (
    <>
      {tf("to", "To", "gail@northwind.example")}
      {tf("subject", "Subject (optional)", "Duplicate bills this week")}
      {tf("about", "What it is about - the AI writes the email from this; it waits for your approval", "The pairs found: {{s1}}", { multiline: true, minRows: 2 })}
      {test}
    </>
  );
  return (
    <>
      {tf("prompt", "What the agent does with what the steps above found", "Open the vendor portal and void the second copy of each pair.", { multiline: true, minRows: 3 })}
      <Typography variant="caption" sx={{ color: FAINT }}>Always the last step. It is handed every step's output, and Ask me before and Done when below.</Typography>
      {test}
    </>
  );
}

function AddStep({ flow, at, onAdd, last }) {
  const [el, setEl] = useState(null);
  const kinds = Object.keys(KIND_WORDS).filter((k) => k !== "agent" || (last && canAddAgent(flow)));
  return (
    <Box sx={{ display: "flex", alignItems: "center", pl: 1.25, minHeight: last ? 36 : 22 }}>
      {last ? <Button size="small" startIcon={<AddIcon sx={{ fontSize: 15 }} />} onClick={(e) => setEl(e.currentTarget)}
        sx={{ ml: -0.5, fontSize: 12.5 }}>Add step</Button>
        : <IconButton size="small" aria-label="Add a step here" onClick={(e) => setEl(e.currentTarget)}
          sx={{ ml: -1.05, width: 22, height: 22, bgcolor: PANEL, border: `1px solid ${BORDER}`, opacity: 0.55, "&:hover": { opacity: 1, bgcolor: PANEL } }}>
          <AddIcon sx={{ fontSize: 14 }} /></IconButton>}
      <Menu anchorEl={el} open={!!el} onClose={() => setEl(null)}>
        {kinds.map((k) => <MenuItem key={k} sx={{ fontSize: 13, gap: 1 }} onClick={() => { setEl(null); onAdd(at, k); }}><KindChip kind={k} />
          <Typography variant="caption" sx={{ color: FAINT }}>{{ source: "a query, a call, a file - the same every run", ai: "one model call: yes/no, fields or text",
            task: "open a task for you or an agent", draft: "an email that waits for your approval", agent: "work that needs an agent's hands" }[k]}</Typography>
        </MenuItem>)}
      </Menu>
    </Box>
  );
}

export default function WorkflowSteps({ flow, setFlow, outputs, setOutputs, connectors, types, agents, title, sourceId, inputs, changed }) {
  const [open, setOpen] = useState(() => new Set(flow.length <= 3 ? flow.map((s) => s.id) : []));
  const [testing, setTesting] = useState("");
  const [tested, setTested] = useState(false);       // a test has run here - the outputs below are a test's, not the last run's
  const typeOptions = (types || []).filter((t) => t.status === "builtin" && !NOT_A_STEP.has(t.type));
  const toggle = (id) => setOpen((o) => { const n = new Set(o); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const setStep = (i, patch, replace) => setFlow((f) => f.map((s, n) => n !== i ? s
    : replace ? { id: s.id, kind: s.kind, label: s.label, ...(s.only_if ? { only_if: s.only_if } : {}), ...patch } : { ...s, ...patch }));
  const add = (at, kind) => { const next = insertStep(flow, at, kind); const made = next.find((s) => !flow.some((x) => x.id === s.id)); setFlow(next); if (made) setOpen((o) => new Set([...o, made.id])); };
  // one step, against the outputs the page holds for the steps above it - never re-running their writes
  const testOne = async (i, outs = outputs) => {
    setTesting(flow[i].id);
    try {
      const { data } = await api.post("/api/workflows/step-test", { flow: toSaved(flow), index: i, outputs: outs, inputs, title, source_id: sourceId });
      const next = { ...outs, [flow[i].id]: data };
      setOutputs(next); setTested(true); return next;
    } catch (e) {
      const next = { ...outs, [flow[i].id]: { id: flow[i].id, status: "failed", error: e?.response?.data?.detail || "the test could not run" } };
      setOutputs(next); return next;
    } finally { setTesting(""); }
  };
  const testAll = async () => {
    let outs = { ...outputs };
    for (let i = 0; i < flow.length; i++) {
      outs = await testOne(i, outs);
      if (["failed", "waiting"].includes(outs[flow[i].id]?.status)) break;
    }
  };
  const ran = flow.filter((s) => outputs[s.id]);
  return (
    <Box data-tq-flow="">
      <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 1, flexWrap: "wrap" }}>
        <Typography variant="caption" sx={{ color: FAINT, flex: 1, minWidth: 220 }}>
          Code runs each step the same way every time; a model runs only at the AI steps.{" "}
          {!ran.length ? "" : tested ? testWords(ran.map((s) => outputs[s.id])) : `Last run: ${runWords(ran.map((s) => outputs[s.id]), true)}.`}
        </Typography>
        {!!flow.length && <Button size="small" variant="outlined" disabled={!!testing} onClick={testAll}
          startIcon={testing ? <CircularProgress size={12} /> : <PlayArrowIcon sx={{ fontSize: 15 }} />}>Test every step</Button>}
      </Box>
      {flow.map((s, i) => {
        const rec = outputs[s.id], isOpen = open.has(s.id), bad = badRefs(flow, i), miss = missingIn(s), mark = changed?.[s.id];
        const test = (
          <Box sx={{ display: "flex", flexDirection: "column", gap: 0.75 }}>
            <Button size="small" variant="outlined" disabled={!!testing} onClick={() => testOne(i)} sx={{ alignSelf: "flex-start", fontSize: 12 }}
              startIcon={testing === s.id ? <CircularProgress size={12} /> : <PlayArrowIcon sx={{ fontSize: 14 }} />}>
              {testing === s.id ? "Testing…" : "Test this step"}</Button>
            <StepResult rec={rec} />
          </Box>
        );
        return (
          <React.Fragment key={s.id}>
            {i > 0 && <AddStep flow={flow} at={i} onAdd={add} />}
            <Box sx={{ display: "flex", gap: 1.25 }}>
              {/* the rail: one number per step, joined top to bottom */}
              <Box sx={{ display: "flex", flexDirection: "column", alignItems: "center", width: 22, flexShrink: 0 }}>
                <Box sx={{ width: 22, height: 22, borderRadius: "50%", display: "grid", placeItems: "center", fontSize: 11, fontWeight: 700,
                  color: rec?.status === "failed" ? "#fff" : DIM, bgcolor: rec?.status === "failed" ? ALERT : PANEL, border: `1px solid ${BORDER}`, mt: 1.1 }}>{i + 1}</Box>
                <Box sx={{ flex: 1, width: "1px", bgcolor: BORDER, minHeight: 8 }} />
              </Box>
              <Box data-tq-step={s.id} sx={{ flex: 1, minWidth: 0, bgcolor: PANEL, border: `1px solid ${mark ? "#a58bb5" : BORDER}`, borderRadius: 2,
                boxShadow: mark ? "0 0 0 2px #efe9f3" : "none" }}>
                <Box onClick={() => toggle(s.id)} sx={{ display: "flex", alignItems: "center", gap: 1, px: 1.25, py: 0.9, cursor: "pointer", minWidth: 0 }}>
                  <KindChip kind={s.kind} />
                  <Typography noWrap sx={{ color: INK, fontWeight: 600, fontSize: 13.5, flexShrink: 0, maxWidth: "42%" }}>{s.label || KIND_WORDS[s.kind]}</Typography>
                  {s.only_if && <Typography noWrap variant="caption" sx={{ color: FAINT, flexShrink: 2, minWidth: 0, display: { xs: "none", md: "block" } }}>
                    only if {flow.find((x) => x.id === s.only_if.step)?.label || s.only_if.step} {ONLY_IF.find(([v]) => v === s.only_if.is)?.[1]}</Typography>}
                  <Box sx={{ flex: 1 }} />
                  {rec && <Typography noWrap variant="caption" sx={{ color: rec.status === "failed" ? ALERT_INK : FAINT, display: { xs: "none", sm: "flex" }, alignItems: "center",
                    gap: 0.6, maxWidth: 280, minWidth: 0 }}><Dot status={rec.status} />
                    <Box component="span" sx={{ overflow: "hidden", textOverflow: "ellipsis" }}>{recHead(rec)}</Box></Typography>}
                  {(miss || bad.length) && !isOpen ? <Typography variant="caption" sx={{ color: ALERT_INK, whiteSpace: "nowrap" }}>needs {miss || "a fix"}</Typography> : null}
                  <Box onClick={(e) => e.stopPropagation()} sx={{ display: "flex", alignItems: "center" }}>
                    <IconButton size="small" aria-label="Move up" disabled={i === 0 || s.kind === "agent"} onClick={() => setFlow(moveStep(flow, i, -1))}><ArrowUpwardIcon sx={{ fontSize: 15 }} /></IconButton>
                    <IconButton size="small" aria-label="Move down" disabled={i === flow.length - 1 || flow[i + 1]?.kind === "agent" || s.kind === "agent"} onClick={() => setFlow(moveStep(flow, i, 1))}><ArrowDownwardIcon sx={{ fontSize: 15 }} /></IconButton>
                    <IconButton size="small" aria-label="Remove this step" onClick={() => setFlow(removeStep(flow, i))}><CloseIcon sx={{ fontSize: 15 }} /></IconButton>
                  </Box>
                  <ExpandMoreIcon sx={{ fontSize: 18, color: FAINT, transform: isOpen ? "rotate(180deg)" : "none", transition: "transform .15s" }} />
                </Box>
                {isOpen && <Box sx={{ px: 1.25, pb: 1.25, pt: 0.25, display: "flex", flexDirection: "column", gap: 1.1, borderTop: `1px solid ${BORDER}` }}>
                  {mark && <Typography variant="caption" sx={{ color: "#6a4f7a", fontWeight: 600, mt: 0.75 }}>
                    {mark.has("*") ? "Added by the repair" : `Changed by the repair: ${[...mark].join(", ")}`}</Typography>}
                  <TextField size="small" label="Step name" value={s.label || ""} placeholder={KIND_WORDS[s.kind]} sx={{ ...field, mt: mark ? 0 : 1 }}
                    onChange={(e) => setStep(i, { label: e.target.value })} />
                  <KindConfig step={s} flow={flow} index={i} set={(p, replace) => setStep(i, p, replace)} typeOptions={typeOptions}
                    connectors={connectors || []} agents={agents || []} test={test} />
                  {!!bad.length && <Typography variant="caption" sx={{ color: ALERT_INK }}>
                    {bad.map((r) => `{{${r}}}`).join(", ")} {bad.length === 1 ? "is not a step" : "are not steps"} above this one.</Typography>}
                  {s.kind !== "agent" && <OnlyIf flow={flow} index={i} step={s} onChange={(p) => setStep(i, p)} />}
                </Box>}
              </Box>
            </Box>
          </React.Fragment>
        );
      })}
      <AddStep flow={flow} at={flow.length} onAdd={add} last />
    </Box>
  );
}

