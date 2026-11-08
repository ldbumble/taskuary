// A BLANK LEFT IN A DRAFT (the owner, 2026-10-30): a drafted reply can hold a slot like "[REASON]" or "[DATE]", and Send went out
// with it. The server refuses it (taskuary/blanks.py - the one door, so the phone and the assistant meet it too); this is the same
// rule, from the same blanks.json, so the draft box can mark the slots and the press can say so before anything is posted.
// Only template slots count: a gateway's "[External]", a link "[text](url)", a footnote "[1]", a checkbox "[x]", code and quoted lines
// go out as they are.
import J from "../../taskuary/blanks.json" with { type: "json" };

const NOT_SLOTS = new Set(J.not_slots), SAID = new Set(J.said);
const esc = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
const BOX = /(?<![\w\]\\])\[([^[\]\n]{1,160})\](?!\(|\[|:\s*(?:https?:\/\/|<))/g;
// ...a choice left for the owner ("[Gail is joining / Gail is not joining]", the product audit 2026-11-08) and a bare line to fill ("by ___")
const CHOICE = /\S\s+\/\s+\S/, LINE = /(?<![\w_])_{3,}(?![\w_])/g;
const SHOUT = /^[A-Z][A-Z0-9'’&/.,#_ -]*$/;
const CUE = new RegExp(`^(?:${[...J.cues].sort((a, b) => b.length - a.length).map(esc).join("|")})\\b`, "i");
const PHRASE = /^[A-Za-z][\w'’&/.,# -]{0,39}$/;
// code and quoted lines are someone else's words: blanked to spaces so a slot's place in the text stays where it was
const ASIDE = /```[\s\S]*?(?:```|$(?![\s\S]))|`[^`\n]*`|^[ \t]*>[^\n]*/gm;

export function isSlot(inner) {
  const s = inner.trim();
  if (!s || NOT_SLOTS.has(s.toUpperCase()) || (s.toLowerCase().match(/[a-z]+/g) || []).some((w) => SAID.has(w))) return false;
  if (/^_{2,}$/.test(s) || CHOICE.test(s)) return true;
  if (s.length > 60) return false;
  if (SHOUT.test(s)) return (s.match(/[A-Z]/g) || []).length >= 2;
  return PHRASE.test(s) && CUE.test(s);
}

// [start, end, "[SLOT]"] for every blank still in the text, in order
export function blankSpans(text) {
  if (!text) return [];
  const seen = text.replace(ASIDE, (m) => m.replace(/[^\n]/g, " "));
  const box = [...seen.matchAll(BOX)].filter((m) => isSlot(m[1])).map((m) => [m.index, m.index + m[0].length, text.slice(m.index, m.index + m[0].length)]);
  const line = [...seen.matchAll(LINE)].filter((m) => !box.some(([a, b]) => a <= m.index && m.index < b)).map((m) => [m.index, m.index + m[0].length, m[0]]);
  return [...box, ...line].sort((a, b) => a[0] - b[0]);
}

export const findBlanks = (text) => [...new Set(blankSpans(text).map(([, , s]) => s))];

// THE PRESS ASKS ONCE (the owner, 2026-11-08): Send stays lit over a draft still holding a blank, and pressing it asks "This still has [ROOM].
// Send anyway?" - every draft card that sends reads this one line. "" when nothing is left to fill. A long choice is cut to its head
export function blankAsk(text) {
  const [b] = findBlanks(text);
  return b ? `This still has ${b.length > 40 ? `${b.slice(0, 38).trimEnd()}…${b.startsWith("[") ? "]" : ""}` : b}. Send anyway?` : "";
}

// "Fill in [REASON] first" while a blank remains; "" when the text can go - word for word the server's
export function blankRefusal(text) {
  const b = findBlanks(text);
  return !b.length ? "" : `Fill in ${b.length === 1 ? b[0] : `${b.slice(0, -1).join(", ")} and ${b.at(-1)}`} first`;
}
