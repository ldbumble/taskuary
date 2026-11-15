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

// A SIGN-IN SAVED AHEAD OF TIME (the owner, 2026-11-03: "we probably should have space on connector to fill out what the system requires"):
// the site, its user name and password - and its authenticator key if it has one - sealed the way the fill page's Save to vault keeps them.
// The boxes empty once it is kept; nothing typed is ever shown back.
function AddSignin({ onSaved }) {
  const [open, setOpen] = useState(false), [f, setF] = useState({ site: "", user: "", password: "", key: "" });
  const [busy, setBusy] = useState(false), [err, setErr] = useState(""), [said, setSaid] = useState("");
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const save = async (e) => {
    e.preventDefault();
    if (busy || !f.site.trim() || !f.password) return;
    setBusy(true); setErr(""); setSaid("");
    try {
      const { data } = await api.post("/api/signins", f);
      setF({ site: "", user: "", password: "", key: "" }); setOpen(false); setSaid(`Saved your ${data.site} sign-in to the vault.`); onSaved?.();
    } catch (x) { setErr(x?.response?.data?.detail || "That sign-in was not saved - try again."); }
    finally { setBusy(false); }
  };
  if (!open) return (
    <Box sx={{ display: "flex", alignItems: "center", gap: 1.5, py: 0.75 }}>
      <Button size="small" variant="outlined" data-tq-signin-add-open="" onClick={() => { setOpen(true); setSaid(""); }}
        sx={{ color: INK, borderColor: BORDER, textTransform: "none" }}>Add a sign-in</Button>
      {said && <Typography role="status" sx={{ color: FAINT, fontSize: 12.5 }}>{said}</Typography>}
    </Box>
  );
  return (
    <Box component="form" data-tq-signin-add="" onSubmit={save} autoComplete="off"
      sx={{ display: "grid", gap: 1, gridTemplateColumns: { xs: "1fr", sm: "1fr 1fr" }, py: 1, maxWidth: 560 }}>
      <TextField size="small" label="Site" placeholder="portal.example.com" value={f.site} onChange={set("site")} autoFocus
        inputProps={{ spellCheck: false, "data-tq-signin-site": "" }} sx={{ gridColumn: "1 / -1" }} />
      <TextField size="small" label="User name" value={f.user} onChange={set("user")} autoComplete="off" inputProps={{ spellCheck: false }} />
      <TextField size="small" label="Password" type="password" value={f.password} onChange={set("password")} autoComplete="new-password" />
      <TextField size="small" label="Authenticator setup key (optional)" type="password" value={f.key} onChange={set("key")} autoComplete="off"
        inputProps={{ spellCheck: false }} sx={{ gridColumn: "1 / -1" }} />
      <Typography sx={{ gridColumn: "1 / -1", color: FAINT, fontSize: 12 }}>
        Kept sealed on this computer. Taskuary types it into the page of that site when an agent signs in there - the agent never sees it.</Typography>
      {err && <Typography role="alert" sx={{ gridColumn: "1 / -1", color: "var(--tq-danger, #a33b3b)", fontSize: 12.5 }}>{err}</Typography>}
      <Box sx={{ gridColumn: "1 / -1", display: "flex", gap: 1 }}>
        <Button size="small" variant="contained" disableElevation type="submit" disabled={busy || !f.site.trim() || !f.password}>
          {busy ? "Saving…" : "Save to vault"}</Button>
        <Button size="small" onClick={() => { setOpen(false); setErr(""); setF({ site: "", user: "", password: "", key: "" }); }}
          sx={{ color: DIM, textTransform: "none" }}>Cancel</Button>
      </Box>
    </Box>
  );
}

export default function SavedSignins() {
  const [rows, setRows] = useState(null), [err, setErr] = useState(""), [busy, setBusy] = useState(""), [what, setWhat] = useState("");
  const [keyFor, setKeyFor] = useState(""), [key, setKey] = useState(""), [keyErr, setKeyErr] = useState("");
  // A REFUSED PRESS IS SAID ON ITS OWN ROW (2026-10-26): a refused Remove replaced the whole list with its error until a reload, and a
  // refused Remove authenticator key said nothing - its box, where keyErr is drawn, is not open on a row that has a key
  const [rowErr, setRowErr] = useState({ site: "", text: "" });
  const load = () => api.get("/api/signins").then(({ data }) => { setRows(data?.data || []); setErr(""); })
    .catch((e) => setErr(e?.response?.data?.detail || "The saved sign-ins could not be read - Taskuary did not answer."));
  useEffect(() => { load(); }, []);
  const remove = async (site) => {
    setBusy(site); setWhat("remove"); setRowErr({ site: "", text: "" });
    try { await api.delete(`/api/signins/${encodeURIComponent(site)}`); await load(); }
    catch (e) { setRowErr({ site, text: e?.response?.data?.detail || "That sign-in was not removed - try again." }); }
    finally { setBusy(""); }
  };
  const saveKey = async (site, value) => {
    setBusy(site); setWhat("key"); setKeyErr(""); setRowErr({ site: "", text: "" });
    try { await api.post(`/api/signins/${encodeURIComponent(site)}/code`, { key: value }); setKeyFor(""); setKey(""); await load(); }
    // a mistyped key is said under its box, and the box keeps what was typed to fix it - a refused removal, with no box, on its row
    catch (e) {
      if (value) setKeyErr(e?.response?.data?.detail || "The authenticator key was not saved - try again.");
      else setRowErr({ site, text: e?.response?.data?.detail || "The authenticator key was not removed - try again." });
    }
    finally { setBusy(""); }
  };
  if (err && !rows) return <Typography variant="body2" role="alert" sx={{ color: "var(--tq-danger, #a33b3b)", py: 1.5 }}>{err}</Typography>;
  // ...and with none, one quiet line: an owner checking nothing is kept found no trace of the feature at all (2026-10-25)
  if (!rows?.length) return <Box data-tq-saved-signins="" sx={{ py: 1.5 }}>
    <Typography variant="body2" sx={{ color: FAINT, fontSize: 12.5 }}>
      No saved sign-ins. A sign-in you type in the agent browser is kept here once it goes through - or add one now.</Typography>
    <AddSignin onSaved={load} /></Box>;
  return (
    <Box data-tq-saved-signins="" sx={{ py: 1.5 }}>
      <Typography sx={{ color: INK, fontWeight: 600, fontSize: 13.5, mb: 0.5 }}>Saved sign-ins</Typography>
      <AddSignin onSaved={load} />
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
          {rowErr.site === r.site && rowErr.text && (
            <Typography variant="body2" role="alert" data-tq-signin-err="" sx={{ color: "var(--tq-danger, #a33b3b)", mt: 0.5, fontSize: 12.5 }}>{rowErr.text}</Typography>
          )}
          {keyFor === r.site && !r.code && (
            <Box component="form" data-tq-signin-key="" sx={{ display: "flex", gap: 1, alignItems: "flex-start", mt: 1 }}
              onSubmit={(e) => { e.preventDefault(); if (key.trim()) saveKey(r.site, key.trim()); }}>
              <TextField size="small" type="password" autoComplete="off" autoFocus value={key} onChange={(e) => setKey(e.target.value)}
                placeholder="Setup key - the code under &quot;Can't scan the QR code?&quot;" error={!!keyErr} helperText={keyErr || " "}
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
