// Task Hub design system - clean, light, compact enterprise workspace (Linear/Notion-ish):
// soft gray canvas, white cards, hairline borders, one indigo accent, small quiet type.
import { createTheme } from "@mui/material/styles";

// Contrast is the design: near-black ink, secondary text you can actually read, and the
// gray reserved for what is truly tertiary. The old DIM/FAINT washed the review panel's
// blurbs into fog at README scale - Scandinavian means quiet, not illegible.
export const BG = "#f3f5f1";           // page canvas - a cool paper, not grey
export const PANEL = "#ffffff";        // cards
export const PANEL2 = "#f4f7f1";       // inset panels / code-ish blocks
export const BORDER = "#dce1d8";
export const INK = "#18201b";          // primary text - near black, faintly green
export const DIM = "#48524a";          // secondary text - readable, not fog
export const FAINT = "#8b938d";        // tertiary (timestamps, rails)
export const ACCENT = "#2f6b4f";       // forest - anything that is on YOU
export const ACCENT2 = "#1f6b64";      // deep teal - work in flight (labels, links)
export const GRADIENT = `linear-gradient(90deg, ${ACCENT}, #3f8a66)`;

export const ACTION_COLORS = {
  auto: { bg: "#eaf1e4", fg: "#4d6b3f", label: "auto-answered" },
  draft: { bg: "#e4efe8", fg: "#245740", label: "needs review" },
  ignore: { bg: "#eef1eb", fg: "#8b938d", label: "ignored" },
  report: { bg: "#e2efed", fg: "#1f6b64", label: "report" },
  feed: { bg: "#eaf1e4", fg: "#4d6b3f", label: "info" },
  filed: { bg: "#eef1eb", fg: "#8b938d", label: "filed" },
  skip: { bg: "#eceee9", fg: "#7c867e", label: "skipped" },
  task_only: { bg: "#e4efe8", fg: "#2f6b4f", label: "task created" },
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
  open: "#7d9e6c", in_progress: "#1f6b64", waiting: "#2f6b4f", done: "#4d6b3f", dropped: "#9aa39b",
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
  },
});

export const mono = { fontFamily: "'IBM Plex Mono', 'Cascadia Code', Consolas, monospace" };
// Compact modern select styling, shared by the detail-header dropdowns and the hand-off form.
export const selSx = { fontSize: 12.5, bgcolor: "#fff", borderRadius: 2,
  "& .MuiOutlinedInput-notchedOutline": { borderColor: BORDER },
  "&:hover .MuiOutlinedInput-notchedOutline": { borderColor: "#b6d0c2" },
  "&.Mui-focused .MuiOutlinedInput-notchedOutline": { borderColor: ACCENT } };
export const card = { bgcolor: PANEL, border: `1px solid ${BORDER}`, borderRadius: 2, p: 1.5,
  boxShadow: "0 1px 2px rgba(30,50,38,.04)" };
// Double-border frame: a soft gray mat around a white card (layered, Linear/Arc-style).
// Use for the big detail surfaces - review panel, task detail - so they read as raised.
export const frame = { p: 0.75, bgcolor: "#e9ede6", border: "1px solid #d5dbd1", borderRadius: 3,
  boxShadow: "0 14px 44px rgba(30,50,38,.12)" };
export const frameInner = { bgcolor: PANEL, border: `1px solid ${BORDER}`, borderRadius: 2.25, overflow: "hidden" };

export const hoverable = {
  transition: "box-shadow .15s, border-color .15s",
  "&:hover": { borderColor: "#b6d0c2", boxShadow: "0 2px 8px rgba(47,107,79,.10)", cursor: "pointer" },
};
// Feed entrance: quiet slide-up fade, staggered per row by animationDelay at the call site.
export const fadeIn = {
  "@keyframes thubFadeIn": { from: { opacity: 0, transform: "translateY(6px)" }, to: { opacity: 1, transform: "none" } },
  animation: "thubFadeIn .35s ease both",
};

// Muted segmented-pill color pairs - the Timeline filter treatment, shared by every tab.
export const PILL_COLORS = {
  amber: { bg: "#e4efe8", fg: "#2f6b4f", bd: "#b6d0c2" },
  teal: { bg: "#e2efed", fg: "#1f6b64", bd: "#bcd9d5" },
  green: { bg: "#eaf1e4", fg: "#4d6b3f", bd: "#cfe0c4" },
  gray: { bg: "#eef1eb", fg: "#8b938d", bd: "#dce1d8" },
  red: { bg: "#f4eae8", fg: "#8f4a41", bd: "#e3cec9" },
  purple: { bg: "#e2efed", fg: "#1f6b64", bd: "#bcd9d5" },
};
