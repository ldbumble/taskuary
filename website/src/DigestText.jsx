import React from "react";
import { Alert, Box, Typography } from "@mui/material";
import { parseDigest } from "./digestText.js";

const URL = /(https?:\/\/[^\s<>"')\]]+)/g;
const Linked = ({ children }) => String(children || "").split(URL).map((part, i) =>
  /^https?:\/\//.test(part)
    ? <a key={i} href={part} target={/#task=\d+/.test(part) ? undefined : "_blank"} rel="noreferrer"
        style={{ color: "#526978", fontWeight: 650, textDecoration: "none" }}
        onClick={(e) => { const hit = /#task=(\d+)/.exec(part); if (hit) { e.preventDefault(); window.location.hash = `task=${hit[1]}`; } }}>
        {/#task=(\d+)/.test(part) ? `open TQ-${String(/#task=(\d+)/.exec(part)[1]).padStart(4, "0")} →` : part}
      </a>
    : <React.Fragment key={i}>{part}</React.Fragment>);

const Sections = ({ sections }) => <Box sx={{ display: "grid", gap: 1.25 }}>
  {sections.map((section) => <Box component="section" key={section.title}
    sx={{ border: "1px solid #e1ddd5", borderRadius: 2, bgcolor: "#fff", overflow: "hidden" }}>
    <Typography component="h3" sx={{ m: 0, px: 1.35, py: 0.85, bgcolor: "#f5f2ec",
      borderBottom: "1px solid #e6e0d7", color: "#343832", fontSize: 13, fontWeight: 760 }}>
      {section.title}
    </Typography>
    <Box component="ol" sx={{ m: 0, py: 1, pl: 4.25, pr: 1.4, color: "#393b37",
      "& li": { pl: 0.35, mb: 0.7, fontSize: 12.5, lineHeight: 1.55, whiteSpace: "pre-wrap" },
      "& li:last-of-type": { mb: 0 }, "& li::marker": { color: "#718775", fontWeight: 750 } }}>
      {section.items.map((item, i) => <li key={`${section.title}-${i}`}><Linked>{item}</Linked></li>)}
    </Box>
  </Box>)}
</Box>;

export default function DigestText({ text }) {
  const digest = parseDigest(text);
  return <Box sx={{ textAlign: "left" }}>
    {digest.error && <Alert severity="error" variant="outlined" sx={{ mb: 1.25, alignItems: "flex-start",
      bgcolor: "#fff8f5", borderColor: "#e6bcb2", "& .MuiAlert-message": { width: "100%" } }}>
      <Typography sx={{ fontSize: 13, fontWeight: 780, mb: 0.35 }}>🚨 Errors</Typography>
      <Box component="ol" sx={{ m: 0, pl: 2.25, "& li": { fontSize: 12.25, lineHeight: 1.5 } }}>
        <li>The AI could not write this morning’s digest. {digest.error}</li>
      </Box>
    </Alert>}
    {digest.meta && <Typography variant="caption" sx={{ display: "block", color: "#817b72", mb: 1 }}>
      {digest.meta}
    </Typography>}
    {!digest.error && <Sections sections={digest.sections} />}
    {digest.error && digest.sections.length > 0 && <Box component="details" sx={{ mt: 0.75,
      "& summary": { cursor: "pointer", color: "#65766a", fontSize: 12, fontWeight: 700, py: 0.5 },
      "&[open] summary": { mb: 0.75 } }}>
      <summary>Show unreviewed source data</summary>
      <Typography variant="caption" sx={{ display: "block", color: "#817b72", mb: 0.8 }}>
        The AI did not judge or summarize these items. They are grouped only to make the source readable.
      </Typography>
      <Sections sections={digest.sections} />
    </Box>}
  </Box>;
}

