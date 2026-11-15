// SIGN IN WITH GOOGLE, on the Gmail card (the owner, 2026-11-15: "any way to connect to gmail through the api so you can use the calendar
// item? add that option as well not just app password"). One sign-in brings the account's mail, calendar and contacts: the browser goes
// to Google and comes back to this server (googlecal.py), and the box finishes by itself, as Sign in with ChatGPT does.
// EACH INSTALL BRINGS ITS OWN GOOGLE CLIENT, as Microsoft (MsOwnApp): Taskuary ships none, so a card without one lists the steps to make
// a Desktop client and holds its two boxes (`children`, the card's own autosaving fields) - never a button that says it cannot.
// What the box says once signed in - which road the mail is on, a lapse, a sign-in that only reads - is the server's line (googlecal.state).
import React, { useEffect, useState } from "react";
import { Box, Button, CircularProgress, Typography } from "@mui/material";
import api from "./api";
import { BORDER, DIM, INK, PANEL2 } from "./theme.jsx";
import { PEOPLE_MISSING } from "./peopleSearch.js";

export const G_SIGNIN = "Sign in with Google";
const CLOUD = "https://console.cloud.google.com";
const saved = (conn, k) => (conn.ConfigSaved || []).includes(k);
const A = ({ to, children }) => <a href={`${CLOUD}${to}`} target="_blank" rel="noreferrer">{children}</a>;

// the five minutes in Google Cloud, in the order its pages ask for them
const ClientSteps = () => (
  // ...its links in the app's own link colour, not the browser's default blue (the Gmail card's look, 2026-11-15)
  <Box component="ol" data-tq-google-steps="" sx={{ m: 0, pl: 2.5, color: DIM, fontSize: 12.5, lineHeight: 1.6, "& li": { mb: 0.25 },
    "& a": { color: "var(--tq-link, #55697a)", fontWeight: 600, textUnderlineOffset: 2 } }}>
    <li>Open <A to="/projectcreate">Google Cloud → New project</A>, name it Taskuary → Create. It is free.</li>
    <li>Enable three APIs in that project: <A to="/apis/library/gmail.googleapis.com">Gmail API</A>,{" "}
      <A to="/apis/library/calendar-json.googleapis.com">Google Calendar API</A> and <A to="/apis/library/people.googleapis.com">People API</A> → Enable on each.</li>
    <li><A to="/auth/overview">Google Auth Platform → Get started</A>: app name Taskuary, your own email. Audience: <b>Internal</b> on a
      Google Workspace account; otherwise <b>External</b>, then Audience → Test users → add your own address.</li>
    <li><A to="/auth/clients">Clients → Create client</A> → Application type <b>Desktop app</b> → Create. Copy its Client ID and Client
      secret into the two boxes below.</li>
    <li>Press {G_SIGNIN}. Google says the app is not verified - it is yours: Advanced → Go to Taskuary, and leave the boxes ticked.
      An External client still in Testing is signed out every 7 days; Audience → <b>Publish app</b> ends that.</li>
  </Box>
);

export function GoogleCalendar({ conn, cfg, reload, flush, onSignedIn, children }) {
  const [flow, setFlow] = useState(null);      // {flow, url, at}
  const [state, setState] = useState("");      // "" | ok | error
  const [detail, setDetail] = useState("");
  const [busy, setBusy] = useState(false);
  const signedIn = saved(conn, "google_refresh_token") || !!cfg.google_refresh_token;
  const [st, setSt] = useState(null);          // the server's word (googlecal.state): {available, connected, lapsed, again, said}
  const base = `/api/connectors/${conn.ConnectorId}/google/calendar`;
  // asked again whenever what it is read from changes: the client's two boxes saving, a sign-in landing, a poll's error coming or going
  const read = [signedIn, cfg.google_client_id || "", saved(conn, "google_client_secret"), conn.HasSecret, conn.LastError || "", state].join("|");
  useEffect(() => {
    let alive = true;
    api.get(base).then(({ data }) => { if (alive) setSt(data); }).catch(() => {});
    return () => { alive = false; };
  }, [base, read]);
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
          setFlow(null); setState("error"); setDetail(`The sign-in was not finished in ten minutes, so this stopped waiting. Press ${G_SIGNIN} to start a fresh one.`);
          return;
        }
        if (data.status === "pending") { setTimeout(tick, 2000); return; }
        setFlow(null); setState(data.status === "ok" ? "ok" : "error"); setDetail(data.detail || "the sign-in did not complete");
        if (data.status === "ok") { reload?.(); onSignedIn?.(); }
      } catch (e) { if (!alive) return; setFlow(null); setState("error"); setDetail(e?.response?.data?.detail || "the sign-in did not complete"); }
    };
    const id = setTimeout(tick, 2000);
    return () => { alive = false; clearTimeout(id); };
  }, [flow, base, reload]);   // eslint-disable-line react-hooks/exhaustive-deps
  const again = signedIn && !!st?.again, can = !!st?.available;
  // signed in and nothing to do: one quiet line saying what the sign-in covers and which road the mail is on - and what the search skips
  if (signedIn && !again && !flow && state !== "error") {
    const said = state === "ok" ? `✓ ${detail}` : st?.said;
    if (!said && !conn.PeopleMissing?.length) return null;
    return (
      <Box data-tq-google-signed-in="" sx={{ mb: 2, display: "flex", flexDirection: "column", gap: 0.25 }}>
        {said && <Typography variant="caption" sx={{ color: state === "ok" ? "var(--tq-success, #47654a)" : DIM, fontWeight: state === "ok" ? 600 : 400 }}>{said}</Typography>}
        {!!conn.PeopleMissing?.length && <Typography data-tq-google-people="" variant="caption" sx={{ color: DIM }}>{PEOPLE_MISSING("this account's Google contacts")}</Typography>}
      </Box>
    );
  }
  const start = async () => {
    setBusy(true); setState(""); setDetail("");
    try {
      await flush?.();     // the client's two boxes, typed a moment ago, are on the card before Google is asked with them
      const { data } = await api.post(base); setFlow({ ...data, at: Date.now() }); window.open(data.url, "_blank", "noopener");
    } catch (e) { setState("error"); setDetail(e?.response?.data?.detail || "could not start the sign-in"); }
    setBusy(false);
  };
  // the two boxes count once typed: the server's word is from before this press saves them
  const typed = !!String(cfg.google_client_id || "").trim() && (saved(conn, "google_client_secret") || !!cfg.google_client_secret);
  return (
    <Box data-tq-google-calendar="" sx={{ mb: 2, p: 1.5, border: `1px solid ${BORDER}`, borderRadius: 2, bgcolor: PANEL2, display: "flex", flexDirection: "column", gap: 1 }}>
      <Typography sx={{ fontWeight: 600, fontSize: 13, color: INK }}>{G_SIGNIN}</Typography>
      {again ? <Typography variant="body2" role="alert" data-tq-google-again="" sx={{ color: "var(--tq-danger, #6b2733)", fontWeight: 600 }}>{st.said}</Typography> : (
        <Typography variant="caption" sx={{ color: DIM, lineHeight: 1.5 }}>
          One sign-in brings this account's mail, calendar and contacts: invites are answered and meetings set up from here, and no App
          Password is needed. Prefer the App Password? It still works under Credentials, for mail alone.
        </Typography>
      )}
      {st && !can && !typed && <>
        <Typography variant="caption" sx={{ color: INK, lineHeight: 1.5 }}>
          It signs in through a Google client of your own - Taskuary ships none, so Google shows your own name on it.
          About five minutes, once:
        </Typography>
        <ClientSteps />
      </>}
      <Box data-tq-google-client="" sx={{ display: "flex", flexDirection: "column", gap: 1.25, pt: 0.5 }}>{children}</Box>
      {state === "ok" ? null : flow ? (
        <Typography variant="caption" sx={{ color: DIM, display: "flex", alignItems: "center", gap: 0.75, flexWrap: "wrap" }}>
          <CircularProgress size={11} /> Finish in the Google tab that opened - this card completes by itself.
          <a href={flow.url} target="_blank" rel="noreferrer">Open it again</a>
          <Button size="small" onClick={() => { api.post(`${base}/cancel`, { flow: flow.flow }).catch(() => {}); setFlow(null); setState(""); setDetail(""); }}
            sx={{ fontSize: 11.5, color: DIM }}>Cancel</Button>
        </Typography>
      ) : (
        <Box><Button variant="contained" disableElevation disabled={busy || !(can || typed)} onClick={start}>
          {busy ? <CircularProgress size={14} sx={{ color: "#fff" }} /> : again ? "Sign in again" : G_SIGNIN}</Button></Box>
      )}
      {detail && <Typography variant="body2" role={state === "ok" ? undefined : "alert"} sx={{ fontWeight: 600, color: state === "ok" ? "var(--tq-success, #47654a)" : "var(--tq-danger, #6b2733)" }}>
        {state === "ok" ? "✓" : "✗"} {detail}</Typography>}
    </Box>
  );
}
