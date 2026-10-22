// A ROW'S STATUS ON ITS ICON, AND THE TASK PAGE'S STATUS PILL - one reading for both (railStatus.js says what; this draws it). On the
// rail the RING round the source's logo says the state (the owner, 2026-10-22: "The spinning thing around is good. Don't spin the whole
// thing, just the circle around it"): the logo stays exactly as it is, and each state is a ring of its own shape in the pill's colour -
// spinning while an agent works, breathing while somebody waits on you, solid when ready to send, half when stopped, broken when it
// failed, dotted while it waits to start (railStatus.RING, statusMark.css). Readable without colour or motion: the shapes differ, and
// the state's words are the icon's label and hover.
import React from "react";
import { statusLabel } from "./railStatus.js";
import "./statusMark.css";

// the logo with its state: `status` from railStatus/taskStatus, `children` the source's logo. `wears` - the ring says the state (the
// rail); without it only an agent at work rings it (the header pill, unchanged). `progress` (0..1) - a goal's ring fills as its steps
// are done, in the bad ink when it slipped (`status` then only colours it)
export function StatusLogo({ status, agent = "", className = "", wears = true, progress = null, children }) {
  const st = status, spins = !!st?.spins, goal = progress != null;
  const ring = goal ? "progress" : wears && st ? st.ring || "none" : "";
  const said = st && !goal ? statusLabel(st, agent) : undefined;
  return (
    <span className={["tq-mark", className, spins && !goal ? "spins" : "", ring && !["none", "spin"].includes(ring) ? `rg-${ring}` : "",
      st?.role && wears ? `rl-${st.role}` : ""].filter(Boolean).join(" ")}
      style={goal ? { "--p": Math.round(Math.max(0, Math.min(1, progress)) * 100) } : undefined}
      data-tq-working={spins && !goal ? "" : undefined} data-tq-status={!goal && st?.key || undefined} data-tq-ring={ring || undefined}
      role={said ? "img" : undefined} aria-label={said} title={said}>
      {children}
    </span>
  );
}

// THE TASK HEADER'S STATUS, top right: exactly the rail's mark and word for this task - its logo ringed while an agent works
export function StatusPill({ status, logo = null, agent = "", note = "" }) {
  if (!status) return null;
  const title = [status.hint, note].filter(Boolean).join(" ");
  return (
    <span className={`tq-status-pill role-${status.role || "none"}`} data-tq-status-pill={status.key} title={title || undefined}>
      {status.spins
        ? <StatusLogo status={status} agent={agent} wears={false}>{logo}</StatusLogo>
        : <i className="mark" aria-hidden="true">{status.mark !== "spinner" ? status.mark : ""}</i>}
      <span className="word">{status.word}</span>
    </span>
  );
}
