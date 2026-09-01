// ＋ New — the only door on the Timeline that starts something instead of reacting to it.
//
// Until now every row on the Timeline was something that HAPPENED to the owner. Sending a
// message meant opening Outlook (the app this one exists to keep them out of); starting a job
// meant the Board; and a reminder had nowhere to go at all, so it went in a notebook and the
// screen they watch all day knew nothing about it.
//
// Three doors, one sheet - and the agent door forks again, into a CLI session or the
// assistant's own chat. All of them land on the Timeline at the minute the button was
// pressed. Nothing here sends: "Send something" produces a DRAFT the owner approves, which is
// the one send path the app has and the only one that respects the per-channel reply switches.
import React, { forwardRef, useCallback, useEffect, useImperativeHandle, useRef, useState } from "react";
import {
  Alert, Box, Button, CircularProgress, Dialog, DialogContent, DialogTitle, IconButton,
  MenuItem, Select, TextField, Typography,
} from "@mui/material";
import CloseIcon from "@mui/icons-material/Close";
import api from "./api";
import { ACCENT, ACCENT2, BORDER, DIM, FAINT, GRADIENT, INK, PANEL, PANEL2, ROLES, mono } from "./theme.jsx";
import { ChannelIcon, AgentPicker, useAgents, TaskuaryMark } from "./ui.jsx";
import { NO_REPO, planTask } from "./newTask.js";
import FormControlLabel from "@mui/material/FormControlLabel";
import Checkbox from "@mui/material/Checkbox";

const KINDS = [
  { key: "send",   mark: "✉️", label: "Send something", hint: "a message you start, drafted in your voice and approved by you" },
  { key: "agent",  mark: <TaskuaryMark size={14} />, label: "Give an agent a job", hint: "a live CLI session, or the assistant's own chat — the two doors triage picks between" },
  { key: "note",   mark: "💡", label: "Note to self", hint: "a reminder or an idea — nothing works it, it just sits on the day you pick" },
];

const Label = ({ children }) => (
  <Typography sx={{ ...mono, fontSize: 9.5, fontWeight: 600, letterSpacing: ".11em",
    textTransform: "uppercase", color: ACCENT2, mb: 0.75 }}>{children}</Typography>
);

const Fork = ({ on, title, hint, onClick }) => (
  <Box onClick={onClick} role="button" tabIndex={0}
    onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && onClick()}
    sx={{ flex: 1, minWidth: 0, border: `1px solid ${on ? ACCENT : BORDER}`, borderRadius: 2,
      p: 1.25, cursor: "pointer", bgcolor: on ? "#fff" : "#fcfaf7",
      boxShadow: on ? `inset 0 0 0 1px ${ACCENT}` : "none", transition: "border-color .15s" }}>
    <Typography sx={{ fontSize: 12.5, fontWeight: 600, color: INK, mb: 0.4 }}>{title}</Typography>
    <Typography sx={{ fontSize: 11, color: FAINT, lineHeight: 1.5 }}>{hint}</Typography>
  </Box>
);

// Keep the large freeform field below its own render boundary. The sheet contains provider
// discovery, menus, forks, and a MUI dialog; owning this value at the sheet level rebuilt all of
// that on every keystroke and made an ordinary sentence feel like terminal input over a slow
// connection. The parent only hears when empty/non-empty changes and reads the value on submit.
const AboutField = React.memo(forwardRef(function AboutField({ kind, how, onReady }, ref) {
  const [value, setValue] = useState("");
  const ready = useRef(false);
  useImperativeHandle(ref, () => ({ value, clear: () => { ready.current = false; setValue(""); } }), [value]);
  const changed = (e) => {
    const next = e.target.value;
    setValue(next);
    const hasText = !!next.trim();
    if (hasText !== ready.current) { ready.current = hasText; onReady(hasText); }
  };
  return (
    <TextField fullWidth multiline minRows={kind === "note" ? 2 : 3} value={value} autoFocus
      onChange={changed}
      placeholder={kind === "send" ? "the census numbers he asked for, plus why Ashgrove moved"
        : kind === "agent" ? (how === "chat" ? "why did Riverbend's census move four points in July?"
          : "work out why the nightly export drops the last facility")
        : "chase the Ashgrove AP replacement"}
      sx={{ "& .MuiInputBase-root": { fontSize: 13, bgcolor: "#fcfaf7" } }} />
  );
}));

export default function NewSheet({ open, onClose, onDone, onOpenTask }) {
  const [kind, setKind] = useState("send");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [ok, setOk] = useState("");

  // send
  const [targets, setTargets] = useState([]);          // [{channel, to: [{to, name, hint}]}]
  const [channel, setChannel] = useState("");
  const [to, setTo] = useState("");
  const [hasAbout, setHasAbout] = useState(false);
  const aboutRef = useRef(null);
  const [mode, setMode] = useState("draft");
  // agent
  const { agents, models } = useAgents();
  const [agent, setAgent] = useState("coder");
  const [model, setModel] = useState("");
  // "terminal" = a CLI on a keyboard, "chat" = the assistant's own thread. Held here rather
  // than inferred from the words: a question landing in a terminal by ACCIDENT is exactly what
  // newTask.planTask exists to stop, and it will not guess for us.
  const [how, setHow] = useState("terminal");
  // A session you open here is usually one you mean to sit in, so it does not end itself: the
  // judge that closes a router's task on a quiet screen would close this one while you read it.
  const [stayOpen, setStayOpen] = useState(true);
  // note
  const [when, setWhen] = useState("");

  useEffect(() => { if (!open) return; setErr(""); setOk(""); }, [open]);
  useEffect(() => { if (agents.length && !agents.includes(agent)) setAgent(agents[0]); }, [agents, agent]);
  useEffect(() => {
    if (!open) return;
    api.get("/api/send-targets").then(({ data }) => {
      const list = data.data || [];
      setTargets(list);
      setChannel((c) => c || list[0]?.channel || "");
    }).catch(() => setTargets([]));
  }, [open]);

  const chanTargets = (targets.find((t) => t.channel === channel)?.to) || [];
  const close = () => { if (!busy) onClose?.(); };

  const submit = useCallback(async () => {
    setBusy(true); setErr(""); setOk("");
    const about = String(aboutRef.current?.value || "").trim();
    try {
      if (kind === "send") {
        const { data } = await api.post("/api/outbox", { channel, to: to.trim(), about, mode });
        setOk(mode === "task"
          ? `${data.ref} — an agent is finding out first; the message is drafted when it is done.`
          : `${data.ref} — drafted. It is on the Timeline waiting for you to send it.`);
        aboutRef.current?.clear(); setHasAbout(false); onDone?.(); onOpenTask?.(data.taskId);
      } else if (kind === "agent") {
        // one module decides chat-vs-terminal for the whole app, so the Board and this sheet can
        // never disagree about what "no repository" means
        const chat = how === "chat";
        const plan = planTask(chat ? NO_REPO : null, chat ? "live" : "terminal", false, !chat && stayOpen);
        const { data } = await api.post("/api/tasks", { Title: about.slice(0, 300), Summary: about,
          Kind: plan.kind, Tags: plan.tags });
        if (plan.chat) {
          // nothing to dispatch: the chat opens its own session and asks the question off the tag
          // planTask put on the task (GeneralWorkspace), which is why the words are not passed as a prop
          setOk(`${data.ref} — open on Tasks; the assistant already has the question.`);
        } else {
          await api.post(`/api/tasks/${data.taskId}/dispatch`, { agent, model: model || null });
          setOk(`${data.ref} — ${agent} is on it in a live session.`);
        }
        aboutRef.current?.clear(); setHasAbout(false); onDone?.(); onOpenTask?.(data.taskId);
      } else {
        const { data } = await api.post("/api/notes", { title: about.slice(0, 300), body: "", when: when || null });
        setOk(`Noted — it sits on ${String(data.at).slice(0, 16)} and nothing will touch it.`);
        aboutRef.current?.clear(); setHasAbout(false); setWhen(""); onDone?.();
      }
    } catch (e) { setErr(e?.response?.data?.detail || "That did not go through"); }
    setBusy(false);
  }, [kind, channel, to, mode, how, agent, model, when, onDone, onOpenTask]);

  const canGo = hasAbout && (kind !== "send" || (channel && to.trim()));
  const verb = kind === "send" ? (mode === "task" ? "Send an agent" : "Draft it")
    : kind === "agent" ? (how === "chat" ? "Ask the assistant" : "Start the session") : "Note it";

  return (
    <Dialog open={!!open} onClose={close} fullWidth maxWidth="sm" data-tq-keep>
      <DialogTitle sx={{ display: "flex", alignItems: "center", gap: 1, pb: 0.5 }}>
        <Box sx={{ flex: 1 }}>What are we starting?</Box>
        <IconButton size="small" onClick={close}><CloseIcon sx={{ fontSize: 17 }} /></IconButton>
      </DialogTitle>

      {/* the kinds are tabs, not a select: three doors that all exist is the point of the sheet,
          and a closed dropdown hides two of them behind a click */}
      <Box sx={{ display: "flex", gap: 0.25, px: 3, borderBottom: `1px solid ${BORDER}` }}>
        {KINDS.map((k) => (
          <Box key={k.key} onClick={() => { setKind(k.key); setErr(""); setOk(""); }} role="tab"
            aria-selected={kind === k.key} title={k.hint}
            sx={{ display: "flex", alignItems: "center", gap: 0.75, px: 1.5, py: 1, cursor: "pointer",
              fontSize: 12.5, fontWeight: 600, whiteSpace: "nowrap", mb: "-1px",
              color: kind === k.key ? INK : FAINT,
              borderBottom: `2px solid ${kind === k.key ? ACCENT : "transparent"}`,
              transition: "color .15s" }}>
            <Box component="span" aria-hidden sx={{ fontSize: 13, lineHeight: 1 }}>{k.mark}</Box>{k.label}
          </Box>
        ))}
      </Box>

      <DialogContent sx={{ display: "flex", flexDirection: "column", gap: 2, pt: 2.5 }}>
        {kind === "send" && (
          <>
            <Box>
              <Label>Channel</Label>
              <Box sx={{ display: "flex", gap: 0.75, flexWrap: "wrap" }}>
                {targets.map((t) => (
                  <Box key={t.channel} onClick={() => { setChannel(t.channel); setTo(""); }}
                    sx={{ display: "flex", alignItems: "center", gap: 0.75, px: 1.25, py: 0.75, cursor: "pointer",
                      border: `1px solid ${channel === t.channel ? ACCENT : BORDER}`, borderRadius: 2,
                      boxShadow: channel === t.channel ? `inset 0 0 0 1px ${ACCENT}` : "none",
                      fontSize: 12.5, fontWeight: 600, color: channel === t.channel ? INK : DIM }}>
                    <ChannelIcon channel={t.channel} sx={{ fontSize: 15 }} />{t.channel}
                  </Box>
                ))}
                {!targets.length && (
                  <Typography variant="caption" sx={{ color: FAINT }}>
                    No channel here can send yet — turn replies on for a mailbox or a chat in Connections.
                  </Typography>
                )}
              </Box>
            </Box>
            <Box>
              <Label>To</Label>
              {/* the addresses this install actually knows, from the same list a report's
                  delivery offers - a JID typed from memory is a message that goes nowhere */}
              <Select size="small" fullWidth displayEmpty value={to} onChange={(e) => setTo(e.target.value)}
                renderValue={(v) => v || "pick someone you already trade messages with"}
                sx={{ fontSize: 13, bgcolor: "#fcfaf7", color: to ? INK : FAINT }}
                MenuProps={{ PaperProps: { sx: { maxHeight: 360 } } }}>
                {chanTargets.map((t) => (
                  <MenuItem key={t.to} value={t.to} sx={{ fontSize: 12.5, display: "block" }}>
                    <Box sx={{ fontWeight: 600 }}>{t.name || t.to}</Box>
                    {t.hint && <Box sx={{ fontSize: 10.5, color: FAINT }}>{t.hint}</Box>}
                  </MenuItem>
                ))}
                {!chanTargets.length && <MenuItem disabled sx={{ fontSize: 12 }}>nothing known on this channel yet</MenuItem>}
              </Select>
            </Box>
          </>
        )}

        {kind === "agent" && (
          <>
            {/* Not every job wants a keyboard. This sheet only ever opened a terminal, so a
                question you just wanted TALKED THROUGH had to be filed as a coding task and then
                walked back - the exact mistake newTask.js was written to prevent. Both doors,
                stated, and the choice made before anything is created. */}
            <Box>
              <Label>Who works it</Label>
              <Box sx={{ display: "flex", gap: 1 }}>
                <Fork on={how === "terminal"} onClick={() => setHow("terminal")} title="A live session"
                  hint="a CLI agent on a keyboard, in a checkout — it edits, runs and reports back." />
                <Fork on={how === "chat"} onClick={() => setHow("chat")} title="Just talk it through"
                  hint="the assistant's own thread on the task. Research, plan, decide — no terminal, no repository." />
              </Box>
            </Box>
            {how === "terminal" && (
              <Box>
                <Label>Agent</Label>
                <Box sx={{ display: "flex", alignItems: "center", gap: 1.25, flexWrap: "wrap" }}>
                  <AgentPicker agents={agents} models={models} agent={agent} model={model}
                    onAgent={setAgent} onModel={setModel} size={30} />
                  {/* no repository picker here on purpose: guess_repo ranks the checkouts against
                      what you just typed (SOUL.md's repo map), and a session that opens in the wrong
                      tree refuses to start rather than guessing. Name the system in the ask. */}
                  <Typography variant="caption" sx={{ color: FAINT, flex: 1, minWidth: 180 }}>
                    It picks the checkout from what you write — name the system if there is any doubt.
                  </Typography>
                </Box>
                {/* the difference between a session that works FOR you and one you work IN */}
                <FormControlLabel sx={{ mt: 0.5, ml: 0, alignItems: "flex-start" }}
                  control={<Checkbox size="small" checked={stayOpen} sx={{ py: 0.25, mr: 0.5 }}
                    onChange={(x) => setStayOpen(x.target.checked)} />}
                  label={
                    <Box sx={{ pt: 0.35 }}>
                      <Typography sx={{ fontSize: 12.5, fontWeight: 600, color: INK }}>Leave it open when it goes quiet</Typography>
                      <Typography sx={{ fontSize: 11, color: FAINT, lineHeight: 1.5 }}>
                        For a session you mean to sit in. Off, it closes itself the moment it reads
                        as finished — which is right for work that arrived, and wrong while you are
                        still typing. `taskuary --done` still ends it either way.
                      </Typography>
                    </Box>} />
              </Box>
            )}
          </>
        )}

        <Box>
          <Label>{kind === "send" ? "What's this about"
            : kind === "agent" ? (how === "chat" ? "What do you want to work out" : "What should it do")
            : "What do you want to remember"}</Label>
          <AboutField ref={aboutRef} kind={kind} how={how} onReady={setHasAbout} />
          {kind === "send" && (
            <Typography variant="caption" sx={{ color: FAINT, display: "block", mt: 0.75 }}>
              Shorthand is fine — this is what you are telling the drafter, not what they read.
            </Typography>
          )}
        </Box>

        {kind === "send" && (
          <Box>
            <Label>And then</Label>
            <Box sx={{ display: "flex", gap: 1 }}>
              <Fork on={mode === "draft"} onClick={() => setMode("draft")} title="Draft it and show me"
                hint="written in your voice from the thread. It lands on the Timeline as ✉️ reply ready." />
              <Fork on={mode === "task"} onClick={() => setMode("task")} title="Find out first"
                hint="an agent researches it, then drafts the message from what it actually found." />
            </Box>
          </Box>
        )}

        {kind === "note" && (
          <Box>
            <Label>Come back to it</Label>
            {/* the note's row is stamped with WHEN IT IS FOR, so the Timeline's own clock is the
                reminder: it sits in that day, out of the way until then (ownwork.note) */}
            <TextField type="datetime-local" size="small" value={when} onChange={(e) => setWhen(e.target.value)}
              sx={{ "& .MuiInputBase-root": { fontSize: 13, bgcolor: "#fcfaf7" } }} />
            <Typography variant="caption" sx={{ color: FAINT, display: "block", mt: 0.75 }}>
              Leave it empty for now. A date puts the row in that day and it stays quiet until then.
            </Typography>
          </Box>
        )}

        {err && <Alert severity="error" sx={{ py: 0.25, fontSize: 12.5 }}>{err}</Alert>}
        {ok && <Alert severity="success" sx={{ py: 0.25, fontSize: 12.5 }}>{ok}</Alert>}
      </DialogContent>

      <Box sx={{ display: "flex", gap: 1, justifyContent: "flex-end", px: 3, py: 1.75,
        borderTop: `1px solid ${BORDER}`, bgcolor: PANEL2 }}>
        <Button size="small" onClick={close} sx={{ color: DIM }}>Cancel</Button>
        <Button size="small" variant="contained" disableElevation disabled={!canGo || busy} onClick={submit}
          startIcon={busy ? <CircularProgress size={12} sx={{ color: "#fff" }} /> : null}
          sx={{ background: GRADIENT }}>{busy ? "Working…" : verb}</Button>
      </Box>
    </Dialog>
  );
}
