// SETUP MODE'S RAIL (the owner, 2026-10-15: "it should be a distinct setup mode vs regular operations mode"): while setting up, the
// steps are what is done and what is next - not the mail. A step pressed takes the canvas back to it (FirstRun listens for tq-setup-go).
// Read from the first run's own state, again whenever a step moves (tq-setup-changed).
import React, { useEffect, useState } from "react";
import { Box, Typography } from "@mui/material";
import CheckIcon from "@mui/icons-material/Check";
import { onFirstRun, readFirstRun } from "./firstRunState.js";
import { DIM, FAINT, INK } from "./theme.jsx";
import { stepsOf } from "./setupSteps.js";

export default function SetupSteps() {
  const [st, setSt] = useState(null), [shown, setShown] = useState(() => window.__tqSetupShown || "");
  useEffect(() => {
    const on = (e) => setShown(e.detail || "");
    window.addEventListener("tq-setup-shown", on);
    return () => window.removeEventListener("tq-setup-shown", on);
  }, []);
  useEffect(() => {
    // setup's one shared read (firstRunState.js): the canvas reads every few seconds and the rail draws each answer it takes - its own
    // eight-second read only goes out when nobody has asked lately (the overnight setup walk, 2026-10-26)
    const off = onFirstRun(setSt), read = () => readFirstRun().catch(() => {});
    readFirstRun(3000).then(setSt).catch(() => {}); window.addEventListener("tq-setup-changed", read);
    const id = setInterval(() => readFirstRun(7000).catch(() => {}), 8000);   // the mail being read moves "Finish" from sorting to ready on its own
    return () => { off(); window.removeEventListener("tq-setup-changed", read); clearInterval(id); };
  }, []);
  const go = (key) => window.dispatchEvent(new CustomEvent("tq-setup-go", { detail: key }));
  // A STRIP ACROSS THE SETUP SCREEN'S TOP, not a column beside it (the owner, 2026-11-03: "the welcome screen should take up the entire screen"):
  // each step a bar - done, here, still to come - its name and where it stands under it; on a phone the bars alone, and the step you are on in words
  const rows = stepsOf(st, shown), at = rows.findIndex((r) => r.current);
  const tone = (r) => (r.done ? "#47654a" : r.current ? INK : "#e2ddd3");
  return (
    <Box component="nav" aria-label="Setup steps" data-tq-setup-steps="" sx={{ flexShrink: 0, mb: 1.25, px: { xs: 0.5, sm: 0 } }}>
      {at >= 0 && <Typography sx={{ display: { xs: "block", sm: "none" }, fontSize: 12.5, color: DIM, mb: 0.75 }} data-tq-setup-at="">
        Step {at + 1} of {rows.length} · <b style={{ color: INK }}>{rows[at].label}</b></Typography>}
      <Box sx={{ display: "grid", gridTemplateColumns: `repeat(${rows.length || 1}, minmax(0, 1fr))`, gap: { xs: 0.5, sm: 1.25 } }}>
        {rows.map((r, i) => (
          <Box key={r.key} component="button" type="button" onClick={() => go(r.key)} data-tq-setup-step={r.key} disabled={!!r.disabled}
            aria-current={r.current ? "step" : undefined} aria-label={`${i + 1}. ${r.label}${r.done ? " - done" : ""}`}
            sx={{ display: "flex", flexDirection: "column", justifyContent: "flex-start", minWidth: 0, textAlign: "left", border: 0, bgcolor: "transparent", p: 0, pb: 0.25, fontFamily: "inherit",
              cursor: r.disabled ? "default" : "pointer", opacity: r.disabled ? 0.65 : 1, borderRadius: "4px",
              "&:hover:not(:disabled) .tq-step-name": { color: INK }, "&:focus-visible": { outline: "2px solid #55697a", outlineOffset: 3 } }}>
            <Box sx={{ height: 3, borderRadius: 2, bgcolor: tone(r), mb: { xs: 0, sm: 0.75 } }} />
            <Box sx={{ display: { xs: "none", sm: "block" }, minWidth: 0 }}>
              <Typography noWrap className="tq-step-name" sx={{ fontSize: 12.5, fontWeight: r.current ? 700 : 600, color: r.done || r.current ? INK : DIM }}>
                {r.done && <CheckIcon sx={{ fontSize: 13, color: "#47654a", mr: 0.4, verticalAlign: "-2px" }} />}{r.label}</Typography>
              {r.sub && <Typography noWrap sx={{ fontSize: 11, color: FAINT }} title={r.sub}>{r.sub}</Typography>}
            </Box>
          </Box>
        ))}
      </Box>
    </Box>
  );
}
