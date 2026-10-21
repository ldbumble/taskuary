// PLAYBOOKS LIVE ON THE REPORTS PAGE, beside reports and workflows (the owner, 2026-10-21: "Reports / Workflows / Playbooks"; Settings
// is for regular configuration). A playbook is how this company does one kind of job - triage matches arriving mail to its `when`
// line - so it sits with the other things that do work, not with the knobs. The list is the playbooks on disk, each with its own
// on/off switch (off = kept, never matched); one opens in the playbook editor (DocsView, which owns the words and Delete).
import React, { useCallback, useEffect, useState } from "react";
import { Box, Button, Switch, Typography } from "@mui/material";
import AddIcon from "@mui/icons-material/Add";
import MenuBookIcon from "@mui/icons-material/MenuBook";
import api from "./api.js";
import DocsView from "./DocsView.jsx";
import NewPlaybookDialog from "./NewPlaybookDialog.jsx";
import { BORDER, DIM, FAINT, INK, PANEL, mono } from "./theme.jsx";
import { plural } from "./timeWords.js";

export { PB_OPEN, pbOpen } from "./playbookOpen.js";

export function usePlaybooks() {
  const [books, setBooks] = useState(null);              // null until read (collectionsStartNull): "none yet" is not "not read"
  const [deleted, setDeleted] = useState(null);          // Recently deleted: kept 30 days, Restore puts one back as it was
  const [err, setErr] = useState("");
  const load = useCallback(async () => {
    try { const { data } = await api.get("/api/playbooks"); setBooks(data.data || []); setDeleted(data.deleted || []); setErr(""); }
    catch (e) { setErr(e?.response?.data?.detail || "The playbooks could not be read."); }
  }, []);
  useEffect(() => { load(); }, [load]);
  // ...switched off is kept for later and never matched by triage (PUT /api/playbooks/<slug>/enabled)
  const setOn = useCallback(async (slug, on) => {
    setBooks((bs) => (bs || []).map((b) => (b.slug === slug ? { ...b, enabled: on } : b)));
    try { await api.put(`/api/playbooks/${slug}/enabled`, { on }); }
    catch (e) { setErr(e?.response?.data?.detail || "It could not be switched."); }
    load();
  }, [load]);
  const restore = useCallback(async (slug) => {
    try { await api.post(`/api/playbooks/${slug}/restore`); }
    catch (e) { setErr(e?.response?.data?.detail || "It could not be restored."); }
    load();
  }, [load]);
  return { books: books || [], deleted: deleted || [], loaded: books !== null, err, load, setOn, restore };
}

export function PlaybookRow({ b, onOpen, onToggle }) {
  const on = b.enabled !== false;
  return (
    <Box data-tq-playbook={b.slug} onClick={onOpen}
      sx={{ display: "flex", alignItems: "center", gap: 1.5, py: 1.25, px: 0.5, cursor: "pointer", borderBottom: `1px solid ${BORDER}`,
        opacity: on ? 1 : 0.7, "&:hover": { bgcolor: "#faf8f4" } }}>
      <MenuBookIcon sx={{ fontSize: 18, color: "#55697a", flexShrink: 0 }} />
      <Box sx={{ flex: 1, minWidth: 0 }}>
        <Typography sx={{ color: INK, fontWeight: 600, fontSize: 13.5 }} noWrap>{b.title}</Typography>
        <Typography variant="caption" sx={{ color: DIM, display: "block" }} noWrap>when: {b.when || "—"}</Typography>
        {!!b.uses?.length && <Typography variant="caption" sx={{ ...mono, color: FAINT, display: "block" }} noWrap>uses {b.uses.join(" · ")}</Typography>}
      </Box>
      <Typography variant="caption" sx={{ color: on ? DIM : FAINT, flexShrink: 0 }}>{on ? "triage matches it" : "off - kept, not matched"}</Typography>
      <Switch size="small" checked={on} inputProps={{ "aria-label": `${b.title}: ${on ? "on" : "off"}` }}
        onClick={(e) => e.stopPropagation()} onChange={() => onToggle(!on)} />
    </Box>
  );
}

// RECENTLY DELETED, under the shelf: Delete is at once (no "are you sure" - the owner, 2026-10-21), so this is its undo.
// Restore brings one back exactly - its words, its on/off switch, its place; after 30 days it is gone for good.
export function RecentlyDeleted({ items, onRestore }) {
  if (!items?.length) return null;
  return (
    <Box data-tq-playbooks-deleted="" sx={{ mt: 2 }}>
      <Typography sx={{ fontSize: 12, fontWeight: 600, color: DIM, px: 0.5, mb: 0.5 }}>Recently deleted</Typography>
      {items.map((d) => (
        <Box key={d.slug} data-tq-playbook-deleted={d.slug}
          sx={{ display: "flex", alignItems: "center", gap: 1.5, py: 1, px: 0.5, borderBottom: `1px solid ${BORDER}` }}>
          <MenuBookIcon sx={{ fontSize: 18, color: FAINT, flexShrink: 0 }} />
          <Box sx={{ flex: 1, minWidth: 0 }}>
            <Typography sx={{ color: DIM, fontWeight: 600, fontSize: 13.5 }} noWrap>{d.title}</Typography>
            <Typography variant="caption" sx={{ color: FAINT, display: "block" }} noWrap>
              not matched · gone for good {d.days_left > 0 ? `in ${plural(d.days_left, "day")}` : "today"}
            </Typography>
          </Box>
          <Button size="small" variant="outlined" onClick={() => onRestore(d.slug)}>Restore</Button>
        </Box>
      ))}
    </Box>
  );
}

// the section's own tool: one road to a new playbook, the dialog that builds it with AI or opens the editor on a blank one
// ...a connector card's link (#playbook=new:<type>) arrives with `connectorType`, the dialog open for that card
export function NewPlaybook({ onManual, onDone, connectorType = "" }) {
  const [open, setOpen] = useState(!!connectorType);
  return <>
    <Button size="small" variant="outlined" disableElevation startIcon={<AddIcon sx={{ fontSize: 15 }} />} onClick={() => setOpen(true)}
      sx={{ mt: 1.5, alignSelf: "flex-start" }}>New playbook</Button>
    {open && <NewPlaybookDialog connectorType={connectorType} onClose={() => { setOpen(false); onDone?.(); }}
      onManual={() => { setOpen(false); onManual(); }} />}
  </>;
}

export function PlaybookDetail({ slug, onGone }) {
  return <Box sx={{ bgcolor: PANEL }}><DocsView sel={{ group: "playbooks", doc: slug }} onSel={() => {}} onGone={onGone} /></Box>;
}

export const PB_EMPTY = "No playbooks yet - New playbook builds one from a past email or your own words, and an agent proposes one when it finishes a job that will recur.";
