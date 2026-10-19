// THE PLACES A SENTENCE SENDS THE OWNER, AND THE WORDS THEY NEVER SEE - read from taskuary/words.json, the same file the server
// reads (taskuary/words.py). A sentence that names a place asks place(id) for its name and its link, never a typed
// "Settings → ..." string: a page that moves or is renamed is fixed in that one file.
import words from "../../taskuary/words.json" with { type: "json" };

export const PLACES = words.places;
// an unknown id is a bug in the caller, said plainly in the page rather than as "undefined"
export const place = (id) => PLACES[id] || { name: String(id || ""), href: "" };
export const placeName = (id) => place(id).name;
export const placeHref = (id) => place(id).href;
export const JARGON = words.jargon;
// a tool that runs on the owner's own machine - "claude (on this computer)", the server's words.local said the same way
export const LOCAL = words.local;
export const localName = (tool) => `${tool} (${LOCAL})`;
// one pattern per word: an all-caps word (CLI, PR, JSON) is matched as written, the rest in any case; a prefix ("claude-") has no
// end boundary. Word edges keep "approve" from reading as "PR".
const esc = (w) => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
export const JARGON_RES = JARGON.map((w) => new RegExp(`\\b${esc(w)}${/-$/.test(w) ? "" : "\\b"}`, w === w.toUpperCase() ? "" : "i"));
export const jargonIn = (text) => { const s = String(text || ""); for (const re of JARGON_RES) { const m = s.match(re); if (m) return m; } return null; };
// WHEN THE ADVISOR HAS NO LINE (advisor.status {none: why}): the sentence the strip says and the one move the row lights. An unknown
// reason is said as "nothing" - a strip that goes blank is the thing this exists to stop
const NONE = Object.fromEntries(Object.entries(words.advice_none).filter(([k]) => !k.startsWith("_")));
export const adviceNone = (why) => NONE[why] || NONE.nothing;
export const ADVICE_NONE = NONE;
