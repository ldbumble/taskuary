// The Assistant page: Taskuary walks you through your inbox. The PIPE on the left is what has not
// been looked at yet, ranked (funnel.py): new things fall in from the top and slide to their slot,
// the pile sits at the mouth at the bottom, and the bottom item is what comes out next. Showing an
// item in the chat is reading it, so it leaves the pipe - "All" shows the rest of the recent
// Timeline for anything you want pulled back in. The CHAT on the right is one long conversation
// with Taskuary (concierge.py): one item per turn, said in a breath, with the card that acts on it
// underneath; a name or a subject typed into it pulls that thing in. A meeting in ten minutes or an
// agent that just asked interrupts as a "by the way" line above the composer, whatever the chat is
// on. Past chats slide over; New chat starts a fresh conversation. Everything durable lives on the
// server; this file only draws and pushes buttons.
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Box, CircularProgress, IconButton, MenuItem, Popover, Select, Tooltip, Typography } from "@mui/material";
import HistoryIcon from "@mui/icons-material/History";
import EditNoteIcon from "@mui/icons-material/EditNote";
import TuneIcon from "@mui/icons-material/Tune";
import VolumeUpIcon from "@mui/icons-material/VolumeUp";
import VolumeOffIcon from "@mui/icons-material/VolumeOff";
import SendIcon from "@mui/icons-material/ArrowUpward";
import SentimentSatisfiedAltIcon from "@mui/icons-material/SentimentSatisfiedAlt";
import CloseIcon from "@mui/icons-material/Close";
import ViewSidebarIcon from "@mui/icons-material/ViewSidebar";
import api from "./api.js";
import { readNdjson, toolTarget } from "./assistantStream.js";
import { pollWhileActive } from "./visible.js";
import { syncFace, syncStatusDelay } from "./syncTiming.js";
import { Md, looksMd } from "./md.jsx";
import { MicButton, TaskuaryMark, ChannelIcon, fmtDateTime, fmtTime12 } from "./ui.jsx";
import { DIM, FAINT, INK, ROLES } from "./theme.jsx";
import { ageText, arrivals, cardFor, drawOrder, keysOf, rowMeta, statusLine, topAlert } from "./funnelPile.js";
import { AgentCard, AgentDoneCard, BriefCard, FyisCard, IdeaCard, MeetingCard, MessageCard, ReplyCard, ReportCard, SetupCard, SourceMark, TaskCard, WrapupCard } from "./assistantCards.jsx";
import { timelineDayLabel } from "./timelineDay.js";
import "./assistantView.css";

// what a PERSON sent, whatever lane it landed in (funnel.came_in): a slipped follow-up about a mail
// is still mail, and the walk that skipped it said "0 of them are mail" with five in the pipe
const incoming = (items) => (items || []).filter((i) => i.mid && !["report", "own", "assistant"].includes(i.channel || "email"));
const waitingLine = (items) => {
  const n = (items || []).length, came = incoming(items).length;
  const by = [["slipped", "forgotten"], ["landed", "report"], ["fyi", "fyi"]]
    .map(([w, lane]) => [w, (items || []).filter((i) => i.lane === lane).length]).filter(([, k]) => k);
  return `${n} waiting${came ? ` - ${came} came in` : ""}${by.length ? `, ${by.map(([w, k]) => `${k} ${w}`).join(", ")}` : ""}.`
    + " I'll take you through them one at a time.";
};

const ROW_H = 34, CUR_H = 62;   // one thin line, like a Timeline row (30px + a 4px gap); the current one opens up to two
const EMOJI_REPLIES = [
  ["👍", "Sounds good"], ["❤️", "Love it"], ["😂", "Funny"], ["🎉", "Celebrate"],
  ["👏", "Well done"], ["🙏", "Thank you"], ["✅", "Confirmed"], ["👀", "Looking"],
  ["🤔", "Thinking"], ["😕", "Unsure"], ["👎", "No thanks"], ["🔥", "Excellent"],
];
const errText = (e) => e?.response?.data?.detail || e?.message || "Taskuary could not answer.";
const speakOn = () => { try { return localStorage.getItem("taskuary_speak") === "1"; } catch { return false; } };
const speak = (text) => {
  if (!text || typeof window === "undefined" || !window.speechSynthesis) return;
  try { window.speechSynthesis.cancel(); const u = new SpeechSynthesisUtterance(text.replace(/[*_#`>]/g, "")); u.rate = 1.05; window.speechSynthesis.speak(u); } catch { /* no voice on this box */ }
};
// the pile's key for a Timeline row, so "All" can pull any row into the chat
const keyForRow = (r) => r.ReviewStatus === "pending" && r.ReviewId ? `review:${r.ReviewId}`
  : r.AgentWaiting && r.TaskId ? `agent:${r.TaskId}` : r.Channel === "report" ? `report:${r.MessageId}` : `msg:${r.MessageId}`;

// ── the pipe ─────────────────────────────────────────────────────────────────────────────────
function Pipe({ pile, current, onPull, mode, setMode, open, onClose }) {
  const items = pile?.items || [];
  // the Timeline's own sync clock, here too, off the same status endpoint and the same formatter:
  // when the mail was last read, when the next background poll is due, and a button to read it now.
  // lastPollAt is the SERVER's epoch, so the time comes from (now - lastPollAt) against OUR clock.
  const [sync, setSync] = useState(null);
  const [lastSync, setLastSync] = useState(null);
  const [nextAt, setNextAt] = useState(null);
  const [syncing, setSyncing] = useState(false);
  const [tick, setTick] = useState(0);
  useEffect(() => { const id = setInterval(() => setTick((t) => t + 1), 1000); return () => clearInterval(id); }, []);
  useEffect(() => {
    let alive = true, timer = null;
    const ask = async () => {
      if (!alive) return;
      let running = false, due = null;
      try {
        const { data } = await api.get("/api/ingest/status");
        if (!alive) return;
        setSync(data); running = data.status?.state === "running";
        const pollAt = Number(data.lastPollAt) || null;
        setLastSync(pollAt ? new Date(Date.now() - (data.now - pollAt) * 1000) : null);
        due = data.nextPollAt ? Date.now() + (data.nextPollAt - data.now) * 1000 : null;
        setNextAt(due);
      } catch { /* the chip just stops counting */ }
      timer = setTimeout(ask, syncStatusDelay({ running, nextAt: due }));
    };
    ask();
    return () => { alive = false; clearTimeout(timer); };
  }, []);
  const syncNow = async () => { setSyncing(true); try { await api.post("/api/ingest/poll"); } catch { /* surfaces in Connections */ } setTimeout(() => setSyncing(false), 4000); };
  const busy = syncing || sync?.status?.state === "running";
  const nextIn = nextAt ? Math.max(0, Math.round((nextAt - Date.now()) / 1000)) : null;
  const face = { busy, what: sync?.status?.what || "", every: sync?.everyMinutes ?? 10, lastAt: lastSync, nextIn };
  void tick;                                     // the countdown redraws on the tick, not on a fetch
  // the one on the table sits at the mouth as CURRENT - it slides down there from wherever it was
  // in the pile (same key, same element), and a task named in the chat lands there from nowhere
  const drawn = [...drawOrder(items).filter((i) => i.key !== current?.key), ...(current ? [{ ...current, current: true }] : [])];
  const prev = useRef(null);
  const prevItems = useRef(null);
  const bodyRef = useRef(null);
  const [landing, setLanding] = useState(new Set());
  useEffect(() => {
    const fresh = arrivals(prev.current, items);
    prev.current = keysOf(items); prevItems.current = items;
    if (!fresh.size) return undefined;
    setLanding(fresh);
    const t = setTimeout(() => setLanding(new Set()), 40);       // one frame above the pipe, then it falls to its slot
    return () => clearTimeout(t);
  }, [pile?.rev]);                                                 // eslint-disable-line react-hooks/exhaustive-deps
  // gravity: the mouth is what you look at, so a pile taller than the column is scrolled to its bottom
  // ...and the view opens ON the mouth: what comes out next is the one thing to look at. Twice, because
  // the rows are still sliding into place on the first frame and the scroll height grows under us.
  useEffect(() => {
    if (mode !== "pile") return undefined;
    const down = () => { const el = bodyRef.current; if (el) el.scrollTop = el.scrollHeight; };
    const id = requestAnimationFrame(down); const t = setTimeout(down, 600);
    return () => { cancelAnimationFrame(id); clearTimeout(t); };
  }, [pile?.rev, mode, items.length, current?.key]);
  const [recent, setRecent] = useState(null);
  useEffect(() => {
    if (mode !== "all") return undefined;
    let live = true;
    api.get("/api/feed", { params: { limit: 80 } }).then(({ data }) => live && setRecent(data.data || [])).catch(() => live && setRecent([]));
    return () => { live = false; };
  }, [mode]);
  // The NEXT pill has to be what the Next button will actually bring up. The server skips what an
  // agent has in hand and what this walk already showed (funnel.next_item); the pill did not, so a
  // coder parked on a question wore NEXT while two fyi about lunch came out instead (2026-09-03).
  const upNext = (i) => !i.settling && i.lane !== "working" && i.key !== current?.key;
  const nextKey = (items.find((i) => upNext(i) && !i.surfaced) || items.find(upNext))?.key;
  // ...and how close it is to empty, once that is worth saying (the owner asked for it at "halfway
  // down the funnel", so from fifteen: the count is the encouragement, no exclamation needed)
  const left = items.filter((i) => !i.settling && i.lane !== "working").length;
  const cheer = mode !== "pile" || !left || left > 15 ? ""
    : left === 1 ? "One more and the pipe is clear."
      : left <= 5 ? `${left} to go, then the pipe is clear.`
        : `${left} away from a clear pipe.`;
  const n = drawn.length;
  const bottom = drawn[n - 1];
  const day = bottom ? timelineDayLabel(String(bottom.kind === "meeting" ? bottom.when : (bottom.since || bottom.when)).slice(0, 10)) : "";
  // the funnel's shape: a row's edges sit ON the wall behind it, so the pile reads as the funnel
  // emptying (the owner, 2026-09-03: "the outside edges of the timeline items shoud match the width
  // to the edge of the funnel... that's the whole idea so it looks like it's emptying"). The walls
  // are a clip-path from full width at the top to 12% in at the mouth, so the inset at any height is
  // measured, not guessed - and it needs the body's own box, which only the DOM knows.
  const stackRef = useRef(null);
  const wallRef = useRef(null);
  const [box, setBox] = useState({ w: 0, h: 0, top: 0 });
  // The WALL's own box, not the viewport's: an absolutely positioned child of a scrolling column
  // spans the whole scrollable content, so measuring the visible height put the rows nearest the
  // mouth on the wrong part of the taper as soon as the pile was long enough to scroll (the owner,
  // 2026-09-03: "This is out of line"). offsetTop/offsetHeight share one origin - the padding box.
  const measure = useCallback(() => {
    const w = wallRef.current, st = stackRef.current;
    if (!w) return;
    const next = { w: w.offsetWidth, h: w.offsetHeight, top: st ? st.offsetTop : 0 };
    setBox((b) => (b.w === next.w && b.h === next.h && b.top === next.top ? b : next));   // same box, no re-render
  }, []);
  useEffect(() => {
    measure();
    if (typeof ResizeObserver === "undefined") return undefined;
    const ro = new ResizeObserver(measure);
    if (wallRef.current) ro.observe(wallRef.current);
    if (bodyRef.current) ro.observe(bodyRef.current);
    return () => ro.disconnect();
  });                                                    // every render: the stack's top moves as the pile grows
  const WALL = 0.07, PAD = 10;                           // .tq-pipe-walls' clip-path taper, and .tq-pipe-body's padding
  const inset = (top, h) => {
    if (!box.w || !box.h) return 0;
    const y = box.top + top + h / 2;                     // the row's middle, in the wall's own space
    return Math.max(0, Math.round(2 + WALL * box.w * Math.min(1, Math.max(0, y / box.h)) - PAD));
  };
  return (
    <div className={`tq-asst-col tq-asst-pipe${open ? " open" : ""}`}>
      <div className="tq-pipe-head">
        <b>The pipe</b><span className="n" title="not looked at yet">{items.length}</span>
        <button type="button" className="tq-pipe-sync" onClick={syncNow} disabled={busy}
          title={busy ? (sync?.status?.what || "reading the mailboxes now") : `${syncFace(face)} — click to read the mailboxes now`}>
          {syncFace({ ...face, terse: true })}</button>
        <div className="tq-pipe-toggle">
          <button type="button" className={mode === "pile" ? "on" : ""} onClick={() => setMode("pile")} title="What you have not looked at yet">Unread</button>
          <button type="button" className={mode === "all" ? "on" : ""} onClick={() => setMode("all")} title="Everything recent on the Timeline — pull any of it back into the chat">All</button>
        </div>
        {open && <IconButton size="small" onClick={onClose} sx={{ ml: 0.5 }}><CloseIcon sx={{ fontSize: 16 }} /></IconButton>}
      </div>
      {mode === "all" ? (
        <div className="tq-pipe-body tq-pipe-recent">
          {recent === null && <Box sx={{ display: "grid", placeItems: "center", py: 3 }}><CircularProgress size={18} /></Box>}
          {recent?.map((r) => (
            <div key={r.MessageId} className="r" onClick={() => onPull(keyForRow(r), `Tell me about “${r.Subject || r.Title || "this"}”`)} title={r.RouteReason || ""}>
              <ChannelIcon channel={r.Channel} sx={{ fontSize: 13 }} />
              <div><b>{r.Subject || r.Title || "(no subject)"}</b><span>{r.FromName || r.FromEmail || r.SourceName} · {r.Category}</span></div>
              <span style={{ fontFamily: "'IBM Plex Mono', Consolas, monospace", fontSize: 10, color: "#8a847a" }}>{ageText(r.SentAt)}</span>
            </div>
          ))}
        </div>
      ) : !drawn.length ? (
        <div className="tq-pipe-empty"><div>
          <Typography sx={{ fontSize: 30, lineHeight: 1 }}>✓</Typography>
          <b>All done</b>
          <span>Nothing is waiting on you. New things fall in here as they land, and Taskuary will speak up.</span>
        </div></div>
      ) : (
        <div className="tq-pipe-body" ref={bodyRef}>
          <div className="tq-pipe-walls" ref={wallRef} />
          {!!pile?.hidden && <div className="tq-pipe-more">+{pile.hidden} more wait behind these</div>}
          {/* nothing disappears silently: what the owner's own standing rules held back is said here */}
          {!!pile?.muted && (
            <div className="tq-pipe-more" title={`Your standing rules:\n${(pile.rules || []).join("\n")}\n\nThey are still on the Timeline.`}>
              {pile.muted} filed by your rules
            </div>
          )}
          {!!cheer && <div className="tq-pipe-cheer">{cheer}</div>}
          <div className="tq-pipe-stack" ref={stackRef} style={{ height: drawn.reduce((h, i) => h + (i.current ? CUR_H : ROW_H), 0) + 6 }}>
            {drawn.map((i, idx) => {
              const top = drawn.slice(0, idx).reduce((h, r) => h + (r.current ? CUR_H : ROW_H), 0);
              const meta = rowMeta(i);
              const role = meta.role ? ROLES[meta.role].solid : "#d3ccc1";
              const cls = ["tq-pipe-row", landing.has(i.key) ? "landing" : "", i.settling ? "settling" : "", i.surfaced && !i.current ? "shown" : "", i.current ? "current" : i.key === nextKey ? "next" : ""].filter(Boolean).join(" ");
              const who = i.who && !i.title.toLowerCase().startsWith(i.who.toLowerCase()) ? i.who : "";
              const tag = i.settling ? "triaging…" : i.kind === "agent" && i.asking ? "asked you" : meta.word;
              const loud = i.lane === "blocked" || i.lane === "time";
              const promoted = loud || i.lane === "approve";
              const side = inset(top, i.current ? CUR_H : ROW_H);
              return (
                <div key={i.key} className={cls} style={{ top: landing.has(i.key) ? -ROW_H : top, left: side, right: side, borderLeftColor: role }}
                  onClick={() => !i.settling && !i.current && onPull(i.key, `Show me “${i.title}”`)}
                  title={`${meta.word}${promoted ? " · triage moved it up" : ""}${i.surfaced && !i.current ? " · shown already, still waiting on you" : ""} — ${i.why || ""}`}>
                  <span className="when"><i style={{ background: role }} />{fmtTime12(i.kind === "meeting" ? i.when : (i.since || i.when))}</span>
                  <span className="logo"><SourceMark item={i} size={13} /></span>
                  <div className="t">
                    {i.current ? <span className="tq-pipe-next cur">current</span> : i.key === nextKey ? <span className="tq-pipe-next">next</span> : null}
                    {promoted && !i.current && <span className="up" title="triage moved it up">↑</span>}
                    {/* the task's number comes BEFORE the words: last in the row, it was the first thing
                        the funnel's narrowing clipped off (the owner, 2026-09-03: "tq is still off") */}
                    {!!i.ref && !i.current && <span className="tq-pipe-ref" title="the task this belongs to">{i.ref}</span>}
                    {!!i.more && <span className="tq-pipe-ref" title={`${i.more} more on this thread - the newest speaks for it`}>+{i.more}</span>}
                    {who && <span className="who">{who}</span>}<b>{i.title}</b>
                  </div>
                  {/* the lane's word is the row's own last COLUMN: as a flex item at the end of the
                      words it was what overflowed when the row narrowed - "reply pending" hanging
                      over the right border (the owner, 2026-09-03) */}
                  <span className="tq-pipe-tag" style={{ color: meta.role ? ROLES[meta.role].ink : "#6f6960", background: meta.role ? ROLES[meta.role].tint : "#eee9e1", borderColor: meta.role ? ROLES[meta.role].bd : "#ddd6cb" }}>
                    {loud ? `${meta.mark} ` : ""}{tag}</span>
                  {i.current && <div className="sub">{[i.why, i.kind === "meeting" ? ageText(i.when) : `${ageText(i.since || i.when)} ago`].filter(Boolean).join(" · ")}</div>}
                </div>
              );
            })}
          </div>
        </div>
      )}
      {mode === "pile" && !!drawn.length && (
        <div className="tq-pipe-foot">
          {day && <div className="tq-pipe-day">{day}</div>}
          <div className="tq-pipe-mouth">{current ? "on the table" : ""}</div>
        </div>
      )}
    </div>
  );
}

// ── one line of the conversation, with its card ───────────────────────────────────────────
function Line({ m, live, actions, fresh }) {
  if (m.role === "user") return <div className="tq-msg you"><div className="body">{m.text}</div></div>;
  if (m.role === "receipt") return (
    <div className="tq-msg receipt"><span /><div className="body">✓ {m.text}
      {!!m.tid && <button type="button" className="tq-chip" style={{ marginLeft: 8 }} onClick={() => actions.openTask?.(m.tid)}>Open {m.ref || "the task"}</button>}
    </div></div>);
  const kind = m.card?.kind === "setup" ? "setup" : cardFor(m.card);
  const c = live && fresh && m.card && fresh.key === m.card.key ? { ...m.card, ...fresh } : m.card;   // the live card follows the pile
  const card = live && m.card && kind ? {
    reply: <ReplyCard card={c} onDone={actions.done} onOpenTask={actions.openTask} onTimeline={actions.timeline} />,
    agent: <AgentCard card={c} onDone={actions.done} onOpenTask={actions.openTask} />,
    meeting: <MeetingCard card={c} onDone={actions.done} onOpenTask={actions.openTask} />,
    report: <ReportCard card={c} onOpenTask={actions.openTask} onTimeline={actions.timeline} onDone={actions.done} />,
    agentdone: <AgentDoneCard card={c} onOpenTask={actions.openTask} onDone={actions.done} onSurface={actions.surface} />,
    idea: <IdeaCard card={c} onAct={actions.done} onOpenTask={actions.openTask} onTimeline={actions.timeline} />,
    message: <MessageCard card={c} onDone={actions.done} onOpenTask={actions.openTask} onTimeline={actions.timeline} onSurface={actions.surface} />,
    setup: <SetupCard card={m.card} onNavigate={actions.navigate} onHandOff={actions.handOff} />,
    brief: <BriefCard card={m.card} onStart={actions.start} />,
    task: <TaskCard card={c} onDone={actions.done} onOpenTask={actions.openTask} />,
    fyis: <FyisCard card={c} onDone={actions.done} onSurface={(k) => actions.surface(k)} onTimeline={actions.timeline} />,
    wrapup: <WrapupCard card={c} onDone={actions.done} onOpenTask={actions.openTask} />,
  }[kind] : null;
  return (
    <>
      <div className="tq-msg">
        <div className="avatar"><TaskuaryMark size={18} /></div>
        <div className="body">
          {m.text ? (looksMd(m.text) ? <Md text={m.text} /> : m.text.split("\n").map((p, i) => <p key={i}>{p}</p>)) : null}
          {!live && m.card && kind && kind !== "setup" && kind !== "brief" && (
            <div className="tq-card-note" style={{ display: "flex", alignItems: "center", gap: 5 }}>
              <SourceMark item={m.card} size={12} /> {m.card.title}
              {m.card.tid && <a href={`#task=${m.card.tid}`} style={{ color: "#55697a", marginLeft: 4 }}>{m.card.ref}</a>}
            </div>
          )}
          {card}
        </div>
      </div>
      {live && !!m.options?.length && (
        <div className="tq-options">{m.options.map((o) => <button key={o} type="button" className="tq-chip" onClick={() => actions.pick(o)}>{o}</button>)}</div>
      )}
    </>
  );
}

// ── the page ─────────────────────────────────────────────────────────────────────────────────
export default function AssistantView({ onOpenTask, onNavigate, active = true }) {
  const [state, setState] = useState(null);           // /api/concierge: the dock task, its turns, the AI choices
  const [msgs, setMsgs] = useState([]);
  const [pile, setPile] = useState(null);
  const [busy, setBusy] = useState(false);
  const [work, setWork] = useState([]);              // the turn's tool calls and progress, as they stream
  const [err, setErr] = useState("");
  const [current, setCurrent] = useState(null);       // the key on the table
  const [currentItem, setCurrentItem] = useState(null);   // ...and the item itself, drawn at the mouth of the pipe
  const [text, setText] = useState("");
  const [acked, setAcked] = useState(() => new Set());
  const [chatsOpen, setChatsOpen] = useState(false);
  const [chats, setChats] = useState([]);
  const [old, setOld] = useState(null);               // an earlier chat, read-only
  const [aiEl, setAiEl] = useState(null);
  const [emojiEl, setEmojiEl] = useState(null);
  const [speakOnState, setSpeak] = useState(speakOn);
  const [pipeMode, setPipeMode] = useState("pile");
  const [pipeOpen, setPipeOpen] = useState(false);
  const [navH, setNavH] = useState(49);
  const bodyRef = useRef(null);

  useEffect(() => {
    const el = document.getElementById("tqTopNav");
    if (!el || typeof ResizeObserver === "undefined") return undefined;
    const ro = new ResizeObserver(() => setNavH(el.offsetHeight)); ro.observe(el); setNavH(el.offsetHeight);
    return () => ro.disconnect();
  }, []);

  // one turn of the assistant, streamed: tool calls show under the dots as they happen, `done` is the answer
  const turn = useCallback(async (body) => {
    setWork([]);
    const token = localStorage.getItem("taskuary_token");
    const res = await fetch("/api/concierge/stream", { method: "POST", headers: { "Content-Type": "application/json", ...(token ? { "X-Taskuary-Token": token } : {}) }, body: JSON.stringify(body) });
    if (!res.ok || !res.body) {                       // the static demo, or an older server: the plain door
      const path = body.mode === "open" ? "/api/concierge/open" : body.mode === "next" ? "/api/concierge/next" : "/api/concierge/say";
      return (await api.post(path, body.mode === "next" ? { key: body.key, only: body.only } : body.mode === "say" ? { text: body.text, key: body.key } : {})).data;
    }
    for await (const ev of readNdjson(res.body)) {
      if (ev.type === "done") { setWork([]); return ev; }
      if (ev.type === "error") throw new Error(ev.error || "The assistant could not answer.");
      // only real work shows under the dots - a command, a read, a call - never the CLI's own housekeeping
      if (ev.type === "tool_call" && !/^(ToolSearch|TodoWrite|TaskCreate|TaskUpdate|TaskList|Skill)$/.test(ev.name || ""))
        setWork((w) => [...w, `${ev.name || "tool"} ${toolTarget(ev.detail?.args).slice(0, 90)}`].slice(-6));
    }
    throw new Error("The assistant stopped without an answer.");
  }, []);

  const loadState = useCallback(async () => {
    const { data } = await api.get("/api/concierge");
    setState(data); setMsgs(data.messages || []);
    // A closed task may have an older `agentdone` card in the transcript. It remains readable
    // history, but it is not live work and must not be restored as CURRENT in the funnel.
    const last = [...(data.messages || [])].reverse().find((m) => m.card && !["brief", "setup", "agentdone"].includes(m.card.kind));
    setCurrent(last?.card?.key || null); setCurrentItem(last?.card || null);
    return data;
  }, []);
  const currentRef = useRef(null); const surfaceRef = useRef(null); const speakRef = useRef(null);
  const loadPile = useCallback(async () => {
    try {
      // the key we are holding rides along, so the server can say whether it is still a thing
      const { data } = await api.get("/api/funnel/pile", { params: currentRef.current?.key ? { current: currentRef.current.key } : {} });
      setPile((p) => p?.rev === data.rev ? p : data);
      if (data.events?.length) {
        // the watcher recorded its lines on the conversation: pick them up, and if one is about the item on
        // the table, the table clears and the walk moves on
        const { data: st } = await api.get("/api/concierge");
        const fresh = [];
        setMsgs((m) => { const have = new Set(m.map((x) => x.id)); fresh.push(...(st.messages || []).filter((x) => !have.has(x.id))); return [...m, ...fresh]; });
        // ...and a line the WATCHER wrote puts its card on the table, exactly as surfacing one does.
        // It did not, so the page still thought nothing was current and drew the "By the way" bar for
        // the very card sitting in the chat (the owner, 2026-09-03: "Don't show bottom prompt if it's
        // already in main chat").
        const put = [...fresh].reverse().find((x) => x.card && !["brief", "setup", "agentdone"].includes(x.card.kind));
        if (put) { setCurrent(put.card.key); setCurrentItem(put.card); }
        const hit = data.events.find((e) => currentRef.current && e.tid === currentRef.current.tid && e.kind !== "parked" && e.kind !== "asking");
        if (hit) { setCurrent(null); setCurrentItem(null); setTimeout(() => surfaceRef.current?.(), 900); }
        for (const e of data.events) if (e.kind === "done" || e.kind === "asking") speakRef.current?.(e.text);
      }
      // the item on the table is live: an agent that stops and starts again changes what its row and card say
      // ...and when the server says the key is GONE - the reply was sent, the task closed, it was swept -
      // the table clears itself instead of showing a draft that is no longer waiting on anybody.
      if (currentRef.current?.key && "current" in data && data.current === null) {
        setCurrent(null); setCurrentItem(null);
      } else setCurrentItem((cur) => {
        if (!cur) return cur;
        const fresh = data.current?.key === cur.key ? data.current : (data.items || []).find((i) => i.key === cur.key);
        return fresh && (fresh.lane !== cur.lane || fresh.why !== cur.why || fresh.asking !== cur.asking) ? { ...cur, ...fresh } : cur;
      });
    } catch { /* next tick */ }
  }, []);
  useEffect(() => { currentRef.current = currentItem; }, [currentItem]);
  useEffect(() => { loadState().catch((e) => setErr(errText(e))); }, [loadState]);
  useEffect(() => pollWhileActive(active, loadPile, 5000), [active, loadPile]);
  useEffect(() => { const el = bodyRef.current; if (el) el.scrollTop = el.scrollHeight; }, [msgs, busy]);
  // ...and again whenever the thread GROWS - a card that loaded its draft, a report that unfolded - so the
  // bottom of the conversation is always what you see, unless you have scrolled up to read
  useEffect(() => {
    const el = bodyRef.current, inner = el?.firstElementChild;
    if (!el || !inner || typeof ResizeObserver === "undefined") return undefined;
    const ro = new ResizeObserver(() => { if (el.scrollHeight - el.scrollTop - el.clientHeight < 240) el.scrollTop = el.scrollHeight; });
    ro.observe(inner);
    return () => ro.disconnect();
  }, []);

  const items = pile?.items || [];
  const ready = items.filter((i) => !i.settling);
  // an alert about something already IN the conversation is noise: the card is right there
  const shownKeys = useMemo(() => new Set(msgs.slice(-8).map((m) => m.card?.key).filter(Boolean)), [msgs]);
  const alert = useMemo(() => topAlert(pile?.alerts, acked, currentItem, shownKeys), [pile, acked, currentItem, shownKeys]);
  const say = useCallback((line) => { if (speakOnState) speak(line); }, [speakOnState]);
  useEffect(() => { speakRef.current = say; }, [say]);
  const only = useRef(null);                                       // "mail" once the owner chose to start with the mail
  const landed = useCallback((data) => {
    if (data.exhausted) only.current = null;            // the mail ran out: Next continues with the rest of the pipe
    const card = data.item ? { ...data.item } : null;
    setMsgs((m) => [...m, { id: `a${Date.now()}`, role: "assistant", text: data.say, options: data.options || [], card }]);
    if (card) { setCurrent(card.key); setCurrentItem(card); } else { setCurrent(null); setCurrentItem(null); }
    say(data.say); loadPile();
  }, [loadPile, say]);

  // pull the next thing (or the one named; or the next piece of mail) out of the pipe and say it
  const surface = useCallback(async (key = null, asUser = null) => {
    if (busy) return;
    setBusy(true); setErr("");
    if (asUser) setMsgs((m) => [...m, { id: `u${Date.now()}`, role: "user", text: asUser }]);
    try { landed(await turn({ mode: "next", key, only: key ? null : only.current })); }
    catch (e) { setErr(errText(e)); }
    setBusy(false);
  }, [busy, landed, turn]);
  useEffect(() => { surfaceRef.current = surface; }, [surface]);
  const start = (what) => { only.current = what; surface(null, what === "mail" ? "Just what came in." : "Walk me through my tasks."); };

  // The day used to write itself the moment the page opened - a model call nobody asked for, which
  // also landed UNDER a "Set something up" the owner had already pressed (2026-09-03: "I hit new chat
  // to set something up and it ran the email walk through welcome command?"). The welcome block is the
  // door now: what is waiting, in facts, and the walk starts on a button.

  const send = async (line) => {
    const t = String(line ?? text).trim();
    if (!t || busy) return;
    setText(""); setBusy(true); setErr("");
    setMsgs((m) => [...m, { id: `u${Date.now()}`, role: "user", text: t }]);
    try {
      const data = await turn({ mode: "say", text: t, key: current });
      if (data.item) landed(data);                       // the words pointed at something: it is on the table now
      else {
        setMsgs((m) => [...m, { id: `a${Date.now()}`, role: "assistant", text: data.say, options: data.options || [] }]); say(data.say);
        if (data.decision) await decide(data.decision);  // the words were a decision: carry it out, then move on
      }
    } catch (e) { setErr(errText(e)); }
    setBusy(false);
  };
  const sendEmoji = (emoji) => {
    setEmojiEl(null);
    // Do not destroy a sentence the owner was already writing. With an empty composer this is
    // the promised one-click response; with a draft it behaves like an ordinary emoji keyboard.
    if (text.trim()) setText((v) => `${v}${/\s$/.test(v) ? "" : " "}${emoji}`);
    else send(emoji);
  };
  // the owner decided in words: the same doors the card's buttons open, then the next thing. Never stuck.
  const decide = async (d) => {
    // The card is looked up by the key on the table, and it can be MISSING - a key that changed under
    // a pile refresh, a card older than the thread we hold. Every branch below is guarded on it, so a
    // missing card used to mean nothing happened at all while the server had already said "Closing the
    // task. Moving on." (the owner, 2026-09-03: "I told the ai to close it but it did not"). The live
    // item is the same shape and is the fallback; when neither has what the verb needs, say so.
    // ...and when the owner's SENTENCE named another subject, the server resolves it and sends the
    // item it meant along as `target`. That one is acted on; the card on the table is not touched
    // and does not settle (2026-09-03: "not ours" about the outage deleted the finished coding task).
    const cur = d.target || [...msgs].reverse().find((m) => m.card && m.card.key === current)?.card || currentItem || null;
    const elsewhere = !!d.target;
    const mid = cur?.mid, verb = d.verb;
    const needs = { reply: mid, approve: cur?.rid, redraft: cur?.rid, not_ours: mid, not_ours_remember: mid, not_ours_sender: mid,
                    coder: mid, mine: mid, forward: mid, archive: mid, answer_agent: cur?.tid, rerun: cur?.source_id, close: cur?.tid };
    if (verb in needs && !needs[verb]) {
      setMsgs((m) => [...m, { id: `r${Date.now()}`, role: "receipt",
                              text: `I could not do that from here - ${cur ? `${cur.ref || "this one"} has nothing to ${verb} on it` : "nothing is on the table"}. Open it and the buttons will.`,
                              tid: cur?.tid, ref: cur?.ref }]);
      return;
    }
    // moving on happens ONLY on the item that is on the table, and only when the verb settled it
    const after = async (receipt) => {
      if (receipt) setMsgs((m) => [...m, { id: `r${Date.now()}`, role: "receipt", text: receipt, tid: cur?.tid, ref: cur?.ref }]);
      if (elsewhere) { loadPile(); return; }
      await done(null);
    };
    try {
      if (verb === "reply" && mid) {
        const { data } = await api.post(`/api/messages/${mid}/reply`, { draft: true, instruction: d.text || null });
        if (data.reviewId && !elsewhere) { await api.post("/api/funnel/settle", { key: current, verb: "done" }); setCurrent(null); setTimeout(() => surface(`review:${data.reviewId}`), 300); return; }
        if (data.reviewId) { loadPile(); return; }
      } else if (verb === "redraft" && cur?.rid && mid) {
        // the draft itself is rewritten and the SAME review comes back up - the model used to claim
        // the edit and the next approve sent the untouched original (2026-09-03)
        const { data } = await api.post(`/api/messages/${mid}/reply`, { draft: true, redraft: true, instruction: d.text || null });
        setMsgs((m) => [...m, { id: `r${Date.now()}`, role: "receipt", text: data.draft ? "Rewritten - read it below before you send it." : "I could not rewrite it here; edit the draft on the card and send that." }]);
        if (!elsewhere) { setCurrent(null); setTimeout(() => surface(`review:${cur.rid}`), 300); } else loadPile();
        return;
      } else if (verb === "approve" && cur?.rid) {
        const { data } = await api.post(`/api/reviews/${cur.rid}/decide`, { verb: "approve", final_text: null, note: null });
        // a refusal is not an error banner: nothing was sent, the review is untouched, and the
        // card stays where it is (an empty draft, or a verdict that already landed)
        if (data.empty || data.already) {
          setMsgs((m) => [...m, { id: `r${Date.now()}`, role: "receipt", tid: cur.tid, ref: cur.ref,
                                  text: data.empty ? "Nothing was sent - there is no draft on this one yet. Say reply and what to tell them, and it lands here for your yes."
                                                   : `Nothing was sent - ${cur.ref || "this one"} was already ${data.status}. It is off the queue.` }]);
          loadPile(); return;
        }
        if (data.send_error) throw new Error(data.send_error);
        setMsgs((m) => [...m, { id: `r${Date.now()}`, role: "receipt", text: `Sent${cur.who ? ` to ${cur.who}` : ""}.${cur.tid ? ` ${cur.ref} closed.` : ""}` }]);
      } else if (verb === "answer_agent" && cur?.tid) {
        await api.post(`/api/tasks/${cur.tid}/waitroom`, { text: d.text || "yes" });
        await after(`Told ${cur.agent || "the agent"}: “${String(d.text || "yes").slice(0, 80)}”`);
        return;
      } else if (verb === "archive" && mid) {
        const { data } = await api.post(`/api/messages/${mid}/file`, { learn: false, archive: true });
        await after(`Archived${data.ref ? ` - ${data.ref} is closed, not deleted` : " - off the pipe, nothing deleted"}.`);
        return;
      } else if (verb === "remembered" || verb === "forwarded" || verb === "setting" || verb === "split") {
        // Taskuary already did these itself and said so; the card the server recorded is in the
        // thread. Nothing to settle - a memory is not a verdict about the thing on the table.
        loadPile(); return;
      } else if (verb === "remember" && d.text) { await api.post("/api/memory", { note: d.text, scope: "global" }); loadPile(); return; }
      else if (verb === "followup" && current) { await api.post("/api/concierge/act", { key: current, verb: "followup" }); await after("Follow-up drafted - it waits for your yes."); return; }
      else if (verb === "not_ours_sender" && mid) await api.post(`/api/messages/${mid}/not-mine`, { scope: "sender" });
      else if (verb === "not_ours" && mid) {
        const { data } = await api.post(`/api/messages/${mid}/file`, { learn: false });
        if (data.taskArchived) setMsgs((m) => [...m, { id: `r${Date.now()}`, role: "receipt", tid: cur?.tid, ref: data.ref, text: `Filed. ${data.ref} was kept and closed, not deleted - an agent had worked it.` }]);
      }
      else if (verb === "not_ours_remember" && mid) await api.post(`/api/messages/${mid}/not-mine`, { scope: "subject" });
      else if (verb === "coder" && mid) {
        const { data } = await api.post(`/api/messages/${mid}/dispatch`, { instruction: d.text || null });
        setMsgs((m) => [...m, { id: `r${Date.now()}`, role: "receipt", text: `${data.ref || "It"} is with the coding agent${d.text ? " with your note" : ""} - I'll bring it back when it's done.` }]);
      }
      else if (verb === "mine" && mid) await api.post(`/api/messages/${mid}/mine`, { kind: "task" });
      else if (verb === "rerun" && cur?.source_id) {
        const { data } = await api.post(`/api/reports/${cur.source_id}/rerun`);
        setMsgs((m) => [...m, { id: `r${Date.now()}`, role: "receipt", text: `${data.title || "The report"} is rerunning in the background - it lands back in the pipe when it's done.` }]);
      } else if (verb === "close" && cur?.tid) {
        await api.patch(`/api/tasks/${cur.tid}`, { Status: "done" });
        setMsgs((m) => [...m, { id: `r${Date.now()}`, role: "receipt", text: `${cur.ref || "The task"} closed.` }]);
      }
      else if (verb === "stop_agent" && d.taskId) {       // ending the AGENT, which is not closing the task
        if (d.wrap) await api.post(`/api/tasks/${d.taskId}/wrap`, { close: true });
        else await api.post(`/api/tasks/${d.taskId}/agent/stop`);
        setMsgs((m) => [...m, { id: `r${Date.now()}`, role: "receipt", tid: d.taskId, ref: d.ref,
                                text: d.wrap ? `${d.ref} wrapped up - the report is on it and the task is closed.`
                                             : `The agent on ${d.ref} is stopped. The task is still open.` }]);
        loadPile(); return;
      }
      else if (verb === "walkthrough" && d.taskId) {      // a set-up is a conversation, not a build
        setMsgs((m) => [...m, { id: `r${Date.now()}`, role: "receipt", tid: d.taskId, ref: d.ref,
                                text: `${d.ref} is open as a walk-through - nothing was built. Its browser opens beside the assistant.` }]);
        loadPile(); onOpenTask?.(d.taskId); return;
      }
      else if (verb === "created") {                      // the words WERE the brief: the task exists already
        setMsgs((m) => [...m, { id: `r${Date.now()}`, role: "receipt", tid: d.taskId, ref: d.ref,
                                text: `${d.ref} is with the coding agent - it comes back here when it is done.` }]);
        loadPile(); return;
      }
      else if (verb === "clear") {
        const c = d.cleared || {};
        // a standing RULE already keeps these out of the pipe; a sender-wide verdict on top of it would
        // reach everything that person ever sends, which is not what "don't need these" means
        if (c.remember && c.mid && !c.rules?.length) { try { await api.post(`/api/messages/${c.mid}/not-mine`, { scope: "sender" }); } catch { /* the sweep still happened */ } }
        loadPile(); return;
      }
      else if (verb === "setup" && d.text) {
        const { data } = await api.post("/api/concierge/setup", { text: d.text });
        setMsgs((m) => [...m, { id: `r${Date.now()}`, role: "receipt", tid: data.taskId, ref: data.ref,
                                text: `${data.ref} — "${data.title}" is open as a step-by-step walkthrough. Its browser opens beside the assistant.` }]);
        if (data.taskId) onOpenTask?.(data.taskId);
        if (!current) return;
      }
      else if (["later", "skip", "next", "done", "closed", "ack"].includes(verb)) { /* settled below */ }
      else if (!(verb in needs)) {
        // NOTHING falls through to done(null) any more: an unknown verb used to mark the item on
        // the table done for good while the chat said something else entirely (2026-09-03)
        setMsgs((m) => [...m, { id: `r${Date.now()}`, role: "receipt", tid: cur?.tid, ref: cur?.ref,
                                text: `I don't have a road for that here${cur?.ref ? ` - ${cur.ref} is untouched` : ""}. Open it and its own buttons will.` }]);
        return;
      }
      if (verb === "done" && cur && cur.kind !== "agent") {
        // done on a task-backed item means the TASK is done: its pending draft is dismissed and it closes
        if (cur.rid) { try { await api.post(`/api/reviews/${cur.rid}/decide`, { verb: "no_reply", final_text: null, note: "handled - the owner said so" }); } catch { /* it may be decided already */ } }
        if (cur.tid) { try { await api.patch(`/api/tasks/${cur.tid}`, { Status: "done" }); setMsgs((m) => [...m, { id: `r${Date.now()}`, role: "receipt", text: `${cur.ref} closed.` }]); } catch { /* fine */ } }
      }
      if (["later", "skip"].includes(verb)) { await settle(verb); return; }
      await after(null);
    } catch (e) { setErr(errText(e)); }
  };
  // a card did its thing: say so in the thread, then move on
  const done = async (receipt) => {
    if (receipt) setMsgs((m) => [...m, { id: `r${Date.now()}`, role: "receipt", text: receipt }]);
    if (current) { try { await api.post("/api/funnel/settle", { key: current, verb: "done" }); } catch { /* it may already be gone */ } }
    setCurrent(null); setCurrentItem(null);
    setTimeout(() => surface(), 500);
  };
  const settle = async (verb) => {
    if (!current) { surface(); return; }
    try { await api.post("/api/funnel/settle", { key: current, verb }); } catch { /* fine */ }
    setMsgs((m) => [...m, { id: `r${Date.now()}`, role: "receipt", text: verb === "done" ? "Done." : verb === "later" ? "Pushed back a few hours — it comes back into the pipe then." : "Skipped until tomorrow morning." }]);
    setCurrent(null); setCurrentItem(null); loadPile();
    setTimeout(() => surface(), 400);
  };
  const setup = () => setMsgs((m) => [...m, { id: `a${Date.now()}`, role: "assistant", text: "Tell me what to set up - a report, a connection, an automation - in a sentence. I open it as a walk-through with the assistant: it takes you through it here, nothing is built and no repository is touched. If something does have to be built, say send it to the coding agent.",
    card: { key: "setup", kind: "setup", lane: "report", title: "Set something up" }, options: [] }]);
  const handOff = async (text) => {
    if (!text.trim() || busy) return;
    setBusy(true); setErr("");
    setMsgs((m) => [...m, { id: `u${Date.now()}`, role: "user", text }]);
    try {
      const { data } = await api.post("/api/concierge/setup", { text });
      setMsgs((m) => [...m, { id: `r${Date.now()}`, role: "receipt", tid: data.taskId, ref: data.ref,
                              text: `${data.ref} — "${data.title}" is open as a step-by-step walkthrough. Its browser opens beside the assistant.` }]);
      if (data.taskId) onOpenTask?.(data.taskId);
    } catch (e) { setErr(errText(e)); }
    setBusy(false);
  };
  const ack = async (a, go) => {
    setAcked((s) => new Set([...s, a.key]));
    api.post("/api/funnel/settle", { key: a.key, verb: "ack" }).catch(() => {});
    if (go) surface(a.item, `Show me — ${a.text}`);
  };
  const openChats = async () => { setChatsOpen(true); try { setChats((await api.get("/api/concierge/chats")).data.data || []); } catch { /* list stays */ } };
  const newChat = async () => {
    if (busy) return;
    setBusy(true); setErr("");
    try { await api.post("/api/assistant/dock/new"); setOld(null); setChatsOpen(false); setCurrent(null); setCurrentItem(null); await loadState(); await loadPile(); }
    catch (e) { setErr(errText(e)); }
    setBusy(false);
  };
  const openOld = async (c) => {
    if (c.open) { setOld(null); setChatsOpen(false); return; }
    try { const { data } = await api.get(`/api/concierge/chats/${c.taskId}`); setOld({ ...c, messages: data.messages || [] }); setChatsOpen(false); }
    catch (e) { setErr(errText(e)); }
  };
  const pickAi = async (pick) => {
    const p = (state?.providers || []).find((x) => x.pick === pick);
    try { const { data } = await api.post("/api/concierge/ai", { pick, model: null }); setState((s) => ({ ...s, pick: data.pick, provider: p?.label || data.pick, model: data.model || p?.model || "" })); }
    catch (e) { setErr(errText(e)); }
    setAiEl(null);
  };
  const toggleSpeak = () => { const v = !speakOnState; setSpeak(v); try { localStorage.setItem("taskuary_speak", v ? "1" : "0"); } catch { /* private mode */ } if (!v) window.speechSynthesis?.cancel(); };
  const timeline = (mid) => { window.location.hash = `msg=${mid}`; onNavigate?.("Timeline"); };

  const actions = { done, start, handOff, openTask: onOpenTask, timeline, navigate: onNavigate, pick: (o) => send(o),
    surface: (key, note) => { if (note) setMsgs((m) => [...m, { id: `r${Date.now()}`, role: "receipt", text: note }]); setTimeout(() => key ? surface(key) : loadPile(), 900); } };
  const shown = old ? old.messages : msgs;
  const lastCardIdx = useMemo(() => { for (let i = shown.length - 1; i >= 0; i -= 1) if (shown[i].card) return i; return -1; }, [shown]);
  const height = `calc(100vh - ${navH}px - 38px)`;   // the page padding above and below: the chat fits the screen, nothing scrolls but the thread

  return (
    <Box className="tq-asst" sx={{ height }}>
      <Pipe pile={pile} current={old ? null : currentItem} mode={pipeMode} setMode={setPipeMode} open={pipeOpen} onClose={() => setPipeOpen(false)}
        onPull={(key, asUser) => { setPipeOpen(false); if (old) setOld(null); surface(key, asUser || null); }} />
      <div className="tq-asst-col" style={{ position: "relative" }}>
        <div className="tq-chat-head">
          <Box sx={{ width: 30, height: 30, borderRadius: 2, background: "linear-gradient(90deg, #55697a, #7d9a7c)", display: "grid", placeItems: "center" }}><TaskuaryMark size={22} /></Box>
          <div className="who"><b>Taskuary</b><span>{old ? `An earlier chat · ${fmtDateTime(old.at)}` : statusLine(items, busy)}</span></div>
          <div className="grow" />
          <Tooltip title="The pipe"><IconButton size="small" onClick={() => setPipeOpen((v) => !v)} sx={{ display: { xs: "inline-flex", md: "none" } }}><ViewSidebarIcon sx={{ fontSize: 18, color: DIM }} /></IconButton></Tooltip>
          <Tooltip title={speakOnState ? "Reading replies aloud — click to stop" : "Read replies aloud"}><IconButton size="small" onClick={toggleSpeak}>{speakOnState ? <VolumeUpIcon sx={{ fontSize: 18, color: "#526b53" }} /> : <VolumeOffIcon sx={{ fontSize: 18, color: DIM }} />}</IconButton></Tooltip>
          <Tooltip title={`AI: ${state?.provider || "none"}${state?.model ? ` · ${state.model}` : ""}`}><IconButton size="small" onClick={(e) => setAiEl(e.currentTarget)}><TuneIcon sx={{ fontSize: 18, color: DIM }} /></IconButton></Tooltip>
          <Tooltip title="Past chats"><IconButton size="small" onClick={openChats}><HistoryIcon sx={{ fontSize: 18, color: DIM }} /></IconButton></Tooltip>
          <Tooltip title="New chat — archives this one"><IconButton size="small" onClick={newChat} disabled={busy}><EditNoteIcon sx={{ fontSize: 19, color: DIM }} /></IconButton></Tooltip>
        </div>
        <Popover open={!!aiEl} anchorEl={aiEl} onClose={() => setAiEl(null)} anchorOrigin={{ vertical: "bottom", horizontal: "right" }} transformOrigin={{ vertical: "top", horizontal: "right" }}
          slotProps={{ paper: { sx: { p: 1.5, width: 320 } } }}>
          <Typography sx={{ fontSize: 12, fontWeight: 700, color: INK, mb: 0.5 }}>Which AI speaks here</Typography>
          <Typography variant="caption" sx={{ color: DIM, display: "block", mb: 1, lineHeight: 1.45 }}>Your CLI agent is the default, on its quick gear (haiku, low effort, flash) - it can read, rerun reports and run tools. An API model answers faster but cannot act. The agents doing the actual work are chosen elsewhere.</Typography>
          <Select size="small" fullWidth value={state?.pick || ""} displayEmpty onChange={(e) => pickAi(e.target.value)} sx={{ fontSize: 12 }}>
            {!state?.providers?.length && <MenuItem value="">No AI connected</MenuItem>}
            {(state?.providers || []).map((p) => <MenuItem key={p.pick} value={p.pick} sx={{ fontSize: 12 }}>{p.label}{p.type === "cli" ? " · can act (default)" : " · fast, talk only"}</MenuItem>)}
          </Select>
        </Popover>
        {old && <div className="tq-old-banner"><span>You are reading an earlier chat.</span><button type="button" className="tq-chip" onClick={() => setOld(null)}>Back to today</button></div>}
        {chatsOpen && (
          <div className="tq-chats">
            <div className="tq-chats-head">Chats<span style={{ flex: 1 }} /><IconButton size="small" onClick={() => setChatsOpen(false)}><CloseIcon sx={{ fontSize: 16 }} /></IconButton></div>
            <div className="tq-chats-list">
              {!chats.length && <Typography sx={{ color: FAINT, fontSize: 12, p: 1.5 }}>No earlier chats yet.</Typography>}
              {chats.map((c) => (
                <div key={c.taskId} className="c" onClick={() => openOld(c)} title={c.started ? `started ${c.started.slice(0, 16)}` : ""}>
                  {c.open ? <i /> : <span style={{ width: 7 }} />}<b>{c.title}</b>
                  {/* what the walk actually got through, so one transcript can be told from another */}
                  <span>{[c.mail ? `${c.mail} mail` : "", c.seen ? `${c.seen} looked at` : "", c.minutes ? `${c.minutes} min` : "", ageText(c.at)].filter(Boolean).join(" · ")}</span>
                </div>
              ))}
            </div>
          </div>
        )}
        <div className="tq-chat-body" ref={bodyRef}>
          <div className="tq-chat-inner">
            {!state && !err && <Box sx={{ display: "grid", placeItems: "center", py: 6 }}><CircularProgress size={22} /></Box>}
            {state && !shown.length && !busy && (
              <div className="tq-welcome">
                <TaskuaryMark size={30} />
                <b>{items.length ? "Ready when you are" : "All done"}</b>
                <span>{items.length ? waitingLine(ready) : "Nothing is waiting on you. Ask me anything, or set something up."}</span>
                <div className="tq-modes">
                  <button type="button" className="tq-chip primary" disabled={!ready.length} onClick={() => start(null)}
                    title="Everything in the pipe, oldest first - mail, reports, agents, meetings">Walk me through my tasks</button>
                  <button type="button" className="tq-chip" disabled={!incoming(ready).length} onClick={() => start("mail")}
                    title="Only what people sent you - mail and chat">Just what came in</button>
                  <button type="button" className="tq-chip" onClick={setup}>Set something up</button>
                </div>
              </div>
            )}
            {shown.map((m, i) => <Line key={m.id} m={m} live={!old && i === lastCardIdx} actions={actions} fresh={currentItem} />)}
            {busy && (
              <div className="tq-msg"><div className="avatar"><TaskuaryMark size={18} /></div>
                <div className="body"><span className="tq-typing"><i /><i /><i /></span>
                  {!!work.length && <div className="tq-work">{work.map((w, i) => <div key={i}>{w}</div>)}</div>}
                </div>
              </div>
            )}
            {err && <Typography sx={{ color: "#7a2f3c", fontSize: 12, mb: 1 }}>{err}</Typography>}
          </div>
        </div>
        {alert && !old && (
          <div className="tq-btw" role="status">
            <span className="dot" /><div className="txt"><b>By the way —</b>{alert.text}.{current ? " Finish this one and say next, or switch now." : ""}</div>
            <button type="button" className="tq-chip primary" onClick={() => ack(alert, true)}>{current ? "Switch to it" : "Show me"}</button>
            <button type="button" className="tq-chip" onClick={() => ack(alert, false)}>Later</button>
          </div>
        )}
        {!old && (
          <div className="tq-compose">
            <div className="tq-quick">
              <button type="button" className="tq-chip" disabled={busy || !ready.length} onClick={() => surface()}>Next</button>
              {current && <>
                <button type="button" className="tq-chip" disabled={busy} onClick={() => settle("done")}>Done</button>
                <button type="button" className="tq-chip" disabled={busy} onClick={() => settle("later")}>Later</button>
                <button type="button" className="tq-chip" disabled={busy} onClick={() => settle("skip")}>Tomorrow</button>
              </>}
              <button type="button" className="tq-chip" disabled={busy} onClick={setup}>Set something up</button>
            </div>
            <div className="tq-compose-box">
              <MicButton size={18} onText={(t) => setText((v) => (v ? `${v} ${t}` : t))} />
              <Tooltip title="Send an emoji response">
                <IconButton size="small" aria-label="Choose an emoji response" disabled={busy}
                  onClick={(e) => setEmojiEl(e.currentTarget)} sx={{ p: 0.45, color: DIM }}>
                  <SentimentSatisfiedAltIcon sx={{ fontSize: 18 }} />
                </IconButton>
              </Tooltip>
              <textarea rows={1} value={text} placeholder={current ? "Ask about this one, tell me what to do with it, or name something else…" : "Ask Taskuary anything — a name or a subject pulls it in…"}
                onChange={(e) => setText(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }} />
              <button type="button" className="tq-send" aria-label="Send" disabled={busy || !text.trim()} onClick={() => send()}><SendIcon fontSize="small" /></button>
            </div>
            <Popover open={!!emojiEl} anchorEl={emojiEl} onClose={() => setEmojiEl(null)}
              anchorOrigin={{ vertical: "top", horizontal: "left" }} transformOrigin={{ vertical: "bottom", horizontal: "left" }}
              slotProps={{ paper: { sx: { p: 1.1, borderRadius: 2.5 } } }}>
              <Typography sx={{ fontSize: 11.5, fontWeight: 700, color: INK, px: 0.4, pb: 0.75 }}>Send a quick response</Typography>
              <Box sx={{ display: "grid", gridTemplateColumns: "repeat(6, 36px)", gap: 0.4 }}>
                {EMOJI_REPLIES.map(([emoji, label]) => (
                  <Box key={emoji} component="button" type="button" aria-label={`Send ${label}`} title={label}
                    onClick={() => sendEmoji(emoji)} sx={{ appearance: "none", border: "1px solid transparent", borderRadius: 1.5,
                      bgcolor: "transparent", cursor: "pointer", width: 36, height: 36, p: 0, fontSize: 20, lineHeight: 1,
                      "&:hover": { bgcolor: "#f4f1ec", borderColor: "#e1dcd5", transform: "scale(1.08)" } }}>
                    {emoji}
                  </Box>
                ))}
              </Box>
              {!!text.trim() && <Typography sx={{ fontSize: 10.5, color: FAINT, px: 0.4, pt: 0.75 }}>Added to your draft; press send when ready.</Typography>}
            </Popover>
            <div className="tq-compose-hint">Enter sends · Shift+Enter adds a line · the buttons on a card do the acting</div>
          </div>
        )}
      </div>
    </Box>
  );
}
