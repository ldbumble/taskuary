// AN ITEM IN A TASK'S THREE SECTIONS (the owner, 2026-10-28: "even reports should come in with the 3 sections of came in-close out but they
// should be small on the side like active agent. Want this to be consistent across. even fyi"): a report or an FYI on the table is the same
// card a task is - its header line, then Came from | the middle | Close out left to right - with the section it is about open and the other
// two the SLIM tabs a live agent leaves (TaskPage MINI_W): an arrow, a mark, a dot for where it stands, the words on hover. A tab's press opens
// its section; the one the item is about folds to its full tab while another is open, as a live agent's does. The pieces are the task's own
// (TaskPage SectionTab, SECTION, SLOT, SectionHead), so the two read as one design. Every section stays mounted: the card's verbs (Foot) ride
// the dock's row from wherever they are drawn, whichever section is open
// ...and ON A DESK THEY RIDE ITS PANE (the owner, 2026-10-31: "i thought we moved all buttons to the agent canvas?? report should be white with
// buttons on it"): as a task's moves left the bar for its panes (2026-10-29/30), the open section wears the task's white strip - its name, its
// fold arrows - and an item that `lays` its moves has every one of them on the strip of the section it is about, and on that section's spine
// folded; the bar is Back and Next. A phone's stacked sections keep the row as it was
import React, { useEffect, useLayoutEffect, useRef, useState } from "react";
import { Box, Typography } from "@mui/material";
import { FOCUS, FOCUS_EDGE, MINI_W, PaneStrip, SECTION, SHADE, SLOT, STACK_BELOW, STRIP_H, SectionHead, SectionTab, TAB_W } from "./TaskPage.jsx";
import { BORDER, DIM, INK, frameInner } from "./theme.jsx";
import { layTable, onPressing, useSpineAll } from "./actionRow.js";

// a section's white card on the warm ground, as a task's focus is
export const ItemPart = ({ children, sx = null, ...rest }) => <Box {...rest} sx={{ ...FOCUS, px: { xs: 1.25, sm: 2 }, minWidth: 0, ...sx }}>{children}</Box>;
// the section an item's moves are laid on, while it lays them (the card's Foot reads it: actionRow.splitRow `all`), else null
export const ItemLay = React.createContext(null);

// `sections`: [{ key, n, name, body, lines, foot, icon, moves }] in the flow's order; `about`: the key the item is about (it opens there, and only it
// folds to a full tab); `here`: the section it is up to; `height`: the canvas's (CanvasItem wordsCap) - one height, like a task's three;
// `lays`: its moves ride the `about` section on a desk (ItemLay)
export default function ItemSections({ kind, label, title, aside, sections, about, here = about, height, itemKey, lays = false }) {
  const [open, setOpen] = useState(about);
  useEffect(() => { setOpen(about); }, [itemKey, about]);
  const body = useRef(null), [w, setW] = useState(0);
  useLayoutEffect(() => {
    const el = body.current;
    if (!el) return undefined;
    const on = () => setW(Math.round(el.getBoundingClientRect().width));
    on();
    if (typeof ResizeObserver === "undefined") return undefined;
    const ro = new ResizeObserver(on); ro.observe(el); return () => ro.disconnect();
  }, []);
  // ...and a section with a STAGE MOVE on its spine (an FYI's Agent: Send to agent) folds to a full tab, as a task's does, so the move can stand
  // there (the owner, 2026-10-31); a press on it opens that section, as a task's spine does
  const spine = useSpineAll(), staged = (k) => k !== about && (spine[k] || []).length > 0;
  const closedW = (k) => (k === about || staged(k) ? TAB_W : MINI_W);
  const openW = (k) => Math.max(240, w - sections.filter((s) => s.key !== k).reduce((n, s) => n + closedW(s.key), 0) - (k === sections[0].key ? 0 : 1));
  const at = (k) => sections.findIndex((s) => s.key === k);
  // ON A PHONE THEY STACK, as a task's sections do under STACK_BELOW (trust audit R1, 2026-10-28): slim side tabs left a report 240px wide
  const stacked = w > 0 && w < STACK_BELOW, keys = sections.map((s) => s.key), kq = keys.join(" ");
  const laid = React.useMemo(() => (lays && w > 0 && !stacked ? { all: about, keys: kq.split(" ") } : null), [lays, w > 0, stacked, about, kq]);   // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { layTable(itemKey, laid); return () => layTable(itemKey, null); }, [itemKey, laid]);
  const spineAt = useRef(spine); spineAt.current = spine;
  useEffect(() => (laid ? onPressing((id) => { const k = laid.keys.find((x) => x !== about && (spineAt.current[x] || []).some((v) => v.id === id)); if (k) setOpen(k); }) : undefined),
    [laid, about]);
  return (
    <ItemLay.Provider value={laid}>
    <Box data-tq-item-sections={kind} sx={{ ...frameInner, height, display: "flex", flexDirection: "column", boxSizing: "border-box", minWidth: 0 }}>
      {/* THE HEADER LINE a task's is (TaskPage data-tq-task-head): what kind it is in the ref's place, its title, and when */}
      <Box data-tq-item-head="" sx={{ px: 1.75, py: 0.7, bgcolor: "#fff", borderBottom: `1px solid ${BORDER}`, flexShrink: 0, display: "flex", gap: 0.9, alignItems: "center", minHeight: 30 }}>
        <Typography sx={{ color: "#41525f", letterSpacing: ".015em", fontWeight: 600, fontSize: 11.5, flexShrink: 0 }}>{label}</Typography>
        <Typography noWrap title={typeof title === "string" ? title : undefined} sx={{ color: INK, flex: 1, minWidth: 0, fontWeight: 600, fontSize: 14, letterSpacing: "-.005em" }}>{title}</Typography>
        {aside && <Box sx={{ flexShrink: 0, color: DIM, fontSize: 11.5, display: "flex", alignItems: "center", gap: 0.75 }}>{aside}</Box>}
      </Box>
      <Box ref={body} data-tq-item-body="" data-tq-sections="" data-tq-main={open} data-tq-stacked={stacked ? "" : undefined}
        sx={stacked ? { flex: 1, minHeight: 0, minWidth: 0, display: "flex", flexDirection: "column", gap: 1.5, bgcolor: SHADE, overflowY: "auto",
          scrollbarWidth: "thin", overscrollBehaviorY: "contain", px: 1.25, py: 1.25, boxSizing: "border-box" }
          : { flex: 1, minHeight: 0, minWidth: 0, display: "flex", flexDirection: "row", bgcolor: SHADE, position: "relative", overflow: "hidden" }}>
        {sections.map((s, i) => stacked ? (
          <Box key={s.key} data-tq-slot={s.key} data-tq-open="" sx={{ minWidth: 0, flexShrink: 0 }}>
            <Box role="region" aria-label={s.name} className="tq-item-sec" sx={{ display: "flex", flexDirection: "column", gap: 1.5, minWidth: 0 }}>
              <SectionHead sec={s} moves={s.moves} />
              {s.body}
            </Box>
          </Box>
        ) : (
          // ...the open one under its white strip (TaskPage PaneStrip), which says its name: a non-`about` one folds back to the one it is about
          <Box key={s.key} data-tq-slot={s.key} data-tq-open={open === s.key ? "" : undefined}
            sx={{ ...SLOT(open === s.key, closedW(s.key)), ...(i ? { borderLeft: `1px solid ${FOCUS_EDGE}` } : {}), "& > [role=region]": { top: `${STRIP_H}px` } }}>
            {open !== s.key && <SectionTab sec={s} lines={s.lines || []} foot={s.foot || ""} icon={s.icon} here={here === s.key && open !== here}
              mini={closedW(s.key) === MINI_W} before={at(s.key) < at(open)} onOpen={() => setOpen(s.key)} />}
            {open === s.key && <PaneStrip sec={s.key} name={s.name} keys={keys} fold={(to) => (s.key === about ? to : about)} onFold={setOpen} />}
            <Box role="region" aria-label={s.name} aria-hidden={open !== s.key ? true : undefined} className="tq-item-sec"
              sx={{ ...SECTION(open === s.key, w ? openW(s.key) : "100%"), gap: 1.5 }}>
              {s.body}
            </Box>
          </Box>
        ))}
      </Box>
    </Box>
    </ItemLay.Provider>
  );
}
