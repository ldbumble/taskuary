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
import { plural } from "./timeWords.js";
import { MARKS, MARK_HINT, groupLines, marksFor, personDoc } from "./learnedGroups.js";
import ConnectAi from "./ConnectAi.jsx";

// a line's colours by where it stands; the HEADINGS are the subjects and who reads each (learnedGroups.groupLines) - "rides into every
// prompt" was never true once each reader took its own sections (the memory redesign, 2026-10-25)
const STATUS = {
  live:       { label: "IN USE", color: ROLES.handled.solid, tint: ROLES.handled.tint, bd: ROLES.handled.bd },
  proposed:   { label: "PROPOSED · your call — would hide mail", color: ROLES.info.solid, tint: ROLES.info.tint, bd: ROLES.info.bd },
  hypothesis: { label: "HYPOTHESES · still earning it", color: ROLES.muted.solid, tint: PANEL, bd: BORDER },
};
const RED = ROLES.you.solid, RED_INK = ROLES.you.ink, RED_TINT = ROLES.you.tint, RED_BD = ROLES.you.bd;
const day = (d) => (d ? String(d).slice(5, 10).replace("-", "/") : "");
const short = (s, n) => { const t = String(s || "").replace(/^\d{4}-\d{2}-\d{2}:\s*/, ""); return t.length > n ? t.slice(0, n - 1) + "…" : t; };

// The badge shows what the line is WORTH, not what its tag says: an untested line loses a point
// per quiet month, so a stale s:5 counts as less and the strikethrough says by how much.
const Score = ({ s, eff, color }) => (
  <Box component="span" sx={{ ...mono, fontWeight: 600, fontSize: 10, borderRadius: 1, px: 0.6, color: "#fff", bgcolor: color }}>
    {eff != null && eff !== s && <Box component="span" sx={{ opacity: 0.6, textDecoration: "line-through", mr: 0.4 }}>s:{s}</Box>}
    s:{eff != null ? eff : s}
  </Box>
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
      <Typography sx={{ ...mono, fontSize: 9.5, letterSpacing: 1, color: FAINT, fontWeight: 600, mb: 0.5 }}>THE LEDGER · every point gained or lost</Typography>
      <Ledger line={line} promoteAt={promoteAt} />
      <Typography sx={{ ...mono, fontSize: 9.5, letterSpacing: 1, color: FAINT, fontWeight: 600, mt: 1.25, mb: 0.75 }}>
        WHAT FED IT · {plural(evs.length, "verdict")}, oldest first{contraIds.size ? ` · ${contraIds.size} against` : ""}
      </Typography>
      <Box sx={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(230px, 1fr))", gap: 0.75 }}>
        {evs.map((e) => <Evidence key={e.id} e={e} contra={contraIds.has(e.id)} innerRef={() => {}} />)}
        {evs.length === 0 && <Typography variant="caption" sx={{ color: FAINT }}>no evidence ids on this line</Typography>}
      </Box>
    </Box>
  );
};

// KEEP / WRONG / FORGET on the line itself (the owner's ruling 2, 2026-10-23; on Visualize too, 2026-10-25) - quiet words, never a row
// of filled buttons: the line is what you read, the three are how you correct it
export const MarkRow = ({ marks, onMark, busy }) => (
  <Box sx={{ display: "inline-flex", gap: 0.25, flexShrink: 0 }} data-tq-learned-marks="">
    {marks.map((m) => (
      <Button key={m} size="small" disabled={busy} data-tq-mark={m} title={MARK_HINT[m]} onClick={(e) => { e.stopPropagation(); onMark(m); }}
        sx={{ fontSize: 10.5, py: 0, px: 0.75, minWidth: 0, minHeight: 22, color: m === "wrong" ? RED_INK : DIM }}>{MARKS[m]}</Button>
    ))}
  </Box>
);

export default function LearnedView({ onChanged, onPerson, people = [] }) {
  const [g, setG] = useState(null);
  const [err, setErr] = useState("");
  const [open, setOpen] = useState(null);        // the line whose fan is showing
  const [pinned, setPinned] = useState(null);    // click keeps it open when the pointer leaves
  const [looseOpen, setLooseOpen] = useState(false);
  const hoverT = React.useRef(null);
  const enter = (key) => { clearTimeout(hoverT.current); hoverT.current = setTimeout(() => setOpen(key), 140); };
  const leave = () => { clearTimeout(hoverT.current); hoverT.current = setTimeout(() => setOpen(pinned), 220); };
  const pin = (key) => { const next = pinned === key ? null : key; setPinned(next); setOpen(next || key); };
  const load = useCallback(async () => {
    try { setG((await api.get("/api/learned/graph")).data); } catch (e) { setErr(e?.response?.data?.detail || "Could not read LEARNED.md"); }
  }, []);
  useEffect(() => { load(); }, [load]);
  const [busy, setBusy] = useState(""), [said, setSaid] = useState(null);      // said: {key, msg} - why a mark did not take, by its line
  const mark = async (key, how) => {
    setBusy(key); setSaid(null);
    try { await api.post("/api/learned/mark", { key, how }); await load(); onChanged?.(); }
    catch (e) { setSaid({ key, msg: e?.response?.data?.detail || "That did not go through - nothing was changed." }); if (e?.response?.status === 404) await load(); }
    finally { setBusy(""); }
  };
  if (err) return <Typography variant="body2" sx={{ color: RED_INK }}>{err}</Typography>;
  if (!g) return <Typography variant="caption" sx={{ color: FAINT }}>Reading LEARNED.md…</Typography>;
  const groups = groupLines(g);
  const loose = g.loose_evidence || [];

  const Card = ({ l }) => {
    const st = STATUS[l.status]; const isOpen = open === l.key && !l.own; const isPinned = pinned === l.key;
    return (
      <Box onMouseEnter={() => enter(l.key)} onMouseLeave={leave}
        sx={{ p: 1.25, borderRadius: 2, bgcolor: st.tint, border: `${isOpen ? 1.5 : 1}px solid ${isOpen ? st.color : st.bd}`,
          boxShadow: isPinned ? "0 1px 4px rgba(30,50,38,.14)" : "none" }}>
        <Box onClick={() => !l.own && pin(l.key)} sx={{ cursor: l.own ? "default" : "pointer" }} title={l.own ? undefined : isPinned ? "Click to unpin" : "Click to keep this open"}>
          <Box sx={{ display: "flex", alignItems: "center", gap: 0.75, mb: 0.4 }} data-tq-learned-line={l.key}>
            {l.own ? <Typography variant="caption" sx={{ ...mono, color: st.color, fontSize: 10, fontWeight: 600 }}>YOURS · as you wrote it</Typography> : <>
              <Score s={l.score} eff={l.effective} color={st.color} />
              <Typography variant="caption" sx={{ color: FAINT, fontSize: 10 }}
                title={l.effective !== l.score ? `Nothing has confirmed this since ${l.seen}, so it counts as s:${l.effective}` : ""}>seen {l.seen}</Typography>
              <Typography variant="caption" sx={{ ...mono, color: st.color, fontSize: 10, fontWeight: 600 }}>
                {isOpen ? "▾" : "▸"} {plural(l.evidence.length, "act")}{isPinned ? " · pinned" : ""}
              </Typography></>}
            <Box sx={{ flex: 1 }} />
            {l.eligible && l.status === "hypothesis" && <Chip size="small" label="earned it" sx={{ height: 16, fontSize: 9.5, bgcolor: ROLES.handled.tint, color: ROLES.handled.ink }} />}
            <MarkRow marks={marksFor(l)} busy={busy === l.key} onMark={(how) => mark(l.key, how)} />
          </Box>
          <Typography variant="body2" sx={{ fontSize: 12.5, lineHeight: 1.4, color: INK }}>{l.text}</Typography>
          {said?.key === l.key && <Typography variant="caption" role="alert" sx={{ color: RED_INK, display: "block", mt: 0.4 }}>{said.msg}</Typography>}
        </Box>
        {isOpen && <Fan line={l} promoteAt={g.promote_at} />}
      </Box>
    );
  };

  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 1.5, p: 2, bgcolor: PANEL, border: `1px solid ${BORDER}`, borderRadius: 2 }}>
      {/* nothing is learned with no AI connected - said once, with its way out (the design, 3.8; ConnectAi, 2026-10-21) */}
      {g.ai === false && (
        <Box sx={{ display: "flex", alignItems: "center", gap: 1, p: 1, borderRadius: 1.5, bgcolor: PANEL2, border: `1px solid ${BORDER}` }} data-tq-learn-no-ai="">
          <Typography variant="body2" sx={{ fontSize: 12.5, color: INK, flex: 1 }}>Connect an AI to learn how you work. What you write here is read either way.</Typography>
          <ConnectAi />
        </Box>
      )}
      <Typography variant="caption" sx={{ color: DIM, lineHeight: 1.5 }}>
        <b style={{ ...mono, fontSize: 10, letterSpacing: 1, color: FAINT }}>WHAT DRIVES WHAT · </b>
        every learned line shows how many of your own acts fed it. Keep makes a line yours, Wrong takes it out for good, Forget takes it out for now. Point at one and they fan out underneath — red where one contradicted — with the line's ledger: every point it gained or lost, on one clock. Click to keep it open.
        {g.history_since ? "" : " History records from now; today's ledgers are reconstructed from the evidence dates."}
      </Typography>
      <Box sx={{ display: "grid", gridTemplateColumns: "200px minmax(0, 1fr)", gap: 3, alignItems: "start" }}>
        <Box sx={{ display: "flex", flexDirection: "column", gap: 1 }}>
          <Typography sx={{ ...mono, fontSize: 9.5, letterSpacing: 1, color: FAINT, fontWeight: 600 }}>SOUL.md · OUTRANKS</Typography>
          {(g.soul || []).map((r, i) => (
            <Box key={i} sx={{ p: 1, borderRadius: 2, bgcolor: PANEL2, border: `1px solid ${BORDER}`, fontSize: 11, color: DIM, lineHeight: 1.4 }}>{r.text}</Box>
          ))}
          <Typography variant="caption" sx={{ color: FAINT, fontSize: 10.5 }}>A learned line never overrides these; where they disagree, SOUL wins.</Typography>
        </Box>
        <Box sx={{ display: "flex", flexDirection: "column", gap: 2, minWidth: 0 }}>
          {groups.map((sec) => (
            <Box key={sec.slug} sx={{ display: "flex", flexDirection: "column", gap: 1 }} data-tq-learned-section={sec.slug}>
              <Typography sx={{ ...mono, fontSize: 9.5, letterSpacing: 1, color: sec.slug === "proposed" ? RED : FAINT, fontWeight: 600 }}>
                {sec.title.toUpperCase()} · <span style={{ fontWeight: 400, letterSpacing: 0, textTransform: "none" }}>{sec.reads}</span></Typography>
              {sec.lines.length === 0 && <Typography variant="caption" sx={{ color: FAINT }}>nothing here yet</Typography>}
              {/* YOUR PEOPLE under the person each line is about, with their page in the Docs tree where the ledger keeps one */}
              {sec.people ? sec.people.map(({ subject, lines: ls }) => {
                const page = personDoc(subject, people);
                return (
                  <Box key={subject || "-"} sx={{ display: "flex", flexDirection: "column", gap: 0.75 }}>
                    {subject && <Typography variant="caption" sx={{ ...mono, fontSize: 10, color: DIM }}>
                      {subject}{page && onPerson ? <> · <Box component="button" type="button" data-tq-person-link={page} onClick={() => onPerson(page)}
                        sx={{ border: 0, p: 0, bgcolor: "transparent", color: "#55697a", font: "inherit", textDecoration: "underline", cursor: "pointer" }}>their page</Box></> : null}
                    </Typography>}
                    {ls.map((l) => <Card key={l.key} l={l} />)}
                  </Box>);
              }) : sec.lines.map((l) => <Card key={l.key} l={l} />)}
            </Box>
          ))}
          {(g.deleted || []).length > 0 && (
            <Box sx={{ display: "flex", flexDirection: "column", gap: 1 }}>
              <Typography sx={{ ...mono, fontSize: 9.5, letterSpacing: 1, color: RED, fontWeight: 600 }}>DIED · contradicted until s:0</Typography>
              {g.deleted.map((l) => (
                <Box key={l.key} sx={{ p: 1.1, borderRadius: 2, bgcolor: RED_TINT, border: `1px dashed ${RED_BD}`, color: RED_INK, opacity: .85 }}>
                  <Typography variant="caption" sx={{ ...mono, fontSize: 10 }}>
                    deleted {day(l.deleted_at)} · {plural(l.contradictions.length, "contradiction")}
                    {l.contradictions.length ? " · " + l.contradictions.map((c) => `${day(c.date)}${c.ev ? " (" + c.ev + ")" : ""}`).join(", ") : ""}
                  </Typography>
                  <Typography variant="body2" sx={{ fontSize: 12.5, textDecoration: "line-through" }}>{l.text}</Typography>
                </Box>
              ))}
            </Box>
          )}
          {loose.length > 0 && (
            <Box>
              <Typography component="button" type="button" aria-expanded={looseOpen} onClick={() => setLooseOpen((o) => !o)}
                sx={{ ...mono, fontSize: 9.5, letterSpacing: 1, color: FAINT, fontWeight: 600, cursor: "pointer",
                  appearance: "none", border: 0, bgcolor: "transparent", p: 0, textAlign: "left", display: "block" }}>
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
