// THE ITEM ON THE TABLE (the canvas redesign, docs/superpowers/specs/2026-09-29-assistant-canvas-redesign-design.md):
// an item with a task behind it is shown by the Tasks tab's own task view (TaskPage) inside the conversation, at the
// canvas's width and the chat's full height - Task, Agent work, Close out, with their bars and the agent's pane.
//
// ONE HEIGHT, ALWAYS. Expand hides the conversation around the view; it never changes the view's own box. A pty grown
// after it has output corrupts the pane (ConPTY keeps a grown viewport top-anchored - see terminal.remember_geometry),
// so the terminal inside is sized once, for the whole canvas, and nothing here can grow it afterwards.
import React, { useEffect, useRef, useState } from "react";
import { Box, Button, Typography } from "@mui/material";
import TaskPage from "./TaskPage.jsx";

// the height the view takes: the chat body's own, less its padding - the same in both states (see above). Said in CSS,
// against the chat body as a SIZE container (assistantView.css .tq-chat-body): a height measured in script was stale
// whenever the body was measured hidden or before it settled, and the view sat at its 420px floor under a screen of
// empty canvas (the owner, 2026-09-29: "fill up more width and more height ... see more in one screen")
export const CANVAS_ITEM_HEIGHT = "max(420px, calc(100cqh - 26px))";

// an item the canvas shows as a task view: it has a task, and it is not a proposal, a set-up step or a batch
export const showsTask = (card, kind) => !!card?.tid && !["proposal", "setup", "walk", "brief", "fyis", "meeting"].includes(kind);

// ON A PHONE the view is the SCREEN's height from the start, and Expand pins that same box over the page with a back
// arrow - full screen, and still never a resize: the box it pins is measured in place, the same width and height.
export const phoneItemHeight = (innerHeight) => Math.max(420, Math.round((innerHeight || 0) - 16));

export default function CanvasItem({ card, height, expanded, onExpand, onNext, busy, onFold, onAfter, onListChanged, onChanged, onGoReports, phone = false }) {
  // a task opened "and start it" or "with this dialog up" (TaskHubPage.openTask): once, then it is spent
  const [auto, setAuto] = useState(card.autostart ? { taskId: card.tid, ...card.autostart } : null);
  const [act, setAct] = useState(card.act ? { taskId: card.tid, act: card.act } : null);
  // a view put on the table is brought into view whole - the chat's own scroll pinned its bottom, which left a task opened
  // by a link showing only its heading under a screenful of earlier lines
  const box = useRef(null);
  useEffect(() => { box.current?.scrollIntoView({ block: "start" }); }, [card.key]);
  const [phoneH] = useState(() => phoneItemHeight(typeof window === "undefined" ? 0 : window.innerHeight));
  // where the box sits in the page, taken the moment it is pinned - the pinned box keeps exactly this width
  const [pin, setPin] = useState(null);
  useEffect(() => {
    if (!(phone && expanded)) { setPin(null); return; }
    const r = box.current?.getBoundingClientRect();
    if (r) setPin({ left: r.left, width: r.width });   // exact: a rounded width re-wrapped the strip and moved the pane by 2px
  }, [phone, expanded]);
  const h = phone ? phoneH : height;
  return (
    <>
    {pin && <Box aria-hidden sx={{ position: "fixed", inset: 0, zIndex: 1349, bgcolor: "#f6f4f1" }} />}
    <Box ref={box} data-tq-canvas-item={card.key} data-tq-pinned={pin ? "" : undefined}
      sx={{ height: h, display: "flex", flexDirection: "column", minWidth: 0, scrollMarginTop: "8px",
        ...(pin ? { position: "fixed", top: 8, left: pin.left, width: pin.width, zIndex: 1350 } : {}) }}>
      <Box sx={{ flex: 1, minHeight: 0, display: "flex" }}>
      <TaskPage taskId={card.tid} canvas active autostart={auto} onAutostarted={() => setAuto(null)}
        openAct={act} onActOpened={() => setAct(null)}
        expanded={expanded} onExpand={onExpand}
        onClose={onFold} onListChanged={onListChanged} onChanged={onChanged} onGoReports={onGoReports}
        // closed, put away or deleted here, the walk moves on - the same as Done on a walk card
        onSelect={(id) => { if (!id) onAfter(); }}
        onFinish={async (status, close) => { await close(); onAfter(); }}
        onReminded={(out) => { if (out?.remindAt) onAfter(); }} backArrow={phone} />
      </Box>
      {/* NEXT, UNDER THE VIEW, where the walk has always put it (the owner, 2026-09-29: "the next goes on top right corner
          and not on the bottom like it used to be ... it's not very easy to see"). It is the walk's ONE button on a task:
          everything else - done, remind, hand off, reply - is the task view's own, right above it. */}
      <Box sx={{ flexShrink: 0, display: "flex", alignItems: "center", gap: 1.5, pt: 1, pb: 0.25, px: 0.5 }}>
        <Button variant="contained" disableElevation data-tq-next="" disabled={busy} onClick={onNext}
          sx={{ height: 38, px: 3, borderRadius: 99, fontSize: 13.5, fontWeight: 700, bgcolor: "#55697a", "&:hover": { bgcolor: "#41525f" } }}>
          Next
        </Button>
        <Typography sx={{ fontSize: 12, color: "#8a847a" }} noWrap>puts this one down, still yours, and brings the next</Typography>
      </Box>
    </Box>
    </>
  );
}
