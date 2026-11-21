import React, { useCallback, useEffect, useState } from "react";
import { Box, MenuItem, Select, Typography } from "@mui/material";
import api from "./api";
import { BORDER, DIM, FAINT, INK } from "./theme.jsx";
import { ACCESS, accessOf, accessSave } from "./agentAccess.js";

// AGENT PERMISSIONS, IN ONE PLACE (the owner, 2026-10-05: "make place in settings for permissions"). Each connection already
// carries its Authority on its own card (ConnectorsView.AuthorityRow); this is the same field, every connection on one page,
// so "what may my agents change?" has one answer to read. The general agent's own reach is the knob above this table.

export default function AgentPermissions({ onLoaded }) {
  const [rows, setRows] = useState(null);
  const [busy, setBusy] = useState(0);
  const [err, setErr] = useState("");
  // a request that failed is not an empty answer (PhoneDoorways): "no connections" would be a lie about the owner's setup
  const load = useCallback(async () => {
    try { setRows((await api.get("/api/connectors")).data.data || []); setErr(""); onLoaded?.(true); }
    catch (e) { setRows(null); setErr(e?.response?.data?.detail || "could not read your connections just now"); onLoaded?.(false); }
  }, [onLoaded]);
  useEffect(() => { load(); }, [load]);
  const save = async (c, body) => {
    setBusy(c.ConnectorId); setErr("");
    try { await api.post("/api/connectors", { ConnectorId: c.ConnectorId, ...body }); await load(); }
    catch (e) { setErr(e?.response?.data?.detail || "could not save that"); }
    setBusy(0);
  };
  // ...never an AI card (the server's IsAI, llm.AI_TYPES): it is what agents think with, not a system they act in - "HIPAA AI - off for agents"
  // read as if agents could not use the AI (2026-11-15)
  const live = (rows || []).filter((c) => c.Active && !c.IsAI);
  return (
    <Box sx={{ mb: 2 }} data-tq-agent-permissions>
      <Typography variant="body2" sx={{ color: DIM, mb: 1 }}>
        What agents may do in each connected system. Every connection starts at full authority; narrow the ones you want. Read only: they look, and any change becomes a proposal you approve on
        the task. Read and write: they make the change themselves. A connection agents cannot use at all is off for them.
      </Typography>
      {live.map((c) => (
        <Box key={c.ConnectorId} data-tq-access-row={c.ConnectorId} sx={{ display: "flex", alignItems: "center", gap: 1.5, py: 1.1, borderBottom: `1px solid ${BORDER}`, flexWrap: "wrap" }}>
          <Box sx={{ flex: 1, minWidth: 180 }}>
            <Typography sx={{ color: INK, fontWeight: 600, fontSize: 13 }}>{c.Name || c.Type}</Typography>
            <Typography variant="caption" sx={{ color: FAINT }}>{c.Type}</Typography>
          </Box>
          <Select size="small" value={accessOf(c)} disabled={busy === c.ConnectorId} onChange={(e) => save(c, accessSave(c, e.target.value))}
            inputProps={{ "aria-label": `What agents may do in ${c.Name || c.Type}` }} sx={{ minWidth: 170, fontSize: 12.5, bgcolor: "var(--tq-panel, #fff)" }}>
            {Object.entries(ACCESS).map(([k, label]) => <MenuItem key={k} value={k} sx={{ fontSize: 12.5 }}>{label}</MenuItem>)}
          </Select>
        </Box>
      ))}
      {rows && !live.length && <Typography variant="body2" sx={{ color: DIM }}>No connection is switched on yet — add one under Connections.</Typography>}
      {err && <Typography variant="body2" sx={{ color: "var(--tq-danger, #7a2f3c)", mt: 1 }}>{err}</Typography>}
    </Box>
  );
}
