// YOUR SIGNATURE (Settings -> Replies, handsign.py): the one an agent signs forms with - a permission slip, a consent form (the owner,
// 2026-11-04: "A person got a permission slip to sign for their kid. The agent should sign it and say 'do you want me to send it out'").
// Drawn here with a mouse, a pen or a finger, or uploaded as a picture, once. Kept on this computer and read back by the owner's token
// alone; an agent never sees it - Taskuary places it, and every signed form waits for the owner's Send.
// Both roads end as one PNG: the strokes (or the picture, its paper made see-through) cut to the ink and no bigger than 600x240.
import React, { useEffect, useRef, useState } from "react";
import { Box, Button, Typography } from "@mui/material";
import api from "./api";
import { BORDER, DIM, FAINT, INK } from "./theme.jsx";

const W = 480, H = 160, MAX_W = 600, MAX_H = 240, PAPER = 225;   // the pad's size on the page; the saved picture's most; paper is brighter than this

// the ink alone: cut to what is not see-through, a little room round it, and shrunk to fit MAX_W x MAX_H
export function inked(src) {
  const { width: w, height: h } = src, px = src.getContext("2d").getImageData(0, 0, w, h).data;
  let x0 = w, y0 = h, x1 = -1, y1 = -1;
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) if (px[(y * w + x) * 4 + 3] > 8) {
    if (x < x0) x0 = x; if (x > x1) x1 = x; if (y < y0) y0 = y; if (y > y1) y1 = y;
  }
  if (x1 < 0) return null;
  const pad = 6; x0 = Math.max(0, x0 - pad); y0 = Math.max(0, y0 - pad); x1 = Math.min(w - 1, x1 + pad); y1 = Math.min(h - 1, y1 + pad);
  const cw = x1 - x0 + 1, ch = y1 - y0 + 1, s = Math.min(1, MAX_W / cw, MAX_H / ch);
  const out = document.createElement("canvas");
  out.width = Math.max(1, Math.round(cw * s)); out.height = Math.max(1, Math.round(ch * s));
  out.getContext("2d").drawImage(src, x0, y0, cw, ch, 0, 0, out.width, out.height);
  return out.toDataURL("image/png");
}

// an uploaded picture: drawn at most 1200 wide, its near-white paper made see-through so the form's line shows under the ink
function fromPicture(file) {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file), img = new Image();
    img.onload = () => {
      const s = Math.min(1, 1200 / img.naturalWidth, 600 / img.naturalHeight), c = document.createElement("canvas");
      c.width = Math.max(1, Math.round(img.naturalWidth * s)); c.height = Math.max(1, Math.round(img.naturalHeight * s));
      const g = c.getContext("2d"); g.drawImage(img, 0, 0, c.width, c.height);
      const d = g.getImageData(0, 0, c.width, c.height), p = d.data;
      for (let i = 0; i < p.length; i += 4) if (p[i] > PAPER && p[i + 1] > PAPER && p[i + 2] > PAPER) p[i + 3] = 0;
      g.putImageData(d, 0, 0); URL.revokeObjectURL(url); resolve(inked(c));
    };
    img.onerror = () => { URL.revokeObjectURL(url); reject(new Error("That file is not a picture this browser can read - try a PNG or JPG.")); };
    img.src = url;
  });
}

// Signatures keep paper under their fixed export ink, including transparent saved PNGs.
function Pad({ onSave, onCancel, busy }) {
  const ref = useRef(null), last = useRef(null), [ink, setInk] = useState(false);
  useEffect(() => {
    const c = ref.current, r = window.devicePixelRatio || 1;
    c.width = W * r; c.height = H * r;
    const g = c.getContext("2d"); g.scale(r, r);
    g.lineWidth = 2.4; g.lineCap = g.lineJoin = "round"; g.strokeStyle = "#1d2a52";
  }, []);
  const at = (e) => { const b = ref.current.getBoundingClientRect(); return [(e.clientX - b.left) * W / b.width, (e.clientY - b.top) * H / b.height]; };
  const down = (e) => { e.preventDefault(); ref.current.setPointerCapture?.(e.pointerId); last.current = at(e); move(e); };
  const move = (e) => {
    if (!last.current) return;
    const [x, y] = at(e), [px, py] = last.current, g = ref.current.getContext("2d");
    g.beginPath(); g.moveTo(px, py); g.lineTo(x + (x === px && y === py ? 0.1 : 0), y); g.stroke();
    last.current = [x, y]; setInk(true);
  };
  const up = () => { last.current = null; };
  const again = () => { const c = ref.current; c.getContext("2d").clearRect(0, 0, c.width, c.height); setInk(false); };
  return (
    <Box data-tq-hand-signature-pad="">
      <Box sx={{ position: "relative", width: "100%", maxWidth: W, aspectRatio: `${W} / ${H}`, border: `1px solid ${BORDER}`, borderRadius: 1.5, bgcolor: "#fff" }}>
        <Box sx={{ position: "absolute", left: "6%", right: "6%", bottom: "24%", borderBottom: `1px dashed ${BORDER}`, pointerEvents: "none" }} />
        <canvas ref={ref} aria-label="Sign here" onPointerDown={down} onPointerMove={move} onPointerUp={up} onPointerLeave={up} onPointerCancel={up}
          style={{ position: "absolute", inset: 0, width: "100%", height: "100%", touchAction: "none", cursor: "crosshair" }} />
      </Box>
      <Box sx={{ display: "flex", gap: 1, mt: 1 }}>
        <Button size="small" variant="contained" disableElevation disabled={!ink || busy} onClick={() => onSave(inked(ref.current))}>
          {busy ? "Saving…" : "Save"}</Button>
        <Button size="small" disabled={!ink || busy} onClick={again} sx={{ color: DIM }}>Start over</Button>
        <Button size="small" disabled={busy} onClick={onCancel} sx={{ color: DIM }}>Cancel</Button>
      </Box>
    </Box>
  );
}

export default function HandSignature() {
  const [info, setInfo] = useState(null), [url, setUrl] = useState(""), [drawing, setDrawing] = useState(false);
  const [busy, setBusy] = useState(false), [err, setErr] = useState(""), file = useRef(null);
  const show = async (got) => {
    setInfo(got);
    if (!got?.saved) { setUrl(""); return; }
    const { data } = await api.get("/api/hand-signature/image", { responseType: "blob" });
    setUrl(URL.createObjectURL(data));
  };
  useEffect(() => { api.get("/api/hand-signature").then(({ data }) => show(data)).catch(() => setErr("Your signature could not be read - Taskuary did not answer.")); }, []);
  useEffect(() => () => url && URL.revokeObjectURL(url), [url]);
  const save = async (data) => {
    if (!data) return;
    setBusy(true); setErr("");
    try { await show((await api.put("/api/hand-signature", { data })).data); setDrawing(false); }
    catch (e) { setErr(e?.response?.data?.detail || e?.message || "Your signature was not saved - try again."); }
    finally { setBusy(false); }
  };
  const upload = async (e) => {
    const f = e.target.files?.[0]; e.target.value = "";
    if (!f) return;
    try { const data = await fromPicture(f); data ? save(data) : setErr("That picture has no ink on it - nothing darker than the paper."); }
    catch (x) { setErr(x.message); }
  };
  const clear = async () => {
    setBusy(true); setErr("");
    try { await show((await api.delete("/api/hand-signature")).data); }
    catch (e) { setErr(e?.response?.data?.detail || "Your signature was not cleared - try again."); }
    finally { setBusy(false); }
  };
  return (
    <Box data-tq-hand-signature="" sx={{ py: 2.5, borderBottom: `1px solid ${BORDER}` }}>
      <Typography sx={{ color: INK, fontWeight: 600, fontSize: 13.5 }}>Your signature</Typography>
      <Typography variant="body2" sx={{ color: DIM, mt: 0.25, mb: 1.25 }}>
        Agents sign forms with it - a permission slip, a consent form - and every signed form waits for your Send. Kept on this computer; only you see it.
      </Typography>
      {drawing ? <Pad busy={busy} onSave={save} onCancel={() => { setDrawing(false); setErr(""); }} /> : (
        <Box sx={{ display: "flex", alignItems: "center", gap: 1.5, flexWrap: "wrap" }}>
          {url ? <Box sx={{ border: `1px solid ${BORDER}`, borderRadius: 1.5, bgcolor: "#fff", px: 1.5, py: 1, lineHeight: 0 }}>
            <img data-tq-hand-signature-preview="" src={url} alt="Your saved signature" style={{ maxHeight: 64, maxWidth: 260 }} />
          </Box> : info && <Typography sx={{ color: FAINT, fontSize: 12.5 }}>No signature saved - an agent asks you for one before it signs anything.</Typography>}
          <Box sx={{ display: "flex", gap: 1 }}>
            <Button size="small" variant="outlined" disabled={busy || !info} onClick={() => { setDrawing(true); setErr(""); }}
              sx={{ color: INK, borderColor: BORDER, textTransform: "none" }}>{url ? "Draw a new one" : "Draw it"}</Button>
            <Button size="small" variant="outlined" disabled={busy || !info} onClick={() => file.current?.click()}
              sx={{ color: INK, borderColor: BORDER, textTransform: "none" }}>Upload a picture</Button>
            {url && <Button size="small" disabled={busy} onClick={clear} sx={{ color: DIM, textTransform: "none" }}>Clear</Button>}
          </Box>
          <input ref={file} type="file" accept="image/png,image/jpeg" hidden onChange={upload} data-tq-hand-signature-file="" />
        </Box>
      )}
      {err && <Typography role="alert" sx={{ color: "var(--tq-danger, #a33b3b)", fontSize: 12.5, mt: 1 }}>{err}</Typography>}
    </Box>
  );
}
