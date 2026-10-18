// ONE FAILURE SHAPE ON THE PAGE (failures.py, 2026-10-18): a card's failed press printed the raw sentence and nothing to press - a
// fix the server named (Connect a mailbox, Sign in again, Connect a coding tool) was dropped on the floor. `failOf` keeps the
// sentence and the record's fix; `CardErr` draws them: the fix as a button that opens its place, else Report this bug.
import React from "react";
import { openAppLink } from "./appLinks.js";
import { openBugReport, shownError } from "./bugReportOpen.js";
import { label } from "./buttons.js";
import { errText } from "./gameItem.jsx";

export const failOf = (e) => {
  const fix = e?.outcome?.fix || e?.response?.data?.fix;
  const retry = e?.outcome?.retry ?? e?.response?.data?.retry;
  return { text: errText(e), fix: fix?.href && fix?.label ? fix : null, retry: retry === true };
};

// ...and the ways past it as buttons, for a surface that draws its own sentence (the task page's error line): the fix, else Try again
// where the failure says a retry could work, else Report this bug - a start that failed on the task page showed the sentence alone
export function FailWays({ fail, onRetry }) {
  if (!fail || (!fail.fix && !fail.text)) return null;
  return <span style={{ display: "inline-flex", gap: 6, marginLeft: 8, flexWrap: "wrap" }}>
    {fail.fix
      ? <button type="button" className="tq-chip primary" onClick={() => openAppLink(fail.fix.href)}>{fail.fix.label}</button>
      : fail.retry && onRetry
        ? <button type="button" className="tq-chip" onClick={onRetry}>{label("try_again")}</button>
        : <button type="button" className="tq-chip" onClick={() => openBugReport(shownError(fail.text))}>{label("report_bug")}</button>}
  </span>;
}

// `bug={false}` where the card draws its own Report this bug (a connection's check, once it is stuck)
export function CardErr({ err, className = "tq-card-err", bug = true }) {
  if (!err) return null;
  const { text, fix } = typeof err === "string" ? { text: err, fix: null } : err;
  return <div className={className}>{text}
    <div style={{ marginTop: 6 }}>
      {fix
        ? <button type="button" className="tq-chip primary" onClick={() => openAppLink(fix.href)}>{fix.label}</button>
        : bug && <button type="button" className="tq-chip" onClick={() => openBugReport(shownError(text))}>{label("report_bug")}</button>}
    </div></div>;
}
