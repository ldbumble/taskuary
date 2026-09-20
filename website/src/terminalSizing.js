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

// FitAddon can land exactly on a fractional cell boundary that the browser then rounds down when
// painting. Reserve one row so a full-screen TUI's status/prompt line is always inside the pane.
// This is shared by Claude, Codex and every other CLI rendered through xterm.
export const safeTerminalRows = (rows) => Math.max(2, Math.floor(rows || 0) - 1);

// The server barrier and xterm parser are independent. Seeing either one alone is not enough
// to uncover a replaying pane - and a pane already uncovered is never "revealed" again: the
// reveal focuses the terminal, so re-running it on every live frame stole the keyboard from
// whatever the owner was typing into.
export const canRevealTerminal = (readySeen, pendingWrites, lifted = false) => !lifted && !!readySeen && pendingWrites === 0;

// ConPTY keeps its viewport TOP-anchored when the pty grows: the cursor stays on its row and the
// new rows below are blank. xterm's default does the opposite - it pulls scrollback back into the
// viewport and moves the cursor down with it. A triage-started coder opens at the server's 32x110,
// the task page then fits ~60 rows, and the CLI's next absolute cursor move (row 32, where ConPTY
// still is) lands mid-pane over lines the pane already showed: "two frames at once" (2026-09-18).
// xterm's windowsPty option switches its grow to ConPTY's model. The server says which pty it is
// on every geom frame; an older server says nothing, and the default stands.
export const adoptPtyGeometry = (term, geom) => {
  if (typeof geom?.conpty !== "boolean") return;
  term.options.windowsPty = geom.conpty ? { backend: "conpty" } : {};
};
