// COPY IN THE CORNER (the owner, 2026-11-05: "should have added copy button on corner for text stuff to copy"): a quiet icon at the top right of
// a block worth copying - an answer of the agent's, a code block - shown on hover as other chat apps do, a tick for a moment once copied. No row
// of its own: it sits over the block's corner. `text` is a string or a function read at the press (a code block's own text).
import React, { useEffect, useState } from "react";
import ContentCopyIcon from "@mui/icons-material/ContentCopy";
import DoneIcon from "@mui/icons-material/DoneRounded";
import { label as btn } from "./buttons.js";
import "./copyCorner.css";

export const copyText = (s) => Promise.resolve().then(() => navigator.clipboard.writeText(String(s || "")));   // no clipboard API: a rejection, not a throw

export default function CopyCorner({ text, label = btn("copy") }) {
  const [done, setDone] = useState(false);
  useEffect(() => { if (!done) return undefined; const t = setTimeout(() => setDone(false), 1500); return () => clearTimeout(t); }, [done]);
  const press = (e) => {
    e.preventDefault(); e.stopPropagation();
    copyText(typeof text === "function" ? text() : text).then(() => setDone(true), () => {});
  };
  return (
    <button type="button" className={`tq-copy${done ? " tq-copy-done" : ""}`} data-tq-copy="" onClick={press} aria-label={done ? btn("copy", "done") : label} title={done ? btn("copy", "done") : label}>
      {done ? <DoneIcon sx={{ fontSize: 14 }} /> : <ContentCopyIcon sx={{ fontSize: 13 }} />}
    </button>
  );
}
