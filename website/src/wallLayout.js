// Pure wall-layout operations live here so drag behavior can be verified without a browser.
export const movePane = (order, from, target) => {
  if (!from || !target || from === target) return order;
  const next = [...order], fromAt = next.indexOf(from), targetAt = next.indexOf(target);
  if (fromAt < 0 || targetAt < 0) return order;
  next.splice(targetAt, 0, next.splice(fromAt, 1)[0]);
  return next;
};

// Pointer dragging asks the document what pane is actually under the pointer. Unlike native
// HTML drag-and-drop this works the same way over xterm, nested SVGs, Chromium, Firefox and touch.
// Keep the DOM lookup here so the event wiring can be small and its important edge cases tested.
export const wallPaneAtPoint = (documentLike, x, y) => {
  const hit = documentLike?.elementFromPoint?.(x, y);
  const pane = hit?.closest?.("[data-wall-pane]");
  return pane?.getAttribute?.("data-wall-pane") || "";
};

export const resizedPaneHeight = (startHeight, startY, clientY, minimum) =>
  Math.max(minimum, Math.round(startHeight + clientY - startY));

// The server closes the pty before it writes the report and drafts the reply. Keep that one dead
// session visible while its wrap request is still running, otherwise the websocket exit removes
// the pane (and its spinner) while the actual close-out can still fail seconds later.
export const holdWrappingSessions = (fresh, current, wrapping) => {
  const seen = new Set((fresh || []).map((s) => s.sid));
  const held = (current || []).filter((s) => wrapping?.[s.sid] && !seen.has(s.sid));
  return [...(fresh || []), ...held];
};

export const withoutWallSession = (rows, sid) => (rows || []).filter((row) => row.sid !== sid);

// Fill the wall vertically according to what is actually on it. Reserving two rows even when
// every pane fits across one row leaves half the screen blank (most obvious at 3× with 3 agents).
// At most two rows share the viewport; further rows scroll with the same useful pane height.
export const defaultPaneHeight = (paneCount, columns) => {
  const rows = Math.min(2, Math.max(1, Math.ceil(paneCount / Math.max(1, columns))));
  const gaps = (rows - 1) * 12;
  return `max(300px, calc((100vh - ${104 + gaps}px) / ${rows}))`;
};
