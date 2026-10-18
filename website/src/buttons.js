// THE ONE LIST OF BUTTONS, read from taskuary/buttons.json - the same file the server, the phone, the Advisor and the assistant's
// tools read (the owner, 2026-10-17: "if it's in one code place it's easy to update it later"). A button's words are never typed
// anywhere else in the page: a card asks label("close"), the task page's row asks labelOfRow("done"). Ids are wiring, labels are words.
import buttons from "../../taskuary/buttons.json" with { type: "json" };

export const VERBS = buttons.verbs, CHOICES = buttons.choices;
const { _: _r, ...removed } = buttons.removed;
// verbs that are gone: an old saved card or a typed word lands on the verb named (null: nothing - the button is never drawn)
export const REMOVED = removed;
export const liveVerb = (verb) => (verb && verb in REMOVED ? REMOVED[verb] : verb || null);
const of = (verb) => VERBS[liveVerb(verb)] || null;
export const label = (verb, state) => { const v = of(verb); return !v ? "" : (state && v.states?.[state]) || v.label; };
export const hint = (verb, state) => { const v = of(verb); return !v ? "" : (state && v.state_hints?.[state]) || v.hint || ""; };
// the task page's row registers its own ids (`done`, `remind`, `save-end`); each verb lists the ids that are the same act
const ROW = Object.fromEntries(Object.entries(VERBS).flatMap(([k, v]) => (v.row || []).map((r) => [r, k])));
export const verbOfRow = (rowId) => ROW[String(rowId || "").split(":").pop()] || null;
export const labelOfRow = (rowId, state) => label(verbOfRow(rowId), state);
export const hintOfRow = (rowId, state) => hint(verbOfRow(rowId), state);
export const rowsOf = (verb) => VERBS[liveVerb(verb)]?.row || [];
// every word a button may say - its label and each state's - so a check of "every named button exists" reads one list
export const ALL_LABELS = [...new Set(Object.values(VERBS).flatMap((v) => [v.label, ...Object.values(v.states || {})]))];
// a choice's answer, by its verb, inside one of the card's questions (Not ours / an idea / which agent)
export const choice = (q, verb) => (CHOICES[q] || []).find(([k]) => k === verb)?.[1] || "";
