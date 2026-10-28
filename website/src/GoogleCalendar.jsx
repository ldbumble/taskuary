// SIGN IN WITH GOOGLE FOR THE CALENDAR (the owner, 2026-10-26: "yes" to "A Gmail card's calendar is only read once its Google calendar
// fields are filled in by hand. Should the card offer a 'Sign in with Google' step for the calendar?"). A Gmail card is IMAP and carries
// no calendar, so while no Google calendar is on it the card offers this one step: the browser goes to Google asking for
// calendar.readonly and comes back to this server (googlecal.py), and the box finishes by itself, as Sign in with ChatGPT does.
// It rides Taskuary's own Google client (the owner, 2026-10-26: "don't want to create my own google client, want to use their own"):
// nobody creates or pastes one. A build that has none yet draws no step at all - no instructions to go and make a client.
import React, { useEffect, useState } from "react";
import { Box, Button, CircularProgress, Typography } from "@mui/material";
import api from "./api";
import { BORDER, DIM, INK, PANEL2 } from "./theme.jsx";
import { PEOPLE_MISSING } from "./peopleSearch.js";

export const G_CAL = "Sign in with Google for the calendar";
export const G_CAL_NONE = "Google sign-in isn't available in this build yet";
const saved = (conn, k) => (conn.ConfigSaved || []).includes(k);

export function GoogleCalendar({ conn, cfg, reload }) {
  const [flow, setFlow] = useState(null);      // {flow, url, at}
  const [state, setState] = useState("");      // "" | ok | error
  const [detail, setDetail] = useState("");
  const [busy, setBusy] = useState(false);
  const signedIn = saved(conn, "google_refresh_token") || !!cfg.google_refresh_token;
  const [can, setCan] = useState(true);        // the server's word: does this build carry a Google client (googlecal.available)
  const base = `/api/connectors/${conn.ConnectorId}/google/calendar`;
  useEffect(() => {
    if (signedIn) return undefined;
    let alive = true;
    api.get(base).then(({ data }) => { if (alive) setCan(!!data.available); }).catch(() => {});
    return () => { alive = false; };
  }, [base, signedIn]);
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
  // a Google calendar is on the card: nothing to offer - but a sign-in from before Taskuary asked for contacts says the search skips them
  if (signedIn && !detail && conn.PeopleMissing?.length)
    return <Typography data-tq-google-people="" variant="caption" component="div" sx={{ color: DIM, mb: 2 }}>{PEOPLE_MISSING("this account's Google contacts")}</Typography>;
  if (signedIn && !detail) return null;
  // ...and a build with no Google client draws nothing: a disabled button saying so was a dead box on the card (the setup sweep, 2026-10-28)
  if (!can && !flow && !detail) return null;
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
        The App Password brings mail only. Sign in once and Taskuary reads this account's calendar - read-only - when it answers about times,
        and searches its contacts when you pick someone to write to.
      </Typography>
      {state === "ok" ? null : flow ? (
        <Typography variant="caption" sx={{ color: DIM, display: "flex", alignItems: "center", gap: 0.75, flexWrap: "wrap" }}>
          <CircularProgress size={11} /> Finish in the Google tab that opened - this card completes by itself.
          <a href={flow.url} target="_blank" rel="noreferrer">Open it again</a>
          <Button size="small" onClick={() => { api.post(`${base}/cancel`, { flow: flow.flow }).catch(() => {}); setFlow(null); setState(""); setDetail(""); }}
            sx={{ fontSize: 11.5, color: DIM }}>Cancel</Button>
        </Typography>
      ) : (
        <Box><Button variant="contained" disableElevation disabled={busy || !can} onClick={start}>
          {busy ? <CircularProgress size={14} sx={{ color: "#fff" }} /> : G_CAL}</Button></Box>
      )}
      {detail && <Typography variant="body2" role={state === "ok" ? undefined : "alert"} sx={{ fontWeight: 600, color: state === "ok" ? "#47654a" : "#6b2733" }}>
        {state === "ok" ? "✓" : "✗"} {detail}</Typography>}
    </Box>
  );
}
