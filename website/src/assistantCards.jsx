// The cards under Taskuary's lines. Commentary explains; the clearly labelled button acts - so
// the model never chooses a card (funnelPile.cardFor does, by kind) and never claims an action
// happened. Every button here calls an endpoint that already exists for the Timeline, the Review
// queue or the Board; the card only puts it under the sentence that was just said. Reading
// happens IN the card (the full text unfolds under it) and every card links to where the whole of
// it lives - the task, or the row on the Timeline - because everything is the chat.
import React, { useEffect, useRef, useState } from "react";
import { Button, TextField } from "@mui/material";
import SendRoundedIcon from "@mui/icons-material/SendRounded";
import RefreshRoundedIcon from "@mui/icons-material/RefreshRounded";
import DoneRoundedIcon from "@mui/icons-material/DoneRounded";
import EventIcon from "@mui/icons-material/Event";
import TerminalIcon from "@mui/icons-material/Terminal";
import api from "./api.js";
import { gistFor } from "./fyiRow.js";
import { runOperation } from "./taskOps.js";
import { ChannelIcon, TaskuaryMark, channelColor, cleanText, fmtDateTime } from "./ui.jsx";
import { Md, looksMd } from "./md.jsx";
import DigestText from "./DigestText.jsx";
import TodayMeetingsStrip from "./TodayMeetingsStrip.jsx";
import { ROLES, ASSISTANT } from "./theme.jsx";
import { laneMeta, ageText, agoText, assistantFocus } from "./funnelPile.js";
import { says, subState } from "./laneSays.js";
// the agent card's kicker, per sub-state of the blocked lane (the sentence itself is laneSays)
const KICK = { asking: "asked", approval: "asks permission", stalled: "is stuck", parked: "stopped" };
import { sendBlockLine, draftState } from "./sendState.js";
import { progressLine } from "./checklist.js";
import { TerminalPane } from "./TerminalView.jsx";
import { agentCardView } from "./agentCardView.js";
import { lazyGeneral } from "./lazyGeneral.js";
import { RepoPicker } from "./RepoPicker.jsx";
import { useCliSetup, SetupButton, CliPane, canSetup } from "./cliSetup.jsx";
import OwnerForm from "./OwnerForm.jsx";
import { summarize, stateOf, whoOf } from "./walkSummary.js";

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
  if (item.kind === "agent" || item.kind === "agentdone") return <TerminalIcon sx={{ fontSize: size, color: "#41525f" }} />;
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
  if (item.kind === "agent" || item.kind === "agentdone") return "#41525f";
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

// the asker, in bold, when the sentence opens with them
function Lead({ text, who }) {
  const t = String(text || "").trim();
  if (!t) return null;
  const w = String(who || "").trim();
  if (w && t.toLowerCase().startsWith(w.toLowerCase())) return <div className="tq-card-lead"><b>{t.slice(0, w.length)}</b>{t.slice(w.length)}</div>;
  return <div className="tq-card-lead">{t}</div>;
}

// who wants what, for a card with a task behind it: the task's own summary, which triage writes
function TaskLead({ card, fallback }) {
  const [sum, setSum] = useState(null);
  useEffect(() => {
    let live = true;
    if (!card?.tid) { setSum(""); return () => { live = false; }; }
    api.get(`/api/tasks/${card.tid}`).then(({ data }) => live && setSum(String(data?.task?.Summary || ""))).catch(() => live && setSum(""));
    return () => { live = false; };
  }, [card?.tid, card?.presentation_revision]);
  return <Lead text={firstSentence(sum) || firstSentence(card?.summary) || fallback || card?.title} who={card?.who} />;
}

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
    catch (e) { setErr(errText(e)); setBusy(false); }
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
export function Foot({ verb, then, where, covers = [], close, onDone, more, promote, extra = [], inline = false }) {
  const nav = React.useContext(CardNav);
  const shut = useClose(close || {}, onDone);
  const [open, setOpen] = useState(false);
  const lifted = !verb && promote ? (nav.also || []).find((a) => a.verb === promote) : null;
  const also = [...(nav.also || []).filter((a) => !covers.includes(a.verb) && a !== lifted), ...extra];
  const words = [...also, ...(close?.tid && !also.some((a) => a.verb === "close")
    ? [{ verb: "close", label: shut.busy ? "Closing…" : "Close the task", title: "Close the task - it stops coming back to Work", onClick: shut.run, disabled: shut.busy }] : [])];
  return (
    <>
      {then && <div className="tq-card-then">{then}</div>}
      <div className="tq-card-actions">
        {verb || (lifted && <Button size="small" variant="contained" disableElevation disabled={lifted.disabled} onClick={lifted.onClick} title={lifted.title} sx={primary}>{lifted.label}</Button>)}
        {nav.onNext && <Button size="small" variant="outlined" disabled={nav.busy} onClick={nav.onNext} sx={quiet}>Next</Button>}
        {more}
        {!inline && !!words.length && (
          <Button size="small" onClick={() => setOpen((o) => !o)} sx={faint} aria-expanded={open}>
            {open ? "Fewer actions ▴" : "More actions ▾"}</Button>
        )}
        <span className="sp" />
        {where}
      </div>
      {inline && !!words.length && (
        <div className="tq-card-also">{words.map((a) => (
          <button key={a.verb || a.label} type="button" title={a.title || undefined} disabled={a.disabled} onClick={a.onClick}>{a.label}</button>
        ))}</div>
      )}
      {!inline && open && (
        <div className="tq-card-actions tq-card-more-actions">{words.map((a) => (
          <Button key={a.verb || a.label} size="small" variant="outlined" title={a.title || undefined} disabled={a.disabled} onClick={a.onClick} sx={quiet}>{a.label}</Button>
        ))}</div>
      )}
      {shut.err && <div className="tq-card-err">{shut.err}</div>}
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
function FullText({ mid, revision }) {
  const [doc, setDoc] = useState(null);
  const shownFor = useRef(null);
  useEffect(() => {
    let live = true;
    if (shownFor.current !== mid) { setDoc(null); shownFor.current = mid; }   // a different message: blank
    // ...and a card with no mail behind it asks for nothing. A task whose only message a skip rule
    // hid has no mid, and fetching /api/messages/null painted FastAPI's own validation sentence
    // ("path.mid: Input should be a valid integer") into the card (the owner, 2026-09-15).
    if (mid == null || mid === "") { setDoc({ error: "" }); return () => { live = false; }; }
    api.get(`/api/messages/${mid}`).then(({ data }) => live && setDoc(data)).catch((e) => live && setDoc({ error: errText(e) }));
    return () => { live = false; };
  }, [mid, revision]);
  if (!doc) return <div className="tq-card-full">…</div>;
  if (doc.error) return <div className="tq-card-err">{doc.error}</div>;
  const body = cleanText(doc.BodyText || "");
  const cut = body.indexOf("\n--- raw data ---");
  const text = cut >= 0 ? body.slice(0, cut) : body;
  const morning = doc.SourceName === "Morning digest" || /^Morning digest\b/i.test(doc.Subject || "");
  return (
    <div className="tq-card-full">
      {morning ? <DigestText text={text} /> : looksMd(text) ? <Md text={text} /> : (text || "(empty)")}
      {doc.SourceLink && <div className="tq-card-note"><a href={doc.SourceLink} target="_blank" rel="noreferrer" style={{ color: "#55697a" }}>open the original</a></div>}
    </div>
  );
}

// A task is the grouping boundary after triage. Fetching `/thread` here would pull the whole Teams
// or WhatsApp room (and made TQ-0367 say +19); task detail tells us exactly which messages triage
// combined. Context rows helped triage decide, but are not part of the grouped ask shown to the owner.
// `list={false}` on the walk's cards: the checklist and the task's history live on the Tasks tab, and
// the card links there rather than repeating them (the owner, 2026-09-23)
function CombinedTaskText({ card, list = true }) {
  const [doc, setDoc] = useState(null);
  const shownFor = useRef(null);
  useEffect(() => {
    let live = true;
    if (!card?.tid) { setDoc({ messages: [] }); return () => { live = false; }; }
    // same task, newer presentation: keep what is on screen and swap it when the fresh copy lands
    const identity = `${card.tid}:${card.mid || ""}`;
    if (shownFor.current !== identity) { setDoc(null); shownFor.current = identity; }
    api.get(`/api/tasks/${card.tid}`).then(({ data }) => live && setDoc(data)).catch((e) => live && setDoc({ error: errText(e) }));
    return () => { live = false; };
  }, [card?.tid, card?.mid, card?.presentation_revision]);
  if (!card?.tid) return <FullText mid={card?.mid} revision={card?.presentation_revision} />;
  if (!doc) return <div className="tq-card-full">…</div>;
  if (doc.error) return <div className="tq-card-err">{doc.error}</div>;
  const messages = (doc.messages || []).filter((m) => String(m.Status || "") !== "context");
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
  const repeatReceipt = ownTask && list && onlyBody && onlyBody === taskWords;   // with no list above it, the body IS the task
  if (messages.length <= 1) return <>{task}{!repeatReceipt && <FullText mid={card?.mid} revision={card?.presentation_revision} />}</>;
  return <>
    {task}
    <div className="tq-card-full tq-card-context">
      <div className="tq-card-note" style={{ marginBottom: 7, fontWeight: 700 }}>
        Email context · {messages.length} messages combined by triage
      </div>
      {messages.map((m, n) => {
        const body = cleanText(m.BodyText || "");
        return (
          <div key={m.MessageId || n} style={{ padding: "7px 0", borderTop: n ? "1px solid #e2ddd4" : 0 }}>
            <div className="tq-card-note" style={{ marginBottom: 3 }}>
              {m.Direction === "out" ? "You" : (m.FromName || m.FromEmail || "Someone")}{m.SentAt ? ` · ${fmtDateTime(m.SentAt)}` : ""}
            </div>
            {looksMd(body) ? <Md text={body} /> : (body || "(empty)")}
          </div>
        );
      })}
    </div>
  </>;
}

// what every card shares: where it came from (logo, lane dot, two words, when), then who wants what.
// The lane colours the DOT only - never an edge or a wash (uri-taste: colour identifies).
export function CardShell({ card, kicker, title, lead, sub, children, err }) {
  const meta = laneMeta(card?.lane);
  const when = card?.when ? agoText(card.when) : "";
  return (
    <div className="tq-card">
      <div className="tq-card-kicker"><span className="src"><SourceMark item={card} /></span><span className="dot" style={{ background: edge(card?.lane) }} />{kicker || meta.word}
        {when && <em>{when}</em>}</div>
      {lead || (typeof title === "string" ? <Lead text={title} who={card?.who} /> : title && <div className="tq-card-lead">{title}</div>)}
      {sub && <div className="tq-card-sub">{sub}</div>}
      {/* why it is BACK. Clearing a task never closed it, so the work tab raises it again once it has
          been quiet - and the card has to say that itself, or the only answer is "why am I seeing this
          again?" (the owner, 2026-09-15: "if they ask why explain it should be closed") */}
      {card?.why_open && <div className="tq-card-excerpt">{card.why_open}</div>}
      {children}
      {err && <div className="tq-card-err">{err}</div>}
    </div>
  );
}

// a reply drafted, or an action proposed - the owner's yes is the only thing that moves it
export function ReplyCard({ card, onDone, onOpenTask, onTimeline }) {
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
  useEffect(() => {
    let live = true;
    api.get("/api/reviews", { params: { status: "pending" } }).then(({ data }) => {
      if (!live) return;
      setRv((data.data || []).find((x) => x.ReviewId === card.rid) || { gone: true });
    }).catch((e) => live && setErr(errText(e)));
    return () => { live = false; };
  }, [card.rid, card.mid, card.presentation_revision]);
  const action = rv?.Kind === "action";
  const draft = () => {
    if (!action) return rv?.DraftText || "";
    try { const p = JSON.parse(rv.DraftText || ""); return p.text || `${p.action}${p.why ? ` — ${p.why}` : ""}`; } catch { return rv?.DraftText || ""; }
  };
  const value = text ?? draft();
  const stale = rv?.Stale ?? card.stale;
  const who = rv ? (rv.FromName && rv.FromEmail ? `${rv.FromName} <${rv.FromEmail}>` : rv.FromName || rv.FromEmail || "them") : "";
  const decide = async (verb) => {
    setBusy(verb); setErr("");
    try {
      const { data } = await api.post(`/api/reviews/${card.rid}/decide`, { verb, final_text: verb === "approve" ? value : null, note: null });
      if (data.send_error) throw new Error(data.send_error);
      onDone?.(verb === "approve" ? (action ? "Done — the action ran." : `Sent to ${who}.`) : action ? "Dismissed — nothing ran." : "Dismissed — no reply goes out.");
    } catch (e) { setErr(errText(e)); }
    setBusy("");
  };
  const redraft = async () => {
    setBusy("redraft"); setErr("");
    try { const { data } = await api.post(`/api/reviews/${card.rid}/draft`); setRv((r) => ({ ...r, DraftText: data.draft, Stale: false })); setText(null); }
    catch (e) { setErr(errText(e)); }
    setBusy("");
  };
  const finish = async () => {
    if (busy || !card.tid) return;
    setBusy("finish"); setErr("");
    try {
      await runOperation(api, "task.complete", card.tid);
      onDone?.(`${card.ref || "The task"} marked done. No reply was sent.`);
    } catch (e) { setErr(errText(e)); }
    finally { setBusy(""); }
  };
  if (rv?.gone) return <CardShell card={card} kicker="already handled" title={card.title} sub="This one is no longer waiting on you." />;
  const verb = action
    ? <Button size="small" variant="contained" disableElevation disabled={!!busy || !rv} startIcon={<DoneRoundedIcon />} onClick={() => decide("approve")} sx={primary}>{busy === "approve" ? "Running…" : "Run it"}</Button>
    : rv?.CanSend === false ? null : rv && !value.trim() && !stale ? (
      /* NOTHING TO SEND YET: a disabled Send was the only button, and the redraft word it covers was
         hidden as its duplicate - no way to get a draft from the card at all (2026-09-23) */
      <Button size="small" variant="contained" disableElevation disabled={!!busy} startIcon={<RefreshRoundedIcon />}
        onClick={redraft} sx={primary}>{busy === "redraft" ? "Drafting…" : "Draft with AI"}</Button>
    ) : stale ? (
      /* the road out of the warning, on the card that carries it: a stale draft disabled the
         only button here and named no way forward (the owner, 2026-09-21: "just reprocess it
         then"). Refreshing is the primary action while the thread is ahead of the draft. */
      <Button size="small" variant="contained" disableElevation disabled={!!busy || !rv}
        startIcon={<RefreshRoundedIcon />} onClick={redraft} sx={primary}
        title="Rewrites the draft from the newest message, then you approve it">
        {busy === "redraft" ? "Refreshing…" : "Refresh the draft"}</Button>
    ) : (
      <Button size="small" variant="contained" disableElevation disabled={!!busy || !rv || !value.trim()} startIcon={<SendRoundedIcon />} onClick={() => decide("approve")} sx={primary}>
        {busy === "approve" ? "Sending…" : "Send reply"}</Button>
    );
  const then = action ? <><b>Run it</b> does what the agent proposed - nothing runs until you press it.</>
    : rv && !value.trim() && !stale ? <><b>Draft with AI</b> writes one for you to approve here - nothing is sent.</>
    : stale ? <><b>Refresh the draft</b> rewrites it from the newest message; you still approve it.</>
    : rv ? <><b>Send reply</b> emails {who}.</> : null;
  return (
    <CardShell card={card} kicker={action ? "an agent asks to act" : "reply · draft ready"}
      lead={action ? <Lead text={rv?.Subject || card.title} /> : <TaskLead card={card} fallback={rv?.Subject} />} err={err}>
      {rv && (
        <TextField fullWidth multiline minRows={2} maxRows={9} value={value} onChange={(e) => setText(e.target.value)}
          placeholder={action ? "" : "No draft yet — choose Draft with AI, or write it here"}
          sx={{ mt: 1, "& textarea": { fontSize: 12.5, lineHeight: 1.5 } }} />
      )}
      {!action && stale && <div className="tq-card-err">New messages arrived after this draft. Refresh the draft with the latest context before sending.</div>}
      {!action && rv && draftState({ ...rv, HasDraft: value.trim() ? 1 : 0 }).line && <div className={draftState(rv).state === "failed" ? "tq-card-err" : "tq-card-excerpt"}>{draftState({ ...rv, HasDraft: value.trim() ? 1 : 0 }).line}</div>}
      {!action && sendBlockLine(rv) && <div className="tq-card-excerpt">{sendBlockLine(rv)}</div>}
      {/* WHAT YOU ARE ANSWERING, said to be that (the owner, 2026-09-14: "though you need to see what
          you are responding to") - one press away, under the draft */}
      {card.mid && <button type="button" className="tq-card-more" onClick={() => setFull((v) => !v)}>{full ? "Less" : "More - what they wrote"}</button>}
      {full && card.mid && <CombinedTaskText card={card} list={false} />}
      {/* "Close without sending" arrives as a conversation word; off the walk (no words), the same
          road is still offered under More actions */}
      <Foot verb={verb} then={then} covers={["approve", "redraft"]}
        extra={card.tid && !nav.also?.length ? [{ verb: "finish", label: busy === "finish" ? "Closing…" : "Mark done without sending",
          title: "Marks the task done, dismisses the draft, and ends any live agent session. No reply is sent.",
          disabled: !!busy || !rv, onClick: finish }] : []}
        where={<Where card={card} onOpenTask={onOpenTask} onTimeline={onTimeline} />} />
    </CardShell>
  );
}

const GeneralWorkspace = React.lazy(lazyGeneral("GeneralWorkspace"));   // guarded: a stale chunk reloads once

// an agent parked on a question: its last lines, and a box that answers it
export function AgentCard({ card, onDone, onOpenTask }) {
  // WHICH agent this is. A general task's chat reaches the pile down the same "an agent is waiting
  // on you" road as a coding CLI - and both were drawn as a terminal, so a research conversation
  // appeared here as a black screen of tool JSON under "This is the agent's own screen" (TQ-0420).
  const chat = agentCardView(card.mode) === "chat";
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [big, setBig] = useState(false);
  // A hand-off is not the main Assistant doing the work. Keep the other agent's workspace folded
  // unless the owner explicitly asks to see it; opening a regular API agent inline made the
  // orchestration chat look as though it had silently changed identities. Its OWN chat is not a
  // hand-off, and folding that leaves the card with nothing to read and nowhere to answer.
  const [live, setLive] = useState(chat && !card.paused);
  const answer = async () => {
    if (!text.trim()) return;
    setBusy(true); setErr("");
    try { await api.post(`/api/tasks/${card.tid}/waitroom`, { text }); onDone?.(`Told ${card.agent || "the agent"}: “${text.trim().slice(0, 80)}”`); }
    catch (e) { setErr(errText(e)); }
    setBusy(false);
  };
  // THE ANSWERS IT OFFERED, as answers. The question and its choices have ridden on this card since
  // PW-228 and nothing drew them, so a four-option chooser could only be answered by reading the
  // terminal and typing a digit into it (the owner, 2026-09-17). A pick goes to the exact request
  // that asked - never to the waiting room, which is a letterbox for a pane that is not asking
  // anything - and the agent's own screen is right above, still the way to say something else.
  const pick = async (c) => {
    setBusy(true); setErr("");
    try {
      await api.post(`/api/tasks/${card.tid}/worker/answer`, { request_id: card.request_id, text: c });
      onDone?.(`Answered ${card.agent || "the agent"}: “${String(c).slice(0, 80)}”`);
    } catch (e) { setErr(errText(e)); }
    setBusy(false);
  };
  const working = card.lane === "working";
  const who = chat ? "assistant" : "agent";
  const resume = async () => {
    setBusy(true); setErr("");
    try {
      await api.post(`/api/tasks/${card.tid}/resume`);
      onOpenTask?.(card.tid, { start: false });
    } catch (e) { setErr(errText(e)); }
    setBusy(false);
  };
  // The two ways an agent ends - wrap up (transcript becomes the report, proposals become reviews,
  // the task closes) and stop - were written here and never rendered, so nothing on this card could
  // reach either. Both roads are alive where they ARE offered: /api/tasks/{id}/wrap from the task
  // page, the Wall and the Agents panel. Removed rather than left looking like a feature.
  return (
    // who wants what, for an agent: ONE sentence for the state (laneSays) as the lead - when the
    // question and its choices are drawn below, the bare form here - and the task under it
    <CardShell card={card} kicker={working ? `the ${who} is working again` : card.paused ? "conversation paused" : `the ${who} ${KICK[subState(card)]}`}
      lead={<Lead text={working ? `${card.working || card.agent || who} is back at it - nothing for you until it stops.` : card.paused ? `${card.working || card.agent || who} was saved after Taskuary stopped - ready to resume.`
        : (card.choices || []).length && card.request_id ? says(subState(card), card.working || card.agent || who) : card.why || says(subState(card), card.working || card.agent || who)} who={card.working || card.agent} />}
      sub={card.paused ? null : card.title} err={err}>
      {card.paused && card.tid && <CombinedTaskText card={card} list={false} />}
      {chat && live ? (
        <div className="tq-card-chat" style={{ height: big ? 640 : 340 }}>
          <React.Suspense fallback={<div className="tq-card-tail">Opening the conversation…</div>}>
            <GeneralWorkspace task={{ TaskId: card.tid, Title: card.title }} compact />
          </React.Suspense>
        </div>
      ) : card.sid && live ? (
        // A SCREEN IS SHOWN WHOLE OR NOT AT ALL. Folded, this was 340px of a terminal mid-redraw -
        // wrapped escape codes and half a spinner - which said nothing anyone could read (the owner,
        // 2026-09-16: "no point of showing the coding window. You can't see anythign... either show
        // the whole thing or let them open task to see it"). So there is ONE size now, the one
        // Bigger used to reach, and the closed state draws nothing at all - the agent's last
        // terminal lines went with it, because raw pyte output is the same unreadable thing.
        <div className="tq-card-term" style={{ height: 640 }}>
          <TerminalPane sid={card.sid} height="640px" autoFocus={false} />
        </div>
      ) : chat && !!card.tail?.length && <div className="tq-card-tail">{card.tail.join("\n")}</div>}
      {(chat || card.sid) && !card.paused && (
        <div className="tq-card-note" style={{ display: "flex", gap: 10, alignItems: "center" }}>
          <span>{!live ? (chat ? "Conversation folded." : "Its screen is not here — show the whole thing, or open the workspace.")
            : chat ? "This is the conversation — answer it here." : "This is the agent's own screen — click in and type to answer it there."}</span>
          <span className="sp" />
          {chat && live && <Button size="small" onClick={() => setBig((b) => !b)} sx={faint}>{big ? "Smaller" : "Bigger"}</Button>}
          <Button size="small" onClick={() => setLive((l) => !l)} sx={faint}>
            {live ? (chat ? "Fold" : "Hide the screen") : chat ? "Show the conversation" : "Show the screen"}</Button>
        </div>
      )}
      {/* what it asked, and the answers it named - the question first, because the buttons under it
          are unreadable without it */}
      {!card.paused && !!(card.choices || []).length && !!card.request_id && (
        <div className="tq-card-ask">
          {!!card.why && <span>{card.why}</span>}
          <div className="tq-card-picks">
            {card.choices.map((c) => (
              <Button key={c} size="small" variant="outlined" disabled={busy} onClick={() => pick(c)}>{c}</Button>
            ))}
          </div>
        </div>
      )}
      {/* the chat above already has a composer, and it talks to the assistant. This box queues into
          the WAITING ROOM, which is a terminal's letterbox - two of them is two different sends. */}
      {!card.paused && !(chat && live) && <TextField fullWidth multiline minRows={1} maxRows={5} value={text} onChange={(e) => setText(e.target.value)}
        placeholder={card.asking ? "Or answer here — it goes straight in, it is waiting for it" : "Tell it what to do next"}
        onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); answer(); } }}
        sx={{ mt: 1, "& textarea": { fontSize: 12.5 } }} />}
      <Foot close={card} onDone={onDone} covers={["answer_agent"]}
        verb={card.paused
          ? <Button size="small" variant="contained" disableElevation disabled={busy} onClick={resume} sx={primary}>{busy ? "Continuing…" : "Continue this session"}</Button>
          : !(chat && live) && <Button size="small" variant="contained" disableElevation disabled={busy || !text.trim()} onClick={answer} sx={primary}>{busy ? "Sending…" : "Answer"}</Button>}
        then={card.paused ? <><b>Continue this session</b> picks it up where Taskuary stopped.</>
          : !(chat && live) ? <><b>Answer</b> goes straight to {card.working || card.agent || `the ${who}`}; it picks up where it stopped.</> : null}
        where={<Button size="small" onClick={() => onOpenTask?.(card.tid, { start: false })} sx={faint}>
          {chat ? "Open the task" : "Open agent workspace"} ↗</Button>} />
    </CardShell>
  );
}

// a meeting inside two hours: when, who, what the invite says - and the prep, one click away
export function MeetingCard({ card, onDone, onOpenTask }) {
  const e = card.event || {};
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const prep = async () => {
    setBusy(true); setErr("");
    try { const { data } = await api.post("/api/calendar/prep", { ...e, instruction: "Get me ready for this meeting: who is in it, what came before it, what I should say." }); onOpenTask?.(data.taskId); onDone?.("Prep opened in its own chat."); }
    catch (er) { setErr(errText(er)); }
    setBusy(false);
  };
  return (
    <CardShell card={card} kicker={`coming up · ${ageText(e.start)}`} title={e.subject || card.title}
      sub={[e.who?.length ? `with ${e.who.slice(0, 6).join(", ")}` : "", e.where].filter(Boolean).join(" · ")} err={err}>
      {e.about && <div className="tq-card-excerpt">{e.about}</div>}
      <Foot promote={e.join ? null : "prep"}
        verb={e.join ? <Button size="small" variant="contained" disableElevation component="a" href={e.join} target="_blank" rel="noreferrer" sx={primary}>Join</Button> : null}
        then={e.join ? <><b>Join</b> opens the meeting link.</> : "Getting prepped opens a chat that gets you ready - who is in it and what came before."} />
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
      <Foot close={card} onDone={onDone} promote={card.bad ? "rerun" : null}
        then={card.bad ? "Running it again reruns the report in the background; it comes back here." : null}
        where={<Where card={card} onOpenTask={onOpenTask} onTimeline={onTimeline} />} />
    </CardShell>
  );
}

// an agent finished: its own summary, the final report read right here, and the task where the files live
export function AgentDoneCard({ card, onOpenTask, onDone, onSurface }) {
  const [report, setReport] = useState(null);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  // What the agent found is usually what the sender is waiting to hear, so the reply belongs on this
  // card. The chat had to refuse it ("TQ-0338 has nothing to reply on it") because a finished agent's
  // item carried no message - it does now (funnel.reply_to), and this is the button (the owner,
  // 2026-09-03: "why can't you create a draft from here").
  const reply = async () => {
    setBusy(true); setErr("");
    try {
      const { data } = await api.post(`/api/messages/${card.mid}/reply`, { draft: true, instruction: null });
      if (data.reviewId) onSurface?.(`review:${data.reviewId}`, "A draft from the agent's findings - read it below.");
      else onDone?.("A reply is drafted on the task.");
    } catch (e) { setErr(errText(e)); }
    setBusy(false);
  };
  useEffect(() => {
    if (!open) return undefined;
    let live = true;
    setReport(null);
    api.get(`/api/tasks/${card.tid}`).then(({ data }) => {
      if (!live) return;
      const rep = (data.comments || []).slice().reverse().find((c) => String(c.Body || "").startsWith("CODER REPORT") || String(c.Body || "").startsWith("HANDOVER NOTE"));
      setReport(rep ? rep.Body.replace(/^(CODER REPORT|HANDOVER NOTE)\s*/, "") : "No report was filed on this task.");
    }).catch((e) => live && setReport(errText(e)));
    return () => { live = false; };
  }, [open, card.tid, card.presentation_revision]);
  const show = () => setOpen((o) => !o);
  return (
    <CardShell card={card} kicker="an agent finished" lead={<Lead text={`${card.who || "The agent"} finished ${card.title}.`} who={card.who} />} err={err}>
      {card.summary && !open && <div className="tq-card-excerpt">{card.summary}</div>}
      {open && <div className="tq-card-full">{report === null ? "…" : looksMd(report) ? <Md text={report} /> : report}</div>}
      <button type="button" className="tq-card-more" onClick={show}>{open ? "Less" : "More - show the final report"}</button>
      <Foot close={card} onDone={onDone} covers={card.mid ? ["reply"] : []}
        verb={card.mid ? (
          <Button size="small" variant="contained" disableElevation disabled={busy} onClick={reply} sx={primary}
            title="Write the sender a reply from what the agent found - it lands on the task for your yes">
            {busy ? "Drafting…" : "Reply from this"}</Button>
        ) : null}
        then={card.mid ? <><b>Reply from this</b> drafts an answer from what it found - nothing is sent until you approve it.</> : null}
        where={<Button size="small" onClick={() => onOpenTask?.(card.tid)} sx={faint}>Open {card.ref} ↗</Button>} />
    </CardShell>
  );
}

// the assistant's own line: the slipped ask, the promise, the thread gone quiet
export function IdeaCard({ card, onAct, onOpenTask, onTimeline, onNavigate }) {
  const a = card.action || {};
  const [busy, setBusy] = useState("");
  const [err, setErr] = useState("");
  const words = { followup: "waiting on them", promise: "you promised", asked: "slipped", cold: "gone quiet", idea: "worth a thought",
                  connect: "worth connecting", health: "needs a look" };
  // THE REPORT PROPOSES, THE CARD HAS THE DOORS (the assistant-runs-the-app design, 2026-09-18): a
  // system to connect opens its card on the Connections tab; a health finding opens the tab that fixes
  // it. "Not for us" is the plain done verb - the idea's key is remembered and it never comes back.
  const go = (tab, hash) => { if (hash) window.location.hash = hash; onNavigate?.(tab); };
  const nav = React.useContext(CardNav);
  return (
    <CardShell card={card} kicker={words[card.idea_kind] || "slipped"} title={card.title} err={err}>
      {card.why && <div className="tq-card-excerpt">{card.why}</div>}
      <Foot
        verb={card.idea_kind === "connect" && a.connector_type ? (
          <Button size="small" variant="contained" disableElevation sx={primary}
            onClick={() => go("Connections", `connector=${a.connector_type}`)}>{a.planned ? `Vote for ${a.title || a.connector_type}` : `Connect ${a.title || a.connector_type}`}</Button>
        ) : card.idea_kind === "health" && a.tab ? (
          <Button size="small" variant="contained" disableElevation sx={primary} onClick={() => go(a.tab, a.hash || "")}>Open {a.tab}</Button>
        ) : null}
        then={card.idea_kind === "connect" && a.connector_type ? <><b>{a.planned ? "Vote" : "Connect"}</b> opens its card on Connections - nothing changes until you finish there.</>
          : card.idea_kind === "health" && a.tab ? <><b>Open {a.tab}</b> takes you to the tab that fixes it.</>
          // the buttons are the short way; saying it is the real one (2026-09-04: "all the ideas
          // should just say it and I will create it")
          : "Say what you want done with it and I'll create it."}
        extra={(card.idea_kind === "connect" || card.idea_kind === "health") && onAct && !nav.also?.length
          ? [{ verb: "seen", label: card.idea_kind === "connect" ? "Not for us" : "Seen",
               onClick: () => onAct(card.idea_kind === "connect" ? "Not for us - remembered." : "Seen.") }] : []}
        where={<Where card={{ ...card, tid: a.tid || card.tid, mid: a.mid || card.mid }} onOpenTask={onOpenTask} onTimeline={onTimeline} />} />
    </CardShell>
  );
}

// a person wrote something: read it here, reply, hand it to an agent, or say it is not ours - and
// two doors for "not ours": one that teaches memory so it never comes back, one for just today
export function MessageCard({ card, onDone, onOpenTask, onTimeline, onSurface }) {
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
    catch (e) { setErr(errText(e)); }
    setBusy("");
  };
  const asks = card.kind !== "fyi";
  const suggestedKind = card.kind === "todo" && card.coding ? "coding" : "general";
  const startAgent = async (agentKind) => {
    setBusy("agent"); setErr("");
    try {
      const { data } = await api.post(`/api/messages/${card.mid}/dispatch`, {
        kind: agentKind,
      });
      if (data.dispatch === "needs_repo") {
        setRepoAsk({ taskId: data.taskId, agent: data.agent || "coder" });
      } else {
        setRepoAsk(null);
        const who = agentKind === "coding" ? (data.agent || "the coding agent") : (data.agent || "the regular agent");
        onDone?.(`${data.ref || "It"} is with ${who} now - I'll bring it back when it's done.`);
      }
    } catch (e) {
      const msg = errText(e);
      // Compatibility with an older server response when this card already knows its task.
      if (card.tid && /could not tell which checkout|no local path/i.test(msg))
        setRepoAsk({ taskId: card.tid, agent: "coder" });
      else setErr(msg);
    }
    setBusy("");
  };
  // the one immediate road for "asked you": a draft, written now, sent only on your yes (PW-126)
  const draftReply = () => post("reply", `/api/messages/${card.mid}/reply`, { draft: true }, null,
    (data) => onSurface?.(data?.reviewId ? `review:${data.reviewId}` : null, "Drafting a reply…"));
  const own = card.kind === "todo" || card.channel === "own";
  const hand = suggestedKind === "coding" ? "Hand to coding agent" : "Hand to agent";
  const verb = !asks || !card.mid ? null : own
    ? <Button size="small" variant="contained" disableElevation disabled={!!busy} onClick={() => startAgent(suggestedKind)} sx={primary}>
        {busy === "agent" ? "Handing it over…" : hand}</Button>
    : <Button size="small" variant="contained" disableElevation disabled={!!busy} onClick={draftReply} sx={primary}>{busy === "reply" ? "Drafting…" : "Draft a reply"}</Button>;
  return (
    <CardShell card={card} kicker={card.kind === "fyi" ? "fyi" : suggestedKind === "coding" ? "coding · nobody on it" : own ? "on your list" : "asked you"}
      lead={<TaskLead card={card} fallback={card.channel === "own" ? card.preview : card.title} />} err={err}>
      {card.channel === "assistant" && card.mid ? <AdvisorWhy mid={card.mid} />
        : card.mid ? <Clamp><CombinedTaskText card={card} list={false} /></Clamp>
        : card.preview && <div className="tq-card-excerpt">{card.preview}</div>}
      <Foot verb={verb} close={card} onDone={onDone}
        covers={own ? [suggestedKind === "coding" ? "coder" : "regular_agent"] : ["reply"]}
        then={!verb ? null : own ? <><b>{hand}</b> starts {suggestedKind === "coding" ? "a coding agent" : "an agent"} on it; it comes back here when it stops.</>
          : <><b>Draft a reply</b> writes one for you to approve here - nothing is sent.</>}
        where={<Where card={card} onOpenTask={onOpenTask} onTimeline={onTimeline} />} />
      {repoAsk && (
        <div className="tq-card-full" style={{ marginTop: 8 }}>
          <div style={{ fontWeight: 700, marginBottom: 6 }}>Which repository should the coding agent use?</div>
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
// the group's name in the rail band's own pill (the owner, 2026-09-23: "should be circle pills with
// colors"): who is waiting on you wears the rail's "your task" colour, an agent the working blue, your
// own list the report beige, and what needs no decision the muted one
const GROUP_ROLE = { people: "you", you: "info", agents: "working", read: "muted" };
// the groups themselves - also drawn on the empty chat's welcome, which is what the walk starts from
// `quiet` groups show their pill and count only - on the day's opener, what needs no decision is on the
// rail already, and its rows were what pushed the way in off the screen (2026-09-23: "one screen")
export function WhoWantsWhat({ groups, onRow, max = ROWS_PER_GROUP, quiet = [] }) {
  return (groups || []).map((g) => ({ g, n: quiet.includes(g.key) ? 0 : max })).map(({ g, n }) => (
    <div key={g.key} className="tq-sum-group">
      <div className="tq-sum-head"><span style={{ color: ROLES[GROUP_ROLE[g.key]].ink, background: ROLES[GROUP_ROLE[g.key]].tint,
        borderColor: ROLES[GROUP_ROLE[g.key]].bd }}>{g.word}</span><em>{g.rows.length}</em></div>
      {g.rows.slice(0, n).map((i) => (
        <button key={i.key} type="button" className="tq-sum-row" onClick={() => onRow?.(i.key)} title="Bring this one up now">
          <span className="dot" style={{ background: sourceColor(i) }} />
          <b>{whoOf(i)}</b>
          <span className="what">{i.title}</span>
          <span className="st">{stateOf(i, laneMeta(i.lane).word)}</span>
        </button>
      ))}
      {n > 0 && g.rows.length > n && <div className="tq-sum-more">and {g.rows.length - n} more</div>}
    </div>
  ));
}
export function BriefCard({ card, onStart }) {
  const nav = React.useContext(CardNav);
  const sum = nav.items ? summarize(nav.items) : null;
  const n = sum ? sum.n : card.n;
  return (
    <CardShell card={{ ...card, lane: "report", when: null }} kicker="start of the walk"
      lead={<Lead text={sum ? sum.lead : n ? `${n} thing${n === 1 ? "" : "s"} waiting on you.` : "Nothing waiting on you."} />}
      sub={n ? null : "Ask me anything, or set something up."}>
      {sum && <WhoWantsWhat groups={sum.groups} onRow={nav.surface} />}
      {/* "Start at the top" IS the walk's Next here - one button, not two for the same step */}
      {!!n && <CardNav.Provider value={{ ...nav, onNext: null }}>
        <Foot verb={<Button size="small" variant="contained" disableElevation onClick={() => onStart?.(null)} sx={primary}
            title="Everything in the pipe, one card at a time">Start at the top</Button>}
          then={<><b>Start at the top</b> brings up the first card; each one has its verb and Next.</>}
          more={<Button size="small" onClick={() => onStart?.("mail")} sx={faint}
            title="Only what people sent you - mail and chat">Just what came in</Button>} />
      </CardNav.Provider>}
    </CardShell>
  );
}

// a task named in the chat, with no mail of its own to act on: read what the agent left, open it, or tell it something
export function TaskCard({ card, onDone, onOpenTask }) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState("");
  const [err, setErr] = useState("");
  // NOBODY IS ON THIS. The card offered one action - queue a line for the agent to read when it next
  // stops - on a task whose agent had never started and never would: the message went into a waiting
  // room nothing was going to read (the owner, 2026-09-14). Idle work gets the button that changes
  // that; telling the agent something stays for when there IS one.
  const idle = card.lane === "queued";
  const tell = async () => {
    if (!text.trim()) return;
    setBusy("tell"); setErr("");
    try { await api.post(`/api/tasks/${card.tid}/waitroom`, { text }); onDone?.(`Queued for the agent on ${card.ref}: “${text.trim().slice(0, 80)}”`); }
    catch (e) { setErr(errText(e)); }
    setBusy("");
  };
  const start = async () => {
    setBusy("start"); setErr("");
    // the one dispatch road the task page and the general button use (PW-216) - the kind switch, the
    // live-worker check and the repository all decided in one place, never re-judged here
    try { await runOperation(api, "dispatch.prepare", card.tid, { kind: card.coding === false ? "general" : "coding" });
          onDone?.(`Started on ${card.ref}.`); }
    catch (e) { setErr(errText(e)); }
    setBusy("");
  };
  return (
    <CardShell card={card} kicker={idle ? "waiting to start" : "the task you asked about"}
      lead={<TaskLead card={card} />} sub={assistantFocus(card).lead || card.why} err={err}>
      {card.summary && <div className="tq-card-excerpt">{card.summary}</div>}
      {idle && card.why_idle && <div className="tq-card-excerpt"><b>Why it has not started:</b> {card.why_idle}</div>}
      {!idle && <TextField fullWidth multiline minRows={1} maxRows={4} value={text} onChange={(e) => setText(e.target.value)}
        placeholder="Tell the agent on this task something — it is typed in when it next stops"
        onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); tell(); } }} sx={{ mt: 1, "& textarea": { fontSize: 12.5 } }} />}
      <Foot close={card} onDone={onDone}
        verb={idle
          ? <Button size="small" variant="contained" disableElevation disabled={!!busy} onClick={start} sx={primary}>{busy === "start" ? "Starting…" : "Start the agent"}</Button>
          : <Button size="small" variant="contained" disableElevation disabled={!!busy || !text.trim()} onClick={tell} sx={primary}>{busy === "tell" ? "Queuing…" : "Tell the agent"}</Button>}
        then={idle ? <><b>Start the agent</b> hands it to an agent now; it comes back here when it stops.</>
          : <><b>Tell the agent</b> queues your words; they are typed in when it next stops.</>}
        where={<Button size="small" onClick={() => onOpenTask?.(card.tid)} sx={faint}>Open {card.ref} ↗</Button>} />
    </CardShell>
  );
}

// a handful of fyi's: a summary for each; read any in place; act on ONE of them through the same proposal
// road the words take (PW-151) - never on the handful, never marking its siblings - or let them all go
// how many fyi a card can show whole before every line folds to one (FyisCard)
const FOLD_AT = 6;

export function FyisCard({ card, onDone, onSurface, onTimeline, onPropose }) {
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
    try { const { data } = await api.post(`/api/messages/${i.mid}/reply`, { draft: true }); onSurface?.(data.reviewId ? `review:${data.reviewId}` : null, "Drafting a reply…"); }
    catch (e) { setErr(errText(e)); }
    setBusy("");
  };
  const propose = async (verb, i) => {
    setBusy(i.key); setErr("");
    try { await onPropose?.(verb, i.key); } catch (e) { setErr(errText(e)); }
    setBusy("");
  };
  return (
    <CardShell card={card} kicker={`${items.length} fyi · nothing to decide`}
      lead={<Lead text={`${items.length} message${items.length === 1 ? "" : "s"} just want${items.length === 1 ? "s" : ""} you to know something.`} />} err={err}>
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
            <span className="chev">{open === i.key ? "\u25be" : "\u25b8"}</span>
          </button>
          {open !== i.key && !folded && gistFor(i) && <div className="tq-fyi-gist">{gistFor(i)}</div>}
          {open === i.key && i.mid && <FullText mid={i.mid} revision={i.presentation_revision || card.presentation_revision} />}
          {/* ...and acting on it belongs to the ONE you opened, through the same proposal road the words
              take (PW-151) - never on the handful, never marking its siblings */}
          {open === i.key && (
            <div className="tq-card-actions tq-fyi-acts">
              {i.mid && <Button size="small" variant="outlined" disabled={!!busy} onClick={() => reply(i)} sx={quiet}>Reply</Button>}
              {i.mid && <Button size="small" variant="outlined" disabled={!!busy} onClick={() => propose("mine", i)} sx={quiet}>Make task</Button>}
              {i.mid && <Button size="small" variant="outlined" disabled={!!busy} onClick={() => propose("coder", i)} sx={quiet}>Coding agent</Button>}
              {i.mid && <Button size="small" variant="outlined" disabled={!!busy} onClick={() => propose("regular_agent", i)} sx={quiet}>Regular agent</Button>}
              <Button size="small" onClick={() => onSurface?.(i.key)} sx={faint}>Talk about it</Button>
            </div>
          )}
        </div>
      ))}
      </div>
      {/* the one card whose verb IS Next: marking the handful read moves on (fyis carries no `next`) */}
      <Foot verb={<Button size="small" variant="contained" disableElevation onClick={() => onDone?.(`Read — ${items.length} fyi let go.`)} sx={primary}>All read, next</Button>}
        then={<><b>All read, next</b> marks {items.length === 1 ? "it" : `all ${items.length}`} read - they stay on the Timeline.</>}
        where={null} />
    </CardShell>
  );
}

// the reply went out, the agent is finished, the task is still open: the last step is yours
export function WrapupCard({ card, onDone, onOpenTask }) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const close = async () => {
    setBusy(true); setErr("");
    try { await api.patch(`/api/tasks/${card.tid}`, { Status: "done" }); onDone?.(`${card.ref} closed.`); }
    catch (e) { setErr(errText(e)); }
    setBusy(false);
  };
  return (
    <CardShell card={card} kicker="reply sent · task still open" title={card.title} sub={card.why} err={err}>
      {card.sent && <div className="tq-card-excerpt">You sent: {card.sent}</div>}
      {card.summary && <div className="tq-card-excerpt">The agent: {card.summary}</div>}
      <Foot covers={["close"]}
        verb={<Button size="small" variant="contained" disableElevation disabled={busy} onClick={close} sx={primary}>{busy ? "Closing…" : "Close the task"}</Button>}
        then={<><b>Close the task</b> ends {card.ref} - it stops coming back to Work.</>}
        where={<Button size="small" onClick={() => onOpenTask?.(card.tid)} sx={faint}>Open {card.ref} ↗</Button>} />
    </CardShell>
  );
}

// "set something up": your words open a guided Assistant task. It may drive an embedded browser,
// but no coding session or checkout is involved unless the owner explicitly asks for one later.
//
// NOTHING PRODUCES `kind: "setup"` ANY MORE. The "Set up Taskuary" chip was its only caller and it
// now opens the scripted walk (`kind: "walk"`, WalkCard); the concierge's own `setup` verb renders
// a proposal. AssistantView still maps the kind, so a card carrying it renders - this is kept
// against that and against browserWalkthrough.test.mjs, which pins the prose below to prove the
// walkthrough is not described as coding work. Delete it and that guarantee goes with it.
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
export function WalkCard({ card, at, total, onNavigate, onNext, onBack, onRestart, onFinish, onSaved }) {
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
            style={{ marginRight: 7, fontSize: 13, fontWeight: 700, color: card.done ? "#47654a" : "#b3aa9c" }}>
            {card.done ? "☑" : "☐"}</span>
        )}
        {card.title}
      </>} sub={card.blurb}>
      {/* how far along: one thin bar, no numbers to read twice */}
      <div className="tq-walk-progress" aria-hidden="true"><i style={{ width: `${((at + 1) / Math.max(1, total)) * 100}%` }} /></div>
      {/* THE PICTURE IS THE CARD. It used to be squeezed to the card's width and then cropped to a
          130px strip of its top-left corner, which showed a search box and half a heading and read as
          a smear (the owner, 2026-09-18: "the images look unclear"). Whole, at the shot's own shape,
          and clickable: the picture of the tab is the way to the tab. A broken image removes itself
          rather than leaving a torn box - the words above and below already carry the stop. */}
      {/* ZOOMED IN, not shrunk to fit. Whole-and-small put a 1280px page into 540px and the words
          became texture (the owner, 2026-09-18: "zoom it in even if you can only see part of it").
          The picture is drawn at twice the box and the box shows its top-left - where a tab's name,
          its navigation and its first card live - and pans to the rest on hover. */}
      {card.image && (
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
      {card.key === "owner" && <OwnerForm onDone={async () => { await onSaved?.(); }} />}
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
      <CardNav.Provider value={{ onNext: last ? null : onNext, also: [
        ...(!first ? [{ verb: "back", label: "‹ Back", onClick: onBack }] : []),
        ...(!first ? [{ verb: "restart", label: "Start over", title: "back to the first stop", onClick: onRestart }] : []),
        { verb: "finish", label: "Finish", onClick: onFinish }] }}>
        <Foot inline verb={card.goto && <Button size="small" variant="contained" disableElevation onClick={() => go(card.goto)}
            sx={primary}>{card.goto.label || `Open ${card.goto.tab}`}</Button>}
          then={card.goto ? <><b>{card.goto.label || `Open ${card.goto.tab}`}</b> takes you there. Questions? Ask below in your own words - the walk keeps your place.</>
            : "Questions? Ask below in your own words - the walk keeps your place."} />
      </CardNav.Provider>
    </CardShell>
  );
}
