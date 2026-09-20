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
const Where = ({ card, onOpenTask, onTimeline }) => card?.tid
  ? <Button size="small" onClick={() => onOpenTask?.(card.tid)} sx={faint}>Open {card.ref || "task"}</Button>
  : card?.mid ? <Button size="small" onClick={() => onTimeline?.(card.mid)} sx={faint}>On the Timeline</Button> : null;

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
function CombinedTaskText({ card }) {
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
  if (!doc) return <div className="tq-card-full">â€¦</div>;
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
  const task = (taskText || items.length) ? (
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
  const repeatReceipt = ownTask && onlyBody && onlyBody === taskWords;
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
              {m.Direction === "out" ? "You" : (m.FromName || m.FromEmail || "Someone")}{m.SentAt ? ` Â· ${fmtDateTime(m.SentAt)}` : ""}
            </div>
            {looksMd(body) ? <Md text={body} /> : (body || "(empty)")}
          </div>
        );
      })}
    </div>
  </>;
}

// what every card shares: the source logo, the lane's word and dot, the title, the sub-line
export function CardShell({ card, kicker, title, sub, children, err }) {
  const meta = laneMeta(card?.lane);
  return (
    <div className="tq-card" style={{ borderLeftColor: edge(card?.lane) }}>
      <div className="tq-card-kicker"><span className="src"><SourceMark item={card} /></span><span className="dot" style={{ background: edge(card?.lane) }} />{kicker || meta.word}
        {card?.ref && <em>{card.ref}</em>}</div>
      {title && <div className="tq-card-title">{title}</div>}
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

// THE STEP NOTHING ELSE TAKES. Sending a reply, an agent finishing and pressing Next all leave the
// task open - so it sat in Tasks with nobody to end it, and the work tab now raises it again every
// hour until somebody does (the owner, 2026-09-15: "We need button for Completed inline with the
// chat"). One road: the same task.complete the spoken "close it" takes, so button and word cannot
// disagree about what closing means.
export function CompleteButton({ card, onDone, disabled }) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  if (!card?.tid) return null;
  const close = async () => {
    setBusy(true); setErr("");
    try { await runOperation(api, "task.complete", card.tid); onDone?.(`${card.ref || "The task"} is closed.`); }
    catch (e) { setErr(errText(e)); setBusy(false); }
  };
  return (
    <>
      <Button size="small" variant="outlined" disabled={busy || disabled} onClick={close} sx={quiet}
        title="Close the task - it stops coming back to Work">{busy ? "Closing…" : "Completed"}</Button>
      {err && <span className="tq-card-err">{err}</span>}
    </>
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
  const [full, setFull] = useState(true);
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
  return (
    <CardShell card={card} title={rv?.Subject || card.title} sub={rv ? (action ? "An agent proposed this. It runs only if you say so." : `To ${who}`) : "loading…"} err={err}>
      {rv?.Preview && !action && !full && <div className="tq-card-excerpt">{cleanText(rv.Preview).slice(0, 400)}</div>}
      {/* WHAT YOU ARE ANSWERING, said to be that. The block came up unlabelled above an unlabelled
          box, so the card opened with the task list and the owner had to work out which half was
          theirs (the owner, 2026-09-14: "though you need to see what you are responding to"). */}
      {full && card.mid && !action && <div className="tq-task-focus-label">They asked</div>}
      {full && card.mid && <CombinedTaskText card={card} />}
      {rv && !action && <div className="tq-task-focus-label" style={{ marginTop: 8 }}>Your draft</div>}
      {rv && (
        <TextField fullWidth multiline minRows={2} maxRows={9} value={value} onChange={(e) => setText(e.target.value)}
          placeholder={action ? "" : "No draft yet — choose Draft with AI, or write it here"}
          sx={{ mt: 1, "& textarea": { fontSize: 12.5, lineHeight: 1.5 } }} />
      )}
      {!action && stale && <div className="tq-card-err">New messages arrived after this draft. Refresh the draft with the latest context before sending.</div>}
      {!action && rv && draftState({ ...rv, HasDraft: value.trim() ? 1 : 0 }).line && <div className={draftState(rv).state === "failed" ? "tq-card-err" : "tq-card-excerpt"}>{draftState({ ...rv, HasDraft: value.trim() ? 1 : 0 }).line}</div>}
      {!action && sendBlockLine(rv) && <div className="tq-card-excerpt">{sendBlockLine(rv)}</div>}
      <div className="tq-card-actions">
        {action ? <>
          <Button size="small" variant="contained" disableElevation disabled={!!busy || !rv} startIcon={<DoneRoundedIcon />} onClick={() => decide("approve")} sx={primary}>{busy === "approve" ? "Running…" : "Run it"}</Button>
        </> : <>
          {rv?.CanSend !== false && (
            <Button size="small" variant="contained" disableElevation disabled={!!busy || !rv || !value.trim() || !!stale} startIcon={<SendRoundedIcon />} onClick={() => decide("approve")} sx={primary}>
              {busy === "approve" ? "Sending…" : "Approve & send"}</Button>
          )}
          {card.tid && <Button size="small" variant="outlined" disabled={!!busy || !rv}
            startIcon={<DoneRoundedIcon />} onClick={finish} sx={quiet}
            title="Marks the task done, dismisses the draft, and ends any live agent session. No reply is sent.">
            {busy === "finish" ? "Closing…" : "Mark done without sending"}</Button>}
          {card.mid && <Button size="small" onClick={() => setFull((v) => !v)} sx={faint}>{full ? "Fold" : "Read what they wrote"}</Button>}
        </>}
        <span className="sp" />
        <Where card={card} onOpenTask={onOpenTask} onTimeline={onTimeline} />
      </div>
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
    <CardShell card={card} kicker={working ? `the ${who} is working again` : card.paused ? "conversation paused" : `the ${who} ${KICK[subState(card)]}`} title={card.paused ? null : card.title}
      sub={working ? `${card.working || card.agent || who} · back at it - nothing for you until it stops` : card.paused ? `${card.working || card.agent || who} · saved after Taskuary stopped - ready to resume`
        // ONE sentence for the state (laneSays); when the question and its choices are drawn below, the bare form here
        : (card.choices || []).length && card.request_id ? says(subState(card), card.working || card.agent || who) : card.why || says(subState(card), card.working || card.agent || who)} err={err}>
      {card.paused && card.tid && <CombinedTaskText card={card} />}
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
      <div className="tq-card-actions">
        {card.paused
          ? <Button size="small" variant="contained" disableElevation disabled={busy} onClick={resume} sx={primary}>{busy ? "Continuing…" : "Continue this session"}</Button>
          : !(chat && live) && <Button size="small" variant="contained" disableElevation disabled={busy || !text.trim()} onClick={answer} sx={primary}>{busy ? "Sending…" : "Answer"}</Button>}
        <span className="sp" />
        <Button size="small" onClick={() => onOpenTask?.(card.tid, { start: false })} sx={faint}>
          {chat ? "Open the task" : "Open agent workspace"}</Button>
        <CompleteButton card={card} onDone={onDone} />
      </div>
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
      <div className="tq-card-actions">
        {e.join && <Button size="small" variant="outlined" component="a" href={e.join} target="_blank" rel="noreferrer" sx={quiet}>Join</Button>}
      </div>
    </CardShell>
  );
}

// a report landed: read it here, or go to the row
export function ReportCard({ card, onOpenTask, onTimeline, onDone }) {
  // Open, like the mail card: a digest behind a "Read it" is a digest nobody reads (the owner,
  // 2026-09-04: "Same with Morning digest should be open like here is your morning digest?").
  // .tq-card-full caps at 420px and scrolls, so a long report cannot run away with the page.
  const [full, setFull] = useState(true);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const rerun = async () => {
    setBusy(true); setErr("");
    try { const { data } = await api.post(`/api/reports/${card.source_id}/rerun`); onDone?.(`${data.title || card.title} is rerunning in the background - it lands back in the pipe when it's done.`); }
    catch (e) { setErr(errText(e)); }
    setBusy(false);
  };
  return (
    <CardShell card={card} kicker={card.bad ? "a report failed" : "a report landed"} title={card.title} sub={agoText(card.when)} err={err}>
      {card.bad && !full && <div className="tq-card-excerpt">The run failed — the cause is in the report.</div>}
      {full && card.brief_today && <TodayMeetingsStrip />}
      {full && card.mid && <FullText mid={card.mid} revision={card.presentation_revision} />}
      <div className="tq-card-actions">
        <Button size="small" variant="contained" disableElevation onClick={() => setFull((v) => !v)} sx={primary}>{full ? "Fold it" : "Read it"}</Button>
        <CompleteButton card={card} onDone={onDone} />
        <span className="sp" />
        <Where card={card} onOpenTask={onOpenTask} onTimeline={onTimeline} />
      </div>
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
      else onDone?.("A reply is open in Review.");
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
    <CardShell card={card} kicker="an agent finished" title={card.title} sub={`${card.who || "agent"} · ${agoText(card.when)}`} err={err}>
      {card.summary && !open && <div className="tq-card-excerpt">{card.summary}</div>}
      {open && <div className="tq-card-full">{report === null ? "…" : looksMd(report) ? <Md text={report} /> : report}</div>}
      <div className="tq-card-actions">
        <Button size="small" variant="contained" disableElevation onClick={show} sx={primary}>{open ? "Fold the report" : "Show the final report"}</Button>
        {!!card.mid && (
          <Button size="small" variant="outlined" disabled={busy} onClick={reply} sx={quiet}
            title="Write the sender a reply from what the agent found - it lands in Review for your yes">
            {busy ? "Drafting…" : "Reply from this"}</Button>
        )}
        <Button size="small" onClick={() => onOpenTask?.(card.tid)} sx={faint}>Open {card.ref}</Button>
        <CompleteButton card={card} onDone={onDone} />
        {onDone && <Button size="small" onClick={() => onDone("Seen.")} sx={faint}>Seen, next</Button>}
      </div>
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
  return (
    <CardShell card={card} kicker={words[card.idea_kind] || "slipped"} title={card.title} sub={card.why} err={err}>
      <div className="tq-card-actions">
        {card.idea_kind === "connect" && a.connector_type && (
          <Button size="small" variant="contained" disableElevation sx={primary}
            onClick={() => go("Connections", `connector=${a.connector_type}`)}>{a.planned ? `Vote for ${a.title || a.connector_type}` : `Connect ${a.title || a.connector_type}`}</Button>
        )}
        {card.idea_kind === "health" && a.tab && (
          <Button size="small" variant="contained" disableElevation sx={primary} onClick={() => go(a.tab, a.hash || "")}>Open {a.tab}</Button>
        )}
        {(card.idea_kind === "connect" || card.idea_kind === "health") && onAct && (
          <Button size="small" onClick={() => onAct(card.idea_kind === "connect" ? "Not for us - remembered." : "Seen.")} sx={faint}>
            {card.idea_kind === "connect" ? "Not for us" : "Seen"}</Button>
        )}
        <span className="sp" />
        <Where card={{ ...card, tid: a.tid || card.tid, mid: a.mid || card.mid }} onOpenTask={onOpenTask} onTimeline={onTimeline} />
      </div>
      {/* the buttons are the short way; saying it is the real one, and nothing says so (2026-09-04:
          "all the ideas should just say it and I will create it") */}
      <span className="tq-card-note">Or just say what you want done with it and I'll create it.</span>
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
  // that arrived and never the thread behind it.
  const [full, setFull] = useState(true);
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
  return (
    <CardShell card={card} kicker={card.kind === "fyi" ? "fyi" : suggestedKind === "coding" ? "coding · nobody on it" : card.kind === "todo" ? "on your list" : "asked you"} title={card.channel === "own" ? null : card.title}
      sub={`${card.who || "someone"} · ${agoText(card.when)}`} err={err}>
      {!full && card.preview && <div className="tq-card-excerpt">{card.preview}</div>}
      {full && card.mid && <CombinedTaskText card={card} />}
      <div className="tq-card-actions">
        <Button size="small" variant="outlined" onClick={() => setFull((v) => !v)} sx={quiet}>{full ? "Fold" : "Read it"}</Button>
        <CompleteButton card={card} onDone={onDone} />
        <span className="sp" />
        <Where card={card} onOpenTask={onOpenTask} onTimeline={onTimeline} />
      </div>
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
export function BriefCard({ card, onStart }) {
  return (
    <CardShell card={{ ...card, lane: "report" }} kicker="today" title={card.n ? `${card.n} thing${card.n === 1 ? "" : "s"} waiting on you` : "Nothing waiting on you"}
      sub={card.n ? `${card.mail} of them came in from a person. I'll take you through them one at a time - say Done, Later or Next to move on.` : "Ask me anything, or set something up."}>
      {!!card.n && (
        <div className="tq-card-actions">
          <Button size="small" variant="contained" disableElevation onClick={() => onStart?.("mail")} sx={primary}
            title="Only what people sent you - mail and chat">Just what came in</Button>
          <Button size="small" variant="outlined" onClick={() => onStart?.(null)} sx={quiet}
            title="Everything in the pipe, oldest first - mail, reports, agents, meetings">Everything, in order</Button>
        </div>
      )}
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
    <CardShell card={card} kicker={idle ? "waiting to start" : "the task you asked about"} title={card.title}
      sub={assistantFocus(card).lead || card.why} err={err}>
      {card.summary && <div className="tq-card-excerpt">{card.summary}</div>}
      {card.tid && <CombinedTaskText card={card} />}
      {idle && card.why_idle && <div className="tq-card-excerpt"><b>Why it has not started:</b> {card.why_idle}</div>}
      {!idle && <TextField fullWidth multiline minRows={1} maxRows={4} value={text} onChange={(e) => setText(e.target.value)}
        placeholder="Tell the agent on this task something — it is typed in when it next stops"
        onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); tell(); } }} sx={{ mt: 1, "& textarea": { fontSize: 12.5 } }} />}
      <div className="tq-card-actions">
        {idle
          ? <Button size="small" variant="contained" disableElevation disabled={!!busy} onClick={start} sx={primary}>{busy === "start" ? "Starting…" : "Start the agent"}</Button>
          : <Button size="small" variant="contained" disableElevation onClick={() => onOpenTask?.(card.tid)} sx={primary}>Open {card.ref}</Button>}
        {idle
          ? <Button size="small" variant="outlined" onClick={() => onOpenTask?.(card.tid)} sx={quiet}>Open {card.ref}</Button>
          : <Button size="small" variant="outlined" disabled={!!busy || !text.trim()} onClick={tell} sx={quiet}>{busy === "tell" ? "Queuing…" : "Tell the agent"}</Button>}
        <CompleteButton card={card} onDone={onDone} />
      </div>
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
    <CardShell card={card} kicker={`${items.length} fyi · nothing to do`} title={null} err={err}>
      {items.map((i) => (
        <div key={i.key} className={`tq-fyi${folded && open !== i.key ? " lean" : ""}`}>
          {/* The LINE is the item: it wraps rather than being cut, and it is said once - an
              assistant's idea files the same sentence as title and gist (fyiRow.gistFor). */}
          <div className="tq-fyi-line" onClick={folded ? () => setOpen((o) => (o === i.key ? null : i.key)) : undefined}>
            <SourceMark item={i} size={13} />
            <b>{i.who || "someone"}</b>
            <span className="t">{i.title}</span>
            {folded && <span className="chev">{open === i.key ? "\u25be" : "\u25b8"}</span>}
          </div>
          {open !== i.key && !folded && gistFor(i) && <div className="tq-fyi-gist">{gistFor(i)}</div>}
          {open === i.key && folded && gistFor(i) && <div className="tq-fyi-gist">{gistFor(i)}</div>}
          {open === i.key && i.mid && <FullText mid={i.mid} revision={i.presentation_revision || card.presentation_revision} />}
          {/* two doors, each named for what it does: one unfolds the message under this line, the
              other takes the item into the conversation. "Read" and "Dig in" said one thing twice.
              On a folded batch they belong to the line you opened - twenty of them is the problem. */}
          {(!folded || open === i.key) && (
          <div className="tq-fyi-doors">
            {i.mid && <Button size="small" onClick={() => setOpen((o) => (o === i.key ? null : i.key))} sx={faint}>
              {open === i.key ? "Hide" : "Full message"}</Button>}
            <Button size="small" onClick={() => onSurface?.(i.key)} sx={faint}>Talk about it</Button>
          </div>
          )}
          {/* ...and acting on it belongs to the ONE you opened. Four buttons on every row is twelve
              on a three-fyi card, and the card's whole point is that none of them needs you. */}
          {open === i.key && i.mid && (
            <div className="tq-card-actions" style={{ marginTop: 2 }}>
              <Button size="small" disabled={!!busy} onClick={() => reply(i)} sx={faint}>Reply</Button>
              <Button size="small" disabled={!!busy} onClick={() => propose("mine", i)} sx={faint}>Make task</Button>
              <Button size="small" disabled={!!busy} onClick={() => propose("coder", i)} sx={faint}>Coding agent</Button>
              <Button size="small" disabled={!!busy} onClick={() => propose("regular_agent", i)} sx={faint}>Regular agent</Button>
            </div>
          )}
        </div>
      ))}
      <div className="tq-card-actions">
        <Button size="small" variant="contained" disableElevation onClick={() => onDone?.(`Read — ${items.length} fyi let go.`)} sx={primary}>All read, next</Button>
        <span className="sp" />
        {items[0]?.mid && <Button size="small" onClick={() => onTimeline?.(items[0].mid)} sx={faint}>On the Timeline</Button>}
      </div>
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
      <div className="tq-card-actions">
        <span className="sp" />
        <Button size="small" onClick={() => onOpenTask?.(card.tid)} sx={faint}>Open {card.ref}</Button>
      </div>
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
      {/* The walk is scripted and reaches no model - but a question typed during it is an ordinary
          turn, answered beside the walk while the walk keeps its place (walk.py's own design). One
          line: it is a reassurance, not a paragraph to read fourteen times. */}
      <div className="tq-card-note">Questions? Ask below in your own words — the walk keeps your place.</div>
      <div className="tq-card-actions">
        {/* the checklist's five stops carry the label the panel's own row uses, so the walk and the
            panel name the same destination the same way; a tab stop is its tab and needs none */}
        {card.goto && <Button size="small" variant="contained" disableElevation onClick={() => go(card.goto)}
          sx={primary}>{card.goto.label || `Open ${card.goto.tab}`}</Button>}
        {/* Back and Next are one act each - a position moved (walk.go takes any stop). Start over is
            the reset the server always had and the card never offered (the owner, 2026-09-18: "we
            also need a button to start over the walk through"). */}
        {!first && <Button size="small" onClick={onBack} sx={faint}>‹ Back</Button>}
        {!last && <Button size="small" onClick={onNext} sx={faint}>Next ›</Button>}
        <span className="sp" />
        {!first && <Button size="small" onClick={onRestart} sx={faint} title="back to the first stop">Start over</Button>}
        <Button size="small" onClick={onFinish} sx={faint}>Finish</Button>
      </div>
    </CardShell>
  );
}
