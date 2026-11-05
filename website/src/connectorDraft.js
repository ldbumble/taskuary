// EVERY FIELD ON A CONNECTION CARD SAVES ITSELF (the owner, 2026-11-05: "what saves with one click while other hit the save buttons.
// it's just confusing"). The card's settings controls - a switch, a pick, a prompt typed - stage what they want into the card's draft,
// and the draft saves itself: a pick at once, typing once it pauses (ConnectorDraft.jsx useCardDraft). One Save bar for the card
// (2026-09-28) is gone with the Save buttons it stood beside; actions (test, sign in, add or remove a source) still happen at once.
//
// THE DRAFT HOLDS ONLY WHAT WAS CHANGED. A control posts the whole config it drew from, and saving that whole config wrote back a
// poller's watermark as the page last read it (#242). Staged, the config is cut down to the keys the control changed - a patch -
// and the save sends that patch (ConfigPatch), which the server merges over the config as it is now (store.merge_config).

export const DRAFT_FIELDS = ["ConfigJson", "Roles", "Scope", "Active"];

const parse = (s) => { try { return JSON.parse(s || "{}") || {}; } catch { return {}; } };
const same = (a, b) => JSON.stringify(a ?? null) === JSON.stringify(b ?? null);
const roles = (r) => String(r || "").split(",").map((x) => x.trim()).filter(Boolean).sort().join(",");

// the keys `next` changes over `base`, as a patch: a key gone is null (the server removes it)
export const cfgPatch = (base = {}, next = {}) => Object.fromEntries([...new Set([...Object.keys(base), ...Object.keys(next)])]
  .filter((k) => !same(base[k], next[k])).map((k) => [k, k in next && next[k] !== undefined ? next[k] : null]));
// a patch laid over a config: null removes its key
export const patched = (cfg = {}, patch = {}) => {
  const out = { ...cfg };
  for (const [k, v] of Object.entries(patch)) { if (v === null) delete out[k]; else out[k] = v; }
  return out;
};

// a post a card may hold back: only settings fields beside the row's id - anything else (a new source's Address, a
// secret) is an action and goes straight through
export const stageable = (body, idKey) => Object.keys(body || {}).every((k) => k === idKey || DRAFT_FIELDS.includes(k));

// fold one control's post into the draft. A control builds its ConfigJson from the row as drawn (`saved` with the draft laid over),
// so what it changed is what differs from that - kept as a patch, never as the whole config
export const stage = (want, body, saved = {}) => {
  const next = { ...(want || {}) };
  for (const k of Object.keys(body || {})) {
    if (k === "ConfigJson") next.cfg = { ...(want?.cfg || {}), ...cfgPatch(parse(applied(saved, want).ConfigJson), parse(body.ConfigJson)) };
    else if (DRAFT_FIELDS.includes(k)) next[k] = body[k];
  }
  return next;
};

// THE CONNECTION'S OWN SWITCH IS A PRESS, NOT A DRAFT (the owner, 2026-10-23: "you enable a connection and then sync now button
// shows up but then under it it says not saved"). It saves on the press, so the card is in one state; a source's switch is a setting
// in the draft, saved at once like every pick. `now` posts at once, `rest` is what is still staged (null: nothing)
export const splitNow = (body, idKey = "ConnectorId") => {
  if (!body || !("Active" in body)) return { now: null, rest: body };
  const { Active, ...others } = body, keys = Object.keys(others).filter((k) => k !== idKey);
  return { now: { [idKey]: body[idKey], Active: !!Active }, rest: keys.length ? others : null };
};

// SYNC NOW READS WHAT IS SAVED: shown only once the server has the card on, and greyed - the reason in its hover - while the
// card holds edits the server does not have yet (they save themselves in a moment). `edited`: a box typed into and not yet saved
export const syncState = (saved, pending = [], edited = false) =>
  !saved?.Active ? { show: false, ok: false, why: "" }
  : pending.length || edited ? { show: true, ok: false, why: "Saving your change - Sync now reads what is saved" }
  : { show: true, ok: true, why: "" };

// a card's own boxes (its credentials) typed past what they last saved - a secret typed at all counts
export const editedBoxes = (keys, cfg, base, secret = "") =>
  !!secret || keys.some((k) => String(cfg?.[k] ?? "") !== String(base?.[k] ?? ""));

// the row as its controls should draw it: saved, with the draft laid over
export const applied = (saved, want) => {
  if (!want) return saved;
  const out = { ...saved };
  for (const k of ["Roles", "Scope", "Active"]) if (k in want) out[k] = want[k];
  if (want.cfg) out.ConfigJson = JSON.stringify(patched(parse(saved?.ConfigJson), want.cfg));
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
    for (const [k, v] of Object.entries(want.cfg)) if (!same(base[k], v)) out.push({ field: "ConfigJson", key: k, from: base[k], to: v ?? undefined });
  }
  return out;
};

// the one post that saves a row's draft - its changed fields, and its changed config keys as a patch - or null when nothing differs
export const saveBody = (saved, want, idKey) => {
  const diff = changes(saved, want);
  if (!diff.length) return null;
  const body = { [idKey]: saved[idKey] };
  for (const c of diff) {
    if (c.field === "ConfigJson") body.ConfigPatch = { ...(body.ConfigPatch || {}), [c.key]: want.cfg[c.key] };
    else body[c.field] = want[c.field];
  }
  return body;
};

// the draft once the row came back as `saved`: what the server now holds drops out, so a staged key never hides a later change to it
export const prune = (saved, want) => {
  if (!want || !saved) return want || null;
  const left = new Set(changes(saved, want).map((c) => c.key)), out = {};
  for (const k of ["Roles", "Scope", "Active"]) if (k in want && left.has(k)) out[k] = want[k];
  const cfg = Object.fromEntries(Object.entries(want.cfg || {}).filter(([k]) => left.has(k)));
  if (Object.keys(cfg).length) out.cfg = cfg;
  return Object.keys(out).length ? out : null;
};

// THE QUIET TICK BY A FIELD: "Saved" once its save landed, "Not saved - <why>" when the server refused it, nothing while it waits
export const tickWords = (st) => (!st ? "" : st.state === "saved" ? "Saved" : st.state === "error" ? `Not saved - ${st.why || "try again"}` : "");
// a refusal in the server's own words, or a plain one
export const whyNot = (e) => String(e?.response?.data?.detail || e?.message || "the change did not reach Taskuary - it will try again on your next edit");
