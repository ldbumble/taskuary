// A KNOB THAT IS A LIST, one entry a line (settings_schema.json type "lines") - first for "Folders agents may look in for code"
// (repochoice.py, the owner 2026-11-06). A blank setting means the shipped list, so the box shows that list rather than an empty one:
// what the owner reads is what the agent may open. Saved on leaving the box, trimmed; emptied, it goes back to the shipped list.
import React, { useEffect, useState } from "react";
import { TextField, Typography } from "@mui/material";
import { FAINT } from "./theme.jsx";

export const lines = (s) => String(s || "").split(/\r?\n|;/).map((x) => x.trim()).filter(Boolean);

export default function LinesSetting({ value = "", fallback = "", save }) {
  const shown = (value || fallback || "").trim();
  const [text, setText] = useState(shown);
  useEffect(() => { setText(shown); }, [shown]);
  const leave = () => {
    const v = lines(text).join("\n");
    // ...the shipped list typed back unchanged stays "the shipped list", so it follows the machine as folders come and go
    const next = v === lines(fallback).join("\n") ? "" : v;
    if (next !== (value || "")) save(next);
    setText(next || lines(fallback).join("\n"));
  };
  return (
    <div style={{ minWidth: 260, maxWidth: 420 }}>
      <TextField multiline minRows={2} maxRows={8} fullWidth value={text} onChange={(e) => setText(e.target.value)} onBlur={leave}
        placeholder="One folder a line" sx={{ bgcolor: "var(--tq-panel, #fff)" }} inputProps={{ "aria-label": "one folder a line", style: { fontSize: 12.5, fontFamily: "monospace" } }} />
      {!value && <Typography variant="caption" sx={{ color: FAINT, display: "block", mt: 0.25 }}>The usual places on this computer - change them here.</Typography>}
    </div>
  );
}
