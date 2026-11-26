// ONE ARTIFACT FOR EVERYTHING A TURN SETS DOWN (the owner, 2026-11-24: "any chart/pdf etc should also be a white artifact; 2 ways to hit the
// same code: either artifact creation or review step"): a file the agent made, a view it drew, and anything it hands him for review - an
// email, a reply, a post, a GitHub comment, a held step, sent or waiting - stand in this one raised frame (appTheme.css .tq-turn-frame).
// `label` is what it is in plain words, over its content; `press` is the row under it - none for a thing made, the press named by what it does
// for a thing to review. What is inside (a picture, a preview, a view's blocks, editable words) is the content's own renderer.
import React, { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { lineAt, lineStep, shownTab } from "./cardLine.js";
import { Box, Button, Checkbox, CircularProgress, Typography } from "@mui/material";
import OpenInNewIcon from "@mui/icons-material/OpenInNew";
import { PressedButton } from "./PassedCard.jsx";
import { CcRow, DraftField, ToRow } from "./ui.jsx";
import { attUrl } from "./fileSave.js";
import { FOCUS_RING, pressable } from "./pressable.js";
import { MdLine } from "./md.jsx";
import { listCap } from "./bulkCard.js";
import { changeMarks, hasChange, wordDiff } from "./textDiff.js";
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
// (an email's recipients), `read` (a fact it goes by: where it goes), `picture` (one picture, once - the one-item rule), `change` (new words for
// old: the new text whole, marked where it changes against `was`), `ask` (one of the agent's questions: a pick and a line to answer in).
// `press`: [{id, label, tone: p | s | q | x, run, disabled, title, spin, hidden, attrs}] - p the press named by what it does, s the others, q a
// quiet one (Dismiss), x a no in red. `after`: {mark, label, line, link: {href, text}} - what the press did. `items`: a bulk card's rows.
export function ReviewCard({ id = "", kind = "", state = "waiting", label: title = null, face = "", fields = [], files = null, before = null, press = [],
  lit = "", nowrap = false, tail = null, after = null, failed = "", under = null, items = null, barRef = null, onView = null, children, ...rest }) {
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
        {press.map((v) => <Press key={v.id} v={v} lit={lit} anyLit={anyLit} />)}
        {tail}
      </Box>}
      {failed && <Typography role="alert" data-tq-review-failed="" sx={{ pt: 0.75, fontSize: 12.5, color: ALERT_INK, overflowWrap: "anywhere" }}><MdLine text={failed} /></Typography>}
      {under}
    </Artifact>
  );
}

// A SET RAISED IN ONE CALL IS ONE CARD WITH A TAB EACH (BulkCard.jsx, taskuary/cardqueue.py sets; the owner, 2026-11-26: the same post for X, for
// Reddit and for LinkedIn): ONE frame - in its head the tab names, the one shown marked and a settled one ticked, and an arrow each side of the
// count; under them each item as the card it is (`children`, one per tab, in its order), lying flat in that frame, side by side, the shown one
// slid into view. One he said no to, or whose press failed, is crossed, never ticked (`no`). A press on an item is that item's alone AND NEVER
// CHANGES THE ONE SHOWN (cardLine.lineAt): it stays, saying what the press did; he moves with the arrows or a tab's name. The height follows
// the item shown, so nothing under it jumps
const SLIDE = 280, GAP = 24;
const useLayout = typeof window === "undefined" ? useEffect : useLayoutEffect;
export function CardLine({ tabs, children }) {
  const panes = React.Children.toArray(children);
  const [shown, setShown] = useState(() => shownTab(tabs)), [h, setH] = useState(null), refs = useRef([]);
  const at = lineAt(tabs, shown);
  useLayout(() => {
    const el = refs.current[at];
    if (!el) return undefined;
    const fit = () => setH(el.offsetHeight); fit();
    const ro = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(fit);
    ro?.observe(el); return () => ro?.disconnect();
  }, [at, panes.length]);
  const go = (i) => { if (tabs[i]) setShown(shownTab(tabs, tabs[i].key)); };
  const keys = (e) => { const d = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0; if (d) { e.preventDefault(); go(lineStep(tabs, at, d)); } };
  // ...an arrow each side of the count: the card before, the card after - a look, never a press on the card shown
  const arrow = (d, name = d < 0 ? "Previous card" : "Next card") => <Box component="button" type="button" aria-label={name} title={name} data-tq-line-step={d} onClick={() => go(lineStep(tabs, at, d))}
    sx={{ ...FOCUS_RING, font: "inherit", fontSize: 16, lineHeight: 1, width: 24, height: 24, flexShrink: 0, display: "grid", placeItems: "center", p: 0, cursor: "pointer",
      bgcolor: "transparent", color: INK, border: `1px solid ${BORDER}`, borderRadius: "50%", "&:hover": { bgcolor: "var(--tq-inset, #eef2f5)" } }}>{d < 0 ? "‹" : "›"}</Box>;
  const ease = { transition: `transform ${SLIDE}ms cubic-bezier(.2,.7,.2,1), height ${SLIDE}ms ease`, "@media (prefers-reduced-motion: reduce)": { transition: "none" } };
  return (
    <Artifact data-tq-card-line={tabs.length} data-tq-line-at={tabs[at]?.key || ""} sx={{ px: 1.5, py: 1.25 }}>
      <Box data-tq-line-head="" sx={{ display: "flex", alignItems: "center", gap: 0.5, pb: 0.75, mb: 1, minWidth: 0, borderBottom: `1px solid ${BORDER}` }}>
        <Box role="tablist" aria-label="Cards in line" onKeyDown={keys} sx={{ display: "flex", alignItems: "center", minWidth: 0, overflow: "hidden" }}>
          {tabs.map((t, i) => <React.Fragment key={t.key}>{i > 0 && <Box component="span" aria-hidden sx={{ color: FAINT, fontSize: 12, px: 0.25 }}>·</Box>}
            <Box component="button" type="button" role="tab" aria-selected={i === at} tabIndex={i === at ? 0 : -1} data-tq-line-tab={t.key}
              data-tq-tab-state={t.no ? "not-done" : t.done ? "done" : "waiting"} onClick={() => go(i)} title={t.no ? `${t.name} - not done` : t.name}
              sx={{ ...FOCUS_RING, font: "inherit", fontSize: 12.5, lineHeight: 1.6, cursor: "pointer", bgcolor: "transparent", border: 0, px: 0.5, py: 0.125, minWidth: 0,
                maxWidth: 180, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", borderBottom: "2px solid", borderRadius: 0,
                borderColor: i === at ? ACCENT : "transparent", fontWeight: i === at ? 700 : 500, color: i === at ? INK : t.done ? FAINT : DIM,
                transition: "color 160ms ease, border-color 160ms ease", "&:hover": { color: INK } }}>{t.no ? `✗ ${t.name}` : t.done ? `✓ ${t.name}` : t.name}</Box></React.Fragment>)}
        </Box>
        <Box sx={{ ml: "auto", pl: 1, flexShrink: 0, display: "flex", alignItems: "center", gap: 0.75 }}>{arrow(-1)}
          <Typography aria-live="polite" data-tq-card-queue="" component="span" sx={{ fontSize: 11.5, color: DIM, fontVariantNumeric: "tabular-nums" }}>{`${at + 1} of ${tabs.length}`}</Typography>
          {arrow(1)}</Box>
      </Box>
      {/* ...each item lies flat in the one frame: no edge, no padding of its own (appTheme.css: a card inside a card) */}
      <Box sx={{ overflow: "hidden", ...(h != null ? { height: h } : {}), ...ease, "& .tq-turn-frame.tq-turn-frame": { border: 0, borderRadius: 0, m: 0, p: 0, maxWidth: "100%" } }}>
        <Box sx={{ display: "flex", alignItems: "flex-start", gap: `${GAP}px`, transform: `translateX(calc(${-at} * (100% + ${GAP}px)))`, ...ease }}>
          {panes.map((p, i) => <Box key={tabs[i]?.key ?? i} ref={(el) => { refs.current[i] = el; }} role="tabpanel" data-tq-line-pane={tabs[i]?.key ?? i}
            {...(i === at ? {} : { inert: "", "aria-hidden": "true" })} sx={{ flex: "0 0 100%", minWidth: 0 }}>{p}</Box>)}
        </Box>
      </Box>
    </Artifact>
  );
}

// ...one button of the press row: the lit one filled (the Advisor's pick, where it stands), else the press named by what it does - ON EVERY
// CARD, AT EVERY WIDTH (the card gallery, 2026-11-25: Comment and Approve stood outlined where the task's bar "carried the pick" - a bar that
// draws no card's press, and on a phone is not there); a folded one stays mounted, unseen, its width the one the fold measured
function Press({ v, lit, anyLit }) {
  const filled = v.id === lit || (!anyLit && v.tone === "p");
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
// ...AND A LINE OF HIS TO CHANGE WRAPS (the card gallery, 2026-11-25: at phone width a Reddit title and a subject showed only their start - an
// <input> cannot wrap): one row that grows with its words, still one line - Enter and a pasted line break are kept out of it
const OneLine = ({ f, sx, ...rest }) => (
  <Box component="textarea" rows={1} aria-label={f.label} value={String(f.value ?? "")} onChange={(e) => f.onChange(e.target.value.replace(/\s*\n\s*/g, " "))}
    onKeyDown={(e) => { if (e.key === "Enter") e.preventDefault(); }} sx={{ ...INLINE, display: "block", resize: "none", overflow: "hidden", fieldSizing: "content", ...sx }} {...rest} />);
const Row = ({ f, children }) => (
  <Box data-tq-field-row={f.key} sx={{ display: "flex", alignItems: "baseline", gap: 0.8, mb: 0.75, minWidth: 0, flexWrap: "wrap" }}>
    {f.label && <Typography sx={{ ...LABEL, flexShrink: 0 }}>{f.label}</Typography>}{children}</Box>
);
const Choice = ({ f }) => f.editable
  ? <Box component="select" data-tq-act-choice={f.key} aria-label={f.label} value={String(f.value)} onChange={(e) => f.onChange(e.target.value)}
      sx={{ ...INLINE, fontSize: 11.5, color: INK, cursor: "pointer", fieldSizing: "content" }}>
      {(f.choices || []).map((c) => <option key={String(c.value)} value={String(c.value)}>{c.label}</option>)}</Box>
  : <span data-tq-act-choice={f.key}>{(f.choices || []).find((c) => String(c.value) === String(f.value))?.label || String(f.value ?? "")}</span>;

// ...NEW WORDS FOR OLD (the owner, 2026-11-24: "to edit text it should show the edited text?" ... "show also where it changed in the full text"):
// a routine's instructions, a report's question, a skill page - the new text whole, read as tracked changes: what it adds lit, what it takes
// out struck where it stood. A click puts him in the plain words to change, and he stays there - what it adds still lit as he types, a tick where
// words went - so nothing under the pointer moves on the way to Approve. `was`: the words before; `marks`: false shows the new words bare
const MARKED = { "& ins": { textDecoration: "none", bgcolor: "var(--tq-added, rgba(111, 158, 110, 0.28))", borderRadius: "2px" },
  "& del": { color: "var(--tq-removed, #b4495a)", fontSize: "0.92em", opacity: 0.85 } };
function Change({ f }) {
  const [typing, setTyping] = useState(false);
  const parts = useMemo(() => wordDiff(f.was, f.value), [f.was, f.value]), on = f.marks !== false && hasChange(parts);
  const read = !f.editable || (on && !typing);
  return <Box data-tq-change={f.key} data-tq-marks={on ? "on" : "off"} sx={{ mb: 0.75 }}>
    {f.label && <Typography data-tq-change-label="" sx={{ ...LABEL, mb: 0.375 }}>{f.label}</Typography>}
    {read ? <Box data-tq-change-text="" {...(f.editable ? { role: "textbox", tabIndex: 0, "aria-label": f.label, onClick: () => setTyping(true), onFocus: () => setTyping(true) } : {})}
        sx={{ ...FOCUS_RING, ...MARKED, fontSize: 13, lineHeight: 1.5, color: INK, whiteSpace: "pre-wrap", overflowWrap: "anywhere", cursor: f.editable ? "text" : "default",
          ...(f.editable ? { border: `1px solid ${BORDER}`, borderRadius: "4px", px: 1.75, py: 1.0625 } : {}) }}>
        {on ? parts.map((p, i) => p.t === "add" ? <ins key={i} data-tq-added="">{p.s}</ins> : p.t === "del" ? <del key={i} data-tq-removed="">{p.s}</del> : p.s) : f.value}</Box>
      : <DraftField value={f.value} onChange={(e) => f.onChange?.(e.target.value)} marks={on ? changeMarks(parts) : []} autoFocus={typing}
          inputProps={{ "aria-label": f.label, "data-tq-change-box": f.key, style: { fontSize: 13, lineHeight: 1.5 } }} />}
  </Box>;
}

// ...ONE OF THE AGENT'S QUESTIONS (questionsCard.js): the question, a pick where it gave choices - pressed again it is let go - and a line to
// type his own answer in; once the card is pressed, what he answered, read-only where it stood
export const Ask = ({ f }) => (
  <Box data-tq-ask={f.key} sx={{ mb: 1.25 }}>
    <Typography component="div" data-tq-ask-question="" sx={{ fontSize: 13, fontWeight: 600, color: INK, lineHeight: 1.4, mb: 0.5, overflowWrap: "anywhere" }}>{f.label}</Typography>
    {!f.editable ? <Typography data-tq-ask-answer="" sx={{ fontSize: 13, lineHeight: 1.5, color: f.value ? INK : FAINT, whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{f.value || "No answer"}</Typography> : <>
      {(f.choices || []).length > 0 && <Box role="group" aria-label={f.label} sx={{ display: "flex", flexWrap: "wrap", gap: 0.75, mb: 0.5 }}>
        {f.choices.map((c) => <Button key={c} size="small" disableElevation variant={f.value === c ? "contained" : "outlined"} aria-pressed={f.value === c} data-tq-ask-choice={c}
          onClick={() => f.onChange(f.value === c ? "" : c)} sx={{ textTransform: "none", minWidth: 0, maxWidth: "100%", textAlign: "left" }}>{c}</Button>)}</Box>}
      <OneLine f={{ ...f, value: (f.choices || []).includes(f.value) ? "" : f.value }} data-tq-ask-line={f.key} placeholder={(f.choices || []).length ? "Or write your own" : "Your answer"}
        sx={{ ...FOCUS_RING, width: "100%", borderBottom: "1px dashed var(--tq-border, #d9e0d6)", fontSize: 13, color: INK, py: 0.25, "&:focus": { borderBottomColor: "var(--tq-border-strong, #6f8a6e)" } }} /></>}
  </Box>
);

function Field({ f, onView }) {
  const [open, setOpen] = useState(false);
  if (f.type === "change") return <Change f={f} />;
  if (f.type === "ask") return <Ask f={f} />;
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
    {f.editable ? <OneLine f={f} data-tq-act-line={f.key} placeholder={f.label} sx={{ width: "100%" }} /> : f.value}</Typography>;
  if (f.type === "line") return <Row f={f}>{f.editable
    ? <OneLine f={f} data-tq-act-line={f.key} {...(f.key === "subject" ? { "data-tq-subject": "" } : {})} placeholder={f.placeholder || (f.optional ? "none" : f.label)}
        sx={{ ...FOCUS_RING, flex: 1, minWidth: 0, borderBottom: "1px dashed var(--tq-border, #d9e0d6)", fontSize: 13, fontWeight: 600, color: INK, py: 0.25,
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
// the first few open in their own card to review. THE FILES A TURN MADE ARE THE SAME ROWS (TurnFiles): its name a press that shows it in the one
// preview under them (`onPick`, `picked`), its kind and size the line, its Download the row's `tail`
export const Items = ({ items }) => (
  <Box component="ul" data-tq-review-items="" sx={{ listStyle: "none", m: 0, p: 0, maxHeight: listCap(items), overflowY: "auto" }}>
    {items.map((x, i) => <Box component="li" key={x.id} data-tq-bulk-row={x.id} {...(x.picked ? { "data-tq-picked": "" } : {})}
      sx={{ borderTop: i ? `1px solid ${BORDER}` : "none", py: 0.5, ...(x.onPick ? { px: 0.75, borderRadius: "4px", bgcolor: x.picked ? "var(--tq-inset, #eef2f5)" : "transparent" } : {}) }}>
      <Box sx={{ display: "flex", alignItems: "center", gap: 1, minWidth: 0 }}>
        {x.onCheck ? <Checkbox size="small" checked={!!x.checked} disabled={!!x.locked} onChange={x.onCheck} sx={{ p: 0.25 }} inputProps={{ "aria-label": `Include ${x.target}` }} />
          : x.mark != null && <Box component="span" sx={{ width: 26, textAlign: "center", color: x.mark === "✓" ? "var(--tq-ok, #3d7a4f)" : FAINT }}>{x.mark}</Box>}
        <Typography {...(x.onPick ? { ...pressable(x.onPick), "aria-current": x.picked ? "true" : undefined, "data-tq-pick": x.id } : {})} sx={{ fontSize: 13, color: INK,
          flexShrink: 0, maxWidth: 260, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", textDecoration: x.struck ? "line-through" : "none",
          ...(x.onPick ? { ...FOCUS_RING, cursor: "pointer", fontWeight: x.picked ? 700 : 400, "&:hover": { textDecoration: "underline" } } : {}) }}>{x.target}</Typography>
        <Typography sx={{ fontSize: 13, color: DIM, flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{x.line}</Typography>
        {(x.flags || []).map((f) => <Typography key={f} variant="caption" sx={{ color: "var(--tq-warn, #8a4b1c)" }}>{f}</Typography>)}
        {x.failed && <Typography variant="caption" title={x.failed} sx={{ color: "var(--tq-danger, #7a2f3c)", maxWidth: 260, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{x.failed}</Typography>}
        {x.onOpen && <Button size="small" data-tq-opens-under="" aria-expanded={!!x.open} onClick={x.onOpen} sx={{ minWidth: 0 }}>{x.open ? "Hide" : "Open"}</Button>}
        {x.tail}
      </Box>
      {x.open && x.body && <Box sx={{ pl: 4, pb: 1 }}>{x.body}</Box>}
    </Box>)}
  </Box>
);
