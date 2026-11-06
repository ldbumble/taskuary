// "Report this bug": the draft the server scrubbed, shown whole and editable, sent by opening GitHub's new-issue page.
// Nothing leaves without the person pressing Send, and what leaves is exactly what the boxes hold.
import React, { useEffect, useState } from "react";
import { Box, Button, Checkbox, CircularProgress, Dialog, DialogContent, DialogTitle, FormControlLabel, TextField, Typography } from "@mui/material";
import { ButtonBar } from "./ButtonBar.jsx";
import api from "./api";
import { snapshot } from "./lastError.js";
import { fullReport, issueUrl, joinBody, techOf } from "./bugReport.js";
import { draftRequest, howToOpen, openBugReport, rawError, shownError } from "./bugReportOpen.js";
import { capture, copyShot } from "./shot.js";
import { DIM, FAINT } from "./theme.jsx";
import { label as btnLabel } from "./buttons.js";

const CUT = "The full report is on your clipboard - paste it into the issue.";
const SHOT_ON = "The screenshot is on your clipboard - paste it into the issue.";
const REFUSED = "The clipboard refused it - select the text and copy it yourself.";

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
  // whether the screenshot is still what the clipboard holds: a text copy since puts it out of reach, so offer it again
  const [shotOnClip, setShotOnClip] = useState(false);

  useEffect(() => {
    if (!open) return undefined;
    let live = true;
    const r = draftRequest(snapshot(screen), error);
    setReq(r); setDraft(null); setRefused(""); setNote(""); setShot(null); setShotOnClip(false); setShowTech(false);
    api.post("/api/bug-report/draft", r).then(({ data }) => {
      if (!live) return;
      setDraft(data); setTitle(data.title || ""); setText(data.explanation || ""); setTech(techOf(data));
    }).catch((e) => {
      const d = e?.response?.data?.detail;
      if (live) setRefused(typeof d === "string" ? d : "The report could not be drafted.");
    });
    return () => { live = false; };
  }, [open, screen, error]);

  const copy = (s) => Promise.resolve().then(() => navigator.clipboard.writeText(s));     // no clipboard API: a rejection, not a throw
  // a wish (the Assistant's issue.draft, a system with no card) is a feature request: its own title, field and label
  const kind = draft?.kind || error?.kind || "bug", wish = kind === "feature";
  const body = () => joinBody(text, tech, !!shot, kind);
  const say = (p, ok, onClip) => p.then(() => { setNote(ok); setShotOnClip(onClip); }).catch(() => setNote(REFUSED));
  const copyText = (s, ok) => say(copy(s), ok, false);
  const takeShot = (on) => {
    if (!on) { setShot(null); setShotOnClip(false); setNote(""); return; }
    const p = capture();
    setShot(p);
    copyShot(p).then(() => { setNote(SHOT_ON); setShotOnClip(true); })
      .catch(() => { setShot(null); setShotOnClip(false); setNote("The screenshot could not be copied."); });
  };
  const send = async () => {
    setBusy(true);
    try {
      const b = body(), { url, cut } = issueUrl(title, b, undefined, kind);
      // the cut note only when the copy took: otherwise it would send them to paste what is not there
      const copied = cut ? await copy(fullReport(title, b)).then(() => true, () => false) : false;
      if (copied) setShotOnClip(false);
      if (howToOpen(window) === "app") await api.post("/api/open-url", { url });
      else window.open(url, "_blank", "noopener");
      if (cut) setNote(copied ? CUT : REFUSED); else onClose();
    } catch { setNote("GitHub did not open. Copy the full report and paste it into a new issue."); }
    finally { setBusy(false); }
  };

  return <Dialog open={open} onClose={busy ? undefined : onClose} fullWidth maxWidth="sm" aria-labelledby="bug-report-title"
    PaperProps={{ sx: { maxHeight: "90vh" } }}>
    <DialogTitle id="bug-report-title">{btnLabel("report_bug", wish ? "feature" : undefined)}</DialogTitle>
    <DialogContent>
      {refused ? <Typography sx={{ fontSize: 13.5 }}>{refused}</Typography>
        : !draft ? <Box sx={{ display: "flex", alignItems: "center", gap: 1.25, color: DIM, fontSize: 13 }}><CircularProgress size={16} />{wish ? "Preparing the request…" : "Preparing the report…"}</Box>
        : <>
          <Typography sx={{ color: DIM, fontSize: 13, mb: 2 }}>This goes to a public GitHub page. Check it before you submit.</Typography>
          <TextField fullWidth size="small" label="Title" value={title} disabled={busy} onChange={(e) => setTitle(e.target.value)} sx={{ mb: 2 }} />
          <TextField fullWidth multiline minRows={3} label={wish ? "What would help" : "What happened"} value={text} disabled={busy} onChange={(e) => setText(e.target.value)} />
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
    <ButtonBar>
      {refused ? <>
        <Button onClick={() => copyText(rawError(req), "Copied.")}>Copy the error</Button>
        <Button onClick={onClose}>Close</Button>
      </> : <>
        <Button variant="contained" onClick={send} disabled={!draft || busy || !title.trim()}>{busy ? "Opening…" : "Send"}</Button>
        <Button onClick={() => copyText(fullReport(title, body()), "Copied.")} disabled={!draft || busy}>Copy full report</Button>
        {shot && !shotOnClip && <Button onClick={() => say(copyShot(shot), SHOT_ON, true)}>Copy the screenshot</Button>}
        {!draft && <Button onClick={onClose}>Close</Button>}
      </>}
      {supportUrl && <><ButtonBar.Sep /><Button href={supportUrl} target="_blank" rel="noopener noreferrer">Open GitHub</Button></>}
    </ButtonBar>
  </Dialog>;
}

// the quiet link under an error the page drew: small, dim, no icon - an offer, not an alarm
export const ReportLink = ({ text, style }) => <button type="button" onClick={() => openBugReport(shownError(text))}
  style={{ display: "block", marginTop: 4, padding: 0, border: 0, background: "none", color: DIM, fontSize: 11.5, cursor: "pointer", textDecoration: "underline", ...style }}>
  {btnLabel("report_bug")}</button>;
