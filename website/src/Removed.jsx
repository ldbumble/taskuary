// THE UNDO LINE AND RECENTLY DELETED (removed.js says why): drawn by the list that holds the kind, under the press that removed it.
import React, { useCallback, useEffect, useState } from "react";
import { Box, Button, IconButton, Typography } from "@mui/material";
import CloseIcon from "@mui/icons-material/Close";
import RestoreIcon from "@mui/icons-material/RestoreFromTrash";
import api from "./api.js";
import { BORDER, DIM, FAINT, INK } from "./theme.jsx";
import { plural } from "./timeWords.js";
import { announceRemoved, clearRemoved, lastRemoved, onRemoved, removedLine, showsRemoved } from "./removed.js";

export const restoreDeleted = async (did) => (await api.post(`/api/deleted/${did}/restore`)).data;

// "Removed Outlook mail - Undo": the one line a Remove leaves. Undo puts it back as it was and says so; a refusal is said here too.
export function UndoLine({ kinds, onRestored, sx }) {
  const [r, setR] = useState(() => lastRemoved());
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => onRemoved((x) => { setR(x); setErr(""); }), []);
  if (!showsRemoved(r, kinds)) return null;
  const undo = async () => {
    setBusy(true); setErr("");
    try { await restoreDeleted(r.did); clearRemoved(r.did); await onRestored?.(r); }
    catch (e) { setErr(e?.response?.data?.detail || "It could not be put back."); }
    setBusy(false);
  };
  return (
    <Box data-tq-undo={r.kind} role="status" sx={{ display: "flex", alignItems: "center", gap: 1, px: 1.25, py: 0.5, mb: 1.5, borderRadius: 1.5,
      bgcolor: "#f3efe8", border: `1px solid ${BORDER}`, ...sx }}>
      <Typography variant="body2" sx={{ color: INK, flex: 1, minWidth: 0 }} noWrap>
        {removedLine(r.title, r.verb)}{err ? <Box component="span" sx={{ color: "#6b2733", fontWeight: 600 }}> - {err}</Box> : ""}
      </Typography>
      <Button size="small" disabled={busy} onClick={undo} sx={{ fontWeight: 700 }}>Undo</Button>
      <IconButton size="small" aria-label="Dismiss" title="Dismiss" onClick={() => clearRemoved(r.did)}><CloseIcon sx={{ fontSize: 14 }} /></IconButton>
    </Box>
  );
}

// A Remove from a page: the press, the server's answer, and the line - in one call, so every page removes the same way
export async function removeNow(call, kind, title, verb = "Removed") {
  const { data } = await call();
  return announceRemoved({ did: data?.deleted, title: data?.title || title, kind: data?.kind || kind, verb });
}

// Recently deleted: what a Remove kept, for KEEP_DAYS, each with Restore. `version` reloads it when a Remove happens elsewhere.
export function useDeleted(kinds) {
  const key = kinds.join(",");
  const [items, setItems] = useState(null);              // null until read: a list that failed to read draws nothing, not "none"
  const load = useCallback(async () => {
    try { setItems((await api.get("/api/deleted", { params: { kinds: key } })).data.data || []); } catch { setItems(null); }
  }, [key]);
  useEffect(() => { load(); return onRemoved(() => load()); }, [load]);
  return { items: items || [], load };
}

export function RecentlyDeleted({ kinds, onRestored, sx }) {
  const { items, load } = useDeleted(kinds);
  const [err, setErr] = useState("");
  if (!items.length) return null;
  const restore = async (d) => {
    setErr("");
    try { await restoreDeleted(d.id); clearRemoved(d.id); await load(); await onRestored?.(d); }
    catch (e) { setErr(e?.response?.data?.detail || "It could not be restored."); }
  };
  return (
    <Box data-tq-recently-deleted={kinds.join(",")} sx={{ mt: 2, ...sx }}>
      <Typography sx={{ fontSize: 12, fontWeight: 600, color: DIM, px: 0.5, mb: 0.5 }}>Recently deleted</Typography>
      {err && <Typography variant="body2" sx={{ color: "#6b2733", fontWeight: 600, px: 0.5 }}>✗ {err}</Typography>}
      {items.map((d) => (
        <Box key={d.id} data-tq-deleted={d.id} sx={{ display: "flex", alignItems: "center", gap: 1.5, py: 1, px: 0.5, borderBottom: `1px solid ${BORDER}` }}>
          <RestoreIcon sx={{ fontSize: 18, color: FAINT, flexShrink: 0 }} />
          <Box sx={{ flex: 1, minWidth: 0 }}>
            <Typography sx={{ color: DIM, fontWeight: 600, fontSize: 13.5 }} noWrap>{d.title}</Typography>
            <Typography variant="caption" sx={{ color: FAINT, display: "block" }} noWrap>
              {d.kind} · gone for good {d.days_left > 0 ? `in ${plural(d.days_left, "day")}` : "today"}
            </Typography>
          </Box>
          <Button size="small" variant="outlined" onClick={() => restore(d)}>Restore</Button>
        </Box>
      ))}
    </Box>
  );
}
