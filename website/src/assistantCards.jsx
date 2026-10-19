// The cards under Taskuary's lines. Commentary explains; the clearly labelled button acts - so
// the model never chooses a card (funnelPile.cardFor does, by kind) and never claims an action
// happened. Every button here calls an endpoint that already exists for the Timeline, the Review
// queue or the Board; the card only puts it under the sentence that was just said. Reading
// happens IN the card (the full text unfolds under it) and every card links to where the whole of
// it lives - the task, or the row on the Timeline - because everything is the chat.
import React, { useEffect, useRef, useState } from "react";
import { draftCanSend, useCapabilities } from "./capabilities.js";
import { movesOf, useVerbs } from "./actionRow.js";
import { choice, hint as btnHint, label as btn } from "./buttons.js";
import { Button, TextField } from "@mui/material";
import SendRoundedIcon from "@mui/icons-material/SendRounded";
import RefreshRoundedIcon from "@mui/icons-material/RefreshRounded";
import DoneRoundedIcon from "@mui/icons-material/DoneRounded";
import EventIcon from "@mui/icons-material/Event";
import TerminalIcon from "@mui/icons-material/Terminal";
import OutlinedFlagIcon from "@mui/icons-material/OutlinedFlag";
import api from "./api.js";
import { gistFor } from "./fyiRow.js";
import { runOperation } from "./taskOps.js";
import { ChannelIcon, TaskuaryMark, channelColor, cleanText, fmtDateTime, fmtTime12 } from "./ui.jsx";
import { openAppLink } from "./appLinks.js";
import { CardErr, failOf } from "./failure.jsx";
import { place } from "./words.js";
import { Md, looksMd } from "./md.jsx";
import { jsonRows } from "./reportRows.js";
import DigestText from "./DigestText.jsx";
import TodayMeetingsStrip from "./TodayMeetingsStrip.jsx";
import { useCalendarToday } from "./calendarToday.js";
import { ROLES, ASSISTANT, ALERT, ALERT_INK } from "./theme.jsx";
import { laneMeta } from "./funnelPile.js";
import { age, ago, plural } from "./timeWords.js";
import { SECTION, WORD, ideaWord } from "./lanes.js";
import { sendBlockLine, draftState } from "./sendState.js";
import { openReply, useDraftJob } from "./replyDraft.js";
import { agentRuns } from "./taskFilter.js";
import { progressLine } from "./checklist.js";
import { RepoPicker } from "./RepoPicker.jsx";
import { Attachments, mentionsPicture } from "./Attachments.jsx";
import { useCliSetup, SetupButton, CliPane, canSetup } from "./cliSetup.jsx";
import OwnerForm from "./OwnerForm.jsx";
import { FirstSync } from "./SetupWizard.jsx";
import { gistOf, refOf, summarize, stateOf, whoOf } from "./walkSummary.js";
import { closeoutOf, reviewText } from "./reviewProposal.js";
import { OFFER_HINT, OFFER_LABEL, useCloseoutState } from "./closeoutState.js";
import { READY } from "./taskLifecycle.js";
import { connError, openBugReport } from "./bugReportOpen.js";

const errText = (e) => e?.response?.data?.detail || e?.message || "That did not work";
const edge = (lane) => { const r = laneMeta(lane).role; return r ? ROLES[r].solid : "#d3ccc1"; };
const primary = { color: "#fff", background: ASSISTANT.gradient, "&:hover": { background: "linear-gradient(90deg, #465866, #698368)" } };
const quiet = { color: "#4d4a43", borderColor: "#d6cec1", bgcolor: "#fffdfb" };
const faint = { color: "#867f74" };

// where a thing came from: the channel's own logo, a calendar for a meeting, a terminal for an
// agent, the mark for the assistant's own line
export function SourceMark({ item, size = 14 }) {
  if (!item) return null;
  if (item.kind === "meeting") return <EventIcon sx={{ fontSize: size, color: "#55697a" }} />;
  // a goal has no source: it wears the project mark (spec 2026-10-12)
  if (String(item.kind || "").startsWith("goal")) return <OutlinedFlagIcon sx={{ fontSize: size, color: "#55697a" }} />;
  // an agent on it is the row's STATE (its chip says so), not where it came from: an Advisor idea, a report or a
  // mail an agent picked up keeps its own mark (the owner, 2026-09-25: "it should be advisor as that's what it
  // comes from"). The terminal is left for work with no source at all.
  if ((item.kind === "agent" || item.kind === "agentdone") && !item.channel) return <TerminalIcon sx={{ fontSize: size, color: "#41525f" }} />;
  if (item.kind === "setup" || item.kind === "brief" || item.kind === "walk" || (item.kind === "idea" && !item.channel)) return <TaskuaryMark size={size} />;
  if (item.kind === "fyis" && !item.channel) return <TaskuaryMark size={size} />;
  return <ChannelIcon channel={item.channel || "email"} sx={{ fontSize: size }} />;
}

// ...and the same answer as ONE COLOUR, for the dot on the work rail's spine. It mirrors SourceMark
// branch for branch on purpose: the dot and the logo beside it must never disagree about where a row
// came from (the owner, 2026-09-16: "the timeline dots should be the color of the source").
export function sourceColor(item) {
  if (!item) return "#a9a294";
  if (item.kind === "meeting") return "#55697a";
  if (String(item.kind || "").startsWith("goal")) return "#55697a";
  if ((item.kind === "agent" || item.kind === "agentdone") && !item.channel) return "#41525f";
  if (item.kind === "setup" || item.kind === "brief" || item.kind === "walk" || (item.kind === "idea" && !item.channel)) return ASSISTANT.solid;
  if (item.kind === "fyis" && !item.channel) return ASSISTANT.solid;
  return channelColor(item.channel || "email");
}

// the link every card carries: the task when there is one, else the row on the Timeline
// ...and only the task: the Timeline link set a #msg= that nothing in Chat mode reads, so it was a
// button that did nothing (the owner, 2026-09-23: "on the timeline does nothing"). A card with no task
// opens its whole text in place (More), which is what the link was for.
const Where = ({ card, onOpenTask, label }) => card?.tid
  ? <Button size="small" onClick={() => onOpenTask?.(card.tid)} sx={faint}>{label || `Open ${card.ref || "task"}`} ↗</Button>
  : null;

// ONE CARD, FIVE PARTS, EVERY KIND (the owner, 2026-09-23: "all cards should be equal ... there should be
// summary of who wants what ... buttons should be next or do action now with link to task"): where it
// came from, who wants what, what is ready, what the button does, then the verb and Next. The line
// below the card - the conversation's own verbs - rides INTO the card through CardNav: Next beside
// the verb, every other word on one quiet "Also" line, so a card is never two rows of buttons.
export const CardNav = React.createContext({ onNext: null, also: [], items: null, surface: null });

// the first sentence of triage's summary - it now answers "who wants what" (triage.TASK_FIELDS)
export const firstSentence = (s) => String(s || "").trim().split(/(?<=[.!?])\s+/)[0] || "";

// WHAT A CARD READS, fetched once and kept (the owner, 2026-09-23: "this opens then rerenders"). The
// lead and the box each fetched the same task, and every rail refresh (a new presentation_revision)
// fetched both again; the box also BLANKED to "…" whenever the item's message id moved - which a
// grouped task's does, between the walk's copy and the rail's. Now a url is fetched once in flight,
// the last answer is drawn at once, a refresh swaps it in only if it changed, and nothing blanks.
// A read is shared only for the SAME revision: joining whatever was in flight for the url made a newer
// revision wait on an older, slower answer and draw it - the stale text won the race (PW-106). Each url
// numbers its reads, and only the newest may land; a superseded one changes nothing.
const fetched = new Map(), inFlight = new Map(), newest = new Map();
function useFetched(url, revision) {
  const [data, setData] = useState(() => (url ? fetched.get(url) ?? null : null));
  useEffect(() => {
    if (!url) { setData(null); return undefined; }
    let live = true;
    setData(fetched.has(url) ? fetched.get(url) : null);     // a DIFFERENT thing never shows the last one's text
    const key = `${url}|${revision ?? ""}`;
    let flight = inFlight.get(key);
    if (!flight) {
      const seq = (newest.get(url) || 0) + 1;
      newest.set(url, seq);
      flight = api.get(url).then(({ data: d }) => {
        if (newest.get(url) !== seq) return { seq };
        const was = fetched.get(url);
        const same = was && JSON.stringify(was) === JSON.stringify(d);
        if (!same) fetched.set(url, d);
        return { seq, d: same ? was : d };
      }).catch((e) => ({ seq, d: fetched.get(url) || { error: errText(e) } })).finally(() => inFlight.delete(key));
      inFlight.set(key, flight);
    }
    flight.then(({ seq, d }) => { if (live && seq === newest.get(url) && d !== undefined) setData(d); });
    return () => { live = false; };
  }, [url, revision]);
  return data;
}

// the asker, in bold, when the sentence opens with them
function Lead({ text, who }) {
  const t = String(text || "").trim();
  if (!t) return null;
  const w = String(who || "").trim();
  if (w && t.toLowerCase().startsWith(w.toLowerCase())) return <div className="tq-card-lead"><b>{t.slice(0, w.length)}</b>{t.slice(w.length)}</div>;
  return <div className="tq-card-lead">{t}</div>;
}


// THE CARD'S THREE PARTS (the owner, 2026-09-28: "the goal is to see what triggered the task, agent action, and what
// we are reviewing"): every card with a task behind it tells it in that order - the trigger as the lead, this line,
// then the thing to decide. The agent's part lived only inside a `why` sentence, or unlabelled, or nowhere.
// THE STORY IS QUIET, YOUR MOVE IS LOUD (the owner, 2026-09-28: "your eye should be drawn to the thing to do" - a mix
// of the canvas's thread and ledger). Who asked and what the agent did are told as a thread of the people in it, in
// muted ink; the one decision is YourMove, framed, its main button inside. Presentation only: every road the cards
// take is their own, unchanged.
const CHANNEL_WORD = { email: "Email", github: "GitHub", whatsapp: "WhatsApp", teams: "Teams", slack: "Slack", telegram: "Telegram",
  sms: "Text", discord: "Discord", google_chat: "Google Chat", assistant: "Advisor", own: "New task" };
export const channelWord = (ch) => CHANNEL_WORD[String(ch || "").toLowerCase()] || (ch ? String(ch)[0].toUpperCase() + String(ch).slice(1) : "");
// work the owner started has nobody behind it: its "sender" is the owner ("owner" from CreatedBy, "You" from ownwork)
export const isOwn = (card) => card?.channel === "own" || ["owner", "you", "me"].includes(String(card?.who || "").trim().toLowerCase());
// a display name as a person is called (triage.person_name): Outlook's "Doyle, Alex M. at Northwind" reads "Alex M. Doyle"
export const personName = (name) => {
  let n = String(name || "").replace(/\s*<[^>]*>/g, "").replace(/"/g, " ").replace(/\s+/g, " ").trim();
  if (!n || n.includes("@")) return n;
  n = n.replace(/\s+at\s+[^,<>@]+$/i, "").trim();
  const parts = n.split(",");
  if (parts.length === 2 && parts[0].trim() && parts[1].trim() && parts[0].trim().split(" ").length <= 2) n = `${parts[1].trim()} ${parts[0].trim()}`;
  return n;
};
const capital = (s) => { const t = String(s || "").trim(); return t ? t[0].toUpperCase() + t.slice(1) : ""; };
// WHAT AN AGENT IS, never the profile's bare name (the owner, 2026-09-28, puzzled by a bare profile name on a card): a terminal
// agent codes, a chat one does general work; the profile shows beside it only when it says more than that.
const PLAIN_PROFILE = new Set(["coding", "claude", "codex", "agent", "assistant", "general", "regular", "the agent"]);
export function agentLabel(card, name) {
  const p = String(name || card?.working || card?.agent || "").trim();
  const chat = ["chat", "assistant"].includes(String(card?.mode || "")) || p.toLowerCase() === "assistant";
  const kind = chat ? "General agent" : "Coding agent";
  return p && !PLAIN_PROFILE.has(p.toLowerCase()) ? `${kind} · ${p}` : kind;
}
// the report an agent files (wrapup.py: AGENT REPORT, CODER REPORT on older rows): Summary is what it found, Actions what it did, Determination its verdict -
// the evidence the move is decided on, where one sentence ("PR #81 was reviewed and approved") is not enough
export function readReport(body) {
  const text = String(body || "").replace(/^((?:AGENT|CODER) REPORT|HANDOVER NOTE)\s*/, "").split(/\n\s*LAST MESSAGE\s*\n/)[0];
  const field = (k) => ((text.match(new RegExp(`^\\s*${k}:\\s*(.+)$`, "im")) || [])[1] || "").trim();
  return { summary: field("Summary"), actions: field("Actions"), verdict: field("Determination"), text: text.trim() };
}
const shortVerdict = (r) => (r?.verdict && r.verdict.length <= 60 && !String(r.summary || "").toLowerCase().includes(r.verdict.toLowerCase()) ? r.verdict : "");
// WHAT THE THING IS, in its own words (the owner, 2026-09-28: "you don't see what the PR is? at least the title"): the
// source's subject - a pull request's title with its number, an email's subject - since the summary's first sentence
// says who wants what, not what it is. "owner/repo#113 fix: ..." reads "PR #113 · fix: ..."
export function subjectLine(msg) {
  const s = String(msg?.Subject || "").replace(/\s+/g, " ").trim();
  if (!s) return "";
  const m = s.match(/^[\w.-]+\/[\w.-]+#(\d+)\s+(.*)$/);
  const kind = /^\s*\[pull request/i.test(String(msg?.BodyText || "")) ? "PR " : /^\s*\[issue/i.test(String(msg?.BodyText || "")) ? "Issue " : "";
  if (m) return `${kind}#${m[1]} · ${m[2]}`;
  return s.replace(/^((re|fw|fwd):\s*)+/i, "");
}
const restOf = (summary) => String(summary || "").trim().split(/(?<=[.!?])\s+/).slice(1).join(" ");
export const reportOf = (doc) => (doc?.comments || []).slice().reverse().find((c) => /^((?:AGENT|CODER) REPORT|HANDOVER NOTE)/.test(String(c.Body || "")));
const TASK_GLYPH = <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round"><rect x="4" y="4" width="16" height="16" rx="3" /><polyline points="8.5 12 11 14.5 15.5 9.5" /></svg>;
const CODE_GLYPH = <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round"><polyline points="8 7 3 12 8 17" /><polyline points="16 7 21 12 16 17" /></svg>;

// asker: the task's own sentence (default) | false (no task to tell). agent: "auto" (drawn when it has anything) |
// true (drawn, "No agent yet" when empty) | false. state: the agent's word ("finished", "asks you"...). did: its
// summary when no report was filed. extra: more lines under the agent (its folded screen, its question's context).
export function Story({ card, asker = true, agent = "auto", state, did, name, extra, fallback, by, words, tail = false, turn }) {
  const doc = useFetched(card?.tid ? `/api/tasks/${card.tid}` : null, card?.presentation_revision);
  const [open, setOpen] = useState(false);
  // THE ADVISOR ASKED (the owner, 2026-09-28: "why does advisor say YOU in the task? it's the advisor"): a task made from
  // an Advisor idea is created by the assistant - its asker is the Advisor, not the owner
  const advisor = by === undefined && (String(doc?.task?.Source || "") === "assistant" || String(doc?.task?.SourceRef || "").startsWith("assistant:")
    || card?.channel === "assistant");
  const own = by === undefined && !advisor && isOwn(card);
  const said = capital(firstSentence(doc?.task?.Summary) || firstSentence(fallback) || card?.title);
  const src = (doc?.messages || []).find((m) => m.Status !== "context") || null;
  const subject = subjectLine(src);
  const showSubject = subject && !said.toLowerCase().includes(subject.replace(/^(PR |Issue )?#\d+(\s·)?\s*/, "").toLowerCase());
  const rest = restOf(doc?.task?.Summary);
  const who = advisor ? "Advisor" : own ? "You" : by === null ? "The task" : personName(by || card?.who || "Someone") || "Someone";
  const from = [advisor ? "an idea" : own ? (card?.mid && card?.channel !== "own" ? channelWord(card.channel) : "your task") : channelWord(card?.channel),
    card?.when ? ago(card.when) : ""].filter(Boolean).join(" · ");
  const rep = reportOf(doc), r = rep ? readReport(rep.Body) : null;
  const found = r?.summary || String(did ?? card?.summary ?? "").trim();
  const drawAgent = agent === true || (agent === "auto" && (found || state || extra));
  // WHOSE TURN: yours when your step follows, the agent's while it works, theirs while you wait on them
  const whose = turn || (tail ? "you" : card?.lane === "working" ? "agent" : card?.lane === "theirs" ? "asker" : null);
  const lit = (who) => (!whose ? "" : whose === who ? " on" : " off");
  return (
    <div className="tq-story">
      {asker && said && (
        <div className="tq-thr">{(drawAgent || tail) && <span className={`tq-thr-rail${drawAgent ? "" : " tail"}`} />}
          <span className={`tq-av ${own ? "tq-av-you" : "tq-av-asker"}${lit("asker")}`}>{TASK_GLYPH}</span>
          <div className="tq-thr-body"><div className="tq-thr-h"><b>{who}</b>{advisor ? " raised · " : own || by === null ? " · " : ["fyi", "report"].includes(card?.lane) || card?.kind === "fyi" ? " wrote · " : " asked · "}{from}</div><div className="tq-thr-say">{said}</div>
            {showSubject && <div className="tq-thr-subject">{subject}</div>}
            {rest && <div className="tq-thr-rest">{rest}</div>}{words}</div>
        </div>
      )}
      {drawAgent && (
        <div className="tq-thr">{tail && <span className="tq-thr-rail tail" />}
          <span className={`tq-av tq-av-agent${found || state ? "" : " none"}${lit("agent")}`}>{CODE_GLYPH}</span>
          <div className="tq-thr-body">
            <div className="tq-thr-h"><b>{found || state ? agentLabel(card, name) : "No agent yet"}</b>{state ? ` · ${state}` : ""}</div>
            {found ? <div className="tq-thr-did">{found}</div> : !state && <div className="tq-thr-did muted">Nobody is working on this.</div>}
            {/* ONE account of the work (the owner, 2026-09-28: "the agent part has 3 parts? ... combine them"): what it found
                is the text; what it did follows as one line; its verdict only when it is a short decision the summary
                does not already say ("accept") - most verdicts restated the summary word for word */}
            {(r?.actions || shortVerdict(r)) && (
              <div className="tq-thr-more">
                {r.actions && <><b>It did:</b> {r.actions}</>}
                {shortVerdict(r) && <>{r.actions ? " " : ""}<b>Verdict:</b> {shortVerdict(r)}</>}
              </div>
            )}
            {/* ...what it last said only when it filed no report - the report already says it, and the card has to fit
                one screen (the owner, 2026-09-28: "it's too big to see in one screen") */}
            {!r?.summary && extra}
            {r?.text && <button type="button" className="tq-card-more" onClick={() => setOpen((o) => !o)}>{open ? "Hide its report" : "Its full report"}</button>}
            {open && r?.text && <div className="tq-card-full">{looksMd(r.text) ? <Md text={r.text} /> : r.text}</div>}
          </div>
        </div>
      )}
    </div>
  );
}

// the one framed block on a card: what you decide, and the button that does it. tone "alert" when something outside
// (GitHub, a limit) stands in the way - the only place a card shouts
// ...and it is the THREAD'S LAST STEP, not a framed box (the owner, 2026-09-28: "over designed ... it should not stand
// out that much ... the logo for your move should stand out"): your avatar on the same line, lit because the turn is
// yours, the header like every step's ("You · start it"), then what to decide and the button
export function YourMove({ title, tone, go, then, children }) {
  // THE MOVE STAYS ON THE PIECE IT ACTS ON (the owner, 2026-10-06: "any button that relates to a piece of a task ... put the button
  // right there, if related to task in general then put button on bottom"): sending this draft, closing out this pull request,
  // answering this agent are drawn here, under what they act on; the row under the chat keeps the task's own verbs. It used to be
  // read into the row (2026-09-30: "everything should be on the bottom").
  const rowed = false;
  return (
    <div className={`tq-thr tq-move${tone === "alert" ? " alert" : ""}`}>
      <span className="tq-av tq-av-you on">You</span>
      {/* NO WORDS BESIDE THE CIRCLE (the owner, 2026-09-28: "don't need these words. the you circle says it. just the
          button move it up"): what there is to read first, then the button - on the circle's line when there is nothing */}
      <div className="tq-thr-body" title={title ? `You - ${title}` : undefined}>
        {children}
        {((go && !rowed) || then) && <div className={`tq-move-go${React.Children.toArray(children).some(Boolean) ? "" : " first"}`}>{!rowed && go}{then && <span className="tq-move-then">{then}</span>}</div>}
      </div>
    </div>
  );
}
// the move's own button: the card's main verb, larger, in the move's ink
const moveSx = { ...primary, fontWeight: 600, fontSize: 12.5, px: 1.5, py: 0.55, "&.Mui-disabled": { color: "#fff", background: "#b9c2bd" } };
const alertSx = { ...moveSx, background: ALERT, "&:hover": { background: ALERT_INK } };

// MORE ONLY WHEN THERE IS MORE (the owner, 2026-09-23: "the less button when there is only one line
// don't show"). The box shows the opening; the toggle appears only if the text is actually cut off -
// measured, since the text arrives after the card draws - and the fade only then too.
export function Clamp({ children, what = "the whole message" }) {
  const [open, setOpen] = useState(false);
  const [over, setOver] = useState(false);
  const ref = useRef(null);
  useEffect(() => {
    const el = ref.current;
    if (!el || open) return undefined;
    const check = () => { const box = el.querySelector(".tq-card-full") || el; setOver(box.scrollHeight > box.clientHeight + 4); };
    check();
    const ro = new ResizeObserver(check); ro.observe(el);
    const mo = new MutationObserver(check); mo.observe(el, { childList: true, subtree: true, characterData: true });
    return () => { ro.disconnect(); mo.disconnect(); };
  }, [open]);
  return <>
    <div ref={ref} className={open ? "" : `tq-card-clamp${over ? " over" : ""}`}>{children}</div>
    {(over || open) && <button type="button" className="tq-card-more" onClick={() => setOpen((v) => !v)}>{open ? "Less" : `More - ${what}`}</button>}
  </>;
}

// THE STEP NOTHING ELSE TAKES. Sending a reply, an agent finishing and pressing Next all leave the
// task open (the owner, 2026-09-15: "We need button for Completed inline with the chat"). One road:
// the same task.complete the spoken "close it" takes. Since 2026-09-23 it is a word on the card's
// Also line rather than a button of its own on every card.
function useClose(card, onDone) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const run = async () => {
    setBusy(true); setErr("");
    try { await runOperation(api, "task.complete", card.tid); onDone?.(`${card.ref || "The task"} is closed.`); }
    catch (e) { setErr(failOf(e)); setBusy(false); }
  };
  return { run, busy, err };
}

// the card's foot: what the verb does, the verb and Next, the link out, and the Also line. `covers`
// names the conversation verbs the card's own button already is, so a word is never offered twice.
// `promote` lifts one conversation word into the verb's place when the card has no button of its own
// for it - the word stays the one road (2026-09-07: "only one place"), it just stands first.
// `extra` adds a card's own words (a road the conversation has no word for); `inline` keeps them on the
// quiet line - the set-up walk's Back / Start over / Finish move you, they are not actions on a thing.
// Everywhere else they sit behind ONE "More actions", opened in place - six underlined words under
// every card read as a second row of buttons (the owner, 2026-09-23: "maybe a more actions button as
// it's confusing").
// the task page's own actions, reached from a card (the owner, 2026-09-28: "whatever actions you can do in tasks should
// have those buttons ... it can be in more") - each opens the task with that dialog up
// the task page's own acts, by their buttons.json verbs - the same words the task page draws
const TASK_ACTS = [["not_a_task", "remove"], ["handoff", "forward"], ["reshape", "split"]].map(([act, v]) => [act, btn(v), btnHint(v)]);

export function Foot({ verb, then, where, covers = [], close, onDone, more, promote, extra = [], inline = false, openTask, taskId }) {
  const nav = React.useContext(CardNav);
  const shut = useClose(close || {}, onDone);
  const [open, setOpen] = useState(false);
  const lifted = !verb && promote ? (nav.also || []).find((a) => a.verb === promote) : null;
  const also = [...(nav.also || []).filter((a) => !covers.includes(a.verb) && a !== lifted), ...extra];
  // a reply still unsent behind the card is dismissed by closing - the button says so (the owner, 2026-09-24)
  const unsent = !!(close?.draft || close?.reply_pending);
  const words = [...also, ...(close?.tid && !also.some((a) => a.verb === "close")
    ? [{ verb: "close", label: shut.busy ? "Closing…" : btn("close"),
         title: unsent ? `${btnHint("close")} - the drafted reply is not sent; it stays on the task` : btnHint("close"),
         onClick: shut.run, disabled: shut.busy }] : []),
    ...((close?.tid || taskId) && openTask ? TASK_ACTS.map(([act, label, title]) => ({ verb: `task:${act}`, label, title, onClick: () => openTask(close?.tid || taskId, { act }) })) : [])];
  // THE ROW ABOVE THE CHAT LINE (layout B, 2026-09-30): Next and the card's other words ride there, in the one place every item
  // keeps them; the card keeps its own move. The same handlers - a word's click still gets the element it was pressed on.
  const rowed = !!nav.row;
  // The first three of the card's own words stand in the row (a report's Put it on my list, Send to agent); the rest - and Mark done and
  // the task page's acts - sit behind More. The card's own move (its Foot `verb`) stays in the card.
  const asVerb = (a, group) => ({ id: `w:${a.verb || a.label}`, group, tone: "s", label: a.label, title: a.title, disabled: a.disabled,
    run: (e, anchor) => a.onClick?.({ currentTarget: anchor || e?.currentTarget }) });
  useVerbs("foot", rowed ? [
    ...(nav.onNext ? [{ id: "next", group: "next", label: btn("next"), disabled: nav.busy, run: () => nav.onNext(), title: btnHint("next") }] : []),
    // a Foot's move acts on the WHOLE item on the table - a batch's "All read, next", a report's, a message's - so it rides the row with
    // the task's verbs (the owner, 2026-10-06: "all read next should be on bottom no as it relates to the whole lot?"); what acts on a
    // PIECE of it (a draft under a task, YourMove's send) stays on the piece. Mark done is never behind More.
    ...movesOf(verb, "decide", "v"),
    ...(lifted ? [{ ...asVerb(lifted, "decide"), tone: "p" }] : []),
    ...words.map((a, i) => asVerb(a, i < 3 || a.verb === "close" ? "decide" : "more")),
  ] : null, rowed, nav.ref);
  return (
    <>
      {then && <div className="tq-card-then">{then}</div>}
      <div className="tq-card-actions">
        {!rowed && (verb || (lifted && <Button size="small" variant="contained" disableElevation disabled={lifted.disabled} onClick={lifted.onClick} title={lifted.title} sx={primary}>{lifted.label}</Button>))}
        {nav.onNext && !rowed && <Button size="small" variant="outlined" disabled={nav.busy} onClick={nav.onNext} sx={quiet}>{btn("next")}</Button>}
        {more}
        {!inline && !rowed && !!words.length && (
          <Button size="small" onClick={() => setOpen((o) => !o)} sx={faint} aria-expanded={open}>
            {open ? "Fewer actions ▴" : "More actions ▾"}</Button>
        )}
        <span className="sp" />
        {where}
      </div>
      {inline && !rowed && !!words.length && (
        <div className="tq-card-also">{words.map((a) => (
          <button key={a.verb || a.label} type="button" title={a.title || undefined} disabled={a.disabled} onClick={a.onClick}>{a.label}</button>
        ))}</div>
      )}
      {!inline && !rowed && open && (
        <div className="tq-card-actions tq-card-more-actions">{words.map((a) => (
          <Button key={a.verb || a.label} size="small" variant="outlined" title={a.title || undefined} disabled={a.disabled} onClick={a.onClick} sx={quiet}>{a.label}</Button>
        ))}</div>
      )}
      <CardErr err={shut.err} />
    </>
  );
}

// AN ADVISOR IDEA made into a task: its text IS the task's summary, so the box repeated the lead word for
// word (the owner, 2026-09-23: "what is the gray part doing? sounds like a repeat. maybe where it got it
// from?"). What the lead does not say is WHY the Advisor raised it - the `why:` line every idea carries
// (assistant._idea_message) - so that is the box, said as whose reason it is.
function AdvisorWhy({ mid }) {
  const [why, setWhy] = useState(null);
  useEffect(() => {
    let live = true;
    if (mid == null || mid === "") { setWhy(""); return () => { live = false; }; }   // no mail behind it: ask for nothing
    api.get(`/api/messages/${mid}`).then(({ data }) => {
      if (!live) return;
      const body = cleanText(data?.BodyText || "");
      const at = body.search(/\n\s*why:\s*/i);
      setWhy(at >= 0 ? body.slice(at).replace(/^\s*why:\s*/i, "").trim() : "");
    }).catch(() => live && setWhy(""));
    return () => { live = false; };
  }, [mid]);
  if (!why) return null;
  return <div className="tq-card-excerpt"><b>Why the Advisor raised it:</b> {why}</div>;
}

// the whole text, unfolded under the card on request - a report as markdown, a mail as it was written
const cell = (v) => (v == null ? "" : typeof v === "number" ? v.toLocaleString() : String(v));
function RowsTable({ rows }) {
  const cols = [...new Set(rows.flatMap((r) => Object.keys(r)))];
  return (
    <table className="tq-rows">
      <thead><tr>{cols.map((c) => <th key={c}>{c.replace(/_/g, " ")}</th>)}</tr></thead>
      <tbody>{rows.map((r, i) => <tr key={i}>{cols.map((c) => <td key={c} className={typeof r[c] === "number" ? "n" : ""}>{cell(r[c])}</td>)}</tr>)}</tbody>
    </table>
  );
}

function FullText({ mid, revision }) {
  // a card with no mail behind it asks for nothing. A task whose only message a skip rule hid has no
  // mid, and fetching /api/messages/null painted FastAPI's own validation sentence ("path.mid: Input
  // should be a valid integer") into the card (the owner, 2026-09-15).
  const none = mid == null || mid === "";
  const got = useFetched(none ? null : `/api/messages/${mid}`, revision);
  const doc = none ? { error: "" } : got;
  const [whole, setWhole] = useState(false);
  if (!doc) return <div className="tq-card-full">…</div>;
  if (doc.error) return <div className="tq-card-err">{doc.error}</div>;
  // what they WROTE (ReadText: no chain, signature, legal footer or banner); the whole email on request
  const raw = cleanText(doc.BodyText || "");
  const read = doc.ReadText != null ? cleanText(doc.ReadText) : raw;
  const body = whole ? raw : read;
  const cut = body.indexOf("\n--- raw data ---");
  const text = noImages(cut >= 0 ? body.slice(0, cut) : body);
  const morning = doc.SourceName === "Morning digest" || /^Morning digest\b/i.test(doc.Subject || "");
  return (
    <div className="tq-card-full">
      {morning ? <DigestText text={text} sourceId={/^report:(\d+)/.exec(doc.ConversationId || "")?.[1] ?? null} /> : jsonRows(text) ? <RowsTable rows={jsonRows(text)} /> : looksMd(text) ? <Md text={text} /> : (text || "(empty)")}
      {/* ...and the pictures pasted into it, drawn - the screenshot is often the whole ask */}
      {!none && !morning && <Attachments messageId={mid} canFetch={String(doc.Channel || "") === "email" && mentionsPicture(doc.BodyText)} dense />}
      {read !== raw && <button type="button" className="tq-card-more" onClick={() => setWhole((v) => !v)}>{whole ? "Just what they wrote" : "Show the whole email"}</button>}
      {doc.SourceLink && <div className="tq-card-note"><a href={doc.SourceLink} target="_blank" rel="noreferrer" style={{ color: "#55697a" }}>open the original</a></div>}
    </div>
  );
}

// A task is the grouping boundary after triage. Fetching `/thread` here would pull the whole Teams
// or WhatsApp room (and made TQ-0367 say +19); task detail tells us exactly which messages triage
// combined. Context rows helped triage decide, but are not part of the grouped ask shown to the owner.
// `list={false}` on the walk's cards: the checklist and the task's history live on the Tasks tab, and
// the card links there rather than repeating them (the owner, 2026-09-23)
// A PASTED PICTURE IS DRAWN, ITS REFERENCE IS NOT (the owner, 2026-09-28: "images inline of the email are not coming
// through"): the body only carries "[image: ...]" / cid: stand-ins that render as nothing - the picture itself comes
// from the message's attachments (Attachments, under the message), so the stand-ins are what goes
// "look for attachments on this mail" only where the body points at a picture that is not here yet - on every message it
// was a line of noise under mail that never had one
export const noImages = (text) => String(text || "")
  .replace(/!\[[^\]]*\]\([^)]*\)/g, "")
  .replace(/<img\b[^>]*>/gi, "")
  .replace(/\[(?:image|cid|inline image)[^\]]*\]/gi, "")
  .replace(/\n{3,}/g, "\n\n");

function CombinedTaskText({ card, list = true }) {
  // the TASK is the identity - which of its messages the item happens to name does not change what the
  // task bundles, so a moved mid neither blanks nor refetches it; a newer presentation refreshes quietly
  const doc = useFetched(card?.tid ? `/api/tasks/${card.tid}` : null, card?.presentation_revision);
  if (!card?.tid) return <FullText mid={card?.mid} revision={card?.presentation_revision} />;
  if (!doc) return <div className="tq-card-full">…</div>;
  if (doc.error) return <div className="tq-card-err">{doc.error}</div>;
  // NEWEST FIRST (the owner, 2026-09-28): the latest word is what the card is about; the thread reads back from it
  const messages = (doc.messages || []).filter((m) => String(m.Status || "") !== "context")
    .slice().sort((a, b) => String(b.SentAt || "").localeCompare(String(a.SentAt || "")));
  // The job is the reason this card exists, so it sits above the source thread as a todo rather than
  // disappearing into the thread's pale metadata. The list is read-only here; ticking stays on the task.
  const taskText = String(doc.task?.Summary || doc.task?.Title || card.title || "").trim();
  const progress = progressLine(doc.checklist);
  // THE LIST IS THE TASK when there is one. This said the job twice - a bold summary, then a
  // checklist item repeating it - under a header checkbox that ticked nothing and belonged to
  // nothing (the owner, 2026-09-11: "seems duplicated... boxes should be for specific items in
  // the task list"). A box now means exactly one thing: an item you can tick. The summary stands
  // in only when there are no items, so a card with no list still says what the job is.
  const storedItems = doc.checklist || [];
  const ownTask = messages.length === 1 && messages[0]?.Channel === "own";
  // A task created from the Assistant used to have no checklist at all. Give the older records the
  // same one-item list shape as newly created ones without inventing a second copy of their words.
  const items = storedItems.length ? storedItems : (ownTask && taskText
    ? [{ id: "task", text: taskText, done: false, displayOnly: true }] : []);
  const task = list && (taskText || items.length) ? (
    <div className="tq-task-focus" role="group" aria-label="Task to do">
      <div className="tq-task-focus-label">{items.length ? "Task list" : "Task"}
        {progress && <em>{progress}</em>}
      </div>
      {!items.length && taskText && <div className="tq-task-focus-text">{taskText}</div>}
      {!!items.length && <div className="tq-task-focus-list">
        {items.map((item, n) => (
          <div className={`tq-task-focus-item${item.done ? " done" : ""}`} key={item.id || n}>
            <span className="tq-task-box" aria-hidden="true">{item.done ? "✓" : ""}</span>
            <span>{item.text}</span>
          </div>
        ))}
      </div>}
    </div>
  ) : null;
  const onlyBody = cleanText(messages[0]?.BodyText || "").toLocaleLowerCase();
  const taskWords = cleanText(taskText).toLocaleLowerCase();
  // An `own` source message is the receipt for creating the task. When its body is exactly the task
  // text, showing it beneath the task list says the same sentence a third time and adds no context.
  // ...and the lead now says the task's summary, so a lone message that IS that summary (a task made by
  // hand, an Advisor idea) is the same words twice, whatever its channel (the owner, 2026-09-23: "2
  // sections?"). Same = equal, or one opens with the other's first 80 characters.
  const sameWords = (a, b) => !!a && !!b && (a === b || a.startsWith(b.slice(0, 80)) || b.startsWith(a.slice(0, 80)));
  const repeatReceipt = messages.length === 1 && sameWords(onlyBody, taskWords);
  if (messages.length <= 1) return <>{task}{!repeatReceipt && <FullText mid={card?.mid} revision={card?.presentation_revision} />}</>;
  return <>
    {task}
    <div className="tq-card-full tq-card-context">
      <div className="tq-card-note" style={{ marginBottom: 7, fontWeight: 600 }}>
        Email context · {messages.length} messages read together
      </div>
      {messages.map((m, n) => {
        const body = noImages(cleanText(m.ReadText ?? m.BodyText ?? ""));
        return (
          <div key={m.MessageId || n} style={{ padding: "7px 0", borderTop: n ? "1px solid #e2ddd4" : 0 }}>
            <div className="tq-card-note" style={{ marginBottom: 3 }}>
              {m.Direction === "out" ? "You" : (m.FromName || m.FromEmail || "Someone")}{m.SentAt ? ` · ${fmtDateTime(m.SentAt)}` : ""}
            </div>
            {looksMd(body) ? <Md text={body} /> : (body || "(empty)")}
            {m.MessageId && <Attachments messageId={m.MessageId} canFetch={String(m.Channel || "") === "email" && mentionsPicture(m.BodyText)} dense />}
          </div>
        );
      })}
    </div>
  </>;
}

// what every card shares: where it came from (logo, lane dot, two words, when), then who wants what.
// The lane colours the DOT only - never an edge or a wash (the owner's taste: colour identifies).
export function CardShell({ card, kicker, title, lead, sub, children, err }) {
  const meta = laneMeta(card?.lane);
  const when = card?.when ? ago(card.when) : "";
  return (
    <div className="tq-card">
      <div className="tq-card-kicker"><span className="src"><SourceMark item={card} /></span><span className="dot" style={{ background: edge(card?.lane) }} />{kicker || meta.word}
        {when && <em>{when}</em>}</div>
      {lead || (typeof title === "string" ? <Lead text={title} who={card?.who} /> : title && <div className="tq-card-lead">{title}</div>)}
      {sub && <div className="tq-card-sub">{sub}</div>}
      {/* why it is BACK. Clearing a task never closed it, so the work tab raises it again once it has
          been quiet - and the card has to say that itself, or the only answer is "why am I seeing this
          again?" (the owner, 2026-09-15: "if they ask why explain it should be closed") */}
      {card?.why_open && <div className="tq-card-sub">{card.why_open}</div>}
      {children}
      <CardErr err={err} />
    </div>
  );
}

// how the reply leaves: "emails" said of a WhatsApp answer told the owner it would go somewhere it would not
const SENDS_ON = { whatsapp: "on WhatsApp", teams: "in Teams", slack: "in Slack", telegram: "on Telegram", sms: "by text",
  github: "on GitHub", discord: "on Discord", google_chat: "in Google Chat" };
export const sendsBy = (channel, who) => { const on = SENDS_ON[String(channel || "").toLowerCase()]; return on ? `answers ${who} ${on}` : `emails ${who}`; };

// a reply drafted, or an action proposed - the owner's yes is the only thing that moves it
export function ReplyCard({ card, onDone, onSent, onOpenTask, onTimeline }) {
  const caps = useCapabilities();                     // can a draft leave: its channel asked here, and its row (draftCanSend)
  const [rv, setRv] = useState(null);
  const [text, setText] = useState(null);
  const [busy, setBusy] = useState("");
  const [err, setErr] = useState("");
  // A draft on a grouped task must open with the whole grouped ask visible. Otherwise the owner is
  // asked to approve an answer against only the latest of seven messages.
  // ...and now it is: the lead says who wants what in triage's words, so what they wrote folds
  // behind More and the draft is the thing in the open (2026-09-23)
  const [full, setFull] = useState(false);
  const nav = React.useContext(CardNav);
  // the reply waiting beside a close-out: the two are ONE decision here, as on the task page - the merge first,
  // then this reply goes out (the owner, 2026-09-27)
  const [mate, setMate] = useState(null);
  const [coRv, setCoRv] = useState(null);
  useEffect(() => {
    let live = true;
    api.get("/api/reviews", { params: { status: "pending" } }).then(({ data }) => {
      if (!live) return;
      setRv((data.data || []).find((x) => x.ReviewId === card.rid) || { gone: true });
      const found = (data.data || []).find((x) => x.ReviewId === card.rid);
      setMate(found && closeoutOf(found) ? (data.data || []).find((x) => x.TaskId === found.TaskId && x.Kind !== "action"
        && (draftCanSend(caps, x) || String(x.Channel || "").toLowerCase() === "github")) || null : null);   // the close-out carries a GitHub comment
      // the task's close-out, whichever card is on the table - the reply's card reads GitHub's state through it too
      setCoRv(found && closeoutOf(found) ? found : found ? (data.data || []).find((x) => x.TaskId === found.TaskId && closeoutOf(x)) || null : null);
    }).catch((e) => live && setErr(failOf(e)));
    return () => { live = false; };
  }, [card.rid, card.mid, card.presentation_revision]);
  // A REPLY OPENED AT ONCE is drawn before its draft exists (replyDraft.js): "Drafting…" until it lands, then it fills the box;
  // a draft that could not be written says why here
  const job = useDraftJob(card.rid);
  const drafting = job?.state === "drafting";
  useEffect(() => {
    if (job?.state === "done") setRv((r) => (r && !r.gone ? { ...r, DraftText: job.draft, HasDraft: job.draft ? 1 : 0, DraftError: null } : r));
    if (job?.state === "failed") setErr(`The draft could not be written - ${job.error}. Write it here, or Draft with AI again.`);
  }, [job]);
  const action = rv?.Kind === "action";
  const co = closeoutOf(rv);
  // THE CARD READS GITHUB FIRST (closeoutState.js): Close out is live only when this repo's rules let it merge now
  const { gh, reload: reloadGh, act } = useCloseoutState(coRv?.ReviewId);
  const blocked = !!gh && !gh.ok;
  const cop = co || closeoutOf(coRv);
  const draft = () => {
    if (mate) return mate.DraftText || "";
    if (!action) return rv?.DraftText || "";
    if (co) return reviewText(rv);
    try { const p = JSON.parse(rv.DraftText || ""); return p.text || `${p.action}${p.why ? ` — ${p.why}` : ""}`; } catch { return rv?.DraftText || ""; }
  };
  const value = text ?? draft();
  const stale = !!(rv?.Stale ?? card.stale);          // a raw review row's Stale is 0, which React would draw
  // a GitHub author is their login - their "address" is GitHub's own noreply mailbox, which nobody reads
  const onGithub = String(rv?.Channel || "").toLowerCase() === "github";
  const who = rv ? (rv.FromName && rv.FromEmail && !onGithub ? `${rv.FromName} <${rv.FromEmail}>` : rv.FromName || rv.FromEmail || "them") : "";
  const decide = async (verb) => {
    setBusy(verb); setErr("");
    try {
      // Decline and Close out anyway belong to the close-out, whichever card is showing; the reply rides with them
      const onCo = ["close_pr", "merge_anyway"].includes(verb) && coRv ? coRv.ReviewId : card.rid;
      const withReply = mate || (onCo !== card.rid && !action);
      const { data } = await api.post(`/api/reviews/${onCo}/decide`, withReply
        ? { verb, final_text: null, note: null, reply_text: verb !== "reject" ? value : null }
        : { verb, final_text: verb === "approve" ? value : null, note: null });
      if (data.refused) reloadGh();
      if (data.send_error) throw new Error(data.send_error);
      const sentTo = mate && verb !== "reject" ? ` The reply went to ${mate.FromName || "them"}.` : "";
      const yes = verb === "approve" || verb === "merge_anyway", ran = yes || verb === co?.alt?.verb;
      const said = verb === co?.alt?.verb ? `Done — ${co.alt.then}.${sentTo}` : yes ? (co ? `Done — ${co.then}.${sentTo}` : action ? "Done — the action ran." : `Sent to ${who}.`)
        : co ? "Not yet — the task stays open." : action ? "Dismissed — nothing ran." : "Dismissed — no reply goes out.";
      // SENDING AND CLOSING ARE TWO STEPS (the owner, 2026-10-18): a send, or an Approve that ran, leaves the item on the table with
      // its receipt - Mark done and Next on its row - where it used to settle the item and walk on as if the task were finished
      if (ran && onSent) onSent(said, card.tid, card.ref);
      else onDone?.(said);
    } catch (e) { setErr(failOf(e)); }
    setBusy("");
  };
  const redraft = async () => {
    setBusy("redraft"); setErr("");
    try { const { data } = await api.post(`/api/reviews/${card.rid}/draft`); setRv((r) => ({ ...r, DraftText: data.draft, Stale: false })); setText(null); }
    catch (e) { setErr(failOf(e)); }
    setBusy("");
  };
  // SEND IT BACK TO THE AGENT (the owner, 2026-09-28: "don't see button to send back to agent?"): the one road every
  // agent continues down (/continue-work), your words the first thing it hears. When GitHub refuses the close-out, the
  // refusal IS the note - the agent is told what to fix, and the card comes back when it stops.
  const [back, setBack] = useState(null);
  const sendBack = async (note) => {
    setBusy("back"); setErr("");
    try {
      await api.post(`/api/tasks/${card.tid}/continue-work`, { note: note || null });
      onDone?.(`Sent back to ${card.agent || "the agent"}${note ? `: “${note.slice(0, 80)}”` : ""}. It comes back here when it stops.`);
    } catch (e) { setErr(failOf(e)); }
    setBusy("");
  };
  const conflict = blocked && gh?.state === "dirty" && !!card.tid;
  const finish = async () => {
    if (busy || !card.tid) return;
    setBusy("finish"); setErr("");
    try {
      await runOperation(api, "task.complete", card.tid);
      onDone?.(`${card.ref || "The task"} marked done. No reply was sent.`);
    } catch (e) { setErr(failOf(e)); }
    finally { setBusy(""); }
  };
  if (rv?.gone) return <CardShell card={card} kicker="already handled" title={card.title} sub="This one is no longer waiting on you." />;
  const goSx = conflict || (co && blocked) ? alertSx : moveSx;
  const verb = conflict
    ? <Button size="small" variant="contained" disableElevation disabled={!!busy} onClick={() => sendBack(`The merge was refused: ${gh.reason.split(" - ")[0]}. Resolve that on the pull request and push; the owner approves it once it is clean.`)} sx={goSx}>
        {busy === "back" ? "Sending…" : btn("continue")}</Button>
    : action
    ? <Button size="small" variant="contained" disableElevation disabled={!!busy || !rv || (co && blocked)} title={co && blocked ? gh.reason : btnHint("approve", "action")} startIcon={<DoneRoundedIcon />} onClick={() => decide("approve")} sx={goSx}>{busy === "approve" ? (co ? co.busy : "Running…") : btn("approve", "action")}</Button>
    : rv && !draftCanSend(caps, rv) && !card.closeout ? null : rv && !value.trim() && !stale ? (
      /* NOTHING TO SEND YET: a disabled Send was the only button, and the redraft word it covers was
         hidden as its duplicate - no way to get a draft from the card at all (2026-09-23) */
      <Button size="small" variant="contained" disableElevation disabled={!!busy || drafting} startIcon={<RefreshRoundedIcon />}
        onClick={redraft} sx={goSx}>{busy === "redraft" || drafting ? "Drafting…" : btn("redraft", "none")}</Button>
    ) : stale ? (
      /* the road out of the warning, on the card that carries it: a stale draft disabled the
         only button here and named no way forward (the owner, 2026-09-21: "just reprocess it
         then"). Refreshing is the primary action while the thread is ahead of the draft. */
      <Button size="small" variant="contained" disableElevation disabled={!!busy || !rv}
        startIcon={<RefreshRoundedIcon />} onClick={redraft} sx={goSx}
        title={btnHint("redraft")}>
        {busy === "redraft" ? "Drafting…" : btn("redraft")}</Button>
    ) : (
      <Button size="small" variant="contained" disableElevation disabled={!!busy || !rv || !value.trim() || blocked} title={blocked ? gh.reason : undefined} startIcon={<SendRoundedIcon />} onClick={() => decide("approve")} sx={goSx}>
        {busy === "approve" ? "Sending…" : btn("approve")}</Button>
    );
  const then = conflict ? <>tells it to resolve the conflicts and push; this card comes back when it stops, and nothing is merged or sent until then.</>
    : co ? <>{co.then}{mate ? <>, then the reply above {sendsBy(mate.Channel, mate.FromName || "them")}</> : null}.</>
    : action ? <>does what the agent proposed - nothing runs until you press it.</>
    : rv && !value.trim() && !stale ? <>writes one for you to approve here - nothing is sent.</>
    : stale ? <>rewrites it from the newest message; you still approve it.</>
    : rv && card.closeout ? <>{card.closeout}, then the reply above {sendsBy(rv.Channel, who)}.</>
    : rv ? <>{sendsBy(rv.Channel, who)}{card.tid ? ` - the task stays open until you ${btn("close")}` : ""}.</> : null;
  // YOUR MOVE, named: what the block decides, in its own words (the canvas's A+B, the owner 2026-09-28)
  const replyTo = String(mate ? mate.FromName || "them" : who).replace(/\s*<[^>]*>/g, "");
  const stopped = conflict || ((co || card.tid) && blocked);
  const moveTitle = stopped ? "GitHub won't merge it yet" : action && !co ? "run what the agent proposed" : co ? "close out"
    : rv && !value.trim() && !stale ? "no reply drafted yet" : stale ? "the thread moved on" : `reply to ${replyTo}`;
  const via = SENDS_ON[String(mate?.Channel || rv?.Channel || "").toLowerCase()] || "by email";
  return (
    <CardShell card={card} kicker={(co || card.tid) && blocked ? "can't close out yet" : co || (card.tid && value.trim()) ? READY : action ? "an agent asks to act" : value.trim() ? "reply · draft ready" : "reply · no draft yet"}
      lead={action && !co ? <Lead text={rv?.Subject || card.title} /> : <Story card={card} state={card.summary ? "finished" : undefined} fallback={rv?.Subject} tail />} err={err}>
      <YourMove title={moveTitle} tone={stopped ? "alert" : null} go={verb} then={then}>
        {/* what GitHub says about this pull request now - why Close out is off, or the red it will merge past */}
        {gh && blocked && <div className="tq-move-say">{capital(gh.reason)}.</div>}
        {/* WHAT THE BOX IS (the owner, 2026-09-28: "what does the words mean?"): the reply, to whom, and when it goes */}
        {rv && (!action || mate) && <div className="tq-move-to">{`Your reply to ${replyTo} ${via} - it goes when you press ${btn("approve", action ? "action" : undefined)}${stopped ? ", once it can merge" : ""}. Edit it here first if you like.`}</div>}
        {rv && (
          <TextField fullWidth multiline minRows={2} maxRows={9} value={value} onChange={(e) => setText(e.target.value)}
            placeholder={drafting ? "Drafting…" : action && !mate ? "" : "Write your answer here"}
            sx={{ mt: 0.75, "& .MuiOutlinedInput-root": { background: "#fffdf9" }, "& textarea": { fontSize: 13.5, lineHeight: 1.55 } }} />
        )}
        {!action && stale && <div className="tq-card-err">{`New messages arrived after this draft. Press ${btn("redraft")} to write it from the latest message before sending.`}</div>}
        {!action && rv && drafting && !value.trim() && <div className="tq-card-excerpt">Drafting… it fills in here when the AI is done - or write it yourself.</div>}
        {!action && rv && !drafting && draftState({ ...rv, HasDraft: value.trim() ? 1 : 0 }).line && <div className={draftState(rv).state === "failed" ? "tq-card-err" : "tq-card-excerpt"}>{draftState({ ...rv, HasDraft: value.trim() ? 1 : 0 }).line}</div>}
        {!action && !card.closeout && sendBlockLine(rv) && <div className="tq-card-excerpt">{sendBlockLine(rv)}</div>}
        {gh && !blocked && gh.note && <div className="tq-card-excerpt">{capital(gh.note)}.</div>}
      </YourMove>
      {/* WHAT YOU ARE ANSWERING, said to be that (the owner, 2026-09-14: "though you need to see what
          you are responding to") - one press away, under the move */}
      {card.mid && <button type="button" className="tq-card-more" onClick={() => setFull((v) => !v)}>{full ? "Less" : "More - what they wrote"}</button>}
      {full && card.mid && <CombinedTaskText card={card} list={false} />}
      {back !== null && (
        <div style={{ display: "flex", gap: 8, alignItems: "flex-start", marginTop: 8 }}>
          <TextField fullWidth multiline minRows={1} maxRows={4} autoFocus value={back} onChange={(e) => setBack(e.target.value)}
            placeholder={`What should ${card.agent || "the agent"} change?`} sx={{ "& textarea": { fontSize: 12.5 } }} />
          <Button size="small" variant="outlined" disabled={!!busy || !back.trim()} onClick={() => sendBack(back.trim())} sx={quiet}>
            {busy === "back" ? "Sending…" : btn("continue")}</Button>
        </div>
      )}
      {/* "Mark done" arrives as a conversation word; off the walk (no words), the same road is still offered
          under More actions */}
      <Foot covers={["approve", "redraft"]} taskId={card.tid} openTask={onOpenTask}
        extra={[...(gh?.offers || []).map((o) => ({ verb: o, label: busy === o ? "…" : OFFER_LABEL[o], title: OFFER_HINT[o], disabled: !!busy || !rv,
          onClick: async () => {
            if (o === "anyway") return decide("merge_anyway");
            setBusy(o); setErr("");
            try { const said = await act(o); onDone?.(`${said}. Press ${btn("approve", "action")} again once the checks pass.`); } catch (e) { setErr(failOf(e)); }
            setBusy("");
          } })),
          ...(cop?.alt ? [{ verb: cop.alt.verb, label: busy === cop.alt.verb ? cop.alt.busy : cop.alt.label, title: `${cop.alt.label} ${cop.alt.then}.`,
          disabled: !!busy || !rv, onClick: () => decide(cop.alt.verb) }] : []),
        // a draft's choices are Close out, Redraft or Mark done (the owner, 2026-10-01: "rejected is useless - it should be redraft
        // or close task") - an empty or stale draft has its redraft as the move itself
        ...(rv && !action && !stale && value.trim() ? [{ verb: "redraft", label: busy === "redraft" ? "Drafting…" : btn("redraft"),
          title: btnHint("redraft"), disabled: !!busy, onClick: redraft }] : []),
        ...(card.tid && !conflict ? [{ verb: "back", label: btn("continue"), title: btnHint("continue"),
          disabled: !!busy, onClick: () => setBack((b) => (b === null ? "" : null)) }] : []),
        ...(card.tid && !nav.also?.length ? [{ verb: "finish", label: busy === "finish" ? "Closing…" : btn("close"),
          title: `${btnHint("close")} - the draft is dismissed, any agent still on it stops, and no reply is sent`,
          disabled: !!busy || !rv, onClick: finish }] : [])]}
        where={<Where card={card} onOpenTask={onOpenTask} onTimeline={onTimeline} />} />
    </CardShell>
  );
}

// a meeting inside two hours: when, who, what the invite says - Join when it has a link. No "Getting prepped" line: nothing on
// this card preps (the owner, 2026-10-02 - prep is the game view's and the phone's word)
export function MeetingCard({ card }) {
  const e = card.event || {};
  return (
    <CardShell card={card} kicker={`coming up · ${age(e.start)}`} title={e.subject || card.title}
      sub={[e.who?.length ? `with ${e.who.slice(0, 6).join(", ")}` : "", e.where].filter(Boolean).join(" · ")}>
      {e.about && <div className="tq-card-excerpt">{e.about}</div>}
      <Foot verb={e.join ? <Button size="small" variant="contained" disableElevation component="a" href={e.join} target="_blank" rel="noreferrer" sx={primary}>Join</Button> : null}
        then={e.join ? <><b>Join</b> opens the meeting link.</> : null} />
    </CardShell>
  );
}

// a report landed: read it here, or go to the row
export function ReportCard({ card, onOpenTask, onTimeline, onDone }) {
  // Open, like the mail card: a digest behind a "Read it" is a digest nobody reads (the owner,
  // 2026-09-04: "Same with Morning digest should be open like here is your morning digest?").
  // .tq-card-full caps at 420px and scrolls, so a long report cannot run away with the page.
  // The report reads open still, CLAMPED to its opening lines (Clamp): the headline is the lead, the
  // first lines are the box, and More - only when there is more - unfolds the rest in place (2026-09-23)
  return (
    <CardShell card={card} kicker={card.bad ? "a report failed" : "report"} title={card.title}>
      {card.bad && <div className="tq-card-excerpt">The run failed — the cause is in the report.</div>}
      {card.brief_today && <TodayMeetingsStrip />}
      {card.mid && <Clamp what="the whole report"><FullText mid={card.mid} revision={card.presentation_revision} /></Clamp>}
      {/* where its result shows is the report's routing, and a failure only ever reaches the bell (reports.run_lands) */}
      <Foot close={card} onDone={onDone} promote={card.bad ? "rerun" : null}
        then={card.bad ? "Running it again runs the report in the background - its result goes where the report sends it, and if it fails the bell says why." : null}
        where={<>
          <Where card={card} onOpenTask={onOpenTask} onTimeline={onTimeline} />
          {/* the report itself, one press away - the card was the only place it showed and it had no way back to it */}
          {card.source_id != null && <Button size="small" component="a" href={`#report=${card.source_id}`} sx={faint}>Edit this report ↗</Button>}
        </>} />
    </CardShell>
  );
}

// the assistant's own line: the slipped ask, the promise, the thread gone quiet
export function IdeaCard({ card, onOpenTask, onTimeline, onNavigate }) {
  const a = card.action || {};
  // THE REPORT PROPOSES, THE CARD HAS THE DOORS (the assistant-runs-the-app design, 2026-09-18): a
  // system to connect opens its card on the Connections tab; a health finding opens the tab that fixes
  // it. Putting it down is the chips' Not ours, the same word every idea carries (C5, 2026-09-27).
  const go = (tab, hash) => { if (hash) window.location.hash = hash; onNavigate?.(tab); };
  // THE FINDING, THEN WHOSE MOVE, THEN ANY SUGGESTION, apart (the owner, 2026-10-10): the chip is triage's verdict, the rows are
  // the Advisor's own parts, and the evidence links to the mail it came from instead of sitting in a raw box
  const mid = a.mid || card.mid, why = a.why || card.why;
  const from = mid ? <a className="tq-card-link" href={`#msg=${mid}`} onClick={(e) => { e.preventDefault(); onTimeline?.(mid); }}>{card.who ? `${card.who}'s message` : "the message"} ↗</a>
    : a.source?.label ? <span>{a.source.label}</span> : null;
  const facts = [["Whose move", a.whose], ["Suggestion", a.suggest], ["Based on", why && <>{from}{from && ": "}{why}</>]].filter(([, v]) => v);
  const chip = card.lane === "asked" ? "on you" : "not on you";
  return (
    <CardShell card={card} kicker={<>{ideaWord(card.idea_kind)}<span className="tq-card-chip">{chip}</span></>} title={card.title}>
      {facts.length > 0 && <div className="tq-card-facts">{facts.map(([k, v]) => <React.Fragment key={k}><div>{k}</div><div>{v}</div></React.Fragment>)}</div>}
      <Foot
        verb={card.idea_kind === "connect" && a.connector_type ? (
          <Button size="small" variant="contained" disableElevation sx={primary}
            onClick={() => go("Connections", `connector=${a.connector_type}`)}>{a.planned ? `See ${a.title || a.connector_type}` : `Connect ${a.title || a.connector_type}`}</Button>
        ) : card.idea_kind === "health" && a.tab ? (
          <Button size="small" variant="contained" disableElevation sx={primary} onClick={() => go(a.tab, a.hash || "")}>Open {a.tab}</Button>
        ) : null}
        then={card.idea_kind === "connect" && a.connector_type ? <><b>{a.planned ? "See" : "Connect"}</b> opens its card on Connections - nothing changes until you finish there.</>
          : card.idea_kind === "health" && a.tab ? <><b>Open {a.tab}</b> takes you to the tab that fixes it.</>
          // the buttons in the bar say what they do; the sentence that explained them is gone (2026-10-10)
          : null}
        where={<Where card={{ ...card, tid: a.tid || card.tid, mid: a.mid || card.mid }} onOpenTask={onOpenTask} onTimeline={onTimeline} />} />
    </CardShell>
  );
}

// a person wrote something: read it here, reply, hand it to an agent, or say it is not ours - and
// two doors for "not ours": one that teaches memory so it never comes back, one for just today
export function MessageCard({ card, onDone, onOpenTask, onTimeline, onSurface, onNavigate }) {
  const [busy, setBusy] = useState("");
  const [err, setErr] = useState("");
  const [repoAsk, setRepoAsk] = useState(null);
  // Shown, not offered. Clicking "Read it" to find out what a thing IS put a step in front of every
  // decision (the owner, 2026-09-04: "by default it should show the full email - not the full chain
  // ... don't want to have to click read it"). FullText fetches this ONE message, so it is the mail
  // that arrived and never the thread behind it - shown whole when it fits, clamped with More when not.
  const post = async (verb, path, body, receipt, after) => {
    setBusy(verb); setErr("");
    try { const { data } = await api.post(path, body || {}); after?.(data); if (receipt) onDone?.(typeof receipt === "function" ? receipt(data) : receipt); }
    catch (e) { setErr(failOf(e)); }
    setBusy("");
  };
  const asks = card.kind !== "fyi";
  // ...read off what is connected, like the row (concierge.chips_for): the card offered Send to coding agent with no coding tool, so the
  // card and the row disagreed and the press failed (the re-audit, 2026-10-18)
  const canCode = useCapabilities().coding;
  const suggestedKind = card.kind === "todo" && card.coding && canCode ? "coding" : "general";
  const startAgent = async (agentKind) => {
    setBusy("agent"); setErr("");
    try {
      const { data } = await api.post(`/api/messages/${card.mid}/dispatch`, {
        kind: agentKind,
      });
      if (data.dispatch === "needs_repo") {
        setRepoAsk({ taskId: data.taskId, agent: data.agent || "" });
      } else {
        setRepoAsk(null);
        const who = agentKind === "coding" ? (data.agent || "the coding agent") : (data.agent || "an agent");
        onDone?.(`${data.ref || "It"} is with ${who} now - I'll bring it back when it's done.`);
      }
    } catch (e) {
      const msg = errText(e);
      // Compatibility with an older server response when this card already knows its task.
      if (card.tid && /could not tell which checkout|no local path/i.test(msg))
        setRepoAsk({ taskId: card.tid, agent: "" });   // blank: the server finds the coding profile
      else setErr(msg);
    }
    setBusy("");
  };
  // the one immediate road for "asked you": a draft, sent only on your yes (PW-126) - its card at once, "Drafting…" until
  // the model is done (the owner, 2026-10-01: "never waits on the AI")
  const draftReply = async () => {
    setBusy("reply"); setErr("");
    try { const data = await openReply(api, card.mid); onSurface?.(data?.reviewId ? `review:${data.reviewId}` : null, "Drafting a reply…"); }
    catch (e) { setErr(failOf(e)); }
    setBusy("");
  };
  // A BROKEN CONNECTION is not a message and has no task: its row clears itself on the next good check,
  // so the card's verb is the way to FIX it - the connection's own card - and Next puts it down until the
  // error changes (2026-09-23)
  // hooks first - the connection card below returns early, and a hook after it would change the order per kind
  const doc = useFetched(card.tid ? `/api/tasks/${card.tid}` : null, card.presentation_revision);
  const shut = useClose(card, onDone);
  const [back, setBack] = useState(null);
  const [said, setSaid] = useState(card.why || "");     // a broken connection's error, as its last check said it
  const [note, setNote] = useState("");
  const [stuck, setStuck] = useState(false);          // Check again, or the restart, did not fix it
  if (card.kind === "connection") {
    // THE FIX ON THE CARD, not a trip to Connections (the row-bot comparison, 2026-10-07): most of these are a server that was down
    // for a while, and Check again is the whole repair. A Microsoft sign-out is not - that one needs the sign-in, so it leads.
    const cid = String(card.key || "").split(":")[1], signin = /signed you out/i.test(card.title || "");
    const openIt = () => { window.location.hash = `connector=${card.channel}`; onNavigate?.("Connections"); };
    const at = () => new Date().toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
    // THE ERROR IS SAID ONCE (the owner, 2026-10-15): a failed check said it again under the card, word for word. A check that
    // gets the same answer says when it looked; a different answer takes the error's place
    const check = async () => {
      setBusy("check"); setErr("");
      try {
        const { data } = await api.post(`/api/connectors/${cid}/test`);
        if (data?.ok) onDone?.(`${card.who || "The connection"} answers again - that row is gone.`);
        else {
          if (data?.detail) setSaid(data.detail);
          setNote(`Checked at ${at()} - still not answering.`); setStuck(true);
          // ...and the error you are reading NOW is the one you have seen: a changed error counts as new (its sig), so without
          // this the very next Next brought the same card straight back under its new words
          await api.post("/api/funnel/settle", { key: card.key, verb: "surfaced", read: true }).catch(() => {});
        }
      } catch (e) { setErr(failOf(e)); }
      setBusy("");
    };
    // RESTART FROM THE CARD (the owner, 2026-10-15: "where is the button to restart it from the page itself?"): a bridge this
    // machine runs (card.restart, funnel.broken_connections) is restarted by the same verb as its Connections card - it installs
    // what is missing and starts it detached (wabridge.py) - then checked, so the row clears the moment it answers
    const restart = async () => {
      setBusy("restart"); setErr(""); setNote("Restarting the bridge…");
      try {
        await api.post(`/api/connectors/${cid}/wa/bridge/restart`);
        for (let i = 0; i < 200; i++) {               // npm install of its dependency is minutes on a slow line, the first time
          await new Promise((r) => setTimeout(r, 1500));
          const { data } = await api.get(`/api/connectors/${cid}/wa/status`).catch(() => ({ data: null }));
          const phase = data?.manager?.phase;
          if (phase === "installing") setNote("Installing the bridge's dependency - a few minutes the first time…");
          if (phase === "failed") { setBusy(""); setNote(""); setStuck(true); setErr(`The bridge did not start: ${data.manager.detail || "no reason given"}`); return; }
          if (data?.bridge || phase === "running") break;
        }
      } catch (e) { setBusy(""); setNote(""); setStuck(true); setErr(failOf(e)); return; }
      setBusy("");
      await check();
    };
    return (
      <div className="tq-conn" data-tq-conn={card.key}>
        <div className="tq-conn-head">
          <SourceMark item={card} size={15} />
          <b>{card.title}</b>
          <span className="tq-conn-pill">{signin ? "signed out" : "not answering"}</span>
          {card.when && <em>{ago(card.when)}</em>}
        </div>
        <div className="tq-conn-body">
          {said && <><div className="tq-conn-label">What it said</div><div className="tq-conn-said">{said}</div></>}
          {signin && <div className="tq-conn-note">Once you are signed in again this clears by itself.</div>}
          {note && <div className="tq-conn-note">{note}</div>}
          <CardErr err={err} className="tq-conn-note bad" bug={false} />
          {/* Check again IS the walk's own "Test it" chip, answered on the card at once - so the chip steps aside (the phone keeps it) */}
          <Foot covers={["test_connection"]} verb={signin
            ? <Button size="small" variant="contained" disableElevation sx={primary} onClick={openIt}>Sign in again</Button>
            : <>{cid && <Button size="small" variant="contained" disableElevation sx={primary} disabled={!!busy} onClick={check}
                  title={btnHint("test_connection")}>{busy === "check" ? "Checking…" : btn("test_connection")}</Button>}
                {cid && card.restart && <Button size="small" variant="outlined" sx={quiet} disabled={!!busy} onClick={restart}
                  title="Stop the bridge if it is stuck and start it again on this machine - you stay paired">
                  {busy === "restart" ? "Restarting…" : "Restart bridge"}</Button>}
                <Button size="small" variant="outlined" sx={quiet} onClick={openIt}
                  title="Its card on Connections - for a new password, key or setting">Open the connection</Button>
                {/* WHAT A CHECK CANNOT FIX IS OURS TO HEAR ABOUT (the owner, 2026-10-15: "if not solvable i thought we added button create
                    issue in github"): once Check again or the restart has failed here, the same scrubbed, previewed popup every error offers */}
                {stuck && <Button size="small" variant="outlined" sx={quiet} onClick={() => openBugReport(connError(card, said))}
                  title="Draft a GitHub issue from this error - you see and edit everything before it opens">{btn("report_bug")}</Button>}</>} />
        </div>
      </div>
    );
  }
  const own = card.kind === "todo" || card.channel === "own";
  // WORK YOU STARTED has nobody behind it (the owner, 2026-09-28: "the cards of tasks I started looked wrong"): no
  // reply to yourself, no "not ours", and a New task - no message at all - still gets its button
  const mineAlone = isOwn(card);
  const hand = btn(suggestedKind === "coding" ? "coding_agent" : "regular_agent");
  const startTask = async () => {
    setBusy("agent"); setErr("");
    try { await runOperation(api, "dispatch.prepare", card.tid, { kind: suggestedKind }); onDone?.(`Started on ${card.ref || "it"}.`); }
    catch (e) { setErr(failOf(e)); }
    setBusy("");
  };
  // NOT WHILE AN AGENT RUNS ON IT (the owner, 2026-10-01): its own session is the way in, and the dispatch door refuses it too
  const handIt = agentRuns(card) ? null : card.mid ? () => startAgent(suggestedKind) : card.tid ? startTask : null;
  const verb = !asks ? null : own || mineAlone
    ? handIt && <Button size="small" variant="contained" disableElevation disabled={!!busy} onClick={handIt} sx={moveSx}>
        {busy === "agent" ? "Handing it over…" : hand}</Button>
    : card.mid && <Button size="small" variant="contained" disableElevation disabled={!!busy} onClick={draftReply} sx={moveSx}>{busy === "reply" ? "Drafting…" : btn("reply")}</Button>;
  const asker = String(card.who || "them").replace(/\s*<[^>]*>/g, "");
  // AN AGENT ALREADY DID IT (the owner, 2026-09-28: TQ-0796 read "who should take it? Hand to agent" under the report of
  // the agent that took it): once a report is filed the move is to close the task, or send it back with what to change
  const reported = !!reportOf(doc) && (own || mineAlone);
  const sendBack = async () => {
    setBusy("back"); setErr("");
    try { await api.post(`/api/tasks/${card.tid}/continue-work`, { note: (back || "").trim() || null }); onDone?.(`Sent back to the agent on ${card.ref || "it"}. It comes back here when it stops.`); }
    catch (e) { setErr(failOf(e)); }
    setBusy("");
  };
  // what they wrote, in their words, inside the ask - never for your own task, whose words the story already said
  const words = card.channel === "assistant" && card.mid ? <div className="tq-thr-words"><AdvisorWhy mid={card.mid} /></div>
    : card.mid && !mineAlone ? <div className="tq-thr-words"><Clamp><CombinedTaskText card={card} list={false} /></Clamp></div> : null;
  return (
    <CardShell card={card} kicker={card.kind === "fyi" ? "fyi" : reported ? "agent reported" : suggestedKind === "coding" ? "coding · nobody on it" : own || mineAlone ? "your task" : WORD.asked}
      lead={<Story card={card} agent={own || mineAlone ? true : false} words={words} tail={!!verb || reported}
        fallback={card.channel === "own" ? card.preview : card.title} />} err={err}>
      {reported ? (
        <YourMove title={`${btn("close")}, or ${btn("continue")}`}
          go={<><Button size="small" variant="contained" disableElevation disabled={shut.busy || !!busy} onClick={shut.run} sx={moveSx} title={btnHint("close")}>{shut.busy ? "Closing…" : btn("close")}</Button>
            <Button size="small" variant="outlined" disabled={!!busy} onClick={() => setBack((b) => (b === null ? "" : null))} sx={quiet} title={btnHint("continue")}>{btn("continue")}</Button></>}
          then={back === null ? `if it is not finished, ${btn("continue")} says what is left.` : null}>
          {back !== null && (
            <div style={{ display: "flex", gap: 8, alignItems: "flex-start", marginTop: 8 }}>
              <TextField fullWidth multiline minRows={1} maxRows={4} autoFocus value={back} onChange={(e) => setBack(e.target.value)}
                placeholder="What is left for it to do?" sx={{ "& .MuiOutlinedInput-root": { background: "#fffdf9" }, "& textarea": { fontSize: 13 } }} />
              <Button size="small" variant="contained" disableElevation disabled={!!busy} onClick={sendBack} sx={moveSx}>{busy === "back" ? "Sending…" : "Send back"}</Button>
            </div>
          )}
          <CardErr err={shut.err} />
        </YourMove>
      ) : verb ? (
        <YourMove title={own || mineAlone ? "who should take it?" : `reply to ${asker}`} go={verb}
          then={own || mineAlone ? `starts ${suggestedKind === "coding" ? "a coding agent" : "an agent"} on it; it comes back here when it stops.`
            : "writes one for you to approve here - nothing is sent."} />
      ) : card.kind === "fyi" && <div className="tq-card-note">Nothing to decide - it only wants you to know.</div>}
      <Foot openTask={onOpenTask} close={card} onDone={onDone}
        covers={[...(own || mineAlone ? (suggestedKind === "coding" ? ["coding_agent", "coder"] : ["regular_agent"]) : ["reply"]), ...(mineAlone ? ["reply", "not_ours"] : [])]}
        where={<Where card={card} onOpenTask={onOpenTask} onTimeline={onTimeline} />} />
      {repoAsk && (
        <div className="tq-card-full" style={{ marginTop: 8 }}>
          <div style={{ fontWeight: 600, marginBottom: 6 }}>Which repository should the coding agent use?</div>
          <RepoPicker taskId={repoAsk.taskId} agent={repoAsk.agent}
            onDone={(data) => { if (data?.repo) { setRepoAsk(null); startAgent("coding"); } }} />
          <Button size="small" sx={faint} onClick={() => setRepoAsk(null)}>Not now</Button>
        </div>
      )}
    </CardShell>
  );
}

// the day, at the top of a new chat: how much waits, of what, and the two ways to start walking
// ...and it is the START OF THE WALK: who wants what, grouped, before the first card - the day's
// opener in place of the Morning digest (2026-09-23). Rows come from the LIVE pile, so a row settled
// since the chat opened is gone from here too; a row's click brings that one card up.
const ROWS_PER_GROUP = 5;
// the group's name in a pill of its own tint - assistantView.css `.tq-sum-head span.lvl-<group>`, the rail bands' own
// own tint, the same class the rail's heading wears (walkSummary.GROUPS are the rail's levels, 2026-10-02)
// the groups themselves - also drawn on the empty chat's welcome, which is what the walk starts from
// `quiet` groups show their pill and count only - on the day's opener, what needs no decision is on the
// rail already, and its rows were what pushed the way in off the screen (2026-09-23: "one screen")
export function WhoWantsWhat({ groups, onRow, max = ROWS_PER_GROUP, quiet = [] }) {
  return (groups || []).map((g) => ({ g, n: quiet.includes(g.key) ? 0 : max })).map(({ g, n }) => (
    <div key={g.key} className="tq-sum-group">
      <div className="tq-sum-head"><span className={`lvl-${g.key}`}>{g.word}</span><em>{g.n ?? g.rows.length}</em></div>
      {g.rows.slice(0, n).map((i) => (
        <button key={i.key} type="button" className="tq-sum-row" onClick={() => onRow?.(i.key)} title="Bring this one up now">
          <span className="dot" style={{ background: sourceColor(i) }} />
          <span className="ref">{refOf(i)}</span>
          <b>{whoOf(i)}</b>
          <span className="what">{i.title}{i.count > 1 && <em className="n"> ×{i.count}</em>}</span>
          <span className="st">{stateOf(i, laneMeta(i.lane).word)}</span>
        </button>
      ))}
      {n > 0 && (g.n ?? g.rows.length) > n && <div className="tq-sum-more">and {(g.n ?? g.rows.length) - Math.min(n, g.rows.length)} more</div>}
    </div>
  ));
}
// the day's opener: one card per band - its name, how many, and who from. A card walks that band (the owner, 2026-10-06:
// "it should be cards with summary info not list of details, we have that on the left side")
export function DayCards({ groups, onSection }) {
  return (
    <div className="tq-day-cards">
      {(groups || []).map((g) => (
        <button key={g.key} type="button" className={`tq-day-card lvl-${g.key}`} onClick={() => onSection?.(g.key)} title={`Walk me through ${g.word}`}>
          <span className="top"><span className="lbl"><i className="dot" />{g.word}</span><b>{g.n ?? g.rows.length}</b></span>
          <span className="who">{gistOf(g)}</span>
        </button>
      ))}
    </div>
  );
}
// THE DAY'S OPENER (the owner picked mock-up A, 2026-10-08): one paper card - the day's meetings as plain lines on the left,
// what waits on the right as a row per band (its gist, its count). It replaces the grey meetings box over a row of tiles.
// No meetings: the waiting side alone; nothing waiting: the meetings alone; neither: nothing.
const atLocal = (s) => new Date(String(s).replace(" ", "T")).getTime();
const firstNames = (who = []) => who.slice(0, 2).map((w) => String(w).split(/[ @]/)[0]).join(", ") + (who.length > 2 ? ` +${who.length - 2}` : "");
// `loading`: the launch is still reading the mail, so the counts are not the day's yet - they say so instead of growing under you
export function DayOpener({ groups = [], onSection, top = null, loading = false }) {
  const today = useCalendarToday();
  const [, tick] = useState(0);
  useEffect(() => { const id = setInterval(() => tick((v) => v + 1), 60000); return () => clearInterval(id); }, []);
  const all = today?.events || [], evs = all.filter((e) => !e.all_day), allDay = all.filter((e) => e.all_day);
  const now = Date.now(), next = evs.findIndex((e) => atLocal(e.start) > now);
  // the now line sits between what is behind you and what is ahead - not above a day that has not started
  const nowAt = next === -1 ? (evs.length ? evs.length : -1) : next > 0 ? next : -1;
  // ONE HEADLINE (U6): "Waiting · 30" counted reports and FYI the rows below called nothing to decide - the count is what is
  // on you, and reports and FYI sit apart as reading. Which sections are which is lanes.json's; a section's `you` is its rows that
  // are on you (summarize - waiting on THEM is under On you but not on you, as the greeting has always said)
  const cnt = (gs) => gs.reduce((n, g) => n + (g.n ?? g.rows.length), 0), isRead = (g) => !!SECTION[g.key]?.to_read;
  const act = groups.filter((g) => !isRead(g)), read = groups.filter(isRead);
  const onYou = groups.reduce((n, g) => n + (g.you ?? (SECTION[g.key]?.on_you ? g.n ?? g.rows.length : 0)), 0), toRead = cnt(read);
  const row = (g) => (
    <button key={g.key} type="button" className={`tq-day-row lvl-${g.key}`} onClick={() => onSection?.(g.key)} title={`Walk me through ${g.word}`}>
      <i className="dot" /><b className="lbl">{g.word}</b><span className="who">{gistOf(g)}</span><b className="n">{loading ? "…" : g.n ?? g.rows.length}</b>
    </button>
  );
  // THE WHOLE CARD FROM THE FIRST DAY (the owner, 2026-10-15: "on first startup it should show the full card - say calendar missing if
  // not available"): the calendar side says what it is - none connected, unreadable, or a day with no meetings - instead of vanishing.
  // `sources` is what calendar.today could reach; an answer from before it was sent says nothing, so the side stays as it was.
  const cal = !today || today.off ? null : Array.isArray(today.sources) && !today.sources.length ? "none"
    : !all.length && today.errors?.length ? "error" : !all.length && Array.isArray(today.sources) ? "empty" : null;
  const agenda = !!all.length || !!cal, waits = !!groups.length || loading;
  if (!agenda && !waits && !top) return null;
  const line = (e, i) => {
    const end = e.end ? atLocal(e.end) : atLocal(e.start) + 30 * 60000, past = end < now, live = !past && atLocal(e.start) <= now;
    return (
      <div key={`${e.start}-${i}`} className={`ev${past ? " past" : ""}${live ? " live" : ""}`} title={e.about || undefined}>
        <span className="t">{fmtTime12(e.start)}</span>
        <span className="s"><b>{e.subject}</b>{!!e.who?.length && <span> · {firstNames(e.who)}</span>}</span>
      </div>
    );
  };
  // ...and what CHANGED while you were away rides on top of the same card (SinceBlock - the owner picked "A +", 2026-10-08)
  return (
    <div className="tq-day-box">
    {top}
    {(agenda || waits) && <div className={`tq-day${agenda && waits ? "" : " solo"}`}>
      {!!cal && (
        <div className="tq-day-agenda" data-tq-cal={cal}>
          <div className="tq-day-h">Your day · {cal === "empty" ? "no meetings" : "calendar"}</div>
          <div className="ev cal-note"><span className="s">{cal === "none" ? "No calendar connected - your Microsoft 365 or Gmail card reads it once it is allowed to."
            : cal === "error" ? `Your calendar could not be read - ${String(today.errors[0]).slice(0, 140)}` : "Nothing on your calendar today."}</span></div>
          {cal !== "empty" && <button type="button" className="tq-linkish cal-go" onClick={() => openAppLink(place("mail").href)}>
            {cal === "none" ? "Connect a calendar" : "Open your mail card"}</button>}
        </div>
      )}
      {!!all.length && (
        <div className="tq-day-agenda">
          <div className="tq-day-h">Your day · {plural(evs.length, "meeting")}</div>
          {allDay.map((e) => <div key={e.subject} className="ev allday"><span className="t">all day</span><span className="s"><b>{e.subject}</b></span></div>)}
          {evs.map((e, i) => (
            <React.Fragment key={`${e.start}-${i}`}>
              {i === nowAt && <div className="ev now"><span className="t">now</span><i /></div>}
              {line(e, i)}
            </React.Fragment>
          ))}
          {nowAt === evs.length && <div className="ev now"><span className="t">now</span><i /></div>}
        </div>
      )}
      {waits && (
        <div className="tq-day-wait">
          <div className="tq-day-h">{loading ? "Counting…" : onYou ? `${onYou} on you` : "Nothing on you"}</div>
          {!groups.length && <div style={{ fontSize: 13, color: "#6e685f" }}>Your mail is still being read - what needs you shows up here.</div>}
          {act.map(row)}
          {!!read.length && <div className="tq-day-h" style={{ marginTop: 8 }}>To read · {loading ? "…" : toRead}</div>}
          {read.map(row)}
        </div>
      )}
    </div>}
    </div>
  );
}
export function BriefCard({ card, onStart }) {
  const nav = React.useContext(CardNav);
  const sum = nav.items ? summarize(nav.items) : null;
  const n = sum ? sum.n : card.n;
  return (
    <CardShell card={{ ...card, lane: "report", when: null }} kicker="start of the walk"
      lead={<Lead text={sum ? sum.lead : n ? `${plural(n, "thing")} waiting on you.` : "Nothing waiting on you."} />}
      sub={n ? null : "Ask me anything, or set something up."}>
      {sum && <WhoWantsWhat groups={sum.groups} onRow={nav.surface} />}
      {/* "Start at the top" IS the walk's Next here - one button, not two for the same step */}
      {!!n && <CardNav.Provider value={{ ...nav, onNext: null }}>
        <Foot verb={<Button size="small" variant="contained" disableElevation onClick={() => onStart?.(null)} sx={primary}
            title="Everything in the pipe, one card at a time">Start at the top</Button>}
          then={<><b>Start at the top</b> brings up the first card; each one has its verb and Next.</>} />
      </CardNav.Provider>}
    </CardShell>
  );
}

// how many fyi a card can show whole before every line folds to one (FyisCard)
const FOLD_AT = 6;

export function FyisCard({ card, onDone, onSurface, onTimeline, onPropose }) {
  const canCode = useCapabilities().coding;                   // no coding tool connected: no Coding agent (capabilities.js)
  const [open, setOpen] = useState(null);
  const [busy, setBusy] = useState("");
  const [err, setErr] = useState("");
  const items = card.items || [];
  // A batch of four is read whole: every line carries its gist and its two doors, and you never
  // open anything. A batch of ten drawn the same way is a card you scroll past, with twenty doors
  // on the one thing whose whole point is that none of it needs you (the owner, 2026-09-16: "when
  // it does 4 fyi or 10 fyis at one time"). So past FOLD_AT the lines fold: one apiece, and the
  // gist and the doors appear on the one you open.
  const folded = items.length > FOLD_AT;
  // a reply is the one immediate road (PW-126): the draft is written now, nothing is sent, nothing is marked
  const reply = async (i) => {
    setBusy(i.key); setErr("");
    try { const data = await openReply(api, i.mid); onSurface?.(data.reviewId ? `review:${data.reviewId}` : null, "Drafting a reply…"); }
    catch (e) { setErr(failOf(e)); }
    setBusy("");
  };
  const propose = async (verb, i) => {
    setBusy(i.key); setErr("");
    try { await onPropose?.(verb, i.key); } catch (e) { setErr(failOf(e)); }
    setBusy("");
  };
  return (
    <CardShell card={card} kicker={`${items.length} fyi · nothing to decide`}
      lead={<Lead text={`${plural(items.length, "message")} just want${items.length === 1 ? "s" : ""} you to know something.`} />} err={err}>
      {/* THE BOX, like every card's: one line per message - who, what, and its first line - and nothing
          else. The two doors each line wore ("Full message", "Talk about it") made four fyi a card of
          eight buttons (the owner, 2026-09-23: "you never redesigned the fyi cards"). A line is the
          control: it opens that one message in place, with its actions under it. Past a handful the
          first lines go too, so ten fyi is a list you skim (2026-09-16: "4 fyi or 10 fyis at one time"). */}
      <div className="tq-fyi-box">
      {items.map((i) => (
        <div key={i.key} className={`tq-fyi${open === i.key ? " open" : ""}`}>
          <button type="button" className="tq-fyi-line" onClick={() => setOpen((o) => (o === i.key ? null : i.key))}
            aria-expanded={open === i.key} title={open === i.key ? "Fold it" : "Read it here"}>
            <SourceMark item={i} size={13} />
            <b>{i.who || "someone"}</b>
            <span className="t">{i.title}</span>
            {/* WHEN each came, as every message on a task says it (the owner, 2026-10-14) */}
            {(i.since || i.when) && <span className="at">{fmtDateTime(i.since || i.when)}</span>}
            <span className="chev">{open === i.key ? "\u25be" : "\u25b8"}</span>
          </button>
          {open !== i.key && !folded && gistFor(i) && <div className="tq-fyi-gist">{gistFor(i)}</div>}
          {open === i.key && i.mid && <FullText mid={i.mid} revision={i.presentation_revision || card.presentation_revision} />}
          {/* ...and acting on it belongs to the ONE you opened, through the same proposal road the words
              take (PW-151) - never on the handful, never marking its siblings; and an entry already filed under a
              task is never offered to be made one (the owner, 2026-10-01) */}
          {open === i.key && (
            <div className="tq-card-actions tq-fyi-acts">
              {i.mid && <Button size="small" variant="outlined" disabled={!!busy} onClick={() => reply(i)} title={btnHint("reply")} sx={quiet}>{btn("reply")}</Button>}
              {i.mid && !i.tid && <Button size="small" variant="outlined" disabled={!!busy} onClick={() => propose("mine", i)} title={btnHint("mine")} sx={quiet}>{btn("mine")}</Button>}
              {i.mid && !i.tid && canCode && <Button size="small" variant="outlined" disabled={!!busy} onClick={() => propose("coding_agent", i)} title={btnHint("coding_agent")} sx={quiet}>{btn("coding_agent")}</Button>}
              {i.mid && !i.tid && <Button size="small" variant="outlined" disabled={!!busy} onClick={() => propose("regular_agent", i)} title={btnHint("regular_agent")} sx={quiet}>{btn("regular_agent")}</Button>}
              {/* one line of the handful can be put down on its own - All read was the only way to let any of it go */}
              {i.mid && <Button size="small" variant="outlined" disabled={!!busy} onClick={() => propose("not_ours", i)} title={btnHint("not_ours")} sx={quiet}>{btn("not_ours")}</Button>}
              <Button size="small" onClick={() => onSurface?.(i.key)} sx={faint}>Talk about it</Button>
            </div>
          )}
        </div>
      ))}
      </div>
      {/* the one card whose verb IS Next: marking the handful read moves on (fyis carries no `next`) */}
      <Foot verb={<Button size="small" variant="contained" disableElevation onClick={() => onDone?.(`Read — ${items.length} fyi let go.`)} sx={primary}>{btn("next", "batch")}</Button>}
        then={<><b>{btn("next", "batch")}</b> marks {items.length === 1 ? "it" : `all ${items.length}`} read - search finds {items.length === 1 ? "it" : "them"} later.</>}
        where={null} />
    </CardShell>
  );
}

export function SetupCard({ card, onNavigate, onHandOff }) {
  const [text, setText] = useState("");
  return (
    <CardShell card={{ ...card, lane: "report" }} kicker="set something up" title="What should it do?"
      sub="A report that pulls last month's Zoho invoices, a connection to a new system, an alert when a job fails - in your words. The assistant walks you through it and can navigate a browser beside the conversation.">
      <TextField fullWidth multiline minRows={2} maxRows={6} value={text} onChange={(e) => setText(e.target.value)}
        placeholder="Set up a report that…" onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); onHandOff?.(text); setText(""); } }}
        sx={{ mt: 1, "& textarea": { fontSize: 12.5 } }} />
      <div className="tq-card-actions">
        <Button size="small" variant="contained" disableElevation disabled={!text.trim()} onClick={() => { onHandOff?.(text); setText(""); }} sx={primary}>Open walkthrough</Button>
        <span className="sp" />
        <Button size="small" onClick={() => { window.location.hash = "report=new"; onNavigate?.("Reports"); }} sx={faint}>Reports tab</Button>
        <Button size="small" onClick={() => onNavigate?.("Connections")} sx={faint}>Connections tab</Button>
      </div>
    </CardShell>
  );
}

/* One stop of the scripted walk. Deterministic: the text is shipped, the buttons are code, and
   nothing here asks a model anything - the chip this sits behind used to open an AI-led walk-through,
   which could not run before an AI was connected, which is when it gets pressed.

   `can` is what the APP can do here, shipped and identical on every install. `facts` is what THIS
   install has done, read off the same tables the checklist reads - so a stop can never claim
   something the checklist contradicts. `image` is a shot of the tab, and it is decoration with a
   caption's job: a card whose image fails to load is still a complete stop, which is why it is
   rendered with onError rather than reserved space. */
// A WINDOW ONTO THE TAB, NOT A PICTURE OF IT. A screenshot was either too small to read or a zoomed
// corner of one (the owner, 2026-09-23: "maybe skip the images and just have a window into settings you
// can scroll. like we have session window"). So a stop draws the tab itself - live, scrollable, the real
// thing - in a box the size of the AI stop's terminal. Loaded only when a stop shows it. The Assistant
// stop keeps its picture: the walk runs inside the Assistant, and a window onto it would hold itself.
// ...and Settings and Docs are the canvas's own picker - the chips and their cards - not the old tab's scrolling rail, which
// nothing else in the app draws any more (the owner, 2026-10-07: "do we still have the scroll settings left sidebar?")
const Picker = React.lazy(() => import("./CanvasBrowse.jsx"));
const PICKER_AT = { settings: null, docs: "docs" };
function SettingsWindow({ stop, go }) {
  const [state, setState] = useState({ section: PICKER_AT[stop], open: null });
  return <Picker area="settings" state={state} onState={setState} live onNavigate={(tab) => go({ tab })} />;
}
const TAB_WINDOWS = {
  connections: React.lazy(() => import("./ConnectorsView.jsx")),
  docs: SettingsWindow,
  settings: SettingsWindow,
  board: React.lazy(() => import("./BoardView.jsx")),
  tasks: React.lazy(() => import("./TasksView.jsx")),
  reports: React.lazy(() => import("./ReportsView.jsx")),
  hub: React.lazy(() => import("./HubView.jsx")),
};

function TabWindow({ stop, go }) {
  // Tasks picks its first task on arrival: that choice stays IN the window. Treated as a click, it
  // carried the owner off to the Tasks tab the moment the stop drew.
  const [sel, setSel] = useState(null);
  const View = TAB_WINDOWS[stop];
  if (!View) return null;
  // a task opened from the Board or the Hub goes to its real tab, where there is room to work on it
  const openTask = (id) => id && go({ tab: "Tasks", hash: `task=${typeof id === "object" ? id.TaskId : id}` });
  return (
    <div className="tq-walk-window">
      <React.Suspense fallback={<div className="tq-card-full">…</div>}>
        {View === SettingsWindow ? <View stop={stop} go={go} />
          : <View active onNavigate={(tab) => go({ tab })} onOpenTask={openTask} onSelect={setSel} selected={sel} />}
      </React.Suspense>
    </div>
  );
}

export function WalkCard({ card, at, total, onNavigate, onNext, onBack, onRestart, onFinish, onSaved }) {
  const outer = React.useContext(CardNav);   // the walk's own foot rides in the row too, whatever its words are
  const { openSetup, opening, pane, note } = useCliSetup();
  const [cli, setCli] = useState(null);
  useEffect(() => {
    if (card?.key !== "ai") return;
    api.get("/api/cli/detect").then(({ data }) => setCli((data.data || []).find((o) => canSetup(o)) || null)).catch(() => {});
  }, [card?.key]);
  const go = (goto) => {
    if (!goto) return;
    if (goto.hash) window.location.hash = goto.hash;
    onNavigate?.(goto.tab);
  };
  const last = at >= total - 1, first = at <= 0;
  // THREE THINGS TO DO, NOT FIVE. The lists ran to five bullets a stop and the eye stopped reading
  // them by the third stop; three is what a person tries, and the tab itself has the rest.
  const can = (card.can || []).slice(0, 3);
  return (
    <CardShell card={{ ...card, lane: "report" }} kicker={`the walk · ${at + 1} of ${total}`}
      title={<>
        {/* A BOX ONLY WHERE THERE IS SOMETHING TO COMPLETE. The first five stops carry the
            checklist's own `done`; the rest are a tour of the app, and an empty box beside "the
            Timeline" would invent a chore nobody has (the owner, 2026-09-17: "show check boxes if
            it's done. Make the walk through accurate to what was completed"). */}
        {"done" in card && (
          <span aria-hidden="true" title={card.done ? "already done" : "not done yet"}
            style={{ marginRight: 7, fontSize: 13, fontWeight: 600, color: card.done ? "#47654a" : "#b3aa9c" }}>
            {card.done ? "☑" : "☐"}</span>
        )}
        {card.title}
      </>} sub={card.blurb}>
      {/* how far along: one thin bar, no numbers to read twice */}
      <div className="tq-walk-progress" aria-hidden="true"><i style={{ transform: `scaleX(${(at + 1) / Math.max(1, total)})` }} /></div>
      {/* THE PICTURE IS THE CARD. It used to be squeezed to the card's width and then cropped to a
          130px strip of its top-left corner, which showed a search box and half a heading and read as
          a smear (the owner, 2026-09-18: "the images look unclear"). Whole, at the shot's own shape,
          and clickable: the picture of the tab is the way to the tab. A broken image removes itself
          rather than leaving a torn box - the words above and below already carry the stop. */}
      {/* THE WHOLE TAB, as wide as the card (assistantView.css .tq-walk-shot says why it is neither the
          old 540px thumbnail nor the zoomed corner that replaced it). */}
      {TAB_WINDOWS[card.key] && <TabWindow stop={card.key} go={go} />}
      {card.image && !TAB_WINDOWS[card.key] && (
        <div className="tq-walk-shot" title={card.goto ? `Open ${card.goto.tab}` : undefined}
          role={card.goto ? "button" : undefined} tabIndex={card.goto ? 0 : undefined}
          onClick={() => go(card.goto)} onKeyDown={(e) => { if (e.key === "Enter") go(card.goto); }}
          style={{ cursor: card.goto ? "pointer" : "default" }}>
          <img src={card.image} alt={`The ${card.title} tab`} loading="lazy"
            onError={(e) => { e.currentTarget.parentElement.style.display = "none"; }} />
        </div>
      )}
      {/* what THIS install has - the same tables the checklist reads. Said as whose it is: a bare
          "none yet" under a picture of the tab did not say none of WHAT. */}
      {card.facts && <div className="tq-card-excerpt"><b>On this install</b> · {card.facts}</div>}
      {/* the five setup stops mirror the checklist's own done-ness (walk.state reads the same
          tables) - a stop that has been done says so, the same green the checklist panel uses,
          rather than reading identically whether or not it has been. */}
      {/* setup.state writes a detail that says what it IS ("already connected: Outlook mail, \u2026"),
          so this renders it as given. It used to patch the words back on for one step by key, which
          left every other step reading as a heading for the instructions under it. */}
      {card.done && card.detail && <div style={{ fontSize: 12.5, fontWeight: 600, color: "#47654a", margin: "4px 0" }}>
        {card.detail}</div>}
      {can.length > 0 && (
        <div className="tq-walk-can">
          <span className="lbl">You can</span>
          {can.map((o, i) => o.goto
            ? <button key={i} type="button" onClick={() => go(o.goto)} title={`Open ${o.goto.tab}`}>{o.text}</button>
            : <span key={i} className="plain">{o.text}</span>)}
        </div>
      )}
      {/* Two stops do the work in place rather than sending you somewhere. This one because its whole
          content is two text boxes, and because the bullet above it says "type your name and email
          right here" - a card that then offered only a button to Docs was making a promise it did not
          keep (the owner, 2026-09-17). Saving refreshes the stop, so its tick appears where you are. */}
      {/* ...and Save moves ON: it only re-ticked the stop, and the owner pressed Save and sat on a step that looked
          finished and stuck (the owner, 2026-10-14: "hitting save on the walk for the first name does not move to the next step") */}
      {card.key === "owner" && <OwnerForm onDone={async () => { await onSaved?.(); onNext?.(); }} />}
      {card.action === "sync" && <FirstSync enabled={card.enabled} ready={card.done}
        firstItems={card.first_items || []} onSaved={onSaved} onNavigate={onNavigate} />}
      {/* ...and this one because what it opens is a terminal, and a terminal has no page of its own
          to visit. */}
      {/* ...and NOT when a brain already answers. Offering to install a coding CLI to an install
          running on Azure OpenAI told it the wrong thing twice: that it needed one, and that a
          terminal is how its own connection gets set up (the owner, 2026-09-17). */}
      {card.key === "ai" && cli && !card.done && (
        <div style={{ marginTop: 8 }}>
          <SetupButton cli={cli} opening={opening} onOpen={openSetup} />
          {note && <div className="tq-card-note">{note.text}</div>}
          {pane && <CliPane pane={pane} height="38vh" />}
        </div>
      )}
      {/* THE SAME FOOT AS EVERY OTHER CARD (the owner, 2026-09-23: "match the walk through cards to the
          cards used to walk you through tasks"): the stop's own verb - its tab, under the label the
          checklist panel's row uses - then Next, and Back / Start over / Finish on the Also line.
          Back and Next are one act each - a position moved (walk.go takes any stop); Start over is the
          reset the server always had (the owner, 2026-09-18: "we also need a button to start over").
          The walk is scripted and reaches no model - but a question typed during it is an ordinary
          turn, answered beside the walk while the walk keeps its place (walk.py's own design). */}
      <CardNav.Provider value={{ busy: outer.busy, row: outer.row, ref: outer.ref, onNext: last ? null : onNext, also: [
        ...(!first ? [{ verb: "back", label: "‹ Back", onClick: onBack }] : []),
        ...(!first ? [{ verb: "restart", label: "Start over", title: "back to the first stop", onClick: onRestart }] : []),
        { verb: "finish", label: "Finish", onClick: onFinish }] }}>
        <Foot inline verb={card.action !== "sync" && card.goto && <Button size="small" variant="contained" disableElevation onClick={() => go(card.goto)}
            sx={primary}>{card.goto.label || `Open ${card.goto.tab}`}</Button>}
          then={card.action === "sync" ? "Review one result before continuing to the optional settings."
            : card.goto ? <><b>{card.goto.label || `Open ${card.goto.tab}`}</b> takes you there. Questions? Ask below in your own words - the walk keeps your place.</>
            : "Questions? Ask below in your own words - the walk keeps your place."} />
      </CardNav.Provider>
    </CardShell>
  );
}
