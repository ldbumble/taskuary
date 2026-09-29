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
