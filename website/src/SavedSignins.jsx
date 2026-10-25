// THE SIGN-INS KEPT FOR THE BROWSER AGENT (Settings -> Agent permissions, signin.py): each site the owner ticked "Save to vault for next
// time" for on a fill page, when it was saved and last used - and Remove, which forgets the sealed password AND that site's cookies in the
// browser's kept state. Never the user name or the password: the page is not where they are read back.
// ...and its AUTHENTICATOR KEY (the owner, 2026-10-25: "Yes: TOTP codes in the sign-in vault"): kept here or on the fill page, sealed like
// the password, so the server types the site's code after it. Write-only - the row says one is kept, never what it is.
import React, { useEffect, useState } from "react";
import { Box, Button, TextField, Typography } from "@mui/material";
import api from "./api";
import { ago } from "./timeWords.js";
import { BORDER, DIM, FAINT, INK } from "./theme.jsx";

export default function SavedSignins() {
  const [rows, setRows] = useState(null), [err, setErr] = useState(""), [busy, setBusy] = useState(""), [what, setWhat] = useState("");
  const [keyFor, setKeyFor] = useState(""), [key, setKey] = useState(""), [keyErr, setKeyErr] = useState("");
  const load = () => api.get("/api/signins").then(({ data }) => { setRows(data?.data || []); setErr(""); })
    .catch((e) => setErr(e?.response?.data?.detail || "The saved sign-ins could not be read - Taskuary did not answer."));
  useEffect(() => { load(); }, []);
  const remove = async (site) => {
    setBusy(site); setWhat("remove");
    try { await api.delete(`/api/signins/${encodeURIComponent(site)}`); await load(); }
    catch (e) { setErr(e?.response?.data?.detail || "That sign-in was not removed - try again."); }
    finally { setBusy(""); }
  };
  const saveKey = async (site, value) => {
    setBusy(site); setWhat("key"); setKeyErr("");
    try { await api.post(`/api/signins/${encodeURIComponent(site)}/code`, { key: value }); setKeyFor(""); setKey(""); await load(); }
    // a mistyped key is said under its box, and the box keeps what was typed to fix it
    catch (e) { setKeyErr(e?.response?.data?.detail || "The authenticator key was not saved - try again."); }
    finally { setBusy(""); }
  };
  if (err) return <Typography variant="body2" role="alert" sx={{ color: "#a33b3b", py: 1.5 }}>{err}</Typography>;
  if (!rows?.length) return null;
  return (
    <Box data-tq-saved-signins="" sx={{ py: 1.5 }}>
      <Typography sx={{ color: INK, fontWeight: 600, fontSize: 13.5, mb: 0.5 }}>Saved sign-ins</Typography>
      {rows.map((r) => (
        <Box key={r.site} sx={{ py: 1, borderBottom: `1px solid ${BORDER}` }}>
          <Box sx={{ display: "flex", alignItems: "center", gap: 1.5 }}>
            <Box sx={{ flex: 1, minWidth: 0 }}>
              <Typography noWrap sx={{ fontSize: 13, color: INK }} title={r.site}>{r.site}</Typography>
              <Typography variant="caption" sx={{ color: FAINT, display: "block" }}>
                saved {ago(r.saved * 1000)} · {r.used ? `last used ${ago(r.used * 1000)}` : "not used yet"}
                {r.code ? " · authenticator code" : ""}</Typography>
            </Box>
            <Button size="small" disabled={busy === r.site} sx={{ color: DIM, textTransform: "none" }}
              onClick={() => r.code ? saveKey(r.site, "") : (setKeyFor(keyFor === r.site ? "" : r.site), setKey(""), setKeyErr(""))}
              title={r.code ? "Forgets the authenticator key - the site's code is then yours to type"
                : "Keep the site's authenticator key, so Taskuary types its code after the password"}>
              {r.code ? "Remove authenticator key" : "Add authenticator key"}</Button>
            <Button size="small" variant="outlined" disabled={busy === r.site} onClick={() => remove(r.site)} sx={{ color: DIM, borderColor: BORDER }}
              title="Forgets the saved password and signs the browser out of this site">{busy === r.site && what === "remove" ? "Removing…" : "Remove"}</Button>
          </Box>
          {keyFor === r.site && !r.code && (
            <Box component="form" data-tq-signin-key="" sx={{ display: "flex", gap: 1, alignItems: "flex-start", mt: 1 }}
              onSubmit={(e) => { e.preventDefault(); if (key.trim()) saveKey(r.site, key.trim()); }}>
              <TextField size="small" type="password" autoComplete="off" autoFocus value={key} onChange={(e) => setKey(e.target.value)}
                placeholder="The key beside the QR code, or its otpauth:// link" error={!!keyErr} helperText={keyErr || " "}
                inputProps={{ "aria-label": `Authenticator key for ${r.site}`, spellCheck: false }} sx={{ flex: 1 }} />
              <Button size="small" variant="outlined" type="submit" disabled={!key.trim() || busy === r.site}
                sx={{ color: INK, borderColor: BORDER }}>{busy === r.site ? "Saving…" : "Save"}</Button>
            </Box>
          )}
        </Box>
      ))}
    </Box>
  );
}
