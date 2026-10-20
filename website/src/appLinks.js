// THE APP'S OWN PAGES, AS LINKS (the owner, 2026-10-15: "if i ask the assistant to help me set up the intacct api, does it just
// open the sage intacct settings page? it should"). The Assistant names a page the way every other link here does - #connector=
// intacct, #settings=policies, #report=new-agent - and the canvas already knows every one of them (canvasLinks.js). This is the
// one reader: is a link one of ours, and open it.
import { canvasRequestFromHash, placeOf } from "./canvasLinks.js";
import { placeHref } from "./words.js";

// SETUP IS A MODE, not a page the canvas opens: its link asks for it the way the top bar's Setup does (TaskHubPage's openSetup).
// Without one, "set up taskuary" typed in the chat was answered with a link to Company Hub (2026-10-16)
const SETUP = "#setup";

// an in-app page link - one the canvas opens - or null (a web address, a task link handled elsewhere, anything unknown)
export const appLink = (href) => {
  const h = String(href || "").trim();
  if (h === SETUP) return h;
  if (!h.startsWith("#") || /^#task=/.test(h)) return null;
  const req = canvasRequestFromHash(h);
  return req && req.kind === "browse" ? h : null;
};

// the page a reply names, as written: [Open the Sage Intacct connection](#connector=intacct) - else the ONE task it points at
// ([TQ-0123](#task=123)); a reply that mentions several tasks in passing opens none of them
// ...and the same for pages (2026-10-19 UI walk): the model is asked for ONE link, and a reply with two opened the first. Setup is
// never opened from a reply: it is a mode that replaces the whole page, so "open my email settings" answered with a #setup link
// swapped the chat - the answer and the composer with it - for the setup screen. Its link stays in the words, to be pressed.
export const firstAppLink = (text) => {
  const links = [...new Set([...String(text || "").matchAll(/\]\((#[^)\s]+)\)/g)].map((m) => m[1]))];
  const pages = links.map(appLink).filter(Boolean);
  if (pages.length) return pages.length === 1 && pages[0] !== SETUP ? pages[0] : null;
  const tasks = [...new Set(links.filter((h) => /^#task=\d+$/.test(h)))];
  return tasks.length === 1 ? tasks[0] : null;
};

// open it on the canvas - the same road a bell or a bookmark takes; the same link twice still opens it again
export const openAppLink = (h) => {
  const want = String(h || "").replace(/^#/, "");
  if (!want) return;
  if (`#${want}` === SETUP) { window.dispatchEvent(new Event("tq-first-run")); return; }
  // ...the same link again is cleared without a step of its own (it was a hash of its own, a bare "#" for Back to land on)
  if (window.location.hash.replace(/^#/, "") === want) window.history.replaceState(window.history.state, "", here(""));
  window.location.hash = want;
};

// ONE ROUTER (the 2026-10-19 UI walk, G2): links came in, but nothing the owner did on the canvas was ever written back - Back left
// the app, and #task=11 stood in the address after the walk moved on, so a reload reopened it. The canvas says where it is
// (recordPlace), the browser's Back and Forward and every followed link come back through one listener (onPlace).
const here = (h) => `${window.location.pathname}${window.location.search}${h}`;
//   how: "push"    the owner went somewhere - a page, a section, a task picked - and Back returns
//        "replace" the same step said more exactly, the walk's Next, the server's word, a link already in the address
export const recordPlace = (want, how = "replace") => {
  if (typeof window === "undefined" || placeOf(window.location.hash) === placeOf(want)) return;
  window.history[how === "push" ? "pushState" : "replaceState"](window.history.state, "", here(want));
};
// a followed link fires hashchange (and popstate with it); Back and Forward fire popstate (and hashchange when the hash differs):
// one call per step. `back` is true for a step of history - the only way an address with no place ("") is asked for
export const onPlace = (fn) => {
  let last = null;
  const go = (e) => {
    const h = window.location.hash || "";
    if (last === h) return;
    last = h; setTimeout(() => { last = null; }, 0);
    fn(h, e.type === "popstate");
  };
  window.addEventListener("popstate", go); window.addEventListener("hashchange", go);
  return () => { window.removeEventListener("popstate", go); window.removeEventListener("hashchange", go); };
};

// WHERE A SETTING IS SAVED, as a link (aidefaults.owner_link): a place of words.json, or one connector's card. "agents" opened the
// Profiles shelf - the claude connection lives on Connections' AI CLI agents page (the 2026-10-19 UI walk)
export const ownerHref = (link) => {
  const l = String(link || "");
  return l.startsWith("connector:") ? `#connector=${l.slice(10)}` : l ? placeHref(l) : "";
};

// THE THING A LINK NAMED, IN VIEW AND SHOWN: scrolled to the middle and outlined for a moment (assistantView.css .tq-flash) - a
// knob two screens down the group it opened was a link that seemed to do nothing
const flash = (el) => {
  el.classList?.remove("tq-flash"); void el.offsetWidth; el.classList?.add("tq-flash");
  clearTimeout(el.tqFlash); el.tqFlash = setTimeout(() => el.classList?.remove("tq-flash"), 1800);   // shown again: an earlier timer must not cut it
};
// ...AND KEPT THERE WHILE THE PAGE FINISHES DRAWING (verify, 2026-10-19): one scroll on arrival was undone by whatever loaded above it
// afterwards - How mail is sorted's AI panel stands up from a spinner over its rows, so a "Fallback AI programs" hit landed at the top
// of its group with the setting 1,700px down. The thing's place in the page (its top plus every scroll above it, so a scroll does not
// count as a move) is watched each frame; when the page above it moves, it is brought back. It is marked [data-tq-held] too, so the
// chat's own hold on the card (AssistantView keepTable) holds IT rather than the card's top - two holds on one scroll fought. The
// owner's own scroll, click or key lets go of both at once - a page never pulls back from under them; else the watch ends after HOLD.
const HOLD = 8000, owner = ["wheel", "touchstart", "keydown", "pointerdown"];
const layoutTop = (el) => {
  let y = el.getBoundingClientRect().top;
  for (let p = el.parentElement; p; p = p.parentElement) y += p.scrollTop || 0;   // <html> among them: the window's own scroll
  return y;
};
let letGo = () => {};
// `find` looks it up again each frame: a row redrawn is a new element, and a panel card that stands up late is not there at first
export const focusPlace = (el, find = null) => {
  if (!el && !find) return;
  letGo();
  if (el) { el.scrollIntoView?.({ block: "center", behavior: "smooth" }); flash(el); }
  if (typeof window === "undefined" || !window.requestAnimationFrame) return;
  const t0 = Date.now();
  let cur = el, y = el ? layoutTop(el) : 0, watching = true;
  const mark = (e) => { cur?.removeAttribute?.("data-tq-held"); cur = e; e.setAttribute?.("data-tq-held", ""); };
  const stop = () => { watching = false; cur?.removeAttribute?.("data-tq-held"); owner.forEach((e) => window.removeEventListener(e, stop, true)); };
  letGo = stop; if (el) mark(el);
  owner.forEach((e) => window.addEventListener(e, stop, true));
  const tick = () => {
    if (!watching || Date.now() - t0 > HOLD) return;                                  // the watch ends; the mark stays till the owner acts
    const e = (find && find()) || (cur?.isConnected ? cur : null);
    if (e) {                                                                            // a row redrawn: between the two it is in neither
      const ny = layoutTop(e);
      if (e !== cur || Math.abs(ny - y) > 2) { mark(e); y = ny; e.scrollIntoView?.({ block: "center" }); flash(e); }
    }
    window.requestAnimationFrame(tick);
  };
  window.requestAnimationFrame(tick);
};
