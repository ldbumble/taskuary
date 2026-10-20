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
import { workingLine } from "./agentWork.js";
import { Box, CircularProgress, IconButton, MenuItem, Popover, Select, Tooltip, Typography, useMediaQuery } from "@mui/material";
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
import { runOperation } from "./taskOps.js";
import { openReply } from "./replyDraft.js";
import { DEMO } from "./demoApi.js";
import { lazyView } from "./lazyView.jsx";
import { loadGeneral } from "./lazyGeneral.js";
// the static demo's guided journey: nothing outside the demo build ever draws it, so nothing there fetches it
const DemoJourney = DEMO ? lazyView(() => import("./DemoJourney.jsx")) : () => null;
import { advisedIn, onPressed, onPressing, press as pressRow, rowNow, useHosted, useRowVerbs, useVerbs } from "./actionRow.js";
import { hint as btnHint, label as btn, liveVerb, verbOfRow } from "./buttons.js";
import { readNdjson, toolTarget } from "./assistantStream.js";
import { pollWhileActive } from "./visible.js";
import { liveUp, onLive } from "./live.js";
import { adviceKeyFor, adviceShown } from "./advice.js";
import { Md, looksMd } from "./md.jsx";
import { ChannelIcon, MicButton, TaskuaryMark, fmtDateTime, fmtTime12 } from "./ui.jsx";
// TASKUARY'S MARK IN THE CHAT (the owner, 2026-09-28: "the taskuary logo is blue and very obvious ... you can change the
// taskuary logo ... at least how it shows in the assistant"): its six-point star drawn in Taskuary's sage, outlined like
// the avatars on its cards - the bright tile repeated on every line shouted over the card it introduced
// the speaker's mark is TASKUARY'S OWN LOGO, never a second drawing of it (the owner, 2026-10-06: "logo should match the
// taskuary one not a different one")
const AssistantMark = () => <TaskuaryMark size={24} />;
import { BORDER, DIM, FAINT, INK, LEVEL_COLOR, LEVEL_TINT, ROLES } from "./theme.jsx";
import { railShort } from "./batchItems.js";
import ProposalCard from "./ProposalCard.jsx";
import { adviceRead, tableOf, tableWords } from "./tableState.js";
import { ReportLink } from "./BugReportDialog.jsx";
import { openBugReport, shownError } from "./bugReportOpen.js";
import { RemindPicker } from "./RemindMe.jsx";
import { agentOpen } from "./taskFilter.js";
import ContinueBox from "./ContinueBox.jsx";
import CloseNote from "./CloseNote.jsx";
import { AttachImage, ImageTray, usePromptImages } from "./promptImages.jsx";
import { afterCancel, afterConfirm, afterExecute, holdsProposal, markExecuted, proposalSay } from "./proposalCard.js";
import { LEVEL_META, LEVEL_ROLE, arrivals, asPressed, attentionBand, bandsOf, canAdvanceSelection, captureNextSelection, cardFor, currentItemFromPile, displayRevision, drawOrder, fillCaps, followsItem, foldsAs, hasNextSelection, interactiveCardIndex, keysOf, lastActIndex, chipsOf, receiptChips, CAPPED, FLOOR, FOOT_PX, levelLabel, nextMarkerKey, trimCaps, ROW_PX, nextSelectionBody, nextSelectionScope, refreshCurrentPresentation, refreshPilePresentation, replaceSelectionToken, rowMeta, sameSelectionScope, selectionGuardDetail, settledHistory } from "./funnelPile.js";
import { FYI_PAGE, coveredByReload, fyiTail, heldSince, pileRows, sentChips } from "./funnelPile.js";
import { isCoveragePending } from "./processingAll.js";
import { mergeDurableTurns, pickLine, placeLine } from "./assistantTurns.js";
import { lightOf, litAfter, litPick, litPull } from "./assistantLight.js";
import DigestText from "./DigestText.jsx";
import { firstAppLink, openAppLink, recordPlace } from "./appLinks.js";
import { hashFor } from "./canvasLinks.js";
import { useCapabilities } from "./capabilities.js";
import { place } from "./words.js";
// FirstRun, the walk's workspace and the browse cards are drawn after the pile or a click, never on the first frame: out of the entry chunk
const FirstRun = lazyView(() => import("./FirstRun.jsx"));
import SetupSteps from "./SetupSteps.jsx";
import SetupLine from "./SetupLine.jsx";
import { BriefCard, CardNav, DayOpener, FyisCard, IdeaCard, MeetingCard, MessageCard, ReplyCard, ReportCard, SetupCard, SourceMark, WalkCard, sourceColor } from "./assistantCards.jsx";
import { summarize } from "./walkSummary.js";
import { refreshToday, useCalendarToday } from "./calendarToday.js";
import FeedView from "./FeedView.jsx";
import { MORE_PX, backAt, dueWord, placed, pulledRow, sectionDone, sectionNext } from "./funnelPile.js";
import { age, ago, band, bandUntil, plural } from "./timeWords.js";
const GeneralWorkspace = lazyView(loadGeneral);
import CanvasItem, { CANVAS_ITEM_HEIGHT, showsTask } from "./CanvasItem.jsx";
import ActionRow, { AdviceNone, AdvisorNext } from "./ActionRow.jsx";
import { floorOf } from "./inView.js";
const CanvasBrowse = lazyView(() => import("./CanvasBrowse.jsx"));
import { ROADS, roadOfCard } from "./timelineState.js";
import { walkAdvances } from "./walkStep.js";
import { fmtDate, fmtTime } from "./dates.js";
import { noteWrite } from "./wrote.js";
import { revealRing } from "./railReveal.js";
import "./assistantView.css";

// Which walk-through this tab was in. Per-browser and deliberately thin - one task id - because the
// walk itself lives on the server: a reload asks the task whether it is still an open set-up before
// showing anything, so a stale key restores nothing.
const WALK_KEY = "taskuary_walk_tid";
const isOpenWalk = (t) => !!t && t.SourceRef === "assistant:setup" && !["done", "dropped"].includes(t.Status);
// markers the server writes on a line that are NOT cards (concierge.SETUP_QUESTIONS): the line is its words
// ...and a line that carries its own words (concierge: a failed act's way on, the already-seen opens): never an item card
const NOTE_KINDS = new Set(["setup_questions", "words"]);

// what a PERSON sent, whatever lane it landed in (funnel.came_in): a slipped follow-up about a mail
// is still mail, and the walk that skipped it said "0 of them are mail" with five in the pipe

// WHAT THE HEADING ALREADY SAID. A row speaks only when its own word ADDS something: "slipped"
// under fyi does, "fyi" under fyi does not, and "agent finished" under agents working does -
// because the band says they are still going (the owner, 2026-09-16: "show emoji if it says
// something besides for what lane it's in"). Compared on the WORD, not the lane, so a kind that
// overrides its lane's word - agentdone, wrapup - is judged on the word it actually shows.
const BAND_SAYS = { reports: "report", fyi: "fyi", agents: "agent working" };
const CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳";   // a ranked row's place in its batch (HEAD_RANGE tops out at 20)
const ROW_H = 33, CUR_H = 57;   // a Timeline row (30px + its 3px gap); the current one opens up to two lines
const BATCH_TAIL = 13;          // the gap a bracket leaves under itself for its own label
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
  if (demoNo(e)) DEMO_SAID.add(demoNo(e));
  return (typeof detail === "string" ? detail : null) || e?.message || "Taskuary could not answer.";
};
// THE DEMO SAYING NO (U8, 2026-10-17): a refusal is the demo speaking, so it is posted as a plain line of its own - it came in
// red with "Report this bug" under it, as if the app had broken. setErr below routes any sentence in this set to the chat.
const DEMO_SAID = new Set();
const demoNo = (e) => (e?.response?.status === 403 && e.response.data?.demo ? String(e.response.data.detail || "This is the demo - nothing is sent.") : "");
// what an empty rail offers: the same doors as the welcome block (runChip knows these three)
const IDLE_CHIPS = [{ verb: "newtask", label: btn("new_task") }, { verb: "setupask", label: "Set something up" }, { verb: "tour", label: "Change my setup" }];   // not a second "set up" beside "Set something up" (U14)
// THE AI POPOVER, from what is connected (J): it named "your coding tool" to people with none, and "chosen elsewhere" with no way there
export const AI_DEFAULTS = place("ai_defaults").href;
export const aiSays = (providers = []) => {
  const acts = providers.some((p) => p.type === "cli"), talks = providers.some((p) => p.type !== "cli" && p.type !== "demo");
  if (!acts && !talks) return "No AI is connected yet, so I can only offer the buttons. Connect one and I can take instructions in words.";
  return ["The AI picked here answers you in this chat.", acts && "One that runs on this computer can also look things up and rerun reports for you.",
    talks && "One connected as an online service answers faster but only talks.", "The agents that do the work have their own settings."].filter(Boolean).join(" ");
};
const speakOn = () => { try { return localStorage.getItem("taskuary_speak") === "1"; } catch { return false; } };
const speak = (text) => {
  if (!text || typeof window === "undefined" || !window.speechSynthesis) return;
  try { window.speechSynthesis.cancel(); const u = new SpeechSynthesisUtterance(text.replace(/[*_#`>]/g, "")); u.rate = 1.05; window.speechSynthesis.speak(u); } catch { /* no voice on this box */ }
};
// the pile's key for a Timeline row, so any row on the rail can be pulled into the chat - the same
// key the pipe itself carries, so the server puts the same item on the table either way
export const keyForRow = (r) => r.ReviewStatus === "pending" && r.ReviewId ? `review:${r.ReviewId}`
  : r.AgentWaiting && r.TaskId ? `agent:${r.TaskId}` : !r.MessageId && r.TaskId ? `task:${r.TaskId}`   // a search hit on a task: never msg:undefined
  : r.Channel === "report" ? `report:${r.MessageId}` : `msg:${r.MessageId}`;

// THE DAY'S ROOM, HELD (2026-10-20): the meetings, the counts and the since-line land moments after the Walk row draws, and
// each pushed it down under a reaching pointer. While any of them is still loading, the region above the row keeps the height
// it settled at last time at this width - this browser's memory, so a first load has none and draws as before. Settled, the
// region is its own height again, and the page looks exactly as it did.
const DAY_H = "taskuary_day_height";
const dayHeights = () => { try { return JSON.parse(window.localStorage.getItem(DAY_H) || "{}") || {}; } catch { return {}; } };
function DayHold({ loading, children }) {
  const ref = useRef(null), today = useCalendarToday(), settled = !loading && !!today;
  useLayoutEffect(() => {
    const el = ref.current, w = () => String(Math.round(el.clientWidth / 10) * 10);
    if (!el) return undefined;
    if (!settled) { const h = dayHeights()[w()]; el.style.minHeight = h ? `${h}px` : ""; return undefined; }
    el.style.minHeight = "";
    const save = () => {
      const { [w()]: _, ...rest } = dayHeights();   // newest last, a handful of widths kept
      try { window.localStorage.setItem(DAY_H, JSON.stringify(Object.fromEntries([...Object.entries(rest).slice(-7), [w(), el.offsetHeight]]))); } catch { /* memory only */ }
    };
    save();
    const ro = new ResizeObserver(save); ro.observe(el);
    return () => ro.disconnect();
  }, [settled]);
  return <div ref={ref} className="tq-day-hold">{children}</div>;
}

// ── the pipe: the top of the rail ────────────────────────────────────────────────────────────
// An assistant that has just woken up says hello like one (the owner, 2026-09-04: "it should be
// good morning/afternoon or whatever it is and should say how can i help").
// WHAT ALREADY HAPPENED, under the tiles that say what waits (the row-bot comparison, 2026-10-07): the mail read and filed,
// the reports that ran, the agents that finished, and what was learned this week - counted on the server, no model, so the
// opening screen never waits on one. Nothing to say says nothing.
function SinceBlock({ onOpen, onReading }) {
  const [d, setD] = useState(null);
  const [open, setOpen] = useState(false);
  const [writing, setWriting] = useState("");
  const read = useCallback(() => api.get("/api/since").then(({ data }) => { setD(data); return data; }), []);
  useEffect(() => { let live = true; read().catch(() => {}); return () => { live = false; }; }, [read]);
  // read once on mount, it kept the counts from before the startup catch-up had read a message (B5, 2026-10-11)
  useEffect(() => onLive(["arrive"], () => { read().catch(() => {}); }), [read]);
  const o = d?.overnight || {}, cards = d?.cards || [], dg = d?.digest || {};
  // LOADING, NOT MISSING (the owner, 2026-10-14: "put the digest right away on load and the numbers ... in loading mode"): while
  // the launch still reads the mail or writes the digest, the card says so and reads again until both are in
  const pending = !d || d.reading || dg.writing;
  useEffect(() => { onReading?.(!d || !!d.reading); }, [d, onReading]);
  useEffect(() => { if (!d || !pending) return undefined; const id = setTimeout(() => read().catch(() => {}), 4000); return () => clearTimeout(id); }, [d, pending, read]);
  // ...and THE DIGEST OPENS FOLDED: the day's card is the view, "See the full digest" opens it (the owner, 2026-10-16: "the morning
  // digest should open closed not open so this is the view") - only Write a fresh one, asked for, opens it by itself
  // "Write a fresh one" runs the report now (about twenty seconds) and the folded line follows it until the new one is in
  const fresh = async () => {
    if (!dg.source_id || writing.startsWith("Writing")) return;
    const was = dg.at;
    setWriting("Writing a fresh one…");
    try { await api.post(`/api/reports/${dg.source_id}/rerun`); }
    catch (e) { setWriting(`It could not start - ${errText(e)}`); return; }
    for (let i = 0; i < 30; i += 1) {
      await new Promise((r) => setTimeout(r, 4000));
      const now = await read().catch(() => null);
      if (now?.digest?.at && now.digest.at !== was) { setWriting(""); setOpen(true); return; }
    }
    setWriting("Still writing - it lands here when it's done.");
  };
  const counts = [[o.mail, "came in"], [o.reports, o.reports === 1 ? "report ran" : "reports ran"],
    [o.sessions, o.sessions === 1 ? "agent finished" : "agents finished"], [o.closed, o.closed === 1 ? "task closed" : "tasks closed"]]
    .filter(([n]) => n).map(([n, w]) => `${n} ${w}`).join(" · ");
  if (!pending && !counts && !cards.length && !dg.at && !d?.learned?.line) return null;
  const spin = (words) => <span role="status" style={{ display: "inline-flex", alignItems: "center", gap: 6 }}><CircularProgress size={12} thickness={5} sx={{ color: "#827356" }} />{words}</span>;
  return (
    <div className="tq-since" data-tq-since="">
      <div className="tq-since-head"><span className="tq-day-h" style={{ margin: 0 }}>{o.heading || "Since last night"}</span>{!d || d.reading ? spin("Reading what came in…") : counts && <span>{counts}</span>}</div>
      {!!cards.length && <div className="tq-since-cards">
        {cards.map((c, i) => (
          <button key={c.key || c.link || i} type="button" className={`tq-since-card ${c.kind}`} data-tq-since-card={c.key || c.link}
            onClick={() => { if (c.key) onOpen?.(c.key); else if (c.link) openAppLink(c.link); }} title={c.key ? "Open it" : "See what changed"}>
            <span className="lbl"><i />{c.label}</span><span className="txt">{c.text}</span>
          </button>
        ))}
      </div>}
      {/* WHAT WAS LEARNED - the memory - always its own line, never squeezed out of the cards (2026-10-08: "did you remove the memory section?") */}
      {d?.learned?.line && <div className="tq-since-digest" data-tq-learned="">
        <span className="tag" style={{ color: "#6e685f" }}>MEMORY</span>
        <span title={d.learned.latest ? `Latest: ${d.learned.latest}` : undefined}>{d.learned.line}</span>
        <button type="button" className="tq-linkish" onClick={() => { openAppLink("settings=docs&doc=learned&view=changes"); }}>See what changed</button>
      </div>}
      {dg.source_id && dg.writing && !writing && <div className="tq-since-digest" data-tq-digest="" data-tq-digest-writing="">
        {/* queued by Finish setup (firstrun.first_digest): not written until the mail it reads is sorted - said so, with how many are left */}
        <span className="tag">MORNING DIGEST</span>{spin(dg.waiting ? `Not written yet - ${plural(dg.waiting, "email")} still being sorted first`
          : "Writing today's digest…")}
      </div>}
      {dg.source_id && !(dg.writing && !writing) && <div className="tq-since-digest" data-tq-digest="">
        <span className="tag">MORNING DIGEST</span>
        {dg.at ? <span>written {ago(dg.at)}</span> : <span>not written yet today</span>}
        {dg.at && <button type="button" className="tq-linkish" onClick={() => setOpen((v) => !v)} aria-expanded={open}>{open ? "Fold it ▴" : "See the full digest ▾"}</button>}
        <span className="sep">|</span>
        {/* while it writes, the button IS the status - a spinner, not the button beside a second line saying the same (2026-10-13) */}
        {writing.startsWith("Writing")
          ? spin(writing)
          : <button type="button" className="tq-linkish" onClick={fresh}>Write a fresh one</button>}
        {writing && !writing.startsWith("Writing") && <span>{writing}</span>}
      </div>}
      {open && dg.text && <div className="tq-since-body"><DigestText text={dg.text} sourceId={dg.source_id} /></div>}
    </div>
  );
}

function greeting() {
  const h = new Date().getHours();
  return h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening";
}

function Pile({ pile, current, onPull, error, onRetry, onSection, onCurrent, onMoreFyi, settingUp = false, tag = "on the table" }) {
  const items = pile?.items || [];
  // the plain FYI the page has not asked for whole yet (funnel.page_fyi): counted with their band, drawn when it is opened
  const tail = fyiTail(pile).length;
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
    ...(curKey && !known ? [pulledRow(current)] : []),
    ...onTable,
    // the card on the table lends the row its words; WHERE the row sits is the rail's (placed) - its older lane drew a
    // working agent under Your task until the next chat read refreshed it (the owner, 2026-09-28)
    ...drawOrder(visibleItems).map((i) => (i.key === curKey ? placed(i, current) : i)),
  ];
  const prev = useRef(null);
  const [landing, setLanding] = useState(new Set());
  // ...and only into a rail that had rows: after an empty one (a read that failed, a first sync) every row would fall at once, the
  // whole band squeezed above the pipe and drawn over itself on the way down (G8)
  const arrivalsOf = (was) => (was?.size ? arrivals(was, items) : new Set());
  useEffect(() => {
    const fresh = arrivalsOf(prev.current);
    prev.current = keysOf(items);
    if (!fresh.size) return undefined;
    setLanding(fresh);
    const t = setTimeout(() => setLanding(new Set()), 40);       // one frame above the pipe, then it falls to its slot
    return () => clearTimeout(t);
  }, [displayRevision(pile)]);                                     // eslint-disable-line react-hooks/exhaustive-deps
  // ...and above it from its FIRST frame (G8): the mark above is set after that frame is painted, and the arrival was drawn once in its
  // slot, over the row still gliding out of it. Until the effect has run, the rows this pile adds are told apart here.
  const arriving = arrivalsOf(prev.current);
  const falls = (k) => landing.has(k) || arriving.has(k);
  // The NEXT ring has to be what the Next button will actually bring up. The server skips what an
  // agent has in hand and what this walk already showed (funnel.next_item); the marker did not, so a
  // coding agent parked on a question wore NEXT while two fyi about lunch came out instead (2026-09-03).
  // New servers capture the selection from the same snapshot as this pile. FYI batches have a
  // composite selected key, so their first ordered member wears the visible NEXT marker.
  const nextKey = nextMarkerKey(pile, items, current);
  // how close to empty, once that is worth saying (the owner asked for it at "halfway down the
  // funnel", so from fifteen: the count is the encouragement - no header, no total)
  const left = items.filter((i) => !i.settling && i.lane !== "working").length + tail;
  const cheer = !left || left > 15 ? "" : left === 1 ? "One more and you're clear."
    : left <= 5 ? `${left} to go, then you're clear.` : `${left} away from clear.`;

  // ── the ranked tail, when a connector is in bulk mode ───────────────────────────────────────
  // The server says WHICH row wears the pill and how many wait behind it; on an install that ranks
  // nothing it says null, and every line below is dead. An owner who takes one item at a time never
  // sees any of this (the owner, 2026-09-18: "i should not see it since i process each by itself").
  // ONE PER RANKED INPUT: each has its own queue, its own batch size and its own count, so each
  // wears its own pill under its own last row. An install that ranks nothing gets an empty list and
  // every line below is dead.
  const markers = pile?.more_markers || [];
  const byKey = useMemo(() => Object.fromEntries(markers.map((m) => [m.key, m])), [markers]);
  // BULK PROCESSING: a ranked row's place in its batch, circled (the owner, 2026-09-28: "we should write numbers on it
  // like circle 1 rank") - in the order the batch let them in, which is rank order (rank.rank_numbers)
  const rankNo = pile?.rank_numbers || {};
  // a BATCH row: how far it got, in words and as one bar segment per item (batch.py / batchItems.js)
  const batchNo = pile?.batch_progress || {};
  const [openChannel, setOpenChannel] = useState("");
  const [waiting, setWaiting] = useState(null);
  useEffect(() => {
    if (!openChannel) return;
    let alive = true;
    api.get("/api/funnel/waiting").then(({ data }) => { if (alive) setWaiting(data); }).catch(() => {});
    return () => { alive = false; };
  }, [openChannel]);
  useEffect(() => { if (!markers.length) setOpenChannel(""); }, [markers.length]);

  // ── how much of each band fits ──────────────────────────────────────────────────────────────
  // urgent, your task and agents working draw in full; reports and fyi divide what is left of the
  // rail's height, floor of two (funnelPile.fillCaps). It is MEASURED from the scroller, so the
  // answer follows the window instead of being a number somebody picked.
  // PASSED means you moved ON from it: the card on the table has been shown (the walk marks it at once)
  // but you are still on it, so it keeps its band until Next takes you past it (the owner, 2026-09-23:
  // "it started in your task and moved to passed without touching anything")
  const atTable = (i) => !!current && (i.key === current.key || (current.aliases || []).includes(i.key) || (i.aliases || []).includes(current.key));
  // ...and the row on the table stays in the band it was clicked in (2026-10-19 UI walk): a For later row clicked was taken up by the
  // server (no longer put down) and jumped to On you under the pointer. It moves when the owner moves on, never while they look.
  const lastLevel = useRef({}), pin = useRef(null);
  const tableRow = current ? drawn.find(atTable) : null;
  if (!tableRow) pin.current = null;
  else if (pin.current?.key !== tableRow.key) pin.current = { key: tableRow.key, level: lastLevel.current[tableRow.key] || null };
  const bands = bandsOf(drawn.map((i) => (i.surfaced && atTable(i) ? { ...i, surfaced: false } : i)), pin.current);
  lastLevel.current = Object.fromEntries(bands.flatMap((b) => b.items.map((i) => [i.key, b.level])));
  // the FYI band is costed whole: its "N more fyi" stays while any of it is not here (fillCaps reads `total`)
  if (tail) for (const b of bands) if (b.level === "fyi") b.total = b.items.length + tail;
  const sig = bands.map((b) => `${b.level}:${b.items.length}`).join(",");
  const wrapRef = useRef(null);
  // what is on the table is ringed WHERE THE OWNER CAN SEE IT (railReveal.js): once per change, after the rows' .55s glide
  const tableKey = current?.key || null;
  useEffect(() => {
    if (!tableKey) return undefined;
    const t = setTimeout(() => revealRing(wrapRef.current), 620);
    return () => clearTimeout(t);
  }, [tableKey]);
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
  // ...and an OPEN fyi band asks for its next page as its "N more fyi" scrolls into view - more as the owner scrolls
  const moreRef = useRef(null);
  const fyiOpen = opened.has("fyi") && tail > 0;
  useEffect(() => {
    const el = moreRef.current;
    if (!fyiOpen || !el || typeof IntersectionObserver === "undefined") return undefined;
    const io = new IntersectionObserver((seen) => { if (seen.some((e) => e.isIntersecting)) onMoreFyi?.(); },
      { root: el.closest("[data-tq-rail]"), rootMargin: "0px 0px 200px 0px" });
    io.observe(el);
    return () => io.disconnect();
  }, [fyiOpen, displayRevision(pile)]);                           // eslint-disable-line react-hooks/exhaustive-deps
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
  // A ROW THAT JOINS A BAND WAITS FOR THE GLIDE (G8): a row moving in - passed into For later, a slot freed under a cap - was drawn in
  // its slot at once, under the rows still gliding out of it, for ten-odd frames. It comes in once the others have moved. Not on the
  // first draw, and not a row falling in from above the pipe (`landing`), which has its own way in.
  // ...nor the row on the table: the ring lands with its card, in the same frame
  const placedNow = useRef([]), placedBefore = useRef(null), enterTimer = useRef(0);
  placedNow.current = [];
  const [entering, setEntering] = useState(() => new Set());
  useLayoutEffect(() => {
    const now = placedNow.current, was = placedBefore.current, inPile = prev.current;
    placedBefore.current = new Set(now);
    const fresh = was ? now.filter((lk) => !was.has(lk)).map((lk) => lk.slice(lk.indexOf(" ") + 1)).filter((k) => k !== curKey && inPile?.has(k)) : [];
    if (!fresh.length) return;
    setEntering(new Set(fresh));
    clearTimeout(enterTimer.current); enterTimer.current = setTimeout(() => setEntering(new Set()), 700);
  });
  useEffect(() => () => { clearTimeout(enterTimer.current); }, []);
  // ...AND A ROW REORDERED IN ITS BAND GLIDES TOO: React moves its node in the page to keep the order, and a moved node starts
  // from its new place with no transition - the row put on the table jumped to its slot, full height, over rows still gliding
  // past it (a rail click: 15 frames of rows drawn on each other). Such a row is sent back to where it was and let go from there.
  const rested = useRef(new Map());
  useLayoutEffect(() => {
    const was = rested.current, now = new Map();
    for (const el of wrapRef.current?.querySelectorAll(".tq-pile-row[data-tq-key]") || []) {
      const k = `${el.closest("[data-tq-run]")?.dataset.tqRun} ${el.dataset.tqKey}`, top = parseFloat(el.style.top) || 0;
      const p = was.get(k);
      if (p && !el.classList.contains("landing") && Math.abs(p.top - top) > 1 && Math.abs(parseFloat(getComputedStyle(el).top) - top) < 0.5) {
        el.style.transition = "none"; el.style.top = `${p.top}px`; el.style.height = `${p.h}px`;
        void el.offsetHeight;                                  // the old place is drawn as the start, then the glide runs from it
        el.style.transition = ""; el.style.top = `${top}px`; el.style.height = "";
      }
      now.set(k, { top, h: (el.classList.contains("current") ? CUR_H : ROW_H) - 3 });   // where it comes to rest: the 3px is the gap
    }
    rested.current = now;
  });
  useLayoutEffect(() => {
    const el = wrapRef.current;
    const scroller = el?.closest("[data-tq-rail]");
    if (!el || !scroller || trim >= headroom) return;
    const over = scroller.scrollHeight - scroller.clientHeight;
    if (over > 4) setTrim((was) => Math.min(headroom, was + Math.ceil(over / ROW_PX)));
  });

  return (
    <div className="tq-pile" data-tq-keep ref={wrapRef}>
      {!pile ? (error ? (
        /* A LOAD THAT FAILED IS NOT A LOAD IN PROGRESS. This spun on "Loading timeline" for as long
           as the tab stayed open while the server had answered 500 twenty minutes earlier - and the
           owner, on a fresh install on another machine, had nothing to read anywhere (2026-09-22). */
        <div className="tq-pile-empty" role="alert">
          <span className="mark">!</span><b>The timeline did not load</b>{error}
          <button type="button" className="tq-pile-retry" onClick={() => onRetry?.()}>{btn("try_again")}</button>
        </div>
      ) : (
        <div className="tq-pile-empty" role="status"><CircularProgress size={18} /><b>Loading timeline</b>Reading what arrived and what still needs you.</div>
      )
      ) : !drawn.length && settingUp ? (
        // a first run has nothing here because nothing is CONNECTED yet - "All done" read as finished (fresh-install shot, 2026-10-14)
        // ...and says what is next in the first run's own words (firstrun.state's `todo`), not a step count of its own (2026-10-15)
        <div className="tq-pile-empty" data-tq-pile-setup=""><b>Your mail shows up here</b>Setup: {settingUp}. What comes in is then sorted into this list.</div>
      ) : !drawn.length ? (
        <div className="tq-pile-empty"><span className="mark">✓</span><b>All done</b>Nothing is waiting on you. New things land here as they arrive, and Taskuary speaks up.</div>
      ) : bands.map(({ level, items: rows }) => {
        const open = opened.has(level);
        const extra = level === "fyi" ? tail : 0;           // the band's rows not here yet - counted, never dropped
        const cap = open ? rows.length : (caps[level] ?? rows.length);
        // only the two bands the rail is allowed to cap can be folded; urgent, your task and agents
        // working are never hidden, so a chevron on them would offer nothing
        const folds = CAPPED.includes(level) && rows.length > FLOOR;
        // what is on the table is never capped away, wherever in its band it sits
        const shown = rows.filter((i, n) => n < cap || i.key === curKey || batchKeys.has(i.key));
        const hidden = rows.length - shown.length + extra;
        let stackHeight = 0;
        // BULK PROCESSING: the "250 more" pill hangs off the LAST ranked row, where reading stopped -
        // not off the band, which is what the fyi pill means. It takes real height, so the rows under
        // it move down by exactly that and the stack still measures true.
        const moreTops = [];
        let wasInBatch = false;
        const positioned = shown.map((item) => {
          // ...and the ROW AFTER the bracket steps down by the height of the bracket's own label, so
          // "on the table · 4 fyi" hangs in a gap instead of being printed across the next fyi's
          // subject (the owner, 2026-09-22). One gap, once, while a batch is up: no row is reordered
          // and nothing above it moves, which is what "the row wears the ring where it sits" protects.
          const inBatch = batchKeys.has(item.key);
          // ...and when the batch OPENS the band there is nowhere above it for the bracket's own
          // edge to go: the stack starts flush under the sticky heading. Four pixels here put the
          // ring around the first card instead of along its top border.
          if (inBatch && !wasInBatch && stackHeight === 0) stackHeight += 4;
          if (wasInBatch && !inBatch) stackHeight += BATCH_TAIL;
          wasInBatch = inBatch;
          const top = stackHeight;
          stackHeight += item.key === curKey ? CUR_H : ROW_H;
          if (byKey[item.key]) { moreTops.push({ top: stackHeight, mark: byKey[item.key] }); stackHeight += MORE_PX; }
          placedNow.current.push(`${level} ${item.key}`);
          return { item, top };
        });
        // the bracket spans its members where they already are: it adds no height and moves no row
        const mem = positioned.filter(({ item }) => batchKeys.has(item.key));
        if (mem.length && wasInBatch) stackHeight += BATCH_TAIL;      // ...the batch ends the band
        // Its bottom edge is where it always was; its TOP is clamped into the stack. Four pixels of
        // breathing room above the first member is four pixels UNDER the band heading, which is
        // sticky, opaque and painted above it - so the bracket's top edge and both its corners
        // simply were not there, and the group read as a row with its top cut off (2026-09-22).
        const bracket = mem.length
          ? { top: Math.max(0, mem[0].top - 4),
              height: mem[mem.length - 1].top + ROW_H + 1 - Math.max(0, mem[0].top - 4) } : null;
        return (
          <div className="tq-pile-band" key={level} data-tq-run={level} style={{ "--band": LEVEL_COLOR[level], "--tint": LEVEL_TINT[level] }}>
            {/* the category, said once, in the one place importance exists in this product - and
                the reason the dock above the rail no longer carries a level dropdown saying it.
                A band that can be opened is also the way to shut it again: opening one had no way
                back at all (the owner, 2026-09-16: "clicking on fyi or reports should close it
                back up or a tiny arrow"). */}
            {/* THE HEADING WALKS ITS SECTION (the canvas redesign, 2026-09-29): its first row goes on the table and Next
                stays inside it until it is empty. Opening a capped band is the chevron's job alone now. */}
            <div className={`tq-pile-head${folds ? " folds" : ""}`} data-tq-section-head={level} role="button"
              title={`Walk ${levelLabel(level)} - ${LEVEL_META[level]?.hint || ""}`}
              onClick={() => onSection(level)}>
              {/* each band its own SUBTLE tint (the owner, 2026-09-28: "now all the pills are the same. make them subtly
                  different") - light red for your task, never the loud one; urgent alone keeps its colour */}
              <span className={`lvl-${level}`}>{levelLabel(level)}</span>
              {folds && <i className="fold" role="button" title={open ? `Collapse ${levelLabel(level)}` : `Show all ${rows.length + extra}`}
                onClick={(e) => { e.stopPropagation(); if (!open && extra) onMoreFyi?.(); setOpened((cur) => {
                  const next = new Set(cur);
                  if (next.has(level)) next.delete(level); else next.add(level);
                  return next;
                }); }}>{open ? "▾" : "▸"}</i>}
              <hr /><em>{rows.length + extra}</em>
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
                const cls = ["tq-pile-row", falls(i.key) ? "landing" : entering.has(i.key) ? "entering" : "", i.settling ? "settling" : "",
                  isCur ? "current" : inBatch ? "inbatch" : i.key === nextKey ? "next" : ""].filter(Boolean).join(" ");
                // NO PILLS ON A ROW (the owner, 2026-09-28: "nothing else has pill"): a row's state is its mark and word, the same
                // for every lane - "ready to send" and "agent waiting on you" included
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
                  <div key={i.key} className={cls} data-tq-key={i.key} style={{ top: falls(i.key) ? -ROW_H : top }}>
                    {/* For later counts DOWN to when it comes back, in the same short form the age column uses */}
                    <span className="when" title={level === "later" && backAt(i) ? `back ${ago(backAt(i))}` : undefined}>
                      {String(i.kind || "").startsWith("goal") ? dueWord(i.due)      /* a goal's clock is its date (spec 2026-10-12) */
                        : level === "later" ? bandUntil(backAt(i)) : band(i.kind === "meeting" ? i.when : (i.since || i.when))}</span>
                    {/* the dot is the BAND's colour, the pill's own (the owner, 2026-10-06: one palette, everywhere) - where it
                        came from is the logo inside the row */}
                    <span className="rail"><i style={{ background: LEVEL_COLOR[level] || sourceColor(i) }} /></span>
                    {/* the row already on the table SHOWS it - on a phone that means closing the drawer over it */}
                    <div className="card" onClick={() => (isCur ? onCurrent?.() : !i.settling && onPull(i.key, `Show me “${i.title}”`))}
                      title={[i.who, meta.word, i.ref, i.promoted ? 'moved up - it looked urgent' : '', i.why].filter(Boolean).join(" · ")}>
                      <div className="t">
                        <span className="logo"><SourceMark item={i} size={15} /></span>
                        {!!rankNo[i.key] && <span className="tq-pile-rank" title={`#${rankNo[i.key]} of this batch, by importance`}>
                          {CIRCLED[rankNo[i.key] - 1] || rankNo[i.key]}</span>}
                        <b>{i.title}</b>
                        {/* which task this IS. It is how you say "TQ-0588" to the assistant, how you
                            match a row to the Tasks tab, and it was only ever in the tooltip.
                            ...on the row you are looking at: on every row it cut each subject at a laptop's 334px rail to ~14
                            characters (the walk click-through, 2026-10-17) - the others carry it in the hover */}
                        {!!i.ref && isCur && <span className="tq-pile-ref">{i.ref}</span>}
                        {/* a BATCH says how far it got in the row's own height - "1/4"; the whole line on hover and on the table */}
                        {!!batchNo[i.key] && <span className="tq-pile-ref" title={batchNo[i.key].line}>{railShort(batchNo[i.key].states)}</span>}
                        {i.settling && <span className="tq-pile-tag">reading…</span>}
                        {!!word && (
                          <span className="tq-pile-word"
                            style={meta.role === "bad" ? { color: ROLES.bad.ink } : undefined}>
                            <i>{meta.mark}</i><span className="w">{word}</span></span>
                        )}
                      </div>
                      {isCur && <div className="sub">{batchNo[i.key]?.line || [i.why, i.kind === "meeting" ? age(i.when) : ago(i.since || i.when)].filter(Boolean).join(" · ")}</div>}
                    </div>
                    {/* THE SAME WORD ON THE SAME BORDER. A handful on the table says so on its
                        bracket ("on the table · 4 fyi"); one item on the table wore the identical
                        slate ring and said nothing, so the ring had to be read rather than known
                        (the owner, 2026-09-17: "isn't there a current word on the border around
                        chosen task by the assistant?"). It is a sibling of the card, not a child:
                        the card clips its overflow so the title can ellipse. */}
                    {isCur && <b className="tq-pile-now" data-tq-now={tag}>{tag}</b>}
                  </div>
                );
              })}
              {moreTops.map(({ top, mark }) => (
                <button key={mark.key} type="button" className="tq-pile-more" style={{ position: "absolute", top }}
                  title="Ranked and waiting to be read - one is read each time you finish one above"
                  onClick={() => setOpenChannel((c) => (c === mark.channel ? "" : mark.channel))}>
                  {mark.count} more
                </button>
              ))}
            </div>
            {moreTops.length > 0 && openChannel && (
              <div className="tq-pile-waiting">
                {/* nothing below the line has been triaged, so there is no lane, no ref and no task
                    list to draw - only what the arrival itself carried, and the rank's own reason */}
                {(waiting?.items || []).filter((w) => w.channel === openChannel).slice(0, 20).map((w) => (
                  <div key={w.mid} className="tq-pile-waitrow">
                    <span className="subj">{w.subject}</span>
                    <span className="why">{[w.who, w.why].filter(Boolean).join(" \u00b7 ")}</span>
                  </div>
                ))}
                {!waiting && <div className="tq-pile-waitrow"><span className="why">Reading the list\u2026</span></div>}
                {waiting && (waiting.items || []).filter((w) => w.channel === openChannel).length > 20 && (
                  <div className="tq-pile-waitrow"><span className="why">
                    {(waiting.items || []).filter((w) => w.channel === openChannel).length - 20} more below these
                  </span></div>
                )}
              </div>
            )}
            {hidden > 0 && (
              <button type="button" className="tq-pile-more" ref={open && extra ? moreRef : undefined}
                onClick={() => { if (extra) onMoreFyi?.(); setOpened((cur) => new Set(cur).add(level)); }}>
                {hidden} more {level === "reports" ? "report" : level === "ideas" ? "idea" : "fyi"}{hidden > 1 && level !== "fyi" ? "s" : ""}
              </button>
            )}
          </div>
        );
      })}
      {!!cheer && <div className="tq-pile-cheer">{cheer}</div>}
      {!!pile?.hidden && <div className="tq-pile-note">+{pile.hidden} more wait behind these</div>}
      {/* nothing disappears silently: what the owner's own standing rules held back is said here */}
      {!!pile?.muted && <div className="tq-pile-note" title={`Your standing rules:\n${(pile.rules || []).join("\n")}\n\nNothing is deleted - search finds what they filed.`}>{pile.muted} filed by your rules</div>}
    </div>
  );
}
// the ways to use the stage - lives in the page's top bar (TaskHubPage), since it decides what the sidebar's rows do.
// Game swaps the whole tab for the office (AssistantGame.jsx): the same pile, walked instead of talked through.

// ── one line of the conversation, with its card ───────────────────────────────────────────
// THE WORDS LIVE IN THE ROW BY THE PROMPT, never as buttons under a chat line (the owner, 2026-10-06: "no button in line ever
// anyway. it should on bottom by the prompt"). A line hands its words to the same row the task view fills (actionRow.js).
function BarVerbs({ owner, chips, busy, onChip }) {
  // the item's key in the id: the end of the walk offers one "open" chip per item, and one id kept only the last - "Open TQ-0001" opened
  // TQ-0010. The verb stays LAST so isDone's /:done$/ still finds a done chip
  useVerbs(owner, chips.map((c, i) => ({ id: `chat:${c.key ? `${c.key}:` : ""}${c.verb || c.label}`, label: c.label, group: c.verb === "next" ? "next" : "decide",
    tone: i === 0 && c.verb !== "next" ? "p" : "s", title: c.hint || "", disabled: busy, run: () => onChip(c) })), chips.length > 0);
  return null;
}

// A ROW TRIAGE FAILED ON can be judged again from the row by the prompt - this one, or every one that failed (the owner,
// 2026-10-06: "i refreshed the app but it did not retriage??" - a day the brain failed on every call, past the automatic
// sweep's day, with only a per-row Retry on the Timeline). The server works them off the request, oldest first.
function RetryVerbs({ item, failed, onSaid, onDone }) {
  const [busy, setBusy] = useState(false);
  const on = item?.lane === "unjudged" && !!item?.mid;
  const go = async (all) => {
    setBusy(true);
    try {
      if (all) {
        const { data } = await api.post("/api/messages/retriage-failed");
        onSaid(data?.count ? `Sorting ${plural(data.count, "message")} again - each moves to its place as it is read.` : "Nothing is waiting to be sorted any more.");
      } else {
        await api.post(`/api/messages/${item.mid}/retriage`);
        onSaid("Sorted again.");
      }
    } catch (e) { onSaid(`Could not sort them again - ${e?.response?.data?.detail || e?.message || "the server did not answer"}.`, "error"); }
    setBusy(false); onDone?.();
  };
  useVerbs("retriage", [
    { id: "retriage", label: btn("retriage"), group: "decide", tone: "p", disabled: busy, run: () => go(false), title: btnHint("retriage") },
    ...(failed > 1 ? [{ id: "retriage-all", label: `${btn("retriage")} - all ${failed}`, group: "decide", tone: "s", disabled: busy, run: () => go(true),
      title: "Every message that could not be sorted, oldest first - whatever its age" }] : []),
  ], on);
  return null;
}

function Line({ m, lastBrief = false, live, last, actions, fresh, tableChips = [], barHolds = false, canvas = null }) {
  if (m.role === "user") return <div className="tq-msg you"><div className="body">{m.text}
    {!!m.shots?.length && <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 6 }}>{m.shots.map((s) => (
      <img key={s.path} src={s.url} alt={s.name} style={{ maxWidth: 160, maxHeight: 120, borderRadius: 6, border: "1px solid #ddd6cb" }} />))}</div>}</div></div>;
  // the day's opener draws the welcome, once - an earlier day's sits under it as nothing (actions.welcome)
  if (m.card?.kind === "brief") return lastBrief ? actions.welcome(m) : null;
  // BROWSING (the canvas redesign, 2026-09-29): Connections, Settings, Reports or Hub, walked by clicks on this line
  if (m.role === "browse") return (
    <div className={`tq-browse-line${canvas?.browsing === m.id ? " tq-canvas-live" : ""}`} data-tq-browse-line={m.area}>
      <CanvasBrowse area={m.area} state={m.state || {}} live={canvas?.browsing === m.id}
        onState={(state) => actions.browseState(m.id, state)} onOpenCard={actions.openCard} onReopen={() => actions.browse(m.area, m.state)}
        onNavigate={actions.navigate} onOpenTask={actions.openTask} onClose={() => actions.browseClose(m.id)} />
    </div>
  );
  if (m.role === "receipt") return (
    <div className="tq-msg receipt"><span /><div className="body">{m.status && m.status !== "done" ? "✗" : "✓"} {m.text}
      {/* a receipt can carry the walk's own word: a sweep puts the table down and OFFERS Next rather
          than jumping to the next thing by itself (the owner, 2026-09-11). Same strip, same buttons.
          ...and its Open and Report this bug go there too: a button in the line is against "no button in line ever" (2026-10-06),
          and an Open TQ-x and a Report this bug link stood in the chat under a failure (the walk click-through, 2026-10-17) */}
      {last && <BarVerbs owner={`line:${m.id}`} chips={receiptChips(m)} busy={actions.busy} onChip={actions.chip} />}
    </div></div>);
  // The funnel deliberately renames msg:<mid> to agent:<tid> when somebody takes the task. Follow
  // the task identity across that rename; matching only the old key left a live agent displayed as
  // "nobody on it" until a new chat line happened to replace the card.
  const follows = live && !m.proposal && followsItem(m.card, fresh);   // a proposal is its own card, never the item's
  // ``fresh`` is a complete presentation, not a patch. Exact replacement clears source fields
  // that disappeared while retaining the durable conversation line and the card's local UI state.
  const c = follows ? fresh : m.card;                     // the live card follows the pile
  // NOTE_KINDS mark a line for the server's own bookkeeping (the set-up's pending questions) and draw nothing:
  // read as an item card they hid the sentence and drew an empty "asked you" box where the questions were
  // (the owner, 2026-09-24: "it should show ... like normal but no response??")
  const kind = NOTE_KINDS.has(c?.kind) ? null
    // ...and Set up Taskuary's card is the setup itself: unrouted it fell to a message card - an empty "asked you" box (2026-10-15)
    : c?.kind === "setup" ? "setup" : c?.kind === "walk" ? "walk" : c?.kind === "firstrun" ? "firstrun" : (m.proposal || c?.kind === "proposal") ? "proposal" : cardFor(c);
  // the short line only over a LIVE card, which shows the brief and the repository itself; one read back from
  // history carries only its heading, so there the sentence is still the only place the brief is written
  const text = kind === "proposal" ? proposalSay(m.proposal?.say_card || m.text, m.proposal || c, live) : m.text;
  // From the DURABLE turn, never from `fresh`: the vocabulary was chosen when the line was written and
  // is recorded with it, while a pile refresh rebuilds the live item WITHOUT chips - reading them off
  // `fresh` made the words vanish on the next poll. A verb that has since stopped applying is refused
  // server-side at propose time, which is the only place that can know.
  // A proposal is waiting on its own Confirm: offering the item's verbs beside it invites two answers.
  const own = chipsOf(m);
  const said = last && !m.proposal && kind !== "proposal" ? (own.length || m.card ? own : tableChips) : [];
  // NEVER A DEAD END (the owner, 2026-09-30: "it can write that ... but then should move to next or at least have buttons to
  // navigate"): the newest line with nothing to press - a notice, an answer, a line read back from history - offers Next
  // while the pipe still holds something. Not under an FYI batch: its own "All read, next" IS Next (the owner, 2026-10-02)
  // ...and with the rail EMPTY it offered nothing at all: "Nothing's waiting." ended on no button, and the morning line took
  // the place of the welcome block's own. What there is to do then is start something - the welcome block's doors, as words.
  const idle = !(actions.items || []).length;
  const chips = barHolds && !m.card ? []          // the task view's own row under the chat holds its words, Next included
    : said.length || !last || m.role !== "assistant" || m.proposal || kind === "proposal" || kind === "fyis"
    ? said : idle ? IDLE_CHIPS : [{ verb: "next", label: btn("next") }];
  const card = live && m.card && kind ? {
    proposal: <ProposalCard p={m.proposal || c} onConfirm={actions.confirm} onCancel={actions.cancel} onPreview={actions.preview} />,
    reply: <ReplyCard card={c} onDone={actions.done} onSent={actions.sent} onOpenTask={actions.openTask} onTimeline={actions.timeline} />,
    meeting: <MeetingCard card={c} onDone={actions.done} onOpenTask={actions.openTask} />,
    report: <ReportCard card={c} onOpenTask={actions.openTask} onTimeline={actions.timeline} onDone={actions.done} />,
    idea: <IdeaCard card={c} onOpenTask={actions.openTask} onTimeline={actions.timeline} onNavigate={actions.navigate} onDone={actions.done} />,
    message: <MessageCard card={c} onDone={actions.done} onOpenTask={actions.openTask} onTimeline={actions.timeline} onSurface={actions.surface} onNavigate={actions.navigate} />,
    setup: <SetupCard card={m.card} onNavigate={actions.navigate} onHandOff={actions.handOff} />,
    walk: <WalkCard card={m.card} at={m.card.n} total={m.card.total} onNavigate={actions.navigate}
      onNext={() => actions.walk(m.card.n + 1)} onBack={() => actions.walk(m.card.n - 1)}
      onRestart={actions.walkRestart} onFinish={() => actions.walk(-1)}
      onSaved={() => actions.walkSaved(m.id)} />,
    brief: <BriefCard card={m.card} onStart={actions.start} />,
    // SET UP TASKUARY is the two cards, not the 13-stop walk (the owner, 2026-10-14: "what is this garbage ... where are the cards")
    firstrun: <FirstRun revisit onChanged={actions.reload} onWalk={() => actions.start(null)} />,
    fyis: <FyisCard card={c} onDone={actions.done} onSurface={actions.surface} onTimeline={actions.timeline} onPropose={actions.propose} />,
  }[kind] : null;
  // A STOP THE WALK HAS MOVED PAST is a finished step, not something the assistant said. Falling
  // through to the title note below drew six near-identical rows, each carrying the message avatar
  // AND the card's own mark - two snowflakes and a title, six times, with nothing saying they were
  // one walk (the owner, running it). It keeps its place in the trail as one muted line that counts
  // itself, so scrolling up reads as the steps already passed.
  const passed = !live && kind === "walk" && !!m.card;
  // THE TASK VIEW ON THE TABLE (the canvas redesign, 2026-09-29): the Tasks tab's own view, not a walk card
  // ...folded to its title line by its X, or while a browse card is open below it (the mockup's Browse board)
  const foldedNow = !!canvas && live && !!m.card && (foldsAs(canvas.folded, m.card.key) || !!canvas.browsing);
  // a broken connection on the table is drawn like the task view beside it - its own frame, no avatar (the owner, 2026-10-15)
  const bare = live && c?.kind === "connection" && !foldedNow;
  if (live && canvas && m.card && showsTask(c, kind) && !foldedNow) return (
    <div className="tq-canvas-live">
      <CanvasItem card={c} height={canvas.height} expanded={canvas.expanded} onExpand={canvas.toggle} phone={canvas.phone}
        onNext={() => actions.next()} busy={actions.busy} onFold={() => canvas.fold(c.key)} onAfter={() => actions.advance(null, true)}
        onLeave={() => canvas.putDown(c.key, c.tid)} onStay={(why) => canvas.pickUp(c.key, why)} onReminded={(out) => actions.reminded(out, c)}
        onListChanged={actions.reload} onChanged={actions.changed} onGoReports={actions.goReports} onOpenTask={actions.openTask} lit={canvas.lit}
        onPropose={actions.pressAdvice} />
    </div>
  );
  // THE WORDS RIDE IN THE CARD (2026-09-23): Next beside the card's verb, every other word on its
  // quiet Also line. Only answer chips (a model's own options) and a card-less line keep the strip.
  const inCard = !!card && kind !== "walk" && kind !== "setup";
  const verbs = inCard ? chips.filter((c) => c.verb) : [];
  // a card that has FOLDED or been walked past is not the item any more - its recorded words (Stop and save, Remind me)
  // were still offered while it closed (the owner, 2026-10-06: "why do we still have these buttons while it's closing a task?");
  // all it keeps is the way on
  const moved = !!m.card && (!live || foldedNow);
  const strip = moved ? chips.filter((c) => c.verb === "next") : inCard ? chips.filter((c) => !c.verb) : chips;
  const nextChip = verbs.find((c) => c.verb === "next");
  const nav = { busy: actions.busy, items: actions.items, surface: actions.surface, row: live && last && !!canvas && !actions.handedTo, ref: c?.ref || "",   // Next and the words ride in the row above the chat line

    onNext: nextChip ? () => actions.chip(nextChip) : null,
    also: verbs.filter((c) => c.verb !== "next").map((c) => ({ verb: c.verb, label: c.label, title: c.hint, disabled: actions.busy, onClick: (e) => actions.chip(c, e?.currentTarget) })) };
  return (
    <>
      {/* the item on the table takes the canvas's whole width, whatever card it wears (the owner, 2026-09-29) */}
      {/* ...a PROPOSAL is not the item: it is a line of the chat, and full width beside narrow lines read as a glitch (the owner,
          2026-10-08: "why are some wide and some narrow?") */}
      <div className={passed ? "tq-msg tq-step" : live && card && kind !== "proposal" ? `tq-msg tq-live-card${bare ? " tq-bare" : ""}` : "tq-msg"}>
        {!passed && !bare && <div className="avatar"><AssistantMark /></div>}
        <div className="body">
          {/* NOT OVER A LIVE CARD: the card's lead says who wants what, and the sentence above it said
              the same thing first (the owner, 2026-09-23: "remove the text above the card - it's duplicate").
              A proposal keeps its sentence - that is the question its Confirm answers. */}
          {/* ...nor over one the walk has moved past: the line under it (the item's mark, its title and its
              task) is the trail, and the sentence was that line at length (2026-09-23: "we just hit next,
              don't need all this text") */}
          {/* ...and over a PROPOSAL only what its card does not say - the heading and its line were the sentence's
              first half (the owner, 2026-09-24: "if there is box don't show it again") */}
          {text && !(m.card && kind && !["proposal", "walk", "setup"].includes(kind)) ? (looksMd(text) ? <Md text={text} /> : text.split("\n").map((p, i) => <p key={i}>{p}</p>)) : null}
          {passed && (
            <div className="tq-step-done"><i>✓</i><b>{(m.card.n ?? 0) + 1} of {m.card.total}</b>
              <span>·</span>{m.card.title}</div>
          )}
          {/* AN EARLIER ITEM FOLDS TO ITS TITLE LINE - a record of the walk, not a door. "Open again" brought it to the bottom as the
              current item, and reopening it in place would leave two current items when the assistant, the bar and Next all work
              the last one (the owner, 2026-10-16: "maybe just remove the open again button"); asking for it brings it back */}
          {/* ...and a task view's receipt is a sentence: no title line under it (Stream B) */}
          {!passed && (!live || foldedNow) && m.card && kind && kind !== "setup" && kind !== "brief" && !(kind === "proposal" && m.card.background_event) && (
            // ...except the item ON THE TABLE, folded by its X or a page opened over it: that line is its door back - nothing reopened
            // it, while the rail kept ringing it and the Advisor kept talking about it (re-audit item 4, 2026-10-18)
            <div className="tq-fold" data-tq-folded={m.card.key} {...(live && foldedNow ? { role: "button", tabIndex: 0, title: "Open it again",
              style: { cursor: "pointer" }, onClick: () => actions.reopen?.(m.card.key, true),
              onKeyDown: (e) => { if (e.key === "Enter") actions.reopen?.(m.card.key, true); } } : {})}>
              <SourceMark item={m.card} size={12} />
              {!!m.card.ref && <span className="ref">{m.card.ref}</span>}
              <b>{m.card.title}</b>
            </div>
          )}
          {card && !foldedNow && <CardNav.Provider value={nav}>{card}</CardNav.Provider>}
          {/* WHY ITS BUTTONS ARE DEAD, on the card itself: the walk is in a chat, and the one explanation was a banner
              at the foot of the page (2026-09-29: "Next" greyed out on the card with nothing saying why) */}
          {last && card && actions.handedTo && (
            <div className="tq-card-excerpt">The walk is in {actions.handedTo} - answer it there, or press {btn("walk_here")} below to use these buttons here.</div>
          )}
          {/* The action words, in the assistant's own line - one place to look, chosen by the server from
              the item's kind and already filtered to what this one can carry (concierge.chips_for). A
              strip over the composer and a second row under the bubble said the same things twice and
              neither was where the sentence was (the owner, 2026-09-07). */}
          {last && <BarVerbs owner={`line:${m.id}`} chips={strip} busy={actions.busy} onChip={actions.chip} />}
        </div>
      </div>
    </>
  );
}

// ── the page ─────────────────────────────────────────────────────────────────────────────────
/* THE ADVISOR'S NOTES (spec 2026-10-12, "Seeing the Advisor's thinking"): a receipt, not a transcript - what it decided
   on the item on the table, what it dropped and why, with the evidence it cited. Read from /api/advice/notes; shown in
   the clock menu above the past chats, only while something is on the table. */
// ...in plain words: the raw drop reasons ("no brain", "verb not offered: stop_agent"), event names and evidence ids were the
// Advisor's own bookkeeping, unreadable to the person it is for (J)
export const quietWhy = (d = "") => {
  const s = String(d || "");
  if (/no brain|no[ _]ai/i.test(s)) return "No AI connected yet - connect one under Connections, AI.";
  if (s === "cap") return "Busy hour - I'll look again shortly.";
  if (s.startsWith("no answer")) return "The AI didn't answer - I'll look again when this one changes.";
  if (s.startsWith("verb not offered")) return "Its idea wasn't one of the buttons here, so it kept quiet.";
  return "Nothing for you to do here.";
};
// Counts from its own mount - the turn it waits on - and is the only thing that redraws each second
function WorkingFor() {
  const [t0] = useState(() => Date.now()), [now, setNow] = useState(t0);
  useEffect(() => { const id = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(id); }, []);
  const line = workingLine(now - t0);
  return line ? <span className="tq-working" data-tq-working="">{line}</span> : null;
}

function AdvisorNotes({ keyOnTable }) {
  const [rows, setRows] = useState(null);
  useEffect(() => {
    let on = true;
    api.get("/api/advice/notes", { params: { key: keyOnTable, limit: 8 } }).then(({ data }) => { if (on) setRows(data?.rows || []); }).catch(() => { if (on) setRows([]); });
    return () => { on = false; };
  }, [keyOnTable]);
  return (
    <div className="tq-advisor-notes">
      <Typography sx={{ fontSize: 12, fontWeight: 600, color: INK, px: 1.5, pt: 1.25 }}>Advisor's notes on this one</Typography>
      {rows === null && <Typography sx={{ color: FAINT, fontSize: 12, px: 1.5, py: 0.75 }}>Reading…</Typography>}
      {rows && !rows.length && <Typography sx={{ color: FAINT, fontSize: 12, px: 1.5, py: 0.75 }}>Nothing judged on it yet.</Typography>}
      {(rows || []).map((r, i) => (
        <div key={i} style={{ padding: "6px 12px", borderTop: "1px solid #eee9e2" }}>
          <Typography sx={{ fontSize: 11.5, color: FAINT }}>{[age(r.at), r.tier > 1 ? "a closer look" : ""].filter(Boolean).join(" · ")}</Typography>
          <Typography sx={{ fontSize: 12.5, color: INK }}>{r.verb ? `${r.pill} - ${r.line}` : quietWhy(r.dropped)}</Typography>
          {!!(r.evidence || []).some((e) => e.label) && <Typography sx={{ fontSize: 11.5, color: FAINT }}>Looked at: {r.evidence.map((e) => e.label).filter(Boolean).join(" · ")}</Typography>}
        </div>
      ))}
    </div>
  );
}

export default function AssistantView({ onOpenTask, onNavigate, onChanged, mode, onMode, active = true, request = null }) {
  const [state, setState] = useState(null);           // /api/concierge: the dock task, its turns, the AI choices
  const handoff = state?.handoff || null;             // the walk is in a phone chat: this tab is locked behind it
  // A set-up walk-through, running HERE. The conversation binds to that task's own session - which
  // is the one with the browser and the operator's brain - so the owner never leaves this tab to be
  // walked through something they just asked for. Leaving is a button; the task and its session
  // outlive it either way, so nothing is lost by leaving and nothing is resumed by accident.
  const [walk, setWalk] = useState(null);
  const [msgs, setMsgs] = useState([]);
  const msgsRef = useRef(msgs); msgsRef.current = msgs;      // what is on screen, for a read to tell what it ADDED
  const caps = useCapabilities(), canCode = caps.coding;   // coding is mentioned only where a coding tool is connected
  const [pile, setPile] = useState(null);
  // NOT READ YET IS NOT EMPTY (the owner, 2026-10-20): until the first pile read lands the welcome says it is loading, in the
  // place of "Nothing is waiting on you", and a Walk press made then is kept and run when the rows are in (walkQueued)
  const [pileRead, setPileRead] = useState(false), [walkQueued, setWalkQueued] = useState(false);
  useEffect(() => { pileRef.current = pile; }, [pile]);   // the section walk reads the rail as drawn
  // the day's meetings are asked for NOW, not when the welcome first draws - the strip is ready with it
  useEffect(() => { refreshToday(); }, []);
  const [busy, setBusy] = useState(false);
  // a card was let go and the next one is on its way: the settle and the deferred pick run BEFORE
  // surface() raises busy, and that second drew nothing at all (the owner, 2026-09-25: "for a second
  // there is no ... loading the next"). Its own flag, because busy would make surface() refuse to run.
  const [nextComing, setNextComing] = useState(false);
  // THE TASK BEING PUT DOWN leaves the rail at the press too. The card folded while the close ran behind the "…", but the rail
  // drew the server's pile - and a task closed off a live session waits on its write-up first, so for eighteen seconds it
  // sat on the rail as an open task already seen: under For later (the owner, 2026-10-01: "it first went to Later ... and
  // did not disappear right away"). Held until the pile no longer carries it, so a reopened task is never hidden.
  const [leavingTid, setLeavingTid] = useState(null);
  // A TASK BEING CONTINUED moves to Agents working at the press the same way: "Continuing" said so at 0.3 s while its row
  // sat under On you until the next pile, two seconds on (press audit, 2026-10-01). Held until the pile has it working.
  const [continuingTid, setContinuingTid] = useState(null);
  // the walk validates Current against the pile before it can say anything, and that read was
  // 5-47s (2026-09-09). busy is the TURN's interlock and surface() refuses to run while it is
  // set, so opening needs its own flag - without one the button stayed enabled, said nothing,
  // and looked broken for the whole wait.
  const [starting, setStarting] = useState(false);
  const [resetting, setResetting] = useState(false);  // replacing a chat is housekeeping, never an AI turn
  const [work, setWork] = useState([]);              // the turn's tool calls and progress, as they stream
  const [err, setErrRaw] = useState("");
  const setErr = useCallback((v) => {
    if (typeof v === "string" && DEMO_SAID.has(v)) { setMsgs((m) => [...m, { id: `d${Date.now()}`, role: "assistant", text: v, options: [] }]); return; }
    setErrRaw(v);
  }, []);
  const [current, setCurrent] = useState(null);       // the key on the table - the walk's item
  const [currentItem, setCurrentItem] = useState(null);   // ...and the item itself, drawn at the top of the pipe
  const [cardKey, setCardKey] = useState(null);       // ...or a task opened by name (the Board's open), which is no pile item
  const [text, setText] = useState("");
  const [advice, setAdvice] = useState(null);     // the Advisor's line for the key on the table (advisor.py), or null
  const [changed, setChanged] = useState(null);   // {for, reading}: a press refused as changed since the Advisor looked (B6)
  // THE BOX GROWS WITH WHAT YOU TYPE, like every chat app: one row empty, a row per line after that, up to the CSS
  // cap (40% of the window) - then it scrolls inside. rows={1} alone held a paragraph in a one-and-a-half-line slot
  // (the owner, 2026-09-24: "how do we deal with this when you type in many lines?")
  const composeRef = useRef(null);
  useLayoutEffect(() => {
    const el = composeRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${el.scrollHeight}px`;
  }, [text]);
  const phone = useMediaQuery("(max-width:600px)");     // the composer's hint is one line there
  const [chatsOpen, setChatsOpen] = useState(false);
  const [chats, setChats] = useState([]);
  const [chatsLoading, setChatsLoading] = useState(false);
  const [old, setOld] = useState(null);               // an earlier chat, read-only
  const [aiEl, setAiEl] = useState(null);
  const [remindOn, setRemindOn] = useState(null);      // the walk's Remind me: { task, anchor }
  // THE ASSISTANT'S LIT BUTTON (assistantLight.js): a typed act lights the row's own verb for it until a press or the table moves on
  const [lit, setLit] = useState(null);
  useEffect(() => onPressed(() => setLit(null)), []);
  const [continueOn, setContinueOn] = useState(null);  // the walk's Continue: { task, anchor, ref }
  const pics = usePromptImages();                        // pictures sent with the chat line
  // ...and the task view's own Continue on the canvas (TaskPage) asks for the same card
  useEffect(() => {
    const on = (e) => { setNoteOn(null); setContinueOn({ task: e.detail.task, ref: e.detail.ref }); };
    window.addEventListener("tq-continue", on);
    return () => window.removeEventListener("tq-continue", on);
  }, []);
  // ...and Close with a note, the same card: what came of it, and the task view's own close behind the button
  const [noteOn, setNoteOn] = useState(null);           // { task, ref, close(note) }
  // ...and the task view's Configure the next run takes the same place: one card under the conversation at a time
  useEffect(() => {
    const on = () => { setContinueOn(null); setNoteOn(null); };
    window.addEventListener("tq-next-run", on);
    return () => window.removeEventListener("tq-next-run", on);
  }, []);
  useEffect(() => {
    const on = (e) => { setContinueOn(null); setNoteOn(e.detail); };
    window.addEventListener("tq-close-note", on);
    return () => window.removeEventListener("tq-close-note", on);
  }, []);
  const noteKey = useRef(undefined);
  useEffect(() => {
    if (noteOn && noteKey.current !== undefined && noteKey.current !== current) setNoteOn(null);
    noteKey.current = noteOn ? (noteKey.current ?? current) : undefined;
  }, [current, noteOn]);
  // ...and it belongs to ITS task: Next, or anything else put on the table, takes it away (the owner, 2026-09-30: "you left the
  // input box there after hitting next?? it has to be connected to the task")
  const continueKey = useRef(undefined);
  useEffect(() => {
    if (continueOn && continueKey.current !== undefined && continueKey.current !== current) setContinueOn(null);
    continueKey.current = continueOn ? (continueKey.current ?? current) : undefined;
  }, [current, continueOn]);
  const [emojiEl, setEmojiEl] = useState(null);
  const [speakOnState, setSpeak] = useState(speakOn);
  const [modeIn, setModeIn] = useState("chat"), stageMode = mode ?? modeIn, setStageMode = onMode ?? setModeIn;   // what a click on a row does: chat (default) or task view
  const [railOpen, setRailOpen] = useState(false);      // on a phone: the rail instead of the chat
  const bodyRef = useRef(null);
  // Polls and state loads can already be in flight when New chat is pressed. Epoching the
  // conversation prevents an old response from painting the archived thread back over the blank one.
  const chatEpoch = useRef(0);
  const resettingRef = useRef(false);
  const turnFlight = useRef(false);       // React state updates after the event; this closes same-tick double submits
  const turnsBegun = useRef(0);           // every turn sent, counted: a read sent before one began is older than its answer (readChat)
  const openExtra = useRef(null);         // the agent start / act a task opened by name rides in on (openTaskCard -> landed)
  const stopRef = useRef(null);           // the Stop beside the dots: aborts the turn being waited on
  // ...only a turn the model is ANSWERING. Next loading the following item is a fetch, not an answer: it showed "Stop"
  // beside the dots after every let-go (the owner, 2026-10-07: "why is there a button though it should just be ...")
  const answering = useRef(false);
  // Pile construction is comparatively expensive. Never let a timer tick and a websocket
  // notification queue duplicate requests in this tab; remember one forced refresh instead.
  const pileFlight = useRef(null);
  const pileForcePending = useRef(false);
  const loadPileRef = useRef(null);
  const forcedLoadStartedAt = useRef(0);       // when the last forced pile load began (funnelPile.coveredByReload)
  const currentRef = useRef(null); const surfaceRef = useRef(null); const speakRef = useRef(null);
  const noticedRef = useRef(null);      // the context notice the stream already showed this turn
  const only = useRef(null);                                       // "mail" once the owner chose to start with the mail
  const fyiWant = useRef(FYI_PAGE);                                // how many plain FYI the rail asks for whole (funnel.page_fyi)
  const selectionRef = useRef(null);
  const sectionRef = useRef(null);                                 // {level, seen}: a section walk, from its heading
  // THE CANVAS (2026-09-29): the task view takes the chat body's height, Expand hides the conversation around it, and
  // its X folds it to one line - three pieces of client state; none of them asks the server for anything
  const [bodyH, setBodyH] = useState(0);
  const [expanded, setExpanded] = useState(false);
  const [foldedKey, setFoldedKey] = useState(null);
  // the card browsed open, in words - what "this" means to the next turn (concierge.say open_card)
  const openCardRef = useRef(null);
  const browseRef = useRef(null), openTaskRef = useRef(null), browseDownRef = useRef(null);
  const openCard = useCallback((label) => { openCardRef.current = label || null; }, []);
  // the table changed: the next item opens un-expanded and unfolded - a NEW item only. advance() empties the table on the way to
  // the next one, and resetting the fold then drew the task just closed again until the next landed (the owner, 2026-10-05:
  // "the task stayed open and popped back open before closing")
  const tableKey = currentItem?.key || null;
  // ...and never over setup: setupOn mirrors firstRun, which is declared below this line
  const setupOn = useRef(false);
  // WHAT IS ON THE TABLE, by key: the walk's item, or the task opened by name. The advice is read for this key and shown only
  // when it was read for it - the last item's line never stands over the next one
  const onTable = current || cardKey;
  useEffect(() => { if (!tableKey) return; setExpanded(false); setFoldedKey(null); }, [tableKey]);
  // ONE ROAD ONTO THE TABLE (2026-10-18): Next, a chip, a rail click, the Board's open, a reopen, a browse card, the card after a
  // receipt or a failed act - every way something reaches the table comes through here, so the rail's "on the table" mark, the
  // advice and the scroll can never disagree. It was six copies, each setting part of it: the rail marked the item before a Board
  // task, the last item's advice stood over the next, and a card that followed a receipt landed under the row (the walk's SEEN).
  //   how: "pile"   the walk's item (null puts the table down)
  //        "card"   a task opened by name - no pile item, so the rail marks nothing
  //        "view"   a page opened on the canvas, the folded item opened again - the walk's item stays, only the view moves
  //        "sync"   the server's word re-read (a reload, another tab, a refresh): the table follows, the view does not jump
  // a new key re-reads the advice and clears the strip's "this changed" (the effect on onTable below); the same key only refreshes
  const pin = useRef(false);            // the card on the table is held at the top of the view (keepTable below)
  // how the next address is written (recordPlace): "push" once the owner goes somewhere, "replace" for the walk and the server
  const navHow = useRef("replace");
  const cardRef = useRef(null);
  const putOnTable = useCallback((card, how = "pile") => {
    if (how !== "view") {
      const item = how === "card" ? null : card || null;
      currentRef.current = item; cardRef.current = how === "card" ? card?.key || null : null;
      setCurrent(item?.key || null); setCurrentItem(item); setCardKey(cardRef.current);
      // ...and the page the chat was answering about is put away with it: the open page's label stood after a task landed by Next,
      // a chip or a receipt, and the chat went on answering about Settings (re-audit, 2026-10-18)
      if (card) openCardRef.current = null;
    }
    if (how !== "sync") pin.current = true;
    else navHow.current = "replace";
  }, []);
  // the chat body's height is the task view's (CanvasItem): measured, never guessed, and re-measured with the window
  useEffect(() => {
    const el = bodyRef.current;
    if (!el || typeof ResizeObserver === "undefined") return undefined;
    const ro = new ResizeObserver(() => setBodyH(el.clientHeight));
    ro.observe(el); setBodyH(el.clientHeight);
    return () => ro.disconnect();
  }, [walk]);
  // Expand shows the view alone: the body scrolls it into place
  useEffect(() => { if (expanded) bodyRef.current?.querySelector(".tq-canvas-live")?.scrollIntoView({ block: "start" }); }, [expanded]);
  const pileRef = useRef(null);
  const selectionContractSeen = useRef(false);

  // one turn of the assistant, streamed: tool calls show under the dots as they happen, `done` is the answer
  const turnOnce = useCallback(async (body) => {
    turnsBegun.current += 1;
    if (body.mode === "next") body = { ...body, fyi: fyiWant.current };
    setWork([]);
    const stop = new AbortController(); stopRef.current = stop;
    const plain = async () => {
      const endpoint = body.mode === "open" ? "/api/concierge/open" : body.mode === "next" ? "/api/concierge/next" : "/api/concierge/say";
      return (await api.post(endpoint, body.mode === "next" ? { key: body.key, only: body.only, include_surfaced: body.include_surfaced, exclude: body.exclude,
        selection_revision: body.selection_revision, expected_next_key: body.expected_next_key, expected_next_members: body.expected_next_members, fyi: body.fyi }
        : body.mode === "say" ? { text: body.text, key: body.key, context_mid: body.context_mid, images: body.images || [] } : {})).data;
    };
    // The public demo is intentionally a local script. Do not even attempt the streaming AI
    // endpoint: its invented threads should never look like a model is working behind the page.
    if (DEMO) return plain();
    const token = localStorage.getItem("taskuary_token");
    const res = await fetch("/api/concierge/stream", { method: "POST", signal: stop.signal, headers: { "Content-Type": "application/json", ...(token ? { "X-Taskuary-Token": token } : {}) }, body: JSON.stringify(body) });
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
  // ...answered, refused or stopped, a turn can change what the sync caption shows (wrote.js)
  const turn = useCallback(body => turnOnce(body).finally(noteWrite), [turnOnce]);

  const loadState = useCallback(async () => {
    const epoch = chatEpoch.current;
    const { data } = await api.get("/api/concierge");
    if (epoch !== chatEpoch.current) return null;
    // ...keeping what the canvas opened locally meanwhile - a browse card or a task opened before the conversation came
    // back was wiped by it (a sidebar button pressed while the page loads)
    setState(data); setMsgs((cur) => [...settledHistory(data.messages, data.current?.key || null), ...cur.filter((m) => m.role === "browse" || /^t\d/.test(String(m.id)))]);
    // Current is the server's persisted, validated word (PW-162) - never inferred from the last card in the
    // transcript: a handled item stays readable history and is not revived as live work, and an invalid
    // Current comes back null with nothing chosen in its place.
    selectionRef.current = null;
    putOnTable(data.current || null, "sync");
    return data;
  }, [putOnTable]);
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
      deferredChat.current.delete(timer); setNextComing(false);
      if (epoch === chatEpoch.current && !resettingRef.current) fn();
    }, delay);
    deferredChat.current.add(timer);
    return timer;
  }, []);
  const cancelDeferredChat = useCallback(() => {
    setNextComing(false);
    for (const timer of deferredChat.current) clearTimeout(timer);
    deferredChat.current.clear();
  }, []);
  useEffect(() => cancelDeferredChat, [cancelDeferredChat]);
  // Provider messages can arrive while this conversation is already open. The server writes
  // the resulting correction (for example, "you replied in WhatsApp; draft removed") into the
  // durable conversation, so read new turns on every freshness check -- not only when an agent
  // watcher event happens to accompany them.
  // The live socket carries no event for these turns (store.add_comment pokes nothing), so this read
  // runs on the 30 s tick even while the socket is up - the pile beside it does not need to.
  const readChat = useCallback(async (epoch = chatEpoch.current) => {
    const turns = turnsBegun.current;
    const { data: st } = await api.get("/api/concierge");
    if (epoch !== chatEpoch.current || resettingRef.current) return false;
    setMsgs((m) => mergeDurableTurns(m, st.messages || []).messages);
    // WHERE THE WALK IS, from the same answer: a hand-off started or ended somewhere else (a second tab, the phone's own
    // "take it back") left this tab unlocked or locked until a reload (2026-09-29 audit)
    setState((s) => (s && (s.handoff?.at || null) !== (st.handoff?.at || null) ? { ...s, handoff: st.handoff || null } : s));
    // ...AND WHAT IS ON THE TABLE, from the same answer. The walk can be driven from somewhere
    // else - a phone chat holding the handoff, another tab - and this one followed the WORDS while
    // its rail went on ringing whatever the desk itself last put up: the chat showed four fyis and
    // the rail ringed the report before them (the owner, 2026-09-22: "it's out of sync again while
    // talking to assistant on whatsapp"). Current is the server's persisted, validated word
    // (PW-162) wherever it is read; never while a turn of ours is in flight, because that answer
    // is the newer truth and the poll would drag the table back a step.
    // ...and not over a task the owner opened by name here: the walk's Current is not what this tab is showing then
    // ...nor from a read sent before a turn that has answered since: it was taken before that turn moved the table, and dragged a
    // cold link's task back to the item before it (a link's pull outran the boot's own read, found by the perf pass, 2026-10-20)
    if (!turnFlight.current && !cardRef.current) {
      const said = st.current || null;
      if (turns === turnsBegun.current && (said?.key || null) !== (currentRef.current?.key || null)) putOnTable(said, "sync");
    }
    return true;
  }, [putOnTable]);
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
        exclude: requestedScope.exclude, fyi: fyiWant.current,
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
      pileRef.current = refreshPilePresentation(pileRef.current, data);
      setPile((p) => refreshPilePresentation(p, data)); setPileRead(true);
      if (!(await readChat(epoch))) return;
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
            // an update about Current is never a line the chat writes by itself: the card refreshes in place
            // (below) and, with speech on, it is said aloud
            const preview = String(fresh.preview || "").replace(/\s+/g, " ").trim().slice(0, 180);
            const line = `New message from ${fresh.who || "someone"} arrived on ${fresh.ref || fresh.title || "this thread"}`
              + (preview ? `: “${preview}”` : "") + ". The context is refreshed."
              + (fresh.rid ? " The earlier draft is now out of date; redraft it before sending." : "");
            speakRef.current?.(line);
          }
          const refreshed = refreshCurrentPresentation(cur, fresh);
          if (newer || refreshed !== cur) putOnTable(refreshed, "sync");
        } else if (cur?.key && "current" in data && data.current === null) {
          selectionRef.current = null;
          putOnTable(null, "sync");
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
      else setPileRead(true);                 // a failed read draws what it drew before; the retry fills it in
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
  }, [readChat, putOnTable]);
  useEffect(() => { loadPileRef.current = loadPile; }, [loadPile]);
  // the FYI band asks for its next page - opened, or its "N more fyi" scrolled into view. One ask at a time; the cached rail
  // answers it (no force), and a read already in flight is followed by one that carries the bigger page.
  const morePending = useRef(false);
  const moreFyi = useCallback(() => {
    if (morePending.current || !fyiTail(pileRef.current).length) return;
    morePending.current = true;
    fyiWant.current += 4 * FYI_PAGE;
    Promise.resolve(pileFlight.current).catch(() => {}).then(() => loadPileRef.current?.()).finally(() => { morePending.current = false; });
  }, []);
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
  // the Advisor's line for the item on the table: read when the table changes and when its event lands; a changed
  // item answers {} and the pill goes with it - nothing on the rail moves for it (spec 2026-10-12, mechanics 3-5)
  // ...stamped with the key it was read FOR, and a read that comes back after the table moved on is dropped
  const adviceAsk = useRef(0);
  // `asking`: the key a read is out for - the strip says "Thinking about this one…" while the table waits on it, so the row with
  // nothing dark is never read as having nothing to do
  const [asking, setAsking] = useState(null);
  const readAdvice = useCallback(async (key, keep, again = false) => {
    const n = ++adviceAsk.current;
    if (!keep) setAdvice(null);                     // a new item starts with no line, never the last item's
    setAsking(key || null);
    if (!key) return;
    let got = null;
    // ...and {"none":"no_ai"}: no AI connected is said once, with the way to connect one, instead of a strip that stays empty (U3)
    let read = { advice: null, asking: null };
    try { read = adviceRead((await api.get("/api/advice", { params: { key } })).data, key); got = read.advice; }
    catch { got = null; }
    if (n !== adviceAsk.current) return;
    // ...pending is the Advisor judging it now: the line comes by the `advice` event. One that never lands is asked again once, and
    // then the quiet line goes - never a "Thinking" that stands for good
    setAdvice(got); setAsking(again ? null : read.asking);
    if (read.asking && !again) setTimeout(() => { if (n === adviceAsk.current) readAdvice(key, true, true); }, 20000);
  }, []);
  // ...re-read when the table changes AND when the card on it refreshes (a reply landing keeps the key and moves the
  // revision: the old pill must go), and when the Advisor's own event names this item or one of its aliases
  // ...and when its lane moves (an agent continued is at work: its "waiting on you" line must go)
  useEffect(() => { readAdvice(onTable); setChanged(null); }, [onTable, readAdvice]);
  useEffect(() => { if (onTable) readAdvice(onTable, true); }, [currentItem?.view_revision, currentItem?.lane]);   // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => onLive("advice", (ev) => {
    const key = adviceKeyFor(ev, currentRef.current || (cardRef.current ? { key: cardRef.current } : null));
    if (key) readAdvice(key, true);
  }), [readAdvice]);
  // ...and after EVERY press on the item, once it settles: the revision covers what an act leaves (advisor.revision - a draft sent,
  // an act refused), so a line judged before the Send is never read back over its "Sent" (2026-10-19)
  const onTableRef = useRef(null);
  useEffect(() => { onTableRef.current = onTable; }, [onTable]);
  useEffect(() => onPressed(() => { if (onTableRef.current) readAdvice(onTableRef.current, true); }), [readAdvice]);
  // LIT AND PRESSED (the deep dive, 2026-10-20): each press on the row, Next included, while a line is shown says what was lit and the
  // revision it was judged at (advisor.press) - the evidence the owner's moves are learned from. Nothing on screen changes for it.
  const shownRef = useRef(null);
  const notePress = useCallback((pressed) => {
    const a = shownRef.current;
    if (!a?.key || !a.verb || !pressed) return;
    api.post("/api/advice/press", { key: a.key, advised: a.verb, pressed, revision: a.revision || null }).catch(() => {});
  }, []);
  useEffect(() => onPressing((id) => notePress(verbOfRow(id) || String(id || "").split(":").pop())), [notePress]);
  // ARRIVING (welcome.arrive): the page opening, or the window coming back into focus, is the owner sitting down - the
  // first time on a new day, or after a long gap, the chat opens with the day in a breath. Leaving is noted too, so "what
  // came in while you were away" counts from when they actually went. Code on the server, never a model; a miss is silent.
  useEffect(() => {
    if (!active) return undefined;
    let last = 0;
    const arrive = (leaving = false) => {
      if (!leaving && Date.now() - last < 60_000) return;
      if (!leaving) last = Date.now();
      api.post("/api/concierge/arrive", { leaving }).then(({ data }) => { if (data?.said || data?.drawn) readChat().catch(() => {}); }).catch(() => {});
    };
    const back = () => { if (document.visibilityState !== "hidden") arrive(false); };
    const away = () => arrive(true);
    arrive(false);
    window.addEventListener("focus", back); window.addEventListener("blur", away);
    document.addEventListener("visibilitychange", back);
    // a greeting held for the startup catch-up (welcome.py: it said "nothing new came in" while the mail was still being read, B4):
    // the server says when the mail is in, and the page asks again - past the minute's throttle, which the catch-up can beat
    const off = onLive(["arrive"], (ev) => { if (ev?.type === "arrive") { last = 0; arrive(false); } });
    return () => { off(); window.removeEventListener("focus", back); window.removeEventListener("blur", away); document.removeEventListener("visibilitychange", back); };
  }, [active, readChat]);
  // Writes push an event and force one fresh rebuild. The timer is only a disconnected-socket
  // safety net: rebuilding this multi-source pile every five seconds starved Board, Tasks and
  // Past chats behind work whose answer had not changed.
  // It rebuilt the pile every 30 s even under a live socket. With pushes arriving the pile only needs
  // what no write announces - a Later coming due - so every tenth tick; the chat is still read each tick
  // (readChat). The first call is the tab becoming active, with the live listener off until then: a full read.
  useEffect(() => {
    let n = 0, first = true;
    return pollWhileActive(active, () => {
      if (first || !liveUp() || ++n % 10 === 0) loadPile(false);
      else readChat().catch(() => { /* the next tick reads again */ });
      first = false;
    }, 30000);
  }, [active, loadPile, readChat]);
  // A TURN FROM THE PHONE shows here as it happens: the dots while WhatsApp is being answered, and the words the
  // moment they are sent - it used to wait for the 30 s tick (the owner, 2026-09-24: "it takes 20 seconds from when
  // message is responded to in whatsapp to show up on the assistant")
  const [phoneBusy, setPhoneBusy] = useState(false);
  const [mailReading, setMailReading] = useState(false);
  // set up when the page opened? then the canvas IS the setup until its walk starts (FirstRun.jsx); never in the demo
  const [firstRun, setFirstRun] = useState(false), [setupTodo, setSetupTodo] = useState("");
  setupOn.current = firstRun;
  const setupRef = useRef(null);
  useEffect(() => {
    // the static demo has no first run: its top-bar Setup says how to install Taskuary (setup() below), and nothing more
    if (DEMO) {
      const show = () => setupRef.current?.();
      window.addEventListener("tq-first-run", show);
      return () => window.removeEventListener("tq-first-run", show);
    }
    // ...only an install with nothing sorted yet opens ON it: one already reading mail opens on its day, and the cards are a press away
    // ...until the owner FINISHES it (Finish setup / Walk me through my tasks): it used to end itself on the first sorted email and
    // leave a half-made day under a lone button (the owner, 2026-10-15). An install that was working before is finished (settle_existing),
    // and a server that does not say (an older one) is never read as "not finished": only an explicit false opens setup
    api.get("/api/setup/first-run").then(({ data }) => { if (data?.step && data.dismissed === false) setFirstRun(true); }).catch(() => {});
    const show = () => setupRef.current?.();                    // the top bar's setup chip asks for the cards
    // what is next, for the rail - read again whenever the first run moves a step (FirstRun fires tq-setup-changed)
    const todo = () => api.get("/api/setup/first-run").then(({ data }) => setSetupTodo(data?.todo || "")).catch(() => {});
    todo();
    window.addEventListener("tq-first-run", show); window.addEventListener("tq-setup-changed", todo);
    return () => { window.removeEventListener("tq-first-run", show); window.removeEventListener("tq-setup-changed", todo); };
  }, []);       // the launch still reading the mail (SinceBlock): the counts wait
  useEffect(() => onLive(["chat-changed"], (ev) => {
    setPhoneBusy(!!ev?.thinking);
    readChat().catch(() => { /* the tick reads again */ });
  }), [readChat]);
  // a sync lands rows several times a second; one forced rebuild after the burst, not one per row -
  // and a CEILING, because a run that keeps talking pushed the trailing timer out indefinitely and
  // left the pile on its 30-second safety poll (2026-09-10 audit).
  useEffect(() => {
    if (!active) return undefined;
    // ...and not at all when a forced load already began after the newest event: the turn that
    // caused the write reloaded the rows itself, and this was the fourth full build of one press
    return onLive(["feed-changed", "task-changed"], (ev, meta) => { if (!coveredByReload(meta, forcedLoadStartedAt.current)) loadPile(true); }, { wait: 1500, max: 5000 });
  }, [active, loadPile]);
  // ...but THE ITEM ON THE TABLE is read at once: its agent asking is the one change the owner is looking at, and the burst's 1.5s
  // left its rail row saying "working" under a header that already said it waited on them (G7, 2026-10-20)
  useEffect(() => {
    if (!active) return undefined;
    return onLive("task-changed", (ev, meta) => {
      const tid = Number(ev?.task_id) || 0;
      if (tid && tid === currentRef.current?.tid && !coveredByReload(meta, forcedLoadStartedAt.current)) loadPile(true);
    }, { wait: 150, max: 600 });
  }, [active, loadPile]);
  // ...but only once there IS a conversation: on the empty welcome it scrolled "Good morning" and the
  // day's meetings off the top of the screen (the owner, 2026-09-23: "this is cutting off the top")
  // ...on a NEW line, not on a line's own state changing: browsing (a chip, a card, Back) rewrites its line in place, and
  // pinning the bottom there threw the card you had just opened out of view (the canvas redesign, 2026-09-29)
  const holdBottom = useRef(false);        // a browse card is being read from its top
  // THE END OF THE THREAD, WHEN A TASK VIEW ENDS IT, IS THAT VIEW'S TOP (the owner, 2026-10-18: "top is not high enough ... should it
  // not fill the entire screen"): the view is the body's height, so scrolled to the bottom it stood ~30px low under a strip of the
  // line before it. Its top meets the body's top instead - the same place the pin puts it.
  // STUCK: the thread was put at its end and nobody has scrolled it since. The thread growing then keeps it there however much it
  // grows - a reload drew the chat, then the task view, 285px at once, and the observer's "within 240px of the end" let go of it, so
  // the answer the reload was for sat under the fold (the 2026-10-19 UI walk)
  const stuck = useRef(false);
  const toEnd = (el) => {
    const live = [...el.querySelectorAll(".tq-canvas-live")].pop(), box = el.getBoundingClientRect(), r = live?.getBoundingClientRect();
    const top = r && box.bottom + (el.scrollHeight - el.scrollTop - el.clientHeight) - r.bottom < 48;
    el.scrollTop = top ? el.scrollTop + r.top - box.top : el.scrollHeight;
    stuck.current = !top;
  };
  // THE CARD ON THE TABLE STAYS IN VIEW (B15; the walk's SEEN, 2026-10-17): putOnTable pins it, and the pin brings its top to the
  // top of the view once it mounts and KEEPS it there while it loads and grows - a receipt or a failure under it, a draft filling
  // in, used to push it down until only its header (or nothing) stood above the row. The pin lets go when the owner scrolls, types,
  // or the assistant says something that is not a receipt (an answer, a proposal to confirm) - and the next item takes it over.
  const keepTable = useCallback(() => {
    const body = bodyRef.current;
    if (!pin.current || !body) return false;
    const el = [...body.querySelectorAll(".tq-canvas-live, .tq-live-card")].pop();
    if (!el) return false;
    holdBottom.current = true;
    // ...UNLESS A LINK NAMED SOMETHING IN IT (appLinks.focusPlace marks it [data-tq-held]): then that is what is held, in the middle.
    // Two holds on one scroll fought - the card's top pulled back over a setting a search hit had brought up (verify, 2026-10-19)
    const held = el.querySelector("[data-tq-held]"), b = body.getBoundingClientRect(), r = (held || el).getBoundingClientRect();
    // ...and A MOVE LIT ON THE CARD stays clear of a phone's docked strip and row (inView.floorOf): held by the card's top, the refused
    // send's Redraft was pulled back under the dock the moment it was scrolled clear (the matrix's phone pass, 2026-10-20)
    const lit = !held && el.querySelector("[data-tq-lit]")?.getBoundingClientRect();
    const off = held ? r.top + r.height / 2 - (b.top + body.clientHeight / 2) : Math.max(r.top - b.top, lit?.height ? lit.bottom + 8 - floorOf(body, el) : -Infinity);
    if (Math.abs(off) > 2) body.scrollTop += off;      // the body alone scrolls - scrollIntoView moved the whole page as well
    return true;
  }, []);
  // a NEW line lets go of the hold: the answer to "what does this one do?" must land in view (the final review) - a pinned card
  // stays, and a line that is not a receipt lets go of it
  useEffect(() => {
    const m = msgs[msgs.length - 1];
    if (pin.current && m && (m.proposal || (!m.card && m.role !== "receipt" && m.role !== "browse"))) pin.current = false;
    if (keepTable()) return;
    holdBottom.current = false; const el = bodyRef.current; if (el && el.querySelector(".tq-msg:not(.tq-welcome-msg)")) toEnd(el);
  }, [msgs.length, busy]);   // eslint-disable-line react-hooks/exhaustive-deps
  // ...and again whenever the thread GROWS - a card that loaded its draft, a report that unfolded - so the
  // bottom of the conversation is always what you see, unless you have scrolled up to read, or a card is pinned
  useEffect(() => {
    const el = bodyRef.current, inner = el?.firstElementChild;
    if (!el || !inner || typeof ResizeObserver === "undefined") return undefined;
    const ro = new ResizeObserver(() => { if (keepTable()) return; if (!holdBottom.current && (stuck.current || el.scrollHeight - el.scrollTop - el.clientHeight < 240) && el.querySelector(".tq-msg:not(.tq-welcome-msg)")) toEnd(el); });
    ro.observe(inner);
    // the owner's own scroll is theirs: the pin lets go, and so does the end - until they scroll back down to it
    const own = () => { pin.current = false; stuck.current = false; };
    const atEnd = () => { if (el.scrollHeight - el.scrollTop - el.clientHeight < 4) stuck.current = true; };
    el.addEventListener("wheel", own, { passive: true }); el.addEventListener("touchmove", own, { passive: true });
    el.addEventListener("scroll", atEnd, { passive: true });
    // ...and so is the owner's KEYBOARD (the 2026-10-19 UI walk): a card filled in by Tab and Enter snapped back to its top on Save -
    // 588px up, the button just pressed gone - because only a wheel or a finger let go of the pin. A key pressed in the thread, or
    // focus the keyboard moved into it (a Tab from the box below), is the owner working there; focus the app moves itself is not.
    let keyAt = 0;
    const key = () => { keyAt = Date.now(); }, typed = () => { pin.current = false; };
    const tabbed = () => { if (Date.now() - keyAt < 800) pin.current = false; };
    const bar = (e) => { if (e.target === el) own(); };             // the scrollbar: a press on the body itself, not on a line in it
    document.addEventListener("keydown", key, true); el.addEventListener("keydown", typed); el.addEventListener("focusin", tabbed);
    el.addEventListener("pointerdown", bar);
    return () => {
      ro.disconnect(); el.removeEventListener("wheel", own); el.removeEventListener("touchmove", own); el.removeEventListener("scroll", atEnd);
      document.removeEventListener("keydown", key, true); el.removeEventListener("keydown", typed); el.removeEventListener("focusin", tabbed);
      el.removeEventListener("pointerdown", bar);
    };
  }, [walk, keepTable]);
  useEffect(() => { keepTable(); }, [msgs, keepTable]);
  // a box opened under the card (Continue's note, Close with a note) is where the owner is now: the pin lets go before the
  // thread's resize would scroll the card back over it (a layout effect - it must land before the observer runs)
  useLayoutEffect(() => { if (continueOn || noteOn) pin.current = false; }, [continueOn, noteOn]);

  const items = pile?.items || [];
  const ready = items.filter((i) => !i.settling);
  const canAdvance = canAdvanceSelection(pile, ready, only.current);
  const pileLoading = pile === null && !pileRead;
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
    // a task opened to start its agent or an act (the Board's, a workflow's) carries that start onto the row the server answered with
    const extra = openExtra.current; openExtra.current = null;
    const card = data.item ? { ...data.item, ...(extra && extra.tid === data.item.tid ? { autostart: extra.autostart, act: extra.act } : {}) } : null;
    // the end of the walk's "Open TQ-12" words come as `chips`: dropped here, its only button was a Next that said it again
    // ONE COPY PER ITEM (2026-10-19 UI walk): an item opened again - from search, the Board, the rail - moves its line to the end, never a second
    setMsgs((m) => placeLine(m, { id: `a${Date.now()}`, role: "assistant", text: data.say, options: data.options || [], chips: data.chips || [], card }));
    putOnTable(card);
    say(data.say);
    // the turn brought the rail as it left it: hold that, with the new table excluded. Nothing along
    // (the walk ran out, an older server, the demo) is the page's own load, as before.
    if (card && data.pile) holdPile(data.pile, nextSelectionScope(only.current, card.key));
    else { selectionRef.current = null; loadPile(true); }
  }, [holdPile, loadPile, putOnTable, say]);

  const ensureNextSelection = useCallback(async (scope) => {
    for (let attempt = 0; attempt < 2; attempt += 1) {
      const captured = selectionRef.current;
      if (captured && sameSelectionScope(captured.scope, scope)) return captured;
      await loadPileRef.current?.(true);
    }
    const captured = selectionRef.current;
    return captured && sameSelectionScope(captured.scope, scope) ? captured : null;
  }, []);

  // a line of the assistant's own that needs no turn - a section walk running out
  const noteLine = useCallback((text) => setMsgs((m) => [...m, { id: `s${Date.now()}`, role: "assistant", text }]), []);
  // pull the next thing (or the one named; or the next piece of mail) out of the pipe and say it
  // `blind`: pressed with no item in front of the owner (the walk's start, a chat chip on an empty table) - see the retry below
  const surface = useCallback(async (key = null, asUser = null, leaving = null, blind = false) => {
    if (busy || resetting || handoff || turnFlight.current) return;
    // WALKING A SECTION: Next stays inside it - the next of its rows the walk has not shown - and once it is empty it
    // says so and the walk goes on as normal (the canvas redesign, 2026-09-29)
    if (!key && sectionRef.current) {
      const sec = sectionRef.current;
      if (currentRef.current?.key) sec.seen.add(currentRef.current.key);
      let nxt = sectionNext(pileRef.current?.items, sec.level, sec.seen);
      if (!nxt && sec.level === "fyi" && fyiTail(pileRef.current).length) {
        fyiWant.current += 4 * FYI_PAGE;
        await loadPileRef.current?.();
        nxt = sectionNext(pileRef.current?.items, sec.level, sec.seen);
      }
      if (nxt) { sec.seen.add(nxt.key); key = nxt.key; }
      else {
        sectionRef.current = null;
        noteLine(sectionDone(sec.level));
      }
    }
    turnFlight.current = true;
    setBusy(true); setErr("");
    if (!key) navHow.current = "replace";            // the walk's Next is a stream, not a stack: the address follows, Back does not
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
    if (optimisticId) setMsgs((m) => pickLine(m, { id: optimisticId, role: "user", text: asUser, pick: key || undefined }));
    // NEXT PUTS THE TABLE DOWN AT ONCE, the way "All read, next" does (the owner, 2026-09-30: "when you hit next on a task it
    // does not close the current task instantly ... the close of past one should be instant"): the task folds to its title
    // line now and the "…" shows while the next one loads; a Next that fails opens it again
    const putDown = !key && currentRef.current?.key ? currentRef.current.key : null;
    if (putDown) { setExpanded(false); setFoldedKey(putDown); }
    try {
      // A named Timeline/pile row remains an explicit pull. Automatic Walk/Next echoes the exact
      // server capture; demo/old-server payloads alone retain the legacy tokenless fallback.
      const navigation = capture ? nextSelectionBody(capture) : scope;
      let data;
      try { data = await turn({ mode: "next", key, leaving, ...navigation }); }
      catch (e) {
        // A BLIND PRESS HAS NO PICK TO PROTECT: the guard (PW-050) refuses a Next whose item is not the one the page shows,
        // and nothing was shown - a reply landing between the morning card and its button made the owner press twice
        // (2026-10-13). A plain stale refusal ran nothing, so the server's fresh capture is taken once, never more.
        const g = blind && selectionGuardDetail(e), fresh = g && !g.reason && g.retryable !== false ? captureNextSelection(g, scope) : null;
        if (!fresh || epoch !== chatEpoch.current) throw e;
        selectionRef.current = fresh;
        setPile((p) => replaceSelectionToken(p, g));
        data = await turn({ mode: "next", key, leaving, ...nextSelectionBody(fresh) });
      }
      landed(data);
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
      if (putDown) setFoldedKey((k) => (k === putDown ? null : k));
      setErr(errText(e));
    }
    turnFlight.current = false;
    setBusy(false);
  }, [busy, ensureNextSelection, handoff, landed, loadPile, noteLine, resetting, turn]);
  useEffect(() => { surfaceRef.current = surface; }, [surface]);
  const startFlight = useRef(false);
  // ONE ANSWER TO "CAN THE WALK START?" (the 2026-10-19 UI walk): the button greyed on one list and the press returned on another, so a
  // press could look taken and do nothing. Both read walkOff; the refs only close same-tick double presses the state has not caught.
  const walkOff = busy || resetting || !!handoff || starting;
  const start = async (what) => {
    if (walkOff || turnFlight.current || startFlight.current) return;
    startFlight.current = true;
    const epoch = chatEpoch.current;
    const said = "Walk me through my tasks.";
    setStarting(true); setErr("");
    const lineId = `u${Date.now()}`;
    setMsgs((m) => [...m, { id: lineId, role: "user", text: said }]);
    try {
      only.current = sharedFilter.current && sharedFilter.current !== "{}" ? `view:${sharedFilter.current}` : (pile?.canonical ? null : what);
      selectionRef.current = null;
      await loadPile(true);                   // validate/resume Current under the requested scope
      if (epoch !== chatEpoch.current || resettingRef.current) return;
      // the line is already on screen: surface must not post a second copy of it
      // resume what is on the table only if you have not PASSED it: a passed item waits in Passed for
      // its hour, and starting the walk put it straight back in front of you (the owner, 2026-09-23:
      // "it's in the passed section but showing up on assistant first")
      if (!currentRef.current || currentRef.current.surfaced) await surface(null, null, null, true);
    } catch (e) {
      // the owner's line is on screen now, so a failure has to be answered on screen too -
      // an unhandled rejection would leave "Walk me through my tasks." sitting there alone. The line is taken back, so the
      // welcome block (drawn on an empty chat) returns with its button - kept, it hid the only way to try again
      setMsgs((m) => m.filter((x) => x.id !== lineId));
      setErr(`The walk didn't start - ${errText(e)}. Press Walk me through my tasks to try again.`);
    } finally {
      startFlight.current = false;
      setStarting(false);
    }
  };
  // the Walk press kept while the pile loaded: run once the rows are in - and only if there is a walk to start, which is
  // exactly when the button would have been pressable had the rows been there
  // ...and kept while anything else holds the walk (walkOff): run then, never dropped by start()'s own refusal
  useEffect(() => {
    if (!walkQueued || pileLoading || walkOff) return;
    setWalkQueued(false);
    if (canAdvance) start(null);
  }, [walkQueued, pileLoading, canAdvance, walkOff]);   // eslint-disable-line react-hooks/exhaustive-deps

  // The day used to write itself the moment the page opened - a model call nobody asked for, which
  // also landed UNDER a "Set something up" the owner had already pressed (2026-09-03: "I hit new chat
  // to set something up and it ran the email walk through welcome command?"). The welcome block is the
  // door now: what is waiting, in facts, and the walk starts on a button.

  const send = async (line) => {
    // a picture alone is a line too: "what is this?" is what it means
    const images = line == null ? pics.paths : [];
    const t = String(line ?? text).trim() || (images.length ? "What is this?" : "");
    if (!t || busy || resetting || handoff || turnFlight.current || pics.busy) return;
    turnFlight.current = answering.current = true;
    setText(""); setBusy(true); setErr(""); setLit(null);
    const shots = line == null ? pics.imgs : [];
    if (images.length) pics.clear();
    setMsgs((m) => [...m, { id: `u${Date.now()}`, role: "user", text: t, shots }]);
    try {
      // a card browsed open is what "this" means - not the item folded above it (the final review)
      // ...and otherwise WHAT IS OPEN ON THE TABLE, whatever put it there (the owner, 2026-10-01: "the assistant has the open box in
      // context always regardless of what it is"): a task opened by name or from the rail never became the walk's `current`, so a
      // question about it went out about the walk's old item, or about nothing. The newest live card that is not folded leads.
      const table = msgs[interactiveCardIndex(msgs)]?.card;
      const tableKey = table?.key && table.key !== foldedKey && !browsing ? table.key : null;
      // ...and a page open beside it does not take it off the table: the Assistant's own "turn off background sync" opened Settings, and the
      // next "mark this done" went out about nothing while the rail still said ON THE TABLE (verify, 2026-10-19). Both go; the words say which
      const subject = tableKey || current || cardRef.current;
      const ask = () => turn({ mode: "say", text: t, key: subject, context_mid: currentItem?.mid && subject === current ? currentItem.mid : null,
                               open_card: openCardRef.current, images });
      const data = await ask().catch(async (e) => { if (!isCoveragePending(e)) throw e; await new Promise((r) => setTimeout(r, 1200)); return ask(); });
      if (data.context_update && noticedRef.current !== data.context_update) {   // not already said by the stream event
        setMsgs((m) => [...m, { id: `context${Date.now()}`, role: "assistant", text: data.context_update }]);
        say(data.context_update);
      }
      noticedRef.current = null;
      if (data.item) landed(data);                       // the words pointed at something: it is on the table now
      else {
        // THE ASSISTANT ROUTES (the owner, 2026-10-19: "it should just surface the correct button"): an act comes back as the row's own button
        // to light (`light`), the page that holds it (`open`) or a new job written into New (`new`) - never a card to confirm, and nothing runs
        setMsgs((m) => [...m, { id: `a${Date.now()}`, role: "assistant", text: data.say, options: data.options || [], chips: data.chips || [] }]);
        say(data.say);
        // THE PAGE IT NAMED, OPENED (appLinks.js): "set up Intacct" puts the Sage Intacct card beside the answer, not a sentence
        // about where to find it. Only a fresh reply opens one - a reloaded history draws its links, it does not open them.
        // ...a reply that carries `open` has decided for itself: "" is the app's own words (no AI), whose links are to press
        const page = "open" in data ? data.open : firstAppLink(data.say);
        if (page) openAppLink(page);
        if (data.new) browseRef.current?.("new", data.new);
        const l = lightOf(data.light);
        if (l) {
          setLit(l);
          // ...its item brought up the rail's road when it is not the one on the table, so the rail rings it
          const key = litPull(l, { key: tableKey || current, tid: currentItem?.tid });
          if (key) deferInChat(() => { browseDown(); surfaceRef.current?.(key); }, 300);
          // ...and on the table already, a page open over it is put down: the lit button and its line stood hidden under Settings (verify,
          // 2026-10-19 - "mark this done" asked beside the page the Assistant had opened)
          else browseDown();
        }
        if (data.decision) await decide(data.decision, data);  // the two immediate exceptions: a reply drafts, Next moves (PW-126/128)
      }
    } catch (e) {
      // a typed line that got no answer ended on a red "Assistant request failed (500)" and an empty composer: the line is
      // above, so Try again sends it once more - and Next is there whatever the trouble was
      const why = errText(e), raw = /request failed|network error|stopped without|could not answer/i.test(why);
      if (!images.length) setText((v) => v || t);        // back in the box: a live card under it keeps the row, and its Try again with it
      if (demoNo(e)) setErr(why);
      else setMsgs((m) => [...m, { id: `r${Date.now()}`, role: "receipt", status: "error",
        text: e?.name === "AbortError" ? "Stopped." : raw ? "I didn't get an answer through. Nothing was changed." : `Not answered - ${why}`,
        chips: [{ ask: t, label: btn("try_again") }, ...((pile?.items || []).length ? [{ verb: "next", label: btn("next") }] : [])] }]);
    }
    turnFlight.current = answering.current = false;
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
      // the reply's card comes up at once and its draft fills in behind it - never a wait on the model (2026-10-01)
      if (verb === "reply" && mid) {
        const data = await openReply(api, mid, d.text || null, d.cc || null);
        // a name to loop in that nobody by it has written as is said, never guessed: the card's CC row takes an address
        if (data?.cc_unknown?.length) setMsgs((m) => [...m, { id: `r${Date.now()}`, role: "receipt",
          text: `I have no address for ${data.cc_unknown.join(", ")} - add them in the reply's CC.` }]);
        // ...wherever it was asked about: "send Omar the answer" with nothing on the table was told "it lands below for your
        // yes", and the draft went onto his task with nothing landing here (2026-10-06)
        // ...and its Send is lit: drafting is not sending, the owner's press is (the owner, 2026-10-19)
        if (data.reviewId) {
          setLit({ verb: "approve", label: btn("approve"), line: `Read the draft, then press ${btn("approve")} when you're sure.`, key: `review:${data.reviewId}`,
                   tid: cur?.tid ? Number(cur.tid) : null, landed: false });
          if (!elsewhere) putOnTable(null, "sync"); deferInChat(() => surfaceRef.current?.(`review:${data.reviewId}`), 300); return;
        }
        loadPile(); return;
      }
      if (verb === "redraft" && cur?.rid && mid) {
        const { data } = await api.post(`/api/messages/${mid}/reply`, { draft: true, redraft: true, instruction: d.text || null });
        // "below" only when it lands below: a redraft on another task said "read it below" over nothing (2026-10-19 UI walk) - there
        // the receipt names the task and its chip opens it
        const ref = cur.ref || `TQ-${String(cur.tid).padStart(4, "0")}`;
        const there = elsewhere && cur.tid ? { tid: cur.tid, ref, chips: [{ verb: "opentask", tid: cur.tid, label: `Open ${ref}` }] } : {};
        setMsgs((m) => [...m, { id: `r${Date.now()}`, role: "receipt", ...there, text: data.draft
          ? (there.tid ? `Rewritten on ${ref} - read it there before you send it.` : "Rewritten - read it below before you send it.")
          : `I could not rewrite it here; edit the draft on ${there.tid ? ref : "the card"} and send that.` }]);
        if (!elsewhere) { putOnTable(null, "sync"); deferInChat(() => surfaceRef.current?.(`review:${cur.rid}`), 300); } else loadPile();
        return;
      }
      if (verb === "setting" || verb === "forwarded") { loadPile(); return; }   // Taskuary put these on the task itself
      setMsgs((m) => [...m, { id: `r${Date.now()}`, role: "receipt", tid: cur?.tid, ref: cur?.ref,
                              text: `I couldn't line that up${cur?.ref ? ` - ${cur.ref} is untouched` : ""}. Say it again, or use the buttons on the card.`, chips: [{ verb: "next", label: btn("next") }] }]);
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
      catch (e) {
        if (demoNo(e)) { setErr(errText(e)); return; }                  // the demo's own line, not a failed receipt
        const b = e?.response?.data || {};
        res = e?.response?.status === 409 ? { status: b.status || "stale", error: b.detail || errText(e), receipt: b.receipt, chips: b.chips || [] }
          : { status: "error", error: b.detail || errText(e) };
      }
      const out = afterExecute(p, res);
      const step = afterConfirm(p, out, current);
      // a sweep cleared what was on the table too: the receipt carries Next, and the walk waits for it
      // ...and an act that did NOT happen carries its way on (concierge.recover): Try again, GitHub's own offers, the
      // item's other verbs, Next - it said "Not done" and offered nothing (2026-09-29)
      // (the repositories stay on the proposal card's own picker here - the chat has them only where there is no card)
      // ...and a SEND that went carries its own (concierge.sent_chips): Mark done and Next - the item stays on the table
      const chips = (out.status !== "done" || p.kind === "review.approve") && res?.chips?.length ? res.chips.filter((c) => !(out.repo && c.verb === "repo"))
        : step === "offer" || out.status !== "done" ? [{ verb: "next", label: btn("next") }] : [];
      setMsgs((m) => [...m.map((x) => (holdsProposal(x, p) ? { ...x, proposal: { ...x.proposal, ...(p.replaces ? p : {}), status: out.status, repo: out.repo || null, outcome: res?.outcome || null } } : x)),
                       { id: `r${Date.now()}`, role: "receipt", status: out.status, text: out.receipt, tid: p.tid || res?.outcome?.taskId, ref: p.ref || res?.outcome?.ref, chips }]);
      onChanged?.();
      // the server already settled or closed the item; a settle proposal (later, tomorrow, done) must not be
      // re-marked "done" by the page, so it advances without the settle post. A hand-off that STARTED advances
      // once the same way (PW-135): the delegated task stays in Unread as Working, nothing is settled; a
      // repository still to choose, a failed start or a cancel keep the item where it is. A sweep that
      // cleared the table settled it too, but does NOT walk on: the table is put down and Next is offered.
      if (step === "watch") { clearTable(); loadPile(); openTaskCard({ tid: out.tid }); }
      else if (step === "advance") advance();
      else if (step === "settle") await done(null);
      else { if (step === "offer") clearTable(); loadPile(); }
    } finally { setBusy(false); }
  };
  // a card button on ONE entry (PW-151): the same proposal road the words take, minus the interpreter - the
  // target is explicit. The card lands in the chat and runs from its own button, like any proposal.
  const proposeDirect = async (verb, key, table = false, revision = null) => {
    // the pill carries the stamp it was judged at, and a moved item refuses it (409); the plain road is unchanged
    const { data } = revision ? await api.post("/api/concierge/propose", { verb, key, table, revision })
      : await api.post("/api/concierge/propose", { verb, key, table });
    // refused before any proposal existed: the reason and this item's other words, as a line of its own (no card to confirm)
    if (!data.id) {
      setMsgs((m) => [...m, { id: `a${Date.now()}`, role: "assistant", text: data.say, options: [], card: { kind: "words", chips: data.chips || [] } }]);
      return data;
    }
    setMsgs((m) => [...m, { id: `a${Date.now()}`, role: "assistant", text: data.say, options: [], proposal: data,
                            card: { kind: "proposal", key: data.key, title: data.label, op: data.id, tid: data.tid, ref: data.ref } }]);
    say(data.say);
    return data;
  };
  // THE ADVISOR'S MOVE, pressed: a 409 means the item moved since it was judged - the old button would fail the same way on every
  // press, so the advice is read again for the item as it is now and the strip says so (B6)
  // ONE ROAD FOR AN ADVISOR PRESS (2026-10-18): the Advisor's pick is the row's own button whenever the row has it - pressed, it
  // runs that button's handler, exactly as a click does (a draft's Send sends the box as edited). It went to the proposal road
  // instead and drew an inline "Send / Cancel" card in the chat (the walk's INLINE). Only a verb the row lacks goes there.
  const pressAdvice = async (a, anchor = null) => {
    const key = a.for || a.key;
    setChanged(null);
    const real = advisedIn(rowNow().list.filter((v) => !String(v.id).startsWith("advice:")), a);
    if (real) { pressRow(real.id, null, anchor); return null; }
    notePress(liveVerb(a.verb));                   // a move the row has no button for is pressed here, not through the row
    // a fix is a place (advisor.for_key's href), never a proposal: with no '<rid>:fix' on the row it opens the place itself
    if (liveVerb(a.verb) === "fix" && a.href) { openAppLink(a.href); return null; }
    if (a.verb === "answer_agent") { askAnswer(currentRef.current); return null; }
    // MAKE A TASK TO FIX THIS (advisor.failure): a failure nothing here fixes becomes a task of its own, carrying what failed - made by
    // the same tool the assistant uses, so it has a receipt like any act, then opened
    if (liveVerb(a.verb) === "new_task" && a.task) {
      try {
        const made = await runOperation(api, "task.create_from_text", 0, { text: a.task.text, title: a.task.title, kind: "task" });
        if (made?.taskId) openTaskRef.current?.({ tid: made.taskId });
        noteLine(`Made ${made?.ref || "a task"} to fix it - what failed and why are on it.`);
      } catch (e) { if (demoNo(e)) setErr(errText(e)); else throw e; }
      return null;
    }
    // a move that is no proposal (it drafts, asks for a day, or asks what to add) takes the chip's own road - the server refuses it
    if (["reply", "redraft", "defer", "continue"].includes(liveVerb(a.verb))) { await runChip({ verb: liveVerb(a.verb) }); return null; }
    try { return await proposeDirect(a.verb, key, true, a.revision); }
    catch (e) {
      if (demoNo(e)) { setErr(errText(e)); return null; }          // the demo saying no is a line in the chat, not the row's error
      if (e?.response?.status !== 409) throw e;
      setChanged({ for: key, reading: true }); await readAdvice(key); setChanged({ for: key });
      return null;
    }
  };
  // ANSWER IT has nothing to send until the owner says it: pressed bare it was refused ("What should I tell...?"). The box is where
  // the answer goes - the server passes what is typed over a waiting agent to it
  const askAnswer = (item) => {
    noteLine(`Type your answer below - it goes straight to ${item?.agent || "the agent"} that is waiting.`);
    setTimeout(() => composeRef.current?.focus(), 0);
  };
  // ONE road for every action word in the chat. A word the assistant offered is a word that runs: the
  // verb goes to the same proposal endpoint a card button uses, with the target explicit. The two that
  // are not proposals keep their own immediate behaviour - a reply DRAFTS (PW-126), Next moves the walk
  // and puts down what it left. An OPTIONS choice is not a verb at all: it goes back as the owner's words.
  const runChip = async (c, anchor) => {
    if (busy || resetting || handoff || !c) return;
    if (c.ask) { send(c.ask); return; }
    if (c.verb === "newtask") { browseRef.current?.("new", {}); return; }
    // THE PLACE THAT FIXES IT (concierge.recover, outbound.Fixable): an app link, opened on the canvas like any other
    if (c.verb === "go" && c.href) { openAppLink(c.href); return; }
    // ...a receipt's own task, and its bug report, from the row (they were buttons in the line)
    if (c.verb === "opentask" && c.tid) { openTaskRef.current?.({ tid: c.tid }); return; }
    if (c.verb === "bug") { openBugReport(shownError(c.text)); return; }
    if (c.verb === "setupask") { askSetup(); return; }
    if (c.verb === "tour") { await setup(); return; }
    const item = currentRef.current || currentItem;
    const key = item?.key || current;
    if (c.verb === "next") { surface(null, null, key, !item); return; }
    // MARK DONE UNDER A SEND'S RECEIPT: the task it names, closed by the one close - the item it was may be gone already (its draft
    // went), so this never asks the table for it - then the walk goes on
    if (c.verb === "close" && c.tid) {
      setBusy(true); setErr("");
      try {
        await runOperation(api, "task.complete", c.tid);
        setMsgs((m) => [...m, { id: `r${Date.now()}`, role: "receipt", text: `${c.ref || "The task"} marked done.` }]);
        advance(null, true);
      } catch (e) { setErr(errText(e)); } finally { setBusy(false); }
      return;
    }
    if (c.verb === "answer_agent") { askAnswer(item); return; }
    // one item by name - one the walk already showed and will not repeat yet ("N things you've already seen")
    if (c.verb === "open" && c.key) { surface(c.key); return; }
    // REMIND ME asks for the day - the task page's own picker - and the walk moves on once it is put away
    // CONTINUE SESSION asks what to tell it (optional), then the agent picks up - the walk moves on (A19)
    if (c.verb === "continue") { if (item?.tid) setContinueOn({ task: { TaskId: item.tid }, anchor: anchor || null, ref: item.ref }); return; }
    // ...an Advisor idea's own day when it has no task: the idea sleeps until then (C5, 2026-09-27)
    if (c.verb === "defer" && item?.kind === "idea" && item?.idea) { setRemindOn({ task: { TaskId: `idea-${item.idea}` }, path: `/api/assistant/ideas/${item.idea}/snooze`, anchor: anchor || null, ref: item.ref }); return; }
    // ...and with its agent still open the picker says to Stop and save first, instead of offering days (2026-10-01)
    if (c.verb === "defer") { if (item?.tid) setRemindOn({ task: { TaskId: item.tid, RemindAt: item.remind_at || "" }, anchor: anchor || null, ref: item.ref, live: agentOpen(item) }); return; }
    if (c.verb === "reply" || c.verb === "redraft") { await decide({ verb: c.verb }); return; }
    // A FAILED ACT'S WAY ON (concierge.recover): the same confirmation once more, or the close-out's own GitHub button
    if (c.verb === "retry" && c.op) {
      await runProposal({ id: c.op, version: c.version, kind: c.kind, label: btn("try_again"), key: item?.key, tid: item?.tid, ref: item?.ref,
                          settles: !!c.settles });
      return;
    }
    // ...a failed proposal told something more (Send anyway: past a delivery nobody can confirm) - the same proposal, revised, run again
    if (c.verb === "revise" && c.op) {
      setBusy(true); setErr("");
      let op = null;
      try { op = (await api.patch(`/api/operations/${c.op}`, { params: c.params || {} })).data; }
      catch (e) { setErr(errText(e)); }
      finally { setBusy(false); }
      if (op) await runProposal({ ...op, label: c.label, key: item?.key, tid: item?.tid, ref: item?.ref, settles: !!c.settles });
      return;
    }
    // ...a hand-off that stopped for a repository: that repository, then the same confirmation again
    if (c.verb === "repo" && c.op) {
      setBusy(true); setErr("");
      let op = null;
      try { op = (await api.patch(`/api/operations/${c.op}`, { params: { ...(c.params || {}), repo: c.repo } })).data; }
      catch (e) { setErr(errText(e)); }
      finally { setBusy(false); }
      if (op) await runProposal({ ...op, label: c.label, key: item?.key, tid: item?.tid, ref: item?.ref, settles: !!c.settles });
      return;
    }
    if (c.verb === "closeout" && c.rid) {
      setBusy(true); setErr("");
      try {
        const { data } = await api.post(`/api/reviews/${c.rid}/closeout/${c.act}`);
        setMsgs((m) => [...m, { id: `r${Date.now()}`, role: "receipt", tid: item?.tid, ref: item?.ref,
                                text: `${data?.said || c.label}. Press ${btn("approve", "action")} again once the checks pass.` }]);
      } catch (e) { setErr(errText(e)); } finally { setBusy(false); }
      return;
    }
    setBusy(true); setErr("");
    try {
      // Prep me is gone (buttons.json `removed`): an old saved chip of a removed verb runs as the verb it became, or not at all
      const verb = liveVerb(c.verb);
      if (!verb) return;
      const pr = c.revision ? await pressAdvice({ verb, key, revision: c.revision }) : await proposeDirect(verb, key, true, null);
      if (pr?.auto) await runProposal(pr);
    } catch (e) { setErr(errText(e)); } finally { setBusy(false); }
  };
  // a dry run of a proposed report (PW-195): the server refuses anything that could write
  const previewProposal = async (p) => (await api.post(`/api/operations/${p.id}/preview`)).data;
  const cancelProposal = async (p) => {
    try { await api.delete(`/api/operations/${p.id}`); } catch { /* it may be gone already */ }
    const out = afterCancel(p);
    setMsgs((m) => [...m.map((x) => (holdsProposal(x, p) ? { ...x, proposal: { ...x.proposal, ...(p.replaces ? p : {}), status: out.status } } : x)),
                     { id: `r${Date.now()}`, role: "receipt", text: out.receipt, tid: p.tid, ref: p.ref, chips: [{ verb: "next", label: btn("next") }] }]);
  };
  // a card did its thing: say so in the thread, then move on
  // the table is put down - nothing is chosen in its place. Walking on is advance(), which is this
  // plus asking for the next thing; a sweep does only this and leaves Next to the owner's finger.
  const clearTable = () => { selectionRef.current = null; putOnTable(null, "sync"); };
  // `settled`: the server has answered already (a Mark done or Remind me that closed the task before calling here)
  const advance = (pile = null, settled = false) => {
    clearTable();
    onChanged?.();                                     // a draft may have gone out: the Review badge recounts
    // a settle that brought the rail back with it: held under the empty table's scope, and the walk needs
    // no half-second of grace - the server has settled already, and the timer only has to outlive this
    // render (a proposal's busy flag is released the moment its caller returns)
    if (pile) holdPile(pile, nextSelectionScope(only.current, null));
    setNextComing(true);
    deferInChat(() => surfaceRef.current?.(), pile || settled ? 120 : 500);
  };
  const done = async (receipt) => {
    // the card folds to its line the moment its verb is pressed - see interactiveCardIndex
    setMsgs((m) => { const i = interactiveCardIndex(m), out = i < 0 ? m : m.map((x, j) => (j === i ? { ...x, done: true } : x));
      return receipt ? [...out, { id: `r${Date.now()}`, role: "receipt", text: receipt }] : out; });
    setNextComing(true);
    let pile = null;
    // `only` rides along so the rail comes back captured under the scope this page walks with
    if (current) {
      try { pile = (await api.post("/api/funnel/settle", { key: current, verb: "done", only: only.current, fyi: fyiWant.current })).data?.pile || null; }
      catch (e) {
        // A receipt means the act already landed (a close, a sent reply) and only the settle after it failed - often with
        // the 422 "unavailable" that closing a task causes: walk on. Without one, gone already (404/422) is done too;
        // anything else did NOT happen, and folding the card and walking on said it had.
        if (!receipt && ![404, 422].includes(e?.response?.status)) {
          setNextComing(false);
          setMsgs((m) => [...m.map((x) => (x.done && x.card?.key === current ? { ...x, done: false } : x)),
            { id: `r${Date.now()}`, role: "receipt", status: "error", text: "Not done - Taskuary didn't answer. It is still here; press it again.", chips: [{ verb: "next", label: btn("next") }] }]);
          return;
        }
      }
    }
    advance(pile);
  };
  // A SEND KEEPS THE ITEM ON THE TABLE (the owner, 2026-10-18: "sending and closing are two steps"): the card folds to its line, the
  // receipt says what went, and its row is the two ways on - Mark done (the one close) while there is a task, and Next. Nothing is
  // settled and the walk does not move: done() above did both, as if the send had finished the task.
  const sent = (receipt, tid = null, ref = null) => {
    setMsgs((m) => { const i = interactiveCardIndex(m), out = i < 0 ? m : m.map((x, j) => (j === i ? { ...x, done: true } : x));
      return [...out, { id: `r${Date.now()}`, role: "receipt", text: receipt, ...sentChips(tid, ref) }]; });
    onChanged?.(); loadPile();
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
  const askSetup = () => setMsgs((m) => [...m, { id: `a${Date.now()}`, role: "assistant", text: "Tell me what to set up - a report, a connection, an automation - and I'll take you through it here; nothing changes until you say so."
      + (canCode ? " If something has to be built, say send it to the coding agent." : ""),   // coding is offered only where a coding tool is connected
    card: { key: "setup", kind: "setup", lane: "report", title: "Set something up" }, options: [] }]);
  const [walking, setWalking] = useState(false);        // guards the chip against a double-click
  const setup = async () => {
    if (walking) return;
    // typed or pressed, Set up Taskuary is the one setup mode the top bar's Setup opens (the owner, 2026-10-16) - its card in the chat
    // was the same questions with the chat box still under them
    if (!DEMO) { setFirstRun(true); return; }
    if (DEMO) {
      setMsgs((m) => [...m, { id: `w${Date.now()}`, role: "assistant", text:
        "## Set up Taskuary on your own machine\n\nThis browser demo uses fictional data and cannot connect an inbox. "
        + "[Download Taskuary for Windows](https://github.com/ldbumble/taskuary/releases/latest/download/Taskuary.exe) or "
        + "[follow the installation guide](https://taskuary.com/docs/).\n\n"
        + "In your installed app: enter your name, choose an AI, connect one mailbox or chat, and sync your first messages. "
        + "The setup guide helps you through each step. Hosted AI receives the context needed for the task; a local model keeps those prompts on your machine." }]);
      return;
    }
    setWalking(true);
    try { pushStop((await api.get("/api/setup/walk")).data); }
    catch { setMsgs((m) => [...m, { id: `w${Date.now()}`, role: "receipt", status: "error", text: "The walk-through didn't load.", chips: [{ verb: "tour", label: btn("try_again") }] }]); }
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
        text: "Walk finished. Change my setup below starts it again any time.", chips: IDLE_CHIPS }]);   // the button it named had gone with the welcome block
    } catch {      // the card stays where it is; nothing was lost - but a press that did nothing says so
      setMsgs((m) => [...m, { id: `w${Date.now()}`, role: "receipt", status: "error", text: "That step didn't load. Press it again." }]);
    }
    finally { setWalking(false); }
  };
  // Start over: the server's reset (place -> 0), then the first stop as a fresh card. Not walkTo(0):
  // that is a move to stop 1 from wherever you were, and the receipt trail would read as one.
  const walkRestart = async () => {
    if (walking) return;
    setWalking(true);
    try { pushStop((await api.post("/api/setup/walk/reset")).data); }
    catch { setMsgs((m) => [...m, { id: `w${Date.now()}`, role: "receipt", status: "error", text: "The walk didn't start over. Press Start over again." }]); }
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
                              text: `${data.ref} — "${data.title}". The walk is below; nothing changes until you say so.` }]);
      enterWalk({ tid: data.taskId, ref: data.ref, title: data.title });
    } catch (e) { setErr(errText(e)); }
    setBusy(false);
  };
  // past chats are read, a page at a time (PW-157): listing them changes nothing on the server
  const [chatsNext, setChatsNext] = useState(null);
  const [chatsErr, setChatsErr] = useState("");
  const openChats = async () => {
    setChatsOpen(true); setChatsLoading(true); setChatsErr("");
    // said INSIDE the list: the page's own error line sits under this overlay, which read "No earlier chats yet." instead
    try { const { data } = await api.get("/api/concierge/chats", { params: { limit: 25 }, timeout: 10000 }); setChats(data.data || []); setChatsNext(data.next || null); }
    catch (e) { setChatsErr(`Past chats didn't load - ${errText(e)}`); }
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
    selectionRef.current = null; putOnTable(null, "sync");
    setMsgs([]); setText(""); setWork([]); setErr("");
    setOld(null); setChatsOpen(false);
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
    catch (e) { setChatsErr(`That chat didn't open - ${errText(e)}. Click it again.`); }
  };
  const pickAi = async (pick) => {
    const p = (state?.providers || []).find((x) => x.pick === pick);
    try { const { data } = await api.post("/api/concierge/ai", { pick, model: null }); setState((s) => ({ ...s, pick: data.pick, provider: p?.label || data.pick, model: data.model || p?.model || "" })); }
    catch (e) { setErr(errText(e)); }
    setAiEl(null);
  };
  const toggleSpeak = () => { const v = !speakOnState; setSpeak(v); try { localStorage.setItem("taskuary_speak", v ? "1" : "0"); } catch { /* private mode */ } if (!v) window.speechSynthesis?.cancel(); };
  // a card's link to its message: it opens on the stage, over the chat, right here - the rail reads the
  // hash and pins it (FeedView.openHash); its close comes back to the conversation
  const timeline = (mid) => { openAppLink(`msg=${mid}`); };
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
  const walkSection = (level) => {
    const seen = new Set();
    const first = sectionNext(pile?.items, level, seen);
    if (!first) return;
    seen.add(first.key);
    sectionRef.current = { level, seen };
    // the assistant SAYS what is in the section, then walks it - the whole list once, before the first item (the owner, 2026-09-30)
    const rows = (bandsOf(pileRows(pile)).find((b) => b.level === level)?.items || []).filter((i) => !i.settling);
    const said = rows.slice(0, 8).map((i) => `${i.who ? i.who + " - " : ""}${i.title}`).join("; ") + (rows.length > 8 ? `; and ${rows.length - 8} more` : "");
    if (rows.length) setMsgs((m) => [...m, { id: `s${Date.now()}`, role: "receipt", text: `${levelLabel(level)}: ${rows.length} to go through. ${said}. Starting with the first.` }]);
    pull(first.key, null);
  };
  // A SIDEBAR BUTTON POSTS ITS BROWSE CARD into the conversation - no AI, no tab: the newest one is the live one, and an
  // earlier one folds to its line, so only one detail is ever mounted (the canvas redesign, 2026-09-29)
  const browse = (area, state = {}) => {
    navHow.current = "push";
    setRailOpen(false); if (old) setOld(null); setStageMode("chat"); setExpanded(false);
    const id = `b${Date.now()}`;
    // THE SAME AREA MOVES ITS CARD: a link or a button for the area already open re-places that card, never posts a second
    // one - a second unmounted the first mid-dialog (a #playbook link opening New playbook), and old links posted two
    setMsgs((m) => {
      const live = [...m].reverse().find((x) => x.role === "browse" || (x.card && !x.card.background_event));
      if (live?.role === "browse" && live.area === area) return m.map((x) => (x.id === live.id ? { ...x, state, down: false } : x));
      return [...m, { id, role: "browse", area, state }];
    });
    putOnTable(null, "view");                          // its top in view, held there while it loads
  };
  // A TASK OPENED BY NAME - a link, a notification, the Board, a card's "Open TQ-0005" - is shown the same way the walk
  // shows one: its task view, as the newest line (the canvas redesign: the Tasks tab is gone)
  // A ROW, A TASK OR AN FYI PUTS THE BROWSE CARD DOWN AT THE CLICK, as one sidebar area replaces another (the owner, 2026-10-01:
  // "if i click on settings while hub is open it closes hub right away ... same should happen if you hit show task after
  // connection tab open"): the open view folds to its line now, and the "…" waits under it while the item loads
  // ...but a New card left behind is no record of anything - nothing was made - so it goes, the way its Cancel takes it: folded,
  // it stood in the chat as a bare "New" (the walk click-through, 2026-10-17)
  const browseDown = () => { openCardRef.current = null; setMsgs((m) => m.filter((x) => !(x.role === "browse" && x.area === "new"))
    .map((x) => (x.role === "browse" && !x.down ? { ...x, down: true } : x))); };
  // ...and it goes the rail's own road (2026-10-19 UI walk): a task opened by name was put down as a bare "task:N" card the server
  // never heard of, so the rail marked nothing, Next served it again and a reload put back the walk's last item. The server answers
  // `task:N` for any task (funnel.item_for_key), through the task's own row when the rail has one. Only a busy walk, which refuses
  // a pull, still lands the bare card - opening must never do nothing.
  const openTaskCard = (req) => {
    setExpanded(false); setFoldedKey(null);
    if (!(busy || resetting || handoff || turnFlight.current)) {
      openExtra.current = req.start || req.act ? { tid: req.tid, autostart: req.start || null, act: req.act || null } : null;
      pull(`task:${req.tid}`); return;
    }
    setRailOpen(false); if (old) setOld(null); setStageMode("chat"); browseDown();
    const ref = `TQ-${String(req.tid).padStart(4, "0")}`;
    // the task from the Board is what is on the table now: the rail kept marking the item before it "on the table"
    const card = { kind: "task", key: `task:${req.tid}`, tid: req.tid, title: ref, ref, autostart: req.start || null, act: req.act || null };
    setMsgs((m) => [...m, { id: `t${Date.now()}`, role: "assistant", text: "", card }]);
    putOnTable(card, "card");
  };
  browseRef.current = browse; openTaskRef.current = openTaskCard; browseDownRef.current = browseDown;
  // a pull lands through surface() -> landed() -> putOnTable; one refused as busy lands nothing, so nothing waits for it
  const pull = (key, asUser) => {
    navHow.current = "push";
    setRailOpen(false); if (old) setOld(null); setStageMode("chat"); browseDown(); surface(key, asUser || null);
  };

  // What the Chat/Task toggle MEANS on the pipe rail: chat pulls the row into the conversation,
  // task opens it on the stage the way a feed row does. Only a row with a message behind it can be
  // opened - a meeting, a wrapup or an agent has no message, so those still answer in the chat,
  // and pull() switches the stage there so the answer is not written somewhere invisible.
  const pullOrOpen = (key, asUser, openByMid, openByItem) => {
    browseDown();
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

  // THE DAY'S OPENER, one drawing: the empty chat's welcome, and the "Today" card the chat records when the owner sits down
  // (welcome.arrive) - that card drew a row list of its own, which was not the opener (the owner, 2026-10-08)
  const welcome = (m = null) => firstRun ? (
    // FIRST RUN (the owner, 2026-10-14: "first time you login the setup ... on the assistant canvas"): three questions in place of
    // the day, until the walk starts. The popup checklist is gone; this is the one road.
    <div className="tq-msg tq-welcome-msg"><div className="avatar"><AssistantMark /></div>
    <div className="tq-welcome"><FirstRun onChanged={() => loadPile(true)} onWalk={() => { setFirstRun(false); start(null); }}
      onFinish={() => { setFirstRun(false); loadPile(true); }} /></div></div>
  ) : (
    <div className="tq-msg tq-welcome-msg"><div className="avatar"><AssistantMark /></div>
    <div className="tq-welcome">
      {/* TASKUARY SPEAKING, the way every line of the chat is: the mark is the speaker's avatar in
          the left column, never inline with the greeting (the owner, 2026-09-23: "it should be the
          person talking"), and the whole day fits one screen without scrolling */}
      <div className="tq-welcome-head"><b>{greeting()}</b>
        <span>{fmtDate(new Date(), "en-US", { weekday: "short", day: "numeric", month: "short" })} · {fmtTime(new Date(), "en-US", { hour: "numeric", minute: "2-digit" })}</span></div>
      {/* no card.away line here: SinceBlock below already says what came in, and the two counts read as a contradiction (U6) */}
      {/* the start of the walk: the day's meetings, then who wants what - the best of the Morning
          digest, on the screen the day opens on (2026-09-23) */}
      <DayHold loading={pileLoading || mailReading}>
      <DayOpener groups={items.length ? summarize(railPile ? pileRows(railPile) : items).groups : []} onSection={walkSection}
        loading={mailReading} top={<SinceBlock onOpen={(k) => pull(k, null)} onReading={setMailReading} />} />
      {pileLoading ? <span data-tq-pile-loading="">Loading...</span>
        : !items.length && <span>Nothing is waiting on you - ask me anything, or set something up.</span>}
      {/* greyed with no reason read as broken: say why, and where the rows are */}
      {!!items.length && !canAdvance && !busy && !starting && <span className="tq-welcome-why">
        Nothing to walk through right now - what's left is with an agent or put away for later. Click a row on the left to open it.</span>}
      </DayHold>
      <div className="tq-modes">
        <button type="button" className="tq-chip primary" disabled={walkOff || walkQueued || (!pileLoading && !canAdvance)}
          // ...kept on the press itself while loading: the day fills in above this row as it lands and moves it, and a click
          // whose release lands after the move never reaches the button
          onPointerDown={pileLoading ? () => setWalkQueued(true) : undefined}
          onClick={() => (pileLoading ? setWalkQueued(true) : start(null))}
          title="Everything waiting, most important first - mail, reports, agents, meetings">{starting || walkQueued ? "Getting your first one..." : "Walk me through my tasks"}</button>
        {/* NO "Set up Taskuary" HERE: setup is the Setup button on the top bar, never a choice in the chat (the owner, 2026-10-19) */}
        {/* RUN, not set up: setting things up is the top bar's Setup; this door goes where the reports and workflows ARE
            (the owner, 2026-10-08: "it should be run report/workflow which will take you to reports/workflows") */}
        <button type="button" className="tq-chip" disabled={resetting} onClick={() => onNavigate?.("Reports")}
          title="Your reports and workflows - run one now, or see what each found">Run a report or workflow</button>
        {/* the same walk, on your phone - offered only for a chat that is already connected and
            names an Assistant chat, because this talks to the assistant, it does not set one up */}
        {(state?.doorways || []).map((d) => (
          <button key={d.channel} type="button" className="tq-chip tq-chip-chat" disabled={busy || resetting || !canAdvance}
            onClick={() => handOver(d)} title={`I say hello in ${d.name} and take you through the same items there; this tab locks until you press ${btn("walk_here")}`}>
            <ChannelIcon channel={d.channel} sx={{ fontSize: 14 }} />
            Walk me through them in {d.label}
          </button>
        ))}
      </div>
    </div></div>
  );
  // SETUP REOPENS THE SETUP, on the canvas (the owner, 2026-10-15: "restart the initial walk through from the button on top - not the
  // pop up one"): every question open, the day back on Back to my day
  // ...but the browser demo has no setup to run - it cannot connect an inbox - so its door is the install note (setup() above), never
  // a setup that waits on "Getting set up…" for good (the browser CI, 2026-10-15)
  setupRef.current = () => (DEMO ? setup() : setFirstRun(true));
  // A REMINDER'S RECEIPT, from the walk's picker or the task view's: where it went - one line, and no Take it back (the owner, 2026-10-19:
  // "no take it back button. hate that"): a day picked wrong is picked again with Remind me
  const remindReceipt = (out, tid, ref) => {
    setMsgs((m) => [...m, { id: `r${Date.now()}`, role: "receipt", tid, ref,
      // ...in the server's own words when it recorded the line (server.remind_task), so its read finds the same turn and draws it once
      text: out?.receipt || (out?.remindAt ? `Away until ${out.when} - it is under ${place("later").name}, and back in front of you that morning.${out.warn ? ` ${out.warn}` : ""}` : "It is back on your rail now.") }]);
  };
  // ...the Advisor's own move (a task to fix what failed, a proposal) pressed from a phone's row as from this one: the phone's strip had
  // none, so a move the row lacks drew no line and no button there (the matrix's phone pass, 2026-10-20)
  const actions = { done, sent, start, handOff, welcome, openTask: onOpenTask, timeline, navigate: onNavigate, items: pileRows(pile), pressAdvice,
    reminded: (out, c) => remindReceipt(out, c?.tid, c?.ref),
    next: () => runChip({ verb: "next" }), advance: (pile, settled) => advance(pile, settled), reload: () => loadPile(true), changed: onChanged,
    goReports: () => onNavigate?.("Reports"),
    // an earlier line back on the table - or the folded item itself, which only unfolds: it never left the table
    // ...and a page opened over it is put away with the fold: the item under it was folded by the page, not by its X
    reopen: (key, onTable) => { if (onTable) { setFoldedKey(null); browseDown(); putOnTable(null, "view"); } else pull(key); },
    browseState: (id, state) => { navHow.current = "push"; holdBottom.current = true; setMsgs((m) => m.map((x) => (x.id === id ? { ...x, state } : x))); },
    browse: (area, state) => browse(area, state),
    browseClose: (id) => setMsgs((m) => m.filter((x) => x.id !== id)),    // the New card, closed: its line goes
    openCard,
    walk: walkTo, walkSaved, walkRestart, chip: runChip, busy: busy || resetting || !!handoff,
    handedTo: handoff ? ((state?.doorways || []).find((d) => d.channel === handoff.channel)?.label || handoff.channel) : "",
    confirm: confirmProposal, cancel: cancelProposal, propose: proposeDirect, preview: previewProposal,
    surface: (key, note) => {
      if (note) setMsgs((m) => [...m, { id: `r${Date.now()}`, role: "receipt", text: note }]);
      deferInChat(() => key ? surfaceRef.current?.(key) : loadPileRef.current?.(), 900);
    } };
  const shown = old ? old.messages : msgs;
  const lastBriefId = [...shown].reverse().find((m) => m.card?.kind === "brief")?.id;
  // the live browse card: the newest one, unless the walk has put an item on the table since
  const browsing = useMemo(() => {
    for (let i = shown.length - 1; i >= 0; i -= 1) {
      if (shown[i].role === "browse") return shown[i].down ? null : shown[i].id;
      if (shown[i].card && !shown[i].card.background_event) return null;
    }
    return null;
  }, [shown]);
  // THE TABLE, ONE RECORD (tableState.js): folded by its X or under a page opened over it, the item keeps its key - and the Advisor
  // keeps quiet, its button never acting on what nobody can see. The strip speaks only for the item on the table, at rest.
  const table = tableOf({ current, cardKey, foldedKey, browsing, setup: setupOn.current });
  // ...and what the rail's tag and the box say of it: a page over it is not it in view (tableWords)
  const tableSays = tableWords(table, currentItem?.ref || (/^task:(\d+)$/.test(table.key || "") ? `TQ-${table.key.slice(5).padStart(4, "0")}` : ""));
  // THE ASSISTANT'S LIGHT OUTRANKS THE ADVISOR'S while its item is on the table: the owner asked for that act in words, and the Advisor's line
  // over it would name another button (assistantLight.js); it goes out at the next press or when the table moves on
  const litTable = { key: table.key, tid: currentItem?.tid ?? Number(/^task:(\d+)$/.exec(table.key || "")?.[1] || 0) };
  const litNow = litPick(lit, litTable);
  useEffect(() => { setLit((l) => litAfter(l, litTable)); }, [litTable.key, litTable.tid, lit]);   // eslint-disable-line react-hooks/exhaustive-deps
  const shownAdvice = table.speaks && !litNow ? adviceShown(advice, { key: table.key, lane: currentItem?.lane }, busy) : null;
  shownRef.current = shownAdvice?.verb ? { key: shownAdvice.for || shownAdvice.key || table.key, verb: shownAdvice.verb, revision: shownAdvice.revision } : null;
  // ...an answer that landed wins: the strip asking for an AI over a line the Advisor did give hid the line and left its button dark
  const noAi = table.speaks && !busy && !shownAdvice && !litNow && (caps.ai === false || (advice?.none === "no_ai" && advice.for === table.key));
  // ...and every other reason there is no line, said (words.json advice_none) - an agent at work included, whose line is hidden
  const noneSaid = !table.speaks || busy || shownAdvice || noAi || litNow ? null
    : advice?.none && advice.for === table.key ? advice : currentItem?.lane === "working" ? { none: "working", for: table.key } : null;
  // ON A PHONE THE LINE RIDES WITH ITS ROW: the row is drawn at the task view's foot there (CanvasItem), and the line pinned over the
  // composer stood a screen away from the button it lit (2026-10-19) - the view draws both, and the dock none
  const hostedRow = useHosted();
  // NEVER LEFT HANGING (the owner, 2026-10-08: "assistant is leaving user hanging. We need Next button on bottom at least and say hit
  // next to continue"): a Next the server refused because the list moved under it said so in red and left nothing to press - every
  // card above folded, so no card had a row to register. With nothing on the table and the walk able to go on (or a press just
  // refused), the row's floor is Next.
  // ...and only when the ROW IS EMPTY without it: a task card on the table already registers its own Next and verbs, and the floor's
  // "Press Next below" over them read as a bug (README capture, 2026-10-08). What the owner can press is the test, not which card is up
  const rowVerbs = useRowVerbs();
  // setup's lit move on the row - About your work's Next (`about:next`) included: it was never lit, as its id is not `setup:` (2026-10-19)
  const setupLit = !firstRun ? null : (() => { const v = rowVerbs.list.find((x) => /^(setup|about):/.test(String(x.id)) && x.tone === "p" && !x.disabled); return v ? { id: v.id } : null; })();
  const rowEmpty = !rowVerbs.list.some((v) => !String(v.id).startsWith("floor:"));
  // ...and not under a page the owner opened on the canvas (Reports, Connections): they are working there, and the line read
  // as part of that page (the owner's workflow screenshot, 2026-10-15)
  // ...and under a proposal waiting on its Confirm: the item it came from folded away with its row, and the walk must still go on
  // past it (the walk's INLINE, 2026-10-17: the only way on was the card's own buttons in the chat)
  const asked = shown[interactiveCardIndex(shown)]?.proposal, proposing = !!asked && asked.version != null && (asked.status || "proposed") === "proposed";
  const hanging = !!state && !old && !walk && !browsing && shown.length > 0 && !busy && !starting && rowEmpty && (canAdvance || !!err || proposing);
  useVerbs("floor", [{ id: "floor:next", group: "next", label: btn("next"), tone: "p", title: btnHint("next"),
    run: () => { setErr(""); surface(null, null); } }], hanging);
  const navOn = shown.find((x) => x.id === browsing)?.area || "";
  // WHAT THE PAGE ASKS THE CANVAS TO OPEN (TaskHubPage canvasReq): once each, and only once the chat has loaded - the
  // first load replaces the conversation, and a card posted before it would be wiped
  const doneReq = useRef(0);
  useEffect(() => {
    if (!request?.n || request.n === doneReq.current || !state) return;
    doneReq.current = request.n;
    // ...`at` numbers the ask, so a view already open on the page opens the card a second link names (ConnectorsView, SettingsView)
    if (request.kind === "browse") browseRef.current?.(request.area, { ...(request.state || {}), at: request.n });
    // ...a reload of the address the canvas wrote itself (#task=N, recordPlace) names the task the server already has on the table:
    // opening it again was a pull - a write, and the walk's place taken again (PW-118, 0.3.9.9 CI)
    else if (request.kind === "task" && request.fromUrl && !request.start && !request.act
      && Number(state.current?.tid ?? /^task:(\d+)$/.exec(state.current?.key || "")?.[1] ?? 0) === Number(request.tid)) navHow.current = "replace";
    else if (request.kind === "task") openTaskRef.current?.(request);
    else if (request.kind === "new") browseRef.current?.("new", {});     // #new-task: the New card in the conversation
    // Back to the address with no place: the walk's own table, the page over it put down (appLinks.onPlace)
    else if (request.kind === "home") { setRailOpen(false); setFoldedKey(null); browseDownRef.current?.(); putOnTable(null, "view"); }
    if (request.fromUrl) navHow.current = "replace";
  }, [request, state]);   // eslint-disable-line react-hooks/exhaustive-deps
  // A COLD LINK TO A TASK (#task=N in a new tab) draws that task first: the conversation came back with the walk's last item on
  // the table, which drew whole - its view and every read behind it - for the 0.6-1 s the link's own pull took, then gave way.
  // The page stays on its loading spinner until the pull has answered (or failed); what it then draws is what it drew before.
  // Before paint (layout effect), so the frame that lands the pull is the first one drawn; every render, as the pull may end in any
  // state (busy, the messages, an error).
  const [linkHold, setLinkHold] = useState(() => (request?.kind === "task" && request.fromUrl ? request.n : 0));
  useLayoutEffect(() => { if (linkHold && (doneReq.current === linkHold || request?.n !== linkHold) && !turnFlight.current) setLinkHold(0); });
  const holding = !!linkHold && !err && !firstRun;
  // THE ADDRESS SAYS WHERE THE OWNER IS (the 2026-10-19 UI walk, G2): the page open on the canvas, else the task on the table, else
  // nothing - a reload lands on the server's own table. Never while a turn is landing (the table is about to move) or a link is still
  // on its way (the address is the link's), nor over setup or an old conversation, which are not places
  const liveBrowse = shown.find((x) => x.id === browsing) || null;
  const placeHash = liveBrowse ? hashFor(liveBrowse.area, liveBrowse.state) : litTable.tid ? `#task=${litTable.tid}` : "";
  // ...and not in the commit that serves one: its page is drawn on the next, and this one still showed the table - written then, the
  // address became the table's before the link's own hashchange was heard, and the link opened the task instead (found by PLACE)
  const reqSeen = useRef(0);
  useEffect(() => {
    if (request?.n && request.n !== reqSeen.current) { if (request.n === doneReq.current) reqSeen.current = request.n; return; }
    if (!active || !state || old || firstRun || busy) return;
    recordPlace(placeHash, navHow.current); navHow.current = "replace";
  }, [placeHash, active, state, old, firstRun, busy, request]);   // eslint-disable-line react-hooks/exhaustive-deps
  const railPile = useMemo(() => ((leavingTid || continuingTid) && pile?.items
    ? { ...pile, items: asPressed(pile.items, { leaving: leavingTid, continuing: continuingTid }) } : pile),
    [pile, leavingTid, continuingTid]);
  useEffect(() => {                                   // the close has landed: the server's pile no longer has it
    if (leavingTid && pile?.items && !pile.items.some((i) => i.tid === leavingTid)) setLeavingTid(null);
  }, [pile, leavingTid]);
  useEffect(() => {                                   // ...and the continue has: the server's pile has it working (or not at all)
    const row = continuingTid && pile?.items ? pile.items.find((i) => i.tid === continuingTid) : undefined;
    if (continuingTid && pile?.items && (!row || attentionBand(row) === 5)) setContinuingTid(null);
  }, [pile, continuingTid]);
  // ...and never for long on the page's word alone: a session that ended at once is the server's to say
  useEffect(() => {
    if (!continuingTid) return undefined;
    const t = setTimeout(() => setContinuingTid((x) => (x === continuingTid ? null : x)), 20000);
    return () => clearTimeout(t);
  }, [continuingTid]);
  // ...and the Assistant's lit button with its line, for the phone's row at the view's foot (CanvasItem)
  const canvasState = useMemo(() => ({ height: CANVAS_ITEM_HEIGHT, expanded, folded: foldedKey, browsing, phone, lit: litNow,
    toggle: () => setExpanded((x) => !x), fold: (key) => { setExpanded(false); setFoldedKey(key); },
    // the task leaves the table the moment it is put down, the "…" under its title line while the server closes it
    putDown: (key, tid = null) => { setExpanded(false); setFoldedKey(key); setNextComing(true); setLeavingTid(tid); },
    pickUp: (key, why) => { setFoldedKey((k) => (k === key ? null : k)); setNextComing(false); setLeavingTid(null); if (why) setErr(why); } }),
    [bodyH, expanded, foldedKey, browsing, phone, litNow?.verb, litNow?.line]);   // eslint-disable-line react-hooks/exhaustive-deps
  const handedTo = handoff ? (state?.doorways || []).find((d) => d.channel === handoff.channel) : null;
  const lastCardIdx = useMemo(() => interactiveCardIndex(shown), [shown]);
  const lastSaidIdx = useMemo(() => lastActIndex(shown), [shown]);
  // a reloaded answer is text only: the item still on the table lends it its verbs, so Next is never gone
  // ONE ROW OF WORDS (the owner, 2026-10-05: "why is there buttons both places?"): a task on the table is drawn as its task view,
  // and that view registers its words in the row under the chat (layout B). A bare line under it then borrowed the same item's
  // chips as recorded when it was surfaced - a second row, and a stale one: a note saying the draft was removed and the task
  // closed still offered Close out and Redraft it. While the bar holds the item, a line borrows nothing.
  const barHolds = useMemo(() => {
    const c = shown[lastCardIdx]?.card;
    return !old && !!c && showsTask(c, cardFor(c)) && !foldsAs(canvasState?.folded, c.key) && !canvasState?.browsing;
  }, [shown, lastCardIdx, old, canvasState]);
  const tableChips = useMemo(() => {
    const c = shown[lastCardIdx]?.card;
    return c && current && (c.key === current || (c.aliases || []).includes(current)) ? chipsOf(shown[lastCardIdx]) : [];
  }, [shown, lastCardIdx, current]);

  const chat = (
    <div className={shownAdvice ? "tq-asst-col advising" : "tq-asst-col"} style={{ position: "relative", flex: 1, minHeight: 0 }}>
      <div className="tq-chat-head">
        {/* no mark here: the top bar already carries the logo (the owner, 2026-10-06: "don't need it on top of the assistant") */}
        <div className="who" style={{ minWidth: 0 }}><b>Taskuary</b>{old && <span>An earlier chat · {fmtDateTime(old.at)}</span>}</div>
        <div className="grow" />
        <Tooltip title="Your work"><IconButton size="small" onClick={() => setRailOpen(true)} sx={{ display: { xs: "inline-flex", md: "none" } }}><ViewSidebarIcon sx={{ fontSize: 18, color: DIM }} /></IconButton></Tooltip>
        <Tooltip title={speakOnState ? "Reading replies aloud — click to stop" : "Read replies aloud"}><IconButton size="small" className="tq-phone-hide" onClick={toggleSpeak}>{speakOnState ? <VolumeUpIcon sx={{ fontSize: 18, color: "#526b53" }} /> : <VolumeOffIcon sx={{ fontSize: 18, color: DIM }} />}</IconButton></Tooltip>
        {/* no AI to name before the first run picked one - it named a CLI and a profile over the question asking which (2026-10-15) */}
        {!firstRun && <Tooltip title={state?.scripted ? "Scripted demo - no AI is running" : "Which AI speaks here"}><IconButton size="small" className="tq-phone-hide" onClick={(e) => setAiEl(e.currentTarget)}><TuneIcon sx={{ fontSize: 18, color: DIM }} /></IconButton></Tooltip>}
        <Tooltip title="Past chats"><IconButton size="small" onClick={openChats}><HistoryIcon sx={{ fontSize: 18, color: DIM }} /></IconButton></Tooltip>
        <Tooltip title="New chat — archives this one"><IconButton size="small" onClick={newChat} disabled={busy || resetting}><EditNoteIcon sx={{ fontSize: 19, color: DIM }} /></IconButton></Tooltip>
      </div>
      {remindOn && <RemindPicker task={remindOn.task} path={remindOn.path} anchor={remindOn.anchor || document.body} live={remindOn.live} onClose={() => setRemindOn(null)}
        onDone={(out) => { remindReceipt(out, remindOn.path ? null : remindOn.task.TaskId, remindOn.ref); if (out?.remindAt) advance(); }} />}
      <Popover open={!!aiEl} anchorEl={aiEl} onClose={() => setAiEl(null)} anchorOrigin={{ vertical: "bottom", horizontal: "right" }} transformOrigin={{ vertical: "top", horizontal: "right" }}
        slotProps={{ paper: { sx: { p: 1.5, width: 320 } } }}>
        <Typography sx={{ fontSize: 12, fontWeight: 600, color: INK, mb: 0.5 }}>{state?.scripted ? "Scripted demo assistant" : "Which AI speaks here"}</Typography>
        <Typography variant="caption" sx={{ color: DIM, display: "block", mb: 1, lineHeight: 1.45 }}>{state?.scripted
          ? "Every thread, post, and reply here is invented and runs locally in this page. No AI, agent, mailbox, or outside system is connected."
          : aiSays(state?.providers)}</Typography>
        <Select size="small" fullWidth value={state?.pick || ""} displayEmpty disabled={!!state?.scripted} onChange={(e) => pickAi(e.target.value)} sx={{ fontSize: 12 }}>
          {!state?.providers?.length && <MenuItem value="">No AI connected</MenuItem>}
          {(state?.providers || []).map((p) => <MenuItem key={p.pick} value={p.pick} sx={{ fontSize: 12 }}>{p.label}{p.type === "demo" ? " · demo" : p.type === "cli" ? " · can look things up and act" : " · fast, talks only"}</MenuItem>)}
        </Select>
        {!state?.scripted && <button type="button" className="tq-linkish" style={{ marginTop: 8, fontSize: 12 }}
          onClick={() => { setAiEl(null); openAppLink(state?.providers?.length ? AI_DEFAULTS : place("ai").href); }}>
          {state?.providers?.length ? `Choose which AI does what - ${place("ai_defaults").name}` : "Connect an AI"}</button>}
      </Popover>
      {old && <div className="tq-old-banner"><span>You are reading an earlier chat.</span><button type="button" className="tq-chip" onClick={() => setOld(null)}>Back to today</button></div>}
      {chatsOpen && (
        <div className="tq-chats">
          <div className="tq-chats-head">Chats<span style={{ flex: 1 }} /><IconButton aria-label="Close past chats" size="small" onClick={() => setChatsOpen(false)}><CloseIcon sx={{ fontSize: 16 }} /></IconButton></div>
          <div className="tq-chats-list">
            {current && <AdvisorNotes keyOnTable={current} />}
            {chatsLoading && <Typography sx={{ color: FAINT, fontSize: 12, p: 1.5 }}>Loading past chats…</Typography>}
            {chatsErr && <Typography role="alert" sx={{ color: "#7a2f3c", fontSize: 12, p: 1.5 }}>{chatsErr}{" "}
              <button type="button" className="tq-chip" onClick={openChats}>{btn("try_again")}</button></Typography>}
            {!chatsLoading && !chatsErr && !chats.length && <Typography sx={{ color: FAINT, fontSize: 12, p: 1.5 }}>No earlier chats yet.</Typography>}
            {chats.map((c) => (
              <div key={c.taskId} className="c" onClick={() => openOld(c)} title={c.started ? `started ${c.started.slice(0, 16)}` : ""}>
                {c.open ? <i /> : <span style={{ width: 7 }} />}<b>{c.title}</b>
                {/* what the walk actually got through, so one transcript can be told from another */}
                <span>{[c.mail ? `${c.mail} mail` : "", c.seen ? `${c.seen} looked at` : "", c.minutes ? `${c.minutes} min` : "", age(c.at)].filter(Boolean).join(" · ")}</span>
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
              <span>{walk.title}. Nothing changes until you say so; its browser opens beside this conversation.</span></div>
            <button type="button" className="tq-chip" onClick={leaveWalk}>Leave the walk</button>
          </div>
          <div className="tq-walk"><GeneralWorkspace task={walk.task} compact /></div>
        </>
      )}
      {!walk && (
      <div className={`tq-chat-body${expanded ? " expanded" : ""}`} ref={bodyRef}>
        <div className={`tq-chat-inner${expanded ? " expanded" : ""}`}>
          {/* ...the spinner holds while a cold link's task is on its way (linkHold) */}
          {(!state || holding) && !err && <Box sx={{ display: "grid", placeItems: "center", py: 6 }}><CircularProgress size={22} /></Box>}
          {!holding && <>
          {/* SETUP MODE IS ITS OWN SCREEN (the owner, 2026-10-15: "it should be a distinct setup mode vs regular operations mode"):
              setup alone on the canvas, never under the day's conversation */}
          {/* ...but a place picked from the sidebar during setup opens: it lit up and nothing opened, and nothing said why (re-audit,
              2026-10-18). The place shows alone, with the way back to setup over it */}
          {firstRun && browsing ? <>
            <div className="tq-next" role="status" data-tq-setup-back=""><div className="tq-next-txt">Setup is waiting where you left it.</div>
              <button type="button" className="tq-chip" onClick={browseDown}>{`Back to ${place("setup").name}`}</button></div>
            {shown.filter((m) => m.id === browsing).map((m) => <Line key={m.id} m={m} live last tableChips={[]} barHolds={false}
                                     actions={actions} fresh={null} canvas={canvasState} />)}
          </> : firstRun ? state && welcome() : state && !shown.length && !busy && welcome()}
          {!firstRun && shown.map((m, i) => <Line key={m.id} m={m} lastBrief={m.id === lastBriefId} live={!old && i === lastCardIdx} last={!old && i === lastSaidIdx} tableChips={tableChips} barHolds={barHolds}
                                     actions={actions} fresh={currentItem} canvas={old ? null : canvasState} />)}
          {/* CONTINUE, IN LINE (the owner, 2026-09-30): a card under the item, like New - the mic and pictures in it */}
          {!old && continueOn && (
            <div className="tq-browse-line" ref={(el) => { if (el && !el.dataset.seen) { el.dataset.seen = "1"; el.scrollIntoView({ block: "nearest", behavior: "smooth" }); } }}>
              <ContinueBox inline task={continueOn.task} taskRef={continueOn.ref} onClose={() => setContinueOn(null)}
                onPress={() => setContinuingTid(continueOn.task.TaskId)} onFail={() => setContinuingTid(null)}
                onDone={() => {
                  // NO RECEIPT: the session on the table shows it working - "Continuing with your note..." under it was clutter
                  // (the owner, 2026-10-13). ...and the table STAYS on it: you continued it to watch it work, not to be walked past it (the owner,
                  // 2026-09-30: "the session started but then closed and moved on without hitting next"); the view shows the
                  // session when it opens (TaskPage hears task-changed)
                }} />
            </div>
          )}
          {!old && noteOn && (
            <div className="tq-browse-line" ref={(el) => { if (el && !el.dataset.seen) { el.dataset.seen = "1"; el.scrollIntoView({ block: "nearest", behavior: "smooth" }); } }}>
              <CloseNote inline taskRef={noteOn.ref} initial={noteOn.note} onClose={() => setNoteOn(null)}
                onSubmit={async (note) => {
                  // put down at the press with the task it closes; a close that fails brings the card back with its words
                  const on = noteOn;
                  setNoteOn(null);
                  try { await on.close(note); } catch (e) { setNoteOn({ ...on, note }); throw e; }
                  setMsgs((m) => [...m, { id: `r${Date.now()}`, role: "receipt", tid: on.task.TaskId, ref: on.ref, text: `Closed with your note: ${note}` }]);
                }} />
            </div>
          )}
          {/* the slot the task view draws Configure the next run into (TaskPage, createPortal) */}
          {!old && <div className="tq-browse-line" data-tq-run-slot="" style={{ display: "contents" }} />}
          {(busy || phoneBusy || nextComing) && (
            <div className="tq-msg"><div className="avatar"><AssistantMark /></div>
              <div className="body"><span className="tq-typing"><i /><i /><i /></span>
                {/* ...and how long it has been at it, where the dots alone were silent: its own clock, so the chat does not redraw each second */}
                {busy && answering.current && !DEMO && <WorkingFor />}
                {/* an answer that hangs had no way out: New chat is refused while one is being written (dock/new 409) */}
                {busy && answering.current && !DEMO && (
                  <button type="button" className="tq-chip" style={{ marginLeft: 8 }} title="Stops the answer being written and gives you the chat back."
                    onClick={() => { api.post("/api/concierge/stop").catch(() => {}); stopRef.current?.abort(); }}>Stop</button>
                )}
                {!!work.length && <div className="tq-work">{work.map((w, i) => <div key={i}>{w}</div>)}</div>}
              </div>
            </div>
          )}
          {err && <Typography component="div" sx={{ color: "#7a2f3c", fontSize: 12, mb: 1 }}>{err}<ReportLink text={err} /></Typography>}
          {/* the floor's Next is the filled button under the chat - no line telling the owner to press it (the owner, 2026-10-15: "Don't be
              dumb like saying click next to move on if it's obvious") */}
          </>}
        </div>
      </div>
      )}
      {/* NO "Continue previous work" bar either: a second label along the bottom, for work the rail already
          lists (the owner, 2026-09-23: "still see bottom label"). */}
      {/* NO BOTTOM STRIP. The pinned reminder line restated what the rail and the card already show (the owner,
          2026-09-23: "remove the label that is constantly reminding you of tasks ... it's now in the
          screen"). A new message on the card you are reading refreshes that card; its draft says it is stale. */}
      {/* the walk is on the phone: this tab does not get to answer the same item (the owner, 2026-09-07:
          "make the desktop unavailable if sent to whatsapp otherwise it's confusing") */}
      {!old && handoff && (
        <div className="tq-handed" role="status">
          <ChannelIcon channel={handoff.channel} sx={{ fontSize: 17 }} />
          <div className="txt"><b>The walk is in {handedTo?.label || handoff.channel}</b>
            <span>Answer me there and I keep going. This chat waits so the same thing is not answered twice.</span></div>
          <button type="button" className="tq-chip primary" disabled={busy} onClick={takeBack} title={btnHint("walk_here")}>{btn("walk_here")}</button>
        </div>
      )}
      {!old && !handoff && !walk && (
        <div className="tq-compose" {...pics.drop}>
          <RetryVerbs item={currentItem} failed={(pile?.items || []).filter((i) => i.lane === "unjudged").length}
            onSaid={(text, status) => setMsgs((m) => [...m, { id: `r${Date.now()}`, role: "receipt", status: status || "done", text }])}
            onDone={() => loadPile(true)} />
          {/* ONE PANEL, THREE LAYERS (the owner, 2026-10-13: "i thought there will be one border around all 3"): the Advisor's
              suggestion, the row whose filled button it picked, and the box - one border, the box its floor */}
          <div className="tq-dock">
          {firstRun ? <SetupLine /> : noAi ? (
            <div className="tq-next" role="status" data-tq-advice="no_ai">
              <div className="tq-next-txt">Connect an AI to get a suggestion on each item</div>
              {/* quiet: the row below keeps the one filled button */}
              <button type="button" className="tq-chip" onClick={() => openAppLink(place("ai").href)}>Connect an AI</button>
            </div>
          ) : <>
            {/* THE ADVICE IS ON ITS WAY: the row has nothing dark until it lands (rowOf), and a quiet line says so - no button.
                ONE STRIP, ONE HEIGHT from Thinking to its answer: it came and went under the row, which jumped (2026-10-19) */}
            {table.speaks && !holding && !hostedRow && <div className="tq-strip" data-tq-strip={busy ? "busy" : ""}>
            {/* THE ASSISTANT'S LIT BUTTON SAYS SO HERE, over the row it lit: the strip stood empty over a dark Mark done, and "Press Mark done"
                was only up in the chat (verify, 2026-10-19) - it goes out with the light */}
            {table.speaks && !!litNow && <div className="tq-next" role="status" data-tq-advice="lit"><div className="tq-next-txt">{litNow.line}</div></div>}
            {table.speaks && !litNow && !shownAdvice && !noneSaid && !changed && !busy && asking === onTable && currentItem?.lane !== "working" && (
              <div className="tq-next" role="status" data-tq-advice-thinking=""><div className="tq-next-txt">Thinking about this one…</div></div>)}
            {table.speaks && !litNow && changed && changed.for === onTable && <div className="tq-next" role="status" data-tq-advice-changed="">
              <div className="tq-next-txt">{changed.reading ? "This changed - reading it again…" : shownAdvice ? "This changed - here's the updated suggestion."
                : "This changed - nothing to suggest on it now."}</div></div>}
            <AdvisorNext advice={shownAdvice} onPropose={pressAdvice} />
            {!changed && !litNow && <AdviceNone advice={noneSaid} />}
            </div>}
          </>}
          {/* ...and during setup its line is the Advisor's (SetupLine): the move setup fills (FirstRun's tone) is the one lit - nothing
              was, so the line said "pick it" over a plain Back and a greyed Next (2026-10-19) */}
          <ActionRow advised={litNow || shownAdvice || noneSaid || setupLit} />
          {!firstRun && <ImageTray pics={pics} sx={{ width: "100%", mb: 0.75 }} />}
          <div className="tq-compose-box" style={firstRun ? { display: "none" } : undefined}>
            <AttachImage pics={pics} sx={{ color: DIM }} />
            <MicButton size={18} sx={{ width: 34, height: 34, p: 0, color: DIM }} onText={(t) => setText((v) => (v ? `${v} ${t}` : t))} />
            <Tooltip title="Send an emoji response">
              <IconButton size="small" aria-label="Choose an emoji response" disabled={busy || resetting}
                onClick={(e) => setEmojiEl(e.currentTarget)} sx={{ width: 34, height: 34, p: 0, color: DIM }}>
                <SentimentSatisfiedAltIcon sx={{ fontSize: 18 }} />
              </IconButton>
            </Tooltip>
            {/* a phone's composer is one line tall and the long hint wrapped under its own edge, cut
                mid-word ("name or a subject pulls it in" lost its tail, 2026-09-20): the short hint there */}
            <textarea ref={composeRef} rows={1} value={text} disabled={resetting}
              placeholder={phone ? tableSays.phone : tableSays.box}
              onChange={(e) => setText(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }} />
            <button type="button" className="tq-send" aria-label="Send" disabled={busy || resetting || pics.busy || !(text.trim() || pics.imgs.length)} onClick={() => send()}><SendIcon fontSize="small" /></button>
          </div>
          </div>
          <Popover open={!!emojiEl} anchorEl={emojiEl} onClose={() => setEmojiEl(null)}
            anchorOrigin={{ vertical: "top", horizontal: "left" }} transformOrigin={{ vertical: "bottom", horizontal: "left" }}
            slotProps={{ paper: { sx: { p: 1.1, borderRadius: 2.5 } } }}>
            <Typography sx={{ fontSize: 11.5, fontWeight: 600, color: INK, px: 0.4, pb: 0.75 }}>Send a quick response</Typography>
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
        Hovering a row opens it here; clicking pins it. You get the message that arrived, why Taskuary sorted it
        where it did, what the agent is doing about it, and the reply waiting to go — each on its own tab.
      </Typography>
    </Box>
  );

  return (
    <>
    {DEMO && <DemoJourney onChanged={() => { loadPile(true); onChanged?.(); }} />}
    <FeedView onOpenTask={onOpenTask} onChanged={onChanged} active={active} onGo={(tab, key) => browse(key)} navOn={navOn}
      onInventoryFilter={inventoryFilterChanged} unreadInventory={pile}
      top={({ openByMid, openByItem }) => <Pile pile={railPile} settingUp={firstRun ? setupTodo || "finish setting up" : ""}current={old || (leavingTid && currentItem?.tid === leavingTid) ? null : currentItem}
        error={pile ? "" : err} onRetry={() => { setErr(""); loadPile(true); }}
        onPull={(key, asUser) => { sectionRef.current = null; pullOrOpen(key, asUser, openByMid, openByItem); }}
        onSection={walkSection} onMoreFyi={moreFyi} tag={tableSays.tag} onCurrent={() => { setRailOpen(false); if (table.folded || table.place) { setFoldedKey(null); browseDown(); putOnTable(null, "view"); } }} />}
      stage={stageMode === "chat" ? chat : placeholder} rowMode={stageMode}
      onPull={(r, o) => pull(keyForRow(r), o?.quiet ? null : `Tell me about “${r.Subject || r.Title || "this"}”`)}
      railOnNarrow={railOpen} setupMode={firstRun} setupRail={firstRun ? <SetupSteps /> : null} />
    </>
  );
}
