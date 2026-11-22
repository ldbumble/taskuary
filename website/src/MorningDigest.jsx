import React, { useEffect, useState } from "react";
import { Box, Switch, TextField, Typography } from "@mui/material";
import api from "./api.js";
import { DIM } from "./theme.jsx";

// THE MORNING DIGEST'S OWN CONTROLS, IN SETTINGS (the owner, 2026-11-22: it opens the main screen, so it is no report to list - "Settings"): its
// time and its on/off, written to the one report row it has always been (reports.is_digest), so its runs and its history stay as they were
const isDigest = (s) => { try { const c = JSON.parse(s?.ConfigJson || "{}"); return c.type === "digest" || (c.sources || []).some((x) => x.type === "digest"); } catch { return false; } };
export { isDigest };

export default function MorningDigest() {
  const [src, setSrc] = useState(null), [err, setErr] = useState("");
  const load = () => api.get("/api/sources").then(({ data }) => setSrc((data.data || []).find((s) => s.Channel === "report" && isDigest(s)) || false)).catch(() => setSrc(false));
  useEffect(() => { load(); }, []);
  if (src === null) return null;
  if (!src) return null;                                             // ...none made yet: nothing to set
  const cfg = (() => { try { return JSON.parse(src.ConfigJson || "{}"); } catch { return {}; } })();
  const save = async (fields) => {
    setErr(""); const next = { ...src, ...fields };
    setSrc(next);                                                      // ...the switch moves at the press; a refused save puts it back and says why
    try { await api.post("/api/sources", { SourceId: src.SourceId, ...fields }); }
    catch (e) { setSrc(src); setErr(e?.response?.data?.detail || "That did not save - try again."); }
  };
  return (
    <Box data-tq-morning-digest="" sx={{ display: "flex", alignItems: "center", gap: 2, flexWrap: "wrap", py: 1 }}>
      <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
        <Switch size="small" checked={!!src.Active} onChange={(e) => save({ Active: e.target.checked ? 1 : 0 })} inputProps={{ "aria-label": "Morning digest" }} />
        <Typography sx={{ fontSize: 13.5 }}>Morning digest on the main screen</Typography>
      </Box>
      <TextField type="time" size="small" label="Written at" value={cfg.daily_at || "08:00"} disabled={!src.Active} data-tq-digest-time=""
        onChange={(e) => e.target.value && save({ ConfigJson: JSON.stringify({ ...cfg, daily_at: e.target.value }) })} sx={{ width: 140 }}
        helperText="and when Taskuary starts, once a day" />
      {err && <Typography role="alert" sx={{ fontSize: 12.5, color: "var(--tq-danger, #6b2733)" }}>{err}</Typography>}
    </Box>
  );
}
