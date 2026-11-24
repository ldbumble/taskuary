// WHICH AI DOES WHAT (the owner, 2026-11-23): one page, each job once - sorting new mail, the task agents, the coding agent, the
// Assistant and where reports go - each with the AI that does it and the model it runs on, then the quick / normal / hard levels.
// Every card says what runs (the server's own answer, aidefaults) and writes each half back to the screen that owns it: nothing is
// stored twice. The page is the ONE place these are set - there are no fallback rows - so a failed read says why and tries again.
import React, { useCallback, useEffect, useRef, useState } from "react";
import { Alert, Box, Button, Checkbox, CircularProgress, FormControlLabel, MenuItem, Select, Typography } from "@mui/material";
import api from "./api";
import { ACCENT2, BORDER, DIM, FAINT, INK, card, mono } from "./theme.jsx";
import { RouteRules } from "./RouteRules.jsx";
import ModelPick from "./ModelPick.jsx";
import { repick, runsLine } from "./aiCards.js";

const link = { border: 0, background: "none", p: 0, font: "inherit", textAlign: "inherit", color: "var(--tq-link, #55697a)", cursor: "pointer",
  "&:hover": { textDecoration: "underline" } };
const head = { color: FAINT, display: "block", mb: 0.4, fontWeight: 600 };

// One job = one card. Colour only IDENTIFIES (the sage rule); the loudest line is RUNS - what will actually run.
const Slot = ({ slot, brains, agents, judgeOptions, onSave, onGo }) => {
  const isAgent = slot.key === "default_brain";
  // The judge is the one slot that may be pointed at a model which cannot write, so it is the one picker that shows them. Its own blank
  // row already means "the report's own AI", so the brains' blank entry is dropped rather than offered twice.
  const isJudge = slot.key === "judge_ai";
  const options = isAgent ? (agents || []).map((a) => (typeof a === "string" ? { value: a, label: a, ready: true } : a))
    : isJudge ? [...(judgeOptions || []), ...(brains || []).filter((o) => o.value)] : brains;
  const picked = options.find((o) => o.value === slot.value);
  const ai = picked?.label?.split(" · ")[0] || slot.runs?.brain || "";
  const model = (field, label, hint) => (
    <Box>
      <Typography variant="caption" sx={head}>{label}</Typography>
      <ModelPick value={slot[field] || ""} models={slot.choices} connector={slot.connector} ready={slot.ready} ai={ai}
        placeholder={hint} onSave={(v) => onSave({ [field]: v })} />
    </Box>
  );
  return (
    // ...the place a link to its settings lands (SettingsView's knob, by the same word list: `~=` matches any one of them)
    <Box data-tq-knob={(slot.settings || [slot.key]).join(" ")} data-tq-slot={slot.key} sx={{ ...card, p: 2, mb: 1.5, bgcolor: "var(--tq-panel, #fff)" }}>
      <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 0.25 }}>
        <Box sx={{ width: 7, height: 7, borderRadius: "50%", bgcolor: ACCENT2, flexShrink: 0 }} />
        <Typography sx={{ color: INK, fontWeight: 600, fontSize: 14 }}>{slot.label}</Typography>
      </Box>
      <Typography variant="body2" sx={{ color: DIM, mb: 0.25 }}>{slot.desc}</Typography>
      <Typography variant="caption" sx={{ color: FAINT, display: "block", mb: 1.5 }}>{slot.why}</Typography>

      <Box sx={{ display: "flex", gap: 1.5, flexWrap: "wrap", alignItems: "flex-start" }}>
        <Box>
          <Typography variant="caption" sx={head}>{isJudge ? "what decides" : "which AI"}</Typography>
          <Select size="small" displayEmpty value={picked ? slot.value : ""} data-tq-slot-brain={slot.key}
            onChange={(e) => onSave({ value: e.target.value })} MenuProps={{ PaperProps: { sx: { maxHeight: 340 } } }}
            sx={{ minWidth: 250, fontSize: 12.5, bgcolor: "var(--tq-panel, #fff)" }}>
            {options.map((o) => (
              <MenuItem key={o.value} value={o.value} disabled={o.ready === false} data-tq-brain-option={o.value} sx={{ fontSize: 12.5 }}
                onClick={() => repick(slot, o.value) && onSave({ value: o.value })}>
                {o.label}{o.ready === false ? " — no key saved" : ""}
              </MenuItem>
            ))}
            {!options.length && <MenuItem value="" disabled sx={{ fontSize: 12.5 }}>nothing connected yet</MenuItem>}
          </Select>
        </Box>
        {/* four yes/nos do not get better on a bigger model, and this slot owns no model setting to write one to */}
        {!isJudge && model("model", "model", slot.default_hint || "its own default")}
        {!isJudge && slot.strong_model !== undefined && model("strong_model", "strong model, for hard work", "none - hard work stays on the model")}
        {/* effort only where the AI can actually be told one - an empty list is an AI that takes none */}
        {!isJudge && !!(slot.efforts || []).length && (
          <Box>
            <Typography variant="caption" sx={head}>effort</Typography>
            <Select size="small" displayEmpty value={slot.effort || ""} onChange={(e) => onSave({ effort: e.target.value })}
              sx={{ minWidth: 150, fontSize: 12.5, bgcolor: "var(--tq-panel, #fff)" }}>
              <MenuItem value="" sx={{ fontSize: 12.5 }}>its own default</MenuItem>
              {slot.efforts.map((eff) => <MenuItem key={eff} value={eff} sx={{ fontSize: 12.5 }}>{eff}</MenuItem>)}
            </Select>
          </Box>
        )}
        {/* the owner's own mark, off by default and never set by code: once the data rule is on, sensitive work reaches only an AI marked here */}
        {!isJudge && slot.sensitive_ok !== undefined && (
          <FormControlLabel sx={{ ml: 0, mt: 2.25 }} control={<Checkbox size="small" checked={!!slot.sensitive_ok} data-tq-sensitive-ok=""
            onChange={(e) => onSave({ sensitive_ok: e.target.checked })} />}
            label={<Typography sx={{ fontSize: 12.5, color: DIM }}>may read sensitive data</Typography>} />
        )}
      </Box>

      <Box sx={{ mt: 1.5, pt: 1.25, borderTop: `1px solid ${BORDER}`, display: "flex", gap: 1, alignItems: "baseline", flexWrap: "wrap" }}>
        <Typography variant="caption" sx={{ color: FAINT, fontWeight: 600 }}>RUNS</Typography>
        <Typography sx={{ ...mono, fontSize: 12.5, color: INK, fontWeight: 600 }} data-tq-slot-runs="">
          {slot.runs ? runsLine(slot) : [picked?.label || "—", isJudge ? "" : slot.ready && (slot.model || slot.default_hint)].filter(Boolean).join(" · ")}
        </Typography>
        {/* whose choice it was (the owner, 2026-11-11: "never change from what's in settings") - said only where it was not theirs */}
        {slot.set_by && !slot.ask && <Typography variant="caption" data-tq-slot-set-by="" sx={{ color: FAINT }}>{slot.set_by}</Typography>}
        {slot.owner && slot.owner_link && (
          <Typography variant="caption" sx={{ color: FAINT }}>
            saved on {slot.owner}
            <Typography component="button" type="button" variant="caption" onClick={() => onGo(slot.owner_link)} sx={{ ...link, ml: 0.5 }}>open →</Typography>
          </Typography>
        )}
      </Box>
      {slot.runs?.why && <Typography variant="caption" data-tq-slot-why="" sx={{ color: FAINT, display: "block", mt: 0.5 }}>{slot.runs.why}</Typography>}
      {slot.note && <Typography variant="caption" sx={{ color: FAINT, display: "block", mt: 0.5 }}>{slot.note}</Typography>}
      {/* what it is actually asked: four yes/nos, whose criterion is the sentence on each report's own card (the owner, 2026-09-17) */}
      {isJudge && !!(slot.decides || []).length && (
        <Box sx={{ mt: 1.25, pt: 1, borderTop: `1px solid ${BORDER}` }}>
          <Typography variant="caption" sx={{ color: FAINT, fontWeight: 600, display: "block", mb: 0.5 }}>Asked of it, once per run</Typography>
          {slot.decides.map((d) => (
            <Typography key={d.line} sx={{ ...mono, fontSize: 11.5, color: INK, whiteSpace: "pre-wrap" }}>
              {d.line.toUpperCase()}: {d.says} <Typography component="span" sx={{ ...mono, fontSize: 11.5, color: FAINT }}>
                but only if: the sentence you wrote on that report&rsquo;s card</Typography>
            </Typography>
          ))}
          {slot.evidence && <Typography variant="caption" sx={{ color: FAINT, display: "block", mt: 0.5 }}>{slot.evidence}</Typography>}
        </Box>
      )}
    </Box>
  );
};

// a read that failed is tried again by itself - a server still starting, a slow first answer - and says why with a button meanwhile
export const RETRY_MS = [1500, 4000, 10000];

export default function AiDefaults({ brains, onGo }) {
  const [state, setState] = useState(null);
  const [err, setErr] = useState("");
  const tries = useRef(0);
  const load = useCallback(async () => {
    try { setState((await api.get("/api/ai/defaults")).data); setErr(""); tries.current = 0; }
    catch (e) {
      setErr(e?.response?.status === 404 ? "This Taskuary is older than this page - restart Taskuary and the page appears."
        : `Could not read which AI does what${e?.response?.data?.detail ? ` - ${e.response.data.detail}` : ""}.`);
      const wait = RETRY_MS[tries.current++];
      if (wait && e?.response?.status !== 404) setTimeout(load, wait);
    }
  }, []);
  useEffect(() => { load(); }, [load]);
  // The checklist's models row: arriving here is the evidence it was looked at. A failure is ignored - this page is the point.
  useEffect(() => { api.post("/api/setup/seen", { step: "models" }).catch(() => {}); }, []);
  const [say, setSay] = useState("");
  const save = async (slot, patch) => {
    try { setSay(""); await api.post("/api/ai/defaults", { slot: slot.key, ...patch }); load(); }
    catch (e) { setSay(e?.response?.data?.detail || "could not save that"); }
  };

  if (!state && !err) return <CircularProgress size={20} sx={{ m: 2 }} />;
  const slots = state?.slots || [];
  return (
    <Box sx={{ mb: 1 }}>
      <Typography variant="body2" sx={{ color: DIM, mb: 1.5 }}>
        Each job, the AI that does it and the model it runs on - picked from that AI's own list. Adding an AI or signing in is under{" "}
        <Typography component="button" type="button" variant="body2" onClick={() => onGo("connections")} sx={link}>Connections</Typography>.
      </Typography>
      {err && (
        <Alert severity="warning" sx={{ mb: 1.5, fontSize: 12.5 }} data-tq-ai-defaults-error=""
          action={<Button size="small" onClick={() => { tries.current = 0; load(); }} sx={{ textTransform: "none" }}>Try again</Button>}>{err}</Alert>
      )}
      {say && <Alert severity="warning" sx={{ mb: 1.5, fontSize: 12.5 }}>{say}</Alert>}
      {/* the levels govern the agents' cards above them: each level's AI and model, Auto on or off, the strong cap (the router, 2026-10-25);
          where reports go is its own job, after them */}
      {[...slots.filter((s) => s.key !== "judge_ai"), ...(slots.length ? ["levels"] : []), ...slots.filter((s) => s.key === "judge_ai")].map((s) => (s === "levels"
        ? <RouteRules key="levels" />
        : <Slot key={s.key} slot={s} brains={brains} agents={state.agent_options || []}
          judgeOptions={state.judge_options || []} onSave={(patch) => save(s, patch)} onGo={onGo} />))}
    </Box>
  );
}
