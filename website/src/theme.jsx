// Task Hub design system - clean, light, compact enterprise workspace (Linear/Notion-ish):
// soft gray canvas, white cards, hairline borders, one indigo accent, small quiet type.
import { createTheme } from "@mui/material/styles";

export const BG = "#f6f7f9";           // page canvas
export const PANEL = "#ffffff";        // cards
export const PANEL2 = "#f4f5f7";       // inset panels / code-ish blocks
export const BORDER = "#e5e8ee";
export const INK = "#1c2536";          // primary text
export const DIM = "#697386";          // secondary text
export const FAINT = "#98a1b3";        // tertiary (timestamps, rails)
export const ACCENT = "#4f46e5";       // indigo
export const ACCENT2 = "#0e7490";      // deep teal (labels, links)
export const GRADIENT = `linear-gradient(90deg, ${ACCENT}, #7c6cf0)`;

export const ACTION_COLORS = {
  auto: { bg: "#e6f7fb", fg: "#0e7490", label: "auto-answered" },
  draft: { bg: "#fef4e6", fg: "#b45309", label: "needs review" },
  escalate: { bg: "#fdecec", fg: "#b91c1c", label: "escalated" },
  ignore: { bg: "#eef0f3", fg: "#8a94a6", label: "ignored" },
  report: { bg: "#e6f7fb", fg: "#0e7490", label: "report" },
  feed: { bg: "#eef7f0", fg: "#15803d", label: "info" },
  filed: { bg: "#eef0f3", fg: "#8a94a6", label: "filed" },
  skip: { bg: "#f4f0f6", fg: "#7e5f8f", label: "skipped" },
  task_only: { bg: "#eef0ff", fg: "#4f46e5", label: "task created" },
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
};

export const TASK_STATUS_COLORS = {
  open: "#4f46e5", in_progress: "#b45309", waiting: "#7e22ce", done: "#15803d", dropped: "#8a94a6",
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
    fontFamily: "'Inter', 'Segoe UI', system-ui, sans-serif",
    fontSize: 12.5,
    body2: { fontSize: 12.5 },
    caption: { fontSize: 11 },
    subtitle2: { fontSize: 12.5 },
  },
  shape: { borderRadius: 8 },
  components: {
    MuiPaper: { styleOverrides: { root: { backgroundImage: "none", border: `1px solid ${BORDER}`, boxShadow: "none" } } },
    MuiButton: {
      styleOverrides: {
        root: { textTransform: "none", fontWeight: 600, fontSize: 12.5, borderRadius: 8 },
        contained: { boxShadow: "none", "&:hover": { boxShadow: "0 2px 8px rgba(79,70,229,.25)" } },
      },
    },
    MuiChip: { styleOverrides: { root: { fontWeight: 600 } } },
    MuiTextField: { defaultProps: { size: "small" } },
    MuiSelect: { defaultProps: { size: "small" } },
    MuiTooltip: { styleOverrides: { tooltip: { backgroundColor: INK, fontSize: 11.5, borderRadius: 6, padding: "6px 10px" } } },
    MuiDialog: {
      styleOverrides: {
        paper: { borderRadius: 16, border: `1px solid ${BORDER}`, boxShadow: "0 24px 60px rgba(16,24,40,.18)", padding: 4 },
      },
      defaultProps: { slotProps: { backdrop: { sx: { backgroundColor: "rgba(16,24,40,.35)", backdropFilter: "blur(3px)" } } } },
    },
    MuiDialogTitle: { styleOverrides: { root: { fontSize: 15, fontWeight: 700, paddingBottom: 4 } } },
    MuiDrawer: {
      styleOverrides: { paper: { boxShadow: "-12px 0 40px rgba(16,24,40,.12)", borderTopLeftRadius: 16, borderBottomLeftRadius: 16 } },
      defaultProps: { slotProps: { backdrop: { sx: { backgroundColor: "rgba(16,24,40,.25)", backdropFilter: "blur(2px)" } } } },
    },
    MuiMenu: { styleOverrides: { paper: { borderRadius: 10, border: `1px solid ${BORDER}`, boxShadow: "0 8px 24px rgba(16,24,40,.12)" } } },
    MuiSwitch: { defaultProps: { size: "small" } },
  },
});

export const mono = { fontFamily: "'JetBrains Mono', 'Cascadia Code', Consolas, monospace" };
// Compact modern select styling, shared by the detail-header dropdowns and the hand-off form.
export const selSx = { fontSize: 12.5, bgcolor: "#fff", borderRadius: 2,
  "& .MuiOutlinedInput-notchedOutline": { borderColor: BORDER },
  "&:hover .MuiOutlinedInput-notchedOutline": { borderColor: "#c9cff0" },
  "&.Mui-focused .MuiOutlinedInput-notchedOutline": { borderColor: ACCENT } };
export const card = { bgcolor: PANEL, border: `1px solid ${BORDER}`, borderRadius: 2, p: 1.5,
  boxShadow: "0 1px 2px rgba(16,24,40,.04)" };
// Double-border frame: a soft gray mat around a white card (layered, Linear/Arc-style).
// Use for the big detail surfaces - review panel, task detail - so they read as raised.
export const frame = { p: 0.75, bgcolor: "#eceef4", border: "1px solid #dde2ea", borderRadius: 3,
  boxShadow: "0 14px 44px rgba(16,24,40,.12)" };
export const frameInner = { bgcolor: PANEL, border: `1px solid ${BORDER}`, borderRadius: 2.25, overflow: "hidden" };

export const hoverable = {
  transition: "box-shadow .15s, border-color .15s",
  "&:hover": { borderColor: "#c9cff0", boxShadow: "0 2px 8px rgba(79,70,229,.10)", cursor: "pointer" },
};
// Feed entrance: quiet slide-up fade, staggered per row by animationDelay at the call site.
export const fadeIn = {
  "@keyframes thubFadeIn": { from: { opacity: 0, transform: "translateY(6px)" }, to: { opacity: 1, transform: "none" } },
  animation: "thubFadeIn .35s ease both",
};

// Muted segmented-pill color pairs - the Timeline filter treatment, shared by every tab.
export const PILL_COLORS = {
  amber: { bg: "#fef4e6", fg: "#b45309", bd: "#f3ddb8" },
  teal: { bg: "#e6f7fb", fg: "#0e7490", bd: "#c2e7f0" },
  green: { bg: "#e8f6ee", fg: "#15803d", bd: "#cdeeda" },
  gray: { bg: "#eef0f3", fg: "#8a94a6", bd: "#dde2ea" },
  red: { bg: "#fdecec", fg: "#b91c1c", bd: "#f3c8c8" },
  purple: { bg: "#f5f3ff", fg: "#7e22ce", bd: "#ddd6fe" },
};
