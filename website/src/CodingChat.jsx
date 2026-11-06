// A CODING TASK IS THE SAME ONE CHAT (the owner, 2026-11-06: "combine the close out action in the coding cli as well. basically making general and
// coding agent more similar. i do like you can review the code diffs if you want... i like the editor that you can see the code").
//
// The general chat's look, its classes and its step lines (generalWorkspace.css, AgentStepRows): the mail that came in on the right, each turn
// of the agent on the left - its words, its work folded into "N steps", every edit its own row that opens on the diff - then the drafted reply
// with Send (`next`, Close out's own cards), the landing card, how it closed, and the AI it used. One thin box under it all: what is typed goes
// into the running CLI (the waiting room types it in - terminal.type_into), or picks the session back up when none runs (/continue-work).
// The live terminal is a "Terminal" toggle on the chat, inside it, never a second column: it opens by itself only when the CLI's screen asks
// what nothing typed here can answer (a chooser, a permission prompt, a sign-in), and the owner can open it to watch.
// OVER ACP (acpcoding.py) the box is a prompt (sent when the turn ends, if one runs), Stop ends the turn (session/cancel), a permission is a
// card here, and the Terminal is its commands' live output - offered only once there is some, never a blank pane.
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Box } from "@mui/material";
import TerminalIcon from "@mui/icons-material/TerminalRounded";
import MailOutlineIcon from "@mui/icons-material/MailOutline";
import WhatsAppIcon from "@mui/icons-material/WhatsApp";
import ChatBubbleOutlineIcon from "@mui/icons-material/ChatBubbleOutline";
import PersonOutlineIcon from "@mui/icons-material/PersonOutline";
import WriteIcon from "@mui/icons-material/EditNoteRounded";
import CloseIcon from "@mui/icons-material/Close";
import DoneIcon from "@mui/icons-material/CheckBoxRounded";
import NowIcon from "@mui/icons-material/IndeterminateCheckBoxRounded";
import TodoIcon from "@mui/icons-material/CheckBoxOutlineBlankRounded";
import api from "./api.js";
import { onLive, touches } from "./live.js";
import { stillHeld } from "./heldLines.js";
import { chatRows, workCount } from "./codingChat.js";
import { PermissionCards } from "./AgentChannels.jsx";
import { teammateLine } from "./agentChannels.js";
import { AgentSteps } from "./AgentStepRows.jsx";
import { Hunk } from "./DiffView.jsx";
import { Md } from "./md.jsx";
import { TerminalPane } from "./TerminalView.jsx";
import { AttachChip, usePromptImages, withImages } from "./promptImages.jsx";
import { PromptBox } from "./AgentSummary.jsx";
import { AGENT_TURN, MESSAGE } from "./kinds.js";
import { baseName } from "./agentSteps.js";
import { dayLabel, fmtTime12 } from "./dates.js";
import { plural } from "./timeWords.js";
import { BORDER, PANEL2 } from "./theme.jsx";
import "./generalWorkspace.css";
import "./agentStepRows.css";

const when = (at) => { const d = dayLabel(at); return [d && d !== "Today" ? d : "", fmtTime12(at)].filter(Boolean).join(" "); };
const CHANNEL = { email: "Email", whatsapp: "WhatsApp message", teams: "Teams message", slack: "Slack message", telegram: "Telegram message", sms: "Text" };
const Mark = ({ channel }) => {
  const c = String(channel || "").toLowerCase();
  const Icon = c === "whatsapp" ? WhatsAppIcon : !c || c === "email" ? MailOutlineIcon : ChatBubbleOutlineIcon;
  return <Icon aria-hidden sx={{ fontSize: 14, verticalAlign: "-2px", mr: 0.5 }} />;
};
const LIVE_SHOWN = 6;

// what came in, on the right - who, on what, when - a burst from one sender under one head (the general chat's Arrived)
const MailRow = ({ mail }) => <div className="tq-aui-message tq-aui-brief">{mail.filter((x) => !x.own).map((x, i, all) => {
  const more = i > 0 && all[i - 1].who === x.who && all[i - 1].channel === x.channel;
  return <div key={i} className={`tq-aui-arrived${more ? " tq-aui-arrived-more" : ""}`} data-tq-chat-arrived="">
    <span className="tq-aui-arrived-head">{more ? (x.at ? when(x.at) : "") : <><Mark channel={x.channel} />
      {[`${CHANNEL[String(x.channel || "").toLowerCase()] || "Message"} from ${x.who || "someone"}`, x.at ? when(x.at) : ""].filter(Boolean).join(" · ")}</>}</span>
    <span className="tq-aui-arrived-words" dir="auto" title={x.words}>{x.words}</span></div>; })}</div>;

// ...a teammate's line from a bound chat (agentchannels.py) is theirs, named and marked, never "You"
const YouRow = ({ text, at, held }) => { const mate = teammateLine(text); return (
  <div className={`tq-aui-message tq-aui-user`} data-tq-held={held ? "" : undefined} data-tq-teammate={mate ? mate.who : undefined}>
    <div className="tq-aui-user-head"><PersonOutlineIcon aria-hidden sx={{ fontSize: 14, verticalAlign: "-2px", mr: 0.5 }} />
      {mate ? `${mate.who} (teammate) · ${mate.via}` : "You"}{at ? ` · ${when(at)}` : ""}</div>
    <div className="tq-aui-user-bubble" dir="auto">{mate ? mate.text : text}</div>
  </div>); };

// AN EDIT IS A ROW THAT OPENS ON ITS DIFF: "Edited budget.py (+12 −3)", the code with its line numbers under it
const EditRow = ({ p }) => (
  <details className="tq-aui-step tq-aui-step-edit tq-cc-edit" data-tq-edit={baseName(p.file)}>
    <summary><WriteIcon aria-hidden className="tq-aui-step-icon" /><span>{p.summary}</span></summary>
    <div className="tq-cc-diff">{p.hunks.length ? p.hunks.map((h, i) => <Hunk key={i} h={h} path={p.file} />)
      : <div className="tq-dv-empty">Its log keeps no diff for this one.</div>}</div>
  </details>);

// ITS PLAN, A CHECKLIST: done ticked, the one it is on marked, the rest open
const PLAN_ICON = { done: DoneIcon, now: NowIcon, todo: TodoIcon };
const PlanRow = ({ p }) => (
  <ul className="tq-cc-plan" data-tq-plan="" aria-label="The agent's plan">{p.items.map((x, i) => { const Icon = PLAN_ICON[x.state] || TodoIcon;
    return <li key={i} data-tq-plan-item={x.state}><Icon aria-hidden sx={{ fontSize: 15 }} /><span>{x.text}</span></li>; })}</ul>);

// its work: open while it runs, the newest LIVE_SHOWN steps; once it has answered, one "N steps" line that opens
const Work = ({ steps, running }) => {
  if (running) { const cut = Math.max(0, steps.length - LIVE_SHOWN);
    return <div className="tq-aui-live-steps" data-tq-live-steps="" role="status" aria-live="polite">
      {!!cut && <details className="tq-aui-live-earlier"><summary>{plural(cut, "earlier step")}</summary><AgentSteps data={{ steps: steps.slice(0, cut) }} /></details>}
      <AgentSteps data={{ steps: steps.slice(cut) }} /></div>; }
  const n = workCount({ steps });
  return <details className="tq-aui-working-fold"><summary>{n ? plural(n, "step") : "Along the way"}</summary><AgentSteps data={{ steps }} /></details>;
};

const Turn = ({ r }) => (
  <div className="tq-aui-message tq-aui-agent" data-tq-coding-turn={r.running ? "running" : ""}>
    <div className="tq-aui-role">{AGENT_TURN}{r.at && <span style={{ textTransform: "none", letterSpacing: 0, fontWeight: 500, marginLeft: 8 }}>· {when(r.at)}</span>}</div>
    <div className="tq-aui-agent-body">
      {r.parts.map((p, i) => p.type === "said" ? <Md key={p.id} text={p.text} />
        : p.type === "edit" ? <EditRow key={p.id} p={p} />
        : p.type === "plan" ? <PlanRow key={p.id} p={p} />
        : <Work key={p.id} steps={p.steps} running={r.running && i === r.parts.length - 1} />)}
      {r.running && <div className="tq-aui-thinking" role="status"><i /><i /><i /><span>Working on this…</span></div>}
    </div>
  </div>);

export default function CodingChat({ task, term = null, next = null, landing = null, closedLine = "", came = null, reading = null, onChanged }) {
  const tid = task.TaskId;
  const [data, setData] = useState(null), [text, setText] = useState(""), [held, setHeld] = useState([]), [err, setErr] = useState(""),
    [termPick, setTermPick] = useState(null), [sending, setSending] = useState(false);
  const load = useCallback(() => api.get(`/api/tasks/${tid}/coding-chat`).then(({ data: d }) => setData(d?.data || null)).catch(() => {}), [tid]);
  useEffect(() => { setData(null); setHeld([]); setText(""); setErr(""); setTermPick(null); load(); }, [tid, load]);
  // the page's own session (TaskPage `term`) is the first word that a CLI runs: the chat's read follows it
  const pageLive = term?.alive && term.mode !== "assistant" && term.taskId === tid ? term : null;
  const live = data?.live || (pageLive ? { sid: pageLive.sid, cli: pageLive.cli, asking: false, working: !pageLive.waiting } : null);
  useEffect(() => { load(); }, [pageLive?.sid, pageLive?.alive, load]);
  // ...read again while a CLI runs, and when the task moves (a mail joined, a session ended)
  useEffect(() => { if (!live) return undefined; const t = setInterval(load, 2500); return () => clearInterval(t); }, [!!live, load]);   // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => onLive("task-changed", (ev) => { if (touches(ev, tid)) load(); }), [tid, load]);
  const rows = useMemo(() => chatRows(data || {}), [data]);
  // a line typed here stays drawn as the owner's until the CLI's own log has it - matched as the general chat matches (heldLines.stillHeld): its
  // words however spelled back, and only a line logged SINCE the hold, so a "yes" said earlier never takes a new "yes" away
  const yours = useMemo(() => rows.filter((r) => r.kind === "you").length, [rows]);
  useEffect(() => { setHeld((h) => (h.length ? stillHeld(h, rows.filter((r) => r.kind === "you").map((r) => ({ role: "user", content: [{ type: "text", text: r.text }] }))) : h)); }, [rows]);
  // ...a session over ACP has a terminal only once a command printed something (codingchat.live_of `terminal`)
  const hasTerm = !!live && live.terminal !== false, acp = live?.transport === "acp";
  const termShown = hasTerm && (termPick ?? !!live.asking);
  const stop = () => api.post(`/api/tasks/${tid}/agent/cancel`).then(() => setTimeout(load, 600)).catch((x) => setErr(x?.response?.data?.detail || x?.message || "It did not stop"));
  const vp = useRef(null), stuck = useRef(true);
  useEffect(() => { const v = vp.current; if (v && stuck.current) v.scrollTop = v.scrollHeight; }, [rows.length, held.length, !!next, !!landing]);   // eslint-disable-line react-hooks/exhaustive-deps
  const closed = ["done", "dropped"].includes(String(task.Status || ""));
  // ...AND FILES, as every box takes them (the owner, 2026-11-06): saved by the server, and named to the CLI by their paths after the words - the
  // way the general chat hands a CLI its files (promptImages.withImages); every coding CLI reads a file from its path
  const pics = usePromptImages({ files: true });
  useEffect(() => { pics.clear(); }, [tid]);   // eslint-disable-line react-hooks/exhaustive-deps
  const send = async () => {
    const w = text.trim(), files = pics.paths;
    if ((!w && !files.length) || sending || pics.busy) return;
    const said = withImages(w, files);
    setText(""); setErr(""); setSending(true);
    const id = `held-${Date.now()}`;
    setHeld((h) => [...h, { id, text: w || said, after: yours }]);
    try {
      // ...into the running CLI as its next line, or the session picked back up with these words leading
      if (live) await api.post(`/api/tasks/${task.TaskId}/waitroom`, { text: said });
      else await api.post(`/api/tasks/${task.TaskId}/continue-work`, { note: said });
      pics.clear(); onChanged?.(); setTimeout(load, 1200);
    } catch (x) { setHeld((h) => h.filter((l) => l.id !== id)); setText(w); setErr(x?.response?.data?.detail || x?.message || "It did not go"); }
    setSending(false);
  };
  return (
    <Box data-tq-coding-chat={tid} sx={{ border: `1px solid ${BORDER}`, borderRadius: 1.75, overflow: "hidden", bgcolor: PANEL2, height: "100%", minHeight: 0, display: "flex", flexDirection: "column" }}>
      <div className="tq-aui-thread tq-aui-chat">
        <div className="tq-aui-viewport" ref={vp} onScroll={(e) => { const v = e.currentTarget; stuck.current = v.scrollHeight - v.scrollTop - v.clientHeight < 40; }}>
          {reading}
          {!rows.length && !held.length && data && <div className="tq-aui-hint" style={{ margin: "8px 0 16px" }}>
            {live ? "The agent is starting - its turns show here as it works." : "No session has run on this task yet - write below to start one."}</div>}
          {rows.map((r) => r.kind === "mail" ? <MailRow key={r.id} mail={r.mail} /> : r.kind === "you" ? <YouRow key={r.id} text={r.text} at={r.at} /> : <Turn key={r.id} r={r} />)}
          {held.map((l) => <YouRow key={l.id} text={l.text} held />)}
          {/* WHAT THE AGENT WAITS ON THE OWNER'S PRESS FOR (permissions.py): one card each, answered here or by the owner on a bound chat */}
          <PermissionCards taskId={tid} items={data?.permissions || []} onAnswered={load} />
          {live?.working && !rows.at(-1)?.running && <div className="tq-aui-thinking" role="status"><i /><i /><i /><span>{live.cli || "The agent"} is working…</span></div>}
          {/* THE DRAFTED REPLY, with its Send (Close out's own cards, TaskPage closeBody) - then the branch's landing, then how it closed */}
          {next && <Box data-tq-next-steps="" className="tq-aui-summary" sx={{ mt: 1 }}>
            <Box component="span" sx={{ display: "block", color: "#292824", fontSize: 13.5, fontWeight: 700, mt: 1, mb: 0.25 }}>Suggested reply</Box>{next}</Box>}
          {landing}
          {closedLine && <div className="tq-aui-closed" data-tq-chat-closed="">{closedLine}</div>}
        </div>
        {termShown && <Box data-tq-chat-terminal="" sx={{ flex: "0 0 46%", minHeight: 220, borderTop: `1px solid ${BORDER}`, display: "flex", flexDirection: "column", "& > *": { flex: 1, minHeight: 0 } }}>
          <TerminalPane sid={live.sid} height="100%" onExit={load} /></Box>}
        <div className="tq-aui-footer">
          {live?.asking && !termShown && <div className="tq-aui-hint" role="status" style={{ margin: "0 0 6px" }}>The agent's screen is asking something - open the Terminal to answer it.</div>}
          {/* THE ONE BOX (AgentSummary.PromptBox): paperclip, the Came-from chip and the files, the words, the mic, the Terminal toggle, Send */}
          <PromptBox text={text} setText={setText} pics={pics} busy={false} sendOff={sending} onSend={send} label="Message the agent" title="Send"
            placeholder={closed ? "Write to pick it back up…" : live ? MESSAGE : "Write to pick the session back up…"}
            chips={came ? <AttachChip data-tq-came-chip="" name={came.label} title={came.title || came.label} icon={came.icon || false} onClick={came.onOpen}
              sx={{ cursor: came.onOpen ? "pointer" : "default" }} /> : null}
            /* THE TERMINAL, A TOGGLE ON THE CHAT: only while a CLI runs */
            extra={<>{acp && live.working && <button type="button" className="tq-aui-cancel" data-tq-stop-turn="" aria-label="Stop response"
              title="Stops this turn - the session stays, and what you type next carries on" onClick={stop}><CloseIcon fontSize="small" /></button>}
              {hasTerm && <button type="button" className="tq-cc-term" data-tq-terminal-toggle="" aria-pressed={termShown ? "true" : "false"}
              title={termShown ? "Hide the agent's terminal" : "Watch the agent's terminal - and answer what only it can"} onClick={() => setTermPick(!termShown)}>
              <TerminalIcon sx={{ fontSize: 15 }} /><span>Terminal</span></button>}</>} />
          {err && <div className="tq-aui-asking-err" role="alert" style={{ padding: "4px 4px 0" }}>{err}</div>}
          <div className="tq-aui-hint">{acp ? (live.working ? "Enter sends it when this turn ends · Shift+Enter adds a line" : "Enter sends it to the agent · Shift+Enter adds a line")
            : live ? "Enter types it into the running agent · Shift+Enter adds a line" : "Enter picks the session back up with what you wrote · Shift+Enter adds a line"}</div>
        </div>
      </div>
    </Box>
  );
}
