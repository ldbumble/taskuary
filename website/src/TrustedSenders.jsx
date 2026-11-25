// WHO YOU TRUSTED (Settings -> Agent permissions; the readiness review, 2026-11-14): a Trust press was kept for good and nothing listed or undid
// it. Each sender and organisation the owner trusted (senders.trusted), with Remove: their next message waits behind Trust again - and each
// routine step he always approved (flow.standing_list), whose next write waits for his press once removed.
import React, { useEffect, useState } from "react";
import { Box, Button, Typography } from "@mui/material";
import api from "./api";
import { BORDER, DIM, FAINT, INK } from "./theme.jsx";

const id = (r) => `${r.kind}:${JSON.stringify(r.key)}`;

export default function TrustedSenders() {
  const [rows, setRows] = useState(null), [err, setErr] = useState(""), [busy, setBusy] = useState("");
  const load = () => api.get("/api/trusted").then(({ data }) => { setRows(data?.data || []); setErr(""); })
    // a server older than this page (or the public demo) has no list to show: nothing, rather than an error over a page of knobs
    .catch((e) => (e?.response?.status === 404 ? setRows([]) : setErr(e?.response?.data?.detail || "Who you trusted could not be read - Taskuary did not answer.")));
  useEffect(() => { load(); }, []);
  const remove = async (r) => {
    setBusy(id(r));
    try { await api.post("/api/trusted/remove", { kind: r.kind, key: r.key }); await load(); }
    catch (e) { setErr(e?.response?.data?.detail || "That was not taken back - try again."); }
    finally { setBusy(""); }
  };
  if (err) return <Typography variant="body2" role="alert" sx={{ color: "var(--tq-danger, #a33b3b)", py: 1.5 }}>{err}</Typography>;
  if (!rows?.length) return null;
  return (
    <Box data-tq-trusted="" sx={{ py: 1.5 }}>
      <Typography sx={{ color: INK, fontWeight: 600, fontSize: 13.5 }}>Who and what you trusted</Typography>
      <Typography variant="caption" sx={{ color: FAINT, display: "block", mb: 0.5 }}>
        A person or organisation's messages start an agent by themselves; a routine step you always approved runs without asking.
        Remove one and it waits for your press again.</Typography>
      {rows.map((r) => (
        <Box key={id(r)} data-tq-trusted-row="" sx={{ display: "flex", alignItems: "center", gap: 1.5, py: 1, borderBottom: `1px solid ${BORDER}` }}>
          <Box sx={{ flex: 1, minWidth: 0 }}>
            <Typography noWrap sx={{ fontSize: 13, color: INK }} title={r.label}>{r.label}</Typography>
            {r.via && <Typography variant="caption" noWrap sx={{ color: FAINT, display: "block" }}>{`on ${r.via}`}</Typography>}
          </Box>
          <Button size="small" variant="outlined" disabled={busy === id(r)} onClick={() => remove(r)} sx={{ color: DIM, borderColor: BORDER }}>
            {busy === id(r) ? "Removing…" : "Remove"}</Button>
        </Box>
      ))}
    </Box>
  );
}
