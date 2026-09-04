// The Assistant page IS the Timeline now. The RAIL on the left is the Timeline's own rail (FeedView),
// with the PIPE at its top: what has not been looked at yet, ranked (funnel.py), next-out FIRST -
// triage moves the important things to the top, new things fall in and slide to their slot, and the
// whole day's Timeline runs on below it, dated. The STAGE on the right is one long conversation with
// Taskuary (concierge.py): one item per turn, said in a breath, with the card that acts on it
// underneath; clicking a row pulls it in, a name or a subject typed into it pulls that thing in.
// A meeting in ten minutes or an agent that just asked interrupts as a "by the way" line above the
// composer, whatever the chat is on. Two ways to use the stage, one toggle: CHAT (the default -
// rows go to the conversation) or TASK (rows open on the stage the way the Timeline always did:
// hover previews, click pins). Past chats slide over; New chat starts a fresh conversation.
// Everything durable lives on the server; this file only draws and pushes buttons.
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
import { DEMO } from "./demoApi.js";
import { readNdjson, toolTarget } from "./assistantStream.js";
import { pollWhileActive } from "./visible.js";
import { onLive } from "./live.js";
import { Md, looksMd } from "./md.jsx";
import { ChannelIcon, MicButton, TaskuaryMark, fmtDateTime, fmtTime12 } from "./ui.jsx";
import { BORDER, DIM, FAINT, INK, ROLES } from "./theme.jsx";
import { ageText, arrivals, cardFor, currentItemFromPile, drawOrder, followsItem, keysOf, rowMeta, statusLine, topAlert } from "./funnelPile.js";
import { mergeDurableTurns } from "./assistantTurns.js";
import { AgentCard, AgentDoneCard, BriefCard, FyisCard, IdeaCard, MeetingCard, MessageCard, ReplyCard, ReportCard, SetupCard, SourceMark, TaskCard, WrapupCard } from "./assistantCards.jsx";
import FeedView from "./FeedView.jsx";
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

const ROW_H = 33, CUR_H = 57;   // a Timeline row (30px + its 3px gap); the current one opens up to two lines
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
// the pile's key for a Timeline row, so any row on the rail can be pulled into the chat - the same
// key the pipe itself carries, so the server puts the same item on the table either way
export const keyForRow = (r) => r.ReviewStatus === "pending" && r.ReviewId ? `review:${r.ReviewId}`
  : r.AgentWaiting && r.TaskId ? `agent:${r.TaskId}` : r.Channel === "report" ? `report:${r.MessageId}` : `msg:${r.MessageId}`;

// ── the pipe: the top of the rail ────────────────────────────────────────────────────────────
// An assistant that has just woken up says hello like one (the owner, 2026-09-04: "it should be
// good morning/afternoon or whatever it is and should say how can i help").
function greeting() {
  const h = new Date().getHours();
  return h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening";
}

function Pile({ pile, current, onPull }) {
  const items = pile?.items || [];
  // the one on the table sits at the TOP as CURRENT - it slides up there from wherever it was in the
  // pile (same key, same element), and a task named in the chat lands there from nowhere
  const drawn = [...(current ? [{ ...current, current: true }] : []), ...drawOrder(items).filter((i) => i.key !== current?.key)];
  const prev = useRef(null);
  const [landing, setLanding] = useState(new Set());
  useEffect(() => {
    const fresh = arrivals(prev.current, items);
    prev.current = keysOf(items);
    if (!fresh.size) return undefined;
    setLanding(fresh);
    const t = setTimeout(() => setLanding(new Set()), 40);       // one frame above the pipe, then it falls to its slot
    return () => clearTimeout(t);
  }, [pile?.rev]);                                                 // eslint-disable-line react-hooks/exhaustive-deps
  // The NEXT pill has to be what the Next button will actually bring up. The server skips what an
  // agent has in hand and what this walk already showed (funnel.next_item); the pill did not, so a
  // coder parked on a question wore NEXT while two fyi about lunch came out instead (2026-09-03).
  const upNext = (i) => !i.settling && i.lane !== "working" && i.key !== current?.key;
  const nextKey = (items.find((i) => upNext(i) && !i.surfaced) || items.find(upNext))?.key;
  // how close to empty, once that is worth saying (the owner asked for it at "halfway down the
  // funnel", so from fifteen: the count is the encouragement - no header, no total)
  const left = items.filter((i) => !i.settling && i.lane !== "working").length;
  const cheer = !left || left > 15 ? "" : left === 1 ? "One more and the pipe is clear."
    : left <= 5 ? `${left} to go, then the pipe is clear.` : `${left} away from a clear pipe.`;
  return (
    <div className="tq-pile" data-tq-keep>
      {!drawn.length ? (
        <div className="tq-pile-empty"><span className="mark">✓</span><b>All done</b>Nothing is waiting on you. New things land here as they arrive, and Taskuary speaks up.</div>
      ) : (
        <div className="tq-pile-stack" style={{ height: drawn.reduce((h, i) => h + (i.current ? CUR_H : ROW_H), 0) }}>
          {drawn.map((i, idx) => {
            const top = drawn.slice(0, idx).reduce((h, r) => h + (r.current ? CUR_H : ROW_H), 0);
            const meta = rowMeta(i);
            const role = meta.role ? ROLES[meta.role].solid : "#d3ccc1";
            const cls = ["tq-pile-row", landing.has(i.key) ? "landing" : "", i.settling ? "settling" : "", i.current ? "current" : i.key === nextKey ? "next" : ""].filter(Boolean).join(" ");
            const who = i.who && !i.title.toLowerCase().startsWith(i.who.toLowerCase()) ? i.who : "";
            const tag = i.settling ? "triaging…" : i.kind === "agent" && i.asking ? "asked you" : meta.word;
            const loud = i.lane === "blocked" || i.lane === "time";
            const promoted = loud || i.lane === "approve";           // triage moved it up: the little arrow says so
            return (
              <div key={i.key} className={cls} style={{ top: landing.has(i.key) ? -ROW_H : top, "--edge": role }}>
                <span className="when">{fmtTime12(i.kind === "meeting" ? i.when : (i.since || i.when))}</span>
                <span className="rail"><i style={{ background: role }} /></span>
                <div className="card" onClick={() => !i.settling && !i.current && onPull(i.key, `Show me “${i.title}”`)}
                  title={`${meta.word}${promoted ? " · triage moved it up" : ""}${i.surfaced && !i.current ? " · shown already, still waiting on you" : ""} — ${i.why || ""}`}>
                  <div className="t">
                    <span className="logo"><SourceMark item={i} size={15} /></span>
                    {i.current ? <span className="tq-pile-next cur">current</span> : i.key === nextKey ? <span className="tq-pile-next">next</span> : null}
                    {promoted && !i.current && <span className="up" title="triage moved it up">↑</span>}
                    {!!i.ref && <span className="tq-pile-ref" title="the task this belongs to">{i.ref}</span>}
                    {!!i.more && <span className="tq-pile-ref" title={`${i.more} more on this thread - the newest speaks for it`}>+{i.more}</span>}
                    {who && <span className="who">{who}</span>}<b>{i.title}</b>
                    <span className="tq-pile-tag" style={{ color: meta.role ? ROLES[meta.role].ink : "#6f6960", background: meta.role ? ROLES[meta.role].tint : "#eee9e1", borderColor: meta.role ? ROLES[meta.role].bd : "#ddd6cb" }}>
                      {loud ? `${meta.mark} ` : ""}{tag}</span>
                  </div>
                  {i.current && <div className="sub">{[i.why, i.kind === "meeting" ? ageText(i.when) : `${ageText(i.since || i.when)} ago`].filter(Boolean).join(" · ")}</div>}
                </div>
              </div>
            );
          })}
        </div>
      )}
      {!!cheer && <div className="tq-pile-cheer">{cheer}</div>}
      {!!pile?.hidden && <div className="tq-pile-note">+{pile.hidden} more wait behind these</div>}
      {/* nothing disappears silently: what the owner's own standing rules held back is said here */}
      {!!pile?.muted && <div className="tq-pile-note" title={`Your standing rules:\n${(pile.rules || []).join("\n")}\n\nThey are still on the Timeline (all).`}>{pile.muted} filed by your rules</div>}
    </div>
  );
}

// the two ways to use the stage - shown in the chat's header and on the task view's empty stage,
// so whichever one you are in, the other is one click away
const StageMode = ({ mode, setMode }) => (
  <div className="tq-stage-mode" title="What a click on a row does">
    <button type="button" className={mode === "chat" ? "on" : ""} onClick={() => setMode("chat")} title="Rows go to the conversation - Taskuary walks you through them">Chat</button>
    <button type="button" className={mode === "task" ? "on" : ""} onClick={() => setMode("task")} title="Rows open here on their own - the message, the triage, the agent's work, the draft">Task</button>
  </div>
);

// ── one line of the conversation, with its card ───────────────────────────────────────────
function Line({ m, live, actions, fresh }) {
  if (m.role === "user") return <div className="tq-msg you"><div className="body">{m.text}</div></div>;
  if (m.role === "receipt") return (
    <div className="tq-msg receipt"><span /><div className="body">✓ {m.text}
      {!!m.tid && <button type="button" className="tq-chip" style={{ marginLeft: 8 }} onClick={() => actions.openTask?.(m.tid)}>Open {m.ref || "the task"}</button>}
    </div></div>);
  // The funnel deliberately renames msg:<mid> to agent:<tid> when somebody takes the task. Follow
  // the task identity across that rename; matching only the old key left a live coder displayed as
  // "nobody on it" until a new chat line happened to replace the card.
  const follows = live && followsItem(m.card, fresh);
  const c = follows ? { ...m.card, ...fresh } : m.card;   // the live card follows the pile
  const kind = c?.kind === "setup" ? "setup" : cardFor(c);
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
export default function AssistantView({ onOpenTask, onNavigate, onChanged, active = true }) {
  const [state, setState] = useState(null);           // /api/concierge: the dock task, its turns, the AI choices
  const [msgs, setMsgs] = useState([]);
  const [pile, setPile] = useState(null);
  const [busy, setBusy] = useState(false);
  const [resetting, setResetting] = useState(false);  // replacing a chat is housekeeping, never an AI turn
  const [work, setWork] = useState([]);              // the turn's tool calls and progress, as they stream
  const [err, setErr] = useState("");
  const [current, setCurrent] = useState(null);       // the key on the table
  const [currentItem, setCurrentItem] = useState(null);   // ...and the item itself, drawn at the top of the pipe
  const [text, setText] = useState("");
  const [acked, setAcked] = useState(() => new Set());
  const [chatsOpen, setChatsOpen] = useState(false);
  const [chats, setChats] = useState([]);
  const [chatsLoading, setChatsLoading] = useState(false);
  const [old, setOld] = useState(null);               // an earlier chat, read-only
  const [aiEl, setAiEl] = useState(null);
  const [emojiEl, setEmojiEl] = useState(null);
  const [speakOnState, setSpeak] = useState(speakOn);
  const [stageMode, setStageMode] = useState("chat");   // what a click on a row does: chat (default) or task view
  const [railOpen, setRailOpen] = useState(false);      // on a phone: the rail instead of the chat
  const bodyRef = useRef(null);
  // Polls and state loads can already be in flight when New chat is pressed. Epoching the
  // conversation prevents an old response from painting the archived thread back over the blank one.
  const chatEpoch = useRef(0);
  const resettingRef = useRef(false);
  const turnFlight = useRef(false);       // React state updates after the event; this closes same-tick double submits
  // Pile construction is comparatively expensive. Never let a timer tick and a websocket
  // notification queue duplicate requests in this tab; remember one forced refresh instead.
  const pileFlight = useRef(false);
  const pileForcePending = useRef(false);
  const loadPileRef = useRef(null);

  // one turn of the assistant, streamed: tool calls show under the dots as they happen, `done` is the answer
  const turn = useCallback(async (body) => {
    setWork([]);
    const plain = async () => {
      const endpoint = body.mode === "open" ? "/api/concierge/open" : body.mode === "next" ? "/api/concierge/next" : "/api/concierge/say";
      return (await api.post(endpoint, body.mode === "next" ? { key: body.key, only: body.only, include_surfaced: body.include_surfaced, exclude: body.exclude }
        : body.mode === "say" ? { text: body.text, key: body.key, context_mid: body.context_mid } : {})).data;
    };
    // The public demo is intentionally a local script. Do not even attempt the streaming AI
    // endpoint: its invented threads should never look like a model is working behind the page.
    if (DEMO) return plain();
    const token = localStorage.getItem("taskuary_token");
    const res = await fetch("/api/concierge/stream", { method: "POST", headers: { "Content-Type": "application/json", ...(token ? { "X-Taskuary-Token": token } : {}) }, body: JSON.stringify(body) });
    if (!res.ok || !res.body) {                       // the static demo, or an older server: the plain door
      return plain();
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
    const epoch = chatEpoch.current;
    const { data } = await api.get("/api/concierge");
    if (epoch !== chatEpoch.current) return null;
    setState(data); setMsgs(data.messages || []);
    // A closed task may have an older `agentdone` card in the transcript. It remains readable
    // history, but it is not live work and must not be restored as CURRENT in the pipe.
    const last = [...(data.messages || [])].reverse().find((m) => m.card && !["brief", "setup", "agentdone"].includes(m.card.kind));
    setCurrent(last?.card?.key || null); setCurrentItem(last?.card || null);
    return data;
  }, []);
  const currentRef = useRef(null); const surfaceRef = useRef(null); const speakRef = useRef(null);
  // A decision can schedule the next card a few hundred milliseconds later. Those callbacks
  // belong to the conversation that scheduled them: New chat must cancel them, or the archived
  // walk starts advancing inside the new blank conversation without the owner asking anything.
  const deferredChat = useRef(new Set());
  const deferInChat = useCallback((fn, delay) => {
    // Auto-advance is one intention, not a queue. A card callback and a live pile event can both
    // notice the same transition; retaining both timers makes two /next calls and persists the
    // same Assistant answer twice. The newest transition supersedes the older scheduled read.
    for (const pending of deferredChat.current) clearTimeout(pending);
    deferredChat.current.clear();
    const epoch = chatEpoch.current;
    const timer = setTimeout(() => {
      deferredChat.current.delete(timer);
      if (epoch === chatEpoch.current && !resettingRef.current) fn();
    }, delay);
    deferredChat.current.add(timer);
    return timer;
  }, []);
  const cancelDeferredChat = useCallback(() => {
    for (const timer of deferredChat.current) clearTimeout(timer);
    deferredChat.current.clear();
  }, []);
  useEffect(() => cancelDeferredChat, [cancelDeferredChat]);
  const loadPile = useCallback(async (force = false) => {
    if (resettingRef.current) return;
    if (pileFlight.current) {
      if (force) pileForcePending.current = true;
      return;
    }
    pileFlight.current = true;
    const epoch = chatEpoch.current;
    try {
      // the key we are holding rides along, so the server can say whether it is still a thing
      const { data } = await api.get("/api/funnel/pile", { params: {
        ...(currentRef.current?.key ? { current: currentRef.current.key } : {}),
        ...(force ? { force: 1 } : {}),
      } });
      if (epoch !== chatEpoch.current || resettingRef.current) return;
      setPile((p) => p?.rev === data.rev ? p : data);
      // Provider messages can arrive while this conversation is already open. The server writes
      // the resulting correction (for example, "you replied in WhatsApp; draft removed") into the
      // durable conversation, so read new turns on every freshness check -- not only when an agent
      // watcher event happens to accompany them.
      const { data: st } = await api.get("/api/concierge");
      if (epoch !== chatEpoch.current || resettingRef.current) return;
      const fresh = [];
      setMsgs((m) => {
        const merged = mergeDurableTurns(m, st.messages || []);
        fresh.push(...merged.added);
        return merged.messages;
      });
      if (data.events?.length) {
        // the watcher recorded its lines on the conversation: pick them up, and if one is about the item on
        // the table, the table clears and the walk moves on
        // ...and a line the WATCHER wrote puts its card on the table, exactly as surfacing one does.
        // It did not, so the page still thought nothing was current and drew the "By the way" bar for
        // the very card sitting in the chat (the owner, 2026-09-03: "Don't show bottom prompt if it's
        // already in main chat").
        const put = [...fresh].reverse().find((x) => x.card && !["brief", "setup", "agentdone"].includes(x.card.kind));
        if (put) { setCurrent(put.card.key); setCurrentItem(put.card); }
        const hit = data.events.find((e) => currentRef.current && e.tid === currentRef.current.tid && e.kind !== "parked" && e.kind !== "asking");
        if (hit) { setCurrent(null); setCurrentItem(null); deferInChat(() => surfaceRef.current?.(), 900); }
        for (const e of data.events) if (e.kind === "done" || e.kind === "asking") speakRef.current?.(e.text);
      }
      // the item on the table is live: an agent that stops and starts again changes what its row and card say
      // ...and when the server says the key is GONE - the reply was sent, the task closed, it was swept -
      // the table clears itself instead of showing a draft that is no longer waiting on anybody.
      {
        const cur = currentRef.current;
        // Starting from Tasks/Board changes msg:<mid> into agent:<tid>. The old key is correctly
        // absent, but the task is not gone: prefer its working row before clearing the table.
        const fresh = currentItemFromPile(cur, data);
        if (fresh) {
          const newer = fresh.mid && cur.mid && fresh.mid !== cur.mid;
          if (newer) {
            const preview = String(fresh.preview || "").replace(/\s+/g, " ").trim().slice(0, 180);
            const line = `New message from ${fresh.who || "someone"} arrived on ${fresh.ref || fresh.title || "this thread"}`
              + (preview ? `: “${preview}”` : "") + ". I refreshed the context."
              + (fresh.rid ? " The earlier draft is now out of date; redraft it before sending." : "");
            setMsgs((m) => [...m, { id: `context${Date.now()}`, role: "assistant", text: line }]);
            speakRef.current?.(line);
          }
          if (newer || fresh.key !== cur.key || fresh.lane !== cur.lane || fresh.why !== cur.why || fresh.asking !== cur.asking
              || fresh.stale !== cur.stale || fresh.sig !== cur.sig || fresh.sid !== cur.sid || fresh.agent !== cur.agent) {
            const merged = { ...cur, ...fresh };
            currentRef.current = merged;
            setCurrent(merged.key);
            setCurrentItem(merged);
          }
        } else if (cur?.key && "current" in data && data.current === null) {
          setCurrent(null); setCurrentItem(null);
        }
      }
    } catch { /* the live event or safety timer will retry */ }
    finally {
      pileFlight.current = false;
      if (pileForcePending.current && !resettingRef.current) {
        pileForcePending.current = false;
        queueMicrotask(() => loadPileRef.current?.(true));
      }
    }
  }, [deferInChat]);
  useEffect(() => { loadPileRef.current = loadPile; }, [loadPile]);
  useEffect(() => { currentRef.current = currentItem; }, [currentItem]);
  useEffect(() => { loadState().catch((e) => setErr(errText(e))); }, [loadState]);
  // Writes push an event and force one fresh rebuild. The timer is only a disconnected-socket
  // safety net: rebuilding this multi-source pile every five seconds starved Board, Tasks and
  // Past chats behind work whose answer had not changed.
  useEffect(() => pollWhileActive(active, () => loadPile(false), 30000), [active, loadPile]);
  useEffect(() => active ? onLive(["feed-changed", "task-changed"], () => loadPile(true)) : undefined, [active, loadPile]);
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
    if (busy || resetting || turnFlight.current) return;
    turnFlight.current = true;
    setBusy(true); setErr("");
    if (asUser) setMsgs((m) => [...m, { id: `u${Date.now()}`, role: "user", text: asUser }]);
    try { landed(await turn({ mode: "next", key, only: key ? null : only.current,
                              exclude: key ? null : currentRef.current?.key || null })); }
    catch (e) { setErr(errText(e)); }
    turnFlight.current = false;
    setBusy(false);
  }, [busy, landed, resetting, turn]);
  useEffect(() => { surfaceRef.current = surface; }, [surface]);
  const start = (what) => { only.current = what; surface(null, what === "mail" ? "Just what came in." : "Walk me through my tasks."); };

  // The day used to write itself the moment the page opened - a model call nobody asked for, which
  // also landed UNDER a "Set something up" the owner had already pressed (2026-09-03: "I hit new chat
  // to set something up and it ran the email walk through welcome command?"). The welcome block is the
  // door now: what is waiting, in facts, and the walk starts on a button.

  const send = async (line) => {
    const t = String(line ?? text).trim();
    if (!t || busy || resetting || turnFlight.current) return;
    turnFlight.current = true;
    setText(""); setBusy(true); setErr("");
    setMsgs((m) => [...m, { id: `u${Date.now()}`, role: "user", text: t }]);
    try {
      const data = await turn({ mode: "say", text: t, key: current, context_mid: currentItem?.mid || null });
      if (data.context_update) {
        setMsgs((m) => [...m, { id: `context${Date.now()}`, role: "assistant", text: data.context_update }]);
        say(data.context_update);
      }
      if (data.item) landed(data);                       // the words pointed at something: it is on the table now
      else {
        setMsgs((m) => [...m, { id: `a${Date.now()}`, role: "assistant", text: data.say, options: data.options || [] }]); say(data.say);
        if (data.decision) await decide(data.decision);  // the words were a decision: carry it out, then move on
      }
    } catch (e) { setErr(errText(e)); }
    turnFlight.current = false;
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
        if (data.reviewId && !elsewhere) { await api.post("/api/funnel/settle", { key: current, verb: "done" }); setCurrent(null); deferInChat(() => surfaceRef.current?.(`review:${data.reviewId}`), 300); return; }
        if (data.reviewId) { loadPile(); return; }
      } else if (verb === "redraft" && cur?.rid && mid) {
        // the draft itself is rewritten and the SAME review comes back up - the model used to claim
        // the edit and the next approve sent the untouched original (2026-09-03)
        const { data } = await api.post(`/api/messages/${mid}/reply`, { draft: true, redraft: true, instruction: d.text || null });
        setMsgs((m) => [...m, { id: `r${Date.now()}`, role: "receipt", text: data.draft ? "Rewritten - read it below before you send it." : "I could not rewrite it here; edit the draft on the card and send that." }]);
        if (!elsewhere) { setCurrent(null); deferInChat(() => surfaceRef.current?.(`review:${cur.rid}`), 300); } else loadPile();
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
        const { data } = await api.post(`/api/messages/${mid}/dispatch`, { kind: "coding", instruction: d.text || null });
        setMsgs((m) => [...m, { id: `r${Date.now()}`, role: "receipt", text: `${data.ref || "It"} is with the coding agent${d.text ? " with your note" : ""} - I'll bring it back when it's done.` }]);
      }
      else if (verb === "regular_agent" && mid) {
        const { data } = await api.post(`/api/messages/${mid}/dispatch`, { kind: "general", instruction: d.text || null });
        setMsgs((m) => [...m, { id: `r${Date.now()}`, role: "receipt", text: `${data.ref || "It"} is with ${data.agent || "the regular agent"}${d.text ? " with your note" : ""} - I'll bring it back when it's done.` }]);
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
                                text: `${d.ref} is open as a walk-through - nothing was built. Open it when you want to start; its browser opens beside the assistant.` }]);
        loadPile(); return;                              // the owner is mid-conversation: do not yank the tab
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
                                text: `${data.ref} — "${data.title}" is open as a step-by-step walkthrough. Open it when you want to start; its browser opens beside the assistant.` }]);
        if (!current) return;                       // ...and the walk stays where it was: see handOff
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
    onChanged?.();                                     // a draft may have gone out: the Review badge recounts
    deferInChat(() => surfaceRef.current?.(), 500);
  };
  const settle = async (verb) => {
    if (!current) { surface(); return; }
    try { await api.post("/api/funnel/settle", { key: current, verb }); } catch { /* fine */ }
    setMsgs((m) => [...m, { id: `r${Date.now()}`, role: "receipt", text: verb === "done" ? "Done." : verb === "later" ? "Pushed back a few hours — it comes back into the pipe then." : "Skipped until tomorrow morning." }]);
    setCurrent(null); setCurrentItem(null); loadPile();
    deferInChat(() => surfaceRef.current?.(), 400);
  };
  const setup = () => setMsgs((m) => [...m, { id: `a${Date.now()}`, role: "assistant", text: "Tell me what to set up - a report, a connection, an automation - in a sentence. I open it as a walk-through with the assistant: it takes you through it here, nothing is built and no repository is touched. If something does have to be built, say send it to the coding agent.",
    card: { key: "setup", kind: "setup", lane: "report", title: "Set something up" }, options: [] }]);
  const handOff = async (text) => {
    if (!text.trim() || busy) return;
    setBusy(true); setErr("");
    setMsgs((m) => [...m, { id: `u${Date.now()}`, role: "user", text }]);
    try {
      const { data } = await api.post("/api/concierge/setup", { text });
      // ...and we STAY here. Opening the task yanked the owner off the Assistant tab the moment
      // they asked for a walk-through, and sixty seconds later its own session raised a hand at
      // them from the tab they had been thrown onto (the 2026-09-03 break test). The receipt is a
      // link: they go when they want to.
      setMsgs((m) => [...m, { id: `r${Date.now()}`, role: "receipt", tid: data.taskId, ref: data.ref,
                              text: `${data.ref} — "${data.title}" is open as a step-by-step walkthrough. Open it when you want to start; its browser opens beside the assistant.` }]);
    } catch (e) { setErr(errText(e)); }
    setBusy(false);
  };
  const ack = async (a, go) => {
    setAcked((s) => new Set([...s, a.key]));
    api.post("/api/funnel/settle", { key: a.key, verb: "ack" }).catch(() => {});
    if (go) surface(a.item, `Show me — ${a.text}`);
  };
  const openChats = async () => {
    setChatsOpen(true); setChatsLoading(true);
    try { setChats((await api.get("/api/concierge/chats", { timeout: 10000 })).data.data || []); }
    catch (e) { setErr(errText(e)); }
    setChatsLoading(false);
  };
  const newChat = async () => {
    if (busy || resetting || turnFlight.current) return;
    chatEpoch.current += 1;
    resettingRef.current = true;
    cancelDeferredChat();
    pileForcePending.current = false;
    setResetting(true);
    // Clear first. Archiving is not a prompt and must never draw Taskuary's thinking animation.
    // Keep provider and pile metadata on screen while the server swaps the hidden durable chat.
    only.current = null;
    currentRef.current = null;
    setMsgs([]); setText(""); setWork([]); setErr(""); setAcked(new Set());
    setOld(null); setChatsOpen(false); setCurrent(null); setCurrentItem(null);
    setState((s) => s ? { ...s, messages: [] } : s);
    try {
      await api.post("/api/assistant/dock/new", null, { timeout: 30000 });
      await loadState();
      resettingRef.current = false;
      setResetting(false);
      // If a pre-reset request is still draining, this records one fresh read to run after it.
      await loadPile(true);
    } catch (e) {
      resettingRef.current = false;
      setResetting(false);
      // A failed archive restores the authoritative thread; never leave a client-only blank
      // conversation that would still carry the previous model context on its next turn.
      try { await loadState(); } catch { /* preserve the archive error below */ }
      setErr(errText(e));
    }
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
  // a card's "open on the Timeline": the row opens on the stage, over the chat, right here - the rail
  // reads the hash and pins the row (FeedView); its close comes back to the conversation
  const timeline = (mid) => { window.location.hash = `msg=${mid}`; };
  const openWhatsApp = () => {
    window.location.hash = "connector=whatsapp";
    onNavigate?.("Connections");
  };
  // a row pulled off the rail - the pipe's or the Timeline's - goes on the table exactly as the pipe's
  // own click does, by the same key (so the server puts the same item up, whichever list it came from)
  // The pile IS the assistant's walk, so pulling one always answers in the chat. In task mode the
  // stage was showing the "Pick anything on the left" placeholder instead, so a click on a pipe row
  // put a turn somewhere invisible and read as nothing happening at all (the owner, 2026-09-04: "I
  // clicked on task and it just made the morning digest disappear and nothing hovered and opened").
  const pull = (key, asUser) => {
    setRailOpen(false); if (old) setOld(null); setStageMode("chat"); surface(key, asUser || null);
  };

  // What the Chat/Task toggle MEANS on the pipe rail: chat pulls the row into the conversation,
  // task opens it on the stage the way a feed row does. Only a row with a message behind it can be
  // opened - a meeting, a wrapup or an agent has no message, so those still answer in the chat,
  // and pull() switches the stage there so the answer is not written somewhere invisible.
  const pullOrOpen = (key, asUser, openByMid) => {
    const it = (pile?.items || []).find((i) => i.key === key);
    if (stageMode === "task" && it?.mid && openByMid?.(it.mid)) { setRailOpen(false); return; }
    pull(key, asUser);
  };

  const actions = { done, start, handOff, openTask: onOpenTask, timeline, navigate: onNavigate, pick: (o) => send(o),
    surface: (key, note) => {
      if (note) setMsgs((m) => [...m, { id: `r${Date.now()}`, role: "receipt", text: note }]);
      deferInChat(() => key ? surfaceRef.current?.(key) : loadPileRef.current?.(), 900);
    } };
  const shown = old ? old.messages : msgs;
  const lastCardIdx = useMemo(() => { for (let i = shown.length - 1; i >= 0; i -= 1) if (shown[i].card) return i; return -1; }, [shown]);

  const chat = (
    <div className="tq-asst-col" style={{ position: "relative", flex: 1, minHeight: 0 }}>
      <div className="tq-chat-head">
        <Box sx={{ width: 30, height: 30, borderRadius: 2, background: "linear-gradient(90deg, #55697a, #7d9a7c)", display: "grid", placeItems: "center", flexShrink: 0 }}><TaskuaryMark size={22} /></Box>
        <div className="who" style={{ minWidth: 0 }}><b>Taskuary</b><span>{old ? `An earlier chat · ${fmtDateTime(old.at)}` : resetting ? "new chat" : statusLine(items, busy)}</span></div>
        <div className="grow" />
        <StageMode mode={stageMode} setMode={setStageMode} />
        <Tooltip title="The Timeline"><IconButton size="small" onClick={() => setRailOpen(true)} sx={{ display: { xs: "inline-flex", md: "none" } }}><ViewSidebarIcon sx={{ fontSize: 18, color: DIM }} /></IconButton></Tooltip>
        <Tooltip title={speakOnState ? "Reading replies aloud — click to stop" : "Read replies aloud"}><IconButton size="small" className="tq-phone-hide" onClick={toggleSpeak}>{speakOnState ? <VolumeUpIcon sx={{ fontSize: 18, color: "#526b53" }} /> : <VolumeOffIcon sx={{ fontSize: 18, color: DIM }} />}</IconButton></Tooltip>
        <Tooltip title={state?.scripted ? "Scripted demo - no AI is running" : `AI: ${state?.provider || "none"}${state?.model ? ` · ${state.model}` : ""}`}><IconButton size="small" className="tq-phone-hide" onClick={(e) => setAiEl(e.currentTarget)}><TuneIcon sx={{ fontSize: 18, color: DIM }} /></IconButton></Tooltip>
        <Tooltip title="Past chats"><IconButton size="small" onClick={openChats}><HistoryIcon sx={{ fontSize: 18, color: DIM }} /></IconButton></Tooltip>
        <Tooltip title="New chat — archives this one"><IconButton size="small" onClick={newChat} disabled={busy || resetting}><EditNoteIcon sx={{ fontSize: 19, color: DIM }} /></IconButton></Tooltip>
      </div>
      <Popover open={!!aiEl} anchorEl={aiEl} onClose={() => setAiEl(null)} anchorOrigin={{ vertical: "bottom", horizontal: "right" }} transformOrigin={{ vertical: "top", horizontal: "right" }}
        slotProps={{ paper: { sx: { p: 1.5, width: 320 } } }}>
        <Typography sx={{ fontSize: 12, fontWeight: 700, color: INK, mb: 0.5 }}>{state?.scripted ? "Scripted demo assistant" : "Which AI speaks here"}</Typography>
        <Typography variant="caption" sx={{ color: DIM, display: "block", mb: 1, lineHeight: 1.45 }}>{state?.scripted
          ? "Every thread, Timeline post, and reply here is invented and runs locally in this page. No AI, agent, mailbox, or outside system is connected."
          : "Your CLI agent is the default, on its quick gear (haiku, low effort, flash) - it can read, rerun reports and run tools. An API model answers faster but cannot act. The agents doing the actual work are chosen elsewhere."}</Typography>
        <Select size="small" fullWidth value={state?.pick || ""} displayEmpty disabled={!!state?.scripted} onChange={(e) => pickAi(e.target.value)} sx={{ fontSize: 12 }}>
          {!state?.providers?.length && <MenuItem value="">No AI connected</MenuItem>}
          {(state?.providers || []).map((p) => <MenuItem key={p.pick} value={p.pick} sx={{ fontSize: 12 }}>{p.label}{p.type === "demo" ? " · local fixture" : p.type === "cli" ? " · can act (default)" : " · fast, talk only"}</MenuItem>)}
        </Select>
      </Popover>
      {old && <div className="tq-old-banner"><span>You are reading an earlier chat.</span><button type="button" className="tq-chip" onClick={() => setOld(null)}>Back to today</button></div>}
      {chatsOpen && (
        <div className="tq-chats">
          <div className="tq-chats-head">Chats<span style={{ flex: 1 }} /><IconButton size="small" onClick={() => setChatsOpen(false)}><CloseIcon sx={{ fontSize: 16 }} /></IconButton></div>
          <div className="tq-chats-list">
            {chatsLoading && <Typography sx={{ color: FAINT, fontSize: 12, p: 1.5 }}>Loading past chats…</Typography>}
            {!chatsLoading && !chats.length && <Typography sx={{ color: FAINT, fontSize: 12, p: 1.5 }}>No earlier chats yet.</Typography>}
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
              <b>{greeting()}</b>
              <span>{items.length ? `How can I help? ${waitingLine(ready)}`
                : "How can I help? Nothing is waiting on you - ask me anything, or set something up."}</span>
              <div className="tq-modes">
                <button type="button" className="tq-chip primary" disabled={resetting || !ready.length} onClick={() => start(null)}
                  title="Everything in the pipe, most important first - mail, reports, agents, meetings">Walk me through my tasks</button>
                <button type="button" className="tq-chip" disabled={resetting || !incoming(ready).length} onClick={() => start("mail")}
                  title="Only what people sent you - mail and chat">Just what came in</button>
                <button type="button" className="tq-chip" disabled={resetting} onClick={setup}
                  title="A scheduled check that reads and summarises, or a workflow that writes data">Set up a report or workflow</button>
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
            <button type="button" className="tq-chip" disabled={busy || resetting || !ready.length} onClick={() => surface()}>Next</button>
            {current && <>
              <button type="button" className="tq-chip" disabled={busy || resetting} onClick={() => settle("done")}>Done</button>
              <button type="button" className="tq-chip" disabled={busy || resetting} onClick={() => settle("later")}>Later</button>
              <button type="button" className="tq-chip" disabled={busy || resetting} onClick={() => settle("skip")}>Tomorrow</button>
            </>}
            <button type="button" className="tq-chip" disabled={busy || resetting} onClick={setup}>Set something up</button>
          </div>
          <div className="tq-compose-box">
            <MicButton size={18} sx={{ width: 34, height: 34, p: 0, color: DIM }} onText={(t) => setText((v) => (v ? `${v} ${t}` : t))} />
            <Tooltip title="Send an emoji response">
              <IconButton size="small" aria-label="Choose an emoji response" disabled={busy || resetting}
                onClick={(e) => setEmojiEl(e.currentTarget)} sx={{ width: 34, height: 34, p: 0, color: DIM }}>
                <SentimentSatisfiedAltIcon sx={{ fontSize: 18 }} />
              </IconButton>
            </Tooltip>
            <textarea rows={1} value={text} disabled={resetting} placeholder={current ? "Ask about this one, tell me what to do with it, or name something else…" : "Ask Taskuary anything — a name or a subject pulls it in…"}
              onChange={(e) => setText(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }} />
            <button type="button" className="tq-send" aria-label="Send" disabled={busy || resetting || !text.trim()} onClick={() => send()}><SendIcon fontSize="small" /></button>
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
          <div className="tq-compose-hint">Enter sends · Shift+Enter adds a line · click a row on the left to pull it in · the buttons on a card do the acting</div>
          <button type="button" className="tq-whatsapp-connect" onClick={openWhatsApp}>
            <ChannelIcon channel="whatsapp" sx={{ fontSize: 15 }} />
            Connect WhatsApp to the Assistant
          </button>
        </div>
      )}
    </div>
  );

  // the task view's resting stage: what the rail is for in this mode, and the way back to the chat
  const placeholder = (
    <Box sx={{ height: "100%", border: `1px dashed ${BORDER}`, borderRadius: 2, display: "flex", flexDirection: "column",
      alignItems: "center", justifyContent: "center", gap: 1, px: 4, textAlign: "center" }}>
      <Typography sx={{ fontSize: 13.5, fontWeight: 600, color: DIM }}>Pick anything on the left</Typography>
      <Typography variant="caption" sx={{ color: FAINT, maxWidth: 380, lineHeight: 1.6 }}>
        Hovering a row opens it here; clicking pins it. You get the message that arrived, why triage sent it
        where it did, what the agent is doing about it, and the reply waiting to go — each on its own tab.
      </Typography>
      <Box sx={{ mt: 1 }}><StageMode mode={stageMode} setMode={setStageMode} /></Box>
    </Box>
  );

  return (
    <FeedView onOpenTask={onOpenTask} onChanged={onChanged} active={active}
      top={({ openByMid }) => <Pile pile={pile} current={old ? null : currentItem}
        onPull={(key, asUser) => pullOrOpen(key, asUser, openByMid)} />}
      stage={stageMode === "chat" ? chat : placeholder} rowMode={stageMode}
      onPull={(r) => pull(keyForRow(r), `Tell me about “${r.Subject || r.Title || "this"}”`)}
      railOnNarrow={railOpen} />
  );
}
