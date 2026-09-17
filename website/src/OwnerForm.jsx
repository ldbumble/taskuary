// Your name and email, in the two places that ask for them: the setup checklist's first row and the
// walk's first stop.
//
// It lives here rather than inside the checklist because the walk's own bullet said "type your name
// and email right here" while the card carried no field at all - the only way through was the button
// to Docs, which is exactly the pointing the checklist stopped doing (the owner, 2026-09-17: "this is
// wrong. i want box to put in your info directly for this"). Two text boxes have nowhere better to
// be, and a promise made in a bullet has to be kept by the card under it.
import React, { useEffect, useState } from "react";
import { Alert, Box, Button, TextField } from "@mui/material";
import api from "./api";

const Field = (p) => <TextField size="small" fullWidth sx={{ bgcolor: "#fff" }} {...p} />;

export default function OwnerForm({ onDone }) {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  useEffect(() => {
    api.get("/api/owner").then(({ data }) => {
      if (data.owner && data.owner !== "the owner") setName(data.owner);
      // the fresh-install value is the literal token the documents carry, not an address
      if (data.owner_email && !data.owner_email.includes("{{")) setEmail(data.owner_email);
    }).catch(() => {});
  }, []);
  const save = async () => {
    setBusy(true); setErr("");
    try { await api.put("/api/owner", { name: name.trim(), email: email.trim() || null }); await onDone(); }
    catch (e) { setErr(e?.response?.data?.detail || "could not save that"); }
    setBusy(false);
  };
  return (
    <Box sx={{ display: "flex", gap: 1, mt: 1, flexWrap: "wrap" }}>
      <Field label="Your name" value={name} onChange={(e) => setName(e.target.value)} sx={{ bgcolor: "#fff", flex: 1, minWidth: 160 }} />
      <Field label="Email" value={email} onChange={(e) => setEmail(e.target.value)} sx={{ bgcolor: "#fff", flex: 1, minWidth: 160 }} />
      <Button variant="contained" disableElevation size="small" disabled={busy || !name.trim()} onClick={save}>
        {busy ? "…" : "Save"}
      </Button>
      {err && <Alert severity="error" sx={{ width: "100%", fontSize: 12.5 }}>{err}</Alert>}
    </Box>
  );
}
