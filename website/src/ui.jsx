// Shared Task Hub atoms: chips, channel icons, relative time. Light + compact.
import React, { useEffect, useState } from "react";
import { Box, Button, Chip, CircularProgress, MenuItem, Select, TextField, Tooltip, Typography } from "@mui/material";
import SmartToyIcon from "@mui/icons-material/SmartToy";
import api from "./api";
import MailOutlineIcon from "@mui/icons-material/MailOutline";
import GroupsIcon from "@mui/icons-material/Groups";
import GitHubIcon from "@mui/icons-material/GitHub";
import AssessmentIcon from "@mui/icons-material/Assessment";
import TerminalIcon from "@mui/icons-material/Terminal";
import TagIcon from "@mui/icons-material/Tag";
import AutoAwesomeIcon from "@mui/icons-material/AutoAwesome";
import { ACTION_COLORS, TASK_STATUS_COLORS, mono, DIM, FAINT, ACCENT2, PANEL2 } from "./theme.jsx";

// Brand colors so a glance says where a message came from: Teams purple, Outlook blue,
// teal for scheduled reports.
export const CHANNEL_COLORS = { teams: "#6264A7", email: "#0F6CBD", github: "#1c2536", report: "#0e7490", slack: "#611f69", ai: "#b45309" };
export const ChannelIcon = ({ channel, sx }) => {
  const Icon = channel === "teams" ? GroupsIcon : channel === "github" ? GitHubIcon
    : channel === "report" ? AssessmentIcon : channel === "email" ? MailOutlineIcon
    : channel === "slack" ? TagIcon : channel === "ai" ? AutoAwesomeIcon : TerminalIcon;
  return <Icon sx={{ fontSize: 15, color: CHANNEL_COLORS[channel] || "#98a1b3", ...sx }} />;
};

export const RefChip = ({ taskId, onClick }) => taskId ? (
  <Chip size="small" label={`TQ-${String(taskId).padStart(4, "0")}`} onClick={onClick}
    sx={{ ...mono, bgcolor: "#eef0ff", color: "#4f46e5", height: 19, fontSize: 10.5 }} />
) : null;

export const ActionChip = ({ action, reviewStatus, taskStatus }) => {
  // A finished task outranks everything else the chip could say.
  if (taskStatus === "done" && reviewStatus !== "pending") {
    return <Chip size="small" label="completed" sx={{ bgcolor: "#e8f6ee", color: "#15803d", height: 19, fontSize: 10.5, fontWeight: 700 }} />;
  }
  // What actually matters to the reader: current state, not just the original verdict.
  const key = reviewStatus === "auto" ? "auto"
    : reviewStatus === "pending" ? (action === "escalate" ? "escalate" : "draft")
      : action || "task_only";
  const c = ACTION_COLORS[key] || ACTION_COLORS.task_only;
  const decided = reviewStatus && !["pending", "auto"].includes(reviewStatus);
  const label = !decided ? c.label : reviewStatus === "no_reply" ? "no reply needed" : `reviewed · ${reviewStatus}`;
  return <Chip size="small" label={label}
    sx={{ bgcolor: decided ? (reviewStatus === "no_reply" ? "#eef0f3" : "#e8f6ee") : c.bg,
      color: decided ? (reviewStatus === "no_reply" ? "#8a94a6" : "#15803d") : c.fg, height: 19, fontSize: 10.5 }} />;
};

export const StatusDot = ({ ok, warn }) => (
  <Box component="span" sx={{ display: "inline-block", width: 8, height: 8, borderRadius: "50%", mr: 1,
    bgcolor: ok ? "#22c55e" : warn ? "#f59e0b" : "#cbd2dd" }} />
);

// Expandable "prompt sent to agent" block inside a run trace - collapsed by default.
export const PromptBlock = ({ text }) => (
  <Box component="details" sx={{ my: 0.5 }}>
    <Box component="summary" sx={{ ...mono, cursor: "pointer", color: ACCENT2, fontSize: 10.5 }}>
      ▸ prompt sent to agent · {(text || "").length.toLocaleString()} chars — click to expand
    </Box>
    <Box component="pre" sx={{ ...mono, whiteSpace: "pre-wrap", bgcolor: PANEL2, borderRadius: 1.5,
      p: 1, mt: 0.5, fontSize: 10.5, lineHeight: 1.45, maxHeight: 320, overflow: "auto", color: DIM }}>
      {text}
    </Box>
  </Box>
);

// The live agent console: a run's trace rendered like a terminal. Contiguous 'live'
// events (streamed CLI output - tool calls, text) group into one dark scroll box that
// follows the tail while the run is going; prompts stay collapsible; everything else
// stays a one-line caption.
export const RunTrace = ({ traceJson, running }) => {
  let evs = [];
  try { evs = JSON.parse(traceJson || "[]"); } catch { /* mid-write JSON: next poll fixes it */ }
  const boxRef = React.useRef(null);
  React.useEffect(() => { if (running && boxRef.current) boxRef.current.scrollTop = boxRef.current.scrollHeight; });
  const groups = [];
  evs.forEach((ev) => {
    const last = groups[groups.length - 1];
    if (ev.kind === "live" && last?.kind === "live") last.items.push(ev);
    else groups.push(ev.kind === "live" ? { kind: "live", items: [ev] } : { kind: ev.kind, ev });
  });
  return groups.map((g, i) => {
    const tail = i === groups.length - 1;
    if (g.kind === "live") return (
      <Box key={i} ref={tail ? boxRef : null} sx={{ bgcolor: "#0f172a", borderRadius: 1.5, px: 1.25, py: 0.75,
        my: 0.5, maxHeight: 280, overflowY: "auto", border: "1px solid #1e293b" }}>
        {g.items.map((ev, k) => (
          <Typography key={k} variant="caption" sx={{ ...mono, display: "block", fontSize: 10.5, lineHeight: 1.6,
            whiteSpace: "pre-wrap", wordBreak: "break-word",
            color: ev.detail.startsWith("→") ? "#a5b4fc" : ev.detail.startsWith("✗") ? "#fca5a5" : "#94a3b8" }}>
            <span style={{ color: "#475569" }}>{(ev.at || "").slice(11)}</span> {ev.detail}
          </Typography>
        ))}
        {running && tail && (
          <Typography variant="caption" sx={{ ...mono, color: "#22d3ee", fontSize: 10.5,
            "@keyframes tqBlink": { "50%": { opacity: 0.25 } }, animation: "tqBlink 1.1s step-end infinite" }}>
            ▮ agent working…
          </Typography>
        )}
      </Box>
    );
    if (g.kind === "prompt") return <PromptBlock key={i} text={g.ev.detail} />;
    return (
      <Typography key={i} variant="caption" sx={{ ...mono, display: "block", color: FAINT, fontSize: 10.5 }}>
        {(g.ev.at || "").slice(11)} [{g.ev.kind}] {g.ev.name}: {(g.ev.detail || "").slice(0, 120)}
      </Typography>
    );
  });
};

// Unified-diff viewer: green adds, red removes, purple hunks, bold file headers.
export const DiffBlock = ({ text }) => {
  if (!text) return null;
  const lines = String(text).split("\n");
  const style = (l) => l.startsWith("+++") || l.startsWith("---") || l.startsWith("diff --git")
    ? { color: "#1c2536", fontWeight: 700, bgcolor: "#eef0f3" }
    : l.startsWith("@@") ? { color: "#7e22ce", bgcolor: "#f5f3ff" }
      : l.startsWith("+") ? { color: "#15803d", bgcolor: "#e8f6ee" }
        : l.startsWith("-") ? { color: "#b91c1c", bgcolor: "#fdecec" }
          : { color: "#697386" };
  return (
    <Box sx={{ border: "1px solid #e5e8ee", borderRadius: 1.5, overflow: "auto", maxHeight: 360, bgcolor: "#fff" }}>
      {lines.map((l, i) => (
        <Box key={i} component="pre" sx={{ ...mono, m: 0, px: 1.25, py: 0.1, fontSize: 11,
          lineHeight: 1.5, whiteSpace: "pre-wrap", wordBreak: "break-all", ...style(l) }}>
          {l || " "}
        </Box>
      ))}
    </Box>
  );
};

// The coder's report, parsed into labeled sections instead of a wall of text.
const REPORT_COLORS = { Triage: "#0e7490", Determination: "#7e22ce", Actions: "#b45309", Summary: "#15803d" };
export const CoderReport = ({ body }) => {
  const parts = String(body || "").replace(/^CODER REPORT\n?/, "").split(/(?:^|\n)(Triage|Determination|Actions|Summary):\s*/);
  const sections = [];
  for (let i = 1; i < parts.length; i += 2) {
    const text = (parts[i + 1] || "").trim();
    if (text) sections.push({ label: parts[i], text });
  }
  if (!sections.length) {
    return <Typography variant="body2" sx={{ whiteSpace: "pre-wrap", color: "#1c2536" }}>{body}</Typography>;
  }
  return (
    <Box>
      {sections.map((s, i) => (
        <Box key={s.label} sx={{ display: "flex", gap: 1.25, py: 0.9,
          borderTop: i ? "1px solid #e9ddfb" : "none" }}>
          <Typography variant="caption" sx={{ ...mono, color: REPORT_COLORS[s.label], fontWeight: 700,
            fontSize: 9.5, letterSpacing: 1, textTransform: "uppercase", width: 96, flexShrink: 0, pt: 0.25 }}>
            {s.label}
          </Typography>
          <Typography variant="body2" sx={{ color: "#1c2536", lineHeight: 1.55, whiteSpace: "pre-wrap", minWidth: 0 }}>
            {s.text}
          </Typography>
        </Box>
      ))}
    </Box>
  );
};

// WHO does the work and on WHICH model. One control, used by every run surface (Board
// dialog, task header, send-to-agent) so the choice reads the same everywhere. The agent
// list comes from your configured CLIs; the model list from that CLI's known models plus
// whatever the profile sets as its default.
export const useAgents = () => {
  const [agents, setAgents] = useState([]);
  const [models, setModels] = useState({});
  useEffect(() => {
    api.get("/api/agents").then(({ data }) => {
      setAgents((data.data || []).map((a) => a.Name));
      setModels(data.models || {});
    }).catch(() => {});
  }, []);
  return { agents, models };
};

export const AgentPicker = ({ agents, models, agent, model, onAgent, onModel, size = 30 }) => {
  const info = models[agent] || {};
  const choices = info.choices || [];
  return (
    <>
      <Select size="small" value={agents.includes(agent) ? agent : (agents[0] || agent)}
        onChange={(e) => onAgent(e.target.value)}
        sx={{ fontSize: 12.5, height: size, bgcolor: "#fff", minWidth: 120 }}>
        {(agents.length ? agents : [agent]).map((a) => (
          <MenuItem key={a} value={a} sx={{ fontSize: 12.5 }}>
            {a}{models[a]?.cmd ? ` · ${models[a].cmd}` : ""}
          </MenuItem>
        ))}
      </Select>
      <Select size="small" displayEmpty value={model || ""} onChange={(e) => onModel(e.target.value)}
        sx={{ fontSize: 12.5, height: size, bgcolor: "#fff", minWidth: 150 }}>
        <MenuItem value="" sx={{ fontSize: 12.5 }}>
          {info.default ? `default · ${info.default}` : "the agent's default model"}
        </MenuItem>
        {choices.map((m) => <MenuItem key={m} value={m} sx={{ fontSize: 12.5 }}>{m}</MenuItem>)}
      </Select>
    </>
  );
};

// Hand ANY timeline item to a coding agent: your prompt + the item's context (subject,
// sender, full body, thread, the operator docs) go down together. Items that aren't a
// task yet become one server-side, so the run has somewhere to live and stream into.
export const SendToAgent = ({ messageId, subject, onOpenTask, dense }) => {
  const [open, setOpen] = useState(false);
  const { agents, models } = useAgents();
  const [agent, setAgent] = useState("coder");
  const [model, setModel] = useState("");
  const [prompt, setPrompt] = useState("");
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState(null);
  const [err, setErr] = useState("");
  useEffect(() => { if (agents.length && !agents.includes(agent)) setAgent(agents[0]); }, [agents, agent]);
  const send = async () => {
    setBusy(true); setErr("");
    try {
      const { data } = await api.post(`/api/messages/${messageId}/dispatch`,
        { agent, model: model || null, instruction: prompt.trim() || null });
      setSent(data); setPrompt("");
    } catch (e) { setErr(e?.response?.data?.detail || "Could not reach the agent"); }
    setBusy(false);
  };
  if (sent) return (
    <Box sx={{ display: "flex", alignItems: "center", gap: 1, mt: dense ? 0.5 : 1 }}>
      <SmartToyIcon sx={{ fontSize: 15, color: "#15803d" }} />
      <Typography variant="caption" sx={{ color: "#15803d", fontWeight: 600 }}>
        {sent.agent} is on it — {sent.ref}
      </Typography>
      <Button size="small" sx={{ fontSize: 11 }} onClick={() => onOpenTask?.(sent.taskId)}>watch it live →</Button>
      <Button size="small" sx={{ fontSize: 11, color: DIM }} onClick={() => setSent(null)}>send another</Button>
    </Box>
  );
  if (!open) return (
    <Button size="small" startIcon={<SmartToyIcon sx={{ fontSize: 14 }} />} onClick={() => setOpen(true)}
      sx={{ fontSize: 11.5, color: "#7e22ce" }}>Send to coding agent</Button>
  );
  return (
    <Box sx={{ mt: 1, p: 1.25, bgcolor: "#faf8ff", border: "1px solid #e9ddfb", borderRadius: 1.5 }}>
      <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 0.75, flexWrap: "wrap" }}>
        <SmartToyIcon sx={{ fontSize: 15, color: "#7e22ce" }} />
        <Typography variant="caption" sx={{ color: "#7e22ce", fontWeight: 700 }}>Send to an agent</Typography>
        <Box sx={{ flex: 1, minWidth: 8 }} />
        <AgentPicker agents={agents} models={models} agent={agent} model={model}
          onAgent={setAgent} onModel={setModel} size={26} />
      </Box>
      <TextField fullWidth multiline minRows={2} size="small" autoFocus value={prompt}
        onChange={(e) => setPrompt(e.target.value)}
        placeholder={`What should it do? e.g. "Find why this failed and fix it, then tell me what changed."`}
        sx={{ bgcolor: "#fff" }} />
      <Box sx={{ display: "flex", alignItems: "center", gap: 1, mt: 0.75 }}>
        <Typography variant="caption" sx={{ color: FAINT, flex: 1, minWidth: 0 }} noWrap>
          it gets the full message{subject ? ` “${subject}”` : ""} + your operator docs as context
        </Typography>
        <Button size="small" sx={{ fontSize: 11, color: DIM }} onClick={() => setOpen(false)}>cancel</Button>
        <Button size="small" variant="contained" disableElevation disabled={busy} onClick={send}
          startIcon={busy ? <CircularProgress size={11} sx={{ color: "#fff" }} /> : null}
          sx={{ fontSize: 11.5, bgcolor: "#7e22ce", "&:hover": { bgcolor: "#6b1fb0" } }}>
          {busy ? "sending…" : "Send"}
        </Button>
      </Box>
      {err && <Typography variant="caption" sx={{ color: "#b91c1c", display: "block", mt: 0.5 }}>{err}</Typography>}
    </Box>
  );
};

export const TaskStatusChip = ({ status }) => (
  <Chip size="small" label={status} sx={{ bgcolor: "transparent", border: `1px solid ${TASK_STATUS_COLORS[status] || "#98a1b3"}55`,
    color: TASK_STATUS_COLORS[status] || "#98a1b3", height: 19, fontSize: 10.5 }} />
);

export const timeAgo = (s) => {
  if (!s) return "";
  const mins = Math.max(0, (Date.now() - new Date(s.replace(" ", "T"))) / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${Math.round(mins)}m ago`;
  if (mins < 60 * 24) return `${Math.round(mins / 60)}h ago`;
  return `${Math.round(mins / 1440)}d ago`;
};

// Bodies arrive as HTML (email) or oddly-spaced stripped text - make them readable.
export const cleanText = (s) => (s || "").replace(/<(style|script|head)[^>]*>[\s\S]*?<\/\1>/gi, " ")
  .replace(/<[^>]+>/g, " ").replace(/&nbsp;|&#\d+;|&\w+;/g, " ")
  .replace(/[^\S\n]+/g, " ").replace(/ ?\n ?/g, "\n").replace(/\n{3,}/g, "\n\n").trim();

// Mail carries the whole thread quoted underneath the new text. Find where the new part
// ends so the panel can lead with what actually just arrived and fold the history away.
const QUOTE_MARKS = [
  /^\s*-{2,}\s*(original message|forwarded message)\s*-{2,}/im,
  /^\s*from:\s*\S.*$/im,
  /^\s*on .{5,140}\bwrote:\s*$/im,
  /^\s*_{5,}\s*$/m,
  /^\s*>{1,}\s?\S.*$/m,
];
export const splitQuoted = (text) => {
  const t = String(text || "");
  const at = QUOTE_MARKS.map((re) => t.search(re)).filter((i) => i > 0).sort((a, b) => a - b)[0];
  // a body that IS a forward (marker at the very top) stays whole - there's no "new" half
  // to lead with - and a stub of a quote (a truncated tail) isn't worth its own fold
  if (at == null || t.length - at < 40) return { latest: t, quoted: "" };
  return { latest: t.slice(0, at).trim(), quoted: t.slice(at).trim() };
};

// Times are stamped in LOCAL time - parse as-is; a trailing Z still wins when a
// source provides real UTC (Graph does).
const asUtc = (s) => new Date(s.replace(" ", "T"));
export const fmtTime12 = (s) => s ? asUtc(s).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" }) : "";
export const fmtDateTime = (s) => s ? asUtc(s).toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }) : "";
export const localDay = (s) => s ? asUtc(s).toLocaleDateString("sv-SE") : "";   // YYYY-MM-DD in local zone

// ── Stripe-style two-level navigation atoms (Settings/Docs/Connectors share these) ──
export const Crumb = ({ section, onBack, title }) => (
  <Box sx={{ mb: 2.5 }}>
    <Typography variant="caption" onClick={onBack}
      sx={{ color: "#4f46e5", fontWeight: 600, cursor: "pointer", "&:hover": { textDecoration: "underline" } }}>
      {section}
    </Typography>
    <Typography sx={{ color: "#1c2536", fontWeight: 800, fontSize: 20, lineHeight: 1.2, mt: 0.25 }}>{title}</Typography>
  </Box>
);

export const UnderTabs = ({ tabs, value, onChange }) => (
  <Box sx={{ display: "flex", gap: 3, borderBottom: "1px solid #e5e8ee", mb: 2 }}>
    {tabs.map((t) => (
      <Box key={t} onClick={() => onChange(t)}
        sx={{ pb: 1, cursor: "pointer", fontSize: 13, fontWeight: 600, mb: "-1px",
          color: value === t ? "#4f46e5" : DIM,
          borderBottom: `2px solid ${value === t ? "#4f46e5" : "transparent"}`,
          "&:hover": { color: "#1c2536" } }}>
        {t}
      </Box>
    ))}
  </Box>
);

export const LandingCard = ({ icon, title, desc, onOpen }) => (
  <Box onClick={onOpen} sx={{ display: "flex", gap: 1.5, cursor: "pointer", alignItems: "flex-start",
    "&:hover .thubPgTitle": { textDecoration: "underline" } }}>
    <Box sx={{ width: 38, height: 38, borderRadius: 2, bgcolor: "#fff", border: "1px solid #e5e8ee",
      display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0,
      boxShadow: "0 1px 2px rgba(16,24,40,.05)" }}>
      {icon}
    </Box>
    <Box sx={{ minWidth: 0 }}>
      <Typography className="thubPgTitle" sx={{ color: "#4f46e5", fontWeight: 700, fontSize: 14.5, lineHeight: 1.3 }}>{title}</Typography>
      <Typography variant="body2" sx={{ color: DIM, mt: 0.25 }}>{desc}</Typography>
    </Box>
  </Box>
);

export const SectionLabel = ({ children, right }) => (
  <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", mb: 1, mt: 2 }}>
    <Typography variant="overline" sx={{ color: ACCENT2, letterSpacing: 1.5, fontWeight: 700, fontSize: 10 }}>{children}</Typography>
    {right}
  </Box>
);

export const Empty = ({ children }) => (
  <Typography variant="body2" sx={{ color: FAINT, py: 3, textAlign: "center" }}>{children}</Typography>
);

export const scoreBar = (v) => (
  <Tooltip title={v?.toFixed ? v.toFixed(2) : v}>
    <Box sx={{ width: 54, height: 4, bgcolor: PANEL2, border: "1px solid #e5e8ee", borderRadius: 3, overflow: "hidden", display: "inline-block", mr: 1 }}>
      <Box sx={{ width: `${Math.min(100, (v || 0) * 100)}%`, height: "100%", bgcolor: "#4f46e5" }} />
    </Box>
  </Tooltip>
);

// Compact filter pill row used across views.
// Segmented control: one contained housing, obviously interactive; the active segment
// fills with its muted color pair {bg, fg, bd} (indigo default), the rest stay quiet.
export const FilterPills = ({ options, value, onChange }) => (
  <Box sx={{ display: "inline-flex", gap: 0.25, p: 0.4, bgcolor: "#f1f3f6",
    border: "1px solid #e5e8ee", borderRadius: 2.5 }}>
    {options.map((o) => {
      const key = o.key ?? o, on = value === key;
      const c = o.c || { bg: "#eef0ff", fg: "#4f46e5", bd: "#c9cff0" };
      return (
        <Box key={key} onClick={() => onChange(key)}
          sx={{ px: 1.25, py: 0.45, borderRadius: 1.75, cursor: "pointer", fontSize: 11.5,
            fontWeight: on ? 700 : 500, lineHeight: 1.4, userSelect: "none", whiteSpace: "nowrap",
            bgcolor: on ? c.bg : "transparent", color: on ? c.fg : DIM,
            border: `1px solid ${on ? c.bd : "transparent"}`,
            boxShadow: on ? "0 1px 2px rgba(16,24,40,.08)" : "none",
            transition: "all .15s", "&:hover": on ? {} : { bgcolor: "#e9ecf1", color: "#1c2536" } }}>
          {o.label ?? (o || "all")}
        </Box>
      );
    })}
  </Box>
);
