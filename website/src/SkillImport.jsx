// Bringing in someone else's SKILL.md as an ordinary worker. /read only proposes - it writes
// nothing - so the owner can see the purpose AND the body before any of it becomes a session's
// instructions; /import is the one call that actually writes, and only for the rows it is handed.
import React, { useEffect, useMemo, useState } from "react";
import { Alert, Box, Button, Checkbox, Chip, CircularProgress, Dialog, DialogActions, DialogContent,
  DialogTitle, FormControlLabel, TextField, Typography } from "@mui/material";
import api from "./api";
import { buildPayload, clashText, cutBy, reconcileImport, slug } from "./skillImport.js";
import { BORDER, FAINT, INK, ROLES, mono } from "./theme.jsx";
import { Confirm } from "./ui.jsx";

const failure = (e) => e?.response?.data?.detail || e?.message || "Something went wrong";
const kb = (n) => (n >= 1024 ? `${(n / 1024).toFixed(1)} KB` : `${n || 0} B`);

const STEPS = ["Where from", "What is in it", "Import"];

export default function SkillImport({ onClose, onImported }) {
  const [step, setStep] = useState(0);
  const [path, setPath] = useState("");
  const [found, setFound] = useState(null);
  const [rows, setRows] = useState([]);   // one proposal per skill, edited in place before anything is written
  const [openBody, setOpenBody] = useState({});
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [done, setDone] = useState(null); // the last import's receipt: {imported: [...names]}
  const [docChars, setDocChars] = useState(0);   // where a session's seed cuts a rules document - the server's number
  const [overwrite, setOverwrite] = useState(null); // index of the row whose Overwrite is waiting on a confirm

  useEffect(() => {
    let live = true;
    api.get("/api/skills/found").then(({ data }) => live && setFound(data.data || []))
      .catch((e) => live && setErr(failure(e)));
    return () => { live = false; };
  }, []);

  const groups = useMemo(() => {
    const g = new Map();
    for (const r of found || []) {
      const key = r.plugin || "Personal skills";
      if (!g.has(key)) g.set(key, { key, rows: [] });
      g.get(key).rows.push(r);
    }
    return [...g.values()];
  }, [found]);

  const read = async () => {
    const target = path.trim();
    if (!target) return;
    setBusy(true); setErr("");
    try {
      const { data } = await api.post("/api/skills/read", { path: target });
      setDocChars(data.doc_chars || 0);
      // enabled defaults OFF: reading a skill only proposes it, it does not offer it to the router.
      // name is slugged up front so what the owner sees is already what the server will store.
      setRows((data.data || []).map((r) => ({ ...r, name: slug(r.name), enabled: false, replace: false, clash: null, imported: false })));
      setStep(1);
    } catch (e) { setErr(failure(e)); }
    setBusy(false);
  };

  const setRow = (i, patch) => setRows((rs) => rs.map((r, j) => (j === i ? { ...r, ...patch } : r)));

  const runImport = async () => {
    setBusy(true); setErr(""); setDone(null);
    try {
      // buildPayload/reconcileImport both slug the name through the one shared rule (skillImport.js)
      // - what is SENT and what is MATCHED against the response are the same string by construction.
      const { data } = await api.post("/api/skills/import", { skills: buildPayload(rows) });
      setRows((rs) => reconcileImport(rs, data));
      setDone({ imported: data.imported || [] });
      if (data.imported?.length) onImported?.();
    } catch (e) { setErr(failure(e)); }
    setBusy(false);
  };

  const pending = rows.filter((r) => !r.imported);
  const allNamed = rows.every((r) => r.name.trim());

  return (
    <Dialog open onClose={busy ? undefined : onClose} fullWidth maxWidth="md" PaperProps={{ sx: { minHeight: "62vh" } }}>
      <DialogTitle>Import skills — step {step + 1} of 3: {STEPS[step]}</DialogTitle>
      <DialogContent sx={{ display: "flex", flexDirection: "column", gap: 1.25 }}>
        {err && <Alert severity="error" onClose={() => setErr("")}>{err}</Alert>}

        {step === 0 && (
          <>
            <Typography variant="body2" sx={{ color: FAINT }}>
              A skill is somebody else's SKILL.md - a rules document written for one coding harness, not
              access to anything. Point at a single SKILL.md, or a plugin folder to bring over everything
              inside it at once.
            </Typography>
            <Box sx={{ display: "flex", gap: 1 }}>
              <TextField fullWidth size="small" label="Path" placeholder="~/.claude/skills/researcher/SKILL.md"
                value={path} onChange={(e) => setPath(e.target.value)} />
              <Button variant="contained" disableElevation disabled={busy || !path.trim()} onClick={read}>
                {busy ? <CircularProgress size={16} sx={{ color: "#fff" }} /> : "Read"}
              </Button>
            </Box>
            <Typography variant="caption" sx={{ color: FAINT }}>
              Already found on this machine - click one to fill the path above, then Read.
            </Typography>
            <Box sx={{ flex: 1, minHeight: 0, maxHeight: 340, overflowY: "auto", border: `1px solid ${BORDER}`, borderRadius: 1.5, p: 1 }}>
              {found === null && <CircularProgress size={18} />}
              {found?.length === 0 && <Typography variant="body2" sx={{ color: FAINT }}>No skills found under ~/.claude on this machine.</Typography>}
              {groups.map((g) => (
                <Box key={g.key} sx={{ mb: 1.25 }}>
                  <Typography variant="caption" sx={{ color: FAINT, fontWeight: 700, textTransform: "uppercase", letterSpacing: 0.5 }}>{g.key}</Typography>
                  {g.rows.map((r) => (
                    <Box key={r.path} onClick={() => setPath(r.path)}
                      sx={{ display: "flex", alignItems: "center", gap: 1, py: 0.6, px: 0.75, borderRadius: 1, cursor: "pointer",
                        bgcolor: path === r.path ? "#f4f1ec" : "transparent", "&:hover": { bgcolor: "#f4f1ec" } }}>
                      <Typography sx={{ ...mono, fontSize: 12.5, fontWeight: 600, color: INK, flex: 1 }} noWrap>{r.name}</Typography>
                      <Typography variant="caption" sx={{ color: FAINT }}>{kb(r.bytes)}</Typography>
                    </Box>
                  ))}
                </Box>
              ))}
            </Box>
          </>
        )}

        {step === 1 && (
          <>
            <Typography variant="body2" sx={{ color: FAINT }}>
              This text becomes a worker's instructions - that is why the body is shown here, before
              anything is written.
            </Typography>
            <Box sx={{ flex: 1, minHeight: 0, overflowY: "auto" }}>
              {rows.map((r, i) => (
                <Box key={r.path || i} sx={{ border: `1px solid ${BORDER}`, borderRadius: 1.5, p: 1.25, mb: 1 }}>
                  <Box sx={{ display: "flex", gap: 1, flexWrap: "wrap", alignItems: "center" }}>
                    <TextField size="small" label="Name" value={r.name} sx={{ minWidth: 160 }}
                      helperText="Saved in this shape - lowercase, hyphenated"
                      onChange={(e) => setRow(i, { name: e.target.value })}
                      onBlur={(e) => setRow(i, { name: slug(e.target.value) })} />
                    <TextField size="small" label="Purpose - when should triage choose this?" value={r.purpose}
                      sx={{ flex: "1 1 260px" }} onChange={(e) => setRow(i, { purpose: e.target.value })} />
                    <Chip size="small" variant="outlined" label={kb(r.bytes)} />
                    {cutBy(r, docChars) > 0 && <Chip size="small" sx={{ color: ROLES.you.ink, borderColor: ROLES.you.bd }} variant="outlined"
                      title="A session is given the rules flattened and cut at a fixed length. The router still sees the whole purpose."
                      label={`${cutBy(r, docChars).toLocaleString()} characters past what a session is given - the end is cut`} />}
                  </Box>
                  <FormControlLabel sx={{ mt: 0.25, display: "flex" }}
                    control={<Checkbox checked={!!r.enabled} onChange={(e) => setRow(i, { enabled: e.target.checked })} />}
                    label="Offer this worker to the router - unticked, it sits on the Profiles list but triage never picks it" />
                  <Button size="small" onClick={() => setOpenBody((o) => ({ ...o, [i]: !o[i] }))}>
                    {openBody[i] ? "Hide the body" : "Read it"}
                  </Button>
                  {openBody[i] && (
                    <Box sx={{ mt: 0.75, maxHeight: 260, overflowY: "auto", bgcolor: "#f6f4f1", borderRadius: 1, p: 1 }}>
                      <Typography component="pre" sx={{ ...mono, fontSize: 11.5, whiteSpace: "pre-wrap", m: 0, color: INK }}>{r.body}</Typography>
                    </Box>
                  )}
                </Box>
              ))}
            </Box>
          </>
        )}

        {step === 2 && (
          <>
            {pending.length > 0 && <Typography variant="body2" sx={{ color: FAINT }}>
              {pending.length} skill{pending.length === 1 ? "" : "s"} ready to write as {pending.length === 1 ? "a profile" : "profiles"}.
            </Typography>}
            <Box sx={{ flex: 1, minHeight: 0, overflowY: "auto" }}>
              {rows.map((r, i) => (
                <Box key={r.path || i} sx={{ display: "flex", alignItems: "center", gap: 1, py: 0.6, flexWrap: "wrap" }}>
                  <Typography sx={{ ...mono, fontSize: 12.5, flex: 1, minWidth: 120 }}>{r.name}</Typography>
                  <Typography variant="caption" sx={{ color: FAINT }}>{r.enabled ? "on the roster" : "not routed"}</Typography>
                  {r.imported && <Chip size="small" label="imported ✓" />}
                  {r.clash && (
                    <>
                      <Chip size="small" sx={{ bgcolor: ROLES.you.tint, color: ROLES.you.ink, border: `1px solid ${ROLES.you.bd}` }}
                        label={clashText(r.clash)} />
                      <Button size="small" onClick={() => setRow(i, { name: slug(`${r.name}-imported`), clash: null, replace: false })}>Rename</Button>
                      {/* asks first: a rules document has no history, so this cannot be undone */}
                      <Button size="small" color="error" onClick={() => setOverwrite(i)}>Overwrite it</Button>
                    </>
                  )}
                </Box>
              ))}
            </Box>
            {done && !pending.length && <Alert severity="success">Imported: {done.imported.join(", ") || "none"}</Alert>}
          </>
        )}
      </DialogContent>
      <DialogActions>
        <Button disabled={busy} onClick={onClose}>{done && !pending.length ? "Done" : "Close"}</Button>
        <Box sx={{ flex: 1 }} />
        {step > 0 && <Button disabled={busy} onClick={() => setStep(step - 1)}>Back</Button>}
        {step === 1 && <Button variant="contained" disableElevation disabled={busy || !rows.length || !allNamed} onClick={() => setStep(2)}>Next</Button>}
        {step === 2 && pending.length > 0 && (
          <Button variant="contained" disableElevation disabled={busy} onClick={runImport}>
            {busy ? <CircularProgress size={16} sx={{ color: "#fff" }} /> : "Import"}
          </Button>
        )}
      </DialogActions>
      <Confirm open={overwrite !== null} confirmLabel="Overwrite" onClose={() => setOverwrite(null)}
        title={rows[overwrite]?.clash?.doc ? `Overwrite ${rows[overwrite].clash.doc.toUpperCase()}.md?` : `Overwrite the "${rows[overwrite]?.name}" profile?`}
        text={rows[overwrite]?.clash?.doc
          ? "That is an operator document the assistant reads on every message, not a worker profile. Its current text has no history to restore from, so this cannot be undone. Rename the import instead unless you mean it."
          : "Its kind and its whole rules document are replaced by this skill's. A profile's document has no history to restore from, so this cannot be undone."}
        onConfirm={() => { setRow(overwrite, { replace: true, clash: null }); }} />
    </Dialog>
  );
}
