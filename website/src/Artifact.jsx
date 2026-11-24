// ONE ARTIFACT FOR EVERYTHING A TURN SETS DOWN (the owner, 2026-11-24: "any chart/pdf etc should also be a white artifact; 2 ways to hit the
// same code: either artifact creation or review step"): a file the agent made, a view it drew, and anything it hands him for review - an
// email, a reply, a post, a GitHub comment, a held step, sent or waiting - stand in this one raised frame (appTheme.css .tq-turn-frame).
// `label` is what it is in plain words, over its content; `press` is the row under it - none for a thing made, the press named by what it does
// for a thing to review. What is inside (a picture, a preview, a view's blocks, editable words) is the content's own renderer.
import React, { useState } from "react";
import { Box, Button, Checkbox, CircularProgress, Typography } from "@mui/material";
import OpenInNewIcon from "@mui/icons-material/OpenInNew";
import { PressedButton } from "./PassedCard.jsx";
import { CcRow, DraftField, ToRow } from "./ui.jsx";
import { attUrl } from "./fileSave.js";
import { FOCUS_RING, pressable } from "./pressable.js";
import { MdLine } from "./md.jsx";
import { ACCENT, ALERT_INK, BORDER, DIM, FAINT, INK, label as LABEL } from "./theme.jsx";

export default function Artifact({ as = "div", label = null, press = null, wide = false, className = "", sx, children, ...rest }) {
  return (
    <Box component={as} className={`tq-turn-frame${wide ? " tq-turn-wide" : ""}${className ? ` ${className}` : ""}`} sx={sx} {...rest}>
      {label != null && <Box data-tq-artifact-label="" sx={{ fontSize: 13.5, fontWeight: 700, color: INK, lineHeight: 1.3, overflowWrap: "anywhere" }}>{label}</Box>}
      {children}
      {press}
    </Box>
  );
}

// ANYTHING FOR HIS REVIEW IS THIS ONE CARD (the owner, 2026-11-24: "anything that needs review is ONE generic white raised artifact with editable
// text (label, text, files, one press button named by what it does) - never hard-coded per kind"). An email, a reply, a post, a GitHub comment,
// a Jira move, a held step, a bulk job: each kind only maps its DATA onto these props (ReviewDecision.jsx); the road the press takes is the
// server's. Its after-state - sent, posted, failed, dismissed - is drawn here, on the same card, in place of its press row.
// `fields`: [{key, type, label, value, editable, onChange, ...}] in the order they read; type `line` (a line of words: a subject, a title),
// `heading` (a bold title line), `text` (the words: a body, a post, a comment), `choice` (a pick, on the line under the label), `to` and `people`
// (an email's recipients), `read` (a fact it goes by: where it goes), `picture` (one picture, once - the one-item rule).
// `press`: [{id, label, tone: p | s | q | x, run, disabled, title, spin, hidden, attrs}] - p the press named by what it does, s the others, q a
// quiet one (Dismiss), x a no in red. `after`: {mark, label, line, link: {href, text}} - what the press did. `items`: a bulk card's rows.
export function ReviewCard({ id = "", kind = "", state = "waiting", label: title = null, face = "", fields = [], files = null, before = null, press = [],
  lit = "", quiet = false, nowrap = false, tail = null, after = null, failed = "", under = null, items = null, barRef = null, onView = null, children, ...rest }) {
  const live = fields.some((f) => f.editable), choices = fields.filter((f) => f.type === "choice");
  const anyLit = press.some((v) => v.id === lit && !v.hidden);
  return (
    <Artifact data-tq-review-card={id} data-tq-review-kind={kind} data-tq-act-state={state} sx={{ px: 1.5, py: 1.25 }} {...rest}>
      {(title != null || face || choices.length > 0) && <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 0.75, minWidth: 0 }}>
        {face && <Box aria-hidden sx={{ width: 34, height: 34, flexShrink: 0, borderRadius: "50%", bgcolor: "var(--tq-inset, #dfe6ec)", color: "var(--tq-link, #55697a)",
          display: "grid", placeItems: "center", fontWeight: 700, fontSize: 13 }}>{face}</Box>}
        <Box sx={{ minWidth: 0 }}>
          {title != null && <Typography data-tq-review-label="" component="div" sx={{ fontSize: 13.5, fontWeight: 700, color: INK, lineHeight: 1.3, overflowWrap: "anywhere" }}>{title}</Typography>}
          {choices.length > 0 && <Typography component="div" sx={{ fontSize: 11.5, color: FAINT }}>
            {choices.map((f, i) => <React.Fragment key={f.key}>{i ? " · " : ""}<Choice f={f} /></React.Fragment>)}</Typography>}
        </Box>
      </Box>}
      {before}
      {fields.filter((f) => f.type !== "choice" && !f.hide).map((f) => <Field key={f.key} f={f} onView={onView} />)}
      {files}
      {items && <Items items={items} />}
      {children}
      {after ? <After a={after} /> : (press.length > 0 || tail) && <Box ref={barRef} data-tq-moves="" data-tq-press-row="" {...(live ? {} : { "data-tq-read-only": "" })}
        sx={{ display: "flex", alignItems: "center", gap: 0.75, mt: 1, flexWrap: nowrap ? "nowrap" : "wrap", ...(nowrap ? { "& > button": { whiteSpace: "nowrap", flexShrink: 0 } } : {}) }}>
        {press.map((v) => <Press key={v.id} v={v} lit={lit} anyLit={anyLit} quiet={quiet} />)}
        {tail}
      </Box>}
      {failed && <Typography role="alert" data-tq-review-failed="" sx={{ pt: 0.75, fontSize: 12.5, color: ALERT_INK, overflowWrap: "anywhere" }}><MdLine text={failed} /></Typography>}
      {under}
    </Artifact>
  );
}

// ...one button of the press row: the lit one filled (the Advisor's pick, where it stands), else the press named by what it does - unless the
// task's bar carries the pick (`quiet`); a folded one stays mounted, unseen, its width the one the fold measured
function Press({ v, lit, anyLit, quiet }) {
  const filled = v.id === lit || (!anyLit && !quiet && v.tone === "p");
  return <Button size="small" disableElevation variant={filled ? "contained" : v.tone === "q" || v.tone === "x" ? "text" : "outlined"} color={v.tone === "x" ? "error" : "primary"}
    data-tq-press={String(v.id).split(":").pop()} disabled={!!v.disabled} onClick={v.run} title={v.title || undefined} style={v.hidden ? { display: "none" } : undefined}
    startIcon={v.spin ? <CircularProgress size={11} data-tq-sending="" color="inherit" /> : null} {...(v.attrs || {})}>{v.label}</Button>;
}

// ...what the press did, where its buttons stood: the press it took, drawn pressed, and where it went - one mark for every card (PressedButton)
const After = ({ a }) => (
  <Box data-tq-after="" sx={{ display: "flex", alignItems: "center", gap: 0.75, mt: 1, flexWrap: "wrap" }}>
    <PressedButton pressed={a.mark || "approved"} label={a.label || ""} />
    {!!(a.line || a.link) && <Typography role="status" data-tq-sent-line="" component="span" sx={{ fontSize: 12, color: DIM, overflowWrap: "anywhere" }}>
      {a.line}{a.link && <>{a.line ? " · " : ""}<a href={a.link.href} target="_blank" rel="noopener noreferrer" style={{ color: "var(--tq-link, #55697a)" }}>
        {a.link.text}<OpenInNewIcon sx={{ fontSize: 12, ml: 0.25, verticalAlign: "-1px" }} /></a></>}</Typography>}
  </Box>
);

// ...a line of words is his to change while it waits, where it stands - the same type, no box around it, so nothing moves when it turns
// editable (the owner, 2026-11-23: "all cards should be that way if there is text")
const INLINE = { font: "inherit", fontSize: "inherit", fontWeight: "inherit", lineHeight: "inherit", color: "inherit", border: 0, background: "transparent", padding: 0,
  outline: 0, borderRadius: "4px", minWidth: "4ch", "&:focus-visible": { outline: `2px solid ${ACCENT}`, outlineOffset: 1 } };
const Row = ({ f, children }) => (
  <Box data-tq-field-row={f.key} sx={{ display: "flex", alignItems: "baseline", gap: 0.8, mb: 0.75, minWidth: 0, flexWrap: "wrap" }}>
    {f.label && <Typography sx={{ ...LABEL, flexShrink: 0 }}>{f.label}</Typography>}{children}</Box>
);
const Choice = ({ f }) => f.editable
  ? <Box component="select" data-tq-act-choice={f.key} aria-label={f.label} value={String(f.value)} onChange={(e) => f.onChange(e.target.value)}
      sx={{ ...INLINE, fontSize: 11.5, color: INK, cursor: "pointer", fieldSizing: "content" }}>
      {(f.choices || []).map((c) => <option key={String(c.value)} value={String(c.value)}>{c.label}</option>)}</Box>
  : <span data-tq-act-choice={f.key}>{(f.choices || []).find((c) => String(c.value) === String(f.value))?.label || String(f.value ?? "")}</span>;

function Field({ f, onView }) {
  const [open, setOpen] = useState(false);
  if (f.type === "to") return <Box data-tq-to-line="" sx={{ display: "flex", alignItems: "baseline", columnGap: 2, flexWrap: "wrap" }}>
    <ToRow to={f.value} disabled={!f.editable} needs={!!f.needs} who={f.who || ""} onSave={f.onSave} />{f.trail}</Box>;
  if (f.type === "people") return f.editable ? <CcRow cc={f.value} setCc={f.onChange} channel="email" label={f.label} autoOpen={!!f.autoOpen} onClose={f.onClose} />
    : <Row f={f}><Typography variant="body2" sx={{ color: INK }}>{(f.value || []).join(", ") || "none"}</Typography></Row>;
  if (f.type === "read") return <Row f={f}><Typography variant="body2" data-tq-field={f.key} sx={{ color: INK, fontWeight: 600, minWidth: 0, overflowWrap: "anywhere" }}>{f.value}</Typography>
    {f.note && <Typography variant="caption" sx={{ color: FAINT }}>{f.note}</Typography>}</Row>;
  if (f.type === "picture") return <>
    <Box component="img" data-tq-act-image={f.value} src={attUrl(f.file)} alt={f.alt || f.file?.name || ""} onClick={onView ? () => onView(f.file) : undefined}
      sx={{ display: "block", width: "100%", height: "auto", aspectRatio: "auto 1.91 / 1", maxHeight: "min(60vh, 560px)", objectFit: "cover", mt: 0.75, borderRadius: "8px",
        cursor: onView ? "zoom-in" : "default" }} />
    {f.note && <Typography data-tq-act-image-manual="" sx={{ pt: 0.5, fontSize: 11.5, color: FAINT }}>{f.note}</Typography>}</>;
  if (f.type === "fold") return <Typography {...pressable(f.onToggle)} data-tq-show-command="" aria-expanded={!!f.open} sx={{ ...FOCUS_RING, display: "inline-block", fontSize: 11.5,
    color: "var(--tq-link, #55697a)", cursor: "pointer", fontWeight: 600, mb: f.open ? 0.5 : 0, "&:hover": { textDecoration: "underline" } }}>{f.label}</Typography>;
  if (f.type === "heading") return <Typography data-tq-act-heading={f.key} component="div" sx={{ fontSize: 14, fontWeight: 700, lineHeight: 1.5, color: INK, mb: 0.5, overflowWrap: "anywhere" }}>
    {f.editable ? <Box component="input" data-tq-act-line={f.key} aria-label={f.label} placeholder={f.label} value={String(f.value ?? "")} onChange={(e) => f.onChange(e.target.value)}
      sx={{ ...INLINE, display: "block", width: "100%" }} /> : f.value}</Typography>;
  if (f.type === "line") return <Row f={f}>{f.editable
    ? <Box component="input" data-tq-act-line={f.key} {...(f.key === "subject" ? { "data-tq-subject": "" } : {})} aria-label={f.label} placeholder={f.placeholder || (f.optional ? "none" : f.label)}
        value={String(f.value ?? "")} onChange={(e) => f.onChange(e.target.value)}
        sx={{ ...INLINE, ...FOCUS_RING, flex: 1, minWidth: 0, borderBottom: "1px dashed var(--tq-border, #d9e0d6)", fontSize: 13, fontWeight: 600, color: INK, py: 0.25,
          "&:focus": { borderBottomColor: "var(--tq-border-strong, #6f8a6e)" } }} />
    : <Typography variant="body2" sx={{ color: INK, fontWeight: 600, minWidth: 0, overflowWrap: "anywhere" }}>{f.value}</Typography>}</Row>;
  // ...the words: his to change in the one box every card writes in (DraftField: it grows, it marks a blank, a spinner while the AI writes) -
  // read-only once it went, three lines and the rest a press away
  const long = String(f.value || "").split("\n").length > 3 || String(f.value || "").length > 260;
  if (!f.editable && !f.box) return <>
    <Typography data-tq-act-text="" data-tq-sent-text="" sx={{ fontSize: 13, lineHeight: 1.5, color: f.dim ? DIM : INK, whiteSpace: "pre-wrap", overflowWrap: "anywhere",
      ...(open || !f.clamp ? {} : { display: "-webkit-box", WebkitLineClamp: 3, WebkitBoxOrient: "vertical", overflow: "hidden" }) }}>{f.value}</Typography>
    {f.clamp && long && <Typography {...pressable(() => setOpen((o) => !o))} aria-expanded={open} sx={{ ...FOCUS_RING, display: "inline-block", fontSize: 11.5,
      color: "var(--tq-link, #55697a)", cursor: "pointer", fontWeight: 600, "&:hover": { textDecoration: "underline" } }}>{open ? "Show less" : "Show all"}</Typography>}</>;
  return <Box ref={f.boxRef} data-tq-draft-box="" data-tq-act-text="" data-tq-field="draft" data-tq-label={f.label || "Reply draft"} sx={{ position: "relative", ...(f.hidden ? { display: "none" } : {}) }}>
    {f.spin && <CircularProgress size={14} data-tq-drafting-spin="" sx={{ position: "absolute", top: 12, right: 12, zIndex: 1, color: FAINT }} />}
    <DraftField value={f.value} onChange={(e) => f.onChange?.(e.target.value)} marks={f.marks || []} placeholder={f.placeholder || ""}
      inputProps={{ readOnly: !f.editable, "aria-label": f.label || "Reply draft", style: { fontSize: 13, lineHeight: 1.5 } }} />
    {f.over && <Typography sx={{ fontSize: 11.5, color: ALERT_INK, mt: 0.25 }}>{f.over}</Typography>}
  </Box>;
}

// ...A BULK JOB IS THE SAME CARD WITH ITS ROWS (taskuary/bulkcard.py): whom or what each goes to, its one line, what to check, its tick box, and
// the first few open in their own card to review
const Items = ({ items }) => (
  <Box component="ul" data-tq-review-items="" sx={{ listStyle: "none", m: 0, p: 0, maxHeight: 420, overflowY: "auto" }}>
    {items.map((x, i) => <Box component="li" key={x.id} data-tq-bulk-row={x.id} sx={{ borderTop: i ? `1px solid ${BORDER}` : "none", py: 0.5 }}>
      <Box sx={{ display: "flex", alignItems: "center", gap: 1, minWidth: 0 }}>
        {x.onCheck ? <Checkbox size="small" checked={!!x.checked} disabled={!!x.locked} onChange={x.onCheck} sx={{ p: 0.25 }} inputProps={{ "aria-label": `Include ${x.target}` }} />
          : <Box component="span" sx={{ width: 26, textAlign: "center", color: x.mark === "✓" ? "var(--tq-ok, #3d7a4f)" : FAINT }}>{x.mark}</Box>}
        <Typography sx={{ fontSize: 13, color: INK, flexShrink: 0, maxWidth: 260, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
          textDecoration: x.struck ? "line-through" : "none" }}>{x.target}</Typography>
        <Typography sx={{ fontSize: 13, color: DIM, flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{x.line}</Typography>
        {(x.flags || []).map((f) => <Typography key={f} variant="caption" sx={{ color: "var(--tq-warn, #8a4b1c)" }}>{f}</Typography>)}
        {x.failed && <Typography variant="caption" title={x.failed} sx={{ color: "var(--tq-danger, #7a2f3c)", maxWidth: 260, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{x.failed}</Typography>}
        {x.onOpen && <Button size="small" onClick={x.onOpen} sx={{ minWidth: 0 }}>{x.open ? "Hide" : "Open"}</Button>}
      </Box>
      {x.open && x.body && <Box sx={{ pl: 4, pb: 1 }}>{x.body}</Box>}
    </Box>)}
  </Box>
);
