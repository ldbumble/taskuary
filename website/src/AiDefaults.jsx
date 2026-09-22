// The AI defaults panel: who triages, who codes, who assists — and on WHICH MODEL, in one
// place. Before this, Settings named a brain and stopped: the model that brain would actually
// run lived on the connector's card, or on the CLI profile's light-model field, or in a plain
// text box, depending on what you had picked. Three defaults, three screens, and the page that
// chose the brain could not tell you what was about to happen (the owner, 2026-09-10).
//
// So every row here answers the same two questions out loud — what runs, and who owns it — and
// writes each half back to the screen that owns it. Nothing is stored twice: the connector card
// and Connections → AI CLI agents remain the truth and keep working.
import React, { useCallback, useEffect, useState } from "react";
import { Alert, AlertTitle, Autocomplete, Box, CircularProgress, MenuItem, Select, TextField, Typography } from "@mui/material";
import api from "./api";
import { ACCENT2, BORDER, DIM, FAINT, INK, card, mono } from "./theme.jsx";

// A model box left blank is not "unconfigured" — it means the provider's own default, and the
// server says which. Shown as the placeholder so an empty field never reads as broken.
const Model = ({ slot, onSave }) => {
  const [v, setV] = useState(slot.model || "");
  useEffect(() => { setV(slot.model || ""); }, [slot.model, slot.value]);
  const commit = (next) => { if ((next || "") !== (slot.model || "")) onSave({ model: next || "" }); };
  return (
    <Autocomplete freeSolo size="small" options={slot.choices || []} value={v} disabled={!slot.ready}
      onInputChange={(_e, next) => setV(next)}
      onChange={(_e, next) => { setV(next || ""); commit(next || ""); }}
      onBlur={() => commit(v)}
      sx={{ minWidth: 260 }}
      renderInput={(p) => <TextField {...p} label="model" placeholder={slot.default_hint || "provider default"}
        sx={{ bgcolor: "#fff" }} />} />
  );
};

// One default = one card. Colour only IDENTIFIES (the sage rule) - the emphasis is
// typographic, and the line that matters most, "what will actually run", is the loudest thing
// in the card rather than a caption under two dropdowns.
const Slot = ({ slot, brains, agents, judgeOptions, onSave, onGo }) => {
  const isAgent = slot.key === "default_agent";
  // The judge is the one slot that may be pointed at a model which cannot write, so it is the one
  // picker that shows them. Its own blank row already means "auto" (the report's own brain), so
  // the brains' auto entry — same empty value — is dropped rather than offered twice.
  const isJudge = slot.key === "judge_ai";
  const options = isAgent ? (agents || []).map((a) => typeof a === "string"
    ? { value: a, label: a, ready: true }
    : a) : isJudge ? [...(judgeOptions || []), ...(brains || []).filter((o) => o.value)] : brains;
  const picked = options.find((o) => o.value === slot.value);
  // the judge names no model of its own, so RUNS is the thing itself rather than "· the provider default"
  const runs = isJudge ? (slot.default_hint || "") : (slot.model || slot.default_hint || "the provider default");
  return (
    <Box sx={{ ...card, p: 2, mb: 1.5, bgcolor: "#fff" }}>
      <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 0.25 }}>
        <Box sx={{ width: 7, height: 7, borderRadius: "50%", bgcolor: ACCENT2, flexShrink: 0 }} />
        <Typography sx={{ color: INK, fontWeight: 800, fontSize: 14 }}>{slot.label}</Typography>
      </Box>
      <Typography variant="body2" sx={{ color: DIM, mb: 0.25 }}>{slot.desc}</Typography>
      <Typography variant="caption" sx={{ color: FAINT, display: "block", mb: 1.5 }}>{slot.why}</Typography>

      <Box sx={{ display: "flex", gap: 1.5, flexWrap: "wrap", alignItems: "flex-start" }}>
        <Box>
          <Typography variant="caption" sx={{ color: FAINT, display: "block", mb: 0.4, fontWeight: 700 }}>
            {isAgent ? "which CLI" : isJudge ? "what decides" : "which brain"}
          </Typography>
          <Select size="small" displayEmpty value={picked ? slot.value : ""}
            onChange={(e) => onSave({ value: e.target.value })}
            sx={{ minWidth: 250, fontSize: 12.5, bgcolor: "#fff" }}>
            {options.map((o) => (
              <MenuItem key={o.value} value={o.value} disabled={o.ready === false} sx={{ fontSize: 12.5 }}>
                {o.label}{o.ready === false ? " — no key saved" : ""}
              </MenuItem>
            ))}
            {!options.length && <MenuItem value="" disabled sx={{ fontSize: 12.5 }}>nothing configured yet</MenuItem>}
          </Select>
        </Box>
        {/* four yes/nos do not get better on a bigger model, and this slot owns no model setting
            to write one to - a box that saved nowhere would be worse than no box */}
        {!isJudge && (
          <Box>
            <Typography variant="caption" sx={{ color: FAINT, display: "block", mb: 0.4, fontWeight: 700 }}>model</Typography>
            <Model slot={slot} onSave={onSave} />
          </Box>
        )}
        {/* effort only where the CLI can actually be told one - climodels leaves it empty for
            the CLIs whose flag we cannot spell, and a dead dropdown would imply otherwise */}
        {!!(slot.efforts || []).length && (
          <Box>
            <Typography variant="caption" sx={{ color: FAINT, display: "block", mb: 0.4, fontWeight: 700 }}>effort</Typography>
            <Select size="small" displayEmpty value={slot.effort || ""} onChange={(e) => onSave({ effort: e.target.value })}
              sx={{ minWidth: 150, fontSize: 12.5, bgcolor: "#fff" }}>
              <MenuItem value="" sx={{ fontSize: 12.5 }}>default</MenuItem>
              {slot.efforts.map((eff) => <MenuItem key={eff} value={eff} sx={{ fontSize: 12.5 }}>{eff}</MenuItem>)}
            </Select>
          </Box>
        )}
      </Box>

      <Box sx={{ mt: 1.5, pt: 1.25, borderTop: `1px solid ${BORDER}`, display: "flex", gap: 1,
        alignItems: "baseline", flexWrap: "wrap" }}>
        <Typography variant="caption" sx={{ color: FAINT, fontWeight: 700 }}>RUNS</Typography>
        <Typography sx={{ ...mono, fontSize: 12.5, color: INK, fontWeight: 700 }}>
          {picked ? picked.label : "—"}{slot.ready && runs ? ` · ${runs}` : ""}{slot.effort ? ` · ${slot.effort}` : ""}
        </Typography>
        {slot.owner && (
          <Typography variant="caption" sx={{ color: FAINT }}>
            saved on {slot.owner}
            {slot.owner_link && (
              <Typography component="span" variant="caption" onClick={() => onGo(slot.owner_link)}
                sx={{ color: "#55697a", cursor: "pointer", ml: 0.5, "&:hover": { textDecoration: "underline" } }}>
                open →
              </Typography>
            )}
          </Typography>
        )}
      </Box>
      {slot.note && <Typography variant="caption" sx={{ color: FAINT, display: "block", mt: 0.5 }}>{slot.note}</Typography>}
      {/* What it is actually asked. This slot is not a taste setting - it is four yes/nos, and
          whichever thing answers them answers exactly these (the owner, 2026-09-17: "show the
          wording for jev ... what are the decision choices it's going for"). The criterion in each
          one is the sentence on the report's own card, which is why it is not repeated here. */}
      {isJudge && !!(slot.decides || []).length && (
        <Box sx={{ mt: 1.25, pt: 1, borderTop: `1px solid ${BORDER}` }}>
          <Typography variant="caption" sx={{ color: FAINT, fontWeight: 700, display: "block", mb: 0.5 }}>
            ASKED OF IT, ONCE PER RUN
          </Typography>
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

export default function AiDefaults({ brains, agents, onGo, onLoaded }) {
  const [state, setState] = useState(null);
  const [err, setErr] = useState("");
  const load = useCallback(async () => {
    try { setState((await api.get("/api/ai/defaults")).data); onLoaded?.(true); }
    catch (e) {
      // Tell the page this panel is not standing up, so it puts the PLAIN rows back. Hiding
      // them in favour of a panel that then fails made the triage brain, the default agent and
      // the assistant unreachable altogether - worse than the duplication it was avoiding.
      onLoaded?.(false);
      // A failed load used to leave `state` null forever, and the spinner below never came
      // down: the panel span the whole error away. 404 here means one specific thing - the
      // server predates this endpoint - so say that rather than "something went wrong".
      setErr(e?.response?.status === 404
        ? "this Taskuary server is older than this page — restart Taskuary to pick up the new backend"
        : (e?.response?.data?.detail || e?.message || "could not read the AI defaults"));
      setState({ slots: [], agents: [] });
    }
  }, []);
  useEffect(() => { load(); }, [load]);
  // The checklist's models row is the one step with nothing to derive - a fresh install already
  // ships working brain and model defaults, so "the defaults are fine" and "I never looked" are the
  // same state. Arriving here is the evidence, so arriving here is what records it. Failure is
  // ignored on purpose: a checklist row is a nicety and this page is the point.
  useEffect(() => { api.post("/api/setup/seen", { step: "models" }).catch(() => {}); }, []);

  const save = async (slot, patch) => {
    try { setErr(""); await api.post("/api/ai/defaults", { slot: slot.key, ...patch }); load(); }
    catch (e) { setErr(e?.response?.data?.detail || "could not save that"); }
  };

  const stale = /restart Taskuary/.test(err);
  if (!state) return <CircularProgress size={20} sx={{ m: 2 }} />;
  return (
    <Box sx={{ mb: 1 }}>
      <Typography variant="body2" sx={{ color: DIM, mb: 1.5 }}>
        Which AI does what, and on which model. Adding or signing into a CLI or an API key is
        still <Typography component="span" variant="body2" onClick={() => onGo("connectors")}
          sx={{ color: "#55697a", cursor: "pointer", "&:hover": { textDecoration: "underline" } }}>Connections</Typography>;
        this page only chooses between what you have connected.
      </Typography>
      {err && (
        <Alert severity={stale ? "error" : "warning"} sx={{ mb: 1.5, fontSize: 12.5 }}>
          {stale && <AlertTitle sx={{ fontSize: 13, fontWeight: 800 }}>Restart Taskuary to finish this update</AlertTitle>}
          {err}
          {stale && " — until then the rows below are the older, plainer controls, and the model and effort pickers are not available."}
        </Alert>
      )}
      {/* a payload without slots is a payload, not a crash: the public demo serves one and the
          whole Settings view fell into the error boundary - "Something in this view failed to
          draw" - over a page of knobs that simply had nothing to list (2026-09-22) */}
      {(state.slots || []).map((s) => (
        <Slot key={s.key} slot={s} brains={brains} agents={state.agent_options || agents || state.agents || []}
          judgeOptions={state.judge_options || []} onSave={(patch) => save(s, patch)} onGo={onGo} />
      ))}
    </Box>
  );
}
