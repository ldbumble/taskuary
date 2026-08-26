// Shared Task Hub atoms: chips, channel icons, relative time. Light + compact.
import React, { useEffect, useState } from "react";
import { Alert, Box, Button, Chip, CircularProgress, Dialog, DialogActions, DialogContent,
  DialogContentText, DialogTitle, MenuItem, Select, TextField, Tooltip, Typography } from "@mui/material";
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
import { Logo, hasLogo } from "./logos.jsx";
import { ACTION_COLORS, BORDER, CATPPUCCIN, TASK_STATUS_COLORS, mono, DIM, FAINT, INK, PANEL, ACCENT2, PANEL2 } from "./theme.jsx";

// Brand colors so a glance says where a message came from: Teams purple, Outlook blue,
// teal for scheduled reports.
export const CHANNEL_COLORS = { teams: "#6264A7", email: "#0F6CBD", github: "#1c2536", report: "#1f6b64",
  slack: "#611f69", telegram: "#229ED9", whatsapp: "#25D366", ai: "#2f6b4f",
  jira: "#0052CC", asana: "#F06A6A", monday: "#6161FF", clickup: "#7b68ee", todoist: "#e44332",
  gitlab: "#fc6d26", azdo: "#0078d4", linear: "#5e6ad2", trello: "#0079bf", notion: "#37352f",
  discord: "#5865F2", sentry: "#7b6bc9", pagerduty: "#048a24",
  aws: "#ff9900", azure: "#0078d4", database: "#475569", smb_file: "#475569" };
const CHANNEL_ICONS = { teams: GroupsIcon, github: GitHubIcon, report: AssessmentIcon,
  email: MailOutlineIcon, slack: TagIcon, telegram: SendIcon, whatsapp: WhatsAppIcon,
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
  return <Icon sx={{ fontSize: 15, color: CHANNEL_COLORS[channel] || "#9aa39b", ...sx }} />;
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
    sx={{ ...mono, bgcolor: "#e4efe8", color: "#2f6b4f", height: 19, fontSize: 10.5 }} />
) : null;

export const ActionChip = ({ action, reviewStatus, taskStatus, needsYou }) => {
  // A finished task outranks everything else the chip could say.
  if (taskStatus === "done" && reviewStatus !== "pending") {
    return <Chip size="small" label="completed" sx={{ bgcolor: "#eaf1e4", color: "#4d6b3f", height: 19, fontSize: 10.5, fontWeight: 700 }} />;
  }
  // and "nobody is moving this" outranks the verdict: what happened to it matters less
  // than whether it is sitting on you right now
  if (needsYou) {
    return <Chip size="small" label="needs you" sx={{ bgcolor: "#e4efe8", color: "#2f6b4f", border: "1px solid #b6d0c2",
      height: 19, fontSize: 10.5, fontWeight: 700 }} />;
  }
  // What actually matters to the reader: current state, not just the original verdict.
  // 'report' and 'feed' are NOT verdicts - nothing judged those items; they are here to be
  // read. Only 'ignored' means a policy actually rejected something.
  const key = ["report", "feed", "filed"].includes(action) ? action
    : reviewStatus === "auto" ? "auto"
      : reviewStatus === "pending" ? "draft"
        : action || "task_only";
  const c = ACTION_COLORS[key] || ACTION_COLORS.task_only;
  const decided = reviewStatus && !["pending", "auto"].includes(reviewStatus);
  const label = !decided ? c.label : reviewStatus === "no_reply" ? "no reply needed" : `reviewed · ${reviewStatus}`;
  return <Chip size="small" label={label}
    sx={{ bgcolor: decided ? (reviewStatus === "no_reply" ? "#eef1eb" : "#eaf1e4") : c.bg,
      color: decided ? (reviewStatus === "no_reply" ? "#8b938d" : "#4d6b3f") : c.fg, height: 19, fontSize: 10.5 }} />;
};

/* ── Proof of work: the evidence behind a task, so approving is a judgement and not an act
   of faith. Everything here is measured (git, the session's own test output, the checks
   API) - and what is MISSING is stated, because a thin card must never read as a clean
   one. Fetches itself; renders nothing at all for a task with no evidence yet. ── */
const PILL = { ok: { bg: "#eaf1e4", fg: "#4d6b3f" }, bad: { bg: "#f4eae8", fg: "#8f4a41" },
  wait: { bg: "#e4efe8", fg: "#2f6b4f" }, none: { bg: "#eef1eb", fg: "#8b938d" } };
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
              <Typography variant="caption" sx={{ ...mono, color: "#4d6b3f", fontSize: 10 }}>+{f.added}</Typography>
              <Typography variant="caption" sx={{ ...mono, color: "#8f4a41", fontSize: 10 }}>−{f.removed}</Typography>
            </Box>
          ))}
        </Box>
      )}
      {ci?.checks?.failed?.length > 0 && (
        <Box sx={{ mt: 0.5 }}>
          {ci.checks.failed.map((f) => (
            <Typography key={f.name} variant="caption" sx={{ color: "#8f4a41", display: "block", fontSize: 10.5 }}>
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
              sx={{ fontSize: 11, fontWeight: 700, color: "#2f6b4f", textDecoration: "none" }}>
              {ci.kind === "pr" ? "open PR ↗" : "the commit ↗"}
            </Box>
            <Box component="span" onClick={() => !busy && act("ci")}
              sx={{ fontSize: 11, fontWeight: 700, color: busy ? FAINT : "#2f6b4f", cursor: "pointer" }}>
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
              sx={{ fontSize: 11, fontWeight: 700, color: busy ? FAINT : "#2f6b4f", cursor: "pointer" }}>
              {busy === "land" ? "landing…" : p.flow === "direct" ? "push straight to the branch" : "open a draft PR"}
            </Box>
            <Box component="span" onClick={() => !busy && act(`land?flow=${p.flow === "direct" ? "pr" : "direct"}`)}
              title="just this once, the other way"
              sx={{ fontSize: 11, color: busy ? FAINT : FAINT, cursor: "pointer", "&:hover": { color: "#2f6b4f" } }}>
              {p.flow === "direct" ? "or a draft PR" : "or push direct"}
            </Box>
          </>
        )}
        {onOpenTask && (
          <Box component="span" onClick={() => onOpenTask(taskId)}
            sx={{ fontSize: 11, fontWeight: 700, color: "#2f6b4f", cursor: "pointer" }}>the whole session</Box>
        )}
      </Box>
      {p.error && <Typography variant="caption" sx={{ color: "#8f4a41", display: "block", mt: 0.5 }}>{p.error}</Typography>}
    </Box>
  );
};

export const StatusDot = ({ ok, warn }) => (
  <Box component="span" sx={{ display: "inline-block", width: 8, height: 8, borderRadius: "50%", mr: 1,
    bgcolor: ok ? "#22c55e" : warn ? "#2f6b4f" : "#cdd5c8" }} />
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
    ? { color: "#1c2536", fontWeight: 700, bgcolor: "#eef1eb" }
    : l.startsWith("@@") ? { color: "#1f6b64", bgcolor: "#e2efed" }
      : l.startsWith("+") ? { color: "#4d6b3f", bgcolor: "#eaf1e4" }
        : l.startsWith("-") ? { color: "#8f4a41", bgcolor: "#f4eae8" }
          : { color: "#5e685f" };
  return (
    <Box sx={{ border: "1px solid #dce1d8", borderRadius: 1.5, overflow: "auto", maxHeight: 360, bgcolor: "#fff" }}>
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
              bgcolor: "#f7f9f5", "&:hover": { bgcolor: "#f4f7f1" } }}>
            <ChevronRightIcon sx={{ fontSize: 16, color: FAINT, flexShrink: 0,
              transform: open.has(i) ? "rotate(90deg)" : "none", transition: "transform .12s" }} />
            <Typography sx={{ ...mono, fontSize: 11.5, color: INK, flex: 1, minWidth: 0,
              overflow: "hidden", textOverflow: "ellipsis", direction: "rtl", textAlign: "left" }}>
              {f.path}
            </Typography>
            {/* the two numbers people actually scan a file list for */}
            <Typography sx={{ ...mono, fontSize: 11, color: "#4d6b3f", fontVariantNumeric: "tabular-nums" }}>+{f.added}</Typography>
            <Typography sx={{ ...mono, fontSize: 11, color: "#8f4a41", fontVariantNumeric: "tabular-nums" }}>−{f.removed}</Typography>
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
const REPORT_COLORS = { Triage: "#1f6b64", Determination: "#1f6b64", Actions: "#2f6b4f", Summary: "#4d6b3f",
  Found: "#1f6b64", Did: "#2f6b4f", Next: "#1f6b64" };
/* The four things you can do with a timeline item were four buttons of four different sizes
   and colours, two rows apart, half of them right-aligned - so the reader had to hunt for
   the set. One list, one shape per row: what it is, and what it does. */
export const ChoiceRow = ({ icon, label, hint, tint = "#e4efe8", onClick, first, busy }) => (
  <Box onClick={busy ? undefined : onClick}
    sx={{ display: "flex", alignItems: "center", gap: 1.1, px: 1.25, py: 0.7, cursor: busy ? "default" : "pointer",
      borderTop: first ? "none" : `1px solid ${BORDER}`, transition: "background .12s",
      "&:hover": { bgcolor: busy ? "transparent" : "#f7f9f5" }, "&:hover .thubChoiceGo": { opacity: 1, transform: "none" } }}>
    <Box sx={{ width: 24, height: 24, borderRadius: 1.5, bgcolor: tint, flexShrink: 0,
      display: "flex", alignItems: "center", justifyContent: "center" }}>{icon}</Box>
    <Box sx={{ flex: 1, minWidth: 0 }}>
      <Typography variant="body2" sx={{ color: INK, fontWeight: 600, lineHeight: 1.3 }}>{label}</Typography>
      {hint && <Typography variant="caption" sx={{ color: FAINT, display: "block", lineHeight: 1.25, fontSize: 10.5 }}>{hint}</Typography>}
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
      <Typography variant="caption" sx={{ color: "#4d6b3f", fontWeight: 600, display: "block" }}>
        ✓ noted — triage will apply this to{" "}
        {saved.scope === "global" ? "every sender" : saved.scope === "subject" ? `any mail about “${saved.scopeKey}”` : saved.scopeKey}
        {" "}from now on
      </Typography>
      {/* the verdict works from here on; tasks opened BEFORE it are still sitting there, and
          saying nothing about them is how a fix reads as "still not learning" */}
      {!!saved.alsoCovered?.length && (
        <Typography variant="caption" sx={{ color: "#2f6b4f", display: "block", mt: 0.25 }}>
          {saved.alsoCovered.length} open task{saved.alsoCovered.length === 1 ? "" : "s"} already match it
          ({saved.alsoCovered.slice(0, 4).map((t) => `TQ-${String(t.taskId).padStart(4, "0")}`).join(", ")}
          {saved.alsoCovered.length > 4 ? ", …" : ""}) — close them the same way if they are not yours either.
        </Typography>
      )}
    </Box>
  );
  if (!open) return row ? (
    <ChoiceRow first={first} tint="#eef1eb" onClick={() => setOpen(true)}
      icon={<BlockIcon sx={{ fontSize: 15, color: "#8b938d" }} />}
      label="Not our task" hint="say why once — triage remembers it for this topic, or this sender" />
  ) : (
    <Button size="small" sx={{ color: "#8b938d", fontSize: 11 }} onClick={() => setOpen(true)}
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
      <SmartToyIcon sx={{ fontSize: 15, color: "#4d6b3f" }} />
      <Typography variant="caption" sx={{ color: "#4d6b3f", fontWeight: 600 }}>
        {sent.agent} is on it in a live session — {sent.ref}
      </Typography>
      <Button size="small" sx={{ fontSize: 11 }} onClick={() => onOpenTask?.(sent.taskId)}>watch it live →</Button>
      <Button size="small" sx={{ fontSize: 11, color: DIM }} onClick={() => setSent(null)}>send another</Button>
    </Box>
  );
  if (!open) return row ? (
    <ChoiceRow first={first} tint="#e2efed" onClick={() => setOpen(true)}
      icon={<SmartToyIcon sx={{ fontSize: 15, color: "#1f6b64" }} />}
      label="Send it to a coding agent" hint="opens a live session on a new task — you watch it work" />
  ) : (
    <Button size="small" startIcon={<SmartToyIcon sx={{ fontSize: 14 }} />} onClick={() => setOpen(true)}
      sx={{ fontSize: 11.5, color: "#1f6b64" }}>Send to coding agent</Button>
  );
  return (
    <Box sx={{ mt: 1, p: 1.25, bgcolor: "#faf8ff", border: "1px solid #e9ddfb", borderRadius: 1.5 }}>
      <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 0.75, flexWrap: "wrap" }}>
        <SmartToyIcon sx={{ fontSize: 15, color: "#1f6b64" }} />
        <Typography variant="caption" sx={{ color: "#1f6b64", fontWeight: 700 }}>Send to an agent</Typography>
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
          sx={{ fontSize: 11.5, bgcolor: "#1f6b64", "&:hover": { bgcolor: "#6b1fb0" } }}>
          {busy ? "sending…" : "Send"}
        </Button>
      </Box>
      {err && <Typography variant="caption" sx={{ color: "#8f4a41", display: "block", mt: 0.5 }}>{err}</Typography>}
    </Box>
  );
};

/* Task status, review status and run status were three ladders the reader had to combine
   in their head ("in_progress + reviewed·rejected" — so is it mine or not?). This is the
   one answer: what does this task need from ME, right now. Everything shows this. */
export const TASK_STATES = [
  { key: "needs_you", label: "needs you", c: { bg: "#e4efe8", fg: "#2f6b4f", bd: "#b6d0c2" } },
  { key: "working", label: "agent working", c: { bg: "#e2efed", fg: "#1f6b64", bd: "#bcd9d5" } },
  { key: "queued", label: "queued", c: { bg: "#e4efe8", fg: "#2f6b4f", bd: "#b6d0c2" } },
  { key: "done", label: "done", c: { bg: "#eaf1e4", fg: "#4d6b3f", bd: "#cbe8d6" } },
  { key: "dropped", label: "dropped", c: { bg: "#eef1eb", fg: "#8b938d", bd: "#dce1d8" } },
];
const ST = Object.fromEntries(TASK_STATES.map((x) => [x.key, x]));
// A CLI that has printed nothing for this long is parked at its own prompt - the next move
// is yours, not its. Thinking agents print constantly; a question is silence.
export const IDLE_WAITING = 45;
export const busyNow = (t) => (t?.RunStatus === "running")
  || (t?.Session?.alive && t.Session.idle < IDLE_WAITING);
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
  <Chip size="small" label={status} sx={{ bgcolor: "transparent", border: `1px solid ${TASK_STATUS_COLORS[status] || "#9aa39b"}55`,
    color: TASK_STATUS_COLORS[status] || "#9aa39b", height: 19, fontSize: 10.5 }} />
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
      sx={{ color: "#2f6b4f", fontWeight: 600, cursor: "pointer", "&:hover": { textDecoration: "underline" } }}>
      {section}
    </Typography>
    <Typography sx={{ color: "#1c2536", fontWeight: 800, fontSize: 20, lineHeight: 1.2, mt: 0.25 }}>{title}</Typography>
  </Box>
);

export const UnderTabs = ({ tabs, value, onChange }) => (
  <Box sx={{ display: "flex", gap: 2.5, borderBottom: "1px solid #dce1d8", mb: 2, overflowX: "auto" }}>
    {tabs.map((t) => (
      <Box key={t} onClick={() => onChange(t)}
        sx={{ pb: 1, cursor: "pointer", fontSize: 13, fontWeight: 600, mb: "-1px", flexShrink: 0,
          color: value === t ? "#2f6b4f" : DIM,
          borderBottom: `2px solid ${value === t ? "#2f6b4f" : "transparent"}`,
          "&:hover": { color: "#1c2536" } }}>
        {t}
      </Box>
    ))}
  </Box>
);

export const LandingCard = ({ icon, title, desc, onOpen }) => (
  <Box onClick={onOpen} sx={{ display: "flex", gap: 1.5, cursor: "pointer", alignItems: "flex-start",
    "&:hover .thubPgTitle": { textDecoration: "underline" } }}>
    <Box sx={{ width: 38, height: 38, borderRadius: 2, bgcolor: "#fff", border: "1px solid #dce1d8",
      display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0,
      boxShadow: "0 1px 2px rgba(30,50,38,.05)" }}>
      {icon}
    </Box>
    <Box sx={{ minWidth: 0 }}>
      <Typography className="thubPgTitle" sx={{ color: "#2f6b4f", fontWeight: 700, fontSize: 14.5, lineHeight: 1.3 }}>{title}</Typography>
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
    <Box sx={{ width: 54, height: 4, bgcolor: PANEL2, border: "1px solid #dce1d8", borderRadius: 3, overflow: "hidden", display: "inline-block", mr: 1 }}>
      <Box sx={{ width: `${Math.min(100, (v || 0) * 100)}%`, height: "100%", bgcolor: "#2f6b4f" }} />
    </Box>
  </Tooltip>
);

// Compact filter pill row used across views.
// Segmented control: one contained housing, obviously interactive; the active segment
// fills with its muted color pair {bg, fg, bd} (indigo default), the rest stay quiet.
export const FilterPills = ({ options, value, onChange }) => (
  <Box sx={{ display: "inline-flex", gap: 0.25, p: 0.4, bgcolor: "#f4f7f1",
    border: "1px solid #dce1d8", borderRadius: 2.5 }}>
    {options.map((o) => {
      const key = o.key ?? o, on = value === key;
      const c = o.c || { bg: "#e4efe8", fg: "#2f6b4f", bd: "#b6d0c2" };
      return (
        <Box key={key} onClick={() => onChange(key)}
          sx={{ px: 1.25, py: 0.45, borderRadius: 1.75, cursor: "pointer", fontSize: 11.5,
            display: "inline-flex", alignItems: "center", gap: 0.55,
            fontWeight: on ? 700 : 500, lineHeight: 1.4, userSelect: "none", whiteSpace: "nowrap",
            bgcolor: on ? c.bg : "transparent", color: on ? c.fg : DIM,
            border: `1px solid ${on ? c.bd : "transparent"}`,
            boxShadow: on ? "0 1px 2px rgba(30,50,38,.08)" : "none",
            transition: "all .15s", "&:hover": on ? {} : { bgcolor: "#e9ecf1", color: "#1c2536" } }}>
          {o.label ?? (o || "all")}
          {/* the count is a BADGE, not the last word of the label - glued on with a space,
              "needs you 2" reads as one phrase and the number disappears into the name */}
          {o.n != null && (
            <Box component="span" sx={{ px: 0.55, py: 0.05, borderRadius: 99, fontSize: 10, fontWeight: 700,
              fontVariantNumeric: "tabular-nums", lineHeight: 1.5,
              bgcolor: on ? "rgba(255,255,255,.7)" : "#e3e7ee", color: on ? c.fg : "#8b938d" }}>{o.n}</Box>
          )}
        </Box>
      );
    })}
  </Box>
);
