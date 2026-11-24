// ONE ARTIFACT FOR EVERYTHING A TURN SETS DOWN (the owner, 2026-11-24: "any chart/pdf etc should also be a white artifact; 2 ways to hit the
// same code: either artifact creation or review step"): a file the agent made, a view it drew, and anything it hands him for review - an
// email, a reply, a post, a GitHub comment, a held step, sent or waiting - stand in this one raised frame (appTheme.css .tq-turn-frame).
// `label` is what it is in plain words, over its content; `press` is the row under it - none for a thing made, the press named by what it does
// for a thing to review. What is inside (a picture, a preview, a view's blocks, editable words) is the content's own renderer.
import React from "react";
import { Box } from "@mui/material";
import { INK } from "./theme.jsx";

export default function Artifact({ as = "div", label = null, press = null, wide = false, className = "", sx, children, ...rest }) {
  return (
    <Box component={as} className={`tq-turn-frame${wide ? " tq-turn-wide" : ""}${className ? ` ${className}` : ""}`} sx={sx} {...rest}>
      {label != null && <Box data-tq-artifact-label="" sx={{ fontSize: 13.5, fontWeight: 700, color: INK, lineHeight: 1.3, overflowWrap: "anywhere" }}>{label}</Box>}
      {children}
      {press}
    </Box>
  );
}
