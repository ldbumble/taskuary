// SETUP COMPLETE (the owner, 2026-10-16: "when setup is complete confetti should come down say setup complete with big button to move
// to normal"): shown once, the first time the required steps are done - confetti falls, one big move into the day, and a quiet way to
// connect more first. A computer set to reduce motion gets the words without the confetti.
import React, { useEffect, useRef } from "react";
import { Box, Button, Typography } from "@mui/material";
import { DIM } from "./theme.jsx";

const COLORS = ["#4f6d5a", "#c08a3e", "#8a5a83", "#4a6a8a", "#b5523b", "#d8b45a"];

function Confetti() {
  const ref = useRef(null);
  useEffect(() => {
    const c = ref.current;
    if (!c || window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) return undefined;
    const ctx = c.getContext("2d"), px = window.devicePixelRatio || 1;
    const fit = () => { c.width = c.offsetWidth * px; c.height = c.offsetHeight * px; };
    fit();
    const W = () => c.width, H = () => c.height, r = Math.random;
    const bits = Array.from({ length: 160 }, () => ({ x: r() * W(), y: -r() * H(), w: (6 + r() * 6) * px, h: (3 + r() * 4) * px,
      vy: (1.5 + r() * 2.5) * px, vx: (r() - 0.5) * 1.2 * px, a: r() * 6, va: (r() - 0.5) * 0.2, col: COLORS[(r() * COLORS.length) | 0] }));
    let id, until = performance.now() + 4500;
    const tick = (t) => {
      ctx.clearRect(0, 0, W(), H());
      let live = 0;
      for (const b of bits) {
        b.x += b.vx + Math.sin(b.a) * 0.6; b.y += b.vy; b.a += b.va;
        if (b.y > H() && t < until) { b.y = -10; b.x = r() * W(); }   // it keeps falling for a few seconds, then lets the last ones land
        if (b.y <= H()) live += 1;
        ctx.save(); ctx.translate(b.x, b.y); ctx.rotate(b.a); ctx.fillStyle = b.col; ctx.fillRect(-b.w / 2, -b.h / 2, b.w, b.h); ctx.restore();
      }
      if (live) id = requestAnimationFrame(tick);
    };
    id = requestAnimationFrame(tick);
    window.addEventListener("resize", fit);
    return () => { cancelAnimationFrame(id); window.removeEventListener("resize", fit); };
  }, []);
  return <canvas ref={ref} data-tq-confetti="" aria-hidden="true"
    style={{ position: "absolute", inset: 0, width: "100%", height: "100%", pointerEvents: "none", zIndex: 0 }} />;
}

// `aiError`: the AI failing on the real mail. Then it is not complete: "reading and sorting your mail" with a big Go to my day stood over
// a line saying the AI was not sorting anything (the non-coder audit, 2026-10-17) - the problem, and Change AI as the one big button
export default function SetupDone({ onDay, onMore, aiError = "", onChangeAi }) {
  if (aiError) return (
    <Box data-tq-setup-done="ai-error" sx={{ minHeight: "56vh", display: "flex", flexDirection: "column", alignItems: "center",
      justifyContent: "center", gap: 2, textAlign: "center", px: 2 }}>
      <Typography component="h2" sx={{ fontSize: 30, fontWeight: 700, letterSpacing: -0.5 }}>One thing left: your AI</Typography>
      <Typography sx={{ color: DIM, fontSize: 15.5, maxWidth: 560 }}>{aiError} Pick another one - it is checked on a test email first.</Typography>
      <Button variant="contained" disableElevation size="large" onClick={onChangeAi}
        sx={{ fontSize: 18, px: 5, py: 1.5, borderRadius: 2.5, mt: 1 }}>Change AI</Button>
      <Button size="small" onClick={onDay} sx={{ color: DIM }}>Go to my day anyway</Button>
    </Box>
  );
  return (
    <Box data-tq-setup-done="" sx={{ position: "relative", minHeight: "56vh", display: "flex", flexDirection: "column", alignItems: "center",
      justifyContent: "center", gap: 2, textAlign: "center", px: 2 }}>
      <Confetti />
      <Typography component="h2" sx={{ fontSize: 34, fontWeight: 700, letterSpacing: -0.5, position: "relative", zIndex: 1 }}>Setup complete</Typography>
      <Typography sx={{ color: DIM, fontSize: 15.5, maxWidth: 520, position: "relative", zIndex: 1 }}>
        Taskuary is reading and sorting what came in. Your day is ready - everything waiting, most important first.</Typography>
      <Button variant="contained" disableElevation size="large" onClick={onDay}
        sx={{ fontSize: 18, px: 5, py: 1.5, borderRadius: 2.5, mt: 1, position: "relative", zIndex: 1 }}>Go to my day</Button>
      <Button size="small" onClick={onMore} sx={{ color: DIM, position: "relative", zIndex: 1 }}>Connect more apps first</Button>
    </Box>
  );
}
