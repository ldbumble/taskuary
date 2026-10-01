// THE ITEM ON THE TABLE (the canvas redesign, docs/superpowers/specs/2026-09-29-assistant-canvas-redesign-design.md):
// an item with a task behind it is shown by the Tasks tab's own task view (TaskPage) inside the conversation, at the
// canvas's width and the chat's full height - Task, Agent work, Close out, with their bars and the agent's pane.
//
// ONE HEIGHT, ALWAYS. Expand hides the conversation around the view; it never changes the view's own box. A pty grown
// after it has output corrupts the pane (ConPTY keeps a grown viewport top-anchored - see terminal.remember_geometry),
// so the terminal inside is sized once, for the whole canvas, and nothing here can grow it afterwards.
import React, { useEffect, useRef, useState } from "react";
import { Box } from "@mui/material";
import TaskPage from "./TaskPage.jsx";
import ActionRow from "./ActionRow.jsx";
import { useHost, useVerbs } from "./actionRow.js";

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

export default function CanvasItem({ card, height, expanded, onExpand, onNext, busy, onFold, onAfter, onLeave, onStay, onListChanged, onChanged, onGoReports, phone = false }) {
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
  // NEXT, in the row: the walk's ONE button on a task (the owner, 2026-09-29), the same handler as the button it replaces
  useHost(phone);
  useVerbs("next", [{ id: "next", group: "next", label: "Next", disabled: !!busy, run: () => onNext(), title: "Puts this one down, still yours, and brings the next" }]);
  return (
    <>
    {pin && <Box aria-hidden sx={{ position: "fixed", inset: 0, zIndex: 1349, bgcolor: "#f6f4f1" }} />}
    <Box ref={box} data-tq-canvas-item={card.key} data-tq-pinned={pin ? "" : undefined}
      sx={{ height: h, display: "flex", flexDirection: "column", minWidth: 0, scrollMarginTop: "8px",
        // ...but a view with NO PANE in it (a stopped agent, a note, a closed task) is only as tall as what it says: the full
        // height left a screen of blank canvas under three short bars (the owner, 2026-09-30: "what's with extra space???").
        // A pane - terminal, agent chat, browser - still gets the one height it is sized for, so the pty is never grown.
        ...(!pin && !phone ? { "&:not(:has(.xterm, [class*='tq-aui'], canvas, iframe))": { height: "auto", maxHeight: h } } : {}),
        ...(pin ? { position: "fixed", top: 8, left: pin.left, width: pin.width, zIndex: 1350 } : {}) }}>
      <Box sx={{ flex: "1 1 auto", minHeight: 0, display: "flex" }}>
      <TaskPage taskId={card.tid} canvas active autostart={auto} onAutostarted={() => setAuto(null)}
        openAct={act} onActOpened={() => setAct(null)}
        expanded={expanded} onExpand={onExpand}
        onClose={onFold} onListChanged={onListChanged} onChanged={onChanged} onGoReports={onGoReports}
        // closed, put away or deleted here, the walk moves on - the same as Done on a walk card
        onSelect={(id) => { if (!id) onAfter(); }}
        onFinish={async (status, close) => { await close(); onAfter(); }}
        onReminded={(out) => { if (out?.remindAt) onAfter(); }} backArrow={phone}
        // Mark done and Remind me put the task down AT THE PRESS, as Next does; a failure puts it back with the reason
        onLeave={onLeave} onStay={onStay} />
      </Box>
      {/* THE BUTTONS ARE NOT HERE (layout B, 2026-09-30): the view registers its verbs and Next, and the ONE row above the chat line
          draws them. On a phone the same row rides at the view's foot instead, in both states - the pinned full-screen view covers
          the dock, and the box is sized once, so Expand must not add or take away a row. */}
      {phone && <ActionRow inline />}
    </Box>
    </>
  );
}
