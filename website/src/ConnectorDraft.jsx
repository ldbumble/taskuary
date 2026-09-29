// The card's draft, the one save its controls go through, and the bar that lists and saves it (connectorDraft.js has
// the rules). A control outside a card with a draft - there is none today, but a panel reused elsewhere - saves at once.
import React, { createContext, useContext, useState } from "react";
import { Box, Button, CircularProgress, Typography } from "@mui/material";
import api from "./api";
import { PANEL, BORDER, DIM, INK } from "./theme.jsx";
import { applied, changes, saveBody, say, stage, stageable } from "./connectorDraft.js";

const Draft = createContext(null);

// the draft a connection card holds, over the connection and its sources
export function useCardDraft(conn, sources, reload) {
  const [want, setWant] = useState(null);
  const [wantSrc, setWantSrc] = useState({});
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const draftConn = applied(conn, want);
  const draftSources = sources.map((s) => (wantSrc[s.SourceId] ? applied(s, wantSrc[s.SourceId]) : s));
  const pending = [
    ...changes(conn, want).map((c) => ({ ...c, where: "" })),
    ...sources.flatMap((s) => changes(s, wantSrc[s.SourceId]).map((c) => ({ ...c, where: s.Address }))),
  ];
  const discard = () => { setWant(null); setWantSrc({}); setErr(""); };
  const save = async () => {
    setBusy(true); setErr("");
    try {
      const body = saveBody(conn, want, "ConnectorId");
      if (body) await api.post("/api/connectors", body);
      for (const s of sources) {
        const sb = saveBody(s, wantSrc[s.SourceId], "SourceId");
        if (sb) await api.post("/api/sources", sb);
      }
      discard();
      await reload?.();
    } catch (e) {
      setErr(e?.response?.data?.detail || "the changes could not be saved - nothing was lost, try again");
    } finally { setBusy(false); }
  };
  const ctx = {
    stageConn: (body) => setWant((w) => stage(w, body)),
    stageSource: (body) => setWantSrc((m) => ({ ...m, [body.SourceId]: stage(m[body.SourceId], body) })),
  };
  return { conn: draftConn, sources: draftSources, pending, save, discard, busy, err, ctx };
}

export const DraftProvider = ({ value, children }) => <Draft.Provider value={value}>{children}</Draft.Provider>;

// a control's settings post: held by the card it sits in, straight to the server outside one
export function useSaveConnector(reload) {
  const d = useContext(Draft);
  return async (body) => {
    if (d && stageable(body, "ConnectorId")) { d.stageConn(body); return; }
    await api.post("/api/connectors", body); await reload?.();
  };
}
export function useSaveSource(reload) {
  const d = useContext(Draft);
  return async (body) => {
    if (d && stageable(body, "SourceId")) { d.stageSource(body); return; }
    await api.post("/api/sources", body); await reload?.();
  };
}

// "2 unsaved changes" and each one, then Discard / Save. Sticky, so it stays in reach on a long card.
export function SaveBar({ draft, labels = {}, words = {} }) {
  const n = draft.pending.length;
  if (!n) return null;
  const line = (c) => {
    const label = labels[c.key] || c.key.replace(/_/g, " ");
    const obj = (c.from && typeof c.from === "object") || (c.to && typeof c.to === "object");
    return `${c.where ? `${c.where} · ` : ""}${label}${obj ? " changed" : `: ${say(c.from, c.key, words)} → ${say(c.to, c.key, words)}`}`;
  };
  return (
    <Box className="tq-savebar" role="region" aria-label="Unsaved changes"
      sx={{ position: "sticky", bottom: 12, zIndex: 5, mt: 2, p: 1.5, bgcolor: PANEL, border: `1px solid ${BORDER}`,
        borderLeft: "3px solid #55697a", borderRadius: 2, boxShadow: "0 4px 16px rgba(30,40,50,.12)" }}>
      <Typography sx={{ fontWeight: 700, fontSize: 13, color: INK, mb: 0.5 }}>{n} unsaved change{n === 1 ? "" : "s"}</Typography>
      <Box component="ul" sx={{ m: 0, pl: 2.25, mb: 1, color: DIM, fontSize: 12.5, lineHeight: 1.6 }}>
        {draft.pending.map((c) => <li key={`${c.where}|${c.field}|${c.key}`}>{line(c)}</li>)}
      </Box>
      {draft.err && <Typography sx={{ color: "#8a3646", fontSize: 12, mb: 1 }}>{draft.err}</Typography>}
      <Box sx={{ display: "flex", gap: 1, justifyContent: "flex-end" }}>
        <Button size="small" onClick={draft.discard} disabled={draft.busy}>Discard</Button>
        <Button size="small" variant="contained" disableElevation onClick={draft.save} disabled={draft.busy}>
          {draft.busy ? <CircularProgress size={14} sx={{ color: "#fff" }} /> : "Save"}</Button>
      </Box>
    </Box>
  );
}
