// The browser pane's arithmetic, kept out of React so it can be tested: how a frame fits its
// box, how a pointer on the canvas maps back to a page coordinate, and how the split between
// terminal and browser is remembered. The design (2026-08-30): terminal narrower, browser the
// larger share, a drag handle between, pane appears when the agent opens a page.

export const DEFAULT_RATIO = 0.58;          // the browser's share of the width
export const MIN_RATIO = 0.3, MAX_RATIO = 0.8;
export const CHIP_BELOW = 700;              // a slot narrower than this (a Wall tile) gets a chip, not a split
const KEY_RATIO = "tq-browser-ratio", KEY_FOLD = "tq-browser-folded";
const foldKey = (sid) => sid ? `${KEY_FOLD}.${sid}` : KEY_FOLD;

export const clampRatio = (r) => (Number.isFinite(r) ? Math.min(MAX_RATIO, Math.max(MIN_RATIO, r)) : DEFAULT_RATIO);

// the pointer's position across the whole split, as the browser's share (it sits on the right)
export const ratioFromPointer = (x, left, width) => (width > 0 ? clampRatio(1 - (x - left) / width) : DEFAULT_RATIO);

export const savedRatio = () => {
  try { return clampRatio(parseFloat(localStorage.getItem(KEY_RATIO))); } catch { return DEFAULT_RATIO; }
};
export const rememberRatio = (r) => { try { localStorage.setItem(KEY_RATIO, String(clampRatio(r))); } catch { /* private mode */ } };
// Folding is a choice about THIS browser, not every browser opened in the future. The old global
// key made one Fold click hide every later session, which looked exactly like navigation failed.
export const savedFold = (sid) => { try { return localStorage.getItem(foldKey(sid)) === "1"; } catch { return false; } };
export const rememberFold = (f, sid) => { try { localStorage.setItem(foldKey(sid), f ? "1" : "0"); } catch { /* private mode */ } };

// Letterbox a frame into a box: the page is drawn whole and centred, never cropped or stretched.
// Returns the drawn rectangle and the scale from page pixels to canvas pixels.
export const fitFrame = (fw, fh, bw, bh) => {
  if (!(fw > 0 && fh > 0 && bw > 0 && bh > 0)) return { x: 0, y: 0, w: 0, h: 0, scale: 0 };
  const scale = Math.min(bw / fw, bh / fh);
  const w = Math.round(fw * scale), h = Math.round(fh * scale);
  return { x: Math.round((bw - w) / 2), y: Math.round((bh - h) / 2), w, h, scale };
};

// A pointer on the canvas, as a coordinate ON THE PAGE (CSS pixels, what CDP input wants). Null
// when the pointer is on the letterbox margin - a click there is not a click on the page.
export const toPage = (cx, cy, fit) => {
  if (!fit || !fit.scale) return null;
  const x = (cx - fit.x) / fit.scale, y = (cy - fit.y) / fit.scale;
  if (x < 0 || y < 0 || x > fit.w / fit.scale || y > fit.h / fit.scale) return null;
  return { x: Math.round(x), y: Math.round(y) };
};

const BUTTONS = ["left", "middle", "right"];
// agent-browser's input_mouse message for a DOM mouse event: CDP event types, page coordinates
export const mouseMessage = (type, e, fit) => {
  const p = toPage(e.offsetX, e.offsetY, fit);
  if (!p) return null;
  const eventType = { mousedown: "mousePressed", mouseup: "mouseReleased", mousemove: "mouseMoved" }[type];
  if (!eventType) return null;
  return { type: "input_mouse", eventType, x: p.x, y: p.y, button: BUTTONS[e.button] || "none",
    clickCount: type === "mousemove" ? 0 : 1, modifiers: modifiers(e) };
};
export const wheelMessage = (e, fit) => {
  const p = toPage(e.offsetX, e.offsetY, fit);
  if (!p) return null;
  return { type: "input_mouse", eventType: "mouseWheel", x: p.x, y: p.y, deltaX: e.deltaX || 0, deltaY: e.deltaY || 0,
    button: "none", modifiers: modifiers(e) };
};

// CDP modifier bits: Alt=1, Ctrl=2, Meta=4, Shift=8
export const modifiers = (e) => (e.altKey ? 1 : 0) | (e.ctrlKey ? 2 : 0) | (e.metaKey ? 4 : 0) | (e.shiftKey ? 8 : 0);

// A keystroke for the page. Printable keys carry `text` so the page receives the character;
// keyDown for a printable key uses CDP's "keyDown" which also inserts text when `text` is set.
export const keyMessage = (type, e) => {
  const eventType = type === "keydown" ? (e.key.length === 1 ? "keyDown" : "rawKeyDown") : type === "keyup" ? "keyUp" : null;
  if (!eventType) return null;
  const m = { type: "input_keyboard", eventType, key: e.key, code: e.code, modifiers: modifiers(e) };
  if (type === "keydown" && e.key.length === 1 && !e.ctrlKey && !e.metaKey) m.text = e.key;
  else if (type === "keydown" && e.key === "Enter") m.text = "\r";
  return m;
};

// Parse one relay message; frames become {type, seq, src, w, h} ready to draw, the rest pass through.
export const parseMessage = (raw) => {
  let m;
  try { m = JSON.parse(raw); } catch { return null; }
  if (!m || typeof m !== "object") return null;
  if (m.type === "frame") {
    const md = m.metadata || {};
    return { type: "frame", seq: m.seq, src: `data:image/jpeg;base64,${m.data}`, w: md.deviceWidth || 0, h: md.deviceHeight || 0,
      at: md.timestamp || 0 };
  }
  return m;
};

// A page address as the toolbar shows it: scheme and trailing slash dropped, long paths cut in the middle
export const shortUrl = (u, max = 64) => {
  if (!u) return "";
  const s = String(u).replace(/^https?:\/\//, "").replace(/\/$/, "");
  return s.length <= max ? s : `${s.slice(0, Math.ceil(max * 0.6))}…${s.slice(-Math.floor(max * 0.35))}`;
};

// Should this slot hold the split, or just a chip? The Wall tiles three or four sessions across.
export const layoutFor = (width, open, folded) => (!open ? "none" : width < CHIP_BELOW ? "chip" : folded ? "folded" : "split");
