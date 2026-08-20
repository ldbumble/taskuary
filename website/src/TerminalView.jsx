// Real terminals in the app: xterm.js over a websocket over a pty. There is exactly ONE
// place they live - the task page. No terminal tab, no dock at the bottom of the screen: a
// session belongs to the task it is working. The pty lives server-side, so leaving the task
// (or reloading) never kills it - reopening the task re-attaches to the running session.
import React, { useEffect, useRef, useState } from "react";
import { Box, Typography } from "@mui/material";
import { Terminal } from "@xterm/xterm";
import { FitAddon } from "@xterm/addon-fit";
import { WebLinksAddon } from "@xterm/addon-web-links";
import { Unicode11Addon } from "@xterm/addon-unicode11";
import "@xterm/xterm/css/xterm.css";
import { BORDER, CATPPUCCIN, FAINT, PANEL, XTERM_THEME, mono } from "./theme.jsx";

// Programming fonts first: agent TUIs draw boxes and progress bars out of block glyphs,
// which only line up in a font with real box-drawing coverage.
const TERM_FONT = "'Cascadia Mono', 'JetBrains Mono', 'Fira Code', Consolas, 'Courier New', monospace";

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
  useEffect(() => {
    const term = new Terminal({ fontSize: 12.5, fontFamily: TERM_FONT, fontWeightBold: 600,
      theme: XTERM_THEME, cursorBlink: true, cursorStyle: "bar", scrollback: 10000,
      allowProposedApi: true, drawBoldTextInBrightColors: false, letterSpacing: 0, lineHeight: 1.15 });
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
    ws.onopen = () => { setState("live"); send({ type: "resize", rows: term.rows, cols: term.cols }); };
    ws.onmessage = (e) => {
      const m = JSON.parse(e.data);
      if (m.type === "out") term.write(m.data);
      else if (m.type === "exit") { setState("exited"); term.write("\r\n\x1b[90m— process exited —\x1b[0m\r\n"); exit.current?.(); }
    };
    ws.onclose = () => setState((s) => (s === "exited" ? s : "closed"));
    term.onData((d) => send({ type: "in", data: d }));
    const onResize = () => { fit.fit(); send({ type: "resize", rows: term.rows, cols: term.cols }); };
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
    return () => { window.removeEventListener("resize", onResize); ro.disconnect();
      el.removeEventListener("wheel", trap); d1.dispose(); d2.dispose(); ws.close(); term.dispose(); };
  }, [sid]);
  return (
    <Box sx={{ position: "relative", border: `1px solid ${BORDER}`, borderRadius: 2, overflow: "hidden", bgcolor: CATPPUCCIN.bg }}>
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
      {state !== "live" && (
        <Typography variant="caption" sx={{ ...mono, position: "absolute", top: 6, right: 10, fontSize: 10,
          color: state === "exited" ? CATPPUCCIN.green : CATPPUCCIN.yellow }}>
          {state}
        </Typography>
      )}
    </Box>
  );
};

// Taskuary paints its terminals in Catppuccin Mocha. Claude Code's own theme is set
// inside Claude Code, so this is a command to run there - not something to write into
// somebody's global CLI config behind their back.
export const ThemeHint = () => (
  <Typography variant="caption" sx={{ color: FAINT, display: "block", mt: 1.5 }}>
    Terminals here use the Catppuccin Mocha palette. To match it inside Claude Code itself,
    run{" "}
    <Box component="code" sx={{ ...mono, bgcolor: PANEL, border: `1px solid ${BORDER}`, borderRadius: 1,
      px: 0.75, py: 0.25, fontSize: 11, cursor: "pointer" }}
      title="click to copy"
      onClick={() => navigator.clipboard?.writeText("/plugin install catppuccin@matcra587/claude-themes")}>
      /plugin install catppuccin@matcra587/claude-themes
    </Box>{" "}
    in a Claude Code session, then pick a flavor with /theme.
  </Typography>
);
