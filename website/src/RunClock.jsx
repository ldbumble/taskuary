import React, { useEffect, useState } from "react";
import { IconButton } from "@mui/material";
import CloseIcon from "@mui/icons-material/Close";
import { elapsedText } from "./agentWork.js";
import { dayLabel, fmtTime12 } from "./dates.js";

// A chat's time: its day where it is not today, and the time
export const when = (at) => {
  if (at instanceof Date) { const y = at.getFullYear(), p = (n) => String(n).padStart(2, "0");
    at = `${y}-${p(at.getMonth() + 1)}-${p(at.getDate())} ${p(at.getHours())}:${p(at.getMinutes())}:${p(at.getSeconds())}`; }
  const d = dayLabel(at); return [d && d !== "Today" ? d : "", fmtTime12(at)].filter(Boolean).join(" ");
};

// THE TURN'S HEAD, FROM THE PRESS: its time and how long it has run, counting - the same element before the agent's first word and after it
// ...and the ONE way to stop an agent mid-run, on the turn it stops (the owner, 2026-11-10: "we should have x button for agent to stop in middle
// of the work"): the chat's own stop road (onStop), nothing else
export const StopCtx = React.createContext(null);
// ...`start` null (a turn the list gave no start - the server always sends one; this is the defensive road): no time is claimed. The moment it
// was drawn read as the turn's start, and the count began again at 0s on every render, and again on every return to the task
// ...the start a turn of the list gives its clock (ms), or null
export const turnStart = (t) => (t?.started ? t.started * 1000 : null);
export const RunClock = ({ start }) => {
  const [now, setNow] = useState(() => Date.now()), stop = React.useContext(StopCtx);
  useEffect(() => { const t = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(t); }, []);
  return <span data-tq-ran="" data-tq-run-clock="" style={{ textTransform: "none", letterSpacing: 0, fontWeight: 500, marginLeft: 8 }}>
    {start == null ? "· working" : `· ${when(new Date(start))} · working ${elapsedText(Math.max(0, now - start))}`}
    {stop && <IconButton size="small" data-tq-stop-run="" aria-label="Stop the agent" title="Stops this turn - the chat stays, and what you type next carries on"
      onClick={stop} sx={{ ml: 0.5, p: 0.25, verticalAlign: "-3px" }}><CloseIcon sx={{ fontSize: 13 }} /></IconButton>}</span>;
};
