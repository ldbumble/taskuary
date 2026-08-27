// LEARNED.md as a picture (discussion #27). Left: what SOUL.md says (it outranks). Right: the
// learned lines by status - live, proposed, still hypotheses, died. Open a line and its
// evidence FANS OUT underneath it: a compact grid of the verdicts that fed it, a short thread
// from the line to each, red where one contradicted, plus the line's ledger - its score over
// time with the exact event that moved it. Evidence never leaves the rule it belongs to, so a
// seventeen-verdict rule is a card that grows, not a column three screens tall.
// Nothing here is a new source of truth: lines are the doc's own [s:N | ev | seen] tags, the
// chips its ev ids resolved to real rows, the history the learned_history rows the learn pass writes.
import React, { useCallback, useEffect, useState } from "react";
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
const short = (s, n) => { const t = String(s || "").replace(/^\d{4}-\d{2}-\d{2}:\s*/, ""); return t.length > n ? t.slice(0, n - 1) + "…" : t; };

const Score = ({ s, color }) => (
  <Box component="span" sx={{ ...mono, fontWeight: 700, fontSize: 10, borderRadius: 1, px: 0.6, color: "#fff", bgcolor: color }}>s:{s}</Box>
);

// The ledger: one line's life on one clock.
const Ledger = ({ line, promoteAt }) => {
  const steps = line.steps || [];
  const dated = steps.filter((s) => s.date);
  if (!dated.length) return <Typography variant="caption" sx={{ color: FAINT }}>No dated evidence yet — this line has a score but nothing to draw it from.</Typography>;
  const W = 720, H = 96, L = 30, R = 14, T = 12, B = 22;
  const t0 = new Date(dated[0].date.replace(" ", "T")).getTime(), t1 = Math.max(Date.now(), new Date(dated[dated.length - 1].date.replace(" ", "T")).getTime());
  const maxS = Math.max(promoteAt + 1, ...steps.map((s) => s.score));
  const X = (d) => L + ((new Date(String(d).replace(" ", "T")).getTime() - t0) / Math.max(1, t1 - t0)) * (W - L - R);
  const Y = (s) => T + (1 - s / maxS) * (H - T - B);
  let d = "", prev = null;
  dated.forEach((s) => { const x = X(s.date), y = Y(s.score); d += prev ? ` L ${x} ${prev} L ${x} ${y}` : `M ${x} ${y}`; prev = y; });
  const last = steps[steps.length - 1];
  d += ` L ${W - R} ${Y(last.score)}`;
  const dead = steps.some((s) => s.action === "deleted");
  const col = dead ? RED : STATUS[line.status]?.color || DIM;
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" style={{ display: "block", maxWidth: W }}>
      <line x1={L} y1={Y(promoteAt)} x2={W - R} y2={Y(promoteAt)} stroke={ROLES.handled.bd} strokeDasharray="3 3" />
      <text x={W - R} y={Y(promoteAt) - 4} fontSize="9" fill={ROLES.handled.solid} textAnchor="end" fontFamily="IBM Plex Mono, monospace">s:{promoteAt} · live from here</text>
      <path d={d} fill="none" stroke={col} strokeWidth="2" strokeDasharray={dead ? "5 3" : undefined} />
      {dated.map((s, i) => (
        <g key={i}>
          <circle cx={X(s.date)} cy={Y(s.score)} r={s.effect < 0 ? 5 : 3.5} fill={s.effect < 0 ? RED : s.action === "promoted" ? ROLES.handled.solid : col} />
          <title>{`${day(s.date)} · ${s.effect < 0 ? (s.action === "deleted" ? "deleted" : "−1") : s.action === "promoted" ? "promoted" : "+1"}${s.ev ? " · " + s.ev : ""}`}</title>
        </g>
      ))}
      <text x={L} y={H - 7} fontSize="9" fill={FAINT} fontFamily="IBM Plex Mono, monospace">{day(dated[0].date)}</text>
      <text x={W - R} y={H - 7} fontSize="9" fill={FAINT} textAnchor="end" fontFamily="IBM Plex Mono, monospace">today</text>
    </svg>
  );
};

// One evidence chip: id · date on top, the verdict's own words under it.
const Evidence = ({ e, contra, innerRef }) => (
  <Box ref={innerRef} sx={{ p: 0.8, borderRadius: 1.5, bgcolor: contra ? RED_TINT : PANEL, border: `1px solid ${contra ? RED_BD : BORDER}`,
    fontSize: 11, lineHeight: 1.35, minWidth: 0 }} title={e.label}>
    <Typography variant="caption" sx={{ ...mono, fontSize: 9.5, color: contra ? RED_INK : FAINT, display: "block" }}>
      {contra ? "−1 · " : ""}{e.id} · {day(e.date)}{e.kind === "review" ? " · review" : e.kind === "task" ? " · task" : ""}
    </Typography>
    <Box sx={{ color: contra ? RED_INK : INK, overflow: "hidden", display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical" }}>{short(e.label, 110)}</Box>
  </Box>
);

// The fan: the line's evidence laid out beneath it, oldest first, in the same tint as the
// line. Sitting inside the card is what says "these fed it" - threads drawn to each chip
// read as spaghetti, and were removed.
const Fan = ({ line, promoteAt }) => {
  const contraIds = new Set((line.steps || []).filter((s) => s.effect < 0 && s.ev).map((s) => s.ev));
  const evs = [...(line.evidence || [])].sort((a, b) => String(a.date || "").localeCompare(String(b.date || "")));
  return (
    <Box sx={{ mt: 1.25, pt: 1, borderTop: `1px dashed ${BORDER}` }}>
      <Typography sx={{ ...mono, fontSize: 9.5, letterSpacing: 1, color: FAINT, fontWeight: 700, mb: 0.5 }}>THE LEDGER · every point gained or lost</Typography>
      <Ledger line={line} promoteAt={promoteAt} />
      <Typography sx={{ ...mono, fontSize: 9.5, letterSpacing: 1, color: FAINT, fontWeight: 700, mt: 1.25, mb: 0.75 }}>
        WHAT FED IT · {evs.length} verdict{evs.length === 1 ? "" : "s"}, oldest first{contraIds.size ? ` · ${contraIds.size} against` : ""}
      </Typography>
      <Box sx={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(230px, 1fr))", gap: 0.75 }}>
        {evs.map((e) => <Evidence key={e.id} e={e} contra={contraIds.has(e.id)} innerRef={() => {}} />)}
        {evs.length === 0 && <Typography variant="caption" sx={{ color: FAINT }}>no evidence ids on this line</Typography>}
      </Box>
    </Box>
  );
};

export default function LearnedView({ onChanged }) {
  const [g, setG] = useState(null);
  const [err, setErr] = useState("");
  const [open, setOpen] = useState(null);
  const [looseOpen, setLooseOpen] = useState(false);
  const load = useCallback(async () => {
    try { setG((await api.get("/api/learned/graph")).data); } catch (e) { setErr(e?.response?.data?.detail || "Could not read LEARNED.md"); }
  }, []);
  useEffect(() => { load(); }, [load]);
  if (err) return <Typography variant="body2" sx={{ color: RED_INK }}>{err}</Typography>;
  if (!g) return <Typography variant="caption" sx={{ color: FAINT }}>Reading LEARNED.md…</Typography>;
  const lines = g.lines || [];
  const adopt = async (key) => { await api.post("/api/learn/adopt", { key }); await load(); onChanged?.(); };
  const groups = ["live", "proposed", "hypothesis"].map((s) => [s, lines.filter((l) => l.status === s)]);
  const loose = g.loose_evidence || [];

  const Card = ({ l }) => {
    const st = STATUS[l.status]; const isOpen = open === l.key;
    return (
      <Box sx={{ p: 1.25, borderRadius: 2, bgcolor: st.tint, border: `${isOpen ? 1.5 : 1}px solid ${isOpen ? st.color : st.bd}` }}>
        <Box onClick={() => setOpen(isOpen ? null : l.key)} sx={{ cursor: "pointer" }}>
          <Box sx={{ display: "flex", alignItems: "center", gap: 0.75, mb: 0.4 }}>
            <Score s={l.score} color={st.color} />
            <Typography variant="caption" sx={{ color: FAINT, fontSize: 10 }}>seen {l.seen}</Typography>
            <Typography variant="caption" sx={{ ...mono, color: st.color, fontSize: 10, fontWeight: 700 }}>
              {isOpen ? "▾" : "▸"} {l.evidence.length} verdict{l.evidence.length === 1 ? "" : "s"}
            </Typography>
            <Box sx={{ flex: 1 }} />
            {l.eligible && l.status === "hypothesis" && <Chip size="small" label="earned it" sx={{ height: 16, fontSize: 9.5, bgcolor: ROLES.handled.tint, color: ROLES.handled.ink }} />}
            {l.status !== "live" && (
              <Button size="small" onClick={(e) => { e.stopPropagation(); adopt(l.key); }} sx={{ fontSize: 10.5, py: 0, minWidth: 0 }}
                title="Move this line into the live section — it rides into every prompt from now on">Adopt</Button>
            )}
          </Box>
          <Typography variant="body2" sx={{ fontSize: 12.5, lineHeight: 1.4, color: INK }}>{l.text}</Typography>
        </Box>
        {isOpen && <Fan line={l} promoteAt={g.promote_at} />}
      </Box>
    );
  };

  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 1.5, p: 2, bgcolor: PANEL, border: `1px solid ${BORDER}`, borderRadius: 2 }}>
      <Typography variant="caption" sx={{ color: DIM, lineHeight: 1.5 }}>
        <b style={{ ...mono, fontSize: 10, letterSpacing: 1, color: FAINT }}>WHAT DRIVES WHAT · </b>
        every line shows how many of your verdicts fed it. Open one and they fan out underneath — red where one contradicted — with the line's ledger: every point it gained or lost, on one clock.
        {g.history_since ? "" : " History records from now; today's ledgers are reconstructed from the evidence dates."}
      </Typography>
      <Box sx={{ display: "grid", gridTemplateColumns: "200px minmax(0, 1fr)", gap: 3, alignItems: "start" }}>
        <Box sx={{ display: "flex", flexDirection: "column", gap: 1 }}>
          <Typography sx={{ ...mono, fontSize: 9.5, letterSpacing: 1, color: FAINT, fontWeight: 700 }}>SOUL.md · OUTRANKS</Typography>
          {(g.soul || []).map((r, i) => (
            <Box key={i} sx={{ p: 1, borderRadius: 2, bgcolor: PANEL2, border: `1px solid ${BORDER}`, fontSize: 11, color: DIM, lineHeight: 1.4 }}>{r.text}</Box>
          ))}
          <Typography variant="caption" sx={{ color: FAINT, fontSize: 10.5 }}>A learned line never overrides these; where they disagree, SOUL wins.</Typography>
        </Box>
        <Box sx={{ display: "flex", flexDirection: "column", gap: 2, minWidth: 0 }}>
          {groups.map(([status, ls]) => (
            <Box key={status} sx={{ display: "flex", flexDirection: "column", gap: 1 }}>
              <Typography sx={{ ...mono, fontSize: 9.5, letterSpacing: 1, color: status === "proposed" ? RED : FAINT, fontWeight: 700 }}>{STATUS[status].label}</Typography>
              {ls.length === 0 && <Typography variant="caption" sx={{ color: FAINT }}>nothing here yet</Typography>}
              {ls.map((l) => <Card key={l.key} l={l} />)}
            </Box>
          ))}
          {(g.deleted || []).length > 0 && (
            <Box sx={{ display: "flex", flexDirection: "column", gap: 1 }}>
              <Typography sx={{ ...mono, fontSize: 9.5, letterSpacing: 1, color: RED, fontWeight: 700 }}>DIED · contradicted until s:0</Typography>
              {g.deleted.map((l) => (
                <Box key={l.key} sx={{ p: 1.1, borderRadius: 2, bgcolor: RED_TINT, border: `1px dashed ${RED_BD}`, color: RED_INK, opacity: .85 }}>
                  <Typography variant="caption" sx={{ ...mono, fontSize: 10 }}>
                    deleted {day(l.deleted_at)} · {l.contradictions.length} contradiction{l.contradictions.length === 1 ? "" : "s"}
                    {l.contradictions.length ? " · " + l.contradictions.map((c) => `${day(c.date)}${c.ev ? " (" + c.ev + ")" : ""}`).join(", ") : ""}
                  </Typography>
                  <Typography variant="body2" sx={{ fontSize: 12.5, textDecoration: "line-through" }}>{l.text}</Typography>
                </Box>
              ))}
            </Box>
          )}
          {loose.length > 0 && (
            <Box>
              <Typography onClick={() => setLooseOpen((o) => !o)} sx={{ ...mono, fontSize: 9.5, letterSpacing: 1, color: FAINT, fontWeight: 700, cursor: "pointer" }}>
                {looseOpen ? "▾" : "▸"} VERDICTS NOT YET IN ANY LINE · {loose.length}
              </Typography>
              {looseOpen && (
                <Box sx={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(210px, 1fr))", gap: 0.75, mt: 0.75 }}>
                  {loose.map((e) => <Evidence key={e.id} e={e} contra={false} innerRef={() => {}} />)}
                </Box>
              )}
              <Typography variant="caption" sx={{ color: FAINT, display: "block", mt: 0.5 }}>The next reflection reads these; a pattern two or more of them share becomes a hypothesis.</Typography>
            </Box>
          )}
        </Box>
      </Box>
    </Box>
  );
}
