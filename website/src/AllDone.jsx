// THE RAIL WHEN THE WALK REACHES CLEAR (the owner, 2026-11-06): a ~1.5 s confetti burst on a canvas over the rail's empty state, then the "All
// done" line arrives. `burst`: read once, as it mounts - the rail went from rows to none in front of the owner (allDone.burstsNow). Reduced
// motion: no confetti, the line at once. No dependency: a canvas and requestAnimationFrame.
import React, { useEffect, useRef, useState } from "react";
import { BURST_MS, LINE_AFTER_MS, pieceAt, piecesOf } from "./allDone.js";

const still = () => { try { return !!window.matchMedia?.("(prefers-reduced-motion: reduce)").matches; } catch { return false; } };

export default function AllDone({ burst = false, children }) {
  const [play] = useState(() => burst && !still()), [line, setLine] = useState(!play), canvas = useRef(null);
  useEffect(() => {
    if (!play) return undefined;
    const c = canvas.current, ctx = c?.getContext?.("2d");
    const lineAt = setTimeout(() => setLine(true), LINE_AFTER_MS);
    if (!ctx) return () => clearTimeout(lineAt);
    const dpr = window.devicePixelRatio || 1, w = c.clientWidth, h = c.clientHeight, ps = piecesOf();
    c.width = w * dpr; c.height = h * dpr; ctx.scale(dpr, dpr);
    let raf = 0; const t0 = performance.now();
    const draw = (now) => {
      const t = now - t0;
      ctx.clearRect(0, 0, w, h);
      if (t >= BURST_MS) return;
      for (const p of ps) {
        const { x, y, rot, fade } = pieceAt(p, t);
        ctx.save(); ctx.globalAlpha = fade; ctx.translate(w / 2 + x, 64 + y); ctx.rotate(rot); ctx.fillStyle = p.c; ctx.fillRect(-p.w / 2, -p.h / 2, p.w, p.h); ctx.restore();
      }
      raf = requestAnimationFrame(draw);
    };
    raf = requestAnimationFrame(draw);
    return () => { clearTimeout(lineAt); cancelAnimationFrame(raf); };
  }, [play]);
  return (
    <div className="tq-pile-empty tq-all-done" data-tq-all-done={play ? "burst" : ""}>
      {play && <canvas ref={canvas} className="tq-all-done-confetti" aria-hidden="true" />}
      <div className={line ? "tq-all-done-line in" : "tq-all-done-line"}>{children}</div>
    </div>
  );
}
