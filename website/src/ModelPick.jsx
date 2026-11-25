// ONE MODEL PICKER for every box on the "Which AI does what" page (the owner, 2026-11-23): a model is picked from its AI's OWN list
// and saved as its id. An AI card's list is what its provider serves this key (/api/ai/models/<id>, the list the card's Test reads);
// a CLI's is its own catalogue (the server's `choices`). A typed box is left only where no list could be read.
import React, { useEffect, useState } from "react";
import { Autocomplete, Box, TextField, Typography } from "@mui/material";
import api from "./api";
import { FAINT } from "./theme.jsx";
import { idOf, offList } from "./aiCards.js";

// the cards' own lists, {<id>: [...]}, read once per card while the page is open; a failed read leaves that card out (its static list, or the
// typed box). The AI chooser on a task and in New reads its cards' models here too (SwitchAi)
export function useCardModels(connectors = [], on = true) {
  const [live, setLive] = useState({});
  const key = on ? [...new Set(connectors.filter(Boolean).map(String))].sort().join(",") : "";
  useEffect(() => {
    setLive({});
    if (!key) return;
    let ok = true;
    for (const id of key.split(","))
      api.get(`/api/ai/models/${id}`).then((r) => ok && !r.data?.error && setLive((m) => ({ ...m, [id]: r.data?.models || [] }))).catch(() => {});
    return () => { ok = false; };
  }, [key]);
  return live;
}
export const useModels = (connector, on = true) => useCardModels([connector], on)[String(connector)] || null;

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
