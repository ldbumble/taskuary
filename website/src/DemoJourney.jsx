// The static demo uses the application's agent workspace and approval card against the same
// in-memory task the Timeline shows. No account, AI, database, or delivery is connected.
import React, { useEffect, useRef, useState } from "react";
import { Alert, Box, Button, CircularProgress, Typography } from "@mui/material";
import api from "./api.js";
import { DEMO_GUIDED, demoJourneySnapshot, onDemoJourney } from "./demoApi.js";
import { NUMBERS_REQUEST, NUMBERS_TASK } from "./demoNumbers.js";
import GeneralWorkspace from "./GeneralWorkspace.jsx";
import ReviewDecision from "./ReviewDecision.jsx";
import { Md } from "./md.jsx";
import { BORDER, DIM, INK, PANEL, PANEL2 } from "./theme.jsx";

export default function DemoJourney({ onChanged }) {
  const [journey, setJourney] = useState(demoJourneySnapshot);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState("");
  const changed = useRef(onChanged);
  changed.current = onChanged;
  useEffect(() => {
    if (!DEMO_GUIDED) return undefined;
    setJourney(demoJourneySnapshot());
    return onDemoJourney((next) => { setJourney(next); changed.current?.(); });
  }, []);
  if (!DEMO_GUIDED) return null;
  const phase = journey.phase;
  const step = phase === "request" ? 0 : phase === "working" ? 1 : 2;
  const start = async () => {
    setStarting(true); setError("");
    try { await api.post(`/api/tasks/${NUMBERS_TASK}/dispatch`, { agent: "analyst" }); }
    catch (e) { setError(e?.response?.data?.detail || "The demo could not start. Try again."); }
    finally { setStarting(false); }
  };
  return (
    <Box data-tq-demo-journey={phase} sx={{ maxWidth: 1120, mx: "auto", mb: 2, border: `1px solid ${BORDER}`, borderRadius: 2,
      bgcolor: PANEL, p: { xs: 1.5, md: 2.5 }, color: INK }}>
      <Box sx={{ display: "flex", flexWrap: "wrap", alignItems: "baseline", gap: 1, mb: 1 }}>
        <Typography component="h1" sx={{ fontSize: { xs: 20, md: 24 }, fontWeight: 600 }}>Try one request</Typography>
        <Typography sx={{ fontSize: 12, color: DIM }}>Scripted demo · fictional data · nothing sends or connects</Typography>
      </Box>
      <Box component="ol" aria-label="Demo steps" sx={{ listStyle: "none", m: 0, p: 0, display: "flex", flexWrap: "wrap", gap: 1.5, mb: 2 }}>
        {["Read the request", "Check the result", "Approve the reply"].map((label, i) => (
          <Box component="li" key={label} aria-current={i === step && phase !== "complete" ? "step" : undefined}
            sx={{ fontSize: 12, fontWeight: i === step ? 700 : 500, color: i <= step ? INK : DIM }}>
            {i < step || phase === "complete" ? "✓" : i + 1} · {label}
          </Box>
        ))}
      </Box>
      {phase === "request" && <>
        <Typography sx={{ fontWeight: 600, fontSize: 14 }}>Ruth asks for the latest vendor spend numbers</Typography>
        <Typography sx={{ fontSize: 13, color: DIM, my: 1, maxWidth: 760 }}>{NUMBERS_REQUEST}</Typography>
        <Typography sx={{ fontSize: 12, color: DIM, mb: 1.5 }}>The task already has her request. Let the demo analyst prepare a sourced answer and a draft for you to review.</Typography>
        <Button variant="contained" disableElevation disabled={starting} onClick={start}>
          {starting ? "Starting…" : "Start demo agent"}
        </Button>
      </>}
      {phase === "working" && <>
        <Typography role="status" sx={{ fontSize: 13, mb: 1.5, display: "flex", gap: 1, alignItems: "center" }}>
          <CircularProgress size={14} /> Preparing the fictional report and checking its totals…
        </Typography>
        <Box sx={{ height: { xs: 360, md: 420 }, minWidth: 0 }}><GeneralWorkspace task={journey.task} compact /></Box>
      </>}
      {phase === "review" && <>
        <Typography sx={{ fontSize: 14, fontWeight: 600, mb: 1.5 }}>The result is ready. Check its evidence, edit the reply, then simulate approval.</Typography>
        <Box sx={{ display: "grid", gridTemplateColumns: { xs: "minmax(0, 1fr)", md: "minmax(0, 1fr) minmax(0, 1fr)" }, gap: 2 }}>
          <Box sx={{ minWidth: 0, p: 1.5, bgcolor: PANEL2, borderRadius: 1.5 }} data-tq-demo-result=""><Md text={journey.result} /></Box>
          <Box sx={{ minWidth: 0 }} data-tq-demo-review=""><ReviewDecision review={journey.review} simulated
            onChanged={() => setJourney(demoJourneySnapshot())} onSent={() => setJourney(demoJourneySnapshot())} /></Box>
        </Box>
      </>}
      {phase === "complete" && <Box role="status" data-tq-demo-outcome="">
        <Typography sx={{ fontSize: 18, fontWeight: 600 }}>Request finished in this demo.</Typography>
        <Typography sx={{ fontSize: 13, my: 1 }}>You reviewed the checked numbers and approved the reply. The fictional task is done. No email was sent.</Typography>
        <Box component="details" sx={{ fontSize: 12, color: DIM, mb: 1.5 }}><summary>Your approved demo reply</summary>
          <Typography sx={{ fontSize: 12, whiteSpace: "pre-wrap", mt: 1 }}>{journey.review?.FinalText}</Typography>
        </Box>
        <Button component="a" href="https://taskuary.com/docs/" variant="contained" disableElevation>Set up your own inbox</Button>
        <Button component="a" href="?demo=explore" sx={{ ml: 1 }}>Explore the full demo</Button>
        <Button component="a" href="?workflow=numbers">Try again</Button>
      </Box>}
      {error && <Alert severity="error" sx={{ mt: 1 }}>{error}</Alert>}
      {phase !== "complete" && <Typography sx={{ mt: 1.5, fontSize: 11.5, color: DIM }}>
        This page simulates the workflow. Reload to reset it. <a href="?demo=explore">Explore the full demo</a> · <a href="https://taskuary.com/docs/">Install and connect your own inbox</a>
      </Typography>}
    </Box>
  );
}
