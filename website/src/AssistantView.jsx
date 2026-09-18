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
import React, { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
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
import PreviousWork from "./PreviousWork.jsx";
import { Md, looksMd } from "./md.jsx";
import { ChannelIcon, MicButton, TaskuaryMark, fmtDateTime, fmtTime12 } from "./ui.jsx";
import { BORDER, DIM, FAINT, INK, ROLES } from "./theme.jsx";
import ProposalCard from "./ProposalCard.jsx";
import { afterCancel, afterConfirm, afterExecute, markExecuted, proposalOf } from "./proposalCard.js";
import { LEVEL_META, LEVEL_ROLE, ageText, agoText, arrivals, bandsOf, canAdvanceSelection, captureNextSelection, cardFor, currentItemFromPile, displayRevision, drawOrder, fillCaps, followsItem, hasNextSelection, interactiveCardIndex, keysOf, laneCounted, lastSaidIndex, chipsOf, CAPPED, FLOOR, FOOT_PX, levelLabel, nextMarkerKey, trimCaps, ROW_PX, nextSelectionBody, nextSelectionScope, pendingAlerts, railAge, refreshCurrentPresentation, refreshPilePresentation, replaceSelectionToken, rowMeta, sameSelectionScope, selectionGuardDetail, statusLine, topAlert } from "./funnelPile.js";
import { coveredByReload, heldSince } from "./funnelPile.js";
import { isCoveragePending } from "./processingAll.js";
import { mergeDurableTurns } from "./assistantTurns.js";
import { AgentCard, AgentDoneCard, BriefCard, FyisCard, IdeaCard, MeetingCard, MessageCard, ReplyCard, ReportCard, SetupCard, SourceMark, TaskCard, WalkCard, WrapupCard, sourceColor } from "./assistantCards.jsx";
import FeedView from "./FeedView.jsx";
import { MORE_PX } from "./funnelPile.js";
import GeneralWorkspace from "./GeneralWorkspace.jsx";
import { ROADS, roadOfCard } from "./timelineState.js";
import { walkAdvances } from "./walkStep.js";
import "./assistantView.css";

// Which walk-through this tab was in. Per-browser and deliberately thin - one task id - because the
// walk itself lives on the server: a reload asks the task whether it is still an open set-up before
// showing anything, so a stale key restores nothing.
const WALK_KEY = "taskuary_walk_tid";
const isOpenWalk = (t) => !!t && t.SourceRef === "assistant:setup" && !["done", "dropped"].includes(t.Status);

// what a PERSON sent, whatever lane it landed in (funnel.came_in): a slipped follow-up about a mail
// is still mail, and the walk that skipped it said "0 of them are mail" with five in the pipe
const incoming = (items) => (items || []).filter((i) => i.mid && !["report", "own", "assistant"].includes(i.channel || "email"));
const waitingLine = (items) => {
  const n = (items || []).length, came = incoming(items).length;
  // the counting words come from the one vocabulary (taskuary/lanes.json via funnelPile), not from a
  // third copy written out here - this line said "landed" while the row beside it said "report"
  const by = ["forgotten", "report", "fyi"]
    .map((lane) => [laneCounted(lane), (items || []).filter((i) => i.lane === lane).length]).filter(([, k]) => k);
  return `${n} waiting${came ? ` - ${came} came in` : ""}${by.length ? `, ${by.map(([w, k]) => `${k} ${w}`).join(", ")}` : ""}.`
    + " I'll take you through them one at a time.";
};

// WHAT THE HEADING ALREADY SAID. A row speaks only when its own word ADDS something: "slipped"
// under fyi does, "fyi" under fyi does not, and "agent finished" under agents working does -
// because the band says they are still going (the owner, 2026-09-16: "show emoji if it says
// something besides for what lane it's in"). Compared on the WORD, not the lane, so a kind that
// overrides its lane's word - agentdone, wrapup - is judged on the word it actually shows.
const BAND_SAYS = { reports: "report", fyi: "fyi", agents: "agent working" };
const ROW_H = 33, CUR_H = 57;   // a Timeline row (30px + its 3px gap); the current one opens up to two lines
// what sits UNDER the bands and still has to fit: the pile's own padding, the cheer line and the
// two quiet notes, and the scroller's bottom padding (funnelPile.FOOT_PX)
const PILE_FOOT = FOOT_PX;
const EMOJI_REPLIES = [
  ["👍", "Sounds good"], ["❤️", "Love it"], ["😂", "Funny"], ["🎉", "Celebrate"],
  ["👏", "Well done"], ["🙏", "Thank you"], ["✅", "Confirmed"], ["👀", "Looking"],
  ["🤔", "Thinking"], ["😕", "Unsure"], ["👎", "No thanks"], ["🔥", "Excellent"],
];
const errText = (e) => {
  const detail = e?.response?.data?.detail || e?.detail;
  if (detail?.code?.startsWith("selection_")) return detail.message || (detail.code === "selection_unavailable"
    ? "Next is temporarily unavailable. Review the refreshed list and try again."
    : detail.retryable === false
    ? "That Next request may already have completed. Review the refreshed conversation before acting again."
    : "Next changed while the list refreshed. Review the updated Next item and press Next again.");
  return (typeof detail === "string" ? detail : null) || e?.message || "Taskuary could not answer.";
};
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
  // A full account can return dozens of canonical rows together. Painting that entire stack in
  // one React commit leaves the rail blank until the browser has laid out every card. On the
  // first successful load, put the first row down immediately and admit a small batch per
  // animation frame. One row per frame made a 507-row account take at least 8.5 seconds even
  // before layout; batching keeps progressive paint without making the inventory the timer.
  const firstLoad = useRef(null);
  const [revealed, setRevealed] = useState(1);
  useEffect(() => {
    if (!pile) return undefined;
    const revision = displayRevision(pile) || "loaded";
    if (firstLoad.current !== null) {
      firstLoad.current = revision;
      setRevealed(items.length);
      return undefined;
    }
    firstLoad.current = revision;
    setRevealed(Math.min(1, items.length));
    if (items.length <= 1) return undefined;
    let frame = 0;
    const addBatch = () => {
      setRevealed((count) => {
        const next = Math.min(items.length, count + 24);
        if (next < items.length) frame = requestAnimationFrame(addBatch);
        return next;
      });
    };
    frame = requestAnimationFrame(addBatch);
    return () => cancelAnimationFrame(frame);
  }, [displayRevision(pile)]);                                     // eslint-disable-line react-hooks/exhaustive-deps
  const visibleItems = items.slice(0, revealed);
  // WHAT IS ON THE TABLE STAYS WHERE IT IS. The current item used to be lifted out of the pile and
  // redrawn at the top of one flat stack. The rail is grouped by category now, so hoisting would
  // tear a row out of its band on every Next - and an fyi BATCH would tear out ten. Nothing is
  // reordered: the row wears the ring where it already sits, and a batch draws ONE bracket around
  // all of its members (the owner, 2026-09-16: "when the fyi is showing in assistant the work
  // timeline should highlight all 4 or 10 ... now i think it condenses"). Every row's `top` is
  // still computed by the same running sum, so the glide the pile has always had is untouched.
  const batch = current?.kind === "fyis" ? current : null;
  // `members` is the server's word for them; `items` is the same list as cards, and is what an
  // older server sends - read either, so the bracket cannot go missing on a version skew.
  const batchKeys = new Set(batch ? (batch.members || (batch.items || []).map((i) => i.key)) : []);
  const curKey = current && !batch ? current.key : null;
  // a task named in the chat is on the table without being in the pile: it joins its own band
  const known = curKey && visibleItems.some((i) => i.key === curKey);
  // SHOWN IS READ, so the moment a batch goes up its rows leave the pile - and the rail had
  // nothing left to ring. While the batch is ON THE TABLE its entries are put back, in their own
  // band, so you can see the four things being talked about instead of watching them disappear.
  const have = new Set(visibleItems.map((i) => i.key));
  const onTable = batch ? (batch.items || []).filter((i) => i.key && !have.has(i.key)) : [];
  const drawn = [
    ...(curKey && !known ? [{ ...current }] : []),
    ...onTable,
    ...drawOrder(visibleItems).map((i) => (i.key === curKey ? { ...i, ...current } : i)),
  ];
  const prev = useRef(null);
  const [landing, setLanding] = useState(new Set());
  useEffect(() => {
    const fresh = arrivals(prev.current, items);
    prev.current = keysOf(items);
    if (!fresh.size) return undefined;
    setLanding(fresh);
    const t = setTimeout(() => setLanding(new Set()), 40);       // one frame above the pipe, then it falls to its slot
    return () => clearTimeout(t);
  }, [displayRevision(pile)]);                                     // eslint-disable-line react-hooks/exhaustive-deps
  // The NEXT ring has to be what the Next button will actually bring up. The server skips what an
  // agent has in hand and what this walk already showed (funnel.next_item); the marker did not, so a
  // coder parked on a question wore NEXT while two fyi about lunch came out instead (2026-09-03).
  // New servers capture the selection from the same snapshot as this pile. FYI batches have a
  // composite selected key, so their first ordered member wears the visible NEXT marker.
  const nextKey = nextMarkerKey(pile, items, current);
  // how close to empty, once that is worth saying (the owner asked for it at "halfway down the
  // funnel", so from fifteen: the count is the encouragement - no header, no total)
  const left = items.filter((i) => !i.settling && i.lane !== "working").length;
  const cheer = !left || left > 15 ? "" : left === 1 ? "One more and the pipe is clear."
    : left <= 5 ? `${left} to go, then the pipe is clear.` : `${left} away from a clear pipe.`;

  // ── the ranked tail, when a connector is in bulk mode ───────────────────────────────────────
  // The server says WHICH row wears the pill and how many wait behind it; on an install that ranks
  // nothing it says null, and every line below is dead. An owner who takes one item at a time never
  // sees any of this (the owner, 2026-09-18: "i should not see it since i process each by itself").
  const moreAfter = pile?.more_after || null;
  const [waitingOpen, setWaitingOpen] = useState(false);
  const [waiting, setWaiting] = useState(null);
  useEffect(() => {
    if (!waitingOpen || !moreAfter) return;
    let alive = true;
    api.get("/api/funnel/waiting").then(({ data }) => { if (alive) setWaiting(data); }).catch(() => {});
    return () => { alive = false; };
  }, [waitingOpen, moreAfter]);
  useEffect(() => { if (!moreAfter) setWaitingOpen(false); }, [moreAfter]);

  // ── how much of each band fits ──────────────────────────────────────────────────────────────
  // urgent, your task and agents working draw in full; reports and fyi divide what is left of the
  // rail's height, floor of two (funnelPile.fillCaps). It is MEASURED from the scroller, so the
  // answer follows the window instead of being a number somebody picked.
  const bands = bandsOf(drawn);
  const sig = bands.map((b) => `${b.level}:${b.items.length}`).join(",");
  const wrapRef = useRef(null);
  const [room, setRoom] = useState(0);
  useLayoutEffect(() => {
    const el = wrapRef.current;
    const scroller = el?.closest("[data-tq-rail]");
    if (!el || !scroller) return undefined;
    // only the SCROLLER is observed. Watching the pile too would be a feedback loop, because the
    // pile's own height is the thing this measurement decides.
    const measure = () => {
      const top = el.getBoundingClientRect().top - scroller.getBoundingClientRect().top;
      const next = Math.max(0, scroller.clientHeight - top - PILE_FOOT);
      setRoom((was) => (Math.abs(was - next) > 4 ? next : was));
    };
    measure();
    if (typeof ResizeObserver === "undefined") return undefined;
    const ro = new ResizeObserver(measure);
    ro.observe(scroller);
    return () => ro.disconnect();
  }, [sig]);
  const [opened, setOpened] = useState(() => new Set());        // bands the owner opened by hand
  // WHAT THE ESTIMATE MISSED. fillCaps costs what it expects the browser to paint; this is the
  // overflow it actually painted, measured once per change and given back in rows. Bounded by the
  // guard below so a band that cannot shrink any further can never spin.
  const [trim, setTrim] = useState(0);
  useLayoutEffect(() => { setTrim(0); }, [sig]);
  // the row on the table is 24px taller than the rest, and it is drawn inside one of these bands
  const base = fillCaps(room - (curKey ? CUR_H - ROW_H : 0), bands);
  // how many rows the capped bands could still give back before they are at their floor. Past that
  // the rail genuinely does not fit and scrolls: your task and agents working are never trimmed.
  const headroom = CAPPED.reduce((n, level) => n + Math.max(0, (base[level] ?? 0) - FLOOR), 0);
  const caps = trimCaps(base, bands, trim);
  useLayoutEffect(() => {
    const el = wrapRef.current;
    const scroller = el?.closest("[data-tq-rail]");
    if (!el || !scroller || trim >= headroom) return;
    const over = scroller.scrollHeight - scroller.clientHeight;
    if (over > 4) setTrim((was) => Math.min(headroom, was + Math.ceil(over / ROW_PX)));
  });

  return (
    <div className="tq-pile" data-tq-keep ref={wrapRef}>
      {!pile ? (
        <div className="tq-pile-empty" role="status"><CircularProgress size={18} /><b>Loading timeline</b>Reading what arrived and what still needs you.</div>
      ) : !drawn.length ? (
        <div className="tq-pile-empty"><span className="mark">✓</span><b>All done</b>Nothing is waiting on you. New things land here as they arrive, and Taskuary speaks up.</div>
      ) : bands.map(({ level, items: rows }) => {
        const open = opened.has(level);
        const cap = open ? rows.length : (caps[level] ?? rows.length);
        // only the two bands the rail is allowed to cap can be folded; urgent, your task and agents
        // working are never hidden, so a chevron on them would offer nothing
        const folds = CAPPED.includes(level) && rows.length > FLOOR;
        // what is on the table is never capped away, wherever in its band it sits
        const shown = rows.filter((i, n) => n < cap || i.key === curKey || batchKeys.has(i.key));
        const hidden = rows.length - shown.length;
        let stackHeight = 0;
        // BULK PROCESSING: the "250 more" pill hangs off the LAST ranked row, where reading stopped -
        // not off the band, which is what the fyi pill means. It takes real height, so the rows under
        // it move down by exactly that and the stack still measures true.
        let moreTop = null;
        const positioned = shown.map((item) => {
          const top = stackHeight;
          stackHeight += item.key === curKey ? CUR_H : ROW_H;
          if (moreAfter && item.key === moreAfter.key) { moreTop = stackHeight; stackHeight += MORE_PX; }
          return { item, top };
        });
        // the bracket spans its members where they already are: it adds no height and moves no row
        const mem = positioned.filter(({ item }) => batchKeys.has(item.key));
        const bracket = mem.length
          ? { top: mem[0].top - 4, height: mem[mem.length - 1].top + ROW_H - mem[0].top + 5 } : null;
        return (
          <div className="tq-pile-band" key={level} data-tq-run={level}>
            {/* the category, said once, in the one place importance exists in this product - and
                the reason the dock above the rail no longer carries a level dropdown saying it.
                A band that can be opened is also the way to shut it again: opening one had no way
                back at all (the owner, 2026-09-16: "clicking on fyi or reports should close it
                back up or a tiny arrow"). */}
            <div className={`tq-pile-head${folds ? " folds" : ""}`} title={folds
              ? (open ? `Collapse ${levelLabel(level)}` : `Show all ${rows.length}`)
              : (LEVEL_META[level]?.hint || "")}
              onClick={folds ? () => setOpened((cur) => {
                const next = new Set(cur);
                if (next.has(level)) next.delete(level); else next.add(level);
                return next;
              }) : undefined}>
              <span style={{ color: ROLES[LEVEL_ROLE[level]]?.ink, background: ROLES[LEVEL_ROLE[level]]?.tint,
                borderColor: ROLES[LEVEL_ROLE[level]]?.bd }}>{levelLabel(level)}</span>
              {folds && <i className="fold">{open ? "▾" : "▸"}</i>}
              <hr /><em>{rows.length}</em>
            </div>
            <div className="tq-pile-stack" style={{ height: stackHeight }}>
              {bracket && (
                <div className="tq-pile-batch" style={{ top: bracket.top, height: bracket.height }}>
                  <b>on the table · {mem.length} fyi</b>
                </div>
              )}
              {positioned.map(({ item: i, top }) => {
                const meta = rowMeta(i);
                const isCur = i.key === curKey;
                const inBatch = batchKeys.has(i.key);
                const cls = ["tq-pile-row", landing.has(i.key) ? "landing" : "", i.settling ? "settling" : "",
                  isCur ? "current" : inBatch ? "inbatch" : i.key === nextKey ? "next" : ""].filter(Boolean).join(" ");
                // the one pill a row can still wear: work has STOPPED until you answer it.
                const loud = i.lane === "blocked" || i.lane === "approve";
                // ...and every other row says its lane - mark and word - unless that is the very
                // thing the heading above it already said (BAND_SAYS).
                // A MEETING says its clock time instead. "coming up" is what the urgent heading and
                // the age already tell you; what it does not tell you is when to be there (the
                // owner, 2026-09-16: "for calendar invite you need to say the actual time of the
                // meeting"). It goes on the card rather than in the gutter, which is an age column
                // for every row and too narrow for a time.
                const word = i.settling ? ""
                  : i.kind === "meeting" ? `invite · ${fmtTime12(i.when)}`
                    : meta.word !== BAND_SAYS[level] ? meta.word : "";
                return (
                  <div key={i.key} className={cls} style={{ top: landing.has(i.key) ? -ROW_H : top }}>
                    <span className="when">{railAge(i.kind === "meeting" ? i.when : (i.since || i.when))}</span>
                    {/* the dot is WHERE IT CAME FROM. The logo says the same at reading size; the
                        dot says it at scanning size, down a column you can run an eye along. */}
                    <span className="rail"><i style={{ background: sourceColor(i) }} /></span>
                    <div className="card" onClick={() => !i.settling && !isCur && onPull(i.key, `Show me “${i.title}”`)}
                      title={[i.who, meta.word, i.ref, i.promoted ? 'triage moved it up' : '', i.why].filter(Boolean).join(" · ")}>
                      <div className="t">
                        <span className="logo"><SourceMark item={i} size={15} /></span>
                        <b>{i.title}</b>
                        {/* which task this IS. It is how you say "TQ-0588" to the assistant, how you
                            match a row to the Tasks tab, and it was only ever in the tooltip. */}
                        {!!i.ref && <span className="tq-pile-ref">{i.ref}</span>}
                        {i.settling && <span className="tq-pile-tag">triaging…</span>}
                        {loud && !i.settling && (
                          <span className="tq-pile-tag loud"
                            style={{ color: ROLES.you.ink, background: ROLES.you.tint, borderColor: ROLES.you.bd }}>
                            {meta.mark} {meta.word}</span>
                        )}
                        {!loud && !!word && (
                          <span className="tq-pile-word"
                            style={meta.role === "bad" ? { color: ROLES.bad.ink } : undefined}>
                            <i>{meta.mark}</i>{word}</span>
                        )}
                      </div>
                      {isCur && <div className="sub">{[i.why, i.kind === "meeting" ? ageText(i.when) : agoText(i.since || i.when)].filter(Boolean).join(" · ")}</div>}
                    </div>
                    {/* THE SAME WORD ON THE SAME BORDER. A handful on the table says so on its
                        bracket ("on the table · 4 fyi"); one item on the table wore the identical
                        slate ring and said nothing, so the ring had to be read rather than known
                        (the owner, 2026-09-17: "isn't there a current word on the border around
                        chosen task by the assistant?"). It is a sibling of the card, not a child:
                        the card clips its overflow so the title can ellipse. */}
                    {isCur && <b className="tq-pile-now">on the table</b>}
                  </div>
                );
              })}
              {moreTop != null && (
                <button type="button" className="tq-pile-more" style={{ position: "absolute", top: moreTop }}
                  title="Ranked and waiting to be read - one is read each time you finish one above"
                  onClick={() => setWaitingOpen((v) => !v)}>
                  {moreAfter.count} more
                </button>
              )}
            </div>
            {moreTop != null && waitingOpen && (
              <div className="tq-pile-waiting">
                {/* nothing below the line has been triaged, so there is no lane, no ref and no task
                    list to draw - only what the arrival itself carried, and the rank's own reason */}
                {(waiting?.items || []).slice(0, 20).map((w) => (
                  <div key={w.mid} className="tq-pile-waitrow">
                    <span className="subj">{w.subject}</span>
                    <span className="why">{[w.who, w.why].filter(Boolean).join(" \u00b7 ")}</span>
                  </div>
                ))}
                {!waiting && <div className="tq-pile-waitrow"><span className="why">Reading the list\u2026</span></div>}
                {waiting && waiting.count > 20 && (
                  <div className="tq-pile-waitrow"><span className="why">{waiting.count - 20} more below these</span></div>
                )}
              </div>
            )}
            {hidden > 0 && (
              <button type="button" className="tq-pile-more"
                onClick={() => setOpened((cur) => new Set(cur).add(level))}>
                {hidden} more {level === "reports" ? "reports" : "fyi"}
              </button>
            )}
          </div>
        );
      })}
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
function Line({ m, live, last, actions, fresh }) {
  if (m.role === "user") return <div className="tq-msg you"><div className="body">{m.text}</div></div>;
  if (m.role === "receipt") return (
    <div className="tq-msg receipt"><span /><div className="body">✓ {m.text}
      {!!m.tid && <button type="button" className="tq-chip" style={{ marginLeft: 8 }} onClick={() => actions.openTask?.(m.tid)}>Open {m.ref || "the task"}</button>}
      {/* a receipt can carry the walk's own word: a sweep puts the table down and OFFERS Next rather
          than jumping to the next thing by itself (the owner, 2026-09-11). Same strip, same buttons. */}
      {last && !!chipsOf(m).length && (
        <div className="tq-verbs">
          {chipsOf(m).map((c, i) => (
            <button key={c.verb || c.label} type="button" className={i === 0 ? "tq-verb primary" : "tq-verb"}
              disabled={actions.busy} onClick={() => actions.chip(c)}>{c.label}</button>
          ))}
        </div>
      )}
    </div></div>);
  // The funnel deliberately renames msg:<mid> to agent:<tid> when somebody takes the task. Follow
  // the task identity across that rename; matching only the old key left a live coder displayed as
  // "nobody on it" until a new chat line happened to replace the card.
  const follows = live && !m.proposal && followsItem(m.card, fresh);   // a proposal is its own card, never the item's
  // ``fresh`` is a complete presentation, not a patch. Exact replacement clears source fields
  // that disappeared while retaining the durable conversation line and the card's local UI state.
  const c = follows ? fresh : m.card;                     // the live card follows the pile
  const kind = c?.kind === "setup" ? "setup" : c?.kind === "walk" ? "walk" : (m.proposal || c?.kind === "proposal") ? "proposal" : cardFor(c);
  // From the DURABLE turn, never from `fresh`: the vocabulary was chosen when the line was written and
  // is recorded with it, while a pile refresh rebuilds the live item WITHOUT chips - reading them off
  // `fresh` made the words vanish on the next poll. A verb that has since stopped applying is refused
  // server-side at propose time, which is the only place that can know.
  // A proposal is waiting on its own Confirm: offering the item's verbs beside it invites two answers.
  const chips = last && !m.proposal && kind !== "proposal" ? chipsOf(m) : [];
  const card = live && m.card && kind ? {
    proposal: <ProposalCard p={m.proposal || c} onConfirm={actions.confirm} onCancel={actions.cancel} onPreview={actions.preview} />,
    reply: <ReplyCard card={c} onDone={actions.done} onOpenTask={actions.openTask} onTimeline={actions.timeline} />,
    agent: <AgentCard card={c} onDone={actions.done} onOpenTask={actions.openTask} />,
    meeting: <MeetingCard card={c} onDone={actions.done} onOpenTask={actions.openTask} />,
    report: <ReportCard card={c} onOpenTask={actions.openTask} onTimeline={actions.timeline} onDone={actions.done} />,
    agentdone: <AgentDoneCard card={c} onOpenTask={actions.openTask} onDone={actions.done} onSurface={actions.surface} />,
    idea: <IdeaCard card={c} onAct={actions.done} onOpenTask={actions.openTask} onTimeline={actions.timeline} />,
    message: <MessageCard card={c} onDone={actions.done} onOpenTask={actions.openTask} onTimeline={actions.timeline} onSurface={actions.surface} />,
    setup: <SetupCard card={m.card} onNavigate={actions.navigate} onHandOff={actions.handOff} />,
    walk: <WalkCard card={m.card} at={m.card.n} total={m.card.total} onNavigate={actions.navigate}
      onNext={() => actions.walk(m.card.n + 1)} onBack={() => actions.walk(m.card.n - 1)}
      onRestart={actions.walkRestart} onFinish={() => actions.walk(-1)}
      onSaved={() => actions.walkSaved(m.id)} />,
    brief: <BriefCard card={m.card} onStart={actions.start} />,
    task: <TaskCard card={c} onDone={actions.done} onOpenTask={actions.openTask} />,
    fyis: <FyisCard card={c} onDone={actions.done} onSurface={actions.surface} onTimeline={actions.timeline} onPropose={actions.propose} />,
    wrapup: <WrapupCard card={c} onDone={actions.done} onOpenTask={actions.openTask} />,
  }[kind] : null;
  // A STOP THE WALK HAS MOVED PAST is a finished step, not something the assistant said. Falling
  // through to the title note below drew six near-identical rows, each carrying the message avatar
  // AND the card's own mark - two snowflakes and a title, six times, with nothing saying they were
  // one walk (the owner, running it). It keeps its place in the trail as one muted line that counts
  // itself, so scrolling up reads as the steps already passed.
  const passed = !live && kind === "walk" && !!m.card;
  return (
    <>
      <div className={passed ? "tq-msg tq-step" : "tq-msg"}>
        {!passed && <div className="avatar"><TaskuaryMark size={18} /></div>}
        <div className="body">
          {m.text ? (looksMd(m.text) ? <Md text={m.text} /> : m.text.split("\n").map((p, i) => <p key={i}>{p}</p>)) : null}
          {passed && (
            <div className="tq-step-done"><i>✓</i><b>{(m.card.n ?? 0) + 1} of {m.card.total}</b>
              <span>·</span>{m.card.title}</div>
          )}
          {!passed && !live && m.card && kind && kind !== "setup" && kind !== "brief" && (
            <div className="tq-card-note" style={{ display: "flex", alignItems: "center", gap: 5 }}>
              <SourceMark item={m.card} size={12} /> {m.card.title}
              {m.card.tid && <a href={`#task=${m.card.tid}`} style={{ color: "#55697a", marginLeft: 4 }}>{m.card.ref}</a>}
            </div>
          )}
          {card}
          {/* The action words, in the assistant's own line - one place to look, chosen by the server from
              the item's kind and already filtered to what this one can carry (concierge.chips_for). A
              strip over the composer and a second row under the bubble said the same things twice and
              neither was where the sentence was (the owner, 2026-09-07). */}
          {last && !!chips.length && (
            <div className="tq-verbs">
              {chips.map((c, i) => (
                <button key={c.verb || c.label} type="button" className={i === 0 ? "tq-verb primary" : "tq-verb"}
                  title={c.hint || undefined} disabled={actions.busy} onClick={() => actions.chip(c)}>{c.label}</button>
              ))}
            </div>
          )}
        </div>
      </div>
    </>
  );
}

// ── the page ─────────────────────────────────────────────────────────────────────────────────
export default function AssistantView({ onOpenTask, onNavigate, onChanged, active = true }) {
  const [state, setState] = useState(null);           // /api/concierge: the dock task, its turns, the AI choices
  const handoff = state?.handoff || null;             // the walk is in a phone chat: this tab is locked behind it
  // A set-up walk-through, running HERE. The conversation binds to that task's own session - which
  // is the one with the browser and the operator's brain - so the owner never leaves this tab to be
  // walked through something they just asked for. Leaving is a button; the task and its session
  // outlive it either way, so nothing is lost by leaving and nothing is resumed by accident.
  const [walk, setWalk] = useState(null);
  const [msgs, setMsgs] = useState([]);
  const [pile, setPile] = useState(null);
  const [busy, setBusy] = useState(false);
  // the walk validates Current against the pile before it can say anything, and that read was
  // 5-47s (2026-09-09). busy is the TURN's interlock and surface() refuses to run while it is
  // set, so opening needs its own flag - without one the button stayed enabled, said nothing,
  // and looked broken for the whole wait.
  const [starting, setStarting] = useState(false);
  const [resetting, setResetting] = useState(false);  // replacing a chat is housekeeping, never an AI turn
  const [work, setWork] = useState([]);              // the turn's tool calls and progress, as they stream
  const [err, setErr] = useState("");
  const [current, setCurrent] = useState(null);       // the key on the table
  const [currentItem, setCurrentItem] = useState(null);   // ...and the item itself, drawn at the top of the pipe
  const [text, setText] = useState("");
  const [acked, setAcked] = useState(() => new Set());
  const [notices, setNotices] = useState([]);           // the page's own strip notices: a newer message on Current (PW-165)
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
  const pileFlight = useRef(null);
  const pileForcePending = useRef(false);
  const loadPileRef = useRef(null);
  const forcedLoadStartedAt = useRef(0);       // when the last forced pile load began (funnelPile.coveredByReload)
  const currentRef = useRef(null); const surfaceRef = useRef(null); const speakRef = useRef(null);
  const noticedRef = useRef(null);      // the context notice the stream already showed this turn
  const only = useRef(null);                                       // "mail" once the owner chose to start with the mail
  const selectionRef = useRef(null);
  const selectionContractSeen = useRef(false);

  // one turn of the assistant, streamed: tool calls show under the dots as they happen, `done` is the answer
  const turn = useCallback(async (body) => {
    setWork([]);
    const plain = async () => {
      const endpoint = body.mode === "open" ? "/api/concierge/open" : body.mode === "next" ? "/api/concierge/next" : "/api/concierge/say";
      return (await api.post(endpoint, body.mode === "next" ? { key: body.key, only: body.only, include_surfaced: body.include_surfaced, exclude: body.exclude,
        selection_revision: body.selection_revision, expected_next_key: body.expected_next_key, expected_next_members: body.expected_next_members }
        : body.mode === "say" ? { text: body.text, key: body.key, context_mid: body.context_mid } : {})).data;
    };
    // The public demo is intentionally a local script. Do not even attempt the streaming AI
    // endpoint: its invented threads should never look like a model is working behind the page.
    if (DEMO) return plain();
    const token = localStorage.getItem("taskuary_token");
    const res = await fetch("/api/concierge/stream", { method: "POST", headers: { "Content-Type": "application/json", ...(token ? { "X-Taskuary-Token": token } : {}) }, body: JSON.stringify(body) });
    if (!res.ok) {
      // An old server may not have the streaming door. A selection conflict is authoritative:
      // replaying it through the plain endpoint would submit the same navigation twice.
      if ([404, 405, 501].includes(res.status)) return plain();
      let payload = null;
      try { payload = await res.json(); } catch { /* retain the HTTP status */ }
      const error = new Error(typeof payload?.detail === "string" ? payload.detail : `Assistant request failed (${res.status})`);
      error.response = { status: res.status, data: payload || {} };
      throw error;
    }
    if (!res.body) return plain();                    // the static demo, or an older server: the plain door
    for await (const ev of readNdjson(res.body)) {
      if (ev.type === "done") { setWork([]); return ev; }
      if (ev.type === "error") {
        const error = new Error(ev.error || "The assistant could not answer.");
        error.code = ev.code; error.detail = ev.detail;
        throw error;
      }
      // the thread moved while we were about to speak (PW-052): said now, before the answer, once
      if (ev.type === "context_update" && ev.say) {
        setMsgs((m) => [...m, { id: `context${Date.now()}`, role: "assistant", text: ev.say }]);
        noticedRef.current = ev.say;
      }
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
    // Current is the server's persisted, validated word (PW-162) - never inferred from the last card in the
    // transcript: a handled item stays readable history and is not revived as live work, and an invalid
    // Current comes back null with nothing chosen in its place.
    const last = data.current || null;
    currentRef.current = last;
    selectionRef.current = null;
    setCurrent(last?.key || null); setCurrentItem(last);
    return data;
  }, []);
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
      return pileFlight.current;
    }
    const epoch = chatEpoch.current;
    // The optional `current` response belongs to this exact key. A click can put B on the table
    // while the request for A is in flight; that older response may still refresh the rail, but it
    // must never replace or clear B.
    const requestedCurrentKey = currentRef.current?.key || null;
    const requestedScope = nextSelectionScope(only.current, requestedCurrentKey);
    if (force) forcedLoadStartedAt.current = Date.now();
    const request = (async () => { try {
      // the key we are holding rides along, so the server can say whether it is still a thing
      const { data } = await api.get("/api/funnel/pile", { params: {
        ...(requestedCurrentKey ? { current: requestedCurrentKey } : {}),
        only: requestedScope.only, include_surfaced: requestedScope.include_surfaced,
        exclude: requestedScope.exclude,
        ...(force ? { force: 1 } : {}),
      } });
      const activeScope = nextSelectionScope(only.current, currentRef.current?.key || null);
      if (epoch !== chatEpoch.current || resettingRef.current || !sameSelectionScope(requestedScope, activeScope)) {
        pileForcePending.current = true;
        return null;
      }
      const captured = captureNextSelection(data, requestedScope);
      if (hasNextSelection(data)) selectionContractSeen.current = true;
      selectionRef.current = captured;
      setPile((p) => refreshPilePresentation(p, data));
      // Provider messages can arrive while this conversation is already open. The server writes
      // the resulting correction (for example, "you replied in WhatsApp; draft removed") into the
      // durable conversation, so read new turns on every freshness check -- not only when an agent
      // watcher event happens to accompany them.
      const { data: st } = await api.get("/api/concierge");
      if (epoch !== chatEpoch.current || resettingRef.current) return;
      setMsgs((m) => mergeDurableTurns(m, st.messages || []).messages);
      if (data.events?.length) {
        // The watcher's word is a strip notice the server keeps (PW-165/166) and, here, a spoken line.
        // Background activity is never permission to choose, replace, clear, or advance the subject.
        // A FINISHED task says nothing: it is waiting on nobody. An agent that stopped to ask is the
        // one transition that lands on the owner, so it is the one that speaks (the owner, 2026-09-14).
        for (const e of data.events) if (e.kind === "asking") speakRef.current?.(e.text);
      }
      // the item on the table is live: an agent that stops and starts again changes what its row and card say
      // ...and when the server says the key is GONE - the reply was sent, the task closed, it was swept -
      // the table clears itself instead of showing a draft that is no longer waiting on anybody.
      {
        const cur = currentRef.current;
        if ((cur?.key || null) !== requestedCurrentKey) return captured;
        // Starting from Tasks/Board changes msg:<mid> into agent:<tid>. The old key is correctly
        // absent, but the task is not gone: prefer its working row before clearing the table.
        const fresh = currentItemFromPile(cur, data);
        if (fresh) {
          const newer = fresh.mid && cur.mid && fresh.mid !== cur.mid;
          if (newer) {
            // an update about Current is a strip notice (PW-165), never a line the chat writes by itself; the
            // context refresh below is passive and the subject does not change
            const preview = String(fresh.preview || "").replace(/\s+/g, " ").trim().slice(0, 180);
            const line = `New message from ${fresh.who || "someone"} arrived on ${fresh.ref || fresh.title || "this thread"}`
              + (preview ? `: “${preview}”` : "") + ". The context is refreshed."
              + (fresh.rid ? " The earlier draft is now out of date; redraft it before sending." : "");
            const key = `notice:msg:${fresh.mid}`;
            setNotices((n) => [...n.filter((x) => x.key !== key), { key, item: cur.key, kind: "update", lane: cur.lane, text: line, notice: true, local: true }]);
            speakRef.current?.(line);
          }
          const refreshed = refreshCurrentPresentation(cur, fresh);
          if (newer || refreshed !== cur) {
            currentRef.current = refreshed;
            setCurrent(refreshed.key);
            setCurrentItem(refreshed);
          }
        } else if (cur?.key && "current" in data && data.current === null) {
          currentRef.current = null;
          selectionRef.current = null;
          setCurrent(null); setCurrentItem(null);
        }
      }
      return captured;
    } catch (error) {
      const guard = selectionGuardDetail(error);
      if (guard) {
        selectionContractSeen.current = true;
        selectionRef.current = null;
        setPile((p) => replaceSelectionToken(p, guard));
        setErr(errText(error));
      }
      // membership still settling behind a write: ask again in a moment rather than freeze on stale rows
      if (isCoveragePending(error)) setTimeout(() => loadPileRef.current?.(force), 1200);
      return null; /* the live event or safety timer will retry */
    }
    finally {
      pileFlight.current = null;
      if (pileForcePending.current && !resettingRef.current) {
        pileForcePending.current = false;
        queueMicrotask(() => loadPileRef.current?.(true));
      }
    } })();
    pileFlight.current = request;
    return request;
  }, []);
  useEffect(() => { loadPileRef.current = loadPile; }, [loadPile]);
  // FeedView's initial filter is the unfiltered JSON object below. Treat that as the
  // starting state instead of a change: otherwise mount starts the normal cached read,
  // then immediately queues a forced second rebuild for the exact same scope.
  const sharedFilter = useRef("{}");
  const inventoryFilterChanged = useCallback((filter) => {
    if (sharedFilter.current === filter) return;
    sharedFilter.current = filter;
    only.current = filter === '{}' ? null : `view:${filter}`;
    selectionRef.current = null;
    loadPileRef.current?.(true);
  }, []);
  useEffect(() => { currentRef.current = currentItem; }, [currentItem]);
  useEffect(() => { loadState().catch((e) => setErr(errText(e))); }, [loadState]);
  // Writes push an event and force one fresh rebuild. The timer is only a disconnected-socket
  // safety net: rebuilding this multi-source pile every five seconds starved Board, Tasks and
  // Past chats behind work whose answer had not changed.
  useEffect(() => pollWhileActive(active, () => loadPile(false), 30000), [active, loadPile]);
  // a sync lands rows several times a second; one forced rebuild after the burst, not one per row -
  // and a CEILING, because a run that keeps talking pushed the trailing timer out indefinitely and
  // left the pile on its 30-second safety poll (2026-09-10 audit).
  useEffect(() => {
    if (!active) return undefined;
    // ...and not at all when a forced load already began after the newest event: the turn that
    // caused the write reloaded the rows itself, and this was the fourth full build of one press
    return onLive(["feed-changed", "task-changed"], (ev, meta) => { if (!coveredByReload(meta, forcedLoadStartedAt.current)) loadPile(true); }, { wait: 1500, max: 5000 });
  }, [active, loadPile]);
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
  const canAdvance = canAdvanceSelection(pile, ready, only.current);
  // an alert about something already IN the conversation is noise: the card is right there
  const shownKeys = useMemo(() => new Set(msgs.slice(-8).map((m) => m.card?.key).filter(Boolean)), [msgs]);
  const pending = useMemo(() => pendingAlerts([...(pile?.alerts || []), ...notices], acked, currentItem, shownKeys), [pile, notices, acked, currentItem, shownKeys]);
  const alert = pending[0] || null;
  const say = useCallback((line) => { if (speakOnState) speak(line); }, [speakOnState]);
  useEffect(() => { speakRef.current = say; }, [say]);
  // The rail came WITH an answer - a turn's or a settle's - read on the server after that write. The
  // page holds it and captures Next from it under the scope it will press with, instead of asking for
  // the same rows again: a press of Next was two of those reloads at 1.5-2 s each, and the visible
  // gap between the old rows vanishing and the next four appearing (design B, 2026-09-17).
  const holdPile = useCallback((data, scope) => {
    forcedLoadStartedAt.current = heldSince(data);     // the live events this read already saw need no reload
    if (hasNextSelection(data)) selectionContractSeen.current = true;
    selectionRef.current = captureNextSelection(data, scope);
    setPile((p) => refreshPilePresentation(p, data));
  }, []);
  const landed = useCallback((data) => {
    if (data.exhausted && !only.current?.startsWith("view:")) only.current = null;            // the mail ran out: Next continues with the rest of the pipe
    const card = data.item ? { ...data.item } : null;
    setMsgs((m) => [...m, { id: `a${Date.now()}`, role: "assistant", text: data.say, options: data.options || [], card }]);
    currentRef.current = card;
    if (card) { setCurrent(card.key); setCurrentItem(card); } else { setCurrent(null); setCurrentItem(null); }
    say(data.say);
    // the turn brought the rail as it left it: hold that, with the new table excluded. Nothing along
    // (the walk ran out, an older server, the demo) is the page's own load, as before.
    if (card && data.pile) holdPile(data.pile, nextSelectionScope(only.current, card.key));
    else { selectionRef.current = null; loadPile(true); }
  }, [holdPile, loadPile, say]);

  const ensureNextSelection = useCallback(async (scope) => {
    for (let attempt = 0; attempt < 2; attempt += 1) {
      const captured = selectionRef.current;
      if (captured && sameSelectionScope(captured.scope, scope)) return captured;
      await loadPileRef.current?.(true);
    }
    const captured = selectionRef.current;
    return captured && sameSelectionScope(captured.scope, scope) ? captured : null;
  }, []);

  // pull the next thing (or the one named; or the next piece of mail) out of the pipe and say it
  const surface = useCallback(async (key = null, asUser = null, leaving = null) => {
    if (busy || resetting || handoff || turnFlight.current) return;
    turnFlight.current = true;
    setBusy(true); setErr("");
    const epoch = chatEpoch.current;
    const scope = nextSelectionScope(key ? null : only.current, key ? null : currentRef.current?.key || null);
    const capture = key ? null : await ensureNextSelection(scope);
    const activeScope = nextSelectionScope(key ? null : only.current, key ? null : currentRef.current?.key || null);
    const scopeMoved = !key && !sameSelectionScope(scope, activeScope);
    if (epoch !== chatEpoch.current || resettingRef.current || scopeMoved) {
      turnFlight.current = false;
      setBusy(false);
      // a new chat or a reset is the owner's own doing and stays quiet. The rail re-emitting under
      // a slow pile is NOT: this returned with no error and no message, and between 08:20 and
      // 08:47 on 2026-09-09 not one press reached the server while the button looked alive.
      if (scopeMoved) setErr((m) => m || "The list moved while that was loading - press it again.");
      return;
    }
    // A failed modern capture (including selection_unavailable) never becomes an optimistic owner
    // turn. The pile refresh already supplied the bounded error; a later explicit gesture retries.
    if (!key && selectionContractSeen.current && !capture) {
      setErr((message) => message || "Next is still refreshing. Review the updated list and press Next again.");
      turnFlight.current = false;
      setBusy(false);
      return;
    }
    const optimisticId = asUser ? `u${Date.now()}` : null;
    if (optimisticId) setMsgs((m) => [...m, { id: optimisticId, role: "user", text: asUser }]);
    try {
      // A named Timeline/pile row remains an explicit pull. Automatic Walk/Next echoes the exact
      // server capture; demo/old-server payloads alone retain the legacy tokenless fallback.
      const navigation = capture ? nextSelectionBody(capture) : scope;
      landed(await turn({ mode: "next", key, leaving, ...navigation }));
    } catch (e) {
      const guard = selectionGuardDetail(e);
      if (guard) {
        if (optimisticId) setMsgs((m) => m.filter((message) => message.id !== optimisticId));
        const freshCapture = captureNextSelection(guard, scope);
        selectionContractSeen.current = true;
        selectionRef.current = freshCapture;
        setPile((p) => replaceSelectionToken(p, guard));
        loadPile(true);                       // refresh the rows, never retry the navigation
      }
      setErr(errText(e));
    }
    turnFlight.current = false;
    setBusy(false);
  }, [busy, ensureNextSelection, handoff, landed, loadPile, resetting, turn]);
  useEffect(() => { surfaceRef.current = surface; }, [surface]);
  const startFlight = useRef(false);
  const start = async (what) => {
    if (busy || resetting || handoff || turnFlight.current || startFlight.current || starting) return;
    startFlight.current = true;
    const epoch = chatEpoch.current;
    const said = what === "mail" ? "Just what came in." : "Walk me through my tasks.";
    setStarting(true); setErr("");
    setMsgs((m) => [...m, { id: `u${Date.now()}`, role: "user", text: said }]);
    try {
      only.current = sharedFilter.current && sharedFilter.current !== "{}" ? `view:${sharedFilter.current}` : (pile?.canonical ? null : what);
      selectionRef.current = null;
      await loadPile(true);                   // validate/resume Current under the requested scope
      if (epoch !== chatEpoch.current || resettingRef.current) return;
      // the line is already on screen: surface must not post a second copy of it
      if (!currentRef.current) await surface(null, null);
    } catch (e) {
      // the owner's line is on screen now, so a failure has to be answered on screen too -
      // an unhandled rejection would leave "Walk me through my tasks." sitting there alone
      setErr(errText(e));
    } finally {
      startFlight.current = false;
      setStarting(false);
    }
  };

  // The day used to write itself the moment the page opened - a model call nobody asked for, which
  // also landed UNDER a "Set something up" the owner had already pressed (2026-09-03: "I hit new chat
  // to set something up and it ran the email walk through welcome command?"). The welcome block is the
  // door now: what is waiting, in facts, and the walk starts on a button.

  const send = async (line) => {
    const t = String(line ?? text).trim();
    if (!t || busy || resetting || handoff || turnFlight.current) return;
    turnFlight.current = true;
    setText(""); setBusy(true); setErr("");
    setMsgs((m) => [...m, { id: `u${Date.now()}`, role: "user", text: t }]);
    try {
      const ask = () => turn({ mode: "say", text: t, key: current, context_mid: currentItem?.mid || null });
      const data = await ask().catch(async (e) => { if (!isCoveragePending(e)) throw e; await new Promise((r) => setTimeout(r, 1200)); return ask(); });
      if (data.context_update && noticedRef.current !== data.context_update) {   // not already said by the stream event
        setMsgs((m) => [...m, { id: `context${Date.now()}`, role: "assistant", text: data.context_update }]);
        say(data.context_update);
      }
      noticedRef.current = null;
      if (data.item) landed(data);                       // the words pointed at something: it is on the table now
      else {
        const prop = proposalOf(data);      // a consequential decision arrives as a proposal to confirm (PW-123)
        setMsgs((m) => [...m, { id: `a${Date.now()}`, role: "assistant", text: data.say, options: data.options || [], chips: data.chips || [],
                                ...(prop ? { proposal: prop, card: { kind: "proposal", key: prop.key, title: prop.label, op: prop.id, tid: prop.tid, ref: prop.ref } } : {}) }]);
        say(data.say);
        if (prop?.auto) await runProposal(prop);                   // a plain verb on the item on the table: no button to press
        else if (!prop && data.decision) await decide(data.decision, data);  // the two immediate exceptions: a reply drafts, Next moves (PW-126/128)
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
  // the owner decided in words. Only two decisions still run without a confirmation (PW-126/128): a reply
  // request DRAFTS (nothing is sent, nothing is marked), and Next moves the walk without marking, closing
  // or deferring anything. Everything else arrives as a proposal card and runs from its button.
  const decide = async (d, data) => {
    const cur = d.target || [...msgs].reverse().find((m) => m.card && m.card.key === current)?.card || currentItem || null;
    const elsewhere = !!d.target;
    const mid = cur?.mid, verb = d.verb;
    try {
      // their yes (or no) to the card already on the table, said instead of clicked: the server ran it
      // before it answered, so the only thing left here is to stop the card saying "proposed" and move
      // the walk on if the item is off the table. Falling through to the receipt below announced a
      // failure over a success and left the walk sitting on finished work (2026-09-10 walk).
      if (verb === "confirm" || verb === "cancel") {
        setMsgs((m) => markExecuted(m, data?.executed));
        onChanged?.();
        if (data?.settled) advance(); else loadPile();
        return;
      }
      if (verb === "next") {
        // the capture is kept: the table did not change, so the token still names the pick the rail
        // shows - and the server takes anything else that moved fresh (processing_navigation.reserve)
        deferInChat(() => surfaceRef.current?.(), 300); return;
      }
      if (verb === "reply" && mid) {
        const { data } = await api.post(`/api/messages/${mid}/reply`, { draft: true, instruction: d.text || null });
        if (data.reviewId && !elsewhere) { setCurrent(null); deferInChat(() => surfaceRef.current?.(`review:${data.reviewId}`), 300); return; }
        loadPile(); return;
      }
      if (verb === "redraft" && cur?.rid && mid) {
        const { data } = await api.post(`/api/messages/${mid}/reply`, { draft: true, redraft: true, instruction: d.text || null });
        setMsgs((m) => [...m, { id: `r${Date.now()}`, role: "receipt", text: data.draft ? "Rewritten - read it below before you send it." : "I could not rewrite it here; edit the draft on the card and send that." }]);
        if (!elsewhere) { setCurrent(null); deferInChat(() => surfaceRef.current?.(`review:${cur.rid}`), 300); } else loadPile();
        return;
      }
      if (verb === "setting" || verb === "forwarded") { loadPile(); return; }   // Taskuary put these in Review itself
      setMsgs((m) => [...m, { id: `r${Date.now()}`, role: "receipt", tid: cur?.tid, ref: cur?.ref,
                              text: `That needs a confirmation card and none came back${cur?.ref ? ` - ${cur.ref} is untouched` : ""}. Say it again.` }]);
    } catch (e) { setErr(errText(e)); }
  };
  // the confirmation button (PW-124/125): the structured proposal by id and version - never a phrase sent
  // back through the interpreter. The receipt is what the server said happened; the walk moves only on a
  // success that settles the item on the table.
  const confirmProposal = async (p) => { if (!busy) await runProposal(p); };
  const runProposal = async (p) => {
    setBusy(true);
    try {
      let res;
      try { res = (await api.post(`/api/operations/${p.id}/execute`, { version: p.version })).data; }
      catch (e) { res = { status: e?.response?.status === 409 ? "stale" : "error", error: e?.response?.data?.detail || errText(e) }; }
      const out = afterExecute(p, res);
      const step = afterConfirm(p, out, current);
      // a sweep cleared what was on the table too: the receipt carries Next, and the walk waits for it
      const chips = step === "offer" ? [{ verb: "next", label: "Next" }] : [];
      setMsgs((m) => [...m.map((x) => (x.proposal?.id === p.id ? { ...x, proposal: { ...x.proposal, status: out.status, repo: out.repo || null, outcome: res?.outcome || null } } : x)),
                       { id: `r${Date.now()}`, role: "receipt", text: out.receipt, tid: p.tid, ref: p.ref, chips }]);
      onChanged?.();
      // the server already settled or closed the item; a settle proposal (later, tomorrow, done) must not be
      // re-marked "done" by the page, so it advances without the settle post. A hand-off that STARTED advances
      // once the same way (PW-135): the delegated task stays in Unread as Working, nothing is settled; a
      // repository still to choose, a failed start or a cancel keep the item where it is. A sweep that
      // cleared the table settled it too, but does NOT walk on: the table is put down and Next is offered.
      if (step === "advance") advance();
      else if (step === "settle") await done(null);
      else { if (step === "offer") clearTable(); loadPile(); }
    } finally { setBusy(false); }
  };
  // a card button on ONE entry (PW-151): the same proposal road the words take, minus the interpreter - the
  // target is explicit. The card lands in the chat and runs from its own button, like any proposal.
  const proposeDirect = async (verb, key, table = false) => {
    const { data } = await api.post("/api/concierge/propose", { verb, key, table });
    setMsgs((m) => [...m, { id: `a${Date.now()}`, role: "assistant", text: data.say, options: [], proposal: data,
                            card: { kind: "proposal", key: data.key, title: data.label, op: data.id, tid: data.tid, ref: data.ref } }]);
    say(data.say);
    return data;
  };
  // Get me ready for this meeting: a conversation with the assistant, no checkout (server: calendar/prep)
  const prep = async (item) => {
    const e = item?.event || {};
    const { data } = await api.post("/api/calendar/prep", { ...e, instruction: "Get me ready for this meeting: who is in it, what came before it, what I should say." });
    setMsgs((m) => [...m, { id: `r${Date.now()}`, role: "receipt", tid: data.taskId, ref: data.ref,
                            text: `${data.ref} - prep is open as its own conversation with the assistant.` }]);
    advance();
  };
  // ONE road for every action word in the chat. A word the assistant offered is a word that runs: the
  // verb goes to the same proposal endpoint a card button uses, with the target explicit. The two that
  // are not proposals keep their own immediate behaviour - a reply DRAFTS (PW-126), Next moves the walk
  // and puts down what it left. An OPTIONS choice is not a verb at all: it goes back as the owner's words.
  const runChip = async (c) => {
    if (busy || resetting || handoff || !c) return;
    if (c.ask) { send(c.ask); return; }
    const item = currentRef.current || currentItem;
    const key = item?.key || current;
    if (c.verb === "next") { surface(null, null, key); return; }
    if (c.verb === "reply" || c.verb === "redraft") { await decide({ verb: c.verb }); return; }
    setBusy(true); setErr("");
    try {
      if (c.verb === "prep") await prep(item);
      else if (c.verb === "followup") {
        const out = await api.post("/api/concierge/act", { key, verb: "followup" });
        setMsgs((m) => [...m, { id: `r${Date.now()}`, role: "receipt", text: "Follow-up drafted - it waits for your yes.", tid: out.data?.taskId }]);
        advance();
      } else {
        const pr = await proposeDirect(c.verb, key, true);
        if (pr?.auto) await runProposal(pr);
      }
    } catch (e) { setErr(errText(e)); } finally { setBusy(false); }
  };
  // a dry run of a proposed report (PW-195): the server refuses anything that could write
  const previewProposal = async (p) => (await api.post(`/api/operations/${p.id}/preview`)).data;
  const cancelProposal = async (p) => {
    try { await api.delete(`/api/operations/${p.id}`); } catch { /* it may be gone already */ }
    const out = afterCancel(p);
    setMsgs((m) => [...m.map((x) => (x.proposal?.id === p.id ? { ...x, proposal: { ...x.proposal, status: out.status } } : x)),
                     { id: `r${Date.now()}`, role: "receipt", text: out.receipt, tid: p.tid, ref: p.ref }]);
  };
  // a card did its thing: say so in the thread, then move on
  // the table is put down - nothing is chosen in its place. Walking on is advance(), which is this
  // plus asking for the next thing; a sweep does only this and leaves Next to the owner's finger.
  const clearTable = () => {
    currentRef.current = null; selectionRef.current = null;
    setCurrent(null); setCurrentItem(null);
  };
  const advance = (pile = null) => {
    clearTable();
    onChanged?.();                                     // a draft may have gone out: the Review badge recounts
    // a settle that brought the rail back with it: held under the empty table's scope, and the walk needs
    // no half-second of grace - the server has settled already, and the timer only has to outlive this
    // render (a proposal's busy flag is released the moment its caller returns)
    if (pile) holdPile(pile, nextSelectionScope(only.current, null));
    deferInChat(() => surfaceRef.current?.(), pile ? 120 : 500);
  };
  const done = async (receipt) => {
    if (receipt) setMsgs((m) => [...m, { id: `r${Date.now()}`, role: "receipt", text: receipt }]);
    let pile = null;
    // `only` rides along so the rail comes back captured under the scope this page walks with
    if (current) { try { pile = (await api.post("/api/funnel/settle", { key: current, verb: "done", only: only.current })).data?.pile || null; } catch { /* it may already be gone */ } }
    advance(pile);
  };
  // Setting Taskuary up: the scripted walk, one stop per message so the conversation keeps the
  // trail. Nothing here reaches a model - a question typed during it is an ordinary turn, answered
  // beside the walk, and Next picks the script back up where it was.
  // TWO THINGS ARE CALLED "walk" IN THIS FILE. This set - pushStop/setup/walkTo/walking/
  // walkAdvances - is the SCRIPTED TOUR of the app: static stops, no AI, no task behind it.
  // `enterWalk`/`setWalk`/`walk` further down is the AI-LED WALK-THROUGH of one task, which opens
  // GeneralWorkspace on a real session. They share nothing but the word.
  const pushStop = (data) => {
    const stop = (data.stops || [])[data.at];
    if (!stop) return;
    setMsgs((m) => [...m, { id: `w${Date.now()}`, role: "assistant",
      card: { ...stop, kind: "walk", lane: "report", total: data.total }, options: [] }]);
  };
  // A stop that did its work in place re-reads itself, so the tick lands on the card you are looking
  // at rather than waiting for the next press. It patches THAT message by id and pushes nothing: a
  // second card for a step you just finished would read as the walk going backwards.
  const walkSaved = async (id) => {
    try {
      const { data } = await api.get("/api/setup/walk");
      setMsgs((m) => m.map((x) => {
        if (x.id !== id || !x.card) return x;
        const fresh = (data.stops || []).find((s) => s.key === x.card.key);
        return fresh ? { ...x, card: { ...fresh, kind: "walk", lane: "report", total: data.total } } : x;
      }));
    } catch { /* the card stays as it is; the save itself already succeeded */ }
  };
  // ...and the OTHER door, which this walk took the name of: "set something up" - a report, a
  // connection, an automation - is the assistant's own walk-through of a thing you describe. The
  // scripted walk inherited the identifier `setup` and with it the welcome block's button, so the
  // chip still reading "Set up a report or workflow" opened the fourteen-stop tour of the app.
  const askSetup = () => setMsgs((m) => [...m, { id: `a${Date.now()}`, role: "assistant", text: "Tell me what to set up - a report, a connection, an automation - in a sentence. I open it as a walk-through with the assistant: it takes you through it here, nothing is built and no repository is touched. If something does have to be built, say send it to the coding agent.",
    card: { key: "setup", kind: "setup", lane: "report", title: "Set something up" }, options: [] }]);
  const [walking, setWalking] = useState(false);        // guards the chip against a double-click
  const setup = async () => {
    if (walking) return;
    setWalking(true);
    try { pushStop((await api.get("/api/setup/walk")).data); }
    catch { setMsgs((m) => [...m, { id: `w${Date.now()}`, role: "receipt", text: "The walk could not be loaded." }]); }
    finally { setWalking(false); }
  };
  // -1 is Finish: walking off the end clears the place server-side, so the next press starts over.
  // The same guard as the chip: Next is a POST, so a double-press moved the place twice and pushed
  // two stop cards into the conversation.
  const walkTo = async (at) => {
    if (walking) return;
    setWalking(true);
    try {
      const { data } = await api.post("/api/setup/walk", { at });
      if (walkAdvances(at, data.total)) pushStop(data);
      else setMsgs((m) => [...m, { id: `w${Date.now()}`, role: "receipt",
        text: "Walk finished — “Set up Taskuary” starts it again any time." }]);
    } catch { /* the card stays where it is; nothing was lost */ }
    finally { setWalking(false); }
  };
  // Start over: the server's reset (place -> 0), then the first stop as a fresh card. Not walkTo(0):
  // that is a move to stop 1 from wherever you were, and the receipt trail would read as one.
  const walkRestart = async () => {
    if (walking) return;
    setWalking(true);
    try { pushStop((await api.post("/api/setup/walk/reset")).data); }
    catch { /* the card stays where it is */ }
    finally { setWalking(false); }
  };
  // The walk's task, fetched once so GeneralWorkspace has the row it needs (it owns everything
  // after that: the session, the provider, the browser beside the thread).
  const enterWalk = async ({ tid, ref, title }) => {
    try {
      const { data } = await api.get(`/api/tasks/${tid}`);
      setWalk({ tid, ref, title: title || data.task?.Title || "", task: data.task });
      try { localStorage.setItem(WALK_KEY, String(tid)); } catch { /* private mode */ }
    } catch (e) { setErr(errText(e)); }
  };
  // Leaving puts the WALK down, never the task: the session keeps whatever it was doing and the
  // row is on the Board. This is a change of what this pane is showing, so it asks the server for
  // nothing (PW-166 - a background update reaches the table by the owner's own navigation).
  const leaveWalk = () => {
    setWalk(null);
    try { localStorage.removeItem(WALK_KEY); } catch { /* private mode */ }
  };
  // A reload does not abandon the walk. The id is all this browser kept; the TASK says whether it
  // is still one - closed, dropped or reopened as something else and this shows the chat instead.
  useEffect(() => {
    let live = true;
    let tid = null;
    try { tid = localStorage.getItem(WALK_KEY); } catch { /* private mode */ }
    if (!tid) return undefined;
    api.get(`/api/tasks/${tid}`).then(({ data }) => {
      if (!live) return;
      if (isOpenWalk(data.task)) setWalk({ tid: Number(tid), ref: data.task.Ref || `TQ-${String(tid).padStart(4, "0")}`, title: data.task.Title, task: data.task });
      else try { localStorage.removeItem(WALK_KEY); } catch { /* private mode */ }
    }).catch(() => { try { localStorage.removeItem(WALK_KEY); } catch { /* private mode */ } });
    return () => { live = false; };
  }, []);
  const handOff = async (text) => {
    if (!text.trim() || busy) return;
    setBusy(true); setErr("");
    setMsgs((m) => [...m, { id: `u${Date.now()}`, role: "user", text }]);
    try {
      const { data } = await api.post("/api/concierge/setup", { text });
      // ...and we STAY here, and the walk STARTS here. Opening the task yanked the owner off the
      // Assistant tab the moment they asked for a walk-through (the 2026-09-03 break test) - so it
      // stopped navigating, and then nothing walked them at all: a cold row and "open it when you
      // want to start" (the owner, 2026-09-10: "it's supposed to walk me through this?"). The
      // conversation binds to that task's own session instead. Its browser comes with it, and
      // leaving the walk is a button, not a navigation.
      setMsgs((m) => [...m, { id: `r${Date.now()}`, role: "receipt", tid: data.taskId, ref: data.ref,
                              text: `${data.ref} — "${data.title}". The walk is below; nothing is built and no repository is touched.` }]);
      enterWalk({ tid: data.taskId, ref: data.ref, title: data.title });
    } catch (e) { setErr(errText(e)); }
    setBusy(false);
  };
  // Later puts the NOTICE down, not the item or the task behind it; Open is the owner's own navigation to it
  // (PW-166) - the one road by which a background update ever reaches the table
  const ack = async (a, go) => {
    setAcked((s) => new Set([...s, a.key]));
    if (!a.local) api.post("/api/funnel/settle", { key: a.key, verb: "ack" }).catch(() => {});
    if (go) surface(a.item, `Open — ${a.text}`);
  };
  // past chats are read, a page at a time (PW-157): listing them changes nothing on the server
  const [chatsNext, setChatsNext] = useState(null);
  const openChats = async () => {
    setChatsOpen(true); setChatsLoading(true);
    try { const { data } = await api.get("/api/concierge/chats", { params: { limit: 25 }, timeout: 10000 }); setChats(data.data || []); setChatsNext(data.next || null); }
    catch (e) { setErr(errText(e)); }
    setChatsLoading(false);
  };
  const moreChats = async () => {
    if (!chatsNext) return;
    setChatsLoading(true);
    try { const { data } = await api.get("/api/concierge/chats", { params: { limit: 25, before: chatsNext }, timeout: 10000 }); setChats((c) => [...c, ...(data.data || [])]); setChatsNext(data.next || null); }
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
    only.current = sharedFilter.current && sharedFilter.current !== "{}" ? `view:${sharedFilter.current}` : null;
    currentRef.current = null;
    selectionRef.current = null;
    setMsgs([]); setText(""); setWork([]); setErr(""); setAcked(new Set()); setNotices([]);
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
  // The walk, taken to a chat you already have connected (WhatsApp, Telegram). This is not a way to
  // CONNECT one - a chat with no Assistant card offers nothing here (the owner, 2026-09-07: "point is
  // to talk to assistant through it not connect it"). While it is there the tab locks itself: two
  // screens answering the same item is how the same mail gets replied to twice.
  const handOver = async (d) => {
    if (busy || resetting || handoff) return;
    setBusy(true); setErr("");
    try { await api.post("/api/concierge/handoff", { channel: d.channel }); await loadState(); }
    catch (e) { setErr(errText(e)); } finally { setBusy(false); }
  };
  const takeBack = async () => {
    setBusy(true); setErr("");
    try { await api.post("/api/concierge/handoff/end"); await loadState(); }
    catch (e) { setErr(errText(e)); } finally { setBusy(false); }
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
  const pullOrOpen = (key, asUser, openByMid, openByItem) => {
    // ...and an entry of the batch on the table, which is drawn on the rail but is not a pile row
    const it = (pile?.items || []).find((i) => i.key === key)
      || (currentItem?.items || []).find((i) => i.key === key);
    if (stageMode === "task") {
      // A MESSAGE opens on the stage. Anything else with a TASK behind it opens the task: an agent
      // row, a meeting's prep, a proposal - none of them carry a mid (funnel.from_agents,
      // from_calendar, from_proposals build items without one), so Task mode fell straight through
      // to the chat and the owner got a conversation about the very thing they had just asked to
      // open (the owner, 2026-09-16: "task button on the assistant, if i click it then hit a item
      // the chat pops up not the actual task"). Only a row with neither - a bare meeting - has
      // nothing to open, and talking about it is the right answer there.
      if (it?.mid && openByMid?.(it.mid)) { setRailOpen(false); return; }
      // no message, but the canonical item can still be asked about itself - a task, an idea, a
      // review - and that is what the stage draws. It is the same pane the Timeline gives these.
      const pid = it?.processing_id || (key.startsWith("processing:") ? key.slice("processing:".length) : "");
      const target = it?.tid ? { kind: "task", id: it.tid } : it?.rid ? { kind: "review", id: it.rid } : null;
      if (pid && target && openByItem?.(pid, target)) { setRailOpen(false); return; }
      // ...and on a legacy install, where there is no canonical item to ask, the task itself
      if (it?.tid && onOpenTask) { onOpenTask(it.tid); setRailOpen(false); return; }
    }
    pull(key, asUser);
  };

  const actions = { done, start, handOff, openTask: onOpenTask, timeline, navigate: onNavigate,
    walk: walkTo, walkSaved, walkRestart, chip: runChip, busy: busy || resetting || !!handoff,
    confirm: confirmProposal, cancel: cancelProposal, propose: proposeDirect, preview: previewProposal,
    surface: (key, note) => {
      if (note) setMsgs((m) => [...m, { id: `r${Date.now()}`, role: "receipt", text: note }]);
      deferInChat(() => key ? surfaceRef.current?.(key) : loadPileRef.current?.(), 900);
    } };
  const shown = old ? old.messages : msgs;
  const handedTo = handoff ? (state?.doorways || []).find((d) => d.channel === handoff.channel) : null;
  const lastCardIdx = useMemo(() => interactiveCardIndex(shown), [shown]);
  const lastSaidIdx = useMemo(() => lastSaidIndex(shown), [shown]);

  const chat = (
    <div className="tq-asst-col" style={{ position: "relative", flex: 1, minHeight: 0 }}>
      <div className="tq-chat-head">
        <Box sx={{ width: 30, height: 30, borderRadius: 2, background: "linear-gradient(90deg, #55697a, #7d9a7c)", display: "grid", placeItems: "center", flexShrink: 0 }}><TaskuaryMark size={22} /></Box>
        <div className="who" style={{ minWidth: 0 }}><b>Taskuary</b><span>{old ? `An earlier chat · ${fmtDateTime(old.at)}` : resetting ? "new chat" : !pile ? "Loading your items…" : statusLine(items, busy)}</span></div>
        <div className="grow" />
        {/* Setting Taskuary up is not a first-run-only wizard (PW-189): the entry stays on the header, and it
            opens the scripted walk in THIS conversation - nothing is navigated away from, and nothing here
            is a phrase for an AI to interpret, since none may be connected yet when this gets pressed. */}
        <Tooltip title="A walk through every part of Taskuary — one step at a time, no AI needed">
          <button type="button" className="tq-chip tq-phone-hide" disabled={busy || resetting || walking} onClick={setup}>Set up Taskuary</button></Tooltip>
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
            {chatsNext && !chatsLoading && <button type="button" className="tq-chip" style={{ margin: 8 }} onClick={moreChats}>Earlier chats</button>}
          </div>
        </div>
      )}
      {/* the set-up walk, running in this pane: the task's own conversation, with its browser beside
          it (GeneralWorkspace/SessionPane). The chat underneath is kept, not replaced - Leave puts
          the walk down and the conversation is where it was. */}
      {!old && walk && (
        <>
          <div className="tq-handed" role="status">
            <TaskuaryMark size={17} />
            <div className="txt"><b>Walking you through {walk.ref}</b>
              <span>{walk.title}. Nothing is built and no repository is touched; its browser opens beside this conversation.</span></div>
            <button type="button" className="tq-chip" onClick={leaveWalk}>Leave the walk</button>
          </div>
          <div className="tq-walk"><GeneralWorkspace task={walk.task} compact /></div>
        </>
      )}
      {!walk && (
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
                <button type="button" className="tq-chip primary" disabled={busy || resetting || starting || !canAdvance} onClick={() => start(null)}
                  title="Everything in the pipe, most important first - mail, reports, agents, meetings">{starting ? "Reading your pipe..." : "Walk me through my tasks"}</button>
                {!pile?.canonical && <button type="button" className="tq-chip" disabled={busy || resetting || starting || !incoming(ready).length} onClick={() => start("mail")}
                  title="Only what people sent you - mail and chat">Just what came in</button>}
                {/* the same walk the header chip opens. It lives here as well because the header
                    hides its chip on a phone, and this block is what a phone shows - without it the
                    one door to the set-up guidance was absent on the device it is most needed on. */}
                <button type="button" className="tq-chip" disabled={busy || resetting || walking} onClick={setup}
                  title="A walk through every part of Taskuary — one step at a time, no AI needed">Set up Taskuary</button>
                <button type="button" className="tq-chip" disabled={resetting} onClick={askSetup}
                  title="A scheduled check that reads and summarises, or a workflow that writes data">Set up a report or workflow</button>
                {/* the same walk, on your phone - offered only for a chat that is already connected and
                    names an Assistant chat, because this talks to the assistant, it does not set one up */}
                {(state?.doorways || []).map((d) => (
                  <button key={d.channel} type="button" className="tq-chip tq-chip-chat" disabled={busy || resetting || !canAdvance}
                    onClick={() => handOver(d)} title={`I say hello in ${d.name} and take you through the same items there; this tab locks until you take it back`}>
                    <ChannelIcon channel={d.channel} sx={{ fontSize: 14 }} />
                    Walk me through them in {d.label}
                  </button>
                ))}
              </div>
            </div>
          )}
          {shown.map((m, i) => <Line key={m.id} m={m} live={!old && i === lastCardIdx} last={!old && i === lastSaidIdx}
                                     actions={actions} fresh={currentItem} />)}
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
      )}
      {/* Unfinished work from before, with its own recap - listed, never resumed by arriving here
          (previous-work.test.mjs: "Loading the welcome card never starts an agent"). It is a LABEL
          along the bottom, not a shelf above the conversation: on top it pushed the walk off the
          screen (the owner, 2026-09-17), and inside the welcome card it would unmount the moment a
          line lands in the chat - reviewing one saved draft puts a line there, which took the shelf
          away with the rest of the list still on it. It draws nothing when there is nothing saved. */}
      {state && !old && !handoff && !walk && <PreviousWork active={active} onOpenTask={onOpenTask}
        onReview={(rid) => surfaceRef.current?.(`review:${rid}`)} />}
      {/* ONE bottom strip for every unsolicited update (PW-165), kept until Open or Later (PW-166); the rest of
          the queue waits behind it and comes up as each is put down */}
      {/* while the walk is in a chat the interruption is SENT there (remote_assistant.push_alerts);
          a strip on the locked tab would only be a button that cannot act */}
      {alert && !old && !handoff && !walk && (
        <div className="tq-btw" role="status">
          <span className="dot" /><div className="txt"><b>By the way —</b>{alert.text}.{pending.length > 1 ? ` (+${pending.length - 1} more)` : ""}</div>
          <button type="button" className="tq-chip primary" onClick={() => ack(alert, true)}>{alert.item === current ? "Open the update" : current ? "Switch to it" : "Open"}</button>
          <button type="button" className="tq-chip" onClick={() => ack(alert, false)}>Later</button>
        </div>
      )}
      {/* the walk is on the phone: this tab does not get to answer the same item (the owner, 2026-09-07:
          "make the desktop unavailable if sent to whatsapp otherwise it's confusing") */}
      {!old && handoff && (
        <div className="tq-handed" role="status">
          <ChannelIcon channel={handoff.channel} sx={{ fontSize: 17 }} />
          <div className="txt"><b>The walk is in {handedTo?.label || handoff.channel}</b>
            <span>Answer me there and I keep going. This chat waits so the same thing is not answered twice.</span></div>
          <button type="button" className="tq-chip primary" disabled={busy} onClick={takeBack}>Take it back</button>
        </div>
      )}
      {!old && !handoff && !walk && (
        <div className="tq-compose">
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
          <div className="tq-compose-hint">Enter sends · Shift+Enter adds a line · click a row on the left to pull it in · the words under each message do the acting</div>
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
      onInventoryFilter={inventoryFilterChanged} unreadInventory={pile}
      top={({ openByMid, openByItem }) => <Pile pile={pile} current={old ? null : currentItem}
        onPull={(key, asUser) => pullOrOpen(key, asUser, openByMid, openByItem)} />}
      stage={stageMode === "chat" ? chat : placeholder} rowMode={stageMode}
      onPull={(r) => pull(keyForRow(r), `Tell me about “${r.Subject || r.Title || "this"}”`)}
      railOnNarrow={railOpen} />
  );
}
