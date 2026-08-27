// LEARNED.md as a picture (discussion #27). Left to right: what SOUL.md says (it outranks),
// the learned lines - live, proposed, still hypotheses - and the verdicts that fed them, with a
// ribbon per piece of evidence. Click a line and its ledger opens underneath: the score over
// time, a dot per verdict, red where one contradicted it, the bar at s:4 where a line goes live,
// and the exact event that demoted or killed it. Nothing here is a new source of truth: the
// lines are the doc's own [s:N | ev | seen] tags, the ribbons its ev ids, the history the
// learned_history rows the learn pass writes.
import React, { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { Box, Button, Chip, Typography } from "@mui/material";
import api from "./api";
import { PANEL, PANEL2, BORDER, DIM, FAINT, INK, ROLES, mono } from "./theme.jsx";

const STATUS = {
  live:       { label: "LIVE · rides into every prompt", color: ROLES.handled.solid, tint: ROLES.handled.tint, bd: ROLES.handled.bd },
  proposed:   { label: "PROPOSED · your call — would hide mail", color: ROLES.info.solid, tint: ROLES.info.tint, bd: ROLES.info.bd },
  hypothesis: { label: "HYPOTHESES · still earning it", color: ROLES.muted.solid, tint: PANEL, bd: BORDER },
};
const RED = ROLES.you.solid, RED_INK = ROLES.you.ink, RED_TINT = ROLES.you.tint, RED_BD = ROLES.you.bd;
const day = (d) => (d ? String(d).slice(5, 10).replace("-", "/") : "");

const Score = ({ s, color }) => (
  <Box component="span" sx={{ ...mono, fontWeight: 700, fontSize: 10, borderRadius: 1, px: 0.6, color: "#fff", bgcolor: color }}>s:{s}</Box>
);

// The ledger: one line's life on one clock.
const Ledger = ({ line, promoteAt }) => {
  const steps = line.steps || [];
  const dated = steps.filter((s) => s.date);
  if (!dated.length) return <Typography variant="caption" sx={{ color: FAINT }}>No dated evidence yet — this line has a score but nothing to draw it from.</Typography>;
  const W = 760, H = 120, L = 36, R = 16, T = 14, B = 26;
  const t0 = new Date(dated[0].date.replace(" ", "T")).getTime(), t1 = Math.max(Date.now(), new Date(dated[dated.length - 1].date.replace(" ", "T")).getTime());
  const maxS = Math.max(promoteAt + 1, ...steps.map((s) => s.score));
  const X = (d) => L + ((new Date(String(d).replace(" ", "T")).getTime() - t0) / Math.max(1, t1 - t0)) * (W - L - R);
  const Y = (s) => T + (1 - s / maxS) * (H - T - B);
  let d = "", prev = null;
  dated.forEach((s) => { const x = X(s.date), y = Y(s.score); d += prev ? ` L ${x} ${prev} L ${x} ${y}` : `M ${x} ${y}`; prev = y; });
  const last = steps[steps.length - 1];
  d += ` L ${W - R} ${Y(last.score)}`;
  const dead = steps.some((s) => s.action === "deleted");
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" style={{ display: "block", maxWidth: W }}>
      <line x1={L} y1={Y(promoteAt)} x2={W - R} y2={Y(promoteAt)} stroke={ROLES.handled.bd} strokeDasharray="3 3" />
      <text x={L + 4} y={Y(promoteAt) - 4} fontSize="9" fill={ROLES.handled.solid} fontFamily="IBM Plex Mono, monospace">s:{promoteAt} · where a line goes live</text>
      <path d={d} fill="none" stroke={dead ? RED : STATUS[line.status]?.color || DIM} strokeWidth="2" strokeDasharray={dead ? "5 3" : undefined} />
      {dated.map((s, i) => (
        <g key={i}>
          <circle cx={X(s.date)} cy={Y(s.score)} r={s.effect < 0 ? 5 : 3.5} fill={s.effect < 0 ? RED : s.action === "promoted" ? ROLES.handled.solid : STATUS[line.status]?.color || DIM} />
          <title>{`${day(s.date)} · ${s.effect < 0 ? (s.action === "deleted" ? "deleted" : "−1") : s.action === "promoted" ? "promoted" : "+1"}${s.ev ? " · " + s.ev : ""}`}</title>
        </g>
      ))}
      <text x={L} y={H - 8} fontSize="9" fill={FAINT} fontFamily="IBM Plex Mono, monospace">{day(dated[0].date)}</text>
      <text x={W - R} y={H - 8} fontSize="9" fill={FAINT} textAnchor="end" fontFamily="IBM Plex Mono, monospace">today</text>
    </svg>
  );
};

export default function LearnedView({ onChanged }) {
  const [g, setG] = useState(null);
  const [err, setErr] = useState("");
  const [sel, setSel] = useState(null);
  const [hover, setHover] = useState(null);
  const [ribbons, setRibbons] = useState([]);
  const wrap = useRef(null), refs = useRef({});
  const load = useCallback(async () => {
    try { setG((await api.get("/api/learned/graph")).data); } catch (e) { setErr(e?.response?.data?.detail || "Could not read LEARNED.md"); }
  }, []);
  useEffect(() => { load(); }, [load]);

  // ribbons are measured off the rendered cards, so the layout stays plain flex/grid and the
  // curves follow wherever the cards land (window width, a line added, a card deleted)
  const measure = useCallback(() => {
    if (!g || !wrap.current) return;
    const box = wrap.current.getBoundingClientRect();
    const at = (id) => { const el = refs.current[id]; if (!el) return null; const r = el.getBoundingClientRect(); return { l: r.left - box.left, r: r.right - box.left, y: r.top - box.top + r.height / 2 }; };
    const out = [];
    g.lines.forEach((l) => {
      const a = at(`line:${l.key}`); if (!a) return;
      l.evidence.forEach((e) => {
        const b = at(`ev:${e.id}`); if (!b) return;
        const contra = l.steps.some((s) => s.effect < 0 && s.ev === e.id);
        out.push({ key: `${l.key}|${e.id}`, line: l.key, d: `M ${a.r} ${a.y} C ${(a.r + b.l) / 2} ${a.y}, ${(a.r + b.l) / 2} ${b.y}, ${b.l} ${b.y}`, contra });
      });
    });
    setRibbons(out);
  }, [g]);
  useLayoutEffect(() => { measure(); const t = setTimeout(measure, 60); window.addEventListener("resize", measure); return () => { clearTimeout(t); window.removeEventListener("resize", measure); }; }, [measure]);

  if (err) return <Typography variant="body2" sx={{ color: RED_INK }}>{err}</Typography>;
  if (!g) return <Typography variant="caption" sx={{ color: FAINT }}>Reading LEARNED.md…</Typography>;
  const lines = g.lines || [];
  const evidence = [];
  const seen = new Set();
  lines.forEach((l) => l.evidence.forEach((e) => { if (!seen.has(e.id)) { seen.add(e.id); evidence.push(e); } }));
  (g.loose_evidence || []).forEach((e) => { if (!seen.has(e.id)) { seen.add(e.id); evidence.push({ ...e, loose: true }); } });
  evidence.sort((a, b) => String(b.date || "").localeCompare(String(a.date || "")));
  const selLine = lines.find((l) => l.key === sel) || (g.deleted || []).find((l) => l.key === sel);
  const adopt = async (key) => { await api.post("/api/learn/adopt", { key }); await load(); onChanged?.(); };
  const groups = ["live", "proposed", "hypothesis"].map((s) => [s, lines.filter((l) => l.status === s)]);

  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 1.5 }}>
      <Typography variant="caption" sx={{ color: DIM, lineHeight: 1.5 }}>
        <b style={{ ...mono, fontSize: 10, letterSpacing: 1, color: FAINT }}>WHAT DRIVES WHAT · </b>
        a ribbon is one of your verdicts feeding a line; red where it contradicted. Click a line for its ledger — every point it gained or lost, on one clock.
        {g.history_since ? "" : " History starts recording from now; today's ledgers are reconstructed from the evidence dates."}
      </Typography>
      <Box ref={wrap} sx={{ position: "relative", display: "grid", gridTemplateColumns: "200px minmax(0, 1fr) 320px", gap: 3, alignItems: "start" }}>
        <svg style={{ position: "absolute", inset: 0, width: "100%", height: "100%", pointerEvents: "none", overflow: "visible" }}>
          {ribbons.map((r) => {
            const on = hover ? hover === r.line : sel ? sel === r.line : true;
            return <path key={r.key} d={r.d} fill="none" stroke={r.contra ? RED : ROLES.handled.solid} strokeWidth={r.contra ? 2 : 3}
              strokeDasharray={r.contra ? "6 4" : undefined} opacity={on ? (hover || sel ? 0.75 : 0.35) : 0.08} />;
          })}
        </svg>
        {/* SOUL */}
        <Box sx={{ display: "flex", flexDirection: "column", gap: 1 }}>
          <Typography sx={{ ...mono, fontSize: 9.5, letterSpacing: 1, color: FAINT, fontWeight: 700 }}>SOUL.md · OUTRANKS</Typography>
          {(g.soul || []).map((r, i) => (
            <Box key={i} sx={{ p: 1, borderRadius: 2, bgcolor: ROLES.working.tint, border: `1px solid ${ROLES.working.bd}`, fontSize: 11, color: ROLES.working.ink, lineHeight: 1.4 }}>{r.text}</Box>
          ))}
          <Typography variant="caption" sx={{ color: FAINT, fontSize: 10.5 }}>A learned line never overrides these; where they disagree, SOUL wins.</Typography>
        </Box>
        {/* lines */}
        <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
          {groups.map(([status, ls]) => (
            <Box key={status} sx={{ display: "flex", flexDirection: "column", gap: 1 }}>
              <Typography sx={{ ...mono, fontSize: 9.5, letterSpacing: 1, color: status === "proposed" ? RED : FAINT, fontWeight: 700 }}>{STATUS[status].label}</Typography>
              {ls.length === 0 && <Typography variant="caption" sx={{ color: FAINT }}>nothing here yet</Typography>}
              {ls.map((l) => (
                <Box key={l.key} ref={(el) => { refs.current[`line:${l.key}`] = el; }}
                  onClick={() => setSel(sel === l.key ? null : l.key)} onMouseEnter={() => setHover(l.key)} onMouseLeave={() => setHover(null)}
                  sx={{ p: 1.1, borderRadius: 2, cursor: "pointer", bgcolor: STATUS[status].tint, border: `1px solid ${sel === l.key ? STATUS[status].color : STATUS[status].bd}`,
                    boxShadow: sel === l.key ? "0 1px 4px rgba(30,50,38,.12)" : "none" }}>
                  <Box sx={{ display: "flex", alignItems: "center", gap: 0.75, mb: 0.4 }}>
                    <Score s={l.score} color={STATUS[status].color} />
                    <Typography variant="caption" sx={{ color: FAINT, fontSize: 10 }}>seen {l.seen} · {l.evidence.length} verdict{l.evidence.length === 1 ? "" : "s"}</Typography>
                    <Box sx={{ flex: 1 }} />
                    {l.eligible && status === "hypothesis" && <Chip size="small" label="earned it" sx={{ height: 16, fontSize: 9.5, bgcolor: ROLES.handled.tint, color: ROLES.handled.ink }} />}
                    {status !== "live" && (
                      <Button size="small" onClick={(e) => { e.stopPropagation(); adopt(l.key); }} sx={{ fontSize: 10.5, py: 0, minWidth: 0 }}
                        title="Move this line into the live section — it rides into every prompt from now on">Adopt</Button>
                    )}
                  </Box>
                  <Typography variant="body2" sx={{ fontSize: 12.5, lineHeight: 1.4, color: INK }}>{l.text}</Typography>
                </Box>
              ))}
            </Box>
          ))}
          {(g.deleted || []).length > 0 && (
            <Box sx={{ display: "flex", flexDirection: "column", gap: 1 }}>
              <Typography sx={{ ...mono, fontSize: 9.5, letterSpacing: 1, color: RED, fontWeight: 700 }}>DIED · contradicted until s:0</Typography>
              {g.deleted.map((l) => (
                <Box key={l.key} onClick={() => setSel(sel === l.key ? null : l.key)}
                  sx={{ p: 1.1, borderRadius: 2, cursor: "pointer", bgcolor: RED_TINT, border: `1px dashed ${RED_BD}`, color: RED_INK, opacity: .85 }}>
                  <Typography variant="caption" sx={{ ...mono, fontSize: 10 }}>deleted {day(l.deleted_at)} · {l.contradictions.length} contradiction{l.contradictions.length === 1 ? "" : "s"}</Typography>
                  <Typography variant="body2" sx={{ fontSize: 12.5, textDecoration: "line-through" }}>{l.text}</Typography>
                </Box>
              ))}
            </Box>
          )}
        </Box>
        {/* evidence */}
        <Box sx={{ display: "flex", flexDirection: "column", gap: 0.75 }}>
          <Typography sx={{ ...mono, fontSize: 9.5, letterSpacing: 1, color: FAINT, fontWeight: 700 }}>YOUR VERDICTS · THE EVIDENCE</Typography>
          {evidence.slice(0, 40).map((e) => {
            const on = !hover && !sel ? true : lines.some((l) => (l.key === (hover || sel)) && l.evidence.some((x) => x.id === e.id));
            return (
              <Box key={e.id} ref={(el) => { refs.current[`ev:${e.id}`] = el; }}
                sx={{ p: 0.8, borderRadius: 1.5, bgcolor: PANEL, border: `1px solid ${BORDER}`, fontSize: 11, lineHeight: 1.35, opacity: on ? 1 : 0.35 }}>
                <Typography variant="caption" sx={{ ...mono, fontSize: 9.5, color: FAINT, display: "block" }}>{e.id} · {day(e.date)}{e.loose ? " · not yet in any line" : ""}</Typography>
                <Box sx={{ color: INK }}>{String(e.label || "").slice(0, 140)}</Box>
              </Box>
            );
          })}
          {evidence.length === 0 && <Typography variant="caption" sx={{ color: FAINT }}>No verdicts yet — "Not our task" and "Not a task" write here.</Typography>}
        </Box>
      </Box>
      {selLine && (
        <Box sx={{ p: 1.5, bgcolor: PANEL, border: `1px solid ${BORDER}`, borderRadius: 2 }}>
          <Typography sx={{ ...mono, fontSize: 9.5, letterSpacing: 1, color: FAINT, fontWeight: 700, mb: 0.5 }}>THE LEDGER · {selLine.text.slice(0, 90)}</Typography>
          {selLine.status === "deleted" ? (
            <Typography variant="body2" sx={{ color: RED_INK, fontSize: 12 }}>
              Deleted {day(selLine.deleted_at)} after {selLine.contradictions.length} contradiction{selLine.contradictions.length === 1 ? "" : "s"}
              {selLine.contradictions.length ? ": " + selLine.contradictions.map((c) => `${day(c.date)}${c.ev ? " (" + c.ev + ")" : ""}`).join(", ") : ""}.
            </Typography>
          ) : (
            <Ledger line={selLine} promoteAt={g.promote_at} />
          )}
          {selLine.evidence && (
            <Box sx={{ display: "flex", flexDirection: "column", gap: 0.4, mt: 1 }}>
              {selLine.steps.filter((s) => s.date).map((s, i) => {
                const e = selLine.evidence.find((x) => x.id === s.ev);
                return (
                  <Typography key={i} variant="caption" sx={{ fontSize: 11, color: s.effect < 0 ? RED_INK : INK }}>
                    <b style={{ ...mono, color: s.effect < 0 ? RED : ROLES.handled.solid }}>{s.effect < 0 ? (s.action === "deleted" ? "×" : "−1") : s.action === "promoted" ? "↑" : "+1"}</b>
                    {" "}{day(s.date)} · {s.ev || s.action}{e ? " · " + String(e.label).slice(0, 110) : ""}
                  </Typography>
                );
              })}
            </Box>
          )}
        </Box>
      )}
    </Box>
  );
}
