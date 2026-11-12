// SET UP WITH AI IS A DOOR TO THE CHAT (the owner, 2026-10-30: "the AI box on top of report/dashboard setup goes away; those buttons open the
// corner chat window with that setup as its subject"). Where "Describe the report you want" stood, one outlined button: it brings up the
// empty builder - the page's own New - and opens the chat asking for it. The Assistant fills the builder there, a step at a time in the
// chat (pageView.js): its describe-it runs the same composer the box ran (ReportsView's view extras), Preview is its to press, Save the owner's.
import React from "react";
import { Button } from "@mui/material";
import AutoAwesomeIcon from "@mui/icons-material/AutoAwesome";
import { openHelp } from "./pageView.js";
import { openAppLink } from "./appLinks.js";
import { firstPressOf, goesStraight } from "./newTask.js";

export const NEW_HASH = { report: "report=new", dashboard: "report=new-dashboard", workflow: "report=new-agent" };
const WHAT = { report: "a new report", dashboard: "a new dashboard", workflow: "a new routine" };
export const helpAsk = (kind, words = "") => `Help me set up ${WHAT[kind] || WHAT.report}${String(words || "").trim() ? `: ${String(words).trim()}` : ""}`;

// its press: the builder brought up (`onOpen`), and the chat asked for it with the owner's words - New's straight road presses this same one
export const startSetup = (kind, words, onOpen) => { onOpen?.(); openHelp(helpAsk(kind, words), { wait: 700 }); };
// STRAIGHT INTO THE BUILDER (owner-approved, 2026-11-12): a report, dashboard or routine the Assistant wrote up (`made`, concierge._new) - from
// New's box or from the chat - opens its builder with the setup asked there, this press made once per line; the middle card's Set up with AI
// asked the Assistant it all again. True when it went (`onOpen`: what the door shuts first, New's card); false leaves the caller its card
export const goStraight = (made, onOpen) => {
  if (!goesStraight(made?.kind, made?.line)) return false;
  if (firstPressOf(made.line)) startSetup(made.kind, made.text || "", () => { onOpen?.(); openAppLink(NEW_HASH[made.kind]); });
  return true;
};

// ...and out of the view the Assistant is sent (data-tq-view-skip, the owner, 2026-11-02): it opens the Assistant itself, so a press from the
// chat would only ask the chat again
export default function SetupWithAi({ kind = "report", onOpen, words = "", sx = {} }) {
  return (
    <Button size="small" variant="outlined" disableElevation data-tq-setup-ai={kind} data-tq-view-skip="" startIcon={<AutoAwesomeIcon sx={{ fontSize: 15 }} />}
      title="Opens the chat - the Assistant sets it up with you in the builder; saving stays yours"
      onClick={() => startSetup(kind, words, onOpen)} sx={{ alignSelf: "flex-start", ...sx }}>
      Set up with AI
    </Button>
  );
}
