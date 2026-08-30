// Return the new PTY geometry only when it actually changed. ResizeObserver may report the same
// box repeatedly; forwarding duplicates makes full-screen terminal apps repaint for no reason.
export const changedTerminalSize = (previous, rows, cols) => {
  const current = `${rows}x${cols}`;
  return current === previous ? null : current;
};
