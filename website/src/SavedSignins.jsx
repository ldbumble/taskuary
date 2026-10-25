// THE SIGN-INS KEPT FOR THE BROWSER AGENT (Settings -> Agent permissions, signin.py): each site the owner ticked "Save to vault for next
// time" for on a fill page, when it was saved and last used - and Remove, which forgets the sealed password AND that site's cookies in the
// browser's kept state. Never the user name or the password: the page is not where they are read back.
import React, { useEffect, useState } from "react";
import { Box, Button, Typography } from "@mui/material";
import api from "./api";
import { ago } from "./timeWords.js";
import { BORDER, DIM, FAINT, INK } from "./theme.jsx";

export default function SavedSignins() {
  const [rows, setRows] = useState(null), [err, setErr] = useState(""), [busy, setBusy] = useState("");
  const load = () => api.get("/api/signins").then(({ data }) => { setRows(data?.data || []); setErr(""); })
    .catch((e) => setErr(e?.response?.data?.detail || "The saved sign-ins could not be read - Taskuary did not answer."));
  useEffect(() => { load(); }, []);
  const remove = async (site) => {
    setBusy(site);
    try { await api.delete(`/api/signins/${encodeURIComponent(site)}`); await load(); }
    catch (e) { setErr(e?.response?.data?.detail || "That sign-in was not removed - try again."); }
    finally { setBusy(""); }
  };
  if (err) return <Typography variant="body2" role="alert" sx={{ color: "#a33b3b", py: 1.5 }}>{err}</Typography>;
  if (!rows?.length) return null;
  return (
    <Box data-tq-saved-signins="" sx={{ py: 1.5 }}>
      <Typography sx={{ color: INK, fontWeight: 600, fontSize: 13.5, mb: 0.5 }}>Saved sign-ins</Typography>
      {rows.map((r) => (
        <Box key={r.site} sx={{ display: "flex", alignItems: "center", gap: 1.5, py: 1, borderBottom: `1px solid ${BORDER}` }}>
          <Box sx={{ flex: 1, minWidth: 0 }}>
            <Typography noWrap sx={{ fontSize: 13, color: INK }} title={r.site}>{r.site}</Typography>
            <Typography variant="caption" sx={{ color: FAINT, display: "block" }}>
              saved {ago(r.saved * 1000)} · {r.used ? `last used ${ago(r.used * 1000)}` : "not used yet"}</Typography>
          </Box>
          <Button size="small" variant="outlined" disabled={busy === r.site} onClick={() => remove(r.site)} sx={{ color: DIM, borderColor: BORDER }}
            title="Forgets the saved password and signs the browser out of this site">{busy === r.site ? "Removing…" : "Remove"}</Button>
        </Box>
      ))}
    </Box>
  );
}
