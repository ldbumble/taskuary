// ONE VIEWER FOR EVERY PICTURE A CARD DRAWS (the owner, 2026-11-25: "you should be able to zoom in on an image that pops up on the white cards
// if you need"): a post's picture, a picture handed over, a run of them, a chart, an email's - a press on it opens it here, fitted to the window.
// The wheel, a pinch, + and - zoom it about the pointer; a drag moves it once zoomed; a press on it zooms in there, or back; the arrows step through the
// card's others (`files`); Esc, the cross or a press past it closes it. FileDialog opens a picture here, so every road to one is this one
import React, { useEffect, useRef, useState } from "react";
import { Box, Button, Dialog, IconButton, Typography } from "@mui/material";
import AddIcon from "@mui/icons-material/Add";
import ChevronLeftIcon from "@mui/icons-material/ChevronLeft";
import ChevronRightIcon from "@mui/icons-material/ChevronRight";
import CloseIcon from "@mui/icons-material/Close";
import RemoveIcon from "@mui/icons-material/Remove";
import { attUrl, useSave } from "./fileSave.js";
import { useOverlay } from "./overlays.js";
import { FIT, MAX, STEP, keyOf, pan, pictureList, stepAt, zoomAt } from "./pictureZoom.js";

const ARROW = { position: "absolute", top: "50%", transform: "translateY(-50%)", zIndex: 1, bgcolor: "var(--tq-panel, #fff)", color: "var(--tq-text, #3f423c)",
  border: "1px solid var(--tq-border, #e3ddd2)", boxShadow: "var(--tq-frame-shadow)", "&:hover": { bgcolor: "var(--tq-inset, #f1ede5)" } };

export function PictureDialog({ file, files = null, onClose }) {
  const list = pictureList(file, files), [at, setAt] = useState({ of: "", i: 0 }), [v, setV] = useState(FIT), [, save] = useSave();
  const i = at.of === keyOf(file) ? at.i : Math.max(0, list.findIndex((f) => keyOf(f) === keyOf(file))), f = list[i];
  const stage = useRef(null), img = useRef(null), pts = useRef(new Map()), moved = useRef(false), vr = useRef(v); vr.current = v;
  useOverlay(!!file, onClose, { typeThrough: true, own: "+=-0" });
  const fit = () => { const s = stage.current, p = img.current; return s && p ? { w: p.offsetWidth, h: p.offsetHeight, W: s.clientWidth, H: s.clientHeight } : undefined; };
  // ...a point from the window's centre, where the zoom holds still
  const from = (cx, cy) => { const r = stage.current?.getBoundingClientRect(); return r ? { x: cx - r.left - r.width / 2, y: cy - r.top - r.height / 2 } : { x: 0, y: 0 }; };
  const zoom = (k, a) => setV((o) => zoomAt(o, k, a, fit()));
  const go = (d) => { if (list.length < 2) return; setAt({ of: keyOf(file), i: stepAt(list.length, i, d) }); setV(FIT); };
  useEffect(() => { setV(FIT); }, [keyOf(file)]);
  useEffect(() => {
    if (!file) return undefined;
    const key = (e) => {
      if (e.target?.closest?.("input, textarea, [contenteditable=true]")) return;
      const k = e.key === "+" || e.key === "=" ? STEP : e.key === "-" ? 1 / STEP : 0;
      if (k) { e.preventDefault(); zoom(k); } else if (e.key === "0") { e.preventDefault(); setV(FIT); }
      else if (e.key === "ArrowRight" || e.key === "ArrowLeft") { e.preventDefault(); go(e.key === "ArrowRight" ? 1 : -1); }
    };
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  });
  // ...the wheel, and a trackpad's pinch (a wheel with Ctrl), zoom the picture, never the page: so not passive, as React's own wheel is
  const wheelOn = (el) => {
    if (!el || el.__tqWheel) return;
    el.__tqWheel = true;
    el.addEventListener("wheel", (e) => { e.preventDefault(); zoom(Math.exp(-e.deltaY * (e.ctrlKey ? 0.01 : 0.0015)), from(e.clientX, e.clientY)); }, { passive: false });
  };
  const down = (e) => { if (e.target.closest?.("button")) return; pts.current.set(e.pointerId, { x: e.clientX, y: e.clientY }); moved.current = false; };
  const move = (e) => {
    const m = pts.current, was = m.get(e.pointerId);
    if (!was) return;
    const now = { x: e.clientX, y: e.clientY };
    if (Math.abs(now.x - was.x) + Math.abs(now.y - was.y) > 2) moved.current = true;
    if (m.size >= 2) {
      const [a, b] = [...m.values()], other = a === was ? b : a, d0 = Math.hypot(was.x - other.x, was.y - other.y), d1 = Math.hypot(now.x - other.x, now.y - other.y);
      if (d0 > 0) zoom(d1 / d0, from((now.x + other.x) / 2, (now.y + other.y) / 2));
    } else if (vr.current.s > 1) setV((o) => pan({ ...o, x: o.x + now.x - was.x, y: o.y + now.y - was.y }, fit()));
    m.set(e.pointerId, now);
  };
  const up = (e) => pts.current.delete(e.pointerId);
  if (!file || !f) return null;
  const big = v.s > 1, grabbing = big && pts.current.size > 0;
  return (
    <Dialog open onClose={onClose} maxWidth={false} data-tq-picture-viewer={keyOf(f)} data-tq-file-dialog={keyOf(f)}
      PaperProps={{ sx: { m: { xs: 1, sm: 2 }, width: "min(1400px, calc(100vw - 16px))", height: "min(1000px, calc(100dvh - 16px))", maxWidth: "none", maxHeight: "none",
        display: "flex", flexDirection: "column", overflow: "hidden" } }}>
      <Box sx={{ display: "flex", alignItems: "center", gap: 0.5, px: 1.5, py: 0.75, borderBottom: "1px solid var(--tq-border, #e3ddd2)", minWidth: 0 }}>
        <Typography component="b" sx={{ flex: 1, minWidth: 0, fontSize: 14, fontWeight: 700, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{f.name}</Typography>
        {list.length > 1 && <Typography data-tq-picture-at="" sx={{ fontSize: 12, color: "var(--tq-muted, #858078)", flexShrink: 0, px: 0.5 }}>{`${i + 1} of ${list.length}`}</Typography>}
        <IconButton size="small" aria-label="Zoom out" data-tq-zoom-out="" disabled={!big} onClick={() => zoom(1 / STEP)}><RemoveIcon fontSize="small" /></IconButton>
        <Typography data-tq-zoom-at="" sx={{ fontSize: 12, color: "var(--tq-muted, #858078)", width: 40, textAlign: "center", flexShrink: 0 }}>{`${Math.round(v.s * 100)}%`}</Typography>
        <IconButton size="small" aria-label="Zoom in" data-tq-zoom-in="" disabled={v.s >= MAX} onClick={() => zoom(STEP)}><AddIcon fontSize="small" /></IconButton>
        {!f.missing && <Button size="small" onClick={() => save(f)} data-tq-download="" sx={{ flexShrink: 0 }}>Download</Button>}
        <IconButton size="small" aria-label="Close" onClick={onClose}><CloseIcon fontSize="small" /></IconButton>
      </Box>
      {/* ...a press on the window past the picture closes it, as one past the dialog does - a drag that ends there does not */}
      <Box ref={(el) => { stage.current = el; wheelOn(el); }} data-tq-picture-stage="" onPointerDown={down} onPointerMove={move} onPointerUp={up} onPointerCancel={up} onPointerLeave={up}
        onClick={(e) => { if (!moved.current && !img.current?.contains(e.target) && !e.target.closest?.("button")) onClose(); }}
        sx={{ position: "relative", flex: 1, minHeight: 0, overflow: "hidden", display: "flex", alignItems: "center", justifyContent: "center", p: 1,
          bgcolor: "var(--tq-inset, #f1ede5)", touchAction: "none", userSelect: "none", cursor: grabbing ? "grabbing" : "default" }}>
        <Box component="img" ref={img} key={keyOf(f)} src={attUrl(f)} alt={f.alt || f.name || ""} draggable={false} data-tq-picture-big={keyOf(f)}
          onClick={(e) => { if (!moved.current) big ? setV(FIT) : zoom(2.5, from(e.clientX, e.clientY)); }}
          sx={{ display: "block", maxWidth: "100%", maxHeight: "100%", objectFit: "contain", transform: `translate(${v.x}px, ${v.y}px) scale(${v.s})`, transformOrigin: "center",
            transition: grabbing ? "none" : "transform 120ms ease-out", cursor: grabbing ? "grabbing" : big ? "grab" : "zoom-in", "@media (prefers-reduced-motion: reduce)": { transition: "none" } }} />
        {list.length > 1 && <>
          <IconButton aria-label="Previous picture" data-tq-picture-prev="" onClick={() => go(-1)} sx={{ ...ARROW, left: 8 }}><ChevronLeftIcon /></IconButton>
          <IconButton aria-label="Next picture" data-tq-picture-next="" onClick={() => go(1)} sx={{ ...ARROW, right: 8 }}><ChevronRightIcon /></IconButton></>}
      </Box>
    </Dialog>
  );
}
