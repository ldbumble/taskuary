// WHAT A PRESS DID, ON WHAT WAS PRESSED (the owner, 2026-11-23, walk 11 F6: "Not for me" and "Send and close" left the screen at once with
// nothing saying what the press did): every press that moves the walk on - Mark done, Close with a note, Remind me with a day, Not for me,
// Watch it, Send and close - shows its result on its own button for PRESS_BEAT, and only then does the walk move. Back and Next stand greyed
// through the beat (one move at a time). The words are one function's (pressWord), wherever the result is drawn; the button that draws it is
// one component (PressLabel). Never a chat line.
import React, { useSyncExternalStore } from "react";

export const PRESS_BEAT = 900;
const WORDS = { done: "Done", "close-note": "Done · note kept", nat: "Not for you - filed", watch: "Watching", send_close: "Sent · closed" };
// a draft's own verbs are `<rid>:send_close`: the last part says the act
export const pressWord = (verb, x = {}) => { const k = String(verb || "").split(":").pop();
  return k === "remind" ? (x.day ? `Back ${x.day}` : "Put off") : WORDS[k] || ""; };

// the press the row last ran ({id, of, at}: actionRow.press records it), so the result lands on THAT button - the same verb of the next item is not it
let last = null, now = null, n = 0;
const subs = new Set(), sub = (f) => { subs.add(f); return () => subs.delete(f); }, set = (v) => { now = v; subs.forEach((f) => f()); };
export const pressedOn = (id, of = "", at = "") => { last = { id: String(id || ""), of: of || "", at: at || "" }; };
// ...the word on its button, then the beat; `move` after it. The result stays on the button while the walk moves (the item leaves under it -
// a label flicking back for the last frames would be a flicker), and is taken back when the press failed and the item stays (pressOver)
// ...only a row press of the same act: Mark done pressed on a draft card has no row button to wear it, and the beat still holds the move
export function pressBeat(verb, x = {}, on = last) {
  const word = pressWord(verb, x), k = ++n, same = on && on.id.split(":").pop() === String(verb).split(":").pop();
  if (!word) return Promise.resolve();
  set({ ...(same ? on : { id: String(verb), of: "", at: "" }), word, k, beating: true });
  return new Promise((r) => setTimeout(() => { if (now?.k === k) set({ ...now, beating: false }); r(); }, PRESS_BEAT));
}
export const pressOver = () => { if (now) set(null); };
export const pressNow = () => now;
// true while a press's result is up and its move has not begun: Back and Next grey for it
const beating = () => !!now?.beating, current = () => now;
export const useBeat = () => useSyncExternalStore(sub, beating, beating);
export const resultOf = (r, v) => (r && v && r.id === String(v.id) && r.of === (v.of || "") && r.at === (v.at || "") ? r.word : "");
// THE PRESS-RESULT COMPONENT: a row button's words - its result while one is up for it, else its own label
export function PressLabel({ v, children }) {
  const word = resultOf(useSyncExternalStore(sub, current, current), v);
  return word ? React.createElement("span", { "data-tq-press-result": "", role: "status" }, word) : children ?? v?.label ?? null;
}
