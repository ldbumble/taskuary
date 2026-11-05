// EACH TURN ENDS IN THREE PARTS (the closeout-in-chat spec, 2026-11-04): what this is about, what the agent did, and the next steps - the
// drafts waiting on Send, the steps only the owner can take ("On you: …"), or "Nothing left to do here". Where the chat is the task's home the
// drafts are their cards, inside Next steps (Task 4.2: `next`, what Close out held - TaskPage's own, so each draft is drawn once); elsewhere a
// line each. An On you step's mark says whose it is, never a press.
import React, { useState } from "react";
import { Box, IconButton, Typography } from "@mui/material";
import SendIcon from "@mui/icons-material/ArrowUpward";
import api from "./api.js";
import { hasReply, nextSteps } from "./agentSummary.js";
import { Md } from "./md.jsx";
import { readingOf } from "./threadReading.js";
import { dayLabel, fmtTime12 } from "./dates.js";
const dayWord = (at) => { const d = dayLabel(at); return d && d !== "Today" ? `${d} ` : ""; };
import { MicButton } from "./ui.jsx";
import { ALERT_INK, BORDER, DIM, FAINT, INK } from "./theme.jsx";

// ...a chatbot's answer, split into sections to read (the owner, 2026-11-05): a short bold heading over each, no rules, no boxes but the email's
const HEAD = { display: "block", color: INK, fontSize: 13.5, fontWeight: 700, mt: 1.5, mb: 0.25 };
const Head = ({ children, first }) => <Typography component="span" sx={{ ...HEAD, ...(first ? { mt: 0 } : {}) }}>{children}</Typography>;
const LINE = { fontSize: 13.5, lineHeight: 1.55, color: INK, overflowWrap: "anywhere" };
const who = (r) => r.FromName || r.FromEmail || "";

const PARA = { ...LINE, mt: 1 };
// A REGULAR CHAT (the owner, 2026-11-05: "it's just a chat with it summarizing in different paragraphs (short text as possible) this is the chat,
// this is what i did about it and this is what i suggest" - "hate all the boxes ... no lines"): plain paragraphs, no rules, no boxes, no
// "On you:" line per step - the steps only the owner can take are ONE sentence, the first three and how many more the To do holds
const ONYOU_SHOWN = 3;
const OnYou = ({ items }) => {
  if (!items.length) return null;
  const shown = items.slice(0, ONYOU_SHOWN).map((i) => i.text.replace(/[.\s]+$/, "")), more = items.length - shown.length;
  return <Typography data-tq-on-you={items.map((i) => i.id || "").join(" ")} sx={LINE}>
    {`For you to do: ${shown.join("; ")}${more > 0 ? `, and ${more} more on the To do` : ""}.`}</Typography>;
};
// NEXT STEPS HOLD THE REPLY (the owner, 2026-11-05: "next steps should be above or combined with suggested reply as that's the next steps.
// meaning review the file then send it"): one head, what is on the owner first, then the draft with its Send
const DraftHead = () => <Head>Next steps</Head>;

export default function AgentSummary({ summary, reviews = [], checklist = [], acts = [], cards = true, next = null, folded = false }) {
  if (!summary) return null;
  const did = String(summary.did || "").trim(), about = String(summary.about || "").trim();
  // ...a turn that is history keeps the draft it left, read-only: what was drafted and to whom, no Send (the owner, 2026-11-05)
  // ...read from the draft itself (its id is all the turn keeps), with where it went since: sent, set aside, or still waiting
  const drafted = (summary.drafted || []).map((x) => (reviews || []).find((r) => r.ReviewId === x?.review)).filter((r) => r && String(r.DraftText || "").trim());
  const fate = (r) => r.Status === "sent" || r.DeliveryState === "sent" ? "sent" : r.Status === "pending" ? "" : "not sent";
  const Drafted = () => drafted.map((r) => <Box key={r.ReviewId} data-tq-drafted-then="" sx={{ mt: 1, px: 1.5, py: 1, borderLeft: "3px solid #dcd6ca", color: DIM, fontSize: 13, lineHeight: 1.5 }}>
    <Typography component="span" sx={{ display: "block", fontSize: 11.5, fontWeight: 700, color: FAINT, mb: 0.25 }}>
      {["Drafted", who(r) && `to ${who(r)}`, fate(r)].filter(Boolean).join(" · ")}</Typography>
    <Box sx={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere", maxHeight: 220, overflow: "auto" }}>{r.DraftText}</Box></Box>);
  if (folded) return did || drafted.length ? (<>
    {did && <Box component="details" data-tq-summary="folded" className="tq-aui-summary" sx={{ mt: 0.75 }}>
      {/* ...one line: what it did, cut where the line ends - the whole of it a press away */}
      <Box component="summary" sx={{ ...HEAD, mt: 0, cursor: "pointer", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", "&:hover": { color: INK } }}>
        What I did<Box component="span" sx={{ fontWeight: 400, color: DIM, ml: 0.75 }}>{did.split("\n")[0]}</Box></Box>
      <Box sx={{ ...LINE, color: DIM }}><Md text={did} /></Box>
    </Box>}
    <Drafted /></>) : null;
  const { drafts, onYou, held, nothing } = nextSteps({ summary, reviews, checklist, acts, cards });
  return (
    <Box data-tq-summary="open" className="tq-aui-summary">
      {!!about && <><Head first>What this is about</Head><Typography data-tq-summary-about="" sx={LINE}>{about}</Typography></>}
      {!!did && <><Head first={!about}>What I did</Head><Box data-tq-summary-did="" sx={LINE}><Md text={did} /></Box></>}
      {(next && hasReply(reviews)) || (drafts.length && !next) || held.length || onYou.length || nothing ? <DraftHead /> : null}
      <OnYou items={onYou} />
      {!!held.length && <Typography data-tq-summary-held={held.length} sx={LINE}>
        {held.length === 1 ? "One step waits for your Approve, below." : `${held.length} steps wait for your Approve, below.`}</Typography>}
      {!next && drafts.map((r) => <Typography key={r.ReviewId} data-tq-summary-draft={r.ReviewId} sx={LINE}>
        {who(r) ? `A reply to ${who(r)} is drafted and waits for your Send.` : "A reply is drafted and waits for your Send."}</Typography>)}
      {next ? <Box sx={{ mt: 0.75 }}>{next}</Box> : null}
      {nothing && <Typography data-tq-nothing-left="" sx={{ ...LINE, color: DIM }}>Nothing left to do here.</Typography>}
    </Box>
  );
}

// WHEN NO AGENT RAN (the spec's reply the drafter wrote): triage's reading, the drafter's why as "What I did", then the card - TaskPage's Close
// out body (`cards`) - and the box. The box is Send to agent's road (the dispatch, which makes the task the general agent's) with the owner's
// own words; from its first turn on the chat is the agent's. `box` off where the task's own agent form already starts it (a general task not begun).
export function NoAgentChat({ task, reviews = [], checklist = [], mails = [], cards = null, box = true, onStarted }) {
  const [text, setText] = useState(""), [busy, setBusy] = useState(false), [err, setErr] = useState("");
  const why = String((reviews || []).find((r) => r?.Status === "pending" && r.DraftWhy)?.DraftWhy || "").trim();
  const { onYou } = nextSteps({ reviews, checklist, cards: false });
  // ...the ask in one plain paragraph: what the thread wants (triage's reading), never its labelled lines
  const ask = readingOf(task?.ThreadJson)?.asking || "";
  const send = async () => {
    const words = text.trim();
    if (!words || busy) return;
    setBusy(true); setErr("");
    try { const { data } = await api.post(`/api/tasks/${task.TaskId}/dispatch`, { kind: "general", instruction: words }); setText(""); onStarted?.(data); }
    catch (e) { setErr(e?.response?.data?.detail || "Could not start the agent - check that an AI is connected under Connections, then send it again."); }
    finally { setBusy(false); }
  };
  // WHAT CAME IN, ON THE RIGHT, as every input in the chat is (the owner, 2026-11-05): each message of the task, oldest first - theirs by name,
  // the owner's own as You - with its time; the read of it and the box under them
  const said = (mails || []).filter((m) => m && (m.OwnText || m.ReadText || m.BodyText || m.Subject)).slice(-8);
  const mine = (m) => m.Direction === "out" || m.Status === "context";
  return (
    <Box data-tq-no-agent-chat="" sx={{ minWidth: 0, display: "flex", flexDirection: "column", mt: 1, flex: "1 1 auto", minHeight: 0 }}>
      {!!said.length && <div className="tq-aui-chat" style={{ display: "contents" }}><div className="tq-aui-message tq-aui-brief" data-tq-no-agent-inputs="">
        {said.map((m) => <div key={m.MessageId} className="tq-aui-arrived" data-tq-chat-arrived="">
          <span className="tq-aui-arrived-head">{[mine(m) ? "You" : (m.FromName || m.FromEmail || "Someone"), m.SentAt && `${dayWord(m.SentAt)}${fmtTime12(m.SentAt)}`].filter(Boolean).join(" · ")}</span>
          <span className="tq-aui-arrived-words" title={String(m.OwnText || m.ReadText || m.BodyText || "")}>{String(m.OwnText || m.ReadText || m.BodyText || m.Subject || "").trim().slice(0, 600)}</span>
        </div>)}
      </div></div>}
      <Box sx={{ pb: 1 }}>
        {!!ask && <><Head first>What this is about</Head><Typography data-tq-chat-ask="" sx={LINE}>{ask}</Typography></>}
        {!!why && <><Head first={!ask}>What I did</Head><Typography data-tq-draft-why="" sx={LINE}>{why}</Typography></>}
        {cards ? <Box>{hasReply(reviews) && <DraftHead />}{cards}</Box> : null}
        {onYou.length ? <><Head>Next steps</Head><OnYou items={onYou} /></> : null}
      </Box>
      {box && <Box component="form" onSubmit={(e) => { e.preventDefault(); send(); }}
        sx={{ display: "flex", alignItems: "flex-end", gap: 0.5, px: 1, py: 0.5, border: `1px solid ${BORDER}`, borderRadius: 2, bgcolor: "#fff", mt: "auto" }}>
        <Box component="textarea" data-tq-no-agent-box="" rows={1} value={text} disabled={busy} onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }}
          placeholder="Tell me what's wrong, or ask about anything here…"
          sx={{ flex: 1, minWidth: 0, resize: "none", border: 0, outline: 0, font: "inherit", fontSize: 13.5, lineHeight: 1.5, color: INK, bgcolor: "transparent", py: 0.5 }} />
        <MicButton size={18} sx={{ color: "#6b5f45", p: 0.5 }} onText={(t) => setText((w) => (w.trim() ? `${w.trimEnd()} ${t}` : t))} />
        <IconButton type="submit" size="small" data-tq-no-agent-send="" aria-label="Send to the agent" disabled={busy || !text.trim()}
          title="Starts the agent on this task with your words"><SendIcon fontSize="small" /></IconButton>
      </Box>}
      {!!err && <Typography role="alert" sx={{ px: 1.5, pb: 1, fontSize: 12.5, color: ALERT_INK }}>{err}</Typography>}
    </Box>
  );
}
