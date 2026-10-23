// THE LINKS STILL OPEN (Settings -> Sharing, under "Share links on your network"): each result shared by link, when it closes, how often it
// was opened - and Revoke, which ends it at once (sharing.revoke). The link itself was shown once, when it was made: only its hash is kept.
import React, { useEffect, useState } from "react";
import { Box, Button, Typography } from "@mui/material";
import api from "./api";
import { BORDER, DIM, FAINT, INK } from "./theme.jsx";

export default function SharedLinks() {
  const [rows, setRows] = useState(null), [err, setErr] = useState(""), [busy, setBusy] = useState(0);
  const load = () => api.get("/api/shares").then(({ data }) => { setRows(data?.data || []); setErr(""); })
    .catch((e) => setErr(e?.response?.data?.detail || "The links could not be read - Taskuary did not answer."));
  useEffect(() => { load(); }, []);
  const revoke = async (id) => {
    setBusy(id);
    try { await api.delete(`/api/shares/${id}`); await load(); }
    catch (e) { setErr(e?.response?.data?.detail || "That link was not revoked - try again."); }
    finally { setBusy(0); }
  };
  if (err) return <Typography variant="body2" role="alert" sx={{ color: "#a33b3b", py: 1.5 }}>{err}</Typography>;
  if (!rows?.length) return null;
  return (
    <Box data-tq-shared-links="" sx={{ py: 1.5 }}>
      <Typography sx={{ color: INK, fontWeight: 600, fontSize: 13.5, mb: 0.5 }}>Links open now</Typography>
      {rows.map((r) => (
        <Box key={r.id} sx={{ display: "flex", alignItems: "center", gap: 1.5, py: 1, borderBottom: `1px solid ${BORDER}` }}>
          <Box sx={{ flex: 1, minWidth: 0 }}>
            <Typography noWrap sx={{ fontSize: 13, color: INK }} title={r.title}>{r.title}</Typography>
            <Typography variant="caption" sx={{ color: FAINT, display: "block" }}>
              {r.kind} · shared {String(r.created || "").slice(0, 16)} · open until {String(r.expires || "").slice(0, 16)} · opened {r.views || 0}×</Typography>
          </Box>
          <Button size="small" variant="outlined" disabled={busy === r.id} onClick={() => revoke(r.id)} sx={{ color: DIM, borderColor: BORDER }}
            title="Ends this link now - whoever has it sees nothing">{busy === r.id ? "Revoking…" : "Revoke"}</Button>
        </Box>
      ))}
    </Box>
  );
}
