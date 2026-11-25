// A CARD THAT NEEDS A CONNECTION NOT SET UP BRINGS THAT CONNECTION'S OWN SETUP UP UNDER IT (the owner, 2026-11-25): Connect opened the
// Connections page and left the card behind. The setup is the Connections page's own card (ChannelDetail - its fields, its Test, its
// sign-in), drawn under the card that asked for it; once it connects, that is the press: the card goes on (onConnected) and its agent is told.
import React, { useCallback, useEffect, useState } from "react";
import { Box, Typography } from "@mui/material";
import api from "./api";
import { ChannelDetail } from "./ConnectorsView.jsx";
import { DIM } from "./theme.jsx";
import { setupType } from "./connectSetup.js";

export default function ConnectSetup({ href, onConnected, onClose }) {
  const type = setupType(href);
  const [got, setGot] = useState(null), [err, setErr] = useState("");
  const load = useCallback(async () => {
    try {
      const [c, s] = await Promise.all([api.get("/api/connectors"), api.get("/api/sources")]);
      setGot({ conns: c.data?.data || [], sources: s.data?.data || [] }); setErr("");
    } catch (e) { setErr(e?.response?.data?.detail || e?.message || "Its card could not be read."); }
  }, []);
  useEffect(() => { load(); }, [load]);
  const conn = got?.conns.find((c) => String(c.Type || "").toLowerCase() === type);
  if (err || (got && !conn)) return <Typography variant="body2" data-tq-inline-setup-failed="" sx={{ color: DIM, mt: 0.75 }}>{err || "Its card is not here."}</Typography>;
  if (!conn) return null;
  return (<Box data-tq-inline-setup={type} sx={{ mt: 1 }}>
    <ChannelDetail key={conn.ConnectorId} conn={conn} sources={got.sources} reload={load} simple onBack={onClose} onConnected={onConnected} />
  </Box>);
}
