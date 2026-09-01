// Getting started, done here rather than described here.
//
// A fresh install opens on an empty Timeline that looks exactly like a working install on a quiet
// morning, and the few things standing between those two states live on different tabs.
// The first version of this pointed at those tabs. Pointing is not setting up: it hands the work
// back with directions attached.
//
// So every step that CAN be done in one or two fields is done here, against the same endpoints
// the Connections tab uses, and then TESTED - a key that is saved but wrong is not a connected
// brain, and finding that out later, from an empty Timeline, is the failure this exists to
// prevent. What genuinely cannot be (Outlook and Teams need an app registration; Slack needs a
// bot token) says so plainly and opens the card.
import React, { useCallback, useEffect, useState } from "react";
import {
  Alert, Box, Button, Chip, CircularProgress, Dialog, DialogContent, MenuItem, Select, TextField,
  Tooltip, Typography,
} from "@mui/material";
import CheckCircleIcon from "@mui/icons-material/CheckCircle";
import RadioButtonUncheckedIcon from "@mui/icons-material/RadioButtonUnchecked";
import CloseIcon from "@mui/icons-material/Close";
import OpenInNewIcon from "@mui/icons-material/OpenInNew";
import api from "./api";
import SoulInterview from "./SoulInterview.jsx";
import { BORDER, DIM, FAINT, INK, PANEL2 } from "./theme.jsx";

// "Three things and Taskuary works" was prose. Steps were added to the wizard and it went on
// saying three, because a number written as a word is a number nobody updates. Counted now -
// and counted over the SAME list the panel shows and the top-bar pill tracks (the guided steps),
// so the headline, the pill and the rows can never disagree again.
const COUNT = ["No", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten"];
const spell = (n) => COUNT[n] || String(n);

export const useSetup = (tick) => {
  const [state, setState] = useState(null);
  const load = useCallback(() => {
    api.get("/api/setup").then(({ data }) => setState(data)).catch(() => {});
  }, []);
  useEffect(() => { load(); }, [load, tick]);
  return [state, load];
};

/* The counter covers the three essentials plus the recommended first sync and personalization.
   "Ready" means the funnel works; "complete" means its first drafts and triage have also learned
   from the owner's history. A dismissed checklist stays as a quiet way back until it is complete. */
export const SetupChip = ({ state, onOpen }) => {
  if (!state || state.complete) return null;
  const done = state.guide_done ?? state.done;
  const total = state.guide_total ?? state.total;
  const pct = total ? (done / total) * 100 : 0;
  return (
    <Tooltip title={state.dismissed ? "Setup — put away, click to reopen"
      : state.ready ? "Finish personalizing Taskuary" : "Finish setting Taskuary up"}>
      <Box onClick={onOpen}
        sx={{ display: "flex", alignItems: "center", gap: 0.75, cursor: "pointer", ml: 1,
          px: 1, py: 0.35, borderRadius: 99, border: `1px solid ${state.dismissed ? BORDER : "#d8cfbe"}`,
          bgcolor: state.dismissed ? "transparent" : "#eae4d8",
          opacity: state.dismissed ? 0.75 : 1, "&:hover": { opacity: 1 } }}>
        <Box sx={{ position: "relative", display: "flex", width: 16, height: 16 }}>
          <CircularProgress variant="determinate" value={100} size={16} thickness={6}
            sx={{ color: "#e6e9ef", position: "absolute" }} />
          <CircularProgress variant="determinate" value={pct} size={16} thickness={6} sx={{ color: "#55697a" }} />
        </Box>
        <Typography variant="caption" sx={{ fontWeight: 700, color: state.dismissed ? DIM : "#55697a" }}>
          {done}/{total}
        </Typography>
      </Box>
    </Tooltip>
  );
};

/* AI providers that are genuinely one field. Azure needs an endpoint AND a deployment name, and
   Ollama needs the name of a model you have actually pulled - both belong on the card, where
   there is room to say so. Offering them here as "paste a key" would be a lie. */
const BRAINS = [
  { type: "anthropic", label: "Anthropic", hint: "console.anthropic.com → API keys", ph: "sk-ant-…" },
  { type: "openai", label: "OpenAI", hint: "platform.openai.com → API keys", ph: "sk-…" },
  { type: "openrouter", label: "OpenRouter", hint: "one key, most models", ph: "sk-or-…" },
];
/* Mailboxes that connect with an address and a password. Outlook and Teams need an Entra app
   registration (three values and an admin consent screen); Slack needs a bot token from an app
   you create. Those are card work, and saying so is kinder than a form that cannot finish. */
const BOXES = [
  { type: "gmail", label: "Gmail", hint: "needs an App Password, not your Google password — myaccount.google.com → Security → App passwords" },
  { type: "imap", label: "Any other mailbox", hint: "IMAP — your provider's host, address and password" },
];

const Field = (p) => <TextField size="small" fullWidth sx={{ bgcolor: "#fff" }} {...p} />;

/* Every inline form ends the same way: save, then TEST, and say which of the two failed. A key
   that saved and does not work is the exact state this wizard exists to prevent. */
const useConnect = (onDone) => {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [ok, setOk] = useState("");
  const run = async (fields) => {
    setBusy(true); setErr(""); setOk("");
    try {
      const { data: list } = await api.get("/api/connectors");
      const existing = (list.data || []).find((c) => c.Type === fields.Type);
      const body = { ...fields, Active: true, ...(existing ? { ConnectorId: existing.ConnectorId } : { Name: fields.Name || fields.Type }) };
      const { data } = await api.post("/api/connectors", body);
      const { data: t } = await api.post(`/api/connectors/${data.connectorId}/test`, {});
      if (t.ok) { setOk(t.detail || "connected"); await onDone(); }
      else setErr(t.detail || t.error || "it saved, but the test call failed");
    } catch (e) {
      setErr(e?.response?.data?.detail || e?.message || "that did not work");
    }
    setBusy(false);
  };
  return { run, busy, err, ok };
};

const OwnerForm = ({ onDone }) => {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  useEffect(() => {
    api.get("/api/owner").then(({ data }) => {
      if (data.owner && data.owner !== "the owner") setName(data.owner);
      if (data.owner_email) setEmail(data.owner_email);
    }).catch(() => {});
  }, []);
  const save = async () => {
    setBusy(true); setErr("");
    try { await api.put("/api/owner", { name: name.trim(), email: email.trim() || null }); await onDone(); }
    catch (e) { setErr(e?.response?.data?.detail || "could not save that"); }
    setBusy(false);
  };
  return (
    <Box sx={{ display: "flex", gap: 1, mt: 1, flexWrap: "wrap" }}>
      <Field label="Your name" value={name} onChange={(e) => setName(e.target.value)} sx={{ bgcolor: "#fff", flex: 1, minWidth: 160 }} />
      <Field label="Email" value={email} onChange={(e) => setEmail(e.target.value)} sx={{ bgcolor: "#fff", flex: 1, minWidth: 160 }} />
      <Button variant="contained" disableElevation size="small" disabled={busy || !name.trim()} onClick={save}>
        {busy ? "…" : "Save"}
      </Button>
      {err && <Alert severity="error" sx={{ width: "100%", fontSize: 12.5 }}>{err}</Alert>}
    </Box>
  );
};

/* Add a CLI agent and prove it runs, in one button. `asBrain` also points triage at it.
   The test is a real one-line run through the CLI, which is the only thing that distinguishes
   "installed" from "works": a headless agent missing its permission flag looks fine and then
   hangs forever on an approval nobody can click. */
const CliPicker = ({ asBrain, onDone }) => {
  const [list, setList] = useState(null);
  const [busy, setBusy] = useState("");
  const [msg, setMsg] = useState(null);
  useEffect(() => {
    api.get("/api/cli/detect").then(({ data }) => setList(data.data || [])).catch(() => setList([]));
  }, []);
  const use = async (cli) => {
    setBusy(cli.name); setMsg(null);
    try {
      if (cli.cmd) await api.put(`/api/agents/${encodeURIComponent(cli.name)}`,
        { cmd: cli.cmd, args: cli.args, ...(cli.resume_args ? { resume_args: cli.resume_args } : {}), timeout: cli.timeout || 1500 });
      const { data } = await api.post(`/api/agents/${encodeURIComponent(cli.name)}/test`, {});
      if (!data.ok) { setMsg({ bad: true, text: data.error || "the CLI did not answer" }); setBusy(""); return; }
      if (asBrain) await api.patch("/api/settings", { name: "triage_ai", value: `cli:${cli.name}` });
      setMsg({ text: `${cli.label} answered — ${asBrain ? "it is your triage brain now" : "ready for coding tasks"}` });
      await onDone();
    } catch (e) {
      setMsg({ bad: true, text: e?.response?.data?.detail || e?.message || "that did not work" });
    }
    setBusy("");
  };
  if (list === null) return <Typography variant="caption" sx={{ color: FAINT }}>looking for CLIs on your PATH…</Typography>;
  return (
    <Box>
      {list.length === 0 ? (
        <Typography variant="caption" sx={{ color: FAINT }}>
          No AI CLI found on your PATH. Claude Code, Codex, and Gemini CLI are detected automatically once installed.
        </Typography>
      ) : list.map((cli) => (
        <Box key={cli.name} sx={{ display: "flex", alignItems: "center", gap: 1, py: 0.5 }}>
          <Box sx={{ flex: 1, minWidth: 0 }}>
            <Typography sx={{ fontSize: 12.5, fontWeight: 700, color: INK }}>
              {cli.label}{cli.profile && cli.profile !== cli.label ? <Typography component="span" variant="caption" sx={{ color: FAINT, ml: 0.75 }}>profile “{cli.profile}”</Typography> : null}
            </Typography>
            <Typography variant="caption" sx={{ color: cli.configured && !cli.installed ? "#8a3646" : FAINT, wordBreak: "break-all" }}>
              {cli.path ? cli.path
                : cli.configured ? `configured here${cli.cmd ? ` as “${cli.cmd}”` : ""}, but not found on this machine — install it, or fix the command in Connections → AI CLI agents`
                : cli.cmd}
            </Typography>
            {/* found, runnable by hand, and still refused from a background process - so it is
                said here rather than at 6am as "Access is denied." */}
            {cli.store && (
              <Typography variant="caption" sx={{ color: "#8a3646", display: "block", fontWeight: 600 }}>
                This is the Microsoft Store copy. Taskuary cannot start it in the background
                (“Access is denied.”) — install the ordinary build from the vendor and it will be picked up here.
              </Typography>
            )}
          </Box>
          <Button size="small" variant="outlined" disabled={!!busy} onClick={() => use(cli)}
            sx={{ fontSize: 11.5, whiteSpace: "nowrap" }}>
            {busy === cli.name ? "testing…" : asBrain ? "Use & test" : "Add & test"}
          </Button>
        </Box>
      ))}
      {msg && <Alert severity={msg.bad ? "error" : "success"} sx={{ mt: 1, fontSize: 12.5 }}>{msg.text}</Alert>}
    </Box>
  );
};

const AgentForm = ({ onDone }) => (
  <Box sx={{ mt: 1 }}>
    <CliPicker onDone={onDone} />
  </Box>
);

const BrainForm = ({ onDone, onGo }) => {
  const [type, setType] = useState("anthropic");
  const [key, setKey] = useState("");
  const { run, busy, err, ok } = useConnect(onDone);
  const brain = BRAINS.find((b) => b.type === type);
  return (
    <Box sx={{ mt: 1 }}>
      {/* the CLI first: most people arriving here already pay for one and have no separate key,
          and asking them for a key they do not have was the wrong first question */}
      <Typography variant="caption" sx={{ color: DIM, fontWeight: 700, display: "block", mb: 0.5 }}>
        Use a coding CLI you already have
      </Typography>
      <CliPicker asBrain onDone={onDone} />
      <Typography variant="caption" sx={{ color: FAINT, display: "block", mt: 1.5, mb: 0.5, fontWeight: 700 }}>
        …or paste an API key
      </Typography>
      <Box sx={{ display: "flex", gap: 0.75, flexWrap: "wrap", mb: 1 }}>
        {BRAINS.map((b) => (
          <Chip key={b.type} label={b.label} size="small" onClick={() => setType(b.type)}
            sx={{ fontSize: 11.5, fontWeight: 600, cursor: "pointer",
              bgcolor: type === b.type ? "#eae4d8" : "transparent",
              color: type === b.type ? "#55697a" : DIM, border: `1px solid ${type === b.type ? "#d8cfbe" : BORDER}` }} />
        ))}
      </Box>
      <Box sx={{ display: "flex", gap: 1, flexWrap: "wrap" }}>
        <Field label={`${brain.label} API key`} placeholder={brain.ph} type="password" value={key}
          onChange={(e) => setKey(e.target.value)} helperText={brain.hint}
          sx={{ bgcolor: "#fff", flex: 1, minWidth: 220 }} />
        <Button variant="contained" disableElevation size="small" sx={{ height: 40 }}
          disabled={busy || !key.trim()} onClick={() => run({ Type: type, Name: brain.label, Secret: key.trim() })}>
          {busy ? "testing…" : "Connect"}
        </Button>
      </Box>
      {ok && <Alert severity="success" sx={{ mt: 1, fontSize: 12.5 }}>{ok}</Alert>}
      {err && <Alert severity="error" sx={{ mt: 1, fontSize: 12.5 }}>{err}</Alert>}
      <Typography variant="caption" sx={{ color: FAINT, display: "block", mt: 1 }}>
        Running a local model, or on Azure OpenAI?{" "}
        <Box component="span" sx={{ color: "#55697a", cursor: "pointer" }} onClick={() => onGo("Connections")}>
          Set those up on the Connections tab
        </Box>{" "}— they need a model name or an endpoint, not just a key.
      </Typography>
    </Box>
  );
};

const MailboxForm = ({ onDone, onGo }) => {
  const [type, setType] = useState("gmail");
  const [f, setF] = useState({ address: "", password: "", imap_host: "" });
  const { run, busy, err, ok } = useConnect(onDone);
  const box = BOXES.find((b) => b.type === type);
  const ready = f.address.trim() && f.password.trim() && (type === "gmail" || f.imap_host.trim());
  const go = () => run({
    Type: type, Name: box.label, Secret: f.password.trim(),
    ConfigJson: JSON.stringify(type === "gmail"
      ? { address: f.address.trim() }
      : { address: f.address.trim(), imap_host: f.imap_host.trim() }),
  });
  return (
    <Box sx={{ mt: 1 }}>
      <Box sx={{ display: "flex", gap: 0.75, flexWrap: "wrap", mb: 1 }}>
        {BOXES.map((b) => (
          <Chip key={b.type} label={b.label} size="small" onClick={() => setType(b.type)}
            sx={{ fontSize: 11.5, fontWeight: 600, cursor: "pointer",
              bgcolor: type === b.type ? "#eae4d8" : "transparent",
              color: type === b.type ? "#55697a" : DIM, border: `1px solid ${type === b.type ? "#d8cfbe" : BORDER}` }} />
        ))}
      </Box>
      <Box sx={{ display: "flex", gap: 1, flexWrap: "wrap" }}>
        {type === "imap" && (
          <Field label="IMAP host" placeholder="imap.yourdomain.com" value={f.imap_host}
            onChange={(e) => setF({ ...f, imap_host: e.target.value })} sx={{ bgcolor: "#fff", flex: 1, minWidth: 170 }} />
        )}
        <Field label="Mailbox address" placeholder="you@example.com" value={f.address}
          onChange={(e) => setF({ ...f, address: e.target.value })} sx={{ bgcolor: "#fff", flex: 1, minWidth: 170 }} />
        <Field label="Password" type="password" value={f.password}
          onChange={(e) => setF({ ...f, password: e.target.value })} sx={{ bgcolor: "#fff", flex: 1, minWidth: 150 }} />
        <Button variant="contained" disableElevation size="small" sx={{ height: 40 }}
          disabled={busy || !ready} onClick={go}>{busy ? "testing…" : "Connect"}</Button>
      </Box>
      <Typography variant="caption" sx={{ color: FAINT, display: "block", mt: 0.75 }}>{box.hint}</Typography>
      {ok && <Alert severity="success" sx={{ mt: 1, fontSize: 12.5 }}>{ok}</Alert>}
      {err && <Alert severity="error" sx={{ mt: 1, fontSize: 12.5 }}>{err}</Alert>}
      <Typography variant="caption" sx={{ color: FAINT, display: "block", mt: 1 }}>
        Outlook, Teams, Slack, GitHub and the trackers need an app registration or a bot token —{" "}
        <Box component="span" sx={{ color: "#55697a", cursor: "pointer" }} onClick={() => onGo("Connections")}>
          their cards walk you through it
        </Box>.
      </Typography>
    </Box>
  );
};

const SyncForm = ({ onDone }) => {
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const run = async () => {
    setBusy(true); setMsg("Reading your mailboxes…");
    try {
      await api.post("/api/ingest/poll", {});
      // the poll runs in the background, so watch its own status rather than guessing at a wait
      for (let i = 0; i < 90; i++) {
        await new Promise((r) => setTimeout(r, 2000));
        const { data } = await api.get("/api/ingest/status");
        if (data.status?.state !== "running") break;
        setMsg(data.status.what || "Reading…");
      }
      await onDone();
      setMsg("");
    } catch { setMsg("the sync could not be started — check the Connections tab"); }
    setBusy(false);
  };
  return (
    <Box sx={{ mt: 1 }}>
      <Button variant="contained" disableElevation size="small" disabled={busy} onClick={run}>
        {busy ? "syncing…" : "Sync now"}
      </Button>
      {msg && <Typography variant="caption" sx={{ color: DIM, display: "block", mt: 0.75 }}>{msg}</Typography>}
    </Box>
  );
};

const HISTORY = {
  style: {
    button: "Generate my reply style",
    working: "Reading messages you sent…",
    note: "This writes only inside STYLE.md's generated section. Anything you add yourself stays untouched when you regenerate.",
  },
  triage: {
    button: "Learn my triage habits",
    working: "Comparing what you answered and skipped…",
    note: "This writes only inside TRIAGE.md's generated section. You can inspect and edit every conclusion afterward.",
  },
};

/* The Docs page already owns the safe history generators. Onboarding gives them the missing
   sequence and context: sync first, then one click for writing voice and one for attention. */
const HistoryForm = ({ name, onDone, onGo }) => {
  const [busy, setBusy] = useState(false);
  const [what, setWhat] = useState("");
  const [msg, setMsg] = useState(null);
  const copy = HISTORY[name];
  useEffect(() => {
    if (!busy) return undefined;
    const t = setInterval(async () => {
      try { setWhat((await api.get("/api/doc/generate/status")).data.what || ""); }
      catch { /* progress is a nicety; the generate call remains authoritative */ }
    }, 1200);
    return () => clearInterval(t);
  }, [busy]);
  const generate = async () => {
    setBusy(true); setWhat(copy.working); setMsg(null);
    try {
      const { data } = await api.post(`/api/doc/${name}/generate`);
      setMsg({ text: data.detail || "Generated from your history." });
      await onDone();
    } catch (e) {
      setMsg({ bad: true, text: e?.response?.data?.detail || "Could not generate from history." });
    }
    setBusy(false); setWhat("");
  };
  return (
    <Box sx={{ mt: 1 }}>
      <Button variant="contained" disableElevation size="small" disabled={busy} onClick={generate}
        startIcon={busy ? <CircularProgress size={12} sx={{ color: "#fff" }} /> : null}>
        {busy ? (what || copy.working) : copy.button}
      </Button>
      <Typography variant="caption" sx={{ color: FAINT, display: "block", mt: 0.75, lineHeight: 1.5 }}>
        {copy.note}{" "}
        <Box component="span" onClick={() => onGo("Docs")} sx={{ color: "#55697a", cursor: "pointer" }}>
          Open Docs
        </Box>
      </Typography>
      {msg && <Alert severity={msg.bad ? "error" : "success"} sx={{ mt: 1, fontSize: 12.5 }}>{msg.text}</Alert>}
    </Box>
  );
};

const StyleForm = (props) => <HistoryForm name="style" {...props} />;
const TriageForm = (props) => <HistoryForm name="triage" {...props} />;
const SoulForm = ({ onDone, onGo }) => {
  const [open, setOpen] = useState(false);
  return (
    <Box sx={{ mt: 1 }}>
      <Button variant="contained" disableElevation size="small" onClick={() => setOpen(true)}>
        Answer seven questions
      </Button>
      <Typography variant="caption" sx={{ color: FAINT, display: "block", mt: 0.75, lineHeight: 1.5 }}>
        Your current SOUL.md remains in force until the new version is written. You can inspect and edit the result in{" "}
        <Box component="span" onClick={() => onGo("Docs")} sx={{ color: "#55697a", cursor: "pointer" }}>
          Docs
        </Box>.
      </Typography>
      <SoulInterview open={open} onClose={() => setOpen(false)} onWritten={() => onDone()} />
    </Box>
  );
};
const FORMS = { owner: OwnerForm, ai: BrainForm, inbound: MailboxForm, sync: SyncForm,
  soul: SoulForm, style: StyleForm, triage: TriageForm, agent: AgentForm };

/* A done step collapses to ONE line. Its reason mattered while you were deciding whether to do
   it; afterwards it is six lines of history pushing the thing you are actually working on below
   the fold. Only the open step carries its full text, and only one is ever open - so the panel
   is the size of the work left rather than the size of the whole list. */
const Step = ({ s, n, open, onOpen, onGo, onDone }) => {
  const Form = FORMS[s.key];
  const active = open && !s.done;
  return (
    <Box sx={{ borderTop: n ? `1px solid ${BORDER}` : "none",
      // the open step is lifted out of the list rather than merely indented
      bgcolor: active ? "#fff" : "transparent",
      boxShadow: active ? "inset 3px 0 0 #55697a" : "none",
      px: active ? 1.5 : 0, py: s.done ? 1 : 1.5,
      transition: "background-color .15s" }}>
      <Box sx={{ display: "flex", gap: 1.5, alignItems: s.done ? "center" : "flex-start" }}>
        <Box sx={{ pt: s.done ? 0 : 0.25, display: "flex" }}>
          {s.done
            ? <CheckCircleIcon sx={{ fontSize: 18, color: "#47654a" }} />
            : <RadioButtonUncheckedIcon sx={{ fontSize: 20, color: s.optional ? "#cfc9bf" : "#55697a" }} />}
        </Box>
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Box sx={{ display: "flex", alignItems: "baseline", gap: 1, flexWrap: "wrap" }}>
            <Typography sx={{ fontWeight: s.done ? 600 : 700, fontSize: s.done ? 12.5 : 13.5,
              color: s.done ? DIM : INK }}>{s.title}</Typography>
            {s.optional && !s.done && (
              <Typography variant="caption" sx={{ color: FAINT }}>{s.recommended ? "recommended" : "optional"}</Typography>
            )}
            {s.done && s.detail && (
              <Typography variant="caption" sx={{ color: "#47654a", fontWeight: 600 }}>{s.detail}</Typography>
            )}
          </Box>
          {/* WHY before HOW, while it is still a decision */}
          {!s.done && (
            <Typography variant="caption" sx={{ color: DIM, display: "block", mt: 0.25, lineHeight: 1.55 }}>
              {s.why}
            </Typography>
          )}
          {active && Form && <Form onDone={onDone} onGo={onGo} />}
        </Box>
        {!s.done && !open && Form && (
          <Button size="small" variant="outlined" onClick={onOpen}
            sx={{ alignSelf: "center", whiteSpace: "nowrap", fontSize: 12 }}>
            {s.key === "sync" ? "Sync" : s.key === "soul" ? "Personalize"
              : ["style", "triage"].includes(s.key) ? "Generate" : "Set up"}
          </Button>
        )}
        {!s.done && !Form && (
          <Button size="small" endIcon={<OpenInNewIcon sx={{ fontSize: 13 }} />} onClick={() => onGo(s.where)}
            sx={{ alignSelf: "center", whiteSpace: "nowrap", fontSize: 12 }}>{s.where}</Button>
        )}
        {/* a finished step can still be reopened - "done" is not "never again" */}
        {s.done && Form && !open && (
          <Typography variant="caption" onClick={onOpen}
            sx={{ color: FAINT, cursor: "pointer", whiteSpace: "nowrap", "&:hover": { color: "#55697a" } }}>
            change
          </Typography>
        )}
        {s.done && open && Form && <Box sx={{ width: "100%" }}><Form onDone={onDone} onGo={onGo} /></Box>}
      </Box>
    </Box>
  );
};

/* What actually happens once it is connected. Somebody who has just pasted a key has no model of
   the funnel yet, and "you're all set" tells them nothing about where to look next. */
const NextSteps = ({ onGo }) => (
  <Box sx={{ mt: 2, p: 1.5, bgcolor: "#f2f7f4", border: "1px solid #cfe6d9", borderRadius: 1.5 }}>
    <Typography sx={{ fontWeight: 700, fontSize: 13, color: "#47654a", mb: 0.75 }}>What happens now</Typography>
    {[
      ["Timeline", "Every message lands here as it arrives, with the verdict triage gave it and why."],
      ["Review", "Questions get a reply drafted in your voice. Nothing sends until you approve it."],
      ["Board", "Real work becomes a task. Coding tasks can go to your CLI agent; the rest waits on your list."],
      ["Docs", "SOUL.md is the funnel's constitution — what counts as a task, how you answer. Edit it and triage changes."],
    ].map(([tab, text]) => (
      <Box key={tab} sx={{ display: "flex", gap: 1, mb: 0.5 }}>
        <Box component="span" onClick={() => onGo(tab)}
          sx={{ fontWeight: 700, fontSize: 12, color: "#55697a", cursor: "pointer", minWidth: 62 }}>{tab}</Box>
        <Typography variant="caption" sx={{ color: DIM, flex: 1, lineHeight: 1.5 }}>{text}</Typography>
      </Box>
    ))}
    <Typography variant="caption" sx={{ color: FAINT, display: "block", mt: 0.75 }}>
      Say “Not our task” on anything that is not yours and triage remembers it — that is how it learns your job.
    </Typography>
  </Box>
);

export const SetupPanel = ({ open, state, onClose, onGo, onDismiss, onRefresh }) => {
  const [openKey, setOpenKey] = useState(null);
  const steps = state?.steps || [];
  // the first thing left to do is already open: a wizard whose every step needs a click first is
  // a list of buttons
  useEffect(() => {
    if (!open || !steps.length) return;
    if (state.complete) { setOpenKey(null); return; }
    // whatever is left, in order - so a completed step advances to the next one by itself
    // A genuinely optional extra such as the coding agent never springs open after the guided
    // path is complete; it remains one explicit Set up click for people who want it.
    setOpenKey((k) => k || (steps.find((s) => !s.done && FORMS[s.key]
      && (!s.optional || s.recommended)) || {}).key || null);
  }, [open, steps, state?.complete]);
  if (!state) return null;
  const guideTotal = state.guide_total ?? state.total;
  const guideDone = state.guide_done ?? state.done;
  const guideLeft = guideTotal - guideDone;
  // finishing hands you the next thing to do: closing to nothing makes you hunt for the button
  // you were always going to press
  const done = async () => { setOpenKey(null); await onRefresh(); };
  return (
    <Dialog open={!!open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogContent sx={{ p: 3 }}>
        <Box sx={{ display: "flex", alignItems: "flex-start", gap: 1 }}>
          <Box sx={{ flex: 1 }}>
            <Typography sx={{ fontWeight: 800, fontSize: 17, color: INK }}>
              {state.complete ? "Taskuary is ready for you"
                : state.ready ? "The essentials work — make it yours"
                  : `${spell(guideTotal)} steps and Taskuary is yours`}
            </Typography>
            <Typography variant="body2" sx={{ color: DIM, mt: 0.5 }}>
              {state.complete
                ? "Connections and personalization are complete. It will keep learning from your verdicts."
                : state.ready
                  ? `${guideLeft} recommended ${guideLeft === 1 ? "step" : "steps"} left to personalize Taskuary. They use your answers or your own history, and remain editable.`
                : `${guideDone} of ${guideTotal} done${guideLeft ? ` — ${guideLeft} to go` : ""}. `
                  + `The first ${state.total} are what make the funnel work at all: without them the `
                  + "Timeline stays empty and looks like a quiet day."}
            </Typography>
          </Box>
          <CloseIcon onClick={onClose} sx={{ fontSize: 18, color: FAINT, cursor: "pointer", mt: 0.5 }} />
        </Box>

        <Box sx={{ mt: 2, bgcolor: PANEL2, border: `1px solid ${BORDER}`, borderRadius: 1.5, px: 2 }}>
          {steps.map((s, i) => (
            <Step key={s.key} s={s} n={i} open={openKey === s.key} onOpen={() => setOpenKey(s.key)}
              onGo={onGo} onDone={done} />
          ))}
        </Box>

        {state.complete && <NextSteps onGo={onGo} />}

        <Box sx={{ display: "flex", alignItems: "center", gap: 1, mt: 2 }}>
          <Typography variant="caption" sx={{ color: FAINT, flex: 1 }}>
            {state.dismissed
              ? "Put away — the quiet counter in the top bar brings it back."
              : state.complete
                ? "Revisit any of these choices later from Connections, Docs, or Settings."
              : state.ready && !state.complete
                ? "These are recommendations, not gates. Finish later and the counter keeps your place."
                : "Not now? Put it away; the counter in the top bar brings it back."}
          </Typography>
          {!state.complete && (
            <Button size="small" sx={{ color: DIM, fontSize: 12 }} onClick={() => onDismiss(!state.dismissed)}>
              {state.dismissed ? "Show it again" : state.ready ? "Finish later" : "Put it away"}
            </Button>
          )}
          <Button size="small" variant="contained" disableElevation onClick={onClose} sx={{ fontSize: 12 }}>
            {state.complete ? "Done" : "Close"}
          </Button>
        </Box>
      </DialogContent>
    </Dialog>
  );
};
