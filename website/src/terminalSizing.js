// Return the new PTY geometry only when it actually changed. ResizeObserver may report the same
// box repeatedly; forwarding duplicates makes full-screen terminal apps repaint for no reason.
export const changedTerminalSize = (previous, rows, cols) => {
  const current = `${rows}x${cols}`;
  return current === previous ? null : current;
};

// A mounted task pane is kept in the DOM while another app tab is open. display:none reports
// a zero-sized box; fitting and forwarding that transient geometry makes a full-screen TUI
// repaint once while hidden and again when the owner returns.
export const usableTerminalBox = (width, height) => width >= 80 && height >= 40;

// The server barrier and xterm parser are independent. Seeing either one alone is not enough
// to uncover a replaying pane.
export const canRevealTerminal = (readySeen, pendingWrites) => !!readySeen && pendingWrites === 0;
