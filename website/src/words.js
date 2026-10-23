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
// a dashboard's doors, filters and page buttons (dashboards.py, src/dashboard/)
export const DASH = words.dashboard;
// one name per thing the owner is shown, and the surfaces that are gone (words.json's nouns and gone)
export const NOUNS = Object.fromEntries(Object.entries(words.nouns).filter(([k]) => !k.startsWith("_")));
export const noun = (id) => NOUNS[id] || String(id || "");
export const GONE = words.gone.words;
// a tool that runs on the owner's own machine - "claude (on this computer)", the server's words.local said the same way
export const LOCAL = words.local;
export const localName = (tool) => `${tool} (${LOCAL})`;
// one pattern per word: an all-caps word (CLI, PR, JSON) is matched as written, the rest in any case; a prefix ("claude-") has no
// end boundary. Word edges keep "approve" from reading as "PR".
const esc = (w) => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
export const JARGON_RES = [...JARGON.map((w) => new RegExp(`\\b${esc(w)}${/-$/.test(w) ? "" : "\\b"}`, w === w.toUpperCase() ? "" : "i")),
  ...GONE.map((w) => new RegExp(`\\b${esc(w)}\\b`))];   // a removed surface is matched as written: "the project timeline" is a word
export const jargonIn = (text) => { const s = String(text || ""); for (const re of JARGON_RES) { const m = s.match(re); if (m) return m; } return null; };
// WHEN THE ADVISOR LIGHTS NOTHING (advisor.status {none: why}): only no AI is said, with its way out (the owner, 2026-10-23: "No
// suggestion...", "Nothing to decide..." and "Thinking..." went) - any other reason is silent, with Next lit
const NONE = Object.fromEntries(Object.entries(words.advice_none).filter(([k]) => !k.startsWith("_")));
export const adviceNone = (why) => NONE[why] || { line: "", move: "next" };
export const ADVICE_NONE = NONE;
// THE ONE RULEBOOK's words (rulebook.py): each state's line and the verbs it lights, the server's and the page's alike
export const ADVICE_RULE = Object.fromEntries(Object.entries(words.advice_rule).filter(([k]) => !k.startsWith("_")));
