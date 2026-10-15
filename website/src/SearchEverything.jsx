import { t as tx } from "./i18n.js";
// ONE SEARCH OVER EVERYTHING (the owner, 2026-10-13: "i want to be able to search for anything so search would bring up
// tasks/emails/chats/pr etc etc with little pill on it for channel/task/email"). The rail's filter found a task by its
// words and a source by its name, and a mail no task held was findable from nowhere. This is the one box: the bar at
// the top of the rail (or Ctrl+K anywhere) opens it, and every hit wears a pill saying what it is (searchHits.js).
import React, { useEffect, useMemo, useRef, useState } from "react";
import { Box, Dialog, InputBase, LinearProgress, Tooltip } from "@mui/material";
import SearchIcon from "@mui/icons-material/Search";
import TaskAltIcon from "@mui/icons-material/TaskAlt";
import MailOutlineIcon from "@mui/icons-material/MailOutline";
import ChatBubbleOutlineIcon from "@mui/icons-material/ChatBubbleOutline";
import CallMergeIcon from "@mui/icons-material/CallMerge";
import AdjustIcon from "@mui/icons-material/Adjust";
import PsychologyOutlinedIcon from "@mui/icons-material/PsychologyOutlined";
import BarChartIcon from "@mui/icons-material/BarChart";
import DescriptionOutlinedIcon from "@mui/icons-material/DescriptionOutlined";
import PowerOutlinedIcon from "@mui/icons-material/PowerOutlined";
import api from "./api";
import { agoText } from "./funnelPile.js";
import { arrange, filters, kindOf, marks, meta, terms } from "./searchHits.js";
import { ASSISTANT, BORDER, DIM, FAINT, INK, PANEL, PANEL2, PALETTE, PILL_COLORS, ACCENT, mono } from "./theme.jsx";

// colour identifies, it never shouts: each pill is a pale tint with its own ink, from the five colours - never the
// oxblood, which means "this is on you" and nothing else
const TONES = { slate: [PALETTE.slate, "#e6ebef"], sage: [PALETTE.sage, "#e5ece2"], brass: [PALETTE.brass, "#ede7da"],
  oat: [PALETTE.oat, "#ece8e1"], advisor: [ASSISTANT.ink, "#e8eee4"], pick: [PILL_COLORS.pick.fg, PILL_COLORS.pick.bg] };
const ICONS = { task: TaskAltIcon, email: MailOutlineIcon, chat: ChatBubbleOutlineIcon, pr: CallMergeIcon, issue: AdjustIcon,
  advisor: PsychologyOutlinedIcon, report: BarChartIcon, source: PowerOutlinedIcon };
const MARK = "#efe3bf";            // the matched words: a highlighter's wash, not a colour that means anything

export function Pill({ hit, sx }) {
  const k = kindOf(hit), [fg, bg] = TONES[k.tone] || TONES.oat;
  const Icon = ICONS[hit.type] || DescriptionOutlinedIcon;
  return (
    <Box component="span" data-tq-search-pill={hit.type} sx={{ display: "inline-flex", alignItems: "center", gap: 0.4, flexShrink: 0,
      height: 20, px: 0.85, borderRadius: 99, bgcolor: bg, color: fg, fontSize: 10.5, fontWeight: 650, letterSpacing: ".01em", ...sx }}>
      <Icon sx={{ fontSize: 12 }} />{k.label}
    </Box>
  );
}

const Marked = ({ text, words }) => marks(text, words).map((p, i) => (p.hit
  ? <Box key={i} component="mark" sx={{ bgcolor: MARK, color: "inherit", borderRadius: "3px", px: "1px" }}>{p.t}</Box>
  : <React.Fragment key={i}>{p.t}</React.Fragment>));

const Kbd = ({ children }) => (
  <Box component="kbd" sx={{ ...mono, fontSize: 10, color: FAINT, px: 0.6, py: "1px", borderRadius: "5px",
    border: `1px solid ${BORDER}`, borderBottomWidth: 2, bgcolor: PANEL, lineHeight: 1.4 }}>{children}</Box>
);

// The bar on the TOP LINE of the app (the owner, 2026-10-14: "it should be on top line not on top of the work rail"): it looks
// like a box and opens the real one, wherever the dialog is mounted (FeedView listens for OPEN_SEARCH).
export const OPEN_SEARCH = "tq-search-open";
export const openSearch = () => window.dispatchEvent(new Event(OPEN_SEARCH));
export function SearchBar({ onOpen }) {
  return (
    <Box component="button" type="button" onClick={onOpen} data-tq-search-open="true" aria-label={tx("Search everything (Ctrl+K)")}
      sx={{ display: "flex", alignItems: "center", gap: 0.9, width: "100%", height: 32, px: 1.1, cursor: "text",
        border: `1px solid ${BORDER}`, borderRadius: "9px", bgcolor: PANEL, fontFamily: "inherit", textAlign: "left",
        transition: "border-color .15s, box-shadow .15s",
        "&:hover": { borderColor: "#cfc7bb", boxShadow: "0 1px 3px rgba(30,50,38,.06)" } }}>
      <SearchIcon sx={{ fontSize: 16, color: FAINT }} />
      <Box component="span" sx={{ flex: 1, fontSize: 12.5, color: FAINT, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}> {tx("Search tasks, mail, chats, PRs…")}</Box>
      <Kbd>Ctrl K</Kbd>
    </Box>
  );
}

function Row({ hit, words, on, onPick, onTask, onHover }) {
  const closed = ["done", "dropped"].includes(hit.status), m = meta(hit);
  const ref = useRef(null);
  useEffect(() => { if (on) ref.current?.scrollIntoView({ block: "nearest" }); }, [on]);
  return (
    <Box ref={ref} role="option" aria-selected={on} data-tq-search-hit={hit.id} onClick={() => onPick(hit)} onMouseMove={onHover}
      onMouseDown={(e) => e.preventDefault()}
      sx={{ position: "relative", display: "flex", gap: 1.25, alignItems: "flex-start", px: 1.5, py: 1, mx: 0.75, borderRadius: "9px",
        cursor: "pointer", bgcolor: on ? "#f0ebe3" : "transparent", transition: "background-color .08s" }}>
      <Pill hit={hit} sx={{ mt: "1px", minWidth: 62, justifyContent: "center" }} />
      <Box sx={{ flex: 1, minWidth: 0 }}>
        <Box sx={{ display: "flex", alignItems: "baseline", gap: 0.75, minWidth: 0 }}>
          <Box sx={{ fontSize: 13, fontWeight: 600, color: closed ? DIM : INK, lineHeight: 1.35, minWidth: 0,
            overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}><Marked text={hit.title} words={words} /></Box>
          {hit.more > 0 && <Box component="span" sx={{ fontSize: 10.5, color: FAINT, flexShrink: 0 }}>+{hit.more} {tx("in thread")}</Box>}
        </Box>
        {(m.length > 0 || hit.when) && (
          <Box sx={{ fontSize: 11.5, color: FAINT, mt: 0.15, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
            {[...m, hit.when ? agoText(hit.when) : ""].filter(Boolean).join(" · ")}</Box>
        )}
        {hit.snippet && (
          <Box sx={{ fontSize: 11.5, color: DIM, mt: 0.35, lineHeight: 1.45, display: "-webkit-box", WebkitLineClamp: 2,
            WebkitBoxOrient: "vertical", overflow: "hidden" }}><Marked text={hit.snippet} words={words} /></Box>
        )}
      </Box>
      {hit.ref && (
        <Tooltip title={hit.type === "task" ? (closed ? "Closed - open it to read or reopen it" : "Open the task") : "Open the task it is on"}>
          <Box component="button" type="button" data-tq-search-task={hit.tid}
            onMouseDown={(e) => e.preventDefault()} onClick={(e) => { e.stopPropagation(); onTask(hit.tid); }}
            sx={{ ...mono, flexShrink: 0, fontSize: 10.5, color: closed ? FAINT : ACCENT, bgcolor: "transparent", border: `1px solid ${BORDER}`,
              borderRadius: "6px", px: 0.6, py: "1px", cursor: "pointer", textDecoration: closed ? "line-through" : "none",
              "&:hover": { borderColor: "#cbd4dc", bgcolor: "#e6ebef" } }}>{hit.ref}</Box>
        </Tooltip>
      )}
    </Box>
  );
}

export default function SearchEverything({ open, onClose, onOpenTask, onOpenMessage, onPickSource }) {
  const [q, setQ] = useState(""), [res, setRes] = useState(null), [busy, setBusy] = useState(false);
  const [only, setOnly] = useState(""), [at, setAt] = useState(0);
  useEffect(() => { if (!open) { setQ(""); setRes(null); setOnly(""); setAt(0); } }, [open]);
  useEffect(() => {
    const t = q.trim();
    if (terms(t).length === 0) { setRes(null); setBusy(false); return undefined; }
    let alive = true; setBusy(true);
    const h = setTimeout(() => api.get("/api/search", { params: { q: t } })
      .then(({ data }) => { if (alive) { setRes(data); setAt(0); } })
      .catch(() => { if (alive) setRes({ q: t, hits: [], failed: true }); })
      .finally(() => { if (alive) setBusy(false); }), 180);
    return () => { alive = false; clearTimeout(h); };
  }, [q]);
  const hits = res?.hits || [];
  const strip = useMemo(() => filters(hits), [hits]);
  const shown = useMemo(() => arrange(hits, only), [hits, only]);
  const words = useMemo(() => terms(res?.q || ""), [res]);
  useEffect(() => { if (only && !strip.some((f) => f.key === only)) setOnly(""); }, [strip, only]);

  const pick = (h) => {
    if (!h) return;
    onClose();
    if (h.type === "task") onOpenTask?.(h.tid, h);
    else if (h.type === "source") onPickSource?.(h.pick);
    else if (!onOpenMessage?.(h.mid, h) && h.tid) onOpenTask?.(h.tid, h);
  };
  const key = (e) => {
    const n = shown.flat.length;
    if (e.key === "ArrowDown") { e.preventDefault(); setAt((i) => (n ? (i + 1) % n : 0)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setAt((i) => (n ? (i - 1 + n) % n : 0)); }
    else if (e.key === "Enter") { e.preventDefault(); pick(shown.flat[at]); }
    else if (e.key === "Tab" && strip.length > 1) {
      e.preventDefault();
      const i = strip.findIndex((f) => f.key === only), next = strip[(i + (e.shiftKey ? -1 : 1) + strip.length) % strip.length];
      setOnly(next.key); setAt(0);
    }
  };
  let i = -1;
  return (
    <Dialog open={open} onClose={onClose} data-tq-search="true"
      slotProps={{ backdrop: { sx: { bgcolor: "rgba(38,37,33,.28)", backdropFilter: "blur(2px)" } } }}
      sx={{ "& .MuiDialog-container": { alignItems: "flex-start" } }}
      PaperProps={{ sx: { mt: "9vh", width: 680, maxWidth: "calc(100vw - 32px)", borderRadius: "14px", bgcolor: PANEL,
        border: `1px solid #dad4cb`, boxShadow: "0 24px 64px rgba(30,50,38,.22)", overflow: "hidden", m: 2 } }}>
      <Box sx={{ display: "flex", alignItems: "center", gap: 1.25, px: 2, height: 56, borderBottom: `1px solid ${BORDER}` }}>
        <SearchIcon sx={{ fontSize: 21, color: q ? INK : FAINT }} />
        <InputBase autoFocus fullWidth value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={key}
          placeholder={tx("Search tasks, mail, chats, pull requests, the Advisor…")} inputProps={{ "aria-label": "Search everything", "data-tq-search-input": "true" }}
          sx={{ fontSize: 16, color: INK, "& input::placeholder": { color: FAINT, opacity: 1 } }} />
        <Kbd>Esc</Kbd>
      </Box>
      <Box sx={{ height: 2 }}>{busy && <LinearProgress sx={{ height: 2, bgcolor: "transparent", "& .MuiLinearProgress-bar": { bgcolor: ACCENT } }} />}</Box>
      {strip.length > 1 && (
        <Box role="tablist" sx={{ display: "flex", gap: 0.6, px: 2, pt: 1, pb: 0.5, flexWrap: "wrap" }}>
          {strip.map((f) => (
            <Box key={f.key || "all"} component="button" type="button" role="tab" aria-selected={only === f.key} data-tq-search-filter={f.key || "all"}
              onMouseDown={(e) => e.preventDefault()} onClick={() => { setOnly(f.key); setAt(0); }}
              sx={{ display: "inline-flex", alignItems: "center", gap: 0.6, height: 26, px: 1.1, borderRadius: 99, cursor: "pointer",
                fontFamily: "inherit", fontSize: 11.5, fontWeight: 600, border: `1px solid ${only === f.key ? "#cbd4dc" : BORDER}`,
                bgcolor: only === f.key ? "#e4e9ee" : "transparent", color: only === f.key ? "#41525f" : DIM,
                "&:hover": { bgcolor: only === f.key ? "#e4e9ee" : PANEL2 } }}>
              {f.label}<Box component="span" sx={{ fontSize: 10.5, color: FAINT, fontWeight: 600 }}>{f.n}</Box>
            </Box>
          ))}
        </Box>
      )}
      <Box role="listbox" sx={{ maxHeight: "min(60vh, 560px)", overflowY: "auto", py: 0.75 }}>
        {!res && (
          <Box sx={{ px: 2.5, py: 3, textAlign: "center" }}>
            <Box sx={{ display: "flex", justifyContent: "center", gap: 0.6, flexWrap: "wrap", mb: 1.25 }}>
              {["task", "email", "chat", "pr", "advisor", "report", "source"].map((t) => <Pill key={t} hit={{ type: t }} />)}
            </Box>
            <Box sx={{ fontSize: 12.5, color: DIM }}>{tx("Every task, mail, chat line, pull request, Advisor post and source - open or closed.")}</Box>
          </Box>
        )}
        {res && !hits.length && !busy && (
          <Box sx={{ px: 2.5, py: 3, textAlign: "center", fontSize: 12.5, color: DIM }}>
            {res.failed ? "Search didn't answer - try again in a moment." : <>{tx("Nothing matches “")}{res.q}”.</>}</Box>
        )}
        {shown.groups.map((g) => (
          <Box key={g.group} sx={{ mb: 0.5 }}>
            <Box sx={{ px: 2.25, pt: 1, pb: 0.4, fontSize: 11.5, fontWeight: 600, color: FAINT, display: "flex", gap: 0.6 }}>
              {g.group}<Box component="span" sx={{ fontWeight: 500 }}>{g.hits.length}</Box></Box>
            {g.hits.map((h) => { i += 1; const n = i; return (
              <Row key={h.id} hit={h} words={words} on={n === at} onPick={pick} onHover={() => n !== at && setAt(n)}
                onTask={(tid) => { onClose(); onOpenTask?.(tid); }} />); })}
          </Box>
        ))}
      </Box>
      <Box sx={{ display: "flex", alignItems: "center", gap: 1.5, px: 2, height: 36, borderTop: `1px solid ${BORDER}`, bgcolor: "#faf8f5",
        fontSize: 11, color: FAINT }}>
        <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}><Kbd>↑</Kbd><Kbd>↓</Kbd>{tx("move")}</Box>
        <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}><Kbd>Enter</Kbd>{tx("open")}</Box>
        <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}><Kbd>Tab</Kbd>{tx("kind")}</Box>
        <Box sx={{ flex: 1 }} />
        {res && hits.length > 0 && <Box>{shown.flat.length} {tx("of")} {hits.length}</Box>}
      </Box>
    </Dialog>
  );
}
