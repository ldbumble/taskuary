import React, { useState } from "react";
import { describe } from "./proposalCard.js";
import { RepoPicker } from "./RepoPicker.jsx";

// The confirmation box (PW-123): what will happen, on what, with which parameters - and one specifically
// labelled button that submits the structured proposal. Cancel leaves everything where it is. A card
// read back from history carries no version, so it shows what was proposed and offers nothing.
export default function ProposalCard({ p, onConfirm, onCancel, onPreview }) {
  const [peek, setPeek] = useState(null);
  if (!p) return null;
  const d = describe(p);
  const preview = async () => {
    setPeek({ busy: true });
    try { setPeek(await onPreview?.(p)); } catch (e) { setPeek({ error: e?.response?.data?.detail || e?.message || "the dry run failed" }); }
  };
  const open = p.version != null && (p.status || "proposed") === "proposed";
  const askRepo = p.status === "error" && p.repo?.taskId;      // a decision, not a failure: choose, then the same confirmation runs again (PW-135)
  const state = { done: "Confirmed.", cancelled: "Cancelled.", stale: "Out of date - say it again.", error: "Failed - nothing moved." }[p.status] || "";
  return (
    <div className="tq-proposal" style={{ border: "1px solid #d8d1c5", borderRadius: 12, padding: "10px 12px", marginTop: 6, background: "#fffdfb" }}>
      <div style={{ fontWeight: 700, fontSize: 12.5, color: "#41525f" }}>{d.title}</div>
      {d.target && <div style={{ fontSize: 12, color: "#55697a", marginTop: 2 }}>{d.target}</div>}
      {!!d.params.length && (
        <div style={{ fontSize: 11.5, color: "#6b6459", marginTop: 4 }}>
          {d.params.map(([k, v]) => <div key={k}><span style={{ fontWeight: 600 }}>{k}:</span> {String(v)}</div>)}
        </div>
      )}
      {peek && !peek.busy && (
        <div style={{ fontSize: 11.5, color: "#55697a", marginTop: 6, whiteSpace: "pre-wrap" }}>
          {peek.error ? `Dry run: ${peek.error}` : `Dry run - ${peek.headline || ""}\n${peek.summary || ""}`}
        </div>
      )}
      {p.status === "done" && p.outcome?.link && <div style={{ marginTop: 6 }}><a href={p.outcome.link} style={{ fontSize: 12, color: "#55697a" }}>Open it</a></div>}
      {askRepo ? (
        <div style={{ marginTop: 8 }}>
          <div style={{ fontWeight: 600, fontSize: 12, color: "#41525f" }}>Which repository should the coding agent use?</div>
          <RepoPicker taskId={p.repo.taskId} agent={p.repo.agent} onDone={(data) => { if (data?.repo) onConfirm?.(p); }} />
          <button type="button" className="tq-chip" onClick={() => onCancel?.(p)}>Not now</button>
        </div>
      ) : open ? (
        <div className="tq-options" style={{ marginTop: 8 }}>
          <button type="button" className="tq-chip primary" onClick={() => onConfirm?.(p)}>{d.confirm}</button>
          {d.preview && <button type="button" className="tq-chip" disabled={!!peek?.busy} onClick={preview}>{peek?.busy ? "Running…" : "Preview"}</button>}
          <button type="button" className="tq-chip" onClick={() => onCancel?.(p)}>{d.cancel}</button>
        </div>
      ) : (state ? <div style={{ fontSize: 11.5, color: "#8a8276", marginTop: 6 }}>{state}</div> : null)}
    </div>
  );
}
