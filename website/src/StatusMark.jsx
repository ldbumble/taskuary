// A ROW'S STATUS ON ITS ICON, AND THE TASK PAGE'S STATUS PILL - one drawing for both (railStatus.js says what; this draws it): the
// source's logo with the state built in - the spinning ring while an agent works (the owner loves it, 2026-10-21), else the lane's own
// hand (waving) or flag as a small badge on the logo where the move is the owner's, and the plain logo for the rest (railStatus.BADGE).
// Readable without colour or motion: the state's words are the icon's label, and with reduced motion the ring holds still and no badge moves.
import React from "react";
import { statusLabel } from "./railStatus.js";
import "./statusMark.css";

// the logo with its state: `status` from railStatus/taskStatus, `children` the source's logo
export function StatusLogo({ status, agent = "", className = "", children }) {
  const st = status, spins = !!st?.spins, badge = !spins && st?.badge || "";
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
  const title = [status.hint, note].filter(Boolean).join(" "), mark = status.mark !== "spinner" ? status.mark : "";
  // ...ON A PHONE THE MARK ALONE (the owner, 2026-10-27): "waiting on them" cut the title to a stub - the word is still in the pill for a
  // screen reader (statusMark.css hides it only from sight), and the hover says it. A state with no mark keeps its word
  return (
    <span className={`tq-status-pill role-${status.role || "none"}${status.spins || mark ? " marked" : ""}`} data-tq-status-pill={status.key}
      title={title || status.word || undefined}>
      {status.spins
        ? <StatusLogo status={status} agent={agent}>{logo}</StatusLogo>
        : <i className="mark" aria-hidden="true">{mark}</i>}
      <span className="word">{status.word}</span>
    </span>
  );
}
