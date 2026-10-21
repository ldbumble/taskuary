// A CONNECTOR CARD'S FIRST STEP, LIT (the owner, 2026-10-20: "add LinkedIn as a connector" - the Assistant brings up the card and lights
// its first real step). Read off the card as it is drawn, never a list per type: the card's primary (filled) button when it can be
// pressed - Sign in with LinkedIn, Connect, Save - else the first empty box it asks for, which is what holds that button back. Lit with
// the outline the setup and the Advisor use (data-tq-setup-lit, assistantView.css) and held in view (appLinks.focusPlace).
import { focusPlace } from "./appLinks.js";

export const STEP_SAID = "its first step is lit there";     // the server's words (concierge, connection.create) the page fills in
export const LIT = "taskuary:step-lit";

// candidates in the card's order: {kind: "button", text, primary, disabled} | {kind: "field", text, empty}
export function pickStep(cs) {
  const primary = cs.find((c) => c.kind === "button" && c.primary);
  if (primary && !primary.disabled) return cs.indexOf(primary);
  const field = cs.findIndex((c) => c.kind === "field" && c.empty);
  if (field >= 0) return field;
  return primary ? cs.indexOf(primary) : -1;
}

// the reply's line, finished with what was lit
export const stepWords = (s) => (!s?.text ? "" : s.kind === "button" ? `press ${s.text}` : `fill in ${s.text} first`);
export const finishLine = (text, s) => (stepWords(s) && String(text || "").includes(STEP_SAID) ? text.replace(STEP_SAID, stepWords(s)) : text);

const shown = (e) => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
const fieldText = (e) => (e.closest(".MuiFormControl-root")?.querySelector("label")?.innerText || e.getAttribute("aria-label") || e.placeholder || "")
  .replace(/\s*\*\s*$/, "").trim();

function candidates(root) {
  const els = [...root.querySelectorAll(".MuiButton-root, input:not([type=hidden]):not([type=checkbox]):not([type=radio]), textarea")].filter(shown);
  return els.map((e) => (e.matches(".MuiButton-root")
    ? { el: e, kind: "button", text: (e.innerText || "").trim(), primary: e.classList.contains("MuiButton-contained"), disabled: !!e.disabled }
    : { el: e, kind: "field", text: fieldText(e), empty: !e.readOnly && !e.disabled && !String(e.value || "").trim(), lit: e.closest(".MuiInputBase-root") || e }));
}

// light the card's first step as it draws, report it once (`onLit({kind, text})`), and hold it in view; returns the cleanup
export function lightStep(root, onLit, ms = 6000) {
  if (!root || typeof MutationObserver === "undefined") return () => {};
  let told = false, lit = null;
  const find = () => { const cs = candidates(root), i = pickStep(cs); return i >= 0 ? cs[i] : null; };
  const apply = () => {
    const c = find(), el = c ? (c.lit || c.el) : null;
    if (el === lit) return;
    lit?.removeAttribute("data-tq-setup-lit");
    lit = el;
    if (!el) return;
    el.setAttribute("data-tq-setup-lit", "light");
    if (!told) { told = true; focusPlace(el, () => { const n = find(); return n ? (n.lit || n.el) : null; }); onLit?.({ kind: c.kind, text: c.text }); }
  };
  apply();
  const mo = new MutationObserver(apply);
  mo.observe(root, { childList: true, subtree: true, attributes: true, attributeFilter: ["disabled", "class", "value"] });
  const stop = setTimeout(() => mo.disconnect(), ms);
  return () => { clearTimeout(stop); mo.disconnect(); lit?.removeAttribute("data-tq-setup-lit"); };
}
