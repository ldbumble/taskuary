import { t as tx } from "./i18n.js";
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
  Alert, Autocomplete, Box, Button, Chip, CircularProgress, Dialog, DialogContent, DialogTitle, IconButton,
  TextField, Typography,
} from "@mui/material";
import CloseIcon from "@mui/icons-material/Close";
import api from "./api";
import { ACCENT, ACCENT2, BORDER, DIM, FAINT, GRADIENT, INK, PANEL, PANEL2, ROLES, mono } from "./theme.jsx";
import { ChannelIcon, AgentPicker, MicButton, useAgents, TaskuaryMark } from "./ui.jsx";
import { outcomeOf } from "./dispatchOutcome.js";
import { NO_REPO, planTask } from "./newTask.js";
import NewRepo from "./NewRepo.jsx";
import { AttachImage, ImageTray, usePromptImages, withImages } from "./promptImages.jsx";
import { emailRecipientOptions, normalizeEmails, recipientLabel, recipientOptions } from "./recipientOptions.js";
import FormControlLabel from "@mui/material/FormControlLabel";
import Checkbox from "@mui/material/Checkbox";

const KINDS = [
  { key: "send",   mark: "✉️", label: "Send something", hint: "a message you start, drafted in your voice and approved by you" },
  { key: "agent",  mark: <TaskuaryMark size={14} />, label: "Give an agent a job", hint: "a live CLI session, or the assistant's own chat — the two doors triage picks between" },
  { key: "note",   mark: "💡", label: "Note to self", hint: "a reminder or an idea — nothing works it, it just sits on the day you pick" },
  { key: "goal",   mark: "🎯", label: "Set a goal", hint: "an outcome with a date and steps — the steps are tasks, and it stays on your rail until it is done" },
  // A JOB THAT REPEATS (the owner, 2026-10-15: "new should have this workflow/report option that would just take you to the
  // same ui for reports/workflows"): no second form here - it opens the one Reports keeps, so a report or a workflow is set up
  // in exactly one place
  { key: "repeat", mark: "🔁", label: "Report or workflow", hint: "a job that runs on a schedule — a report reads and summarises, a workflow does the work" },
];
// where each one is set up (ReportsView reads the hash, on the tab and on the canvas alike)
const REPEAT_TO = { report: "report=new", workflow: "report=new-agent" };

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

export const EmailRecipients = ({ value, onChange, options, placeholder }) => (
  <Autocomplete multiple freeSolo autoHighlight openOnFocus size="small" fullWidth
    options={options}
    value={value}
    onChange={(_event, values) => onChange(normalizeEmails(values))}
    getOptionLabel={(option) => typeof option === "string" ? option : (option.name || option.to || "")}
    isOptionEqualToValue={(option, selected) => option.to?.toLowerCase() === String(selected).toLowerCase()}
    filterOptions={(rows, state) => emailRecipientOptions(rows, state.inputValue)}
    renderTags={(emails, getTagProps) => emails.map((email, index) => (
      <Chip {...getTagProps({ index })} key={email} label={email} size="small" sx={{ maxWidth: 260 }} />
    ))}
    renderOption={(props, option) => {
      const address = typeof option === "string" ? option : option.to;
      return (
        <Box component="li" {...props} key={address} sx={{ display: "block !important", fontSize: 12.5 }}>
          <Box sx={{ fontWeight: 600 }}>{typeof option === "string" ? `Use ${address}` : (option.name || address)}</Box>
          {typeof option !== "string" && <Box sx={{ fontSize: 10.5, color: FAINT }}>{address}</Box>}
        </Box>
      );
    }}
    renderInput={(params) => (
      <TextField {...params} placeholder={value.length ? "Add another email" : placeholder}
        sx={{ "& .MuiInputBase-root": { fontSize: 13, bgcolor: "#fcfaf7" } }} />
    )} />
);

// Keep the large freeform field below its own render boundary. The sheet contains provider
// discovery, menus, forks, and a MUI dialog; owning this value at the sheet level rebuilt all of
// that on every keystroke and made an ordinary sentence feel like terminal input over a slow
// connection. The parent only hears when empty/non-empty changes and reads the value on submit.
const AboutField = React.memo(forwardRef(function AboutField({ kind, how, onReady, bus, pics }, ref) {
  const [value, setValue] = useState("");
  const ready = useRef(false);
  const timer = useRef(0);
  useEffect(() => () => clearTimeout(timer.current), []);
  useImperativeHandle(ref, () => ({ value, clear: () => { ready.current = false; setValue(""); bus?.current?.(""); } }), [value, bus]);
  const changed = (e) => {
    const next = e.target.value;
    setValue(next);
    const hasText = !!next.trim();
    if (hasText !== ready.current) { ready.current = hasText; onReady(hasText); }
    // the repository picker hears the words on a pause in typing, never per key (only it re-renders, not the card)
    if (bus?.current) { clearTimeout(timer.current); timer.current = setTimeout(() => bus.current?.(next), 200); }
  };
  // ...and a picture pasted or dropped into it goes with the words (a note to self keeps words only)
  const withPics = pics && kind !== "note";
  return (
    <>
    <TextField fullWidth multiline minRows={kind === "note" ? 2 : 3} value={value} autoFocus
      onChange={changed} {...(withPics ? pics.drop : {})}
      placeholder={kind === "goal" ? "the nightly census lands in the new ledger for all three sites, and the old portal's export is switched off"
        : kind === "send" ? "the census numbers he asked for, plus why Ashgrove moved"
        : kind === "agent" ? (how === "general" ? "why did Riverbend's census move four points in July?"
          : "work out why the nightly export drops the last facility")
        : "chase the Ashgrove AP replacement"}
      // SAID, NOT TYPED (the owner, 2026-09-30: "can't ... use voice notes to write this prompt?"): the composer's own mic,
      // its words appended where the typing would go
      InputProps={{ endAdornment: (
        <Box sx={{ display: "flex", alignSelf: "flex-start", gap: 0.25 }}>
          {withPics && <AttachImage pics={pics} sx={{ width: 30, height: 30 }} />}
          <MicButton size={18} sx={{ width: 30, height: 30, p: 0, color: "#6e685f" }}
            onText={(t) => changed({ target: { value: value ? `${value} ${t}` : t } })} />
        </Box>) }}
      sx={{ "& .MuiInputBase-root": { fontSize: 13, bgcolor: "#fcfaf7", alignItems: "flex-start" } }} />
    {withPics && <ImageTray pics={pics} sx={{ mt: 0.75 }} />}
    </>
  );
}));

// `inline`: the card the sidebar's New button posts into the conversation (the canvas redesign) - the same tabs and fields,
// drawn in the conversation's own width instead of a dialog over the page. Without it the dialog stays for any other door.
export default function NewSheet({ open, onClose, onDone, onOpenTask, inline = false }) {
  const [kind, setKind] = useState("send");
  const said = useRef(null);      // the words, for the repository picker (see NewRepo)
  const repoPick = useRef(null);  // what the picker says to use, read on submit
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [ok, setOk] = useState("");

  // send
  const [targets, setTargets] = useState([]);          // [{channel, to: [{to, name, hint}]}]
  const [channel, setChannel] = useState("");
  const [to, setTo] = useState("");
  const [emailTo, setEmailTo] = useState([]);
  const [cc, setCc] = useState([]);
  const [hasAbout, setHasAbout] = useState(false);
  const aboutRef = useRef(null);
  const [mode, setMode] = useState("draft");
  const pics = usePromptImages();
  // agent
  const { agents, models, kinds, brainList, brainModels, generalBrains } = useAgents();
  const [agent, setAgent] = useState("coder");
  const [brain, setBrain] = useState("");   // WHICH CLI runs it; blank = the brain settings name
  const [model, setModel] = useState("");
  const [role, setRole] = useState("");     // a general agent: which profile (researcher, analyst...)
  const [pick, setPick] = useState("");     // ...and which brain runs it; blank = the General agent setting
  // "terminal" = a CLI on a keyboard, "general" = a general agent with no repository. Held here rather
  // than inferred from the words: a question landing in a terminal by ACCIDENT is exactly what
  // newTask.planTask exists to stop, and it will not guess for us.
  const [how, setHow] = useState("terminal");
  // A session you open here is usually one you mean to sit in, so it does not end itself: the
  // judge that closes a router's task on a quiet screen would close this one while you read it.
  // note
  const [when, setWhen] = useState("");
  // a goal (spec 2026-10-12): what done looks like is the words above; by when, who is involved, and whether the AI plans the steps
  const [by, setBy] = useState(""); const [who, setWho] = useState(""); const [plan, setPlan] = useState(true);
  const [repeat, setRepeat] = useState("workflow");

  useEffect(() => { if (!open) return; setErr(""); setOk(""); }, [open]);
  useEffect(() => {
    if (agents.length && !agents.includes(agent)) { setAgent(agents[0]); setModel(""); }
  }, [agents, agent]);
  // a new general task has no profile to keep, so the first general role is chosen rather than "the profile it has"
  const roles = agents.filter((a) => !["coding", "cli"].includes(String(kinds[a] || "").toLowerCase()));
  useEffect(() => { if (!role && roles.length) setRole(roles.includes("researcher") ? "researcher" : roles[0]); }, [roles, role]);
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
    if (kind === "repeat") { onClose?.(); window.location.hash = REPEAT_TO[repeat]; return; }
    setBusy(true); setErr(""); setOk("");
    const about = String(aboutRef.current?.value || "").trim();
    try {
      if (kind === "send") {
        const { data } = await api.post("/api/outbox", {
          channel, to: channel === "email" ? emailTo : to.trim(),
          cc: channel === "email" ? cc : [], about: withImages(about, pics.paths), mode,
        });
        setOk(mode === "task"
          ? `${data.ref} — an agent is finding out first; the message is drafted when it is done.`
          : `${data.ref} — drafted. It is on the Timeline waiting for you to send it.`);
        aboutRef.current?.clear(); setHasAbout(false); pics.clear(); onDone?.(); onOpenTask?.(data.taskId);
      } else if (kind === "agent") {
        // one module decides chat-vs-terminal for the whole app, so the Board and this sheet can
        // never disagree about what "no repository" means
        const general = how === "general";
        // a session opens where the picker says (auto = the repository the words name, else the server guesses as ever);
        // the choice is the task's `repo:` tag, the override that always wins
        const pickd = general ? null : repoPick.current?.(about) || null;
        // a general agent: kind general with no repository, started below like the task page's hand-off - never the
        // assistant's thread, which does nothing itself (2026-10-15)
        const plan = planTask(general ? NO_REPO : pickd?.repo || null, general ? "file" : "terminal", false, true);
        const { data } = await api.post("/api/tasks", { Title: about.slice(0, 300), Summary: withImages(about, pics.paths),
          Kind: plan.kind, Tags: plan.tags });
        // it skipped triage, so nothing gave it a checklist: read the words behind the answer (server._read_hand_task)
        api.post(`/api/tasks/${data.taskId}/read-ask`).catch(() => null);
        // a folder typed for a repository the agent had none for is saved on the agent first - the session refuses to open without one
        if (pickd?.repo && pickd.path) await api.put(`/api/tasks/${data.taskId}/repo`, { repo: pickd.repo, path: pickd.path, agent });
        if (general) {
          const { data: out } = await api.post(`/api/tasks/${data.taskId}/dispatch`,
            { kind: "general", agent: role || null, pick: pick || null, model: model || null });
          setOk(`${data.ref} — ${outcomeOf(out).text}.`);
        } else {
          // WHAT THE ANSWER SAID, not what the button hoped. A task with no checkout comes back
          // `needs_repo` with started: false, and this announced "is on it in a live session" over
          // the top of it (the owner, 2026-09-22: "hit the new button with coding agent but it did
          // not start"). One reading of a dispatch answer, the same one every other surface uses.
          const { data: out } = await api.post(`/api/tasks/${data.taskId}/dispatch`,
            { agent, brain: brain || null, model: model || null });
          setOk(`${data.ref} — ${outcomeOf(out).text}.`);
        }
        aboutRef.current?.clear(); setHasAbout(false); pics.clear(); onDone?.(); onOpenTask?.(data.taskId);
      } else if (kind === "goal") {
        const title = about.split(/[.\n]/)[0].trim().slice(0, 120) || about.slice(0, 120);
        const { data } = await api.post("/api/tasks", { Title: title, Summary: who ? `${about}\nInvolved: ${who}` : about,
          DoneWhen: about.slice(0, 1000), DueAt: by || null, Kind: "task", Tags: "goal" });
        // the model writes the steps (server.plan_goal); "Track it" leaves the boxes to you
        if (plan) api.post(`/api/tasks/${data.taskId}/read-ask`, { goal: true }).catch(() => null);
        setOk(`${data.ref} — ${plan ? "planning the steps; they land on the task in a moment." : "on your rail; add the steps on the task."}`);
        aboutRef.current?.clear(); setHasAbout(false); setBy(""); setWho(""); onDone?.(); onOpenTask?.(data.taskId);
      } else {
        const { data } = await api.post("/api/notes", { title: about.slice(0, 300), body: "", when: when || null });
        setOk(`Noted — it sits on ${String(data.at).slice(0, 16)} and nothing will touch it.`);
        aboutRef.current?.clear(); setHasAbout(false); setWhen(""); onDone?.();
      }
    } catch (e) { setErr(e?.response?.data?.detail || "That did not go through"); }
    setBusy(false);
  }, [kind, repeat, channel, to, emailTo, cc, mode, how, agent, brain, model, role, pick, when, by, who, plan, onDone, onOpenTask, onClose, pics]);

  const canGo = kind === "repeat" || (hasAbout && (kind !== "send" || (channel && (channel === "email" ? emailTo.length : to.trim()))));
  const verb = kind === "repeat" ? `Set up the ${repeat}` : kind === "send" ? (mode === "task" ? "Send an agent" : "Draft it")
    : kind === "agent" ? (how === "general" ? "Start the agent" : "Start the session") : kind === "goal" ? (plan ? "Plan it" : "Track it") : "Note it";

  // the card: a bordered block in the conversation's width, Esc closes it, nothing floats over the page
  const Shell = inline ? Box : Dialog;
  const shell = inline
    ? { "data-tq-new": "", onKeyDown: (e) => { if (e.key === "Escape") close(); },
        sx: { border: `1px solid ${BORDER}`, borderRadius: "12px", bgcolor: PANEL, overflow: "hidden", scrollMarginTop: "8px" } }
    : { open: !!open, onClose: close, fullWidth: true, maxWidth: "sm", "data-tq-keep": true };
  if (inline && !open) return null;
  return (
    <Shell {...shell}>
      <DialogTitle sx={{ display: "flex", alignItems: "center", gap: 1, pb: 0.5 }}>
        <Box sx={{ flex: 1 }}>{tx("What are we starting?")}</Box>
        <IconButton aria-label={tx("Close new task")} size="small" onClick={close}><CloseIcon sx={{ fontSize: 17 }} /></IconButton>
      </DialogTitle>

      {/* the kinds are tabs, not a select: three doors that all exist is the point of the sheet,
          and a closed dropdown hides two of them behind a click */}
      <Box sx={{ display: "flex", gap: 0.25, px: { xs: 1, sm: 3 }, borderBottom: `1px solid ${BORDER}`, overflowX: "auto", scrollbarWidth: "none" }}>
        {KINDS.map((k) => (
          <Box key={k.key} onClick={() => { setKind(k.key); setErr(""); setOk(""); }} role="tab"
            aria-selected={kind === k.key} title={k.hint}
            sx={{ display: "flex", alignItems: "center", gap: 0.75, px: { xs: 1, sm: 1.5 }, py: 1, cursor: "pointer", flexShrink: 0,
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
              <Label>{tx("Channel")}</Label>
              <Box sx={{ display: "flex", gap: 0.75, flexWrap: "wrap" }}>
                {targets.map((t) => (
                  <Box key={t.channel} onClick={() => { setChannel(t.channel); setTo(""); setEmailTo([]); setCc([]); }}
                    sx={{ display: "flex", alignItems: "center", gap: 0.75, px: 1.25, py: 0.75, cursor: "pointer",
                      border: `1px solid ${channel === t.channel ? ACCENT : BORDER}`, borderRadius: 2,
                      boxShadow: channel === t.channel ? `inset 0 0 0 1px ${ACCENT}` : "none",
                      fontSize: 12.5, fontWeight: 600, color: channel === t.channel ? INK : DIM }}>
                    <ChannelIcon channel={t.channel} sx={{ fontSize: 15 }} />{t.channel}
                  </Box>
                ))}
                {!targets.length && (
                  <Typography variant="caption" sx={{ color: FAINT }}> {tx("No channel here can send yet — turn replies on for a mailbox or a chat in Connections.")} </Typography>
                )}
              </Box>
            </Box>
            <Box>
              <Label>{tx("To")}</Label>
              {channel === "email" ? (
                <EmailRecipients value={emailTo} onChange={setEmailTo} options={chanTargets}
                  placeholder={tx("Search contacts or type any email address")} />
              ) : <Autocomplete key={channel} size="small" fullWidth openOnFocus autoHighlight
                options={chanTargets}
                value={chanTargets.find((target) => target.to === to) || null}
                onChange={(_event, target) => setTo(target?.to || "")}
                getOptionLabel={recipientLabel}
                isOptionEqualToValue={(option, value) => option.to === value.to}
                filterOptions={(options, state) => recipientOptions(options, state.inputValue)}
                noOptionsText={chanTargets.length ? "No matching conversation" : "nothing known on this channel yet"}
                renderOption={(props, target) => (
                  <Box component="li" {...props} key={target.to} sx={{ display: "block !important", fontSize: 12.5 }}>
                    <Box sx={{ fontWeight: 600 }}>{target.name || target.to}</Box>
                    {target.hint && <Box sx={{ fontSize: 10.5, color: FAINT }}>{target.hint}</Box>}
                  </Box>
                )}
                renderInput={(params) => (
                  <TextField {...params} placeholder={tx("Search people and conversations")}
                    sx={{ "& .MuiInputBase-root": { fontSize: 13, bgcolor: "#fcfaf7" } }} />
                )} />}
            </Box>
            {channel === "email" && (
              <Box>
                <Label>CC</Label>
                <EmailRecipients value={cc} onChange={setCc} options={chanTargets}
                  placeholder={tx("Search contacts or type any email address")} />
                <Typography variant="caption" sx={{ color: FAINT, display: "block", mt: 0.75 }}> {tx("Drafts use STYLE.md. Docs → STYLE.md → Generate from history learns your recurring email signature.")} </Typography>
              </Box>
            )}
          </>
        )}

        {kind === "agent" && (
          <>
            {/* Not every job wants a keyboard. This sheet only ever opened a terminal, so a
                question you just wanted TALKED THROUGH had to be filed as a coding task and then
                walked back - the exact mistake newTask.js was written to prevent. Both doors,
                stated, and the choice made before anything is created. */}
            <Box>
              <Label>{tx("Who works it")}</Label>
              <Box sx={{ display: "flex", gap: 1 }}>
                <Fork on={how === "terminal"} onClick={() => { setHow("terminal"); setModel(""); }} title={tx("A live session")}
                  hint={tx("a CLI agent on a keyboard, in a checkout — it edits, runs and reports back.")} />
                <Fork on={how === "general"} onClick={() => { setHow("general"); setModel(""); }} title={tx("A general agent")}
                  hint={tx("a researcher, analyst or writer on its own — no repository. It looks things up, drafts and reports back.")} />
              </Box>
            </Box>
            {how === "general" && (
              <Box>
                <Label>{tx("Agent")}</Label>
                {/* the task page's hand-off, the same three questions: which profile, which brain, which model */}
                <Box sx={{ display: "flex", alignItems: "center", gap: 1.25, flexWrap: "wrap" }}>
                  <AgentPicker agents={agents} models={models} kinds={kinds} agent={role} model={model}
                    generalBrains={generalBrains} pick={pick} onPick={setPick}
                    onAgent={(a) => { setRole(a); setModel(""); }} onModel={setModel} size={30} />
                </Box>
              </Box>
            )}
            {how === "terminal" && (
              <Box>
                <Label>{tx("Agent")}</Label>
                <Box sx={{ display: "flex", alignItems: "center", gap: 1.25, flexWrap: "wrap" }}>
                  <AgentPicker agents={agents} models={models} kinds={kinds} coding agent={agent} model={model}
                    brains={brainList} brainModels={brainModels} brain={brain}
                    onBrain={(b) => { setBrain(b); setModel(""); }}
                    onAgent={(a) => { setAgent(a); setModel(""); }} onModel={setModel} size={30} />
                </Box>
                {/* the checkout: AUTO by default (what guess_repo always did), or chosen here - the owner, 2026-09-30:
                    "can't choose repo to create coding session in" */}
                <Box sx={{ mt: 1.25 }}><NewRepo agent={agent} bus={said} out={repoPick} first={aboutRef.current?.value || ""} /></Box>
                {/* A session you start is yours to end: the server marks the task the moment you open
                    one (selfclose.claim), whichever door you came through - no checkbox to forget. */}
              </Box>
            )}
          </>
        )}

        {kind === "repeat" && (
          <Box>
            <Label>{tx("Which kind")}</Label>
            <Box sx={{ display: "flex", gap: 1 }}>
              <Fork on={repeat === "workflow"} onClick={() => setRepeat("workflow")} title={tx("A workflow")}
                hint={tx("does the work on a schedule - checks, opens tasks, prepares drafts - and asks before it changes what you said it must not.")} />
              <Fork on={repeat === "report"} onClick={() => setRepeat("report")} title={tx("A report")}
                hint={tx("reads your systems on a schedule and summarises what it finds. It changes nothing.")} />
            </Box>
            <Typography variant="caption" sx={{ color: FAINT, display: "block", mt: 0.75 }}> {tx("It opens on Reports, where you describe it in your own words and it fills the form in.")} </Typography>
          </Box>
        )}

        {kind !== "repeat" && <Box>
          <Label>{kind === "goal" ? "What does done look like" : kind === "send" ? "What's this about"
            : kind === "agent" ? (how === "general" ? "What should it find out or write" : "What should it do")
            : "What do you want to remember"}</Label>
          <AboutField ref={aboutRef} kind={kind} how={how} onReady={setHasAbout} bus={said} pics={pics} />
          {kind === "send" && (
            <Typography variant="caption" sx={{ color: FAINT, display: "block", mt: 0.75 }}> {tx("Shorthand is fine — this is what you are telling the drafter, not what they read.")} </Typography>
          )}
        </Box>}

        {kind === "send" && (
          <Box>
            <Label>{tx("And then")}</Label>
            <Box sx={{ display: "flex", gap: 1 }}>
              <Fork on={mode === "draft"} onClick={() => setMode("draft")} title={tx("Draft it and show me")}
                hint={tx("written in your voice from the thread. It lands on the Timeline as 🏁 ready to close out.")} />
              <Fork on={mode === "task"} onClick={() => setMode("task")} title={tx("Find out first")}
                hint={tx("an agent researches it, then drafts the message from what it actually found.")} />
            </Box>
          </Box>
        )}

        {kind === "goal" && (
          <>
            <Box>
              <Label>{tx("By")}</Label>
              <TextField type="date" size="small" value={by} onChange={(e) => setBy(e.target.value)} sx={{ "& .MuiInputBase-root": { fontSize: 13, bgcolor: "#fcfaf7" } }} />
              <Typography sx={{ fontSize: 11, color: FAINT, mt: 0.5 }}>{tx("The date is the goal's clock: it sits where the age goes on your rail.")}</Typography>
            </Box>
            <Box>
              <Label>{tx("Who is involved")}</Label>
              <TextField fullWidth size="small" value={who} onChange={(e) => setWho(e.target.value)} placeholder={tx("Ray Colton, Payworth (Marcus), the coder")}
                sx={{ "& .MuiInputBase-root": { fontSize: 13, bgcolor: "#fcfaf7" } }} />
              <Typography sx={{ fontSize: 11, color: FAINT, mt: 0.5 }}>{tx("People it may chase and systems it may touch. Anyone else is a question to you first.")}</Typography>
            </Box>
            <Box>
              <Label>{tx("And then")}</Label>
              <Box sx={{ display: "flex", gap: 1 }}>
                <Fork on={plan} onClick={() => setPlan(true)} title={tx("Plan it and show me")}
                  hint={tx("the AI proposes the steps from your words; you cut or add, then start the first one. It lands on the rail as a goal.")} />
                <Fork on={!plan} onClick={() => setPlan(false)} title={tx("Track it, I have the plan")}
                  hint={tx("type the steps yourself on the task; it chases the people on them and reports against the date.")} />
              </Box>
            </Box>
          </>
        )}

        {kind === "note" && (
          <Box>
            <Label>{tx("Come back to it")}</Label>
            {/* the note's row is stamped with WHEN IT IS FOR, so the Timeline's own clock is the
                reminder: it sits in that day, out of the way until then (ownwork.note) */}
            <TextField type="datetime-local" size="small" value={when} onChange={(e) => setWhen(e.target.value)}
              sx={{ "& .MuiInputBase-root": { fontSize: 13, bgcolor: "#fcfaf7" } }} />
            <Typography variant="caption" sx={{ color: FAINT, display: "block", mt: 0.75 }}> {tx("Leave it empty for now. A date puts the row in that day and it stays quiet until then.")} </Typography>
          </Box>
        )}

        {err && <Alert severity="error" sx={{ py: 0.25, fontSize: 12.5 }}>{err}</Alert>}
        {ok && <Alert severity="success" sx={{ py: 0.25, fontSize: 12.5 }}>{ok}</Alert>}
      </DialogContent>

      <Box sx={{ display: "flex", gap: 1, justifyContent: "flex-end", px: 3, py: 1.75,
        borderTop: `1px solid ${BORDER}`, bgcolor: PANEL2 }}>
        <Button size="small" onClick={close} sx={{ color: DIM }}>{tx("Cancel")}</Button>
        <Button size="small" variant="contained" disableElevation disabled={!canGo || busy} onClick={submit}
          startIcon={busy ? <CircularProgress size={12} sx={{ color: "#fff" }} /> : null}
          sx={{ background: GRADIENT }}>{busy ? "Working…" : verb}</Button>
      </Box>
    </Shell>
  );
}
