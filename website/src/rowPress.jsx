// A PRESS IS SAID ON THE ROW THAT WAS PRESSED (the owner, 2026-11-20, of Run now on Reports: "it should say running on the card, not on top ...
// fix this as a general fix"): the button turns to "Running…", the row shows that it is at it, and what came of it lands in the row's own line -
// a failure stays on that row with its reason. One road for every row's press (Reports, Dashboards, Routines): no page-top banner says it.
import React, { useCallback, useEffect, useRef, useState } from "react";

const GIVE_UP_MS = 15 * 60 * 1000;      // a run that never lands stops reading as at work - its row's own line still says what it last did

// `landed(key, was)`: has the row's own record moved on from `was` (its last run when pressed)? `reload`: reads the rows again while one is at work
export function useRowPress({ landed, reload, every = 2500 }) {
  const [rows, setRows] = useState({});
  const was = useRef({});
  const start = useCallback((key, before) => { was.current[key] = { before, at: Date.now() }; setRows((r) => ({ ...r, [key]: { state: "running" } })); }, []);
  const fail = useCallback((key, said) => { delete was.current[key]; setRows((r) => ({ ...r, [key]: { state: "failed", said } })); }, []);
  const done = useCallback((key) => { delete was.current[key]; setRows((r) => { const n = { ...r }; delete n[key]; return n; }); }, []);
  const running = (key) => rows[key]?.state === "running";
  const busy = Object.values(rows).some((x) => x.state === "running");
  useEffect(() => {
    if (!busy) return undefined;
    const t = setInterval(() => { reload?.(); }, every);
    return () => clearInterval(t);
  }, [busy, reload, every]);
  // ...each row at work, against its own record: moved on, it is done - its result is the row's own line now
  const check = useCallback(() => {
    for (const [key, w] of Object.entries(was.current)) if (landed(key, w.before) || Date.now() - w.at > GIVE_UP_MS) done(key);
  }, [landed, done]);
  return { rows, start, fail, done, running, check, of: (key) => rows[key] || null };
}

// ...and what the row says of it, under the row's own line: at work while it runs, its reason when it failed - nothing once its result is the row's
export function RowPressLine({ press }) {
  if (!press) return null;
  const failed = press.state === "failed";
  return <div data-tq-row-press={press.state} role={failed ? "alert" : "status"}
    style={{ fontSize: 12.5, padding: "0 0 8px 36px", color: failed ? "var(--tq-danger, #6b2733)" : "var(--tq-secondary, #6e685f)" }}>
    {failed ? press.said : "Running now - what it finds lands in its last run below."}</div>;
}
