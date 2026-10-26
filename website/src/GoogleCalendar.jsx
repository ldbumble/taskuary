// SIGN IN WITH GOOGLE FOR THE CALENDAR (the owner, 2026-10-26: "yes" to "A Gmail card's calendar is only read once its Google calendar
// fields are filled in by hand. Should the card offer a 'Sign in with Google' step for the calendar?"). A Gmail card is IMAP and carries
// no calendar, so while no Google calendar is on it the card offers this one step: the browser goes to Google asking for
// calendar.readonly and comes back to this server (googlecal.py), and the box finishes by itself, as Sign in with ChatGPT does.
// Taskuary ships no Google client: with none on the card the box says what is needed - the server says the same if pressed anyway.
import React, { useEffect, useState } from "react";
import { Box, Button, CircularProgress, Typography } from "@mui/material";
import api from "./api";
import { BORDER, DIM, INK, PANEL2 } from "./theme.jsx";

export const G_CAL = "Sign in with Google for the calendar";
export const G_CAL_NEEDS = "Needs a Google OAuth client of your own first: turn on the Google Calendar API in Google Cloud console, create an OAuth client of type Desktop app, and paste its client id and secret into this card's Google OAuth client fields.";
const saved = (conn, k) => (conn.ConfigSaved || []).includes(k);

export function GoogleCalendar({ conn, cfg, reload }) {
  const [flow, setFlow] = useState(null);      // {flow, url, at}
  const [state, setState] = useState("");      // "" | ok | error
  const [detail, setDetail] = useState("");
  const [busy, setBusy] = useState(false);
  const signedIn = saved(conn, "google_refresh_token") || !!cfg.google_refresh_token;
  const can = !!(cfg.google_client_id && (saved(conn, "google_client_secret") || cfg.google_client_secret));
  const base = `/api/connectors/${conn.ConnectorId}/google/calendar`;
  useEffect(() => {
    if (!flow) return undefined;
    let alive = true;
    const tick = async () => {
      if (!alive) return;
      try {
        const { data } = await api.post(`${base}/poll`, { flow: flow.flow });
        if (!alive) return;
        if (data.status === "pending" && Date.now() - flow.at > 600000) {
          api.post(`${base}/cancel`, { flow: flow.flow }).catch(() => {});
          setFlow(null); setState("error"); setDetail(`The sign-in was not finished in ten minutes, so this stopped waiting. Press ${G_CAL} to start a fresh one.`);
          return;
        }
        if (data.status === "pending") { setTimeout(tick, 2000); return; }
        setFlow(null); setState(data.status === "ok" ? "ok" : "error"); setDetail(data.detail || "the sign-in did not complete");
        if (data.status === "ok") reload?.();
      } catch (e) { if (!alive) return; setFlow(null); setState("error"); setDetail(e?.response?.data?.detail || "the sign-in did not complete"); }
    };
    const id = setTimeout(tick, 2000);
    return () => { alive = false; clearTimeout(id); };
  }, [flow, base, reload]);
  if (signedIn && !detail) return null;       // a Google calendar is on the card: nothing to offer
  const start = async () => {
    setBusy(true); setState(""); setDetail("");
    try { const { data } = await api.post(base); setFlow({ ...data, at: Date.now() }); window.open(data.url, "_blank", "noopener"); }
    catch (e) { setState("error"); setDetail(e?.response?.data?.detail || "could not start the sign-in"); }
    setBusy(false);
  };
  return (
    <Box data-tq-google-calendar="" sx={{ mb: 2, p: 1.5, border: `1px solid ${BORDER}`, borderRadius: 2, bgcolor: PANEL2, display: "flex", flexDirection: "column", gap: 1 }}>
      <Typography sx={{ fontWeight: 600, fontSize: 13, color: INK }}>Google calendar</Typography>
      <Typography variant="caption" sx={{ color: DIM, lineHeight: 1.5 }}>
        The App Password brings mail only. Sign in once and Taskuary reads this account's calendar - read-only - when it answers about times.
      </Typography>
      {state === "ok" ? null : flow ? (
        <Typography variant="caption" sx={{ color: DIM, display: "flex", alignItems: "center", gap: 0.75, flexWrap: "wrap" }}>
          <CircularProgress size={11} /> Finish in the Google tab that opened - this card completes by itself.
          <a href={flow.url} target="_blank" rel="noreferrer">Open it again</a>
          <Button size="small" onClick={() => { api.post(`${base}/cancel`, { flow: flow.flow }).catch(() => {}); setFlow(null); setState(""); setDetail(""); }}
            sx={{ fontSize: 11.5, color: DIM }}>Cancel</Button>
        </Typography>
      ) : (
        <Box><Button variant="contained" disableElevation disabled={busy} onClick={start}>
          {busy ? <CircularProgress size={14} sx={{ color: "#fff" }} /> : G_CAL}</Button></Box>
      )}
      {!can && !flow && !detail && <Typography variant="caption" sx={{ color: DIM, lineHeight: 1.5 }}>{G_CAL_NEEDS}</Typography>}
      {detail && <Typography variant="body2" role={state === "ok" ? undefined : "alert"} sx={{ fontWeight: 600, color: state === "ok" ? "#47654a" : "#6b2733" }}>
        {state === "ok" ? "✓" : "✗"} {detail}</Typography>}
    </Box>
  );
}
