// A SKILL SOMEBODY SENT HIM, IN (the owner, 2026-11-26: "share with someone else"): a zip, a folder or a lone SKILL.md is read by the
// server and shown here WHOLE - its words, the files that come with it, what in it does nothing here - and saved only by his one press
// on exactly that (taskuary/skillshare.py: `shown` is the hash of what was drawn; a pick that reads differently at the press is refused).
// Nothing in it runs, it never lands on a skill he has, and what it says gives an agent no permission.
import React, { useRef, useState } from "react";
import { Box, Button, Dialog, DialogContent, DialogTitle, Menu, MenuItem, Typography } from "@mui/material";
import { ButtonBar } from "./ButtonBar.jsx";
import FileUploadOutlinedIcon from "@mui/icons-material/FileUploadOutlined";
import api from "./api.js";
import { BORDER, DIM, FAINT, INK, PANEL2, mono } from "./theme.jsx";
import { plural } from "./timeWords.js";

const failure = (e) => e?.response?.data?.detail || e?.message || "It could not be imported.";
const dataOf = (f) => new Promise((ok, no) => { const r = new FileReader(); r.onload = () => ok(String(r.result || "")); r.onerror = () => no(r.error); r.readAsDataURL(f); });
// what the server is sent: each file by its path inside the folder he picked (a lone file by its name), its bytes as a data: URL
export const picked = async (list) => Promise.all([...list].map(async (f) => ({ name: f.webkitRelativePath || f.name, data: await dataOf(f) })));
const kb = (n) => (n < 1024 ? `${n} B` : `${Math.round(n / 1024)} KB`);

export function ImportCard({ view, busy, error, onSave, onClose }) {
  return <Dialog open onClose={busy ? undefined : onClose} fullWidth maxWidth="md" aria-labelledby="import-skill-title" PaperProps={{ sx: { maxHeight: "90vh" } }}>
    <DialogTitle id="import-skill-title" sx={{ pb: 0.5 }}>Import skill · {view.title}</DialogTitle>
    <DialogContent data-tq-skill-import={view.slug}>
      <Typography sx={{ color: DIM, fontSize: 13.5, mb: 1.5 }}>{view.description}</Typography>
      <Box component="pre" data-tq-skill-import-text="" sx={{ ...mono, m: 0, p: 1.5, fontSize: 12, lineHeight: 1.6, color: INK, bgcolor: PANEL2,
        border: `1px solid ${BORDER}`, borderRadius: 1.5, whiteSpace: "pre-wrap", overflowWrap: "anywhere", maxHeight: "46vh", overflowY: "auto" }}>{view.text}</Box>
      {!!view.files?.length && <Box sx={{ mt: 1.5 }}>
        <Typography sx={{ fontSize: 12, fontWeight: 600, color: DIM }}>{plural(view.files.length, "file")} kept with it - stored, never run</Typography>
        {view.files.map((f) => <Typography key={f.name} sx={{ ...mono, fontSize: 11.5, color: FAINT }}>{f.name} · {kb(f.size)}</Typography>)}
      </Box>}
      <Box sx={{ mt: 1.5, display: "flex", flexDirection: "column", gap: 0.5 }}>
        <Typography sx={{ fontSize: 12.5, color: DIM }}>
          Saved as <b>Reports → Skills → {view.slug}</b>{view.renamed ? " - you already have one by its own name, and that one is not touched" : ""}.
          Agents read it as someone else's words. It gives no permission: every send, post or change still waits for your press.
        </Typography>
        {!!view.ignored?.length && <Typography data-tq-skill-import-ignored="" sx={{ fontSize: 12.5, color: DIM }}>
          Ignored here: <span style={mono}>{view.ignored.join(", ")}</span> - a skill cannot allow tools or change how an agent runs.
        </Typography>}
        {!!error && <Typography sx={{ fontSize: 12.5, fontWeight: 600, color: "var(--tq-danger, #6b2733)" }}>✗ {error}</Typography>}
      </Box>
    </DialogContent>
    <ButtonBar>
      <Button variant="contained" data-tq-skill-import-save="" onClick={onSave} disabled={busy}>{busy ? "Saving…" : "Save skill"}</Button>
      <Button onClick={onClose} disabled={busy}>Cancel</Button>
    </ButtonBar>
  </Dialog>;
}

export default function ImportSkill({ onDone }) {
  const [at, setAt] = useState(null), [files, setFiles] = useState(null), [view, setView] = useState(null);
  const [busy, setBusy] = useState(false), [error, setError] = useState("");
  const one = useRef(null), many = useRef(null);
  const read = async (e) => {
    const list = e.target.files; setAt(null); setError("");
    if (!list?.length) return;
    try {
      const sent = await picked(list); e.target.value = "";
      const { data } = await api.post("/api/skills/import", { files: sent });
      setFiles(sent); setView(data);
    } catch (err) { setError(failure(err)); }
  };
  const save = async () => {
    setBusy(true); setError("");
    try { await api.post("/api/skills/import", { files, save: true, shown: view.shown }); setView(null); setFiles(null); onDone?.(); }
    catch (err) { setError(failure(err)); }
    finally { setBusy(false); }
  };
  return <>
    <Button size="small" variant="outlined" disableElevation data-tq-skill-import-open="" startIcon={<FileUploadOutlinedIcon sx={{ fontSize: 15 }} />}
      onClick={(e) => setAt(e.currentTarget)} sx={{ alignSelf: "flex-start" }}>Import</Button>
    <Menu anchorEl={at} open={!!at} onClose={() => setAt(null)}>
      <MenuItem onClick={() => { setAt(null); one.current?.click(); }}>A file - a .zip or a SKILL.md</MenuItem>
      <MenuItem onClick={() => { setAt(null); many.current?.click(); }}>A folder</MenuItem>
    </Menu>
    <input ref={one} type="file" hidden accept=".zip,.md,.markdown,.txt" onChange={read} />
    <input ref={many} type="file" hidden webkitdirectory="" onChange={read} />
    {!!error && !view && <Typography variant="body2" sx={{ mt: 1, fontWeight: 600, color: "var(--tq-danger, #6b2733)" }}>✗ {error}</Typography>}
    {view && <ImportCard view={view} busy={busy} error={error} onSave={save} onClose={() => { setView(null); setFiles(null); setError(""); }} />}
  </>;
}
