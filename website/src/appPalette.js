// One warm night palette for MUI and the custom CSS views. Each var() keeps its exact
// existing light value as fallback; only the dark root declares these properties.
export const DARK = {
  canvas: "#2a2925", panel: "#33312d", inset: "#3d3b36",
  text: "#eeeae3", secondary: "#c6c0b7", muted: "#aaa59d",
  border: "#4a4741", "border-strong": "#606368", scrollbar: "#606368",
  link: "#a8c4d9", success: "#abc9a5", danger: "#e5a3ae", warning: "#dac18c", purple: "#c9afd8",
  "tint-slate": "#293743", "tint-sage": "#2a392f", "tint-red": "#422d35",
  "tint-brass": "#3b3428", "tint-neutral": "#31302e", "tint-purple": "#372e40",
  "edge-slate": "#526779", "edge-sage": "#506c55", "edge-red": "#78505a", "edge-brass": "#756345", "edge-purple": "#695477",
};

export const darkVariables = Object.fromEntries(Object.entries(DARK).map(([key, value]) => [`--tq-${key}`, value]));
darkVariables["--tq-panel-rgb"] = "51 49 45";
