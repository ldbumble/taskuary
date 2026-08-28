// Real terminals in the app: xterm.js over a websocket over a pty. A session belongs to the
// task it is working, and it is shown where that task is worked: the task page, and - for a
// "Get AI to set it up" session - the connector card whose guide it is following (still a task
// on the Board). No terminal tab, no dock at the bottom of the screen. The pty lives
// server-side, so leaving the page (or reloading) never kills it - coming back re-attaches.
import React, { useEffect, useRef, useState } from "react";
import { Box, CircularProgress, Typography } from "@mui/material";
import { Terminal } from "@xterm/xterm";
import { FitAddon } from "@xterm/addon-fit";
import { WebLinksAddon } from "@xterm/addon-web-links";
import { Unicode11Addon } from "@xterm/addon-unicode11";
import "@xterm/xterm/css/xterm.css";
import { BORDER, CATPPUCCIN, FAINT, PANEL, XTERM_THEME, mono } from "./theme.jsx";
import { MicButton } from "./ui.jsx";

// Programming fonts first: agent TUIs draw boxes and progress bars out of block glyphs,
// which only line up in a font with real box-drawing coverage.
const TERM_FONT = "'Cascadia Mono', 'JetBrains Mono', 'Fira Code', Consolas, 'Courier New', monospace";

// The palettes people actually run their terminals in. A CLI like codex has no theme command
// of its own - it paints with the TERMINAL's colors - so this picker is how you restyle it
// (claude additionally themes itself; see ThemeHint). Choice sticks per browser.
const THEMES = {
  "Catppuccin Mocha": XTERM_THEME,
  Dracula: { background: "#282a36", foreground: "#f8f8f2", cursor: "#f8f8f2", selectionBackground: "#44475a",
    black: "#21222c", red: "#ff5555", green: "#50fa7b", yellow: "#f1fa8c", blue: "#bd93f9",
    magenta: "#ff79c6", cyan: "#8be9fd", white: "#f8f8f2", brightBlack: "#6272a4", brightRed: "#ff6e6e",
    brightGreen: "#69ff94", brightYellow: "#ffffa5", brightBlue: "#d6acff", brightMagenta: "#ff92df",
    brightCyan: "#a4ffff", brightWhite: "#ffffff" },
  "Tokyo Night": { background: "#1a1b26", foreground: "#c0caf5", cursor: "#c0caf5", selectionBackground: "#33467c",
    black: "#15161e", red: "#f7768e", green: "#9ece6a", yellow: "#e0af68", blue: "#7aa2f7",
    magenta: "#bb9af7", cyan: "#7dcfff", white: "#a9b1d6", brightBlack: "#414868", brightRed: "#f7768e",
    brightGreen: "#9ece6a", brightYellow: "#e0af68", brightBlue: "#7aa2f7", brightMagenta: "#bb9af7",
    brightCyan: "#7dcfff", brightWhite: "#c0caf5" },
  "Gruvbox Dark": { background: "#282828", foreground: "#ebdbb2", cursor: "#ebdbb2", selectionBackground: "#504945",
    black: "#282828", red: "#cc241d", green: "#98971a", yellow: "#d79921", blue: "#458588",
    magenta: "#b16286", cyan: "#689d6a", white: "#a89984", brightBlack: "#928374", brightRed: "#fb4934",
    brightGreen: "#b8bb26", brightYellow: "#fabd2f", brightBlue: "#83a598", brightMagenta: "#d3869b",
    brightCyan: "#8ec07c", brightWhite: "#ebdbb2" },
  "One Dark": { background: "#282c34", foreground: "#abb2bf", cursor: "#abb2bf", selectionBackground: "#3e4451",
    black: "#282c34", red: "#e06c75", green: "#98c379", yellow: "#e5c07b", blue: "#61afef",
    magenta: "#c678dd", cyan: "#56b6c2", white: "#abb2bf", brightBlack: "#5c6370", brightRed: "#e06c75",
    brightGreen: "#98c379", brightYellow: "#d19a66", brightBlue: "#61afef", brightMagenta: "#c678dd",
    brightCyan: "#56b6c2", brightWhite: "#ffffff" },
};
const savedTheme = () => {
  try { const n = localStorage.getItem("tq-term-theme"); return THEMES[n] ? n : "Catppuccin Mocha"; }
  catch { return "Catppuccin Mocha"; }
};

// How much of the run fits on screen. A coding CLI writes far more than it asks, so the
// useful size here is smaller than a font you would READ prose at - most of these lines are
// scanned, not read, and every point of size costs you rows of context. 7 and 8 exist for
// exactly that: at 7px a 700px pane holds ~90 rows instead of ~50, which is the difference
// between watching a diff go past and reading it.
const SIZES = [7, 8, 9, 10, 11, 12, 12.5, 14];
const DEFAULT_SIZE = 10;
// Changing DEFAULT_SIZE moves nobody who has already used the app: their old choice is in
// localStorage and wins forever. Bumping this rev re-defaults every browser ONCE, then their
// next A-/A+ sticks as usual - the only way a new default reaches people who are already here.
const SIZE_REV = "2";
const savedSize = () => {
  try {
    if (localStorage.getItem("tq-term-size-rev") !== SIZE_REV) {
      localStorage.setItem("tq-term-size-rev", SIZE_REV);
      localStorage.setItem("tq-term-size", String(DEFAULT_SIZE));
      return DEFAULT_SIZE;
    }
    const n = parseFloat(localStorage.getItem("tq-term-size"));
    return SIZES.includes(n) ? n : DEFAULT_SIZE;
  } catch { return DEFAULT_SIZE; }          // private mode: the default every time, which is fine
};
// Leading has to come down WITH the size or the gain is thrown away: 1.15 line-height on 7px
// text spends a fifth of the pane on whitespace between lines nobody is reading closely.
const leading = (n) => (n <= 8 ? 1.0 : n <= 10 ? 1.08 : 1.15);

const wsUrl = (sid) => {
  const t = localStorage.getItem("taskuary_token");
  return `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/api/terminals/${sid}/ws${t ? `?token=${encodeURIComponent(t)}` : ""}`;
};

// One live session. Mounts xterm once, streams both ways, resizes the pty to the pane.
// The effect keys on `sid` ALONE: the task page re-renders every few seconds while a run
// polls, and taking a fresh callback identity as a dependency tore the terminal down and
// rebuilt it on every one of those renders - which is what "it just flashes" was.
export const TerminalPane = ({ sid, height = "70vh", onExit }) => {
  const host = useRef(null);
  const exit = useRef(onExit);
  exit.current = onExit;
  const [state, setState] = useState("connecting");
  // Reopening a task replays the whole scrollback in one write, and xterm parses it with the
  // viewport following along - so you watched the session scroll from its first line down to
  // the bottom, every time. The pane stays curtained until the server says the live screen is
  // up (see the 'ready' frame); nobody needs to watch their own history rewind.
  const [restoring, setRestoring] = useState(false);
  const [themeName, setThemeName] = useState(savedTheme);
  const [size, setSize] = useState(savedSize);
  const termRef = useRef(null);
  const refit = useRef(null);                        // set at mount: refit + tell the pty
  const sendRef = useRef(null);                      // the socket's send, for the mic: dictated text is typed into the session
  useEffect(() => {                                  // live restyle, no reconnect
    try { localStorage.setItem("tq-term-theme", themeName); } catch { /* private mode */ }
    if (termRef.current) termRef.current.options.theme = THEMES[themeName];
  }, [themeName]);
  // resizing the FONT resizes the terminal: same pane, more rows. The pty has to be told, or
  // the CLI keeps painting for the old window and its TUI wraps against nothing.
  useEffect(() => {
    try { localStorage.setItem("tq-term-size", String(size)); } catch { /* private mode */ }
    if (!termRef.current) return;
    termRef.current.options.fontSize = size;
    termRef.current.options.lineHeight = leading(size);
    // one frame late on purpose: fit() divides the pane by the CHARACTER size, and xterm has
    // not remeasured the glyph yet on this tick - refitting now just recomputes the old rows
    const id = requestAnimationFrame(() => refit.current?.());
    return () => cancelAnimationFrame(id);
  }, [size]);
  useEffect(() => {
    const term = new Terminal({ fontSize: savedSize(), fontFamily: TERM_FONT, fontWeightBold: 600,
      theme: THEMES[savedTheme()], cursorBlink: true, cursorStyle: "bar", scrollback: 10000,
      allowProposedApi: true, drawBoldTextInBrightColors: false, letterSpacing: 0, lineHeight: leading(savedSize()) });
    termRef.current = term;
    const fit = new FitAddon();
    term.loadAddon(fit);
    term.loadAddon(new WebLinksAddon((_e, uri) => window.open(uri, "_blank", "noopener")));
    const uni = new Unicode11Addon();
    term.loadAddon(uni);
    term.unicode.activeVersion = "11";              // emoji + box glyphs measure correctly
    term.open(host.current);
    // No WebGL renderer here on purpose: it renders nothing at all on software-GL stacks
    // (WebView2 without a GPU, remote desktop, headless), and a blank terminal is a much
    // worse failure than a few dropped frames. The DOM renderer draws the same colors.
    fit.fit();
    const ws = new WebSocket(wsUrl(sid));
    const send = (m) => ws.readyState === 1 && ws.send(JSON.stringify(m));
    sendRef.current = send;
    ws.onopen = () => { setState("live"); send({ type: "resize", rows: term.rows, cols: term.cols }); };
    // a server that never sends 'ready' (older build, a child that dies mid-redraw) must not
    // leave the curtain down over a working session - the pane opens anyway
    let bail = null;
    const lift = () => { clearTimeout(bail); term.scrollToBottom(); setRestoring(false); };
    ws.onmessage = (e) => {
      const m = JSON.parse(e.data);
      if (m.type === "out") {
        if (m.replay) { setRestoring(true); bail = setTimeout(lift, 4000); }
        term.write(m.data, m.replay ? () => term.scrollToBottom() : undefined);
      }
      else if (m.type === "ready") lift();
      else if (m.type === "exit") { setState("exited"); term.write("\r\n\x1b[90m— process exited —\x1b[0m\r\n"); exit.current?.(); lift(); }
    };
    ws.onclose = () => setState((s) => (s === "exited" ? s : "closed"));
    term.onData((d) => send({ type: "in", data: d }));
    const onResize = () => { fit.fit(); send({ type: "resize", rows: term.rows, cols: term.cols }); };
    refit.current = onResize;                       // the size picker drives the same path
    window.addEventListener("resize", onResize);
    const ro = new ResizeObserver(onResize);
    ro.observe(host.current);
    // The wheel never leaves the terminal. When xterm has nothing to scroll (an idle TUI in the
    // alternate buffer, or a CLI that exited) it lets the event BUBBLE, so scrolling over the
    // session yanked the whole page instead - "scroll defaults to page". A live TUI still gets
    // the wheel first (xterm consumes it before this fires); this only swallows the leftovers.
    const el = host.current;
    const trap = (e) => e.preventDefault();
    el.addEventListener("wheel", trap, { passive: false });
    // ...and the scrollbar only shows when there is genuinely something behind it: a TUI in the
    // alternate buffer scrolls ITSELF (the wheel is forwarded to it), so xterm's own bar would be
    // a full-height slider that drags nothing.
    const gauge = () => {
      const scrollable = term.buffer.active.type === "normal" && term.buffer.active.length > term.rows;
      el.style.setProperty("--sbar", scrollable ? "1" : "0");
    };
    gauge();
    const d1 = term.onScroll(gauge), d2 = term.onRender(gauge);
    term.focus();
    return () => { window.removeEventListener("resize", onResize); ro.disconnect(); clearTimeout(bail);
      el.removeEventListener("wheel", trap); d1.dispose(); d2.dispose(); ws.close(); term.dispose(); };
  }, [sid]);
  return (
    <Box sx={{ position: "relative", border: `1px solid ${BORDER}`, borderRadius: 2, overflow: "hidden",
      bgcolor: THEMES[themeName].background }}>
      {/* the pane's two knobs, discreet until hovered: how it is painted, and how much of the
          run fits in it. Both restyle ANY CLI in the pane - codex and claude included - and
          both stick per browser. */}
      <Box sx={{ position: "absolute", top: 5, right: 10, zIndex: 2, display: "flex", alignItems: "center", gap: 0.5,
        opacity: 0.62, "&:hover": { opacity: 1 }, transition: "opacity .15s" }}>
        {/* one step smaller is a couple more rows of the run without touching the layout -
            far cheaper than scrolling back for what just went past */}
        <Box component="button" onClick={() => setSize((n) => SIZES[Math.max(0, SIZES.indexOf(n) - 1)])}
          disabled={size === SIZES[0]} title="smaller text — more of the run on screen"
          sx={{ ...mono, fontSize: 11, lineHeight: 1, px: 0.5, py: 0.25, bgcolor: "transparent", color: "#867f74",
            border: "none", cursor: "pointer", "&:disabled": { opacity: 0.3, cursor: "default" },
            "&:hover:not(:disabled)": { color: "#e1dcd5" } }}>A−</Box>
        {/* the number, so the range is DISCOVERABLE: two unlabelled letters gave no way to
            tell whether you were already at the smallest or had five steps left */}
        <Typography sx={{ ...mono, fontSize: 9.5, color: "#867f74", minWidth: 16, textAlign: "center",
          fontVariantNumeric: "tabular-nums" }}>{size}</Typography>
        <Box component="button" onClick={() => setSize((n) => SIZES[Math.min(SIZES.length - 1, SIZES.indexOf(n) + 1)])}
          disabled={size === SIZES[SIZES.length - 1]} title="bigger text"
          sx={{ ...mono, fontSize: 13, lineHeight: 1, px: 0.5, py: 0.25, bgcolor: "transparent", color: "#867f74",
            border: "none", cursor: "pointer", "&:disabled": { opacity: 0.3, cursor: "default" },
            "&:hover:not(:disabled)": { color: "#e1dcd5" } }}>A+</Box>
        {/* dictate to the agent: the words are typed into the session as keystrokes, no Enter -
            you read them and press it yourself */}
        <MicButton size={15} sx={{ color: "#867f74", p: 0.25, "&:hover": { color: "#e1dcd5" } }}
          onText={(t) => { sendRef.current?.({ type: "in", data: t }); termRef.current?.focus(); }} />
        <Box component="select" value={themeName} onChange={(e) => setThemeName(e.target.value)}
          title="terminal palette"
          sx={{ ...mono, fontSize: 10, bgcolor: "transparent", color: "#867f74", border: "none",
            outline: "none", cursor: "pointer" }}>
          {Object.keys(THEMES).map((n) => <option key={n} value={n} style={{ color: "#111" }}>{n}</option>)}
        </Box>
      </Box>
      {/* A scrollbar on the session itself, the way a console has one.
          xterm 6 does not use a native scrollbar: it embeds VS Code's scrollable element, which
          AUTO-HIDES - the bar ships as `class="invisible scrollbar vertical fade"`, opacity 0 and
          pointer-events none. So the slider was there the whole time, correctly sized and
          positioned, and simply could not be seen or grabbed; the only scrollbar on screen was the
          page's, which is why reaching the scrollback meant scrolling the whole window instead.
          Colour comes from XTERM_THEME - this keeps the vertical bar on permanently. */}
      <Box ref={host} sx={{ height, p: 1, "& .xterm": { height: "100%" },
        "& .xterm-scrollable-element > .scrollbar.vertical": {
          // pinned visible ONLY while scrollback exists (--sbar, set from the buffer state):
          // an alternate-screen TUI scrolls itself, and a dead full-height slider is a lie
          opacity: "var(--sbar, 0) !important", pointerEvents: "auto !important", visibility: "visible !important",
          // a visible TRACK, not just a slider: a bare thumb floating on a dark pane still reads
          // as "there is no scrollbar" - the channel is what says the pane scrolls
          background: "rgba(255,255,255,.06)", borderLeft: "1px solid rgba(255,255,255,.08)" },
        "& .xterm-scrollable-element > .scrollbar.vertical > .slider": {
          borderRadius: 99, width: "8px !important", marginLeft: "3px", transition: "background .15s" },
        "& .xterm-scrollable-element > .scrollbar.vertical:hover > .slider": { width: "11px !important" } }} />
      {/* the curtain: the pane's own background, so a reopened session looks like it was
          simply already there - and it lifts on the live screen, scrolled to the bottom */}
      {restoring && (
        <Box sx={{ position: "absolute", inset: 0, zIndex: 1, display: "flex", alignItems: "center",
          justifyContent: "center", gap: 1, bgcolor: THEMES[themeName].background }}>
          <CircularProgress size={13} sx={{ color: CATPPUCCIN.yellow }} />
          <Typography variant="caption" sx={{ ...mono, fontSize: 10.5, color: CATPPUCCIN.yellow }}>
            restoring the session…
          </Typography>
        </Box>
      )}
      {state !== "live" && (
        <Typography variant="caption" sx={{ ...mono, position: "absolute", top: 6, right: 130, fontSize: 10,
          color: state === "exited" ? CATPPUCCIN.green : CATPPUCCIN.yellow }}>
          {state}
        </Typography>
      )}
    </Box>
  );
};

// Taskuary's terminals default to Catppuccin Mocha, switchable per pane (top-right picker)
// - that palette is what styles codex and every other CLI, since a TUI paints with the
// terminal's colors. Claude Code additionally themes ITSELF, which is set inside Claude
// Code - a command to run there, not something to write into somebody's global CLI config
// behind their back.
export const ThemeHint = () => (
  <Typography variant="caption" sx={{ color: FAINT, display: "block", mt: 1.5 }}>
    The session's top-right corner holds both knobs: A− / A+ set the text size, 7px to 14px with
    the current one shown between them (7 fits roughly twice the run on screen — the leading
    tightens with it, so the rows are gained rather than spent on whitespace), and the picker switches the terminal
    palette (Catppuccin, Dracula, Tokyo Night, Gruvbox, One Dark) — that restyles codex and any
    other CLI, since a TUI paints with the terminal's colors. To match Catppuccin inside Claude
    Code itself, run{" "}
    <Box component="code" sx={{ ...mono, bgcolor: PANEL, border: `1px solid ${BORDER}`, borderRadius: 1,
      px: 0.75, py: 0.25, fontSize: 11, cursor: "pointer" }}
      title="click to copy"
      onClick={() => navigator.clipboard?.writeText("/plugin install catppuccin@matcra587/claude-themes")}>
      /plugin install catppuccin@matcra587/claude-themes
    </Box>{" "}
    in a Claude Code session, then pick a flavor with /theme.
  </Typography>
);
