// AN ITEM IN A TASK'S THREE SECTIONS (the owner, 2026-10-28: "even reports should come in with the 3 sections of came in-close out but they
// should be small on the side like active agent. Want this to be consistent across. even fyi"): a report or an FYI on the table is the same
// card a task is - its header line, then Came from | the middle | Close out left to right - with the section it is about open and the other
// two the SLIM tabs a live agent leaves (TaskPage MINI_W): an arrow, a mark, a dot for where it stands, the words on hover. A tab's press opens
// its section; the one the item is about folds to its full tab while another is open, as a live agent's does. The pieces are the task's own
// (TaskPage SectionTab, SECTION, SLOT, SectionHead), so the two read as one design. Every section stays mounted: the card's verbs (Foot) ride
// the dock's row from wherever they are drawn, whichever section is open
import React, { useEffect, useLayoutEffect, useRef, useState } from "react";
import { Box, Typography } from "@mui/material";
import { FOCUS, FOCUS_EDGE, MINI_W, SECTION, SHADE, SLOT, STACK_BELOW, SectionHead, SectionTab, TAB_W } from "./TaskPage.jsx";
import { BORDER, DIM, INK, frameInner } from "./theme.jsx";

// a section's white card on the warm ground, as a task's focus is
export const ItemPart = ({ children, sx = null, ...rest }) => <Box {...rest} sx={{ ...FOCUS, px: { xs: 1.25, sm: 2 }, minWidth: 0, ...sx }}>{children}</Box>;

// `sections`: [{ key, n, name, body, lines, foot, icon }] in the flow's order; `about`: the key the item is about (it opens there, and only it
// folds to a full tab); `here`: the section it is up to; `height`: the canvas's (CanvasItem wordsCap) - one height, like a task's three
export default function ItemSections({ kind, label, title, aside, sections, about, here = about, height, itemKey }) {
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
  const closedW = (k) => (k === about ? TAB_W : MINI_W);
  const openW = (k) => Math.max(240, w - sections.filter((s) => s.key !== k).reduce((n, s) => n + closedW(s.key), 0) - (k === sections[0].key ? 0 : 1));
  const at = (k) => sections.findIndex((s) => s.key === k);
  // ON A PHONE THEY STACK, as a task's sections do under STACK_BELOW (trust audit R1, 2026-10-28): slim side tabs left a report 240px wide
  const stacked = w > 0 && w < STACK_BELOW;
  return (
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
              <SectionHead sec={s} />
              {s.body}
            </Box>
          </Box>
        ) : (
          <Box key={s.key} data-tq-slot={s.key} data-tq-open={open === s.key ? "" : undefined}
            sx={{ ...SLOT(open === s.key, closedW(s.key)), ...(i ? { borderLeft: `1px solid ${FOCUS_EDGE}` } : {}) }}>
            {open !== s.key && <SectionTab sec={s} lines={s.lines || []} foot={s.foot || ""} icon={s.icon} here={here === s.key && open !== here}
              mini={closedW(s.key) === MINI_W} before={at(s.key) < at(open)} onOpen={() => setOpen(s.key)} />}
            <Box role="region" aria-label={s.name} aria-hidden={open !== s.key ? true : undefined} className="tq-item-sec"
              sx={{ ...SECTION(open === s.key, w ? openW(s.key) : "100%"), gap: 1.5 }}>
              <SectionHead sec={s} />
              {s.body}
            </Box>
          </Box>
        ))}
      </Box>
    </Box>
  );
}
