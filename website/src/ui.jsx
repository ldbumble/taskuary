// Shared Task Hub atoms: chips, channel icons, relative time. Light + compact.
import { says } from "./laneSays.js";
import { laneMeta, taskStateMeta } from "./funnelPile.js";
import { AGENT, NOT_SENT, READY } from "./taskLifecycle.js";
import { WORD } from "./lanes.js";
import { ago, agoMins, dur, durSince, plural } from "./timeWords.js";
import React, { useEffect, useRef, useState } from "react";
import { useCapabilities, NO_CODING_TOOL } from "./capabilities.js";
import { bareAddresses } from "./replyDelivery.js";
import { keepAddresses, linkParts } from "./mailLinks.js";
import { Alert, Autocomplete, Box, Button, Chip, CircularProgress, Dialog, DialogActions, DialogContent,
  DialogContentText, DialogTitle, InputAdornment, MenuItem, Select, TextField, Tooltip, Typography } from "@mui/material";
import SearchIcon from "@mui/icons-material/Search";
import BlockIcon from "@mui/icons-material/Block";
import PsychologyOutlinedIcon from "@mui/icons-material/PsychologyOutlined";
import api from "./api";
import { dictate, dictationError } from "./dictation.js";
import { onLive, touches } from "./live.js";
import { outcomeOf } from "./dispatchOutcome.js";
import { RepoPicker } from "./RepoPicker.jsx";
import { Md } from "./md.jsx";
import MailOutlineIcon from "@mui/icons-material/MailOutline";
import GroupsIcon from "@mui/icons-material/Groups";
import AccountTreeOutlinedIcon from "@mui/icons-material/AccountTreeOutlined";
import GitHubIcon from "@mui/icons-material/GitHub";
// the assistant wears TASKUARY's own mark, not a robot head: it is this app talking, and a
// generic bot glyph read as some third party bolted on the side
import PersonOutlineIcon from "@mui/icons-material/PersonOutline";
import AssessmentIcon from "@mui/icons-material/Assessment";
import TerminalIcon from "@mui/icons-material/Terminal";
import TagIcon from "@mui/icons-material/Tag";
import AutoAwesomeIcon from "@mui/icons-material/AutoAwesome";
import ChevronRightIcon from "@mui/icons-material/ChevronRight";
import SendIcon from "@mui/icons-material/Send";
import WhatsAppIcon from "@mui/icons-material/WhatsApp";
import BugReportIcon from "@mui/icons-material/BugReport";
import ChecklistIcon from "@mui/icons-material/Checklist";
import ViewKanbanIcon from "@mui/icons-material/ViewKanban";
import MergeTypeIcon from "@mui/icons-material/MergeType";
import ArticleIcon from "@mui/icons-material/Article";
import ErrorOutlineIcon from "@mui/icons-material/ErrorOutline";
import NotificationsActiveIcon from "@mui/icons-material/NotificationsActive";
import CloudQueueIcon from "@mui/icons-material/CloudQueue";
import StorageIcon from "@mui/icons-material/Storage";
import MicIcon from "@mui/icons-material/Mic";
import MicOffIcon from "@mui/icons-material/MicOff";
import StopCircleIcon from "@mui/icons-material/StopCircle";
import { IconButton as MuiIconButton, Popover, Tooltip as MuiTooltip } from "@mui/material";
import { openAppLink } from "./appLinks.js";
import { place, placeName } from "./words.js";
import ConnectAi from "./ConnectAi.jsx";
import { Logo, hasLogo } from "./logos.jsx";
import PublishedPages, { isPublished } from "./PublishedPages.jsx";
import { choice, label as btnLabel } from "./buttons.js";   // buttons.json's words; theme.jsx owns `label`
import { asUtc, setTz, fmtTime } from "./dates.js";
import { FOCUS_RING, pressable } from "./pressable.js";
import { readContacts } from "./contacts.js";
import { personLine, runSearch, withFound } from "./peopleSearch.js";
export { agentAssignee, assignedAgent, assigneeLabel } from "./agentIdentity.js";
import { ROLES, ACTION_COLORS, TAGS, ASSISTANT, ALERT, ALERT_INK, ALERT_TINT, ALERT_BD, BORDER, CATPPUCCIN, TASK_STATUS_COLORS, mono, DIM, FAINT, INK, PANEL, ACCENT2, PANEL2, label } from "./theme.jsx";
import { AGENT_SHOWN, shownAgent } from "./kinds.js";

// Taskuary actions wear Taskuary's actual product mark. The generic robot glyph suggested a
// third-party bot and, on a quiet text button, did not make the dispatch action read as a button.
// TASKUARY'S STAR, drawn in the ink around it (the owner, 2026-09-28: "don't like the taskuary logo in the assistant ...
// doesn't look right") - the bright image tile read as a foreign badge on the Assistant's own surfaces
export const StarMark = ({ size = 14 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" aria-hidden>
    <line x1="12" y1="3.5" x2="12" y2="20.5" /><line x1="4.6" y1="7.75" x2="19.4" y2="16.25" /><line x1="4.6" y1="16.25" x2="19.4" y2="7.75" />
    <circle cx="12" cy="12" r="1.7" fill="currentColor" stroke="none" />
  </svg>
);

// the product mark - recoloured purple to Taskuary green in the image itself, the glyph unchanged (the owner, 2026-10-06)
export const TaskuaryMark = ({ size = 18, sx }) => (
  <Box component="img" src={`${import.meta.env.BASE_URL}favicon.png?v=4`} alt="" aria-hidden
    sx={{ width: size, height: size, display: "block", flexShrink: 0, borderRadius: "27%", ...sx }} />
);

// Brand colors so a glance says where a message came from: Teams purple, Outlook blue - and
// amber for scheduled reports, the one row that is ours and not a person, so it has to read
// from across the room rather than blend into the paper the way sage did.
// a workflow is a report's sibling that WRITES - its own mark, in the rail's sage, never the report's amber
export const CHANNEL_COLORS = { teams: "#6264A7", email: "#41525f", github: "#2b2a26", report: "#c47d1a", workflow: "#6f8a6e", assistant: ASSISTANT.solid,
  followup: "#6f8a6e", promise: "#55697a", prep: "#8a7a5c", cold: "#8a3646", idea: "#55697a",     // the assistant's producers (Settings)
  slack: "#611f69", telegram: "#229ED9", whatsapp: "#25D366", imessage: "#34C759", ai: "#55697a",
  jira: "#0052CC", asana: "#F06A6A", monday: "#6161FF", clickup: "#7b68ee", todoist: "#e44332",
  gitlab: "#fc6d26", azdo: "#0078d4", linear: "#5e6ad2", trello: "#0079bf", notion: "#37352f",
  discord: "#5865F2", sentry: "#7b6bc9", pagerduty: "#048a24",
  aws: "#ff9900", azure: "#0078d4", database: "#6b6459", smb_file: "#6b6459", own: "#8a7a5c" };
// ...and the ONE colour that stands for a source, for the dot on the work rail. A channel with its
// own brand mark is not in the table above (the mark colours itself), so its logo's colour is named
// here rather than falling through to the grey everything-else takes.
const BRAND_COLORS = { outlook: "#0F6CBD", gmail: "#EA4335", imap: "#41525f", calendar: "#55697a" };
export const channelColor = (ch) => BRAND_COLORS[ch] || CHANNEL_COLORS[ch] || "#a9a294";
const CHANNEL_ICONS = { teams: GroupsIcon, github: GitHubIcon, report: AssessmentIcon, workflow: AccountTreeOutlinedIcon,
  followup: SendIcon, promise: ChecklistIcon, prep: GroupsIcon, cold: ErrorOutlineIcon, idea: AutoAwesomeIcon,
  email: MailOutlineIcon, slack: TagIcon, telegram: SendIcon, whatsapp: WhatsAppIcon, imessage: SendIcon,
  ai: AutoAwesomeIcon, jira: BugReportIcon, asana: ChecklistIcon, monday: ViewKanbanIcon,
  clickup: ViewKanbanIcon, todoist: ChecklistIcon,
  gitlab: MergeTypeIcon, azdo: ViewKanbanIcon, linear: ChecklistIcon, trello: ViewKanbanIcon,
  notion: ArticleIcon, discord: TagIcon, sentry: ErrorOutlineIcon, pagerduty: NotificationsActiveIcon,
  aws: CloudQueueIcon, azure: CloudQueueIcon, database: StorageIcon, smb_file: StorageIcon,
  own: PersonOutlineIcon };
// A product named on a card wears its OWN logo where we have one (logos.jsx, self-colored);
// everything else falls back to a Material glyph tinted with the channel's brand color.
export const ChannelIcon = ({ channel, sx }) => {
  if (channel === "assistant") return <TaskuaryMark size={15} sx={sx} />;
  if (hasLogo(channel)) return <Logo name={channel} sx={sx} />;
  const Icon = CHANNEL_ICONS[channel] || TerminalIcon;
  return <Icon sx={{ fontSize: 15, color: CHANNEL_COLORS[channel] || "#a9a294", ...sx }} />;
};

/* One dialog for everything that destroys something.

   Deleting a report, an agent or a connection, and "Not a task" - which deletes the task AND
   writes a verdict triage reads on every later message - were all a single unconfirmed click; "Not a task" was one
   click inside a MENU, where the pointer is already moving. None of it is undoable.

   `what` names the thing in the user's own words, `consequence` says what actually happens
   beyond the obvious (a sender rule written, credentials wiped, a schedule stopped) - a dialog
   that only says "are you sure?" tells you nothing you did not already know. The failure is
   shown here rather than swallowed: these calls can be refused, and a dialog that closes on a
   failed delete claims the thing is gone. */
/* One in-app question in the app's own voice. A native confirm() paints the browser's
   "127.0.0.1:7787 says" box over the page - the one dialog in the product that does not look
   like the product. */
export const Confirm = ({ open, title, text, confirmLabel = "OK", onConfirm, onClose }) => {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const go = async () => {
    setBusy(true); setErr("");
    try { await onConfirm(); setBusy(false); onClose(); }
    catch (e) { setErr(e?.response?.data?.detail || e?.message || "that did not work"); setBusy(false); }
  };
  return (
    <Dialog open={!!open} onClose={busy ? undefined : onClose} maxWidth="xs" fullWidth>
      <DialogTitle sx={{ fontSize: 15.5, fontWeight: 600, pb: 0.5 }}>{title}</DialogTitle>
      <DialogContent>
        <DialogContentText sx={{ fontSize: 13, color: DIM, whiteSpace: "pre-wrap" }}>{text}</DialogContentText>
        {err && <Alert severity="error" sx={{ mt: 1.5 }}>{err}</Alert>}
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 2 }}>
        <Button onClick={onClose} disabled={busy}>Cancel</Button>
        <Button variant="contained" disableElevation onClick={go} disabled={busy}>
          {busy ? <CircularProgress size={14} sx={{ color: "#fff" }} /> : confirmLabel}</Button>
      </DialogActions>
    </Dialog>
  );
};

export const ConfirmDelete = ({ open, what, consequence, confirmLabel = "Delete", title = null, undoable = false, onConfirm, onClose }) => {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const go = async () => {
    setBusy(true); setErr("");
    try { await onConfirm(); setBusy(false); onClose(); }
    catch (e) { setErr(e?.response?.data?.detail || e?.message || "that did not work"); setBusy(false); }
  };
  return (
    <Dialog open={!!open} onClose={busy ? undefined : onClose} maxWidth="xs" fullWidth>
      <DialogTitle sx={{ fontSize: 15.5, fontWeight: 600, pb: 0.5 }}>{title || `Delete ${what}?`}</DialogTitle>
      <DialogContent>
        <DialogContentText sx={{ fontSize: 13, color: DIM }}>
          {consequence}{undoable ? "" : " This cannot be undone."}
        </DialogContentText>
        {err && <Alert severity="error" sx={{ mt: 1.5, fontSize: 12.5 }}>{err}</Alert>}
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 2 }}>
        {/* Cancel is the default focus and sits where the eye lands: the safe one is not the
            one you hit by reflex */}
        <Button onClick={onClose} disabled={busy} autoFocus sx={{ fontSize: 12.5 }}>Cancel</Button>
        <Button onClick={go} disabled={busy} color="error" variant="contained" disableElevation
          sx={{ fontSize: 12.5 }}>{busy ? "…" : confirmLabel}</Button>
      </DialogActions>
    </Dialog>
  );
};

export const RefChip = ({ taskId, onClick }) => taskId ? (
  <Chip size="small" label={`TQ-${String(taskId).padStart(4, "0")}`} onClick={onClick}
    sx={{ fontFamily: "'IBM Plex Sans', 'Segoe UI', Arial, sans-serif", fontVariantNumeric: "tabular-nums",
      letterSpacing: ".015em", fontWeight: 600, bgcolor: "#eae4d8", color: "#55697a",
      height: 19, fontSize: 10.5 }} />
) : null;

export const ActionChip = ({ action, reviewStatus, taskStatus, needsYou, category, working }) => {
  // an agent in a live session on this task: the row says so, by name - not "needs you"
  if (working && taskStatus !== "done" && reviewStatus !== "pending") {
    // "agent", not the agent's name: the name is whichever CLI happens to be configured (claude,
    // codex, a wrapper) and reads as a brand on a status chip; the tooltip still says who
    return <Chip size="small" label="agent working" title={`${working} has this task open in a live session right now`}
      sx={{ bgcolor: ROLES.working.tint, color: ROLES.working.ink, height: 19, fontSize: 10.5, fontWeight: 600 }} />;
  }
  // a category that is NOT a review state (info, promo, ignored…) is the whole story - a
  // stray review row must not turn a colleague's FYI into "reviewed · edited"
  const cat = category && TAGS[category];
  if (cat && !["coding", "todo", "review", "triaging"].includes(category) && taskStatus !== "done") {
    return <Chip size="small" label={cat.label} title={cat.hint} sx={{ bgcolor: cat.bg, color: cat.fg, height: 19, fontSize: 10.5, fontWeight: 600 }} />;
  }
  // A finished task outranks everything else the chip could say.
  if (taskStatus === "done" && reviewStatus !== "pending") {
    return <Chip size="small" label="done" sx={{ bgcolor: "#dfeade", color: "#47654a", height: 19, fontSize: 10.5, fontWeight: 600 }} />;
  }
  // and "nobody is moving this" outranks the verdict: what happened to it matters less
  // than whether it is sitting on you right now
  if (needsYou) {
    return <Chip size="small" label="needs you" sx={{ bgcolor: ALERT, color: "#fffdfb",
      height: 19, fontSize: 10.5, fontWeight: 600 }} />;
  }
  // What actually matters to the reader: current state, not just the original verdict.
  // 'report' and 'feed' are NOT verdicts - nothing judged those items; they are here to be
  // read. Only 'ignored' means a policy actually rejected something.
  if (action === "triaging") {                     // decided in seconds: the pill breathes until then
    return <Chip size="small" label="triaging…" sx={{ bgcolor: "#e6e0d5", color: "#6f6960", height: 19, fontSize: 10.5, fontWeight: 600,
      "@keyframes tqBreathe": { "50%": { opacity: 0.45 } }, animation: "tqBreathe 1.4s ease-in-out infinite" }} />;
  }
  const key = ["report", "feed", "filed"].includes(action) ? action
    : reviewStatus === "auto" ? "auto"
      : reviewStatus === "pending" ? "draft"
        : action || "task_only";
  const c = (cat && !["pending", "auto"].includes(reviewStatus || "") ? cat : null) || ACTION_COLORS[key] || ACTION_COLORS.task_only;
  const decided = reviewStatus && !["pending", "auto"].includes(reviewStatus);
  const label = !decided ? c.label : reviewStatus === "no_reply" ? "no reply needed" : `reviewed · ${reviewStatus}`;
  return <Chip size="small" label={label}
    sx={{ bgcolor: decided ? (reviewStatus === "no_reply" ? "#e9e3d8" : "#dfeade") : c.bg,
      color: decided ? (reviewStatus === "no_reply" ? "#867f74" : "#47654a") : c.fg, height: 19, fontSize: 10.5 }} />;
};

/* ── Proof of work: the evidence behind a task, so approving is a judgement and not an act
   of faith. Everything here is measured (git, the session's own test output, the checks
   API) - and what is MISSING is stated, because a thin card must never read as a clean
   one. Fetches itself; renders nothing at all for a task with no evidence yet. ── */
const PILL = { ok: { bg: "#dfeade", fg: "#47654a" }, bad: { bg: "#f0e2e4", fg: "#6b2733" },
  wait: { bg: "#eae4d8", fg: "#55697a" }, none: { bg: "#e9e3d8", fg: "#867f74" } };
const Pill = ({ tone = "none", children }) => (
  <Box component="span" sx={{ ...PILL[tone], px: 0.85, py: 0.2, borderRadius: 99, fontSize: 10.5, fontWeight: 600 }}>
    {children}
  </Box>
);

export const ProofCard = ({ taskId, onOpenTask }) => {
  const [p, setP] = useState(null);
  const [busy, setBusy] = useState("");
  const load = React.useCallback(() => {
    if (!taskId) return;
    api.get(`/api/tasks/${taskId}/proof`).then(({ data }) => setP(data)).catch(() => setP(null));
  }, [taskId]);
  useEffect(() => { load(); }, [load]);
  if (!p) return null;
  const t = p.tests || {}, ci = p.ci, ds = p.diffstat || {};
  const act = async (path) => {
    setBusy(path);
    try { await api.post(`/api/tasks/${taskId}/${path}`); load(); }
    catch (e) { setP({ ...p, error: e?.response?.data?.detail || "that did not work" }); }
    setBusy("");
  };
  return (
    <Box sx={{ bgcolor: PANEL2, border: `1px solid ${BORDER}`, borderRadius: 1.5, px: 1.25, py: 1 }}>
      <Box sx={{ display: "flex", alignItems: "center", gap: 0.75, flexWrap: "wrap", mb: 0.5 }}>
        <Pill tone={ds.files ? "ok" : "none"}>
          {ds.files ? `${plural(ds.files, "file")} · +${ds.added} −${ds.removed}` : "no file changes"}
        </Pill>
        <Pill tone={!t.ran ? "none" : t.failed ? "bad" : "ok"}>
          {!t.ran ? "no tests detected" : t.failed ? `${t.failed} failing / ${t.passed} passed` : `${t.passed} tests passed`}
        </Pill>
        {ci && (
          <Pill tone={ci.checks?.state === "failure" ? "bad" : ci.checks?.state === "pending" ? "wait"
            : ci.checks?.state === "success" ? "ok" : "none"}>
            {`${ci.kind === "pr" ? `PR #${ci.number}` : `${ci.branch} @ ${ci.sha}`} · CI ${ci.checks?.state || "unchecked"}`}
          </Pill>
        )}
        {p.seconds != null && <Pill>{dur(p.seconds)} elapsed</Pill>}
        {p.attempts?.length > 1 && <Pill tone="wait">{p.attempts.length} attempts</Pill>}
      </Box>
      {t.ran && t.line && (
        <Typography variant="caption" sx={{ ...mono, color: DIM, display: "block", fontSize: 10.5 }}>{t.line}</Typography>
      )}
      {p.files?.length > 0 && (
        <Box sx={{ mt: 0.5, maxHeight: 132, overflowY: "auto" }}>
          {p.files.slice(0, 24).map((f) => (
            <Box key={f.path} sx={{ display: "flex", gap: 1, alignItems: "baseline" }}>
              <Typography variant="caption" sx={{ ...mono, color: INK, fontSize: 10.5, flex: 1, minWidth: 0 }} noWrap>{f.path}</Typography>
              <Typography variant="caption" sx={{ ...mono, color: "#47654a", fontSize: 10 }}>+{f.added}</Typography>
              <Typography variant="caption" sx={{ ...mono, color: "#6b2733", fontSize: 10 }}>−{f.removed}</Typography>
            </Box>
          ))}
        </Box>
      )}
      {ci?.checks?.failed?.length > 0 && (
        <Box sx={{ mt: 0.5 }}>
          {ci.checks.failed.map((f) => (
            <Typography key={f.name} variant="caption" sx={{ color: "#6b2733", display: "block", fontSize: 10.5 }}>
              ✗ {f.name}{f.summary ? ` — ${f.summary}` : ""}
            </Typography>
          ))}
        </Box>
      )}
      {p.gaps?.length > 0 && (
        <Typography variant="caption" sx={{ color: FAINT, display: "block", mt: 0.5 }}>
          Not evidenced: {p.gaps.join(" · ")}
        </Typography>
      )}
      <Box sx={{ display: "flex", gap: 1.25, mt: 0.75, alignItems: "center", flexWrap: "wrap" }}>
        {ci ? (
          <>
            <Box component="a" href={ci.url} target="_blank" rel="noreferrer"
              sx={{ fontSize: 11, fontWeight: 600, color: "#55697a", textDecoration: "none" }}>
              {ci.kind === "pr" ? "open PR ↗" : "the commit ↗"}
            </Box>
            <Box component="button" type="button" disabled={!!busy} onClick={() => act("ci")}
              sx={{ border: 0, bgcolor: "transparent", p: 0, font: "inherit",
                fontSize: 11, fontWeight: 600, color: busy ? FAINT : "#55697a", cursor: "pointer" }}>
              {busy === "ci" ? "Checking CI…" : "re-check CI"}
            </Box>
          </>
        ) : (
          // the button says what it will actually DO, per Settings → How finished work lands;
          // the other road stays one click away rather than buried in Settings
          <>
            <Box component="span" onClick={() => !busy && act("land")}
              title={p.flow === "direct" ? "pushes the commits already in the checkout straight onto the default branch"
                : "opens a DRAFT pull request from this task's branch — it merges only when you approve the task's close-out"}
              sx={{ fontSize: 11, fontWeight: 600, color: busy ? FAINT : "#55697a", cursor: "pointer" }}>
              {busy === "land" ? "landing…" : p.flow === "direct" ? "push straight to the branch" : "open a draft PR"}
            </Box>
            <Box component="span" onClick={() => !busy && act(`land?flow=${p.flow === "direct" ? "pr" : "direct"}`)}
              title="just this once, the other way"
              sx={{ fontSize: 11, color: busy ? FAINT : FAINT, cursor: "pointer", "&:hover": { color: "#55697a" } }}>
              {p.flow === "direct" ? "or a draft PR" : "or push direct"}
            </Box>
          </>
        )}
        {onOpenTask && (
          <Box component="span" onClick={() => onOpenTask(taskId)}
            sx={{ fontSize: 11, fontWeight: 600, color: "#55697a", cursor: "pointer" }}>the whole session</Box>
        )}
      </Box>
      {p.error && <Typography variant="caption" sx={{ color: "#6b2733", display: "block", mt: 0.5 }}>{p.error}</Typography>}
    </Box>
  );
};

export const StatusDot = ({ ok, warn }) => (
  <Box component="span" sx={{ display: "inline-block", width: 8, height: 8, borderRadius: "50%", mr: 1,
    bgcolor: ok ? ROLES.done.solid : warn ? ROLES.working.solid : "#cfc9bf" }} />
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
      <Box key={i} ref={tail ? boxRef : null} sx={{ bgcolor: CATPPUCCIN.bg, borderRadius: 1.5, px: 1.25, py: 0.75,
        my: 0.5, maxHeight: 280, overflowY: "auto", border: `1px solid ${CATPPUCCIN.surface}` }}>
        {g.items.map((ev, k) => (
          <Typography key={k} variant="caption" sx={{ ...mono, display: "block", fontSize: 10.5, lineHeight: 1.6,
            whiteSpace: "pre-wrap", wordBreak: "break-word",
            color: ev.detail.startsWith("→") ? CATPPUCCIN.blue : ev.detail.startsWith("✗") ? CATPPUCCIN.red : CATPPUCCIN.dim }}>
            <span style={{ color: CATPPUCCIN.faint }}>{(ev.at || "").slice(11)}</span> {ev.detail}
          </Typography>
        ))}
        {running && tail && (
          <Typography variant="caption" sx={{ ...mono, color: CATPPUCCIN.cyan, fontSize: 10.5,
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
    ? { color: "#2b2a26", fontWeight: 600, bgcolor: "#e9e3d8" }
    : l.startsWith("@@") ? { color: "#6f8a6e", bgcolor: "#e3e6e1" }
      : l.startsWith("+") ? { color: "#47654a", bgcolor: "#dfeade" }
        : l.startsWith("-") ? { color: "#6b2733", bgcolor: "#f0e2e4" }
          : { color: "#5e685f" };
  return (
    <Box sx={{ border: "1px solid #e1dcd5", borderRadius: 1.5, overflow: "auto", maxHeight: 360, bgcolor: "#fff" }}>
      {lines.map((l, i) => (
        <Box key={i} component="pre" sx={{ ...mono, m: 0, px: 1.25, py: 0.1, fontSize: 11,
          lineHeight: 1.5, whiteSpace: "pre-wrap", wordBreak: "break-all", ...style(l) }}>
          {l || " "}
        </Box>
      ))}
    </Box>
  );
};

/* The same diff, per FILE. One 360px box holding a five-file change is not a review - you
   scroll it once and approve on vibes. A row per file with its own counts is a list you can
   work through, and the first file opens because a one-file change should need no clicks. */
export const DiffFiles = ({ files, cwd, branch }) => {
  const [open, setOpen] = React.useState(() => new Set(files.length === 1 ? [0] : []));
  const flip = (i) => setOpen((s) => { const n = new Set(s); n.has(i) ? n.delete(i) : n.add(i); return n; });
  if (!files.length) return <Empty>Nothing to push — no commits waiting, and the working tree is clean.</Empty>;
  return (
    <Box>
      <Typography variant="caption" sx={{ ...mono, color: FAINT, display: "block", mb: 0.75, wordBreak: "break-all" }}>
        {cwd}{branch ? ` · ${branch}` : ""}
      </Typography>
      {files.map((f, i) => (
        <Box key={f.path} sx={{ border: `1px solid ${BORDER}`, borderRadius: 1.5, mb: 0.75, overflow: "hidden", bgcolor: "#fff" }}>
          <Box onClick={() => flip(i)}
            sx={{ display: "flex", alignItems: "center", gap: 1, px: 1.25, py: 0.7, cursor: "pointer",
              bgcolor: "#f4f1ec", "&:hover": { bgcolor: "#e9e3d8" } }}>
            <ChevronRightIcon sx={{ fontSize: 16, color: FAINT, flexShrink: 0,
              transform: open.has(i) ? "rotate(90deg)" : "none", transition: "transform .12s" }} />
            <Typography sx={{ ...mono, fontSize: 11.5, color: INK, flex: 1, minWidth: 0,
              overflow: "hidden", textOverflow: "ellipsis", direction: "rtl", textAlign: "left" }}>
              {f.path}
            </Typography>
            {/* the two numbers people actually scan a file list for */}
            <Typography sx={{ ...mono, fontSize: 11, color: "#47654a", fontVariantNumeric: "tabular-nums" }}>+{f.added}</Typography>
            <Typography sx={{ ...mono, fontSize: 11, color: "#6b2733", fontVariantNumeric: "tabular-nums" }}>−{f.removed}</Typography>
          </Box>
          {open.has(i) && (f.binary
            ? <Typography variant="caption" sx={{ color: FAINT, display: "block", px: 1.5, py: 1 }}>Binary file — git reports it changed, there is no text to show.</Typography>
            : f.truncated
              ? <Typography variant="caption" sx={{ color: FAINT, display: "block", px: 1.5, py: 1 }}>Too large to render here — open it in your editor.</Typography>
              : <DiffBlock text={f.patch} />)}
        </Box>
      ))}
    </Box>
  );
};

/* The four things you can do with a timeline item were four buttons of four different sizes
   and colours, two rows apart, half of them right-aligned - so the reader had to hunt for
   the set. One list, one shape per row: what it is, and what it does. */
/* ── Voice into prompts. Is there a speech-to-text connector at all (Connections → AI — voice)?
   Asked once per mount; the mic explains itself when there is none. ── */
export const useVoiceReady = () => {
  const [v, setV] = React.useState(null), [n, setN] = React.useState(0);
  React.useEffect(() => {
    let alive = true;
    api.get("/api/voice/status").then(({ data }) => alive && setV(data)).catch(() => alive && setV({ ready: false }));
    return () => { alive = false; };
  }, [n]);
  return v && { ...v, recheck: () => setN((x) => x + 1) };
};
// the owner picked the browser's own recogniser over a voice AI, once - remembered on this browser
const BROWSER_VOICE = "tq-voice-browser";
const browserVoice = () => { try { return localStorage.getItem(BROWSER_VOICE) === "1"; } catch { return false; } };

// One mic. Press to record, press again to stop; the clip goes to /api/voice/transcribe as its
// raw bytes and the text lands through onText - into a prompt box, or straight into a session.
export const MicButton = ({ onText, onInterim, onActive, ctl, size = 18, sx }) => {
  const voice = useVoiceReady();
  const live = React.useRef({}); live.current = { onText, onInterim };   // the latest handlers: a session outlives many renders
  const [rec, setRec] = React.useState(null);
  const [busy, setBusy] = React.useState(false);
  // ...and SAYS WHILE IT LISTENS OR TRANSCRIBES (the owner, 2026-10-27: "I click on the voice thing, it expands, but while I'm talking it
  // gets small"): the browser's mic prompt takes the focus, and the chat box that opened for it read that as a look away and shut - its
  // mic with it, mid-sentence. The box holds itself open while this is true
  React.useEffect(() => { onActive?.(!!rec || busy); }, [!!rec, busy]);   // eslint-disable-line react-hooks/exhaustive-deps
  const [err, setErr] = React.useState("");
  const [ask, setAsk] = React.useState(null), [byBrowser, setByBrowser] = React.useState(browserVoice);
  // ...and a mic that stops SAYS WHY, beside it, not in a tooltip nobody hovers (the owner, 2026-10-28: "it just turns right off")
  const errAt = React.useRef(0), recRef = React.useRef(null); recRef.current = rec;
  const flash = (s) => { setErr(s); clearTimeout(errAt.current); errAt.current = setTimeout(() => setErr(""), 8000); };
  React.useEffect(() => () => { clearTimeout(errAt.current); recRef.current?.cancel?.(); }, []);
  const [hover, setHover] = React.useState(false);
  // NO VOICE AI, NO LIVE MIC (the owner, 2026-10-15: "if there is no voice provider the mic icon ... should be crossed out with popup
  // to configure voice ai before it will activate"): the mic shows crossed out and its press asks - set up a voice AI, or (Edge and
  // Chrome ship their own recogniser, the Web Speech API, free) use the browser's. That one cannot transcribe a voice-note FILE, so
  // the connectors still matter for the funnel.
  const SR = typeof window !== "undefined" ? (window.SpeechRecognition || window.webkitSpeechRecognition) : null;
  const viaBrowser = !!(voice && !voice.ready && SR && byBrowser);
  const off = !!(voice && !voice.ready && !viaBrowser);
  const press = (e) => { if (!off) return start(); setAsk(e.currentTarget); voice.recheck(); };
  // set up in the meantime (the popup's own button, or another tab): the mic is live the moment the status says so
  React.useEffect(() => { if (ask && voice?.ready) setAsk(null); }, [ask, voice?.ready]);
  const start = async () => {
    setErr("");
    if (viaBrowser) {
      // ...it keeps listening until the owner stops it (dictate, dictation.js): Chrome's own ends are started again, and a stop it will
      // not take back says why. With onInterim (the chat box) each settled phrase lands as it is said and the rest shows as it is heard;
      // elsewhere the whole lands at the stop, as before
      let all = "";
      const vocab = voice?.vocabulary?.length && window.SpeechRecognitionPhrase ? () => voice.vocabulary.map((term) => new window.SpeechRecognitionPhrase(term, 5)) : null;
      try {
        const d = dictate({ SR, lang: navigator.language || "en-US", phrases: vocab,
          onFinal: (t) => { if (live.current.onInterim) live.current.onText?.(t); else all = all ? `${all} ${t}` : t; },
          onInterim: (t) => live.current.onInterim?.(t),
          onEnd: (line) => { setRec(null); if (ctl) ctl.current = null; if (all) live.current.onText?.(all); if (line) flash(line); } });
        setRec(d); if (ctl) ctl.current = { cancel: () => d.cancel() };
      } catch { flash("This browser cannot dictate here - set up a voice AI instead"); }
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const type = window.MediaRecorder?.isTypeSupported?.("audio/webm;codecs=opus") ? "audio/webm;codecs=opus" : undefined;
      const mr = new MediaRecorder(stream, type ? { mimeType: type } : undefined);
      const chunks = [];
      mr.ondataavailable = (e) => { if (e.data.size) chunks.push(e.data); };
      mr.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        const blob = new Blob(chunks, { type: mr.mimeType || "audio/webm" });
        setBusy(true);
        try {
          const { data } = await api.post("/api/voice/transcribe", blob, { headers: { "Content-Type": blob.type || "audio/webm" } });
          if (data.text) onText?.(data.text); else flash("nothing audible");
        } catch (e) { flash(e?.response?.data?.detail || "transcription failed"); }
        setBusy(false);
      };
      mr.start(); setRec(mr);
    } catch (e) { flash(e?.name === "NotAllowedError" ? dictationError("not-allowed") : "No microphone this browser can use - plug one in or allow it in the address bar"); }
  };
  const stop = () => { rec?.stop(); if (!viaBrowser) setRec(null); };   // the browser's dictation reports back through onEnd
  const title = err || (!voice ? ""
    : rec ? "Stop and transcribe"
    : voice.ready ? `Dictate (${voice.label || voice.provider})`
    : viaBrowser ? `Dictate — your browser's own recogniser. A voice AI (${placeName("voice")}) is more accurate and reads voice notes.`
    : "Voice is off — no voice AI is set up yet");
  const useBrowser = () => {
    try { localStorage.setItem(BROWSER_VOICE, "1"); } catch { /* private window: this visit only */ }
    setByBrowser(true); setAsk(null);
  };
  return (<>
    <MuiTooltip title={ask ? "" : err ? <span data-tq-mic-err="">{err}</span> : title} open={!ask && (!!err || (hover && !!title))}
      onOpen={() => setHover(true)} onClose={() => setHover(false)}><span>
      <MuiIconButton size="small" onClick={rec ? stop : press} disabled={busy || !voice} sx={sx} data-tq-mic={off ? "off" : "on"}
        aria-label={rec ? "stop recording" : off ? "voice is off - set up a voice AI" : "dictate"}>
        {busy ? <CircularProgress size={size - 4} /> : rec ? <StopCircleIcon sx={{ fontSize: size, color: "#8a3646" }} />
          : off ? <MicOffIcon sx={{ fontSize: size, opacity: 0.7 }} /> : <MicIcon sx={{ fontSize: size }} />}
      </MuiIconButton>
    </span></MuiTooltip>
    <Popover open={!!ask} anchorEl={ask} onClose={() => setAsk(null)} data-tq-voice-ask
      anchorOrigin={{ vertical: "top", horizontal: "center" }} transformOrigin={{ vertical: "bottom", horizontal: "center" }}
      slotProps={{ paper: { sx: { p: 1.75, maxWidth: 320, borderRadius: 2, mt: -0.75 } } }}>
      <Typography sx={{ fontSize: 13.5, fontWeight: 600, color: INK }}>Set up voice to talk instead of type</Typography>
      <Typography sx={{ fontSize: 12.5, color: DIM, mt: 0.5, lineHeight: 1.5 }}>
        Pick a voice AI under {placeName("voice")}. Groq has a free tier; Local Whisper runs on this computer with no key.
      </Typography>
      <Box sx={{ display: "flex", gap: 1, mt: 1.5, flexWrap: "wrap" }}>
        <Button size="small" variant="contained" disableElevation sx={{ textTransform: "none" }}
          onClick={() => { setAsk(null); openAppLink(place("voice").href); }}>Set up voice AI</Button>
        {SR && <Button size="small" sx={{ textTransform: "none" }} onClick={useBrowser}>Use this browser's own (free)</Button>}
      </Box>
    </Popover>
  </>);
};

export const ChoiceRow = ({ icon, label, hint, tint = "#eae4d8", onClick, first, busy }) => (
  <Box onClick={busy ? undefined : onClick}
    sx={{ display: "flex", alignItems: "center", gap: 1.1, px: 1.25, py: 0.55, cursor: busy ? "default" : "pointer",
      borderTop: first ? "none" : `1px solid ${BORDER}`, transition: "background .12s",
      "&:hover": { bgcolor: busy ? "transparent" : "#f4f1ec" }, "&:hover .thubChoiceGo": { opacity: 1, transform: "none" } }}>
    <Box sx={{ width: 24, height: 24, borderRadius: 1.5, bgcolor: tint, flexShrink: 0,
      display: "flex", alignItems: "center", justifyContent: "center" }}>{icon}</Box>
    {/* one line per choice: the label, then its hint trailing in the same line (ellipsis on
        a narrow panel, the whole of it on hover) - eight two-line rows needed a scrollbar */}
    <Box sx={{ flex: 1, minWidth: 0, display: "flex", alignItems: "baseline", gap: 0.9 }} title={hint || undefined}>
      <Typography variant="body2" sx={{ color: INK, fontWeight: 600, lineHeight: 1.3, whiteSpace: "nowrap" }}>{label}</Typography>
      {hint && <Typography variant="caption" noWrap sx={{ color: FAINT, fontSize: 10.5, minWidth: 0 }}>{hint}</Typography>}
    </Box>
    {busy ? <CircularProgress size={13} />
      : <ChevronRightIcon className="thubChoiceGo" sx={{ fontSize: 16, color: FAINT, opacity: 0,
          transform: "translateX(-3px)", transition: "opacity .12s, transform .12s" }} />}
  </Box>
);

export const ChoiceList = ({ children }) => (
  <Box sx={{ bgcolor: PANEL, border: `1px solid ${BORDER}`, borderRadius: 2, overflow: "hidden" }}>{children}</Box>
);

export const AgentReport = ({ body, artifacts: all = [] }) => {
  // WHAT THE AGENT DID (the owner, 2026-10-09: "Just show the last message/summary and that's all"; then "the original summary
  // was much more in detail? what happened to that?"). The detailed account is the ANSWER the agent saved for the task
  // (session_artifacts.result - the seven items); a later session's last message is only that session's own news (the deploy),
  // so showing it alone dropped the answer. The answer in full, the newest session's own account in full under it, and what
  // it made.
  // With no saved answer: the session's last message, else its summary.
  const answer = all.find((a) => a.kind === "agent_result");             // newest first, as the API sends them
  // ...and what it MADE: pages it published, files a chat showed (the owner, 2026-10-09: "agent work ... should reflect what it
  // did. simple task and any related artifacts it creates. replies, actions should be on the close out tab")
  const pages = all.filter((a) => isPublished(a) || a.kind === "shown");
  // the session's last message rides at the END of the report (the agent's finish: AGENT REPORT ... LAST MESSAGE ...; CODER REPORT on older rows)
  const [report, last] = String(body || "").replace(/^((?:AGENT|CODER) REPORT|HANDOVER NOTE)\n?/, "").trim().split(/\n+LAST MESSAGE\n/);
  const lead = (/^Summary:[ \t]*([\s\S]*?)(?=^(?:Triage|Determination|Actions|Found|Did|Next):|(?![\s\S]))/m.exec(report)?.[1] ?? report).trim();
  const [said, setSaid] = useState(answer?.url ? null : "");
  useEffect(() => {
    let live = true;
    // its '# TQ-0001 - <title>' heading is the task's title, not the answer
    if (answer?.url) api.get(answer.url, { responseType: "text", transformResponse: (x) => x })
      .then(({ data }) => live && setSaid(String(data || "").replace(/^# [\s\S]*?(\n\s*\n|$)/, "").trim())).catch(() => live && setSaid(""));
    else setSaid("");
    return () => { live = false; };
  }, [answer?.url]);
  if (said == null) return <CircularProgress size={12} />;
  const words = (said || last || lead || "").trim();
  // the newest session's own account, in full, under the answer it followed (the owner, 2026-10-09: "i want to see the full
  // output of the session summary") - its last message, else its summary
  const since = said ? (last || lead || "").trim() : "";
  if (!words && !pages.length) return null;
  return (
    <Box sx={{ width: "100%", bgcolor: PANEL, px: 1.35, py: 1.15 }}>
      {words && <Box sx={{ fontSize: 13, color: INK }}><Md text={words} /></Box>}
      {since && since !== said && (
        <Box sx={{ mt: 1.2, pt: 1, borderTop: `1px solid ${BORDER}` }}>
          <Typography sx={{ fontSize: 11.5, fontWeight: 600, color: DIM, mb: 0.4 }}>Latest session</Typography>
          <Box sx={{ fontSize: 13, color: INK }}><Md text={since} /></Box>
        </Box>
      )}
      {!!pages.length && <Box sx={{ mt: words ? 1 : 0 }}><PublishedPages pages={pages} deliver /></Box>}
    </Box>
  );
};

// ...and every task page opens on the LAST READ, re-read behind it: each page read /api/agents afresh, so its agent buttons drew as
// "nothing known yet" and flipped a beat later (the owner, 2026-10-26: "when you load task the buttons load then go gray then reload")
let agentsLast = null;
const agentsOf = (data) => ({
  agentsRead: true, codingReady: data.coding_ready ?? !!(data.brain_list || []).length,
  agents: (data.data || []).map((a) => a.Name),
  models: data.models || {},
  // what each worker is FOR. A coding dialog asks which CLI; the five general profiles -
  // researcher, analyst, coordinator, marketer, trader - answer a question it never asked.
  kinds: Object.fromEntries((data.data || []).map((a) => [a.Name, a.Kind])),
  // profile name -> the CLI it actually runs (the coding profile is usually claude) - the Board
  // tints a working card by the BRAND, and the name alone doesn't say which one it is
  cmds: Object.fromEntries(Object.entries(data.config || {}).map(([k, v]) => [k, (v || {}).cmd || k])),
  // ...and WHICH BRAIN each role runs on. A role no longer says which CLI runs it - every
  // coding task's role is the one coding profile - so the card asks this instead (the owner, 2026-09-16).
  brains: data.brains || {}, brainList: data.brain_list || [], brainModels: data.brain_models || {},
  // the brains a NON-coding hand-off may choose: one per installed CLI, then the API connectors
  generalBrains: data.general_brains || [],
});
// agentsRead: [] read is "no AI connected"; [] not yet read is nothing yet. codingReady: a coding agent can start (agents.coding_ready)
const AGENTS_UNREAD = { agents: [], models: {}, cmds: {}, kinds: {}, brains: {}, brainList: [], brainModels: {}, generalBrains: [], agentsRead: false, codingReady: false };
export const useAgents = () => {
  const [v, setV] = useState(() => agentsLast || AGENTS_UNREAD);
  useEffect(() => {
    let on = true;
    api.get("/api/agents").then(({ data }) => { agentsLast = agentsOf(data); if (on) setV(agentsLast); }).catch(() => {});
    return () => { on = false; };
  }, []);
  return v;
};
// THE CODING PROFILE IS FOUND BY ITS KIND, never by a name: the owner may rename it, or have none - and then blank, so
// the server (which resolves the same way) chooses rather than this page naming one that is not there.
export const codingProfile = (agents = [], kinds = {}) => agents.find((a) => String(kinds[a] || "").toLowerCase() === "coding") || "";

// CODING IS THE PROFILE. A coding profile is not a worker to choose between - it is one job that any CLI
// can run, and the question a
// repository dialog asks is which CLI runs it (the owner, 2026-09-14: "for coding there is no need
// to choose profile. That's for general. Coding is the profile for coding sessions"). So in coding
// mode the menu says the CLI, and the five general profiles are not offered at all.
// One row of model choices, wherever they are asked for. `info.models` carries the CLI's own
// [{id,label}] - Claude Code's catalog, codex's models_cache - so the menu reads the way that CLI's
// own /model does; `choices` is the flat id list older payloads still send.
export const ModelSelect = ({ info = {}, model, onModel, size = 30, whose = "tool", sx, menuProps, empty }) => {
  const rows = (info.models || []).filter((m) => m && m.id);
  const ids = rows.length ? rows.map((m) => m.id) : (info.choices || []);
  const labels = Object.fromEntries(rows.map((m) => [m.id, m.label || m.id]));
  // a model saved before its CLI changed hands is still what this run would use: show it, do not
  // silently fall back to the default and report a model nobody chose
  const list = model && !ids.includes(model) ? [model, ...ids] : ids;
  const fs = sx?.fontSize || 12.5;
  return (
    <Select size="small" displayEmpty value={model || ""} onChange={(e) => onModel(e.target.value)} MenuProps={menuProps}
      sx={{ fontSize: 12.5, height: size, bgcolor: "#fff", minWidth: 150, ...sx }}>
      <MenuItem value="" sx={{ fontSize: fs }}>
        {empty || (info.default ? `default · ${info.default}` : `the ${whose}'s default model`)}
      </MenuItem>
      {list.map((m) => <MenuItem key={m} value={m} sx={{ fontSize: fs }}>{labels[m] || m}</MenuItem>)}
    </Select>
  );
};

export { NO_CODING_TOOL };            // one wording, beside the check that greys on it (capabilities.cannotStart)
export const NoCodingTool = () => (
  <Box data-tq-no-coding-tool="" sx={{ display: "flex", alignItems: "center", gap: 1, fontSize: 12.5, color: INK }}>
    <span>{NO_CODING_TOOL} -</span>
    <Button size="small" variant="outlined" onClick={() => openAppLink(place("ai_apps").href)}>Connect one</Button>
  </Box>);

// WHAT MATTERS FOR COMPUTER USE, in the brain menu itself (2026-10-25): four equal items gave no basis for the key choice. Only on a
// task that wants a browser, and only where it is not ordinary. Text in an existing control.
export const brainNote = (b, browser) => [b?.signed_out ? "not signed in" : "",
  browser ? (b?.browser === false ? "can't use the browser" : b?.holds === false ? "browser acts not held" : "") : ""]
  .filter(Boolean).map((t) => ` · ${t}`).join("");

export const AgentPicker = ({ agents, models, agent, model, onAgent, onModel, size = 30, kinds = {},
                             coding = false, brains = [], brain = "", onBrain, brainModels = {},
                             generalBrains = [], brainsRead = false, codingReady = true, pick = "", onPick, has = "", browser = false }) => {
  // A coding picker chooses the BRAIN - which CLI runs the work. It always did in spirit ("chooses
  // the executable, not one of several instruction profiles backed by it") but it named a profile
  // to say so; the role is the coding profile for every coding task now, so that list would be one entry
  // repeated (the 2026-09-16 spec). General work picks a ROLE **and** a brain: two questions, and
  // a hand-off is allowed to answer both (the owner, 2026-09-18).
  const roles = Object.keys(kinds).length
    ? agents.filter((a) => !["coding", "cli"].includes(String(kinds[a] || "").toLowerCase())) : agents;
  // A BRAIN THAT IS GONE IS STILL WHAT THIS TASK NAMES. `brains` is the installed list now, so a
  // value outside it used to select brains[0] silently - the picker showed a CLI nobody chose.
  const list = coding ? (brain && !brains.includes(brain) ? [brain, ...brains] : brains) : roles;
  const value = coding ? brain : agent;
  // A HAND-OFF LEAVES THE PROFILE IT HAS: blank, and no picker asks (below).
  const handOff = !coding && !!onPick;
  const selected = handOff ? value : (list.includes(value) ? value : (list[0] || value));
  const info = (coding ? brainModels[selected] : models[selected]) || {};
  const chosenBrain = generalBrains.find((b) => b.pick === pick) || {};
  // NO CODING TOOL CHOSEN, SAID IN PLACE OF A BLANK PICKER (owner-approved, 2026-10-21): the picker drew an empty box and the start
  // found a tool on the computer by itself. The server refuses that start too (terminal.start_on_task).
  if (coding && brainsRead && !codingReady) return <NoCodingTool />;
  return (
    <>
      {/* A HAND-OFF NAMES NO PROFILE (the owner, 2026-10-29: "the agent should just say Taskuary but the profile inherits from it" - a
          reservation was being made by "researcher", and "assistant" is no profile they ever made). It runs the profile the task has
          (triage's role, else the assistant's own), behind the scenes; the profiles themselves are kept in Docs -> Profiles. */}
      {!handOff && <Select size="small" value={selected || ""}
        onChange={(e) => (coding ? onBrain : onAgent)(e.target.value)}
        sx={{ fontSize: 12.5, height: size, bgcolor: "#fff", minWidth: 120 }}>
        {list.map((a) => (
          <MenuItem key={a} value={a} sx={{ fontSize: 12.5 }}>
            {a}{coding && brainModels[a] && brainModels[a].installed === false ? " · not installed" : ""}
          </MenuItem>
        ))}
      </Select>}
      {handOff && (
        <Select size="small" displayEmpty value={pick || ""} onChange={(e) => { onPick(e.target.value); onModel(""); }}
          sx={{ fontSize: 12.5, height: size, bgcolor: "#fff", minWidth: 150 }}>
          <MenuItem value="" sx={{ fontSize: 12.5 }}>
            {!generalBrains.length ? "No AI connected" : browser ? "an AI that can use the browser" : "the brain it runs on"}
          </MenuItem>
          {generalBrains.map((b) => <MenuItem key={b.pick} value={b.pick} sx={{ fontSize: 12.5 }}>{b.label}{brainNote(b, browser)}</MenuItem>)}
        </Select>
      )}
      {/* "No AI connected" in the menu, and the button that connects one beside it (owner-approved, 2026-10-21) */}
      {handOff && brainsRead && !generalBrains.length && <ConnectAi variant="outlined" sx={{ height: size }} />}
      <ModelSelect size={size} model={model} onModel={onModel} whose={coding ? "tool" : "agent"}
        info={handOff ? { models: chosenBrain.models, default: chosenBrain.model } : info} />
    </>
  );
};

// "This isn't ours." Says so about THIS item and teaches the classifier at the same time:
// the note is saved to memory, and triage reads it on every later message from that sender.
// Editable before saving, because the reason is the part that has to be right.
// `onLock` tells the panel above to stop following the mouse while this is open: rows shift
// under the cursor during a sync, hover re-selects whatever landed there, and the panel -
// keyed on the selected message - unmounted with the half-typed verdict inside it. That read
// as "Not our task doesn't work while syncing", and nothing said otherwise because the save
// error was swallowed. Both ends are fixed here: the lock, and a visible failure.
export const NotMine = ({ messageId, onDone, onLock, row, first, compact = false }) => {
  const [open, setOpen] = useState(false);
  const [note, setNote] = useState("");
  // no default here on purpose: the server picks the scope this message calls for (a topic when
  // there is a subject to key on) and the panel shows what it picked. "this sender" as a fixed
  // default is what filed "resident refunds are not our task" under one colleague of seventeen.
  const [scope, setScope] = useState("");
  const [topic, setTopic] = useState("");
  const [topicEdited, setTopicEdited] = useState(false);
  const [edited, setEdited] = useState(false);
  const [saved, setSaved] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  useEffect(() => { onLock?.(open && !saved); }, [open, saved, onLock]);
  useEffect(() => () => onLock?.(false), [onLock]);      // unmounted anyway: never leave it locked
  // the suggested wording follows the scope, so the sentence and the dropdown never disagree -
  // but an EDITED note is the owner's own words and is never overwritten
  useEffect(() => {
    if (!open) return;
    api.get(`/api/messages/${messageId}/not-mine/suggest`, { params: { ...(scope ? { scope } : {}), ...(topicEdited ? { topic } : {}) } })
      .then(({ data }) => { setScope((c) => c || data.scope); if (!topicEdited) setTopic(data.topic || ""); if (!edited) setNote(data.note); })
      .catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, messageId, scope]);
  const save = async () => {
    setBusy(true); setErr("");
    try {
      const { data } = await api.post(`/api/messages/${messageId}/not-mine`,
        { note: note.trim() || null, scope: scope || "sender", topic: topic.trim() || null });
      setSaved(data);
      setTimeout(() => onDone?.(), 1400);
    } catch (e) {
      setErr(e?.response?.data?.detail || e?.message || "the verdict did not save — try again");
    }
    setBusy(false);
  };
  if (saved) return (
    <Box sx={row ? { px: 1.25, py: 1 } : undefined}>
      <Typography variant="caption" sx={{ color: "#47654a", fontWeight: 600, display: "block" }}>
        ✓ noted — triage will apply this to{" "}
        {saved.scope === "global" ? "every sender" : saved.scope === "subject" ? `any mail about “${saved.scopeKey}”` : saved.scopeKey}
        {" "}from now on
      </Typography>
      {/* the verdict works from here on; tasks opened BEFORE it are still sitting there, and
          saying nothing about them is how a fix reads as "still not learning" */}
      {!!saved.alsoCovered?.length && (
        <Typography variant="caption" sx={{ color: "#55697a", display: "block", mt: 0.25 }}>
          {plural(saved.alsoCovered.length, "open task")} already match it
          ({saved.alsoCovered.slice(0, 4).map((t) => `TQ-${String(t.taskId).padStart(4, "0")}`).join(", ")}
          {saved.alsoCovered.length > 4 ? ", …" : ""}) — close them the same way if they are not yours either.
        </Typography>
      )}
    </Box>
  );
  if (!open && compact) return (
    <Button size="small" disableElevation startIcon={<PsychologyOutlinedIcon sx={{ fontSize: 16 }} />}
      onClick={() => setOpen(true)} title="Not our responsibility — explain why once so triage remembers"
      sx={{ width: 190, height: 34, px: 1.5, justifyContent: "flex-start", borderRadius: 2,
        textTransform: "none", fontWeight: 600, fontSize: 12, whiteSpace: "nowrap", boxShadow: "none",
        color: "#5a3e83", bgcolor: "#f8f5fc", border: "1px solid #d9cbea",
        "&:hover": { bgcolor: "#f1eafa", borderColor: "#bca3d8", boxShadow: "none" } }}>
      {btnLabel("not_ours")}
      <Box component="span" aria-hidden sx={{ ml: 1, px: 0.65, py: 0.08, borderRadius: 0.8,
        bgcolor: "rgba(90,62,131,.1)", fontSize: 8.5, fontWeight: 600, letterSpacing: 0.7,
        lineHeight: 1.5 }}>MEMORY</Box>
    </Button>
  );
  if (!open) return row ? (
    <ChoiceRow first={first} tint="#e9e3d8" onClick={() => setOpen(true)}
      icon={<BlockIcon sx={{ fontSize: 15, color: "#867f74" }} />}
      label={btnLabel("not_ours")} hint="say why once — triage remembers it for this topic, or this sender" />
  ) : (
    <Button size="small" sx={{ color: "#867f74", fontSize: 11 }} onClick={() => setOpen(true)}
      title="Not our responsibility — and remember why, so triage learns it">{btnLabel("not_ours")}</Button>
  );
  return (
    <Box sx={{ width: "100%", flexBasis: compact ? "100%" : "auto", mt: row ? 0 : 1, p: 1.25, bgcolor: PANEL2,
      border: row ? "none" : `1px solid ${BORDER}`, borderRadius: row ? 0 : 1.5 }}>
      <Typography variant="caption" sx={{ color: DIM, fontWeight: 600, display: "block", mb: 0.5 }}>
        Not our task — what should triage remember?
      </Typography>
      {/* WHAT the verdict is about, in the owner's words. Trimming the subject guesses at the
          standing part ("resident refund request") and drops the changing one (the resident);
          being told beats guessing, and a topic keyed too narrowly is a verdict that fires once. */}
      {scope === "subject" && (
        <Box sx={{ display: "flex", alignItems: "center", gap: 0.75, mb: 0.75 }}>
          <Typography variant="caption" sx={{ color: FAINT, whiteSpace: "nowrap" }}>mail about</Typography>
          <TextField fullWidth size="small" value={topic} sx={{ bgcolor: "#fff" }}
            inputProps={{ style: { fontSize: 12.5, padding: "4px 8px" } }}
            onChange={(e) => { setTopicEdited(true); setTopic(e.target.value); }} />
        </Box>
      )}
      <TextField fullWidth multiline minRows={2} size="small" value={note} sx={{ bgcolor: "#fff" }}
        onChange={(e) => { setEdited(true); setNote(e.target.value); }} />
      <Box sx={{ display: "flex", alignItems: "center", gap: 1, mt: 0.75, flexWrap: "wrap" }}>
        <Select size="small" value={scope || "sender"} onChange={(e) => setScope(e.target.value)}
          sx={{ fontSize: 11.5, height: 26, bgcolor: "#fff" }}>
          {/* the topic first, because a verdict is usually about a KIND OF WORK and whoever
              happens to send it next is not the point */}
          {topic && <MenuItem value="subject" sx={{ fontSize: 12 }}>any mail about this</MenuItem>}
          <MenuItem value="sender" sx={{ fontSize: 12 }}>this sender</MenuItem>
          <MenuItem value="sender_domain" sx={{ fontSize: 12 }}>everyone at their domain</MenuItem>
          <MenuItem value="global" sx={{ fontSize: 12 }}>every sender</MenuItem>
        </Select>
        <Typography variant="caption" sx={{ color: FAINT, flex: 1, minWidth: 120 }}>
          {scope === "subject" && topic
            ? `Matches any mail about “${topic}”, whoever sends it — the changing part of the subject is ignored.`
            : "Their mail keeps arriving — only the verdict is learned."}
        </Typography>
        <Button size="small" sx={{ color: DIM, fontSize: 11 }} onClick={() => setOpen(false)}>Cancel</Button>
        <Button size="small" variant="contained" disableElevation
          disabled={busy || !note.trim() || (scope === "subject" && !topic.trim())} onClick={save}
          sx={{ fontSize: 11.5 }}>{busy ? "saving…" : "Not ours — remember this"}</Button>
      </Box>
      {err && <Typography variant="caption" sx={{ color: ROLES.bad.ink, fontWeight: 600, display: "block", mt: 0.75 }}>
        {err} — your note is still here.
      </Typography>}
    </Box>
  );
};

// One door, then an explicit choice. Triage may suggest which kind fits, but it must not silently
// choose the regular API agent or a coding CLI on the owner's behalf.
export const SendToAgent = ({ messageId, subject, taskKind, onOpenTask, dense, row, first }) => {
  const canCode = useCapabilities().coding;                   // no coding tool connected: no Coding agent, and nothing suggests one (capabilities.js)
  const suggestedKind = canCode && (!taskKind || String(taskKind).toLowerCase() === "coding") ? "coding" : "general";
  const [agentKind, setAgentKind] = useState("");
  const coding = agentKind === "coding";
  const [open, setOpen] = useState(false);
  const { agents, models, kinds, brainList, brainModels } = useAgents();
  const [agent, setAgent] = useState("");          // the coding profile, by kind; blank = the server finds it
  const [brain, setBrain] = useState("");          // WHICH CLI runs it; blank = the brain settings name
  const [model, setModel] = useState("");
  const [prompt, setPrompt] = useState("");
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState(null);
  const [repoAsk, setRepoAsk] = useState(null);     // a repository DECISION, never reported as a start (PW-212)
  const [err, setErr] = useState("");
  useEffect(() => { if (!agents.includes(agent)) setAgent(codingProfile(agents, kinds)); }, [agents, kinds, agent]);
  const send = async () => {
    if (!agentKind) return;
    setBusy(true); setErr("");
    try {
      const { data } = await api.post(`/api/messages/${messageId}/dispatch`,
        { kind: agentKind, agent: coding ? (agent || null) : null, brain: coding ? (brain || null) : null,
          model: model || null, instruction: prompt.trim() || null });
      const outcome = outcomeOf(data);
      if (outcome.state === "needs_repo") { setRepoAsk({ taskId: data.taskId, agent: data.agent || agent }); }
      else {
        setRepoAsk(null); setSent({ ...data, outcome }); setPrompt("");
        onOpenTask?.(data.taskId);          // the session IS the page - go watch it
      }
    } catch (e) { setErr(e?.response?.data?.detail || "Could not reach the agent"); }
    setBusy(false);
  };
  if (repoAsk) return (
    <Box sx={{ mt: 1, p: 1.25, bgcolor: PANEL2, border: `1px solid ${BORDER}`, borderRadius: 1.5 }}>
      <Typography variant="caption" sx={{ color: DIM, fontWeight: 600, display: "block", mb: 0.5 }}>Which repository should the coding agent use?</Typography>
      <RepoPicker taskId={repoAsk.taskId} agent={repoAsk.agent}
        onDone={(data) => { if (data?.repo) { setRepoAsk(null); send(); } }} />
      <Button size="small" sx={{ fontSize: 11, color: DIM }} onClick={() => setRepoAsk(null)}>Not now - nothing was started</Button>
    </Box>
  );
  if (sent) return (
    <Box sx={{ display: "flex", alignItems: "center", gap: 1, mt: dense ? 0.5 : 1 }}>
      <TaskuaryMark size={16} />
      <Typography variant="caption" sx={{ color: "#47654a", fontWeight: 600 }}>
        {sent.outcome?.text || `${sent.agent || "The agent"} is on it in a live session — ${sent.ref}`}
      </Typography>
      <Button size="small" sx={{ fontSize: 11 }} onClick={() => onOpenTask?.(sent.taskId)}>watch it live →</Button>
      <Button size="small" sx={{ fontSize: 11, color: DIM }} onClick={() => setSent(null)}>send another</Button>
    </Box>
  );
  if (!open) return row ? (
    <ChoiceRow first={first} tint="#e3e6e1" onClick={() => setOpen(true)}
      icon={<TaskuaryMark size={17} />}
      label="Send to agent…" hint="choose a coding agent or a regular agent" />
  ) : (
    <Button size="small" disableElevation startIcon={<TaskuaryMark size={15} />}
      onClick={() => setOpen(true)}
      sx={{ width: 190, height: 34, px: 1.5, borderRadius: 2, textTransform: "none", fontSize: 12,
        justifyContent: "flex-start", fontWeight: 600, whiteSpace: "nowrap", color: DIM, bgcolor: PANEL,
        border: `1px solid ${BORDER}`, boxShadow: "none",
        "&:hover": { color: INK, bgcolor: PANEL, borderColor: "#d8cfbe", boxShadow: "none" } }}>
      Send to agent…
    </Button>
  );
  return (
    <Box sx={{ mt: 1, p: 1.25, bgcolor: PANEL2, border: `1px solid ${BORDER}`, borderRadius: 1.5 }}>
      <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 0.75, flexWrap: "wrap" }}>
        <TaskuaryMark size={17} />
        <Typography variant="caption" sx={{ color: DIM, fontWeight: 600 }}>Which kind of agent?</Typography>
        <Box sx={{ flex: 1, minWidth: 8 }} />
        {coding && <AgentPicker agents={agents} models={models} agent={agent} model={model} coding
          brains={brainList} brainModels={brainModels} brain={brain} onBrain={(b) => { setBrain(b); setModel(""); }}
          onAgent={setAgent} onModel={setModel} size={26} />}
      </Box>
      <Box sx={{ display: "flex", gap: 0.75, mb: agentKind ? 0.75 : 0, flexWrap: "wrap" }}>
        {canCode && <Button size="small" variant={agentKind === "coding" ? "contained" : "outlined"} disableElevation
          onClick={() => setAgentKind("coding")}>{choice("agent", "coding_agent")}</Button>}
        <Button size="small" variant={agentKind === "general" ? "contained" : "outlined"} disableElevation
          onClick={() => setAgentKind("general")}>{choice("agent", "regular_agent")}</Button>
      </Box>
      <Typography variant="caption" sx={{ color: FAINT, display: "block", mb: agentKind ? 0.5 : 0 }}>
        Triage tagged this {suggestedKind}; your choice here is what actually runs.
      </Typography>
      {agentKind && <TextField fullWidth multiline minRows={2} size="small" autoFocus value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          placeholder={coding ? `What should it do? e.g. "Find why this failed and fix it, then tell me what changed."`
            : "What should the agent do with this?"}
          sx={{ bgcolor: "#fff" }} />}
      <Box sx={{ display: "flex", alignItems: "center", gap: 1, mt: 0.75 }}>
        <Typography variant="caption" sx={{ color: FAINT, flex: 1, minWidth: 0 }} noWrap>
          it gets the full message{subject ? ` “${subject}”` : ""} + your operator docs as context
        </Typography>
        <Button size="small" sx={{ fontSize: 11, color: DIM }} onClick={() => setOpen(false)}>Cancel</Button>
        <Button size="small" variant="contained" disableElevation disabled={busy || !agentKind} onClick={send}
          startIcon={busy ? <CircularProgress size={11} sx={{ color: "#fff" }} /> : null}
          sx={{ fontSize: 11.5, bgcolor: "#6f8a6e", "&:hover": { bgcolor: "#5b7259" } }}>
          {busy ? "sending…" : btnLabel(agentKind === "coding" ? "coding_agent" : "regular_agent")}
        </Button>
      </Box>
      {err && <Typography variant="caption" sx={{ color: "#6b2733", display: "block", mt: 0.5 }}>{err}</Typography>}
    </Box>
  );
};

/* Task status, review status and run status were three ladders the reader had to combine
   in their head ("in_progress + reviewed·rejected" — so is it mine or not?). This is the
   one answer: what does this task need from ME, right now. Everything shows this. */
// `solid` is the one colour that carries the state on its own - the rail down a list row, a dot.
// The c-triple cannot supply it: needs-you's fg is now the colour of text ON alert, not the alert.
//
// And needs-you finally wears ALERT. theme.jsx has always called it "the needs-you pill" and this
// table handed it the same beige as `queued`, so the single row in the rail that had stopped and
// was waiting on the owner looked exactly like the rows that were merely parked (2026-09-16).
export const TASK_STATES = [
  { key: "needs_you", label: WORD.blocked, solid: ALERT, c: { bg: ALERT, fg: "#fffdfb", bd: ALERT } },
  { key: "working", label: WORD.working, solid: "#6f8a6e", c: { bg: "#e3e6e1", fg: "#6f8a6e", bd: "#d2d6cf" } },
  { key: "queued", label: WORD.queued, solid: "#a09787", c: { bg: "#eae4d8", fg: "#55697a", bd: "#d8cfbe" } },
  { key: "done", label: WORD.closed, solid: "#47654a", c: { bg: "#dfeade", fg: "#47654a", bd: "#c8d9c7" } },
  { key: "dropped", label: WORD.dropped, solid: "#a09787", c: { bg: "#e9e3d8", fg: "#867f74", bd: "#e1dcd5" } },
];
const ST = Object.fromEntries(TASK_STATES.map((x) => [x.key, x]));
// A CLI that has printed nothing for this long is parked at its own prompt - the next move
// is yours, not its. Thinking agents print constantly; a question is silence.
export const IDLE_WAITING = 45;
// `waiting` is the server's verdict (the CLI's own screen, silence as fallback); older rows
// without it fall back to the clock here
export const isWaiting = (s) => (s?.waiting ?? (s?.idle >= IDLE_WAITING));
// How long a parked agent has been holding its question - "asked you 5m ago". The row already carries the session that stateOf()
// reads, so this costs nothing, and a question left for an hour should say so on the rail rather than only inside the task. The task
// list and the task page each typed this once (2026-10-18).
export const askedAgo = (t) => (t?.Session && isWaiting(t.Session) ? `asked you ${agoMins((Number(t.Session.idle) || 0) / 60)}` : "");
// A LIVE SESSION SPEAKS FOR ITSELF. The run row says `running` for as long as the pty is up,
// including while the CLI sits at its prompt waiting for an answer - so the rail read "agent
// working" on TQ-0004 while the page header, the Wall and the toast all said the agent had
// stopped and was waiting (2026-09-18). The run row decides only when there is no session to ask.
export const busyNow = (t) => (t?.Session?.alive ? !isWaiting(t.Session) : t?.RunStatus === "running");
// The ladder, top down: dropped, done, an agent is ACTUALLY running it, else it is yours.
// "in_progress with nothing running" used to read as "agent working" - a task whose agent
// finished without closing it then sat there looking busy and nobody was told.
// THE RAIL SAYS WHAT THE WORK RAIL SAYS. Everything that was not done, dropped or busy fell
// through to ONE red "needs you", so an agent parked on a question and a reply waiting for your
// yes wore the identical chip - two different moves, one word (the owner, 2026-09-22: "right now
// it has tags needs you, which is agent stopped but now you are going to move that to reply
// needed... just keep the same tags in in progress like in work").
// The words come from taskuary/lanes.json, the one vocabulary the Work rail, chat and the
// Timeline already build their tables from, so this rail cannot invent a fourth one.
const taskLane = (t) => {
  if (t.Session?.alive) return isWaiting(t.Session) ? "blocked" : "working";
  if (t.RunStatus === "running") return "working";
  if (t.RunStatus === "error") return "broken";        // it failed: your move, never back to queued
  if (t.ReviewStatus === "pending") return "approve";  // a reply, or an action, waits for your yes
  return "yours";                                      // real work with nobody on it
};
const laneState = (lane) => {
  const m = laneMeta(lane), c = ROLES[m.role || "muted"];
  return { key: lane, label: m.word, solid: c.solid, c: { bg: c.tint, fg: c.ink, bd: c.bd } };
};
// THE SERVER'S STATE WINS (taskstate.py, T1-T9): one rule for the list and the Board, the rail's own. `key` stays the
// bucket the list files it under - a closed task, the agent's or yours, is done; a continued one is live work again.
const fromServer = (k) => {
  if (k === "closed") return ST.done;
  if (k === "dropped") return ST.dropped;
  const m = taskStateMeta(k);
  if (!m) return null;
  const c = ROLES[m.role || "muted"];
  return { key: k === "agentdone" ? "done" : k, state: k, label: m.word, mark: m.mark,
    solid: c.solid, c: { bg: c.tint, fg: c.ink, bd: c.bd } };
};
export const stateOf = (t) => {
  if (!t) return ST.queued;
  const server = t.State && fromServer(t.State);
  if (server) return server;
  if (t.Status === "dropped") return ST.dropped;
  if (t.Status === "done") return ST.done;
  return laneState(taskLane(t));
};
export const StateChip = ({ task }) => {
  const st = stateOf(task);
  // the rail's mark leads the word, as it does on the rail (⏳ waiting to start, 👋 agent waiting on you)
  return <Chip size="small" label={st.mark && st.mark !== "spinner" ? `${st.mark} ${st.label}` : st.label}
    sx={{ bgcolor: st.c.bg, color: st.c.fg, border: `1px solid ${st.c.bd}`, height: 19, fontSize: 10.5, fontWeight: 600 }} />;
};

export const TaskStatusChip = ({ status }) => (
  <Chip size="small" label={String(status || "").replace(/_/g, " ")} sx={{ bgcolor: "transparent", border: `1px solid ${TASK_STATUS_COLORS[status] || "#a9a294"}55`,
    color: TASK_STATUS_COLORS[status] || "#a9a294", height: 19, fontSize: 10.5 }} />
);

const LC = {
  neutral: { bg: "#f4f1ec", fg: "#55697a", bd: "#d8cfbe" },
  working: { bg: "#e3e6e1", fg: "#526b55", bd: "#cbd5c9" },
  you: { bg: "#e3eadf", fg: "#3f5943", bd: "#c4d2c0" },          // on you is sage, the palette's (2026-10-06), not oxblood
  // theme.jsx has always called ALERT "the needs-you pill" and this wore the tint instead - the
  // same weight as four calmer phases, so the one state where work has STOPPED until the owner
  // answers read like the rest (the owner, 2026-09-11: "make the needs you a little redder").
  needsYou: { bg: "#5f7a5f", fg: "#fffdfb", bd: "#5f7a5f" },  // ...solid, as the On you pill is
  done: { bg: "#dfeade", fg: "#47654a", bd: "#c8d9c7" },
  reply: { bg: "#f1ead9", fg: "#765f38", bd: "#ded0ad" },
  bad: { bg: ROLES.bad.tint, fg: ROLES.bad.ink, bd: ROLES.bad.bd },
};

const lifecycleColor = (kind, phase) => {
  const value = String(phase || "");
  if (value === AGENT.waiting) return LC.needsYou;        // an agent blocked on you, and only that
  if (value === NOT_SENT) return LC.bad;                  // a refused send is a failure, never the green of ready
  if (value === READY || value === "approval needed" || value === "ready") return LC.you;
  if (value === AGENT.working || value === "in progress") return LC.working;
  if (value === "done" || value === "sent" || value === AGENT.saved || value === AGENT.finished) return LC.done;
  if (kind === "reply") return LC.reply;
  return LC.neutral;
};

// Always name the state machine. A naked "done" beside an active terminal was the original
// ambiguity: the task can be done while an agent is stopped and a reply is still unsent.
export const LifecycleChip = ({ kind, phase, compact = false, sx = {} }) => {
  const c = lifecycleColor(kind, phase);
  // ...unless the phase names it already: "agent · agent working" says it twice
  return <Chip size="small" label={String(phase || "").startsWith(kind) ? phase : `${kind} · ${phase}`}
    sx={{ bgcolor: c.bg, color: c.fg, border: `1px solid ${c.bd}`, height: compact ? 17 : 20,
      fontSize: compact ? 11 : 11.5, fontWeight: 500, "& .MuiChip-label": { px: compact ? 0.7 : 0.9 }, ...sx }} />;
};

// a stamp's age read in the server's zone (asUtc), said by the one rule (timeWords.ago)
export const timeAgo = (s) => (s ? ago(asUtc(String(s))) : "");

// Bodies arrive as HTML (email) or oddly-spaced stripped text - make them readable.
// A MAIL SYSTEM'S EXTERNAL-SENDER BANNER is not something anybody said (the owner, 2026-09-23: "this email ... template of all
// emails should be removed from everywhere") - and which text is one is the model's word, never a phrase list here (2026-10-28):
// triage names it (its verdict's `wrapper`) and the server leaves it out of ReadText, what every screen shows.
// the line Taskuary writes over a GitHub/Asana/monday item for TRIAGE ("[pull request by X - association: Y]") is
// evidence for the judge, never what they said - remote_assistant.PROVENANCE is the same rule for the phone
export const PROVENANCE = /^\s*\[(?:pull request|issue) by [^\]\n]*\]\s*|^\s*\[(?:Asana task|Monday item)[^\]\n]*\]\s*/i;
export const cleanText = (s) => keepAddresses(s).replace(PROVENANCE, "").replace(/<(style|script|head)[^>]*>[\s\S]*?<\/\1>/gi, " ")
  .replace(/<[^>]+>/g, " ").replace(/&nbsp;|&#\d+;|&\w+;/g, " ")
  .replace(/[^\S\n]+/g, " ").replace(/ ?\n ?/g, "\n").replace(/\n{3,}/g, "\n\n").trim();
// a mail's text with its addresses as links (mailLinks.js), each opened in a new tab
export const LinkedText = ({ text }) => linkParts(text).map((p, i) => p.href
  ? <a key={i} href={p.href} target="_blank" rel="noopener noreferrer" style={{ color: "#55697a", overflowWrap: "anywhere" }}>{p.text}</a>
  : <React.Fragment key={i}>{p.text}</React.Fragment>);

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

// The time helpers live in dates.js, where each formatter is built once (2026-10-19); these are the names every screen imports.
export { asUtc, tzLabel, fmtTime12, tsMs, fmtDateTime, localDay, tzNow } from "./dates.js";
export const loadTz = (settings) => { setTz((settings.find((s) => s.Name === "timezone") || {}).Value || ""); };
api.get("/api/settings").then(({ data }) => loadTz(data.data || [])).catch(() => {});   // once per page load

// ── Stripe-style two-level navigation atoms (Settings/Docs/Connectors share these) ──
export const Crumb = ({ section, onBack, title }) => (
  <Box sx={{ mb: 2.5 }}>
    <Typography variant="caption" onClick={onBack}
      sx={{ color: "#55697a", fontWeight: 600, cursor: "pointer", "&:hover": { textDecoration: "underline" } }}>
      {section}
    </Typography>
    <Typography sx={{ color: "#2b2a26", fontWeight: 600, fontSize: 20, lineHeight: 1.2, mt: 0.25 }}>{title}</Typography>
  </Box>
);

/* The Docs/Settings shell, lifted out so every tab that has sections wears it: a sticky rail
   on the left, the open section beside it. Connectors and Reports were the last two opening on
   a full-width wall - the layout the rest of the app stopped using - so a search and a section
   list are here rather than copied twice more. `right` renders above the section content, for
   the actions a tab keeps on screen (Sync now, New report). */
export const SideRail = ({ title, note, items, value, onChange, q, setQ, placeholder, children }) => (
  <Box sx={{ display: "grid", gridTemplateColumns: { xs: "minmax(0, 1fr)", md: "236px minmax(0,1fr)" },
    gap: 3, alignItems: "start", maxWidth: 1320, mx: "auto" }}>
    <Box sx={{ position: { md: "sticky" }, top: { md: 62 } }}>
      <Typography sx={{ color: INK, fontWeight: 600, fontSize: 16, mb: 1.5 }}>{title}</Typography>
      {setQ && (
        <TextField fullWidth placeholder={placeholder} value={q} onChange={(e) => setQ(e.target.value)}
          sx={{ mb: 1.5, bgcolor: "#fff", borderRadius: 2 }}
          InputProps={{ startAdornment: <InputAdornment position="start"><SearchIcon sx={{ fontSize: 17, color: FAINT }} /></InputAdornment> }} />
      )}
      {items.map((it) => {
        if (it.section) return (
          <Typography key={`section-${it.section}`} variant="overline"
            sx={{ display: "block", color: ACCENT2, letterSpacing: 1.35, fontWeight: 600,
              fontSize: 9.5, px: 1.25, mt: it.first ? 0 : 1.6, mb: 0.3 }}>
            {it.section}
          </Typography>
        );
        const key = it.key ?? it, on = !q && value === key;
        return (
          <Box key={key} onClick={() => { setQ?.(""); onChange(key); }}
            sx={{ display: "flex", alignItems: "center", gap: 1, px: 1.25, height: 34, borderRadius: 1.75,
              cursor: "pointer", fontSize: 12.5, fontWeight: on ? 600 : 400,
              color: on ? "#41525f" : DIM, bgcolor: on ? "#eae4d8" : "transparent",
              "&:hover": { bgcolor: on ? "#eae4d8" : "#f4f1ec" } }}>
            <Box sx={{ flex: 1, minWidth: 0, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
              {it.label ?? it}
            </Box>
            {it.n != null && <Typography variant="caption" sx={{ color: FAINT, fontSize: 10.5 }}>{it.n}</Typography>}
          </Box>
        );
      })}
      {note && <Typography variant="caption" sx={{ color: FAINT, display: "block", pt: 2, px: 1.25, lineHeight: 1.6 }}>{note}</Typography>}
    </Box>
    <Box sx={{ minWidth: 0 }}>{children}</Box>
  </Box>
);

export const UnderTabs = ({ tabs, value, onChange }) => (
  <Box sx={{ display: "flex", gap: 2.5, borderBottom: "1px solid #e1dcd5", mb: 2, flexWrap: "wrap" }}>
    {tabs.map((t) => (
      <Box key={t} onClick={() => onChange(t)}
        sx={{ pb: 1, cursor: "pointer", fontSize: 13, fontWeight: 600, mb: "-1px", flexShrink: 0,
          color: value === t ? "#55697a" : DIM,
          borderBottom: `2px solid ${value === t ? "#55697a" : "transparent"}`,
          "&:hover": { color: "#2b2a26" } }}>
        {t}
      </Box>
    ))}
  </Box>
);

// `foot` is a line UNDER the description that is not part of the card's click (an Install
// button there must not also open the card's form)
export const LandingCard = ({ icon, title, desc, onOpen, foot }) => (
  <Box onClick={onOpen} sx={{ display: "flex", gap: 1.5, cursor: "pointer", alignItems: "flex-start",
    "&:hover .thubPgTitle": { textDecoration: "underline" } }}>
    <Box sx={{ width: 38, height: 38, borderRadius: 2, bgcolor: "#fff", border: "1px solid #e1dcd5",
      display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0,
      boxShadow: "0 1px 2px rgba(30,50,38,.05)" }}>
      {icon}
    </Box>
    <Box sx={{ minWidth: 0 }}>
      <Typography className="thubPgTitle" sx={{ color: "#55697a", fontWeight: 600, fontSize: 14.5, lineHeight: 1.3 }}>{title}</Typography>
      <Typography variant="body2" sx={{ color: DIM, mt: 0.25 }}>{desc}</Typography>
      {foot && <Box onClick={(e) => e.stopPropagation()}>{foot}</Box>}
    </Box>
  </Box>
);

export const SectionLabel = ({ children, right }) => (
  <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", mb: 1, mt: 2 }}>
    <Typography variant="overline" sx={{ color: ACCENT2, letterSpacing: 1.5, fontWeight: 600, fontSize: 10 }}>{children}</Typography>
    {right}
  </Box>
);

export const Empty = ({ children }) => (
  <Typography variant="body2" sx={{ color: FAINT, py: 3, textAlign: "center" }}>{children}</Typography>
);

export const scoreBar = (v) => (
  <Tooltip title={v?.toFixed ? v.toFixed(2) : v}>
    <Box sx={{ width: 54, height: 4, bgcolor: PANEL2, border: "1px solid #e1dcd5", borderRadius: 3, overflow: "hidden", display: "inline-block", mr: 1 }}>
      <Box sx={{ width: `${Math.min(100, (v || 0) * 100)}%`, height: "100%", bgcolor: "#55697a" }} />
    </Box>
  </Tooltip>
);

// Compact filter pill row used across views.
// Segmented control: one contained housing, obviously interactive; the active segment
// fills with its muted color pair {bg, fg, bd} (indigo default), the rest stay quiet.
// Screenshots on a prompt box, wherever there is one. A pty carries text only, so the image
// goes to disk when you send and the NOTE names the file - a coding CLI reads images from a
// path (Claude Code's Read does), which is how it gets to see what you pasted. Shared, because
// "paste a screenshot" that works in one prompt box and silently does nothing in the next is
// the bug: the Wall's queue had it, the New task dialog did not.
export const usePromptImages = () => {
  const [imgs, setImgs] = React.useState([]);
  const add = (files) => setImgs((s) => [...s, ...[...(files || [])].filter((f) => f && /^image\//.test(f.type))
    .map((f) => ({ id: Math.random().toString(36).slice(2), file: f, url: URL.createObjectURL(f) }))]);
  const onPaste = (e) => {
    const files = [...(e.clipboardData?.items || [])].filter((i) => i.kind === "file" && /^image\//.test(i.type)).map((i) => i.getAsFile()).filter(Boolean);
    if (!files.length) return;
    e.preventDefault(); add(files);
  };
  const drop = (id) => setImgs((s) => { const g = s.find((x) => x.id === id); if (g) URL.revokeObjectURL(g.url); return s.filter((x) => x.id !== id); });
  const clear = () => setImgs((s) => { s.forEach((x) => URL.revokeObjectURL(x.url)); return []; });
  // needs a task to hang them on, so this runs after the task exists; returns the sentence
  // that names the saved files, to be joined onto the prompt the agent is seeded with.
  const upload = async (taskId) => {
    const paths = [];
    for (const im of imgs) paths.push((await api.post(`/api/tasks/${taskId}/waitroom/image`, im.file, { headers: { "Content-Type": im.file.type } })).data.path);
    if (!paths.length) return "";
    return `${paths.length === 1 ? "Pasted image - open it with your image/Read tool:" : "Pasted images - open them with your image/Read tool:"} ${paths.map((x) => `"${x}"`).join(" ")}`;
  };
  return { imgs, add, onPaste, drop, clear, upload };
};

// The pasted screenshots, as a strip of thumbnails under the box they were pasted into.
export const PromptThumbs = ({ imgs, onDrop, h = 40, note = true }) => !imgs.length ? null : (
  <Box sx={{ display: "flex", gap: 0.75, flexWrap: "wrap", alignItems: "center", mt: 0.5 }}>
    {imgs.map((im) => (
      <Box key={im.id} sx={{ position: "relative" }}>
        <Box component="img" src={im.url} alt="" sx={{ height: h, borderRadius: 0.75, border: "1px solid #ddd2b9", display: "block" }} />
        <Box component="button" type="button" onClick={() => onDrop(im.id)} aria-label="Remove this image" sx={{ position: "absolute", top: -5, right: -5, width: 14, height: 14, borderRadius: 99,
          bgcolor: "#6b5f45", color: "#fff", fontSize: 9, lineHeight: "14px", textAlign: "center", cursor: "pointer", border: 0, p: 0 }}>×</Box>
      </Box>
    ))}
    {note && <Typography variant="caption" sx={{ color: "#6b5f45", fontSize: 10 }}>
      {imgs.length === 1 ? "goes with the prompt, as a file the agent opens" : `${imgs.length} images go with the prompt`}
    </Typography>}
  </Box>
);

// THE WAITING ROOM, as a box you can type into from anywhere a task shows. What you think of
// while the agent works goes in here and is typed into its session as one batch the moment it
// stops - never mid-turn, never on top of a question it is waiting on you to answer. The same
// box on the task page, on a Board card and in the Timeline's funnel bar, so the idea goes
// where you are instead of you going to find the room.
export const TellAgent = ({ taskId, taskRef, compact = false, onQueued }) => {
  const [wait, setWait] = React.useState({ data: [], state: null });
  const [text, setText] = React.useState("");
  const [flash, setFlash] = React.useState("");
  // a refusal is not a hint: in compact it was grey placeholder text in an empty box, read as the box's own suggestion
  const [fail, setFail] = React.useState("");
  const failed = (s) => { setFail(s); setTimeout(() => setFail(""), 8000); };
  const [many, setMany] = React.useState(false);      // paste a list: one prompt per line, queued in order
  const { imgs, onPaste, drop: dropImg, clear: dropImgs, upload: uploadImgs } = usePromptImages();
  const [showQ, setShowQ] = React.useState(false);    // Wall badge peeks at the queue, then folds itself away
  const peekTimer = React.useRef(null);
  const load = React.useCallback(async () => {
    if (!taskId) return;
    try { setWait((await api.get(`/api/tasks/${taskId}/waitroom`)).data); } catch { setWait({ data: [], state: null }); }
  }, [taskId]);
  React.useEffect(() => { load(); return onLive("task-changed", (ev) => { if (touches(ev, taskId)) load(); }); }, [load, taskId]);
  React.useEffect(() => () => clearTimeout(peekTimer.current), []);
  const lines = text.split("\n").map((l) => l.replace(/^\s*(?:[-*•]|\d+[.)])\s*/, "").trim()).filter(Boolean).length;
  const queue = async () => {
    if (!text.trim() && !imgs.length) return;
    try {
      const ref = await uploadImgs(taskId);
      const body = [text.trim(), ref].filter(Boolean).join(many ? "\n" : " ");
      const { data } = many
        ? await api.post(`/api/tasks/${taskId}/waitroom/bulk`, { text: body })
        : await api.post(`/api/tasks/${taskId}/waitroom`, { text: body });
      dropImgs(); setText(""); setMany(false);
      if (many) { setFlash(`${data.queued} prompts queued — they drip in one per stop`); setTimeout(() => setFlash(""), 5000); load(); onQueued?.(data); return; }
      // words that name none of a chooser's options are kept, not typed into it - say why, not "queued" (B12)
      if (data.state === "not_a_choice") { failed(`Kept, not sent - ${data.why}`); load(); onQueued?.(data); return; }
      setFlash(data.delivered ? (data.state === "restarted" ? "session reopened with it" : "typed in — the agent was parked") : "queued — goes in when the agent stops");
      setTimeout(() => setFlash(""), 4000);
      load(); onQueued?.(data);
    } catch (e) { failed(`Not sent - ${e?.response?.data?.detail || "Taskuary didn't answer"}. Your words are still in the box; try again.`); }
  };
  const pending = wait.data.filter((w) => !w.DeliveredAt);
  const peekQueue = () => {
    if (!pending.length) return;
    clearTimeout(peekTimer.current); setShowQ(true);
    peekTimer.current = setTimeout(() => setShowQ(false), 3000);
  };
  const stateLine = wait.state === "working" ? "agent is working — this waits for its next stop"
    : wait.state === "asking" ? "agent is asking you something — what you write here IS the answer, and goes in at once"
    : wait.state === "parked" ? "agent is parked — this goes straight in"
    : wait.state === "no_session" ? "no live session — this reopens one with your note as the ask" : "";
  // compact has no room for a header line, so the placeholder carries the state instead
  const straight = ["asking", "parked", "no_session"].includes(wait.state), verb = straight && !many ? "Send" : "Queue";
  const ph = many ? "One prompt per line — twenty is fine. Bullets and numbers are stripped; they drip in one per stop, in this order."
    : !compact ? "Anything you think of while it works — queued, typed in when it stops. Enter to queue, Shift+Enter for a new line. Paste a screenshot to send it along."
    : wait.state === "asking" ? "It is asking — answer here and it goes straight in"
    : wait.state === "parked" ? "Tell the agent — goes straight in. Enter to send, paste a screenshot to attach it"
    : wait.state === "no_session" ? "Tell the agent — reopens a session with this as the ask"
    : "Tell the agent — queued, typed in when it stops. Enter to send, paste a screenshot to attach it";
  const input = (
    <TextField fullWidth multiline minRows={many ? 6 : 1} maxRows={many ? 14 : (compact ? 1 : 5)} size="small" value={text}
      placeholder={compact && flash ? flash : ph}
      onChange={(e) => setText(e.target.value)} onPaste={onPaste}
      onKeyDown={(e) => { if (!many && e.key === "Enter" && !e.shiftKey) { e.preventDefault(); queue(); } }}
      sx={{ bgcolor: "#fffdfb", "& .MuiInputBase-input": { fontSize: compact ? 11.5 : 12.5 },
        ...(compact ? { "& .MuiInputBase-root": { py: "3px", px: 1 } } : {}) }} />
  );
  const thumbs = <PromptThumbs imgs={imgs} onDrop={dropImg} h={compact ? 28 : 40} />;
  const queueRows = pending.map((w, i) => (
        <Box key={w.WId} sx={{ display: "flex", gap: 0.75, alignItems: "baseline" }}>
          <Typography variant="caption" sx={{ ...mono, color: "#6b5f45", fontSize: 9.5, flexShrink: 0 }}>{i + 1}.</Typography>
          <Typography variant="body2" noWrap={compact} title={w.Note}
            sx={{ fontSize: compact ? 11 : 11.5, flex: 1, minWidth: 0, whiteSpace: compact ? "nowrap" : "pre-wrap", color: INK }}>{w.Note}</Typography>
          <Typography variant="caption" onClick={async () => {
              try { await api.delete(`/api/tasks/${taskId}/waitroom/${w.WId}`); } catch { failed("Couldn't withdraw it - it may already have gone in."); }
              load(); }}
            sx={{ color: FAINT, cursor: "pointer", fontSize: 10, "&:hover": { color: "#8a3646" } }}>withdraw</Typography>
        </Box>
  ));
  // The full task page keeps the durable queue list open. The Wall gets the same list only as a
  // three-second overlay, so checking it never changes the terminal's geometry.
  const queued = !compact && pending.length > 0 && (
    <Box sx={{ mt: 0.5, display: "flex", flexDirection: "column", gap: 0.25 }}>
      {queueRows}
    </Box>
  );
  // Compact (the Wall): exactly one fixed-height row. The corner badge is the only queue-size
  // change; clicking it briefly overlays the list without moving or resizing the terminal.
  if (compact) {
    return (
      <Box sx={{ position: "relative", height: 40 }}>
        {fail && (
          <Box role="alert" sx={{ position: "absolute", zIndex: 6, left: 0, right: 0, bottom: "calc(100% + 4px)", bgcolor: "#f3e7e9",
            border: "1px solid #8a364655", borderRadius: 1.5, px: 1, py: 0.5 }}>
            <Typography variant="caption" sx={{ color: "#8a3646", fontSize: 11 }}>{fail}</Typography>
          </Box>
        )}
        {showQ && pending.length > 0 && (
          <Box sx={{ position: "absolute", zIndex: 5, left: 0, right: 0, bottom: "calc(100% + 4px)",
            maxHeight: 104, overflowY: "auto", display: "flex", flexDirection: "column", gap: 0.3,
            bgcolor: "#fffdfb", border: "1px solid #ddd2b9", borderRadius: 1.5, p: 0.75,
            boxShadow: "0 5px 16px rgba(60,50,35,.14)" }}>
            {queueRows}
          </Box>
        )}
        <Box sx={{ height: 40, boxSizing: "border-box", overflow: "hidden", bgcolor: "#f1ead9",
          border: "1px solid #ddd2b9", borderRadius: 1.5, px: 0.75, py: 0.45 }}>
          <Box sx={{ height: "100%", display: "flex", alignItems: "center", gap: 0.5 }}>
          <Box title={pending.length ? `${plural(pending.length, "prompt")} waiting to go in — click to peek for 3 seconds; open the full task to withdraw them` : stateLine}
            onClick={peekQueue}
            sx={{ position: "relative", display: "flex", alignItems: "center", justifyContent: "center",
              width: 20, height: 24, color: "#6b5f45", flexShrink: 0, userSelect: "none",
              cursor: pending.length ? "pointer" : "default" }}>
            <Typography sx={{ ...mono, fontSize: 11, fontWeight: 600, color: "inherit" }}>✎</Typography>
            {pending.length > 0 && (
              <Box sx={{ position: "absolute", top: -4, right: -5, minWidth: 14, height: 14, px: 0.3,
                display: "flex", alignItems: "center", justifyContent: "center", borderRadius: 99,
                bgcolor: "#6b5f45", color: "#fffdfb", border: "1px solid #f1ead9",
                ...mono, fontSize: 8, fontWeight: 600, lineHeight: 1 }}>
                {pending.length > 99 ? "99+" : pending.length}
              </Box>
            )}
          </Box>
          {input}
          {imgs.length > 0 && (
            <Tooltip title={`${plural(imgs.length, "image")} attached — click to remove`}>
              <Box component="button" onClick={dropImgs}
                sx={{ ...mono, height: 24, px: 0.6, borderRadius: 1, border: "1px solid #ddd2b9",
                  bgcolor: "#fffdfb", color: "#6b5f45", cursor: "pointer", fontSize: 9.5, whiteSpace: "nowrap" }}>
                ▧ {imgs.length} ×
              </Box>
            </Tooltip>
          )}
          <MicButton size={15} sx={{ color: "#6b5f45", p: 0.25 }} onText={(t) => setText((s) => (s.trim() ? `${s.trimEnd()} ${t}` : t))} />
          <Button size="small" variant="contained" disableElevation onClick={queue} disabled={!text.trim() && !imgs.length}
            sx={{ bgcolor: "#8a7a5c", "&:hover": { bgcolor: "#6b5f45" }, minWidth: 0, px: 1, py: 0.2, fontSize: 11, lineHeight: 1.4, whiteSpace: "nowrap" }}>{verb}</Button>
          </Box>
        </Box>
      </Box>
    );
  }
  return (
    <Box sx={{ bgcolor: "#f1ead9", border: "1px solid #ddd2b9", borderRadius: 2, p: 1.25 }}>
      <Box sx={{ display: "flex", alignItems: "center", gap: 0.75, mb: 0.5 }}>
        <Typography sx={{ ...mono, fontSize: 9.5, letterSpacing: 1, color: "#6b5f45", fontWeight: 600 }}>
          ✎ TELL THE AGENT{taskRef ? ` · ${taskRef}` : ""}{pending.length ? ` · ${pending.length} waiting to go in` : ""}
        </Typography>
        <Box sx={{ flex: 1 }} />
        {stateLine && <Typography variant="caption" sx={{ color: "#6b5f45", fontSize: 10.5 }}>{stateLine}</Typography>}
        <Typography variant="caption" onClick={() => setMany((m) => !m)}
          sx={{ color: "#6b5f45", fontSize: 10.5, cursor: "pointer", textDecoration: "underline", ml: 1 }}>
          {many ? "one note" : "paste a list"}
        </Typography>
      </Box>
      <Box sx={{ display: "flex", gap: 1 }}>
        {input}
        <MicButton sx={{ alignSelf: "flex-end", color: "#6b5f45" }} onText={(t) => setText((s) => (s.trim() ? `${s.trimEnd()} ${t}` : t))} />
        <Button size="small" variant="contained" disableElevation onClick={queue} disabled={!text.trim() && !imgs.length}
          sx={{ alignSelf: "flex-end", bgcolor: "#8a7a5c", "&:hover": { bgcolor: "#6b5f45" }, whiteSpace: "nowrap" }}>
          {many ? `Queue ${lines || ""} prompt${lines === 1 ? "" : "s"}` : verb}</Button>
      </Box>
      {thumbs}
      {flash && <Typography variant="caption" sx={{ color: "#47654a", display: "block", mt: 0.5 }}>{flash}</Typography>}
      {fail && <Typography variant="caption" role="alert" sx={{ color: "#8a3646", display: "block", mt: 0.5 }}>{fail}</Typography>}
      {queued}
      {wait.data.some((w) => w.DeliveredAt) && (
        <Typography variant="caption" sx={{ color: FAINT, display: "block", mt: 0.5 }}>
          {plural(wait.data.filter((w) => w.DeliveredAt).length, "earlier note")} already typed in.
        </Typography>
      )}
    </Box>
  );
};

// The same box behind one button, for places with no room for it (a Board card, the funnel bar).
export const TellAgentButton = ({ taskId, taskRef, count = 0, small = false }) => {
  const [open, setOpen] = React.useState(false);
  const show = (e) => { e.stopPropagation(); setOpen(true); };
  const label = count ? `${count} waiting` : "Tell the agent";
  return (
    <>
      {small ? (
        <Box component="span" onClick={show} title="Tell the agent something — queued until it stops"
          sx={{ display: "inline-flex", alignItems: "center", gap: 0.4, px: 0.6, py: 0.15, borderRadius: 99, cursor: "pointer",
            bgcolor: "#f1ead9", color: "#6b5f45", border: "1px solid #ddd2b9", fontSize: 9.5, fontWeight: 600, whiteSpace: "nowrap",
            "&:hover": { bgcolor: "#e9dfc5" } }}>
          ✎ {label}
        </Box>
      ) : (
        <Button size="small" disableElevation onClick={show} title="Tell the agent something — queued until it stops"
          startIcon={<Box component="span" aria-hidden sx={{ fontSize: 13, lineHeight: 1 }}>✎</Box>}
          sx={{ width: 190, height: 34, px: 1.5, justifyContent: "flex-start", borderRadius: 2,
            textTransform: "none", fontSize: 12, fontWeight: 600, whiteSpace: "nowrap", color: DIM, bgcolor: PANEL,
            border: `1px solid ${BORDER}`, boxShadow: "none",
            "&:hover": { color: INK, bgcolor: PANEL, borderColor: "#d8cfbe", boxShadow: "none" } }}>
          {label}
        </Button>
      )}
      <Dialog open={open} onClose={(e) => { e?.stopPropagation?.(); setOpen(false); }} maxWidth="sm" fullWidth PaperProps={{ sx: { borderRadius: 3, p: 1.5 }, onClick: (e) => e.stopPropagation() }}>
        <TellAgent taskId={taskId} taskRef={taskRef} />
      </Dialog>
    </>
  );
};

// The agent's live session as a black console - the same peephole the Board cards wear, so
// "the agent is working this now" is a thing you can SEE moving, not a sentence. Last lines of the
// terminal, the files it has modified, a blinking cursor while it works and a pause mark when
// it has stopped and is waiting on you. Click opens the task's real terminal.
const _elapsed = (since) => (since ? durSince(since) : "");
/* ── Said and did: what the agent HOLDS, in the terminal's own colours ─────────────────────
   The Board pane used to show two raw trace lines - nobody read them. This is the same dark pane
   with lines a person checks: the tool in hand (agent · tool · file · seconds), the agent's own
   list with the current item lit, the files it has written hottest first. Fed by /api/runs/live
   -> session.work (taskuary/witness.py: Claude hooks, Codex rollout, git). A pane always says
   which rung it stands on: tool line -> last screen line -> files only. Red is spent on exactly
   one thing: a file written after the agent said done. ── */
const fileName = (p) => String(p || "").split(/[\\/]/).pop();
const secsAgo = (at) => (at ? durSince(at) : "");
const isHot = (at) => at && Date.now() - new Date(String(at).replace(" ", "T")) < 20000;
// up to `max` list lines: everything when it fits; otherwise the current item with what is around it
const todoWindow = (todos, max = 4) => {
  if (todos.length <= max) return { rows: todos, hidden: 0 };
  const i = Math.max(0, todos.findIndex((t) => t.status === "now"));
  const start = Math.max(0, Math.min(i - 1, todos.length - max));
  return { rows: todos.slice(start, start + max), hidden: todos.length - max, before: start };
};
const TERM_MARK = { done: "✓", now: "▸", todo: "○" };
const TERM_TONE = { done: CATPPUCCIN.faint, now: CATPPUCCIN.yellow, todo: CATPPUCCIN.faint };

// the one header line, shared by the pane and the compact WorkLine
const workHead = (work, who, waiting, asking, startedAt, promptPending = false, state = "", detail = "") => {
  if (promptPending) return { tone: CATPPUCCIN.yellow, mark: "▮", text: who,
    tool: "prompt sent · waiting for first response", t: startedAt ? secsAgo(startedAt) : "", blink: true };
  // the ONE sentence for the state (laneSays): a stall reads "stuck", never "asked you"; the request's words ride in the tool slot
  if (waiting) return { tone: CATPPUCCIN.yellow, mark: "⏸", text: says(state || (asking ? "asking" : "parked"), who), tool: String(detail || "").slice(0, 120), t: "" };
  // a tool that FAILED (the PostToolUseFailure hook) shows its failure where a running tool shows its name
  if (work?.tool?.name) return { tone: work.tool.error ? CATPPUCCIN.red : CATPPUCCIN.cyan, mark: work.tool.error ? "✗" : "▮", text: who,
    tool: `${work.tool.name} ${fileName(work.tool.target) || work.tool.target || ""}${work.tool.error ? ` — failed: ${work.tool.error}` : ""}`.trim(), t: secsAgo(work.tool.at), blink: !work.tool.error };
  if (work?.last_line) return { tone: CATPPUCCIN.cyan, mark: "▮", text: who, tool: `last line: ${work.last_line}`, t: startedAt ? secsAgo(startedAt) : "", blink: true, muted: true };
  return { tone: CATPPUCCIN.cyan, mark: "▮", text: `${who} working`, tool: "", t: startedAt ? secsAgo(startedAt) : "", blink: true };
};

export const WorkPane = ({ run, onOpen }) => {
  // the CLI it runs, not the profile's nickname: a profile called codex that runs claude is claude here
  const work = run?.work || {}, who = shownAgent(run);
  const waiting = run?.kind === "session" && (run.asking || isWaiting(run));
  const h = workHead(work, who, waiting, run?.asking, run?.StartedAt || run?.started, run?.promptPending, run?.state, run?.request?.text);
  const todos = work.todos || [];
  const files = (work.files?.length ? work.files : (run?.files || []).map((p) => ({ path: p, n: 0 }))).slice(0, 4);
  const more = Math.max(0, (work.files?.length || run?.files?.length || 0) - files.length);
  const { rows, hidden, before } = todoWindow(todos);
  const flag = (work.flags || []).find((f) => f.level === "check");
  const fin = !!work.done_at && !work.tool;
  return (
    <Box onClick={onOpen} sx={{ mt: 0.6, bgcolor: CATPPUCCIN.bg, border: `1px solid ${CATPPUCCIN.surface}`, borderRadius: 1.25, px: 0.85, py: 0.55,
      ...mono, fontSize: 9.5, lineHeight: 1.6, color: CATPPUCCIN.dim, cursor: onOpen ? "pointer" : "default" }}>
      <Box sx={{ display: "flex", alignItems: "center", gap: 0.6, whiteSpace: "nowrap", overflow: "hidden", color: h.tone, fontWeight: 600 }}>
        <Box component="span" sx={h.blink && !waiting ? { "@keyframes tqBlink": { "50%": { opacity: 0.25 } }, animation: "tqBlink 1.1s step-end infinite" } : {}}>{h.mark}</Box>
        <span>{h.text}</span>
        {h.tool && <Box component="span" noWrap sx={{ color: h.muted ? CATPPUCCIN.faint : CATPPUCCIN.blue, fontWeight: 500, overflow: "hidden", textOverflow: "ellipsis", minWidth: 0 }}>{h.tool}</Box>}
        <Box sx={{ flex: 1 }} />
        {h.t && <Box component="span" sx={{ color: CATPPUCCIN.faint, fontWeight: 400 }}>{h.t}</Box>}
      </Box>
      {!!todos.length && (
        <Box sx={{ borderTop: `1px dashed ${CATPPUCCIN.surface}`, mt: 0.4, pt: 0.35 }}>
          {fin ? (
            <Box sx={{ color: CATPPUCCIN.green }}>✓ {work.n_done} of {work.n_todos} done{work.said ? <Box component="span" sx={{ color: CATPPUCCIN.faint }}> · {work.said.slice(0, 60)}</Box> : null}</Box>
          ) : (
            <>
              {before > 0 && <Box sx={{ color: CATPPUCCIN.faint }}>✓ {before} done</Box>}
              {rows.map((t, i) => (
                <Box key={i} sx={{ display: "grid", gridTemplateColumns: "12px 1fr auto", gap: "0 6px", whiteSpace: "nowrap", overflow: "hidden",
                  color: t.status === "now" ? CATPPUCCIN.fg : CATPPUCCIN.faint, opacity: t.status === "todo" ? 0.8 : 1 }}>
                  <Box component="span" sx={{ textAlign: "center", color: t.status === "done" ? CATPPUCCIN.green : TERM_TONE[t.status] }}>{TERM_MARK[t.status] || "○"}</Box>
                  <Box component="span" sx={{ overflow: "hidden", textOverflow: "ellipsis", color: t.status === "now" ? CATPPUCCIN.yellow : "inherit" }}>{t.text}</Box>
                  <Box component="span" sx={{ color: CATPPUCCIN.faint, fontSize: 9 }}>{t.status === "now" ? `${work.n_done + 1}/${work.n_todos}` : ""}</Box>
                </Box>
              ))}
              {hidden - (before || 0) > 0 && <Box sx={{ color: CATPPUCCIN.faint }}>+{hidden - (before || 0)} more</Box>}
            </>
          )}
        </Box>
      )}
      {!!files.length && (
        <Box sx={{ borderTop: `1px dashed ${CATPPUCCIN.surface}`, mt: 0.4, pt: 0.4, display: "flex", flexWrap: "wrap", gap: "3px 4px", alignItems: "center" }}>
          <Box component="span" sx={{ color: CATPPUCCIN.faint, mr: 0.25 }}>{fin ? "touched" : "holding"}</Box>
          {files.map((f) => (
            <Tooltip key={f.path} title={f.path} arrow>
              <Box component="span" sx={{ display: "inline-flex", alignItems: "center", gap: 0.5, px: 0.6, borderRadius: 0.75, lineHeight: 1.5,
                bgcolor: isHot(f.last) ? "#2a2f4a" : CATPPUCCIN.surface, color: f.late ? CATPPUCCIN.peach : isHot(f.last) ? CATPPUCCIN.blue : CATPPUCCIN.dim }}>
                {isHot(f.last) && <Box component="span" sx={{ width: 5, height: 5, borderRadius: "50%", bgcolor: CATPPUCCIN.blue, "@keyframes tqPulse": { "50%": { opacity: 0.25 } }, animation: "tqPulse 1.4s ease-in-out infinite" }} />}
                {fileName(f.path)}{f.n > 0 && <Box component="span" sx={{ color: CATPPUCCIN.faint }}>×{f.n}</Box>}
              </Box>
            </Tooltip>
          ))}
          {more > 0 && <Box component="span" sx={{ color: CATPPUCCIN.faint }}>+{more}</Box>}
        </Box>
      )}
      {flag && <Box sx={{ color: CATPPUCCIN.red, whiteSpace: "normal", lineHeight: 1.45, mt: 0.35 }}>✗ {flag.text}</Box>}
    </Box>
  );
};

// one line, for a header: ● agent · Edit server.py · 4s  |  ● agent · last line: "…"
export const WorkLine = ({ work, who = "agent", waiting = false, asking = false, startedAt, promptPending = false, state = "", detail = "" }) => {
  const h = workHead(work, who, waiting, asking, startedAt, promptPending, state, detail);
  if (!h.tool && !waiting) return null;
  return (
    <Box sx={{ display: "inline-flex", alignItems: "center", gap: 0.6, minWidth: 0, maxWidth: "100%", ...mono, fontSize: 10.5 }}>
      <Box component="span" sx={{ width: 6, height: 6, borderRadius: "50%", flexShrink: 0, bgcolor: waiting ? ROLES.you.solid : ROLES.working.solid,
        ...(waiting ? {} : { "@keyframes tqPulse2": { "50%": { opacity: 0.25 } }, animation: "tqPulse2 1.4s ease-in-out infinite" }) }} />
      <Box component="span" sx={{ fontWeight: 600, color: waiting ? ROLES.you.ink : INK, whiteSpace: "nowrap" }}>{waiting ? h.text : who}</Box>
      {h.tool && <Box component="span" noWrap sx={{ px: 0.6, borderRadius: 0.75, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", minWidth: 0,
        bgcolor: h.muted ? ROLES.muted.tint : ROLES.working.tint, color: h.muted ? ROLES.muted.ink : ROLES.working.ink }}>{h.tool}</Box>}
      {h.t && <Box component="span" sx={{ color: FAINT, flexShrink: 0 }}>{h.t}</Box>}
    </Box>
  );
};

/* The task page's strip: the agent's own list beside the files it wrote, with git's +/- per file,
   reconciled in plain sentences (taskuary/witness.py decides "late"; nothing is
   inferred). Provenance pills say where the task came from and who worked it - facts the audit
   chain already held and the card never showed. Polls only while the session is alive. */
const pillSx = (r) => ({ height: 16, fontSize: 9, fontWeight: 600, bgcolor: ROLES[r].tint, color: ROLES[r].ink, border: `1px solid ${ROLES[r].bd}`, "& .MuiChip-label": { px: 0.75 } });
const hhmm = (s) => s ? fmtTime(new Date(String(s).replace(" ", "T")), "en-US", { hour: "numeric", minute: "2-digit" }) : "";
export const WorkStrip = ({ taskId, live, session, provenance, defaultCollapsed = false }) => {
  // The terminal list already carries current witness/provenance data. Paint that immediately;
  // the richer /work response (diff counts, exact audit provenance) replaces it in the background.
  // Waiting for that request made the whole strip appear to have vanished above a busy terminal.
  const seed = session ? {
    work: session.work || null,
    files: (session.work?.files?.length ? session.work.files : (session.files || [])).map((f) =>
      typeof f === "string" ? { path: f, n: 0 } : f),
    prov: provenance || {},
    session: { sid: session.sid, alive: session.alive, agent: session.agent, cli: session.cli,
      started: session.started, cwd: session.cwd },
  } : null;
  const [d, setD] = useState(seed);
  const [failed, setFailed] = useState(false);
  // During a live run the terminal owns the page, so first use starts folded. Once the owner
  // chooses, keep that choice for this browser; opening the strip is still one click away.
  const [open, setOpen] = useState(() => { try {
    const saved = localStorage.getItem("tq.workstrip");
    return saved == null ? !defaultCollapsed : saved !== "0";
  } catch { return !defaultCollapsed; } });
  const toggle = () => { setOpen((o) => { try { localStorage.setItem("tq.workstrip", o ? "0" : "1"); } catch { /* private window */ } return !o; }); };
  useEffect(() => {
    if (!taskId) return undefined;
    let alive = true;
    setD(seed); setFailed(false);
    // The terminal roster already supplies the folded summary. Do not fetch detail the owner
    // cannot see; opening the strip performs the richer read immediately.
    if (!open) return () => { alive = false; };
    const load = async (diff) => {
      try {
        const { data } = await api.get(`/api/tasks/${taskId}/work`, { params: { diff } });
        if (alive) { setD(data); setFailed(false); }
      } catch { if (alive) setFailed(true); }
    };
    load(true);
    // PTY output must not fan out into HTTP. This secondary summary refreshes at a bounded pace.
    const id = live ? setInterval(() => load(false), 5000) : 0;
    return () => { alive = false; clearInterval(id); };
  }, [taskId, live, open]);
  const w = d?.work;
  if (!d) return failed ? (
    <Box sx={{ mb: 0.75, border: `1px solid ${ROLES.you.bd}`, borderRadius: 2, bgcolor: ROLES.you.tint,
      px: 1.5, py: 0.65, display: "flex", alignItems: "center", gap: 1 }}>
      <Typography sx={{ ...mono, fontSize: 10, fontWeight: 600, color: ROLES.you.ink }}>agent activity unavailable</Typography>
      <Typography variant="caption" sx={{ color: DIM }}>the terminal is unaffected · {live ? "retrying" : "reload to retry"}</Typography>
    </Box>
  ) : null;
  const todos = w?.todos || [], files = (d.files || []).slice(0, 12);
  const tone = { check: "you", note: "info", ok: "done" };
  const who = d.session?.cli || d.session?.agent || d.prov?.by || "agent";
  const checks = (w?.flags || []).filter((f) => f.level === "check").length;
  const summary = `said ${todos.length ? `${w.n_done}/${w.n_todos}` : "—"} · touched ${(d.files || []).length}`;
  return (
    // flexShrink 0: the task page stacks this over a terminal with a fixed height in a flex column,
    // and a shrinkable overflow:hidden box in that column collapsed to nothing - the strip was in
    // the DOM and never on screen
    <Box sx={{ mb: 0.75, border: `1px solid ${BORDER}`, borderRadius: 2, bgcolor: PANEL, overflow: "hidden", flexShrink: 0 }}>
      <Box onClick={toggle} title={open ? "Fold the detail away" : "Open: the agent's list beside the files it wrote"}
        sx={{ px: 1.5, py: 0.5, display: "flex", flexWrap: "wrap", gap: 0.5, alignItems: "center", cursor: "pointer", borderBottom: open ? `1px solid ${BORDER}` : 0, "&:hover": { bgcolor: "#faf8f5" } }}>
        <Typography component="span" sx={{ ...mono, fontSize: 10, color: FAINT, width: 12 }}>{open ? "▾" : "▸"}</Typography>
        <Typography component="span" sx={{ ...mono, fontSize: 9.5, color: DIM, fontWeight: 600, letterSpacing: ".06em", mr: 0.25 }}>AGENT ACTIVITY</Typography>
        {d.prov?.from && <Chip size="small" label={`from: ${d.prov.from}`} sx={pillSx("muted")} />}
        {d.prov?.kind && <Chip size="small" label={`kind: ${d.prov.kind}`} sx={pillSx("working")} />}
        {d.prov?.by && <Chip size="small" label={`by: ${who}`} sx={pillSx("working")} />}
        {d.prov?.approved && <Chip size="small" label={`approved by you · ${hhmm(d.prov.approved)}`} sx={pillSx("info")} />}
        {w?.done_at && <Chip size="small" label={`agent said done · ${hhmm(w.done_at)}`} sx={pillSx("done")} />}
        <Chip size="small" label={summary} sx={pillSx("muted")} />
        {checks > 0 && <Chip size="small" label={`${checks} to check`} sx={pillSx("you")} />}
        <Box sx={{ flex: 1 }} />
        {w && <WorkLine work={w} who={who} waiting={false} startedAt={d.session?.started}
          promptPending={d.session?.promptPending} />}
      </Box>
      {open && <Box sx={{ display: "grid", gridTemplateColumns: { xs: "minmax(0, 1fr)", md: "minmax(0, 1fr) minmax(0, 1fr)" } }}>
        <Box sx={{ px: 1.5, py: 1, borderRight: { md: `1px solid ${BORDER}` } }}>
          <Box sx={{ display: "flex", alignItems: "baseline", gap: 1, mb: 0.5 }}>
            <Typography sx={{ ...mono, fontSize: 9.5, letterSpacing: ".08em", textTransform: "uppercase", color: FAINT, fontWeight: 600 }}>said it would</Typography>
            <Typography variant="caption" sx={{ color: DIM }}>{todos.length ? `the agent's own list · ${w.n_done} of ${w.n_todos}` : w?.source ? "no list reported by this agent" : "no signal from this CLI - files only"}</Typography>
          </Box>
          {todos.map((t, i) => (
            <Box key={i} sx={{ display: "flex", gap: 1, alignItems: "flex-start", py: 0.35, borderBottom: i < todos.length - 1 ? `1px dashed ${BORDER}` : 0, color: t.status === "todo" ? FAINT : INK, fontSize: 12.5 }}>
              <Box sx={{ ...mono, fontSize: 10, width: 15, height: 15, borderRadius: "50%", display: "grid", placeItems: "center", flex: "none", mt: "2px",
                bgcolor: t.status === "done" ? ROLES.done.solid : t.status === "now" ? ROLES.working.solid : "transparent", color: t.status === "todo" ? FAINT : "#fff",
                border: t.status === "todo" ? `1.5px solid ${BORDER}` : 0 }}>{t.status === "done" ? "✓" : t.status === "now" ? "▸" : ""}</Box>
              <span>{t.text}</span>
            </Box>
          ))}
          {!todos.length && w?.said && <Typography variant="caption" sx={{ color: DIM, display: "block" }}>last said: “{w.said.slice(0, 200)}”</Typography>}
        </Box>
        <Box sx={{ px: 1.5, py: 1 }}>
          <Box sx={{ display: "flex", alignItems: "baseline", gap: 1, mb: 0.5 }}>
            <Typography sx={{ ...mono, fontSize: 9.5, letterSpacing: ".08em", textTransform: "uppercase", color: FAINT, fontWeight: 600 }}>touched</Typography>
            <Typography variant="caption" sx={{ color: DIM }}>{plural(files.length, "file")}{d.diffstat?.added != null ? ` · +${d.diffstat.added} −${d.diffstat.removed}` : ""}</Typography>
          </Box>
          {files.map((f) => {
            const top = Math.max(1, ...files.map((x) => x.n || 1));
            return (
              <Box key={f.path} title={f.path} sx={{ display: "grid", gridTemplateColumns: "1fr auto auto 64px", gap: 1, alignItems: "center", py: 0.35, borderBottom: `1px dashed ${BORDER}`,
                "&:last-of-type": { borderBottom: 0 }, color: INK, opacity: f.late || isHot(f.last) || f.n > 0 ? 1 : 0.7 }}>
                <Typography noWrap sx={{ ...mono, fontSize: 11.5 }}>{f.path}</Typography>
                <Typography sx={{ ...mono, fontSize: 10.5, color: FAINT, fontVariantNumeric: "tabular-nums" }}>{f.n ? `×${f.n}` : ""}</Typography>
                <Typography sx={{ ...mono, fontSize: 10.5, color: f.late ? ROLES.you.ink : FAINT, fontVariantNumeric: "tabular-nums" }}>
                  {f.added != null ? <><span style={{ color: ROLES.done.solid }}>+{f.added}</span> <span style={{ color: ROLES.you.solid }}>−{f.removed}</span></> : hhmm(f.last)}
                </Typography>
                <Box sx={{ height: 4, borderRadius: 2, bgcolor: PANEL2 }}><Box sx={{ height: "100%", borderRadius: 2, width: `${Math.round(100 * (f.n || 0.3) / top)}%`, bgcolor: f.late ? ROLES.you.solid : ROLES.working.solid, opacity: isHot(f.last) ? 1 : 0.7 }} /></Box>
              </Box>
            );
          })}
          {!files.length && <Typography variant="caption" sx={{ color: FAINT }}>nothing written yet</Typography>}
        </Box>
      </Box>}
      {open && !!(w?.flags || []).length && (
        <Box sx={{ px: 1.5, py: 0.75, borderTop: `1px solid ${BORDER}`, display: "flex", flexDirection: "column", gap: 0.4 }}>
          {w.flags.map((f, i) => (
            <Box key={i} sx={{ display: "flex", gap: 1, alignItems: "flex-start", fontSize: 12 }}>
              <Chip size="small" label={f.level} sx={{ ...pillSx(tone[f.level] || "info"), mt: "1px" }} />
              <span>{f.text}</span>
            </Box>
          ))}
        </Box>
      )}
    </Box>
  );
};

// `fill` hands the console the whole pane instead of a five-line letterbox: the Timeline's
// Agent tab was a small dark box above 600px of nothing while an agent worked in it. Filling,
// the tail scrolls inside and the header stays put.
export const LiveConsole = ({ run, agent, lines = 5, onOpen, fill }) => {
  const waiting = run ? (run.kind === "session" && (run.asking || isWaiting(run))) : false;
  const tail = (run?.tail || []).slice(-lines);
  const files = run?.files || [];
  const who = run ? shownAgent(run) : agent || AGENT_SHOWN;
  return (
    <Box onClick={onOpen} title="Open the task - the real terminal"
      sx={{ bgcolor: CATPPUCCIN.bg, border: `1px solid ${CATPPUCCIN.surface}`, borderRadius: 1.5, px: 1.25, py: 0.9, cursor: onOpen ? "pointer" : "default",
        ...(fill ? { flex: 1, minHeight: 0, display: "flex", flexDirection: "column" } : {}),
        "&:hover": onOpen ? { borderColor: CATPPUCCIN.overlay } : {} }}>
      <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: tail.length ? 0.5 : 0, flexShrink: 0 }}>
        <Typography variant="caption" sx={{ ...mono, fontSize: 10.5, fontWeight: 600, color: waiting ? CATPPUCCIN.yellow : CATPPUCCIN.cyan,
          ...(waiting ? {} : { "@keyframes tqBlink2": { "50%": { opacity: 0.25 } }, animation: "tqBlink2 1.1s step-end infinite" }) }}>
          {waiting ? `⏸ ${says(run?.state || (run?.asking ? "asking" : "parked"), who)}` : `▮ ${who} working${run?.StartedAt ? ` · ${_elapsed(run.StartedAt)}` : ""}`}
        </Typography>
        <Box sx={{ flex: 1 }} />
        {files.slice(0, 4).map((f) => (
          <Typography key={f} variant="caption" sx={{ ...mono, fontSize: 9, color: CATPPUCCIN.dim, bgcolor: CATPPUCCIN.surface, px: 0.6, borderRadius: 0.75 }}>
            {String(f).split(/[\\/]/).pop()}
          </Typography>
        ))}
        {onOpen && <Typography variant="caption" sx={{ ...mono, fontSize: 9.5, color: CATPPUCCIN.faint }}>open ↗</Typography>}
      </Box>
      <Box sx={fill ? { flex: 1, minHeight: 0, overflowY: "auto", display: "flex", flexDirection: "column", justifyContent: "flex-end" } : {}}>
      {tail.map((l, i, all) => (
        <Typography key={i} noWrap variant="caption" sx={{ ...mono, display: "block", fontSize: 10, lineHeight: 1.55,
          color: l.startsWith("→") ? CATPPUCCIN.blue : l.startsWith("✗") ? CATPPUCCIN.red : CATPPUCCIN.fg, opacity: 0.45 + 0.55 * ((i + 1) / all.length) }}>
          {l.replace(/\n/g, " ")}
        </Typography>
      ))}
      {!tail.length && <Typography variant="caption" sx={{ ...mono, fontSize: 10, color: CATPPUCCIN.faint }}>…</Typography>}
      </Box>
    </Box>
  );
};

export const FilterPills = ({ options, value, onChange }) => (
  // A segmented control reads as one control only in one row, so it never wraps - which on a
  // phone dragged the whole page sideways. It scrolls inside itself instead, with the scrollbar
  // hidden: the pills are the affordance.
  <Box sx={{ display: "inline-flex", alignItems: "center", gap: 0.25, p: 0.4, height: 34, boxSizing: "border-box",
    bgcolor: "#e9e3d8", maxWidth: "100%",
    overflowX: "auto", scrollbarWidth: "none", "&::-webkit-scrollbar": { display: "none" },
    border: "1px solid #e1dcd5", borderRadius: 2.5 }}>
    {options.map((o) => {
      const key = o.key ?? o, on = value === key;
      const c = o.c || { bg: "#eae4d8", fg: "#55697a", bd: "#d8cfbe" };
      return (
        <Box key={key} onClick={() => onChange(key)}
          sx={{ px: 1.25, py: 0.45, borderRadius: 1.75, cursor: "pointer", fontSize: 11.5,
            display: "inline-flex", alignItems: "center", gap: 0.55,
            fontWeight: on ? 700 : 500, lineHeight: 1.4, userSelect: "none", whiteSpace: "nowrap",
            bgcolor: on ? c.bg : "transparent", color: on ? c.fg : DIM,
            border: `1px solid ${on ? c.bd : "transparent"}`,
            boxShadow: on ? "0 1px 2px rgba(30,50,38,.08)" : "none",
            transition: "all .15s", "&:hover": on ? {} : { bgcolor: "#eae5dd", color: "#2b2a26" } }}>
          {o.label ?? (o || "all")}
          {/* the count is a BADGE, not the last word of the label - glued on with a space,
              "needs you 2" reads as one phrase and the number disappears into the name */}
          {o.n != null && (
            <Box component="span" sx={{ px: 0.55, py: 0.05, borderRadius: 99, fontSize: 10, fontWeight: 600,
              fontVariantNumeric: "tabular-nums", lineHeight: 1.5,
              bgcolor: on ? "rgba(255,255,255,.7)" : "#e6e2da", color: on ? c.fg : "#867f74" }}>{o.n}</Box>
          )}
        </Box>
      );
    })}
  </Box>
);

// ── PICKING A PERSON ────────────────────────────────────────────────────────────────────
// Everyone Taskuary has seen (/api/people), searched by name OR address, with the option row
// laid out so it survives a long name beside a long address. It used to be a bare Autocomplete
// whose <li> had no width control at all, so "Paula Vance, CPA · PVance@vendor.example" wrapped over
// the row beneath it and the list read as broken (owner, 2026-09-02). One component now, because
// there is no reason for looping someone in and handing work over to disagree about how a person
// is chosen.
//
// freeSolo on purpose: the right recipient is often somebody who has never written to you.
// ...one read shared by every picker drawn within a minute (contacts.js)
export const useContacts = () => {
  const [people, setPeople] = useState([]);
  useEffect(() => { let on = true; readContacts((u) => api.get(u)).then((p) => { if (on) setPeople(p); }).catch(() => {}); return () => { on = false; }; }, []);
  return people;
};

// ...and the server's search as you type: company, domain, a fragment of a name, the model's pick when nothing plain fits (peopleSearch.js)
export const usePeopleSearch = (q, channel = "email") => {
  const [found, setFound] = useState({ q: "", rows: [], ai: false });
  useEffect(() => runSearch((u, o) => api.get(u, o), q, channel, setFound), [q, channel]);
  return found;
};

// `channel`: a chat's picker offers that channel's chats (their handle is what goes); the address book is email's alone
export const ContactPicker = ({ value, onChange, onPick, placeholder = "name or email address",
                               people, autoFocus, size = "small", sx, onKeyDown, clearOnPick, channel = "email" }) => {
  const rows = String(channel || "email").toLowerCase() === "email" ? people || [] : [];
  const found = usePeopleSearch(value, channel);
  const q = String(value || "").trim().toLowerCase();
  // search the NAME as well as the address: nobody remembers how a colleague's mailbox is spelled
  const local = rows.filter((p) => p.Email && (!q || `${p.Name || ""} ${p.Email}`.toLowerCase().includes(q)))
    .slice(0, 50).map((p) => ({ to: p.Email, name: p.Name || "" }));
  const opts = withFound(local, found, value).slice(0, 50);
  const of = (o) => opts.find((x) => x.to === o) || {};
  return (
    <Autocomplete freeSolo autoHighlight size={size} sx={sx}
      options={opts.map((o) => o.to)}
      inputValue={value ?? ""}
      onInputChange={(_e, v) => onChange?.(v || "")}
      onChange={(_e, v) => { if (v) { onPick?.(String(v)); if (clearOnPick) onChange?.(""); } }}
      getOptionLabel={(o) => String(o)}
      filterOptions={(x) => x}
      renderOption={(props, o) => {
        const p = of(o), line = personLine(p);
        return (
          <li {...props} key={o} data-tq-person={o} style={{ display: "block", padding: "4px 10px", minWidth: 0 }}>
            {p.name && (
              <div style={{ fontSize: 12.5, color: INK, fontWeight: 600, overflow: "hidden",
                textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{p.name}</div>
            )}
            <div style={{ fontSize: 11.5, color: FAINT, overflow: "hidden",
              textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{line ? `${line} · ${o}` : o}</div>
          </li>
        );
      }}
      renderInput={(params) => (
        <TextField {...params} autoFocus={autoFocus} placeholder={placeholder} onKeyDown={onKeyDown}
          inputProps={{ ...params.inputProps, style: { ...(params.inputProps || {}).style, fontSize: 12.5 } }} />
      )} />
  );
};

// Who else gets this answer. Held by the caller and passed on the send, never stored: the copy
// list you can SEE is the one that goes, and a reloaded page starts empty rather than quietly
// copying somebody you added an hour ago (verdicts.decide).
// WHO AN EMAIL DRAFT GOES TO, corrected at the card: the TO line was text, so a wrong name or one with no address ("Devorah
// Cohn ?") could only be dropped (the owner, 2026-10-06: "i should be able to edit the email address"). Saves on pick.
// ...the line wears the sender's name ("Erin Blake <erin@…>", replyDelivery.deliveryTo); the box and the save carry the addresses alone -
// saved back as it stood, the name went into the envelope as the address
export const ToRow = ({ to, onSave, disabled }) => {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [err, setErr] = useState("");
  const people = useContacts();
  const save = async (a) => {
    const v = bareAddresses(a);
    if (!v.length || !v.every((x) => x.includes("@"))) { setErr("pick a person or type their email address"); return; }
    try { await onSave(v); setText(""); setErr(""); setOpen(false); }
    catch (e) { setErr(e?.response?.data?.detail || "could not change who it goes to"); }
  };
  return (
    <Box sx={{ display: "flex", alignItems: "center", gap: 0.8, mb: 0.75, flexWrap: "wrap", minWidth: 0 }}>
      <Typography sx={{ ...label, flexShrink: 0 }}>To</Typography>
      {open ? (
        <ContactPicker people={people} value={text} onChange={setText} onPick={save} autoFocus
          placeholder="name or email address" sx={{ width: 300 }}
          onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); save(text); }
                              if (e.key === "Escape") { setOpen(false); setErr(""); } }} />
      ) : (
        <>
          <Typography variant="body2" sx={{ color: INK, fontWeight: 600 }} noWrap>{to || "nobody yet"}</Typography>
          {/* ...opened on the address it has: "change" emptied To while the footer still named the old one (the UI audit, 2026-10-21) */}
          {!disabled && <Typography {...pressable(() => { setText(bareAddresses(to).join(", ")); setOpen(true); })} data-tq-to-change
            sx={{ ...FOCUS_RING, fontSize: 11.5, color: "#55697a", cursor: "pointer", fontWeight: 600, "&:hover": { textDecoration: "underline" } }}>
            change</Typography>}
        </>
      )}
      {!!err && <Typography variant="caption" sx={{ color: "#6b2733" }}>{err}</Typography>}
    </Box>
  );
};

export const CcRow = ({ cc, setCc, channel }) => {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [err, setErr] = useState("");
  const people = useContacts();
  if (String(channel || "").toLowerCase() !== "email") return null;   // a chat has members, not recipients
  // ...a name nobody matched is said, as To says it (the overnight walk, 2026-10-27: Enter on "gail" did nothing and said nothing)
  const add = (a) => {
    const v = String(a || "").trim();
    if (!v.includes("@")) { if (v) setErr("pick a person or type their email address"); return; }
    setCc([...(cc || []).filter((x) => x.toLowerCase() !== v.toLowerCase()), v]);
    setText(""); setErr(""); setOpen(false);
  };
  return (
    <Box sx={{ display: "flex", alignItems: "center", gap: 0.8, mb: 0.75, flexWrap: "wrap", minWidth: 0 }}>
      <Typography sx={{ color: "#6f8a6e", fontSize: 9.5, fontWeight: 600, letterSpacing: "1.5px", flexShrink: 0 }}>CC</Typography>
      {(cc || []).map((a) => (
        <Box key={a} sx={{ display: "inline-flex", alignItems: "center", gap: 0.5, px: 0.8, py: 0.15,
          borderRadius: 99, bgcolor: "#eef1ec", border: "1px solid #d9e0d6" }}>
          <Typography sx={{ fontSize: 11.5, color: INK }}>{a}</Typography>
          <Box component="button" type="button" aria-label={`Remove ${a} from CC`}
            onClick={() => setCc((cc || []).filter((x) => x !== a))}
            sx={{ cursor: "pointer", color: FAINT, fontSize: 12, lineHeight: 1, border: 0, bgcolor: "transparent", p: 0, fontFamily: "inherit", "&:hover": { color: "#6b2733" } }}>✕</Box>
        </Box>
      ))}
      {open ? (
        <ContactPicker people={people} value={text} onChange={setText} onPick={add} autoFocus
          placeholder="name or email address" sx={{ width: 260 }}
          onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); add(text); }
                              if (e.key === "Escape") { setOpen(false); setErr(""); } }} />
      ) : (
        <Typography {...pressable(() => setOpen(true))}
          sx={{ ...FOCUS_RING, fontSize: 11.5, color: "#55697a", cursor: "pointer", fontWeight: 600,
                "&:hover": { textDecoration: "underline" } }}>
          {(cc || []).length ? "+ someone else" : "+ loop someone in"}
        </Typography>
      )}
      {!!err && open && <Typography variant="caption" sx={{ color: "#6b2733" }}>{err}</Typography>}
    </Box>
  );
};

// THE REPLY DRAFT BOX, one for every surface that shows a draft (task Close out, the walk's reply card) - a long email
// read through an 8-line slot with its own scrollbar (the owner, 2026-10-19). It grows with the text up to 60% of the
// window, and the corner handle drags it taller or shorter. The drag is fed back as autosize's own floor (minRows) rather
// than a height autosize would overwrite on the next keystroke, so the two never fight: the box keeps the size you gave it
// and still grows past it with the text.
export const DraftField = ({ value, onChange, sx, inputProps, ...rest }) => {
  const ref = useRef(null), drag = useRef(null);
  const [rows, setRows] = useState(0), [cap, setCap] = useState(24);
  const line = (el) => parseFloat(getComputedStyle(el).lineHeight) || 18;
  useEffect(() => {
    const el = ref.current; if (!el) return;
    // ...and in a task's work column, no taller than leaves Send under it with the column at its top (the owner, 2026-10-26: "why is
    // this cut off" - a 60%-of-screen draft outgrew the column, the lit Send was scrolled up to, and "Result" rested half under the edge)
    const col = el.closest("[data-tq-work]");
    const fit = () => {
      // ...64px under it: Send's row and its margins - at 56 Send stood 1-3px past the column's foot (1366, and 1440 once the silent
      // strip gave the dock's 31px back, 2026-10-26), was scrolled to, and the column opened scrolled; four rows at least, so a short column keeps Send in view
      const room = col ? col.clientHeight - (el.getBoundingClientRect().top - col.getBoundingClientRect().top + col.scrollTop) - 64 : Infinity;
      setCap(Math.max(col ? 4 : 8, Math.floor(Math.min(window.innerHeight * 0.6, room) / line(el))));
    };
    fit(); window.addEventListener("resize", fit);
    const cro = col && new ResizeObserver(fit); cro?.observe(col);
    // a resize while the pointer is down on the box is the handle being dragged; settle it once the drag goes quiet
    const ro = new ResizeObserver(() => { if (!drag.current) return;
      clearTimeout(drag.current.t); drag.current.t = setTimeout(() => setRows(Math.max(2, Math.round(el.clientHeight / line(el)))), 250); });
    ro.observe(el);
    const up = () => { drag.current = null; };   // the settle already queued still lands
    window.addEventListener("pointerup", up);
    return () => { ro.disconnect(); cro?.disconnect(); window.removeEventListener("resize", fit); window.removeEventListener("pointerup", up); };
  }, []);
  return <TextField fullWidth multiline minRows={Math.max(2, rows)} maxRows={Math.max(cap, rows)} value={value} onChange={onChange} {...rest}
    inputRef={ref} inputProps={{ ...inputProps, "data-tq-draft": "", onPointerDown: () => { drag.current = { t: 0 }; } }}
    sx={{ ...sx, "& textarea": { ...(sx?.["& textarea"] || {}), resize: "vertical" } }} />;
};
