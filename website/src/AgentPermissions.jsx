import React, { useCallback, useEffect, useState } from "react";
import { Box, Button, MenuItem, Select, Typography } from "@mui/material";
import api from "./api";
import { BORDER, DIM, FAINT, INK } from "./theme.jsx";

// AGENT PERMISSIONS, IN ONE PLACE (the owner, 2026-10-05: "make place in settings for permissions"). Each connection already
// carries its Authority on its own card (ConnectorsView.AuthorityRow); this is the same field, every connection on one page,
// so "what may my agents change?" has one answer to read. The general agent's own reach is the knob above this table.
const LEVELS = { read: "Read only", write: "Read and write", admin: "Full authority" };
const rolesOf = (c) => new Set(String(c.Roles || "").split(",").map((r) => r.trim()).filter(Boolean));

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
  const live = (rows || []).filter((c) => c.Active);
  return (
    <Box sx={{ mb: 2 }} data-tq-agent-permissions>
      <Typography variant="body2" sx={{ color: DIM, mb: 1 }}>
        What agents may do in each connected system. Every connection starts at full authority; narrow the ones you want. Read only: they look, and any change becomes a proposal you approve on
        the task. Read and write: they make the change themselves. A connection agents cannot use at all is off for them.
      </Typography>
      {live.map((c) => {
        const tool = rolesOf(c).has("tool");
        const level = String(c.Scope || "").toLowerCase() || String(c.ScopeDefault || "read").toLowerCase();
        return (
          <Box key={c.ConnectorId} sx={{ display: "flex", alignItems: "center", gap: 1.5, py: 1.1, borderBottom: `1px solid ${BORDER}`, flexWrap: "wrap" }}>
            <Box sx={{ flex: 1, minWidth: 180 }}>
              <Typography sx={{ color: INK, fontWeight: 700, fontSize: 13 }}>{c.Name || c.Type}</Typography>
              <Typography variant="caption" sx={{ color: FAINT }}>{c.Type}</Typography>
            </Box>
            {tool ? (
              <>
                <Select size="small" value={level} disabled={busy === c.ConnectorId} onChange={(e) => save(c, { Scope: e.target.value })}
                  sx={{ minWidth: 170, fontSize: 12.5, bgcolor: "#fff" }}>
                  {Object.entries(LEVELS).map(([k, label]) => (
                    <MenuItem key={k} value={k} sx={{ fontSize: 12.5 }}>{label}{!c.Scope && k === level ? " (default)" : ""}</MenuItem>
                  ))}
                </Select>
                <Button size="small" disabled={busy === c.ConnectorId} sx={{ fontSize: 11.5 }}
                  onClick={() => save(c, { Roles: [...rolesOf(c)].filter((r) => r !== "tool").join(",") })}>Off for agents</Button>
              </>
            ) : (
              <>
                <Typography variant="body2" sx={{ color: DIM, minWidth: 170 }}>off for agents</Typography>
                <Button size="small" disabled={busy === c.ConnectorId} sx={{ fontSize: 11.5 }}
                  onClick={() => save(c, { Roles: [...rolesOf(c), "tool"].join(",") })}>Let agents use it</Button>
              </>
            )}
          </Box>
        );
      })}
      {rows && !live.length && <Typography variant="body2" sx={{ color: DIM }}>No connection is switched on yet — add one under Connections.</Typography>}
      {err && <Typography variant="body2" sx={{ color: "#7a2f3c", mt: 1 }}>{err}</Typography>}
    </Box>
  );
}
