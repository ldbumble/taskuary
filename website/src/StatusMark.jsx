// A ROW'S STATUS ON ITS ICON, AND THE TASK PAGE'S STATUS PILL - one drawing for both (railStatus.js says what; this draws it): the
// source's logo with the state built in - the spinning ring while an agent works (the owner loves it, 2026-10-21), else the lane's own
// mark as a small badge on the logo, waving or turning where that says something. Readable without colour or motion: the state's words
// are the icon's label, and with reduced motion the ring holds still and no badge moves.
import React from "react";
import { statusLabel } from "./railStatus.js";
import "./statusMark.css";

// the logo with its state: `status` from railStatus/taskStatus, `children` the source's logo
export function StatusLogo({ status, agent = "", className = "", children }) {
  const st = status, spins = !!st?.spins, badge = !spins && st?.mark && st.mark !== "spinner" ? st.mark : "";
  return (
    <span className={["tq-mark", className, spins ? "spins" : ""].filter(Boolean).join(" ")} data-tq-working={spins ? "" : undefined}
      data-tq-status={st?.key || undefined} role={st ? "img" : undefined} aria-label={st ? statusLabel(st, agent) : undefined}
      title={st ? statusLabel(st, agent) : undefined}>
      {children}
      {badge && <i className={`badge${st.anim ? ` ${st.anim}` : ""}`} aria-hidden="true">{badge}</i>}
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
        ? <StatusLogo status={status} agent={agent}>{logo}</StatusLogo>
        : <i className="mark" aria-hidden="true">{status.mark !== "spinner" ? status.mark : ""}</i>}
      <span className="word">{status.word}</span>
    </span>
  );
}
