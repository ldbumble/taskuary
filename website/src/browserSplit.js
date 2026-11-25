// The browser pane's arithmetic, kept out of React so it can be tested: how a frame fits its
// box, how a pointer on the canvas maps back to a page coordinate, and how the split between
// terminal and browser is remembered. The design (2026-08-30): terminal narrower, browser the
// larger share, a drag handle between, pane appears when the agent opens a page.

export const DEFAULT_RATIO = 0.58;          // the browser's share of the width
export const MIN_RATIO = 0.3, MAX_RATIO = 0.8;
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
// EVERY KEY CARRIES ITS WINDOWS KEY CODE. Chrome runs Backspace, Delete, the arrows, Home/End, Tab and Ctrl+A off
// windowsVirtualKeyCode, not off `key`: without it a typed "abc" went in and Backspace did nothing (the owner on a portal's
// sign-in, 2026-11-03: "something went in but backspace did not work"). Measured against agent-browser 0.38.2's stream: no
// code, "abc" + Backspace stayed "abc"; with it, "ab" - and Ctrl+A then Backspace emptied the box.
const VK = { Backspace: 8, Tab: 9, Enter: 13, Shift: 16, Control: 17, Alt: 18, Pause: 19, CapsLock: 20, Escape: 27, " ": 32, PageUp: 33,
  PageDown: 34, End: 35, Home: 36, ArrowLeft: 37, ArrowUp: 38, ArrowRight: 39, ArrowDown: 40, Insert: 45, Delete: 46, Meta: 91 };
export const keyCodeOf = (e) => {
  if (e.keyCode) return e.keyCode;
  if (VK[e.key] != null) return VK[e.key];
  const m = /^(?:Key([A-Z])|Digit(\d))$/.exec(e.code || "");
  if (m) return (m[1] || m[2]).charCodeAt(0);
  if (/^F\d{1,2}$/.test(e.key || "")) return 111 + Number(e.key.slice(1));
  return e.key && e.key.length === 1 ? e.key.toUpperCase().charCodeAt(0) : 0;
};
// Ctrl+V (Cmd+V) is not sent as a key: the page's clipboard is the agent's browser's, empty. The paste event brings the owner's own
// clipboard instead (pasteMessages).
export const isPaste = (e) => (e.ctrlKey || e.metaKey) && !e.altKey && String(e.key).toLowerCase() === "v";
// ENTER IS A KEY THAT TYPES: Chrome sends a form on the character a keyDown carries, and a rawKeyDown carries none - so Enter in a sign-in's
// password box did nothing and the page stayed up (the recorded browser walk, 2026-11-11). It goes as a paste's line break does (pasteMessages).
export const keyMessage = (type, e) => {
  const eventType = type === "keydown" ? (e.key.length === 1 || e.key === "Enter" ? "keyDown" : "rawKeyDown") : type === "keyup" ? "keyUp" : null;
  if (!eventType) return null;
  const m = { type: "input_keyboard", eventType, key: e.key, code: e.code, modifiers: modifiers(e) };
  const vk = keyCodeOf(e);
  if (vk) Object.assign(m, { windowsVirtualKeyCode: vk, nativeVirtualKeyCode: vk });
  if (type === "keydown" && e.key.length === 1 && !e.ctrlKey && !e.metaKey) m.text = e.key;
  else if (type === "keydown" && e.key === "Enter") m.text = "\r";
  return m;
};
// The owner's clipboard, typed into the page a character at a time: agent-browser's stream has no insert-text message, and a keyDown
// carrying several characters inserts none of them (measured, 0.38.2). A line break is an Enter.
export const pasteMessages = (text) => [...String(text || "").replace(/\r\n?/g, "\n")].slice(0, 4000).map((ch) => (ch === "\n"
  ? { type: "input_keyboard", eventType: "keyDown", key: "Enter", code: "Enter", modifiers: 0, windowsVirtualKeyCode: 13, nativeVirtualKeyCode: 13, text: "\r" }
  : { type: "input_keyboard", eventType: "keyDown", key: ch, modifiers: 0, text: ch }));

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
// ...BUT A LAPTOP'S PANE IS NOT A DESKTOP'S: at 1366x768 the pane is ~540px, so a 1200px page drew at 45% and its text at ~7px, in the
// pane where the owner is asked to sign in (2026-10-25). Under NARROW_PANE the page is 980px - still the width sites give a desktop.
export const NARROW_PANE = 800, NARROW_VIEWPORT_W = 980;

export const viewportFor = (w, h) => {
  if (!(w > 0 && h > 0)) return null;
  const vw = Math.round(Math.max(w < NARROW_PANE ? NARROW_VIEWPORT_W : MIN_VIEWPORT_W, w));
  return { w: vw, h: Math.max(MIN_VIEWPORT_H, Math.round(vw * (h / w))) };
};

// THE FIRST PICTURE OF A VIEW WAITS FOR THE PANE'S SHAPE (BrowserPane.draw): a frame taken at another shape than the pane asks for is held
// while nothing is drawn yet, for at most FIRST_WAIT ms from the connection's first frame. `drawn`: a picture is already on the canvas;
// `frame`: {w, h} of the frame; `box`: the pane's own size; `waited`: ms since the first frame.
export const FIRST_WAIT = 1200;
export const holdFirst = (drawn, frame, box, waited) => {
  const want = box && viewportFor(box.width, box.height);
  if (drawn || !want || !(frame?.w > 0 && frame?.h > 0) || waited >= FIRST_WAIT) return false;
  return viewportMoved({ w: frame.w, h: frame.h }, want);
};
// the address of the tab the browser says is the active one (its `tabs` message), or ""
export const activeTab = (m) => String((m?.tabs || []).find((t) => t?.active)?.url || "");
// THE TABS OF THE TASK'S ONE BROWSER (the owner, 2026-11-15: "open multiple sites on same window with tabs"): {id, name, url, active} per tab
// from the browser's `tabs` message - named by the page's title, or its host where the title is only its address. [] for a tabs message
// with none, and the strip draws only for two or more: a one-site task looks as it always did
export const TAB_ID = /^t\d{1,4}$/;
// ...AND A PAGE KEEPS THE TITLE IT ONCE SHOWED (design round 5, 2026-11-19: thirteen vendor tabs read "127.0.0.1:18791", "127.0.0.2:18791" ... - the
// browser names a tab in the background by its address alone): the title seen for an address names its tab until another title comes
const TITLES = new Map();
export const tabList = (m) => (Array.isArray(m?.tabs) ? m.tabs : []).filter((t) => t && TAB_ID.test(String(t.tabId || ""))).map((t) => {
  const url = String(t.url || ""), at = url.split("#")[0], now = String(t.title || "").trim();
  let host = ""; try { host = new URL(url).host; } catch { /* not an address */ }
  const bare = (x) => !x || x === host || url.includes(x);
  if (!bare(now)) TITLES.set(at, now);
  const title = bare(now) ? TITLES.get(at) || "" : now;
  // ...a page reached by a bare address with no title of its own reads by its address without the port (never "127.0.0.4:18811")
  const where = /^\d+\.\d+\.\d+\.\d+(:\d+)?$|^\[/.test(host) ? host.replace(/:\d+$/, "") : host;
  return { id: String(t.tabId), name: (title || where || now || url) || "new tab", url, active: !!t.active };
});

// Dragging the splitter fires a resize every frame; Chrome should not be re-laid-out for six pixels.
export const viewportMoved = (was, now, tol = 32) =>
  !!now && (!was || Math.abs(was.w - now.w) > tol || Math.abs(was.h - now.h) > tol);

// A page address as the toolbar shows it: scheme and trailing slash dropped, long paths cut in the middle
// ...and a page the agent opened from disk is its FILE'S NAME, never the path to it (the stress test, 2026-11-02: the chip read
// "browser · file:///C:/Users/<you>/...") - the last part of the path, decoded, with no query or anchor
export const shortUrl = (u, max = 64) => {
  if (!u) return "";
  if (/^file:/i.test(String(u).trim())) {
    const p = String(u).trim().replace(/[?#].*$/, "").split(/[\\/]+/).filter(Boolean).pop() || "";
    let n = p; try { n = decodeURIComponent(p); } catch { /* the name as it was */ }
    return `file · ${n.length <= max ? n : `${n.slice(0, Math.ceil(max * 0.6))}…${n.slice(-Math.floor(max * 0.35))}`}`;
  }
  const s = String(u).replace(/^https?:\/\//, "").replace(/\/$/, "");
  return s.length <= max ? s : `${s.slice(0, Math.ceil(max * 0.6))}…${s.slice(-Math.floor(max * 0.35))}`;
};

// IS THERE A BROWSER TO SHOW: one that is open ON A PAGE (the owner, 2026-11-04: "browser should not show unless we need login";
// "no browser should open if we don't have a URL"). A task marked "needs a browser" used to reserve the pane while Chrome came up, and
// an empty tab took it: a black about:blank beside an agent that only searched and asked where and when. Nothing shows - no view, no
// chip - until the agent opens a page; a sign-in, a hand-over and a held act all wait on one (isBlankPage below).
export const showsBrowser = (open, url) => !!open && !isBlankPage(url);

// WHO SHAPES THE PAGE. Every tab watching one session used to set its viewport - a phone and a desktop on
// the same task fought, and the desktop's page came back phone-shaped between black bars (2026-10-02).
// One Chrome, one shape: the tab the owner is AT (visible and focused), or one they just pressed in
// (`claim`: a click in the pane, Take over, the window coming back) - never a background tab's resize.
export const mayShape = (hidden, focused, claim = false) => !hidden && (!!claim || !!focused);

// ONLY BROWSING TAKES ROOM (the owner, 2026-10-09: "only browser use should take up space in the chat box"). An agent
// that opens a file of its own in its browser - rendering a mock receipt to test against - is not out on the web: the
// pane stays folded to its chip, one click from showing, and unfolds by itself once the agent goes to a real address.
export const isLocalPage = (url) => /^file:/i.test(String(url || "").trim());
// AN EMPTY TAB IS NOT A PAGE (the owner, 2026-11-03): a Chrome launched for a task marked "needs a browser" sat on about:blank as half the
// canvas - "an empty tab, live" - on a task the agent answered without one. It takes no room at all (showsBrowser)
export const isBlankPage = (url) => { const u = String(url || "").trim(); return !u || /^about:/i.test(u); };
// ...and "your turn - click the page and type" is for a wait ON the page: the agent's hand-over (isTurn) or a sign-in (signin.PREFIX) -
// never a question it asked in words, which is answered in the chat's box
export const waitsOnPage = (asking) => isTurn(asking) || isSignin(asking);

// THE ONE LAYOUT OF THE BROWSER PANE, for every slot it is drawn in - a chat task, a coding task, a Wall tile, a setup's terminal (the design
// loop, 2026-11-20: three rules - layoutFor's chip under 700/560 with a view stacked over the chat, quietLayout's chip under 420 - drew the same
// hand-over as a chip on a coding task and a split on a chat task). The view sits BESIDE the chat, never above it and never over the task list;
// only a phone's width gets the chip, the view as a link. `folded`: the owner's own Fold (or an agent's own file it opened, isLocalPage)
export const CHIP_BELOW = 420;
export const paneLayout = (width, open, folded = false) => (!open ? "none" : width > 0 && width < CHIP_BELOW ? "chip" : folded ? "folded" : "split");
// the layouts where the view itself is on screen, so what waits on it (a held act, the owner's turn) is drawn on it
export const viewOnScreen = (layout) => layout === "split";
// ...and the chat keeps CHAT_SHARE of the width whatever the ratio dragged: at a laptop's ~555px slot a pixel floor for the chat left the page
// ~190px, too small to sign in on - and four fifths of a wide slot left the chat a column of two-word lines
export const CHAT_SHARE = 0.45;
export const paneShare = (r) => Math.min(1 - CHAT_SHARE, clampRatio(r));

// WHICH KIND OF ASK IT IS, as the server says it (workerstate.ask_of: 'signin' | 'turn' | 'question') - the page never reads a request id's marker.
// A STEP ONLY THE OWNER CAN DO ON THE PAGE: the agent handed the page over - drawn on the view as "Your turn"
export const isTurn = (asking) => asking?.ask === "turn";
export const isSignin = (asking) => asking?.ask === "signin";
// WHAT THE CHAT'S BOX SAYS WHILE THE AGENT WAITS ON HIM - one function for every ask: a sign-in is typed on the page (never a password here), a
// step handed over is done on the page (the browser audit, 2026-11-15: "Answer the agent's question..." stood under a step that was no question),
// and only a question is answered in the box
export const askPlaceholder = (asking) => (!asking ? "" : isSignin(asking) ? "Message the agent - never your password"
  : isTurn(asking) ? "Your step is on the page - or tell the agent here…"
  : "Answer the agent's question…");

// A HELD BROWSER ACT of THIS session's browser (browsergate.py), as the view draws it - null for anything else (a shell step, another
// session's act: those stay on their card in the conversation)
export const heldOn = (review, sid) => {
  let p;
  try { p = JSON.parse(review?.DraftText || ""); } catch { return null; }
  if (p?.action !== "browser_act" || !sid || String(p.sid) !== String(sid)) return null;
  return { id: review.ReviewId, what: p.what || p.command || "the step the agent held", site: p.site || "", url: p.url || "", why: p.why || "" };
};

// THE CARDS HIS PRESS IS ON NOW, BY THE CHAT'S OWN LIST (conversation.items): a card drawn there and not greyed. The view's "waits for your
// Approve in the chat" names only these (walk 10, 2026-11-23: it named a held sign-up for 15 minutes while the turn at work drew no card -
// a card comes as a turn's last thing - and again after an input had greyed it). ...AND THE STEP A CARD CARRIES (`step`, chatlog.advance): the
// last press of the browser road he sent it down, drawn on that card (walk 22: held, joined to the card he had pressed, and named nowhere)
export const pressable = (list) => new Set((list?.items || [])
  .flatMap((x) => (x.kind === "card" ? [x] : x.kind === "turn" ? x.cards || [] : []))
  .filter((c) => c.status === "pending" && c.review != null).flatMap((c) => [c.review, ...(c.step ? [c.step.review] : [])]));

// ONE THING IN FRONT OF HIM AT A TIME (the owner's rule): his turn on the page, else the held step that waits for his Approve - never both
export const pageBars = (turn, held = []) => (turn ? { turn, held: [] } : { turn: null, held });

// A CHAT TASK SHOWS THE BROWSER ONLY WHEN THE OWNER IS NEEDED ON IT (the owner, 2026-11-05: "for browser we don't really want to show it
// unless they need login ... Browser should open side by side not top/bottom"). The agent browsing is a "Working on this…" line in the
// chat and nothing more; the page is drawn for a sign-in or a code the vault does not keep (a `signin:` ask), a hand-over - a captcha,
// a step only a person may do (isTurn) - or a step it held for Approve (heldOn). A saved sign-in raises no ask (signin.needs), so it
// is never drawn. Then it is laid out as every pane is (paneLayout).
