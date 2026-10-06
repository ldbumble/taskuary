// THE CHECKOUT PICKER ON THE NEW CARD (the owner, 2026-09-30: "can't choose repo to create coding session in").
// The card only said "it picks the checkout from what you write". That stays the default - AUTO - and is now visible:
// the repository the words name outright shows as the pick, and any known repository, or another by name and folder,
// can be chosen instead. The choice rides on the new task as its `repo:` tag; a folder typed for a repo the agent has no
// path for is saved on the agent before the session starts (NewSheet.submit).
// It keeps its own state and hears the words through `bus` (debounced by the field), so a keystroke rebuilds THIS, not the card.
import React, { useEffect, useState } from "react";
import { Box, TextField, Typography } from "@mui/material";
import AccountTreeIcon from "@mui/icons-material/AccountTree";
import api from "./api";
import { BORDER, DIM, FAINT, INK } from "./theme.jsx";
import { AUTO, OTHER, chosenRepo } from "./newRepo.js";

const small = { "& .MuiInputBase-root": { fontSize: 12.5, bgcolor: "#fcfaf7" } };

export default function NewRepo({ agent = "coder", bus, out, first = "" }) {
  const [rows, setRows] = useState(null);
  const [pick, setPick] = useState(AUTO);
  const [said, setSaid] = useState(first);
  const [name, setName] = useState("");
  const [path, setPath] = useState("");
  useEffect(() => {
    let live = true; setRows(null);
    api.get("/api/repos", { params: { agent } }).then(({ data }) => live && setRows(data.data || [])).catch(() => live && setRows([]));
    return () => { live = false; };
  }, [agent]);
  useEffect(() => { bus.current = setSaid; return () => { bus.current = null; }; }, [bus]);
  const list = rows || [];
  // what the card reads when the owner presses Start: the words AS THEY ARE THEN, not as the last debounce saw them
  out.current = (words) => chosenRepo({ rows: list, pick, said: words, name, path });
  const c = chosenRepo({ rows: list, pick, said, name, path });
  const why = pick === OTHER ? "a checkout that is not in the list - the folder is saved for it"
    : pick ? "your choice"
    : c.repo ? "named in what you wrote" : "not named - picked from what you write, when you start";
  return (
    <Box data-tq-new-repo="">
      <Box sx={{ display: "flex", alignItems: "center", gap: 0.75, flexWrap: "wrap" }}>
        <AccountTreeIcon sx={{ fontSize: 15, color: DIM }} />
        <Typography variant="caption" sx={{ color: DIM, fontWeight: 600 }}>Repository</Typography>
        <select aria-label="Repository the session opens in" value={pick} onChange={(e) => setPick(e.target.value)}
          style={{ fontSize: 12.5, padding: "5px 6px", borderRadius: 6, border: `1px solid ${BORDER}`, background: "#fff", color: INK, minWidth: 240, maxWidth: "100%" }}>
          <option value={AUTO}>{c.named ? `Auto - ${c.repo}` : "Auto - picks from what you write"}</option>
          {list.map((r) => <option key={r.repo} value={r.repo}>{r.repo}{r.has_path ? "" : " (no local folder)"}</option>)}
          <option value={OTHER}>Another repository…</option>
        </select>
        <Typography variant="caption" sx={{ color: FAINT, flex: 1, minWidth: 180 }}>{rows === null ? "loading the list…" : why}</Typography>
      </Box>
      {pick === OTHER && (
        <Box sx={{ display: "flex", gap: 1, mt: 1, flexWrap: "wrap" }}>
          <TextField size="small" label="Repository" placeholder="owner/name" value={name} onChange={(e) => setName(e.target.value)} sx={{ ...small, flex: 1, minWidth: 180 }} />
          <TextField size="small" label="Folder on this machine" value={path} onChange={(e) => setPath(e.target.value)} sx={{ ...small, flex: 2, minWidth: 220 }} />
        </Box>
      )}
      {pick !== OTHER && c.needsPath && (
        <Box sx={{ mt: 1 }}>
          <TextField size="small" fullWidth label={`Where is ${c.repo} checked out?`} value={path} onChange={(e) => setPath(e.target.value)}
            helperText="Saved on the agent, so every later task for this repository opens there." sx={small} />
        </Box>
      )}
    </Box>
  );
}
