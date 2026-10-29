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
import TuneIcon from "@mui/icons-material/Tune";
import PersonOutlineIcon from "@mui/icons-material/PersonOutline";
import api from "./api";
import { OPEN_SEARCH, openAppLink } from "./appLinks.js";
import { prefetchTask } from "./taskDetail.js";
import { ago } from "./timeWords.js";
import { aloneAs, arrange, asks, channelsFor, countWords, filters, kindOf, marks, messageLink, meta, nothingMatches, nothingYet, personHits, terms, totalOf } from "./searchHits.js";
import { ASSISTANT, BORDER, DIM, FAINT, INK, PANEL, PANEL2, PALETTE, PILL_COLORS, ACCENT, mono } from "./theme.jsx";

// colour identifies, it never shouts: each pill is a pale tint with its own ink, from the five colours - never the
// oxblood, which means "this is on you" and nothing else
const TONES = { slate: [PALETTE.slate, "#e6ebef"], sage: [PALETTE.sage, "#e5ece2"], brass: [PALETTE.brass, "#ede7da"],
  oat: [PALETTE.oat, "#ece8e1"], advisor: [ASSISTANT.ink, "#e8eee4"], pick: [PILL_COLORS.pick.fg, PILL_COLORS.pick.bg] };
const ICONS = { task: TaskAltIcon, email: MailOutlineIcon, chat: ChatBubbleOutlineIcon, pr: CallMergeIcon, issue: AdjustIcon,
  advisor: PsychologyOutlinedIcon, report: BarChartIcon, source: PowerOutlinedIcon, setting: TuneIcon, connector: PowerOutlinedIcon,
  person: PersonOutlineIcon };
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
export { OPEN_SEARCH };
export const openSearch = () => window.dispatchEvent(new Event(OPEN_SEARCH));
// a hit was picked: the page around the search (TaskHubPage) brings Chat up, which is where a pick is drawn
export const SEARCH_PICKED = "tq-search-picked";
export const searchPicked = () => window.dispatchEvent(new Event(SEARCH_PICKED));
// ...and AT A PHONE'S WIDTH THE SAME BUTTON, as its icon (the 2026-10-19 UI walk, G13): the bar was display:none there, so a
// phone had no search at all
export function SearchBar({ onOpen }) {
  return (
    <Box component="button" type="button" onClick={onOpen} data-tq-search-open="true" aria-label="Search everything (Ctrl+K)"
      sx={{ display: "flex", alignItems: "center", justifyContent: { xs: "center", sm: "flex-start" }, gap: 0.9,
        width: { xs: 32, sm: "100%" }, height: 32, px: { xs: 0, sm: 1.1 }, cursor: "text",
        border: `1px solid ${BORDER}`, borderRadius: "9px", bgcolor: PANEL, fontFamily: "inherit", textAlign: "left",
        transition: "border-color .15s, box-shadow .15s",
        "&:hover": { borderColor: "#cfc7bb", boxShadow: "0 1px 3px rgba(30,50,38,.06)" } }}>
      <SearchIcon sx={{ fontSize: 16, color: FAINT }} />
      <Box component="span" sx={{ flex: 1, fontSize: 12.5, color: FAINT, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
        display: { xs: "none", sm: "block" } }}>Search tasks, mail, chats, PRs…</Box>
      <Box component="span" sx={{ display: { xs: "none", sm: "inline-flex" } }}><Kbd>Ctrl K</Kbd></Box>
    </Box>
  );
}

// MESSAGE THEM (the owner's idea, trust audit F6, 2026-10-28): a person found is someone to write to - on the channels New's own Send something
// can reach them on (searchHits.channelsFor), and the pick opens that compose already addressed, the way the New button's does
const CHANNEL_WORDS = { email: "Email", teams: "Teams", whatsapp: "WhatsApp", telegram: "Telegram", imessage: "iMessage", discord: "Discord", slack: "Slack" };
function MessageThem({ person, onGo, sx }) {
  const [ways, setWays] = useState(null);
  const ask = () => api.get("/api/send-targets").then(({ data }) => setWays(channelsFor(person, data?.data))).catch(() => setWays([]));
  const btn = { fontFamily: "inherit", fontSize: 11.5, fontWeight: 600, color: ACCENT, bgcolor: "transparent", border: `1px solid ${BORDER}`,
    borderRadius: "6px", px: 0.8, py: "2px", cursor: "pointer", "&:hover": { borderColor: "#cbd4dc", bgcolor: "#e6ebef" } };
  return (
    <Box data-tq-message-them={person.to} onMouseDown={(e) => e.preventDefault()} onClick={(e) => e.stopPropagation()}
      sx={{ display: "flex", alignItems: "center", gap: 0.6, flexWrap: "wrap", flexShrink: 0, ...sx }}>
      {ways === null ? <Box component="button" type="button" data-tq-message-open="" onClick={ask} sx={btn}>Message them</Box>
        : !ways.length ? <Box component="span" sx={{ fontSize: 11.5, color: FAINT }}>Nothing here can reach them yet</Box>
        : <>{ways.length > 1 && <Box component="span" sx={{ fontSize: 11.5, color: FAINT }}>on</Box>}
          {ways.map((w) => <Box key={w.channel} component="button" type="button" data-tq-message-channel={w.channel} onClick={() => onGo(w)} sx={btn}>
            {ways.length > 1 ? CHANNEL_WORDS[w.channel] || w.channel : `Message them on ${CHANNEL_WORDS[w.channel] || w.channel}`}</Box>)}</>}
    </Box>
  );
}

function Row({ hit, words, on, onPick, onTask, onHover, onMessage }) {
  const closed = ["done", "dropped"].includes(hit.status), m = meta(hit);
  const ref = useRef(null);
  useEffect(() => { if (on) ref.current?.scrollIntoView({ block: "nearest" }); }, [on]);
  return (
    <Box ref={ref} role="option" aria-selected={on} data-tq-search-hit={hit.id} onClick={() => onPick(hit)} onMouseMove={onHover}
      onMouseDown={(e) => e.preventDefault()}
      sx={{ position: "relative", display: "flex", gap: 1.25, alignItems: "flex-start", px: 1.5, py: 1, mx: 0.75, borderRadius: "9px",
        cursor: "pointer", bgcolor: on ? "#f0ebe3" : "transparent", transition: "background-color .08s" }}>
      {/* one column of pills, so every title starts at the same x: "Connection" outgrew 62px and its title stood 24px right of the rest */}
      {/* ...on a desk; a phone keeps the titles' room */}
      <Pill hit={hit} sx={{ mt: "1px", minWidth: 62, width: { xs: "auto", sm: 88 }, justifyContent: "center" }} />
      <Box sx={{ flex: 1, minWidth: 0 }}>
        <Box sx={{ display: "flex", alignItems: "baseline", gap: 0.75, minWidth: 0 }}>
          <Box sx={{ fontSize: 13, fontWeight: 600, color: closed ? DIM : INK, lineHeight: 1.35, minWidth: 0,
            overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}><Marked text={hit.title} words={words} /></Box>
          {hit.more > 0 && <Box component="span" sx={{ fontSize: 10.5, color: FAINT, flexShrink: 0 }}>+{hit.more} in thread</Box>}
        </Box>
        {/* the sender and the place are marked too, and a match nothing on the row shows is said (search.py `why`) */}
        {(m.length > 0 || hit.when || hit.why) && (
          <Box sx={{ fontSize: 11.5, color: FAINT, mt: 0.15, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
            <Marked text={[...m, hit.when ? ago(hit.when) : "", hit.why || ""].filter(Boolean).join(" · ")} words={words} /></Box>
        )}
        {hit.snippet && (
          <Box sx={{ fontSize: 11.5, color: DIM, mt: 0.35, lineHeight: 1.45, display: "-webkit-box", WebkitLineClamp: 2,
            WebkitBoxOrient: "vertical", overflow: "hidden" }}><Marked text={hit.snippet} words={words} /></Box>
        )}
      </Box>
      {hit.type === "person" && onMessage && <MessageThem person={hit} onGo={(w) => onMessage(w)} />}
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

// FOCUS GOES TO WHAT WAS OPENED (the 2026-10-19 UI walk): the dialog gave it back to the search bar, a screen away from the task.
// ...AND STAYS THERE WHILE IT LANDS (verify, 2026-10-20): a task already on the table was focused on the first frame, its card drew
// again and focus fell to the page; a setting or a connection was never focused at all. `find` is asked each frame - a box redrawn is
// a new element, a knob stands up after its group - and focus is put back on it until it has held still for HOLD; the owner's own
// key, click or scroll lets go at once (appLinks.focusPlace holds the scroll the same way). Its own terminal keeps the keys.
const ITEM = "[data-tq-canvas-item]", HOLD = 1500, OWNER = ["keydown", "pointerdown", "wheel", "touchstart"];
const focusOpened = (find) => {
  if (typeof window === "undefined" || !window.requestAnimationFrame) return;
  const t0 = Date.now();
  let on = true, last = null, since = 0;
  const stop = () => { on = false; OWNER.forEach((e) => window.removeEventListener(e, stop, true)); };
  OWNER.forEach((e) => window.addEventListener(e, stop, true));
  const tick = () => {
    if (!on) return;
    const el = find(), now = Date.now();
    if (el !== last) { last = el; since = now; }
    if (el && !el.contains(document.activeElement)) {
      // a knob's row takes focus without joining the Tab order, as the canvas's boxes do (CanvasItem tabIndex -1)
      if (!el.hasAttribute("tabindex")) { el.setAttribute("tabindex", "-1"); el.style.outline = "none"; }
      el.focus({ preventScroll: true });
    }
    if (now - t0 < 5000 && (!el || now - since < HOLD)) window.requestAnimationFrame(tick); else stop();
  };
  window.requestAnimationFrame(tick);
};
// what each kind of pick opened: the box holding the task; for a mail no task holds, the box that was not on the table before; for
// a setting or a connection, the place its link names (focusPlace's [data-tq-held] - a knob) else the open card it landed on
const fresh = (sel, before) => [...document.querySelectorAll(sel)].find((e) => !before.has(e));
const opened = (h) => {
  const before = new Set(document.querySelectorAll(`${ITEM}, [data-tq-held]`));
  if (h.href) return () => fresh("[data-tq-held]", before) || document.querySelector("[data-tq-browse-one]");
  if (h.tid) return () => document.querySelector(`${ITEM} [data-tq-task-page="${Number(h.tid)}"]`)?.closest(ITEM);
  return () => fresh(ITEM, before);
};

export default function SearchEverything({ open, onClose, onOpenTask, onOpenMessage, onPickSource, query = "" }) {
  const [q, setQ] = useState(""), [res, setRes] = useState(null), [busy, setBusy] = useState(false);
  const [only, setOnly] = useState(""), [at, setAt] = useState(0);
  // ENTER OPENS WHAT WAS TYPED (the 2026-10-19 UI walk, G9): Enter straight after typing opened the LAST query's top hit - the rows
  // on screen were still the old words' - or, before any answer, did nothing. The rows count only when they answer the words in
  // the box (`settled`); an Enter before that is held for these words and spent on their answer's first row
  const typed = useRef(""), held = useRef("");
  const settled = !!res && res.q === q.trim() && !busy;
  useEffect(() => { if (!open) { setQ(""); setRes(null); setOnly(""); setAt(0); typed.current = held.current = ""; } }, [open]);
  // ...and opened by the chat's link with words (appLinks #search=): they stand in the box, searched as if typed
  useEffect(() => { if (open && query) { typed.current = query; setQ(query); } }, [open, query]);
  useEffect(() => {
    const t = q.trim();
    if (!asks(t)) { setRes(null); setBusy(false); held.current = ""; return undefined; }
    let alive = true; setBusy(true);
    // ...and the people the To/Cc pickers would offer for the same words, read beside it: a directory that does not answer leaves the rest
    const people = () => (t.length < 2 ? Promise.resolve([]) : api.get("/api/people/search", { params: { q: t } }).then(({ data }) => personHits(data?.data)).catch(() => []));
    const h = setTimeout(() => Promise.all([api.get("/api/search", { params: { q: t } }), people()])
      .then(([{ data }, ps]) => { if (alive) { setRes({ ...data, hits: [...(data?.hits || []), ...ps], q: t }); setAt(0); } })
      .catch(() => { if (alive) setRes({ q: t, hits: [], failed: true }); })
      .finally(() => { if (alive) setBusy(false); }), 180);
    return () => { alive = false; clearTimeout(h); };
  }, [q]);
  const hits = res?.hits || [];
  const strip = useMemo(() => filters(hits, res), [hits, res]);
  const shown = useMemo(() => arrange(hits, only), [hits, only]);
  const words = useMemo(() => terms(res?.q || ""), [res]);
  useEffect(() => { if (only && !strip.some((f) => f.key === only)) setOnly(""); }, [strip, only]);
  // the highlighted hit's task is read while it is highlighted, so Enter opens it whole - not an empty frame first (taskDetail.js, G8)
  const aheadTid = settled ? shown.flat[at]?.tid || 0 : 0;
  useEffect(() => { if (aheadTid) prefetchTask(api, aheadTid); }, [aheadTid]);

  // ...Message them: the search goes, and New's Send something opens on the canvas, addressed (CanvasBrowse -> NewSheet)
  const message = (w) => { onClose(); searchPicked(); openAppLink(messageLink(w)); };
  const pick = (h) => {
    if (!h) return;
    // ...a person stays in the box: their address becomes the words, and what they sent and the tasks they are on come up
    if (h.type === "person") { typed.current = h.to; setQ(h.to); setOnly(""); setAt(0); return; }
    const find = h.type === "source" ? null : opened(h);
    onClose();
    // a setting or a connection: the page that holds it, by its link - the road every in-app link takes, which brings it to view
    if (h.href) { searchPicked(); openAppLink(h.href); }
    else if (h.type === "task") onOpenTask?.(h.tid, h);
    else if (h.type === "source") onPickSource?.(h.pick);
    else if (!onOpenMessage?.(h.mid, h) && h.tid) onOpenTask?.(h.tid, h);
    if (find) focusOpened(find);
  };
  // the held Enter, spent when its words' answer lands - on nothing, when they found nothing (the empty line says so)
  useEffect(() => {
    if (!held.current || !settled || held.current !== res.q) return;
    held.current = ""; pick(shown.flat[0]);
  });
  const key = (e) => {
    const n = shown.flat.length;
    if (e.key === "ArrowDown") { e.preventDefault(); setAt((i) => (n ? (i + 1) % n : 0)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setAt((i) => (n ? (i - 1 + n) % n : 0)); }
    else if (e.key === "Enter") {
      e.preventDefault();
      const t = typed.current.trim();
      if (settled && res.q === t) pick(shown.flat[at]);
      else if (asks(t)) held.current = t;
    }
    else if (e.key === "Tab" && strip.length > 1) {
      e.preventDefault();
      const i = strip.findIndex((f) => f.key === only), next = strip[(i + (e.shiftKey ? -1 : 1) + strip.length) % strip.length];
      setOnly(next.key); setAt(0);
    }
  };
  // "8 of 23" where the list is cut, and the way to see the rest: more words
  const all = totalOf(res, only), groupCount = (g) => { const t = totalOf(res, g.group); return t.n > g.hits.length || t.more ? `${g.hits.length} of ${countWords(t)}` : g.hits.length; };
  const footer = all.n > shown.flat.length || all.more ? `${shown.flat.length} of ${countWords(all)} · add a word to narrow` : `${shown.flat.length} of ${all.n}`;
  let i = -1;
  return (
    // no disableRestoreFocus (verify, 2026-10-20): Esc left focus on the page, and words typed next went nowhere - a cancel gives it
    // back to where it was (the chat's composer); a pick moves it on from there, to what it opened (focusOpened)
    <Dialog open={open} onClose={onClose} data-tq-search="true"
      slotProps={{ backdrop: { sx: { bgcolor: "rgba(38,37,33,.28)", backdropFilter: "blur(2px)" } } }}
      sx={{ "& .MuiDialog-container": { alignItems: "flex-start" } }}
      PaperProps={{ sx: { mt: "9vh", width: 680, maxWidth: "calc(100vw - 32px)", borderRadius: "14px", bgcolor: PANEL,
        border: `1px solid #dad4cb`, boxShadow: "0 24px 64px rgba(30,50,38,.22)", overflow: "hidden", m: 2 } }}>
      <Box sx={{ display: "flex", alignItems: "center", gap: 1.25, px: 2, height: 56, borderBottom: `1px solid ${BORDER}` }}>
        <SearchIcon sx={{ fontSize: 21, color: q ? INK : FAINT }} />
        <InputBase autoFocus fullWidth value={q} onKeyDown={key}
          onChange={(e) => { typed.current = e.target.value; if (held.current !== e.target.value.trim()) held.current = ""; setQ(e.target.value); }}
          placeholder="Search tasks, mail, chats, pull requests, the Advisor…" inputProps={{ "aria-label": "Search everything", "data-tq-search-input": "true" }}
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
      {/* rows that answer earlier words are drawn faint until the answer for these lands: they are not what Enter opens */}
      <Box role="listbox" data-tq-search-settled={settled ? "true" : "false"}
        sx={{ maxHeight: "min(60vh, 560px)", overflowY: "auto", py: 0.75, opacity: res && !settled ? 0.5 : 1, transition: "opacity .12s" }}>
        {!res && (
          <Box sx={{ px: 2.5, py: 3, textAlign: "center" }}>
            <Box sx={{ display: "flex", justifyContent: "center", gap: 0.6, flexWrap: "wrap", mb: 1.25 }}>
              {["task", "email", "chat", "pr", "advisor", "report", "source"].map((t) => <Pill key={t} hit={{ type: t }} />)}
            </Box>
            <Box sx={{ fontSize: 12.5, color: DIM }}>Every task, mail, chat line, pull request, Advisor post and source - open or closed.</Box>
          </Box>
        )}
        {res && !hits.length && !busy && (
          <Box sx={{ px: 2.5, py: 3, textAlign: "center", fontSize: 12.5, color: DIM }}>
            {res.failed ? "Search didn't answer - try again in a moment." : nothingMatches(res.q)}</Box>
        )}
        {shown.groups.map((g) => (
          <Box key={g.group} sx={{ mb: 0.5 }}>
            <Box sx={{ px: 2.25, pt: 1, pb: 0.4, fontSize: 11.5, fontWeight: 600, color: FAINT, display: "flex", gap: 0.6 }}>
              {g.group}<Box component="span" sx={{ fontWeight: 500 }}>{groupCount(g)}</Box></Box>
            {g.hits.map((h) => { i += 1; const n = i; return (
              <Row key={h.id} hit={h} words={words} on={n === at} onPick={pick} onHover={() => n !== at && setAt(n)} onMessage={aloneAs(res) ? null : message}
                onTask={(tid) => { const find = opened({ tid }); onClose(); onOpenTask?.(tid); focusOpened(find); }} />); })}
          </Box>
        ))}
        {settled && aloneAs(res) && <Box data-tq-search-alone="" sx={{ px: 2.5, py: 1.25, fontSize: 12.5, color: DIM }}>{nothingYet(aloneAs(res))}
          <MessageThem person={hits[0]} onGo={message} sx={{ mt: 0.9 }} /></Box>}
      </Box>
      <Box sx={{ display: "flex", alignItems: "center", gap: 1.5, px: 2, height: 36, borderTop: `1px solid ${BORDER}`, bgcolor: "#faf8f5",
        fontSize: 11, color: FAINT }}>
        <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}><Kbd>↑</Kbd><Kbd>↓</Kbd>move</Box>
        <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}><Kbd>Enter</Kbd>open</Box>
        <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}><Kbd>Tab</Kbd>kind</Box>
        <Box sx={{ flex: 1 }} />
        {res && hits.length > 0 && <Box data-tq-search-count="">{footer}</Box>}
      </Box>
    </Dialog>
  );
}
