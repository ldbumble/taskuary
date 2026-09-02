// Taskuary design system - "Beacon": warm oat paper, slate-blue brand, sage second, and ONE
// loud colour reserved for the only thing that ever needs you. Hairline borders, small quiet
// type, no decoration that carries meaning.
import { createTheme } from "@mui/material/styles";

// Contrast is the design: near-black ink, secondary text you can actually read, and the
// gray reserved for what is truly tertiary. The old DIM/FAINT washed the review panel's
// blurbs into fog at README scale - quiet, not illegible.
export const BG = "#f6f4f1";           // page canvas - a cool paper, not grey
export const PANEL = "#fffdfb";        // cards - warm white, not clinical white
export const PANEL2 = "#e9e3d8";       // inset panels / code-ish blocks
export const BORDER = "#e1dcd5";
export const INK = "#262521";          // primary text - near black, faintly warm
export const DIM = "#4d4a43";          // secondary text - readable, not fog
export const FAINT = "#6e685f";        // tertiary (timestamps, rails) - twice darkened: the first two
                                       // passes still read as fog against oat paper
export const ACCENT = "#55697a";       // slate blue - the brand: chrome, links, buttons
export const ACCENT2 = "#6f8a6e";      // sage - section labels, secondary emphasis
export const GRADIENT = `linear-gradient(90deg, ${ACCENT}, #7d9a7c)`;
// The assistant shares the sync control's slate-to-sage family: the sage end identifies its
// posts without the old light-blue wash, and primary actions use the exact same gradient.
// The tint and border sit close to the paper on purpose: a saturated green panel among cream
// cards read as a warning rather than as a voice (the owner, 2026-08-30 - "make it more subtle
// like the rest of the colors"). Identity comes from the dot, the icon and the label, which stay
// sage; the surfaces stay quiet. Timeline rows take no assistant tint at all.
export const ASSISTANT = {
  solid: "#7d9a7c", ink: "#526b53", tint: "#f3f5f0", bd: "#dde1d6", gradient: GRADIENT,
};

/* The one loud colour, and the whole point of this palette: ALERT means "this is on you" and
   is spent on nothing else. It is deliberately COOLER than the paper - a warm red on warm oat
   has no temperature contrast to separate it, which is how two earlier passes came out looking
   first like salmon and then like a stain. Oxblood is the answer: dark and muted enough to read
   as deliberate rather than as a warning light, and pulled far enough toward the slate that it
   shares a family with the blue-grey instead of arguing with it. It is the only saturated thing
   on the screen. */
export const ALERT = "#8a3646";        // oxblood - solid: dots, badges, the needs-you pill
export const ALERT_INK = "#7a2f3c";    // text on a tint
export const ALERT_TINT = "#f3e6e8";   // the tint, mixed toward the paper
export const ALERT_BD = "#e0c6cb";

/* ── ROLES: one colour per MEANING, and nothing else decides a colour ────────────────────
   The bug this fixes is not any single hex. It is that "in progress" was wearing the
   needs-you red, "report" and "inbound" were wearing a cool grey-green on warm paper, and
   every chip picked its own pair by hand - so the same meaning looked different in three
   tabs and different meanings looked the same in one. Seven roles, each with a solid (dots,
   badges, the one loud pill), an ink (text on a tint), a tint and a border. Everything that
   carries meaning reads from here; anything not in this table does not get to be coloured. */
export const ROLES = {
  you:     { solid: ALERT,     ink: ALERT_INK, tint: ALERT_TINT, bd: ALERT_BD },   // it is on YOU
  working: { solid: "#55697a", ink: "#41525f", tint: "#e4e9ee",  bd: "#cbd4dc" },  // an agent has it
  handled: { solid: "#6f8a6e", ink: "#4c6450", tint: "#e4ebe2",  bd: "#cdd9cb" },  // done for you
  done:    { solid: "#47654a", ink: "#3c5740", tint: "#e2ebe0",  bd: "#c9dcc8" },  // finished
  info:    { solid: "#8a7a5c", ink: "#6b5f45", tint: "#eee7d6",  bd: "#ddd2b9" },  // a report, to read
  muted:   { solid: "#a09787", ink: "#6f6960", tint: "#e6e0d5",  bd: "#dad3c5" },  // filed, ignored
  bad:     { solid: "#7e2d2d", ink: "#7e2d2d", tint: "#f4e7e5",  bd: "#e2c6c2" },  // failed, rejected
};

const role = (r, label) => ({ bg: ROLES[r].tint, fg: ROLES[r].ink, label });
export const ACTION_COLORS = {
  auto: role("handled", "auto-answered"),
  draft: role("you", "needs review"),          // drafted, still yours to send
  ignore: role("muted", "ignored"),
  report: role("info", "report"),
  feed: role("info", "info"),
  filed: role("muted", "filed"),
  skip: role("muted", "skipped"),
  task_only: role("working", "task created"),
  triaging: role("muted", "triaging…"),          // shown first, decided next (ingest.deferred)
};
// What a message IS - triage's verdict in one word (taskuary/categories.py decides it). 'info'
// is GREEN because a person told you something; the same "nothing to do" from a mailing list
// is 'promo' and grey - a colleague's FYI and a vendor's newsletter must not wear the same tag.
export const TAGS = {
  coding:    { ...role("working", "coding"),   hint: "sent to the coding agent" },
  todo:      { ...role("working", "to do"),    hint: "real work, on your own list - not code" },
  review:    { ...role("you", "review"),       hint: "a reply is drafted for you to send" },
  info:      { ...role("done", "info"),        hint: "a person told you something; nothing to do" },
  automated: { ...role("info", "automated"),   hint: "a system told you something; nothing to do" },
  promo:     { ...role("muted", "promo"),      hint: "marketing or a newsletter - skim past" },
  filed:     { ...role("muted", "filed"),      hint: "kept; triage found nothing to do" },
  ignored:   { ...role("muted", "ignored"),    hint: "a policy, or you, said no" },
  report:    { ...role("info", "report"),      hint: "a scheduled report - hover to read the summary" },
  feed:      { ...role("info", "feed"),        hint: "shown for information - this connection is a feed" },
  yours:     { ...role("handled", "your reply"), hint: "you sent this - kept so the thread shows both sides" },
  triaging:  { ...role("muted", "triaging…"),  hint: "on the timeline first - triage is deciding" },
  assistant: { bg: ASSISTANT.tint, fg: ASSISTANT.ink, label: "assistant",
    hint: "the assistant's own post - what it noticed and what it would do; open it to talk back or act" },
};

// Catppuccin Mocha — the palette the Claude Code / Codex theme plugins use, so a session
// looks the same in Taskuary as it does in your own terminal. Full 16-colour ANSI set:
// agent TUIs paint spinners, diffs and boxes with these, and a partial palette washes out.
export const CATPPUCCIN = {
  bg: "#1e1e2e", bgAlt: "#181825", fg: "#cdd6f4", dim: "#a6adc8", faint: "#6c7086",
  surface: "#313244", overlay: "#585b70", cursor: "#f5e0dc",
  red: "#f38ba8", green: "#a6e3a1", yellow: "#f9e2af", blue: "#89b4fa",
  magenta: "#f5c2e7", cyan: "#94e2d5", mauve: "#cba6f7", peach: "#fab387",
};
export const XTERM_THEME = {
  background: CATPPUCCIN.bg, foreground: CATPPUCCIN.fg, cursor: CATPPUCCIN.cursor,
  cursorAccent: CATPPUCCIN.bg, selectionBackground: CATPPUCCIN.overlay, selectionForeground: "#ffffff",
  black: "#45475a", red: CATPPUCCIN.red, green: CATPPUCCIN.green, yellow: CATPPUCCIN.yellow,
  blue: CATPPUCCIN.blue, magenta: CATPPUCCIN.magenta, cyan: CATPPUCCIN.cyan, white: "#bac2de",
  brightBlack: CATPPUCCIN.overlay, brightRed: "#f38ba8", brightGreen: "#a6e3a1", brightYellow: "#f9e2af",
  brightBlue: "#89b4fa", brightMagenta: "#f5c2e7", brightCyan: "#94e2d5", brightWhite: "#f5f5f7",
  // xterm's default slider is 20% white on a dark pane - invisible, so a session that scrolls
  // perfectly well reads as "I cannot scroll back". These are opaque enough to see and grab.
  scrollbarSliderBackground: "#5c6378", scrollbarSliderHoverBackground: "#7b83a0",
  scrollbarSliderActiveBackground: "#9aa2c0",
};

export const TASK_STATUS_COLORS = {
  open: ROLES.muted.solid, in_progress: ROLES.working.solid, waiting: ROLES.you.solid,
  done: ROLES.done.solid, dropped: ROLES.muted.solid,
};

export const theme = createTheme({
  palette: {
    mode: "light",
    background: { default: BG, paper: PANEL },
    primary: { main: ACCENT },
    secondary: { main: ACCENT2 },
    text: { primary: INK, secondary: DIM },
    divider: BORDER,
  },
  typography: {
    fontFamily: "'IBM Plex Sans', 'Segoe UI', system-ui, sans-serif",
    fontSize: 12.5,
    body2: { fontSize: 12.5 },
    caption: { fontSize: 11 },
    subtitle2: { fontSize: 12.5 },
  },
  shape: { borderRadius: 8 },
  components: {
    MuiCssBaseline: { styleOverrides: {
      // Windows paints a classic scrollbar - arrow buttons and all - on every box that can
      // scroll, and a box that overflows by a pixel shows up as a pair of stray arrows at
      // its edge. Thin, arrowless, the app's own colour, everywhere; nothing else changes.
      // Chromium ignores the ::-webkit-scrollbar rules once scrollbar-width is set, so the
      // standard property is for Firefox only; Edge and Chrome take the webkit rules below
      "@supports not selector(::-webkit-scrollbar)": { "*": { scrollbarWidth: "thin", scrollbarColor: "#d3ccc1 transparent" } },
      "*::-webkit-scrollbar": { width: 8, height: 8 },
      "*::-webkit-scrollbar-thumb": { backgroundColor: "#d3ccc1", borderRadius: 8 },
      "*::-webkit-scrollbar-track": { background: "transparent" },
      "*::-webkit-scrollbar-button": { display: "none", width: 0, height: 0 },
      "*::-webkit-scrollbar-corner": { background: "transparent" },
    } },
    MuiPaper: { styleOverrides: { root: { backgroundImage: "none", border: `1px solid ${BORDER}`, boxShadow: "none" } } },
    MuiButton: {
      styleOverrides: {
        root: { textTransform: "none", fontWeight: 600, fontSize: 12.5, borderRadius: 8 },
        contained: { boxShadow: "none", "&:hover": { boxShadow: "0 2px 8px rgba(47,107,79,.25)" } },
      },
    },
    MuiChip: { styleOverrides: { root: { fontWeight: 600 } } },
    MuiTextField: { defaultProps: { size: "small" } },
    MuiSelect: { defaultProps: { size: "small" } },
    MuiTooltip: { styleOverrides: { tooltip: { backgroundColor: INK, fontSize: 11.5, borderRadius: 6, padding: "6px 10px" } } },
    MuiDialog: {
      styleOverrides: {
        paper: { borderRadius: 16, border: `1px solid ${BORDER}`, boxShadow: "0 24px 60px rgba(30,50,38,.18)", padding: 4 },
      },
      defaultProps: { slotProps: { backdrop: { sx: { backgroundColor: "rgba(30,50,38,.35)", backdropFilter: "blur(3px)" } } } },
    },
    MuiDialogTitle: { styleOverrides: { root: { fontSize: 15, fontWeight: 700, paddingBottom: 4 } } },
    MuiDrawer: {
      styleOverrides: { paper: { boxShadow: "-12px 0 40px rgba(30,50,38,.12)", borderTopLeftRadius: 16, borderBottomLeftRadius: 16 } },
      defaultProps: { slotProps: { backdrop: { sx: { backgroundColor: "rgba(30,50,38,.25)", backdropFilter: "blur(2px)" } } } },
    },
    MuiMenu: { styleOverrides: { paper: { borderRadius: 10, border: `1px solid ${BORDER}`, boxShadow: "0 8px 24px rgba(30,50,38,.12)" } } },
    MuiSwitch: { defaultProps: { size: "small" } },
    // the hand-raise toast: MUI's default is a black bar, the one thing on the screen not from
    // this palette. Paper, ink, a hairline and a soft shadow - a note left on the desk, not a siren
    MuiSnackbarContent: { styleOverrides: { root: { backgroundColor: PANEL, color: INK, border: `1px solid ${BORDER}`,
      boxShadow: "0 10px 28px rgba(30,50,38,.14)", borderRadius: 10, fontSize: 12.5, fontWeight: 500, maxWidth: 520 } } },
  },
});

export const mono = { fontFamily: "'IBM Plex Mono', 'Cascadia Code', Consolas, monospace" };
// Compact modern select styling, shared by the detail-header dropdowns and the hand-off form.
export const selSx = { fontSize: 12.5, bgcolor: "#fff", borderRadius: 2,
  "& .MuiOutlinedInput-notchedOutline": { borderColor: BORDER },
  "&:hover .MuiOutlinedInput-notchedOutline": { borderColor: "#d8cfbe" },
  "&.Mui-focused .MuiOutlinedInput-notchedOutline": { borderColor: ACCENT } };
export const card = { bgcolor: PANEL, border: `1px solid ${BORDER}`, borderRadius: 2, p: 1.5,
  boxShadow: "0 1px 2px rgba(30,50,38,.04)" };
// Double-border frame: a soft gray mat around a white card (layered, Linear/Arc-style).
// Use for the big detail surfaces - review panel, task detail - so they read as raised.
export const frame = { p: 0.75, bgcolor: "#eae5dd", border: "1px solid #dad4cb", borderRadius: 3,
  boxShadow: "0 14px 44px rgba(30,50,38,.12)" };
export const frameInner = { bgcolor: PANEL, border: `1px solid ${BORDER}`, borderRadius: 2.25, overflow: "hidden" };

export const hoverable = {
  transition: "box-shadow .15s, border-color .15s",
  "&:hover": { borderColor: "#d8cfbe", boxShadow: "0 2px 8px rgba(47,107,79,.10)", cursor: "pointer" },
};
// Feed entrance: quiet slide-up fade, staggered per row by animationDelay at the call site.
export const fadeIn = {
  "@keyframes thubFadeIn": { from: { opacity: 0, transform: "translateY(6px)" }, to: { opacity: 1, transform: "none" } },
  animation: "thubFadeIn .35s ease both",
};

// Muted segmented-pill color pairs - the Timeline filter treatment, shared by every tab.
// the old names (amber/teal/green/gray/red/purple) said what a pill LOOKED like, which is how
// "in progress" ended up wearing the needs-you red. These say what it MEANS.
const pill = (r) => ({ bg: ROLES[r].tint, fg: ROLES[r].ink, bd: ROLES[r].bd });
export const PILL_COLORS = {
  // `pick` carries NO meaning: it is "this is the filter you have selected", for controls that
  // choose a SUBSET rather than report a state. Source-kind filters (code, boards, alerts) are
  // that: giving them state colours said an alerts feed was failing and a code feed was busy.
  pick: { bg: "#e6e0d5", fg: "#33302a", bd: "#d3cabb" },
  you: pill("you"), working: pill("working"), handled: pill("handled"),
  done: pill("done"), info: pill("info"), gray: pill("muted"), bad: pill("bad"),
  // kept so nothing breaks mid-rename, but pointed at the right meaning
  amber: pill("you"), teal: pill("working"), green: pill("done"), red: pill("bad"), purple: pill("working"),
};
