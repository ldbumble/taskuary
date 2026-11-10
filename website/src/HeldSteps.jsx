// ONE CARD FOR A TURN'S HELD STEPS (the owner, 2026-11-09: "this should be one action button and one card. make it smaller and more
// combined, an action card if you can"): the steps the agent's turn had held, as one act - its title, why it waits once, the folder once, the
// steps numbered, every command under one "Show the commands", one Approve that runs them in order through the one decide door
// (/api/reviews/steps, shellgate.approve_steps: it stops at the first that fails and says which) and one Dismiss. Once pressed it STAYS in the
// turn (the owner, 2026-11-09: "leave the approval card in the agent turn as well with approved"): the press it took, and what came of it.
import React, { useState } from "react";
import { Box, Button, CircularProgress, Typography } from "@mui/material";
import api from "./api";
import { heldCard } from "./reviewProposal.js";
import { useVerbs } from "./actionRow.js";
import { label as btn } from "./buttons.js";
import { failLine, pressSteps } from "./press.js";
import { FOCUS_RING, pressable } from "./pressable.js";
import { ALERT_INK, BORDER, DIM, FAINT, INK } from "./theme.jsx";

const MARK = { ran: "✓", dismissed: "✗", failed: "✗", waiting: "" };
export default function HeldSteps({ reviews, onChanged, toRow = false }) {
  const c = heldCard(reviews), n = c.steps.length;
  const [busy, setBusy] = useState(""), [err, setErr] = useState(""), [open, setOpen] = useState(false);
  const go = async (verb) => {
    setBusy(verb); setErr("");
    const o = await pressSteps(api, c.waiting, verb), data = o.data;
    if (data?.failed) setErr(`Step ${c.steps.findIndex((s) => s.id === data.failed.review) + 1} failed: ${data.failed.error}${data.left?.length ? ` - ${data.left.length === 1 ? "the step after it was" : "the steps after it were"} not run` : ""}`);
    else if (data?.busy) setErr(data.busy);             // the agent is mid-turn in that folder: nothing ran (shellgate.mid_turn)
    else if (!data) setErr(failLine(o, "run"));        // no answer in time is "it may still be going", never "nothing was run" (press.js)
    setBusy(""); onChanged?.();
  };
  const id = (v) => `${c.steps[0]?.id}:${v}`, live = !c.pressed;
  useVerbs(`held:${c.steps[0]?.id}`, live ? [
    { id: id("approve"), group: "decide", tone: "p", label: btn("approve", "action"), disabled: !!busy, run: () => go("approve"), card: true },
    { id: id("reject"), group: "decide", tone: "s", label: "Dismiss", disabled: !!busy, run: () => go("reject"), card: true }] : [], toRow);
  return (
    <Box data-tq-held-steps={n} data-tq-act-state={c.pressed || "waiting"} sx={{ mt: 0.5, px: 1.25, py: 0.9, border: `1px solid ${BORDER}`, borderRadius: 1.5, bgcolor: "var(--tq-panel, #fff)" }}>
      <Typography sx={{ fontSize: 13.5, fontWeight: 700, color: INK, lineHeight: 1.3, overflowWrap: "anywhere" }}>{c.title}</Typography>
      <Typography noWrap title={c.folder} sx={{ fontSize: 11.5, color: FAINT }}>{live ? `${c.why.replace(/\.$/, "")} · in ` : "In "}
        <Box component="span" sx={{ color: DIM, fontWeight: 600 }}>{c.folder}</Box></Typography>
      {n > 1 && <Box component="ol" data-tq-held-list="" sx={{ m: 0, mt: 0.5, pl: 2.5, fontSize: 12.5, color: INK, lineHeight: 1.5 }}>
        {c.steps.map((s) => <li key={s.id} data-tq-held-step={s.state}><span style={{ color: s.state === "dismissed" ? FAINT : INK }}>{s.text}</span>
          {MARK[s.state] && <span style={{ color: s.state === "ran" ? "var(--tq-success, #47654a)" : s.state === "failed" ? ALERT_INK : FAINT, marginLeft: 6 }}>{MARK[s.state]}</span>}</li>)}</Box>}
      <Typography {...pressable(() => setOpen((o) => !o))} data-tq-show-command="" aria-expanded={open}
        sx={{ ...FOCUS_RING, display: "inline-block", mt: 0.4, fontSize: 11.5, color: "var(--tq-link, #55697a)", cursor: "pointer", fontWeight: 600, "&:hover": { textDecoration: "underline" } }}>
        {open ? `Hide the command${n > 1 ? "s" : ""}` : `Show the command${n > 1 ? "s" : ""}`}</Typography>
      {open && <Box component="pre" data-tq-held-commands="" sx={{ m: 0, mt: 0.4, p: 0.75, bgcolor: "var(--tq-inset, #f6f4f1)", borderRadius: 1, fontSize: 11.5, color: DIM, whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>
        {c.steps.map((s, i) => `${n > 1 ? `${i + 1}. ` : ""}${s.command}`).join("\n")}</Box>}
      <Box sx={{ display: "flex", alignItems: "center", gap: 0.75, mt: 0.6, flexWrap: "wrap" }}>
        {live ? <>
          <Button size="small" variant="contained" disableElevation data-tq-held-approve="" disabled={!!busy} onClick={() => go("approve")}
            startIcon={busy === "approve" ? <CircularProgress size={12} color="inherit" /> : null}>
            {busy === "approve" ? "running…" : btn("approve", "action")}</Button>
          <Button size="small" disabled={!!busy} data-tq-held-dismiss="" onClick={() => go("reject")} sx={{ color: ALERT_INK }}>Dismiss</Button>
          {!!c.said && <Typography sx={{ fontSize: 11.5, color: FAINT }}>{c.said}</Typography>}
        </> : <>
          {/* ...the press it took, drawn pressed, and what came of it on the same line */}
          <Button size="small" variant={c.pressed !== "dismissed" ? "contained" : "outlined"} disableElevation disabled data-tq-pressed={c.pressed}
            sx={{ "&.Mui-disabled": c.pressed !== "dismissed" ? { bgcolor: "var(--tq-tint-sage, #dfe8dd)", color: "var(--tq-success, #47654a)" } : { color: FAINT } }}>
            {c.pressed !== "dismissed" ? "✓ Approved" : "✗ Dismissed"}</Button>
          <Typography data-tq-act-done="" sx={{ fontSize: 12, color: DIM, overflowWrap: "anywhere" }}>{c.said}
            {c.url && <> · <a href={c.url} target="_blank" rel="noreferrer">{c.url.replace(/^https?:\/\//, "").slice(0, 70)}</a></>}</Typography>
        </>}
      </Box>
      {/* ...the step that failed on an earlier press says so after a reload too (heldCard's error, read off the review) */}
      {(err || (!busy && (live || c.pressed === "failed") && c.error)) && <Typography role="alert" sx={{ mt: 0.5, fontSize: 12, color: ALERT_INK }}>{err || c.error}</Typography>}
    </Box>
  );
}
