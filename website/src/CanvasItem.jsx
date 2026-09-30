// THE ITEM ON THE TABLE (the canvas redesign, docs/superpowers/specs/2026-09-29-assistant-canvas-redesign-design.md):
// an item with a task behind it is shown by the Tasks tab's own task view (TaskPage) inside the conversation, at the
// canvas's width and the chat's full height - Task, Agent work, Close out, with their bars and the agent's pane.
//
// ONE HEIGHT, ALWAYS. Expand hides the conversation around the view; it never changes the view's own box. A pty grown
// after it has output corrupts the pane (ConPTY keeps a grown viewport top-anchored - see terminal.remember_geometry),
// so the terminal inside is sized once, for the whole canvas, and nothing here can grow it afterwards.
import React from "react";
import { Box } from "@mui/material";
import TaskPage from "./TaskPage.jsx";

// the height the view takes: the chat body's own, less its padding - the same in both states (see above)
export const canvasItemHeight = (bodyHeight) => Math.max(420, Math.round((bodyHeight || 0) - 26));

// an item the canvas shows as a task view: it has a task, and it is not a proposal, a set-up step or a batch
export const showsTask = (card, kind) => !!card?.tid && !["proposal", "setup", "walk", "brief", "fyis", "meeting"].includes(kind);

export default function CanvasItem({ card, height, expanded, onExpand, onNext, busy, onFold, onAfter, onListChanged, onChanged, onGoReports }) {
  return (
    <Box data-tq-canvas-item={card.key} sx={{ height, display: "flex", minWidth: 0 }}>
      <TaskPage taskId={card.tid} canvas active
        onNext={onNext} nextBusy={busy} expanded={expanded} onExpand={onExpand}
        onClose={onFold} onListChanged={onListChanged} onChanged={onChanged} onGoReports={onGoReports}
        // closed, put away or deleted here, the walk moves on - the same as Done on a walk card
        onSelect={(id) => { if (!id) onAfter(); }}
        onFinish={async (status, close) => { await close(); onAfter(); }}
        onReminded={(out) => { if (out?.remindAt) onAfter(); }} />
    </Box>
  );
}
