// ONE MODEL PICKER for every box on the "Which AI does what" page (the owner, 2026-11-23): a model is picked from its AI's OWN list
// and saved as its id. An AI card's list is what its provider serves this key (/api/ai/models/<id>, the list the card's Test reads);
// a CLI's is its own catalogue (the server's `choices`). A typed box is left only where no list could be read.
import React, { useEffect, useState } from "react";
import { Autocomplete, Box, TextField, Typography } from "@mui/material";
import api from "./api";
import { FAINT } from "./theme.jsx";
import { idOf, offList } from "./aiCards.js";

// the card's own list, read once per card while the page is open; a failed read leaves the static list (or the typed box)
export function useModels(connector, on = true) {
  const [live, setLive] = useState(null);
  useEffect(() => {
    if (!connector || !on) { setLive(null); return; }
    let ok = true;
    api.get(`/api/ai/models/${connector}`).then((r) => ok && setLive(r.data?.error ? null : r.data?.models || [])).catch(() => ok && setLive(null));
    return () => { ok = false; };
  }, [connector, on]);
  return live;
}

export default function ModelPick({ value, models, connector, ready = true, disabled, placeholder, label, ai, onSave, width = 260 }) {
  const live = useModels(connector, ready);
  const list = live?.length ? live : (models || []).map(idOf).filter(Boolean);
  const [v, setV] = useState(value || "");
  useEffect(() => setV(value || ""), [value]);
  const commit = (next) => { const id = idOf(next); if (id !== (value || "")) onSave(id); };
  const name = (o) => { const m = (models || []).find((x) => idOf(x) === o); return (typeof m === "object" && m?.label) || o || ""; };
  const off = offList(value, live);
  return (
    <Box>
      <Autocomplete freeSolo={!list.length} forcePopupIcon openOnFocus size="small" options={list} value={v || null} disabled={!ready || !!disabled}
        getOptionLabel={name} onInputChange={(_e, next) => !list.length && setV(next)}
        onChange={(_e, next) => { setV(idOf(next)); commit(next); }} onBlur={() => !list.length && commit(v)}
        sx={{ minWidth: width }} renderInput={(p) => <TextField {...p} label={label} placeholder={placeholder}
          sx={{ bgcolor: "var(--tq-panel, #fff)" }} inputProps={{ ...p.inputProps, style: { fontSize: 12.5 } }} />} />
      {off && <Typography variant="caption" data-tq-model-off-list="" sx={{ color: FAINT, display: "block", mt: 0.5, maxWidth: width + 80 }}>
        {`${value} is not a model ${ai || "this AI"} lists - pick one of its own.`}</Typography>}
    </Box>
  );
}
