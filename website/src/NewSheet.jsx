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
import React, { forwardRef, useCallback, useEffect, useId, useImperativeHandle, useRef, useState } from "react";
import {
  Alert, Autocomplete, Box, Button, Chip, CircularProgress, Dialog, DialogContent, DialogTitle, IconButton,
  TextField, Typography,
} from "@mui/material";
import CloseIcon from "@mui/icons-material/Close";
import api from "./api";
import { ACCENT, ACCENT2, BORDER, DIM, FAINT, GRADIENT, INK, PANEL, PANEL2, ROLES, mono } from "./theme.jsx";
import { ChannelIcon, AgentPicker, MicButton, useAgents, codingProfile, TaskuaryMark, usePeopleSearch } from "./ui.jsx";
import { withFound } from "./peopleSearch.js";
import { outcomeOf } from "./dispatchOutcome.js";
import { NO_REPO, planTask } from "./newTask.js";
import NewRepo from "./NewRepo.jsx";
import { AttachImage, ImageTray, usePromptImages, withImages } from "./promptImages.jsx";
import { emailRecipientOptions, normalizeEmails, recipientId, recipientLabel, recipientOptions, validEmail } from "./recipientOptions.js";
import FormControlLabel from "@mui/material/FormControlLabel";
import Checkbox from "@mui/material/Checkbox";
import SetupWithAi, { NEW_HASH } from "./SetupWithAi.jsx";
import { useVerbs } from "./actionRow.js";
import ConnectAi from "./ConnectAi.jsx";
import NewMeeting from "./NewMeeting.jsx";

// the server's own words for it (general.NO_AI)
const NO_AI_LINE = "No AI is connected, so an agent can't run this yet - connect one, then send it again.";
const NO_AI_PLAN = "No AI is connected to plan the steps - connect one, or choose Track it and add the steps yourself.";
import { connectorNamed } from "./connectorCatalog.js";
import { openAppLink } from "./appLinks.js";
import { NEW_PB, askPlaybook } from "./playbookOpen.js";
import { DASH, place } from "./words.js";
import { label as btn } from "./buttons.js";
import { useCapabilities } from "./capabilities.js";
import { FOCUS_RING, pressable } from "./pressable.js";

const KINDS = [
  { key: "send",   mark: "✉️", label: "Send something", hint: "a message you start, drafted in your voice and approved by you" },
  { key: "agent",  mark: <TaskuaryMark size={14} />, label: "Give an agent a job", hint: "an agent works on it for you and reports back" },
  { key: "note",   mark: "💡", label: "Note to self", hint: "a reminder or an idea — nothing works it, it just sits on the day you pick" },
  // ...and a meeting (the owner, 2026-10-28: "probably new meeting screen is better"): free times off your calendar and theirs, the invite drafted for your Send
  { key: "meeting", mark: "📅", label: "Meeting", hint: "a time with people, found on your calendar and theirs — the invite is drafted for your Send" },
  { key: "goal",   mark: "🎯", label: "Set a goal", hint: "an outcome with a date and steps — the steps are tasks, and it stays on your rail until it is done" },
  // A JOB THAT REPEATS, one tab each (the owner, 2026-10-15: "we need 2, one for reports and one for workflows"): say it in
  // your words and Build it - the draft opens on Reports, filled in, to check and save. The same box Reports has (Composer)
  { key: "report",   mark: "📊", label: "Report", hint: "reads your systems on a schedule and summarises what it finds — it changes nothing" },
  // ...and beside it, a dashboard (the owner, 2026-10-23: "similar to reports but more visual"): described here, drafted by the same
  // box, and opened on Reports → Dashboards drawn over real rows to save
  { key: "dashboard", mark: "📈", label: DASH.tab, hint: DASH.tab_hint },
  { key: "workflow", mark: "🔁", label: "Routine", hint: "does the work on a schedule — checks, opens tasks, prepares drafts — and asks before what you said it must not" },
  // ...and the third thing Reports keeps (the owner, 2026-10-22: "this is not playbook ui?" - asked for one, the Assistant handed it to a
  // general agent as its job). Its words go to the shelf's own New playbook, which sets it up with AI there (playbookOpen.askPlaybook)
  { key: "playbook", mark: "📖", label: "Playbook", hint: "how one kind of request is handled from now on — triage matches new mail to it, and its steps are followed your way" },
];
const REPEATS = ["report", "dashboard", "workflow"];

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

// A WHOLE ADDRESS TYPED IS AN ADDRESS GIVEN, however the box is left: Tab or a click away threw it away, and the reply went to
// nobody (the UI audit, 2026-10-21). Only a whole address is taken - half a name never becomes a recipient behind the owner's back.
export const EmailRecipients = ({ value, onChange, options, placeholder }) => {
  const [typed, setTyped] = useState("");
  // ...and the server's search beside the list this form was given: "dynamo" is everyone at Dynamo (peopleSearch.js)
  const found = usePeopleSearch(typed, "email");
  const take = () => { const v = typed.trim(); if (validEmail(v)) { onChange(normalizeEmails([...value, v])); setTyped(""); } };
  return (
  <Autocomplete multiple freeSolo autoHighlight openOnFocus size="small" fullWidth
    options={options}
    value={value} inputValue={typed} onInputChange={(_event, v, why) => { if (why !== "reset") setTyped(v); }}
    onBlur={take}
    onChange={(_event, values) => { onChange(normalizeEmails(values)); setTyped(""); }}
    getOptionLabel={(option) => typeof option === "string" ? option : (option.name || option.to || "")}
    isOptionEqualToValue={(option, selected) => option.to?.toLowerCase() === String(selected).toLowerCase()}
    filterOptions={(rows, state) => withFound(emailRecipientOptions(rows, state.inputValue), found, state.inputValue)}
    renderTags={(emails, getTagProps) => emails.map((email, index) => (
      <Chip {...getTagProps({ index })} key={email} label={email} size="small" sx={{ maxWidth: 260 }} />
    ))}
    renderOption={(props, option) => {
      const address = typeof option === "string" ? option : option.to;
      return (
        <Box component="li" {...props} key={address} sx={{ display: "block !important", fontSize: 12.5 }}>
          <Box sx={{ fontWeight: 600 }}>{typeof option === "string" ? `Use ${address}` : (option.name || address)}</Box>
          {typeof option !== "string" && <Box sx={{ fontSize: 10.5, color: FAINT }}>{option.found && option.hint ? `${option.hint} · ${address}` : address}</Box>}
        </Box>
      );
    }}
    renderInput={(params) => (
      <TextField {...params} placeholder={value.length ? "Add another email" : placeholder}
        sx={{ "& .MuiInputBase-root": { fontSize: 13, bgcolor: "#fcfaf7" } }} />
    )} />
  );
};

// WHO A CHAT GOES TO, picked by name: the known chats on this channel, and the server's search over them as you type - a description
// the plain match cannot place goes to the model once (peopleSearch.js). Its own component, so a keystroke redraws the box, not the sheet.
export const ChatRecipient = ({ channel, options, value, onChange }) => {
  const [typed, setTyped] = useState("");
  const found = usePeopleSearch(typed, channel);
  return (
    <Autocomplete size="small" fullWidth openOnFocus autoHighlight options={options} value={value}
      onInputChange={(_event, v, why) => { if (why !== "reset") setTyped(v || ""); }}
      onChange={(_event, target) => onChange(target)}
      getOptionLabel={recipientLabel}
      isOptionEqualToValue={(option, v) => option.to === v.to}
      filterOptions={(rows, state) => withFound(recipientOptions(rows, state.inputValue), found, state.inputValue)}
      noOptionsText={options.length ? "No matching conversation" : "nothing known on this channel yet"}
      renderOption={(props, target) => (
        <Box component="li" {...props} key={target.to} sx={{ display: "block !important", fontSize: 12.5 }}>
          <Box sx={{ fontWeight: 600 }}>{recipientLabel(target)}</Box>
          {recipientId(target) && <Box sx={{ ...mono, fontSize: 10, color: FAINT }}>{recipientId(target)}</Box>}
          {target.hint && <Box sx={{ fontSize: 10.5, color: FAINT }}>{target.hint}</Box>}
        </Box>
      )}
      renderInput={(params) => (
        <TextField {...params} placeholder="Search people and conversations"
          sx={{ "& .MuiInputBase-root": { fontSize: 13, bgcolor: "#fcfaf7" } }} />
      )} />
  );
};

// Keep the large freeform field below its own render boundary. The sheet contains provider
// discovery, menus, forks, and a MUI dialog; owning this value at the sheet level rebuilt all of
// that on every keystroke and made an ordinary sentence feel like terminal input over a slow
// connection. The parent only hears when empty/non-empty changes and reads the value on submit.
const AboutField = React.memo(forwardRef(function AboutField({ kind, how, onReady, bus, pics, initial = "", onWords }, ref) {
  const [value, setValue] = useState(initial);
  const ready = useRef(false);
  // the words the Assistant wrote it up with (concierge._new) count as typed: the button is live from the first render
  useEffect(() => { if (initial.trim()) { ready.current = true; onReady(true); bus?.current?.(initial); } }, []);   // eslint-disable-line react-hooks/exhaustive-deps
  const timer = useRef(0);
  useEffect(() => () => clearTimeout(timer.current), []);
  useImperativeHandle(ref, () => ({ value, clear: () => { ready.current = false; setValue(""); bus?.current?.(""); } }), [value, bus]);
  const changed = (e) => {
    const next = e.target.value;
    setValue(next);
    const hasText = !!next.trim();
    if (hasText !== ready.current) { ready.current = hasText; onReady(hasText); }
    // the repository picker hears the words on a pause in typing, never per key (only it re-renders, not the card)
    if (bus?.current || onWords) { clearTimeout(timer.current); timer.current = setTimeout(() => { bus?.current?.(next); onWords?.(next); }, 200); }
  };
  // ...and a picture pasted or dropped into it goes with the words (a note to self keeps words only)
  const withPics = pics && kind !== "note" && kind !== "playbook";     // ...and New playbook takes words (POST /api/playbooks/setup)
  return (
    <>
    <TextField fullWidth multiline minRows={kind === "note" ? 2 : 3} value={value} autoFocus
      onChange={changed} {...(withPics ? pics.drop : {})}
      placeholder={kind === "goal" ? "the nightly census lands in the new ledger for all three sites, and the old portal's export is switched off"
        : kind === "send" ? "the census numbers he asked for, plus why Site 7 moved"
        : kind === "agent" ? (how === "general" ? "why did Site 3's census move four points in July?"
          : "work out why the nightly export drops the last facility")
        : kind === "playbook" ? "when someone asks for their leave balance, gather it from payroll and draft the reply for my review"
        : "chase the Payworth AP replacement"}
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
// `line`: the Assistant's line that wrote this card (concierge._new) - its press says that line again as what it started (`onSaid`)
// `initialChannel` / `initialTo`: Send something already addressed - a People hit's Message them (SearchEverything, trust audit F6)
export default function NewSheet({ open, onClose, onDone, onOpenTask, inline = false, initialKind = "send", initialHow = "", initialText = "", line = null, onSaid,
  initialChannel = "", initialTo = "", initialMeeting = null, initialRoutine = null }) {
  const [kind, setKind] = useState(initialKind);
  const said = useRef(null);      // the words, for the repository picker (see NewRepo)
  const repoPick = useRef(null);  // what the picker says to use, read on submit
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [errAi, setErrAi] = useState(false);      // the error is "no AI is connected": it carries Connect an AI
  const [ok, setOk] = useState("");

  // send
  const [targets, setTargets] = useState([]);          // [{channel, to: [{to, name, hint}]}]
  const [targetsRead, setTargetsRead] = useState(false);   // an empty list before the answer is not "nothing can send"
  const [channel, setChannel] = useState("");
  const [to, setTo] = useState("");
  const [emailTo, setEmailTo] = useState([]);
  const [cc, setCc] = useState([]);
  const [hasAbout, setHasAbout] = useState(false);
  const aboutRef = useRef(null);
  const [mode, setMode] = useState("draft");
  const pics = usePromptImages();
  // agent
  const { agents, models, kinds, brainList, brainModels, generalBrains, agentsRead, codingReady } = useAgents();
  const [agent, setAgent] = useState("");   // the coding profile, by kind; blank = the server finds it
  const [brain, setBrain] = useState("");   // WHICH CLI runs it; blank = the brain settings name
  const [model, setModel] = useState("");
  const [role, setRole] = useState("");     // a general agent: which profile (researcher, analyst...)
  const [pick, setPick] = useState("");     // ...and which brain runs it; blank = the General agent setting
  // "terminal" = a CLI on a keyboard, "general" = a general agent with no repository. Held here rather
  // than inferred from the words: a question landing in a terminal by ACCIDENT is exactly what
  // newTask.planTask exists to stop, and it will not guess for us.
  const [how, setHow] = useState(initialHow || "terminal");
  // A session you open here is usually one you mean to sit in, so it does not end itself: the
  // judge that closes a router's task on a quiet screen would close this one while you read it.
  // note
  const [when, setWhen] = useState("");
  // a goal (spec 2026-10-12): what done looks like is the words above; by when, who is involved, and whether the AI plans the steps
  const noAi = useCapabilities().ai === false;
  // ...Plan it only with an AI to plan: pre-selected with none, the goal's first press failed into NO_AI_PLAN (2026-10-22 walk). The
  // capability lands after the first draw, so it is followed until the owner picks a side
  const [by, setBy] = useState(""); const [who, setWho] = useState(""); const [plan, setPlan] = useState(!noAi), planPicked = useRef(false);
  useEffect(() => { if (!planPicked.current) setPlan(!noAi); }, [noAi]);
  const filed = useRef(null);      // a task this sheet filed whose start was refused: {taskId, ref, about, how}

  useEffect(() => { if (!open) return; setErr(""); setOk(""); setKind(initialKind); }, [open, initialKind]);
  useEffect(() => {
    if (!agents.includes(agent)) { setAgent(codingProfile(agents, kinds)); setModel(""); }
  }, [agents, kinds, agent]);
  // a new general task has no profile to keep, so the first general role is chosen rather than "the profile it has"
  const roles = agents.filter((a) => !["coding", "cli"].includes(String(kinds[a] || "").toLowerCase()));
  useEffect(() => { if (!role && roles.length) setRole(roles.includes("researcher") ? "researcher" : roles[0]); }, [roles, role]);
  useEffect(() => {
    if (!open) return;
    api.get("/api/send-targets").then(({ data }) => {
      const list = data.data || [];
      setTargets(list); setTargetsRead(true);
      const asked = initialChannel && list.some((t) => t.channel === initialChannel) ? initialChannel : "";
      setChannel((c) => asked || c || list[0]?.channel || "");
      if (asked && initialTo) { if (asked === "email") setEmailTo([initialTo]); else setTo(initialTo); }
      // NOTHING CAN SEND: New opened on Send something anyway, a whole form to fill that could only fail (the walk click-through,
      // 2026-10-17). It opens on the next tab that works; Send something stays one click away and says what it needs.
      if (!list.length) setKind((k) => (k === "send" && initialKind === "send" ? "agent" : k));
    }).catch(() => setTargets([]));
  }, [open]);
  // A CONNECTOR NAMED IN AN AGENT'S JOB is offered its card on the row, beside Start (connectorCatalog.connectorNamed): "connect taskuary
  // to linkedin" was only ever an agent job, with no way to Connections (a tester, 2026-10-20). The words still go to an agent if pressed.
  const [words, setWords] = useState(initialText);
  const named = kind === "agent" ? connectorNamed(words) : null;
  // each sheet registers as ITSELF: the Feed's closed dialog and the chat's open card both said "new-send", one cleared what the
  // other put, and every put re-drew both - the Send something tab died in that loop (React #185, the UI audit 2026-10-21)
  const me = useId();
  useVerbs(`new-connect${me}`, named ? [{ id: "new:open-connector", group: "decide", tone: "s", label: `Open the ${named.title} card`,
    title: `${named.title} is connected on its own card under Connections - no agent needed`,
    run: () => { onClose?.(); openAppLink(`#connector=${named.type}`); } }] : [], open && !!named);
  // ...and what it needs is a button on the row, not a sentence pointing at Connections
  useVerbs(`new-send${me}`, [{ id: "new:connect-sending", group: "decide", tone: "s", label: "Connect a mailbox",
    title: "Sending needs a mailbox or a chat with replies on", run: () => openAppLink(place("mail").href) }], open && targetsRead && kind === "send" && !targets.length);

  const chanTargets = (targets.find((t) => t.channel === channel)?.to) || [];
  const mailTargets = (targets.find((t) => t.channel === "email")?.to) || [];
  const close = () => { if (!busy) onClose?.(); };

  const submit = useCallback(async () => {
    setBusy(true); setErr(""); setErrAi(false); setOk("");
    const about = String(aboutRef.current?.value || "").trim();
    try {
      if (kind === "send") {
        const { data } = await api.post("/api/outbox", {
          channel, to: channel === "email" ? emailTo : to.trim(),
          cc: channel === "email" ? cc : [], about: withImages(about, pics.paths), mode,
        });
        setOk(mode === "task"
          ? `${data.ref} — an agent is finding out first; the message is drafted when it is done.`
          : `${data.ref} — drafted. It is open now, waiting for you to send it.`);
        aboutRef.current?.clear(); setHasAbout(false); pics.clear(); onDone?.(); onOpenTask?.(data.taskId);
      } else if (kind === "agent") {
        // one module decides chat-vs-terminal for the whole app, so the Board and this sheet can
        // never disagree about what "no repository" means
        const general = how === "general";
        // NOTHING TO RUN IT ON, SAID HERE AND THE SHEET STAYS OPEN (owner-approved, 2026-10-21): the task was made, its agent failed a
        // second later, and it sat on the rail under "waiting on you". Read fresh - the list loaded with the sheet may be from before
        if (general && !((await api.get("/api/agents")).data?.general_brains || []).length) {
          setErr(NO_AI_LINE); setErrAi(true); setBusy(false); return;
        }
        // a session opens where the picker says (auto = the repository the words name, else the server guesses as ever);
        // the choice is the task's `repo:` tag, the override that always wins
        const pickd = general ? null : repoPick.current?.(about) || null;
        // a general agent: kind general with no repository, started below like the task page's hand-off - never the
        // assistant's thread, which does nothing itself (2026-10-15)
        const plan = planTask(general ? NO_REPO : pickd?.repo || null, general ? "file" : "terminal", false, true);
        // A START REFUSED FILES ONE TASK, NOT ONE PER PRESS (the UI audit, 2026-10-21): the task was made before the start was asked
        // for, so each retry of a refused start filed another copy nobody worked on. The same words pressed again start the one filed.
        const again = filed.current?.about === about && filed.current.how === how ? filed.current : null;
        const data = again || (await api.post("/api/tasks", { Title: about.slice(0, 300), Summary: withImages(about, pics.paths),
          Kind: plan.kind, Tags: plan.tags })).data;
        if (!again) {
          filed.current = { ...data, about, how };
          // it skipped triage, so nothing gave it a checklist: read the words behind the answer (server._read_hand_task)
          api.post(`/api/tasks/${data.taskId}/read-ask`).catch(() => null);
        }
        // a folder typed for a repository the agent had none for is saved on the agent first - the session refuses to open without one
        if (pickd?.repo && pickd.path) await api.put(`/api/tasks/${data.taskId}/repo`, { repo: pickd.repo, path: pickd.path, ...(agent ? { agent } : {}) });
        let out;
        try {
          // WHAT THE ANSWER SAID, not what the button hoped. A task with no checkout comes back
          // `needs_repo` with started: false, and this announced "is on it in a live session" over
          // the top of it (the owner, 2026-09-22: "hit the new button with coding agent but it did
          // not start"). One reading of a dispatch answer, the same one every other surface uses.
          ({ data: out } = await api.post(`/api/tasks/${data.taskId}/dispatch`, { ...(general
            ? { kind: "general", agent: role || null, pick: pick || null, model: model || null }
            : { agent: agent || null, brain: brain || null, model: model || null }), ...(line ? { said: line } : {}) }));
        } catch (e) {
          // ...and the line says the task is there: "nothing started" over a task already filed sent the owner to press again
          throw { response: { data: { detail: `${data.ref} is filed but did not start - ${String(e?.response?.data?.detail || "the start was refused").replace(/\.$/, "")}. Press ${verb} to try it again.` } } };
        }
        filed.current = null;
        if (out?.said) onSaid?.(out.said);
        setOk(`${data.ref} — ${outcomeOf(out).text}.`);
        aboutRef.current?.clear(); setHasAbout(false); pics.clear(); onDone?.(); onOpenTask?.(data.taskId);
      } else if (kind === "playbook") {
        // the one road to a playbook is the shelf's New playbook: this press is its Set up with AI, made there once with these words
        askPlaybook(about, true); onClose?.(); openAppLink(`report=${NEW_PB}`);
      } else if (kind === "goal") {
        // PLAN IT WITH NO AI SAYS SO (owner-approved, 2026-10-21): it promised "planning the steps; they land in a moment" and none came
        if (plan && !((await api.get("/api/agents")).data?.general_brains || []).length) {
          setErr(NO_AI_PLAN); setErrAi(true); setBusy(false); return;
        }
        const title = about.split(/[.\n]/)[0].trim().slice(0, 120) || about.slice(0, 120);
        const { data } = await api.post("/api/tasks", { Title: title, Summary: who ? `${about}\nInvolved: ${who}` : about,
          DoneWhen: about.slice(0, 1000), DueAt: by || null, Kind: "task", Tags: "goal" });
        // the model writes the steps (server.plan_goal); "Track it" leaves the boxes to you
        if (plan && !noAi) api.post(`/api/tasks/${data.taskId}/read-ask`, { goal: true }).catch(() => null);
        // ...and with no AI nothing plans them: it promised steps that never came (the UI audit, 2026-10-21)
        setOk(`${data.ref} — ${!plan ? "on your rail; add the steps on the task." : noAi ? "on your rail. No AI is connected, so nothing can plan the steps - add them on the task."
          : "planning the steps; they land on the task in a moment."}`);
        aboutRef.current?.clear(); setHasAbout(false); setBy(""); setWho(""); onDone?.(); onOpenTask?.(data.taskId);
      } else {
        const { data } = await api.post("/api/notes", { title: about.slice(0, 300), body: "", when: when || null });
        setOk(`Noted — it sits on ${String(data.at).slice(0, 16)} and nothing will touch it.`);
        aboutRef.current?.clear(); setHasAbout(false); setWhen(""); onDone?.();
      }
    } catch (e) { setErr(e?.response?.data?.detail || "That did not go through"); }
    setBusy(false);
  }, [kind, channel, to, emailTo, cc, mode, how, agent, brain, model, role, pick, when, by, who, plan, noAi, onDone, onOpenTask, onClose, pics, line, onSaid]);

  // ...and no live session without a coding tool the owner chose (owner-approved, 2026-10-21): Send to coding agent stays disabled
  const noCodingTool = kind === "agent" && how === "terminal" && (!agentsRead || !codingReady);
  const canGo = hasAbout && !noCodingTool && (kind !== "send" || (channel && (channel === "email" ? emailTo.length : to.trim())));
  // a hand-off is the one Send to agent / Send to coding agent (buttons.json); the others are this form's own words
  const verb = kind === "send" ? (mode === "task" ? btn("regular_agent") : "Draft it")
    : kind === "agent" ? btn(how === "general" ? "regular_agent" : "coding_agent") : kind === "goal" ? (plan ? "Plan it" : "Track it")
    : kind === "playbook" ? "Set up with AI" : "Note it";

  // the card: a bordered block in the conversation's width, Esc closes it, nothing floats over the page
  const Shell = inline ? Box : Dialog;
  const shell = inline
    ? { "data-tq-new": "", onKeyDown: (e) => { if (e.key === "Escape") close(); },
        sx: { border: `1px solid ${BORDER}`, borderRadius: "12px", bgcolor: PANEL, overflow: "hidden", scrollMarginTop: "8px" } }
    : { open: !!open, onClose: close, fullWidth: true, maxWidth: "md", "data-tq-keep": true };   // md: the tabs fit on one line, and scroll sideways when they do not
  if (inline && !open) return null;
  return (
    <Shell {...shell}>
      <DialogTitle sx={{ display: "flex", alignItems: "center", gap: 1, pb: 0.5 }}>
        <Box sx={{ flex: 1 }}>What are we starting?</Box>
        <IconButton aria-label="Close new task" size="small" onClick={close}><CloseIcon sx={{ fontSize: 17 }} /></IconButton>
      </DialogTitle>

      {/* the kinds are tabs, not a select: three doors that all exist is the point of the sheet,
          and a closed dropdown hides two of them behind a click */}
      <Box sx={{ display: "flex", gap: 0.25, px: { xs: 1, sm: 3 }, borderBottom: `1px solid ${BORDER}`, overflowX: "auto", scrollbarWidth: "none" }}>
        {KINDS.map((k) => (
          <Box key={k.key} {...pressable(() => { setKind(k.key); setErr(""); setOk(""); })} role="tab"
            aria-selected={kind === k.key} title={k.hint}
            sx={{ ...FOCUS_RING, display: "flex", alignItems: "center", gap: 0.75, px: { xs: 1, sm: 1.5 }, py: 1, cursor: "pointer", flexShrink: 0,
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
                  <Box key={t.channel} onClick={() => { setChannel(t.channel); setTo(""); setEmailTo([]); setCc([]); }}
                    sx={{ display: "flex", alignItems: "center", gap: 0.75, px: 1.25, py: 0.75, cursor: "pointer",
                      border: `1px solid ${channel === t.channel ? ACCENT : BORDER}`, borderRadius: 2,
                      boxShadow: channel === t.channel ? `inset 0 0 0 1px ${ACCENT}` : "none",
                      fontSize: 12.5, fontWeight: 600, color: channel === t.channel ? INK : DIM }}>
                    <ChannelIcon channel={t.channel} sx={{ fontSize: 15 }} />{t.channel}
                  </Box>
                ))}
                {!targets.length && (
                  <Typography variant="caption" sx={{ color: FAINT }}>
                    Nothing here can send yet - connect a mailbox, or turn replies on for a chat (the button below).
                  </Typography>
                )}
              </Box>
            </Box>
            <Box>
              <Label>To</Label>
              {channel === "email" ? (
                <EmailRecipients value={emailTo} onChange={setEmailTo} options={chanTargets}
                  placeholder="Search contacts or type any email address" />
              ) : <ChatRecipient key={channel} channel={channel} options={chanTargets}
                value={chanTargets.find((target) => target.to === to) || (to ? { to, name: "" } : null)}
                onChange={(target) => setTo(target?.to || "")} />}
            </Box>
            {channel === "email" && (
              <Box>
                <Label>CC</Label>
                <EmailRecipients value={cc} onChange={setCc} options={chanTargets}
                  placeholder="Search contacts or type any email address" />
                <Typography variant="caption" sx={{ color: FAINT, display: "block", mt: 0.75 }}>
                  Drafts use STYLE.md. Docs → STYLE.md → Generate from history learns your recurring email signature.
                </Typography>
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
              <Label>Who works it</Label>
              <Box sx={{ display: "flex", gap: 1 }}>
                <Fork on={how === "terminal"} onClick={() => { setHow("terminal"); setModel(""); }} title="A live session"
                  hint="a CLI agent on a keyboard, in a checkout — it edits, runs and reports back." />
                <Fork on={how === "general"} onClick={() => { setHow("general"); setModel(""); }} title="A general agent"
                  hint="a researcher, analyst or writer on its own. It looks things up, drafts and reports back." />
              </Box>
            </Box>
            {how === "general" && (
              <Box>
                <Label>Agent</Label>
                {/* the task page's hand-off, the same three questions: which profile, which brain, which model */}
                <Box sx={{ display: "flex", alignItems: "center", gap: 1.25, flexWrap: "wrap" }}>
                  <AgentPicker agents={agents} models={models} kinds={kinds} agent={role} model={model}
                    generalBrains={generalBrains} brainsRead={agentsRead} pick={pick} onPick={setPick}
                    onAgent={(a) => { setRole(a); setModel(""); }} onModel={setModel} size={30} />
                </Box>
              </Box>
            )}
            {how === "terminal" && (
              <Box>
                <Label>Agent</Label>
                <Box sx={{ display: "flex", alignItems: "center", gap: 1.25, flexWrap: "wrap" }}>
                  <AgentPicker agents={agents} models={models} kinds={kinds} coding agent={agent} model={model}
                    brains={brainList} brainModels={brainModels} brain={brain} brainsRead={agentsRead} codingReady={codingReady}
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

        {REPEATS.includes(kind) && (
          // ...THE DESCRIBE BOX IS THE CHAT'S NOW (2026-10-30): its builder comes up, and the Assistant sets it up there with you - or by hand
          <Box data-tq-new-repeat={kind} sx={{ display: "flex", alignItems: "center", gap: 1, flexWrap: "wrap" }}>
            <SetupWithAi kind={kind} words={kind === initialKind ? initialText : ""} onOpen={() => { onClose?.(); openAppLink(NEW_HASH[kind]); }} />
            <Button size="small" onClick={() => { onClose?.(); openAppLink(NEW_HASH[kind]); }}>Set it up by hand</Button>
          </Box>
        )}

        {kind === "meeting" && (
          // ...its own form, its own Find times: the pick is the press, so the footer keeps only Cancel
          <NewMeeting renderTo={(p) => <EmailRecipients {...p} />} options={mailTargets} initial={initialKind === "meeting" ? initialMeeting || { about: initialText } : {}}
            onPicked={(d) => { setOk(`${d.ref} — the invite is drafted in Close out, waiting for your ${btn("approve")}. Nothing went out.`); onDone?.(); onOpenTask?.(d.taskId); }} />
        )}

        {!REPEATS.includes(kind) && kind !== "meeting" && <Box>
          <Label>{kind === "goal" ? "What does done look like" : kind === "send" ? "What's this about"
            : kind === "agent" ? (how === "general" ? "What should it find out or write" : "What should it do")
            : kind === "playbook" ? "What should this playbook do" : "What do you want to remember"}</Label>
          <AboutField ref={aboutRef} kind={kind} how={how} onReady={setHasAbout} bus={said} pics={pics} initial={initialText} onWords={setWords} />
          {kind === "send" && (
            <Typography variant="caption" sx={{ color: FAINT, display: "block", mt: 0.75 }}>
              Shorthand is fine — this is what you are telling the drafter, not what they read.
            </Typography>
          )}
          {kind === "playbook" && (
            <Typography variant="caption" sx={{ color: FAINT, display: "block", mt: 0.75 }}>
              It opens under Reports → Playbooks, where your assistant drafts the steps with you — Approve there saves it.
            </Typography>
          )}
        </Box>}

        {kind === "send" && (
          <Box>
            <Label>And then</Label>
            <Box sx={{ display: "flex", gap: 1 }}>
              <Fork on={mode === "draft"} onClick={() => setMode("draft")} title="Draft it and show me"
                hint="written in your voice from the thread. It opens for you as 🏁 ready to send - sending it leaves the task open." />
              <Fork on={mode === "task"} onClick={() => setMode("task")} title="Find out first"
                hint="an agent researches it, then drafts the message from what it actually found." />
            </Box>
          </Box>
        )}

        {kind === "goal" && (
          <>
            <Box>
              <Label>By</Label>
              <TextField type="date" size="small" value={by} onChange={(e) => setBy(e.target.value)} sx={{ "& .MuiInputBase-root": { fontSize: 13, bgcolor: "#fcfaf7" } }} />
              <Typography sx={{ fontSize: 11, color: FAINT, mt: 0.5 }}>The date shows on the goal's row on your rail, as "due" and the day.</Typography>
            </Box>
            <Box>
              <Label>Who is involved</Label>
              <TextField fullWidth size="small" value={who} onChange={(e) => setWho(e.target.value)} placeholder="Ray Colton, Payworth (Marcus), the coding agent"
                sx={{ "& .MuiInputBase-root": { fontSize: 13, bgcolor: "#fcfaf7" } }} />
              <Typography sx={{ fontSize: 11, color: FAINT, mt: 0.5 }}>People it may chase and systems it may touch. Anyone else is a question to you first.</Typography>
            </Box>
            <Box>
              <Label>And then</Label>
              <Box sx={{ display: "flex", gap: 1 }}>
                <Fork on={plan} onClick={() => { planPicked.current = true; setPlan(true); }} title="Plan it and show me"
                  hint="the AI proposes the steps from your words; you cut or add, then start the first one. It lands on the rail as a goal." />
                <Fork on={!plan} onClick={() => { planPicked.current = true; setPlan(false); }} title="Track it, I have the plan"
                  hint="type the steps yourself on the task; it chases the people on them and reports against the date." />
              </Box>
            </Box>
          </>
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

        {err && <Alert severity="error" sx={{ py: 0.25, fontSize: 12.5, alignItems: "center" }}
          action={errAi ? <ConnectAi onGo={() => onClose?.()} /> : null}>{err}</Alert>}
        {ok && <Alert severity="success" sx={{ py: 0.25, fontSize: 12.5 }}>{ok}</Alert>}
      </DialogContent>

      <Box sx={{ display: "flex", gap: 1, justifyContent: "flex-end", px: 3, py: 1.75,
        borderTop: `1px solid ${BORDER}`, bgcolor: PANEL2 }}>
        <Button size="small" onClick={close} sx={{ color: DIM }}>Cancel</Button>
        {!REPEATS.includes(kind) && kind !== "meeting" && <Button size="small" variant="contained" disableElevation disabled={!canGo || busy} onClick={submit}
          startIcon={busy ? <CircularProgress size={12} sx={{ color: "#fff" }} /> : null}
          sx={{ background: GRADIENT }}>{busy ? "Working…" : verb}</Button>}
      </Box>
    </Shell>
  );
}
