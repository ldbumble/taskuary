// ONE SAVE PER CONNECTION CARD (the owner, 2026-09-28: "all connectors should have save button and show pending
// change? better ux"). A card's settings controls used to post the moment they were touched - sixteen of them - while
// three sections had Save buttons of their own, so "Ranked together" saved by itself and nothing said it had. The card
// now holds what its controls pick as a DRAFT - the connection's own fields and its sources' - and one bar lists each
// change and saves them together. Actions (test, sign in, reset, add or remove a source) still happen at once.
//
// The draft is what the controls WANT, and pending is always want-vs-saved: a credential form that saves the config on
// its own simply takes those keys off the list.

export const DRAFT_FIELDS = ["ConfigJson", "Roles", "Scope", "Active"];

const parse = (s) => { try { return JSON.parse(s || "{}") || {}; } catch { return {}; } };
const same = (a, b) => JSON.stringify(a ?? null) === JSON.stringify(b ?? null);
const roles = (r) => String(r || "").split(",").map((x) => x.trim()).filter(Boolean).sort().join(",");

// a post a card may hold back: only settings fields beside the row's id - anything else (a new source's Address, a
// secret) is an action and goes straight through
export const stageable = (body, idKey) => Object.keys(body || {}).every((k) => k === idKey || DRAFT_FIELDS.includes(k));

// fold one control's post into the draft. A control builds its ConfigJson from the draft it was drawn from, so the
// newest one already carries every change before it
export const stage = (want, body) => {
  const next = { ...(want || {}) };
  for (const k of Object.keys(body || {})) {
    if (k === "ConfigJson") next.cfg = parse(body.ConfigJson);
    else if (DRAFT_FIELDS.includes(k)) next[k] = body[k];
  }
  return next;
};

// THE CONNECTION'S OWN SWITCH IS A PRESS, NOT A DRAFT (the owner, 2026-10-23: "you enable a connection and then sync now button
// shows up but then under it it says not saved"). Held for the bar, the switch drew the card on - Sync now and all - while the
// server still had it off and the bar said "Connection: off → on". It saves on the press now, so the card is in one state; a
// source's switch stays a setting in the draft. `now` posts at once, `rest` is what is still staged (null: nothing)
export const splitNow = (body, idKey = "ConnectorId") => {
  if (!body || !("Active" in body)) return { now: null, rest: body };
  const { Active, ...others } = body, keys = Object.keys(others).filter((k) => k !== idKey);
  return { now: { [idKey]: body[idKey], Active: !!Active }, rest: keys.length ? others : null };
};

// SYNC NOW READS WHAT IS SAVED: shown only once the server has the card on, and greyed - the reason in its hover - while the
// card holds edits the server does not have yet. `edited`: a box on the card typed into and not saved (its credentials)
export const syncState = (saved, pending = [], edited = false) =>
  !saved?.Active ? { show: false, ok: false, why: "" }
  : pending.length || edited ? { show: true, ok: false, why: "Save your changes first - Sync now reads what is saved" }
  : { show: true, ok: true, why: "" };

// a card's own boxes (its credentials, saved by their own button) typed past what they last saved - a secret typed at all counts
export const editedBoxes = (keys, cfg, base, secret = "") =>
  !!secret || keys.some((k) => String(cfg?.[k] ?? "") !== String(base?.[k] ?? ""));

// the row as its controls should draw it: saved, with the draft laid over
export const applied = (saved, want) => {
  if (!want) return saved;
  const out = { ...saved };
  for (const k of ["Roles", "Scope", "Active"]) if (k in want) out[k] = want[k];
  if (want.cfg) out.ConfigJson = JSON.stringify(want.cfg);
  return out;
};

// what the draft would change: [{field, key, from, to}] - `field` is the row column, `key` the config key within it
export const changes = (saved, want) => {
  if (!want || !saved) return [];
  const out = [];
  if ("Active" in want && !!want.Active !== !!saved.Active) out.push({ field: "Active", key: "Active", from: !!saved.Active, to: !!want.Active });
  if ("Roles" in want && roles(want.Roles) !== roles(saved.Roles)) out.push({ field: "Roles", key: "Roles", from: roles(saved.Roles), to: roles(want.Roles) });
  if ("Scope" in want && String(want.Scope || "").toLowerCase() !== String(saved.Scope || "").toLowerCase())
    out.push({ field: "Scope", key: "Scope", from: saved.Scope || "", to: want.Scope || "" });
  if (want.cfg) {
    const base = parse(saved.ConfigJson);
    for (const k of new Set([...Object.keys(base), ...Object.keys(want.cfg)]))
      if (!same(base[k], want.cfg[k])) out.push({ field: "ConfigJson", key: k, from: base[k], to: want.cfg[k] });
  }
  return out;
};

// the one post that saves a row's draft, or null when nothing differs
export const saveBody = (saved, want, idKey) => {
  const diff = changes(saved, want);
  if (!diff.length) return null;
  const body = { [idKey]: saved[idKey] };
  for (const c of diff) {
    if (c.field === "ConfigJson") body.ConfigJson = JSON.stringify(want.cfg);
    else body[c.field] = want[c.field];
  }
  return body;
};

// a value as the bar says it
export const say = (v, key, words = {}) => {
  if (words[key] && words[key][String(v ?? "")] !== undefined) return words[key][String(v ?? "")];
  if (v === true) return "on";
  if (v === false || v === undefined || v === null || v === "") return "off";
  if (Array.isArray(v)) return v.length ? v.join(", ") : "none";
  if (typeof v === "object") return "edited";
  const s = String(v);
  return s.length > 40 ? `${s.slice(0, 39)}…` : s;
};

// LEAVING KEEPS THE DRAFT (the owner, 2026-10-21: no "are you sure"): the crumb asked "Leave without saving 1 change(s)?" in the
// browser's own box. Saving on the way out would post what the owner had not said yes to - a switch, a role - so the draft is
// kept instead, per card, for as long as the app is open: back on the card, the bar still lists the changes and Save or Discard
// them. Nothing is lost and nothing is saved behind the owner's back.
const KEPT = new Map();
export const keptDraft = (id) => (id != null && KEPT.get(id)) || { want: null, wantSrc: {} };
export function keepDraft(id, want, wantSrc) {
  if (id == null) return;
  if (want || Object.keys(wantSrc || {}).length) KEPT.set(id, { want, wantSrc: wantSrc || {} });
  else KEPT.delete(id);
}
