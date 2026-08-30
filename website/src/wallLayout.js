// Pure wall-layout operations live here so drag behavior can be verified without a browser.
export const movePane = (order, from, target) => {
  if (!from || !target || from === target) return order;
  const next = [...order], fromAt = next.indexOf(from), targetAt = next.indexOf(target);
  if (fromAt < 0 || targetAt < 0) return order;
  next.splice(targetAt, 0, next.splice(fromAt, 1)[0]);
  return next;
};

export const resizedPaneHeight = (startHeight, startY, clientY, minimum) =>
  Math.max(minimum, Math.round(startHeight + clientY - startY));

// Fill the wall vertically according to what is actually on it. Reserving two rows even when
// every pane fits across one row leaves half the screen blank (most obvious at 3× with 3 agents).
// At most two rows share the viewport; further rows scroll with the same useful pane height.
export const defaultPaneHeight = (paneCount, columns) => {
  const rows = Math.min(2, Math.max(1, Math.ceil(paneCount / Math.max(1, columns))));
  const gaps = (rows - 1) * 12;
  return `max(300px, calc((100vh - ${104 + gaps}px) / ${rows}))`;
};
