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
// ...AND THE CHAT KEEPS A READABLE WIDTH. Four fifths of a 1000px slot left the conversation ~200px - a
// column of two-word lines beside a browser nobody needed that wide (the 2026-10-02 pane pass). The ratio
// is still the owner's; it just never takes the chat below this many pixels (plus the 8px handle).
export const MIN_CHAT_PX = 360;
export const splitRatio = (r, width) =>
  (width > 0 ? Math.max(MIN_RATIO, Math.min(clampRatio(r), (width - MIN_CHAT_PX - 8) / width)) : clampRatio(r));

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

// THE SHAPE OF THE PAGE ITSELF. Chrome renders at a viewport nobody set - 1280x720, a wide desktop
// shape - and fitFrame then letterboxes that into a pane which is taller than it is wide: measured
// 2026-09-14, 55% of the pane was black and the page drew at 38%. Telling the browser the pane's
// SHAPE removes the bars; keeping a desktop WIDTH keeps the layout sites serve to a desktop, which
// is the one thing matching the pane exactly would have cost (the owner chose this trade).
export const MIN_VIEWPORT_W = 1200;
export const MIN_VIEWPORT_H = 400;

export const viewportFor = (w, h) => {
  if (!(w > 0 && h > 0)) return null;
  const vw = Math.round(Math.max(MIN_VIEWPORT_W, w));
  return { w: vw, h: Math.max(MIN_VIEWPORT_H, Math.round(vw * (h / w))) };
};

// Dragging the splitter fires a resize every frame; Chrome should not be re-laid-out for six pixels.
export const viewportMoved = (was, now, tol = 32) =>
  !!now && (!was || Math.abs(was.w - now.w) > tol || Math.abs(was.h - now.h) > tol);

// A page address as the toolbar shows it: scheme and trailing slash dropped, long paths cut in the middle
export const shortUrl = (u, max = 64) => {
  if (!u) return "";
  const s = String(u).replace(/^https?:\/\//, "").replace(/\/$/, "");
  return s.length <= max ? s : `${s.slice(0, Math.ceil(max * 0.6))}…${s.slice(-Math.floor(max * 0.35))}`;
};

// IS THERE A BROWSER TO SHOW. A task that asked for one shows its pane while Chrome is still coming up
// (`expect`) - but only until that browser has been seen open: once it has, and closes, the pane folds.
// `expect` alone kept it standing for ever over a frozen last frame and a "no page open" note, its socket
// knocking every two seconds on a relay that refused it (the 2026-10-02 pane pass).
export const showsBrowser = (open, expect, seen) => !!open || (!!expect && !seen);

// WHO SHAPES THE PAGE. Every tab watching one session used to set its viewport - a phone and a desktop on
// the same task fought, and the desktop's page came back phone-shaped between black bars (2026-10-02).
// One Chrome, one shape: the tab the owner is AT (visible and focused), or one they just pressed in
// (`claim`: a click in the pane, Take over, the window coming back) - never a background tab's resize.
export const mayShape = (hidden, focused, claim = false) => !hidden && (!!claim || !!focused);

// ONLY BROWSING TAKES ROOM (the owner, 2026-10-09: "only browser use should take up space in the chat box"). An agent
// that opens a file of its own in its browser - rendering a mock receipt to test against - is not out on the web: the
// pane stays folded to its chip, one click from showing, and unfolds by itself once the agent goes to a real address.
export const isLocalPage = (url) => /^file:/i.test(String(url || "").trim());

// Should this slot hold the split, or just a chip? The Wall tiles three or four sessions across.
export const layoutFor = (width, open, folded) => (!open ? "none" : width < CHIP_BELOW ? "chip" : folded ? "folded" : "split");
