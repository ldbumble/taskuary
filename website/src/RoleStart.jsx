// Start from a role: one click from "I do accounts payable" to the worker, its playbooks and its
// mail. Everything it lays out (roles.py) already had its own page; nobody who is not technical
// ever found all four, so the role is offered here, where the workers live, until it is taken.
import React, { useCallback, useEffect, useState } from "react";
import { Box, Button, Dialog, DialogActions, DialogContent, DialogTitle, TextField, Typography } from "@mui/material";
import api from "./api";
import { FAINT, INK } from "./theme.jsx";

// what changed, in the owner's words - a receipt, not a log
const said = (r) => [
  r.profile_added ? `Added the ${r.profile.toUpperCase()}.md worker.` : `The ${r.profile.toUpperCase()}.md worker was already here.`,
  r.playbooks_added.length ? `Added ${r.playbooks_added.length} playbook${r.playbooks_added.length > 1 ? "s" : ""}.` : "",
  `Mail with no better-suited worker now goes to ${r.profile}.`,
  r.ledger_narrowed ? `${r.ledger_narrowed} is set to read: every bill becomes a proposal you approve.` : "",
  r.workflow_id ? "The daily portal job is on the Reports tab under Workflows, switched off until you have signed in to the portal once." : "",
].filter(Boolean).join(" ");

export default function RoleStart({ onApplied }) {
  const [roles, setRoles] = useState([]);
  const [open, setOpen] = useState(null);     // the role being set up
  const [portal, setPortal] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [done, setDone] = useState("");
  const load = useCallback(() => api.get("/api/roles").then(({ data }) => setRoles(data.data || [])).catch(() => {}), []);
  useEffect(() => { load(); }, [load]);
  const apply = async () => {
    setBusy(true); setErr("");
    try {
      const { data } = await api.post(`/api/roles/${open.name}`, { portal });
      setDone(said(data)); setOpen(null); await load(); onApplied?.();
    } catch (e) { setErr(e?.response?.data?.detail || "Could not set it up. Try again, or add the profile by hand."); }
    finally { setBusy(false); }
  };
  const offered = roles.filter((r) => !r.applied);
  if (!offered.length && !done) return null;
  return (
    <Box sx={{ mb: 1.25 }}>
      {done && <Typography sx={{ fontSize: 11.5, color: INK, p: 1.25, mb: 0.75, bgcolor: "#fff", border: "1px solid #e1dcd5", borderRadius: 2 }}>{done}</Typography>}
      {offered.map((r) => (
        <Box key={r.name} sx={{ p: 1.25, mb: 0.75, border: "1px dashed #d8cfbe", borderRadius: 2, display: "flex", alignItems: "center", gap: 1 }}>
          <Box sx={{ flex: 1, minWidth: 0 }}>
            <Typography sx={{ fontSize: 12.5, fontWeight: 600, color: INK }}>Start from a role: {r.title}</Typography>
            <Typography sx={{ fontSize: 11.5, color: FAINT }}>{r.blurb}</Typography>
          </Box>
          <Button size="small" variant="outlined" sx={{ whiteSpace: "nowrap" }} onClick={() => { setOpen(r); setPortal(""); setErr(""); }}>Set up</Button>
        </Box>
      ))}
      <Dialog open={!!open} onClose={() => !busy && setOpen(null)} maxWidth="xs" fullWidth>
        <DialogTitle sx={{ fontSize: 16 }}>Set up for {open?.title.toLowerCase()}</DialogTitle>
        <DialogContent>
          <Typography sx={{ fontSize: 12.5, color: INK, mb: 1.5 }}>
            Adds the {open?.profile.toUpperCase()}.md worker and its playbooks, and sends your mail to it when no other worker fits.
            Nothing is posted to your ledger without your approval.
          </Typography>
          {open?.portal_needed && (
            <TextField size="small" fullWidth label="Bill-approval portal address (optional)" placeholder="https://"
              value={portal} onChange={(e) => setPortal(e.target.value)}
              helperText="For the daily job that reads the portal's approved bills. You can add it later." />
          )}
          {err && <Typography sx={{ fontSize: 12, color: "#8a3324", mt: 1 }}>{err}</Typography>}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpen(null)} disabled={busy}>Cancel</Button>
          <Button variant="contained" onClick={apply} disabled={busy}>{busy ? "Setting up…" : "Set up"}</Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
