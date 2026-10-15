// SETUP MODE'S RAIL (the owner, 2026-10-15: "it should be a distinct setup mode vs regular operations mode"): while setting up, the
// left column is the steps - what is done, what is next - not the mail. A step pressed takes the canvas back to it (FirstRun listens
// for tq-setup-go). Read from the first run's own state, again whenever a step moves (tq-setup-changed).
import React, { useEffect, useState } from "react";
import { Box, Typography } from "@mui/material";
import api from "./api";
import { DIM, FAINT, INK } from "./theme.jsx";
import { stepsOf } from "./setupSteps.js";

export default function SetupSteps() {
  const [st, setSt] = useState(null);
  useEffect(() => {
    let on = true;
    const read = () => api.get("/api/setup/first-run").then(({ data }) => on && setSt(data)).catch(() => {});
    read(); window.addEventListener("tq-setup-changed", read);
    const id = setInterval(read, 8000);                 // the mail being read moves "Finish" from sorting to ready on its own
    return () => { on = false; window.removeEventListener("tq-setup-changed", read); clearInterval(id); };
  }, []);
  const go = (key) => window.dispatchEvent(new CustomEvent("tq-setup-go", { detail: key }));
  return (
    <Box data-tq-setup-steps="" sx={{ pt: 1.5, px: 0.5 }}>
      <Typography sx={{ fontSize: 11, fontWeight: 700, letterSpacing: ".06em", color: FAINT, textTransform: "uppercase", mb: 1, px: 1 }}>
        Setting up Taskuary</Typography>
      {stepsOf(st).map((r, i) => (
        <Box key={r.key} component="button" type="button" onClick={() => go(r.key)} data-tq-setup-step={r.key}
          sx={{ display: "flex", alignItems: "flex-start", gap: 1.1, width: "100%", textAlign: "left", border: 0, cursor: "pointer",
            fontFamily: "inherit", borderRadius: "8px", px: 1, py: 0.9, bgcolor: r.current ? "#e4e9ee" : "transparent",
            "&:hover": { bgcolor: r.current ? "#e4e9ee" : "#efebe3" } }}>
          <Box sx={{ width: 20, height: 20, borderRadius: "50%", flexShrink: 0, display: "grid", placeItems: "center", fontSize: 11, fontWeight: 700,
            color: r.done ? "#fff" : r.current ? INK : FAINT, bgcolor: r.done ? "#47654a" : "transparent",
            border: r.done ? "none" : `1.5px solid ${r.current ? INK : "#cfc9bf"}` }}>{r.done ? "✓" : i + 1}</Box>
          <Box sx={{ minWidth: 0 }}>
            <Typography sx={{ fontSize: 13, fontWeight: r.current ? 700 : 600, color: r.done || r.current ? INK : DIM }}>{r.label}</Typography>
            {r.sub && <Typography sx={{ fontSize: 11.5, color: FAINT }}>{r.sub}</Typography>}
          </Box>
        </Box>
      ))}
    </Box>
  );
}
