// ONE CARD FOR EVERY ACT A CONNECTOR DECLARES (the owner, 2026-11-05: "each connector should have settings what the action view looks like
// no?"): the agent's run_tool on a tool the catalogue gives an action view (taskuary/connectorcatalog.json `actions`, read by actionCard.js) -
// a LinkedIn post with its picture, who sees it and post now or save as a draft; a Bluesky or Mastodon post; a comment on a tracker item. Its
// words are editable while it waits, its choices too where declared, pre-filled from the connection's defaults (Connections). The press is the
// one decide road every proposal takes (/api/reviews/{id}/decide, verdicts.decide -> proposals.execute): nothing goes before it. Live only on
// the newest turn; older turns keep theirs read-only, in their own words. Once it went it says so, with the link.
import React, { useState } from "react";
import { Box, Button, CircularProgress, Typography } from "@mui/material";
import OpenInNewIcon from "@mui/icons-material/OpenInNew";
import api from "./api.js";
import { attUrl } from "./Attachments.jsx";
import { FileDialog } from "./PublishedPages.jsx";
import { actionFor, changed, choiceOf, fieldsOf, stateOf, textKey, valuesOf, wordsOf } from "./actionCard.js";
import { outputRow } from "./taskOutputs.js";
import { hint } from "./buttons.js";
import { ACCENT, ALERT_INK, BORDER, DIM, FAINT, INK } from "./theme.jsx";

const initials = (s) => String(s || "").split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0].toUpperCase()).join("") || "in";
const PICK = { font: "inherit", fontSize: 11.5, color: INK, border: 0, background: "transparent", padding: 0, cursor: "pointer", outline: 0 };

export default function ActionCard({ row, tid, live = true, onChanged }) {
  const p = row?.post || {}, act = actionFor(p.type), st = stateOf(row, live), tk = textKey(act);
  const [text, setText] = useState(String(p[tk] || "")), [vals, setVals] = useState(() => valuesOf(act, p));
  const [busy, setBusy] = useState(""), [err, setErr] = useState(""), [viewing, setViewing] = useState(null), [done, setDone] = useState(null);
  if (!act) return null;
  const fields = fieldsOf(act, p, !!st.live && !done), post = act.kind === "post", w = wordsOf(act, done || st.live ? vals : p);
  const img = fields.find((f) => f.type === "image" && f.value), pic = img ? outputRow(tid ?? row?.TaskId, img.value) : null;
  const max = fields.find((f) => f.key === tk)?.max, over = max && text.length > max;
  const go = done?.url ?? st.url, gone = !!done || st.done;
  const decide = async (verb) => {
    setBusy(verb); setErr("");
    const nothing = `It didn't go through - nothing was ${post ? "posted" : "sent"}. Try again.`;
    try {
      const { data } = await api.post(`/api/reviews/${row.ReviewId}/decide`, { verb, final_text: verb === "approve" ? text : null, note: null,
        ...(verb === "approve" && Object.keys(changed(act, p, vals)).length ? { fields: changed(act, p, vals) } : {}) }, { timeout: 120000 });
      if (!data?.ok) { setErr(data?.send_error || nothing); return; }
      if (verb === "approve") setDone({ url: data.result?.url || "" });
      onChanged?.();
    } catch (e) { setErr(e?.response?.data?.detail || nothing); }
    finally { setBusy(""); }
  };
  // ...a choice reads as its label; while it waits, the label is the pick itself - no box around it
  const choice = (f) => f.editable
    ? <Box component="select" key={f.key} data-tq-act-choice={f.key} aria-label={f.label} value={String(vals[f.key])} disabled={!!busy}
        onChange={(e) => setVals((v) => ({ ...v, [f.key]: e.target.value }))} sx={PICK}>
        {f.choices.map((c) => <option key={String(c.value)} value={String(c.value)}>{c.label}</option>)}</Box>
    : <span key={f.key} data-tq-act-choice={f.key}>{choiceOf(f, f.value)?.label || String(f.value)}</span>;
  const meta = [row?.network, ...fields.filter((f) => f.type === "choice").map(choice)].filter(Boolean);
  const lines = fields.filter((f) => f.type === "line" && f.value);
  return (
    <Box data-tq-act={row?.ReviewId} data-tq-act-kind={act.kind} data-tq-act-state={gone ? "done" : st.live ? "waiting" : "not-done"}
      sx={{ mt: 1, border: `1px solid ${BORDER}`, borderRadius: 2, bgcolor: "#fff", overflow: "hidden" }}>
      <Box sx={{ display: "flex", alignItems: "center", gap: 1, px: 1.5, pt: 1.25, pb: 0.75 }}>
        {post && <Box aria-hidden sx={{ width: 34, height: 34, borderRadius: "50%", bgcolor: "#dfe6ec", color: ACCENT, display: "grid", placeItems: "center", fontWeight: 700, fontSize: 13 }}>
          {initials(row?.as)}</Box>}
        <Box sx={{ minWidth: 0 }}>
          <Typography sx={{ fontSize: 13.5, fontWeight: 700, color: INK, lineHeight: 1.2 }}>
            {post ? row?.as || `Your ${row?.network || ""} account` : lines.map((f) => `${f.label} ${f.value}`).join(" · ") || row?.network}</Typography>
          <Typography component="div" sx={{ fontSize: 11.5, color: FAINT }}>{meta.map((m, i) => <React.Fragment key={i}>{i ? " · " : ""}{m}</React.Fragment>)}</Typography>
        </Box>
      </Box>
      {post && lines.map((f) => <Typography key={f.key} sx={{ px: 1.5, fontSize: 12, color: DIM }}>{f.label}: {f.value}</Typography>)}
      {st.live && !gone
        ? <Box component="textarea" data-tq-act-text="" value={text} onChange={(e) => setText(e.target.value)} disabled={!!busy} rows={Math.min(14, Math.max(3, text.split("\n").length + 1))}
            sx={{ display: "block", width: "100%", boxSizing: "border-box", resize: "vertical", border: 0, outline: 0, px: 1.5, py: 0.5, font: "inherit", fontSize: 13.5, lineHeight: 1.5, color: INK, bgcolor: "transparent" }} />
        : <Typography data-tq-act-text="" sx={{ px: 1.5, py: 0.5, fontSize: 13.5, lineHeight: 1.5, color: gone ? INK : DIM, whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{p[tk]}</Typography>}
      {pic && <Box component="img" data-tq-act-image={img.value} src={attUrl(pic)} alt={p.alt || pic.name} onClick={() => setViewing(pic)}
        sx={{ display: "block", width: "100%", maxHeight: 320, objectFit: "contain", bgcolor: "#f6f4f1", mt: 0.75, cursor: "zoom-in", borderTop: `1px solid ${BORDER}`, borderBottom: `1px solid ${BORDER}` }} />}
      <Box sx={{ display: "flex", alignItems: "center", gap: 1, px: 1.5, py: 1, flexWrap: "wrap" }}>
        {gone ? <Typography data-tq-act-done="" sx={{ fontSize: 13, color: "#47654a", fontWeight: 600 }}>✓ {done ? w.done : st.said}
          {go && <> · <a href={go} target="_blank" rel="noopener noreferrer" style={{ color: ACCENT }}>See it on {row?.network}<OpenInNewIcon sx={{ fontSize: 12, ml: 0.25, verticalAlign: "-1px" }} /></a></>}</Typography>
          : st.live ? <>
            <Button size="small" variant="contained" disableElevation data-tq-act-press="" disabled={!!busy || !text.trim() || !!over} onClick={() => decide("approve")}
              title={hint("approve", post ? "post" : "action")} startIcon={busy === "approve" ? <CircularProgress size={12} color="inherit" /> : null}>
              {busy === "approve" ? w.busy : w.press}</Button>
            <Button size="small" disabled={!!busy} onClick={() => decide("reject")} data-tq-act-dismiss="">Dismiss</Button>
            {over ? <Typography sx={{ fontSize: 11.5, color: ALERT_INK }}>{text.length} of {max} characters</Typography>
              : act.note && <Typography sx={{ fontSize: 11.5, color: FAINT }}>{act.note}</Typography>}</>
          : <Typography sx={{ fontSize: 12.5, color: FAINT }}>{st.said}</Typography>}
      </Box>
      {err && <Typography role="alert" sx={{ px: 1.5, pb: 1, fontSize: 12.5, color: ALERT_INK }}>{err}</Typography>}
      <FileDialog file={viewing} onClose={() => setViewing(null)} />
    </Box>
  );
}
