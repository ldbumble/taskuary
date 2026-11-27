// THE TASK'S ROW OF BUTTONS, ONE BUILDER (the owner, 2026-11-23: "one toolbar ... same buttons, same labels, same order"): every move the task
// has, drawn once - on the open pane's white strip (TaskButtons), a folded pane's spine (SpineMoves), an item's own line (PaneMoves) - and off
// the canvas (the Tasks tab) the same TaskButtons from the page's own verbs. What a press did shows on its button (PressLabel, pressResult).
import React, { useEffect, useLayoutEffect, useRef, useState } from "react";
import { Box, Menu, MenuItem } from "@mui/material";
import { foldRow, heldOff, press, rowOf, sectionsOf, splitRow, taskButtons, useSpineAll, useSpineVerbs } from "./actionRow.js";
import { PressLabel } from "./pressResult.js";
import { ROW_LOOK } from "./ButtonBar.jsx";
import { ACCENT, DIM, FAINT, INK } from "./theme.jsx";

export const FOCUS_EDGE = "var(--tq-border, #e4ded4)";
export const MOVES_AT = 0.33;      // where a spine's moves start, down its height (SectionTab fits its lines above them)
// A FOLDED PANE'S STAGE MOVES (actionRow.splitRow, the owner 2026-10-29): Send to agent / Continue / Run another on Agent's spine, Draft
// reply / Redraft on the chat's - stacked the spine's width in the row's own button look, the lit one filled. A press opens the pane and
// starts the step there (the page's "a press opens its section"); a press on the rest of the spine opens it as before. Came from's are Not a
// task and Remind me, which act where they stand. ...and a thin rule between the spine's words and its moves (the owner, 2026-10-29: "text,
// a rule, then the buttons"). A `tucked` move (a sent reply's Hand it to a person) is not on a spine unless it is lit: its open pane has it
// ...and every move there READS AS A BUTTON AT REST (the owner, 2026-10-29: "can't see the buttons on top, maybe we need color?"): the
// controls' own slate tint with the slate edge (5.7:1 on white) and INK words; the lit one keeps its filled slate
// ...and NOT ALL THE SAME (the owner, 2026-10-29: "what can we make them stand out but not all the same"): one slate, four weights. The
// Advisor's pick filled (.p); a move that takes the task a stage on (`fwd`) outlined in the slate, slate words on white; Mark done the same
// with a stronger edge (`done`), filled only when it is the pick; what acts on the whole task (`task`: Close with a note, Change, Share) quiet
// words that take a tint on hover; a put-down (`down`: Not a task, Remind me) quiet and secondary, a faint edge - no new hue anywhere
const PUT_DOWN = new Set(["nat", "remind", "watch"]);
export const rankOf = (v, head = false) => { const k = String(v?.id || "").split(":").pop(); return head ? (k === "done" ? "done" : "task") : PUT_DOWN.has(k) ? "down" : "fwd"; };
const OUTLINED = { bgcolor: "var(--tq-panel, #fff)", borderColor: ACCENT, color: "var(--tq-link, #55697a)" };
export const MOVE_LOOK = {
  "& .tq-ab.fwd:not(.p), & .tq-ab.done:not(.p)": OUTLINED, "& .tq-ab.done:not(.p)": { boxShadow: `inset 0 0 0 1px ${ACCENT}` },
  "& .tq-ab.fwd:not(.p):hover:not(:disabled), & .tq-ab.done:not(.p):hover:not(:disabled)": { bgcolor: "var(--tq-panel, #f1f4f7)" },
  // ...the task's own quiet moves still wear their pill (the owner, 2026-10-29: "these should have circle pills around them"): a faint edge
  "& .tq-ab.task:not(.p)": { bgcolor: "var(--tq-panel, #fff)", borderColor: "var(--tq-border, #cfc8bc)", color: DIM },
  "& .tq-ab.task:not(.p):hover:not(:disabled)": { bgcolor: "var(--tq-panel, #f6f4f0)", borderColor: ACCENT, color: INK },
  "& .tq-ab.down:not(.p)": { bgcolor: "transparent", borderColor: "var(--tq-border, #d8d1c5)", color: FAINT },
  "& .tq-ab.down:not(.p):hover:not(:disabled)": { bgcolor: "var(--tq-panel, #fff)", borderColor: ACCENT, color: INK } };
const SPINE_MOVES = { ...MOVE_LOOK, display: "flex", flexDirection: "column", gap: 0.6, position: "absolute", top: `${MOVES_AT * 100}%`, left: 12, right: 12,
  pt: 1, borderTop: `1px solid ${FOCUS_EDGE}`, cursor: "default",
  // ...a spine in ratio can be narrow (tabW): its move's words wrap to a second line rather than cut to "Hand it t..."
  "& .tq-ab": { width: "100%", minWidth: 0, minHeight: 30, fontSize: 12.5, px: 1, py: 0.4, justifyContent: "center", textAlign: "center", whiteSpace: "normal",
    lineHeight: 1.2, height: "auto" } };
export const SEC_NAME = { from: "Came from", agent: "Agent" };
const stageBtn = (v, word = v.label, head = false) => <button key={v.id} type="button" className={`tq-ab ${v.tone} ${rankOf(v, head)}`} disabled={v.disabled} aria-disabled={v.disabled || undefined} data-tq-inert={v.inert ? "" : undefined} data-tq-verb={v.id}
  title={(v.disabled && v.why) || v.title || word} onClick={(e) => press(v.id, e, e.currentTarget, v.of)}><PressLabel v={v}>{word}</PressLabel></button>;
// THE TASK'S OWN MOVES RIDE THE CHAT'S PANE (the owner, 2026-10-30, and 2026-11-06: one chat, no Close out): Mark done first (2026-11-02), a closed
// task's Reopen in its place (2026-11-05), then Close with a note, Attach a file and Share; Came from carries Change ▾
function useTaskMoves(sec) {
  const head = useSpineVerbs("head"), share = useSpineVerbs("share"), change = useSpineVerbs("change"), close = sec === "agent";
  const lead = (v) => isDoneMove(v) || /(^|:)reopen$/.test(String(v.id));
  return { done: close ? head.filter(lead) : NO_MOVES, task: close ? [...head.filter((v) => !lead(v)), ...share] : NO_MOVES,
    change: sec === "from" ? change : NO_MOVES };
}
const NO_MOVES = [];
function ChangeMoves({ change, even = false, act = press }) {
  // ...greyed with why when nothing in it applies now (a closed task's: taskMoves), as any move of the task's own is
  const [at, setAt] = useState(null), inert = heldOff(change), off = change.length > 0 && change.every((v) => v.disabled);
  return <>
    <button type="button" className={even ? "tq-ab row" : "tq-ab s task"} aria-haspopup="menu" aria-expanded={!!at} data-tq-more="change"
      disabled={inert || off} aria-disabled={inert || off || undefined} data-tq-inert={inert ? "" : undefined}
      title={off ? change[0].why : "Split or merge, who does it or the priority"} onClick={(e) => setAt(e.currentTarget)}>{"Change ▾"}</button>
    <Menu open={!!at} anchorEl={at} onClose={() => setAt(null)}>
      {change.map((v) => <MenuItem key={v.id} dense disabled={v.disabled} data-tq-verb={v.id} sx={{ fontSize: 12.5 }}
        onClick={(e) => { const a = at; setAt(null); act(v.id, e, a, v.of); }}>{v.label}</MenuItem>)}</Menu></>;
}
// ...`quiet`: an item's own whole-item moves laid on its one pane (actionRow.splitRow `all`: a report's Pause this report and Share) wear the
// task's own quiet look, as its Change pill set them apart on the bar
export function SpineMoves({ sec, name = SEC_NAME[sec] }) {
  const vs = useSpineVerbs(sec).filter((v) => !v.tucked || v.tone === "p"), { done, task, change } = useTaskMoves(sec);
  if (!vs.length && !done.length && !task.length && !change.length) return null;
  return (
    <Box data-tq-spine-moves={sec} role="group" aria-label={`${name} moves`} sx={SPINE_MOVES} onClick={(e) => e.stopPropagation()}>
      {done.map((v) => stageBtn(v, v.label, true))}
      {vs.map((v) => stageBtn(v, v.spine || v.label, !!v.quiet))}
      {task.map((v) => stageBtn(v, v.label, true))}
      {change.length > 0 && <ChangeMoves change={change} />}
    </Box>);
}
// ONE ROW OF TASK BUTTONS (the owner, 2026-11-06: "same place but can be on spine or on top if the agent spine is open but it should be one code
// easy to change"): every move the task has, gathered off every pane (actionRow.splitRow), in SECTIONS (actionRow.TASK_GROUPS: Finish | Pass on
// | Agent | More), a hairline between them; a task's own move that does not apply now is greyed with why (taskMoves.js), an empty section is not drawn. Drawn once, where BUTTONS_AT says:
// "strip", the open pane's white strip (the Agent's when it is open); "spine", Came from's spine. One line on a strip, its words never wrapped -
// what does not fit folds into its ▾ from the right
// ...and ONE BUILDER FOR EVERY STATE (the owner, 2026-11-23: held for a stranger, at work, after a restart, closed - one toolbar): off the canvas
// (the Tasks tab, a session filling the page) the same row is drawn from the page's own verbs (`verbs`, pressed in place by `act`) - the bar and
// header strip that drew them a second and third way are gone
export const BUTTONS_AT = "strip";
const byOf = (verbs) => splitRow(rowOf({ list: verbs, ref: "" }), { open: "agent" }).by;
export function TaskButtons({ skip = () => false, spine = false, verbs = null, act = press }) {
  const all = useSpineAll(), by = verbs ? byOf(verbs) : all, list = taskButtons(by, skip);
  const up = list.filter((x) => x.change || !x.v.tucked || x.v.tone === "p"), tucked = list.filter((x) => !up.includes(x)).map((x) => x.v);
  const items = up.map((x) => (x.change ? { key: "change", change: x.change, grp: x.grp } : { key: x.v.id, v: x.v, head: x.head, grp: x.grp }));
  if (spine) return items.length ? <Box data-tq-spine-moves="task" role="group" aria-label="Task moves" sx={SPINE_MOVES} onClick={(e) => e.stopPropagation()}>
    {items.map((x) => (x.change ? <ChangeMoves key="change" change={x.change} /> : stageBtn(x.v, x.v.spine || x.v.label, !!x.head)))}</Box> : null;
  return <MovesLine items={items} tucked={tucked} sec="task" name="Task" even act={act} />;
}
// ...one line: what does not fit folds into its ▾ from the end - never Mark done nor what is lit
export function PaneMoves({ sec, skip = () => false, name = SEC_NAME[sec] }) {
  const all = useSpineVerbs(sec).filter((v) => !v.card && !skip(v)), { done, task, change } = useTaskMoves(sec);
  // ...a `tucked` move keeps its rule (a sent reply's Hand it to a person): behind the strip's ▾ unless it is lit
  const up = all.filter((v) => !v.tucked || v.tone === "p"), tucked = all.filter((v) => !up.includes(v));
  const own = (vs) => vs.filter((v) => !skip(v)).map((v) => ({ key: v.id, v, head: true }));
  const items = [...own(done), ...up.map((v) => ({ key: v.id, v, head: !!v.quiet })), ...own(task), ...(change.length ? [{ key: "change", change }] : [])];
  return <MovesLine items={items} tucked={tucked} sec={sec} name={name} />;
}
// ...`even` (the task's row, the owner 2026-11-06: "not all different sizes"): every button one size and one outlined look, the lit one alone
// filled, its sections apart by a hairline (actionRow.sectionsOf) - the ▾ in More's place at the end
function MovesLine({ items, tucked, sec, name, even = false, act = press }) {
  // ...what folds is never Mark done nor what is lit: the others go into the ▾ from the end, wherever the lit one stands (a lit Propose a new time
  // at the row's end was cut off at the strip's edge while the moves before it held their places)
  const box = useRef(null), [drop, setDrop] = useState(0), [, refit] = useState(0), [at, setAt] = useState(null);
  const sig = items.map((x) => `${x.key}:${x.v?.label || ""}:${x.v?.tone || ""}`).join("|");
  useLayoutEffect(() => { setDrop(0); }, [sig]);
  const { shown, out, loose } = foldRow(items, drop);
  useLayoutEffect(() => { const b = box.current; if (b && drop < loose && b.scrollWidth > b.clientWidth + 1) setDrop((k) => k + 1); });
  // ...and a width change measures again even when nothing was folded: a pane narrowing into a half (side by side) left its last move cut off
  // at the edge until some unrelated draw folded it seconds later
  useEffect(() => {
    const b = box.current?.parentElement;
    if (!b || typeof ResizeObserver === "undefined") return undefined;
    let w = b.clientWidth;
    const ro = new ResizeObserver(() => { if (Math.abs(b.clientWidth - w) > 2) { w = b.clientWidth; setDrop(0); refit((k) => k + 1); } });
    ro.observe(b);
    return () => ro.disconnect();
  }, []);
  if (!items.length && !tucked.length) return null;
  const rest = [...out.flatMap((x) => (x.change ? x.change : [x.v])), ...tucked];
  const btn = (x) => (x.change ? <ChangeMoves key="change" change={x.change} even={even} act={act} /> : even ? rowBtn(x.v, x.v.label, act) : stageBtn(x.v, x.v.label, !!x.head));
  // ...the fold is NAMED (the owner, 2026-11-23: a bare ▾ beside the moves read as nothing): "More ▾", as Change wears its own name
  const fold = rest.length > 0 && <button key="fold" type="button" className={even ? "tq-ab row" : "tq-ab s task"} aria-haspopup="menu" data-tq-more={sec}
    disabled={heldOff(rest)} aria-disabled={heldOff(rest) || undefined} onClick={(e) => setAt(e.currentTarget)}>{MORE}</button>;
  const secs = even ? sectionsOf([...shown, ...(fold ? [{ key: "fold", grp: "more", fold }] : [])]) : [];
  return <Box ref={box} data-tq-pane-moves={sec} role="group" aria-label={`${name} moves`} sx={even ? EVEN_ROW : { ...MOVE_LOOK, display: "flex", gap: 0.75, flexWrap: "nowrap", minWidth: 0, overflow: "hidden",
    "& .tq-ab": { flexShrink: 0 } }}>
    {even ? secs.map((g, i) => [i > 0 && <span key={`sep-${g.grp}`} className="tq-row-sep" aria-hidden="true" />,
      <Box key={g.grp} component="span" data-tq-row-group={g.grp} sx={{ display: "flex", gap: 0.75, flexShrink: 0 }}>{g.items.map((x) => x.fold || btn(x))}</Box>])
      : <>{shown.map(btn)}{fold}</>}
    <Menu open={!!at} anchorEl={at} onClose={() => setAt(null)}>
      {rest.map((v) => <MenuItem key={v.id} dense disabled={v.disabled} data-tq-verb={v.id} title={(v.disabled && v.why) || undefined} sx={{ fontSize: 12.5 }}
        onClick={(e) => { const a = at; setAt(null); act(v.id, e, a, v.of); }}>{v.label}</MenuItem>)}</Menu></Box>;
}
const isDoneMove = (v) => v.id === "done" || /:done$/.test(String(v.id));
// THE TASK ROW'S ONE BUTTON: one height, padding, font and radius for every move, outlined; the lit one (the Advisor's pick) alone filled
const rowBtn = (v, word = v.label, act = press) => <button key={v.id} type="button" className={`tq-ab row${v.tone === "p" ? " p" : ""}`} disabled={v.disabled} aria-disabled={v.disabled || undefined} data-tq-inert={v.inert ? "" : undefined} data-tq-verb={v.id}
  title={(v.disabled && v.why) || v.title || word} onClick={(e) => act(v.id, e, e.currentTarget, v.of)}><PressLabel v={v}>{word}</PressLabel></button>;
export const MORE = "More ▾";
const EVEN_ROW = { ...ROW_LOOK, display: "flex", alignItems: "center", gap: 1, flexWrap: "nowrap", minWidth: 0, overflow: "hidden" };
