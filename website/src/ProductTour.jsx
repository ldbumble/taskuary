// The How Taskuary works overlay: a spotlight on the real chrome, a card in Beacon type,
// and nothing else. The steps live in productTour.js so the copy can be tested without drawing.
import React, { useEffect, useLayoutEffect, useRef, useState } from "react";
import { Box, Button, IconButton, Typography } from "@mui/material";
import CloseIcon from "@mui/icons-material/Close";
import { TaskuaryMark } from "./ui.jsx";
import { ACCENT, BORDER, DIM, FAINT, GRADIENT, INK, PANEL } from "./theme.jsx";
import { TOUR_STEPS, dimRects, holeFor, placeCard, visibleRect } from "./productTour.js";

const CARD_W = 400;

export default function ProductTour({ open, tab, onNavigate, onClose }) {
  const [i, setI] = useState(0);
  const [hole, setHole] = useState(null);
  const [pos, setPos] = useState({ top: 80, left: 80 });
  const cardRef = useRef(null);
  const nextRef = useRef(null);
  const step = TOUR_STEPS[i] || TOUR_STEPS[0];
  const last = i === TOUR_STEPS.length - 1;

  useEffect(() => { if (open) setI(0); }, [open]);
  useEffect(() => {
    if (!open) return undefined;
    if (step.tab && step.tab !== tab) onNavigate?.(step.tab);
  }, [open, step.tab, tab, onNavigate]);

  useLayoutEffect(() => {
    if (!open) return undefined;
    const measure = () => {
      const el = step.target ? document.querySelector(`[data-tour="${step.target}"]`) : null;
      let target = visibleRect(el);
      if (step.target && !target) target = visibleRect(document.querySelector('[data-tour="pages"]'));
      const nextHole = holeFor(target);
      setHole(nextHole);
      const card = cardRef.current?.getBoundingClientRect();
      setPos(placeCard({
        target, cardW: card?.width || CARD_W, cardH: card?.height || 220,
        vw: window.innerWidth, vh: window.innerHeight,
      }));
    };
    const t = setTimeout(measure, 90);
    window.addEventListener("resize", measure);
    return () => { clearTimeout(t); window.removeEventListener("resize", measure); };
  }, [open, i, tab, step.target]);

  useEffect(() => {
    if (!open) return undefined;
    nextRef.current?.focus();
    const onKey = (e) => {
      if (e.key === "Escape") { e.preventDefault(); onClose?.("skipped"); }
      if (e.key === "ArrowRight" || (e.key === "Enter" && !e.shiftKey)) {
        e.preventDefault(); last ? onClose?.("done") : setI((n) => n + 1);
      }
      if (e.key === "ArrowLeft") { e.preventDefault(); setI((n) => Math.max(0, n - 1)); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, last, onClose]);

  if (!open) return null;
  const vw = typeof window === "undefined" ? 1200 : window.innerWidth;
  const vh = typeof window === "undefined" ? 800 : window.innerHeight;
  const dims = dimRects(hole, vw, vh);

  return (
    <Box role="dialog" aria-modal="true" aria-labelledby="tq-tour-title" aria-describedby="tq-tour-body"
      sx={{ position: "fixed", inset: 0, zIndex: 1600 }}>
      {dims.map((r, n) => (
        <Box key={n} aria-hidden onClick={() => { /* the card is the only way through */ }}
          sx={{ position: "fixed", top: r.top, left: r.left, width: r.width, height: r.height,
            bgcolor: "rgba(38, 37, 33, 0.46)", transition: "top .22s ease, left .22s ease, width .22s ease, height .22s ease" }} />
      ))}
      {hole && (
        <Box aria-hidden sx={{ position: "fixed", top: hole.top, left: hole.left, width: hole.width, height: hole.height,
          borderRadius: `${hole.radius}px`, pointerEvents: "none",
          boxShadow: "0 0 0 2px #fffdfb, 0 10px 28px rgba(38, 37, 33, .22)",
          transition: "top .22s ease, left .22s ease, width .22s ease, height .22s ease" }} />
      )}
      <Box ref={cardRef} sx={{ position: "fixed", top: pos.top, left: pos.left, width: { xs: "min(400px, calc(100vw - 32px))", sm: CARD_W },
        bgcolor: PANEL, border: `1px solid ${BORDER}`, borderRadius: 2.5, overflow: "hidden",
        boxShadow: "0 22px 70px rgba(42, 39, 33, .22), 0 4px 18px rgba(42, 39, 33, .10)",
        transition: "top .22s ease, left .22s ease" }}>
        <Box sx={{ display: "flex", alignItems: "center", gap: 1, px: 1.75, py: 1.15, color: "white", background: GRADIENT }}>
          <TaskuaryMark size={26} sx={{ boxShadow: "0 1px 5px #0002" }} />
          <Box sx={{ minWidth: 0, flex: 1 }}>
            <Typography sx={{ fontSize: 10.5, letterSpacing: ".12em", textTransform: "uppercase", opacity: 0.82, fontWeight: 700 }}>
              {step.kicker}
            </Typography>
            <Typography id="tq-tour-title" sx={{ fontSize: 15.5, fontWeight: 800, lineHeight: 1.25, letterSpacing: "-.2px" }}>
              {step.title}
            </Typography>
          </Box>
          <IconButton size="small" aria-label="Skip walkthrough" onClick={() => onClose?.("skipped")} sx={{ color: "white" }}>
            <CloseIcon sx={{ fontSize: 18 }} />
          </IconButton>
        </Box>
        <Box sx={{ px: 2.1, pt: 1.6, pb: 1.35 }}>
          <Typography id="tq-tour-body" sx={{ fontSize: 13.5, color: INK, lineHeight: 1.6 }}>{step.body}</Typography>
          <Box sx={{ display: "flex", alignItems: "center", gap: 0.85, mt: 1.7 }}>
            {TOUR_STEPS.map((s, n) => (
              <Box key={s.id} component="button" type="button" aria-label={`Step ${n + 1}: ${s.title}`}
                onClick={() => setI(n)}
                sx={{ appearance: "none", width: n === i ? 16 : 7, height: 7, p: 0, border: 0, borderRadius: 99,
                  bgcolor: n === i ? ACCENT : n < i ? "#7d9a7c" : "#d8cfbe", cursor: "pointer",
                  transition: "width .16s ease, background .16s ease" }} />
            ))}
            <Typography sx={{ ml: 0.4, color: FAINT, fontSize: 10.5, fontWeight: 600 }}>{i + 1} of {TOUR_STEPS.length}</Typography>
            <Box sx={{ flex: 1 }} />
            {i > 0 && (
              <Button size="small" onClick={() => setI((n) => n - 1)}
                sx={{ minWidth: 0, px: 1.1, color: DIM, textTransform: "none", fontWeight: 600 }}>Back</Button>
            )}
            <Button ref={nextRef} size="small" variant="contained" disableElevation
              onClick={() => last ? onClose?.("done") : setI((n) => n + 1)}
              sx={{ px: 1.6, textTransform: "none", fontWeight: 700, background: GRADIENT }}>
              {last ? "Get started" : "Next"}
            </Button>
          </Box>
        </Box>
      </Box>
    </Box>
  );
}
