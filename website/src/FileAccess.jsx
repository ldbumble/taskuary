// ALLOW SAVING FILES, on a sign-in card (the owner, 2026-10-23): off by default, and choosing it signs in again asking for one more
// permission - Microsoft's Files.ReadWrite on an Outlook or Teams card, Google's drive.file on the Gmail card - so Share can put a result
// in a Taskuary folder of the owner's OneDrive or Drive. The default sign-in never asks for it (fileaccess.py).
import React, { useState } from "react";
import { Box, Checkbox, FormControlLabel, Typography } from "@mui/material";
import api from "./api";
import { BORDER, DIM, INK, PANEL2 } from "./theme.jsx";

export const ALLOW_FILES = "Allow saving files";
export const MS_FILES_HINT = "Signs in again asking Microsoft for one more permission, Files.ReadWrite, so Share can save a result to a Taskuary folder in your OneDrive. Off: Taskuary never asks for it.";
export const G_FILES_HINT = "Signs in again asking Google for one more permission, drive.file - it sees only the files Taskuary makes - so Share can save a result to a Taskuary folder in your Drive.";

export function AllowFiles({ checked, onChange, disabled = false, hint }) {
  return (
    <FormControlLabel title={hint} data-tq-allow-files="" sx={{ m: 0, "& .MuiTypography-root": { fontSize: 12.5, color: INK } }}
      control={<Checkbox size="small" checked={!!checked} disabled={disabled} onChange={(e) => onChange(e.target.checked)} />} label={ALLOW_FILES} />
  );
}

// the Gmail card's: a consent round of the card's own OAuth client, opened in a new tab; the server keeps the new token on its return
export function GoogleFiles({ conn, cfg, reload }) {
  const [err, setErr] = useState(""), [went, setWent] = useState(false);
  // a Google sign-in to widen: the calendar's, on Taskuary's own client or the card's (googlecal.client)
  const can = (conn.ConfigSaved || []).includes("google_refresh_token") || !!cfg.google_refresh_token;
  // no Google sign-in to widen and nothing chosen: a panel holding only a disabled checkbox is not drawn (the setup sweep, 2026-10-28) -
  // it comes once the calendar's sign-in is on the card
  if (!can && !cfg.allow_files) return null;
  const flip = async (on) => {
    setErr("");
    try { const { data } = await api.post(`/api/connectors/${conn.ConnectorId}/google/files`, { on }); window.open(data.url, "_blank", "noopener"); setWent(true); }
    catch (e) { setErr(e?.response?.data?.detail || "Google could not be asked - try again."); }
  };
  return (
    <Box data-tq-google-files="" sx={{ mb: 2, p: 1.25, border: `1px solid ${BORDER}`, borderRadius: 2, bgcolor: PANEL2, display: "flex", flexDirection: "column", gap: 0.5 }}>
      <AllowFiles checked={cfg.allow_files} onChange={flip} disabled={!can}
        hint={can ? G_FILES_HINT : "Needs the Google sign-in first - Sign in with Google for the calendar, above"} />
      {went && <Typography variant="caption" sx={{ color: DIM }}>Finish in the Google tab, then come back - this card reads it again.
        <Box component="button" type="button" onClick={() => { setWent(false); reload?.(); }} sx={{ ml: 0.75, border: 0, background: "none", color: "#55697a", cursor: "pointer", font: "inherit", p: 0 }}>Read it again</Box></Typography>}
      {err && <Typography variant="caption" role="alert" sx={{ color: "#6b2733" }}>{err}</Typography>}
    </Box>
  );
}
