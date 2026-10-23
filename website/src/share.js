// SHARE A RESULT (the owner, 2026-10-23: "button on report on bottom named share"): what the one Share verb offers and what each of its
// ways posts - the server's sharing.py does the work. Pure, so the menu's greying and the request bodies are tested without a page.
//
// A SHAREABLE RESULT is { kind, title, text?, html?, data?, task?, message? }:
//   - a report's result names its `message`, an agent's or a workflow's names its `task` - the server reads the words from the store
//   - anything else on the table (a dashboard) brings its own `title` and `text` / `html` / `data` rows - the server cleans the HTML
import { CHOICES, hint, label } from "./buttons.js";

export const SHARE_ID = "share";                       // the row id; buttons.json's share_result lists it
export const WAYS = (CHOICES.share || []).map(([key, word]) => ({ key, word }));
// the Settings knob a greyed Shared link points at, and where the page brings it up (#settings=config&group=..&key=..)
export const LINK_SETTING = "share_links_lan";
export const SETTING_HREF = `settings=config&group=Sharing&key=${LINK_SETTING}`;

// is there anything to share: a result the store holds, or one that brought its own words
export const shareable = (r) => !!r && !!(r.task || r.message || String(r.text || "").trim() || String(r.html || "").trim() || (Array.isArray(r.data) && r.data.length));

// the menu's rows from /api/shares/ways: each way, greyed with the server's sentence; before it answers, greyed and "Checking…"; a page
// that could not ask says so on every row rather than offering what may not work.
// `summary`: whether this item offers "Email a summary" (the AI's message about a task's work - EmailSomeone), else `summaryWhy`; it
// goes by email too, so it is greyed with email's own reason. `noResult`: why the ways that carry THE RESULT cannot (nothing to carry yet).
export function waysOf(ways, failed = false, { summary = false, summaryWhy = "", noResult = "" } = {}) {
  return WAYS.map(({ key, word }) => {
    const w = ways?.[key === "summary" ? "email" : key];
    const own = key === "summary" ? (summary ? "" : summaryWhy || "a summary is written from a task's work - this has none") : noResult;
    const why = own || (failed ? "Taskuary did not answer - try again in a moment" : !ways ? "Checking…" : w?.ok ? "" : w?.why || "this cannot work here yet");
    return { key, word, ok: !why, why };
  });
}
// a greyed Shared link because the switch is off is one press from the switch (the owner turns it on; nothing turns it on for them)
export const offersSetting = (ways) => !!ways && !ways.setting && !ways.link?.ok;

// the body POST /api/shares takes for one way
export function shareBody(result, how, extra = {}) {
  const r = result || {}, pick = (k) => (r[k] == null || r[k] === "" ? {} : { [k]: r[k] });
  return { how, kind: r.kind || "result", ...pick("title"), ...pick("task"), ...pick("message"),
    ...(r.task || r.message ? {} : { ...pick("text"), ...pick("html"), ...(Array.isArray(r.data) ? { data: r.data } : {}) }), ...extra };
}

// what the card's badge says on its hover once a way went - the badge itself is the button's own word, "✓ Share" (presses are badges)
export function sharedNote(how, out, copied) {
  if (how === "summary") return `Drafted - it waits on its task for you to press ${label("approve")}`;
  if (how === "email") return `Drafted for ${(out?.to || []).join(", ")} on ${out?.ref || "its task"} - nothing is sent until you press ${label("approve")}`;
  const where = how === "link" ? `Link for your network, open until ${String(out?.expires || "").slice(0, 16)}` : how === "onedrive" ? "In OneDrive, in the Taskuary folder" : "In Google Drive, in the Taskuary folder";
  return `${where}${out?.url ? ` - ${copied ? "link copied" : `copy it: ${out.url}`}` : ""}`;
}

// the row verb: its one name and hint from buttons.json; `run` opens the menu at the button
export const shareVerb = (run, disabled = false, why = "") => ({ id: SHARE_ID, group: "more", tone: "s", label: label("share_result"), title: hint("share_result"), disabled, why, run });
