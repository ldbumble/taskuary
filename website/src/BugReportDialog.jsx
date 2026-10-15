// "Report this bug": the draft the server scrubbed, shown whole and editable, sent by opening GitHub's new-issue page.
// Nothing leaves without the person pressing Send, and what leaves is exactly what the boxes hold.
import React, { useEffect, useState } from "react";
import { Box, Button, Checkbox, CircularProgress, Dialog, DialogActions, DialogContent, DialogTitle, FormControlLabel, TextField, Typography } from "@mui/material";
import api from "./api";
import { snapshot } from "./lastError.js";
import { fullReport, issueUrl, joinBody, techOf } from "./bugReport.js";
import { draftRequest, howToOpen, openBugReport, rawError, shownError } from "./bugReportOpen.js";
import { capture, copyShot } from "./shot.js";
import { DIM, FAINT } from "./theme.jsx";

const CUT = "The full report is on your clipboard - paste it into the issue.";
const SHOT_ON = "The screenshot is on your clipboard - paste it into the issue.";

export default function BugReportDialog({ open, onClose, screen, error, supportUrl }) {
  const [req, setReq] = useState(null);
  const [draft, setDraft] = useState(null);
  const [refused, setRefused] = useState("");
  const [title, setTitle] = useState("");
  const [text, setText] = useState("");
  const [tech, setTech] = useState("");
  const [showTech, setShowTech] = useState(false);
  const [shot, setShot] = useState(null);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open) return undefined;
    let live = true;
    const r = draftRequest(snapshot(screen), error);
    setReq(r); setDraft(null); setRefused(""); setNote(""); setShot(null); setShowTech(false);
    api.post("/api/bug-report/draft", r).then(({ data }) => {
      if (!live) return;
      setDraft(data); setTitle(data.title || ""); setText(data.explanation || ""); setTech(techOf(data));
    }).catch((e) => {
      const d = e?.response?.data?.detail;
      if (live) setRefused(typeof d === "string" ? d : "The report could not be drafted.");
    });
    return () => { live = false; };
  }, [open, screen, error]);

  const copy = (s) => navigator.clipboard.writeText(s);
  const body = () => joinBody(text, tech, !!shot);
  const say = (p, ok) => p.then(() => setNote(ok)).catch(() => setNote("The clipboard refused it - select the text and copy it yourself."));
  const takeShot = (on) => {
    if (!on) { setShot(null); setNote(""); return; }
    const p = capture();
    setShot(p);
    copyShot(p).then(() => setNote(SHOT_ON)).catch(() => { setShot(null); setNote("The screenshot could not be taken."); });
  };
  const send = async () => {
    setBusy(true);
    try {
      const b = body(), { url, cut } = issueUrl(title, b);
      if (cut) await copy(fullReport(title, b)).catch(() => {});
      if (howToOpen(window) === "app") await api.post("/api/open-url", { url });
      else window.open(url, "_blank", "noopener");
      if (cut) setNote(CUT); else onClose();
    } catch { setNote("GitHub did not open. Copy the full report and paste it into a new issue."); }
    finally { setBusy(false); }
  };

  return <Dialog open={open} onClose={busy ? undefined : onClose} fullWidth maxWidth="sm" aria-labelledby="bug-report-title"
    PaperProps={{ sx: { maxHeight: "90vh" } }}>
    <DialogTitle id="bug-report-title">Report this bug</DialogTitle>
    <DialogContent>
      {refused ? <Typography sx={{ fontSize: 13.5 }}>{refused}</Typography>
        : !draft ? <Box sx={{ display: "flex", alignItems: "center", gap: 1.25, color: DIM, fontSize: 13 }}><CircularProgress size={16} />Preparing the report…</Box>
        : <>
          <Typography sx={{ color: DIM, fontSize: 13, mb: 2 }}>This goes to a public GitHub page. Check it before you submit.</Typography>
          <TextField fullWidth size="small" label="Title" value={title} disabled={busy} onChange={(e) => setTitle(e.target.value)} sx={{ mb: 2 }} />
          <TextField fullWidth multiline minRows={3} label="What happened" value={text} disabled={busy} onChange={(e) => setText(e.target.value)} />
          <Button size="small" onClick={() => setShowTech(!showTech)} aria-expanded={showTech}
            sx={{ mt: 1.5, px: 0, color: DIM, textTransform: "none" }}>{showTech ? "Hide technical details" : "Technical details"}</Button>
          {showTech && <TextField fullWidth multiline minRows={6} maxRows={16} value={tech} disabled={busy} onChange={(e) => setTech(e.target.value)}
            inputProps={{ "aria-label": "Technical details", style: { fontFamily: "ui-monospace, Consolas, monospace", fontSize: 12 } }} />}
          <FormControlLabel sx={{ display: "flex", mt: 1 }} label={<Typography sx={{ fontSize: 13 }}>Add a screenshot</Typography>}
            control={<Checkbox size="small" checked={!!shot} disabled={busy} onChange={(e) => takeShot(e.target.checked)} />} />
          {shot && <Typography sx={{ color: FAINT, fontSize: 12 }}>Every word in it is blanked out. Only the layout shows.</Typography>}
        </>}
      {note && <Typography sx={{ color: DIM, fontSize: 12.5, mt: 1.5 }} role="status">{note}</Typography>}
    </DialogContent>
    <DialogActions sx={{ px: 3, pb: 2, flexWrap: "wrap", gap: 1 }}>
      {supportUrl && <Button href={supportUrl} target="_blank" rel="noopener noreferrer" sx={{ mr: "auto", color: DIM, textTransform: "none" }}>Open GitHub</Button>}
      {refused ? <>
        <Button onClick={() => say(copy(rawError(req)), "Copied.")}>Copy the error</Button>
        <Button onClick={onClose}>Close</Button>
      </> : <>
        {shot && note === CUT && <Button onClick={() => say(copyShot(shot), SHOT_ON)}>Copy the screenshot</Button>}
        <Button onClick={() => say(copy(fullReport(title, body())), "Copied.")} disabled={!draft || busy}>Copy full report</Button>
        <Button variant="contained" onClick={send} disabled={!draft || busy || !title.trim()}>{busy ? "Opening…" : "Send"}</Button>
      </>}
    </DialogActions>
  </Dialog>;
}

// the quiet link under an error the page drew: small, dim, no icon - an offer, not an alarm
export const ReportLink = ({ text, style }) => <button type="button" onClick={() => openBugReport(shownError(text))}
  style={{ display: "block", marginTop: 4, padding: 0, border: 0, background: "none", color: DIM, fontSize: 11.5, cursor: "pointer", textDecoration: "underline", ...style }}>
  Report this bug</button>;
