// The agent's browser, live, beside its terminal. Frames come from agent-browser's screencast
// through the server relay (/api/terminals/:sid/browser/ws) and are drawn on a canvas; the
// owner can take the keyboard and mouse when a page asks for something an agent must never
// type - a password, a 2FA code - and hand it back. Snapshot files the frame on the task.
import React, { useEffect, useRef, useState } from "react";
import { Box, Typography } from "@mui/material";
import api from "./api.js";
import { BORDER, CATPPUCCIN, FAINT, PANEL, mono } from "./theme.jsx";
import { fitFrame, keyMessage, mouseMessage, parseMessage, shortUrl, viewportFor, viewportMoved,
  wheelMessage } from "./browserSplit.js";

const wsUrl = (sid) => {
  const t = localStorage.getItem("taskuary_token");
  return `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/api/terminals/${sid}/browser/ws${t ? `?token=${encodeURIComponent(t)}` : ""}`;
};

const btn = { ...mono, fontSize: 10.5, lineHeight: 1, px: 0.9, py: 0.45, borderRadius: 1, cursor: "pointer",
  border: `1px solid ${BORDER}`, bgcolor: "transparent", color: "#b9b2a8", "&:hover": { color: "#e1dcd5", borderColor: "#6b655c" } };

export default function BrowserPane({ sid, taskId, url: url0 = "", onFold, overlay = false }) {
  const box = useRef(null), canvas = useRef(null), sendRef = useRef(null), img = useRef(null), fit = useRef(null);
  const [live, setLive] = useState(false);
  const [url, setUrl] = useState(url0);
  const [driving, setDriving] = useState(false);
  // {t, bad}: a refusal must not read as a success - both used to come out in the same green
  const [note, setNote] = useState(null);
  // they tried to use a page they are only watching - the keyboard went nowhere and said nothing
  const [asked, setAsked] = useState(false);
  const drivingRef = useRef(false);
  drivingRef.current = driving;
  const held = useRef(0);       // the newest frame's seq while this tab is hidden: acked on return
  // null until the daemon says; false = it is up but holding no page, so no frame is coming
  const [attached, setAttached] = useState(null);
  const shape = useRef(null), shapeTimer = useRef(null);

  /* THE PAGE IS GIVEN THIS PANE'S SHAPE, so there is nothing left to letterbox. Debounced, because
     the splitter drags; ignored on failure, because a browser that will not resize still draws. */
  const fitViewport = () => {
    if (!box.current) return;
    const r = box.current.getBoundingClientRect();
    const want = viewportFor(r.width, r.height);
    if (!viewportMoved(shape.current, want)) return;
    clearTimeout(shapeTimer.current);
    shapeTimer.current = setTimeout(() => {
      shape.current = want;
      api.post(`/api/terminals/${sid}/browser/viewport`, want).catch(() => { shape.current = null; });
    }, 400);
  };

  // draw whatever the newest frame is into whatever size the box is now
  const paint = () => {
    const c = canvas.current, im = img.current;
    if (!c || !box.current) return;
    const r = box.current.getBoundingClientRect(), dpr = window.devicePixelRatio || 1;
    const bw = Math.max(1, Math.floor(r.width)), bh = Math.max(1, Math.floor(r.height));
    if (c.width !== bw * dpr || c.height !== bh * dpr) { c.width = bw * dpr; c.height = bh * dpr; c.style.width = `${bw}px`; c.style.height = `${bh}px`; }
    const ctx = c.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.fillStyle = "#101010"; ctx.fillRect(0, 0, bw, bh);
    if (!im) return;
    fit.current = fitFrame(im.naturalWidth, im.naturalHeight, bw, bh);
    const f = fit.current;
    ctx.drawImage(im, f.x, f.y, f.w, f.h);
  };

  useEffect(() => {
    let ws, closed = false, retry = null;
    const connect = () => {
      ws = new WebSocket(wsUrl(sid));
      const send = (m) => ws.readyState === 1 && ws.send(JSON.stringify(m));
      sendRef.current = send;
      ws.onmessage = (e) => {
        const m = parseMessage(e.data);
        if (!m) return;
        if (m.type === "frame") {
          /* A TAB NOBODY IS LOOKING AT was still paying for all of it: a 50KB decode and a repaint
             every 80ms, and an ack asking for the next one. The stream is ack-paced end to end
             (browserview.py), so holding the ack stops it at the source - Chrome stops capturing -
             and the frame it stopped on is acked the moment the tab comes back. */
          if (document.hidden) { held.current = m.seq; return; }
          const im = new Image();
          im.onload = () => {
            /* LIVE IS THE SOCKET, NOT THE CLOCK. This went grey four seconds after the last frame -
               and an ack-paced stream sends no frame at all while a page sits still, so a sign-in
               form the agent was waiting on read as a dead pane (2026-09-15). It is live until the
               relay closes; a page that is not moving is a page that is not moving. */
            img.current = im; paint(); setLive(true);
            send({ type: "ack", seq: m.seq });       // ack AFTER drawing: the next frame is the page now, not history
          };
          im.src = m.src;
        } else if (m.type === "url" && m.url) setUrl(m.url);
        /* THE STREAM SAYS WHEN IT HAS NOTHING, and we used to drop that on the floor. An
           agent-browser daemon answers its screencast port the moment it launches, whether or not
           a page was ever opened in it - browserview.state() calls that "open", the relay
           connects, and the daemon's first message is {"connected": false, "screencasting":
           false}. No frame ever follows. The pane drew an empty canvas and nothing else, so a
           browser that had simply never been navigated looked identical to a broken one (the
           owner, 2026-09-16, after an agent gave up on `agent-browser open` and asked him to sign
           in himself). Measured on his live session: one status message, zero frames. */
        else if (m.type === "status") setAttached(m.connected !== false);
      };
      // the relay closes when the agent's browser goes; the parent polls and unmounts us. Until
      // then a dropped socket (server restart) comes back on its own.
      ws.onclose = () => { setLive(false); if (!closed) retry = setTimeout(connect, 2000); };
    };
    connect();
    const wake = () => {
      if (document.hidden || !held.current) return;
      sendRef.current?.({ type: "ack", seq: held.current });
      held.current = 0;
    };
    document.addEventListener("visibilitychange", wake);
    const ro = new ResizeObserver(() => { paint(); fitViewport(); });
    ro.observe(box.current);
    fitViewport();
    return () => { closed = true; clearTimeout(retry); clearTimeout(shapeTimer.current);
      document.removeEventListener("visibilitychange", wake); ro.disconnect(); ws?.close(); };
  }, [sid]);

  // input reaches the page only while the owner is driving - a stray click on a watched pane
  // must not click the agent's page out from under it
  const forward = (m) => m && drivingRef.current && sendRef.current?.(m);
  const takeOver = () => { setAsked(false); setDriving(true); requestAnimationFrame(() => canvas.current?.focus()); };
  // THE OWNER CAN OPEN A PAGE. The pane had no address bar, so when the agent handed the keyboard
  // over - which it is told to do for a password or a 2FA code - there was nowhere to hand it to:
  // Take over only forwards clicks, and there is nothing to click on about:blank. The task the
  // owner was watching could not be finished from the screen he was watching it on (2026-09-16).
  const [typed, setTyped] = useState("");
  const [going, setGoing] = useState(false);
  const say = (t, bad = false, ms = 3000) => { setNote({ t, bad }); setTimeout(() => setNote(null), ms); };
  const go = async () => {
    const want = typed.trim();
    if (!want || going) return;
    setGoing(true); setNote(null);
    try {
      const r = await api.post(`/api/terminals/${sid}/browser/open`, { url: want });
      setUrl(r.data.url); setTyped("");
    } catch (e) { say(e?.response?.data?.detail || "could not open that page", true, 6000); }
    setGoing(false);
  };
  const onMouse = (e) => { if (!drivingRef.current) return void (e.type === "mousedown" && setAsked(true)); e.preventDefault(); forward(mouseMessage(e.type, e.nativeEvent, fit.current)); };
  const onWheel = (e) => { if (!drivingRef.current) return; e.preventDefault(); forward(wheelMessage(e.nativeEvent, fit.current)); };
  // the page asked for a password, the agent said to type it here, and the keystroke went nowhere
  // and said nothing (the owner, 2026-09-14). Dropping it is right; dropping it in silence is not.
  const onKey = (e) => { if (!drivingRef.current) return void setAsked(true); e.preventDefault(); e.stopPropagation(); forward(keyMessage(e.type, e.nativeEvent)); };

  const snapshot = async () => {
    try {
      const r = await api.post(`/api/terminals/${sid}/browser/snapshot`, { task_id: taskId || null });
      say(`saved ${r.data.name} on the task`);
    } catch (e) { say(e?.response?.data?.detail || "could not save the snapshot", true); }
  };

  return (
    <Box sx={{ position: overlay ? "absolute" : "relative", ...(overlay ? { inset: 0, zIndex: 3 } : {}), display: "flex",
      flexDirection: "column", minHeight: 0, minWidth: 0, border: `1px solid ${driving ? CATPPUCCIN.yellow : BORDER}`,
      borderRadius: 2, overflow: "hidden", bgcolor: "#101010", transition: "border-color .15s" }}>
      {/* toolbar: what page, whether frames are flowing, who is driving */}
      <Box sx={{ display: "flex", alignItems: "center", gap: 1, px: 1, py: 0.5, bgcolor: PANEL, borderBottom: `1px solid ${BORDER}`, flexShrink: 0 }}>
        <Box title={live ? "live - frames are flowing" : "connecting…"}
          sx={{ width: 8, height: 8, borderRadius: 99, flexShrink: 0, bgcolor: live ? CATPPUCCIN.green : "#5a554d",
            boxShadow: live ? `0 0 0 3px ${CATPPUCCIN.green}33` : "none", transition: "background .3s" }} />
        <Typography title="The agent opened this page itself - this pane is its browser, watched live.
Take over to drive it yourself; close the session to close it."
          sx={{ ...mono, fontSize: 10.5, color: live ? "#c9c3b9" : FAINT, letterSpacing: 0.3, flexShrink: 0 }}>
          {live ? "LIVE" : "…"}
        </Typography>
        {/* the URL is a FIELD, not a label: click it and type somewhere else. Blank shows where
            the browser is, so it still reads as the address line when nobody is typing. */}
        <Box component="input" value={typed} disabled={going}
          onChange={(e) => setTyped(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") go(); if (e.key === "Escape") setTyped(""); e.stopPropagation(); }}
          placeholder={shortUrl(url) || "the agent's browser \u2014 type an address to open one"}
          title={url ? `${url}\n\ntype an address and press Enter to go somewhere else` : "type an address and press Enter to open a page"}
          sx={{ ...mono, fontSize: 11, color: "#c9c3b9", flex: 1, minWidth: 0, bgcolor: "transparent",
            border: "1px solid transparent", borderRadius: 1, px: 0.75, py: 0.25, outline: "none",
            "&::placeholder": { color: "#a8a196", opacity: 1 },
            "&:hover": { borderColor: BORDER }, "&:focus": { borderColor: CATPPUCCIN.yellow, bgcolor: "#1a1a1a" } }} />
        {!!typed.trim() && (
          <Box component="button" onClick={go} disabled={going} sx={{ ...btn, flexShrink: 0 }}>{going ? "opening…" : "Go"}</Box>
        )}
        {note && <Typography title={note.t} sx={{ ...mono, fontSize: 10, flexShrink: 1, minWidth: 0, maxWidth: "45%",
          overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
          color: note.bad ? CATPPUCCIN.red : CATPPUCCIN.green }}>{note.t}</Typography>}
        <Box component="button" onClick={() => (driving ? setDriving(false) : takeOver())}
          title={driving ? "give the page back to the agent" : "drive the page yourself - for a password or a code the agent must not type"}
          sx={{ ...btn, ...(driving ? { color: CATPPUCCIN.yellow, borderColor: CATPPUCCIN.yellow } : {}) }}>
          {driving ? "Hand back" : "Take over"}
        </Box>
        <Box component="button" onClick={snapshot} title="keep this frame on the task as an attachment" sx={btn}>Snapshot</Box>
        {onFold && <Box component="button" onClick={onFold} title={overlay ? "back to the terminal" : "fold the browser away"} sx={btn}>{overlay ? "✕" : "›"}</Box>}
      </Box>
      {/* the page. tabIndex so keystrokes land here while driving; the canvas swallows the wheel
          the same way the terminal does, so scrolling the page never scrolls the app */}
      <Box ref={box} sx={{ flex: 1, minHeight: 0, position: "relative", cursor: driving ? "default" : "not-allowed" }}>
        <Box component="canvas" ref={canvas} tabIndex={0} onMouseDown={onMouse} onMouseUp={onMouse} onMouseMove={onMouse}
          onWheel={onWheel} onKeyDown={onKey} onKeyUp={onKey} onContextMenu={(e) => e.preventDefault()}
          sx={{ display: "block", outline: "none", position: "absolute", inset: 0 }} />
        {/* Only before the first frame: once a page has painted, a momentary "not connected"
            is the browser moving between pages, not an empty pane. */}
        {attached === false && !live && (
          <Box sx={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column",
            alignItems: "center", justifyContent: "center", gap: 0.75, px: 3, textAlign: "center" }}>
            <Typography sx={{ ...mono, fontSize: 11.5, color: "#c9c3b9" }}>the browser is running, with no page open</Typography>
            <Typography sx={{ ...mono, fontSize: 10.5, color: FAINT, lineHeight: 1.6 }}>
              Nothing has been navigated to yet, so there is nothing to show. Type an address up
              there to open one — then take over to drive it yourself.
            </Typography>
          </Box>
        )}
        {/* THE EMPTY PAGE SAYS IT IS EMPTY. A session that asked for a browser gets one on
            about:blank, which paints as a white rectangle labelled LIVE - and nothing said whether
            that was the page or a broken pane (the 2026-09-18 pane pass, defect #1). Frames ARE
            flowing; it is a blank tab, and here is what fills it. Gone the moment a page has an
            address. */}
        {live && (!url || url === "about:blank") && (
          <Box sx={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column", pointerEvents: "none",
            alignItems: "center", justifyContent: "center", gap: 0.75, px: 3, textAlign: "center" }}>
            <Typography sx={{ ...mono, fontSize: 11.5, color: "#867f74" }}>an empty tab, live</Typography>
            <Typography sx={{ ...mono, fontSize: 10.5, color: "#a8a196", lineHeight: 1.6 }}>
              The agent opens its pages here. Or type an address above to open one yourself.
            </Typography>
          </Box>
        )}
        {driving && (
          <Typography sx={{ ...mono, position: "absolute", left: 8, bottom: 6, fontSize: 10, color: CATPPUCCIN.yellow,
            bgcolor: "#000000aa", px: 0.75, py: 0.25, borderRadius: 1, pointerEvents: "none" }}>
            you are driving — the agent's next command still runs; hand back when done
          </Typography>
        )}
        {asked && !driving && (
          <Box sx={{ position: "absolute", left: 8, right: 8, bottom: 6, display: "flex", alignItems: "center", gap: 1,
            bgcolor: "#000000cc", border: `1px solid ${CATPPUCCIN.yellow}66`, px: 1, py: 0.5, borderRadius: 1 }}>
            <Typography sx={{ ...mono, fontSize: 10, color: "#e1dcd5", flex: 1 }}>
              You are watching the agent's page — Take over to type on it.
            </Typography>
            <Box component="button" onClick={takeOver}
              sx={{ ...btn, color: CATPPUCCIN.yellow, borderColor: CATPPUCCIN.yellow }}>Take over</Box>
          </Box>
        )}
      </Box>
    </Box>
  );
}
