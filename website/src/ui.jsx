// Shared Task Hub atoms: chips, channel icons, relative time. Light + compact.
import React, { useEffect, useState } from "react";
import { Alert, Box, Button, Chip, CircularProgress, Dialog, DialogActions, DialogContent,
  DialogContentText, DialogTitle, InputAdornment, MenuItem, Select, TextField, Tooltip, Typography } from "@mui/material";
import SearchIcon from "@mui/icons-material/Search";
import SmartToyIcon from "@mui/icons-material/SmartToy";
import BlockIcon from "@mui/icons-material/Block";
import api from "./api";
import MailOutlineIcon from "@mui/icons-material/MailOutline";
import GroupsIcon from "@mui/icons-material/Groups";
import GitHubIcon from "@mui/icons-material/GitHub";
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
import StopCircleIcon from "@mui/icons-material/StopCircle";
import { IconButton as MuiIconButton, Tooltip as MuiTooltip } from "@mui/material";
import { Logo, hasLogo } from "./logos.jsx";
import { ROLES, ACTION_COLORS, TAGS, ALERT, ALERT_INK, ALERT_TINT, ALERT_BD, BORDER, CATPPUCCIN, TASK_STATUS_COLORS, mono, DIM, FAINT, INK, PANEL, ACCENT2, PANEL2 } from "./theme.jsx";

// Brand colors so a glance says where a message came from: Teams purple, Outlook blue - and
// amber for scheduled reports, the one row that is ours and not a person, so it has to read
// from across the room rather than blend into the paper the way sage did.
export const CHANNEL_COLORS = { teams: "#6264A7", email: "#41525f", github: "#2b2a26", report: "#c47d1a",
  slack: "#611f69", telegram: "#229ED9", whatsapp: "#25D366", imessage: "#34C759", ai: "#55697a",
  jira: "#0052CC", asana: "#F06A6A", monday: "#6161FF", clickup: "#7b68ee", todoist: "#e44332",
  gitlab: "#fc6d26", azdo: "#0078d4", linear: "#5e6ad2", trello: "#0079bf", notion: "#37352f",
  discord: "#5865F2", sentry: "#7b6bc9", pagerduty: "#048a24",
  aws: "#ff9900", azure: "#0078d4", database: "#6b6459", smb_file: "#6b6459" };
const CHANNEL_ICONS = { teams: GroupsIcon, github: GitHubIcon, report: AssessmentIcon,
  email: MailOutlineIcon, slack: TagIcon, telegram: SendIcon, whatsapp: WhatsAppIcon, imessage: SendIcon,
  ai: AutoAwesomeIcon, jira: BugReportIcon, asana: ChecklistIcon, monday: ViewKanbanIcon,
  clickup: ViewKanbanIcon, todoist: ChecklistIcon,
  gitlab: MergeTypeIcon, azdo: ViewKanbanIcon, linear: ChecklistIcon, trello: ViewKanbanIcon,
  notion: ArticleIcon, discord: TagIcon, sentry: ErrorOutlineIcon, pagerduty: NotificationsActiveIcon,
  aws: CloudQueueIcon, azure: CloudQueueIcon, database: StorageIcon, smb_file: StorageIcon };
// A product named on a card wears its OWN logo where we have one (logos.jsx, self-colored);
// everything else falls back to a Material glyph tinted with the channel's brand color.
export const ChannelIcon = ({ channel, sx }) => {
  if (hasLogo(channel)) return <Logo name={channel} sx={sx} />;
  const Icon = CHANNEL_ICONS[channel] || TerminalIcon;
  return <Icon sx={{ fontSize: 15, color: CHANNEL_COLORS[channel] || "#a9a294", ...sx }} />;
};

/* One dialog for everything that destroys something.

   Deleting a report, an agent or a connection, and "Not a task" - which deletes the task AND
   writes a rule about its sender - were all a single unconfirmed click; "Not a task" was one
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
      <DialogTitle sx={{ fontSize: 15.5, fontWeight: 700, pb: 0.5 }}>{title}</DialogTitle>
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

export const ConfirmDelete = ({ open, what, consequence, confirmLabel = "Delete", onConfirm, onClose }) => {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const go = async () => {
    setBusy(true); setErr("");
    try { await onConfirm(); setBusy(false); onClose(); }
    catch (e) { setErr(e?.response?.data?.detail || e?.message || "that did not work"); setBusy(false); }
  };
  return (
    <Dialog open={!!open} onClose={busy ? undefined : onClose} maxWidth="xs" fullWidth>
      <DialogTitle sx={{ fontSize: 15.5, fontWeight: 700, pb: 0.5 }}>Delete {what}?</DialogTitle>
      <DialogContent>
        <DialogContentText sx={{ fontSize: 13, color: DIM }}>
          {consequence} This cannot be undone.
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
    sx={{ ...mono, bgcolor: "#eae4d8", color: "#55697a", height: 19, fontSize: 10.5 }} />
) : null;

export const ActionChip = ({ action, reviewStatus, taskStatus, needsYou, category, working }) => {
  // an agent in a live session on this task: the row says so, by name - not "needs you"
  if (working && taskStatus !== "done" && reviewStatus !== "pending") {
    // "agent", not the agent's name: the name is whichever CLI happens to be configured (claude,
    // codex, a wrapper) and reads as a brand on a status chip; the tooltip still says who
    return <Chip size="small" label="agent working" title={`${working} has this task open in a live session right now`}
      sx={{ bgcolor: ROLES.working.tint, color: ROLES.working.ink, height: 19, fontSize: 10.5, fontWeight: 700 }} />;
  }
  // a category that is NOT a review state (info, promo, ignored…) is the whole story - a
  // stray review row must not turn a colleague's FYI into "reviewed · edited"
  const cat = category && TAGS[category];
  if (cat && !["coding", "todo", "review", "triaging"].includes(category) && taskStatus !== "done") {
    return <Chip size="small" label={cat.label} title={cat.hint} sx={{ bgcolor: cat.bg, color: cat.fg, height: 19, fontSize: 10.5, fontWeight: 700 }} />;
  }
  // A finished task outranks everything else the chip could say.
  if (taskStatus === "done" && reviewStatus !== "pending") {
    return <Chip size="small" label="completed" sx={{ bgcolor: "#dfeade", color: "#47654a", height: 19, fontSize: 10.5, fontWeight: 700 }} />;
  }
  // and "nobody is moving this" outranks the verdict: what happened to it matters less
  // than whether it is sitting on you right now
  if (needsYou) {
    return <Chip size="small" label="needs you" sx={{ bgcolor: ALERT, color: "#fffdfb",
      height: 19, fontSize: 10.5, fontWeight: 700 }} />;
  }
  // What actually matters to the reader: current state, not just the original verdict.
  // 'report' and 'feed' are NOT verdicts - nothing judged those items; they are here to be
  // read. Only 'ignored' means a policy actually rejected something.
  if (action === "triaging") {                     // decided in seconds: the pill breathes until then
    return <Chip size="small" label="triaging…" sx={{ bgcolor: "#e6e0d5", color: "#6f6960", height: 19, fontSize: 10.5, fontWeight: 700,
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
  <Box component="span" sx={{ ...PILL[tone], px: 0.85, py: 0.2, borderRadius: 99, fontSize: 10.5, fontWeight: 700 }}>
    {children}
  </Box>
);
const mins = (s) => (s == null ? null : s < 90 ? `${s}s` : s < 5400 ? `${Math.round(s / 60)}m` : `${(s / 3600).toFixed(1)}h`);

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
          {ds.files ? `${ds.files} file${ds.files === 1 ? "" : "s"} · +${ds.added} −${ds.removed}` : "no file changes"}
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
        {p.seconds != null && <Pill>{mins(p.seconds)} elapsed</Pill>}
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
              sx={{ fontSize: 11, fontWeight: 700, color: "#55697a", textDecoration: "none" }}>
              {ci.kind === "pr" ? "open PR ↗" : "the commit ↗"}
            </Box>
            <Box component="span" onClick={() => !busy && act("ci")}
              sx={{ fontSize: 11, fontWeight: 700, color: busy ? FAINT : "#55697a", cursor: "pointer" }}>
              {busy === "ci" ? "checking…" : "re-check CI"}
            </Box>
          </>
        ) : (
          // the button says what it will actually DO, per Settings → How finished work lands;
          // the other road stays one click away rather than buried in Settings
          <>
            <Box component="span" onClick={() => !busy && act("land")}
              title={p.flow === "direct" ? "pushes the commits already in the checkout straight onto the default branch"
                : "opens a DRAFT pull request from this task's branch — never merges"}
              sx={{ fontSize: 11, fontWeight: 700, color: busy ? FAINT : "#55697a", cursor: "pointer" }}>
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
            sx={{ fontSize: 11, fontWeight: 700, color: "#55697a", cursor: "pointer" }}>the whole session</Box>
        )}
      </Box>
      {p.error && <Typography variant="caption" sx={{ color: "#6b2733", display: "block", mt: 0.5 }}>{p.error}</Typography>}
    </Box>
  );
};

export const StatusDot = ({ ok, warn }) => (
  <Box component="span" sx={{ display: "inline-block", width: 8, height: 8, borderRadius: "50%", mr: 1,
    bgcolor: ok ? "#22c55e" : warn ? "#55697a" : "#cfc9bf" }} />
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
    ? { color: "#2b2a26", fontWeight: 700, bgcolor: "#e9e3d8" }
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

// The coder's report, parsed into labeled sections instead of a wall of text.
const REPORT_COLORS = { Triage: "#6f8a6e", Determination: "#6f8a6e", Actions: "#55697a", Summary: "#47654a",
  Found: "#6f8a6e", Did: "#55697a", Next: "#6f8a6e" };
/* The four things you can do with a timeline item were four buttons of four different sizes
   and colours, two rows apart, half of them right-aligned - so the reader had to hunt for
   the set. One list, one shape per row: what it is, and what it does. */
/* ── Voice into prompts. Is there a speech-to-text connector at all (Connectors → AI — voice)?
   Asked once per mount; the mic explains itself when there is none. ── */
export const useVoiceReady = () => {
  const [v, setV] = React.useState(null);
  React.useEffect(() => {
    let alive = true;
    api.get("/api/voice/status").then(({ data }) => alive && setV(data)).catch(() => alive && setV({ ready: false }));
    return () => { alive = false; };
  }, []);
  return v;
};

// One mic. Press to record, press again to stop; the clip goes to /api/voice/transcribe as its
// raw bytes and the text lands through onText - into a prompt box, or straight into a session.
export const MicButton = ({ onText, size = 18, sx }) => {
  const voice = useVoiceReady();
  const [rec, setRec] = React.useState(null);
  const [busy, setBusy] = React.useState(false);
  const [err, setErr] = React.useState("");
  const flash = (s) => { setErr(s); setTimeout(() => setErr(""), 5000); };
  // No voice connector? Edge and Chrome ship their own recogniser (the Web Speech API) - free,
  // decent for dictation, nothing to set up. It cannot transcribe a voice-note FILE, so the
  // connectors still matter for the funnel; here it means the mic always works.
  const SR = typeof window !== "undefined" ? (window.SpeechRecognition || window.webkitSpeechRecognition) : null;
  const viaBrowser = !!(voice && !voice.ready && SR);
  const start = async () => {
    if (viaBrowser) {
      try {
        const r = new SR(); r.lang = navigator.language || "en-US"; r.continuous = true; r.interimResults = false;
        let heard = "";
        r.onresult = (e) => { heard = Array.from(e.results).filter((x) => x.isFinal).map((x) => x[0].transcript.trim()).join(" "); };
        r.onerror = (e) => flash(e.error === "not-allowed" ? "microphone blocked in this browser" : `recognition ${e.error}`);
        r.onend = () => { setRec(null); if (heard) onText?.(heard); else flash("nothing heard"); };
        r.start(); setRec(r);
      } catch { flash("this browser cannot dictate here"); }
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
    } catch { flash("microphone not available in this browser"); }
  };
  const stop = () => { rec?.stop(); if (!viaBrowser) setRec(null); };   // the browser recogniser reports back through onend
  const title = err || (!voice ? ""
    : rec ? "Stop and transcribe"
    : voice.ready ? `Dictate (${voice.label || voice.provider})`
    : viaBrowser ? "Dictate — your browser's own recogniser (free). Add an AI voice connector for voice notes and better accuracy."
    : "Dictate — add an AI voice connector first (Connectors → AI — voice; Groq is free)");
  return (
    <MuiTooltip title={title}><span>
      <MuiIconButton size="small" onClick={rec ? stop : start} disabled={busy || (voice && !voice.ready && !viaBrowser)} sx={sx}
        aria-label={rec ? "stop recording" : "dictate"}>
        {busy ? <CircularProgress size={size - 4} /> : rec ? <StopCircleIcon sx={{ fontSize: size, color: "#8a3646" }} /> : <MicIcon sx={{ fontSize: size }} />}
      </MuiIconButton>
    </span></MuiTooltip>
  );
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

export const CoderReport = ({ body }) => {
  const text = String(body || "").replace(/^(CODER REPORT|HANDOVER NOTE)\n?/, "").trim();
  // ^ anchored per line, and the label eats spaces but NOT the newline - letting \s* run on
  // swallowed the separator, so an all-empty report rendered "TRIAGE -> Determination:"
  const parts = text.split(/^(Triage|Determination|Actions|Summary|Found|Did|Next):[ \t]*/m);
  const rows = [];
  for (let i = 1; i < parts.length; i += 2) {
    const t = (parts[i + 1] || "").trim();
    if (t) rows.push({ label: parts[i], text: t });
  }
  // free prose (a shell session, a note written by hand) - show it as written
  if (!rows.length) {
    return text ? <Typography variant="body2" sx={{ whiteSpace: "pre-wrap", color: INK, overflowWrap: "anywhere" }}>{text}</Typography> : null;
  }
  return (
    <Box component="table" sx={{ width: "100%", borderCollapse: "collapse", tableLayout: "fixed" }}>
      <Box component="tbody">
        {rows.map((r, i) => (
          <Box component="tr" key={r.label} sx={{ verticalAlign: "top" }}>
            <Box component="td" sx={{ width: 104, px: 1, py: 0.85, bgcolor: PANEL2, whiteSpace: "nowrap",
              borderTop: i ? `1px solid ${BORDER}` : "none", borderRight: `1px solid ${BORDER}` }}>
              <Typography variant="caption" sx={{ ...mono, color: REPORT_COLORS[r.label] || DIM, fontWeight: 700,
                fontSize: 9.5, letterSpacing: 1, textTransform: "uppercase" }}>{r.label}</Typography>
            </Box>
            <Box component="td" sx={{ px: 1.25, py: 0.85, borderTop: i ? `1px solid ${BORDER}` : "none" }}>
              <Typography variant="body2" sx={{ color: INK, lineHeight: 1.55, whiteSpace: "pre-wrap",
                overflowWrap: "anywhere" }}>{r.text}</Typography>
            </Box>
          </Box>
        ))}
      </Box>
    </Box>
  );
};

export const useAgents = () => {
  const [agents, setAgents] = useState([]);
  const [models, setModels] = useState({});
  const [cmds, setCmds] = useState({});
  useEffect(() => {
    api.get("/api/agents").then(({ data }) => {
      setAgents((data.data || []).map((a) => a.Name));
      setModels(data.models || {});
      // profile name -> the CLI it actually runs ('coder' is usually claude) - the Board
      // tints a working card by the BRAND, and the name alone doesn't say which one it is
      setCmds(Object.fromEntries(Object.entries(data.config || {}).map(([k, v]) => [k, (v || {}).cmd || k])));
    }).catch(() => {});
  }, []);
  return { agents, models, cmds };
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

// "This isn't ours." Says so about THIS item and teaches the classifier at the same time:
// the note is saved to memory, and triage reads it on every later message from that sender.
// Editable before saving, because the reason is the part that has to be right.
// `onLock` tells the panel above to stop following the mouse while this is open: rows shift
// under the cursor during a sync, hover re-selects whatever landed there, and the panel -
// keyed on the selected message - unmounted with the half-typed verdict inside it. That read
// as "Not our task doesn't work while syncing", and nothing said otherwise because the save
// error was swallowed. Both ends are fixed here: the lock, and a visible failure.
export const NotMine = ({ messageId, onDone, onLock, row, first }) => {
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
    <Box>
      <Typography variant="caption" sx={{ color: "#47654a", fontWeight: 600, display: "block" }}>
        ✓ noted — triage will apply this to{" "}
        {saved.scope === "global" ? "every sender" : saved.scope === "subject" ? `any mail about “${saved.scopeKey}”` : saved.scopeKey}
        {" "}from now on
      </Typography>
      {/* the verdict works from here on; tasks opened BEFORE it are still sitting there, and
          saying nothing about them is how a fix reads as "still not learning" */}
      {!!saved.alsoCovered?.length && (
        <Typography variant="caption" sx={{ color: "#55697a", display: "block", mt: 0.25 }}>
          {saved.alsoCovered.length} open task{saved.alsoCovered.length === 1 ? "" : "s"} already match it
          ({saved.alsoCovered.slice(0, 4).map((t) => `TQ-${String(t.taskId).padStart(4, "0")}`).join(", ")}
          {saved.alsoCovered.length > 4 ? ", …" : ""}) — close them the same way if they are not yours either.
        </Typography>
      )}
    </Box>
  );
  if (!open) return row ? (
    <ChoiceRow first={first} tint="#e9e3d8" onClick={() => setOpen(true)}
      icon={<BlockIcon sx={{ fontSize: 15, color: "#867f74" }} />}
      label="Not our task" hint="say why once — triage remembers it for this topic, or this sender" />
  ) : (
    <Button size="small" sx={{ color: "#867f74", fontSize: 11 }} onClick={() => setOpen(true)}
      title="Not our responsibility — and remember why, so triage learns it">Not our task</Button>
  );
  return (
    <Box sx={{ width: "100%", mt: 1, p: 1.25, bgcolor: PANEL2, border: `1px solid ${BORDER}`, borderRadius: 1.5 }}>
      <Typography variant="caption" sx={{ color: DIM, fontWeight: 700, display: "block", mb: 0.5 }}>
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
        <Button size="small" sx={{ color: DIM, fontSize: 11 }} onClick={() => setOpen(false)}>cancel</Button>
        <Button size="small" variant="contained" disableElevation
          disabled={busy || !note.trim() || (scope === "subject" && !topic.trim())} onClick={save}
          sx={{ fontSize: 11.5 }}>{busy ? "saving…" : "Not ours — remember this"}</Button>
      </Box>
      {err && <Typography variant="caption" sx={{ color: "#b42318", fontWeight: 600, display: "block", mt: 0.75 }}>
        {err} — your note is still here.
      </Typography>}
    </Box>
  );
};

// Hand ANY timeline item to a coding agent: your prompt + the item's context (subject,
// sender, full body, thread, the operator docs) go down together. Items that aren't a
// task yet become one server-side, so the run has somewhere to live and stream into.
export const SendToAgent = ({ messageId, subject, onOpenTask, dense, row, first }) => {
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
      onOpenTask?.(data.taskId);          // the session IS the page - go watch it
    } catch (e) { setErr(e?.response?.data?.detail || "Could not reach the agent"); }
    setBusy(false);
  };
  if (sent) return (
    <Box sx={{ display: "flex", alignItems: "center", gap: 1, mt: dense ? 0.5 : 1 }}>
      <SmartToyIcon sx={{ fontSize: 15, color: "#47654a" }} />
      <Typography variant="caption" sx={{ color: "#47654a", fontWeight: 600 }}>
        {sent.agent} is on it in a live session — {sent.ref}
      </Typography>
      <Button size="small" sx={{ fontSize: 11 }} onClick={() => onOpenTask?.(sent.taskId)}>watch it live →</Button>
      <Button size="small" sx={{ fontSize: 11, color: DIM }} onClick={() => setSent(null)}>send another</Button>
    </Box>
  );
  if (!open) return row ? (
    <ChoiceRow first={first} tint="#e3e6e1" onClick={() => setOpen(true)}
      icon={<SmartToyIcon sx={{ fontSize: 15, color: "#6f8a6e" }} />}
      label="Send it to a coding agent" hint="opens a live session on a new task — you watch it work" />
  ) : (
    <Button size="small" startIcon={<SmartToyIcon sx={{ fontSize: 14 }} />} onClick={() => setOpen(true)}
      sx={{ fontSize: 11.5, color: "#6f8a6e" }}>Send to coding agent</Button>
  );
  return (
    <Box sx={{ mt: 1, p: 1.25, bgcolor: "#faf8ff", border: "1px solid #e9ddfb", borderRadius: 1.5 }}>
      <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 0.75, flexWrap: "wrap" }}>
        <SmartToyIcon sx={{ fontSize: 15, color: "#6f8a6e" }} />
        <Typography variant="caption" sx={{ color: "#6f8a6e", fontWeight: 700 }}>Send to an agent</Typography>
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
          sx={{ fontSize: 11.5, bgcolor: "#6f8a6e", "&:hover": { bgcolor: "#6b1fb0" } }}>
          {busy ? "sending…" : "Send"}
        </Button>
      </Box>
      {err && <Typography variant="caption" sx={{ color: "#6b2733", display: "block", mt: 0.5 }}>{err}</Typography>}
    </Box>
  );
};

/* Task status, review status and run status were three ladders the reader had to combine
   in their head ("in_progress + reviewed·rejected" — so is it mine or not?). This is the
   one answer: what does this task need from ME, right now. Everything shows this. */
export const TASK_STATES = [
  { key: "needs_you", label: "needs you", c: { bg: "#eae4d8", fg: "#55697a", bd: "#d8cfbe" } },
  { key: "working", label: "agent working", c: { bg: "#e3e6e1", fg: "#6f8a6e", bd: "#d2d6cf" } },
  { key: "queued", label: "queued", c: { bg: "#eae4d8", fg: "#55697a", bd: "#d8cfbe" } },
  { key: "done", label: "done", c: { bg: "#dfeade", fg: "#47654a", bd: "#c8d9c7" } },
  { key: "dropped", label: "dropped", c: { bg: "#e9e3d8", fg: "#867f74", bd: "#e1dcd5" } },
];
const ST = Object.fromEntries(TASK_STATES.map((x) => [x.key, x]));
// A CLI that has printed nothing for this long is parked at its own prompt - the next move
// is yours, not its. Thinking agents print constantly; a question is silence.
export const IDLE_WAITING = 45;
// `waiting` is the server's verdict (the CLI's own screen, silence as fallback); older rows
// without it fall back to the clock here
export const isWaiting = (s) => (s?.waiting ?? (s?.idle >= IDLE_WAITING));
export const busyNow = (t) => (t?.RunStatus === "running")
  || (t?.Session?.alive && !isWaiting(t.Session));
// The ladder, top down: dropped, done, an agent is ACTUALLY running it, else it is yours.
// "in_progress with nothing running" used to read as "agent working" - a task whose agent
// finished without closing it then sat there looking busy and nobody was told.
export const stateOf = (t) => {
  if (!t) return ST.queued;
  if (t.Status === "dropped") return ST.dropped;
  if (t.Status === "done") return ST.done;
  if (busyNow(t)) return ST.working;
  return ST.needs_you;                       // incl. a session sitting at a question
};
export const StateChip = ({ task }) => {
  const st = stateOf(task);
  return <Chip size="small" label={st.label}
    sx={{ bgcolor: st.c.bg, color: st.c.fg, border: `1px solid ${st.c.bd}`, height: 19, fontSize: 10.5, fontWeight: 700 }} />;
};

export const TaskStatusChip = ({ status }) => (
  <Chip size="small" label={status} sx={{ bgcolor: "transparent", border: `1px solid ${TASK_STATUS_COLORS[status] || "#a9a294"}55`,
    color: TASK_STATUS_COLORS[status] || "#a9a294", height: 19, fontSize: 10.5 }} />
);

export const timeAgo = (s) => {
  if (!s) return "";
  const mins = Math.max(0, (Date.now() - asUtc(String(s))) / 60000);
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

// Times are stamped in the SERVER's local time (store.norm_stamp makes every channel land
// there). The `timezone` setting names that zone: with it set, every time wears its short
// label (2:44 PM EDT) and a browser in another zone still reads the stamps correctly -
// naive local strings would otherwise be silently reinterpreted in the viewer's zone.
let TZ = "";
export const loadTz = (settings) => { TZ = (settings.find((s) => s.Name === "timezone") || {}).Value || ""; };
api.get("/api/settings").then(({ data }) => loadTz(data.data || [])).catch(() => {});   // once per page load
const tzOffsetMin = (d) => {
  // what the configured zone's UTC offset was AT that moment (DST-correct), via Intl
  const part = new Intl.DateTimeFormat("en-US", { timeZone: TZ, timeZoneName: "shortOffset" })
    .formatToParts(d).find((p) => p.type === "timeZoneName")?.value || "GMT+0";
  const m = part.replace("GMT", "").match(/([+-]?)(\d+)(?::(\d+))?/) || [0, "+", "0"];
  return (m[1] === "-" ? -1 : 1) * (parseInt(m[2] || 0) * 60 + parseInt(m[3] || 0));
};
const asUtc = (s) => {
  const iso = s.replace(" ", "T");
  if (!TZ) return new Date(iso);                       // blank = this browser IS the server's zone
  try { return new Date(Date.parse(iso + "Z") - tzOffsetMin(new Date(iso + "Z")) * 60000); }
  catch { return new Date(iso); }
};
export const tzLabel = () => {
  if (!TZ) return "";
  try {
    return new Intl.DateTimeFormat("en-US", { timeZone: TZ, timeZoneName: "short" })
      .formatToParts(new Date()).find((p) => p.type === "timeZoneName")?.value || "";
  } catch { return ""; }
};
const tzOpt = () => (TZ ? { timeZone: TZ } : {});   // format in the configured zone, so digits match the label
export const fmtTime12 = (s) => s ? asUtc(s).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit", ...tzOpt() }) : "";
export const tsMs = (s) => s ? asUtc(s).getTime() : 0;      // one clock for everything the Timeline orders (messages, meetings)
export const fmtDateTime = (s) => {
  if (!s) return "";
  const base = asUtc(s).toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit", ...tzOpt() });
  const z = tzLabel();
  return z ? `${base} ${z}` : base;
};
export const localDay = (s) => s ? asUtc(s).toLocaleDateString("sv-SE", tzOpt()) : "";   // YYYY-MM-DD in that zone

// ── Stripe-style two-level navigation atoms (Settings/Docs/Connectors share these) ──
export const Crumb = ({ section, onBack, title }) => (
  <Box sx={{ mb: 2.5 }}>
    <Typography variant="caption" onClick={onBack}
      sx={{ color: "#55697a", fontWeight: 600, cursor: "pointer", "&:hover": { textDecoration: "underline" } }}>
      {section}
    </Typography>
    <Typography sx={{ color: "#2b2a26", fontWeight: 800, fontSize: 20, lineHeight: 1.2, mt: 0.25 }}>{title}</Typography>
  </Box>
);

/* The Docs/Settings shell, lifted out so every tab that has sections wears it: a sticky rail
   on the left, the open section beside it. Connectors and Reports were the last two opening on
   a full-width wall - the layout the rest of the app stopped using - so a search and a section
   list are here rather than copied twice more. `right` renders above the section content, for
   the actions a tab keeps on screen (Sync now, New report). */
export const SideRail = ({ title, note, items, value, onChange, q, setQ, placeholder, children }) => (
  <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", md: "236px minmax(0,1fr)" },
    gap: 3, alignItems: "start", maxWidth: 1320, mx: "auto" }}>
    <Box sx={{ position: { md: "sticky" }, top: { md: 62 } }}>
      <Typography sx={{ color: INK, fontWeight: 700, fontSize: 16, mb: 1.5 }}>{title}</Typography>
      {setQ && (
        <TextField fullWidth placeholder={placeholder} value={q} onChange={(e) => setQ(e.target.value)}
          sx={{ mb: 1.5, bgcolor: "#fff", borderRadius: 2 }}
          InputProps={{ startAdornment: <InputAdornment position="start"><SearchIcon sx={{ fontSize: 17, color: FAINT }} /></InputAdornment> }} />
      )}
      {items.map((it) => {
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

export const LandingCard = ({ icon, title, desc, onOpen }) => (
  <Box onClick={onOpen} sx={{ display: "flex", gap: 1.5, cursor: "pointer", alignItems: "flex-start",
    "&:hover .thubPgTitle": { textDecoration: "underline" } }}>
    <Box sx={{ width: 38, height: 38, borderRadius: 2, bgcolor: "#fff", border: "1px solid #e1dcd5",
      display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0,
      boxShadow: "0 1px 2px rgba(30,50,38,.05)" }}>
      {icon}
    </Box>
    <Box sx={{ minWidth: 0 }}>
      <Typography className="thubPgTitle" sx={{ color: "#55697a", fontWeight: 700, fontSize: 14.5, lineHeight: 1.3 }}>{title}</Typography>
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
    <Box sx={{ width: 54, height: 4, bgcolor: PANEL2, border: "1px solid #e1dcd5", borderRadius: 3, overflow: "hidden", display: "inline-block", mr: 1 }}>
      <Box sx={{ width: `${Math.min(100, (v || 0) * 100)}%`, height: "100%", bgcolor: "#55697a" }} />
    </Box>
  </Tooltip>
);

// Compact filter pill row used across views.
// Segmented control: one contained housing, obviously interactive; the active segment
// fills with its muted color pair {bg, fg, bd} (indigo default), the rest stay quiet.
// THE WAITING ROOM, as a box you can type into from anywhere a task shows. What you think of
// while the agent works goes in here and is typed into its session as one batch the moment it
// stops - never mid-turn, never on top of a question it is waiting on you to answer. The same
// box on the task page, on a Board card and in the Timeline's funnel bar, so the idea goes
// where you are instead of you going to find the room.
export const TellAgent = ({ taskId, taskRef, compact = false, onQueued }) => {
  const [wait, setWait] = React.useState({ data: [], state: null });
  const [text, setText] = React.useState("");
  const [flash, setFlash] = React.useState("");
  const [many, setMany] = React.useState(false);      // paste a list: one prompt per line, queued in order
  const [imgs, setImgs] = React.useState([]);         // screenshots pasted into the box, going with the note
  const [showQ, setShowQ] = React.useState(!compact); // compact folds the queued notes behind their count
  const load = React.useCallback(async () => {
    if (!taskId) return;
    try { setWait((await api.get(`/api/tasks/${taskId}/waitroom`)).data); } catch { setWait({ data: [], state: null }); }
  }, [taskId]);
  React.useEffect(() => { load(); const id = setInterval(load, 15000); return () => clearInterval(id); }, [load]);
  const lines = text.split("\n").map((l) => l.replace(/^\s*(?:[-*•]|\d+[.)])\s*/, "").trim()).filter(Boolean).length;
  // A screenshot pasted in: held here as a thumbnail, uploaded when you queue. The pty carries
  // text only, so the file goes to disk and the note names it - the agent opens it from there.
  const onPaste = (e) => {
    const files = [...(e.clipboardData?.items || [])].filter((i) => i.kind === "file" && /^image\//.test(i.type)).map((i) => i.getAsFile()).filter(Boolean);
    if (!files.length) return;
    e.preventDefault();
    setImgs((s) => [...s, ...files.map((f) => ({ id: Math.random().toString(36).slice(2), file: f, url: URL.createObjectURL(f) }))]);
  };
  const dropImg = (id) => setImgs((s) => { const g = s.find((x) => x.id === id); if (g) URL.revokeObjectURL(g.url); return s.filter((x) => x.id !== id); });
  const queue = async () => {
    if (!text.trim() && !imgs.length) return;
    try {
      const paths = [];
      for (const im of imgs) paths.push((await api.post(`/api/tasks/${taskId}/waitroom/image`, im.file, { headers: { "Content-Type": im.file.type } })).data.path);
      const ref = !paths.length ? "" : `${paths.length === 1 ? "Pasted image - open it with your image/Read tool:" : "Pasted images - open them with your image/Read tool:"} ${paths.map((x) => `"${x}"`).join(" ")}`;
      const body = [text.trim(), ref].filter(Boolean).join(many ? "\n" : " ");
      const { data } = many
        ? await api.post(`/api/tasks/${taskId}/waitroom/bulk`, { text: body })
        : await api.post(`/api/tasks/${taskId}/waitroom`, { text: body });
      imgs.forEach((im) => URL.revokeObjectURL(im.url)); setImgs([]); setText(""); setMany(false);
      if (many) { setFlash(`${data.queued} prompts queued — they drip in one per stop`); setTimeout(() => setFlash(""), 5000); load(); onQueued?.(data); return; }
      setFlash(data.delivered ? (data.state === "restarted" ? "session reopened with it" : "typed in — the agent was parked") : "queued — goes in when the agent stops");
      setTimeout(() => setFlash(""), 4000);
      load(); onQueued?.(data);
    } catch (e) { setFlash(e?.response?.data?.detail || "could not queue it"); }
  };
  const pending = wait.data.filter((w) => !w.DeliveredAt);
  const stateLine = wait.state === "working" ? "agent is working — this waits for its next stop"
    : wait.state === "asking" ? "agent is asking you something — answer it first; this goes in after"
    : wait.state === "parked" ? "agent is parked — this goes straight in"
    : wait.state === "no_session" ? "no live session — this reopens one with your note as the ask" : "";
  // compact has no room for a header line, so the placeholder carries the state instead
  const ph = many ? "One prompt per line — twenty is fine. Bullets and numbers are stripped; they drip in one per stop, in this order."
    : !compact ? "Anything you think of while it works — queued, typed in when it stops. Enter to queue, Shift+Enter for a new line. Paste a screenshot to send it along."
    : wait.state === "asking" ? "It asked you something — answer that first; this goes in after"
    : wait.state === "parked" ? "Tell the agent — goes straight in. Enter to send, paste a screenshot to attach it"
    : wait.state === "no_session" ? "Tell the agent — reopens a session with this as the ask"
    : "Tell the agent — queued, typed in when it stops. Enter to send, paste a screenshot to attach it";
  const input = (
    <TextField fullWidth multiline minRows={many ? 6 : 1} maxRows={many ? 14 : (compact ? 2 : 5)} size="small" value={text} placeholder={ph}
      onChange={(e) => setText(e.target.value)} onPaste={onPaste}
      onKeyDown={(e) => { if (!many && e.key === "Enter" && !e.shiftKey) { e.preventDefault(); queue(); } }}
      sx={{ bgcolor: "#fffdfb", "& .MuiInputBase-input": { fontSize: compact ? 11.5 : 12.5 },
        ...(compact ? { "& .MuiInputBase-root": { py: "3px", px: 1 } } : {}) }} />
  );
  const thumbs = imgs.length > 0 && (
    <Box sx={{ display: "flex", gap: 0.75, flexWrap: "wrap", alignItems: "center", mt: 0.5 }}>
      {imgs.map((im) => (
        <Box key={im.id} sx={{ position: "relative" }}>
          <Box component="img" src={im.url} alt="" sx={{ height: compact ? 28 : 40, borderRadius: 0.75, border: "1px solid #ddd2b9", display: "block" }} />
          <Box onClick={() => dropImg(im.id)} title="remove" sx={{ position: "absolute", top: -5, right: -5, width: 14, height: 14, borderRadius: 99,
            bgcolor: "#6b5f45", color: "#fff", fontSize: 9, lineHeight: "14px", textAlign: "center", cursor: "pointer" }}>×</Box>
        </Box>
      ))}
      <Typography variant="caption" sx={{ color: "#6b5f45", fontSize: 10 }}>
        {imgs.length === 1 ? "goes with the note, as a file the agent opens" : `${imgs.length} images go with the note`}
      </Typography>
    </Box>
  );
  // compact: the open list is capped at about three lines and scrolls - the terminal above is
  // the view, and a long funnel must not eat it a line at a time
  const queued = showQ && pending.length > 0 && (
    <Box sx={{ mt: 0.5, display: "flex", flexDirection: "column", gap: 0.25, ...(compact ? { maxHeight: 58, overflowY: "auto" } : {}) }}>
      {pending.map((w, i) => (
        <Box key={w.WId} sx={{ display: "flex", gap: 0.75, alignItems: "baseline" }}>
          <Typography variant="caption" sx={{ ...mono, color: "#6b5f45", fontSize: 9.5, flexShrink: 0 }}>{i + 1}.</Typography>
          <Typography variant="body2" noWrap={compact} title={w.Note}
            sx={{ fontSize: compact ? 11 : 11.5, flex: 1, minWidth: 0, whiteSpace: compact ? "nowrap" : "pre-wrap", color: INK }}>{w.Note}</Typography>
          <Typography variant="caption" onClick={async () => { await api.delete(`/api/tasks/${taskId}/waitroom/${w.WId}`); load(); }}
            sx={{ color: FAINT, cursor: "pointer", fontSize: 10, "&:hover": { color: "#8a3646" } }}>withdraw</Typography>
        </Box>
      ))}
    </Box>
  );
  // Compact (the wall): ONE row - the terminal is the view, this is a slot under it. The count
  // chip is the only sign of what waits; click it to see (and withdraw) the notes.
  if (compact) {
    return (
      <Box sx={{ bgcolor: "#f1ead9", border: "1px solid #ddd2b9", borderRadius: 1.5, px: 0.75, py: 0.5 }}>
        <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
          <Typography onClick={() => pending.length && setShowQ((v) => !v)}
            title={pending.length ? `${pending.length} note${pending.length === 1 ? "" : "s"} waiting for the agent's next stop — click to ${showQ ? "hide" : "see"} them` : stateLine}
            sx={{ ...mono, fontSize: 9.5, fontWeight: 700, color: "#6b5f45", flexShrink: 0, minWidth: 16, cursor: pending.length ? "pointer" : "default", userSelect: "none" }}>
            ✎{pending.length ? ` ${pending.length}` : ""}
          </Typography>
          {input}
          <MicButton size={15} sx={{ color: "#6b5f45", p: 0.25 }} onText={(t) => setText((s) => (s.trim() ? `${s.trimEnd()} ${t}` : t))} />
          <Button size="small" variant="contained" disableElevation onClick={queue} disabled={!text.trim() && !imgs.length}
            sx={{ bgcolor: "#8a7a5c", "&:hover": { bgcolor: "#6b5f45" }, minWidth: 0, px: 1, py: 0.2, fontSize: 11, lineHeight: 1.4, whiteSpace: "nowrap" }}>Queue</Button>
        </Box>
        {thumbs}
        {flash && <Typography variant="caption" sx={{ color: "#47654a", display: "block", mt: 0.25, fontSize: 10.5 }}>{flash}</Typography>}
        {queued}
      </Box>
    );
  }
  return (
    <Box sx={{ bgcolor: "#f1ead9", border: "1px solid #ddd2b9", borderRadius: 2, p: 1.25 }}>
      <Box sx={{ display: "flex", alignItems: "center", gap: 0.75, mb: 0.5 }}>
        <Typography sx={{ ...mono, fontSize: 9.5, letterSpacing: 1, color: "#6b5f45", fontWeight: 700 }}>
          ✎ TELL THE AGENT{taskRef ? ` · ${taskRef}` : ""}{pending.length ? ` · ${pending.length} in the funnel` : ""}
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
          {many ? `Queue ${lines || ""} prompt${lines === 1 ? "" : "s"}` : "Queue"}</Button>
      </Box>
      {thumbs}
      {flash && <Typography variant="caption" sx={{ color: "#47654a", display: "block", mt: 0.5 }}>{flash}</Typography>}
      {queued}
      {wait.data.some((w) => w.DeliveredAt) && (
        <Typography variant="caption" sx={{ color: FAINT, display: "block", mt: 0.5 }}>
          {wait.data.filter((w) => w.DeliveredAt).length} earlier note{wait.data.filter((w) => w.DeliveredAt).length === 1 ? "" : "s"} already typed in.
        </Typography>
      )}
    </Box>
  );
};

// The same box behind one button, for places with no room for it (a Board card, the funnel bar).
export const TellAgentButton = ({ taskId, taskRef, count = 0, small = false }) => {
  const [open, setOpen] = React.useState(false);
  return (
    <>
      <Box component="span" onClick={(e) => { e.stopPropagation(); setOpen(true); }} title="Tell the agent something — queued until it stops"
        sx={{ display: "inline-flex", alignItems: "center", gap: 0.4, px: small ? 0.6 : 0.9, py: 0.15, borderRadius: 99, cursor: "pointer",
          bgcolor: "#f1ead9", color: "#6b5f45", border: "1px solid #ddd2b9", fontSize: small ? 9.5 : 10.5, fontWeight: 700, whiteSpace: "nowrap",
          "&:hover": { bgcolor: "#e9dfc5" } }}>
        ✎ {count ? `${count} waiting` : "tell the agent"}
      </Box>
      <Dialog open={open} onClose={(e) => { e?.stopPropagation?.(); setOpen(false); }} maxWidth="sm" fullWidth PaperProps={{ sx: { borderRadius: 3, p: 1.5 }, onClick: (e) => e.stopPropagation() }}>
        <TellAgent taskId={taskId} taskRef={taskRef} />
      </Dialog>
    </>
  );
};

// The agent's live session as a black console - the same peephole the Board cards wear, so
// "coder is working this now" is a thing you can SEE moving, not a sentence. Last lines of the
// terminal, the files it has modified, a blinking cursor while it works and a pause mark when
// it has stopped and is waiting on you. Click opens the task's real terminal.
const _elapsed = (since) => {
  if (!since) return "";
  const sec = Math.max(0, (Date.now() - new Date(String(since).replace(" ", "T"))) / 1000);
  return sec < 90 ? `${Math.round(sec)}s` : sec < 5400 ? `${Math.round(sec / 60)}m` : `${(sec / 3600).toFixed(1)}h`;
};
/* ── Said and did: what the agent HOLDS, in the terminal's own colours ─────────────────────
   The Board pane used to show two raw trace lines - nobody read them. This is the same dark pane
   with lines a person checks: the tool in hand (agent · tool · file · seconds), the agent's own
   list with the current item lit, the files it has written hottest first. Fed by /api/runs/live
   -> session.work (taskuary/witness.py: Claude hooks, Codex rollout, git). A pane always says
   which rung it stands on: tool line -> last screen line -> files only. Red is spent on exactly
   one thing: a file written after the agent said done. ── */
const fileName = (p) => String(p || "").split(/[\\/]/).pop();
const secsAgo = (at) => { if (!at) return ""; const s = Math.max(0, (Date.now() - new Date(String(at).replace(" ", "T"))) / 1000); return s < 90 ? `${Math.round(s)}s` : s < 5400 ? `${Math.round(s / 60)}m` : `${(s / 3600).toFixed(1)}h`; };
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
const workHead = (work, who, waiting, asking, startedAt) => {
  if (waiting) return { tone: CATPPUCCIN.yellow, mark: "⏸", text: `${who} ${asking ? "asked you something" : "stopped - waiting on you"}`, tool: "", t: "" };
  if (work?.tool?.name) return { tone: CATPPUCCIN.cyan, mark: "▮", text: who, tool: `${work.tool.name} ${fileName(work.tool.target) || work.tool.target || ""}`.trim(), t: secsAgo(work.tool.at), blink: true };
  if (work?.last_line) return { tone: CATPPUCCIN.cyan, mark: "▮", text: who, tool: `last line: ${work.last_line}`, t: startedAt ? secsAgo(startedAt) : "", blink: true, muted: true };
  return { tone: CATPPUCCIN.cyan, mark: "▮", text: `${who} working`, tool: "", t: startedAt ? secsAgo(startedAt) : "", blink: true };
};

export const WorkPane = ({ run, onOpen }) => {
  // the CLI it runs, not the profile's nickname: a profile called codex that runs claude is claude here
  const work = run?.work || {}, who = run?.cli || run?.AgentName || run?.agent || "agent";
  const waiting = run?.kind === "session" && (run.asking || isWaiting(run));
  const h = workHead(work, who, waiting, run?.asking, run?.StartedAt || run?.started);
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
export const WorkLine = ({ work, who = "agent", waiting = false, asking = false, startedAt }) => {
  const h = workHead(work, who, waiting, asking, startedAt);
  if (!h.tool && !waiting) return null;
  return (
    <Box sx={{ display: "inline-flex", alignItems: "center", gap: 0.6, minWidth: 0, maxWidth: "100%", ...mono, fontSize: 10.5 }}>
      <Box component="span" sx={{ width: 6, height: 6, borderRadius: "50%", flexShrink: 0, bgcolor: waiting ? ROLES.you.solid : ROLES.working.solid,
        ...(waiting ? {} : { "@keyframes tqPulse2": { "50%": { opacity: 0.25 } }, animation: "tqPulse2 1.4s ease-in-out infinite" }) }} />
      <Box component="span" sx={{ fontWeight: 700, color: waiting ? ROLES.you.ink : INK, whiteSpace: "nowrap" }}>{waiting ? h.text : who}</Box>
      {h.tool && <Box component="span" noWrap sx={{ px: 0.6, borderRadius: 0.75, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", minWidth: 0,
        bgcolor: h.muted ? ROLES.muted.tint : ROLES.working.tint, color: h.muted ? ROLES.muted.ink : ROLES.working.ink }}>{h.tool}</Box>}
      {h.t && <Box component="span" sx={{ color: FAINT, flexShrink: 0 }}>{h.t}</Box>}
    </Box>
  );
};

/* The task page's strip: the agent's own list beside the files it wrote, with git's +/- per file,
   reconciled in plain sentences (taskuary/witness.py decides "late" and "stray"; nothing is
   inferred). Provenance pills say where the task came from and who worked it - facts the audit
   chain already held and the card never showed. Polls only while the session is alive. */
const pillSx = (r) => ({ height: 16, fontSize: 9, fontWeight: 700, bgcolor: ROLES[r].tint, color: ROLES[r].ink, border: `1px solid ${ROLES[r].bd}`, "& .MuiChip-label": { px: 0.75 } });
const hhmm = (s) => s ? new Date(String(s).replace(" ", "T")).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" }) : "";
export const WorkStrip = ({ taskId, live }) => {
  const [d, setD] = useState(null);
  // one line by default - the terminal is the page, and a strip that pushed its bottom off screen
  // was worse than no strip; the detail opens on click and stays open for this browser
  const [open, setOpen] = useState(() => { try { return localStorage.getItem("tq.workstrip") === "1"; } catch { return false; } });
  const toggle = () => { setOpen((o) => { try { localStorage.setItem("tq.workstrip", o ? "0" : "1"); } catch { /* private window */ } return !o; }); };
  useEffect(() => {
    if (!taskId) return undefined;
    let alive = true;
    const load = async (diff) => { try { const { data } = await api.get(`/api/tasks/${taskId}/work`, { params: { diff } }); if (alive) setD(data); } catch { /* no session yet */ } };
    load(true);
    // the witness is cheap and polled; git's per-file diff is not, so it refreshes only when the session ends
    const id = live ? setInterval(() => load(false), 5000) : 0;
    return () => { alive = false; clearInterval(id); };
  }, [taskId, live]);
  const w = d?.work;
  if (!d || (!w && !(d.files || []).length)) return null;
  const todos = w?.todos || [], files = (d.files || []).slice(0, 12);
  const tone = { check: "you", note: "info", ok: "done" };
  const who = d.session?.cli || d.session?.agent || d.prov?.by || "agent";
  const checks = (w?.flags || []).filter((f) => f.level === "check").length;
  const summary = `said ${todos.length ? `${w.n_done}/${w.n_todos}` : "—"} · touched ${(d.files || []).length}`;
  return (
    <Box sx={{ mb: 0.75, border: `1px solid ${BORDER}`, borderRadius: 2, bgcolor: PANEL, overflow: "hidden" }}>
      <Box onClick={toggle} title={open ? "Fold the detail away" : "Open: the agent's list beside the files it wrote"}
        sx={{ px: 1.5, py: 0.5, display: "flex", flexWrap: "wrap", gap: 0.5, alignItems: "center", cursor: "pointer", borderBottom: open ? `1px solid ${BORDER}` : 0, "&:hover": { bgcolor: "#faf8f5" } }}>
        <Typography component="span" sx={{ ...mono, fontSize: 10, color: FAINT, width: 12 }}>{open ? "▾" : "▸"}</Typography>
        {d.prov?.from && <Chip size="small" label={`from: ${d.prov.from}`} sx={pillSx("muted")} />}
        {d.prov?.kind && <Chip size="small" label={`kind: ${d.prov.kind}`} sx={pillSx("working")} />}
        {d.prov?.by && <Chip size="small" label={`by: ${who}`} sx={pillSx("working")} />}
        {d.prov?.approved && <Chip size="small" label={`approved by you · ${hhmm(d.prov.approved)}`} sx={pillSx("info")} />}
        {w?.done_at && <Chip size="small" label={`agent said done · ${hhmm(w.done_at)}`} sx={pillSx("done")} />}
        <Chip size="small" label={summary} sx={pillSx("muted")} />
        {checks > 0 && <Chip size="small" label={`${checks} to check`} sx={pillSx("you")} />}
        <Box sx={{ flex: 1 }} />
        {w && <WorkLine work={w} who={who} waiting={false} startedAt={d.session?.started} />}
      </Box>
      {open && <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", md: "1fr 1fr" } }}>
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
            <Typography variant="caption" sx={{ color: DIM }}>{files.length} file{files.length === 1 ? "" : "s"}{d.diffstat?.added != null ? ` · +${d.diffstat.added} −${d.diffstat.removed}` : ""}</Typography>
          </Box>
          {files.map((f) => {
            const top = Math.max(1, ...files.map((x) => x.n || 1));
            return (
              <Box key={f.path} title={f.path} sx={{ display: "grid", gridTemplateColumns: "1fr auto auto 64px", gap: 1, alignItems: "center", py: 0.35, borderBottom: `1px dashed ${BORDER}`,
                "&:last-of-type": { borderBottom: 0 }, color: f.stray ? ROLES.info.ink : INK, opacity: f.late || isHot(f.last) || f.n > 0 ? 1 : 0.7 }}>
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

export const LiveConsole = ({ run, agent, lines = 5, onOpen }) => {
  const waiting = run ? (run.kind === "session" && (run.asking || isWaiting(run))) : false;
  const tail = (run?.tail || []).slice(-lines);
  const files = run?.files || [];
  const who = run?.AgentName || agent || "agent";
  return (
    <Box onClick={onOpen} title="Open the task - the real terminal"
      sx={{ bgcolor: CATPPUCCIN.bg, border: `1px solid ${CATPPUCCIN.surface}`, borderRadius: 1.5, px: 1.25, py: 0.9, cursor: onOpen ? "pointer" : "default",
        "&:hover": onOpen ? { borderColor: CATPPUCCIN.overlay } : {} }}>
      <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: tail.length ? 0.5 : 0 }}>
        <Typography variant="caption" sx={{ ...mono, fontSize: 10.5, fontWeight: 700, color: waiting ? CATPPUCCIN.yellow : CATPPUCCIN.cyan,
          ...(waiting ? {} : { "@keyframes tqBlink2": { "50%": { opacity: 0.25 } }, animation: "tqBlink2 1.1s step-end infinite" }) }}>
          {waiting ? `⏸ ${who} ${run?.asking ? "asked you something" : "stopped - waiting on you"}` : `▮ ${who} working${run?.StartedAt ? ` · ${_elapsed(run.StartedAt)}` : ""}`}
        </Typography>
        <Box sx={{ flex: 1 }} />
        {files.slice(0, 4).map((f) => (
          <Typography key={f} variant="caption" sx={{ ...mono, fontSize: 9, color: CATPPUCCIN.dim, bgcolor: CATPPUCCIN.surface, px: 0.6, borderRadius: 0.75 }}>
            {String(f).split(/[\\/]/).pop()}
          </Typography>
        ))}
        {onOpen && <Typography variant="caption" sx={{ ...mono, fontSize: 9.5, color: CATPPUCCIN.faint }}>open ↗</Typography>}
      </Box>
      {tail.map((l, i, all) => (
        <Typography key={i} noWrap variant="caption" sx={{ ...mono, display: "block", fontSize: 10, lineHeight: 1.55,
          color: l.startsWith("→") ? CATPPUCCIN.blue : l.startsWith("✗") ? CATPPUCCIN.red : CATPPUCCIN.fg, opacity: 0.45 + 0.55 * ((i + 1) / all.length) }}>
          {l.replace(/\n/g, " ")}
        </Typography>
      ))}
      {!tail.length && <Typography variant="caption" sx={{ ...mono, fontSize: 10, color: CATPPUCCIN.faint }}>…</Typography>}
    </Box>
  );
};

export const FilterPills = ({ options, value, onChange }) => (
  <Box sx={{ display: "inline-flex", gap: 0.25, p: 0.4, bgcolor: "#e9e3d8",
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
            <Box component="span" sx={{ px: 0.55, py: 0.05, borderRadius: 99, fontSize: 10, fontWeight: 700,
              fontVariantNumeric: "tabular-nums", lineHeight: 1.5,
              bgcolor: on ? "rgba(255,255,255,.7)" : "#e6e2da", color: on ? c.fg : "#867f74" }}>{o.n}</Box>
          )}
        </Box>
      );
    })}
  </Box>
);
