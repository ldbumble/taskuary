// The cards under Taskuary's lines. Commentary explains; the clearly labelled button acts - so
// the model never chooses a card (funnelPile.cardFor does, by kind) and never claims an action
// happened. Every button here calls an endpoint that already exists for the Timeline, the Review
// queue or the Board; the card only puts it under the sentence that was just said. Reading
// happens IN the card (the full text unfolds under it) and every card links to where the whole of
// it lives - the task, or the row on the Timeline - because everything is the chat.
import React, { useEffect, useState } from "react";
import { Button, TextField } from "@mui/material";
import SendRoundedIcon from "@mui/icons-material/SendRounded";
import RefreshRoundedIcon from "@mui/icons-material/RefreshRounded";
import DoneRoundedIcon from "@mui/icons-material/DoneRounded";
import EventIcon from "@mui/icons-material/Event";
import TerminalIcon from "@mui/icons-material/Terminal";
import api from "./api.js";
import { ChannelIcon, TaskuaryMark, cleanText, fmtDateTime } from "./ui.jsx";
import { Md, looksMd } from "./md.jsx";
import { ROLES, ASSISTANT } from "./theme.jsx";
import { laneMeta, ageText } from "./funnelPile.js";
import { TerminalPane } from "./TerminalView.jsx";
import { RepoPicker } from "./RepoPicker.jsx";

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
  if (item.kind === "setup" || item.kind === "brief" || (item.kind === "idea" && !item.channel)) return <TaskuaryMark size={size} />;
  if (item.kind === "fyis" && !item.channel) return <TaskuaryMark size={size} />;
  return <ChannelIcon channel={item.channel || "email"} sx={{ fontSize: size }} />;
}

// the link every card carries: the task when there is one, else the row on the Timeline
const Where = ({ card, onOpenTask, onTimeline }) => card?.tid
  ? <Button size="small" onClick={() => onOpenTask?.(card.tid)} sx={faint}>Open {card.ref || "task"}</Button>
  : card?.mid ? <Button size="small" onClick={() => onTimeline?.(card.mid)} sx={faint}>On the Timeline</Button> : null;

// the whole text, unfolded under the card on request - a report as markdown, a mail as it was written
function FullText({ mid }) {
  const [doc, setDoc] = useState(null);
  useEffect(() => {
    let live = true;
    api.get(`/api/messages/${mid}`).then(({ data }) => live && setDoc(data)).catch((e) => live && setDoc({ error: errText(e) }));
    return () => { live = false; };
  }, [mid]);
  if (!doc) return <div className="tq-card-full">…</div>;
  if (doc.error) return <div className="tq-card-err">{doc.error}</div>;
  const body = cleanText(doc.BodyText || "");
  const cut = body.indexOf("\n--- raw data ---");
  const text = cut >= 0 ? body.slice(0, cut) : body;
  return (
    <div className="tq-card-full">
      {looksMd(text) ? <Md text={text} /> : (text || "(empty)")}
      {doc.SourceLink && <div className="tq-card-note"><a href={doc.SourceLink} target="_blank" rel="noreferrer" style={{ color: "#55697a" }}>open the original</a></div>}
    </div>
  );
}

// A task is the grouping boundary after triage. Fetching `/thread` here would pull the whole Teams
// or WhatsApp room (and made TQ-0367 say +19); task detail tells us exactly which messages triage
// combined. Context rows helped triage decide, but are not part of the grouped ask shown to the owner.
function CombinedTaskText({ card }) {
  const [doc, setDoc] = useState(null);
  useEffect(() => {
    let live = true;
    if (!card?.tid) { setDoc({ messages: [] }); return () => { live = false; }; }
    api.get(`/api/tasks/${card.tid}`).then(({ data }) => live && setDoc(data)).catch((e) => live && setDoc({ error: errText(e) }));
    return () => { live = false; };
  }, [card?.tid, card?.mid]);
  if (!card?.tid) return <FullText mid={card?.mid} />;
  if (!doc) return <div className="tq-card-full">â€¦</div>;
  if (doc.error) return <div className="tq-card-err">{doc.error}</div>;
  const messages = (doc.messages || []).filter((m) => String(m.Status || "") !== "context");
  if (messages.length <= 1) return <FullText mid={card?.mid} />;
  return (
    <div className="tq-card-full">
      <div className="tq-card-note" style={{ marginBottom: 7, fontWeight: 700 }}>
        {messages.length} messages combined by triage â€” shown together
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
  );
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
  const [full, setFull] = useState(true);
  useEffect(() => {
    let live = true;
    api.get("/api/reviews", { params: { status: "pending" } }).then(({ data }) => {
      if (!live) return;
      setRv((data.data || []).find((x) => x.ReviewId === card.rid) || { gone: true });
    }).catch((e) => live && setErr(errText(e)));
    return () => { live = false; };
  }, [card.rid, card.mid]);
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
  if (rv?.gone) return <CardShell card={card} kicker="already handled" title={card.title} sub="This one is no longer waiting on you." />;
  return (
    <CardShell card={card} title={rv?.Subject || card.title} sub={rv ? (action ? "An agent proposed this. It runs only if you say so." : `To ${who}`) : "loading…"} err={err}>
      {rv?.Preview && !action && !full && <div className="tq-card-excerpt">{cleanText(rv.Preview).slice(0, 400)}</div>}
      {full && card.mid && <CombinedTaskText card={card} />}
      {rv && (
        <TextField fullWidth multiline minRows={2} maxRows={9} value={value} onChange={(e) => setText(e.target.value)}
          placeholder={action ? "" : "No draft yet — choose Draft with AI, or write it here"}
          sx={{ mt: 1, "& textarea": { fontSize: 12.5, lineHeight: 1.5 } }} />
      )}
      {!action && stale && <div className="tq-card-err">New messages arrived after this draft. Refresh the draft with the latest context before sending.</div>}
      <div className="tq-card-actions">
        {action ? <>
          <Button size="small" variant="contained" disableElevation disabled={!!busy || !rv} startIcon={<DoneRoundedIcon />} onClick={() => decide("approve")} sx={primary}>{busy === "approve" ? "Running…" : "Run it"}</Button>
          <Button size="small" variant="outlined" disabled={!!busy} onClick={() => decide("reject")} sx={quiet}>Dismiss</Button>
        </> : <>
          {rv?.CanSend !== false && (
            <Button size="small" variant="contained" disableElevation disabled={!!busy || !rv || !value.trim() || !!stale} startIcon={<SendRoundedIcon />} onClick={() => decide("approve")} sx={primary}>
              {busy === "approve" ? "Sending…" : "Approve & send"}</Button>
          )}
          <Button size="small" variant="outlined" disabled={!!busy || !rv} startIcon={<RefreshRoundedIcon />} onClick={redraft} sx={quiet}>{busy === "redraft" ? "Drafting…" : stale ? "Refresh draft" : rv?.DraftText ? "Redraft" : "Draft with AI"}</Button>
          <Button size="small" variant="outlined" disabled={!!busy} onClick={() => decide("no_reply")} sx={{ ...quiet, ...faint }}>Dismiss</Button>
          {card.mid && <Button size="small" onClick={() => setFull((v) => !v)} sx={faint}>{full ? "Fold" : "Read what they wrote"}</Button>}
        </>}
        <span className="sp" />
        <Where card={card} onOpenTask={onOpenTask} onTimeline={onTimeline} />
      </div>
    </CardShell>
  );
}

// an agent parked on a question: its last lines, and a box that answers it
export function AgentCard({ card, onDone, onOpenTask }) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [big, setBig] = useState(false);
  // A hand-off is not the main Assistant doing the work. Keep the other agent's workspace folded
  // unless the owner explicitly asks to see it; opening a regular API agent inline made the
  // orchestration chat look as though it had silently changed identities.
  const [live, setLive] = useState(false);
  const answer = async () => {
    if (!text.trim()) return;
    setBusy(true); setErr("");
    try { await api.post(`/api/tasks/${card.tid}/waitroom`, { text }); onDone?.(`Told ${card.agent || "the agent"}: “${text.trim().slice(0, 80)}”`); }
    catch (e) { setErr(errText(e)); }
    setBusy(false);
  };
  const working = card.lane === "working";
  // ...and the two ways an agent ENDS, in the chat, where the owner is looking (2026-09-03: "we need
  // to button to close down agent in the chat. it's finished.."). Wrapping up is the whole ending -
  // the transcript becomes the report, proposals become reviews, the reply gets drafted, the task
  // closes; stopping just ends the session and leaves the task where it is.
  const [ending, setEnding] = useState("");
  const finish = async (wrap) => {
    setEnding(wrap ? "wrap" : "stop"); setErr("");
    try {
      if (wrap) await api.post(`/api/tasks/${card.tid}/wrap`, { close: true });
      else await api.post(`/api/tasks/${card.tid}/agent/stop`);
      onDone?.(wrap ? `${card.ref || "The task"} wrapped up - the report is on it and the task is closed.`
                    : `${card.agent || "The agent"} stopped. ${card.ref || "The task"} is still open.`);
    } catch (e) { setErr(errText(e)); }
    setEnding("");
  };
  return (
    <CardShell card={card} kicker={working ? "the agent is working again" : card.asking ? "the agent asked" : "the agent stopped"} title={card.title}
      sub={`${card.working || card.agent || "agent"} · ${working ? "back at it - nothing for you until it stops" : card.asking ? "waiting on your answer" : "parked at its prompt"}`} err={err}>
      {card.sid && live ? (
        <div className="tq-card-term" style={{ height: big ? 640 : 340 }}>
          <TerminalPane sid={card.sid} height={big ? "640px" : "340px"} autoFocus={false} />
        </div>
      ) : !!card.tail?.length && <div className="tq-card-tail">{card.tail.join("\n")}</div>}
      {card.sid && (
        <div className="tq-card-note" style={{ display: "flex", gap: 10, alignItems: "center" }}>
          <span>{live ? "This is the agent's own screen — click in and type to answer it there." : "Screen folded."}</span>
          <span className="sp" />
          <Button size="small" onClick={() => setBig((b) => !b)} sx={faint}>{big ? "Smaller" : "Bigger"}</Button>
          <Button size="small" onClick={() => setLive((l) => !l)} sx={faint}>{live ? "Fold" : "Show the screen"}</Button>
        </div>
      )}
      <TextField fullWidth multiline minRows={1} maxRows={5} value={text} onChange={(e) => setText(e.target.value)}
        placeholder={card.asking ? "Or answer here — it is typed in when the agent next stops" : "Tell it what to do next"}
        onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); answer(); } }}
        sx={{ mt: 1, "& textarea": { fontSize: 12.5 } }} />
      <div className="tq-card-actions">
        <Button size="small" variant="contained" disableElevation disabled={busy || !text.trim()} onClick={answer} sx={primary}>{busy ? "Sending…" : "Answer"}</Button>
        <Button size="small" variant="outlined" disabled={!!ending} onClick={() => finish(true)} sx={quiet}
          title="File its report, draft the reply and close the task">{ending === "wrap" ? "Wrapping up…" : "It's finished - wrap it up"}</Button>
        <Button size="small" disabled={!!ending} onClick={() => finish(false)} sx={faint}
          title="End the session and leave the task open">{ending === "stop" ? "Stopping…" : "Just stop it"}</Button>
        <span className="sp" />
        <Button size="small" onClick={() => onOpenTask?.(card.tid, { start: false })} sx={faint}>Open agent workspace</Button>
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
        <Button size="small" variant="contained" disableElevation disabled={busy} onClick={prep} sx={primary}>{busy ? "Opening…" : "Prep me"}</Button>
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
    <CardShell card={card} kicker={card.bad ? "a report failed" : "a report landed"} title={card.title} sub={`${ageText(card.when)} ago`} err={err}>
      {card.bad && !full && <div className="tq-card-excerpt">The run failed — the cause is in the report.</div>}
      {full && card.mid && <FullText mid={card.mid} />}
      <div className="tq-card-actions">
        <Button size="small" variant="contained" disableElevation onClick={() => setFull((v) => !v)} sx={primary}>{full ? "Fold it" : "Read it"}</Button>
        {card.source_id && <Button size="small" variant="outlined" disabled={busy} onClick={rerun} sx={quiet}>{busy ? "Queuing…" : "Run it again"}</Button>}
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
  const show = async () => {
    setOpen((o) => !o);
    if (report !== null) return;
    try {
      const { data } = await api.get(`/api/tasks/${card.tid}`);
      const rep = (data.comments || []).slice().reverse().find((c) => String(c.Body || "").startsWith("CODER REPORT") || String(c.Body || "").startsWith("HANDOVER NOTE"));
      setReport(rep ? rep.Body.replace(/^(CODER REPORT|HANDOVER NOTE)\s*/, "") : "No report was filed on this task.");
    } catch (e) { setReport(errText(e)); }
  };
  return (
    <CardShell card={card} kicker="an agent finished" title={card.title} sub={`${card.who || "agent"} · ${ageText(card.when)} ago`} err={err}>
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
        {onDone && <Button size="small" onClick={() => onDone("Seen.")} sx={faint}>Seen, next</Button>}
      </div>
    </CardShell>
  );
}

// the assistant's own line: the slipped ask, the promise, the thread gone quiet
export function IdeaCard({ card, onAct, onOpenTask, onTimeline }) {
  const a = card.action || {};
  const [busy, setBusy] = useState("");
  const [err, setErr] = useState("");
  const act = async (verb, receipt) => {
    setBusy(verb); setErr("");
    try { const { data } = await api.post("/api/concierge/act", { key: card.key, verb }); onAct?.(receipt, data); }
    catch (e) { setErr(errText(e)); }
    setBusy("");
  };
  const words = { followup: "waiting on them", promise: "you promised", asked: "slipped", cold: "gone quiet", idea: "worth a thought" };
  return (
    <CardShell card={card} kicker={words[card.idea_kind] || "slipped"} title={card.title} sub={card.why} err={err}>
      <div className="tq-card-actions">
        {(a.type === "followup" || (a.mid && card.idea_kind !== "cold")) && (
          <Button size="small" variant="contained" disableElevation disabled={!!busy} onClick={() => act("followup", "Follow-up drafted — it waits for your yes.")} sx={primary}>{busy === "followup" ? "Drafting…" : "Draft follow-up"}</Button>
        )}
        {a.mid && <Button size="small" variant="outlined" disabled={!!busy} onClick={() => act("task", "Made it a task.")} sx={quiet}>Make it a task</Button>}
        <Button size="small" variant="outlined" disabled={!!busy} onClick={() => act("dismiss", "Noted — not this.")} sx={{ ...quiet, ...faint }}>Not this</Button>
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
  const [notOurs, setNotOurs] = useState(false);
  const [sender, setSender] = useState(false);
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
    <CardShell card={card} kicker={card.kind === "fyi" ? "fyi" : suggestedKind === "coding" ? "coding · nobody on it" : card.kind === "todo" ? "on your list" : "asked you"} title={card.title}
      sub={`${card.who || "someone"} · ${ageText(card.when)} ago`} err={err}>
      {!full && card.preview && <div className="tq-card-excerpt">{card.preview}</div>}
      {full && card.mid && <CombinedTaskText card={card} />}
      <div className="tq-card-actions">
        <Button size="small" variant="outlined" onClick={() => setFull((v) => !v)} sx={quiet}>{full ? "Fold" : "Read it"}</Button>
        {asks && <Button size="small" variant="contained" disableElevation disabled={!!busy} sx={primary}
          onClick={() => post("reply", `/api/messages/${card.mid}/reply`, { draft: true }, null,
            (d) => onSurface?.(d.reviewId ? `review:${d.reviewId}` : null, "Drafting a reply…"))}>{busy === "reply" ? "Drafting…" : "Reply"}</Button>}
        <Button size="small" variant="outlined" disableElevation disabled={!!busy} sx={quiet}
          title="Starts a CLI coding agent in a repository" onClick={() => startAgent("coding")}>
          {busy === "agent" ? "Starting…" : "Coding agent"}</Button>
        <Button size="small" variant="outlined" disableElevation disabled={!!busy} sx={quiet}
          title="Starts a non-coding agent for reading, analysis, or other general work" onClick={() => startAgent("general")}>
          {busy === "agent" ? "Starting…" : "Regular agent"}</Button>
        <Button size="small" variant="outlined" disabled={!!busy} sx={quiet}
          onClick={() => post("chat", `/api/messages/${card.mid}/chat`, {}, "Opened in a full workspace.", (d) => d.taskId && onOpenTask?.(d.taskId))}>Talk it through</Button>
        {/* On an fyi too: `asks` hid this, so the one road OFF an fyi that is actually work - turning
            it into a task - was the one thing the card could not do. The owner asked for exactly
            that ("turn into x, move on, make task for later", 2026-09-04), and the assistant's own
            line now offers it out loud, so the button has to be there to keep the promise. */}
        {card.mid && <Button size="small" variant="outlined" disabled={!!busy} sx={quiet}
          onClick={() => post("mine", `/api/messages/${card.mid}/mine`, { kind: "task" }, "On your list.")}>
          {busy === "mine" ? "…" : asks ? "Mine, I'll do it" : "Make it a task"}</Button>}
        <span className="sp" />
        <Button size="small" disabled={!!busy} onClick={() => setNotOurs((v) => !v)} sx={faint}>Not ours…</Button>
        <Button size="small" disabled={!!busy} onClick={() => setSender((v) => !v)} sx={faint}>Ignore this sender…</Button>
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
      {sender && (
        <div className="tq-card-actions" style={{ marginTop: 6 }}>
          <Button size="small" variant="outlined" disabled={!!busy} sx={quiet}
            onClick={() => post("rule", `/api/messages/${card.mid}/ignore-sender`, { how: "rule" },
              (d) => `An exclusion rule now skips ${d.sender}${d.affected ? ` — and ${d.affected} of their older messages left the Timeline` : ""}. Settings → Rules turns it back off.`)}>
            {busy === "rule" ? "…" : "Add an exclusion rule"}</Button>
          <Button size="small" variant="outlined" disabled={!!busy} sx={{ ...quiet, ...faint }}
            onClick={() => post("justmem", `/api/messages/${card.mid}/ignore-sender`, { how: "memory" },
              (d) => `Remembered. Mail from ${d.sender} keeps arriving and stays readable — triage files it from now on.`)}>
            {busy === "justmem" ? "…" : "Just remember it"}</Button>
          <span className="tq-card-note">A rule stops their mail reaching triage at all and hides what already arrived. A memory leaves everything readable and teaches triage the verdict.</span>
        </div>
      )}
      {notOurs && (
        <div className="tq-card-actions" style={{ marginTop: 6 }}>
          <Button size="small" variant="outlined" disabled={!!busy} sx={quiet}
            onClick={() => post("remember", `/api/messages/${card.mid}/not-mine`, { scope: "subject" }, "Not ours — remembered. This kind of mail is filed from now on.")}>
            {busy === "remember" ? "…" : "Not ours — remember it"}</Button>
          <Button size="small" variant="outlined" disabled={!!busy} sx={{ ...quiet, ...faint }}
            onClick={() => post("once", `/api/messages/${card.mid}/file`, { learn: false }, "Filed — just this once.")}>
            {busy === "once" ? "…" : "Not ours, just this once"}</Button>
          <span className="tq-card-note">Remembering writes a verdict triage reads on every later message like this one.</span>
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
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const tell = async () => {
    if (!text.trim()) return;
    setBusy(true); setErr("");
    try { await api.post(`/api/tasks/${card.tid}/waitroom`, { text }); onDone?.(`Queued for the agent on ${card.ref}: “${text.trim().slice(0, 80)}”`); }
    catch (e) { setErr(errText(e)); }
    setBusy(false);
  };
  return (
    <CardShell card={card} kicker="the task you asked about" title={card.title} sub={card.why} err={err}>
      {card.summary && <div className="tq-card-excerpt">{card.summary}</div>}
      <TextField fullWidth multiline minRows={1} maxRows={4} value={text} onChange={(e) => setText(e.target.value)}
        placeholder="Tell the agent on this task something — it is typed in when it next stops"
        onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); tell(); } }} sx={{ mt: 1, "& textarea": { fontSize: 12.5 } }} />
      <div className="tq-card-actions">
        <Button size="small" variant="contained" disableElevation onClick={() => onOpenTask?.(card.tid)} sx={primary}>Open {card.ref}</Button>
        <Button size="small" variant="outlined" disabled={busy || !text.trim()} onClick={tell} sx={quiet}>{busy ? "Queuing…" : "Tell the agent"}</Button>
      </div>
    </CardShell>
  );
}

// a handful of fyi's: who said what, read any in place, dig into one, or let them all go
export function FyisCard({ card, onDone, onSurface, onTimeline }) {
  const [open, setOpen] = useState(null);
  const items = card.items || [];
  return (
    <CardShell card={card} kicker={`${items.length} fyi · nothing to do`} title={null}>
      {items.map((i) => (
        <div key={i.key} className="tq-fyi">
          <div className="tq-fyi-row">
            <SourceMark item={i} size={13} />
            <b>{i.who || "someone"}</b><span className="t">{i.title}</span>
            <Button size="small" onClick={() => setOpen((o) => (o === i.key ? null : i.key))} sx={faint}>{open === i.key ? "Fold" : "Read"}</Button>
            <Button size="small" onClick={() => onSurface?.(i.key)} sx={faint}>Dig in</Button>
          </div>
          {open !== i.key && i.preview && <div className="tq-fyi-gist">{i.preview}</div>}
          {open === i.key && i.mid && <FullText mid={i.mid} />}
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
        <Button size="small" variant="contained" disableElevation disabled={busy} onClick={close} sx={primary}>{busy ? "Closing…" : `Close ${card.ref}`}</Button>
        <Button size="small" variant="outlined" onClick={() => onDone?.("Kept open.")} sx={quiet}>Keep it open</Button>
        <span className="sp" />
        <Button size="small" onClick={() => onOpenTask?.(card.tid)} sx={faint}>Open {card.ref}</Button>
      </div>
    </CardShell>
  );
}

// "set something up": your words open a guided Assistant task. It may drive an embedded browser,
// but no coding session or checkout is involved unless the owner explicitly asks for one later.
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
