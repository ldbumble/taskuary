// The agent's browser, live, beside its terminal. Frames come from agent-browser's screencast
// through the server relay (/api/terminals/:sid/browser/ws) and are drawn on a canvas; the
// owner can take the keyboard and mouse when a page asks for something an agent must never
// type - a password, a 2FA code - and hand it back. Snapshot files the frame on the task.
import React, { useEffect, useRef, useState } from "react";
import { Box, Typography } from "@mui/material";
import api from "./api.js";
import { BORDER, CATPPUCCIN, FAINT, PANEL, mono } from "./theme.jsx";
import { fitFrame, keyMessage, mouseMessage, parseMessage, shortUrl, wheelMessage } from "./browserSplit.js";

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
  const [note, setNote] = useState("");
  const drivingRef = useRef(false);
  drivingRef.current = driving;

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
    let ws, closed = false, retry = null, staleTimer = null;
    const connect = () => {
      ws = new WebSocket(wsUrl(sid));
      const send = (m) => ws.readyState === 1 && ws.send(JSON.stringify(m));
      sendRef.current = send;
      ws.onmessage = (e) => {
        const m = parseMessage(e.data);
        if (!m) return;
        if (m.type === "frame") {
          const im = new Image();
          im.onload = () => {
            img.current = im; paint(); setLive(true);
            clearTimeout(staleTimer); staleTimer = setTimeout(() => setLive(false), 4000);
            send({ type: "ack", seq: m.seq });       // ack AFTER drawing: the next frame is the page now, not history
          };
          im.src = m.src;
        } else if (m.type === "url" && m.url) setUrl(m.url);
      };
      // the relay closes when the agent's browser goes; the parent polls and unmounts us. Until
      // then a dropped socket (server restart) comes back on its own.
      ws.onclose = () => { setLive(false); if (!closed) retry = setTimeout(connect, 2000); };
    };
    connect();
    const ro = new ResizeObserver(paint);
    ro.observe(box.current);
    return () => { closed = true; clearTimeout(retry); clearTimeout(staleTimer); ro.disconnect(); ws?.close(); };
  }, [sid]);

  // input reaches the page only while the owner is driving - a stray click on a watched pane
  // must not click the agent's page out from under it
  const forward = (m) => m && drivingRef.current && sendRef.current?.(m);
  const onMouse = (e) => { if (!drivingRef.current) return; e.preventDefault(); forward(mouseMessage(e.type, e.nativeEvent, fit.current)); };
  const onWheel = (e) => { if (!drivingRef.current) return; e.preventDefault(); forward(wheelMessage(e.nativeEvent, fit.current)); };
  const onKey = (e) => { if (!drivingRef.current) return; e.preventDefault(); e.stopPropagation(); forward(keyMessage(e.type, e.nativeEvent)); };

  const snapshot = async () => {
    try {
      const r = await api.post(`/api/terminals/${sid}/browser/snapshot`, { task_id: taskId || null });
      setNote(`saved ${r.data.name} on the task`);
    } catch (e) { setNote(e?.response?.data?.detail || "could not save the snapshot"); }
    setTimeout(() => setNote(""), 3000);
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
        <Typography sx={{ ...mono, fontSize: 10.5, color: live ? "#c9c3b9" : FAINT, letterSpacing: 0.3, flexShrink: 0 }}>
          {live ? "LIVE" : "…"}
        </Typography>
        <Typography title={url} sx={{ ...mono, fontSize: 11, color: "#a8a196", flex: 1, minWidth: 0, overflow: "hidden",
          textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {shortUrl(url) || "the agent's browser"}
        </Typography>
        {note && <Typography sx={{ ...mono, fontSize: 10, color: CATPPUCCIN.green, flexShrink: 0 }}>{note}</Typography>}
        <Box component="button" onClick={() => { setDriving((d) => !d); requestAnimationFrame(() => canvas.current?.focus()); }}
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
        {driving && (
          <Typography sx={{ ...mono, position: "absolute", left: 8, bottom: 6, fontSize: 10, color: CATPPUCCIN.yellow,
            bgcolor: "#000000aa", px: 0.75, py: 0.25, borderRadius: 1, pointerEvents: "none" }}>
            you are driving — the agent's next command still runs; hand back when done
          </Typography>
        )}
      </Box>
    </Box>
  );
}
