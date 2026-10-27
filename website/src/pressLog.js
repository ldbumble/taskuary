// EVERY PRESS, KEPT (the Advisor and memory design, phase B, 2026-10-23): only a desk press made while the Advisor's line showed was
// sent, so the Tasks tab and every press with nothing lit were lost. Each surface now says, for every press, what was pressed, what it
// had lit and which other buttons were live - the server keeps it (presses.py; the phone records there itself). Nothing on screen changes.
import { rowOf } from "./actionRow.js";
import { VERBS, verbOfRow } from "./buttons.js";

// a row id or a verb -> the verb: `done` is close, `12:approve` is approve, `advice:chase` is chase
export const verbOf = (id) => verbOfRow(id) || String(id || "").split(":").pop() || "";

// THE DESK: what its row drew at the press, read through the same rowOf the row is drawn with - the filled verb (the Advisor's pick,
// Next under a "nothing to do" line, a running agent's own Stop and save) and every button that could be pressed, the card's own
// moves under the draft among them
export function deskPress(snap, pick, id) {
  const r = rowOf(snap, pick);
  const drawn = [...r.decide, ...r.agent, ...r.more, ...(r.next ? [r.next] : [])].filter((v) => !v.slot);
  const lit = r.primary || (r.next?.tone === "p" ? r.next : null) || r.agent.find((v) => v.tone === "p") || null;
  const live = [...drawn, ...snap.list.filter((v) => v.card)].filter((v) => !v.disabled).map((v) => verbOf(v.id));
  return { pressed: verbOf(id), lit: lit ? verbOf(lit.id) : "", live: [...new Set(live.filter(Boolean))] };
}

// THE TASKS TAB draws its own buttons, not the row: a button is known by its one name (buttons.json - "one name per button", the
// owner, 2026-10-17), and what is lit is what is filled on the page
const BY_LABEL = Object.fromEntries(Object.entries(VERBS).filter(([k]) => !k.startsWith("_"))
  .flatMap(([k, v]) => [v.label, ...Object.values(v.states || {})].map((l) => [l.toLowerCase(), k])));
export const verbOfLabel = (text) => BY_LABEL[String(text || "").replace(/\s+/g, " ").trim().toLowerCase()] || "";
const filled = (b) => /\bMuiButton-contained\b/.test(String(b?.className || ""));
export function pagePress(root, btn) {
  const pressed = verbOfLabel(btn?.textContent);
  if (!pressed || !root) return null;
  const all = [...root.querySelectorAll("button")].filter((b) => !b.disabled);
  const verbs = (bs) => [...new Set(bs.map((b) => verbOfLabel(b.textContent)).filter(Boolean))];
  return { pressed, lit: verbs(all.filter(filled))[0] || "", live: verbs(all) };
}

// one press, posted - a lost post costs one observation, never the press
export function notePress(api, { key, pressed, surface, lit = "", live = null, advised = null, revision = null }) {
  if (!key || !pressed) return null;
  return api.post("/api/advice/press", { key, pressed, surface, lit, live, advised, revision }, { quiet: true }).catch(() => {});
}
