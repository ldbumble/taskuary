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
import ChatBubbleOutlineIcon from "@mui/icons-material/ChatBubbleOutline";
import ViewSidebarIcon from "@mui/icons-material/ViewSidebar";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import api from "./api.js";
import { runOperation } from "./taskOps.js";
import { openReply } from "./replyDraft.js";
import { DEMO } from "./demoApi.js";
import { lazyView } from "./lazyView.jsx";
import { loadGeneral } from "./lazyGeneral.js";
// the static demo's guided journey: nothing outside the demo build ever draws it, so nothing there fetches it
const DemoJourney = DEMO ? lazyView(() => import("./DemoJourney.jsx")) : () => null;
import { advisedIn, aimed, onPressed, onPressing, press as pressRow, leaveRow, rowNow, rowTable, useHosted, useRowVerbs, useVerbs } from "./actionRow.js";
import { deskPress, notePress as notePressed } from "./pressLog.js";
import { forgetTasks, heldTask, heldTerm, notePile, pageRead, prefetchTask, watchReads } from "./taskDetail.js";
import { readLists } from "./connectorLists.js";
import { hint as btnHint, label as btn, liveVerb, verbOfRow } from "./buttons.js";
import { readTurn, toolTarget } from "./assistantStream.js";
import { pollWhileActive } from "./visible.js";
import { liveUp, onLive } from "./live.js";
import { adviceKeyFor, adviceShown, stripWord, taskNote } from "./advice.js";
import { Md, looksMd } from "./md.jsx";
import { ChannelIcon, MicButton, TaskuaryMark, fmtDateTime, fmtTime12 } from "./ui.jsx";
// TASKUARY'S MARK IN THE CHAT (the owner, 2026-09-28: "the taskuary logo is blue and very obvious ... you can change the
// taskuary logo ... at least how it shows in the assistant"): its six-point star drawn in Taskuary's sage, outlined like
// the avatars on its cards - the bright tile repeated on every line shouted over the card it introduced
// the speaker's mark is TASKUARY'S OWN LOGO, never a second drawing of it (the owner, 2026-10-06: "logo should match the
// taskuary one not a different one")
const AssistantMark = () => <TaskuaryMark size={24} />;
import { DIM, FAINT, INK, LEVEL_COLOR, LEVEL_TINT, PRIORITY_COLOR, ROLES } from "./theme.jsx";
import { railShort } from "./batchItems.js";
import ProposalCard from "./ProposalCard.jsx";
import { adviceRead, tableOf, tableWords } from "./tableState.js";
import { ReportLink } from "./BugReportDialog.jsx";
import { openBugReport, shownError } from "./bugReportOpen.js";
import { AgentSteps } from "./AgentStepRows.jsx";
import { RemindPicker } from "./RemindMe.jsx";
import { SlotPicker } from "./CalendarPick.jsx";
import { agentOpen } from "./taskFilter.js";
import ContinueBox from "./ContinueBox.jsx";
import { ASK_REPORT, AgentAsk } from "./RunForm.jsx";
import CloseNote from "./CloseNote.jsx";
import { AttachImage, ImageTray, usePromptImages } from "./promptImages.jsx";
import { afterCancel, afterConfirm, afterExecute, followUps, holdsProposal, markExecuted, proposalSay } from "./proposalCard.js";
import { LEVEL_META, LEVEL_ROLE, arrivals, isUrgent, arrivedAt, asPressed, putDownLanded, bandsOf, canAdvanceSelection, captureNextSelection, cardFor, currentItemFromPile, displayRevision, drawOrder, fillCaps, followsItem, foldsAs, hasNextSelection, inOrder, interactiveCardIndex, tableCardIndex, keysOf, lastActIndex, chipsOf, receiptChips, CAPPED, FLOOR, FOOT_PX, levelLabel, nextMarkerKey, trimCaps, ROW_PX, nextSelectionBody, nextSelectionScope, refreshCurrentPresentation, refreshPilePresentation, replaceSelectionToken, rowMeta, sameSelectionScope, selectionGuardDetail, settledHistory, withdrawSelection } from "./funnelPile.js";
import { FYI_PAGE, ageHover, awayFromClear, coveredByReload, fyiHasRoom, fyiTail, heldSince, latestLine, pileRows, sentChips } from "./funnelPile.js";
import { railStatus, rowWhy } from "./railStatus.js";
import { UndoLine } from "./Removed.jsx";
import { StatusLogo } from "./StatusMark.jsx";
import { isCoveragePending } from "./processingAll.js";
import { mergeDurableTurns, nextBadge, pickLine, placeLine, pressChip, pressLine, pressedNoteOf, pressedOf } from "./assistantTurns.js";
import { lightOf, litAfter, litOn, litPick, litPull } from "./assistantLight.js";
import DigestText from "./DigestText.jsx";
import { canGoBack, firstAppLink, onStep, openAppLink, recordPlace } from "./appLinks.js";
import { hashFor } from "./canvasLinks.js";
import { canSend, useCapabilities } from "./capabilities.js";
import { place } from "./words.js";
import ConnectAi, { CONNECT_AI, connectAi } from "./ConnectAi.jsx";
// FirstRun, the walk's workspace and the browse cards are drawn after the pile or a click, never on the first frame: out of the entry chunk
const FirstRun = lazyView(() => import("./FirstRun.jsx"));
import SetupSteps from "./SetupSteps.jsx";
import SetupLine from "./SetupLine.jsx";
import { BriefCard, CardNav, DashboardCard, DayOpener, onYouCount, FyisCard, IdeaCard, MeetingCard, MessageCard, ReplyCard, ReportCard, SetupCard, SourceMark, WalkCard, sourceColor } from "./assistantCards.jsx";
import { summarize } from "./walkSummary.js";
import { refreshToday, useCalendarToday } from "./calendarToday.js";
import FeedView from "./FeedView.jsx";
import { MORE_PX, backAt, dueWord, placed, pulledRow, sectionDone, sectionNext } from "./funnelPile.js";
import { isImportant, level as priorityOf } from "./priority.js";
import { age, ago, band, bandUntil, plural } from "./timeWords.js";
const GeneralWorkspace = lazyView(loadGeneral);
import CanvasItem, { CANVAS_ITEM_HEIGHT, showsTask } from "./CanvasItem.jsx";
import ActionRow, { AdvisorNext } from "./ActionRow.jsx";
import { floorOf } from "./inView.js";
const CanvasBrowse = lazyView(() => import("./CanvasBrowse.jsx"));
import { ROADS, roadOfCard } from "./timelineState.js";
import { walkAdvances } from "./walkStep.js";
import { fmtDate, fmtTime } from "./dates.js";
import { noteWrite } from "./wrote.js";
import { LIT, STEP_SAID, finishLine } from "./connectorStep.js";
import { revealRing } from "./railReveal.js";
import { pressable } from "./pressable.js";
import { coalesce } from "./coalesce.js";
import { takeAsk } from "./askAssistant.js";
import "./assistantView.css";

// Which walk-through this tab was in. Per-browser and deliberately thin - one task id - because the
// walk itself lives on the server: a reload asks the task whether it is still an open set-up before
// showing anything, so a stale key restores nothing.
const WALK_KEY = "taskuary_walk_tid";
const HOLD_MS = 400;            // the longest a row waits for its item's first decision before it is drawn without one
const POP_LIT_MS = 1800;        // how long the chat pop-up shows the owner's line when the answer was only a lit button
const isOpenWalk = (t) => !!t && t.SourceRef === "assistant:setup" && !["done", "dropped"].includes(t.Status);
// markers the server writes on a line that are NOT cards (concierge.SETUP_QUESTIONS): the line is its words
// ...and a line that carries its own words (concierge: a failed act's way on, the already-seen opens): never an item card
const NOTE_KINDS = new Set(["setup_questions", "words"]);

// what a PERSON sent, whatever lane it landed in (funnel.came_in): a slipped follow-up about a mail
// is still mail, and the walk that skipped it said "0 of them are mail" with five in the pipe

// WHAT THE HEADING ALREADY SAID. A row speaks only when its own word ADDS something: "slipped"
// under fyi does, "fyi" under fyi does not (the owner, 2026-09-16: "show emoji if it says
// something besides for what lane it's in"). Compared on the WORD, not the lane, so a kind that
// overrides its lane's word - agentdone, wrapup - is judged on the word it actually shows.
// An agent WORKING says so with the ring spinning round its icon, not a word (the owner, 2026-10-21), and a GOAL says its steps.
const BAND_SAYS = { reports: "report", fyi: "fyi" };
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
    ? "Taskuary could not read the list just now. Press Next to try again."
    : detail.retryable === false
    ? "That Next request may already have completed. Review the refreshed conversation before acting again."
    : "Taskuary could not move on just now. Press Next to try again.");
  if (demoNo(e)) DEMO_SAID.add(demoNo(e));
  return (typeof detail === "string" ? detail : null) || e?.message || "Taskuary could not answer.";
};
// THE DEMO SAYING NO (U8, 2026-10-17): a refusal is the demo speaking, so it is posted as a plain line of its own - it came in
// red with "Report this bug" under it, as if the app had broken. setErr below routes any sentence in this set to the chat.
const DEMO_SAID = new Set();
const demoNo = (e) => (e?.response?.status === 403 && e.response.data?.demo ? String(e.response.data.detail || "This is the demo - nothing is sent.") : "");
// what an empty rail offers: the same doors as the welcome block (runChip knows these three)
const IDLE_CHIPS = [{ verb: "newtask", label: btn("new_task") }, { verb: "setupask", label: "Set something up" }, { verb: "tour", label: "Change my setup" }];   // not a second "set up" beside "Set something up" (U14)
// the presses that start an agent on an item: each opens the agent box first (askAgent) - `coder` is coding_agent's old name
const AGENT_VERBS = ["coding_agent", "regular_agent", "coder"];
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
        <span className="tag">MEMORY</span>
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

// The one hook React runs BEFORE it changes the page (getSnapshotBeforeUpdate, class components only): Pile reads where its rows are
// drawn there, so a glide that changes course starts from that frame - after the change a row React moved has lost it
class BeforeCommit extends React.Component {
  getSnapshotBeforeUpdate() { this.props.take(); return null; }
  componentDidUpdate() {}
  render() { return null; }
}

function Pile({ pile, current, onPull, error, onRetry, onSection, onCurrent, onMoreFyi, settingUp = false, noAi = false, tag = "on the table", coming = false }) {
  const items = pile?.items || [];
  const sendCaps = useCapabilities();       // a draft its channel cannot send wears "draft to copy", never the flag (railStatus)
  // a task read newer than this rail takes back its agent lane (railStatus.agentGone): the row draws again when one says something new
  const [, reread] = useState(0);
  useEffect(() => watchReads(() => reread((n) => n + 1)), []);
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
  // BETWEEN TWO BATCHES the band keeps room for the one on its way (the 2026-10-25 sweep): "All read, next" lands the settled rail before the
  // next batch is on the table, and for that moment the band fell to its floor - "6 more fyi" between 8 and 4, "2 more fyi" before none.
  // The batch the server has chosen next (expected_next_members) holds its rows in view until it lands; it is not ringed before it is up.
  const nextBatch = new Set(!current && coming && (pile?.expected_next_members || []).length > 1 ? pile.expected_next_members : []);
  const curKey = current && !batch ? current.key : null;
  // a task named in the chat is on the table without being in the pile: it joins its own band
  const known = curKey && visibleItems.some((i) => i.key === curKey);
  // SHOWN IS READ, so the moment a batch goes up its rows leave the pile - and the rail had
  // nothing left to ring. While the batch is ON THE TABLE its entries are put back, in their own
  // band, so you can see the four things being talked about instead of watching them disappear.
  const have = new Set(visibleItems.map((i) => i.key));
  const onTable = batch ? (batch.items || []).filter((i) => i.key && !have.has(i.key)) : [];
  // the card on the table lends the row its words; WHERE the row sits is the rail's (placed) - its older lane drew a
  // working agent under Your task until the next chat read refreshed it (the owner, 2026-09-28). A row from outside the pile takes
  // its place in the order (inOrder), never the top of its section.
  const drawn = inOrder(drawOrder(visibleItems).map((i) => (i.key === curKey ? placed(i, current) : i)),
    [...(curKey && !known ? [pulledRow(current)] : []), ...onTable]);
  const prev = useRef(null);
  const [landing, setLanding] = useState(new Set());
  // ...and only into a rail that had rows: after an empty one (a read that failed, a first sync) every row would fall at once, the
  // whole band squeezed above the pipe and drawn over itself on the way down (G8)
  // ...and never a row this rail has drawn before: a report put on the list leaves the rail and comes back a read later as its task, and it
  // fell in from above the pipe across every row of Tasks (the dead-end walk's SWAP, 2026-10-25) - it comes back in its slot
  const ever = useRef(new Set());
  const arrivalsOf = (was) => (was?.size ? new Set([...arrivals(was, items)].filter((k) => !ever.current.has(k))) : new Set());
  useEffect(() => {
    const fresh = arrivalsOf(prev.current);
    prev.current = keysOf(items);
    for (const k of prev.current) ever.current.add(k);
    if (!fresh.size) return undefined;
    setLanding(fresh);
    const t = setTimeout(() => setLanding(new Set()), 40);       // one frame above the pipe, then it falls to its slot
    return () => clearTimeout(t);
  }, [displayRevision(pile)]);                                     // eslint-disable-line react-hooks/exhaustive-deps
  // ...and above it from its FIRST frame (G8): the mark above is set after that frame is painted, and the arrival was drawn once in its
  // slot, over the row still gliding out of it. Until the effect has run, the rows this pile adds are told apart here.
  const arriving = arrivalsOf(prev.current);
  // ...but never the row on the table: Put it on my list settles the report and brings it back a read later as the task it now is, and it
  // fell in from above the pipe across the rows of Tasks while the canvas already showed it (the dead-end walk's SWAP, 2026-10-25). Like an
  // entering row, the ring lands with its card, in its slot
  const falls = (k) => k !== curKey && (landing.has(k) || arriving.has(k));
  // The NEXT ring has to be what the Next button will actually bring up. The server skips what an
  // agent has in hand and what this walk already showed (funnel.next_item); the marker did not, so a
  // coding agent parked on a question wore NEXT while two fyi about lunch came out instead (2026-09-03).
  // New servers capture the selection from the same snapshot as this pile. FYI batches have a
  // composite selected key, so their first ordered member wears the visible NEXT marker.
  const nextKey = nextMarkerKey(pile, items, current);
  // ...and its task is read now, so Next opens it whole (taskDetail.js, G8) - a rail row under the pointer the same way, below
  const nextTid = items.find((i) => i.key === nextKey)?.tid || 0;
  // ...again whenever the rail is drawn anew: a write in between let the held read go (taskDetail.js), and it is read once more here
  useEffect(() => { if (nextTid) prefetchTask(api, nextTid); }, [nextTid, displayRevision(pile)]);   // eslint-disable-line react-hooks/exhaustive-deps

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
  // tasks draw in full; reports and fyi divide what is left of the
  // rail's height, floor of two (funnelPile.fillCaps). It is MEASURED from the scroller, so the
  // answer follows the window instead of being a number somebody picked.
  // PASSED means you moved ON from it: the card on the table has been shown (the walk marks it at once)
  // but you are still on it, so it keeps its band until Next takes you past it (the owner, 2026-09-23:
  // "it started in your task and moved to passed without touching anything")
  const atTable = (i) => !!current && (i.key === current.key || (current.aliases || []).includes(i.key) || (i.aliases || []).includes(current.key));
  // ...and the row on the table stays in the band it was clicked in (2026-10-19 UI walk): a For later row clicked was taken up by the
  // server (no longer put down) and jumped to Tasks under the pointer. It moves when the owner moves on, never while they look.
  const lastLevel = useRef({}), pin = useRef(null);
  const tableRow = current ? drawn.find(atTable) : null;
  if (!tableRow) pin.current = null;
  else if (pin.current?.key !== tableRow.key) pin.current = { key: tableRow.key, level: lastLevel.current[tableRow.key] || null };
  const bands = bandsOf(drawn.map((i) => (i.surfaced && atTable(i) ? { ...i, surfaced: false } : i)), pin.current);
  lastLevel.current = Object.fromEntries(bands.flatMap((b) => b.items.map((i) => [i.key, b.level])));
  // the FYI band is costed whole: its "N more fyi" stays while any of it is not here (fillCaps reads `total`)
  if (tail) for (const b of bands) if (b.level === "fyi") b.total = b.items.length + tail;
  // how close to empty, once that is worth saying (the owner asked for it at "halfway down the
  // funnel", so from fifteen: the count is the encouragement - no header, no total)
  // ...and it is THE HEADINGS ADDED UP, the table's rows with them until they are put down (funnelPile.awayFromClear)
  const left = awayFromClear(bands, tail);
  const cheer = !left || left > 15 ? "" : left === 1 ? "One more and you're clear."
    : left <= 5 ? `${left} to go, then you're clear.` : `${left} away from clear.`;
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
    // ...where the pile STARTS in the scroller's content, however far it is scrolled: read against the scroller's own top, a rail
    // scrolled down (the ring revealed below the fold) measured a room the height of the scroll larger than it had
    const measure = () => {
      const top = el.getBoundingClientRect().top - scroller.getBoundingClientRect().top + scroller.scrollTop;
      const next = Math.max(0, scroller.clientHeight - top - PILE_FOOT);
      setRoom((was) => (Math.abs(was - next) > 4 ? next : was));
    };
    measure();
    if (typeof ResizeObserver === "undefined") return undefined;
    // ...and again when what sits ABOVE the pile comes, goes or changes height ("Removed <title> - Undo", UndoLine): the scroller keeps
    // its size, so the room measured with the line there stayed after it was dismissed, and the reverse - rows held back under an empty rail
    const ro = new ResizeObserver(measure);
    const watch = () => { ro.disconnect(); ro.observe(scroller); for (let s = el.previousElementSibling; s; s = s.previousElementSibling) ro.observe(s); measure(); };
    watch();
    const mo = typeof MutationObserver === "undefined" ? null : new MutationObserver(watch);
    mo?.observe(scroller, { childList: true });
    return () => { ro.disconnect(); mo?.disconnect(); };
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
  // ...and it is given back when the room changes, and when the rail it was taken for has room again: a trim taken in one moment's
  // overflow (a shorter window, a line above the pile) stayed until a band's count changed, so a tall rail kept "9 more fyi" over an
  // empty half (the owner, 2026-10-26). Given back once per change, never right after it was taken, so the two can never take turns.
  const [trim, setTrim] = useState(0), grew = useRef(false);
  useLayoutEffect(() => { setTrim(0); grew.current = false; }, [sig, room]);
  // the row on the table is 24px taller than the rest, and it is drawn inside one of these bands
  const base = fillCaps(room - (curKey ? CUR_H - ROW_H : 0), bands);
  // how many rows the capped bands could still give back before they are at their floor. Past that
  // the rail genuinely does not fit and scrolls: tasks are never trimmed.
  const headroom = CAPPED.reduce((n, level) => n + Math.max(0, (base[level] ?? 0) - FLOOR), 0);
  const caps = trimCaps(base, bands, trim);
  // ...and the FYI band asks for its next page while the rail has room for it (fyiHasRoom), not only once it is opened by hand - once
  // per count it has, so a page that brings nothing new is never asked for again
  const fyiHave = bands.find((b) => b.level === "fyi")?.items.length ?? 0, fyiAsked = useRef(-1);
  const fyiFills = !!tail && !trim && fyiHasRoom(room - (curKey ? CUR_H - ROW_H : 0), bands);
  useEffect(() => { if (fyiFills && fyiAsked.current !== fyiHave) { fyiAsked.current = fyiHave; onMoreFyi?.(); } }, [fyiFills, fyiHave]);   // eslint-disable-line react-hooks/exhaustive-deps
  // what a band draws: its cap's worth, and whatever is on the table wherever in the band it sits
  const shownIn = (level, rows) => { const cap = opened.has(level) ? rows.length : (caps[level] ?? rows.length);
    return rows.filter((i, n) => n < cap || i.key === curKey || batchKeys.has(i.key) || nextBatch.has(i.key)); };
  // THE RAIL IS ONE TAB STOP (owner-approved, 2026-10-20): a listbox with a roving tabindex - Tab lands on the row on the table (else
  // the first), Up/Down move the focus ring, Enter opens the row as a click does, Escape gives focus back to where it came from
  const [kbdKey, setKbdKey] = useState(null);
  // ...and the stop goes with the table: a row picked by keyboard, then a mouse Next, left the tab stop on the row the walk had left, so Tab
  // back in and Enter put it on the table again (the 2026-10-25 sweep)
  useEffect(() => { setKbdKey(null); }, [current?.key]);
  const kbdBack = useRef(null);
  const stops = bands.flatMap(({ level, items: rows }) => shownIn(level, rows)).filter((i) => !i.settling).map((i) => i.key);
  const tabKey = stops.includes(kbdKey) ? kbdKey : stops.includes(curKey) ? curKey : stops[0];
  const railKey = (e) => {
    const all = [...(wrapRef.current?.querySelectorAll('.card[role="option"]:not([aria-disabled="true"])') || [])], at = all.indexOf(document.activeElement);
    if (at < 0 || !["ArrowDown", "ArrowUp", "Enter", "Escape"].includes(e.key)) return;
    e.preventDefault();
    if (e.key === "Enter") { all[at].click(); return; }
    if (e.key === "Escape") { const b = kbdBack.current; kbdBack.current = null; if (b?.isConnected) b.focus(); else all[at].blur(); return; }
    const to = all[Math.max(0, Math.min(all.length - 1, at + (e.key === "ArrowDown" ? 1 : -1)))];
    setKbdKey(to.closest("[data-tq-key]")?.dataset.tqKey || null); to.focus();
  };
  // A ROW THAT JOINS A BAND WAITS FOR THE GLIDE (G8): a row moving in - passed into For later, a slot freed under a cap - was drawn in
  // its slot at once, under the rows still gliding out of it, for ten-odd frames. It comes in once the others have moved. Not on the
  // first draw, and not a row falling in from above the pipe (`landing`), which has its own way in.
  // ...nor the row on the table: the ring lands with its card, in the same frame
  // ...and a row this rail drew before that COMES BACK waits too: it does not fall from above the pipe (`ever`), and it was not in the last
  // pile, so it was drawn in its slot at once while the rows under it glided down out of it - a task closed behind its card put its row
  // back at the top of its band, two rows on one spot for ~15 frames (the dead-end walk's SWAP, faults closed, 2026-10-27)
  const placedNow = useRef([]), placedBefore = useRef(null), enterTimer = useRef(0);
  placedNow.current = [];
  const [entering, setEntering] = useState(() => new Set());
  useLayoutEffect(() => {
    const now = placedNow.current, was = placedBefore.current, inPile = prev.current;
    placedBefore.current = new Set(now);
    const fresh = was ? now.filter((lk) => !was.has(lk)).map((lk) => lk.slice(lk.indexOf(" ") + 1)).filter((k) => k !== curKey && (inPile?.has(k) || ever.current.has(k))) : [];
    if (!fresh.length) return;
    setEntering(new Set(fresh));
    clearTimeout(enterTimer.current); enterTimer.current = setTimeout(() => setEntering(new Set()), 700);
  });
  useEffect(() => () => { clearTimeout(enterTimer.current); }, []);
  // ...AND A ROW REORDERED IN ITS BAND GLIDES TOO: React moves its node in the page to keep the order, and a moved node starts
  // from its new place with no transition - the row put on the table jumped to its slot, full height, over rows still gliding
  // past it (a rail click: 15 frames of rows drawn on each other). Such a row is sent back to where it was drawn and let go from there.
  // ...AND A GLIDE THAT CHANGES COURSE RESTARTS EVERY ROW TOGETHER. A close rings the next row at once (drawn ahead) and the pile's
  // answer lands mid-glide with the closed row gone: the rows whose top changed again began a fresh .55s glide from where they were,
  // while the ringed row's height kept its old one - it grew into the row under it (CI's slow runner, SWAP: 3-6px for a few frames).
  // So on any change of course every row starts again from where it is drawn now, top and height, on the one curve: the drawn frame
  // has no overlap and neither has the end, and one curve over one time never makes one in between.
  // WHERE IT IS DRAWN is read before React changes the page (BeforeCommit). Read after, a row React moved had lost its glide, and it
  // was sent back to where it was last GOING, not where it was: a send moves the row on the table inside its band (the walk's faults
  // pass: 0 -> 99), and when that lands while a glide still runs - CI's slow runner - the row restarted off its drawn place, over the
  // row under it (SWAP, faults unknown, 2026-10-21).
  const rested = useRef(new Map()), restNow = useRef(new Map()), drawnAt = useRef(null);
  restNow.current = new Map();
  const takeDrawn = () => {
    const was = rested.current, now = restNow.current;
    drawnAt.current = null;
    if (!was.size || (now.size === was.size && [...now].every(([k, n]) => was.get(k)?.top === n.top && was.get(k)?.h === n.h))) return;
    drawnAt.current = new Map();
    for (const el of wrapRef.current?.querySelectorAll(".tq-pile-row[data-tq-key]") || []) {
      const cs = getComputedStyle(el);
      drawnAt.current.set(`${el.closest("[data-tq-run]")?.dataset.tqRun} ${el.dataset.tqKey}`, [parseFloat(cs.top), parseFloat(cs.height)]);
    }
  };
  useLayoutEffect(() => {
    const was = rested.current, now = new Map(), drawn = drawnAt.current;
    drawnAt.current = null;
    const els = [...(wrapRef.current?.querySelectorAll(".tq-pile-row[data-tq-key]") || [])].filter((el) => !el.classList.contains("landing"));
    for (const el of els) {
      const k = `${el.closest("[data-tq-run]")?.dataset.tqRun} ${el.dataset.tqKey}`;
      now.set(k, { el, top: parseFloat(el.style.top) || 0, h: (el.classList.contains("current") ? CUR_H : ROW_H) - 3 });   // its rest: less the 3px gap
    }
    rested.current = new Map([...now].map(([k, { top, h }]) => [k, { top, h }]));
    const moved = [...now].some(([k, n]) => !was.has(k) || was.get(k).top !== n.top || was.get(k).h !== n.h) || was.size !== now.size;
    if (!moved || !was.size) return;
    // read every row first, then write: one frame's values for all of them - as drawn before the change, or, new here, where it lands
    const from = [...now].map(([k, { el }]) => {
      const d = was.has(k) && drawn?.get(k);
      if (d) return [el, ...d];
      const cs = getComputedStyle(el);
      return [el, parseFloat(cs.top), parseFloat(cs.height)];
    });
    for (const [el, top, h] of from) { el.style.transitionProperty = "opacity, transform"; el.style.top = `${top}px`; el.style.height = `${h}px`; }
    void wrapRef.current.offsetHeight;                         // that frame is the start; then the glide runs from it, for every row at once
    for (const { el, top } of now.values()) { el.style.transitionProperty = ""; el.style.top = `${top}px`; el.style.height = ""; }
  });
  useLayoutEffect(() => {
    const el = wrapRef.current;
    const scroller = el?.closest("[data-tq-rail]");
    if (!el || !scroller) return;
    const over = scroller.scrollHeight - scroller.clientHeight;
    if (over > 4 && trim < headroom) { grew.current = true; setTrim((was) => Math.min(headroom, was + Math.ceil(over / ROW_PX))); return; }
    if (over > 0 || !trim || grew.current) return;
    const box = scroller.getBoundingClientRect(), end = el.getBoundingClientRect().bottom - box.top + scroller.scrollTop;
    const free = Math.floor((scroller.clientHeight - (parseFloat(getComputedStyle(scroller).paddingBottom) || 0) - end) / ROW_PX);
    if (free > 0) setTrim((was) => Math.max(0, was - free));
  });

  return (
    <div className="tq-pile" data-tq-keep ref={wrapRef} role="listbox" aria-label="Your list" onKeyDown={railKey} data-tq-left={left}
      onFocus={(e) => { if (!wrapRef.current?.contains(e.relatedTarget)) kbdBack.current = e.relatedTarget || null; }}>
      <BeforeCommit take={takeDrawn} />
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
        <div className="tq-pile-empty" data-tq-pile-setup=""><b>Your work shows up here</b>Setup: {settingUp}. What comes in is then sorted into this list.</div>
      ) : !drawn.length && noAi ? (
        // NOTHING COULD BE JUDGED, so nothing is "done" (owner-approved, 2026-10-21): with no AI connected, setup put away, the rail said
        // "All done - nothing is waiting on you" over a day in which nothing that arrives can be read or sorted
        <div className="tq-pile-empty" data-tq-pile-no-ai=""><b>Nothing can be sorted yet</b>No AI is connected, so what comes in cannot be read and sorted into this list.
          <button type="button" className="tq-pile-retry" data-tq-connect-ai="" onClick={connectAi}>{CONNECT_AI}</button>
        </div>
      ) : !drawn.length ? (
        <div className="tq-pile-empty"><span className="mark">✓</span><b>All done</b>Nothing is waiting on you. New things land here as they arrive, and Taskuary speaks up.</div>
      ) : bands.map(({ level, items: rows }) => {
        const open = opened.has(level);
        const extra = level === "fyi" ? tail : 0;           // the band's rows not here yet - counted, never dropped
        // only the bands the rail is allowed to cap can be folded; tasks are never hidden, so a
        // chevron on them would offer nothing
        const folds = CAPPED.includes(level) && rows.length > FLOOR;
        // what is on the table is never capped away, wherever in its band it sits
        const shown = shownIn(level, rows);
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
          if (!falls(item.key)) restNow.current.set(`${level} ${item.key}`, { top, h: (item.key === curKey ? CUR_H : ROW_H) - 3 });
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
            <div className={`tq-pile-head${folds ? " folds" : ""}`} data-tq-section-head={level}
              title={`Walk ${levelLabel(level)} - ${LEVEL_META[level]?.hint || ""}`}
              {...pressable(() => onSection(level))}>
              {/* each band its own SUBTLE tint (the owner, 2026-09-28: "now all the pills are the same. make them subtly
                  different") */}
              <span className={`lvl-${level}`}>{levelLabel(level)}</span>
              {folds && <i className="fold" title={open ? `Collapse ${levelLabel(level)}` : `Show all ${rows.length + extra}`} aria-expanded={open}
                {...pressable((e) => { e.stopPropagation(); if (!open && extra) onMoreFyi?.(); setOpened((cur) => {
                  const next = new Set(cur);
                  if (next.has(level)) next.delete(level); else next.add(level);
                  return next;
                }); })}>{open ? "▾" : "▸"}</i>}
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
                // URGENT IS A QUIET SHADE ON THE ROW, IN ITS PLACE (the owner, 2026-10-22: "remove the urgent section and just add quiet
                // shading around it") - no heading of its own, no icon, no word; Next walks it in its place
                const hot = !i.settling && isUrgent(i);
                // ...and the DOT says the stored priority whatever the band (2026-10-26): a draft waiting for the owner's yes, a blocked agent,
                // a goal or a wait on someone never reaches band 1, so an urgent one drew regular's sage - raising important to urgent
                // visibly lowered its mark. The owner's ruling (2026-10-25): the category IS the dot's colour. The band and the walk stay
                const urgentDot = !i.settling && (hot || priorityOf(i.priority) === "urgent");
                // ...and IMPORTANT a quieter mark of its own, in its place too - never a move (the owner, 2026-10-25: "show it as a mark
                // in its row's place"); urgent outranks it, so an urgent row wears urgent's shade alone
                const imp = isImportant(i, hot);
                const cls = ["tq-pile-row", falls(i.key) ? "landing" : entering.has(i.key) ? "entering" : "", i.settling ? "settling" : "", urgentDot ? "urgent" : imp ? "important" : "",
                  isCur ? "current" : inBatch ? "inbatch" : i.key === nextKey ? "next" : ""].filter(Boolean).join(" ");
                // NO PILLS ON A ROW (the owner, 2026-09-28: "nothing else has pill"): a row's state is its mark and word, the same
                // for every lane - "ready to send" and "agent waiting on you" included
                // ...and every other row says its lane - mark and word - unless that is the very
                // thing the heading above it already said (BAND_SAYS).
                // A MEETING says its clock time instead. "coming up" is what the shade and
                // the age already tell you; what it does not tell you is when to be there (the
                // owner, 2026-09-16: "for calendar invite you need to say the actual time of the
                // meeting"). It goes on the card rather than in the gutter, which is an age column
                // for every row and too narrow for a time.
                // THE ROW'S STATE IS ON ITS ICON (owner-approved 2026-10-21): the ring spinning while an agent works, and a badge on the
                // logo only where the move is the owner's - the hand of somebody waiting on you, waving, and the flag of a reply ready to
                // send (the owner, 2026-10-22: too many emojis on the rail); every other state is the plain logo (railStatus.BADGE, the
                // same reading the task header's pill takes). The words and emoji on the row's right go, so the title has the room; the
                // state's words are the icon's label and hover. A row in a band whose heading already says it (fyi, report) wears none;
                // a goal keeps its own mark. Urgent is the row's shading, a meeting its time.
                const goal = String(i.kind || "").startsWith("goal");
                const page = i.tid ? pageRead(i.tid) : null, why = rowWhy(i, page);
                const st = i.settling || goal || i.kind === "meeting" ? null : railStatus(i, !canSend(sendCaps, i.channel), page);
                const shown = st && (st.spins || meta.word !== BAND_SAYS[level]) ? st : null;
                const word = i.settling ? ""
                  : i.kind === "meeting" ? `invite · ${fmtTime12(i.when)}`
                    // a goal says only that it SLIPPED (red); on track or not started, its steps say enough (the owner, 2026-10-21)
                    : goal ? (i.kind === "goal_slipped" ? meta.word : "") : "";
                return (
                  <div key={i.key} className={cls} data-tq-key={i.key} data-tq-urgent={urgentDot ? "" : undefined} data-tq-important={imp ? "" : undefined}
                    style={{ top: falls(i.key) ? -ROW_H : top }}>
                    {/* For later counts DOWN to when it comes back, in the same short form the age column uses */}
                    {/* ...every other row says its ARRIVAL, never a new age for a reply - and no "+N" for one either: what came in since is
                        read inside the task (the owner, 2026-10-26: "if it's in the task it's fine no?") */}
                    <span className="when" title={level === "later" && backAt(i) ? `back ${ago(backAt(i))}` : goal || i.kind === "meeting" ? undefined : ageHover(i)}>
                      {goal ? dueWord(i.due)      /* a goal's clock is its date (spec 2026-10-12) */
                        : level === "later" ? bandUntil(backAt(i)) : band(i.kind === "meeting" ? i.when : arrivedAt(i))}</span>
                    {/* the dot is the BAND's colour, the pill's own (the owner, 2026-10-06: one palette, everywhere) - where it
                        came from is the logo inside the row */}
                    {/* ...and an IMPORTANT row's dot is the theme's slate instead - the category IS the dot's colour, in the app's own
                        scheme (the owner, 2026-10-25: "match the app's scheme", no new hues); urgent keeps its shade as it was */}
                    <span className="rail"><i style={{ background: imp ? PRIORITY_COLOR.important : LEVEL_COLOR[level] || sourceColor(i) }} /></span>
                    {/* the row already on the table SHOWS it - on a phone that means closing the drawer over it. Any other row is pulled
                        QUIETLY, as a search hit is: a 'Show me "..."' bubble per click was free text saying what the click did (2026-10-22) */}
                    <div className="card" role="option" aria-selected={isCur} aria-disabled={i.settling ? true : undefined}
                      tabIndex={i.key === tabKey ? 0 : -1} onFocus={() => setKbdKey(i.key)}
                      onClick={() => (isCur ? onCurrent?.() : !i.settling && onPull(i.key))}
                      onPointerEnter={() => { if (!isCur && i.tid) prefetchTask(api, i.tid); }}
                      aria-label={urgentDot ? `${i.title} - urgent` : imp ? `${i.title} - important` : undefined}
                      title={[i.who, st?.word || meta.word, i.ref, imp ? "important" : "", i.promoted ? 'moved up - it looked urgent' : '', why].filter(Boolean).join(" · ")}>
                      <div className="t">
                        {/* AN AGENT AT WORK is a ring spinning round the row's icon (the owner, 2026-10-21) - it stops when the agent
                            finishes, asks, fails or is stopped; the highlighted border stays the table's alone. A goal wears its mark. */}
                        <StatusLogo status={shown} agent={i.working || i.agent} className="logo">
                          {goal ? <span className="goal">{meta.mark}</span> : <SourceMark item={i} size={15} />}</StatusLogo>
                        {!!rankNo[i.key] && <span className="tq-pile-rank" title={`#${rankNo[i.key]} of this batch, by importance`}>
                          {CIRCLED[rankNo[i.key] - 1] || rankNo[i.key]}</span>}
                        <b className={goal ? "goal-t" : undefined}>{i.title}</b>
                        {/* a goal's row is "🎯 title · 2 of 5 steps" - its count, never its TQ number (the owner, 2026-10-21) */}
                        {goal && Number.isInteger(i.steps) && i.steps > 0 && <span className="tq-pile-steps">· {i.steps_done || 0} of {i.steps} steps</span>}
                        {/* which task this IS. It is how you say "TQ-0588" to the assistant, how you
                            match a row to the Tasks tab, and it was only ever in the tooltip.
                            ...on the row you are looking at: on every row it cut each subject at a laptop's 334px rail to ~14
                            characters (the walk click-through, 2026-10-17) - the others carry it in the hover */}
                        {!!i.ref && isCur && !goal && <span className="tq-pile-ref">{i.ref}</span>}
                        {/* a BATCH says how far it got in the row's own height - "1/4"; the whole line on hover and on the table */}
                        {!!batchNo[i.key] && <span className="tq-pile-ref" title={batchNo[i.key].line}>{railShort(batchNo[i.key].states)}</span>}
                        {i.settling && <span className="tq-pile-tag">reading…</span>}
                        {!!word && (
                          <span className={`tq-pile-word${goal ? " keep" : ""}`}
                            style={meta.role === "bad" ? { color: ROLES.bad.ink } : undefined}>
                            {!goal && <i>{meta.mark}</i>}<span className="w">{word}</span></span>
                        )}
                      </div>
                      {/* the line under the title is the NEWEST message once there is more than one (the owner, 2026-10-23) */}
                      {isCur && <div className="sub">{batchNo[i.key]?.line || (latestLine(i) ? [latestLine(i), ago(i.last_at)]
                        : [why, i.kind === "meeting" ? age(i.when) : ago(i.since || i.when)]).filter(Boolean).join(" · ")}</div>}
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
// WHAT WAS PRESSED, ON THE CARD IT WAS PRESSED ON (the owner, 2026-10-22: "put a little animation on the corner of the past task - like
// button marked done not free text"): the button's own label as a quiet badge (assistantTurns.pressedOf)
// ...and a Close with a note wears its note after the badge, one muted truncated line, whole on hover (the owner, 2026-10-23: "write on it
// marked done with note")
function Pressed({ label, note = "" }) {
  return <><span className="tq-pressed" data-tq-pressed={label} title={note || undefined}>✓ {label}</span>
    {note && <span className="tq-pressed-note" data-tq-pressed-note="" title={note}>{note}</span>}</>;
}
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
  // a PREPARED answer's line (drawAhead, `held`) says its words at once and draws its card once the press has answered: a card's
  // first reads write (a task's origin filed on its first detail read, the Advisor asked), and a write under a press between
  // its admission and its commit check refused the press as stale (PW-118, 2026-10-20)
  // ...and not its words either: they are the card's own lead, shown only where no card hides them, so a held card's "Next up: 4 FYIs."
  // stood alone as a bubble until the press answered (the owner, 2026-10-25: "saw a stray text showing next 4 fyi every once in a while")
  if (m.held) m = { ...m, card: null, text: "" };
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
        onNavigate={actions.navigate} onOpenTask={actions.openTask} onClose={() => actions.browseClose(m.id)} onSaid={actions.said} />
    </div>
  );
  if (m.role === "receipt") return (
    <div className="tq-msg receipt"><span /><div className="body">{m.status === "warn" ? "" : m.status && m.status !== "done" ? "✗ " : "✓ "}{m.text}{pressedOf(m) && <Pressed label={pressedOf(m)} note={pressedNoteOf(m)} />}
      {/* a receipt can carry the walk's own word: a sweep puts the table down and OFFERS Next rather
          than jumping to the next thing by itself (the owner, 2026-09-11). Same strip, same buttons.
          ...and its Open and Report this bug go there too: a button in the line is against "no button in line ever" (2026-10-06),
          and an Open TQ-x and a Report this bug link stood in the chat under a failure (the walk click-through, 2026-10-17) */}
      {last && <BarVerbs owner={`line:${m.id}`} chips={receiptChips(m)} busy={actions.busy} onChip={actions.chip} />}
    </div></div>);
  // THE END OF THE WALK SAYS NOTHING (the owner, 2026-10-23: "yes remove the sentence, just the button"): a line with no words and no item
  // is only its buttons - Walk me through my tasks and its Opens - on the row by the prompt, never an empty bubble wearing the mark
  if (m.role === "assistant" && (!m.card || m.card.kind === "words") && !m.proposal && !String(m.text || "").trim() && !pressedOf(m))
    return last ? <BarVerbs owner={`line:${m.id}`} chips={barHolds ? [] : chipsOf(m)} busy={actions.busy} onChip={actions.chip} /> : null;
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
    dashboard: <DashboardCard card={c} onOpenTask={actions.openTask} onDone={actions.done} />,
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
    fyis: <FyisCard card={c} onDone={actions.done} onSurface={actions.surface} onTimeline={actions.timeline} onPropose={actions.propose} onAgent={actions.agent} />,
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
        onNext={() => actions.next()} busy={actions.busy} picking={actions.picking} onFold={() => canvas.fold(c.key)} onAfter={() => actions.advance(null, true)}
        onLeave={() => canvas.putDown(c.key, c.tid)} onStay={(why) => canvas.pickUp(c.key, why)} onReminded={(out) => actions.reminded(out, c)}
        onListChanged={actions.reload} onChanged={actions.changed} onOpenTask={actions.openTask} lit={canvas.lit} advice={canvas.advice}
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
  // ...except the two a SEND folded it with (actions.sent): Mark done and Next are what is left to do with it, not its old words
  const moved = !!m.card && (!live || foldedNow) && !m.sent;
  const strip = moved ? chips.filter((c) => c.verb === "next") : inCard ? chips.filter((c) => !c.verb) : chips;
  const nextChip = verbs.find((c) => c.verb === "next");
  const nav = { busy: actions.busy, items: actions.items, surface: actions.surface, row: live && last && !!canvas, ref: c?.ref || "",   // Next and the words ride in the row above the chat line

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
          {/* WHAT IT LOOKED AT AND PRESSED, over what it says (troubleshoot.py): the general agent's own rows, kept on the line */}
          {!!(m.steps?.length || m.card?.steps?.length) && <AgentSteps data={{ steps: m.steps?.length ? m.steps : m.card.steps }} />}
          {text && !(m.card && kind && !["proposal", "walk", "setup"].includes(kind)) ? (looksMd(text) ? <Md text={text} /> : text.split("\n").map((p, i) => <p key={i}>{p}</p>)) : null}
          {/* a word pressed under a line that carries no item (a failure's Update branch): its badge on that line */}
          {!kind && pressedOf(m) && <Pressed label={pressedOf(m)} />}
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
              {pressedOf(m) && <Pressed label={pressedOf(m)} note={pressedNoteOf(m)} />}
            </div>
          )}
          {card && !foldedNow && <CardNav.Provider value={nav}>{card}</CardNav.Provider>}
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
const NO_AI_DROP = /no brain|no[ _]ai/i;       // the Advisor's own drop word for "no AI to ask" (advisor.QUIET)
export const quietWhy = (d = "") => {
  const s = String(d || "");
  if (NO_AI_DROP.test(s)) return "No AI connected yet - connect one under Connections, AI.";
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

// ...THE SAME DECISION THE TASK SHOWS, OR NOTHING (the Advisor audit's judge, 2026-10-26): the menu listed older model rows - "Someone is
// waiting on an answer from you." - beside a section that said "You usually answer Erin within the hour". It reads the one decision the
// row lit and the section says (/api/advice, advisor.decide), through the same filter (advice.taskNote): its line and what it rests on
function AdvisorNotes({ keyOnTable }) {
  const [d, setD] = useState(null);
  useEffect(() => {
    let on = true;
    api.get("/api/advice", { params: { key: keyOnTable } }).then(({ data }) => { if (on) setD(data || {}); }).catch(() => { if (on) setD({}); });
    return () => { on = false; };
  }, [keyOnTable]);
  const note = d && taskNote(d), rests = (note && d.rests) || [];
  return (
    <div className="tq-advisor-notes">
      <Typography sx={{ fontSize: 12, fontWeight: 600, color: INK, px: 1.5, pt: 1.25 }}>Advisor's notes on this one</Typography>
      <div style={{ padding: "6px 12px 8px" }} data-tq-advisor-notes-line="">
        {d === null ? <Typography sx={{ color: FAINT, fontSize: 12 }}>Reading…</Typography>
          : d.none === "no_ai" ? <><Typography sx={{ fontSize: 12.5, color: INK }}>{quietWhy("no ai")}</Typography><ConnectAi variant="outlined" sx={{ mt: 0.5 }} /></>
          : note ? <Typography sx={{ fontSize: 12.5, color: INK }}>{d.label ? `${d.label} - ` : ""}{note.line}</Typography>
          : <Typography sx={{ color: FAINT, fontSize: 12 }}>{d.label && d.verb !== "next" ? `Nothing to add - ${d.label} is the lit button.` : "Nothing to add on this one."}</Typography>}
        {rests.length > 0 && <Typography sx={{ fontSize: 11.5, color: FAINT }}>Rests on: {rests.map((r) => r.label).join(" · ")}</Typography>}
      </div>
    </div>
  );
}

export default function AssistantView({ onOpenTask, onNavigate, onChanged, active = true, request = null }) {
  const [state, setState] = useState(null);           // /api/concierge: the dock task, its turns, the AI choices
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
  // A ROW CLICKED IS NOT A NEXT PRESSED (the owner, 2026-10-26: "fix switching tasks thing of course"): every pick greyed Next for the
  // ~300 ms its pull took, on a row that had just drawn the new task. While a pick (a row, a name, a link) is in flight Next stays
  // pressable, and a press then is held and runs once the pick lands - on the item the owner was looking at, as a press always does.
  // `flight`: the walk move under way - a pick or not, and the item it is leaving, whose verbs leave the row at once (actionRow.leaveRow)
  const [flight, setFlight] = useState(null), nextHeld = useRef(false), picking = !!flight?.pick;
  // a card was let go and the next one is on its way: the settle and the deferred pick run BEFORE
  // surface() raises busy, and that second drew nothing at all (the owner, 2026-09-25: "for a second
  // there is no ... loading the next"). Its own flag, because busy would make surface() refuse to run.
  const [nextComing, setNextComing] = useState(false);
  // THE TASK BEING PUT DOWN leaves the rail at the press too. The card folded while the close ran behind the "…", but the rail
  // drew the server's pile - and a task closed off a live session waits on its write-up first, so for eighteen seconds it
  // sat on the rail as an open task already seen: under For later (the owner, 2026-10-01: "it first went to Later ... and
  // did not disappear right away"). Held until the pile no longer carries it, so a reopened task is never hidden.
  const [leavingTid, setLeavingTid] = useState(null);
  // A TASK BEING CONTINUED rings at the press the same way: "Continuing" said so at 0.3 s while its row sat still until the next
  // pile, two seconds on (press audit, 2026-10-01). Held until the pile has it working; it stays where it is, under Tasks.
  const [continuingTid, setContinuingTid] = useState(null);
  // the walk validates Current against the pile before it can say anything, and that read was
  // 5-47s (2026-09-09). busy is the TURN's interlock and surface() refuses to run while it is
  // set, so opening needs its own flag - without one the button stayed enabled, said nothing,
  // and looked broken for the whole wait.
  const [starting, setStarting] = useState(false);
  const [resetting, setResetting] = useState(false);  // replacing a chat is housekeeping, never an AI turn
  const [work, setWork] = useState([]);              // the turn's tool calls and progress, as they stream
  const [words, setWords] = useState("");            // ...and the answer's words as they are written - the finished answer replaces them
  const [steps, setSteps] = useState([]);            // ...and its own steps, looking into the app's trouble - kept on the answer after
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
  // the key whose FIRST decision is being read: its row waits for it (at most HOLD_MS), so the lit button lands with the row instead of
  // reshuffling it under the owner's hand - a lit verb kept in view pushed its neighbour into the ▾ (the dead-end walk's STILL, 2026-10-23)
  const [reading, setReading] = useState(""), [readFor, setReadFor] = useState(null);
  // ...let go only once the decision is drawn: the effect runs after the strip's own (AdvisorNext registers a move the row lacks then)
  useEffect(() => { if (readFor) setReading((r) => (r === readFor.key ? "" : r)); }, [readFor]);
  const [, setChanged] = useState(null);   // {for, reading}: a press refused as changed since the Advisor looked (B6) - said by no strip now
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
  const [slotsOn, setSlotsOn] = useState(null);        // the walk's Propose a new time / Find a time: { item, act, anchor }
  // THE ASSISTANT'S LIT BUTTON (assistantLight.js): a typed act lights the row's own verb for it until a press or the table moves on
  const [lit, setLit] = useState(null);
  useEffect(() => onPressed(() => setLit(null)), []);
  // an act makes the read held of ITS task old (taskDetail.js) - the task last on the table, since a close has put it down by the time
  // the act is told. Forgetting every read let go of the next item's too, just before the walk went on to it (G8). Next is no act
  const actedTid = useRef(null);
  // ...the item a close drew at its press is not the one acted on (drawNextEarly): the act is told after it is up
  useEffect(() => { if (currentItem?.tid && earlyRef.current?.key !== currentItem.key) actedTid.current = currentItem.tid; }, [currentItem]);
  useEffect(() => onPressed((id) => { if (!/(^|:)next$/.test(String(id || ""))) forgetTasks(actedTid.current ?? null); }), []);
  // ...and a write anywhere - an agent, another tab, a sync - makes that task's held read old (all of them, when it names none)
  useEffect(() => onLive("task-changed", (ev) => forgetTasks(ev?.task_id ?? null)), []);
  const [continueOn, setContinueOn] = useState(null);  // the walk's Continue: { task, anchor, ref }
  // ...and the owner's notes the Assistant lit it with ("rerun it with these notes: ..."): its box opens holding them, for that task
  const continueNote = useRef(null);
  const noteFor = (tid) => (continueNote.current && Number(continueNote.current.tid) === Number(tid) ? continueNote.current.note : "");
  const pics = usePromptImages();                        // pictures sent with the chat line
  // ...and the task view's own Continue on the canvas (TaskPage) asks for the same card
  useEffect(() => {
    const on = (e) => { setNoteOn(null); setAgentOn(null); setContinueOn({ task: e.detail.task, ref: e.detail.ref }); };
    window.addEventListener("tq-continue", on);
    return () => window.removeEventListener("tq-continue", on);
  }, []);
  // ...and Close with a note, the same card: what came of it, and the task view's own close behind the button
  const [noteOn, setNoteOn] = useState(null);           // { task, ref, close(note) }
  // ...and the task view's Run another agent closes them: one agent box open at a time
  // SEND TO AGENT ON AN ITEM WITH NO TASK PAGE - an email, an fyi, a report run - opens the agent box under it (RunForm.AgentAsk):
  // { item, coding }. Nothing starts until its Start (the owner, 2026-10-23: "you need to write prompt what about the email ... is the issue")
  const [agentOn, setAgentOn] = useState(null);
  useEffect(() => {
    const on = () => { setContinueOn(null); setNoteOn(null); setAgentOn(null); };
    window.addEventListener("tq-next-run", on);
    return () => window.removeEventListener("tq-next-run", on);
  }, []);
  useEffect(() => {
    const on = (e) => { setContinueOn(null); setAgentOn(null); setNoteOn(e.detail); };
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
  // ...and the agent box goes with its item the same way
  const agentKey = useRef(undefined);
  useEffect(() => {
    if (agentOn && agentKey.current !== undefined && agentKey.current !== current) setAgentOn(null);
    agentKey.current = agentOn ? (agentKey.current ?? current) : undefined;
  }, [current, agentOn]);
  const [emojiEl, setEmojiEl] = useState(null);
  const [speakOnState, setSpeak] = useState(speakOn);
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
  const browseRef = useRef(null), openTaskRef = useRef(null), openMsgRef = useRef(null), browseDownRef = useRef(null);
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
  // every move of the table made HERE, counted: a server word read before one is older than it (readChat, loadPile)
  const tableMoves = useRef(0);
  // ONE RULE FOR WHAT IS ON THE TABLE (the owner, 2026-10-25: "make sure we don't have this issue, one code that's it"): an item the walk
  // pressed past or closed - Next, Mark done, Remind me, Close with a note, any put-down - never comes back to the table unless its row is
  // clicked. The walk had several voices for "current": the server's answer, a chat re-read's Current, the line drawn ahead, and the canvas
  // falling back to the newest card in the chat - and any one of them put a closed task back up after Next had moved on (a done task
  // bouncing back over the agent row Next had brought). Every road to the table asks this record: putOnTable refuses a left item, the
  // early draw never paints one, the canvas never takes one for its live line. Only a pick by name or row (surface's `key`) or a new walk
  // clears it. It decides nothing about what comes NEXT - the server's capture does - and costs no round trip before paint.
  const leftRef = useRef(new Set()), leavingRef = useRef(null), pickedRef = useRef(false), bounced = useRef(false);
  const leftOf = (c) => { const k = c?.key || "", t = c?.tid || /^(?:task|agent):(\d+)$/.exec(k)?.[1];
    return [k && `k:${k}`, t && `t:${t}`].filter(Boolean); };
  const isLeft = (c) => !!c && leftOf(c).some((x) => leftRef.current.has(x));
  const leave = (c) => { for (const x of leftOf(c)) leftRef.current.add(x); };
  const unleave = (c) => { for (const x of leftOf(c)) leftRef.current.delete(x); };
  const putOnTable = useCallback((card, how = "pile") => {
    if (card && how !== "card" && isLeft(card)) return;          // pressed past or closed: never back unless its row is clicked (leftRef)
    if (how !== "sync") tableMoves.current += 1;
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
  const pendingPile = useRef(null), pileLoads = useRef(0);   // the rail still riding behind the card on the table (landed)
  const preparedRef = useRef(null);                         // the answer Next will give for the held selection (surface, drawAhead)

  // one turn of the assistant, streamed: tool calls show under the dots as they happen, `done` is the answer
  const turnOnce = useCallback(async (body) => {
    turnsBegun.current += 1;
    if (body.mode === "next") body = { ...body, fyi: fyiWant.current };
    setWork([]); setWords(""); setSteps([]);
    const stop = new AbortController(); stopRef.current = stop;
    const plain = async () => {
      const endpoint = body.mode === "open" ? "/api/concierge/open" : body.mode === "next" ? "/api/concierge/next" : "/api/concierge/say";
      return (await api.post(endpoint, body.mode === "next" ? { key: body.key, only: body.only, include_surfaced: body.include_surfaced, exclude: body.exclude,
        selection_revision: body.selection_revision, expected_next_key: body.expected_next_key, expected_next_members: body.expected_next_members, fyi: body.fyi, ...(body.blind ? { blind: true } : {}) }
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
    const answer = await readTurn(res.body, (ev) => {
      // the words as the model writes them (agents.spoken: never its CALL line) - drawn at once, replaced by the answer
      if (ev.type === "words") { setWords(String(ev.detail || "")); return; }
      // ...and the steps it takes looking into the app's own trouble (troubleshoot.py), drawn as the general agent's are
      if (ev.type === "steps") { setSteps(Array.isArray(ev.detail?.steps) ? ev.detail.steps : []); return; }
      if (ev.type === "error") {
        setWords("");
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
    });
    setWords(""); setSteps([]);
    if (answer) { setWork([]); return answer; }
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
  const readChatOnce = useCallback(async (epoch) => {
    const turns = turnsBegun.current, moves = tableMoves.current, mid = turnFlight.current;
    const { data: st } = await api.get("/api/concierge");
    if (epoch !== chatEpoch.current || resettingRef.current) return false;
    setMsgs((m) => mergeDurableTurns(m, st.messages || []).messages);
    // WHERE THE WALK IS, from the same answer: a hand-off started or ended somewhere else (a second tab, the phone's own
    // "stop") - kept as state only; it locks nothing here (2026-10-23)
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
    // ...NOR FROM A READ SENT WHILE A TURN WAS IN FLIGHT, OR BEFORE THE TABLE MOVED HERE (the owner, 0.3.9.21: "I clicked on task 1171 and
    // it jumped back to the deep dive one, then right back"). A rail click draws its task at once and its pull runs for seconds on a real
    // brain; a live event mid-pull read the conversation while the server still had the old task as Current, that answer came back after
    // the pull had landed, and it put the old task back up until the next read. The latest click wins: only a read sent after it may move it.
    // ...NOR OVER THE ITEM A CLOSE DREW AT ITS PRESS (drawNextEarly) while that close is on its way (2026-10-25): the close's own receipt
    // woke this read, the server still held the closed task as Current, and the table under the next task was cleared - a Next pressed on
    // it then left nothing, and the task kept no badge. That item is the table's until the close lands and the walk asks after it.
    if (!turnFlight.current && !cardRef.current && !mid && !earlyRef.current && moves === tableMoves.current) {
      const said = st.current || null;
      if (turns === turnsBegun.current && (said?.key || null) !== (currentRef.current?.key || null)) putOnTable(said, "sync");
    }
    return true;
  }, [putOnTable]);
  // ONE CONVERSATION READ AT A TIME (coalesce.js): every chat-changed event, the tick, an arrive and each pile read asked
  // again on its own, and behind a stalled server they stacked up (2026-10-23). A call while one runs shares the one re-read after it
  // - which captures the turn and the table as they stand when IT is sent, so the guards above hold as before.
  const readChatRef = useRef(readChatOnce); readChatRef.current = readChatOnce;
  const chatReads = useRef(null);
  chatReads.current ||= coalesce((epoch) => readChatRef.current(epoch));
  const readChat = useCallback((epoch = chatEpoch.current) => chatReads.current.run(epoch, epoch), []);
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
    const requestedCurrentKey = currentRef.current?.key || null, requestedMoves = tableMoves.current;
    const requestedScope = nextSelectionScope(only.current, requestedCurrentKey);
    pileLoads.current += 1;                    // a rail still riding behind a card is older than this read (landed)
    if (force) forcedLoadStartedAt.current = Date.now();
    const askedAt = Date.now();                // what this rail reflects is no older than this (taskDetail.notePile)
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
      selectionRef.current = captured; preparedRef.current = data.prepared_next || null;
      pileRef.current = refreshPilePresentation(pileRef.current, data); notePile(askedAt);
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
        // ...nor the same key put up again since (A, B, A): the table was moved here after this read was sent
        if ((cur?.key || null) !== requestedCurrentKey || requestedMoves !== tableMoves.current) return captured;
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
  const unconfirmedRef = useRef(null), adviceHeld = useRef(null);   // the key drawn ahead of its press's answer, until it lands (readAdvice)
  // NO "THINKING..." (the owner, 2026-10-23): the Advisor answers at once with the rule's lit button, and the model's read, where one
  // is wanted, arrives by the `advice` event - nothing is drawn while a read is out
  const readAdvice = useCallback(async (key, keep) => {
    const n = ++adviceAsk.current;
    if (!keep) setAdvice(null);                     // a new item starts with no line, never the last item's
    if (!key) return;
    // ...and not while the card is one drawn ahead of its press's answer (drawAhead): the Advisor reads the rail, and
    // a rail rebuilt under the press between its admission and its commit check refused the press as stale (PW-118). The
    // read is made once the answer has landed (landed), exactly as it was when the card only came with the answer.
    if (!keep) { setReading(key); setTimeout(() => setReading((r) => (r === key ? "" : r)), HOLD_MS); }
    if (unconfirmedRef.current === key) { adviceHeld.current = key; return; }
    let got = null;
    // ...and {"none":"no_ai"}: no AI connected is said once, with the way to connect one, instead of a strip that stays empty (U3)
    try { got = adviceRead((await api.get("/api/advice", { params: { key } })).data, key).advice; }
    catch { got = null; }
    if (n !== adviceAsk.current) return;
    setAdvice(got); setReadFor({ key });
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
  // LIT AND PRESSED (the deep dive, 2026-10-20): each press on the row says what was lit and the revision it was judged at
  // (advisor.press) - the evidence the owner's moves are learned from. EVERY press, lit or not (phase B, 2026-10-23: only a press
  // under a shown line was sent): what the row had filled and what else it offered (pressLog.deskPress). Nothing on screen changes.
  const shownRef = useRef(null), pickRef = useRef(null), activeRef = useRef(active);
  activeRef.current = active;
  const notePress = useCallback((id) => {
    if (!activeRef.current) return;                // a card pressed on the Tasks tab is that tab's to record (TaskPage)
    const a = shownRef.current, key = a?.key || onTableRef.current;
    notePressed(api, { key, surface: "desk", ...deskPress(rowNow(), pickRef.current, id), advised: a?.verb || null, revision: a?.revision || null });
  }, []);
  useEffect(() => onPressing(notePress), [notePress]);
  // ONE GESTURE, ONE ITEM (2026-10-25): a double-click on Mark done closed two tasks - the close drew the next task up at its press
  // (drawNextEarly) and the second click landed on that task's own Mark done. Every press on the canvas, the row under it and the menus
  // they open is held to the item it lands on (actionRow.aimed): the view under the pointer, else what is on the table. The second click
  // of a double-click, or a press within one press of the last, on another item does nothing at all. The rail is never held - a row
  // clicked is the owner naming the item. Captured on the window, so no card's own handler sees a press that is not one.
  useEffect(() => {
    const gate = (e) => {
      const b = e.target?.closest?.("button, [role=button], [role=menuitem]");
      if (!b || b.closest("[data-tq-rail]") || !b.closest(".tq-asst-col, [role=menu], .MuiPopover-paper")) return;
      const item = b.closest("[data-tq-canvas-item]")?.getAttribute("data-tq-canvas-item") || currentRef.current?.key || "";
      if (!aimed(item, e)) { e.stopPropagation(); e.preventDefault(); }
    };
    window.addEventListener("click", gate, true);
    return () => window.removeEventListener("click", gate, true);
  }, []);
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
  // SETUP IS NOT LOST (W2, the 2026-10-21 UI audit): a page or a task opened during setup is drawn OVER it - setup stays mounted, hidden,
  // on the step and the card it was on - and the rail's steps, the Setup chip and Chat take what is over it away. Before, a page opened
  // from the sidebar replaced setup, and only a reload brought it back; a task picked in Search or made on New never opened at all.
  const [overSetup, setOverSetup] = useState(false);                // a task or a message opened by name during setup
  const backToSetup = useCallback(() => { setOverSetup(false); browseDownRef.current?.(); }, []);
  useEffect(() => { if (!firstRun) setOverSetup(false); }, [firstRun]);
  useEffect(() => {
    if (!firstRun) return undefined;
    window.addEventListener("tq-setup-go", backToSetup); window.addEventListener("tq-setup-back", backToSetup);
    return () => { window.removeEventListener("tq-setup-go", backToSetup); window.removeEventListener("tq-setup-back", backToSetup); };
  }, [firstRun, backToSetup]);
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
    // the scrollbar: a press on the body itself, not on a line in it. A press ON a line is the owner working there, as a key is: a
    // Connections step header or switch snapped the card back to its top on every click, the thing pressed gone (the UI audit, 2026-10-21)
    const bar = (e) => { if (e.target === el) own(); else pin.current = false; };
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
  // THE DAY IS STILL BEING COUNTED - the first read, the launch's mail read ("Counting…" on the card), or rows still settling with
  // nothing the walk can pick yet. The opener said "Nothing to walk through" and greyed Walk under On you rows the card was still
  // counting (an owner screenshot, 2026-10-20): while it counts it says Loading..., and a Walk press is held until it lands (walkQueued)
  const onYou = useMemo(() => onYouCount(items.length ? summarize(items).groups : []), [items]);
  const counting = pileLoading || mailReading || (!canAdvance && items.some((i) => i.settling));
  const say = useCallback((line) => { if (speakOnState) speak(line); }, [speakOnState]);
  useEffect(() => { speakRef.current = say; }, [say]);
  // The rail came WITH an answer - a turn's or a settle's - read on the server after that write. The
  // page holds it and captures Next from it under the scope it will press with, instead of asking for
  // the same rows again: a press of Next was two of those reloads at 1.5-2 s each, and the visible
  // gap between the old rows vanishing and the next four appearing (design B, 2026-09-17).
  const holdPile = useCallback((data, scope) => {
    forcedLoadStartedAt.current = heldSince(data);     // the live events this read already saw need no reload
    notePile(forcedLoadStartedAt.current);              // ...and a task read older than it no longer speaks over its rows
    if (hasNextSelection(data)) selectionContractSeen.current = true;
    selectionRef.current = captureNextSelection(data, scope);
    preparedRef.current = data.prepared_next || null;
    setPile((p) => refreshPilePresentation(p, data));
  }, []);
  // ONE ROAD AHEAD OF THE ANSWER (G8 swap-never-clear + the prepared Next, 2026-10-20): a press draws its next line at once and the
  // press's own answer fills that SAME line in place - its id kept, so the view in it stays mounted - or takes it down when it brought
  // something else; a refusal or a failure takes it down and puts back what was on the table. What is drawn: the server's PREPARED
  // answer (prepared_next, its words and chips) when it was worked out for exactly this selection, else the rail's own row for the
  // item the capture names (surface) - or the one a close names, drawn at the close's press (drawNextEarly). The line is `ahead` until
  // its answer lands: no copy of the item yet (itemKey), so the older line of that item stays where it stood until the answer is
  // placed - and goes back to being the item's line if this one comes down.
  const aheadRef = useRef(null);      // { id, key, hash, say, table } of the line drawn before its answer (drawAhead, landed, unshow)
  // the next item a close drew at its press, before the server recorded the close (drawNextEarly) - handed to the walk's next
  // surface by advance (carryRef), or taken down with the closed item put back when the close fails (canvas pickUp)
  const earlyRef = useRef(null), carryRef = useRef(null), adoptRef = useRef(null);
  const movedOnRef = useRef(false);   // that early draw was taken over by another walk move before its close landed (adopt, advance)
  const tableNow = () => ({ item: currentRef.current, cardKey: cardRef.current, openCard: openCardRef.current, pin: pin.current });
  const drawAhead = useCallback((line, hash = null) => {
    if (isLeft(line.card)) return null;                           // the early draw paints FROM the one rule, never past it (leftRef)
    const rec = { id: line.id, key: line.card?.key || null, hash, say: line.text, table: tableNow() };
    // ...and the Advisor is not asked about it until the answer lands (readAdvice): the Advisor reads the rail, and a rail rebuilt under
    // the press between its admission and its commit check refused the press as stale (PW-118, 2026-10-20)
    unconfirmedRef.current = rec.key; adviceHeld.current = null;
    setMsgs((m) => [...m, { ...line, ahead: true }]);
    putOnTable(line.card);
    if (line.text) say(line.text);
    return rec;
  }, [putOnTable, say]);   // eslint-disable-line react-hooks/exhaustive-deps
  const unshow = useCallback((rec) => {
    unconfirmedRef.current = null; adviceHeld.current = null;
    if (!rec) return;
    setMsgs((m) => m.filter((x) => x.id !== rec.id));
    const t = rec.table;
    if (t.cardKey) putOnTable({ key: t.cardKey }, "card"); else putOnTable(t.item, "sync");
    openCardRef.current = t.openCard; pin.current = t.pin;
  }, [putOnTable]);
  const landed = useCallback((data) => {
    // THE SERVER ANSWERED WITH AN ITEM THIS WALK ALREADY LEFT (leftRef): a report put on the list comes back as its task, a closed row
    // re-offered from the walk's place. It is not painted - it is put down as Next would, and the walk asks once more
    if (!pickedRef.current && data.item && isLeft(data.item)) {
      const ahead = aheadRef.current; aheadRef.current = null; unshow(ahead);
      if (!bounced.current) {
        bounced.current = true;
        api.post("/api/funnel/settle", { key: data.item.key, verb: "surfaced", read: true, put_down: true })
          .catch(() => {}).then(() => loadPileRef.current?.(true)).then(() => deferInChat(() => surfaceRef.current?.(), 0));
      }
      return;
    }
    bounced.current = false;
    if (pickedRef.current && data.item) unleave(data.item);   // picked by name or row: whatever key it comes back under is the owner's again
    if (data.exhausted && !only.current?.startsWith("view:")) only.current = null;            // the mail ran out: Next continues with the rest of the pipe
    // a task opened to start its agent or an act (the Board's, a workflow's) carries that start onto the row the server answered with
    const extra = openExtra.current; openExtra.current = null;
    const card = data.item ? { ...data.item, ...(extra && extra.tid === data.item.tid ? { autostart: extra.autostart, act: extra.act } : {}) } : null;
    // the end of the walk's "Open TQ-12" words come as `chips`: dropped here, its only button was a Next that said it again
    // ONE COPY PER ITEM (2026-10-19 UI walk): an item opened again - from search, the Board, the rail - moves its line to the end, never a second
    // ...and the line drawn ahead of this answer (drawAhead) IS this line when it named the same item - its id kept, so the view in it
    // stays mounted, its card drawn now if it was held (Line) - and comes down when the answer brought something else. The prepared
    // answer it drew, confirmed by answer_hash, is not drawn twice: nothing is put on the table or said again.
    const ahead = aheadRef.current; aheadRef.current = null;
    const heldAdvice = ahead ? adviceHeld.current : null;
    unconfirmedRef.current = null; adviceHeld.current = null;
    const same = !!ahead?.hash && ahead.hash === data.answer_hash && !extra, keep = !!ahead && card?.key === ahead.key;
    const id = keep ? ahead.id : `a${Date.now()}`;
    setMsgs((m) => placeLine(ahead ? m.filter((x) => x.id !== ahead.id) : m, { id, role: "assistant", text: data.say, options: data.options || [], chips: data.chips || [], card }));
    if (!same) putOnTable(card);
    if (!ahead || ahead.say !== data.say) say(data.say);
    if (heldAdvice) readAdvice(card?.key || heldAdvice);     // the Advisor's read the line drawn ahead held back (readAdvice)
    // the turn brought the rail as it left it: hold that, with the new table excluded. Nothing along
    // (the walk ran out, an older server, the demo) is the page's own load, as before.
    if (card && data.pile) holdPile(data.pile, nextSelectionScope(only.current, card.key));
    else if (card && data.pileLater) {
      // THE RAIL FOLLOWS THE CARD (2026-10-20): the card is drawn now and the rail it came from stays up - highlight and
      // counts included - until the turn's own rail lands on the same stream. A rail read begun since is newer and wins.
      const scope = nextSelectionScope(only.current, card.key), epoch = chatEpoch.current, loads = pileLoads.current;
      const later = pendingPile.current = data.pileLater.then((fresh) => {
        if (pendingPile.current === later) pendingPile.current = null;
        if (epoch !== chatEpoch.current || resettingRef.current || loads !== pileLoads.current) return;
        if (fresh) holdPile(fresh, scope);
        else { selectionRef.current = null; setPile(withdrawSelection); loadPile(true); }
      });
    }
    // ...no rail rides along: the ring the rail holds was captured for the old table, and comes down until the reload lands
    else { selectionRef.current = null; if (card) setPile(withdrawSelection); loadPile(true); }
  }, [holdPile, loadPile, putOnTable, readAdvice, say]);

  const ensureNextSelection = useCallback(async (scope) => {
    if (pendingPile.current) await pendingPile.current;        // the rail riding behind the last card carries the next token
    for (let attempt = 0; attempt < 3; attempt += 1) {
      const captured = selectionRef.current;
      if (captured && sameSelectionScope(captured.scope, scope)) return captured;
      // ...and a read already on its way is waited out, never taken as this scope's: it was asked for the table as it stood when it
      // was sent, and one for another table is dropped when it lands (loadPile) - joined, it spent a try and brought nothing. The read
      // that follows it is this scope's own
      if (pileFlight.current) await pileFlight.current;
      else await loadPileRef.current?.(true);
    }
    const captured = selectionRef.current;
    return captured && sameSelectionScope(captured.scope, scope) ? captured : null;
  }, []);

  // a line of the assistant's own that needs no turn - a section walk running out
  const noteLine = useCallback((text) => setMsgs((m) => [...m, { id: `s${Date.now()}`, role: "assistant", text }]), []);
  // pull the next thing (or the one named; or the next piece of mail) out of the pipe and say it
  // `blind`: pressed with no item in front of the owner (the walk's start, a chat chip on an empty table) - see the retry below
  const surface = useCallback(async (key = null, asUser = null, leaving = null, blind = false) => {
    // the next item a close already drew at its press (drawNextEarly), handed on by advance: this answer fills it or takes it down
    const carried = carryRef.current; carryRef.current = null;
    if (!carried && earlyRef.current) adoptRef.current?.();   // any other walk move makes a close's early draw the table's own
    const dropCarried = () => { if (carried) { unconfirmedRef.current = null; adviceHeld.current = null;
      setMsgs((m) => m.filter((x) => x.id !== carried.id)); if (!currentRef.current) putOnTable(null, "sync"); } };
    if (busy || resetting || turnFlight.current) { dropCarried(); return; }
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
    setBusy(true); setErr(""); setFlight({ pick: !!key, from: key && key === currentRef.current?.key ? null : currentRef.current?.key || null });
    if (key) unleave({ key });                                    // a row clicked, a name, a link: the owner asked for it back
    pickedRef.current = !!key;
    if (!key) navHow.current = "replace";            // the walk's Next is a stream, not a stack: the address follows, Back does not
    const epoch = chatEpoch.current;
    // NEXT IS "SHOW ME THE NEXT THING" (the owner, 2026-10-26: "i hate the next list changed. No one cares. Think about it from user
    // perspective"): a list moving under the press is the app's to absorb, never a line asking for another press. The rail read a press
    // waits on can itself move the table - the server says its item is gone and the table clears, the same task comes back under a new
    // key - so the press captures again for the table as it now stands, three rounds at most, and still moving after that it goes with
    // no capture: the server takes its own pick for that table (no stale check) and the ring follows what came up. Nothing is skipped
    // by it: a row the ring showed and the owner never saw stays unread on the rail and comes up later.
    let scope, capture;
    for (let round = 0; round < 3; round += 1) {
      scope = nextSelectionScope(key ? null : only.current, key ? null : currentRef.current?.key || null);
      capture = key ? null : await ensureNextSelection(scope);
      // a new chat or a reset is the owner's own doing and stays quiet. 2026-09-09: a press that returned here with no word looked
      // alive and reached nothing for half an hour - which is why the only quiet return left is the owner's own
      if (epoch !== chatEpoch.current || resettingRef.current) { turnFlight.current = false; setBusy(false); setFlight(null); dropCarried(); return; }
      const activeScope = nextSelectionScope(key ? null : only.current, key ? null : currentRef.current?.key || null);
      const scopeMoved = !key && !sameSelectionScope(scope, activeScope);
      if (!scopeMoved) break;
      scope = activeScope; capture = null;
    }
    const optimisticId = asUser ? `u${Date.now()}` : null;
    if (optimisticId) setMsgs((m) => pickLine(m, { id: optimisticId, role: "user", text: asUser, pick: key || undefined }));
    // NEXT PUTS THE TABLE DOWN AT ONCE, the way "All read, next" does (the owner, 2026-09-30: "when you hit next on a task it
    // does not close the current task instantly ... the close of past one should be instant"): the task folds to its title
    // line now and the "…" shows while the next one loads; a Next that fails opens it again
    const putDown = !key && currentRef.current?.key ? currentRef.current.key : null;
    const leftItem = putDown ? currentRef.current : null;
    if (putDown) { setExpanded(false); setFoldedKey(putDown); leave(leftItem); }
    // ...AND IT WEARS "Next" like any press (the owner, 2026-10-23: "we should have next pill on this one to show what was clicked on
    // each task") - only a card nothing else was pressed on; a Next that fails takes the badge off with the fold
    // ...saying what Next did (the owner, 2026-10-23: "should show read on reports if you go pass them when you hit next"): "Read" on a
    // report, a dashboard or an fyi Next settles read, "Next" on a task it only passes (nextBadge)
    const wear = (on) => setMsgs((m) => { let i = -1;
      for (let j = m.length - 1; j >= 0; j -= 1) if (m[j]?.card?.key === putDown) { i = j; break; }
      const word = i < 0 ? "" : nextBadge(m[i].card);
      if (i < 0 || (on ? pressedOf(m[i]) : m[i].pressed !== word)) return m;
      return m.map((x, j) => (j !== i ? x : on ? { ...x, pressed: word } : (({ pressed, ...rest }) => rest)(x))); });
    if (putDown) wear(true);
    // ...AND THE NEXT ONE IS PUT UP IN THE SAME FRAME (G8, swap never clear): between the fold and the server's answer the canvas held
    // no view at all and the rail still rang the item just put down - 10-25 frames on every Next. The capture already names what this
    // Next brings (the server refuses any other - PW-050), so it is drawn now (drawAhead) and the answer fills the same line in place
    // (landed). A refusal or a failure takes it down again and puts the table back on the item it left (the catch below).
    // FIRST the server's own answer, PREPARED for exactly this selection (prepared_next, tied to its selection_revision): its words,
    // chips and card, as the answer would draw them; the press still commits and its answer_hash confirms it.
    const prep = !key && capture && !openExtra.current && preparedRef.current?.selection_revision === capture.selection_revision ? preparedRef.current : null;
    preparedRef.current = null;
    const was = currentRef.current, rows = pileRef.current?.items || [];
    // ...ELSE the rail's row for it: a rail row pulled by name (the server answers with the row that was pressed), or the single item
    // the capture names - after a close that already put the table down too (Mark done, Remove, Remind me: advance), and at the walk's start
    const aheadKey = prep ? null : key || (capture?.expected_next_key && (capture.expected_next_members || []).length <= 1 ? capture.expected_next_key : null);
    // ...an item an agent is working included: it is a task like the rest, and its card is the agent's pane (the owner, 2026-10-21)
    const aheadItem = aheadKey && aheadKey !== was?.key ? rows.find((i) => i.key === aheadKey && !i.settling) : null;
    const line = { id: `a${Date.now()}`, role: "assistant", options: [], chips: [] };
    // ...its CARD drawn at the answer, the words at once (`held`, Line): a card's first reads write - a task's origin is filed on its
    // first detail read - and a write under the press between its admission and its commit check refused it as stale (PW-118). A task
    // whose read is held already had that first read (taskDetail.js prefetchTask): its view draws at once, as the rail's row does.
    const drawsNow = (c) => !!c && showsTask(c, cardFor(c)) && !!heldTask(c.tid) && heldTerm(c.tid) !== undefined;
    // ...ELSE a Next's only when its task is read already (and whether an agent holds it, which half its row turns on): an empty view put up
    // ahead of its own read is the shell this is here to end. A ROW CLICKED COLD is drawn at the click all the same (owner-approved,
    // 2026-10-20): the old view stayed up under the click for the whole read and the ring sat on it, so the click looked unheard - now
    // the new item's frame comes up with its title over the view's own loading state, the ring moves with it, and the answer fills it.
    // (A pick by name carries no selection to refuse as stale, so its view's first read is no PW-118 write.)
    // ...and the line a close drew at its press is THIS line when the server's capture names it too - the empty table the close left is
    // what a failure goes back to - and comes down otherwise
    const keeps = !!carried && carried.key === (prep ? prep.answer.item?.key : aheadItem?.key);
    // (no hash: the close emptied the table under it, so the answer puts its item on the table again, as it always did)
    if (keeps) aheadRef.current = { ...carried, hash: null, table: tableNow() };
    else dropCarried();
    if (keeps) unconfirmedRef.current = carried.key;   // drawn already; its Advisor read still waits on this answer
    else if (prep) aheadRef.current = drawAhead({ ...line, text: prep.answer.say, options: prep.answer.options || [], chips: prep.answer.chips || [],
                                                 card: prep.answer.item || null, ...(drawsNow(prep.answer.item) ? {} : { held: true }) }, prep.answer_hash);
    else if (aheadItem && (drawsNow(aheadItem) || (key && showsTask(aheadItem, cardFor(aheadItem)))))
      aheadRef.current = drawAhead({ ...line, text: "", card: aheadItem });
    try {
      // A named Timeline/pile row remains an explicit pull. Automatic Walk/Next echoes the exact
      // server capture; with none to be had (above), the server's own pick for this scope.
      let navigation = capture ? nextSelectionBody(capture) : { ...scope };
      // ...and a press made with nothing on the table says so: the server then takes a pick that moved fresh rather than refusing
      // it - the walk's first press, made while the opener still reads what came in (the owner, 2026-10-20)
      if (blind && capture) navigation.blind = true;
      let data;
      for (let tries = 0; ; tries += 1) {
        try { data = await turn({ mode: "next", key, leaving, ...navigation }); break; }
        catch (e) {
          // THE SERVER'S "THE LIST CHANGED" IS TAKEN, NEVER SAID (the owner, 2026-10-26: "i hate the next list changed. No one cares"):
          // a plain stale refusal ran nothing, so the press goes again at once with the server's fresh pick, and refused once more, with
          // its own pick (no capture). One press is still one move: a navigation in progress, done already or uncertain is not retried
          const g = !key && selectionGuardDetail(e), real = !g || g.code !== "selection_stale" || g.retryable === false
            || ["navigation_in_progress", "already_completed", "outcome_uncertain"].includes(g.reason);
          if (real || tries >= 2 || epoch !== chatEpoch.current) throw e;
          const fresh = tries === 0 ? captureNextSelection(g, scope) : null;
          selectionRef.current = fresh;
          setPile((p) => replaceSelectionToken(p, g));
          navigation = fresh ? { ...nextSelectionBody(fresh), ...(blind ? { blind: true } : {}) } : { ...scope };
        }
      }
      landed(data);
    } catch (e) {
      unshow(aheadRef.current); aheadRef.current = null;   // what was put up ahead of the answer comes down, the table back on the item it left
      const guard = selectionGuardDetail(e);
      if (guard) {
        if (optimisticId) setMsgs((m) => m.filter((message) => message.id !== optimisticId));
        const freshCapture = captureNextSelection(guard, scope);
        selectionContractSeen.current = true;
        selectionRef.current = freshCapture;
        setPile((p) => replaceSelectionToken(p, guard));
        loadPile(true);                       // refresh the rows: the retries above are spent, or this was no list change
      }
      if (putDown) { setFoldedKey((k) => (k === putDown ? null : k)); wear(false); }
      if (leftItem) { unleave(leftItem); putOnTable(leftItem, "sync"); }   // the Next did not happen: the item it left is the table's again
      setErr(errText(e));
    }
    turnFlight.current = false;
    setBusy(false); setFlight(null);
  }, [busy, drawAhead, ensureNextSelection, landed, loadPile, noteLine, putOnTable, resetting, turn, unshow]);
  useEffect(() => { surfaceRef.current = surface; }, [surface]);
  // A CLOSE PUTS THE NEXT ONE UP AT ITS PRESS (owner-approved, 2026-10-20): Mark done, Remove and Remind me fold the item at once, and
  // the next was drawn only once the server had recorded the close and the walk asked for it - ~200 ms of a folded line and no view.
  // The capture held for the table names what the walk brings after it, so that item is drawn now, the way a Next draws it (only
  // from a held read; never in a section walk, which picks its own next); a close that fails takes it down again (canvas pickUp)
  const drawNextEarly = (leaving) => {
    if (earlyRef.current || sectionRef.current || turnFlight.current) return;
    movedOnRef.current = false;
    const cap = selectionRef.current, nk = cap?.expected_next_key;
    if (!nk || nk === leaving || (cap.expected_next_members || []).length > 1) return;
    const it = (pileRef.current?.items || []).find((i) => i.key === nk && !i.settling);
    if (!it || !showsTask(it, cardFor(it)) || !heldTask(it.tid) || heldTerm(it.tid) === undefined) return;
    earlyRef.current = drawAhead({ id: `a${Date.now()}`, role: "assistant", text: "", options: [], chips: [], card: it });
  };
  const drawNextEarlyRef = useRef(null); drawNextEarlyRef.current = drawNextEarly;
  // ...and the close failed: the drawn item comes down and the closed one is back on the table (its fold undone by pickUp)
  const takeEarlyBack = () => { const e = earlyRef.current; earlyRef.current = null; movedOnRef.current = false; if (e) unshow(e); };
  // ...and a walk move other than the close's own makes it the table's own: an item line like any other, its Advisor read made now
  const adopt = () => {
    const e = earlyRef.current; earlyRef.current = null;
    if (!e) return;
    movedOnRef.current = true;
    const held = unconfirmedRef.current === e.key && adviceHeld.current;
    unconfirmedRef.current = null; adviceHeld.current = null;
    setMsgs((m) => { const x = m.find((y) => y.id === e.id); return x ? placeLine(m.filter((y) => y !== x), { ...x, ahead: false }) : m; });
    if (held) readAdvice(e.key);
  };
  adoptRef.current = adopt;
  const takeEarlyBackRef = useRef(null); takeEarlyBackRef.current = takeEarlyBack;
  const startFlight = useRef(false);
  const startLast = useRef(null);   // the newest line when Walk was pressed: the "…" stands until a line lands after it
  // ONE ANSWER TO "CAN THE WALK START?" (the 2026-10-19 UI walk): the button greyed on one list and the press returned on another, so a
  // press could look taken and do nothing. Both read walkOff; the refs only close same-tick double presses the state has not caught.
  const walkOff = busy || resetting || starting;
  const start = async (what) => {
    // A WALK PRESSED WHILE THE WALK IS BUSY IS HELD (owner-approved, 2026-10-20), as the opener's early press is (74861f7d): a turn
    // or a Next in flight dropped it and the button looked taken. Its button says "Getting your first one..." until it runs.
    if (walkOff || turnFlight.current || startFlight.current) { if (!starting && !startFlight.current) setWalkQueued(true); return; }
    startFlight.current = true;
    leftRef.current.clear(); bounced.current = false;            // a new walk shows every open task again (next-is-seen-in-this-walk)
    const epoch = chatEpoch.current;
    // A PRESS IS NOT A TYPED LINE (the owner, 2026-10-23: "it just hung there and we don't need the words"): no "Walk me through my
    // tasks." bubble - only the "…" (tq-pending) from the press until the first item lands, whatever the server takes
    startLast.current = msgs.length ? msgs[msgs.length - 1].id : null;
    setStarting(true); setErr("");
    try {
      only.current = sharedFilter.current && sharedFilter.current !== "{}" ? `view:${sharedFilter.current}` : (pile?.canonical ? null : what);
      selectionRef.current = null;
      await loadPile(true);                   // validate/resume Current under the requested scope
      if (epoch !== chatEpoch.current || resettingRef.current) return;
      // resume what is on the table only if you have not PASSED it: a passed item waits in Passed for
      // its hour, and starting the walk put it straight back in front of you (the owner, 2026-09-23:
      // "it's in the passed section but showing up on assistant first")
      if (!currentRef.current || currentRef.current.surfaced) await surface(null, null, null, true);
    } catch (e) {
      // the "…" went with the press, so a failure has to be answered on screen - and the welcome block (drawn on an empty chat,
      // hidden while starting) returns with its button: the only way to try again
      setErr(`The walk didn't start - ${errText(e)}. Press Walk me through my tasks to try again.`);
    } finally {
      startFlight.current = false;
      setStarting(false);
    }
  };
  // the Walk press kept while the pile loaded: run once the rows are in - and only if there is a walk to start, which is
  // exactly when the button would have been pressable had the rows been there
  // ...and kept while anything else holds the walk (walkOff): run then, never dropped by start()'s own refusal
  // ...and kept while the day is still counted: run the moment the walk can pick one, or once the count lands - then only if there
  // is something on you to walk (the button's own rule), never a press dropped because the rows were still settling
  useEffect(() => {
    if (!walkQueued || walkOff || turnFlight.current || (counting && !canAdvance) || pileLoading) return;
    setWalkQueued(false);
    if (canAdvance || onYou) start(null);
  }, [walkQueued, pileLoading, counting, canAdvance, onYou, walkOff]);   // eslint-disable-line react-hooks/exhaustive-deps

  // The day used to write itself the moment the page opened - a model call nobody asked for, which
  // also landed UNDER a "Set something up" the owner had already pressed (2026-09-03: "I hit new chat
  // to set something up and it ran the email walk through welcome command?"). The welcome block is the
  // door now: what is waiting, in facts, and the walk starts on a button.

  // A LINE TYPED WHILE A TASK COMES UP IS HELD, NEVER DROPPED (the owner, 2026-10-26: asked while a task was loading on the canvas,
  // "it ignored it"): opening a row holds `busy` for its whole read - 9-10 s on a live day - and Enter returned below with no line
  // and no word, the words left sitting in the box. The line is drawn at once and goes when the table is free (the effect beside
  // openLater), about what is then on it - the task that was coming up. A picture still waits in its tray, the words with it.
  const askLater = useRef([]), sending = useRef(null);
  const send = async (line, held = false) => {
    // a picture alone is a line too: "what is this?" is what it means
    const images = line == null ? pics.paths : [];
    const t = String(line ?? text).trim() || (images.length ? "What is this?" : "");
    if (!t || pics.busy) return;
    if (busy || resetting || turnFlight.current) {
      // ...but never a second copy: Enter twice in one tick reaches here with the line already going (`sending`)
      if (resetting || images.length || t === sending.current || askLater.current.includes(t)) return;
      askLater.current = [...askLater.current, t];
      if (line == null) setText("");
      setMsgs((m) => [...m, { id: `u${Date.now()}`, role: "user", text: t, shots: [], heldAsk: true }]);
      return;
    }
    turnFlight.current = answering.current = true; sending.current = t;
    setText(""); setBusy(true); setErr(""); setLit(null);
    if (popOnRef.current) setPopOpen(true);            // the answer comes up over the task (the one-row chat bar)
    const shots = line == null ? pics.imgs : [];
    if (images.length) pics.clear();
    // ...a held line is on screen already: it is let go, not drawn twice
    setMsgs((m) => { const i = held ? m.findIndex((x) => x.heldAsk && x.text === t) : -1;
      return i >= 0 ? m.map((x, j) => (j === i ? { ...x, heldAsk: false } : x)) : [...m, { id: `u${Date.now()}`, role: "user", text: t, shots }]; });
    try {
      // a card browsed open is what "this" means - not the item folded above it (the final review)
      // ...and otherwise WHAT IS OPEN ON THE TABLE, whatever put it there (the owner, 2026-10-01: "the assistant has the open box in
      // context always regardless of what it is"): a task opened by name or from the rail never became the walk's `current`, so a
      // question about it went out about the walk's old item, or about nothing. The newest live card that is not folded leads.
      const table = msgs[tableCardIndex(msgs, current || cardRef.current)]?.card;
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
        const aid = `a${Date.now()}`;
        // ...and a lit button or a press is no line at all (the owner, 2026-10-23: "what the heck is Lit"): only words get one
        if (data.say || data.options?.length || data.chips?.length)
          setMsgs((m) => [...m, { id: aid, role: "assistant", text: data.say, options: data.options || [], chips: data.chips || [], steps: data.steps || [] }]);
        // A TYPED PUT-DOWN WAS PRESSED (concierge._put_down - the owner, 2026-10-23: "it should collapse the task and write on it marked done
        // with note"): its card wears the button's badge, and on the table it is put down as the row's own press puts it down - folded, the
        // next item up - never a line saying so
        const pr = data.pressed;
        if (pr?.label) {
          setMsgs((m) => pressLine(m, pr, pr.label, pr.note || ""));
          const here = { key: tableKey || current, tid: currentItem?.tid };
          if (litOn({ key: pr.key, tid: pr.tid ? Number(pr.tid) : null }, here) || pr.table) {
            // ...folded as done() folds the card a press lands on
            setMsgs((m) => { const i = interactiveCardIndex(m); return i < 0 ? m : m.map((x, j) => (j === i ? { ...x, done: true } : x)); });
            canvasState.putDown(here.key || pr.key, pr.tid ?? null); advance(null, true);
          } else { onChanged?.(); loadPile(); }
        }
        // a connector card brought up lights its first step - the line is finished with what it lit ("press Sign in with LinkedIn")
        if (String(data.say || "").includes(STEP_SAID)) {
          const done = (e) => { window.removeEventListener(LIT, done); setMsgs((m) => m.map((x) => (x.text === data.say ? { ...x, text: finishLine(x.text, e.detail) } : x))); };
          window.addEventListener(LIT, done); setTimeout(() => window.removeEventListener(LIT, done), 8000);
        }
        if (data.say) say(data.say);
        // THE PAGE IT NAMED, OPENED (appLinks.js): "set up Intacct" puts the Sage Intacct card beside the answer, not a sentence
        // about where to find it. Only a fresh reply opens one - a reloaded history draws its links, it does not open them.
        // ...a reply that carries `open` has decided for itself: "" is the app's own words (no AI), whose links are to press
        const page = "open" in data ? data.open : firstAppLink(data.say);
        if (page) openAppLink(page);
        // ...its line rides with it (`aid`): the card's Send to agent says it again as what it started (concierge.said_started)
        if (data.new) browseRef.current?.("new", { ...data.new, aid });
        const l = lightOf(data.light);
        if (l) {
          setLit(l);
          continueNote.current = data.light?.note ? { tid: data.light.tid, note: String(data.light.note) } : null;
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
    turnFlight.current = answering.current = false; sending.current = null;
    setBusy(false);
  };
  // ...and a line the bell hands over (askAssistant.js), sent as if typed - or left in the box while a turn is running, never dropped
  const askRef = useRef(null);
  askRef.current = (t) => (busy || resetting || turnFlight.current ? setText(t) : send(t));
  useEffect(() => {
    const on = () => { const t = takeAsk(); if (t) askRef.current(t); };
    on(); window.addEventListener("tq-ask", on);
    return () => window.removeEventListener("tq-ask", on);
  }, []);
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
          setLit({ verb: "approve", label: btn("approve"), line: "", key: `review:${data.reviewId}`,
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
        // ...and a rewrite that did not happen is drawn as the failure it is (✗) - a receipt with no status wore the tick (2026-10-26)
        setMsgs((m) => [...m, { id: `r${Date.now()}`, role: "receipt", ...there, ...(data.draft ? {} : { status: "failed" }), text: data.draft
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
        : step === "offer" || out.status !== "done" ? [{ verb: "next", label: btn("next") }] : followUps(p, out);
      // A PRESS THAT WENT THROUGH IS A BADGE ON ITS CARD, never "Done - Mark done · TQ-0001." under it (the owner, 2026-10-22: "we don't
      // need that text ever"). A line stays only where it carries a way on (a send's Mark done and Next, Not ours taken further, a
      // sweep's Next) - and a press that did NOT go through is said, as a failure
      // ...and one with no card here to wear it (a report set up from words) keeps its line, as the server does (concierge.receipt_turn)
      const quiet = out.status === "done" && !chips.length;
      setMsgs((m) => {
        const ms = m.map((x) => (holdsProposal(x, p) ? { ...x, proposal: { ...x.proposal, ...(p.replaces ? p : {}), status: out.status, repo: out.repo || null, outcome: res?.outcome || null } } : x));
        // ...and one that went through wears its badge even where its line stays for the way on: Not ours folded with no mark (the 2026-10-25 sweep)
        const worn = out.status === "done" ? pressLine(ms, { key: p.key, tid: p.tid || res?.outcome?.taskId }, String(p.label || p.title || "").split(": ")[0]) : ms;
        return quiet && worn !== ms ? worn
          : [...worn, { id: `r${Date.now()}`, role: "receipt", status: out.status, text: out.receipt, tid: p.tid || res?.outcome?.taskId, ref: p.ref || res?.outcome?.ref, chips }];
      });
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
  // a card button on ONE entry (PW-151): the same proposal road the words take, minus the interpreter - the target is explicit
  // ...AND THE PRESS IS THE DECISION (`press`, the 2026-10-25 sweep): it runs here at once, whatever the verb - "Chase them" and "Put it
  // on my list" drew "Nothing happens until you say yes" with the button already pressed, and the server wrote the press into the chat
  // as an owner line ("Not ours: FW: ...") with a second card that folded the item after it (assistant-is-a-router: no confirm cards)
  const proposeDirect = async (verb, key, table = false, revision = null) => {
    // the pill carries the stamp it was judged at, and a moved item refuses it (409); the plain road is unchanged
    const { data } = revision ? await api.post("/api/concierge/propose", { verb, key, table, revision, press: true })
      : await api.post("/api/concierge/propose", { verb, key, table, press: true });
    // refused before any proposal existed: the reason and this item's other words, as a line of its own (no card to confirm)
    if (!data.id) {
      setMsgs((m) => [...m, { id: `a${Date.now()}`, role: "assistant", text: data.say, options: [], card: { kind: "words", chips: data.chips || [] } }]);
      return data;
    }
    // a move the server runs AT ONCE (concierge.AUTO: Not ours, Mark done, Stop) draws no card: its caller runs it on the spot, and the
    // card it drew stood with Cancel and its own From now on until the run came back (remove-undo.test's race, 2026-10-23)
    if (data.auto) { await runProposal(data); return { ...data, ran: true }; }
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
    // ...and an agent start asks what first, as its button does: the box opens, the Advisor's pick never starts one by itself
    if (AGENT_VERBS.includes(liveVerb(a.verb))) { askAgent(currentRef.current, liveVerb(a.verb)); return null; }
    // ...and a move the server runs AT ONCE from the row (concierge.AUTO: Not ours files just this once, its From now on under the
    // receipt) runs at once from here too: the Advisor's copy of Not ours drew a proposal card with Cancel the row's own never does
    // (remove-undo.test, 2026-10-23) - one press, one behaviour, whichever button it was
    try { return await proposeDirect(a.verb, key, true, a.revision); }
    catch (e) {
      if (demoNo(e)) { setErr(errText(e)); return null; }          // the demo saying no is a line in the chat, not the row's error
      if (e?.response?.status !== 409) throw e;
      setChanged({ for: key, reading: true }); await readAdvice(key); setChanged({ for: key });
      return null;
    }
  };
  // THE AGENT BOX FOR AN ITEM: a task on the table opens its own (TaskPage hears tq-agent-ask - the box in its agent step); an email,
  // an fyi or a report run with no task page gets the same box under its card here
  const askAgent = (item, verb) => {
    const coding = verb === "coding_agent" || verb === "coder" || (verb !== "regular_agent" && !!item?.coding);
    if (item?.tid && showsTask(item, cardFor(item))) { window.dispatchEvent(new CustomEvent("tq-agent-ask", { detail: { tid: item.tid, coding } })); return; }
    if (!item?.key) return;
    setContinueOn(null); setNoteOn(null);
    setAgentOn({ item, coding });
  };
  // ...and its Start: the hand-off's own proposal, carrying what was said and the agent chosen (concierge.propose_direct), run at
  // once - the box was the confirmation. The walk then does what a hand-off always did: the task opens, working (runProposal)
  const startOnItem = async (item, o) => {
    const { data } = await api.post("/api/concierge/propose", { verb: o.verb, key: item.key, table: true, exact: true, text: o.text || null,
      agent: o.agent || null, brain: o.brain || null, pick: o.pick || null, model: o.model || null, press: true });
    if (!data?.id) throw new Error(data?.say || "It did not start.");
    setAgentOn(null);
    await runProposal({ ...data, key: data.key || item.key });
  };
  // ANSWER IT has nothing to send until the owner says it: pressed bare it was refused ("What should I tell...?"). The box is where
  // the answer goes - the server passes what is typed over a waiting agent to it
  const askAnswer = (item) => {
    noteLine(`Type your answer below - it goes straight to ${item?.agent || "the agent"} that is waiting.`);
    setTimeout(() => composeRef.current?.focus(), 0);
  };
  // THE CALENDAR'S ANSWERS (calwrite.py): Accept and Decline draft at once; Propose a new time and Find a time open the free times
  // first (SlotPicker). Each lands on the table as a draft with Send lit, as a reply does - nothing reaches the calendar before the
  // owner's Send. A card that may not write says so in one line, with its sign-in as the way out (failures.py's fix).
  const calendarDrafted = (data, item) => {
    if (!data?.ok) {
      setMsgs((m) => [...m, { id: `r${Date.now()}`, role: "receipt", status: "error", text: data?.say || "That could not be drafted.", tid: item?.tid, ref: item?.ref,
        chips: [...(data?.fix?.href ? [{ verb: "go", href: data.fix.href, label: data.fix.label }] : []), { verb: "next", label: btn("next") }] }]);
      return;
    }
    setLit({ verb: "approve", label: btn("approve"), line: "", key: `review:${data.reviewId}`,
             tid: item?.tid ? Number(item.tid) : null, landed: false });
    putOnTable(null, "sync"); deferInChat(() => surfaceRef.current?.(`review:${data.reviewId}`), 300);
  };
  const calendarAnswer = async (item, act, slot = null) => {
    setBusy(true); setErr("");
    try { calendarDrafted((await api.post(`/api/messages/${item.mid}/calendar`, { act, ...(slot || {}) })).data, item); }
    catch (e) { setErr(errText(e)); } finally { setBusy(false); }
  };
  // ONE road for every action word in the chat. A word the assistant offered is a word that runs: the
  // verb goes to the same proposal endpoint a card button uses, with the target explicit. The two that
  // are not proposals keep their own immediate behaviour - a reply DRAFTS (PW-126), Next moves the walk
  // and puts down what it left. An OPTIONS choice is not a verb at all: it goes back as the owner's words.
  const runChip = async (c, anchor) => {
    if (busy || resetting || !c) return;
    if (c.ask) { send(c.ask); return; }
    if (c.verb === "newtask") { browseRef.current?.("new", {}); return; }
    // THE PLACE THAT FIXES IT (concierge.recover, outbound.Fixable): an app link, opened on the canvas like any other
    if (c.verb === "go" && c.href) { openAppLink(c.href); return; }
    // ...a receipt's own task, and its bug report, from the row (they were buttons in the line)
    if (c.verb === "opentask" && c.tid) { openTaskRef.current?.({ tid: c.tid }); return; }
    // ...and the app's own trouble the chat could not fix (troubleshoot.chips): drafted from what it found, not the page's last error
    if (c.verb === "bug") { openBugReport(c.report || shownError(c.text)); return; }
    if (c.verb === "setupask") { askSetup(); return; }
    // ...and the end of the walk's way to walk again: the day card's own button and handler, on the row (the owner, 2026-10-22)
    if (c.verb === "walk") { start(null); return; }
    // ...a Not ours taken further, under its receipt (followUps): the item it names, whatever is on the table now - run at once
    if (c.follow?.kind) {
      setBusy(true); setErr("");
      try {
        await runOperation(api, c.follow.kind, c.follow.target, c.follow.params);
        setMsgs((m) => pressChip(m, c));          // its badge on the line it was under, not "<word> - done." (2026-10-22)
        onChanged?.();
      } catch (e) { setErr(errText(e)); } finally { setBusy(false); }
      return;
    }
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
        setMsgs((m) => pressChip(m, c));          // ...and Mark done's badge on the send's line, not "TQ-0001 marked done." (2026-10-22)
        advance(null, true);
      } catch (e) { setErr(errText(e)); } finally { setBusy(false); }
      return;
    }
    if (c.verb === "answer_agent") { askAnswer(item); return; }
    // SEND TO AGENT ASKS WHAT FIRST (the owner, 2026-10-23): the agent box opens where the item is - nothing starts at the press
    if (AGENT_VERBS.includes(c.verb) && !c.text) { askAgent(item, c.verb); return; }
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
    if ((c.verb === "accept_invite" || c.verb === "decline_invite") && item?.mid) { await calendarAnswer(item, c.verb === "accept_invite" ? "accept" : "decline"); return; }
    if ((c.verb === "propose_time" || c.verb === "find_time") && item?.mid) { setSlotsOn({ item, act: c.verb === "propose_time" ? "propose" : "schedule", anchor: anchor || null }); return; }
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
        await api.post(`/api/reviews/${c.rid}/closeout/${c.act}`);
        setMsgs((m) => pressChip(m, c));          // its badge on the line it was under, not a sentence (the owner, 2026-10-22)
      } catch (e) { setErr(errText(e)); } finally { setBusy(false); }
      return;
    }
    setBusy(true); setErr("");
    try {
      // Prep me is gone (buttons.json `removed`): an old saved chip of a removed verb runs as the verb it became, or not at all
      const verb = liveVerb(c.verb);
      if (!verb) return;
      if (c.revision) await pressAdvice({ verb, key, revision: c.revision }); else await proposeDirect(verb, key, true, null);
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
    // THE WALK WENT ON WITHOUT IT (2026-10-25): Next pressed on the item a close drew at its press, while the close was still on its way.
    // The close landing then put down the table - by then the item Next brought - and asked for the next one again: the walk came back
    // to that item, put it down as one already left, and stood on an empty table; the task Next walked past kept no badge. That Next is
    // the walk's move now, so the close only counts.
    if (movedOnRef.current) { movedOnRef.current = false; onChanged?.(); setNextComing(false); return; }
    // a close that drew the next item at its press leaves that item up: the walk's surface fills it in place (carryRef) - only the
    // table it reads its scope from is empty, as clearTable leaves it
    const early = earlyRef.current; earlyRef.current = null;
    // ...and what this put-down took off the table is recorded (leftRef) - never the item that early draw already put up: Mark done on
    // the first task recorded the second, and the walk then put the second down unseen (the canvas's putDown recorded the first itself)
    if (!early) leave(currentRef.current);
    if (early) { selectionRef.current = null; currentRef.current = null; carryRef.current = early; }
    else clearTable();
    onChanged?.();                                     // a draft may have gone out: the Review badge recounts
    // a settle that brought the rail back with it: held under the empty table's scope, and the walk needs
    // no half-second of grace - the server has settled already, and the timer only has to outlive this
    // render (a proposal's busy flag is released the moment its caller returns)
    if (pile) holdPile(pile, nextSelectionScope(only.current, null));
    setNextComing(true);
    deferInChat(() => surfaceRef.current?.(), pile || settled ? 120 : 500);
  };
  // `pressed`: the label of the button that did it - the folded card wears it as its badge, and no line is said (the owner, 2026-10-22:
  // "we don't need that text ever"). Given, the act landed already; null, only the settle below does it
  const done = async (pressed) => {
    // the card folds to its line the moment its verb is pressed - see interactiveCardIndex
    setMsgs((m) => { const i = interactiveCardIndex(m);
      return i < 0 ? m : m.map((x, j) => (j === i ? { ...x, done: true, ...(pressed ? { pressed } : {}) } : x)); });
    setNextComing(true);
    let pile = null;
    // `only` rides along so the rail comes back captured under the scope this page walks with
    if (current) {
      try { pile = (await api.post("/api/funnel/settle", { key: current, verb: "done", only: only.current, fyi: fyiWant.current, ...(pressed ? { pressed } : {}) })).data?.pile || null; }
      catch (e) {
        // A receipt means the act already landed (a close, a sent reply) and only the settle after it failed - often with
        // the 422 "unavailable" that closing a task causes: walk on. Without one, gone already (404/422) is done too;
        // anything else did NOT happen, and folding the card and walking on said it had.
        if (!pressed && ![404, 422].includes(e?.response?.status)) {
          setNextComing(false);
          setMsgs((m) => [...m.map((x) => (x.done && x.card?.key === current ? { ...x, done: false } : x)),
            { id: `r${Date.now()}`, role: "receipt", status: "error", text: "Not done - Taskuary didn't answer. It is still here; press it again.", chips: [{ verb: "next", label: btn("next") }] }]);
          return;
        }
      }
    }
    advance(pile);
  };
  // A SEND KEEPS THE ITEM ON THE TABLE (the owner, 2026-10-18: "sending and closing are two steps"): the card folds to its line and
  // the row by the prompt is the two ways on - Mark done (the one close) while there is a task, and Next. Nothing is settled and the
  // walk does not move: done() above did both, as if the send had finished the task.
  // ...and NO "Sent to Erin Blake." LINE (the owner, 2026-10-22: "yes"): the folded card wears the button's badge ("✓ Send") and
  // carries the two words itself (`sent` keeps them on the row once it has folded - Line), so they stand while it is the newest line
  const sent = (pressed, tid = null, ref = null) => {
    setMsgs((m) => { const i = interactiveCardIndex(m);
      return i < 0 ? m : m.map((x, j) => (j === i ? { ...x, done: true, sent: true, ...(pressed ? { pressed } : {}), ...sentChips(tid, ref) } : x)); });
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
  // New chat and Continue on an earlier one are the same swap: the server changes which chat is live, the page redraws it
  const swapChat = async (path) => {
    if (busy || resetting || turnFlight.current) return;
    chatEpoch.current += 1;
    leftRef.current.clear();
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
      await api.post(path, null, { timeout: 30000 });
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
  const newChat = () => swapChat("/api/assistant/dock/new");
  // an earlier chat could only be read - going back to where it left off meant making a task of it (TQ-1161)
  const continueOld = () => old && swapChat(`/api/concierge/chats/${old.taskId}/continue`);
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
  // a card's link to its message ("<name>'s message ↗", an idea's Based on): that message's own card, on the table (openMsgCard)
  const timeline = (mid) => openMsgRef.current?.(mid);
  // The walk, taken to a chat you already have connected (WhatsApp, Telegram). This is not a way to
  // CONNECT one - a chat with no Assistant card offers nothing here (the owner, 2026-09-07: "point is
  // to talk to assistant through it not connect it"). While it is there the tab locks itself: two
  // screens answering the same item is how the same mail gets replied to twice.
  const handOver = async (d) => {
    if (busy || resetting) return;
    setBusy(true); setErr("");
    try { await api.post("/api/concierge/handoff", { channel: d.channel }); await loadState(); }
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
    // ...and walks it from its first row, saying nothing: the line that listed the section first (2026-09-30) was a long receipt with
    // report titles doubled, and the rail beside it already lists them ("buttons do the talking", the owner, 2026-10-22)
    pull(first.key, null);
  };
  // A SIDEBAR BUTTON POSTS ITS BROWSE CARD into the conversation - no AI, no tab: the newest one is the live one, and an
  // earlier one folds to its line, so only one detail is ever mounted (the canvas redesign, 2026-09-29)
  const browse = (area, state = {}) => {
    if (area === "connections") readLists(api);        // its lists asked for now, beside its chunk (connectorLists.js)
    navHow.current = "push";
    setRailOpen(false); if (old) setOld(null); setExpanded(false);
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
  // ...and A TASK ASKED FOR WHILE A TURN IS IN FLIGHT waits for that turn, then goes the rail's road (the dead-end walk's RING, 2026-10-20):
  // the Assistant's own answer linking it is followed before its turn has closed, and a Board press during a slow Next is too - each landed
  // the bare card, so the rail ringed nothing and only the address told the server. A walk handed to a phone waits the same way (no lock, 2026-10-23).
  const openLater = useRef(null);
  const openTaskCard = (req) => {
    setExpanded(false); setFoldedKey(null);
    if (setupOn.current) setOverSetup(true);
    if (!(busy || resetting || turnFlight.current)) {
      openExtra.current = req.start || req.act ? { tid: req.tid, autostart: req.start || null, act: req.act || null } : null;
      pull(`task:${req.tid}`); return;
    }
    openLater.current = req;
  };
  browseRef.current = browse; openTaskRef.current = openTaskCard; browseDownRef.current = browseDown;
  useEffect(() => {
    if (busy || resetting || !openLater.current) return;
    const req = openLater.current; openLater.current = null;
    if (req.kind === "msg") openMsgRef.current?.(req.mid); else if (req.kind === "pull") pullRef.current?.(req.key, req.asUser); else openTaskRef.current?.(req);
  }, [busy, resetting]);
  // ...and a line typed while it came up (askLater, at send) goes once it is up - after an open queued above, which takes the turn first,
  // and one at a time: each is its own turn, answered before the next goes
  useEffect(() => {
    if (busy || resetting || turnFlight.current || !askLater.current.length) return;
    const [t, ...rest] = askLater.current; askLater.current = rest;
    send(t, true);
  }, [busy, resetting]);   // eslint-disable-line react-hooks/exhaustive-deps
  // a pull lands through surface() -> landed() -> putOnTable. ONE ASKED FOR WHILE A TURN IS IN FLIGHT WAITS for it, as Open from chat
  // does (above): a rail click mid-pull was refused as busy and did nothing at all - the owner clicked a third task while the second was
  // still coming up, and stayed on the second. The latest ask wins; one queued before it is dropped. A walk handed to a phone refuses nothing.
  const pullRef = useRef(null);
  const pull = (key, asUser) => {
    if (!resetting && (busy || turnFlight.current)) { openLater.current = { kind: "pull", key, asUser }; return; }
    navHow.current = "push";
    if (setupOn.current) setOverSetup(true);                // during setup it opens over setup, which waits where it was (W2)
    setRailOpen(false); if (old) setOld(null); browseDown(); surface(key, asUser || null);
  };
  pullRef.current = pull;

  // A MESSAGE ASKED FOR BY ID - a card's "<name>'s message ↗", an idea's "Based on", a #msg= link - is put on the table as ITS card, the
  // one the walk shows for it (funnel.item_for_key answers msg:N for any message, through its task's row when it has one). It opened a
  // second view of the row on the stage - Summary / Message / Triage / Agent, titled "undefined in chat" - which the owner had taken
  // for gone (2026-10-20: "it should not take you there regardless"). Asked for mid-turn, it waits for the turn as a task does.
  const openMsgCard = (mid) => {
    if (!mid) return;
    if (busy || resetting || turnFlight.current) { openLater.current = { kind: "msg", mid }; return; }
    pull(`msg:${mid}`);
  };
  openMsgRef.current = openMsgCard;

  // THE DAY'S OPENER, one drawing: the empty chat's welcome, and the "Today" card the chat records when the owner sits down
  // (welcome.arrive) - that card drew a row list of its own, which was not the opener (the owner, 2026-10-08)
  const welcome = (m = null) => firstRun ? (
    // FIRST RUN (the owner, 2026-10-14: "first time you login the setup ... on the assistant canvas"): three questions in place of
    // the day, until the walk starts. The popup checklist is gone; this is the one road.
    <div className="tq-msg tq-welcome-msg"><div className="avatar"><AssistantMark /></div>
    <div className="tq-welcome"><FirstRun onChanged={() => loadPile(true)} onWalk={() => { setFirstRun(false); start(null); }}
      onFinish={() => { setFirstRun(false); loadPile(true); }} hidden={setupCovered.current} /></div></div>
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
      {/* no "Nothing is waiting on you - ask me anything" line when the day is empty: the card above says it and the buttons below
          are the choices (the owner, 2026-10-22: "what is this blank text?? buttons do the talking.." / "I hate free text") */}
      {counting && <span data-tq-pile-loading="">Loading...</span>}
      {/* ...nor a line under a greyed Walk explaining why and pointing at the rail (the owner, 2026-10-22:
          "yes remove that walk line too"): the rail's rows are there to click */}
      </DayHold>
      <div className="tq-modes">
        {/* pressable while the day counts or the walk is busy: the press is held (walkQueued) and runs once it can */}
        <button type="button" className="tq-chip primary" disabled={walkQueued || starting || resetting || (!counting && !canAdvance && !onYou)}
          // ...kept on the press itself while loading: the day fills in above this row as it lands and moves it, and a click
          // whose release lands after the move never reaches the button
          onPointerDown={counting ? () => setWalkQueued(true) : undefined}
          onClick={() => (counting || walkOff ? setWalkQueued(true) : start(null))}
          title={btnHint("walk")}>{starting || walkQueued ? "Getting your first one..." : btn("walk")}</button>
        {/* NO "Set up Taskuary" HERE: setup is the Setup button on the top bar, never a choice in the chat (the owner, 2026-10-19) */}
        {/* RUN, not set up: setting things up is the top bar's Setup; this door goes where the reports and workflows ARE
            (the owner, 2026-10-08: "it should be run report/workflow which will take you to reports/workflows") */}
        <button type="button" className="tq-chip" disabled={resetting} onClick={() => onNavigate?.("Reports")}
          title="Your reports and workflows - run one now, or see what each found">Run a report or workflow</button>
        {/* the same walk, on your phone - offered only for a chat that is already connected and
            names an Assistant chat, because this talks to the assistant, it does not set one up */}
        {(state?.doorways || []).map((d) => (
          <button key={d.channel} type="button" className="tq-chip tq-chip-chat" disabled={busy || resetting || !canAdvance}
            onClick={() => handOver(d)} title={`I say hello in ${d.name} and take you through the same items there; this tab keeps working beside it`}>
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
  setupRef.current = () => { if (DEMO) { setup(); return; } setFirstRun(true); backToSetup(); };
  // A REMINDER'S RECEIPT, from the walk's picker or the task view's: where it went - one line, and no Take it back (the owner, 2026-10-19:
  // "no take it back button. hate that"): a day picked wrong is picked again with Remind me
  // ...and since 2026-10-22 not even that line: Remind me's badge on the item's card (the owner: "we don't need that text ever"). The day it
  // went to is on the rail's Later row and on the task; a warning about that day is still worth saying
  const remindReceipt = (out, tid, ref, key = null) => {
    setMsgs((m) => { const ms = pressLine(m, { key, tid }, btn("defer"));
      // ...as a warning, not a success: "✓ That is after it is due" ticked a line saying the day picked may be wrong (the 2026-10-25 sweep)
      return out?.warn ? [...ms, { id: `r${Date.now()}`, role: "receipt", status: "warn", tid, ref, text: out.warn }] : ms; });
  };
  // ...the Advisor's own move (a task to fix what failed, a proposal) pressed from a phone's row as from this one: the phone's strip had
  // none, so a move the row lacks drew no line and no button there (the matrix's phone pass, 2026-10-20)
  const actions = { done, sent, start, handOff, welcome, openTask: onOpenTask, timeline, navigate: onNavigate, items: pileRows(pile), pressAdvice,
    reminded: (out, c) => remindReceipt(out, c?.tid, c?.ref, c?.key),
    next: () => { if (picking && busy) nextHeld.current = true; else runChip({ verb: "next" }); }, picking: picking && !resetting, advance: (pile, settled) => advance(pile, settled), reload: () => loadPile(true), changed: onChanged,
    // an earlier line back on the table - or the folded item itself, which only unfolds: it never left the table
    // ...and a page opened over it is put away with the fold: the item under it was folded by the page, not by its X
    reopen: (key, onTable) => { if (onTable) { setFoldedKey(null); browseDown(); putOnTable(null, "view"); } else pull(key); },
    browseState: (id, state) => { navHow.current = "push"; holdBottom.current = true; setMsgs((m) => m.map((x) => (x.id === id ? { ...x, state } : x))); },
    browse: (area, state) => browse(area, state),
    browseClose: (id) => setMsgs((m) => m.filter((x) => x.id !== id)),    // the New card, closed: its line goes
    // ...and pressed: the line that wrote it says what it started, as the server now has it (a reload reads the same words)
    said: (id, text) => { if (id && text) setMsgs((m) => m.map((x) => (x.id === id ? { ...x, text } : x))); },
    openCard,
    walk: walkTo, walkSaved, walkRestart, chip: runChip, busy: busy || resetting,
    confirm: confirmProposal, cancel: cancelProposal, propose: proposeDirect, preview: previewProposal, agent: startOnItem,
    surface: (key, note) => {
      if (note) setMsgs((m) => [...m, { id: `r${Date.now()}`, role: "receipt", text: note }]);
      deferInChat(() => key ? surfaceRef.current?.(key) : loadPileRef.current?.(), 900);
    } };
  // ...the Next held over a pick runs the moment it lands (or is dropped with it, by a reset)
  useEffect(() => { if (busy || !nextHeld.current) return; nextHeld.current = false; if (!resetting) runChip({ verb: "next" }); }, [busy]);   // eslint-disable-line react-hooks/exhaustive-deps
  const shown = old ? old.messages : msgs;
  const walkDots = starting && (msgs.length ? msgs[msgs.length - 1].id : null) === startLast.current;
  const lastBriefId = [...shown].reverse().find((m) => m.card?.kind === "brief")?.id;
  // the live browse card: the newest one, unless the walk has put an item on the table since
  const browsing = useMemo(() => {
    for (let i = shown.length - 1; i >= 0; i -= 1) {
      if (shown[i].role === "browse") return shown[i].down ? null : shown[i].id;
      if (shown[i].card && !shown[i].card.background_event) return null;
    }
    return null;
  }, [shown]);
  // ...and during setup, the task or message opened over it (overSetup): the newest card, drawn alone like a page (W2)
  const setupCard = firstRun && overSetup && !browsing ? [...shown].reverse().find((m) => m.card && !m.card.background_event) || null : null;
  const setupCovered = useRef(false);
  setupCovered.current = !!(firstRun && (browsing || setupCard));
  // THE TABLE, ONE RECORD (tableState.js): folded by its X or under a page opened over it, the item keeps its key - and the Advisor
  // keeps quiet, its button never acting on what nobody can see. The strip speaks only for the item on the table, at rest.
  const table = tableOf({ current, cardKey, foldedKey, browsing, setup: setupOn.current, over: !!setupCard });
  // ...and the row draws only ITS verbs from the frame it changes (actionRow.rowTable), none of the one a press is leaving: both in one
  // commit, before the paint - no frame shows the old task's buttons, and a press that fails gives them back in the frame it says so
  useLayoutEffect(() => { rowTable(table.key); leaveRow(flight?.from); }, [table.key, flight?.from]);
  // ...and what the rail's tag and the box say of it: a page over it is not it in view (tableWords)
  const tableSays = tableWords(table, currentItem?.ref || (/^task:(\d+)$/.test(table.key || "") ? `TQ-${table.key.slice(5).padStart(4, "0")}` : ""));
  // THE ASSISTANT'S LIGHT OUTRANKS THE ADVISOR'S while its item is on the table: the owner asked for that act in words, and the Advisor's line
  // over it would name another button (assistantLight.js); it goes out at the next press or when the table moves on
  const litTable = { key: table.key, tid: currentItem?.tid ?? Number(/^task:(\d+)$/.exec(table.key || "")?.[1] || 0) };
  const litNow = litPick(lit, litTable);
  useEffect(() => { setLit((l) => litAfter(l, litTable)); }, [litTable.key, litTable.tid, lit]);   // eslint-disable-line react-hooks/exhaustive-deps
  const shownAdvice = table.speaks && !litNow ? adviceShown(advice, { key: table.key, lane: currentItem?.lane }, busy) : null;
  // ...and the decision a WARNING in the task is read from (advice.taskNote): never put out by the Assistant's light or a turn in flight -
  // a warning about the draft does not blink while the chat answers
  const noteAdvice = adviceShown(advice, { key: table.key, lane: currentItem?.lane }, false);
  shownRef.current = shownAdvice?.verb ? { key: shownAdvice.for || shownAdvice.key || table.key, verb: shownAdvice.verb, revision: shownAdvice.revision } : null;
  // ...an answer that landed wins: the strip asking for an AI over a line the Advisor did give hid the line and left its button dark
  // ...and every other reason there is no line, said (words.json advice_none) - an agent at work included, whose line is hidden.
  // ONE DECISION for the strip's word and the button it lights (advice.stripWord): they were chosen apart, and "Connect an AI" stood
  // over a dark Stop and save on an agent that needed nothing (the UI audit's C2, 2026-10-21)
  const { pick: stripPick } = stripWord({ speaks: table.speaks, busy, shown: shownAdvice, lit: litNow, aiOff: caps.ai === false,
    advice, key: table.key, lane: currentItem?.lane });
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
  pickRef.current = stripPick || setupLit;         // what the row is drawn with - a press records what it had filled (notePress)
  const rowEmpty = !rowVerbs.list.some((v) => !String(v.id).startsWith("floor:"));
  // ...and not under a page the owner opened on the canvas (Reports, Connections): they are working there, and the line read
  // as part of that page (the owner's workflow screenshot, 2026-10-15)
  // ...and under a proposal waiting on its Confirm: the item it came from folded away with its row, and the walk must still go on
  // past it (the walk's INLINE, 2026-10-17: the only way on was the card's own buttons in the chat)
  const asked = shown[interactiveCardIndex(shown)]?.proposal, proposing = !!asked && asked.version != null && (asked.status || "proposed") === "proposed";
  // ...and never while the next one is ON ITS WAY (nextComing): "All read, next" folds the batch and its row with it at the press, and
  // the settle plus the walk's grace ran before surface() took `busy` - the floor's Next stood alone on the row for that second, then
  // the next batch's words replaced it (the owner, 2026-10-22: "a next button shows up for a second while the next 4 are loading why??").
  // The "…" under the table is what that second shows; a settle that fails clears nextComing and its receipt offers Next itself
  const hanging = !!state && !old && !walk && !browsing && shown.length > 0 && !busy && !starting && !nextComing && rowEmpty && (canAdvance || !!err || proposing);
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
    // ...read off the table NOW, not the boot's answer: a link to the task the page loaded with, pressed in the chat after Next had moved
    // on, was taken for that reload and opened nothing (the dead-end walk's RING, 2026-10-20)
    // ...BUT A PAGE OPEN OVER IT IS PUT DOWN: Back from Reports or Settings opened over the task lands on that task's own address, and this
    // took it for a reload and left the page drawn, the task hidden and no Back left (the 2026-10-25 sweep) - the 'home' road below, here
    else if (request.kind === "task" && request.fromUrl && !request.start && !request.act
      && Number(currentRef.current?.tid ?? /^task:(\d+)$/.exec(currentRef.current?.key || cardRef.current || "")?.[1] ?? 0) === Number(request.tid)) {
      if (browsing) { setRailOpen(false); setFoldedKey(null); browseDownRef.current?.(); putOnTable(null, "view"); }
      navHow.current = "replace";
    }
    else if (request.kind === "task") openTaskRef.current?.(request);
    else if (request.kind === "msg") openMsgRef.current?.(request.mid);   // #msg=N: that message's card (canvasLinks)
    else if (request.kind === "new") browseRef.current?.("new", {});     // #new-task: the New card in the conversation
    // Back to the address with no place: the walk's own table, the page over it put down (appLinks.onPlace)
    // ...and on a chat that held nothing but pages, the empty chat comes back as it was - its greeting, day card and Walk button: the folded
    // page headers stood in their place over a lone floor Next, one more for every trip (the 2026-10-25 sweep)
    else if (request.kind === "home") { setRailOpen(false); setFoldedKey(null); browseDownRef.current?.(); putOnTable(null, "view");
      setMsgs((m) => (m.length && m.every((x) => x.role === "browse") ? [] : m)); }
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
  // ...and a task its X folded away is not where the owner is: the address stopped naming it (UX walk, 2026-10-22)
  const placeHash = liveBrowse ? hashFor(liveBrowse.area, liveBrowse.state) : litTable.tid && !table.folded ? `#task=${litTable.tid}` : "";
  // ...and not in the commit that serves one: its page is drawn on the next, and this one still showed the table - written then, the
  // address became the table's before the link's own hashchange was heard, and the link opened the task instead (found by PLACE)
  const reqSeen = useRef(0);
  useEffect(() => {
    if (request?.n && request.n !== reqSeen.current) { if (request.n === doneReq.current) reqSeen.current = request.n; return; }
    if (!active || !state || old || firstRun || busy) return;
    recordPlace(placeHash, navHow.current); navHow.current = "replace";
  }, [placeHash, active, state, old, firstRun, busy, request]);   // eslint-disable-line react-hooks/exhaustive-deps
  // BACK IN THE WINDOW ITSELF (TQ-1187): the desktop window has no browser bar, so the step behind a page or task the owner opened is
  // a press away here - the browser's own Back, the road onPlace already takes. Only over a step of ours (appLinks.canGoBack)
  const [canBack, setCanBack] = useState(canGoBack);
  useEffect(() => onStep(() => setCanBack(canGoBack())), []);
  const railPile = useMemo(() => ((leavingTid || continuingTid) && pile?.items
    ? { ...pile, items: asPressed(pile.items, { leaving: leavingTid, continuing: continuingTid }) } : pile),
    [pile, leavingTid, continuingTid]);
  useEffect(() => {                                   // the close has landed: the server's pile no longer has it, or has it For later
    if (leavingTid && pile?.items && putDownLanded(pile.items, leavingTid)) setLeavingTid(null);
  }, [pile, leavingTid]);
  useEffect(() => {                                   // ...and the continue has: the server's pile has it working (or not at all)
    const row = continuingTid && pile?.items ? pile.items.find((i) => i.tid === continuingTid) : undefined;
    if (continuingTid && pile?.items && (!row || row.lane === "working")) setContinuingTid(null);
  }, [pile, continuingTid]);
  // ...and never for long on the page's word alone: a session that ended at once is the server's to say
  useEffect(() => {
    if (!continuingTid) return undefined;
    const t = setTimeout(() => setContinuingTid((x) => (x === continuingTid ? null : x)), 20000);
    return () => clearTimeout(t);
  }, [continuingTid]);
  // ...and the Assistant's lit button with its line, for the phone's row at the view's foot (CanvasItem)
  const canvasState = useMemo(() => ({ height: CANVAS_ITEM_HEIGHT, expanded, folded: foldedKey, browsing, phone, lit: litNow, advice: noteAdvice,
    toggle: () => setExpanded((x) => !x), fold: (key) => { setExpanded(false); setFoldedKey(key); },
    // the task leaves the table the moment it is put down, the "…" under its title line while the server closes it
    // ...and the next item comes up in the same press (drawNextEarly); a close that fails puts the drawn one down and this one back
    putDown: (key, tid = null) => { leave({ key, tid }); leavingRef.current = { key, tid }; setExpanded(false); setFoldedKey(key); setNextComing(true); setLeavingTid(tid); drawNextEarlyRef.current?.(key); },
    pickUp: (key, why) => { takeEarlyBackRef.current?.(); unleave(leavingRef.current?.key === key ? leavingRef.current : { key }); setFoldedKey((k) => (k === key ? null : k)); setNextComing(false); setLeavingTid(null); if (why) setErr(why); } }),
    [bodyH, expanded, foldedKey, browsing, phone, litNow?.verb, litNow?.line, noteAdvice?.for, noteAdvice?.state, noteAdvice?.line, noteAdvice?.verb]);   // eslint-disable-line react-hooks/exhaustive-deps
  const lastCardIdx = useMemo(() => { const i = tableCardIndex(shown, old ? null : current || cardKey), c = shown[i]?.card;
    // ...the canvas's own fallback (the newest card in the chat) included: a durable line about a closed task landing after Next drew it
    return !old && c && c.key !== current && isLeft(c) ? -1 : i; }, [shown, old, current, cardKey]);
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
  // THE ONE-ROW CHAT BAR (the owner, 2026-10-26: "try one row chat bar with ai pop up. let me see what it looks like"): the box is how the
  // owner tells Taskuary what to do with the task ("reply saying Thursday works", "remind me Monday") - acting, not a help chat - and it
  // cost a whole band under the row. It is a pill at the row's end now, widened while it is used, and what is said about the task on the
  // table - the lines after its view - is drawn in a pop-up over the view instead of under it, so the view never moves. The same lines,
  // the same Line, mounted while the pop-up is shut (a last line's chips stay on the row); only the place changes. A phone keeps the column.
  const popOn = !phone && !old && !walk && !firstRun && lastCardIdx >= 0 && barHolds;
  const popLines = useMemo(() => (popOn ? shown.map((m, i) => [m, i]).filter(([, i]) => i > lastCardIdx).slice(-12) : []), [popOn, shown, lastCardIdx]);
  const popPending = popOn && (busy || phoneBusy);
  const [popOpen, setPopOpen] = useState(false), [boxOpen, setBoxOpen] = useState(false);
  const popRef = useRef(null), popBodyRef = useRef(null), boxRef = useRef(null), popOnRef = useRef(false);
  popOnRef.current = popOn;
  const boxWide = boxOpen || !!text.trim() || !!pics.imgs.length || !!emojiEl;
  // THE PILL'S HINT FITS THE PILL: with a row beside it and no task on the table the box is the 220px pill, and the long hint ("Ask
  // Taskuary anything — a name or a subject pulls it in…") ran on under its own send button, cut mid-word (the overnight setup walk,
  // 2026-10-26). Measured, because the row beside it is what makes it a pill (the CSS's :has)
  const [boxNarrow, setBoxNarrow] = useState(false);
  useEffect(() => {
    const el = boxRef.current;
    if (!el || typeof ResizeObserver === "undefined") return undefined;
    // ...and the box OPEN is laid over the canvas, growing up from the pill's corner (assistantView.css): the answer pop-up stands on top
    // of it, never under it, so its last line is not covered while the owner types (--tq-box-h, the open box's height; 0 at rest)
    const ro = new ResizeObserver(() => {
      const r = el.getBoundingClientRect();
      setBoxNarrow(r.width < 360);
      el.closest(".tq-compose")?.style.setProperty("--tq-box-h", el.hasAttribute("data-tq-open") ? `${Math.round(r.height)}px` : "0px");
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, [old, walk]);                                   // the box is mounted only while neither is up
  // ...it opens on the owner's line (send) and on the Assistant speaking up about the task in this session - never on a reload's history
  const popLast = popLines[popLines.length - 1]?.[0];
  useEffect(() => { if (popLast?.role === "assistant" && /^(a|s|d|context)\d/.test(popLast.id)) setPopOpen(true); }, [popLast?.id]);   // eslint-disable-line react-hooks/exhaustive-deps
  // ...and AN ANSWER THAT WAS ONLY A LIT BUTTON shuts it again by itself (the chat bar's open question, default chosen 2026-10-26): a reply
  // that only lit or pressed is no chat line (only words get one), so the pop-up held the owner's own line alone over the task - it is
  // shown a moment, the row's dark button being the answer. Never over an error, nor while the answer is still on its way
  useEffect(() => {
    if (!popOpen || popPending || err || popLast?.role !== "user") return undefined;
    const t = setTimeout(() => setPopOpen(false), POP_LIT_MS);
    return () => clearTimeout(t);
  }, [popOpen, popPending, err, popLast?.id, popLast?.role]);
  // ...and goes with the task: the next one on the table starts with it shut
  const popTable = shown[lastCardIdx]?.card?.key || "";
  useEffect(() => { setPopOpen(false); }, [popTable]);
  // ...shut by Esc, its x, or a press anywhere but on it or the box (a menu it opened is on it)
  useEffect(() => {
    if (!popOpen) return undefined;
    const down = (e) => { if (popRef.current?.contains(e.target) || boxRef.current?.contains(e.target) || e.target.closest?.(".MuiPopover-root, .MuiMenu-root, .MuiDialog-root")) return; setPopOpen(false); };
    const key = (e) => { if (e.key === "Escape") setPopOpen(false); };
    document.addEventListener("pointerdown", down, true); document.addEventListener("keydown", key);
    return () => { document.removeEventListener("pointerdown", down, true); document.removeEventListener("keydown", key); };
  }, [popOpen]);
  // ...its newest words in view, as the chat's end is
  useLayoutEffect(() => { const el = popBodyRef.current; if (el && popOpen) el.scrollTop = el.scrollHeight; }, [popOpen, popLines.length, popPending, words]);
  // ...a line of its own that stands under the card on the table only while the answer is on its way (tq-pending, assistantView.css) -
  // or in the pop-up over it, where the answer it waits for will be
  const pendingLine = <>{(busy || phoneBusy || nextComing || walkDots) && (
            <div className="tq-msg tq-pending"><div className="avatar"><AssistantMark /></div>
              <div className="body">{busy && words ? <div className="tq-words" data-tq-words="">{looksMd(words) ? <Md text={words} /> : words.split("\n").map((p, i) => <p key={i}>{p}</p>)}</div>
                : <span className="tq-typing"><i /><i /><i /></span>}
                {/* ...and how long it has been at it, where the dots alone were silent: its own clock, so the chat does not redraw each second */}
                {busy && answering.current && !DEMO && <WorkingFor />}
                {/* an answer that hangs had no way out: New chat is refused while one is being written (dock/new 409) */}
                {busy && answering.current && !DEMO && (
                  <button type="button" className="tq-chip" style={{ marginLeft: 8 }} title="Stops the answer being written and gives you the chat back."
                    onClick={() => { api.post("/api/concierge/stop").catch(() => {}); stopRef.current?.abort(); }}>Stop</button>
                )}
                {busy && !!steps.length && <AgentSteps data={{ steps }} />}
                {!!work.length && <div className="tq-work">{work.map((w, i) => <div key={i}>{w}</div>)}</div>}
              </div>
            </div>
          )}</>;
  const errLine = err && <Typography component="div" sx={{ color: "#7a2f3c", fontSize: 12, mb: 1 }}>{err}<ReportLink text={err} /></Typography>;
  const chat = (
    <div className="tq-asst-col" style={{ position: "relative", flex: 1, minHeight: 0 }}>
      <div className="tq-chat-head">
        {/* no mark here: the top bar already carries the logo (the owner, 2026-10-06: "don't need it on top of the assistant") */}
        {canBack && !!placeHash && !old && !firstRun && <Tooltip title="Back (Alt+←)"><IconButton size="small" aria-label="Back" onClick={() => window.history.back()} sx={{ ml: -0.75, mr: 0.25 }}><ArrowBackIcon sx={{ fontSize: 18, color: DIM }} /></IconButton></Tooltip>}
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
      {slotsOn && <SlotPicker mid={slotsOn.item.mid} act={slotsOn.act} anchor={slotsOn.anchor || document.body} onClose={() => setSlotsOn(null)}
        onRefused={(data) => calendarDrafted(data, slotsOn.item)} onPick={(slot) => calendarAnswer(slotsOn.item, slotsOn.act, slot)} />}
      <Popover open={!!aiEl} anchorEl={aiEl} onClose={() => setAiEl(null)} anchorOrigin={{ vertical: "bottom", horizontal: "right" }} transformOrigin={{ vertical: "top", horizontal: "right" }}
        slotProps={{ paper: { sx: { p: 1.5, width: 320 } } }}>
        <Typography sx={{ fontSize: 12, fontWeight: 600, color: INK, mb: 0.5 }}>{state?.scripted ? "Scripted demo assistant" : "Which AI speaks here"}</Typography>
        <Typography variant="caption" sx={{ color: DIM, display: "block", mb: 1, lineHeight: 1.45 }}>{state?.scripted
          ? "Every thread, post, and reply here is invented and runs locally in this page. No AI, agent, mailbox, or outside system is connected."
          : aiSays(state?.providers)}</Typography>
        <Select size="small" fullWidth value={state?.pick || ""} displayEmpty disabled={!!state?.scripted} onChange={(e) => pickAi(e.target.value)} sx={{ fontSize: 12 }}>
          {!state?.providers?.length && <MenuItem value="">{state?.scripted ? "Scripted demo" : "No AI connected"}</MenuItem>}
          {(state?.providers || []).map((p) => <MenuItem key={p.pick} value={p.pick} sx={{ fontSize: 12 }}>{p.label}{p.type === "demo" ? " · demo" : p.type === "cli" ? " · can look things up and act" : " · fast, talks only"}</MenuItem>)}
        </Select>
        {!state?.scripted && <button type="button" className="tq-linkish" style={{ marginTop: 8, fontSize: 12 }}
          onClick={() => { setAiEl(null); openAppLink(state?.providers?.length ? AI_DEFAULTS : place("ai").href); }}>
          {state?.providers?.length ? `Choose which AI does what - ${place("ai_defaults").name}` : "Connect an AI"}</button>}
      </Popover>
      {old && <div className="tq-old-banner"><span>You are reading an earlier chat.</span>
        <button type="button" className="tq-chip" onClick={continueOld} disabled={busy || resetting}>Continue this chat</button>
        <button type="button" className="tq-chip" onClick={() => setOld(null)}>Back to today</button></div>}
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
          {/* ...and setup stays MOUNTED under it, hidden (W2): the rail's steps, the Setup chip and Chat bring it back as it was left */}
          {firstRun && (browsing || setupCard) && <div data-tq-setup-over="" style={{ display: "contents" }}>
            <div className="tq-next" role="status" data-tq-setup-back=""><div className="tq-next-txt">Setup is waiting where you left it.</div>
              <button type="button" className="tq-chip" onClick={backToSetup}>{`Back to ${place("setup").name}`}</button></div>
            {browsing ? shown.filter((m) => m.id === browsing).map((m) => <Line key={m.id} m={m} live last tableChips={[]} barHolds={false}
                                     actions={actions} fresh={null} canvas={canvasState} />)
              : <Line key={setupCard.id} m={setupCard} live last tableChips={tableChips} barHolds={barHolds}
                  actions={actions} fresh={currentItem} canvas={canvasState} />}
          </div>}
          {firstRun ? state && <div data-tq-setup-under={setupCovered.current ? "hidden" : ""} style={setupCovered.current ? { display: "none" } : undefined}>{welcome()}</div>
            : state && !shown.length && !busy && !starting && welcome()}
          {!firstRun && shown.map((m, i) => popOn && i > lastCardIdx ? null : <Line key={m.id} m={m} lastBrief={m.id === lastBriefId} live={!old && i === lastCardIdx} last={!old && i === lastSaidIdx} tableChips={tableChips} barHolds={barHolds}
                                     actions={actions} fresh={currentItem} canvas={old ? null : canvasState} />)}
          {/* CONTINUE, IN LINE (the owner, 2026-09-30): a card under the item, like New - the mic and pictures in it */}
          {!old && continueOn && (
            <div className="tq-browse-line" ref={(el) => { if (el && !el.dataset.seen) { el.dataset.seen = "1"; el.scrollIntoView({ block: "nearest", behavior: "smooth" }); } }}>
              <ContinueBox inline task={continueOn.task} taskRef={continueOn.ref} initial={noteFor(continueOn.task.TaskId)}
                onClose={() => { continueNote.current = null; setContinueOn(null); }}
                onPress={() => setContinuingTid(continueOn.task.TaskId)} onFail={() => setContinuingTid(null)}
                onDone={() => {
                  // NO RECEIPT: the session on the table shows it working - "Continuing with your note..." under it was clutter
                  // (the owner, 2026-10-13). ...and the table STAYS on it: you continued it to watch it work, not to be walked past it (the owner,
                  // 2026-09-30: "the session started but then closed and moved on without hitting next"); the view shows the
                  // session when it opens (TaskPage hears task-changed)
                }} />
            </div>
          )}
          {/* THE AGENT BOX, under the item it is about - what to do, the mic and pictures, which agent - and its Start is the start */}
          {!old && agentOn && (
            <div className="tq-browse-line">
              <AgentAsk inline coding={agentOn.coding} title={`${btn(agentOn.coding ? "coding_agent" : "regular_agent")}${agentOn.item.ref ? ` · ${agentOn.item.ref}` : ""}`}
                what={agentOn.item.kind === "report" ? "It gets this report and its rows." : agentOn.item.mid ? "It gets the message and its attachments." : "It gets this item."}
                placeholder={agentOn.item.kind === "report" ? ASK_REPORT : undefined}
                onClose={() => setAgentOn(null)} onStart={(o) => startOnItem(agentOn.item, o)} />
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
                  // ...its badge on the item's card, not a sentence repeating the note - the note is on the task (the owner, 2026-10-22)
                  // ...ITS OWN badge, and the note under it (typed-put-down-acts, 2026-10-23): it wore "Mark done" with no note until a reload
                  // drew the server's stamp (the 2026-10-25 sweep)
                  setMsgs((m) => pressLine(m, { tid: on.task.TaskId }, btn("close_note"), String(note || "").trim()));
                }} />
            </div>
          )}
          {!popPending && pendingLine}
          {!(popOn && popOpen) && errLine}
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
      {/* NO LOCK WHILE THE WALK IS ON THE PHONE (the owner, 2026-10-23: "we used to have that if we were talking on the phone it would
          lock the screen on desktop but we should probably get rid of that"): the box stays, and the table follows the phone's walk */}
      {!old && !walk && (
        <div className="tq-compose" {...pics.drop}>
          {/* THE ANSWER POP-UP (the one-row chat bar, 2026-10-26): the lines after the task view, over it - it never moves - a few turns
              tall at most, scrolling inside. Shut, it stays mounted: the last line's chips are on the row either way */}
          {popOn && (!!popLines.length || popPending) && (
            <div className="tq-chat-pop" data-tq-chat-pop="" role="dialog" aria-label="Taskuary's answer" ref={popRef} hidden={!popOpen}
              style={{ maxHeight: Math.max(180, Math.round(bodyH * 0.45)) }}>
              <div className="tq-chat-pop-head"><TaskuaryMark size={16} /><b>Taskuary</b>{currentItem?.ref && <span>{`· ${currentItem.ref}`}</span>}<span style={{ flex: 1 }} />
                <Tooltip title="Past chats"><IconButton size="small" aria-label="Past chats" onClick={() => { setPopOpen(false); openChats(); }}><HistoryIcon sx={{ fontSize: 16, color: DIM }} /></IconButton></Tooltip>
                <IconButton size="small" aria-label="Close the answer" onClick={() => setPopOpen(false)}><CloseIcon sx={{ fontSize: 16, color: DIM }} /></IconButton></div>
              <div className="tq-chat-pop-body" ref={popBodyRef}>
                {popLines.map(([m, i]) => <Line key={m.id} m={m} lastBrief={m.id === lastBriefId} live={false} last={i === lastSaidIdx} tableChips={tableChips} barHolds={barHolds}
                  actions={actions} fresh={currentItem} canvas={canvasState} />)}
                {popPending && pendingLine}
                {popOpen && errLine}
              </div>
            </div>
          )}
          <RetryVerbs item={currentItem} failed={(pile?.items || []).filter((i) => i.lane === "unjudged").length}
            onSaid={(text, status) => setMsgs((m) => [...m, { id: `r${Date.now()}`, role: "receipt", status: status || "done", text }])}
            onDone={() => loadPile(true)} />
          {/* ONE PANEL, THREE LAYERS (the owner, 2026-10-13: "i thought there will be one border around all 3"): the Advisor's
              suggestion, the row whose filled button it picked, and the box - one border, the box its floor */}
          <div className="tq-dock">
          {/* ...setup's own line only while setup is in view: a task opened over it speaks for itself (tableOf's `over`, 2026-10-26) */}
          {firstRun && !setupCard && <SetupLine />}
          {/* NO STRIP OVER THE ROW (the owner, 2026-10-26: "maybe keep the box but remove the advisor? not sure the advisor is really
              useful"): the Advisor's pick is the row's one dark button and says nothing; the few lines that warn are in the task, beside
              what they are about (advice.taskNote). AdvisorNext only joins a move the row lacks, and leaves the walks' hidden mark */}
          {!firstRun && table.speaks && !holding && !hostedRow && <>
            <AdvisorNext advice={shownAdvice} onPropose={pressAdvice} onErr={setErr} />
            {/* ...and a decision that lights NOTHING on purpose (an agent asking is answered in its own pane, the design's state 7): no
                word, no button - only a mark, so the dead-end walk can tell it from one that never got its decision */}
            {!shownAdvice && advice?.for === onTable && advice?.state && !advice.verb && !advice.none && <div hidden data-tq-advice="" data-tq-silent="" data-tq-unlit={advice.state} />}
          </>}
          {!firstRun && <ImageTray pics={pics} sx={{ width: "100%", mb: 0.75 }} />}
          {/* ONE ROW: the row's groups and the box share a line (the one-row chat bar, 2026-10-26) - the box a pill at its end while at rest,
              widened while it is used, the groups folding into their ▾ for the room (ActionRow measures what is left; Next and the lit
              move never fold). With no row - the day's opener, a phone, whose row rides with its task view - the box is the whole line */}
          <div className="tq-dock-line">
          {/* ...and during setup its line is the Advisor's (SetupLine): the move setup fills (FirstRun's tone) is the one lit - nothing
              was, so the line said "pick it" over a plain Back and a greyed Next (2026-10-19) */}
          <ActionRow advised={stripPick || setupLit} hold={!!reading && reading === onTable} />
          <div className="tq-compose-box" style={firstRun ? { display: "none" } : undefined} ref={boxRef} data-tq-open={boxWide ? "" : undefined}
            onFocus={() => setBoxOpen(true)} onBlur={(e) => { if (!e.currentTarget.contains(e.relatedTarget)) setBoxOpen(false); }}>
            <div className="tq-compose-tools">
            <AttachImage pics={pics} sx={{ color: DIM }} />
            <MicButton size={18} sx={{ width: 34, height: 34, p: 0, color: DIM }} onText={(t) => setText((v) => (v ? `${v} ${t}` : t))} />
            <Tooltip title="Send an emoji response">
              <IconButton size="small" aria-label="Choose an emoji response" disabled={busy || resetting}
                onClick={(e) => setEmojiEl(e.currentTarget)} sx={{ width: 34, height: 34, p: 0, color: DIM }}>
                <SentimentSatisfiedAltIcon sx={{ fontSize: 18 }} />
              </IconButton>
            </Tooltip>
            </div>
            {/* ...the pop-up shut, what was said comes back from here */}
            {popOn && !popOpen && (!!popLines.length || popPending) && (
              <Tooltip title={popPending ? "Answering…" : "Show the last answer"}>
                <IconButton size="small" aria-label="Show the last answer" data-tq-pop-again="" onClick={() => setPopOpen(true)}
                  sx={{ width: 28, height: 28, p: 0, color: popPending ? "#526b53" : DIM }}><ChatBubbleOutlineIcon sx={{ fontSize: 16 }} /></IconButton>
              </Tooltip>)}
            {/* a phone's composer is one line tall and the long hint wrapped under its own edge, cut
                mid-word ("name or a subject pulls it in" lost its tail, 2026-09-20): the short hint there - and the pill's at rest */}
            <textarea ref={composeRef} rows={1} value={text} disabled={resetting} aria-label={tableSays.name}
              placeholder={boxNarrow && !boxWide ? "Ask…" : phone ? tableSays.phone : !popOn ? tableSays.box : boxWide ? "Tell me what to do with it, or ask about it…" : "Ask…"}
              onChange={(e) => setText(e.target.value)} onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); }
                // Esc shuts the pop-up first, then hands an empty box back to its pill
                if (e.key === "Escape") { e.stopPropagation(); if (popOpen) setPopOpen(false); else if (!text.trim()) e.currentTarget.blur(); }
              }} />
            <button type="button" className="tq-send" aria-label="Send" disabled={busy || resetting || pics.busy || !(text.trim() || pics.imgs.length)} onClick={() => send()}><SendIcon fontSize="small" /></button>
          </div>
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


  // A TASK FOLDED BY ITS X IS PUT AWAY (UX walk, 2026-10-22): its rail row lost the "on the table" mark and the address its #task, which
  // said it was still in view - so its row is an ordinary row now, and a click on it opens it again in place, as its folded line does
  const unfoldTable = () => { setRailOpen(false); setFoldedKey(null); browseDown(); putOnTable(null, "view"); };
  return (
    <>
    {DEMO && <DemoJourney onChanged={() => { loadPile(true); onChanged?.(); }} />}
    <FeedView onOpenTask={onOpenTask} onChanged={onChanged} active={active} onGo={(tab, key) => browse(key)} navOn={navOn}
      onInventoryFilter={inventoryFilterChanged} unreadInventory={pile}
      // a task Removed as not a task leaves the rail with "Removed <title> - Undo" over it (Removed.jsx); Undo puts it back on the rail
      top={<><UndoLine kinds={["task"]} onRestored={() => { loadPile(true); onChanged?.(); }} sx={{ mx: 1, mt: 1, mb: 1 }} /><Pile pile={railPile} settingUp={firstRun ? setupTodo || "finish setting up" : ""} noAi={!!state && !(state.providers || []).length}
        current={old || table.folded || (leavingTid && currentItem?.tid === leavingTid) ? null : currentItem} coming={nextComing || busy}
        error={pile ? "" : err} onRetry={() => { setErr(""); loadPile(true); }}
        onPull={(key, asUser) => { sectionRef.current = null; if (table.folded && key === table.key) unfoldTable(); else pull(key, asUser); }}
        onSection={walkSection} onMoreFyi={moreFyi} tag={tableSays.tag} onCurrent={() => { setRailOpen(false); if (table.folded || table.place) unfoldTable(); }} /></>}
      stage={chat}
      onPull={(r, o) => pull(keyForRow(r), o?.quiet ? null : `Tell me about “${r.Subject || r.Title || "this"}”`)}
      railOnNarrow={railOpen} setupMode={firstRun} setupRail={firstRun ? <SetupSteps /> : null} />
    </>
  );
}
