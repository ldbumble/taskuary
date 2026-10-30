// SET UP WITH AI IS A DOOR TO THE CHAT (the owner, 2026-10-30: "the AI box on top of report/dashboard setup goes away; those buttons open the
// corner chat window with that setup as its subject"). Where "Describe the report you want" stood, one outlined button: it brings up the
// empty builder - the page's own New - and opens the chat asking for it. The Assistant fills the builder there, a step at a time in the
// chat (pageView.js): its describe-it runs the same composer the box ran (ReportsView's view extras), Preview is its to press, Save the owner's.
import React from "react";
import { Button } from "@mui/material";
import AutoAwesomeIcon from "@mui/icons-material/AutoAwesome";
import { openHelp } from "./pageView.js";

export const NEW_HASH = { report: "report=new", dashboard: "report=new-dashboard", workflow: "report=new-agent" };
const WHAT = { report: "a new report", dashboard: "a new dashboard", workflow: "a new routine" };
export const helpAsk = (kind, words = "") => `Help me set up ${WHAT[kind] || WHAT.report}${String(words || "").trim() ? `: ${String(words).trim()}` : ""}`;

export default function SetupWithAi({ kind = "report", onOpen, words = "", sx = {} }) {
  return (
    <Button size="small" variant="outlined" disableElevation data-tq-setup-ai={kind} startIcon={<AutoAwesomeIcon sx={{ fontSize: 15 }} />}
      title="Opens the chat - the Assistant sets it up with you in the builder; saving stays yours"
      onClick={() => { onOpen?.(); openHelp(helpAsk(kind, words), { wait: 700 }); }} sx={{ alignSelf: "flex-start", ...sx }}>
      Set up with AI
    </Button>
  );
}
